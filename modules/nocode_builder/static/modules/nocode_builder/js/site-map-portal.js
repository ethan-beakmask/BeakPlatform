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
                var res = await fetch('/api/nocode-builder/sub-systems/' + this.subSystemSc + '/site-map/user-tree');
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
                    // 用 refRaw 保存原始資料，避免被 Wunderbaum 內部 data 屬性覆蓋
                    refRaw: JSON.parse(JSON.stringify(n)),
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
                        var d = (e.node.data && e.node.data.refRaw) || e.node.data || {};
                        if (d.node_type === 'page') {
                            self._buildBreadcrumb(e.node);
                            self.loadPage(d);
                        }
                    },
                });

                // 樹建立完成後自動導航
                self._autoNavigate();
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

            // 更新瀏覽器標籤標題
            document.title = this.subSystemName + ' - ' + (nodeData.name || '');

            var pageSc = nodeData.page_layout_secure_code;
            if (!pageSc) {
                this.pageError = '此節點未連結頁面';
                this.pageLoading = false;
                return;
            }

            try {
                // 並行: 取得 node context + page layout
                var ctxPromise = fetch(
                    '/api/nocode-builder/sub-systems/' + this.subSystemSc
                    + '/site-map/nodes/' + nodeData.secure_code + '/context'
                ).then(function(r) { return r.json(); });

                var layoutPromise = fetch(
                    '/api/nocode-builder/pages/' + pageSc
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

                // 套用頁面樣式
                this._applyPageStyle(layoutData.data.style_config || {});

                // v3 Grid 模式 or v2 GridStack 模式
                if (layout.version === 3 && layout.mode === 'grid') {
                    this._renderGridLayout(layout, ctx);
                } else {
                    // 向下相容: 舊格式 bindings
                    layout = this._migrateBindingsToContext(layout);
                    var items = layout.widgets || [];
                    this._initGrid();
                    this._renderLayout(items, ctx);
                }
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

            // 清空 DOM (grid-stack 或 portal-grid)
            var gsEl = document.querySelector('.sp2-content .grid-stack');
            if (gsEl) gsEl.innerHTML = '';
            var pgEl = document.querySelector('.sp2-content .portal-grid');
            if (pgEl) {
                pgEl.className = 'grid-stack';
                pgEl.removeAttribute('style');
                pgEl.innerHTML = '';
            }

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
                var content = gsItem.querySelector('.grid-stack-item-content');

                if (widgetConfig && widgetConfig.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                    widgetConfig.id = id;
                    widgetConfig._subSystemSc = self.subSystemSc;
                    widgetConfig._siteMapNodeSc = (self.currentNode && self.currentNode.secure_code) || '';
                    widgetConfig._onNavigate = function (nodeData) { self.loadPage(nodeData); };
                    if (content) {
                        content.innerHTML = '';
                        var smw = new SiteMenuWidget(content, widgetConfig);
                        smw.init();
                        self._widgets[id] = smw;
                    }
                } else if (widgetConfig && widgetConfig.viewCode) {
                    widgetConfig.id = id;
                    self._applyWidgetPermissions(widgetConfig, ctx);
                    if (content) {
                        content.innerHTML = '';
                        var widget = new DataListWidget(content, widgetConfig);
                        widget.init();
                        self._widgets[id] = widget;
                    }
                } else {
                    if (content) {
                        content.innerHTML = '<div class="dlw-root"><div class="dlw-empty">未設定資料來源</div></div>';
                    }
                }
            }
        },

        // ===== v3 Grid 佈局渲染 =====

        _renderGridLayout(layout, ctx) {
            var self = this;
            var gridSize = layout.gridSize || [4, 4];
            var zones = layout.zones || [];
            var widgets = layout.widgets || [];

            // 建立 zone -> widget 映射
            var widgetByZone = {};
            for (var i = 0; i < widgets.length; i++) {
                widgetByZone[widgets[i].zoneId] = widgets[i].widget;
            }

            // 找到渲染容器 (替代 grid-stack)
            var container = document.querySelector('.sp2-content .grid-stack');
            if (!container) return;
            container.innerHTML = '';
            container.className = 'portal-grid';

            // 使用 colWidths/rowHeights (如果有)，否則用均等 fr
            if (layout.colWidths && layout.colWidths.length > 0) {
                container.style.gridTemplateColumns = layout.colWidths.map(function(w) { return w + 'fr'; }).join(' ');
            } else {
                container.style.gridTemplateColumns = 'repeat(' + gridSize[1] + ', 1fr)';
            }
            if (layout.rowHeights && layout.rowHeights.length > 0) {
                container.style.gridTemplateRows = layout.rowHeights.map(function(h) { return 'minmax(120px, ' + h + 'fr)'; }).join(' ');
            } else {
                container.style.gridTemplateRows = 'repeat(' + gridSize[0] + ', minmax(120px, 1fr))';
            }

            for (var j = 0; j < zones.length; j++) {
                var zone = zones[j];
                var cell = document.createElement('div');
                cell.className = 'portal-grid-cell';
                cell.style.gridRow = zone.row + ' / span ' + zone.rowSpan;
                cell.style.gridColumn = zone.col + ' / span ' + zone.colSpan;

                var widgetConfig = widgetByZone[zone.id];
                if (widgetConfig && widgetConfig.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                    var wid = widgetConfig.id || ('v_' + Math.random().toString(36).slice(2, 8));
                    widgetConfig.id = wid;
                    widgetConfig._subSystemSc = self.subSystemSc;
                    widgetConfig._siteMapNodeSc = (self.currentNode && self.currentNode.secure_code) || '';
                    widgetConfig._onNavigate = function (nodeData) { self.loadPage(nodeData); };
                    var smw = new SiteMenuWidget(cell, widgetConfig);
                    smw.init();
                    self._widgets[wid] = smw;
                } else if (widgetConfig && widgetConfig.viewCode) {
                    var wid = widgetConfig.id || ('v_' + Math.random().toString(36).slice(2, 8));
                    widgetConfig.id = wid;
                    self._applyWidgetPermissions(widgetConfig, ctx);
                    var widget = new DataListWidget(cell, widgetConfig);
                    widget.init();
                    self._widgets[wid] = widget;
                } else {
                    cell.innerHTML = '<div class="dlw-root"><div class="dlw-empty">未設定資料來源</div></div>';
                }

                container.appendChild(cell);
            }

            if (zones.length === 0) {
                container.innerHTML = '<div style="grid-column:1/-1; text-align:center; padding:40px; color:#999;">此頁面尚未配置佈局</div>';
            }
        },

        // ===== Widget 層級權限 (Phase 3) =====

        /**
         * 套用 widget 層級的 CRUD 權限和資料篩選
         *
         * 優先順序:
         *   1. widget.rolePermissions[roleType] — widget 層級明確設定
         *   2. ctx.crud / ctx.data_filters — 節點層級 (backward compat)
         *   3. 管理層預設全權，其他角色預設唯讀
         */
        _applyWidgetPermissions(widgetConfig, ctx) {
            var roleType = this.roleType;
            var isAdmin = this.isAdmin;

            // --- CRUD 權限 ---
            var rolePerm = (widgetConfig.rolePermissions || {})[roleType];
            if (rolePerm) {
                // Widget 層級: 明確按角色設定
                widgetConfig.allowCreate = !!rolePerm.create;
                widgetConfig.allowEdit = !!rolePerm.edit;
                widgetConfig.allowDelete = !!rolePerm.delete;
            } else if (widgetConfig.rolePermissions) {
                // rolePermissions 存在但無此角色的設定
                if (isAdmin) {
                    widgetConfig.allowCreate = true;
                    widgetConfig.allowEdit = true;
                    widgetConfig.allowDelete = true;
                } else {
                    widgetConfig.allowCreate = false;
                    widgetConfig.allowEdit = false;
                    widgetConfig.allowDelete = false;
                }
            } else {
                // 無 rolePermissions → fallback 到節點層級
                var crud = ctx.crud || {};
                if ('create' in crud) widgetConfig.allowCreate = crud.create;
                if ('edit' in crud) widgetConfig.allowEdit = crud.edit;
                if ('delete' in crud) widgetConfig.allowDelete = crud.delete;
            }

            // --- 資料篩選 ---
            var roleFilter = (widgetConfig.roleFilters || {})[roleType];
            if (roleFilter && Object.keys(roleFilter).length > 0) {
                // Widget 層級: 用 resolved_vars 替換變數
                widgetConfig._subSystemFilters = this._resolveFilterVars(
                    roleFilter, ctx.resolved_vars || {}
                );
            } else if (!widgetConfig.roleFilters) {
                // 無 roleFilters → fallback 到節點層級
                var dataFilters = ctx.data_filters || {};
                if (Object.keys(dataFilters).length > 0) {
                    widgetConfig._subSystemFilters = dataFilters;
                }
            }
            // roleFilters 存在但無此角色 → 無額外篩選

            // 注入 site map context headers
            widgetConfig._siteMapNodeSc = ctx.node_secure_code;
            widgetConfig._subSystemSc = this.subSystemSc;
        },

        /**
         * 前端變數替換 (對應後端 resolve_filter_variables)
         */
        _resolveFilterVars(filters, resolvedVars) {
            var result = {};
            for (var col in filters) {
                var val = filters[col];
                if (typeof val === 'string' && val.charAt(0) === '$'
                        && resolvedVars[val] !== undefined) {
                    result[col] = resolvedVars[val];
                } else {
                    result[col] = val;
                }
            }
            return result;
        },

        // ===== 自動導航 =====

        /**
         * 自動導航: 優先到 ?page= 指定的頁面，否則到 welcome (根頁面)
         */
        _autoNavigate: function () {
            if (!this._wbTree || this.tree.length === 0) return;

            var self = this;
            var params = new URLSearchParams(window.location.search);
            var targetSc = params.get('page');

            // 嘗試導航到指定頁面
            if (targetSc) {
                var wbNode = self._wbTree.findFirst(function (n) {
                    return n.key === targetSc;
                });
                if (wbNode) {
                    wbNode.setActive(true);
                    return;
                }
            }

            // 預設: 導航到 welcome (第一個根 page 節點)
            var welcomeSc = self._findWelcomeSc(self.tree);
            if (welcomeSc) {
                var wbWelcome = self._wbTree.findFirst(function (n) {
                    return n.key === welcomeSc;
                });
                if (wbWelcome) {
                    wbWelcome.setActive(true);
                }
            }
        },

        /**
         * 找到根頁面 (welcome) 的 secure_code
         */
        _findWelcomeSc: function (nodes) {
            for (var i = 0; i < nodes.length; i++) {
                if (nodes[i].node_type === 'page') return nodes[i].secure_code;
            }
            return nodes.length > 0 ? nodes[0].secure_code : null;
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
        },

        _applyPageStyle: function (styleConfig) {
            var sc = styleConfig || {};
            var content = document.querySelector('.sp2-content');
            if (!content) return;

            content.style.backgroundColor = sc.bgColor || '';
            content.style.color = sc.textColor || '';
            content.style.fontFamily = sc.fontFamily || '';
            content.style.fontSize = sc.fontSize ? (sc.fontSize + 'px') : '';

            // 底圖
            var styleId = 'sp2-page-bg-style';
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
                var css = '.sp2-content { position: relative; }\n'
                    + '.sp2-content::before {\n'
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
        }
    };
}
