/**
 * spec-multifaceted.js -- 多面向規格管理
 * Alpine.js 驅動的列表頁
 */

function specMultifacetedManager() {
    return {
        loading: true,
        specs: [],
        dataClasses: [],

        // 新增 modal
        showCreateModal: false,
        createForm: { name: '', description: '' },
        creating: false,

        // 刪除確認
        deleteTarget: null,
        showDeleteModal: false,
        deleting: false,

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
                var resp = await fetch('/api/spec-formulate/multifaceted/specs');
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
                var resp = await fetch('/api/spec-formulate/multifaceted/data-classes');
                var data = await resp.json();
                if (data.success) {
                    this.dataClasses = data.data || [];
                }
            } catch (e) {
                console.error('載入 data classes 失敗:', e);
            }
        },

        openCreate() {
            this.createForm = { name: '', description: '' };
            this.showCreateModal = true;
        },

        async confirmCreate() {
            var name = (this.createForm.name || '').trim();
            if (!name) {
                alert('規格名稱必填');
                return;
            }
            this.creating = true;
            try {
                var resp = await fetch('/api/spec-formulate/multifaceted/specs', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                    },
                    body: JSON.stringify({
                        name: name,
                        description: (this.createForm.description || '').trim(),
                        fields: [],
                    }),
                });
                var data = await resp.json();
                if (data.success) {
                    this.showCreateModal = false;
                    // 導向編輯頁
                    window.location.href = '/spec-formulate/multifaceted/' +
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
            window.location.href = '/spec-formulate/multifaceted/' +
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
                    '/api/spec-formulate/multifaceted/specs/' +
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
