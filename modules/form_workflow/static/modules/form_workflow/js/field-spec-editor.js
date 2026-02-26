/**
 * field-spec-editor.js -- 欄位規格編輯器 (Excel-like Grid)
 * Alpine.js component
 */

const FORMIO_TYPES = [
    { value: 'textfield', label: '文字', pgDefault: 'VARCHAR(500)' },
    { value: 'textarea', label: '多行文字', pgDefault: 'TEXT' },
    { value: 'number', label: '數字', pgDefault: 'NUMERIC' },
    { value: 'checkbox', label: '核取方塊', pgDefault: 'BOOLEAN' },
    { value: 'day', label: '日期', pgDefault: 'DATE' },
    { value: 'datetime', label: '日期時間', pgDefault: 'TIMESTAMP' },
    { value: 'email', label: '電子郵件', pgDefault: 'VARCHAR(200)' },
    { value: 'phoneNumber', label: '電話', pgDefault: 'VARCHAR(50)' },
    { value: 'select', label: '下拉選單', pgDefault: 'VARCHAR(500)' },
    { value: 'radio', label: '單選按鈕', pgDefault: 'VARCHAR(200)' },
    { value: 'selectboxes', label: '複選框', pgDefault: 'JSONB' },
    { value: 'file', label: '檔案', pgDefault: 'JSONB' },
    { value: 'signature', label: '簽名', pgDefault: 'TEXT' },
    { value: 'hidden', label: '隱藏', pgDefault: 'TEXT' },
    { value: 'currency', label: '貨幣', pgDefault: 'NUMERIC(15,2)' },
    { value: 'url', label: 'URL', pgDefault: 'VARCHAR(1000)' },
    { value: 'tags', label: '標籤', pgDefault: 'JSONB' },
    { value: 'datagrid', label: '資料表格', pgDefault: 'JSONB' },
    { value: 'editgrid', label: '編輯表格', pgDefault: 'JSONB' },
];

function getPgDefault(formioType) {
    var t = FORMIO_TYPES.find(function(x) { return x.value === formioType; });
    return t ? t.pgDefault : 'TEXT';
}

function fieldSpecEditor() {
    return {
        formTemplateSc: window.__SPEC_CONFIG.formTemplateSecureCode,
        formTemplateName: '',
        specVersion: null,
        specStatus: null,

        // standalone 模式
        mode: window.__SPEC_CONFIG.mode || 'template',
        specSc: window.__SPEC_CONFIG.specSc || '',
        specName: '',

        fields: [],
        loading: true,
        saving: false,

        // 底部空白列
        newRow: _emptyField(),

        // 進階設定 Modal
        showDetailModal: false,
        detailIndex: -1,
        detailForm: {},
        detailOptionRows: [],
        detailGridChildRows: [],

        // 比對
        showCompare: false,
        compareResult: null,
        comparing: false,

        // 歷史
        showHistory: false,
        histories: [],
        historyLoading: false,

        // 預覽
        showPreview: false,
        previewSchema: null,
        previewing: false,

        // 拖曳
        dragIndex: -1,

        // 關聯表單 Modal
        showLinkModal: false,
        linkTemplates: [],
        linkTemplateSc: null,
        linkLoading: false,

        // 給 template 使用
        FORMIO_TYPES: FORMIO_TYPES,

        get isStandalone() {
            return this.mode === 'standalone';
        },

        get apiBase() {
            if (this.isStandalone && this.specSc) {
                return '/api/form-workflow/specs/standalone/' + this.specSc;
            }
            return '/api/form-workflow/specs/' + this.formTemplateSc;
        },

        async init() {
            if (this.isStandalone) {
                await this.loadStandaloneSpec();
            } else {
                await this.loadTemplateName();
                await this.loadSpec();
            }
        },

        // ===== API 方法 =====

        async loadTemplateName() {
            try {
                var res = await fetch('/api/form-workflow/templates/' + this.formTemplateSc);
                var data = await res.json();
                if (data.success && data.data) {
                    this.formTemplateName = data.data.name || '';
                }
            } catch (e) {
                console.error('loadTemplateName:', e);
            }
        },

        async loadStandaloneSpec() {
            this.loading = true;
            if (!this.specSc) {
                // 新建模式
                this.fields = [];
                this.specVersion = null;
                this.loading = false;
                return;
            }
            try {
                var res = await fetch('/api/form-workflow/specs/standalone/' + this.specSc);
                var data = await res.json();
                if (data.success && data.data) {
                    this.fields = _normalizeFields(data.data.fields || []);
                    this.specVersion = data.data.version;
                    this.specStatus = data.data.status;
                    this.specName = data.data.name || '';
                    this.formTemplateName = data.data.name || '(獨立規格)';
                    if (data.data.form_template_secure_code) {
                        this.formTemplateSc = data.data.form_template_secure_code;
                    }
                }
            } catch (e) {
                console.error('loadStandaloneSpec:', e);
            }
            this.loading = false;
        },

        async loadSpec() {
            this.loading = true;
            try {
                var res = await fetch('/api/form-workflow/specs/' + this.formTemplateSc);
                var data = await res.json();
                if (data.success && data.data) {
                    this.fields = _normalizeFields(data.data.fields || []);
                    this.specVersion = data.data.version;
                    this.specStatus = data.data.status;
                } else {
                    this.fields = [];
                    this.specVersion = null;
                    this.specStatus = null;
                }
            } catch (e) {
                console.error('loadSpec:', e);
            }
            this.loading = false;
        },

        async saveSpec() {
            this.saving = true;
            try {
                // 過濾空白列，清除內部 flag
                var cleanFields = this.fields
                    .filter(function(f) { return f.field_key && f.field_key.trim(); })
                    .map(function(f) {
                        var copy = JSON.parse(JSON.stringify(f));
                        delete copy._pgTypeOverridden;
                        return copy;
                    });

                var url, body;
                if (this.isStandalone && !this.specSc) {
                    // 新建獨立 spec
                    if (!this.specName || !this.specName.trim()) {
                        _toast('error', '請輸入規格名稱');
                        this.saving = false;
                        return;
                    }
                    url = '/api/form-workflow/specs/standalone';
                    body = JSON.stringify({ name: this.specName, fields: cleanFields });
                } else if (this.isStandalone && this.specSc) {
                    url = '/api/form-workflow/specs/standalone/' + this.specSc;
                    body = JSON.stringify({ name: this.specName, fields: cleanFields });
                } else {
                    url = '/api/form-workflow/specs/' + this.formTemplateSc;
                    body = JSON.stringify({ fields: cleanFields });
                }

                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: body,
                });
                var data = await res.json();
                if (data.success) {
                    this.specVersion = data.data.version;
                    this.specStatus = data.data.status;
                    this.fields = _normalizeFields(data.data.fields || cleanFields);
                    if (this.isStandalone && !this.specSc && data.data.secure_code) {
                        this.specSc = data.data.secure_code;
                        // 更新 URL 不重載頁面
                        history.replaceState(null, '', '/forms/data-specs/' + this.specSc + '/edit');
                    }
                    _toast('success', data.message || '已儲存');
                } else {
                    _toast('error', data.error || '儲存失敗');
                }
            } catch (e) {
                _toast('error', '儲存失敗: ' + e.message);
            }
            this.saving = false;
        },

        async syncFromFormio() {
            if (!confirm('從 FormIO schema 同步會覆蓋目前的規格，確認?')) return;
            this.saving = true;
            try {
                var res = await fetch('/api/form-workflow/specs/' + this.formTemplateSc + '/sync-from-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var data = await res.json();
                if (data.success) {
                    this.fields = _normalizeFields(data.data.fields || []);
                    this.specVersion = data.data.version;
                    _toast('success', data.message || '已同步');
                } else {
                    _toast('error', data.error || '同步失敗');
                }
            } catch (e) {
                _toast('error', '同步失敗: ' + e.message);
            }
            this.saving = false;
        },

        async applyToForm(mode) {
            if (mode !== 'preview' && !confirm('套用到表單將修改 FormIO schema，確認?')) return;
            this.saving = true;
            try {
                var res = await fetch('/api/form-workflow/specs/' + this.formTemplateSc + '/apply-to-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: mode }),
                });
                var data = await res.json();
                if (data.success) {
                    if (mode === 'preview') {
                        this.previewSchema = data.data.schema;
                        this.showPreview = true;
                    } else {
                        _toast('success', data.message || '已套用');
                    }
                } else {
                    _toast('error', data.error || '操作失敗');
                }
            } catch (e) {
                _toast('error', '操作失敗: ' + e.message);
            }
            this.saving = false;
        },

        async generatePreview() {
            this.previewing = true;
            try {
                var res = await fetch('/api/form-workflow/specs/' + this.formTemplateSc + '/generate-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var data = await res.json();
                if (data.success) {
                    this.previewSchema = data.data.schema;
                    this.showPreview = true;
                } else {
                    _toast('error', data.error || '預覽失敗');
                }
            } catch (e) {
                _toast('error', '預覽失敗: ' + e.message);
            }
            this.previewing = false;
        },

        async runCompare() {
            this.comparing = true;
            try {
                var res = await fetch('/api/form-workflow/specs/' + this.formTemplateSc + '/compare');
                var data = await res.json();
                if (data.success) {
                    this.compareResult = data.data;
                    this.showCompare = true;
                } else {
                    _toast('error', data.error || '比對失敗');
                }
            } catch (e) {
                _toast('error', '比對失敗: ' + e.message);
            }
            this.comparing = false;
        },

        async loadHistory() {
            this.historyLoading = true;
            try {
                var url;
                if (this.isStandalone && this.specSc) {
                    url = '/api/form-workflow/specs/standalone/' + this.specSc + '/history';
                } else {
                    url = '/api/form-workflow/specs/' + this.formTemplateSc + '/history';
                }
                var res = await fetch(url);
                var data = await res.json();
                if (data.success) {
                    this.histories = data.data.histories || [];
                    this.showHistory = true;
                }
            } catch (e) {
                _toast('error', '載入歷史失敗');
            }
            this.historyLoading = false;
        },

        // ===== Standalone: 關聯表單 =====

        async openLinkForm() {
            this.showLinkModal = true;
            this.linkTemplateSc = null;
            this.linkLoading = true;
            try {
                var res = await fetch('/api/form-workflow/specs/available-templates');
                var data = await res.json();
                if (data.success) {
                    this.linkTemplates = data.data || [];
                }
            } catch (e) {
                _toast('error', '載入範本失敗');
            }
            this.linkLoading = false;
        },

        async confirmLinkForm() {
            if (!this.linkTemplateSc || !this.specSc) return;
            try {
                var res = await fetch('/api/form-workflow/specs/standalone/' + this.specSc + '/link-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ form_template_secure_code: this.linkTemplateSc }),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已關聯');
                    this.formTemplateSc = this.linkTemplateSc;
                    this.showLinkModal = false;
                } else {
                    _toast('error', data.error || '關聯失敗');
                }
            } catch (e) {
                _toast('error', '關聯失敗: ' + e.message);
            }
        },

        async createFormFromSpec() {
            if (!this.specSc) return;
            var formName = prompt('請輸入新表單名稱:', this.specName || '');
            if (!formName) return;
            try {
                var res = await fetch('/api/form-workflow/specs/standalone/' + this.specSc + '/create-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: formName }),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已建立表單');
                    if (data.data && data.data.form_template) {
                        this.formTemplateSc = data.data.form_template.secure_code;
                    }
                } else {
                    _toast('error', data.error || '建立失敗');
                }
            } catch (e) {
                _toast('error', '建立失敗: ' + e.message);
            }
        },

        // ===== Inline Grid 操作 =====

        commitNewRow() {
            if (!this.newRow.field_key || !this.newRow.field_key.trim()) return;
            var key = this.newRow.field_key.trim();
            if (this.fields.some(function(f) { return f.field_key === key; })) {
                _toast('error', 'Field Key "' + key + '" 已存在');
                return;
            }
            this.newRow.field_key = key;
            this.newRow.sort_order = this.fields.length;
            if (!this.newRow.pg_type) {
                this.newRow.pg_type = getPgDefault(this.newRow.formio_type);
            }
            this.fields.push(JSON.parse(JSON.stringify(this.newRow)));
            this.newRow = _emptyField();
        },

        removeField(idx) {
            this.fields.splice(idx, 1);
            this.fields.forEach(function(f, i) { f.sort_order = i; });
        },

        onTypeChange(idx) {
            var f = this.fields[idx];
            if (!f._pgTypeOverridden) {
                f.pg_type = getPgDefault(f.formio_type);
            }
        },

        onPgTypeInput(idx) {
            this.fields[idx]._pgTypeOverridden = true;
        },

        onNewRowTypeChange() {
            this.newRow.pg_type = getPgDefault(this.newRow.formio_type);
        },

        // ===== 進階設定 Modal =====

        openDetail(idx) {
            this.detailIndex = idx;
            var f = JSON.parse(JSON.stringify(this.fields[idx]));
            this.detailForm = f;
            this.detailOptionRows = (f.options || []).map(function(o) { return {label: o.label || '', value: o.value || ''}; });
            this.detailGridChildRows = (f.grid_children || []).map(function(c) { return JSON.parse(JSON.stringify(c)); });
            this.showDetailModal = true;
        },

        saveDetail() {
            var f = this.detailForm;
            var filteredOptions = this.detailOptionRows.filter(function(o) { return o.value || o.label; });
            f.options = filteredOptions.length > 0 ? filteredOptions : null;
            f.grid_children = this.detailGridChildRows.length > 0 ? this.detailGridChildRows : null;

            // 回寫進階欄位到 fields 陣列
            var target = this.fields[this.detailIndex];
            target.constraints = JSON.parse(JSON.stringify(f.constraints));
            target.default_value = f.default_value;
            target.options = f.options ? JSON.parse(JSON.stringify(f.options)) : null;
            target.grid_children = f.grid_children ? JSON.parse(JSON.stringify(f.grid_children)) : null;
            this.showDetailModal = false;
            _toast('success', '進階設定已更新');
        },

        closeDetail() {
            this.showDetailModal = false;
        },

        addDetailOption() {
            this.detailOptionRows.push({ label: '', value: '' });
        },

        removeDetailOption(idx) {
            this.detailOptionRows.splice(idx, 1);
        },

        addDetailGridChild() {
            this.detailGridChildRows.push(_emptyField());
        },

        removeDetailGridChild(idx) {
            this.detailGridChildRows.splice(idx, 1);
        },

        // ===== 拖曳排序 =====

        dragStart(idx) {
            this.dragIndex = idx;
        },

        dragOver(idx, event) {
            event.preventDefault();
        },

        drop(idx) {
            if (this.dragIndex < 0 || this.dragIndex === idx) return;
            var item = this.fields.splice(this.dragIndex, 1)[0];
            this.fields.splice(idx, 0, item);
            this.fields.forEach(function(f, i) { f.sort_order = i; });
            this.dragIndex = -1;
        },

        dragEnd() {
            this.dragIndex = -1;
        },

        // ===== 工具 =====

        getFormioLabel(type) {
            var t = FORMIO_TYPES.find(function(x) { return x.value === type; });
            return t ? t.label : type;
        },

        formatDate(iso) {
            if (!iso) return '-';
            var d = new Date(iso);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        },

        getDiffSummary(diff) {
            if (!diff) return '';
            var parts = [];
            if (diff.added && diff.added.length) parts.push('+' + diff.added.length);
            if (diff.modified && diff.modified.length) parts.push('~' + diff.modified.length);
            if (diff.removed && diff.removed.length) parts.push('-' + diff.removed.length);
            return parts.join(' / ');
        },
    };
}

/** 確保每個 field 的 constraints 物件完整 */
function _normalizeFields(fields) {
    return fields.map(function(f) {
        f.constraints = Object.assign({
            required: false,
            maxLength: null,
            minLength: null,
            min: null,
            max: null,
            pattern: null,
            customValidation: null,
        }, f.constraints || {});
        return f;
    });
}

function _emptyField() {
    return {
        field_key: '',
        label: '',
        formio_type: 'textfield',
        pg_type: 'VARCHAR(500)',
        constraints: {
            required: false,
            maxLength: null,
            minLength: null,
            min: null,
            max: null,
            pattern: null,
            customValidation: null,
        },
        is_pii: false,
        description: '',
        default_value: null,
        options: null,
        grid_children: null,
        sort_order: 0,
    };
}

function _toast(type, msg) {
    var el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;padding:10px 18px;border-radius:4px;font-size:13px;max-width:400px;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    if (type === 'success') {
        el.style.background = '#d1fae5';
        el.style.color = '#065f46';
        el.style.border = '1px solid #6ee7b7';
    } else if (type === 'error') {
        el.style.background = '#fee2e2';
        el.style.color = '#991b1b';
        el.style.border = '1px solid #fca5a5';
    } else {
        el.style.background = '#e0e7ff';
        el.style.color = '#3730a3';
        el.style.border = '1px solid #a5b4fc';
    }
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function() { el.remove(); }, 3500);
}
