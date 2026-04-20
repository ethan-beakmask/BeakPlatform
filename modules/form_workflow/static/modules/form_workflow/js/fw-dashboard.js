/* fw-dashboard.js — 表單流程儀表板 (Mode A) */

function fwDashboard() {
    return {
        loading: true,
        stats: {
            form_templates: 0,
            workflow_templates: 0,
            form_instances: 0,
            pending_instances: 0
        },
        templates: [],
        workflows: [],
        instances: [],

        async init() {
            await Promise.all([
                this.loadStats(),
                this.loadTemplates(),
                this.loadWorkflows(),
                this.loadInstances()
            ]);
            this.loading = false;
        },

        async loadStats() {
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/stats');
                const data = await res.json();
                if (data.success) {
                    this.stats = data.data;
                }
            } catch (e) {
                console.error('載入統計失敗:', e);
            }
        },

        async loadTemplates() {
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/templates');
                const data = await res.json();
                if (data.success) {
                    this.templates = data.data.templates || [];
                }
            } catch (e) {
                console.error('載入模板失敗:', e);
            }
        },

        async loadWorkflows() {
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/workflows');
                const data = await res.json();
                if (data.success) {
                    this.workflows = data.data.workflows || [];
                }
            } catch (e) {
                console.error('載入工作流失敗:', e);
            }
        },

        async loadInstances() {
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/instances');
                const data = await res.json();
                if (data.success) {
                    this.instances = data.data.instances || [];
                }
            } catch (e) {
                console.error('載入實例失敗:', e);
            }
        },

        goTo(page) {
            var urls = {
                'templates': window.__BP + '/forms/templates',
                'workflows': window.__BP + '/forms/workflows',
                'instances': window.__BP + '/forms/instances',
                'pending': window.__BP + '/forms/pending'
            };
            if (urls[page]) {
                window.location.href = urls[page];
            }
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
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
            return map[status] || status;
        },

        getStatusClass(status) {
            var map = {
                'DRAFT': 'pending',
                'PENDING': 'pending',
                'RUNNING': 'running',
                'COMPLETED': 'completed',
                'REJECTED': 'pending',
                'CANCELLED': 'pending'
            };
            return map[status] || 'pending';
        }
    };
}
