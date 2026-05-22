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

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

import config
from services.firestore_service import FirestoreService
from services.storage_service import StorageService
from services.youtube_service import YouTubeService
from processors.mode_a import ModeAProcessor
from processors.mode_b import ModeBProcessor

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


# =============================================================================
# リクエスト/レスポンスモデル
# =============================================================================
class ModeARequest(BaseModel):
    """モードA: ゼロから生成リクエスト"""
    theme: str = Field(..., description="動画のテーマ")
    style: Optional[str] = Field("informative", description="動画のスタイル")
    duration_seconds: Optional[int] = Field(45, description="目標の動画長さ（秒）")
    user_id: str = Field(..., description="FirebaseユーザーID")
    gemini_api_key: str = Field("", description="ユーザーのGemini APIキー")
    pexels_api_key: str = Field("", description="Pexels APIキー（フリー画像用）")
    
    # TTS Settings
    tts_engine: str = Field("edge", description="使用するTTSエンジン")
    voice_name: str = Field("nanami", description="音声名（Edge用など）")
    speaking_rate: float = Field(1.0, description="読み上げ速度")
    google_tts_key: str = Field("", description="Google Cloud TTS用APIキー")
    elevenlabs_key: str = Field("", description="ElevenLabs APIキー")
    aivis_key: str = Field("", description="Aivis Cloud APIキー")
    
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


class JobStatusResponse(BaseModel):
    """ジョブステータスレスポンス"""
    job_id: str
    status: str
    progress: int = 0
    message: str = ""
    youtube_url: Optional[str] = None
    created_at: Optional[str] = None


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
        background_tasks.add_task(
            run_mode_a_pipeline,
            job_id=job_id,
            theme=request.theme,
            style=request.style,
            duration=duration,
            user_id=request.user_id,
            gemini_api_key=request.gemini_api_key,
            pexels_api_key=request.pexels_api_key,
            tts_engine=request.tts_engine,
            voice_name=request.voice_name,
            speaking_rate=request.speaking_rate,
            google_tts_key=request.google_tts_key,
            elevenlabs_key=request.elevenlabs_key,
            aivis_key=request.aivis_key,
            script_data=request.script_data,
            auto_post=request.auto_post,
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
# モードB: 既存動画の自動編集
# =============================================================================
@app.post("/api/process/mode-b", response_model=JobStatusResponse)
async def process_mode_b(request: ModeBRequest, background_tasks: BackgroundTasks):
    """
    モードB: アップロードされた素材動画を自動編集
    非同期でバックグラウンド処理を開始し、即座にジョブIDを返す
    """
    try:
        # Firestoreにジョブドキュメントを作成
        job_id = firestore.create_job(
            user_id=request.user_id,
            mode="B",
            params={
                "storage_path": request.storage_path,
                "enable_jet_cut": request.enable_jet_cut,
                "enable_subtitles": request.enable_subtitles,
            }
        )

        # バックグラウンドで動画処理を実行
        background_tasks.add_task(
            run_mode_b_pipeline,
            job_id=job_id,
            storage_path=request.storage_path,
            enable_jet_cut=request.enable_jet_cut,
            enable_subtitles=request.enable_subtitles,
            user_id=request.user_id,
        )

        logger.info(f"モードBジョブ開始: {job_id} 素材='{request.storage_path}'")

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
            created_at=job.get("created_at"),
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
        engine = ResearchEngine(gemini_api_key=request.gemini_api_key)
        result = await engine.analyze_trend(request.keyword)
        
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
async def download_video(job_id: str):
    """完成動画のダウンロードURL（署名付き）を返す"""
    from fastapi.responses import RedirectResponse
    try:
        job = firestore.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="ジョブが見つかりません")
        if job.get("status") != "completed":
            raise HTTPException(status_code=400, detail="動画がまだ完成していません")

        storage_url = job.get("storage_url")
        if storage_url:
            return RedirectResponse(url=storage_url)

        raise HTTPException(status_code=404, detail="動画ファイルが見つかりません")
    except HTTPException:
        raise
    except Exception as e:
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
    gemini_api_key: str,
    pexels_api_key: str = "",
    tts_engine: str = "edge",
    voice_name: str = "nanami",
    speaking_rate: float = 1.0,
    google_tts_key: str = "",
    elevenlabs_key: str = "",
    aivis_key: str = "",
    script_data: dict = None,
    auto_post: bool = False,
):
    """モードAの処理パイプライン全体を実行"""
    processor = ModeAProcessor(
        firestore, storage,
        gemini_api_key=gemini_api_key,
        pexels_api_key=pexels_api_key,
        tts_engine=tts_engine,
        voice_name=voice_name,
        speaking_rate=speaking_rate,
        google_tts_key=google_tts_key,
        elevenlabs_key=elevenlabs_key,
        aivis_key=aivis_key
    )
    try:
        firestore.update_job(job_id, status="processing", progress=5, message="処理を開始しています...")

        # 1. 台本生成 (script_dataがあればスキップ)
        if script_data:
            firestore.update_job(job_id, progress=20, message="提供された台本を読み込み中...")
        else:
            firestore.update_job(job_id, progress=10, message="Geminiで台本を生成中...")
            script_data = await processor.generate_script(theme, style, duration)
            firestore.update_job(job_id, progress=30, message="台本生成完了")

        # 2. 音声合成 (30%)
        firestore.update_job(job_id, progress=30, message="音声を合成中...")
        audio_path = await processor.synthesize_audio(script_data, job_id)

        # 3. 画像素材生成 (50%)
        firestore.update_job(job_id, progress=50, message="画像素材を生成中...")
        image_paths = await processor.generate_visuals(script_data, job_id)

        # 4. 動画合成 (70%)
        firestore.update_job(job_id, progress=70, message="動画を合成中...")
        video_path = await processor.compose_video(
            script_data, audio_path, image_paths, job_id, duration
        )

        # 5. Cloud Storageにアップロード (85%)
        firestore.update_job(job_id, progress=85, message="動画をアップロード中...")
        storage_url = storage.upload_file(
            video_path,
            f"outputs/{user_id}/{job_id}/output.mp4"
        )

        # 6. YouTubeに投稿 (95%)
        firestore.update_job(job_id, progress=95, message="YouTubeに投稿中...")
        youtube_url = youtube.upload_video(
            video_path=str(video_path),
            title=f"{theme} | KIMIDORI Movie Auto",
            description=f"テーマ「{theme}」から自動生成された動画です。\n\n{script_data.get('description', '')}",
            tags=script_data.get("tags", ["自動生成", "AI"]),
            privacy_status="private",  # 非公開で投稿
        )

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
):
    """モードBの処理パイプライン全体を実行"""
    processor = ModeBProcessor(firestore, storage)
    try:
        firestore.update_job(job_id, status="processing", progress=5, message="処理を開始しています...")

        # 1. 素材動画をダウンロード (10%)
        firestore.update_job(job_id, progress=10, message="素材動画をダウンロード中...")
        source_video_path = storage.download_file(storage_path, config.TMP_DIR / job_id / "source.mp4")

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
        firestore.update_job(job_id, progress=85, message="完成動画をアップロード中...")
        storage_url = storage.upload_file(
            final_video_path,
            f"outputs/{user_id}/{job_id}/output.mp4"
        )

        # 6. YouTubeに投稿 (95%)
        firestore.update_job(job_id, progress=95, message="YouTubeに投稿中...")
        youtube_url = youtube.upload_video(
            video_path=str(final_video_path),
            user_id=user_id,
            title=f"自動編集動画 | KIMIDORI Movie Auto",
            description="自動編集（ジェットカット＋テロップ付与）された動画です。",
            tags=["自動編集", "ジェットカット", "テロップ"],
            privacy_status="private",
        )

        # 7. 完了 (100%)
        firestore.update_job(
            job_id,
            status="completed",
            progress=100,
            message="処理が完了しました！",
            youtube_url=youtube_url,
            storage_url=storage_url,
        )
        logger.info(f"モードBジョブ完了: {job_id} → {youtube_url}")

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

