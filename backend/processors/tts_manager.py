"""
統合TTSマネージャー（完全無料・フリーミアム・有料の全TTSエンジン対応）

対応エンジン:
1. 完全無料（オープンソース・ローカル含む）:
   - edge: Microsoft Edge Neural TTS (完全無料・APIキー不要)
   - gtts: Google Translate TTS (完全無料・APIキー不要)
   - voicevox: VOICEVOX (商用利用無料・ずんだもん等・ローカル/外部API)
   - sharevox: SHAREVOX (完全無料・ローカル/外部API)
   - coeiroink: COEIROINK (完全無料・ローカル/外部API)
   - aivis: AivisSpeech (完全無料・ローカル/Aivis Cloud)
   - oss_custom: Fish Speech / GPT-SoVITS / ChatTTS / Bert-VITS2 / StyleTTS2 (ローカル/外部エンドポイント)

2. 制限付き無料 / フリーミアム（無料枠あり）:
   - google: Google Cloud Text-to-Speech (Neural2/WaveNet)
   - azure: Microsoft Azure Speech (月50万文字無料 F0 / ニューラル音声)
   - elevenlabs: ElevenLabs (月10,000文字無料 / 超高品質音声クローン)
   - amazon_polly: Amazon Polly (AWS 12ヶ月無料枠)
   - ondoku: 音読さん (月5,000文字無料)
   - coefont: CoeFont (API対応)

3. 完全有料 / 従量課金:
   - openai: OpenAI TTS (tts-1 / tts-1-hd, alloy, echo, etc.)
"""

import asyncio
import base64
import html
import logging
from pathlib import Path
import subprocess
import urllib.parse
import httpx

from processors.edge_tts_engine import EdgeTTSEngine

logger = logging.getLogger(__name__)


class TTSManager:
    """全TTSエンジン（無料・フリーミアム・有料）を統合管理するエンジン"""

    def __init__(
        self,
        engine: str = "edge",
        voice_name: str = "nanami",
        speaking_rate: float = 1.0,
        # Google Cloud TTS
        google_tts_key: str = "",
        # ElevenLabs
        elevenlabs_key: str = "",
        elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        # OpenAI TTS
        openai_key: str = "",
        openai_model: str = "tts-1",
        openai_voice: str = "alloy",
        # Microsoft Azure Speech
        azure_key: str = "",
        azure_region: str = "japaneast",
        azure_voice: str = "ja-JP-NanamiNeural",
        # Amazon Polly
        aws_access_key: str = "",
        aws_secret_key: str = "",
        aws_region: str = "ap-northeast-1",
        polly_voice: str = "Mizuki",
        # VOICEVOX / SHAREVOX / COEIROINK / Aivis
        voicevox_url: str = "http://localhost:50021",
        voicevox_speaker: int = 3,  # ずんだもん(ノーマル)
        sharevox_url: str = "http://localhost:50025",
        sharevox_speaker: int = 0,
        coeiroink_url: str = "http://localhost:50031",
        coeiroink_speaker: str = "",
        coeiroink_style: int = 0,
        aivis_url: str = "http://localhost:10101",
        aivis_key: str = "",
        aivis_speaker: int = 1,
        # OSS Custom (Fish Speech, GPT-SoVITS, ChatTTS, Bert-VITS2, StyleTTS2)
        oss_tts_url: str = "http://localhost:9880",
        oss_tts_format: str = "openai",
        oss_voice: str = "",
        # 音読さん (Ondoku)
        ondoku_token: str = "",
        # CoeFont
        coefont_key: str = "",
        coefont_secret: str = "",
        coefont_id: str = ""
    ):
        self.engine = (engine or "edge").lower()
        self.voice_name = voice_name or "nanami"
        self.speaking_rate = float(speaking_rate) if speaking_rate else 1.0

        # 各認証情報・設定
        self.google_tts_key = google_tts_key
        self.elevenlabs_key = elevenlabs_key
        self.elevenlabs_voice_id = elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"
        
        self.openai_key = openai_key
        self.openai_model = openai_model or "tts-1"
        self.openai_voice = openai_voice or "alloy"

        self.azure_key = azure_key
        self.azure_region = azure_region or "japaneast"
        self.azure_voice = azure_voice or "ja-JP-NanamiNeural"

        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region or "ap-northeast-1"
        self.polly_voice = polly_voice or "Mizuki"

        self.voicevox_url = voicevox_url.rstrip("/") if voicevox_url else "http://localhost:50021"
        self.voicevox_speaker = int(voicevox_speaker) if str(voicevox_speaker).isdigit() else 3

        self.sharevox_url = sharevox_url.rstrip("/") if sharevox_url else "http://localhost:50025"
        self.sharevox_speaker = int(sharevox_speaker) if str(sharevox_speaker).isdigit() else 0

        self.coeiroink_url = coeiroink_url.rstrip("/") if coeiroink_url else "http://localhost:50031"
        self.coeiroink_speaker = coeiroink_speaker
        self.coeiroink_style = int(coeiroink_style) if str(coeiroink_style).isdigit() else 0

        self.aivis_url = aivis_url.rstrip("/") if aivis_url else "http://localhost:10101"
        self.aivis_key = aivis_key
        self.aivis_speaker = int(aivis_speaker) if str(aivis_speaker).isdigit() else 1

        self.oss_tts_url = oss_tts_url.rstrip("/") if oss_tts_url else "http://localhost:9880"
        self.oss_tts_format = oss_tts_format or "openai"
        self.oss_voice = oss_voice

        self.ondoku_token = ondoku_token
        self.coefont_key = coefont_key
        self.coefont_secret = coefont_secret
        self.coefont_id = coefont_id

        # 常にフォールバック先として機能するEdge TTSエンジン
        self.edge_engine = EdgeTTSEngine(voice_name=self.voice_name, speaking_rate=self.speaking_rate)

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
            await self.synthesize_single_text(narration, output_path)
            audio_paths.append(output_path)

        logger.info(f"全{len(audio_paths)}シーンの音声合成完了 (エンジン: {self.engine})")
        return audio_paths

    async def synthesize_single_text(self, text: str, output_path: Path) -> Path:
        """単一のテキストを音声ファイルに合成する（自動フォールバック付き）"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.engine == "gtts":
                await self._synthesize_gtts(text, output_path)
            elif self.engine == "voicevox":
                await self._synthesize_voicevox(text, output_path)
            elif self.engine == "sharevox":
                await self._synthesize_sharevox(text, output_path)
            elif self.engine == "coeiroink":
                await self._synthesize_coeiroink(text, output_path)
            elif self.engine == "aivis":
                await self._synthesize_aivis(text, output_path)
            elif self.engine == "oss_custom":
                await self._synthesize_oss_custom(text, output_path)
            elif self.engine == "openai":
                await self._synthesize_openai(text, output_path)
            elif self.engine == "google":
                await self._synthesize_google(text, output_path)
            elif self.engine == "azure":
                await self._synthesize_azure(text, output_path)
            elif self.engine == "elevenlabs":
                await self._synthesize_elevenlabs(text, output_path)
            elif self.engine == "amazon_polly":
                await self._synthesize_polly(text, output_path)
            elif self.engine == "ondoku":
                await self._synthesize_ondoku(text, output_path)
            elif self.engine == "coefont":
                await self._synthesize_coefont(text, output_path)
            else:
                # デフォルト: Edge TTS (完全無料)
                await self.edge_engine.synthesize_scene(text, output_path)
        except Exception as e:
            logger.error(f"TTS合成エラー ({self.engine}): {e}")
            logger.warning("完全無料の Edge TTS へ自動フォールバックします...")
            try:
                await self.edge_engine.synthesize_scene(text, output_path)
            except Exception as fb_err:
                logger.error(f"Edge TTS フォールバック失敗: {fb_err}. gTTS へ緊急フォールバック...")
                await self._synthesize_gtts(text, output_path)

        return output_path

    # =========================================================================
    # 1. 完全無料エンジン (Edge, gTTS, VOICEVOX, SHAREVOX, COEIROINK, Aivis, OSS)
    # =========================================================================

    async def _synthesize_gtts(self, text: str, output_path: Path):
        """Google Translate TTS (完全無料・APIキー不要)"""
        encoded_text = urllib.parse.quote(text)
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=ja&q={encoded_text}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

    async def _synthesize_voicevox(self, text: str, output_path: Path):
        """VOICEVOX Engine (ローカルまたはリモートAPI)"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. audio_query
            query_res = await client.post(
                f"{self.voicevox_url}/audio_query",
                params={"text": text, "speaker": self.voicevox_speaker}
            )
            query_res.raise_for_status()
            query_json = query_res.json()
            query_json["speedScale"] = self.speaking_rate

            # 2. synthesis
            synth_res = await client.post(
                f"{self.voicevox_url}/synthesis",
                params={"speaker": self.voicevox_speaker},
                json=query_json
            )
            synth_res.raise_for_status()
            self._save_audio_convert_mp3(synth_res.content, output_path)

    async def _synthesize_sharevox(self, text: str, output_path: Path):
        """SHAREVOX Engine (VOICEVOX互換API)"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            query_res = await client.post(
                f"{self.sharevox_url}/audio_query",
                params={"text": text, "speaker": self.sharevox_speaker}
            )
            query_res.raise_for_status()
            query_json = query_res.json()
            query_json["speedScale"] = self.speaking_rate

            synth_res = await client.post(
                f"{self.sharevox_url}/synthesis",
                params={"speaker": self.sharevox_speaker},
                json=query_json
            )
            synth_res.raise_for_status()
            self._save_audio_convert_mp3(synth_res.content, output_path)

    async def _synthesize_coeiroink(self, text: str, output_path: Path):
        """COEIROINK Engine (ローカルAPI)"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # COEIROINK v1 互換API
            endpoint = f"{self.coeiroink_url}/audio_query"
            params = {"text": text, "speaker": self.coeiroink_style or 0}
            if self.coeiroink_speaker:
                params["speaker_uuid"] = self.coeiroink_speaker

            query_res = await client.post(endpoint, params=params)
            query_res.raise_for_status()
            query_json = query_res.json()
            query_json["speedScale"] = self.speaking_rate

            synth_res = await client.post(
                f"{self.coeiroink_url}/synthesis",
                params={"speaker": self.coeiroink_style or 0},
                json=query_json
            )
            synth_res.raise_for_status()
            self._save_audio_convert_mp3(synth_res.content, output_path)

    async def _synthesize_aivis(self, text: str, output_path: Path):
        """AivisSpeech (ローカルまたはAivis Cloud)"""
        headers = {}
        if self.aivis_key:
            headers["Authorization"] = f"Bearer {self.aivis_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            query_res = await client.post(
                f"{self.aivis_url}/audio_query",
                params={"text": text, "speaker": self.aivis_speaker},
                headers=headers
            )
            query_res.raise_for_status()
            query_json = query_res.json()
            query_json["speedScale"] = self.speaking_rate

            synth_res = await client.post(
                f"{self.aivis_url}/synthesis",
                params={"speaker": self.aivis_speaker},
                json=query_json,
                headers=headers
            )
            synth_res.raise_for_status()
            self._save_audio_convert_mp3(synth_res.content, output_path)

    async def _synthesize_oss_custom(self, text: str, output_path: Path):
        """
        次世代OSS音声モデル統合アダプター
        Fish Speech, GPT-SoVITS, ChatTTS, Bert-VITS2, StyleTTS2 等のローカルAPI/OpenAI互換TTS
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            if self.oss_tts_format == "openai":
                # OpenAI互換エンドポイント (Fish Speech, ChatTTS 等)
                url = f"{self.oss_tts_url}/v1/audio/speech"
                payload = {
                    "input": text,
                    "voice": self.oss_voice or "default",
                    "speed": self.speaking_rate
                }
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                self._save_audio_convert_mp3(resp.content, output_path)
            elif self.oss_tts_format == "gpt_sovits":
                # GPT-SoVITS 標準WebUI API
                url = f"{self.oss_tts_url}/tts"
                params = {
                    "text": text,
                    "text_lang": "ja",
                    "speed": self.speaking_rate
                }
                if self.oss_voice:
                    params["character"] = self.oss_voice
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                self._save_audio_convert_mp3(resp.content, output_path)
            else:
                # 汎用REST POST
                url = self.oss_tts_url
                payload = {"text": text, "voice": self.oss_voice, "speed": self.speaking_rate}
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                self._save_audio_convert_mp3(resp.content, output_path)

    # =========================================================================
    # 2. クラウド・有料・フリーミアムエンジン (OpenAI, Google, Azure, ElevenLabs, Polly, etc.)
    # =========================================================================

    async def _synthesize_openai(self, text: str, output_path: Path):
        """OpenAI TTS (tts-1 / tts-1-hd, alloy, echo, fable, onyx, nova, shimmer)"""
        if not self.openai_key:
            raise ValueError("OpenAI APIキーが設定されていません")

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.openai_model,
            "input": text,
            "voice": self.openai_voice,
            "speed": self.speaking_rate
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

    async def _synthesize_google(self, text: str, output_path: Path):
        """Google Cloud Text-to-Speech (REST API版: キー単体で動作)"""
        if not self.google_tts_key:
            raise ValueError("Google Cloud TTSのAPIキーが設定されていません")

        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.google_tts_key}"
        voice_target = self.voice_name if self.voice_name.startswith("ja-JP-") else "ja-JP-Neural2-B"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "ja-JP", "name": voice_target},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": self.speaking_rate
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            res_data = resp.json()
            audio_b64 = res_data.get("audioContent", "")
            if not audio_b64:
                raise ValueError("Google TTSからの音声データが空です")
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))

    async def _synthesize_azure(self, text: str, output_path: Path):
        """Microsoft Azure Cognitive Services Speech (月50万文字無料 / 有料)"""
        if not self.azure_key:
            raise ValueError("Azure Speech APIキーが設定されていません")

        url = f"https://{self.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": self.azure_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            "User-Agent": "KimidoriVideoAuto"
        }
        rate_pct = int((self.speaking_rate - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
        escaped_text = html.escape(text)
        ssml = f"""<speak version='1.0' xml:lang='ja-JP'>
  <voice xml:lang='ja-JP' xml:gender='Female' name='{self.azure_voice}'>
    <prosody rate='{rate_str}'>{escaped_text}</prosody>
  </voice>
</speak>"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, content=ssml.encode("utf-8"), headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

    async def _synthesize_elevenlabs(self, text: str, output_path: Path):
        """ElevenLabs (月10,000文字無料 / 有料で超高品質)"""
        if not self.elevenlabs_key:
            raise ValueError("ElevenLabs APIキーが設定されていません")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.elevenlabs_voice_id}"
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

    async def _synthesize_polly(self, text: str, output_path: Path):
        """Amazon Polly (AWS Polly API)"""
        # boto3がインストールされていれば優先使用
        try:
            import boto3
            session = boto3.Session(
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.aws_region
            )
            polly = session.client("polly")
            engine_type = "neural" if self.polly_voice in ["Kazuha", "Takumi", "Tomoko"] else "standard"
            response = polly.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=self.polly_voice,
                Engine=engine_type
            )
            with open(output_path, "wb") as f:
                f.write(response["AudioStream"].read())
        except ImportError:
            raise RuntimeError("Amazon Pollyの利用にはboto3ライブラリが必要です。")

    async def _synthesize_ondoku(self, text: str, output_path: Path):
        """音読さん (Ondoku API)"""
        if not self.ondoku_token:
            raise ValueError("音読さん APIトークンが設定されていません")

        url = "https://ondoku3.com/api/v1/speech"
        headers = {
            "Authorization": f"Bearer {self.ondoku_token}",
            "Content-Type": "application/json"
        }
        data = {
            "text": text,
            "voice": "ja-JP-Standard-A",
            "speed": self.speaking_rate
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            res_json = resp.json()
            audio_url = res_json.get("url")
            if not audio_url:
                raise ValueError("音読さんからの音声URL取得に失敗しました")
            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(audio_resp.content)

    async def _synthesize_coefont(self, text: str, output_path: Path):
        """CoeFont API"""
        if not self.coefont_key:
            raise ValueError("CoeFont APIキーが設定されていません")

        url = "https://api.coefont.cloud/v1/text2speech"
        headers = {
            "X-Coefont-Date": "",
            "X-Coefont-Content": "",
            "Authorization": self.coefont_key,
            "Content-Type": "application/json"
        }
        data = {
            "coefont": self.coefont_id,
            "text": text,
            "speed": self.speaking_rate
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

    # =========================================================================
    # ヘルパー: 音声保存とMP3変換
    # =========================================================================

    def _save_audio_convert_mp3(self, content: bytes, output_path: Path):
        """WAVまたは未判定音声を保存し、必要ならFFmpegでMP3に変換"""
        # 先頭バイトでWAV判定 (RIFF...)
        if content.startswith(b"RIFF"):
            wav_path = output_path.with_suffix(".wav")
            with open(wav_path, "wb") as f:
                f.write(content)
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(wav_path), "-acodec", "libmp3lame", str(output_path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if wav_path.exists():
                    wav_path.unlink()
            except Exception as e:
                logger.warning(f"FFmpeg MP3変換に失敗したためWAVのまま上書きします: {e}")
                import shutil
                shutil.move(str(wav_path), str(output_path))
        else:
            with open(output_path, "wb") as f:
                f.write(content)
