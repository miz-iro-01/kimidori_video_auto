/**
 * KIMIDORI YouTube Auto - Auth & Salon Security Controller
 * - サロンiframe連携 (URLパラメータ auth_token, salon_plan または postMessage)
 * - 単体URL直接アクセス時の認証・サロン誘導
 * - APIリクエスト時の認証ヘッダー付与 (X-Salon-Token, X-BYOG-Active)
 */

(function () {
  class AuthSecurityManager {
    constructor() {
      this.initAuthFromUrlAndStorage();
      this.initIframePostMessageListener();
      this.applySecurityGuard();
    }

    /** URLパラメータおよびlocalStorageから認証トークンとプラン情報を取得・保存 */
    initAuthFromUrlAndStorage() {
      const params = new URLSearchParams(window.location.search);
      const urlToken = params.get('auth_token') || params.get('token');
      const urlPlan = params.get('salon_plan') || params.get('plan');
      const urlEmail = params.get('user_email') || params.get('email');

      if (urlToken) {
        localStorage.setItem('kimidori_auth_token', urlToken);
        if (window.settingsManager) window.settingsManager.set('salonAuthToken', urlToken);
      }
      if (urlPlan) {
        localStorage.setItem('kimidori_salon_plan', urlPlan);
        if (window.settingsManager) {
          window.settingsManager.set('salonPlan', urlPlan);
          window.settingsManager.set('planTier', urlPlan);
        }
      }
      if (urlEmail) {
        localStorage.setItem('kimidori_user_email', urlEmail);
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

    /** 親ウィンドウ（サロンポータル）からのpostMessage認証データ受信 */
    initIframePostMessageListener() {
      window.addEventListener('message', (event) => {
        if (!event.data) return;
        const data = event.data;

        // サロンからのログイン・認証同期メッセージ
        if (data.type === 'SALON_AUTH_SYNC' || data.type === 'salon_user_auth') {
          if (data.token) {
            localStorage.setItem('kimidori_auth_token', data.token);
            if (window.settingsManager) window.settingsManager.set('salonAuthToken', data.token);
          }
          if (data.plan) {
            localStorage.setItem('kimidori_salon_plan', data.plan);
            if (window.settingsManager) {
              window.settingsManager.set('salonPlan', data.plan);
              window.settingsManager.set('planTier', data.plan);
            }
          }
          if (data.email) {
            localStorage.setItem('kimidori_user_email', data.email);
          }
          if (window.appController && window.appController.refreshUserCredits) {
            window.appController.refreshUserCredits();
          }
        }
      });
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
     * 単体アクセス時＆未認証時のガード処理
     * ローカル開発環境（localhost / 127.0.0.1）およびBYOG設定済み時はパス
     */
    applySecurityGuard() {
      const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const hasToken = Boolean(this.getAuthToken());
      const inIframe = this.isInIframe();

      // ローカル環境またはiframe内または認証済みなら安全
      if (isLocal || hasToken || inIframe) {
        return;
      }

      // BYOGが既に登録されている場合は単体直アクセスでも開発・利用を許可
      if (window.settingsManager && window.settingsManager.isByogActive()) {
        return;
      }

      // 単体直アクセスで未認証の場合、画面上部にサロン連携案内バナーを表示
      window.addEventListener('DOMContentLoaded', () => {
        const topBanner = document.createElement('div');
        topBanner.id = 'salonAuthGuardBanner';
        topBanner.style.cssText = `
          background: linear-gradient(90deg, #1e1b4b 0%, #312e81 100%);
          border-bottom: 2px solid var(--accent-primary);
          color: #f8fafc;
          padding: 0.65rem 1.25rem;
          font-size: 0.85rem;
          display: flex;
          align-items: center;
          justify-content: space-between;
          position: sticky;
          top: 0;
          z-index: 9999;
        `;
        topBanner.innerHTML = `
          <div style="display: flex; align-items: center; gap: 8px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--accent-primary);"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
            <span><strong>サロン会員限定ツール:</strong> サロンポータルからのアクセス、または「設定」にてBYOG（自前環境接続）モードを設定してご利用ください。</span>
          </div>
          <button type="button" class="btn btn-outline" onclick="document.querySelector('[data-target=\\'settings\\']')?.click();" style="padding: 0.25rem 0.65rem; font-size: 0.75rem;">設定を開く</button>
        `;
        document.body.prepend(topBanner);
      });
    }
  }

  window.authSecurityManager = new AuthSecurityManager();
})();
