"""
KIMIDORI Movie Auto - Pro版ショート動画生成エンジン
portable-video-studio のノウハウ（全6〜7カット・合計55〜60秒・全カット動画/アニメーション演出）を完全移植
有料Gemini APIによる高エンゲージメントショート動画の自動生成
"""

import os
import re
import json
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from utils.key_manager import KeyManager
from utils.ffmpeg_utils import get_audio_duration

logger = logging.getLogger(__name__)

PRO_SHORTS_GENRES = {
    "story": {
        "name": "ストーリー・ドラマ・スカッと",
        "description": "テンポの良いリアルな会話劇。冒頭3秒の衝撃展開からスタート。",
        "rule": "主人公によるリアルなストーリー展開。全カット動画演出。"
    },
    "business": {
        "name": "ビジネス・教養・ノウハウ",
        "description": "冒頭3秒で『9割の人が勘違いしている〇〇の真実』など強烈なフック。",
        "rule": "ナレーターによる論理的で痛快な知的ショート解説。全カット動画演出。"
    },
    "edoculture": {
        "name": "歴史・江戸文化・浮世絵雑学",
        "description": "江戸情緒ある浮世絵アニメーションとテンポの良い歴史雑学解説。",
        "rule": "現代キャラ排除。浮世絵アニメーションと純粋な知的好奇心解説。"
    },
    "trivia": {
        "name": "雑学・ミステリー・驚きの事実",
        "description": "視聴者の手をピタッと止める常識覆し系ショート解説。",
        "rule": "テンポの良い疑問提示と即座の解説。ダイナミック演出。"
    }
}


class ProShortsEngine:
    """Pro版ショート動画（60秒・5〜6本のアニメーション/動画連結）生成エンジン"""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])

    async def generate_pro_shorts_script(self, theme: str, genre: str = "story") -> Dict[str, Any]:
        """
        60秒尺（全6〜7カット・各8〜10秒・全カット動画演出）の高密度台本をGeminiで生成
        """
        genre_info = PRO_SHORTS_GENRES.get(genre, PRO_SHORTS_GENRES["story"])

        prompt = f"""
あなたはYouTube ShortsやTikTokで100万回再生を連発するショート動画のトッププロデューサーです。
以下のテーマで、厳密に【60秒尺（全6〜7カット、各8〜10秒、合計55〜60秒）】の超高エンゲージメント動画台本を作成してください。

【テーマ】: {theme}
【ジャンル】: {genre_info['name']}
【演出ルール】:
{genre_info['rule']}
・全カット【演出】：動画（ダイナミック動画演出）として構成すること。
・各カットは8〜10秒程度（全6〜7カットで合計55〜60秒）。

【出力フォーマット（厳格なJSON）】:
必ず以下のJSON形式のみを出力してください（```json ``` で囲んでください）。
{{
  "title": "ショート動画タイトル",
  "theme": "{theme}",
  "genre": "{genre}",
  "target_duration_seconds": 60,
  "cuts": [
    {{
      "cut_id": "Cut_001",
      "time_range": "[00:00 - 00:09]",
      "speaker": "話者名（または ナレーション）",
      "dialogue": "セリフまたは発話テキスト（冒頭3秒で引き込むフック）",
      "description": "画面の情景・被写体のアクション・背景描写",
      "camera_effect": "動画 (アクション)",
      "bgm_tag": "cheerful / warm / touching / suspense / frightening / funny / epic / neutral から選択"
    }}
  ]
}}
"""
        models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
        import aiohttp

        async def _call(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.75, "maxOutputTokens": 4096}
                }
                for model in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        continue
            raise RuntimeError("Pro版ショート台本の生成に失敗しました")

        raw_text = await self.key_manager.execute_with_retry_async(_call)

        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        json_str = m.group(1) if m else raw_text
        try:
            return json.loads(json_str)
        except Exception:
            clean = json_str.strip()
            if not clean.endswith("}"):
                clean += "\n]}"
            return json.loads(clean)
