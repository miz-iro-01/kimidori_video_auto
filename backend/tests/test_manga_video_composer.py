"""
MangaVideoComposer モジュールの単体テスト (unittest ベース)
"""

import unittest
import tempfile
import shutil
import subprocess
from pathlib import Path
from PIL import Image

from processors.manga_video_composer import MangaVideoComposer


class TestMangaVideoComposer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.composer = MangaVideoComposer()

        # ダミーベース画像（赤）
        self.base_img_path = Path(self.temp_dir) / "base.png"
        img_base = Image.new("RGB", (320, 480), (200, 50, 50))
        img_base.save(self.base_img_path)

        # ダミーオーバーレイ画像（緑）
        self.overlay_img_path = Path(self.temp_dir) / "overlay.png"
        img_overlay = Image.new("RGBA", (320, 480), (50, 200, 50, 200))
        img_overlay.save(self.overlay_img_path)

        # FFmpeg/FFprobeの存在チェック
        try:
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True)
            self.has_ffmpeg = (res.returncode == 0)
        except Exception:
            self.has_ffmpeg = False

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_single_scene_clip_creation(self):
        """0.3秒演出切り替え付き単一シーンクリップ作成テスト"""
        if not self.has_ffmpeg:
            self.skipTest("FFmpeg is not installed or available.")

        out_clip = Path(self.temp_dir) / "test_clip.mp4"
        duration = self.composer.create_single_scene_clip(
            base_image_path=self.base_img_path,
            overlay_image_path=self.overlay_img_path,
            audio_path=None,
            output_clip_path=out_clip,
            duration=2.0,
            width=320,
            height=480,
            fps=15
        )

        self.assertTrue(out_clip.exists())
        self.assertGreaterEqual(duration, 2.0)

    def test_build_multi_bgm_track(self):
        """シーンごとの感情タグによるマルチBGMトラック構築テスト"""
        if not self.has_ffmpeg:
            self.skipTest("FFmpeg is not installed or available.")

        out_bgm = Path(self.temp_dir) / "test_multibgm.aac"
        bgm_sequence = [(2.0, None), (3.0, None)]  # ダミー配列

        result_path = self.composer.build_multi_bgm_track(
            scene_bgm_sequence=bgm_sequence,
            total_duration=5.0,
            output_bgm_path=out_bgm
        )

        self.assertTrue(result_path.exists())

    def test_full_compose_manga_video(self):
        """全シーンの合成・結合・BGMマルチミックステスト"""
        if not self.has_ffmpeg:
            self.skipTest("FFmpeg is not installed or available.")

        scene_assets = [
            {
                "scene_number": 1,
                "base_image_path": str(self.base_img_path),
                "overlay_image_path": str(self.overlay_img_path),
                "audio_path": None,
                "bgm_tag": "warm",
                "duration_seconds": 2.0
            },
            {
                "scene_number": 2,
                "base_image_path": str(self.base_img_path),
                "overlay_image_path": str(self.overlay_img_path),
                "audio_path": None,
                "bgm_tag": "suspense",
                "duration_seconds": 2.0
            }
        ]

        output_video = Path(self.temp_dir) / "final_output.mp4"
        work_dir = Path(self.temp_dir) / "work"

        res_video = self.composer.compose_manga_video(
            scene_assets=scene_assets,
            bgm_map={"warm": None, "suspense": None},
            output_video_path=output_video,
            work_dir=work_dir,
            video_size=(320, 480)
        )

        self.assertTrue(res_video.exists())
        self.assertGreater(res_video.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
