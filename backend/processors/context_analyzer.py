"""
KIMIDORI Movie Auto - 文脈・感情連動型 Bロール検出アナライザー
Whisper文字起こしテキストから、Geminiを活用して動画内の感情の高まり・重要シーン・話題転換点を特定し、
最適な英語検索クエリとインサート区間（開始秒・長さ）を算出する。
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
import aiohttp

import config
from utils.key_manager import KeyManager

logger = logging.getLogger(__name__)

# オフライン・フォールバック用感情辞書
RULE_EMOTION_KEYWORDS = [
    {"pattern": r"売上|利益|成功|収益|株価|跳ね上が|成長|大ヒット|バズ", "emotion": "success", "query": "business growth success graph celebration"},
    {"pattern": r"落ち込|絶望|失敗|破綻|赤字|後悔|どうすれば|涙|泣く", "emotion": "sadness", "query": "depressed sad stressed person alone"},
    {"pattern": r"驚き|まさか|信じられない|衝撃|えっ|パニック|嘘だろ", "emotion": "shock", "query": "shocked surprise dramatic reaction"},
    {"pattern": r"怒り|許せない|激怒|クレーム|理不尽|トラブル|喧嘩", "emotion": "anger", "query": "angry confrontation argument tension"},
    {"pattern": r"嬉しい|感謝|幸せ|最高|ワクワク|笑顔|喜び", "emotion": "happy", "query": "happy joyful smiling celebration cheerful"},
    {"pattern": r"危険|注意|警告|リスク|恐怖|怖い|怪しい", "emotion": "danger", "query": "danger warning mysterious caution dark"},
    {"pattern": r"仕事|オフィス|残業|ビジネス|会議|プレゼン|パソコン", "emotion": "business", "query": "modern office corporate meeting laptop work"},
    {"pattern": r"お金|投資|資産|富裕層|豪邸|高級|タワマン", "emotion": "wealth", "query": "luxury wealth money financial skyscraper"}
]


class ContextAnalyzer:
    """Whisperの音声認識結果からBロール挿入候補を抽出するアナライザー"""

    def __init__(self, key_manager: Optional[KeyManager] = None):
        self.key_manager = key_manager or KeyManager([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])

    async def detect_broll_insertion_points(
        self,
        transcript_segments: List[Dict[str, Any]],
        video_duration: float,
        max_inserts: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Whisper字幕セグメントからBロールをインサートすべきタイムコードとPexels英語クエリを抽出

        Args:
            transcript_segments: [{"start": 0.0, "end": 4.5, "text": "..."}]
            video_duration: 動画全体の長さ（秒）
            max_inserts: 最大インサート数（動画が長すぎないよう調整）

        Returns:
            List[Dict]: [
                {
                    "start": 開始秒,
                    "duration": インサート秒数 (3.0〜5.0秒),
                    "end": 終了秒,
                    "emotion": "shock",
                    "pexels_query": "shocked surprise dramatic reaction",
                    "reason": "..."
                }
            ]
        """
        if not transcript_segments:
            return []

        # 1. Gemini APIによる高精度文脈・感情解析を試行
        try:
            gemini_results = await self._analyze_with_gemini(transcript_segments, video_duration, max_inserts)
            if gemini_results:
                logger.info(f"Gemini文脈解析により {len(gemini_results)} 箇所のBロール挿入点を検出しました。")
                return gemini_results
        except Exception as e:
            logger.warning(f"Gemini文脈解析エラー、ルールベースへフォールバック: {e}")

        # 2. ルールベースフォールバック（オフライン・API制限時）
        fallback_results = self._analyze_with_rules(transcript_segments, video_duration, max_inserts)
        logger.info(f"ルールベース文脈解析により {len(fallback_results)} 箇所のBロール挿入点を検出しました。")
        return fallback_results

    async def _analyze_with_gemini(
        self,
        transcript_segments: List[Dict[str, Any]],
        video_duration: float,
        max_inserts: int
    ) -> List[Dict[str, Any]]:
        """Geminiを用いた文脈・感情転換点解析"""
        simplified_segments = [
            {
                "start": round(s.get("start", 0), 1),
                "end": round(s.get("end", 0), 1),
                "text": s.get("text", "").strip()
            }
            for s in transcript_segments
            if s.get("text", "").strip()
        ]

        if not simplified_segments:
            return []

        prompt = f"""
あなたはプロのYouTube映像編集エディターです。
以下の動画の音声文字起こしデータ（タイムスタンプ付き）を読み込み、視聴者の集中を持続させるための「Bロール（情景映像・イメージ映像）」をインサートする最適な瞬間を最大{max_inserts}箇所特定してください。

【動画情報】
- 動画尺: 約{video_duration:.1f}秒
- インサートルール:
  1. 感情の高まり（喜び、ショック、悲しみ、怒り、驚きなど）や具体的な情景（オフィス、お金、パソコン作業、大自然など）に該当する区間を選ぶこと。
  2. 各インサートの長さは 3.0 〜 5.0 秒とすること。
  3. インサート同士の間隔は最低でも 8 秒以上離すこと。
  4. Pexelsなどのフリー動画サイトでヒットしやすい具体的な「英語検索キーワード（2〜4単語）」を出力すること。

【字幕セグメント】:
{json.dumps(simplified_segments[:80], ensure_ascii=False)}

【出力フォーマット（必ずJSON配列のみ出力すること）】:
```json
[
  {{
    "start": 12.5,
    "duration": 4.0,
    "emotion": "shock",
    "pexels_query": "shocked business man looking at screen",
    "reason": "予想外のトラブル発生による動揺を視覚的に補強"
  }}
]
```
"""
        models = [config.GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.5-pro"]

        async def _call_gemini(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                for model in models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    payload = {
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
                    }
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25.0) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                    except Exception:
                        continue
            raise RuntimeError("Gemini API call failed for context analysis")

        raw_text = await self.key_manager.execute_with_retry_async(_call_gemini)
        m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw_text, re.DOTALL)
        json_str = m.group(1) if m else raw_text
        targets = json.loads(json_str)

        valid_targets = []
        for t in targets:
            start = float(t.get("start", 0))
            dur = min(6.0, max(2.5, float(t.get("duration", 4.0))))
            if start + dur <= video_duration and start >= 1.0:
                t["start"] = start
                t["duration"] = dur
                t["end"] = round(start + dur, 2)
                valid_targets.append(t)

        # 時間順にソートし、重複・近接を整理
        valid_targets.sort(key=lambda x: x["start"])
        filtered = []
        last_end = 0.0
        for item in valid_targets:
            if item["start"] >= last_end + 8.0:
                filtered.append(item)
                last_end = item["end"]
            if len(filtered) >= max_inserts:
                break

        return filtered

    def _analyze_with_rules(
        self,
        transcript_segments: List[Dict[str, Any]],
        video_duration: float,
        max_inserts: int
    ) -> List[Dict[str, Any]]:
        """正規表現キーワードマッチングによるルールベースBロール検出"""
        candidates = []
        last_end = 0.0

        for seg in transcript_segments:
            text = seg.get("text", "")
            start = float(seg.get("start", 0))
            seg_duration = float(seg.get("end", start + 3)) - start

            if start < last_end + 8.0 or start > video_duration - 4.0:
                continue

            for rule in RULE_EMOTION_KEYWORDS:
                if re.search(rule["pattern"], text):
                    dur = min(4.5, max(3.0, seg_duration))
                    candidates.append({
                        "start": round(start, 2),
                        "duration": round(dur, 2),
                        "end": round(start + dur, 2),
                        "emotion": rule["emotion"],
                        "pexels_query": rule["query"],
                        "reason": f"キーワード「{text[:20]}」に対応するイメージをインサート"
                    })
                    last_end = start + dur
                    break

            if len(candidates) >= max_inserts:
                break

        return candidates
