# ============================================================
# KIMIDORI YouTube Auto — Cloud Run 用 Dockerfile
# Python 3.11 + FFmpeg + Whisper + FastAPI + 静的フロントエンド
# ============================================================

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    XDG_CACHE_HOME=/app/cache \
    FFMPEG_THREADS=4 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    libsndfile1 \
    libmagic1 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存関係のインストール
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Whisperモデルの事前ダウンロード（ビルド時キャッシュ）
RUN python -c "import whisper; whisper.load_model('base')"

# ソースコード全体のコピー (frontend, backend)
COPY . .

# ディレクトリ作成
RUN mkdir -p /app/backend/cache /app/backend/tmp /tmp/kimidori

WORKDIR /app/backend

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# ポートはCloud Runで自動注入される $PORT に対応
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 3600"]
