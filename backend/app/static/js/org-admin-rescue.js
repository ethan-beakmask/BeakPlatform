/* org-admin-rescue.js — 系統管理員管理企業管理員（重設密碼） */

function rescueResetPasswordForm() {
    const config = window.__RESCUE_CONFIG || {};

    return {
        resetTarget: null,
        resetName: '',
        password: '',
        confirmPassword: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '載入中...',
        validateTimer: null,
        formAction: '',

        get canSubmit() {
            return this.password.length > 0
                && this.confirmPassword.length > 0
                && this.password === this.confirmPassword
                && this.passwordChecked
                && this.passwordErrors.length === 0;
        },

        async init() {
            await this.loadPasswordRequirements();
        },

        openModal(secureCode, displayName) {
            this.resetTarget = secureCode;
            this.resetName = displayName;
            this.formAction = '/organizations/' + config.orgCode + '/admins/' + secureCode + '/reset-password';
            this.generatePassword();
        },

        async loadPasswordRequirements() {
            try {
                const response = await fetch('/auth/password-policy');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        const p = data.data.policy;
                        let reqs = [`長度至少 ${p.min_length} 個字元`];
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

        async generatePassword() {
            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]')?.value
                                || document.querySelector('meta[name="csrf-token"]')?.content;
                const response = await fetch('/auth/password-policy/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        this.password = data.data.password;
                        this.confirmPassword = data.data.password;
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
            this.validateTimer = setTimeout(() => this._doValidate(), 300);
        },

        async _doValidate() {
            if (!this.password) {
                this.passwordErrors = [];
                this.passwordChecked = false;
                return;
            }

            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]')?.value
                                || document.querySelector('meta[name="csrf-token"]')?.content;
                const response = await fetch('/auth/password-policy/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ password: this.password })
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        this.passwordErrors = data.data.errors || [];
                        this.passwordChecked = true;
                    }
                }
            } catch (err) {
                console.error('驗證密碼失敗:', err);
            }
        },

        closeModal() {
            this.resetTarget = null;
            this.resetName = '';
            this.password = '';
            this.confirmPassword = '';
            this.showPassword = false;
            this.passwordErrors = [];
            this.passwordChecked = false;
            this.formAction = '';
        }
    };
}
