"""
KIMIDORI Movie Auto — FastAPI メインエントリーポイント
Cloud Run 上で動作する動画処理APIサーバー
"""

import asyncio
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
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
from processors.mode_a import ModeAProcessor
from processors.mode_b import ModeBProcessor
from processors.manga_script_generator import MangaScriptGenerator
from processors.batch_asset_generator import BatchAssetGenerator
from processors.manga_video_composer import MangaVideoComposer
from utils.key_manager import KeyManager
from typing import Optional, List, Dict, Union

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


class MangaScriptRequest(BaseModel):
    """長尺漫画シナリオ生成リクエスト"""
    original_text: str = Field(..., description="原案・エピソードテキスト")
    target_length_minutes: int = Field(3, description="目標動画長さ（分）")
    gemini_api_keys: Union[List[str], str] = Field(..., description="ユーザーのGemini APIキー（配列またはカンマ区切り）")
    user_id: str = Field(..., description="FirebaseユーザーID")


class MangaVideoGenerateRequest(BaseModel):
    """長尺漫画動画生成リクエスト"""
    script_data: dict = Field(..., description="生成されたシナリオJSON")
    user_id: str = Field(..., description="FirebaseユーザーID")
    gemini_api_keys: Union[List[str], str] = Field("", description="Gemini APIキー（無料枠：テキスト・構成用）")
    paid_gemini_api_key: Optional[str] = Field("", description="Gemini 有料APIキー（画像・キャラクター・動画生成用）")
    tts_engine: str = Field("edge", description="TTSエンジン")
    voice_name: str = Field("nanami", description="声色名")
    bgm_map: Dict[str, str] = Field({}, description="タグ別BGMファイルマッピング")
    auto_post: bool = Field(False, description="完全自動投稿フラグ")
    # TTS Parameters
    tts_params: Optional[Dict[str, Any]] = Field(None, description="詳細なTTS設定パラメータ")


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


async def run_manga_video_job(
    job_id: str,
    script_data: dict,
    user_id: str,
    tts_engine: str,
    voice_name: str,
    bgm_map: dict,
    watermark_required: bool,
    paid_gemini_api_key: str = "",
    tts_params: Optional[dict] = None
):
    """長尺漫画動画のバックグラウンド合成タスク"""
    try:
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        firestore.update_job(job_id, {"progress": 25, "message": "画像・ナレーション音声をバッチ生成中..."})

        # Step 3 バッチアセット生成（有料Geminiキーを画像生成、TTS設定をナレーションに使用）
        batch_gen = BatchAssetGenerator()
        scene_assets = await batch_gen.generate_batch_assets(
            script_data=script_data,
            output_dir=job_dir / "assets",
            tts_engine=tts_engine,
            voice_name=voice_name,
            tts_params=tts_params
        )

        firestore.update_job(job_id, {"progress": 65, "message": "0.3秒演出切り替え・マルチBGMクロスフェード合成中..."})

        # Step 4 動画合成
        composer = MangaVideoComposer()
        output_mp4 = job_dir / "manga_video_final.mp4"
        composer.compose_manga_video(
            scene_assets=scene_assets,
            bgm_map=bgm_map,
            output_video_path=output_mp4,
            work_dir=job_dir / "work",
            is_paid_member=not watermark_required
        )

        firestore.update_job(job_id, {
            "status": "COMPLETED",
            "progress": 100,
            "message": "長尺漫画動画の作成が完了しました！",
            "video_path": str(output_mp4)
        })
    except Exception as e:
        logger.error(f"Manga video job {job_id} failed: {e}")
        firestore.update_job(job_id, {
            "status": "FAILED",
            "progress": 0,
            "message": f"動画生成エラー: {str(e)}"
        })



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

        # Firestoreにジョブドキュメントを作成
        job_id = firestore.create_job(
            user_id=request.user_id,
            mode="A",
            params={
                "theme": request.theme,
                "style": request.style,
                "duration_seconds": duration,
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
    auto_subtitle: bool = Form(True),
    target_youtube_account: Optional[str] = Form(None)
):
    """
    モードB: 素材動画を直接アップロードしてジェットカット＆自動テロップ処理を開始
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

        logger.info(f"素材動画アップロード完了: {file.filename} -> {source_video_path} ({source_video_path.stat().st_size} bytes)")

        # Firestoreにジョブドキュメントを作成
        firestore.create_job(
            user_id=user_id,
            mode="B",
            params={
                "storage_path": str(source_video_path),
                "enable_jet_cut": jet_cut,
                "enable_subtitles": auto_subtitle,
                "target_youtube_account": target_youtube_account,
                "filename": file.filename
            }
        )

        # バックグラウンドで動画処理を実行
        background_tasks.add_task(
            run_mode_b_pipeline,
            job_id=job_id,
            storage_path=str(source_video_path),
            enable_jet_cut=jet_cut,
            enable_subtitles=auto_subtitle,
            user_id=user_id,
            target_youtube_account=target_youtube_account,
        )

        return JobStatusResponse(
            job_id=job_id,
            status="pending",
            progress=0,
            message="動画を受け付けました。自動編集を開始します...",
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
async def get_job_status(job_id: str):
    """ジョブの現在のステータスを取得"""
    try:
        job = firestore.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")

        return JobStatusResponse(
            job_id=job_id,
            status=job.get("status", "unknown"),
            progress=job.get("progress", 0),
            message=job.get("message", ""),
            youtube_url=job.get("youtube_url"),
            storage_url=job.get("storage_url"),
            created_at=job.get("created_at"),
            research_strategy=job.get("research_strategy")
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


@app.post("/api/jobs/{job_id}/publish")
async def publish_job_manual(job_id: str, req: PublishRequest):
    """完了済みの動画をYouTubeに手動でアップロードする"""
    try:
        job = firestore.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")
        if job.get("status") != "completed":
            raise HTTPException(status_code=400, detail="動画がまだ完成していません")
            
        storage_url = job.get("storage_url")
        if not storage_url:
            raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")

        # ローカルにダウンロードしてからアップロード
        tmp_video_path = config.TMP_DIR / f"upload_{job_id}.mp4"
        storage.download_file(storage_url, tmp_video_path)

        youtube_url = youtube.upload_video(
            video_path=str(tmp_video_path),
            title=req.title,
            user_id=req.user_id,
            description=req.description,
            tags=req.tags,
            privacy_status="private"  # 初期設定は非公開
        )

        if not youtube_url:
            raise HTTPException(status_code=500, detail="YouTube APIが利用できないか、認証されていません。")

        # ジョブを更新
        firestore.update_job(job_id, youtube_url=youtube_url)
        tmp_video_path.unlink(missing_ok=True)

        return {"success": True, "youtube_url": youtube_url}
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
        job = firestore.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")
        if job.get("status") != "completed":
            raise HTTPException(status_code=400, detail="動画がまだ完成していません")

        storage_path = job.get("storage_url")
        if not storage_path:
            raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")

        # 1. ローカルの一時ディレクトリにファイルが残っているかチェック (同一インスタンスでの即時プレビュー)
        local_candidates = [
            config.TMP_DIR / job_id / "final_with_bgm.mp4",
            config.TMP_DIR / job_id / "final_output.mp4",
            config.TMP_DIR / f"cache_{job_id}.mp4",
        ]
        local_video = None
        for cand in local_candidates:
            if cand.exists() and cand.stat().st_size > 0:
                local_video = cand
                break

        # 2. ローカルにない場合はCloud Storageからローカルキャッシュに1回だけ取得
        if not local_video:
            if storage_path.startswith("http"):
                return RedirectResponse(url=storage_path)

            blob = storage.bucket.blob(storage_path)
            if not blob.exists():
                raise HTTPException(status_code=404, detail="Storage上にファイルが見つかりません")

            cache_path = config.TMP_DIR / f"cache_{job_id}.mp4"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(cache_path))
            local_video = cache_path

        # 3. Starlette FileResponse を返却
        # FileResponse は内部で Accept-Ranges: bytes, 206 Partial Content, Content-Length, Content-Range を完全自動処理
        disposition = "attachment" if download == 1 else "inline"
        filename = f"kimidori_video_{job_id}.mp4"

        return FileResponse(
            path=str(local_video),
            media_type="video/mp4",
            content_disposition_type=disposition,
            filename=filename if disposition == "attachment" else None,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
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
):
    """モードBの処理パイプライン全体を実行"""
    processor = ModeBProcessor(firestore, storage)
    try:
        firestore.update_job(job_id, status="processing", progress=5, message="処理を開始しています...")

        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # 1. 素材動画の取得 (10%)
        firestore.update_job(job_id, progress=10, message="素材動画を準備中...")
        if storage_path and Path(storage_path).exists():
            source_video_path = Path(storage_path)
        else:
            source_video_path = storage.download_file(storage_path, job_dir / "source.mp4")

        # 2. 音声認識 (30%)
        firestore.update_job(job_id, progress=30, message="Whisperで音声認識中...")
        transcription = await processor.transcribe_audio(source_video_path, job_id)

        # 3. 無音区間の検出とジェットカット (50%)
        if enable_jet_cut:
            firestore.update_job(job_id, progress=50, message="無音区間を検出してカット中...")
            cut_video_path = await processor.jet_cut(source_video_path, transcription, job_id)
        else:
            cut_video_path = source_video_path

        # 4. テロップの焼き付け (70%)
        if enable_subtitles:
            firestore.update_job(job_id, progress=70, message="自動テロップを焼き付け中...")
            final_video_path = await processor.burn_subtitles(
                cut_video_path, transcription, job_id
            )
        else:
            final_video_path = cut_video_path

        # 5. Cloud Storageにアップロード (85%)
        firestore.update_job(job_id, progress=85, message="完成動画を保存中...")
        storage_url = None
        try:
            storage_url = storage.upload_file(
                final_video_path,
                f"outputs/{user_id}/{job_id}/output.mp4"
            )
        except Exception as st_err:
            logger.warning(f"Storage保存スキップ (ローカルパスを利用): {st_err}")

        # 6. YouTubeに投稿 (オプション)
        youtube_url = None
        if target_youtube_account:
            firestore.update_job(job_id, progress=95, message="YouTubeに投稿中...")
            try:
                youtube_url = youtube.upload_video(
                    video_path=str(final_video_path),
                    user_id=user_id,
                    title="自動編集動画 | KIMIDORI Movie Auto",
                    description="自動編集（ジェットカット＋テロップ付与）された動画です。",
                    tags=["自動編集", "ジェットカット", "テロップ"],
                    privacy_status="private",
                )
            except Exception as yt_err:
                logger.warning(f"YouTube投稿エラー: {yt_err}")

        # 7. 完了 (100%)
        firestore.update_job(
            job_id,
            status="completed",
            progress=100,
            message="処理が完了しました！",
            youtube_url=youtube_url,
            storage_url=storage_url,
            video_path=str(final_video_path)
        )
        logger.info(f"モードBジョブ完了: {job_id} -> {final_video_path}")

    except Exception as e:
        error_msg = f"処理中にエラーが発生しました: {str(e)}"
        logger.error(f"モードBジョブ失敗: {job_id} — {traceback.format_exc()}")
        firestore.update_job(job_id, status="failed", message=error_msg)

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
        <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0f0c1b; color: #fff; margin: 0; padding: 20px; text-align: center;">
        <div style="background: rgba(57, 255, 20, 0.1); border: 1px solid rgba(57, 255, 20, 0.3); border-radius: 12px; padding: 2rem; max-width: 400px;">
          <div style="font-size: 3rem; margin-bottom: 1rem;">✅</div>
          <h2 style="color: #39ff14; margin-bottom: 0.5rem;">連携完了！</h2>
          <p style="color: #a0aec0; font-size: 0.9rem;">YouTubeチャンネル「{channel.get('name', '不明')}」の連携が完了しました。</p>
          <p style="color: #666; font-size: 0.8rem; margin-top: 1rem;">このウィンドウは自動的に閉じます...</p>
        </div>
        <script>
            const channelData = {channel_json};
            window.opener.postMessage({{
                type: 'youtube_auth_success',
                channel: channelData
            }}, '*');
            setTimeout(() => window.close(), 3000);
        </script>
        </body></html>
        """)
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return HTMLResponse(content=f"""
        <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0f0c1b; color: #fff; margin: 0; padding: 20px; text-align: center;">
        <div style="background: rgba(255, 50, 50, 0.1); border: 1px solid rgba(255, 50, 50, 0.3); border-radius: 12px; padding: 2rem; max-width: 400px;">
          <div style="font-size: 3rem; margin-bottom: 1rem;">❌</div>
          <h2 style="color: #ff3232;">連携エラー</h2>
          <p style="color: #a0aec0; font-size: 0.9rem;">{str(e)}</p>
        </div>
        </body></html>
        """, status_code=400)


@app.get("/api/youtube/channels")
async def get_youtube_channels(user_id: str):
    """ユーザーに紐づいたYouTubeチャンネル一覧を取得する"""
    try:
        channels = youtube.get_user_channels(user_id)
        return {"channels": channels}
    except Exception as e:
        logger.error(f"Failed to get channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/youtube/channels/{channel_id}")
async def delete_youtube_channel(channel_id: str, user_id: str):
    """ユーザーの連携済みYouTubeチャンネルを解除する"""
    try:
        firestore.db.collection('users').document(user_id).collection('youtube_channels').document(channel_id).delete()
        return {"success": True, "message": f"チャンネル {channel_id} の連携を解除しました"}
    except Exception as e:
        logger.error(f"Failed to delete channel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def get_user_permissions(user_id: str, feature: Optional[str] = None):
    """ユーザーのプラン情報および指定機能の権限情報を取得"""
    plan_info = permission_manager.get_user_plan(user_id)
    if feature:
        access_info = permission_manager.check_feature_access(user_id, feature)
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
    access = permission_manager.check_feature_access(req.user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
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
    access = permission_manager.check_feature_access(req.user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    job_id = str(uuid.uuid4())
    job_data = {
        "job_id": job_id,
        "user_id": req.user_id,
        "mode": "MANGA_LONG",
        "status": "PROCESSING",
        "progress": 5,
        "message": "長尺漫画動画生成ジョブを開始しました...",
        "created_at": datetime.now().isoformat()
    }
    firestore.create_job(job_id, job_data)

    background_tasks.add_task(
        run_manga_video_job,
        job_id=job_id,
        script_data=req.script_data,
        user_id=req.user_id,
        tts_engine=req.tts_engine,
        voice_name=req.voice_name,
        bgm_map=req.bgm_map,
        watermark_required=access["watermark_required"],
        paid_gemini_api_key=req.paid_gemini_api_key or "",
        tts_params=req.tts_params
    )
    return {"job_id": job_id, "status": "PROCESSING"}


# =============================================================================
# Pro版ショート動画 & 長尺動画（完全仕様） API エンドポイント
# =============================================================================
class ProShortsRequest(BaseModel):
    theme: str
    genre: str = "story"
    user_id: str = "default_user"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/pro-shorts/script")
async def generate_pro_shorts_script_endpoint(req: ProShortsRequest):
    """Pro版ショート動画（60秒・全カット動画演出）の台本を生成する"""
    access = permission_manager.check_feature_access(req.user_id, FeatureName.PRO_SHORT_VIDEO_CREATE if hasattr(FeatureName, "PRO_SHORT_VIDEO_CREATE") else FeatureName.MANGA_LONG_VIDEO_CREATE)
    if not access["allowed"]:
        raise HTTPException(status_code=403, detail=access["reason"])

    try:
        from processors.pro_shorts_engine import ProShortsEngine
        km = KeyManager(req.gemini_api_keys or [config.GEMINI_API_KEY])
        engine = ProShortsEngine(key_manager=km)
        script = await engine.generate_pro_shorts_script(theme=req.theme, genre=req.genre)
        return {"success": True, "script": script}
    except Exception as e:
        logger.error(f"Pro版ショート動画台本生成失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LongVideoScriptRequest(BaseModel):
    theme: str
    genre: str = "story"
    target_minutes: int = 15
    research_notes: Optional[str] = ""
    user_id: str = "default_user"
    gemini_api_keys: Optional[List[str]] = None


@app.post("/api/long-video/script")
async def generate_long_video_script_endpoint(req: LongVideoScriptRequest):
    """長尺動画（15〜20分・全5章・120〜180カット）の完全仕様台本と人物シートを生成する"""
    access = permission_manager.check_feature_access(req.user_id, FeatureName.MANGA_LONG_VIDEO_CREATE)
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
            research_notes=req.research_notes or ""
        )
        return {"success": True, "script": script}
    except Exception as e:
        logger.error(f"長尺動画台本生成失敗: {e}")
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
                "id": "oss_custom",
                "name": "次世代OSS音声モデル (Fish Speech / GPT-SoVITS / ChatTTS / StyleTTS2)",
                "tier": "free",
                "tier_label": "完全無料 (ローカル/サーバー)",
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

        await tts_mgr.synthesize_single_text(text, preview_file)

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


# フロントエンド静的ファイルの配信マウント (http://localhost:8080/ でWeb UIを直接表示)
frontend_dir = config.BASE_DIR.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


