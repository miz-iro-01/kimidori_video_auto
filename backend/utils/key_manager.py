"""
KIMIDORI Movie Auto - API Key Manager
複数APIキーのラウンドロビン管理および429(Rate Limit)等のエラー発生時の自動キー切替・リトライモジュール
"""

import asyncio
import logging
import threading
from typing import Callable, List, Optional, Any, TypeVar, Awaitable, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")

class NoAPIKeysAvailableError(Exception):
    """有効なAPIキーが存在しない場合の例外"""
    pass

class KeyManagerAllKeysFailedError(Exception):
    """全てのAPIキー試行でエラーが発生した場合の例外"""
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


class KeyManager:
    """
    複数APIキーのラウンドロビン管理およびリトライモジュール
    """

    def __init__(
        self,
        api_keys: Optional[Union[List[str], str]] = None,
        max_retries: Optional[int] = None
    ):
        """
        Args:
            api_keys: APIキーのリスト、またはカンマ区切りの文字列
            max_retries: リトライの最大回数（デフォルトはキーの数 * 2 または 3）
        """
        self._lock = threading.Lock()
        self._current_index = 0
        self._api_keys: List[str] = []
        self.max_retries = max_retries
        
        if api_keys:
            self.set_keys(api_keys)

    def set_keys(self, api_keys: Union[List[str], str]) -> None:
        """APIキーのリストを更新設定する"""
        with self._lock:
            if isinstance(api_keys, str):
                # カンマまたは改行区切りの文字列に対応
                keys = [k.strip() for k in api_keys.replace("\n", ",").split(",") if k.strip()]
            elif isinstance(api_keys, list):
                keys = [str(k).strip() for k in api_keys if str(k).strip()]
            else:
                keys = []

            self._api_keys = keys
            self._current_index = 0
            logger.info(f"KeyManager: {len(self._api_keys)} 個のAPIキーを設定しました。")

    def add_key(self, key: str) -> None:
        """APIキーを1件追加する"""
        clean_key = key.strip() if key else ""
        if clean_key:
            with self._lock:
                if clean_key not in self._api_keys:
                    self._api_keys.append(clean_key)
                    logger.info("KeyManager: APIキーを追加しました。")

    def get_keys(self) -> List[str]:
        """設定されている全キーのリストを取得"""
        with self._lock:
            return list(self._api_keys)

    @property
    def key_count(self) -> int:
        """登録されているAPIキーの総数"""
        with self._lock:
            return len(self._api_keys)

    def get_next_key(self) -> str:
        """
        ラウンドロビン方式で次のAPIキーを取得する
        """
        with self._lock:
            if not self._api_keys:
                raise NoAPIKeysAvailableError("使用可能なAPIキーが登録されていません。")

            key = self._api_keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._api_keys)
            return key

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """
        例外が429 / Rate Limit / Quota Exceeded系エラーかどうかを判定する
        """
        err_msg = str(exc).lower()
        err_type = type(exc).__name__.lower()

        keywords = [
            "429",
            "rate limit",
            "ratelimit",
            "resourceexhausted",
            "quota",
            "too many requests",
            "exceeded",
        ]
        
        return any(kw in err_msg or kw in err_type for kw in keywords)

    def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        max_retries: Optional[int] = None,
        pass_key_as_arg: bool = True,
        **kwargs
    ) -> T:
        """
        同期関数をラウンドロビンAPIキーを用いて実行し、レート制限エラー等の場合に自動で次のキーに切替えてリトライする

        Args:
            func: 実行する関数 (例: `lambda api_key: call_gemini(api_key, prompt)`)
                  pass_key_as_arg=True の場合、第1引数に api_key が渡される func(api_key, *args, **kwargs)
            max_retries: リトライ上限回数。指定なき場合は (キーの数 * 2) または設定値
            pass_key_as_arg: Trueの場合、func(api_key, *args, **kwargs) として呼び出す
        """
        if self.key_count == 0:
            raise NoAPIKeysAvailableError("使用可能なAPIキーが登録されていません。")

        retries_limit = (
            max_retries 
            if max_retries is not None 
            else (self.max_retries if self.max_retries is not None else max(self.key_count * 2, 3))
        )

        last_exception = None

        for attempt in range(retries_limit):
            api_key = self.get_next_key()
            try:
                if pass_key_as_arg:
                    return func(api_key, *args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if self._is_rate_limit_error(e):
                    logger.warning(
                        f"APIキー ({api_key[:6]}...) でレート制限/429エラーが発生しました (試行 {attempt + 1}/{retries_limit}): {e}. 次のキーに切り替えます。"
                    )
                else:
                    logger.warning(
                        f"APIキー ({api_key[:6]}...) でエラーが発生しました (試行 {attempt + 1}/{retries_limit}): {e}. 次のキーに切り替えます。"
                    )

        raise KeyManagerAllKeysFailedError(
            f"すべてのAPIキー試行 ({retries_limit} 回) に失敗しました。",
            last_exception=last_exception
        )

    async def execute_with_retry_async(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        max_retries: Optional[int] = None,
        pass_key_as_arg: bool = True,
        **kwargs
    ) -> T:
        """
        非同期 (async) 関数をラウンドロビンAPIキーを用いて実行し、エラー時に自動リトライする
        """
        if self.key_count == 0:
            raise NoAPIKeysAvailableError("使用可能なAPIキーが登録されていません。")

        retries_limit = (
            max_retries 
            if max_retries is not None 
            else (self.max_retries if self.max_retries is not None else max(self.key_count * 2, 3))
        )

        last_exception = None

        for attempt in range(retries_limit):
            api_key = self.get_next_key()
            try:
                if pass_key_as_arg:
                    return await func(api_key, *args, **kwargs)
                else:
                    return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if self._is_rate_limit_error(e):
                    logger.warning(
                        f"APIキー ({api_key[:6]}...) でレート制限/429エラーが発生しました (試行 {attempt + 1}/{retries_limit}): {e}. 次のキーに切り替えます。"
                    )
                else:
                    logger.warning(
                        f"APIキー ({api_key[:6]}...) でエラーが発生しました (試行 {attempt + 1}/{retries_limit}): {e}. 次のキーに切り替えます。"
                    )

        raise KeyManagerAllKeysFailedError(
            f"すべてのAPIキー試行 ({retries_limit} 回) に失敗しました。",
            last_exception=last_exception
        )
