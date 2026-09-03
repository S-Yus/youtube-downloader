# -*- coding: utf-8 -*-
"""
YouTube専用ダウンロードブラウザ (YouTube Downloader)
====================================================

依存ライブラリのセットアップ:
    pip install PyQt6 PyQt6-WebEngine yt-dlp

※ 「最高画質(動画+音声)」および「MP3変換」には FFmpeg が必要です。
   - Ubuntu/Debian: sudo apt install ffmpeg
   - macOS:         brew install ffmpeg
   - Windows:       https://ffmpeg.org/download.html からダウンロードしてPATHを通す

実行:
    python main.py
"""

import os
import re
import sys
import shutil
import subprocess

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QProgressBar,
    QDialog,
    QMessageBox,
    QFrame,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    import yt_dlp
except ImportError:
    print("yt-dlp がインストールされていません。`pip install yt-dlp` を実行してください。")
    sys.exit(1)


# ----------------------------------------------------------------------------
# 定数
# ----------------------------------------------------------------------------

HOME_URL = "https://www.youtube.com"
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTubeDownloader")

# YouTube動画ページ判定用の正規表現
VIDEO_URL_PATTERNS = [
    re.compile(r"(?:www\.|m\.)?youtube\.com/watch\?.*v=[\w-]{6,}"),  # 通常動画
    re.compile(r"youtu\.be/[\w-]{6,}"),                               # 短縮URL
    re.compile(r"(?:www\.|m\.)?youtube\.com/shorts/[\w-]{6,}"),       # Shorts
]

# YouTube Pop Style QSS
APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0F0F0F;
    color: #FFFFFF;
    font-family: "Segoe UI", "Yu Gothic UI", "Hiragino Sans", sans-serif;
    font-size: 13px;
}

/* --- URLバー --- */
QLineEdit {
    background-color: #212121;
    color: #FFFFFF;
    border: 2px solid #303030;
    border-radius: 16px;
    padding: 8px 16px;
    selection-background-color: #3EA6FF;
}
QLineEdit:focus {
    border: 2px solid #3EA6FF;
}

/* --- ナビゲーションボタン --- */
QPushButton {
    background-color: #212121;
    color: #FFFFFF;
    border: none;
    border-radius: 16px;
    padding: 8px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #383838;
}
QPushButton:pressed {
    background-color: #3EA6FF;
    color: #0F0F0F;
}
QPushButton:disabled {
    background-color: #1A1A1A;
    color: #555555;
}

/* --- ダウンロードボタン(非アクティブ) --- */
QPushButton#downloadButton {
    background-color: #212121;
    color: #777777;
    border: 2px solid #303030;
    border-radius: 18px;
    padding: 8px 20px;
}

/* --- ダウンロードボタン(アクティブ: YouTube Red 発光) --- */
QPushButton#downloadButton[active="true"] {
    background-color: #FF0000;
    color: #FFFFFF;
    border: 2px solid #FF4E45;
}
QPushButton#downloadButton[active="true"]:hover {
    background-color: #FF4E45;
}

/* --- プログレスバー --- */
QProgressBar {
    background-color: #212121;
    border: none;
    border-radius: 12px;
    height: 24px;
    text-align: center;
    color: #FFFFFF;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #FF0000;
    border-radius: 12px;
}

/* --- ステータスラベル --- */
QLabel#speedLabel {
    color: #3EA6FF;
    font-weight: bold;
}
QLabel#statusLabel {
    color: #AAAAAA;
}

/* --- ダイアログ --- */
QDialog {
    background-color: #0F0F0F;
}

/* --- 画質選択カード --- */
QPushButton#qualityCard {
    background-color: #212121;
    color: #FFFFFF;
    border: 2px solid #303030;
    border-radius: 16px;
    padding: 18px;
    text-align: left;
    font-size: 14px;
}
QPushButton#qualityCard:hover {
    border: 2px solid #3EA6FF;
    background-color: #2A2A2A;
}
QPushButton#qualityCard:pressed {
    border: 2px solid #FF0000;
}

/* --- メッセージボックス --- */
QMessageBox {
    background-color: #212121;
}
QMessageBox QPushButton {
    background-color: #3EA6FF;
    color: #0F0F0F;
    border-radius: 12px;
    padding: 8px 20px;
    min-width: 90px;
}
QMessageBox QPushButton:hover {
    background-color: #66BBFF;
}
"""


# ----------------------------------------------------------------------------
# ユーティリティ
# ----------------------------------------------------------------------------

def is_video_url(url: str) -> bool:
    """URLがYouTubeの動画ページかどうか判定する。"""
    return any(p.search(url) for p in VIDEO_URL_PATTERNS)


def ffmpeg_available() -> bool:
    """FFmpegがPATH上に存在するか確認する。"""
    return shutil.which("ffmpeg") is not None


def open_folder(path: str) -> None:
    """OSに応じてフォルダをファイルマネージャで開く。"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"フォルダを開けませんでした: {e}")


# ----------------------------------------------------------------------------
# ダウンロードスレッド
# ----------------------------------------------------------------------------

class DownloadThread(QThread):
    """yt-dlp によるダウンロードをバックグラウンドで実行するスレッド。"""

    progress = pyqtSignal(float, str)   # (パーセント, 速度文字列)
    finished_ok = pyqtSignal(str)       # 保存先パス
    failed = pyqtSignal(str)            # エラーメッセージ

    def __init__(self, url: str, mode: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.mode = mode  # "best" | "720p" | "mp3"

    def _hook(self, d: dict) -> None:
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
            self.progress.emit(percent, speed_str)
        elif d.get("status") == "finished":
            # 後処理(結合/変換)フェーズに入るため100%表示
            self.progress.emit(100.0, "後処理中...")

    def run(self) -> None:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        ydl_opts = {
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "progress_hooks": [self._hook],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

        if self.mode == "best":
            ydl_opts["format"] = "bestvideo+bestaudio/best"
            ydl_opts["merge_output_format"] = "mp4"
        elif self.mode == "720p":
            ydl_opts["format"] = (
                "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            )
            ydl_opts["merge_output_format"] = "mp4"
        elif self.mode == "mp3":
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
                ydl.download([self.url])
            self.finished_ok.emit(DOWNLOAD_DIR)
        except yt_dlp.utils.DownloadError as e:
            self.failed.emit(f"ダウンロードに失敗しました:\n{e}")
        except Exception as e:
            self.failed.emit(f"予期しないエラーが発生しました:\n{e}")


# ----------------------------------------------------------------------------
# 画質選択ダイアログ
# ----------------------------------------------------------------------------

class QualityDialog(QDialog):
    """「最高画質」「720p」「音声のみ(MP3)」をカードUIで選択するダイアログ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_mode: str | None = None

        self.setWindowTitle("ダウンロード形式を選択")
        self.setFixedWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("🎬  ダウンロード形式を選択")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        cards = [
            ("best", "🏆  最高画質 (動画+音声)", "最高解像度の動画と音声を結合して保存"),
            ("720p", "📺  720p", "バランスの良い標準HD画質"),
            ("mp3", "🎵  音声のみ (MP3)", "音声をMP3 (192kbps) に変換して保存"),
        ]

        for mode, label, desc in cards:
            btn = QPushButton(f"{label}\n{desc}")
            btn.setObjectName("qualityCard")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, m=mode: self._select(m))
            layout.addWidget(btn)

        cancel = QPushButton("キャンセル")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _select(self, mode: str) -> None:
        self.selected_mode = mode
        self.accept()


# ----------------------------------------------------------------------------
# メインウィンドウ
# ----------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader Browser")
        self.resize(1200, 800)

        self.download_thread: DownloadThread | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- 上部ナビゲーションバー ---
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.back_btn = QPushButton("◀")
        self.forward_btn = QPushButton("▶")
        self.reload_btn = QPushButton("⟳")
        for b in (self.back_btn, self.forward_btn, self.reload_btn):
            b.setFixedWidth(44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("URLを入力して Enter...")

        self.download_btn = QPushButton("⬇ ダウンロード")
        self.download_btn.setObjectName("downloadButton")
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_download_active(False)

        nav.addWidget(self.back_btn)
        nav.addWidget(self.forward_btn)
        nav.addWidget(self.reload_btn)
        nav.addWidget(self.url_bar, stretch=1)
        nav.addWidget(self.download_btn)
        root.addLayout(nav)

        # --- ブラウザ本体 ---
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl(HOME_URL))
        root.addWidget(self.browser, stretch=1)

        # --- 下部ステータスバー ---
        status_frame = QFrame()
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(8, 0, 8, 0)
        status_layout.setSpacing(12)

        self.status_label = QLabel("待機中")
        self.status_label.setObjectName("statusLabel")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(24)

        self.speed_label = QLabel("-- KB/s")
        self.speed_label.setObjectName("speedLabel")
        self.speed_label.setFixedWidth(110)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar, stretch=1)
        status_layout.addWidget(self.speed_label)
        root.addWidget(status_frame)

        # --- シグナル接続 ---
        self.back_btn.clicked.connect(self.browser.back)
        self.forward_btn.clicked.connect(self.browser.forward)
        self.reload_btn.clicked.connect(self.browser.reload)
        self.url_bar.returnPressed.connect(self._navigate)
        self.browser.urlChanged.connect(self._on_url_changed)
        self.download_btn.clicked.connect(self._on_download_clicked)

    # ------------------------------------------------------------------
    # ナビゲーション
    # ------------------------------------------------------------------

    def _navigate(self) -> None:
        text = self.url_bar.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        self.browser.setUrl(QUrl(text))

    def _on_url_changed(self, qurl: QUrl) -> None:
        url = qurl.toString()
        self.url_bar.setText(url)
        self.url_bar.setCursorPosition(0)
        self._set_download_active(is_video_url(url))

    def _set_download_active(self, active: bool) -> None:
        """ダウンロードボタンのアクティブ状態(赤発光)を切り替える。"""
        self.download_btn.setProperty("active", "true" if active else "false")
        self.download_btn.setEnabled(active and self.download_thread is None)
        # プロパティ変更後にスタイルを再適用
        self.download_btn.style().unpolish(self.download_btn)
        self.download_btn.style().polish(self.download_btn)

    # ------------------------------------------------------------------
    # ダウンロード処理
    # ------------------------------------------------------------------

    def _on_download_clicked(self) -> None:
        url = self.browser.url().toString()
        if not is_video_url(url):
            QMessageBox.warning(self, "エラー", "動画ページのURLを取得できませんでした。\n動画ページを開いてから再度お試しください。")
            return
        if self.download_thread is not None:
            QMessageBox.information(self, "実行中", "現在ダウンロードが進行中です。完了までお待ちください。")
            return

        dialog = QualityDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_mode is None:
            return
        mode = dialog.selected_mode

        # FFmpegチェック(結合・MP3変換に必須)
        if mode in ("best", "mp3") and not ffmpeg_available():
            QMessageBox.critical(
                self,
                "FFmpeg未検出",
                "FFmpegが見つかりません。\n"
                "「最高画質」および「MP3変換」にはFFmpegが必要です。\n\n"
                "インストール方法:\n"
                "  Windows: https://ffmpeg.org/download.html\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg",
            )
            return

        self._start_download(url, mode)

    def _start_download(self, url: str, mode: str) -> None:
        self.download_thread = DownloadThread(url, mode)
        self.download_thread.progress.connect(self._on_progress)
        self.download_thread.finished_ok.connect(self._on_download_finished)
        self.download_thread.failed.connect(self._on_download_failed)
        self.download_thread.finished.connect(self._on_thread_done)

        mode_names = {"best": "最高画質", "720p": "720p", "mp3": "音声のみ(MP3)"}
        self.status_label.setText(f"ダウンロード中 ({mode_names.get(mode, mode)})")
        self.progress_bar.setValue(0)
        self.speed_label.setText("-- KB/s")
        self.download_btn.setEnabled(False)

        self.download_thread.start()

    def _on_progress(self, percent: float, speed: str) -> None:
        self.progress_bar.setValue(int(percent))
        self.speed_label.setText(speed)

    def _on_download_finished(self, folder: str) -> None:
        self.status_label.setText("完了")
        self.progress_bar.setValue(100)
        self.speed_label.setText("-- KB/s")

        box = QMessageBox(self)
        box.setWindowTitle("ダウンロード完了")
        box.setText("🎉 ダウンロードが完了しました!")
        box.setIcon(QMessageBox.Icon.Information)
        open_btn = box.addButton("保存先フォルダを開く", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("閉じる", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            open_folder(folder)

    def _on_download_failed(self, message: str) -> None:
        self.status_label.setText("エラー")
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "ダウンロードエラー", message)

    def _on_thread_done(self) -> None:
        thread = self.download_thread
        self.download_thread = None
        if thread is not None:
            thread.deleteLater()
        # 現在のURLに応じてボタン状態を復元
        self._set_download_active(is_video_url(self.browser.url().toString()))
        if self.status_label.text().startswith("ダウンロード中"):
            self.status_label.setText("待機中")

    def closeEvent(self, event) -> None:
        if self.download_thread is not None and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "確認",
                "ダウンロードが進行中です。終了しますか?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self.download_thread.terminate()
            self.download_thread.wait(3000)
        event.accept()


# ----------------------------------------------------------------------------
# エントリポイント
# ----------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
