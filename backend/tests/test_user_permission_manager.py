"""
UserPermissionManager モジュールの単体テスト (unittest ベース)
"""

import unittest
from services.firestore_service import FirestoreService
from services.user_permission_manager import UserPermissionManager, PlanType, FeatureName


class TestUserPermissionManager(unittest.TestCase):

    def setUp(self):
        self.firestore = FirestoreService()
        self.perm_mgr = UserPermissionManager(firestore_service=self.firestore)
        self.test_user_free = "user_test_free_123"
        self.test_user_pro = "user_test_pro_456"

    def test_default_free_user_permission(self):
        """未設定ユーザーにおける無料会員制限の判定テスト"""
        plan_info = self.perm_mgr.get_user_plan(self.test_user_free)
        self.assertEqual(plan_info["plan"], PlanType.FREE)
        self.assertFalse(plan_info["is_pro"])

        # ショート動画作成: 無料会員利用可能（ロゴ表示あり・カスタムBGM不可）
        res_short = self.perm_mgr.check_feature_access(self.test_user_free, FeatureName.SHORT_VIDEO_CREATE)
        self.assertTrue(res_short["allowed"])
        self.assertTrue(res_short["watermark_required"])
        self.assertFalse(res_short["custom_bgm_allowed"])

        # 長尺動画作成: 無料会員利用可能（ロゴ表示あり・カスタムBGM不可）
        res_long = self.perm_mgr.check_feature_access(self.test_user_free, FeatureName.LONG_VIDEO_CREATE)
        self.assertTrue(res_long["allowed"])
        self.assertTrue(res_long["watermark_required"])
        self.assertFalse(res_long["custom_bgm_allowed"])

        # 長尺漫画動画作成: 無料会員利用不可
        res_manga = self.perm_mgr.check_feature_access(self.test_user_free, FeatureName.MANGA_LONG_VIDEO_CREATE)
        self.assertFalse(res_manga["allowed"])

        # 自動投稿: 無料会員利用不可
        res_post = self.perm_mgr.check_feature_access(self.test_user_free, FeatureName.YOUTUBE_AUTO_POST)
        self.assertFalse(res_post["allowed"])

    def test_pro_user_permission(self):
        """有料サブスク会員への更新および制限解除のテスト"""
        # PRO プランへ更新
        update_success = self.perm_mgr.update_user_plan(self.test_user_pro, PlanType.PRO)
        self.assertTrue(update_success)

        plan_info = self.perm_mgr.get_user_plan(self.test_user_pro)
        self.assertEqual(plan_info["plan"], PlanType.PRO)
        self.assertTrue(plan_info["is_pro"])

        # 長尺漫画動画作成: 有料会員利用可能（ロゴ非表示・カスタムBGM自由）
        res_manga = self.perm_mgr.check_feature_access(self.test_user_pro, FeatureName.MANGA_LONG_VIDEO_CREATE)
        self.assertTrue(res_manga["allowed"])
        self.assertFalse(res_manga["watermark_required"])
        self.assertTrue(res_manga["custom_bgm_allowed"])

        # 自動投稿: 有料会員利用可能
        res_post = self.perm_mgr.check_feature_access(self.test_user_pro, FeatureName.YOUTUBE_AUTO_POST)
        self.assertTrue(res_post["allowed"])

    def test_user_settings_save_and_load(self):
        """ユーザー設定の保存とロードテスト"""
        settings = {
            "default_voice": "nanami",
            "custom_bgm_mapping": {
                "warm": "my_custom_warm.mp3",
                "suspense": "my_custom_suspense.mp3"
            }
        }
        success = self.perm_mgr.save_user_settings(self.test_user_pro, settings)
        self.assertTrue(success)

        loaded = self.perm_mgr.get_user_settings(self.test_user_pro)
        self.assertEqual(loaded.get("default_voice"), "nanami")
        self.assertEqual(loaded.get("custom_bgm_mapping", {}).get("warm"), "my_custom_warm.mp3")


if __name__ == "__main__":
    unittest.main()
