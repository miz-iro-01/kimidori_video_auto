"""
MangaScriptGenerator モジュールの単体テスト (unittest ベース)
"""

import unittest
import json
import asyncio
from unittest.mock import MagicMock, patch

from utils.key_manager import KeyManager
from processors.manga_script_generator import MangaScriptGenerator, VALID_BGM_TAGS


class TestMangaScriptGenerator(unittest.TestCase):

    def setUp(self):
        self.mock_script_json = json.dumps({
            "title": "テスト用スカッとストーリー",
            "description": "テスト用の概要説明",
            "bgm_summary": ["warm", "suspense", "touching"],
            "scenes": [
                {
                    "scene_number": 1,
                    "speaker": "ナレーション",
                    "narration": "静かな田舎町に住む主人公。",
                    "visual_description": "のどかな風景",
                    "character_prompt": "A quiet Japanese countryside town, anime manga style",
                    "bgm_tag": "warm",
                    "duration_seconds": 6
                },
                {
                    "scene_number": 2,
                    "speaker": "悪役",
                    "narration": "ふはは、邪魔をするな！",
                    "visual_description": "悪役の怒り顔",
                    "character_prompt": "An angry villian in anime style",
                    "bgm_tag": "INVALID_TAG_NAME",  # バリデーションテスト用
                    "duration_seconds": 5
                }
            ]
        })

    def test_json_cleaning_and_tag_validation(self):
        """JSONパースおよびBGMタグの自動補正テスト"""
        km = KeyManager(["FAKE_KEY_1"])
        generator = MangaScriptGenerator(key_manager=km)

        # 内部メソッドの直接呼出しテスト
        raw_text = f"```json\n{self.mock_script_json}\n```"
        cleaned = generator._clean_json_string(raw_text)
        data = json.loads(cleaned)
        generator._validate_and_normalize_bgm_tags(data)

        self.assertEqual(data["scenes"][0]["bgm_tag"], "warm")
        # 不正なタグ INVALID_TAG_NAME が neutral に置換されたか
        self.assertEqual(data["scenes"][1]["bgm_tag"], "neutral")

    @patch("processors.manga_script_generator.genai.GenerativeModel")
    def test_generate_manga_script_sync_with_keymanager(self, mock_generative_model):
        """KeyManager と連携した同期生成テスト（429フェイルオーバー含む）"""
        km = KeyManager(["KEY_FAIL_429", "KEY_WORKING"])
        generator = MangaScriptGenerator(key_manager=km)

        # モックの挙動を設定
        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance

        # 1回目のAPI呼び出し（KEY_FAIL_429）は429エラー、2回目（KEY_WORKING）は正常レスポンス
        def mock_generate_content(prompt, generation_config):
            # 現在設定されているキーをチェックしてシミュレート
            if "KEY_FAIL_429" in generator.key_manager._api_keys[0] and generator.key_manager._current_index == 1:
                raise Exception("429 ResourceExhausted: Quota Exceeded")
            
            mock_res = MagicMock()
            mock_res.text = self.mock_script_json
            return mock_res

        mock_model_instance.generate_content.side_effect = mock_generate_content

        result = generator.generate_manga_script("ある日の出来事...", target_length_minutes=2)

        self.assertEqual(result["title"], "テスト用スカッとストーリー")
        self.assertEqual(len(result["scenes"]), 2)
        self.assertEqual(result["scenes"][1]["bgm_tag"], "neutral")

    @patch("processors.manga_script_generator.genai.GenerativeModel")
    def test_generate_manga_script_async(self, mock_generative_model):
        """非同期生成テスト"""
        km = KeyManager(["KEY_ASYNC_OK"])
        generator = MangaScriptGenerator(key_manager=km)

        mock_model_instance = MagicMock()
        mock_generative_model.return_value = mock_model_instance

        async def mock_generate_async(prompt, generation_config):
            await asyncio.sleep(0.01)
            mock_res = MagicMock()
            mock_res.text = self.mock_script_json
            return mock_res

        mock_model_instance.generate_content_async.side_effect = mock_generate_async

        async def run_test():
            return await generator.generate_manga_script_async("原案テキスト")

        result = asyncio.run(run_test())

        self.assertEqual(result["title"], "テスト用スカッとストーリー")
        self.assertEqual(result["scenes"][0]["bgm_tag"], "warm")


if __name__ == "__main__":
    unittest.main()
