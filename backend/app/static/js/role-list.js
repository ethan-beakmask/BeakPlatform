/* role-list.js — 角色列表管理 (Mode A) */

function roleListManager() {
    var rows = document.querySelectorAll('tbody tr[data-code]');
    var roles = [];
    rows.forEach(function(row) {
        roles.push({
            code: row.dataset.code,
            usage: parseInt(row.dataset.usage || '0'),
            isSystem: row.dataset.system === 'true'
        });
    });

    return {
        roles: roles,
        selectedIds: [],
        showBatchDeleteModal: false,
        isDeleting: false,
        resultMsg: '',
        resultIsError: false,

        get allSelected() {
            var selectableRoles = this.roles.filter(function(r) { return !r.isSystem; });
            var self = this;
            return selectableRoles.length > 0 && selectableRoles.every(function(r) { return self.selectedIds.includes(r.code); });
        },

        get selectedWithUsage() {
            var self = this;
            return this.roles.filter(function(r) { return self.selectedIds.includes(r.code) && r.usage > 0; }).length;
        },

        toggleAll() {
            var selectableRoles = this.roles.filter(function(r) { return !r.isSystem; });
            if (this.allSelected) {
                this.selectedIds = [];
            } else {
                this.selectedIds = selectableRoles.map(function(r) { return r.code; });
            }
        },

        toggleRole(code) {
            var idx = this.selectedIds.indexOf(code);
            if (idx >= 0) {
                this.selectedIds.splice(idx, 1);
            } else {
                this.selectedIds.push(code);
            }
        },

        invertSelection() {
            var selectableRoles = this.roles.filter(function(r) { return !r.isSystem; });
            var newSelection = [];
            var self = this;
            selectableRoles.forEach(function(r) {
                if (!self.selectedIds.includes(r.code)) {
                    newSelection.push(r.code);
                }
            });
            this.selectedIds = newSelection;
        },

        selectUnused() {
            var unusedRoles = this.roles.filter(function(r) { return !r.isSystem && r.usage === 0; });
            this.selectedIds = unusedRoles.map(function(r) { return r.code; });
        },

        confirmBatchDelete() {
            if (this.selectedIds.length === 0) return;
            this.showBatchDeleteModal = true;
        },

        getCSRFToken() {
            return document.querySelector('meta[name="csrf-token"]')?.content || '';
        },

        async doBatchDelete() {
            this.isDeleting = true;
            this.resultMsg = '';

            try {
                var resp = await fetch(window.__BP + '/api/roles/batch-delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({ ids: this.selectedIds })
                });
                var data = await resp.json();

                this.showBatchDeleteModal = false;

                if (resp.ok) {
                    this.resultIsError = false;
                    this.resultMsg = data.message;
                    if (data.errors && data.errors.length > 0) {
                        this.resultMsg += '。部分失敗：' + data.errors.join(', ');
                        this.resultIsError = true;
                    }
                    setTimeout(function() { location.reload(); }, 1500);
                } else {
                    this.resultIsError = true;
                    this.resultMsg = data.error || '刪除失敗';
                }
            } catch (e) {
                console.error('Batch delete error:', e);
                this.showBatchDeleteModal = false;
                this.resultIsError = true;
                this.resultMsg = '網路錯誤，請稍後再試';
            } finally {
                this.isDeleting = false;
            }
        }
    };
}
