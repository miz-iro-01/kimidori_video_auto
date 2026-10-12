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
        overlay_image_path: Optional[Union[str, Path]],
        audio_path: Optional[Union[str, Path]],
        output_clip_path: Union[str, Path],
        duration: float,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        switch_delay: float = 0.3,
        video_clip_path: Optional[Union[str, Path]] = None,
        overlay_cards: Optional[List[Dict[str, Any]]] = None,
        enable_ken_burns: bool = True,
        camera_effect: str = "zoom_in",
        trim_start: float = 0.0,
        force_duration: Optional[float] = None,
        se_path: Optional[Union[str, Path]] = None,
        se_volume: float = 0.7,
        se_delay: float = 0.0
    ) -> float:
        """
        1シーン分の動画クリップを作成する。
        - video_clip_path (ComfyUI LTX-Video等のAI生成動画、またはPexelsストック動画) がある場合:
          動画クリップをベース映像として採用し、その上に順次字幕・テロップカードを合成。
        - 静止画の場合:
          Ken Burns効果 (zoompan: zoom_in / zoom_out / pan_left / pan_right) により、滑らかなカメラワーク映像へ自動変換。
        - overlay_cards がある場合:
          ナレーションの尺に合わせて複数のテロップカードまたは0.4秒遅延フキダシを between(t, start, end) で順次切り替え。
        - se_path がある場合:
          ナレーション音声に効果音 (SE) を指定のディレイ・音量で amix 合成。
        """
        out_p = Path(output_clip_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        has_audio = audio_path and Path(audio_path).exists()
        audio_duration = self._get_audio_duration(audio_path) if has_audio else duration
        if trim_start > 0 and has_audio:
            audio_duration = max(0.5, audio_duration - trim_start)

        if force_duration is not None and force_duration > 0.3:
            final_duration = float(force_duration)
        else:
            final_duration = max(duration, audio_duration, switch_delay + 0.5)

        has_ai_video = video_clip_path and Path(video_clip_path).exists() and Path(video_clip_path).stat().st_size > 0
        has_se = se_path and Path(se_path).exists() and Path(se_path).stat().st_size > 0

        cmd = [self.ffmpeg_path, "-y", "-loglevel", "error"]
        filter_parts = []
        current_input_idx = 0

        # ----------------------------------------------------
        # 1. ベース映像の入力とフィルタ構築
        # ----------------------------------------------------
        if has_ai_video:
            # 動画クリップをベース映像として使用
            if trim_start > 0:
                cmd.extend(["-ss", str(trim_start)])
            cmd.extend(["-stream_loop", "-1", "-t", str(final_duration), "-i", str(video_clip_path)])
            filter_parts.append(
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps},settb=AVTB[vbase];"
            )
        else:
            # 静止画ベース（Ken Burns ズームパン演出 または 通常リサイズ）
            cmd.extend(["-loop", "1", "-t", str(final_duration), "-i", str(base_image_path)])
            eff = (camera_effect or "zoom_in").lower()
            if enable_ken_burns and eff != "static":
                up_w = int(width * 1.2)
                up_h = int(height * 1.2)
                if "pan_left" in eff:
                    zp_expr = f"zoompan=z=1.12:x='max(0,(iw-iw/zoom)*(1-on/{max(30, int(final_duration*fps))}))':y='ih/2-(ih/zoom/2)'"
                elif "pan_right" in eff or "pan" in eff:
                    zp_expr = f"zoompan=z=1.12:x='min(iw-iw/zoom,(iw-iw/zoom)*(on/{max(30, int(final_duration*fps))}))':y='ih/2-(ih/zoom/2)'"
                elif "zoom_out" in eff:
                    zp_expr = "zoompan=z='if(lte(on,1),1.15,max(1.0,zoom-0.0008))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                else:
                    zp_expr = "zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                filter_parts.append(
                    f"[0:v]scale={up_w}:{up_h}:force_original_aspect_ratio=increase,"
                    f"crop={up_w}:{up_h},"
                    f"{zp_expr}:"
                    f"d=1:s={width}x{height}:fps={fps},settb=AVTB[vbase];"
                )
            else:
                filter_parts.append(f"[0:v]scale={width}:{height},fps={fps},settb=AVTB[vbase];")

        current_input_idx += 1

        # ----------------------------------------------------
        # 2. テロップカードのオーバーレイ処理
        # ----------------------------------------------------
        valid_cards = []
        if overlay_cards and isinstance(overlay_cards, list) and len(overlay_cards) >= 1:
            for c in overlay_cards:
                cp = c.get("image_path")
                if cp and Path(cp).exists():
                    valid_cards.append({
                        "path": str(cp),
                        "start_time": float(c.get("start_time", 0.0)),
                        "end_time": float(c.get("end_time", final_duration))
                    })

        last_v_label = "[vbase]"

        if len(valid_cards) >= 1:
            # 複数カードの順次オーバーレイチェイン
            num_cards = len(valid_cards)
            for i, card in enumerate(valid_cards):
                cmd.extend(["-loop", "1", "-t", str(final_duration), "-i", card["path"]])
                card_in_idx = current_input_idx
                current_input_idx += 1

                is_last = (i == num_cards - 1)
                next_v_label = "[outv]" if is_last else f"[v_ov_{i}]"
                st = card["start_time"]
                et = card["end_time"]

                filter_parts.append(
                    f"{last_v_label}[{card_in_idx}:v]overlay=0:0:"
                    f"enable='between(t,{st:.2f},{et:.2f})'{next_v_label};"
                )
                last_v_label = next_v_label
        elif overlay_image_path and Path(overlay_image_path).exists():
            # 後方互換フォールバック: 0.3秒後表示
            cmd.extend(["-loop", "1", "-t", str(final_duration), "-i", str(overlay_image_path)])
            ov_in_idx = current_input_idx
            current_input_idx += 1

            filter_parts.append(
                f"[{ov_in_idx}:v]scale={width}:{height},fps={fps},settb=AVTB[v_ov_single];"
                f"{last_v_label}[v_ov_single]overlay=enable='gte(t,{switch_delay})'[outv];"
            )
            last_v_label = "[outv]"
        else:
            filter_parts.append(f"{last_v_label}null[outv];")
            last_v_label = "[outv]"

        # ----------------------------------------------------
        # 3. 音声トラック設定（ナレーション ＋ 効果音SEミキシング対応）
        # ----------------------------------------------------
        if has_audio:
            if trim_start > 0:
                cmd.extend(["-ss", str(trim_start)])
            cmd.extend(["-i", str(audio_path)])
            audio_in_idx = current_input_idx
            current_input_idx += 1
        else:
            cmd.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={final_duration}"])
            audio_in_idx = current_input_idx
            current_input_idx += 1

        if has_se:
            cmd.extend(["-i", str(se_path)])
            se_in_idx = current_input_idx
            current_input_idx += 1
            delay_ms = max(0, int(float(se_delay or 0.0) * 1000))
            vol_se = max(0.0, min(2.0, float(se_volume if se_volume is not None else 0.7)))
            filter_parts.append(
                f"[{audio_in_idx}:a]apad=whole_dur={final_duration},atrim=0:{final_duration},asetpts=PTS-STARTPTS[amain];"
                f"[{se_in_idx}:a]volume={vol_se:.2f},adelay={delay_ms}|{delay_ms},apad=whole_dur={final_duration},atrim=0:{final_duration},asetpts=PTS-STARTPTS[ase];"
                f"[amain][ase]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[outa];"
            )
            audio_map_target = "[outa]"
        else:
            filter_parts.append(
                f"[{audio_in_idx}:a]apad=whole_dur={final_duration},atrim=0:{final_duration},asetpts=PTS-STARTPTS[outa];"
            )
            audio_map_target = "[outa]"

        filter_complex = "".join(filter_parts).rstrip(";")

        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", audio_map_target,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "192000",
            "-t", str(final_duration),
            str(out_p)
        ])

        logger.info(f"MangaVideoComposer: Creating scene clip ({final_duration:.2f}s, AI/Stock Video: {has_ai_video}, SE: {bool(has_se)}, Cards: {len(valid_cards)}) -> {out_p.name}")
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
        video_size: Tuple[int, int] = (1080, 1920),
        bgm_volume: float = BGM_VOLUME
    ) -> Path:
        """
        全シーンアセットを合成し、感情別BGMマルチ合成＆ロゴオーバーレイ適用して最終動画を出力
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
                overlay_image_path=scene.get("overlay_image_path"),
                audio_path=scene.get("audio_path"),
                output_clip_path=clip_file,
                duration=scene.get("duration_seconds", 5),
                width=width,
                height=height,
                switch_delay=float(scene.get("bubble_delay", 0.3) or 0.3),
                video_clip_path=scene.get("video_path"),
                overlay_cards=scene.get("overlay_cards"),
                enable_ken_burns=True,
                camera_effect=str(scene.get("camera_effect") or "zoom_in"),
                trim_start=float(scene.get("trim_start", 0.0) or 0.0),
                force_duration=scene.get("force_duration"),
                se_path=scene.get("se_path"),
                se_volume=float(scene.get("se_volume", 0.7) if scene.get("se_volume") is not None else 0.7),
                se_delay=float(scene.get("se_delay", 0.0) or 0.0)
            )

            clip_paths.append(clip_file)
            total_duration += dur

            # BGMのシーケンス情報を登録（override指定時は全カット統一BGM）
            bgm_tag = scene.get("bgm_tag", "neutral")
            bgm_file = (
                bgm_map.get("__override__")
                or bgm_map.get(bgm_tag)
                or bgm_map.get("neutral")
                or bgm_map.get("warm")
            )
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
            output_bgm_path=multibgm_audio_file,
            bgm_volume=bgm_volume
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
