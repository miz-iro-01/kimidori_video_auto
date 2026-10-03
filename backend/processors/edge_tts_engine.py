"""
Edge TTS 音声合成モジュール（完全無料・APIキー不要）
Microsoft Edge の Neural TTS を使用してナレーション音声を生成
"""

import asyncio
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

# 利用可能な日本語音声一覧
JAPANESE_VOICES = {
    "nanami": {"id": "ja-JP-NanamiNeural", "label": "七海（女性・標準）", "gender": "female", "pitch": "+0Hz", "rate_offset": 0},
    "keita": {"id": "ja-JP-KeitaNeural", "label": "慶太（男性・標準）", "gender": "male", "pitch": "+0Hz", "rate_offset": 0},
    "aoi": {"id": "ja-JP-NanamiNeural", "label": "あおい（女性・明るい高め）", "gender": "female", "pitch": "+9Hz", "rate_offset": 4},
    "daichi": {"id": "ja-JP-KeitaNeural", "label": "大地（男性・落ち着き低音）", "gender": "male", "pitch": "-9Hz", "rate_offset": -4},
    "mayu": {"id": "ja-JP-NanamiNeural", "label": "まゆ（女性・アニメ調・元気）", "gender": "female", "pitch": "+15Hz", "rate_offset": 7},
    "naoki": {"id": "ja-JP-KeitaNeural", "label": "直樹（男性・若々しい青年）", "gender": "male", "pitch": "+8Hz", "rate_offset": 4},
    "shiori": {"id": "ja-JP-NanamiNeural", "label": "しおり（女性・落ち着きお姉さん）", "gender": "female", "pitch": "-5Hz", "rate_offset": -4},
}

DEFAULT_VOICE = "nanami"


class EdgeTTSEngine:
    """
    Edge TTS を使用した完全無料の音声合成エンジン

    特徴:
    - APIキー不要
    - 課金なし（Microsoft Edge と同じ音声エンジン）
    - 高品質な Neural 音声
    - 日本語対応（ピッチ・速度モジュレーションによる7キャラボイス）
    """

    def __init__(self, voice_name: str = DEFAULT_VOICE, speaking_rate: float = 1.0):
        """
        Args:
            voice_name: 音声の名前キー（JAPANESE_VOICES のキー）
            speaking_rate: 読み上げ速度（0.5〜2.0）
        """
        voice_info = JAPANESE_VOICES.get(voice_name, JAPANESE_VOICES[DEFAULT_VOICE])
        self.voice_id = voice_info["id"]
        self.pitch = voice_info.get("pitch", "+0Hz")
        rate_offset = voice_info.get("rate_offset", 0)
        self.rate = self._format_rate(speaking_rate, rate_offset)

    @staticmethod
    def _format_rate(rate: float, offset_percent: int = 0) -> str:
        """速度をEdge TTSの形式に変換（例: +20%, -10%）"""
        percent = int((rate - 1.0) * 100) + offset_percent
        if percent >= 0:
            return f"+{percent}%"
        return f"{percent}%"

    async def synthesize_scene(self, text: str, output_path: Path) -> Path:
        """
        テキストを音声に合成する

        Args:
            text: 読み上げるテキスト
            output_path: 出力ファイルパス（.mp3）

        Returns:
            Path: 生成された音声ファイルのパス
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice_id,
            rate=self.rate,
            pitch=self.pitch,
        )

        await communicate.save(str(output_path))
        logger.info(f"Edge TTS 音声生成完了: {output_path.name} (voice={self.voice_id}, pitch={self.pitch})")
        return output_path


    async def synthesize_all_scenes(
        self, scenes: list[dict], job_dir: Path
    ) -> list[Path]:
        """全シーンのナレーションを音声合成"""
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

        logger.info(f"全{len(audio_paths)}シーンの音声合成完了（Edge TTS）")
        return audio_paths

    @staticmethod
    def get_available_voices() -> list[dict]:
        """利用可能な日本語音声の一覧を返す"""
        return [
            {"key": k, **v} for k, v in JAPANESE_VOICES.items()
        ]
