/**
 * sub_system_list.html - Alpine.js Manager
 * 子系統列表管理
 */
function subSystemListManager() {
    return {
        items: [],
        groups: [],
        menuItems: [],
        loading: true,
        showCreateModal: false,
        showDeleteModal: false,
        deletingItem: null,
        createForm: {
            name: '',
            description: '',
            icon: '',
            group_unit_secure_code: '',
            menu_item_secure_code: '',
        },
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await Promise.all([
                this.loadList(),
                this.loadGroups(),
                this.loadMenuItems(),
            ]);
        },

        async loadList() {
            this.loading = true;
            try {
                const res = await fetch('/api/data-crud/sub-systems');
                const data = await res.json();
                if (data.success) {
                    this.items = data.data || [];
                }
            } catch (e) {
                console.error('Load sub-systems failed:', e);
            } finally {
                this.loading = false;
            }
        },

        async loadGroups() {
            try {
                const res = await fetch('/api/units/groups');
                const data = await res.json();
                if (data.units) {
                    this.groups = data.units || [];
                }
            } catch (e) {
                console.error('Load groups failed:', e);
            }
        },

        async loadMenuItems() {
            try {
                const res = await fetch('/api/menu');
                const data = await res.json();
                if (data.items) {
                    // 只列出 leaf 節點（無子項的選單）
                    this.menuItems = data.items.filter(m => !m.children || m.children.length === 0);
                }
            } catch (e) {
                console.error('Load menu items failed:', e);
            }
        },

        async doCreate() {
            if (!this.createForm.name.trim()) {
                this.showToast('名稱不可為空', 'error');
                return;
            }
            if (!this.createForm.group_unit_secure_code) {
                this.showToast('請選擇綁定社群', 'error');
                return;
            }
            try {
                const res = await fetch('/api/data-crud/sub-systems', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.createForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showCreateModal = false;
                    this.createForm = {
                        name: '', description: '', icon: '',
                        group_unit_secure_code: '', menu_item_secure_code: '',
                    };
                    this.showToast('子系統已建立', 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
        },

        confirmDelete(item) {
            this.deletingItem = item;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deletingItem) return;
            try {
                const res = await fetch('/api/data-crud/sub-systems/' + this.deletingItem.secure_code, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('子系統已刪除', 'success');
                    await this.loadList();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
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
            if (!dateStr) return '-';
            return new Date(dateStr).toLocaleString('zh-TW');
        }
    };
}
