"""
高品質OSS TTS（ElevenLabs互換・F5-TTS・Fish Speech・GPT-SoVITS・OpenAI互換）汎用クライアントアダプタ層
POST /v1/text-to-speech/{voice_id}, POST /v1/text-to-speech, POST /v1/audio/speech 等に統合対応
"""

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal, Dict, Any

import httpx

import config

logger = logging.getLogger(__name__)

TTSProtocolType = Literal["elevenlabs_compatible", "openai_compatible", "vllm_omni", "fastapi", "f5_tts", "fish_speech", "auto"]


@dataclass
class HighQualityTTSConfig:
    """高品質OSS TTS（OpenBMB VoxCPM / ElevenLabs互換 / F5-TTS / Fish Speech）接続設定"""
    endpoint_url: str = ""
    api_key: str = ""
    voice_id: str = "default"
    model_id: str = "openbmb/VoxCPM2"
    protocol: str = "vllm_omni"
    speaking_rate: float = 1.0
    stability: float = 0.55
    similarity_boost: float = 0.78
    sample_rate: int = 48000
    prompt_text: Optional[str] = None
    fallback_engine: str = "edge"
    fallback_voice: str = "ja-JP-NanamiNeural"

    @classmethod
    def from_params(cls, params: Optional[Dict[str, Any]] = None, voice_name: str = "", is_voxcpm: bool = False) -> "HighQualityTTSConfig":
        params = params or {}
        # VoxCPM優先、次にOSS ElevenLabs設定をフォールバックとして取得
        endpoint_url = (
            params.get("voxcpm_endpoint_url")
            or params.get("voxcpm_url")
            or (getattr(config, "VOXCPM_ENDPOINT_URL", "") if is_voxcpm else "")
            or params.get("oss_elevenlabs_url")
            or params.get("oss_tts_url")
            or getattr(config, "OSS_TTS_ENDPOINT_URL", "")
            or getattr(config, "VOXCPM_ENDPOINT_URL", "http://localhost:8808")
        ).strip()
        api_key = (
            params.get("voxcpm_api_key")
            or (getattr(config, "VOXCPM_API_KEY", "") if is_voxcpm else "")
            or params.get("oss_elevenlabs_key")
            or params.get("elevenlabs_key")
            or params.get("oss_tts_api_key")
            or getattr(config, "OSS_TTS_API_KEY", "")
        ).strip()
        voice_id = (
            params.get("voxcpm_voice_id")
            or params.get("voxcpm_voice")
            or (params.get("oss_elevenlabs_voice_id") if not is_voxcpm else "")
            or params.get("oss_voice")
            or params.get("elevenlabs_voice_id")
            or (voice_name if voice_name and voice_name not in ("nanami", "default") else "")
            or (getattr(config, "VOXCPM_VOICE_ID", "default") if is_voxcpm else getattr(config, "OSS_TTS_VOICE_ID", "default"))
        ).strip()
        protocol = (
            params.get("voxcpm_protocol")
            or (getattr(config, "VOXCPM_PROTOCOL", "") if is_voxcpm else "")
            or params.get("oss_elevenlabs_protocol")
            or params.get("oss_tts_format")
            or (getattr(config, "VOXCPM_PROTOCOL", "vllm_omni") if is_voxcpm else getattr(config, "OSS_TTS_PROTOCOL", "elevenlabs_compatible"))
        ).strip()
        prompt_text = params.get("voxcpm_prompt") or params.get("prompt_text") or None
        speaking_rate = float(params.get("speaking_rate", 1.0) or 1.0)
        return cls(
            endpoint_url=endpoint_url,
            api_key=api_key,
            voice_id=voice_id or "default",
            model_id=params.get("model") or getattr(config, "VOXCPM_MODEL", "openbmb/VoxCPM2"),
            protocol=protocol or ("vllm_omni" if is_voxcpm else "elevenlabs_compatible"),
            speaking_rate=speaking_rate,
            sample_rate=int(params.get("sample_rate", getattr(config, "VOXCPM_SAMPLE_RATE", 48000))),
            prompt_text=prompt_text,
        )


class HighQualityOSSTTSAdapter:
    """
    POST /v1/text-to-speech (ElevenLabs互換) やオープンソースTTSサーバー
    (F5-TTS, Fish Speech, GPT-SoVITS, OpenAI互換 /v1/audio/speech) に接続する汎用TTSクライアントアダプタ
    """

    def __init__(self, tts_config: Optional[HighQualityTTSConfig] = None):
        self.config = tts_config or HighQualityTTSConfig.from_params()

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        allow_fallback: bool = True,
    ) -> Path:
        """
        テキストから音声ファイルを生成して output_path に保存する。
        1. ElevenLabs互換エンドポイント (POST /v1/text-to-speech/{voice_id} または POST /v1/text-to-speech)
        2. オープンソースTTSサーバー (F5-TTS / Fish Speech / OpenAI互換 /v1/audio/speech)
        の順または指定プロトコルで試行し、失敗時は allow_fallback=True なら Edge-TTS へフォールバックする。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        base_url = (self.config.endpoint_url or "").strip().rstrip("/")
        if not base_url:
            if allow_fallback:
                logger.warning("高品質OSS TTSのエンドポイントURLが未設定のため、標準Neural音声へフォールバックします。")
                return await self._fallback_edge_tts(text, output_path)
            raise ValueError("高品質OSS TTSのエンドポイントURLが設定されていません。設定画面または.envで指定してください。")

        protocol = (self.config.protocol or "vllm_omni").lower()
        last_error: Optional[Exception] = None

        # プロトコル優先順位の構築（OpenBMB VoxCPM vLLM-Omni, ElevenLabs互換, FastAPI, OSS TTS）
        attempt_chain = []
        if protocol in ("vllm_omni", "vllm", "voxcpm", "openai", "openai_compatible"):
            attempt_chain = ["vllm_omni", "openai_speech", "elevenlabs_v1_voice", "elevenlabs_v1_root", "voxcpm_fastapi", "oss_tts"]
        elif protocol in ("elevenlabs", "elevenlabs_compatible"):
            attempt_chain = ["elevenlabs_v1_voice", "elevenlabs_v1_root", "vllm_omni", "openai_speech", "voxcpm_fastapi", "oss_tts"]
        elif protocol in ("fastapi", "voxcpm_fastapi"):
            attempt_chain = ["voxcpm_fastapi", "vllm_omni", "openai_speech", "elevenlabs_v1_voice", "elevenlabs_v1_root"]
        elif protocol in ("f5", "f5_tts", "fish", "fish_speech"):
            attempt_chain = ["elevenlabs_v1_root", "openai_speech", "oss_tts", "elevenlabs_v1_voice"]
        else:
            attempt_chain = ["vllm_omni", "elevenlabs_v1_voice", "elevenlabs_v1_root", "openai_speech", "voxcpm_fastapi", "oss_tts"]

        headers: Dict[str, str] = {
            "Accept": "audio/mpeg, audio/wav, application/octet-stream, */*",
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["xi-api-key"] = self.config.api_key
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        voice_id = self.config.voice_id or "default"

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            for mode in attempt_chain:
                try:
                    url, payload = self._build_request(base_url, voice_id, text, mode)
                    res = await client.post(url, json=payload, headers=headers)
                    if res.status_code == 200 and len(res.content) > 128:
                        self._write_normalized_audio(res.content, output_path)
                        logger.info(f"OpenBMB VoxCPM/OSS TTS合成成功 ({mode} -> {url}): {output_path.name}")
                        return output_path
                    else:
                        last_error = RuntimeError(f"HTTP {res.status_code}: {res.text[:200]}")
                except Exception as err:
                    last_error = err
                    continue

        if allow_fallback:
            logger.warning(f"OpenBMB VoxCPM/OSS TTSサーバーへの接続失敗 ({last_error})。無料TTS (Edge-TTS) へ自動フォールバックします。")
            return await self._fallback_edge_tts(text, output_path)

        raise RuntimeError(
            f"OpenBMB VoxCPM（ElevenLabs互換）サーバーでの音声合成に失敗しました ({base_url}): {last_error}"
        )

    def _build_request(self, base_url: str, voice_id: str, text: str, mode: str) -> tuple[str, Dict[str, Any]]:
        """各互換エンドポイント仕様に合わせたURLとJSONペイロードを構築"""
        has_v1_tts = "/v1/text-to-speech" in base_url
        has_v1_audio = "/v1/audio/speech" in base_url

        if mode == "vllm_omni":
            url = base_url if has_v1_audio else f"{base_url}/v1/audio/speech"
            payload = {
                "model": self.config.model_id or "openbmb/VoxCPM2",
                "input": text,
                "voice": voice_id,
                "response_format": "wav",
                "speed": self.config.speaking_rate,
            }
            if self.config.prompt_text:
                payload["prompt"] = self.config.prompt_text
            return url, payload

        if mode == "voxcpm_fastapi":
            url = base_url if base_url.endswith("/v1/tts") or base_url.endswith("/tts") else f"{base_url}/v1/tts"
            payload = {
                "text": text,
                "voice": voice_id,
                "sample_rate": self.config.sample_rate,
            }
            if self.config.prompt_text:
                payload["prompt_text"] = self.config.prompt_text
            return url, payload

        if mode == "elevenlabs_v1_voice":
            if has_v1_tts:
                url = base_url if base_url.endswith(voice_id) else f"{base_url}/{voice_id}"
            else:
                url = f"{base_url}/v1/text-to-speech/{voice_id}"
            payload = {
                "text": text,
                "voice_id": voice_id,
                "model_id": self.config.model_id or "openbmb/VoxCPM2",
                "voice_settings": {
                    "stability": self.config.stability,
                    "similarity_boost": self.config.similarity_boost,
                    "speed": self.config.speaking_rate,
                },
            }
            if self.config.prompt_text:
                payload["prompt"] = self.config.prompt_text
            return url, payload

        if mode == "elevenlabs_v1_root":
            url = base_url if has_v1_tts else f"{base_url}/v1/text-to-speech"
            payload = {
                "text": text,
                "voice_id": voice_id,
                "voice": voice_id,
                "model_id": self.config.model_id or "openbmb/VoxCPM2",
                "speed": self.config.speaking_rate,
                "voice_settings": {
                    "stability": self.config.stability,
                    "similarity_boost": self.config.similarity_boost,
                },
            }
            if self.config.prompt_text:
                payload["prompt"] = self.config.prompt_text
            return url, payload

        if mode == "openai_speech":
            url = base_url if has_v1_audio else f"{base_url}/v1/audio/speech"
            payload = {
                "model": self.config.model_id or "openbmb/VoxCPM2",
                "input": text,
                "voice": voice_id,
                "response_format": "mp3",
                "speed": self.config.speaking_rate,
            }
            return url, payload

        # oss_tts (Fish Speech / F5-TTS / GPT-SoVITS /v1/tts or /tts)
        url = base_url if base_url.endswith("/tts") else f"{base_url}/v1/tts"
        payload = {
            "text": text,
            "text_lang": "ja",
            "ref_audio_path": voice_id,
            "voice": voice_id,
            "speaker": voice_id,
            "speed_factor": self.config.speaking_rate,
            "format": "mp3",
        }
        return url, payload

    @staticmethod
    def _write_normalized_audio(raw_bytes: bytes, output_path: Path) -> None:
        """48kHz WAVやOGGバイナリが返却された場合でも拡張子に合わせて正規化保存する"""
        is_wav = raw_bytes[:4] == b"RIFF"
        if is_wav and output_path.suffix.lower() == ".mp3":
            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_file(io.BytesIO(raw_bytes), format="wav")
                seg.export(str(output_path), format="mp3")
                return
            except Exception:
                pass
        output_path.write_bytes(raw_bytes)

    async def _fallback_edge_tts(self, text: str, output_path: Path) -> Path:
        import edge_tts
        rate_pct = int((self.config.speaking_rate - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
        comm = edge_tts.Communicate(text, self.config.fallback_voice, rate=rate_str)
        await comm.save(str(output_path))
        return output_path


class VoxCPMClientAdapter(HighQualityOSSTTSAdapter):
    """
    OpenBMB VoxCPM（VoxCPM2 48kHz Studio Quality / ElevenLabs Compatible）クライアントアダプタ
    GitHub: https://github.com/OpenBMB/VoxCPM.git
    vLLM-Omni (/v1/audio/speech), ElevenLabs互換 (/v1/text-to-speech), FastAPI (/v1/tts) に標準対応
    """
    def __init__(self, tts_config: Optional[HighQualityTTSConfig] = None):
        cfg = tts_config or HighQualityTTSConfig.from_params(is_voxcpm=True)
        super().__init__(tts_config=cfg)
