/**
 * Lab Designer - GridStack 佈局設計器
 *
 * 功能：
 * 1. 元件庫：點擊加入 DATALIST
 * 2. GridStack 網格佈局（拖放/縮放）
 * 3. 元件設定：選 view、調參數
 * 4. Context 設定：設定 widget 的 output/input context keys
 * 5. 儲存/載入 DB、預覽
 */
function labDesigner() {
    return {
        grid: null,
        widgets: {},            // id -> DataListWidget 實例
        widgetConfigs: {},      // id -> config JSON
        selectedWidgetId: null,
        availableViews: [],
        viewColumnsCache: {},   // viewCode -> columns_config 快取

        // 持久化
        pageSecureCode: null,   // 當前頁面 secure_code (null=新頁面)
        pageName: '',
        pageDescription: '',
        pageStatus: 'draft',    // draft / published
        savedPages: [],         // 已存頁面列表
        showPageListModal: false,
        showSaveAsModal: false,
        saveAsName: '',

        // 當前選中 widget 的設定
        settingViewCode: '',
        settingPageSize: 10,
        settingShowSearch: true,
        settingShowPagination: true,
        settingAllowCreate: false,
        settingAllowEdit: false,
        settingAllowDelete: false,

        // Context Outputs/Inputs 設定
        settingContextOutputs: [],
        settingContextInputs: [],
        newOutputEvent: 'row-select',
        newOutputKey: '',
        newOutputCol: '',
        newInputKey: '',
        newInputCol: '',

        async init() {
            await this._loadViews();
            this._initGridStack();
            this._initClickSelect();

            // 如果 URL 有 secure_code，載入
            const match = window.location.pathname.match(/\/lab\/([^/]+)/);
            if (match && match[1] !== 'view') {
                await this._loadPage(match[1]);
            }
        },

        // ===== GridStack =====

        _initGridStack() {
            this.grid = GridStack.init({
                column: 12,
                cellHeight: 60,
                minRow: 10,
                margin: 8,
                float: true,
                removable: false,
                acceptWidgets: true,
                draggable: { handle: '.dlw-header' },
            }, '.grid-stack');

            this.grid.on('added', (event, items) => {
                for (const item of items) {
                    if (item.el && !this.widgets[item.id]) {
                        this._onWidgetAdded(item);
                    }
                }
            });
        },

        _initClickSelect() {
            const canvas = document.querySelector('.lab-canvas');
            if (!canvas) return;
            canvas.addEventListener('click', (e) => {
                const gsItem = e.target.closest('.grid-stack-item');
                if (gsItem) {
                    const id = gsItem.getAttribute('gs-id');
                    if (id && this.widgetConfigs[id]) {
                        this.selectWidget(id);
                        return;
                    }
                }
                if (e.target.closest('.grid-stack') && !gsItem) {
                    this.selectedWidgetId = null;
                    document.querySelectorAll('.grid-stack-item.lab-selected').forEach(el => {
                        el.classList.remove('lab-selected');
                    });
                }
            });
        },

        // ===== Widget =====

        addWidgetByClick() {
            const id = 'w_' + Math.random().toString(36).slice(2, 8);
            this.grid.addWidget({ x: 0, y: 0, w: 6, h: 5, id: id, content: '' });
        },

        _onWidgetAdded(item) {
            const id = item.id || ('w_' + Math.random().toString(36).slice(2, 8));
            if (!item.id) {
                item.id = id;
                if (item.el) item.el.setAttribute('gs-id', id);
            }
            const config = {
                id: id, type: 'DATALIST', viewCode: null, title: '',
                pageSize: 10, showSearch: true, showPagination: true,
                allowCreate: null, allowEdit: null, allowDelete: null,
                sortColumn: null, sortDir: null, visibleColumns: null,
                contextOutputs: [], contextInputs: [],
            };
            this.widgetConfigs[id] = config;
            const content = item.el ? item.el.querySelector('.grid-stack-item-content') : null;
            if (content) {
                content.innerHTML = '';
                const widget = new DataListWidget(content, config);
                widget.init();
                this.widgets[id] = widget;
            }
            this.selectWidget(id);
        },

        removeSelectedWidget() {
            if (!this.selectedWidgetId) return;
            const id = this.selectedWidgetId;
            const el = document.querySelector('.grid-stack-item[gs-id="' + id + '"]');
            if (el) this.grid.removeWidget(el);
            if (this.widgets[id]) { this.widgets[id].destroy(); delete this.widgets[id]; }
            delete this.widgetConfigs[id];
            this.selectedWidgetId = null;
        },

        get widgetList() {
            return Object.keys(this.widgetConfigs).map(id => {
                const cfg = this.widgetConfigs[id];
                const view = this.availableViews.find(v => v.secure_code === cfg.viewCode);
                return { id: id, label: cfg.title || (view ? view.name : '') || id };
            });
        },

        // ===== 選中與設定 =====

        selectWidget(id) {
            this.selectedWidgetId = id;
            const config = this.widgetConfigs[id];
            if (!config) return;
            this.settingViewCode = config.viewCode || '';
            this.settingPageSize = config.pageSize || 10;
            this.settingShowSearch = config.showSearch !== false;
            this.settingShowPagination = config.showPagination !== false;
            this.settingAllowCreate = config.allowCreate === true;
            this.settingAllowEdit = config.allowEdit === true;
            this.settingAllowDelete = config.allowDelete === true;

            // 載入 context 設定
            this.settingContextOutputs = JSON.parse(JSON.stringify(config.contextOutputs || []));
            this.settingContextInputs = JSON.parse(JSON.stringify(config.contextInputs || []));

            // 重設新增表單
            this.newOutputEvent = 'row-select';
            this.newOutputKey = '';
            this.newOutputCol = '';
            this.newInputKey = '';
            this.newInputCol = '';

            document.querySelectorAll('.grid-stack-item').forEach(el => el.classList.remove('lab-selected'));
            const el = document.querySelector('.grid-stack-item[gs-id="' + id + '"]');
            if (el) el.classList.add('lab-selected');
        },

        applySettings() {
            if (!this.selectedWidgetId) return;
            const id = this.selectedWidgetId;
            const config = this.widgetConfigs[id];
            if (!config) return;
            const view = this.availableViews.find(v => v.secure_code === this.settingViewCode);
            Object.assign(config, {
                viewCode: this.settingViewCode || null,
                title: view ? view.name : '',
                pageSize: parseInt(this.settingPageSize) || 10,
                showSearch: this.settingShowSearch,
                showPagination: this.settingShowPagination,
                allowCreate: this.settingAllowCreate || null,
                allowEdit: this.settingAllowEdit || null,
                allowDelete: this.settingAllowDelete || null,
                contextOutputs: JSON.parse(JSON.stringify(this.settingContextOutputs)),
                contextInputs: JSON.parse(JSON.stringify(this.settingContextInputs)),
            });
            // 快取此 view 的欄位
            if (view && view.columns_config) {
                this.viewColumnsCache[view.secure_code] = view.columns_config;
            }
            const widget = this.widgets[id];
            if (widget) widget.updateConfig(config);
        },

        // ===== Context Output/Input 管理 =====

        addContextOutput() {
            if (!this.newOutputKey.trim() || !this.newOutputCol.trim()) {
                alert(__('請填寫 Context Key 和欄位'));
                return;
            }
            this.settingContextOutputs.push({
                event: this.newOutputEvent,
                contextKey: this.newOutputKey.trim(),
                sourceColumn: this.newOutputCol.trim(),
            });
            this.newOutputKey = '';
            this.newOutputCol = '';
        },

        removeContextOutput(index) {
            this.settingContextOutputs.splice(index, 1);
        },

        addContextInput() {
            if (!this.newInputKey.trim() || !this.newInputCol.trim()) {
                alert(__('請填寫 Context Key 和篩選欄位'));
                return;
            }
            this.settingContextInputs.push({
                contextKey: this.newInputKey.trim(),
                filterColumn: this.newInputCol.trim(),
            });
            this.newInputKey = '';
            this.newInputCol = '';
        },

        removeContextInput(index) {
            this.settingContextInputs.splice(index, 1);
        },

        // ===== 取得選中 widget 的欄位清單 =====

        get selectedWidgetColumns() {
            if (!this.selectedWidgetId) return [];
            const cfg = this.widgetConfigs[this.selectedWidgetId];
            if (!cfg || !cfg.viewCode) return [];
            return this.viewColumnsCache[cfg.viewCode] || [];
        },

        // ===== Views =====

        async _loadViews() {
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/views');
                const data = await res.json();
                if (data.success) {
                    this.availableViews = data.data.filter(v => v.is_active);
                    // 預載欄位快取
                    for (const v of this.availableViews) {
                        if (v.columns_config) {
                            this.viewColumnsCache[v.secure_code] = v.columns_config;
                        }
                    }
                }
            } catch (e) {
                console.error('[Lab] loadViews error:', e);
            }
        },

        // ===== 持久化 =====

        _buildLayoutJson() {
            const items = this.grid.getGridItems().map(el => {
                const node = el.gridstackNode;
                return {
                    x: node.x, y: node.y, w: node.w, h: node.h,
                    id: node.id,
                    widget: this.widgetConfigs[node.id] || null
                };
            });
            return { version: 2, widgets: items };
        },

        async savePage() {
            if (!this.pageSecureCode) {
                // 新頁面 → 彈出另存對話框
                this.saveAsName = this.pageName || '';
                this.showSaveAsModal = true;
                return;
            }
            // 更新既有頁面
            const layout = this._buildLayoutJson();
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages/' + this.pageSecureCode, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: this.pageName,
                        description: this.pageDescription,
                        layout_json: layout
                    })
                });
                const data = await res.json();
                if (data.success) {
                    alert(__('已儲存'));
                } else {
                    alert(__('儲存失敗: {msg}', {msg: data.error || ''}));
                }
            } catch (e) {
                alert(__('儲存失敗: {msg}', {msg: e.message}));
            }
        },

        async saveAsPage() {
            if (!this.saveAsName.trim()) {
                alert(__('請輸入頁面名稱'));
                return;
            }
            const layout = this._buildLayoutJson();
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: this.saveAsName.trim(),
                        description: this.pageDescription,
                        layout_json: layout
                    })
                });
                const data = await res.json();
                if (data.success) {
                    this.pageSecureCode = data.data.secure_code;
                    this.pageName = data.data.name;
                    this.showSaveAsModal = false;
                    // 更新 URL
                    history.replaceState(null, '', window.__BP + '/nocode-builder/lab/' + this.pageSecureCode);
                    alert(__('已儲存'));
                } else {
                    alert(__('儲存失敗: {msg}', {msg: data.error || ''}));
                }
            } catch (e) {
                alert(__('儲存失敗: {msg}', {msg: e.message}));
            }
        },

        async openPageList() {
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages');
                const data = await res.json();
                if (data.success) {
                    this.savedPages = data.data;
                }
            } catch (e) {
                console.error('[Lab] loadPages error:', e);
            }
            this.showPageListModal = true;
        },

        async openPage(secureCode) {
            this.showPageListModal = false;
            await this._loadPage(secureCode);
            history.replaceState(null, '', window.__BP + '/nocode-builder/lab/' + secureCode);
        },

        async _loadPage(secureCode) {
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages/' + secureCode);
                const data = await res.json();
                if (!data.success) {
                    alert(__('載入失敗: {msg}', {msg: data.error || ''}));
                    return;
                }
                this.pageSecureCode = data.data.secure_code;
                this.pageName = data.data.name;
                this.pageDescription = data.data.description || '';
                this.pageStatus = data.data.status || 'draft';
                let layout = data.data.layout_json || {};

                // 向下相容: 舊格式 → 新格式
                layout = this._migrateBindingsToContext(layout);

                this._clearAll();
                this._loadLayoutWidgets(layout.widgets || []);
            } catch (e) {
                alert(__('載入失敗: {msg}', {msg: e.message}));
            }
        },

        /**
         * 向下相容: 將舊版 bindings 格式遷移為 contextInputs/contextOutputs
         */
        _migrateBindingsToContext(layout) {
            if (layout.version === 2) return layout;

            const bindings = layout.bindings || [];
            if (bindings.length === 0) {
                layout.version = 2;
                return layout;
            }

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
        },

        newPage() {
            this._clearAll();
            this.pageSecureCode = null;
            this.pageName = '';
            this.pageDescription = '';
            this.pageStatus = 'draft';
            history.replaceState(null, '', window.__BP + '/nocode-builder/lab');
        },

        // 預覽
        previewLayout() {
            if (!this.pageSecureCode) {
                alert(__('請先儲存頁面'));
                return;
            }
            window.open(window.__BP + '/nocode-builder/pages/' + this.pageSecureCode, '_blank');
        },

        // 發布
        async publishPage() {
            if (!this.pageSecureCode) {
                alert(__('請先儲存頁面'));
                return;
            }
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages/' + this.pageSecureCode + '/publish', {
                    method: 'PATCH',
                });
                const data = await res.json();
                if (data.success) {
                    this.pageStatus = 'published';
                    alert(__('頁面已發布\n上線版 URL: {url}', {url: `/p/${this.pageSecureCode}`}));
                } else {
                    alert(__('發布失敗: {msg}', {msg: data.error || ''}));
                }
            } catch (e) {
                alert(__('發布失敗: {msg}', {msg: e.message}));
            }
        },

        // 取消發布
        async unpublishPage() {
            if (!this.pageSecureCode) return;
            if (!confirm(__('確定要取消發布？取消後 /p/ 連結將無法存取。'))) return;
            try {
                const res = await fetch(window.__BP + '/api/nocode-builder/pages/' + this.pageSecureCode + '/unpublish', {
                    method: 'PATCH',
                });
                const data = await res.json();
                if (data.success) {
                    this.pageStatus = 'draft';
                    alert(__('已取消發布'));
                } else {
                    alert(__('取消發布失敗: {msg}', {msg: data.error || ''}));
                }
            } catch (e) {
                alert(__('取消發布失敗: {msg}', {msg: e.message}));
            }
        },

        // 上線版 URL
        get publishedUrl() {
            if (!this.pageSecureCode || this.pageStatus !== 'published') return '';
            return window.__BP + '/p/' + this.pageSecureCode;
        },

        _loadLayoutWidgets(items) {
            for (const item of items) {
                const id = item.id || ('w_' + Math.random().toString(36).slice(2, 8));
                const gsItem = this.grid.addWidget({
                    x: item.x, y: item.y, w: item.w || 6, h: item.h || 4,
                    id: id, content: ''
                });
                if (item.widget) {
                    item.widget.id = id;
                    // 確保有 context 欄位
                    if (!item.widget.contextOutputs) item.widget.contextOutputs = [];
                    if (!item.widget.contextInputs) item.widget.contextInputs = [];
                    this.widgetConfigs[id] = item.widget;
                    const content = gsItem.querySelector('.grid-stack-item-content');
                    if (content) {
                        content.innerHTML = '';
                        let widget;
                        if (item.widget.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                            widget = new SiteMenuWidget(content, item.widget);
                        } else {
                            widget = new DataListWidget(content, item.widget);
                        }
                        widget.init();
                        this.widgets[id] = widget;
                    }
                }
            }
        },

        _clearAll() {
            // 重設 PageContext
            if (typeof PageContext !== 'undefined') {
                PageContext.reset();
            }
            for (const id of Object.keys(this.widgets)) {
                this.widgets[id].destroy();
            }
            this.widgets = {};
            this.widgetConfigs = {};
            this.selectedWidgetId = null;
            this.settingContextOutputs = [];
            this.settingContextInputs = [];
            this.grid.removeAll();
        }
    };
}
