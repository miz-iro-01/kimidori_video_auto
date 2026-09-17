"""
KIMIDORI Movie Auto - 素材（画像・音声）ローカルキャッシュマネージャー
生成済み画像、吹き出し画像、音声ファイルのキャッシュおよび再利用を管理する
"""

import os
import json
import hashlib
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple
import config

logger = logging.getLogger(__name__)


class AssetCacheManager:
    """
    画像・音声・テキスト演出素材のローカルキャッシュ管理クラス
    """

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None):
        """
        Args:
            cache_dir: キャッシュの保存先ディレクトリ（デフォルトは config.CACHE_DIR / 'assets'）
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(config.CACHE_DIR) / "assets"

        self.audio_cache_dir = self.cache_dir / "audio"
        self.image_cache_dir = self.cache_dir / "images"
        self.overlay_cache_dir = self.cache_dir / "overlays"
        self.meta_cache_dir = self.cache_dir / "metadata"

        # ディレクトリの自動生成
        for d in [self.audio_cache_dir, self.image_cache_dir, self.overlay_cache_dir, self.meta_cache_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_hash(prefix: str, content: str, extra_params: Optional[Dict[str, Any]] = None) -> str:
        """
        検索用ハッシュキーを生成
        """
        data = f"{prefix}:{content}"
        if extra_params:
            # 辞書のキーをソートして決定論的に文字列化
            extra_str = json.dumps(extra_params, sort_keys=True, ensure_ascii=False)
            data += f":{extra_str}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def get_audio(self, text: str, voice_params: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """
        テキストおよび音声パラメータからキャッシュ済み音声ファイルのパスを取得
        """
        hash_key = self.generate_hash("audio", text, voice_params)
        target_path = self.audio_cache_dir / f"{hash_key}.mp3"
        if target_path.exists() and target_path.stat().st_size > 0:
            logger.info(f"AssetCacheManager: Audio cache HIT for text '{text[:15]}...' -> {hash_key[:10]}")
            return target_path
        return None

    def save_audio(self, source_path: Union[str, Path], text: str, voice_params: Optional[Dict[str, Any]] = None) -> Path:
        """
        生成された音声ファイルをキャッシュに保存
        """
        hash_key = self.generate_hash("audio", text, voice_params)
        target_path = self.audio_cache_dir / f"{hash_key}.mp3"
        source_p = Path(source_path)

        if source_p.resolve() != target_path.resolve():
            shutil.copy2(source_p, target_path)

        # メタデータの保存
        self._save_metadata(hash_key, "audio", {"text": text, "voice_params": voice_params})
        logger.info(f"AssetCacheManager: Saved audio to cache -> {hash_key[:10]}")
        return target_path

    def get_image(self, prompt: str, image_params: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """
        プロンプトおよび画像生成パラメータからキャッシュ済み画像ファイルのパスを取得
        """
        hash_key = self.generate_hash("image", prompt, image_params)
        target_path = self.image_cache_dir / f"{hash_key}.png"
        if target_path.exists() and target_path.stat().st_size > 0:
            logger.info(f"AssetCacheManager: Image cache HIT for prompt '{prompt[:15]}...' -> {hash_key[:10]}")
            return target_path
        return None

    def save_image(self, source_path_or_image: Union[str, Path, Any], prompt: str, image_params: Optional[Dict[str, Any]] = None) -> Path:
        """
        生成された画像をキャッシュに保存（PathまたはPIL Imageオブジェクトを受け入れ）
        """
        hash_key = self.generate_hash("image", prompt, image_params)
        target_path = self.image_cache_dir / f"{hash_key}.png"

        if isinstance(source_path_or_image, (str, Path)):
            source_p = Path(source_path_or_image)
            if source_p.resolve() != target_path.resolve():
                shutil.copy2(source_p, target_path)
        else:
            # PIL Image想定
            source_path_or_image.save(target_path, "PNG", quality=95)

        self._save_metadata(hash_key, "image", {"prompt": prompt, "image_params": image_params})
        logger.info(f"AssetCacheManager: Saved image to cache -> {hash_key[:10]}")
        return target_path

    def get_overlay(self, text: str, speaker: str, overlay_params: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """
        吹き出し/テロップ演出用オーバーレイ画像のキャッシュを取得
        """
        hash_key = self.generate_hash("overlay", f"{speaker}:{text}", overlay_params)
        target_path = self.overlay_cache_dir / f"{hash_key}.png"
        if target_path.exists() and target_path.stat().st_size > 0:
            logger.info(f"AssetCacheManager: Overlay cache HIT for speaker '{speaker}' -> {hash_key[:10]}")
            return target_path
        return None

    def save_overlay(self, source_path_or_image: Union[str, Path, Any], text: str, speaker: str, overlay_params: Optional[Dict[str, Any]] = None) -> Path:
        """
        吹き出し/テロップ演出用オーバーレイ画像をキャッシュに保存
        """
        hash_key = self.generate_hash("overlay", f"{speaker}:{text}", overlay_params)
        target_path = self.overlay_cache_dir / f"{hash_key}.png"

        if isinstance(source_path_or_image, (str, Path)):
            source_p = Path(source_path_or_image)
            if source_p.resolve() != target_path.resolve():
                shutil.copy2(source_p, target_path)
        else:
            source_path_or_image.save(target_path, "PNG")

        self._save_metadata(hash_key, "overlay", {"text": text, "speaker": speaker, "overlay_params": overlay_params})
        logger.info(f"AssetCacheManager: Saved overlay to cache -> {hash_key[:10]}")
        return target_path

    def _save_metadata(self, hash_key: str, asset_type: str, info: Dict[str, Any]) -> None:
        """キャッシュメタデータをJSONとして保存"""
        meta_path = self.meta_cache_dir / f"{hash_key}.json"
        meta_data = {
            "hash_key": hash_key,
            "asset_type": asset_type,
            "info": info
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

    def clear_cache(self, asset_type: Optional[str] = None) -> int:
        """
        キャッシュを削除（全削除または指定タイプ削除）
        """
        count = 0
        dirs_to_clear = []
        if asset_type == "audio":
            dirs_to_clear = [self.audio_cache_dir]
        elif asset_type == "image":
            dirs_to_clear = [self.image_cache_dir]
        elif asset_type == "overlay":
            dirs_to_clear = [self.overlay_cache_dir]
        else:
            dirs_to_clear = [self.audio_cache_dir, self.image_cache_dir, self.overlay_cache_dir, self.meta_cache_dir]

        for d in dirs_to_clear:
            for item in d.glob("*"):
                if item.is_file():
                    try:
                        item.unlink()
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete cached file {item}: {e}")
        return count
