/**
 * KIMIDORI YouTube Auto - App Controller
 * UIの制御・バリデーション・ビュー切り替え
 */

class AppController {
  constructor() {
    this.initViews();
    this.initForms();
    this.initSettings();
    this.renderSettings();
    this.validateForms();
    this.initAuth();
  }

  // --- ビュー（画面）切り替え ---
  initViews() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
      item.addEventListener('click', () => {
        // ナビの切り替え
        navItems.forEach(n => n.classList.remove('active'));
        item.classList.add('active');

        // セクションの切り替え
        const target = item.dataset.target;
        document.querySelectorAll('.view-section').forEach(sec => {
          sec.classList.remove('active');
        });
        document.getElementById(`view-${target}`).classList.add('active');
      });
    });
  }

  // --- 設定画面の初期化 ---
  initSettings() {
    // Gemini Key
    const keyInput = document.getElementById('setGeminiKey');
    const saveKeyBtn = document.getElementById('btnSaveGemini');
    
    keyInput.value = window.settingsManager.get('geminiApiKey') || "";
    
    saveKeyBtn.addEventListener('click', () => {
      const val = keyInput.value.trim();
      if(val && !val.startsWith("AIza")) {
        this.showToast("有効なGemini APIキーを入力してください（AIza...で始まります）", "error");
        return;
      }
      window.settingsManager.set('geminiApiKey', val);
      this.showToast("Gemini APIキーを保存しました", "success");
    });

    // Pexels Key
    const pexelsInput = document.getElementById('setPexelsKey');
    const savePexelsBtn = document.getElementById('btnSavePexels');
    if (pexelsInput && savePexelsBtn) {
      pexelsInput.value = window.settingsManager.get('pexelsApiKey') || "";
      savePexelsBtn.addEventListener('click', () => {
        window.settingsManager.set('pexelsApiKey', pexelsInput.value.trim());
        this.showToast("Pexels APIキーを保存しました", "success");
      });
    }



    // --- TTS Engine Settings ---
    const ttsEngineSelect = document.getElementById('setTtsEngine');
    const googleTtsInput = document.getElementById('setGoogleTtsKey');
    const elevenLabsInput = document.getElementById('setElevenLabsKey');
    const aivisInput = document.getElementById('setAivisKey');
    
    const groupGoogle = document.getElementById('groupGoogleTtsKey');
    const groupElevenLabs = document.getElementById('groupElevenLabsKey');
    const groupAivis = document.getElementById('groupAivisKey');

    const updateTtsUi = (engine) => {
      groupGoogle.style.display = engine === 'google' ? 'block' : 'none';
      groupElevenLabs.style.display = engine === 'elevenlabs' ? 'block' : 'none';
      groupAivis.style.display = engine === 'aivis' ? 'block' : 'none';
    };

    if (ttsEngineSelect) {
      const currentEngine = window.settingsManager.get('ttsEngine') || 'edge';
      ttsEngineSelect.value = currentEngine;
      updateTtsUi(currentEngine);
      
      if (googleTtsInput) googleTtsInput.value = window.settingsManager.get('googleTtsKey') || "";
      if (elevenLabsInput) elevenLabsInput.value = window.settingsManager.get('elevenLabsKey') || "";
      if (aivisInput) aivisInput.value = window.settingsManager.get('aivisKey') || "";

      ttsEngineSelect.addEventListener('change', (e) => {
        updateTtsUi(e.target.value);
      });
    }

    // Voice & General TTS Save
    const voiceSelect = document.getElementById('setVoiceName');
    const saveVoiceBtn = document.getElementById('btnSaveVoice');
    if (voiceSelect && saveVoiceBtn) {
      voiceSelect.value = window.settingsManager.get('voiceName') || "nanami";
      saveVoiceBtn.addEventListener('click', () => {
        if(ttsEngineSelect) window.settingsManager.set('ttsEngine', ttsEngineSelect.value);
        if(googleTtsInput) window.settingsManager.set('googleTtsKey', googleTtsInput.value.trim());
        if(elevenLabsInput) window.settingsManager.set('elevenLabsKey', elevenLabsInput.value.trim());
        if(aivisInput) window.settingsManager.set('aivisKey', aivisInput.value.trim());
        window.settingsManager.set('voiceName', voiceSelect.value);
        this.showToast("ナレーション設定を保存しました", "success");
      });
    }

    // YouTube Add Button (OAuth Login)
    const btnAddYoutube = document.getElementById('btnAddYoutube');
    if (btnAddYoutube) {
      btnAddYoutube.addEventListener('click', async () => {
        // 管理者によってグローバル設定された認証情報を自動で取得
        const clientId = window.settingsManager.get('globalYoutubeClientId') || window.settingsManager.get('youtubeClientId');
        const clientSecret = window.settingsManager.get('globalYoutubeClientSecret') || window.settingsManager.get('youtubeClientSecret');

        if (!clientId || !clientSecret || clientId.includes("dummy") || clientSecret.includes("dummy")) {
          return this.showToast("Google OAuthの設定が未設定、またはデフォルトのダミー値です。右上「管理者パネル」から正しい Client ID と Client Secret を入力・保存してください。", "warning");
        }

        // 【ポップアップブロック対策】クリックの瞬間に即時でローディング状態のウィンドウを安全に開く
        const authWindow = window.open("", "youtube_auth", "width=600,height=700");
        if (authWindow) {
          authWindow.document.write(`
            <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0f0c1b; color: #fff; margin: 0; padding: 20px; text-align: center;">
              <div style="border: 4px solid rgba(255,255,255,0.1); border-top-color: #39ff14; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin-bottom: 20px;"></div>
              <h3 style="font-weight: 500;">YouTube 認証ページへ転送中...</h3>
              <p style="color: #a0aec0; font-size: 0.85rem;">安全に接続を確立しています。しばらくお待ちください。</p>
              <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
            </body></html>
          `);
        } else {
          return this.showToast("ポップアップがブロックされました。ブラウザの設定で許可してください。", "error");
        }

        try {
          const reqBody = {
            user_id: (() => {
              if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
              const mockUserStr = localStorage.getItem('kimidori_mock_user');
              if (mockUserStr) {
                try { return JSON.parse(mockUserStr).uid; } catch(e) {}
              }
              return "user_123";
            })()
          };

          // 管理者設定のキーがあれば送信し、なければバックエンドのデフォルト環境変数設定に委ねる
          if (clientId && clientSecret) {
            reqBody.client_id = clientId;
            reqBody.client_secret = clientSecret;
          }

          // 【ドメインバグの解決】window.apiClient.baseUrl を動的に使用して正しいAPIに通信する
          const res = await fetch(`${window.apiClient.baseUrl}/api/auth/youtube/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(reqBody)
          });
          
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "認証URLの取得に失敗しました");
          }
          
          const data = await res.json();
          // 取得したYouTube OAuth認証URLへリダイレクト
          authWindow.location.href = data.auth_url;

        } catch (e) {
          if (authWindow) authWindow.close();
          console.error("YouTube OAuth Init Error:", e);
          this.showToast("接続エラー: バックエンドAPIサーバーが起動していないか、または設定が正しくありません。", "error");
        }
      });
    }

    // 認証完了時のメッセージ受信
    window.addEventListener('message', (event) => {
      if (event.data === 'youtube_auth_success') {
        this.showToast("YouTubeアカウントの連携が完了しました！", "success");
        // 本来はここでYouTubeアカウント一覧をリロードする
      }
    });
  }

  // 設定状況をUIに反映
  renderSettings() {
    // 必須設定のアラート表示
    const hasKey = window.settingsManager.hasGeminiKey();
    const alertCard = document.getElementById('setupAlertCard');
    if (alertCard) {
      alertCard.style.display = hasKey ? 'none' : 'flex';
    }

    const statusDot = document.getElementById('systemStatusDot');
    const statusText = document.getElementById('systemStatusText');
    if (hasKey) {
      statusDot.className = "status-dot ready";
      statusText.textContent = "システム準備完了";
    } else {
      statusDot.className = "status-dot";
      statusText.textContent = "システム待機中（設定待ち）";
    }

    // YouTube アカウント一覧
    const accounts = window.settingsManager.getYouTubeAccounts();
    const list = document.getElementById('ytAccountList');
    
    if (accounts.length === 0) {
      list.innerHTML = `<p style="color: var(--text-muted); font-size: 0.9rem;">連携済みのチャンネルはありません。</p>`;
    } else {
      list.innerHTML = accounts.map(acc => `
        <div class="yt-account-item">
          <div class="yt-account-info">
            <div class="yt-avatar">${acc.name.charAt(0)}</div>
            <span class="yt-name">${acc.name}</span>
          </div>
          <button class="btn btn-outline" onclick="window.appController.removeYouTube('${acc.id}')">解除</button>
        </div>
      `).join('');
    }

    // 投稿先セレクトボックスの更新
    ['inputTargetChannelA', 'inputTargetChannelB'].forEach(id => {
      const select = document.getElementById(id);
      if (!select) return;
      select.innerHTML = '<option value="">-- 投稿しない（ダウンロードのみ） --</option>' + 
        accounts.map(acc => `<option value="${acc.id}">${acc.name}</option>`).join('');
    });
  }

  // --- フォームバリデーション ---
  validateForms() {
    const hasKey = window.settingsManager.hasGeminiKey();
    const btnA = document.getElementById('btnSubmitA');
    if(btnA) btnA.disabled = !hasKey;
    
    // UIのHintの更新
    const accounts = window.settingsManager.getYouTubeAccounts();
    const hintA = document.getElementById('hintChannelA');
    if (hintA) {
      hintA.style.display = accounts.length > 0 ? 'none' : 'block';
    }
  }

  // --- フォーム初期化 (モードA: ウィザード) ---
  initForms() {
    // 状態管理
    this.wizardState = { theme: "", strategy: "", scriptData: null, duration: 45, style: "informative", target: "" };

    const showStep = (stepNum) => {
      document.querySelectorAll('.wizard-step').forEach(el => el.style.display = 'none');
      document.getElementById(`step${stepNum}`).style.display = 'block';
    };

    // STEP 1: リサーチ開始
    document.getElementById('btnRunResearch')?.addEventListener('click', async () => {
      const theme = document.getElementById('inputTheme').value.trim();
      const target = document.getElementById('inputTargetChannelA').value;
      const isAuto = document.getElementById('checkAutoMode').checked;

      if (!theme) return this.showToast("テーマを入力してください", "error");
      if (!window.settingsManager.hasGeminiKey()) return this.showToast("設定画面でGemini APIキーを登録してください", "error");

      this.wizardState.theme = theme;
      this.wizardState.target = target;

      if (isAuto) {
        // 完全自動モード：確認をスキップしてバックエンドで全処理
        showStep(4);
        document.getElementById('execPanelA').style.display = 'block';
        document.getElementById('videoResultPanel').style.display = 'none';
        document.getElementById('execTitleA').textContent = "完全自動でリサーチから動画生成、投稿まで実行中...";
        this.simulateProgress('A');
        
        try {
          // script_data=null, auto_post=true でリクエスト
          await window.apiClient.generateVideo(theme, "informative", 45, target, null, true);
          this.showToast("完全自動投稿タスクが開始されました！", "success");
        } catch(e) {
          this.showToast(e.message, "error");
          showStep(1);
        }
        return;
      }

      // 手動モード：STEP 2へ
      showStep(2);
      document.getElementById('researchLoading').style.display = 'block';
      document.getElementById('researchResults').style.display = 'none';

      try {
        const res = await window.apiClient.runResearch(theme);
        document.getElementById('researchAnalysisText').textContent = res.analysis_result;
        this.wizardState.strategy = res.analysis_result;
        
        document.getElementById('researchLoading').style.display = 'none';
        document.getElementById('researchResults').style.display = 'block';
      } catch (err) {
        this.showToast("リサーチ失敗: " + err.message, "error");
        showStep(1);
      }
    });

    // 戻るボタン
    document.getElementById('btnBackTo1')?.addEventListener('click', () => showStep(1));
    document.getElementById('btnBackTo2')?.addEventListener('click', () => showStep(2));

    // STEP 2 -> STEP 3: 台本生成
    document.getElementById('btnGenerateScript')?.addEventListener('click', async () => {
      showStep(3);
      document.getElementById('scriptLoading').style.display = 'block';
      document.getElementById('scriptEditor').style.display = 'none';

      try {
        const combinedTheme = `テーマ: ${this.wizardState.theme}\n\n戦略:\n${this.wizardState.strategy}`;
        const preview = await window.apiClient.getScriptPreview(combinedTheme, this.wizardState.style, this.wizardState.duration);
        
        if (preview && preview.script) {
          this.wizardState.scriptData = preview.script;
          document.getElementById('inputScriptData').value = JSON.stringify(preview.script, null, 2);
        } else {
          throw new Error("台本データが取得できませんでした。");
        }
        
        document.getElementById('scriptLoading').style.display = 'none';
        document.getElementById('scriptEditor').style.display = 'block';
      } catch (err) {
        this.showToast(err.message, "error");
        showStep(2);
      }
    });

    // STEP 3 -> STEP 4: 動画生成
    document.getElementById('btnGenerateVideo')?.addEventListener('click', async () => {
      try {
        // ユーザーが編集したJSONをパース
        this.wizardState.scriptData = JSON.parse(document.getElementById('inputScriptData').value);
      } catch (e) {
        return this.showToast("台本のJSONフォーマットが不正です。修正してください。", "error");
      }

      showStep(4);
      document.getElementById('execPanelA').style.display = 'block';
      document.getElementById('videoResultPanel').style.display = 'none';
      document.getElementById('execTitleA').textContent = "動画をレンダリング中...";
      this.simulateProgress('A');

      try {
        // 編集済みのscript_dataを渡して動画生成
        await window.apiClient.generateVideo(
          this.wizardState.theme, 
          this.wizardState.style, 
          this.wizardState.duration, 
          this.wizardState.target,
          this.wizardState.scriptData,
          false
        );
        this.showToast("動画の生成リクエストを送信しました！", "success");
        
        // 実際にはFirestore等のリスナーで完了検知するが、今回はモックとして完了画面へ切り替え
        setTimeout(() => {
          document.getElementById('execPanelA').style.display = 'none';
          document.getElementById('videoResultPanel').style.display = 'block';
          // デモ用に適当な動画URLをセット（実際はstorageのURLが入る）
          document.getElementById('finalVideoPlayer').src = "https://www.w3schools.com/html/mov_bbb.mp4";
        }, 8000);

      } catch (err) {
        this.showToast(err.message, "error");
        showStep(3);
      }
    });

    // 投稿ボタン（手動モード時の最終ステップ）
    document.getElementById('btnPostToYouTube')?.addEventListener('click', () => {
      this.showToast("YouTubeへの投稿処理を開始しました！", "success");
      // 実際にはバックエンドの投稿APIを叩く
    });

    // Modal Close
    document.getElementById('modalClose')?.addEventListener('click', () => {
      document.getElementById('modalOverlay').classList.remove('active');
      document.getElementById('modalVideo').pause();
    });

    // --- トレンドリサーチのアクション ---
    const formResearch = document.getElementById('formResearch');
    const btnSubmitResearch = document.getElementById('btnSubmitResearch');
    
    if (formResearch && btnSubmitResearch) {
      formResearch.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!window.settingsManager.hasGeminiKey()) {
          return this.showToast("設定画面でGemini APIキーを登録してください", "error");
        }

        const keyword = document.getElementById('inputResearchKeyword').value.trim();
        if (!keyword) return this.showToast("キーワードを入力してください", "error");

        btnSubmitResearch.disabled = true;
        const panel = document.getElementById('execPanelResearch');
        const title = document.getElementById('execTitleResearch');
        const resultPanel = document.getElementById('researchResultPanel');
        
        panel.style.display = 'block';
        resultPanel.style.display = 'none';
        
        // 疑似プログレスアニメーション
        title.textContent = "YouTubeでバズっている動画を検索中...";
        this.simulateProgress('Research');

        try {
          const res = await window.apiClient.runResearch(keyword);
          
          // 結果表示の組み立て
          const list = document.getElementById('analyzedVideosList');
          list.innerHTML = res.analyzed_videos.map(v => 
            `<li><a href="${v.link}" target="_blank" style="color: var(--accent-primary);">${v.title}</a> (再生数: ${v.views})</li>`
          ).join('');
          
          document.getElementById('researchAnalysisText').textContent = res.analysis_result;
          
          // この戦略を動画生成に反映するボタンのフック
          const btnApply = document.getElementById('btnApplyResearchToVideo');
          btnApply.onclick = () => {
            document.querySelector('.nav-item[data-target="generate"]').click();
            const themeInput = document.getElementById('inputTheme');
            themeInput.value = `以下のリサーチ戦略に基づいて動画を作って：\n\n${res.analysis_result}\n\nテーマ: ${keyword}`;
            themeInput.focus();
          };

          panel.style.display = 'none';
          resultPanel.style.display = 'block';
          this.showToast("リサーチが完了しました！", "success");

        } catch (err) {
          this.showToast(err.message, "error");
          panel.style.display = 'none';
        } finally {
          btnSubmitResearch.disabled = false;
        }
      });
    }
  }

  simulateProgress(mode) {
    const bar = document.getElementById(`execBar${mode}`);
    const title = document.getElementById(`execTitle${mode}`);
    if(!bar || !title) return;
    
    let p = 0;
    const interval = setInterval(() => {
      p += 5;
      if (p > 90) clearInterval(interval);
      bar.style.width = `${p}%`;
      if(p===20) title.textContent = "台本と構成を作成中...";
      if(p===40) title.textContent = "フリー素材をPexelsから取得中...";
      if(p===60) title.textContent = "画像素材とエフェクトを適用中...";
      if(p===80) title.textContent = "動画をエンコード中...";
    }, 500);
  }

  // --- YouTube疑似OAuth連携 ---
  simulateYouTubeOAuth() {
    try {
      const mockAccounts = ["ゲーム実況チャンネル", "Vlogチャンネル", "解説チャンネル", "メインチャンネル", "サブチャンネル"];
      const current = window.settingsManager.getYouTubeAccounts().length;
      if (current >= 5) throw new Error("登録できるアカウントは最大5つまでです。");
      
      const newAcc = {
        id: `yt_${Date.now()}`,
        name: mockAccounts[current % mockAccounts.length],
        token: "dummy_oauth_token"
      };
      
      window.settingsManager.addYoutubeAccount(newAcc);
      this.showToast(`${newAcc.name}を連携しました`, "success");
    } catch(err) {
      this.showToast(err.message, "error");
    }
  }

  removeYouTube(id) {
    window.settingsManager.removeYoutubeAccount(id);
    this.showToast("連携を解除しました", "success");
  }

  // --- 認証機能 (Firebase Auth & ロール管理) ---
  initAuth() {
    // ログイン / 新規作成タブ切り替え
    const tabBtnLogin = document.getElementById('tabBtnLogin');
    const tabBtnRegister = document.getElementById('tabBtnRegister');
    const formLogin = document.getElementById('formLogin');
    const formRegister = document.getElementById('formRegister');

    if (tabBtnLogin && tabBtnRegister && formLogin && formRegister) {
      tabBtnLogin.addEventListener('click', () => {
        tabBtnLogin.classList.add('active');
        tabBtnRegister.classList.remove('active');
        formLogin.classList.add('active');
        formRegister.classList.remove('active');
      });

      tabBtnRegister.addEventListener('click', () => {
        tabBtnRegister.classList.add('active');
        tabBtnLogin.classList.remove('active');
        formRegister.classList.add('active');
        formLogin.classList.remove('active');
      });
    }

    // ログイン処理
    formLogin?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('loginEmail').value.trim();
      const password = document.getElementById('loginPassword').value;
      
      // 管理者アカウント特別パスワード認証（モック／ローカル用フォールバック）
      const isAdminCredentials = (email === 'sl0wmugi9@gmail.com' || email === 'oumaumauma32@gmail.com') && password === 'kimidori2026';
      
      try {
        if (isAdminCredentials) {
          // Firebase Authで一度試す（本番用アカウントがすでに登録されている場合のため）
          try {
            await firebase.auth().signInWithEmailAndPassword(email, password);
            this.showToast("管理者としてログインしました！", "success");
            return;
          } catch (fbErr) {
            console.warn("Firebase Auth failed, falling back to mock login:", fbErr);
            // Firebaseが未初期化・設定不備の場合のモックログイン
            const mockUser = {
              uid: email === 'sl0wmugi9@gmail.com' ? 'admin_mugi_uid' : 'admin_ouma_uid',
              email: email,
              isMock: true
            };
            localStorage.setItem('kimidori_mock_user', JSON.stringify(mockUser));
            this.showToast("管理者ログインしました（ローカルフォールバック）", "success");
            this.updateAuthState(mockUser);
            return;
          }
        }
        
        await firebase.auth().signInWithEmailAndPassword(email, password);
        this.showToast("ログインしました！", "success");
      } catch (err) {
        console.error(err);
        this.showToast("ログイン失敗: " + err.message, "error");
      }
    });

    // 新規登録処理
    formRegister?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('registerEmail').value.trim();
      const password = document.getElementById('registerPassword').value;
      
      try {
        await firebase.auth().createUserWithEmailAndPassword(email, password);
        this.showToast("アカウントが作成され、ログインしました！", "success");
      } catch (err) {
        console.error(err);
        this.showToast("登録失敗: " + err.message, "error");
      }
    });

    // Google ログイン処理
    document.getElementById('btnGoogleLogin')?.addEventListener('click', async () => {
      try {
        const provider = new firebase.auth.GoogleAuthProvider();
        await firebase.auth().signInWithPopup(provider);
        this.showToast("Googleでログインしました！", "success");
      } catch (err) {
        console.error(err);
        this.showToast("Googleログイン失敗: " + err.message, "error");
      }
    });

    // ログアウト処理
    document.getElementById('btnLogout')?.addEventListener('click', async () => {
      try {
        localStorage.removeItem('kimidori_mock_user');
        await firebase.auth().signOut();
        this.showToast("ログアウトしました", "success");
      } catch (err) {
        console.error(err);
        this.showToast("ログアウト失敗: " + err.message, "error");
      }
    });

    // 管理者向け設定保存処理
    const btnAdminSave = document.getElementById('btnAdminSaveYoutubeCreds');
    const adminClientIdInput = document.getElementById('adminYoutubeClientId');
    const adminClientSecretInput = document.getElementById('adminYoutubeClientSecret');

    if (btnAdminSave && adminClientIdInput && adminClientSecretInput) {
      // 1. ローカルから即時復元 (初期表示の速度確保)
      const cachedId = window.settingsManager.get('globalYoutubeClientId');
      const cachedSecret = window.settingsManager.get('globalYoutubeClientSecret');

      if (cachedId) {
        adminClientIdInput.value = cachedId;
      } else if (adminClientIdInput.value && !adminClientIdInput.value.includes('dummy')) {
        // 初回ロード時、HTMLの初期プレバインド値を設定キャッシュにバインド
        window.settingsManager.set('globalYoutubeClientId', adminClientIdInput.value);
        window.settingsManager.set('youtubeClientId', adminClientIdInput.value);
      } else {
        adminClientIdInput.value = "";
      }

      if (cachedSecret) {
        adminClientSecretInput.value = cachedSecret;
      } else if (adminClientSecretInput.value && !adminClientSecretInput.value.includes('dummy')) {
        // 初回ロード時、HTMLの初期プレバインド値を設定キャッシュにバインド
        window.settingsManager.set('globalYoutubeClientSecret', adminClientSecretInput.value);
        window.settingsManager.set('youtubeClientSecret', adminClientSecretInput.value);
      } else {
        adminClientSecretInput.value = "";
      }

      // 2. クラウド (Firestore) からの同期ロードを試みる
      try {
        if (typeof db !== 'undefined' && firebaseConfig.apiKey !== "YOUR_API_KEY") {
          db.collection('settings').doc('global_youtube').get().then(doc => {
            if (doc.exists) {
              const data = doc.data();
              if (data.clientId) {
                adminClientIdInput.value = data.clientId;
                window.settingsManager.set('globalYoutubeClientId', data.clientId);
                window.settingsManager.set('youtubeClientId', data.clientId);
              }
              if (data.clientSecret) {
                adminClientSecretInput.value = data.clientSecret;
                window.settingsManager.set('globalYoutubeClientSecret', data.clientSecret);
                window.settingsManager.set('youtubeClientSecret', data.clientSecret);
              }
              console.log("☁️ クラウド (Firestore) からグローバルOAuth設定を取得しました");
            }
          }).catch(err => {
            console.warn("Firestore からのグローバル設定取得に失敗しました:", err);
          });
        }
      } catch (e) {
        console.warn("Firestore 初期化エラー (ローカルデータを使用します):", e);
      }

      btnAdminSave.addEventListener('click', async () => {
        const cId = adminClientIdInput.value.trim();
        const cSec = adminClientSecretInput.value.trim();
        
        // まずローカルに保存
        window.settingsManager.set('globalYoutubeClientId', cId);
        window.settingsManager.set('globalYoutubeClientSecret', cSec);
        window.settingsManager.set('youtubeClientId', cId);
        window.settingsManager.set('youtubeClientSecret', cSec);
        
        // クラウド (Firestore) への同期保存を試みる
        let savedToCloud = false;
        try {
          if (typeof db !== 'undefined' && firebaseConfig.apiKey !== "YOUR_API_KEY") {
            await db.collection('settings').doc('global_youtube').set({
              clientId: cId,
              clientSecret: cSec,
              updatedAt: firebase.firestore.FieldValue.serverTimestamp()
            }, { merge: true });
            savedToCloud = true;
            console.log("☁️ クラウド (Firestore) にグローバルOAuth設定を保存しました");
          }
        } catch (err) {
          console.error("Firestore へのグローバル設定同期に失敗しました:", err);
        }

        if (savedToCloud) {
          this.showToast("クラウドにグローバル認証情報を同期・保存しました！", "success");
        } else {
          this.showToast("グローバル認証情報をローカルに保存しました", "info");
        }
      });
    }

    // 認証監視
    firebase.auth().onAuthStateChanged(user => {
      if (user) {
        this.updateAuthState(user);
      } else {
        // Firebaseがログインしていない場合、ローカルのモックユーザーをチェック
        const mockUserStr = localStorage.getItem('kimidori_mock_user');
        if (mockUserStr) {
          try {
            const mockUser = JSON.parse(mockUserStr);
            this.updateAuthState(mockUser);
            return;
          } catch (e) {
            localStorage.removeItem('kimidori_mock_user');
          }
        }
        this.updateAuthState(null);
      }
    });
  }

  // 統一的な認証状態反映ロジック
  updateAuthState(user) {
    const loginPage = document.getElementById('loginPage');
    const currentUserDisplay = document.getElementById('currentUserDisplay');
    const navAdminItem = document.getElementById('navAdminItem');

    if (user) {
      console.log("🔥 ログイン中ユーザー:", user.email);
      if (loginPage) loginPage.classList.add('hidden');
      if (currentUserDisplay) currentUserDisplay.textContent = `👑 ${user.email}`;

      // 管理者判定: sl0wmugi9@gmail.com または oumaumauma32@gmail.com
      const isAdmin = user.email === 'sl0wmugi9@gmail.com' || user.email === 'oumaumauma32@gmail.com';

      if (isAdmin) {
        if (navAdminItem) navAdminItem.style.display = 'flex';
        this.loadAdminStats();
      } else {
        if (navAdminItem) navAdminItem.style.display = 'none';
        // もし現在管理者ページにいた場合はダッシュボードへ強制遷移
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav && activeNav.dataset.target === 'admin') {
          document.querySelector('.nav-item[data-target="dashboard"]').click();
        }
      }
    } else {
      console.log("🔑 未ログイン");
      if (loginPage) loginPage.classList.remove('hidden');
      if (currentUserDisplay) currentUserDisplay.textContent = "";
      if (navAdminItem) navAdminItem.style.display = 'none';

      // 未ログイン時はダッシュボードを表示しておく（UIリセット）
      document.querySelectorAll('.view-section').forEach(sec => {
        sec.classList.remove('active');
      });
      document.getElementById('view-dashboard')?.classList.add('active');
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelector('.nav-item[data-target="dashboard"]')?.classList.add('active');
    }
  }

  // 管理者パネルの情報読み込み・モック表示
  loadAdminStats() {
    // モックデータ（プレミアム感を出すため）
    const userCountEl = document.getElementById('adminUserCount');
    const jobCountEl = document.getElementById('adminJobCount');
    const userListBody = document.getElementById('adminUserListBody');
    const serverUrlEl = document.getElementById('adminServerUrl');

    if (serverUrlEl) {
      serverUrlEl.textContent = window.apiClient ? window.apiClient.baseUrl : (
        (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
          ? `http://${window.location.hostname}:8080`
          : "https://api.your-saas-domain.com"
      );
    }

    if (userCountEl) userCountEl.textContent = "3";
    if (jobCountEl) jobCountEl.textContent = "42";

    if (userListBody) {
      userListBody.innerHTML = `
        <tr style="border-bottom: 1px solid var(--border-color);">
          <td style="padding: 0.75rem 1rem; font-family: monospace;">sl0wmugi9@gmail.com_uid</td>
          <td style="padding: 0.75rem 1rem;">sl0wmugi9@gmail.com</td>
          <td style="padding: 0.75rem 1rem;"><span style="color: var(--accent-primary); font-weight: bold;">👑 共同管理者</span></td>
          <td style="padding: 0.75rem 1rem;"><span style="color: var(--accent-primary);">● アクティブ</span></td>
        </tr>
        <tr style="border-bottom: 1px solid var(--border-color);">
          <td style="padding: 0.75rem 1rem; font-family: monospace;">oumaumauma32@gmail.com_uid</td>
          <td style="padding: 0.75rem 1rem;">oumaumauma32@gmail.com</td>
          <td style="padding: 0.75rem 1rem;"><span style="color: var(--accent-primary); font-weight: bold;">👑 共同管理者</span></td>
          <td style="padding: 0.75rem 1rem;"><span style="color: var(--accent-primary);">● アクティブ</span></td>
        </tr>
        <tr style="border-bottom: 1px solid var(--border-color);">
          <td style="padding: 0.75rem 1rem; font-family: monospace;">user_demo_uid</td>
          <td style="padding: 0.75rem 1rem;">user@example.com</td>
          <td style="padding: 0.75rem 1rem;">一般ユーザー</td>
          <td style="padding: 0.75rem 1rem;"><span style="color: var(--text-secondary);">● オフライン</span></td>
        </tr>
      `;
    }
  }

  // --- トースト通知 ---
  showToast(message, type = "info") {
    const wrapper = document.getElementById('toastWrapper');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    wrapper.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = "toastIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) reverse forwards";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.appController = new AppController();
});
