/* user-edit.js — 編輯用戶頁面 (passwordForm + transliterateName) */

const __userEditConfig = window.__USER_EDIT_CONFIG || {};

function passwordForm() {
    return {
        password: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: __('載入中...'),
        validateTimer: null,

        // 姓名與翻譯
        nativeName: __userEditConfig.nativeName || '',
        englishName: __userEditConfig.englishName || '',
        transliterating: false,
        detectedLang: '',
        langNames: { 'zh': __('中文'), 'ja': __('日文'), 'ko': __('韓文'), 'unknown': __('未知'), 'mixed': __('混合') },

        async init() {
            await this.loadRequirements();
        },

        async loadRequirements() {
            try {
                const response = await fetch(window.__BP + '/auth/password-policy');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        const p = data.data.policy;
                        let reqs = [__('長度至少 {min} 個字元', {min: p.min_length})];
                        if (p.require_uppercase) reqs.push(__('包含大寫字母'));
                        if (p.require_lowercase) reqs.push(__('包含小寫字母'));
                        if (p.require_digit) reqs.push(__('包含數字'));
                        if (p.require_special) reqs.push(__('包含特殊符號'));
                        this.passwordRequirements = reqs.join('、') + __('（留空則不變更）');
                    } else {
                        this.passwordRequirements = __('密碼長度至少 8 個字元（留空則不變更）');
                    }
                }
            } catch (err) {
                this.passwordRequirements = __('密碼長度至少 8 個字元（留空則不變更）');
            }
        },

        async generatePassword() {
            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                  document.querySelector('input[name="csrf_token"]')?.value;
                const response = await fetch(window.__BP + '/auth/password-policy/generate', {
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
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                  document.querySelector('input[name="csrf_token"]')?.value;
                const response = await fetch(window.__BP + '/auth/password-policy/validate', {
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

        async transliterateName() {
            if (!this.nativeName || this.transliterating) return;

            this.transliterating = true;
            this.detectedLang = '';

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                  document.querySelector('input[name="csrf_token"]')?.value;
                const response = await fetch(window.__BP + '/api/transliterate/name', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ name: this.nativeName })
                });

                const data = await response.json();
                if (data.success) {
                    this.englishName = data.data.romanized;
                    this.detectedLang = data.data.language;
                } else {
                    console.error('翻譯失敗:', data.message);
                }
            } catch (err) {
                console.error('翻譯請求失敗:', err);
            } finally {
                this.transliterating = false;
            }
        }
    };
}
