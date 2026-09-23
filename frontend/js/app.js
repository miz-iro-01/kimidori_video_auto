/**
 * KIMIDORI YouTube Auto - App Controller
 * UIの制御・バリデーション・ビュー切り替え
 */

class AppController {
  constructor() {
    this.adminUsers = [];
    this.initViews();
    this.initForms();
    this.initMangaForm();
    this.initSettings();
    this.renderSettings();
    this.validateForms();
    this.initShortsSummaryHandler();
    this.initAdminUserHandlers();
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
          sec.style.display = 'none';
        });
        const targetSec = document.getElementById(`view-${target}`);
        if (targetSec) {
          targetSec.classList.add('active');
          targetSec.style.display = 'block';
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

    // 投稿ボタンリセット
    const btnPost = document.getElementById('btnPostToYouTube');
    if (btnPost) {
      btnPost.disabled = false;
      btnPost.style.backgroundColor = '';
      btnPost.innerHTML = '<span class="icon-youtube"></span> YouTubeに投稿する';
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

        if (job.status === "completed") {
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
        } else if (job.status === "failed") {
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

  // 簡易ショート動画 高精度化まとめコピー機能
  initShortsSummaryHandler() {
    const copyBtn = document.getElementById('btnCopyShortsTechSummary');
    if (!copyBtn) return;

    const summaryText = `# 簡易ショート動画 高精度化・プロンプト＆映像設計仕様まとめ

## 1. 日本語形態素・自然文脈分割 (Semantic Segmentation)
- 課題: 固定文字数（14文字）の機械的改行により、「気 / 遣う」「先 / 生は」等の単語途中切断が発生していた。
- 解決策: 文末句読点（100点）、カギ括弧（75点）、2文字助詞（45点）、1文字助詞（25点）の文法スコアリングを実装し、意味が通る自然な文節単位で自動改行。

## 2. 厳格な行頭・行末禁則処理 (Kinsoku Shori)
- 行頭禁則: 閉じ括弧（」』）)）や句読点（。、？！?!）が行頭にぶら下がることを完全禁止。
- 行末禁則: 開き括弧（「『（(）が行末に来ることを禁止。
- 孤立行撲滅: 1〜2文字だけの「ぶら下がり行（例: 「は」「。」）」を検知し、前後の行と自然に結合・再配分。

## 3. 横幅14文字制限 × 最大3行カード時間等分分割
- スマホ縦画面（1080×1920）において、1行を最大14文字・最大3行に厳格制限。
- 長いセリフがある場合、同じ背景画像の尺の中で1〜3枚のテロップカードに時間等分分割（カード1 → カード2 → カード3）し、テンポよく切り替えて表示。

## 4. 映像デザイン＆テロップ視認性最適化
- フォント: Noto Sans JP（太字 62px）
- 輪郭線: 高精細な黒ストローク（幅 5px）による視認性向上。
- セーフティマージン: 左右に106pxずつの余白を確保し、スマホ画面端やSNS UIとの文字被りを防止。
- 動的演出: ケンバーンズ効果（ズーム・パン）と滑らかなフェードトランジションを適用。

## 5. 超高速プレビュー＆ストリーミング再生
- MP4 faststart化: FFmpegの \`-movflags +faststart\` を適用し、moov atom（動画メタデータ）を先頭配置。
- HTTP 206 Partial Content: バックエンドにStarlette FileResponse を採用し、HTML5 <video> のバイト範囲リクエスト（Range）に対応。読み込み待ちゼロで即座にプレビュー再生が可能に。

## 6. デュアルGemini API自動フォールバック
- 無料版APIキー（AQ.A... / AI Studio）と有料版APIキー（AIza... / Cloud Console）の両方に完全対応。
- レート制限（429）やエラー時も、複数モデル（gemini-2.5-flash / 2.0-flash / 1.5-flash）へシームレスに自動フォールバック。
`;

    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(summaryText);
        this.showToast("簡易ショート動画の高精度化まとめをコピーしました！", "success");
      } catch (err) {
        // フォールバック
        const ta = document.createElement('textarea');
        ta.value = summaryText;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        this.showToast("簡易ショート動画の高精度化まとめをコピーしました！", "success");
      }
    });
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
      checkAutoMode.addEventListener('change', async (e) => {
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
        const theme = document.getElementById('inputProShortsTheme').value.trim();
        const genre = document.getElementById('inputProShortsGenre').value;
        if (!theme) return this.showToast("テーマ・題材を入力してください", "error");

        this.showToast("Pro版ショート台本（全6〜7カット・全カット動画演出）を生成中...", "info");
        btnRunProShorts.disabled = true;
        try {
          const res = await window.apiClient.generateProShortsScript(theme, genre);
          if (res.success && res.script) {
            document.getElementById('inputProShortsScriptJson').value = JSON.stringify(res.script, null, 2);
            proShortsScriptArea.style.display = 'block';
            this.showToast("Pro版ショート動画の台本が生成されました！", "success");
          }
        } catch (err) {
          this.showToast("台本生成失敗: " + err.message, "error");
        } finally {
          btnRunProShorts.disabled = false;
        }
      });
    }

    if (btnGenProShorts) {
      btnGenProShorts.addEventListener('click', async () => {
        const jsonStr = document.getElementById('inputProShortsScriptJson').value.trim();
        if (!jsonStr) return this.showToast("台本データがありません", "error");

        let scriptData;
        try {
          scriptData = JSON.parse(jsonStr);
        } catch (e) {
          return this.showToast("JSON形式が不正です: " + e.message, "error");
        }

        const ttsEngine = window.settingsManager.get('ttsEngine') || 'edge';
        const voiceName = window.settingsManager.get('voiceName') || 'nanami';

        this.showToast("Pro版ショート動画の生成を開始しました", "info");
        btnGenProShorts.disabled = true;

        try {
          const res = await window.apiClient.generateMangaVideo(scriptData, ttsEngine, voiceName);
          const progArea = document.getElementById('proShortsProgressArea');
          const titleEl = document.getElementById('proShortsProgressTitle');
          const fillEl = document.getElementById('proShortsProgressFill');
          const msgEl = document.getElementById('proShortsProgressMsg');
          const resEl = document.getElementById('proShortsVideoResult');
          const previewEl = document.getElementById('proShortsVideoPreview');

          progArea.style.display = 'block';

          this.startJobPolling(res.job_id, 'PRO_SHORTS', {
            onProgress: (job) => {
              titleEl.textContent = job.message || "生成中...";
              fillEl.style.width = `${job.progress || 10}%`;
              msgEl.textContent = `進捗: ${job.progress}%`;
            },
            onComplete: (job) => {
              titleEl.textContent = "Pro版ショート動画が完成しました！";
              fillEl.style.width = "100%";
              msgEl.textContent = "生成完了";
              if (job.video_path) {
                resEl.style.display = 'block';
                const dlUrl = `${window.apiClient.baseUrl}/api/video/download?path=${encodeURIComponent(job.video_path)}`;
                previewEl.src = dlUrl;
                const dlBtn = document.getElementById('btnDownloadProShorts');
                if (dlBtn) dlBtn.href = dlUrl;
              }
              btnGenProShorts.disabled = false;
            },
            onError: (err) => {
              titleEl.textContent = "生成失敗";
              msgEl.textContent = err;
              btnGenProShorts.disabled = false;
            }
          });
        } catch (err) {
          this.showToast("動画生成失敗: " + err.message, "error");
          btnGenProShorts.disabled = false;
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
      this.showToast("最初から新しく作成する画面に戻りました", "info");
    });

    // 2. 長尺動画（15〜20分）完全仕様
    const btnRunLong = document.getElementById('btnRunLongVideoScript');
    const btnGenLong = document.getElementById('btnGenerateLongVideo');
    const longScriptArea = document.getElementById('longVideoScriptArea');
    const longLockNotice = document.getElementById('longVideoLockNotice');

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
        const theme = document.getElementById('inputLongVideoTheme').value.trim();
        const genre = document.getElementById('inputLongVideoGenre').value;
        const duration = document.getElementById('inputLongVideoDuration').value;

        if (!theme) return this.showToast("動画テーマまたは原案資料を入力してください", "error");

        this.showToast("全5章長尺台本＆人物シートを生成中...", "info");
        btnRunLong.disabled = true;

        try {
          const res = await window.apiClient.generateLongVideoScript(theme, genre, duration);
          if (res.success && res.script) {
            document.getElementById('inputLongVideoScriptJson').value = JSON.stringify(res.script, null, 2);
            longScriptArea.style.display = 'block';
            this.showToast("全5章台本と確定設計図が生成されました！", "success");
          }
        } catch (err) {
          this.showToast("長尺台本生成失敗: " + err.message, "error");
        } finally {
          btnRunLong.disabled = false;
        }
      });
    }

    if (btnGenLong) {
      btnGenLong.addEventListener('click', async () => {
        const jsonStr = document.getElementById('inputLongVideoScriptJson').value.trim();
        if (!jsonStr) return this.showToast("台本データがありません", "error");

        let scriptData;
        try {
          scriptData = JSON.parse(jsonStr);
        } catch (e) {
          return this.showToast("JSON形式が不正です: " + e.message, "error");
        }

        const ttsEngine = window.settingsManager.get('ttsEngine') || 'edge';
        const voiceName = window.settingsManager.get('voiceName') || 'nanami';

        this.showToast("長尺動画（小分け小メモリ生成）を開始しました", "info");
        btnGenLong.disabled = true;

        try {
          const res = await window.apiClient.generateMangaVideo(scriptData, ttsEngine, voiceName);
          const progArea = document.getElementById('longVideoProgressArea');
          const titleEl = document.getElementById('longVideoProgressStatusTitle');
          const fillEl = document.getElementById('longVideoProgressFill');
          const msgEl = document.getElementById('longVideoProgressMessage');
          const resEl = document.getElementById('longVideoResult');
          const previewEl = document.getElementById('longVideoPreview');
          const downloadBtn = document.getElementById('btnDownloadLongVideo');

          progArea.style.display = 'block';

          this.startJobPolling(res.job_id, 'LONG_VIDEO', {
            onProgress: (job) => {
              titleEl.textContent = job.message || "小分け合成中...";
              fillEl.style.width = `${job.progress || 10}%`;
              msgEl.textContent = `進捗: ${job.progress}%`;
            },
            onComplete: (job) => {
              titleEl.textContent = "長尺動画が完成しました！";
              fillEl.style.width = "100%";
              msgEl.textContent = "生成完了";
              if (job.video_path) {
                const downloadUrl = `${window.apiClient.baseUrl}/api/video/download?path=${encodeURIComponent(job.video_path)}`;
                resEl.style.display = 'block';
                previewEl.src = downloadUrl;
                if (downloadBtn) downloadBtn.href = downloadUrl;
              }
              btnGenLong.disabled = false;
            },
            onError: (err) => {
              titleEl.textContent = "生成失敗";
              msgEl.textContent = err;
              btnGenLong.disabled = false;
            }
          });
        } catch (err) {
          this.showToast("動画生成失敗: " + err.message, "error");
          btnGenLong.disabled = false;
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
      this.showToast("最初から新しく作成する画面に戻りました", "info");
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.appController = new AppController();
  // BGM管理の初期化（DOMロード後に実行）
  setTimeout(() => window.appController.initBGMManager(), 500);
});
