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

    def optimize_video_ratio(self, video_ratio: float = 0.2):
        """
        コスト最適化: 全カットのうち指定比率（デフォルト約20% = 1/5）のみを type: 'video' に設定し、
        残りを type: 'image'（Ken Burns静止画演出）に配分
        """
        total = len(self.scenes)
        if total == 0:
            return
        video_count = max(1, int(total * video_ratio))
        # 冒頭、各章の開始シーン、盛り上がりシーンにvideoを優先配分
        step = max(1, total // video_count)
        for i, scene in enumerate(self.scenes):
            if i % step == 0 and video_count > 0:
                scene.type = "video"
                video_count -= 1
            else:
                scene.type = "image"
