/**
 * KIMIDORI Movie Auto — ジョブ管理 v2
 * デモシミュレーション付き台本生成・進捗監視
 */

class JobManager {
  constructor() {
    this.isDemoMode = true; // Firebase未設定時はデモ
    this.listeners = new Map();
  }

  /** モードA: 台本生成→動画作成ジョブを送信 */
  async submitModeA(theme, style, durationSeconds) {
    // 開発環境と本番環境のURL判別（本来は環境変数等で切り替え）
    const apiUrl = window.apiClient ? window.apiClient.baseUrl : (
      (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
        ? `http://${window.location.hostname}:8080`
        : "https://api.your-saas-domain.com"
    );
    const geminiKey = settingsManager.get("geminiApiKey");
    const voiceName = settingsManager.get("voiceName");
    const speakingRate = settingsManager.get("speakingRate");

    // ユーザーがAPIキーを設定している場合のみサーバーに送信
    if (geminiKey) {
      try {
        const resp = await fetch(`${apiUrl}/api/process/mode-a`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            theme, 
            style, 
            duration_seconds: durationSeconds, 
            user_id: "web-user",
            gemini_api_key: geminiKey,
            voice_name: voiceName,
            speaking_rate: speakingRate
          }),
        });
        if (!resp.ok) throw new Error(`APIエラー: ${resp.status}`);
        return await resp.json();
      } catch (err) {
        console.error("API接続失敗、デモモードにフォールバックします", err);
      }
    }

    // デモモード（APIキーがない、またはサーバーに繋がらない場合）
    return this._simulateModeA(theme, style, durationSeconds);
  }

  /** モードB: 既存動画編集ジョブを送信 */
  async submitModeB(file, enableJetCut, enableSubtitles) {
    const apiUrl = settingsManager.get("apiUrl");
    if (apiUrl && apiUrl !== "http://localhost:8080") {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("enable_jet_cut", enableJetCut);
      formData.append("enable_subtitles", enableSubtitles);
      const resp = await fetch(`${apiUrl}/api/process/mode-b`, { method: "POST", body: formData });
      if (!resp.ok) throw new Error(`APIエラー: ${resp.status}`);
      return await resp.json();
    }
    return this._simulateModeB(file.name, enableJetCut, enableSubtitles);
  }

  watchJob(jobId, onUpdate) { /* Firestoreリアルタイム監視 */ }
  unwatchJob(jobId) { const unsub = this.listeners.get(jobId); if (unsub) { unsub(); this.listeners.delete(jobId); } }

  /** デモ: モードAシミュレーション（台本データ含む） */
  _simulateModeA(theme, style, duration) {
    const jobId = `demo-${Date.now()}`;
    // デモ用の台本データを生成
    const scriptData = this._generateDemoScript(theme, style, duration);
    const steps = [
      { progress: 5, message: "処理を開始しています...", delay: 500 },
      { progress: 10, message: "Geminiで台本を生成中...", delay: 1500, showScript: true },
      { progress: 25, message: "音声を合成中（シーン 1/6）...", delay: 1200 },
      { progress: 35, message: "音声を合成中（シーン 3/6）...", delay: 1000 },
      { progress: 45, message: "画像素材を生成中...", delay: 1500 },
      { progress: 55, message: "ケンバーンズ効果を適用中...", delay: 1200 },
      { progress: 65, message: "テロップを重畳中...", delay: 1000 },
      { progress: 75, message: "シーンを結合して動画を合成中...", delay: 1800 },
      { progress: 85, message: "動画をエンコード中...", delay: 1500 },
      { progress: 95, message: "YouTubeに投稿中（非公開）...", delay: 1200 },
      { progress: 100, message: "処理が完了しました！", delay: 500, done: true },
    ];
    return { job_id: jobId, status: "pending", progress: 0, message: "ジョブを受け付けました", _simulation: { steps, scriptData } };
  }

  /** デモ: モードBシミュレーション */
  _simulateModeB(fileName, enableJetCut, enableSubtitles) {
    const jobId = `demo-${Date.now()}`;
    const steps = [
      { progress: 5, message: "処理を開始しています...", delay: 500 },
      { progress: 15, message: "素材動画を解析中...", delay: 1500 },
      { progress: 30, message: "Whisperで音声認識中（これには時間がかかります）...", delay: 2500 },
      { progress: 45, message: "無音区間を検出中...", delay: 1500 },
      { progress: 55, message: `ジェットカット実行中（12箇所の無音を検出）...`, delay: 2000 },
      { progress: 70, message: "自動テロップを生成中...", delay: 1800 },
      { progress: 80, message: "テロップを動画に焼き付け中...", delay: 2000 },
      { progress: 90, message: "動画をエンコード中...", delay: 1500 },
      { progress: 95, message: "YouTubeに投稿中（非公開）...", delay: 1200 },
      { progress: 100, message: "処理が完了しました！", delay: 500, done: true },
    ];
    return { job_id: jobId, status: "pending", progress: 0, _simulation: { steps, scriptData: null } };
  }

  /** デモ用の台本データを動的生成 */
  _generateDemoScript(theme, style, duration) {
    const sceneCount = Math.max(4, Math.min(8, Math.round(duration / 8)));
    const scenes = [];
    const overlays = [
      "衝撃の事実", "知っていますか？", "ポイント①", "具体例", 
      "驚きの結果", "まとめ", "次回予告", "重要"
    ];
    const narrations = {
      informative: [
        `みなさん、${theme}について考えたことはありますか？`,
        `実は、この分野では驚くべき発見がされています。`,
        `専門家によると、今後ますます重要になると言われています。`,
        `具体的な例を見てみましょう。`,
        `このデータからわかることは、大きな変化が起きているということです。`,
        `では、私たちにできることは何でしょうか。`,
        `まず第一に、正しい知識を身につけることが大切です。`,
        `いかがでしたか？${theme}の世界は奥が深いですね。`,
      ],
      entertaining: [
        `やばい！${theme}がマジですごいんです！`,
        `これ知らない人、損してますよ！`,
        `実はこんな裏話があるんです。`,
        `ここからが本番です！`,
        `信じられないかもしれませんが、これ本当の話なんです。`,
        `みんなの反応が面白すぎる！`,
        `最後に衝撃の事実をお伝えします。`,
        `フォローして次の動画もお楽しみに！`,
      ],
      tutorial: [
        `今日は${theme}のやり方を解説します。`,
        `まず最初に、必要なものを準備しましょう。`,
        `ステップ1: 基本的な設定を行います。`,
        `ステップ2: 実際にやってみましょう。`,
        `ここがポイントです。注意してください。`,
        `うまくいかない場合は、この方法を試してみてください。`,
        `完成です！思ったより簡単でしたね。`,
        `チャンネル登録で最新チュートリアルをチェック！`,
      ],
      storytelling: [
        `これは${theme}にまつわる、ある物語です。`,
        `すべては、ある日の出来事から始まりました。`,
        `誰もが不可能だと思っていました。`,
        `しかし、転機が訪れます。`,
        `困難を乗り越え、一歩ずつ前に進みました。`,
        `そしてついに、その瞬間が訪れたのです。`,
        `この経験から学んだことは、諦めないことの大切さです。`,
        `あなたも、自分の物語を始めてみませんか？`,
      ],
    };

    const narrationList = narrations[style] || narrations.informative;

    for (let i = 0; i < sceneCount; i++) {
      scenes.push({
        scene_number: i + 1,
        narration: narrationList[i % narrationList.length],
        visual_description: `Scene about ${theme}, part ${i + 1}`,
        text_overlay: overlays[i % overlays.length],
        duration_seconds: Math.round(duration / sceneCount),
      });
    }

    return {
      title: `【必見】${theme}の真実 — 知らないと損する${sceneCount}つのこと`,
      description: `${theme}について、わかりやすく解説する動画です。AIが自動生成しました。`,
      tags: [theme, "AI生成", "ショート", "解説", "トレンド"],
      scenes,
    };
  }

  /** デモシミュレーションを実行 */
  runSimulation(jobData, onUpdate) {
    if (!jobData._simulation) return;
    const { steps, scriptData } = jobData._simulation;
    let idx = 0;
    const runStep = () => {
      if (idx >= steps.length) return;
      const step = steps[idx];
      setTimeout(() => {
        const update = {
          status: step.done ? "completed" : "processing",
          progress: step.progress,
          message: step.message,
        };
        if (step.showScript && scriptData) update.scriptData = scriptData;
        if (step.done) update.youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
        onUpdate(update);
        idx++;
        runStep();
      }, step.delay);
    };
    runStep();
  }
}

const jobManager = new JobManager();
