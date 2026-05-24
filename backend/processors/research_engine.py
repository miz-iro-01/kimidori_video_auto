import logging
import asyncio
from typing import List, Dict, Optional
import google.generativeai as genai

# Keyless YouTube Tools
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

logger = logging.getLogger(__name__)

class ResearchEngine:
    """最新トレンドのリサーチとライバル動画の解析を行うエンジン"""

    def __init__(self, gemini_api_key: str):
        if not gemini_api_key:
            raise ValueError("Gemini APIキーが設定されていません。")
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def search_trending_shorts(self, keyword: str, limit: int = 5) -> List[Dict]:
        """キーワードに関連するショート動画を検索"""
        logger.info(f"リサーチ開始: キーワード '{keyword}'")
        try:
            # YouTubeでの検索（"shorts" キーワードを付与してショート動画を狙う）
            search_query = f"{keyword} #shorts"
            videos_search = VideosSearch(search_query, limit=limit * 2)
            results = videos_search.result()
            
            videos = []
            for video in results.get('result', []):
                # ざっくりとショート動画（60秒以内）かを判定
                duration_str = video.get('duration', '0:00')
                if duration_str:
                    parts = duration_str.split(':')
                    if len(parts) == 2:
                        try:
                            seconds = int(parts[0]) * 60 + int(parts[1])
                            if seconds <= 90:  # 余裕を持って90秒以内
                                videos.append({
                                    "id": video.get("id"),
                                    "title": video.get("title"),
                                    "views": video.get("viewCount", {}).get("text", "N/A"),
                                    "link": video.get("link")
                                })
                        except ValueError:
                            pass
                
                if len(videos) >= limit:
                    break
                    
            return videos
        except Exception as e:
            logger.error(f"YouTube検索エラー: {e}")
            return []

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

    async def analyze_trend(self, keyword: str) -> Dict:
        """指定したキーワードで伸びている動画を分析し、最適な構成を提案する"""
        videos = self.search_trending_shorts(keyword, limit=3)
        if not videos:
            return {"error": "関連するショート動画が見つかりませんでした。別のキーワードを試してください。"}

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
            max_retries = 4
            delay = 10
            response = None
            for attempt in range(max_retries):
                try:
                    response = await self.model.generate_content_async(prompt)
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Gemini API limit exceeded (429), retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        raise
                        
            return {
                "success": True,
                "keyword": keyword,
                "analyzed_videos": analyzed_data,
                "analysis_result": response.text.strip()
            }
        except Exception as e:
            logger.error(f"Gemini解析エラー: {e}")
            return {"error": f"解析中にエラーが発生しました: {str(e)}"}
