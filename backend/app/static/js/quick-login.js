/* quick-login.js — 開發環境快速登入頁面 */
const _SYSTEM_ORG = window.__SYSTEM_ORG_CODE || '';

function quickLoginManager() {
    return {
        organizations: [],
        users: [],
        selectedOrgSecureCode: '',
        selectedOrgDomain: '',
        selectedUserId: '',
        loading: false,
        loadingUsers: false,
        successMessage: '',
        errorMessage: '',
        currentUser: null,

        async init() {
            await this.loadOrganizations();

            // 預設選擇系統企業
            if (this.organizations.length > 0) {
                const systemOrg = this.organizations.find(org => org.domain_name === _SYSTEM_ORG);
                if (systemOrg) {
                    await this.selectOrg(systemOrg.secure_code);
                } else {
                    await this.selectOrg(this.organizations[0].secure_code);
                }
            }
        },

        async loadOrganizations() {
            try {
                const response = await fetch('/bp/dev/get-orgs');
                const result = await response.json();
                if (result.success) {
                    // 系統企業排在最前面
                    this.organizations = result.data.sort((a, b) => {
                        if (a.domain_name === _SYSTEM_ORG) return -1;
                        if (b.domain_name === _SYSTEM_ORG) return 1;
                        return a.name.localeCompare(b.name);
                    });
                } else {
                    this.errorMessage = result.message;
                }
            } catch (error) {
                this.errorMessage = '載入企業失敗: ' + error.message;
            }
        },

        async selectOrg(secureCode) {
            if (this.selectedOrgSecureCode === secureCode) return;

            this.selectedOrgSecureCode = secureCode;
            // 更新選中的企業 domain
            const selectedOrg = this.organizations.find(org => org.secure_code === secureCode);
            this.selectedOrgDomain = selectedOrg ? selectedOrg.domain_name : '';

            this.users = [];
            this.selectedUserId = '';
            this.errorMessage = '';
            this.loadingUsers = true;

            try {
                const response = await fetch(`/dev/get-users/${secureCode}`);
                const result = await response.json();
                if (result.success) {
                    // 排序：系統管理員 > 企業管理員 > 一般用戶
                    const order = { 'SYSTEM_ADMIN': 0, 'ORG_ADMIN': 1, 'MEMBER': 2, 'EXTERNAL': 3 };
                    this.users = result.data.sort((a, b) => {
                        const orderA = order[a.user_type] ?? 9;
                        const orderB = order[b.user_type] ?? 9;
                        if (orderA !== orderB) return orderA - orderB;
                        return (a.display_name || a.username).localeCompare(b.display_name || b.username);
                    });
                } else {
                    this.errorMessage = result.message;
                }
            } catch (error) {
                this.errorMessage = '載入用戶失敗: ' + error.message;
            } finally {
                this.loadingUsers = false;
            }
        },

        async loginAs(user) {
            if (this.loading) return;

            this.selectedUserId = user.id;
            this.loading = true;
            this.errorMessage = '';
            this.successMessage = '';

            try {
                const response = await fetch('/bp/dev/quick-login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: user.id })
                });

                const result = await response.json();

                if (result.success) {
                    this.successMessage = result.message;
                    this.currentUser = result.data.user;

                    // 1 秒後跳轉
                    setTimeout(() => {
                        window.location.href = result.data.redirect_url;
                    }, 1000);
                } else {
                    this.errorMessage = result.message;
                    this.loading = false;
                }
            } catch (error) {
                this.errorMessage = '登入失敗: ' + error.message;
                this.loading = false;
            }
        },

        async logout() {
            this.loading = true;
            this.successMessage = '';
            this.errorMessage = '';
            this.currentUser = null;

            try {
                await fetch('/bp/dev/logout', { method: 'POST' });
                this.successMessage = 'Session 已清除';
            } catch (error) {
                // 忽略錯誤
            } finally {
                this.loading = false;
            }
        }
    };
}
