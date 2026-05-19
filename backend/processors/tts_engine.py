"""
Google Cloud Text-to-Speech 音声合成モジュール
台本のナレーションテキストから音声ファイルを生成する
"""

import logging
from pathlib import Path

from google.cloud import texttospeech
import config

logger = logging.getLogger(__name__)


class TTSEngine:
    """Google Cloud Text-to-Speech を使用した音声合成エンジン"""

    def __init__(self):
        self.client = texttospeech.TextToSpeechClient()
        self.voice = texttospeech.VoiceSelectionParams(
            language_code=config.TTS_LANGUAGE_CODE,
            name=config.TTS_VOICE_NAME,
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=config.TTS_SPEAKING_RATE,
            pitch=0.0,
        )

    async def synthesize_scene(self, text: str, output_path: Path) -> Path:
        """
        単一シーンのナレーションを音声合成する

        Args:
            text: 読み上げるテキスト
            output_path: 出力ファイルパス

        Returns:
            Path: 生成された音声ファイルのパス
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        synthesis_input = texttospeech.SynthesisInput(text=text)

        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=self.voice,
            audio_config=self.audio_config,
        )

        with open(output_path, "wb") as f:
            f.write(response.audio_content)

        logger.info(f"音声合成完了: {output_path.name} ({len(response.audio_content)} bytes)")
        return output_path

    async def synthesize_all_scenes(
        self, scenes: list[dict], job_dir: Path
    ) -> list[Path]:
        """
        全シーンのナレーションを音声合成する

        Args:
            scenes: 台本のシーンリスト
            job_dir: ジョブの作業ディレクトリ

        Returns:
            list[Path]: 生成された音声ファイルのパスリスト
        """
        audio_dir = job_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        audio_paths = []
        for i, scene in enumerate(scenes):
            narration = scene.get("narration", "")
            if not narration:
                continue

            output_path = audio_dir / f"scene_{i:03d}.mp3"
            await self.synthesize_scene(narration, output_path)
            audio_paths.append(output_path)

        logger.info(f"全{len(audio_paths)}シーンの音声合成完了")
        return audio_paths
