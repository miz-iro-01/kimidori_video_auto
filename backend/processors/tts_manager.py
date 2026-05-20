import logging
import asyncio
from pathlib import Path
import httpx
from google.cloud import texttospeech

from processors.edge_tts_engine import EdgeTTSEngine

logger = logging.getLogger(__name__)

class TTSManager:
    """複数のTTSエンジン（Edge, Google Cloud, ElevenLabs, AivisSpeech）を統合管理するマネージャー"""

    def __init__(
        self,
        engine: str = "edge",
        voice_name: str = "nanami",
        speaking_rate: float = 1.0,
        google_tts_key: str = "",
        elevenlabs_key: str = "",
        aivis_key: str = ""
    ):
        self.engine = engine
        self.voice_name = voice_name
        self.speaking_rate = speaking_rate
        
        self.google_tts_key = google_tts_key
        self.elevenlabs_key = elevenlabs_key
        self.aivis_key = aivis_key
        
        # Edge TTS エンジン
        self.edge_engine = EdgeTTSEngine(voice_name=voice_name, speaking_rate=speaking_rate)

    async def synthesize_all_scenes(self, scenes: list[dict], job_dir: Path) -> list[Path]:
        """指定されたエンジンで全シーンの音声を合成する"""
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        
        audio_paths = []
        for i, scene in enumerate(scenes):
            narration = scene.get("narration", "")
            if not narration:
                continue

            output_path = audio_dir / f"scene_{i:03d}.mp3"
            
            # 各エンジンへのルーティング
            try:
                if self.engine == "google":
                    await self._synthesize_google(narration, output_path)
                elif self.engine == "elevenlabs":
                    await self._synthesize_elevenlabs(narration, output_path)
                elif self.engine == "aivis":
                    await self._synthesize_aivis(narration, output_path)
                else:
                    # デフォルト: Edge TTS
                    await self.edge_engine.synthesize_scene(narration, output_path)
            except Exception as e:
                logger.error(f"TTS合成エラー ({self.engine}): {e}")
                # エラー時はフォールバックとしてEdge TTSを使う
                logger.warning(f"Edge TTSへフォールバックします...")
                await self.edge_engine.synthesize_scene(narration, output_path)
                
            audio_paths.append(output_path)

        logger.info(f"全{len(audio_paths)}シーンの音声合成完了 ({self.engine})")
        return audio_paths

    async def _synthesize_google(self, text: str, output_path: Path):
        """Google Cloud TTSの実装"""
        if not self.google_tts_key:
            raise ValueError("Google Cloud TTSのAPIキーまたはクレデンシャルが設定されていません")
            
        client = texttospeech.TextToSpeechClient(client_options={"api_key": self.google_tts_key})
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # 音声パラメータ（Googleの代表的な日本語音声）
        voice = texttospeech.VoiceSelectionParams(
            language_code="ja-JP",
            name="ja-JP-Neural2-B" # 女性音声（必要に応じてマッピング）
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=self.speaking_rate
        )
        
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        with open(output_path, "wb") as out:
            out.write(response.audio_content)

    async def _synthesize_elevenlabs(self, text: str, output_path: Path):
        """ElevenLabs TTSの実装"""
        if not self.elevenlabs_key:
            raise ValueError("ElevenLabs APIキーが設定されていません")
            
        # ElevenLabsのデフォルト日本語対応音声ID（例: Rachel）
        voice_id = "21m00Tcm4TlvDq8ikWAM" 
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.elevenlabs_key
        }
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)

    async def _synthesize_aivis(self, text: str, output_path: Path):
        """Aivis Cloud APIの実装 (VOICEVOX互換REST)"""
        if not self.aivis_key:
            raise ValueError("Aivis APIキーが設定されていません")
            
        # Aivis Cloud / VOICEVOX互換エンドポイントを想定した処理
        # 話者ID (speaker=1) を指定
        speaker_id = 1
        base_url = "https://api.aivis-project.com/v1" # 仮のクラウドAPIエンドポイント
        
        headers = {
            "Authorization": f"Bearer {self.aivis_key}"
        }
        
        async with httpx.AsyncClient() as client:
            # 1. audio_queryの作成
            query_res = await client.post(
                f"{base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                headers=headers
            )
            query_res.raise_for_status()
            audio_query = query_res.json()
            
            # 話速の変更
            audio_query["speedScale"] = self.speaking_rate
            
            # 2. synthesisで音声合成
            synth_res = await client.post(
                f"{base_url}/synthesis",
                params={"speaker": speaker_id},
                json=audio_query,
                headers=headers
            )
            synth_res.raise_for_status()
            
            # mp3ではなくwav形式で返る場合が多いが、ffmepg結合時に処理可能なので保存
            with open(output_path.with_suffix('.wav'), "wb") as f:
                f.write(synth_res.content)
            
            # pydubやffmpegでmp3変換を避けるため、パス自体はwavとして戻す（あるいは上書き）
            import shutil
            shutil.move(str(output_path.with_suffix('.wav')), str(output_path))
