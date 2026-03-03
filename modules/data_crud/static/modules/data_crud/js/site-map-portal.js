/**
 * site-map-portal.js -- 用戶 Portal V2
 * 左側 Wunderbaum 樹狀選單 + 右側 GridStack 動態頁面載入
 */
function siteMapPortal() {
    return {
        loading: true,
        error: '',
        subSystemSc: '',
        subSystemName: '',
        roleType: '',
        isAdmin: false,
        tree: [],
        breadcrumb: [],

        // 頁面載入狀態
        currentNode: null,
        pageLoading: false,
        pageError: '',

        // GridStack 和 widgets
        _grid: null,
        _widgets: {},
        _wbTree: null,

        _roleLabels: {
            'MANAGER': '團長',
            'DEPUTY': '副團長',
            'PROXY1': '代理人(一)',
            'PROXY2': '代理人(二)',
            'MEMBER': '團員',
        },

        get roleLabel() {
            return this._roleLabels[this.roleType] || this.roleType || '';
        },

        async init() {
            var config = window.__PORTAL_CONFIG || {};
            this.subSystemSc = config.subSystemSc || '';
            this.subSystemName = config.subSystemName || '';

            if (!this.subSystemSc) {
                this.error = '未指定子系統';
                this.loading = false;
                return;
            }

            try {
                var res = await fetch('/api/data-crud/sub-systems/' + this.subSystemSc + '/site-map/user-tree');
                var data = await res.json();
                if (!data.success) {
                    this.error = data.error || '載入失敗';
                    this.loading = false;
                    return;
                }

                this.roleType = data.data.role_type || '';
                this.isAdmin = data.data.is_admin || false;
                this.tree = data.data.tree || [];
            } catch (e) {
                this.error = '載入失敗: ' + e.message;
            }

            this.loading = false;
            this._renderTree();
        },

        // ===== Wunderbaum 樹選單 =====

        _treeToSource(nodes) {
            var self = this;
            return nodes.map(function(n) {
                var icon = n.node_type === 'folder' ? 'bi bi-folder' : 'bi bi-file-earmark';
                if (n.icon) icon = n.icon;
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

        _renderTree() {
            var self = this;
            this.$nextTick(function() {
                var el = document.getElementById('sp2-tree');
                if (!el) return;
                if (typeof mar10 === 'undefined' || !mar10.Wunderbaum) {
                    console.error('Wunderbaum not loaded');
                    return;
                }

                var source = self._treeToSource(self.tree);

                self._wbTree = new mar10.Wunderbaum({
                    element: el,
                    id: 'sp2-nav',
                    source: source,
                    selectMode: 'single',

                    activate: function(e) {
                        var d = e.node.data;
                        if (d.node_type === 'page') {
                            self._buildBreadcrumb(e.node);
                            self.loadPage(d);
                        }
                    },
                });
            });
        },

        _buildBreadcrumb(wbNode) {
            var parts = [];
            var n = wbNode;
            while (n && n.key !== '_root') {
                parts.unshift(n.title);
                n = n.parent;
            }
            this.breadcrumb = parts;
        },

        // ===== 頁面載入 =====

        async loadPage(nodeData) {
            this._destroyCurrentPage();
            this.currentNode = nodeData;
            this.pageLoading = true;
            this.pageError = '';

            var pageSc = nodeData.page_layout_secure_code;
            if (!pageSc) {
                this.pageError = '此節點未連結頁面';
                this.pageLoading = false;
                return;
            }

            try {
                // 並行: 取得 node context + page layout
                var ctxPromise = fetch(
                    '/api/data-crud/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + nodeData.secure_code + '/context'
                ).then(function(r) { return r.json(); });

                var layoutPromise = fetch(
                    '/api/data-crud/pages/' + pageSc
                ).then(function(r) { return r.json(); });

                var results = await Promise.all([ctxPromise, layoutPromise]);
                var ctxData = results[0];
                var layoutData = results[1];

                if (!ctxData.success) {
                    this.pageError = ctxData.error || '取得權限失敗';
                    this.pageLoading = false;
                    return;
                }
                if (!layoutData.success) {
                    this.pageError = layoutData.error || '載入頁面失敗';
                    this.pageLoading = false;
                    return;
                }

                var ctx = ctxData.data;
                var layout = layoutData.data.layout_json || {};

                // 向下相容: 舊格式 bindings
                layout = this._migrateBindingsToContext(layout);
                var items = layout.widgets || [];

                this._initGrid();
                this._renderLayout(items, ctx);
            } catch (e) {
                this.pageError = '載入頁面失敗: ' + e.message;
            } finally {
                this.pageLoading = false;
            }
        },

        _destroyCurrentPage() {
            // 銷毀 widgets
            for (var id in this._widgets) {
                if (this._widgets[id] && typeof this._widgets[id].destroy === 'function') {
                    try { this._widgets[id].destroy(); } catch (e) { /* ignore */ }
                }
            }
            this._widgets = {};

            // 銷毀 GridStack
            if (this._grid) {
                try { this._grid.destroy(false); } catch (e) { /* ignore */ }
                this._grid = null;
            }

            // 清空 DOM
            var gsEl = document.querySelector('.sp2-content .grid-stack');
            if (gsEl) gsEl.innerHTML = '';

            // Reset PageContext
            if (typeof PageContext !== 'undefined') {
                PageContext.reset();
            }

            this.currentNode = null;
            this.pageError = '';
        },

        _initGrid() {
            this._grid = GridStack.init({
                column: 12,
                cellHeight: 60,
                margin: 8,
                staticGrid: true,
                float: true,
            }, '.sp2-content .grid-stack');
        },

        _renderLayout(items, ctx) {
            var self = this;
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var id = item.id || ('v_' + Math.random().toString(36).slice(2, 8));
                var gsItem = this._grid.addWidget({
                    x: item.x, y: item.y,
                    w: item.w || 6, h: item.h || 4,
                    id: id, content: ''
                });

                var widgetConfig = item.widget;
                if (widgetConfig && widgetConfig.viewCode) {
                    widgetConfig.id = id;

                    // 套用節點 CRUD 覆蓋
                    var crud = ctx.crud || {};
                    if ('create' in crud) widgetConfig.allowCreate = crud.create;
                    if ('edit' in crud) widgetConfig.allowEdit = crud.edit;
                    if ('delete' in crud) widgetConfig.allowDelete = crud.delete;

                    // 套用節點資料篩選
                    var dataFilters = ctx.data_filters || {};
                    if (Object.keys(dataFilters).length > 0) {
                        widgetConfig._subSystemFilters = dataFilters;
                    }

                    // 注入 site map context headers
                    widgetConfig._siteMapNodeSc = ctx.node_secure_code;
                    widgetConfig._subSystemSc = self.subSystemSc;

                    var content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '';
                        var widget = new DataListWidget(content, widgetConfig);
                        widget.init();
                        self._widgets[id] = widget;
                    }
                } else {
                    var content2 = gsItem.querySelector('.grid-stack-item-content');
                    if (content2) {
                        content2.innerHTML = '<div class="dlw-root"><div class="dlw-empty">未設定資料來源</div></div>';
                    }
                }
            }
        },

        /**
         * 向下相容: bindings → contextInputs/contextOutputs
         * (復用 lab-viewer.js 邏輯)
         */
        _migrateBindingsToContext(layout) {
            if (layout.version === 2) return layout;

            var bindings = layout.bindings || [];
            if (bindings.length === 0) {
                layout.version = 2;
                return layout;
            }

            var widgetMap = {};
            var widgets = layout.widgets || [];
            for (var i = 0; i < widgets.length; i++) {
                var w = widgets[i];
                if (w.widget) {
                    if (!w.widget.contextOutputs) w.widget.contextOutputs = [];
                    if (!w.widget.contextInputs) w.widget.contextInputs = [];
                    widgetMap[w.id] = w.widget;
                }
            }

            for (var j = 0; j < bindings.length; j++) {
                var b = bindings[j];
                if (b.action !== 'filter' || !b.mapping) continue;

                var sourceWidget = widgetMap[b.source];
                var targetWidget = widgetMap[b.target];
                if (!sourceWidget || !targetWidget) continue;

                for (var targetCol in b.mapping) {
                    var sourceCol = b.mapping[targetCol];
                    var contextKey = b.source + '_' + sourceCol;

                    var hasOutput = sourceWidget.contextOutputs.some(function(o) {
                        return o.contextKey === contextKey && o.event === b.event;
                    });
                    if (!hasOutput) {
                        sourceWidget.contextOutputs.push({
                            event: b.event,
                            contextKey: contextKey,
                            sourceColumn: sourceCol,
                        });
                    }

                    var hasInput = targetWidget.contextInputs.some(function(inp) {
                        return inp.contextKey === contextKey && inp.filterColumn === targetCol;
                    });
                    if (!hasInput) {
                        targetWidget.contextInputs.push({
                            contextKey: contextKey,
                            filterColumn: targetCol,
                        });
                    }
                }
            }

            delete layout.bindings;
            layout.version = 2;
            return layout;
        }
    };
}
