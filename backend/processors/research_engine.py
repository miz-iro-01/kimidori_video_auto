import logging
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
        """動画の字幕（トーク内容）を取得"""
        try:
            # 日本語を優先して字幕を取得
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
            formatter = TextFormatter()
            text = formatter.format_transcript(transcript_list)
            # 長すぎる場合はカット（1000文字程度）
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
            if transcript:
                analyzed_data.append(v)
                combined_text += f"【タイトル】: {v['title']}\n【再生数】: {v['views']}\n【字幕内容】:\n{transcript}\n\n"

        if not combined_text:
            return {"error": "動画はみつかりましたが、解析可能な字幕（トーク）がありませんでした。"}

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
            response = self.model.generate_content(prompt)
            return {
                "success": True,
                "keyword": keyword,
                "analyzed_videos": analyzed_data,
                "analysis_result": response.text.strip()
            }
        except Exception as e:
            logger.error(f"Gemini解析エラー: {e}")
            return {"error": f"解析中にエラーが発生しました: {str(e)}"}
