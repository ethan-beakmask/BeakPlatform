/**
 * DataListWidget - 無碼資料清單元件
 *
 * 自治的 widget：給一組 config JSON，在指定容器內自動渲染資料表。
 * 支援搜尋、排序、分頁、CRUD 操作、PageContext 共享狀態通訊。
 *
 * PageContext 介面：
 *   contextOutputs: [{ event, contextKey, sourceColumn }]
 *   contextInputs:  [{ contextKey, filterColumn }]
 *
 * 用法：
 *   const widget = new DataListWidget(containerEl, {
 *       viewCode: 'xxx',
 *       pageSize: 10,
 *       showSearch: true,
 *       contextOutputs: [...],
 *       contextInputs: [...],
 *       ...
 *   });
 *   widget.init();
 */
class DataListWidget {

    constructor(container, config) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;
        this.id = config.id || ('dlw_' + Math.random().toString(36).slice(2, 8));

        // 設定（合併預設值）
        this.config = Object.assign({
            viewCode: null,
            title: '',
            pageSize: 10,
            showSearch: true,
            showPagination: true,
            allowCreate: null,   // null = 依 view 設定
            allowEdit: null,
            allowDelete: null,
            sortColumn: null,    // null = 依 view 預設
            sortDir: null,
            visibleColumns: null, // null = 依 view 設定
            contextOutputs: [],
            contextInputs: [],
        }, config);

        // 狀態
        this.viewConfig = null;
        this.rows = [];
        this.loading = true;
        this.search = '';
        this.sortCol = '';
        this.sortDir = 'ASC';
        this.pagination = { page: 1, pages: 0, total: 0, per_page: 10 };
        this.selectedRowId = null;

        // 外部篩選條件（由 PageContext input 注入）
        this._externalFilters = {};

        // DOM 快取
        this._els = {};
    }

    // ===== 初始化 =====

    async init() {
        // 向 PageContext 登錄
        if (typeof PageContext !== 'undefined') {
            PageContext.register(this.id);

            // 登記 output keys
            const outputKeys = (this.config.contextOutputs || []).map(o => o.contextKey);
            if (outputKeys.length > 0) {
                PageContext.registerOutputKeys(this.id, outputKeys);
            }

            // 訂閱 input keys
            for (const input of (this.config.contextInputs || [])) {
                PageContext.subscribe(input.contextKey, this.id, (key, value) => {
                    this._onContextChange(key, value);
                });
            }
        }

        if (!this.config.viewCode) {
            this._renderEmpty('未設定資料來源');
            return;
        }
        this._renderSkeleton();
        await this._loadViewConfig();
        await this._loadRows(1);
    }

    destroy() {
        // 從 PageContext 取消登錄
        if (typeof PageContext !== 'undefined') {
            PageContext.unregister(this.id);
        }
        if (this.container) {
            this.container.innerHTML = '';
        }
    }

    // ===== PageContext 介面 =====

    /**
     * 當訂閱的 context key 變更時觸發
     * @param {string} key - 變更的 context key
     * @param {*} value - 新值
     */
    _onContextChange(key, value) {
        // 先清除自己的所有 output（觸發 cascading clear）
        if (typeof PageContext !== 'undefined') {
            PageContext.clearWidgetOutputs(this.id);
        }

        // 重建篩選條件
        this._rebuildFiltersFromContext();

        // 判斷是否有有效篩選值
        const hasValue = Object.values(this._externalFilters).some(
            v => v !== null && v !== undefined && v !== ''
        );
        if (hasValue) {
            this.selectedRowId = null;
            this._loadRows(1);
        } else {
            // 所有 input 都為 null → 清空顯示
            this.selectedRowId = null;
            this.rows = [];
            this._renderTable();
        }
    }

    /**
     * 從 PageContext 的當前狀態重建外部篩選條件
     */
    _rebuildFiltersFromContext() {
        this._externalFilters = {};
        if (typeof PageContext === 'undefined') return;

        for (const input of (this.config.contextInputs || [])) {
            const val = PageContext.get(input.contextKey);
            if (val !== null && val !== undefined && val !== '') {
                this._externalFilters[input.filterColumn] = val;
            }
        }
    }

    /**
     * 發送 row-select 事件：寫入 output 到 PageContext
     * @param {object} rowData - 被選中的整列資料
     */
    _emitRowSelect(rowData) {
        this.selectedRowId = rowData?._row_id || null;
        if (typeof PageContext === 'undefined') return;

        for (const output of (this.config.contextOutputs || [])) {
            if (output.event === 'row-select') {
                const value = rowData ? rowData[output.sourceColumn] : null;
                PageContext.set(output.contextKey, value, this.id);
            }
        }
    }

    // ===== 取得設定 JSON（供序列化） =====

    getConfig() {
        return Object.assign({}, this.config);
    }

    updateConfig(newConfig) {
        Object.assign(this.config, newConfig);
        this.destroy();
        this.init();
    }

    // ===== 資料載入 =====

    async _loadViewConfig() {
        try {
            const res = await fetch('/api/data-crud/views/' + this.config.viewCode);
            const data = await res.json();
            if (data.success) {
                this.viewConfig = data.data;
                this.sortCol = this.config.sortColumn || data.data.default_sort_column || '';
                this.sortDir = this.config.sortDir || data.data.default_sort_dir || 'ASC';
                this.pagination.per_page = this.config.pageSize || data.data.page_size || 10;
                this._updateTitle();
            } else {
                this._renderEmpty('載入失敗: ' + (data.error || ''));
            }
        } catch (e) {
            this._renderEmpty('載入失敗: ' + e.message);
        }
    }

    async _loadRows(page) {
        if (!this.viewConfig) return;
        if (page !== undefined) this.pagination.page = page;
        this.loading = true;
        this._showLoading(true);

        try {
            let url = '/api/data-crud/views/' + this.config.viewCode + '/rows'
                + '?page=' + this.pagination.page
                + '&per_page=' + this.pagination.per_page;
            if (this.search) url += '&q=' + encodeURIComponent(this.search);
            if (this.sortCol) url += '&sort=' + this.sortCol + '&dir=' + this.sortDir;

            // 附加外部篩選條件
            for (const [col, val] of Object.entries(this._externalFilters)) {
                if (val !== null && val !== undefined && val !== '') {
                    url += '&filter_' + encodeURIComponent(col) + '=' + encodeURIComponent(val);
                }
            }

            const res = await fetch(url);
            const data = await res.json();
            if (data.success) {
                this.rows = data.data.rows || [];
                this.pagination.page = data.data.page;
                this.pagination.pages = data.data.pages;
                this.pagination.total = data.data.total;
                this.pagination.per_page = data.data.per_page;
            }
        } catch (e) {
            console.error('[DataListWidget] loadRows error:', e);
        } finally {
            this.loading = false;
            this._renderTable();
        }
    }

    // ===== 可見欄位 =====

    _getDisplayColumns() {
        if (!this.viewConfig || !this.viewConfig.columns_config) return [];
        let cols = this.viewConfig.columns_config
            .filter(c => c.visible)
            .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));

        if (this.config.visibleColumns && this.config.visibleColumns.length > 0) {
            const allowed = new Set(this.config.visibleColumns);
            cols = cols.filter(c => allowed.has(c.column));
        }
        return cols;
    }

    // ===== 權限判斷 =====

    _canCreate() {
        if (this.config.allowCreate !== null) return this.config.allowCreate;
        return this.viewConfig?.allow_create || false;
    }

    _canEdit() {
        if (this.config.allowEdit !== null) return this.config.allowEdit;
        return this.viewConfig?.allow_edit || false;
    }

    _canDelete() {
        if (this.config.allowDelete !== null) return this.config.allowDelete;
        return this.viewConfig?.allow_delete || false;
    }

    // ===== DOM 渲染 =====

    _renderSkeleton() {
        const c = this.container;
        c.innerHTML = '';
        c.classList.add('dlw-root');

        // 標題列
        const header = document.createElement('div');
        header.className = 'dlw-header';
        header.innerHTML = '<span class="dlw-title"></span><div class="dlw-toolbar"></div>';
        c.appendChild(header);
        this._els.header = header;
        this._els.title = header.querySelector('.dlw-title');
        this._els.toolbar = header.querySelector('.dlw-toolbar');

        // 搜尋
        if (this.config.showSearch) {
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'dlw-search';
            input.placeholder = '搜尋...';
            let timer = null;
            input.addEventListener('input', () => {
                clearTimeout(timer);
                timer = setTimeout(() => {
                    this.search = input.value.trim();
                    this._loadRows(1);
                }, 400);
            });
            this._els.toolbar.appendChild(input);
        }

        // 內容區
        const body = document.createElement('div');
        body.className = 'dlw-body';
        body.innerHTML = '<div class="dlw-loading">載入中...</div>';
        c.appendChild(body);
        this._els.body = body;

        // 分頁
        if (this.config.showPagination) {
            const pager = document.createElement('div');
            pager.className = 'dlw-pager';
            pager.style.display = 'none';
            c.appendChild(pager);
            this._els.pager = pager;
        }
    }

    _renderEmpty(msg) {
        this.container.innerHTML = '';
        this.container.classList.add('dlw-root');
        const el = document.createElement('div');
        el.className = 'dlw-empty';
        el.textContent = msg || '未設定資料來源';
        this.container.appendChild(el);
    }

    _updateTitle() {
        if (!this._els.title) return;
        this._els.title.textContent = this.config.title || this.viewConfig?.name || '';
    }

    _showLoading(show) {
        if (!this._els.body) return;
        if (show) {
            this._els.body.innerHTML = '<div class="dlw-loading">載入中...</div>';
        }
    }

    _renderTable() {
        const body = this._els.body;
        if (!body) return;

        const cols = this._getDisplayColumns();
        const hasActions = this._canEdit() || this._canDelete();

        if (this.rows.length === 0) {
            body.innerHTML = '<div class="dlw-empty-data">尚無資料</div>';
            if (this._els.pager) this._els.pager.style.display = 'none';
            return;
        }

        // 建表
        const table = document.createElement('table');
        table.className = 'dlw-table';

        // thead
        const thead = document.createElement('thead');
        let headHtml = '<tr>';
        for (const col of cols) {
            const isActive = this.sortCol === col.column;
            const arrow = isActive ? (this.sortDir === 'ASC' ? ' ^' : ' v') : '';
            headHtml += '<th class="dlw-sortable" data-col="' + col.column + '">'
                + (col.label || col.column)
                + '<span class="dlw-sort-arrow">' + arrow + '</span></th>';
        }
        if (hasActions) headHtml += '<th class="dlw-actions-th">操作</th>';
        headHtml += '</tr>';
        thead.innerHTML = headHtml;
        table.appendChild(thead);

        // 綁排序
        thead.querySelectorAll('.dlw-sortable').forEach(th => {
            th.addEventListener('click', (e) => {
                e.stopPropagation(); // 不觸發列選中
                const col = th.dataset.col;
                if (this.sortCol === col) {
                    this.sortDir = this.sortDir === 'ASC' ? 'DESC' : 'ASC';
                } else {
                    this.sortCol = col;
                    this.sortDir = 'ASC';
                }
                this._loadRows(1);
            });
        });

        // tbody
        const tbody = document.createElement('tbody');
        for (const row of this.rows) {
            const tr = document.createElement('tr');
            tr.className = 'dlw-row';
            if (row._row_id === this.selectedRowId) {
                tr.classList.add('dlw-row-selected');
            }

            // 點擊整列 → 發送 row-select
            tr.addEventListener('click', () => {
                // 移除舊選中
                tbody.querySelectorAll('.dlw-row-selected').forEach(el => {
                    el.classList.remove('dlw-row-selected');
                });
                tr.classList.add('dlw-row-selected');
                this._emitRowSelect(row);
            });

            for (const col of cols) {
                const td = document.createElement('td');
                td.textContent = this._formatCell(row[col.column]);
                tr.appendChild(td);
            }
            if (hasActions) {
                const td = document.createElement('td');
                td.className = 'dlw-actions';
                if (this._canEdit()) {
                    const btn = document.createElement('a');
                    btn.className = 'dlw-btn sm';
                    btn.textContent = '編輯';
                    btn.href = '/data-crud/views/' + this.config.viewCode + '/rows/' + row._row_id + '/edit';
                    btn.target = '_blank';
                    btn.addEventListener('click', (e) => e.stopPropagation());
                    td.appendChild(btn);
                }
                if (this._canDelete()) {
                    const btn = document.createElement('button');
                    btn.className = 'dlw-btn sm danger';
                    btn.textContent = '刪除';
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._doDelete(row._row_id);
                    });
                    td.appendChild(btn);
                }
                tr.appendChild(td);
            }
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);

        body.innerHTML = '';
        const wrapper = document.createElement('div');
        wrapper.style.overflowX = 'auto';
        wrapper.appendChild(table);
        body.appendChild(wrapper);

        // 分頁
        this._renderPager();
    }

    _renderPager() {
        const pager = this._els.pager;
        if (!pager) return;
        if (this.pagination.pages <= 1) {
            pager.style.display = 'none';
            return;
        }
        pager.style.display = 'flex';
        pager.innerHTML =
            '<span>共 ' + this.pagination.total + ' 筆，第 ' + this.pagination.page + '/' + this.pagination.pages + ' 頁</span>'
            + '<div class="dlw-page-btns">'
            + '<button class="dlw-btn sm dlw-prev" ' + (this.pagination.page <= 1 ? 'disabled' : '') + '>上一頁</button>'
            + '<button class="dlw-btn sm dlw-next" ' + (this.pagination.page >= this.pagination.pages ? 'disabled' : '') + '>下一頁</button>'
            + '</div>';
        pager.querySelector('.dlw-prev')?.addEventListener('click', () => {
            if (this.pagination.page > 1) this._loadRows(this.pagination.page - 1);
        });
        pager.querySelector('.dlw-next')?.addEventListener('click', () => {
            if (this.pagination.page < this.pagination.pages) this._loadRows(this.pagination.page + 1);
        });
    }

    _formatCell(value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'boolean') return value ? 'Y' : 'N';
        if (typeof value === 'object') return JSON.stringify(value);
        const s = String(value);
        return s.length > 60 ? s.substring(0, 60) + '...' : s;
    }

    async _doDelete(rowId) {
        if (!confirm('確定要刪除此筆資料嗎?')) return;
        try {
            const res = await fetch(
                '/api/data-crud/views/' + this.config.viewCode + '/rows/' + rowId,
                { method: 'DELETE' }
            );
            const data = await res.json();
            if (data.success) {
                this._loadRows();
            } else {
                alert('刪除失敗: ' + (data.error || ''));
            }
        } catch (e) {
            alert('刪除失敗: ' + e.message);
        }
    }
}
