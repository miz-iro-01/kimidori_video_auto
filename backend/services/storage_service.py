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
        try:
            # ローカル環境など（秘密鍵を持つサービスアカウントJSON）の場合は通常通り生成可能
            url = blob.generate_signed_url(expiration=timedelta(days=7))
        except Exception as e:
            # Cloud Run などのコンピュート環境では秘密鍵がないため、IAM APIを利用して署名する
            import google.auth
            from google.auth.iam import Signer
            from google.auth.transport.requests import Request
            
            credentials, project = google.auth.default()
            credentials.refresh(Request())
            
            sa_email = f"{project}-compute@developer.gserviceaccount.com"
            signer = Signer(Request(), credentials, sa_email)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(days=7),
                service_account_email=sa_email,
                signer=signer
            )

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

    def delete_file(self, storage_path: str) -> bool:
        """
        Cloud Storage上のファイルを削除

        Args:
            storage_path: Storage上のファイルパス

        Returns:
            bool: 削除が成功したかどうか
        """
        try:
            blob = self.bucket.blob(storage_path)
            blob.delete()
            logger.info(f"削除完了: {storage_path}")
            return True
        except Exception as e:
            logger.warning(f"ファイル削除に失敗: {storage_path} — {e}")
            return False
