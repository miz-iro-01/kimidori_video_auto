"""
KIMIDORI Movie Auto - Pexels Bロール素材自動取得クライアント
addyosmani/pexels-ai-video-downloader 設計準拠
Whisper解析から導出された文脈・感情キーワードに基づき、Pexels APIから適切なBロール映像・画像を取得・ローカルキャッシュする
"""

import os
import re
import json
import logging
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
import httpx

import config

logger = logging.getLogger(__name__)

PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"


class PexelsClient:
    """Pexels APIを使用したBロール動画・写真素材の検索・ダウンロードクライアント"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PEXELS_API_KEY", "")
        self.cache_dir = config.CACHE_DIR / "pexels"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        """APIキーが設定されているか確認"""
        return bool(self.api_key and len(self.api_key.strip()) > 10)

    async def search_and_download_broll(
        self,
        query: str,
        orientation: str = "landscape",  # "landscape" or "portrait"
        preferred_type: str = "video",    # "video" or "image"
        min_duration: float = 3.0,
        output_dir: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """
        英語クエリでPexelsから素材を検索し、最適なファイルを取得してローカル保存する

        Args:
            query: 検索キーワード (英語)
            orientation: "landscape" (16:9 横長) または "portrait" (9:16 縦長)
            preferred_type: "video" (動画優先) または "image" (静止画)
            min_duration: 必要最小動画長（秒）
            output_dir: 保存先ディレクトリ

        Returns:
            Dict: {"file_path": Path, "type": "video"|"image", "duration": float, "id": int, "url": str}
        """
        if not self.is_available():
            logger.warning("Pexels APIキーが未設定のため、Bロール素材検索をスキップします。")
            return None

        clean_query = query.strip()
        if not clean_query:
            return None

        # キャッシュキー
        cache_key = hashlib.md5(f"{clean_query}_{orientation}_{preferred_type}".encode("utf-8")).hexdigest()
        target_dir = output_dir or self.cache_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. 動画検索（動画優先時）
        if preferred_type == "video":
            video_result = await self._search_and_download_video(clean_query, orientation, min_duration, target_dir, cache_key)
            if video_result:
                return video_result
            logger.info(f"Pexels動画素材が見つからなかったため、画像検索へフォールバック: '{clean_query}'")

        # 2. 画像検索（フォールバック または 静止画指定時）
        photo_result = await self._search_and_download_photo(clean_query, orientation, target_dir, cache_key)
        return photo_result

    async def _search_and_download_video(
        self,
        query: str,
        orientation: str,
        min_duration: float,
        target_dir: Path,
        cache_key: str
    ) -> Optional[Dict[str, Any]]:
        """Pexels動画を検索してダウンロード"""
        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "per_page": 10,
            "orientation": orientation,
            "size": "medium"
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params)
                if res.status_code != 200:
                    logger.warning(f"Pexels Video API error: {res.status_code} {res.text[:100]}")
                    return None

                data = res.json()
                videos = data.get("videos", [])
                if not videos:
                    return None

                # 最適な動画ファイルを選択（HD 1080p または 720p、duration が十分なもの）
                best_video = None
                best_file = None

                for v in videos:
                    v_duration = v.get("duration", 0)
                    if v_duration < min_duration:
                        continue
                    files = v.get("video_files", [])
                    # 解像度順にソート (HD/FHD優先)
                    files_sorted = sorted(files, key=lambda f: f.get("width", 0) * f.get("height", 0), reverse=True)
                    for f in files_sorted:
                        if f.get("file_type") == "video/mp4" and f.get("link"):
                            best_video = v
                            best_file = f
                            break
                    if best_file:
                        break

                if not best_file:
                    # 時間制限なしで先頭のmp4を取得
                    for v in videos:
                        for f in v.get("video_files", []):
                            if f.get("file_type") == "video/mp4" and f.get("link"):
                                best_video = v
                                best_file = f
                                break
                        if best_file:
                            break

                if not best_file:
                    return None

                download_url = best_file["link"]
                video_id = best_video.get("id", 0)
                out_path = target_dir / f"broll_vid_{video_id}_{cache_key[:8]}.mp4"

                # 既にローカルに存在すればキャッシュ利用
                if out_path.exists() and out_path.stat().st_size > 10000:
                    logger.info(f"Pexels動画キャッシュ再利用: {out_path.name}")
                    return {
                        "file_path": out_path,
                        "type": "video",
                        "duration": float(best_video.get("duration", min_duration)),
                        "id": video_id,
                        "url": download_url
                    }

                # ダウンロード実行
                logger.info(f"Pexels動画ダウンロード開始: '{query}' -> {out_path.name}")
                dl_res = await client.get(download_url, follow_redirects=True, timeout=60.0)
                if dl_res.status_code == 200:
                    with open(out_path, "wb") as f:
                        f.write(dl_res.content)
                    logger.info(f"Pexels動画ダウンロード完了 ({out_path.stat().st_size} bytes)")
                    return {
                        "file_path": out_path,
                        "type": "video",
                        "duration": float(best_video.get("duration", min_duration)),
                        "id": video_id,
                        "url": download_url
                    }

        except Exception as e:
            logger.warning(f"Pexels動画ダウンロード失敗 ('{query}'): {e}")

        return None

    async def _search_and_download_photo(
        self,
        query: str,
        orientation: str,
        target_dir: Path,
        cache_key: str
    ) -> Optional[Dict[str, Any]]:
        """Pexels写真を検索してダウンロード"""
        headers = {"Authorization": self.api_key}
        params = {
            "query": query,
            "per_page": 5,
            "orientation": orientation
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(PEXELS_PHOTO_SEARCH_URL, headers=headers, params=params)
                if res.status_code != 200:
                    return None

                data = res.json()
                photos = data.get("photos", [])
                if not photos:
                    return None

                photo = photos[0]
                photo_id = photo.get("id", 0)
                img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
                if not img_url:
                    return None

                out_path = target_dir / f"broll_img_{photo_id}_{cache_key[:8]}.jpg"
                if out_path.exists() and out_path.stat().st_size > 5000:
                    return {
                        "file_path": out_path,
                        "type": "image",
                        "duration": 4.0,
                        "id": photo_id,
                        "url": img_url
                    }

                dl_res = await client.get(img_url, follow_redirects=True, timeout=30.0)
                if dl_res.status_code == 200:
                    with open(out_path, "wb") as f:
                        f.write(dl_res.content)
                    logger.info(f"Pexels画像ダウンロード完了: '{query}' -> {out_path.name}")
                    return {
                        "file_path": out_path,
                        "type": "image",
                        "duration": 4.0,
                        "id": photo_id,
                        "url": img_url
                    }
        except Exception as e:
            logger.warning(f"Pexels画像ダウンロード失敗 ('{query}'): {e}")

        return None
