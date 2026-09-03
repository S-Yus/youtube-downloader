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
import uuid
import shutil
import threading

from flask import Flask, jsonify, render_template, request, send_file

try:
    import yt_dlp
except ImportError:
    print("yt-dlp がインストールされていません。`pip install yt-dlp` を実行してください。")
    sys.exit(1)

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloader")

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

    ydl_opts = {
        "outtmpl": os.path.join(job_dir, "%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

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
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def api_info():
    """動画のタイトル・サムネイル等のメタ情報を取得する。"""
    url = (request.json or {}).get("url", "").strip()
    if not is_video_url(url):
        return jsonify({"error": "YouTubeの動画URLではありません。watch?v= / youtu.be / shorts のURLを入力してください。"}), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
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
def api_progress(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify({"error": "ジョブが見つかりません。"}), 404
        return jsonify({k: v for k, v in job.items() if k != "filepath"})


@app.route("/api/file/<job_id>")
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
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
