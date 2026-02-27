/**
 * row_form.html - Alpine.js Manager
 * 全頁面新增/編輯資料
 *
 * 有 form.io schema 時使用 form.io 渲染（含驗證），
 * 無 schema 時 fallback 到 plain input。
 */
function rowFormManager() {
    const config = window.__DC_ROW_FORM || {};

    return {
        secureCode: config.secureCode,
        rowId: config.rowId,
        viewConfig: {},
        formData: {},
        loading: true,
        saving: false,
        dbName: '',
        toast: { show: false, message: '', type: 'success' },

        // form.io 相關
        useFormio: false,
        formioSchema: null,
        formioInstance: null,
        formioI18n: {},

        get formColumns() {
            if (!this.viewConfig.columns_config) return [];
            return this.viewConfig.columns_config
                .filter(c => c.visible_in_form)
                .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
        },

        async init() {
            await this.loadDbInfo();
            await this.loadViewConfig();
            await this.loadFormioSchema();

            if (this.useFormio) {
                await this.renderFormio();
                if (this.rowId) {
                    await this.loadRowIntoFormio();
                }
            } else {
                if (this.rowId) {
                    await this.loadRow();
                } else {
                    this.initFormData();
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
                console.warn('formio schema not available, using plain input:', e);
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
                console.error('form.io render failed, fallback to plain input:', e);
                this.useFormio = false;
                if (this.rowId) {
                    await this.loadRow();
                } else {
                    this.initFormData();
                }
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
        // Plain input fallback (原有邏輯)
        // =====================================================

        initFormData() {
            this.formData = {};
            this.formColumns.forEach(col => {
                this.formData[col.column] = '';
            });
        },

        async loadRow() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}/rows/${this.rowId}`);
                const data = await res.json();
                if (data.success) {
                    this.formData = {};
                    this.formColumns.forEach(col => {
                        const val = data.data[col.column];
                        this.formData[col.column] = val !== null && val !== undefined ? String(val) : '';
                    });
                } else {
                    this.showToast(data.error || '載入資料失敗', 'error');
                }
            } catch (e) {
                this.showToast('載入資料失敗', 'error');
            }
        },

        isTextArea(col) {
            const t = (col.db_type || '').toUpperCase();
            return t === 'TEXT' || t === 'JSONB' || t === 'JSON';
        },

        isFieldDisabled(col) {
            return col.readonly || col.is_pk || col.is_system;
        },

        // =====================================================
        // 儲存
        // =====================================================

        async save() {
            let payload;

            if (this.useFormio && this.formioInstance) {
                // form.io 路徑：觸發驗證
                const valid = await this.formioInstance.checkValidity(
                    this.formioInstance.submission.data, true, null, false
                );
                if (!valid) {
                    this.showToast('請修正表單中的錯誤', 'error');
                    return;
                }
                payload = this.formioInstance.submission.data;
                // 移除 form.io 內部欄位
                delete payload.submit;
            } else {
                // plain input 路徑
                payload = {};
                this.formColumns.forEach(col => {
                    if (!col.readonly && !col.is_pk && !col.is_system) {
                        let val = this.formData[col.column];
                        if (val === '' && col.nullable) {
                            val = null;
                        }
                        payload[col.column] = val;
                    }
                });
            }

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
