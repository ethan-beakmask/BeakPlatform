/**
 * Permission Central Management
 * 權限中央管理前端邏輯
 */
function permissionCentral() {
    return {
        // Tab 狀態
        activeTab: 'role',

        // 資料
        roles: [],
        allPermissions: [],
        allMenus: [],

        // 角色視角
        selectedRoleCode: '',
        roleData: null,
        roleLoading: false,

        // 角色權限編輯
        showPermEditor: false,
        editingPerms: [],
        filterPermLevel: '',
        saving: false,

        // 功能視角
        menuTreeRoots: [],
        selectedMenuCode: '',
        menuData: null,
        menuLoading: false,

        // 衝突偵測
        conflictsData: null,
        conflictsLoading: false,
        conflictCount: 0,

        // 訊息提示
        toast: { show: false, message: '', type: '' },

        // 常數
        userTypeLabels: {
            'SYSTEM_ADMIN': '系統管理員',
            'ORG_ADMIN': '企業管理員',
            'EMPLOYEE': '員工',
            'EXTERNAL': '外部廠商'
        },

        async init() {
            await Promise.all([
                this.loadRoles(),
                this.loadPermissions(),
                this.loadMenus(),
            ]);
            this.buildMenuTree();
            // 背景載入衝突數
            this.loadConflictCount();
        },

        // ============================================================
        // 資料載入
        // ============================================================

        async loadRoles() {
            try {
                const res = await fetch('/api/permissions/roles');
                const data = await res.json();
                this.roles = data.roles || [];
            } catch (e) {
                console.error('Failed to load roles:', e);
            }
        },

        async loadPermissions() {
            try {
                const res = await fetch('/api/permissions/permissions');
                const data = await res.json();
                this.allPermissions = data.permissions || [];
            } catch (e) {
                console.error('Failed to load permissions:', e);
            }
        },

        async loadMenus() {
            try {
                const res = await fetch('/api/permissions/menus');
                const data = await res.json();
                this.allMenus = data.menus || [];
            } catch (e) {
                console.error('Failed to load menus:', e);
            }
        },

        // ============================================================
        // 角色視角
        // ============================================================

        async loadRoleView() {
            if (!this.selectedRoleCode) {
                this.roleData = null;
                return;
            }
            this.roleLoading = true;
            this.showPermEditor = false;
            try {
                const res = await fetch('/api/permissions/role-view/' + this.selectedRoleCode);
                this.roleData = await res.json();
            } catch (e) {
                console.error('Failed to load role view:', e);
                this.showToast('載入失敗', 'error');
            } finally {
                this.roleLoading = false;
            }
        },

        // ============================================================
        // 權限編輯
        // ============================================================

        get filteredPermissions() {
            if (!this.filterPermLevel) return this.allPermissions;
            return this.allPermissions.filter(p => p.permission_level === this.filterPermLevel);
        },

        togglePerm(secureCode) {
            const idx = this.editingPerms.indexOf(secureCode);
            if (idx >= 0) {
                this.editingPerms.splice(idx, 1);
            } else {
                this.editingPerms.push(secureCode);
            }
        },

        enterPermEditor() {
            if (this.showPermEditor) {
                this.showPermEditor = false;
                return;
            }
            // 進入編輯模式時，載入目前的權限
            if (this.roleData) {
                this.editingPerms = this.roleData.rbac_permissions.map(p => p.permission_secure_code);
            }
            this.showPermEditor = true;
        },

        async saveRolePermissions() {
            if (!this.selectedRoleCode) return;
            this.saving = true;
            try {
                const res = await fetch('/api/permissions/role-permissions', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role_secure_code: this.selectedRoleCode,
                        permission_secure_codes: this.editingPerms
                    })
                });
                const data = await res.json();
                if (res.ok) {
                    this.showToast(data.message + ' (+' + data.added + ' -' + data.removed + ')', 'success');
                    this.showPermEditor = false;
                    await this.loadRoleView();
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                console.error('Failed to save permissions:', e);
                this.showToast('儲存失敗', 'error');
            } finally {
                this.saving = false;
            }
        },

        // ============================================================
        // 功能視角
        // ============================================================

        buildMenuTree() {
            const map = {};
            const roots = [];

            // 建立節點 map
            for (const item of this.allMenus) {
                map[item.secure_code] = { ...item, children: [], _expanded: false };
            }

            // 建構樹
            for (const item of this.allMenus) {
                const node = map[item.secure_code];
                if (item.parent_secure_code && map[item.parent_secure_code]) {
                    map[item.parent_secure_code].children.push(node);
                } else {
                    roots.push(node);
                }
            }

            this.menuTreeRoots = roots;
        },

        selectMenu(secureCode) {
            this.selectedMenuCode = secureCode;
            this.loadMenuView();
        },

        async loadMenuView() {
            if (!this.selectedMenuCode) {
                this.menuData = null;
                return;
            }
            this.menuLoading = true;
            try {
                const res = await fetch('/api/permissions/menu-view/' + this.selectedMenuCode);
                this.menuData = await res.json();
            } catch (e) {
                console.error('Failed to load menu view:', e);
                this.showToast('載入失敗', 'error');
            } finally {
                this.menuLoading = false;
            }
        },

        // ============================================================
        // 衝突偵測
        // ============================================================

        async loadConflicts() {
            this.conflictsLoading = true;
            try {
                const res = await fetch('/api/permissions/conflicts');
                this.conflictsData = await res.json();
                this.conflictCount = this.conflictsData.summary.total;
            } catch (e) {
                console.error('Failed to load conflicts:', e);
                this.showToast('偵測失敗', 'error');
            } finally {
                this.conflictsLoading = false;
            }
        },

        async loadConflictCount() {
            try {
                const res = await fetch('/api/permissions/conflicts');
                const data = await res.json();
                this.conflictCount = data.summary.total;
            } catch (e) {
                // 背景載入，靜默失敗
            }
        },

        jumpToMenu(menuSecureCode) {
            this.activeTab = 'menu';
            this.selectedMenuCode = menuSecureCode;
            // 展開樹節點至該選單
            this.expandToMenu(menuSecureCode);
            this.loadMenuView();
        },

        expandToMenu(secureCode) {
            // 找到該節點的路徑並展開
            const expandPath = (nodes) => {
                for (const node of nodes) {
                    if (node.secure_code === secureCode) {
                        return true;
                    }
                    if (node.children && node.children.length > 0) {
                        if (expandPath(node.children)) {
                            node._expanded = true;
                            return true;
                        }
                    }
                }
                return false;
            };
            expandPath(this.menuTreeRoots);
        },

        // ============================================================
        // 訊息提示
        // ============================================================

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
