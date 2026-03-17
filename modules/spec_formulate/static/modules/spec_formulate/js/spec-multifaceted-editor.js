/**
 * spec-multifaceted-editor.js -- 多面向規格編輯器
 * Alpine.js + Tabulator 6.x 整合
 *
 * 核心差異（vs field-spec-editor）：
 * - 欄位結構: core + facets 分層
 * - data_class 取代 formio_type 作為主類型
 * - facet 按需填充，未啟用的 facet 不顯示
 * - 格式投影面板顯示各格式的映射結果
 */

function specMultifacetedEditor() {
    return {
        specSc: window.__MF_SPEC_CONFIG.specSc || '',
        loading: true,
        saving: false,

        // Spec 資料
        specName: '',
        specTableName: '',
        specDescription: '',
        specVersion: 0,
        activeFacets: [],
        fields: [],

        // data_class 清單
        dataClasses: [],
        _dcValues: {},
        _dcToPgType: {
            'text': 'VARCHAR(500)', 'text_long': 'TEXT',
            'integer': 'INTEGER', 'decimal': 'NUMERIC',
            'currency': 'NUMERIC(15,2)', 'serial': 'SERIAL',
            'boolean': 'BOOLEAN', 'date': 'DATE', 'datetime': 'TIMESTAMP',
            'email': 'VARCHAR(200)', 'phone': 'VARCHAR(50)',
            'url': 'VARCHAR(1000)', 'enum_single': 'VARCHAR(500)',
            'enum_multi': 'JSONB', 'json': 'JSONB', 'tags': 'JSONB',
            'binary': 'BYTEA', 'signature': 'TEXT',
        },

        // Tabulator
        gridTable: null,

        // 投影面板 -- 使用 reactive 陣列驅動，避免依賴 Tabulator 內部狀態
        projectionFields: [],
        activeFacetTab: '',

        // 歷史
        showHistory: false,
        histories: [],
        historyLoading: false,

        // 進階編輯 modal
        showDetailModal: false,
        detailIndex: -1,
        detailForm: {
            field_key: '',
            label: '',
            description: '',
            core: { data_class: 'text', required: false, is_pii: false, default_value: null },
            facets: {},
        },

        // 表單關聯
        linkedFormTemplateSc: '',
        linkedFormTemplateName: '',

        // 關聯表單 modal
        showLinkFormModal: false,
        linkTemplates: [],
        linkTemplatesLoading: false,
        linkSelectedSc: '',
        linkSubmitting: false,

        // 建立表單 modal
        showCreateFormModal: false,
        createFormName: '',
        createFormCode: '',
        createFormSubmitting: false,

        // PostgreSQL 資料表
        linkedSqlTable: '',
        showReadTableModal: false,
        pgTables: [],
        pgTablesLoading: false,
        pgSelectedTable: '',
        pgCompareResult: null,
        pgApplying: false,

        // CSRF
        csrfToken: '',

        async init() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            this.csrfToken = meta ? meta.getAttribute('content') : '';

            await this.loadDataClasses();
            if (this.specSc) {
                await this.loadSpec();
            }
            this.loading = false;
            var self = this;
            // 等 Alpine 完成 x-show 切換後，再用 requestAnimationFrame
            // 確保瀏覽器已完成 layout，Tabulator 才能正確計算欄寬
            this.$nextTick(function() {
                requestAnimationFrame(function() {
                    self.initGrid();
                });
            });
        },

        async loadDataClasses() {
            try {
                var resp = await fetch('/api/spec-formulate/multifaceted/data-classes');
                var data = await resp.json();
                if (data.success) {
                    this.dataClasses = data.data || [];
                    var dcv = {};
                    this.dataClasses.forEach(function(dc) {
                        dcv[dc.value] = dc.label;
                    });
                    this._dcValues = dcv;
                }
            } catch (e) {
                console.error('載入 data classes 失敗:', e);
            }
        },

        async loadSpec() {
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc
                );
                var data = await resp.json();
                if (data.success) {
                    var s = data.data;
                    this.specName = s.name || '';
                    this.specTableName = s.table_name || '';
                    this.specDescription = s.description || '';
                    this.specVersion = s.version || 0;
                    this.activeFacets = s.active_facets || [];
                    // 將 facets.postgresql.pg_type 提取到 _pg_type 虛擬欄位
                    var fields = s.fields || [];
                    var dcPg = this._dcToPgType;
                    fields.forEach(function(f) {
                        var pgFacet = (f.facets || {}).postgresql || {};
                        if (pgFacet.pg_type) {
                            f._pg_type = pgFacet.pg_type;
                        } else {
                            // 從 data_class 推導預設值
                            var dc = (f.core || {}).data_class || 'text';
                            f._pg_type = dcPg[dc] || 'TEXT';
                        }
                    });
                    this.fields = fields;
                    this.linkedFormTemplateSc = s.linked_form_template_sc || '';
                    this.linkedSqlTable = s.linked_sql_table || '';
                    if (this.activeFacets.length > 0 && !this.activeFacetTab) {
                        this.activeFacetTab = this.activeFacets[0];
                    }
                    // 載入關聯表單名稱
                    if (this.linkedFormTemplateSc) {
                        this._loadLinkedTemplateName();
                    }
                }
            } catch (e) {
                console.error('載入規格失敗:', e);
            }
        },

        initGrid() {
            var self = this;
            var el = document.getElementById('mf-field-grid');
            if (!el) return;

            this.gridTable = new Tabulator(el, {
                data: this.fields,
                layout: 'fitColumns',
                movableRows: true,
                selectable: true,
                placeholder: '尚未定義欄位，點擊「+ 欄位」新增',
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
                        cellEdited: function(cell) {
                            var row = cell.getRow();
                            var existingKey = row.getData().field_key;
                            // 只在 field_key 為空時自動翻譯
                            if (!existingKey || !existingKey.trim()) {
                                var label = cell.getValue();
                                if (label && label.trim()) {
                                    self._translateFieldKey(label, row);
                                }
                            }
                        },
                    },
                    {
                        title: 'Field Key', field: 'field_key', editor: 'input',
                        minWidth: 120, cssClass: 'mono-cell',
                        validator: function(cell, value) {
                            if (!value) return true;
                            return /^[a-zA-Z][a-zA-Z0-9_]*$/.test(value);
                        },
                    },
                    {
                        title: 'Data Class', field: 'core.data_class',
                        width: 80,
                        editor: 'list',
                        editorParams: {
                            values: self._dcValues,
                            listOnEmpty: true,
                            autocomplete: true,
                        },
                        formatter: function(cell) {
                            var val = cell.getValue();
                            return self._dcValues[val] || val || '';
                        },
                        accessorDownload: function(value) {
                            return self._dcValues[value] || value;
                        },
                        cellEdited: function(cell) {
                            // Data Class 變更時自動更新 PG Type
                            var dc = cell.getValue();
                            var row = cell.getRow();
                            var currentPg = row.getData()._pg_type || '';
                            // 只在 PG Type 為空或等於舊的預設值時自動更新
                            var newPg = self._dcToPgType[dc] || 'TEXT';
                            if (!currentPg || self._pgTypeIsDefault(currentPg)) {
                                row.update({ _pg_type: newPg });
                            }
                        },
                    },
                    {
                        title: 'PG Type', field: '_pg_type',
                        width: 120, cssClass: 'mono-cell',
                        editor: 'input',
                    },
                    {
                        title: '加密', field: 'core.is_pii',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 100, editor: true,
                        cellEdited: function(cell) {
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
                        title: '必填', field: 'core.required',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 100, editor: true,
                    },
                    {
                        title: '說明', field: 'description', editor: 'input',
                        minWidth: 150,
                    },
                    {
                        title: '操作', width: 70, hozAlign: 'center',
                        resizable: false,
                        formatter: function(cell) {
                            var btn = document.createElement('button');
                            btn.textContent = '詳細';
                            btn.style.cssText = 'padding:2px 8px;font-size:11px;border:1px solid #d1d5db;background:#fff;cursor:pointer;border-radius:2px;';
                            var thisRow = cell.getRow();
                            btn.addEventListener('click', function(e) {
                                e.stopPropagation();
                                var allRows = self.gridTable.getRows();
                                for (var ri = 0; ri < allRows.length; ri++) {
                                    if (allRows[ri] === thisRow) {
                                        self.openDetail(ri);
                                        break;
                                    }
                                }
                            });
                            return btn;
                        },
                    },
                ],
                rowFormatter: function(row) {
                    var data = row.getData();
                    var isPii = data.core && data.core.is_pii;
                    if (isPii) {
                        row.getElement().classList.add('pii-row');
                    }
                },
            });

            // Tabulator 建表完成後，同步 reactive 投影資料
            this.gridTable.on('tableBuilt', function() {
                self._syncProjectionFields();
            });
            // 行異動時同步（新增、刪除、編輯、排序）
            this.gridTable.on('dataChanged', function() {
                self._syncProjectionFields();
            });
            this.gridTable.on('rowMoved', function() {
                self._syncProjectionFields();
            });
        },

        /** 將 Tabulator 資料同步到 Alpine reactive projectionFields */
        _syncProjectionFields() {
            if (!this.gridTable) {
                this.projectionFields = [];
                return;
            }
            this.projectionFields = this.gridTable.getData().filter(function(f) {
                return f.field_key && f.field_key.trim();
            });
        },

        /** 檢查 pg_type 是否為某個 data_class 的預設值 */
        _pgTypeIsDefault(pgType) {
            var vals = Object.values(this._dcToPgType);
            return vals.indexOf(pgType) >= 0;
        },

        // ── 欄位操作 ──

        addColumn() {
            if (!this.gridTable) return;
            this.gridTable.addRow({
                field_key: '',
                label: '',
                description: '',
                sort_order: 0,
                _pg_type: 'VARCHAR(500)',
                core: {
                    data_class: 'text',
                    required: false,
                    is_pii: false,
                    default_value: null,
                },
                facets: {},
            });
        },

        addEmptyRows(count) {
            if (!this.gridTable) return;
            for (var i = 0; i < count; i++) {
                this.gridTable.addRow({
                    field_key: '',
                    label: '',
                    description: '',
                    sort_order: 0,
                    _pg_type: 'VARCHAR(500)',
                    core: {
                        data_class: 'text',
                        required: false,
                        is_pii: false,
                        default_value: null,
                    },
                    facets: {},
                });
            }
        },

        deleteSelectedRows() {
            if (!this.gridTable) return;
            var selected = this.gridTable.getSelectedRows();
            if (selected.length === 0) {
                alert('請先勾選要刪除的欄位');
                return;
            }
            selected.forEach(function(row) { row.delete(); });
        },

        // ── 儲存 ──

        _collectFields() {
            if (!this.gridTable) return [];
            var rows = this.gridTable.getData();
            var fields = [];
            for (var i = 0; i < rows.length; i++) {
                var r = rows[i];
                if (!r.field_key || !(r.field_key || '').trim()) continue;

                var facets = r.facets || {};
                // 將 _pg_type 虛擬欄位寫回 facets.postgresql.pg_type
                var pgType = (r._pg_type || '').trim();
                if (pgType) {
                    if (!facets.postgresql) facets.postgresql = {};
                    facets.postgresql.pg_type = pgType;
                }

                fields.push({
                    field_key: (r.field_key || '').trim(),
                    label: (r.label || '').trim(),
                    sort_order: i,
                    description: (r.description || '').trim(),
                    core: r.core || {
                        data_class: 'text',
                        required: false,
                        is_pii: false,
                        default_value: null,
                    },
                    facets: facets,
                });
            }
            return fields;
        },

        async saveSpec() {
            var fields = this._collectFields();
            this.saving = true;

            try {
                var url, method;
                if (this.specSc) {
                    url = '/api/spec-formulate/multifaceted/specs/' + this.specSc;
                    method = 'POST';
                } else {
                    url = '/api/spec-formulate/multifaceted/specs';
                    method = 'POST';
                }

                var body = {
                    name: this.specName,
                    table_name: this.specTableName,
                    description: this.specDescription,
                    fields: fields,
                };

                var resp = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify(body),
                });

                var data = await resp.json();
                if (data.success) {
                    var s = data.data;
                    this.specVersion = s.version || this.specVersion;
                    this.activeFacets = s.active_facets || this.activeFacets;
                    if (!this.specSc && s.secure_code) {
                        this.specSc = s.secure_code;
                        history.replaceState(null, '',
                            '/spec-formulate/multifaceted/' + s.secure_code + '/edit');
                    }
                    if (s.warnings && s.warnings.length > 0) {
                        alert('已儲存（有警告）:\n' + s.warnings.join('\n'));
                    }
                } else {
                    var msg = data.error || '儲存失敗';
                    if (data.details) {
                        msg += '\n' + data.details.join('\n');
                    }
                    alert(msg);
                }
            } catch (e) {
                alert('儲存失敗: ' + e.message);
            }
            this.saving = false;
        },

        // ── Facet 填充 ──

        async populateFacet(facetName) {
            if (!this.specSc) {
                alert('請先儲存規格');
                return;
            }

            // 先儲存當前欄位
            await this.saveSpec();

            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/populate-facet',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({ facet_name: facetName }),
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.activeFacets = data.data.active_facets || [];
                    if (!this.activeFacetTab) {
                        this.activeFacetTab = facetName;
                    }
                    // 重新載入以取得更新後的 fields
                    await this.loadSpec();
                    if (this.gridTable) {
                        this.gridTable.setData(this.fields);
                        this._syncProjectionFields();
                    }
                    var msg = data.message || '完成';
                    if (data.data.skipped_count > 0) {
                        msg += '\n不支援的欄位: ' +
                            data.data.skipped_fields
                                .map(function(s) { return s.field_key + ' (' + s.reason + ')'; })
                                .join(', ');
                    }
                    alert(msg);
                } else {
                    alert(data.error || '填充失敗');
                }
            } catch (e) {
                alert('填充失敗: ' + e.message);
            }
        },

        // ── 投影面板 ──

        getFacetProjection(field, facetName) {
            var facets = field.facets || {};
            return facets[facetName] || null;
        },

        getFacetSupportInfo(dataClass, facetName) {
            for (var i = 0; i < this.dataClasses.length; i++) {
                if (this.dataClasses[i].value === dataClass) {
                    var dc = this.dataClasses[i];
                    var supported = (dc.supported_facets || []).indexOf(facetName) >= 0;
                    return { supported: supported };
                }
            }
            return { supported: false };
        },

        // ── 進階編輯 Modal ──

        openDetail(index) {
            var rows = this.gridTable.getData();
            if (index < 0 || index >= rows.length) return;
            var row = rows[index];
            this.detailIndex = index;
            this.detailForm = JSON.parse(JSON.stringify(row));
            if (!this.detailForm.core) {
                this.detailForm.core = {
                    data_class: 'text',
                    required: false,
                    is_pii: false,
                    default_value: null,
                };
            }
            if (!this.detailForm.facets) {
                this.detailForm.facets = {};
            }
            this.showDetailModal = true;
        },

        saveDetail() {
            if (this.detailIndex < 0 || !this.gridTable) return;
            var allRows = this.gridTable.getRows();
            if (this.detailIndex < allRows.length) {
                allRows[this.detailIndex].update(this.detailForm);
                this._syncProjectionFields();
            }
            this.showDetailModal = false;
        },

        closeDetail() {
            this.showDetailModal = false;
            this.detailIndex = -1;
        },

        // ── 版本歷史 ──

        async loadHistory() {
            if (!this.specSc) return;
            this.historyLoading = true;
            this.showHistory = true;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' +
                    this.specSc + '/history'
                );
                var data = await resp.json();
                if (data.success) {
                    this.histories = data.data || [];
                }
            } catch (e) {
                console.error('載入歷史失敗:', e);
            }
            this.historyLoading = false;
        },

        // ── 資料表名稱翻譯 ──

        async autoTranslateTableName() {
            // 只在 table_name 為空時自動翻譯
            if (this.specTableName) return;
            if (!this.specName || !this.specName.trim()) return;
            try {
                var resp = await fetch('/api/spec-formulate/multifaceted/translate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({ name: this.specName, prefix: 'spec_' }),
                });
                var data = await resp.json();
                if (data.success && !this.specTableName) {
                    this.specTableName = data.code;
                }
            } catch (e) {
                // 靜默
            }
        },

        async _translateFieldKey(label, row) {
            try {
                var resp = await fetch('/api/spec-formulate/multifaceted/translate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({ name: label, prefix: '' }),
                });
                var data = await resp.json();
                if (data.success && data.code) {
                    // 再次確認 field_key 仍為空（避免競爭）
                    var current = row.getData().field_key;
                    if (!current || !current.trim()) {
                        row.update({ field_key: data.code });
                        this._syncProjectionFields();
                    }
                }
            } catch (e) {
                // 靜默
            }
        },

        // ── 表單關聯 ──

        async _loadLinkedTemplateName() {
            // 透過 available-templates 無法取到已佔用的，直接顯示 sc 即可
            // 但可用 link-form 回傳的 name。先從已有資訊取
            // 若 loadSpec 回傳沒帶 name，就保留 sc
            this.linkedFormTemplateName = '';
        },

        async openLinkFormModal() {
            this.showLinkFormModal = true;
            this.linkSelectedSc = '';
            this.linkTemplates = [];
            this.linkTemplatesLoading = true;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/available-templates'
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkTemplates = data.data || [];
                }
            } catch (e) {
                console.error('載入可用表單失敗:', e);
            }
            this.linkTemplatesLoading = false;
        },

        async confirmLinkForm() {
            if (!this.linkSelectedSc) return;
            this.linkSubmitting = true;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc + '/link-form',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({
                            form_template_secure_code: this.linkSelectedSc,
                        }),
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedFormTemplateSc = data.data.linked_form_template_sc;
                    this.linkedFormTemplateName = data.data.template_name || '';
                    this.showLinkFormModal = false;
                    alert(data.message);
                } else {
                    alert(data.error || '關聯失敗');
                }
            } catch (e) {
                alert('關聯失敗: ' + e.message);
            }
            this.linkSubmitting = false;
        },

        async unlinkForm() {
            if (!confirm('確定要解除表單關聯？')) return;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc + '/unlink-form',
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedFormTemplateSc = '';
                    this.linkedFormTemplateName = '';
                } else {
                    alert(data.error || '解除失敗');
                }
            } catch (e) {
                alert('解除失敗: ' + e.message);
            }
        },

        openCreateFormModal() {
            this.createFormName = this.specName;
            this.createFormCode = '';
            this.showCreateFormModal = true;
        },

        async confirmCreateForm() {
            this.createFormSubmitting = true;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc + '/create-form',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({
                            name: this.createFormName || this.specName,
                            code: this.createFormCode,
                        }),
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedFormTemplateSc = data.data.form_template.secure_code;
                    this.linkedFormTemplateName = data.data.form_template.name;
                    this.showCreateFormModal = false;
                    alert(data.message);
                } else {
                    alert(data.error || '建立失敗');
                }
            } catch (e) {
                alert('建立失敗: ' + e.message);
            }
            this.createFormSubmitting = false;
        },

        // ── PostgreSQL 資料表 ──

        async openReadTableModal() {
            this.showReadTableModal = true;
            this.pgSelectedTable = '';
            this.pgCompareResult = null;
            this.pgTables = [];
            this.pgTablesLoading = true;
            try {
                // 確保企業 DB 存在
                await fetch('/api/spec-formulate/multifaceted/pg/ensure-db', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': this.csrfToken },
                });
                var resp = await fetch('/api/spec-formulate/multifaceted/pg/tables');
                var data = await resp.json();
                if (data.success) {
                    this.pgTables = data.data || [];
                } else {
                    alert(data.error || '載入資料表失敗');
                }
            } catch (e) {
                alert('載入失敗: ' + e.message);
            }
            this.pgTablesLoading = false;
        },

        async pgCompareTable() {
            if (!this.pgSelectedTable) {
                this.pgCompareResult = null;
                return;
            }
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/pg/compare/' + encodeURIComponent(this.pgSelectedTable)
                );
                var data = await resp.json();
                if (data.success) {
                    this.pgCompareResult = data.data;
                } else {
                    alert(data.error || '比對失敗');
                }
            } catch (e) {
                alert('比對失敗: ' + e.message);
            }
        },

        async pgLinkTable(tableName) {
            // 僅關聯，不修改資料表
            try {
                // 用 saveSpec 儲存 linked_sql_table（透過後端更新）
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/pg/apply-to-table',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({ table_name: tableName }),
                    }
                );
                var data = await resp.json();
                this.linkedSqlTable = tableName;
                this.showReadTableModal = false;
            } catch (e) {
                alert('關聯失敗: ' + e.message);
            }
        },

        async pgApplySpecToTable() {
            if (!this.pgSelectedTable) return;
            if (!confirm('確定要將 SPEC 的欄位定義覆蓋到資料表？\\n這可能導致資料庫錯誤（如型別不相容）。')) return;

            this.pgApplying = true;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/pg/apply-to-table',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({ table_name: this.pgSelectedTable }),
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedSqlTable = this.pgSelectedTable;
                    var msg = data.message;
                    if (data.data && data.data.errors && data.data.errors.length > 0) {
                        msg += '\n\n失敗項目:\n' + data.data.errors.join('\n');
                    }
                    if (data.data && data.data.executed_sql && data.data.executed_sql.length > 0) {
                        msg += '\n\n已執行:\n' + data.data.executed_sql.join('\n');
                    }
                    alert(msg);
                    this.showReadTableModal = false;
                } else {
                    alert(data.error || '覆蓋失敗');
                }
            } catch (e) {
                alert('操作失敗: ' + e.message);
            }
            this.pgApplying = false;
        },

        async pgCreateTable() {
            if (!this.specTableName) {
                alert('請先設定資料表名稱');
                return;
            }

            // 檢查 PG Type 缺漏
            if (this.gridTable) {
                var rows = this.gridTable.getData();
                var missing = [];
                for (var i = 0; i < rows.length; i++) {
                    var r = rows[i];
                    if (!r.field_key || !r.field_key.trim()) continue;
                    if (!r._pg_type || !r._pg_type.trim()) {
                        missing.push(r.field_key);
                    }
                }
                if (missing.length > 0) {
                    alert('以下欄位缺少 PG Type:\n' + missing.join(', ') + '\n\n請填寫後再試。');
                    return;
                }
            }

            if (!confirm('將在企業資料庫建立資料表: ' + this.specTableName + '\n確定繼續？')) return;

            try {
                // 先儲存最新欄位（含 PG Type）
                await this.saveSpec();

                // 確保企業 DB 存在
                await fetch('/api/spec-formulate/multifaceted/pg/ensure-db', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': this.csrfToken },
                });

                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/pg/create-table',
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.csrfToken,
                        },
                        body: JSON.stringify({ table_name: this.specTableName }),
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedSqlTable = this.specTableName;
                    var msg = data.message;
                    if (data.data && data.data.warnings && data.data.warnings.length > 0) {
                        msg += '\n\n警告:\n' + data.data.warnings.join('\n');
                    }
                    if (data.data && data.data.ddl) {
                        msg += '\n\nDDL:\n' + data.data.ddl;
                    }
                    alert(msg);
                } else {
                    var errMsg = data.error || data.message || '建立失敗';
                    if (data.data && data.data.ddl) {
                        errMsg += '\n\nDDL:\n' + data.data.ddl;
                    }
                    alert(errMsg);
                }
            } catch (e) {
                alert('建立失敗: ' + e.message);
            }
        },

        async pgUnlinkTable() {
            if (!confirm('確定要解除資料表關聯？（不會刪除實際資料表）')) return;
            try {
                var resp = await fetch(
                    '/api/spec-formulate/multifaceted/specs/' + this.specSc +
                    '/pg/unlink-table',
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedSqlTable = '';
                } else {
                    alert(data.error || '解除失敗');
                }
            } catch (e) {
                alert('解除失敗: ' + e.message);
            }
        },

        formatDate(ts) {
            if (!ts) return '-';
            var d = new Date(ts);
            var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
            return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' +
                pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' +
                pad(d.getMinutes());
        },
    };
}
