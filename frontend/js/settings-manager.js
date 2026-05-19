/**
 * KIMIDORI Movie Auto — 設定管理 (SaaS BYOK版)
 * ユーザーが持ち込むAPIキーや設定の保存・読み込み
 */

class SettingsManager {
  constructor() {
    this.STORAGE_KEY = "kimidori_user_settings";
    this.defaults = {
      geminiApiKey: "",
      youtubePrivacy: "private",
      youtubeAuthenticated: false,
      voiceName: "nanami",
      speakingRate: 1.0,
    };
  }

  /** 全設定を取得 */
  getAll() {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      return saved ? { ...this.defaults, ...JSON.parse(saved) } : { ...this.defaults };
    } catch {
      return { ...this.defaults };
    }
  }

  /** 特定の設定値を取得 */
  get(key) {
    return this.getAll()[key] ?? this.defaults[key];
  }

  /** 全設定を保存 */
  saveAll(settings) {
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(settings));
  }

  /** 特定の設定値を保存 */
  set(key, value) {
    const all = this.getAll();
    all[key] = value;
    this.saveAll(all);
  }

  /** APIキーが設定されているかチェック */
  isConfigured(key) {
    const val = this.get(key);
    return typeof val === "string" && val.trim().length > 0;
  }

  /** フォームから設定値を収集 */
  collectFromForm() {
    return {
      geminiApiKey: document.getElementById("settingGeminiKey")?.value || "",
      youtubePrivacy: document.getElementById("settingYouTubePrivacy")?.value || "private",
      voiceName: document.getElementById("settingVoiceName")?.value || "nanami",
      speakingRate: parseFloat(document.getElementById("settingSpeakingRate")?.value || "1.0"),
      youtubeAuthenticated: this.get("youtubeAuthenticated"),
    };
  }

  /** 設定値をフォームに反映 */
  populateForm() {
    const s = this.getAll();
    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    
    setVal("settingGeminiKey", s.geminiApiKey);
    setVal("settingYouTubePrivacy", s.youtubePrivacy);
    setVal("settingVoiceName", s.voiceName);
    setVal("settingSpeakingRate", s.speakingRate);

    // 読み上げ速度表示
    const rateDisplay = document.getElementById("speakingRateValue");
    if (rateDisplay) rateDisplay.textContent = `${s.speakingRate}x`;

    this.updateWarnings();
  }

  /** 未設定の警告表示を更新 */
  updateWarnings() {
    const hasKey = this.isConfigured("geminiApiKey");
    const warningA = document.getElementById("apiWarningA");
    const btnA = document.getElementById("btnGenerateA");
    
    if (warningA) {
      if (hasKey) {
        warningA.classList.remove("active");
        if (btnA) btnA.disabled = false;
      } else {
        warningA.classList.add("active");
        if (btnA) btnA.disabled = true;
      }
    }

    // YouTube認証ステータス
    const ytStatus = document.getElementById("youtubeAuthStatus");
    if (ytStatus) {
      const isAuth = this.get("youtubeAuthenticated");
      const dot = ytStatus.querySelector(".status-dot");
      const text = ytStatus.querySelector("span");
      if (isAuth) {
        dot.className = "status-dot connected";
        text.textContent = "連携済み";
      } else {
        dot.className = "status-dot pending";
        text.textContent = "未連携";
      }
    }
  }
}

// グローバルインスタンス
const settingsManager = new SettingsManager();
