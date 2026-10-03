"""
KIMIDORI Movie Auto - Script Normalizer Engine
直接入力されたテキスト、アップロードされたファイル、Google Driveから取得したドキュメント等の
任意の形式の台本を、当ツール専用の厳格なタイムラインカット割りJSON（フォーマット固定化）へ
Geminiを用いて自動変換・リライトする。
"""

import json
import re
import logging
from typing import Dict, Any, List, Optional

import config
from utils.key_manager import KeyManager

logger = logging.getLogger(__name__)


class ScriptNormalizer:
    """外部台本を当ツールの標準タイムラインJSONフォーマットへ固定化・リライトするエンジン"""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])

    async def normalize_to_timeline_json(
        self,
        raw_text: str,
        target_format: str = "pro_shorts",
        genre: str = "knowledge",
        speaking_rate: float = 1.0
    ) -> Dict[str, Any]:
        """
        raw_text を解析し、当ツール専用の厳格なタイムラインJSONへリライト変換する。
        - target_format: 'pro_shorts' (60秒・全6〜7カット・全カット動画演出) または
                         'long_video' (15分・章構造・全カット演出)
        """
        if not raw_text or not raw_text.strip():
            raise ValueError("台本テキストが空です。")

        if target_format == "pro_shorts":
            prompt = f"""
あなたは動画制作のプロフェッショナルです。
以下の入力された任意のテキスト・台本・メモ・外部資料を、当ツールの【Pro版ショート動画（厳格な60秒・全6〜7カット・全カット動画演出）専用のタイムラインJSON】へ完全にリライト・正規化してください。

【対象の元台本/資料】:
{raw_text[:4000]}

【リライトの厳格ルール】:
1. 時間設計: 全6〜7カット、各カットは8〜10秒、合計55〜60秒に厳密に収めること。
2. 構成:
   - Cut_001 (00:00〜00:09): 冒頭3秒で視聴者の手を止める強烈なフック。
   - Cut_002〜Cut_005: 疑問の深掘り、具体的ファクト、予想を裏切る展開。
   - Cut_006〜Cut_007: 納得のオチ・教訓、フォロー・いいねへの誘導。
3. ト書き (description): 画像・動画生成AIが忠実に描画できるよう、被写体の表情・ポーズ・背景・照明・構図を具体的に描写すること（※「佐藤さん」等の安易な固定名は禁止）。
4. セリフ (dialogue): 1カットあたり最大2〜3文（約30〜45文字）。早口にならず自然に伝わる文字量に調整すること。
5. カメラ演出 (camera_effect): 全カット「動画 (アクション)」または「動画 (ズームイン)」「動画 (パン)」などの動画演出を指定すること。
6. BGM (bgm_tag): cheerful / warm / touching / suspense / frightening / funny / epic / neutral から適切なものを1つ選択。

【出力フォーマット (厳格なJSON)】:
必ず以下のJSON形式のみを出力してください（```json ``` で囲んでください）。
{{
  "title": "動画タイトル",
  "theme": "主要テーマ",
  "genre": "{genre}",
  "target_duration_seconds": 60,
  "cuts": [
    {{
      "cut_id": "Cut_001",
      "time_range": "[00:00 - 00:09]",
      "speaker": "ナレーション（または 話者名）",
      "dialogue": "セリフまたは発話内容",
      "description": "映像の情景・キャラクターの動作・背景・ライティングの詳細説明",
      "camera_effect": "動画 (ズームイン)",
      "bgm_tag": "suspense"
    }}
  ]
}}
"""
        else:
            prompt = f"""
あなたは長尺動画（15分）のプロフェッショナル構成作家です。
以下の入力されたテキスト・資料を、当ツールの【長尺漫画・解説動画（15分・全5章構成）専用のタイムラインJSON】へリライト・正規化してください。

【対象の元台本/資料】:
{raw_text[:6000]}

【リライトの厳格ルール】:
1. 構成: 全5章（オープニング、展開1、展開2、解決/クライマックス、まとめエンディング）。
2. カット設計: 1カットあたり3〜8秒、テンポの良い対話と解説で構成すること。
3. ト書き (description): 場面の情景、登場人物の感情・動作、背景を具体的に描写すること。
4. カメラ演出 (camera_effect): zoom_in / zoom_out / pan_left / pan_right / static / video_action から選択。
5. BGM (bgm_tag): 場面の雰囲気に合わせて指定。

【出力フォーマット (厳格なJSON)】:
必ず以下のJSON形式のみを出力してください（```json ``` で囲んでください）。
{{
  "title": "長尺動画タイトル",
  "theme": "テーマ",
  "genre": "{genre}",
  "target_minutes": 15,
  "chapters": [
    {{
      "chapter_num": 1,
      "title": "第1章タイトル",
      "cuts": [
        {{
          "cut_id": "Cut_001",
          "time_range": "[00:00 - 00:06]",
          "speaker": "話者名",
          "dialogue": "セリフ",
          "description": "画面の情景描写",
          "camera_effect": "zoom_in",
          "bgm_tag": "suspense"
        }}
      ]
    }}
  ]
}}
"""

        models_to_try = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash"]
        import aiohttp

        async def _call(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.65, "maxOutputTokens": 8192}
                }
                for m in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        continue
            raise RuntimeError("Gemini台本リライトAPIの呼び出しに失敗しました。")

        raw_res = await self.key_manager.execute_with_retry_async(_call)
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_res, re.DOTALL)
        json_str = m.group(1) if m else raw_res
        try:
            return json.loads(json_str)
        except Exception:
            clean = json_str.strip()
            if not clean.endswith("}"):
                clean += "\n]}"
            return json.loads(clean)
