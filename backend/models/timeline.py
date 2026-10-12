"""
KIMIDORI Movie Auto - タイムラインJSON（設計書モデル）
長尺動画（15〜20分 / 120〜180カット）および自動動画編集の中間データ表現・コスト最適化・単体リカバリー機構
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import uuid
import datetime


class SubtitleItem(BaseModel):
    """字幕テロップ情報"""
    start: float
    end: float
    text: str


class CameraWork(BaseModel):
    """Ken Burnsカメラワーク効果（remotion準拠）"""
    effect: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right", "ken_burns"] = "ken_burns"
    start_scale: float = 1.0
    end_scale: float = 1.15
    pan_direction: Literal["center", "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"] = "center"


class BRollMaterial(BaseModel):
    """Pexels等の文脈・感情連動Bロール素材"""
    source: Literal["pexels", "local", "ai_generated"] = "pexels"
    material_type: Literal["video", "image"] = "video"
    query: str = ""
    emotion_tag: str = ""
    media_url: Optional[str] = None
    local_path: Optional[str] = None
    start_offset: float = 0.0
    duration: float = 4.0
    transition_in: Literal["fade", "dissolve", "cut"] = "dissolve"
    transition_out: Literal["fade", "dissolve", "cut"] = "dissolve"


class TimelineScene(BaseModel):
    """シーン（カット）単位の中間データモデル"""
    scene_id: int
    cut_key: str = ""
    # コスト最適化: 全180カット中 約1/5(約36シーン)のみ type: 'video'、残りは type: 'image'
    type: Literal["image", "video"] = "image"
    status: Literal["pending", "generating", "generated", "failed"] = "pending"
    duration: float = 5.0
    speaker: str = "ナレーション"
    narration: str = ""
    description: str = ""
    character_prompt: str = ""
    location_prompt: str = ""
    bgm_tag: str = "neutral"
    camera_work: CameraWork = Field(default_factory=CameraWork)
    b_roll: Optional[BRollMaterial] = None
    audio_path: Optional[str] = None
    base_image_path: Optional[str] = None
    overlay_image_path: Optional[str] = None
    rendered_clip_path: Optional[str] = None
    subtitles: List[SubtitleItem] = Field(default_factory=list)
    error_message: Optional[str] = None


class TimelineProject(BaseModel):
    """プロジェクト全体のタイムライン設計書"""
    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    theme: str = ""
    genre: str = "story"
    total_minutes: float = 15.0
    total_duration: float = 0.0
    current_step: int = 1
    total_steps: int = 5
    status: Literal["draft", "processing", "completed", "failed"] = "draft"
    characters: List[Dict[str, Any]] = Field(default_factory=list)
    scenes: List[TimelineScene] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def get_failed_scenes(self) -> List[TimelineScene]:
        """失敗したシーンのみを抽出（単体再生成・リカバリー用）"""
        return [s for s in self.scenes if s.status == "failed"]

    def reset_failed_scenes_to_pending(self):
        """失敗したシーンのステータスをpendingにリセット"""
        for s in self.scenes:
            if s.status == "failed":
                s.status = "pending"
                s.error_message = None

    def mark_scene_status(self, scene_id: int, status: Literal["pending", "generating", "generated", "failed"], error: Optional[str] = None):
        """指定シーンのステータスを更新"""
        for s in self.scenes:
            if s.scene_id == scene_id:
                s.status = status
                if error:
                    s.error_message = error
                break
        self.updated_at = datetime.datetime.utcnow().isoformat()

    def optimize_video_ratio(self, video_ratio: float = 0.25):
        """
        ハイブリッド動画生成コスト最適化:
        導入（冒頭）・各章の開始カット・クライマックス（盛り上がり/epic/終盤）の重要カットを type: 'video'（AIアニメーション動画）に設定し、
        通常の会話・解説カットを type: 'image'（キャラ固定静止画 ＋ カメラワークパン/ズーム ＋ セリフ浮き出し演出）に配分する。
        """
        total = len(self.scenes)
        if total == 0:
            return
        max_video = max(2, int(total * video_ratio))
        used = 0
        camera_cycle = ["zoom_in", "pan_right", "pan_left", "zoom_out"]

        for i, scene in enumerate(self.scenes):
            is_intro = (i == 0)
            is_chapter_open = scene.cut_key.endswith("_cut1")
            is_climax = (i == total - 1) or (scene.bgm_tag in ("epic", "suspense") and i >= int(total * 0.65))
            explicit_video = (scene.type == "video")

            if (is_intro or is_chapter_open or is_climax or explicit_video) and used < max_video:
                scene.type = "video"
                used += 1
            else:
                scene.type = "image"

            if scene.camera_work.effect in ("ken_burns", "none", ""):
                scene.camera_work.effect = camera_cycle[i % len(camera_cycle)]  # type: ignore

        # まだ枠が余っていれば均等ステップで重要箇所に配分
        if used < max_video and total > 3:
            step = max(2, total // max(1, (max_video - used + 1)))
            for i, scene in enumerate(self.scenes):
                if scene.type != "video" and i % step == 0 and used < max_video:
                    scene.type = "video"
                    used += 1
