"""
KIMIDORI Movie Auto - 長尺動画自動生成システム 完全仕様エンジン
15〜20分の長尺動画（全5章・120〜180カット）を安定生成。
メモリ圧迫防止の1カット小分け動画化 ＆ 音声先行計測（音ズレ防止） ＆ 人物領域自動検知吹き出し配置
"""

import os
import re
import json
import logging
import asyncio
import subprocess
import tempfile
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps

import config
from utils.key_manager import KeyManager
from utils.ffmpeg_utils import get_audio_duration, get_video_info
from processors.storyboard_generator import StoryboardAnalyzer

logger = logging.getLogger(__name__)

# ジャンル別プロンプト指示
GENRE_SPECS = {
    "story": {
        "label": "ストーリー・ドラマ・スカッと漫画",
        "description": "会話劇中心。主人公と周囲のリアルなセリフ展開。解説者なし。",
        "style_prefix": "vibrant Japanese manga anime style, expressive character acting, dramatic lighting, high detail"
    },
    "business": {
        "label": "ビジネス・教養・経済・洋書解説",
        "description": "ナレーション主導。論理的で分かりやすいデータ・図解・多彩な実例。",
        "style_prefix": "modern clean infographic style, professional illustration, sleek minimalist design, 8k"
    },
    "edoculture": {
        "label": "歴史・江戸文化・浮世絵雑学",
        "description": "情緒あふれる江戸の風景と歴史解説。現代描写を完全排除。",
        "style_prefix": "authentic Japanese ukiyoe woodblock print, Edo period aesthetic, traditional texture, masterpiece"
    },
    "trivia": {
        "label": "雑学・ミステリー・サイエンス",
        "description": "知的好奇心を刺激するフックと驚きの事実の連続解説。",
        "style_prefix": "cinematic documentary style, dramatic contrast, highly detailed atmosphere, 4k"
    }
}


class LongVideoEngine:
    """長尺動画（15〜20分）完全仕様生成エンジン"""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])
        self.storyboard_analyzer = StoryboardAnalyzer()

    # -------------------------------------------------------------------------
    # 1. 情報収集と台本の作成 (全5章・120〜180カット)
    # -------------------------------------------------------------------------
    async def generate_long_script(
        self,
        theme: str,
        genre: str = "story",
        target_minutes: int = 15,
        research_notes: str = ""
    ) -> Dict[str, Any]:
        """
        題材やリサーチメモから、1場面3〜8秒のセリフと状況説明からなる台本を作成。
        同時に登場人物の英語指示文一覧表（容姿統一）を作成。
        """
        genre_spec = GENRE_SPECS.get(genre, GENRE_SPECS["story"])
        target_cuts = max(80, min(180, int(target_minutes * 8)))

        prompt = f"""
あなたはYouTubeで100万再生を連発する長尺動画（{target_minutes}分動画）のプロ脚本家・構成作家です。
以下の条件に従い、全5章からなる本格的な長尺動画台本と、登場人物の英語指示文一覧表（キャラクターシート）を作成してください。

【テーマ】: {theme}
【ジャンル】: {genre_spec['label']}（{genre_spec['description']}）
【目標尺】: 約{target_minutes}分（合計 {target_cuts} カット程度、1カットあたり3〜8秒程度）
【参考リサーチメモ】: {research_notes or '特になし（あなたの豊富な知識から最新の知見と大ヒット構成を展開してください）'}

【出力フォーマット（厳密なJSON）】:
必ず以下のJSON形式のみを出力してください（Markdownコードブロック ```json ``` で囲んでください）。
{{
  "title": "動画のタイトル",
  "theme": "{theme}",
  "genre": "{genre}",
  "characters": [
    {{
      "name": "登場人物の名前（例: 佐藤、健一、ナレーター）",
      "role": "主人公 / 同僚 / 妻 / ナレーター など",
      "appearance_prompt_en": "英語の外見・服装指示（例: a 28-year-old Japanese male office worker, short black hair, wearing a navy business suit and tie, neat appearance, anime style）"
    }}
  ],
  "main_locations": [
    {{
      "name": "オフィス / 自宅リビング / 街頭 など",
      "location_prompt_en": "英語の舞台背景指示（例: modern Tokyo office interior, desk with computer, daylight streaming through window）"
    }}
  ],
  "chapters": [
    {{
      "chapter_num": 1,
      "chapter_title": "章のタイトル",
      "cuts": [
        {{
          "cut_id": "Cut_001",
          "speaker": "話者名（ナレーション または 登場人物名）",
          "dialogue": "セリフまたはナレーション本文（1場面あたり20〜60文字程度、3〜8秒で話せる長さ）",
          "description": "ト書き（画面の状況、人物の表情や動作、場所）",
          "bgm_tag": "cheerful / warm / touching / suspense / frightening / funny / epic / neutral から選択",
          "camera_effect": "固定 / ズームイン / パン左 / パン右 / 動画(アクション)",
          "is_video_cut": true または false（冒頭の約10箇所や重要シーンのみtrue、基本はfalse）
        }}
      ]
    }}
  ]
}}
"""
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
        import aiohttp

        async def _call_gemini(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.75, "maxOutputTokens": 8192}
                }
                for model in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=60) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        continue
            raise RuntimeError("長尺台本のGemini生成呼び出しに失敗しました")

        raw_text = await self.key_manager.execute_with_retry_async(_call_gemini)
        
        # JSON抽出
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        json_str = m.group(1) if m else raw_text
        try:
            script_data = json.loads(json_str)
        except Exception:
            # 括弧のバランス等簡易修正
            clean = json_str.strip()
            if not clean.endswith("}"):
                clean += "\n}]}]}"
            script_data = json.loads(clean)

        return script_data

    # -------------------------------------------------------------------------
    # 2. 音声の先行作成と絵コンテ確定（音ズレ根本防止）
    # -------------------------------------------------------------------------
    async def measure_speech_durations(
        self,
        cuts: List[Dict[str, Any]],
        output_dir: Path,
        tts_engine: str = "edge",
        voice_map: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        セリフごとの音声合成を先行実行し、実際の再生時間をミリ秒単位で測定して確定秒数を記録する
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        import edge_tts

        for idx, cut in enumerate(cuts):
            dialogue = cut.get("dialogue", "").strip()
            audio_path = output_dir / f"{cut['cut_id']}_speech.mp3"
            
            if not dialogue:
                # 無音の場合はデフォルト4.0秒
                cut["audio_path"] = None
                cut["exact_duration"] = 4.0
                continue

            # 音声合成（Edge TTS / Nanami または指定ボイス）
            speaker = cut.get("speaker", "ナレーション")
            voice = voice_map.get(speaker, "ja-JP-NanamiNeural") if voice_map else "ja-JP-NanamiNeural"
            
            communicate = edge_tts.Communicate(dialogue, voice)
            await communicate.save(str(audio_path))

            # 正確な秒数をFFprobeでミリ秒計測
            duration = get_audio_duration(audio_path)
            # 音声の余白0.4秒を付与
            exact_duration = max(2.5, round(duration + 0.4, 2))

            cut["audio_path"] = str(audio_path)
            cut["exact_duration"] = exact_duration

        return cuts

    # -------------------------------------------------------------------------
    # 3. 画像認識による文字枠・吹き出しの自動配置（顔・人物重心検知）
    # -------------------------------------------------------------------------
    def auto_layout_caption(
        self,
        base_image_path: Path,
        output_path: Path,
        speaker: str,
        dialogue: str,
        description: str = ""
    ) -> Path:
        """
        画像の中から人物の領域を測定し、人物がいない最も広い空間に文字枠を配置。
        人物が右→左に配置、左→右に配置。
        セリフは丸い吹き出し枠、状況説明は上下の長方形枠。
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(base_image_path).convert("RGBA")
        width, height = img.size

        # 人物重心の推定（輝度・カラー分散解析による左右判定）
        gray = img.convert("L")
        left_box = (0, int(height * 0.2), int(width * 0.5), int(height * 0.8))
        right_box = (int(width * 0.5), int(height * 0.2), width, int(height * 0.8))

        left_stat = ImageOps.invert(gray.crop(left_box)).getextrema()
        right_stat = ImageOps.invert(gray.crop(right_box)).getextrema()

        # 右側の方が被写体・人物コントラストが高い場合は人物が右側にいると判定
        person_on_right = (right_stat[1] >= left_stat[1])

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # フォント設定
        font_path = "C:\\Windows\\Fonts\\msgothic.ttc"
        try:
            font_speech = ImageFont.truetype(font_path, int(height * 0.038))
            font_speaker = ImageFont.truetype(font_path, int(height * 0.032))
        except Exception:
            font_speech = ImageFont.load_default()
            font_speaker = ImageFont.load_default()

        is_narration = speaker in ["ナレーション", "語り", "解説", "ナレーター"]

        if is_narration:
            # 状況説明・解説: 画面下部（または上部）の長方形枠
            box_height = int(height * 0.16)
            box_y0 = int(height * 0.80)
            box_y1 = box_y0 + box_height

            # 半透明ダーク長方形背景
            draw.rectangle([(int(width * 0.05), box_y0), (int(width * 0.95), box_y1)], fill=(15, 23, 42, 220), outline=(255, 255, 255, 200), width=2)
            
            # テキスト描画（白文字＋影）
            draw.text((int(width * 0.08), box_y0 + int(box_height * 0.25)), dialogue, fill=(255, 255, 255, 255), font=font_speech)
        else:
            # セリフ: 丸い吹き出し枠（人物の逆側へ配置）
            bubble_w = int(width * 0.42)
            bubble_h = int(height * 0.26)

            bubble_x0 = int(width * 0.06) if person_on_right else int(width * 0.52)
            bubble_y0 = int(height * 0.12)
            bubble_x1 = bubble_x0 + bubble_w
            bubble_y1 = bubble_y0 + bubble_h

            # 白い丸角吹き出し（縁取り付き）
            draw.rounded_rectangle([(bubble_x0, bubble_y0), (bubble_x1, bubble_y1)], radius=20, fill=(255, 255, 255, 240), outline=(30, 41, 59, 255), width=3)
            
            # 話者名バッジ
            badge_w = int(len(speaker) * int(height * 0.035) + 20)
            badge_h = int(height * 0.045)
            draw.rounded_rectangle([(bubble_x0 + 10, bubble_y0 - int(badge_h * 0.5)), (bubble_x0 + 10 + badge_w, bubble_y0 + int(badge_h * 0.5))], radius=8, fill=(16, 185, 129, 255))
            draw.text((bubble_x0 + 20, bubble_y0 - int(badge_h * 0.45)), speaker, fill=(255, 255, 255, 255), font=font_speaker)

            # セリフテキスト（黒文字、折り返し）
            max_chars = 14
            lines = [dialogue[i:i+max_chars] for i in range(0, len(dialogue), max_chars)]
            line_y = bubble_y0 + 35
            for line in lines:
                draw.text((bubble_x0 + 20, line_y), line, fill=(15, 23, 42, 255), font=font_speech)
                line_y += int(height * 0.048)

        # 合成
        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        final_img.save(output_path, "JPEG", quality=95)
        return output_path

    # -------------------------------------------------------------------------
    # 4. カットごとの小分け動画化 ＆ 全体の無劣化一瞬結合
    # -------------------------------------------------------------------------
    def render_single_cut_video(
        self,
        cut: Dict[str, Any],
        image_path: Path,
        audio_path: Optional[Path],
        output_cut_video: Path,
        duration: float,
        camera_effect: str = "固定"
    ) -> Path:
        """
        1カット分の映像（静止画＋Ken Burnsパン/ズーム＋音声）を短尺動画としてレンダリング保存。
        メモリ圧迫・クラッシュを防ぐ小分け設計。
        """
        output_cut_video.parent.mkdir(parents=True, exist_ok=True)
        img_str = str(image_path).replace("\\", "/")

        # カメラワークフィルター
        if "ズームイン" in camera_effect:
            vf = f"scale=1920:1080,zoompan=z='min(zoom+0.0015,1.15)':d={int(duration*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=25"
        elif "パン" in camera_effect:
            vf = f"scale=1920:1080,zoompan=z=1.1:d={int(duration*25)}:x='if(lte(on,1),(iw-iw/zoom)/2,x+1)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=25"
        else:
            vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

        if audio_path and Path(audio_path).exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(image_path),
                "-i", str(audio_path),
                "-t", str(duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                str(output_cut_video)
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(image_path),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                str(output_cut_video)
            ]

        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_cut_video

    def concat_all_cuts(
        self,
        cut_video_paths: List[Path],
        output_video_path: Path,
        bgm_path: Optional[Path] = None
    ) -> Path:
        """
        FFmpeg concat demuxerを用いて、全小分けカット動画を無劣化・一瞬で連結。
        BGMがある場合は自動音量調整（ダッキング）して合成。
        """
        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        list_txt = output_video_path.parent / "concat_list.txt"
        
        with open(list_txt, "w", encoding="utf-8") as f:
            for p in cut_video_paths:
                f.write(f"file '{p.name}'\n")

        raw_concat = output_video_path.parent / "raw_concat.mp4"
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_txt),
            "-c", "copy",
            str(raw_concat)
        ]
        subprocess.run(cmd_concat, cwd=output_video_path.parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        if bgm_path and Path(bgm_path).exists():
            # BGMをループ＋小音量 (0.15) でミックス
            cmd_mix = [
                "ffmpeg", "-y",
                "-i", str(raw_concat),
                "-stream_loop", "-1", "-i", str(bgm_path),
                "-filter_complex", "[1:a]volume=0.15[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(output_video_path)
            ]
            subprocess.run(cmd_mix, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        else:
            if raw_concat != output_video_path:
                import shutil
                shutil.copy2(raw_concat, output_video_path)

        return output_video_path
