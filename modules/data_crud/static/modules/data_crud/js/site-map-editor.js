/**
 * site-map-editor.js -- 網站地圖編輯器
 * Alpine.js component: Wunderbaum 樹 + 節點屬性面板 + 權限白名單
 */
function siteMapEditor(subSystemSc) {
    return {
        loading: true,
        tree: [],
        _wbTree: null,
        selectedNode: null,
        availableLayouts: [],

        // 節點屬性表單
        nodeForm: {
            name: '', icon: '', node_type: 'page',
            page_layout_secure_code: '', is_active: true,
            crud_overrides: {}, data_filters: {},
        },

        // 權限面板
        permissions: [],
        permLoading: false,
        addPermForm: { target_type: 'ROLE', target_secure_code: '' },
        permTargets: [],
        permTargetLoading: false,

        // 新增節點 Modal
        showAddModal: false,
        addForm: {
            name: '', node_type: 'page', icon: '',
            page_layout_secure_code: '', parent_secure_code: null,
        },

        toast: { show: false, message: '', type: 'success' },

        async init() {
            await Promise.all([
                this.loadTree(),
                this.loadLayouts(),
            ]);
            this.loading = false;
        },

        // ===== 資料載入 =====

        async loadTree() {
            try {
                var res = await fetch('/api/data-crud/sub-systems/' + subSystemSc + '/site-map');
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
                var res = await fetch('/api/data-crud/pages');
                var data = await res.json();
                if (data.success) {
                    this.availableLayouts = data.data || [];
                }
            } catch (e) {
                console.error('loadLayouts:', e);
            }
        },

        // ===== Wunderbaum 樹 =====

        _treeToSource(nodes) {
            var self = this;
            return nodes.map(function(n) {
                var icon = n.node_type === 'folder' ? 'bi bi-folder' : 'bi bi-file-earmark';
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
                node_type: d.node_type || 'page',
                page_layout_secure_code: d.page_layout_secure_code || '',
                is_active: d.is_active !== false,
                crud_overrides: JSON.parse(JSON.stringify(d.crud_overrides || {})),
                data_filters: JSON.parse(JSON.stringify(d.data_filters || {})),
            };
            this.loadPermissions(d.secure_code);
        },

        // ===== 節點 CRUD =====

        openAddModal(parentSc) {
            this.addForm = {
                name: '', node_type: 'page', icon: '',
                page_layout_secure_code: '', parent_secure_code: parentSc || null,
            };
            this.showAddModal = true;
        },

        async doAddNode() {
            if (!this.addForm.name.trim()) {
                this.showToast('名稱不可為空', 'error');
                return;
            }
            try {
                var body = {
                    name: this.addForm.name.trim(),
                    node_type: this.addForm.node_type,
                    icon: this.addForm.icon || null,
                    parent_secure_code: this.addForm.parent_secure_code || null,
                    page_layout_secure_code: this.addForm.page_layout_secure_code || null,
                };
                var res = await fetch('/api/data-crud/sub-systems/' + subSystemSc + '/site-map/nodes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    this.showAddModal = false;
                    this.showToast('節點已建立', 'success');
                    await this.loadTree();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
        },

        async saveNode() {
            if (!this.selectedNode) return;
            if (!this.nodeForm.name.trim()) {
                this.showToast('名稱不可為空', 'error');
                return;
            }
            try {
                var body = {
                    name: this.nodeForm.name.trim(),
                    icon: this.nodeForm.icon || null,
                    page_layout_secure_code: this.nodeForm.page_layout_secure_code || null,
                    is_active: this.nodeForm.is_active,
                    crud_overrides: this.nodeForm.crud_overrides,
                    data_filters: this.nodeForm.data_filters,
                };
                var res = await fetch(
                    '/api/data-crud/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast('節點已更新', 'success');
                    await this.loadTree();
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
            }
        },

        async deleteNode() {
            if (!this.selectedNode) return;
            if (!confirm('確定要刪除此節點（含所有子節點）?')) return;
            try {
                var res = await fetch(
                    '/api/data-crud/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code,
                    { method: 'DELETE' }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '節點已刪除', 'success');
                    this.selectedNode = null;
                    await this.loadTree();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
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
                var res = await fetch('/api/data-crud/sub-systems/' + subSystemSc + '/site-map/reorder', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ nodes: nodes }),
                });
                var data = await res.json();
                if (!data.success) {
                    this.showToast(data.error || '排序失敗', 'error');
                }
            } catch (e) {
                console.error('reorder:', e);
            }
        },

        // ===== 權限管理 =====

        async loadPermissions(nodeSc) {
            this.permLoading = true;
            this.permissions = [];
            try {
                var res = await fetch(
                    '/api/data-crud/sub-systems/' + subSystemSc + '/site-map/nodes/' + nodeSc + '/permissions'
                );
                var data = await res.json();
                if (data.success) {
                    this.permissions = data.data || [];
                }
            } catch (e) {
                console.error('loadPermissions:', e);
            }
            this.permLoading = false;
        },

        async onPermTargetTypeChange() {
            this.addPermForm.target_secure_code = '';
            this.permTargets = [];
            if (!this.addPermForm.target_type) return;

            this.permTargetLoading = true;
            try {
                var res = await fetch(
                    '/api/module-access/targets?type=' + this.addPermForm.target_type
                );
                var data = await res.json();
                if (data.success) {
                    this.permTargets = data.data || [];
                }
            } catch (e) {
                console.error('loadTargets:', e);
            }
            this.permTargetLoading = false;
        },

        async addPermission() {
            if (!this.selectedNode) return;
            if (!this.addPermForm.target_secure_code) {
                this.showToast('請選擇對象', 'error');
                return;
            }
            try {
                var res = await fetch(
                    '/api/data-crud/sub-systems/' + subSystemSc + '/site-map/nodes/' + this.selectedNode.secure_code + '/permissions',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            target_type: this.addPermForm.target_type,
                            target_secure_code: this.addPermForm.target_secure_code,
                        }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast('權限已新增', 'success');
                    this.addPermForm.target_secure_code = '';
                    await this.loadPermissions(this.selectedNode.secure_code);
                } else {
                    this.showToast(data.error || '新增失敗', 'error');
                }
            } catch (e) {
                this.showToast('新增失敗: ' + e.message, 'error');
            }
        },

        async removePermission(permSc) {
            if (!confirm('確定要移除此權限?')) return;
            try {
                var res = await fetch(
                    '/api/data-crud/sub-systems/' + subSystemSc + '/site-map/permissions/' + permSc,
                    { method: 'DELETE' }
                );
                var data = await res.json();
                if (data.success) {
                    this.showToast('權限已刪除', 'success');
                    if (this.selectedNode) {
                        await this.loadPermissions(this.selectedNode.secure_code);
                    }
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // ===== CRUD Overrides (簡化版) =====

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

        // ===== Target Type 翻譯 =====

        targetTypeLabel(type) {
            var map = { 'ROLE': '角色', 'DEPARTMENT': '部門', 'GROUP': '群組', 'ACCOUNT': '帳號' };
            return map[type] || type;
        },

        // ===== Toast =====

        showToast(message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function() { self.toast.show = false; }, 3000);
        },
    };
}
