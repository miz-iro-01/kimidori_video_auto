"""
KIMIDORI Movie Auto — 設定管理
環境変数からの設定読み込みとデフォルト値の定義
"""

import os
from pathlib import Path

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = Path(__file__).parent
TMP_DIR = Path(os.getenv("TMP_DIR", "/app/tmp"))
CACHE_DIR = Path(os.getenv("XDG_CACHE_HOME", "/app/cache"))

# 一時ファイル用ディレクトリを確保
TMP_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Firebase 設定
# =============================================================================
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "your-project.appspot.com")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "video_jobs")

# =============================================================================
# Google Cloud 設定
# =============================================================================
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")

# =============================================================================
# Gemini API 設定
# =============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# =============================================================================
# YouTube API 設定
# =============================================================================
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS", "/app/client_secrets.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "/app/youtube_token.json")

# =============================================================================
# Whisper 設定
# =============================================================================
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# =============================================================================
# 動画処理設定
# =============================================================================
# モードA: ショート動画
SHORT_VIDEO_WIDTH = 1080
SHORT_VIDEO_HEIGHT = 1920
SHORT_VIDEO_FPS = 30
SHORT_VIDEO_MAX_DURATION = 60  # 秒

# モードB: 長尺動画
LONG_VIDEO_WIDTH = 1920
LONG_VIDEO_HEIGHT = 1080
LONG_VIDEO_FPS = 30

# ジェットカット設定
SILENCE_THRESHOLD_DB = -35  # 無音判定の閾値（dB）
SILENCE_MIN_DURATION = 0.5  # 無音と判定する最小持続時間（秒）
SILENCE_PADDING = 0.1  # カット時の前後パディング（秒）

# テロップ設定
SUBTITLE_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SUBTITLE_FONT_SIZE = 48
SUBTITLE_COLOR = "white"
SUBTITLE_OUTLINE_COLOR = "black"
SUBTITLE_OUTLINE_WIDTH = 3
SUBTITLE_POSITION_Y = 0.85  # 画面下部85%の位置

# TTS 設定
TTS_LANGUAGE_CODE = "ja-JP"
TTS_VOICE_NAME = "ja-JP-Neural2-B"
TTS_SPEAKING_RATE = 1.0
