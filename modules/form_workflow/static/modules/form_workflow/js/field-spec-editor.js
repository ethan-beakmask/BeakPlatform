/**
 * field-spec-editor.js -- 欄位規格編輯器
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
    const t = FORMIO_TYPES.find(x => x.value === formioType);
    return t ? t.pgDefault : 'TEXT';
}

function fieldSpecEditor() {
    return {
        formTemplateSc: window.__SPEC_CONFIG.formTemplateSecureCode,
        formTemplateName: '',
        specVersion: null,
        specStatus: null,

        fields: [],
        loading: true,
        saving: false,

        // 編輯 modal
        showFieldModal: false,
        editingIndex: -1,
        fieldForm: _emptyField(),

        // options 編輯
        optionRows: [],

        // grid children 編輯
        gridChildRows: [],

        // 比對結果
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

        // drag
        dragIndex: -1,

        async init() {
            await this.loadTemplateName();
            await this.loadSpec();
        },

        async loadTemplateName() {
            try {
                const res = await fetch(`/api/form-workflow/templates/${this.formTemplateSc}`);
                const data = await res.json();
                if (data.success && data.data) {
                    this.formTemplateName = data.data.name || '';
                }
            } catch (e) {
                console.error('loadTemplateName:', e);
            }
        },

        async loadSpec() {
            this.loading = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}`);
                const data = await res.json();
                if (data.success && data.data) {
                    this.fields = data.data.fields || [];
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
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields: this.fields }),
                });
                const data = await res.json();
                if (data.success) {
                    this.specVersion = data.data.version;
                    this.specStatus = data.data.status;
                    this.fields = data.data.fields || this.fields;
                    _toast('success', data.message || '已儲存');
                } else {
                    _toast('error', data.error || '儲存失敗');
                }
            } catch (e) {
                _toast('error', '儲存失敗: ' + e.message);
            }
            this.saving = false;
        },

        // --- 同步自 FormIO ---
        async syncFromFormio() {
            if (!confirm('從 FormIO schema 同步會覆蓋目前的規格，確認?')) return;
            this.saving = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}/sync-from-formio`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                const data = await res.json();
                if (data.success) {
                    this.fields = data.data.fields || [];
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

        // --- 套用到表單 ---
        async applyToForm(mode) {
            const msg = mode === 'preview'
                ? '產生預覽...'
                : '套用到表單將修改 FormIO schema，確認?';
            if (mode !== 'preview' && !confirm(msg)) return;

            this.saving = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}/apply-to-form`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode }),
                });
                const data = await res.json();
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

        // --- 生成 FormIO 預覽 ---
        async generatePreview() {
            this.previewing = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}/generate-formio`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                const data = await res.json();
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

        // --- 三向比對 ---
        async runCompare() {
            this.comparing = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}/compare`);
                const data = await res.json();
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

        // --- 歷史 ---
        async loadHistory() {
            this.historyLoading = true;
            try {
                const res = await fetch(`/api/form-workflow/specs/${this.formTemplateSc}/history`);
                const data = await res.json();
                if (data.success) {
                    this.histories = data.data.histories || [];
                    this.showHistory = true;
                }
            } catch (e) {
                _toast('error', '載入歷史失敗');
            }
            this.historyLoading = false;
        },

        // --- 欄位 CRUD ---
        openAddField() {
            this.editingIndex = -1;
            this.fieldForm = _emptyField();
            this.optionRows = [];
            this.gridChildRows = [];
            this.showFieldModal = true;
        },

        openEditField(idx) {
            this.editingIndex = idx;
            const f = JSON.parse(JSON.stringify(this.fields[idx]));
            this.fieldForm = f;
            this.optionRows = (f.options || []).map(o => ({...o}));
            this.gridChildRows = (f.grid_children || []).map(c => ({...c}));
            this.showFieldModal = true;
        },

        saveField() {
            const f = this.fieldForm;
            if (!f.field_key || !f.field_key.trim()) {
                _toast('error', 'Field Key 為必填');
                return;
            }
            if (!f.formio_type) {
                _toast('error', 'FormIO Type 為必填');
                return;
            }

            // 自動填入 pg_type
            if (!f.pg_type) {
                f.pg_type = getPgDefault(f.formio_type);
            }

            // options
            f.options = this.optionRows.filter(o => o.value || o.label).length > 0
                ? this.optionRows.filter(o => o.value || o.label)
                : null;

            // grid_children
            f.grid_children = this.gridChildRows.length > 0
                ? this.gridChildRows
                : null;

            if (this.editingIndex >= 0) {
                this.fields[this.editingIndex] = JSON.parse(JSON.stringify(f));
            } else {
                // 檢查重複
                if (this.fields.some(x => x.field_key === f.field_key.trim())) {
                    _toast('error', 'Field Key "' + f.field_key + '" 已存在');
                    return;
                }
                f.sort_order = this.fields.length;
                this.fields.push(JSON.parse(JSON.stringify(f)));
            }
            this.showFieldModal = false;
        },

        removeField(idx) {
            if (confirm('確定移除此欄位?')) {
                this.fields.splice(idx, 1);
            }
        },

        // --- Options 管理 ---
        addOptionRow() {
            this.optionRows.push({ label: '', value: '' });
        },

        removeOptionRow(idx) {
            this.optionRows.splice(idx, 1);
        },

        // --- Grid Children 管理 ---
        addGridChild() {
            this.gridChildRows.push(_emptyField());
        },

        removeGridChild(idx) {
            this.gridChildRows.splice(idx, 1);
        },

        // --- FormIO Type 變更時自動推導 pgType ---
        onFormioTypeChange() {
            this.fieldForm.pg_type = getPgDefault(this.fieldForm.formio_type);
        },

        // --- 拖曳排序 ---
        dragStart(idx) {
            this.dragIndex = idx;
        },

        dragOver(idx, event) {
            event.preventDefault();
        },

        drop(idx) {
            if (this.dragIndex < 0 || this.dragIndex === idx) return;
            const item = this.fields.splice(this.dragIndex, 1)[0];
            this.fields.splice(idx, 0, item);
            // 更新 sort_order
            this.fields.forEach((f, i) => { f.sort_order = i; });
            this.dragIndex = -1;
        },

        dragEnd() {
            this.dragIndex = -1;
        },

        // --- 工具 ---
        getFormioLabel(type) {
            const t = FORMIO_TYPES.find(x => x.value === type);
            return t ? t.label : type;
        },

        formatDate(iso) {
            if (!iso) return '-';
            const d = new Date(iso);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        },

        getDiffSummary(diff) {
            if (!diff) return '';
            const parts = [];
            if (diff.added && diff.added.length) parts.push('+' + diff.added.length);
            if (diff.modified && diff.modified.length) parts.push('~' + diff.modified.length);
            if (diff.removed && diff.removed.length) parts.push('-' + diff.removed.length);
            return parts.join(' / ');
        },
    };
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
    // 簡易 toast
    const el = document.createElement('div');
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
    setTimeout(() => el.remove(), 3500);
}
