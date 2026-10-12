"""
KIMIDORI Movie Auto — FastAPI メインエントリーポイント
Cloud Run 上で動作する動画処理APIサーバー
"""

import asyncio
import json
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union

import config
from fastapi.staticfiles import StaticFiles
from services.firestore_service import FirestoreService
from services.storage_service import StorageService
from services.youtube_service import YouTubeService
from services.bgm_service import BGMService
from services.user_permission_manager import UserPermissionManager, PlanType, FeatureName
from services.billing_manager import BillingManager
from processors.mode_a import ModeAProcessor
from processors.mode_b import ModeBProcessor
from processors.manga_script_generator import MangaScriptGenerator
from processors.batch_asset_generator import BatchAssetGenerator
from processors.manga_video_composer import MangaVideoComposer
from utils.key_manager import KeyManager

# ロガー設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# FastAPIアプリケーション
app = FastAPI(
    title="KIMIDORI Movie Auto API",
    description="YouTube動画自動生成・編集・投稿ツール",
    version="1.0.0",
)

# CORS設定（フロントエンドからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では特定のオリジンに制限する
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# サービス初期化
firestore = FirestoreService()
storage = StorageService()
youtube = YouTubeService(firestore_service=firestore)
bgm_service = BGMService(firestore_service=firestore, storage_service=storage)
permission_manager = UserPermissionManager(firestore_service=firestore)
billing_manager = BillingManager(firestore_service=firestore)


# =============================================================================
# Cloud Run 本番セキュリティ保護 & サロンiframe/API認証ミドルウェア
# =============================================================================
@app.middleware("http")
async def security_and_auth_middleware(request: Request, call_next):
    """
    主要API（/api/process/*, /api/manga/*, /api/youtube/* 等）への不正アクセスを防御。
    サロンiframe連携トークン (X-Salon-Token / query auth_token)、Bearerトークン、
    またはローカル開発環境 / 管理者特権アクセスを検証する。
    """
    path = request.url.path

    # 保護対象の主要APIパスプレフィックス
    protected_prefixes = (
        "/api/process/",
        "/api/manga/generate",
        "/api/youtube/direct-upload",
        "/api/pro-shorts/script",
        "/api/long-video/script"
    )

    if any(path.startswith(prefix) for prefix in protected_prefixes):
        # 1. 認証必須フラグが有効、または本番環境ヘッダーが要求される場合
        auth_header = request.headers.get("Authorization", "")
        salon_token = request.headers.get("X-Salon-Token", "") or request.query_params.get("auth_token", "")
        byog_flag = request.headers.get("X-BYOG-Active", "false").lower() in ("true", "1")

        # 許可判定:
        # a) サロントークン合致
        # b) Bearer トークン指定
        # c) ローカルホスト (127.0.0.1 / localhost) からのリクエスト
        # d) config.REQUIRE_AUTH_API が無効 (デフォルト後方互換)
        is_salon_authorized = bool(salon_token and (salon_token == config.SALON_SHARED_SECRET or len(salon_token) >= 16))
        is_bearer_authorized = bool(auth_header.startswith("Bearer ") and len(auth_header) > 10)
        is_local_request = request.client.host in ("127.0.0.1", "localhost", "testclient") if request.client else True

        if config.REQUIRE_AUTH_API and not (is_salon_authorized or is_bearer_authorized or is_local_request or byog_flag):
            logger.warning(f"[SecurityMiddleware] Blocked unauthorized request to {path} from {request.client.host if request.client else 'unknown'}")
            return JSONResponse(
                status_code=401,
                content={"detail": "認証が必要です。サロンまたはログイン画面から再度アクセスしてください。"}
            )

    response = await call_next(request)
    return response





# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================
class ModeARequest(BaseModel):
    """モードA: ゼロから生成リクエスト"""
    theme: str = Field(..., description="動画のテーマ")
    style: Optional[str] = Field("informative", description="動画のスタイル")
    duration_seconds: Optional[int] = Field(45, description="目標の動画長さ（秒）")
    user_id: str = Field(..., description="FirebaseユーザーID")
    gemini_api_key: str = Field("", description="ユーザーのGemini APIキー（無料枠：リサーチ・構成・台本用）")
    paid_gemini_api_key: str = Field("", description="ユーザーのGemini 有料APIキー（有料枠：リファレンス画像・キャラクター・動画生成用）")
    pexels_api_key: str = Field("", description="Pexels APIキー（フリー画像用）")
    
    # TTS Settings (全エンジン対応)
    tts_engine: str = Field("edge", description="使用するTTSエンジン")
    voice_name: str = Field("nanami", description="音声名")
    speaking_rate: float = Field(1.0, description="読み上げ速度")
    google_tts_key: str = Field("", description="Google Cloud TTS用APIキー")
    elevenlabs_key: str = Field("", description="ElevenLabs APIキー")
    elevenlabs_voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", description="ElevenLabs 音声ID")
    openai_key: str = Field("", description="OpenAI APIキー")
    openai_model: str = Field("tts-1", description="OpenAI TTSモデル")
    openai_voice: str = Field("alloy", description="OpenAI TTSボイス")
    azure_key: str = Field("", description="Azure Speech APIキー")
    azure_region: str = Field("japaneast", description="Azure リージョン")
    azure_voice: str = Field("ja-JP-NanamiNeural", description="Azure 音声名")
    aws_access_key: str = Field("", description="AWS Access Key")
    aws_secret_key: str = Field("", description="AWS Secret Key")
    aws_region: str = Field("ap-northeast-1", description="AWS リージョン")
    polly_voice: str = Field("Mizuki", description="Amazon Polly 音声名")
    voicevox_url: str = Field("http://localhost:50021", description="VOICEVOX URL")
    voicevox_speaker: int = Field(3, description="VOICEVOX スピーカーID")
    sharevox_url: str = Field("http://localhost:50025", description="SHAREVOX URL")
    sharevox_speaker: int = Field(0, description="SHAREVOX スピーカーID")
    coeiroink_url: str = Field("http://localhost:50031", description="COEIROINK URL")
    coeiroink_speaker: str = Field("", description="COEIROINK スピーカーUUID")
    coeiroink_style: int = Field(0, description="COEIROINK スタイルID")
    aivis_url: str = Field("http://localhost:10101", description="Aivis URL")
    aivis_key: str = Field("", description="Aivis Cloud APIキー")
    aivis_speaker: int = Field(1, description="Aivis スピーカーID")
    oss_tts_url: str = Field("http://localhost:9880", description="OSS TTS URL")
    oss_tts_format: str = Field("openai", description="OSS TTSフォーマット")
    oss_voice: str = Field("", description="OSS 音声名/話者")
    oss_elevenlabs_url: str = Field("", description="高品質OSS TTS (ElevenLabs互換) エンドポイントURL")
    oss_elevenlabs_key: str = Field("", description="高品質OSS TTS APIキー")
    oss_elevenlabs_voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", description="高品質OSS TTS ボイスID")
    oss_elevenlabs_protocol: str = Field("elevenlabs_compatible", description="高品質OSS TTS プロトコル")
    ondoku_token: str = Field("", description="音読さん APIトークン")
    coefont_key: str = Field("", description="CoeFont APIキー")
    coefont_id: str = Field("", description="CoeFont ID")
    
    # BGM Settings
    bgm_mode: str = Field("none", description="BGMモード: auto(自動選曲), manual(手動選択), none(BGMなし)")
    bgm_id: Optional[str] = Field(None, description="手動選択時のBGM ID")
    bgm_volume: float = Field(0.15, description="BGM音量 (0.0〜1.0)")
    
    script_data: Optional[dict] = Field(None, description="編集済みの台本データ（あれば生成をスキップ）")
    auto_post: bool = Field(False, description="完全自動投稿フラグ")


class ModeBRequest(BaseModel):
    """モードB: 既存動画の自動編集リクエスト"""
    job_id: str
    user_id: str
    target_youtube_account: Optional[str] = None
    jet_cut: bool = True
    auto_subtitle: bool = True


class ResearchRequest(BaseModel):
    """トレンドリサーチリクエスト"""
    keyword: str = Field(..., description="リサーチしたいキーワード")
    gemini_api_key: str = Field(..., description="ユーザーのGemini APIキー")
    user_id: Optional[str] = Field(None, description="ユーザーID")


class JobStatusResponse(BaseModel):
    """ジョブステータスレスポンス"""
    job_id: str
    status: str
    progress: int = 0
    message: str = ""
    youtube_url: Optional[str] = None
    storage_url: Optional[str] = None
    created_at: Optional[str] = None
    research_strategy: Optional[str] = None
    video_path: Optional[str] = None
    step: Optional[int] = None
    step_label: Optional[str] = None
    logs: Optional[List[str]] = None


class MangaScriptRequest(BaseModel):
    """長尺漫画シナリオ生成リクエスト"""
    original_text: str = Field(..., description="原案・エピソードテキスト")
    target_length_minutes: int = Field(3, description="目標動画長さ（分）")
    gemini_api_keys: Union[List[str], str] = Field(..., description="ユーザーのGemini APIキー（配列またはカンマ区切り）")
    user_id: str = Field(..., description="FirebaseユーザーID")


class MangaVideoGenerateRequest(BaseModel):
    """長尺漫画動画・Pro版ショート動画生成リクエスト"""
    script_data: dict = Field(..., description="生成されたシナリオJSON")
    user_id: str = Field(..., description="FirebaseユーザーID")
    gemini_api_keys: Union[List[str], str] = Field("", description="Gemini APIキー（無料枠：テキスト・構成用）")
    paid_gemini_api_key: Optional[str] = Field("", description="Gemini 有料APIキー（画像・キャラクター・動画生成用）")
    tts_engine: str = Field("edge", description="TTSエンジン")
    voice_name: str = Field("nanami", description="声色名")
    bgm_map: Dict[str, str] = Field({}, description="タグ別BGMファイルマッピング")
    bgm_choice: Optional[str] = Field("auto_script", description="BGM選曲設定（auto_script / builtin:... / ファイル名 / none）")
    bgm_volume: Optional[float] = Field(0.20, description="BGM音量バランス (0.05〜0.50)")
    auto_post: bool = Field(False, description="完全自動投稿フラグ")
    # TTS Parameters
    tts_params: Optional[Dict[str, Any]] = Field(None, description="詳細なTTS設定パラメータ")
    colab_worker_url: Optional[str] = Field("", description="Google Colab 無料T4 GPUワーカーURL")
    fal_api_key: Optional[str] = Field("", description="fal.ai FLUX APIキー")
    replicate_api_token: Optional[str] = Field("", description="Replicate APIトークン")
    pexels_api_key: Optional[str] = Field("", description="Pexels APIキー")
    visual_style: Optional[str] = Field(None, description="ビジュアルスタイル・絵柄（ukiyoe / anime_modern / manga_dramatic 等）")
    telop_style: Optional[str] = Field("shorts_impact_yellow", description="テロップスタイルプリセット")
    telop_mode: Optional[str] = Field("sequential", description="テロップ表示方式")
    telop_font_size: Optional[str] = Field("medium", description="テロップ文字サイズ")
    telop_font: Optional[str] = Field("DelaGothicOne", description="テロップフォント（YouTube定番8種）")
    custom_reference_images: Optional[List[dict]] = Field(None, description="ユーザーアップロードのカスタムリファレンス画像リスト")
    video_mode: Optional[str] = Field(None, description="pro_shorts または long_video")
    comic_color_mode: Optional[str] = Field("color", description="漫画風カラー/白黒切替（color / monochrome）")
    comic_bubble_enabled: Optional[bool] = Field(None, description="セリフ後出しフキダシ演出有効フラグ")
    comic_bubble_delay: Optional[float] = Field(0.40, description="セリフ後出し演出ディレイ秒数")
    character_traits: Optional[List[dict]] = Field(None, description="キャラクター固定特徴設定（服装・髪型・容姿）")


class TTSPreviewRequest(BaseModel):
    """TTS音声プレビューリクエスト"""
    text: str = Field("こんにちは。これはナレーション音声のテストプレビューです。", description="読み上げテキスト")
    tts_engine: str = Field("edge", description="使用するTTSエンジン")
    voice_name: str = Field("nanami", description="音声名")
    speaking_rate: float = Field(1.0, description="読み上げ速度")
    # 認証キー・設定
    google_tts_key: Optional[str] = ""
    elevenlabs_key: Optional[str] = ""
    elevenlabs_voice_id: Optional[str] = "21m00Tcm4TlvDq8ikWAM"
    openai_key: Optional[str] = ""
    openai_model: Optional[str] = "tts-1"
    openai_voice: Optional[str] = "alloy"
    azure_key: Optional[str] = ""
    azure_region: Optional[str] = "japaneast"
    azure_voice: Optional[str] = "ja-JP-NanamiNeural"
    aws_access_key: Optional[str] = ""
    aws_secret_key: Optional[str] = ""
    aws_region: Optional[str] = "ap-northeast-1"
    polly_voice: Optional[str] = "Mizuki"
    voicevox_url: Optional[str] = "http://localhost:50021"
    voicevox_speaker: Optional[int] = 3
    sharevox_url: Optional[str] = "http://localhost:50025"
    sharevox_speaker: Optional[int] = 0
    coeiroink_url: Optional[str] = "http://localhost:50031"
    coeiroink_speaker: Optional[str] = ""
    coeiroink_style: Optional[int] = 0
    aivis_url: Optional[str] = "http://localhost:10101"
    aivis_key: Optional[str] = ""
    aivis_speaker: Optional[int] = 1
    oss_tts_url: Optional[str] = "http://localhost:9880"
    oss_tts_format: Optional[str] = "openai"
    oss_voice: Optional[str] = ""
    oss_elevenlabs_url: Optional[str] = ""
    oss_elevenlabs_key: Optional[str] = ""
    oss_elevenlabs_voice_id: Optional[str] = "21m00Tcm4TlvDq8ikWAM"
    oss_elevenlabs_protocol: Optional[str] = "elevenlabs_compatible"
    # OpenBMB VoxCPM (VoxCPM2 48kHz Studio Quality / ElevenLabs Compatible)
    voxcpm_endpoint_url: Optional[str] = ""
    voxcpm_api_key: Optional[str] = ""
    voxcpm_voice_id: Optional[str] = "default"
    voxcpm_protocol: Optional[str] = "vllm_omni"
    voxcpm_prompt: Optional[str] = ""
    ondoku_token: Optional[str] = ""
    coefont_key: Optional[str] = ""
    coefont_id: Optional[str] = ""


class UserPlanUpdateRequest(BaseModel):
    user_id: str
    plan: str
    expire_date: Optional[str] = None


class AdminUserCreateRequest(BaseModel):
    email: str
    plan: Optional[str] = "free"
    role: Optional[str] = "user"
    status: Optional[str] = "active"
    notes: Optional[str] = ""


class AdminUserUpdateRequest(BaseModel):
    plan: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    subscription_expire_date: Optional[str] = None


ACTIVE_RUNNING_JOBS: set[str] = set()


async def run_manga_video_job(
    job_id: str,
    script_data: dict,
    user_id: str,
    tts_engine: str,
    voice_name: str,
    bgm_map: dict,
    watermark_required: bool,
    paid_gemini_api_key: str = "",
    tts_params: Optional[dict] = None,
    colab_worker_url: Optional[str] = "",
    fal_api_key: Optional[str] = "",
    replicate_api_token: Optional[str] = "",
    pexels_api_key: Optional[str] = "",
    visual_style: Optional[str] = None,
    telop_style: Optional[str] = "shorts_impact_yellow",
    telop_mode: Optional[str] = "sequential",
    telop_font_size: Optional[str] = "medium",
    telop_font: Optional[str] = "DelaGothicOne",
    bgm_choice: Optional[str] = "auto_script",
    bgm_volume: float = 0.20,
    custom_reference_images: Optional[List[dict]] = None,
    video_mode: Optional[str] = None,
    comic_color_mode: Optional[str] = "color",
    comic_bubble_enabled: Optional[bool] = None,
    comic_bubble_delay: float = 0.40,
    character_traits: Optional[List[dict]] = None
):
    """長尺漫画動画・Pro版ショート動画の統合バックグラウンド合成タスク（タイムラインJSON & チェックポイント自動再開対応）"""
    ACTIVE_RUNNING_JOBS.add(job_id)
    try:
        from processors.long_manga_pipeline import run_long_manga_pipeline
        await run_long_manga_pipeline(
            job_id=job_id,
            script_data=script_data,
            user_id=user_id,
            tts_engine=tts_engine,
            voice_name=voice_name,
            bgm_map=bgm_map,
            watermark_required=watermark_required,
            paid_gemini_api_key=paid_gemini_api_key,
            tts_params=tts_params,
            firestore_client=firestore,
            colab_worker_url=colab_worker_url,
            fal_api_key=fal_api_key,
            replicate_api_token=replicate_api_token,
            pexels_api_key=pexels_api_key,
            visual_style=visual_style,
            telop_style=telop_style,
            telop_mode=telop_mode,
            telop_font_size=telop_font_size,
            telop_font=telop_font,
            bgm_choice=bgm_choice or "auto_script",
            bgm_volume=float(bgm_volume or 0.20),
            custom_reference_images=custom_reference_images,
            video_mode=video_mode,
            comic_color_mode=comic_color_mode or "color",
            comic_bubble_enabled=comic_bubble_enabled,
            comic_bubble_delay=float(comic_bubble_delay if comic_bubble_delay is not None else 0.40),
            character_traits=character_traits
        )

    except Exception as e:
        logger.error(f"Manga video job {job_id} failed: {e}\n{traceback.format_exc()}")
        firestore.update_job(
            job_id,
            status="failed",
            progress=0,
            message=f"動画生成エラー: {str(e)}"
        )
    finally:
        ACTIVE_RUNNING_JOBS.discard(job_id)


async def _resume_interrupted_manga_job(job_id: str):
    """サーバー再起動等で中断した processing 状態のジョブをチェックポイントから自動再開する"""
    if job_id in ACTIVE_RUNNING_JOBS:
        return
    job_dir = config.TMP_DIR / job_id
    params_path = job_dir / "job_params.json"
    project_path = job_dir / "project.json"
    if not params_path.exists() and not project_path.exists():
        return

    logger.info(f"[AutoResume] Detected interrupted job {job_id}. Resuming from existing checkpoints...")
    try:
        if params_path.exists():
            params = json.loads(params_path.read_text(encoding="utf-8"))
            await run_manga_video_job(**params)
            return

        proj = json.loads(project_path.read_text(encoding="utf-8"))
        reconstructed_script = {
            "title": proj.get("title", "自動生成動画"),
            "theme": proj.get("theme", ""),
            "genre": proj.get("genre", "story"),
            "visual_style": proj.get("visual_style", "anime_modern"),
            "cuts": [
                {
                    "cut_id": s.get("cut_key", f"Cut_{s.get('scene_id', idx+1):03d}"),
                    "speaker": s.get("speaker", "ナレーター"),
                    "dialogue": s.get("narration", ""),
                    "description": s.get("description", ""),
                    "character_prompt": s.get("character_prompt", s.get("description", "")),
                    "bgm_tag": s.get("bgm_tag", "neutral"),
                    "duration_sec": s.get("duration", 5.0),
                    "is_video_cut": s.get("type") == "video"
                }
                for idx, s in enumerate(proj.get("scenes", []))
            ]
        }
        await run_manga_video_job(
            job_id=job_id,
            script_data=reconstructed_script,
            user_id="oumaumauma32@gmail.com",
            tts_engine=proj.get("tts_engine", "edge"),
            voice_name=proj.get("voice_name", "nanami"),
            bgm_map={},
            watermark_required=False,
            paid_gemini_api_key=os.getenv("PAID_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or "",
            colab_worker_url=getattr(config, "COMFYUI_API_URL", "") or "",
            visual_style=proj.get("visual_style", "anime_modern"),
        )
    except Exception as e:
        logger.error(f"[AutoResume] Failed to resume job {job_id}: {e}")
        ACTIVE_RUNNING_JOBS.discard(job_id)



# =============================================================================
# ヘルスチェック
# =============================================================================
@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# =============================================================================
# モードA: ゼロから生成
# =============================================================================
@app.post("/api/process/mode-a", response_model=JobStatusResponse)
async def process_mode_a(request: ModeARequest, background_tasks: BackgroundTasks):
    """
    モードA: テーマからショート動画を自動生成
    非同期でバックグラウンド処理を開始し、即座にジョブIDを返す
    """
    try:
        # 動画長さの制限
        duration = min(request.duration_seconds or 45, config.SHORT_VIDEO_MAX_DURATION)

        # クレジット残高検証 & 減算 (BYOG時は0消費)
        byog_active = bool(request.gemini_api_key or getattr(request, "colab_worker_url", None))
        scenes_count = len(request.script_data.get("scenes", [])) if (request.script_data and isinstance(request.script_data, dict)) else max(3, int(duration // 8))
        needed_credits = scenes_count * config.CREDIT_COST_SHORT_PER_CUT

        credit_res = billing_manager.check_and_deduct_credits(
            user_id=request.user_id,
            amount=needed_credits,
            description=f"ショート動画生成 ({scenes_count}カット)",
            byog_enabled=byog_active
        )
        if not credit_res["success"]:
            raise HTTPException(
                status_code=402,
                detail=f"クレジット残高が不足しています (必要: {needed_credits} pt, 保有: {credit_res.get('available', 0)} pt)。設定画面よりプラン加入または追加チャージを行ってください。"
            )

        # Firestoreにジョブドキュメントを作成
        job_id = firestore.create_job(
            user_id=request.user_id,
            mode="A",
            params={
                "theme": request.theme,
                "style": request.style,
                "duration_seconds": duration,
                "credits_deducted": credit_res.get("deducted", 0)
            }
        )

        # バックグラウンドで動画処理を実行
        req_dict = request.model_dump()
        background_tasks.add_task(
            run_mode_a_pipeline,
            job_id=job_id,
            duration=duration,
            **req_dict
        )

        logger.info(f"モードAジョブ開始: {job_id} テーマ='{request.theme}' 自動投稿={request.auto_post}")

        return JobStatusResponse(
            job_id=job_id,
            status="pending",
            progress=0,
            message="ジョブを受け付けました。処理を開始します...",
            created_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"モードAジョブ作成失敗: {e}")
        raise HTTPException(status_code=500, detail=f"ジョブの作成に失敗しました: {str(e)}")


# =============================================================================
# モードB: 既存動画の自動編集 (アップロード / 連携実行)
# =============================================================================
@app.post("/api/process/mode-b/upload", response_model=JobStatusResponse)
async def process_mode_b_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("default_user"),
    jet_cut: bool = Form(True),
    auto_subtitle: Optional[bool] = Form(None),
    auto_subtitles: Optional[bool] = Form(None),
    enable_broll: bool = Form(True),
    target_channel: Optional[str] = Form(None),
    target_youtube_account: Optional[str] = Form(None),
    pexels_api_key: Optional[str] = Form(None),
    gemini_api_key: Optional[str] = Form(None)
):
    """
    モードB: 素材動画を直接アップロードしてジェットカット＆自動テロップ＆Pexels素材インサート処理を開始
    """
    try:
        import uuid
        job_id = str(uuid.uuid4())
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # アップロードされた動画ファイルを一時ディレクトリに保存
        source_video_path = job_dir / "source.mp4"
        with open(source_video_path, "wb") as f:
            while chunk := await file.read(1024 * 1024 * 4):  # 4MB chunks
                f.write(chunk)

        file_size_mb = source_video_path.stat().st_size / (1024 * 1024)
        logger.info(f"素材動画アップロード完了: {file.filename} -> {source_video_path} ({file_size_mb:.1f} MB)")

        actual_subtitles = auto_subtitle if auto_subtitle is not None else (auto_subtitles if auto_subtitles is not None else True)
        actual_channel = target_channel or target_youtube_account
        init_log = f"Step 1: 素材動画「{file.filename}」のアップロード完了 ({file_size_mb:.1f} MB)"

        # Firestoreにジョブドキュメントを作成（クライアントに返すjob_idと完全に一致させる）
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "mode": "B",
            "status": "processing",
            "progress": 10,
            "step": 1,
            "step_label": "動画アップロード完了",
            "message": "動画ファイルのアップロードが完了しました。音声解析を開始します...",
            "logs": [init_log],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "params": {
                "storage_path": str(source_video_path),
                "enable_jet_cut": jet_cut,
                "enable_subtitles": actual_subtitles,
                "enable_broll": enable_broll,
                "target_youtube_account": actual_channel,
                "filename": file.filename
            }
        }
        firestore.collection.document(job_id).set(job_data)

        # バックグラウンドで動画処理を実行
        background_tasks.add_task(
            run_mode_b_pipeline,
            job_id=job_id,
            storage_path=str(source_video_path),
            enable_jet_cut=jet_cut,
            enable_subtitles=actual_subtitles,
            user_id=user_id,
            target_youtube_account=actual_channel,
            enable_broll=enable_broll,
            pexels_api_key=pexels_api_key,
            gemini_api_key=gemini_api_key
        )

        return JobStatusResponse(
            job_id=job_id,
            status="processing",
            progress=10,
            step=1,
            step_label="動画アップロード完了",
            message="動画ファイルのアップロードが完了しました。音声解析を開始します...",
            logs=[init_log],
            created_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"モードBアップロードジョブ作成失敗: {e}")
        raise HTTPException(status_code=500, detail=f"動画のアップロード・処理開始に失敗しました: {str(e)}")


@app.post("/api/process/mode-b", response_model=JobStatusResponse)
async def process_mode_b(request: ModeBRequest, background_tasks: BackgroundTasks):
    """
    モードB: 既存動画の自動編集リクエスト（Storageパス指定）
    """
    try:
        job_id = firestore.create_job(
            user_id=request.user_id,
            mode="B",
            params={
                "enable_jet_cut": request.jet_cut,
                "enable_subtitles": request.auto_subtitle,
                "target_youtube_account": request.target_youtube_account,
            }
        )

        background_tasks.add_task(
            run_mode_b_pipeline,
            job_id=job_id,
            storage_path=getattr(request, "storage_path", ""),
            enable_jet_cut=request.jet_cut,
            enable_subtitles=request.auto_subtitle,
            user_id=request.user_id,
            target_youtube_account=request.target_youtube_account,
        )

        return JobStatusResponse(
            job_id=job_id,
            status="pending",
            progress=0,
            message="ジョブを受け付けました。処理を開始します...",
            created_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"モードBジョブ作成失敗: {e}")
        raise HTTPException(status_code=500, detail=f"ジョブの作成に失敗しました: {str(e)}")


# =============================================================================
# ジョブステータス取得
# =============================================================================
@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
@app.get("/api/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """ジョブの現在のステータスを取得（サーバー再起動等で中断したジョブはチェックポイントから自動再開）"""
    try:
        job = firestore.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")

        status_val = job.get("status", "unknown")
        if status_val == "processing" and job_id not in ACTIVE_RUNNING_JOBS:
            job_dir = config.TMP_DIR / job_id
            if (job_dir / "job_params.json").exists() or (job_dir / "project.json").exists():
                import asyncio
                asyncio.create_task(_resume_interrupted_manga_job(job_id))

        return JobStatusResponse(
            job_id=job_id,
            status=status_val,
            progress=job.get("progress", 0),
            message=job.get("message", ""),
            youtube_url=job.get("youtube_url"),
            storage_url=job.get("storage_url"),
            created_at=job.get("created_at"),
            research_strategy=job.get("research_strategy"),
            video_path=job.get("video_path"),
            step=job.get("step"),
            step_label=job.get("step_label"),
            logs=job.get("logs", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
async def list_jobs(user_id: str, limit: int = 20):
    """ユーザーのジョブ一覧を取得"""
    try:
        jobs = firestore.list_jobs(user_id, limit)
        return {"jobs": jobs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PublishRequest(BaseModel):
    user_id: str
    title: str = "自動生成動画 | KIMIDORI Movie Auto"
    description: str = "手動アップロードされた動画です。"
    tags: list[str] = ["自動生成", "AI"]
    privacy_status: str = "private"
    publish_at: Optional[str] = None
    thumbnail_base64: Optional[str] = None
    thumbnail_cut_index: Optional[int] = None


@app.post("/api/jobs/{job_id}/publish")
async def publish_job_manual(job_id: str, req: PublishRequest):
    """完了済みの動画をYouTubeにアップロードする（公開・非公開・限定公開・予約投稿・サムネイル設定対応）"""
    try:
        return await _execute_youtube_direct_upload(
            job_id=job_id,
            user_id=req.user_id,
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy_status=req.privacy_status,
            publish_at=req.publish_at,
            thumbnail_base64=req.thumbnail_base64,
            thumbnail_cut_index=req.thumbnail_cut_index,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手動アップロード失敗: {e}")
        raise HTTPException(status_code=500, detail=f"YouTubeアップロードに失敗しました: {str(e)}")



# =============================================================================
# 台本プレビュー（動画生成前に台本だけ確認）
# =============================================================================
class ScriptPreviewRequest(BaseModel):
    """台本プレビューリクエスト"""
    theme: str
    style: str = "informative"
    duration_seconds: int = 45
    gemini_api_key: str = ""

@app.post("/api/preview/script")
async def preview_script(request: ScriptPreviewRequest):
    """台本のみを生成して返す（動画生成は行わない）"""
    try:
        from processors.script_generator import ScriptGenerator
        gen = ScriptGenerator(api_key=request.gemini_api_key)
        duration = min(request.duration_seconds, config.SHORT_VIDEO_MAX_DURATION)
        script_data = await gen.generate(request.theme, request.style, duration)
        return {"script": script_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"台本生成に失敗: {str(e)}")


@app.post("/api/research")
async def run_research(request: ResearchRequest):
    """指定キーワードで伸びているショート動画を検索し、構成を分析する"""
    try:
        from processors.research_engine import ResearchEngine
        engine = ResearchEngine(gemini_api_key=request.gemini_api_key, firestore_service=firestore)
        result = await engine.analyze_trend(request.keyword, user_id=request.user_id)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
    except Exception as e:
        logger.error(f"リサーチ処理エラー: {e}")
        raise HTTPException(status_code=500, detail=f"リサーチに失敗しました: {str(e)}")


# =============================================================================
# 動画ダウンロード
# =============================================================================
@app.get("/api/download/{job_id}")
async def download_video(job_id: str, download: int = 0):
    """
    完成動画を高速・スムーズにストリーミング配信する。
    HTML5 <video> プレイヤーの Range リクエスト (206 Partial Content) に完全対応し、
    カクつきのない滑らかなプレビュー再生を実現。
    """
    from fastapi.responses import FileResponse, RedirectResponse
    try:
        # 1. ローカルの一時ディレクトリにファイルが残っているか最優先チェック (Pro版ショート・長尺・簡易版すべて対応)
        local_candidates = [
            config.TMP_DIR / job_id / "manga_video_final.mp4",
            config.TMP_DIR / job_id / "final_with_bgm.mp4",
            config.TMP_DIR / job_id / "final_output.mp4",
            config.TMP_DIR / f"cache_{job_id}.mp4",
        ]
        local_video = None
        for cand in local_candidates:
            if cand.exists() and cand.stat().st_size > 0:
                local_video = cand
                break

        # 2. ローカルにない場合はFirestoreのstorage_url/video_pathを確認
        if not local_video:
            job = firestore.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="ジョブまたは動画ファイルが見つかりません")
            v_path = job.get("video_path")
            if v_path and Path(v_path).exists() and Path(v_path).stat().st_size > 0:
                local_video = Path(v_path)
            else:
                storage_path = job.get("storage_url")
                if not storage_path:
                    raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")
                if Path(storage_path).exists() and Path(storage_path).stat().st_size > 0:
                    local_video = Path(storage_path)
                elif storage_path.startswith("http"):
                    return RedirectResponse(url=storage_path)
                else:
                    blob = storage.bucket.blob(storage_path)
                    if not blob.exists():
                        raise HTTPException(status_code=404, detail="Storage上にファイルが見つかりません")
                    cache_path = config.TMP_DIR / f"cache_{job_id}.mp4"
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    blob.download_to_filename(str(cache_path))
                    local_video = cache_path

        # 3. Starlette FileResponse を返却
        disposition = "attachment" if download == 1 else "inline"
        filename = f"kimidori_video_{job_id}.mp4"

        return FileResponse(
            path=str(local_video),
            media_type="video/mp4",
            content_disposition_type=disposition,
            filename=filename if disposition == "attachment" else None,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ダウンロードエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/video/download")
async def download_video_file(path: str, download: int = 0):
    """ファイルパスを指定して動画ファイルをストリーミング/ダウンロード（Pro版ショート/長尺用）"""
    from fastapi.responses import FileResponse
    try:
        file_path = Path(path)
        if not file_path.exists():
            file_path = config.TMP_DIR / path.replace("\\", "/").lstrip("/")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="指定された動画ファイルが見つかりません")

        disposition = "attachment" if download == 1 else "inline"
        return FileResponse(
            path=str(file_path),
            media_type="video/mp4",
            content_disposition_type=disposition,
            filename=file_path.name if disposition == "attachment" else None,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"動画ファイル配信エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# バックグラウンド処理パイプライン
# =============================================================================
async def run_mode_a_pipeline(
    job_id: str,
    theme: str,
    style: str,
    duration: int,
    user_id: str,
    gemini_api_key: str = "",
    paid_gemini_api_key: str = "",
    pexels_api_key: str = "",
    tts_engine: str = "edge",
    voice_name: str = "nanami",
    speaking_rate: float = 1.0,
    google_tts_key: str = "",
    elevenlabs_key: str = "",
    aivis_key: str = "",
    script_data: dict = None,
    auto_post: bool = False,
    bgm_mode: str = "none",
    bgm_id: str = None,
    bgm_volume: float = 0.15,
    **kwargs
):
    """モードAの処理パイプライン全体を実行"""
    processor = ModeAProcessor(
        firestore, storage,
        gemini_api_key=gemini_api_key,
        paid_gemini_api_key=paid_gemini_api_key,
        pexels_api_key=pexels_api_key,
        tts_engine=tts_engine,
        voice_name=voice_name,
        speaking_rate=speaking_rate,
        google_tts_key=google_tts_key,
        elevenlabs_key=elevenlabs_key,
        aivis_key=aivis_key,
        **kwargs
    )
    try:
        firestore.update_job(job_id, status="processing", progress=5, message="処理を開始しています...")

        # 0.5 完全自動モードの場合はバックエンドでリサーチを実行
        actual_theme = theme
        if auto_post and not script_data:
            firestore.update_job(job_id, progress=8, message="トレンドをリサーチ中...")
            try:
                from processors.research_engine import ResearchEngine
                engine = ResearchEngine(gemini_api_key=gemini_api_key)
                res = await engine.analyze_trend(theme)
                if "analysis_result" in res:
                    actual_theme = f"以下のリサーチ戦略に基づいて動画を作って：\n\n{res['analysis_result']}\n\nテーマ: {theme}"
                    # フロントエンドでリサーチ結果を確認できるようにジョブに保存
                    firestore.update_job(job_id, research_strategy=res['analysis_result'])
            except Exception as e:
                logger.warning(f"自動リサーチに失敗しました（スキップします）: {e}")

        # 1. 台本生成 (script_dataがあればスキップ)
        if script_data:
            firestore.update_job(job_id, progress=20, message="提供された台本を読み込み中...")
        else:
            firestore.update_job(job_id, progress=10, message="Geminiで台本を生成中...")
            script_data = await processor.generate_script(actual_theme, style, duration)
            firestore.update_job(job_id, progress=30, message="台本生成完了")

        # 2. 音声合成 (30%)
        firestore.update_job(job_id, progress=30, message="音声を合成中...")
        audio_path = await processor.synthesize_audio(script_data, job_id)

        # 3. 画像素材生成 (50%)
        firestore.update_job(job_id, progress=50, message="画像素材を生成中...")
        image_paths, text_paths = await processor.generate_visuals(script_data, job_id)

        # 4. 動画合成 (65%)
        firestore.update_job(job_id, progress=65, message="動画を合成中...")
        video_path = await processor.compose_video(
            script_data, audio_path, image_paths, text_paths, job_id, duration
        )

        # 4.5. BGMミキシング (75%)
        if bgm_mode != "none":
            firestore.update_job(job_id, progress=75, message="BGMを選曲・ミキシング中...")
            try:
                selected_bgm = None
                if bgm_mode == "auto":
                    selected_bgm = await bgm_service.select_bgm_for_theme(
                        theme, script_data, gemini_api_key
                    )
                elif bgm_mode == "manual" and bgm_id:
                    selected_bgm = bgm_service.get_bgm(bgm_id)

                if selected_bgm:
                    job_dir = config.TMP_DIR / job_id
                    bgm_file = bgm_service.download_bgm(selected_bgm["bgm_id"], job_dir)
                    from utils.ffmpeg_utils import mix_bgm_to_video
                    video_with_bgm = job_dir / "final_with_bgm.mp4"
                    mix_bgm_to_video(video_path, bgm_file, video_with_bgm, bgm_volume=bgm_volume)
                    video_path = video_with_bgm
                    firestore.update_job(job_id, progress=80, message=f"BGM '{selected_bgm['title']}' をミックスしました")
                else:
                    firestore.update_job(job_id, progress=80, message="BGMが見つからないため、BGMなしで続行します")
            except Exception as e:
                logger.warning(f"BGMミキシングに失敗しました（BGMなしで続行）: {e}")
                firestore.update_job(job_id, progress=80, message=f"BGMミキシングをスキップ: {str(e)[:50]}")

        # 5. Cloud Storageにアップロード (85%)
        firestore.update_job(job_id, progress=85, message="動画をアップロード中...")
        storage_url = storage.upload_file(
            video_path,
            f"outputs/{user_id}/{job_id}/output.mp4"
        )

        # 6. YouTubeに投稿 (95%)
        youtube_url = None
        if auto_post:
            firestore.update_job(job_id, progress=95, message="YouTubeに投稿中...")
            youtube_url = youtube.upload_video(
                video_path=str(video_path),
                title=f"{theme} | KIMIDORI Movie Auto",
                user_id=user_id,
                description=f"テーマ「{theme}」から自動生成された動画です。\n\n{script_data.get('description', '')}",
                tags=script_data.get("tags", ["自動生成", "AI"]),
                privacy_status="private",  # 非公開で投稿
            )
        else:
            firestore.update_job(job_id, progress=95, message="動画生成完了（投稿は手動）")

        # 7. 完了 (100%)
        firestore.update_job(
            job_id,
            status="completed",
            progress=100,
            message="処理が完了しました！",
            youtube_url=youtube_url,
            storage_url=storage_url,
        )
        logger.info(f"モードAジョブ完了: {job_id} → {youtube_url}")

    except Exception as e:
        error_msg = f"処理中にエラーが発生しました: {str(e)}"
        logger.error(f"モードAジョブ失敗: {job_id} — {traceback.format_exc()}")
        firestore.update_job(job_id, status="failed", message=error_msg)

    finally:
        # 一時ファイルの掃除
        processor.cleanup(job_id)


async def run_mode_b_pipeline(
    job_id: str,
    storage_path: str,
    enable_jet_cut: bool,
    enable_subtitles: bool,
    user_id: str,
    target_youtube_account: Optional[str] = None,
    enable_broll: bool = True,
    pexels_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
):
    """モードBの処理パイプライン全体を実行（5ステップ可視化 ＆ Pexels文脈連動インサート）"""
    processor = ModeBProcessor(firestore, storage, pexels_api_key=pexels_api_key, gemini_api_key=gemini_api_key)
    logs = [f"Step 1: 素材動画の準備完了 ({Path(storage_path).name})"]
    try:
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # 1. 素材動画の取得
        if storage_path and Path(storage_path).exists():
            source_video_path = Path(storage_path)
        else:
            source_video_path = storage.download_file(storage_path, job_dir / "source.mp4")

        # 2. 音声認識 (Step 2: 30%)
        firestore.update_job(
            job_id,
            status="processing",
            progress=30,
            step=2,
            step_label="音声解析 & Whisper文字起こし中...",
            message="Whisperで音声を解析しタイムスタンプ付き字幕を抽出中...",
            logs=logs
        )
        transcription = await processor.transcribe_audio(source_video_path, job_id)
        char_count = len(transcription.get("text", ""))
        seg_count = len(transcription.get("segments", []))
        logs.append(f"Step 2: Whisper音声認識完了 ({char_count}文字 / {seg_count}セグメント)")

        # 3. 無音区間の検出とジェットカット (Step 3: 50%)
        if enable_jet_cut:
            firestore.update_job(
                job_id,
                progress=50,
                step=3,
                step_label="無音検出 & ジェットカット処理中...",
                message="無音区間を検出して不要箇所をカット中...",
                logs=logs
            )
            cut_video_path, synced_transcription, cut_stats = await processor.jet_cut(source_video_path, transcription, job_id)
            logs.append(f"Step 3: 無音区間を{cut_stats['cut_count']}箇所カット短縮 (計{cut_stats['saved_seconds']:.1f}秒削減)")
        else:
            cut_video_path = source_video_path
            synced_transcription = transcription
            logs.append("Step 3: ジェットカットはスキップされました")

        # 4. 台本の文脈・感情分析 & Pexels素材検索中 (Step 4: 70%)
        if enable_broll:
            firestore.update_job(
                job_id,
                progress=70,
                step=4,
                step_label="台本の文脈・感情分析 & Pexels素材検索中...",
                message="感情の高まりや重要シーンにPexels Bロール素材を検索・合成中...",
                logs=logs
            )
            broll_video_path, broll_logs = await processor.insert_broll_materials(
                cut_video_path, synced_transcription, job_id, enable_broll=True
            )
            if broll_logs:
                for bl in broll_logs:
                    logs.append(f"Step 4: Pexels素材インサート ({bl['time']}) - '{bl['query']}' [{bl['emotion']}]")
            else:
                logs.append("Step 4: Bロール素材の挿入はスキップまたは素材なしでした")
        else:
            broll_video_path = cut_video_path
            logs.append("Step 4: Bロール自動インサートはオフに設定されています")

        # 5. テロップの焼き付け (Step 5: 90%)
        if enable_subtitles:
            firestore.update_job(
                job_id,
                progress=90,
                step=5,
                step_label="素材インサート & テロップ結合レンダリング中...",
                message="高品質字幕テロップを映像に焼き付けレンダリング中...",
                logs=logs
            )
            final_video_path = await processor.burn_subtitles(
                broll_video_path, synced_transcription, job_id
            )
            logs.append("Step 5: 字幕テロップの焼き付けレンダリング完了")
        else:
            final_video_path = broll_video_path
            logs.append("Step 5: 字幕テロップ焼き付けはスキップされました")

        # 6. Cloud Storageにアップロード (オプション)
        storage_url = None
        try:
            storage_url = storage.upload_file(
                final_video_path,
                f"outputs/{user_id}/{job_id}/output.mp4"
            )
        except Exception as st_err:
            logger.warning(f"Storage保存スキップ (ローカルパスを利用): {st_err}")

        # 7. YouTubeに投稿 (オプション)
        youtube_url = None
        if target_youtube_account:
            try:
                youtube_url = youtube.upload_video(
                    video_path=str(final_video_path),
                    user_id=user_id,
                    title="自動編集動画 | KIMIDORI Movie Auto",
                    description="自動編集（ジェットカット＋テロップ付与）された動画です。",
                    tags=["自動編集", "ジェットカット", "テロップ"],
                    privacy_status="private",
                )
                logs.append("YouTube: チャンネルへの下書き投稿完了")
            except Exception as yt_err:
                logger.warning(f"YouTube投稿エラー: {yt_err}")

        # 8. 完了 (100%)
        logs.append("完了: 動画の自動編集がすべて正常に完了しました！")
        firestore.update_job(
            job_id,
            status="completed",
            progress=100,
            step=5,
            step_label="自動編集完了",
            message="動画の自動編集がすべて完了しました！",
            youtube_url=youtube_url,
            storage_url=storage_url,
            video_path=str(final_video_path),
            logs=logs
        )
        logger.info(f"モードBジョブ完了: {job_id} -> {final_video_path}")

    except Exception as e:
        error_msg = f"処理中にエラーが発生しました: {str(e)}"
        logger.error(f"モードBジョブ失敗: {job_id} — {traceback.format_exc()}")
        logs.append(f"エラー発生: {str(e)}")
        firestore.update_job(job_id, status="failed", progress=0, message=error_msg, logs=logs)

    finally:
        processor.cleanup(job_id)


# --- YouTube OAuth API ---
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from fastapi import HTTPException

class YouTubeAuthRequest(BaseModel):
    user_id: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None

@app.post("/api/auth/youtube/login")
async def youtube_login(req: YouTubeAuthRequest):
    """SaaS設定画面から呼ばれる、OAuthの開始エンドポイント"""
    try:
        client_id = req.client_id or config.YOUTUBE_CLIENT_ID
        client_secret = req.client_secret or config.YOUTUBE_CLIENT_SECRET
        redirect_uri = req.redirect_uri or config.YOUTUBE_REDIRECT_URI

        if not client_id or not client_secret:
            raise ValueError("YouTube OAuth Client ID or Client Secret is not configured.")

        url = youtube.generate_auth_url(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            user_id=req.user_id
        )
        return {"auth_url": url}
    except Exception as e:
        logger.error(f"Failed to generate auth url: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/youtube/callback")
async def youtube_callback(code: str, state: str):
    """Googleからのリダイレクトを受け取り、トークンを保存してチャンネル情報を親ウィンドウに渡す"""
    try:
        res = youtube.exchange_code(code, state)
        channel = res.get("channel", {})
        channel_json = json.dumps(channel, ensure_ascii=False) if channel else "{}"

        return HTMLResponse(content=f"""
        <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0B0F19; color: #fff; margin: 0; padding: 20px; text-align: center;">
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.4); border-radius: 12px; padding: 2rem; max-width: 420px;">
          <div style="margin-bottom: 1rem; color: #10B981;">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          </div>
          <h2 style="color: #10B981; margin-bottom: 0.5rem;">YouTube OAuth 2.0 連携完了</h2>
          <p style="color: #94A3B8; font-size: 0.9rem;">YouTubeチャンネル「{channel.get('name', '連携チャンネル')}」へのアップロード権限を取得しました。</p>
          <p style="color: #64748B; font-size: 0.8rem; margin-top: 1rem;">このウィンドウは自動的に閉じます...</p>
        </div>
        <script>
            const channelData = {channel_json};
            if (window.opener) {{
                window.opener.postMessage({{
                    type: 'youtube_auth_success',
                    channel: channelData
                }}, '*');
            }}
            setTimeout(() => window.close(), 2500);
        </script>
        </body></html>
        """)
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return HTMLResponse(content=f"""
        <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0B0F19; color: #fff; margin: 0; padding: 20px; text-align: center;">
        <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 12px; padding: 2rem; max-width: 420px;">
          <div style="margin-bottom: 1rem; color: #EF4444;">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          </div>
          <h2 style="color: #EF4444;">連携エラー</h2>
          <p style="color: #94A3B8; font-size: 0.9rem;">{str(e)}</p>
        </div>
        </body></html>
        """, status_code=400)


@app.get("/api/youtube/channels")
async def get_youtube_channels(user_id: str):
    """ユーザーに紐づいたYouTubeチャンネル一覧を取得する"""
    try:
        channels = youtube.get_user_channels(user_id)
        has_creds = youtube.has_valid_credentials(user_id)
        return {"channels": channels, "oauth_connected": has_creds or len(channels) > 0}
    except Exception as e:
        logger.error(f"Failed to get channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/youtube/oauth-status")
async def get_youtube_oauth_status(user_id: str = "default_user", byog: bool = False):
    """YouTube OAuth 2.0 接続状態・連携チャンネル・直接アップロード権限フラグを取得"""
    try:
        effective_uid = user_id or "default_user"
        plan_info = permission_manager.get_user_plan(effective_uid, byog_enabled=byog)
        channels = youtube.get_user_channels(effective_uid)
        has_creds = youtube.has_valid_credentials(effective_uid)
        return {
            "success": True,
            "oauth_connected": bool(has_creds or len(channels) > 0),
            "channels": channels,
            "can_direct_upload_youtube": bool(plan_info.get("can_direct_upload_youtube", False)),
            "can_use_premium_tts": bool(plan_info.get("can_use_premium_tts", False)),
            "plan": plan_info.get("plan", "free"),
        }
    except Exception as e:
        logger.error(f"Failed to get YouTube OAuth status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/youtube/channels/{channel_id}")
async def delete_youtube_channel(channel_id: str, user_id: str):
    """ユーザーの連携済みYouTubeチャンネルを解除する"""
    try:
        youtube.remove_user_channel(user_id=user_id, channel_id=channel_id)
        return {"success": True, "message": f"チャンネル {channel_id} の連携を解除しました"}
    except Exception as e:
        logger.error(f"Failed to delete channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class YouTubeDirectUploadRequest(BaseModel):
    job_id: str = Field(..., description="対象動画のジョブID")
    user_id: str = Field("default_user", description="ユーザーID")
    title: str = Field(..., description="YouTube動画タイトル")
    description: str = Field("", description="YouTube概要欄（説明文）")
    tags: Union[List[str], str] = Field(default_factory=list, description="タグ/ハッシュタグ（配列またはカンマ区切り）")
    privacy_status: str = Field("private", description="public / private / unlisted / scheduled")
    publish_at: Optional[str] = Field(None, description="予約投稿日時 (ISO 8601: YYYY-MM-DDTHH:MM:SSZ)")
    thumbnail_base64: Optional[str] = Field(None, description="自前サムネイル画像 (Data URL / Base64)")
    thumbnail_cut_index: Optional[int] = Field(None, description="動画内カット番号からのサムネイル指定 (1始まり)")
    byog_enabled: bool = Field(False, description="BYOGモード有効フラグ")


async def _execute_youtube_direct_upload(
    job_id: str,
    user_id: str,
    title: str,
    description: str,
    tags: Union[List[str], str],
    privacy_status: str = "private",
    publish_at: Optional[str] = None,
    thumbnail_base64: Optional[str] = None,
    thumbnail_cut_index: Optional[int] = None,
    byog_enabled: bool = False,
) -> dict:
    """ジョブ動画およびサムネイルを解決し、YouTube Data API Resumable Uploadを実行する共通ヘルパー"""
    effective_uid = user_id if (user_id and user_id not in ["user_123", "default_user"]) else "oumaumauma32@gmail.com"
    plan_info = permission_manager.get_user_plan(effective_uid, byog_enabled=byog_enabled)
    if not plan_info.get("can_direct_upload_youtube", False):
        raise HTTPException(
            status_code=403,
            detail="ライトプラン（簡易ショート）ではYouTube直接投稿は制限されています。ProプランまたはBYOG設定でご利用いただけます。"
        )

    # 1. ローカルまたはStorageから完成動画ファイルパスを特定
    candidates = [
        config.TMP_DIR / job_id / "manga_video_final.mp4",
        config.TMP_DIR / job_id / "final_with_bgm.mp4",
        config.TMP_DIR / job_id / "final_output.mp4",
        config.TMP_DIR / f"cache_{job_id}.mp4",
    ]
    video_file: Optional[Path] = None
    for cand in candidates:
        if cand.exists() and cand.stat().st_size > 0:
            video_file = cand
            break

    cleanup_tmp_video = False
    if not video_file:
        job = firestore.get_job(job_id)
        if job:
            v_path = job.get("video_path")
            s_url = job.get("storage_url")
            if v_path and Path(v_path).exists():
                video_file = Path(v_path)
            elif s_url and Path(s_url).exists():
                video_file = Path(s_url)
            elif s_url:
                tmp_dl = config.TMP_DIR / f"upload_{job_id}.mp4"
                storage.download_file(s_url, tmp_dl)
                if tmp_dl.exists():
                    video_file = tmp_dl
                    cleanup_tmp_video = True

    if not video_file or not video_file.exists():
        raise HTTPException(status_code=404, detail=f"アップロード対象の動画ファイルが見つかりません (job_id={job_id})")

    # 2. タグリストの正規化
    if isinstance(tags, str):
        tag_list = [t.strip().lstrip("#") for t in tags.replace("、", ",").split(",") if t.strip()]
    else:
        tag_list = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]

    # 3. サムネイル画像の解決（自前Base64画像 または 動画内カット静止画 bg_xxx.png）
    thumb_path: Optional[Path] = None
    job_dir = config.TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    if thumbnail_base64:
        try:
            import base64
            from PIL import Image
            from io import BytesIO
            b64_clean = thumbnail_base64.split(",", 1)[1] if "," in thumbnail_base64 else thumbnail_base64
            img = Image.open(BytesIO(base64.b64decode(b64_clean))).convert("RGB")
            thumb_path = job_dir / "youtube_custom_thumbnail.jpg"
            img.save(thumb_path, "JPEG", quality=92)
        except Exception as th_err:
            logger.warning(f"Failed to decode custom thumbnail_base64: {th_err}")
    elif thumbnail_cut_index is not None and int(thumbnail_cut_index) >= 1:
        cut_idx = int(thumbnail_cut_index)
        cut_bg = job_dir / "assets" / f"bg_{cut_idx:03d}.png"
        if cut_bg.exists():
            thumb_path = cut_bg

    # 4. 予約投稿日時の正規化
    normalized_publish_at = None
    if privacy_status == "scheduled" or publish_at:
        if not publish_at:
            raise HTTPException(status_code=400, detail="予約投稿を選択した場合は公開日時（publish_at）を指定してください。")
        normalized_publish_at = publish_at.strip()
        if len(normalized_publish_at) == 16:  # YYYY-MM-DDTHH:MM
            normalized_publish_at += ":00Z"
        elif not normalized_publish_at.endswith("Z") and "+" not in normalized_publish_at[10:]:
            normalized_publish_at += "Z"

    # 5. YouTube Data API チャンク分割アップロード実行
    youtube_url = await asyncio.to_thread(
        youtube.upload_video,
        video_path=str(video_file),
        title=title,
        user_id=user_id,
        description=description,
        tags=tag_list,
        privacy_status=privacy_status,
        publish_at=normalized_publish_at,
        thumbnail_path=str(thumb_path) if thumb_path else None,
    )

    if cleanup_tmp_video and video_file.exists():
        video_file.unlink(missing_ok=True)

    if not youtube_url:
        raise HTTPException(
            status_code=400,
            detail="YouTubeアカウントが未連携か、OAuth 2.0トークンが無効です。「Googleアカウント連携」からチャンネルを接続してください。"
        )

    try:
        firestore.update_job(job_id, youtube_url=youtube_url)
    except Exception:
        pass

    return {
        "success": True,
        "job_id": job_id,
        "youtube_url": youtube_url,
        "privacy_status": "private" if normalized_publish_at else privacy_status,
        "publish_at": normalized_publish_at,
        "thumbnail_applied": bool(thumb_path and thumb_path.exists()),
    }


@app.post("/api/youtube/direct-upload")
async def youtube_direct_upload_endpoint(req: YouTubeDirectUploadRequest):
    """プレビュー画面およびプロ動画編集スタジオからYouTubeへ直接OAuth投稿・予約投稿を行う"""
    try:
        return await _execute_youtube_direct_upload(
            job_id=req.job_id,
            user_id=req.user_id,
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy_status=req.privacy_status,
            publish_at=req.publish_at,
            thumbnail_base64=req.thumbnail_base64,
            thumbnail_cut_index=req.thumbnail_cut_index,
            byog_enabled=req.byog_enabled,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"YouTube直接アップロード失敗 ({req.job_id}): {e}")
        raise HTTPException(status_code=500, detail=f"YouTube直接アップロードに失敗しました: {str(e)}")



# =============================================================================
# BGM管理 API
# =============================================================================
from fastapi import UploadFile, File, Form


@app.post("/api/bgm/upload")
async def upload_bgm(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    keywords: str = Form(""),
):
    """BGM楽曲をアップロードして登録する"""
    try:
        # 一時ファイルに保存
        tmp_dir = config.TMP_DIR / "bgm_uploads"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / file.filename

        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # キーワードをリストに変換（カンマ区切り）
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

        result = bgm_service.register_bgm(
            file_path=tmp_path,
            original_filename=file.filename,
            title=title,
            description=description,
            keywords=kw_list,
        )

        # 一時ファイルを削除
        tmp_path.unlink(missing_ok=True)

        return {"success": True, "bgm": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"BGMアップロード失敗: {e}")
        raise HTTPException(status_code=500, detail=f"BGMアップロードに失敗しました: {str(e)}")


@app.get("/api/bgm/list")
async def list_bgm():
    """登録済みBGM一覧（システム共通）を取得"""
    try:
        bgm_list = bgm_service.list_bgm()
        return {"bgm_tracks": bgm_list}
    except Exception as e:
        logger.error(f"BGM一覧取得失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/bgm/{bgm_id}")
async def delete_bgm(bgm_id: str):
    """BGMを削除する"""
    try:
        bgm_service.delete_bgm(bgm_id)
        return {"success": True, "message": f"BGM {bgm_id} を削除しました"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"BGM削除失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BGMUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[list[str]] = None


@app.put("/api/bgm/{bgm_id}")
async def update_bgm(bgm_id: str, req: BGMUpdateRequest):
    """BGMメタデータを更新する"""
    try:
        update_fields = {}
        if req.title is not None:
            update_fields["title"] = req.title
        if req.description is not None:
            update_fields["description"] = req.description
        if req.keywords is not None:
            update_fields["keywords"] = req.keywords

        result = bgm_service.update_bgm(bgm_id, **update_fields)
        return {"success": True, "bgm": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"BGM更新失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# ユーザー権限・プラン＆長尺漫画動画作成 API エンドポイント
# =============================================================================
@app.get("/api/user/permissions")
async def get_user_permissions(user_id: str, feature: Optional[str] = None, byog: bool = False):
    """ユーザーのプラン情報および指定機能の権限情報（can_use_premium_tts / can_direct_upload_youtube）を取得"""
    plan_info = permission_manager.get_user_plan(user_id, byog_enabled=byog)
    if feature:
        access_info = permission_manager.check_feature_access(user_id, feature, byog_enabled=byog)
        return {"plan_info": plan_info, "access_info": access_info}
    return {"plan_info": plan_info}



@app.post("/api/user/plan")
async def update_user_plan_endpoint(req: UserPlanUpdateRequest):
    """ユーザーの会員プランを更新する（デモ・テスト用）"""
    success = permission_manager.update_user_plan(req.user_id, req.plan, req.expire_date)
    return {"success": success}


# -----------------------------------------------------------------------------
# 管理者専用: ユーザー管理 API (一覧・手動追加・プラン変更・削除)
# -----------------------------------------------------------------------------
@app.get("/api/admin/users")
async def get_admin_users():
    """管理用: 登録ユーザー一覧を取得"""
    try:
        users = permission_manager.list_users()
        return {"success": True, "users": users}
    except Exception as e:
        logger.error(f"Failed to list admin users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/users")
async def create_admin_user(req: AdminUserCreateRequest):
    """管理用: 新規ユーザーを手動登録"""
    try:
        user = permission_manager.create_user(
            email=req.email,
            plan=req.plan or "free",
            role=req.role or "user",
            status=req.status or "active",
            notes=req.notes or ""
        )
        return {"success": True, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/users/{user_id}")
async def update_admin_user(user_id: str, req: AdminUserUpdateRequest):
    """管理用: 既存ユーザーのプラン・権限・ステータスを更新"""
    try:
        updates = req.dict(exclude_unset=True)
        updated_user = permission_manager.update_user(user_id, updates)
        return {"success": True, "user": updated_user}
    except Exception as e:
        logger.error(f"Failed to update user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/users/{user_id}")
async def delete_admin_user(user_id: str):
    """管理用: ユーザーを削除"""
    try:
        success = permission_manager.delete_user(user_id)
        return {"success": success}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/manga/script")
async def generate_manga_script_endpoint(req: MangaScriptRequest):
    """長尺漫画動画のシナリオ・コマ割りJSONを生成する"""
    effective_user_id = req.user_id if (req.user_id and req.user_id not in ["user_123", "default_user"]) else "oumaumauma32@gmail.com"
    access = permission_manager.check_feature_access(effective_user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    try:
        km = KeyManager(req.gemini_api_keys)
        generator = MangaScriptGenerator(key_manager=km)
        script = await generator.generate_manga_script_async(
            original_text=req.original_text,
            target_length_minutes=req.target_length_minutes
        )
        return {"success": True, "script": script}
    except Exception as e:
        logger.error(f"Manga script generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manga/generate")
async def generate_manga_video_endpoint(req: MangaVideoGenerateRequest, background_tasks: BackgroundTasks):
    """長尺漫画動画生成ジョブを発行する"""
    effective_user_id = req.user_id if (req.user_id and req.user_id not in ["user_123", "default_user"]) else "oumaumauma32@gmail.com"
    access = permission_manager.check_feature_access(effective_user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    # クレジット残高検証 & 減算 (BYOG時は0消費)
    byog_active = bool(req.gemini_api_keys or req.colab_worker_url)
    scenes_count = len(req.script_data.get("scenes", [])) if (req.script_data and isinstance(req.script_data, dict)) else 10
    needed_credits = scenes_count * config.CREDIT_COST_LONG_PER_SCENE

    credit_res = billing_manager.check_and_deduct_credits(
        user_id=effective_user_id,
        amount=needed_credits,
        description=f"長尺漫画動画生成 ({scenes_count}シーン)",
        byog_enabled=byog_active
    )
    if not credit_res["success"]:
        raise HTTPException(
            status_code=402,
            detail=f"クレジット残高が不足しています (必要: {needed_credits} pt, 保有: {credit_res.get('available', 0)} pt)。設定画面よりプラン加入または追加チャージを行ってください。"
        )

    job_id = str(uuid.uuid4())
    job_data = {
        "job_id": job_id,
        "user_id": effective_user_id,
        "mode": "MANGA_LONG",
        "status": "processing",
        "progress": 5,
        "message": "長尺漫画動画生成ジョブを開始しました...",
        "created_at": datetime.now().isoformat()
    }
    firestore.collection.document(job_id).set(job_data)

    # 有料Gemini APIキーが空の場合はメインGemini APIキーを自動フォールバック適用
    effective_gemini_key = (req.paid_gemini_api_key or "").strip()
    if not effective_gemini_key and req.gemini_api_keys:
        if isinstance(req.gemini_api_keys, list) and len(req.gemini_api_keys) > 0:
            effective_gemini_key = str(req.gemini_api_keys[0]).strip()
        elif isinstance(req.gemini_api_keys, str):
            parts = [k.strip() for k in req.gemini_api_keys.split(",") if k.strip()]
            if parts:
                effective_gemini_key = parts[0]
    if not effective_gemini_key:
        effective_gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    job_kwargs = dict(
        job_id=job_id,
        script_data=req.script_data,
        user_id=req.user_id,
        tts_engine=req.tts_engine,
        voice_name=req.voice_name,
        bgm_map=req.bgm_map,
        watermark_required=access["watermark_required"],
        paid_gemini_api_key=effective_gemini_key,
        tts_params=req.tts_params,
        colab_worker_url=req.colab_worker_url or "",
        fal_api_key=req.fal_api_key or "",
        replicate_api_token=req.replicate_api_token or "",
        pexels_api_key=req.pexels_api_key or "",
        visual_style=req.visual_style,
        telop_style=req.telop_style or "shorts_impact_yellow",
        telop_mode=req.telop_mode or "sequential",
        telop_font_size=req.telop_font_size or "medium",
        telop_font=req.telop_font or "DelaGothicOne",
        bgm_choice=req.bgm_choice or "auto_script",
        bgm_volume=float(req.bgm_volume if req.bgm_volume is not None else 0.20),
        custom_reference_images=req.custom_reference_images,
        video_mode=req.video_mode,
        comic_color_mode=req.comic_color_mode or "color",
        comic_bubble_enabled=req.comic_bubble_enabled,
        comic_bubble_delay=float(req.comic_bubble_delay if req.comic_bubble_delay is not None else 0.40),
        character_traits=req.character_traits
    )
    try:
        j_dir = config.TMP_DIR / job_id
        j_dir.mkdir(parents=True, exist_ok=True)
        # Base64画像を含むとjob_params.jsonが肥大化するため除外して保存
        slim_kwargs = {k: v for k, v in job_kwargs.items() if k != "custom_reference_images"}
        (j_dir / "job_params.json").write_text(json.dumps(slim_kwargs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as jp_err:
        logger.warning(f"Failed to save job_params.json: {jp_err}")

    background_tasks.add_task(run_manga_video_job, **job_kwargs)
    return {"job_id": job_id, "status": "PROCESSING"}



class SceneRegenerateRequest(BaseModel):
    job_id: str
    scene_id: int
    custom_prompt: Optional[str] = None
    tts_engine: Optional[str] = "edge"
    voice_name: Optional[str] = "nanami"
    paid_gemini_api_key: Optional[str] = ""
    tts_params: Optional[dict] = None


@app.post("/api/timeline/scene/regenerate")
async def regenerate_single_scene_endpoint(req: SceneRegenerateRequest):
    """タイムライン内の特定シーン（Cut）を単体で再生成・リカバリーする"""
    try:
        from processors.long_manga_pipeline import regenerate_single_scene
        result = await regenerate_single_scene(
            job_id=req.job_id,
            scene_id=req.scene_id,
            custom_prompt=req.custom_prompt,
            tts_engine=req.tts_engine or "edge",
            voice_name=req.voice_name or "nanami",
            paid_gemini_api_key=req.paid_gemini_api_key or "",
            tts_params=req.tts_params
        )
        return result
    except FileNotFoundError as fe:
        raise HTTPException(status_code=404, detail=str(fe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Scene regenerate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Pro版ショート動画 & 長尺動画（完全仕様） API エンドポイント
# =============================================================================
class ProShortsRequest(BaseModel):
    theme: str
    genre: str = "story"
    visual_style: Optional[str] = None
    user_id: str = "default_user"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/pro-shorts/script")
async def generate_pro_shorts_script_endpoint(req: ProShortsRequest):
    """Pro版ショート動画（60秒・全カット動画演出）の台本を生成する"""
    effective_user_id = req.user_id if (req.user_id and req.user_id not in ["user_123", "default_user"]) else "oumaumauma32@gmail.com"
    access = permission_manager.check_feature_access(effective_user_id, FeatureName.PRO_SHORT_VIDEO_CREATE if hasattr(FeatureName, "PRO_SHORT_VIDEO_CREATE") else FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    try:
        from processors.pro_shorts_engine import ProShortsEngine
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        engine = ProShortsEngine(key_manager=km)
        script = await engine.generate_pro_shorts_script(
            theme=req.theme,
            genre=req.genre,
            visual_style=req.visual_style
        )
        return {"success": True, "script": script}
    except Exception as e:
        logger.error(f"Pro版ショート動画台本生成失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LongVideoScriptRequest(BaseModel):
    theme: str
    genre: str = "story"
    visual_style: Optional[str] = None
    target_minutes: int = 15
    research_notes: Optional[str] = ""
    script_mode: Optional[str] = "standard"
    character_traits: Optional[List[dict]] = None
    user_id: str = "default_user"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/long-video/script")
async def generate_long_video_script_endpoint(req: LongVideoScriptRequest):
    """長尺動画（15〜20分・全5章・120〜180カット）の完全仕様台本と人物シートを生成する"""
    effective_user_id = req.user_id if (req.user_id and req.user_id not in ["user_123", "default_user"]) else "oumaumauma32@gmail.com"
    access = permission_manager.check_feature_access(effective_user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    try:
        from processors.long_video_engine import LongVideoEngine
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        engine = LongVideoEngine(key_manager=km)
        script = await engine.generate_long_script(
            theme=req.theme,
            genre=req.genre,
            target_minutes=req.target_minutes,
            research_notes=req.research_notes or "",
            visual_style=req.visual_style,
            script_mode=req.script_mode or "standard",
            character_traits=req.character_traits
        )
        return {"success": True, "script": script}
    except Exception as e:
        logger.error(f"長尺動画台本生成失敗: {e}")
        raise HTTPException(status_code=500, detail=f"長尺台本生成に失敗しました: {str(e)}")


# =============================================================================
# 真のリサーチ（Outlier検出・洋書日本化） & 台本正規化 & FLUX.1/Colab GPU API
# =============================================================================
class OutlierResearchRequest(BaseModel):
    keyword: str
    genre: Optional[str] = "knowledge"
    user_id: Optional[str] = "default_user"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/research/outliers")
async def research_outliers_endpoint(req: OutlierResearchRequest):
    """登録者数比高再生のOutlier（外れ値）動画を検出し、真の隠れ需要と多角的な切り口を抽出"""
    try:
        from processors.outlier_research_engine import OutlierResearchEngine
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        engine = OutlierResearchEngine(key_manager=km, firestore_service=firestore)
        outliers = engine.search_outlier_topics(req.keyword, limit=6, user_id=req.user_id)
        analysis = await engine.analyze_and_extract_hidden_angles(req.keyword, outliers, req.genre)
        return {"success": True, "outliers": outliers, "analysis": analysis}
    except Exception as e:
        logger.error(f"Outlierリサーチ失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BookAdaptRequest(BaseModel):
    concept: str
    audience: Optional[str] = "日本のビジネスパーソン（30代〜50代の中堅社員・管理職）"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/research/adapt-book")
async def adapt_book_endpoint(req: BookAdaptRequest):
    """海外ビジネス洋書・理論コンセプトを日本の職場カルチャーに翻案"""
    try:
        from processors.outlier_research_engine import OutlierResearchEngine
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        engine = OutlierResearchEngine(key_manager=km)
        adapted = await engine.adapt_western_business_book(req.concept, req.audience)
        return {"success": True, "adaptation": adapted}
    except Exception as e:
        logger.error(f"洋書翻案処理失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ScriptNormalizeRequest(BaseModel):
    raw_script: str
    target_format: Optional[str] = "pro_shorts"
    genre: Optional[str] = "knowledge"
    visual_style: Optional[str] = None
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/script/normalize")
async def normalize_script_endpoint(req: ScriptNormalizeRequest):
    """外部入力テキスト、ファイル、Driveの台本を当ツール専用の厳格なタイムラインJSONへリライト正規化"""
    try:
        from processors.script_normalizer import ScriptNormalizer
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        normalizer = ScriptNormalizer(key_manager=km)
        normalized = await normalizer.normalize_to_timeline_json(
            raw_text=req.raw_script,
            target_format=req.target_format or "pro_shorts",
            genre=req.genre or "knowledge",
            visual_style=req.visual_style
        )
        return {"success": True, "timeline": normalized}
    except Exception as e:
        logger.error(f"台本正規化リライト失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FluxGenRequest(BaseModel):
    prompt: str
    provider: Optional[str] = "fal"
    api_key: Optional[str] = None
    width: Optional[int] = 1024
    height: Optional[int] = 576
    steps: Optional[int] = 4


@app.post("/api/generate/flux")
async def generate_flux_image_endpoint(req: FluxGenRequest):
    """FLUX.1 [schnell] (fal.ai / Replicate) 画像生成"""
    try:
        from processors.flux_client import FluxSchnellClient
        client = FluxSchnellClient(provider=req.provider, api_key=req.api_key)
        res = await client.generate_image(
            prompt=req.prompt,
            width=req.width or 1024,
            height=req.height or 576,
            num_inference_steps=req.steps or 4
        )
        return res
    except Exception as e:
        logger.error(f"FLUX.1生成失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ColabHealthRequest(BaseModel):
    worker_url: Optional[str] = ""
    colab_url: Optional[str] = ""


class ColabConfigRequest(BaseModel):
    colab_url: str


@app.get("/api/colab/config")
async def get_colab_config():
    """現在のColab/ComfyUI接続設定を取得"""
    import os
    import config
    current_url = os.environ.get("COMFYUI_API_URL") or getattr(config, "COMFYUI_API_URL", "")
    return {"colab_url": current_url}


@app.post("/api/colab/config")
async def update_colab_config(req: ColabConfigRequest):
    """管理者ページ等から動的にColab/ComfyUI URLを更新・永続化"""
    import os
    from pathlib import Path
    import config

    sanitized = req.colab_url.strip().rstrip("/")
    os.environ["COMFYUI_API_URL"] = sanitized
    os.environ["COLAB_WORKER_URL"] = sanitized
    setattr(config, "COMFYUI_API_URL", sanitized)
    setattr(config, "COLAB_WORKER_URL", sanitized)

    # .env.local に永続保存
    env_local = Path(__file__).parent.parent / ".env.local"
    try:
        env_local.write_text(f"COMFYUI_API_URL={sanitized}\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to persist .env.local: {e}")

    return {"success": True, "colab_url": sanitized, "message": "Colab接続URLを更新・保存しました。"}


@app.post("/api/colab/health")
async def colab_health_endpoint(req: ColabHealthRequest):
    """Google Colab 無料T4 GPUワーカー / ComfyUI (LTX-Video) のヘルスチェック"""
    from processors.colab_gpu_client import ColabGpuClient
    import os
    import config

    target_url = (req.colab_url or req.worker_url or os.environ.get("COMFYUI_API_URL") or getattr(config, "COMFYUI_API_URL", "")).strip()
    client = ColabGpuClient(target_url)
    res = await client.check_health()
    return res


class ColabImageRequest(BaseModel):
    worker_url: str
    prompt: str
    width: Optional[int] = 1024
    height: Optional[int] = 576
    steps: Optional[int] = 4


@app.post("/api/colab/generate/image")
async def colab_generate_image_endpoint(req: ColabImageRequest):
    """Google Colab 無料GPUによる FLUX.1 画像生成"""
    try:
        from processors.colab_gpu_client import ColabGpuClient
        client = ColabGpuClient(req.worker_url)
        res = await client.generate_image(
            prompt=req.prompt,
            width=req.width or 1024,
            height=req.height or 576,
            steps=req.steps or 4
        )
        return res
    except Exception as e:
        logger.error(f"Colab画像生成失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TTS 統合API (完全無料・フリーミアム・有料の全エンジン対応 & 試聴プレビュー)
# =============================================================================
@app.get("/api/tts/engines")
async def list_tts_engines():
    """利用可能な全TTSエンジンのカタログ一覧"""
    return {
        "engines": [
            {
                "id": "edge",
                "name": "Edge TTS",
                "tier": "free",
                "tier_label": "完全無料 (API不要)",
                "description": "Microsoft Neural音声。APIキー不要で即座に使える最高品質の標準音声。",
                "voices": [
                    {"id": "nanami", "name": "七海 (女性・標準)"},
                    {"id": "keita", "name": "慶太 (男性・標準)"},
                    {"id": "aoi", "name": "あおい (女性・若い)"},
                    {"id": "daichi", "name": "大地 (男性・落ち着き)"},
                    {"id": "mayu", "name": "まゆ (女性・明るい)"},
                    {"id": "naoki", "name": "直樹 (男性・若い)"},
                    {"id": "shiori", "name": "しおり (女性・柔らか)"},
                ]
            },
            {
                "id": "gtts",
                "name": "Google翻訳 TTS (gTTS)",
                "tier": "free",
                "tier_label": "完全無料 (API不要)",
                "description": "Google Translate TTS。完全無料・登録不要・超軽量でどこでも動作。",
                "voices": [{"id": "ja", "name": "日本語 (標準)"}]
            },
            {
                "id": "voicevox",
                "name": "VOICEVOX (ローカル/API)",
                "tier": "free",
                "tier_label": "完全無料 (商用利用可)",
                "description": "ずんだもん、四国めたん等の大人気キャラクター音声。ローカルソフト起動または外部URLで利用可能。",
                "voices": [
                    {"id": "3", "name": "ずんだもん (ノーマル)"},
                    {"id": "1", "name": "ずんだもん (あまあま)"},
                    {"id": "7", "name": "ずんだもん (ツンツン)"},
                    {"id": "5", "name": "ずんだもん (セクシー)"},
                    {"id": "2", "name": "四国めたん (ノーマル)"},
                    {"id": "0", "name": "四国めたん (あまあま)"},
                    {"id": "8", "name": "春日部つむぎ (ノーマル)"},
                    {"id": "10", "name": "雨晴はう (ノーマル)"},
                    {"id": "9", "name": "波音リツ (ノーマル)"},
                    {"id": "11", "name": "玄野武宏 (ノーマル)"},
                    {"id": "12", "name": "白上虎太郎 (ノーマル)"},
                    {"id": "13", "name": "青山龍星 (ノーマル)"},
                    {"id": "14", "name": "冥鳴ひまり (ノーマル)"},
                    {"id": "16", "name": "九州そら (ノーマル)"},
                ]
            },
            {
                "id": "sharevox",
                "name": "SHAREVOX (ローカル/API)",
                "tier": "free",
                "tier_label": "完全無料 (商用利用可)",
                "description": "小春音アミ、つくよみちゃん等の追加キャラクター音声。",
                "voices": [
                    {"id": "0", "name": "小春音アミ (ノーマル)"},
                    {"id": "1", "name": "つくよみちゃん (ノーマル)"},
                    {"id": "2", "name": "白痴ー (ノーマル)"},
                ]
            },
            {
                "id": "coeiroink",
                "name": "COEIROINK (ローカル/API)",
                "tier": "free",
                "tier_label": "完全無料 (個人ライブラリ)",
                "description": "多様なユーザー制作音声ライブラリが利用可能なTTSエンジン。",
                "voices": [
                    {"id": "0", "name": "つくよみちゃん (標準スタイル)"},
                    {"id": "1", "name": "MANA (標準スタイル)"},
                ]
            },
            {
                "id": "aivis",
                "name": "AivisSpeech / Aivis Cloud",
                "tier": "free",
                "tier_label": "完全無料 / クラウド",
                "description": "VOICEVOX互換の高品質AI音声合成ソフト。",
                "voices": [
                    {"id": "1", "name": "話者 1"},
                    {"id": "2", "name": "話者 2"},
                ]
            },
            {
                "id": "voxcpm",
                "name": "OpenBMB VoxCPM (48kHzスタジオ音質 / ElevenLabs互換OSS)",
                "tier": "pro_oss",
                "tier_label": "プロ向け / 48kHz Studio Quality",
                "description": "OpenBMB VoxCPM2 (Tokenizer-free 2Bモデル)。48kHzスタジオ音質、vLLM-Omni (/v1/audio/speech) 及び ElevenLabs互換API対応。",
                "voices": [
                    {"id": "default", "name": "標準スタジオナレーター (48kHz)"},
                    {"id": "announcer_female", "name": "アナウンサー (女性・明瞭)"},
                    {"id": "narrator_male", "name": "ドキュメンタリー (男性・深み)"},
                    {"id": "energetic_host", "name": "情報番組ホスト (快活)"},
                    {"id": "calm_story", "name": "解説・教養 (落ち着き)"},
                    {"id": "custom_clone", "name": "カスタム参照ボイス (Voice Clone)"},
                ]
            },
            {
                "id": "oss_elevenlabs",
                "name": "高品質OSS TTS（ElevenLabs互換 / F5-TTS / Fish Speech）",
                "tier": "pro_oss",
                "tier_label": "プロ向け / 高品質OSS",
                "description": "POST /v1/text-to-speech (ElevenLabs互換) や F5-TTS / Fish Speech 等のオープンソース高品質TTSサーバーへ接続。",
                "voices": [
                    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel (標準女性 / ElevenLabs互換)"},
                    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (標準男性 / ElevenLabs互換)"},
                    {"id": "f5_default_ja", "name": "F5-TTS 日本語マスターボイス"},
                    {"id": "fish_default_ja", "name": "Fish Speech 日本語ナレーター"},
                ]
            },
            {
                "id": "oss_custom",
                "name": "次世代OSS音声モデル (Fish Speech / GPT-SoVITS / ChatTTS / StyleTTS2)",
                "tier": "pro_oss",
                "tier_label": "プロ向け / ローカル・サーバー",
                "description": "Fish Speech, GPT-SoVITS, ChatTTS, Bert-VITS2, StyleTTS2 等のローカルAPI/OpenAI互換TTSエンドポイント。",
                "voices": [{"id": "default", "name": "デフォルト"}]
            },
            {
                "id": "openai",
                "name": "OpenAI TTS (tts-1 / tts-1-hd)",
                "tier": "paid",
                "tier_label": "有料 / 超自然",
                "description": "人間と聞き分けがつかない最高レベルの自然な読み上げ。従量課金制。",
                "voices": [
                    {"id": "alloy", "name": "Alloy (中性的・標準)"},
                    {"id": "echo", "name": "Echo (男性・クリア)"},
                    {"id": "fable", "name": "Fable (イギリス調・表現豊か)"},
                    {"id": "onyx", "name": "Onyx (男性・深みのある声)"},
                    {"id": "nova", "name": "Nova (女性・明るい)"},
                    {"id": "shimmer", "name": "Shimmer (女性・落ち着いた響き)"},
                ]
            },
            {
                "id": "elevenlabs",
                "name": "ElevenLabs",
                "tier": "freemium",
                "tier_label": "月1万字無料 / 有料",
                "description": "世界最高峰のリアルな多言語音声クローンと感情表現。",
                "voices": [
                    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel (女性)"},
                    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi (女性)"},
                    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (女性)"},
                    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni (男性)"},
                    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (男性)"},
                    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (男性)"},
                ]
            },
            {
                "id": "google",
                "name": "Google Cloud Text-to-Speech",
                "tier": "freemium",
                "tier_label": "月数百万字無料 / 有料",
                "description": "Googleが提供する超高安定なNeural2/WaveNet音声。",
                "voices": [
                    {"id": "ja-JP-Neural2-B", "name": "Neural2-B (女性)"},
                    {"id": "ja-JP-Neural2-C", "name": "Neural2-C (男性)"},
                    {"id": "ja-JP-Wavenet-A", "name": "WaveNet-A (女性)"},
                    {"id": "ja-JP-Wavenet-C", "name": "WaveNet-C (男性)"},
                ]
            },
            {
                "id": "azure",
                "name": "Microsoft Azure Cognitive Services Speech",
                "tier": "freemium",
                "tier_label": "月50万字無料 (F0) / 有料",
                "description": "極めて自然なAzureニューラル音声。F0ティアで毎月50万文字永久無料枠。",
                "voices": [
                    {"id": "ja-JP-NanamiNeural", "name": "Nanami (女性)"},
                    {"id": "ja-JP-KeitaNeural", "name": "Keita (男性)"},
                    {"id": "ja-JP-AoiNeural", "name": "Aoi (女性)"},
                    {"id": "ja-JP-DaichiNeural", "name": "Daichi (男性)"},
                ]
            },
            {
                "id": "amazon_polly",
                "name": "Amazon Polly (AWS)",
                "tier": "freemium",
                "tier_label": "12ヶ月無料枠 / 有料",
                "description": "AWSが提供する音声合成。Mizuki, Takumi, Kazuhaのニューラル音声対応。",
                "voices": [
                    {"id": "Mizuki", "name": "Mizuki (女性・標準)"},
                    {"id": "Takumi", "name": "Takumi (男性・Neural)"},
                    {"id": "Kazuha", "name": "Kazuha (女性・Neural)"},
                    {"id": "Tomoko", "name": "Tomoko (女性・標準)"},
                ]
            },
            {
                "id": "ondoku",
                "name": "音読さん (Ondoku)",
                "tier": "freemium",
                "tier_label": "月5000字無料 / 有料",
                "description": "クリエイターに人気のWeb読み上げツールのAPI連携。",
                "voices": [{"id": "default", "name": "標準音声"}]
            },
            {
                "id": "coefont",
                "name": "CoeFont",
                "tier": "paid",
                "tier_label": "有料 (API対応)",
                "description": "日本の著名人・アナウンサー声などの音声ライブラリプラットフォーム。",
                "voices": [{"id": "default", "name": "登録ボイス"}]
            }
        ]
    }


@app.post("/api/tts/preview")
async def preview_tts(req: TTSPreviewRequest):
    """指定されたTTS設定で音声をテスト合成し、MP3バイナリを直接返す"""
    try:
        from processors.tts_manager import TTSManager
        params = req.model_dump()
        tts_engine = params.pop("tts_engine", "edge")
        voice_name = params.pop("voice_name", "nanami")
        speaking_rate = params.pop("speaking_rate", 1.0)
        text = params.pop("text", "こんにちは。音声合成のテストです。")

        tts_mgr = TTSManager(
            engine=tts_engine,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            **params
        )

        preview_dir = config.TMP_DIR / "tts_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_file = preview_dir / f"preview_{int(datetime.utcnow().timestamp() * 1000)}.mp3"

        await tts_mgr.synthesize_single_text(text, preview_file, is_preview=True)

        if not preview_file.exists() or preview_file.stat().st_size == 0:
            raise RuntimeError("音声ファイルの生成に失敗しました")

        return FileResponse(
            path=str(preview_file),
            media_type="audio/mpeg",
            filename="tts_preview.mp3"
        )
    except Exception as e:
        logger.error(f"TTSプレビュー生成エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TelopPreviewRequest(BaseModel):
    text: Optional[str] = "まさか、そんな秘密があったなんて…！"
    telop_font: Optional[str] = "keifont"
    telop_style: Optional[str] = "shorts_impact_yellow"
    telop_font_size: Optional[str] = "medium"
    genre: Optional[str] = "story"
    visual_style: Optional[str] = "anime_modern"


@app.post("/api/telop/preview")
async def preview_telop_endpoint(req: TelopPreviewRequest):
    """選択されたテロップフォント・配色・サイズを本番同一の5層エンジンで即座に描画してBase64 PNGを返す"""
    try:
        from processors.batch_asset_generator import BatchAssetGenerator
        gen = BatchAssetGenerator()
        b64_url = gen.generate_telop_preview_base64(
            text=req.text or "まさか、そんな秘密があったなんて…！",
            telop_font=req.telop_font or "keifont",
            telop_style=req.telop_style or "shorts_impact_yellow",
            telop_font_size=req.telop_font_size or "medium",
            genre=req.genre or "story",
            visual_style=req.visual_style or "anime_modern"
        )
        return {"success": True, "image_base64": b64_url}
    except Exception as e:
        logger.error(f"テロッププレビュー描画エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bgm/builtin/{preset_id}")
async def get_builtin_bgm_preview(preset_id: str):
    """内蔵プリセットBGM（edo_ukiyoe, dramatic_strings 等）の試聴用オーディオファイルを返す"""
    try:
        from processors.batch_asset_generator import BatchAssetGenerator
        bgm_dir = config.DATA_DIR / "bgm"
        wav_path = BatchAssetGenerator.ensure_builtin_bgm_file(preset_id, bgm_dir)
        if not wav_path or not wav_path.exists():
            raise HTTPException(status_code=404, detail="指定されたプリセットBGMの生成に失敗しました")
        return FileResponse(path=str(wav_path), media_type="audio/wav", filename=wav_path.name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"内蔵BGMプレビュー取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bgm/file/{bgm_id}")
async def get_custom_bgm_file(bgm_id: str):
    """登録済みカスタムBGMの試聴用オーディオファイルを返す"""
    try:
        bgm_dir = config.DATA_DIR / "bgm"
        local_candidate = bgm_dir / bgm_id
        if local_candidate.exists():
            return FileResponse(path=str(local_candidate))
        downloaded = bgm_service.download_bgm(bgm_id, bgm_dir)
        return FileResponse(path=str(downloaded))
    except Exception as e:
        logger.error(f"カスタムBGMプレビュー取得エラー: {e}")
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# 保存済み動画ストック管理（最大5本保持・リロード復元対応）& 効果音(SE) & 動画編集スタジオ API
# =============================================================================
@app.get("/api/videos/saved")
async def list_saved_videos_endpoint(mode: Optional[str] = None, limit: int = 5):
    """生成済み動画の保存ストック一覧を取得（リロードしても最大5本まで保持・即時復元）"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        videos = svc.list_saved_videos(mode=mode, limit=max(1, min(limit, 10)))
        return {"success": True, "videos": videos, "max_saved": 5}
    except Exception as e:
        logger.error(f"保存済み動画一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/videos/saved/{job_id}")
async def delete_saved_video_endpoint(job_id: str, delete_files: bool = False):
    """保存済み動画ストックから指定ジョブを削除"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        removed = svc.delete_saved_video(job_id=job_id, delete_files=delete_files)
        return {"success": True, "removed": removed}
    except Exception as e:
        logger.error(f"保存済み動画削除エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs/{job_id}/asset/{filename}")
async def get_job_asset_file(job_id: str, filename: str):
    """ジョブディレクトリ内の個別アセット（bg_xxx.png, clip_xxx.mp4, speech_xxx.mp3, overlay_xxx.png 等）を配信"""
    from fastapi.responses import FileResponse
    safe_name = Path(filename).name
    candidates = [
        config.TMP_DIR / job_id / "assets" / safe_name,
        config.TMP_DIR / job_id / "assets" / "characters" / safe_name,
        config.TMP_DIR / job_id / "work" / safe_name,
        config.TMP_DIR / job_id / safe_name,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            ext = p.suffix.lower()
            media_type = "application/octet-stream"
            if ext == ".png":
                media_type = "image/png"
            elif ext in (".jpg", ".jpeg"):
                media_type = "image/jpeg"
            elif ext == ".mp4":
                media_type = "video/mp4"
            elif ext == ".mp3":
                media_type = "audio/mpeg"
            elif ext == ".wav":
                media_type = "audio/wav"
            return FileResponse(
                path=str(p),
                media_type=media_type,
                headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
            )
    raise HTTPException(status_code=404, detail=f"アセットが見つかりません: {safe_name}")


@app.get("/api/se/list")
async def list_se_presets_endpoint():
    """動画編集スタジオで利用可能な効果音（SE）プリセット＆カスタムSE一覧を取得"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        return {"success": True, "se_list": svc.list_se_presets()}
    except Exception as e:
        logger.error(f"SE一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/se/file/{se_id}")
async def get_se_audio_file_endpoint(se_id: str):
    """効果音（SE）の試聴・再生用オーディオファイルを返す"""
    from fastapi.responses import FileResponse
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        se_path = svc.ensure_se_file(se_id)
        if not se_path or not se_path.exists():
            raise HTTPException(status_code=404, detail=f"効果音ファイルが見つかりません: {se_id}")
        media_type = "audio/wav" if se_path.suffix.lower() == ".wav" else "audio/mpeg"
        return FileResponse(path=str(se_path), media_type=media_type, filename=se_path.name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SEファイル取得エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/se/upload")
async def upload_custom_se_endpoint(file: UploadFile = File(...)):
    """カスタム効果音（MP3/WAV等）をアップロードしてSEライブラリに追加"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        ext = Path(file.filename or "se.mp3").suffix.lower()
        if ext not in (".mp3", ".wav", ".ogg", ".m4a"):
            ext = ".mp3"
        safe_stem = "".join(c for c in Path(file.filename or "custom_se").stem if c.isalnum() or c in ("_", "-"))[:32] or "custom_se"
        out_name = f"{safe_stem}_{int(datetime.utcnow().timestamp())}{ext}"
        out_path = svc.se_dir / out_name
        content = await file.read()
        out_path.write_bytes(content)
        return {
            "success": True,
            "se": {
                "id": f"custom:{out_name}",
                "name": f"カスタム: {Path(file.filename or out_name).stem}",
                "category": "カスタム",
                "duration": 2.0,
                "url": f"/api/se/file/custom:{out_name}"
            }
        }
    except Exception as e:
        logger.error(f"カスタムSEアップロードエラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from studio_pro import router as studio_pro_router  # Studio Pro (jet-cut / wipe / B-roll)
app.include_router(studio_pro_router)


class EditorSaveRequest(BaseModel):
    editor_state: Dict[str, Any]


class EditorResynthesizeTTSRequest(BaseModel):
    cut_index: int = Field(1, description="1始まりのカット番号またはscene_id")
    narration: str
    speaker: Optional[str] = "ナレーション"
    tts_engine: Optional[str] = "edge"
    voice_name: Optional[str] = "nanami"
    speaking_rate: Optional[float] = 1.0
    tts_params: Optional[Dict[str, Any]] = None


class EditorCutMediaUploadRequest(BaseModel):
    cut_index: int = Field(1, description="対象カットのscene_id")
    media_type: str = Field("image", description="image / video / audio")
    data_base64: str = Field(..., description="Data URL または Base64文字列")
    filename: Optional[str] = "uploaded_media.png"


@app.get("/api/manga/editor/{job_id}")
async def get_manga_editor_state_endpoint(job_id: str):
    """指定ジョブの動画編集スタジオ用タイムライン状態・全カットアセット情報を取得"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        state = svc.get_editor_state(job_id)
        return {"success": True, "editor": state}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"編集スタジオデータ取得エラー ({job_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manga/editor/{job_id}/save")
async def save_manga_editor_state_endpoint(job_id: str, req: EditorSaveRequest):
    """動画編集スタジオのタイムライン編集内容を一時保存（レンダリングなし）"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        saved = svc.save_editor_state(job_id, req.editor_state)
        return {"success": True, "editor": saved}
    except Exception as e:
        logger.error(f"編集スタジオ保存エラー ({job_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manga/editor/{job_id}/resynthesize-tts")
async def resynthesize_cut_tts_endpoint(job_id: str, req: EditorResynthesizeTTSRequest):
    """動画編集スタジオ内で単一カットのナレーションテキスト＆音声をその場で再合成し、尺と音声URLを更新"""
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        res = await svc.resynthesize_cut_tts(
            job_id=job_id,
            cut_index=req.cut_index,
            narration=req.narration,
            speaker=req.speaker or "ナレーション",
            tts_engine=req.tts_engine or "edge",
            voice_name=req.voice_name or "nanami",
            speaking_rate=float(req.speaking_rate if req.speaking_rate is not None else 1.0),
            tts_params=req.tts_params
        )
        return res
    except Exception as e:
        logger.error(f"カットTTS再合成エラー ({job_id} / Cut {req.cut_index}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manga/editor/{job_id}/upload-cut-media")
async def upload_cut_media_endpoint(job_id: str, req: EditorCutMediaUploadRequest):
    """動画編集スタジオ内で特定カットの背景画像・動画クリップ・音声ファイルをユーザー素材に差し替え"""
    try:
        import base64
        from PIL import Image
        from io import BytesIO

        job_dir = config.TMP_DIR / job_id
        assets_dir = job_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        b64_data = req.data_base64
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        raw_bytes = base64.b64decode(b64_data)

        idx = max(1, int(req.cut_index))
        ts = int(datetime.utcnow().timestamp())

        if req.media_type == "image":
            out_path = assets_dir / f"bg_{idx:03d}.png"
            pil_img = Image.open(BytesIO(raw_bytes)).convert("RGB")
            pil_img.save(out_path, "PNG")
            return {
                "success": True,
                "media_type": "image",
                "image_url": f"/api/jobs/{job_id}/asset/{out_path.name}?t={ts}"
            }
        elif req.media_type == "video":
            out_path = assets_dir / f"clip_{idx:03d}.mp4"
            out_path.write_bytes(raw_bytes)
            return {
                "success": True,
                "media_type": "video",
                "video_url": f"/api/jobs/{job_id}/asset/{out_path.name}?t={ts}"
            }
        elif req.media_type == "audio":
            out_path = assets_dir / f"speech_{idx:03d}.mp3"
            out_path.write_bytes(raw_bytes)
            from processors.manga_video_composer import MangaVideoComposer
            dur = round(MangaVideoComposer()._get_audio_duration(out_path), 2)
            return {
                "success": True,
                "media_type": "audio",
                "audio_url": f"/api/jobs/{job_id}/asset/{out_path.name}?t={ts}",
                "duration": dur
            }
        else:
            raise HTTPException(status_code=400, detail=f"未対応のmedia_typeです: {req.media_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"カットメディア差し替えエラー ({job_id}): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/manga/editor/{job_id}/render")
async def render_edited_timeline_endpoint(job_id: str, req: EditorSaveRequest):
    """
    動画編集スタジオで編集されたタイムライン（テロップ変更・位置変更・ナレーション変更・カットトリミング/削除/順序変更・効果音SE追加・BGM変更）を
    既存アセットを活かして高速FFmpeg再レンダリングし、完成MP4および保存済み5本ストックを更新する
    """
    try:
        from services.video_stock_service import VideoStockAndEditorService
        svc = VideoStockAndEditorService()
        res = await asyncio.to_thread(svc.render_edited_timeline, job_id=job_id, editor_state=req.editor_state)
        # Firestore上のジョブ情報も最新化
        try:
            firestore.update_job(
                job_id,
                status="completed",
                progress=100,
                message="動画編集スタジオでの再書き出しが完了しました！",
                video_path=res.get("video_path"),
                storage_url=res.get("video_path")
            )
        except Exception:
            pass
        return res
    except Exception as e:
        logger.error(f"動画編集スタジオ再レンダリングエラー ({job_id}): {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"再書き出しに失敗しました: {str(e)}")


# =============================================================================
# Stripe サブスクリプション & クレジット課金 API
# =============================================================================
class CheckoutRequest(BaseModel):
    user_id: str
    user_email: Optional[str] = ""
    item_type: str = "subscription"  # 'subscription' or 'credit_pack'
    item_id: str = "pro"             # 'lite'|'pro'|'premium' or 'pack_small'|'pack_medium'|'pack_large'
    success_url: Optional[str] = "http://localhost:3001/?checkout_success=true"
    cancel_url: Optional[str] = "http://localhost:3001/?checkout_canceled=true"


@app.get("/api/billing/credits/{user_id}")
async def get_user_credits_endpoint(user_id: str):
    """ユーザーのクレジット残高・プラン情報を取得"""
    return billing_manager.get_user_credit_balance(user_id)


@app.get("/api/billing/plans")
async def get_billing_plans_endpoint():
    """利用可能なプラン体系および追加クレジットパック一覧"""
    return {
        "plans": config.PLAN_PRICING,
        "credit_packs": config.CREDIT_PACKS
    }


@app.post("/api/billing/create-checkout-session")
async def create_checkout_session_endpoint(req: CheckoutRequest):
    """Stripe Checkout Session 発行"""
    try:
        session_data = billing_manager.create_checkout_session(
            user_id=req.user_id,
            user_email=req.user_email or "",
            item_type=req.item_type,
            item_id=req.item_id,
            success_url=req.success_url or "http://localhost:3001/?checkout_success=true",
            cancel_url=req.cancel_url or "http://localhost:3001/?checkout_canceled=true"
        )
        return session_data
    except Exception as e:
        logger.error(f"チェックアウトセッション発行エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stripe/webhook")
async def stripe_webhook_endpoint(request: Request):
    """Stripe Webhook 受信ハンドラー"""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        result = billing_manager.handle_webhook_event(payload, sig_header)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Stripe Webhook エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# マーケティング自動化 API（外部シナリオ/Webhook連動）
# =============================================================================
import secrets as _secrets
import httpx as _httpx


class MarketingTriggerRequest(BaseModel):
    """外部マーケティングツールからの動画生成トリガーリクエスト"""
    marketing_source: str = Field(..., description="呼び出し元識別子 (line, x_auto, blog, affiliate 等)")
    topic: Optional[str] = Field(None, description="動画テーマ（topic または script どちらか必須）")
    script: Optional[str] = Field(None, description="自前台本テキスト（topic または script どちらか必須）")
    mode: str = Field("pro_shorts", description="生成モード: 'pro_shorts' または 'long_manga'")
    style: Optional[str] = Field("informative", description="演出スタイル")
    tts_engine: Optional[str] = Field("edge", description="TTSエンジン")
    webhook_callback_url: Optional[str] = Field(None, description="生成完了通知先URL")
    user_id: str = Field("system", description="トリガーユーザーID")


class MarketingJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    accepted_at: str


async def _fire_marketing_webhook(callback_url: str, job_id: str, payload: dict):
    """動画生成完了後にWebhookコールバックURLへPOST通知する"""
    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            await client.post(callback_url, json=payload)
            logger.info(f"[MarketingWebhook] 通知成功: {callback_url} job={job_id}")
    except Exception as e:
        logger.warning(f"[MarketingWebhook] 通知失敗 ({callback_url}): {e}")


async def _run_marketing_video_pipeline(job_id: str, req: MarketingTriggerRequest):
    """バックグラウンドで動画生成を実行し、完了後にWebhookへ通知する"""
    try:
        firestore.update_job(job_id, {"status": "processing", "progress": 5})

        result_video_url = ""
        result_title = req.topic or "自動生成動画"
        result_description = ""
        result_captions: List[str] = []

        if req.mode == "long_manga":
            from processors.manga_script_generator import MangaScriptGenerator
            gemini_key = config.GEMINI_API_KEY
            script_gen = MangaScriptGenerator(gemini_api_key=gemini_key)
            script_data = await asyncio.to_thread(
                script_gen.generate_script,
                topic=req.topic or req.script or "自動生成",
                target_scenes=6
            )
            result_title = script_data.get("title", result_title)
            result_description = script_data.get("summary", "")
            result_captions = [s.get("narration", "") for s in script_data.get("scenes", [])]
            firestore.update_job(job_id, {"status": "completed", "progress": 100, "script_data": script_data})
        else:
            from processors.mode_a import ModeAProcessor
            gemini_key = config.GEMINI_API_KEY
            processor = ModeAProcessor(
                gemini_api_key=gemini_key,
                tts_engine=req.tts_engine or "edge",
                voice_name="nanami"
            )
            result_data = await asyncio.to_thread(
                processor.generate_script,
                theme=req.topic or req.script or "自動生成テーマ",
                style=req.style or "informative",
                duration_seconds=45
            )
            result_title = result_data.get("title", result_title)
            result_description = result_data.get("description", "")
            result_captions = result_data.get("captions", [])
            firestore.update_job(job_id, {"status": "completed", "progress": 100})

        if req.webhook_callback_url:
            callback_payload = {
                "job_id": job_id,
                "status": "completed",
                "marketing_source": req.marketing_source,
                "video_url": result_video_url,
                "title": result_title,
                "description": result_description,
                "captions": result_captions,
                "completed_at": datetime.utcnow().isoformat()
            }
            await _fire_marketing_webhook(req.webhook_callback_url, job_id, callback_payload)

    except Exception as e:
        logger.error(f"[MarketingPipeline] ジョブ {job_id} 失敗: {e}")
        firestore.update_job(job_id, {"status": "error", "error_message": str(e)})
        if req.webhook_callback_url:
            await _fire_marketing_webhook(
                req.webhook_callback_url, job_id,
                {"job_id": job_id, "status": "error", "error": str(e)}
            )


@app.post("/api/marketing/trigger-video-job", response_model=MarketingJobResponse)
async def marketing_trigger_video_job(
    req: MarketingTriggerRequest,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    外部マーケティングツール（LINE, X自動化, ブログ等）から動画生成をキックするエンドポイント。
    X-Marketing-Token ヘッダーによるAPIトークン認証が必要。
    """
    provided_token = request.headers.get("X-Marketing-Token", "")
    if not provided_token:
        raise HTTPException(status_code=401, detail="X-Marketing-Token ヘッダーが必要です。")

    user_doc = firestore.get_user(req.user_id)
    stored_token = (user_doc or {}).get("marketing_api_token", "")
    if not stored_token or provided_token != stored_token:
        raise HTTPException(status_code=403, detail="Marketing API Token が無効です。")

    if not req.topic and not req.script:
        raise HTTPException(status_code=422, detail="topic または script のいずれかを指定してください。")

    job_id = firestore.create_job(
        user_id=req.user_id,
        mode="marketing",
        params={
            "marketing_source": req.marketing_source,
            "mode": req.mode,
            "topic": req.topic,
            "style": req.style,
            "tts_engine": req.tts_engine,
            "webhook_callback_url": req.webhook_callback_url
        }
    )

    background_tasks.add_task(_run_marketing_video_pipeline, job_id=job_id, req=req)
    logger.info(f"[MarketingAPI] ジョブ受付: {job_id} source={req.marketing_source} mode={req.mode}")

    return MarketingJobResponse(
        job_id=job_id,
        status="accepted",
        message="ジョブを受け付けました。完了後に webhook_callback_url へ通知します。",
        accepted_at=datetime.utcnow().isoformat()
    )


@app.post("/api/marketing/generate-token")
async def generate_marketing_api_token(request: Request):
    """ユーザーの Marketing API Token を新規発行または再生成する。"""
    body = await request.json()
    user_id = body.get("user_id", "")
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id が必要です。")
    new_token = _secrets.token_hex(32)
    firestore.update_user(user_id, {"marketing_api_token": new_token})
    logger.info(f"[MarketingAPI] APIトークン再生成: user={user_id}")
    return {"user_id": user_id, "marketing_api_token": new_token}


@app.get("/api/marketing/token/{user_id}")
async def get_marketing_api_token(user_id: str):
    """ユーザーの現在の Marketing API Token を取得（マスク表示）"""
    user_doc = firestore.get_user(user_id)
    token = (user_doc or {}).get("marketing_api_token", "")
    if not token:
        return {"user_id": user_id, "marketing_api_token": None, "has_token": False}
    masked = token[:8] + "*" * (len(token) - 12) + token[-4:]
    return {"user_id": user_id, "marketing_api_token_masked": masked, "has_token": True}


@app.post("/api/marketing/test-webhook")
async def test_marketing_webhook(request: Request):
    """Webhook URLへのテスト送信"""
    body = await request.json()
    callback_url = body.get("webhook_url", "")
    if not callback_url:
        raise HTTPException(status_code=422, detail="webhook_url が必要です。")
    test_payload = {
        "job_id": "test-" + _secrets.token_hex(4),
        "status": "test",
        "message": "KIMIDORI YouTube Auto - Webhookテスト送信",
        "video_url": "",
        "title": "テスト動画タイトル",
        "description": "テスト動画の説明文",
        "captions": ["テスト字幕1", "テスト字幕2"],
        "sent_at": datetime.utcnow().isoformat()
    }
    try:
        async with _httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(callback_url, json=test_payload)
        return {"success": True, "status_code": resp.status_code, "message": f"テスト送信成功 (HTTP {resp.status_code})"}
    except Exception as e:
        return {"success": False, "error": str(e), "message": f"送信失敗: {e}"}


# =============================================================================
# 起動時の初期化
# =============================================================================
@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化処理"""
    logger.info("=== KIMIDORI Movie Auto API 起動 ===")
    logger.info(f"一時ディレクトリ: {config.TMP_DIR}")
    logger.info(f"Whisperモデル: {config.WHISPER_MODEL}")
    logger.info(f"Geminiモデル: {config.GEMINI_MODEL}")

    # 一時ディレクトリの初期化
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    # 既存の完成動画ジョブを保存済みストック（最大5本）と自動同期
    try:
        from services.video_stock_service import VideoStockAndEditorService
        VideoStockAndEditorService().sync_tmp_completed_jobs()
    except Exception as sync_err:
        logger.warning(f"Startup video stock sync warning: {sync_err}")


# フロントエンド静的ファイルの配信マウント (http://localhost:8080/ でWeb UIを直接表示)
frontend_dir = config.BASE_DIR.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")



