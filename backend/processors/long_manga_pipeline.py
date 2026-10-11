"""
KIMIDORI Movie Auto - 長尺漫画動画（15〜20分）＆ Pro版ショート統合パイプライン
タイムラインJSON（設計書モデル）、1/5動画コスト最適化、単体リカバリー機構、
0.3秒演出切り替え・マルチBGMクロスフェード合成
"""

import os
import sys
import json
import logging
import asyncio
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime

from models.timeline import TimelineProject, TimelineScene, CameraWork
from processors.batch_asset_generator import BatchAssetGenerator
from processors.manga_video_composer import MangaVideoComposer
import config

logger = logging.getLogger(__name__)


def normalize_script_data_to_timeline(script_data: Dict[str, Any]) -> TimelineProject:
    """
    script_data が 「chapters/cuts 階層構造（長尺動画形式）」、「cuts 単体配列（Pro版ショート）」、
    あるいは「scenes 形式（従来形式）」のいずれであっても自動検知し、
    TimelineProject / TimelineScene に統一正規化する。
    """
    title = script_data.get("title") or script_data.get("theme") or "Untitled Manga Video"
    genre = script_data.get("genre", "story")
    characters = script_data.get("characters", [])
    
    project = TimelineProject(
        title=title,
        theme=script_data.get("theme", title),
        genre=genre,
        characters=characters,
        scenes=[]
    )

    cut_counter = 1

    # パターン A: chapters / cuts 階層構造（全120〜180カット等の長尺動画形式）
    if "chapters" in script_data and isinstance(script_data["chapters"], list):
        logger.info(f"[Timeline] Detected 'chapters/cuts' format with {len(script_data['chapters'])} chapters.")
        for ch_idx, chapter in enumerate(script_data["chapters"]):
            chapter_cuts = chapter.get("cuts", [])
            for c_idx, cut in enumerate(chapter_cuts):
                narration = (
                    cut.get("dialogue") or 
                    cut.get("narration") or 
                    cut.get("text") or 
                    cut.get("lines") or ""
                )
                speaker = cut.get("speaker") or cut.get("character") or "ナレーション"
                prompt = (
                    cut.get("visual_prompt") or 
                    cut.get("image_prompt") or 
                    cut.get("description") or 
                    cut.get("scene_description") or ""
                )
                camera_eff = cut.get("camera_effect", "ken_burns")
                duration = float(cut.get("duration_seconds") or cut.get("duration") or 5.0)
                is_video = bool(cut.get("is_video_cut", False))

                cw = CameraWork(effect="ken_burns")
                if "ズーム" in str(camera_eff) or "zoom" in str(camera_eff).lower():
                    cw.effect = "zoom_in"
                elif "パン" in str(camera_eff) or "pan" in str(camera_eff).lower():
                    cw.effect = "pan_left"

                scene = TimelineScene(
                    scene_id=cut_counter,
                    cut_key=f"ch{ch_idx + 1}_cut{c_idx + 1}",
                    type="video" if is_video else "image",
                    duration=duration,
                    speaker=speaker,
                    narration=narration,
                    description=prompt,
                    character_prompt=prompt,
                    bgm_tag=cut.get("bgm_tag", "neutral"),
                    camera_work=cw,
                    status="pending"
                )
                project.scenes.append(scene)
                cut_counter += 1

    # パターン B: cuts 単体配列（Pro版ショート動画形式）
    elif "cuts" in script_data and isinstance(script_data["cuts"], list):
        logger.info(f"[Timeline] Detected top-level 'cuts' format with {len(script_data['cuts'])} cuts.")
        for c_idx, cut in enumerate(script_data["cuts"]):
            narration = cut.get("dialogue") or cut.get("narration") or cut.get("text") or ""
            speaker = cut.get("speaker") or "ナレーション"
            prompt = cut.get("description") or cut.get("scene_description") or ""
            duration = float(cut.get("duration_seconds") or cut.get("duration") or 5.0)
            is_video = bool(cut.get("is_video_cut", False) or "動画" in str(cut.get("camera_effect", "")))

            scene = TimelineScene(
                scene_id=cut_counter,
                cut_key=f"cut_{c_idx + 1:03d}",
                type="video" if is_video else "image",
                duration=duration,
                speaker=speaker,
                narration=narration,
                description=prompt,
                character_prompt=prompt,
                bgm_tag=cut.get("bgm_tag", "neutral"),
                status="pending"
            )
            project.scenes.append(scene)
            cut_counter += 1

    # パターン C: scenes 配列構造（従来の漫画動画形式）
    elif "scenes" in script_data and isinstance(script_data["scenes"], list):
        logger.info(f"[Timeline] Detected flat 'scenes' format with {len(script_data['scenes'])} scenes.")
        for idx, sc in enumerate(script_data["scenes"]):
            narration = sc.get("narration") or sc.get("text") or sc.get("dialogue") or ""
            speaker = sc.get("speaker") or "ナレーション"
            prompt = sc.get("character_prompt") or sc.get("visual_description") or sc.get("image_prompt") or ""
            duration = float(sc.get("duration_seconds") or sc.get("duration") or 5.0)

            scene = TimelineScene(
                scene_id=cut_counter,
                cut_key=f"scene_{idx + 1:03d}",
                type="image",
                duration=duration,
                speaker=speaker,
                narration=narration,
                description=prompt,
                character_prompt=prompt,
                bgm_tag=sc.get("bgm_tag", "neutral"),
                status="pending"
            )
            project.scenes.append(scene)
            cut_counter += 1

    # 万が一データが空の場合のフォールバック
    if len(project.scenes) == 0:
        logger.warning("[Timeline] Empty script_data. Creating fallback intro scene.")
        project.scenes.append(
            TimelineScene(
                scene_id=1,
                cut_key="fallback_001",
                type="image",
                duration=5.0,
                speaker="ナレーション",
                narration=title,
                description="Anime style modern illustration",
                character_prompt="Anime style modern illustration",
                status="pending"
            )
        )

    # 1/5 動画コスト最適化の適用
    project.optimize_video_ratio(video_ratio=0.2)
    logger.info(f"[Timeline] Successfully normalized {len(project.scenes)} scenes (Video cuts: {sum(1 for s in project.scenes if s.type == 'video')}).")
    return project


async def run_long_manga_pipeline(
    job_id: str,
    script_data: Dict[str, Any],
    user_id: str,
    tts_engine: str,
    voice_name: str,
    bgm_map: Dict[str, Any],
    watermark_required: bool,
    paid_gemini_api_key: str = "",
    tts_params: Optional[Dict[str, Any]] = None,
    firestore_client: Any = None,
    colab_worker_url: Optional[str] = "",
    fal_api_key: Optional[str] = "",
    replicate_api_token: Optional[str] = "",
    pexels_api_key: Optional[str] = "",
    visual_style: Optional[str] = None,
    telop_style: Optional[str] = "shorts_impact_yellow",
    telop_mode: Optional[str] = "sequential",
    telop_font_size: Optional[str] = "medium",
    telop_font: Optional[str] = "DelaGothicOne",
    bgm_choice: Optional[str] = "auto_script",
    bgm_volume: float = 0.20
) -> str:
    """
    長尺漫画動画・Pro版ショート動画の全体生成パイプライン実行メイン関数。
    5%から100%までリアルタイムに進捗と詳細ログを Firestore に刻みながら実行する。
    """
    from services.firestore_service import FirestoreService
    firestore = firestore_client or FirestoreService()

    logs = []
    job_dir = config.TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = job_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    work_dir = job_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    def log_and_update(progress: int, step: int, step_label: str, message: str):
        logs.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {message}")
        firestore.update_job(
            job_id,
            progress=progress,
            step=step,
            step_label=step_label,
            message=message,
            logs=logs
        )
        logger.info(f"[{job_id}] ({progress}%) {message}")

    try:
        # Step 1: 台本データの解析＆タイムライン正規化 (10%)
        log_and_update(10, 1, "タイムライン正規化 & コスト最適化中", "台本データを解析し、タイムライン中間設計図へ正規化中...")
        project = normalize_script_data_to_timeline(script_data)
        resolved_visual_style = (
            visual_style
            or script_data.get("visual_style")
            or ("ukiyoe" if project.genre == "edoculture" else "anime_modern")
        )
        total_scenes = len(project.scenes)
        log_and_update(
            15, 1, "タイムライン構築完了", 
            f"全 {total_scenes} カットをタイムライン設計書に展開（スタイル: {resolved_visual_style} / 画像生成 ➔ I2Vアニメーション動画化）"
        )

        # project.json を一時ディレクトリに保存（単体再生成・リカバリー用）
        project_json_path = job_dir / "project.json"
        with open(project_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_id": job_id,
                "title": project.title,
                "theme": project.theme,
                "genre": project.genre,
                "visual_style": resolved_visual_style,
                "tts_engine": tts_engine,
                "voice_name": voice_name,
                "scenes": [
                    {
                        "scene_id": s.scene_id,
                        "cut_key": s.cut_key,
                        "type": s.type,
                        "status": s.status,
                        "duration": s.duration,
                        "speaker": s.speaker,
                        "narration": s.narration,
                        "description": s.description,
                        "character_prompt": s.character_prompt,
                        "bgm_tag": s.bgm_tag
                    } for s in project.scenes
                ]
            }, f, ensure_ascii=False, indent=2)

        # Step 1.5: 登場人物の実画像マスター（単一キャラクターバストアップ）事前一括生成 (18%)
        batch_gen = BatchAssetGenerator()

        # キャラクター定義の確認と自動補完（シーン情景は絶対に含めず純粋なキャラクター外見のみを指定）
        char_style_hint = (
            "authentic Edo-period Ukiyo-e woodblock print portrait by Hokusai and Kuniyoshi, slender ukiyo-e eyes, sumi-e ink outlines on handmade washi paper, strictly NO anime style"
            if resolved_visual_style == "ukiyoe"
            else f"distinctive character design in {resolved_visual_style} style, waist-up portrait on clean background"
        )
        if not getattr(project, "characters", None):
            speaker_set = []
            for s in project.scenes:
                spk = (s.speaker or "").strip()
                if spk and spk not in ["ナレーション", "語り", "解説", "Voice", "SE"] and spk not in speaker_set:
                    speaker_set.append(spk)
            if speaker_set:
                project.characters = [
                    {
                        "name": spk_name,
                        "appearance_prompt_en": (
                            f"single character {spk_name} from '{project.theme}', "
                            f"period-appropriate attire, {char_style_hint}"
                        )
                    }
                    for spk_name in speaker_set[:2]
                ]
            else:
                project.characters = [
                    {
                        "name": "メインキャラクター",
                        "appearance_prompt_en": (
                            f"single main protagonist character from '{project.theme}', "
                            f"{char_style_hint}"
                        )
                    }
                ]

        if project.characters:
            char_names = [c.get("name") for c in project.characters if c.get("name")]
            log_and_update(
                18, 1, f"マスターリファレンス画像生成中 ({resolved_visual_style})",
                f"Gemini Nano Banana で基準マスター画像を生成中 ({resolved_visual_style}): {', '.join(char_names)}"
            )
            char_master_map = await batch_gen.generate_character_masters(
                characters=project.characters,
                output_dir=assets_dir,
                colab_worker_url=colab_worker_url,
                fal_api_key=fal_api_key,
                replicate_api_token=replicate_api_token,
                paid_gemini_api_key=paid_gemini_api_key,
                visual_style=resolved_visual_style
            )
            log_and_update(
                20, 1, "マスターリファレンス画像確定完了",
                f"基準マスター画像の生成が完了しました（{len(char_master_map)}件 / スタイル: {resolved_visual_style}）。これをリファレンスにして各シーン画像 ➔ アニメーション動画を生成します"
            )
        else:
            char_master_map = {}

        # Step 2: 各シーンのアセット生成（Stage1: 画像生成 ➔ Stage2: I2Vアニメーション動画化 ➔ Stage3: プロ仕様テロップ）(20%〜65%)
        scene_assets = []

        log_and_update(20, 2, "シーン画像＆I2Vアニメーション生成中", f"全 {total_scenes} カットの画像生成 ➔ リファレンスI2Vアニメーション動画化を開始します...")

        for idx, scene in enumerate(project.scenes):
            scene_num = scene.scene_id
            curr_pct = 20 + int((idx / total_scenes) * 45) # 20% 〜 65%
            
            log_and_update(
                curr_pct, 2, "画像生成 ➔ I2Vアニメーション変換中",
                f"カット {idx + 1} / {total_scenes} 生成中 ({scene.speaker}: {scene.narration[:15]}...)"
            )

            scene_dict = {
                "scene_number": scene_num,
                "speaker": scene.speaker,
                "narration": scene.narration,
                "character_prompt": scene.character_prompt or scene.description,
                "visual_description": scene.description,
                "bgm_tag": scene.bgm_tag,
                "duration_seconds": scene.duration
            }

            try:
                asset_res = await batch_gen.generate_single_scene_assets(
                    scene_data=scene_dict,
                    output_dir=assets_dir,
                    tts_engine=tts_engine,
                    voice_name=voice_name,
                    tts_params=tts_params,
                    paid_gemini_api_key=paid_gemini_api_key,
                    colab_worker_url=colab_worker_url,
                    fal_api_key=fal_api_key,
                    replicate_api_token=replicate_api_token,
                    pexels_api_key=pexels_api_key,
                    characters=project.characters,
                    character_master_map=char_master_map,
                    genre=project.genre,
                    visual_style=resolved_visual_style,
                    telop_style=telop_style,
                    telop_mode=telop_mode,
                    telop_font_size=telop_font_size,
                    telop_font=telop_font
                )
                scene.status = "generated"
                scene_assets.append(asset_res)
            except Exception as scene_err:
                logger.warning(f"Scene {scene_num} asset generation warning: {scene_err}")
                scene.status = "failed"
                # 安全な美麗フォールバック
                pil_ph = batch_gen._generate_artistic_backdrop(1080, 1920, scene.description, scene_num, genre=project.genre)
                ph_path = assets_dir / f"bg_{scene_num:03d}.png"
                pil_ph.save(ph_path, "PNG")

                pil_ov = batch_gen._create_manga_bubble_overlay(
                    1080, 1920, scene.speaker, scene.narration, genre=project.genre, telop_style=telop_style, telop_font=telop_font
                )
                ov_path = assets_dir / f"overlay_{scene_num:03d}.png"
                pil_ov.save(ov_path, "PNG")


                scene_assets.append({
                    "scene_number": scene_num,
                    "speaker": scene.speaker,
                    "narration": scene.narration,
                    "bgm_tag": scene.bgm_tag,
                    "audio_path": None,
                    "base_image_path": str(ph_path),
                    "overlay_image_path": str(ov_path),
                    "duration_seconds": scene.duration
                })

        # Firestore に各シーンの最新ステータス一覧を格納
        scenes_data_for_ui = [
            {
                "scene_id": s.scene_id,
                "cut_key": s.cut_key,
                "type": s.type,
                "status": s.status,
                "duration": s.duration,
                "speaker": s.speaker,
                "narration": s.narration,
                "description": s.description
            } for s in project.scenes
        ]
        firestore.update_job(job_id, scenes=scenes_data_for_ui)

        log_and_update(65, 3, "アセット生成完了", f"全 {len(scene_assets)} カットのアセット生成が正常に完了しました")

        # Step 3: BGM選曲の解決 ＆ マルチBGMクロスフェード動画合成 (70%〜90%)
        effective_bgm_map = dict(bgm_map or {})
        builtin_bgm_dir = config.DATA_DIR / "bgm"
        choice = (bgm_choice or "auto_script").strip()

        if choice == "none":
            effective_bgm_map = {}
        elif choice.startswith("builtin:"):
            preset_wav = batch_gen.ensure_builtin_bgm_file(choice, builtin_bgm_dir)
            if preset_wav and preset_wav.exists():
                effective_bgm_map["__override__"] = str(preset_wav)
        elif choice != "auto_script":
            # 登録済みカスタムBGMファイル名またはbgm_id指定
            custom_bgm_file = builtin_bgm_dir / choice
            if custom_bgm_file.exists():
                effective_bgm_map["__override__"] = str(custom_bgm_file)
            else:
                try:
                    from services.bgm_service import BGMService
                    from services.storage_service import StorageService
                    bgm_svc = BGMService(firestore, StorageService())
                    dl_bgm = bgm_svc.download_bgm(choice, builtin_bgm_dir)
                    if dl_bgm and dl_bgm.exists():
                        effective_bgm_map["__override__"] = str(dl_bgm)
                except Exception as bgm_dl_err:
                    logger.warning(f"Failed to download custom BGM {choice}: {bgm_dl_err}")

        # auto_script またはフォールバック補完: 未設定タグに内蔵BGMを自動割り当て
        if choice != "none" and "__override__" not in effective_bgm_map:
            tag_to_builtin = {
                "cheerful": "upbeat_marimba",
                "funny": "upbeat_marimba",
                "warm": "calm_piano",
                "touching": "calm_piano",
                "suspense": "mystery_synth",
                "frightening": "mystery_synth",
                "epic": "dramatic_strings",
                "neutral": "edo_ukiyoe" if (resolved_visual_style == "ukiyoe" or project.genre == "edoculture") else "corporate_clean"
            }
            if resolved_visual_style == "ukiyoe" or project.genre == "edoculture":
                edo_wav = batch_gen.ensure_builtin_bgm_file("edo_ukiyoe", builtin_bgm_dir)
                if edo_wav:
                    for t_k in tag_to_builtin:
                        if t_k not in effective_bgm_map or not Path(str(effective_bgm_map[t_k])).exists():
                            effective_bgm_map[t_k] = str(edo_wav)
            else:
                for t_k, b_id in tag_to_builtin.items():
                    if t_k not in effective_bgm_map or not Path(str(effective_bgm_map[t_k])).exists():
                        b_wav = batch_gen.ensure_builtin_bgm_file(b_id, builtin_bgm_dir)
                        if b_wav:
                            effective_bgm_map[t_k] = str(b_wav)

        log_and_update(70, 4, "マルチBGMクロスフェード & 演出合成中", f"BGM設定 ({choice}) ＆ テロップ合成を実行しています...")
        composer = MangaVideoComposer()
        output_mp4 = job_dir / "manga_video_final.mp4"

        # FFmpeg合成をスレッドプールで実行
        await asyncio.to_thread(
            composer.compose_manga_video,
            scene_assets=scene_assets,
            bgm_map=effective_bgm_map,
            output_video_path=output_mp4,
            work_dir=work_dir,
            is_paid_member=not watermark_required,
            bgm_volume=float(bgm_volume or 0.20)
        )

        if not output_mp4.exists() or output_mp4.stat().st_size == 0:
            raise RuntimeError("動画合成処理が完了しましたが、出力ファイルが生成されませんでした。")

        file_mb = output_mp4.stat().st_size / (1024 * 1024)
        log_and_update(95, 5, "動画ファイル確定", f"高画質長尺動画のレンダリングが完了しました ({file_mb:.1f} MB)")

        # 完了更新
        firestore.update_job(
            job_id,
            status="completed",
            progress=100,
            step=5,
            step_label="動画作成完了",
            message="長尺動画の作成が完了しました！ダウンロード可能です。",
            video_path=str(output_mp4),
            scenes=scenes_data_for_ui,
            logs=logs
        )
        logger.info(f"Job {job_id} successfully completed. Output: {output_mp4}")
        return str(output_mp4)

    except Exception as e:
        err_msg = f"動画生成エラー: {str(e)}"
        logger.error(f"Long manga pipeline failed for job {job_id}: {e}\n{traceback.format_exc()}")
        logs.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] ERROR: {err_msg}")
        firestore.update_job(
            job_id,
            status="failed",
            progress=0,
            step_label="エラー発生",
            message=err_msg,
            logs=logs
        )
        raise e


async def regenerate_single_scene(
    job_id: str,
    scene_id: int,
    custom_prompt: Optional[str] = None,
    tts_engine: str = "edge",
    voice_name: str = "nanami",
    paid_gemini_api_key: str = "",
    tts_params: Optional[dict] = None
) -> Dict[str, Any]:
    """
    指定された scene_id のカットのみを単体で再生成し、リカバリーする関数。
    """
    from services.firestore_service import FirestoreService
    firestore = FirestoreService()

    job_dir = config.TMP_DIR / job_id
    project_json_path = job_dir / "project.json"
    if not project_json_path.exists():
        raise FileNotFoundError(f"Project state for job '{job_id}' not found.")

    with open(project_json_path, "r", encoding="utf-8") as f:
        project_data = json.load(f)

    scenes = project_data.get("scenes", [])
    target_idx = None
    for idx, s in enumerate(scenes):
        if int(s.get("scene_id", 0)) == int(scene_id):
            target_idx = idx
            break

    if target_idx is None:
        raise ValueError(f"Scene ID {scene_id} not found in job {job_id}.")

    scene_data = scenes[target_idx]
    if custom_prompt:
        scene_data["character_prompt"] = custom_prompt
        scene_data["description"] = custom_prompt

    assets_dir = job_dir / "assets"
    batch_gen = BatchAssetGenerator()

    scene_dict = {
        "scene_number": scene_id,
        "speaker": scene_data.get("speaker", "ナレーション"),
        "narration": scene_data.get("narration", ""),
        "character_prompt": scene_data.get("character_prompt", ""),
        "visual_description": scene_data.get("description", ""),
        "bgm_tag": scene_data.get("bgm_tag", "neutral"),
        "duration_seconds": scene_data.get("duration", 5.0)
    }

    asset_res = await batch_gen.generate_single_scene_assets(
        scene_data=scene_dict,
        output_dir=assets_dir,
        tts_engine=tts_engine,
        voice_name=voice_name,
        tts_params=tts_params,
        paid_gemini_api_key=paid_gemini_api_key
    )

    scene_data["status"] = "generated"
    scenes[target_idx] = scene_data
    project_data["scenes"] = scenes

    with open(project_json_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, ensure_ascii=False, indent=2)

    # Firestoreのジョブドキュメントも差分更新
    firestore.update_job(job_id, scenes=scenes)

    return {
        "success": True,
        "job_id": job_id,
        "scene_id": scene_id,
        "status": "generated",
        "asset": asset_res
    }
