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
        """ワーカーの疎通とGPU利用可能性を検証 (ComfyUI / LTX-Video および FastAPI ワーカー両対応)"""
        if not self.worker_url:
            return {"connected": False, "error": "ColabワーカーURLが設定されていません"}

        target_url = self.worker_url.rstrip("/")
        try:
            async with aiohttp.ClientSession() as session:
                # 1. ComfyUI (/system_stats) を優先して検査
                try:
                    async with session.get(f"{target_url}/system_stats", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            devices = data.get("devices", [])
                            device_names = [d.get("name", "GPU") for d in devices] if devices else ["Colab GPU"]
                            vram_val = devices[0].get("vram_total", 16 * 1024 * 1024 * 1024) / (1024**3) if devices else 15.0
                            return {
                                "connected": True,
                                "service": "ComfyUI (LTX-Video)",
                                "gpu_available": True,
                                "device": ", ".join(device_names),
                                "vram_gb": round(vram_val, 1),
                                "supported_models": ["LTX-Video", "FLUX.1-schnell"]
                            }
                        elif resp.status == 502:
                            return {
                                "connected": False,
                                "error": "HTTP 502 Bad Gateway: Cloudflareトンネルは接続中ですが、Colab上のComfyUIプロセスがまだ準備中または起動していません。"
                            }
                except Exception:
                    pass

                # 2. 独自FastAPIワーカー (/health) を検査
                try:
                    async with session.get(f"{target_url}/health", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return {
                                "connected": True,
                                "service": "Colab FastAPI Worker",
                                "gpu_available": data.get("gpu_available", False),
                                "device": data.get("device", "unknown"),
                                "vram_gb": data.get("vram_gb", 0),
                                "supported_models": data.get("supported_models", ["FLUX.1-schnell-nf4", "CogVideoX-2B"])
                            }
                        return {"connected": False, "error": f"HTTP {resp.status}"}
                except Exception as ex2:
                    return {"connected": False, "error": f"接続失敗: {str(ex2)}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 576,
        steps: int = 4,
        reference_image_base64: Optional[str] = None,
        strength: float = 0.65
    ) -> Dict[str, Any]:
        """Colab上の FLUX.1 [schnell] (NF4) で完全無料画像生成（img2imgキャラクター一貫性対応）"""
        if not self.worker_url:
            raise ValueError("ColabワーカーURLが未設定です")

        url = f"{self.worker_url}/generate/image"
        payload = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "reference_image_base64": reference_image_base64,
            "strength": strength
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
        reference_image_base64: Optional[str] = None,
        num_frames: int = 16,
        fps: int = 8,
        duration_seconds: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """Colab上の CogVideoX-2B / AnimateDiff で完全無料動画生成"""
        if not self.worker_url:
            raise ValueError("ColabワーカーURLが未設定です")

        url = f"{self.worker_url}/generate/video"
        effective_b64 = image_base64 or reference_image_base64 or ""
        payload = {
            "prompt": prompt,
            "image_base64": effective_b64,
            "reference_image_base64": effective_b64,
            "num_frames": num_frames,
            "fps": fps,
            "duration_seconds": duration_seconds
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

    async def generate_comfyui_ltx_video(
        self,
        prompt: str,
        negative_prompt: str = "worst quality, low quality, blurry, distorted, split screen, comic panels, text, watermark",
        width: int = 512,
        height: int = 768,
        num_frames: int = 97,
        steps: int = 20,
        fps: int = 24,
        output_file_path: Optional[str] = None,
        output_path: Optional[str] = None,
        timeout_sec: int = 300,
        image_path: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Google Colab上のComfyUI (LTX-Video) へワークフローを投入し、
        生成されたシーン画像（image_path）をリファレンス（Image-to-Video）としてアニメーション動画（MP4）を生成・保存する。
        """
        import asyncio
        import random
        from pathlib import Path

        if not self.worker_url:
            raise ValueError("ComfyUI / ColabワーカーURLが未設定です")

        output_file_path = output_file_path or output_path
        base_url = self.worker_url.rstrip("/")
        seed = random.randint(1, 1000000000)

        def build_t2v_workflow() -> Dict[str, Any]:
            return {
                "1": {
                    "inputs": {"ckpt_name": "ltx-video-2b-v0.9.1.safetensors"},
                    "class_type": "CheckpointLoaderSimple"
                },
                "2": {
                    "inputs": {"text": prompt, "clip": ["1", 1]},
                    "class_type": "CLIPTextEncode"
                },
                "3": {
                    "inputs": {"text": negative_prompt, "clip": ["1", 1]},
                    "class_type": "CLIPTextEncode"
                },
                "4": {
                    "inputs": {"width": width, "height": height, "length": num_frames, "batch_size": 1},
                    "class_type": "EmptyLTXVLatentVideo"
                },
                "5": {
                    "inputs": {
                        "seed": seed, "steps": steps, "cfg": 3.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
                        "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                        "latent_image": ["4", 0]
                    },
                    "class_type": "KSampler"
                },
                "6": {
                    "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                    "class_type": "VAEDecode"
                },
                "7": {
                    "inputs": {
                        "images": ["6", 0],
                        "frame_rate": 25,
                        "loop_count": 0,
                        "filename_prefix": "LTXVideo",
                        "format": "video/h264-mp4",
                        "pingpong": False,
                        "save_output": True
                    },
                    "class_type": "VHS_VideoCombine"
                }
            }

        def build_i2v_workflow(uploaded_img_name: str) -> Dict[str, Any]:
            return {
                "1": {
                    "inputs": {"ckpt_name": "ltx-video-2b-v0.9.1.safetensors"},
                    "class_type": "CheckpointLoaderSimple"
                },
                "2": {
                    "inputs": {"text": prompt, "clip": ["1", 1]},
                    "class_type": "CLIPTextEncode"
                },
                "3": {
                    "inputs": {"text": negative_prompt, "clip": ["1", 1]},
                    "class_type": "CLIPTextEncode"
                },
                "8": {
                    "inputs": {"image": uploaded_img_name},
                    "class_type": "LoadImage"
                },
                "4": {
                    "inputs": {
                        "positive": ["2", 0],
                        "negative": ["3", 0],
                        "vae": ["1", 2],
                        "image": ["8", 0],
                        "width": width,
                        "height": height,
                        "length": num_frames,
                        "batch_size": 1
                    },
                    "class_type": "LTXVImgToVideo"
                },
                "5": {
                    "inputs": {
                        "seed": seed, "steps": steps, "cfg": 3.0,
                        "sampler_name": "euler", "scheduler": "normal", "denoise": 0.85,
                        "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 1],
                        "latent_image": ["4", 2]
                    },
                    "class_type": "KSampler"
                },
                "6": {
                    "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                    "class_type": "VAEDecode"
                },
                "7": {
                    "inputs": {
                        "images": ["6", 0],
                        "frame_rate": 25,
                        "loop_count": 0,
                        "filename_prefix": "LTXVideo_I2V",
                        "format": "video/h264-mp4",
                        "pingpong": False,
                        "save_output": True
                    },
                    "class_type": "VHS_VideoCombine"
                }
            }

        async with aiohttp.ClientSession() as session:
            uploaded_image_name = None
            if image_path and Path(image_path).exists():
                try:
                    upload_url = f"{base_url}/upload/image"
                    form = aiohttp.FormData()
                    with open(image_path, "rb") as img_f:
                        img_bytes = img_f.read()
                    form.add_field("image", img_bytes, filename=Path(image_path).name, content_type="image/png")
                    form.add_field("overwrite", "true")
                    async with session.post(upload_url, data=form, timeout=aiohttp.ClientTimeout(total=20)) as up_resp:
                        if up_resp.status == 200:
                            up_data = await up_resp.json()
                            uploaded_image_name = up_data.get("name")
                            logger.info(f"Uploaded scene reference image to ComfyUI: {uploaded_image_name}")
                except Exception as up_err:
                    logger.warning(f"ComfyUI image upload skipped ({up_err}), falling back to T2V workflow")

            # 1. プロンプト投入（I2V優先 ➔ 失敗時はT2Vへ自動フォールバック）
            prompt_url = f"{base_url}/prompt"
            prompt_id = None
            workflows_to_try = [build_i2v_workflow(uploaded_image_name), build_t2v_workflow()] if uploaded_image_name else [build_t2v_workflow()]

            last_err = None
            for wf in workflows_to_try:
                try:
                    async with session.post(prompt_url, json={"prompt": wf}, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            prompt_id = data.get("prompt_id")
                            if prompt_id:
                                break
                        else:
                            err_text = await resp.text()
                            last_err = RuntimeError(f"ComfyUI /prompt エラー ({resp.status}): {err_text[:120]}")
                except Exception as e:
                    last_err = e

            if not prompt_id:
                logger.warning(f"Failed to queue ComfyUI prompt: {last_err}")
                raise last_err or RuntimeError("ComfyUIから有効な prompt_id を取得できませんでした")

            # 2. 完了ポーリング
            history_url = f"{base_url}/history/{prompt_id}"
            start_time = asyncio.get_event_loop().time()
            output_file_info = None

            while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
                try:
                    async with session.get(history_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            hist_data = await resp.json()
                            prompt_hist = hist_data.get(prompt_id)
                            if prompt_hist and "outputs" in prompt_hist:
                                for node_id, node_out in prompt_hist["outputs"].items():
                                    files = node_out.get("gifs") or node_out.get("videos") or node_out.get("images")
                                    if files and len(files) > 0:
                                        output_file_info = files[0]
                                        break
                                if output_file_info:
                                    break
                except Exception:
                    pass
                await asyncio.sleep(3)

            if not output_file_info:
                raise TimeoutError(f"ComfyUI動画生成がタイムアウトしました ({timeout_sec}秒)")

            # 3. 動画バイナリダウンロード
            fname = output_file_info.get("filename", "")
            subfolder = output_file_info.get("subfolder", "")
            ftype = output_file_info.get("type", "output")
            view_url = f"{base_url}/view?filename={fname}&subfolder={subfolder}&type={ftype}"

            if output_file_path:
                out_path = Path(output_file_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                async with session.get(view_url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        with open(out_path, "wb") as f:
                            f.write(content)
                        return {
                            "success": True,
                            "video_path": str(out_path),
                            "video_url": view_url,
                            "prompt_id": prompt_id
                        }
                    else:
                        raise RuntimeError(f"ComfyUI動画ダウンロード失敗 ({resp.status})")

            return {
                "success": True,
                "video_url": view_url,
                "prompt_id": prompt_id
            }
