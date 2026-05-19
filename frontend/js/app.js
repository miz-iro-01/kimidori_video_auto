/**
 * KIMIDORI Movie Auto — メインアプリケーション v2
 * ナビゲーション、台本プレビュー、動画プレビュー、設定管理の統合
 */

document.addEventListener("DOMContentLoaded", () => {
  // ===== DOM参照 =====
  const $ = (id) => document.getElementById(id);

  // ナビゲーション
  const navTabs = document.querySelectorAll(".nav-tab");
  const pages = document.querySelectorAll(".page");

  // モードタブ
  const tabA = $("tabModeA"), tabB = $("tabModeB");
  const panelA = $("panelModeA"), panelB = $("panelModeB");

  // モードAフォーム
  const formA = $("formModeA"), inputTheme = $("inputTheme"), selectStyle = $("selectStyle");
  const rangeDuration = $("rangeDuration"), durationValue = $("durationValue"), btnGenA = $("btnGenerateA");
  const progressA = $("progressA"), barA = $("progressBarA"), msgA = $("progressMessageA"), pctA = $("progressPercentA");
  const scriptPreviewA = $("scriptPreviewA"), scriptContentA = $("scriptContentA");
  const resultA = $("resultA"), resultTitleA = $("resultTitleA"), resultMsgA = $("resultMessageA");
  const videoPlayerA = $("videoPlayerA"), btnDownloadA = $("btnDownloadA"), btnYouTubeA = $("btnYouTubeA");

  // モードBフォーム
  const formB = $("formModeB"), fileUploadArea = $("fileUploadArea"), inputVideoFile = $("inputVideoFile");
  const fileNameDisplay = $("fileNameDisplay"), btnGenB = $("btnGenerateB");
  const progressB = $("progressB"), barB = $("progressBarB"), msgB = $("progressMessageB"), pctB = $("progressPercentB");
  const resultB = $("resultB"), btnDownloadB = $("btnDownloadB"), btnYouTubeB = $("btnYouTubeB");

  let selectedFile = null;
  let jobHistory = JSON.parse(localStorage.getItem("kimidori_jobs") || "[]");

  // ===== ナビゲーション =====
  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const page = tab.dataset.page;
      navTabs.forEach((t) => t.classList.toggle("active", t === tab));
      pages.forEach((p) => p.classList.toggle("active", p.id === `page${page.charAt(0).toUpperCase() + page.slice(1)}`));
      if (page === "settings") { settingsManager.populateForm(); settingsManager.updateStatusDisplay(); }
      if (page === "history") renderJobHistory();
    });
  });

  // ===== モードタブ =====
  tabA.addEventListener("click", () => { tabA.classList.add("active"); tabB.classList.remove("active"); panelA.classList.add("active"); panelB.classList.remove("active"); });
  tabB.addEventListener("click", () => { tabB.classList.add("active"); tabA.classList.remove("active"); panelB.classList.add("active"); panelA.classList.remove("active"); });

  // ===== スライダー =====
  rangeDuration.addEventListener("input", (e) => { durationValue.textContent = `${e.target.value}秒`; });
  const speakingRate = $("settingSpeakingRate");
  if (speakingRate) speakingRate.addEventListener("input", (e) => { $("speakingRateValue").textContent = `${e.target.value}x`; });

  // ===== TTSエンジン切替 =====
  const ttsSelect = $("settingTTSEngine");
  if (ttsSelect) ttsSelect.addEventListener("change", (e) => settingsManager.updateTTSOptions(e.target.value));

  // ===== パスワード表示切替 =====
  const toggleVisibility = (btnId, inputId) => {
    const btn = $(btnId), inp = $(inputId);
    if (btn && inp) btn.addEventListener("click", () => { inp.type = inp.type === "password" ? "text" : "password"; });
  };
  toggleVisibility("btnToggleGeminiKey", "settingGeminiKey");
  toggleVisibility("btnToggleYTSecret", "settingYouTubeClientSecret");

  // ===== ファイルアップロード =====
  fileUploadArea.addEventListener("click", () => inputVideoFile.click());
  fileUploadArea.addEventListener("dragover", (e) => { e.preventDefault(); fileUploadArea.classList.add("drag-over"); });
  fileUploadArea.addEventListener("dragleave", () => fileUploadArea.classList.remove("drag-over"));
  fileUploadArea.addEventListener("drop", (e) => {
    e.preventDefault(); fileUploadArea.classList.remove("drag-over");
    if (e.dataTransfer.files[0]?.type.startsWith("video/")) handleFile(e.dataTransfer.files[0]);
    else showToast("動画ファイルを選択してください", "error");
  });
  inputVideoFile.addEventListener("change", (e) => { if (e.target.files[0]) handleFile(e.target.files[0]); });

  function handleFile(file) {
    selectedFile = file;
    fileNameDisplay.textContent = `📎 ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
    fileNameDisplay.style.display = "block";
    btnGenB.disabled = false;
    showToast(`ファイルを選択: ${file.name}`, "info");
  }

  // ===== GCPキーアップロード =====
  const gcpArea = $("gcpKeyUploadArea"), gcpInput = $("inputGCPKey"), gcpName = $("gcpKeyFileName");
  if (gcpArea) {
    gcpArea.addEventListener("click", () => gcpInput.click());
    gcpInput.addEventListener("change", (e) => {
      if (e.target.files[0]) { gcpName.textContent = `🔑 ${e.target.files[0].name}`; gcpName.style.display = "block"; }
    });
  }

  // ===== モードA: 動画生成 =====
  formA.addEventListener("submit", async (e) => {
    e.preventDefault();
    const theme = inputTheme.value.trim();
    if (!theme) { showToast("テーマを入力してください", "error"); return; }

    btnGenA.disabled = true; btnGenA.innerHTML = "<span>⏳</span> 処理中...";
    progressA.classList.add("active"); resultA.classList.remove("active");
    scriptPreviewA.classList.remove("active");
    updateProgress("A", 0, "ジョブを送信中...");

    try {
      const result = await jobManager.submitModeA(theme, selectStyle.value, parseInt(rangeDuration.value));
      showToast("ジョブを受け付けました！", "success");
      addJob({ id: result.job_id, mode: "A", theme, status: "processing", createdAt: new Date().toISOString() });

      if (result._simulation) {
        jobManager.runSimulation(result, (update) => handleUpdate("A", result.job_id, update));
      }
    } catch (err) { showToast(`エラー: ${err.message}`, "error"); resetBtn("A"); }
  });

  // ===== モードB: 動画編集 =====
  formB.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) { showToast("動画ファイルを選択してください", "error"); return; }

    btnGenB.disabled = true; btnGenB.innerHTML = "<span>⏳</span> 処理中...";
    progressB.classList.add("active"); resultB.classList.remove("active");
    updateProgress("B", 0, "ファイルをアップロード中...");

    try {
      const result = await jobManager.submitModeB(selectedFile, $("checkJetCut").checked, $("checkSubtitles").checked);
      showToast("ジョブを受け付けました！", "success");
      addJob({ id: result.job_id, mode: "B", theme: selectedFile.name, status: "processing", createdAt: new Date().toISOString() });

      if (result._simulation) {
        jobManager.runSimulation(result, (update) => handleUpdate("B", result.job_id, update));
      }
    } catch (err) { showToast(`エラー: ${err.message}`, "error"); resetBtn("B"); }
  });

  // ===== ジョブ更新ハンドラー =====
  function handleUpdate(mode, jobId, data) {
    updateProgress(mode, data.progress, data.message);

    // 台本表示
    if (data.scriptData && mode === "A") renderScript(data.scriptData);

    if (data.status === "completed") {
      showResult(mode, true, data.message, data.youtube_url);
      updateJob(jobId, "completed", data.youtube_url);
      resetBtn(mode);
    } else if (data.status === "failed") {
      showResult(mode, false, data.message);
      updateJob(jobId, "failed");
      resetBtn(mode);
    }
  }

  function updateProgress(mode, progress, message) {
    const bar = mode === "A" ? barA : barB;
    const msg = mode === "A" ? msgA : msgB;
    const pct = mode === "A" ? pctA : pctB;
    bar.style.width = `${progress}%`;
    msg.textContent = message;
    pct.textContent = `${progress}%`;
  }

  // ===== 台本プレビュー =====
  function renderScript(script) {
    scriptPreviewA.classList.add("active");
    let html = `<div class="script-title">📌 ${esc(script.title)}</div>`;
    html += `<div class="script-tags">${script.tags.map(t => `<span class="script-tag">#${esc(t)}</span>`).join("")}</div>`;
    script.scenes.forEach((s) => {
      html += `<div class="script-scene">
        <div class="script-scene-header">
          <span class="script-scene-num">シーン ${s.scene_number}</span>
          <span class="script-scene-duration">⏱ ${s.duration_seconds}秒</span>
        </div>
        <div class="script-scene-narration">${esc(s.narration)}</div>
        <div class="script-scene-overlay">💬 ${esc(s.text_overlay)}</div>
      </div>`;
    });
    scriptContentA.innerHTML = html;
  }

  // ===== 台本折りたたみ =====
  const toggleScript = $("btnToggleScriptA");
  if (toggleScript) {
    toggleScript.addEventListener("click", () => {
      const content = scriptContentA;
      const isHidden = content.style.display === "none";
      content.style.display = isHidden ? "block" : "none";
      toggleScript.textContent = isHidden ? "▼" : "▶";
    });
  }

  // ===== 結果表示 =====
  function showResult(mode, success, message, youtubeUrl) {
    const res = mode === "A" ? resultA : resultB;
    const title = mode === "A" ? resultTitleA : $("resultTitleB");
    const msg = mode === "A" ? resultMsgA : $("resultMessageB");
    const dl = mode === "A" ? btnDownloadA : btnDownloadB;
    const yt = mode === "A" ? btnYouTubeA : btnYouTubeB;

    res.classList.toggle("error", !success);
    title.textContent = success ? "🎉 動画が完成しました！" : "❌ 処理に失敗しました";
    msg.textContent = message;

    if (success && youtubeUrl) {
      yt.href = youtubeUrl; yt.style.display = "inline-flex";
      // デモではダウンロードリンクにダミーを設定
      dl.href = "#"; dl.style.display = "inline-flex";
      dl.addEventListener("click", (e) => { e.preventDefault(); showToast("デモモードではダウンロードできません。Cloud Runデプロイ後に利用可能です。", "info"); });
    } else {
      yt.style.display = "none"; dl.style.display = "none";
    }

    res.classList.add("active");
    showToast(success ? "動画の処理が完了しました！" : "処理中にエラーが発生しました", success ? "success" : "error");
  }

  function resetBtn(mode) {
    if (mode === "A") { btnGenA.disabled = false; btnGenA.innerHTML = '<span class="btn-icon">🚀</span> 台本を生成して動画を作成する'; }
    else { btnGenB.disabled = false; btnGenB.innerHTML = '<span class="btn-icon">✂️</span> 自動編集を開始する'; }
  }

  // ===== ジョブ履歴 =====
  function addJob(job) { jobHistory.unshift(job); jobHistory = jobHistory.slice(0, 50); localStorage.setItem("kimidori_jobs", JSON.stringify(jobHistory)); }
  function updateJob(id, status, url) { const j = jobHistory.find(x => x.id === id); if (j) { j.status = status; if (url) j.youtubeUrl = url; localStorage.setItem("kimidori_jobs", JSON.stringify(jobHistory)); } }

  function renderJobHistory() {
    const list = $("jobList"), empty = $("emptyState");
    list.querySelectorAll(".job-item").forEach(el => el.remove());
    if (!jobHistory.length) { empty.style.display = "block"; return; }
    empty.style.display = "none";
    jobHistory.forEach((job) => {
      const item = document.createElement("div"); item.className = "job-item";
      const statusText = { pending: "待機中", processing: "処理中", completed: "完了", failed: "失敗" }[job.status] || job.status;
      const date = new Date(job.createdAt).toLocaleString("ja-JP", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
      item.innerHTML = `<div class="job-item-info"><span class="job-item-mode">モード${job.mode}</span><div><div class="job-item-theme">${esc(job.theme)}</div><div class="job-item-date">${date}</div></div></div><span class="status-badge ${job.status}">${statusText}</span>`;
      if (job.youtubeUrl) { item.style.cursor = "pointer"; item.onclick = () => window.open(job.youtubeUrl, "_blank"); }
      list.appendChild(item);
    });
  }

  // ===== 設定保存 =====
  const btnSave = $("btnSaveSettings");
  if (btnSave) btnSave.addEventListener("click", () => {
    settingsManager.saveAll(settingsManager.collectFromForm());
    settingsManager.updateStatusDisplay();
    showToast("設定を保存しました", "success");
  });

  const btnReset = $("btnResetSettings");
  if (btnReset) btnReset.addEventListener("click", () => {
    if (confirm("すべての設定をリセットしますか？")) {
      settingsManager.reset(); settingsManager.populateForm(); settingsManager.updateStatusDisplay();
      showToast("設定をリセットしました", "info");
    }
  });

  // 接続テスト
  const btnTest = $("btnTestConnection");
  if (btnTest) btnTest.addEventListener("click", async () => {
    const url = $("settingApiUrl")?.value;
    if (!url) { showToast("URLを入力してください", "error"); return; }
    try {
      const resp = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
      if (resp.ok) showToast("✅ Cloud Run APIに接続成功！", "success");
      else showToast(`接続失敗: HTTP ${resp.status}`, "error");
    } catch { showToast("接続失敗: サーバーに到達できません", "error"); }
  });

  // YouTube認証
  const btnAuth = $("btnAuthYouTube");
  if (btnAuth) btnAuth.addEventListener("click", () => {
    showToast("YouTube認証はCloud Runバックエンドのデプロイ後に利用可能です", "info");
  });

  // ===== ユーティリティ =====
  function showToast(message, type = "info") {
    const icons = { success: "✅", error: "❌", info: "ℹ️", warning: "⚠️" };
    const toast = document.createElement("div"); toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${icons[type] || ""}</span><span>${esc(message)}</span>`;
    $("toastContainer").appendChild(toast);
    setTimeout(() => { toast.style.opacity = "0"; toast.style.transform = "translateX(100px)"; toast.style.transition = "all 0.3s ease"; setTimeout(() => toast.remove(), 300); }, 4000);
  }

  function esc(text) { const d = document.createElement("div"); d.textContent = text; return d.innerHTML; }

  // ===== 初期化 =====
  renderJobHistory();
  settingsManager.updateStatusDisplay();
  console.log("🎬 KIMIDORI Movie Auto v2 初期化完了");
});
