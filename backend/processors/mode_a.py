"""
モードA プロセッサー v2 — ケンバーンズ効果付き動画生成
画像にズーム・パン・フェードトランジションを適用して動画化
"""
import logging
import shutil
import subprocess
import httpx
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from processors.script_generator import ScriptGenerator
from processors.script_generator import ScriptGenerator
from processors.tts_manager import TTSManager
from utils.ffmpeg_utils import concat_video_clips

logger = logging.getLogger(__name__)


class ModeAProcessor:
    """モードA: テーマからショート動画を自動生成（ケンバーンズ効果付き）"""

    def __init__(self, firestore_service, storage_service,
                 gemini_api_key: str = "", paid_gemini_api_key: str = "", pexels_api_key: str = "",
                 tts_engine: str = "edge", voice_name: str = "nanami", speaking_rate: float = 1.0,
                 google_tts_key: str = "", elevenlabs_key: str = "", aivis_key: str = "",
                 **kwargs):
        self.firestore = firestore_service
        self.storage = storage_service
        # テキスト・台本生成には無料APIキー（なければ有料キー）を使用
        text_api_key = gemini_api_key or paid_gemini_api_key
        # 画像生成・アニメーションには有料APIキー（なければ無料キー）を使用
        self.visual_api_key = paid_gemini_api_key or gemini_api_key
        self.paid_gemini_api_key = paid_gemini_api_key
        self.script_gen = ScriptGenerator(api_key=text_api_key)
        self.pexels_api_key = pexels_api_key
        
        self.tts = TTSManager(
            engine=tts_engine,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            google_tts_key=google_tts_key,
            elevenlabs_key=elevenlabs_key,
            aivis_key=aivis_key,
            **kwargs
        )

    def _get_job_dir(self, job_id: str) -> Path:
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    async def generate_script(self, theme: str, style: str, duration: int) -> dict:
        return await self.script_gen.generate(theme, style, duration)

    async def synthesize_audio(self, script_data: dict, job_id: str) -> list[Path]:
        job_dir = self._get_job_dir(job_id)
        return await self.tts.synthesize_all_scenes(script_data["scenes"], job_dir)

    async def generate_visuals(self, script_data: dict, job_id: str) -> tuple[list[Path], list[Path]]:
        """グラデーション背景画像と、テロップ透過画像を別々に生成"""
        job_dir = self._get_job_dir(job_id)
        image_dir = job_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_paths = []
        text_paths = []

        # シーンごとに異なるグラデーション
        palettes = [
            [(26, 26, 46), (22, 33, 62), (108, 99, 255)],
            [(44, 62, 80), (52, 73, 94), (52, 152, 219)],
            [(142, 68, 173), (155, 89, 182), (192, 57, 43)],
            [(39, 174, 96), (46, 204, 113), (241, 196, 15)],
            [(192, 57, 43), (231, 76, 60), (243, 156, 18)],
            [(41, 128, 185), (52, 152, 219), (26, 188, 156)],
            [(243, 156, 18), (241, 196, 15), (46, 204, 113)],
            [(127, 140, 141), (149, 165, 166), (108, 99, 255)],
        ]

        W, H = config.SHORT_VIDEO_WIDTH, config.SHORT_VIDEO_HEIGHT
        # ケンバーンズ用に大きめの画像を生成（1.3倍）
        BIG_W, BIG_H = int(W * 1.3), int(H * 1.3)

        try:
            font = ImageFont.truetype(config.SUBTITLE_FONT, 62)
            font_small = ImageFont.truetype(config.SUBTITLE_FONT, 40)
        except Exception:
            font = ImageFont.load_default()
            font_small = font

        for i, scene in enumerate(script_data["scenes"]):
            img_path = image_dir / f"scene_{i:03d}.png"
            palette = palettes[i % len(palettes)]
            
            bg_image = None
            
            # --- Pexelsから画像を取得（APIキーがある場合） ---
            if self.pexels_api_key and scene.get("search_query"):
                query = scene["search_query"]
                try:
                    with httpx.Client() as client:
                        res = client.get(
                            "https://api.pexels.com/v1/search",
                            headers={"Authorization": self.pexels_api_key},
                            params={"query": query, "per_page": 15, "orientation": "portrait"}
                        )
                        if res.status_code == 200:
                            data = res.json()
                            if data.get("photos") and len(data["photos"]) > 0:
                                import random
                                photo = random.choice(data["photos"])
                                img_url = photo["src"]["large2x"]
                                img_res = client.get(img_url)
                                if img_res.status_code == 200:
                                    # Pexels画像を読み込み
                                    downloaded = Image.open(__import__('io').BytesIO(img_res.content))
                                    downloaded = downloaded.convert("RGB")
                                    # アスペクト比を保持してリサイズ＆クロップ
                                    downloaded_ratio = downloaded.width / downloaded.height
                                    target_ratio = BIG_W / BIG_H
                                    if downloaded_ratio > target_ratio:
                                        new_w = int(downloaded.height * target_ratio)
                                        offset = (downloaded.width - new_w) // 2
                                        downloaded = downloaded.crop((offset, 0, offset + new_w, downloaded.height))
                                    else:
                                        new_h = int(downloaded.width / target_ratio)
                                        offset = (downloaded.height - new_h) // 2
                                        downloaded = downloaded.crop((0, offset, downloaded.width, offset + new_h))
                                    
                                    bg_image = downloaded.resize((BIG_W, BIG_H), Image.Resampling.LANCZOS)
                                    # 少し暗くして文字を読みやすくする
                                    enhancer = __import__('PIL.ImageEnhance', fromlist=['ImageEnhance']).Brightness(bg_image)
                                    bg_image = enhancer.enhance(0.6)
                                    logger.info(f"Pexelsから画像取得成功: '{query}'")
                except Exception as e:
                    logger.warning(f"Pexels画像の取得に失敗しました ({query}): {e}")

            # --- フォールバック: グラデーション背景 ---
            if bg_image is None:
                bg_image = Image.new("RGB", (BIG_W, BIG_H))
                draw = ImageDraw.Draw(bg_image)
                for y in range(BIG_H):
                    ratio = y / BIG_H
                    r = int(palette[0][0] * (1 - ratio) + palette[1][0] * ratio)
                    g = int(palette[0][1] * (1 - ratio) + palette[1][1] * ratio)
                    b = int(palette[0][2] * (1 - ratio) + palette[1][2] * ratio)
                    draw.line([(0, y), (BIG_W, y)], fill=(r, g, b))

                # 装飾的な光の円を追加
                overlay = Image.new("RGBA", (BIG_W, BIG_H), (0, 0, 0, 0))
                odraw = ImageDraw.Draw(overlay)
                cx, cy = int(BIG_W * 0.7), int(BIG_H * 0.3)
                for r_val in range(300, 0, -3):
                    alpha = max(0, int(15 * (r_val / 300)))
                    odraw.ellipse(
                        [cx - r_val, cy - r_val, cx + r_val, cy + r_val],
                        fill=(palette[2][0], palette[2][1], palette[2][2], alpha)
                    )
                bg_image.paste(Image.alpha_composite(bg_image.convert("RGBA"), overlay).convert("RGB"))

            bg_image.save(img_path, "PNG", quality=95)
            image_paths.append(img_path)

            # --- テロップテキスト用透過画像の生成（1画面あたり最大3行・1行14文字以内・1〜3枚に最適分割） ---
            text = scene.get("text_overlay") or scene.get("narration") or ""
            if text:
                cards = self.split_text_into_cards(text, max_lines_per_card=3, max_chars_per_line=14)
                scene_text_paths = []

                for part_idx, card_text in enumerate(cards):
                    text_image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(text_image)

                    # テキストの中央・下部配置（余白と行間を最適化）
                    bbox = draw.multiline_textbbox((0, 0), card_text, font=font, align="center", spacing=12, stroke_width=5)
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    tx = (W - tw) // 2
                    ty = int(H * 0.76) - th // 2

                    # 滑らかな太めのアウトライン＋白文字
                    draw.multiline_text(
                        (tx, ty), card_text,
                        fill=(255, 255, 255, 255),
                        font=font,
                        align="center",
                        spacing=12,
                        stroke_width=5,
                        stroke_fill=(0, 0, 0, 255)
                    )

                    text_img_path = image_dir / f"text_{i:03d}_part{part_idx}.png"
                    text_image.save(text_img_path, "PNG")
                    scene_text_paths.append(text_img_path)

                text_paths.append(scene_text_paths)
            else:
                text_paths.append([])

        logger.info(f"画像素材 {len(image_paths)}枚 生成完了（ケンバーンズ＆テロップ最大3行・最適分割対応）")
        return image_paths, text_paths

    START_PROHIBITED = set('、。，．・？！?!」』）)]｝}”’ー〜～ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ')
    END_PROHIBITED = set('「『（([｛{“‘')
    PARTICLES_2 = [
        'について', 'として', 'によって', 'けれど', 'だけど', 'だから', 
        'しかし', 'そして', 'ながら', 'ように', 'ために', 'すると', 
        'なので', 'から', 'まで', 'より', 'ので', 'のに', 'ても', 'たら'
    ]
    PARTICLES_1 = ['は', 'が', 'を', 'に', 'へ', 'で', 'と', 'て', 'も']

    @classmethod
    def clean_japanese_text(cls, text: str) -> str:
        """テキストの余分な改行や変な記号を正規化し、行頭の孤立記号を除去"""
        import re
        t = text.replace('\\n', ' ').replace('\r', ' ').replace('\n', ' ')
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'」[。、.]+', '」', t)
        # 行頭の孤立した閉じ括弧や句読点を完全に除去
        t = re.sub(r'^[」』）)\s。、？！?!]+', '', t)
        t = re.sub(r'[「『（(\s]+$', '', t)
        return t

    @classmethod
    def find_natural_split_points(cls, text: str) -> dict[int, int]:
        points = {}
        n = len(text)
        for i in range(1, n):
            if text[i] in cls.START_PROHIBITED:
                continue
            if text[i-1] in cls.END_PROHIBITED:
                continue

            score = 1
            if text[i-1] in '。！？!?':
                score = 100
            elif text[i-1] in '、,':
                score = 80
            elif text[i-1] in '」』）':
                score = 75
            else:
                matched = False
                for p in cls.PARTICLES_2:
                    plen = len(p)
                    if i >= plen and text[i-plen:i] == p:
                        score = 45
                        matched = True
                        break
                if not matched:
                    for p in cls.PARTICLES_1:
                        if text[i-1] == p and i >= 2 and text[i-2] not in cls.START_PROHIBITED:
                            score = 25
                            break
            points[i] = score
        return points

    @classmethod
    def wrap_single_card(cls, text: str, max_chars: int = 14) -> list[str]:
        """1枚のカード用テキストを、最大14文字・禁則処理遵守・自然な文節で改行する"""
        clean = cls.clean_japanese_text(text)
        if not clean:
            return []
        if len(clean) <= max_chars:
            return [clean]

        points = cls.find_natural_split_points(clean)
        lines = []
        curr = clean

        while len(curr) > max_chars:
            search_max = min(len(curr), max_chars)
            best_pt = -1
            best_score = -1

            for pt in range(search_max, 2, -1):
                if pt in points:
                    balance_bonus = 10 - abs(pt - int(search_max * 0.75))
                    total_score = points[pt] + balance_bonus
                    if total_score > best_score:
                        best_score = total_score
                        best_pt = pt

            if best_pt == -1:
                for pt in range(search_max, 2, -1):
                    if curr[pt] not in cls.START_PROHIBITED and curr[pt-1] not in cls.END_PROHIBITED:
                        best_pt = pt
                        break
                if best_pt == -1:
                    best_pt = search_max

            line = curr[:best_pt].strip()
            if line:
                lines.append(line)
            curr = curr[best_pt:].strip()
            points = cls.find_natural_split_points(curr)

        if curr:
            if len(curr) <= 2 and lines:
                prev = lines.pop()
                combined = prev + curr
                if len(combined) <= max_chars:
                    lines.append(combined)
                else:
                    sub_pts = cls.find_natural_split_points(combined)
                    mid = len(combined) // 2
                    best_m = -1
                    best_s = -1
                    for pt in range(min(len(combined), max_chars), 2, -1):
                        if pt in sub_pts and len(combined) - pt <= max_chars:
                            s = sub_pts[pt] - abs(pt - mid) * 2
                            if s > best_s:
                                best_s = s
                                best_m = pt
                    if best_m != -1:
                        lines.append(combined[:best_m].strip())
                        lines.append(combined[best_m:].strip())
                    else:
                        lines.append(combined[:mid].strip())
                        lines.append(combined[mid:].strip())
            else:
                lines.append(curr)

        return lines

    @classmethod
    def split_text_into_cards(cls, text: str, max_lines_per_card: int = 3, max_chars_per_line: int = 14) -> list[str]:
        """
        1シーンのテキストを、1画面あたり最大3行（各行最大14文字）に厳密に収まるように
        1〜3枚の字幕カードに最適分割する。
        """
        clean = cls.clean_japanese_text(text)
        if not clean:
            return []

        all_lines = cls.wrap_single_card(clean, max_chars=max_chars_per_line)
        if len(all_lines) <= max_lines_per_card:
            return ["\n".join(all_lines)]

        if len(all_lines) <= 6:
            n = len(all_lines)
            mid = (n + 1) // 2
            card1 = "\n".join(all_lines[:mid])
            card2 = "\n".join(all_lines[mid:])
            return [card1, card2]

        n = len(all_lines)
        p1 = (n + 2) // 3
        p2 = p1 + ((n - p1 + 1) // 2)
        card1 = "\n".join(all_lines[:p1])
        card2 = "\n".join(all_lines[p1:p2])
        card3 = "\n".join(all_lines[p2:min(p2 + max_lines_per_card, n)])
        return [card1, card2, card3]

    async def compose_video(self, script_data, audio_paths, image_paths, text_paths, job_id, duration):
        """ケンバーンズ効果＋フェードトランジション＋3分割テロップ時間差オーバーレイ付きで動画を合成"""
        job_dir = self._get_job_dir(job_id)
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        W, H = config.SHORT_VIDEO_WIDTH, config.SHORT_VIDEO_HEIGHT
        scene_clips = []
        scenes = script_data["scenes"]

        kb_effects = [
            "zoompan=z='zoom+0.001':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='if(lte(zoom,1.0),1.5,zoom-0.001)':x='iw/2-(iw/zoom/2)':y='ih/4-(ih/zoom/4)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='zoom+0.0008':x='iw/4-(iw/zoom/4)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='if(lte(zoom,1.0),1.4,zoom-0.0008)':x='iw*3/4-(iw/zoom*3/4)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
        ]

        for i, scene in enumerate(scenes):
            if i >= len(audio_paths) or i >= len(image_paths):
                break

            clip_path = clips_dir / f"clip_{i:03d}.mp4"
            from utils.whisper_utils import get_audio_duration
            try:
                scene_dur = get_audio_duration(audio_paths[i]) + 0.5
            except Exception as e:
                logger.warning(f"音声長さ取得エラー, デフォルトを使用: {e}")
                scene_dur = scene.get("duration_seconds", 5)

            frames = int(scene_dur * 30)
            kb = kb_effects[i % len(kb_effects)].format(dur=frames, w=W, h=H)
            fade_filter = f",fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, scene_dur-0.5)}:d=0.5"

            scene_texts = text_paths[i] if (text_paths and i < len(text_paths)) else []

            if scene_texts and len(scene_texts) > 0:
                # 3分割テロップを時間差でオーバーレイ
                n_parts = len(scene_texts)
                part_dur = scene_dur / n_parts

                cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image_paths[i])]
                for tp in scene_texts:
                    cmd.extend(["-loop", "1", "-i", str(tp)])
                cmd.extend(["-i", str(audio_paths[i])])

                # フィルターチェーン構築
                fc_lines = [f"[0:v]{kb}[bg0]"]
                last_v = "[bg0]"
                for p_idx in range(n_parts):
                    st = round(p_idx * part_dur, 2)
                    et = round((p_idx + 1) * part_dur, 2)
                    next_v = f"[bg{p_idx+1}]"
                    if p_idx == n_parts - 1:
                        fc_lines.append(f"{last_v}[{p_idx+1}:v]overlay=0:0:enable='between(t,{st},{et})'{fade_filter},format=yuv420p[v]")
                    else:
                        fc_lines.append(f"{last_v}[{p_idx+1}:v]overlay=0:0:enable='between(t,{st},{et})'{next_v}")
                        last_v = next_v

                filter_str = "; ".join(fc_lines)
                audio_input_idx = n_parts + 1

                cmd.extend([
                    "-filter_complex", filter_str,
                    "-map", "[v]", "-map", f"{audio_input_idx}:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "30",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    "-shortest", "-t", str(scene_dur),
                    str(clip_path)
                ])
            else:
                # テキストなし
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-loop", "1", "-i", str(image_paths[i]),
                    "-i", str(audio_paths[i]),
                    "-filter_complex", f"[0:v]{kb}{fade_filter},format=yuv420p[v]",
                    "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "30",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    "-shortest", "-t", str(scene_dur),
                    str(clip_path),
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.error(f"シーン{i}生成エラー: {result.stderr[-300:]}")
                # フォールバック: ケンバーンズなしで生成
                cmd_fallback = [
                    "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image_paths[i]),
                    "-i", str(audio_paths[i]),
                    "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "30",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", "-t", str(scene_dur),
                    str(clip_path),
                ]
                subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=120)

            scene_clips.append(clip_path)

        output_path = job_dir / "final_output.mp4"
        concat_video_clips(scene_clips, output_path)
        logger.info(f"ショート動画合成完了（ケンバーンズ効果付き）: {output_path}")
        return output_path

    def cleanup(self, job_id: str):
        job_dir = config.TMP_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
