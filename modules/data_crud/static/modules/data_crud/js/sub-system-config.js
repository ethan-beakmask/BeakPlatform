/**
 * sub_system_config.html - Alpine.js Manager
 * 子系統配置（基本資訊 + 頁面管理）
 */
function subSystemConfigManager() {
    return {
        loading: true,
        secureCode: '',
        activeTab: 'sitemap',
        form: {
            name: '',
            description: '',
            icon: '',
            group_unit_secure_code: '',
            menu_item_secure_code: '',
            is_active: true,
        },
        pages: [],
        groups: [],
        menuItems: [],
        availableLayouts: [],
        expandedPage: -1,
        showAddPageModal: false,
        addPageForm: {
            page_layout_secure_code: '',
            display_name: '',
            display_order: 0,
        },
        toast: { show: false, message: '', type: 'success' },

        async init() {
            const config = window.__SSC_CONFIG || {};
            this.secureCode = config.secureCode || '';

            await Promise.all([
                this.loadSubSystem(),
                this.loadPages(),
                this.loadGroups(),
                this.loadMenuItems(),
                this.loadLayouts(),
            ]);
            this.loading = false;
        },

        async loadSubSystem() {
            try {
                const res = await fetch('/api/data-crud/sub-systems/' + this.secureCode);
                const data = await res.json();
                if (data.success) {
                    const d = data.data;
                    this.form.name = d.name || '';
                    this.form.description = d.description || '';
                    this.form.icon = d.icon || '';
                    this.form.group_unit_secure_code = d.group_unit_secure_code || '';
                    this.form.menu_item_secure_code = d.menu_item_secure_code || '';
                    this.form.is_active = d.is_active !== false;
                }
            } catch (e) {
                console.error('Load sub-system failed:', e);
            }
        },

        async loadPages() {
            try {
                const res = await fetch('/api/data-crud/sub-systems/' + this.secureCode + '/pages');
                const data = await res.json();
                if (data.success) {
                    this.pages = data.data || [];
                }
            } catch (e) {
                console.error('Load pages failed:', e);
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
                    this.menuItems = data.items.filter(m => !m.children || m.children.length === 0);
                }
            } catch (e) {
                console.error('Load menu items failed:', e);
            }
        },

        async loadLayouts() {
            try {
                const res = await fetch('/api/data-crud/pages');
                const data = await res.json();
                if (data.success) {
                    this.availableLayouts = data.data || [];
                }
            } catch (e) {
                console.error('Load layouts failed:', e);
            }
        },

        async save() {
            if (!this.form.name.trim()) {
                this.showToast('名稱不可為空', 'error');
                return;
            }
            try {
                const res = await fetch('/api/data-crud/sub-systems/' + this.secureCode, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.form),
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已儲存', 'success');
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
        },

        // === 頁面管理 ===

        togglePageDetail(idx) {
            this.expandedPage = this.expandedPage === idx ? -1 : idx;
        },

        async doAddPage() {
            if (!this.addPageForm.page_layout_secure_code) {
                this.showToast('請選擇頁面佈局', 'error');
                return;
            }
            try {
                const res = await fetch('/api/data-crud/sub-systems/' + this.secureCode + '/pages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.addPageForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showAddPageModal = false;
                    this.addPageForm = { page_layout_secure_code: '', display_name: '', display_order: 0 };
                    this.showToast('頁面已加入', 'success');
                    await this.loadPages();
                } else {
                    this.showToast(data.error || '加入失敗', 'error');
                }
            } catch (e) {
                this.showToast('加入失敗: ' + e.message, 'error');
            }
        },

        async savePage(p) {
            try {
                const res = await fetch(
                    '/api/data-crud/sub-systems/' + this.secureCode + '/pages/' + p.secure_code,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            display_name: p.display_name,
                            display_order: p.display_order,
                            visible_roles: p.visible_roles,
                            crud_overrides: p.crud_overrides,
                            data_filters: p.data_filters,
                        }),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast('頁面設定已儲存', 'success');
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
        },

        async removePage(p) {
            if (!confirm('確定移除此頁面?')) return;
            try {
                const res = await fetch(
                    '/api/data-crud/sub-systems/' + this.secureCode + '/pages/' + p.secure_code,
                    { method: 'DELETE' }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast('頁面已移除', 'success');
                    await this.loadPages();
                } else {
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (e) {
                this.showToast('移除失敗: ' + e.message, 'error');
            }
        },

        // === visible_roles 操作 ===

        hasRole(p, role) {
            return (p.visible_roles || []).includes(role);
        },

        toggleRole(p, role) {
            if (!p.visible_roles) p.visible_roles = [];
            if (role === '*') {
                // 切換「全部」
                if (this.hasRole(p, '*')) {
                    p.visible_roles = [];
                } else {
                    p.visible_roles = ['*'];
                }
                return;
            }
            // 非 * 角色：移除 * 後切換
            p.visible_roles = p.visible_roles.filter(r => r !== '*');
            const idx = p.visible_roles.indexOf(role);
            if (idx >= 0) {
                p.visible_roles.splice(idx, 1);
            } else {
                p.visible_roles.push(role);
            }
            if (p.visible_roles.length === 0) {
                p.visible_roles = ['*'];
            }
        },

        // === crud_overrides 操作 ===

        getCrud(p, role, action) {
            const overrides = p.crud_overrides || {};
            const roleOverride = overrides[role];
            if (!roleOverride) {
                // 預設: 管理層全開，成員全關
                const adminRoles = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'];
                return adminRoles.includes(role);
            }
            return roleOverride[action] || false;
        },

        setCrud(p, role, action, value) {
            if (!p.crud_overrides) p.crud_overrides = {};
            if (!p.crud_overrides[role]) {
                // 初始化
                const adminRoles = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'];
                const isAdmin = adminRoles.includes(role);
                p.crud_overrides[role] = {
                    create: isAdmin, edit: isAdmin, delete: isAdmin
                };
            }
            p.crud_overrides[role][action] = value;
        },

        // === data_filters 操作 ===

        getFilters(p, role) {
            return (p.data_filters || {})[role] || {};
        },

        addFilter(p, role) {
            if (!p.data_filters) p.data_filters = {};
            if (!p.data_filters[role]) p.data_filters[role] = {};
            // 產生一個暫時 key
            const key = 'column_' + Date.now();
            p.data_filters[role][key] = '';
        },

        removeFilter(p, role, col) {
            if (p.data_filters && p.data_filters[role]) {
                delete p.data_filters[role][col];
            }
        },

        renameFilter(p, role, oldCol, newCol) {
            if (!newCol || oldCol === newCol) return;
            if (p.data_filters && p.data_filters[role]) {
                const val = p.data_filters[role][oldCol];
                delete p.data_filters[role][oldCol];
                p.data_filters[role][newCol] = val;
            }
        },

        setFilterValue(p, role, col, value) {
            if (p.data_filters && p.data_filters[role]) {
                p.data_filters[role][col] = value;
            }
        },

        // === 通用 ===

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
