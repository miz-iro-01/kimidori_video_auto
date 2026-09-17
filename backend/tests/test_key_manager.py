"""
KeyManager モジュールの単体テスト (unittest ベース)
"""

import unittest
import asyncio
from utils.key_manager import (
    KeyManager,
    NoAPIKeysAvailableError,
    KeyManagerAllKeysFailedError,
)


class TestKeyManager(unittest.TestCase):

    def test_string_initialization(self):
        """文字列（カンマ・改行区切り）による初期化テスト"""
        km = KeyManager("key1, key2\nkey3")
        self.assertEqual(km.get_keys(), ["key1", "key2", "key3"])
        self.assertEqual(km.key_count, 3)

    def test_round_robin_key_retrieval(self):
        """ラウンドロビン方式でのキー取得テスト"""
        km = KeyManager(["KEY_A", "KEY_B", "KEY_C"])
        
        self.assertEqual(km.get_next_key(), "KEY_A")
        self.assertEqual(km.get_next_key(), "KEY_B")
        self.assertEqual(km.get_next_key(), "KEY_C")
        self.assertEqual(km.get_next_key(), "KEY_A")  # 周回

    def test_execute_with_retry_success(self):
        """正常系の同期実行テスト"""
        km = KeyManager(["KEY_A", "KEY_B"])
        
        def dummy_func(api_key, text):
            return f"{api_key}:{text}"
            
        result = km.execute_with_retry(dummy_func, "hello")
        self.assertEqual(result, "KEY_A:hello")

    def test_execute_with_retry_429_failover(self):
        """429 (Rate Limit) エラー発生時の自動キー切り替えテスト"""
        km = KeyManager(["KEY_FAIL", "KEY_SUCCESS"])
        
        attempts = []

        def mock_api_call(api_key, prompt):
            attempts.append(api_key)
            if api_key == "KEY_FAIL":
                raise Exception("429 ResourceExhausted: Rate limit exceeded")
            return f"Response with {api_key} for {prompt}"

        result = km.execute_with_retry(mock_api_call, "test prompt")
        
        self.assertEqual(attempts, ["KEY_FAIL", "KEY_SUCCESS"])
        self.assertEqual(result, "Response with KEY_SUCCESS for test prompt")

    def test_execute_with_retry_all_fail(self):
        """全キーでエラーが発生した場合のテスト"""
        km = KeyManager(["KEY_1", "KEY_2"])
        
        def always_fail(api_key):
            raise Exception("429 Too Many Requests")

        with self.assertRaises(KeyManagerAllKeysFailedError):
            km.execute_with_retry(always_fail, max_retries=2)

    def test_async_execute_with_retry_429_failover(self):
        """非同期関数での429エラー時自動キー切り替えテスト"""
        km = KeyManager(["KEY_ERR", "KEY_OK"])
        attempts = []

        async def mock_async_api(api_key, data):
            attempts.append(api_key)
            await asyncio.sleep(0.01)
            if api_key == "KEY_ERR":
                raise Exception("429 Quota Exceeded")
            return f"OK:{api_key}:{data}"

        async def run_test():
            return await km.execute_with_retry_async(mock_async_api, "data123")

        result = asyncio.run(run_test())
        
        self.assertEqual(attempts, ["KEY_ERR", "KEY_OK"])
        self.assertEqual(result, "OK:KEY_OK:data123")

    def test_empty_keys_exception(self):
        """キー未設定時の例外テスト"""
        km = KeyManager([])
        
        with self.assertRaises(NoAPIKeysAvailableError):
            km.get_next_key()

        with self.assertRaises(NoAPIKeysAvailableError):
            km.execute_with_retry(lambda k: k)


if __name__ == "__main__":
    unittest.main()
