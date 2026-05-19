"""
モードB プロセッサー — 既存動画の自動編集
素材動画 → Whisper音声認識 → 無音カット（ジェットカット）→ テロップ焼付
"""
import logging
import shutil
from pathlib import Path

import config
from processors.subtitle_burner import SubtitleBurner
from utils.whisper_utils import (
    extract_audio_from_video, transcribe, detect_silence_regions, get_audio_duration,
)
from utils.ffmpeg_utils import cut_and_concat_segments, get_video_info

logger = logging.getLogger(__name__)


class ModeBProcessor:
    """モードB: 既存動画のジェットカット＋自動テロップ付与"""

    def __init__(self, firestore_service, storage_service):
        self.firestore = firestore_service
        self.storage = storage_service
        self.subtitle_burner = SubtitleBurner()

    def _get_job_dir(self, job_id: str) -> Path:
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    async def transcribe_audio(self, video_path: Path, job_id: str) -> dict:
        """
        動画から音声を抽出し、Whisperで音声認識を実行

        Returns:
            dict: Whisperの認識結果（segments含む）
        """
        job_dir = self._get_job_dir(job_id)
        audio_path = job_dir / "extracted_audio.wav"

        # 音声抽出
        extract_audio_from_video(video_path, audio_path)

        # Whisperで音声認識
        result = transcribe(audio_path, language="ja", word_timestamps=True)

        logger.info(
            f"音声認識完了: {len(result.get('segments', []))}セグメント, "
            f"テキスト長: {len(result.get('text', ''))}文字"
        )
        return result

    async def jet_cut(
        self, video_path: Path, transcription: dict, job_id: str
    ) -> Path:
        """
        無音区間を検出してジェットカットを実行する

        処理の流れ:
        1. FFmpeg silencedetect で無音区間を検出
        2. 無音区間を除外した「有音セグメント」リストを構築
        3. FFmpeg の trim + concat フィルターでカット結合

        Args:
            video_path: 入力動画のパス
            transcription: Whisperの認識結果
            job_id: ジョブID

        Returns:
            Path: ジェットカット済み動画のパス
        """
        job_dir = self._get_job_dir(job_id)
        audio_path = job_dir / "extracted_audio.wav"

        # 音声ファイルが存在しない場合は抽出
        if not audio_path.exists():
            extract_audio_from_video(video_path, audio_path)

        # 無音区間を検出
        silence_regions = detect_silence_regions(audio_path)
        logger.info(f"無音区間: {len(silence_regions)}箇所検出")

        if not silence_regions:
            logger.info("無音区間が見つからないため、カットは実行しません")
            return video_path

        # 動画の総時間を取得
        video_info = get_video_info(video_path)
        total_duration = video_info["duration"]

        # 無音区間を除外した有音セグメントを構築
        keep_segments = self._build_keep_segments(
            silence_regions, total_duration
        )

        if not keep_segments:
            logger.warning("有音セグメントがありません")
            return video_path

        # カット前後の時間を計算
        total_keep = sum(s["end"] - s["start"] for s in keep_segments)
        cut_ratio = (1 - total_keep / total_duration) * 100
        logger.info(
            f"ジェットカット: {total_duration:.1f}秒 → {total_keep:.1f}秒 "
            f"({cut_ratio:.1f}%カット)"
        )

        # ジェットカット実行
        output_path = job_dir / "jet_cut_output.mp4"
        cut_and_concat_segments(video_path, keep_segments, output_path)

        return output_path

    async def burn_subtitles(
        self, video_path: Path, transcription: dict, job_id: str
    ) -> Path:
        """
        Whisperの認識結果を使って動画にテロップを焼き付ける

        Args:
            video_path: 入力動画のパス
            transcription: Whisperの認識結果
            job_id: ジョブID

        Returns:
            Path: テロップ付き動画のパス
        """
        job_dir = self._get_job_dir(job_id)
        segments = transcription.get("segments", [])

        if not segments:
            logger.warning("テロップ用のセグメントがありません")
            return video_path

        # 動画情報を取得
        video_info = get_video_info(video_path)

        # ASS字幕ファイルを生成
        subtitle_path = job_dir / "subtitles.ass"
        self.subtitle_burner.create_ass_subtitle(
            segments=segments,
            output_path=subtitle_path,
            video_width=video_info["width"],
            video_height=video_info["height"],
        )

        # テロップを焼き付け
        output_path = job_dir / "subtitled_output.mp4"
        self.subtitle_burner.burn_subtitles_to_video(
            video_path=video_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
        )

        return output_path

    def _build_keep_segments(
        self, silence_regions: list[dict], total_duration: float
    ) -> list[dict]:
        """
        無音区間リストから「残すべきセグメント」リストを構築

        無音区間の間の有音区間を抽出し、前後にパディングを追加する
        """
        padding = config.SILENCE_PADDING
        keep_segments = []

        # 先頭から最初の無音区間まで
        prev_end = 0.0

        for silence in sorted(silence_regions, key=lambda x: x["start"]):
            seg_start = prev_end
            seg_end = silence["start"] + padding  # 無音の少し手前まで残す

            if seg_end > seg_start + 0.1:  # 極短セグメントは除外
                keep_segments.append({
                    "start": max(0, seg_start),
                    "end": min(seg_end, total_duration),
                })

            prev_end = silence["end"] - padding  # 無音の少し後から再開

        # 最後の無音区間から末尾まで
        if prev_end < total_duration - 0.1:
            keep_segments.append({
                "start": max(0, prev_end),
                "end": total_duration,
            })

        return keep_segments

    def cleanup(self, job_id: str):
        """ジョブの一時ファイルを削除"""
        job_dir = config.TMP_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
            logger.info(f"一時ファイル削除: {job_dir}")
