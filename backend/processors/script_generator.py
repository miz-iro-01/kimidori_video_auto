"""
Gemini API を使った台本生成モジュール
テーマから構造化された動画台本を自動生成する
"""

import json
import logging
import asyncio
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
        self.primary_model_name = config.GEMINI_MODEL
        self.fallback_models = config.GEMINI_FALLBACK_MODELS

    async def _try_generate(self, prompt: str, generation_config: dict) -> str:
        """フォールバックモデルを含めてGemini APIを呼び出す"""
        # まずプライマリモデルを先頭に、重複を除いたモデルリストを作成
        models_to_try = [self.primary_model_name]
        for m in self.fallback_models:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = None
        for model_name in models_to_try:
            model = genai.GenerativeModel(model_name)
            # 各モデルで最大2回リトライ
            for attempt in range(2):
                try:
                    logger.info(f"Gemini API呼び出し: model={model_name} (attempt {attempt+1})")
                    response = await model.generate_content_async(
                        prompt,
                        generation_config=generation_config
                    )
                    return response.text.strip()
                except Exception as e:
                    last_error = e
                    if "429" in str(e):
                        if attempt == 0:
                            logger.warning(f"モデル {model_name} で429エラー、{10}秒後にリトライ...")
                            await asyncio.sleep(10)
                        else:
                            logger.warning(f"モデル {model_name} のクォータ枯渇、次のモデルへフォールバック")
                            break  # 次のモデルへ
                    else:
                        raise  # 429以外のエラーはそのままraise

        # 全モデル試してもダメだった場合
        raise Exception(
            f"全てのGeminiモデル ({', '.join(models_to_try)}) でクォータ制限に達しました。"
            f"しばらく時間をおいてから再試行するか、Google AI Studioで課金設定をご確認ください。"
            f"\n最後のエラー: {last_error}"
        )

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
            "text_overlay": "画面にテロップとして表示するテキスト（ナレーションとほぼ同じ内容で、音声なしでも内容が理解できるようにすること。必要に応じて改行 '\\n' を入れる）",
            "duration_seconds": 5
        }}
    ]
}}

ルール:
- シーンは5〜8個程度
- 各シーンのナレーションは自然な日本語で
- text_overlay はナレーションの内容をそのまま、あるいは視聴者が読みやすいように整えたテロップテキストにすること。絶対に「シーン1」などの文字は含めないこと。
- search_query はPexels等のフリー素材サイトで検索できる一般的な英語のキーワードにすること
- 全シーンの duration_seconds の合計が {duration_seconds} 秒程度になるようにする
- 冒頭は視聴者の注意を引くフック、最後はまとめで締める
"""

        try:
            generation_config = {
                "response_mime_type": "application/json"
            }
            text = await self._try_generate(prompt, generation_config)

            # JSONブロックを抽出（念のためのフォールバック処理）
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

