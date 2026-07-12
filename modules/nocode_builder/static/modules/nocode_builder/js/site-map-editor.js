/**
 * site-map-editor.js -- 網站地圖編輯器
 * Alpine.js component: Wunderbaum 樹 + 節點屬性面板 + access_roles 准入設定
 */
var SM_ROLES = ['GUEST', 'MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2', 'MEMBER'];

function siteMapEditor(subSystemSc) {
    return {
        loading: true,
        tree: [],
        _wbTree: null,
        selectedNode: null,
        availableLayouts: [],

        // 節點屬性表單
        nodeForm: {
            name: '', icon: '',
            page_layout_secure_code: '', is_active: true,
            access_roles: [],
            redirect_to: window.__BP + '/dashboard',
            crud_overrides: {}, data_filters: {},
            permission_mode: 'inherit',
            permission_policy_secure_code: '',
        },

        // 權限政策組列表 (從 [設定] 頁建立)
        permissionPolicies: [],

        // 新增網頁 Modal
        showAddModal: false,
        addForm: {
            name: '', icon: '',
            page_layout_secure_code: '', parent_secure_code: null,
        },

        // 准入權限（grant-based）
        nodePermissions: [],
        nodePermLoading: false,
        newNodePerm: { grant_type: 'department', grant_target: '', include_children: false, _selectedName: '' },
        permTargetOptions: [],
        permTreeLoading: false,
        permSaving: false,
        _permCache: {},

        toast: { show: false, message: '', type: 'success' },

        // Icon picker state
        _ip_show: false,
        _ip_activeCategory: 'business',
        _ip_search: '',
        _ip_selectedIcon: '',
        _iconTarget: 'node',   // 'node' | 'add'

        async init() {
            await Promise.all([
                this.loadTree(),
                this.loadLayouts(),
                this.loadPermissionPolicies(),
            ]);
            this.loading = false;
        },

        // ===== 資料載入 =====

        async loadTree() {
            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map');
                var data = await res.json();
                if (data.success) {
                    this.tree = data.data || [];
                }
            } catch (e) {
                console.error('loadTree:', e);
            }
            this._renderTree();
        },

        async loadLayouts() {
            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/pages');
                var data = await res.json();
                if (data.success) {
                    this.availableLayouts = data.data || [];
                }
            } catch (e) {
                console.error('loadLayouts:', e);
            }
        },

        async loadPermissionPolicies() {
            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/permission-policies');
                var data = await res.json();
                if (data.success) {
                    this.permissionPolicies = data.data || [];
                }
            } catch (e) {
                console.error('loadPermissionPolicies:', e);
            }
        },

        // ===== Wunderbaum 樹 =====

        _treeToSource(nodes) {
            var self = this;
            return nodes.map(function(n) {
                var icon = n.icon || 'ri-file-text-line';
                var node = {
                    title: n.name,
                    key: n.secure_code,
                    icon: icon,
                    expanded: true,
                    data: n,
                };
                if (n.children && n.children.length > 0) {
                    node.children = self._treeToSource(n.children);
                }
                return node;
            });
        },

        _destroyTree() {
            if (this._wbTree) {
                try { this._wbTree.destroy(); } catch (e) { /* ignore */ }
                this._wbTree = null;
            }
            var el = document.getElementById('sm-tree');
            if (el) el.innerHTML = '';
        },

        _renderTree() {
            var self = this;
            this._destroyTree();

            this.$nextTick(function() {
                var el = document.getElementById('sm-tree');
                if (!el) return;
                if (typeof mar10 === 'undefined' || !mar10.Wunderbaum) {
                    console.error('Wunderbaum not loaded');
                    return;
                }

                var source = self._treeToSource(self.tree);

                self._wbTree = new mar10.Wunderbaum({
                    element: el,
                    id: 'sm-editor',
                    source: source,
                    selectMode: 'single',

                    activate: function(e) {
                        var d = e.node.data;
                        self.selectNodeData(d);
                    },

                    dnd: {
                        effectAllowed: 'move',
                        dropEffectDefault: 'move',
                        dragStart: function() { return true; },
                        dragEnter: function(e) {
                            return ['before', 'after', 'over'];
                        },
                        drop: function(e) {
                            e.node.moveTo(e.region === 'over' ? e.targetNode : e.targetNode, e.region);
                            self._saveReorder();
                        },
                    },
                });
            });
        },

        selectNodeData(d) {
            this.selectedNode = d;
            this.nodeForm = {
                name: d.name || '',
                icon: d.icon || '',
                page_layout_secure_code: d.page_layout_secure_code || '',
                is_active: d.is_active !== false,
                access_roles: (d.access_roles || []).slice(),
                redirect_to: d.redirect_to || window.__BP + '/dashboard',
                crud_overrides: JSON.parse(JSON.stringify(d.crud_overrides || {})),
                data_filters: JSON.parse(JSON.stringify(d.data_filters || {})),
                permission_mode: d.permission_mode || 'inherit',
                permission_policy_secure_code: d.permission_policy_secure_code || '',
            };
            this._ip_selectedIcon = this.nodeForm.icon;
            // 載入准入權限 (僅 custom 模式需要)
            if (this.nodeForm.permission_mode === 'custom') {
                this.loadNodePermissions(d.secure_code);
            } else {
                this.nodePermissions = [];
                this.nodePermLoading = false;
            }
        },

        // ===== 准入控制 (grant-based permissions) =====

        async loadNodePermissions(nodeSc) {
            this.nodePermLoading = true;
            this.nodePermissions = [];
            this.newNodePerm = { grant_type: 'department', grant_target: '', include_children: false, _selectedName: '' };
            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + nodeSc + '/permissions');
                var data = await res.json();
                if (data.success) {
                    // 只取 grant-based 記錄
                    this.nodePermissions = (data.data || []).filter(function(p) { return p.grant_type; });
                }
            } catch (e) {
                console.error('loadNodePermissions:', e);
            } finally {
                this.nodePermLoading = false;
            }
            // 預載部門樹
            await this._loadPermTargets('department');
        },

        async onPermTypeChange() {
            this.newNodePerm.grant_target = '';
            this.newNodePerm.include_children = false;
            this.newNodePerm._selectedName = '';
            await this._loadPermTargets(this.newNodePerm.grant_type);
        },

        async _loadPermTargets(grantType) {
            this.permTargetOptions = [];
            var container = document.getElementById('sm-perm-tree-container');

            if (grantType === 'department' || grantType === 'group') {
                this.permTreeLoading = true;
                if (container) container.innerHTML = '';
                try {
                    var treeRoots = [];
                    var orgName = __('企業');
                    if (grantType === 'department') {
                        if (!this._permCache.departments) {
                            var res = await fetch(window.__BP + '/api/units/departments?tree=true');
                            var data = await res.json();
                            this._permCache.departments = data.units || [];
                        }
                        treeRoots = [{
                            secure_code: '__ORG_ROOT__',
                            name: orgName,
                            full_path: orgName,
                            children: this._permCache.departments,
                            _isVirtualRoot: true,
                        }];
                    } else {
                        if (!this._permCache.groups) {
                            var res2 = await fetch(window.__BP + '/api/units/groups?tree=true');
                            var data2 = await res2.json();
                            this._permCache.groups = data2.units || [];
                        }
                        var intGroups = [];
                        var extGroups = [];
                        for (var i = 0; i < this._permCache.groups.length; i++) {
                            var g = this._permCache.groups[i];
                            if (g.code === 'EXTERNAL_VENDORS' || g.code === 'external_vendors') {
                                extGroups.push(g);
                            } else {
                                intGroups.push(g);
                            }
                        }
                        treeRoots.push({
                            secure_code: '__ORG_ROOT__',
                            name: orgName,
                            full_path: orgName,
                            children: intGroups,
                            _isVirtualRoot: true,
                        });
                        for (var j = 0; j < extGroups.length; j++) {
                            treeRoots.push(extGroups[j]);
                        }
                    }
                    if (container) {
                        this._renderPermTree(container, treeRoots, 0);
                    }
                } catch (e) {
                    console.error('_loadPermTargets tree:', e);
                } finally {
                    this.permTreeLoading = false;
                }
            } else if (grantType === 'user') {
                if (!this._permCache.users) {
                    var res3 = await fetch(window.__BP + '/api/users?per_page=100');
                    var data3 = await res3.json();
                    if (data3.users) {
                        this._permCache.users = data3.users;
                    }
                }
                this.permTargetOptions = (this._permCache.users || []).map(function(u) {
                    return {
                        value: u.secure_code || u.id,
                        label: u.display_name || u.native_name || u.employee_id || u.id,
                    };
                });
            }
        },

        _renderPermTree(container, nodes, depth) {
            var self = this;
            for (var ni = 0; ni < nodes.length; ni++) {
                var node = nodes[ni];
                var hasChildren = node.children && node.children.length > 0;
                var isRoot = (depth === 0);
                var nodeEl = document.createElement('div');
                nodeEl.className = 'dc-perm-tree-node';

                var row = document.createElement('div');
                row.className = 'dc-perm-tree-row';
                if (isRoot) row.classList.add('dc-perm-tree-root');
                row.style.paddingLeft = (8 + depth * 16) + 'px';

                var toggle = document.createElement('span');
                toggle.className = 'dc-perm-tree-toggle';
                if (hasChildren) {
                    toggle.textContent = '\u25BC';
                    toggle.style.cursor = 'pointer';
                }
                row.appendChild(toggle);

                var label = document.createElement('span');
                label.className = 'dc-perm-tree-label';
                label.textContent = node.name;
                row.appendChild(label);

                nodeEl.appendChild(row);

                var childContainer = null;
                if (hasChildren) {
                    childContainer = document.createElement('div');
                    childContainer.className = 'dc-perm-tree-children';
                    childContainer.style.display = 'block';
                    this._renderPermTree(childContainer, node.children, depth + 1);
                    nodeEl.appendChild(childContainer);
                }

                if (hasChildren) {
                    (function(t, cc) {
                        t.addEventListener('click', function(e) {
                            e.stopPropagation();
                            var isOpen = cc.style.display !== 'none';
                            cc.style.display = isOpen ? 'none' : 'block';
                            t.textContent = isOpen ? '\u25B6' : '\u25BC';
                        });
                    })(toggle, childContainer);
                }

                var sc = node.secure_code || node.id;
                var nodeName = node.full_path || node.name;
                (function(r, s, n) {
                    r.addEventListener('click', function() {
                        var box = container.closest('.dc-perm-tree-box');
                        if (box) box.querySelectorAll('.dc-perm-tree-row.selected').forEach(function(el) { el.classList.remove('selected'); });
                        r.classList.add('selected');
                        self.newNodePerm.grant_target = s;
                        self.newNodePerm._selectedName = n;
                    });
                })(row, sc, nodeName);

                container.appendChild(nodeEl);
            }
        },

        async addNodePermRule() {
            if (!this.newNodePerm.grant_target || !this.selectedNode) return;
            this.permSaving = true;

            var targetName = this.newNodePerm._selectedName;
            if (!targetName) {
                var opt = this.permTargetOptions.find(function(o) { return o.value === this.newNodePerm.grant_target; }.bind(this));
                targetName = opt ? opt.label : this.newNodePerm.grant_target;
            }

            try {
                var res = await fetch(
                    window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code + '/permissions',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            grant_type: this.newNodePerm.grant_type,
                            grant_target: this.newNodePerm.grant_target,
                            grant_target_name: targetName,
                            include_children: this.newNodePerm.include_children,
                        }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    await this.loadNodePermissions(this.selectedNode.secure_code);
                    this.newNodePerm.grant_target = '';
                    this.newNodePerm._selectedName = '';
                    var treeBox = document.querySelector('.dc-perm-tree-box');
                    if (treeBox) treeBox.querySelectorAll('.dc-perm-tree-row.selected').forEach(function(el) { el.classList.remove('selected'); });
                    this.showToast(__('准入規則已新增'));
                } else {
                    this.showToast(data.error || data.message || __('新增失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('新增失敗: {msg}', {msg: e.message}), 'error');
            } finally {
                this.permSaving = false;
            }
        },

        async deleteNodePermRule(permSc) {
            if (!confirm(__('確定要刪除此准入規則?'))) return;
            try {
                var res = await fetch(
                    window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/permissions/' + permSc,
                    { method: 'DELETE' }
                );
                var data = await res.json();
                if (data.success) {
                    await this.loadNodePermissions(this.selectedNode.secure_code);
                    this.showToast(__('准入規則已刪除'));
                } else {
                    this.showToast(data.message || __('刪除失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('刪除失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        getPermTypeLabel(type) {
            if (type === 'department') return __('部門');
            if (type === 'group') return __('社群');
            if (type === 'user') return __('個人');
            return type;
        },

        getPermTypeCss(type) {
            if (type === 'department') return 'dept';
            if (type === 'group') return 'group';
            if (type === 'user') return 'user';
            return '';
        },

        // ===== 節點 CRUD =====

        openAddModal(parentSc) {
            this.addForm = {
                name: '', icon: '',
                page_layout_secure_code: '', parent_secure_code: parentSc || null,
            };
            this.showAddModal = true;
        },

        async doAddNode() {
            if (!this.addForm.name.trim()) {
                this.showToast(__('名稱不可為空'), 'error');
                return;
            }
            try {
                var body = {
                    name: this.addForm.name.trim(),
                    node_type: 'page',
                    icon: this.addForm.icon || null,
                    parent_secure_code: this.addForm.parent_secure_code || null,
                    page_layout_secure_code: this.addForm.page_layout_secure_code || null,
                };
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    this.showAddModal = false;
                    this.showToast(__('網頁已建立'), 'success');
                    await this.loadTree();
                } else {
                    this.showToast(data.error || __('建立失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('建立失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        async saveNode() {
            if (!this.selectedNode) return;
            if (!this.nodeForm.name.trim()) {
                this.showToast(__('名稱不可為空'), 'error');
                return;
            }
            try {
                var body = {
                    name: this.nodeForm.name.trim(),
                    icon: this.nodeForm.icon || null,
                    page_layout_secure_code: this.nodeForm.page_layout_secure_code || null,
                    is_active: this.nodeForm.is_active,
                    access_roles: this.nodeForm.access_roles,
                    redirect_to: this.nodeForm.redirect_to || window.__BP + '/dashboard',
                    crud_overrides: this.nodeForm.crud_overrides,
                    data_filters: this.nodeForm.data_filters,
                    permission_mode: this.nodeForm.permission_mode || null,
                    permission_policy_secure_code: this.nodeForm.permission_mode === 'policy'
                        ? (this.nodeForm.permission_policy_secure_code || null)
                        : null,
                };
                var res = await fetch(
                    window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast(__('網頁已更新'), 'success');
                    await this.loadTree();
                } else {
                    this.showToast(data.error || __('更新失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('更新失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        onPermModeChange() {
            if (this.nodeForm.permission_mode === 'custom' && this.selectedNode) {
                this.loadNodePermissions(this.selectedNode.secure_code);
            } else {
                this.nodePermissions = [];
            }
            if (this.nodeForm.permission_mode !== 'policy') {
                this.nodeForm.permission_policy_secure_code = '';
            }
        },

        async applyDown() {
            if (!this.selectedNode) return;
            if (!confirm(__('將此網頁的權限設定套用到所有子網頁?\n(已設定自訂權限的子網頁不受影響)'))) return;
            try {
                var res = await fetch(
                    window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code + '/apply-down',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ skip_custom: true }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || __('已套用'), 'success');
                    await this.loadTree();
                } else {
                    this.showToast(data.error || __('套用失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('套用失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        getPermModePolicyName() {
            var sc = this.nodeForm.permission_policy_secure_code;
            if (!sc) return '';
            var pg = this.permissionPolicies.find(function(p) { return p.secure_code === sc; });
            return pg ? pg.name : '';
        },

        async deleteNode() {
            if (!this.selectedNode) return;
            if (!confirm(__('確定要刪除此網頁（含所有子網頁）?'))) return;
            try {
                var res = await fetch(
                    window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code,
                    { method: 'DELETE' }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || __('網頁已刪除'), 'success');
                    this.selectedNode = null;
                    await this.loadTree();
                } else {
                    this.showToast(data.error || __('刪除失敗'), 'error');
                }
            } catch (e) {
                this.showToast(__('刪除失敗: {msg}', {msg: e.message}), 'error');
            }
        },

        // ===== 拖曳排序 =====

        async _saveReorder() {
            if (!this._wbTree) return;
            var nodes = [];
            this._wbTree.visit(function(node) {
                var parentKey = node.parent && node.parent.key !== '_root' ? node.parent.key : null;
                nodes.push({
                    secure_code: node.key,
                    parent_secure_code: parentKey,
                    display_order: node.getIndex(),
                });
            });

            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/reorder', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nodes: nodes }),
                });
                var data = await res.json();
                if (!data.success) {
                    this.showToast(data.error || __('排序失敗'), 'error');
                }
            } catch (e) {
                console.error('reorder:', e);
            }
        },

        // ===== CRUD Overrides (保留，Phase 3 移至 widget) =====

        getCrud(role, action) {
            var overrides = this.nodeForm.crud_overrides || {};
            var roleOverride = overrides[role];
            if (!roleOverride) {
                var adminRoles = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'];
                return adminRoles.indexOf(role) >= 0;
            }
            return roleOverride[action] || false;
        },

        setCrud(role, action, value) {
            if (!this.nodeForm.crud_overrides) this.nodeForm.crud_overrides = {};
            if (!this.nodeForm.crud_overrides[role]) {
                var adminRoles = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'];
                var isAdmin = adminRoles.indexOf(role) >= 0;
                this.nodeForm.crud_overrides[role] = {
                    create: isAdmin, edit: isAdmin, delete: isAdmin
                };
            }
            this.nodeForm.crud_overrides[role][action] = value;
        },

        // ===== Data Filters =====

        getFilters(role) {
            return (this.nodeForm.data_filters || {})[role] || {};
        },

        addFilter(role) {
            if (!this.nodeForm.data_filters) this.nodeForm.data_filters = {};
            if (!this.nodeForm.data_filters[role]) this.nodeForm.data_filters[role] = {};
            var key = 'column_' + Date.now();
            this.nodeForm.data_filters[role][key] = '';
        },

        removeFilter(role, col) {
            if (this.nodeForm.data_filters && this.nodeForm.data_filters[role]) {
                delete this.nodeForm.data_filters[role][col];
            }
        },

        renameFilter(role, oldCol, newCol) {
            if (!newCol || oldCol === newCol) return;
            if (this.nodeForm.data_filters && this.nodeForm.data_filters[role]) {
                var val = this.nodeForm.data_filters[role][oldCol];
                delete this.nodeForm.data_filters[role][oldCol];
                this.nodeForm.data_filters[role][newCol] = val;
            }
        },

        setFilterValue(role, col, value) {
            if (this.nodeForm.data_filters && this.nodeForm.data_filters[role]) {
                this.nodeForm.data_filters[role][col] = value;
            }
        },

        // ===== Toast =====

        showToast(message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function() { self.toast.show = false; }, 3000);
        },

        // ===== Icon Picker =====

        openIconPicker(target) {
            this._iconTarget = target;
            var currentIcon = target === 'add' ? this.addForm.icon : this.nodeForm.icon;
            this._ip_selectedIcon = currentIcon || '';
            this._ip_activeCategory = 'business';
            this._ip_search = '';
            this._ip_show = true;
        },

        ipOpen() {
            this._ip_show = true;
            this._ip_search = '';
        },

        ipClose() {
            this._ip_show = false;
        },

        ipSelect(iconClass) {
            this._ip_selectedIcon = iconClass;
            if (this._iconTarget === 'add') {
                this.addForm.icon = iconClass;
            } else {
                this.nodeForm.icon = iconClass;
            }
            this.ipClose();
        },

        ipClear() {
            this._ip_selectedIcon = '';
            if (this._iconTarget === 'add') {
                this.addForm.icon = '';
            } else {
                this.nodeForm.icon = '';
            }
            this.ipClose();
        },

        ipGetCategories() {
            return typeof ICON_CATEGORIES !== 'undefined' ? ICON_CATEGORIES : [];
        },

        ipGetIcons() {
            var cats = this.ipGetCategories();
            var active = this._ip_activeCategory;
            var cat = null;
            for (var i = 0; i < cats.length; i++) {
                if (cats[i].name === active) { cat = cats[i]; break; }
            }
            var icons = cat ? cat.icons : [];
            var search = (this._ip_search || '').trim().toLowerCase();
            if (!search) return icons;
            return icons.filter(function(ic) { return ic.toLowerCase().indexOf(search) >= 0; });
        },

        ipSetCategory(name) {
            this._ip_activeCategory = name;
        },
    };
}
