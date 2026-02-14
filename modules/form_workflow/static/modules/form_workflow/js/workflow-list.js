/**
 * workflow_list.html — Alpine.js Manager
 */
function workflowListManager() {
    return {
        workflows: [],
        loading: true,
        searchQuery: '',
        flowType: 'main',
        totalCounts: { main: 0, subflow: 0 },
        treeView: { active: false, name: '', code: '', chart: null },
        viewMode: localStorage.getItem('workflows_view_mode') || 'list',
        selectedCategory: null,
        selectedItems: [],
        batchProcessing: false,
        pagination: { page: 1, pages: 1, total: 0, has_prev: false, has_next: false },

        showModal: false,
        editingWorkflow: null,
        formData: { name: '', code: '', description: '', category_secure_code: '', is_active: true, is_subprocess: false },
        categories: [],
        flatCategories: [],
        saving: false,

        showDeleteModal: false,
        deletingWorkflow: null,
        deleteWarnings: [],

        async init() {
            await this.loadCategories();
            const saved = localStorage.getItem('workflows_filter_category');
            if (saved && this.flatCategories.some(c => c.secure_code === saved)) {
                this.selectedCategory = saved;
            } else if (this.flatCategories.length > 0) {
                this.selectedCategory = this.flatCategories[0].secure_code;
            }
            await this.loadWorkflows();
        },

        async loadCategories() {
            try {
                const res = await fetch('/api/form-workflow/categories?context=workflow_design');
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
                    const hasOther = flat.some(c => c.name === '其他');
                    if (!hasOther) {
                        flat.push({ secure_code: '__uncategorized__', name: '其他', parent_name: null, display: '其他' });
                    }
                    this.flatCategories = flat;
                    if (flat.length > 1 && !this.formData.category_secure_code) {
                        const rec = flat.find(c => c.secure_code === 'SYS_CAT_WORKFLOW_REC');
                        this.formData.category_secure_code = rec ? rec.secure_code : flat[0].secure_code;
                    }
                }
            } catch (e) {
                console.error('載入分類失敗:', e);
            }
        },

        async loadWorkflows() {
            this.loading = true;
            try {
                let url = `/api/form-workflow/workflows?page=${this.pagination.page}`;
                if (this.searchQuery) url += `&q=${encodeURIComponent(this.searchQuery)}`;
                if (this.flowType) url += `&flow_type=${this.flowType}`;

                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.workflows = data.data.workflows || [];
                    this.pagination = data.data.pagination || this.pagination;
                }
                this._updateTabCounts();
            } catch (e) {
                console.error('載入失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        async _updateTabCounts() {
            try {
                const res = await fetch(`/api/form-workflow/workflows?${this.searchQuery ? 'q=' + encodeURIComponent(this.searchQuery) : ''}`);
                const data = await res.json();
                if (data.success) {
                    const all = data.data.workflows || [];
                    this.totalCounts.main = all.filter(w => !w.is_subprocess).length;
                    this.totalCounts.subflow = all.filter(w => w.is_subprocess && !w.parent_workflow_secure_code).length;
                }
            } catch (e) { /* silent */ }
        },

        goToPage(page) {
            if (page < 1 || page > this.pagination.pages) return;
            this.pagination.page = page;
            this.loadWorkflows();
        },

        openCreateModal() {
            this.editingWorkflow = null;
            this.formData = {
                name: '', code: '', description: '',
                category_secure_code: (this.flatCategories.find(c => c.secure_code === 'SYS_CAT_WORKFLOW_REC') || this.flatCategories[0] || {}).secure_code || '',
                is_active: true,
                is_subprocess: this.flowType === 'subflow'
            };
            this.showModal = true;
        },

        editWorkflow(w) {
            window.location.href = `/forms/workflows/${w.secure_code}`;
        },

        closeModal() {
            this.showModal = false;
            this.editingWorkflow = null;
        },

        async saveWorkflow() {
            if (this.saving) return;
            this.saving = true;
            try {
                const url = this.editingWorkflow
                    ? `/api/form-workflow/workflows/${this.editingWorkflow.secure_code}`
                    : '/api/form-workflow/workflows';
                const method = this.editingWorkflow ? 'PUT' : 'POST';
                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.formData)
                });
                const data = await res.json();
                if (data.success) {
                    if (!this.editingWorkflow && data.data && data.data.secure_code) {
                        window.location.href = `/forms/workflows/${data.data.secure_code}?created=1`;
                    } else {
                        this.closeModal();
                        this.loadWorkflows();
                    }
                } else {
                    alert('操作失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('操作失敗: ' + e.message);
            } finally {
                this.saving = false;
            }
        },

        async openTree(w) {
            const rootCode = w.parent_workflow_secure_code || w.secure_code;
            try {
                const res = await fetch('/api/form-workflow/workflows/flow-trees/' + rootCode);
                const data = await res.json();
                if (!data.success) return;
                const tree = data.data.tree;
                this.treeView.name = tree.name;
                this.treeView.code = tree.code;
                this.treeView.active = true;
                this.$nextTick(() => {
                    setTimeout(() => {
                        this.treeView.chart = WorkflowTreeChart.render(
                            '#inline-tree-chart', [tree],
                            { onNodeClick: function (nodeData) {
                                window.location.href = '/api/workflows/designer/standalone?id=' + nodeData.id + '&from=tree&root=' + rootCode;
                            }}
                        );
                    }, 50);
                });
            } catch (e) {
                console.error('載入樹系圖失敗:', e);
            }
        },

        closeTree() {
            this.treeView.active = false;
            this.treeView.chart = null;
            document.getElementById('inline-tree-chart').innerHTML = '';
        },

        fitTree() {
            if (this.treeView.chart) this.treeView.chart.fit();
        },

        async confirmDelete(w) {
            this.deletingWorkflow = w;
            this.deleteWarnings = [];
            try {
                const res = await fetch(`/api/form-workflow/workflows/${w.secure_code}?check=1`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success && data.has_mappings) {
                    this.deleteWarnings = data.mappings || [];
                }
            } catch (e) { /* 預檢失敗不阻擋 */ }
            this.showDeleteModal = true;
        },

        async deleteWorkflow() {
            if (!this.deletingWorkflow) return;
            try {
                const res = await fetch(`/api/form-workflow/workflows/${this.deletingWorkflow.secure_code}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.deletingWorkflow = null;
                    this.loadWorkflows();
                } else {
                    alert('刪除失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('刪除失敗: ' + e.message);
            }
        },

        get filteredWorkflows() {
            if (!this.selectedCategory) return this.workflows;
            if (this.selectedCategory === '__uncategorized__') {
                const knownCodes = this.flatCategories.filter(c => c.secure_code !== '__uncategorized__').map(c => c.secure_code);
                return this.workflows.filter(w => !w.category_secure_code || !knownCodes.includes(w.category_secure_code));
            }
            return this.workflows.filter(w => w.category_secure_code === this.selectedCategory);
        },

        getCategoryCount(sc) {
            if (sc === '__uncategorized__') {
                const knownCodes = this.flatCategories.filter(c => c.secure_code !== '__uncategorized__').map(c => c.secure_code);
                return this.workflows.filter(w => !w.category_secure_code || !knownCodes.includes(w.category_secure_code)).length;
            }
            return this.workflows.filter(w => w.category_secure_code === sc).length;
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            const d = new Date(dateStr);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', {hour: '2-digit', minute: '2-digit'});
        },

        truncate(str, len) {
            if (!str) return '-';
            return str.length > len ? str.substring(0, len) + '...' : str;
        },

        firstLine(str) {
            if (!str) return '-';
            return str.split('\n')[0] || '-';
        },

        toggleSelect(sc) {
            const idx = this.selectedItems.indexOf(sc);
            if (idx >= 0) this.selectedItems.splice(idx, 1);
            else this.selectedItems.push(sc);
        },

        toggleSelectAll() {
            if (this.selectedItems.length === this.filteredWorkflows.length) {
                this.selectedItems = [];
            } else {
                this.selectedItems = this.filteredWorkflows.map(w => w.secure_code);
            }
        },

        invertSelection() {
            const all = this.filteredWorkflows.map(w => w.secure_code);
            this.selectedItems = all.filter(sc => !this.selectedItems.includes(sc));
        },

        async batchSaveNewVersion() {
            if (this.batchProcessing || this.selectedItems.length === 0) return;
            if (!confirm(`確定要將選取的 ${this.selectedItems.length} 個流程另存新版？`)) return;
            this.batchProcessing = true;
            try {
                const res = await fetch('/api/form-workflow/workflows/batch/save-new-version', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secure_codes: this.selectedItems })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`完成：成功 ${data.summary.succeeded}，失敗 ${data.summary.failed}`);
                    this.selectedItems = [];
                    this.loadWorkflows();
                } else {
                    alert('操作失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('操作失敗: ' + e.message);
            } finally {
                this.batchProcessing = false;
            }
        },

        async batchDelete() {
            if (this.batchProcessing || this.selectedItems.length === 0) return;
            if (!confirm(`確定要刪除選取的 ${this.selectedItems.length} 個流程？此操作無法復原。`)) return;
            this.batchProcessing = true;
            try {
                const res = await fetch('/api/form-workflow/workflows/batch/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ secure_codes: this.selectedItems })
                });
                const data = await res.json();
                if (data.success) {
                    alert(`完成：成功 ${data.summary.succeeded}，失敗 ${data.summary.failed}`);
                    this.selectedItems = [];
                    this.loadWorkflows();
                } else {
                    alert('操作失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('操作失敗: ' + e.message);
            } finally {
                this.batchProcessing = false;
            }
        }
    };
}
