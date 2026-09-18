import logging
import asyncio
from typing import List, Dict, Optional
import google.generativeai as genai
import config

# Keyless YouTube Tools
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

logger = logging.getLogger(__name__)

class ResearchEngine:
    """最新トレンドのリサーチとライバル動画の解析を行うエンジン"""

    def __init__(self, gemini_api_key: str, firestore_service=None):
        if not gemini_api_key:
            raise ValueError("Gemini APIキーが設定されていません。")
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)
        self.fallback_models = config.GEMINI_FALLBACK_MODELS
        self.firestore = firestore_service

    async def _try_generate(self, prompt: str) -> str:
        """フォールバックモデルを含めてGemini APIを高信頼性で呼び出す"""
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-2.0-flash-lite"
        ]
        
        last_error = None
        # 1. google.generativeai SDKによる試行
        for model_name in models_to_try:
            try:
                logger.info(f"Gemini API呼び出し (research): model={model_name}")
                model = genai.GenerativeModel(model_name)
                response = await asyncio.wait_for(model.generate_content_async(prompt), timeout=30.0)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                err_str = str(e)
                last_error = e
                logger.warning(f"モデル {model_name} でSDKエラー ({err_str[:150]})、次を試します。")
                continue

        # 2. SDKが全滅した場合はREST API経由で直接再試行（portable-video-studio方式）
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
            }
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
                try:
                    async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates and "content" in candidates[0]:
                                parts = candidates[0]["content"].get("parts", [])
                                if parts and "text" in parts[0]:
                                    return parts[0]["text"].strip()
                        else:
                            err_txt = await resp.text()
                            last_error = f"HTTP {resp.status}: {err_txt[:150]}"
                except Exception as e:
                    last_error = e
                    continue

        raise Exception(
            f"Geminiリサーチ解析が一時的に混雑しています。しばらく時間をおいて再試行してください。(詳細: {last_error})"
        )

    def search_trending_shorts(self, keyword: str, limit: int = 5, user_id: str = None) -> List[Dict]:
        """キーワードに関連する動画を検索"""
        logger.info(f"リサーチ開始: キーワード '{keyword}'")
        videos = []
        
        # 1. ユーザーのYouTube連携があれば公式APIを試す
        if self.firestore and user_id:
            try:
                from services.youtube_service import YouTubeService
                yt_service = YouTubeService(self.firestore)
                youtube_client = yt_service._get_authenticated_service(user_id)
                
                if youtube_client:
                    logger.info("公式YouTube APIを使用して検索します...")
                    search_response = youtube_client.search().list(
                        q=f"{keyword} #shorts",
                        part="snippet",
                        maxResults=limit,
                        type="video"
                    ).execute()
                    
                    for item in search_response.get("items", []):
                        videos.append({
                            "id": item["id"]["videoId"],
                            "title": item["snippet"]["title"],
                            "views": "N/A",
                            "link": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                        })
                    
                    if videos:
                        return videos
            except Exception as e:
                logger.warning(f"公式YouTube API検索失敗: {e}")

        # 2. 公式APIが使えない、または失敗した場合はフォールバック
        logger.info("非公式スクレイピング(VideosSearch)で検索します...")
        try:
            # YouTubeでの検索（"shorts" キーワードを付与してショート動画を優先的に狙う）
            search_query = f"{keyword} #shorts"
            videos_search = VideosSearch(search_query, limit=limit)
            results = videos_search.result()
            
            for video in results.get('result', []):
                videos.append({
                    "id": video.get("id"),
                    "title": video.get("title"),
                    "views": video.get("viewCount", {}).get("text", "N/A"),
                    "link": video.get("link")
                })
                
                if len(videos) >= limit:
                    break
                    
            return videos
        except Exception as e:
            logger.error(f"YouTube検索エラー: {e}")
            return videos

    def fetch_transcript(self, video_id: str) -> Optional[str]:
        """動画の字幕（トーク内容）を取得。手動/自動生成/翻訳/英語など多段階で取得を試みる"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # 多段階の取得フォールバック
            transcript = None
            
            # 1. 日本語（手動）
            try:
                transcript = transcript_list.find_manually_created_transcript(['ja'])
            except Exception:
                pass
                
            # 2. 日本語（自動生成）
            if not transcript:
                try:
                    transcript = transcript_list.find_generated_transcript(['ja'])
                except Exception:
                    pass
            
            # 3. 英語（手動または自動生成）
            if not transcript:
                try:
                    transcript = transcript_list.find_transcript(['en'])
                except Exception:
                    pass
                    
            # 4. その他の言語があれば自動で日本語に翻訳する
            if not transcript:
                try:
                    # 最初の字幕を何でもいいから取得
                    raw_transcript = next(iter(transcript_list))
                    transcript = raw_transcript.translate('ja')
                except Exception:
                    pass
                    
            if not transcript:
                return None
                
            data = transcript.fetch()
            formatter = TextFormatter()
            text = formatter.format_transcript(data)
            return text[:1000]
        except Exception as e:
            logger.warning(f"字幕取得失敗 ({video_id}): {e}")
            return None

    async def analyze_trend(self, keyword: str, user_id: str = None) -> Dict:
        """指定したキーワードで伸びている動画を分析し、最適な構成を提案する"""
        videos = self.search_trending_shorts(keyword, limit=3, user_id=user_id)
        if not videos:
            logger.warning("YouTubeから動画情報を取得できませんでした。Gemini内部知識フォールバックを実行します。")
            prompt = f"""
あなたはプロのYouTubeショート動画コンサルタントです。
現在、キーワード「{keyword}」でバズる動画を作成するための具体的な戦略を提案してください。
（※現在YouTubeの検索APIが一時的に制限されているため、あなたの内部知識から「このキーワードでよく伸びる動画の傾向」を推測してください。）

以下のフォーマットに沿って分析結果をまとめてください。
1. 【トレンドの傾向】: なぜこれらの動画が伸びているのか？（テーマ性、切り口など）
2. 【最強のフック（冒頭1〜3秒）の提案】: 視聴者を逃さないための冒頭のセリフ案を3つ。
3. 【推奨される台本の構成】: 例（フック→共感→解決策→オチ）など。
4. 【狙うべきターゲット・感情】: どんな悩みを持つ人に向けて、どんな感情（驚き、納得など）を引き起こすべきか。
"""
            try:
                analysis_text = await self._try_generate(prompt)
                return {
                    "success": True,
                    "keyword": keyword,
                    "analyzed_videos": [],
                    "analysis_result": f"【※YouTube検索制限時のため、AI内部知識による推測リサーチ】\n\n{analysis_text}"
                }
            except Exception as e:
                return {"error": "リサーチ処理が完全に失敗しました。しばらく時間をおいて再試行してください。"}

        analyzed_data = []
        combined_text = ""

        for v in videos:
            transcript = self.fetch_transcript(v["id"])
            analyzed_data.append(v)
            if transcript:
                combined_text += f"【タイトル】: {v['title']}\n【再生数】: {v['views']}\n【字幕内容】:\n{transcript}\n\n"
            else:
                combined_text += f"【タイトル】: {v['title']}\n【再生数】: {v['views']}\n【字幕内容】: （字幕を取得できませんでした。タイトルから動画内容を推測して分析してください）\n\n"

        if not combined_text:
            return {"error": "動画情報の取得に失敗しました。別のキーワードを試してください。"}

        # Geminiによるトレンド解析
        prompt = f"""
あなたはプロのYouTubeショート動画コンサルタントです。
以下のデータは、キーワード「{keyword}」で現在再生回数が伸びている実際のYouTubeショート動画のタイトルと字幕（台本）です。

{combined_text}

この成功事例を徹底的に分析し、ユーザーが次に作るべき「バズるショート動画」の具体的な戦略を提案してください。
以下のフォーマットに沿って分析結果をまとめてください。

1. 【トレンドの傾向】: なぜこれらの動画が伸びているのか？（テーマ性、切り口など）
2. 【最強のフック（冒頭1〜3秒）の提案】: 視聴者を逃さないための冒頭のセリフ案を3つ。
3. 【推奨される台本の構成】: 例（フック→共感→解決策→オチ）など。
4. 【狙うべきターゲット・感情】: どんな悩みを持つ人に向けて、どんな感情（驚き、納得など）を引き起こすべきか。
"""
        try:
            analysis_text = await self._try_generate(prompt)
            return {
                "success": True,
                "keyword": keyword,
                "analyzed_videos": analyzed_data,
                "analysis_result": analysis_text
            }
        except Exception as e:
            logger.error(f"Gemini解析エラー: {e}")
            return {"error": f"解析中にエラーが発生しました: {str(e)}"}
