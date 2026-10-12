/**
 * KIMIDORI YouTube Auto - Auth & Salon Security Controller
 * (salon-cloudrun-tools 仕様準拠)
 * - サロンiframe連携 & SSOハンドシェイク (SALON_AUTH_SYNC / URLパラメータ)
 * - POST /api/auth/sso エンドポイント連携による即時ツール開放
 * - スタンドアロン直接アクセス時のログイン画面表示
 * - 親ウィンドウへのドラフト保存 (SAVE_DRAFT) PostMessageブリッジ
 */

(function () {
  class AuthSecurityManager {
    constructor() {
      this.initAuthFromUrlAndStorage();
      this.initIframePostMessageListener();
      this.applySecurityGuard();
      this.initDraftBridge();
    }

    /**
     * サロンSSO認証API（POST /api/auth/sso）を呼び出し、セッションを初期化してツールを開放する
     */
    async performSalonSso(authPayload) {
      try {
        const res = await fetch('/api/auth/sso', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(authPayload)
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        if (data.success) {
          // localStorage & settingsManager に認証情報を保存
          localStorage.setItem('kimidori_auth_token', data.auth_token || '');
          localStorage.setItem('kimidori_user_email', data.user_email || '');
          localStorage.setItem('kimidori_user_id', data.user_id || '');
          localStorage.setItem('kimidori_user_role', data.role || 'user');
          localStorage.setItem('kimidori_salon_plan', data.plan || 'pro');
          localStorage.setItem('kimidori_is_admin', data.is_admin ? 'true' : 'false');
          localStorage.setItem('kimidori_from_salon', 'true');

          if (window.settingsManager) {
            window.settingsManager.set('salonAuthToken', data.auth_token);
            window.settingsManager.set('salonPlan', data.plan);
            window.settingsManager.set('planTier', data.plan);
            window.settingsManager.set('userId', data.user_id);
          }

          const userObj = {
            uid: data.user_id,
            email: data.user_email,
            role: data.role,
            plan: data.plan,
            isAdmin: data.is_admin,
            from_salon: true
          };

          // AppController への認証状態反映 & ツール即座開放
          const applyAuth = () => {
            if (window.appController) {
              window.appController.currentUser = userObj;
              window.appController.isAdmin = data.is_admin;
              window.appController.updateAuthState(userObj);
              if (window.appController.refreshUserCredits) {
                window.appController.refreshUserCredits();
              }
            }
            const loginPage = document.getElementById('loginPage');
            if (loginPage) loginPage.classList.add('hidden');

            const banner = document.getElementById('salonAuthGuardBanner');
            if (banner) banner.remove();
          };

          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', applyAuth);
          } else {
            applyAuth();
          }

          console.log('[SalonSSO] 認証成功・ツール開放完了:', data.user_email, `(Admin: ${data.is_admin})`);
          return data;
        }
      } catch (err) {
        console.error('[SalonSSO] ハンドシェイクエラー:', err);
      }
      return null;
    }

    /** URLパラメータおよびlocalStorageから認証トークンとプラン情報を取得・SSO判定 */
    initAuthFromUrlAndStorage() {
      const params = new URLSearchParams(window.location.search);
      const urlToken = params.get('auth_token') || params.get('token');
      const urlPlan = params.get('salon_plan') || params.get('plan');
      const urlEmail = (params.get('user_email') || params.get('email') || '').trim().toLowerCase();
      const urlUserId = params.get('user_id') || params.get('uid');
      const isMasterAdmin = (urlEmail === 'oumaumauma32@gmail.com');
      const fromSalon = params.get('from_salon') === 'true' || Boolean(urlEmail || urlToken);

      // サロンからの遷移パラメータが存在する場合、SSOハンドシェイクを実行
      if (fromSalon && (urlEmail || urlUserId || urlToken)) {
        this.performSalonSso({
          user_email: urlEmail || '',
          user_id: urlUserId || urlEmail || '',
          role: isMasterAdmin ? 'admin' : 'user',
          is_admin: isMasterAdmin,
          salon_plan: urlPlan || (isMasterAdmin ? 'admin' : 'premium'),
          auth_token: urlToken || '',
          from_salon: true
        });
      } else {
        // 保存済みのサロンSSOセッションがある場合の自動復元
        const savedToken = localStorage.getItem('kimidori_auth_token');
        const savedEmail = (localStorage.getItem('kimidori_user_email') || '').trim().toLowerCase();
        const savedFromSalon = localStorage.getItem('kimidori_from_salon') === 'true';
        if (savedFromSalon && savedEmail) {
          const isSavedMasterAdmin = (savedEmail === 'oumaumauma32@gmail.com');
          const userObj = {
            uid: localStorage.getItem('kimidori_user_id') || savedEmail,
            email: savedEmail,
            role: isSavedMasterAdmin ? 'admin' : 'user',
            plan: isSavedMasterAdmin ? 'admin' : (localStorage.getItem('kimidori_salon_plan') || 'premium'),
            isAdmin: isSavedMasterAdmin,
            from_salon: true
          };
          const restoreAuth = () => {
            if (window.appController) {
              window.appController.currentUser = userObj;
              window.appController.isAdmin = userObj.isAdmin;
              window.appController.updateAuthState(userObj);
            }
            const loginPage = document.getElementById('loginPage');
            if (loginPage) loginPage.classList.add('hidden');
          };
          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', restoreAuth);
          } else {
            restoreAuth();
          }
        }
      }

      // Stripe決済コールバック処理
      if (params.get('checkout_success') === 'true') {
        setTimeout(() => {
          if (window.appController && window.appController.showToast) {
            window.appController.showToast('プラン加入・クレジットチャージが完了しました！', 'success');
          }
          if (window.appController && window.appController.refreshUserCredits) {
            window.appController.refreshUserCredits();
          }
        }, 800);
      } else if (params.get('checkout_canceled') === 'true') {
        setTimeout(() => {
          if (window.appController && window.appController.showToast) {
            window.appController.showToast('決済手続きがキャンセルされました', 'warning');
          }
        }, 800);
      }
    }

    /** 親ウィンドウ（サロンポータル）からのpostMessage認証データ受信 & ハンドシェイク */
    initIframePostMessageListener() {
      // 親ウィンドウへの読み込み完了通知 (サロンホスト側へSSO同期を要求)
      if (this.isInIframe()) {
        try {
          window.parent.postMessage({ type: 'TOOL_READY', tool: 'kimidori-youtube-auto' }, '*');
        } catch (e) {}
      }

      window.addEventListener('message', (event) => {
        if (!event.data) return;
        const data = event.data;

        // サロンホストからの認証・セッション同期メッセージ
        if (
          data.type === 'SALON_AUTH_SYNC' ||
          data.type === 'INIT_CONTEXT' ||
          data.type === 'salon_user_auth'
        ) {
          const userEmail = (data.user_email || data.userEmail || data.email || '').trim().toLowerCase();
          const userId = data.user_id || data.userId || userEmail || '';
          const isMasterAdmin = (userEmail === 'oumaumauma32@gmail.com');
          const role = isMasterAdmin ? 'admin' : 'user';
          const isAdmin = isMasterAdmin;
          const plan = data.salon_plan || data.plan || (isMasterAdmin ? 'admin' : 'premium');
          const token = data.auth_token || data.token || '';

          this.performSalonSso({
            user_email: userEmail,
            user_id: userId,
            role: role,
            is_admin: isAdmin,
            salon_plan: plan,
            auth_token: token,
            from_salon: true
          });
        }
      });
    }

    /** サロンホストへのドラフト保存 (SAVE_DRAFT) PostMessageブリッジ初期化 */
    initDraftBridge() {
      window.sendDraftToSalon = (title, content, targetCollection = 'contents') => {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({
            type: 'SAVE_DRAFT',
            title: title || '自動生成動画台本',
            content: content || '',
            targetCollection: targetCollection
          }, '*');
          if (window.appController && window.appController.showToast) {
            window.appController.showToast('サロンへ下書きを保存しました', 'success');
          }
        } else {
          console.log('[DraftBridge] スタンドアロン実行中: 下書きはローカルに保持されます');
        }
      };
    }

    /** 認証トークン取得 */
    getAuthToken() {
      return (
        localStorage.getItem('kimidori_auth_token') ||
        (window.settingsManager && window.settingsManager.get('salonAuthToken')) ||
        ''
      );
    }

    /** iframe内稼働中か単体直アクセスかの判定 */
    isInIframe() {
      try {
        return window.self !== window.top;
      } catch (e) {
        return true;
      }
    }

    /**
     * 単体直アクセス時のセキュリティガード
     * - 未認証かつ非サロンの場合は、スタンドアロンログイン画面（#loginPage）を表示
     * - ローカル環境（localhost / 127.0.0.1）またはBYOG設定時または認証済みの場合は利用可能
     */
    applySecurityGuard() {
      const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const hasToken = Boolean(this.getAuthToken());
      const inIframe = this.isInIframe();
      const fromSalon = localStorage.getItem('kimidori_from_salon') === 'true';

      // ローカル環境、サロンiframe内、認証済み、またはサロンからのセッションならパス
      if (isLocal || hasToken || inIframe || fromSalon) {
        return;
      }

      // BYOGが既に登録されている場合は単体直アクセスでも開発・利用を許可
      if (window.settingsManager && window.settingsManager.isByogActive()) {
        return;
      }

      // 未認証単体直アクセス時は、確実にスタンドアロンログイン画面を表示
      window.addEventListener('DOMContentLoaded', () => {
        const loginPage = document.getElementById('loginPage');
        if (loginPage) {
          loginPage.classList.remove('hidden');
        }
      });
    }
  }

  window.authSecurityManager = new AuthSecurityManager();
})();
