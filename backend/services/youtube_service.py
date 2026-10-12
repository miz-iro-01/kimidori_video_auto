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
    """YouTube Data API v3 を使用したOAuth 2.0直接アップロード・予約投稿・サムネイル設定サービス"""

    def __init__(self, firestore_service=None):
        self._youtube = None
        self.firestore = firestore_service
        self.local_store_path = config.DATA_DIR / "youtube_oauth.json"

    def _load_local_store(self) -> dict:
        try:
            if self.local_store_path.exists():
                return json.loads(self.local_store_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read youtube_oauth.json: {e}")
        return {"states": {}, "users": {}}

    def _save_local_store(self, data: dict) -> None:
        try:
            self.local_store_path.parent.mkdir(parents=True, exist_ok=True)
            self.local_store_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write youtube_oauth.json: {e}")

    def generate_auth_url(self, client_id: str, client_secret: str, redirect_uri: str, user_id: str) -> str:
        """SaaSユーザーが連携するためのOAuth認証URLを発行する (youtube.uploadスコープ)"""
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

        state_payload = {
            "user_id": user_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri
        }

        # stateをFirestoreおよびローカルJSONに保存
        try:
            if self.firestore:
                self.firestore.db.collection('oauth_states').document(state).set(state_payload)
        except Exception as e:
            logger.warning(f"Firestore oauth_states save skipped: {e}")

        store = self._load_local_store()
        store.setdefault("states", {})[state] = state_payload
        self._save_local_store(store)

        return auth_url

    def exchange_code(self, code: str, state: str) -> dict:
        """コールバックで受け取ったcodeをトークンに交換し、チャンネル情報を取得・保存する"""
        state_data = None
        doc_ref = None
        try:
            if self.firestore:
                doc_ref = self.firestore.db.collection('oauth_states').document(state)
                doc = doc_ref.get()
                if doc.exists:
                    state_data = doc.to_dict()
        except Exception as e:
            logger.warning(f"Firestore oauth_states read warning: {e}")

        if not state_data:
            store = self._load_local_store()
            state_data = store.get("states", {}).get(state)

        if not state_data:
            raise ValueError("Invalid OAuth state")

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

        # 認証情報をユーザーDBおよびローカルJSONに保存
        user_id = state_data["user_id"]
        cred_dict = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else list(YOUTUBE_SCOPES)
        }
        try:
            if self.firestore:
                self.firestore.db.collection('users').document(user_id).set({
                    "youtube_creds": cred_dict
                }, merge=True)
        except Exception as e:
            logger.warning(f"Firestore youtube_creds save warning: {e}")

        store = self._load_local_store()
        user_entry = store.setdefault("users", {}).setdefault(user_id, {})
        user_entry["youtube_creds"] = cred_dict
        store.get("states", {}).pop(state, None)
        self._save_local_store(store)

        # チャンネル情報を取得して保存
        channel_info = self._fetch_and_save_channel(credentials, user_id)

        # 不要になったstateを削除
        try:
            if doc_ref:
                doc_ref.delete()
        except Exception:
            pass

        return {"success": True, "user_id": user_id, "channel": channel_info}

    def _fetch_and_save_channel(self, credentials, user_id: str) -> dict:
        """認証済みの認証情報を使ってチャンネル情報を取得し、Firestoreとローカルに保存する"""
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

            try:
                if self.firestore:
                    self.firestore.db.collection('users').document(user_id).collection('youtube_channels').document(channel_info["id"]).set(channel_info, merge=True)
            except Exception as e:
                logger.warning(f"Firestore channel save warning: {e}")

            store = self._load_local_store()
            user_entry = store.setdefault("users", {}).setdefault(user_id, {})
            channels_map = user_entry.setdefault("channels", {})
            channels_map[channel_info["id"]] = channel_info
            self._save_local_store(store)

            logger.info(f"YouTube channel saved: {channel_info['name']} (ID: {channel_info['id']}) for user {user_id}")
            return channel_info

        except Exception as e:
            logger.error(f"Failed to fetch YouTube channel info: {e}")
            return {}

    def get_user_channels(self, user_id: str) -> list:
        """ユーザーに紐づいた全YouTubeチャンネル情報を取得する"""
        channels_by_id = {}
        if self.firestore:
            try:
                channels_ref = self.firestore.db.collection('users').document(user_id).collection('youtube_channels')
                docs = channels_ref.stream()
                for doc in docs:
                    d = doc.to_dict()
                    if d and d.get("id"):
                        channels_by_id[d["id"]] = d
            except Exception as e:
                logger.warning(f"Failed to get user channels from Firestore: {e}")

        store = self._load_local_store()
        local_channels = store.get("users", {}).get(user_id, {}).get("channels", {})
        for cid, cinfo in local_channels.items():
            if cid not in channels_by_id:
                channels_by_id[cid] = cinfo

        return list(channels_by_id.values())

    def remove_user_channel(self, user_id: str, channel_id: str) -> None:
        """連携済みYouTubeチャンネルを削除する"""
        try:
            if self.firestore:
                self.firestore.db.collection('users').document(user_id).collection('youtube_channels').document(channel_id).delete()
        except Exception as e:
            logger.warning(f"Firestore channel delete warning: {e}")

        store = self._load_local_store()
        user_entry = store.get("users", {}).get(user_id, {})
        if "channels" in user_entry and channel_id in user_entry["channels"]:
            user_entry["channels"].pop(channel_id, None)
            self._save_local_store(store)

    def has_valid_credentials(self, user_id: str) -> bool:
        """ユーザーが有効なYouTube OAuth認証トークンを保持しているか判定"""
        cred_data = self._load_user_cred_dict(user_id)
        return bool(cred_data and (cred_data.get("token") or cred_data.get("refresh_token")))

    def _load_user_cred_dict(self, user_id: str) -> Optional[dict]:
        if self.firestore:
            try:
                doc = self.firestore.db.collection('users').document(user_id).get()
                if doc.exists and "youtube_creds" in doc.to_dict():
                    return doc.to_dict()["youtube_creds"]
            except Exception:
                pass
        store = self._load_local_store()
        # 指定user_idになければ他の一致ユーザー（default_user / oumaumauma32@gmail.com）も検索
        for uid_cand in [user_id, "oumaumauma32@gmail.com", "default_user", "user_123"]:
            if not uid_cand:
                continue
            c = store.get("users", {}).get(uid_cand, {}).get("youtube_creds")
            if c:
                return c
        return None

    def _get_authenticated_service(self, user_id: str):
        """ユーザーIDに紐づく認証済みYouTube APIサービスを取得"""
        cred_data = self._load_user_cred_dict(user_id)
        if not cred_data:
            logger.warning(f"YouTube credentials not found for user {user_id}")
            return None

        creds = Credentials.from_authorized_user_info(cred_data, YOUTUBE_SCOPES)

        if creds and creds.expired and creds.refresh_token:
            logger.info("YouTubeトークンを更新中...")
            creds.refresh(Request())
            cred_data["token"] = creds.token
            try:
                if self.firestore:
                    self.firestore.db.collection('users').document(user_id).set({
                        "youtube_creds": cred_data
                    }, merge=True)
            except Exception:
                pass
            store = self._load_local_store()
            store.setdefault("users", {}).setdefault(user_id, {})["youtube_creds"] = cred_data
            self._save_local_store(store)

        return build("youtube", "v3", credentials=creds)

    def set_thumbnail(self, video_id: str, thumbnail_path: str, user_id: str) -> bool:
        """アップロード済み動画にカスタムサムネイル画像を設定する (youtube.thumbnails().set)"""
        t_path = Path(thumbnail_path)
        if not t_path.exists() or t_path.stat().st_size == 0:
            return False

        youtube = self._get_authenticated_service(user_id)
        if not youtube:
            return False

        ext = t_path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        try:
            thumb_media = MediaFileUpload(str(t_path), mimetype=mime, resumable=False)
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=thumb_media
            ).execute()
            logger.info(f"YouTubeカスタムサムネイル設定完了: video_id={video_id} ({t_path.name})")
            return True
        except Exception as e:
            logger.warning(f"YouTubeサムネイル設定失敗 (video_id={video_id}): {e}")
            return False

    def upload_video(
        self,
        video_path: str,
        title: str,
        user_id: str,
        description: str = "",
        tags: list[str] = None,
        category_id: str = "22",  # 22 = People & Blogs
        privacy_status: str = "private",
        publish_at: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        動画をYouTubeにチャンク分割アップロード（Resumable Upload）する。
        公開・非公開・限定公開・予約投稿（publishAt ISO 8601）およびサムネイル設定に対応。
        """
        youtube = self._get_authenticated_service(user_id)
        if not youtube:
            logger.warning(f"YouTube APIが利用できないため、投稿をスキップします (user_id={user_id})")
            return None

        effective_privacy = "private" if (publish_at or privacy_status == "scheduled") else privacy_status
        if effective_privacy not in ("public", "private", "unlisted"):
            effective_privacy = "private"

        status_body = {
            "privacyStatus": effective_privacy,
            "selfDeclaredMadeForKids": False,
        }
        if publish_at:
            status_body["publishAt"] = publish_at

        body = {
            "snippet": {
                "title": (title or "KIMIDORI Movie Auto")[:100],
                "description": (description or "")[:5000],
                "tags": tags or [],
                "categoryId": category_id,
                "defaultLanguage": "ja",
                "defaultAudioLanguage": "ja",
            },
            "status": status_body,
        }

        # チャンク分割アップロード（大容量ファイル対応: 10MBチャンク Resumable Upload）
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,
        )

        try:
            logger.info(f"YouTube投稿開始: '{title}' (privacy={effective_privacy}, publishAt={publish_at})")

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

            # サムネイル画像が指定されている場合は適用
            if thumbnail_path and Path(thumbnail_path).exists():
                self.set_thumbnail(video_id=video_id, thumbnail_path=thumbnail_path, user_id=user_id)

            logger.info(f"YouTube投稿完了: {video_url}")
            return video_url

        except HttpError as e:
            logger.error(f"YouTube APIエラー: {e}")
            raise
        except Exception as e:
            logger.error(f"YouTube投稿に失敗: {e}")
            raise

