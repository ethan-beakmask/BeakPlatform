/* user-view.js — 用戶詳情頁面（重設密碼） */

function resetPasswordForm() {
    return {
        showResetPassword: false,
        password: '',
        confirmPassword: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '載入中...',
        validateTimer: null,

        async init() {
            await this.loadPasswordRequirements();
        },

        openResetModal() {
            this.showResetPassword = true;
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
                const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
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
                const csrfToken = document.querySelector('input[name="csrf_token"]')?.value;
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
            this.showResetPassword = false;
            this.password = '';
            this.confirmPassword = '';
            this.showPassword = false;
            this.passwordErrors = [];
            this.passwordChecked = false;
        }
    };
}
