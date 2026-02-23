/**
 * data-spec-list.js -- 資料表規格管理
 * Alpine.js component
 */

function dataSpecManager() {
    return {
        items: [],
        loading: true,
        totalRegistries: 0,

        // 新增 Modal
        showNewModal: false,
        availableTemplates: [],
        loadingTemplates: false,
        selectedTemplateSc: null,

        // 比對 Modal
        showCompareModal: false,
        compareResult: null,
        compareTemplateName: '',
        comparing: false,

        // 建立中
        creating: false,

        async init() {
            await this.loadData();
        },

        async loadData() {
            this.loading = true;
            try {
                const res = await fetch('/api/form-workflow/specs/registry-overview');
                const data = await res.json();
                if (data.success) {
                    this.items = (data.data || []).map(item => ({
                        ...item,
                        expanded: false,
                    }));
                    this.totalRegistries = this.items.reduce(
                        (sum, item) => sum + (item.registries || []).length, 0
                    );
                } else {
                    _dsToast('error', data.error || '載入失敗');
                }
            } catch (e) {
                _dsToast('error', '載入失敗: ' + e.message);
            }
            this.loading = false;
        },

        toggleExpand(item) {
            item.expanded = !item.expanded;
        },

        // --- 新增規格 ---
        async openNewSpec() {
            this.showNewModal = true;
            this.selectedTemplateSc = null;
            this.loadingTemplates = true;
            try {
                const res = await fetch('/api/form-workflow/specs/available-templates');
                const data = await res.json();
                if (data.success) {
                    this.availableTemplates = data.data || [];
                } else {
                    _dsToast('error', data.error || '載入範本失敗');
                }
            } catch (e) {
                _dsToast('error', '載入範本失敗: ' + e.message);
            }
            this.loadingTemplates = false;
        },

        selectTemplate(sc) {
            this.selectedTemplateSc = sc;
        },

        confirmNewSpec() {
            if (!this.selectedTemplateSc) {
                _dsToast('error', '請選擇表單範本');
                return;
            }
            this.showNewModal = false;
            window.open('/forms/templates/' + this.selectedTemplateSc + '/spec', '_blank');
        },

        // --- 跳轉編輯器 ---
        goToSpecEditor(ftSc) {
            window.open('/forms/templates/' + ftSc + '/spec', '_blank');
        },

        // --- 建立規格 (sync-from-formio) ---
        async createSpec(item) {
            if (this.creating) return;
            this.creating = true;
            try {
                const res = await fetch(
                    '/api/form-workflow/specs/' + item.form_template_secure_code + '/sync-from-formio',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}',
                    }
                );
                const data = await res.json();
                if (data.success) {
                    _dsToast('success', data.message || '規格已建立');
                    await this.loadData();
                } else {
                    _dsToast('error', data.error || '建立失敗');
                }
            } catch (e) {
                _dsToast('error', '建立失敗: ' + e.message);
            }
            this.creating = false;
        },

        // --- 三向比對 ---
        async runCompare(item) {
            this.comparing = true;
            this.compareTemplateName = item.form_template_name;
            try {
                const res = await fetch(
                    '/api/form-workflow/specs/' + item.form_template_secure_code + '/compare'
                );
                const data = await res.json();
                if (data.success) {
                    this.compareResult = data.data;
                    this.showCompareModal = true;
                } else {
                    _dsToast('error', data.error || '比對失敗');
                }
            } catch (e) {
                _dsToast('error', '比對失敗: ' + e.message);
            }
            this.comparing = false;
        },

        // --- 工具 ---
        formatDate(iso) {
            if (!iso) return '-';
            const d = new Date(iso);
            return d.toLocaleDateString('zh-TW') + ' ' +
                   d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        },

        getStatusClass(status) {
            if (!status) return 'none';
            const s = status.toLowerCase();
            if (s === 'published') return 'published';
            if (s === 'suspended') return 'suspended';
            if (s === 'archived') return 'archived';
            return 'none';
        },

        getStatusLabel(status) {
            if (!status) return '-';
            const map = {
                'Published': '已發行',
                'Suspended': '已停用',
                'Archived': '已封存',
            };
            return map[status] || status;
        },
    };
}

function _dsToast(type, msg) {
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;padding:10px 18px;border-radius:4px;font-size:13px;max-width:400px;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    if (type === 'success') {
        el.style.background = '#d1fae5';
        el.style.color = '#065f46';
        el.style.border = '1px solid #6ee7b7';
    } else if (type === 'error') {
        el.style.background = '#fee2e2';
        el.style.color = '#991b1b';
        el.style.border = '1px solid #fca5a5';
    } else {
        el.style.background = '#e0e7ff';
        el.style.color = '#3730a3';
        el.style.border = '1px solid #a5b4fc';
    }
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}
