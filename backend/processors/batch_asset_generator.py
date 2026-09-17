"""
KIMIDORI Movie Auto - バッチ素材（画像・吹き出し演出・音声）生成モジュール
コマ割りシナリオデータから、全シーンの音声・画像・演出用吹き出し画像をキャッシュ機構付きで一括並列生成する
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont

from utils.asset_cache_manager import AssetCacheManager
from processors.tts_manager import TTSManager
import config

logger = logging.getLogger(__name__)


class BatchAssetGenerator:
    """
    長尺・漫画動画用のアセット（音声・背景画像・漫画風吹き出し演出画像）のバッチ生成およびキャッシュ制御モジュール
    """

    def __init__(self, cache_manager: Optional[AssetCacheManager] = None):
        self.cache_manager = cache_manager or AssetCacheManager()
        self.tts_manager = TTSManager()

    def _create_manga_bubble_overlay(
        self,
        width: int,
        height: int,
        speaker: str,
        narration: str,
        max_chars_per_line: int = 14
    ) -> Image.Image:
        """
        PILを使用して、透明背景上に漫画風の吹き出しテロップ画像を作成する
        演出用: 0.3秒で「人物のみ」から「吹き出し付き」へオーバーレイ表示するために使用
        """
        # RGBAの透明キャンバス作成
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 画面下部に白地＋黒枠の角丸吹き出し領域を描画
        margin = int(width * 0.05)
        bubble_w = width - (margin * 2)
        bubble_h = int(height * 0.28)
        bubble_x0 = margin
        bubble_y0 = height - bubble_h - int(height * 0.05)
        bubble_x1 = bubble_x0 + bubble_w
        bubble_y1 = bubble_y0 + bubble_h

        # 吹き出しの背景（半透明白 240, 240, 245, 235）と枠線（黒 30, 30, 30）
        draw.rounded_rectangle(
            [bubble_x0, bubble_y0, bubble_x1, bubble_y1],
            radius=20,
            fill=(245, 245, 250, 235),
            outline=(30, 30, 35, 255),
            width=5
        )

        # スピーカーラベルタグの描画（存在する場合）
        if speaker and speaker != "ナレーション":
            tag_w = int(bubble_w * 0.3)
            tag_h = int(bubble_h * 0.22)
            tag_x0 = bubble_x0 + 15
            tag_y0 = bubble_y0 - (tag_h // 2)
            draw.rounded_rectangle(
                [tag_x0, tag_y0, tag_x0 + tag_w, tag_y0 + tag_h],
                radius=10,
                fill=(40, 120, 220, 255)
            )
            # スピーカー名描画
            try:
                font_tag = ImageFont.truetype("arial.ttf", size=int(tag_h * 0.6))
            except Exception:
                font_tag = ImageFont.load_default()
            draw.text((tag_x0 + 12, tag_y0 + 4), speaker, fill=(255, 255, 255, 255), font=font_tag)

        # セリフテキストの折り返し処理
        lines = []
        for i in range(0, len(narration), max_chars_per_line):
            lines.append(narration[i:i + max_chars_per_line])

        # 本文描画
        text_content = "\n".join(lines[:4])  # 最大4行
        try:
            font_main = ImageFont.truetype("arial.ttf", size=int(height * 0.038))
        except Exception:
            font_main = ImageFont.load_default()

        draw.text(
            (bubble_x0 + 25, bubble_y0 + 25),
            text_content,
            fill=(20, 20, 25, 255),
            font=font_main,
            spacing=10
        )

        return overlay

    def _generate_placeholder_image(self, width: int, height: int, prompt: str, scene_num: int) -> Image.Image:
        """
        画像API失敗時やオフラインテスト用のプレースホルダー漫画風背景画像を生成
        """
        img = Image.new("RGB", (width, height), (35, 38, 48))
        draw = ImageDraw.Draw(img)

        # 集中線や背景格子の簡易描画
        for i in range(0, width, 40):
            draw.line([(i, 0), (width - i, height)], fill=(45, 50, 65), width=2)

        try:
            font = ImageFont.truetype("arial.ttf", size=int(height * 0.04))
        except Exception:
            font = ImageFont.load_default()

        text_str = f"Scene #{scene_num}\nPrompt: {prompt[:30]}..."
        draw.text((width // 10, height // 3), text_str, fill=(220, 220, 230), font=font)
        return img

    async def generate_single_scene_assets(
        self,
        scene_data: Dict[str, Any],
        output_dir: Path,
        tts_engine: str = "edge",
        voice_name: Optional[str] = None,
        image_size: Tuple[int, int] = (1080, 1920)
    ) -> Dict[str, Any]:
        """
        1シーン分の音声・ベース画像・吹き出しオーバーレイ画像を生成（キャッシュ優先）
        """
        scene_num = scene_data.get("scene_number", 1)
        narration = scene_data.get("narration", "")
        speaker = scene_data.get("speaker", "ナレーション")
        prompt = scene_data.get("character_prompt", "") or scene_data.get("visual_description", "")
        bgm_tag = scene_data.get("bgm_tag", "neutral")

        # ----------------------------------------------------
        # 1. 音声アセット生成（キャッシュチェック）
        # ----------------------------------------------------
        voice_params = {"engine": tts_engine, "voice": voice_name}
        cached_audio = self.cache_manager.get_audio(narration, voice_params)

        audio_out_path = output_dir / f"speech_{scene_num:03d}.mp3"

        if cached_audio:
            # キャッシュからコピー
            import shutil
            shutil.copy2(cached_audio, audio_out_path)
            logger.info(f"Scene {scene_num}: Loaded audio from cache.")
        else:
            # 新規生成
            try:
                tts_mgr = TTSManager(engine=tts_engine, voice_name=voice_name or "nanami")
                scenes_input = [{"narration": narration}]
                # 各並列タスクごとに独立した一時サブディレクトリを使用
                sub_temp_dir = output_dir / f"scene_temp_{scene_num:03d}"
                sub_temp_dir.mkdir(parents=True, exist_ok=True)
                
                generated_paths = await tts_mgr.synthesize_all_scenes(scenes_input, sub_temp_dir)
                
                if generated_paths and generated_paths[0].exists():
                    gen_p = generated_paths[0]
                    self.cache_manager.save_audio(gen_p, narration, voice_params)
                    import shutil
                    shutil.copy2(gen_p, audio_out_path)
                    shutil.rmtree(sub_temp_dir, ignore_errors=True)
                else:
                    audio_out_path = None
            except Exception as e:
                logger.error(f"Scene {scene_num}: Failed to generate TTS: {e}")
                audio_out_path = None

        # ----------------------------------------------------
        # 2. ベース画像アセット生成（キャッシュチェック）
        # ----------------------------------------------------
        img_w, img_h = image_size
        img_params = {"width": img_w, "height": img_h}
        cached_image = self.cache_manager.get_image(prompt, img_params)

        base_image_out_path = output_dir / f"bg_{scene_num:03d}.png"

        if cached_image:
            import shutil
            shutil.copy2(cached_image, base_image_out_path)
            logger.info(f"Scene {scene_num}: Loaded base image from cache.")
        else:
            # 新規プレースホルダーまたは生成
            pil_img = self._generate_placeholder_image(img_w, img_h, prompt, scene_num)
            self.cache_manager.save_image(pil_img, prompt, img_params)
            pil_img.save(base_image_out_path, "PNG")

        # ----------------------------------------------------
        # 3. 吹き出し/テロップ演出画像アセット生成（キャッシュチェック）
        # ----------------------------------------------------
        overlay_params = {"width": img_w, "height": img_h}
        cached_overlay = self.cache_manager.get_overlay(narration, speaker, overlay_params)

        overlay_out_path = output_dir / f"overlay_{scene_num:03d}.png"

        if cached_overlay:
            import shutil
            shutil.copy2(cached_overlay, overlay_out_path)
            logger.info(f"Scene {scene_num}: Loaded overlay from cache.")
        else:
            pil_overlay = self._create_manga_bubble_overlay(img_w, img_h, speaker, narration)
            self.cache_manager.save_overlay(pil_overlay, narration, speaker, overlay_params)
            pil_overlay.save(overlay_out_path, "PNG")

        return {
            "scene_number": scene_num,
            "speaker": speaker,
            "narration": narration,
            "bgm_tag": bgm_tag,
            "audio_path": str(audio_out_path) if audio_out_path else None,
            "base_image_path": str(base_image_out_path),
            "overlay_image_path": str(overlay_out_path),
            "duration_seconds": scene_data.get("duration_seconds", 5)
        }

    async def generate_batch_assets(
        self,
        script_data: Dict[str, Any],
        output_dir: Union[str, Path],
        tts_engine: str = "edge",
        voice_name: Optional[str] = None,
        image_size: Tuple[int, int] = (1080, 1920)
    ) -> List[Dict[str, Any]]:
        """
        全シーンのアセットをバッチ生成するメインメソッド
        """
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)

        scenes = script_data.get("scenes", [])
        logger.info(f"BatchAssetGenerator: Starting batch asset generation for {len(scenes)} scenes...")

        tasks = [
            self.generate_single_scene_assets(
                scene_data=scene,
                output_dir=out_p,
                tts_engine=tts_engine,
                voice_name=voice_name,
                image_size=image_size
            )
            for scene in scenes
        ]

        # 非同期一括並列実行
        results = await asyncio.gather(*tasks)
        logger.info(f"BatchAssetGenerator: Completed asset generation for {len(results)} scenes.")
        return results
