/**
 * user-create-mixin.js -- 新增員工表單共用邏輯
 *
 * 提供 userCreateMixin(config) 回傳 Alpine.js mixin 物件。
 * config:
 *   formData     - 初始表單資料 (預設 {})
 *   orgSettings  - 企業設定 (預設 {})
 *   orgName      - 企業名稱 (預設 '企業')
 *   onCreated    - 建立成功後回呼 (user) => void
 */
'use strict';

function userCreateMixin(config) {
    config = config || {};
    var formData = config.formData || {};
    var orgSettings = config.orgSettings || {};

    return {
        // 名稱欄位
        uc_nativeName: formData.native_name || '',
        uc_englishName: formData.english_name || '',
        uc_englishNameManual: !!formData.english_name,
        uc_usernameRaw: formData.username || '',
        uc_usernameManual: !!formData.username,
        uc_nickname: formData.nickname || '',
        uc_nicknameManual: !!formData.nickname,

        // 名稱連接符號
        uc_nameConnector: orgSettings.name_connector != null ? orgSettings.name_connector : '.',

        // 帳號即時檢查
        uc_usernameCheckTimer: null,
        uc_usernameAvailable: null,
        uc_usernameChecking: false,
        uc_usernameChecked: false,

        // 密碼欄位
        uc_password: '',
        uc_suggestedPassword: '',
        uc_showPassword: false,
        uc_passwordErrors: [],
        uc_passwordChecked: false,
        uc_passwordRequirements: '',
        uc_validateTimer: null,

        // 個人偏好
        uc_interfaceLanguage: formData.interface_language || '',
        uc_userTimezone: formData.timezone || '',

        // 聯絡方式
        uc_backupEmail1: formData.backup_email_1 || '',
        uc_backupEmail2: formData.backup_email_2 || '',
        uc_mobilePhone1: formData.mobile_phone_1 || '',
        uc_mobilePhone2: formData.mobile_phone_2 || '',

        // 翻譯功能
        uc_transliterating: false,
        uc_detectedLang: '',
        uc_langNames: { 'zh': '中文', 'ja': '日文', 'ko': '韓文', 'unknown': '未知', 'mixed': '混合' },

        // 用戶編號
        uc_rules: [],
        uc_selectedRule: '',
        uc_nextNumber: '',
        uc_employeeId: formData.employee_id || '',
        uc_employeeIdManual: !!formData.employee_id,

        // 部門 (外部可設定)
        uc_departmentCode: formData.department_code || '',

        // 建立中狀態
        uc_submitting: false,

        get uc_hasRules() {
            return this.uc_rules.length > 0;
        },

        get uc_normalizedUsername() {
            return this.uc_usernameRaw.replace(/\s+/g, '').toLowerCase();
        },

        get uc_suggestedUsername() {
            if (!this.uc_englishName) return '';
            return this.uc_englishName.trim().replace(/\s+/g, this.uc_nameConnector).toLowerCase();
        },

        async uc_init() {
            await Promise.all([
                this.uc_loadRules(),
                this.uc_loadPasswordRequirements(),
                this.uc_loadSuggestedPassword()
            ]);
        },

        // 重置表單
        uc_reset() {
            this.uc_nativeName = '';
            this.uc_englishName = '';
            this.uc_englishNameManual = false;
            this.uc_usernameRaw = '';
            this.uc_usernameManual = false;
            this.uc_nickname = '';
            this.uc_nicknameManual = false;
            this.uc_password = '';
            this.uc_showPassword = false;
            this.uc_passwordErrors = [];
            this.uc_passwordChecked = false;
            this.uc_interfaceLanguage = '';
            this.uc_userTimezone = '';
            this.uc_backupEmail1 = '';
            this.uc_backupEmail2 = '';
            this.uc_mobilePhone1 = '';
            this.uc_mobilePhone2 = '';
            this.uc_transliterating = false;
            this.uc_detectedLang = '';
            this.uc_employeeId = '';
            this.uc_employeeIdManual = false;
            this.uc_departmentCode = '';
            this.uc_usernameAvailable = null;
            this.uc_usernameChecked = false;
            this.uc_usernameChecking = false;
            this.uc_submitting = false;
            // 重新載入建議密碼和編號
            this.uc_loadSuggestedPassword();
            if (this.uc_hasRules) {
                var rule = this.uc_rules.find(function(r) { return r.default_for === 'EMPLOYEE'; }) || this.uc_rules[0];
                if (rule) {
                    this.uc_selectedRule = rule.secure_code;
                    this.uc_nextNumber = rule.preview;
                }
            }
        },

        // === 名稱連動 ===

        uc_hasCJK: function(text) {
            return /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(text);
        },

        uc_onNativeNameChange: function() {
            this.uc_updateNicknameMask();
            if (!this.uc_englishNameManual && !this.uc_hasCJK(this.uc_nativeName)) {
                this.uc_englishName = this.uc_nativeName;
                if (!this.uc_usernameManual) {
                    this.uc_usernameRaw = this.uc_suggestedUsername;
                    this.uc_debouncedCheckUsername();
                }
            }
        },

        uc_onEnglishNameChange: function() {
            this.uc_englishNameManual = true;
            if (!this.uc_usernameManual) {
                this.uc_usernameRaw = this.uc_suggestedUsername;
                this.uc_debouncedCheckUsername();
            }
        },

        uc_onNicknameChange: function() {
            this.uc_nicknameManual = true;
        },

        uc_onUsernameManualChange: function() {
            this.uc_usernameManual = true;
            this.uc_debouncedCheckUsername();
        },

        uc_updateNicknameMask: function() {
            if (!this.uc_nicknameManual) {
                this.uc_nickname = this.uc_maskName(this.uc_nativeName || this.uc_englishName || '');
            }
        },

        uc_maskName: function(name) {
            if (!name) return '';
            var chars = Array.from(name);
            var len = chars.length;
            if (len <= 1) return '\u25CB';
            if (len === 2) return chars[0] + '\u25CB';
            var mid = '';
            for (var i = 0; i < len - 2; i++) mid += '\u25CB';
            return chars[0] + mid + chars[len - 1];
        },

        // === 帳號即時檢查 ===

        uc_debouncedCheckUsername: function() {
            clearTimeout(this.uc_usernameCheckTimer);
            var username = this.uc_normalizedUsername;
            if (!username) {
                this.uc_usernameChecked = false;
                this.uc_usernameChecking = false;
                return;
            }
            this.uc_usernameChecking = true;
            var self = this;
            this.uc_usernameCheckTimer = setTimeout(function() { self.uc_checkUsername(); }, 500);
        },

        uc_checkUsername: async function() {
            var username = this.uc_normalizedUsername;
            if (!username) return;
            try {
                var resp = await fetch('/users/check-username?username=' + encodeURIComponent(username));
                var data = await resp.json();
                if (this.uc_normalizedUsername === username) {
                    this.uc_usernameAvailable = data.available;
                    this.uc_usernameChecked = true;
                    this.uc_usernameChecking = false;
                }
            } catch (e) {
                this.uc_usernameChecking = false;
            }
        },

        // === 密碼 ===

        uc_loadPasswordRequirements: async function() {
            try {
                var response = await fetch('/auth/password-policy');
                if (response.ok) {
                    var data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        var p = data.data.policy;
                        var reqs = ['\u9577\u5EA6\u81F3\u5C11 ' + p.min_length + ' \u500B\u5B57\u5143'];
                        if (p.require_uppercase) reqs.push('\u5305\u542B\u5927\u5BEB\u5B57\u6BCD');
                        if (p.require_lowercase) reqs.push('\u5305\u542B\u5C0F\u5BEB\u5B57\u6BCD');
                        if (p.require_digit) reqs.push('\u5305\u542B\u6578\u5B57');
                        if (p.require_special) reqs.push('\u5305\u542B\u7279\u6B8A\u7B26\u865F');
                        this.uc_passwordRequirements = reqs.join('\u3001');
                    } else {
                        this.uc_passwordRequirements = '\u5BC6\u78BC\u9577\u5EA6\u81F3\u5C11 8 \u500B\u5B57\u5143';
                    }
                }
            } catch (err) {
                this.uc_passwordRequirements = '\u5BC6\u78BC\u9577\u5EA6\u81F3\u5C11 8 \u500B\u5B57\u5143';
            }
        },

        uc_loadSuggestedPassword: async function() {
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch('/auth/password-policy/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) this.uc_suggestedPassword = data.data.password;
                }
            } catch (err) {
                this.uc_suggestedPassword = '';
            }
        },

        uc_useSuggestedPassword: function() {
            if (this.uc_suggestedPassword) {
                this.uc_password = this.uc_suggestedPassword;
                this.uc_showPassword = true;
                this.uc_validatePassword();
            }
        },

        uc_validatePassword: function() {
            clearTimeout(this.uc_validateTimer);
            var self = this;
            this.uc_validateTimer = setTimeout(function() { self.uc_doValidatePassword(); }, 300);
        },

        uc_doValidatePassword: async function() {
            if (!this.uc_password) {
                this.uc_passwordErrors = [];
                this.uc_passwordChecked = false;
                return;
            }
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch('/auth/password-policy/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ password: this.uc_password })
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) {
                        this.uc_passwordErrors = data.data.errors || [];
                        this.uc_passwordChecked = true;
                    }
                }
            } catch (err) {}
        },

        // === 用戶編號 ===

        uc_loadRules: async function() {
            try {
                var response = await fetch('/api/numbering/rules?scope=INTERNAL_ONLY');
                var data = await response.json();
                if (data.success && data.data.length > 0) {
                    this.uc_rules = data.data;
                    var defaultRule = this.uc_rules.find(function(r) { return r.default_for === 'EMPLOYEE'; });
                    if (defaultRule) {
                        this.uc_selectedRule = defaultRule.secure_code;
                        this.uc_nextNumber = defaultRule.preview;
                    } else {
                        this.uc_selectedRule = this.uc_rules[0].secure_code;
                        this.uc_nextNumber = this.uc_rules[0].preview;
                    }
                    if (!this.uc_employeeIdManual && this.uc_nextNumber) {
                        this.uc_employeeId = this.uc_nextNumber;
                    }
                }
            } catch (err) {}
        },

        uc_onRuleChange: async function() {
            if (!this.uc_selectedRule) return;
            try {
                var response = await fetch('/api/numbering/next?rule=' + this.uc_selectedRule);
                var data = await response.json();
                if (data.success) {
                    this.uc_nextNumber = data.data.number;
                    if (!this.uc_employeeIdManual) {
                        this.uc_employeeId = this.uc_nextNumber;
                    }
                }
            } catch (err) {}
        },

        // === 翻譯 ===

        uc_transliterateName: async function() {
            if (!this.uc_nativeName || this.uc_transliterating) return;
            this.uc_transliterating = true;
            this.uc_detectedLang = '';
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch('/api/transliterate/name', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ name: this.uc_nativeName })
                });
                var data = await response.json();
                if (data.success) {
                    this.uc_englishName = data.data.romanized;
                    this.uc_englishNameManual = true;
                    this.uc_detectedLang = data.data.language;
                    if (!this.uc_usernameManual) {
                        this.uc_usernameRaw = this.uc_suggestedUsername;
                        this.uc_debouncedCheckUsername();
                    }
                }
            } catch (err) {}
            this.uc_transliterating = false;
        },

        // === 提交 (API 方式) ===

        uc_submit: async function() {
            if (this.uc_submitting) return null;

            // 驗證必填
            if (!this.uc_nativeName || !this.uc_englishName || !this.uc_normalizedUsername) {
                return { success: false, error: '\u672C\u570B\u59D3\u540D\u3001\u82F1\u6587\u59D3\u540D\u3001\u5E33\u865F\u70BA\u5FC5\u586B' };
            }
            if (this.uc_usernameChecked && !this.uc_usernameAvailable) {
                return { success: false, error: '\u5E33\u865F\u5DF2\u5B58\u5728' };
            }
            if (this.uc_password && this.uc_passwordErrors.length > 0) {
                return { success: false, error: '\u5BC6\u78BC\u4E0D\u7B26\u5408\u8981\u6C42' };
            }

            this.uc_submitting = true;
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var payload = {
                    native_name: this.uc_nativeName,
                    english_name: this.uc_englishName,
                    username: this.uc_normalizedUsername,
                    password: this.uc_password || null,
                    role: 'user',
                    employee_id: this.uc_employeeId || null,
                    department_code: this.uc_departmentCode || null,
                    nickname: this.uc_nickname || null,
                    interface_language: this.uc_interfaceLanguage || null,
                    timezone: this.uc_userTimezone || null,
                    backup_email_1: this.uc_backupEmail1 || null,
                    backup_email_2: this.uc_backupEmail2 || null,
                    mobile_phone_1: this.uc_mobilePhone1 || null,
                    mobile_phone_2: this.uc_mobilePhone2 || null
                };

                var res = await fetch('/api/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });
                var data = await res.json();
                if (res.ok) {
                    return { success: true, user: data.user || data };
                } else {
                    return { success: false, error: data.error || data.message || '\u5EFA\u7ACB\u5931\u6557' };
                }
            } catch (err) {
                return { success: false, error: '\u5EFA\u7ACB\u5931\u6557: ' + err.message };
            } finally {
                this.uc_submitting = false;
            }
        }
    };
}
