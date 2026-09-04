# -*- coding: utf-8 -*-
"""
YouTube Downloader — ブラウザ(Web)版
=====================================

依存ライブラリのセットアップ:
    pip install flask yt-dlp

※ 「最高画質(動画+音声)」および「MP3変換」には FFmpeg が必要です。
   - Ubuntu/Debian: sudo apt install ffmpeg
   - macOS:         brew install ffmpeg
   - Windows:       https://ffmpeg.org/download.html からダウンロードしてPATHを通す

実行:
    python app.py
    → ブラウザで http://localhost:5000 を開く
"""

import os
import re
import sys
import glob
import hmac
import time
import uuid
import shutil
import secrets
import threading
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, request, send_file, session

try:
    import yt_dlp
except ImportError:
    print("yt-dlp がインストールされていません。`pip install yt-dlp` を実行してください。")
    sys.exit(1)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# 認証設定
#   環境変数 APP_USERNAME / APP_PASSWORD でログイン情報を設定する。
#   APP_PASSWORD が未設定の場合はランダムなパスワードを生成して起動時に表示する。
#   SECRET_KEY はセッション署名用(未設定なら起動ごとにランダム生成)。
# ----------------------------------------------------------------------------
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
if not APP_PASSWORD:
    APP_PASSWORD = secrets.token_urlsafe(16)
    print("=" * 60)
    print("APP_PASSWORD が未設定のため、パスワードを自動生成しました:")
    print(f"  ユーザー名: {APP_USERNAME}")
    print(f"  パスワード: {APP_PASSWORD}")
    print("固定したい場合は環境変数 APP_USERNAME / APP_PASSWORD を設定してください。")
    print("=" * 60)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
if os.environ.get("HTTPS_ONLY") == "1":  # HTTPS配信時はcookieをSecureにする
    app.config["SESSION_COOKIE_SECURE"] = True

# ----------------------------------------------------------------------------
# ログイン試行のレート制限(総当たり攻撃対策)
#   同一IPからの連続失敗が MAX_LOGIN_FAILURES 回に達したら LOCKOUT_SECONDS 秒ロック。
# ----------------------------------------------------------------------------
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 300

login_failures: dict[str, list] = {}  # {ip: [失敗回数, ロック解除時刻]}
login_failures_lock = threading.Lock()


def client_ip() -> str:
    """リバースプロキシ/トンネル経由でも実クライアントIPを取得する。"""
    fwd = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def is_locked_out(ip: str) -> int:
    """ロック中なら残り秒数を、そうでなければ0を返す。"""
    with login_failures_lock:
        rec = login_failures.get(ip)
        if rec and rec[0] >= MAX_LOGIN_FAILURES:
            remaining = int(rec[1] - time.time())
            if remaining > 0:
                return remaining
            del login_failures[ip]
    return 0


def record_login_failure(ip: str) -> None:
    with login_failures_lock:
        rec = login_failures.setdefault(ip, [0, 0.0])
        rec[0] += 1
        if rec[0] >= MAX_LOGIN_FAILURES:
            rec[1] = time.time() + LOCKOUT_SECONDS


def clear_login_failures(ip: str) -> None:
    with login_failures_lock:
        login_failures.pop(ip, None)


def login_required(f):
    """未ログインならページは /login へリダイレクト、APIは401 JSONを返す。"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "ログインが必要です。", "auth": False}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

DOWNLOAD_DIR = os.environ.get(
    "DOWNLOAD_DIR", os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloader")
)

# YouTubeのcookieファイル(Netscape形式)。VPSなどデータセンターIPからの
# ボット判定を回避するために、自分のブラウザからエクスポートしたcookieを指定する。
COOKIES_FILE = os.environ.get("COOKIES_FILE", "")


def base_ydl_opts() -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

# YouTube動画ページ判定用の正規表現
VIDEO_URL_PATTERNS = [
    re.compile(r"(?:www\.|m\.)?youtube\.com/watch\?.*v=[\w-]{6,}"),  # 通常動画
    re.compile(r"youtu\.be/[\w-]{6,}"),                               # 短縮URL
    re.compile(r"(?:www\.|m\.)?youtube\.com/shorts/[\w-]{6,}"),       # Shorts
]

# ジョブ管理: {job_id: {status, percent, speed, title, error, filepath}}
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def is_video_url(url: str) -> bool:
    return any(p.search(url) for p in VIDEO_URL_PATTERNS)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _update_job(job_id: str, **kwargs) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def _download_worker(job_id: str, url: str, mode: str) -> None:
    """バックグラウンドスレッドで yt-dlp を実行する。"""
    job_dir = os.path.join(DOWNLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total * 100) if total else 0.0
            speed = d.get("speed")
            if speed:
                if speed >= 1024 * 1024:
                    speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
                else:
                    speed_str = f"{speed / 1024:.1f} KB/s"
            else:
                speed_str = "-- KB/s"
            _update_job(job_id, status="downloading", percent=round(percent, 1), speed=speed_str)
        elif d.get("status") == "finished":
            _update_job(job_id, status="processing", percent=100.0, speed="後処理中...")

    ydl_opts = base_ydl_opts()
    ydl_opts.update(
        {
            "outtmpl": os.path.join(job_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [hook],
        }
    )

    if mode == "best":
        ydl_opts["format"] = "bestvideo+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"
    elif mode == "720p":
        ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        ydl_opts["merge_output_format"] = "mp4"
    elif mode == "mp3":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        files = [f for f in glob.glob(os.path.join(job_dir, "*")) if os.path.isfile(f)]
        if not files:
            raise RuntimeError("ダウンロードファイルが見つかりませんでした。")
        # 後処理後に残った最新のファイルを採用
        filepath = max(files, key=os.path.getmtime)

        _update_job(
            job_id,
            status="done",
            percent=100.0,
            speed="",
            title=title,
            filepath=filepath,
            filename=os.path.basename(filepath),
        )
    except yt_dlp.utils.DownloadError as e:
        _update_job(job_id, status="error", error=f"ダウンロードに失敗しました: {e}")
    except Exception as e:
        _update_job(job_id, status="error", error=f"予期しないエラーが発生しました: {e}")


# ----------------------------------------------------------------------------
# ルーティング
# ----------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    return send_file(os.path.join(BASE_DIR, "index.html"))


@app.route("/login", methods=["GET"])
def login_page():
    if session.get("logged_in"):
        return redirect("/")
    return send_file(os.path.join(BASE_DIR, "login.html"))


@app.route("/api/login", methods=["POST"])
def api_login():
    ip = client_ip()
    remaining = is_locked_out(ip)
    if remaining > 0:
        return jsonify(
            {"error": f"ログイン失敗が続いたためロックされています。{remaining}秒後に再試行してください。"}
        ), 429

    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if hmac.compare_digest(username, APP_USERNAME) and hmac.compare_digest(password, APP_PASSWORD):
        clear_login_failures(ip)
        session["logged_in"] = True
        session.permanent = True
        return jsonify({"ok": True})

    record_login_failure(ip)
    time.sleep(1)  # 総当たりを遅くする
    return jsonify({"error": "ユーザー名またはパスワードが違います。"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/info", methods=["POST"])
@login_required
def api_info():
    """動画のタイトル・サムネイル等のメタ情報を取得する。"""
    url = (request.json or {}).get("url", "").strip()
    if not is_video_url(url):
        return jsonify({"error": "YouTubeの動画URLではありません。watch?v= / youtu.be / shorts のURLを入力してください。"}), 400
    try:
        with yt_dlp.YoutubeDL(base_ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
        return jsonify(
            {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "view_count": info.get("view_count"),
            }
        )
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"動画情報を取得できませんでした: {e}"}), 400
    except Exception as e:
        return jsonify({"error": f"予期しないエラー: {e}"}), 500


@app.route("/api/download", methods=["POST"])
@login_required
def api_download():
    """ダウンロードジョブを開始する。"""
    data = request.json or {}
    url = data.get("url", "").strip()
    mode = data.get("mode", "")

    if not is_video_url(url):
        return jsonify({"error": "YouTubeの動画URLではありません。"}), 400
    if mode not in ("best", "720p", "mp3"):
        return jsonify({"error": "不正なダウンロード形式です。"}), 400
    if mode in ("best", "mp3") and not ffmpeg_available():
        return jsonify(
            {
                "error": "FFmpegが見つかりません。「最高画質」「MP3変換」にはFFmpegが必要です。"
                "(Linux: sudo apt install ffmpeg / macOS: brew install ffmpeg)"
            }
        ), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "starting", "percent": 0.0, "speed": "-- KB/s", "error": None}

    t = threading.Thread(target=_download_worker, args=(job_id, url, mode), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/progress/<job_id>")
@login_required
def api_progress(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify({"error": "ジョブが見つかりません。"}), 404
        return jsonify({k: v for k, v in job.items() if k != "filepath"})


@app.route("/api/file/<job_id>")
@login_required
def api_file(job_id: str):
    """完了したファイルをブラウザへダウンロードさせる。"""
    with jobs_lock:
        job = jobs.get(job_id)
    if job is None or job.get("status") != "done":
        return jsonify({"error": "ファイルはまだ準備できていません。"}), 404
    filepath = job.get("filepath")
    if not filepath or not os.path.isfile(filepath):
        return jsonify({"error": "ファイルが見つかりません。"}), 404
    return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath))


if __name__ == "__main__":
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"保存先: {DOWNLOAD_DIR}")
    print("ブラウザで http://localhost:5000 を開いてください。")
    # 外部公開時は HOST=0.0.0.0 を設定する(PORT も環境変数で変更可)
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
        threaded=True,
    )
