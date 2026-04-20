/* user-form.js -- 新增用戶頁面 (獨立頁面版本，零 jQuery) */
'use strict';

var __userFormConfig = window.__USER_FORM_CONFIG || {};
var _ufFormData = __userFormConfig.formData || {};
var _ufOrgSettings = __userFormConfig.orgSettings || {};

function userForm() {
    return {
        // 名稱欄位
        nativeName: _ufFormData.native_name || '',
        englishName: _ufFormData.english_name || '',
        englishNameManual: !!_ufFormData.english_name,
        usernameRaw: _ufFormData.username || '',
        usernameManual: !!_ufFormData.username,
        nickname: _ufFormData.nickname || '',
        nicknameManual: !!_ufFormData.nickname,
        role: _ufFormData.role || 'user',

        // 名稱連接符號
        nameConnector: _ufOrgSettings.name_connector != null ? _ufOrgSettings.name_connector : '.',

        // 帳號即時檢查
        usernameCheckTimer: null,
        usernameAvailable: null,
        usernameChecking: false,
        usernameChecked: false,

        // 密碼欄位
        password: '',
        suggestedPassword: '',
        showPassword: false,
        passwordErrors: [],
        passwordChecked: false,
        passwordRequirements: '',
        validateTimer: null,

        // 個人偏好
        interfaceLanguage: _ufFormData.interface_language || '',
        userTimezone: _ufFormData.timezone || '',

        // 聯絡方式
        backupEmail1: _ufFormData.backup_email_1 || '',
        backupEmail2: _ufFormData.backup_email_2 || '',
        mobilePhone1: _ufFormData.mobile_phone_1 || '',
        mobilePhone2: _ufFormData.mobile_phone_2 || '',

        // 翻譯功能
        transliterating: false,
        detectedLang: '',
        langNames: { 'zh': '中文', 'ja': '日文', 'ko': '韓文', 'unknown': '未知', 'mixed': '混合' },

        // 用戶編號
        rules: [],
        selectedRule: '',
        nextNumber: '',
        employeeId: _ufFormData.employee_id || '',
        employeeIdManual: !!_ufFormData.employee_id,

        // 部門選擇器
        _deptTree: null,
        _deptTreeData: [],
        _deptPickerOpen: false,
        _selectedDeptCode: _ufFormData.department_code || '',
        _selectedDeptName: '',

        get hasRules() { return this.rules.length > 0; },
        get normalizedUsername() { return this.usernameRaw.replace(/\s+/g, '').toLowerCase(); },
        get suggestedUsername() {
            if (!this.englishName) return '';
            return this.englishName.trim().replace(/\s+/g, this.nameConnector).toLowerCase();
        },

        async init() {
            await Promise.all([
                this.loadRules(),
                this.loadPasswordRequirements(),
                this.loadSuggestedPassword()
            ]);
            // 如果有預設部門，載入並顯示
            if (this._selectedDeptCode) {
                this._loadDeptTree();
            }
            // 點擊外部關閉選擇器
            var self = this;
            document.addEventListener('click', function(e) {
                var container = document.getElementById('dept-selector-container');
                if (container && !container.contains(e.target)) {
                    self.closeDeptPicker();
                }
            });
        },

        // === 名稱連動 ===
        hasCJK(text) { return /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(text); },

        onNativeNameChange() {
            this.updateNicknameMask();
            if (!this.englishNameManual && !this.hasCJK(this.nativeName)) {
                this.englishName = this.nativeName;
                if (!this.usernameManual) {
                    this.usernameRaw = this.suggestedUsername;
                    this.debouncedCheckUsername();
                }
            }
        },
        onEnglishNameChange() {
            this.englishNameManual = true;
            if (!this.usernameManual) {
                this.usernameRaw = this.suggestedUsername;
                this.debouncedCheckUsername();
            }
        },
        onNicknameChange() { this.nicknameManual = true; },
        onUsernameManualChange() {
            this.usernameManual = true;
            this.debouncedCheckUsername();
        },
        updateNicknameMask() {
            if (!this.nicknameManual) {
                this.nickname = this.maskName(this.nativeName || this.englishName || '');
            }
        },
        maskName(name) {
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
        debouncedCheckUsername() {
            clearTimeout(this.usernameCheckTimer);
            var username = this.normalizedUsername;
            if (!username) { this.usernameChecked = false; this.usernameChecking = false; return; }
            this.usernameChecking = true;
            var self = this;
            this.usernameCheckTimer = setTimeout(function() { self._checkUsername(); }, 500);
        },
        async _checkUsername() {
            var username = this.normalizedUsername;
            if (!username) return;
            try {
                var resp = await fetch(window.__BP + '/users/check-username?username=' + encodeURIComponent(username));
                var data = await resp.json();
                if (this.normalizedUsername === username) {
                    this.usernameAvailable = data.available;
                    this.usernameChecked = true;
                    this.usernameChecking = false;
                }
            } catch (e) { this.usernameChecking = false; }
        },

        // === 密碼 ===
        async loadPasswordRequirements() {
            try {
                var response = await fetch(window.__BP + '/auth/password-policy');
                if (response.ok) {
                    var data = await response.json();
                    if (data.success && data.data.policy.enabled) {
                        var p = data.data.policy;
                        var reqs = ['\u9577\u5EA6\u81F3\u5C11 ' + p.min_length + ' \u500B\u5B57\u5143'];
                        if (p.require_uppercase) reqs.push('\u5305\u542B\u5927\u5BEB\u5B57\u6BCD');
                        if (p.require_lowercase) reqs.push('\u5305\u542B\u5C0F\u5BEB\u5B57\u6BCD');
                        if (p.require_digit) reqs.push('\u5305\u542B\u6578\u5B57');
                        if (p.require_special) reqs.push('\u5305\u542B\u7279\u6B8A\u7B26\u865F');
                        this.passwordRequirements = reqs.join('\u3001');
                    } else { this.passwordRequirements = '\u5BC6\u78BC\u9577\u5EA6\u81F3\u5C11 8 \u500B\u5B57\u5143'; }
                }
            } catch (err) { this.passwordRequirements = '\u5BC6\u78BC\u9577\u5EA6\u81F3\u5C11 8 \u500B\u5B57\u5143'; }
        },
        async loadSuggestedPassword() {
            try {
                var csrfToken = (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch(window.__BP + '/auth/password-policy/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) this.suggestedPassword = data.data.password;
                }
            } catch (err) { this.suggestedPassword = ''; }
        },
        useSuggestedPassword() {
            if (this.suggestedPassword) {
                this.password = this.suggestedPassword;
                this.showPassword = true;
                this.validatePassword();
            }
        },
        validatePassword() {
            clearTimeout(this.validateTimer);
            var self = this;
            this.validateTimer = setTimeout(function() { self._doValidate(); }, 300);
        },
        async _doValidate() {
            if (!this.password) { this.passwordErrors = []; this.passwordChecked = false; return; }
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch(window.__BP + '/auth/password-policy/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ password: this.password })
                });
                if (response.ok) {
                    var data = await response.json();
                    if (data.success) { this.passwordErrors = data.data.errors || []; this.passwordChecked = true; }
                }
            } catch (err) {}
        },

        // === 用戶編號 ===
        async loadRules() {
            try {
                var response = await fetch(window.__BP + '/api/numbering/rules?scope=INTERNAL_ONLY');
                var data = await response.json();
                if (data.success && data.data.length > 0) {
                    this.rules = data.data;
                    var defaultRule = this.rules.find(function(r) { return r.default_for === 'EMPLOYEE'; });
                    if (defaultRule) {
                        this.selectedRule = defaultRule.secure_code;
                        this.nextNumber = defaultRule.preview;
                    } else {
                        this.selectedRule = this.rules[0].secure_code;
                        this.nextNumber = this.rules[0].preview;
                    }
                    if (!this.employeeIdManual && this.nextNumber) this.employeeId = this.nextNumber;
                }
            } catch (err) {}
        },
        async onRuleChange() {
            if (!this.selectedRule) return;
            try {
                var response = await fetch(window.__BP + '/api/numbering/next?rule=' + this.selectedRule);
                var data = await response.json();
                if (data.success) {
                    this.nextNumber = data.data.number;
                    if (!this.employeeIdManual) this.employeeId = this.nextNumber;
                }
            } catch (err) {}
        },

        // === 翻譯 ===
        async transliterateName() {
            if (!this.nativeName || this.transliterating) return;
            this.transliterating = true;
            this.detectedLang = '';
            try {
                var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content ||
                                (document.querySelector('input[name="csrf_token"]') || {}).value;
                var response = await fetch(window.__BP + '/api/transliterate/name', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ name: this.nativeName })
                });
                var data = await response.json();
                if (data.success) {
                    this.englishName = data.data.romanized;
                    this.englishNameManual = true;
                    this.detectedLang = data.data.language;
                    if (!this.usernameManual) {
                        this.usernameRaw = this.suggestedUsername;
                        this.debouncedCheckUsername();
                    }
                }
            } catch (err) {}
            this.transliterating = false;
        },

        // === 部門選擇器 (零依賴 Tree 元件) ===

        async _loadDeptTree() {
            try {
                var response = await fetch(window.__BP + '/api/units/departments?tree=true');
                var data = await response.json();
                if (response.ok) {
                    this._deptTreeData = data.units || [];
                    if (this._selectedDeptCode) {
                        var dept = this._findDeptByCode(this._deptTreeData, this._selectedDeptCode);
                        if (dept) {
                            this._selectedDeptName = dept.name;
                            this._updateDeptDisplay();
                        }
                    }
                }
            } catch (err) {}
        },

        _findDeptByCode(items, code) {
            for (var i = 0; i < items.length; i++) {
                if (items[i].code === code) return items[i];
                if (items[i].children && items[i].children.length > 0) {
                    var found = this._findDeptByCode(items[i].children, code);
                    if (found) return found;
                }
            }
            return null;
        },

        _buildPickerTree() {
            var container = document.getElementById('dept-tree-select');
            if (!container) return;
            if (this._deptTree) { this._deptTree.destroy(); this._deptTree = null; }

            if (this._deptTreeData.length === 0) {
                container.innerHTML = '<div style="padding:20px;color:#888;text-align:center;">尚無部門</div>';
                return;
            }

            var self = this;
            var orgName = __userFormConfig.orgName || '\u4F01\u696D';
            var buildData = function(items) {
                return items.map(function(item) {
                    return {
                        id: item.id,
                        label: item.name + ' (' + item.code + ')',
                        expanded: true,
                        children: (item.children && item.children.length > 0) ? buildData(item.children) : [],
                        data: { code: item.code, name: item.name }
                    };
                });
            };

            var treeData = [{
                id: 'root',
                label: orgName,
                expanded: true,
                children: buildData(this._deptTreeData),
                data: { type: 'root' }
            }];

            this._deptTree = new BeakTree(container, {
                data: treeData,
                hideRoot: false,
                maxExpanded: 500,
                onNodeClick: function(id, node) {
                    if (id === 'root') return;
                    self._selectedDeptCode = node.data.code;
                    self._selectedDeptName = node.data.name;
                    self._updateDeptDisplay();
                    self.closeDeptPicker();
                }
            });

            // 導航到已選擇的部門
            if (this._selectedDeptCode) {
                var dept = this._findDeptByCode(this._deptTreeData, this._selectedDeptCode);
                if (dept) this._deptTree.focusNode(dept.id);
            }
        },

        _updateDeptDisplay() {
            var display = document.getElementById('dept-display');
            var input = document.getElementById('department_code_input');
            var clearBtn = document.getElementById('dept-clear-btn');
            if (!display) return;

            if (this._selectedDeptCode && this._selectedDeptName) {
                display.textContent = this._selectedDeptName;
                display.classList.remove('empty');
                if (input) input.value = this._selectedDeptCode;
                if (clearBtn) clearBtn.style.display = '';
            } else {
                display.textContent = '\u9EDE\u64CA\u9078\u64C7\u90E8\u9580';
                display.classList.add('empty');
                if (input) input.value = '';
                if (clearBtn) clearBtn.style.display = 'none';
            }
        },

        toggleDeptPicker() {
            if (this._deptPickerOpen) { this.closeDeptPicker(); }
            else { this.openDeptPicker(); }
        },

        async openDeptPicker() {
            if (this._deptTreeData.length === 0) await this._loadDeptTree();
            var picker = document.getElementById('dept-tree-picker');
            if (picker) picker.style.display = '';
            this._deptPickerOpen = true;
            this.$nextTick(function() { this._buildPickerTree(); }.bind(this));
        },

        closeDeptPicker() {
            var picker = document.getElementById('dept-tree-picker');
            if (picker) picker.style.display = 'none';
            this._deptPickerOpen = false;
        },

        clearDeptSelection() {
            this._selectedDeptCode = '';
            this._selectedDeptName = '';
            this._updateDeptDisplay();
        }
    };
}
