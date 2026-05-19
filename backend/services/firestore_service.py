"""
Firestore サービス — ジョブ管理
ジョブの作成・更新・取得を行う
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore

import config

logger = logging.getLogger(__name__)

# Firebase Admin SDK の初期化（アプリケーション全体で1回だけ）
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()


class FirestoreService:
    """Firestoreを使用したジョブ管理サービス"""

    def __init__(self):
        self.collection = db.collection(config.FIRESTORE_COLLECTION)

    def create_job(self, user_id: str, mode: str, params: dict) -> str:
        """
        新しいジョブドキュメントを作成する

        Args:
            user_id: FirebaseユーザーID
            mode: 処理モード（"A" or "B"）
            params: ジョブパラメータ

        Returns:
            str: 生成されたジョブID
        """
        job_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        job_doc = {
            "job_id": job_id,
            "user_id": user_id,
            "mode": mode,
            "params": params,
            "status": "pending",
            "progress": 0,
            "message": "ジョブを作成しました",
            "youtube_url": None,
            "storage_url": None,
            "created_at": now,
            "updated_at": now,
        }

        self.collection.document(job_id).set(job_doc)
        logger.info(f"ジョブ作成: {job_id} (モード{mode})")
        return job_id

    def update_job(self, job_id: str, **kwargs) -> None:
        """
        ジョブドキュメントを更新する

        Args:
            job_id: ジョブID
            **kwargs: 更新するフィールド
        """
        kwargs["updated_at"] = datetime.utcnow().isoformat()
        self.collection.document(job_id).update(kwargs)

        status = kwargs.get("status", "")
        progress = kwargs.get("progress", "")
        message = kwargs.get("message", "")
        logger.debug(f"ジョブ更新: {job_id} status={status} progress={progress} {message}")

    def get_job(self, job_id: str) -> Optional[dict]:
        """ジョブドキュメントを取得"""
        doc = self.collection.document(job_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def list_jobs(self, user_id: str, limit: int = 20) -> list[dict]:
        """ユーザーのジョブ一覧を取得（新しい順）"""
        docs = (
            self.collection
            .where("user_id", "==", user_id)
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
