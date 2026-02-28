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

        // (已移除 newRow 單列機制，改用 addEmptyRows 批次新增)

        // 進階設定 Modal
        showDetailModal: false,
        detailIndex: -1,
        detailForm: { constraints: { required: false, maxLength: null, minLength: null, min: null, max: null, pattern: null, customValidation: null } },
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
        historyPreview: null,  // 正在檢視的歷史版本
        historyRestoring: false,

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

        // 建立表單 Modal
        showCreateFormModal: false,
        createFormName: '',
        createFormCategorySc: '',
        createFormCategories: [],
        createFormLoading: false,

        // SQL Table 操作
        sqlLoading: false,
        showSqlTableModal: false,
        sqlTables: [],
        selectedSqlTable: '',
        showSqlApplyModal: false,
        sqlApplyPreview: null,

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
                // 新建模式，預設 10 列空白欄位
                this.fields = [];
                this.addEmptyRows(10);
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
                // 驗證已填寫的欄位（有 field_key 的列）
                var filledFields = this.fields.filter(function(f) {
                    return f.field_key && f.field_key.trim();
                });
                if (filledFields.length === 0) {
                    _toast('error', '至少需要一個已設定 Field Key 的欄位');
                    this.saving = false;
                    return;
                }
                // 檢查必填欄位完整性
                var errors = [];
                var keySet = {};
                for (var i = 0; i < filledFields.length; i++) {
                    var f = filledFields[i];
                    var rowNum = this.fields.indexOf(f) + 1;
                    if (!f.label || !f.label.trim()) {
                        errors.push('第 ' + rowNum + ' 列缺少 Label');
                    }
                    var key = f.field_key.trim();
                    if (keySet[key]) {
                        errors.push('第 ' + rowNum + ' 列 Field Key "' + key + '" 重複');
                    }
                    keySet[key] = true;
                }
                if (errors.length > 0) {
                    _toast('error', errors.join('；'));
                    this.saving = false;
                    return;
                }
                // 過濾空白列，清除內部 flag
                var cleanFields = filledFields
                    .map(function(f) {
                        var copy = JSON.parse(JSON.stringify(f));
                        delete copy._pgTypeOverridden;
                        delete copy._uid;
                        copy.field_key = copy.field_key.trim();
                        copy.label = copy.label.trim();
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
                    this.fields = _normalizeFields(data.data.fields || cleanFields, this.fields);
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
                    this.fields = _normalizeFields(data.data.fields || [], this.fields);
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

        previewHistoryVersion(h) {
            this.historyPreview = h;
        },

        closeHistoryPreview() {
            this.historyPreview = null;
        },

        async restoreAsNewVersion(h) {
            if (!confirm('確定要以 v' + h.version + ' 的欄位建立新版本？')) return;
            this.historyRestoring = true;
            try {
                var fields = h.fields_snapshot || [];
                var url, body;
                if (this.isStandalone && this.specSc) {
                    url = '/api/form-workflow/specs/standalone/' + this.specSc;
                    body = { fields: fields, description: '從 v' + h.version + ' 取回建立' };
                } else {
                    url = '/api/form-workflow/specs/' + this.formTemplateSc;
                    body = { fields: fields, description: '從 v' + h.version + ' 取回建立' };
                }
                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已從 v' + h.version + ' 建立新版');
                    this.historyPreview = null;
                    this.showHistory = false;
                    // 重新載入
                    this.fields = _normalizeFields(data.data.fields || [], this.fields);
                    this.specVersion = data.data.version;
                    this.dirty = false;
                } else {
                    _toast('error', data.error || '取回失敗');
                }
            } catch (e) {
                _toast('error', '取回失敗: ' + e.message);
            }
            this.historyRestoring = false;
        },

        async applyHistoryToForm(h) {
            if (this.isStandalone) {
                _toast('error', '獨立規格無綁定表單，無法套用');
                return;
            }
            if (!confirm('確定要將 v' + h.version + ' 的欄位套用到表單設計？\n（發行機制確保既有 SQL 表不受影響）')) return;
            this.historyRestoring = true;
            try {
                // 先取回為新版
                var saveRes = await fetch('/api/form-workflow/specs/' + this.formTemplateSc, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        fields: h.fields_snapshot || [],
                        description: '從 v' + h.version + ' 取回並套用到表單',
                    }),
                });
                var saveData = await saveRes.json();
                if (!saveData.success) {
                    _toast('error', saveData.error || '儲存新版失敗');
                    this.historyRestoring = false;
                    return;
                }

                // 套用到表單
                var applyRes = await fetch('/api/form-workflow/specs/' + this.formTemplateSc + '/sync-spec-to-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var applyData = await applyRes.json();
                if (applyData.success) {
                    _toast('success', '已從 v' + h.version + ' 取回並套用到表單設計');
                    this.historyPreview = null;
                    this.showHistory = false;
                    this.fields = _normalizeFields(saveData.data.fields || [], this.fields);
                    this.specVersion = saveData.data.version;
                    this.dirty = false;
                } else {
                    _toast('error', applyData.error || '套用到表單失敗');
                }
            } catch (e) {
                _toast('error', '操作失敗: ' + e.message);
            }
            this.historyRestoring = false;
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

        async openCreateFormModal() {
            if (!this.specSc) return;
            this.createFormName = this.specName || '';
            this.createFormCategorySc = '';
            this.createFormCategories = [];
            this.showCreateFormModal = true;
            this.createFormLoading = true;
            try {
                var res = await fetch('/api/form-workflow/categories?context=form_design&flat=1');
                var data = await res.json();
                if (data.success) {
                    this.createFormCategories = data.data || [];
                    if (this.createFormCategories.length > 0) {
                        this.createFormCategorySc = this.createFormCategories[0].secure_code;
                    }
                }
            } catch (e) { /* silent */ }
            this.createFormLoading = false;
        },

        async confirmCreateForm() {
            if (!this.specSc || !this.createFormName.trim()) return;
            this.saving = true;
            try {
                var body = { name: this.createFormName.trim() };
                if (this.createFormCategorySc) {
                    body.category_secure_code = this.createFormCategorySc;
                }
                var res = await fetch('/api/form-workflow/specs/standalone/' + this.specSc + '/create-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已建立表單');
                    this.showCreateFormModal = false;
                    if (data.data && data.data.form_template) {
                        this.formTemplateSc = data.data.form_template.secure_code;
                    }
                } else {
                    _toast('error', data.error || '建立失敗');
                }
            } catch (e) {
                _toast('error', '建立失敗: ' + e.message);
            }
            this.saving = false;
        },

        // ===== SQL Table 操作 =====

        async openSyncFromSqlModal() {
            this.sqlLoading = true;
            this.selectedSqlTable = '';
            this.sqlTables = [];
            this.showSqlTableModal = true;
            try {
                var res = await fetch('/api/form-workflow/specs/sql-tables');
                var data = await res.json();
                if (data.success) {
                    this.sqlTables = data.data || [];
                } else {
                    _toast('error', data.error || '載入失敗');
                }
            } catch (e) {
                _toast('error', '載入失敗: ' + e.message);
            }
            this.sqlLoading = false;
        },

        async confirmSyncFromSql() {
            if (!this.selectedSqlTable) return;
            this.sqlLoading = true;
            try {
                var url = this.apiBase + '/sync-from-sql-table';
                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ table_name: this.selectedSqlTable }),
                });
                var data = await res.json();
                if (data.success && data.data && data.data.fields) {
                    this.fields = _normalizeFields(data.data.fields, this.fields);
                    this.showSqlTableModal = false;
                    _toast('success', data.message || '欄位已匯入');
                } else {
                    _toast('error', data.error || '匯入失敗');
                }
            } catch (e) {
                _toast('error', '匯入失敗: ' + e.message);
            }
            this.sqlLoading = false;
        },

        async applyToSqlTable() {
            if (!this.specVersion) {
                _toast('error', '請先儲存規格');
                return;
            }
            this.sqlLoading = true;
            this.sqlApplyPreview = null;
            try {
                var url = this.apiBase + '/apply-to-sql-table';
                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: false }),
                });
                var data = await res.json();
                if (data.success) {
                    this.sqlApplyPreview = data.data;
                    this.showSqlApplyModal = true;
                } else {
                    _toast('error', data.error || '預覽失敗');
                }
            } catch (e) {
                _toast('error', '預覽失敗: ' + e.message);
            }
            this.sqlLoading = false;
        },

        async confirmApplyToSql() {
            this.sqlLoading = true;
            try {
                var url = this.apiBase + '/apply-to-sql-table';
                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showSqlApplyModal = false;
                    var action = data.data.action;
                    if (action === 'create') {
                        _toast('success', '已建立 SQL Table: ' + data.data.table_name);
                    } else if (action === 'alter') {
                        _toast('success', '已更新 SQL Table: ' + data.data.table_name);
                    } else {
                        _toast('info', '表結構無需變更');
                    }
                } else {
                    _toast('error', data.error || '執行失敗');
                }
            } catch (e) {
                _toast('error', '執行失敗: ' + e.message);
            }
            this.sqlLoading = false;
        },

        // ===== Inline Grid 操作 =====

        addEmptyRows(count) {
            for (var i = 0; i < count; i++) {
                var row = _emptyField();
                row.sort_order = this.fields.length;
                this.fields.push(row);
            }
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


        // ===== 進階設定 Modal =====

        openDetail(idx) {
            this.detailIndex = idx;
            var f = JSON.parse(JSON.stringify(this.fields[idx]));
            // 確保 constraints 物件存在
            if (!f.constraints || typeof f.constraints !== 'object') {
                f.constraints = {};
            }
            var dc = f.constraints;
            if (dc.required === undefined) dc.required = false;
            if (dc.maxLength === undefined) dc.maxLength = null;
            if (dc.minLength === undefined) dc.minLength = null;
            if (dc.min === undefined) dc.min = null;
            if (dc.max === undefined) dc.max = null;
            if (dc.pattern === undefined) dc.pattern = null;
            if (dc.customValidation === undefined) dc.customValidation = null;
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

/**
 * 確保每個 field 的 constraints 物件完整
 *
 * @param {Array} fields - 新的 fields 陣列
 * @param {Array} [oldFields] - 可選，舊 fields 陣列。傳入時會按索引保留舊 _uid，
 *   避免 Alpine.js 銷毀重建 <select>（重建時 x-model 在 x-for options
 *   建立前觸發，導致 formio_type 被重設為第一個選項 textfield）
 */
function _normalizeFields(fields, oldFields) {
    return fields.map(function(f, i) {
        if (!f._uid) {
            f._uid = (oldFields && i < oldFields.length && oldFields[i]._uid)
                ? oldFields[i]._uid
                : _nextUid();
        }
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

var _uidCounter = 0;
function _nextUid() { return '__uid_' + (++_uidCounter) + '_' + Date.now(); }

function _emptyField() {
    return {
        _uid: _nextUid(),
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
