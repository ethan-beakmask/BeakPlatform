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
