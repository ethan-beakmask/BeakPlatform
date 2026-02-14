/* fw-instance-list.js — 我的表單列表 (Mode A) */

function instanceListManager() {
    return {
        instances: [],
        loading: true,
        tab: 'mine',
        statusFilter: '',
        pagination: { page: 1, pages: 1, total: 0, has_prev: false, has_next: false },

        showDetailModal: false,
        viewingInstance: null,

        async init() {
            await this.loadInstances();
        },

        async loadInstances() {
            this.loading = true;
            try {
                var url = '/api/form-workflow/instances?page=' + this.pagination.page + '&tab=' + this.tab;
                if (this.statusFilter) url += '&status=' + this.statusFilter;

                var res = await fetch(url);
                var data = await res.json();
                if (data.success) {
                    this.instances = data.data.instances || [];
                    this.pagination = data.data.pagination || this.pagination;
                }
            } catch (e) {
                console.error('載入失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        goToPage(page) {
            if (page < 1 || page > this.pagination.pages) return;
            this.pagination.page = page;
            this.loadInstances();
        },

        async viewDetail(i) {
            try {
                var res = await fetch('/api/form-workflow/instances/' + i.secure_code);
                var data = await res.json();
                if (data.success) {
                    this.viewingInstance = data.data;
                    this.showDetailModal = true;
                }
            } catch (e) {
                console.error('載入詳情失敗:', e);
            }
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            var d = new Date(dateStr);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', {hour: '2-digit', minute: '2-digit'});
        },

        getStatusText(status) {
            var map = {
                'DRAFT': '草稿',
                'PENDING': '待處理',
                'RUNNING': '處理中',
                'COMPLETED': '已完成',
                'REJECTED': '已駁回',
                'CANCELLED': '已取消'
            };
            return map[status] || status || '-';
        },

        getStatusClass(status) {
            var map = {
                'DRAFT': 'draft',
                'PENDING': 'pending',
                'RUNNING': 'running',
                'COMPLETED': 'completed',
                'REJECTED': 'rejected',
                'CANCELLED': 'cancelled'
            };
            return map[status] || 'draft';
        }
    };
}
