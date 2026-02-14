/* user-form.js — 新增用戶頁面 (userForm + 部門選擇器) */

const __userFormConfig = window.__USER_FORM_CONFIG || {};
const formData = __userFormConfig.formData || {};
const orgSettings = __userFormConfig.orgSettings || {};

function userForm() {
    return {
        // 名稱欄位
        nativeName: formData.native_name || '',
        englishName: formData.english_name || '',
        englishNameManual: !!formData.english_name,
        usernameRaw: formData.username || '',
        usernameManual: !!formData.username,
        nickname: formData.nickname || '',
        nicknameManual: !!formData.nickname,
        role: formData.role || 'user',

        // 名稱連接符號
        nameConnector: orgSettings.name_connector != null ? orgSettings.name_connector : '.',

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
        passwordRequirements: '載入中...',
        validateTimer: null,

        // 個人偏好
        interfaceLanguage: formData.interface_language || '',
        userTimezone: formData.timezone || '',

        // 聯絡方式
        backupEmail1: formData.backup_email_1 || '',
        backupEmail2: formData.backup_email_2 || '',
        mobilePhone1: formData.mobile_phone_1 || '',
        mobilePhone2: formData.mobile_phone_2 || '',

        // 翻譯功能
        transliterating: false,
        detectedLang: '',
        langNames: { 'zh': '中文', 'ja': '日文', 'ko': '韓文', 'unknown': '未知', 'mixed': '混合' },

        // 用戶編號
        rules: [],
        selectedRule: '',
        nextNumber: '',
        employeeId: formData.employee_id || '',
        employeeIdManual: !!formData.employee_id,

        get hasRules() {
            return this.rules.length > 0;
        },

        get normalizedUsername() {
            return this.usernameRaw.replace(/\s+/g, '').toLowerCase();
        },

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
        },

        // === 名稱連動 ===

        hasCJK(text) {
            return /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(text);
        },

        onNativeNameChange() {
            // 本國姓名 → 暱稱 (遮罩)
            this.updateNicknameMask();
            // 非 CJK 本國姓名 → 英文姓名 (自動填入)
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
            // 英文姓名 → 帳號
            if (!this.usernameManual) {
                this.usernameRaw = this.suggestedUsername;
                this.debouncedCheckUsername();
            }
        },

        onNicknameChange() {
            this.nicknameManual = true;
        },

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
            const chars = [...name];
            const len = chars.length;
            if (len <= 1) return '\u25CB';
            if (len === 2) return chars[0] + '\u25CB';
            return chars[0] + '\u25CB'.repeat(len - 2) + chars[len - 1];
        },

        // === 帳號即時檢查 ===

        debouncedCheckUsername() {
            clearTimeout(this.usernameCheckTimer);
            const username = this.normalizedUsername;
            if (!username) {
                this.usernameChecked = false;
                this.usernameChecking = false;
                return;
            }
            this.usernameChecking = true;
            this.usernameCheckTimer = setTimeout(() => this._checkUsername(), 500);
        },

        async _checkUsername() {
            const username = this.normalizedUsername;
            if (!username) return;
            try {
                const resp = await fetch(`/users/check-username?username=${encodeURIComponent(username)}`);
                const data = await resp.json();
                if (this.normalizedUsername === username) {
                    this.usernameAvailable = data.available;
                    this.usernameChecked = true;
                    this.usernameChecking = false;
                }
            } catch (e) {
                console.error('檢查帳號失敗:', e);
                this.usernameChecking = false;
            }
        },

        // === 密碼 ===

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

        async loadSuggestedPassword() {
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
                        this.suggestedPassword = data.data.password;
                    }
                }
            } catch (err) {
                this.suggestedPassword = '';
            }
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

        // === 用戶編號 ===

        async loadRules() {
            try {
                const response = await fetch('/api/numbering/rules?scope=INTERNAL_ONLY');
                const data = await response.json();
                if (data.success && data.data.length > 0) {
                    this.rules = data.data;
                    const defaultRule = this.rules.find(r => r.default_for === 'EMPLOYEE');
                    if (defaultRule) {
                        this.selectedRule = defaultRule.secure_code;
                        this.nextNumber = defaultRule.preview;
                    } else {
                        this.selectedRule = this.rules[0].secure_code;
                        this.nextNumber = this.rules[0].preview;
                    }
                    if (!this.employeeIdManual && this.nextNumber) {
                        this.employeeId = this.nextNumber;
                    }
                }
            } catch (err) {
                console.error('載入編號規則失敗:', err);
            }
        },

        async onRuleChange() {
            if (!this.selectedRule) return;
            try {
                const response = await fetch(`/api/numbering/next?rule=${this.selectedRule}`);
                const data = await response.json();
                if (data.success) {
                    this.nextNumber = data.data.number;
                    if (!this.employeeIdManual) {
                        this.employeeId = this.nextNumber;
                    }
                }
            } catch (err) {
                console.error('取得編號失敗:', err);
            }
        },

        // === 翻譯 ===

        async transliterateName() {
            if (!this.nativeName || this.transliterating) return;

            this.transliterating = true;
            this.detectedLang = '';

            try {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content ||
                                  document.querySelector('input[name="csrf_token"]')?.value;
                const response = await fetch('/api/transliterate/name', {
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
                    this.englishNameManual = true;
                    this.detectedLang = data.data.language;
                    // 觸發帳號自動產生
                    if (!this.usernameManual) {
                        this.usernameRaw = this.suggestedUsername;
                        this.debouncedCheckUsername();
                    }
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

// ===== 部門選擇器 - 使用 jstree 組織樹 =====

let deptTreeData = [];
let selectedDeptCode = formData.department_code || '';
let selectedDeptName = '';
let deptTreeInitialized = false;

// 初始化部門樹
async function initDeptTree() {
    if (deptTreeInitialized) return;

    try {
        const response = await fetch('/api/units/departments?tree=true');
        const data = await response.json();
        if (response.ok) {
            deptTreeData = data.units || [];
            buildDeptTree();
            deptTreeInitialized = true;

            // 如果有預設值，找出對應名稱並更新顯示
            if (selectedDeptCode) {
                const dept = findDeptByCode(deptTreeData, selectedDeptCode);
                if (dept) {
                    selectedDeptName = dept.name;
                    updateDeptDisplay();
                }
            }
        }
    } catch (err) {
        console.error('載入部門失敗:', err);
        $('#dept-tree-select').html('<div class="dept-tree-empty">載入失敗</div>');
    }
}

// 遞迴查找部門
function findDeptByCode(items, code) {
    for (const item of items) {
        if (item.code === code) return item;
        if (item.children && item.children.length > 0) {
            const found = findDeptByCode(item.children, code);
            if (found) return found;
        }
    }
    return null;
}

// 建構 jstree
function buildDeptTree() {
    const $tree = $('#dept-tree-select');

    // 銷毀舊實例
    if ($tree.jstree(true)) {
        $tree.jstree('destroy');
    }

    // 如果沒有部門，顯示提示
    if (deptTreeData.length === 0) {
        $tree.html('<div class="dept-tree-empty">尚無部門，請先建立部門</div>');
        return;
    }

    // 建構 jstree 資料結構
    const buildTreeData = (items) => items.map(item => ({
        id: item.id,
        text: item.name + ' <span style="color: #888; font-size: 11px;">(' + item.code + ')</span>',
        icon: 'icon-dept',
        state: { opened: true },
        data: { code: item.code, name: item.name },
        children: item.children && item.children.length > 0 ? buildTreeData(item.children) : []
    }));

    // 根節點使用企業名稱
    const orgName = __userFormConfig.orgName || '企業';
    const treeData = [{
        id: 'root',
        text: orgName,
        icon: 'icon-company',
        state: { opened: true, disabled: true },
        data: { type: 'root' },
        children: buildTreeData(deptTreeData)
    }];

    $tree.jstree({
        core: {
            data: treeData,
            themes: { dots: true, icons: true },
            worker: false
        },
        plugins: ['wholerow']
    });

    // 選擇事件
    $tree.on('select_node.jstree', function(e, data) {
        if (data.node.id === 'root') return; // 不能選擇根節點

        selectedDeptCode = data.node.data.code;
        selectedDeptName = data.node.data.name;
        updateDeptDisplay();
        closeDeptPicker();
    });

    // 如果有預設選中值，選中它
    if (selectedDeptCode) {
        $tree.on('ready.jstree', function() {
            const dept = findDeptByCode(deptTreeData, selectedDeptCode);
            if (dept) {
                $tree.jstree(true).select_node(dept.id);
            }
        });
    }
}

// 更新顯示
function updateDeptDisplay() {
    const $display = $('#dept-display');
    const $input = $('#department_code_input');
    const $clearBtn = $('#dept-clear-btn');

    if (selectedDeptCode && selectedDeptName) {
        $display.text(selectedDeptName).removeClass('empty');
        $input.val(selectedDeptCode);
        $clearBtn.show();
    } else {
        $display.text('點擊選擇部門').addClass('empty');
        $input.val('');
        $clearBtn.hide();
    }
}

// 開關選擇器
function toggleDeptPicker() {
    const $picker = $('#dept-tree-picker');
    if ($picker.is(':visible')) {
        closeDeptPicker();
    } else {
        openDeptPicker();
    }
}

function openDeptPicker() {
    initDeptTree();
    $('#dept-tree-picker').show();
}

function closeDeptPicker() {
    $('#dept-tree-picker').hide();
}

// 清除選擇
function clearDeptSelection() {
    selectedDeptCode = '';
    selectedDeptName = '';
    updateDeptDisplay();

    // 取消 jstree 的選中狀態
    const $tree = $('#dept-tree-select');
    if ($tree.jstree(true)) {
        $tree.jstree(true).deselect_all();
    }
}

// 點擊外部關閉選擇器
$(document).on('click', function(e) {
    const $container = $('#dept-selector-container');
    if (!$container.is(e.target) && $container.has(e.target).length === 0) {
        closeDeptPicker();
    }
});

// 頁面載入後初始化（如果有預設值）
$(document).ready(function() {
    if (selectedDeptCode) {
        initDeptTree();
    }
});
