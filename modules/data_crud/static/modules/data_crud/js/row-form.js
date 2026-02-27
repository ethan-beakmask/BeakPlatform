/**
 * row_form.html - Alpine.js Manager
 * 全頁面新增/編輯資料（form.io 專用）
 *
 * 使用 form.io schema 渲染表單（含驗證）。
 * 無 schema 時顯示錯誤提示，不提供 fallback。
 */
function rowFormManager() {
    const config = window.__DC_ROW_FORM || {};

    return {
        secureCode: config.secureCode,
        rowId: config.rowId,
        viewConfig: {},
        loading: true,
        saving: false,
        dbName: '',
        toast: { show: false, message: '', type: 'success' },

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

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
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
