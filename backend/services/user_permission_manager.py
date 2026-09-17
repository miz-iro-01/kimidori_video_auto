"""
KIMIDORI Movie Auto - ユーザー権限・プラン制御および設定保存マネージャー
無料会員（指定BGM固定・ロゴ表示）および有料サブスク会員（完全自由・ロゴ非表示）の機能制限・権限判定を行う
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from services.firestore_service import FirestoreService

logger = logging.getLogger(__name__)


class PlanType(str, Enum):
    FREE = "free"
    PRO = "pro"


class FeatureName(str, Enum):
    SHORT_VIDEO_CREATE = "short_video_create"
    AUTO_EDITING = "auto_editing"
    LONG_VIDEO_CREATE = "long_video_create"
    MANGA_LONG_VIDEO_CREATE = "manga_long_video_create"
    MANGA_TO_SHORT = "manga_to_short"
    THUMBNAIL_CREATE = "thumbnail_create"
    YOUTUBE_AUTO_POST = "youtube_auto_post"
    HIGH_QUALITY_VOICE = "high_quality_voice"


# 基本（無料会員）で利用可能な音声モデル一覧
BASIC_VOICE_MODELS = ["nanami", "keita", "edge_default"]

# 有料会員が利用可能な拡張音声モデル一覧
PRO_VOICE_MODELS = [
    "nanami", "keita", "edge_default",
    "google_standard", "google_wavenet",
    "elevenlabs_pro", "aivis_premium"
]


class UserPermissionManager:
    """
    ユーザーの会員区分（無料/有料サブスク）および各種機能の利用権限を管理するクラス
    """

    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        self.firestore = firestore_service or FirestoreService()

    def get_user_plan(self, user_id: str) -> Dict[str, Any]:
        """
        ユーザーのプラン情報をFirestoreから取得する（存在しない場合はデフォルトで無料会員）
        """
        if not user_id:
            return {"plan": PlanType.FREE, "is_pro": False, "expire_date": None}

        try:
            # Firestoreの 'users' コレクションを取得
            doc = self.firestore.db.collection("users").document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                plan = data.get("plan", PlanType.FREE)
                expire_str = data.get("subscription_expire_date")
                
                # 有効期限のチェック
                is_pro = (plan == PlanType.PRO)
                if is_pro and expire_str:
                    try:
                        exp_dt = datetime.fromisoformat(expire_str)
                        if datetime.now() > exp_dt:
                            logger.info(f"User {user_id} PRO subscription expired on {expire_str}")
                            is_pro = False
                            plan = PlanType.FREE
                    except Exception:
                        pass

                return {
                    "plan": plan,
                    "is_pro": is_pro,
                    "expire_date": expire_str
                }
        except Exception as e:
            logger.warning(f"Failed to fetch user plan for {user_id}: {e}")

        # デフォルトは無料会員
        return {"plan": PlanType.FREE, "is_pro": False, "expire_date": None}

    def update_user_plan(
        self,
        user_id: str,
        plan: Union[PlanType, str],
        expire_date: Optional[str] = None
    ) -> bool:
        """
        ユーザーの会員プランを更新・保存する
        """
        if not user_id:
            raise ValueError("user_id は必須です。")

        plan_str = str(plan.value if isinstance(plan, PlanType) else plan).lower()

        data = {
            "plan": plan_str,
            "updated_at": datetime.now().isoformat(),
        }
        if expire_date:
            data["subscription_expire_date"] = expire_date

        try:
            self.firestore.db.collection("users").document(user_id).set(data, merge=True)
            logger.info(f"UserPermissionManager: Updated plan for user {user_id} to '{plan_str}'")
            return True
        except Exception as e:
            logger.error(f"Failed to update plan for user {user_id}: {e}")
            return False

    def check_feature_access(self, user_id: str, feature: Union[FeatureName, str]) -> Dict[str, Any]:
        """
        指定された機能に対するユーザーの利用アクセス権限および制限条件を判定する

        Returns:
            Dict containing:
                - allowed (bool): 利用可否
                - watermark_required (bool): ロゴ表示が必須かどうか
                - custom_bgm_allowed (bool): BGMの自由カスタムが可能かどうか
                - allowed_voice_models (List[str]): 使用可能なナレーション声色
                - reason (str): 判定理由メッセージ
        """
        user_info = self.get_user_plan(user_id)
        is_pro = user_info["is_pro"]
        feat_str = str(feature.value if isinstance(feature, FeatureName) else feature).lower()

        # 有料会員はすべての機能が利用可能・ロゴ非表示・カスタムBGM自由
        if is_pro:
            return {
                "allowed": True,
                "watermark_required": False,
                "custom_bgm_allowed": True,
                "allowed_voice_models": PRO_VOICE_MODELS,
                "reason": "有料サブスク会員: 全機能利用可能（ロゴ非表示・BGM自由変更）"
            }

        # --- 無料会員の機能別判定 ---
        if feat_str == FeatureName.SHORT_VIDEO_CREATE.value:
            return {
                "allowed": True,
                "watermark_required": True,       # ロゴ表示必須
                "custom_bgm_allowed": False,      # TuneCore登録BGM固定
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "無料会員: ショート動画作成利用可能（指定BGM固定・ロゴ表示あり）"
            }

        elif feat_str == FeatureName.LONG_VIDEO_CREATE.value:
            return {
                "allowed": True,
                "watermark_required": True,       # ロゴ表示必須
                "custom_bgm_allowed": False,      # 感情タグ別TuneCore登録BGM割り当て固定
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "無料会員: 長尺動画作成利用可能（シーン別TuneCore指定BGM固定・ロゴ表示あり）"
            }

        elif feat_str in [
            FeatureName.AUTO_EDITING.value,
            FeatureName.MANGA_LONG_VIDEO_CREATE.value,
            FeatureName.MANGA_TO_SHORT.value,
            FeatureName.THUMBNAIL_CREATE.value,
            FeatureName.YOUTUBE_AUTO_POST.value
        ]:
            return {
                "allowed": False,
                "watermark_required": True,
                "custom_bgm_allowed": False,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": f"無料会員は '{feat_str}' 機能を利用できません。有料サブスク登録が必要です。"
            }

        elif feat_str == FeatureName.HIGH_QUALITY_VOICE.value:
            return {
                "allowed": False,
                "watermark_required": True,
                "custom_bgm_allowed": False,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "無料会員は基本音声のみ利用可能です。高クオリティ音声は有料サブスク会員限定です。"
            }

        return {
            "allowed": False,
            "watermark_required": True,
            "custom_bgm_allowed": False,
            "allowed_voice_models": BASIC_VOICE_MODELS,
            "reason": "未定義の機能権限要求です。"
        }

    def save_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """
        ユーザーのカスタムBGM割り当てやデフォルト設定を保存する
        """
        if not user_id:
            return False

        try:
            self.firestore.db.collection("user_settings").document(user_id).set(settings, merge=True)
            logger.info(f"UserPermissionManager: Saved settings for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save settings for user {user_id}: {e}")
            return False

    def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """
        ユーザーのカスタム設定を取得する
        """
        if not user_id:
            return {}

        try:
            doc = self.firestore.db.collection("user_settings").document(user_id).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            logger.warning(f"Failed to fetch settings for user {user_id}: {e}")
        return {}
