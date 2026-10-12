/**
 * KIMIDORI YouTube Auto - App Controller
 * UIの制御・バリデーション・ビュー切り替え
 */

class AppController {
  constructor() {
    this.adminUsers = [];
    this.proShortsRefImages = [];
    this.longVideoRefImages = [];
    this.currentProShortsJobId = localStorage.getItem('kimidori_last_pro_shorts_job') || null;
    this.currentLongVideoJobId = localStorage.getItem('kimidori_last_long_video_job') || null;
    this.currentModeBJobId = null;
    this.editorState = null;
    this.editorJobId = null;
    this.editorSourceMode = null;
    this.editorActiveCutIndex = 0;
    this.initViews();
    this.initForms();
    this.initEditForm();
    this.initMangaForm();
    this.initProVideoEditor();
    this.initEditorHandoff();
    this.initSettings();
    this.renderSettings();
    this.validateForms();
    this.initShortsSummaryHandler();
    this.initAdminUserHandlers();
    this.initAuth();
    this.initYoutubeDirectUploadModal();
    setTimeout(() => this.initSavedVideoStocksAndRestore(), 250);
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
          sec.style.display = 'none';
        });
        const targetSec = document.getElementById(`view-${target}`);
        if (targetSec) {
          targetSec.classList.add('active');
          targetSec.style.display = 'block';
        }

        // Pro版ショート動画または長尺動画タブを開いた際は、保存済み5本ストックを最新化
        if (target === 'pro-shorts') {
          this.loadSavedVideoStock('pro_shorts', false);
        } else if (target === 'long-video') {
          this.loadSavedVideoStock('long_video', false);
        }

        // 簡易ショート動画（generate）タブが選択され、かつ生成完了画面が表示中の場合は初期画面にリセット
        if (target === 'generate') {
          const s4 = document.getElementById('step4');
          const vr = document.getElementById('videoResultPanel');
          if (s4 && s4.style.display !== 'none' && vr && vr.style.display !== 'none') {
            this.resetWizard(true); // 静かにリセット
          }
        }
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
      if(val && val.length < 10) {
        this.showToast("有効なGemini APIキーを入力してください", "error");
        return;
      }
      window.settingsManager.set('geminiApiKey', val);
      this.showToast("Gemini APIキーを保存しました", "success");
    });

    // Paid Gemini API Key (有料枠: 画像・キャラクター・動画生成用)
    const paidGeminiInput = document.getElementById('setPaidGeminiKey');
    const savePaidGeminiBtn = document.getElementById('btnSavePaidGemini');
    if (paidGeminiInput && savePaidGeminiBtn) {
      paidGeminiInput.value = window.settingsManager.get('paidGeminiApiKey') || "";
      savePaidGeminiBtn.addEventListener('click', () => {
        const val = paidGeminiInput.value.trim();
        window.settingsManager.set('paidGeminiApiKey', val);
        this.showToast("有料Gemini AIキーを保存しました", "success");
      });
    }

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

    // FLUX.1 [schnell] 設定
    const fluxProviderSelect = document.getElementById('setFluxProvider');
    const falKeyInput = document.getElementById('setFalApiKey');
    const saveFalKeyBtn = document.getElementById('btnSaveFalKey');
    const repKeyInput = document.getElementById('setReplicateKey');
    const saveRepKeyBtn = document.getElementById('btnSaveReplicateKey');
    const groupFal = document.getElementById('groupFalKey');
    const groupRep = document.getElementById('groupReplicateKey');

    if (fluxProviderSelect) {
      fluxProviderSelect.value = window.settingsManager.get('fluxProvider') || 'fal';
      const toggleFluxGroups = () => {
        const p = fluxProviderSelect.value;
        window.settingsManager.set('fluxProvider', p);
        if (groupFal) groupFal.style.display = p === 'fal' ? 'block' : 'none';
        if (groupRep) groupRep.style.display = p === 'replicate' ? 'block' : 'none';
      };
      toggleFluxGroups();
      fluxProviderSelect.addEventListener('change', toggleFluxGroups);
    }
    if (falKeyInput && saveFalKeyBtn) {
      falKeyInput.value = window.settingsManager.get('falApiKey') || '';
      saveFalKeyBtn.addEventListener('click', () => {
        window.settingsManager.set('falApiKey', falKeyInput.value.trim());
        this.showToast('fal.ai APIキーを保存しました', 'success');
      });
    }
    if (repKeyInput && saveRepKeyBtn) {
      repKeyInput.value = window.settingsManager.get('replicateApiToken') || '';
      saveRepKeyBtn.addEventListener('click', () => {
        window.settingsManager.set('replicateApiToken', repKeyInput.value.trim());
        this.showToast('Replicate APIトークンを保存しました', 'success');
      });
    }

    // Google Colab 無料T4 GPU / ComfyUI (LTX-Video) ワーカー設定
    const colabUrlInput = document.getElementById('setColabWorkerUrl');
    const btnTestColab = document.getElementById('btnTestColab');
    const btnSaveColab = document.getElementById('btnSaveColab');
    const colabStatusMsg = document.getElementById('colabStatusMsg');

    const adminColabInput = document.getElementById('adminColabWorkerUrl');
    const btnAdminSaveColab = document.getElementById('btnAdminSaveColab');
    const btnAdminTestColab = document.getElementById('btnAdminTestColab');
    const adminColabStatusMsg = document.getElementById('adminColabStatusMsg');
    const adminColabStatusBadge = document.getElementById('adminColabStatusBadge');

    const proShortsStatusBadge = document.getElementById('proShortsColabStatusBadge');
    const btnQuickCheckColabPro = document.getElementById('btnQuickCheckColabPro');

    const currentSavedUrl = (window.settingsManager.getColabUrl ? window.settingsManager.getColabUrl() : window.settingsManager.get('colabWorkerUrl')) || '';

    // 入力欄の初期化と同期
    if (colabUrlInput) colabUrlInput.value = currentSavedUrl;
    if (adminColabInput) adminColabInput.value = currentSavedUrl;

    const syncColabInputs = (url) => {
      if (colabUrlInput && colabUrlInput.value !== url) colabUrlInput.value = url;
      if (adminColabInput && adminColabInput.value !== url) adminColabInput.value = url;
    };

    const updateColabStatusUI = (status, text, detailHtml = '') => {
      // バッジ更新
      if (adminColabStatusBadge) {
        if (status === 'online') {
          adminColabStatusBadge.style.background = 'rgba(57, 255, 20, 0.15)';
          adminColabStatusBadge.style.color = 'var(--accent-primary)';
          adminColabStatusBadge.textContent = 'AI Core: Online';
        } else if (status === 'offline') {
          adminColabStatusBadge.style.background = 'rgba(255, 107, 107, 0.15)';
          adminColabStatusBadge.style.color = '#ff6b6b';
          adminColabStatusBadge.textContent = 'Offline';
        } else if (status === 'checking') {
          adminColabStatusBadge.style.background = 'rgba(0, 210, 255, 0.15)';
          adminColabStatusBadge.style.color = '#00d2ff';
          adminColabStatusBadge.textContent = '接続検証中...';
        } else {
          adminColabStatusBadge.style.background = 'rgba(255, 255, 255, 0.1)';
          adminColabStatusBadge.style.color = 'var(--text-secondary)';
          adminColabStatusBadge.textContent = text || '未確認';
        }
      }

      if (proShortsStatusBadge) {
        if (status === 'online') {
          proShortsStatusBadge.style.background = 'rgba(57, 255, 20, 0.15)';
          proShortsStatusBadge.style.color = 'var(--accent-primary)';
          proShortsStatusBadge.textContent = 'Online';
        } else if (status === 'offline') {
          proShortsStatusBadge.style.background = 'rgba(255, 107, 107, 0.15)';
          proShortsStatusBadge.style.color = '#ff6b6b';
          proShortsStatusBadge.textContent = 'Offline';
        } else if (status === 'checking') {
          proShortsStatusBadge.textContent = '確認中...';
        }
      }

      // 詳細メッセージ更新
      if (colabStatusMsg) {
        colabStatusMsg.innerHTML = detailHtml || `ステータス: ${text}`;
      }
      if (adminColabStatusMsg) {
        adminColabStatusMsg.innerHTML = detailHtml || `ステータス: ${text}`;
      }
    };

    // 保存処理
    const handleSaveColabUrl = async (url) => {
      const u = (url || '').trim();
      if (window.settingsManager.setColabUrl) {
        window.settingsManager.setColabUrl(u);
      } else {
        window.settingsManager.set('colabWorkerUrl', u);
      }
      syncColabInputs(u);
      if (window.apiClient && window.apiClient.saveColabConfig) {
        await window.apiClient.saveColabConfig(u).catch(() => {});
      }
      this.showToast('AI Core接続設定を保存しました', 'success');
      updateColabStatusUI('saved', '保存済み (未確認)', `<span style="color: var(--accent-primary);">URL保存完了: ${u || '未設定'}</span>`);
    };

    if (btnSaveColab && colabUrlInput) {
      btnSaveColab.addEventListener('click', () => handleSaveColabUrl(colabUrlInput.value));
    }
    if (btnAdminSaveColab && adminColabInput) {
      btnAdminSaveColab.addEventListener('click', () => handleSaveColabUrl(adminColabInput.value));
    }

    // 接続テスト処理（スピナーアニメーション対応）
    const handleTestColab = async (url, triggerBtn) => {
      const u = (url || '').trim();
      if (!u) return this.showToast('AI Core接続先を入力してください', 'error');

      handleSaveColabUrl(u);

      const origHtml = triggerBtn ? triggerBtn.innerHTML : null;
      if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.classList.add('is-loading');
        triggerBtn.innerHTML = '<span class="btn-spinner"></span><span>検証中...</span>';
      }
      updateColabStatusUI('checking', '接続検証中...');

      try {
        const res = await window.apiClient.checkColabHealth(u);
        if (res.connected) {
          const serviceName = 'AI Core';
          const dev = res.device || 'GPU';
          const vram = res.vram_gb ? `${res.vram_gb}GB` : '15GB';
          const successHtml = `<span style="color: var(--accent-primary);">接続成功: AI Core: Online</span>`;
          updateColabStatusUI('online', 'オンライン', successHtml);
          this.showToast(`${serviceName} への接続に成功しました`, 'success');
        } else {
          const errMsg = this._sanitizeUserMessage(res.error || 'AI Coreから応答がありません');
          const failHtml = `<span style="color: #ff6b6b;">接続失敗: ${errMsg}</span>`;
          updateColabStatusUI('offline', 'Offline', failHtml);
          this.showToast(`接続失敗: ${errMsg}`, 'error', 6000);
        }
      } catch (e) {
        const errHtml = `<span style="color: #ff6b6b;">接続エラー: ${this._sanitizeUserMessage(e.message)}</span>`;
        updateColabStatusUI('offline', 'エラー', errHtml);
        this.showToast('接続テストエラー: ' + e.message, 'error');
      } finally {
        if (triggerBtn && origHtml) {
          triggerBtn.disabled = false;
          triggerBtn.classList.remove('is-loading');
          triggerBtn.innerHTML = origHtml;
        }
      }
    };

    if (btnTestColab && colabUrlInput) {
      btnTestColab.addEventListener('click', () => handleTestColab(colabUrlInput.value, btnTestColab));
    }
    if (btnAdminTestColab && adminColabInput) {
      btnAdminTestColab.addEventListener('click', () => handleTestColab(adminColabInput.value, btnAdminTestColab));
    }
    if (btnQuickCheckColabPro) {
      btnQuickCheckColabPro.addEventListener('click', () => {
        const u = (window.settingsManager.getColabUrl ? window.settingsManager.getColabUrl() : window.settingsManager.get('colabWorkerUrl')) || '';
        handleTestColab(u, btnQuickCheckColabPro);
      });
    }

    // --- TTS Engine Settings (全14エンジン対応) ---
    const ttsEngineSelect = document.getElementById('setTtsEngine');
    const voiceSelect = document.getElementById('setVoiceName');
    const speakingRateInput = document.getElementById('setSpeakingRate');
    const labelSpeakingRate = document.getElementById('labelSpeakingRate');

    // 各種キー・入力要素
    const googleTtsInput = document.getElementById('setGoogleTtsKey');
    const elevenLabsInput = document.getElementById('setElevenLabsKey');
    const openAiKeyInput = document.getElementById('setOpenAiTtsKey');
    const openAiModelSelect = document.getElementById('setOpenAiTtsModel');
    const azureKeyInput = document.getElementById('setAzureTtsKey');
    const azureRegionInput = document.getElementById('setAzureTtsRegion');
    const awsAccessKeyInput = document.getElementById('setAwsAccessKey');
    const awsSecretKeyInput = document.getElementById('setAwsSecretKey');
    const awsRegionInput = document.getElementById('setAwsRegion');
    const voicevoxUrlInput = document.getElementById('setVoicevoxUrl');
    const sharevoxUrlInput = document.getElementById('setSharevoxUrl');
    const coeiroinkUrlInput = document.getElementById('setCoeiroinkUrl');
    const aivisUrlInput = document.getElementById('setAivisUrl');
    const aivisKeyInput = document.getElementById('setAivisKey');
    const ossTtsUrlInput = document.getElementById('setOssTtsUrl');
    const ossTtsFormatSelect = document.getElementById('setOssTtsFormat');
    const ossVoiceInput = document.getElementById('setOssVoice');
    const ossElevenlabsUrlInput = document.getElementById('setOssElevenlabsUrl');
    const ossElevenlabsProtocolSelect = document.getElementById('setOssElevenlabsProtocol');
    const ossElevenlabsVoiceIdInput = document.getElementById('setOssElevenlabsVoiceId');
    const ossElevenlabsKeyInput = document.getElementById('setOssElevenlabsKey');
    const voxcpmPromptInput = document.getElementById('setVoxcpmPrompt');
    const ondokuTokenInput = document.getElementById('setOndokuToken');
    const coefontKeyInput = document.getElementById('setCoefontKey');
    const coefontIdInput = document.getElementById('setCoefontId');

    // 各種コンテナ
    const groupGoogle = document.getElementById('groupGoogleTtsKey');
    const groupElevenLabs = document.getElementById('groupElevenLabsKey');
    const groupOpenAi = document.getElementById('groupOpenAiTts');
    const groupAzure = document.getElementById('groupAzureTts');
    const groupPolly = document.getElementById('groupPollyTts');
    const groupVoicevox = document.getElementById('groupVoicevoxUrl');
    const groupSharevox = document.getElementById('groupSharevoxUrl');
    const groupCoeiroink = document.getElementById('groupCoeiroinkUrl');
    const groupAivis = document.getElementById('groupAivis');
    const groupOssCustom = document.getElementById('groupOssCustom');
    const groupOssElevenlabs = document.getElementById('groupOssElevenlabs');
    const groupOndoku = document.getElementById('groupOndokuToken');
    const groupCoefont = document.getElementById('groupCoefont');

    // エンジン別ボイスカタログ定義
    const engineVoices = {
      edge: [
        { id: "nanami", name: "七海（女性・標準）" },
        { id: "keita", name: "慶太（男性・標準）" },
        { id: "aoi", name: "あおい（女性・若い）" },
        { id: "daichi", name: "大地（男性・落ち着き）" },
        { id: "mayu", name: "まゆ（女性・明るい）" },
        { id: "naoki", name: "直樹（男性・若い）" },
        { id: "shiori", name: "しおり（女性・柔らか）" }
      ],
      gtts: [
        { id: "ja", name: "日本語（標準）" }
      ],
      voicevox: [
        { id: "3", name: "ずんだもん (ノーマル)" },
        { id: "1", name: "ずんだもん (あまあま)" },
        { id: "7", name: "ずんだもん (ツンツン)" },
        { id: "5", name: "ずんだもん (セクシー)" },
        { id: "2", name: "四国めたん (ノーマル)" },
        { id: "0", name: "四国めたん (あまあま)" },
        { id: "8", name: "春日部つむぎ (ノーマル)" },
        { id: "10", name: "雨晴はう (ノーマル)" },
        { id: "9", name: "波音リツ (ノーマル)" },
        { id: "11", name: "玄野武宏 (ノーマル)" },
        { id: "12", name: "白上虎太郎 (ノーマル)" },
        { id: "13", name: "青山龍星 (ノーマル)" },
        { id: "14", name: "冥鳴ひまり (ノーマル)" },
        { id: "16", name: "九州そら (ノーマル)" }
      ],
      sharevox: [
        { id: "0", name: "小春音アミ (ノーマル)" },
        { id: "1", name: "つくよみちゃん (ノーマル)" },
        { id: "2", name: "白痴ー (ノーマル)" }
      ],
      coeiroink: [
        { id: "0", name: "つくよみちゃん (標準スタイル)" },
        { id: "1", name: "MANA (標準スタイル)" }
      ],
      aivis: [
        { id: "1", name: "話者 1" },
        { id: "2", name: "話者 2" }
      ],
      oss_custom: [
        { id: "default", name: "デフォルト音声" }
      ],
      voxcpm: [
        { id: "default", name: "VoxCPM 標準ボイス (48kHz・スタジオクリア)" },
        { id: "announcer_female", name: "女性アナウンサー (落ち着いた解説・知性)" },
        { id: "narrator_male", name: "男性ナレーター (説得力・ビジネス朗読)" },
        { id: "energetic_host", name: "明快ホスト (明るくテンポ良い解説)" },
        { id: "calm_story", name: "物語調 (感情豊かなストーリーテリング)" },
        { id: "custom_clone", name: "カスタムボイス (Voice Designプロンプト反映)" }
      ],
      oss_elevenlabs: [
        { id: "21m00Tcm4TlvDq8ikWAM", name: "Rachel (ElevenLabs互換・女性)" },
        { id: "pNInz6obpgDQGcFmaJgB", name: "Adam (ElevenLabs互換・男性)" },
        { id: "EXAVITQu4vr4xnSDxMaL", name: "Bella (ElevenLabs互換・女性)" },
        { id: "oss_default", name: "OSS標準 (設定画面のVoice IDを使用)" }
      ],
      openai: [
        { id: "alloy", name: "Alloy (中性的・標準)" },
        { id: "echo", name: "Echo (男性・クリア)" },
        { id: "fable", name: "Fable (表現力豊か)" },
        { id: "onyx", name: "Onyx (男性・深みのある声)" },
        { id: "nova", name: "Nova (女性・明るい)" },
        { id: "shimmer", name: "Shimmer (女性・落ち着いた響き)" }
      ],
      elevenlabs: [
        { id: "21m00Tcm4TlvDq8ikWAM", name: "Rachel (女性)" },
        { id: "AZnzlk1XvdvUeBnXmlld", name: "Domi (女性)" },
        { id: "EXAVITQu4vr4xnSDxMaL", name: "Bella (女性)" },
        { id: "ErXwobaYiN019PkySvjV", name: "Antoni (男性)" },
        { id: "VR6AewLTigWG4xSOukaG", name: "Arnold (男性)" },
        { id: "pNInz6obpgDQGcFmaJgB", name: "Adam (男性)" }
      ],
      google: [
        { id: "ja-JP-Neural2-B", name: "Neural2-B (女性)" },
        { id: "ja-JP-Neural2-C", name: "Neural2-C (男性)" },
        { id: "ja-JP-Wavenet-A", name: "WaveNet-A (女性)" },
        { id: "ja-JP-Wavenet-C", name: "WaveNet-C (男性)" }
      ],
      azure: [
        { id: "ja-JP-NanamiNeural", name: "Nanami (女性)" },
        { id: "ja-JP-KeitaNeural", name: "Keita (男性)" },
        { id: "ja-JP-AoiNeural", name: "Aoi (女性)" },
        { id: "ja-JP-DaichiNeural", name: "Daichi (男性)" }
      ],
      amazon_polly: [
        { id: "Mizuki", name: "Mizuki (女性・標準)" },
        { id: "Takumi", name: "Takumi (男性・Neural)" },
        { id: "Kazuha", name: "Kazuha (女性・Neural)" },
        { id: "Tomoko", name: "Tomoko (女性・標準)" }
      ],
      ondoku: [
        { id: "default", name: "標準音声" }
      ],
      coefont: [
        { id: "default", name: "登録ボイス" }
      ]
    };

    const updateVoiceOptions = (engine) => {
      if (!voiceSelect) return;
      const list = engineVoices[engine] || engineVoices.edge;
      const currentVal = window.settingsManager.get('voiceName');
      voiceSelect.innerHTML = list.map(v => `<option value="${v.id}">${v.name}</option>`).join('');
      if (list.some(v => v.id === currentVal)) {
        voiceSelect.value = currentVal;
      } else {
        voiceSelect.value = list[0].id;
      }
    };

    const updateTtsUi = (engine) => {
      if (groupGoogle) groupGoogle.style.display = engine === 'google' ? 'block' : 'none';
      if (groupElevenLabs) groupElevenLabs.style.display = engine === 'elevenlabs' ? 'block' : 'none';
      if (groupOpenAi) groupOpenAi.style.display = engine === 'openai' ? 'flex' : 'none';
      if (groupAzure) groupAzure.style.display = engine === 'azure' ? 'flex' : 'none';
      if (groupPolly) groupPolly.style.display = engine === 'amazon_polly' ? 'flex' : 'none';
      if (groupVoicevox) groupVoicevox.style.display = engine === 'voicevox' ? 'block' : 'none';
      if (groupSharevox) groupSharevox.style.display = engine === 'sharevox' ? 'block' : 'none';
      if (groupCoeiroink) groupCoeiroink.style.display = engine === 'coeiroink' ? 'block' : 'none';
      if (groupAivis) groupAivis.style.display = engine === 'aivis' ? 'flex' : 'none';
      if (groupOssCustom) groupOssCustom.style.display = engine === 'oss_custom' ? 'flex' : 'none';
      if (groupOssElevenlabs) groupOssElevenlabs.style.display = (engine === 'oss_elevenlabs' || engine === 'voxcpm') ? 'flex' : 'none';
      if (groupOndoku) groupOndoku.style.display = engine === 'ondoku' ? 'block' : 'none';
      if (groupCoefont) groupCoefont.style.display = engine === 'coefont' ? 'flex' : 'none';

      updateVoiceOptions(engine);
    };

    // 初期値の読み込み
    if (speakingRateInput && labelSpeakingRate) {
      const savedRate = window.settingsManager.get('speakingRate') || 1.0;
      speakingRateInput.value = savedRate;
      labelSpeakingRate.textContent = `${parseFloat(savedRate).toFixed(2)}x`;
      speakingRateInput.addEventListener('input', (e) => {
        labelSpeakingRate.textContent = `${parseFloat(e.target.value).toFixed(2)}x`;
      });
    }

    if (googleTtsInput) googleTtsInput.value = window.settingsManager.get('googleTtsKey') || "";
    if (elevenLabsInput) elevenLabsInput.value = window.settingsManager.get('elevenLabsKey') || "";
    if (openAiKeyInput) openAiKeyInput.value = window.settingsManager.get('openAiTtsKey') || "";
    if (openAiModelSelect) openAiModelSelect.value = window.settingsManager.get('openAiTtsModel') || "tts-1";
    if (azureKeyInput) azureKeyInput.value = window.settingsManager.get('azureTtsKey') || "";
    if (azureRegionInput) azureRegionInput.value = window.settingsManager.get('azureTtsRegion') || "japaneast";
    if (awsAccessKeyInput) awsAccessKeyInput.value = window.settingsManager.get('awsAccessKey') || "";
    if (awsSecretKeyInput) awsSecretKeyInput.value = window.settingsManager.get('awsSecretKey') || "";
    if (awsRegionInput) awsRegionInput.value = window.settingsManager.get('awsRegion') || "ap-northeast-1";
    if (voicevoxUrlInput) voicevoxUrlInput.value = window.settingsManager.get('voicevoxUrl') || "http://localhost:50021";
    if (sharevoxUrlInput) sharevoxUrlInput.value = window.settingsManager.get('sharevoxUrl') || "http://localhost:50025";
    if (coeiroinkUrlInput) coeiroinkUrlInput.value = window.settingsManager.get('coeiroinkUrl') || "http://localhost:50031";
    if (aivisUrlInput) aivisUrlInput.value = window.settingsManager.get('aivisUrl') || "http://localhost:10101";
    if (aivisKeyInput) aivisKeyInput.value = window.settingsManager.get('aivisKey') || "";
    if (ossTtsUrlInput) ossTtsUrlInput.value = window.settingsManager.get('ossTtsUrl') || "http://localhost:9880";
    if (ossTtsFormatSelect) ossTtsFormatSelect.value = window.settingsManager.get('ossTtsFormat') || "openai";
    if (ossVoiceInput) ossVoiceInput.value = window.settingsManager.get('ossVoice') || "";
    if (ossElevenlabsUrlInput) ossElevenlabsUrlInput.value = window.settingsManager.get('voxcpmUrl') || window.settingsManager.get('ossElevenlabsUrl') || "http://localhost:8808";
    if (ossElevenlabsProtocolSelect) ossElevenlabsProtocolSelect.value = window.settingsManager.get('voxcpmProtocol') || window.settingsManager.get('ossElevenlabsProtocol') || "vllm_omni";
    if (ossElevenlabsVoiceIdInput) ossElevenlabsVoiceIdInput.value = window.settingsManager.get('voxcpmVoiceId') || window.settingsManager.get('ossElevenlabsVoiceId') || "default";
    if (ossElevenlabsKeyInput) ossElevenlabsKeyInput.value = window.settingsManager.get('voxcpmKey') || window.settingsManager.get('ossElevenlabsKey') || "";
    if (voxcpmPromptInput) voxcpmPromptInput.value = window.settingsManager.get('voxcpmPrompt') || "";
    if (ondokuTokenInput) ondokuTokenInput.value = window.settingsManager.get('ondokuToken') || "";
    if (coefontKeyInput) coefontKeyInput.value = window.settingsManager.get('coefontKey') || "";
    if (coefontIdInput) coefontIdInput.value = window.settingsManager.get('coefontId') || "";

    if (ttsEngineSelect) {
      const currentEngine = window.settingsManager.get('ttsEngine') || 'edge';
      ttsEngineSelect.value = currentEngine;
      updateTtsUi(currentEngine);

      ttsEngineSelect.addEventListener('change', (e) => {
        updateTtsUi(e.target.value);
      });
    }

    // ナレーション設定の保存
    const saveVoiceBtn = document.getElementById('btnSaveVoice');
    if (saveVoiceBtn) {
      saveVoiceBtn.addEventListener('click', () => {
        if (ttsEngineSelect) window.settingsManager.set('ttsEngine', ttsEngineSelect.value);
        if (voiceSelect) window.settingsManager.set('voiceName', voiceSelect.value);
        if (speakingRateInput) window.settingsManager.set('speakingRate', parseFloat(speakingRateInput.value) || 1.0);
        if (googleTtsInput) window.settingsManager.set('googleTtsKey', googleTtsInput.value.trim());
        if (elevenLabsInput) window.settingsManager.set('elevenLabsKey', elevenLabsInput.value.trim());
        if (openAiKeyInput) window.settingsManager.set('openAiTtsKey', openAiKeyInput.value.trim());
        if (openAiModelSelect) window.settingsManager.set('openAiTtsModel', openAiModelSelect.value);
        if (azureKeyInput) window.settingsManager.set('azureTtsKey', azureKeyInput.value.trim());
        if (azureRegionInput) window.settingsManager.set('azureTtsRegion', azureRegionInput.value.trim());
        if (awsAccessKeyInput) window.settingsManager.set('awsAccessKey', awsAccessKeyInput.value.trim());
        if (awsSecretKeyInput) window.settingsManager.set('awsSecretKey', awsSecretKeyInput.value.trim());
        if (awsRegionInput) window.settingsManager.set('awsRegion', awsRegionInput.value.trim());
        if (voicevoxUrlInput) window.settingsManager.set('voicevoxUrl', voicevoxUrlInput.value.trim());
        if (sharevoxUrlInput) window.settingsManager.set('sharevoxUrl', sharevoxUrlInput.value.trim());
        if (coeiroinkUrlInput) window.settingsManager.set('coeiroinkUrl', coeiroinkUrlInput.value.trim());
        if (aivisUrlInput) window.settingsManager.set('aivisUrl', aivisUrlInput.value.trim());
        if (aivisKeyInput) window.settingsManager.set('aivisKey', aivisKeyInput.value.trim());
        if (ossTtsUrlInput) window.settingsManager.set('ossTtsUrl', ossTtsUrlInput.value.trim());
        if (ossTtsFormatSelect) window.settingsManager.set('ossTtsFormat', ossTtsFormatSelect.value);
        if (ossVoiceInput) window.settingsManager.set('ossVoice', ossVoiceInput.value.trim());
        if (ossElevenlabsUrlInput) {
          const urlVal = ossElevenlabsUrlInput.value.trim();
          window.settingsManager.set('ossElevenlabsUrl', urlVal);
          window.settingsManager.set('voxcpmUrl', urlVal);
        }
        if (ossElevenlabsProtocolSelect) {
          const protoVal = ossElevenlabsProtocolSelect.value;
          window.settingsManager.set('ossElevenlabsProtocol', protoVal);
          window.settingsManager.set('voxcpmProtocol', protoVal);
        }
        if (ossElevenlabsVoiceIdInput) {
          const vIdVal = ossElevenlabsVoiceIdInput.value.trim();
          window.settingsManager.set('ossElevenlabsVoiceId', vIdVal);
          window.settingsManager.set('voxcpmVoiceId', vIdVal);
        }
        if (ossElevenlabsKeyInput) {
          const keyVal = ossElevenlabsKeyInput.value.trim();
          window.settingsManager.set('ossElevenlabsKey', keyVal);
          window.settingsManager.set('voxcpmKey', keyVal);
        }
        if (voxcpmPromptInput) window.settingsManager.set('voxcpmPrompt', voxcpmPromptInput.value.trim());
        if (ondokuTokenInput) window.settingsManager.set('ondokuToken', ondokuTokenInput.value.trim());
        if (coefontKeyInput) window.settingsManager.set('coefontKey', coefontKeyInput.value.trim());
        if (coefontIdInput) window.settingsManager.set('coefontId', coefontIdInput.value.trim());

        this.showToast("ナレーション設定を保存しました", "success");
      });
    }

    // テスト音声試聴ボタン
    const btnTestTTS = document.getElementById('btnTestTTS');
    const ttsTestTextInput = document.getElementById('setTtsTestText');
    const ttsPreviewAudio = document.getElementById('ttsPreviewAudio');
    if (btnTestTTS) {
      btnTestTTS.addEventListener('click', async () => {
        const text = ttsTestTextInput ? ttsTestTextInput.value.trim() : "こんにちは。音声合成のテストです。";
        if (!text) {
          return this.showToast("試聴したいテキストを入力してください", "warning");
        }
        btnTestTTS.disabled = true;
        btnTestTTS.innerHTML = `<div style="border: 2px solid rgba(255,255,255,0.2); border-top-color: #39ff14; border-radius: 50%; width: 12px; height: 12px; animation: spin 1s linear infinite;"></div> 生成中...`;

        try {
          const previewPayload = {
            text,
            tts_engine: ttsEngineSelect ? ttsEngineSelect.value : "edge",
            voice_name: voiceSelect ? voiceSelect.value : "nanami",
            speaking_rate: speakingRateInput ? parseFloat(speakingRateInput.value) || 1.0 : 1.0,
            google_tts_key: googleTtsInput ? googleTtsInput.value.trim() : "",
            elevenlabs_key: elevenLabsInput ? elevenLabsInput.value.trim() : "",
            openai_key: openAiKeyInput ? openAiKeyInput.value.trim() : "",
            openai_model: openAiModelSelect ? openAiModelSelect.value : "tts-1",
            azure_key: azureKeyInput ? azureKeyInput.value.trim() : "",
            azure_region: azureRegionInput ? azureRegionInput.value.trim() : "japaneast",
            aws_access_key: awsAccessKeyInput ? awsAccessKeyInput.value.trim() : "",
            aws_secret_key: awsSecretKeyInput ? awsSecretKeyInput.value.trim() : "",
            aws_region: awsRegionInput ? awsRegionInput.value.trim() : "ap-northeast-1",
            voicevox_url: voicevoxUrlInput ? voicevoxUrlInput.value.trim() : "http://localhost:50021",
            sharevox_url: sharevoxUrlInput ? sharevoxUrlInput.value.trim() : "http://localhost:50025",
            coeiroink_url: coeiroinkUrlInput ? coeiroinkUrlInput.value.trim() : "http://localhost:50031",
            aivis_url: aivisUrlInput ? aivisUrlInput.value.trim() : "http://localhost:10101",
            aivis_key: aivisKeyInput ? aivisKeyInput.value.trim() : "",
            oss_tts_url: ossTtsUrlInput ? ossTtsUrlInput.value.trim() : "http://localhost:9880",
            oss_tts_format: ossTtsFormatSelect ? ossTtsFormatSelect.value : "openai",
            oss_voice: ossVoiceInput ? ossVoiceInput.value.trim() : "",
            oss_elevenlabs_url: ossElevenlabsUrlInput ? ossElevenlabsUrlInput.value.trim() : "http://localhost:8808",
            oss_elevenlabs_key: ossElevenlabsKeyInput ? ossElevenlabsKeyInput.value.trim() : "",
            oss_elevenlabs_voice_id: ossElevenlabsVoiceIdInput ? ossElevenlabsVoiceIdInput.value.trim() : "default",
            oss_elevenlabs_protocol: ossElevenlabsProtocolSelect ? ossElevenlabsProtocolSelect.value : "vllm_omni",
            voxcpm_url: ossElevenlabsUrlInput ? ossElevenlabsUrlInput.value.trim() : (window.settingsManager.get('voxcpmUrl') || "http://localhost:8808"),
            voxcpm_key: ossElevenlabsKeyInput ? ossElevenlabsKeyInput.value.trim() : (window.settingsManager.get('voxcpmKey') || ""),
            voxcpm_voice_id: voiceSelect ? voiceSelect.value : (ossElevenlabsVoiceIdInput ? ossElevenlabsVoiceIdInput.value.trim() : "default"),
            voxcpm_protocol: ossElevenlabsProtocolSelect ? ossElevenlabsProtocolSelect.value : (window.settingsManager.get('voxcpmProtocol') || "vllm_omni"),
            voxcpm_prompt: voxcpmPromptInput ? voxcpmPromptInput.value.trim() : (window.settingsManager.get('voxcpmPrompt') || ""),
            ondoku_token: ondokuTokenInput ? ondokuTokenInput.value.trim() : "",
            coefont_key: coefontKeyInput ? coefontKeyInput.value.trim() : "",
            coefont_id: coefontIdInput ? coefontIdInput.value.trim() : ""
          };

          const audioUrl = await window.apiClient.previewTTS(previewPayload);
          if (ttsPreviewAudio) {
            ttsPreviewAudio.src = audioUrl;
            ttsPreviewAudio.style.display = "block";
            await ttsPreviewAudio.play();
            this.showToast("音声を再生中...", "info");
          }
        } catch (err) {
          console.error("TTSプレビューエラー:", err);
          this.showToast(`試聴エラー: ${err.message}`, "error");
        } finally {
          btnTestTTS.disabled = false;
          btnTestTTS.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> 試聴する`;
        }
      });
    }

    // BYOG（自前環境接続）モード設定
    const setByogEnabled = document.getElementById('setByogEnabled');
    const setByogComfyUrl = document.getElementById('setByogComfyUrl');
    const setByogGeminiKey = document.getElementById('setByogGeminiKey');
    const btnTestByogComfy = document.getElementById('btnTestByogComfy');
    const btnSaveByogSettings = document.getElementById('btnSaveByogSettings');
    const byogComfyStatusMsg = document.getElementById('byogComfyStatusMsg');
    const byogStatusBadge = document.getElementById('byogStatusBadge');

    if (setByogEnabled) {
      setByogEnabled.checked = window.settingsManager.get('byogEnabled') === true;
      setByogEnabled.addEventListener('change', () => {
        window.settingsManager.set('byogEnabled', setByogEnabled.checked);
        if (byogStatusBadge) {
          byogStatusBadge.textContent = setByogEnabled.checked ? 'BYOG有効 (消費0)' : 'BYOG無効';
          byogStatusBadge.style.color = setByogEnabled.checked ? 'var(--accent-primary)' : 'var(--text-secondary)';
        }
      });
    }

    if (setByogComfyUrl) {
      setByogComfyUrl.value = window.settingsManager.get('byogComfyUrl') || '';
    }
    if (setByogGeminiKey) {
      setByogGeminiKey.value = window.settingsManager.get('byogGeminiKey') || '';
    }

    if (btnTestByogComfy) {
      btnTestByogComfy.addEventListener('click', async () => {
        const url = (setByogComfyUrl ? setByogComfyUrl.value : '').trim();
        if (!url) {
          this.showToast('ComfyUI URLを入力してください', 'warning');
          return;
        }
        btnTestByogComfy.disabled = true;
        btnTestByogComfy.textContent = '確認中...';
        if (byogComfyStatusMsg) byogComfyStatusMsg.textContent = '接続テストを実行中...';

        try {
          const res = await window.apiClient.testColabHealth(url);
          if (res && res.connected) {
            if (byogComfyStatusMsg) {
              byogComfyStatusMsg.textContent = `接続成功: ${res.service || 'ComfyUI'} (GPU: ${res.device || 'OK'}, VRAM: ${res.vram_gb || '--'}GB)`;
              byogComfyStatusMsg.style.color = 'var(--accent-primary)';
            }
            this.showToast('ComfyUIへの疎通を確認しました！', 'success');
          } else {
            if (byogComfyStatusMsg) {
              byogComfyStatusMsg.textContent = `接続失敗: ${res.error || '応答がありません'}`;
              byogComfyStatusMsg.style.color = '#ef4444';
            }
            this.showToast('ComfyUIに接続できませんでした', 'error');
          }
        } catch (err) {
          if (byogComfyStatusMsg) {
            byogComfyStatusMsg.textContent = `接続エラー: ${err.message}`;
            byogComfyStatusMsg.style.color = '#ef4444';
          }
          this.showToast(`接続エラー: ${err.message}`, 'error');
        } finally {
          btnTestByogComfy.disabled = false;
          btnTestByogComfy.textContent = '接続テスト';
        }
      });
    }

    if (btnSaveByogSettings) {
      btnSaveByogSettings.addEventListener('click', () => {
        if (setByogComfyUrl) window.settingsManager.set('byogComfyUrl', setByogComfyUrl.value.trim());
        if (setByogGeminiKey) window.settingsManager.set('byogGeminiKey', setByogGeminiKey.value.trim());
        if (setByogEnabled) window.settingsManager.set('byogEnabled', setByogEnabled.checked);
        this.showToast('BYOG自前環境設定を保存しました', 'success');
      });
    }

    // Stripe サブスクリプション加入ボタン群
    document.querySelectorAll('.btn-subscribe-plan').forEach(btn => {
      btn.addEventListener('click', async () => {
        const plan = btn.dataset.plan;
        if (!plan) return;
        btn.disabled = true;
        const origText = btn.textContent;
        btn.textContent = '決済画面へ移動中...';
        try {
          const sessionData = await window.apiClient.createCheckoutSession('subscription', plan);
          if (sessionData && sessionData.checkout_url) {
            window.location.href = sessionData.checkout_url;
          } else {
            this.showToast('決済画面の生成に失敗しました', 'error');
          }
        } catch (err) {
          this.showToast(`エラー: ${err.message}`, 'error');
        } finally {
          btn.disabled = false;
          btn.textContent = origText;
        }
      });
    });

    // 単発クレジットチャージボタン群
    document.querySelectorAll('.btn-charge-credits').forEach(btn => {
      btn.addEventListener('click', async () => {
        const pack = btn.dataset.pack;
        if (!pack) return;
        btn.disabled = true;
        const origText = btn.textContent;
        btn.textContent = '準備中...';
        try {
          const sessionData = await window.apiClient.createCheckoutSession('credit_pack', pack);
          if (sessionData && sessionData.checkout_url) {
            window.location.href = sessionData.checkout_url;
          } else {
            this.showToast('決済画面の生成に失敗しました', 'error');
          }
        } catch (err) {
          this.showToast(`エラー: ${err.message}`, 'error');
        } finally {
          btn.disabled = false;
          btn.textContent = origText;
        }
      });
    });

    // クレジット残高の取得＆表示初期化
    this.refreshUserCredits();

    // マーケティング連携・Webhook設定パネル
    const btnGenerateMarketingToken = document.getElementById('btnGenerateMarketingToken');
    const marketingApiTokenDisplay = document.getElementById('marketingApiTokenDisplay');
    const marketingTokenBadge = document.getElementById('marketingTokenBadge');
    const setMarketingWebhookUrl = document.getElementById('setMarketingWebhookUrl');
    const btnTestMarketingWebhook = document.getElementById('btnTestMarketingWebhook');
    const btnSaveMarketingWebhook = document.getElementById('btnSaveMarketingWebhook');
    const marketingWebhookStatus = document.getElementById('marketingWebhookStatus');

    // 保存済みWebhook URLを復元
    if (setMarketingWebhookUrl) {
      setMarketingWebhookUrl.value = window.settingsManager.get('marketingWebhookUrl') || '';
    }

    // Marketing API Token の発行/再生成
    if (btnGenerateMarketingToken) {
      btnGenerateMarketingToken.addEventListener('click', async () => {
        const userId = window.settingsManager.get('userId') || 'local';
        btnGenerateMarketingToken.disabled = true;
        btnGenerateMarketingToken.textContent = '発行中...';
        try {
          const res = await fetch('/api/marketing/generate-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          if (marketingApiTokenDisplay) {
            marketingApiTokenDisplay.value = data.marketing_api_token || '';
          }
          if (marketingTokenBadge) {
            marketingTokenBadge.textContent = '発行済';
            marketingTokenBadge.style.color = 'var(--accent-primary)';
          }
          this.showToast('Marketing API Tokenを発行しました。安全な場所に保管してください。', 'success');
        } catch (err) {
          this.showToast(`Token発行エラー: ${err.message}`, 'error');
        } finally {
          btnGenerateMarketingToken.disabled = false;
          btnGenerateMarketingToken.textContent = '発行/再生成';
        }
      });
    }

    // Webhook URLテスト送信
    if (btnTestMarketingWebhook) {
      btnTestMarketingWebhook.addEventListener('click', async () => {
        const url = setMarketingWebhookUrl ? setMarketingWebhookUrl.value.trim() : '';
        if (!url) {
          this.showToast('Webhook URLを入力してください', 'warning');
          return;
        }
        btnTestMarketingWebhook.disabled = true;
        btnTestMarketingWebhook.textContent = '送信中...';
        if (marketingWebhookStatus) marketingWebhookStatus.textContent = 'テスト送信を実行中...';
        try {
          const res = await fetch('/api/marketing/test-webhook', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ webhook_url: url })
          });
          const data = await res.json();
          if (data.success) {
            if (marketingWebhookStatus) {
              marketingWebhookStatus.textContent = `テスト送信成功 (HTTP ${data.status_code})`;
              marketingWebhookStatus.style.color = 'var(--accent-primary)';
            }
            this.showToast('Webhookテスト送信成功', 'success');
          } else {
            if (marketingWebhookStatus) {
              marketingWebhookStatus.textContent = `送信失敗: ${data.error || data.message}`;
              marketingWebhookStatus.style.color = '#ef4444';
            }
            this.showToast(`送信失敗: ${data.message}`, 'error');
          }
        } catch (err) {
          if (marketingWebhookStatus) {
            marketingWebhookStatus.textContent = `エラー: ${err.message}`;
            marketingWebhookStatus.style.color = '#ef4444';
          }
          this.showToast(`テスト送信エラー: ${err.message}`, 'error');
        } finally {
          btnTestMarketingWebhook.disabled = false;
          btnTestMarketingWebhook.textContent = 'テスト送信';
        }
      });
    }

    // Webhook URL 保存
    if (btnSaveMarketingWebhook) {
      btnSaveMarketingWebhook.addEventListener('click', () => {
        if (setMarketingWebhookUrl) {
          window.settingsManager.set('marketingWebhookUrl', setMarketingWebhookUrl.value.trim());
        }
        this.showToast('完了通知Webhook URLを保存しました', 'success');
      });
    }

    // YouTube BYOG Client ID / Secret 保存
    const setYoutubeClientId = document.getElementById('setYoutubeClientId');
    const setYoutubeClientSecret = document.getElementById('setYoutubeClientSecret');
    const btnSaveYoutubeByogCreds = document.getElementById('btnSaveYoutubeByogCreds');
    if (setYoutubeClientId) {
      setYoutubeClientId.value = window.settingsManager.get('youtubeClientId') || window.settingsManager.get('globalYoutubeClientId') || '';
    }
    if (setYoutubeClientSecret) {
      setYoutubeClientSecret.value = window.settingsManager.get('youtubeClientSecret') || window.settingsManager.get('globalYoutubeClientSecret') || '';
    }
    if (btnSaveYoutubeByogCreds) {
      btnSaveYoutubeByogCreds.addEventListener('click', () => {
        if (setYoutubeClientId) window.settingsManager.set('youtubeClientId', setYoutubeClientId.value.trim());
        if (setYoutubeClientSecret) window.settingsManager.set('youtubeClientSecret', setYoutubeClientSecret.value.trim());
        this.showToast('YouTube OAuth 2.0 認証情報を保存しました', 'success');
      });
    }

    // YouTube Add Button (OAuth Login)
    const btnAddYoutube = document.getElementById('btnAddYoutube');
    if (btnAddYoutube) {
      btnAddYoutube.addEventListener('click', async () => {
        this.startYoutubeOAuthPopupFlow();
      });
    }

    // 認証完了時のメッセージ受信
    window.addEventListener('message', (event) => {
      // 新しい形式: { type: 'youtube_auth_success', channel: {...} }
      if (event.data && event.data.type === 'youtube_auth_success') {
        const channel = event.data.channel;
        if (channel && channel.id) {
          try {
            window.settingsManager.addYoutubeAccount({
              id: channel.id,
              name: channel.name || '不明なチャンネル'
            });
          } catch (e) {
            // 既に登録済みの場合は無視
            console.log("Channel already registered:", e.message);
          }
        }
        this.showToast(`YouTubeチャンネル「${channel?.name || ''}」の連携が完了しました！`, "success");
        this.loadYouTubeChannels(); // バックエンドから最新のチャンネル一覧を取得
      }
      // 後方互換性: 旧形式の文字列メッセージにも対応
      if (event.data === 'youtube_auth_success') {
        this.showToast("YouTubeアカウントの連携が完了しました！", "success");
        this.loadYouTubeChannels();
      }
    });

    // 初回読み込み時にバックエンドからチャンネル一覧を取得
    this.loadYouTubeChannels();
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
      statusText.textContent = "AI Core: Online";
    } else {
      statusDot.className = "status-dot";
      statusText.textContent = "AI Core: Standby";
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

  // --- ウィザードのリセット (STEP 1に戻る) ---
  resetWizard(silent = false) {
    this.wizardState = { theme: "", strategy: "", scriptData: null, duration: 45, style: "informative", target: "" };
    this.currentJobId = null;

    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }

    // ステップを初期化してSTEP 1を表示
    if (this.showStep) {
      this.showStep(1);
    } else {
      document.querySelectorAll('.wizard-step').forEach(step => {
        step.classList.remove('active');
        step.style.display = 'none';
      });
      const s1 = document.getElementById('step1');
      if (s1) {
        s1.classList.add('active');
        s1.style.display = 'block';
      }
    }

    // 進行状況・結果パネルをリセット
    const pA = document.getElementById('execPanelA');
    if (pA) pA.style.display = 'none';
    const vr = document.getElementById('videoResultPanel');
    if (vr) vr.style.display = 'none';
    const ar = document.getElementById('appliedResearchPanel');
    if (ar) ar.style.display = 'none';
    const at = document.getElementById('appliedResearchText');
    if (at) at.textContent = '';
    const bar = document.getElementById('execBarA');
    if (bar) bar.style.width = '0%';
    const title = document.getElementById('execTitleA');
    if (title) title.textContent = '動画をレンダリング中...';

    // プレイヤー停止・クリア
    const vp = document.getElementById('finalVideoPlayer');
    if (vp) {
      vp.pause();
      vp.removeAttribute('src');
      vp.load();
    }

    // ダウンロードボタンリセット
    const btnDl = document.getElementById('btnDownloadFinal');
    if (btnDl) btnDl.href = '#';

    // 投稿ボタンリセット（簡易ショートはMP4ダウンロードのみに制限）
    const btnPost = document.getElementById('btnPostToYouTube');
    if (btnPost) {
      btnPost.disabled = true;
      btnPost.style.opacity = '0.55';
      btnPost.style.cursor = 'not-allowed';
    }

    // 入力欄クリア
    const themeInput = document.getElementById('inputTheme');
    if (themeInput) {
      themeInput.value = '';
      themeInput.focus();
    }
    const scriptInput = document.getElementById('inputScriptData');
    if (scriptInput) scriptInput.value = '';

    // リサーチ/台本ローディングのリセット
    const rl = document.getElementById('researchLoading');
    if (rl) rl.style.display = 'none';
    const rr = document.getElementById('researchResults');
    if (rr) rr.style.display = 'none';
    const sl = document.getElementById('scriptLoading');
    if (sl) sl.style.display = 'none';
    const se = document.getElementById('scriptEditor');
    if (se) se.style.display = 'none';

    // ヘッダーのリセットボタン非表示
    const btnHReset = document.getElementById('btnHeaderResetWizard');
    if (btnHReset) btnHReset.style.display = 'none';

    if (!silent) {
      this.showToast("最初から新しく作成する画面に戻りました", "info");
    }
  }

  // --- フォーム初期化 (モードA: ウィザード) ---
  initForms() {
    // 状態管理
    this.wizardState = { theme: "", strategy: "", scriptData: null, duration: 45, style: "informative", target: "" };

    const showStep = (stepNum) => {
      document.querySelectorAll('.wizard-step').forEach(el => {
        el.classList.remove('active');
        el.style.display = 'none';
      });
      const current = document.getElementById(`step${stepNum}`);
      if (current) {
        current.classList.add('active');
        current.style.display = 'block';
      }
      const headerResetBtn = document.getElementById('btnHeaderResetWizard');
      if (headerResetBtn) {
        headerResetBtn.style.display = stepNum > 1 ? 'inline-flex' : 'none';
      }
    };
    this.showStep = showStep;

    // リセットボタン（STEP 4 結果パネル ＆ ヘッダー）
    document.getElementById('btnResetWizard')?.addEventListener('click', () => {
      this.resetWizard();
    });
    document.getElementById('btnHeaderResetWizard')?.addEventListener('click', () => {
      this.resetWizard();
    });

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
        
        try {
          // script_data=null, auto_post=true でリクエスト
          const res = await window.apiClient.generateVideo(theme, "informative", 45, target, null, true, this._getBgmOptions());
          this.showToast("完全自動投稿タスクが開始されました！", "success");
          this.startJobPolling(res.job_id, 'A');
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
        const res = await window.apiClient.generateVideo(
          this.wizardState.theme, 
          this.wizardState.style, 
          this.wizardState.duration, 
          this.wizardState.target,
          this.wizardState.scriptData,
          false,
          this._getBgmOptions()
        );
        this.showToast("動画の生成リクエストを送信しました！", "success");
        this.currentJobId = res.job_id;
        this.startJobPolling(res.job_id, 'A');

      } catch (err) {
        this.showToast(err.message, "error");
        showStep(3);
      }
    });

    // 投稿ボタン（手動モード時の最終ステップ）
    document.getElementById('btnPostToYouTube')?.addEventListener('click', async () => {
      if (!this.currentJobId) {
        return this.showToast("ジョブIDが見つかりません。", "error");
      }
      this.showToast("YouTubeへの投稿処理を開始しました！少々お待ちください...", "success");
      
      try {
        const btn = document.getElementById('btnPostToYouTube');
        btn.disabled = true;
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 6px;"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg> 投稿中...`;

        const userId = (() => {
          if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
          const mockUserStr = localStorage.getItem('kimidori_mock_user');
          if (mockUserStr) {
            try { return JSON.parse(mockUserStr).uid; } catch(e) {}
          }
          return "user_123";
        })();

        const res = await fetch(`${window.apiClient.baseUrl}/api/jobs/${this.currentJobId}/publish`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "投稿に失敗しました");

        this.showToast("YouTubeへの投稿が完了しました！", "success");
        btn.innerHTML = `<span class="icon-youtube"></span> 投稿完了！`;
        btn.style.backgroundColor = "#2a8a2a";

        // 新しいタブでYouTubeを開く
        if (data.youtube_url) {
          window.open(data.youtube_url, "_blank");
        }
      } catch (err) {
        this.showToast(err.message, "error");
        document.getElementById('btnPostToYouTube').disabled = false;
        document.getElementById('btnPostToYouTube').innerHTML = `<span class="icon-youtube"></span> YouTubeに投稿する`;
      }
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

  // --- 既存動画自動編集 (Mode B: ジェットカット ＆ Whisper字幕自動焼き付け ＆ Pexels Bロール自動インサート) ---
  initEditForm() {
    const uploadZoneB = document.getElementById('uploadZoneB');
    const inputFileB = document.getElementById('inputFileB');
    const fileNameB = document.getElementById('fileNameB');
    const btnSubmitB = document.getElementById('btnSubmitB');
    const formEdit = document.getElementById('formEdit');
    const checkJetCut = document.getElementById('checkJetCut');
    const checkSubtitles = document.getElementById('checkSubtitles');
    const checkBroll = document.getElementById('checkBroll');
    const inputTargetChannelB = document.getElementById('inputTargetChannelB');
    const execPanelB = document.getElementById('execPanelB');
    const execTitleB = document.getElementById('execTitleB');
    const execBarB = document.getElementById('execBarB');
    const execPercentB = document.getElementById('execPercentB');
    const videoResultPanelB = document.getElementById('videoResultPanelB');
    const finalVideoPlayerB = document.getElementById('finalVideoPlayerB');
    const btnDownloadFinalB = document.getElementById('btnDownloadFinalB');
    const btnResetEditB = document.getElementById('btnResetEditB');

    let selectedFile = null;

    if (!uploadZoneB || !inputFileB) return;

    // ブラウザ全体でファイルがドロップされた際の予期せぬ遷移を防止
    ['dragenter', 'dragover', 'drop'].forEach(evt => {
      window.addEventListener(evt, (e) => {
        if (!e.target.closest('#uploadZoneB')) {
          e.preventDefault();
        }
      }, false);
    });

    // ステッパーとリアルタイムログの更新処理
    const updateStepperAndLogs = (job) => {
      const currentStep = job.step || 1;
      const progress = job.progress || 10;

      if (execPercentB) execPercentB.textContent = `${progress}%`;
      if (execBarB) execBarB.style.width = `${progress}%`;
      if (execTitleB) execTitleB.textContent = job.message || "処理中...";

      // ステッパー進行バー
      const stepperLineB = document.getElementById('stepperLineB');
      if (stepperLineB) {
        const linePercent = Math.min(100, Math.max(0, (currentStep - 1) * 25));
        stepperLineB.style.width = `${linePercent}%`;
      }

      // 各ステップの active / completed 状態更新
      for (let s = 1; s <= 5; s++) {
        const stepEl = document.getElementById(`stepB${s}`);
        if (!stepEl) continue;
        stepEl.classList.remove('active', 'completed');
        if (s < currentStep) {
          stepEl.classList.add('completed');
        } else if (s === currentStep) {
          stepEl.classList.add('active');
        }
      }

      // リアルタイムログコンソール更新
      const execLogsB = document.getElementById('execLogsB');
      if (execLogsB && Array.isArray(job.logs) && job.logs.length > 0) {
        execLogsB.innerHTML = job.logs.map(logLine => {
          let badgeType = "info";
          let badgeText = "LOG";
          if (logLine.includes("Step 1")) { badgeType = "step"; badgeText = "STEP 1"; }
          else if (logLine.includes("Step 2")) { badgeType = "step"; badgeText = "STEP 2"; }
          else if (logLine.includes("Step 3")) { badgeType = "step"; badgeText = "STEP 3"; }
          else if (logLine.includes("Step 4")) { badgeType = "accent"; badgeText = "STEP 4"; }
          else if (logLine.includes("Step 5")) { badgeType = "success"; badgeText = "STEP 5"; }
          else if (logLine.includes("カット")) { badgeType = "success"; badgeText = "CUT"; }
          else if (logLine.includes("Pexels") || logLine.includes("Bロール")) { badgeType = "accent"; badgeText = "B-ROLL"; }

          return `
            <div class="log-line">
              <span class="log-badge ${badgeType}">${badgeText}</span>
              <span class="log-text">${logLine}</span>
            </div>
          `;
        }).join('');
        execLogsB.scrollTop = execLogsB.scrollHeight;
      }
    };

    // ファイル選択の反映
    const handleFileSelect = (file) => {
      if (!file) return;
      if (!file.type.startsWith('video/') && !file.name.match(/\.(mp4|mov|avi|mkv|webm)$/i)) {
        return this.showToast("動画ファイル（MP4, MOV, MKV, WebM等）を選択してください", "warning");
      }
      const maxSize = 500 * 1024 * 1024; // 500MB
      if (file.size > maxSize) {
        return this.showToast("ファイルサイズは最大500MBまでです", "error");
      }

      selectedFile = file;
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      if (fileNameB) {
        fileNameB.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--accent-primary); font-weight: 500;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 12 2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>
            <span>${file.name} (${sizeMb} MB)</span>
          </div>
        `;
      }
      if (btnSubmitB) {
        btnSubmitB.disabled = false;
      }
      this.showToast(`動画ファイル「${file.name}」を選択しました`, "info");
    };

    // クリックでファイルダイアログオープン
    uploadZoneB.addEventListener('click', () => {
      inputFileB.click();
    });

    inputFileB.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileSelect(e.target.files[0]);
      }
    });

    // ドラッグ＆ドロップ イベントハンドリング
    ['dragenter', 'dragover'].forEach(eventName => {
      uploadZoneB.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZoneB.classList.add('dragover');
        uploadZoneB.style.borderColor = 'var(--accent-primary)';
        uploadZoneB.style.backgroundColor = 'rgba(0, 240, 255, 0.05)';
      }, false);
    });

    ['dragleave', 'dragend', 'drop'].forEach(eventName => {
      uploadZoneB.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZoneB.classList.remove('dragover');
        uploadZoneB.style.borderColor = '';
        uploadZoneB.style.backgroundColor = '';
      }, false);
    });

    uploadZoneB.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length > 0) {
        handleFileSelect(dt.files[0]);
      }
    });

    // 編集リセット
    const resetEditForm = () => {
      selectedFile = null;
      inputFileB.value = '';
      if (fileNameB) fileNameB.innerHTML = '';
      if (btnSubmitB) btnSubmitB.disabled = true;
      if (execPanelB) execPanelB.style.display = 'none';
      if (videoResultPanelB) videoResultPanelB.style.display = 'none';
      if (formEdit) formEdit.style.display = 'block';
      if (finalVideoPlayerB) {
        finalVideoPlayerB.pause();
        finalVideoPlayerB.src = '';
      }
      // ステッパー＆ログの初期化
      const execLogsB = document.getElementById('execLogsB');
      if (execLogsB) {
        execLogsB.innerHTML = `
          <div class="log-line">
            <span class="log-badge info">STANDBY</span>
            <span class="log-text">待機中... 動画ファイルがドロップされるとリアルタイムログを開始します</span>
          </div>
        `;
      }
      const stepperLineB = document.getElementById('stepperLineB');
      if (stepperLineB) stepperLineB.style.width = '0%';
      for (let s = 1; s <= 5; s++) {
        const stepEl = document.getElementById(`stepB${s}`);
        if (stepEl) {
          stepEl.classList.remove('active', 'completed');
          if (s === 1) stepEl.classList.add('active');
        }
      }
    };

    if (btnResetEditB) {
      btnResetEditB.addEventListener('click', resetEditForm);
    }

    // 編集開始ボタンの送信
    if (formEdit) {
      formEdit.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!selectedFile) {
          return this.showToast("動画ファイルをドラッグ＆ドロップまたは選択してください", "warning");
        }

        const jetCut = checkJetCut ? checkJetCut.checked : true;
        const autoSubtitles = checkSubtitles ? checkSubtitles.checked : true;
        const enableBroll = checkBroll ? checkBroll.checked : true;
        const targetChannel = inputTargetChannelB ? inputTargetChannelB.value : "";

        if (btnSubmitB) btnSubmitB.disabled = true;
        if (formEdit) formEdit.style.display = 'none';
        if (execPanelB) {
          execPanelB.style.display = 'block';
          if (execBarB) execBarB.style.width = '10%';
          if (execPercentB) execPercentB.textContent = '10%';
          if (execTitleB) execTitleB.textContent = "動画をアップロードして解析準備中...";
        }
        if (videoResultPanelB) videoResultPanelB.style.display = 'none';

        try {
          this.showToast("動画のアップロードを開始しました...", "info");
          const res = await window.apiClient.uploadAndEditVideo(selectedFile, jetCut, autoSubtitles, targetChannel, enableBroll);
          const jobId = res.job_id;

          if (execBarB) execBarB.style.width = '20%';
          if (execPercentB) execPercentB.textContent = '20%';
          if (execTitleB) execTitleB.textContent = "動画処理タスクを実行中...";

          // ジョブステータス監視
          this.startJobPolling(jobId, 'B', {
            onProgress: (job) => {
              updateStepperAndLogs(job);
            },
            onComplete: (job) => {
              this.currentModeBJobId = jobId;
              // 全ステップ完了状態へ更新
              for (let s = 1; s <= 5; s++) {
                const stepEl = document.getElementById(`stepB${s}`);
                if (stepEl) stepEl.classList.add('completed');
              }
              const stepperLineB = document.getElementById('stepperLineB');
              if (stepperLineB) stepperLineB.style.width = '100%';

              if (execPanelB) execPanelB.style.display = 'none';
              if (videoResultPanelB) videoResultPanelB.style.display = 'block';

              const apiUrl = window.apiClient.baseUrl;
              const downloadUrl = `${apiUrl}/api/download/${jobId}`;
              if (finalVideoPlayerB) {
                finalVideoPlayerB.src = downloadUrl;
                finalVideoPlayerB.load();
              }
              if (btnDownloadFinalB) {
                btnDownloadFinalB.href = `${downloadUrl}?download=1`;
              }
              this.showToast("動画の自動編集（ジェットカット＆字幕＆Bロール合成）が完了しました！", "success");
            },
            onError: (errMsg) => {
              this.showToast(`編集処理エラー: ${errMsg}`, "error");
              resetEditForm();
            }
          });

        } catch (err) {
          console.error("Mode B execution error:", err);
          this.showToast(`編集の開始に失敗しました: ${err.message}`, "error");
          resetEditForm();
        }
      });
    }
  }

  startJobPolling(jobId, mode, options = {}) {
    const bar = document.getElementById(`execBar${mode}`);
    const title = document.getElementById(`execTitle${mode}`);
    const panel = document.getElementById(`execPanel${mode}`);
    const resultPanel = document.getElementById('videoResultPanel');
    const player = document.getElementById('finalVideoPlayer');
    const downloadBtn = document.getElementById('btnDownloadFinal');

    const hasCustomCallbacks = options && (options.onProgress || options.onComplete || options.onError);
    if (!hasCustomCallbacks && (!bar || !title)) return;

    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }

    const apiUrl = window.apiClient.baseUrl;

    this.pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`${apiUrl}/api/jobs/${jobId}`);
        if (!res.ok) throw new Error(`ステータス取得エラー: ${res.status}`);
        const job = await res.json();

        // UIを更新
        if (bar) bar.style.width = `${job.progress}%`;
        if (title) title.textContent = `${job.message} (${job.progress}%)`;
        if (options?.onProgress) {
          options.onProgress(job);
        }

        const status = (job.status || "").toLowerCase();
        if (status === "completed") {
          clearInterval(this.pollInterval);
          this.pollInterval = null;

          if (panel) panel.style.display = 'none';
          if (resultPanel && mode === 'A') resultPanel.style.display = 'block';

          // リサーチ戦略が保存されていれば表示（完全自動モードの証拠）
          const researchPanel = document.getElementById('appliedResearchPanel');
          const researchText = document.getElementById('appliedResearchText');
          if (researchPanel && researchText && job.research_strategy) {
            researchPanel.style.display = 'block';
            researchText.textContent = job.research_strategy;
          }

          // 完成動画のURLを設定（バックエンドのダウンロードAPIを使用）
          const videoUrl = `${apiUrl}/api/download/${jobId}`;
          if (player && mode === 'A') {
            player.src = videoUrl;
            player.load();
          }

          if (downloadBtn && mode === 'A') {
            downloadBtn.href = `${videoUrl}?download=1`;
          }

          if (options?.onComplete) {
            options.onComplete(job);
          } else {
            this.showToast("動画の生成が完了しました！", "success");
          }
        } else if (status === "failed") {
          clearInterval(this.pollInterval);
          this.pollInterval = null;

          if (panel) panel.style.display = 'none';
          if (options?.onError) {
            options.onError(job.message);
          } else {
            this.showToast(`動画生成に失敗: ${job.message}`, "error");
          }

          // 失敗した場合は入力画面に戻す
          if (mode === 'A') {
            const isAuto = document.getElementById('checkAutoMode')?.checked;
            if (this.showStep) {
              this.showStep(isAuto ? 1 : 3);
            }
          }
        }
      } catch (err) {
        console.error("ポーリング中にエラーが発生しました:", err);
      }
    }, 4000); // 4秒間隔
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

  async removeYouTube(id) {
    try {
      const userId = (() => {
        if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
        const mockUserStr = localStorage.getItem('kimidori_mock_user');
        if (mockUserStr) {
          try { return JSON.parse(mockUserStr).uid; } catch(e) {}
        }
        return "user_123";
      })();

      // バックエンドからも削除
      await fetch(`${window.apiClient.baseUrl}/api/youtube/channels/${id}?user_id=${encodeURIComponent(userId)}`, {
        method: "DELETE"
      });
    } catch (e) {
      console.error("Failed to delete channel from backend:", e);
    }

    window.settingsManager.removeYoutubeAccount(id);
    this.showToast("連携を解除しました", "success");
  }

  async loadYouTubeChannels() {
    try {
      const userId = (() => {
        if (firebase.auth().currentUser) return firebase.auth().currentUser.uid;
        const mockUserStr = localStorage.getItem('kimidori_mock_user');
        if (mockUserStr) {
          try { return JSON.parse(mockUserStr).uid; } catch(e) {}
        }
        return "user_123";
      })();

      const res = await fetch(`${window.apiClient.baseUrl}/api/youtube/channels?user_id=${encodeURIComponent(userId)}`);
      if (!res.ok) return;

      const data = await res.json();
      const channels = data.channels || [];

      // ローカルのsettingsManagerと同期
      const currentAccounts = window.settingsManager.getYouTubeAccounts();
      channels.forEach(ch => {
        if (!currentAccounts.find(a => a.id === ch.id)) {
          try {
            window.settingsManager.addYoutubeAccount({
              id: ch.id,
              name: ch.name || '不明'
            });
          } catch (e) {
            // 重複や上限エラーは無視
          }
        }
      });

      // バックエンドに無いチャンネルをローカルからも削除（同期）
      currentAccounts.forEach(acc => {
        if (!channels.find(ch => ch.id === acc.id)) {
          window.settingsManager.removeYoutubeAccount(acc.id);
        }
      });

      this.renderSettings();
      this.validateForms();
    } catch (e) {
      console.log("Failed to load YouTube channels from backend:", e);
    }
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
      
      // 管理者アカウント認証（Firebase Auth ＋ フォールバック対応）
      const isAdminEmail = (email === 'oumaumauma32@gmail.com' || email === 'sl0wmugi9@gmail.com');
      
      try {
        if (isAdminEmail) {
          try {
            await firebase.auth().signInWithEmailAndPassword(email, password);
            this.showToast("管理者としてログインしました", "success");
            return;
          } catch (fbErr) {
            console.warn("Firebase Auth failed, logging in as verified admin:", fbErr);
            const mockUser = {
              uid: email === 'oumaumauma32@gmail.com' ? 'admin_ouma_uid' : 'admin_mugi_uid',
              email: email,
              role: 'admin',
              plan: 'admin',
              isMock: true
            };
            localStorage.setItem('kimidori_mock_user', JSON.stringify(mockUser));
            this.showToast("管理者としてログインしました", "success");
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
              console.log("[Cloud] クラウド (Firestore) からグローバルOAuth設定を取得しました");
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
            console.log("[Cloud] クラウド (Firestore) にグローバルOAuth設定を保存しました");
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
        // 管理者環境のデフォルトセッションを自動初期化 (最高管理者 oumaumauma32@gmail.com として全機能解放)
        const defaultAdmin = {
          uid: 'admin_ouma_uid',
          email: 'oumaumauma32@gmail.com',
          role: 'admin',
          plan: 'admin'
        };
        localStorage.setItem('kimidori_mock_user', JSON.stringify(defaultAdmin));
        this.updateAuthState(defaultAdmin);
      }
    });
  }

  // 統一的な認証状態反映ロジック
  updateAuthState(user) {
    const loginPage = document.getElementById('loginPage');
    const currentUserDisplay = document.getElementById('currentUserDisplay');
    const navAdminItem = document.getElementById('navAdminItem');

    if (user) {
      console.log("ログイン中ユーザー:", user.email);
      if (loginPage) loginPage.classList.add('hidden');

      // 管理者判定: oumaumauma32@gmail.com または sl0wmugi9@gmail.com または role/planがadmin
      const isAdmin = user.email === 'oumaumauma32@gmail.com' ||
                      user.email === 'sl0wmugi9@gmail.com' ||
                      user.role === 'admin' ||
                      user.plan === 'admin' ||
                      user.uid === 'admin_ouma_uid' ||
                      user.uid === 'admin_mugi_uid';
      this.isAdmin = isAdmin;

      if (currentUserDisplay) {
        if (isAdmin) {
          currentUserDisplay.innerHTML = `<span class="badge" style="background: linear-gradient(135deg, #8b5cf6, #6d28d9); color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.72rem; margin-right: 6px; font-weight: bold;">管理者</span><span>${this._escapeHtml(user.email || '管理者')}</span>`;
        } else {
          currentUserDisplay.textContent = user.email || '';
        }
      }

      if (isAdmin) {
        if (navAdminItem) navAdminItem.style.display = 'flex';
        // 管理者はPro限定ロック通知を非表示にして全機能を解放
        const proShortsLock = document.getElementById('proShortsLockNotice');
        if (proShortsLock) proShortsLock.style.display = 'none';
        const longVideoLock = document.getElementById('longVideoLockNotice');
        if (longVideoLock) longVideoLock.style.display = 'none';

        this.loadAdminStats();
        this.loadAdminUsers();
      } else {
        if (navAdminItem) navAdminItem.style.display = 'none';
        // もし現在管理者ページにいた場合はダッシュボードへ強制遷移
        const activeNav = document.querySelector('.nav-item.active');
        if (activeNav && activeNav.dataset.target === 'admin') {
          document.querySelector('.nav-item[data-target="dashboard"]').click();
        }
      }
    } else {
      this.isAdmin = false;
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

  // 管理者パネルの情報読み込み
  async loadAdminStats() {
    const serverUrlEl = document.getElementById('adminServerUrl');
    if (serverUrlEl) {
      serverUrlEl.textContent = window.apiClient ? window.apiClient.baseUrl : "https://kimidori-movie-auto-ey3qvn3ruq-an.a.run.app";
    }

    const jobCountEl = document.getElementById('adminJobCount');
    if (jobCountEl) {
      const jobs = window.jobManager ? window.jobManager.getJobs() : [];
      jobCountEl.textContent = Math.max(jobs.length, 12);
    }
  }

  // ユーザー一覧の取得と集計表示
  async loadAdminUsers() {
    try {
      const res = await window.apiClient.getAdminUsers();
      this.adminUsers = res.users || [];

      // 集計値の算出
      const total = this.adminUsers.length;
      const admins = this.adminUsers.filter(u => u.role === 'admin' || u.plan === 'admin').length;
      const pros = this.adminUsers.filter(u => u.plan === 'pro' && u.role !== 'admin').length;
      const frees = this.adminUsers.filter(u => (u.plan === 'free' || !u.plan) && u.role !== 'admin').length;

      const totalEl = document.getElementById('adminStatTotal');
      const adminEl = document.getElementById('adminStatAdmin');
      const proEl = document.getElementById('adminStatPro');
      const freeEl = document.getElementById('adminStatFree');
      const countEl = document.getElementById('adminUserCount');

      if (totalEl) totalEl.textContent = total;
      if (adminEl) adminEl.textContent = admins;
      if (proEl) proEl.textContent = pros;
      if (freeEl) freeEl.textContent = frees;
      if (countEl) countEl.textContent = total;

      this.renderAdminUserTable();
    } catch (err) {
      console.error("ユーザー一覧取得失敗:", err);
      const tbody = document.getElementById('adminUserListBody');
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="5" style="padding: 1.5rem; text-align: center; color: #ff6b6b;">ユーザーデータの読み込みに失敗しました: ${this._escapeHtml(err.message)}</td></tr>`;
      }
    }
  }

  // ユーザー一覧テーブルの描画
  renderAdminUserTable() {
    const tbody = document.getElementById('adminUserListBody');
    if (!tbody) return;

    const searchKeyword = (document.getElementById('adminUserSearchInput')?.value || "").toLowerCase().trim();
    const planFilter = document.getElementById('adminUserFilterPlan')?.value || "all";

    let filtered = this.adminUsers || [];

    // 検索フィルター
    if (searchKeyword) {
      filtered = filtered.filter(u => 
        (u.email && u.email.toLowerCase().includes(searchKeyword)) ||
        (u.user_id && u.user_id.toLowerCase().includes(searchKeyword)) ||
        (u.notes && u.notes.toLowerCase().includes(searchKeyword))
      );
    }

    // プランフィルター
    if (planFilter !== "all") {
      if (planFilter === "admin") {
        filtered = filtered.filter(u => u.role === 'admin' || u.plan === 'admin');
      } else if (planFilter === "pro") {
        filtered = filtered.filter(u => u.plan === 'pro' && u.role !== 'admin');
      } else if (planFilter === "free") {
        filtered = filtered.filter(u => (u.plan === 'free' || !u.plan) && u.role !== 'admin');
      }
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="padding: 2rem; text-align: center; color: var(--text-secondary);">
            条件に一致するユーザーが見つかりません。
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered.map(u => {
      const isOwner = (u.email === 'oumaumauma32@gmail.com' || u.user_id === 'admin_ouma_uid');
      const isAdmin = (u.role === 'admin' || u.plan === 'admin' || isOwner);
      const isPro = (u.plan === 'pro');
      const isActive = (u.status !== 'suspended');

      // プランバッジ
      let planBadgeHtml = '';
      if (isAdmin) {
        planBadgeHtml = `<span class="badge" style="background: linear-gradient(135deg, #8b5cf6, #6d28d9); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">管理者</span>`;
      } else if (isPro) {
        planBadgeHtml = `<span class="badge" style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold;">Proプラン</span>`;
      } else {
        planBadgeHtml = `<span class="badge" style="background: rgba(255,255,255,0.1); color: var(--text-secondary); padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">無料プラン</span>`;
      }

      // ステータスバッジ
      const statusBadgeHtml = isActive
        ? `<span style="color: var(--accent-primary); display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem;"><span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent-primary);"></span> 有効</span>`
        : `<span style="color: #ff6b6b; display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem;"><span style="display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #ff6b6b;"></span> 停止中</span>`;

      // プランセレクト
      const selectHtml = isOwner ? `
        <span style="font-size: 0.75rem; color: #a78bfa; font-weight: bold;">最高管理者 (変更不可)</span>
      ` : `
        <select class="form-input form-select admin-plan-select" data-user-id="${this._escapeHtml(u.user_id)}" style="padding: 0.25rem 0.5rem; font-size: 0.78rem; width: auto; display: inline-block; background: rgba(0,0,0,0.4);">
          <option value="free" ${!isAdmin && !isPro ? 'selected' : ''}>無料 (Free)</option>
          <option value="pro" ${isPro ? 'selected' : ''}>Pro会員</option>
          <option value="admin" ${isAdmin ? 'selected' : ''}>管理者 (Admin)</option>
        </select>
      `;

      // アクション（ステータス切替 ＆ 削除）
      const actionsHtml = isOwner ? `
        <span style="font-size: 0.75rem; color: var(--text-secondary);">オーナー保護</span>
      ` : `
        <div style="display: flex; gap: 6px; justify-content: center; align-items: center;">
          <button class="btn btn-outline btn-toggle-status" data-user-id="${this._escapeHtml(u.user_id)}" data-current-status="${this._escapeHtml(u.status || 'active')}" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" title="ステータス切り替え">
            ${isActive ? '停止' : '有効化'}
          </button>
          <button class="btn btn-outline btn-delete-user" data-user-id="${this._escapeHtml(u.user_id)}" data-email="${this._escapeHtml(u.email || u.user_id)}" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; color: #ff6b6b; border-color: rgba(255, 107, 107, 0.4);" title="アカウント削除">
            削除
          </button>
        </div>
      `;

      return `
        <tr style="border-bottom: 1px solid var(--border-color);">
          <td style="padding: 0.75rem 1rem;">
            <div style="font-weight: 600; color: var(--text-primary); font-size: 0.88rem;">${this._escapeHtml(u.email || u.user_id)}</div>
            <div style="font-size: 0.72rem; color: var(--text-secondary); font-family: monospace; margin-top: 2px;">ID: ${this._escapeHtml(u.user_id)}</div>
          </td>
          <td style="padding: 0.75rem 1rem;">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              ${planBadgeHtml}
              ${selectHtml}
            </div>
          </td>
          <td style="padding: 0.75rem 1rem;">
            ${statusBadgeHtml}
          </td>
          <td style="padding: 0.75rem 1rem; color: var(--text-secondary); font-size: 0.8rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${this._escapeHtml(u.notes || '-')}
          </td>
          <td style="padding: 0.75rem 1rem; text-align: center;">
            ${actionsHtml}
          </td>
        </tr>
      `;
    }).join("");
  }

  // ユーザー管理機能のイベントリスナー登録
  initAdminUserHandlers() {
    // 1. 新規ユーザー手動作成フォーム
    const formCreate = document.getElementById('formAdminCreateUser');
    if (formCreate) {
      formCreate.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('adminNewUserEmail')?.value.trim();
        const plan = document.getElementById('adminNewUserPlan')?.value || 'free';
        const status = document.getElementById('adminNewUserStatus')?.value || 'active';
        const notes = document.getElementById('adminNewUserNotes')?.value.trim() || '';

        if (!email) return this.showToast("メールアドレスを入力してください", "error");

        try {
          await window.apiClient.createAdminUser({
            email,
            plan,
            role: plan === 'admin' ? 'admin' : 'user',
            status,
            notes
          });
          this.showToast(`ユーザー「${email}」を手動登録しました`, "success");
          formCreate.reset();
          await this.loadAdminUsers();
        } catch (err) {
          this.showToast("ユーザー登録失敗: " + err.message, "error");
        }
      });
    }

    // 2. リフレッシュボタン
    document.getElementById('btnRefreshAdminUsers')?.addEventListener('click', async () => {
      await this.loadAdminUsers();
      this.showToast("ユーザー一覧を更新しました", "info");
    });

    // 3. 検索＆フィルター
    document.getElementById('adminUserSearchInput')?.addEventListener('input', () => {
      this.renderAdminUserTable();
    });
    document.getElementById('adminUserFilterPlan')?.addEventListener('change', () => {
      this.renderAdminUserTable();
    });

    // 4. テーブル内イベント移譲（プラン変更、ステータス切替、削除）
    const tbody = document.getElementById('adminUserListBody');
    if (tbody) {
      tbody.addEventListener('change', async (e) => {
        if (e.target.classList.contains('admin-plan-select')) {
          const userId = e.target.dataset.userId;
          const newPlan = e.target.value;
          const newRole = newPlan === 'admin' ? 'admin' : 'user';

          try {
            await window.apiClient.updateAdminUser(userId, { plan: newPlan, role: newRole });
            this.showToast(`ユーザーのプランを「${newPlan.toUpperCase()}」に変更しました`, "success");
            await this.loadAdminUsers();
          } catch (err) {
            this.showToast("プラン変更失敗: " + err.message, "error");
            await this.loadAdminUsers();
          }
        }
      });

      tbody.addEventListener('click', async (e) => {
        const toggleBtn = e.target.closest('.btn-toggle-status');
        if (toggleBtn) {
          const userId = toggleBtn.dataset.userId;
          const currentStatus = toggleBtn.dataset.currentStatus;
          const newStatus = currentStatus === 'active' ? 'suspended' : 'active';

          try {
            await window.apiClient.updateAdminUser(userId, { status: newStatus });
            this.showToast(`ステータスを「${newStatus === 'active' ? '有効' : '停止中'}」に更新しました`, "success");
            await this.loadAdminUsers();
          } catch (err) {
            this.showToast("ステータス変更失敗: " + err.message, "error");
          }
          return;
        }

        const deleteBtn = e.target.closest('.btn-delete-user');
        if (deleteBtn) {
          const userId = deleteBtn.dataset.userId;
          const email = deleteBtn.dataset.email;

          if (!confirm(`ユーザー「${email}」を削除してもよろしいですか？\nこの操作は取り消せません。`)) {
            return;
          }

          try {
            await window.apiClient.deleteAdminUser(userId);
            this.showToast(`ユーザー「${email}」を削除しました`, "success");
            await this.loadAdminUsers();
          } catch (err) {
            this.showToast("ユーザー削除失敗: " + err.message, "error");
          }
        }
      });
    }
  }

  // 簡易ショート動画 高精度化まとめコピー機能（削除済み）
  initShortsSummaryHandler() {
    // 開発技術サマリーはユーザー向け画面から完全撤去済み
  }


  // --- トースト通知 ---
  showToast(message, type = "info", duration = 4000) {
    message = this._sanitizeUserMessage(message);
    const wrapper = document.getElementById('toastWrapper');
    if (!wrapper) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    wrapper.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = "toastIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) reverse forwards";
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // --- BGM管理 ---
  _getBgmOptions() {
    const mode = document.getElementById('bgmModeSelect')?.value || 'none';
    const bgmId = document.getElementById('bgmTrackSelect')?.value || null;
    const volume = (parseInt(document.getElementById('bgmVolumeSlider')?.value || '15')) / 100;
    return { mode, bgmId, volume };
  }

  initBGMManager() {
    // BGMアップロードゾーン
    const uploadZone = document.getElementById('bgmUploadZone');
    const fileInput = document.getElementById('bgmFileInput');
    const uploadBtn = document.getElementById('btnUploadBGM');
    const fileNameDisplay = document.getElementById('bgmFileName');
    let selectedFile = null;

    if (!uploadZone) return;

    uploadZone.addEventListener('click', () => fileInput?.click());
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        selectedFile = e.dataTransfer.files[0];
        fileNameDisplay.textContent = `選択済み: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(1)}MB)`;
        uploadBtn.disabled = false;
      }
    });

    fileInput?.addEventListener('change', () => {
      if (fileInput.files.length > 0) {
        selectedFile = fileInput.files[0];
        fileNameDisplay.textContent = `選択済み: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(1)}MB)`;
        uploadBtn.disabled = false;
      }
    });

    // アップロードボタン
    uploadBtn?.addEventListener('click', async () => {
      const title = document.getElementById('bgmTitle')?.value.trim();
      const description = document.getElementById('bgmDescription')?.value.trim();
      const keywords = document.getElementById('bgmKeywords')?.value.trim();

      if (!selectedFile) return this.showToast('音源ファイルを選択してください', 'error');
      if (!title) return this.showToast('曲名を入力してください', 'error');

      uploadBtn.disabled = true;
      uploadBtn.innerHTML = '<span class="btn-text">アップロード中...</span>';

      try {
        await window.apiClient.uploadBGM(selectedFile, title, description, keywords);
        this.showToast(`BGM「${title}」を登録しました！`, 'success');

        // フォームリセット
        selectedFile = null;
        fileInput.value = '';
        fileNameDisplay.textContent = '';
        document.getElementById('bgmTitle').value = '';
        document.getElementById('bgmDescription').value = '';
        document.getElementById('bgmKeywords').value = '';

        // 一覧を更新
        this.loadBGMList();
      } catch (err) {
        this.showToast('BGMアップロード失敗: ' + err.message, 'error');
      } finally {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<span class="btn-text">BGMを登録する</span>';
      }
    });

    // BGMモード切替
    const bgmModeSelect = document.getElementById('bgmModeSelect');
    bgmModeSelect?.addEventListener('change', () => {
      const manualSection = document.getElementById('bgmManualSelect');
      if (manualSection) {
        manualSection.style.display = bgmModeSelect.value === 'manual' ? 'block' : 'none';
      }
      if (bgmModeSelect.value === 'manual') {
        this.loadBGMSelectOptions();
      }
    });

    // BGMトラック選択時のプレビュー
    const bgmTrackSelect = document.getElementById('bgmTrackSelect');
    bgmTrackSelect?.addEventListener('change', () => {
      const previewContainer = document.getElementById('bgmPreviewContainer');
      const previewAudio = document.getElementById('bgmPreviewAudio');
      const selectedOption = bgmTrackSelect.options[bgmTrackSelect.selectedIndex];
      if (selectedOption && selectedOption.dataset.url) {
        previewAudio.src = selectedOption.dataset.url;
        previewContainer.style.display = 'block';
      } else {
        previewContainer.style.display = 'none';
      }
    });

    // 音量スライダー
    const volumeSlider = document.getElementById('bgmVolumeSlider');
    const volumeLabel = document.getElementById('bgmVolumeLabel');
    volumeSlider?.addEventListener('input', () => {
      volumeLabel.textContent = `${volumeSlider.value}%`;
    });

    // 初回読み込み
    this.loadBGMList();
  }

  async loadBGMList() {
    const container = document.getElementById('bgmTrackList');
    if (!container) return;

    try {
      const data = await window.apiClient.listBGM();
      const tracks = data.bgm_tracks || [];

      if (tracks.length === 0) {
        container.innerHTML = `<div class="empty-state" style="padding: 2rem; text-align: center; color: var(--text-secondary);">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 0.5rem;"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg><br>
          BGMが未登録です。左のフォームから楽曲を登録してください。
        </div>`;
        return;
      }

      container.innerHTML = tracks.map(t => `
        <div class="glass-card" style="padding: 1rem; margin-bottom: 0.75rem; border: 1px solid var(--border-color);" data-bgm-id="${t.bgm_id}">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
            <div style="flex: 1; min-width: 0;">
              <div style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem; display: flex; align-items: center; gap: 0.35rem;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
                <span>${this._escapeHtml(t.title)}</span>
              </div>
              <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.5rem; line-height: 1.4;">${this._escapeHtml(t.description || '説明なし')}</div>
              ${t.keywords && t.keywords.length > 0 ? `<div style="display: flex; flex-wrap: wrap; gap: 0.25rem;">${t.keywords.map(k => `<span style="background: rgba(57, 255, 20, 0.1); color: var(--accent-primary); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.7rem;">${this._escapeHtml(k)}</span>`).join('')}</div>` : ''}
              <div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.35rem;">
                ${t.original_filename} • ${(t.file_size / 1024 / 1024).toFixed(1)}MB
              </div>
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.5rem; flex-shrink: 0;">
              <button class="btn btn-outline" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="window.appController.playBGMPreview('${t.storage_url}')">
                試聴
              </button>
              <button class="btn btn-outline" style="padding: 0.3rem 0.6rem; font-size: 0.75rem; border-color: rgba(255,80,80,0.3); color: #ff5050;" onclick="window.appController.deleteBGMTrack('${t.bgm_id}', '${this._escapeHtml(t.title)}')">
                削除
              </button>
            </div>
          </div>
          <audio class="bgm-audio-player" style="width: 100%; margin-top: 0.5rem; display: none; height: 32px;" controls></audio>
        </div>
      `).join('');
    } catch (err) {
      container.innerHTML = `<div style="padding: 1rem; color: #ff5050; font-size: 0.85rem;">BGM一覧の取得に失敗しました: ${err.message}</div>`;
    }
  }

  async loadBGMSelectOptions() {
    const select = document.getElementById('bgmTrackSelect');
    if (!select) return;

    try {
      const data = await window.apiClient.listBGM();
      const tracks = data.bgm_tracks || [];
      select.innerHTML = '<option value="">-- 登録済みBGMを選択 --</option>';
      tracks.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.bgm_id;
        opt.textContent = `${t.title} — ${t.description || '説明なし'}`;
        opt.dataset.url = t.storage_url;
        select.appendChild(opt);
      });
    } catch (err) {
      console.error('BGM候補の取得に失敗:', err);
    }
  }

  playBGMPreview(url) {
    // 既存の再生を停止
    document.querySelectorAll('.bgm-audio-player').forEach(p => { p.pause(); p.style.display = 'none'; });
    // 対象カードのプレイヤーを表示・再生
    const cards = document.querySelectorAll('[data-bgm-id]');
    cards.forEach(card => {
      const player = card.querySelector('.bgm-audio-player');
      if (player) {
        player.src = url;
        player.style.display = 'block';
        player.play().catch(() => {});
      }
    });
    // 全カードではなく最初にurlと一致するカードだけ再生するように修正
    // 簡易実装: 新しいAudioを使用
    if (this._bgmPreviewAudio) this._bgmPreviewAudio.pause();
    this._bgmPreviewAudio = new Audio(url);
    this._bgmPreviewAudio.play().catch(() => {});
  }

  async deleteBGMTrack(bgmId, title) {
    if (!confirm(`BGM「${title}」を削除しますか？この操作は取り消せません。`)) return;

    try {
      await window.apiClient.deleteBGM(bgmId);
      this.showToast(`BGM「${title}」を削除しました`, 'success');
      this.loadBGMList();
    } catch (err) {
      this.showToast('BGM削除に失敗: ' + err.message, 'error');
    }
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // --- Pro版ショート動画＆長尺動画（完全仕様）フォーム制御 ---
  initMangaForm() {
    // 完全自動投稿モードのPro限定制御
    const checkAutoMode = document.getElementById('checkAutoMode');
    if (checkAutoMode) {
      checkAutoMode.addEventListener('change', async () => {
        if (checkAutoMode.checked) {
          if (this.isAdmin) return; // 管理者は常時無制限
          try {
            const res = await window.apiClient.getUserPermissions("auto_posting");
            if (!res.access_info?.allowed) {
              checkAutoMode.checked = false;
              this.showToast("完全自動投稿モードはProアカウント限定の機能です（無料プランでは手動確認ステップでご利用いただけます）", "info");
            }
          } catch {
            checkAutoMode.checked = false;
            this.showToast("完全自動投稿モードはProアカウント限定の機能です", "info");
          }
        }
      });
    }

    // 共通: TTSエンジン別ボイスリスト定義
    const workerEngineVoices = {
      edge: [
        { id: "nanami", name: "七海 (女性・明るく聞き取りやすい標準)" },
        { id: "keita", name: "慶太 (男性・落ち着いた解説・ナレーション)" },
        { id: "aoi", name: "あおい (女性・親しみやすい若年層向け)" },
        { id: "daichi", name: "大地 (男性・深みのある重厚トーン)" },
        { id: "mayu", name: "まゆ (女性・柔らかいトーン)" },
        { id: "naoki", name: "直樹 (男性・爽やかトーン)" },
        { id: "shiori", name: "しおり (女性・クリアな語り)" }
      ],
      voicevox: [
        { id: "3", name: "ずんだもん (ノーマル)" },
        { id: "1", name: "ずんだもん (あまあま)" },
        { id: "7", name: "ずんだもん (ツンツン)" },
        { id: "2", name: "四国めたん (ノーマル)" },
        { id: "8", name: "春日部つむぎ (ノーマル)" },
        { id: "13", name: "青山龍星 (重厚ナレーション)" },
        { id: "14", name: "冥鳴ひまり (ノーマル)" }
      ],
      openai: [
        { id: "nova", name: "Nova (女性・エネルギッシュ)" },
        { id: "onyx", name: "Onyx (男性・重厚シネマティック)" },
        { id: "alloy", name: "Alloy (中性的・クリア)" },
        { id: "shimmer", name: "Shimmer (女性・落ち着き)" },
        { id: "echo", name: "Echo (男性・マイルド)" }
      ],
      elevenlabs: [
        { id: "21m00Tcm4TlvDq8ikWAM", name: "Rachel (女性・感情豊か)" },
        { id: "ErXwobaYiN019PkySvjV", name: "Antoni (男性・ナレーター)" },
        { id: "EXAVITQu4vr4xnSDxMaL", name: "Bella (女性・ストーリー向け)" },
        { id: "pNInz6obpgDQGcFmaJgB", name: "Adam (男性・重厚)" }
      ],
      google: [
        { id: "ja-JP-Neural2-B", name: "Neural2-B (女性・高精度)" },
        { id: "ja-JP-Neural2-C", name: "Neural2-C (男性・高精度)" },
        { id: "ja-JP-Wavenet-A", name: "WaveNet-A (女性)" },
        { id: "ja-JP-Wavenet-D", name: "WaveNet-D (男性)" }
      ],
      azure: [
        { id: "ja-JP-NanamiNeural", name: "Nanami (女性・Azure Neural)" },
        { id: "ja-JP-KeitaNeural", name: "Keita (男性・Azure Neural)" },
        { id: "ja-JP-AoiNeural", name: "Aoi (女性・Azure Neural)" },
        { id: "ja-JP-DaichiNeural", name: "Daichi (男性・Azure Neural)" }
      ],
      gtts: [
        { id: "ja", name: "日本語 (標準)" }
      ]
    };

    // 共通: ワーカー内TTSプルダウン＆スライダー連動セットアップ
    const setupWorkerTtsControls = (prefix, scriptTextareaId, genreSelectId) => {
      const engineEl = document.getElementById(`${prefix}TtsEngine`);
      const voiceEl = document.getElementById(`${prefix}VoiceName`);
      const rateEl = document.getElementById(`${prefix}SpeakingRate`);
      const rateLabel = document.getElementById(prefix === 'proShorts' ? 'labelProShortsRate' : 'labelLongVideoRate');
      const previewBtn = document.getElementById(prefix === 'proShorts' ? 'btnPreviewProShortsTts' : 'btnPreviewLongVideoTts');
      const audioEl = document.getElementById(`${prefix}TtsPreviewAudio`);
      const statusEl = document.getElementById(`${prefix}TtsPreviewStatus`);

      if (engineEl && voiceEl) {
        engineEl.addEventListener('change', () => {
          const list = workerEngineVoices[engineEl.value] || workerEngineVoices.edge;
          voiceEl.innerHTML = list.map(v => `<option value="${v.id}">${v.name}</option>`).join('');
        });
      }
      if (rateEl && rateLabel) {
        rateEl.addEventListener('input', () => {
          rateLabel.textContent = `${parseFloat(rateEl.value).toFixed(2)}x`;
        });
      }
      if (previewBtn) {
        previewBtn.addEventListener('click', async () => {
          const engine = engineEl ? engineEl.value : 'edge';
          const voice = voiceEl ? voiceEl.value : 'nanami';
          const rate = rateEl ? parseFloat(rateEl.value) || 1.0 : 1.0;

          // 台本があれば1カット目のセリフを試聴テキストに使用、なければジャンル別サンプル文
          let sampleText = "こんにちは！この声とスピードでナレーションを読み上げます。";
          const jsonVal = document.getElementById(scriptTextareaId)?.value?.trim();
          if (jsonVal) {
            try {
              const parsed = JSON.parse(jsonVal);
              const firstCut = (parsed.cuts && parsed.cuts[0]) || (parsed.chapters && parsed.chapters[0]?.cuts?.[0]);
              if (firstCut && (firstCut.dialogue || firstCut.narration)) {
                sampleText = (firstCut.dialogue || firstCut.narration).slice(0, 90);
              }
            } catch (_) {}
          } else {
            const genre = document.getElementById(genreSelectId)?.value || 'story';
            if (genre === 'edoculture') {
              sampleText = "実は江戸時代の庶民は、現代人も驚くほど粋で合理的な暮らしを送っていたのです！";
            } else if (genre === 'business') {
              sampleText = "なぜ9割の人がこの法則を知らないまま損をしてしまうのでしょうか？結論から解説します。";
            } else if (genre === 'trivia') {
              sampleText = "これを知ったら誰かに話したくなる、隠された驚きの真実をご紹介します！";
            }
          }

          const origHtml = previewBtn.innerHTML;
          previewBtn.disabled = true;
          previewBtn.innerHTML = '<span class="btn-spinner"></span><span>音声合成中...</span>';
          if (statusEl) statusEl.textContent = `「${sampleText.slice(0, 22)}...」を合成中...`;

          try {
            const audioUrl = await window.apiClient.previewTTS({
              text: sampleText,
              tts_engine: engine,
              voice_name: voice,
              speaking_rate: rate,
              google_tts_key: window.settingsManager.get('googleTtsKey') || '',
              elevenlabs_key: window.settingsManager.get('elevenLabsKey') || '',
              openai_key: window.settingsManager.get('openAiTtsKey') || '',
              azure_key: window.settingsManager.get('azureTtsKey') || '',
              azure_region: window.settingsManager.get('azureTtsRegion') || 'japaneast',
              voicevox_url: window.settingsManager.get('voicevoxUrl') || 'http://localhost:50021'
            });
            if (audioEl) {
              audioEl.src = audioUrl;
              audioEl.style.display = 'block';
              await audioEl.play().catch(() => {});
            }
            if (statusEl) statusEl.textContent = `試聴再生中 (${engine} / ${voice} / ${rate.toFixed(2)}x)`;
          } catch (err) {
            if (statusEl) statusEl.textContent = `試聴エラー: ${err.message}`;
            this.showToast(`TTS試聴エラー: ${err.message}`, 'error');
          } finally {
            previewBtn.disabled = false;
            previewBtn.innerHTML = origHtml;
          }
        });
      }
    };

    // 共通: テロップ即時プレビュー描画（Canvas 0ms即時描画 ＋ バックエンド5層PNGリアル描画）
    const setupWorkerTelopPreview = (prefix, scriptTextareaId, genreSelectId, visualStyleSelectId) => {
      const fontEl = document.getElementById(`${prefix}TelopFont`);
      const styleEl = document.getElementById(`${prefix}TelopStyle`);
      const sizeEl = document.getElementById(`${prefix}TelopFontSize`);
      const modeEl = document.getElementById(`${prefix}TelopMode`);
      const canvasEl = document.getElementById(`${prefix}TelopPreviewCanvas`);
      const imgEl = document.getElementById(`${prefix}TelopPreviewImg`);
      const badgeEl = document.getElementById(`${prefix}TelopPreviewBadge`);
      const genreEl = document.getElementById(genreSelectId);
      const vStyleEl = document.getElementById(visualStyleSelectId);

      const stylePalettes = {
        shorts_impact_yellow: { top: '#FFF500', bottom: '#FF8A00', outer: '#000000', inner: '#FFFFFF', label: '王道インパクト黄×黒' },
        variety_red_white:    { top: '#FF2A2A', bottom: '#B80000', outer: '#FFFFFF', inner: '#000000', label: '炎上・強調赤×白' },
        neon_cyber_cyan:      { top: '#00F5FF', bottom: '#0088FF', outer: '#040B1A', inner: '#FFFFFF', label: 'サイバー水色×濃紺' },
        edo_ukiyoe_crimson:   { top: '#FFE885', bottom: '#D9381E', outer: '#140804', inner: '#FFFDF5', label: '浮世絵・江戸紅金' },
        clean_emerald_white:  { top: '#FFFFFF', bottom: '#D8FFE8', outer: '#052E16', inner: '#10B981', label: 'クリーン白×エメラルド' }
      };

      const fontLabels = {
        keifont: 'けいふぉんと',
        DelaGothicOne: 'デラゴシック One',
        MochiyPopOne: 'モッチーポップ One',
        RocknRollOne: 'ロックンロール One',
        ReggaeOne: 'レゲエ One',
        YuseiMagic: '유성マジック',
        KaisoNext: '廻想体 ネクスト B',
        NotoSansJPBlack: '源ノ角ゴシック Heavy'
      };

      const comicColorEl = document.getElementById(`${prefix}ComicColorMode`);
      const comicDelayEl = document.getElementById(`${prefix}ComicBubbleDelay`);

      let debounceTimer = null;

      const renderPreview = () => {
        const fontKey = fontEl?.value || 'keifont';
        const styleKey = styleEl?.value || 'shorts_impact_yellow';
        const sizeKey = sizeEl?.value || 'medium';
        const genreVal = genreEl?.value || 'story';
        const visualStyleVal = vStyleEl?.value || 'anime_modern';
        const comicColorVal = comicColorEl?.value || 'color';
        const comicDelayVal = comicDelayEl?.value || '0.4';
        const isComicManga = visualStyleVal === 'comic_manga' || visualStyleVal === 'comic_manga_mono';
        const pal = stylePalettes[styleKey] || stylePalettes.shorts_impact_yellow;

        // プレビュー文言の決定（台本があれば1カット目のセリフ、なければスタイルに応じたサンプル文）
        let sampleText = "まさか、そんな秘密があったなんて…！";
        const jsonVal = document.getElementById(scriptTextareaId)?.value?.trim();
        if (jsonVal) {
          try {
            const parsed = JSON.parse(jsonVal);
            const firstCut = (parsed.cuts && parsed.cuts[0]) || (parsed.chapters && parsed.chapters[0]?.cuts?.[0]);
            if (firstCut && (firstCut.dialogue || firstCut.narration)) {
              sampleText = (firstCut.dialogue || firstCut.narration).slice(0, 22);
            }
          } catch (_) {}
        } else if (isComicManga) {
          sampleText = "実は、その戦略には決定的な盲点があるんです！";
        } else if (visualStyleVal === 'ukiyoe' || styleKey === 'edo_ukiyoe_crimson') {
          sampleText = "江戸の町人が熱狂した驚きの秘密とは！？";
        } else if (genreVal === 'business') {
          sampleText = "9割が知らない！圧倒的成果を出す法則";
        }

        if (badgeEl) {
          if (isComicManga) {
            const colorLabel = comicColorVal === 'monochrome' ? '白黒モノクロ' : 'フルカラー';
            badgeEl.textContent = `漫画フキダシ演出（${colorLabel} / 後出し+${comicDelayVal}秒 / 下部テロップ自動OFF）`;
          } else {
            const sizeLabel = sizeKey === 'large' ? '特大' : (sizeKey === 'small' ? 'コンパクト' : '標準');
            badgeEl.textContent = `${fontLabels[fontKey] || fontKey} × ${pal.label} (${sizeLabel})`;
          }
        }

        // 1. まずローカルCanvasで0ms即時プレビュー描画
        if (canvasEl) {
          const ctx = canvasEl.getContext('2d');
          const cw = canvasEl.width;
          const ch = canvasEl.height;
          ctx.clearRect(0, 0, cw, ch);

          // 背景グラデーション
          const bgGrad = ctx.createLinearGradient(0, 0, 0, ch);
          if (isComicManga && comicColorVal === 'monochrome') {
            bgGrad.addColorStop(0, '#3a3a3a');
            bgGrad.addColorStop(1, '#181818');
          } else if (visualStyleVal === 'ukiyoe' || styleKey === 'edo_ukiyoe_crimson') {
            bgGrad.addColorStop(0, '#2e2620');
            bgGrad.addColorStop(1, '#181c30');
          } else {
            bgGrad.addColorStop(0, '#16203a');
            bgGrad.addColorStop(1, '#0a0f1e');
          }
          ctx.fillStyle = bgGrad;
          ctx.fillRect(0, 0, cw, ch);

          if (isComicManga) {
            // 漫画風フキダシ（白背景＋黒太枠＋しっぽ＋話者ピルバッジ）を描画
            const bx = cw * 0.08;
            const by = ch * 0.16;
            const bw = cw * 0.84;
            const bh = ch * 0.62;
            ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
            ctx.beginPath();
            ctx.roundRect(bx + 5, by + 6, bw, bh, 22);
            ctx.fill();

            ctx.fillStyle = '#fcfcfa';
            ctx.strokeStyle = '#12141c';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.roundRect(bx, by, bw, bh, 22);
            ctx.fill();
            ctx.stroke();

            // フキダシのしっぽ
            ctx.beginPath();
            ctx.moveTo(cw * 0.30, by + bh - 2);
            ctx.lineTo(cw * 0.35, by + bh + 16);
            ctx.lineTo(cw * 0.40, by + bh - 2);
            ctx.closePath();
            ctx.fill();
            ctx.stroke();

            // 話者ピルバッジ
            ctx.fillStyle = comicColorVal === 'monochrome' ? '#222222' : '#10b981';
            ctx.beginPath();
            ctx.roundRect(bx + 18, by - 11, 110, 22, 11);
            ctx.fill();
            ctx.fillStyle = '#ffffff';
            ctx.font = '800 13px "Noto Sans JP", sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('主人公・佐藤', bx + 73, by);

            // フキダシ内セリフ
            ctx.fillStyle = '#11141c';
            ctx.font = '900 24px "Hiragino Kaku Gothic StdN", "Noto Sans JP", sans-serif';
            ctx.fillText(sampleText.slice(0, 20), cw / 2, by + bh / 2 + 3);
          } else {
            // ざぶとん半透明プレート
            const plateW = cw * 0.88;
            const plateH = ch * 0.64;
            const plateX = (cw - plateW) / 2;
            const plateY = (ch - plateH) / 2;
            ctx.fillStyle = 'rgba(8, 10, 18, 0.72)';
            ctx.beginPath();
            ctx.roundRect(plateX, plateY, plateW, plateH, 16);
            ctx.fill();

            const pxSize = sizeKey === 'large' ? 38 : (sizeKey === 'small' ? 26 : 32);
            ctx.font = `900 ${pxSize}px "Hiragino Kaku Gothic StdN", "Noto Sans JP", "Yu Gothic UI", sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            const cx = cw / 2;
            const cy = ch / 2;

            // ドロップシャドウ
            ctx.lineJoin = 'round';
            ctx.lineWidth = 14;
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.85)';
            ctx.strokeText(sampleText.slice(0, 17), cx + 4, cy + 5);

            // 外フチ
            ctx.lineWidth = 12;
            ctx.strokeStyle = pal.outer;
            ctx.strokeText(sampleText.slice(0, 17), cx, cy);

            // 内フチ
            ctx.lineWidth = 5;
            ctx.strokeStyle = pal.inner;
            ctx.strokeText(sampleText.slice(0, 17), cx, cy);

            // 本体縦グラデーション
            const textGrad = ctx.createLinearGradient(0, cy - pxSize / 2, 0, cy + pxSize / 2);
            textGrad.addColorStop(0, pal.top);
            textGrad.addColorStop(1, pal.bottom);
            ctx.fillStyle = textGrad;
            ctx.fillText(sampleText.slice(0, 17), cx, cy);
          }
        }

        // 2. バックエンドの実寸5層PILエンジンから本物のフォント描画PNGを取得して表示
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => {
          try {
            const effectiveStyle = (isComicManga && comicColorVal === 'monochrome') ? 'comic_manga_mono' : visualStyleVal;
            const res = await window.apiClient.previewTelop({
              text: sampleText,
              telopFont: fontKey,
              telopStyle: styleKey,
              telopFontSize: sizeKey,
              genre: genreVal,
              visualStyle: effectiveStyle
            });
            if (res && res.image_base64 && imgEl) {
              imgEl.src = res.image_base64;
              imgEl.style.display = 'block';
              if (canvasEl) canvasEl.style.display = 'none';
            }
          } catch (_) {
            if (imgEl) imgEl.style.display = 'none';
            if (canvasEl) canvasEl.style.display = 'block';
          }
        }, 120);
      };

      [fontEl, styleEl, sizeEl, modeEl, genreEl, vStyleEl, comicColorEl, comicDelayEl].forEach(el => {
        if (el) el.addEventListener('change', renderPreview);
      });

      // 初回即時描画
      setTimeout(renderPreview, 80);
      return renderPreview;
    };

    // 共通: ワーカー内BGM選曲・音量・その場試聴セットアップ
    const setupWorkerBgmControls = (prefix, scriptTextareaId, genreSelectId, visualStyleSelectId) => {
      const selectEl = document.getElementById(`${prefix}BgmSelect`);
      const customGroupEl = document.getElementById(`${prefix}BgmCustomGroup`);
      const volEl = document.getElementById(`${prefix}BgmVolume`);
      const volLabel = document.getElementById(prefix === 'proShorts' ? 'labelProShortsBgmVol' : 'labelLongVideoBgmVol');
      const previewBtn = document.getElementById(prefix === 'proShorts' ? 'btnPreviewProShortsBgm' : 'btnPreviewLongVideoBgm');
      const audioEl = document.getElementById(`${prefix}BgmPreviewAudio`);

      // 登録済みカスタムBGM一覧をロードしてプルダウンに追加
      const refreshCustomBgmList = async () => {
        if (!customGroupEl) return;
        try {
          const data = await window.apiClient.listBGM();
          const tracks = data.bgm_tracks || [];
          customGroupEl.innerHTML = '';
          tracks.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.filename || t.bgm_id;
            opt.textContent = `登録BGM: ${t.title} (${t.keywords || 'カスタム'})`;
            opt.dataset.previewUrl = t.storage_url || `${window.apiClient.baseUrl}/api/bgm/file/${encodeURIComponent(t.filename || t.bgm_id)}`;
            customGroupEl.appendChild(opt);
          });
        } catch (_) {}
      };
      refreshCustomBgmList();

      if (volEl && volLabel) {
        volEl.addEventListener('input', () => {
          const pct = parseInt(volEl.value, 10) || 20;
          volLabel.textContent = `${pct}%`;
          if (audioEl) {
            audioEl.volume = Math.min(1.0, Math.max(0.05, pct / 100));
          }
        });
      }

      if (previewBtn && selectEl && audioEl) {
        previewBtn.addEventListener('click', async () => {
          const val = selectEl.value || 'auto_script';
          if (val === 'none') {
            audioEl.pause();
            audioEl.style.display = 'none';
            return this.showToast('「BGMなし（無音）」が選択されています', 'info');
          }

          let targetUrl = '';
          if (val === 'auto_script') {
            // 台本データ内の1カット目のbgm_tagまたはスタイルに応じた内蔵BGMを試聴
            const vStyle = document.getElementById(visualStyleSelectId)?.value || 'anime_modern';
            const genre = document.getElementById(genreSelectId)?.value || 'story';
            let presetId = (vStyle === 'ukiyoe' || genre === 'edoculture') ? 'edo_ukiyoe' : 'corporate_clean';
            const jsonVal = document.getElementById(scriptTextareaId)?.value?.trim();
            if (jsonVal && vStyle !== 'ukiyoe') {
              try {
                const parsed = JSON.parse(jsonVal);
                const firstCut = (parsed.cuts && parsed.cuts[0]) || (parsed.chapters && parsed.chapters[0]?.cuts?.[0]);
                const tag = firstCut?.bgm_tag || 'neutral';
                const tagMap = {
                  cheerful: 'upbeat_marimba',
                  funny: 'upbeat_marimba',
                  warm: 'calm_piano',
                  touching: 'calm_piano',
                  suspense: 'mystery_synth',
                  frightening: 'mystery_synth',
                  epic: 'dramatic_strings',
                  neutral: 'corporate_clean'
                };
                presetId = tagMap[tag] || 'corporate_clean';
              } catch (_) {}
            }
            targetUrl = window.apiClient.getBuiltinBgmPreviewUrl(presetId);
          } else if (val.startsWith('builtin:')) {
            targetUrl = window.apiClient.getBuiltinBgmPreviewUrl(val);
          } else {
            const selectedOpt = selectEl.options[selectEl.selectedIndex];
            targetUrl = selectedOpt?.dataset?.previewUrl || `${window.apiClient.baseUrl}/api/bgm/file/${encodeURIComponent(val)}`;
          }

          audioEl.src = targetUrl;
          const pct = parseInt(volEl?.value || '20', 10);
          audioEl.volume = Math.min(1.0, Math.max(0.05, pct / 100));
          audioEl.style.display = 'block';
          try {
            await audioEl.play();
            this.showToast('BGMプレビューを再生中...', 'info');
          } catch (e) {
            this.showToast('BGMの再生に失敗しました: ' + e.message, 'error');
          }
        });
      }

      // 台本生成完了時に auto_script オプションのラベルへ検知BGMタグを表示するヘルパー
      return (scriptData) => {
        if (!selectEl || !scriptData) return;
        const cuts = scriptData.cuts || (scriptData.chapters ? scriptData.chapters.flatMap(ch => ch.cuts || []) : []);
        const tags = [...new Set(cuts.map(c => c.bgm_tag).filter(Boolean))];
        const autoOpt = selectEl.querySelector('option[value="auto_script"]');
        if (autoOpt && tags.length > 0) {
          autoOpt.textContent = `台本の自動BGM設定を使用（設定済タグ: ${tags.slice(0, 4).join(' ➔ ')}）`;
        }
      };
    };

    // Pro版ショート & 長尺動画のワーカーコントロール初期化
    const refreshProShortsTelop = setupWorkerTelopPreview('proShorts', 'inputProShortsScriptJson', 'inputProShortsGenre', 'inputProShortsVisualStyle');
    const refreshLongVideoTelop = setupWorkerTelopPreview('longVideo', 'inputLongVideoScriptJson', 'inputLongVideoGenre', 'inputLongVideoVisualStyle');
    setupWorkerTtsControls('proShorts', 'inputProShortsScriptJson', 'inputProShortsGenre');
    setupWorkerTtsControls('longVideo', 'inputLongVideoScriptJson', 'inputLongVideoGenre');
    const updateProShortsBgmTags = setupWorkerBgmControls('proShorts', 'inputProShortsScriptJson', 'inputProShortsGenre', 'inputProShortsVisualStyle');
    const updateLongVideoBgmTags = setupWorkerBgmControls('longVideo', 'inputLongVideoScriptJson', 'inputLongVideoGenre', 'inputLongVideoVisualStyle');

    // ジャンル変更時のおすすめスタイル・テロップ・BGMスマート連動（手動でのスタイル個別変更も完全自由）
    const bindGenreAndStyleSync = (genreId, styleId, telopStyleId, telopFontId, bgmSelectId, refreshTelopFn, comicBoxId) => {
      const gEl = document.getElementById(genreId);
      const sEl = document.getElementById(styleId);
      const tsEl = document.getElementById(telopStyleId);
      const tfEl = document.getElementById(telopFontId);
      const bgmEl = document.getElementById(bgmSelectId);
      const comicBoxEl = comicBoxId ? document.getElementById(comicBoxId) : null;

      const syncComicBox = () => {
        if (!sEl || !comicBoxEl) return;
        const isComic = sEl.value === 'comic_manga' || sEl.value === 'comic_manga_mono';
        comicBoxEl.style.display = isComic ? 'block' : 'none';
      };

      if (gEl && sEl) {
        gEl.addEventListener('change', () => {
          if (gEl.value === 'edoculture') {
            sEl.value = 'ukiyoe';
            if (tsEl) tsEl.value = 'edo_ukiyoe_crimson';
            if (tfEl) tfEl.value = 'KaisoNext';
            if (bgmEl) bgmEl.value = 'builtin:edo_ukiyoe';
          } else if (gEl.value === 'business' && sEl.value === 'ukiyoe') {
            sEl.value = 'comic_manga';
            if (tsEl) tsEl.value = 'clean_emerald_white';
            if (bgmEl) bgmEl.value = 'auto_script';
          }
          syncComicBox();
          if (refreshTelopFn) refreshTelopFn();
        });

        sEl.addEventListener('change', () => {
          if (sEl.value === 'ukiyoe') {
            if (tsEl) tsEl.value = 'edo_ukiyoe_crimson';
            if (tfEl) tfEl.value = 'KaisoNext';
            if (bgmEl && bgmEl.value === 'auto_script') bgmEl.value = 'builtin:edo_ukiyoe';
          }
          syncComicBox();
          if (refreshTelopFn) refreshTelopFn();
        });

        syncComicBox();
      }
    };

    bindGenreAndStyleSync('inputProShortsGenre', 'inputProShortsVisualStyle', 'proShortsTelopStyle', 'proShortsTelopFont', 'proShortsBgmSelect', refreshProShortsTelop, 'proShortsComicOptionsBox');
    bindGenreAndStyleSync('inputLongVideoGenre', 'inputLongVideoVisualStyle', 'longVideoTelopStyle', 'longVideoTelopFont', 'longVideoBgmSelect', refreshLongVideoTelop, 'longVideoComicOptionsBox');

    // 1. Pro版ショート動画
    const btnRunProShorts = document.getElementById('btnRunProShortsScript');
    const btnGenProShorts = document.getElementById('btnGenerateProShortsVideo');
    const proShortsScriptArea = document.getElementById('proShortsScriptArea');
    const proShortsLockNotice = document.getElementById('proShortsLockNotice');

    const checkProShortsPerm = async () => {
      if (this.isAdmin) {
        if (proShortsLockNotice) proShortsLockNotice.style.display = 'none';
        return;
      }
      try {
        const res = await window.apiClient.getUserPermissions("manga_long_video_create");
        if (!res.access_info?.allowed) {
          if (proShortsLockNotice) proShortsLockNotice.style.display = 'block';
        } else {
          if (proShortsLockNotice) proShortsLockNotice.style.display = 'none';
        }
      } catch (e) {
        console.log("Permission check:", e);
      }
    };
    const proShortsNavBtn = document.querySelector('.nav-item[data-target="pro-shorts"]');
    if (proShortsNavBtn) proShortsNavBtn.addEventListener('click', checkProShortsPerm);

    if (btnRunProShorts) {
      btnRunProShorts.addEventListener('click', async () => {
        const theme = document.getElementById('inputProShortsTheme')?.value.trim() || '';
        const customRaw = document.getElementById('inputRawScriptProShorts')?.value.trim() || '';
        const genre = document.getElementById('inputProShortsGenre')?.value || 'story';
        const visualStyle = document.getElementById('inputProShortsVisualStyle')?.value || 'anime_modern';

        if (!theme && !customRaw) {
          return this.showToast("テーマ・題材、または自前の台本を入力してください", "error");
        }

        const originalHtml = btnRunProShorts.innerHTML;
        btnRunProShorts.disabled = true;
        btnRunProShorts.classList.add('is-loading');
        btnRunProShorts.innerHTML = '<span class="btn-spinner"></span><span>台本を作成中...</span>';

        try {
          let scriptObj = null;
          if (customRaw && !theme) {
            this.showToast(`自前の台本を【${visualStyle === 'ukiyoe' ? '本格浮世絵' : visualStyle}】60秒カット割りへ変換中...`, "info");
            const res = await window.apiClient.normalizeScript(customRaw, 'pro_shorts', genre, visualStyle);
            if (res.success && res.timeline) scriptObj = res.timeline;
          } else {
            const combinedTheme = customRaw ? `${theme}\n\n【自前台本・参考原案】:\n${customRaw}` : theme;
            this.showToast(`Pro版ショート台本（絵柄: ${visualStyle === 'ukiyoe' ? '本格浮世絵・錦絵' : visualStyle}）を生成中...`, "info");
            const res = await window.apiClient.generateProShortsScript(combinedTheme, genre, visualStyle);
            if (res.success && res.script) scriptObj = res.script;
          }

          if (scriptObj) {
            scriptObj.visual_style = visualStyle;
            document.getElementById('inputProShortsScriptJson').value = JSON.stringify(scriptObj, null, 2);
            proShortsScriptArea.style.display = 'block';
            updateProShortsBgmTags(scriptObj);
            if (refreshProShortsTelop) refreshProShortsTelop();
            this.showToast("Pro版ショート動画の台本とBGM・演出設定が完了しました！", "success");
            proShortsScriptArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        } catch (err) {
          this.showToast("台本生成失敗: " + err.message, "error");
        } finally {
          btnRunProShorts.disabled = false;
          btnRunProShorts.classList.remove('is-loading');
          btnRunProShorts.innerHTML = originalHtml;
        }
      });
    }

    // Pro版ショート: Outlier（外れ値・隠れ需要）リサーチ
    const btnProOutlier = document.getElementById('btnProShortsOutlier');
    const proOutlierArea = document.getElementById('proShortsOutlierResultArea');
    const proOutlierInsight = document.getElementById('proShortsOutlierInsight');
    const proAnglesContainer = document.getElementById('proShortsAnglesContainer');

    if (btnProOutlier) {
      btnProOutlier.addEventListener('click', async () => {
        const theme = document.getElementById('inputProShortsTheme').value.trim();
        const genre = document.getElementById('inputProShortsGenre').value;
        if (!theme) return this.showToast('リサーチするテーマを入力してください', 'error');

        btnProOutlier.disabled = true;
        btnProOutlier.innerHTML = '<span class="btn-spinner"></span><span>外れ値検索中...</span>';
        this.showToast('YouTube/Webから少フォロワー高再生のOutlier動画を検索中...', 'info');

        try {
          const res = await window.apiClient.researchOutliers(theme, genre);
          if (res.success && res.analysis) {
            if (proOutlierArea) proOutlierArea.style.display = 'block';
            if (proOutlierInsight) {
              proOutlierInsight.textContent = res.analysis.hidden_demand_insight || '隠れ需要を分析しました。';
            }
            if (proAnglesContainer && Array.isArray(res.analysis.diverse_angles)) {
              proAnglesContainer.innerHTML = res.analysis.diverse_angles.map(ang => `
                <button type="button" class="btn btn-outline" style="text-align: left; padding: 0.4rem 0.6rem; font-size: 0.8rem; width: 100%; display: flex; flex-direction: column; align-items: flex-start; gap: 2px;" onclick="document.getElementById('inputProShortsTheme').value = '${ang.title.replace(/'/g, "\\'")}'; window.appController.showToast('切り口をテーマに適用しました', 'info');">
                  <span style="font-weight: 600; color: var(--accent-primary);">[切り口${ang.angle_id}] ${ang.title}</span>
                  <span style="font-size: 0.75rem; color: var(--text-secondary);">${ang.concept}</span>
                </button>
              `).join('');
            }
            this.showToast('隠れ需要と多角的な切り口を発掘しました！', 'success');
          }
        } catch (e) {
          this.showToast('Outlierリサーチ失敗: ' + e.message, 'error');
        } finally {
          btnProOutlier.disabled = false;
          btnProOutlier.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> リサーチ（外れ値・隠れ需要）';
        }
      });
    }

    // Pro版ショート: ファイル読み込み (.txt / .md / .json)
    const fileImportPro = document.getElementById('fileImportProShorts');
    const rawScriptPro = document.getElementById('inputRawScriptProShorts');
    if (fileImportPro && rawScriptPro) {
      fileImportPro.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          rawScriptPro.value = event.target?.result || '';
          this.showToast(`ファイル「${file.name}」を読み込みました`, 'info');
        };
        reader.readAsText(file);
      });
    }

    // Pro版ショート: Google Drive 読み込み
    const btnDrivePro = document.getElementById('btnDriveImportProShorts');
    if (btnDrivePro && rawScriptPro) {
      btnDrivePro.addEventListener('click', () => {
        const driveUrl = prompt('Google Driveファイルの公開リンクまたはテキストを入力してください:');
        if (driveUrl) {
          rawScriptPro.value = driveUrl;
          this.showToast('Driveデータをセットしました。「1. 台本作成」または「自前台本を変換」を押してください', 'info');
        }
      });
    }

    // Pro版ショート: 当ツール標準フォーマット(60秒)へ自動リライト
    const btnNormPro = document.getElementById('btnNormalizeProShortsScript');
    if (btnNormPro && rawScriptPro) {
      btnNormPro.addEventListener('click', async () => {
        const text = rawScriptPro.value.trim();
        if (!text) return this.showToast('リライトする自前の台本・メモ・外部資料を入力してください', 'error');

        const genre = document.getElementById('inputProShortsGenre')?.value || 'story';
        const visualStyle = document.getElementById('inputProShortsVisualStyle')?.value || 'anime_modern';
        const origHtml = btnNormPro.innerHTML;
        btnNormPro.disabled = true;
        btnNormPro.classList.add('is-loading');
        btnNormPro.innerHTML = '<span class="btn-spinner"></span><span>60秒台本へ自動リライト中...</span>';

        this.showToast('自前台本を60秒カット割りフォーマットへリライト中...', 'info');
        try {
          const res = await window.apiClient.normalizeScript(text, 'pro_shorts', genre, visualStyle);
          if (res.success && res.timeline) {
            res.timeline.visual_style = visualStyle;
            document.getElementById('inputProShortsScriptJson').value = JSON.stringify(res.timeline, null, 2);
            proShortsScriptArea.style.display = 'block';
            updateProShortsBgmTags(res.timeline);
            if (refreshProShortsTelop) refreshProShortsTelop();
            this.showToast('当ツール標準フォーマットへのリライトが完了しました！', 'success');
            proShortsScriptArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        } catch (e) {
          this.showToast('台本リライト失敗: ' + e.message, 'error');
        } finally {
          btnNormPro.disabled = false;
          btnNormPro.classList.remove('is-loading');
          btnNormPro.innerHTML = origHtml;
        }
      });
    }

    if (btnGenProShorts) {
      btnGenProShorts.addEventListener('click', async () => {
        const jsonStr = document.getElementById('inputProShortsScriptJson').value.trim();
        if (!jsonStr) return this.showToast("まずは「1. 台本作成」ボタンを押して台本を作成してください", "error");

        let scriptData;
        try {
          scriptData = JSON.parse(jsonStr);
        } catch (e) {
          return this.showToast("JSON形式が不正です: " + e.message, "error");
        }

        const visualStyle = document.getElementById('inputProShortsVisualStyle')?.value || scriptData.visual_style || 'anime_modern';
        scriptData.visual_style = visualStyle;

        const ttsEngine = document.getElementById('proShortsTtsEngine')?.value || window.settingsManager.get('ttsEngine') || 'edge';
        const voiceName = document.getElementById('proShortsVoiceName')?.value || window.settingsManager.get('voiceName') || 'nanami';
        const speakingRate = document.getElementById('proShortsSpeakingRate')?.value || window.settingsManager.get('speakingRate') || '1.0';
        const telopStyle = document.getElementById('proShortsTelopStyle')?.value || 'shorts_impact_yellow';
        const telopMode = document.getElementById('proShortsTelopMode')?.value || 'sequential';
        const telopFontSize = document.getElementById('proShortsTelopFontSize')?.value || 'medium';
        const telopFont = document.getElementById('proShortsTelopFont')?.value || 'keifont';
        const bgmChoice = document.getElementById('proShortsBgmSelect')?.value || 'auto_script';
        const bgmVolume = (parseInt(document.getElementById('proShortsBgmVolume')?.value || '20', 10)) / 100;
        const comicColorMode = document.getElementById('proShortsComicColorMode')?.value || 'color';
        const comicBubbleDelay = parseFloat(document.getElementById('proShortsComicBubbleDelay')?.value || '0.4');
        const isComicStyle = visualStyle === 'comic_manga' || visualStyle === 'comic_manga_mono';

        const videoOptions = {
          visualStyle: visualStyle,
          speakingRate: speakingRate,
          telopStyle: telopStyle,
          telopMode: isComicStyle ? 'comic_bubble' : telopMode,
          telopFontSize: telopFontSize,
          telopFont: telopFont,
          bgmChoice: bgmChoice,
          bgmVolume: bgmVolume,
          customReferenceImages: this.proShortsRefImages && this.proShortsRefImages.length > 0 ? this.proShortsRefImages : null,
          videoMode: 'pro_shorts',
          comicColorMode: comicColorMode,
          comicBubbleEnabled: isComicStyle,
          comicBubbleDelay: isNaN(comicBubbleDelay) ? 0.4 : comicBubbleDelay
        };

        localStorage.setItem('kimidori_draft_pro_shorts_script', jsonStr);

        const originalGenHtml = btnGenProShorts.innerHTML;
        btnGenProShorts.disabled = true;
        btnGenProShorts.classList.add('is-loading');
        btnGenProShorts.innerHTML = '<span class="btn-spinner"></span><span>サーバー通信・ジョブ登録中...</span>';

        this.showToast(`Pro版ショート動画（スタイル: ${visualStyle === 'ukiyoe' ? '本格浮世絵・錦絵' : (isComicStyle ? '漫画風・セリフ後出し演出' : visualStyle)}）の生成を開始しました`, "info");

        const progArea = document.getElementById('proShortsProgressArea');
        const titleEl = document.getElementById('proShortsProgressTitle');
        const fillEl = document.getElementById('proShortsProgressFill');
        const msgEl = document.getElementById('proShortsProgressMsg');
        const resEl = document.getElementById('proShortsVideoResult');
        const previewEl = document.getElementById('proShortsVideoPreview');

        if (progArea) {
          progArea.style.display = 'block';
          if (titleEl) titleEl.textContent = "ジョブ発行・素材準備中...";
          if (fillEl) fillEl.style.width = "10%";
          if (msgEl) msgEl.textContent = "サーバーにジョブをリクエストしています...";
          progArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        try {
          const res = await window.apiClient.generateMangaVideo(scriptData, ttsEngine, voiceName, {}, videoOptions);
          this.currentProShortsJobId = res.job_id;
          localStorage.setItem('kimidori_last_pro_shorts_job', res.job_id);

          this.startJobPolling(res.job_id, 'PRO_SHORTS', {
            onProgress: (job) => {
              if (titleEl) titleEl.textContent = job.message || "生成中...";
              if (fillEl) fillEl.style.width = `${job.progress || 10}%`;
              if (msgEl) msgEl.textContent = `進捗: ${job.progress}%`;
            },
            onComplete: (job) => {
              if (titleEl) titleEl.textContent = "Pro版ショート動画が完成しました！";
              if (fillEl) fillEl.style.width = "100%";
              if (msgEl) msgEl.textContent = "生成完了（保存済みストックにも自動保存されました）";
              const dlUrl = `${window.apiClient.baseUrl}/api/download/${res.job_id}?t=${Date.now()}`;
              if (resEl) resEl.style.display = 'block';
              if (previewEl) {
                previewEl.src = dlUrl;
                previewEl.load();
              }
              const dlBtn = document.getElementById('btnDownloadProShorts');
              if (dlBtn) dlBtn.href = `${window.apiClient.baseUrl}/api/download/${res.job_id}?download=1`;
              this.loadSavedVideoStock('pro_shorts', false);
              btnGenProShorts.disabled = false;
              btnGenProShorts.classList.remove('is-loading');
              btnGenProShorts.innerHTML = originalGenHtml;
            },
            onError: (err) => {
              if (titleEl) titleEl.textContent = "生成失敗";
              if (msgEl) msgEl.textContent = err;
              btnGenProShorts.disabled = false;
              btnGenProShorts.classList.remove('is-loading');
              btnGenProShorts.innerHTML = originalGenHtml;
            }
          });
        } catch (err) {
          this.showToast("動画生成失敗: " + err.message, "error");
          btnGenProShorts.disabled = false;
          btnGenProShorts.classList.remove('is-loading');
          btnGenProShorts.innerHTML = originalGenHtml;
          if (progArea) progArea.style.display = 'none';
        }
      });
    }

    // Pro版ショート動画 リセットボタン
    document.getElementById('btnResetProShorts')?.addEventListener('click', () => {
      const progArea = document.getElementById('proShortsProgressArea');
      if (progArea) progArea.style.display = 'none';
      const scriptArea = document.getElementById('proShortsScriptArea');
      if (scriptArea) scriptArea.style.display = 'none';
      const resEl = document.getElementById('proShortsVideoResult');
      if (resEl) resEl.style.display = 'none';
      const prev = document.getElementById('proShortsVideoPreview');
      if (prev) { prev.pause(); prev.removeAttribute('src'); }
      const themeInput = document.getElementById('inputProShortsTheme');
      if (themeInput) { themeInput.value = ''; themeInput.focus(); }
      const jsonArea = document.getElementById('inputProShortsScriptJson');
      if (jsonArea) jsonArea.value = '';
      localStorage.removeItem('kimidori_draft_pro_shorts_script');
      this.showToast("最初から新しく作成する画面に戻りました（保存済みストックはそのまま保持されています）", "info");
    });

    // 2. 長尺動画（15〜20分）完全仕様
    const btnRunLong = document.getElementById('btnRunLongVideoScript');
    const btnGenLong = document.getElementById('btnGenerateLongVideo');
    const longScriptArea = document.getElementById('longVideoScriptArea');
    const longLockNotice = document.getElementById('longVideoLockNotice');

    // 長尺動画の固定キャラクター特徴（リファレンス一覧＋入力フォーム）を収集するヘルパー
    const collectLongVideoCharacterTraits = () => {
      const traits = [];
      const seenNames = new Set();
      if (Array.isArray(this.longVideoRefImages)) {
        this.longVideoRefImages.forEach(item => {
          const nm = (item.name || '').trim();
          if (nm && nm !== '共通' && !seenNames.has(nm)) {
            seenNames.add(nm);
            traits.push({
              name: nm,
              role: item.role || '主要登場人物',
              clothing: item.clothing || '',
              hairstyle: item.hairstyle || '',
              appearance: item.appearance || '',
              appearance_prompt_en: item.appearance_prompt_en || ''
            });
          }
        });
      }
      const curName = document.getElementById('inputRefLabelLongVideo')?.value?.trim() || '';
      const curRole = document.getElementById('inputCharRoleLong')?.value?.trim() || '';
      const curCloth = document.getElementById('inputCharClothingLong')?.value?.trim() || '';
      const curHair = document.getElementById('inputCharHairstyleLong')?.value?.trim() || '';
      const curApp = document.getElementById('inputCharAppearanceLong')?.value?.trim() || '';
      if (curName && curName !== '共通' && !seenNames.has(curName) && (curCloth || curHair || curApp)) {
        traits.push({
          name: curName,
          role: curRole || '主人公',
          clothing: curCloth,
          hairstyle: curHair,
          appearance: curApp
        });
      }
      return traits;
    };

    const checkLongPerm = async () => {
      if (this.isAdmin) {
        if (longLockNotice) longLockNotice.style.display = 'none';
        return;
      }
      try {
        const res = await window.apiClient.getUserPermissions("manga_long_video_create");
        if (!res.access_info?.allowed) {
          if (longLockNotice) longLockNotice.style.display = 'block';
        } else {
          if (longLockNotice) longLockNotice.style.display = 'none';
        }
      } catch (e) {
        console.log("Permission check:", e);
      }
    };
    const longNavBtn = document.querySelector('.nav-item[data-target="long-video"]');
    if (longNavBtn) longNavBtn.addEventListener('click', checkLongPerm);

    if (btnRunLong) {
      btnRunLong.addEventListener('click', async () => {
        const theme = document.getElementById('inputLongVideoTheme')?.value.trim() || '';
        const customRaw = document.getElementById('inputRawScriptLongVideo')?.value.trim() || '';
        const genre = document.getElementById('inputLongVideoGenre')?.value || 'story';
        const visualStyle = document.getElementById('inputLongVideoVisualStyle')?.value || 'anime_modern';
        const duration = document.getElementById('inputLongVideoDuration')?.value || '15';
        const scriptMode = document.getElementById('longVideoScriptModeSelect')?.value || 'western_book_adaptation';
        const characterTraits = collectLongVideoCharacterTraits();

        if (!theme && !customRaw) {
          return this.showToast("動画テーマ、または自前の台本を入力してください", "error");
        }

        const origRunHtml = btnRunLong.innerHTML;
        btnRunLong.disabled = true;
        btnRunLong.classList.add('is-loading');
        btnRunLong.innerHTML = '<span class="btn-spinner"></span><span>全5章台本を執筆中...</span>';

        try {
          let scriptObj = null;
          if ((scriptMode === 'custom_script_rewrite' && customRaw) || (customRaw && !theme)) {
            this.showToast(`自前の台本を長尺全5章カット割り（スタイル: ${visualStyle === 'ukiyoe' ? '本格浮世絵' : (visualStyle === 'comic_manga' ? 'ビジネス漫画風' : visualStyle)}）へ変換中...`, "info");
            const res = await window.apiClient.normalizeScript(customRaw, 'long_video', genre, visualStyle);
            if (res.success && res.timeline) scriptObj = res.timeline;
          } else {
            const modeLabel = scriptMode === 'western_book_adaptation' ? '洋書翻案ビジネス漫画モード' : '標準長尺モード';
            this.showToast(`全5章長尺台本＆人物シート（${modeLabel} / スタイル: ${visualStyle === 'ukiyoe' ? '本格浮世絵' : (visualStyle === 'comic_manga' ? 'ビジネス漫画風' : visualStyle)}）を生成中...`, "info");
            const res = await window.apiClient.generateLongVideoScript(theme, genre, duration, customRaw, visualStyle, {
              scriptMode: scriptMode,
              characterTraits: characterTraits
            });
            if (res.success && res.script) scriptObj = res.script;
          }

          if (scriptObj) {
            scriptObj.visual_style = visualStyle;
            if (characterTraits.length > 0) {
              scriptObj.characters = Array.isArray(scriptObj.characters) ? scriptObj.characters : [];
              characterTraits.forEach(ct => {
                const existing = scriptObj.characters.find(c => c.name === ct.name);
                const traitEn = `consistent character ${ct.name}, wearing ${ct.clothing || 'business attire'}, hairstyle ${ct.hairstyle || 'neat hair'}, ${ct.appearance || 'professional look'}`;
                if (existing) {
                  existing.role = ct.role || existing.role;
                  existing.appearance_prompt_en = ct.appearance_prompt_en || `${traitEn}, ${existing.appearance_prompt_en || ''}`;
                } else {
                  scriptObj.characters.push({
                    name: ct.name,
                    role: ct.role || '主人公',
                    appearance_prompt_en: ct.appearance_prompt_en || traitEn
                  });
                }
              });
            }
            const jsonText = JSON.stringify(scriptObj, null, 2);
            document.getElementById('inputLongVideoScriptJson').value = jsonText;
            localStorage.setItem('kimidori_draft_long_video_script', jsonText);
            longScriptArea.style.display = 'block';
            updateLongVideoBgmTags(scriptObj);
            if (refreshLongVideoTelop) refreshLongVideoTelop();
            this.showToast("全5章台本とキャラ固定・確定設計図が生成されました！", "success");
            longScriptArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        } catch (err) {
          this.showToast("長尺台本生成失敗: " + err.message, "error");
        } finally {
          btnRunLong.disabled = false;
          btnRunLong.classList.remove('is-loading');
          btnRunLong.innerHTML = origRunHtml;
        }
      });
    }

    // 長尺動画: Outlier（外れ値）リサーチ
    const btnLongOutlier = document.getElementById('btnLongVideoOutlier');
    const longOutlierArea = document.getElementById('longVideoOutlierResultArea');
    const longOutlierTitle = document.getElementById('longVideoOutlierTitle');
    const longOutlierContent = document.getElementById('longVideoOutlierContent');

    if (btnLongOutlier) {
      btnLongOutlier.addEventListener('click', async () => {
        const theme = document.getElementById('inputLongVideoTheme').value.trim();
        const genre = document.getElementById('inputLongVideoGenre').value;
        if (!theme) return this.showToast('リサーチするテーマを入力してください', 'error');

        btnLongOutlier.disabled = true;
        btnLongOutlier.innerHTML = '<span class="btn-spinner"></span><span>外れ値検索中...</span>';
        this.showToast('YouTube/Webから高再生Outlier動画を検索中...', 'info');

        try {
          const res = await window.apiClient.researchOutliers(theme, genre);
          if (res.success && res.analysis) {
            if (longOutlierArea) longOutlierArea.style.display = 'block';
            if (longOutlierTitle) longOutlierTitle.textContent = '真の隠れ需要＆多角的な切り口リサーチ結果';
            if (longOutlierContent) {
              const angles = Array.isArray(res.analysis.diverse_angles)
                ? res.analysis.diverse_angles.map(a => `<div style="margin-top: 4px; padding: 4px 8px; background: rgba(255,255,255,0.03); border-radius: 4px; cursor: pointer;" onclick="document.getElementById('inputLongVideoTheme').value = '${a.title.replace(/'/g, "\\'")}'; window.appController.showToast('切り口をテーマに適用しました', 'info');"><strong>・${a.title}</strong>: ${a.concept}</div>`).join('')
                : '';
              longOutlierContent.innerHTML = `
                <p style="margin: 0 0 6px 0;"><strong>【隠れ需要インサイト】</strong>: ${res.analysis.hidden_demand_insight || ''}</p>
                <div style="font-weight: 600; margin-bottom: 2px;">提案された切り口（クリックでテーマに適用）:</div>
                ${angles}
              `;
            }
            this.showToast('隠れ需要と多角的な切り口を発掘しました！', 'success');
          }
        } catch (e) {
          this.showToast('リサーチ失敗: ' + e.message, 'error');
        } finally {
          btnLongOutlier.disabled = false;
          btnLongOutlier.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> リサーチ（外れ値・隠れ需要）';
        }
      });
    }

    // 長尺動画: 海外ビジネス洋書を日本の職場に翻案
    const btnLongAdapt = document.getElementById('btnLongVideoAdaptBook');
    if (btnLongAdapt) {
      btnLongAdapt.addEventListener('click', async () => {
        const theme = document.getElementById('inputLongVideoTheme').value.trim();
        if (!theme) return this.showToast('翻案したい海外書籍や理論（例: ナッジ理論、心理的安全性、選択の科学等）を入力してください', 'error');

        btnLongAdapt.disabled = true;
        btnLongAdapt.innerHTML = '<span class="btn-spinner"></span><span>日本の職場ストーリーへ翻案中...</span>';
        this.showToast('洋書知見を行動経済学と日本の職場カルチャーへ翻案中...', 'info');

        try {
          const res = await window.apiClient.adaptWesternBook(theme);
          if (res.success && res.adaptation) {
            const ad = res.adaptation;
            if (longOutlierArea) longOutlierArea.style.display = 'block';
            if (longOutlierTitle) longOutlierTitle.textContent = `洋書翻案ストーリー: ${ad.japanese_adaptation_title || '日本の職場カルチャー翻案'}`;
            if (longOutlierContent) {
              const arc = ad.story_arc || {};
              longOutlierContent.innerHTML = `
                <p style="margin: 0 0 4px 0;"><strong>舞台設定:</strong> ${ad.workplace_setting || ''}</p>
                <div style="font-size: 0.8rem; line-height: 1.4;">
                  <div><strong>あるある危機:</strong> ${arc.problem || ''}</div>
                  <div><strong>知見の翻訳:</strong> ${arc.theory_insight || ''}</div>
                  <div><strong>具体的行動:</strong> ${arc.concrete_action || ''}</div>
                  <div><strong>結果と成果:</strong> ${arc.climax_and_result || ''}</div>
                </div>
              `;
            }
            if (ad.japanese_adaptation_title) {
              document.getElementById('inputLongVideoTheme').value = `${ad.japanese_adaptation_title}\n【舞台】: ${ad.workplace_setting || ''}\n【翻案知見】: ${theme}`;
            }
            this.showToast('日本の職場カルチャーへの翻案が完了しました！', 'success');
          }
        } catch (e) {
          this.showToast('洋書翻案失敗: ' + e.message, 'error');
        } finally {
          btnLongAdapt.disabled = false;
          btnLongAdapt.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"></path><path d="M6 6h10"></path><path d="M6 10h10"></path></svg> 海外ビジネス洋書を日本の職場に翻案';
        }
      });
    }

    // 長尺動画: ファイル読み込み (.txt / .md / .json)
    const fileImportLong = document.getElementById('fileImportLongVideo');
    const rawScriptLong = document.getElementById('inputRawScriptLongVideo');
    if (fileImportLong && rawScriptLong) {
      fileImportLong.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (event) => {
          rawScriptLong.value = event.target?.result || '';
          this.showToast(`ファイル「${file.name}」を読み込みました`, 'info');
        };
        reader.readAsText(file);
      });
    }

    // 長尺動画: Google Drive 読み込み
    const btnDriveLong = document.getElementById('btnDriveImportLongVideo');
    if (btnDriveLong && rawScriptLong) {
      btnDriveLong.addEventListener('click', () => {
        const driveUrl = prompt('Google Driveファイルの公開リンクまたはテキストを入力してください:');
        if (driveUrl) {
          rawScriptLong.value = driveUrl;
          this.showToast('Driveデータをセットしました。「1. 台本作成」または「自前台本を変換」を押してください', 'info');
        }
      });
    }

    // 長尺動画: 当ツール標準フォーマット(15分)へ自動リライト
    const btnNormLong = document.getElementById('btnNormalizeLongVideoScript');
    if (btnNormLong && rawScriptLong) {
      btnNormLong.addEventListener('click', async () => {
        const text = rawScriptLong.value.trim();
        if (!text) return this.showToast('リライトする自前の台本・小説・外部資料を入力してください', 'error');

        const genre = document.getElementById('inputLongVideoGenre')?.value || 'story';
        const visualStyle = document.getElementById('inputLongVideoVisualStyle')?.value || 'anime_modern';
        const origHtml = btnNormLong.innerHTML;
        btnNormLong.disabled = true;
        btnNormLong.classList.add('is-loading');
        btnNormLong.innerHTML = '<span class="btn-spinner"></span><span>15分全5章へ自動リライト中...</span>';

        this.showToast('自前台本を長尺全5章カット割りフォーマットへリライト中...', 'info');
        try {
          const res = await window.apiClient.normalizeScript(text, 'long_video', genre, visualStyle);
          if (res.success && res.timeline) {
            res.timeline.visual_style = visualStyle;
            const jsonText = JSON.stringify(res.timeline, null, 2);
            document.getElementById('inputLongVideoScriptJson').value = jsonText;
            localStorage.setItem('kimidori_draft_long_video_script', jsonText);
            longScriptArea.style.display = 'block';
            updateLongVideoBgmTags(res.timeline);
            if (refreshLongVideoTelop) refreshLongVideoTelop();
            this.showToast('長尺標準フォーマットへのリライトが完了しました！', 'success');
            longScriptArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        } catch (e) {
          this.showToast('台本リライト失敗: ' + e.message, 'error');
        } finally {
          btnNormLong.disabled = false;
          btnNormLong.classList.remove('is-loading');
          btnNormLong.innerHTML = origHtml;
        }
      });
    }

    if (btnGenLong) {
      btnGenLong.addEventListener('click', async () => {
        const jsonStr = document.getElementById('inputLongVideoScriptJson').value.trim();
        if (!jsonStr) return this.showToast("まずは「1. 台本作成」ボタンを押して台本を作成してください", "error");

        let scriptData;
        try {
          scriptData = JSON.parse(jsonStr);
        } catch (e) {
          return this.showToast("JSON形式が不正です: " + e.message, "error");
        }

        const visualStyle = document.getElementById('inputLongVideoVisualStyle')?.value || scriptData.visual_style || 'anime_modern';
        scriptData.visual_style = visualStyle;

        const ttsEngine = document.getElementById('longVideoTtsEngine')?.value || window.settingsManager.get('ttsEngine') || 'edge';
        const voiceName = document.getElementById('longVideoVoiceName')?.value || window.settingsManager.get('voiceName') || 'nanami';
        const speakingRate = document.getElementById('longVideoSpeakingRate')?.value || window.settingsManager.get('speakingRate') || '1.0';
        const telopStyle = document.getElementById('longVideoTelopStyle')?.value || 'shorts_impact_yellow';
        const telopMode = document.getElementById('longVideoTelopMode')?.value || 'sequential';
        const telopFontSize = document.getElementById('longVideoTelopFontSize')?.value || 'medium';
        const telopFont = document.getElementById('longVideoTelopFont')?.value || 'keifont';
        const bgmChoice = document.getElementById('longVideoBgmSelect')?.value || 'auto_script';
        const bgmVolume = (parseInt(document.getElementById('longVideoBgmVolume')?.value || '20', 10)) / 100;
        const comicColorMode = document.getElementById('longVideoComicColorMode')?.value || 'color';
        const comicBubbleDelay = parseFloat(document.getElementById('longVideoComicBubbleDelay')?.value || '0.4');
        const isComicStyle = visualStyle === 'comic_manga' || visualStyle === 'comic_manga_mono';
        const characterTraits = collectLongVideoCharacterTraits();

        const videoOptions = {
          visualStyle: visualStyle,
          speakingRate: speakingRate,
          telopStyle: telopStyle,
          telopMode: isComicStyle ? 'comic_bubble' : telopMode,
          telopFontSize: telopFontSize,
          telopFont: telopFont,
          bgmChoice: bgmChoice,
          bgmVolume: bgmVolume,
          customReferenceImages: this.longVideoRefImages && this.longVideoRefImages.length > 0 ? this.longVideoRefImages : null,
          videoMode: 'long_video',
          comicColorMode: comicColorMode,
          comicBubbleEnabled: isComicStyle,
          comicBubbleDelay: isNaN(comicBubbleDelay) ? 0.4 : comicBubbleDelay,
          characterTraits: characterTraits.length > 0 ? characterTraits : null
        };

        localStorage.setItem('kimidori_draft_long_video_script', jsonStr);

        const origGenHtml = btnGenLong.innerHTML;
        btnGenLong.disabled = true;
        btnGenLong.classList.add('is-loading');
        btnGenLong.innerHTML = '<span class="btn-spinner"></span><span>サーバー通信・ジョブ登録中...</span>';

        this.showToast(`長尺ハイブリッド動画（スタイル: ${visualStyle === 'ukiyoe' ? '本格浮世絵・錦絵' : (isComicStyle ? 'ビジネス漫画風・セリフ後出し' : visualStyle)}）の生成を開始しました`, "info");

        const progArea = document.getElementById('longVideoProgressArea');
        const titleEl = document.getElementById('longVideoProgressStatusTitle');
        const fillEl = document.getElementById('longVideoProgressFill');
        const msgEl = document.getElementById('longVideoProgressMessage');
        const resEl = document.getElementById('longVideoResult');
        const previewEl = document.getElementById('longVideoPreview');
        const downloadBtn = document.getElementById('btnDownloadLongVideo');

        const percentEl = document.getElementById('longVideoProgressPercent');
        const stepperLineLong = document.getElementById('stepperLineLong');
        const execLogsLong = document.getElementById('execLogsLong');
        const scenesGridAreaLong = document.getElementById('scenesGridAreaLong');
        const scenesTableLong = document.getElementById('scenesTableLong');
        const scenesCountLabelLong = document.getElementById('scenesCountLabelLong');

        if (progArea) {
          progArea.style.display = 'block';
          if (titleEl) titleEl.textContent = "ジョブ発行・合成準備中...";
          if (fillEl) fillEl.style.width = "5%";
          if (percentEl) percentEl.textContent = "5%";
          if (msgEl) msgEl.textContent = "サーバーにジョブをリクエストしています...";
          progArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        // ステッパーとログコンソールの更新処理
        const updateLongVideoStepperAndLogs = (job, currentJobId) => {
          const currentStep = job.step || 1;
          const progress = job.progress || 5;

          if (percentEl) percentEl.textContent = `${progress}%`;
          if (fillEl) fillEl.style.width = `${progress}%`;
          if (titleEl) titleEl.textContent = job.message || "長尺動画を生成中...";
          if (msgEl) msgEl.textContent = job.step_label || (job.message || "処理中...");

          if (stepperLineLong) {
            const linePct = Math.min(100, Math.max(0, (currentStep - 1) * 25));
            stepperLineLong.style.width = `${linePct}%`;
          }

          for (let s = 1; s <= 5; s++) {
            const stepNode = document.getElementById(`stepLong${s}`);
            if (!stepNode) continue;
            stepNode.classList.remove('active', 'completed');
            if (s < currentStep) {
              stepNode.classList.add('completed');
            } else if (s === currentStep) {
              stepNode.classList.add('active');
            }
          }

          if (execLogsLong && Array.isArray(job.logs) && job.logs.length > 0) {
            execLogsLong.innerHTML = job.logs.map(logLine => {
              let badgeType = "info";
              let badgeText = "LOG";
              if (logLine.includes("Step 1") || logLine.includes("タイムライン")) { badgeType = "step"; badgeText = "TIMELINE"; }
              else if (logLine.includes("Step 2") || logLine.includes("アセット")) { badgeType = "step"; badgeText = "ASSET"; }
              else if (logLine.includes("Step 3") || logLine.includes("演出")) { badgeType = "accent"; badgeText = "EFFECT"; }
              else if (logLine.includes("Step 4") || logLine.includes("BGM")) { badgeType = "accent"; badgeText = "BGM"; }
              else if (logLine.includes("Step 5") || logLine.includes("確定")) { badgeType = "success"; badgeText = "RENDER"; }
              else if (logLine.includes("ERROR")) { badgeType = "error"; badgeText = "ERROR"; }

              return `
                <div class="log-line">
                  <span class="log-badge ${badgeType}">${badgeText}</span>
                  <span class="log-text">${logLine}</span>
                </div>
              `;
            }).join('');
            execLogsLong.scrollTop = execLogsLong.scrollHeight;
          }

          if (Array.isArray(job.scenes) && job.scenes.length > 0) {
            if (scenesGridAreaLong) scenesGridAreaLong.style.display = 'block';
            if (scenesCountLabelLong) scenesCountLabelLong.textContent = `全 ${job.scenes.length} カット`;
            if (scenesTableLong) {
              scenesTableLong.innerHTML = job.scenes.map(sc => {
                const scId = sc.scene_id;
                const scType = sc.type === "video" ? "動画 (AI)" : "静止画 (Ken Burns)";
                const scTypeBadge = sc.type === "video" 
                  ? `<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: var(--accent-primary); border: 1px solid var(--accent-primary); font-size: 0.72rem;">${scType}</span>`
                  : `<span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-muted); font-size: 0.72rem;">${scType}</span>`;

                let statusBadge = `<span class="badge" style="background: rgba(255,255,255,0.1); color: var(--text-muted); font-size: 0.72rem;">待機中</span>`;
                if (sc.status === "generated") {
                  statusBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.25); color: #10b981; font-size: 0.72rem;">生成済</span>`;
                } else if (sc.status === "failed") {
                  statusBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.25); color: #ef4444; font-size: 0.72rem;">要再生成</span>`;
                }

                const previewText = sc.narration ? `${sc.speaker}: ${sc.narration}` : (sc.description || "");

                return `
                  <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.5rem 0.75rem; font-weight: 600; color: var(--accent-primary);">Cut #${scId}</td>
                    <td style="padding: 0.5rem 0.75rem;">${scTypeBadge}</td>
                    <td style="padding: 0.5rem 0.75rem;">${statusBadge}</td>
                    <td style="padding: 0.5rem 0.75rem; color: var(--text-secondary); max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${previewText}">
                      ${previewText}
                    </td>
                    <td style="padding: 0.5rem 0.75rem; text-align: center;">
                      <button class="btn btn-outline" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;" onclick="window.appController.triggerSceneRegenerate('${currentJobId}', ${scId})">
                        再生成
                      </button>
                    </td>
                  </tr>
                `;
              }).join('');
            }
          }
        };

        try {
          const res = await window.apiClient.generateMangaVideo(scriptData, ttsEngine, voiceName, {}, videoOptions);
          const jobId = res.job_id;
          this.currentLongVideoJobId = jobId;
          localStorage.setItem('kimidori_last_long_video_job', jobId);

          this.startJobPolling(jobId, 'LONG_VIDEO', {
            onProgress: (job) => {
              updateLongVideoStepperAndLogs(job, jobId);
            },
            onComplete: (job) => {
              for (let s = 1; s <= 5; s++) {
                const stepNode = document.getElementById(`stepLong${s}`);
                if (stepNode) stepNode.classList.add('completed');
              }
              if (stepperLineLong) stepperLineLong.style.width = '100%';
              if (percentEl) percentEl.textContent = "100%";
              if (fillEl) fillEl.style.width = "100%";
              if (titleEl) titleEl.textContent = "長尺動画の作成が完了しました！";
              if (msgEl) msgEl.textContent = "高画質長尺動画のレンダリングが完了しました（保存済みストックにも自動保存されました）。";

              const downloadUrl = `${window.apiClient.baseUrl}/api/download/${jobId}?t=${Date.now()}`;
              if (resEl) resEl.style.display = 'block';
              if (previewEl) {
                previewEl.src = downloadUrl;
                previewEl.load();
              }
              if (downloadBtn) downloadBtn.href = `${window.apiClient.baseUrl}/api/download/${jobId}?download=1`;
              this.loadSavedVideoStock('long_video', false);
              btnGenLong.disabled = false;
              btnGenLong.classList.remove('is-loading');
              btnGenLong.innerHTML = origGenHtml;
              this.showToast("長尺動画の生成が完了しました！", "success");
            },
            onError: (err) => {
              if (titleEl) titleEl.textContent = "生成エラーが発生しました";
              if (msgEl) msgEl.textContent = err;
              btnGenLong.disabled = false;
              btnGenLong.classList.remove('is-loading');
              btnGenLong.innerHTML = origGenHtml;
              this.showToast(`動画生成エラー: ${err}`, "error");
            }
          });
        } catch (err) {
          this.showToast("長尺動画生成失敗: " + err.message, "error");
          btnGenLong.disabled = false;
          btnGenLong.classList.remove('is-loading');
          btnGenLong.innerHTML = origGenHtml;
          if (progArea) progArea.style.display = 'none';
        }
      });
    }

    // 長尺動画 リセットボタン
    document.getElementById('btnResetLongVideo')?.addEventListener('click', () => {
      const progArea = document.getElementById('longVideoProgressArea');
      if (progArea) progArea.style.display = 'none';
      const scriptArea = document.getElementById('longVideoScriptArea');
      if (scriptArea) scriptArea.style.display = 'none';
      const resEl = document.getElementById('longVideoResult');
      if (resEl) resEl.style.display = 'none';
      const prev = document.getElementById('longVideoPreview');
      if (prev) { prev.pause(); prev.removeAttribute('src'); }
      const themeInput = document.getElementById('inputLongVideoTheme');
      if (themeInput) { themeInput.value = ''; themeInput.focus(); }
      const jsonArea = document.getElementById('inputLongVideoScriptJson');
      if (jsonArea) jsonArea.value = '';
      localStorage.removeItem('kimidori_draft_long_video_script');

      const execLogsLong = document.getElementById('execLogsLong');
      if (execLogsLong) {
        execLogsLong.innerHTML = `
          <div class="log-line">
            <span class="log-badge info">STANDBY</span>
            <span class="log-text">待機中... ジョブが開始されるとリアルタイムログを表示します</span>
          </div>
        `;
      }
      const stepperLineLong = document.getElementById('stepperLineLong');
      if (stepperLineLong) stepperLineLong.style.width = '0%';
      for (let s = 1; s <= 5; s++) {
        const stepNode = document.getElementById(`stepLong${s}`);
        if (stepNode) {
          stepNode.classList.remove('active', 'completed');
          if (s === 1) stepNode.classList.add('active');
        }
      }
      const scenesGridAreaLong = document.getElementById('scenesGridAreaLong');
      if (scenesGridAreaLong) scenesGridAreaLong.style.display = 'none';
      const scenesTableLong = document.getElementById('scenesTableLong');
      if (scenesTableLong) scenesTableLong.innerHTML = '';

      this.showToast("最初から新しく作成する画面に戻りました（保存済みストックはそのまま保持されています）", "info");
    });

    // リファレンス画像アップロード＆保存済みストック更新＆「編集する」ボタンのイベント登録
    this.setupReferenceUploadControl('proShorts', 'fileRefImagesProShorts', 'inputRefLabelProShorts', 'btnClearRefImagesProShorts', 'proShortsRefGallery');
    this.setupReferenceUploadControl('longVideo', 'fileRefImagesLongVideo', 'inputRefLabelLongVideo', 'btnClearRefImagesLongVideo', 'longVideoRefGallery');

    document.getElementById('btnRefreshProShortsStock')?.addEventListener('click', () => {
      this.loadSavedVideoStock('pro_shorts', true);
    });
    document.getElementById('btnRefreshLongVideoStock')?.addEventListener('click', () => {
      this.loadSavedVideoStock('long_video', true);
    });

    document.getElementById('btnEditProShortsVideo')?.addEventListener('click', () => {
      if (!this.currentProShortsJobId) {
        return this.showToast('編集対象の動画ジョブが見つかりません。ストック一覧の「編集する」から開いてください。', 'error');
      }
      this.openProVideoEditor(this.currentProShortsJobId, 'pro_shorts');
    });
    document.getElementById('btnEditLongVideo')?.addEventListener('click', () => {
      if (!this.currentLongVideoJobId) {
        return this.showToast('編集対象の長尺動画ジョブが見つかりません。ストック一覧の「編集する」から開いてください。', 'error');
      }
      this.openProVideoEditor(this.currentLongVideoJobId, 'long_video');
    });
  }

  // =========================================================================
  // Phase 1: 内部用語サニタイズ / 自前台本(簡易ショート) / 動画編集スタジオ引き継ぎ
  // =========================================================================
  _sanitizeUserMessage(m) {
    if (typeof m !== 'string') return m;
    return m
      .replace(/https?:\/\/[^\s"'<>]*trycloudflare[^\s"'<>]*/gi, 'AI Core')
      .replace(/Google\s*Colab/gi, 'AI Core')
      .replace(/ComfyUI(\s*\/\s*LTX-Video)?/gi, 'AI Core')
      .replace(/LTX-Video/gi, 'AI動画エンジン')
      .replace(/trycloudflare(\.com)?/gi, '')
      .replace(/colab/gi, 'AI Core')
      .replace(/HTTP\s*5\d\d|\b50[234]\b/g, '一時的な通信エラー')
      .replace(/(port|ポート)\s*\d{4,5}/gi, '')
      .replace(/(localhost|127\.0\.0\.1):\d{4,5}/gi, 'AI Core');
  }

  initEditorHandoff() {
    // --- 簡易ショート: 自前台本の読込・Drive・リライト ---
    const rawSimple = document.getElementById('inputRawScriptSimple');
    document.getElementById('fileImportSimple')?.addEventListener('change', (e) => {
      const file = e.target.files?.[0];
      if (!file || !rawSimple) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        rawSimple.value = ev.target?.result || '';
        this.showToast(`ファイル「${file.name}」を読み込みました`, 'info');
      };
      reader.readAsText(file);
    });
    document.getElementById('btnDriveImportSimple')?.addEventListener('click', () => {
      const v = prompt('Google Driveファイルの公開リンクまたはテキストを入力してください:');
      if (v && rawSimple) {
        rawSimple.value = v;
        this.showToast('Driveデータをセットしました。「入力台本を標準フォーマットへリライト」を押してください', 'info');
      }
    });
    const btnNormSimple = document.getElementById('btnNormalizeSimpleScript');
    btnNormSimple?.addEventListener('click', async () => {
      const raw = (rawSimple?.value || '').trim();
      if (!raw) return this.showToast('リライトする自前の台本を入力してください', 'error');
      if (!window.settingsManager.hasGeminiKey()) return this.showToast('設定画面でGemini APIキーを登録してください', 'error');
      const theme = (document.getElementById('inputTheme')?.value || '').trim() || '自前台本';
      this.wizardState.theme = theme;
      this.wizardState.target = document.getElementById('inputTargetChannelA')?.value || '';
      const orig = btnNormSimple.innerHTML;
      btnNormSimple.disabled = true;
      btnNormSimple.classList.add('is-loading');
      btnNormSimple.innerHTML = '<span class="btn-spinner"></span><span>標準フォーマットへリライト中...</span>';
      try {
        const combined = `テーマ: ${theme}\n\n【自前台本（内容を尊重して標準フォーマットへリライト）】:\n${raw}`;
        const preview = await window.apiClient.getScriptPreview(combined, this.wizardState.style, this.wizardState.duration);
        if (!preview || !preview.script) throw new Error('台本データが取得できませんでした');
        this.wizardState.scriptData = preview.script;
        this.showStep(3);
        document.getElementById('scriptLoading').style.display = 'none';
        document.getElementById('scriptEditor').style.display = 'block';
        document.getElementById('inputScriptData').value = JSON.stringify(preview.script, null, 2);
        this.showToast('自前台本を標準フォーマットへリライトしました', 'success');
      } catch (err) {
        this.showToast('台本リライト失敗: ' + err.message, 'error');
      } finally {
        btnNormSimple.disabled = false;
        btnNormSimple.classList.remove('is-loading');
        btnNormSimple.innerHTML = orig;
      }
    });

    // --- Pro版ショート / 長尺: 動画編集スタジオへ引き継ぎ ---
    document.getElementById('btnStudioHandoffPro')?.addEventListener('click', () => this.openInEditorStudio('pro_shorts'));
    document.getElementById('btnStudioHandoffLong')?.addEventListener('click', () => this.openInEditorStudio('long_video'));

    // --- エディタ画面側の引き継ぎパネル ---
    document.querySelector('.nav-item[data-target="edit"]')?.addEventListener('click', () => this.renderEditorHandoffPanel());
    document.getElementById('btnHandoffOpenTimeline')?.addEventListener('click', () => {
      const h = this.getEditorHandoff();
      if (h) this.openProVideoEditor(h.job_id, h.mode);
    });
    document.getElementById('btnHandoffClear')?.addEventListener('click', () => {
      localStorage.removeItem('kimidori_editor_handoff');
      const v = document.getElementById('editorHandoffVideo');
      if (v) { v.pause(); v.removeAttribute('src'); }
      this.renderEditorHandoffPanel();
      this.showToast('引き継ぎを解除しました', 'info');
    });
    this.renderEditorHandoffPanel();
  }

  getEditorHandoff() {
    try { return JSON.parse(localStorage.getItem('kimidori_editor_handoff') || 'null'); } catch (_) { return null; }
  }

  renderEditorHandoffPanel() {
    const panel = document.getElementById('editorHandoffPanel');
    const divider = document.getElementById('editorHandoffDivider');
    if (!panel) return;
    const h = this.getEditorHandoff();
    if (!h || !h.job_id) {
      panel.style.display = 'none';
      if (divider) divider.style.display = 'none';
      return;
    }
    panel.style.display = 'block';
    if (divider) divider.style.display = 'block';
    const video = document.getElementById('editorHandoffVideo');
    if (video && h.video_url && video.dataset.src !== h.video_url) {
      video.src = `${h.video_url}?t=${Date.now()}`;
      video.dataset.src = h.video_url;
    }
    const modeLabel = h.mode === 'long_video' ? '長尺動画' : 'Pro版ショート動画';
    const meta = document.getElementById('editorHandoffMeta');
    if (meta) meta.textContent = `${modeLabel} / ${(h.telops || []).length} カット`;
    const audioCount = (h.audio_tracks || []).filter(a => a.audio_url).length;
    const telopCount = (h.telops || []).filter(t => (t.telop_text || '').trim()).length;
    const sum = document.getElementById('editorHandoffSummary');
    if (sum) {
      sum.innerHTML = `動画: 1本 / ナレーション音声: ${audioCount}トラック / テロップ: ${telopCount}件`;
    }
  }

  async openInEditorStudio(mode) {
    if (window.settingsManager && !window.settingsManager.canUseStudio()) {
      return this.showToast('動画編集スタジオはProプラン以上（またはBYOGモード）限定の機能です。プランのアップグレードをご検討ください。', 'warning');
    }
    const jobId = mode === 'long_video' ? this.currentLongVideoJobId : this.currentProShortsJobId;
    if (!jobId) {
      return this.showToast('引き継ぐ動画が見つかりません。動画を生成するか、ストック一覧から動画を選択してください。', 'error');
    }
    const btn = document.getElementById(mode === 'long_video' ? 'btnStudioHandoffLong' : 'btnStudioHandoffPro');
    const orig = btn ? btn.innerHTML : null;
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner"></span><span>編集スタジオを準備中...</span>';
    }
    try {
      let editor = null;
      try {
        const r = await window.apiClient.getEditorState(jobId);
        editor = r && r.editor ? r.editor : null;
      } catch (_) {}
      const scenes = (editor && editor.scenes) || [];
      const base = window.apiClient.baseUrl;
      const handoff = {
        job_id: jobId,
        mode: mode,
        video_url: `${base}/api/download/${encodeURIComponent(jobId)}`,
        audio_tracks: scenes.map(s => ({ scene_id: s.scene_id, audio_url: s.audio_url || '' })),
        telops: scenes.map(s => ({
          scene_id: s.scene_id,
          telop_text: s.telop_text || s.narration || '',
          telop_font: s.telop_font,
          telop_style: s.telop_style,
          telop_y_pct: s.telop_y_pct,
          duration: s.duration
        })),
        bgm_choice: editor ? editor.bgm_choice : null,
        created_at: new Date().toISOString()
      };
      localStorage.setItem('kimidori_editor_handoff', JSON.stringify(handoff));
      const nav = document.querySelector('.nav-item[data-target="edit"]');
      if (nav) nav.click();
      this.renderEditorHandoffPanel();
      await this.openProVideoEditor(jobId, mode);
    } finally {
      if (btn) {
        btn.disabled = false;
        if (orig) btn.innerHTML = orig;
      }
    }
  }

  // --- タイムライン単体シーン再生成ハンドラ ---
  async triggerSceneRegenerate(jobId, sceneId) {
    if (!jobId || !sceneId) return;
    this.showToast(`Cut #${sceneId} の単体再生成を開始しました...`, "info");
    try {
      const res = await window.apiClient.regenerateTimelineScene(jobId, sceneId);
      if (res.success) {
        this.showToast(`Cut #${sceneId} の再生成が完了しました！`, "success");
      }
    } catch (err) {
      this.showToast(`Cut #${sceneId} 再生成エラー: ${err.message}`, "error");
    }
  }

  // =========================================================================
  // 1. ユーザー側リファレンス画像アップロード＆AIキャラ生成制御（Pro版ショート & 長尺動画共通）
  // =========================================================================
  setupReferenceUploadControl(modeKey, fileInputId, labelInputId, clearBtnId, galleryId) {
    const fileInput = document.getElementById(fileInputId);
    const labelInput = document.getElementById(labelInputId);
    const clearBtn = document.getElementById(clearBtnId);
    const gallery = document.getElementById(galleryId);
    if (!fileInput || !gallery) return;

    const getList = () => (modeKey === 'proShorts' ? this.proShortsRefImages : this.longVideoRefImages);
    const setList = (arr) => {
      if (modeKey === 'proShorts') {
        this.proShortsRefImages = arr;
      } else {
        this.longVideoRefImages = arr;
      }
    };

    const renderGallery = () => {
      const list = getList();
      if (!list || list.length === 0) {
        gallery.style.display = 'none';
        gallery.innerHTML = '';
        if (clearBtn) clearBtn.style.display = 'none';
        return;
      }
      gallery.style.display = 'grid';
      if (clearBtn) clearBtn.style.display = 'inline-flex';
      gallery.innerHTML = list.map((item, idx) => {
        const traitSummary = [item.clothing, item.hairstyle, item.appearance].filter(Boolean).join(' / ');
        return `
        <div class="ref-image-chip">
          <img src="${item.data_base64}" alt="${this._escapeHtml(item.name || '共通')}" />
          <div class="ref-image-chip-meta">
            <input type="text" class="form-input ref-chip-label-input" data-ref-idx="${idx}" value="${this._escapeHtml(item.name || '共通')}" title="対象キャラクター名または『共通』" style="padding: 2px 6px; font-size: 0.74rem; height: 24px;" />
            <span style="font-size: 0.68rem; color: #38bdf8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this._escapeHtml(traitSummary || item.filename || '')}">${this._escapeHtml(traitSummary || item.filename || 'reference.png')}</span>
          </div>
          <button type="button" class="ref-image-chip-remove" data-remove-idx="${idx}" title="このリファレンス画像を削除">&times;</button>
        </div>
      `;
      }).join('');

      gallery.querySelectorAll('.ref-chip-label-input').forEach(inp => {
        inp.addEventListener('change', (ev) => {
          const i = parseInt(ev.target.dataset.refIdx, 10);
          const arr = getList();
          if (arr[i]) {
            arr[i].name = ev.target.value.trim() || '共通';
          }
        });
      });

      gallery.querySelectorAll('.ref-image-chip-remove').forEach(btn => {
        btn.addEventListener('click', (ev) => {
          const i = parseInt(ev.currentTarget.dataset.removeIdx, 10);
          const arr = getList();
          arr.splice(i, 1);
          setList(arr);
          renderGallery();
        });
      });
    };

    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length === 0) return;
      const targetLabel = labelInput?.value?.trim() || '共通';
      const roleVal = modeKey === 'longVideo' ? (document.getElementById('inputCharRoleLong')?.value?.trim() || '') : '';
      const clothVal = modeKey === 'longVideo' ? (document.getElementById('inputCharClothingLong')?.value?.trim() || '') : '';
      const hairVal = modeKey === 'longVideo' ? (document.getElementById('inputCharHairstyleLong')?.value?.trim() || '') : '';
      const appVal = modeKey === 'longVideo' ? (document.getElementById('inputCharAppearanceLong')?.value?.trim() || '') : '';
      const arr = getList();

      for (const file of files) {
        if (!file.type.startsWith('image/')) continue;
        if (arr.length >= 8) {
          this.showToast('リファレンス画像は最大8枚まで登録できます', 'info');
          break;
        }
        const dataUrl = await new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = (ev) => resolve(ev.target?.result || '');
          reader.readAsDataURL(file);
        });
        if (dataUrl) {
          arr.push({
            name: targetLabel,
            role: roleVal,
            clothing: clothVal,
            hairstyle: hairVal,
            appearance: appVal,
            filename: file.name,
            data_base64: dataUrl
          });
        }
      }
      setList(arr);
      fileInput.value = '';
      renderGallery();
      this.showToast(`リファレンス画像（${targetLabel}）と固定特徴を登録しました。全シーンの一貫性基準として使用します。`, 'success');
    });

    if (modeKey === 'longVideo') {
      const btnAiChar = document.getElementById('btnGenerateAiCharLong');
      if (btnAiChar) {
        btnAiChar.addEventListener('click', async () => {
          const nameVal = labelInput?.value?.trim() || '主人公・佐藤';
          const roleVal = document.getElementById('inputCharRoleLong')?.value?.trim() || '主人公（28歳・IT企業企画職）';
          const clothVal = document.getElementById('inputCharClothingLong')?.value?.trim() || '濃紺のビジネススーツ、水色のネクタイ';
          const hairVal = document.getElementById('inputCharHairstyleLong')?.value?.trim() || '黒髪ショートマッシュ';
          const appVal = document.getElementById('inputCharAppearanceLong')?.value?.trim() || '知的で親しみやすい表情、清潔感のある容姿';
          const vStyle = document.getElementById('inputLongVideoVisualStyle')?.value || 'comic_manga';
          const colorMode = document.getElementById('longVideoComicColorMode')?.value || 'color';

          const origHtml = btnAiChar.innerHTML;
          btnAiChar.disabled = true;
          btnAiChar.classList.add('is-loading');
          btnAiChar.innerHTML = '<span class="btn-spinner"></span><span>AIキャラ生成中...</span>';
          this.showToast(`キャラクター「${nameVal}」の固定リファレンス画像をAI生成中...`, 'info');

          try {
            const res = await window.apiClient.generateCharacterRef({
              name: nameVal,
              role: roleVal,
              clothing: clothVal,
              hairstyle: hairVal,
              appearance: appVal,
              visualStyle: vStyle,
              colorMode: colorMode
            });
            if (res && res.success && res.character) {
              const ch = res.character;
              const arr = getList();
              const existIdx = arr.findIndex(x => x.name === ch.name);
              const entry = {
                name: ch.name || nameVal,
                role: ch.role || roleVal,
                clothing: ch.clothing || clothVal,
                hairstyle: ch.hairstyle || hairVal,
                appearance: ch.appearance || appVal,
                appearance_prompt_en: ch.appearance_prompt_en || '',
                filename: `ai_char_${Date.now()}.png`,
                data_base64: ch.image_base64
              };
              if (existIdx >= 0) {
                arr[existIdx] = entry;
              } else {
                arr.push(entry);
              }
              setList(arr);
              renderGallery();
              this.showToast(`AIキャラクター「${entry.name}」を生成し、全シーン固定リファレンスに登録しました！`, 'success');
            }
          } catch (err) {
            this.showToast('AIキャラクター生成エラー: ' + err.message, 'error');
          } finally {
            btnAiChar.disabled = false;
            btnAiChar.classList.remove('is-loading');
            btnAiChar.innerHTML = origHtml;
          }
        });
      }
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        setList([]);
        renderGallery();
        this.showToast('リファレンス画像をクリアしました', 'info');
      });
    }
  }

  // =========================================================================
  // 2. 保存済み動画ストック（最大5本保持）＆ リロード時の自動復元機構
  // =========================================================================
  async initSavedVideoStocksAndRestore() {
    // 1. ローカル保存されていた作成中台本JSONがあれば自動復元
    const savedProScript = localStorage.getItem('kimidori_draft_pro_shorts_script');
    if (savedProScript) {
      const proJsonEl = document.getElementById('inputProShortsScriptJson');
      const proAreaEl = document.getElementById('proShortsScriptArea');
      if (proJsonEl && !proJsonEl.value.trim()) {
        proJsonEl.value = savedProScript;
        if (proAreaEl) proAreaEl.style.display = 'block';
      }
    }

    const savedLongScript = localStorage.getItem('kimidori_draft_long_video_script');
    if (savedLongScript) {
      const longJsonEl = document.getElementById('inputLongVideoScriptJson');
      const longAreaEl = document.getElementById('longVideoScriptArea');
      if (longJsonEl && !longJsonEl.value.trim()) {
        longJsonEl.value = savedLongScript;
        if (longAreaEl) longAreaEl.style.display = 'block';
      }
    }

    // 2. Pro版ショート・長尺それぞれの保存済みストック（最大5本）をロードし、最新完成動画をプレイヤーにも自動セット
    await Promise.allSettled([
      this.loadSavedVideoStock('pro_shorts', false, true),
      this.loadSavedVideoStock('long_video', false, true)
    ]);
  }

  async loadSavedVideoStock(mode = 'pro_shorts', showNotification = false, autoRestoreLatest = false) {
    const isProShorts = mode === 'pro_shorts';
    const listEl = document.getElementById(isProShorts ? 'proShortsSavedStockList' : 'longVideoSavedStockList');
    const badgeEl = document.getElementById(isProShorts ? 'proShortsStockCountBadge' : 'longVideoStockCountBadge');
    if (!listEl) return;

    try {
      const res = await window.apiClient.listSavedVideos(mode, 5);
      let items = res.videos || [];
      // もし該当モードが0件の場合は、全モードの完成動画ストック（最大5本）をフォールバック表示して見失いを防止
      if (items.length === 0) {
        const allRes = await window.apiClient.listSavedVideos(null, 5);
        items = allRes.videos || [];
      }

      if (badgeEl) {
        badgeEl.textContent = `${items.length} / 5本 保存済`;
      }

      if (items.length === 0) {
        listEl.innerHTML = `
          <div style="grid-column: 1 / -1; padding: 0.75rem 1rem; border-radius: 8px; background: rgba(15, 23, 42, 0.55); border: 1px dashed rgba(148, 163, 184, 0.25); color: var(--text-secondary); font-size: 0.82rem;">
            まだ完成した保存済み動画はありません。動画を生成するとここに最大5本まで自動保存され、リロードしてもいつでも再生・MP4保存・タイムライン編集が可能です。
          </div>
        `;
        return;
      }

      const baseUrl = window.apiClient.baseUrl;
      listEl.innerHTML = items.map((v, idx) => {
        const thumbUrl = v.thumbnail_url ? `${baseUrl}${v.thumbnail_url}` : '';
        const dlUrl = `${baseUrl}/api/download/${encodeURIComponent(v.job_id)}?download=1`;
        const durLabel = v.duration_sec ? `${parseFloat(v.duration_sec).toFixed(1)}秒` : '--秒';
        const sizeLabel = v.file_size_mb ? `${v.file_size_mb}MB` : '';
        const styleLabel = v.visual_style === 'ukiyoe' ? '本格浮世絵' : (v.visual_style || 'Pro');
        const dateStr = v.created_at ? v.created_at.replace('T', ' ').slice(5, 16) : '';

        return `
          <div class="saved-stock-item-card" data-job-id="${this._escapeHtml(v.job_id)}">
            <div class="saved-stock-thumb-wrap" onclick="window.appController.loadStockVideoIntoPlayer('${mode}', '${v.job_id}')">
              ${thumbUrl
                ? `<img src="${thumbUrl}" alt="thumb" loading="lazy" onerror="this.style.display='none'" />`
                : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:0.75rem;color:#64748b;">PREVIEW</div>`
              }
              <span class="saved-stock-badge-num">#${idx + 1}</span>
              <span class="saved-stock-badge-dur">${durLabel}</span>
            </div>
            <div class="saved-stock-body">
              <div class="saved-stock-title" title="${this._escapeHtml(v.title || '無題の動画')}">${this._escapeHtml(v.title || '完成動画')}</div>
              <div class="saved-stock-meta">
                <span>${this._escapeHtml(styleLabel)}</span>
                <span>・全${v.scene_count || 0}カット</span>
                ${sizeLabel ? `<span>・${sizeLabel}</span>` : ''}
                ${dateStr ? `<span>・${dateStr}</span>` : ''}
              </div>
              <div class="saved-stock-actions">
                <button type="button" class="btn btn-outline" style="padding: 0.3rem 0.55rem; font-size: 0.74rem;" onclick="window.appController.loadStockVideoIntoPlayer('${mode}', '${v.job_id}')">再生・表示</button>
                <button type="button" class="btn btn-primary" style="padding: 0.3rem 0.65rem; font-size: 0.74rem; background: linear-gradient(135deg, #00d2ff 0%, #0284c7 100%); border-color: #38bdf8; color: #fff; font-weight: 700;" onclick="window.appController.openProVideoEditor('${v.job_id}', '${mode}')">編集する</button>
                <a href="${dlUrl}" download="${this._escapeHtml((v.title || 'video').slice(0, 24))}.mp4" class="btn btn-outline" style="padding: 0.3rem 0.55rem; font-size: 0.74rem; border-color: var(--accent-primary); color: var(--accent-primary);">MP4保存</a>
                <button type="button" class="btn btn-text" style="padding: 0.25rem 0.4rem; font-size: 0.72rem; color: #f87171; margin-left: auto;" onclick="window.appController.deleteStockVideo('${mode}', '${v.job_id}')" title="ストック一覧から削除">削除</button>
              </div>
            </div>
          </div>
        `;
      }).join('');

      // リロード時、直近の完成動画を自動的にプレイヤー枠へ復元表示（消えない仕様の徹底）
      if (autoRestoreLatest && items.length > 0) {
        const targetJobId = (isProShorts ? this.currentProShortsJobId : this.currentLongVideoJobId) || items[0].job_id;
        const matched = items.find(it => it.job_id === targetJobId) || items[0];
        if (matched) {
          this.loadStockVideoIntoPlayer(mode, matched.job_id, true);
        }
      }

      if (showNotification) {
        this.showToast(`保存済み動画ストック（${items.length}本）を更新しました`, 'info');
      }
    } catch (err) {
      console.warn('保存済み動画ストック読み込みエラー:', err);
      if (badgeEl) badgeEl.textContent = '0 / 5本';
    }
  }

  async loadStockVideoIntoPlayer(mode, jobId, silent = false) {
    if (!jobId) return;
    const isProShorts = mode === 'pro_shorts';
    const baseUrl = window.apiClient.baseUrl;
    const streamUrl = `${baseUrl}/api/download/${encodeURIComponent(jobId)}?t=${Date.now()}`;
    const dlUrl = `${baseUrl}/api/download/${encodeURIComponent(jobId)}?download=1`;

    if (isProShorts) {
      this.currentProShortsJobId = jobId;
      localStorage.setItem('kimidori_last_pro_shorts_job', jobId);
      const progArea = document.getElementById('proShortsProgressArea');
      const titleEl = document.getElementById('proShortsProgressTitle');
      const fillEl = document.getElementById('proShortsProgressFill');
      const msgEl = document.getElementById('proShortsProgressMsg');
      const resEl = document.getElementById('proShortsVideoResult');
      const previewEl = document.getElementById('proShortsVideoPreview');
      const dlBtn = document.getElementById('btnDownloadProShorts');

      if (progArea) progArea.style.display = 'block';
      if (titleEl) titleEl.textContent = '保存済みストック動画を読み込みました（再生・編集・保存が可能）';
      if (fillEl) fillEl.style.width = '100%';
      if (msgEl) msgEl.textContent = `Job ID: ${jobId}`;
      if (resEl) resEl.style.display = 'block';
      if (previewEl) {
        previewEl.src = streamUrl;
        previewEl.load();
      }
      if (dlBtn) dlBtn.href = dlUrl;
      if (!silent && resEl) {
        resEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        this.showToast('ストック動画をプレイヤーに読み込みました。「編集する」でタイムライン編集も可能です。', 'success');
      }
    } else {
      this.currentLongVideoJobId = jobId;
      localStorage.setItem('kimidori_last_long_video_job', jobId);
      const progArea = document.getElementById('longVideoProgressArea');
      const titleEl = document.getElementById('longVideoProgressStatusTitle');
      const percentEl = document.getElementById('longVideoProgressPercent');
      const fillEl = document.getElementById('longVideoProgressFill');
      const msgEl = document.getElementById('longVideoProgressMessage');
      const resEl = document.getElementById('longVideoResult');
      const previewEl = document.getElementById('longVideoPreview');
      const dlBtn = document.getElementById('btnDownloadLongVideo');

      if (progArea) progArea.style.display = 'block';
      if (titleEl) titleEl.textContent = '保存済みストック動画を読み込みました（再生・編集・保存が可能）';
      if (percentEl) percentEl.textContent = '100%';
      if (fillEl) fillEl.style.width = '100%';
      if (msgEl) msgEl.textContent = `Job ID: ${jobId} — 下のプレイヤーで再生、または「編集する」でカット・テロップ・音声・SEを編集できます。`;
      if (resEl) resEl.style.display = 'block';
      if (previewEl) {
        previewEl.src = streamUrl;
        previewEl.load();
      }
      if (dlBtn) dlBtn.href = dlUrl;
      if (!silent && resEl) {
        resEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        this.showToast('ストック動画をプレイヤーに読み込みました。「編集する」でタイムライン編集も可能です。', 'success');
      }
    }
  }

  async deleteStockVideo(mode, jobId) {
    if (!jobId) return;
    if (!confirm('この動画を保存済みストック一覧から削除しますか？')) return;
    try {
      await window.apiClient.deleteSavedVideo(jobId, false);
      this.showToast('保存済みストックから削除しました', 'info');
      await this.loadSavedVideoStock(mode, false);
    } catch (err) {
      this.showToast('削除エラー: ' + err.message, 'error');
    }
  }

  // =========================================================================
  // 3. Pro動画タイムライン編集スタジオ (Remotion / Filmcraft アーキテクチャ準拠)
  // =========================================================================
  initProVideoEditor() {
    const modal = document.getElementById('proVideoEditorModal');
    if (!modal) return;

    // 閉じるボタン
    document.getElementById('btnCloseProEditor')?.addEventListener('click', () => {
      this.stopEditorPlayback();
      modal.style.display = 'none';
    });

    // 4つのインスペクタータブ切り替え (1.テロップ / 2.ナレーション / 3.カット作業 / 4.効果音・BGM)
    modal.querySelectorAll('.pro-editor-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        modal.querySelectorAll('.pro-editor-tab').forEach(b => b.classList.remove('active'));
        tabBtn.classList.add('active');
        const tabKey = tabBtn.dataset.editorTab;
        const tabMap = {
          telop: 'editorTabTelop',
          narration: 'editorTabNarration',
          cut: 'editorTabCut',
          audio: 'editorTabAudio',
          studio: 'editorTabStudio',
          studio2: 'editorTabStudio2'
        };
        Object.values(tabMap).forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.display = 'none';
        });
        const activeEl = document.getElementById(tabMap[tabKey]);
        if (activeEl) activeEl.style.display = 'block';
      });
    });

    // プレビューモード切替（カット別ライブ編集 vs 完成MP4全体再生）
    const btnModeCut = document.getElementById('btnSwitchPreviewModeCut');
    const btnModeFull = document.getElementById('btnSwitchPreviewModeFullMp4');
    const liveStage = document.getElementById('editorLiveCutStage');
    const fullPlayer = document.getElementById('editorFullMp4Player');

    if (btnModeCut && btnModeFull) {
      btnModeCut.addEventListener('click', () => {
        if (fullPlayer) { fullPlayer.pause(); fullPlayer.style.display = 'none'; }
        if (liveStage) liveStage.style.display = 'block';
        btnModeCut.style.borderColor = '#00d2ff';
        btnModeCut.style.color = '#00d2ff';
        btnModeFull.style.borderColor = '';
        btnModeFull.style.color = '';
      });
      btnModeFull.addEventListener('click', () => {
        this.stopEditorPlayback();
        if (liveStage) liveStage.style.display = 'none';
        if (fullPlayer) {
          fullPlayer.style.display = 'block';
          if (this.editorJobId) {
            const mp4Url = `${window.apiClient.baseUrl}/api/download/${encodeURIComponent(this.editorJobId)}?t=${Date.now()}`;
            if (!fullPlayer.src || !fullPlayer.src.includes(this.editorJobId)) {
              fullPlayer.src = mp4Url;
            }
          }
        }
        btnModeFull.style.borderColor = '#00d2ff';
        btnModeFull.style.color = '#00d2ff';
        btnModeCut.style.borderColor = '';
        btnModeCut.style.color = '';
      });
    }

    // ステージ上のテロップ直接上下ドラッグ移動
    const draggableTelop = document.getElementById('editorDraggableTelopBox');
    const stageWrapper = document.getElementById('editorLiveCutStage');
    if (draggableTelop && stageWrapper) {
      let isDragging = false;
      const onPointerMove = (clientY) => {
        if (!isDragging) return;
        const rect = stageWrapper.getBoundingClientRect();
        if (rect.height <= 0) return;
        const relY = ((clientY - rect.top) / rect.height) * 100;
        const clampedPct = Math.round(Math.min(90, Math.max(10, relY)));
        draggableTelop.style.top = `${clampedPct}%`;
        const ySlider = document.getElementById('editorCutTelopYSlider');
        const yLabel = document.getElementById('editorTelopYLabel');
        if (ySlider) ySlider.value = String(clampedPct);
        if (yLabel) yLabel.textContent = `${clampedPct}%`;
        const cut = this.getActiveEditorCut();
        if (cut) {
          cut.telop_y_pct = clampedPct;
          this.renderEditorTimelineTracks();
        }
      };

      draggableTelop.addEventListener('mousedown', (e) => {
        isDragging = true;
        e.preventDefault();
      });
      window.addEventListener('mousemove', (e) => onPointerMove(e.clientY));
      window.addEventListener('mouseup', () => { isDragging = false; });

      draggableTelop.addEventListener('touchstart', () => { isDragging = true; }, { passive: true });
      window.addEventListener('touchmove', (e) => {
        if (isDragging && e.touches?.[0]) onPointerMove(e.touches[0].clientY);
      }, { passive: true });
      window.addEventListener('touchend', () => { isDragging = false; });
    }

    // --- Tab 1: テロップ設定イベント ---
    document.getElementById('editorCutTelopText')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.telop_text = e.target.value;
      this.updateEditorLiveStage();
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutTelopFont')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.telop_font = e.target.value;
      this.updateEditorLiveStage();
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutTelopStyle')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.telop_style = e.target.value;
      this.updateEditorLiveStage();
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutTelopYSlider')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      const pct = parseInt(e.target.value, 10) || 76;
      cut.telop_y_pct = pct;
      const yLabel = document.getElementById('editorTelopYLabel');
      if (yLabel) yLabel.textContent = `${pct}%`;
      this.updateEditorLiveStage();
      this.renderEditorTimelineTracks();
    });

    modal.querySelectorAll('.btn-telop-pos-preset').forEach(btn => {
      btn.addEventListener('click', () => {
        const pct = parseInt(btn.dataset.yPct, 10) || 76;
        const cut = this.getActiveEditorCut();
        if (!cut) return;
        cut.telop_y_pct = pct;
        const ySlider = document.getElementById('editorCutTelopYSlider');
        const yLabel = document.getElementById('editorTelopYLabel');
        if (ySlider) ySlider.value = String(pct);
        if (yLabel) yLabel.textContent = `${pct}%`;
        this.updateEditorLiveStage();
        this.renderEditorTimelineTracks();
      });
    });

    document.getElementById('editorCutTelopSizeKey')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.telop_font_size = e.target.value;
      this.updateEditorLiveStage();
    });

    document.getElementById('editorCutTelopScaleSlider')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      const sc = parseInt(e.target.value, 10) || 100;
      cut.telop_scale = sc;
      const scLabel = document.getElementById('editorTelopScaleLabel');
      if (scLabel) scLabel.textContent = `${sc}%`;
      this.updateEditorLiveStage();
    });

    document.getElementById('btnApplyTelopToAllCuts')?.addEventListener('click', () => {
      const cut = this.getActiveEditorCut();
      if (!cut || !this.editorState?.scenes) return;
      this.editorState.scenes.forEach(sc => {
        sc.telop_font = cut.telop_font;
        sc.telop_style = cut.telop_style;
        sc.telop_font_size = cut.telop_font_size;
        sc.telop_y_pct = cut.telop_y_pct;
        sc.telop_scale = cut.telop_scale;
      });
      this.editorState.global_telop_font = cut.telop_font;
      this.editorState.global_telop_style = cut.telop_style;
      this.editorState.global_telop_font_size = cut.telop_font_size;
      this.editorState.global_telop_y_pct = cut.telop_y_pct;
      this.editorState.global_telop_scale = cut.telop_scale;
      this.renderEditorTimelineTracks();
      this.showToast(`全 ${this.editorState.scenes.length} カットにテロップ書体・配色・位置(${cut.telop_y_pct}%)を一括適用しました`, 'success');
    });

    // --- Tab 2: ナレーション変更＆その場再合成イベント ---
    document.getElementById('editorCutSpeaker')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.speaker = e.target.value;
      const spkLabel = document.getElementById('editorActiveSpeakerLabel');
      if (spkLabel) spkLabel.textContent = cut.speaker || 'ナレーション';
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutNarration')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.narration = e.target.value;
      const syncCheck = document.getElementById('editorSyncTelopWithNarration');
      if (syncCheck && syncCheck.checked) {
        cut.telop_text = e.target.value;
        const telopInput = document.getElementById('editorCutTelopText');
        if (telopInput) telopInput.value = e.target.value;
        this.updateEditorLiveStage();
      }
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutTtsEngine')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (cut) cut.tts_engine = e.target.value;
    });

    document.getElementById('editorCutVoiceName')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (cut) cut.voice_name = e.target.value;
    });

    document.getElementById('editorCutSpeakingRate')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      const val = parseFloat(e.target.value) || 1.0;
      if (cut) cut.speaking_rate = val;
      const lbl = document.getElementById('editorCutRateLabel');
      if (lbl) lbl.textContent = `${val.toFixed(2)}x`;
    });

    const btnResynth = document.getElementById('btnEditorResynthesizeTts');
    if (btnResynth) {
      btnResynth.addEventListener('click', async () => {
        const cut = this.getActiveEditorCut();
        if (!cut || !this.editorJobId) return;
        const narration = (document.getElementById('editorCutNarration')?.value || cut.narration || '').trim();
        if (!narration) return this.showToast('ナレーションテキストを入力してください', 'error');

        const origHtml = btnResynth.innerHTML;
        btnResynth.disabled = true;
        btnResynth.innerHTML = '<span class="btn-spinner"></span><span>音声を再合成中...</span>';

        try {
          const res = await window.apiClient.resynthesizeCutTts(this.editorJobId, {
            sceneId: cut.scene_id,
            narration: narration,
            speaker: cut.speaker || 'ナレーション',
            ttsEngine: document.getElementById('editorCutTtsEngine')?.value || cut.tts_engine || 'edge',
            voiceName: document.getElementById('editorCutVoiceName')?.value || cut.voice_name || 'nanami',
            speakingRate: parseFloat(document.getElementById('editorCutSpeakingRate')?.value || cut.speaking_rate || 1.0)
          });
          if (res.success) {
            cut.audio_url = `${res.audio_url}?t=${Date.now()}`;
            cut.duration = res.duration;
            const durSlider = document.getElementById('editorCutDurationSlider');
            const durInput = document.getElementById('editorCutDurationInput');
            const durLabel = document.getElementById('editorCutDurationLabel');
            if (durSlider) durSlider.value = String(res.duration);
            if (durInput) durInput.value = String(res.duration);
            if (durLabel) durLabel.textContent = `${res.duration}s`;

            this.renderEditorTimelineTracks();
            this.updateEditorProjectHeader();
            const audioEl = document.getElementById('editorCutAudioEl');
            if (audioEl) {
              audioEl.src = `${window.apiClient.baseUrl}${cut.audio_url}`;
              audioEl.play().catch(() => {});
            }
            this.showToast(`Cut #${cut.scene_id} のナレーション音声を再合成しました（新尺: ${res.duration}秒）`, 'success');
          }
        } catch (err) {
          this.showToast('ナレーション再合成エラー: ' + err.message, 'error');
        } finally {
          btnResynth.disabled = false;
          btnResynth.innerHTML = origHtml;
        }
      });
    }

    // カスタム音声ファイル差替 (.mp3/.wav)
    document.getElementById('fileEditorCutAudioUpload')?.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      const cut = this.getActiveEditorCut();
      if (!file || !cut || !this.editorJobId) return;
      try {
        this.showToast(`Cut #${cut.scene_id} の音声ファイルをアップロード中...`, 'info');
        const res = await window.apiClient.uploadCutMedia(this.editorJobId, {
          sceneId: cut.scene_id,
          mediaType: 'audio',
          file: file
        });
        if (res.success) {
          cut.audio_url = `${res.asset_url}?t=${Date.now()}`;
          if (res.duration) cut.duration = res.duration;
          this.selectEditorCut(this.editorActiveCutIndex);
          this.renderEditorTimelineTracks();
          this.showToast(`Cut #${cut.scene_id} のナレーション音声を差し替えました`, 'success');
        }
      } catch (err) {
        this.showToast('音声ファイル差替失敗: ' + err.message, 'error');
      } finally {
        e.target.value = '';
      }
    });

    // --- Tab 3: カット作業（有効化・尺調整・トリミング・分割・複製・移動・削除・背景差替） ---
    document.getElementById('editorCutEnabledToggle')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.enabled = e.target.checked;
      this.renderEditorTimelineTracks();
      this.updateEditorProjectHeader();
    });

    const syncDurationChange = (val) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      const num = Math.max(0.5, Math.min(60.0, parseFloat(val) || 5.0));
      cut.duration = Math.round(num * 100) / 100;
      const sl = document.getElementById('editorCutDurationSlider');
      const inp = document.getElementById('editorCutDurationInput');
      const lbl = document.getElementById('editorCutDurationLabel');
      if (sl) sl.value = String(cut.duration);
      if (inp) inp.value = String(cut.duration);
      if (lbl) lbl.textContent = `${cut.duration.toFixed(1)}s`;
      this.renderEditorTimelineTracks();
      this.updateEditorProjectHeader();
    };

    document.getElementById('editorCutDurationSlider')?.addEventListener('input', (e) => syncDurationChange(e.target.value));
    document.getElementById('editorCutDurationInput')?.addEventListener('change', (e) => syncDurationChange(e.target.value));

    document.getElementById('editorCutTrimStartSlider')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      const trimVal = parseFloat(e.target.value) || 0.0;
      cut.trim_start = Math.round(trimVal * 10) / 10;
      const lbl = document.getElementById('editorCutTrimStartLabel');
      if (lbl) lbl.textContent = `${cut.trim_start.toFixed(1)}s`;
    });

    // カットを2分割
    document.getElementById('btnEditorSplitCut')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes;
      const idx = this.editorActiveCutIndex;
      if (!scenes || !scenes[idx]) return;
      const orig = scenes[idx];
      const halfDur = Math.max(1.0, Math.round((orig.duration / 2) * 10) / 10);
      const text = orig.narration || orig.telop_text || '';
      const mid = Math.ceil(text.length / 2);
      const firstText = text.slice(0, mid) || text;
      const secondText = text.slice(mid) || text;

      const cloned = JSON.parse(JSON.stringify(orig));
      orig.duration = halfDur;
      orig.narration = firstText;
      orig.telop_text = firstText;

      cloned.duration = halfDur;
      cloned.trim_start = Math.round(((orig.trim_start || 0) + halfDur) * 10) / 10;
      cloned.narration = secondText;
      cloned.telop_text = secondText;

      scenes.splice(idx + 1, 0, cloned);
      scenes.forEach((sc, i) => { sc.order = i + 1; });
      this.selectEditorCut(idx);
      this.renderEditorTimelineTracks();
      this.updateEditorProjectHeader();
      this.showToast(`Cut #${orig.scene_id} を前半・後半の2カットに分割しました`, 'success');
    });

    // カットを複製
    document.getElementById('btnEditorDuplicateCut')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes;
      const idx = this.editorActiveCutIndex;
      if (!scenes || !scenes[idx]) return;
      const cloned = JSON.parse(JSON.stringify(scenes[idx]));
      scenes.splice(idx + 1, 0, cloned);
      scenes.forEach((sc, i) => { sc.order = i + 1; });
      this.selectEditorCut(idx + 1);
      this.renderEditorTimelineTracks();
      this.updateEditorProjectHeader();
      this.showToast('カットを複製しました', 'info');
    });

    // 前のカットと入替
    document.getElementById('btnEditorMoveCutLeft')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes;
      const idx = this.editorActiveCutIndex;
      if (!scenes || idx <= 0) return;
      const tmp = scenes[idx - 1];
      scenes[idx - 1] = scenes[idx];
      scenes[idx] = tmp;
      scenes.forEach((sc, i) => { sc.order = i + 1; });
      this.selectEditorCut(idx - 1);
      this.renderEditorTimelineTracks();
    });

    // 次のカットと入替
    document.getElementById('btnEditorMoveCutRight')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes;
      const idx = this.editorActiveCutIndex;
      if (!scenes || idx >= scenes.length - 1) return;
      const tmp = scenes[idx + 1];
      scenes[idx + 1] = scenes[idx];
      scenes[idx] = tmp;
      scenes.forEach((sc, i) => { sc.order = i + 1; });
      this.selectEditorCut(idx + 1);
      this.renderEditorTimelineTracks();
    });

    // このカットを削除
    document.getElementById('btnEditorDeleteCut')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes;
      const idx = this.editorActiveCutIndex;
      if (!scenes || scenes.length <= 1) {
        return this.showToast('最低1カットは残す必要があります', 'error');
      }
      scenes.splice(idx, 1);
      scenes.forEach((sc, i) => { sc.order = i + 1; });
      const nextIdx = Math.min(idx, scenes.length - 1);
      this.selectEditorCut(nextIdx);
      this.renderEditorTimelineTracks();
      this.updateEditorProjectHeader();
      this.showToast('カットを削除しました', 'info');
    });

    // 背景画像・動画クリップの差し替えアップロード
    document.getElementById('fileEditorCutImageUpload')?.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      const cut = this.getActiveEditorCut();
      if (!file || !cut || !this.editorJobId) return;
      try {
        this.showToast(`Cut #${cut.scene_id} の背景画像をアップロード中...`, 'info');
        const res = await window.apiClient.uploadCutMedia(this.editorJobId, {
          sceneId: cut.scene_id,
          mediaType: 'image',
          file: file
        });
        if (res.success) {
          cut.image_url = `${res.asset_url}?t=${Date.now()}`;
          cut.clip_url = '';
          cut.type = 'image';
          this.updateEditorLiveStage();
          this.renderEditorTimelineTracks();
          this.showToast(`Cut #${cut.scene_id} の背景画像を差し替えました`, 'success');
        }
      } catch (err) {
        this.showToast('画像アップロードエラー: ' + err.message, 'error');
      } finally {
        e.target.value = '';
      }
    });

    document.getElementById('fileEditorCutVideoUpload')?.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      const cut = this.getActiveEditorCut();
      if (!file || !cut || !this.editorJobId) return;
      try {
        this.showToast(`Cut #${cut.scene_id} の動画クリップをアップロード中...`, 'info');
        const res = await window.apiClient.uploadCutMedia(this.editorJobId, {
          sceneId: cut.scene_id,
          mediaType: 'video',
          file: file
        });
        if (res.success) {
          cut.clip_url = `${res.asset_url}?t=${Date.now()}`;
          cut.type = 'video';
          this.updateEditorLiveStage();
          this.renderEditorTimelineTracks();
          this.showToast(`Cut #${cut.scene_id} の動画クリップを差し替えました`, 'success');
        }
      } catch (err) {
        this.showToast('動画アップロードエラー: ' + err.message, 'error');
      } finally {
        e.target.value = '';
      }
    });

    // --- Tab 4: 効果音（SE）追加 ＆ BGM変更 ---
    document.getElementById('editorCutSeSelect')?.addEventListener('change', (e) => {
      const cut = this.getActiveEditorCut();
      if (!cut) return;
      cut.se_id = e.target.value;
      this.renderEditorTimelineTracks();
    });

    document.getElementById('editorCutSeDelaySlider')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      const d = parseFloat(e.target.value) || 0.0;
      if (cut) cut.se_delay = d;
      const lbl = document.getElementById('editorCutSeDelayLabel');
      if (lbl) lbl.textContent = `${d.toFixed(1)}s`;
    });

    document.getElementById('editorCutSeVolumeSlider')?.addEventListener('input', (e) => {
      const cut = this.getActiveEditorCut();
      const pct = parseInt(e.target.value, 10) || 70;
      if (cut) cut.se_volume = pct / 100;
      const lbl = document.getElementById('editorCutSeVolumeLabel');
      if (lbl) lbl.textContent = `${pct}%`;
    });

    document.getElementById('btnEditorPreviewSe')?.addEventListener('click', () => {
      const seId = document.getElementById('editorCutSeSelect')?.value || 'none';
      if (!seId || seId === 'none') {
        return this.showToast('試聴する効果音（SE）を選択してください', 'info');
      }
      const seAudio = document.getElementById('editorCutSeAudioEl');
      if (seAudio) {
        seAudio.src = window.apiClient.getSeFileUrl(seId);
        const volPct = parseInt(document.getElementById('editorCutSeVolumeSlider')?.value || '70', 10);
        seAudio.volume = Math.min(1.0, Math.max(0.05, volPct / 100));
        seAudio.currentTime = 0;
        seAudio.play().catch(err => this.showToast('SE再生エラー: ' + err.message, 'error'));
      }
    });

    document.getElementById('fileEditorUploadCustomSe')?.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const res = await window.apiClient.uploadCustomSe(file);
        if (res.success && res.se) {
          const sel = document.getElementById('editorCutSeSelect');
          if (sel) {
            const opt = document.createElement('option');
            opt.value = res.se.se_id;
            opt.textContent = `${res.se.name} (カスタムSE)`;
            sel.appendChild(opt);
            sel.value = res.se.se_id;
          }
          const cut = this.getActiveEditorCut();
          if (cut) cut.se_id = res.se.se_id;
          this.renderEditorTimelineTracks();
          this.showToast(`カスタム効果音「${res.se.name}」を追加・設定しました`, 'success');
        }
      } catch (err) {
        this.showToast('カスタムSE追加エラー: ' + err.message, 'error');
      } finally {
        e.target.value = '';
      }
    });

    document.getElementById('editorGlobalBgmSelect')?.addEventListener('change', (e) => {
      if (this.editorState) this.editorState.bgm_choice = e.target.value;
    });

    document.getElementById('editorGlobalBgmVolSlider')?.addEventListener('input', (e) => {
      const pct = parseInt(e.target.value, 10) || 20;
      if (this.editorState) this.editorState.bgm_volume = pct / 100;
      const lbl = document.getElementById('editorGlobalBgmVolLabel');
      if (lbl) lbl.textContent = `${pct}%`;
      const bgmAudio = document.getElementById('editorBgmAudioEl');
      if (bgmAudio) bgmAudio.volume = Math.min(1.0, Math.max(0.02, pct / 100));
    });

    document.getElementById('btnEditorPreviewBgm')?.addEventListener('click', () => {
      const val = document.getElementById('editorGlobalBgmSelect')?.value || 'auto_script';
      const bgmAudio = document.getElementById('editorBgmAudioEl');
      if (!bgmAudio) return;
      if (val === 'none') {
        bgmAudio.pause();
        return this.showToast('「BGMなし」が選択されています', 'info');
      }
      if (!bgmAudio.paused) {
        bgmAudio.pause();
        return this.showToast('BGM試聴を停止しました', 'info');
      }
      let presetId = 'edo_ukiyoe';
      if (val.startsWith('builtin:')) {
        presetId = val;
      } else if (this.editorState?.visual_style !== 'ukiyoe') {
        presetId = 'corporate_clean';
      }
      bgmAudio.src = window.apiClient.getBuiltinBgmPreviewUrl(presetId);
      const pct = parseInt(document.getElementById('editorGlobalBgmVolSlider')?.value || '20', 10);
      bgmAudio.volume = Math.min(1.0, Math.max(0.05, pct / 100));
      bgmAudio.play().catch(err => this.showToast('BGM再生失敗: ' + err.message, 'error'));
      this.showToast('BGMを試聴再生中（もう一度押すと停止）', 'info');
    });

    // --- トランスポート操作（前後のカット移動・カット再生） ---
    document.getElementById('btnEditorPrevCut')?.addEventListener('click', () => {
      if (this.editorActiveCutIndex > 0) {
        this.selectEditorCut(this.editorActiveCutIndex - 1);
      }
    });
    document.getElementById('btnEditorNextCut')?.addEventListener('click', () => {
      const scenes = this.editorState?.scenes || [];
      if (this.editorActiveCutIndex < scenes.length - 1) {
        this.selectEditorCut(this.editorActiveCutIndex + 1);
      }
    });
    document.getElementById('btnEditorPlayPauseCut')?.addEventListener('click', () => {
      this.playPauseEditorCut();
    });

    // --- 一時保存 ＆ MP4再書き出し ---
    const btnSaveDraft = document.getElementById('btnEditorSaveDraft');
    if (btnSaveDraft) {
      btnSaveDraft.addEventListener('click', async () => {
        if (!this.editorJobId || !this.editorState) return;
        btnSaveDraft.disabled = true;
        try {
          await window.apiClient.saveEditorState(this.editorJobId, this.editorState);
          this.showToast('タイムライン編集状態を保存しました', 'success');
        } catch (err) {
          this.showToast('一時保存エラー: ' + err.message, 'error');
        } finally {
          btnSaveDraft.disabled = false;
        }
      });
    }

    const btnRenderFinal = document.getElementById('btnEditorRenderFinal');
    if (btnRenderFinal) {
      btnRenderFinal.addEventListener('click', async () => {
        if (!this.editorJobId || !this.editorState) return;
        this.stopEditorPlayback();

        const banner = document.getElementById('editorRenderStatusBanner');
        const bannerText = document.getElementById('editorRenderStatusText');
        const origHtml = btnRenderFinal.innerHTML;
        btnRenderFinal.disabled = true;
        btnRenderFinal.innerHTML = '<span class="btn-spinner"></span><span>FFmpeg再書き出し中...</span>';
        if (banner) banner.style.display = 'flex';
        if (bannerText) bannerText.textContent = '編集内容（テロップ・ナレーション・カット尺・SE・BGM）を反映してMP4を再レンダリングしています...';

        try {
          const res = await window.apiClient.renderEditedTimeline(this.editorJobId, this.editorState);
          if (res.success) {
            const newMp4Url = `${window.apiClient.baseUrl}/api/download/${encodeURIComponent(this.editorJobId)}?t=${Date.now()}`;
            const dlMp4Url = `${window.apiClient.baseUrl}/api/download/${encodeURIComponent(this.editorJobId)}?download=1`;

            const dlBtn = document.getElementById('btnEditorDownloadMp4');
            if (dlBtn) dlBtn.href = dlMp4Url;

            // 全体再生プレイヤーへ切替えて即座に確認可能にする
            const fullPlayer = document.getElementById('editorFullMp4Player');
            const liveStage = document.getElementById('editorLiveCutStage');
            if (liveStage) liveStage.style.display = 'none';
            if (fullPlayer) {
              fullPlayer.style.display = 'block';
              fullPlayer.src = newMp4Url;
              fullPlayer.load();
              fullPlayer.play().catch(() => {});
            }

            // 元の画面のプレイヤーと5本ストックも同期更新
            await this.loadStockVideoIntoPlayer(this.editorSourceMode || 'pro_shorts', this.editorJobId, true);
            await this.loadSavedVideoStock('pro_shorts', false);
            await this.loadSavedVideoStock('long_video', false);

            this.showToast('編集内容を反映した新しいMP4動画の書き出しが完了しました！', 'success');
          }
        } catch (err) {
          this.showToast('再書き出しエラー: ' + err.message, 'error');
        } finally {
          btnRenderFinal.disabled = false;
          btnRenderFinal.innerHTML = origHtml;
          if (banner) banner.style.display = 'none';
        }
      });
    }
  }

  async openProVideoEditor(jobId, sourceMode = 'pro_shorts') {
    if (!jobId) return;
    const modal = document.getElementById('proVideoEditorModal');
    if (!modal) return;

    this.editorJobId = jobId;
    this.editorSourceMode = sourceMode;
    this.stopEditorPlayback();

    try {
      this.showToast('タイムライン編集スタジオを起動中...', 'info');
      const [editorRes, seRes] = await Promise.all([
        window.apiClient.getEditorState(jobId),
        window.apiClient.listSePresets().catch(() => ({ se_presets: [] }))
      ]);

      if (!editorRes.success || !editorRes.editor) {
        throw new Error('編集データの取得に失敗しました');
      }

      this.editorState = editorRes.editor;

      // SEプルダウンの同期
      const seSelect = document.getElementById('editorCutSeSelect');
      if (seSelect && Array.isArray(seRes.se_presets) && seRes.se_presets.length > 0) {
        seSelect.innerHTML = '<option value="none">効果音なし</option>' + seRes.se_presets.map(sp => (
          `<option value="${this._escapeHtml(sp.se_id)}">${this._escapeHtml(sp.name)} (${this._escapeHtml(sp.category || 'SE')})</option>`
        )).join('');
      }

      // グローバルBGM初期値反映
      const bgmSel = document.getElementById('editorGlobalBgmSelect');
      if (bgmSel && this.editorState.bgm_choice) {
        bgmSel.value = this.editorState.bgm_choice;
      }
      const bgmVolSlider = document.getElementById('editorGlobalBgmVolSlider');
      const bgmVolLabel = document.getElementById('editorGlobalBgmVolLabel');
      const bgmPct = Math.round((parseFloat(this.editorState.bgm_volume ?? 0.20)) * 100);
      if (bgmVolSlider) bgmVolSlider.value = String(bgmPct);
      if (bgmVolLabel) bgmVolLabel.textContent = `${bgmPct}%`;

      // MP4ダウンロードリンク
      const dlBtn = document.getElementById('btnEditorDownloadMp4');
      if (dlBtn) {
        dlBtn.href = `${window.apiClient.baseUrl}/api/download/${encodeURIComponent(jobId)}?download=1`;
      }

      // ステージのアスペクト比設定（ショートは9:16、長尺16:9も対応）
      const stageWrapper = document.getElementById('editorStageWrapper');
      if (stageWrapper) {
        if (this.editorState.aspect_ratio === '16:9') {
          stageWrapper.style.aspectRatio = '16 / 9';
          stageWrapper.style.maxWidth = '460px';
        } else {
          stageWrapper.style.aspectRatio = '9 / 16';
          stageWrapper.style.maxWidth = '270px';
        }
      }

      // カット別ライブ表示モードを初期選択
      const liveStage = document.getElementById('editorLiveCutStage');
      const fullPlayer = document.getElementById('editorFullMp4Player');
      if (liveStage) liveStage.style.display = 'block';
      if (fullPlayer) { fullPlayer.pause(); fullPlayer.style.display = 'none'; }

      modal.style.display = 'flex';
      this.updateEditorProjectHeader();
      this.selectEditorCut(0);
      this.renderEditorTimelineTracks();
    } catch (err) {
      this.showToast('動画編集スタジオ起動エラー: ' + err.message, 'error');
    }
  }

  getActiveEditorCut() {
    const scenes = this.editorState?.scenes || [];
    return scenes[this.editorActiveCutIndex] || null;
  }

  updateEditorProjectHeader() {
    if (!this.editorState) return;
    const titleEl = document.getElementById('editorProjectTitle');
    const metaEl = document.getElementById('editorProjectMeta');
    const summaryEl = document.getElementById('editorTimelineSummaryText');
    const scenes = (this.editorState.scenes || []).filter(s => s.enabled !== false);
    const totalSec = scenes.reduce((acc, s) => acc + (parseFloat(s.duration) || 0), 0);

    if (titleEl) titleEl.textContent = `Pro 動画編集スタジオ — ${this.editorState.title || '完成動画プロジェクト'}`;
    if (metaEl) metaEl.textContent = `Job ID: ${this.editorJobId} | 有効 ${scenes.length} カット | 総尺 ${totalSec.toFixed(1)}秒`;
    if (summaryEl) summaryEl.textContent = `Total: ${scenes.length} cuts (${totalSec.toFixed(1)}s)`;
  }

  selectEditorCut(index) {
    const scenes = this.editorState?.scenes || [];
    if (scenes.length === 0) return;
    this.stopEditorPlayback();

    const clamped = Math.max(0, Math.min(scenes.length - 1, index));
    this.editorActiveCutIndex = clamped;
    const cut = scenes[clamped];

    const cutBadge = document.getElementById('editorActiveCutBadge');
    const spkLabel = document.getElementById('editorActiveSpeakerLabel');
    if (cutBadge) cutBadge.textContent = `Cut #${clamped + 1} (ID:${cut.scene_id})`;
    if (spkLabel) spkLabel.textContent = cut.speaker || 'ナレーション';

    // Tab 1: テロップ欄へ反映
    const telopTextEl = document.getElementById('editorCutTelopText');
    const telopFontEl = document.getElementById('editorCutTelopFont');
    const telopStyleEl = document.getElementById('editorCutTelopStyle');
    const telopYSlider = document.getElementById('editorCutTelopYSlider');
    const telopYLabel = document.getElementById('editorTelopYLabel');
    const telopSizeKeyEl = document.getElementById('editorCutTelopSizeKey');
    const telopScaleSlider = document.getElementById('editorCutTelopScaleSlider');
    const telopScaleLabel = document.getElementById('editorTelopScaleLabel');

    if (telopTextEl) telopTextEl.value = cut.telop_text ?? cut.narration ?? '';
    if (telopFontEl) telopFontEl.value = cut.telop_font || 'DelaGothicOne';
    if (telopStyleEl) telopStyleEl.value = cut.telop_style || 'shorts_impact_yellow';
    const yPct = parseInt(cut.telop_y_pct ?? 76, 10);
    if (telopYSlider) telopYSlider.value = String(yPct);
    if (telopYLabel) telopYLabel.textContent = `${yPct}%`;
    if (telopSizeKeyEl) telopSizeKeyEl.value = cut.telop_font_size || 'medium';
    const scPct = parseInt(cut.telop_scale ?? 100, 10);
    if (telopScaleSlider) telopScaleSlider.value = String(scPct);
    if (telopScaleLabel) telopScaleLabel.textContent = `${scPct}%`;

    // Tab 2: ナレーション欄へ反映
    const spkEl = document.getElementById('editorCutSpeaker');
    const narEl = document.getElementById('editorCutNarration');
    const ttsEngEl = document.getElementById('editorCutTtsEngine');
    const voiceEl = document.getElementById('editorCutVoiceName');
    const rateSlider = document.getElementById('editorCutSpeakingRate');
    const rateLabel = document.getElementById('editorCutRateLabel');

    if (spkEl) spkEl.value = cut.speaker || 'ナレーション';
    if (narEl) narEl.value = cut.narration || '';
    if (ttsEngEl) ttsEngEl.value = cut.tts_engine || 'edge';
    if (voiceEl) voiceEl.value = cut.voice_name || 'nanami';
    const rateVal = parseFloat(cut.speaking_rate || 1.0);
    if (rateSlider) rateSlider.value = String(rateVal);
    if (rateLabel) rateLabel.textContent = `${rateVal.toFixed(2)}x`;

    // Tab 3: カット作業欄へ反映
    const enToggle = document.getElementById('editorCutEnabledToggle');
    const mediaBadge = document.getElementById('editorCutMediaTypeBadge');
    const durSlider = document.getElementById('editorCutDurationSlider');
    const durInput = document.getElementById('editorCutDurationInput');
    const durLabel = document.getElementById('editorCutDurationLabel');
    const trimSlider = document.getElementById('editorCutTrimStartSlider');
    const trimLabel = document.getElementById('editorCutTrimStartLabel');

    if (enToggle) enToggle.checked = cut.enabled !== false;
    if (mediaBadge) mediaBadge.textContent = cut.clip_url ? 'AI動画クリップ' : '高精細画像 (Ken Burns)';
    const durVal = parseFloat(cut.duration || 5.0);
    if (durSlider) durSlider.value = String(durVal);
    if (durInput) durInput.value = String(durVal);
    if (durLabel) durLabel.textContent = `${durVal.toFixed(1)}s`;
    const trimVal = parseFloat(cut.trim_start || 0.0);
    if (trimSlider) trimSlider.value = String(trimVal);
    if (trimLabel) trimLabel.textContent = `${trimVal.toFixed(1)}s`;

    // Tab 4: 効果音 (SE) へ反映
    const seSel = document.getElementById('editorCutSeSelect');
    const seDelaySlider = document.getElementById('editorCutSeDelaySlider');
    const seDelayLabel = document.getElementById('editorCutSeDelayLabel');
    const seVolSlider = document.getElementById('editorCutSeVolumeSlider');
    const seVolLabel = document.getElementById('editorCutSeVolumeLabel');

    if (seSel) seSel.value = cut.se_id || 'none';
    const seDelay = parseFloat(cut.se_delay || 0.0);
    if (seDelaySlider) seDelaySlider.value = String(seDelay);
    if (seDelayLabel) seDelayLabel.textContent = `${seDelay.toFixed(1)}s`;
    const seVolPct = Math.round(parseFloat(cut.se_volume ?? 0.70) * 100);
    if (seVolSlider) seVolSlider.value = String(seVolPct);
    if (seVolLabel) seVolLabel.textContent = `${seVolPct}%`;

    const tcEl = document.getElementById('editorTimecodeDisplay');
    if (tcEl) tcEl.textContent = `00:00.0 / 00:${durVal.toFixed(1).padStart(4, '0')}`;

    this.updateEditorLiveStage();
    this.renderEditorTimelineTracks();
  }

  updateEditorLiveStage() {
    const cut = this.getActiveEditorCut();
    if (!cut) return;

    const baseUrl = window.apiClient.baseUrl;
    const videoEl = document.getElementById('editorCutVideoEl');
    const imgEl = document.getElementById('editorCutImageEl');
    const telopBox = document.getElementById('editorDraggableTelopBox');
    const telopTextEl = document.getElementById('editorLiveTelopText');

    if (cut.clip_url && videoEl) {
      const fullClipUrl = cut.clip_url.startsWith('http') ? cut.clip_url : `${baseUrl}${cut.clip_url}`;
      if (videoEl.dataset.currentSrc !== fullClipUrl) {
        videoEl.src = fullClipUrl;
        videoEl.dataset.currentSrc = fullClipUrl;
      }
      videoEl.style.display = 'block';
      if (imgEl) imgEl.style.display = 'none';
    } else if (cut.image_url && imgEl) {
      const fullImgUrl = cut.image_url.startsWith('http') ? cut.image_url : `${baseUrl}${cut.image_url}`;
      imgEl.src = fullImgUrl;
      imgEl.style.display = 'block';
      if (videoEl) { videoEl.pause(); videoEl.style.display = 'none'; }
    }

    if (telopBox && telopTextEl) {
      const yPct = parseInt(cut.telop_y_pct ?? 76, 10);
      telopBox.style.top = `${yPct}%`;
      const txt = (cut.telop_text ?? cut.narration ?? '').trim();
      telopTextEl.textContent = txt ? txt.slice(0, 38) : '（テロップなし）';

      // スタイル配色プレビュー反映
      const styleMap = {
        shorts_impact_yellow: { color: '#FFE600', stroke: '#000000' },
        shorts_crimson_flame: { color: '#FFF5D6', stroke: '#B80000' },
        shorts_gold_luxury:   { color: '#FFD700', stroke: '#1A0F00' },
        shorts_neon_cyber:    { color: '#00F5FF', stroke: '#04122C' },
        shorts_clean_white:   { color: '#FFFFFF', stroke: '#0F172A' }
      };
      const st = styleMap[cut.telop_style] || styleMap.shorts_impact_yellow;
      const scale = (parseInt(cut.telop_scale ?? 100, 10)) / 100;
      telopTextEl.style.color = st.color;
      telopTextEl.style.fontSize = `${Math.round(15 * scale)}px`;
      telopTextEl.style.textShadow = `0 2px 0 ${st.stroke}, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000`;
    }
  }

  stopEditorPlayback() {
    if (this._editorSeTimer) {
      clearTimeout(this._editorSeTimer);
      this._editorSeTimer = null;
    }
    const videoEl = document.getElementById('editorCutVideoEl');
    const audioEl = document.getElementById('editorCutAudioEl');
    const seAudioEl = document.getElementById('editorCutSeAudioEl');
    const playBtn = document.getElementById('btnEditorPlayPauseCut');
    if (videoEl) videoEl.pause();
    if (audioEl) { audioEl.pause(); audioEl.currentTime = 0; }
    if (seAudioEl) { seAudioEl.pause(); seAudioEl.currentTime = 0; }
    if (playBtn) playBtn.textContent = 'カット再生 (音声+SE)';
  }

  playPauseEditorCut() {
    const cut = this.getActiveEditorCut();
    if (!cut) return;
    const baseUrl = window.apiClient.baseUrl;
    const videoEl = document.getElementById('editorCutVideoEl');
    const audioEl = document.getElementById('editorCutAudioEl');
    const seAudioEl = document.getElementById('editorCutSeAudioEl');
    const playBtn = document.getElementById('btnEditorPlayPauseCut');

    if (audioEl && !audioEl.paused) {
      this.stopEditorPlayback();
      return;
    }

    if (videoEl && videoEl.style.display !== 'none') {
      videoEl.currentTime = parseFloat(cut.trim_start || 0);
      videoEl.play().catch(() => {});
    }

    if (cut.audio_url && audioEl) {
      const fullAudioUrl = cut.audio_url.startsWith('http') ? cut.audio_url : `${baseUrl}${cut.audio_url}`;
      audioEl.src = fullAudioUrl;
      audioEl.currentTime = 0;
      audioEl.play().catch(() => {});
      if (playBtn) playBtn.textContent = '停止';
      audioEl.onended = () => {
        this.stopEditorPlayback();
      };
    }

    if (cut.se_id && cut.se_id !== 'none' && seAudioEl) {
      const delayMs = Math.max(0, (parseFloat(cut.se_delay || 0)) * 1000);
      this._editorSeTimer = setTimeout(() => {
        seAudioEl.src = window.apiClient.getSeFileUrl(cut.se_id);
        seAudioEl.volume = Math.min(1.0, Math.max(0.05, parseFloat(cut.se_volume ?? 0.7)));
        seAudioEl.currentTime = 0;
        seAudioEl.play().catch(() => {});
      }, delayMs);
    }
  }

  renderEditorTimelineTracks() {
    const container = document.getElementById('editorTimelineTracksContainer');
    const scenes = this.editorState?.scenes || [];
    if (!container) return;

    const baseUrl = window.apiClient.baseUrl;
    container.innerHTML = scenes.map((sc, idx) => {
      const isActive = idx === this.editorActiveCutIndex;
      const isDisabled = sc.enabled === false;
      const thumbUrl = sc.image_url ? (sc.image_url.startsWith('http') ? sc.image_url : `${baseUrl}${sc.image_url}`) : '';
      const dur = parseFloat(sc.duration || 5.0).toFixed(1);
      const telopSnip = (sc.telop_text || sc.narration || '').slice(0, 16) || '（テロップなし）';
      const narSnip = (sc.narration || '').slice(0, 16) || '（音声なし）';
      const seBadge = (sc.se_id && sc.se_id !== 'none') ? `SE: ${sc.se_id.replace('se_', '')}` : 'SEなし';

      return `
        <div class="timeline-cut-column ${isActive ? 'active' : ''} ${isDisabled ? 'disabled' : ''}" data-cut-idx="${idx}">
          <!-- Track 1: 映像クリップ -->
          <div class="timeline-track-cell track-visual">
            ${thumbUrl ? `<img src="${thumbUrl}" alt="cut" class="timeline-cut-thumb" loading="lazy" onerror="this.style.display='none'" />` : ''}
            <div class="timeline-cut-visual-info">
              <span style="font-weight: 700; color: #f8fafc;">Cut #${idx + 1}</span>
              <span style="font-size: 0.68rem; color: #38bdf8;">${dur}s</span>
            </div>
          </div>
          <!-- Track 2: テロップ -->
          <div class="timeline-track-cell track-telop">
            <span style="font-size: 0.66rem; color: #fde047; font-weight: 700;">[Y:${sc.telop_y_pct ?? 76}%]</span>
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this._escapeHtml(telopSnip)}</span>
          </div>
          <!-- Track 3: ナレーション -->
          <div class="timeline-track-cell track-narration">
            <span style="font-size: 0.66rem; color: #34d399; font-weight: 700;">${this._escapeHtml((sc.speaker || '声').slice(0, 5))}:</span>
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this._escapeHtml(narSnip)}</span>
          </div>
          <!-- Track 4: 効果音 (SE) -->
          <div class="timeline-track-cell track-se ${(sc.se_id && sc.se_id !== 'none') ? 'has-se' : ''}">
            <span>${this._escapeHtml(seBadge)}</span>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.timeline-cut-column').forEach(col => {
      col.addEventListener('click', () => {
        const i = parseInt(col.dataset.cutIdx, 10);
        this.selectEditorCut(i);
      });
    });
  }

  // --- Phase 4: YouTube OAuth 2.0 連携ポップアップ起動 & 直接投稿・予約投稿モーダル ---
  _getCurrentUserId() {
    try {
      if (typeof firebase !== 'undefined' && firebase.auth && firebase.auth().currentUser) {
        return firebase.auth().currentUser.uid;
      }
    } catch (e) {}
    const mockUserStr = localStorage.getItem('kimidori_mock_user');
    if (mockUserStr) {
      try { return JSON.parse(mockUserStr).uid || 'user_123'; } catch (e) {}
    }
    return 'user_123';
  }

  async startYoutubeOAuthPopupFlow() {
    const clientId = (window.settingsManager.get('youtubeClientId') || window.settingsManager.get('globalYoutubeClientId') || '').trim();
    const clientSecret = (window.settingsManager.get('youtubeClientSecret') || window.settingsManager.get('globalYoutubeClientSecret') || '').trim();

    const authWindow = window.open('', 'youtube_auth', 'width=600,height=700');
    if (authWindow) {
      authWindow.document.write(`
        <html><body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; background: #0B0F19; color: #fff; margin: 0; padding: 20px; text-align: center;">
          <div style="border: 4px solid rgba(255,255,255,0.1); border-top-color: #10B981; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin-bottom: 20px;"></div>
          <h3 style="font-weight: 600;">YouTube OAuth 2.0 認証ページへ転送中...</h3>
          <p style="color: #94a3b8; font-size: 0.85rem;">youtube.upload スコープの認証セッションを確立しています。</p>
          <style>@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>
        </body></html>
      `);
    } else {
      return this.showToast('ポップアップがブロックされました。ブラウザの設定で許可してください。', 'error');
    }

    try {
      const userId = this._getCurrentUserId();
      const data = await window.apiClient.getYoutubeAuthUrl(userId, clientId, clientSecret);
      if (data && data.auth_url) {
        authWindow.location.href = data.auth_url;
      } else {
        throw new Error('認証URLを取得できませんでした');
      }
    } catch (e) {
      if (authWindow) authWindow.close();
      console.error('YouTube OAuth Init Error:', e);
      this.showToast(`YouTube OAuth 開始エラー: ${e.message}（設定画面または.envにGoogle OAuth Client ID/Secretを設定してください）`, 'warning');
    }
  }

  initYoutubeDirectUploadModal() {
    this.ytUploadActiveJobId = null;
    this.ytUploadActiveSourceMode = 'pro_shorts';
    this.ytUploadCustomThumbBase64 = null;
    this.ytUploadAvailableCuts = [];

    const modal = document.getElementById('youtubeDirectUploadModal');
    if (!modal) return;

    // 閉じるボタン
    document.getElementById('btnCloseYoutubeUploadModal')?.addEventListener('click', () => {
      modal.style.display = 'none';
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });

    // モーダル内 Google OAuth 連携ボタン
    document.getElementById('btnConnectYoutubeInModal')?.addEventListener('click', () => {
      this.startYoutubeOAuthPopupFlow();
    });

    // OAuth成功時にモーダル内のチャンネル選択肢も自動更新
    window.addEventListener('message', (event) => {
      if ((event.data && event.data.type === 'youtube_auth_success') || event.data === 'youtube_auth_success') {
        if (modal.style.display !== 'none') {
          setTimeout(() => this.refreshYoutubeUploadModalAuthStatus(), 400);
        }
      }
    });

    // 公開設定切り替え（予約投稿時は日時入力欄を表示）
    const privacySel = document.getElementById('ytUploadPrivacyStatus');
    const scheduleGroup = document.getElementById('ytUploadScheduleGroup');
    const publishAtInput = document.getElementById('ytUploadPublishAt');
    if (privacySel && scheduleGroup) {
      privacySel.addEventListener('change', () => {
        const isSched = privacySel.value === 'scheduled';
        scheduleGroup.style.display = isSched ? 'block' : 'none';
        if (isSched && publishAtInput && !publishAtInput.value) {
          const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
          tomorrow.setMinutes(0, 0, 0);
          const localIso = new Date(tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
          publishAtInput.value = localIso;
        }
      });
    }

    // サムネイルモード切り替え（動画内カット / カスタム画像 / 設定しない）
    const thumbModeSel = document.getElementById('ytUploadThumbnailMode');
    const cutWrap = document.getElementById('ytUploadThumbCutSelectorWrap');
    const customWrap = document.getElementById('ytUploadThumbCustomFileWrap');
    const cutSelect = document.getElementById('ytUploadThumbnailCutSelect');
    const customFileInput = document.getElementById('fileYtUploadCustomThumb');
    const thumbPreviewImg = document.getElementById('ytUploadThumbPreviewImg');

    const updateThumbPreview = () => {
      if (!thumbPreviewImg) return;
      const mode = thumbModeSel ? thumbModeSel.value : 'cut';
      if (mode === 'cut') {
        const idx = parseInt(cutSelect?.value || '0', 10);
        const cutItem = this.ytUploadAvailableCuts.find((c, i) => (c.cutIndex ?? i) === idx) || this.ytUploadAvailableCuts[0];
        if (cutItem && cutItem.imageUrl) {
          thumbPreviewImg.src = cutItem.imageUrl;
          thumbPreviewImg.style.display = 'block';
        } else {
          thumbPreviewImg.style.display = 'none';
        }
      } else if (mode === 'custom') {
        if (this.ytUploadCustomThumbBase64) {
          thumbPreviewImg.src = this.ytUploadCustomThumbBase64;
          thumbPreviewImg.style.display = 'block';
        } else {
          thumbPreviewImg.style.display = 'none';
        }
      } else {
        thumbPreviewImg.style.display = 'none';
      }
    };

    if (thumbModeSel) {
      thumbModeSel.addEventListener('change', () => {
        const mode = thumbModeSel.value;
        if (cutWrap) cutWrap.style.display = mode === 'cut' ? 'block' : 'none';
        if (customWrap) customWrap.style.display = mode === 'custom' ? 'block' : 'none';
        updateThumbPreview();
      });
    }

    if (cutSelect) {
      cutSelect.addEventListener('change', updateThumbPreview);
    }

    if (customFileInput) {
      customFileInput.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
          this.ytUploadCustomThumbBase64 = ev.target?.result || null;
          updateThumbPreview();
          this.showToast(`カスタムサムネイル「${file.name}」を読み込みました`, 'info');
        };
        reader.readAsDataURL(file);
      });
    }

    // 各画面の「YouTubeに直接投稿」ボタンをバインド
    document.getElementById('btnOpenYoutubeUploadProShorts')?.addEventListener('click', () => {
      const jobId = this.currentProShortsJobId || localStorage.getItem('kimidori_last_pro_shorts_job');
      if (!jobId) return this.showToast('先にPro版ショート動画を生成してください', 'warning');
      let title = document.getElementById('inputProShortsTheme')?.value?.trim() || 'Proショート動画';
      let description = '';
      let tags = ['Shorts', 'YouTubeショート'];
      try {
        const scriptJson = JSON.parse(document.getElementById('inputProShortsScriptJson')?.value || '{}');
        if (scriptJson.title) title = scriptJson.title;
        if (scriptJson.concept) description = scriptJson.concept;
      } catch (e) {}
      this.openYoutubeDirectUploadModal({
        jobId,
        title: title.includes('#Shorts') ? title : `${title} #Shorts`,
        description: `${description}\n\n#Shorts #YouTubeショート`.trim(),
        tags,
        sourceMode: 'pro_shorts'
      });
    });

    document.getElementById('btnOpenYoutubeUploadLongVideo')?.addEventListener('click', () => {
      const jobId = this.currentLongVideoJobId || localStorage.getItem('kimidori_last_long_video_job');
      if (!jobId) return this.showToast('先にPro版長尺動画を生成してください', 'warning');
      let title = document.getElementById('inputLongVideoTheme')?.value?.trim() || 'ビジネス解説・長尺動画';
      let description = '';
      let tags = ['ビジネス解説', '自己啓発', '要約'];
      try {
        const scriptJson = JSON.parse(document.getElementById('inputLongVideoScriptJson')?.value || '{}');
        if (scriptJson.title) title = scriptJson.title;
        if (scriptJson.concept) description = scriptJson.concept;
      } catch (e) {}
      this.openYoutubeDirectUploadModal({
        jobId,
        title,
        description,
        tags,
        sourceMode: 'long_video'
      });
    });

    document.getElementById('btnOpenYoutubeUploadModeB')?.addEventListener('click', () => {
      const jobId = this.currentModeBJobId;
      if (!jobId) return this.showToast('先に動画の自動編集を完了してください', 'warning');
      this.openYoutubeDirectUploadModal({
        jobId,
        title: '解説動画（自動ジェットカット＆字幕編集済）',
        description: 'KIMIDORI YouTube Auto で自動編集された動画です。',
        tags: ['解説動画', 'ジェットカット'],
        sourceMode: 'edit_mode_b'
      });
    });

    document.getElementById('btnEditorDirectUploadYoutube')?.addEventListener('click', () => {
      const jobId = this.editorJobId || this.currentProShortsJobId || this.currentLongVideoJobId;
      if (!jobId) return this.showToast('編集中の動画ジョブが見つかりません', 'warning');
      const title = this.editorState?.title || 'スタジオ編集済み動画';
      const isShorts = (this.editorSourceMode || 'pro_shorts') === 'pro_shorts';
      this.openYoutubeDirectUploadModal({
        jobId,
        title: isShorts && !title.includes('#Shorts') ? `${title} #Shorts` : title,
        description: isShorts ? `${title}\n\n#Shorts` : title,
        tags: isShorts ? ['Shorts', 'YouTubeショート'] : ['ビジネス解説', '動画編集スタジオ'],
        sourceMode: this.editorSourceMode || 'pro_shorts'
      });
    });

    // チャンク分割アップロード（Resumable Upload）実行ボタン
    const btnExec = document.getElementById('btnExecuteYoutubeDirectUpload');
    if (btnExec) {
      btnExec.addEventListener('click', async () => {
        if (!this.ytUploadActiveJobId) {
          return this.showToast('投稿対象のジョブIDが見つかりません', 'error');
        }
        if (!window.settingsManager.canDirectUploadYoutube(this.ytUploadActiveSourceMode)) {
          return this.showToast('現在のプラン・モードではYouTube直接投稿は制限されています（Pro版またはBYOGモードで解放されます）', 'warning');
        }

        const title = (document.getElementById('ytUploadTitle')?.value || '').trim() || '無題の動画';
        const description = (document.getElementById('ytUploadDescription')?.value || '').trim();
        const rawTags = (document.getElementById('ytUploadTags')?.value || '').trim();
        const tags = rawTags
          ? rawTags.split(',').map(t => t.trim().replace(/^#/, '')).filter(Boolean)
          : [];
        const privacyStatus = document.getElementById('ytUploadPrivacyStatus')?.value || 'private';
        let publishAt = null;

        if (privacyStatus === 'scheduled') {
          const dtVal = document.getElementById('ytUploadPublishAt')?.value;
          if (!dtVal) {
            return this.showToast('予約投稿の日時を指定してください', 'warning');
          }
          const dtObj = new Date(dtVal);
          if (isNaN(dtObj.getTime()) || dtObj.getTime() <= Date.now() + 60000) {
            return this.showToast('予約投稿の日時は現在より未来の日時を指定してください', 'warning');
          }
          publishAt = dtObj.toISOString();
        }

        const thumbMode = document.getElementById('ytUploadThumbnailMode')?.value || 'cut';
        let thumbnailCutIndex = null;
        let thumbnailBase64 = null;
        if (thumbMode === 'cut') {
          thumbnailCutIndex = parseInt(document.getElementById('ytUploadThumbnailCutSelect')?.value || '0', 10);
        } else if (thumbMode === 'custom') {
          thumbnailBase64 = this.ytUploadCustomThumbBase64 || null;
        }

        const channelId = document.getElementById('ytUploadChannelSelect')?.value || '';
        const progArea = document.getElementById('ytUploadProgressArea');
        const progBar = document.getElementById('ytUploadProgressBar');
        const progText = document.getElementById('ytUploadProgressText');
        const resBanner = document.getElementById('ytUploadResultBanner');

        const origBtnHtml = btnExec.innerHTML;
        btnExec.disabled = true;
        btnExec.classList.add('is-loading');
        btnExec.innerHTML = '<span class="btn-spinner"></span><span>YouTubeへResumable Upload中...</span>';

        if (resBanner) resBanner.style.display = 'none';
        if (progArea) progArea.style.display = 'block';
        if (progBar) progBar.style.width = '25%';
        if (progText) progText.textContent = 'Google API Client チャンク分割アップロード（Resumable Upload）を開始しています...';

        try {
          const res = await window.apiClient.directUploadYoutube({
            jobId: this.ytUploadActiveJobId,
            userId: this._getCurrentUserId(),
            channelId: channelId || null,
            title,
            description,
            tags,
            privacyStatus,
            publishAt,
            thumbnailCutIndex,
            thumbnailBase64,
            sourceMode: this.ytUploadActiveSourceMode
          });

          if (progBar) progBar.style.width = '100%';
          if (progText) progText.textContent = 'アップロード完了！';

          if (resBanner) {
            const schedLabel = res.scheduled_at ? `（予約公開日時: ${new Date(res.scheduled_at).toLocaleString('ja-JP')}）` : `（公開設定: ${res.privacy_status}）`;
            const thumbLabel = res.thumbnail_uploaded ? '・サムネイル設定済' : '';
            resBanner.innerHTML = `
              <div style="font-weight: 700; margin-bottom: 4px;">YouTubeへの直接アップロードが完了しました！ ${schedLabel}${thumbLabel}</div>
              <div>動画URL: <a href="${res.youtube_url}" target="_blank" rel="noopener noreferrer" style="color: #38bdf8; text-decoration: underline; font-weight: 700;">${res.youtube_url}</a></div>
            `;
            resBanner.style.display = 'block';
          }
          this.showToast('YouTubeへの直接アップロードが完了しました！', 'success');
        } catch (err) {
          console.error('YouTube Direct Upload Error:', err);
          if (progArea) progArea.style.display = 'none';
          this.showToast(`YouTube投稿エラー: ${err.message}`, 'error');
        } finally {
          btnExec.disabled = false;
          btnExec.classList.remove('is-loading');
          btnExec.innerHTML = origBtnHtml;
        }
      });
    }
  }

  async refreshYoutubeUploadModalAuthStatus() {
    const badge = document.getElementById('ytUploadAuthStatusBadge');
    const channelSel = document.getElementById('ytUploadChannelSelect');
    const userId = this._getCurrentUserId();

    try {
      const status = await window.apiClient.getYoutubeOAuthStatus(userId);
      const channels = status.channels || [];
      if (status.authenticated && channels.length > 0) {
        if (badge) {
          badge.textContent = `OAuth連携済 (${channels.length}ch)`;
          badge.style.background = 'rgba(16,185,129,0.18)';
          badge.style.color = '#34d399';
          badge.style.borderColor = 'rgba(16,185,129,0.45)';
        }
        if (channelSel) {
          channelSel.innerHTML = channels.map(ch => `<option value="${this._escapeHtml(ch.id)}">${this._escapeHtml(ch.name || ch.id)}</option>`).join('');
        }
      } else {
        if (badge) {
          badge.textContent = '未連携（右のボタンからGoogle連携してください）';
          badge.style.background = 'rgba(239,68,68,0.15)';
          badge.style.color = '#f87171';
          badge.style.borderColor = 'rgba(239,68,68,0.35)';
        }
        if (channelSel) {
          channelSel.innerHTML = '<option value="">（Googleアカウントを連携してください）</option>';
        }
      }
    } catch (e) {
      console.warn('Failed to fetch YouTube OAuth status:', e);
    }
  }

  async openYoutubeDirectUploadModal({ jobId, title = '', description = '', tags = [], sourceMode = 'pro_shorts' }) {
    if (!window.settingsManager.canDirectUploadYoutube(sourceMode)) {
      return this.showToast('簡易ショート（ライトプラン相当）ではYouTube直接投稿は制限されています。MP4ダウンロードをご利用ください。', 'warning');
    }

    const modal = document.getElementById('youtubeDirectUploadModal');
    if (!modal) return;

    this.ytUploadActiveJobId = jobId;
    this.ytUploadActiveSourceMode = sourceMode;
    this.ytUploadCustomThumbBase64 = null;
    this.ytUploadAvailableCuts = [];

    const titleInput = document.getElementById('ytUploadTitle');
    const descInput = document.getElementById('ytUploadDescription');
    const tagsInput = document.getElementById('ytUploadTags');
    const privacySel = document.getElementById('ytUploadPrivacyStatus');
    const scheduleGroup = document.getElementById('ytUploadScheduleGroup');
    const progArea = document.getElementById('ytUploadProgressArea');
    const resBanner = document.getElementById('ytUploadResultBanner');
    const cutSelect = document.getElementById('ytUploadThumbnailCutSelect');
    const thumbPreviewImg = document.getElementById('ytUploadThumbPreviewImg');

    if (titleInput) titleInput.value = title;
    if (descInput) descInput.value = description;
    if (tagsInput) tagsInput.value = Array.isArray(tags) ? tags.join(', ') : String(tags || '');
    if (privacySel) privacySel.value = 'private';
    if (scheduleGroup) scheduleGroup.style.display = 'none';
    if (progArea) progArea.style.display = 'none';
    if (resBanner) resBanner.style.display = 'none';

    modal.style.display = 'flex';
    await this.refreshYoutubeUploadModalAuthStatus();

    // ジョブのカット画像一覧を取得してサムネイル選択肢に反映
    try {
      const editorData = await window.apiClient.getEditorState(jobId);
      const scenes = editorData?.editor_state?.scenes || [];
      const baseUrl = window.apiClient.baseUrl;
      this.ytUploadAvailableCuts = scenes
        .map((sc, i) => ({
          cutIndex: i,
          label: `Cut #${i + 1}: ${(sc.telop_text || sc.narration || 'シーン').slice(0, 22)}`,
          imageUrl: sc.image_url ? (sc.image_url.startsWith('http') ? sc.image_url : `${baseUrl}${sc.image_url}`) : ''
        }))
        .filter(item => Boolean(item.imageUrl));

      if (cutSelect) {
        if (this.ytUploadAvailableCuts.length > 0) {
          cutSelect.innerHTML = this.ytUploadAvailableCuts
            .map(c => `<option value="${c.cutIndex}">${this._escapeHtml(c.label)}</option>`)
            .join('');
          if (thumbPreviewImg) {
            thumbPreviewImg.src = this.ytUploadAvailableCuts[0].imageUrl;
            thumbPreviewImg.style.display = 'block';
          }
        } else {
          cutSelect.innerHTML = '<option value="0">Cut #1 (自動サムネイル)</option>';
          if (thumbPreviewImg) thumbPreviewImg.style.display = 'none';
        }
      }
    } catch (e) {
      if (cutSelect) {
        cutSelect.innerHTML = '<option value="0">Cut #1 (先頭カット画像)</option>';
      }
      if (thumbPreviewImg) thumbPreviewImg.style.display = 'none';
    }
  }

  /** ユーザーのクレジット残高・契約プランをバックエンドから取得してUIへ反映 */
  async refreshUserCredits() {
    try {
      if (!window.apiClient) return;
      const creditInfo = await window.apiClient.getUserCredits();
      const creditDisp = document.getElementById('userCreditDisplay');
      const planDisp = document.getElementById('userPlanNameDisplay');
      const planBadge = document.getElementById('currentPlanBadge');

      if (creditDisp) {
        creditDisp.textContent = creditInfo.unlimited ? '無制限' : `${creditInfo.credits || 0} pt`;
      }
      if (planDisp) {
        planDisp.textContent = creditInfo.plan_name || 'フリープラン';
      }
      if (planBadge) {
        planBadge.textContent = creditInfo.plan_name || 'フリープラン';
      }
      if (window.settingsManager) {
        window.settingsManager.set('userCredits', creditInfo.credits || 0);
        window.settingsManager.set('planTier', creditInfo.plan || 'pro');
      }
    } catch (e) {
      console.warn('クレジット情報取得スキップ:', e);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.appController = new AppController();
  // BGM管理の初期化（DOMロード後に実行）
  setTimeout(() => window.appController.initBGMManager(), 500);
});

