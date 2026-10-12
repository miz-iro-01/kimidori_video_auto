/**
 * KIMIDORI YouTube Auto - Premium Settings Manager
 */

class SettingsManager {
  constructor() {
    this.STORAGE_KEY = "kimidori_yt_auto_settings";
    // デフォルト設定
    this.defaults = {
      geminiApiKey: "",
      paidGeminiApiKey: "",
      pexelsApiKey: "",
      ttsEngine: "edge",
      voiceName: "nanami",
      speakingRate: 1.0,
      googleTtsKey: "",
      elevenLabsKey: "",
      openAiTtsKey: "",
      openAiTtsModel: "tts-1",
      azureTtsKey: "",
      azureTtsRegion: "japaneast",
      awsAccessKey: "",
      awsSecretKey: "",
      awsRegion: "ap-northeast-1",
      voicevoxUrl: "http://localhost:50021",
      sharevoxUrl: "http://localhost:50025",
      coeiroinkUrl: "http://localhost:50031",
      aivisUrl: "http://localhost:10101",
      aivisKey: "",
      ossTtsUrl: "http://localhost:9880",
      ossTtsFormat: "openai",
      ossVoice: "",
      ossElevenlabsUrl: "http://localhost:9880",
      ossElevenlabsKey: "",
      ossElevenlabsVoiceId: "21m00Tcm4TlvDq8ikWAM",
      ossElevenlabsProtocol: "elevenlabs_compatible",
      // OpenBMB VoxCPM (VoxCPM2 48kHz Studio Quality / ElevenLabs Compatible)
      voxcpmUrl: "http://localhost:8808",
      voxcpmKey: "",
      voxcpmVoiceId: "default",
      voxcpmProtocol: "vllm_omni",
      voxcpmPrompt: "",
      ondokuToken: "",
      coefontKey: "",
      coefontId: "",
      youtubeClientId: "",
      youtubeClientSecret: "",
      youtubeAccounts: [],
      fluxProvider: "fal",
      falApiKey: "",
      replicateApiToken: "",
      colabWorkerUrl: "https://alexander-cedar-pastor-cornell.trycloudflare.com",
      googleDriveSync: false,
      planTier: "pro",
      canUsePremiumTts: true,
      canDirectUploadYoutube: true,
      // BYOG（自前環境接続）設定
      byogEnabled: false,
      byogComfyUrl: "",
      byogGeminiKey: "",
      // クレジット & サロン認証
      userCredits: 100,
      salonAuthToken: "",
      salonPlan: "",
      // マーケティング連携
      marketingWebhookUrl: ""
    };
    this.settings = this.load();
  }

  load() {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      const parsed = saved ? { ...this.defaults, ...JSON.parse(saved) } : { ...this.defaults };
      
      // ダミーの認証情報がLocalStorageに残っている場合は自動でクリアする
      const dummyKeys = ['globalYoutubeClientId', 'globalYoutubeClientSecret', 'youtubeClientId', 'youtubeClientSecret'];
      let hasDummy = false;
      dummyKeys.forEach(k => {
        if (parsed[k] && parsed[k].includes('dummy')) {
          parsed[k] = "";
          hasDummy = true;
        }
      });
      if (hasDummy) {
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(parsed));
      }
      
      return parsed;
    } catch {
      return { ...this.defaults };
    }
  }

  save() {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.settings));
    this.notifyUpdate();
  }

  get(key) {
    return this.settings[key];
  }

  set(key, value) {
    this.settings[key] = value;
    this.save();
  }

  // Gemini API Key Validation (無料枠・有料枠のいずれかが設定されていれば利用可能)
  hasGeminiKey() {
    const freeKey = this.get("geminiApiKey");
    const paidKey = this.get("paidGeminiApiKey");
    return (typeof freeKey === "string" && freeKey.trim().length > 10) ||
           (typeof paidKey === "string" && paidKey.trim().length > 10);
  }

  // 利用可能なGemini APIキーを取得（優先指定 または フォールバック）
  getActiveGeminiKey(preferPaid = false) {
    const freeKey = (this.get("geminiApiKey") || "").trim();
    const paidKey = (this.get("paidGeminiApiKey") || "").trim();
    if (preferPaid) {
      return paidKey || freeKey;
    }
    return freeKey || paidKey;
  }

  // 登録されている全有効Geminiキーをリストで取得
  getGeminiKeys() {
    const freeKey = (this.get("geminiApiKey") || "").trim();
    const paidKey = (this.get("paidGeminiApiKey") || "").trim();
    const keys = [];
    if (freeKey && freeKey.length > 10) keys.push(freeKey);
    if (paidKey && paidKey.length > 10 && paidKey !== freeKey) keys.push(paidKey);
    return keys;
  }

  // YouTube Accounts Management (Max 5)
  addYoutubeAccount(account) {
    const accounts = this.get("youtubeAccounts");
    if (accounts.length >= 5) {
      throw new Error("登録できるYouTubeアカウントは最大5つまでです。");
    }
    // 重複チェック
    if (accounts.find(a => a.id === account.id)) {
      throw new Error("このアカウントは既に登録されています。");
    }
    accounts.push(account);
    this.set("youtubeAccounts", accounts);
  }

  removeYoutubeAccount(id) {
    let accounts = this.get("youtubeAccounts");
    accounts = accounts.filter(a => a.id !== id);
    this.set("youtubeAccounts", accounts);
  }

  getYouTubeAccounts() {
    return this.get("youtubeAccounts") || [];
  }

  // Google Colab (ComfyUI / LTX-Video) 接続URL
  getColabUrl() {
    // BYOGが有効で自前ComfyUI URLが登録されている場合は最優先
    if (this.isByogActive() && this.get("byogComfyUrl")) {
      return this.get("byogComfyUrl").trim();
    }
    const url = (this.get("colabWorkerUrl") || "").trim();
    return url || "https://alexander-cedar-pastor-cornell.trycloudflare.com";
  }

  setColabUrl(url) {
    const sanitized = (url || "").trim().replace(/\/+$/, "");
    this.set("colabWorkerUrl", sanitized);
    return sanitized;
  }

  // BYOG（自前GPU/Colab接続・自前APIキー）モード判定
  isByogActive() {
    if (this.get("byogEnabled") === true) return true;
    if (this.get("byogComfyUrl") && this.get("byogComfyUrl").trim().length > 5) return true;
    if (this.hasGeminiKey()) return true;
    const ossUrl = (this.get("ossElevenlabsUrl") || "").trim();
    if (ossUrl && ossUrl !== "http://localhost:9880") return true;
    const voxcpmUrl = (this.get("voxcpmUrl") || "").trim();
    if (voxcpmUrl && voxcpmUrl !== "http://localhost:8808") return true;
    const ytClientId = (this.get("youtubeClientId") || "").trim();
    if (ytClientId.length > 5) return true;
    return false;
  }

  getEffectiveGeminiKey() {
    if (this.isByogActive() && this.get("byogGeminiKey")) {
      return this.get("byogGeminiKey").trim();
    }
    return this.get("geminiApiKey") || "";
  }

  getVoxCPMConfig() {
    return {
      endpoint_url: this.get("voxcpmUrl") || "http://localhost:8808",
      api_key: this.get("voxcpmKey") || "",
      voice_id: this.get("voxcpmVoiceId") || "default",
      protocol: this.get("voxcpmProtocol") || "vllm_omni",
      prompt: this.get("voxcpmPrompt") || "",
      sample_rate: 48000
    };
  }

  // 高品質OSS TTS（ElevenLabs互換）利用可否フラグ（簡易ショート/ライトプラン相当では無料TTSのみ）
  canUsePremiumTts(contextMode = "pro") {
    if (contextMode === "simple_shorts" || this.get("planTier") === "lite") {
      return false;
    }
    return this.get("canUsePremiumTts") !== false || this.isByogActive();
  }

  // YouTube直接OAuth投稿・予約投稿の利用可否フラグ（簡易ショート/ライトプラン相当ではMP4ダウンロードのみ）
  canDirectUploadYoutube(contextMode = "pro") {
    if (contextMode === "simple_shorts" || this.get("planTier") === "lite") {
      return false;
    }
    return this.get("canDirectUploadYoutube") !== false || this.isByogActive();
  }

  // 動画編集スタジオ利用可否フラグ（ライトプランはスタジオ利用不可・Pro/プレミアム/BYOGのみ利用可能）
  canUseStudio() {
    if (this.get("planTier") === "lite") {
      return false;
    }
    return true;
  }

  // UIへの反映イベント
  notifyUpdate() {
    if (window.appController) {
      window.appController.renderSettings();
      window.appController.validateForms();
    }
  }
}

window.settingsManager = new SettingsManager();

