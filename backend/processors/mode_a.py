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

    async def generate_visuals(self, script_data: dict, job_id: str) -> list[Path]:
        """グラデーション背景＋テロップ付き画像を生成"""
        job_dir = self._get_job_dir(job_id)
        image_dir = job_dir / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_paths = []

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
                            params={"query": query, "per_page": 1, "orientation": "portrait"}
                        )
                        if res.status_code == 200:
                            data = res.json()
                            if data.get("photos") and len(data["photos"]) > 0:
                                img_url = data["photos"][0]["src"]["large2x"]
                                img_res = client.get(img_url)
                                if img_res.status_code == 200:
                                    # Pexels画像を読み込み
                                    downloaded = Image.open(httpx.AsyncClient()._get_async_response_content(img_res) if False else __import__('io').BytesIO(img_res.content))
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

            # テロップテキスト描画
            text = scene.get("text_overlay", "")
            if text:
                draw = ImageDraw.Draw(bg_image)
                # テキストの中央配置
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx = (BIG_W - tw) // 2
                ty = int(BIG_H * 0.42)

                # アウトライン
                for ox in range(-3, 4):
                    for oy in range(-3, 4):
                        draw.text((tx + ox, ty + oy), text, fill=(0, 0, 0), font=font)
                draw.text((tx, ty), text, fill=(255, 255, 255), font=font)

                # シーン番号
                num_text = f"SCENE {scene.get('scene_number', i+1)}"
                draw.text((BIG_W // 2 - 60, ty - 60), num_text, fill=palette[2], font=font_small)

            bg_image.save(img_path, "PNG", quality=95)
            image_paths.append(img_path)

        logger.info(f"画像素材 {len(image_paths)}枚 生成完了（ケンバーンズ対応）")
        return image_paths

    async def compose_video(self, script_data, audio_paths, image_paths, job_id, duration):
        """ケンバーンズ効果＋フェードトランジション付きで動画を合成"""
        job_dir = self._get_job_dir(job_id)
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        W, H = config.SHORT_VIDEO_WIDTH, config.SHORT_VIDEO_HEIGHT
        scene_clips = []
        scenes = script_data["scenes"]

        # ケンバーンズ効果のパターン（ズームイン/アウト + パン方向）
        kb_effects = [
            "zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/4-(ih/zoom/4)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='min(zoom+0.001,1.2)':x='iw/4-(iw/zoom/4)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
            "zoompan=z='if(lte(zoom,1.0),1.25,max(1.001,zoom-0.001))':x='iw*3/4-(iw/zoom*3/4)':y='ih/2-(ih/zoom/2)':d={dur}:s={w}x{h}:fps=30",
        ]

        for i, scene in enumerate(scenes):
            if i >= len(audio_paths) or i >= len(image_paths):
                break

            clip_path = clips_dir / f"clip_{i:03d}.mp4"
            scene_dur = scene.get("duration_seconds", 5)
            frames = scene_dur * 30  # 30fps

            # ケンバーンズフィルター
            kb = kb_effects[i % len(kb_effects)].format(dur=frames, w=W, h=H)
            fade_filter = f",fade=t=in:st=0:d=0.5,fade=t=out:st={max(0, scene_dur-0.5)}:d=0.5"

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(image_paths[i]),
                "-i", str(audio_paths[i]),
                "-filter_complex",
                f"[0:v]{kb}{fade_filter},format=yuv420p[v]",
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
                    "ffmpeg", "-y", "-loop", "1", "-i", str(image_paths[i]),
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
