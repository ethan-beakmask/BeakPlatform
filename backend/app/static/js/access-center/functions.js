/**
 * Access Center - Functions authorization tab
 */
function acFunctionsTab() {
    const config = window.__AC_CONFIG || {};

    return {
        isSystemAdmin: !!config.isSystemAdmin,
        organizations: config.organizations || [],
        selectedOrgCode: config.isSystemAdmin ? '' : (config.userOrgSecureCode || ''),
        orgLabel: config.userOrgLabel || config.userOrgSecureCode || '',

        allMenus: [],
        menuTreeRoots: [],
        selectedMenuCode: '',
        selectedMenu: null,
        key1Selection: [],
        roleOptions: [],

        loadingMenus: false,
        loadingRoles: false,
        savingKey1: false,
        savingKey2: false,
        alert: { show: false, message: '', type: 'info' },

        userTypeOptions: [
            { value: 'SYSTEM_ADMIN', label: __('系統管理員'), badge: __('系') },
            { value: 'ORG_ADMIN', label: __('企業管理員'), badge: __('管') },
            { value: 'EMPLOYEE', label: __('企業成員'), badge: __('員') },
            { value: 'EXTERNAL', label: __('外部廠商'), badge: __('外') }
        ],

        async init() {
            window.addEventListener('ac:select-menu', async (event) => {
                const secureCode = event.detail ? event.detail.secureCode : '';
                const orgCode = event.detail ? event.detail.orgCode : '';
                if (!secureCode) return;
                if (this.isSystemAdmin && orgCode && orgCode !== this.selectedOrgCode) {
                    this.selectedOrgCode = orgCode;
                    await this.loadMenus();
                } else if (this.canLoadMenus && this.allMenus.length === 0) {
                    await this.loadMenus();
                }
                const node = this.findTreeNode(secureCode);
                if (node) {
                    this.expandToMenu(secureCode);
                    await this.selectMenu(node, false);
                }
            });
            if (!this.isSystemAdmin) {
                await this.loadMenus();
            }
        },

        get canLoadMenus() {
            return !this.isSystemAdmin || !!this.selectedOrgCode;
        },

        get selectedIsStructural() {
            return this.selectedMenu ? this.isStructuralNode(this.selectedMenu) : false;
        },

        get key2HelpText() {
            if (this.isSystemAdmin) {
                return __('以角色 code 批量套用到全部企業');
            }
            return __('只設定本企業角色，包含自訂角色');
        },

        get visibleRows() {
            const rows = [];
            const walk = (nodes, depth) => {
                for (const node of nodes) {
                    rows.push({ node, depth });
                    if (node._expanded && node.children.length) {
                        walk(node.children, depth + 1);
                    }
                }
            };
            walk(this.menuTreeRoots, 0);
            return rows;
        },

        _orgQueryParam() {
            if (this.isSystemAdmin && this.selectedOrgCode) {
                return '?org_code=' + encodeURIComponent(this.selectedOrgCode);
            }
            return '';
        },

        async onOrgChange() {
            this.clearSelection();
            if (!this.selectedOrgCode) {
                this.allMenus = [];
                this.menuTreeRoots = [];
                return;
            }
            await this.loadMenus();
        },

        clearSelection() {
            this.selectedMenuCode = '';
            this.selectedMenu = null;
            this.key1Selection = [];
            this.roleOptions = [];
        },

        async loadMenus() {
            if (!this.canLoadMenus) return;
            this.loadingMenus = true;
            try {
                const data = await window.acFetch('/api/permissions/menus' + this._orgQueryParam());
                this.allMenus = data.menus || [];
                this.buildMenuTree();
                if (this.selectedMenuCode) {
                    const selected = this.findTreeNode(this.selectedMenuCode);
                    if (selected) {
                        await this.selectMenu(selected, false);
                    } else {
                        this.clearSelection();
                    }
                }
            } catch (e) {
                this.showAlert(e.message || __('載入選單失敗'), 'error');
            } finally {
                this.loadingMenus = false;
            }
        },

        buildMenuTree() {
            const map = {};
            const roots = [];

            for (const item of this.allMenus) {
                const wasExpanded = this.findTreeNode(item.secure_code);
                map[item.secure_code] = Object.assign({}, item, {
                    children: [],
                    _expanded: wasExpanded ? wasExpanded._expanded : true
                });
            }

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

        findTreeNode(secureCode) {
            const stack = this.menuTreeRoots.slice();
            while (stack.length) {
                const node = stack.shift();
                if (node.secure_code === secureCode) return node;
                stack.push(...node.children);
            }
            return null;
        },

        expandToMenu(secureCode) {
            const expandPath = (nodes) => {
                for (const node of nodes) {
                    if (node.secure_code === secureCode) {
                        return true;
                    }
                    if (node.children.length && expandPath(node.children)) {
                        node._expanded = true;
                        return true;
                    }
                }
                return false;
            };
            expandPath(this.menuTreeRoots);
        },

        async selectMenu(node, toggleNode) {
            const shouldToggle = toggleNode !== false;
            if (shouldToggle && node.children.length) {
                node._expanded = !node._expanded;
            }
            this.selectedMenuCode = node.secure_code;
            this.selectedMenu = node;
            this.key1Selection = this.userTypeOptions
                .filter(type => node.user_types && node.user_types[type.value])
                .map(type => type.value);
            this.roleOptions = [];
            if (!this.isStructuralNode(node)) {
                await this.loadKey2Roles();
            }
        },

        async loadKey2Roles() {
            if (!this.selectedMenuCode) return;
            this.loadingRoles = true;
            try {
                const data = await window.acFetch('/api/menu/' + encodeURIComponent(this.selectedMenuCode) + '/roles');
                this.roleOptions = (data.available_roles || []).map(role => Object.assign({}, role));
            } catch (e) {
                this.showAlert(e.message || __('載入角色失敗'), 'error');
            } finally {
                this.loadingRoles = false;
            }
        },

        async saveKey1() {
            if (!this.selectedMenuCode || !this.isSystemAdmin) return;
            if (!this.key1Selection.length) {
                this.showAlert(__('至少需要一個 user_type'), 'error');
                return;
            }

            this.savingKey1 = true;
            try {
                const data = await window.acFetch('/api/menu/' + encodeURIComponent(this.selectedMenuCode) + '/permissions', {
                    method: 'PUT',
                    body: { user_types: this.key1Selection }
                });
                this.applyKey1ToSelected(data.user_types || this.key1Selection);
                this.showAlert(__('鑰匙1已更新'), 'success');
            } catch (e) {
                this.showAlert(e.message || __('儲存鑰匙1失敗'), 'error');
            } finally {
                this.savingKey1 = false;
            }
        },

        applyKey1ToSelected(userTypes) {
            const next = {};
            for (const type of this.userTypeOptions) {
                next[type.value] = userTypes.indexOf(type.value) !== -1;
            }
            if (this.selectedMenu) {
                this.selectedMenu.user_types = next;
            }
            const flat = this.allMenus.find(item => item.secure_code === this.selectedMenuCode);
            if (flat) {
                flat.user_types = next;
            }
        },

        async saveKey2() {
            if (!this.selectedMenuCode || this.selectedIsStructural) return;

            if (this.isSystemAdmin) {
                const orgCount = this.organizations.length;
                const warning = __('將批量套用到全部 %s 個企業...').replace('%s', orgCount);
                if (!window.confirm(warning)) {
                    return;
                }
            }

            this.savingKey2 = true;
            try {
                const selectedIds = this.roleOptions
                    .filter(role => role.selected)
                    .map(role => role.id);
                const data = await window.acFetch('/api/menu/' + encodeURIComponent(this.selectedMenuCode) + '/roles', {
                    method: 'PUT',
                    body: { role_secure_codes: selectedIds }
                });
                const countText = data.org_count
                    ? __('已更新 {count} 筆角色門檻，影響 {orgs} 個企業', { count: data.count || 0, orgs: data.org_count })
                    : __('已更新 {count} 筆角色門檻', { count: data.count || 0 });
                this.showAlert(countText, 'success');
                await this.loadKey2Roles();
            } catch (e) {
                this.showAlert(e.message || __('儲存鑰匙2失敗'), 'error');
            } finally {
                this.savingKey2 = false;
            }
        },

        isStructuralNode(node) {
            return !!(node && ['header', 'divider'].indexOf(node.link_type) !== -1);
        },

        treeIndent(depth) {
            return 'padding-left: ' + (8 + depth * 18) + 'px';
        },

        key1Badges(node) {
            if (!node || !node.user_types) return [];
            return this.userTypeOptions
                .filter(type => node.user_types[type.value])
                .map(type => ({ code: type.value.toLowerCase().replace('_', '-'), label: type.badge }));
        },

        roleOriginLabel(role) {
            return window.acRoleOriginLabel(role);
        },

        roleOriginClass(role) {
            return window.acRoleOriginClass(role);
        },

        showAlert(message, type) {
            this.alert = { show: true, message, type: type || 'info' };
            window.setTimeout(() => {
                this.alert.show = false;
            }, 3500);
        }
    };
}

window.acFunctionsTab = acFunctionsTab;
