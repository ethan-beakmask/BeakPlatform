/* org-admin-create.js — 新增企業管理員表單 (Mode B)
 * 依賴: password-form.js (passwordForm 的密碼驗證邏輯在此重用)
 * Window Bridge: window.__ADMIN_CREATE_CONFIG
 */

var __ADMIN_CREATE_CONFIG = window.__ADMIN_CREATE_CONFIG || {};

function createAdminForm() {
    return {
        selectedEmployee: __ADMIN_CREATE_CONFIG.boundEmployee || '',
        displayName: __ADMIN_CREATE_CONFIG.displayName || '',
        username: __ADMIN_CREATE_CONFIG.username || '',
        notifyEmail: __ADMIN_CREATE_CONFIG.notifyEmail || '',
        password: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '載入中...',
        validateTimer: null,

        async init() {
            await this.loadRequirements();
        },

        async loadRequirements() {
            try {
                var response = await fetch(window.__BP + '/auth/password-policy');
                if (response.ok) {
                    var data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        var p = data.data.policy;
                        var reqs = ['長度至少 ' + p.min_length + ' 個字元'];
                        if (p.require_uppercase) reqs.push('包含大寫字母');
                        if (p.require_lowercase) reqs.push('包含小寫字母');
                        if (p.require_digit) reqs.push('包含數字');
                        if (p.require_special) reqs.push('包含特殊符號');
                        this.passwordRequirements = reqs.join('、');
                    } else {
                        this.passwordRequirements = '密碼長度至少 8 個字元';
                    }
                }
            } catch (err) {
                this.passwordRequirements = '密碼長度至少 8 個字元';
            }
        },

        onEmployeeChange() {
            var select = document.querySelector('select[name="bound_employee"]');
            var option = select.options[select.selectedIndex];

            if (option && option.value) {
                this.displayName = option.dataset.name || '';
                this.username = option.dataset.username || '';
                this.notifyEmail = option.dataset.notifyEmail || '';
            } else {
                this.displayName = '';
                this.username = '';
                this.notifyEmail = '';
            }
        },

        async generatePassword() {
            try {
                var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                document.querySelector('input[name="csrf_token"]')?.value;
                var response = await fetch(window.__BP + '/auth/password-policy/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) {
                        this.password = data.data.password;
                        this.showPassword = true;
                        this.validatePassword();
                    }
                }
            } catch (err) {
                console.error('生成密碼失敗:', err);
            }
        },

        validatePassword() {
            clearTimeout(this.validateTimer);
            var self = this;
            this.validateTimer = setTimeout(function() { self._doValidate(); }, 300);
        },

        async _doValidate() {
            if (!this.password) {
                this.passwordErrors = [];
                this.passwordChecked = false;
                return;
            }

            try {
                var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                document.querySelector('input[name="csrf_token"]')?.value;
                var response = await fetch(window.__BP + '/auth/password-policy/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ password: this.password })
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) {
                        this.passwordErrors = data.data.errors || [];
                        this.passwordChecked = true;
                    }
                }
            } catch (err) {
                console.error('驗證密碼失敗:', err);
            }
        }
    };
}
