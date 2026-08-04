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
        currentPageSc: '',
        designerMounted: false,
        designerKey: 0,
        sortDirty: false,
        _bkTree: null,
        toast: { show: false, message: '' },
        templateModal: {
            open: false,
            loading: false,
            saving: false,
            error: '',
            pageName: '',
            selectedSc: '',
            templates: [],
            reportLines: [],
            showHidden: false,
            busySc: '',
        },

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

        // folder 節點已於 a6e0314e（2026-04-07）廢除，後端 create_node 只收 page，
        // 新增入口也已移除；DB 仍有 3 筆歷史 folder 節點，以下讀取側分支只為相容它們，
        // 不可因為「看起來沒人用」就刪掉（刪了點到舊節點會壞）。
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

            if (nodeData.node_type === 'folder') {
                if (this.currentPageSc && this.designerIsDirty()) {
                    if (!confirm(__('尚未儲存，確定切換？'))) {
                        this.selectedNode = this.findNodeByPage(this.currentPageSc) || this.selectedNode;
                        this.markSelectedRow(this.selectedNode && this.selectedNode.secure_code);
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
                    return;
                }
            }

            this.selectedNode = nodeData;
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
            const pageSc = await this.createPageLayout(name.trim());
            if (!pageSc) return;
            await this.finishPageCreation(pageSc, name.trim());
        },

        // 回傳 true 才代表整條鏈（節點 + 掛載）都成功。
        // 任一步失敗就把剛建好的頁面佈局收回去，不要留下沒有節點的孤兒頁，
        // 呼叫端也才不會在失敗後還顯示「網頁已建立」。
        async finishPageCreation(pageSc, name, showSuccessToast = true) {
            const parentSc = this.selectedNode ? this.selectedNode.secure_code : null;
            const node = await this.createNode({
                name: name.trim(),
                node_type: 'page',
                parent_secure_code: parentSc,
                page_layout_secure_code: pageSc,
            });
            if (!node) {
                await this.discardPageLayout(pageSc);
                return false;
            }
            const mounted = await this.mountSubSystemPage(pageSc, name.trim());
            if (!mounted) return false;
            await this.reloadTree();
            const freshNode = this.findNodeBySecureCode(node.secure_code) || node;
            await this.selectPage(freshNode, pageSc);
            this.markSelectedRow(freshNode.secure_code);
            if (showSuccessToast) this.showToast(__('網頁已建立'));
            return true;
        },

        async discardPageLayout(pageSc) {
            try {
                await fetch(`${BP}/api/nocode-builder/pages/${pageSc}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken() },
                });
            } catch (err) {
                console.warn('discardPageLayout failed', err);
            }
        },

        async openTemplateModal() {
            this.templateModal = {
                open: true,
                loading: true,
                saving: false,
                error: '',
                pageName: '',
                selectedSc: '',
                templates: [],
                reportLines: [],
                showHidden: false,
                busySc: '',
            };
            await this.reloadTemplates();
        },

        async reloadTemplates() {
            const previousSc = this.templateModal.selectedSc;
            this.templateModal.loading = true;
            this.templateModal.error = '';
            try {
                const items = await window.BkPageTemplate.fetchTemplates(this.subSystemSc, this.templateModal.showHidden);
                const templates = (items || []).filter((item) => window.BkPageTemplate.isSupported(item.layout_json));
                this.templateModal.templates = templates;
                const previous = templates.find((item) => item.secure_code === previousSc && !item.is_hidden);
                const firstAvailable = templates.find((item) => !item.is_hidden);
                this.templateModal.selectedSc = previous ? previous.secure_code : (firstAvailable ? firstAvailable.secure_code : '');
            } catch (err) {
                this.templateModal.error = err.message || __('載入樣板失敗');
            } finally {
                this.templateModal.loading = false;
                this.templateModal.busySc = '';
            }
        },

        closeTemplateModal() {
            this.templateModal.open = false;
            this.templateModal.saving = false;
        },

        templateGroups() {
            const grouped = new Map();
            for (const item of this.templateModal.templates || []) {
                const category = item.category || __('未分類');
                if (!grouped.has(category)) grouped.set(category, []);
                grouped.get(category).push(item);
            }
            return Array.from(grouped.entries()).map(([category, items]) => ({ category, items }));
        },

        selectedTemplate() {
            return (this.templateModal.templates || []).find((item) => item.secure_code === this.templateModal.selectedSc) || null;
        },

        canManageTemplates() {
            return window.BkCaps ? window.BkCaps.can('nocode_builder.manage') : false;
        },

        async toggleShowHiddenTemplates() {
            await this.reloadTemplates();
        },

        selectTemplateItem(item) {
            if (!item || item.is_hidden) return;
            this.templateModal.selectedSc = item.secure_code;
        },

        async hideTemplateItem(item) {
            if (!item || this.templateModal.busySc) return;
            this.templateModal.busySc = item.secure_code;
            this.templateModal.error = '';
            try {
                await window.BkPageTemplate.hideTemplate(this.subSystemSc, item.secure_code);
                await this.reloadTemplates();
                this.showToast(__('已隱藏此樣板'));
            } catch (err) {
                this.templateModal.error = err.message || __('隱藏樣板失敗');
                this.templateModal.busySc = '';
            }
        },

        async unhideTemplateItem(item) {
            if (!item || this.templateModal.busySc) return;
            this.templateModal.busySc = item.secure_code;
            this.templateModal.error = '';
            try {
                await window.BkPageTemplate.unhideTemplate(this.subSystemSc, item.secure_code);
                await this.reloadTemplates();
                this.showToast(__('已取消隱藏'));
            } catch (err) {
                this.templateModal.error = err.message || __('取消隱藏失敗');
                this.templateModal.busySc = '';
            }
        },

        templateScopeLabel(scope) {
            if (scope === 'system') return __('內建');
            if (scope === 'org') return __('企業');
            if (scope === 'sub_system') return __('本子系統');
            return scope || '';
        },

        templateThumbnailSrc(item) {
            if (!item) return '';
            const svg = item.thumbnail_svg || window.BkPageTemplate.buildThumbnailSvg(item.layout_json || {});
            return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
        },

        async createPageFromTemplate() {
            const template = this.selectedTemplate();
            const name = (this.templateModal.pageName || '').trim();
            if (!template) {
                this.templateModal.error = __('請選擇樣板');
                return;
            }
            if (template.is_hidden) {
                this.templateModal.error = __('請選擇樣板');
                return;
            }
            if (!name) {
                this.templateModal.error = __('請輸入網頁名稱');
                return;
            }
            this.templateModal.saving = true;
            this.templateModal.error = '';
            this.templateModal.reportLines = [];
            try {
                const res = await fetch(`${BP}/api/nocode-builder/templates/${template.secure_code}/instantiate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({
                        name,
                        sub_system_secure_code: this.subSystemSc,
                    }),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.templateModal.error = data.error || __('建立失敗');
                    return;
                }
                const pageSc = data.data && data.data.page ? data.data.page.secure_code : '';
                if (!pageSc) {
                    this.templateModal.error = __('建立失敗');
                    return;
                }
                const created = await this.finishPageCreation(pageSc, name, false);
                if (!created) {
                    // createNode / mountSubSystemPage 已經各自 toast 過原因，
                    // 但 modal 蓋在上面，所以再寫一次到 modal 裡並保持開啟。
                    this.templateModal.error = __('網頁建立失敗，請確認是否已在左側選取父節點');
                    return;
                }
                const report = window.BkPageTemplate.describeReport(data.data.report || {});
                if (report.hasIssue) {
                    this.templateModal.reportLines = report.lines;
                    return;
                }
                this.showToast(__('網頁已建立'));
                this.closeTemplateModal();
            } catch (err) {
                this.templateModal.error = err.message || __('建立失敗');
            } finally {
                this.templateModal.saving = false;
            }
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
        },

        showToast(message) {
            this.toast = { show: true, message };
            setTimeout(() => { this.toast.show = false; }, 2600);
        },
    };
}
