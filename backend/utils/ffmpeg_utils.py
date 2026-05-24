"""
FFmpeg ユーティリティ — 動画のカット・結合・合成
"""
import logging
import subprocess
import json
from pathlib import Path
from typing import Optional
import config

logger = logging.getLogger(__name__)


def get_video_info(video_path: Path) -> dict:
    """動画ファイルのメタ情報を取得"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"動画情報取得に失敗: {result.stderr}")
    data = json.loads(result.stdout)
    vs = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not vs:
        raise ValueError("動画ストリームが見つかりません")
    fps_parts = vs.get("r_frame_rate", "30/1").split("/")
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
    return {
        "width": int(vs.get("width", 1920)), "height": int(vs.get("height", 1080)),
        "duration": float(data.get("format", {}).get("duration", 0)),
        "fps": fps, "codec": vs.get("codec_name", "unknown"),
    }


def cut_and_concat_segments(video_path: Path, segments: list[dict], output_path: Path) -> Path:
    """動画を指定セグメントでカットし結合（ジェットカット）"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not segments:
        raise ValueError("カットするセグメントが空です")

    filter_parts = []
    concat_inputs = []
    for i, seg in enumerate(segments):
        filter_parts.append(f"[0:v]trim=start={seg['start']}:end={seg['end']},setpts=PTS-STARTPTS[v{i}];")
        filter_parts.append(f"[0:a]atrim=start={seg['start']}:end={seg['end']},asetpts=PTS-STARTPTS[a{i}];")
        concat_inputs.append(f"[v{i}][a{i}]")

    filter_complex = "".join(filter_parts) + f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[outv][outa]"

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(output_path),
    ]
    logger.info(f"ジェットカット実行: {len(segments)}セグメント")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"ジェットカットに失敗: {result.stderr[-200:]}")
    return output_path


def concat_video_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """複数の動画クリップを結合"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{str(p).replace(chr(92), '/')}'\n")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"クリップ結合に失敗: {result.stderr[-200:]}")
    concat_file.unlink(missing_ok=True)
    return output_path


def create_scene_clip(
    background_image: Path, audio_path: Path, text_overlay: str,
    output_path: Path, width: int = 1080, height: int = 1920,
    duration: Optional[float] = None,
) -> Path:
    """背景画像+音声+テロップから1シーンクリップを生成（モードA用）"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_escaped = config.SUBTITLE_FONT.replace(":", "\\:")
    text_escaped = text_overlay.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")

    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p[bg];"
        f"[bg]drawtext=fontfile='{font_escaped}':text='{text_escaped}'"
        f":fontcolor=white:fontsize=64:borderw=3:bordercolor=black"
        f":x=(w-text_w)/2:y=h*0.78[out]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(background_image),
        "-i", str(audio_path), "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    if duration:
        cmd.insert(-1, "-t")
        cmd.insert(-1, str(duration))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"シーンクリップ生成失敗: {result.stderr[-200:]}")
    return output_path
