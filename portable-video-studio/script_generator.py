import os
import json
import asyncio
import aiohttp
import re

class AIScriptGenerator:
    """
    AI自動リサーチ超高速台本生成エンジン
    ・【長尺動画モード】: 15〜20分 / 全5章並列 / 160〜180カット完全保証
    ・【ショート動画モード】: 60秒 / YouTube Shorts・TikTok・Reels特化 / 10〜15カット
    ・ジャンル（ストーリー・ドラマ / ビジネス・解説 / 江戸文化・歴史）に応じた完全特化型シナリオ構築
    ・固定テンプレ（PCのブルーライト等）を完全撤廃し、テーマに合わせた多彩な情景描写
    ・ストーリー系では「解説者」を完全排除し、登場人物のセリフ・会話劇中心の本格ドラマを生成
    """
    def __init__(self, api_key: str = None, user_data_dir: str = "./chrome_profile"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.user_data_dir = os.path.abspath(user_data_dir)

    async def _generate_single_chapter(self, session, ch, theme, genre, key):
        """1つの章を高可用性Geminiモデルで高速リサーチ生成"""
        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.1-flash-lite-preview"
        ]
        
        # ジャンル別のプロンプト設計
        if genre in ["story", "drama"]:
            genre_instruction = f"""
【ジャンル特化ルール（ストーリー・ドラマ・漫画動画）】:
1. 「解説者」や「スタジオ」は【一切登場させないでください（厳禁）】。
2. 主人公（具体的な名前、例：佐藤、タクヤ、健一など）と、周囲の登場人物（妻、同僚、上司、友人、子供など）による【リアルな会話劇（セリフ）】を中心に構成してください。
3. ナレーションは情景説明や心情の補足として適度に使用してください。
4. 【固定テンプレの禁止】:
   - 「PCのブルーライトが顔を青白く照らし」などの使い回し表現は【使用禁止】です。
   - テーマ「{theme}」に相応しい、多彩な生活環境・職場・街頭・家庭・カフェ・駅など臨場感あるシチュエーションを毎回新規に描写してください。
5. 出力フォーマット（厳守）:
   Cut_{ch['base_cut']:03d}
   ト書き：（場所、状況、登場人物の表情や動作）
   【話者名】「セリフ または ナレーション本文」
   【演出】：動画 (アクション) / ズームイン / パン / 固定
"""
        elif genre in ["edoculture", "ukiyoe"]:
            genre_instruction = f"""
【ジャンル特化ルール（江戸の暮らし・浮世絵雑学・歴史）】:
1. 語り手は【ナレーター】のみで統一してください（キャラの寸劇やセリフは不要です）。
2. 現代と江戸を行き来する構成や、現代のサラリーマン・現代のオフィス・PC・ビジネス書・英語タイトルは【完全使用禁止】です。
3. すべてのカット（ト書き・本文）は、純粋な江戸時代の風景（木造長屋、日本橋の大通り、行灯の灯る夜道、職人の工房、活気ある蕎麦屋の店先、大川の渡し船など）と、江戸の歴史・風俗・文化の雑学解説のみで構成してください。
4. 出力フォーマット（厳守）:
   Cut_{ch['base_cut']:03d}
   ト書き：（江戸の風景、長屋、街道、登場人物の衣装や所作）
   【ナレーター】「解説テキスト」
   【演出】：動画 (アクション) / ズームイン / パン / 固定
"""
        else: # business, finance, trivia, history
            genre_instruction = f"""
【ジャンル特化ルール（ビジネス・洋書解説・教養・経済）】:
1. 語り手は【ナレーション】のみで統一してください。「メイン解説者」「解説者」という話者名は【使用禁止】です。
2. 【ナレーション】による論理的で明快な解説、データや図解、具体例を交えて展開してください。
3. 【固定テンプレの禁止】:
   - 「深夜の薄暗い書斎でPCのブルーライト」といったワンパターンな冒頭は避け、テーマ「{theme}」に合わせて、朝の通勤風景、オフィス、街頭、カフェ、スマホ画面など多彩なシチュエーションから始めてください。
4. 出力フォーマット（厳守）:
   Cut_{ch['base_cut']:03d}
   ト書き：（状況、スライド、人物、背景）
   【ナレーション】「解説テキスト」
   【演出】：動画 (アクション) / ズームイン / パン / 固定
"""

        prompt = f"""
あなたはYouTubeで100万再生を連発する大ヒット動画のプロの脚本家・構成作家です。
【テーマ】: {theme}
【ジャンル】: {genre}
【担当チャプター】: 第{ch['num']}章（{ch['title']}）

{genre_instruction}

【必須ボリューム & 演出ルール】:
1. 必ず {ch['target_cuts']} カット以上のボリュームで長尺かつ具体的に執筆してください（要約・省略・端折りは厳禁）。
2. 第1章の冒頭（Cut_001〜Cut_003付近）には視聴者を引き込むため、2〜3カット「【演出】：動画 (アクション)」を指定してください。
3. 各章のクライマックスや感情が動くシーンにも適度に「【演出】：動画 (アクション)」を差し込んでください。
"""

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 8192}
        }

        last_error = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            return ch['num'], candidates[0]["content"]["parts"][0]["text"]
                    else:
                        err_txt = await resp.text()
                        last_error = f"HTTP {resp.status}: {err_txt}"
            except Exception as e:
                last_error = str(e)

        raise RuntimeError(f"第{ch['num']}章の生成に失敗しました: {last_error}")

    async def _generate_short_script(self, session, theme: str, genre: str, key: str) -> str:
        """60秒の縦型ショート動画用台本（全6〜7カット・各8〜10秒・全カット動画演出）を生成"""
        models_to_try = [
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest"
        ]

        if genre in ["edoculture", "ukiyoe"]:
            genre_rules = """
・【完全ナレーション解説形式】：現代のキャラクターや日常会話の寸劇・コントは一切出さないこと。
・純粋な【ナレーター】による知的好奇心を刺激するテンポの良い歴史・浮世絵雑学解説。
・全カット【演出】：動画（浮世絵アニメーション動画）として構成すること。
・各カットは8〜10秒程度（全6〜7カットで合計55〜60秒）。
・ト書きは、江戸時代の情緒ある本物の浮世絵・木版画（町並み、職人、町人、夜道、長屋、大名行列、蕎麦屋など）の情景を描写すること。
"""
        elif genre in ["story", "drama"]:
            genre_rules = """
・主人公によるテンポの良いリアルなストーリー展開。
・0秒〜10秒で視聴者の手を止めさせる衝撃の冒頭からスタート。
・全カット【演出】：動画（ダイナミック動画演出）。
"""
        else:
            genre_rules = """
・【ナレーター】による論理的で痛快な知的ショート解説。
・冒頭3秒で「9割の人が勘違いしている〇〇の真実」など強烈なフックを入れる。
・全カット【演出】：動画（動画クリップ演出）。
"""

        prompt = f"""
あなたはYouTube ShortsやTikTokで100万回再生を連発するショート動画のトッププロデューサーです。
以下のテーマで、厳密に【60秒尺（全6〜7カット、各8〜10秒、合計55〜60秒）】の超高エンゲージメント動画台本を作成してください。

【テーマ】: {theme}
【ジャンル】: {genre}

{genre_rules}

【タイムライン構成（合計55〜60秒・全6〜7カット）】:
1. Cut_001 [00:00]: 【強烈なフック】最初の3秒でスクロールを止める驚きの事実・問いかけ（8秒）
2. Cut_002 [00:08]: 【知られざる事実】誰も知らない驚愕の事実・背景（9秒）
3. Cut_003 [00:17]: 【驚きの仕組み・秘密】どうしてそれが可能だったのか？（9秒）
4. Cut_004 [00:26]: 【衝撃のディテール・職人技】具体的なエピソード・数字・伝説（9秒）
5. Cut_005 [00:35]: 【意外な展開・庶民の反応】当時の人々の熱狂や裏話（9秒）
6. Cut_006 [00:44]: 【現代への教訓・オチ】現代とつながる本質・締めくくり（10秒）
7. Cut_007 [00:54]: 【行動喚起】チャンネル登録・保存を促すエンディング（6秒）※任意

【出力フォーマット（厳守）】:
Cut_001
[00:00]
ト書き：（江戸時代の情緒ある浮世絵の情景、場所、町人の動作など）
【ナレーター】「ナレーション文章（聞き取りやすく引き込まれる解説）」
【演出】：動画 (浮世絵アニメーション動画)

Cut_002
[00:08]
ト書き：（...）
【ナレーター】「...」
【演出】：動画 (...)
...
"""

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 4096}
        }

        last_error = None
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                async with session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            body = candidates[0]["content"]["parts"][0]["text"].strip()
                            genre_label = "ストーリー・ドラマ" if genre in ["story", "drama"] else ("江戸の暮らし・浮世絵雑学" if genre in ["edoculture", "ukiyoe"] else "ビジネス・解説")
                            header = f"""【タイトル】: {theme}
【選定テーマ】: {theme}
■ 動画タイプ: ショート動画 (60秒 / 9:16縦型)
■ 動画ジャンル: {genre_label} ({genre})
■ 目標尺: 60秒 (全6〜7カット・全編動画構成)
■ 構成方針: ナレーション解説とダイナミック浮世絵動画で展開するバイラルショート動画。

==================================================

"""
                            return header + body
                    else:
                        err_txt = await resp.text()
                        last_error = f"HTTP {resp.status}: {err_txt}"
            except Exception as e:
                last_error = str(e)

        raise RuntimeError(f"ショート動画台本の生成に失敗しました: {last_error}")

    async def generate_script_via_api(self, theme: str, genre: str = "business", target_length_minutes: int = 18, api_key: str = None, video_type: str = "long") -> str:
        key = api_key or self.api_key
        if not key:
            raise ValueError("Gemini API キーが入力されていません。上部の入力欄に Google AI Studio の API キーを設定してください。")

        # ショート動画（60秒）の分岐
        if video_type == "short" or target_length_minutes <= 1:
            async with aiohttp.ClientSession() as session:
                return await self._generate_short_script(session, theme, genre, key)

        # 長尺動画（15〜20分 / 全5章並列）
        if genre in ["story", "drama"]:
            chapters = [
                {"num": 1, "title": "オープニング・主人公の日常と葛藤の始まり (テーマに関わる生活・職場・人間関係の異変)", "target_cuts": 35, "base_cut": 1},
                {"num": 2, "title": "転換点・事件と対立 (登場人物たちとの摩擦・衝撃の事実の発覚)", "target_cuts": 35, "base_cut": 36},
                {"num": 3, "title": "葛藤と決意・行動の開始 (仲間との対話・新たな選択と試練)", "target_cuts": 40, "base_cut": 71},
                {"num": 4, "title": "クライマックス・逆転劇 (行動の結果・運命が大きく好転する瞬間)", "target_cuts": 40, "base_cut": 111},
                {"num": 5, "title": "エピローグ・新たな未来 (登場人物たちの成長・希望に満ちた結末)", "target_cuts": 30, "base_cut": 151}
            ]
        elif genre in ["edoculture", "ukiyoe"]:
            chapters = [
                {"num": 1, "title": "オープニング・江戸の驚きの知恵と風俗 (大通り・日本橋・町人の活気)", "target_cuts": 35, "base_cut": 1},
                {"num": 2, "title": "江戸庶民のリアルな日常と暮らし (木造長屋・助け合い・粋な暮らしぶり)", "target_cuts": 35, "base_cut": 36},
                {"num": 3, "title": "江戸の食文化と驚異の出前システム (蕎麦・寿司・屋台・職人の技)", "target_cuts": 40, "base_cut": 71},
                {"num": 4, "title": "江戸の商いと経済・サステナブル社会 (独自の通貨・リサイクル文化・活気ある商家)", "target_cuts": 40, "base_cut": 111},
                {"num": 5, "title": "まとめ・江戸の知恵が教えてくれる心豊かな生き方・エンディング", "target_cuts": 30, "base_cut": 151}
            ]
        else: # business, finance, trivia, history
            chapters = [
                {"num": 1, "title": "オープニング・現代の盲点と問題提起 (テーマに関する衝撃の現実とフック)", "target_cuts": 35, "base_cut": 1},
                {"num": 2, "title": "なぜ多くの人が失敗するのか？ (行動経済学・心理学・社会構造の落とし穴)", "target_cuts": 35, "base_cut": 36},
                {"num": 3, "title": "成功・解決への黄金法則・コア習慣①② (世界的研究・具体的データと実践例)", "target_cuts": 40, "base_cut": 71},
                {"num": 4, "title": "今日からできる実践アクション・習慣③ (具体的ノウハウと図解)", "target_cuts": 40, "base_cut": 111},
                {"num": 5, "title": "まとめ・明日からの行動指針・エンディング", "target_cuts": 30, "base_cut": 151}
            ]

        genre_label = "ストーリー・ドラマ" if genre in ["story", "drama"] else ("江戸の暮らし・浮世絵雑学" if genre in ["edoculture", "ukiyoe"] else "ビジネス・解説")

        header_text = f"""【タイトル】: {theme}
【選定テーマ】: {theme}
■ 動画タイプ: 長尺動画 ({target_length_minutes}分 / 16:9横型)
■ 動画ジャンル: {genre_label} ({genre})
■ 目標尺: {target_length_minutes}分 (全5章構成 / 全160〜180カット)
■ 構成方針: ジャンル特性に最適化した本格長尺シナリオ。

=================================================="""

        # 5章を完全並列実行 (超高速10秒)
        async with aiohttp.ClientSession() as session:
            tasks = [self._generate_single_chapter(session, ch, theme, genre, key) for ch in chapters]
            results = await asyncio.gather(*tasks)

        # 章順にソートして連結
        results.sort(key=lambda x: x[0])
        body_parts = []
        for num, text in results:
            ch_info = next(c for c in chapters if c['num'] == num)
            body_parts.append(f"\n\n--- 【第{num}章：{ch_info['title']}】 ---\n\n" + text.strip())

        full_script = header_text + "".join(body_parts)
        try:
            from storyboard_generator import parse_script_to_storyboard, normalize_script_with_timestamps
            cuts = parse_script_to_storyboard(full_script, genre=genre, video_mode="hook_only")
            full_script = normalize_script_with_timestamps(full_script, cuts)
        except Exception as e_norm:
            print(f"[SCRIPT NORM WARNING] {e_norm}")

        return full_script

    # 互換用エイリアス
    generate_script = generate_script_via_api

