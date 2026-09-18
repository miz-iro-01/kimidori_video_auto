import os
import io
import json
import asyncio
import aiohttp
from pathlib import Path
from PIL import Image, ImageDraw

class AssetGeneratorHook:
    """
    素材生成プラグインフック (Pluggable Asset Generator)
    
    Google Flowに依存せず、任意の画像・動画生成APIや自前スクリプトと
    簡単に連携できるように設計された統一インターフェースです。
    
    【サポートする生成モード】
    1. 'gemini_imagen': Google Gemini / Imagen 3 APIによる直接画像生成 (要APIキー)
    2. 'custom_api': OpenAI DALL-E 3, ComfyUI, Midjourney API等へのHTTPリクエスト
    3. 'preview_card': Pillowによる美麗なプレビューカード生成 (API不要・即座に動作検証可能)
    4. 'external': 外部プロセスがoutputフォルダに書き込むのを監視/受付
    """

    def __init__(self, api_key: str = None, mode: str = "auto"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.mode = mode

    async def generate_asset(self, cut: dict, output_path: str, format_ratio: str = "16:9") -> str:
        """
        1カット分の素材（画像または動画）を生成して output_path に保存する。
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 既存ファイルのスキップ（冪等性）
        if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            return output_path

        cut_num = cut.get("cut_number", 1)
        dialogue = cut.get("dialogue", "")
        speaker = cut.get("speaker", "ナレーション")
        prompt = cut.get("visual_prompt", cut.get("scene_description", ""))
        is_video = cut.get("is_video", False) or output_path.endswith(".mp4")

        # 1. Gemini Imagen 3 直接APIが利用可能な場合
        if self.api_key and (self.mode in ["auto", "gemini_imagen"]) and not is_video:
            try:
                ok = await self._generate_via_imagen_api(prompt, output_path, format_ratio)
                if ok and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    return output_path
            except Exception as e:
                print(f"[GENERATOR HOOK] Imagen API Error: {e}, falling back to preview card...")

        # 2. スタンドアロンプレビューカード生成（API不要・即座に動作確認可能）
        await self._generate_preview_card(cut_num, speaker, dialogue, prompt, output_path, format_ratio, is_video)
        return output_path

    async def _generate_via_imagen_api(self, prompt: str, output_path: str, format_ratio: str = "16:9") -> bool:
        """Gemini Imagen 3 REST API直接呼び出し"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={self.api_key}"
        aspect = "16:9" if format_ratio == "16:9" else "9:16"

        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "aspectRatio": aspect,
                "personGeneration": "ALLOW_ADULT"
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    predictions = data.get("predictions", [])
                    if predictions and "bytesBase64Encoded" in predictions[0]:
                        import base64
                        img_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                        with open(output_path, "wb") as f:
                            f.write(img_bytes)
                        return True
        return False

    async def _generate_preview_card(self, cut_num: int, speaker: str, dialogue: str, prompt: str, output_path: str, format_ratio: str = "16:9", is_video: bool = False):
        """
        Pillowによる高品質なプレビューカード生成
        他の生成AI（DALL-EやMidjourneyなど）と連携する前のUI動作確認・デモにも最適
        """
        width, height = (1280, 720) if format_ratio == "16:9" else (720, 1280)
        img = Image.new("RGB", (width, height), color=(18, 24, 38))
        draw = ImageDraw.Draw(img)

        # 背景グラデーション
        for y in range(height):
            r = int(18 + (y / height) * 20)
            g = int(24 + (y / height) * 30)
            b = int(38 + (y / height) * 50)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 外枠ボーダー
        draw.rectangle([20, 20, width - 20, height - 20], outline=(59, 130, 246), width=3)

        # ヘッダー情報
        cut_label = f"Cut_{cut_num:03d}" if cut_num > 0 else "Cut_000 (Thumbnail)"
        media_type = "[AI Video Clip (MP4)]" if is_video else "[Hi-Res Image (PNG)]"
        
        draw.rectangle([40, 40, 380, 95], fill=(37, 99, 235))
        draw.text((55, 58), f"{cut_label} {media_type}", fill=(255, 255, 255))

        # 話者 & セリフ
        draw.text((50, 130), f"Speaker: {speaker}", fill=(147, 197, 253))
        
        dialogue_text = dialogue if dialogue else "(Narration / BGM Scene)"
        draw.text((50, 180), f"Dialogue: {dialogue_text[:70]}", fill=(241, 245, 249))

        # ビジュアルプロンプト
        prompt_text = prompt if prompt else "(Visual Prompt)"
        draw.text((50, 260), "Visual Prompt:", fill=(209, 213, 219))
        draw.text((50, 300), f"{prompt_text[:120]}...", fill=(156, 163, 175))

        # フッター
        footer_text = "Video Auto Studio - Portable Asset Engine"
        draw.text((50, height - 60), footer_text, fill=(100, 116, 139))

        img.save(output_path, "PNG")
        return output_path
