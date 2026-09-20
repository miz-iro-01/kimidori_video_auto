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


import uuid

ADMIN_EMAILS = {"oumaumauma32@gmail.com", "sl0wmugi9@gmail.com"}


class PlanType(str, Enum):
    FREE = "free"
    PRO = "pro"
    ADMIN = "admin"


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
    ユーザーの会員区分（無料/有料サブスク/管理者）および各種機能の利用権限を管理するクラス
    """

    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        self.firestore = firestore_service or FirestoreService()

    def get_user_plan(self, user_id: str) -> Dict[str, Any]:
        """
        ユーザーのプラン情報をFirestoreから取得する（管理者アカウントは常時最上位権限を保証）
        """
        if not user_id:
            return {"plan": PlanType.FREE, "role": "user", "is_pro": False, "is_admin": False, "expire_date": None}

        # 1. 予約済み管理者メールアドレス・UIDの即時フル権限判定
        if user_id in ADMIN_EMAILS or user_id in ["admin_ouma_uid", "admin_mugi_uid"]:
            return {
                "plan": PlanType.ADMIN,
                "role": "admin",
                "is_pro": True,
                "is_admin": True,
                "expire_date": None,
                "email": user_id if "@" in user_id else ("oumaumauma32@gmail.com" if "ouma" in user_id else "sl0wmugi9@gmail.com")
            }

        try:
            # Firestoreの 'users' コレクションを取得
            doc = self.firestore.db.collection("users").document(user_id).get()
            if not doc.exists and "@" in user_id:
                # メールアドレスで検索
                query_res = list(self.firestore.db.collection("users").where("email", "==", user_id).limit(1).stream())
                if query_res:
                    doc = query_res[0]

            if doc.exists:
                data = doc.to_dict()
                email = data.get("email", "")
                plan = data.get("plan", PlanType.FREE)
                role = data.get("role", "user")
                expire_str = data.get("subscription_expire_date")

                # 管理者メールまたはロール判定
                is_admin = (email in ADMIN_EMAILS or role == "admin" or plan == PlanType.ADMIN)
                if is_admin:
                    return {
                        "plan": PlanType.ADMIN,
                        "role": "admin",
                        "is_pro": True,
                        "is_admin": True,
                        "expire_date": None,
                        "email": email
                    }

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
                    "role": role,
                    "is_pro": is_pro,
                    "is_admin": False,
                    "expire_date": expire_str,
                    "email": email
                }
        except Exception as e:
            logger.warning(f"Failed to fetch user plan for {user_id}: {e}")

        # デフォルトは無料会員
        return {"plan": PlanType.FREE, "role": "user", "is_pro": False, "is_admin": False, "expire_date": None}

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
        管理者・Pro会員は全機能が無制限で解放される。
        """
        user_info = self.get_user_plan(user_id)
        is_admin = user_info.get("is_admin", False)
        is_pro = user_info.get("is_pro", False) or is_admin
        feat_str = str(feature.value if isinstance(feature, FeatureName) else feature).lower()

        # 管理者および有料会員はすべての機能が利用可能・ロゴ非表示・カスタムBGM自由
        if is_admin:
            return {
                "allowed": True,
                "watermark_required": False,
                "custom_bgm_allowed": True,
                "allowed_voice_models": PRO_VOICE_MODELS,
                "reason": "システム管理者: 全機能無制限利用可能（完全解放・ロゴ非表示）"
            }

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

    def list_users(self) -> List[Dict[str, Any]]:
        """全ユーザーのリストを取得（管理画面用）。Firestoreに存在しないデフォルト管理者も自動補完"""
        users = []
        seen_emails = set()

        try:
            docs = self.firestore.db.collection("users").stream()
            for doc in docs:
                data = doc.to_dict()
                u_id = doc.id
                email = data.get("email", u_id if "@" in u_id else "")
                plan = data.get("plan", PlanType.FREE)
                role = data.get("role", "admin" if email in ADMIN_EMAILS else "user")

                # 管理者アカウントの強制上書き
                if email in ADMIN_EMAILS or u_id in ["admin_ouma_uid", "admin_mugi_uid"]:
                    plan = PlanType.ADMIN
                    role = "admin"

                user_obj = {
                    "user_id": u_id,
                    "email": email or u_id,
                    "plan": plan,
                    "role": role,
                    "status": data.get("status", "active"),
                    "notes": data.get("notes", ""),
                    "created_at": data.get("created_at", datetime.now().isoformat()),
                    "updated_at": data.get("updated_at", datetime.now().isoformat()),
                    "subscription_expire_date": data.get("subscription_expire_date", None)
                }
                users.append(user_obj)
                if email:
                    seen_emails.add(email)
        except Exception as e:
            logger.warning(f"Error listing users from Firestore: {e}")

        # 管理者アカウント（oumaumauma32@gmail.com 等）がDBにまだ存在しない場合は自動補完して保存
        default_admins = [
            {"user_id": "admin_ouma_uid", "email": "oumaumauma32@gmail.com", "notes": "システム最高管理者 (オーナー)"},
            {"user_id": "admin_mugi_uid", "email": "sl0wmugi9@gmail.com", "notes": "共同開発・システム管理者"}
        ]
        for adm in default_admins:
            if adm["email"] not in seen_emails:
                adm_data = {
                    "user_id": adm["user_id"],
                    "email": adm["email"],
                    "plan": PlanType.ADMIN,
                    "role": "admin",
                    "status": "active",
                    "notes": adm["notes"],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                users.insert(0, adm_data)
                seen_emails.add(adm["email"])
                try:
                    self.firestore.db.collection("users").document(adm["user_id"]).set(adm_data, merge=True)
                except Exception:
                    pass

        return users

    def create_user(
        self,
        email: str,
        plan: str = "free",
        role: str = "user",
        status: str = "active",
        notes: str = ""
    ) -> Dict[str, Any]:
        """管理者が手動で新規ユーザーを登録する"""
        if not email or "@" not in email:
            raise ValueError("有効なメールアドレスを入力してください。")

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        plan_val = plan.lower()
        if email in ADMIN_EMAILS or role == "admin" or plan_val == "admin":
            plan_val = PlanType.ADMIN
            role = "admin"

        user_data = {
            "user_id": user_id,
            "email": email,
            "plan": plan_val,
            "role": role,
            "status": status,
            "notes": notes,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self.firestore.db.collection("users").document(user_id).set(user_data)
        return user_data

    def update_user(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """管理者が既存ユーザーのプラン、権限、ステータス、メモを更新する"""
        doc_ref = self.firestore.db.collection("users").document(user_id)
        doc = doc_ref.get()
        if not doc.exists:
            # Check by email
            matching = list(self.firestore.db.collection("users").where("email", "==", user_id).limit(1).stream())
            if matching:
                doc_ref = self.firestore.db.collection("users").document(matching[0].id)
                user_id = matching[0].id
                doc = doc_ref.get()

        curr_data = doc.to_dict() if doc.exists else {"user_id": user_id}

        allowed_keys = ["plan", "role", "status", "notes", "subscription_expire_date"]
        clean_updates = {k: v for k, v in updates.items() if k in allowed_keys and v is not None}
        clean_updates["updated_at"] = datetime.now().isoformat()

        # オーナー保護: oumaumauma32@gmail.com の管理者権限降格を防止
        email = curr_data.get("email", "")
        if email in ADMIN_EMAILS or user_id in ["admin_ouma_uid", "admin_mugi_uid"]:
            clean_updates["role"] = "admin"
            clean_updates["plan"] = PlanType.ADMIN
            clean_updates["status"] = "active"

        doc_ref.set(clean_updates, merge=True)
        curr_data.update(clean_updates)
        return curr_data

    def delete_user(self, user_id: str) -> bool:
        """ユーザーを削除する（オーナーは削除不可）"""
        doc_ref = self.firestore.db.collection("users").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("email") in ADMIN_EMAILS or user_id in ["admin_ouma_uid", "admin_mugi_uid"]:
                raise PermissionError("最高管理者のアカウントは削除できません。")
            doc_ref.delete()
            return True
        return False

