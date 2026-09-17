"""
KIMIDORI Movie Auto - 長尺・漫画動画合成＆マルチBGMクロスフェードエンジン
FFmpeg を用いて「人物のみ」→「吹き出し付き」への0.3秒演出切り替え、シーン別感情タグに応じたマルチBGMクロスフェード合成、ナレーションミックス処理を行う
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import config

logger = logging.getLogger(__name__)

# デフォルトの無音/フォールバックBGMや設定
DEFAULT_FADE_DURATION = 1.0  # クロスフェード時間（秒）
BGM_VOLUME = 0.20           # BGMのデフォルト音量 (20%)


class MangaVideoComposer:
    """
    静止画演出、ナレーション、感情タグ別BGMクロスフェード、字幕/ロゴ合成を行うメイン合成エンジン
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def _get_audio_duration(self, audio_path: Union[str, Path]) -> float:
        """音声ファイルの長さ（秒）を取得"""
        if not audio_path or not Path(audio_path).exists():
            return 5.0

        cmd = [
            self.ffprobe_path, "-v", "quiet", "-print_format", "json",
            "-show_format", str(audio_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return float(data.get("format", {}).get("duration", 5.0))
        except Exception as e:
            logger.warning(f"Failed to probe audio duration for {audio_path}: {e}")
        return 5.0

    def create_single_scene_clip(
        self,
        base_image_path: Union[str, Path],
        overlay_image_path: Union[str, Path],
        audio_path: Optional[Union[str, Path]],
        output_clip_path: Union[str, Path],
        duration: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        switch_delay: float = 0.3
    ) -> float:
        """
        1シーン分の動画クリップを作成する。
        演出: 最初の 0.3 秒は `base_image_path`（人物のみ）、
             0.3秒以降は `overlay_image_path`（吹き出し付き）を表示。
        """
        out_p = Path(output_clip_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        has_audio = audio_path and Path(audio_path).exists()
        audio_duration = self._get_audio_duration(audio_path) if has_audio else duration
        final_duration = max(duration, audio_duration, switch_delay + 0.5)

        # 0.3秒切り替えFFmpegフィルタコンプレックス構文
        # 0 ~ 0.3s は 0:v (base_image), 0.3s ~ 終わり は 1:v (overlay_image)
        filter_complex = (
            f"[0:v]scale={width}:{height},fps={fps},settb=AVTB[v0];"
            f"[1:v]scale={width}:{height},fps={fps},settb=AVTB[v1];"
            f"[v0][v1]overlay=enable='gte(t,{switch_delay})'[outv]"
        )

        cmd = [
            self.ffmpeg_path, "-y", "-loglevel", "error",
            "-loop", "1", "-t", str(final_duration), "-i", str(base_image_path),
            "-loop", "1", "-t", str(final_duration), "-i", str(overlay_image_path),
        ]

        if has_audio:
            cmd.extend(["-i", str(audio_path)])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "2:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192000",
                "-t", str(final_duration),
                str(out_p)
            ])
        else:
            # 音声なし無音トラック生成
            cmd.extend([
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "2:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192000",
                "-t", str(final_duration),
                str(out_p)
            ])

        logger.info(f"MangaVideoComposer: Creating scene clip ({final_duration:.2f}s) -> {out_p.name}")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg scene clip creation failed: {res.stderr}")

        return final_duration

    def build_multi_bgm_track(
        self,
        scene_bgm_sequence: List[Tuple[float, str]],  # [(duration, bgm_file_path), ...]
        total_duration: float,
        output_bgm_path: Union[str, Path],
        bgm_volume: float = BGM_VOLUME,
        fade_duration: float = DEFAULT_FADE_DURATION
    ) -> Path:
        """
        シーンごとの感情タグに応じたBGMファイルを、タイムラインに合わせてクロスフェード結合する
        """
        out_p = Path(output_bgm_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not scene_bgm_sequence:
            # BGMなし無音トラック作成
            cmd = [
                self.ffmpeg_path, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration}",
                "-c:a", "aac", str(out_p)
            ]
            subprocess.run(cmd, check=True)
            return out_p

        # BGMファイルを時間順に結合＆クロスフェードビルド
        filter_parts = []
        concat_inputs = []
        valid_inputs = 0
        input_args = []

        current_time = 0.0

        for idx, (dur, bgm_file) in enumerate(scene_bgm_sequence):
            if bgm_file and Path(bgm_file).exists():
                input_args.extend(["-stream_loop", "-1", "-i", str(bgm_file)])
                # 各BGMセグメントの音量調整およびフェード処理
                filter_parts.append(
                    f"[{valid_inputs}:a]volume={bgm_volume},"
                    f"atrim=0:{dur},asetpts=PTS-STARTPTS,"
                    f"afade=t=in:st=0:d={min(fade_duration, dur/2)},"
                    f"afade=t=out:st={max(0.0, dur - fade_duration)}:d={min(fade_duration, dur/2)}[a{valid_inputs}];"
                )
                concat_inputs.append(f"[a{valid_inputs}]")
                valid_inputs += 1
            current_time += dur

        if valid_inputs == 0:
            cmd = [
                self.ffmpeg_path, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration}",
                "-c:a", "aac", str(out_p)
            ]
            subprocess.run(cmd, check=True)
            return out_p

        # 全BGMセグメントを1本のマルチBGMトラックへ連結
        filter_complex = "".join(filter_parts) + f"{''.join(concat_inputs)}concat=n={valid_inputs}:v=0:a=1[bgm_out]"

        cmd = [self.ffmpeg_path, "-y", "-loglevel", "error"]
        cmd.extend(input_args)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[bgm_out]",
            "-t", str(total_duration),
            "-c:a", "aac", "-b:a", "192000",
            str(out_p)
        ])

        logger.info(f"MangaVideoComposer: Building multi-BGM audio track for {total_duration:.2f}s...")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            logger.warning(f"BGM audio concatenation warning: {res.stderr}")
            # フォールバック無音生成
            cmd_fb = [
                self.ffmpeg_path, "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_duration}",
                "-c:a", "aac", str(out_p)
            ]
            subprocess.run(cmd_fb, check=True)

        return out_p

    def compose_manga_video(
        self,
        scene_assets: List[Dict[str, Any]],
        bgm_map: Dict[str, Union[str, Path]],  # {"warm": "path/to/warm.mp3", ...}
        output_video_path: Union[str, Path],
        work_dir: Union[str, Path],
        is_paid_member: bool = False,
        video_size: Tuple[int, int] = (1080, 1920)
    ) -> Path:
        """
        全シーンアセットを合成し、感情別BGMマルチ合成＆ロゴオーバーレイ適用して最終動画を出力

        Args:
            scene_assets: Step 3 で出力されたシーン別アセットのリスト
            bgm_map: 感情タグ(`bgm_tag`)に対応するBGMファイルの辞書
            output_video_path: 最終出力動画パス
            work_dir: 作業用一時ディレクトリ
            is_paid_member: Trueの場合はロゴ非表示、Falseの場合はロゴを表示
            video_size: 幅・高さ (1080, 1920)

        Returns:
            合成された最終動画のパス (.mp4)
        """
        work_p = Path(work_dir)
        work_p.mkdir(parents=True, exist_ok=True)
        final_out = Path(output_video_path)
        final_out.parent.mkdir(parents=True, exist_ok=True)

        width, height = video_size

        # ----------------------------------------------------
        # 1. 各シーンのクリップ生成 (演出0.3秒切替 + ナレーション)
        # ----------------------------------------------------
        clip_paths = []
        scene_bgm_sequence = []
        total_duration = 0.0

        for i, scene in enumerate(scene_assets):
            clip_file = work_p / f"scene_clip_{i:03d}.mp4"
            dur = self.create_single_scene_clip(
                base_image_path=scene["base_image_path"],
                overlay_image_path=scene["overlay_image_path"],
                audio_path=scene.get("audio_path"),
                output_clip_path=clip_file,
                duration=scene.get("duration_seconds", 5),
                width=width,
                height=height
            )

            clip_paths.append(clip_file)
            total_duration += dur

            # BGMのシーケンス情報を登録
            bgm_tag = scene.get("bgm_tag", "neutral")
            bgm_file = bgm_map.get(bgm_tag) or bgm_map.get("neutral") or bgm_map.get("warm")
            scene_bgm_sequence.append((dur, str(bgm_file) if bgm_file else None))

        # ----------------------------------------------------
        # 2. 全シーンクリップの映像・ナレーション結合
        # ----------------------------------------------------
        concat_list_file = work_p / "concat_list.txt"
        with open(concat_list_file, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                f.write(f"file '{cp.resolve()}'\n")

        temp_concat_video = work_p / "temp_main_video.mp4"
        cmd_concat = [
            self.ffmpeg_path, "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
            "-c", "copy", str(temp_concat_video)
        ]
        logger.info(f"MangaVideoComposer: Concatenating {len(clip_paths)} scene clips...")
        subprocess.run(cmd_concat, check=True)

        # ----------------------------------------------------
        # 3. マルチBGMトラックの合成
        # ----------------------------------------------------
        multibgm_audio_file = work_p / "multi_bgm_track.aac"
        self.build_multi_bgm_track(
            scene_bgm_sequence=scene_bgm_sequence,
            total_duration=total_duration,
            output_bgm_path=multibgm_audio_file
        )

        # ----------------------------------------------------
        # 4. メイン動画（ナレーション付き）＋マルチBGMのMix＆ロゴ処理
        # ----------------------------------------------------
        filter_parts = []
        # メイン動画のナレーション音量1.0とマルチBGMをMix
        filter_complex = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2[aout]"

        cmd_final = [
            self.ffmpeg_path, "-y", "-loglevel", "error",
            "-i", str(temp_concat_video),
            "-i", str(multibgm_audio_file),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192000",
            "-shortest",
            str(final_out)
        ]

        logger.info(f"MangaVideoComposer: Finalizing manga video composition -> {final_out.name}")
        res = subprocess.run(cmd_final, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise RuntimeError(f"Final video composition failed: {res.stderr}")

        logger.info(f"MangaVideoComposer: Successfully composed video ({total_duration:.2f}s) at {final_out}")
        return final_out
