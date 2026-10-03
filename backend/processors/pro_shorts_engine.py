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

    async def generate_pro_shorts_script(
        self,
        theme: str,
        genre: str = "story",
        research_context: Optional[str] = None,
        outlier_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        60秒尺（全6〜7カット・各8〜10秒・全カット動画演出）の高密度台本をGeminiで生成。
        外部リサーチデータ・隠れ需要インサイトを注入し、安易なステレオタイプ（偏り）を完全排除する。
        """
        genre_info = PRO_SHORTS_GENRES.get(genre, PRO_SHORTS_GENRES["story"])

        # リサーチコンテキストがない場合、Outlierリサーチを自動実行
        dynamic_research_section = ""
        if research_context:
            dynamic_research_section = f"\n【一次情報・リサーチデータ】:\n{research_context}\n"
        elif outlier_data:
            insight = outlier_data.get("hidden_demand_insight", "")
            hooks = outlier_data.get("proven_hooks", [])
            forbidden = outlier_data.get("forbidden_tropes", [])
            dynamic_research_section = (
                f"\n【外れ値（Outlier）ヒット動画から抽出された隠れ需要】:\n{insight}\n"
                f"【実証済みフック参考】: {', '.join(hooks)}\n"
                f"【使用禁止ステレオタイプ】: {', '.join(forbidden)}\n"
            )
        else:
            try:
                from processors.outlier_research_engine import OutlierResearchEngine
                outlier_engine = OutlierResearchEngine(key_manager=self.key_manager)
                videos = outlier_engine.search_outlier_topics(theme, limit=4)
                analysis = await outlier_engine.analyze_and_extract_hidden_angles(theme, videos, genre)
                insight = analysis.get("hidden_demand_insight", "")
                hooks = analysis.get("proven_hooks", [])
                forbidden = analysis.get("forbidden_tropes", [])
                dynamic_research_section = (
                    f"\n【外れ値（Outlier）リアルタイム検索結果から抽出された隠れ需要】:\n{insight}\n"
                    f"【実証済みフック参考】: {', '.join(hooks)}\n"
                    f"【使用禁止ステレオタイプ】: {', '.join(forbidden)}\n"
                )
            except Exception as e:
                logger.warning(f"自動Outlierリサーチスキップ: {e}")

        prompt = f"""
あなたはYouTube ShortsやTikTokで100万回再生を連発するショート動画のトッププロデューサーです。
以下のテーマとリサーチ情報に基づき、厳密に【60秒尺（全6〜7カット、各8〜10秒、合計55〜60秒）】の超高エンゲージメント動画台本を作成してください。

【テーマ】: {theme}
【ジャンル】: {genre_info['name']}
{dynamic_research_section}
【演出ルール】:
{genre_info['rule']}
・全カット【演出】：動画（ダイナミック動画演出）として構成すること。
・各カットは8〜10秒程度（全6〜7カットで合計55〜60秒）。
・【最重要厳守】：定番の使い古されたステレオタイプ（江戸＝うんち換金、都市伝説＝頭の上の余命数字、ビジネス＝45歳佐藤さん等）は【絶対に使用禁止】。一次情報・独自の意外なファクトに基づいて展開すること。

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
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
        ]
        import aiohttp

        async def _call(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                # ユーザーのAPIキーで利用可能なモデル一覧を動的取得
                active_models = list(models_to_try)
                try:
                    async with session.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=10) as m_resp:
                        if m_resp.status == 200:
                            m_data = await m_resp.json()
                            supported = [
                                m["name"].replace("models/", "")
                                for m in m_data.get("models", [])
                                if "generateContent" in m.get("supportedGenerationMethods", [])
                            ]
                            if supported:
                                # 利用可能モデルの中から優先順序で並び替え
                                prioritized = [m for m in ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-2.5-pro"] if m in supported]
                                other_flashes = [m for m in supported if "flash" in m.lower() and m not in prioritized]
                                other_supported = [m for m in supported if m not in prioritized and m not in other_flashes]
                                active_models = prioritized + other_flashes + other_supported
                except Exception as ex:
                    logger.warning(f"利用可能モデル動的取得スキップ: {ex}")

                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.75, "maxOutputTokens": 4096}
                }
                last_err = "No response"
                for model in active_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                            else:
                                err_txt = await resp.text()
                                last_err = f"Model {model} returned HTTP {resp.status}: {err_txt[:120]}"
                                logger.warning(f"Pro shorts Gemini API fail: {last_err}")
                    except Exception as ex:
                        last_err = str(ex)
                        continue
            raise RuntimeError(f"Pro版ショート台本の生成に失敗しました: {last_err}")

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
