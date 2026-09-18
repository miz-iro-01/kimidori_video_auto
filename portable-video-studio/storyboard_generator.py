import re
import json
from typing import Tuple, List, Dict, Any

def parse_time_to_seconds(t_str: str) -> float:
    """[MM:SS] または [HH:MM:SS] を秒数に変換"""
    parts = t_str.strip("[] ").split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0.0

def clean_dialogue_text(text: str) -> str:
    """
    セリフやナレーションからト書き・演出括弧・話者名プレフィックスを除去して純粋な発話テキストを抽出
    """
    cleaned = text
    cleaned = re.sub(r'[（\(][^）\)]*?(?:心の中|表情|息|沈黙|汗|声|笑み|ため息|焦り|驚き|叫び|呟き|独白|ト書き|演出|ナレーション|視線|動作)[^）\)]*?[）\)]', '', cleaned)
    cleaned = re.sub(r'^[（\(][^）\)]*?[）\)]\s*', '', cleaned)
    cleaned = re.sub(r'^(?:メイン解説者|解説者|ナレーション|セリフ|ト書き|話者|キャラクター|語り手|語り|解説)[：:\s]*', '', cleaned)
    cleaned = cleaned.strip("「」『』\"' \t\r\n")
    return cleaned

def extract_speaker_and_dialogue(line: str, desc: str, known_characters: List[str] = None) -> Tuple[str, str, bool]:
    """
    台本の1行から話者名とセリフ本文を抽出
    """
    speaker = "ナレーション"
    dialogue = ""
    is_speech = False

    m = re.search(r'【([^】]+)】[：:\s]*(.*)', line)
    if m:
        spk_tag = m.group(1).strip()
        rest = m.group(2).strip()

        if spk_tag in ["ナレーション", "語り", "解説", "メイン解説者", "解説者", "語り手", "ナレーター"]:
            speaker = "ナレーション"
            is_speech = False
        elif spk_tag in ["セリフ", "話者名", "キャラクター名", "人物名", "話者", "キャラクター", "男", "女", "主人公"]:
            # 既知のキャラクターまたはト書きから推測
            if known_characters and len(known_characters) > 0:
                speaker = known_characters[0]
            else:
                speaker = "主人公"
            is_speech = True
        else:
            speaker = spk_tag
            is_speech = True

        dialogue = clean_dialogue_text(rest)
    elif line.startswith("「") or line.startswith("『"):
        dialogue = clean_dialogue_text(line)
        is_speech = True
        if known_characters and len(known_characters) > 0:
            speaker = known_characters[0]
        else:
            speaker = "主人公"
    else:
        dialogue = clean_dialogue_text(line)
        is_speech = False

    return speaker, dialogue, is_speech

def dynamic_extract_characters_and_locations(script_text: str, genre: str = "business", style: str = "manga_color") -> Tuple[str, str, List[Dict[str, Any]], Dict[str, str]]:
    """
    【完全動的解析エンジン】
    台本テキスト全体を走査し、台本に実際に登場する：
    1. 全キャラクター（名前・年齢・外見・服装・役割）
    2. 全主要舞台・背景ロケーション（場所名・時間帯・美術プロンプト）
    を100%動的に抽出・構築する。
    """
    # ----------------------------------------------------
    # ① キャラクターの動的抽出
    # ----------------------------------------------------
    # 1. 話者タグからユニークな登場人物を収集
    raw_speakers = re.findall(r'【([^】]+)】', script_text)
    invalid_tags = ["選定テーマ", "テーマ", "演出", "サムネイル画像", "ナレーション", "語り", "解説", "メイン解説者", "解説者", "語り手", "ナレーター", "ト書き", "セリフ", "話者", "キャラクター"]
    character_names = []
    for s in raw_speakers:
        s_clean = s.strip()
        if s_clean and s_clean not in invalid_tags and s_clean not in character_names:
            character_names.append(s_clean)

    # 2. 主人公情報の抽出
    protagonist_name = ""
    protagonist_age = ""
    m_p = re.search(r'主人公[・:\s]*([^\n（(]+)(?:[（(](\d+)[）)])?', script_text)
    if m_p:
        protagonist_name = m_p.group(1).strip()
        if m_p.group(2):
            protagonist_age = m_p.group(2).strip()

    if not protagonist_name and character_names:
        protagonist_name = character_names[0]

    # ジャンル別のデフォルト設定
    is_edo = genre in ["edoculture", "ukiyoe"] or "江戸" in script_text or "長屋" in script_text or "町人" in script_text or style == "ukiyoe"
    is_scifi = genre in ["scifi", "future"] or "宇宙" in script_text or "ロボット" in script_text or "サイバー" in script_text
    is_school = "高校" in script_text or "生徒" in script_text or "教室" in script_text or "制服" in script_text

    char_dict = {}
    roster_descriptions = []

    # 各キャラクターのプロファイル構築
    for idx, cname in enumerate(character_names):
        if is_edo:
            if "女" in cname or "妻" in cname or "娘" in cname:
                c_desc = f"{cname}（江戸時代の町娘・女性、伝統的な着物・帯姿、日本髪、穏やかな和風の顔立ち）"
            elif "武士" in cname or "侍" in cname:
                c_desc = f"{cname}（江戸時代の武士、裃・羽織袴姿、ちょんまげ、凛々しい表情）"
            elif "商人" in cname or "店主" in cname:
                c_desc = f"{cname}（江戸時代の商人、前掛け付きの着物姿、ちょんまげ、愛想の良い表情）"
            else:
                c_desc = f"{cname}（江戸時代の町人・職人、伝統的な半纏や着物姿、ちょんまげ、生き生きとした表情）"
        elif is_school:
            if "女" in cname or "妻" in cname or "娘" in cname:
                c_desc = f"{cname}（日本の女子生徒、制服ブレザーまたはセーラー服、黒髪）"
            else:
                c_desc = f"{cname}（日本の男子生徒、学ランまたはブレザー制服、若々しい顔立ち）"
        elif is_scifi:
            c_desc = f"{cname}（近未来の登場人物、発光ラインのあるスタイリッシュなジャケット）"
        else: # 現代・ビジネス・ドラマ
            if "課長" in cname or "部長" in cname or "上司" in cname:
                c_desc = f"{cname}（50代男性管理職、シャープな顔立ち、眼鏡、ダークスーツ、赤ネクタイ）"
            elif "若手" in cname or "後輩" in cname or "三浦" in cname or "新人" in cname:
                c_desc = f"{cname}（20代若手男性社員、爽やかな顔立ち、黒髪短髪、スリムなブルースーツ）"
            elif "妻" in cname or "美和子" in cname or "母" in cname:
                c_desc = f"{cname}（40代女性、優しい表情、肩までの茶髪、家庭的なニットとエプロン）"
            elif idx == 0 or cname == protagonist_name:
                c_desc = f"{cname}（40代男性主人公、誠実で落ち着いた顔立ち、ダークグレースーツ）"
            else:
                c_desc = f"{cname}（日本の登場人物、自然な表情、清潔感ある服装）"

        char_dict[cname] = c_desc
        roster_descriptions.append(f"{idx+1}) {c_desc}")

    # 主人公プロファイル
    if is_edo:
        char_profile = "江戸時代の町人・職人・旅人、伝統的な和服・着物姿、葛飾北斎・歌川広重風の本格的な浮世絵木版画美術スタイル（現代アニメ風禁止・実写禁止・現代の服装禁止）"
    elif protagonist_name and protagonist_name in char_dict:
        char_profile = char_dict[protagonist_name]
    else:
        char_profile = "日本の男性主人公（45歳会社員、誠実な顔立ち、ダークグレースーツ、2Dカラー漫画スタイル）"

    # キャラクター集合シートプロンプト
    if is_edo:
        char_roster_prompt = (
            "日本の本格的な伝統浮世絵・木版画スタイル（喜多川歌麿・東洲斎写楽・歌川国芳風の伝統木版画美術、和紙の質感、伝統的な日本の色彩、実写禁止、現代風アニメ塗り禁止、英語禁止）。"
            "江戸時代の町人、商人、職人、町娘の風俗画・人物画のラインナップシート。背景は和紙の風合い。"
        )
    elif roster_descriptions:
        char_roster_prompt = (
            "日本の高品質な2Dカラー漫画・アニメキャラクター設定シート、白背景、クリーンな線画、セル画塗り、16:9横型画面："
            + " ".join(roster_descriptions)
        )
    else:
        char_roster_prompt = (
            f"日本の高品質な2Dカラー漫画・アニメキャラクター設定シート、白背景、クリーンな線画、セル画塗り、16:9横型画面：{char_profile}"
        )

    # ----------------------------------------------------
    # ② シーン背景・舞台（ロケーション）の動的抽出
    # ----------------------------------------------------
    descs = re.findall(r'ト書き[：:\s]*[（\(]?([^）\)\n]+)[）\)]?', script_text)
    all_desc_text = " ".join(descs) + " " + script_text

    if is_edo:
        # 江戸時代専用の本格浮世絵ロケーション群（現代のオフィスやリビングは完全排除）
        potential_locations = [
            {"id": "loc_edo_street", "name": "江戸の大通り・日本橋", "keys": ["日本橋", "大通り", "町並み", "街道", "橋", "賑わい", "町", "出前"],
             "prompt": "日本の伝統的な浮世絵・木版画スタイル（江戸の賑わう大通り・日本橋、木造建築の商家、石畳、行灯、提灯、和紙の質感と木版の擦れ、葛飾北斎・歌川広重風の情緒ある伝統美術、実写禁止、現代物禁止）"},
            {"id": "loc_edo_nagaya", "name": "江戸の長屋・路地裏", "keys": ["長屋", "路地", "井戸", "部屋", "家", "暮らし", "台所", "住まい"],
             "prompt": "日本の伝統的な浮世絵・木版画スタイル（江戸の庶民が暮らす木造長屋、路地裏、井戸端、格子戸、和紙テクスチャ、葛飾北斎風の情緒ある伝統美術、実写禁止、現代物禁止）"},
            {"id": "loc_edo_shop", "name": "江戸の蕎麦屋・茶屋・屋台", "keys": ["蕎麦", "茶屋", "屋台", "店", "食事", "料理", "看板", "うどん"],
             "prompt": "日本の伝統的な浮世絵・木版画スタイル（江戸の活気ある蕎麦屋や茶屋の店先、暖簾、湯気の立つ大鍋、木製看板、歌川広重風の伝統木版画美術、和紙の質感、実写禁止、現代物禁止）"},
            {"id": "loc_edo_river", "name": "大川・隅田川・渡し船と富士山", "keys": ["川", "大川", "隅田川", "舟", "渡し船", "富士山", "空", "青空"],
             "prompt": "日本の伝統的な浮世絵・木版画スタイル（大川の渡し船、遠くに見える雄大な富士山、青空と白い雲、葛飾北斎・富嶽三十六景風の伝統木版画美術、和紙の質感、実写禁止、現代物禁止）"},
            {"id": "loc_edo_night", "name": "江戸の月夜・行灯の灯る夜景", "keys": ["夜", "月", "三日月", "行灯", "提灯", "柳", "夜道"],
             "prompt": "日本の伝統的な浮世絵・木版画スタイル（三日月が浮かぶ江戸の夜空、川沿いの柳の木、行灯・提灯の柔らかな灯り、歌川広重・名所江戸百景風の情緒ある夜景美術、和紙の質感、実写禁止、現代物禁止）"}
        ]
    else:
        # 現代・ビジネス・学園ロケーション群
        potential_locations = [
            {"id": "loc_office", "name": "オフィス・職場", "keys": ["オフィス", "職場", "デスク", "会議室", "会社", "残業", "出社", "pc", "パソコン", "モニター", "スライド"],
             "prompt": "日本の高品質な2Dカラー漫画背景美術、静かな日本の現代オフィス、デスク、パソコンモニター、夜景の窓、アニメセル画塗り、実写禁止、人物なし"},
            {"id": "loc_living", "name": "自宅リビング・ダイニング", "keys": ["自宅", "リビング", "家", "部屋", "玄関", "帰宅", "ダイニング", "食卓", "キッチン", "台所", "アパート"],
             "prompt": "日本の高品質な2Dカラー漫画背景美術、温かみのある日本の自宅リビング・ダイニング、ペンダントライト、食卓テーブル、アニメセル画塗り、実写禁止、人物なし"},
            {"id": "loc_commute", "name": "駅・通勤路・街頭", "keys": ["駅", "夜道", "通勤", "電車", "街", "街頭", "帰り道", "歩道", "交差点", "終電", "ホーム"],
             "prompt": "日本の高品質な2Dカラー漫画背景美術、夜の日本の都市街頭・駅前、ネオンの光、街灯、アニメセル画塗り、実写禁止、人物なし"},
            {"id": "loc_izakaya", "name": "居酒屋・酒場", "keys": ["居酒屋", "ビール", "飲み屋", "酒", "バー", "乾杯", "カウンター"],
             "prompt": "日本の高品質な2Dカラー漫画背景美術、風情ある日本の大衆居酒屋、木製カウンター、赤提灯の光、アニメセル画塗り、実写禁止、人物なし"},
            {"id": "loc_park", "name": "公園・屋外", "keys": ["公園", "散歩", "青空", "太陽", "朝", "ベンチ", "広場", "自然", "木陰"],
             "prompt": "日本の高品質な2Dカラー漫画背景美術、爽やかな日本の公園、緑の木々、青空と白い雲、日差し、アニメセル画塗り、実写禁止、人物なし"}
        ]

    extracted_locations = []
    for loc in potential_locations:
        score = sum(all_desc_text.count(k) for k in loc["keys"])
        if score > 0:
            extracted_locations.append((score, loc))

    extracted_locations.sort(key=lambda x: x[0], reverse=True)
    locations = [loc for _, loc in extracted_locations[:5]]

    if not locations:
        locations = potential_locations[:3]

    return char_profile, char_roster_prompt, locations, char_dict

def normalize_script_with_timestamps(script_text: str, cuts: List[Dict[str, Any]]) -> str:
    """台本テキスト内の各カット見出しに [MM:SS] 形式のタイムスタンプを付与・正規化"""
    if not cuts or not script_text:
        return script_text

    time_map = {c["cut_number"]: c["start_time"] for c in cuts if c.get("cut_number", 0) > 0}
    if not time_map:
        return script_text

    def replace_cut(match):
        num_str = match.group(2)
        cut_num = int(num_str)
        t_str = time_map.get(cut_num)
        if not t_str:
            return match.group(0)
        return f"[{t_str}] Cut_{cut_num:03d}"

    pattern = re.compile(r'(?:\[(\d{1,2}:\d{2})\]\s*)?Cut_?(\d+)', re.IGNORECASE)
    normalized = pattern.sub(replace_cut, script_text)
    # 重複して次行に残った [MM:SS] の単独行を削除
    normalized = re.sub(r'(\[\d{1,2}:\d{2}\]\s*Cut_\d+)\s*\n\s*\[\d{1,2}:\d{2}\]', r'\1', normalized)
    return normalized

def parse_script_to_storyboard(
    script_text: str,
    style: str = "manga_color",
    genre: str = "business",
    thumbnail_style: str = "split",
    format: str = "16:9",
    video_mode: str = "hook_only"
) -> List[Dict[str, Any]]:
    """
    台本テキストを全カットの絵コンテ配列（JSON）に高速変換
    - 登場キャラクターの動的抽出とプロファイル構築
    - 主要ロケーションの動的抽出と背景美術プロンプト構築
    - シーン・ロケーションの継続性追跡
    - タイムスタンプからの動的秒数計算・累積タイムライン付与
    - セリフ/ナレーションの完全クレンジング
    """
    cuts = []
    char_profile, char_roster_prompt, locations, char_dict = dynamic_extract_characters_and_locations(script_text, genre)
    known_chars = list(char_dict.keys())

    # 1. サムネイル（Cut_000: YouTubeアップロード用独立アセット）
    thumbnail_cut = generate_thumbnail_cut(script_text, style, genre, thumbnail_style, char_profile, format)
    thumbnail_cut["character_profile"] = char_profile
    thumbnail_cut["character_roster_prompt"] = char_roster_prompt
    thumbnail_cut["locations"] = locations
    thumbnail_cut["format"] = format
    thumbnail_cut["duration"] = 5.0
    cuts.append(thumbnail_cut)

    # 2. カット単位でブロック分割
    raw_blocks = re.split(r'\n(?=\s*(?:\[\d{1,2}:\d{2}\]\s*)?Cut_?\d+)', script_text, flags=re.IGNORECASE)

    raw_cut_items = []
    cut_idx = 1

    for block in raw_blocks:
        b = block.strip()
        if not b or b.startswith("===") or b.startswith("---") or b.startswith("【選定テーマ】") or b.startswith("【タイトル】"):
            continue
        if not re.search(r'Cut_?\d+', b, re.IGNORECASE) and not re.search(r'\[\d{1,2}:\d{2}\]', b):
            continue

        lines = [l.strip() for l in b.split('\n') if l.strip()]
        if not lines:
            continue

        time_str = "00:00"
        has_explicit_time = False
        explicit_time_sec = 0.0
        cut_number = cut_idx
        speaker = "ナレーション"
        dialogue = ""
        desc = ""
        effect = "固定"
        is_speech = False

        # ブロック全体からタイムスタンプとCut番号を探索
        t_match = re.search(r'\[(\d{1,2}:\d{2})\]', b)
        if t_match:
            time_str = t_match.group(1)
            parts = time_str.split(":")
            explicit_time_sec = float(int(parts[0]) * 60 + int(parts[1]))
            has_explicit_time = True

        c_match = re.search(r'Cut_?(\d+)', b, re.IGNORECASE)
        if c_match:
            cut_number = int(c_match.group(1))

        for line in lines:
            if "演出" in line and ("【" in line or "：" in line or ":" in line):
                effect_match = re.search(r'【?演出】?[：:\s]*(.+)', line)
                if effect_match:
                    effect = effect_match.group(1).strip()
            elif line.startswith("ト書き") or line.startswith("（") or line.startswith("("):
                cleaned_desc = re.sub(r'^ト書き[：:\s]*', '', line).strip("（）() ")
                desc = desc + " " + cleaned_desc if desc else cleaned_desc
            elif "【話者" in line or "【キャラクター" in line or "【人物" in line or line.startswith("【") or line.startswith("「") or line.startswith("『") or "セリフ" in line:
                spk, diag, is_spk = extract_speaker_and_dialogue(line, desc, known_chars)
                if spk: speaker = spk
                if diag: dialogue = diag
                if is_spk: is_speech = True

        if not desc and not dialogue:
            desc = f"第{cut_number}カットのシーン描写"
        if not desc:
            desc = dialogue[:40]

        raw_cut_items.append({
            "cut_number": cut_number,
            "time_str": time_str,
            "has_explicit_time": has_explicit_time,
            "time_sec": explicit_time_sec,
            "speaker": speaker,
            "dialogue": dialogue,
            "desc": desc,
            "effect": effect,
            "is_speech": is_speech
        })
        cut_idx = max(cut_idx + 1, cut_number + 1)

    # 3. シーン・ロケーションの動的マッチング ＆ タイムライン累積計算
    current_location_idx = 0
    running_timeline_sec = 0.0

    for i, item in enumerate(raw_cut_items):
        cut_number = item["cut_number"]
        speaker = item["speaker"]
        dialogue = item["dialogue"]
        desc = item["desc"]
        effect = item["effect"]
        is_speech = item["is_speech"]

        # タイムスタンプ決定（明示的指定があれば尊重、なければ累積タイムライン秒数）
        if item["has_explicit_time"] and item["time_sec"] >= running_timeline_sec:
            start_sec = item["time_sec"]
            running_timeline_sec = start_sec
        else:
            start_sec = running_timeline_sec

        mins = int(start_sec // 60)
        secs = int(start_sec % 60)
        time_str = f"{mins:02d}:{secs:02d}"

        # 動的ロケーションマッチング
        full_text = (desc + " " + dialogue + " " + speaker).lower()
        matched_idx = None
        best_score = 0
        for l_idx, loc_obj in enumerate(locations):
            score = sum(full_text.count(k.lower()) for k in loc_obj.get("keys", []))
            if score > best_score:
                best_score = score
                matched_idx = l_idx

        if matched_idx is not None and best_score > 0:
            current_location_idx = matched_idx
        # マッチしない場合は直前の current_location_idx を継続

        # 秒数計算: 次のカットとのタイムスタンプ差分、なければセリフ文字数から自然な秒数を算出
        calculated_dur = 4.0
        if i + 1 < len(raw_cut_items) and raw_cut_items[i+1]["has_explicit_time"] and raw_cut_items[i+1]["time_sec"] > start_sec:
            diff = raw_cut_items[i+1]["time_sec"] - start_sec
            calculated_dur = max(2.5, min(15.0, float(diff)))
        elif dialogue:
            calculated_dur = max(3.0, min(15.0, round(len(dialogue) / 5.0 + 0.5, 1)))
        else:
            calculated_dur = 4.0

        running_timeline_sec = round(start_sec + calculated_dur, 1)

        # ショート動画、浮世絵・歴史雑学、ナレーション主体の場合は単一カット（is_pair=False）
        is_pair = bool(dialogue.strip() and is_speech and genre not in ["edoculture", "ukiyoe"] and style != "ukiyoe" and format != "9:16")
        is_narration = (speaker in ["ナレーション", "ナレーター"] or not is_speech)

        # 動画（Veo/Omni）判定:
        # - 9:16 縦型ショート（全6〜7カット）: 全カットまたは動画演出カットを動画化
        # - 16:9 横型長尺（15〜20分 / 30〜150カット）: 
        #   * クレジット枯渇（1動画15クレジット）を防ぎ、100カット以上の長編を安定完走させるため、
        #   * 冒頭フック（Cut 1）のみをVeo動画とし、解説パートは高精細イラスト（PNG）＋Ken Burnsモーション演出とする
        if format == "9:16":
            is_video = bool("動画" in effect or "アクション" in effect or "ビデオ" in effect or cut_number == 1)
        else:
            if video_mode == "hook_only":
                is_video = (cut_number == 1)
            elif video_mode == "all_video":
                is_video = bool("動画" in effect or "アクション" in effect or "ビデオ" in effect or cut_number == 1)
            elif video_mode == "all_image":
                is_video = False
            else:
                is_video = (cut_number == 1)

        # プロンプトの構築（キャラクター + ロケーション + シーン）
        prompt_with_text, prompt_no_text = build_flow_cut_prompts(
            cut_number, desc, speaker, dialogue, is_speech, style, genre,
            char_profile, locations, current_location_idx, char_dict, format
        )

        cuts.append({
            "cut_id": f"Cut_{cut_number:03d}",
            "cut_number": cut_number,
            "start_time": time_str,
            "duration": calculated_dur,
            "speaker": speaker,
            "dialogue": dialogue,
            "scene_description": desc,
            "camera_effect": effect,
            "is_narration": is_narration,
            "is_pair": is_pair,
            "is_video": is_video,
            "format": format,
            "character_profile": char_profile,
            "character_roster_prompt": char_roster_prompt,
            "locations": locations,
            "prompt_no_text": prompt_no_text,
            "prompt_with_text": prompt_with_text,
            "prompt": prompt_with_text
        })

    return cuts

def generate_thumbnail_cut(script_text: str, style: str = "manga_color", genre: str = "business", thumbnail_style: str = "split", char_profile: str = "", format: str = "16:9") -> dict:
    """
    YouTubeでクリック率20%を超える大ヒットサムネイル（Cut_000）を動的構築（長尺 16:9 / ショート 9:16 対応）
    """
    theme_match = re.search(r'【(?:タイトル|選定テーマ)】[：:]\s*([^\n]+)', script_text)
    theme_title = theme_match.group(1).strip() if theme_match else "江戸の暮らし"

    is_edo = bool(genre in ["edoculture", "ukiyoe"] or style == "ukiyoe" or "江戸" in script_text)
    aspect_tag = "9:16縦型スマートフォン画面構図" if format == "9:16" else "16:9横型ワイドスクリーン構図"
    char_desc = char_profile if char_profile else ("江戸時代の町人" if is_edo else "日本の男性主人公")

    # 1. 左右対比（絶望 vs 成功）: YouTubeサムネイルの王道型 (split)
    if thumbnail_style == "split" or thumbnail_style == "auto" or not thumbnail_style:
        if is_edo:
            quality = "日本の本格的な伝統浮世絵・木版画（葛飾北斎・歌川広重風の歴史的美術、木版印刷の独特な質感、和紙テクスチャ、伝統的な和の色彩、実写禁止、現代風アニメ塗り禁止、英語禁止）"
            prompt_thumb = (
                f"【最高峰の日本の浮世絵サムネイル美術（左右真っ二つの劇的対比スプリットスクリーン構図）】：{quality}、{aspect_tag}。"
                f"【画面構図（※絶対厳守・左右2分割対比構図）】：画面の中央で垂直に左右真っ二つに明確に2分割された劇的な対比レイアウト（Split screen comparison layout）。"
                f"【画面の左半分（貧困・苦難の情景）】：重苦しい暗雲と冷たい雨が降る薄暗いトーン。みすぼらしい着物を着て疲れ果て、頭を抱えて苦悩・絶望する貧しい町人の姿。"
                f"【画面の右半分（繁栄・大成功の情景）】：黄金の光が燦然と輝く明るく華やかなトーン。豪華絢爛な着物をまとい、山積みの千両箱や黄金の前で自信に満ちた最高の笑顔を浮かべる大商人。"
                f"【タイトル文字】：画面上部の中央に力強い江戸文字・勘亭流の極太毛筆筆文字で『{theme_title}』と大きく日本語で描画。"
                f"※【絶対厳守】：英語の文字やアルファベットは一切入れないでください（英語禁止、No English text, Japanese only）。『{theme_title}』の日本語の毛筆タイトル文字のみを描画してください。"
            )
        else:
            quality = f"日本の高品質な2Dカラー漫画・Webtoonスタイル（アニメセル画塗り・シャープな線画、実写禁止）、{aspect_tag}"
            prompt_thumb = (
                f"【高クリック率YouTubeサムネイル（左右真っ二つの劇的対比スプリットスクリーン構図）】：{quality}。"
                f"【画面構図（※絶対厳守・左右2分割対比構図）】：画面の中央で垂直に左右真っ二つに明確に2分割された強烈な対比レイアウト（Split screen comparison layout）。"
                f"【画面の左半分（絶望・貧困・過酷な現実）】：薄暗く重苦しい青黒いトーンと雨。疲れ果てたスーツ姿の人物（{char_desc}）が頭を抱えて苦悩し、山積みの請求書や過酷な残業・どん底の絶望に打ちひしがれている情景。"
                f"【画面の右半分（圧倒的成功・歓喜・富裕層）】：黄金のまばゆい光が降り注ぐ明るいトーン。洗練された高級スーツに身を包んだ大成功者（{char_desc}）が自信に満ちた最高の笑顔を浮かべ、背景には高級タワーマンションの夜景、山積みの札束や金貨・資産が輝く圧倒的勝者の情景。"
                f"【タイトル文字】：画面上部の中央に、極太で強烈なインパクトの日本語袋文字（イエロー×赤縁または白×黒縁のYouTubeサムネ特大文字）で『{theme_title}』と特大サイズで日本語描画。"
                f"※【絶対厳守】：英語の文字やアルファベットは一切入れないでください（英語禁止、No English text）。『{theme_title}』の日本語のタイトル文字のみを描画してください。"
            )

    # 2. 中央人物インパクト (impact: 迫真表情・超アップ)
    elif thumbnail_style == "impact":
        if is_edo:
            quality = "日本の本格的な伝統浮世絵・木版画（東洲斎写楽・歌川国芳風の大首絵・迫真の表情、実写禁止、現代風アニメ塗り禁止、英語禁止）"
            prompt_thumb = (
                f"【最高峰の日本の浮世絵サムネイル美術（中央人物大首絵インパクト構図）】：{quality}、{aspect_tag}。"
                f"【画面構図（※迫真の大首絵クローズアップ）】：画面中央に大きく主人公（{char_desc}）の顔がアップで描かれ、目を見開き驚愕または自信に満ちた迫真の表情。"
                f"【タイトル文字】：画面上部に力強い勘亭流の極太毛筆文字で『{theme_title}』と大きく日本語描画。"
                f"※【絶対厳守】：英語禁止（No English text）。"
            )
        else:
            quality = f"日本の高品質な2Dカラー漫画・Webtoonスタイル（アニメセル画塗り・シャープな線画、実写禁止）、{aspect_tag}"
            prompt_thumb = (
                f"【高クリック率YouTubeサムネイル（中央人物クローズアップ構図）】：{quality}。"
                f"【画面構図（※中央迫真表情構図）】：画面中央に大きく主人公（{char_desc}）の顔が超クローズアップされた構図。目を見開き驚愕する表情、または不敵なカリスマ的笑みを浮かべる迫真の表情。背景にはドラマチックな放射状集中線や衝撃のライティング。"
                f"【タイトル文字】：画面上部に、極太で強烈なインパクトの日本語文字で『{theme_title}』と特大サイズで日本語描画。"
                f"※【絶対厳守】：英語の文字やアルファベットは一切入れないでください（英語禁止、No English text）。『{theme_title}』の日本語のタイトル文字のみを描画してください。"
            )

    # 3. 3分割比較（three_step: ステップ・進化）
    elif thumbnail_style == "three_step":
        quality = f"日本の高品質な2Dカラー漫画・Webtoonスタイル（アニメセル画塗り・シャープな線画、実写禁止）、{aspect_tag}"
        prompt_thumb = (
            f"【高クリック率YouTubeサムネイル（3分割ステップ構図）】：{quality}。"
            f"【画面構図（※3分割進化構図）】：画面が横に3等分されたBefore・Process・Afterの進化比較構図（左：絶望の始まり、中央：転機と覚醒、右：圧倒的成功と富）。"
            f"【登場人物】：{char_desc}。"
            f"【タイトル文字】：画面上部に『{theme_title}』と大きく日本語描画。"
            f"※【絶対厳守】：英語禁止（No English text）。"
        )
    else:
        quality = f"日本の高品質な2Dカラー漫画・Webtoonスタイル（アニメセル画塗り・シャープな線画、実写禁止）、{aspect_tag}"
        prompt_thumb = (
            f"【高クリック率YouTubeサムネイル】：{quality}。"
            f"【登場人物】：{char_desc}。"
            f"【タイトル文字】：画面上部に力強い毛筆筆文字で『{theme_title}』と大きく日本語で描画。"
            f"※【絶対厳守】：英語の文字やアルファベットは一切入れないでください（英語禁止、No English text）。『{theme_title}』の日本語のタイトル文字のみを描画してください。"
        )

    return {
        "cut_id": "Cut_000 (サムネイル)",
        "cut_number": 0,
        "start_time": "00:00",
        "duration": 5.0,
        "speaker": "【サムネイル画像】",
        "dialogue": f"メインサムネイル: {theme_title}",
        "scene_description": f"YouTubeサムネイル ({thumbnail_style})",
        "camera_effect": "サムネイル固定",
        "is_narration": False,
        "is_pair": False,
        "is_video": False,
        "format": format,
        "prompt_no_text": prompt_thumb,
        "prompt_with_text": prompt_thumb,
        "prompt": prompt_thumb
    }

def build_flow_cut_prompts(cut_num: int, desc: str, speaker: str, dialogue: str, is_speech: bool, style: str, genre: str, char_profile: str, locations: list, loc_idx: int = 0, char_dict: dict = None, format: str = "16:9") -> Tuple[str, str]:
    """
    Google Flow用のプロンプトを構築（16:9横型 / 9:16縦型ショート対応）
    - 浮世絵・歴史雑学は本物の木版画美術プロンプトを厳格適用
    - アニメ用語（アニメーション・ポップなエフェクト等）を排除し、伝統木版画スタイルを完全維持
    - 英語化防止（日本語厳守・DO NOT TRANSLATE TO ENGLISH）を徹底
    """
    is_edo = (genre in ["edoculture", "ukiyoe"] or style == "ukiyoe" or "江戸" in desc or "長屋" in desc)

    # アニメ調へのドリフトを防ぐための描写サニタイズ
    sanitized_desc = desc
    if is_edo:
        sanitized_desc = sanitized_desc.replace("アニメーション", "自然な動画演出").replace("ポップなエフェクト", "粋な情景演出").replace("エフェクト", "情景演出")

    if is_edo:
        style_desc = "日本の本格的な伝統浮世絵・木版画スタイル（葛飾北斎・歌川広重・喜多川歌麿風の歴史的美術、木版印刷の独特な質感と擦れ、和紙テクスチャ、伝統的な藍色・紅・墨・黄土色の色彩、実写禁止、現代風アニメ塗り禁止、デジタルアニメ調禁止、セル画アニメ禁止、現代の服装や現代の建物・PC・スライド・ビジネス要素は一切禁止、英語禁止）"
    else:
        style_desc = "日本の高品質な2Dカラー漫画・Webtoonスタイル（アニメセル画塗り・シャープな線画、実写禁止）"

    aspect_desc = "9:16縦型スマートフォン画面（縦長構図）" if format == "9:16" else "16:9横型ワイドスクリーン画面（横長構図）"

    # 場所の選定
    matched_loc = locations[loc_idx]["prompt"] if loc_idx < len(locations) else locations[0]["prompt"]

    # キャラクターシグネチャの特定
    char_sig = ""
    if char_dict and speaker in char_dict:
        char_sig = char_dict[speaker]
    elif char_dict:
        for k, v in char_dict.items():
            if k in speaker or speaker in k:
                char_sig = v
                break

    if not char_sig:
        char_sig = "江戸時代の町人・職人・旅人、伝統的な和服姿" if is_edo else "日本の登場人物"

    # シーンベースプロンプト（Flowエージェントへの明確な自然言語指示）
    if is_edo:
        base_scene = (
            f"【スタイル設定】：{style_desc}、{aspect_desc}。"
            f"【シーン描写】：{sanitized_desc}。"
            f"【舞台背景】：{matched_loc}。"
            f"【人物・風俗】：{char_sig}。"
            f"※【重要厳守】：文字や英語、アルファベット、現代のビジネススライドや現代の服、現代アニメ風表現は一切描画しないでください。純粋な江戸時代の情緒ある浮世絵木版画のみを描画してください。"
        )
    else:
        base_scene = (
            f"【スタイル設定】：{style_desc}、{aspect_desc}。"
            f"【シーン描写】：{desc}。"
            f"【舞台背景】：{matched_loc}。"
            f"【登場人物】：{char_sig}。"
        )

    # 浮世絵・歴史解説やショート動画ではクリーンな絵画美術のみを描画（セリフ吹き出しは不要）
    if is_edo or format == "9:16" or not is_speech:
        prompt_with_text = base_scene
        prompt_no_text = base_scene
        return prompt_with_text, prompt_no_text

    # 通常の漫画動画の場合のセリフ吹き出し処理
    if is_speech and dialogue:
        clean_d = dialogue.replace('"', '').replace("'", "").replace("\n", " ")
        if len(clean_d) > 22:
            split_pos = len(clean_d) // 2
            for punct in ["、", "。", "！", "？", " "]:
                p = clean_d.rfind(punct, 8, 20)
                if p != -1:
                    split_pos = p + 1
                    break
            part1 = clean_d[:split_pos].strip()
            part2 = clean_d[split_pos:].strip()
            prompt_with_text = (
                f"{base_scene} "
                f"【セリフ指示（※絶対厳守）】：キャラクターの近くに白い縦書き漫画吹き出しを2つ自然に配置し、第1吹き出しに『{part1}』、第2吹き出しに『{part2}』と黒文字で描画してください。"
                f"※【重要警告】：絶対に英語に翻訳しないでください！指定された日本語（漢字・ひらがな・カタカナ）『{part1}』『{part2}』を一字一句そのまま日本語で描画してください。アルファベット・英語テキストの描画は一切禁止です。"
            )
        else:
            prompt_with_text = (
                f"{base_scene} "
                f"【セリフ指示（※絶対厳守）】：キャラクターの近くに白い縦書き漫画吹き出しを自然に配置し、黒文字で『{clean_d}』と描画してください。"
                f"※【重要警告】：絶対に英語に翻訳しないでください！指定された日本語（漢字・ひらがな・カタカナ）『{clean_d}』を一字一句そのまま日本語で描画してください。アルファベット・英語テキストの描画は一切禁止です。"
            )
    else:
        prompt_with_text = base_scene

    prompt_no_text = f"{base_scene} 【演出】：文字や吹き出し、字幕は一切入れず、キャラクターと背景のクリーンな2Dイラストのみを描画してください。"
    return prompt_with_text, prompt_no_text
