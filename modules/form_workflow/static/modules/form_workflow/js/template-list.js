/**
 * template_list.html — Alpine.js Manager
 */
function templateListManager() {
    return {
        templates: [],
        loading: true,
        searchQuery: '',
        viewMode: localStorage.getItem('forms_view_mode') || 'grid',
        selectedCategory: null,
        selectedItems: [],
        batchProcessing: false,
        pagination: { page: 1, pages: 1, total: 0, has_prev: false, has_next: false },
        _thumbPendingTimer: null,
        _thumbPendingCount: 0,
        _refreshTimer: null,
        _refreshCount: 0,

        showModal: false,
        editingTemplate: null,
        formData: { name: '', code: '', description: '', category_secure_code: '', is_active: true },
        categories: [],
        flatCategories: [],
        saving: false,

        showSchemaModal: false,
        viewingTemplate: null,

        showDeleteModal: false,
        deletingTemplate: null,
        deleteWarnings: [],

        async init() {
            await this.loadCategories();
            await this.loadTemplates();
            const saved = localStorage.getItem('forms_filter_category');
            if (saved && this.flatCategories.some(c => c.secure_code === saved)) {
                this.selectedCategory = saved;
            } else if (this.flatCategories.length > 0) {
                this.selectedCategory = this.flatCategories[0].secure_code;
            }
            this.pollPendingThumbnail();
            this.startPeriodicRefresh();
        },

        async loadCategories() {
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/categories?context=form_design');
                const data = await res.json();
                if (data.success) {
                    this.categories = data.data || [];
                    const flat = [];
                    this.categories.forEach(parent => {
                        const children = parent.children || [];
                        if (children.length > 0) {
                            children.forEach(child => {
                                flat.push({
                                    secure_code: child.secure_code,
                                    name: child.name,
                                    parent_name: parent.name,
                                    display: parent.name + ' / ' + child.name
                                });
                            });
                        } else {
                            flat.push({
                                secure_code: parent.secure_code,
                                name: parent.name,
                                parent_name: null,
                                display: parent.name
                            });
                        }
                    });
                    this.flatCategories = flat;
                    if (flat.length > 0 && !this.formData.category_secure_code) {
                        const rec = flat.find(c => c.secure_code === 'SYS_CAT_WORKFLOW_REC');
                        this.formData.category_secure_code = rec ? rec.secure_code : flat[0].secure_code;
                    }
                }
            } catch (e) {
                console.error('載入分類失敗:', e);
            }
        },

        async loadTemplates() {
            this.loading = true;
            try {
                let url = `${window.__BP}/api/form-workflow/templates?page=${this.pagination.page}`;
                if (this.searchQuery) url += `&q=${encodeURIComponent(this.searchQuery)}`;

                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.templates = data.data.templates || [];
                    this.pagination = data.data.pagination || this.pagination;
                }
            } catch (e) {
                console.error('載入失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        startPeriodicRefresh() {
            this._refreshCount = 0;
            this._refreshTimer = setInterval(() => {
                this._refreshCount++;
                this.silentReload();
                if (this._refreshCount === 4) {
                    clearInterval(this._refreshTimer);
                    this._refreshTimer = setInterval(() => this.silentReload(), 120000);
                }
            }, 3000);
        },

        async silentReload() {
            try {
                let url = `${window.__BP}/api/form-workflow/templates?page=${this.pagination.page}`;
                if (this.searchQuery) url += `&q=${encodeURIComponent(this.searchQuery)}`;
                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.templates = data.data.templates || [];
                    this.pagination = data.data.pagination || this.pagination;
                }
            } catch (e) { /* silent */ }
        },

        pollPendingThumbnail() {
            const pendingCode = sessionStorage.getItem('thumb_pending');
            if (!pendingCode) return;
            sessionStorage.removeItem('thumb_pending');
            this._thumbPendingCount = 0;
            this._thumbPendingTimer = setInterval(async () => {
                this._thumbPendingCount++;
                if (this._thumbPendingCount > 10) {
                    clearInterval(this._thumbPendingTimer);
                    this._thumbPendingTimer = null;
                    return;
                }
                try {
                    const res = await fetch(`${window.__BP}/api/form-workflow/templates/${pendingCode}`);
                    const data = await res.json();
                    if (!data.success || !data.data.thumbnail_2x1) return;
                    const target = this.templates.find(t => t.secure_code === pendingCode);
                    if (target) target.thumbnail_2x1 = data.data.thumbnail_2x1;
                    clearInterval(this._thumbPendingTimer);
                    this._thumbPendingTimer = null;
                } catch (e) { /* silent */ }
            }, 3000);
        },

        goToPage(page) {
            if (page < 1 || page > this.pagination.pages) return;
            this.pagination.page = page;
            this.loadTemplates();
        },

        openCreateModal() {
            this.editingTemplate = null;
            const rec = this.flatCategories.find(c => c.secure_code === 'SYS_CAT_WORKFLOW_REC');
            this.formData = { name: '', code: '', description: '', category_secure_code: rec ? rec.secure_code : (this.flatCategories.length > 0 ? this.flatCategories[0].secure_code : ''), is_active: true };
            this.showModal = true;
        },

        editTemplate(t) {
            window.location.href = `${window.__BP}/forms/templates/${t.secure_code}`;
        },

        closeModal() {
            this.showModal = false;
            this.editingTemplate = null;
        },

        async saveTemplate() {
            if (this.saving) return;
            this.saving = true;

            try {
                const url = this.editingTemplate
                    ? `${window.__BP}/api/form-workflow/templates/${this.editingTemplate.secure_code}`
                    : window.__BP + '/api/form-workflow/templates';
                const method = this.editingTemplate ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.formData)
                });
                const data = await res.json();

                if (data.success) {
                    if (!this.editingTemplate && data.data && data.data.secure_code) {
                        window.location.href = `${window.__BP}/forms/templates/${data.data.secure_code}?created=1`;
                    } else {
                        this.closeModal();
                        this.loadTemplates();
                    }
                } else {
                    alert(__('操作失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('操作失敗: ') + e.message);
            } finally {
                this.saving = false;
            }
        },

        async viewSchema(t) {
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/templates/${t.secure_code}`);
                const data = await res.json();
                if (data.success) {
                    this.viewingTemplate = data.data;
                    this.showSchemaModal = true;
                }
            } catch (e) {
                console.error('載入結構失敗:', e);
            }
        },

        async confirmDelete(t) {
            this.deletingTemplate = t;
            this.deleteWarnings = [];
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/templates/${t.secure_code}?check=1`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success && data.has_mappings) {
                    this.deleteWarnings = data.mappings || [];
                }
            } catch (e) { /* 預檢失敗不阻擋 */ }
            this.showDeleteModal = true;
        },

        async deleteTemplate() {
            if (!this.deletingTemplate) return;

            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/templates/${this.deletingTemplate.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();

                if (data.success) {
                    this.showDeleteModal = false;
                    this.deletingTemplate = null;
                    this.loadTemplates();
                } else {
                    alert(__('刪除失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('刪除失敗: ') + e.message);
            }
        },

        get filteredTemplates() {
            if (this.selectedCategory === null) return this.templates;
            if (this.selectedCategory === 'SYS_CAT_OTHER') {
                return this.templates.filter(t => !t.category_secure_code || t.category_secure_code === 'SYS_CAT_OTHER');
            }
            return this.templates.filter(t => t.category_secure_code === this.selectedCategory);
        },

        getCategoryCount(sc) {
            if (sc === 'SYS_CAT_OTHER') {
                return this.templates.filter(t => !t.category_secure_code || t.category_secure_code === 'SYS_CAT_OTHER').length;
            }
            return this.templates.filter(t => t.category_secure_code === sc).length;
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
        },

        truncate(str, len) {
            if (!str) return '-';
            return str.length > len ? str.substring(0, len) + '...' : str;
        },

        toggleSelect(sc) {
            const idx = this.selectedItems.indexOf(sc);
            if (idx >= 0) this.selectedItems.splice(idx, 1);
            else this.selectedItems.push(sc);
        },

        toggleSelectAll() {
            if (this.selectedItems.length === this.filteredTemplates.length) {
                this.selectedItems = [];
            } else {
                this.selectedItems = this.filteredTemplates.map(t => t.secure_code);
            }
        },

        invertSelection() {
            const all = this.filteredTemplates.map(t => t.secure_code);
            this.selectedItems = all.filter(sc => !this.selectedItems.includes(sc));
        },

        async batchSaveNewVersion() {
            if (this.batchProcessing || this.selectedItems.length === 0) return;
            if (!confirm(`確定要將選取的 ${this.selectedItems.length} 個表單另存新版？`)) return;
            this.batchProcessing = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/templates/batch/save-new-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secure_codes: this.selectedItems })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`完成：成功 ${data.summary.succeeded}，失敗 ${data.summary.failed}`);
                    this.selectedItems = [];
                    this.loadTemplates();
                } else {
                    alert(__('操作失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('操作失敗: ') + e.message);
            } finally {
                this.batchProcessing = false;
            }
        },

        async handleImportFile(event) {
            const file = event.target.files[0];
            event.target.value = '';
            if (!file) return;

            try {
                const text = await file.text();
                const json = JSON.parse(text);
                const items = json.items;
                if (!Array.isArray(items) || items.length === 0) {
                    alert(__('JSON 格式不正確或無匯入項目'));
                    return;
                }
                if (!confirm(`即將匯入 ${items.length} 個表單模板，code 重複者將跳過。確定？`)) return;

                const res = await fetch(window.__BP + '/api/form-workflow/templates/batch/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ items })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`匯入完成：建立 ${data.summary.created}，跳過 ${data.summary.skipped}`);
                    this.loadTemplates();
                } else {
                    alert(__('匯入失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('匯入失敗: ') + e.message);
            }
        },

        async batchExport() {
            if (this.batchProcessing || this.selectedItems.length === 0) return;
            this.batchProcessing = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/templates/batch/export', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secure_codes: this.selectedItems })
                });
                const data = await res.json();
                if (data.success) {
                    const blob = new Blob([JSON.stringify(data.data, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const now = new Date();
                    const ts = now.getFullYear().toString() +
                        String(now.getMonth() + 1).padStart(2, '0') +
                        String(now.getDate()).padStart(2, '0') + '_' +
                        String(now.getHours()).padStart(2, '0') +
                        String(now.getMinutes()).padStart(2, '0') +
                        String(now.getSeconds()).padStart(2, '0');
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `forms_export_${ts}.json`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } else {
                    alert(__('匯出失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('匯出失敗: ') + e.message);
            } finally {
                this.batchProcessing = false;
            }
        },

        async batchDelete() {
            if (this.batchProcessing || this.selectedItems.length === 0) return;
            if (!confirm(`確定要刪除選取的 ${this.selectedItems.length} 個表單？此操作無法復原。`)) return;
            this.batchProcessing = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/templates/batch/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secure_codes: this.selectedItems })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`完成：成功 ${data.summary.succeeded}，失敗 ${data.summary.failed}`);
                    this.selectedItems = [];
                    this.loadTemplates();
                } else {
                    alert(__('操作失敗: ') + (data.error || data.message));
                }
            } catch (e) {
                alert(__('操作失敗: ') + e.message);
            } finally {
                this.batchProcessing = false;
            }
        }
    };
}
