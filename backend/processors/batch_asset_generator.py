"""
KIMIDORI Movie Auto - バッチ素材（画像・テロップ演出・音声）生成モジュール
mode_a 仕様の高精度テロップ（文脈スコアリング改行・フチ取り描画・ジャンル配色）
および Google Colab 無料T4 GPU / FLUX.1 / Pexels / Imagen 連携による高品質アセット生成
"""

import os
import re
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont

from utils.asset_cache_manager import AssetCacheManager
from processors.tts_manager import TTSManager
from processors.flux_client import FluxSchnellClient
from processors.colab_gpu_client import ColabGpuClient
from processors.pexels_client import PexelsClient
import config

logger = logging.getLogger(__name__)


# 禁則文字および助詞定義 (mode_a 仕様準拠)
START_PROHIBITED = set('、。，．・？！?!」』）)]｝}”’ー〜～ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ')
END_PROHIBITED = set('「『（([｛{“‘')
PARTICLES_2 = [
    'について', 'として', 'によって', 'けれど', 'だけど', 'だから', 
    'しかし', 'そして', 'ながら', 'ように', 'ために', 'すると', 
    'なので', 'から', 'まで', 'より', 'ので', 'のに', 'ても', 'たら'
]
PARTICLES_1 = ['は', 'が', 'を', 'に', 'へ', 'で', 'と', 'て', 'も']

GENRE_TELOP_STYLES = {
    "story": {
        "text_color": (255, 255, 255, 255),
        "stroke_color": (15, 23, 42, 255),
        "badge_bg": (16, 185, 129, 235),
        "box_bg": (15, 23, 42, 140)
    },
    "business": {
        "text_color": (255, 255, 255, 255),
        "stroke_color": (10, 25, 47, 255),
        "badge_bg": (37, 99, 235, 235),
        "box_bg": (10, 25, 47, 150)
    },
    "edoculture": {
        "text_color": (255, 250, 235, 255),
        "stroke_color": (30, 20, 15, 255),
        "badge_bg": (194, 65, 12, 235),
        "box_bg": (30, 20, 15, 150)
    },
    "trivia": {
        "text_color": (255, 255, 255, 255),
        "stroke_color": (20, 20, 25, 255),
        "badge_bg": (217, 119, 6, 235),
        "box_bg": (20, 20, 25, 140)
    }
}


class BatchAssetGenerator:
    """
    長尺・Proショート用のアセット（音声・背景画像・高精度テロップ演出画像）のバッチ生成およびキャッシュ制御モジュール
    """

    def __init__(self, cache_manager: Optional[AssetCacheManager] = None):
        self.cache_manager = cache_manager or AssetCacheManager()
        self.tts_manager = TTSManager()

    @classmethod
    def clean_japanese_text(cls, text: str) -> str:
        """テキストの余分な改行や変な記号を正規化し、行頭の孤立記号を除去"""
        t = text.replace('\\n', ' ').replace('\r', ' ').replace('\n', ' ')
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'」[。、.]+', '」', t)
        t = re.sub(r'^[」』）)\s。、？！?!]+', '', t)
        t = re.sub(r'[「『（(\s]+$', '', t)
        return t

    @classmethod
    def split_text_into_cards(cls, text: str, max_lines_per_card: int = 3, max_chars_per_line: int = 14) -> List[str]:
        """文脈スコアリングと禁則処理に基づき、自然な改行位置で1〜3枚のテロップカードに分割"""
        clean_text = cls.clean_japanese_text(text)
        if not clean_text:
            return [""]

        # 文節単位での分割候補スコア計算
        n = len(clean_text)
        points = {}
        for i in range(1, n):
            if clean_text[i] in START_PROHIBITED:
                continue
            if clean_text[i - 1] in END_PROHIBITED:
                continue

            score = 1
            if clean_text[i - 1] in '。！？!?':
                score = 100
            elif clean_text[i - 1] in '、,':
                score = 80
            elif clean_text[i - 1] in '」』）':
                score = 75
            else:
                matched = False
                for p in PARTICLES_2:
                    plen = len(p)
                    if i >= plen and clean_text[i - plen:i] == p:
                        score = 45
                        matched = True
                        break
                if not matched:
                    for p in PARTICLES_1:
                        if clean_text[i - 1] == p:
                            score = 25
                            break
            points[i] = score

        # 最適改行行の構築
        lines = []
        start = 0
        while start < n:
            remaining = n - start
            if remaining <= max_chars_per_line:
                lines.append(clean_text[start:n])
                break

            best_split = start + max_chars_per_line
            best_score = -1
            min_split = max(start + 4, start + max_chars_per_line - 5)

            for cand in range(start + max_chars_per_line, min_split - 1, -1):
                if cand in points and points[cand] > best_score:
                    best_score = points[cand]
                    best_split = cand

            lines.append(clean_text[start:best_split])
            start = best_split

        # カード単位にまとめる（最大 max_lines_per_card 行）
        cards = []
        for i in range(0, len(lines), max_lines_per_card):
            chunk = lines[i:i + max_lines_per_card]
            cards.append("\n".join(chunk))

        return cards if cards else [clean_text]

    def _get_font(self, size: int) -> ImageFont.ImageFont:
        """プラットフォームに応じた最適な日本語太字フォントを取得"""
        candidates = [
            getattr(config, "SUBTITLE_FONT", None),
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:\\Windows\\Fonts\\meiryo.ttc",
            "C:\\Windows\\Fonts\\YuGothB.ttc",
            "C:\\Windows\\Fonts\\msgothic.ttc",
        ]
        for font_path in candidates:
            if font_path and Path(str(font_path)).exists():
                try:
                    return ImageFont.truetype(str(font_path), size=size)
                except Exception:
                    pass
        try:
            return ImageFont.truetype("arial.ttf", size=size)
        except Exception:
            return ImageFont.load_default()

    def _create_manga_bubble_overlay(
        self,
        width: int,
        height: int,
        speaker: str,
        narration: str,
        genre: str = "story"
    ) -> Image.Image:
        """
        mode_a 基準の高品位テロップ（太字白＋高精細黒アウトライン＋スマートバッジ）を描画
        無駄な巨大白矩形を完全排除し、映像を邪魔しないプロ品質のテロップを生成する
        """
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        style = GENRE_TELOP_STYLES.get(genre, GENRE_TELOP_STYLES["story"])
        cards = self.split_text_into_cards(narration, max_lines_per_card=3, max_chars_per_line=14)
        card_text = cards[0] if cards else ""
        if not card_text:
            return overlay

        # フォントサイズ計算（縦動画 1080x1920: 約 58px）
        font_size = int(width * 0.054)
        font_main = self._get_font(font_size)
        stroke_width = max(3, int(font_size * 0.10))

        # バウンディングボックス測定
        bbox = draw.multiline_textbbox((0, 0), card_text, font=font_main, align="center", spacing=14, stroke_width=stroke_width)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        # 画面下部（画面高の78%付近）に配置
        tx = (width - tw) // 2
        ty = int(height * 0.78) - (th // 2)

        # 読みやすさを高める半透明の薄いバックカプセル
        pad_x = int(font_size * 0.6)
        pad_y = int(font_size * 0.35)
        pill_box = [tx - pad_x, ty - pad_y, tx + tw + pad_x, ty + th + pad_y]
        draw.rounded_rectangle(pill_box, radius=16, fill=style["box_bg"])

        # スピーカーラベルタグ（ナレーション以外の場合のみ表示）
        if speaker and speaker not in ["ナレーション", "語り", "解説"]:
            tag_font_size = int(font_size * 0.58)
            font_tag = self._get_font(tag_font_size)
            badge_w = int(len(speaker) * (tag_font_size * 1.1) + 20)
            badge_h = int(tag_font_size * 1.7)
            tag_x = tx
            tag_y = ty - pad_y - badge_h - 4
            draw.rounded_rectangle(
                [(tag_x, tag_y), (tag_x + badge_w, tag_y + badge_h)],
                radius=8,
                fill=style["badge_bg"],
                outline=(255, 255, 255, 200),
                width=1
            )
            draw.text((tag_x + 10, tag_y + 3), speaker, fill=(255, 255, 255, 255), font=font_tag)

        # 高視認性マルチラインテキスト描画（滑らかな太字フチ取り＋白文字）
        draw.multiline_text(
            (tx, ty),
            card_text,
            font=font_main,
            fill=style["text_color"],
            align="center",
            spacing=14,
            stroke_width=stroke_width,
            stroke_fill=style["stroke_color"]
        )

        return overlay

    def _generate_artistic_backdrop(self, width: int, height: int, prompt: str, scene_num: int, genre: str = "story") -> Image.Image:
        """
        API未設定時・オフライン時のフォールバック背景
        開発者向け文字列（Prompt: ... 等）を一切排除し、シネマティックなアニメグラデーション背景を生成
        """
        base_colors = {
            "story": ((18, 24, 42), (40, 56, 92)),
            "business": ((12, 28, 48), (28, 64, 112)),
            "edoculture": ((38, 22, 16), (82, 54, 38)),
            "trivia": ((24, 18, 38), (64, 42, 98))
        }
        c1, c2 = base_colors.get(genre, base_colors["story"])

        img = Image.new("RGB", (width, height), c1)
        draw = ImageDraw.Draw(img)

        # スムーズなグラデーション描画
        for y in range(height):
            ratio = y / height
            r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
            g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
            b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # アニメ演出用グロー・スポットライト効果
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        cx, cy = int(width * 0.5), int(height * 0.4)
        for r_val in range(int(width * 0.6), 0, -8):
            alpha = max(0, int(18 * (r_val / (width * 0.6))))
            odraw.ellipse([cx - r_val, cy - r_val, cx + r_val, cy + r_val], fill=(255, 255, 255, alpha))

        # 集中線・光条効果（薄いアクセント）
        for angle_step in range(0, width, 60):
            odraw.line([(angle_step, 0), (width - angle_step, height)], fill=(255, 255, 255, 12), width=1)

        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
        return img

    async def generate_single_scene_assets(
        self,
        scene_data: Dict[str, Any],
        output_dir: Path,
        tts_engine: str = "edge",
        voice_name: Optional[str] = None,
        image_size: Tuple[int, int] = (1080, 1920),
        tts_params: Optional[Dict[str, Any]] = None,
        paid_gemini_api_key: Optional[str] = None,
        colab_worker_url: Optional[str] = None,
        fal_api_key: Optional[str] = None,
        replicate_api_token: Optional[str] = None,
        pexels_api_key: Optional[str] = None,
        characters: Optional[List[Dict[str, Any]]] = None,
        genre: str = "story",
        **kwargs
    ) -> Dict[str, Any]:
        """
        1シーン分の音声・ベース画像（Colab GPU / FLUX / Pexels優先）・高精度テロップ画像を生成（キャッシュ優先）
        """
        scene_num = scene_data.get("scene_number", 1)
        narration = scene_data.get("narration", "")
        speaker = scene_data.get("speaker", "ナレーション")
        raw_prompt = scene_data.get("character_prompt", "") or scene_data.get("visual_description", "")
        bgm_tag = scene_data.get("bgm_tag", "neutral")

        # --- キャラクター一貫性（Character Consistency）のアンカー結合 ---
        char_anchor = ""
        if characters and speaker and speaker not in ["ナレーション", "語り", "解説"]:
            for c_def in characters:
                if c_def.get("name") == speaker:
                    char_anchor = c_def.get("appearance_prompt_en", "")
                    break

        if char_anchor:
            prompt = f"{char_anchor}, {raw_prompt}, masterpiece, clean anime manga style, high quality"
        else:
            prompt = f"{raw_prompt}, masterpiece, anime manga art style, 8k"

        # ----------------------------------------------------
        # 1. 音声アセット生成（キャッシュチェック）
        # ----------------------------------------------------
        voice_params = {"engine": tts_engine, "voice": voice_name, **(tts_params or {})}
        cached_audio = self.cache_manager.get_audio(narration, voice_params)

        audio_out_path = output_dir / f"speech_{scene_num:03d}.mp3"

        if cached_audio:
            import shutil
            shutil.copy2(cached_audio, audio_out_path)
            logger.info(f"Scene {scene_num}: Loaded audio from cache.")
        else:
            try:
                tts_mgr = TTSManager(engine=tts_engine, voice_name=voice_name or "nanami", **(tts_params or {}))
                scenes_input = [{"narration": narration}]
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
        # 2. ベース画像アセット生成（Colab GPU / FLUX / Pexels / キャッシュ）
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
            image_generated = False

            # 優先順位 1: 完全無料 Google Colab (T4 GPU) ワーカー
            if colab_worker_url:
                try:
                    logger.info(f"Scene {scene_num}: Calling Google Colab free GPU worker...")
                    colab_client = ColabGpuClient(colab_worker_url)
                    colab_res = await colab_client.generate_image(prompt=prompt, width=img_w, height=img_h)
                    if colab_res.get("image_base64"):
                        import base64
                        from io import BytesIO
                        img_data = base64.b64decode(colab_res["image_base64"])
                        colab_img = Image.open(BytesIO(img_data)).convert("RGB")
                        colab_img.save(base_image_out_path, "PNG")
                        self.cache_manager.save_image(colab_img, prompt, img_params)
                        image_generated = True
                        logger.info(f"Scene {scene_num}: Generated via Google Colab Free GPU.")
                except Exception as colab_err:
                    logger.warning(f"Colab GPU generation failed: {colab_err}. Falling back to next engine...")

            # 優先順位 2: FLUX.1 [schnell] (fal.ai / Replicate)
            if not image_generated and (fal_api_key or replicate_api_token):
                try:
                    provider = "fal" if fal_api_key else "replicate"
                    key = fal_api_key or replicate_api_token
                    logger.info(f"Scene {scene_num}: Calling FLUX.1 [schnell] ({provider})...")
                    flux_client = FluxSchnellClient(provider=provider, api_key=key)
                    flux_res = await flux_client.generate_image(prompt=prompt, width=img_w, height=img_h)
                    if flux_res.get("image_url"):
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as client:
                            img_resp = await client.get(flux_res["image_url"])
                            if img_resp.status_code == 200:
                                from io import BytesIO
                                flux_img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                                flux_img.save(base_image_out_path, "PNG")
                                self.cache_manager.save_image(flux_img, prompt, img_params)
                                image_generated = True
                                logger.info(f"Scene {scene_num}: Generated via FLUX.1 [schnell].")
                except Exception as flux_err:
                    logger.warning(f"FLUX.1 generation failed: {flux_err}. Falling back to next engine...")

            # 優先順位 3: Pexels 素材
            if not image_generated and pexels_api_key:
                try:
                    logger.info(f"Scene {scene_num}: Searching Pexels B-roll...")
                    pexels_client = PexelsClient(api_key=pexels_api_key)
                    broll = await pexels_client.search_and_download_broll(
                        query=raw_prompt[:60],
                        orientation="portrait" if img_h > img_w else "landscape",
                        preferred_type="image",
                        output_dir=output_dir
                    )
                    if broll and Path(broll["file_path"]).exists():
                        p_img = Image.open(broll["file_path"]).convert("RGB").resize((img_w, img_h))
                        p_img.save(base_image_out_path, "PNG")
                        self.cache_manager.save_image(p_img, prompt, img_params)
                        image_generated = True
                        logger.info(f"Scene {scene_num}: Downloaded from Pexels.")
                except Exception as pexels_err:
                    logger.warning(f"Pexels fetch failed: {pexels_err}.")

            # 最終安全フォールバック: 開発テキストのない美麗シネマティック背景
            if not image_generated:
                logger.info(f"Scene {scene_num}: Using aesthetic animated backdrop.")
                art_img = self._generate_artistic_backdrop(img_w, img_h, prompt, scene_num, genre=genre)
                self.cache_manager.save_image(art_img, prompt, img_params)
                art_img.save(base_image_out_path, "PNG")

        # ----------------------------------------------------
        # 3. 高精度テロップ画像アセット生成（mode_a 仕様）
        # ----------------------------------------------------
        overlay_params = {"width": img_w, "height": img_h, "genre": genre}
        cached_overlay = self.cache_manager.get_overlay(narration, speaker, overlay_params)

        overlay_out_path = output_dir / f"overlay_{scene_num:03d}.png"

        if cached_overlay:
            import shutil
            shutil.copy2(cached_overlay, overlay_out_path)
            logger.info(f"Scene {scene_num}: Loaded overlay from cache.")
        else:
            pil_overlay = self._create_manga_bubble_overlay(img_w, img_h, speaker, narration, genre=genre)
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
