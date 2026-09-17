"""
AssetCacheManager および BatchAssetGenerator モジュールの単体テスト (unittest ベース)
"""

import unittest
import asyncio
import tempfile
import shutil
from pathlib import Path
from PIL import Image

from utils.asset_cache_manager import AssetCacheManager
from processors.batch_asset_generator import BatchAssetGenerator


class TestAssetCacheManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_mgr = AssetCacheManager(cache_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_audio_caching(self):
        """音声キャッシュの保存と取得テスト"""
        text = "これはキャッシュテスト用のナレーションです。"
        params = {"engine": "edge", "voice": "ja-JP-NanamiNeural"}

        # 最初はキャッシュ未存在
        self.assertIsNone(self.cache_mgr.get_audio(text, params))

        # ダミー音声ファイルの作成・保存
        dummy_audio = Path(self.temp_dir) / "dummy.mp3"
        with open(dummy_audio, "wb") as f:
            f.write(b"MOCK_MP3_DATA_12345")

        cached_path = self.cache_mgr.save_audio(dummy_audio, text, params)
        self.assertTrue(cached_path.exists())

        # 2回目はキャッシュHIT
        hit_path = self.cache_mgr.get_audio(text, params)
        self.assertIsNotNone(hit_path)
        self.assertEqual(hit_path.resolve(), cached_path.resolve())

    def test_image_and_overlay_caching(self):
        """画像および吹き出しオーバーレイのキャッシュテスト"""
        prompt = "A girl walking in anime style"
        img = Image.new("RGB", (100, 100), (255, 0, 0))

        # 画像保存
        saved_img_path = self.cache_mgr.save_image(img, prompt)
        self.assertIsNotNone(self.cache_mgr.get_image(prompt))

        # オーバーレイ保存
        overlay = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        saved_overlay_path = self.cache_mgr.save_overlay(overlay, "セリフテキスト", "主人公")
        self.assertIsNotNone(self.cache_mgr.get_overlay("セリフテキスト", "主人公"))


class TestBatchAssetGenerator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "cache"
        self.output_dir = Path(self.temp_dir) / "output"

        self.cache_mgr = AssetCacheManager(cache_dir=self.cache_dir)
        self.batch_gen = BatchAssetGenerator(cache_manager=self.cache_mgr)

        self.mock_script_data = {
            "title": "テスト動画",
            "scenes": [
                {
                    "scene_number": 1,
                    "speaker": "ナレーション",
                    "narration": "第一章が始まります。",
                    "character_prompt": "First scene background prompt",
                    "bgm_tag": "warm",
                    "duration_seconds": 4
                },
                {
                    "scene_number": 2,
                    "speaker": "葵",
                    "narration": "信じられない！本当なの？",
                    "character_prompt": "Surprised Japanese girl prompt",
                    "bgm_tag": "suspense",
                    "duration_seconds": 5
                }
            ]
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_batch_assets(self):
        """全シーンの音声・画像・演出オーバーレイの一括生成＆キャッシュ再利用テスト"""
        async def run_batch():
            return await self.batch_gen.generate_batch_assets(
                script_data=self.mock_script_data,
                output_dir=self.output_dir,
                image_size=(320, 480)
            )

        # 1回目の生成実行
        results = asyncio.run(run_batch())

        self.assertEqual(len(results), 2)
        scene1 = results[0]
        self.assertEqual(scene1["scene_number"], 1)
        self.assertTrue(Path(scene1["base_image_path"]).exists())
        self.assertTrue(Path(scene1["overlay_image_path"]).exists())

        # 2回目の生成実行（キャッシュHIT確認）
        output_dir_2 = Path(self.temp_dir) / "output_2"
        async def run_batch_2():
            return await self.batch_gen.generate_batch_assets(
                script_data=self.mock_script_data,
                output_dir=output_dir_2,
                image_size=(320, 480)
            )

        results_2 = asyncio.run(run_batch_2())
        self.assertEqual(len(results_2), 2)
        self.assertTrue(Path(results_2[0]["base_image_path"]).exists())
        self.assertTrue(Path(results_2[0]["overlay_image_path"]).exists())


if __name__ == "__main__":
    unittest.main()
