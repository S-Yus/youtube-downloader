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

### インターネットに公開する(本人専用)

全ページ・全APIがログイン必須で、ログイン試行は同一IPで5回失敗すると5分間ロックされます。
公開する場合は**必ずランダムな長いパスフレーズ**を設定してください:

```bash
# ランダムパスフレーズの生成例
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

#### おすすめ: 自宅PC + Cloudflare Tunnel

自宅の回線(住宅用IP)から動かすためYouTubeにブロックされず、ポート開放も不要で、自動的にHTTPS化されます。

```bash
# 1. サーバーを起動(localhostのままでOK)
APP_USERNAME=yourname APP_PASSWORD='生成したパスフレーズ' SECRET_KEY='固定のランダム値' python app.py

# 2. 別ターミナルで cloudflared を起動(https://は自動付与)
cloudflared tunnel --url http://localhost:5000
```

表示された `https://xxxx.trycloudflare.com` のURLに、スマホや外出先のPCからアクセスできます。
(このクイックトンネルのURLは起動ごとに変わります。固定URLにしたい場合はCloudflareアカウント+独自ドメインで「名前付きトンネル」を作成してください)

cloudflaredのインストール: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

#### 常時公開する場合は gunicorn を推奨

```bash
pip install gunicorn
APP_USERNAME=... APP_PASSWORD=... SECRET_KEY=... gunicorn -w 1 --threads 8 -b 127.0.0.1:5000 app:app
```

※ ジョブ管理・レート制限をメモリ上に持つため、ワーカー数は `-w 1` のまま `--threads` で並行性を確保してください。

#### 注意

- ⚠ RenderやRailwayなどのクラウドにデプロイすると、データセンターIPがYouTubeにボット判定されてダウンロードがほぼ失敗します。自宅PCから動かすのが確実です
- URLとパスフレーズは他人に教えないでください(本ツールは1ユーザー前提です)

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
