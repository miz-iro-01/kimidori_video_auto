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

    const payload = {
      theme,
      style,
      duration_seconds: parseInt(duration),
      user_id: (() => {
        if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
        const mockUserStr = localStorage.getItem('kimidori_mock_user');
        if (mockUserStr) {
          try { return JSON.parse(mockUserStr).uid; } catch(e) {}
        }
        return "user_123";
      })(),
      gemini_api_key: geminiKey,
      pexels_api_key: pexelsKey,
      tts_engine: ttsEngine,
      voice_name: voiceName,
      google_tts_key: googleTtsKey,
      elevenlabs_key: elevenLabsKey,
      aivis_key: aivisKey,
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

  /** 台本プレビュー取得 */
  async getScriptPreview(theme, style, duration) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    if (!window.settingsManager.hasGeminiKey()) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    const res = await fetch(`${this.baseUrl}/api/preview/script`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        theme, style, duration_seconds: parseInt(duration), gemini_api_key: geminiKey
      })
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `台本生成エラー (${res.status})`);
    }
    
    return await res.json();
  }

  /** トレンドリサーチの実行 */
  async runResearch(keyword) {
    const geminiKey = window.settingsManager.get("geminiApiKey");
    if (!window.settingsManager.hasGeminiKey()) {
      throw new Error("Gemini APIキーが設定されていません。");
    }

    const res = await fetch(`${this.baseUrl}/api/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        keyword, 
        gemini_api_key: geminiKey,
        user_id: this._getUserId()
      })
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `リサーチエラー (${res.status})`);
    }

    return await res.json();
  }

  // ===== BGM管理 API =====

  /** ユーザーIDを取得するヘルパー */
  _getUserId() {
    if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
    const mockUserStr = localStorage.getItem('kimidori_mock_user');
    if (mockUserStr) {
      try { return JSON.parse(mockUserStr).uid; } catch(e) {}
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

  /** 長尺漫画動画の生成ジョブの発行 */
  async generateMangaVideo(scriptData, ttsEngine = "edge", voiceName = "nanami", bgmMap = {}) {
    const geminiKey = window.settingsManager.get("geminiApiKey");

    const payload = {
      script_data: scriptData,
      user_id: this._getUserId(),
      gemini_api_keys: geminiKey || "",
      tts_engine: ttsEngine,
      voice_name: voiceName,
      bgm_map: bgmMap
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
}

window.apiClient = new ApiClient();


