/**
 * row_form.html - Alpine.js Manager
 * 全頁面新增/編輯資料（form.io 專用）
 *
 * 使用 form.io schema 渲染表單（含驗證）。
 * 無 schema 時顯示錯誤提示，不提供 fallback。
 */
function rowFormManager() {
    const config = window.__DC_ROW_FORM || {};
    const _urlParams = new URLSearchParams(window.location.search);

    return {
        secureCode: config.secureCode,
        rowId: config.rowId,
        viewConfig: {},
        loading: true,
        saving: false,
        dbName: '',
        toast: { show: false, message: '', type: 'success' },

        // 子系統 context (from URL params)
        _subSystemSc: _urlParams.get('_ss') || '',
        _siteMapNodeSc: _urlParams.get('_smn') || '',

        // form.io 相關
        useFormio: false,
        formioSchema: null,
        formioInstance: null,
        formioI18n: {},

        async init() {
            await this.loadDbInfo();
            await this.loadViewConfig();
            await this.loadFormioSchema();

            if (this.useFormio) {
                await this._injectLookupOptions(this.formioSchema.components);
                await this.renderFormio();
                if (this.rowId) {
                    await this.loadRowIntoFormio();
                }
            }
            this.loading = false;
        },

        async loadDbInfo() {
            try {
                const res = await fetch('/api/data-crud/db-info');
                const data = await res.json();
                if (data.success) {
                    this.dbName = data.data.db_name || '';
                }
            } catch (e) {
                console.error('Load db info failed:', e);
            }
        },

        async loadViewConfig() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}`);
                const data = await res.json();
                if (data.success) {
                    this.viewConfig = data.data;
                }
            } catch (e) {
                console.error('Load view config failed:', e);
            }
        },

        // =====================================================
        // form.io 整合
        // =====================================================

        async loadFormioSchema() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}/formio-schema`);
                const data = await res.json();
                if (data.success && data.data.schema) {
                    this.formioSchema = data.data.schema;
                    this.useFormio = true;
                }
            } catch (e) {
                console.warn('formio schema not available:', e);
            }
        },

        async loadFormioI18n() {
            try {
                const res = await fetch('/static/vendor/formio-i18n-zh-TW.json');
                if (res.ok) {
                    this.formioI18n = await res.json();
                }
            } catch (e) {
                // i18n 載入失敗不影響功能
            }
        },

        async renderFormio() {
            await this.loadFormioI18n();

            const container = document.getElementById('formio-container');
            if (!container) return;

            try {
                this.formioInstance = await Formio.createForm(container, this.formioSchema, {
                    noDefaultSubmitButton: true,
                    language: 'zh-TW',
                    i18n: { 'zh-TW': this.formioI18n }
                });
            } catch (e) {
                console.error('form.io render failed:', e);
                this.useFormio = false;
                this.showToast('表單渲染失敗，請確認欄位規格是否正確', 'error');
            }
        },

        async loadRowIntoFormio() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}/rows/${this.rowId}`);
                const data = await res.json();
                if (data.success && this.formioInstance) {
                    this.formioInstance.submission = { data: data.data };
                } else if (!data.success) {
                    this.showToast(data.error || '載入資料失敗', 'error');
                }
            } catch (e) {
                this.showToast('載入資料失敗', 'error');
            }
        },

        // =====================================================
        // Lookup 注入
        // =====================================================

        async _injectLookupOptions(components) {
            if (!components || !Array.isArray(components)) return;

            // 收集需要 lookup 的元件
            const lookupComps = [];
            const _scan = (comps) => {
                for (const comp of comps) {
                    const props = comp.properties || {};
                    if (props.lookup_category_code && ['select', 'radio', 'selectboxes'].includes(comp.type)) {
                        lookupComps.push({ comp, code: props.lookup_category_code });
                    }
                    if (comp.components) _scan(comp.components);
                    if (comp.columns) {
                        for (const col of comp.columns) {
                            if (col.components) _scan(col.components);
                        }
                    }
                }
            };
            _scan(components);

            if (lookupComps.length === 0) return;

            // 批次載入 (去重)
            const codes = [...new Set(lookupComps.map(lc => lc.code))];
            const cache = {};
            await Promise.all(codes.map(async (code) => {
                try {
                    const res = await fetch('/api/lookup/by-code/' + encodeURIComponent(code));
                    const data = await res.json();
                    if (data.success) {
                        cache[code] = (data.data || []).map(item => ({
                            label: item.label,
                            value: item.code,
                        }));
                    }
                } catch (e) {
                    console.warn('Lookup load failed for', code, e);
                }
            }));

            // 注入到元件
            for (const { comp, code } of lookupComps) {
                const values = cache[code] || [];
                if (comp.type === 'select') {
                    comp.data = comp.data || {};
                    comp.data.values = values;
                } else {
                    // radio / selectboxes
                    comp.values = values;
                }
            }
        },

        // =====================================================
        // 儲存
        // =====================================================

        async save() {
            if (!this.useFormio || !this.formioInstance) {
                this.showToast('此資料表尚未建立欄位規格，無法儲存', 'error');
                return;
            }

            // form.io 路徑：觸發驗證
            const valid = await this.formioInstance.checkValidity(
                this.formioInstance.submission.data, true, null, false
            );
            if (!valid) {
                this.showToast('請修正表單中的錯誤', 'error');
                return;
            }
            const payload = this.formioInstance.submission.data;
            // 移除 form.io 內部欄位
            delete payload.submit;

            this.saving = true;
            try {
                let url, method;
                if (this.rowId) {
                    url = `/api/data-crud/views/${this.secureCode}/rows/${this.rowId}`;
                    method = 'PUT';
                } else {
                    url = `/api/data-crud/views/${this.secureCode}/rows`;
                    method = 'POST';
                }

                const headers = { 'Content-Type': 'application/json' };
                if (this._subSystemSc) {
                    headers['X-SubSystem-SC'] = this._subSystemSc;
                    if (this._siteMapNodeSc) {
                        headers['X-SiteMap-Node'] = this._siteMapNodeSc;
                    }
                }

                const res = await fetch(url, {
                    method,
                    headers,
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast(this.rowId ? '已更新' : '已新增', 'success');
                    setTimeout(() => {
                        window.location.href = `/data-crud/views/${this.secureCode}`;
                    }, 800);
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            } finally {
                this.saving = false;
            }
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
