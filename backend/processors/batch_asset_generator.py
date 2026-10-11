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
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

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

# YouTubeクリエイター定番・極太日本語フォントマップ (backend/assets/fonts/ 配下)
YOUTUBE_FONT_FILES = {
    "DelaGothicOne": "DelaGothicOne-Regular.ttf",       # デラゴシック (超極太インパクト・Shorts王道)
    "ReggaeOne": "ReggaeOne-Regular.ttf",               # レゲエOne (江戸・歴史・和風・バトル系王道)
    "MochiyPopOne": "MochiyPopOne-Regular.ttf",         # モッチーポップ (雑学・ポップ解説系)
    "ShipporiMinchoB1": "ShipporiMinchoB1-ExtraBold.ttf", # しっぽり明朝B1極太 (感動・時代劇・シリアス系)
    "MPLUSRounded1c": "MPLUSRounded1c-Black.ttf",       # M PLUS Rounded 1c Black (極太丸ゴシック・万能)
    "RocknRollOne": "RocknRollOne-Regular.ttf",         # ロックンロールOne (スカッと・エンタメ系)
    "ZenMaruGothic": "ZenMaruGothic-Black.ttf",         # Zen丸ゴシック Black (親しみやすい太丸ゴシック)
    "RampartOne": "RampartOne-Regular.ttf",             # ランパートOne (立体シャドウ装飾書体)
}

GENRE_DEFAULT_FONT = {
    "story": "DelaGothicOne",
    "business": "DelaGothicOne",
    "edoculture": "ReggaeOne",
    "trivia": "MochiyPopOne"
}

GENRE_TELOP_STYLES = {
    "story": {
        "grad_top": (255, 255, 215, 255),
        "grad_mid": (255, 215, 0, 255),
        "grad_bottom": (240, 140, 0, 255),
        "outer_stroke": (8, 8, 12, 255),
        "inner_stroke": (65, 30, 0, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 235),
        "font_scale": 0.066,
        "max_chars_per_line": 11,
        "max_lines": 2
    },
    "business": {
        "grad_top": (255, 255, 255, 255),
        "grad_mid": (240, 248, 255, 255),
        "grad_bottom": (165, 210, 255, 255),
        "outer_stroke": (6, 12, 28, 255),
        "inner_stroke": (25, 65, 145, 255),
        "shadow_color": (0, 5, 15, 255),
        "glow_color": (0, 10, 30, 235),
        "font_scale": 0.064,
        "max_chars_per_line": 12,
        "max_lines": 2
    },
    "edoculture": {
        "grad_top": (255, 252, 225, 255),
        "grad_mid": (255, 210, 55, 255),
        "grad_bottom": (225, 115, 0, 255),
        "outer_stroke": (15, 8, 5, 255),
        "inner_stroke": (115, 25, 5, 255),
        "shadow_color": (10, 4, 0, 255),
        "glow_color": (0, 0, 0, 240),
        "font_scale": 0.066,
        "max_chars_per_line": 11,
        "max_lines": 2
    },
    "trivia": {
        "grad_top": (255, 255, 220, 255),
        "grad_mid": (255, 225, 0, 255),
        "grad_bottom": (245, 155, 0, 255),
        "outer_stroke": (10, 10, 15, 255),
        "inner_stroke": (55, 25, 0, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 235),
        "font_scale": 0.065,
        "max_chars_per_line": 11,
        "max_lines": 2
    }
}

PRO_SHORTS_TELOP_STYLES = {
    "shorts_impact_yellow": {
        "grad_top": (255, 255, 210, 255),
        "grad_mid": (255, 220, 0, 255),
        "grad_bottom": (240, 140, 0, 255),
        "outer_stroke": (8, 8, 12, 255),
        "inner_stroke": (65, 30, 0, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 235),
        "font_scale": 0.066,
        "max_chars_per_line": 11,
        "max_lines": 2
    },
    "shorts_gold_luxury": {
        "grad_top": (255, 255, 235, 255),
        "grad_mid": (250, 205, 65, 255),
        "grad_bottom": (195, 115, 10, 255),
        "outer_stroke": (12, 8, 4, 255),
        "inner_stroke": (90, 45, 5, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 240),
        "font_scale": 0.065,
        "max_chars_per_line": 11,
        "max_lines": 2
    },
    "shorts_crimson_flame": {
        "grad_top": (255, 255, 255, 255),
        "grad_mid": (255, 235, 195, 255),
        "grad_bottom": (255, 175, 95, 255),
        "outer_stroke": (20, 4, 4, 255),
        "inner_stroke": (195, 15, 20, 255),
        "shadow_color": (10, 0, 0, 255),
        "glow_color": (30, 0, 0, 240),
        "font_scale": 0.065,
        "max_chars_per_line": 11,
        "max_lines": 2
    },
    "shorts_neon_cyber": {
        "grad_top": (245, 255, 255, 255),
        "grad_mid": (100, 245, 255, 255),
        "grad_bottom": (0, 175, 245, 255),
        "outer_stroke": (6, 12, 24, 255),
        "inner_stroke": (0, 65, 130, 255),
        "shadow_color": (0, 10, 25, 255),
        "glow_color": (0, 35, 70, 235),
        "font_scale": 0.064,
        "max_chars_per_line": 12,
        "max_lines": 2
    },
    "shorts_clean_white": {
        "grad_top": (255, 255, 255, 255),
        "grad_mid": (248, 250, 252, 255),
        "grad_bottom": (215, 225, 238, 255),
        "outer_stroke": (10, 12, 18, 255),
        "inner_stroke": (35, 45, 65, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 235),
        "font_scale": 0.065,
        "max_chars_per_line": 12,
        "max_lines": 2
    },
    "manga_dialogue": {
        "grad_top": (255, 255, 220, 255),
        "grad_mid": (255, 220, 25, 255),
        "grad_bottom": (240, 145, 0, 255),
        "outer_stroke": (10, 12, 18, 255),
        "inner_stroke": (75, 25, 5, 255),
        "shadow_color": (0, 0, 0, 255),
        "glow_color": (0, 0, 0, 235),
        "font_scale": 0.064,
        "max_chars_per_line": 11,
        "max_lines": 2
    }
}

# ビジュアルスタイル（絵柄・タッチ）別プロンプト定義（ジャンルと独立して選択可能）
VISUAL_STYLE_CONFIGS: Dict[str, Dict[str, str]] = {
    "ukiyoe": {
        "name": "本格浮世絵・江戸木版画",
        "master_prefix": (
            "Authentic traditional Japanese Edo-period Ukiyo-e woodblock print portrait (Yakusha-e / Bijin-ga masterpiece "
            "in the style of Katsushika Hokusai, Utagawa Kuniyoshi, and Toshusai Sharaku)"
        ),
        "master_suffix": (
            "Hand-carved sumi ink brush outlines (kotsusen), flat mineral pigments (indigo ai-zuri, vermilion beni, yellow ochre, gofun white) "
            "printed on aged textured mulberry washi paper with subtle woodgrain baren marks, traditional narrow ukiyo-e eyes (hosoe), "
            "classic Edo facial proportions and kimono patterns. "
            "Strictly NO modern anime style, NO large shiny anime eyes, NO digital cel shading, NO 3D CGI, NO split panels, NO text."
        ),
        "scene_desc": (
            "authentic traditional Japanese Edo-period Ukiyo-e woodblock print (Nishiki-e masterpiece in the style of Katsushika Hokusai, "
            "Utagawa Hiroshige, and Utagawa Kuniyoshi), hand-printed on textured washi paper with bold sumi-ink brush outlines, "
            "flat mineral pigments, bokashi woodblock color gradation, and traditional Edo ukiyo-e human figures "
            "(strictly NO modern anime style, NO modern anime eyes, NO digital cel shading)"
        ),
        "motion_desc": (
            "Animate this traditional Japanese Edo-period Ukiyo-e woodblock print as a living moving Nishiki-e woodblock painting: "
            "expressive traditional kabuki-like posture and facial acting, flowing kimono sleeves in the wind, stylized Hokusai waves/clouds/cherry blossoms "
            "in motion, preserving authentic washi paper texture and sumi ink brush outlines without turning into modern anime or 3D"
        ),
        "ltx_motion_prefix": "moving traditional Japanese Edo Ukiyo-e woodblock print animation, Hokusai and Kuniyoshi nishiki-e style, sumi ink outlines on washi paper, expressive traditional motion"
    },
    "anime_modern": {
        "name": "王道シネマティックアニメ",
        "master_prefix": "Single waist-up high-end modern anime character portrait",
        "master_suffix": "Centered single character in a single unified frame, clean simple background, expressive face, modern cinematic anime masterpiece, 8k, sharp focus. Strictly NO split panels, NO character turnaround sheet, NO multiple angles, NO text.",
        "scene_desc": "high-definition modern cinematic anime illustration, vibrant lighting, Makoto Shinkai and ufotable inspired anime art style",
        "motion_desc": "Animate this exact anime scene with dynamic, expressive character acting, natural body and facial motion, breathing, wind in hair and clothes, and cinematic camera movement",
        "ltx_motion_prefix": "anime motion, expressive character acting, high quality modern anime animation"
    },
    "manga_dramatic": {
        "name": "劇画・青年漫画スタイル",
        "master_prefix": "Single waist-up dramatic gekiga seinen manga character portrait",
        "master_suffix": "Bold sumi ink cross-hatching, intense dramatic chiaroscuro lighting, rich color manga illustration, sharp detailed facial expression. Strictly NO split panels, NO comic frames, NO text.",
        "scene_desc": "dramatic Japanese gekiga seinen manga color illustration, bold ink linework, intense shadows and cinematic dramatic composition",
        "motion_desc": "Animate this dramatic gekiga manga scene with intense character acting, powerful camera movement, and dynamic atmospheric effects",
        "ltx_motion_prefix": "dramatic gekiga manga motion, intense character expression, cinematic lighting movement"
    },
    "watercolor_ink": {
        "name": "水墨画・淡彩日本画絵巻",
        "master_prefix": "Single waist-up traditional Japanese sumi-e ink wash and soft mineral watercolor (Nihonga) character portrait",
        "master_suffix": "Expressive calligraphy brush strokes, delicate watercolor washes on textured paper, serene artistic atmosphere. Strictly NO split panels, NO modern anime look, NO text.",
        "scene_desc": "traditional Japanese sumi-e ink wash and Nihonga mineral watercolor painting on textured paper, poetic atmosphere, fluid brushwork",
        "motion_desc": "Animate this Japanese sumi-e ink and watercolor painting with fluid brushstroke motion, gentle wind, and poetic traditional movement",
        "ltx_motion_prefix": "traditional Japanese sumi-e ink wash and watercolor painting in motion, poetic fluid movement"
    },
    "flat_2d_motion": {
        "name": "モダン2D解説イラスト",
        "master_prefix": "Single waist-up clean modern 2D vector explainer character portrait",
        "master_suffix": "Crisp geometric outlines, flat vibrant harmonious color palette, friendly clear expression, clean background. Strictly NO split panels, NO text.",
        "scene_desc": "clean modern 2D flat vector illustration for engaging visual storytelling, crisp lines, vibrant modern color palette",
        "motion_desc": "Animate this clean 2D illustration with smooth motion graphics, expressive character gesture, and clear visual movement",
        "ltx_motion_prefix": "smooth 2D motion graphics illustration, expressive character gesture, clean animation"
    },
    "photoreal_cinematic": {
        "name": "実写映画・シネマティック写実",
        "master_prefix": "Single waist-up photorealistic cinematic live-action portrait",
        "master_suffix": "Shot on ARRI Alexa 65, 85mm anamorphic lens, natural skin texture, shallow depth of field, cinematic studio lighting. Strictly NO split panels, NO text.",
        "scene_desc": "photorealistic cinematic live-action movie shot, ARRI Alexa 65, anamorphic lens, realistic lighting, 8k RAW cinema quality",
        "motion_desc": "Animate this photorealistic live-action movie scene with natural human acting, realistic physics, and smooth cinema camera movement",
        "ltx_motion_prefix": "photorealistic cinematic live-action movie motion, natural human acting, smooth camera movement"
    }
}


class BatchAssetGenerator:
    """
    長尺・Proショート用のアセット（音声・背景画像・AIアニメーション動画・プロ仕様テロップ演出画像）のバッチ生成およびキャッシュ制御モジュール
    """

    def __init__(self, cache_manager: Optional[AssetCacheManager] = None):
        self.cache_manager = cache_manager or AssetCacheManager()
        self.tts_manager = TTSManager()

    @staticmethod
    def _clean_scene_prompt_for_image(raw_prompt: str, visual_style: Optional[str] = None) -> str:
        """
        ト書き・視覚描写に含まれる「画面には『…』のテロップが浮かび上がり」等のメタ文字描画指示を除去し、
        画像生成AIがイラスト内に文字化け漢字を描画するのを防ぐ。
        さらに visual_style が ukiyoe 等の非アニメスタイルの場合、台本内のアニメ指定語句を除去する。
        """
        if not raw_prompt:
            return ""
        cleaned = raw_prompt
        cleaned = re.sub(r'画面(中央|上部|下部|全体)?には?[「『][^」』]*[」』]の?(キレのある|巨大な|赤い|金色の)?(テロップ|文字|字幕)が[^。、]*[。、]?', '', cleaned)
        cleaned = re.sub(r'[「『][^」』]*[」』]という(テロップ|文字|字幕)[^。、]*[。、]?', '', cleaned)
        cleaned = re.sub(r'(テロップ|字幕|テキスト)が(浮かび上がり|表示され|入り|重なり)[^。、]*[。、]?', '', cleaned)
        if visual_style in ("ukiyoe", "watercolor_ink", "photoreal_cinematic"):
            cleaned = re.sub(r'\b(modern\s+anime|anime\s+style|anime\s+girl|anime\s+boy|anime\s+character|anime|manga\s+style|cel[- ]shaded|cel[- ]shading|2d\s+anime)\b', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'(現代アニメ調|アニメ調|アニメ風|マンガ風|セル画風)', '', cleaned)
        return cleaned.strip()

    @staticmethod
    def _remove_split_panels_if_any(img: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
        """
        Nano Banana 等がリファレンス画像を引きずって「左側に立ち絵パネル・右側に本編シーン」のような
        2分割（スプリットパネル）や外枠ボーダーを生成した場合、境界線を自動検出してメイン領域のみを
        フルスクリーン（target_size）へクロップ＆リサイズする。
        """
        try:
            rgb = img.convert("RGB")
            arr = np.array(rgb, dtype=np.float32)
            h, w, _ = arr.shape
            if w < 128 or h < 128:
                return rgb.resize(target_size, Image.Resampling.LANCZOS)

            gray = np.mean(arr, axis=2)
            col_mean = np.mean(gray, axis=0)
            col_std = np.std(gray, axis=0)
            col_diff = np.mean(np.abs(np.diff(gray, axis=1)), axis=0)

            # 1. 画面中間領域 (18%〜82%) にある縦方向の分割線（黒線・白線・急激な輝度境界）を検出
            v_start = int(w * 0.18)
            v_end = int(w * 0.82)
            split_cols = []
            for x in range(v_start, v_end):
                is_dark_line = (col_mean[x] < 35.0 and col_std[x] < 26.0)
                is_white_line = (col_mean[x] > 238.0 and col_std[x] < 18.0)
                is_sharp_seam = (x < w - 1 and col_diff[x] > 44.0 and (col_std[x] < 32.0 or col_mean[max(0, x-1)] < 45.0 or col_mean[min(w-1, x+1)] < 45.0))
                if is_dark_line or is_white_line or is_sharp_seam:
                    split_cols.append(x)

            if split_cols:
                split_x = int(np.median(split_cols))
                pad = max(12, int(w * 0.015))
                if split_x < w * 0.5:
                    # 左側パネル（リファレンス立ち絵）を除去し、右側メインシーンを採用
                    new_left = min(w - 32, split_x + pad)
                    arr = arr[:, new_left:, :]
                    logger.info(f"[SplitPanelGuard] Cropped left reference panel at x={split_x} (kept x={new_left}..{w})")
                else:
                    # 右側パネルを除去し、左側メインシーンを採用
                    new_right = max(32, split_x - pad)
                    arr = arr[:, :new_right, :]
                    logger.info(f"[SplitPanelGuard] Cropped right split panel at x={split_x} (kept x=0..{new_right})")

            # 2. 上下中間領域 (22%〜78%) にある横方向の分割線を検出
            h2, w2, _ = arr.shape
            gray2 = np.mean(arr, axis=2)
            row_mean = np.mean(gray2, axis=1)
            row_std = np.std(gray2, axis=1)
            h_start = int(h2 * 0.22)
            h_end = int(h2 * 0.78)
            split_rows = [
                y for y in range(h_start, h_end)
                if (row_mean[y] < 30.0 and row_std[y] < 22.0) or (row_mean[y] > 240.0 and row_std[y] < 16.0)
            ]
            if split_rows:
                split_y = int(np.median(split_rows))
                pad_y = max(12, int(h2 * 0.012))
                if split_y < h2 * 0.5:
                    arr = arr[min(h2 - 32, split_y + pad_y):, :, :]
                else:
                    arr = arr[:max(32, split_y - pad_y), :, :]
                logger.info(f"[SplitPanelGuard] Cropped horizontal split panel at y={split_y}")

            # 3. 外周の漫画枠線・余白ボーダー（端から10%以内の黒枠線）を自動トリミング
            h3, w3, _ = arr.shape
            gray3 = np.mean(arr, axis=2)
            r_mean = np.mean(gray3, axis=1)
            r_std = np.std(gray3, axis=1)
            c_mean = np.mean(gray3, axis=0)
            c_std = np.std(gray3, axis=0)

            top = 0
            for y in range(int(h3 * 0.10), 0, -1):
                if r_mean[y] < 42.0 and r_std[y] < 35.0:
                    top = y + 4
                    break
            bottom = h3
            for y in range(int(h3 * 0.90), h3):
                if r_mean[y] < 42.0 and r_std[y] < 35.0:
                    bottom = y - 4
                    break
            left = 0
            for x in range(int(w3 * 0.10), 0, -1):
                if c_mean[x] < 42.0 and c_std[x] < 35.0:
                    left = x + 4
                    break
            right = w3
            for x in range(int(w3 * 0.90), w3):
                if c_mean[x] < 42.0 and c_std[x] < 35.0:
                    right = x - 4
                    break

            if (top > 0 or bottom < h3 or left > 0 or right < w3) and (bottom - top) > h3 * 0.72 and (right - left) > w3 * 0.72:
                arr = arr[top:bottom, left:right, :]
                logger.info(f"[SplitPanelGuard] Trimmed outer frame border: top={top}, bottom={bottom}, left={left}, right={right}")

            cleaned_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            return cleaned_img.resize(target_size, Image.Resampling.LANCZOS)
        except Exception as e:
            logger.warning(f"[SplitPanelGuard] Fallback resize due to error: {e}")
            return img.convert("RGB").resize(target_size, Image.Resampling.LANCZOS)

    @classmethod
    def clean_japanese_text(cls, text: str) -> str:
        """テキストの余分な改行や変な記号を正規化し、行頭の孤立記号や外側の不要なカギ括弧を整形"""
        t = text.replace('\\n', ' ').replace('\r', ' ').replace('\n', ' ')
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'」[。、.]+', '」', t)
        t = re.sub(r'^[」』）)\s。、？！?!]+', '', t)
        t = re.sub(r'[「『（(\s]+$', '', t)
        # 先頭と末尾が単一の「...」で囲まれている場合は外側の「」を外してテロップの左右バランスを整える
        if t.startswith("「") and t.endswith("」") and t.count("「") == 1 and t.count("」") == 1:
            t = t[1:-1].strip()
        return t

    @classmethod
    def split_text_into_cards(cls, text: str, max_lines_per_card: int = 2, max_chars_per_line: int = 11) -> List[str]:
        """文脈スコアリングと禁則処理に基づき、自然な改行位置で1〜2行ずつのテロップカードに分割"""
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

    def _get_font(self, size: int, font_key: Optional[str] = None, genre: str = "story") -> ImageFont.ImageFont:
        """
        YouTubeクリエイター定番の極太日本語フォント（backend/assets/fonts/）を最優先で取得
        """
        fonts_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        selected_key = font_key if (font_key and font_key in YOUTUBE_FONT_FILES) else GENRE_DEFAULT_FONT.get(genre, "DelaGothicOne")

        candidates: List[Union[Path, str, None]] = []
        if selected_key in YOUTUBE_FONT_FILES:
            candidates.append(fonts_dir / YOUTUBE_FONT_FILES[selected_key])

        # フォールバック順（すべて極太YouTubeフォントを優先）
        for fname in YOUTUBE_FONT_FILES.values():
            fpath = fonts_dir / fname
            if fpath not in candidates:
                candidates.append(fpath)

        candidates.extend([
            getattr(config, "SUBTITLE_FONT", None),
            "C:\\Windows\\Fonts\\YuGothB.ttc",
            "C:\\Windows\\Fonts\\meiryob.ttc",
            "C:\\Windows\\Fonts\\meiryo.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ])

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

    def _create_single_card_overlay(
        self,
        width: int,
        height: int,
        speaker: str,
        card_text: str,
        style: Dict[str, Any],
        font_size_key: str = "medium",
        telop_font: Optional[str] = None,
        genre: str = "story"
    ) -> Image.Image:
        """
        プロYouTube Shorts / 放送局クオリティの5層マルチレイヤーテロップ描画
        - 話者名バッジ（辰吉等）および不格好なグレー四角背景ボックスは一切描画しない
        - (1) 背面ガウシアンブラー・ダークオーラ影
        - (2) 3D押し出しハードドロップシャドウ
        - (3) 極太漆黒アウターストローク
        - (4) テーマ色インナーアクセントストローク（二重フチ）
        - (5) 1行ごとの縦方向メタリック・グロスグラデーション塗り
        """
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if not card_text or not card_text.strip():
            return overlay

        lines = [line.strip() for line in card_text.split("\n") if line.strip()]
        if not lines:
            return overlay

        base_scale = style.get("font_scale", 0.066)
        if font_size_key == "large":
            base_scale *= 1.10
        elif font_size_key == "xlarge":
            base_scale *= 1.18
        elif font_size_key == "small":
            base_scale *= 0.88

        font_size = int(width * base_scale)
        max_text_width = int(width * 0.90)
        dummy_draw = ImageDraw.Draw(overlay)

        # 画面幅90%以内に収まる最大フォントサイズを自動算出
        while font_size > 32:
            font_main = self._get_font(font_size, font_key=telop_font, genre=genre)
            outer_sw = max(12, int(font_size * 0.24))
            max_lw = 0
            for line in lines:
                bb = dummy_draw.textbbox((0, 0), line, font=font_main, stroke_width=outer_sw)
                max_lw = max(max_lw, bb[2] - bb[0])
            if max_lw <= max_text_width:
                break
            font_size -= 2

        font_main = self._get_font(font_size, font_key=telop_font, genre=genre)
        outer_sw = max(12, int(font_size * 0.24))
        inner_sw = max(4, int(font_size * 0.08))
        line_gap = max(10, int(font_size * 0.16))

        line_metrics = []
        total_h = 0
        for idx, line in enumerate(lines):
            bb = dummy_draw.textbbox((0, 0), line, font=font_main, stroke_width=outer_sw)
            lw = bb[2] - bb[0]
            lh = bb[3] - bb[1]
            line_metrics.append((line, lw, lh, bb[0], bb[1]))
            total_h += lh
            if idx < len(lines) - 1:
                total_h += line_gap

        # Shortsの黄金視認領域（画面高75%中心）に配置
        base_y = int(height * 0.75) - (total_h // 2)

        glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        stroke_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        stroke_draw = ImageDraw.Draw(stroke_layer)

        fill_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        outer_color = style.get("outer_stroke", (8, 8, 12, 255))
        inner_color = style.get("inner_stroke", (65, 30, 0, 255))
        shadow_color = style.get("shadow_color", (0, 0, 0, 255))
        glow_color = style.get("glow_color", (0, 0, 0, 235))
        c1 = style.get("grad_top", (255, 255, 210, 255))
        c2 = style.get("grad_mid", (255, 220, 0, 255))
        c3 = style.get("grad_bottom", (240, 140, 0, 255))

        curr_y = base_y
        for line, lw, lh, bx0, by0 in line_metrics:
            lx = (width - lw) // 2 - bx0
            ly = curr_y - by0

            # Layer 1: 背面ガウシアンオーラ影（四角い背景ボックス無しでどんな明暗の背景でも100%浮かび上がらせる）
            glow_draw.text(
                (lx, ly + 4),
                line,
                font=font_main,
                fill=glow_color,
                stroke_width=outer_sw + 10,
                stroke_fill=glow_color
            )

            # Layer 2: 3D押し出しハードドロップシャドウ
            sh_y = max(6, int(font_size * 0.12))
            sh_x = max(4, int(font_size * 0.07))
            for ox, oy in [(0, sh_y), (sh_x, sh_y), (-sh_x // 2, sh_y), (0, sh_y // 2)]:
                stroke_draw.text(
                    (lx + ox, ly + oy),
                    line,
                    font=font_main,
                    fill=shadow_color,
                    stroke_width=outer_sw,
                    stroke_fill=shadow_color
                )

            # Layer 3: 極太漆黒アウターストローク
            stroke_draw.text(
                (lx, ly),
                line,
                font=font_main,
                fill=outer_color,
                stroke_width=outer_sw,
                stroke_fill=outer_color
            )

            # Layer 4: 二重フチ用インナーアクセントストローク
            stroke_draw.text(
                (lx, ly),
                line,
                font=font_main,
                fill=inner_color,
                stroke_width=inner_sw,
                stroke_fill=inner_color
            )

            # Layer 5: 1行ごとの縦方向メタリック・グロスグラデーション塗り
            mask_pad = outer_sw * 2
            mw = max(1, lw + mask_pad * 2)
            mh = max(1, lh + mask_pad * 2)
            line_mask = Image.new("L", (mw, mh), 0)
            mask_draw = ImageDraw.Draw(line_mask)
            mask_draw.text((mask_pad - bx0, mask_pad - by0), line, font=font_main, fill=255)

            grad_img = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
            grad_draw = ImageDraw.Draw(grad_img)
            t_top = mask_pad
            t_bot = mask_pad + lh
            span = max(1, t_bot - t_top)

            for gy in range(mh):
                t = max(0.0, min(1.0, (gy - t_top) / span))
                if t < 0.45:
                    u = t / 0.45
                    col = tuple(int(c1[k] * (1.0 - u) + c2[k] * u) for k in range(4))
                else:
                    u = (t - 0.45) / 0.55
                    col = tuple(int(c2[k] * (1.0 - u) + c3[k] * u) for k in range(4))
                grad_draw.line([(0, gy), (mw, gy)], fill=col)

            paste_x = (width - lw) // 2 - mask_pad
            paste_y = curr_y - mask_pad
            fill_layer.paste(grad_img, (paste_x, paste_y), line_mask)

            curr_y += lh + line_gap

        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=12))
        overlay = Image.alpha_composite(overlay, glow_layer)
        overlay = Image.alpha_composite(overlay, stroke_layer)
        overlay = Image.alpha_composite(overlay, fill_layer)

        return overlay

    def _create_manga_bubble_overlays_sequence(
        self,
        width: int,
        height: int,
        speaker: str,
        narration: str,
        duration: float,
        output_dir: Path,
        scene_num: int,
        genre: str = "story",
        telop_style: Optional[str] = None,
        font_size_key: str = "medium",
        telop_font: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        長文ナレーションを最適なカード群に自動分割し、音声尺に合わせて順次切り替わるテロップ画像シーケンスを出力
        """
        if not narration or not narration.strip():
            return []

        style_key = telop_style or "shorts_impact_yellow"
        style = PRO_SHORTS_TELOP_STYLES.get(style_key) or GENRE_TELOP_STYLES.get(genre, GENRE_TELOP_STYLES["story"])

        max_chars = style.get("max_chars_per_line", 11)
        max_lines = style.get("max_lines", 2)

        cards = self.split_text_into_cards(narration, max_lines_per_card=max_lines, max_chars_per_line=max_chars)
        if not cards:
            return []

        total_dur = max(float(duration), 1.0)
        card_lengths = [max(len(c.replace("\n", "").strip()), 1) for c in cards]
        total_chars = sum(card_lengths)

        result_cards = []
        curr_t = 0.0

        for idx, card_text in enumerate(cards):
            clen = card_lengths[idx]
            if idx == len(cards) - 1:
                card_dur = max(total_dur - curr_t, 0.4)
            else:
                card_dur = total_dur * (clen / max(total_chars, 1))

            start_t = round(curr_t, 2)
            end_t = round(min(curr_t + card_dur, total_dur), 2)
            curr_t = end_t

            card_img = self._create_single_card_overlay(
                width=width,
                height=height,
                speaker=speaker,
                card_text=card_text,
                style=style,
                font_size_key=font_size_key,
                telop_font=telop_font,
                genre=genre
            )

            card_filename = f"overlay_{scene_num:03d}_card_{idx:02d}.png"
            card_path = output_dir / card_filename
            card_img.save(card_path, "PNG")

            result_cards.append({
                "image_path": str(card_path),
                "start_time": start_t,
                "end_time": end_t,
                "text": card_text,
                "card_index": idx
            })

        return result_cards

    def _create_manga_bubble_overlay(
        self,
        width: int,
        height: int,
        speaker: str,
        narration: str,
        genre: str = "story",
        telop_style: Optional[str] = None,
        telop_font: Optional[str] = None
    ) -> Image.Image:
        """後方互換用：最初のカード1枚を描画"""
        style_key = telop_style or "shorts_impact_yellow"
        style = PRO_SHORTS_TELOP_STYLES.get(style_key) or GENRE_TELOP_STYLES.get(genre, GENRE_TELOP_STYLES["story"])
        cards = self.split_text_into_cards(narration, max_lines_per_card=style.get("max_lines", 2), max_chars_per_line=style.get("max_chars_per_line", 11))
        card_text = cards[0] if cards else narration
        return self._create_single_card_overlay(width, height, speaker, card_text, style, telop_font=telop_font, genre=genre)

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

    async def _generate_with_gemini_nanobanana(
        self,
        api_key: str,
        prompt: str,
        ref_image_base64: Optional[str] = None,
        target_size: Tuple[int, int] = (1080, 1920),
        aspect_ratio: str = "9:16",
        visual_style: str = "anime_modern"
    ) -> Optional[Image.Image]:
        """
        有料 Gemini API の Nano Banana 最新フラッグシップモデル群
        (gemini-3.1-flash-image / gemini-nano-banana-2.1 / gemini-3-pro-image / gemini-2.5-flash-image)
        を用いて、指定されたスタイル（visual_style: ukiyoe / anime_modern / manga_dramatic 等）に完全準拠した
        単一フルスクリーン構図のマスター画像および一貫性のあるシーン画像を生成する。
        生成後は _remove_split_panels_if_any により分割パネルや外枠ボーダーを完全排除する。
        """
        if not api_key or not api_key.strip():
            return None

        clean_key = api_key.strip()
        clean_prompt = self._clean_scene_prompt_for_image(prompt, visual_style=visual_style)
        style_cfg = VISUAL_STYLE_CONFIGS.get(visual_style or "anime_modern", VISUAL_STYLE_CONFIGS["anime_modern"])
        scene_style_desc = style_cfg["scene_desc"]

        ukiyoe_strict_directive = ""
        if visual_style == "ukiyoe":
            ukiyoe_strict_directive = (
                " AUTHENTIC EDO UKIYO-E MANDATE: Render strictly as an authentic 18th-19th century Japanese Edo-period "
                "Ukiyo-e woodblock print (Nishiki-e) in the tradition of Katsushika Hokusai, Utagawa Hiroshige, "
                "Utagawa Kuniyoshi, and Toshusai Sharaku. Use visible hand-carved sumi-e black woodblock ink outlines, "
                "flat mineral pigments (Prussian blue/bero-ai, vermilion/shu-iro, yellow ochre, mineral green) with traditional "
                "bokashi woodblock ink gradation on aged fibrous handmade mulberry washi paper, and classical Edo ukiyo-e "
                "kabuki/bijin-ga facial proportions (slender painted eyes, elongated classical nose, expressive traditional woodblock posture). "
                "STRICTLY FORBIDDEN: DO NOT use modern anime style, DO NOT draw large glossy anime eyes, DO NOT use modern digital cel-shading or 3D CGI."
            )

        import base64
        from io import BytesIO
        import httpx

        base_url = "https://generativelanguage.googleapis.com/v1beta"

        # Nano Banana 2 / 2.1 / Pro 最優先モデルリスト
        priority_candidates = [
            "gemini-3.1-flash-image",
            "gemini-3.1-flash-image-preview",
            "gemini-nano-banana-2.1",
            "gemini-3-pro-image",
            "gemini-3-pro-image-preview",
            "gemini-2.5-flash-image",
            "gemini-2.5-flash-image-preview",
            "gemini-2.0-flash-exp-image-generation",
            "imagen-3.0-generate-002",
            "imagen-3.0-generate-001",
        ]

        if not hasattr(self, "_cached_nanobanana_models"):
            self._cached_nanobanana_models = {}

        models_to_try: List[str] = self._cached_nanobanana_models.get(clean_key, [])

        async with httpx.AsyncClient(timeout=75.0) as client:
            if not models_to_try:
                try:
                    m_resp = await client.get(f"{base_url}/models?key={clean_key}", timeout=10.0)
                    if m_resp.status_code == 200:
                        m_data = m_resp.json()
                        avail = [
                            m.get("name", "").replace("models/", "")
                            for m in m_data.get("models", [])
                        ]
                        for cand in priority_candidates:
                            if cand in avail and cand not in models_to_try:
                                models_to_try.append(cand)
                        for m_name in avail:
                            if ("image" in m_name.lower() or "nano" in m_name.lower() or "imagen" in m_name.lower()) and m_name not in models_to_try:
                                models_to_try.append(m_name)
                except Exception as disc_err:
                    logger.warning(f"[NanoBanana] Model discovery warning: {disc_err}")

                if not models_to_try:
                    models_to_try = priority_candidates[:6]
                self._cached_nanobanana_models[clean_key] = models_to_try
                logger.info(f"[NanoBanana] Discovered candidate image models: {models_to_try[:5]}")

            for model_name in models_to_try:
                try:
                    # Imagen 系 (:predict エンドポイント)
                    if model_name.startswith("imagen-"):
                        pred_url = f"{base_url}/models/{model_name}:predict?key={clean_key}"
                        pred_payload = {
                            "instances": [{
                                "prompt": (
                                    f"Single full-bleed {aspect_ratio} artwork ({scene_style_desc}): {clean_prompt}.{ukiyoe_strict_directive} "
                                    f"Strictly ONE unified scene filling the entire canvas edge-to-edge. "
                                    f"NO split screen, NO panels, NO borders, NO text, NO letters."
                                )
                            }],
                            "parameters": {
                                "sampleCount": 1,
                                "aspectRatio": aspect_ratio,
                                "outputOptions": {"mimeType": "image/png"}
                            }
                        }
                        p_resp = await client.post(pred_url, json=pred_payload)
                        if p_resp.status_code == 200:
                            p_data = p_resp.json()
                            preds = p_data.get("predictions", [])
                            if preds and preds[0].get("bytesBase64Encoded"):
                                raw_bytes = base64.b64decode(preds[0]["bytesBase64Encoded"])
                                raw_img = Image.open(BytesIO(raw_bytes)).convert("RGB")
                                img = self._remove_split_panels_if_any(raw_img, target_size)
                                logger.info(f"[NanoBanana] Generated image via Imagen model: {model_name} (style={visual_style})")
                                return img
                        continue

                    # Gemini Nano Banana 系 (:generateContent エンドポイント + リファレンス画像 inlineData 対応)
                    gen_url = f"{base_url}/models/{model_name}:generateContent?key={clean_key}"
                    parts: List[Dict[str, Any]] = []

                    if ref_image_base64:
                        clean_b64 = ref_image_base64.split(",")[-1] if "," in ref_image_base64 else ref_image_base64
                        parts.append({
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": clean_b64
                            }
                        })
                        text_instruction = (
                            f"Create ONE SINGLE full-screen {aspect_ratio} scene artwork in this exact art style ({scene_style_desc}) "
                            f"for this moment: {clean_prompt}.{ukiyoe_strict_directive} "
                            f"CRITICAL RULES: "
                            f"1) Use the attached reference image ONLY to match the character's identity, hairstyle, clothing design, and {visual_style} art style. "
                            f"2) NEVER copy the layout of the reference image and NEVER place the reference character portrait in a separate panel on the left or right side. "
                            f"3) The entire {aspect_ratio} canvas must be ONE unified composition edge-to-edge with NO split-screen, NO comic panel dividers, NO white borders, and NO picture-in-picture. "
                            f"4) Do NOT render any text, kanji, subtitles, cartouches, letters, or speech bubbles anywhere in the artwork."
                        )
                    else:
                        text_instruction = (
                            f"Create ONE SINGLE full-screen {aspect_ratio} artwork in this exact art style ({scene_style_desc}): {clean_prompt}.{ukiyoe_strict_directive} "
                            f"CRITICAL RULES: Render ONE unified composition filling the entire {aspect_ratio} canvas edge-to-edge. "
                            f"NO split-screen, NO multiple panels, NO character sheet layout, NO borders, and NO text, kanji, cartouches, or speech bubbles."
                        )

                    parts.append({"text": text_instruction})

                    payload_with_modalities = {
                        "contents": [{"parts": parts}],
                        "generationConfig": {
                            "responseModalities": ["TEXT", "IMAGE"]
                        }
                    }
                    g_resp = await client.post(gen_url, json=payload_with_modalities)

                    if g_resp.status_code != 200:
                        payload_simple = {"contents": [{"parts": parts}]}
                        g_resp = await client.post(gen_url, json=payload_simple)

                    if g_resp.status_code == 200:
                        g_data = g_resp.json()
                        for cand in g_data.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                inline = part.get("inlineData") or part.get("inline_data")
                                if inline and inline.get("data"):
                                    raw_bytes = base64.b64decode(inline["data"])
                                    raw_img = Image.open(BytesIO(raw_bytes)).convert("RGB")
                                    img = self._remove_split_panels_if_any(raw_img, target_size)
                                    logger.info(
                                        f"[NanoBanana] Successfully generated single-frame image via {model_name} "
                                        f"(style={visual_style}, ref_image={bool(ref_image_base64)}, size={target_size})"
                                    )
                                    return img
                    else:
                        err_snip = g_resp.text[:200] if g_resp.text else str(g_resp.status_code)
                        logger.warning(f"[NanoBanana] Model {model_name} returned HTTP {g_resp.status_code}: {err_snip}")
                except Exception as model_err:
                    logger.warning(f"[NanoBanana] Model {model_name} error: {model_err}")
                    continue

        return None

    async def _animate_image_with_veo(
        self,
        api_key: str,
        image_path: Path,
        prompt: str,
        output_video_path: Path,
        aspect_ratio: str = "9:16",
        visual_style: str = "anime_modern"
    ) -> bool:
        """
        Stage 2 (Image-to-Video):
        生成済みのシーン画像 (bg_xxx.png) をリファレンス（入力フレーム）として渡し、
        有料 Gemini API の Veo 3.1 / Veo 3.0 モデルで本物のアニメーション動画 (clip_xxx.mp4) に変換する。
        visual_style (ukiyoe 等) の画風・木版画質感を崩さずにアニメーション化する。
        """
        if not api_key or not api_key.strip() or not image_path.exists():
            return False

        clean_key = api_key.strip()
        clean_prompt = self._clean_scene_prompt_for_image(prompt, visual_style=visual_style)
        style_cfg = VISUAL_STYLE_CONFIGS.get(visual_style or "anime_modern", VISUAL_STYLE_CONFIGS["anime_modern"])
        import base64
        import httpx

        try:
            img_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        except Exception as read_err:
            logger.warning(f"[Veo I2V] Failed to read reference scene image {image_path}: {read_err}")
            return False

        base_url = "https://generativelanguage.googleapis.com/v1beta"
        veo_models = [
            "veo-3.1-fast-generate-preview",
            "veo-3.1-generate-preview",
        ]

        motion_prompt = (
            f"{style_cfg['motion_desc']}: {clean_prompt}. "
            f"Maintain strict character identity and exact {style_cfg['name']} art style from the reference frame. "
            f"No text, no kanji, no subtitles."
        )

        async with httpx.AsyncClient(timeout=90.0) as client:
            for model_name in veo_models:
                url = f"{base_url}/models/{model_name}:predictLongRunning?key={clean_key}"
                payload = {
                    "instances": [
                        {
                            "prompt": motion_prompt,
                            "image": {
                                "bytesBase64Encoded": img_b64,
                                "mimeType": "image/png"
                            }
                        }
                    ],
                    "parameters": {
                        "aspectRatio": aspect_ratio,
                        "sampleCount": 1
                    }
                }
                try:
                    resp = await client.post(url, json=payload, timeout=35.0)
                    if resp.status_code == 429:
                        logger.info(f"[Veo I2V] Model {model_name} rate-limited (429), trying next Veo model...")
                        continue
                    if resp.status_code != 200:
                        logger.warning(f"[Veo I2V] Model {model_name} returned HTTP {resp.status_code}: {resp.text[:180]}")
                        continue

                    op_data = resp.json()
                    op_name = op_data.get("name")
                    if not op_name:
                        continue

                    logger.info(f"[Veo I2V] Started Image-to-Video animation via {model_name} (style={visual_style}): {op_name}")
                    poll_url = f"{base_url}/{op_name}?key={clean_key}"

                    for _ in range(36):  # 最大約180秒ポーリング
                        await asyncio.sleep(5.0)
                        p_resp = await client.get(poll_url, timeout=20.0)
                        if p_resp.status_code != 200:
                            continue
                        p_data = p_resp.json()
                        if not p_data.get("done"):
                            continue

                        if "error" in p_data:
                            logger.warning(f"[Veo I2V] Operation error on {model_name}: {p_data['error']}")
                            return False

                        # 生成完了した動画URIまたはBase64を抽出
                        gen_resp = p_data.get("response", {}).get("generateVideoResponse", {})
                        samples = gen_resp.get("generatedSamples", [])
                        if not samples:
                            samples = p_data.get("response", {}).get("videos", [])

                        for sample in samples:
                            vid_obj = sample.get("video", sample)
                            vid_b64 = vid_obj.get("bytesBase64Encoded")
                            vid_uri = vid_obj.get("uri")
                            if vid_b64:
                                output_video_path.write_bytes(base64.b64decode(vid_b64))
                                if output_video_path.exists() and output_video_path.stat().st_size > 1000:
                                    logger.info(f"[Veo I2V] Animation video saved via {model_name} (base64): {output_video_path.name}")
                                    return True
                            elif vid_uri:
                                dl_url = f"{vid_uri}&key={clean_key}" if "?" in vid_uri else f"{vid_uri}?key={clean_key}"
                                dl_resp = await client.get(dl_url, follow_redirects=True, timeout=60.0)
                                if dl_resp.status_code == 200 and len(dl_resp.content) > 1000:
                                    output_video_path.write_bytes(dl_resp.content)
                                    logger.info(f"[Veo I2V] Animation video downloaded via {model_name}: {output_video_path.name} ({len(dl_resp.content)} bytes)")
                                    return True
                        return False
                except Exception as veo_err:
                    logger.warning(f"[Veo I2V] Error with {model_name}: {veo_err}")
                    continue

        return False

    async def generate_character_masters(
        self,
        characters: List[Dict[str, Any]],
        output_dir: Path,
        colab_worker_url: Optional[str] = None,
        fal_api_key: Optional[str] = None,
        replicate_api_token: Optional[str] = None,
        paid_gemini_api_key: Optional[str] = None,
        visual_style: str = "anime_modern"
    ) -> Dict[str, Path]:
        """
        登場人物ごとの「視覚的基準となるマスター画像（単一キャラクターのバストアップ1枚絵）」を
        指定された visual_style (ukiyoe / anime_modern / manga_dramatic 等) で事前確定生成。
        ※ 2分割パネルや三面図（concept sheet / turnaround）になるのを防ぐため、単一ポートレートとして生成する
        """
        char_dir = output_dir / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)
        master_map = {}

        if not characters:
            return master_map

        style_key = visual_style or "anime_modern"
        style_cfg = VISUAL_STYLE_CONFIGS.get(style_key, VISUAL_STYLE_CONFIGS["anime_modern"])

        for char in characters:
            name = char.get("name", "")
            if not name or name in ["ナレーション", "語り", "解説"]:
                continue

            out_path = char_dir / f"master_{style_key}_{name}.png"
            legacy_path = char_dir / f"master_{name}.png"
            if out_path.exists() and out_path.stat().st_size > 1000:
                master_map[name] = out_path
                logger.info(f"Reused existing character master checkpoint: {out_path.name}")
                continue
            if legacy_path.exists() and legacy_path.stat().st_size > 1000:
                master_map[name] = legacy_path
                logger.info(f"Reused existing character master checkpoint: {legacy_path.name}")
                continue

            appearance = self._clean_scene_prompt_for_image(char.get("appearance_prompt_en", ""), visual_style=style_key)
            master_prompt = (
                f"{style_cfg['master_prefix']} of {name}, {appearance}. "
                f"Centered single figure in a single unified frame. "
                f"{style_cfg['master_suffix']}"
            )

            generated = False

            # 0. 最優先: Gemini API Nano Banana モデルで単一キャラクターマスター画像を生成 (1:1 正方形 1024x1024)
            if paid_gemini_api_key:
                try:
                    c_img = await self._generate_with_gemini_nanobanana(
                        api_key=paid_gemini_api_key,
                        prompt=master_prompt,
                        ref_image_base64=None,
                        target_size=(1024, 1024),
                        aspect_ratio="1:1",
                        visual_style=style_key
                    )
                    if c_img:
                        c_img.save(out_path, "PNG")
                        generated = True
                        logger.info(f"Visual Master Image generated via Gemini Nano Banana ({style_key}): {name}")
                except Exception as e:
                    logger.warning(f"Character master gen via Gemini Nano Banana failed for {name}: {e}")

            # 1. FLUX.1 で実画像マスター生成（クレジットがある場合のみ）
            if not generated and (fal_api_key or replicate_api_token):
                try:
                    provider = "fal" if fal_api_key else "replicate"
                    flux_client = FluxSchnellClient(provider=provider, api_key=fal_api_key or replicate_api_token)
                    res = await flux_client.generate_image(prompt=master_prompt, width=1024, height=1024)
                    if res.get("image_url"):
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as client:
                            resp = await client.get(res["image_url"])
                            if resp.status_code == 200:
                                from io import BytesIO
                                c_img = Image.open(BytesIO(resp.content)).convert("RGB")
                                c_img = self._remove_split_panels_if_any(c_img, (1024, 1024))
                                c_img.save(out_path, "PNG")
                                generated = True
                                logger.info(f"Visual Master Image generated via FLUX.1 ({style_key}): {name}")
                except Exception as e:
                    logger.warning(f"Character master gen via FLUX failed for {name}: {e}")

            # 2. Colab GPU で実画像マスター生成
            if not generated and colab_worker_url:
                try:
                    colab_client = ColabGpuClient(colab_worker_url)
                    res = await colab_client.generate_image(prompt=master_prompt, width=1024, height=1024)
                    if res.get("image_base64"):
                        import base64
                        from io import BytesIO
                        b64_str = res["image_base64"]
                        if "," in b64_str:
                            b64_str = b64_str.split(",")[1]
                        c_img = Image.open(BytesIO(base64.b64decode(b64_str))).convert("RGB")
                        c_img = self._remove_split_panels_if_any(c_img, (1024, 1024))
                        c_img.save(out_path, "PNG")
                        generated = True
                        logger.info(f"Visual Master Image generated via Colab ({style_key}): {name}")
                except Exception as e:
                    logger.warning(f"Character master gen via Colab failed for {name}: {e}")

            if generated:
                master_map[name] = out_path
                logger.info(f"[Character Consistency] Master Anchor Established ({style_key}): {name} -> {out_path}")

        return master_map

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
        character_master_map: Optional[Dict[str, Path]] = None,
        genre: str = "story",
        visual_style: Optional[str] = None,
        telop_style: Optional[str] = None,
        telop_mode: Optional[str] = None,
        telop_font_size: Optional[str] = None,
        telop_font: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        1シーン分のアセット生成（2段階パイプライン）：
        - Stage 1: マスター画像を参照して、指定された visual_style（浮世絵・現代アニメ・劇画マンガ等）で
                   一貫性のある単一フルスクリーンシーン静止画 (bg_xxx.png) を生成
        - Stage 2: 生成したシーン静止画 (bg_xxx.png) をリファレンス（入力画像）として、
                   Colab ComfyUI (LTX-Video I2V) または Gemini Veo 3.1 (I2V) でアニメーション動画 (clip_xxx.mp4) を生成
        - Stage 3: YouTube定番極太フォント＋5層プロ仕様テロップカードシーケンスを生成
        """
        style_key = visual_style or ("ukiyoe" if genre == "edoculture" else "anime_modern")
        style_cfg = VISUAL_STYLE_CONFIGS.get(style_key, VISUAL_STYLE_CONFIGS["anime_modern"])

        scene_num = scene_data.get("scene_number", 1)
        narration = scene_data.get("narration", "")
        speaker = scene_data.get("speaker", "ナレーション")
        raw_prompt = scene_data.get("character_prompt", "") or scene_data.get("visual_description", "")
        clean_raw_prompt = self._clean_scene_prompt_for_image(raw_prompt, visual_style=style_key)
        bgm_tag = scene_data.get("bgm_tag", "neutral")

        # --- キャラクター一貫性（Character Consistency）の実画像アンカー解決 ---
        char_anchor = ""
        ref_image_base64 = None

        if characters:
            if speaker and speaker not in ["ナレーション", "語り", "解説"]:
                for c_def in characters:
                    if c_def.get("name") == speaker:
                        char_anchor = self._clean_scene_prompt_for_image(c_def.get("appearance_prompt_en", ""), visual_style=style_key)
                        break
            if not char_anchor and len(characters) > 0:
                char_anchor = self._clean_scene_prompt_for_image(characters[0].get("appearance_prompt_en", ""), visual_style=style_key)

        # 実画像マスター（Visual Canonical Anchor）が存在する場合、Base64に変換してリファレンス参照用に準備
        if character_master_map:
            master_path = character_master_map.get(speaker)
            if not master_path and len(character_master_map) > 0:
                master_path = next(iter(character_master_map.values()))
            if master_path and Path(master_path).exists():
                try:
                    import base64
                    with open(master_path, "rb") as mf:
                        ref_image_base64 = base64.b64encode(mf.read()).decode("utf-8")
                    logger.info(f"Scene {scene_num}: Injected master reference image ({Path(master_path).name}) for consistent scene generation ({style_key})")
                except Exception as ex:
                    logger.warning(f"Failed to load master image for reference: {ex}")

        scene_style_desc = style_cfg["scene_desc"]
        if char_anchor:
            prompt = f"{char_anchor}, {clean_raw_prompt}, single unified full-screen scene ({scene_style_desc}), masterpiece, high quality, no split screen, no text"
        else:
            prompt = f"{clean_raw_prompt}, single unified full-screen scene ({scene_style_desc}), masterpiece, 8k, no split screen, no text"

        # ----------------------------------------------------
        # 1. 音声アセット生成（キャッシュチェック）
        # ----------------------------------------------------
        voice_params = {"engine": tts_engine, "voice": voice_name, **(tts_params or {})}
        cached_audio = self.cache_manager.get_audio(narration, voice_params)

        audio_out_path = output_dir / f"speech_{scene_num:03d}.mp3"

        if audio_out_path.exists() and audio_out_path.stat().st_size > 500:
            logger.info(f"Scene {scene_num}: Reused existing audio checkpoint ({audio_out_path.name}).")
        elif cached_audio:
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
        # 2-A (Stage 1). ベース画像アセット生成（Nano Banana 2 最優先 ➔ FLUX ➔ Colab ➔ Pexels）
        # ----------------------------------------------------
        img_w, img_h = image_size
        img_ratio = "9:16" if img_h > img_w else "16:9"
        img_params = {
            "width": img_w,
            "height": img_h,
            "engine": "nanobanana_v4_styled",
            "visual_style": style_key,
            "has_ref": bool(ref_image_base64)
        }
        cached_image = self.cache_manager.get_image(prompt, img_params)

        base_image_out_path = output_dir / f"bg_{scene_num:03d}.png"
        video_clip_out_path = output_dir / f"clip_{scene_num:03d}.mp4"
        video_generated = video_clip_out_path.exists() and video_clip_out_path.stat().st_size > 1000
        image_generated = base_image_out_path.exists() and base_image_out_path.stat().st_size > 1000

        if image_generated:
            logger.info(f"Scene {scene_num}: Reused existing scene image checkpoint ({base_image_out_path.name}).")
        if video_generated:
            logger.info(f"Scene {scene_num}: Reused existing I2V animation checkpoint ({video_clip_out_path.name}).")

        # Colab オンライン事前疎通チェック（画像生成・Stage 2 I2V動画生成の両方で共用）
        colab_online = False
        if colab_worker_url and (not image_generated or not video_generated):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=4.0) as ping_client:
                    ping_res = await ping_client.get(colab_worker_url.rstrip("/"))
                    colab_online = ping_res.status_code < 500
            except Exception:
                colab_online = False

        if not image_generated and cached_image:
            raw_cached = Image.open(cached_image).convert("RGB")
            clean_cached = self._remove_split_panels_if_any(raw_cached, (img_w, img_h))
            clean_cached.save(base_image_out_path, "PNG")
            image_generated = True
            logger.info(f"Scene {scene_num}: Loaded and verified single-frame Nano Banana image from cache ({style_key}).")
        elif not image_generated:
            # 優先順位 0 (最優先): 有料 Gemini API Nano Banana モデル（マスター画像リファレンス参照生成）
            if paid_gemini_api_key:
                try:
                    logger.info(
                        f"Scene {scene_num} [Stage 1]: Calling Gemini Nano Banana "
                        f"(style: {style_key}, ref_image: {'yes' if ref_image_base64 else 'no'}, ratio: {img_ratio})..."
                    )
                    nb_img = await self._generate_with_gemini_nanobanana(
                        api_key=paid_gemini_api_key,
                        prompt=prompt,
                        ref_image_base64=ref_image_base64,
                        target_size=(img_w, img_h),
                        aspect_ratio=img_ratio,
                        visual_style=style_key
                    )
                    if nb_img:
                        nb_img.save(base_image_out_path, "PNG")
                        self.cache_manager.save_image(nb_img, prompt, img_params)
                        image_generated = True
                        logger.info(f"Scene {scene_num} [Stage 1]: Generated scene image via Gemini Nano Banana ({style_key}).")
                except Exception as nb_err:
                    logger.warning(f"Scene {scene_num}: Gemini Nano Banana generation failed: {nb_err}")

            # 優先順位 1: FLUX.1 [schnell] (fal.ai / Replicate) (クレジット設定時のみ)
            if not image_generated and (fal_api_key or replicate_api_token):
                try:
                    provider = "fal" if fal_api_key else "replicate"
                    key = fal_api_key or replicate_api_token
                    logger.info(f"Scene {scene_num}: Calling FLUX.1 [schnell] ({provider}, style: {style_key})...")
                    flux_client = FluxSchnellClient(provider=provider, api_key=key)
                    flux_ref_url = f"data:image/png;base64,{ref_image_base64}" if ref_image_base64 else None
                    flux_res = await flux_client.generate_image(
                        prompt=prompt,
                        width=img_w,
                        height=img_h,
                        image_url=flux_ref_url,
                        strength=0.65
                    )
                    if flux_res.get("image_url"):
                        import httpx
                        async with httpx.AsyncClient(timeout=30) as client:
                            img_resp = await client.get(flux_res["image_url"])
                            if img_resp.status_code == 200:
                                from io import BytesIO
                                flux_img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                                flux_img = self._remove_split_panels_if_any(flux_img, (img_w, img_h))
                                flux_img.save(base_image_out_path, "PNG")
                                self.cache_manager.save_image(flux_img, prompt, img_params)
                                image_generated = True
                                logger.info(f"Scene {scene_num}: Generated via FLUX.1 [schnell].")
                except Exception as flux_err:
                    logger.warning(f"FLUX.1 generation failed: {flux_err}. Falling back to next engine...")

            # 優先順位 2: Google Colab ワーカーでベース画像生成
            if not image_generated and colab_online:
                try:
                    colab_client = ColabGpuClient(colab_worker_url)
                    colab_res = await colab_client.generate_image(
                        prompt=prompt,
                        width=img_w,
                        height=img_h,
                        reference_image_base64=ref_image_base64,
                        strength=0.65
                    )
                    if colab_res.get("image_base64"):
                        import base64
                        from io import BytesIO
                        img_data = base64.b64decode(colab_res["image_base64"])
                        colab_img = Image.open(BytesIO(img_data)).convert("RGB")
                        colab_img = self._remove_split_panels_if_any(colab_img, (img_w, img_h))
                        colab_img.save(base_image_out_path, "PNG")
                        self.cache_manager.save_image(colab_img, prompt, img_params)
                        image_generated = True
                        logger.info(f"Scene {scene_num}: Generated via Google Colab Free GPU.")
                except Exception as colab_err:
                    logger.warning(f"Colab GPU image generation failed: {colab_err}")

            # 優先順位 3: Pexels 素材
            if not image_generated and not video_generated and pexels_api_key:
                try:
                    logger.info(f"Scene {scene_num}: Searching Pexels B-roll (video preferred)...")
                    pexels_client = PexelsClient(api_key=pexels_api_key)
                    broll = await pexels_client.search_and_download_broll(
                        query=clean_raw_prompt[:60],
                        orientation="portrait" if img_h > img_w else "landscape",
                        preferred_type="video",
                        output_dir=output_dir
                    )
                    if broll and Path(broll.get("file_path", "")).exists():
                        b_path = Path(broll["file_path"])
                        b_type = broll.get("type", "image")
                        if b_type == "video" or b_path.suffix.lower() in [".mp4", ".mov", ".webm"]:
                            import shutil
                            shutil.copy2(b_path, video_clip_out_path)
                            video_generated = True
                            image_generated = True
                            import subprocess
                            subprocess.run([
                                "ffmpeg", "-y", "-i", str(video_clip_out_path),
                                "-vframes", "1", str(base_image_out_path)
                            ], capture_output=True, timeout=10)
                            logger.info(f"Scene {scene_num}: Downloaded stock video clip from Pexels ({video_clip_out_path.name}).")
                        else:
                            p_img = Image.open(b_path).convert("RGB").resize((img_w, img_h))
                            p_img.save(base_image_out_path, "PNG")
                            self.cache_manager.save_image(p_img, prompt, img_params)
                            image_generated = True
                            logger.info(f"Scene {scene_num}: Downloaded stock image from Pexels.")
                except Exception as pexels_err:
                    logger.warning(f"Pexels fetch failed: {pexels_err}.")

            # 最終安全フォールバック: 開発テキストのない美麗シネマティック背景
            if not image_generated and not video_generated:
                logger.info(f"Scene {scene_num}: Using aesthetic animated backdrop.")
                art_img = self._generate_artistic_backdrop(img_w, img_h, prompt, scene_num, genre=genre)
                art_img.save(base_image_out_path, "PNG")
                image_generated = True

        # ----------------------------------------------------
        # 2-B (Stage 2). 生成したシーン画像 (bg_xxx.png) をリファレンスにしてアニメーション動画化 (Image-to-Video)
        # ----------------------------------------------------
        ltx_motion_prefix = style_cfg["ltx_motion_prefix"]
        if image_generated and base_image_out_path.exists() and not video_generated:
            # 1) Colab ComfyUI (LTX-Video I2V) または Colab GPU Worker がオンラインなら最優先で I2V アニメーション生成
            if colab_online and colab_worker_url:
                try:
                    logger.info(f"Scene {scene_num} [Stage 2 I2V]: Animating {base_image_out_path.name} via Colab ComfyUI LTX-Video I2V ({style_key})...")
                    colab_client = ColabGpuClient(colab_worker_url)
                    ltx_w = 576 if img_h > img_w else 1024
                    ltx_h = 1024 if img_h > img_w else 576
                    await colab_client.generate_comfyui_ltx_video(
                        prompt=f"{ltx_motion_prefix}, {clean_raw_prompt}",
                        output_path=str(video_clip_out_path),
                        width=ltx_w,
                        height=ltx_h,
                        num_frames=97,
                        fps=24,
                        image_path=str(base_image_out_path)
                    )
                    if video_clip_out_path.exists() and video_clip_out_path.stat().st_size > 1000:
                        video_generated = True
                        logger.info(f"Scene {scene_num} [Stage 2 I2V]: Successfully animated scene via Colab ComfyUI LTX-Video ({style_key})!")
                except Exception as colab_i2v_err:
                    logger.warning(f"Scene {scene_num} [Stage 2 I2V]: Colab ComfyUI I2V failed ({colab_i2v_err}), trying custom /generate/video endpoint...")
                    try:
                        import base64
                        scene_b64 = base64.b64encode(base_image_out_path.read_bytes()).decode("utf-8")
                        colab_client = ColabGpuClient(colab_worker_url)
                        v_res = await colab_client.generate_video(
                            prompt=f"{ltx_motion_prefix}, {clean_raw_prompt}",
                            reference_image_base64=scene_b64,
                            duration_seconds=5
                        )
                        if v_res.get("video_base64"):
                            v_b64 = v_res["video_base64"].split(",")[-1]
                            video_clip_out_path.write_bytes(base64.b64decode(v_b64))
                            if video_clip_out_path.exists() and video_clip_out_path.stat().st_size > 1000:
                                video_generated = True
                                logger.info(f"Scene {scene_num} [Stage 2 I2V]: Animated via Colab /generate/video endpoint!")
                    except Exception as colab_v2_err:
                        logger.warning(f"Scene {scene_num} [Stage 2 I2V]: Colab /generate/video fallback also failed: {colab_v2_err}")

            # 2) Colab がオフラインまたは失敗した場合、有料 Gemini API (Veo 3.1 / 3.0 Image-to-Video) でシーン画像をアニメーション動画化
            if not video_generated and paid_gemini_api_key:
                try:
                    logger.info(f"Scene {scene_num} [Stage 2 I2V]: Animating {base_image_out_path.name} via Gemini Veo Image-to-Video ({style_key})...")
                    veo_ok = await self._animate_image_with_veo(
                        api_key=paid_gemini_api_key,
                        image_path=base_image_out_path,
                        prompt=clean_raw_prompt,
                        output_video_path=video_clip_out_path,
                        aspect_ratio=img_ratio,
                        visual_style=style_key
                    )
                    if veo_ok and video_clip_out_path.exists() and video_clip_out_path.stat().st_size > 1000:
                        video_generated = True
                        logger.info(f"Scene {scene_num} [Stage 2 I2V]: Successfully animated scene via Gemini Veo I2V ({style_key})!")
                except Exception as veo_i2v_err:
                    logger.warning(f"Scene {scene_num} [Stage 2 I2V]: Gemini Veo I2V failed: {veo_i2v_err}")

        # ----------------------------------------------------
        # 3 (Stage 3). 高精度YouTubeプロ仕様テロップ画像シーケンス生成
        # ----------------------------------------------------
        overlay_out_path = output_dir / f"overlay_{scene_num:03d}.png"
        audio_dur = float(scene_data.get("duration_seconds") or 5.0)
        if audio_out_path and Path(audio_out_path).exists():
            try:
                from processors.manga_video_composer import MangaVideoComposer
                audio_dur = MangaVideoComposer()._get_audio_duration(audio_out_path)
            except Exception:
                pass

        overlay_cards = self._create_manga_bubble_overlays_sequence(
            width=img_w,
            height=img_h,
            speaker=speaker,
            narration=narration,
            duration=audio_dur,
            output_dir=output_dir,
            scene_num=scene_num,
            genre=genre,
            telop_style=telop_style,
            font_size_key=telop_font_size or "medium",
            telop_font=telop_font
        )

        if overlay_cards and Path(overlay_cards[0]["image_path"]).exists():
            import shutil
            shutil.copy2(overlay_cards[0]["image_path"], overlay_out_path)
        else:
            pil_overlay = self._create_manga_bubble_overlay(
                img_w, img_h, speaker, narration, genre=genre, telop_style=telop_style, telop_font=telop_font
            )
            pil_overlay.save(overlay_out_path, "PNG")

        return {
            "scene_number": scene_num,
            "speaker": speaker,
            "narration": narration,
            "bgm_tag": bgm_tag,
            "visual_style": style_key,
            "audio_path": str(audio_out_path) if audio_out_path else None,
            "base_image_path": str(base_image_out_path),
            "overlay_image_path": str(overlay_out_path),
            "overlay_cards": overlay_cards,
            "video_path": str(video_clip_out_path) if (video_generated and video_clip_out_path.exists()) else None,
            "duration_seconds": audio_dur
        }

    def generate_telop_preview_base64(
        self,
        text: str = "まさか、そんな秘密があったなんて…！",
        telop_font: str = "keifont",
        telop_style: str = "shorts_impact_yellow",
        telop_font_size: str = "medium",
        genre: str = "story",
        visual_style: str = "anime_modern"
    ) -> str:
        """
        AI動画生成ワーカーでテロップ設定（書体・配色・文字サイズ）を選択した瞬間に
        本番と100%同一の5層レンダリングエンジンでプレビューバナー画像（Base64 PNG）を生成して返す。
        """
        import base64
        from io import BytesIO

        style_key = telop_style or "shorts_impact_yellow"
        style = PRO_SHORTS_TELOP_STYLES.get(style_key) or GENRE_TELOP_STYLES.get(genre, GENRE_TELOP_STYLES["story"])

        # 1080x1920 キャンバスで本番同等の5層テロップを描画し、下部テロップ領域をクロップして見やすい横長バナーにする
        full_w, full_h = 1080, 1920
        cards = self.split_text_into_cards(
            text or "まさか、そんな秘密があったなんて…！",
            max_lines_per_card=style.get("max_lines", 2),
            max_chars_per_line=style.get("max_chars_per_line", 11)
        )
        card_text = cards[0] if cards else "まさか、そんな秘密があったなんて…！"

        overlay_rgba = self._create_single_card_overlay(
            width=full_w,
            height=full_h,
            speaker="",
            card_text=card_text,
            style=style,
            font_size_key=telop_font_size or "medium",
            telop_font=telop_font or "keifont",
            genre=genre
        )

        # スタイルに応じた背景プレビュー（浮世絵なら和紙・藍ぼかし風、それ以外はダークシネマ背景）
        crop_top = int(full_h * 0.66)
        crop_bottom = int(full_h * 0.93)
        crop_h = crop_bottom - crop_top

        bg = Image.new("RGBA", (full_w, crop_h), (15, 23, 42, 255))
        bdraw = ImageDraw.Draw(bg)
        if visual_style == "ukiyoe" or telop_style == "edo_ukiyoe_crimson":
            # 浮世絵・和紙風プレビュー背景（藍色×琥珀和紙グラデーション）
            for y in range(crop_h):
                r_ratio = y / max(crop_h, 1)
                r = int(46 * (1 - r_ratio) + 24 * r_ratio)
                g = int(38 * (1 - r_ratio) + 28 * r_ratio)
                b = int(32 * (1 - r_ratio) + 48 * r_ratio)
                bdraw.line([(0, y), (full_w, y)], fill=(r, g, b, 255))
        else:
            for y in range(crop_h):
                r_ratio = y / max(crop_h, 1)
                r = int(22 * (1 - r_ratio) + 10 * r_ratio)
                g = int(32 * (1 - r_ratio) + 15 * r_ratio)
                b = int(58 * (1 - r_ratio) + 30 * r_ratio)
                bdraw.line([(0, y), (full_w, y)], fill=(r, g, b, 255))

        cropped_telop = overlay_rgba.crop((0, crop_top, full_w, crop_bottom))
        composed = Image.alpha_composite(bg, cropped_telop).convert("RGB")

        buf = BytesIO()
        composed.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def ensure_builtin_bgm_file(preset_id: str, bgm_dir: Path, duration_sec: float = 24.0) -> Optional[Path]:
        """
        内蔵プリセットBGM（builtin:edo_ukiyoe 等）が選択された場合、
        高品位なマルチトラック和楽器・ストリングス・アンビエント音源WAVファイルを生成・キャッシュして返す。
        試聴および動画合成の両方で即座に利用可能。
        """
        import wave
        import struct

        clean_id = (preset_id or "edo_ukiyoe").replace("builtin:", "").strip()
        bgm_dir.mkdir(parents=True, exist_ok=True)
        out_wav = bgm_dir / f"builtin_{clean_id}.wav"
        if out_wav.exists() and out_wav.stat().st_size > 10000:
            return out_wav

        sr = 44100
        total_samples = int(sr * duration_sec)
        t = np.linspace(0, duration_sec, total_samples, endpoint=False, dtype=np.float32)

        if clean_id == "edo_ukiyoe":
            # 江戸・和風浮世絵調（都節音階: D4, Eb4, G4, A4, Bb4, D5 ＋ 三味線風撥音プラック ＋ 篠笛風ビブラート ＋ 太鼓低音）
            scale_freqs = [293.66, 311.13, 392.00, 440.00, 466.16, 587.33, 440.00, 392.00]
            beat_dur = 0.5
            audio = np.zeros_like(t)
            for idx in range(int(duration_sec / beat_dur)):
                start_s = int(idx * beat_dur * sr)
                end_s = min(total_samples, int((idx + 1) * beat_dur * sr))
                if start_s >= total_samples:
                    break
                seg_t = t[start_s:end_s] - t[start_s]
                freq = scale_freqs[idx % len(scale_freqs)]
                # 三味線風プラック（急速な立ち上がりと指数減衰＋倍音）
                env = np.exp(-seg_t * 6.5)
                pluck = (
                    0.55 * np.sin(2 * np.pi * freq * seg_t)
                    + 0.30 * np.sin(2 * np.pi * (freq * 2) * seg_t)
                    + 0.15 * np.sin(2 * np.pi * (freq * 3) * seg_t)
                ) * env
                # 2拍ごとの和太鼓風低音アクセント
                if idx % 2 == 0:
                    drum_env = np.exp(-seg_t * 11.0)
                    drum = 0.45 * np.sin(2 * np.pi * 73.42 * seg_t) * drum_env
                    pluck = pluck + drum
                audio[start_s:end_s] += pluck
            # 篠笛風の持続和音パッド（D3 + A3）
            vibrato = 1.0 + 0.004 * np.sin(2 * np.pi * 5.0 * t)
            pad = 0.18 * np.sin(2 * np.pi * 146.83 * t * vibrato) + 0.12 * np.sin(2 * np.pi * 220.0 * t)
            audio = audio + pad
        elif clean_id == "dramatic_strings":
            # 劇的・シリアス（Aマイナー重厚ストリングス進行）
            chords = [
                (220.0, 261.63, 329.63),
                (174.61, 220.0, 261.63),
                (146.83, 174.61, 220.0),
                (164.81, 207.65, 246.94),
            ]
            bar_dur = 2.0
            audio = np.zeros_like(t)
            for idx in range(int(duration_sec / bar_dur)):
                start_s = int(idx * bar_dur * sr)
                end_s = min(total_samples, int((idx + 1) * bar_dur * sr))
                seg_t = t[start_s:end_s] - t[start_s]
                c = chords[idx % len(chords)]
                env = np.minimum(seg_t / 0.25, 1.0) * np.exp(-seg_t * 0.4)
                chord_sig = sum(
                    0.28 * np.sin(2 * np.pi * f * seg_t) + 0.10 * np.sin(2 * np.pi * (f * 2) * seg_t)
                    for f in c
                ) * env
                audio[start_s:end_s] += chord_sig
        elif clean_id == "upbeat_marimba":
            # 軽快・ポップ（雑学・テンポ重視マリンバアルペジオ）
            notes = [523.25, 659.25, 783.99, 1046.50, 783.99, 659.25, 587.33, 698.46]
            step_dur = 0.25
            audio = np.zeros_like(t)
            for idx in range(int(duration_sec / step_dur)):
                start_s = int(idx * step_dur * sr)
                end_s = min(total_samples, int((idx + 1) * step_dur * sr))
                seg_t = t[start_s:end_s] - t[start_s]
                f = notes[idx % len(notes)]
                env = np.exp(-seg_t * 10.0)
                audio[start_s:end_s] += (0.55 * np.sin(2 * np.pi * f * seg_t) + 0.15 * np.sin(2 * np.pi * (f * 4) * seg_t)) * env
            audio += 0.15 * np.sin(2 * np.pi * 130.81 * t)
        elif clean_id == "corporate_clean":
            # ビジネス・解説（爽やか・知的シンセピアノ）
            notes = [261.63, 329.63, 392.00, 493.88, 392.00, 329.63]
            step_dur = 0.5
            audio = np.zeros_like(t)
            for idx in range(int(duration_sec / step_dur)):
                start_s = int(idx * step_dur * sr)
                end_s = min(total_samples, int((idx + 1) * step_dur * sr))
                seg_t = t[start_s:end_s] - t[start_s]
                f = notes[idx % len(notes)]
                env = np.exp(-seg_t * 3.8)
                audio[start_s:end_s] += (0.45 * np.sin(2 * np.pi * f * seg_t) + 0.20 * np.sin(2 * np.pi * (f * 2) * seg_t)) * env
        elif clean_id == "mystery_synth":
            # ミステリー・考察（ダークアンビエント＆パルス）
            pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 2.0 * t)
            audio = (
                0.35 * np.sin(2 * np.pi * 110.0 * t)
                + 0.25 * np.sin(2 * np.pi * 164.81 * t) * pulse
                + 0.18 * np.sin(2 * np.pi * 233.08 * t)
            )
        else:
            # calm_piano (感動・穏やかピアノアルペジオ)
            notes = [261.63, 329.63, 392.00, 523.25, 220.00, 261.63, 329.63, 440.00]
            step_dur = 0.6
            audio = np.zeros_like(t)
            for idx in range(int(duration_sec / step_dur)):
                start_s = int(idx * step_dur * sr)
                end_s = min(total_samples, int((idx + 1) * step_dur * sr))
                seg_t = t[start_s:end_s] - t[start_s]
                f = notes[idx % len(notes)]
                env = np.exp(-seg_t * 2.8)
                audio[start_s:end_s] += (0.48 * np.sin(2 * np.pi * f * seg_t) + 0.16 * np.sin(2 * np.pi * (f * 2) * seg_t)) * env

        # 正規化＆16bitステレオWAV書き出し
        max_amp = float(np.max(np.abs(audio))) or 1.0
        norm_audio = np.clip((audio / max_amp) * 0.75, -0.98, 0.98)
        pcm16 = (norm_audio * 32767.0).astype(np.int16)

        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm16.tobytes())

        return out_wav

