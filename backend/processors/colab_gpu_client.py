"""
KIMIDORI Movie Auto - Google Colab Free GPU Worker Client
手元PCの負荷・電気代ゼロで、Google Colabの無料枠（T4 GPU / 16GB VRAM）を活用して
FLUX.1 [schnell] (NF4量子化) および CogVideoX-2B / AnimateDiff による動画生成を完全無料で実行する。
"""

import logging
from typing import Dict, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)


class ColabGpuClient:
    """Google Colab 上で稼働する無料GPUワーカー（FastAPI + ngrok/tunnel）連携クライアント"""

    def __init__(self, worker_url: str):
        self.worker_url = (worker_url or "").rstrip("/")

    async def check_health(self) -> Dict[str, Any]:
        """ワーカーの疎通とGPU利用可能性を検証"""
        if not self.worker_url:
            return {"connected": False, "error": "ColabワーカーURLが設定されていません"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.worker_url}/health", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "connected": True,
                            "gpu_available": data.get("gpu_available", False),
                            "device": data.get("device", "unknown"),
                            "vram_gb": data.get("vram_gb", 0),
                            "supported_models": data.get("supported_models", ["FLUX.1-schnell-nf4", "CogVideoX-2B"])
                        }
                    return {"connected": False, "error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 576,
        steps: int = 4
    ) -> Dict[str, Any]:
        """Colab上の FLUX.1 [schnell] (NF4) で完全無料画像生成"""
        if not self.worker_url:
            raise ValueError("ColabワーカーURLが未設定です")

        url = f"{self.worker_url}/generate/image"
        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "success": True,
                        "provider": "colab_free_gpu",
                        "image_base64": data.get("image_base64"),
                        "image_url": data.get("image_url", "")
                    }
                else:
                    err_txt = await resp.text()
                    raise RuntimeError(f"Colab画像生成エラー ({resp.status}): {err_txt[:150]}")

    async def generate_video(
        self,
        prompt: str,
        image_base64: Optional[str] = None,
        num_frames: int = 16,
        fps: int = 8
    ) -> Dict[str, Any]:
        """Colab上の CogVideoX-2B / AnimateDiff で完全無料動画生成"""
        if not self.worker_url:
            raise ValueError("ColabワーカーURLが未設定です")

        url = f"{self.worker_url}/generate/video"
        payload = {
            "prompt": prompt,
            "image_base64": image_base64 or "",
            "num_frames": num_frames,
            "fps": fps
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "success": True,
                        "provider": "colab_free_gpu",
                        "video_base64": data.get("video_base64"),
                        "video_url": data.get("video_url", "")
                    }
                else:
                    err_txt = await resp.text()
                    raise RuntimeError(f"Colab動画生成エラー ({resp.status}): {err_txt[:150]}")
