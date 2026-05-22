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

import json
from pathlib import Path

_db = None

class MockQuery:
    def __init__(self, collection, filters=None, orders=None, limit_val=None):
        self.collection = collection
        self.filters = filters or []
        self.orders = orders or []
        self.limit_val = limit_val

    def where(self, field, op, val):
        new_filters = self.filters + [(field, op, val)]
        return MockQuery(self.collection, new_filters, self.orders, self.limit_val)

    def order_by(self, field, direction=None):
        new_orders = self.orders + [(field, direction)]
        return MockQuery(self.collection, self.filters, new_orders, self.limit_val)

    def limit(self, limit):
        return MockQuery(self.collection, self.filters, self.orders, limit)

    def stream(self):
        data = self.collection.db._load_data()
        coll_data = data.get(self.collection.name, {})
        results = []
        for doc_id, doc_data in coll_data.items():
            results.append(MockDocumentSnapshot(doc_id, doc_data, True))
        
        # Apply filters
        for field, op, val in self.filters:
            filtered = []
            for doc in results:
                d_val = doc.to_dict().get(field)
                if op == "==" and d_val == val:
                    filtered.append(doc)
                elif op == ">" and d_val is not None and d_val > val:
                    filtered.append(doc)
            results = filtered

        # Apply ordering
        for field, direction in self.orders:
            descending = (direction == "DESCENDING" or (hasattr(firestore, 'Query') and direction == firestore.Query.DESCENDING))
            results.sort(key=lambda d: d.to_dict().get(field, ""), reverse=descending)

        # Apply limit
        if self.limit_val is not None:
            results = results[:self.limit_val]

        return results

class MockDocumentSnapshot:
    def __init__(self, doc_id, data, exists):
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data or {}

class MockDocumentReference:
    def __init__(self, collection, doc_id):
        self.collection = collection
        self.id = doc_id

    def get(self):
        data = self.collection.db._load_data()
        coll_data = data.get(self.collection.name, {})
        if self.id in coll_data:
            return MockDocumentSnapshot(self.id, coll_data[self.id], True)
        return MockDocumentSnapshot(self.id, None, False)

    def set(self, data, merge=False):
        all_data = self.collection.db._load_data()
        if self.collection.name not in all_data:
            all_data[self.collection.name] = {}
        
        if merge and self.id in all_data[self.collection.name]:
            all_data[self.collection.name][self.id].update(data)
        else:
            all_data[self.collection.name][self.id] = data
            
        self.collection.db._save_data(all_data)

    def update(self, data):
        all_data = self.collection.db._load_data()
        if self.collection.name in all_data and self.id in all_data[self.collection.name]:
            all_data[self.collection.name][self.id].update(data)
            self.collection.db._save_data(all_data)
        else:
            raise ValueError(f"Document {self.id} does not exist to update")

    def delete(self):
        all_data = self.collection.db._load_data()
        if self.collection.name in all_data and self.id in all_data[self.collection.name]:
            del all_data[self.collection.name][self.id]
            self.collection.db._save_data(all_data)

class MockCollectionReference:
    def __init__(self, db, name):
        self.db = db
        self.name = name

    def document(self, doc_id):
        return MockDocumentReference(self, doc_id)

    def where(self, field, op, val):
        return MockQuery(self).where(field, op, val)

    def order_by(self, field, direction=None):
        return MockQuery(self).order_by(field, direction)

    def limit(self, limit):
        return MockQuery(self).limit(limit)

    def stream(self):
        return MockQuery(self).stream()

class MockFirestore:
    def __init__(self):
        self.db_path = config.TMP_DIR / "local_db.json"
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _load_data(self):
        try:
            if self.db_path.exists():
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load local mock DB: {e}")
        return {}

    def _save_data(self, data):
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save local mock DB: {e}")

    def collection(self, name):
        return MockCollectionReference(self, name)

def get_db():
    global _db
    if _db is None:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            _db = firestore.client()
        except Exception as e:
            logger.warning(
                "⚠️ Firebase Admin SDKの初期化に失敗しました。ローカル模擬データベース（MockFirestore）を使用します。 "
                f"エラー詳細: {e}"
            )
            _db = MockFirestore()
    return _db


class FirestoreService:
    """Firestoreを使用したジョブ管理サービス"""

    def __init__(self):
        self._db = None
        self._collection = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_db()
        return self._db

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.db.collection(config.FIRESTORE_COLLECTION)
        return self._collection

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
