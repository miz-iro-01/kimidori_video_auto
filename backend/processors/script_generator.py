"""
Gemini API を使った台本生成モジュール
テーマから構造化された動画台本を自動生成する
"""

import json
import logging
from typing import Optional

import google.generativeai as genai
import config

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """Gemini APIを使用して動画の台本を生成する（ユーザーの無料APIキーを使用）"""

    def __init__(self, api_key: str = ""):
        """
        Args:
            api_key: ユーザーが持ち込むGemini APIキー（無料枠で取得可能）
        """
        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise ValueError("Gemini APIキーが設定されていません。設定画面でAPIキーを入力してください。")
        genai.configure(api_key=key)
        self.model = genai.GenerativeModel(config.GEMINI_MODEL)

    async def generate(
        self,
        theme: str,
        style: str = "informative",
        duration_seconds: int = 45,
    ) -> dict:
        """
        テーマから動画台本を生成する

        Args:
            theme: 動画のテーマ
            style: 動画のスタイル（informative / entertaining / tutorial）
            duration_seconds: 目標の動画長さ（秒）

        Returns:
            dict: 構造化された台本データ
            {
                "title": "動画タイトル",
                "description": "動画の説明文",
                "tags": ["タグ1", "タグ2"],
                "scenes": [
                    {
                        "scene_number": 1,
                        "narration": "ナレーションテキスト",
                        "visual_description": "表示する画像の説明",
                        "search_query": "画像検索用の英単語",
                        "text_overlay": "画面に表示するテロップ",
                        "duration_seconds": 5
                    },
                    ...
                ]
            }
        """
        # 1文字あたり約0.15秒（日本語の読み上げ速度）で概算
        total_chars = int(duration_seconds / 0.15)

        prompt = f"""あなたはYouTubeショート動画の台本作家です。
以下のテーマで、{duration_seconds}秒程度のショート動画の台本をJSON形式で出力してください。

【テーマ】: {theme}
【スタイル】: {style}
【目標の長さ】: {duration_seconds}秒（ナレーション合計で約{total_chars}文字）

以下のJSON形式で出力してください（JSON以外のテキストは含めないでください）:
{{
    "title": "動画のタイトル（キャッチーで興味を引くもの）",
    "description": "YouTubeの動画説明文（100文字程度）",
    "tags": ["関連タグ1", "関連タグ2", "関連タグ3", "関連タグ4", "関連タグ5"],
    "scenes": [
        {{
            "scene_number": 1,
            "narration": "このシーンのナレーションテキスト",
            "visual_description": "このシーンで表示すべきビジュアルの説明",
            "search_query": "このシーンに合う背景画像を探すための英単語（1〜2語。例: business, sunset, technology, happy person）",
            "text_overlay": "画面に大きく表示するキーワードやテロップ（短く）",
            "duration_seconds": 5
        }}
    ]
}}

ルール:
- シーンは5〜8個程度
- 各シーンのナレーションは自然な日本語で
- text_overlay は各シーン5〜15文字程度の短いキーワード
- search_query はPexels等のフリー素材サイトで検索できる一般的な英語のキーワードにすること
- 全シーンの duration_seconds の合計が {duration_seconds} 秒程度になるようにする
- 冒頭は視聴者の注意を引くフック、最後はまとめで締める
"""

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()

            # JSONブロックを抽出（```json ... ``` で囲まれている場合に対応）
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            script_data = json.loads(text)

            # バリデーション
            assert "title" in script_data, "タイトルがありません"
            assert "scenes" in script_data, "シーンがありません"
            assert len(script_data["scenes"]) > 0, "シーンが空です"

            logger.info(
                f"台本生成完了: '{script_data['title']}' "
                f"({len(script_data['scenes'])}シーン)"
            )

            return script_data

        except json.JSONDecodeError as e:
            logger.error(f"台本のJSON解析に失敗: {e}\nレスポンス: {text[:500]}")
            raise ValueError(f"Geminiからの応答をJSON解析できませんでした: {e}")
        except Exception as e:
            logger.error(f"台本生成に失敗: {e}")
            raise
