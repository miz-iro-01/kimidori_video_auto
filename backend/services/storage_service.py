"""
Cloud Storage サービス — ファイルのアップロード・ダウンロード
"""
import logging
from pathlib import Path
from google.cloud import storage as gcs
import config

logger = logging.getLogger(__name__)


class StorageService:
    """Google Cloud Storage を使用したファイル管理"""

    def __init__(self):
        self._client = None
        self._bucket = None

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = gcs.Client()
            except Exception as e:
                logger.warning(f"⚠️ Storageクライアントの初期化に失敗しました。認証情報がない状態で動作しています。エラー詳細: {e}")
                raise RuntimeError(
                    "Google Cloud Storageの認証情報（Application Default Credentials）が設定されていません。"
                ) from e
        return self._client

    @property
    def bucket(self):
        if self._bucket is None:
            self._bucket = self.client.bucket(config.FIREBASE_STORAGE_BUCKET)
        return self._bucket

    def upload_file(self, local_path: Path, destination_path: str) -> str:
        """
        ローカルファイルをCloud Storageにアップロード

        Args:
            local_path: ローカルファイルのパス
            destination_path: Storage上の保存先パス

        Returns:
            str: アップロードされたファイルの公開URL
        """
        blob = self.bucket.blob(destination_path)
        blob.upload_from_filename(str(local_path))

        # 署名付きURLを生成（7日間有効）
        from datetime import timedelta
        url = blob.generate_signed_url(expiration=timedelta(days=7))

        logger.info(f"アップロード完了: {destination_path}")
        return url

    def download_file(self, storage_path: str, local_path: Path) -> Path:
        """
        Cloud Storageからファイルをダウンロード

        Args:
            storage_path: Storage上のファイルパス
            local_path: ダウンロード先のローカルパス

        Returns:
            Path: ダウンロードされたファイルのパス
        """
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob = self.bucket.blob(storage_path)
        blob.download_to_filename(str(local_path))

        logger.info(f"ダウンロード完了: {storage_path} → {local_path}")
        return local_path
