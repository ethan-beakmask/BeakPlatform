/**
 * org-databases.js - 企業獨立資料庫監視頁面
 */

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
        sortBy: 'id',
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
                fetch('/organizations/databases/' + org.secureCode + '/stats')
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
            var sortBy = this.sortBy;
            if (sortBy === 'tables') {
                list.sort(function(a, b) {
                    var at = (a.data && a.data.stats) ? a.data.stats.table_count : -1;
                    var bt = (b.data && b.data.stats) ? b.data.stats.table_count : -1;
                    return bt - at;
                });
            } else if (sortBy === 'size') {
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
            return org.data.stats.table_count + ' 表 / ' + org.data.db_size_display;
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
 * 企業級卡片元件（保留不動）
 */
function odbMonitor() {
    var config = window.__ODB_CONFIG || {};
    return {
        expanded: {},

        init() {
            if (config.dbCount === 1 && config.orgIds && config.orgIds.length === 1) {
                this.expanded['db_' + config.orgIds[0]] = true;
            }
        },

        toggle(key) {
            this.expanded[key] = !this.expanded[key];
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
