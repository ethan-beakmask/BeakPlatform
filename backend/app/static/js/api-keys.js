/**
 * API Key 管理頁面 (/security/api-keys/)
 * 規格: docs/API_KEY_TRIGGER_SPEC.md §4
 *
 * 依賴 window.__APIKEYS_CONFIG = { appPrefix }（模板橋接注入）
 */
(function () {
    const config = window.__APIKEYS_CONFIG || {};
    const PREFIX = config.appPrefix || '';
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

    async function api(path, options = {}) {
        const res = await fetch(PREFIX + path, {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            ...options,
        });
        return res.json();
    }

    window.apiKeysManager = function () {
        return {
            keys: [],
            loading: true,
            msg: '',
            msgErr: false,

            // 選項資料（分類 / 已發行表單 / 用戶）
            categories: [],
            publishedForms: [],
            users: [],

            // 建立/編輯共用表單狀態
            showFormModal: false,
            editingSc: null,          // null = 建立模式
            form: {},
            // 一次性 secret 顯示
            showSecretModal: false,
            createdKey: null,
            secretCopied: false,
            // 暫停
            showSuspendModal: false,
            suspendTarget: null,
            suspendReason: '',

            emptyForm() {
                return {
                    name: '',
                    consumer_label: '',
                    description: '',
                    expires_at: '',
                    allowed_ips_text: '',
                    scope_categories: [],
                    scope_forms: [],
                    applicant_user_secure_code: '',
                };
            },

            async init() {
                this.form = this.emptyForm();
                await Promise.all([this.load(), this.loadOptions()]);
            },

            async load() {
                this.loading = true;
                try {
                    const data = await api('/api/security/api-keys');
                    if (data.success) {
                        this.keys = data.data;
                    } else {
                        this.flash(data.error || '載入失敗', true);
                    }
                } catch (e) {
                    this.flash('載入失敗: ' + e.message, true);
                }
                this.loading = false;
            },

            async loadOptions() {
                // 分類（form_workflow 模組）
                try {
                    const data = await api('/api/form-workflow/categories?flat=1');
                    if (data.success) {
                        this.categories = (data.data || []).filter(c => c.parent_secure_code);
                        // 父分類排前面供整組授權
                        const parents = (data.data || []).filter(c => !c.parent_secure_code);
                        this.categories = parents.concat(this.categories);
                    }
                } catch (e) { /* 模組未載入時忽略 */ }
                // 已發行表單
                try {
                    const data = await api('/api/mappings/published?status=Published');
                    if (data.success) this.publishedForms = data.data || [];
                } catch (e) { /* ignore */ }
                // 企業成員（申請人綁定）
                try {
                    const data = await api('/api/users/?per_page=100');
                    this.users = data.users || [];
                } catch (e) { /* ignore */ }
            },

            flash(message, isErr) {
                this.msg = message;
                this.msgErr = !!isErr;
                if (!isErr) setTimeout(() => { this.msg = ''; }, 4000);
            },

            categoryName(sc) {
                const c = this.categories.find(x => x.secure_code === sc);
                return c ? c.name : sc;
            },

            formName(sc) {
                const f = this.publishedForms.find(x => x.secure_code === sc);
                return f ? f.name : sc;
            },

            scopeSummary(key) {
                const s = key.scopes || {};
                const cats = (s.form_category || []).length;
                const forms = (s.form || []).length;
                const parts = [];
                if (cats) parts.push(`分類 x${cats}`);
                if (forms) parts.push(`表單 x${forms}`);
                return parts.length ? parts.join('、') : '（無授權範圍）';
            },

            statusLabel(status) {
                return { active: '啟用中', suspended: '已暫停', revoked: '已撤銷' }[status] || status;
            },

            fmtTime(iso) {
                if (!iso) return '-';
                return (window.BkTime && BkTime.format) ? BkTime.format(iso, 'short') : iso;
            },

            fmtDate(iso) {
                if (!iso) return '永久';
                return iso.slice(0, 10);
            },

            // ---- 建立 / 編輯 ----

            openCreate() {
                this.editingSc = null;
                this.form = this.emptyForm();
                this.showFormModal = true;
            },

            openEdit(key) {
                this.editingSc = key.secure_code;
                const s = key.scopes || {};
                this.form = {
                    name: key.name || '',
                    consumer_label: key.consumer_label || '',
                    description: key.description || '',
                    expires_at: key.expires_at ? key.expires_at.slice(0, 10) : '',
                    allowed_ips_text: (key.allowed_ips || []).join('\n'),
                    scope_categories: [...(s.form_category || [])],
                    scope_forms: [...(s.form || [])],
                    applicant_user_secure_code: key.applicant_user_secure_code || '',
                };
                this.showFormModal = true;
            },

            buildPayload() {
                const ips = this.form.allowed_ips_text
                    .split('\n').map(x => x.trim()).filter(Boolean);
                return {
                    name: this.form.name,
                    consumer_label: this.form.consumer_label,
                    description: this.form.description,
                    expires_at: this.form.expires_at || null,
                    allowed_ips: ips.length ? ips : null,
                    scopes: {
                        form_category: this.form.scope_categories,
                        form: this.form.scope_forms,
                    },
                    applicant_user_secure_code: this.form.applicant_user_secure_code || null,
                };
            },

            async submitForm() {
                if (!this.form.name.trim()) {
                    this.flash('請填寫名稱', true);
                    return;
                }
                const payload = this.buildPayload();
                try {
                    let data;
                    if (this.editingSc) {
                        data = await api('/api/security/api-keys/' + this.editingSc, {
                            method: 'PATCH', body: JSON.stringify(payload),
                        });
                    } else {
                        data = await api('/api/security/api-keys', {
                            method: 'POST', body: JSON.stringify(payload),
                        });
                    }
                    if (!data.success) {
                        this.flash(data.error || '儲存失敗', true);
                        return;
                    }
                    this.showFormModal = false;
                    if (!this.editingSc) {
                        // 建立成功 -> 顯示一次性 secret
                        this.createdKey = data.data;
                        this.secretCopied = false;
                        this.showSecretModal = true;
                    } else {
                        this.flash('已更新');
                    }
                    await this.load();
                } catch (e) {
                    this.flash('儲存失敗: ' + e.message, true);
                }
            },

            async copySecret() {
                if (!this.createdKey) return;
                const text = 'key_id: ' + this.createdKey.key_id +
                    '\nsecret: ' + this.createdKey.secret;
                try {
                    await navigator.clipboard.writeText(text);
                    this.secretCopied = true;
                } catch (e) {
                    this.flash('複製失敗，請手動選取', true);
                }
            },

            closeSecretModal() {
                this.showSecretModal = false;
                this.createdKey = null;   // 關閉即丟棄，無法再看
            },

            // ---- 暫停 / 復原 / 撤銷 ----

            openSuspend(key) {
                this.suspendTarget = key;
                this.suspendReason = '';
                this.showSuspendModal = true;
            },

            async submitSuspend() {
                if (!this.suspendReason.trim()) {
                    this.flash('請填寫暫停原因', true);
                    return;
                }
                const data = await api(
                    '/api/security/api-keys/' + this.suspendTarget.secure_code + '/suspend',
                    { method: 'POST', body: JSON.stringify({ reason: this.suspendReason }) });
                if (data.success) {
                    this.showSuspendModal = false;
                    this.flash('已暫停');
                    await this.load();
                } else {
                    this.flash(data.error || '暫停失敗', true);
                }
            },

            async resume(key) {
                const data = await api(
                    '/api/security/api-keys/' + key.secure_code + '/resume',
                    { method: 'POST', body: JSON.stringify({}) });
                if (data.success) {
                    this.flash('已復原');
                    await this.load();
                } else {
                    this.flash(data.error || '復原失敗', true);
                }
            },

            async revoke(key) {
                if (!confirm('撤銷後不可復原，外部系統將立即無法使用此 Key。確定撤銷「' + key.name + '」？')) {
                    return;
                }
                const data = await api(
                    '/api/security/api-keys/' + key.secure_code,
                    { method: 'DELETE' });
                if (data.success) {
                    this.flash('已撤銷');
                    await this.load();
                } else {
                    this.flash(data.error || '撤銷失敗', true);
                }
            },
        };
    };
})();
