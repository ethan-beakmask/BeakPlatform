/* global Alpine, BeakTree, __ */
function wksManager(subSystemSc) {
    const BP = window.__BP || '';

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    function slugify(text) {
        return String(text || 'page')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .replace(/^[^a-z]+/, '') || 'page';
    }

    return {
        subSystemSc: subSystemSc || '',
        activeTab: 'design',
        subSystem: null,
        loading: true,
        tree: [],
        selectedNode: null,
        selectedNodeScs: [],
        portalOrgLoaded: false,
        portalGroups: [],
        portalLevels: [],
        accessForm: {
            groupMode: 'all',
            groupCodes: [],
            minLevel: 'GUEST',
        },
        currentPageSc: '',
        designerMounted: false,
        designerKey: 0,
        sortDirty: false,
        _bkTree: null,
        toast: { show: false, message: '' },

        async init() {
            await this.loadSubSystem();
            await this.loadTree();
            this.loading = false;
            this.$nextTick(() => this.initTree());
        },

        async loadSubSystem() {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}`);
                const data = await res.json();
                if (data.success) this.subSystem = data.data;
            } catch (err) {
                console.error('[Workspace] load sub system failed:', err);
            }
        },

        async loadTree() {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/site-map`);
                const data = await res.json();
                if (data.success) this.tree = data.data || [];
            } catch (err) {
                console.error('[Workspace] load site map failed:', err);
            }
        },

        initTree() {
            const wrap = document.querySelector('.wks-tree-wrap');
            if (!wrap) return;

            if (this._bkTree) {
                try { this._bkTree.destroy(); } catch (err) { /* ignore */ }
                this._bkTree = null;
            }

            const el = document.getElementById('wks-tree');
            if (!el) return;
            el.innerHTML = '';
            const source = this.treeToSource(this.tree);
            if (!source.length) return;

            this._bkTree = new BeakTree(el, {
                data: source,
                treeMode: 'lines-dom',
                draggable: true,
                hideHeader: true,
                onNodeClick: (nodeId, node, event) => this.onTreeNodeClick(nodeId, node, event),
                onNodeMoved: () => {
                    this.sortDirty = true;
                    this.saveReorder();
                },
            });
            this._bkTree.expandAll();
            this.markSelectedRow();
            this.markMultiSelectedRows();
        },

        treeToSource(nodes) {
            return (nodes || []).map((node) => ({
                id: node.secure_code,
                label: this.nodeLabel(node),
                data: clone(node),
                children: this.treeToSource(node.children || []),
            }));
        },

        nodeLabel(node) {
            const typeLabel = node.node_type === 'folder' ? __('資料夾') : __('網頁');
            const accessLabel = node.access_matrix ? ` ${__('〔准入〕')}` : '';
            return `[${typeLabel}] ${node.name}${accessLabel}`;
        },

        async onTreeNodeClick(nodeId, bkNode, event) {
            const nodeData = bkNode && bkNode.data ? bkNode.data : {};
            if (event && (event.ctrlKey || event.metaKey)) {
                this.toggleMultiSelect(nodeId);
                return;
            }
            this.selectedNodeScs = [];
            this.selectedNode = nodeData;
            this.markSelectedRow(nodeId);
            this.markMultiSelectedRows();
            this.syncAccessForm();

            if (nodeData.node_type === 'folder') {
                if (this.currentPageSc && this.designerIsDirty()) {
                    if (!confirm(__('尚未儲存，確定切換？'))) {
                        this.selectedNode = this.findNodeByPage(this.currentPageSc) || this.selectedNode;
                        this.markSelectedRow(this.selectedNode && this.selectedNode.secure_code);
                        this.syncAccessForm();
                        return;
                    }
                }
                this.currentPageSc = '';
                this.designerMounted = false;
                const target = event && event.target;
                const isNativeToggle = target && (
                    target.classList.contains('bt-toggle') || target.classList.contains('bt-td-tree')
                );
                if (this._bkTree && !isNativeToggle) this._bkTree.toggle(nodeId);
                return;
            }

            const pageSc = nodeData.page_layout_secure_code || '';
            if (!pageSc) {
                this.currentPageSc = '';
                this.designerMounted = false;
                this.showToast(__('此節點尚未連結頁面'));
                return;
            }
            await this.selectPage(nodeData, pageSc);
        },

        async selectPage(nodeData, pageSc) {
            if (this.currentPageSc && this.currentPageSc !== pageSc && this.designerIsDirty()) {
                if (!confirm(__('尚未儲存，確定切換？'))) {
                    this.selectedNode = this.findNodeByPage(this.currentPageSc) || this.selectedNode;
                    this.markSelectedRow(this.selectedNode && this.selectedNode.secure_code);
                    this.syncAccessForm();
                    return;
                }
            }

            this.selectedNode = nodeData;
            this.syncAccessForm();
            this.currentPageSc = pageSc;
            window.__IR_DESIGNER_CONFIG = {
                secureCode: pageSc,
                designerUrl: `${BP}/nocode/ir-designer/${pageSc}`,
                previewUrl: `${BP}/nocode/ir-designer/${pageSc}/preview`,
            };
            this.designerMounted = false;
            this.designerKey += 1;
            await this.$nextTick();
            this.designerMounted = true;
        },

        designerComponent() {
            const el = document.querySelector('.wks-designer-mount .ird-shell');
            if (!el || !window.Alpine || !Alpine.$data) return null;
            return Alpine.$data(el);
        },

        designerIsDirty() {
            const designer = this.designerComponent();
            if (!designer) return false;
            try {
                return !!designer.dirty || designer.snapshot() !== designer.savedSnapshot;
            } catch (err) {
                return !!designer.dirty;
            }
        },

        async addPage() {
            const name = prompt(__('請輸入網頁名稱'));
            if (!name || !name.trim()) return;
            const parentSc = this.selectedNode ? this.selectedNode.secure_code : null;
            const pageSc = await this.createPageLayout(name.trim());
            if (!pageSc) return;
            const node = await this.createNode({
                name: name.trim(),
                node_type: 'page',
                parent_secure_code: parentSc,
                page_layout_secure_code: pageSc,
            });
            if (!node) return;
            const mounted = await this.mountSubSystemPage(pageSc, name.trim());
            if (!mounted) return;
            await this.reloadTree();
            const freshNode = this.findNodeBySecureCode(node.secure_code) || node;
            await this.selectPage(freshNode, pageSc);
            this.markSelectedRow(freshNode.secure_code);
            this.showToast(__('網頁已建立'));
        },

        async addFolder() {
            const name = prompt(__('請輸入資料夾名稱'));
            if (!name || !name.trim()) return;
            const parentSc = this.selectedNode ? this.selectedNode.secure_code : null;
            const node = await this.createNode({
                name: name.trim(),
                node_type: 'folder',
                parent_secure_code: parentSc,
            });
            if (!node) return;
            await this.reloadTree();
            this.selectedNode = this.findNodeBySecureCode(node.secure_code) || node;
            this.markSelectedRow(node.secure_code);
            this.syncAccessForm();
            this.showToast(__('資料夾已建立'));
        },

        async createPageLayout(name) {
            const pageId = slugify(name).slice(0, 64);
            const payload = {
                name,
                layout_json: {
                    ir_version: 3,
                    page: {
                        id: pageId,
                        title_i18n: { 'zh-TW': name },
                        widgets: [],
                    },
                },
            };
            const res = await fetch(`${BP}/api/nocode-builder/pages`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok || !data.success) {
                this.showToast(data.error || __('建立頁面佈局失敗'));
                return '';
            }
            return data.data.secure_code;
        },

        async mountSubSystemPage(pageSc, name) {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/pages`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({
                        page_layout_secure_code: pageSc,
                        display_name: name,
                        visible_roles: ['*'],
                        is_active: true,
                    }),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('頁面掛載失敗'));
                    return false;
                }
                return true;
            } catch (err) {
                this.showToast(err.message || __('頁面掛載失敗'));
                return false;
            }
        },

        async createNode(payload) {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/site-map/nodes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify(payload),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('建立失敗'));
                    return null;
                }
                return data.data;
            } catch (err) {
                this.showToast(err.message || __('建立失敗'));
                return null;
            }
        },

        async deleteNode() {
            if (!this.selectedNode) return;
            if (!confirm(__('確定要刪除節點「{name}」嗎?', { name: this.selectedNode.name }))) return;
            try {
                const deletingSc = this.selectedNode.secure_code;
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/site-map/nodes/${deletingSc}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken() },
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('刪除失敗'));
                    return;
                }
                this.selectedNode = null;
                this.selectedNodeScs = [];
                this.currentPageSc = '';
                this.designerMounted = false;
                await this.reloadTree();
                this.showToast(__('節點已刪除'));
            } catch (err) {
                this.showToast(err.message || __('刪除失敗'));
            }
        },

        async saveReorder() {
            if (!this._bkTree) return;
            const ordered = [];
            const nodeMap = this._bkTree._nodeMap;
            const collectAll = (nodeId) => {
                const node = nodeMap.get(nodeId);
                if (!node) return;
                ordered.push({
                    secure_code: node.id,
                    parent_secure_code: node.parentId || null,
                    sort_order: ordered.length,
                });
                for (let i = 0; i < node.children.length; i += 1) {
                    collectAll(node.children[i].id);
                }
            };
            const roots = this._bkTree.getRootNodes();
            for (let i = 0; i < roots.length; i += 1) collectAll(roots[i].id);

            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/site-map/reorder`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({ nodes: ordered }),
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    this.sortDirty = false;
                    this.showToast(__('排序已儲存'));
                } else {
                    this.showToast(data.error || __('排序儲存失敗'));
                }
            } catch (err) {
                this.showToast(err.message || __('排序儲存失敗'));
            }
        },

        async reloadTree() {
            const selectedSc = this.selectedNode && this.selectedNode.secure_code;
            await this.loadTree();
            if (selectedSc) this.selectedNode = this.findNodeBySecureCode(selectedSc);
            this.selectedNodeScs = this.selectedNodeScs.filter((sc) => this.findNodeBySecureCode(sc));
            this.syncAccessForm();
            await this.$nextTick();
            this.initTree();
        },

        findNodeBySecureCode(secureCode, nodes) {
            for (const node of (nodes || this.tree || [])) {
                if (node.secure_code === secureCode) return node;
                const found = this.findNodeBySecureCode(secureCode, node.children || []);
                if (found) return found;
            }
            return null;
        },

        findNodeByPage(pageSc, nodes) {
            for (const node of (nodes || this.tree || [])) {
                if (node.page_layout_secure_code === pageSc) return node;
                const found = this.findNodeByPage(pageSc, node.children || []);
                if (found) return found;
            }
            return null;
        },

        markSelectedRow(nodeId) {
            const selectedId = nodeId || (this.selectedNode && this.selectedNode.secure_code);
            document.querySelectorAll('#wks-tree .wks-tree-selected').forEach((el) => {
                el.classList.remove('wks-tree-selected');
            });
            if (!selectedId) return;
            const row = document.querySelector(`#wks-tree tr[data-id="${selectedId}"]`);
            if (row) row.classList.add('wks-tree-selected');
        },

        markMultiSelectedRows() {
            document.querySelectorAll('#wks-tree .wks-tree-multiselected').forEach((el) => {
                el.classList.remove('wks-tree-multiselected');
            });
            this.selectedNodeScs.forEach((sc) => {
                const row = document.querySelector(`#wks-tree tr[data-id="${sc}"]`);
                if (row) row.classList.add('wks-tree-multiselected');
            });
        },

        toggleMultiSelect(nodeSc) {
            if (!nodeSc) return;
            if (this.selectedNodeScs.includes(nodeSc)) {
                this.selectedNodeScs = this.selectedNodeScs.filter((sc) => sc !== nodeSc);
            } else {
                this.selectedNodeScs = [...this.selectedNodeScs, nodeSc];
            }
            this.markMultiSelectedRows();
            this.syncAccessForm();
        },

        accessTargetNodeScs() {
            if (this.selectedNodeScs.length) return this.selectedNodeScs;
            return this.selectedNode ? [this.selectedNode.secure_code] : [];
        },

        selectedAccessCount() {
            return this.accessTargetNodeScs().length;
        },

        async ensurePortalOrg() {
            if (this.portalOrgLoaded) return;
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/portal/org`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('載入群組階級失敗'));
                    return;
                }
                const orgData = data.data || {};
                this.portalGroups = orgData.groups || [];
                this.portalLevels = orgData.levels || [];
                this.portalOrgLoaded = true;
                this.syncAccessForm();
            } catch (err) {
                this.showToast(err.message || __('載入群組階級失敗'));
            }
        },

        activePortalGroups() {
            return (this.portalGroups || []).filter((group) => group && group.code && group.is_active !== false);
        },

        sortedPortalLevels() {
            return [...(this.portalLevels || [])]
                .filter((level) => level && level.code && level.is_active !== false)
                .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
        },

        syncAccessForm() {
            const targets = this.accessTargetNodeScs();
            if (targets.length !== 1) {
                this.accessForm = { groupMode: 'all', groupCodes: [], minLevel: this.defaultMinLevel() };
                return;
            }
            const node = this.findNodeBySecureCode(targets[0]) || this.selectedNode;
            const matrix = node && node.access_matrix && node.access_matrix.read ? node.access_matrix.read : null;
            if (!matrix) {
                this.accessForm = { groupMode: 'all', groupCodes: [], minLevel: this.defaultMinLevel() };
                return;
            }
            const groups = Array.isArray(matrix.groups) ? matrix.groups : [];
            this.accessForm = {
                groupMode: matrix.groups === null ? 'all' : 'limited',
                groupCodes: groups,
                minLevel: matrix.min_level || this.defaultMinLevel(),
            };
        },

        defaultMinLevel() {
            if (this.sortedPortalLevels().some((level) => level.code === 'GUEST')) return 'GUEST';
            const first = this.sortedPortalLevels()[0];
            return first ? first.code : 'GUEST';
        },

        buildAccessMatrix() {
            return {
                read: {
                    groups: this.accessForm.groupMode === 'all' ? null : this.accessForm.groupCodes,
                    min_level: this.accessForm.minLevel || this.defaultMinLevel(),
                },
            };
        },

        async applyAccessMatrix() {
            const targets = this.accessTargetNodeScs();
            if (!targets.length) return;
            const matrix = this.buildAccessMatrix();
            if (matrix.read.groups !== null && !matrix.read.groups.length) {
                this.showToast(__('請至少選擇一個群組'));
                return;
            }
            await this.saveAccessMatrixBatch(targets, matrix, __('節點准入已套用'));
        },

        async clearAccessMatrix() {
            const targets = this.accessTargetNodeScs();
            if (!targets.length) return;
            await this.saveAccessMatrixBatch(targets, null, __('節點准入已清除'));
        },

        async saveAccessMatrixBatch(nodeScs, accessMatrix, message) {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${this.subSystemSc}/site-map/access-matrix/batch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({
                        node_secure_codes: nodeScs,
                        access_matrix: accessMatrix,
                    }),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('儲存節點准入失敗'));
                    return;
                }
                await this.reloadTree();
                this.showToast(message);
            } catch (err) {
                this.showToast(err.message || __('儲存節點准入失敗'));
            }
        },

        showToast(message) {
            this.toast = { show: true, message };
            setTimeout(() => { this.toast.show = false; }, 2600);
        },
    };
}
