/**
 * spec-schema-editor.js -- 資料結構規格編輯器
 * Alpine.js + Tabulator 6.x 整合
 *
 * 核心差異（vs field-spec-editor）：
 * - 欄位結構: core + facets 分層
 * - data_class 取代 formio_type 作為主類型
 * - facet 按需填充，未啟用的 facet 不顯示
 * - 格式投影面板顯示各格式的映射結果
 */

function specSchemaEditor() {
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
        histories: [],

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
        linkedSqlTarget: '',
        pgTarget: 'org',          // 'org' or 'conglomerate'
        cgDbAvailable: false,     // 企業是否屬於有共享 DB 的集團
        cgDbName: '',             // 集團名稱（顯示用）
        showReadTableModal: false,
        pgTables: [],
        pgTablesLoading: false,
        pgSelectedTable: '',
        pgCompareResult: null,
        pgApplying: false,

        // SPEC 清單側邊欄
        specList: [],
        specListLoading: false,

        // 新增規格 modal
        showNewSpecModal: false,
        newSpecForm: { name: '', table_name: '', description: '' },
        newSpecTableSuggestion: '',
        newSpecCreating: false,

        // 製作規格書 modal
        showDocxModal: false,
        docxExporting: false,
        pdfExporting: false,
        docxTitle: '',
        docxItems: [],

        // CSRF
        csrfToken: '',

        async init() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            this.csrfToken = meta ? meta.getAttribute('content') : '';

            await this.loadDataClasses();
            this.loadCgInfo();
            this.loadSpecList();
            if (this.specSc) {
                await this.loadSpec();
                this.loadHistory();
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
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/data-classes');
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

        async loadSpecList() {
            this.specListLoading = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/specs');
                var data = await resp.json();
                if (data.success) {
                    this.specList = data.data || [];
                }
            } catch (e) {
                console.error('載入 SPEC 清單失敗:', e);
            }
            this.specListLoading = false;
        },

        switchSpec(sc) {
            if (sc === this.specSc) return;
            window.location.href = window.__BP + '/spec-formulate/' + sc + '/edit';
        },

        async loadSpec() {
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc
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
                    this.linkedFormTemplateName = s.linked_form_template_name || '';
                    this.linkedSqlTable = s.linked_sql_table || '';
                    this.linkedSqlTarget = s.linked_sql_target || '';
                    if (this.linkedSqlTarget === 'conglomerate') {
                        this.pgTarget = 'conglomerate';
                    }
                    if (this.activeFacets.length > 0 && !this.activeFacetTab) {
                        this.activeFacetTab = this.activeFacets[0];
                    }
                }
            } catch (e) {
                console.error('載入規格失敗:', e);
            }
        },

        /** 將 Alpine proxy 轉為純 JS 物件，供 Tabulator 使用 */
        _plainFields() {
            return JSON.parse(JSON.stringify(this.fields));
        },

        initGrid() {
            var self = this;
            var el = document.getElementById('mf-field-grid');
            if (!el) return;

            this.gridTable = new Tabulator(el, {
                data: this._plainFields(),
                layout: 'fitColumns',
                movableRows: true,
                selectable: true,
                placeholder: '尚未定義欄位，點擊「+ 欄位」新增',
                rowHeight: 24,
                columnDefaults: { headerSort: false },
                columns: [
                    {
                        title: '#', width: 50,
                        hozAlign: 'center', resizable: false,
                        rowHandle: true,
                        formatter: function(cell) {
                            var pos = cell.getRow().getPosition(true);
                            return '<span class="drag-handle">&#x2630;</span>' + pos;
                        },
                    },
                    {
                        title: 'Label', field: 'label', editor: 'input',
                        width: 160,
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
                        width: 160, cssClass: 'mono-cell',
                        validator: function(cell, value) {
                            if (!value) return true;
                            return /^[a-zA-Z][a-zA-Z0-9_]*$/.test(value);
                        },
                    },
                    {
                        title: 'Data Class', field: 'core.data_class',
                        width: 100,
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
                        width: 100, cssClass: 'mono-cell',
                        editor: 'input',
                    },
                    {
                        title: '加密', field: 'core.is_pii',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 70, editor: true,
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
                        width: 70, editor: true,
                    },
                    {
                        title: '說明', field: 'description', editor: 'input',
                        minWidth: 200,
                    },
                    {
                        title: '操作', width: 100, hozAlign: 'center',
                        resizable: false,
                        formatter: function(cell) {
                            var btn = document.createElement('button');
                            btn.textContent = '詳細';
                            btn.style.cssText = 'padding:2px 8px;font-size:11px;border:1px solid #d1d5db;background:#fff;cursor:pointer;border-radius:2px;';
                            btn.addEventListener('click', function(e) {
                                e.stopPropagation();
                                var row = cell.getRow();
                                var pos = row.getPosition(true);
                                self.openDetail(pos - 1);
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
                this.showToast('請先勾選要刪除的欄位', 'warning');
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
                    url = window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc;
                    method = 'POST';
                } else {
                    url = window.__BP + '/api/spec-formulate/schema/specs';
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
                            window.__BP + '/spec-formulate/' + s.secure_code + '/edit');
                    }
                    if (s.warnings && s.warnings.length > 0) {
                        this.showToast('已儲存（有 ' + s.warnings.length + ' 個警告）', 'warning');
                    }
                    // 刷新側邊欄與歷史
                    this.loadSpecList();
                    this.loadHistory();
                } else {
                    var msg = data.error || '儲存失敗';
                    if (data.details) {
                        msg += ' (' + data.details.length + ' 個問題)';
                    }
                    this.showToast(msg, 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
            this.saving = false;
        },

        // ── Facet 填充 ──

        async populateFacet(facetName) {
            if (!this.specSc) {
                this.showToast('請先儲存規格', 'warning');
                return;
            }

            // 先儲存當前欄位
            await this.saveSpec();

            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
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
                        this.gridTable.setData(this._plainFields());
                        this._syncProjectionFields();
                    }
                    var msg = data.message || '完成';
                    if (data.data.skipped_count > 0) {
                        msg += ' (跳過 ' + data.data.skipped_count + ' 個不支援欄位)';
                    }
                    this.showToast(msg, 'success');
                } else {
                    this.showToast(data.error || '填充失敗', 'error');
                }
            } catch (e) {
                this.showToast('填充失敗: ' + e.message, 'error');
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
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' +
                    this.specSc + '/history'
                );
                var data = await resp.json();
                if (data.success) {
                    this.histories = data.data || [];
                }
            } catch (e) {
                console.error('載入歷史失敗:', e);
            }
        },

        restoreVersion(h) {
            var snapshot = h.fields_snapshot || [];
            var dcPg = this._dcToPgType;
            // 補上 _pg_type 虛擬欄位
            snapshot.forEach(function(f) {
                var pgFacet = (f.facets || {}).postgresql || {};
                if (pgFacet.pg_type) {
                    f._pg_type = pgFacet.pg_type;
                } else {
                    var dc = (f.core || {}).data_class || 'text';
                    f._pg_type = dcPg[dc] || 'TEXT';
                }
            });
            this.fields = snapshot;
            this.activeFacets = h.active_facets_snapshot || [];
            if (this.activeFacets.length > 0 && !this.activeFacetTab) {
                this.activeFacetTab = this.activeFacets[0];
            }
            if (this.gridTable) {
                this.gridTable.setData(this._plainFields());
                this._syncProjectionFields();
            }
        },

        // ── 資料表名稱翻譯 ──

        async autoTranslateTableName() {
            // 只在 table_name 為空時自動翻譯
            if (this.specTableName) return;
            if (!this.specName || !this.specName.trim()) return;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/translate', {
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
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/translate', {
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

        // _loadLinkedTemplateName 已由 get_spec API 回傳，不再需要

        async openLinkFormModal() {
            this.showLinkFormModal = true;
            this.linkSelectedSc = '';
            this.linkTemplates = [];
            this.linkTemplatesLoading = true;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/available-templates'
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
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc + '/link-form',
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
                    this.showToast(data.message, 'success');
                } else {
                    this.showToast(data.error || '關聯失敗', 'error');
                }
            } catch (e) {
                this.showToast('關聯失敗: ' + e.message, 'error');
            }
            this.linkSubmitting = false;
        },

        async unlinkForm() {
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc + '/unlink-form',
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedFormTemplateSc = '';
                    this.linkedFormTemplateName = '';
                    this.showToast('已解除表單關聯', 'success');
                } else {
                    this.showToast(data.error || '解除失敗', 'error');
                }
            } catch (e) {
                this.showToast('解除失敗: ' + e.message, 'error');
            }
        },

        async syncToForm() {
            if (!this.linkedFormTemplateSc) {
                this.showToast('尚未關聯表單', 'warning');
                return;
            }
            if (!confirm('確定要將目前的欄位同步回關聯的表單嗎？\n這會覆蓋表單現有的欄位結構。')) {
                return;
            }
            // 先儲存最新欄位
            await this.saveSpec();
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc + '/sync-to-form',
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.showToast(data.message, 'success');
                } else {
                    this.showToast(data.error || '同步失敗', 'error');
                }
            } catch (e) {
                this.showToast('同步失敗: ' + e.message, 'error');
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
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc + '/create-form',
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
                    this.showToast(data.message, 'success');
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
            this.createFormSubmitting = false;
        },

        // ── PostgreSQL 資料表 ──

        async loadCgInfo() {
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/cg/info');
                var data = await resp.json();
                if (data.success && data.data.has_conglomerate_db) {
                    this.cgDbAvailable = true;
                    this.cgDbName = data.data.conglomerate_name || '';
                }
            } catch (e) {
                // 無集團 DB 不影響正常功能
            }
        },

        onPgTargetChange() {
            // 切換目標時清除已載入的表列表
            this.pgTables = [];
            this.pgSelectedTable = '';
            this.pgCompareResult = null;
        },

        pgTableOptions() {
            // 統一成 {value, label} 格式
            // org: pgTables = ['name1', 'name2']
            // conglomerate: pgTables = [{name, creator_org_name, is_owner}]
            var result = [];
            for (var i = 0; i < this.pgTables.length; i++) {
                var t = this.pgTables[i];
                if (typeof t === 'string') {
                    result.push({ value: t, label: t });
                } else {
                    var label = t.name;
                    if (t.creator_org_name) {
                        label += ' (' + t.creator_org_name;
                        if (t.is_owner) label += ', 自己建立';
                        label += ')';
                    }
                    result.push({ value: t.name, label: label });
                }
            }
            return result;
        },

        // 根據 pgTarget 回傳 API 路徑前綴
        _pgApiPrefix() {
            return this.pgTarget === 'conglomerate' ? '/cg/' : '/pg/';
        },

        async openReadTableModal() {
            this.showReadTableModal = true;
            this.pgSelectedTable = '';
            this.pgCompareResult = null;
            this.pgTables = [];
            this.pgTablesLoading = true;
            var prefix = this._pgApiPrefix();
            try {
                if (this.pgTarget === 'org') {
                    // 企業 DB: 先確保存在
                    await fetch(window.__BP + '/api/spec-formulate/schema/pg/ensure-db', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    });
                }
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema' + prefix + 'tables');
                var data = await resp.json();
                if (data.success) {
                    this.pgTables = data.data || [];
                } else {
                    this.showToast(data.error || '載入資料表失敗', 'error');
                }
            } catch (e) {
                this.showToast('載入失敗: ' + e.message, 'error');
            }
            this.pgTablesLoading = false;
        },

        async pgCompareTable() {
            if (!this.pgSelectedTable) {
                this.pgCompareResult = null;
                return;
            }
            var prefix = this._pgApiPrefix();
            var tableName = this.pgTarget === 'conglomerate'
                ? (this.pgSelectedTable.name || this.pgSelectedTable)
                : this.pgSelectedTable;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
                    prefix + 'compare/' + encodeURIComponent(tableName)
                );
                var data = await resp.json();
                if (data.success) {
                    this.pgCompareResult = data.data;
                } else {
                    this.showToast(data.error || '比對失敗', 'error');
                }
            } catch (e) {
                this.showToast('比對失敗: ' + e.message, 'error');
            }
        },

        async pgLinkTable(tableName) {
            // 僅關聯，不修改資料表
            var prefix = this._pgApiPrefix();
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
                    prefix + 'apply-to-table',
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
                this.linkedSqlTarget = this.pgTarget;
                this.showReadTableModal = false;
                this.showToast('已關聯資料表: ' + tableName, 'success');
            } catch (e) {
                this.showToast('關聯失敗: ' + e.message, 'error');
            }
        },

        async pgApplySpecToTable() {
            if (!this.pgSelectedTable) return;
            this.pgApplying = true;
            var prefix = this._pgApiPrefix();
            var tableName = this.pgTarget === 'conglomerate'
                ? (this.pgSelectedTable.name || this.pgSelectedTable)
                : this.pgSelectedTable;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
                    prefix + 'apply-to-table',
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
                if (data.success) {
                    this.linkedSqlTable = tableName;
                    this.linkedSqlTarget = this.pgTarget;
                    var toastMsg = data.message;
                    if (data.data && data.data.errors && data.data.errors.length > 0) {
                        toastMsg += ' (' + data.data.errors.length + ' 個失敗)';
                        this.showToast(toastMsg, 'warning');
                    } else {
                        this.showToast(toastMsg, 'success');
                    }
                    this.showReadTableModal = false;
                } else {
                    this.showToast(data.error || '覆蓋失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗: ' + e.message, 'error');
            }
            this.pgApplying = false;
        },

        async pgCreateTable() {
            if (!this.specTableName) {
                this.showToast('請先設定資料表名稱', 'warning');
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
                    this.showToast('有 ' + missing.length + ' 個欄位缺少 PG Type', 'warning');
                    return;
                }
            }

            var prefix = this._pgApiPrefix();
            try {
                // 先儲存最新欄位（含 PG Type）
                await this.saveSpec();

                if (this.pgTarget === 'org') {
                    // 確保企業 DB 存在
                    await fetch(window.__BP + '/api/spec-formulate/schema/pg/ensure-db', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    });
                }

                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
                    prefix + 'create-table',
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
                    this.linkedSqlTarget = this.pgTarget;
                    var msg = data.message;
                    if (data.data && data.data.warnings && data.data.warnings.length > 0) {
                        msg += ' (' + data.data.warnings.length + ' 個警告)';
                        this.showToast(msg, 'warning');
                    } else {
                        this.showToast(msg, 'success');
                    }
                } else {
                    this.showToast(data.error || data.message || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
        },

        async pgUnlinkTable() {
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + this.specSc +
                    '/pg/unlink-table',
                    {
                        method: 'POST',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.linkedSqlTable = '';
                    this.linkedSqlTarget = '';
                    this.showToast('已解除資料表關聯', 'success');
                } else {
                    this.showToast(data.error || '解除失敗', 'error');
                }
            } catch (e) {
                this.showToast('解除失敗: ' + e.message, 'error');
            }
        },

        // ── 新增規格 ──

        openNewSpecModal() {
            this.newSpecForm = { name: '', table_name: '', description: '' };
            this.newSpecTableSuggestion = '';
            this.showNewSpecModal = true;
        },

        async translateNewSpecTableName() {
            var name = (this.newSpecForm.name || '').trim();
            if (!name) { this.newSpecTableSuggestion = ''; return; }
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/translate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({ name: name, prefix: 'spec_' }),
                });
                var data = await resp.json();
                if (data.success) {
                    this.newSpecTableSuggestion = data.code;
                }
            } catch (e) {
                // 靜默
            }
        },

        async confirmNewSpec() {
            var name = (this.newSpecForm.name || '').trim();
            if (!name) { alert('規格名稱必填'); return; }
            this.newSpecCreating = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/specs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({
                        name: name,
                        table_name: (this.newSpecForm.table_name || '').trim() || this.newSpecTableSuggestion || '',
                        description: (this.newSpecForm.description || '').trim(),
                        fields: [],
                    }),
                });
                var data = await resp.json();
                if (data.success) {
                    this.showNewSpecModal = false;
                    window.location.href = window.__BP + '/spec-formulate/' + data.data.secure_code + '/edit';
                } else {
                    alert(data.error || '建立失敗');
                }
            } catch (e) {
                alert('建立失敗: ' + e.message);
            }
            this.newSpecCreating = false;
        },

        // ── 製作規格書 ──

        openDocxModal() {
            var available = this.specList.filter(function(s) {
                return s.active_facets && s.active_facets.length > 0;
            });
            if (available.length === 0) {
                this.showToast('目前沒有任何已啟用格式的規格可匯出', 'warning');
                return;
            }
            this.docxTitle = '';
            this.docxItems = [];
            this.showDocxModal = true;
        },

        docxAddSpec(spec) {
            for (var i = 0; i < this.docxItems.length; i++) {
                if (this.docxItems[i].spec_sc === spec.secure_code) return;
            }
            var facetSelections = {};
            (spec.active_facets || []).forEach(function(f) {
                facetSelections[f] = true;
            });
            var item = {
                spec_sc: spec.secure_code,
                name: spec.name,
                version: spec.version,
                currentVersion: spec.version,
                versions: [],
                loadingVersions: false,
                activeFacets: spec.active_facets || [],
                selectedFacets: facetSelections,
            };
            this.docxItems.push(item);
            var proxyItem = this.docxItems[this.docxItems.length - 1];
            this._loadDocxVersions(proxyItem);
        },

        docxRemoveSpec(index) {
            this.docxItems.splice(index, 1);
        },

        async _loadDocxVersions(item) {
            item.loadingVersions = true;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' + item.spec_sc + '/versions'
                );
                var data = await resp.json();
                if (data.success) {
                    item.versions = data.data || [];
                }
            } catch (e) {
                console.error('載入版本失敗:', e);
            }
            item.loadingVersions = false;
        },

        docxOnVersionChange(item) {
            var ver = parseInt(item.version);
            var found = null;
            for (var i = 0; i < item.versions.length; i++) {
                if (item.versions[i].version === ver) { found = item.versions[i]; break; }
            }
            if (found) {
                item.activeFacets = found.active_facets || [];
                var newSel = {};
                item.activeFacets.forEach(function(f) {
                    newSel[f] = item.selectedFacets[f] !== false;
                });
                item.selectedFacets = newSel;
            }
        },

        docxGetSelectedCount() {
            var count = 0;
            for (var i = 0; i < this.docxItems.length; i++) {
                var item = this.docxItems[i];
                var facets = item.activeFacets || [];
                for (var j = 0; j < facets.length; j++) {
                    if (item.selectedFacets[facets[j]]) count++;
                }
            }
            return count;
        },

        docxAvailableSpecs() {
            var selected = {};
            for (var i = 0; i < this.docxItems.length; i++) {
                selected[this.docxItems[i].spec_sc] = true;
            }
            return this.specList.filter(function(s) {
                return (s.active_facets && s.active_facets.length > 0) && !selected[s.secure_code];
            });
        },

        async doExportDocx() {
            if (this.docxItems.length === 0) {
                alert('請至少加入一個規格');
                return;
            }
            var specs = [];
            for (var i = 0; i < this.docxItems.length; i++) {
                var item = this.docxItems[i];
                var facets = [];
                var af = item.activeFacets || [];
                for (var j = 0; j < af.length; j++) {
                    if (item.selectedFacets[af[j]]) facets.push(af[j]);
                }
                if (facets.length === 0) {
                    alert(item.name + ': 請至少選擇一種格式');
                    return;
                }
                specs.push({
                    spec_sc: item.spec_sc,
                    version: parseInt(item.version),
                    facets: facets,
                });
            }
            this.docxExporting = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/export/docx', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({
                        doc_title: this.docxTitle || '',
                        specs: specs,
                    }),
                });
                if (resp.ok) {
                    var blob = await resp.blob();
                    var cd = resp.headers.get('content-disposition') || '';
                    var filename = '規格書.docx';
                    var starMatch = cd.match(/filename\*=UTF-8''([^;\s]+)/i);
                    if (starMatch) {
                        filename = decodeURIComponent(starMatch[1]);
                    } else {
                        var plainMatch = cd.match(/filename="?([^";]+)"?/i);
                        if (plainMatch) filename = plainMatch[1];
                    }
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    this.showDocxModal = false;
                } else {
                    var errData = await resp.json();
                    alert(errData.error || '匯出失敗');
                }
            } catch (e) {
                alert('匯出失敗: ' + e.message);
            }
            this.docxExporting = false;
        },

        async doExportPdf() {
            if (this.docxItems.length === 0) {
                alert('請至少加入一個規格');
                return;
            }
            var specs = [];
            for (var i = 0; i < this.docxItems.length; i++) {
                var item = this.docxItems[i];
                var facets = [];
                var af = item.activeFacets || [];
                for (var j = 0; j < af.length; j++) {
                    if (item.selectedFacets[af[j]]) facets.push(af[j]);
                }
                if (facets.length === 0) {
                    alert(item.name + ': 請至少選擇一種格式');
                    return;
                }
                specs.push({
                    spec_sc: item.spec_sc,
                    version: parseInt(item.version),
                    facets: facets,
                });
            }
            this.pdfExporting = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/export/pdf', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({
                        doc_title: this.docxTitle || '',
                        specs: specs,
                    }),
                });
                if (resp.ok) {
                    var blob = await resp.blob();
                    var cd = resp.headers.get('content-disposition') || '';
                    var filename = '規格書.pdf';
                    var starMatch = cd.match(/filename\*=UTF-8''([^;\s]+)/i);
                    if (starMatch) {
                        filename = decodeURIComponent(starMatch[1]);
                    } else {
                        var plainMatch = cd.match(/filename="?([^";]+)"?/i);
                        if (plainMatch) filename = plainMatch[1];
                    }
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                    this.showDocxModal = false;
                } else {
                    var errData = await resp.json();
                    alert(errData.error || '匯出失敗');
                }
            } catch (e) {
                alert('匯出失敗: ' + e.message);
            }
            this.pdfExporting = false;
        },

        showToast(message, type) {
            type = type || 'info';
            var container = document.getElementById('mfe-toast-container');
            if (!container) { console.log('[Toast]', type, message); return; }
            var toast = document.createElement('div');
            toast.className = 'mfe-toast ' + type;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(function() {
                toast.classList.add('fade-out');
                setTimeout(function() { toast.remove(); }, 300);
            }, 3000);
        },

        formatDate(ts) {
            return BkTime.format(ts, 'short');
        },
    };
}
