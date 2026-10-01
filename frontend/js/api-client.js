/**
 * KIMIDORI YouTube Auto - API Client
 * バックエンド（FastAPI / Cloud Run）との通信用クライアント
 */

class ApiClient {
  constructor() {
    this.baseUrl = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
      ? `http://${window.location.hostname}:8080` 
      : "https://kimidori-movie-auto-ey3qvn3ruq-an.a.run.app"; // 本番環境のURL
  }

  /**
   * ユーザーのGemini APIキーで利用可能な最新モデル一覧を動的に解決
   * 廃止モデルを完全排除し、最新のFlash/Proモデルを優先
   */
  async getActiveGeminiModels(apiKey) {
    const defaultModels = [
      "gemini-2.5-flash",
      "gemini-2.5-pro",
      "gemini-3.5-flash",
      "gemini-3.8-flash"
    ];
    if (!apiKey) return defaultModels;

    try {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(apiKey)}`, {
        signal: AbortSignal.timeout(6000)
      });
      if (res.ok) {
        const data = await res.json();
        const supported = (data.models || [])
          .filter(m => Array.isArray(m.supportedGenerationMethods) && m.supportedGenerationMethods.includes("generateContent"))
          .map(m => (m.name || "").replace("models/", ""));

        if (supported.length > 0) {
          const priority = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-2.5-pro"];
          const matched = priority.filter(p => supported.includes(p));
          const flashOthers = supported.filter(s => s.toLowerCase().includes("flash") && !matched.includes(s));
          const allOthers = supported.filter(s => !matched.includes(s) && !flashOthers.includes(s));
          const result = [...matched, ...flashOthers, ...allOthers];
          if (result.length > 0) return result;
        }
      }
    } catch (e) {
      console.warn("動的モデル取得スキップ（デフォルトを使用）:", e);
    }
    return defaultModels;
  }

  /** モードA: 動画生成ジョブの発行 */
  async generateVideo(theme, style, duration, targetChannelId, scriptData = null, autoPost = false, bgmOptions = {}) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    const pexelsKey = window.settingsManager.get("pexelsApiKey") || "";
    
    // TTS 設定の取得
    const ttsEngine = window.settingsManager.get("ttsEngine") || "edge";
    const voiceName = window.settingsManager.get("voiceName");
    const googleTtsKey = window.settingsManager.get("googleTtsKey") || "";
    const elevenLabsKey = window.settingsManager.get("elevenLabsKey") || "";
    const aivisKey = window.settingsManager.get("aivisKey") || "";

    if (!window.settingsManager.hasGeminiKey()) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    const paidGeminiKey = window.settingsManager.get("paidGeminiApiKey") || "";
    const openAiTtsKey = window.settingsManager.get("openAiTtsKey") || "";
    const openAiTtsModel = window.settingsManager.get("openAiTtsModel") || "tts-1";
    const azureTtsKey = window.settingsManager.get("azureTtsKey") || "";
    const azureTtsRegion = window.settingsManager.get("azureTtsRegion") || "japaneast";
    const awsAccessKey = window.settingsManager.get("awsAccessKey") || "";
    const awsSecretKey = window.settingsManager.get("awsSecretKey") || "";
    const awsRegion = window.settingsManager.get("awsRegion") || "ap-northeast-1";
    const voicevoxUrl = window.settingsManager.get("voicevoxUrl") || "http://localhost:50021";
    const sharevoxUrl = window.settingsManager.get("sharevoxUrl") || "http://localhost:50025";
    const coeiroinkUrl = window.settingsManager.get("coeiroinkUrl") || "http://localhost:50031";
    const aivisUrl = window.settingsManager.get("aivisUrl") || "http://localhost:10101";
    const ossTtsUrl = window.settingsManager.get("ossTtsUrl") || "http://localhost:9880";
    const ossTtsFormat = window.settingsManager.get("ossTtsFormat") || "openai";
    const ossVoice = window.settingsManager.get("ossVoice") || "";
    const ondokuToken = window.settingsManager.get("ondokuToken") || "";
    const coefontKey = window.settingsManager.get("coefontKey") || "";
    const coefontId = window.settingsManager.get("coefontId") || "";
    const speakingRate = parseFloat(window.settingsManager.get("speakingRate")) || 1.0;

    const payload = {
      theme,
      style,
      duration_seconds: parseInt(duration),
      user_id: this._getUserId(),
      gemini_api_key: geminiKey,
      paid_gemini_api_key: paidGeminiKey,
      pexels_api_key: pexelsKey,
      tts_engine: ttsEngine,
      voice_name: voiceName,
      speaking_rate: speakingRate,
      google_tts_key: googleTtsKey,
      elevenlabs_key: elevenLabsKey,
      openai_key: openAiTtsKey,
      openai_model: openAiTtsModel,
      azure_key: azureTtsKey,
      azure_region: azureTtsRegion,
      aws_access_key: awsAccessKey,
      aws_secret_key: awsSecretKey,
      aws_region: awsRegion,
      voicevox_url: voicevoxUrl,
      voicevox_speaker: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 3,
      sharevox_url: sharevoxUrl,
      sharevox_speaker: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 0,
      coeiroink_url: coeiroinkUrl,
      coeiroink_style: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 0,
      aivis_url: aivisUrl,
      aivis_key: aivisKey,
      aivis_speaker: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 1,
      oss_tts_url: ossTtsUrl,
      oss_tts_format: ossTtsFormat,
      oss_voice: ossVoice,
      ondoku_token: ondokuToken,
      coefont_key: coefontKey,
      coefont_id: coefontId,
      target_youtube_account: targetChannelId || null,
      script_data: scriptData,
      auto_post: autoPost,
      bgm_mode: bgmOptions.mode || "none",
      bgm_id: bgmOptions.bgmId || null,
      bgm_volume: bgmOptions.volume || 0.15,
    };

    const res = await fetch(`${this.baseUrl}/api/process/mode-a`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `サーバーエラー (${res.status})`);
    }

    return await res.json();
  }

  /** 台本プレビュー取得（無料API・有料API完全両対応・デュアルエンジン） */
  async getScriptPreview(theme, style, duration) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    if (!window.settingsManager.hasGeminiKey()) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    try {
      const res = await fetch(`${this.baseUrl}/api/preview/script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          theme, style, duration_seconds: parseInt(duration), gemini_api_key: geminiKey
        })
      });
      
      if (res.ok) {
        return await res.json();
      }
      console.warn("バックエンド台本生成通信失敗、直接Gemini APIフォールバックを実行します...");
    } catch (e) {
      console.warn("バックエンド台本生成失敗、直接Gemini APIフォールバック:", e);
    }

    // ブラウザ直接フォールバック
    const modelsToTry = await this.getActiveGeminiModels(geminiKey);
    let lastErrDetail = "";

    const targetSec = parseInt(duration) || 60;
    const prompt = `あなたはYouTubeで100万回再生されるショート動画のプロ脚本家です。
テーマ「${theme}」、スタイル「${style}」、目標秒数「${targetSec}秒」の台本を作成してください。

以下のJSON形式で出力してください:
{
  "title": "タイトル",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "ナレーション（日本語）",
      "image_prompt": "英語の画像生成プロンプト"
    }
  ]
}`;

    for (const model of modelsToTry) {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(geminiKey)}`;
      try {
        const directRes = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: { temperature: 0.7, maxOutputTokens: 2048 }
          })
        });

        if (directRes.ok) {
          const data = await directRes.json();
          const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
          if (rawText) {
            const m = rawText.match(/```(?:json)?\s*(\{.*?\})\s*```/s);
            const jsonStr = m ? m[1] : rawText;
            try {
              return JSON.parse(jsonStr);
            } catch {
              return { title: theme, scenes: [{ scene_number: 1, narration: rawText, image_prompt: theme }] };
            }
          }
        } else {
          const errJson = await directRes.json().catch(() => ({}));
          lastErrDetail = errJson.error?.message || `HTTP ${directRes.status}`;
        }
      } catch (err) {
        lastErrDetail = err.message;
        continue;
      }
    }

    throw new Error(`台本プレビューの生成に失敗しました: ${lastErrDetail || 'APIキーの有効性をご確認ください'}`);
  }

  /** トレンドリサーチの実行（無料API・有料API完全両対応・デュアルエンジン） */
  async runResearch(keyword) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    if (!window.settingsManager.hasGeminiKey()) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    // 1. まずバックエンドAPIにリクエスト
    try {
      const res = await fetch(`${this.baseUrl}/api/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          keyword, 
          gemini_api_key: geminiKey,
          user_id: this._getUserId()
        })
      });

      if (res.ok) {
        return await res.json();
      }
      console.warn(`バックエンドリサーチがHTTP ${res.status} を返しました。直接Gemini APIフォールバックを実行します...`);
    } catch (e) {
      console.warn("バックエンドリサーチ通信失敗、直接Gemini APIフォールバックを実行します:", e);
    }

    // 2. バックエンドが古い/エラーの場合は、ブラウザから直接Gemini APIを呼び出す（無料・有料API完全両対応）
    const modelsToTry = await this.getActiveGeminiModels(geminiKey);

    const prompt = `あなたはYouTubeで100万回再生を連発するトッププロデューサー・トレンドアナリストです。
テーマ・キーワード「${keyword}」について、現在YouTubeショートやTikTokでバズる動画の傾向を徹底的に分析し、具体的な台本構成と戦略を提案してください。

以下のフォーマットに沿って明快に日本語で出力してください。
1. 【トレンドの傾向】: なぜこのテーマが伸びているのか？視聴者が求めているコアな心理や悩み。
2. 【最強のフック（冒頭1〜3秒）の提案】: 視聴者の手をピタッと止める冒頭のセリフ案を3つ。
3. 【推奨される台本構成】: 視聴維持率を高める展開（フック→共感→解決・新事実→オチ）。
4. 【狙うべきターゲット・感情】: どんな層にどんな感情（驚き、納得、共感など）を引き起こすべきか。`;

    let lastErr = null;
    for (const model of modelsToTry) {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${encodeURIComponent(geminiKey)}`;
      try {
        const directRes = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: { temperature: 0.7, maxOutputTokens: 2048 }
          })
        });

        if (directRes.ok) {
          const data = await directRes.json();
          const analysisText = data.candidates?.[0]?.content?.parts?.[0]?.text;
          if (analysisText) {
            return {
              success: true,
              keyword: keyword,
              analyzed_videos: [],
              analysis_result: analysisText
            };
          }
        } else {
          const errData = await directRes.json().catch(() => ({}));
          lastErr = errData.error?.message || `HTTP ${directRes.status}`;
        }
      } catch (err) {
        lastErr = err.message;
      }
    }

    throw new Error(`リサーチに失敗しました: ${lastErr || "APIキーをご確認ください"}`);
  }

  // ===== BGM管理 API =====

  /** ユーザーIDを取得するヘルパー */
  _getUserId() {
    if (typeof firebase !== 'undefined' && firebase.auth && firebase.auth().currentUser) {
      const user = firebase.auth().currentUser;
      if (user.email === 'oumaumauma32@gmail.com' || user.email === 'sl0wmugi9@gmail.com') {
        return user.email;
      }
      return user.uid;
    }
    const mockUserStr = localStorage.getItem('kimidori_mock_user');
    if (mockUserStr) {
      try {
        const u = JSON.parse(mockUserStr);
        if (u.email === 'oumaumauma32@gmail.com' || u.email === 'sl0wmugi9@gmail.com') {
          return u.email;
        }
        return u.uid || u.email;
      } catch(e) {}
    }
    return "user_123";
  }

  /** BGMをアップロードして登録 */
  async uploadBGM(file, title, description, keywords) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", title);
    formData.append("description", description || "");
    formData.append("keywords", keywords || "");

    const res = await fetch(`${this.baseUrl}/api/bgm/upload`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGMアップロードエラー (${res.status})`);
    }

    return await res.json();
  }

  /** 登録済みBGM一覧を取得 */
  async listBGM() {
    const res = await fetch(`${this.baseUrl}/api/bgm/list`);

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGM一覧取得エラー (${res.status})`);
    }

    return await res.json();
  }

  /** BGMを削除 */
  async deleteBGM(bgmId) {
    const res = await fetch(`${this.baseUrl}/api/bgm/${bgmId}`, {
      method: "DELETE",
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGM削除エラー (${res.status})`);
    }

    return await res.json();
  }

  /** BGMメタデータを更新 */
  async updateBGM(bgmId, updateData) {
    const res = await fetch(`${this.baseUrl}/api/bgm/${bgmId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...updateData,
      }),
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGM更新エラー (${res.status})`);
    }

    return await res.json();
  }

  /** ユーザーの会員プランおよび機能権限の取得 */
  async getUserPermissions(feature = null) {
    const userId = this._getUserId();
    let url = `${this.baseUrl}/api/user/permissions?user_id=${encodeURIComponent(userId)}`;
    if (feature) {
      url += `&feature=${encodeURIComponent(feature)}`;
    }
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "権限情報の取得に失敗しました。");
    }
    return await res.json();
  }

  /** 長尺漫画動画のシナリオ・コマ割りJSONの生成 */
  async generateMangaScript(originalText, targetLengthMinutes = 3) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    if (!geminiKey) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    const payload = {
      original_text: originalText,
      target_length_minutes: parseInt(targetLengthMinutes),
      gemini_api_keys: geminiKey,
      user_id: this._getUserId()
    };

    const res = await fetch(`${this.baseUrl}/api/manga/script`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `漫画シナリオ生成エラー (${res.status})`);
    }

    return await res.json();
  }

  /** 長尺漫画動画 / Pro版ショート動画の生成ジョブの発行 */
  async generateMangaVideo(scriptData, ttsEngine = "edge", voiceName = "nanami", bgmMap = {}) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    const paidGeminiKey = window.settingsManager.get("paidGeminiApiKey") || "";

    const ttsParams = {
      speaking_rate: parseFloat(window.settingsManager.get("speakingRate")) || 1.0,
      google_tts_key: window.settingsManager.get("googleTtsKey") || "",
      elevenlabs_key: window.settingsManager.get("elevenLabsKey") || "",
      openai_key: window.settingsManager.get("openAiTtsKey") || "",
      openai_model: window.settingsManager.get("openAiTtsModel") || "tts-1",
      azure_key: window.settingsManager.get("azureTtsKey") || "",
      azure_region: window.settingsManager.get("azureTtsRegion") || "japaneast",
      aws_access_key: window.settingsManager.get("awsAccessKey") || "",
      aws_secret_key: window.settingsManager.get("awsSecretKey") || "",
      aws_region: window.settingsManager.get("awsRegion") || "ap-northeast-1",
      voicevox_url: window.settingsManager.get("voicevoxUrl") || "http://localhost:50021",
      voicevox_speaker: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 3,
      sharevox_url: window.settingsManager.get("sharevoxUrl") || "http://localhost:50025",
      sharevox_speaker: voiceName && /^\d+$/.test(voiceName) ? parseInt(voiceName) : 0,
      coeiroink_url: window.settingsManager.get("coeiroinkUrl") || "http://localhost:50031",
      aivis_url: window.settingsManager.get("aivisUrl") || "http://localhost:10101",
      aivis_key: window.settingsManager.get("aivisKey") || "",
      oss_tts_url: window.settingsManager.get("ossTtsUrl") || "http://localhost:9880",
      oss_tts_format: window.settingsManager.get("ossTtsFormat") || "openai",
      ondoku_token: window.settingsManager.get("ondokuToken") || "",
      coefont_key: window.settingsManager.get("coefontKey") || "",
      coefont_id: window.settingsManager.get("coefontId") || ""
    };

    const payload = {
      script_data: scriptData,
      user_id: this._getUserId(),
      gemini_api_keys: geminiKey || "",
      paid_gemini_api_key: paidGeminiKey,
      tts_engine: ttsEngine,
      voice_name: voiceName,
      bgm_map: bgmMap,
      tts_params: ttsParams
    };

    const res = await fetch(`${this.baseUrl}/api/manga/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `漫画動画生成エラー (${res.status})`);
    }

    return await res.json();
  }

  /** Pro版ショート動画の台本生成（バックエンド ＋ 直接Gemini APIフォールバック・全キー両対応） */
  async generateProShortsScript(theme, genre = "story") {
    const keys = window.settingsManager.getGeminiKeys();
    if (!keys || keys.length === 0) {
      throw new Error("Gemini APIキー（無料版または有料版）を設定画面で保存してください。");
    }

    const payload = {
      theme: theme,
      genre: genre,
      user_id: this._getUserId(),
      gemini_api_keys: keys
    };

    // 1. まずバックエンドAPIにリクエスト
    try {
      const res = await fetch(`${this.baseUrl}/api/pro-shorts/script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        if (data && data.success && data.script) {
          return data;
        }
      } else {
        const err = await res.json().catch(() => ({}));
        console.warn(`バックエンドProショート台本生成失敗 (${res.status}):`, err);
      }
    } catch (e) {
      console.warn("バックエンドProショート通信エラー、直接ブラウザGeminiフォールバックへ移行:", e);
    }

    // 2. バックエンドが失敗した場合はブラウザから直結でGemini APIを実行（デュアルキー＆複数モデルフォールバック）
    const genreNames = {
      story: "ストーリー・ドラマ・スカッと",
      knowledge: "ライフハック・豆知識・ノウハウ",
      edoculture: "歴史・江戸文化・浮世絵雑学",
      trivia: "雑学・ミステリー・驚きの事実"
    };
    const genreRules = {
      story: "ナレーターによる感情移入の強い朗読または登場人物の会話。冒頭3秒で事件・葛藤が発生。",
      knowledge: "ナレーターによる論理的で痛快な知的ショート解説。全カット動画演出。",
      edoculture: "現代キャラ排除。浮世絵アニメーションと純粋な知的好奇心解説。",
      trivia: "テンポの良い疑問提示と即座の解説。ダイナミック演出。"
    };

    const gName = genreNames[genre] || genreNames.story;
    const gRule = genreRules[genre] || genreRules.story;

    const prompt = `あなたはYouTube ShortsやTikTokで100万回再生を連発するショート動画のトッププロデューサーです。
以下のテーマで、厳密に【60秒尺（全6〜7カット、各8〜10秒、合計55〜60秒）】の超高エンゲージメント動画台本を作成してください。

【テーマ】: ${theme}
【ジャンル】: ${gName}
【演出ルール】:
${gRule}
・全カット【演出】：動画（ダイナミック動画演出）として構成すること。
・各カットは8〜10秒程度（全6〜7カットで合計55〜60秒）。

【出力フォーマット（厳格なJSON）】:
必ず以下のJSON形式のみを出力してください（Markdownコードブロック \`\`\`json \`\`\` で囲んでください）。
{
  "title": "ショート動画タイトル",
  "theme": "${theme}",
  "genre": "${genre}",
  "target_duration_seconds": 60,
  "cuts": [
    {
      "cut_id": "Cut_001",
      "time_range": "[00:00 - 00:09]",
      "speaker": "話者名（または ナレーション）",
      "dialogue": "セリフまたは発話テキスト（冒頭3秒で引き込むフック）",
      "description": "画面の情景・被写体のアクション・背景描写",
      "camera_effect": "動画 (アクション)",
      "bgm_tag": "cheerful / warm / touching / suspense / frightening / funny / epic / neutral から選択"
    }
  ]
}`;

    let lastErrDetail = "";
    for (const k of keys) {
      const modelsToTry = await this.getActiveGeminiModels(k);
      for (const m of modelsToTry) {
        try {
          const directRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${encodeURIComponent(k)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [{ role: "user", parts: [{ text: prompt }] }],
              generationConfig: { temperature: 0.75, maxOutputTokens: 4096 }
            })
          });

          if (directRes.ok) {
            const data = await directRes.json();
            const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
            if (rawText) {
              const match = rawText.match(/```(?:json)?\s*(\{.*?\})\s*```/s);
              const jsonStr = match ? match[1] : rawText;
              let parsed;
              try {
                parsed = JSON.parse(jsonStr);
              } catch {
                let clean = jsonStr.trim();
                if (!clean.endsWith("}")) clean += "\n]}";
                parsed = JSON.parse(clean);
              }
              return { success: true, script: parsed };
            }
          } else {
            const errJson = await directRes.json().catch(() => ({}));
            lastErrDetail = errJson.error?.message || `HTTP ${directRes.status}`;
          }
        } catch (e) {
          lastErrDetail = e.message;
          continue;
        }
      }
    }

    throw new Error(`Pro版ショート台本の生成に失敗しました: ${lastErrDetail || 'APIキーの有効期限または残高をご確認ください'}`);
  }

  /** 長尺動画（15〜20分）完全仕様の台本・人物シート生成（バックエンド ＋ 直接Gemini APIフォールバック・全キー両対応） */
  async generateLongVideoScript(theme, genre = "story", targetMinutes = 15, researchNotes = "") {
    const keys = window.settingsManager.getGeminiKeys();
    if (!keys || keys.length === 0) {
      throw new Error("Gemini APIキー（無料版または有料版）を設定画面で保存してください。");
    }

    const payload = {
      theme: theme,
      genre: genre,
      target_minutes: parseInt(targetMinutes, 10),
      research_notes: researchNotes,
      user_id: this._getUserId(),
      gemini_api_keys: keys
    };

    // 1. バックエンドAPI呼び出し
    try {
      const res = await fetch(`${this.baseUrl}/api/long-video/script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        if (data && data.success && data.script) {
          return data;
        }
      } else {
        const err = await res.json().catch(() => ({}));
        console.warn(`バックエンド長尺台本生成失敗 (${res.status}):`, err);
      }
    } catch (e) {
      console.warn("バックエンド長尺動画通信エラー、直接ブラウザGeminiフォールバックへ移行:", e);
    }

    // 2. ブラウザ直結フォールバック
    const targetCuts = Math.max(60, Math.min(180, parseInt(targetMinutes, 10) * 8));
    const prompt = `あなたはYouTubeで100万再生を連発する長尺動画（${targetMinutes}分動画）のプロ脚本家・構成作家です。
以下の条件に従い、全5章からなる本格的な長尺動画台本と、登場人物の英語指示文一覧表（キャラクターシート）を作成してください。

【テーマ】: ${theme}
【ジャンル】: ${genre}
【目標尺】: 約${targetMinutes}分（合計 ${targetCuts} カット程度、1カットあたり3〜8秒程度）
【参考リサーチメモ】: ${researchNotes || '特になし（あなたの豊富な知識から最新の知見と大ヒット構成を展開してください）'}

【出力フォーマット（厳密なJSON）】:
必ず以下のJSON形式のみを出力してください（Markdownコードブロック \`\`\`json \`\`\` で囲んでください）。
{
  "title": "動画のタイトル",
  "theme": "${theme}",
  "genre": "${genre}",
  "characters": [
    {
      "name": "登場人物の名前（例: 佐藤、健一、ナレーター）",
      "role": "主人公 / 同僚 / 妻 / ナレーター など",
      "appearance_prompt_en": "英語の外見・服装指示（例: a 28-year-old Japanese male office worker, short black hair, wearing a navy business suit and tie, neat appearance, anime style）"
    }
  ],
  "main_locations": [
    {
      "name": "オフィス / 自宅リビング / 街頭 など",
      "location_prompt_en": "英語の舞台背景指示（例: modern Tokyo office interior, desk with computer, daylight streaming through window）"
    }
  ],
  "chapters": [
    {
      "chapter_num": 1,
      "chapter_title": "章のタイトル",
      "cuts": [
        {
          "cut_id": "Cut_001",
          "speaker": "話者名（ナレーション または 登場人物名）",
          "dialogue": "セリフまたはナレーション本文（1場面あたり20〜60文字程度、3〜8秒で話せる長さ）",
          "description": "ト書き（画面の状況、人物の表情や動作、場所）",
          "bgm_tag": "cheerful / warm / touching / suspense / frightening / funny / epic / neutral から選択",
          "camera_effect": "固定 / ズームイン / パン左 / パン右 / 動画(アクション)",
          "is_video_cut": false
        }
      ]
    }
  ]
}`;

    let lastLongErrDetail = "";
    for (const k of keys) {
      const modelsToTry = await this.getActiveGeminiModels(k);
      for (const m of modelsToTry) {
        try {
          const directRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent?key=${encodeURIComponent(k)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              contents: [{ role: "user", parts: [{ text: prompt }] }],
              generationConfig: { temperature: 0.75, maxOutputTokens: 8192 }
            })
          });

          if (directRes.ok) {
            const data = await directRes.json();
            const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
            if (rawText) {
              const match = rawText.match(/```(?:json)?\s*(\{.*?\})\s*```/s);
              const jsonStr = match ? match[1] : rawText;
              let parsed;
              try {
                parsed = JSON.parse(jsonStr);
              } catch {
                let clean = jsonStr.trim();
                if (!clean.endsWith("}")) clean += "\n}]}]}";
                parsed = JSON.parse(clean);
              }
              return { success: true, script: parsed };
            }
          } else {
            const errJson = await directRes.json().catch(() => ({}));
            lastLongErrDetail = errJson.error?.message || `HTTP ${directRes.status}`;
          }
        } catch (e) {
          lastLongErrDetail = e.message;
          continue;
        }
      }
    }

    throw new Error(`長尺動画台本の生成に失敗しました: ${lastLongErrDetail || 'APIキーの有効期限または残高をご確認ください'}`);
  }

  /** 管理用: 登録ユーザー一覧取得 */
  async getAdminUsers() {
    const res = await fetch(`${this.baseUrl}/api/admin/users`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `ユーザー一覧取得エラー (${res.status})`);
    }
    return await res.json();
  }

  /** 管理用: ユーザー手動追加 */
  async createAdminUser(userData) {
    const res = await fetch(`${this.baseUrl}/api/admin/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(userData)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `ユーザー追加エラー (${res.status})`);
    }
    return await res.json();
  }

  /** 管理用: ユーザー情報更新 */
  async updateAdminUser(userId, updates) {
    const res = await fetch(`${this.baseUrl}/api/admin/users/${encodeURIComponent(userId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `ユーザー更新エラー (${res.status})`);
    }
    return await res.json();
  }

  /** 管理用: ユーザー削除 */
  async deleteAdminUser(userId) {
    const res = await fetch(`${this.baseUrl}/api/admin/users/${encodeURIComponent(userId)}`, {
      method: "DELETE"
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `ユーザー削除エラー (${res.status})`);
    }
    return await res.json();
  }

  /** 既存動画の自動編集（Mode B: ジェットカット・Whisper字幕生成） */
  async uploadAndEditVideo(file, jetCut = true, autoSubtitles = true, targetChannel = "") {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("jet_cut", jetCut ? "true" : "false");
    formData.append("auto_subtitles", autoSubtitles ? "true" : "false");
    formData.append("target_channel", targetChannel || "");
    formData.append("user_id", this._getUserId());

    const res = await fetch(`${this.baseUrl}/api/process/mode-b/upload`, {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `動画のアップロード・編集処理の開始に失敗しました (${res.status})`);
    }

    return await res.json();
  }

  /** TTS 音声プレビュー試聴（ローカルVOICEVOX/SHAREVOX/COEIROINK直接通信 ＆ クラウドAPI両対応） */
  async previewTTS(previewData) {
    const engine = previewData.tts_engine || "edge";
    const text = previewData.text || "こんにちは。";

    // ローカル音声合成エンジン (VOICEVOX / SHAREVOX / COEIROINK) かつ localhost の場合はブラウザから直結実行
    const isLocalhostUrl = (url) => url && (url.includes("localhost") || url.includes("127.0.0.1"));

    if (engine === "voicevox" && isLocalhostUrl(previewData.voicevox_url)) {
      try {
        const baseUrl = (previewData.voicevox_url || "http://localhost:50021").replace(/\/$/, "");
        const speaker = previewData.voice_name && /^\d+$/.test(previewData.voice_name) ? parseInt(previewData.voice_name) : 3;
        
        // 1. audio_query
        const qRes = await fetch(`${baseUrl}/audio_query?text=${encodeURIComponent(text)}&speaker=${speaker}`, {
          method: "POST"
        });
        if (!qRes.ok) throw new Error(`VOICEVOX audio_queryエラー (${qRes.status})`);
        const queryJson = await qRes.json();
        if (previewData.speaking_rate) {
          queryJson.speedScale = parseFloat(previewData.speaking_rate) || 1.0;
        }

        // 2. synthesis
        const sRes = await fetch(`${baseUrl}/synthesis?speaker=${speaker}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(queryJson)
        });
        if (!sRes.ok) throw new Error(`VOICEVOX synthesisエラー (${sRes.status})`);
        const wavBlob = await sRes.blob();
        return URL.createObjectURL(wavBlob);
      } catch (localErr) {
        console.warn("ローカルVOICEVOX直接通信失敗、バックエンドプレビューへフォールバックします:", localErr);
      }
    }

    if (engine === "sharevox" && isLocalhostUrl(previewData.sharevox_url)) {
      try {
        const baseUrl = (previewData.sharevox_url || "http://localhost:50025").replace(/\/$/, "");
        const speaker = previewData.voice_name && /^\d+$/.test(previewData.voice_name) ? parseInt(previewData.voice_name) : 0;
        const qRes = await fetch(`${baseUrl}/audio_query?text=${encodeURIComponent(text)}&speaker=${speaker}`, { method: "POST" });
        if (qRes.ok) {
          const qJson = await qRes.json();
          if (previewData.speaking_rate) qJson.speedScale = parseFloat(previewData.speaking_rate) || 1.0;
          const sRes = await fetch(`${baseUrl}/synthesis?speaker=${speaker}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(qJson)
          });
          if (sRes.ok) {
            const wavBlob = await sRes.blob();
            return URL.createObjectURL(wavBlob);
          }
        }
      } catch (localErr) {
        console.warn("ローカルSHAREVOX通信失敗、バックエンドへフォールバックします:", localErr);
      }
    }

    // クラウドエンジン (Edge, Google, OpenAI, ElevenLabs, Azure, Polly, etc.) またはリモートURLはバックエンドAPI経由で合成
    const res = await fetch(`${this.baseUrl}/api/tts/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(previewData)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `TTSプレビュー失敗 (${res.status})`);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }
}

window.apiClient = new ApiClient();


