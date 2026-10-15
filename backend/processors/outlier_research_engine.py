"""
KIMIDORI Movie Auto - Outlier Research Engine
登録者数に対する再生回数の乖離度（外れ値・Outlier）を検出し、
アカウントの人気に依存しない「真の隠れテーマ（再現性のある需要）」を発掘する。
また、海外ビジネス洋書の知見を日本の職場カルチャーに翻案（日本化）する。
"""

import math
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import google.generativeai as genai
try:
    from youtubesearchpython import VideosSearch
except ImportError:
    VideosSearch = None

import config
from utils.key_manager import KeyManager

logger = logging.getLogger(__name__)


class OutlierResearchEngine:
    """Outlier動画（少フォロワー・高再生）の検出と隠れ需要テーマ解析エンジン"""

    def __init__(self, key_manager: Optional[KeyManager] = None, firestore_service: Any = None):
        self.key_manager = key_manager or KeyManager([config.GEMINI_API_KEY] if config.GEMINI_API_KEY else [])
        self.firestore = firestore_service

    def calculate_outlier_score(
        self,
        view_count: int,
        subscriber_count: int,
        days_since_published: int = 14
    ) -> float:
        """
        外れ値スコアの算出:
        Outlier Score = (再生数 / max(登録者数, 100)) * 経時減衰係数
        登録者数100〜500人で再生回数10万回の場合、スコアは 100〜500 超となり強烈なOutlierと判定される。
        """
        effective_subs = max(subscriber_count, 100)
        base_ratio = view_count / effective_subs
        recency_factor = 1.0 / (1.0 + math.log1p(max(days_since_published, 0) / 7.0))
        return round(base_ratio * recency_factor, 2)

    def _parse_views_string(self, views_str: str) -> int:
        """再生数文字列（例: '12万回視聴', '1.2M views', '3,450 views'）を数値に変換"""
        if not views_str or views_str == "N/A":
            return 1000
        clean = views_str.replace("回視聴", "").replace(" views", "").replace(",", "").strip()
        try:
            if "万" in clean:
                num = float(clean.replace("万", ""))
                return int(num * 10000)
            if "M" in clean or "m" in clean:
                num = float(clean.replace("M", "").replace("m", ""))
                return int(num * 1000000)
            if "K" in clean or "k" in clean:
                num = float(clean.replace("K", "").replace("k", ""))
                return int(num * 1000)
            return int(float(clean))
        except Exception:
            return 1000

    def search_outlier_topics(
        self,
        keyword: str,
        limit: int = 8,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        キーワードに関連する動画を検索し、登録者比再生数の高いOutlier動画を抽出
        """
        logger.info(f"Outlierリサーチ開始: キーワード='{keyword}'")
        raw_videos = []

        # 1. YouTube Data API (公式認証がある場合)
        if self.firestore and user_id:
            try:
                from services.youtube_service import YouTubeService
                yt_service = YouTubeService(self.firestore)
                yt_client = yt_service._get_authenticated_service(user_id)
                if yt_client:
                    search_res = yt_client.search().list(
                        q=f"{keyword} #shorts",
                        part="snippet",
                        maxResults=limit * 2,
                        type="video"
                    ).execute()

                    v_ids = [item["id"]["videoId"] for item in search_res.get("items", [])]
                    if v_ids:
                        v_details = yt_client.videos().list(
                            part="statistics,snippet",
                            id=",".join(v_ids)
                        ).execute()

                        for v_item in v_details.get("items", []):
                            v_id = v_item["id"]
                            v_title = v_item["snippet"]["title"]
                            v_views = int(v_item["statistics"].get("viewCount", 0))
                            v_channel_id = v_item["snippet"]["channelId"]

                            # チャンネル登録者数を取得
                            c_info = yt_client.channels().list(
                                part="statistics",
                                id=v_channel_id
                            ).execute()
                            c_items = c_info.get("items", [])
                            subs = int(c_items[0]["statistics"].get("subscriberCount", 500)) if c_items else 500

                            raw_videos.append({
                                "video_id": v_id,
                                "title": v_title,
                                "views": v_views,
                                "subscribers": subs,
                                "link": f"https://www.youtube.com/watch?v={v_id}"
                            })
            except Exception as e:
                logger.warning(f"公式YouTube API検索スキップ (フォールバックへ移行): {e}")

        # 2. VideosSearch によるスクレイピング検索 (フォールバック)
        if not raw_videos:
            try:
                vs = VideosSearch(f"{keyword} #shorts", limit=limit * 2)
                res = vs.result()
                for item in res.get("result", []):
                    v_id = item.get("id")
                    title = item.get("title")
                    view_text = item.get("viewCount", {}).get("text", "1000")
                    views = self._parse_views_string(view_text)

                    # チャンネルの登録者数推定 (スクレイピングデータから概算)
                    channel_info = item.get("channel", {})
                    channel_name = channel_info.get("name", "Unknown")

                    # 登録者数の推定 (初期値1,000人ベース)
                    estimated_subs = 1000

                    raw_videos.append({
                        "video_id": v_id,
                        "title": title,
                        "views": views,
                        "subscribers": estimated_subs,
                        "channel_name": channel_name,
                        "link": item.get("link", f"https://www.youtube.com/watch?v={v_id}")
                    })
            except Exception as e:
                logger.error(f"VideosSearch取得エラー: {e}")

        # 3. Outlierスコア算出とランキング
        analyzed_results = []
        for v in raw_videos:
            views = v.get("views", 1000)
            subs = v.get("subscribers", 1000)
            score = self.calculate_outlier_score(views, subs, days_since_published=14)
            is_outlier = (views >= 10000 and subs <= 3000) or (score >= 3.0)

            analyzed_results.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "views": views,
                "subscribers": subs,
                "outlier_score": score,
                "is_outlier": is_outlier,
                "link": v.get("link")
            })

        analyzed_results.sort(key=lambda x: (x["is_outlier"], x["outlier_score"], x["views"]), reverse=True)
        return analyzed_results[:limit]

    async def _resolve_supported_models(self, session: Any, key: str) -> List[str]:
        """APIキーが利用可能なGeminiモデル一覧を動的に取得・ソート"""
        default_prio = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-pro", "gemini-1.5-pro"]
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            async with session.get(url, timeout=8) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _non_text = ("tts", "image", "embedding", "veo", "imagen", "aqa", "audio", "robotics")
                    supported = [
                        m["name"].replace("models/", "")
                        for m in data.get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                        and not any(bad in m["name"].lower() for bad in _non_text)
                    ]
                    if supported:
                        prio = [m for m in default_prio if m in supported]
                        other_flash = [m for m in supported if "flash" in m.lower() and m not in prio]
                        rest = [m for m in supported if m not in prio and m not in other_flash]
                        return prio + other_flash + rest
        except Exception as e:
            logger.warning(f"モデル動的取得スキップ (デフォルト使用): {e}")
        return default_prio

    def _build_fallback_analysis(self, keyword: str, genre: str = "knowledge") -> Dict[str, Any]:
        """万が一のAPI通信失敗時にセーフガードとして良質な多角化切り口を自動生成"""
        return {
            "keyword": keyword,
            "hidden_demand_insight": f"「{keyword}」に関する最新の視聴者インサイト。定番の常識とは真逆の意外な事実や、日常生活に直結する知られざる裏側に強い関心が集まっています。",
            "proven_hooks": [
                f"実は9割の人が完全に誤解している「{keyword}」の衝撃事実",
                f"教科書では絶対に教えてくれない「{keyword}」の真実とは？"
            ],
            "diverse_angles": [
                {
                    "angle_id": 1,
                    "title": f"【常識逆転】教科書と正反対！「{keyword}」の本当の姿",
                    "concept": f"定番の固定観念を覆し、当時のリアルな一次記録や科学的根拠から意外なギャップを解き明かす切り口。",
                    "recommended_genre": genre
                },
                {
                    "angle_id": 2,
                    "title": f"【現代との比較】実は現代より過酷？「{keyword}」の知られざる裏側",
                    "concept": f"現代人の感覚からは想像もつかない当時の生活実態や驚きの知恵を対比して共感を呼ぶ切り口。",
                    "recommended_genre": genre
                },
                {
                    "angle_id": 3,
                    "title": f"【ドラマチック実話】命懸けの選択！「{keyword}」を生きた人々の記録",
                    "concept": f"単なる知識ではなく、当時の市井の人々が直面した困難とそれを乗り越えた驚きのエピソードに迫る物語的切り口。",
                    "recommended_genre": genre
                }
            ],
            "forbidden_tropes": [
                "「江戸時代＝うんち換金」などの手垢のついた陳腐なステレオタイプ",
                "表層的な年号や年表の丸暗記的な解説"
            ]
        }

    async def analyze_and_extract_hidden_angles(
        self,
        keyword: str,
        outlier_videos: List[Dict[str, Any]],
        genre: str = "knowledge"
    ) -> Dict[str, Any]:
        """
        外れ値（Outlier）動画群から、アカウントの知名度に依存しない『真の隠れテーマ』と
        多角的な切り口（Angles）をGeminiで抽出する。
        """
        evidence_text = "\n".join([
            f"- タイトル: {v['title']} (再生数: {v['views']}, 登録者数目安: {v['subscribers']}, 外れ値スコア: {v['outlier_score']})"
            for v in outlier_videos
        ]) if outlier_videos else f"- キーワード: {keyword} (競合データ自動補正)"

        prompt = f"""
あなたはYouTube Shortsおよび長尺動画のトップアナリストです。
以下のデータは、キーワード「{keyword}」に関連して、フォロワー数・知名度に依存せず「企画・テーマ自体の力（需要）」で再生数が跳ねた実際のヒット事例データです。

【外れ値動画・競合データ】:
{evidence_text}

【分析と多角化の厳格ルール】:
1. AIが持ちがちな安易な定番ステレオタイプ（例: 江戸＝うんち換金、都市伝説＝頭の上の余命数字、ビジネス＝45歳佐藤さんなど）は【絶対禁止】とします。
2. 登録者数が少ないのに跳ねている「真の理由（意外なギャップ、強烈な疑問、感情の揺さぶり）」を特定してください。
3. 同じ「{keyword}」であっても、毎回異なる視点から作れるように【多角的な切り口（Angles）を3つ】提案してください。

【出力フォーマット (厳格なJSON)】:
必ず以下のJSON形式のみを出力してください（```json ``` で囲んでください）。
{{
  "keyword": "{keyword}",
  "hidden_demand_insight": "知名度に依存せず再生が伸びている隠れ需要の本質分析（100〜150文字）",
  "proven_hooks": [
    "冒頭3秒で離脱を防ぐ実証済みフック案1",
    "冒頭3秒で離脱を防ぐ実証済みフック案2"
  ],
  "diverse_angles": [
    {{
      "angle_id": 1,
      "title": "切り口1のタイトル案",
      "concept": "この切り口の独自性と意外なファクト",
      "recommended_genre": "{genre}"
    }},
    {{
      "angle_id": 2,
      "title": "切り口2のタイトル案",
      "concept": "この切り口の独自性と意外なファクト",
      "recommended_genre": "{genre}"
    }},
    {{
      "angle_id": 3,
      "title": "切り口3のタイトル案",
      "concept": "この切り口の独自性と意外なファクト",
      "recommended_genre": "{genre}"
    }}
  ],
  "forbidden_tropes": ["使用を禁止する手垢のついた陳腐なステレオタイプ1", "使用禁止ステレオタイプ2"]
}}
"""

        import aiohttp
        import re

        async def _call(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                models_to_try = await self._resolve_supported_models(session, key)
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.8, "maxOutputTokens": 4096}
                }
                last_err = ""
                for m in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                            else:
                                err_body = await resp.text()
                                last_err = f"HTTP {resp.status} ({m}): {err_body[:120]}"
                                logger.warning(f"Outlier Gemini fail: {last_err}")
                    except Exception as ex:
                        last_err = str(ex)
                        continue
                raise RuntimeError(f"Gemini API呼び出し失敗: {last_err}")

        try:
            raw_text = await self.key_manager.execute_with_retry_async(_call)
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            json_str = m.group(1) if m else raw_text
            parsed = json.loads(json_str)
            if "diverse_angles" in parsed and len(parsed["diverse_angles"]) > 0:
                return parsed
        except Exception as e:
            logger.warning(f"Gemini隠れ需要分析例外 (セーフガードフォールバック適用): {e}")

        # 安全なフォールバックを返却
        return self._build_fallback_analysis(keyword, genre)


    async def adapt_western_business_book(
        self,
        book_concept_or_title: str,
        target_audience: str = "日本のビジネスパーソン（30代〜50代の中堅社員・管理職）"
    ) -> Dict[str, Any]:
        """
        海外ビジネス洋書・世界的ベストセラー（行動経済学、最新心理学、マネジメント理論など）を、
        日本のリアルな職場環境・人間関係（昭和気質の上司、板挟みの中間管理職、指示待ち部下）に翻案する。
        """
        prompt = f"""
あなたは最高峰のビジネス漫画原作者であり、一流のビジネス翻訳家・構成作家です。
以下の【海外ビジネス洋書・理論コンセプト】を、日本のビジネスパーソンが強烈に共感する【日本の職場ストーリー・漫画動画シナリオ】に翻案してください。

【対象コンセプト・洋書知見】:
{book_concept_or_title}

【ターゲット層】:
{target_audience}

【翻案の厳格ルール】:
1. 舞台設定: 日本の中堅企業・大手企業の営業部、開発部門、総務部など、具体的で泥臭い現場にする。
2. キャラクター構成:
   - 主人公 (実務で理不尽や停滞に悩む日本人社員)
   - 障壁・問題人物 (前例踏襲を強制する上司、モチベーションを失った部下、派閥争いなど)
   - 導き手/気づき (海外の最新知見・行動経済学の原理を実践的なアクションへ変換するアドバイス)
3. 抽象論の徹底排除: 理論名を振りかざすのではなく、「明日から職場のチャットや会議でそのまま使える具体的な声かけ・段取り」としてストーリーを解決へ導くこと。

【出力フォーマット (厳格なJSON)】:
必ず以下のJSON形式のみを出力してください（```json ``` で囲んでください）。
{{
  "original_concept": "{book_concept_or_title}",
  "japanese_adaptation_title": "共感度MAXの日本版ストーリータイトル",
  "workplace_setting": "舞台となる日本企業・部署の設定",
  "story_arc": {{
    "problem": "職場のリアルな理不尽・あるある問題（50〜80字）",
    "theory_insight": "理論・洋書知見の本質を現場目線で言い換えた核心（50〜80字）",
    "concrete_action": "主人公が実行する具体的な解決アクション（50〜80字）",
    "climax_and_result": "職場の空気や成果が劇的に好転する結末（50〜80字）"
  }}
}}
"""

        import aiohttp
        import re

        async def _call(key: str) -> str:
            async with aiohttp.ClientSession() as session:
                models_to_try = await self._resolve_supported_models(session, key)
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.75, "maxOutputTokens": 4096}
                }
                last_err = ""
                for m in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
                    try:
                        async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                            else:
                                err_body = await resp.text()
                                last_err = f"HTTP {resp.status} ({m}): {err_body[:120]}"
                                logger.warning(f"AdaptBook Gemini fail: {last_err}")
                    except Exception as ex:
                        last_err = str(ex)
                        continue
                raise RuntimeError(f"洋書翻案Gemini API呼び出し失敗: {last_err}")

        try:
            raw_text = await self.key_manager.execute_with_retry_async(_call)
            m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
            json_str = m.group(1) if m else raw_text
            parsed = json.loads(json_str)
            if "story_arc" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"洋書翻案Gemini例外 (セーフガードフォールバック適用): {e}")

        return {
            "original_concept": book_concept_or_title,
            "japanese_adaptation_title": f"職場の悩みを解決する知恵: {book_concept_or_title}",
            "workplace_setting": "日本の中堅企業・現場オフィス",
            "story_arc": {
                "problem": "前例主義の壁とコミュニケーションのすれ違い",
                "theory_insight": f"「{book_concept_or_title}」の原理を日常の小さな段取りに変換",
                "concrete_action": "チームの心理的安全性を高める具体的な声かけと情報共有",
                "climax_and_result": "職場の空気が一新され、周囲の信頼と成果を獲得"
            }
        }
