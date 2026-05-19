"""
YouTube Data API v3 サービス — 自動アップロード
処理完了後に動画をYouTubeに非公開で自動投稿する
"""
import logging
import os
import json
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

import config

logger = logging.getLogger(__name__)

# YouTube API のスコープ
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeService:
    """YouTube Data API v3 を使用した自動アップロードサービス"""

    def __init__(self):
        self._youtube = None

    def _get_authenticated_service(self):
        """
        認証済みYouTube APIサービスを取得

        OAuth 2.0 の認証フロー:
        1. 保存済みトークンがあればそれを使用
        2. トークンが期限切れなら自動更新
        3. トークンがなければ新規認証フロー（初回のみ手動が必要）
        """
        if self._youtube:
            return self._youtube

        creds = None
        token_path = Path(config.YOUTUBE_TOKEN_FILE)

        # 保存済みトークンの読み込み
        if token_path.exists():
            with open(token_path, "r") as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)

        # トークンの更新が必要な場合
        if creds and creds.expired and creds.refresh_token:
            logger.info("YouTubeトークンを更新中...")
            creds.refresh(Request())
            # 更新されたトークンを保存
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        # トークンがない場合（初回セットアップ時）
        if not creds or not creds.valid:
            client_secrets = Path(config.YOUTUBE_CLIENT_SECRETS_FILE)
            if not client_secrets.exists():
                logger.warning(
                    "YouTube Client Secretsファイルが見つかりません。"
                    "YouTube投稿はスキップされます。"
                )
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)

            # トークンを保存
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            logger.info("YouTube認証トークンを保存しました")

        self._youtube = build("youtube", "v3", credentials=creds)
        return self._youtube

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: list[str] = None,
        category_id: str = "22",  # 22 = People & Blogs
        privacy_status: str = "private",
    ) -> Optional[str]:
        """
        動画をYouTubeにアップロードする

        Args:
            video_path: アップロードする動画ファイルのパス
            title: 動画タイトル
            description: 動画の説明文
            tags: タグリスト
            category_id: YouTubeカテゴリーID
            privacy_status: 公開設定（"private" / "unlisted" / "public"）

        Returns:
            Optional[str]: アップロードされた動画のURL。失敗した場合はNone
        """
        youtube = self._get_authenticated_service()
        if not youtube:
            logger.warning("YouTube APIが利用できないため、投稿をスキップします")
            return None

        body = {
            "snippet": {
                "title": title[:100],  # タイトルは100文字まで
                "description": description[:5000],
                "tags": tags or [],
                "categoryId": category_id,
                "defaultLanguage": "ja",
                "defaultAudioLanguage": "ja",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        # チャンク分割アップロード（大容量ファイル対応）
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MBチャンク
        )

        try:
            logger.info(f"YouTube投稿開始: '{title}' ({privacy_status})")

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            # Resumableアップロードを実行
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"YouTube投稿進捗: {progress}%")

            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            logger.info(f"YouTube投稿完了: {video_url}")
            return video_url

        except HttpError as e:
            logger.error(f"YouTube APIエラー: {e}")
            raise
        except Exception as e:
            logger.error(f"YouTube投稿に失敗: {e}")
            raise
