/**
 * 企業硬刪除（PF-170：由 hostconfig-index.js 搬來）
 *
 * 對象是「還存在於 organizations 表、已軟刪除」的企業，屬企業層面，
 * 所以掛在 /organizations/ 企業列表頁。
 * 對象是「已不存在企業」的殘留屬主機層面，在 /hostconfig/data-maintenance。
 *
 * 端點由頁面注入 window.__ORG_HARD_DELETE（previewUrl / executeUrl）。
 * 平台跑在 http，navigator.clipboard 不可用，複製一律走 Utils.copyToClipboard，
 * 該頁必須自行載入 app.js。
 */
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
                var res = await fetch(__ORG_HARD_DELETE.previewUrl);
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
                var res = await fetch(__ORG_HARD_DELETE.executeUrl, {
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

