/**
 * view_list.html - Alpine.js Manager
 * 視圖管理列表
 */
function viewListManager() {
    return {
        views: [],
        loading: true,
        dbName: '',
        showDeleteModal: false,
        deletingView: null,
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadDbInfo();
            await this.loadViews();
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

        async loadViews() {
            this.loading = true;
            try {
                const res = await fetch('/api/data-crud/views');
                const data = await res.json();
                if (data.success) {
                    this.views = data.data || [];
                }
            } catch (e) {
                console.error('Load views failed:', e);
            } finally {
                this.loading = false;
            }
        },

        confirmDelete(v) {
            this.deletingView = v;
            this.showDeleteModal = true;
        },

        async doDelete() {
            if (!this.deletingView) return;
            try {
                const res = await fetch(`/api/data-crud/views/${this.deletingView.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('視圖已刪除', 'success');
                    await this.loadViews();
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
