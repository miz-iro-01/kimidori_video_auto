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
                 gemini_api_key: str = "", pexels_api_key: str = "",
                 tts_engine: str = "edge", voice_name: str = "nanami", speaking_rate: float = 1.0,
                 google_tts_key: str = "", elevenlabs_key: str = "", aivis_key: str = ""):
        self.firestore = firestore_service
        self.storage = storage_service
        self.script_gen = ScriptGenerator(api_key=gemini_api_key)
        self.pexels_api_key = pexels_api_key
        
        self.tts = TTSManager(
            engine=tts_engine,
            voice_name=voice_name,
            speaking_rate=speaking_rate,
            google_tts_key=google_tts_key,
            elevenlabs_key=elevenlabs_key,
            aivis_key=aivis_key
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
            font = ImageFont.truetype(config.SUBTITLE_FONT, 72)
            font_small = ImageFont.truetype(config.SUBTITLE_FONT, 42)
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

            # --- テロップテキスト用透過画像の生成（1シーン内を3分割してテンポよく表示） ---
            text = scene.get("text_overlay", "")
            if text:
                # ユーザー指定の句読点ルールを強制適用
                text = text.replace("」。", "」").replace("\\n", " ").strip()
                
                # テキストを2〜3つのパートに分割
                parts = self._split_text_into_parts(text, max_parts=3)
                scene_text_paths = []

                for part_idx, part_text in enumerate(parts):
                    # 各パート内で1行あたり最大14文字で折り返し
                    max_chars = 14
                    final_lines = []
                    for line in part_text.split("\n"):
                        if len(line) > max_chars:
                            wrapped = [line[j:j+max_chars] for j in range(0, len(line), max_chars)]
                            final_lines.extend(wrapped)
                        else:
                            final_lines.append(line)
                    wrapped_text = "\n".join(final_lines)

                    # 動画サイズと同じ透明画像を作成
                    text_image = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(text_image)

                    # テキストの中央・下部配置
                    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font, align="center")
                    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    tx = (W - tw) // 2
                    ty = int(H * 0.76) - th // 2  # 画面下部に配置

                    # 太いアウトライン（縁取り）＋白文字
                    for ox in range(-4, 5):
                        for oy in range(-4, 5):
                            draw.multiline_text((tx + ox, ty + oy), wrapped_text, fill=(0, 0, 0, 255), font=font, align="center")
                    draw.multiline_text((tx, ty), wrapped_text, fill=(255, 255, 255, 255), font=font, align="center")

                    text_img_path = image_dir / f"text_{i:03d}_part{part_idx}.png"
                    text_image.save(text_img_path, "PNG")
                    scene_text_paths.append(text_img_path)

                text_paths.append(scene_text_paths)
            else:
                text_paths.append([])

        logger.info(f"画像素材 {len(image_paths)}枚 生成完了（ケンバーンズ＆テロップ3分割対応）")
        return image_paths, text_paths

    def _split_text_into_parts(self, text: str, max_parts: int = 3) -> list[str]:
        """ナレーションテキストを2〜3つのパートに自然に小分け分割する"""
        import re
        clean = text.strip()
        if len(clean) <= 16:
            return [clean]

        # 1. 句読点（。！？）で分割
        sentences = [s.strip() for s in re.split(r'([。！？!?]+)', clean) if s.strip()]
        merged = []
        k = 0
        while k < len(sentences):
            s = sentences[k]
            if k + 1 < len(sentences) and re.match(r'^[。！？!?]+$', sentences[k+1]):
                s += sentences[k+1]
                k += 2
            else:
                k += 1
            if s.strip():
                merged.append(s.strip())

        if 2 <= len(merged) <= max_parts:
            return merged
        elif len(merged) > max_parts:
            # 均等にmax_parts個へ結合
            res = []
            c_size = (len(merged) + max_parts - 1) // max_parts
            for j in range(0, len(merged), c_size):
                res.append(" ".join(merged[j:j+c_size]))
            return res[:max_parts]

        # 2. 読点（、）で分割
        phrases = [p.strip() for p in re.split(r'([、,]+)', clean) if p.strip()]
        if len(phrases) >= 3:
            p_merged = []
            m = 0
            while m < len(phrases):
                ph = phrases[m]
                if m + 1 < len(phrases) and re.match(r'^[、,]+$', phrases[m+1]):
                    ph += phrases[m+1]
                    m += 2
                else:
                    m += 1
                p_merged.append(ph)
            if 2 <= len(p_merged) <= max_parts:
                return p_merged

        # 3. 文字数による均等2〜3分割
        tot = len(clean)
        if tot <= 32:
            mid = tot // 2
            # スペース等があればそこで区切る
            return [clean[:mid], clean[mid:]]
        else:
            p1 = tot // 3
            p2 = (tot * 2) // 3
            return [clean[:p1], clean[p1:p2], clean[p2:]]

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
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
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
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
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
                    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-t", str(scene_dur),
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
