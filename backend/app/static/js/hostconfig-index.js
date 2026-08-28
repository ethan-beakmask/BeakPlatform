/* hostconfig-index.js - 主機設定首頁邏輯 */

var __HOSTCONFIG = window.__HOSTCONFIG || {};

function formatBytes(bytes) {
    bytes = Number(bytes) || 0;
    if (bytes < 1024) {
        return bytes + ' B';
    }

    var units = ['KB', 'MB', 'GB', 'TB'];
    var value = bytes / 1024;
    var unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value = value / 1024;
        unitIndex++;
    }
    return value.toFixed(1) + ' ' + units[unitIndex];
}

function formatUtcTime(isoStr) {
    if (!isoStr) {
        return '';
    }
    if (typeof BkTime !== 'undefined') {
        return BkTime.format(isoStr, 'short');
    }
    return isoStr;
}

function purgeDeletedManager() {
    return {
        scope: 'all',
        orgs: [],
        tables: [],
        scanning: false,
        scanned: false,
        executing: false,
        resultMessage: '',
        resultSuccess: false,

        get totalCount() {
            var sum = 0;
            for (var i = 0; i < this.tables.length; i++) {
                sum += this.tables[i].count;
            }
            return sum;
        },

        async loadOrgs() {
            try {
                var res = await fetch(__HOSTCONFIG.purgePreviewUrl + '?scope=all');
                var data = await res.json();
                if (data.success) {
                    this.orgs = data.orgs || [];
                }
            } catch (err) {
                // 靜默處理
            }
        },

        async scan() {
            this.scanning = true;
            this.resultMessage = '';
            this.tables = [];
            this.scanned = false;

            try {
                var url = __HOSTCONFIG.purgePreviewUrl + '?scope=' + encodeURIComponent(this.scope);
                var res = await fetch(url);
                var data = await res.json();
                if (data.success) {
                    this.tables = data.tables || [];
                    if (data.orgs) {
                        this.orgs = data.orgs;
                    }
                } else {
                    this.resultMessage = __('掃描失敗: ') + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = __('掃描失敗: ') + err.message;
                this.resultSuccess = false;
            }
            this.scanning = false;
            this.scanned = true;
        },

        async executePurge() {
            var scopeLabel = this.scope === 'all' ? __('全系統') : this.scope;
            if (this.scope !== 'all') {
                for (var i = 0; i < this.orgs.length; i++) {
                    if (this.orgs[i].secure_code === this.scope) {
                        scopeLabel = this.orgs[i].name;
                        break;
                    }
                }
            }

            if (!confirm(
                __('確定要永久清除「') + scopeLabel + __('」中所有標記刪除的記錄嗎？\n\n') +
                __('共 ') + this.totalCount + __(' 筆記錄將被永久刪除。\n') +
                __('此操作無法復原！')
            )) {
                return;
            }

            this.executing = true;
            this.resultMessage = '';

            try {
                var res = await fetch(__HOSTCONFIG.purgeExecuteUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    },
                    body: JSON.stringify({ scope: this.scope })
                });
                var data = await res.json();
                if (data.success) {
                    this.resultSuccess = true;
                    var successMsg = data.message;
                    // 重新掃描以更新計數（scan 會清 resultMessage，之後再恢復）
                    await this.scan();
                    this.resultMessage = successMsg;
                } else {
                    this.resultSuccess = false;
                    this.resultMessage = __('清除失敗: ') + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = __('清除失敗: ') + err.message;
            }
            this.executing = false;
        }
    };
}

function hardDeleteManager() {
    return {
        loading: true,
        executing: false,
        deletedOrgs: [],
        tableCounts: [],
        physical: { file_count: 0, directories: [], manual_required: [] },
        lastPhysical: null,
        errors: [],
        resultMessage: '',
        resultSuccess: false,

        async loadPreview() {
            try {
                var res = await fetch(__HOSTCONFIG.previewUrl);
                var data = await res.json();
                if (data.success) {
                    this.deletedOrgs = data.deleted_orgs || [];
                    this.tableCounts = data.table_counts || [];
                    this.physical = data.physical || { file_count: 0, directories: [], manual_required: [] };
                } else {
                    this.resultMessage = __('載入失敗: ') + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = __('載入失敗: ') + err.message;
                this.resultSuccess = false;
            }
            this.loading = false;
        },

        async executeHardDelete() {
            var orgNames = this.deletedOrgs.map(function(o) { return o.name; }).join(', ');
            if (!confirm(__('確定要永久刪除以下企業及其所有資料嗎？\n\n') + orgNames + __('\n\n此操作無法復原！'))) {
                return;
            }

            this.executing = true;
            this.resultMessage = '';
            this.errors = [];
            this.lastPhysical = null;

            try {
                var res = await fetch(__HOSTCONFIG.executeUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    }
                });
                var data = await res.json();
                if (data.success) {
                    this.resultSuccess = !data.has_errors;
                    this.errors = data.errors || [];
                    this.lastPhysical = data.physical || null;
                    var msg = data.message;
                    if (data.deleted_counts && Object.keys(data.deleted_counts).length > 0) {
                        msg += __('\n\n刪除明細:\n');
                        for (var table in data.deleted_counts) {
                            msg += '- ' + table + ': ' + data.deleted_counts[table] + __(' 筆\n');
                        }
                    }
                    this.resultMessage = msg;
                    await this.loadPreview();
                } else {
                    this.resultSuccess = false;
                    this.resultMessage = __('刪除失敗: ') + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = __('刪除失敗: ') + err.message;
            }
            this.executing = false;
        },

        copyCommand(command) {
            if (!command) {
                return;
            }
            Utils.copyToClipboard(command);
        }
    };
}

function orphanCleanupManager() {
    return {
        tables: [],
        orphanOrgs: [],
        total: 0,
        scanning: false,
        scanned: false,
        executing: false,
        errors: [],
        resultMessage: '',
        resultSuccess: false,

        async scan() {
            this.scanning = true;
            this.resultMessage = '';
            this.errors = [];
            this.tables = [];
            this.orphanOrgs = [];
            this.total = 0;
            this.scanned = false;

            try {
                var res = await fetch(__HOSTCONFIG.orphanPreviewUrl);
                var data = await res.json();
                if (data.success) {
                    this.tables = data.tables || [];
                    this.orphanOrgs = data.orphan_orgs || [];
                    this.total = data.total || 0;
                } else {
                    this.resultMessage = __('掃描失敗: ') + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = __('掃描失敗: ') + err.message;
                this.resultSuccess = false;
            }
            this.scanning = false;
            this.scanned = true;
        },

        async executeCleanup() {
            if (!confirm(
                __('確定要永久清理企業孤兒資料嗎？\n\n') +
                __('共 ') + this.total + __(' 筆記錄將被永久刪除。\n') +
                __('此操作無法復原！')
            )) {
                return;
            }

            this.executing = true;
            this.resultMessage = '';
            this.errors = [];

            try {
                var res = await fetch(__HOSTCONFIG.orphanExecuteUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    }
                });
                var data = await res.json();
                if (data.success) {
                    var msg = data.message;
                    if (data.results && data.results.length > 0) {
                        msg += __('\n\n清理明細:\n');
                        for (var i = 0; i < data.results.length; i++) {
                            var row = data.results[i];
                            msg += '- ' + row.display_name + ' (' + row.table + '): ' + row.deleted + __(' 筆\n');
                        }
                    }
                    await this.scan();
                    this.resultSuccess = !data.has_errors;
                    this.errors = data.errors || [];
                    this.resultMessage = msg;
                } else {
                    this.resultSuccess = false;
                    this.resultMessage = __('清理失敗: ') + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = __('清理失敗: ') + err.message;
            }
            this.executing = false;
        }
    };
}

function physicalOrphanManager() {
    return {
        uploadFiles: [],
        encryptedDirs: [],
        edlDirs: [],
        manualRequired: [],
        totalRemovable: 0,
        scanning: false,
        scanned: false,
        executing: false,
        errors: [],
        resultMessage: '',
        resultSuccess: false,

        formatBytes: formatBytes,
        formatUtcTime: formatUtcTime,

        async scan() {
            this.scanning = true;
            this.resultMessage = '';
            this.errors = [];
            this.uploadFiles = [];
            this.encryptedDirs = [];
            this.edlDirs = [];
            this.manualRequired = [];
            this.totalRemovable = 0;
            this.scanned = false;

            try {
                var res = await fetch(__HOSTCONFIG.physicalPreviewUrl);
                var data = await res.json();
                if (data.success) {
                    this.uploadFiles = data.orphan_upload_files || [];
                    this.encryptedDirs = data.orphan_encrypted_dirs || [];
                    this.edlDirs = data.orphan_edl_dirs || [];
                    this.manualRequired = data.manual_required || [];
                    this.totalRemovable = data.total_removable || 0;
                } else {
                    this.resultMessage = __('掃描失敗: ') + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = __('掃描失敗: ') + err.message;
                this.resultSuccess = false;
            }
            this.scanning = false;
            this.scanned = true;
        },

        async executeCleanup() {
            if (!confirm(
                __('確定要永久清理實體孤兒資源嗎？\n\n') +
                __('共 ') + this.totalRemovable + __(' 個資源將被永久刪除。\n') +
                __('此操作無法復原！')
            )) {
                return;
            }

            this.executing = true;
            this.resultMessage = '';
            this.errors = [];

            try {
                var res = await fetch(__HOSTCONFIG.physicalExecuteUrl, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    }
                });
                var data = await res.json();
                if (data.success) {
                    var msg = data.message;
                    await this.scan();
                    this.resultSuccess = !data.has_errors;
                    this.errors = data.errors || [];
                    this.resultMessage = msg;
                } else {
                    this.resultSuccess = false;
                    this.resultMessage = __('清理失敗: ') + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = __('清理失敗: ') + err.message;
            }
            this.executing = false;
        },

        copyCommand(command) {
            if (!command) {
                return;
            }
            Utils.copyToClipboard(command);
        }
    };
}
