/* hostconfig-index.js - 主機設定首頁邏輯 */

var __HOSTCONFIG = window.__HOSTCONFIG || {};

function restartFlask() {
    var btn = document.getElementById('restartBtn');
    var msg = document.getElementById('statusMsg');

    if (!confirm('確定要重新啟動 Flask 服務嗎？')) {
        return;
    }

    btn.disabled = true;
    btn.textContent = '重啟中...';
    msg.textContent = '';

    fetch(__HOSTCONFIG.restartUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
        }
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.success) {
            msg.style.color = '#2f855a';
            msg.textContent = data.message;
            setTimeout(function() { location.reload(); }, 5000);
        } else {
            msg.style.color = '#c53030';
            msg.textContent = '錯誤: ' + data.message;
            btn.disabled = false;
            btn.textContent = '重新啟動 Flask';
        }
    })
    .catch(function() {
        msg.style.color = '#2f855a';
        msg.textContent = '服務重啟中，5 秒後重新整理...';
        setTimeout(function() { location.reload(); }, 5000);
    });
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
                    this.resultMessage = '掃描失敗: ' + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = '掃描失敗: ' + err.message;
                this.resultSuccess = false;
            }
            this.scanning = false;
            this.scanned = true;
        },

        async executePurge() {
            var scopeLabel = this.scope === 'all' ? '全系統' : this.scope;
            if (this.scope !== 'all') {
                for (var i = 0; i < this.orgs.length; i++) {
                    if (this.orgs[i].secure_code === this.scope) {
                        scopeLabel = this.orgs[i].name;
                        break;
                    }
                }
            }

            if (!confirm(
                '確定要永久清除「' + scopeLabel + '」中所有標記刪除的記錄嗎？\n\n' +
                '共 ' + this.totalCount + ' 筆記錄將被永久刪除。\n' +
                '此操作無法復原！'
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
                    this.resultMessage = '清除失敗: ' + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = '清除失敗: ' + err.message;
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
        resultMessage: '',
        resultSuccess: false,

        async loadPreview() {
            try {
                var res = await fetch(__HOSTCONFIG.previewUrl);
                var data = await res.json();
                if (data.success) {
                    this.deletedOrgs = data.deleted_orgs || [];
                    this.tableCounts = data.table_counts || [];
                } else {
                    this.resultMessage = '載入失敗: ' + data.message;
                    this.resultSuccess = false;
                }
            } catch (err) {
                this.resultMessage = '載入失敗: ' + err.message;
                this.resultSuccess = false;
            }
            this.loading = false;
        },

        async executeHardDelete() {
            var orgNames = this.deletedOrgs.map(function(o) { return o.name; }).join(', ');
            if (!confirm('確定要永久刪除以下企業及其所有資料嗎？\n\n' + orgNames + '\n\n此操作無法復原！')) {
                return;
            }

            this.executing = true;
            this.resultMessage = '';

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
                    this.resultSuccess = true;
                    var msg = data.message;
                    if (data.deleted_counts && Object.keys(data.deleted_counts).length > 0) {
                        msg += '\n\n刪除明細:\n';
                        for (var table in data.deleted_counts) {
                            msg += '- ' + table + ': ' + data.deleted_counts[table] + ' 筆\n';
                        }
                    }
                    this.resultMessage = msg;
                    await this.loadPreview();
                } else {
                    this.resultSuccess = false;
                    this.resultMessage = '刪除失敗: ' + data.message;
                }
            } catch (err) {
                this.resultSuccess = false;
                this.resultMessage = '刪除失敗: ' + err.message;
            }
            this.executing = false;
        }
    };
}
