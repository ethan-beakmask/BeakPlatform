/**
 * Studio 設計器 - 統一設計器 Alpine.js Manager
 *
 * 佈局: 左側(元件庫+Site Map樹) + 中間(設定面板) + 右側(設計區)
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
            { type: 'SITEMENU', label: '選單', icon: 'fa-bars', desc: 'Site Map 導航選單' },
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
        showStylePanel: false,
        propsMode: 'style',     // 'style' | 'widget' | 'perm'
        selectedZoneId: null,

        // Page/SubSystem style config
        styleConfig: { bgColor: '', bgImage: { url: '', opacity: 30, fit: 'contain', position: 'center center' }, textColor: '', fontFamily: '', fontSize: null },
        _subSystemStyleConfig: {},  // 子系統預設樣式(快取)

        // Background gallery
        showBgGallery: false,
        bgGallery: [],

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

        // SITEMENU settings
        settingWidgetType: 'DATALIST',     // 目前選中的 widget type
        smStartNodeSc: '',
        smStartLevel: 'children',
        smOrientation: 'vertical',
        smShowWelcome: true,               // 顯示首頁連結
        smIconLayout: 'top',               // 'top' | 'inline'
        smMenuHeight: 'auto',              // 'auto' | 數字(px)
        smBgColor: '#ffffff',
        smItemBgColor: '#ffffff',
        smItemTextColor: '#333333',
        smItemHoverBgColor: '#e9ecef',
        smItemHoverTextColor: '#333333',
        smAccentColor: '#e67e22',
        smItemGap: 6,
        smHoverExpand: true,
        smHoverExpandDelay: 300,

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
        addNodeForm: { name: '', icon: '', parent_sc: '' },

        // Icon picker state
        _ip_show: false,
        _ip_activeCategory: 'business',
        _ip_search: '',
        _ip_selectedIcon: '',
        _iconTarget: 'node',   // 'node' | 'add' | 'item'
        _iconEditNodeSc: '',   // 'item' target 時追蹤的節點 SC

        // Access Roles (准入設定)
        editAccessRoles: [],
        accessRoleOptions: SM_ROLES.map(function (r) {
            return { value: r, label: SM_ROLE_LABELS[r] || r, hint: SM_ROLE_HINTS[r] || '' };
        }),

        // Pages list
        pageList: [],

        // Templates
        showSaveTemplateModal: false,
        saveTemplateForm: { name: '', description: '' },
        savingTemplate: false,
        templateList: [],
        loadingTemplates: false,
        selectedTemplateSc: null,

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
                if (data.success) {
                    this.subSystem = data.data;
                    this._subSystemStyleConfig = data.data.style_config || {};
                }
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
            if (!this.selectedNode) return;

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
            parts.push(n.name);
            parts.push(this._accessBadgeText(n.access_roles));
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
        // 未儲存切換 modal 暫存
        _pendingNodeSwitch: null,
        showUnsavedModal: false,

        _onBeakTreeNodeClick: function (nodeId, bkNode) {
            var nodeData = (bkNode && bkNode.data) ? bkNode.data : {};

            // 未儲存變更提示：顯示三選一 modal
            if (this.dirty && this.currentPageSc) {
                this._pendingNodeSwitch = { nodeId: nodeId, nodeData: nodeData };
                this.showUnsavedModal = true;
                return;
            }

            this._doNodeSwitch(nodeId, nodeData);
        },

        /** 三選一：儲存並切換 */
        async unsavedSaveAndSwitch() {
            this.showUnsavedModal = false;
            await this.savePage();
            if (this._pendingNodeSwitch) {
                var p = this._pendingNodeSwitch;
                this._pendingNodeSwitch = null;
                this._doNodeSwitch(p.nodeId, p.nodeData);
            }
        },

        /** 三選一：不儲存切換 */
        unsavedDiscardAndSwitch() {
            this.showUnsavedModal = false;
            this.dirty = false;
            if (this._pendingNodeSwitch) {
                var p = this._pendingNodeSwitch;
                this._pendingNodeSwitch = null;
                this._doNodeSwitch(p.nodeId, p.nodeData);
            }
        },

        /** 三選一：取消 */
        unsavedCancel() {
            this.showUnsavedModal = false;
            this._pendingNodeSwitch = null;
        },

        _doNodeSwitch: function (nodeId, nodeData) {
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

            var pageSc = nodeData.page_layout_secure_code;
            if (pageSc) {
                this._loadPageLayout(pageSc);
            } else {
                this.currentPageSc = null;
                this._setupEmptyCanvas();
            }

            // 顯示頁面樣式面板(選了頁面時)
            this.showProps = false;
            this.propsMode = 'style';
            this.showStylePanel = !!pageSc;
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

                // 載入頁面樣式(有值用頁面的，否則 fallback 到子系統預設)
                this._loadStyleConfig(data.data.style_config || {});

                this.editMode = detectedMode;
                this.dirty = false;

                // 套用樣式到 canvas (需等 DOM 更新)
                var self2 = this;
                this.$nextTick(function () { self2._applyStyleToCanvas(); });

                var self = this;
                this.$nextTick(function () {
                    if (detectedMode === 'grid') {
                        self._waitForEl('stu-grid-canvas', function () {
                            self._ensureEditor();
                            if (self._gridEditor) {
                                self._gridEditor.loadLayout(
                                    layout.version === 3 ? layout : self._emptyGridLayout()
                                );
                                // 載入 layout 後同步框線色與頁面底色
                                self._gridEditor.setBorderColor(self.styleConfig.bgColor || '');
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
                this._gridEditor.setBorderColor(this.styleConfig.bgColor || '');
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
                self.propsMode = 'style';
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

            // 點擊 widget 時切換設定面板; 點空白處回到頁面樣式
            var gsEl = this._gsGrid.el;
            gsEl.addEventListener('click', function (e) {
                var gsItem = e.target.closest('.grid-stack-item');
                if (gsItem) {
                    var wid = gsItem.getAttribute('gs-id');
                    if (wid && self._gsWidgetConfigs[wid]) {
                        self._gsSelectItem(wid);
                    }
                } else {
                    // 點擊空白區域 -> 回到頁面樣式面板
                    self.closeWidgetProps();
                }
            });
        },

        _gsAddWidget: function (type) {
            if (!this._gsGrid) return;
            var wid = 'w_' + Math.random().toString(36).slice(2, 8);
            var widgetConfig;

            if (type === 'SITEMENU') {
                widgetConfig = {
                    id: wid, type: 'SITEMENU', title: '',
                    startNodeSc: '', startLevel: 'children',
                    orientation: 'vertical',
                    bgColor: '#ffffff', itemBgColor: '#ffffff', itemTextColor: '#333333',
                    itemHoverBgColor: '#e9ecef', itemHoverTextColor: '#333333',
                    accentColor: '#e67e22',
                    itemGap: 6, hoverExpand: true, hoverExpandDelay: 300,
                    contextOutputs: [], contextInputs: [],
                };
            } else {
                widgetConfig = {
                    id: wid, type: type, viewCode: '', title: '',
                    pageSize: 10, showSearch: true, showPagination: true,
                    allowCreate: false, allowEdit: false, allowDelete: false,
                    contextOutputs: [], contextInputs: [],
                };
            }
            this._gsWidgetConfigs[wid] = widgetConfig;

            var gsItem = this._gsGrid.addWidget({
                x: 0, y: 0, w: 6, h: 4,
                id: wid,
                content: '',
            });

            var content = gsItem.querySelector('.grid-stack-item-content');
            if (content) {
                content.innerHTML = '';
                var widget = this._createWidgetInstance(content, widgetConfig);
                if (widget) {
                    widget.init();
                    this._gsWidgets[wid] = widget;
                }
            }

            this._gsSelectItem(wid);
            this.dirty = true;
        },

        /** 依 type 建立對應 widget instance */
        _createWidgetInstance: function (container, config) {
            if (config.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                return new SiteMenuWidget(container, config);
            }
            if (typeof DataListWidget !== 'undefined') {
                return new DataListWidget(container, config);
            }
            return null;
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
                    var widget = this._createWidgetInstance(content, fullConfig);
                    if (widget) {
                        widget.init();
                        this._gsWidgets[wid] = widget;
                    }
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
            this.settingWidgetType = widgetConfig.type || 'DATALIST';
            this.settingTitle = widgetConfig.title || '';
            this.settingContextOutputs = JSON.parse(JSON.stringify(widgetConfig.contextOutputs || []));
            this.settingContextInputs = JSON.parse(JSON.stringify(widgetConfig.contextInputs || []));

            if (this.settingWidgetType === 'SITEMENU') {
                // SITEMENU 專用欄位
                this.smStartNodeSc = widgetConfig.startNodeSc || '';
                this.smStartLevel = widgetConfig.startLevel || 'children';
                this.smOrientation = widgetConfig.orientation || 'vertical';
                this.smShowWelcome = widgetConfig.showWelcome !== false;
                this.smIconLayout = widgetConfig.iconLayout || 'top';
                this.smMenuHeight = widgetConfig.menuHeight || 'auto';
                this.smBgColor = widgetConfig.bgColor || '#ffffff';
                this.smItemBgColor = widgetConfig.itemBgColor || '#ffffff';
                this.smItemTextColor = widgetConfig.itemTextColor || '#333333';
                this.smItemHoverBgColor = widgetConfig.itemHoverBgColor || '#e9ecef';
                this.smItemHoverTextColor = widgetConfig.itemHoverTextColor || '#333333';
                this.smAccentColor = widgetConfig.accentColor || '#e67e22';
                this.smItemGap = widgetConfig.itemGap != null ? widgetConfig.itemGap : 6;
                this.smHoverExpand = widgetConfig.hoverExpand !== false;
                this.smHoverExpandDelay = widgetConfig.hoverExpandDelay || 300;
                return;
            }

            // DATALIST 專用欄位
            this.settingDataSource = widgetConfig.dataSource || '';
            this.settingTableName = widgetConfig.tableName || '';
            this.settingViewCode = widgetConfig.viewCode || '';
            this.settingPageSize = widgetConfig.pageSize || 10;
            this.settingShowSearch = widgetConfig.showSearch !== false;
            this.settingShowPagination = widgetConfig.showPagination !== false;
            this.settingAllowCreate = widgetConfig.allowCreate || false;
            this.settingAllowEdit = widgetConfig.allowEdit || false;
            this.settingAllowDelete = widgetConfig.allowDelete || false;

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

        /** 將巢狀 tree 攤平為帶 _depth 的陣列，供 select option 使用 */
        flattenTree: function (nodes, depth) {
            var result = [];
            if (!nodes) return result;
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                result.push({ secure_code: n.secure_code, name: n.name, icon: n.icon || '', _depth: depth });
                if (n.children && n.children.length > 0) {
                    result = result.concat(this.flattenTree(n.children, depth + 1));
                }
            }
            return result;
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
            if (this.settingWidgetType === 'SITEMENU') {
                this._applySiteMenuSettings();
                return;
            }

            // DATALIST: 先存回目前正在編輯的篩選角色
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

        _applySiteMenuSettings: function () {
            // 過濾空白的 context 項目 (SITEMENU 用 sourceField 而非 sourceColumn)
            var validOutputs = this.settingContextOutputs.filter(function (o) {
                return o.contextKey && o.contextKey.trim() && o.sourceField && o.sourceField.trim();
            });
            var validInputs = this.settingContextInputs.filter(function (i) {
                return i.contextKey && i.contextKey.trim();
            });

            var menuHeight = this.smMenuHeight;
            if (menuHeight !== 'auto') {
                var parsed = parseInt(menuHeight, 10);
                menuHeight = (parsed > 0) ? parsed : 'auto';
            }

            var widgetConfig = {
                title: this.settingTitle,
                startNodeSc: this.smStartNodeSc,
                startLevel: this.smStartLevel,
                orientation: this.smOrientation,
                showWelcome: this.smShowWelcome,
                iconLayout: this.smIconLayout,
                menuHeight: menuHeight,
                bgColor: this.smBgColor,
                itemBgColor: this.smItemBgColor,
                itemTextColor: this.smItemTextColor,
                itemHoverBgColor: this.smItemHoverBgColor,
                itemHoverTextColor: this.smItemHoverTextColor,
                accentColor: this.smAccentColor,
                itemGap: !isNaN(parseInt(this.smItemGap, 10)) ? parseInt(this.smItemGap, 10) : 6,
                hoverExpand: this.smHoverExpand,
                hoverExpandDelay: parseInt(this.smHoverExpandDelay, 10) || 300,
                contextOutputs: JSON.parse(JSON.stringify(validOutputs)),
                contextInputs: JSON.parse(JSON.stringify(validInputs)),
            };

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
                this.addNodeForm = {
                    name: 'welcome',
                    icon: '',
                    parent_sc: '',
                };
            } else {
                this.addNodeForm = {
                    name: '',
                    icon: '',
                    parent_sc: this.selectedNode
                        ? this.selectedNode.secure_code
                        : this.tree[0].secure_code,
                };
            }
            this.selectedTemplateSc = null;
            this._loadTemplates();
            this.showAddNodeModal = true;
        },

        async doAddNode() {
            var name = this.addNodeForm.name.trim();
            if (!name) { this.showToast('名稱為必填', 'error'); return; }

            try {
                var body = {
                    name: name,
                    node_type: 'page',
                    icon: this.addNodeForm.icon || null,
                    parent_secure_code: this.addNodeForm.parent_sc || null,
                };

                // 判斷是否使用模板
                var layoutJson, styleConfig;
                var tpl = null;
                if (this.selectedTemplateSc) {
                    for (var i = 0; i < this.templateList.length; i++) {
                        if (this.templateList[i].secure_code === this.selectedTemplateSc) {
                            tpl = this.templateList[i];
                            break;
                        }
                    }
                }
                if (tpl) {
                    layoutJson = tpl.layout_json;
                    styleConfig = tpl.style_config || {};
                } else {
                    layoutJson = this.editMode === 'grid'
                        ? { version: 3, mode: 'grid', gridSize: [4, 4], zones: [], widgets: [] }
                        : { version: 2, widgets: [] };
                    styleConfig = {};
                }

                var pagePayload = { name: name, layout_json: layoutJson };
                if (tpl) {
                    pagePayload.style_config = styleConfig;
                }

                var pageRes = await fetch('/api/nocode-builder/pages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(pagePayload),
                });
                var pageData = await pageRes.json();
                if (pageData.success) {
                    body.page_layout_secure_code = pageData.data.secure_code;
                } else {
                    this.showToast(pageData.error || '建立頁面佈局失敗', 'error');
                    return;
                }

                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map/nodes',
                    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
                );
                var data = await res.json();
                if (data.success) {
                    this.showAddNodeModal = false;
                    this.showToast(tpl ? '網頁已從模板建立' : '網頁已建立', 'success');
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
            if (!confirm('確定要刪除網頁「' + this.selectedNode.name + '」嗎?')) return;

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
                    this.showToast('網頁已刪除', 'success');
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
                    body: JSON.stringify({
                        layout_json: layoutJson,
                        style_config: this._buildStyleConfigForSave(),
                    }),
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

        previewPage: async function () {
            if (!this.subSystemSc) return;
            // 自動儲存後再預覽
            if (this.dirty && this.currentPageSc) {
                await this.savePage();
            }
            var url = '/nocode-builder/sub-systems/' + this.subSystemSc + '/portal';
            if (this.selectedNode) {
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
            this.showStylePanel = false;
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
        // Style Settings (頁面/子系統樣式)
        // ================================================================

        _emptyBgImage: function () {
            return { url: '', opacity: 30, fit: 'contain', position: 'center center' };
        },

        _loadStyleConfig: function (pageStyle) {
            var def = this._subSystemStyleConfig || {};
            var s = pageStyle || {};
            var srcBg = s.bgImage || def.bgImage || null;
            var bg = this._emptyBgImage();
            if (srcBg) {
                bg.url = srcBg.url || '';
                bg.opacity = srcBg.opacity != null ? srcBg.opacity : 30;
                bg.fit = srcBg.fit || 'contain';
                bg.position = srcBg.position || 'center center';
            }
            this.styleConfig = {
                bgColor: s.bgColor || def.bgColor || '',
                bgImage: bg,
                textColor: s.textColor || def.textColor || '',
                fontFamily: s.fontFamily || def.fontFamily || '',
                fontSize: s.fontSize || def.fontSize || null,
            };
        },

        _buildStyleConfigForSave: function () {
            var sc = this.styleConfig;
            var result = {};
            if (sc.bgColor) result.bgColor = sc.bgColor;
            if (sc.bgImage && sc.bgImage.url) {
                result.bgImage = {
                    url: sc.bgImage.url,
                    opacity: sc.bgImage.opacity != null ? sc.bgImage.opacity : 30,
                    fit: sc.bgImage.fit || 'contain',
                    position: sc.bgImage.position || 'center center',
                };
            }
            if (sc.textColor) result.textColor = sc.textColor;
            if (sc.fontFamily) result.fontFamily = sc.fontFamily;
            if (sc.fontSize) result.fontSize = sc.fontSize;
            return result;
        },

        onStyleChanged: function () {
            this.dirty = true;
            this._applyStyleToCanvas();
        },

        _applyStyleToCanvas: function () {
            // 即時套用樣式到 Canvas 設計區
            var gridCanvas = document.getElementById('stu-grid-canvas');
            var freeCanvas = document.getElementById('stu-gridstack');
            var targets = [gridCanvas, freeCanvas].filter(Boolean);
            var sc = this.styleConfig;

            targets.forEach(function (el) {
                // 底色
                el.style.backgroundColor = sc.bgColor || '';
                // 字色
                el.style.color = sc.textColor || '';
                // 字型
                el.style.fontFamily = sc.fontFamily || '';
                // 字型大小
                el.style.fontSize = sc.fontSize ? (sc.fontSize + 'px') : '';
            });

            // 同步框線顏色到 GridLayoutEditor，使框線與底色一致
            if (this._gridEditor && typeof this._gridEditor.setBorderColor === 'function') {
                this._gridEditor.setBorderColor(sc.bgColor || '');
            }

            // 底圖 (透過動態 style 注入)
            var styleId = 'stu-page-bg-style';
            var existing = document.getElementById(styleId);
            if (existing) existing.remove();

            if (sc.bgImage && sc.bgImage.url) {
                var opacity = (sc.bgImage.opacity != null ? sc.bgImage.opacity : 30) / 100;
                var fit = sc.bgImage.fit || 'contain';
                var pos = sc.bgImage.position || 'center center';
                var bgSize = fit;
                var bgRepeat = 'no-repeat';
                if (fit === 'tile') {
                    bgSize = 'auto';
                    bgRepeat = 'repeat';
                }

                var css = '#stu-grid-canvas, #stu-gridstack { position: relative; }\n'
                    + '#stu-grid-canvas::before, #stu-gridstack::before {\n'
                    + '  content: "";\n'
                    + '  position: absolute; top:0; left:0; right:0; bottom:0;\n'
                    + '  background-image: url(' + sc.bgImage.url + ');\n'
                    + '  background-size: ' + bgSize + ';\n'
                    + '  background-position: ' + pos + ';\n'
                    + '  background-repeat: ' + bgRepeat + ';\n'
                    + '  opacity: ' + opacity + ';\n'
                    + '  pointer-events: none;\n'
                    + '  z-index: 0;\n'
                    + '}\n';
                var styleEl = document.createElement('style');
                styleEl.id = styleId;
                styleEl.textContent = css;
                document.head.appendChild(styleEl);
            }
        },

        closeWidgetProps: function () {
            this.showProps = false;
            this.propsMode = 'style';
            this.showStylePanel = !!this.currentPageSc;
        },

        // --- 底圖操作 ---

        openBgGallery: async function () {
            await this._loadBgGallery();
            this.showBgGallery = true;
        },

        async _loadBgGallery() {
            try {
                var res = await fetch('/api/nocode-builder/backgrounds');
                var data = await res.json();
                if (data.success) this.bgGallery = data.data || [];
            } catch (e) {
                console.error('Load bg gallery failed:', e);
            }
        },

        selectBgFromGallery: function (bg) {
            this.styleConfig.bgImage.url = bg.url;
            this.showBgGallery = false;
            this.dirty = true;
        },

        async deleteBgFromGallery(sc) {
            if (!confirm('確定刪除此底圖?')) return;
            try {
                var res = await fetch('/api/nocode-builder/backgrounds/' + sc, { method: 'DELETE' });
                var data = await res.json();
                if (data.success) {
                    this.bgGallery = this.bgGallery.filter(function (b) { return b.secure_code !== sc; });
                    this.showToast('底圖已刪除', 'success');
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
            }
        },

        async uploadBgImage(evt) {
            var file = evt.target.files && evt.target.files[0];
            if (!file) return;
            evt.target.value = '';
            await this._doUploadBg(file);
        },

        async uploadBgFromGallery(evt) {
            var file = evt.target.files && evt.target.files[0];
            if (!file) return;
            evt.target.value = '';
            var bg = await this._doUploadBg(file);
            if (bg) {
                this.bgGallery.unshift(bg);
            }
        },

        async _doUploadBg(file) {
            var formData = new FormData();
            formData.append('file', file);
            try {
                var res = await fetch('/api/nocode-builder/backgrounds/upload', {
                    method: 'POST',
                    body: formData,
                });
                var data = await res.json();
                if (data.success) {
                    var bg = data.data;
                    // 自動套用到目前頁面
                    this.styleConfig.bgImage.url = bg.url;
                    this.dirty = true;
                    this.showToast('底圖上傳成功', 'success');
                    return bg;
                } else {
                    this.showToast(data.error || '上傳失敗', 'error');
                    return null;
                }
            } catch (e) {
                this.showToast('上傳失敗', 'error');
                return null;
            }
        },

        clearBgImage: function () {
            this.styleConfig.bgImage = this._emptyBgImage();
            this.dirty = true;
            this._applyStyleToCanvas();
        },

        // --- 子系統操作 ---

        async setAsSubSystemDefault() {
            var style = this._buildStyleConfigForSave();
            if (!confirm('將目前頁面樣式設為子系統預設?')) return;
            try {
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/style', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ style_config: style }),
                });
                var data = await res.json();
                if (data.success) {
                    this._subSystemStyleConfig = style;
                    this.showToast('已設為子系統預設', 'success');
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async applyStyleToAllPages() {
            var style = this._buildStyleConfigForSave();
            if (!confirm('將目前頁面樣式覆蓋到此子系統的所有頁面? 此操作不可復原。')) return;
            try {
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/style/apply-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ style_config: style }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '已套用', 'success');
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        // ================================================================
        // Template (模板)
        // ================================================================

        openSaveTemplate: function () {
            if (!this.currentPageSc) {
                this.showToast('請先選擇一個頁面', 'error');
                return;
            }
            this.saveTemplateForm = { name: '', description: '' };
            this.showSaveTemplateModal = true;
        },

        async doSaveTemplate() {
            var name = this.saveTemplateForm.name.trim();
            if (!name) { this.showToast('模板名稱為必填', 'error'); return; }

            this.savingTemplate = true;
            try {
                var layoutJson;
                if (this.editMode === 'grid') {
                    layoutJson = this._gridEditor ? this._gridEditor.toLayoutJson() : this._emptyGridLayout();
                } else {
                    layoutJson = this._buildGridStackLayoutJson();
                }
                var styleConfig = this._buildStyleConfigForSave();
                var thumbnailSvg = this._generateThumbnailSvg(layoutJson, styleConfig);

                var res = await fetch('/api/nocode-builder/templates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name,
                        description: this.saveTemplateForm.description.trim(),
                        layout_json: layoutJson,
                        style_config: styleConfig,
                        thumbnail_svg: thumbnailSvg,
                    }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showSaveTemplateModal = false;
                    this.showToast('模板已儲存', 'success');
                } else {
                    this.showToast(data.error || '儲存模板失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存模板失敗: ' + e.message, 'error');
            } finally {
                this.savingTemplate = false;
            }
        },

        async _loadTemplates() {
            this.loadingTemplates = true;
            try {
                var res = await fetch('/api/nocode-builder/templates');
                var data = await res.json();
                if (data.success) {
                    this.templateList = data.data || [];
                }
            } catch (e) {
                console.error('Load templates failed:', e);
            } finally {
                this.loadingTemplates = false;
            }
        },

        async deleteTemplate(sc) {
            if (!confirm('確定要刪除此模板?')) return;
            try {
                var res = await fetch('/api/nocode-builder/templates/' + sc, { method: 'DELETE' });
                var data = await res.json();
                if (data.success) {
                    this.templateList = this.templateList.filter(function (t) { return t.secure_code !== sc; });
                    this.showToast('模板已刪除', 'success');
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗', 'error');
            }
        },

        selectTemplate: function (sc) {
            this.selectedTemplateSc = this.selectedTemplateSc === sc ? null : sc;
        },

        /**
         * 根據 layout_json + style_config 產生 SVG 縮圖
         */
        _generateThumbnailSvg: function (layoutJson, styleConfig) {
            var W = 160, H = 100;
            var bgColor = (styleConfig && styleConfig.bgColor) || '#ffffff';
            var rects = '';

            if (layoutJson.mode === 'grid' && layoutJson.zones && layoutJson.zones.length > 0) {
                // Grid mode: 依照 zones 繪製區塊
                var gs = layoutJson.gridSize || [4, 4];
                var rows = gs[0] || 4, cols = gs[1] || 4;
                var pad = 3, cellW = (W - pad * 2) / cols, cellH = (H - pad * 2) / rows;
                var colors = ['#4a90d9', '#50b86c', '#e67e22', '#9b59b6', '#e74c3c', '#1abc9c'];
                for (var i = 0; i < layoutJson.zones.length; i++) {
                    var z = layoutJson.zones[i];
                    var x = pad + (z.col - 1) * cellW + 1;
                    var y = pad + (z.row - 1) * cellH + 1;
                    var w = z.colSpan * cellW - 2;
                    var h = z.rowSpan * cellH - 2;
                    var hasWidget = false;
                    if (layoutJson.widgets) {
                        for (var j = 0; j < layoutJson.widgets.length; j++) {
                            if (layoutJson.widgets[j].zoneId === z.id) { hasWidget = true; break; }
                        }
                    }
                    var fill = hasWidget ? colors[i % colors.length] : '#dde4ed';
                    rects += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h +
                             '" rx="2" fill="' + fill + '" opacity="0.7"/>';
                }
            } else if (layoutJson.widgets && layoutJson.widgets.length > 0 && layoutJson.version === 2) {
                // Free mode: 依照 widget 位置繪製
                var maxX = 12, maxY = 1;
                for (var i = 0; i < layoutJson.widgets.length; i++) {
                    var wy = (layoutJson.widgets[i].y || 0) + (layoutJson.widgets[i].h || 1);
                    if (wy > maxY) maxY = wy;
                }
                var pad = 3, cellW = (W - pad * 2) / maxX, cellH = (H - pad * 2) / maxY;
                var colors = ['#4a90d9', '#50b86c', '#e67e22', '#9b59b6', '#e74c3c', '#1abc9c'];
                for (var i = 0; i < layoutJson.widgets.length; i++) {
                    var wi = layoutJson.widgets[i];
                    var x = pad + (wi.x || 0) * cellW + 1;
                    var y = pad + (wi.y || 0) * cellH + 1;
                    var w = (wi.w || 1) * cellW - 2;
                    var h = (wi.h || 1) * cellH - 2;
                    rects += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h +
                             '" rx="2" fill="' + colors[i % colors.length] + '" opacity="0.7"/>';
                }
            } else {
                // 空白頁面
                rects = '<text x="' + (W / 2) + '" y="' + (H / 2 + 4) + '" text-anchor="middle" ' +
                        'font-size="12" fill="#bbb" font-family="sans-serif">空白</text>';
            }

            return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '">' +
                   '<rect width="' + W + '" height="' + H + '" rx="4" fill="' + bgColor + '"/>' +
                   '<rect width="' + W + '" height="' + H + '" rx="4" fill="none" stroke="#ddd" stroke-width="1"/>' +
                   rects + '</svg>';
        },

        // ================================================================
        // Toast
        // ================================================================

        showToast: function (message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function () { self.toast.show = false; }, 3000);
        },

        // ================================================================
        // Icon Picker (Site Map 節點圖示)
        // ================================================================

        openNodeIconPicker: function () {
            if (!this.selectedNode) return;
            this._iconTarget = 'node';
            this._ip_selectedIcon = this.selectedNode.icon || '';
            this._ip_activeCategory = 'business';
            this._ip_search = '';
            this._ip_show = true;
        },

        openAddNodeIconPicker: function () {
            this._iconTarget = 'add';
            this._ip_selectedIcon = this.addNodeForm.icon || '';
            this._ip_activeCategory = 'business';
            this._ip_search = '';
            this._ip_show = true;
        },

        ipOpen: function () {
            this._ip_show = true;
            this._ip_search = '';
        },

        ipClose: function () {
            this._ip_show = false;
        },

        ipSelect: function (iconClass) {
            this._ip_selectedIcon = iconClass;
            if (this._iconTarget === 'add') {
                this.addNodeForm.icon = iconClass;
            } else if (this._iconTarget === 'item') {
                this._saveItemNodeIcon(this._iconEditNodeSc, iconClass);
            } else if (this.selectedNode) {
                this.selectedNode.icon = iconClass;
                this._saveNodeIcon(iconClass);
            }
            this.ipClose();
        },

        ipClear: function () {
            this._ip_selectedIcon = '';
            if (this._iconTarget === 'add') {
                this.addNodeForm.icon = '';
            } else if (this._iconTarget === 'item') {
                this._saveItemNodeIcon(this._iconEditNodeSc, '');
            } else if (this.selectedNode) {
                this.selectedNode.icon = '';
                this._saveNodeIcon('');
            }
            this.ipClose();
        },

        clearNodeIcon: function () {
            if (!this.selectedNode) return;
            this.selectedNode.icon = '';
            this._saveNodeIcon('');
        },

        _saveNodeIcon: async function (iconClass) {
            if (!this.selectedNode) return;
            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + this.selectedNode.secure_code,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ icon: iconClass || null }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    this._initSiteMapTree();
                } else {
                    this.showToast(data.error || '圖示儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('圖示儲存失敗: ' + e.message, 'error');
            }
        },

        // ================================================================
        // Icon Picker (SITEMENU 節點圖示 - 設定面板用)
        // ================================================================

        /** 遞迴搜尋 tree 中的節點 */
        _findTreeNode: function (nodes, sc) {
            for (var i = 0; i < nodes.length; i++) {
                if (nodes[i].secure_code === sc) return nodes[i];
                if (nodes[i].children && nodes[i].children.length > 0) {
                    var found = this._findTreeNode(nodes[i].children, sc);
                    if (found) return found;
                }
            }
            return null;
        },

        /** 從 SITEMENU 設定面板打開 icon picker */
        openItemIconPicker: function (nodeSc) {
            var node = this._findTreeNode(this.tree, nodeSc);
            if (!node) return;
            this._iconTarget = 'item';
            this._iconEditNodeSc = nodeSc;
            this._ip_selectedIcon = node.icon || '';
            this._ip_activeCategory = 'business';
            this._ip_search = '';
            this._ip_show = true;
        },

        /** 從 SITEMENU 設定面板清除節點圖示 */
        clearItemIcon: function (nodeSc) {
            this._saveItemNodeIcon(nodeSc, '');
        },

        /** 儲存節點圖示 (SITEMENU 設定面板用) */
        _saveItemNodeIcon: async function (nodeSc, iconClass) {
            if (!nodeSc) return;
            try {
                var res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + nodeSc,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ icon: iconClass || null }),
                    }
                );
                var data = await res.json();
                if (data.success) {
                    // 同步更新 selectedNode (若正在編輯同一節點)
                    if (this.selectedNode && this.selectedNode.secure_code === nodeSc) {
                        this.selectedNode.icon = iconClass;
                    }
                    await this._loadTree();
                    this._initSiteMapTree();
                    this.showToast('圖示已更新', 'success');
                } else {
                    this.showToast(data.error || '圖示儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('圖示儲存失敗: ' + e.message, 'error');
            }
        },

        ipGetCategories: function () {
            return typeof ICON_CATEGORIES !== 'undefined' ? ICON_CATEGORIES : [];
        },

        ipGetIcons: function () {
            var cats = this.ipGetCategories();
            var active = this._ip_activeCategory;
            var cat = null;
            for (var i = 0; i < cats.length; i++) {
                if (cats[i].name === active) { cat = cats[i]; break; }
            }
            var icons = cat ? cat.icons : [];
            var search = (this._ip_search || '').trim().toLowerCase();
            if (!search) return icons;
            return icons.filter(function (ic) { return ic.toLowerCase().indexOf(search) >= 0; });
        },

        ipSetCategory: function (name) {
            this._ip_activeCategory = name;
        },
    };
}
