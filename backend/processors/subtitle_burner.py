"""
テロップ焼き付けモジュール
FFmpegを使って動画にテロップ（字幕）を焼き付ける
"""

import logging
import subprocess
import json
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class SubtitleBurner:
    """FFmpegを使用して動画にテロップを焼き付けるクラス"""

    def __init__(self):
        self.font = config.SUBTITLE_FONT
        self.font_size = config.SUBTITLE_FONT_SIZE
        self.color = config.SUBTITLE_COLOR
        self.outline_color = config.SUBTITLE_OUTLINE_COLOR
        self.outline_width = config.SUBTITLE_OUTLINE_WIDTH

    def create_ass_subtitle(
        self,
        segments: list[dict],
        output_path: Path,
        video_width: int = 1920,
        video_height: int = 1080,
    ) -> Path:
        """
        Whisperのセグメントデータから ASS字幕ファイルを生成する

        Args:
            segments: Whisperの認識セグメント [{start, end, text}, ...]
            output_path: 出力する.assファイルのパス
            video_width: 動画の幅
            video_height: 動画の高さ

        Returns:
            Path: 生成された.assファイルのパス
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ASS字幕のスタイル定義
        # MarginV で下からの位置を調整
        margin_v = int(video_height * (1.0 - config.SUBTITLE_POSITION_Y))

        ass_content = f"""[Script Info]
Title: KIMIDORI Movie Auto - 自動テロップ
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans CJK JP,{self.font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{self.outline_width},1,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        for seg in segments:
            start_time = self._seconds_to_ass_time(seg["start"])
            end_time = self._seconds_to_ass_time(seg["end"])
            text = seg["text"].strip().replace("\n", "\\N")

            ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        logger.info(f"ASS字幕ファイル生成完了: {output_path.name} ({len(segments)}セグメント)")
        return output_path

    def burn_subtitles_to_video(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
    ) -> Path:
        """
        動画にASS字幕を焼き付ける

        Args:
            video_path: 入力動画のパス
            subtitle_path: ASS字幕ファイルのパス
            output_path: 出力動画のパス

        Returns:
            Path: テロップ付き動画のパス
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ASS字幕のパスをFFmpegのフィルターで使う形式に変換
        # Windowsパスの場合はエスケープが必要
        sub_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass='{sub_path_escaped}'",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info(f"テロップ焼き付け開始: {video_path.name} → {output_path.name}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode != 0:
            logger.error(f"FFmpegエラー: {result.stderr[-500:]}")
            raise RuntimeError(f"テロップの焼き付けに失敗しました: {result.stderr[-200:]}")

        logger.info(f"テロップ焼き付け完了: {output_path.name}")
        return output_path

    def create_text_overlay_clip(
        self,
        text: str,
        duration: float,
        output_path: Path,
        width: int = 1080,
        height: int = 1920,
        bg_color: str = "black",
    ) -> Path:
        """
        テキストオーバーレイ付きの画像クリップを生成する（モードA用）

        Args:
            text: 表示するテキスト
            duration: クリップの長さ（秒）
            output_path: 出力パス
            width: 動画の幅
            height: 動画の高さ
            bg_color: 背景色

        Returns:
            Path: 生成された動画クリップのパス
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # drawtext フィルターでテキストを中央に配置
        # 日本語フォントを使用
        font_escaped = self.font.replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={width}x{height}:d={duration}:r=30",
            "-vf", (
                f"drawtext=fontfile='{font_escaped}'"
                f":text='{self._escape_ffmpeg_text(text)}'"
                f":fontcolor={self.color}"
                f":fontsize={self.font_size * 2}"
                f":borderw={self.outline_width}"
                f":bordercolor={self.outline_color}"
                f":x=(w-text_w)/2"
                f":y=(h-text_h)/2"
            ),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.error(f"テキストクリップ生成エラー: {result.stderr[-300:]}")
            raise RuntimeError(f"テキストクリップの生成に失敗: {result.stderr[-200:]}")

        return output_path

    @staticmethod
    def _seconds_to_ass_time(seconds: float) -> str:
        """秒数をASS形式の時間文字列に変換 (H:MM:SS.cc)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @staticmethod
    def _escape_ffmpeg_text(text: str) -> str:
        """FFmpegのdrawtextフィルター用にテキストをエスケープ"""
        return (
            text.replace("\\", "\\\\")
            .replace("'", "'\\''")
            .replace(":", "\\:")
            .replace("%", "%%")
        )
