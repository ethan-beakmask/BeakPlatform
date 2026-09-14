/**
 * Sub System Portal - 子系統入口導航頁
 *
 * 從 API 載入用戶角色和可見頁面，卡片式導航。
 */
function subSystemPortal() {
    return {
        loading: true,
        error: '',
        subSystemName: '',
        roleType: '',
        isAdmin: false,
        pages: [],

        _roleLabels: {
            'MANAGER': __('團長'),
            'DEPUTY': __('副團長'),
            'PROXY1': __('代理人(一)'),
            'PROXY2': __('代理人(二)'),
            'MEMBER': __('團員'),
        },

        get roleLabel() {
            return this._roleLabels[this.roleType] || this.roleType || '';
        },

        async init() {
            const config = window.__PORTAL_CONFIG || {};
            this.subSystemName = config.subSystemName || '';

            if (!config.subSystemSc) {
                this.error = __('未指定子系統');
                this.loading = false;
                return;
            }

            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + config.subSystemSc + '/portal');
                const data = await res.json();
                if (!data.success) {
                    this.error = data.error || __('載入失敗');
                    this.loading = false;
                    return;
                }

                this.subSystemName = data.data.sub_system.name || this.subSystemName;
                this.roleType = data.data.role_type || '';
                this.isAdmin = data.data.is_admin || false;
                this.pages = data.data.pages || [];
            } catch (e) {
                this.error = __('載入失敗: {msg}', {msg: e.message});
            } finally {
                this.loading = false;
            }
        },

        openPage(page) {
            const config = window.__PORTAL_CONFIG || {};
            const url = window.__BP + '/p/' + page.page_layout_secure_code
                + '?sub=' + encodeURIComponent(config.subSystemSc)
                + '&ssp=' + encodeURIComponent(page.secure_code);
            window.location.href = url;
        }
    };
}
