# 🎬 KIMIDORI Movie Auto

## YouTube動画自動生成・編集・投稿ツール

AIが動画をゼロから生成、または既存動画を自動編集し、YouTubeに非公開で自動投稿するツールです。

---

## 機能概要

### モードA: ゼロから動画生成
- テーマを入力するだけでショート動画（1分以内）を自動生成
- Gemini APIで台本を自動生成
- Google Cloud TTSで音声合成
- FFmpegでテロップ付き動画を合成
- YouTubeに非公開で自動投稿

### モードB: 既存動画の自動編集
- 素材動画をアップロードするだけで自動編集
- Whisperで音声認識・タイムスタンプ取得
- 無音部分の自動カット（ジェットカット）
- 音声認識結果から自動テロップ付与
- YouTubeに非公開で自動投稿

---

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| フロントエンド | HTML / CSS / JavaScript |
| 認証・DB | Firebase Auth / Firestore |
| ストレージ | Firebase Cloud Storage |
| バックエンド | FastAPI (Python) on Cloud Run |
| 動画処理 | FFmpeg / MoviePy |
| 音声認識 | OpenAI Whisper (オープンソース) |
| 音声合成 | Google Cloud Text-to-Speech |
| 台本生成 | Gemini API |
| 動画投稿 | YouTube Data API v3 |

---

## セットアップ手順

### 1. 前提条件
- Google Cloud プロジェクト（課金有効）
- Firebase プロジェクト
- Python 3.11+
- Docker
- gcloud CLI

### 2. Firebase 設定
```bash
# Firebase CLIインストール
npm install -g firebase-tools

# ログイン＆初期化
firebase login
firebase init
```

`frontend/js/firebase-config.js` の値を自分のプロジェクトに合わせて変更してください。

### 3. Google Cloud API 有効化
```bash
# 必要なAPIを有効化
gcloud services enable \
  run.googleapis.com \
  texttospeech.googleapis.com \
  youtube.googleapis.com \
  generativelanguage.googleapis.com \
  cloudbuild.googleapis.com
```

### 4. 環境変数の設定
```bash
# .env ファイル（backend/ ディレクトリ）
GOOGLE_CLOUD_PROJECT=your-project-id
FIREBASE_STORAGE_BUCKET=your-project.appspot.com
GEMINI_API_KEY=your-gemini-api-key
WHISPER_MODEL=base
```

### 5. YouTube API 認証
1. Google Cloud Console で「OAuth 2.0 クライアント ID」を作成
2. `client_secrets.json` をダウンロードして `backend/` に配置
3. 初回起動時にブラウザで認証フローを完了

### 6. Cloud Run にデプロイ
```bash
cd backend

# Dockerイメージをビルド＆プッシュ
gcloud builds submit --tag gcr.io/YOUR_PROJECT/kimidori-movie-auto

# Cloud Run にデプロイ
gcloud run deploy kimidori-movie-auto \
  --image gcr.io/YOUR_PROJECT/kimidori-movie-auto \
  --platform managed \
  --region asia-northeast1 \
  --memory 4Gi \
  --cpu 4 \
  --timeout 3600 \
  --max-instances 5 \
  --concurrency 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=YOUR_PROJECT,FIREBASE_STORAGE_BUCKET=YOUR_BUCKET,GEMINI_API_KEY=YOUR_KEY"
```

### 7. フロントエンドのデプロイ
```bash
# Cloud Run の URL を firebase-config.js の API_BASE_URL に設定
firebase deploy --only hosting
```

---

## ローカル開発

### バックエンド
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### フロントエンド
```bash
# 任意のHTTPサーバーで配信
cd frontend
python -m http.server 3000
```

---

## ディレクトリ構成

```
kimidori_movie_auto/
├── frontend/                   # フロントエンド
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       ├── firebase-config.js
│       └── job-manager.js
├── backend/                    # バックエンド
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── processors/
│   │   ├── mode_a.py          # モードA処理
│   │   ├── mode_b.py          # モードB処理
│   │   ├── script_generator.py # 台本生成
│   │   ├── tts_engine.py      # 音声合成
│   │   └── subtitle_burner.py # テロップ焼付
│   ├── services/
│   │   ├── firestore_service.py
│   │   ├── storage_service.py
│   │   └── youtube_service.py
│   └── utils/
│       ├── ffmpeg_utils.py
│       └── whisper_utils.py
├── firebase.json
├── firestore.rules
├── storage.rules
└── README.md
```

---

## ライセンス

MIT License
