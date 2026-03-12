/**
 * Studio 設計器 - 統一設計器 Alpine.js Manager
 *
 * 佈局: 左側(元件庫+Site Map樹) + 中央(設計區) + 右側(屬性面板)
 *
 * 支援兩種佈局模式:
 *   - grid: Grid 宮格 (GridLayoutEditor)
 *   - free: GridStack 自由 (lab-designer.js 邏輯)
 */
function studioManager() {
    const config = window.__STUDIO_CONFIG || {};

    return {
        // 子系統資料
        subSystemSc: config.subSystemSc || '',
        subSystem: null,
        layoutMode: 'grid',   // grid | free
        loading: true,

        // Site Map 樹
        tree: [],
        _wbTree: null,
        selectedNode: null,    // 當前選中的節點

        // 頁面佈局
        currentPageSc: null,   // 當前載入的 page layout secure_code
        dirty: false,          // 有未儲存變更

        // Grid 宮格編輯器
        _gridEditor: null,

        // GridStack 自由模式
        _gsGrid: null,
        _gsWidgets: {},        // id -> DataListWidget
        _gsWidgetConfigs: {},  // id -> config

        // 屬性面板
        showProps: false,
        propsMode: 'node',     // node | widget
        // widget 設定
        selectedZoneId: null,
        settingViewCode: '',
        settingTitle: '',
        settingPageSize: 10,
        settingShowSearch: true,
        settingShowPagination: true,
        settingAllowCreate: false,
        settingAllowEdit: false,
        settingAllowDelete: false,
        settingContextOutputs: [],
        settingContextInputs: [],

        // Views (可用的資料表)
        availableViews: [],

        // Node 表單
        nodeForm: {
            name: '',
            icon: '',
            node_type: 'page',
            page_layout_secure_code: '',
        },
        showAddNodeModal: false,
        addNodeForm: { name: '', node_type: 'page', parent_sc: '' },

        // 頁面清單 (for node linking)
        pageList: [],

        toast: { show: false, message: '', type: 'success' },

        // ===== 初始化 =====

        async init() {
            await this._loadSubSystem();
            if (!this.subSystem) {
                this.loading = false;
                return;
            }
            this.layoutMode = this.subSystem.layout_mode || 'grid';

            await Promise.all([
                this._loadTree(),
                this._loadViews(),
                this._loadPages(),
            ]);

            this.loading = false;

            // 等 DOM 完成渲染後初始化樹
            this.$nextTick(() => {
                this._initSiteMapTree();
            });
        },

        /** 輪詢等待 DOM 元素出現 */
        _waitForEl(id, cb) {
            const check = () => {
                const el = document.getElementById(id);
                if (el) { cb(el); }
                else { requestAnimationFrame(check); }
            };
            requestAnimationFrame(check);
        },

        // ===== 資料載入 =====

        async _loadSubSystem() {
            try {
                const res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc);
                const data = await res.json();
                if (data.success) {
                    this.subSystem = data.data;
                }
            } catch (e) {
                console.error('Load sub system failed:', e);
            }
        },

        async _loadTree() {
            try {
                const res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map');
                const data = await res.json();
                if (data.success) {
                    this.tree = data.data || [];
                }
            } catch (e) {
                console.error('Load tree failed:', e);
            }
        },

        async _loadViews() {
            try {
                const res = await fetch('/api/nocode-builder/views');
                const data = await res.json();
                if (data.success) {
                    this.availableViews = data.data || [];
                }
            } catch (e) {
                console.error('Load views failed:', e);
            }
        },

        async _loadPages() {
            try {
                const res = await fetch('/api/nocode-builder/pages');
                const data = await res.json();
                if (data.success) {
                    this.pageList = data.data || [];
                }
            } catch (e) {
                console.error('Load pages failed:', e);
            }
        },

        // ===== Site Map 樹 =====

        _initSiteMapTree() {
            const wrap = document.querySelector('.stu-tree-wrap');
            if (!wrap) return;

            const source = this._treeToSource(this.tree);

            // 銷毀舊樹
            if (this._wbTree) {
                try { this._wbTree.destroy(); } catch (e) { /* ignore */ }
                this._wbTree = null;
            }

            // 移除舊的 #stu-tree，建立全新 div 避免 Wunderbaum destroy 殘留問題
            let el = document.getElementById('stu-tree');
            if (el) el.remove();
            el = document.createElement('div');
            el.id = 'stu-tree';
            wrap.prepend(el);

            this._wbTree = new mar10.Wunderbaum({
                element: el,
                source: source,
                selectMode: 'single',
                activate: (e) => {
                    if (e.node) {
                        this._onTreeNodeActivate(e.node);
                    }
                },
                dnd: {
                    effectAllowed: 'move',
                    dragStart: (e) => {
                        e.event.dataTransfer.effectAllowed = 'move';
                        return true;
                    },
                    dragEnter: (e) => { return true; },
                    drop: (e) => {
                        const src = e.sourceNode;
                        const tgt = e.node;
                        if (!src || !tgt) return;
                        e.sourceNode.moveTo(tgt, e.suggestedDropMode);
                        this._saveReorder();
                    },
                },
            });
        },

        _treeToSource(nodes) {
            if (!nodes || nodes.length === 0) return [];
            return nodes.map(n => ({
                title: (n.icon ? n.icon + ' ' : '') + n.name,
                key: n.secure_code,
                expanded: true,
                // Wunderbaum 會合併 source 屬性到 node，不能用 data: n
                // 用 refRaw 保存原始資料，避免被 Wunderbaum 覆蓋
                refRaw: JSON.parse(JSON.stringify(n)),
                children: this._treeToSource(n.children || []),
                icon: false,
            }));
        },

        _onTreeNodeActivate(wbNode) {
            // Wunderbaum 把 source 屬性存入 node.data
            const nodeData = (wbNode.data && wbNode.data.refRaw) || wbNode.data || {};
            this._onTreeNodeSelect(nodeData);
        },

        _onTreeNodeSelect(nodeData) {
            this.selectedNode = nodeData;
            this.nodeForm.name = nodeData.name || '';
            this.nodeForm.icon = nodeData.icon || '';
            this.nodeForm.node_type = nodeData.node_type || 'page';

            // 如果是 page 類型且有 page_layout，載入佈局
            if (nodeData.node_type === 'page') {
                const pageSc = nodeData.page_layout_secure_code;
                if (pageSc) {
                    this._waitForEl('stu-grid-canvas', () => {
                        this._ensureEditor();
                        this._loadPageLayout(pageSc);
                    });
                } else {
                    // 無頁面佈局，清空設計區
                    this.currentPageSc = null;
                    this._waitForEl('stu-grid-canvas', () => {
                        this._ensureEditor();
                        this._clearCanvas();
                    });
                }
            } else {
                // folder 類型不顯示佈局
                this.currentPageSc = null;
                this._clearCanvas();
            }

            this.showProps = false;
            this.selectedZoneId = null;
        },

        async _loadPageLayout(pageSc) {
            try {
                const res = await fetch('/api/nocode-builder/pages/' + pageSc);
                const data = await res.json();
                if (data.success) {
                    this.currentPageSc = pageSc;
                    const layout = data.data.layout_json || {};

                    if (this.layoutMode === 'grid') {
                        if (this._gridEditor) {
                            this._gridEditor.loadLayout(
                                layout.version === 3 ? layout : this._emptyGridLayout()
                            );
                        }
                    } else {
                        this._loadGridStackLayout(layout);
                    }
                    this.dirty = false;
                }
            } catch (e) {
                console.error('Load page layout failed:', e);
            }
        },

        _emptyGridLayout() {
            return { version: 3, mode: 'grid', gridSize: [4, 4], zones: [], widgets: [] };
        },

        _clearCanvas() {
            if (this.layoutMode === 'grid' && this._gridEditor) {
                this._gridEditor.loadLayout(this._emptyGridLayout());
            } else if (this._gsGrid) {
                this._gsGrid.removeAll();
                this._gsWidgets = {};
                this._gsWidgetConfigs = {};
            }
        },

        // ===== 樹操作 =====

        openAddNode() {
            this.addNodeForm = {
                name: '',
                node_type: 'page',
                parent_sc: this.selectedNode ? this.selectedNode.secure_code : '',
            };
            this.showAddNodeModal = true;
        },

        async doAddNode() {
            const name = this.addNodeForm.name.trim();
            if (!name) { this.showToast('名稱為必填', 'error'); return; }

            try {
                const body = {
                    name: name,
                    node_type: this.addNodeForm.node_type,
                    parent_secure_code: this.addNodeForm.parent_sc || null,
                };

                // 如果是 page 類型，自動建立 page layout
                if (this.addNodeForm.node_type === 'page') {
                    const pageRes = await fetch('/api/nocode-builder/pages', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: name,
                            layout_json: this.layoutMode === 'grid'
                                ? { version: 3, mode: 'grid', gridSize: [4, 4], zones: [], widgets: [] }
                                : { version: 2, widgets: [] },
                        }),
                    });
                    const pageData = await pageRes.json();
                    if (pageData.success) {
                        body.page_layout_secure_code = pageData.data.secure_code;
                    }
                }

                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map/nodes',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.showAddNodeModal = false;
                    this.showToast('節點已建立', 'success');
                    await this._loadTree();
                    await this._loadPages();
                    this._initSiteMapTree();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
        },

        async deleteNode() {
            if (!this.selectedNode) return;
            if (!confirm('確定要刪除節點「' + this.selectedNode.name + '」嗎?')) return;

            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + this.selectedNode.secure_code,
                    { method: 'DELETE' }
                );
                const data = await res.json();
                if (data.success) {
                    this.selectedNode = null;
                    this.currentPageSc = null;
                    this._clearCanvas();
                    this.showToast('節點已刪除', 'success');
                    await this._loadTree();
                    this._initSiteMapTree();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
            }
        },

        async saveNodeName() {
            if (!this.selectedNode) return;
            const name = this.nodeForm.name.trim();
            if (!name) return;

            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + this.selectedNode.secure_code,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: name,
                            icon: this.nodeForm.icon,
                        }),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.selectedNode.name = name;
                    this.selectedNode.icon = this.nodeForm.icon;
                    this.showToast('已儲存', 'success');
                    await this._loadTree();
                    this._initSiteMapTree();
                }
            } catch (e) {
                this.showToast('儲存失敗', 'error');
            }
        },

        async _saveReorder() {
            if (!this._wbTree) return;
            const ordered = [];
            this._wbTree.visit((node) => {
                ordered.push({
                    secure_code: node.key,
                    parent_secure_code: node.parent && !node.parent.isRootNode()
                        ? node.parent.key : null,
                    sort_order: ordered.length,
                });
            });

            try {
                await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map/reorder',
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ nodes: ordered }),
                    }
                );
            } catch (e) {
                console.error('Reorder failed:', e);
            }
        },

        // ===== 編輯器延遲初始化 =====

        _ensureEditor() {
            if (this.layoutMode === 'grid') {
                this._initGridEditor();
            } else {
                this._initGridStackEditor();
            }
        },

        // ===== Grid 宮格編輯器 =====

        _initGridEditor() {
            const el = document.getElementById('stu-grid-canvas');
            if (!el) return;

            // Destroy old editor if re-initializing
            if (this._gridEditor) {
                this._gridEditor = null;
            }
            el.innerHTML = '';

            this._gridEditor = new GridLayoutEditor(el, {
                rows: 4, cols: 4,
            });

            this._gridEditor.onZoneSelect = (zoneId) => {
                this.selectedZoneId = zoneId;
                this.showProps = false;
                this.propsMode = 'node';
            };

            this._gridEditor.onWidgetSelect = (zoneId, widgetConfig) => {
                this.selectedZoneId = zoneId;
                this._populateWidgetSettings(widgetConfig);
                this.showProps = true;
                this.propsMode = 'widget';
            };

            this._gridEditor.onChanged = () => {
                this.dirty = true;
            };
        },

        onComponentDragStart(e, type) {
            e.dataTransfer.setData('text/plain', type);
            e.dataTransfer.effectAllowed = 'copy';
        },

        onComponentClick(type) {
            // 點擊元件庫：如果有選中空 zone，直接放入
            if (this.layoutMode === 'grid' && this._gridEditor) {
                this._gridEditor.addWidgetToSelected(type);
            } else if (this.layoutMode === 'free') {
                this._gsAddWidget(type);
            }
        },

        // ===== GridStack 自由模式 =====

        _initGridStackEditor() {
            const el = document.querySelector('.stu-canvas .grid-stack');
            if (!el) return;

            this._gsGrid = GridStack.init({
                column: 12,
                cellHeight: 60,
                margin: 8,
                float: true,
                removable: false,
                acceptWidgets: true,
            }, el);

            this._gsGrid.on('change', () => { this.dirty = true; });
            this._gsGrid.on('click', (e) => {
                const itemEl = e.target.closest('.grid-stack-item');
                if (itemEl) {
                    const wid = itemEl.getAttribute('gs-id');
                    if (wid && this._gsWidgetConfigs[wid]) {
                        this._populateWidgetSettings(this._gsWidgetConfigs[wid]);
                        this.selectedZoneId = wid;
                        this.showProps = true;
                        this.propsMode = 'widget';
                    }
                }
            });
        },

        _gsAddWidget(type) {
            if (!this._gsGrid) return;
            const wid = 'w_' + Math.random().toString(36).slice(2, 8);
            const config = {
                id: wid,
                type: type,
                viewCode: '',
                title: '',
                pageSize: 10,
                showSearch: true,
                showPagination: true,
                allowCreate: false,
                allowEdit: false,
                allowDelete: false,
                contextOutputs: [],
                contextInputs: [],
            };
            this._gsWidgetConfigs[wid] = config;

            const contentEl = document.createElement('div');
            contentEl.innerHTML = '<div class="dlw-root" style="padding:8px;"><b>' + type + '</b><br><span style="color:#999;">(未設定)</span></div>';

            this._gsGrid.addWidget({
                x: 0, y: 0, w: 6, h: 4,
                id: wid,
                content: contentEl.innerHTML,
            });

            this.dirty = true;
        },

        _loadGridStackLayout(layout) {
            if (!this._gsGrid) {
                setTimeout(() => {
                    this._initGridStackEditor();
                    this._loadGridStackLayout(layout);
                }, 50);
                return;
            }

            this._gsGrid.removeAll();
            this._gsWidgets = {};
            this._gsWidgetConfigs = {};

            const items = (layout && layout.widgets) || [];
            for (const item of items) {
                const wConf = item.widget || {};
                const wid = wConf.id || item.id || ('w_' + Math.random().toString(36).slice(2, 8));
                this._gsWidgetConfigs[wid] = Object.assign({}, wConf, { id: wid });

                const label = wConf.title || wConf.viewCode || '(未設定)';
                this._gsGrid.addWidget({
                    x: item.x || 0,
                    y: item.y || 0,
                    w: item.w || 6,
                    h: item.h || 4,
                    id: wid,
                    content: '<div style="padding:8px;font-size:12px;"><b>'
                        + (wConf.type || 'DATALIST') + '</b><br>'
                        + label + '</div>',
                });
            }
        },

        _buildGridStackLayoutJson() {
            if (!this._gsGrid) return { version: 2, widgets: [] };
            const items = this._gsGrid.getGridItems();
            const widgets = [];
            for (const el of items) {
                const node = el.gridstackNode;
                if (!node) continue;
                const wid = node.id || el.getAttribute('gs-id');
                const conf = this._gsWidgetConfigs[wid] || {};
                widgets.push({
                    x: node.x, y: node.y, w: node.w, h: node.h,
                    id: wid,
                    widget: Object.assign({}, conf),
                });
            }
            return { version: 2, widgets };
        },

        // ===== 屬性面板 =====

        _populateWidgetSettings(config) {
            this.settingViewCode = config.viewCode || '';
            this.settingTitle = config.title || '';
            this.settingPageSize = config.pageSize || 10;
            this.settingShowSearch = config.showSearch !== false;
            this.settingShowPagination = config.showPagination !== false;
            this.settingAllowCreate = config.allowCreate || false;
            this.settingAllowEdit = config.allowEdit || false;
            this.settingAllowDelete = config.allowDelete || false;
            this.settingContextOutputs = JSON.parse(JSON.stringify(config.contextOutputs || []));
            this.settingContextInputs = JSON.parse(JSON.stringify(config.contextInputs || []));
        },

        getViewColumns() {
            const v = this.availableViews.find(v => v.secure_code === this.settingViewCode);
            if (!v || !v.columns_config) return [];
            return v.columns_config.filter(c => c.visible).map(c => c.column);
        },

        applyWidgetSettings() {
            const config = {
                viewCode: this.settingViewCode,
                title: this.settingTitle,
                pageSize: parseInt(this.settingPageSize, 10) || 10,
                showSearch: this.settingShowSearch,
                showPagination: this.settingShowPagination,
                allowCreate: this.settingAllowCreate,
                allowEdit: this.settingAllowEdit,
                allowDelete: this.settingAllowDelete,
                contextOutputs: this.settingContextOutputs,
                contextInputs: this.settingContextInputs,
            };

            if (this.layoutMode === 'grid' && this._gridEditor && this.selectedZoneId) {
                this._gridEditor.updateWidget(this.selectedZoneId, config);
            } else if (this.layoutMode === 'free' && this.selectedZoneId) {
                const wid = this.selectedZoneId;
                if (this._gsWidgetConfigs[wid]) {
                    Object.assign(this._gsWidgetConfigs[wid], config);
                    // 更新 GridStack 項目的顯示
                    const items = this._gsGrid.getGridItems();
                    for (const el of items) {
                        if (el.getAttribute('gs-id') === wid) {
                            const content = el.querySelector('.grid-stack-item-content');
                            if (content) {
                                content.innerHTML = '<div style="padding:8px;font-size:12px;"><b>'
                                    + (config.type || 'DATALIST') + '</b><br>'
                                    + (config.title || config.viewCode || '(未設定)')
                                    + '</div>';
                            }
                        }
                    }
                }
                this.dirty = true;
            }

            this.showToast('已套用', 'success');
        },

        removeSelectedWidget() {
            if (!this.selectedZoneId) return;

            if (this.layoutMode === 'grid' && this._gridEditor) {
                delete this._gridEditor.widgetMap[this.selectedZoneId];
                this._gridEditor.render();
            } else if (this.layoutMode === 'free' && this._gsGrid) {
                const items = this._gsGrid.getGridItems();
                for (const el of items) {
                    if (el.getAttribute('gs-id') === this.selectedZoneId) {
                        this._gsGrid.removeWidget(el);
                        break;
                    }
                }
                delete this._gsWidgetConfigs[this.selectedZoneId];
            }

            this.selectedZoneId = null;
            this.showProps = false;
            this.dirty = true;
        },

        // Context output/input 管理
        addContextOutput() {
            this.settingContextOutputs.push({ event: 'row-select', contextKey: '', sourceColumn: '' });
        },

        removeContextOutput(idx) {
            this.settingContextOutputs.splice(idx, 1);
        },

        addContextInput() {
            this.settingContextInputs.push({ contextKey: '', filterColumn: '' });
        },

        removeContextInput(idx) {
            this.settingContextInputs.splice(idx, 1);
        },

        // ===== 儲存 =====

        async savePage() {
            if (!this.currentPageSc) {
                this.showToast('無頁面可儲存 (請先選擇 page 節點)', 'error');
                return;
            }

            let layoutJson;
            if (this.layoutMode === 'grid') {
                layoutJson = this._gridEditor ? this._gridEditor.toLayoutJson() : this._emptyGridLayout();
            } else {
                layoutJson = this._buildGridStackLayoutJson();
            }

            try {
                const res = await fetch('/api/nocode-builder/pages/' + this.currentPageSc, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ layout_json: layoutJson }),
                });
                const data = await res.json();
                if (data.success) {
                    this.dirty = false;
                    this.showToast('已儲存', 'success');
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗', 'error');
            }
        },

        // ===== 預覽 =====

        previewPage() {
            if (!this.subSystemSc) return;
            window.open('/nocode-builder/sub-systems/' + this.subSystemSc + '/portal', '_blank');
        },

        // ===== 發布/下線 =====

        async togglePublish() {
            if (!this.subSystem) return;
            const action = this.subSystem.status === 'draft' ? 'publish' : 'unpublish';
            const label = action === 'publish' ? '上線' : '下線';

            if (!confirm('確定要' + label + '「' + this.subSystem.name + '」嗎?')) return;

            try {
                const res = await fetch('/api/nocode-builder/projects/' + this.subSystemSc + '/' + action, {
                    method: 'POST',
                });
                const data = await res.json();
                if (data.success) {
                    this.subSystem.status = data.data.status;
                    this.showToast('已' + label, 'success');
                } else {
                    this.showToast(data.error || label + '失敗', 'error');
                }
            } catch (e) {
                this.showToast(label + '失敗', 'error');
            }
        },

        // ===== Toast =====

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
