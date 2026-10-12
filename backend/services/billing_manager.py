"""
KIMIDORI Movie Auto - Stripe サブスクリプション & クレジット管理サービス
- プラン体系（ライト/プロ/プレミアム）と月次クレジット付与
- 追加クレジットチャージ（買い切り）
- Stripe Checkout Session 発行 & Webhook 処理
- 動画生成前のクレジット残高検証 & 減算処理
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import config
from services.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

# Stripe ライブラリの動的ロード（未インストール時でもダミー安全フォールバック）
try:
    import stripe
    if config.STRIPE_SECRET_KEY:
        stripe.api_key = config.STRIPE_SECRET_KEY
except ImportError:
    stripe = None
    logger.warning("stripe package is not installed. Stripe billing will run in local fallback mode.")


class BillingManager:
    """ユーザーの課金プラン、Stripe決済、およびクレジット残高を管理するサービス"""

    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        self.firestore = firestore_service or FirestoreService()
        self.secret_key = config.STRIPE_SECRET_KEY
        self.webhook_secret = config.STRIPE_WEBHOOK_SECRET

    def get_user_credit_balance(self, user_id: str) -> Dict[str, Any]:
        """ユーザーのクレジット残高およびプラン情報を取得"""
        if not user_id:
            return {"credits": 0, "plan": "free_trial", "unlimited": False}

        clean_id = (user_id or "").strip().lower()

        # マスター管理者（oumaumauma32@gmail.com のみ）
        if clean_id in ("oumaumauma32@gmail.com", "admin_ouma_uid"):
            return {
                "user_id": user_id,
                "credits": 999999,
                "plan": "admin",
                "unlimited": True,
                "plan_name": "マスター管理者 (無制限)"
            }

        try:
            doc = self.firestore.db.collection("users").document(user_id).get()
            if doc.exists:
                data = doc.to_dict()
                raw_plan = str(data.get("plan", "free_trial")).strip().lower()
                plan = config.resolve_plan_key(raw_plan)
                is_unlimited = plan in ("admin", "enterprise", "byog_purchased") or bool(data.get("can_use_shared_colab") or data.get("allowed_colab"))
                credits = 999999 if is_unlimited else int(data.get("credits", 30))  # 新規デフォルト30 pt
                plan_name = config.PLAN_PRICING.get(plan, {}).get("name", "無料体験プラン")
                return {
                    "user_id": user_id,
                    "credits": credits,
                    "plan": plan,
                    "unlimited": is_unlimited,
                    "plan_name": plan_name
                }
        except Exception as e:
            logger.warning(f"Failed to fetch credit balance for {user_id}: {e}")

        return {"user_id": user_id, "credits": 30, "plan": "free_trial", "unlimited": False, "plan_name": "無料体験プラン"}

    def check_and_deduct_credits(
        self,
        user_id: str,
        amount: int,
        description: str = "動画生成によるクレジット消費",
        byog_enabled: bool = False
    ) -> Dict[str, Any]:
        """
        動画生成前のクレジット検証および減算。
        BYOG（自前GPU/APIキー持ち込み）モード時はクレジット消費なし（0消費）で許可。
        """
        if byog_enabled:
            logger.info(f"User {user_id}: BYOG mode active -> 0 credits deducted.")
            return {"success": True, "deducted": 0, "remaining": 999999, "byog": True}

        balance_info = self.get_user_credit_balance(user_id)
        if balance_info.get("unlimited"):
            return {"success": True, "deducted": 0, "remaining": 999999, "unlimited": True}

        current_credits = balance_info.get("credits", 0)
        if current_credits < amount:
            logger.warning(f"Credit shortage for user {user_id}: required={amount}, available={current_credits}")
            return {
                "success": False,
                "error": "クレジット残高が不足しています",
                "required": amount,
                "available": current_credits,
                "shortage": amount - current_credits
            }

        new_credits = max(0, current_credits - amount)
        try:
            self.firestore.db.collection("users").document(user_id).set({
                "credits": new_credits,
                "updated_at": datetime.now().isoformat()
            }, merge=True)

            # 履歴ログの記録
            self.firestore.db.collection("credit_logs").document().set({
                "user_id": user_id,
                "amount": -amount,
                "balance_after": new_credits,
                "description": description,
                "created_at": datetime.now().isoformat()
            })
            logger.info(f"Deducted {amount} credits from user {user_id}. Remaining: {new_credits}")
        except Exception as e:
            logger.error(f"Failed to record credit deduction in Firestore: {e}")

        return {
            "success": True,
            "deducted": amount,
            "remaining": new_credits
        }

    def add_credits(self, user_id: str, amount: int, reason: str = "クレジット追加") -> int:
        """クレジットの加算（プラン契約、単発購入、ボーナス等）"""
        balance_info = self.get_user_credit_balance(user_id)
        current = balance_info.get("credits", 0)
        new_total = current + amount

        try:
            self.firestore.db.collection("users").document(user_id).set({
                "credits": new_total,
                "updated_at": datetime.now().isoformat()
            }, merge=True)

            self.firestore.db.collection("credit_logs").document().set({
                "user_id": user_id,
                "amount": amount,
                "balance_after": new_total,
                "description": reason,
                "created_at": datetime.now().isoformat()
            })
            logger.info(f"Added {amount} credits to user {user_id}. New balance: {new_total}")
        except Exception as e:
            logger.error(f"Failed to add credits for user {user_id}: {e}")

        return new_total

    def create_checkout_session(
        self,
        user_id: str,
        user_email: str,
        item_type: str,
        item_id: str,
        success_url: str,
        cancel_url: str
    ) -> Dict[str, Any]:
        """
        Stripe Checkout Session を発行。
        item_type: 'subscription' (プラン月額) または 'credit_pack' (クレジット追加チャージ)
        item_id: 'lite' | 'pro' | 'premium' または 'pack_small' | 'pack_medium' | 'pack_large'
        """
        if not stripe or not config.STRIPE_SECRET_KEY:
            logger.warning("Stripe key not configured. Returning simulated checkout URL.")
            return {
                "checkout_url": f"{success_url}?session_id=simulated_{item_id}_{int(datetime.now().timestamp())}",
                "simulated": True,
                "item_id": item_id
            }

        stripe.api_key = config.STRIPE_SECRET_KEY

        try:
            if item_type in ("one_time", "lifetime") or item_id == "byog_purchased":
                plan_info = config.PLAN_PRICING.get("byog_purchased", {})
                price_jpy = plan_info.get("price_jpy", 79800)

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="payment",
                    customer_email=user_email if "@" in user_email else None,
                    client_reference_id=user_id,
                    metadata={"user_id": user_id, "plan": "byog_purchased", "type": "byog_purchased"},
                    line_items=[{
                        "price_data": {
                            "currency": "jpy",
                            "product_data": {
                                "name": "KIMIDORI YouTube Auto 買い切り無制限プラン",
                                "description": "買い切り79,800円（クレジット0消費・無制限、自前環境セットアップガイド付属）"
                            },
                            "unit_amount": price_jpy
                        },
                        "quantity": 1
                    }],
                    success_url=success_url,
                    cancel_url=cancel_url
                )
                return {"checkout_url": session.url, "session_id": session.id}

            elif item_type == "subscription":
                plan_key = config.resolve_plan_key(item_id)
                plan_info = config.PLAN_PRICING.get(plan_key)
                if not plan_info:
                    raise ValueError(f"Unknown subscription plan: {item_id}")

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="subscription",
                    customer_email=user_email if "@" in user_email else None,
                    client_reference_id=user_id,
                    metadata={"user_id": user_id, "plan": plan_key, "type": "subscription"},
                    line_items=[{
                        "price_data": {
                            "currency": "jpy",
                            "product_data": {
                                "name": f"KIMIDORI YouTube Auto {plan_info['name']}",
                                "description": f"月額プラン（毎月{plan_info['monthly_credits']}クレジット付与）"
                            },
                            "unit_amount": plan_info["price_jpy"],
                            "recurring": {"interval": "month"}
                        },
                        "quantity": 1
                    }],
                    success_url=success_url,
                    cancel_url=cancel_url
                )
                return {"checkout_url": session.url, "session_id": session.id}

            elif item_type == "credit_pack":
                pack_info = config.CREDIT_PACKS.get(item_id)
                if not pack_info:
                    raise ValueError(f"Unknown credit pack: {item_id}")

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    mode="payment",
                    customer_email=user_email if "@" in user_email else None,
                    client_reference_id=user_id,
                    metadata={
                        "user_id": user_id,
                        "pack_id": item_id,
                        "credits": str(pack_info["credits"]),
                        "type": "credit_pack"
                    },
                    line_items=[{
                        "price_data": {
                            "currency": "jpy",
                            "product_data": {
                                "name": f"KIMIDORI {pack_info['name']}",
                                "description": f"動画生成クレジット {pack_info['credits']} pt チャージ"
                            },
                            "unit_amount": pack_info["price_jpy"]
                        },
                        "quantity": 1
                    }],
                    success_url=success_url,
                    cancel_url=cancel_url
                )
                return {"checkout_url": session.url, "session_id": session.id}
            else:
                raise ValueError(f"Invalid item_type: {item_type}")

        except Exception as e:
            logger.error(f"Failed to create Stripe checkout session: {e}")
            raise RuntimeError(f"Stripeチェックアウト作成エラー: {str(e)}")

    def handle_webhook_event(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Stripe Webhook イベントの検証とユーザーデータ・クレジット反映"""
        event = None
        if stripe and config.STRIPE_WEBHOOK_SECRET and sig_header:
            try:
                event = stripe.Webhook.construct_event(
                    payload, sig_header, config.STRIPE_WEBHOOK_SECRET
                )
            except Exception as e:
                logger.error(f"Webhook signature verification failed: {e}")
                raise ValueError("Webhook署名検証に失敗しました")
        else:
            try:
                event = json.loads(payload.decode("utf-8"))
            except Exception as e:
                raise ValueError(f"Invalid payload: {e}")

        event_type = event.get("type", "")
        data_object = event.get("data", {}).get("object", {})
        logger.info(f"Processing Stripe Webhook event: {event_type}")

        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            user_id = data_object.get("client_reference_id") or metadata.get("user_id")
            pay_type = metadata.get("type")

            if user_id:
                if pay_type == "byog_purchased":
                    self.update_user_byog_purchased(user_id)
                elif pay_type == "credit_pack":
                    credits = int(metadata.get("credits", 0))
                    if credits > 0:
                        self.add_credits(user_id, credits, reason=f"追加クレジットチャージ ({metadata.get('pack_id')})")
                elif pay_type == "subscription":
                    raw_plan = metadata.get("plan", "premium")
                    plan = config.resolve_plan_key(raw_plan)
                    monthly_credits = config.PLAN_PRICING.get(plan, {}).get("monthly_credits", 1000)
                    self.update_user_subscription(user_id, plan, monthly_credits)

        elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
            sub_status = data_object.get("status")
            user_id = data_object.get("metadata", {}).get("user_id")
            raw_plan = data_object.get("metadata", {}).get("plan", "premium")
            plan = config.resolve_plan_key(raw_plan)

            if user_id and sub_status in ("active", "trialing"):
                monthly_credits = config.PLAN_PRICING.get(plan, {}).get("monthly_credits", 1000)
                self.update_user_subscription(user_id, plan, monthly_credits)

        elif event_type == "customer.subscription.deleted":
            user_id = data_object.get("metadata", {}).get("user_id")
            if user_id:
                logger.info(f"Subscription canceled for user {user_id}. Downgrading to free_trial.")
                try:
                    self.firestore.db.collection("users").document(user_id).set({
                        "plan": "free_trial",
                        "subscription_status": "canceled",
                        "updated_at": datetime.now().isoformat()
                    }, merge=True)
                except Exception as e:
                    logger.error(f"Failed to update subscription status: {e}")

        return {"handled": True, "event_type": event_type}

    def update_user_byog_purchased(self, user_id: str):
        """買い切り無制限プラン（79,800円）の権限反映"""
        try:
            self.firestore.db.collection("users").document(user_id).set({
                "plan": "byog_purchased",
                "credits": 999999,
                "unlimited": True,
                "byog_enabled": True,
                "show_byog_setup_guide": True,
                "subscription_status": "lifetime",
                "updated_at": datetime.now().isoformat()
            }, merge=True)
            self.add_credits(user_id, 999999, reason="買い切り79,800円プラン（無制限）解放")
            logger.info(f"Updated user {user_id} to byog_purchased lifetime plan.")
        except Exception as e:
            logger.error(f"Failed to update user byog_purchased in Firestore: {e}")

    def update_user_subscription(self, user_id: str, plan: str, credits_to_grant: int):
        """サブスクリプション反映および月次クレジット付与"""
        try:
            expire_date = (datetime.now() + timedelta(days=32)).isoformat()
            self.firestore.db.collection("users").document(user_id).set({
                "plan": plan,
                "subscription_status": "active",
                "subscription_expire_date": expire_date,
                "updated_at": datetime.now().isoformat()
            }, merge=True)
            self.add_credits(user_id, credits_to_grant, reason=f"{plan}プラン月次クレジット付与")
            logger.info(f"Updated subscription for user {user_id}: plan={plan}, granted={credits_to_grant}")
        except Exception as e:
            logger.error(f"Failed to update user subscription in Firestore: {e}")
