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

ADMIN_EMAILS = {"oumaumauma32@gmail.com"}
MASTER_ADMIN_EMAILS = {"oumaumauma32@gmail.com"}


class PlanType(str, Enum):
    FREE_TRIAL = "free_trial"
    STANDARD = "standard"
    PREMIUM = "premium"
    MASTER = "master"
    BYOG_PURCHASED = "byog_purchased"
    ADMIN = "admin"
    # 後方互換性エイリアス
    FREE = "free_trial"
    LITE = "standard"
    PRO = "premium"


class FeatureName(str, Enum):
    SHORT_VIDEO_CREATE = "short_video_create"
    AUTO_EDITING = "auto_editing"
    LONG_VIDEO_CREATE = "long_video_create"
    MANGA_LONG_VIDEO_CREATE = "manga_long_video_create"
    MANGA_TO_SHORT = "manga_to_short"
    THUMBNAIL_CREATE = "thumbnail_create"
    YOUTUBE_AUTO_POST = "youtube_auto_post"
    HIGH_QUALITY_VOICE = "high_quality_voice"


# 基本（無料体験枠・スタンダードプラン）で利用可能な音声エンジン・モデル一覧
BASIC_VOICE_MODELS = ["nanami", "keita", "edge_default", "edge", "voicevox", "gtts", "sharevox", "coeiroink", "aivis"]

# 有料会員（プレミアム/マスター/買い切りBYOG）が利用可能な拡張音声エンジン・モデル一覧
PRO_VOICE_MODELS = [
    "nanami", "keita", "edge_default", "edge", "voicevox", "gtts",
    "oss_elevenlabs", "oss_custom", "voxcpm",
    "google_standard", "google_wavenet", "google",
    "elevenlabs_pro", "elevenlabs", "aivis_premium",
    "openai", "azure", "amazon_polly", "ondoku", "coefont"
]


class UserPermissionManager:
    """
    ユーザーの会員区分（free_trial/standard/premium/master/byog_purchased/管理者）および各種機能の利用権限を管理するクラス
    """

    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        self.firestore = firestore_service or FirestoreService()

    def is_colab_shared_user(self, email: str, user_id: str = "") -> bool:
        """
        「家族・共有Colab利用メンバー」判定:
        事前登録リスト（Firestoreの allowed_colab_users コレクション、ドキュメント、または users テーブルの can_use_shared_colab / allowed_colab 属性）
        に登録されたメールアドレスと一致する場合のみ、Trueを返却する。
        """
        if not email and not user_id:
            return False

        target_email = (email or "").strip().lower()
        target_uid = (user_id or "").strip()

        # マスター管理者は当然利用可能
        if target_email in MASTER_ADMIN_EMAILS:
            return True

        try:
            # 1. Firestore 'allowed_colab_users' コレクション照会 (ID=email または emailフィールド一致)
            if target_email:
                doc = self.firestore.db.collection("allowed_colab_users").document(target_email).get()
                if doc.exists:
                    return True
                # クエリ照会
                matches = list(self.firestore.db.collection("allowed_colab_users").where("email", "==", target_email).limit(1).stream())
                if matches:
                    return True

            # 2. Firestore 'system_settings/allowed_colab_users' リスト照会
            sys_doc = self.firestore.db.collection("system_settings").document("allowed_colab_users").get()
            if sys_doc.exists:
                allowed_list = sys_doc.to_dict().get("emails", [])
                if any(target_email == str(e).strip().lower() for e in allowed_list):
                    return True

            # 3. users コレクション内の個別フラグ判定
            lookup_id = target_uid or target_email
            user_doc = self.firestore.db.collection("users").document(lookup_id).get()
            if user_doc.exists:
                u_data = user_doc.to_dict()
                if u_data.get("can_use_shared_colab") or u_data.get("allowed_colab") or u_data.get("colab_shared"):
                    return True

        except Exception as e:
            logger.warning(f"Error checking is_colab_shared_user for {target_email}: {e}")

        return False

    def get_user_plan(self, user_id: str, byog_enabled: bool = False) -> Dict[str, Any]:
        """
        ユーザーのプラン情報をFirestoreから取得する。
        - マスター管理者（oumaumauma32@gmail.com）のみ最上位管理者権限を付与
        - サロンAdminフラグによるマスター昇格は完全廃止
        - 事前登録Colab共有ユーザーにはBYOG無制限モードを適用
        """
        if not user_id:
            return {
                "plan": PlanType.FREE_TRIAL.value,
                "role": "user",
                "is_pro": bool(byog_enabled),
                "is_admin": False,
                "byog_enabled": bool(byog_enabled),
                "can_use_premium_tts": bool(byog_enabled),
                "can_direct_upload_youtube": bool(byog_enabled),
                "can_use_studio": bool(byog_enabled),
                "expire_date": None
            }

        clean_id = str(user_id).strip().lower()

        # 1. マスター管理者（oumaumauma32@gmail.com のみ厳格判定）
        if clean_id in MASTER_ADMIN_EMAILS or clean_id == "admin_ouma_uid":
            return {
                "plan": PlanType.ADMIN.value,
                "role": "admin",
                "is_pro": True,
                "is_admin": True,
                "byog_enabled": True,
                "can_use_shared_colab": True,
                "can_use_premium_tts": True,
                "can_direct_upload_youtube": True,
                "can_use_studio": True,
                "expire_date": None,
                "email": "oumaumauma32@gmail.com"
            }

        try:
            # Firestoreの 'users' コレクションを取得
            doc = self.firestore.db.collection("users").document(user_id).get()
            if not doc.exists and "@" in user_id:
                query_res = list(self.firestore.db.collection("users").where("email", "==", user_id).limit(1).stream())
                if query_res:
                    doc = query_res[0]

            if doc.exists:
                data = doc.to_dict()
                email = str(data.get("email", "")).strip().lower()
                raw_plan = str(data.get("plan", PlanType.FREE_TRIAL.value)).strip().lower()
                role = "user"  # 一般ユーザーに固定（マスター管理者以外はadmin昇格不可）
                expire_str = data.get("subscription_expire_date")

                # マスター管理者チェック
                if email in MASTER_ADMIN_EMAILS:
                    return {
                        "plan": PlanType.ADMIN.value,
                        "role": "admin",
                        "is_pro": True,
                        "is_admin": True,
                        "byog_enabled": True,
                        "can_use_shared_colab": True,
                        "can_use_premium_tts": True,
                        "can_direct_upload_youtube": True,
                        "can_use_studio": True,
                        "expire_date": None,
                        "email": email
                    }

                # 家族・共有Colab利用メンバー判定
                is_shared_colab = self.is_colab_shared_user(email, user_id=user_id)

                # プランキーの統一マッピング
                plan_map = {
                    "free": PlanType.FREE_TRIAL.value,
                    "free_trial": PlanType.FREE_TRIAL.value,
                    "lite": PlanType.STANDARD.value,
                    "standard": PlanType.STANDARD.value,
                    "pro": PlanType.PREMIUM.value,
                    "premium": PlanType.PREMIUM.value,
                    "master": PlanType.MASTER.value,
                    "byog_purchased": PlanType.BYOG_PURCHASED.value
                }
                unified_plan = plan_map.get(raw_plan, PlanType.FREE_TRIAL.value)

                # 有効期限チェック
                if unified_plan in (PlanType.PREMIUM.value, PlanType.MASTER.value) and expire_str:
                    try:
                        exp_dt = datetime.fromisoformat(expire_str)
                        if datetime.now() > exp_dt:
                            logger.info(f"User {user_id} subscription expired on {expire_str}")
                            unified_plan = PlanType.FREE_TRIAL.value
                    except Exception:
                        pass

                # 機能利用権限の算出
                # - premium, master, byog_purchased: Pro相当機能（スタジオ・高品質TTS・YT直接投稿）解放
                # - standard: スタジオ不可、無料TTSのみ、MP4保存のみ
                # - free_trial: 簡易ショートのみ、スタジオ不可、BGM固定
                # - is_shared_colab または byog_enabled 有効時: BYOG/Colab無制限モード適用
                has_pro_features = (
                    unified_plan in (PlanType.PREMIUM.value, PlanType.MASTER.value, PlanType.BYOG_PURCHASED.value)
                    or bool(byog_enabled)
                    or is_shared_colab
                )
                can_use_studio = (
                    unified_plan in (PlanType.PREMIUM.value, PlanType.MASTER.value, PlanType.BYOG_PURCHASED.value)
                    or bool(byog_enabled)
                    or is_shared_colab
                )

                return {
                    "plan": unified_plan,
                    "role": "user",
                    "is_pro": has_pro_features,
                    "is_admin": False,
                    "byog_enabled": bool(byog_enabled or is_shared_colab or unified_plan == PlanType.BYOG_PURCHASED.value),
                    "can_use_shared_colab": is_shared_colab,
                    "can_use_premium_tts": has_pro_features,
                    "can_direct_upload_youtube": has_pro_features,
                    "can_use_studio": can_use_studio,
                    "expire_date": expire_str,
                    "email": email
                }
        except Exception as e:
            logger.warning(f"Failed to fetch user plan for {user_id}: {e}")

        # デフォルトは無料体験枠（BYOG有効またはColab共有メンバー時は解放）
        is_shared_colab = self.is_colab_shared_user("", user_id=user_id)
        effective_byog = bool(byog_enabled or is_shared_colab)
        return {
            "plan": PlanType.FREE_TRIAL.value,
            "role": "user",
            "is_pro": effective_byog,
            "is_admin": False,
            "byog_enabled": effective_byog,
            "can_use_shared_colab": is_shared_colab,
            "can_use_premium_tts": effective_byog,
            "can_direct_upload_youtube": effective_byog,
            "can_use_studio": effective_byog,
            "expire_date": None
        }

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

    def check_feature_access(
        self,
        user_id: str,
        feature: Union[FeatureName, str],
        byog_enabled: bool = False
    ) -> Dict[str, Any]:
        """
        指定された機能に対するユーザーの利用アクセス権限および制限条件を判定する
        管理者・Pro会員・BYOGモードは全機能（高品質OSS TTS、YouTube直接OAuth投稿・予約投稿）が解放される。
        """
        user_info = self.get_user_plan(user_id, byog_enabled=byog_enabled)
        is_admin = user_info.get("is_admin", False)
        is_pro = user_info.get("is_pro", False) or is_admin or bool(byog_enabled)
        can_use_premium_tts = bool(user_info.get("can_use_premium_tts", is_pro))
        can_direct_upload_youtube = bool(user_info.get("can_direct_upload_youtube", is_pro))
        feat_str = str(feature.value if isinstance(feature, FeatureName) else feature).lower()

        if is_admin:
            return {
                "allowed": True,
                "watermark_required": False,
                "custom_bgm_allowed": True,
                "can_use_premium_tts": True,
                "can_direct_upload_youtube": True,
                "allowed_voice_models": PRO_VOICE_MODELS,
                "reason": "システム管理者: 全機能無制限利用可能（高品質OSS TTS・YouTube直接投稿解放）"
            }

        if is_pro:
            return {
                "allowed": True,
                "watermark_required": False,
                "custom_bgm_allowed": True,
                "can_use_premium_tts": True,
                "can_direct_upload_youtube": True,
                "allowed_voice_models": PRO_VOICE_MODELS,
                "reason": "Proプラン / BYOGモード: 全機能利用可能（高品質OSS TTS・YouTube直接OAuth投稿解放）"
            }

        # --- 無料体験枠 / スタンダードプラン相当の機能別判定 ---
        if feat_str == FeatureName.SHORT_VIDEO_CREATE.value:
            return {
                "allowed": True,
                "watermark_required": True,
                "custom_bgm_allowed": False,
                "can_use_premium_tts": False,
                "can_direct_upload_youtube": False,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "スタンダード/無料体験枠: 無料TTS（VOICEVOX / Edge-TTS）およびMP4ダウンロードのみ利用可能"
            }

        elif feat_str == FeatureName.LONG_VIDEO_CREATE.value:
            return {
                "allowed": True,
                "watermark_required": True,
                "custom_bgm_allowed": False,
                "can_use_premium_tts": False,
                "can_direct_upload_youtube": False,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "無料体験枠: 長尺動画作成利用可能（無料TTS・MP4ダウンロードのみ）"
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
                "can_use_premium_tts": can_use_premium_tts,
                "can_direct_upload_youtube": can_direct_upload_youtube,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": f"スタンダード/無料体験枠では '{feat_str}' 機能を利用できません。プレミアムプランまたはBYOG設定が必要です。"
            }

        elif feat_str == FeatureName.HIGH_QUALITY_VOICE.value:
            return {
                "allowed": False,
                "watermark_required": True,
                "custom_bgm_allowed": False,
                "can_use_premium_tts": False,
                "can_direct_upload_youtube": False,
                "allowed_voice_models": BASIC_VOICE_MODELS,
                "reason": "無料体験枠およびスタンダードプランは無料TTS（VOICEVOX / Edge-TTS）のみ利用可能です。高品質VoxCPM TTSはプレミアム/マスター/BYOG限定です。"
            }

        return {
            "allowed": False,
            "watermark_required": True,
            "custom_bgm_allowed": False,
            "can_use_premium_tts": False,
            "can_direct_upload_youtube": False,
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
        """全ユーザーのリストを取得（管理画面用）。マスター管理者は oumaumauma32@gmail.com のみ厳格設定"""
        users = []
        seen_emails = set()

        try:
            docs = self.firestore.db.collection("users").stream()
            for doc in docs:
                data = doc.to_dict()
                u_id = doc.id
                email = str(data.get("email", u_id if "@" in u_id else "")).strip().lower()
                plan = data.get("plan", PlanType.FREE_TRIAL.value)
                role = "admin" if email in MASTER_ADMIN_EMAILS else "user"

                # マスター管理者アカウントの強制上書き
                if email in MASTER_ADMIN_EMAILS or u_id == "admin_ouma_uid":
                    plan = PlanType.ADMIN.value
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

        # マスター管理者（oumaumauma32@gmail.com）がDBにまだ存在しない場合は自動補完
        if "oumaumauma32@gmail.com" not in seen_emails:
            adm_data = {
                "user_id": "admin_ouma_uid",
                "email": "oumaumauma32@gmail.com",
                "plan": PlanType.ADMIN.value,
                "role": "admin",
                "status": "active",
                "notes": "システム最高管理者 (オーナー)",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            users.insert(0, adm_data)
            try:
                self.firestore.db.collection("users").document("admin_ouma_uid").set(adm_data, merge=True)
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

