# YouTube Downloader

YouTube動画を簡単にダウンロードできる、YouTube風ダークUIのツールです。
**ブラウザ版(Web UI)** と **デスクトップ版(PyQt6)** の2つを同梱しています。

- 対応URL: 通常動画 (`watch?v=`) / 短縮URL (`youtu.be/`) / Shorts (`/shorts/`)
- ダウンロード形式: 最高画質(動画+音声) / 720p / 音声のみ(MP3 192kbps)
- 進捗(%・速度)のリアルタイム表示

## 必要なもの

- Python 3.10 以上
- [FFmpeg](https://ffmpeg.org/)(「最高画質」の結合と「MP3変換」に必要)
  - Windows: https://ffmpeg.org/download.html からダウンロードしてPATHを通す
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`

## セットアップ

```bash
git clone https://github.com/S-Yus/youtube-downloader.git
cd youtube-downloader
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

> デスクトップ版を使わない場合は `pip install flask yt-dlp` だけでも動きます。

## 使い方

### ブラウザ版(推奨)

```bash
python app.py
```

起動したらブラウザで **http://localhost:5000** を開いてください。
(`index.html` を直接ダブルクリックして開いても動きません。ダウンロード処理はPythonサーバー側で行うためです)

1. YouTubeのURLを貼り付けて「解析」
2. 「最高画質 / 720p / MP3」のカードから形式を選択
3. 「ダウンロード開始」→ 進捗バーが完了したら「ファイルを保存」

### デスクトップ版(PyQt6)

```bash
python main.py
```

アプリ内のブラウザでYouTubeを閲覧し、動画ページを開くとダウンロードボタンが赤く点灯します。

## 保存先

サーバー側の保存先は `~/Downloads/YouTubeDownloader/` です。
ブラウザ版では完了後に「ファイルを保存」ボタンからブラウザ経由でも取得できます。

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `Unexpected token '<' ... is not valid JSON` | `index.html` を直接開いています。`python app.py` を実行して http://localhost:5000 からアクセスしてください |
| FFmpeg未検出エラー | FFmpegをインストールしてPATHを通してください |
| ダウンロードに失敗する | `pip install -U yt-dlp` でyt-dlpを最新版に更新してください(YouTube側の仕様変更に追従するため、こまめな更新を推奨) |

## 注意事項

本ツールは**個人的な利用**を想定しています。
コンテンツのダウンロードは、著作権法およびYouTubeの利用規約の範囲内で、自己責任で行ってください。著作権者の許可なくコンテンツを再配布することはできません。

## ライセンス

[MIT License](LICENSE)
