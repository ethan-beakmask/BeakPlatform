/* password-form.js -- 共用密碼表單元件 (Mode A)
 *
 * 使用方式:
 *   x-data="passwordForm()"              -- 基本密碼表單
 *   x-data="passwordForm({autoGenerate: true})"  -- 自動產生密碼
 *   x-data="passwordForm({orgCode: 'xxx'})"      -- 指定目標企業（系統管理員用）
 */

function passwordForm(config) {
    config = config || {};
    return {
        password: '',
        confirmPassword: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '載入中...',
        validateTimer: null,

        async init() {
            await this.loadRequirements();
            if (config.autoGenerate) {
                await this.generatePassword();
            }
        },

        _buildUrl(path) {
            var url = path;
            if (config.orgCode) {
                url += (url.indexOf('?') >= 0 ? '&' : '?') + 'org_code=' + encodeURIComponent(config.orgCode);
            }
            return url;
        },

        async loadRequirements() {
            try {
                var response = await fetch(this._buildUrl(window.__BP + '/auth/password-policy'));
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

        async generatePassword() {
            try {
                var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                document.querySelector('input[name="csrf_token"]')?.value;
                var body = {};
                if (config.orgCode) {
                    body.org_code = config.orgCode;
                }
                var response = await fetch(window.__BP + '/auth/password-policy/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(body)
                });
                if (response.ok) {
                    var data = await response.json();
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
                var body = { password: this.password };
                if (config.orgCode) {
                    body.org_code = config.orgCode;
                }
                var response = await fetch(window.__BP + '/auth/password-policy/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(body)
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
