/**
 * sub_system_list.html - Alpine.js Manager
 * 子系統列表管理
 */
function subSystemListManager() {
    return {
        items: [],
        meta: { is_system_admin: false, is_org_admin: false, can_manage: false },
        loading: true,
        showCreateModal: false,
        showDeleteModal: false,
        deletingItem: null,
        createForm: {
            name: '',
            description: '',
        },
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadList();
        },

        async loadList() {
            this.loading = true;
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/sub-systems');
                const data = await res.json();
                if (data.success) {
                    this.items = data.data || [];
                    if (data.meta) {
                        this.meta = data.meta;
                    }
                }
            } catch (e) {
                console.error('Load sub-systems failed:', e);
            } finally {
                this.loading = false;
            }
        },

        async doCreate() {
            if (!this.createForm.name.trim()) {
                this.showToast(__('名稱不可為空'), 'error');
                return;
            }
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/sub-systems', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.createForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showCreateModal = false;
                    this.createForm = { name: '', description: '' };
                    this.showToast(__('子系統已建立'), 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || __('建立失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('建立失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        confirmDelete(item) {
            this.deletingItem = item;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deletingItem) return;
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + this.deletingItem.secure_code, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast(__('子系統已刪除'), 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || __('刪除失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('刪除失敗'), 'error');
            }
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        truncate(text, len) {
            if (!text) return '';
            return text.length > len ? text.substring(0, len) + '...' : text;
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
        }
    };
}
