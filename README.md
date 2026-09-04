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

1. ログイン画面でユーザー名・パスワードを入力
2. YouTubeのURLを貼り付けて「解析」
3. 「最高画質 / 720p / MP3」のカードから形式を選択
4. 「ダウンロード開始」→ 進捗バーが完了したら「ファイルを保存」

### ログイン認証

本人だけが使えるよう、全ページ・全APIはログイン必須です。認証情報は環境変数で設定します:

```bash
export APP_USERNAME=yourname
export APP_PASSWORD=your-strong-password
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

`APP_PASSWORD` を設定しない場合は、起動時にランダムなパスワードが生成されコンソールに表示されます。
`SECRET_KEY` を固定するとサーバー再起動後もログイン状態が維持されます。

### 外部からアクセスできるように公開する

デフォルトではlocalhostのみ待ち受けます。他の端末や外出先から使う場合:

```bash
HOST=0.0.0.0 PORT=5000 python app.py
```

- **おすすめ: [Tailscale](https://tailscale.com/) などのVPN経由** — 自宅PCでサーバーを動かし、自分の端末からだけアクセスできます。インターネットに晒さないため最も安全です
- インターネットに直接公開する場合は必ず強いパスワードとHTTPS(リバースプロキシ)を併用してください
- ⚠ RenderやRailwayなどのクラウドにデプロイしても、データセンターIPはYouTubeにボット判定されてダウンロードが失敗することが多く、実用になりません。自宅PC + VPNの構成を推奨します

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
