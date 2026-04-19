/**
 * v6 認證模組
 * 使用 Flask-Login 的 session 認證（基於 cookie）
 */

const AuthModule = (() => {
    console.log('✅ AuthModule (v6) 正在初始化...');

    /**
     * 檢查是否已認證
     * @returns {boolean}
     */
    function isAuthenticated() {
        // v6 使用 Flask-Login session，不需要檢查 token
        // 如果能訪問到這個頁面，就表示已經認證
        return true;
    }

    /**
     * 發送認證請求（自動包含 session cookie）
     * @param {string} url - API URL
     * @param {Object} options - fetch 選項
     * @returns {Promise<Response>}
     */
    async function authenticatedFetch(url, options = {}) {
        console.log(`📡 AuthModule.authenticatedFetch: ${url}`);

        // 設置默認選項
        const defaultOptions = {
            credentials: 'same-origin',  // 包含 cookie
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        const finalOptions = { ...defaultOptions, ...options };

        try {
            const response = await fetch(url, finalOptions);

            // 如果是 401 未授權，跳轉到登入頁
            if (response.status === 401) {
                console.warn('⚠️ 401 未授權，跳轉到登入頁');
                window.location.href = '/bp/auth/login';
                return response;
            }

            return response;
        } catch (error) {
            console.error('❌ authenticatedFetch 錯誤:', error);
            throw error;
        }
    }

    /**
     * 檢查權限（v6 簡化版）
     * @param {string} permission - 權限名稱
     * @returns {boolean}
     */
    function hasPermission(permission) {
        // v6 簡化版：假設用戶有所有權限
        // 實際權限檢查由後端處理
        return true;
    }

    /**
     * 登出
     */
    async function logout() {
        try {
            await fetch('/bp/auth/logout', {
                method: 'POST',
                credentials: 'same-origin'
            });
        } catch (error) {
            console.error('❌ 登出失敗:', error);
        } finally {
            window.location.href = '/bp/auth/login';
        }
    }

    console.log('✅ AuthModule (v6) 初始化完成');

    // 導出公開介面
    return {
        isAuthenticated,
        authenticatedFetch,
        hasPermission,
        logout
    };
})();

// 全域暴露
window.AuthModule = AuthModule;
console.log('✅ AuthModule 已掛載到 window 對象');
