"""
KIMIDORI Movie Auto - 長尺・長尺漫画風動画台本生成モジュール
Gemini API および KeyManager を利用し、原案からコマ割り・ナレーション・シーン別BGM指定タグ付きJSON台本を生成する
"""

import json
import logging
import asyncio
import re
from typing import List, Dict, Any, Optional, Union

import google.generativeai as genai
import config
from utils.key_manager import KeyManager, NoAPIKeysAvailableError

logger = logging.getLogger(__name__)

# BGM感情タグの標準定義
VALID_BGM_TAGS = [
    "cheerful",      # 明るい・ポップ
    "warm",          # ほのぼの・温かい・日常
    "touching",      # 感動・泣ける・しんみり
    "suspense",      # スリル・不穏・緊張
    "frightening",   # 恐怖・ホラー
    "funny",         # コミカル・ギャグ
    "epic",          # 壮大・クライマックス
    "neutral"        # 静か・標準
]

DEFAULT_MANGA_PROMPT_TEMPLATE = """
あなたはプロの漫画原作者・動画演出家です。
以下の【原案テキスト】を元に、日本のYouTube長尺動画（スカッと話、スカッと漫画、感動ドラマ風など）として最適な長尺漫画風シナリオのコマ割り・台本・演出データを生成してください。

【原案テキスト】
{original_text}

【条件】
1. ストーリーの展開・感情の変化に合わせて、各シーン/コマに最適な感情タグ (`bgm_tag`) を必ず指定してください。
   使用可能な `bgm_tag` 一覧: {bgm_tags}
2. 各シーンの `narration` は自然な日本語で記述してください。
3. 各シーンの `character_prompt` は、画像生成AIで一貫性のある漫画スタイル画像を生成するための英語プロンプト（例: "A Japanese 20s woman, sad expression, rainy street, anime manga style"）にしてください。
4. 目安シーン数: {target_scene_count} コマ程度。

以下の正確なJSON形式のみで出力してください（マークダウンの装飾や余計な解説テキストは一切含めないでください）。

{{
  "title": "キャッチーな動画タイトル",
  "description": "動画の概要説明文（100〜200文字）",
  "bgm_summary": ["全体で使用される主なBGMタグのリスト"],
  "scenes": [
    {{
      "scene_number": 1,
      "speaker": "ナレーション または キャラクター名",
      "narration": "このコマで流れる台本・セリフ・ナレーション",
      "visual_description": "画面のビジュアル・コマ演出の説明（日本語）",
      "character_prompt": "English image prompt for anime manga style scene",
      "bgm_tag": "warm",
      "duration_seconds": 6
    }}
  ]
}}
"""


class MangaScriptGenerator:
    """
    Gemini API と KeyManager を組み合わせた長尺・長尺漫画風動画台本生成クラス
    """

    def __init__(
        self,
        key_manager: Optional[KeyManager] = None,
        api_keys: Optional[Union[List[str], str]] = None
    ):
        """
        Args:
            key_manager: 既存のKeyManagerインスタンス（指定なき場合はapi_keysから作成）
            api_keys: キーのリストまたは文字列（key_managerが未指定の場合に使用）
        """
        if key_manager:
            self.key_manager = key_manager
        elif api_keys:
            self.key_manager = KeyManager(api_keys)
        else:
            # デフォルトで config.GEMINI_API_KEY を使用
            default_key = config.GEMINI_API_KEY
            if not default_key:
                raise NoAPIKeysAvailableError("Gemini APIキーが設定されていません。")
            self.key_manager = KeyManager([default_key])

        self.primary_model_name = config.GEMINI_MODEL
        self.fallback_models = config.GEMINI_FALLBACK_MODELS

    def _clean_json_string(self, text: str) -> str:
        """レスポンス文字列からコードブロック等を除去してJSON抽出"""
        cleaned = text.strip()
        # ```json ... ``` や ``` ... ``` の除去
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        return cleaned

    def _call_gemini_api_sync(self, api_key: str, prompt: str, generation_config: dict) -> str:
        """単一のAPIキーでGemini APIを呼び出す内部同期メソッド"""
        genai.configure(api_key=api_key)
        
        models_to_try = [self.primary_model_name]
        for m in self.fallback_models:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = None
        for model_name in models_to_try:
            try:
                logger.info(f"MangaScriptGenerator: Calling Gemini ({model_name}) with key {api_key[:6]}...")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt, generation_config=generation_config)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                last_error = e
                logger.warning(f"MangaScriptGenerator error on model {model_name}: {e}")
                if "429" in str(e) or "resourceexhausted" in str(e).lower():
                    # 429の場合はKeyManagerに例外を上げて次のキーに切り替えさせる
                    raise e
                # その他のエラーは次のモデルへフォールバック
                continue

        if last_error:
            raise last_error
        raise Exception("すべてのGeminiモデルで応答が取得できませんでした。")

    async def _call_gemini_api_async(self, api_key: str, prompt: str, generation_config: dict) -> str:
        """単一のAPIキーでGemini APIを呼び出す内部非同期メソッド"""
        genai.configure(api_key=api_key)
        
        models_to_try = [self.primary_model_name]
        for m in self.fallback_models:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = None
        for model_name in models_to_try:
            try:
                logger.info(f"MangaScriptGenerator: Calling Async Gemini ({model_name}) with key {api_key[:6]}...")
                model = genai.GenerativeModel(model_name)
                response = await asyncio.wait_for(
                    model.generate_content_async(prompt, generation_config=generation_config),
                    timeout=45.0
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                last_error = e
                logger.warning(f"MangaScriptGenerator async error on model {model_name}: {e}")
                if "429" in str(e) or "resourceexhausted" in str(e).lower():
                    raise e
                continue

        if last_error:
            raise last_error
        raise Exception("すべてのGeminiモデルで応答が取得できませんでした。")

    def generate_manga_script(
        self,
        original_text: str,
        target_length_minutes: int = 3,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        原案テキストから漫画風長尺動画台本・BGM指定タグJSONを同期生成する

        Args:
            original_text: 原案・ストーリー・テーマのテキスト
            target_length_minutes: 目標動画長（分）
            temperature: Geminiの生成ランダム性パラメータ

        Returns:
            パースされた台本データ辞書
        """
        # 目安シーン数（1シーンあたり約6秒計算）
        target_scene_count = max(5, int(target_length_minutes * 60 / 6))
        bgm_tags_str = ", ".join(VALID_BGM_TAGS)

        prompt = DEFAULT_MANGA_PROMPT_TEMPLATE.format(
            original_text=original_text,
            bgm_tags=bgm_tags_str,
            target_scene_count=target_scene_count
        )

        generation_config = {
            "temperature": temperature,
            "response_mime_type": "application/json"
        }

        # KeyManager を介して自動リトライ＆キー切り替え付きで実行
        raw_response = self.key_manager.execute_with_retry(
            self._call_gemini_api_sync,
            prompt,
            generation_config,
            pass_key_as_arg=True
        )

        cleaned_json = self._clean_json_string(raw_response)
        parsed_data = json.loads(cleaned_json)
        
        # bgm_tagのバリデーション・補正
        self._validate_and_normalize_bgm_tags(parsed_data)

        return parsed_data

    async def generate_manga_script_async(
        self,
        original_text: str,
        target_length_minutes: int = 3,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        原案テキストから漫画風長尺動画台本・BGM指定タグJSONを非同期生成する
        """
        target_scene_count = max(5, int(target_length_minutes * 60 / 6))
        bgm_tags_str = ", ".join(VALID_BGM_TAGS)

        prompt = DEFAULT_MANGA_PROMPT_TEMPLATE.format(
            original_text=original_text,
            bgm_tags=bgm_tags_str,
            target_scene_count=target_scene_count
        )

        generation_config = {
            "temperature": temperature,
            "response_mime_type": "application/json"
        }

        raw_response = await self.key_manager.execute_with_retry_async(
            self._call_gemini_api_async,
            prompt,
            generation_config,
            pass_key_as_arg=True
        )

        cleaned_json = self._clean_json_string(raw_response)
        parsed_data = json.loads(cleaned_json)

        self._validate_and_normalize_bgm_tags(parsed_data)

        return parsed_data

    def _validate_and_normalize_bgm_tags(self, script_data: Dict[str, Any]) -> None:
        """生成されたJSON内のbgm_tagを検証し、未定義タグの場合は'neutral'等に自動正則化する"""
        if "scenes" not in script_data or not isinstance(script_data["scenes"], list):
            return

        for scene in script_data["scenes"]:
            bgm_tag = str(scene.get("bgm_tag", "neutral")).lower().strip()
            if bgm_tag not in VALID_BGM_TAGS:
                logger.warning(f"Unrecognized bgm_tag '{bgm_tag}', fallback to 'neutral'")
                bgm_tag = "neutral"
            scene["bgm_tag"] = bgm_tag
