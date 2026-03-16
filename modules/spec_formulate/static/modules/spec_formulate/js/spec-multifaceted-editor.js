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
        specDescription: '',
        specVersion: 0,
        activeFacets: [],
        fields: [],

        // data_class 清單
        dataClasses: [],
        _dcValues: {},

        // Tabulator
        gridTable: null,

        // 投影面板
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
            this.$nextTick(function() { self.initGrid(); });
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
                    this.specDescription = s.description || '';
                    this.specVersion = s.version || 0;
                    this.activeFacets = s.active_facets || [];
                    this.fields = s.fields || [];
                    if (this.activeFacets.length > 0) {
                        this.activeFacetTab = this.activeFacets[0];
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
                        minWidth: 130,
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
                    },
                    {
                        title: 'PII', field: 'core.is_pii',
                        formatter: 'tickCross', hozAlign: 'center',
                        width: 50, editor: true,
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
                        width: 50, editor: true,
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
        },

        // ── 欄位操作 ──

        addColumn() {
            if (!this.gridTable) return;
            this.gridTable.addRow({
                field_key: '',
                label: '',
                description: '',
                sort_order: 0,
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
                    facets: r.facets || {},
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
