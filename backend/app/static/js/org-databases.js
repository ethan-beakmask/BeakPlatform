/**
 * org-databases.js - 企業獨立資料庫監視頁面
 */

function _emptyHealthData() {
    return {
        provisioning: {},
        orgs: [],
        orphan_databases: [],
        orphan_roles: [],
        summary: {}
    };
}

/**
 * 系統級健康檢查面板
 */
function odbHealthPanel() {
    return {
        loading: false,
        error: '',
        data: _emptyHealthData(),

        get abnormalOrgs() {
            return (this.data.orgs || []).filter(function(org) {
                return org.status !== 'ok';
            });
        },

        get degradedOrgs() {
            return (this.data.orgs || []).filter(function(org) {
                return !!org.degrade;
            });
        },

        load() {
            var self = this;
            this.loading = true;
            this.error = '';

            fetch(window.__BP + '/organizations/databases/health')
                .then(function(resp) {
                    return resp.json().then(function(data) {
                        if (!resp.ok) {
                            throw new Error(data.error || __('健康檢查失敗'));
                        }
                        return data;
                    });
                })
                .then(function(data) {
                    self.data = data || _emptyHealthData();
                    self.data.provisioning = self.data.provisioning || {};
                    self.data.orgs = self.data.orgs || [];
                    self.data.orphan_databases = self.data.orphan_databases || [];
                    self.data.orphan_roles = self.data.orphan_roles || [];
                    self.data.summary = self.data.summary || {};
                })
                .catch(function(err) {
                    self.error = err.message || __('健康檢查失敗');
                })
                .finally(function() {
                    self.loading = false;
                });
        },

        provision(orgSecureCode) {
            var self = this;
            if (!confirm(__('補建會重新產生資料庫帳號密碼。確定要繼續？'))) return;

            var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            fetch(window.__BP + '/organizations/databases/' + encodeURIComponent(orgSecureCode) + '/provision', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({})
            })
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok || !data.success) {
                        throw new Error(data.error || __('補建失敗'));
                    }
                    return data;
                });
            })
            .then(function() {
                self.load();
            })
            .catch(function(err) {
                alert(__('補建失敗: ') + err.message);
            });
        },

        deleteOrphanDb(dbName) {
            var self = this;
            if (!confirm(__('確定要刪除資料庫 {name}？此操作無法復原。', {name: dbName}))) return;

            var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            fetch(window.__BP + '/organizations/databases/orphans/delete-database', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({db_name: dbName})
            })
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok || !data.success) {
                        throw new Error(data.error || __('刪除失敗'));
                    }
                    return data;
                });
            })
            .then(function() {
                self.load();
            })
            .catch(function(err) {
                alert(__('刪除失敗: ') + err.message);
            });
        },

        deleteOrphanRoles() {
            var self = this;
            if (!confirm(__('確定要刪除全部孤兒角色？此操作無法復原。'))) return;

            var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            fetch(window.__BP + '/organizations/databases/orphans/delete-roles', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({roles: this.data.orphan_roles || []})
            })
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok || !data.success) {
                        throw new Error(data.error || __('刪除失敗'));
                    }
                    return data;
                });
            })
            .then(function(data) {
                if (data.errors && data.errors.length > 0) {
                    // errors 是 [{resource, error}, ...]，直接 join 會變成 [object Object]
                    alert(__('部分角色刪除失敗: ') + data.errors.map(function(e) {
                        return (e.resource || '') + ': ' + (e.error || '');
                    }).join('\n'));
                }
                self.load();
            })
            .catch(function(err) {
                alert(__('刪除失敗: ') + err.message);
            });
        },

        statusLabel(status) {
            var map = {
                missing_registration: __('尚未建立'),
                not_ready: __('登記未就緒'),
                missing_database: __('登記存在但實體庫不存在'),
                unreachable: __('連線失敗')
            };
            return map[status] || status || __('未知');
        },

        formatAt(iso) {
            if (!iso) return '-';
            if (typeof BkTime !== 'undefined') {
                return BkTime.format(iso, 'short');
            }
            return iso;
        }
    };
}

/**
 * 系統級 master-detail 元件
 * 左側企業清單（搜尋/排序），右側 DB 統計
 * init 時預載所有企業 stats，供排序與即時切換
 */
function odbSystemView() {
    var rawOrgs = (window.__ODB_ORGS || []).map(function(o) {
        return {
            id: o.id,
            name: o.name,
            domain: o.domain_name,
            secureCode: o.secure_code,
            isActive: o.is_active,
            data: null,
            dataLoaded: false,
            dataLoading: true,
            dataError: null
        };
    });

    return {
        orgs: rawOrgs,
        search: '',
        sortBy: 'id_asc',
        selectedCode: null,
        allLoaded: false,
        tableSortBy: null,

        init() {
            var self = this;
            var pending = this.orgs.length;
            if (pending === 0) {
                this.allLoaded = true;
                return;
            }
            this.orgs.forEach(function(org) {
                fetch(window.__BP + '/organizations/databases/' + org.secureCode + '/stats')
                    .then(function(resp) {
                        if (!resp.ok) throw new Error('HTTP ' + resp.status);
                        return resp.json();
                    })
                    .then(function(data) {
                        _enrichStats(data);
                        org.data = data;
                        org.dataLoaded = true;
                        org.dataLoading = false;
                    })
                    .catch(function(err) {
                        org.dataError = err.message;
                        org.dataLoaded = true;
                        org.dataLoading = false;
                    })
                    .finally(function() {
                        pending--;
                        if (pending === 0) self.allLoaded = true;
                    });
            });

            // 只有一個企業時自動選取
            if (this.orgs.length === 1) {
                this.selectedCode = this.orgs[0].secureCode;
            }
        },

        toggleSort(col) {
            if (col === 'id') {
                this.sortBy = this.sortBy === 'id_asc' ? 'id_desc' : 'id_asc';
            } else if (col === 'tables') {
                this.sortBy = this.sortBy === 'tables_desc' ? 'tables_asc' : 'tables_desc';
            } else if (col === 'size') {
                this.sortBy = this.sortBy === 'size_desc' ? 'size_asc' : 'size_desc';
            }
        },

        sortIcon(col) {
            if (col === 'id') {
                if (this.sortBy === 'id_asc') return ' ^';
                if (this.sortBy === 'id_desc') return ' v';
            } else if (col === 'tables') {
                if (this.sortBy === 'tables_asc') return ' ^';
                if (this.sortBy === 'tables_desc') return ' v';
            } else if (col === 'size') {
                if (this.sortBy === 'size_asc') return ' ^';
                if (this.sortBy === 'size_desc') return ' v';
            }
            return '';
        },

        get filteredOrgs() {
            var list = this.orgs;
            if (this.search) {
                var q = this.search.toLowerCase();
                list = list.filter(function(o) {
                    return o.name.toLowerCase().indexOf(q) >= 0 ||
                           o.domain.toLowerCase().indexOf(q) >= 0;
                });
            }
            list = [].concat(list);
            var s = this.sortBy;
            var _allLoaded = this.allLoaded;
            if (s === 'id_asc') {
                list.sort(function(a, b) { return a.id - b.id; });
            } else if (s === 'id_desc') {
                list.sort(function(a, b) { return b.id - a.id; });
            } else if (s === 'tables_asc') {
                list.sort(function(a, b) {
                    var at = (a.data && a.data.stats) ? a.data.stats.table_count : -1;
                    var bt = (b.data && b.data.stats) ? b.data.stats.table_count : -1;
                    return at - bt;
                });
            } else if (s === 'tables_desc') {
                list.sort(function(a, b) {
                    var at = (a.data && a.data.stats) ? a.data.stats.table_count : -1;
                    var bt = (b.data && b.data.stats) ? b.data.stats.table_count : -1;
                    return bt - at;
                });
            } else if (s === 'size_asc') {
                list.sort(function(a, b) {
                    var as = (a.data && a.data.stats) ? a.data.stats.db_size_bytes : -1;
                    var bs = (b.data && b.data.stats) ? b.data.stats.db_size_bytes : -1;
                    return as - bs;
                });
            } else if (s === 'size_desc') {
                list.sort(function(a, b) {
                    var as = (a.data && a.data.stats) ? a.data.stats.db_size_bytes : -1;
                    var bs = (b.data && b.data.stats) ? b.data.stats.db_size_bytes : -1;
                    return bs - as;
                });
            }
            return list;
        },

        get currentOrg() {
            if (!this.selectedCode) return null;
            for (var i = 0; i < this.orgs.length; i++) {
                if (this.orgs[i].secureCode === this.selectedCode) return this.orgs[i];
            }
            return null;
        },

        selectOrg(code) {
            this.selectedCode = code;
        },

        orgStats(org) {
            if (!org.data || !org.data.stats) return '--';
            return org.data.stats.table_count + __(' 表 / ') + org.data.db_size_display;
        },

        get sortedTables() {
            var org = this.currentOrg;
            if (!org || !org.data || !org.data.stats || !org.data.stats.tables) return [];
            var list = [].concat(org.data.stats.tables);
            var s = this.tableSortBy;
            if (s === 'rows_desc') {
                list.sort(function(a, b) { return b.row_count - a.row_count; });
            } else if (s === 'rows_asc') {
                list.sort(function(a, b) { return a.row_count - b.row_count; });
            } else if (s === 'size_desc') {
                list.sort(function(a, b) { return b.total_bytes - a.total_bytes; });
            } else if (s === 'size_asc') {
                list.sort(function(a, b) { return a.total_bytes - b.total_bytes; });
            }
            return list;
        },

        toggleTableSort(col) {
            if (col === 'rows') {
                this.tableSortBy = this.tableSortBy === 'rows_desc' ? 'rows_asc' : 'rows_desc';
            } else if (col === 'size') {
                this.tableSortBy = this.tableSortBy === 'size_desc' ? 'size_asc' : 'size_desc';
            }
        },

        tableSortIcon(col) {
            if (col === 'rows') {
                return this.tableSortBy === 'rows_asc' ? ' ^' : ' v';
            } else if (col === 'size') {
                return this.tableSortBy === 'size_asc' ? ' ^' : ' v';
            }
            return '';
        }
    };
}

/**
 * 計算 stats 衍生欄位
 */
function _enrichStats(data) {
    if (data.stats && data.stats.tables) {
        data.stats.tables.forEach(function(t) {
            t.total_display = formatBytes(t.total_bytes);
            t.index_display = formatBytes(t.index_bytes);
        });
        data.stats.total_rows = data.stats.tables.reduce(function(s, t) { return s + t.row_count; }, 0);
        data.stats.total_bytes_display = formatBytes(
            data.stats.tables.reduce(function(s, t) { return s + t.total_bytes; }, 0)
        );
        data.stats.total_index_display = formatBytes(
            data.stats.tables.reduce(function(s, t) { return s + t.index_bytes; }, 0)
        );
    }
}

/**
 * 企業級 master-detail 元件
 * 左側 DB 資訊 + 資料表清單（多選/反選/排序）
 * 右側 點擊表名預覽 100 筆資料
 * 刪除：DROP TABLE 前檢查引用 → 標記稽核記錄
 */
function odbOrgView() {
    var raw = window.__ODB_ORG || {};
    var rawTables = (raw.tables || []).map(function(t) {
        return {
            name: t.name,
            row_count: t.row_count,
            total_bytes: t.total_bytes,
            index_bytes: t.index_bytes,
            total_display: t.total_display,
            index_display: t.index_display
        };
    });

    return {
        dbInfo: raw.db_info || {},
        tables: rawTables,
        selected: {},
        selectedTable: null,
        preview: null,
        previewLoading: false,
        previewError: null,
        listSortBy: null,
        deleteModal: false,
        deleteChecking: false,
        deleteRefs: {},
        deleting: false,
        detailRow: null,
        splitPct: 50,
        _dragging: false,

        get isAllSelected() {
            if (this.tables.length === 0) return false;
            for (var i = 0; i < this.tables.length; i++) {
                if (!this.selected[this.tables[i].name]) return false;
            }
            return true;
        },

        get selectedCount() {
            var c = 0;
            for (var k in this.selected) {
                if (this.selected[k]) c++;
            }
            return c;
        },

        get selectedNames() {
            var names = [];
            for (var i = 0; i < this.tables.length; i++) {
                if (this.selected[this.tables[i].name]) {
                    names.push(this.tables[i].name);
                }
            }
            return names;
        },

        get sortedTables() {
            var list = [].concat(this.tables);
            var s = this.listSortBy;
            if (s === 'name_asc') {
                list.sort(function(a, b) { return a.name.localeCompare(b.name); });
            } else if (s === 'name_desc') {
                list.sort(function(a, b) { return b.name.localeCompare(a.name); });
            } else if (s === 'rows_desc') {
                list.sort(function(a, b) { return b.row_count - a.row_count; });
            } else if (s === 'rows_asc') {
                list.sort(function(a, b) { return a.row_count - b.row_count; });
            } else if (s === 'size_desc') {
                list.sort(function(a, b) { return b.total_bytes - a.total_bytes; });
            } else if (s === 'size_asc') {
                list.sort(function(a, b) { return a.total_bytes - b.total_bytes; });
            }
            return list;
        },

        get hasReferences() {
            for (var name in this.deleteRefs) {
                var ref = this.deleteRefs[name];
                if (ref.registry) return true;
                if (ref.crud_views && ref.crud_views.length > 0) return true;
            }
            return false;
        },

        toggleSelect(name) {
            this.selected[name] = !this.selected[name];
        },

        selectAll() {
            var allSelected = this.isAllSelected;
            for (var i = 0; i < this.tables.length; i++) {
                this.selected[this.tables[i].name] = !allSelected;
            }
        },

        invertSelection() {
            for (var i = 0; i < this.tables.length; i++) {
                var name = this.tables[i].name;
                this.selected[name] = !this.selected[name];
            }
        },

        toggleListSort(col) {
            if (col === 'name') {
                this.listSortBy = this.listSortBy === 'name_asc' ? 'name_desc' : 'name_asc';
            } else if (col === 'rows') {
                this.listSortBy = this.listSortBy === 'rows_desc' ? 'rows_asc' : 'rows_desc';
            } else if (col === 'size') {
                this.listSortBy = this.listSortBy === 'size_desc' ? 'size_asc' : 'size_desc';
            }
        },

        listSortIcon(col) {
            if (col === 'name') {
                if (this.listSortBy === 'name_asc') return ' ^';
                if (this.listSortBy === 'name_desc') return ' v';
            } else if (col === 'rows') {
                if (this.listSortBy === 'rows_asc') return ' ^';
                if (this.listSortBy === 'rows_desc') return ' v';
            } else if (col === 'size') {
                if (this.listSortBy === 'size_asc') return ' ^';
                if (this.listSortBy === 'size_desc') return ' v';
            }
            return '';
        },

        selectRow(ri) {
            if (!this.preview) return;
            this.detailRow = (this.detailRow === ri) ? null : ri;
        },

        get detailRowData() {
            if (this.detailRow === null || !this.preview) return null;
            var row = this.preview.rows[this.detailRow];
            if (!row) return null;
            var cols = this.preview.columns;
            var pairs = [];
            for (var i = 0; i < cols.length; i++) {
                pairs.push({ col: cols[i], val: row[i] });
            }
            return pairs;
        },

        startDrag(e) {
            e.preventDefault();
            this._dragging = true;
            var self = this;
            var detail = this.$refs.detailPane;
            if (!detail) return;
            var rect = detail.getBoundingClientRect();
            var totalH = rect.height;
            var topY = rect.top;

            function onMove(ev) {
                if (!self._dragging) return;
                var y = (ev.clientY || ev.touches[0].clientY) - topY;
                var pct = Math.round((y / totalH) * 100);
                if (pct < 15) pct = 15;
                if (pct > 85) pct = 85;
                self.splitPct = pct;
            }
            function onUp() {
                self._dragging = false;
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                document.removeEventListener('touchmove', onMove);
                document.removeEventListener('touchend', onUp);
            }
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
            document.addEventListener('touchmove', onMove);
            document.addEventListener('touchend', onUp);
        },

        previewTable(name) {
            var self = this;
            this.selectedTable = name;
            this.preview = null;
            this.previewError = null;
            this.previewLoading = true;
            this.detailRow = null;

            fetch(window.__BP + '/admin/org-database/preview/' + encodeURIComponent(name))
                .then(function(resp) {
                    var ct = resp.headers.get('content-type') || '';
                    if (ct.indexOf('application/json') >= 0) {
                        return resp.json();
                    }
                    // 非 JSON 回應（如 HTML 錯誤頁）
                    throw new Error(__('伺服器回應異常 (HTTP ') + resp.status + ')');
                })
                .then(function(data) {
                    if (data.error) {
                        self.previewError = data.error;
                    } else {
                        self.preview = data;
                    }
                })
                .catch(function(err) {
                    self.previewError = err.message;
                })
                .finally(function() {
                    self.previewLoading = false;
                });
        },

        getTableRowCount(name) {
            for (var i = 0; i < this.tables.length; i++) {
                if (this.tables[i].name === name) {
                    return '(' + formatNumber(this.tables[i].row_count) + __(' 筆)');
                }
            }
            return '';
        },

        startDelete() {
            if (this.selectedCount === 0) return;
            var self = this;
            this.deleteModal = true;
            this.deleteChecking = true;
            this.deleteRefs = {};

            var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            fetch(window.__BP + '/admin/org-database/check-references', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({tables: this.selectedNames})
            })
            .then(function(resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function(data) {
                self.deleteRefs = data.references || {};
            })
            .catch(function(err) {
                alert(__('檢查引用失敗: ') + err.message);
                self.deleteModal = false;
            })
            .finally(function() {
                self.deleteChecking = false;
            });
        },

        confirmDelete() {
            var self = this;
            this.deleting = true;

            var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
            fetch(window.__BP + '/admin/org-database/drop-tables', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
                body: JSON.stringify({tables: this.selectedNames})
            })
            .then(function(resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function(data) {
                if (data.error) {
                    alert(__('刪除失敗: ') + data.error);
                } else {
                    location.reload();
                }
            })
            .catch(function(err) {
                alert(__('刪除失敗: ') + err.message);
            })
            .finally(function() {
                self.deleting = false;
            });
        }
    };
}

/**
 * 格式化位元組
 */
function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var idx = 0;
    var size = bytes;
    while (size >= 1024 && idx < units.length - 1) {
        size /= 1024;
        idx++;
    }
    if (idx === 0) return Math.floor(size) + ' B';
    return size.toFixed(2) + ' ' + units[idx];
}

/**
 * 格式化數字加千分位
 */
function formatNumber(n) {
    if (n === null || n === undefined) return '0';
    return n.toLocaleString();
}
