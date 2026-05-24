/**
 * KIMIDORI YouTube Auto - API Client
 * バックエンド（FastAPI / Cloud Run）との通信用クライアント
 */

class ApiClient {
  constructor() {
    this.baseUrl = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
      ? `http://${window.location.hostname}:8080` 
      : "https://kimidori-movie-auto-84265380422.asia-northeast1.run.app"; // 本番環境のURL
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
      body: JSON.stringify({ keyword, gemini_api_key: geminiKey })
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
    formData.append("user_id", this._getUserId());
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
    const userId = this._getUserId();
    const res = await fetch(`${this.baseUrl}/api/bgm/list?user_id=${encodeURIComponent(userId)}`);

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGM一覧取得エラー (${res.status})`);
    }

    return await res.json();
  }

  /** BGMを削除 */
  async deleteBGM(bgmId) {
    const userId = this._getUserId();
    const res = await fetch(`${this.baseUrl}/api/bgm/${bgmId}?user_id=${encodeURIComponent(userId)}`, {
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
        user_id: this._getUserId(),
        ...updateData,
      }),
    });

    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || `BGM更新エラー (${res.status})`);
    }

    return await res.json();
  }
}

window.apiClient = new ApiClient();

