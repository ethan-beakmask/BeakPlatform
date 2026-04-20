/**
 * spec-schema.js -- 資料結構規格管理
 * Alpine.js 驅動的列表頁
 */

function specSchemaManager() {
    return {
        loading: true,
        specs: [],
        dataClasses: [],

        // 新增 modal
        showCreateModal: false,
        createForm: { name: '', table_name: '', description: '' },
        creating: false,
        tableSuggestion: '',

        // 刪除確認
        deleteTarget: null,
        showDeleteModal: false,
        deleting: false,

        // 製作規格書 modal
        showDocxModal: false,
        docxExporting: false,
        docxTitle: '資料結構規格書',
        docxItems: [],
        // docxItems: [{ spec_sc, name, version, versions: [{version, is_current, active_facets}], selectedFacets: {pg: true, ...}, loadingVersions: bool }]

        // CSRF
        csrfToken: '',

        init() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            this.csrfToken = meta ? meta.getAttribute('content') : '';
            this.loadSpecs();
            this.loadDataClasses();
        },

        async loadSpecs() {
            this.loading = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/specs');
                var data = await resp.json();
                if (data.success) {
                    this.specs = data.data || [];
                }
            } catch (e) {
                console.error('載入規格失敗:', e);
            }
            this.loading = false;
        },

        async loadDataClasses() {
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/data-classes');
                var data = await resp.json();
                if (data.success) {
                    this.dataClasses = data.data || [];
                }
            } catch (e) {
                console.error('載入 data classes 失敗:', e);
            }
        },

        openCreate() {
            this.createForm = { name: '', table_name: '', description: '' };
            this.tableSuggestion = '';
            this.showCreateModal = true;
        },

        async translateTableName(name) {
            if (!name || !name.trim()) {
                this.tableSuggestion = '';
                return;
            }
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
                    this.tableSuggestion = data.code;
                }
            } catch (e) {
                // 靜默失敗
            }
        },

        async confirmCreate() {
            var name = (this.createForm.name || '').trim();
            if (!name) {
                alert('規格名稱必填');
                return;
            }
            this.creating = true;
            try {
                var resp = await fetch(window.__BP + '/api/spec-formulate/schema/specs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({
                        name: name,
                        table_name: (this.createForm.table_name || '').trim() || this.tableSuggestion || '',
                        description: (this.createForm.description || '').trim(),
                        fields: [],
                    }),
                });
                var data = await resp.json();
                if (data.success) {
                    this.showCreateModal = false;
                    // 導向編輯頁
                    window.location.href = window.__BP + '/spec-formulate/' +
                        data.data.secure_code + '/edit';
                } else {
                    alert(data.error || '建立失敗');
                }
            } catch (e) {
                alert('建立失敗: ' + e.message);
            }
            this.creating = false;
        },

        openEdit(spec) {
            window.location.href = window.__BP + '/spec-formulate/' +
                spec.secure_code + '/edit';
        },

        confirmDelete(spec) {
            this.deleteTarget = spec;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deleteTarget) return;
            this.deleting = true;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' +
                    this.deleteTarget.secure_code,
                    {
                        method: 'DELETE',
                        headers: { 'X-CSRFToken': this.csrfToken },
                    }
                );
                var data = await resp.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.deleteTarget = null;
                    this.loadSpecs();
                } else {
                    alert(data.error || '刪除失敗');
                }
            } catch (e) {
                alert('刪除失敗: ' + e.message);
            }
            this.deleting = false;
        },

        // ── 製作規格書 ──

        openDocxModal() {
            // 只列出有 active_facets 的規格
            var available = this.specs.filter(function(s) {
                return s.active_facets && s.active_facets.length > 0;
            });
            if (available.length === 0) {
                alert('目前沒有任何已啟用格式的規格可匯出');
                return;
            }

            this.docxTitle = '資料結構規格書';
            this.docxItems = [];
            this.showDocxModal = true;
        },

        docxAddSpec(spec) {
            // 避免重複加入
            var exists = false;
            for (var i = 0; i < this.docxItems.length; i++) {
                if (this.docxItems[i].spec_sc === spec.secure_code) {
                    exists = true;
                    break;
                }
            }
            if (exists) return;

            var facetSelections = {};
            (spec.active_facets || []).forEach(function(f) {
                facetSelections[f] = true;  // 預設全選
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

            // 從 docxItems 取 proxy 引用，確保 reactive 更新生效
            var proxyItem = this.docxItems[this.docxItems.length - 1];
            this._loadVersions(proxyItem);
        },

        docxRemoveSpec(index) {
            this.docxItems.splice(index, 1);
        },

        async _loadVersions(item) {
            item.loadingVersions = true;
            try {
                var resp = await fetch(
                    window.__BP + '/api/spec-formulate/schema/specs/' +
                    item.spec_sc + '/versions'
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
            // 切換版本時，更新可選 facets
            var ver = parseInt(item.version);
            var found = null;
            for (var i = 0; i < item.versions.length; i++) {
                if (item.versions[i].version === ver) {
                    found = item.versions[i];
                    break;
                }
            }
            if (found) {
                item.activeFacets = found.active_facets || [];
                // 重置 facet 選擇（只保留在新版本中仍有的）
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
            return this.specs.filter(function(s) {
                return (s.active_facets && s.active_facets.length > 0) &&
                       !selected[s.secure_code];
            });
        },

        async doExportDocx() {
            if (this.docxItems.length === 0) {
                alert('請至少加入一個規格');
                return;
            }

            // 組合 payload
            var specs = [];
            for (var i = 0; i < this.docxItems.length; i++) {
                var item = this.docxItems[i];
                var facets = [];
                var af = item.activeFacets || [];
                for (var j = 0; j < af.length; j++) {
                    if (item.selectedFacets[af[j]]) {
                        facets.push(af[j]);
                    }
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
                        doc_title: this.docxTitle || '資料結構規格書',
                        specs: specs,
                    }),
                });

                if (resp.ok) {
                    // 下載檔案
                    var blob = await resp.blob();
                    var cd = resp.headers.get('content-disposition') || '';
                    var filename = '規格書.docx';
                    // 優先讀取 filename*=UTF-8''... (RFC 5987, 支援中文)
                    var starMatch = cd.match(/filename\*=UTF-8''([^;\s]+)/i);
                    if (starMatch) {
                        filename = decodeURIComponent(starMatch[1]);
                    } else {
                        var plainMatch = cd.match(/filename="?([^";]+)"?/i);
                        if (plainMatch) {
                            filename = plainMatch[1];
                        }
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

        formatDate(ts) {
            return BkTime.format(ts, 'short');
        },
    };
}
