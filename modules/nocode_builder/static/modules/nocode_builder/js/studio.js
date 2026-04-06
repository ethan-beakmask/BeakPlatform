/**
 * Studio 設計器 - 統一設計器 Alpine.js Manager
 *
 * 佈局: 左側(元件庫+Site Map樹) + 中央(設計區) + 右側(屬性面板)
 *
 * 支援兩種佈局模式 (可在同頁面切換):
 *   - grid: 框架模式 (GridLayoutEditor, 16宮格矩陣)
 *   - free: 自由模式 (GridStack, 12欄拖放)
 *
 * Site Map 樹使用 BeakTree 元件 (lines-dom 渲染器 + 拖曳排序)
 */

var SM_ROLES = ['GUEST', 'MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2', 'MEMBER'];
var SM_ROLE_LABELS = {
    GUEST: '訪客 (任何人)',
    MANAGER: '管理者',
    DEPUTY: '副管理者',
    PROXY1: '代理人 1',
    PROXY2: '代理人 2',
    MEMBER: '成員',
};
var SM_ROLE_HINTS = {
    GUEST: '含非成員',
    MANAGER: '',
    DEPUTY: '',
    PROXY1: '',
    PROXY2: '',
    MEMBER: '',
};

function studioManager() {
    var config = window.__STUDIO_CONFIG || {};

    return {
        // Core
        subSystemSc: config.subSystemSc || '',
        subSystem: null,
        loading: true,

        // Edit mode: 'grid' (框架) | 'free' (自由)
        editMode: 'grid',

        // Component library (易擴充，新增元件只需加入此陣列)
        componentTypes: [
            { type: 'DATALIST', label: '資料清單', icon: 'fa-table', desc: '展示與操作資料表' },
        ],

        // Site Map
        tree: [],
        _bkTree: null,
        selectedNode: null,

        // Page layout
        currentPageSc: null,
        dirty: false,

        // Grid editor (框架模式)
        _gridEditor: null,

        // GridStack editor (自由模式)
        _gsGrid: null,
        _gsWidgetConfigs: {},  // id -> widget config
        _gsWidgets: {},        // id -> DataListWidget instances (free mode)

        // Property panel
        showProps: false,
        propsMode: 'widget',    // 'widget' | 'perm'
        selectedZoneId: null,

        // Widget settings
        settingDataSource: '',
        settingTableName: '',
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

        // Role permissions & filters
        settingUseRolePerms: false,
        settingRolePerms: {},       // { ROLE: { create:bool, edit:bool, delete:bool } }
        settingRoleFilters: {},     // { ROLE: { column: value, ... } }
        settingFilterRole: '',      // 目前正在編輯篩選的角色
        settingFilterEntries: [],   // [{ key, value }] 目前角色的篩選條件

        // Role permission matrix helpers
        rolePermRoles: ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2', 'MEMBER', 'GUEST'],
        roleLabels: SM_ROLE_LABELS,
        filterVarOptions: ['$CURRENT_USER', '$CURRENT_USER_NAME', '$CURRENT_ORG', '$TODAY'],

        // Data sources & tables
        dataSources: [],
        sourceTables: [],
        loadingTables: false,
        resolvingView: false,

        // Available views (for backward compat)
        availableViews: [],

        // Node form
        showAddNodeModal: false,
        addNodeForm: { name: '', node_type: 'page', parent_sc: '' },

        // Access Roles (准入設定)
        editAccessRoles: [],
        accessRoleOptions: SM_ROLES.map(function (r) {
            return { value: r, label: SM_ROLE_LABELS[r] || r, hint: SM_ROLE_HINTS[r] || '' };
        }),

        // Pages list
        pageList: [],

        // Toast
        toast: { show: false, message: '', type: 'success' },

        // ================================================================
        // Initialization
        // ================================================================

        async init() {
            await this._loadSubSystem();
            if (!this.subSystem) {
                this.loading = false;
                return;
            }

            await Promise.all([
                this._loadTree(),
                this._loadViews(),
                this._loadPages(),
                this._loadDataSources(),
            ]);

            this.loading = false;

            this.$nextTick(() => {
                this._initSiteMapTree();
            });
        },

        _waitForEl: function (id, cb) {
            var check = function () {
                var el = document.getElementById(id);
                if (el) cb(el);
                else requestAnimationFrame(check);
            };
            requestAnimationFrame(check);
        },

        // ================================================================
        // Data Loading
        // ================================================================

        async _loadSubSystem() {
            try {
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc);
                var data = await res.json();
                if (data.success) this.subSystem = data.data;
            } catch (e) {
                console.error('Load sub system failed:', e);
            }
        },

        async _loadTree() {
            try {
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map');
                var data = await res.json();
                if (data.success) this.tree = data.data || [];
            } catch (e) {
                console.error('Load tree failed:', e);
            }
        },

        async _loadViews() {
            try {
                var res = await fetch('/api/nocode-builder/views');
                var data = await res.json();
                if (data.success) this.availableViews = data.data || [];
            } catch (e) {
                console.error('Load views failed:', e);
            }
        },

        async _loadPages() {
            try {
                var res = await fetch('/api/nocode-builder/pages');
                var data = await res.json();
                if (data.success) this.pageList = data.data || [];
            } catch (e) {
                console.error('Load pages failed:', e);
            }
        },

        async _loadDataSources() {
            try {
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/data-sources');
                var data = await res.json();
                if (data.success) {
                    this.dataSources = (data.data || []).filter(function (s) { return s.available; });
                }
            } catch (e) {
                console.error('Load data sources failed:', e);
            }
        },

        async onDataSourceChange() {
            this.sourceTables = [];
            this.settingTableName = '';
            this.settingViewCode = '';
            if (!this.settingDataSource) return;

            this.loadingTables = true;
            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc +
                    '/data-sources/' + this.settingDataSource + '/tables'
                );
                var data = await res.json();
                if (data.success) this.sourceTables = data.data || [];
            } catch (e) {
                console.error('Load source tables failed:', e);
            } finally {
                this.loadingTables = false;
            }
        },

        async onTableNameChange() {
            this.settingViewCode = '';
            if (!this.settingDataSource || !this.settingTableName) return;

            this.resolvingView = true;
            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc + '/resolve-view',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            data_source: this.settingDataSource,
                            table_name: this.settingTableName,
                        }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this.settingViewCode = data.data.secure_code;
                    var exists = this.availableViews.some(function (v) {
                        return v.secure_code === data.data.secure_code;
                    });
                    if (!exists) {
                        this.availableViews.push(data.data);
                    }
                    if (data.created) {
                        this.showToast('已自動建立視圖配置', 'success');
                    }
                } else {
                    this.showToast(data.error || '無法取得視圖', 'error');
                }
            } catch (e) {
                console.error('Resolve view failed:', e);
                this.showToast('視圖解析失敗', 'error');
            } finally {
                this.resolvingView = false;
            }
        },

        // ================================================================
        // Mode Switching
        // ================================================================

        switchMode: function (mode) {
            if (mode === this.editMode) return;
            if (!this.selectedNode || this.selectedNode.node_type !== 'page') return;

            var hasContent = false;
            if (this.editMode === 'grid' && this._gridEditor) {
                hasContent = Object.keys(this._gridEditor.widgetMap).length > 0;
            } else if (this.editMode === 'free' && this._gsGrid) {
                hasContent = Object.keys(this._gsWidgetConfigs).length > 0;
            }

            if (hasContent) {
                if (!confirm('切換模式將清空目前的佈局，確定嗎?')) return;
            }

            this.editMode = mode;
            this._clearCanvas();
            this.showProps = false;
            this.selectedZoneId = null;

            var self = this;
            this.$nextTick(function () {
                if (mode === 'grid') {
                    self._waitForEl('stu-grid-canvas', function () {
                        self._initGridEditor();
                    });
                } else {
                    self._waitForEl('stu-gridstack', function () {
                        self._initGridStackEditor();
                    });
                }
                self.dirty = true;
            });
        },

        _detectMode: function (layoutJson) {
            if (!layoutJson) return 'grid';
            if (layoutJson.version === 3 && layoutJson.mode === 'grid') return 'grid';
            if (layoutJson.version === 2) return 'free';
            return 'grid';
        },

        // ================================================================
        // Site Map Tree (BeakTree)
        // ================================================================

        _initSiteMapTree: function () {
            var wrap = document.querySelector('.stu-tree-wrap');
            if (!wrap) return;

            var source = this._treeToSource(this.tree);

            if (this._bkTree) {
                try { this._bkTree.destroy(); } catch (e) { /* ignore */ }
                this._bkTree = null;
            }

            var el = document.getElementById('stu-tree');
            if (el) el.innerHTML = '';
            else {
                el = document.createElement('div');
                el.id = 'stu-tree';
                wrap.prepend(el);
            }

            if (source.length === 0) return;

            var self = this;
            this._bkTree = new BeakTree(el, {
                data: source,
                treeMode: 'lines-dom',
                draggable: true,
                hideHeader: true,
                onNodeClick: function (nodeId, node) {
                    self._onBeakTreeNodeClick(nodeId, node);
                },
                onNodeMoved: function (nodeId, newParentId, newIndex) {
                    self._saveReorder();
                },
            });

            // 預設展開所有節點
            this._bkTree.expandAll();
        },

        /**
         * API 樹資料 → BeakTree 格式
         * { secure_code, name, icon, node_type, access_roles, ... }
         * → { id, label, data, children }
         */
        _treeToSource: function (nodes) {
            if (!nodes || nodes.length === 0) return [];
            var self = this;
            return nodes.map(function (n) {
                return {
                    id: n.secure_code,
                    label: self._buildNodeLabel(n),
                    data: JSON.parse(JSON.stringify(n)),
                    children: self._treeToSource(n.children || []),
                };
            });
        },

        /**
         * 組合節點顯示 label（含 icon + 名稱 + 准入 badge）
         */
        _buildNodeLabel: function (n) {
            var parts = [];
            if (n.icon) parts.push(n.icon);
            parts.push(n.name);
            // 准入 badge（僅 page 節點）
            if (n.node_type === 'page') {
                parts.push(this._accessBadgeText(n.access_roles));
            }
            return parts.join(' ');
        },

        /**
         * 准入狀態文字 badge
         */
        _accessBadgeText: function (roles) {
            if (!roles || roles.length === 0) return '[禁]';
            if (roles.indexOf('GUEST') >= 0) return '[開放]';
            return '[' + roles.length + '角色]';
        },

        /**
         * BeakTree 節點點擊 → 選取節點並載入頁面
         */
        _onBeakTreeNodeClick: function (nodeId, bkNode) {
            var nodeData = (bkNode && bkNode.data) ? bkNode.data : {};

            // 未儲存變更提示
            if (this.dirty && this.currentPageSc) {
                if (!confirm('目前頁面有未儲存的變更，確定要切換嗎?')) return;
            }

            // 高亮選取的列
            if (this._bkTree && this._bkTree._tbodyEl) {
                var old = this._bkTree._tbodyEl.querySelector('.stu-tree-selected');
                if (old) old.classList.remove('stu-tree-selected');
                var row = this._bkTree._tbodyEl.querySelector('tr[data-id="' + nodeId + '"]');
                if (row) row.classList.add('stu-tree-selected');
            }

            this._onTreeNodeSelect(nodeData);
        },

        _onTreeNodeSelect: function (nodeData) {
            this.selectedNode = nodeData;

            if (nodeData.node_type === 'page') {
                var pageSc = nodeData.page_layout_secure_code;
                if (pageSc) {
                    this._loadPageLayout(pageSc);
                } else {
                    this.currentPageSc = null;
                    this._setupEmptyCanvas();
                }
            } else {
                this.currentPageSc = null;
                this._clearCanvas();
            }

            this.showProps = false;
            this.selectedZoneId = null;
        },

        async _loadPageLayout(pageSc) {
            try {
                var res = await fetch('/api/nocode-builder/pages/' + pageSc);
                var data = await res.json();
                if (!data.success) return;

                this.currentPageSc = pageSc;
                var layout = data.data.layout_json || {};
                var detectedMode = this._detectMode(layout);

                this.editMode = detectedMode;
                this.dirty = false;

                var self = this;
                this.$nextTick(function () {
                    if (detectedMode === 'grid') {
                        self._waitForEl('stu-grid-canvas', function () {
                            self._ensureEditor();
                            if (self._gridEditor) {
                                self._gridEditor.loadLayout(
                                    layout.version === 3 ? layout : self._emptyGridLayout()
                                );
                            }
                        });
                    } else {
                        self._waitForEl('stu-gridstack', function () {
                            self._ensureEditor();
                            self._loadGridStackLayout(layout);
                        });
                    }
                });
            } catch (e) {
                console.error('Load page layout failed:', e);
            }
        },

        _setupEmptyCanvas: function () {
            var self = this;
            this.$nextTick(function () {
                if (self.editMode === 'grid') {
                    self._waitForEl('stu-grid-canvas', function () {
                        self._ensureEditor();
                        self._clearCanvas();
                    });
                } else {
                    self._waitForEl('stu-gridstack', function () {
                        self._ensureEditor();
                        self._clearCanvas();
                    });
                }
            });
        },

        _clearCanvas: function () {
            // 清理 free mode widgets（不論當前模式，確保模式切換時也能正確清理）
            this._gsDestroyAllWidgets();
            if (this._gsGrid) {
                this._gsGrid.removeAll();
            }
            this._gsWidgetConfigs = {};
            // 清理 grid mode
            if (this._gridEditor) {
                this._gridEditor.loadLayout(this._emptyGridLayout());
            }
        },

        // ================================================================
        // Editor Setup
        // ================================================================

        _ensureEditor: function () {
            if (this.editMode === 'grid') {
                this._initGridEditor();
            } else {
                this._initGridStackEditor();
            }
        },

        // ================================================================
        // Grid Mode (框架模式)
        // ================================================================

        _initGridEditor: function () {
            var el = document.getElementById('stu-grid-canvas');
            if (!el) return;

            if (this._gridEditor) {
                this._gridEditor.destroy();
                this._gridEditor = null;
            }
            el.innerHTML = '';

            this._gridEditor = new GridLayoutEditor(el, { rows: 4, cols: 4 });

            var self = this;
            this._gridEditor.onZoneSelect = function (zoneId) {
                self.selectedZoneId = zoneId;
                self.showProps = false;
                self.propsMode = 'widget';
            };

            this._gridEditor.onWidgetSelect = function (zoneId, widgetConfig) {
                self.selectedZoneId = zoneId;
                self._populateWidgetSettings(widgetConfig);
                self.showProps = true;
                self.propsMode = 'widget';
            };

            this._gridEditor.onChanged = function () {
                self.dirty = true;
            };
        },

        _emptyGridLayout: function () {
            return { version: 3, mode: 'grid', gridSize: [4, 4], zones: [], widgets: [] };
        },

        // ================================================================
        // Free Mode (自由模式)
        // ================================================================

        _initGridStackEditor: function () {
            var el = document.getElementById('stu-gridstack');
            if (!el) return;

            if (this._gsGrid) {
                try { this._gsGrid.destroy(false); } catch (e) { /* ignore */ }
                this._gsGrid = null;
            }
            el.innerHTML = '';
            el.className = 'grid-stack';

            this._gsGrid = GridStack.init({
                column: 12,
                cellHeight: 60,
                margin: 8,
                float: true,
                removable: false,
                acceptWidgets: true,
                draggable: { handle: '.dlw-header' },
            }, el);

            var self = this;
            this._gsGrid.on('change', function () { self.dirty = true; });

            // 點擊 widget 時切換右側設定面板
            var gsEl = this._gsGrid.el;
            gsEl.addEventListener('click', function (e) {
                var gsItem = e.target.closest('.grid-stack-item');
                if (gsItem) {
                    var wid = gsItem.getAttribute('gs-id');
                    if (wid && self._gsWidgetConfigs[wid]) {
                        self._gsSelectItem(wid);
                    }
                }
            });
        },

        _gsAddWidget: function (type) {
            if (!this._gsGrid) return;
            var wid = 'w_' + Math.random().toString(36).slice(2, 8);
            var widgetConfig = {
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
            this._gsWidgetConfigs[wid] = widgetConfig;

            var gsItem = this._gsGrid.addWidget({
                x: 0, y: 0, w: 6, h: 4,
                id: wid,
                content: '',
            });

            var content = gsItem.querySelector('.grid-stack-item-content');
            if (content) {
                content.innerHTML = '';
                var widget = new DataListWidget(content, widgetConfig);
                widget.init();
                this._gsWidgets[wid] = widget;
            }

            this._gsSelectItem(wid);
            this.dirty = true;
        },

        _loadGridStackLayout: function (layout) {
            if (!this._gsGrid) {
                var self = this;
                setTimeout(function () {
                    self._initGridStackEditor();
                    self._loadGridStackLayout(layout);
                }, 50);
                return;
            }

            this._gsDestroyAllWidgets();
            this._gsGrid.removeAll();
            this._gsWidgetConfigs = {};

            var items = (layout && layout.widgets) || [];
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var wConf = item.widget || {};
                var wid = wConf.id || item.id || ('w_' + Math.random().toString(36).slice(2, 8));
                var fullConfig = Object.assign({}, wConf, { id: wid });
                if (!fullConfig.contextOutputs) fullConfig.contextOutputs = [];
                if (!fullConfig.contextInputs) fullConfig.contextInputs = [];
                this._gsWidgetConfigs[wid] = fullConfig;

                var gsItem = this._gsGrid.addWidget({
                    x: item.x || 0,
                    y: item.y || 0,
                    w: item.w || 6,
                    h: item.h || 4,
                    id: wid,
                    content: '',
                });

                var content = gsItem.querySelector('.grid-stack-item-content');
                if (content) {
                    content.innerHTML = '';
                    var widget = new DataListWidget(content, fullConfig);
                    widget.init();
                    this._gsWidgets[wid] = widget;
                }
            }
        },

        _buildGridStackLayoutJson: function () {
            if (!this._gsGrid) return { version: 2, widgets: [] };
            var gridItems = this._gsGrid.getGridItems();
            var widgets = [];
            for (var i = 0; i < gridItems.length; i++) {
                var el = gridItems[i];
                var node = el.gridstackNode;
                if (!node) continue;
                var wid = node.id || el.getAttribute('gs-id');
                var conf = this._gsWidgetConfigs[wid] || {};
                widgets.push({
                    x: node.x, y: node.y, w: node.w, h: node.h,
                    id: wid,
                    widget: Object.assign({}, conf),
                });
            }
            return { version: 2, widgets: widgets };
        },

        _gsSelectItem: function (wid) {
            // 同一 widget 已選取時，不重新載入設定（避免覆蓋未套用的修改）
            if (this.selectedZoneId === wid && this.showProps && this.propsMode === 'widget') {
                return;
            }
            document.querySelectorAll('.grid-stack-item.stu-gs-selected').forEach(function (el) {
                el.classList.remove('stu-gs-selected');
            });
            var el = document.querySelector('.grid-stack-item[gs-id="' + wid + '"]');
            if (el) el.classList.add('stu-gs-selected');
            this.selectedZoneId = wid;
            if (this._gsWidgetConfigs[wid]) {
                this._populateWidgetSettings(this._gsWidgetConfigs[wid]);
                this.showProps = true;
                this.propsMode = 'widget';
            }
        },

        // ================================================================
        // Component Library
        // ================================================================

        onComponentDragStart: function (e, type) {
            e.dataTransfer.setData('text/plain', type);
            e.dataTransfer.effectAllowed = 'copy';
        },

        onComponentClick: function (type) {
            if (this.editMode === 'grid' && this._gridEditor) {
                this._gridEditor.addWidgetToSelected(type);
            } else if (this.editMode === 'free') {
                this._gsAddWidget(type);
            }
        },

        // ================================================================
        // Property Panel
        // ================================================================

        _populateWidgetSettings: async function (widgetConfig) {
            this.settingDataSource = widgetConfig.dataSource || '';
            this.settingTableName = widgetConfig.tableName || '';
            this.settingViewCode = widgetConfig.viewCode || '';
            this.settingTitle = widgetConfig.title || '';
            this.settingPageSize = widgetConfig.pageSize || 10;
            this.settingShowSearch = widgetConfig.showSearch !== false;
            this.settingShowPagination = widgetConfig.showPagination !== false;
            this.settingAllowCreate = widgetConfig.allowCreate || false;
            this.settingAllowEdit = widgetConfig.allowEdit || false;
            this.settingAllowDelete = widgetConfig.allowDelete || false;
            this.settingContextOutputs = JSON.parse(JSON.stringify(widgetConfig.contextOutputs || []));
            this.settingContextInputs = JSON.parse(JSON.stringify(widgetConfig.contextInputs || []));

            // Role permissions
            var rp = widgetConfig.rolePermissions;
            this.settingUseRolePerms = !!(rp && Object.keys(rp).length > 0);
            this.settingRolePerms = rp ? JSON.parse(JSON.stringify(rp)) : {};

            // Role filters
            var rf = widgetConfig.roleFilters;
            this.settingRoleFilters = rf ? JSON.parse(JSON.stringify(rf)) : {};
            this.settingFilterRole = '';
            this.settingFilterEntries = [];

            if (this.settingDataSource) {
                // 直接載入表列表，不透過 onDataSourceChange()
                // 避免暫時清空 settingViewCode 導致 select options 消失
                this.loadingTables = true;
                try {
                    var res = await fetch(
                        '/api/nocode-builder/sub-systems/' + this.subSystemSc +
                        '/data-sources/' + this.settingDataSource + '/tables'
                    );
                    var data = await res.json();
                    if (data.success) this.sourceTables = data.data || [];
                } catch (e) {
                    console.error('Load source tables failed:', e);
                } finally {
                    this.loadingTables = false;
                }
            }
        },

        getViewColumns: function () {
            var vc = this.settingViewCode;
            var v = this.availableViews.find(function (v) { return v.secure_code === vc; });
            if (!v || !v.columns_config) return [];
            return v.columns_config.filter(function (c) { return c.visible; }).map(function (c) {
                return { column: c.column, label: c.label || c.column };
            });
        },

        applyWidgetSettings: function () {
            // 先存回目前正在編輯的篩選角色
            this._saveFilterEntries();

            // 過濾空白的 context 項目
            var validOutputs = this.settingContextOutputs.filter(function (o) {
                return o.contextKey && o.contextKey.trim() && o.sourceColumn && o.sourceColumn.trim();
            });
            var validInputs = this.settingContextInputs.filter(function (i) {
                return i.contextKey && i.contextKey.trim() && i.filterColumn && i.filterColumn.trim();
            });
            var removedCount = (this.settingContextOutputs.length - validOutputs.length)
                             + (this.settingContextInputs.length - validInputs.length);
            if (removedCount > 0) {
                this.settingContextOutputs = validOutputs;
                this.settingContextInputs = validInputs;
                this.showToast('已移除 ' + removedCount + ' 筆未填完的 Context 設定', 'success');
            }

            var widgetConfig = {
                dataSource: this.settingDataSource,
                tableName: this.settingTableName,
                viewCode: this.settingViewCode,
                title: this.settingTitle,
                pageSize: parseInt(this.settingPageSize, 10) || 10,
                showSearch: this.settingShowSearch,
                showPagination: this.settingShowPagination,
                allowCreate: this.settingAllowCreate,
                allowEdit: this.settingAllowEdit,
                allowDelete: this.settingAllowDelete,
                contextOutputs: JSON.parse(JSON.stringify(validOutputs)),
                contextInputs: JSON.parse(JSON.stringify(validInputs)),
            };

            // Role permissions
            if (this.settingUseRolePerms && Object.keys(this.settingRolePerms).length > 0) {
                widgetConfig.rolePermissions = JSON.parse(JSON.stringify(this.settingRolePerms));
            }

            // Role filters (清理空條目)
            var cleanFilters = {};
            var self = this;
            Object.keys(this.settingRoleFilters).forEach(function (role) {
                var f = self.settingRoleFilters[role];
                if (f && Object.keys(f).length > 0) {
                    cleanFilters[role] = JSON.parse(JSON.stringify(f));
                }
            });
            if (Object.keys(cleanFilters).length > 0) {
                widgetConfig.roleFilters = cleanFilters;
            }

            // 取得目標 widget config，先清除需要移除的 key
            var target = null;
            if (this.editMode === 'grid' && this._gridEditor && this.selectedZoneId) {
                target = this._gridEditor.widgetMap[this.selectedZoneId];
            } else if (this.editMode === 'free' && this.selectedZoneId) {
                target = this._gsWidgetConfigs[this.selectedZoneId];
            }
            if (target) {
                if (!this.settingUseRolePerms) delete target.rolePermissions;
                if (Object.keys(cleanFilters).length === 0) delete target.roleFilters;
            }

            // 套用設定
            if (this.editMode === 'grid' && this._gridEditor && this.selectedZoneId) {
                this._gridEditor.updateWidget(this.selectedZoneId, widgetConfig);
            } else if (this.editMode === 'free' && this.selectedZoneId) {
                var wid = this.selectedZoneId;
                if (this._gsWidgetConfigs[wid]) {
                    Object.assign(this._gsWidgetConfigs[wid], widgetConfig);
                    this._gsUpdateWidget(wid, this._gsWidgetConfigs[wid]);
                }
                this.dirty = true;
            }

            this.showToast('已套用', 'success');
        },

        _gsUpdateWidget: function (wid, cfg) {
            var widget = this._gsWidgets[wid];
            if (widget) {
                widget.updateConfig(cfg);
            }
        },

        _gsDestroyAllWidgets: function () {
            if (typeof PageContext !== 'undefined') {
                PageContext.reset();
            }
            var ids = Object.keys(this._gsWidgets);
            for (var i = 0; i < ids.length; i++) {
                this._gsWidgets[ids[i]].destroy();
            }
            this._gsWidgets = {};
        },

        removeSelectedWidget: function () {
            if (!this.selectedZoneId) return;

            if (this.editMode === 'grid' && this._gridEditor) {
                delete this._gridEditor.widgetMap[this.selectedZoneId];
                this._gridEditor.render();
            } else if (this.editMode === 'free' && this._gsGrid) {
                var wid = this.selectedZoneId;
                if (this._gsWidgets[wid]) {
                    this._gsWidgets[wid].destroy();
                    delete this._gsWidgets[wid];
                }
                var items = this._gsGrid.getGridItems();
                for (var i = 0; i < items.length; i++) {
                    if (items[i].getAttribute('gs-id') === wid) {
                        this._gsGrid.removeWidget(items[i]);
                        break;
                    }
                }
                delete this._gsWidgetConfigs[wid];
            }

            this.selectedZoneId = null;
            this.showProps = false;
            this.dirty = true;
        },

        // Context Output/Input
        addContextOutput: function () {
            this.settingContextOutputs.push({ event: 'row-select', contextKey: '', sourceColumn: '' });
        },
        removeContextOutput: function (idx) {
            this.settingContextOutputs.splice(idx, 1);
        },
        addContextInput: function () {
            this.settingContextInputs.push({ contextKey: '', filterColumn: '' });
        },
        removeContextInput: function (idx) {
            this.settingContextInputs.splice(idx, 1);
        },

        // ================================================================
        // Role Permissions & Filters
        // ================================================================

        /**
         * 啟用/停用依角色 CRUD 設定。啟用時以管理層全權、其他唯讀為預設值。
         */
        toggleRolePermMode: function (enabled) {
            this.settingUseRolePerms = enabled;
            if (enabled && Object.keys(this.settingRolePerms).length === 0) {
                var adminRoles = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'];
                var perms = {};
                for (var i = 0; i < this.rolePermRoles.length; i++) {
                    var r = this.rolePermRoles[i];
                    var isAdmin = adminRoles.indexOf(r) >= 0;
                    perms[r] = {
                        create: isAdmin,
                        edit: isAdmin,
                        'delete': isAdmin,
                    };
                }
                this.settingRolePerms = perms;
            }
        },

        /**
         * 取得指定角色的指定 CRUD 權限值
         */
        getRolePerm: function (role, action) {
            var rp = this.settingRolePerms[role];
            return rp ? !!rp[action] : false;
        },

        /**
         * 設定指定角色的指定 CRUD 權限值
         */
        setRolePerm: function (role, action, value) {
            if (!this.settingRolePerms[role]) {
                this.settingRolePerms[role] = { create: false, edit: false, 'delete': false };
            }
            this.settingRolePerms[role][action] = value;
        },

        /**
         * 切換正在編輯的篩選角色，先存回上一個角色再載入新角色
         */
        selectFilterRole: function (role) {
            // 存回目前角色
            this._saveFilterEntries();
            // 載入新角色
            this.settingFilterRole = role;
            if (role && this.settingRoleFilters[role]) {
                var f = this.settingRoleFilters[role];
                this.settingFilterEntries = Object.keys(f).map(function (k) {
                    return { key: k, value: f[k] };
                });
            } else {
                this.settingFilterEntries = [];
            }
        },

        /**
         * 將目前的 filterEntries 寫回 settingRoleFilters
         */
        _saveFilterEntries: function () {
            if (!this.settingFilterRole) return;
            var obj = {};
            for (var i = 0; i < this.settingFilterEntries.length; i++) {
                var e = this.settingFilterEntries[i];
                var k = (e.key || '').trim();
                var v = (e.value || '').trim();
                if (k) obj[k] = v;
            }
            if (Object.keys(obj).length > 0) {
                this.settingRoleFilters[this.settingFilterRole] = obj;
            } else {
                delete this.settingRoleFilters[this.settingFilterRole];
            }
        },

        addFilterEntry: function () {
            this.settingFilterEntries.push({ key: '', value: '' });
        },

        removeFilterEntry: function (idx) {
            this.settingFilterEntries.splice(idx, 1);
        },

        /**
         * 取得已設定篩選的角色摘要
         */
        getFilterSummary: function () {
            var self = this;
            var summary = [];
            this.rolePermRoles.forEach(function (r) {
                // 目前正在編輯的角色用 filterEntries 計算
                if (r === self.settingFilterRole) {
                    var cnt = self.settingFilterEntries.filter(function (e) {
                        return (e.key || '').trim();
                    }).length;
                    if (cnt > 0) summary.push((SM_ROLE_LABELS[r] || r) + '(' + cnt + ')');
                } else {
                    var f = self.settingRoleFilters[r];
                    if (f && Object.keys(f).length > 0) {
                        summary.push((SM_ROLE_LABELS[r] || r) + '(' + Object.keys(f).length + ')');
                    }
                }
            });
            return summary.length > 0 ? summary.join(', ') : '(無)';
        },

        /**
         * 清除指定角色的所有篩選
         */
        clearFilterRole: function (role) {
            delete this.settingRoleFilters[role];
            if (this.settingFilterRole === role) {
                this.settingFilterEntries = [];
            }
        },

        // ================================================================
        // Node Management
        // ================================================================

        openAddNode: function () {
            var isFirstNode = this.tree.length === 0;

            if (isFirstNode) {
                // 第一個節點必須是根頁面 welcome
                this.addNodeForm = {
                    name: 'welcome',
                    node_type: 'page',
                    parent_sc: '',
                };
            } else {
                // 已有根節點，新節點掛在選取節點或根節點下
                var rootSc = (this.tree[0] && this.tree[0].secure_code) || '';
                this.addNodeForm = {
                    name: '',
                    node_type: 'page',
                    parent_sc: this.selectedNode
                        ? this.selectedNode.secure_code
                        : rootSc,
                };
            }
            this.showAddNodeModal = true;
        },

        async doAddNode() {
            var name = this.addNodeForm.name.trim();
            if (!name) { this.showToast('名稱為必填', 'error'); return; }

            try {
                var body = {
                    name: name,
                    node_type: this.addNodeForm.node_type,
                    parent_secure_code: this.addNodeForm.parent_sc || null,
                };

                if (this.addNodeForm.node_type === 'page') {
                    var emptyLayout = this.editMode === 'grid'
                        ? { version: 3, mode: 'grid', gridSize: [4, 4], zones: [], widgets: [] }
                        : { version: 2, widgets: [] };

                    var pageRes = await fetch('/api/nocode-builder/pages', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name, layout_json: emptyLayout }),
                    });
                    var pageData = await pageRes.json();
                    if (pageData.success) {
                        body.page_layout_secure_code = pageData.data.secure_code;
                    } else {
                        this.showToast(pageData.error || '建立頁面佈局失敗', 'error');
                        return;
                    }
                }

                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map/nodes',
                    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
                );
                var data = await res.json();
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
            // 根頁面不可刪除
            if (!this.selectedNode.parent_secure_code) {
                this.showToast('根頁面 (welcome) 不可刪除', 'error');
                return;
            }
            if (!confirm('確定要刪除節點「' + this.selectedNode.name + '」嗎?')) return;

            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + this.selectedNode.secure_code,
                    { method: 'DELETE' }
                );
                var data = await res.json();
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

        /**
         * 從 BeakTree 的 model 取得全部節點順序，送回後端 reorder
         */
        async _saveReorder() {
            if (!this._bkTree) return;

            var flatNodes = this._bkTree._flatNodes;
            var nodeMap = this._bkTree._nodeMap;
            var ordered = [];

            // 遍歷整棵樹（包括收合的節點），收集所有節點
            function collectAll(nodeId) {
                var node = nodeMap.get(nodeId);
                if (!node) return;
                ordered.push({
                    secure_code: node.id,
                    parent_secure_code: node.parentId || null,
                    sort_order: ordered.length,
                });
                for (var i = 0; i < node.children.length; i++) {
                    collectAll(node.children[i].id);
                }
            }

            // 從根節點開始
            var roots = this._bkTree.getRootNodes();
            for (var i = 0; i < roots.length; i++) {
                collectAll(roots[i].id);
            }

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

        // ================================================================
        // Save / Preview / Publish
        // ================================================================

        async savePage() {
            if (!this.currentPageSc) {
                this.showToast('無頁面可儲存 (請先選擇 page 節點)', 'error');
                return;
            }

            var layoutJson;
            if (this.editMode === 'grid') {
                layoutJson = this._gridEditor ? this._gridEditor.toLayoutJson() : this._emptyGridLayout();
            } else {
                layoutJson = this._buildGridStackLayoutJson();
            }

            try {
                var res = await fetch('/api/nocode-builder/pages/' + this.currentPageSc, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ layout_json: layoutJson }),
                });
                var data = await res.json();
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

        previewPage: function () {
            if (!this.subSystemSc) return;
            var url = '/nocode-builder/sub-systems/' + this.subSystemSc + '/portal';
            // 優先預覽當前設計頁，否則到 welcome
            if (this.selectedNode && this.selectedNode.node_type === 'page') {
                url += '?page=' + this.selectedNode.secure_code;
            }
            window.open(url, '_blank');
        },

        async togglePublish() {
            if (!this.subSystem) return;
            var action = this.subSystem.status === 'draft' ? 'publish' : 'unpublish';
            var label = action === 'publish' ? '上線' : '下線';

            if (!confirm('確定要' + label + '「' + this.subSystem.name + '」嗎?')) return;

            try {
                var res = await fetch('/api/nocode-builder/projects/' + this.subSystemSc + '/' + action, {
                    method: 'POST',
                });
                var data = await res.json();
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

        // ================================================================
        // Access Roles (准入設定)
        // ================================================================

        openAccessRoles: function () {
            if (!this.selectedNode) return;
            this.editAccessRoles = (this.selectedNode.access_roles || []).slice();
            this.propsMode = 'perm';
            this.showProps = true;
        },

        toggleAccessRole: function (role, checked) {
            if (role === 'GUEST' && checked) {
                // GUEST 互斥：勾 GUEST 清除其他
                this.editAccessRoles = ['GUEST'];
            } else if (role === 'GUEST' && !checked) {
                this.editAccessRoles = this.editAccessRoles.filter(function (r) { return r !== 'GUEST'; });
            } else if (checked) {
                // 勾選非 GUEST → 移除 GUEST
                this.editAccessRoles = this.editAccessRoles.filter(function (r) { return r !== 'GUEST'; });
                if (this.editAccessRoles.indexOf(role) < 0) {
                    this.editAccessRoles.push(role);
                }
            } else {
                this.editAccessRoles = this.editAccessRoles.filter(function (r) { return r !== role; });
            }
        },

        accessRolesStatus: function () {
            var roles = this.editAccessRoles;
            if (!roles || roles.length === 0) return '禁止所有人進入 (NONE)';
            if (roles.indexOf('GUEST') >= 0) return '開放 -- 任何人皆可進入';
            return '限定 ' + roles.length + ' 個角色可進入: ' + roles.join(', ');
        },

        async saveAccessRoles() {
            if (!this.selectedNode) return;
            var sc = this.selectedNode.secure_code;

            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + sc,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ access_roles: this.editAccessRoles }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    // 更新本地資料
                    this.selectedNode.access_roles = this.editAccessRoles.slice();
                    this.showToast('准入設定已儲存', 'success');
                    // 重新載入樹以更新 badge
                    await this._loadTree();
                    this._initSiteMapTree();
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
        },

        // ================================================================
        // Toast
        // ================================================================

        showToast: function (message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function () { self.toast.show = false; }, 3000);
        },
    };
}
