"""
KIMIDORI Movie Auto - FLUX.1 [schnell] Client
fal.ai または Replicate 経由で超低コスト・超高速（1〜4ステップ）に高品質画像を生成する。
"""

import os
import logging
from typing import Dict, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)


class FluxSchnellClient:
    """FLUX.1 [schnell] 画像生成APIクライアント (fal.ai / Replicate 対応)"""

    def __init__(self, provider: str = "fal", api_key: Optional[str] = None):
        self.provider = (provider or "fal").lower()
        self.api_key = api_key or os.getenv(f"{self.provider.upper()}_API_KEY", "")

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 576,
        num_inference_steps: int = 4
    ) -> Dict[str, Any]:
        """
        FLUX.1 [schnell] で画像を生成する
        """
        if not self.api_key:
            raise ValueError(f"{self.provider.upper()} のAPIキーが設定されていません。")

        if self.provider == "fal":
            return await self._generate_fal(prompt, width, height, num_inference_steps)
        elif self.provider == "replicate":
            return await self._generate_replicate(prompt, width, height, num_inference_steps)
        else:
            raise ValueError(f"未対応のFLUXプロバイダーです: {self.provider}")

    async def _generate_fal(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int
    ) -> Dict[str, Any]:
        url = "https://fal.run/fal-ai/flux/schnell"
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_inference_steps": steps,
            "enable_safety_checker": False
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    images = data.get("images", [])
                    image_url = images[0].get("url") if images else ""
                    return {
                        "success": True,
                        "provider": "fal",
                        "image_url": image_url,
                        "model": "FLUX.1-schnell"
                    }
                else:
                    err_txt = await resp.text()
                    raise RuntimeError(f"fal.ai FLUX.1 生成エラー ({resp.status}): {err_txt[:150]}")

    async def _generate_replicate(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int
    ) -> Dict[str, Any]:
        url = "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait"
        }
        payload = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": "16:9" if width > height else "9:16",
                "num_inference_steps": steps,
                "output_format": "png"
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    output = data.get("output")
                    image_url = output[0] if (isinstance(output, list) and output) else (output if isinstance(output, str) else "")
                    return {
                        "success": True,
                        "provider": "replicate",
                        "image_url": image_url,
                        "model": "FLUX.1-schnell"
                    }
                else:
                    err_txt = await resp.text()
                    raise RuntimeError(f"Replicate FLUX.1 生成エラー ({resp.status}): {err_txt[:150]}")
