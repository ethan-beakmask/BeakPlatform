/**
 * Lab Viewer - 用戶模式佈局渲染
 *
 * 從 API 載入頁面佈局 JSON（DB 持久化），
 * 以 GridStack staticGrid 模式渲染，用戶不能修改佈局結構。
 * Widget 透過 PageContext 共享狀態自動建立連線。
 */
function labViewer() {
    return {
        grid: null,
        widgets: {},
        error: '',
        pageName: '',
        subCtx: null,  // 子系統 context

        async init() {
            const config = window.__PAGE_CONFIG || {};
            if (!config.secureCode) {
                this.error = '未指定頁面';
                return;
            }

            // 子系統 context (server-side 注入)
            this.subCtx = (config.subSystemContext && config.subSystemContext.sub_sc)
                ? config.subSystemContext
                : null;

            // 從 API 載入佈局
            try {
                const res = await fetch('/bp/api/nocode-builder/pages/' + config.secureCode);
                const data = await res.json();
                if (!data.success) {
                    this.error = '載入失敗: ' + (data.error || '');
                    return;
                }

                this.pageName = data.data.name || '';
                let layout = data.data.layout_json || {};

                // 向下相容: 舊格式 bindings → contextInputs/contextOutputs
                layout = this._migrateBindingsToContext(layout);

                const items = layout.widgets || [];

                this._initGrid();
                this._renderLayout(items);
            } catch (e) {
                this.error = '載入失敗: ' + e.message;
            }
        },

        _initGrid() {
            this.grid = GridStack.init({
                column: 12,
                cellHeight: 60,
                margin: 8,
                staticGrid: true,
                float: true,
            }, '.grid-stack');
        },

        _renderLayout(items) {
            for (const item of items) {
                const id = item.id || ('v_' + Math.random().toString(36).slice(2, 8));
                const gsItem = this.grid.addWidget({
                    x: item.x, y: item.y,
                    w: item.w || 6, h: item.h || 4,
                    id: id, content: ''
                });

                const widgetConfig = item.widget;
                if (widgetConfig && widgetConfig.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                    widgetConfig.id = id;
                    const content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '';
                        const smw = new SiteMenuWidget(content, widgetConfig);
                        smw.init();
                        this.widgets[id] = smw;
                    }
                } else if (widgetConfig && widgetConfig.type === 'FORMGRID' && typeof FormGridWidget !== 'undefined') {
                    widgetConfig.id = id;
                    if (this.subCtx) {
                        widgetConfig._subSystemSc = this.subCtx.subSystemSc || '';
                        widgetConfig._siteMapNodeSc = this.subCtx.siteMapNodeSc || '';
                    }
                    const content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '';
                        const fgw = new FormGridWidget(content, widgetConfig);
                        fgw.init();
                        this.widgets[id] = fgw;
                    }
                } else if (widgetConfig && widgetConfig.viewCode) {
                    widgetConfig.id = id;

                    // 子系統 context: 套用 CRUD 覆蓋和資料篩選
                    if (this.subCtx) {
                        this._applySubSystemOverrides(widgetConfig);
                    }

                    const content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '';
                        const widget = new DataListWidget(content, widgetConfig);
                        widget.init();
                        this.widgets[id] = widget;
                    }
                } else {
                    const content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '<div class="dlw-root"><div class="dlw-empty">未設定資料來源</div></div>';
                    }
                }
            }
        },

        /**
         * 套用子系統的 CRUD 覆蓋和資料篩選到 widget config
         */
        _applySubSystemOverrides(widgetConfig) {
            if (!this.subCtx) return;

            const crud = this.subCtx.crud || {};
            // CRUD 覆蓋: 只在子系統有明確設定時覆蓋
            if ('create' in crud) widgetConfig.allowCreate = crud.create;
            if ('edit' in crud) widgetConfig.allowEdit = crud.edit;
            if ('delete' in crud) widgetConfig.allowDelete = crud.delete;

            // 資料篩選: 注入為額外的 contextInputs
            // 使用特殊的 _subSystemFilters 欄位，DataListWidget 會在請求時附加
            const dataFilters = this.subCtx.data_filters || {};
            if (Object.keys(dataFilters).length > 0) {
                widgetConfig._subSystemFilters = dataFilters;
            }
        },

        /**
         * 向下相容: 將舊版 bindings 格式遷移為 contextInputs/contextOutputs
         *
         * 舊格式: { widgets: [...], bindings: [{source, target, event, action, mapping}] }
         * 新格式: { version: 2, widgets: [{ ..., widget: { ..., contextOutputs, contextInputs } }] }
         */
        _migrateBindingsToContext(layout) {
            if (layout.version === 2) return layout;

            const bindings = layout.bindings || [];
            if (bindings.length === 0) {
                layout.version = 2;
                return layout;
            }

            // 建立 widget id → widget config 的索引
            const widgetMap = {};
            for (const item of (layout.widgets || [])) {
                if (item.widget) {
                    if (!item.widget.contextOutputs) item.widget.contextOutputs = [];
                    if (!item.widget.contextInputs) item.widget.contextInputs = [];
                    widgetMap[item.id] = item.widget;
                }
            }

            for (const b of bindings) {
                if (b.action !== 'filter' || !b.mapping) continue;

                const sourceWidget = widgetMap[b.source];
                const targetWidget = widgetMap[b.target];
                if (!sourceWidget || !targetWidget) continue;

                for (const [targetCol, sourceCol] of Object.entries(b.mapping)) {
                    const contextKey = b.source + '_' + sourceCol;

                    // 加 output 到 source widget
                    const hasOutput = sourceWidget.contextOutputs.some(
                        o => o.contextKey === contextKey && o.event === b.event
                    );
                    if (!hasOutput) {
                        sourceWidget.contextOutputs.push({
                            event: b.event,
                            contextKey: contextKey,
                            sourceColumn: sourceCol,
                        });
                    }

                    // 加 input 到 target widget
                    const hasInput = targetWidget.contextInputs.some(
                        i => i.contextKey === contextKey && i.filterColumn === targetCol
                    );
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
