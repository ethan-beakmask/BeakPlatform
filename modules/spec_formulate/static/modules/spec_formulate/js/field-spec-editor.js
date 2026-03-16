/**
 * field-spec-editor.js -- 欄位規格編輯器
 * Alpine.js + Tabulator 6.x 整合
 *
 * 架構:
 * - Tabulator 管理欄位 Grid (inline editing, drag reorder)
 * - Alpine.js 管理 UI 狀態 (toolbar, modals, panels)
 * - 資料流: API -> Alpine -> Tabulator (載入) / Tabulator -> Alpine -> API (儲存)
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

// Type value -> label map for Tabulator list editor
const _TYPE_VALUES = {};
FORMIO_TYPES.forEach(function(t) { _TYPE_VALUES[t.value] = t.label; });

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

        mode: window.__SPEC_CONFIG.mode || 'template',
        specSc: window.__SPEC_CONFIG.specSc || '',
        specName: '',

        fields: [],
        loading: true,
        saving: false,

        // Tabulator instance
        gridTable: null,

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
        historyPreview: null,
        historyRestoring: false,

        // 預覽
        showPreview: false,
        previewSchema: null,
        previewing: false,

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

        // Lookup 類別
        lookupCategories: [],
        lookupPreviewItems: [],
        lookupPreviewLoading: false,

        // 檔案讀取
        fileReading: false,


        FORMIO_TYPES: FORMIO_TYPES,

        get isStandalone() {
            return this.mode === 'standalone';
        },

        get apiBase() {
            if (this.isStandalone && this.specSc) {
                return '/api/spec-formulate/specs/standalone/' + this.specSc;
            }
            return '/api/spec-formulate/specs/' + this.formTemplateSc;
        },

        get exportIdentifier() {
            if (this.isStandalone && this.specSc) return this.specSc;
            return this.formTemplateSc;
        },

        async init() {
            await this.loadLookupCategories();
            if (this.isStandalone) {
                await this.loadStandaloneSpec();
            } else {
                await this.loadTemplateName();
                await this.loadSpec();
            }
            // Grid 在載入資料後初始化
            this.$nextTick(() => { this.initGrid(); });
        },

        // ===== Tabulator Grid =====

        initGrid() {
            var self = this;
            var gridEl = document.getElementById('field-grid');
            if (!gridEl) return;

            this.gridTable = new Tabulator(gridEl, {
                data: this._fieldsToGridData(this.fields),
                layout: 'fitColumns',
                movableRows: true,
                selectable: true,
                headerSort: false,
                placeholder: '點擊工具列 [+ 欄位] 或下方按鈕新增欄位',
                rowHeight: 34,
                columns: [
                    {
                        title: '#', formatter: 'rownum', width: 50,
                        hozAlign: 'center', resizable: false,
                        rowHandle: true,
                    },
                    {
                        title: 'Label', field: 'label', editor: 'input',
                        minWidth: 120,
                    },
                    {
                        title: 'Field Key', field: 'field_key', editor: 'input',
                        minWidth: 120, cssClass: 'mono-cell',
                        validator: function(cell, value) {
                            if (!value) return true;
                            return /^[a-zA-Z0-9_]*$/.test(value);
                        },
                    },
                    {
                        title: 'Type', field: 'formio_type',
                        minWidth: 130,
                        editor: 'list',
                        editorParams: {
                            values: _TYPE_VALUES,
                            listOnEmpty: true,
                            autocomplete: true,
                        },
                        formatter: function(cell) {
                            return _TYPE_VALUES[cell.getValue()] || cell.getValue();
                        },
                        cellEdited: function(cell) {
                            // Type 改變 → 自動連動 PG Type
                            var row = cell.getRow();
                            var newPg = getPgDefault(cell.getValue());
                            row.update({ pg_type: newPg, _pgTypeOverridden: false });
                        },
                    },
                    {
                        title: 'PG Type', field: 'pg_type', editor: 'input',
                        width: 130, cssClass: 'mono-cell',
                    },
                    {
                        title: 'PII', field: 'is_pii',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 50, editor: true,
                        cellEdited: function(cell) {
                            // 更新列底色
                            var row = cell.getRow();
                            var el = row.getElement();
                            if (cell.getValue()) {
                                el.classList.add('pii-row');
                            } else {
                                el.classList.remove('pii-row');
                            }
                        },
                    },
                    {
                        title: '必填', field: 'required',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 50, editor: true,
                    },
                    {
                        title: '說明', field: 'description', editor: 'input',
                        minWidth: 150,
                    },
                    {
                        title: '操作', width: 90, hozAlign: 'center',
                        resizable: false,
                        formatter: function(cell) {
                            var div = document.createElement('div');
                            div.className = 'fs-row-actions';
                            var thisRow = cell.getRow();

                            var btnDetail = document.createElement('button');
                            btnDetail.textContent = '詳細';
                            btnDetail.addEventListener('click', function(e) {
                                e.stopPropagation();
                                // 用 getRows() 比對取得正確的 0-based index
                                var allRows = self.gridTable.getRows();
                                for (var ri = 0; ri < allRows.length; ri++) {
                                    if (allRows[ri] === thisRow) {
                                        self.openDetail(ri);
                                        return;
                                    }
                                }
                            });

                            var btnDel = document.createElement('button');
                            btnDel.textContent = 'X';
                            btnDel.className = 'danger';
                            btnDel.addEventListener('click', function(e) {
                                e.stopPropagation();
                                thisRow.delete();
                                self._syncFieldCount();
                            });

                            div.appendChild(btnDetail);
                            div.appendChild(btnDel);
                            return div;
                        },
                    },
                ],
                cellEdited: function(cell) {
                    self._syncFieldCount();
                },
                rowMoved: function() {
                    self._syncFieldCount();
                },
                dataLoaded: function() {
                    self._applyPiiRowClass();
                },
            });
        },

        _fieldsToGridData(fields) {
            return (fields || []).map(function(f, i) {
                return {
                    _uid: f._uid || '__uid_' + (++_uidCounter) + '_' + Date.now(),
                    label: f.label || '',
                    field_key: f.field_key || '',
                    formio_type: f.formio_type || 'textfield',
                    pg_type: f.pg_type || 'VARCHAR(500)',
                    is_pii: !!f.is_pii,
                    required: !!(f.constraints && f.constraints.required),
                    description: f.description || '',
                    // 保留完整的 constraints 和其他進階欄位
                    constraints: f.constraints || {},
                    default_value: f.default_value || null,
                    options: f.options || null,
                    grid_children: f.grid_children || null,
                    lookup_category_code: f.lookup_category_code || null,
                    _pgTypeOverridden: !!f._pgTypeOverridden,
                    sort_order: i,
                };
            });
        },

        _gridDataToFields() {
            if (!this.gridTable) return this.fields;
            var rows = this.gridTable.getData();
            return rows
                .filter(function(r) { return r.field_key && r.field_key.trim(); })
                .map(function(r, i) {
                    var constraints = Object.assign({}, r.constraints || {});
                    constraints.required = !!r.required;
                    return {
                        field_key: (r.field_key || '').trim(),
                        label: (r.label || '').trim(),
                        formio_type: r.formio_type || 'textfield',
                        pg_type: r.pg_type || 'TEXT',
                        constraints: constraints,
                        is_pii: !!r.is_pii,
                        description: r.description || '',
                        default_value: r.default_value || null,
                        options: r.options || null,
                        grid_children: r.grid_children || null,
                        lookup_category_code: r.lookup_category_code || null,
                        sort_order: i,
                    };
                });
        },

        _syncFieldCount() {
            if (this.gridTable) {
                this.fields = this.gridTable.getData();
            }
        },

        _applyPiiRowClass() {
            if (!this.gridTable) return;
            this.gridTable.getRows().forEach(function(row) {
                var el = row.getElement();
                if (row.getData().is_pii) {
                    el.classList.add('pii-row');
                } else {
                    el.classList.remove('pii-row');
                }
            });
        },

        _setGridData(fields) {
            this.fields = fields;
            if (this.gridTable) {
                this.gridTable.setData(this._fieldsToGridData(fields));
                this.$nextTick(() => { this._applyPiiRowClass(); });
            }
        },

        addEmptyRows(count) {
            if (!this.gridTable) return;
            for (var i = 0; i < count; i++) {
                this.gridTable.addRow({
                    _uid: '__uid_' + (++_uidCounter) + '_' + Date.now(),
                    label: '', field_key: '', formio_type: 'textfield',
                    pg_type: 'VARCHAR(500)', is_pii: false, required: false,
                    description: '', constraints: {}, default_value: null,
                    options: null, grid_children: null, lookup_category_code: null,
                    _pgTypeOverridden: false, sort_order: 0,
                });
            }
            this._syncFieldCount();
        },

        // ===== 欄位操作 =====

        addColumn() {
            if (!this.gridTable) return;
            this.gridTable.addRow({
                _uid: '__uid_' + (++_uidCounter) + '_' + Date.now(),
                label: '', field_key: '', formio_type: 'textfield',
                pg_type: 'VARCHAR(500)', is_pii: false, required: false,
                description: '', constraints: {}, default_value: null,
                options: null, grid_children: null, lookup_category_code: null,
                _pgTypeOverridden: false, sort_order: 0,
            });
            this._syncFieldCount();
        },

        deleteSelectedRows() {
            if (!this.gridTable) return;
            var selected = this.gridTable.getSelectedRows();
            if (selected.length === 0) {
                _toast('info', '請先點選要刪除的列（可按住 Ctrl 多選）');
                return;
            }
            if (!confirm('確定刪除選取的 ' + selected.length + ' 列?')) return;
            selected.forEach(function(row) { row.delete(); });
            this._syncFieldCount();
        },

        // ===== 檔案讀取 =====

        readFile(format) {
            if (format === 'excel') {
                document.getElementById('excel-file-input').click();
            } else if (format === 'csv') {
                document.getElementById('csv-file-input').click();
            }
        },

        async handleFileRead(event, format) {
            var file = event.target.files[0];
            event.target.value = '';
            if (!file) return;

            if (!confirm('讀取檔案將覆蓋目前的欄位資料，確認?')) return;

            this.fileReading = true;
            var url = '/api/spec-formulate/readers/' + format;
            var formData = new FormData();
            formData.append('file', file);

            try {
                var res = await fetch(url, { method: 'POST', body: formData });
                var data = await res.json();
                if (data.success) {
                    this._setGridData(_normalizeFields(data.data.fields));
                    _toast('success', data.message);
                } else {
                    _toast('error', data.error || '讀取失敗');
                }
            } catch (e) {
                _toast('error', '讀取失敗: ' + e.message);
            }
            this.fileReading = false;
        },

        // ===== Lookup =====

        async loadLookupCategories() {
            try {
                var res = await fetch('/api/lookup/categories');
                var data = await res.json();
                if (data.success) { this.lookupCategories = data.data || []; }
            } catch (e) { /* silent */ }
        },

        async loadLookupPreview(code) {
            if (!code) { this.lookupPreviewItems = []; return; }
            this.lookupPreviewLoading = true;
            try {
                var res = await fetch('/api/lookup/by-code/' + encodeURIComponent(code));
                var data = await res.json();
                if (data.success) { this.lookupPreviewItems = (data.data || []).slice(0, 10); }
            } catch (e) { this.lookupPreviewItems = []; }
            this.lookupPreviewLoading = false;
        },

        // ===== API 方法 =====

        async loadTemplateName() {
            try {
                var res = await fetch('/api/form-workflow/templates/' + this.formTemplateSc);
                var data = await res.json();
                if (data.success && data.data) { this.formTemplateName = data.data.name || ''; }
            } catch (e) { console.error('loadTemplateName:', e); }
        },

        async loadStandaloneSpec() {
            this.loading = true;
            if (!this.specSc) {
                this.fields = _emptyFields(10);
                this.specVersion = null;
                this.loading = false;
                return;
            }
            try {
                var res = await fetch('/api/spec-formulate/specs/standalone/' + this.specSc);
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
            } catch (e) { console.error('loadStandaloneSpec:', e); }
            this.loading = false;
        },

        async loadSpec() {
            this.loading = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc);
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
            } catch (e) { console.error('loadSpec:', e); }
            this.loading = false;
        },

        async saveSpec() {
            this.saving = true;
            try {
                var cleanFields = this._gridDataToFields();
                if (cleanFields.length === 0) {
                    _toast('error', '至少需要一個已設定 Field Key 的欄位');
                    this.saving = false;
                    return;
                }
                // 驗證
                var errors = [];
                var keySet = {};
                var keyPattern = /^[a-zA-Z0-9_]+$/;
                for (var i = 0; i < cleanFields.length; i++) {
                    var f = cleanFields[i];
                    var rowNum = i + 1;
                    if (!f.label || !f.label.trim()) {
                        errors.push('第 ' + rowNum + ' 列缺少 Label');
                    }
                    if (!keyPattern.test(f.field_key)) {
                        errors.push('第 ' + rowNum + ' 列 Field Key "' + f.field_key + '" 只能使用英文字母、數字與底線');
                    }
                    if (keySet[f.field_key]) {
                        errors.push('第 ' + rowNum + ' 列 Field Key "' + f.field_key + '" 重複');
                    }
                    keySet[f.field_key] = true;
                    var children = f.grid_children || [];
                    for (var ci = 0; ci < children.length; ci++) {
                        var ck = (children[ci].field_key || '').trim();
                        if (ck && !keyPattern.test(ck)) {
                            errors.push('第 ' + rowNum + ' 列子欄位 "' + ck + '" 格式錯誤');
                        }
                    }
                }
                if (errors.length > 0) {
                    _toast('error', errors.join('; '));
                    this.saving = false;
                    return;
                }

                var url, body;
                if (this.isStandalone && !this.specSc) {
                    if (!this.specName || !this.specName.trim()) {
                        _toast('error', '請輸入規格名稱');
                        this.saving = false;
                        return;
                    }
                    url = '/api/spec-formulate/specs/standalone';
                    body = JSON.stringify({ name: this.specName, fields: cleanFields });
                } else if (this.isStandalone && this.specSc) {
                    url = '/api/spec-formulate/specs/standalone/' + this.specSc;
                    body = JSON.stringify({ name: this.specName, fields: cleanFields });
                } else {
                    url = '/api/spec-formulate/specs/' + this.formTemplateSc;
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
                    var newFields = _normalizeFields(data.data.fields || cleanFields);
                    this._setGridData(newFields);
                    if (this.isStandalone && !this.specSc && data.data.secure_code) {
                        this.specSc = data.data.secure_code;
                        history.replaceState(null, '', '/spec-formulate/' + this.specSc + '/edit');
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
                var res = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc + '/sync-from-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var data = await res.json();
                if (data.success) {
                    var newFields = _normalizeFields(data.data.fields || []);
                    this._setGridData(newFields);
                    this.specVersion = data.data.version;
                    _toast('success', data.message || '已同步');
                } else {
                    _toast('error', data.error || '同步失敗');
                }
            } catch (e) { _toast('error', '同步失敗: ' + e.message); }
            this.saving = false;
        },

        async applyToForm(mode) {
            if (mode !== 'preview' && !confirm('套用到表單將修改 FormIO schema，確認?')) return;
            this.saving = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc + '/apply-to-form', {
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
                } else { _toast('error', data.error || '操作失敗'); }
            } catch (e) { _toast('error', '操作失敗: ' + e.message); }
            this.saving = false;
        },

        async generatePreview() {
            this.previewing = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc + '/generate-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var data = await res.json();
                if (data.success) {
                    this.previewSchema = data.data.schema;
                    this.showPreview = true;
                } else { _toast('error', data.error || '預覽失敗'); }
            } catch (e) { _toast('error', '預覽失敗: ' + e.message); }
            this.previewing = false;
        },

        async runCompare() {
            this.comparing = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc + '/compare');
                var data = await res.json();
                if (data.success) {
                    this.compareResult = data.data;
                    this.showCompare = true;
                } else { _toast('error', data.error || '比對失敗'); }
            } catch (e) { _toast('error', '比對失敗: ' + e.message); }
            this.comparing = false;
        },

        async loadHistory() {
            this.historyLoading = true;
            try {
                var url = (this.isStandalone && this.specSc)
                    ? '/api/spec-formulate/specs/standalone/' + this.specSc + '/history'
                    : '/api/spec-formulate/specs/' + this.formTemplateSc + '/history';
                var res = await fetch(url);
                var data = await res.json();
                if (data.success) {
                    this.histories = data.data.histories || [];
                    this.showHistory = true;
                }
            } catch (e) { _toast('error', '載入歷史失敗'); }
            this.historyLoading = false;
        },

        previewHistoryVersion(h) { this.historyPreview = h; },
        closeHistoryPreview() { this.historyPreview = null; },

        async restoreAsNewVersion(h) {
            if (!confirm('確定要以 v' + h.version + ' 的欄位建立新版本？')) return;
            this.historyRestoring = true;
            try {
                var url = (this.isStandalone && this.specSc)
                    ? '/api/spec-formulate/specs/standalone/' + this.specSc
                    : '/api/spec-formulate/specs/' + this.formTemplateSc;
                var res = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields: h.fields_snapshot || [], description: '從 v' + h.version + ' 取回建立' }),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已從 v' + h.version + ' 建立新版');
                    this.historyPreview = null;
                    this.showHistory = false;
                    this._setGridData(_normalizeFields(data.data.fields || []));
                    this.specVersion = data.data.version;
                } else { _toast('error', data.error || '取回失敗'); }
            } catch (e) { _toast('error', '取回失敗: ' + e.message); }
            this.historyRestoring = false;
        },

        async applyHistoryToForm(h) {
            if (this.isStandalone) { _toast('error', '獨立規格無綁定表單'); return; }
            if (!confirm('確定要將 v' + h.version + ' 套用到表單設計？')) return;
            this.historyRestoring = true;
            try {
                var saveRes = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fields: h.fields_snapshot || [], description: '從 v' + h.version + ' 取回並套用' }),
                });
                var saveData = await saveRes.json();
                if (!saveData.success) { _toast('error', saveData.error || '儲存新版失敗'); this.historyRestoring = false; return; }

                var applyRes = await fetch('/api/spec-formulate/specs/' + this.formTemplateSc + '/sync-spec-to-formio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                var applyData = await applyRes.json();
                if (applyData.success) {
                    _toast('success', '已從 v' + h.version + ' 取回並套用到表單設計');
                    this.historyPreview = null;
                    this.showHistory = false;
                    this._setGridData(_normalizeFields(saveData.data.fields || []));
                    this.specVersion = saveData.data.version;
                } else { _toast('error', applyData.error || '套用失敗'); }
            } catch (e) { _toast('error', '操作失敗: ' + e.message); }
            this.historyRestoring = false;
        },

        // ===== Standalone: 關聯/建立表單 =====

        async openLinkForm() {
            this.showLinkModal = true;
            this.linkTemplateSc = null;
            this.linkLoading = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/available-templates');
                var data = await res.json();
                if (data.success) { this.linkTemplates = data.data || []; }
            } catch (e) { _toast('error', '載入範本失敗'); }
            this.linkLoading = false;
        },

        async confirmLinkForm() {
            if (!this.linkTemplateSc || !this.specSc) return;
            try {
                var res = await fetch('/api/spec-formulate/specs/standalone/' + this.specSc + '/link-form', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ form_template_secure_code: this.linkTemplateSc }),
                });
                var data = await res.json();
                if (data.success) {
                    _toast('success', data.message || '已關聯');
                    this.formTemplateSc = this.linkTemplateSc;
                    this.showLinkModal = false;
                } else { _toast('error', data.error || '關聯失敗'); }
            } catch (e) { _toast('error', '關聯失敗: ' + e.message); }
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
                if (this.createFormCategorySc) { body.category_secure_code = this.createFormCategorySc; }
                var res = await fetch('/api/spec-formulate/specs/standalone/' + this.specSc + '/create-form', {
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
                } else { _toast('error', data.error || '建立失敗'); }
            } catch (e) { _toast('error', '建立失敗: ' + e.message); }
            this.saving = false;
        },

        // ===== SQL Table 操作 =====

        async openSyncFromSqlModal() {
            this.sqlLoading = true;
            this.selectedSqlTable = '';
            this.sqlTables = [];
            this.showSqlTableModal = true;
            try {
                var res = await fetch('/api/spec-formulate/specs/sql-tables');
                var data = await res.json();
                if (data.success) { this.sqlTables = data.data || []; }
                else { _toast('error', data.error || '載入失敗'); }
            } catch (e) { _toast('error', '載入失敗: ' + e.message); }
            this.sqlLoading = false;
        },

        async confirmSyncFromSql() {
            if (!this.selectedSqlTable) return;
            this.sqlLoading = true;
            try {
                var res = await fetch(this.apiBase + '/sync-from-sql-table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ table_name: this.selectedSqlTable }),
                });
                var data = await res.json();
                if (data.success && data.data && data.data.fields) {
                    this._setGridData(_normalizeFields(data.data.fields));
                    this.showSqlTableModal = false;
                    _toast('success', data.message || '欄位已匯入');
                } else { _toast('error', data.error || '匯入失敗'); }
            } catch (e) { _toast('error', '匯入失敗: ' + e.message); }
            this.sqlLoading = false;
        },

        async applyToSqlTable() {
            if (!this.specVersion) { _toast('error', '請先儲存規格'); return; }
            this.sqlLoading = true;
            this.sqlApplyPreview = null;
            try {
                var res = await fetch(this.apiBase + '/apply-to-sql-table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: false }),
                });
                var data = await res.json();
                if (data.success) {
                    this.sqlApplyPreview = data.data;
                    this.showSqlApplyModal = true;
                } else { _toast('error', data.error || '預覽失敗'); }
            } catch (e) { _toast('error', '預覽失敗: ' + e.message); }
            this.sqlLoading = false;
        },

        async confirmApplyToSql() {
            this.sqlLoading = true;
            try {
                var res = await fetch(this.apiBase + '/apply-to-sql-table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showSqlApplyModal = false;
                    var action = data.data.action;
                    if (action === 'create') _toast('success', '已建立 SQL Table: ' + data.data.table_name);
                    else if (action === 'alter') _toast('success', '已更新 SQL Table: ' + data.data.table_name);
                    else _toast('info', '表結構無需變更');
                } else { _toast('error', data.error || '執行失敗'); }
            } catch (e) { _toast('error', '執行失敗: ' + e.message); }
            this.sqlLoading = false;
        },

        // ===== 匯出 =====

        async exportFile(format) {
            if (!this.specVersion && !this.isStandalone) {
                _toast('error', '請先儲存規格');
                return;
            }
            var id = this.exportIdentifier;
            if (!id) { _toast('error', '無法識別規格'); return; }

            try {
                var res = await fetch('/api/spec-formulate/export/' + id + '/' + format, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}',
                });
                if (!res.ok) {
                    var err = await res.json();
                    _toast('error', err.error || '匯出失敗');
                    return;
                }
                var blob = await res.blob();
                var disposition = res.headers.get('Content-Disposition') || '';
                var filename = 'spec.' + format;
                var match = disposition.match(/filename[^;=\n]*=(['\"]?)([^'\";\n]*)\1/);
                if (match && match[2]) filename = decodeURIComponent(match[2]);

                var a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
            } catch (e) { _toast('error', '匯出失敗: ' + e.message); }
        },

        // ===== 進階設定 Modal =====

        openDetail(idx) {
            if (!this.gridTable) return;
            var rows = this.gridTable.getData();
            if (idx < 0 || idx >= rows.length) return;
            this.detailIndex = idx;
            var f = JSON.parse(JSON.stringify(rows[idx]));
            if (!f.constraints || typeof f.constraints !== 'object') f.constraints = {};
            var dc = f.constraints;
            if (dc.required === undefined) dc.required = !!f.required;
            if (dc.maxLength === undefined) dc.maxLength = null;
            if (dc.minLength === undefined) dc.minLength = null;
            if (dc.min === undefined) dc.min = null;
            if (dc.max === undefined) dc.max = null;
            if (dc.pattern === undefined) dc.pattern = null;
            if (dc.customValidation === undefined) dc.customValidation = null;
            if (f.lookup_category_code === undefined) f.lookup_category_code = null;
            this.detailForm = f;
            this.detailOptionRows = (f.options || []).map(function(o) { return { label: o.label || '', value: o.value || '' }; });
            this.detailGridChildRows = (f.grid_children || []).map(function(c) { return JSON.parse(JSON.stringify(c)); });
            this.lookupPreviewItems = [];
            if (f.lookup_category_code) { this.loadLookupPreview(f.lookup_category_code); }
            this.showDetailModal = true;
        },

        saveDetail() {
            var f = this.detailForm;
            var filteredOptions = this.detailOptionRows.filter(function(o) { return o.value || o.label; });
            f.options = filteredOptions.length > 0 ? filteredOptions : null;
            f.grid_children = this.detailGridChildRows.length > 0 ? this.detailGridChildRows : null;
            if (f.lookup_category_code) { f.options = null; }

            // 更新 Tabulator row
            if (this.gridTable) {
                var rows = this.gridTable.getRows();
                if (this.detailIndex >= 0 && this.detailIndex < rows.length) {
                    rows[this.detailIndex].update({
                        constraints: JSON.parse(JSON.stringify(f.constraints)),
                        required: !!f.constraints.required,
                        default_value: f.default_value,
                        options: f.options ? JSON.parse(JSON.stringify(f.options)) : null,
                        grid_children: f.grid_children ? JSON.parse(JSON.stringify(f.grid_children)) : null,
                        lookup_category_code: f.lookup_category_code || null,
                    });
                }
            }
            this.showDetailModal = false;
            _toast('success', '進階設定已更新');
        },

        closeDetail() { this.showDetailModal = false; },

        addDetailOption() { this.detailOptionRows.push({ label: '', value: '' }); },
        removeDetailOption(idx) { this.detailOptionRows.splice(idx, 1); },
        addDetailGridChild() {
            this.detailGridChildRows.push({
                field_key: '', label: '', formio_type: 'textfield',
            });
        },
        removeDetailGridChild(idx) { this.detailGridChildRows.splice(idx, 1); },

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
    };
}

// ===== 全域工具函數 =====

var _uidCounter = 0;

function _normalizeFields(fields) {
    return (fields || []).map(function(f, i) {
        f._uid = f._uid || '__uid_' + (++_uidCounter) + '_' + Date.now();
        f.constraints = Object.assign({
            required: false, maxLength: null, minLength: null,
            min: null, max: null, pattern: null, customValidation: null,
        }, f.constraints || {});
        return f;
    });
}

function _emptyFields(count) {
    var arr = [];
    for (var i = 0; i < count; i++) {
        arr.push({
            _uid: '__uid_' + (++_uidCounter) + '_' + Date.now(),
            field_key: '', label: '', formio_type: 'textfield',
            pg_type: 'VARCHAR(500)',
            constraints: { required: false, maxLength: null, minLength: null, min: null, max: null, pattern: null, customValidation: null },
            is_pii: false, description: '', default_value: null,
            options: null, grid_children: null, lookup_category_code: null,
            sort_order: i,
        });
    }
    return arr;
}

function _toast(type, msg) {
    var el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;padding:10px 18px;border-radius:4px;font-size:13px;max-width:400px;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    if (type === 'success') {
        el.style.background = '#d1fae5'; el.style.color = '#065f46'; el.style.border = '1px solid #6ee7b7';
    } else if (type === 'error') {
        el.style.background = '#fee2e2'; el.style.color = '#991b1b'; el.style.border = '1px solid #fca5a5';
    } else {
        el.style.background = '#e0e7ff'; el.style.color = '#3730a3'; el.style.border = '1px solid #a5b4fc';
    }
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function() { el.remove(); }, 3500);
}
