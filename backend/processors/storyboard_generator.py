"""
KIMIDORI Movie Auto - 絵コンテ・キャラクター・ロケーション自動解析＆プロンプト生成エンジン
portable-video-studio のノウハウを統合・拡張した高度解析プロセッサ
"""

import re
import json
import logging
from typing import Tuple, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# スタイル別英語描画プロンプトプレフィックス定義
STYLE_PROMPTS = {
    "manga_color": "vibrant Japanese manga color illustration, detailed anime lineart, comic book masterpiece",
    "anime": "high quality anime style, Kyoto Animation aesthetic, detailed shading, 8k resolution",
    "ukiyoe": "traditional Japanese ukiyoe woodblock print style, Edo period artwork, authentic texture, Hokusai Hiroshige style",
    "cinematic": "cinematic film still, 35mm photograph, dramatic lighting, depth of field, photorealistic, 8k resolution",
    "realistic": "hyperrealistic photograph, soft natural lighting, extremely detailed, 8k portrait"
}


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
    """セリフやナレーションからト書き・演出括弧・話者名プレフィックスを除去して純粋な発話テキストを抽出"""
    cleaned = text
    cleaned = re.sub(r'[（\(][^）\)]*?(?:心の中|表情|息|沈黙|汗|声|笑み|ため息|焦り|驚き|叫び|呟き|独白|ト書き|演出|ナレーション|視線|動作)[^）\)]*?[）\)]', '', cleaned)
    cleaned = re.sub(r'^[（\(][^）\)]*?[）\)]\s*', '', cleaned)
    cleaned = re.sub(r'^(?:メイン解説者|解説者|ナレーション|セリフ|ト書き|話者|キャラクター|語り手|語り|解説|ナレーター)[：:\s]*', '', cleaned)
    cleaned = cleaned.strip("「」『』\"' \t\r\n")
    return cleaned


def extract_speaker_and_dialogue(line: str, known_characters: Optional[List[str]] = None) -> Tuple[str, str, bool]:
    """台本の1行から話者名とセリフ本文を抽出"""
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
        elif spk_tag in ["セリフ", "話者名", "キャラクター名", "人物名", "話者", "キャラクター"]:
            speaker = known_characters[0] if (known_characters and len(known_characters) > 0) else "主人公"
            is_speech = True
        else:
            speaker = spk_tag
            is_speech = True

        dialogue = clean_dialogue_text(rest)
    elif line.startswith("「") or line.startswith("『"):
        dialogue = clean_dialogue_text(line)
        is_speech = True
        speaker = known_characters[0] if (known_characters and len(known_characters) > 0) else "主人公"
    else:
        dialogue = clean_dialogue_text(line)
        is_speech = False

    return speaker, dialogue, is_speech


class StoryboardAnalyzer:
    """台本からキャラクター、コンテ、タイムライン演出、プロンプトを完全動的に自動抽出・解析するクラス"""

    def __init__(self, style: str = "manga_color"):
        self.style = style
        self.style_prefix = STYLE_PROMPTS.get(style, STYLE_PROMPTS["manga_color"])

    def parse_script_to_storyboard(self, script_text: str, genre: str = "story") -> Dict[str, Any]:
        """
        台本テキスト（テキスト全体）を全自動解析し、カットごとの絵コンテJSON、キャラクター、背景情報を構築する
        """
        raw_speakers = re.findall(r'【([^】]+)】', script_text)
        invalid_tags = ["選定テーマ", "テーマ", "演出", "サムネイル画像", "ナレーション", "語り", "解説", "メイン解説者", "解説者", "語り手", "ナレーター", "ト書き", "セリフ", "話者", "キャラクター"]
        
        character_names = []
        for s in raw_speakers:
            s_clean = s.strip()
            if s_clean and s_clean not in invalid_tags and s_clean not in character_names:
                character_names.append(s_clean)

        cuts = []
        raw_cuts = re.split(r'(Cut_\d+)', script_text)
        
        current_cut_id = "Cut_001"
        for i in range(1, len(raw_cuts), 2):
            cut_label = raw_cuts[i]
            cut_content = raw_cuts[i+1] if i+1 < len(raw_cuts) else ""

            # 各行の抽出
            lines = [l.strip() for l in cut_content.split('\n') if l.strip()]
            desc = ""
            speaker = "ナレーション"
            dialogue = ""
            camera_effect = "固定"
            bgm_tag = "neutral"

            for line in lines:
                if line.startswith("ト書き：") or line.startswith("ト書き:"):
                    desc = line.replace("ト書き：", "").replace("ト書き:", "").strip()
                elif line.startswith("【演出】：") or line.startswith("【演出】:"):
                    camera_effect = line.replace("【演出】：", "").replace("【演出】:", "").strip()
                elif "【" in line:
                    spk, dia, _ = extract_speaker_and_dialogue(line, character_names)
                    speaker = spk
                    dialogue = dia

            # アクションや感情からbgm_tagを自動判定
            if any(w in desc or w in dialogue for w in ["危機", "叫ぶ", "襲う", "恐怖", "黒幕", "怪しい"]):
                bgm_tag = "suspense" if "恐怖" not in desc else "frightening"
            elif any(w in desc or w in dialogue for w in ["涙", "感動", "ありがとう", "奇跡", "別れ"]):
                bgm_tag = "touching"
            elif any(w in desc or w in dialogue for w in ["笑", "冗談", "ドジ", "バカ"]):
                bgm_tag = "funny"
            elif any(w in desc or w in dialogue for w in ["微笑み", "穏やか", "暖か", "公園", "カフェ"]):
                bgm_tag = "warm"
            elif any(w in desc or w in dialogue for w in ["勝利", "スカッと", "突破", "成功"]):
                bgm_tag = "cheerful"

            # 英語プロンプトの自動組み立て
            image_prompt = f"{self.style_prefix}, {desc}, speaker: {speaker}" if desc else f"{self.style_prefix}, scene of {genre}"

            cuts.append({
                "cut_id": cut_label,
                "speaker": speaker,
                "dialogue": dialogue,
                "description": desc,
                "camera_effect": camera_effect,
                "bgm_tag": bgm_tag,
                "image_prompt": image_prompt,
                "duration_seconds": max(4.0, round(len(dialogue) * 0.2, 1)) if dialogue else 5.0
            })

        return {
            "style": self.style,
            "genre": genre,
            "characters": character_names,
            "total_cuts": len(cuts),
            "cuts": cuts
        }
