/**
 * KIMIDORI YouTube Auto - Premium Settings Manager
 */

class SettingsManager {
  constructor() {
    this.STORAGE_KEY = "kimidori_yt_auto_settings";
    // デフォルト設定
    this.defaults = {
      geminiApiKey: "",
      pexelsApiKey: "",
      ttsEngine: "edge", // edge, google, elevenlabs, aivis
      googleTtsKey: "",
      elevenLabsKey: "",
      aivisKey: "",
      voiceName: "nanami",
      youtubeClientId: "",
      youtubeClientSecret: "",
      youtubeAccounts: [] 
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

  // Gemini API Key Validation
  hasGeminiKey() {
    const key = this.get("geminiApiKey");
    return typeof key === "string" && key.startsWith("AIza") && key.length > 30;
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

  // UIへの反映イベント
  notifyUpdate() {
    if (window.appController) {
      window.appController.renderSettings();
      window.appController.validateForms();
    }
  }
}

window.settingsManager = new SettingsManager();
