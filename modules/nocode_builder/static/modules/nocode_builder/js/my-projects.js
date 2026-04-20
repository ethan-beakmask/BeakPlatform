/**
 * my_projects.html - Alpine.js Manager
 * 我的開發案管理
 */
function myProjectsManager() {
    return {
        items: [],
        loading: true,
        showCreateModal: false,
        showDeleteModal: false,
        deletingItem: null,
        createForm: {
            name: '',
            description: '',
            layout_mode: 'grid',
        },
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadList();
        },

        async loadList() {
            this.loading = true;
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/projects');
                const data = await res.json();
                if (data.success) {
                    this.items = data.data || [];
                }
            } catch (e) {
                console.error('Load projects failed:', e);
            } finally {
                this.loading = false;
            }
        },

        openCreate() {
            this.createForm = { name: '', description: '', layout_mode: 'grid' };
            this.showCreateModal = true;
        },

        async doCreate() {
            if (!this.createForm.name.trim()) {
                this.showToast('名稱為必填', 'error');
                return;
            }
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.createForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showCreateModal = false;
                    this.showToast('開發案已建立', 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
        },

        async togglePublish(item) {
            const action = item.status === 'draft' ? 'publish' : 'unpublish';
            const label = action === 'publish' ? '上線' : '下線';
            if (!confirm('確定要' + label + '「' + item.name + '」嗎?')) return;

            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/projects/' + item.secure_code + '/' + action, {
                    method: 'POST',
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已' + label, 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || label + '失敗', 'error');
                }
            } catch (e) {
                this.showToast(label + '失敗', 'error');
            }
        },

        confirmDelete(item) {
            this.deletingItem = item;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deletingItem) return;
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/projects/' + this.deletingItem.secure_code, {
                    method: 'DELETE',
                });
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('已刪除', 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
            }
        },

        statusLabel(status) {
            return status === 'published' ? '上線中' : '開發中';
        },

        statusClass(status) {
            return status === 'published' ? 'active' : 'draft';
        },

        layoutLabel(mode) {
            return mode === 'free' ? 'GridStack 自由' : 'Grid 宮格';
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
        }
    };
}
