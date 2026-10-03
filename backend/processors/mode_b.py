"""
KIMIDORI Movie Auto - モードB プロセッサー
素材動画 → Whisper音声認識 → FFmpeg無音ジェットカット → 字幕タイムスタンプ同期
→ Gemini文脈・感情解析 → Pexels Bロール素材自動取得・ディゾルブ合成 → 自動テロップ焼付
6missedcalls/video-editing-skill & benpiper/auto-video-editor & addyosmani/pexels-ai-video-downloader 準拠
"""

import os
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import config
from processors.subtitle_burner import SubtitleBurner
from processors.pexels_client import PexelsClient
from processors.context_analyzer import ContextAnalyzer
from utils.whisper_utils import (
    extract_audio_from_video, transcribe, detect_silence_regions, get_audio_duration,
)
from utils.ffmpeg_utils import cut_and_concat_segments, get_video_info

logger = logging.getLogger(__name__)


class ModeBProcessor:
    """モードB: 既存動画のジェットカット＋文脈連動Pexels Bロール＋自動テロップ付与"""

    def __init__(
        self,
        firestore_service,
        storage_service,
        pexels_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None
    ):
        self.firestore = firestore_service
        self.storage = storage_service
        self.subtitle_burner = SubtitleBurner()
        self.pexels_client = PexelsClient(api_key=pexels_api_key or os.getenv("PEXELS_API_KEY", ""))
        self.context_analyzer = ContextAnalyzer()

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

        # Whisperで音声認識（日本語、単語タイムスタンプ対応）
        result = transcribe(audio_path, language="ja", word_timestamps=True)

        logger.info(
            f"音声認識完了: {len(result.get('segments', []))}セグメント, "
            f"テキスト長: {len(result.get('text', ''))}文字"
        )
        return result

    async def jet_cut(
        self, video_path: Path, transcription: dict, job_id: str
    ) -> Tuple[Path, dict, Dict[str, Any]]:
        """
        無音区間を検出してジェットカットを実行し、字幕タイムスタンプをカット後タイムラインに再同期する

        Returns:
            (cut_video_path, synced_transcription, stats_dict)
        """
        job_dir = self._get_job_dir(job_id)
        audio_path = job_dir / "extracted_audio.wav"

        if not audio_path.exists():
            extract_audio_from_video(video_path, audio_path)

        # 無音区間を検出 (silencedetect)
        silence_regions = detect_silence_regions(audio_path)
        logger.info(f"無音区間: {len(silence_regions)}箇所検出")

        video_info = get_video_info(video_path)
        total_duration = video_info["duration"]

        if not silence_regions:
            logger.info("無音区間が検出されなかったためカットをスキップします")
            return video_path, transcription, {
                "cut_count": 0,
                "original_duration": total_duration,
                "cut_duration": total_duration,
                "saved_seconds": 0.0
            }

        # 有音セグメントを構築
        keep_segments = self._build_keep_segments(silence_regions, total_duration)

        if not keep_segments:
            return video_path, transcription, {
                "cut_count": 0,
                "original_duration": total_duration,
                "cut_duration": total_duration,
                "saved_seconds": 0.0
            }

        total_keep = sum(s["end"] - s["start"] for s in keep_segments)
        cut_ratio = (1 - total_keep / total_duration) * 100
        saved_seconds = max(0.0, total_duration - total_keep)

        logger.info(
            f"ジェットカット: {total_duration:.1f}秒 → {total_keep:.1f}秒 "
            f"({cut_ratio:.1f}%カット、{saved_seconds:.1f}秒短縮)"
        )

        output_path = job_dir / "jet_cut_output.mp4"
        cut_and_concat_segments(video_path, keep_segments, output_path)

        # 字幕タイムスタンプをカット後時間に再同期
        synced_transcription = self._sync_transcription_to_cuts(transcription, keep_segments)

        stats = {
            "cut_count": len(silence_regions),
            "original_duration": total_duration,
            "cut_duration": total_keep,
            "saved_seconds": saved_seconds
        }

        return output_path, synced_transcription, stats

    def _sync_transcription_to_cuts(self, transcription: dict, keep_segments: list[dict]) -> dict:
        """
        ジェットカット後のタイムラインに合わせてWhisper字幕セグメントの開始・終了時間を再計算する
        """
        old_segments = transcription.get("segments", [])
        new_segments = []

        def map_time(t: float) -> Optional[float]:
            accumulated_time = 0.0
            for seg in keep_segments:
                s, e = seg["start"], seg["end"]
                dur = e - s
                if t < s:
                    # カットされた無音区間内: 直前のセグメント末尾にスナップ
                    return accumulated_time
                elif s <= t <= e:
                    return accumulated_time + (t - s)
                accumulated_time += dur
            return accumulated_time

        for seg in old_segments:
            s_old = seg.get("start", 0.0)
            e_old = seg.get("end", 0.0)
            s_new = map_time(s_old)
            e_new = map_time(e_old)

            if s_new is not None and e_new is not None and (e_new - s_new) > 0.2:
                new_seg = dict(seg)
                new_seg["start"] = round(s_new, 2)
                new_seg["end"] = round(e_new, 2)
                new_segments.append(new_seg)

        synced = dict(transcription)
        synced["segments"] = new_segments
        return synced

    async def insert_broll_materials(
        self,
        video_path: Path,
        transcription: dict,
        job_id: str,
        enable_broll: bool = True
    ) -> Tuple[Path, List[Dict[str, Any]]]:
        """
        WhisperテキストからGeminiで感情・文脈キーワードを解析し、Pexels Bロール素材をディゾルブ合成する

        Returns:
            (composite_video_path, broll_insertion_logs)
        """
        if not enable_broll:
            return video_path, []

        job_dir = self._get_job_dir(job_id)
        video_info = get_video_info(video_path)
        video_duration = video_info.get("duration", 60.0)
        width = video_info.get("width", 1920)
        height = video_info.get("height", 1080)
        orientation = "portrait" if height > width else "landscape"

        # 1. 文脈・感情転換点およびPexelsキーワードの解析
        segments = transcription.get("segments", [])
        targets = await self.context_analyzer.detect_broll_insertion_points(
            transcript_segments=segments,
            video_duration=video_duration,
            max_inserts=4
        )

        if not targets:
            logger.info("Bロール素材の挿入対象が見つからなかったためスキップします")
            return video_path, []

        # 2. Pexels素材の検索とダウンロード
        downloaded_brolls = []
        broll_dir = job_dir / "brolls"
        broll_dir.mkdir(parents=True, exist_ok=True)

        for target in targets:
            query = target.get("pexels_query", "")
            dur = target.get("duration", 4.0)
            broll_item = await self.pexels_client.search_and_download_broll(
                query=query,
                orientation=orientation,
                preferred_type="video",
                min_duration=dur,
                output_dir=broll_dir
            )
            if broll_item and broll_item.get("file_path"):
                target["material"] = broll_item
                downloaded_brolls.append(target)

        if not downloaded_brolls:
            logger.info("Pexels素材が取得できなかったためスキップします")
            return video_path, []

        # 3. FFmpeg によるディゾルブ（クロスフェード）オーバーレイ合成
        current_video = video_path
        applied_logs = []

        for idx, item in enumerate(downloaded_brolls):
            mat = item["material"]
            mat_path = mat["file_path"]
            mat_type = mat["type"]
            start_t = item["start"]
            dur = item["duration"]

            step_output = job_dir / f"broll_step_{idx:02d}.mp4"
            fade_dur = 0.5

            # FFmpegコマンド構築
            # Bロール素材を動画の幅・高さにリサイズし、黒帯なしでクロップ
            # 開始時0.5秒フェードイン、終了時0.5秒フェードアウト
            scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
            fade_filter = f"format=yuva420p,fade=t=in:st=0:d={fade_dur}:alpha=1,fade=t=out:st={dur - fade_dur}:d={fade_dur}:alpha=1"

            filter_complex = (
                f"[1:v]{scale_filter},{fade_filter}[broll];"
                f"[0:v][broll]overlay=enable='between(t,{start_t},{start_t + dur})'[outv]"
            )

            if mat_type == "video":
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(current_video),
                    "-ss", "0", "-t", str(dur), "-i", str(mat_path),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "copy",
                    str(step_output)
                ]
            else:
                # 静止画
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(current_video),
                    "-loop", "1", "-t", str(dur), "-i", str(mat_path),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "copy",
                    str(step_output)
                ]

            try:
                subprocess.run(cmd, check=True, timeout=180)
                current_video = step_output
                applied_logs.append({
                    "time": f"{start_t:.1f}s - {start_t + dur:.1f}s",
                    "emotion": item.get("emotion", "mood"),
                    "query": item.get("pexels_query", ""),
                    "reason": item.get("reason", "")
                })
                logger.info(f"Bロール素材合成完了 ({start_t:.1f}s): {item.get('pexels_query')}")
            except Exception as e:
                logger.warning(f"Bロール素材合成失敗 ({start_t:.1f}s): {e}")

        return current_video, applied_logs

    async def burn_subtitles(
        self, video_path: Path, transcription: dict, job_id: str
    ) -> Path:
        """
        Whisperの認識結果を使って動画にテロップを焼き付ける
        """
        job_dir = self._get_job_dir(job_id)
        segments = transcription.get("segments", [])

        if not segments:
            logger.warning("テロップ用のセグメントがありません")
            return video_path

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
        """
        padding = config.SILENCE_PADDING
        keep_segments = []
        prev_end = 0.0

        for silence in sorted(silence_regions, key=lambda x: x["start"]):
            seg_start = prev_end
            seg_end = silence["start"] + padding

            if seg_end > seg_start + 0.1:
                keep_segments.append({
                    "start": max(0, seg_start),
                    "end": min(seg_end, total_duration),
                })

            prev_end = silence["end"] - padding

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
