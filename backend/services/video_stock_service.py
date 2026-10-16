"""
KIMIDORI Movie Auto - 生成済み動画ストック管理（最大5本保持）＆ Pro動画編集スタジオ・再レンダリングサービス
- リロードしても消えない生成済み動画ストック（最大5本自動保存・既存tmpジョブ自動インデックス）
- YouTube定番効果音（SE 10種）のプロシージャル高音質WAV生成＆配信
- Remotion / Filmcraft アーキテクチャ準拠のタイムライン編集データ管理・ナレーション再合成・FFmpeg高速再書き出し
"""

import os
import json
import math
import wave
import struct
import shutil
import base64
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union

import config

logger = logging.getLogger(__name__)

MAX_STOCK_PER_MODE = 5

BUILTIN_SE_PRESETS: List[Dict[str, Any]] = [
    {"id": "none", "name": "効果音なし", "category": "none", "duration": 0.0},
    {"id": "se_don", "name": "ドン！（衝撃・強調インパクト）", "category": "impact", "duration": 0.85},
    {"id": "se_kira", "name": "キラーン（閃き・注目・解決）", "category": "positive", "duration": 0.90},
    {"id": "se_pikon", "name": "ピコン！（気づき・重要ポイント）", "category": "notice", "duration": 0.45},
    {"id": "se_whoosh", "name": "シュッ！（場面転換・高速トランジション）", "category": "transition", "duration": 0.55},
    {"id": "se_taiko", "name": "和太鼓ドドン！（時代劇・浮世絵・歴史強調）", "category": "japanese", "duration": 1.10},
    {"id": "se_hyoushigi", "name": "拍子木カンカン！（江戸・歌舞伎・開幕演出）", "category": "japanese", "duration": 0.90},
    {"id": "se_quiz", "name": "ジャジャン！（問題提示・重要テーマ登場）", "category": "variety", "duration": 0.95},
    {"id": "se_correct", "name": "ピンポーン！（正解・メリット・成功例）", "category": "positive", "duration": 1.00},
    {"id": "se_shock", "name": "ガーン…（絶望・失敗・危機演出）", "category": "negative", "duration": 1.20},
    {"id": "se_drumroll", "name": "ドラムロール＋ジャン！（結果発表・クライマックス）", "category": "variety", "duration": 1.45},
]


class VideoStockAndEditorService:
    """
    最大5本までの生成済み動画ストック永続化と、Pro動画タイムライン編集（テロップ・ナレーション・カット・SE・BGM）を担うサービス
    """

    def __init__(self):
        self.stock_file = config.DATA_DIR / "saved_videos.json"
        self.se_dir = config.DATA_DIR / "se"
        self.se_dir.mkdir(parents=True, exist_ok=True)
        self.stock_file.parent.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. 内蔵効果音（SE）プロシージャル高音質WAV生成
    # =========================================================================
    def list_se_presets(self) -> List[Dict[str, Any]]:
        """利用可能な効果音（SE）プリセット一覧＋カスタムSE一覧を返す"""
        presets = list(BUILTIN_SE_PRESETS)
        for f in sorted(self.se_dir.glob("custom_*.*")):
            if f.suffix.lower() in [".wav", ".mp3", ".ogg", ".m4a"]:
                presets.append({
                    "id": f.name,
                    "name": f"カスタムSE: {f.stem.replace('custom_', '')}",
                    "category": "custom",
                    "duration": 1.0
                })
        return presets

    def ensure_se_file(self, se_id: str) -> Optional[Path]:
        """指定されたSE IDのオーディオファイルパスを返す（未生成なら即座にWAV合成）"""
        if not se_id or se_id == "none":
            return None

        clean_id = se_id.replace("builtin:", "").strip()
        custom_candidate = self.se_dir / clean_id
        if custom_candidate.exists() and custom_candidate.stat().st_size > 100:
            return custom_candidate

        wav_path = self.se_dir / f"{clean_id}.wav"
        if wav_path.exists() and wav_path.stat().st_size > 500:
            return wav_path

        sr = 44100
        samples: List[float] = []

        if clean_id == "se_don":
            # 重厚なサブベース＋和太鼓系アタック衝撃音
            n = int(sr * 0.85)
            for i in range(n):
                t = i / sr
                env = math.exp(-t * 5.2)
                freq = 52.0 + 135.0 * math.exp(-t * 24.0)
                val = 0.72 * math.sin(2.0 * math.pi * freq * t)
                val += 0.28 * math.sin(2.0 * math.pi * (freq * 2.1) * t) * math.exp(-t * 12.0)
                # アタックノイズ
                if t < 0.04:
                    noise = math.sin(i * 12.9898) * 43758.5453
                    noise = noise - math.floor(noise) - 0.5
                    val += noise * 0.65 * (1.0 - t / 0.04)
                samples.append(max(-0.98, min(0.98, val * env)))

        elif clean_id == "se_kira":
            # キラーン（高音クリスタルベル・アルペジオ）
            n = int(sr * 0.90)
            notes = [(0.0, 1760.0), (0.07, 2217.46), (0.14, 2637.02), (0.21, 3520.0)]
            for i in range(n):
                t = i / sr
                val = 0.0
                for start_t, f in notes:
                    if t >= start_t:
                        dt = t - start_t
                        env = math.exp(-dt * 5.5)
                        val += 0.30 * (math.sin(2 * math.pi * f * dt) + 0.4 * math.sin(2 * math.pi * f * 2.0 * dt)) * env
                samples.append(max(-0.95, min(0.95, val)))

        elif clean_id == "se_pikon":
            # ピコン！（2音ポップチャイム）
            n = int(sr * 0.45)
            for i in range(n):
                t = i / sr
                if t < 0.11:
                    f = 987.77  # B5
                    dt = t
                else:
                    f = 1975.53  # B6
                    dt = t - 0.11
                env = math.exp(-dt * 8.5)
                val = 0.55 * (math.sin(2 * math.pi * f * dt) + 0.25 * math.sin(2 * math.pi * f * 3.0 * dt)) * env
                samples.append(max(-0.95, min(0.95, val)))

        elif clean_id == "se_whoosh":
            # シュッ！（風切りトランジション）
            n = int(sr * 0.55)
            for i in range(n):
                t = i / sr
                norm = t / 0.55
                env = math.sin(math.pi * norm) ** 1.6
                sweep_f = 220.0 + 1400.0 * math.sin(math.pi * norm)
                pseudo_noise = math.sin(i * 78.233) * 43758.5453
                pseudo_noise = (pseudo_noise - math.floor(pseudo_noise)) * 2.0 - 1.0
                carrier = math.sin(2 * math.pi * sweep_f * t)
                val = (0.45 * pseudo_noise + 0.35 * carrier) * env
                samples.append(max(-0.95, min(0.95, val)))

        elif clean_id == "se_taiko":
            # 和太鼓ドドン！（時代劇・浮世絵の二連打）
            n = int(sr * 1.10)
            hits = [(0.0, 0.75, 78.0), (0.24, 0.95, 64.0)]
            for i in range(n):
                t = i / sr
                val = 0.0
                for st, amp, base_f in hits:
                    if t >= st:
                        dt = t - st
                        env = math.exp(-dt * 4.8)
                        f = base_f + 95.0 * math.exp(-dt * 28.0)
                        hit_v = math.sin(2 * math.pi * f * dt) + 0.35 * math.sin(2 * math.pi * f * 1.85 * dt) * math.exp(-dt * 10.0)
                        if dt < 0.025:
                            rim = math.sin(2 * math.pi * 1150.0 * dt) * (1.0 - dt / 0.025) * 0.45
                            hit_v += rim
                        val += amp * hit_v * env
                samples.append(max(-0.98, min(0.98, val)))

        elif clean_id == "se_hyoushigi":
            # 拍子木カンカン！（江戸・歌舞伎の硬質木音二連打）
            n = int(sr * 0.90)
            hits = [0.0, 0.32]
            for i in range(n):
                t = i / sr
                val = 0.0
                for st in hits:
                    if t >= st:
                        dt = t - st
                        env = math.exp(-dt * 18.0)
                        wood = (
                            0.55 * math.sin(2 * math.pi * 2380.0 * dt)
                            + 0.35 * math.sin(2 * math.pi * 3420.0 * dt)
                            + 0.25 * math.sin(2 * math.pi * 1620.0 * dt)
                        )
                        val += wood * env
                samples.append(max(-0.96, min(0.96, val)))

        elif clean_id == "se_quiz":
            # ジャジャン！（問題・登場ブラスコード）
            n = int(sr * 0.95)
            for i in range(n):
                t = i / sr
                val = 0.0
                if t < 0.18:
                    dt = t
                    env = math.exp(-dt * 6.0)
                    freqs = [523.25, 659.25, 783.99]
                else:
                    dt = t - 0.18
                    env = math.exp(-dt * 3.8)
                    freqs = [587.33, 739.99, 880.0, 1174.66]
                for f in freqs:
                    val += 0.22 * (math.sin(2 * math.pi * f * dt) + 0.4 * math.sin(2 * math.pi * f * 2 * dt)) * env
                samples.append(max(-0.95, min(0.95, val)))

        elif clean_id == "se_correct":
            # ピンポーン！（正解チャイム E6 -> C6）
            n = int(sr * 1.00)
            notes = [(0.0, 1318.51), (0.28, 1046.50)]
            for i in range(n):
                t = i / sr
                val = 0.0
                for st, f in notes:
                    if t >= st:
                        dt = t - st
                        env = math.exp(-dt * 3.6)
                        val += 0.42 * (math.sin(2 * math.pi * f * dt) + 0.25 * math.sin(2 * math.pi * f * 2.0 * dt)) * env
                samples.append(max(-0.95, min(0.95, val)))

        elif clean_id == "se_shock":
            # ガーン…（重低音ゴング＋不協和下降音）
            n = int(sr * 1.20)
            for i in range(n):
                t = i / sr
                env = math.exp(-t * 2.6)
                drop = 1.0 - 0.18 * min(1.0, t / 1.0)
                freqs = [110.0 * drop, 116.54 * drop, 164.81 * drop, 233.08 * drop]
                val = sum(0.24 * math.sin(2 * math.pi * f * t) for f in freqs) * env
                samples.append(max(-0.96, min(0.96, val)))

        else:  # se_drumroll 等
            n = int(sr * 1.45)
            for i in range(n):
                t = i / sr
                if t < 0.95:
                    # ロール部分
                    roll_env = (0.3 + 0.7 * (t / 0.95)) * (0.5 + 0.5 * math.sin(2 * math.pi * 26.0 * t))
                    noise = math.sin(i * 45.164) * 43758.5453
                    noise = (noise - math.floor(noise)) * 2.0 - 1.0
                    body = math.sin(2 * math.pi * 185.0 * t)
                    val = (0.45 * noise + 0.25 * body) * roll_env
                else:
                    # シンバル＋コードジャン！
                    dt = t - 0.95
                    env = math.exp(-dt * 4.5)
                    noise = math.sin(i * 91.731) * 43758.5453
                    noise = (noise - math.floor(noise)) * 2.0 - 1.0
                    chord = sum(0.18 * math.sin(2 * math.pi * f * dt) for f in [523.25, 659.25, 783.99, 1046.50])
                    val = (0.35 * noise * math.exp(-dt * 7.0) + chord) * env
                samples.append(max(-0.96, min(0.96, val)))

        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            frames = bytearray()
            for s in samples:
                pcm = int(max(-32767, min(32767, s * 32767)))
                frames.extend(struct.pack("<hh", pcm, pcm))
            wf.writeframes(bytes(frames))

        return wav_path

    # =========================================================================
    # 2. 生成済み動画ストック管理（最大5本自動保存 ＆ tmp自動インデックス）
    # =========================================================================
    def _load_stock_raw(self) -> List[Dict[str, Any]]:
        if self.stock_file.exists():
            try:
                data = json.loads(self.stock_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception as e:
                logger.warning(f"Failed to read saved_videos.json: {e}")
        return []

    def _save_stock_raw(self, items: List[Dict[str, Any]]) -> None:
        try:
            self.stock_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write saved_videos.json: {e}")

    def sync_tmp_completed_jobs(self) -> List[Dict[str, Any]]:
        """
        backend/tmp 配下に存在する完成済み動画ジョブを自動検出し、saved_videos.json と同期する。
        これにより、ページをリロードした後でも直近5本の完成動画を即座に復元・表示できる。
        """
        items = self._load_stock_raw()
        known_ids = {item.get("job_id") for item in items if item.get("job_id")}
        deleted_ids_file = config.DATA_DIR / "deleted_stock_ids.json"
        deleted_ids: set = set()
        if deleted_ids_file.exists():
            try:
                deleted_ids = set(json.loads(deleted_ids_file.read_text(encoding="utf-8")))
            except Exception:
                deleted_ids = set()

        if config.TMP_DIR.exists():
            for job_dir in sorted(config.TMP_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
                if not job_dir.is_dir():
                    continue
                job_id = job_dir.name
                if job_id in known_ids or job_id in deleted_ids:
                    continue

                video_file = None
                for cand_name in ["manga_video_final.mp4", "final_with_bgm.mp4", "final_output.mp4"]:
                    cand = job_dir / cand_name
                    if cand.exists() and cand.stat().st_size > 10000:
                        video_file = cand
                        break
                if not video_file:
                    continue

                proj_file = job_dir / "project.json"
                params_file = job_dir / "job_params.json"
                proj_data = {}
                params_data = {}
                if proj_file.exists():
                    try:
                        proj_data = json.loads(proj_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                if params_file.exists():
                    try:
                        params_data = json.loads(params_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                scenes = proj_data.get("scenes", [])
                script_data = params_data.get("script_data", {})
                has_chapters = isinstance(script_data, dict) and "chapters" in script_data
                mode = params_data.get("video_mode") or ("long_video" if (has_chapters or len(scenes) >= 10) else "pro_shorts")

                title = (
                    proj_data.get("title")
                    or (script_data.get("title") if isinstance(script_data, dict) else None)
                    or f"AI生成動画 ({job_id[:8]})"
                )
                theme = proj_data.get("theme") or title
                genre = proj_data.get("genre", "story")
                visual_style = (
                    params_data.get("visual_style")
                    or proj_data.get("visual_style")
                    or ("ukiyoe" if genre == "edoculture" else "anime_modern")
                )

                mtime = datetime.fromtimestamp(video_file.stat().st_mtime).isoformat()
                size_mb = round(video_file.stat().st_size / (1024 * 1024), 2)

                thumb_rel = None
                bg_001 = job_dir / "assets" / "bg_001.png"
                if bg_001.exists():
                    thumb_rel = f"/api/jobs/{job_id}/asset/bg_001.png"

                entry = {
                    "job_id": job_id,
                    "mode": mode,
                    "title": title,
                    "theme": theme,
                    "genre": genre,
                    "visual_style": visual_style,
                    "tts_engine": params_data.get("tts_engine") or proj_data.get("tts_engine", "edge"),
                    "voice_name": params_data.get("voice_name") or proj_data.get("voice_name", "nanami"),
                    "telop_style": params_data.get("telop_style", "shorts_impact_yellow"),
                    "telop_font": params_data.get("telop_font", "DelaGothicOne"),
                    "bgm_choice": params_data.get("bgm_choice", "auto_script"),
                    "scene_count": len(scenes) if scenes else 6,
                    "file_size_mb": size_mb,
                    "video_path": str(video_file),
                    "video_url": f"/api/video/download?path={video_file.name}&job_id={job_id}",
                    "download_url": f"/api/download/{job_id}",
                    "thumbnail_url": thumb_rel,
                    "created_at": mtime,
                    "updated_at": mtime
                }
                items.append(entry)
                known_ids.add(job_id)

        # 実在する動画ファイルのみフィルタし、新しい順にソート
        valid_items = []
        for item in items:
            jid = item.get("job_id")
            if not jid or jid in deleted_ids:
                continue
            j_dir = config.TMP_DIR / jid
            v_path = Path(item.get("video_path", "")) if item.get("video_path") else (j_dir / "manga_video_final.mp4")
            if not v_path.exists():
                v_path = j_dir / "manga_video_final.mp4"
            if v_path.exists() and v_path.stat().st_size > 10000:
                item["video_path"] = str(v_path)
                item["file_size_mb"] = round(v_path.stat().st_size / (1024 * 1024), 2)
                if not item.get("thumbnail_url") and (j_dir / "assets" / "bg_001.png").exists():
                    item["thumbnail_url"] = f"/api/jobs/{jid}/asset/bg_001.png"
                valid_items.append(item)

        valid_items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
        self._save_stock_raw(valid_items)
        return valid_items

    def list_saved_videos(self, mode: Optional[str] = None, limit: int = MAX_STOCK_PER_MODE) -> List[Dict[str, Any]]:
        """指定モード（または全体）の最新5本の保存済み動画リストを返す"""
        all_items = self.sync_tmp_completed_jobs()
        if not mode or mode == "all":
            return all_items[:limit]

        # 該当モードの動画を優先しつつ、合計5本まで取得可能にする
        mode_items = [it for it in all_items if it.get("mode") == mode]
        other_items = [it for it in all_items if it.get("mode") != mode]
        combined = mode_items + other_items
        return combined[:limit]

    def register_completed_video(
        self,
        job_id: str,
        video_path: Union[str, Path],
        project_data: Optional[Dict[str, Any]] = None,
        job_params: Optional[Dict[str, Any]] = None,
        mode: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """動画完成時または再編集書き出し時にストックへ登録し、最大5本ルールで整理する"""
        items = self.sync_tmp_completed_jobs()
        v_p = Path(video_path)
        proj = project_data or kwargs
        params = job_params or kwargs
        scenes = proj.get("scenes", [])
        cut_count = int(kwargs.get("cut_count") or len(scenes) or 6)
        resolved_mode = mode or params.get("video_mode") or proj.get("mode") or ("long_video" if cut_count >= 10 else "pro_shorts")
        now_iso = datetime.utcnow().isoformat()
        size_mb = round(v_p.stat().st_size / (1024 * 1024), 2) if v_p.exists() else 0.0

        job_dir = config.TMP_DIR / job_id
        thumb_rel = f"/api/jobs/{job_id}/asset/bg_001.png" if (job_dir / "assets" / "bg_001.png").exists() else None

        new_entry = {
            "job_id": job_id,
            "mode": resolved_mode,
            "title": proj.get("title") or kwargs.get("title") or "AI生成動画",
            "theme": proj.get("theme") or kwargs.get("theme") or "",
            "genre": proj.get("genre") or kwargs.get("genre") or "story",
            "visual_style": proj.get("visual_style") or params.get("visual_style") or "anime_modern",
            "tts_engine": proj.get("tts_engine") or params.get("tts_engine") or "edge",
            "voice_name": proj.get("voice_name") or params.get("voice_name") or "nanami",
            "telop_style": params.get("telop_style") or proj.get("telop_style") or "shorts_impact_yellow",
            "telop_font": params.get("telop_font") or proj.get("telop_font") or "DelaGothicOne",
            "bgm_choice": params.get("bgm_choice") or proj.get("bgm_choice") or "auto_script",
            "scene_count": cut_count,
            "file_size_mb": size_mb,
            "video_path": str(v_p),
            "video_url": f"/api/download/{job_id}",
            "download_url": f"/api/download/{job_id}?download=1",
            "thumbnail_url": thumb_rel,
            "created_at": now_iso,
            "updated_at": now_iso
        }

        items = [it for it in items if it.get("job_id") != job_id]
        items.insert(0, new_entry)
        self._save_stock_raw(items[:10])
        return new_entry

    def delete_saved_video(self, job_id: str, delete_files: bool = False) -> bool:
        """ストックから指定されたジョブ動画を除外する"""
        deleted_ids_file = config.DATA_DIR / "deleted_stock_ids.json"
        deleted_ids: set = set()
        if deleted_ids_file.exists():
            try:
                deleted_ids = set(json.loads(deleted_ids_file.read_text(encoding="utf-8")))
            except Exception:
                deleted_ids = set()
        deleted_ids.add(job_id)
        deleted_ids_file.write_text(json.dumps(list(deleted_ids), ensure_ascii=False), encoding="utf-8")

        items = self._load_stock_raw()
        items = [it for it in items if it.get("job_id") != job_id]
        self._save_stock_raw(items)
        if delete_files:
            j_dir = config.TMP_DIR / job_id
            if j_dir.exists():
                shutil.rmtree(j_dir, ignore_errors=True)
        return True

    # =========================================================================
    # 3. ユーザーアップロード・カスタムリファレンス画像の保存処理
    # =========================================================================
    @staticmethod
    def save_custom_reference_images(
        job_dir: Path,
        custom_reference_images: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Path]:
        """
        フロントエンドから渡されたカスタムリファレンス画像（Base64 Data URL）を
        job_dir/assets/characters/ に保存し、{character_name_or_default: Path} マップを返す。
        """
        saved_map: Dict[str, Path] = {}
        if not custom_reference_images or not isinstance(custom_reference_images, list):
            return saved_map

        char_dir = job_dir / "assets" / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)

        from PIL import Image
        from io import BytesIO

        for idx, item in enumerate(custom_reference_images):
            if not isinstance(item, dict):
                continue
            data_url = item.get("data_url") or item.get("base64") or ""
            label = (item.get("label") or item.get("character") or "default").strip()
            if not data_url:
                continue

            try:
                raw_b64 = data_url.split(",")[-1] if "," in data_url else data_url
                img_bytes = base64.b64decode(raw_b64)
                img = Image.open(BytesIO(img_bytes)).convert("RGB")
                safe_label = "".join(ch for ch in label if ch.isalnum() or ch in ("_", "-")) or f"ref_{idx+1}"
                out_path = char_dir / f"user_ref_{idx+1}_{safe_label}.png"
                img.save(out_path, "PNG")

                saved_map[label] = out_path
                if idx == 0 or label in ("default", "all", "全員", "共通", "メイン"):
                    saved_map["__user_default__"] = out_path
                logger.info(f"[CustomRefImage] Saved user reference image #{idx+1} (label={label}) -> {out_path.name}")
            except Exception as e:
                logger.warning(f"[CustomRefImage] Failed to decode/save user reference image #{idx+1}: {e}")

        return saved_map

    # =========================================================================
    # 4. Pro動画タイムライン編集スタジオ（Remotion / Filmcraft準拠）の状態取得・保存・再書き出し
    # =========================================================================
    def get_editor_state(self, job_id: str) -> Dict[str, Any]:
        """
        指定ジョブの動画編集スタジオ用タイムライン状態を取得する。
        editor_state.json があれば優先し、なければ project.json + job_params.json + 実アセットから構築する。
        """
        job_dir = config.TMP_DIR / job_id
        if not job_dir.exists():
            raise FileNotFoundError(f"ジョブディレクトリが見つかりません: {job_id}")

        editor_state_path = job_dir / "editor_state.json"
        if editor_state_path.exists():
            try:
                state = json.loads(editor_state_path.read_text(encoding="utf-8"))
                if state and isinstance(state.get("scenes"), list) and len(state["scenes"]) > 0:
                    return state
            except Exception as e:
                logger.warning(f"Failed to read editor_state.json for {job_id}: {e}")

        proj_path = job_dir / "project.json"
        params_path = job_dir / "job_params.json"
        proj = json.loads(proj_path.read_text(encoding="utf-8")) if proj_path.exists() else {}
        params = json.loads(params_path.read_text(encoding="utf-8")) if params_path.exists() else {}
        assets_dir = job_dir / "assets"

        from processors.manga_video_composer import MangaVideoComposer
        composer = MangaVideoComposer()

        default_font = params.get("telop_font") or "DelaGothicOne"
        default_style = params.get("telop_style") or "shorts_impact_yellow"
        default_size = params.get("telop_font_size") or "large"
        default_tts_engine = params.get("tts_engine") or proj.get("tts_engine") or "edge"
        default_voice = params.get("voice_name") or proj.get("voice_name") or "nanami"
        default_bgm = params.get("bgm_choice") or "auto_script"
        default_bgm_vol = float(params.get("bgm_volume", 0.20))

        scenes_out = []
        raw_scenes = proj.get("scenes", [])
        for idx, s in enumerate(raw_scenes):
            sc_id = int(s.get("scene_id", idx + 1))
            audio_file = assets_dir / f"speech_{sc_id:03d}.mp3"
            bg_file = assets_dir / f"bg_{sc_id:03d}.png"
            clip_file = assets_dir / f"clip_{sc_id:03d}.mp4"
            ov_file = assets_dir / f"overlay_{sc_id:03d}.png"

            measured_dur = float(s.get("duration", 5.0))
            if audio_file.exists() and audio_file.stat().st_size > 200:
                measured_dur = round(max(1.5, composer._get_audio_duration(audio_file)), 2)

            mtime_q = int(datetime.utcnow().timestamp())
            scenes_out.append({
                "scene_id": sc_id,
                "cut_key": s.get("cut_key", f"cut_{sc_id:03d}"),
                "enabled": True,
                "speaker": s.get("speaker", "ナレーション"),
                "narration": s.get("narration", ""),
                "telop_text": s.get("telop_text") or s.get("narration", ""),
                "description": s.get("description", ""),
                "duration": measured_dur,
                "original_duration": measured_dur,
                "trim_start": 0.0,
                "telop_font": s.get("telop_font") or default_font,
                "telop_style": s.get("telop_style") or default_style,
                "telop_font_size": s.get("telop_font_size") or default_size,
                "telop_position": s.get("telop_position", "bottom"),
                "telop_y_pct": int(s.get("telop_y_pct", 76)),
                "telop_scale": int(s.get("telop_scale", 100)),
                "tts_engine": s.get("tts_engine") or default_tts_engine,
                "voice_name": s.get("voice_name") or default_voice,
                "speaking_rate": float((params.get("tts_params") or {}).get("speaking_rate", 1.0)),
                "se_id": s.get("se_id", "none"),
                "se_volume": float(s.get("se_volume", 0.70)),
                "se_delay": float(s.get("se_delay", 0.0)),
                "bgm_tag": s.get("bgm_tag", "neutral"),
                "has_video_clip": clip_file.exists() and clip_file.stat().st_size > 1000,
                "clip_url": f"/api/jobs/{job_id}/asset/clip_{sc_id:03d}.mp4?v={mtime_q}" if clip_file.exists() else None,
                "image_url": f"/api/jobs/{job_id}/asset/bg_{sc_id:03d}.png?v={mtime_q}" if bg_file.exists() else None,
                "audio_url": f"/api/jobs/{job_id}/asset/speech_{sc_id:03d}.mp3?v={mtime_q}" if audio_file.exists() else None,
                "overlay_url": f"/api/jobs/{job_id}/asset/overlay_{sc_id:03d}.png?v={mtime_q}" if ov_file.exists() else None,
            })

        state = {
            "job_id": job_id,
            "title": proj.get("title", "AI生成動画"),
            "theme": proj.get("theme", ""),
            "genre": proj.get("genre", "story"),
            "visual_style": params.get("visual_style") or proj.get("visual_style", "anime_modern"),
            "bgm_choice": default_bgm,
            "bgm_volume": default_bgm_vol,
            "telop_font": default_font,
            "telop_style": default_style,
            "telop_font_size": default_size,
            "tts_engine": default_tts_engine,
            "voice_name": default_voice,
            "video_url": f"/api/download/{job_id}?v={int(datetime.utcnow().timestamp())}",
            "script_data": params.get("script_data") or proj,
            "scenes": scenes_out
        }
        self.save_editor_state(job_id, state)
        return state

    def save_editor_state(self, job_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """編集中のタイムライン状態を editor_state.json に保存する"""
        job_dir = config.TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        editor_state_path = job_dir / "editor_state.json"
        state["updated_at"] = datetime.utcnow().isoformat()
        editor_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

    async def resynthesize_cut_tts(
        self,
        job_id: str,
        scene_id: Optional[int] = None,
        narration: str = "",
        tts_engine: str = "edge",
        voice_name: str = "nanami",
        speaking_rate: float = 1.0,
        tts_params: Optional[Dict[str, Any]] = None,
        cut_index: Optional[int] = None,
        speaker: str = "ナレーション"
    ) -> Dict[str, Any]:
        """特定カットのナレーションテキスト・声色・話速を変更して即座に音声を再合成し、尺を更新する"""
        scene_id = int(scene_id or cut_index or 1)
        job_dir = config.TMP_DIR / job_id
        assets_dir = job_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        from processors.tts_manager import TTSManager
        from processors.manga_video_composer import MangaVideoComposer

        extra_params = dict(tts_params or {})
        extra_params.pop("engine", None)
        extra_params.pop("voice_name", None)
        extra_params.pop("speaking_rate", None)

        tts_mgr = TTSManager(
            engine=tts_engine or "edge",
            voice_name=voice_name or "nanami",
            speaking_rate=float(speaking_rate or 1.0),
            **extra_params
        )

        audio_out_path = assets_dir / f"speech_{int(scene_id):03d}.mp3"
        temp_sub = assets_dir / f"edit_tts_{int(scene_id):03d}"
        temp_sub.mkdir(parents=True, exist_ok=True)

        gen_paths = await tts_mgr.synthesize_all_scenes([{"narration": narration}], temp_sub)
        if not gen_paths or not gen_paths[0].exists():
            raise RuntimeError("ナレーション音声の再生成に失敗しました")

        shutil.copy2(gen_paths[0], audio_out_path)
        shutil.rmtree(temp_sub, ignore_errors=True)

        new_dur = round(max(1.5, MangaVideoComposer()._get_audio_duration(audio_out_path)), 2)
        ts = int(datetime.utcnow().timestamp() * 1000)
        audio_url = f"/api/jobs/{job_id}/asset/{audio_out_path.name}?v={ts}"

        # editor_state.json も同期更新
        try:
            state = self.get_editor_state(job_id)
            for sc in state.get("scenes", []):
                if int(sc.get("scene_id", 0)) == int(scene_id):
                    sc["narration"] = narration
                    sc["telop_text"] = narration
                    sc["tts_engine"] = tts_engine
                    sc["voice_name"] = voice_name
                    sc["speaking_rate"] = speaking_rate
                    sc["duration"] = new_dur
                    sc["audio_url"] = audio_url
            self.save_editor_state(job_id, state)
        except Exception as e:
            logger.warning(f"Failed to update editor_state after TTS resynth: {e}")

        return {
            "success": True,
            "scene_id": scene_id,
            "audio_url": audio_url,
            "duration": new_dur
        }

    def render_edited_timeline(
        self,
        job_id: str,
        editor_state: Dict[str, Any],
        progress_callback: Optional[ Any ] = None
    ) -> Dict[str, Any]:
        """
        動画編集スタジオでの変更内容（テロップ種類・Y位置・サイズ、ナレーション変更、
        カット順序・トリミング・削除、効果音SE追加、BGM変更・音量調整）をすべて反映し、
        FFmpegで高速再レンダリングして完成MP4を更新する。
        """
        from processors.batch_asset_generator import BatchAssetGenerator
        from processors.manga_video_composer import MangaVideoComposer

        job_dir = config.TMP_DIR / job_id
        assets_dir = job_dir / "assets"
        work_dir = job_dir / "work_edit"
        work_dir.mkdir(parents=True, exist_ok=True)

        self.save_editor_state(job_id, editor_state)

        batch_gen = BatchAssetGenerator()
        composer = MangaVideoComposer()

        genre = editor_state.get("genre", "story")
        global_font = editor_state.get("telop_font", "DelaGothicOne")
        global_style = editor_state.get("telop_style", "shorts_impact_yellow")
        global_size = editor_state.get("telop_font_size", "large")
        bgm_choice = editor_state.get("bgm_choice", "auto_script")
        bgm_volume = float(editor_state.get("bgm_volume", 0.20))
        visual_style = editor_state.get("visual_style", "anime_modern")

        studio_cfg = editor_state.get("studio") or {}
        studio_telops_override = bool(studio_cfg.get("telops_override")) and bool(studio_cfg.get("telops"))
        if studio_cfg.get("bgm_muted"):
            bgm_choice = "none"

        active_scenes = [s for s in editor_state.get("scenes", []) if s.get("enabled", True) is not False]
        if not active_scenes:
            raise ValueError("有効なカットが1つもありません。少なくとも1カットを有効にしてください。")

        scene_assets_for_composer: List[Dict[str, Any]] = []
        total_active = len(active_scenes)

        for idx, sc in enumerate(active_scenes):
            sc_id = int(sc.get("scene_id", idx + 1))
            if progress_callback:
                pct = 15 + int((idx / max(total_active, 1)) * 45)
                progress_callback(pct, f"編集カット {idx + 1} / {total_active} のテロップ・音声・効果音を構築中...")

            speaker = sc.get("speaker", "ナレーション")
            narration = sc.get("narration", "")
            telop_text = sc.get("telop_text") if sc.get("telop_text") is not None else narration
            if studio_telops_override:
                telop_text = ""  # Studio telop clips are composited in the post process
            cut_font = sc.get("telop_font") or global_font
            cut_style = sc.get("telop_style") or global_style
            cut_size = sc.get("telop_font_size") or global_size

            # テロップY位置の決定 (top=18%, center=50%, bottom=76%, またはカスタム telop_y_pct)
            pos_key = sc.get("telop_position", "bottom")
            y_pct = sc.get("telop_y_pct")
            if y_pct is not None:
                y_ratio = max(0.08, min(0.92, float(y_pct) / 100.0))
            elif pos_key == "top":
                y_ratio = 0.18
            elif pos_key == "center":
                y_ratio = 0.50
            else:
                y_ratio = 0.76

            scale_mult = max(0.65, min(1.45, float(sc.get("telop_scale", 100)) / 100.0))

            bg_path = assets_dir / f"bg_{sc_id:03d}.png"
            if not bg_path.exists():
                pil_ph = batch_gen._generate_artistic_backdrop(1080, 1920, sc.get("description", ""), sc_id, genre=genre)
                pil_ph.save(bg_path, "PNG")

            clip_path = assets_dir / f"clip_{sc_id:03d}.mp4"
            audio_path = assets_dir / f"speech_{sc_id:03d}.mp3"

            dur = float(sc.get("duration") or 5.0)
            trim_start = max(0.0, float(sc.get("trim_start") or 0.0))

            # テロップカードを新しいフォント・配色・Y位置・サイズで再生成
            overlay_cards = batch_gen._create_manga_bubble_overlays_sequence(
                width=1080,
                height=1920,
                speaker=speaker,
                narration=telop_text,
                duration=dur,
                output_dir=assets_dir,
                scene_num=sc_id,
                genre=genre,
                telop_style=cut_style,
                font_size_key=cut_size,
                telop_font=cut_font,
                telop_y_ratio=y_ratio,
                telop_scale_mult=scale_mult
            )

            ov_single = assets_dir / f"overlay_{sc_id:03d}.png"
            if overlay_cards and Path(overlay_cards[0]["image_path"]).exists():
                shutil.copy2(overlay_cards[0]["image_path"], ov_single)

            # 効果音（SE）の解決
            se_id = sc.get("se_id", "none")
            se_file_path = self.ensure_se_file(se_id) if se_id and se_id != "none" else None
            se_volume = float(sc.get("se_volume", 0.70))
            se_delay = float(sc.get("se_delay", 0.0))

            # Jet-cut: rebuild narration audio with the silent ranges removed
            jet_keep = sc.get("jet_keep")
            if jet_keep and audio_path.exists():
                try:
                    from studio_pro import build_jetcut_audio
                    jc_path = work_dir / f"speech_{sc_id:03d}_jc.mp3"
                    if build_jetcut_audio(audio_path, jc_path, jet_keep):
                        audio_path = jc_path
                except Exception as jc_err:
                    logger.warning(f"jet-cut audio build skipped for scene {sc_id}: {jc_err}")

            scene_assets_for_composer.append({
                "scene_number": sc_id,
                "speaker": speaker,
                "narration": narration,
                "bgm_tag": sc.get("bgm_tag", "neutral"),
                "base_image_path": str(bg_path),
                "overlay_image_path": str(ov_single) if ov_single.exists() else None,
                "overlay_cards": overlay_cards,
                "video_path": str(clip_path) if (clip_path.exists() and clip_path.stat().st_size > 1000) else None,
                "audio_path": str(audio_path) if (audio_path.exists() and audio_path.stat().st_size > 200) else None,
                "duration_seconds": dur,
                "trim_start": trim_start,
                "force_duration": dur,
                "se_path": str(se_file_path) if se_file_path else None,
                "se_volume": se_volume,
                "se_delay": se_delay
            })

        # BGMの解決
        effective_bgm_map: Dict[str, str] = {}
        builtin_bgm_dir = config.DATA_DIR / "bgm"
        choice = (bgm_choice or "none").strip()

        if choice in ("none", "", "null"):
            effective_bgm_map = {}
        elif choice.startswith("builtin:"):
            preset_wav = batch_gen.ensure_builtin_bgm_file(choice, builtin_bgm_dir)
            if preset_wav and preset_wav.exists():
                effective_bgm_map["__override__"] = str(preset_wav)
        elif choice != "auto_script":
            custom_bgm_file = builtin_bgm_dir / choice
            if custom_bgm_file.exists():
                effective_bgm_map["__override__"] = str(custom_bgm_file)

        if progress_callback:
            progress_callback(70, "FFmpegで編集済みタイムライン映像・テロップ・効果音・BGMを合成中...")

        output_mp4 = job_dir / "manga_video_final.mp4"
        composer.compose_manga_video(
            scene_assets=scene_assets_for_composer,
            bgm_map=effective_bgm_map,
            output_video_path=output_mp4,
            work_dir=work_dir,
            is_paid_member=True,
            bgm_volume=bgm_volume
        )

        # Studio Pro: wipe / B-roll / studio telop post process
        try:
            from studio_pro import apply_studio_postprocess
            apply_studio_postprocess(job_dir, output_mp4, editor_state, work_dir)
        except Exception as sp_err:
            logger.warning(f"studio post process skipped: {sp_err}")

        # ストック情報を更新
        stock_entry = self.register_completed_video(
            job_id=job_id,
            video_path=output_mp4,
            project_data=editor_state
        )

        ts = int(datetime.utcnow().timestamp() * 1000)
        return {
            "success": True,
            "job_id": job_id,
            "video_path": str(output_mp4),
            "video_url": f"/api/download/{job_id}?v={ts}",
            "download_url": f"/api/download/{job_id}?download=1&v={ts}",
            "stock_entry": stock_entry
        }
