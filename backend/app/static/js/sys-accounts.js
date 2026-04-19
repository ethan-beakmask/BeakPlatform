/* sys-accounts.js -- 系統管理員帳號管理 (Mode B: Window Bridge)
 *
 * 左表格 + 右編輯面板布局，新增使用 Modal
 * 依賴: Alpine.js, password-form.js
 */

function sysAccountsManager() {
    var config = window.__SYS_ACCOUNTS_CONFIG || {};

    return {
        accounts: config.accounts || [],
        selected: null,
        showCreateModal: false,
        formErrors: [],
        formSuccess: '',
        submitting: false,

        // 編輯表單
        editForm: {
            display_name: '',
            is_active: true,
            new_password: '',
            confirm_password: ''
        },
        showEditPassword: false,

        // 新增表單
        createForm: {
            username: '',
            email: '',
            display_name: '',
            password: '',
            confirm_password: ''
        },
        showCreatePassword: false,

        // 密碼驗證（共用 password-form.js 的 API）
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '',
        validateTimer: null,

        async init() {
            await this._loadPasswordRequirements();
        },

        /* ========== 密碼相關 ========== */

        async _loadPasswordRequirements() {
            try {
                var response = await fetch('/bp/auth/password-policy');
                if (response.ok) {
                    var data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        var p = data.data.policy;
                        var reqs = ['長度至少 ' + p.min_length + ' 個字元'];
                        if (p.require_uppercase) reqs.push('包含大寫字母');
                        if (p.require_lowercase) reqs.push('包含小寫字母');
                        if (p.require_digit) reqs.push('包含數字');
                        if (p.require_special) reqs.push('包含特殊符號');
                        this.passwordRequirements = reqs.join(', ');
                    } else {
                        this.passwordRequirements = '密碼長度至少 12 個字元';
                    }
                }
            } catch (err) {
                this.passwordRequirements = '密碼長度至少 12 個字元';
            }
        },

        _validatePasswordInput(password) {
            clearTimeout(this.validateTimer);
            var self = this;
            this.validateTimer = setTimeout(function () {
                self._doValidatePassword(password);
            }, 300);
        },

        async _doValidatePassword(password) {
            if (!password) {
                this.passwordErrors = [];
                this.passwordChecked = false;
                return;
            }
            try {
                var csrfToken = config.csrfToken;
                var response = await fetch('/bp/auth/password-policy/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ password: password })
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) {
                        this.passwordErrors = data.data.errors || [];
                        this.passwordChecked = true;
                    }
                }
            } catch (err) {
                // 靜默失敗
            }
        },

        async _generatePassword() {
            try {
                var csrfToken = config.csrfToken;
                var response = await fetch('/bp/auth/password-policy/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) {
                        return data.data.password;
                    }
                }
            } catch (err) {
                // 靜默失敗
            }
            return '';
        },

        /* ========== 選取帳號 ========== */

        selectAccount(account) {
            this.selected = account;
            this.editForm = {
                display_name: account.display_name,
                is_active: account.is_active,
                new_password: '',
                confirm_password: ''
            };
            this.formErrors = [];
            this.formSuccess = '';
            this.showEditPassword = false;
            this.passwordErrors = [];
            this.passwordChecked = false;
        },

        /* ========== 新增 Modal ========== */

        async openCreateModal() {
            this.createForm = {
                username: '',
                email: '',
                display_name: '',
                password: '',
                confirm_password: ''
            };
            this.formErrors = [];
            this.formSuccess = '';
            this.submitting = false;
            this.showCreatePassword = false;
            this.passwordErrors = [];
            this.passwordChecked = false;

            // 自動產生建議密碼
            var pwd = await this._generatePassword();
            if (pwd) {
                this.createForm.password = pwd;
                this.createForm.confirm_password = pwd;
                this.showCreatePassword = true;
                this._validatePasswordInput(pwd);
            }

            this.showCreateModal = true;
        },

        closeCreateModal() {
            this.showCreateModal = false;
        },

        async submitCreate() {
            if (this.submitting) return;
            this.formErrors = [];
            this.submitting = true;

            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);
            formData.append('username', this.createForm.username);
            formData.append('email', this.createForm.email);
            formData.append('display_name', this.createForm.display_name);
            formData.append('password', this.createForm.password);
            formData.append('confirm_password', this.createForm.confirm_password);

            try {
                var resp = await fetch(config.urls.create, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                var result = await resp.json();
                if (result.success) {
                    location.reload();
                } else {
                    this.formErrors = result.errors || ['操作失敗'];
                    this.submitting = false;
                }
            } catch (e) {
                this.formErrors = ['網路錯誤'];
                this.submitting = false;
            }
        },

        /* ========== 編輯 ========== */

        async submitEdit() {
            if (!this.selected || this.submitting) return;
            this.formErrors = [];
            this.formSuccess = '';
            this.submitting = true;

            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);
            formData.append('display_name', this.editForm.display_name);
            formData.append('is_active', this.editForm.is_active ? '1' : '0');
            if (this.editForm.new_password) {
                formData.append('new_password', this.editForm.new_password);
                formData.append('confirm_password', this.editForm.confirm_password);
            }

            var url = config.urls.edit.replace('__SC__', this.selected.secure_code);
            try {
                var resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                var result = await resp.json();
                if (result.success) {
                    location.reload();
                } else {
                    this.formErrors = result.errors || ['操作失敗'];
                    this.submitting = false;
                }
            } catch (e) {
                this.formErrors = ['網路錯誤'];
                this.submitting = false;
            }
        },

        /* ========== 刪除 ========== */

        async submitDelete() {
            if (!this.selected || this.selected.is_self) return;
            if (!confirm('確定要刪除系統管理員「' + this.selected.username + '」嗎？此操作無法復原。')) return;
            if (this.submitting) return;
            this.formErrors = [];
            this.submitting = true;

            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);

            var url = config.urls.delete.replace('__SC__', this.selected.secure_code);
            try {
                var resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                var result = await resp.json();
                if (result.success) {
                    location.reload();
                } else {
                    this.formErrors = result.errors || ['刪除失敗'];
                    this.submitting = false;
                }
            } catch (e) {
                this.formErrors = ['網路錯誤'];
                this.submitting = false;
            }
        },

        /* ========== 編輯面板密碼區段 ========== */

        async generateEditPassword() {
            var pwd = await this._generatePassword();
            if (pwd) {
                this.editForm.new_password = pwd;
                this.editForm.confirm_password = pwd;
                this.showEditPassword = true;
                this._validatePasswordInput(pwd);
            }
        },

        async generateCreatePassword() {
            var pwd = await this._generatePassword();
            if (pwd) {
                this.createForm.password = pwd;
                this.createForm.confirm_password = pwd;
                this.showCreatePassword = true;
                this._validatePasswordInput(pwd);
            }
        }
    };
}
