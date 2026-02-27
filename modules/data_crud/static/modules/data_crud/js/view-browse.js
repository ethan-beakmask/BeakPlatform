/**
 * view_browse.html - Alpine.js Manager
 * 資料瀏覽/操作
 */
function viewBrowseManager() {
    const config = window.__DC_BROWSE || {};

    return {
        secureCode: config.secureCode,
        viewConfig: {},
        rows: [],
        loading: true,
        search: '',
        sortCol: '',
        sortDir: 'ASC',
        pagination: { page: 1, pages: 0, total: 0, per_page: 20 },

        // Form modal
        showFormModal: false,
        editingRow: null,
        formData: {},
        saving: false,

        // Delete modal
        showDeleteModal: false,
        deletingRow: null,

        dbName: '',
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadDbInfo();
            await this.loadViewConfig();
            await this.loadRows(1);
        },

        async loadDbInfo() {
            try {
                const res = await fetch('/api/data-crud/db-info');
                const data = await res.json();
                if (data.success) {
                    this.dbName = data.data.db_name || '';
                }
            } catch (e) {
                console.error('Load db info failed:', e);
            }
        },

        // 取得可見欄位（列表顯示）
        get displayColumns() {
            if (!this.viewConfig.columns_config) return [];
            return this.viewConfig.columns_config
                .filter(c => c.visible)
                .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
        },

        // 取得表單欄位
        get formColumns() {
            if (!this.viewConfig.columns_config) return [];
            return this.viewConfig.columns_config
                .filter(c => c.visible_in_form)
                .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
        },

        async loadViewConfig() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}`);
                const data = await res.json();
                if (data.success) {
                    this.viewConfig = data.data;
                    this.sortCol = data.data.default_sort_column || '';
                    this.sortDir = data.data.default_sort_dir || 'ASC';
                }
            } catch (e) {
                console.error('Load view config failed:', e);
            }
        },

        async loadRows(page) {
            if (page !== undefined) {
                this.pagination.page = page;
            }
            this.loading = true;
            try {
                let url = `/api/data-crud/views/${this.secureCode}/rows?page=${this.pagination.page}`;
                if (this.search) url += `&q=${encodeURIComponent(this.search)}`;
                if (this.sortCol) url += `&sort=${this.sortCol}&dir=${this.sortDir}`;

                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.rows = data.data.rows || [];
                    this.pagination = {
                        page: data.data.page,
                        pages: data.data.pages,
                        total: data.data.total,
                        per_page: data.data.per_page,
                    };
                }
            } catch (e) {
                console.error('Load rows failed:', e);
            } finally {
                this.loading = false;
            }
        },

        toggleSort(col) {
            if (this.sortCol === col) {
                this.sortDir = this.sortDir === 'ASC' ? 'DESC' : 'ASC';
            } else {
                this.sortCol = col;
                this.sortDir = 'ASC';
            }
            this.loadRows(1);
        },

        // Create
        openCreateModal() {
            this.editingRow = null;
            this.formData = {};
            this.formColumns.forEach(col => {
                this.formData[col.column] = '';
            });
            this.showFormModal = true;
        },

        // Edit
        openEditModal(row) {
            this.editingRow = row;
            this.formData = {};
            this.formColumns.forEach(col => {
                const val = row[col.column];
                this.formData[col.column] = val !== null && val !== undefined ? String(val) : '';
            });
            this.showFormModal = true;
        },

        async saveRow() {
            // 組裝只包含可寫欄位的資料
            const payload = {};
            this.formColumns.forEach(col => {
                if (!col.readonly && !col.is_pk) {
                    let val = this.formData[col.column];
                    // 空字串轉 null（如果欄位 nullable）
                    if (val === '' && col.nullable) {
                        val = null;
                    }
                    payload[col.column] = val;
                }
            });

            this.saving = true;
            try {
                let url, method;
                if (this.editingRow) {
                    url = `/api/data-crud/views/${this.secureCode}/rows/${this.editingRow._row_id}`;
                    method = 'PUT';
                } else {
                    url = `/api/data-crud/views/${this.secureCode}/rows`;
                    method = 'POST';
                }

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    this.showFormModal = false;
                    this.showToast(this.editingRow ? '已更新' : '已新增', 'success');
                    await this.loadRows();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            } finally {
                this.saving = false;
            }
        },

        // Delete
        confirmDelete(row) {
            this.deletingRow = row;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deletingRow) return;
            try {
                const res = await fetch(
                    `/api/data-crud/views/${this.secureCode}/rows/${this.deletingRow._row_id}`,
                    { method: 'DELETE' }
                );
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('已刪除', 'success');
                    await this.loadRows();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
            }
        },

        formatCell(value, col) {
            if (value === null || value === undefined) return '';
            if (typeof value === 'boolean') return value ? 'Y' : 'N';
            if (typeof value === 'object') return JSON.stringify(value);
            const s = String(value);
            return s.length > 80 ? s.substring(0, 80) + '...' : s;
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
