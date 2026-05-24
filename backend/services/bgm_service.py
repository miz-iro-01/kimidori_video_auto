"""
BGM管理サービス — BGM楽曲の登録・管理・自動選曲
Firebase Storage に楽曲ファイルを保存し、Firestore にメタデータを保持。
Gemini API を使って動画テーマに最適な BGM を自動選択する。
"""

import logging
import uuid
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class BGMService:
    """BGM楽曲の管理と自動選曲サービス"""

    COLLECTION_NAME = "bgm_tracks"
    STORAGE_PREFIX = "bgm"
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

    def __init__(self, firestore_service, storage_service):
        self.firestore = firestore_service
        self.storage = storage_service

    def register_bgm(
        self,
        user_id: str,
        file_path: Path,
        original_filename: str,
        title: str,
        description: str,
        keywords: list[str] = None,
    ) -> dict:
        """
        BGM楽曲を登録する

        Args:
            user_id: ユーザーID
            file_path: アップロードされた一時ファイルのパス
            original_filename: 元のファイル名
            title: 曲名
            description: 曲の説明（ジャンル、雰囲気などの自由記述）
            keywords: 検索用キーワードリスト

        Returns:
            dict: 登録されたBGM情報
        """
        bgm_id = str(uuid.uuid4())
        ext = Path(original_filename).suffix.lower()

        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValueError(
                f"サポートされていないファイル形式です: {ext}。"
                f"対応形式: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        # ファイルサイズチェック
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"ファイルサイズが上限を超えています: "
                f"{file_size / 1024 / 1024:.1f}MB (上限: {self.MAX_FILE_SIZE / 1024 / 1024:.0f}MB)"
            )

        # Firebase Storage にアップロード
        storage_path = f"{self.STORAGE_PREFIX}/{user_id}/{bgm_id}{ext}"
        storage_url = self.storage.upload_file(file_path, storage_path)

        # Firestore にメタデータを保存
        now = datetime.utcnow().isoformat()
        bgm_doc = {
            "bgm_id": bgm_id,
            "user_id": user_id,
            "title": title,
            "description": description,
            "keywords": keywords or [],
            "original_filename": original_filename,
            "storage_path": storage_path,
            "storage_url": storage_url,
            "file_extension": ext,
            "file_size": file_size,
            "created_at": now,
            "updated_at": now,
        }

        self.firestore.db.collection(self.COLLECTION_NAME).document(bgm_id).set(bgm_doc)
        logger.info(f"BGM登録完了: {bgm_id} — '{title}' ({ext}, {file_size / 1024:.0f}KB)")
        return bgm_doc

    def list_bgm(self, user_id: str) -> list[dict]:
        """ユーザーの登録済みBGM一覧を取得"""
        docs = (
            self.firestore.db.collection(self.COLLECTION_NAME)
            .where("user_id", "==", user_id)
            .stream()
        )
        results = [doc.to_dict() for doc in docs]
        # 新しい順にソート
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results

    def get_bgm(self, bgm_id: str) -> Optional[dict]:
        """BGM情報を取得"""
        doc = self.firestore.db.collection(self.COLLECTION_NAME).document(bgm_id).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def update_bgm(self, bgm_id: str, user_id: str, **kwargs) -> dict:
        """BGMメタデータを更新"""
        bgm = self.get_bgm(bgm_id)
        if not bgm:
            raise ValueError(f"BGMが見つかりません: {bgm_id}")
        if bgm["user_id"] != user_id:
            raise PermissionError("このBGMを更新する権限がありません")

        allowed_fields = {"title", "description", "keywords"}
        update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}
        update_data["updated_at"] = datetime.utcnow().isoformat()

        self.firestore.db.collection(self.COLLECTION_NAME).document(bgm_id).update(update_data)
        bgm.update(update_data)
        logger.info(f"BGM更新: {bgm_id} — フィールド: {list(update_data.keys())}")
        return bgm

    def delete_bgm(self, bgm_id: str, user_id: str) -> bool:
        """BGMを削除（Storage + Firestore）"""
        bgm = self.get_bgm(bgm_id)
        if not bgm:
            raise ValueError(f"BGMが見つかりません: {bgm_id}")
        if bgm["user_id"] != user_id:
            raise PermissionError("このBGMを削除する権限がありません")

        # Storage から削除
        try:
            self.storage.delete_file(bgm["storage_path"])
        except Exception as e:
            logger.warning(f"BGMファイルのStorage削除に失敗（続行）: {e}")

        # Firestore から削除
        self.firestore.db.collection(self.COLLECTION_NAME).document(bgm_id).delete()
        logger.info(f"BGM削除完了: {bgm_id} — '{bgm.get('title', '不明')}'")
        return True

    def download_bgm(self, bgm_id: str, dest_dir: Path) -> Path:
        """BGM音源をダウンロードして一時ファイルとして返す"""
        bgm = self.get_bgm(bgm_id)
        if not bgm:
            raise ValueError(f"BGMが見つかりません: {bgm_id}")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"bgm_{bgm_id}{bgm['file_extension']}"
        self.storage.download_file(bgm["storage_path"], dest_path)
        logger.info(f"BGMダウンロード完了: {dest_path}")
        return dest_path

    async def select_bgm_for_theme(
        self,
        theme: str,
        script_data: dict,
        user_id: str,
        gemini_api_key: str,
    ) -> Optional[dict]:
        """
        Gemini APIを使って動画テーマに最適なBGMを自動選択する

        Args:
            theme: 動画のテーマ
            script_data: 台本データ
            user_id: ユーザーID
            gemini_api_key: Gemini APIキー

        Returns:
            選択されたBGM情報、またはNone（BGM未登録の場合）
        """
        bgm_list = self.list_bgm(user_id)
        if not bgm_list:
            logger.info("BGMが未登録のため、BGMなしで動画を生成します")
            return None

        if len(bgm_list) == 1:
            logger.info(f"BGMが1曲のみ登録されているため、自動選択: '{bgm_list[0]['title']}'")
            return bgm_list[0]

        # BGM候補リストを構築
        bgm_candidates = []
        for i, bgm in enumerate(bgm_list):
            desc = bgm.get("description", "")
            kw = ", ".join(bgm.get("keywords", []))
            bgm_candidates.append(
                f"BGM {i + 1}: 曲名「{bgm['title']}」 説明: {desc} キーワード: {kw}"
            )
        candidates_text = "\n".join(bgm_candidates)

        # 台本の要約を作成
        script_summary = ""
        if script_data and "scenes" in script_data:
            scene_texts = [
                s.get("narration", s.get("text_overlay", ""))
                for s in script_data["scenes"][:3]
            ]
            script_summary = " / ".join(scene_texts)

        # Gemini APIで最適なBGMを選択
        prompt = f"""以下の動画テーマと台本内容に最も合うBGMを1つ選んでください。

動画テーマ: {theme}
台本の概要: {script_summary}

登録されているBGM候補:
{candidates_text}

回答は、選択したBGMの番号のみを数字で返してください（例: 1）。
理由は不要です。番号だけを返してください。"""

        try:
            import google.generativeai as genai

            genai.configure(api_key=gemini_api_key)

            # フォールバックモデルリスト
            models = config.GEMINI_FALLBACK_MODELS.copy()
            response_text = None

            for model_name in models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt)
                    response_text = response.text.strip()
                    break
                except Exception as e:
                    logger.warning(f"Gemini {model_name} での選曲失敗、次のモデルを試行: {e}")
                    continue

            if response_text:
                # 数字を抽出
                import re
                match = re.search(r"(\d+)", response_text)
                if match:
                    idx = int(match.group(1)) - 1
                    if 0 <= idx < len(bgm_list):
                        selected = bgm_list[idx]
                        logger.info(
                            f"自動選曲完了: BGM {idx + 1} '{selected['title']}' "
                            f"（テーマ: {theme}）"
                        )
                        return selected

            # フォールバック: 最初のBGMを使用
            logger.warning("Geminiによる選曲結果をパースできませんでした。最初のBGMを使用します")
            return bgm_list[0]

        except Exception as e:
            logger.error(f"自動選曲でエラーが発生しました: {e}")
            # エラー時も最初のBGMを使用
            return bgm_list[0]
