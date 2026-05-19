# ============================================================
# KIMIDORI Movie Auto — Cloud Run 用 Dockerfile
# FFmpeg + Whisper + Python動画処理パイプライン
# ============================================================

# ベースイメージ: Python 3.11 (Debian Bookworm)
FROM python:3.11-slim-bookworm

# 環境変数設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    # Whisperモデルのキャッシュディレクトリ
    XDG_CACHE_HOME=/app/cache \
    # FFmpegスレッド数
    FFMPEG_THREADS=4

# システム依存パッケージのインストール
# - ffmpeg: 動画処理の中核
# - fonts-noto-cjk: 日本語テロップ用フォント
# - libsndfile1: 音声ファイル処理
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    libsndfile1 \
    libmagic1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリ設定
WORKDIR /app

# Python依存関係のインストール（キャッシュ最適化のため先にコピー）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Whisperモデルを事前ダウンロード（ビルド時にキャッシュ）
# "base" モデルを使用（精度とサイズのバランス）
RUN python -c "import whisper; whisper.load_model('base')"

# アプリケーションコードをコピー
COPY . .

# キャッシュディレクトリの作成
RUN mkdir -p /app/cache /app/tmp

# Cloud Runのポート
EXPOSE 8080

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# アプリケーション起動
# Cloud Runでは $PORT 環境変数でポートが指定される
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "3600"]
