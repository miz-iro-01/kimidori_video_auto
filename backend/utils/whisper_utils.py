"""
Whisper ユーティリティ
OpenAI Whisper（オープンソース版）を使用した音声認識
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import whisper
import numpy as np

import config

logger = logging.getLogger(__name__)

# グローバルでモデルをキャッシュ（起動時に1回だけロード）
_whisper_model = None


def get_whisper_model():
    """Whisperモデルのシングルトンを取得"""
    global _whisper_model
    if _whisper_model is None:
        logger.info(f"Whisperモデル '{config.WHISPER_MODEL}' をロード中...")
        _whisper_model = whisper.load_model(config.WHISPER_MODEL)
        logger.info("Whisperモデルのロード完了")
    return _whisper_model


def extract_audio_from_video(video_path: Path, output_path: Path) -> Path:
    """
    動画ファイルから音声トラックを抽出する

    Args:
        video_path: 入力動画ファイルのパス
        output_path: 出力音声ファイルのパス（.wav）

    Returns:
        Path: 抽出された音声ファイルのパス
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                  # 映像なし
        "-acodec", "pcm_s16le", # WAV形式
        "-ar", "16000",         # 16kHz（Whisper推奨）
        "-ac", "1",             # モノラル
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"音声抽出に失敗: {result.stderr[-200:]}")

    logger.info(f"音声抽出完了: {output_path.name}")
    return output_path


def transcribe(
    audio_path: Path,
    language: str = "ja",
    word_timestamps: bool = True,
) -> dict:
    """
    Whisperで音声認識を実行する

    Args:
        audio_path: 音声ファイルのパス
        language: 言語コード
        word_timestamps: 単語レベルのタイムスタンプを取得するか

    Returns:
        dict: Whisperの認識結果
        {
            "text": "全文テキスト",
            "segments": [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "text": "セグメントテキスト",
                    "words": [
                        {"start": 0.0, "end": 0.5, "word": "単語"}
                    ]
                },
                ...
            ]
        }
    """
    model = get_whisper_model()

    logger.info(f"音声認識開始: {audio_path.name} (言語: {language})")

    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=word_timestamps,
        verbose=False,
    )

    segment_count = len(result.get("segments", []))
    logger.info(f"音声認識完了: {segment_count}セグメント検出")

    return result


def detect_silence_regions(
    audio_path: Path,
    threshold_db: float = None,
    min_duration: float = None,
) -> list[dict]:
    """
    FFmpegのsilencedetectフィルターを使用して無音区間を検出する

    Args:
        audio_path: 音声ファイルのパス
        threshold_db: 無音判定の閾値（dB）。デフォルトは config から取得
        min_duration: 無音と判定する最小持続時間（秒）。デフォルトは config から取得

    Returns:
        list[dict]: 無音区間のリスト
        [
            {"start": 0.0, "end": 1.5, "duration": 1.5},
            ...
        ]
    """
    if threshold_db is None:
        threshold_db = config.SILENCE_THRESHOLD_DB
    if min_duration is None:
        min_duration = config.SILENCE_MIN_DURATION

    cmd = [
        "ffmpeg",
        "-i", str(audio_path),
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
        "-f", "null",
        "-",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # FFmpegの出力からsilencedetectの結果をパース
    silence_regions = []
    current_start = None

    for line in result.stderr.split("\n"):
        if "silence_start:" in line:
            try:
                current_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                continue
        elif "silence_end:" in line and current_start is not None:
            try:
                parts = line.split("silence_end:")[1].strip().split()
                end = float(parts[0])
                silence_regions.append({
                    "start": current_start,
                    "end": end,
                    "duration": end - current_start,
                })
                current_start = None
            except (IndexError, ValueError):
                continue

    logger.info(f"無音区間検出完了: {len(silence_regions)}箇所")
    return silence_regions


def get_audio_duration(audio_path: Path) -> float:
    """音声ファイルの長さ（秒）を取得する"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise RuntimeError(f"音声長さの取得に失敗: {result.stderr}")

    import json
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
