/**
 * 登入安全欄位設定 (企業管理員)
 */
function loginSecuritySettings() {
    return {
        loading: true,
        saveMessage: '',
        errorMessage: '',
        validFields: ['sv_1', 'sv_2', 'sv_3'],

        employee: {
            password_field: 'sv_2',
            mine_field: 'sv_1',
            rescue_field: 'sv_3',
            rescue_keyword: '',
        },
        vendor: {
            password_field: 'sv_2',
            mine_field: 'sv_1',
            rescue_field: 'sv_3',
            rescue_keyword: '',
        },

        fieldLabel(f) {
            const map = { sv_1: __('驗證碼 1'), sv_2: __('驗證碼 2'), sv_3: __('驗證碼 3') };
            return map[f] || f;
        },

        async init() {
            await Promise.all([
                this.loadConfig('employee'),
                this.loadConfig('vendor'),
            ]);
            this.loading = false;
        },

        async loadConfig(context) {
            try {
                const resp = await fetch(
                    window.__BP + '/api/admin/settings/login-security/' + context,
                    { credentials: 'same-origin' }
                );
                const data = await resp.json();
                if (data.success) {
                    this[context] = { ...this[context], ...data.data };
                }
            } catch (e) {
                console.error('載入登入安全設定失敗:', e);
            }
        },

        async saveConfig(context) {
            this.saveMessage = '';
            this.errorMessage = '';

            // 前端互斥檢查
            const cfg = this[context];
            const fields = new Set([cfg.password_field, cfg.mine_field, cfg.rescue_field]);
            if (fields.size < 3) {
                this.errorMessage = __('密碼、地雷、救助欄位不能重複指派');
                return;
            }

            try {
                const csrfMeta = document.querySelector('meta[name="csrf-token"]');
                const headers = { 'Content-Type': 'application/json' };
                if (csrfMeta) headers['X-CSRFToken'] = csrfMeta.content;

                const resp = await fetch(
                    window.__BP + '/api/admin/settings/login-security/' + context,
                    {
                        method: 'PUT',
                        credentials: 'same-origin',
                        headers: headers,
                        body: JSON.stringify(cfg),
                    }
                );
                const data = await resp.json();
                if (data.success) {
                    this.saveMessage = __('設定已儲存');
                    setTimeout(() => { this.saveMessage = ''; }, 2000);
                } else {
                    this.errorMessage = data.message || __('儲存失敗');
                    setTimeout(() => { this.errorMessage = ''; }, 4000);
                }
            } catch (e) {
                this.errorMessage = __('儲存失敗: ') + e.message;
                setTimeout(() => { this.errorMessage = ''; }, 4000);
            }
        },
    };
}
