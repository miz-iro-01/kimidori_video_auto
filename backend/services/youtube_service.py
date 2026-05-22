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
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


class YouTubeService:
    """YouTube Data API v3 を使用した自動アップロードサービス"""

    def __init__(self, firestore_service=None):
        self._youtube = None
        self.firestore = firestore_service

    def generate_auth_url(self, client_id: str, client_secret: str, redirect_uri: str, user_id: str) -> str:
        """SaaSユーザーが連携するためのOAuth認証URLを発行する"""
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            client_config,
            scopes=YOUTUBE_SCOPES,
            redirect_uri=redirect_uri
        )
        
        # オフラインアクセス（リフレッシュトークン取得用）
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        # stateを保存（セキュリティ検証用）
        if self.firestore:
            self.firestore.db.collection('oauth_states').document(state).set({
                "user_id": user_id,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri
            })
            
        return auth_url

    def exchange_code(self, code: str, state: str) -> dict:
        """コールバックで受け取ったcodeをトークンに交換し、チャンネル情報を取得する"""
        if not self.firestore:
            raise ValueError("Firestore service not initialized")
            
        doc_ref = self.firestore.db.collection('oauth_states').document(state)
        doc = doc_ref.get()
        if not doc.exists:
            raise ValueError("Invalid OAuth state")
            
        state_data = doc.to_dict()
        client_config = {
            "web": {
                "client_id": state_data["client_id"],
                "client_secret": state_data["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [state_data["redirect_uri"]]
            }
        }
        
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            client_config,
            scopes=YOUTUBE_SCOPES,
            state=state,
            redirect_uri=state_data["redirect_uri"]
        )
        
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # 認証情報をユーザーDBに保存
        user_id = state_data["user_id"]
        cred_dict = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else list(YOUTUBE_SCOPES)
        }
        self.firestore.db.collection('users').document(user_id).set({
            "youtube_creds": cred_dict
        }, merge=True)
        
        # チャンネル情報を取得して保存
        channel_info = self._fetch_and_save_channel(credentials, user_id)
        
        # 不要になったstateを削除
        doc_ref.delete()
        
        return {"success": True, "user_id": user_id, "channel": channel_info}

    def _fetch_and_save_channel(self, credentials, user_id: str) -> dict:
        """認証済みの認証情報を使ってチャンネル情報を取得し、Firestoreに保存する"""
        try:
            yt = build("youtube", "v3", credentials=credentials)
            response = yt.channels().list(
                part="snippet,statistics",
                mine=True
            ).execute()
            
            if not response.get("items"):
                logger.warning(f"No YouTube channel found for user {user_id}")
                return {}
            
            channel = response["items"][0]
            channel_info = {
                "id": channel["id"],
                "name": channel["snippet"]["title"],
                "thumbnail": channel["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                "subscriber_count": channel["statistics"].get("subscriberCount", "0"),
            }
            
            # チャンネル情報をユーザーのサブコレクションに保存（重複回避はchannelIdをドキュメントIDに使用）
            self.firestore.db.collection('users').document(user_id).collection('youtube_channels').document(channel_info["id"]).set(channel_info, merge=True)
            
            logger.info(f"YouTube channel saved: {channel_info['name']} (ID: {channel_info['id']}) for user {user_id}")
            return channel_info
            
        except Exception as e:
            logger.error(f"Failed to fetch YouTube channel info: {e}")
            return {}

    def get_user_channels(self, user_id: str) -> list:
        """ユーザーに紐づいた全YouTube チャンネル情報を取得する"""
        if not self.firestore:
            return []
        try:
            channels_ref = self.firestore.db.collection('users').document(user_id).collection('youtube_channels')
            docs = channels_ref.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error(f"Failed to get user channels: {e}")
            return []

    def _get_authenticated_service(self, user_id: str):
        """ユーザーIDに紐づく認証済みYouTube APIサービスを取得"""
        if self._youtube:
            return self._youtube

        if not self.firestore:
            logger.warning("Firestore is not set, skipping YouTube auth.")
            return None

        doc = self.firestore.db.collection('users').document(user_id).get()
        if not doc.exists or "youtube_creds" not in doc.to_dict():
            logger.warning(f"YouTube credentials not found for user {user_id}")
            return None

        cred_data = doc.to_dict()["youtube_creds"]
        creds = Credentials.from_authorized_user_info(cred_data, YOUTUBE_SCOPES)

        if creds and creds.expired and creds.refresh_token:
            logger.info("YouTubeトークンを更新中...")
            creds.refresh(Request())
            # 更新されたトークンを再保存
            cred_data["token"] = creds.token
            self.firestore.db.collection('users').document(user_id).set({
                "youtube_creds": cred_data
            }, merge=True)

        self._youtube = build("youtube", "v3", credentials=creds)
        return self._youtube

    def upload_video(
        self,
        video_path: str,
        title: str,
        user_id: str,
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
            user_id: 認証用のユーザーID
            description: 動画の説明文
            tags: タグリスト
            category_id: YouTubeカテゴリーID
            privacy_status: 公開設定（"private" / "unlisted" / "public"）

        Returns:
            Optional[str]: アップロードされた動画のURL。失敗した場合はNone
        """
        youtube = self._get_authenticated_service(user_id)
        if not youtube:
            logger.warning(f"YouTube APIが利用できないため、投稿をスキップします (user_id={user_id})")
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
