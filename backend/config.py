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
if os.name == "nt":  # Windows
    TMP_DIR = Path(os.getenv("TMP_DIR", BASE_DIR / "tmp"))
    CACHE_DIR = Path(os.getenv("CACHE_DIR", BASE_DIR / "cache"))
    DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
else:
    TMP_DIR = Path(os.getenv("TMP_DIR", "/app/tmp"))
    CACHE_DIR = Path(os.getenv("XDG_CACHE_HOME", "/app/cache"))
    DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))

# 一時ファイル・データ用ディレクトリを確保
TMP_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Firebase 設定
# =============================================================================
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET", "threads-auto-poster-9f85a.firebasestorage.app")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "video_jobs")

# =============================================================================
# Google Cloud 設定
# =============================================================================
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "threads-auto-poster-9f85a")

# =============================================================================
# Gemini API 設定
# =============================================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# クォータ枯渇・エラー時に順番に試す最新フォールバックモデルリスト（現行モデル優先）
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
]

# =============================================================================
# YouTube API 設定
# =============================================================================
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS", "/app/client_secrets.json")
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "/app/youtube_token.json")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_REDIRECT_URI = os.getenv("YOUTUBE_REDIRECT_URI", "https://kimidori-movie-auto-ey3qvn3ruq-an.a.run.app/api/auth/youtube/callback")

# =============================================================================
# ComfyUI / Colab Worker 設定
# =============================================================================
def _get_comfyui_url_from_env() -> str:
    # 1. 環境変数
    url = os.getenv("COMFYUI_API_URL", "")
    if url:
        return url
    # 2. プロジェクト直下の .env.local
    env_local = BASE_DIR.parent / ".env.local"
    if env_local.exists():
        try:
            with open(env_local, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("COMFYUI_API_URL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass
    return ""

COMFYUI_API_URL = _get_comfyui_url_from_env()

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
import sys
if sys.platform == "win32":
    windows_font = Path("C:/Windows/Fonts/YuGothM.ttc")
    if not windows_font.exists():
        windows_font = Path("C:/Windows/Fonts/meiryo.ttc")
    SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", str(windows_font))
else:
    SUBTITLE_FONT = os.getenv("SUBTITLE_FONT", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

SUBTITLE_FONT_SIZE = 48
SUBTITLE_COLOR = "white"
SUBTITLE_OUTLINE_COLOR = "black"
SUBTITLE_OUTLINE_WIDTH = 3
SUBTITLE_POSITION_Y = 0.85  # 画面下部85%の位置

# TTS 設定
TTS_LANGUAGE_CODE = "ja-JP"
TTS_VOICE_NAME = "ja-JP-Neural2-B"
TTS_SPEAKING_RATE = 1.0

# 高品質OSS TTS（ElevenLabs互換 / F5-TTS / Fish Speech）設定
OSS_TTS_ENDPOINT_URL = os.getenv("OSS_TTS_ENDPOINT_URL", "http://localhost:9880")
OSS_TTS_API_KEY = os.getenv("OSS_TTS_API_KEY", "")
OSS_TTS_VOICE_ID = os.getenv("OSS_TTS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
OSS_TTS_PROTOCOL = os.getenv("OSS_TTS_PROTOCOL", "elevenlabs_compatible")

# OpenBMB VoxCPM (VoxCPM2 48kHz Studio Quality / ElevenLabs Compatible) 設定
# GitHub: https://github.com/OpenBMB/VoxCPM.git
VOXCPM_ENDPOINT_URL = os.getenv("VOXCPM_ENDPOINT_URL", os.getenv("OSS_TTS_ENDPOINT_URL", "http://localhost:8808"))
VOXCPM_API_KEY = os.getenv("VOXCPM_API_KEY", os.getenv("OSS_TTS_API_KEY", ""))
VOXCPM_VOICE_ID = os.getenv("VOXCPM_VOICE_ID", "default")
VOXCPM_PROTOCOL = os.getenv("VOXCPM_PROTOCOL", "vllm_omni")  # 'vllm_omni', 'elevenlabs', 'fastapi'
VOXCPM_SAMPLE_RATE = int(os.getenv("VOXCPM_SAMPLE_RATE", "48000"))
VOXCPM_MODEL = os.getenv("VOXCPM_MODEL", "openbmb/VoxCPM2")
VOXCPM_TIMEOUT_SECONDS = int(os.getenv("VOXCPM_TIMEOUT_SECONDS", "60"))

# =============================================================================
# Stripe サブスクリプション & クレジット課金設定
# =============================================================================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# マスター管理者（単一絶対権限）
MASTER_ADMIN_EMAILS = {"oumaumauma32@gmail.com"}

# 料金プラン体系 (統一仕様)
# 1. free_trial: 無料体験枠 (簡易ショートのみ、動画編集スタジオ不可、BGM固定、YouTube直接投稿不可)
# 2. standard: 1,980円 (300 pt/月、動画編集スタジオ不可、MP4保存のみ、無料TTS)
# 3. premium: 3,980円 (1,000 pt/月、動画編集スタジオ可、高品質VoxCPM TTS開放、YouTube直接投稿開放)
# 4. master: 7,980円 (3,000 pt/月、全機能フル開放、優先キュー処理)
# 5. byog_purchased: 買い切り 79,800円 (無制限・0pt消費、自前環境セットアップガイド表示)
PLAN_PRICING = {
    "free_trial": {
        "name": "無料体験プラン",
        "price_jpy": 0,
        "monthly_credits": 30,
        "features": {
            "can_use_premium_tts": False,
            "can_direct_upload_youtube": False,
            "can_replace_bgm": False,
            "can_use_studio": False,
            "priority_queue": False,
            "is_simple_shorts_only": True
        }
    },
    "standard": {
        "name": "スタンダードプラン",
        "price_jpy": 1980,
        "monthly_credits": 300,
        "features": {
            "can_use_premium_tts": False,
            "can_direct_upload_youtube": False,
            "can_replace_bgm": False,
            "can_use_studio": False,
            "priority_queue": False
        }
    },
    "premium": {
        "name": "プレミアムプラン",
        "price_jpy": 3980,
        "monthly_credits": 1000,
        "features": {
            "can_use_premium_tts": True,
            "can_direct_upload_youtube": True,
            "can_replace_bgm": True,
            "can_use_studio": True,
            "priority_queue": False
        }
    },
    "master": {
        "name": "マスタープラン",
        "price_jpy": 7980,
        "monthly_credits": 3000,
        "features": {
            "can_use_premium_tts": True,
            "can_direct_upload_youtube": True,
            "can_replace_bgm": True,
            "can_use_studio": True,
            "priority_queue": True
        }
    },
    "byog_purchased": {
        "name": "買い切り無制限プラン",
        "price_jpy": 79800,
        "monthly_credits": 999999,
        "is_one_time": True,
        "features": {
            "can_use_premium_tts": True,
            "can_direct_upload_youtube": True,
            "can_replace_bgm": True,
            "can_use_studio": True,
            "priority_queue": True,
            "unlimited": True,
            "show_byog_setup_guide": True
        }
    }
}

# 旧プランキーからの安全な後方互換性エイリアス
PLAN_ALIASES = {
    "free": "free_trial",
    "lite": "standard",
    "pro": "premium",
}

def resolve_plan_key(raw_plan: str) -> str:
    """旧プラン名や変種名を新体系キーに正規化"""
    p = (raw_plan or "").strip().lower()
    if p in PLAN_PRICING:
        return p
    return PLAN_ALIASES.get(p, "free_trial")

# 追加クレジットチャージ体系 (買い切り)
CREDIT_PACKS = {
    "pack_small": {"name": "追加クレジット 200", "credits": 200, "price_jpy": 980},
    "pack_medium": {"name": "追加クレジット 600", "credits": 600, "price_jpy": 2480},
    "pack_large": {"name": "追加クレジット 1500", "credits": 1500, "price_jpy": 4980}
}

# クレジット消費ルール
CREDIT_COST_SHORT_PER_CUT = int(os.getenv("CREDIT_COST_SHORT_PER_CUT", "5"))   # ショート動画: 1カットにつき5クレジット
CREDIT_COST_LONG_PER_SCENE = int(os.getenv("CREDIT_COST_LONG_PER_SCENE", "12")) # 長尺動画: 1シーンにつき12クレジット

# =============================================================================
# サロン連携 & Cloud Run セキュリティ設定
# =============================================================================
SALON_SHARED_SECRET = os.getenv("SALON_SHARED_SECRET", "kimidori_salon_secure_token_2026")
REQUIRE_AUTH_API = os.getenv("REQUIRE_AUTH_API", "false").lower() in ("true", "1")


