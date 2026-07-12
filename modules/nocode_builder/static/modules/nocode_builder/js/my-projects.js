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
                this.showToast(__('名稱為必填'), 'error');
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
                    this.showToast(__('開發案已建立'), 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || __('建立失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('建立失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        async togglePublish(item) {
            const action = item.status === 'draft' ? 'publish' : 'unpublish';
            const label = action === 'publish' ? __('上線') : __('下線');
            if (!confirm(__('確定要{action}「{name}」嗎?', {action: label, name: item.name}))) return;

            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/projects/' + item.secure_code + '/' + action, {
                    method: 'POST',
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast(__('已{action}', {action: label}), 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || __('{action}失敗', {action: label}), 'error');
                }
            } catch (e) {
                this.showToast(__('{action}失敗', {action: label}), 'error');
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
                    this.showToast(__('已刪除'), 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || __('刪除失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('刪除失敗'), 'error');
            }
        },

        statusLabel(status) {
            return status === 'published' ? __('上線中') : __('開發中');
        },

        statusClass(status) {
            return status === 'published' ? 'active' : 'draft';
        },

        layoutLabel(mode) {
            return mode === 'free' ? __('GridStack 自由') : __('Grid 宮格');
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
