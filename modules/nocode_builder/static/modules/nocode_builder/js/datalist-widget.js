/**
 * DataListWidget - 無碼資料清單元件
 *
 * 自治的 widget：給一組 config JSON，在指定容器內自動渲染資料表。
 * 支援搜尋、排序、分頁、CRUD 操作、PageContext 共享狀態通訊。
 * 新增/編輯透過 modal 表單完成（從 columns_config 動態產生欄位）。
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

        // Lookup 映射: { column_name: { code: label } }
        this._lookupMaps = {};

        // DOM 快取
        this._els = {};

        // Modal 狀態
        this._modalOverlay = null;
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
            this._renderEmpty(__('未設定資料來源'));
            return;
        }
        this._renderSkeleton();
        await this._loadViewConfig();
        await this._loadLookupMaps();
        await this._loadRows(1);
    }

    destroy() {
        // 關閉 modal
        this._closeModal();
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
            const res = await fetch(window.__BP + '/api/nocode-builder/views/' + this.config.viewCode);
            const data = await res.json();
            if (data.success) {
                this.viewConfig = data.data;
                this.sortCol = this.config.sortColumn || data.data.default_sort_column || '';
                this.sortDir = this.config.sortDir || data.data.default_sort_dir || 'ASC';
                this.pagination.per_page = this.config.pageSize || data.data.page_size || 10;
                this._updateTitle();
            } else {
                this._renderEmpty(__('載入失敗: {msg}', {msg: data.error || ''}));
            }
        } catch (e) {
            this._renderEmpty(__('載入失敗: {msg}', {msg: e.message}));
        }
    }

    async _loadLookupMaps() {
        if (!this.viewConfig || !this.viewConfig.columns_config) return;
        const lookupCols = this.viewConfig.columns_config.filter(
            c => c.lookup_category_code
        );
        if (lookupCols.length === 0) return;

        // 收集唯一 category codes
        const codes = [...new Set(lookupCols.map(c => c.lookup_category_code))];
        const fetches = codes.map(code =>
            fetch(window.__BP + '/api/lookup/by-code/' + encodeURIComponent(code))
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const map = {};
                        (data.data || []).forEach(item => {
                            map[item.code] = item.label;
                        });
                        return { code, map };
                    }
                    return { code, map: {} };
                })
                .catch(() => ({ code, map: {} }))
        );

        const results = await Promise.all(fetches);
        const categoryMaps = {};
        results.forEach(r => { categoryMaps[r.code] = r.map; });

        // 建立 column -> lookup map 的映射
        for (const col of lookupCols) {
            this._lookupMaps[col.column] = categoryMaps[col.lookup_category_code] || {};
        }
    }

    async _loadRows(page) {
        if (!this.viewConfig) return;
        if (page !== undefined) this.pagination.page = page;
        this.loading = true;
        this._showLoading(true);

        try {
            let url = window.__BP + '/api/nocode-builder/views/' + this.config.viewCode + '/rows'
                + '?page=' + this.pagination.page
                + '&per_page=' + this.pagination.per_page;
            if (this.search) url += '&q=' + encodeURIComponent(this.search);
            if (this.sortCol) url += '&sort=' + this.sortCol + '&dir=' + this.sortDir;

            // 附加外部篩選條件 (PageContext)
            for (const [col, val] of Object.entries(this._externalFilters)) {
                if (val !== null && val !== undefined && val !== '') {
                    url += '&filter_' + encodeURIComponent(col) + '=' + encodeURIComponent(val);
                }
            }

            // 附加子系統資料篩選 (server-side 注入，已替換變數)
            const sysFilters = this.config._subSystemFilters || {};
            for (const [col, val] of Object.entries(sysFilters)) {
                if (val !== null && val !== undefined && val !== '') {
                    url += '&filter_' + encodeURIComponent(col) + '=' + encodeURIComponent(val);
                }
            }

            const res = await fetch(url, { headers: this._buildContextHeaders() });
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

    // ===== 表單欄位（modal 用） =====

    /**
     * 取得表單可見欄位（依 visible_in_form 過濾，sort_order 排序）
     */
    _getFormColumns() {
        if (!this.viewConfig || !this.viewConfig.columns_config) return [];
        return this.viewConfig.columns_config
            .filter(c => c.visible_in_form)
            .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
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
            input.placeholder = __('搜尋...');
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
        body.innerHTML = '<div class="dlw-loading">' + __('載入中...') + '</div>';
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
        // 保留 dlw-header 作為拖曳手柄（GridStack draggable handle）
        const header = document.createElement('div');
        header.className = 'dlw-header';
        header.innerHTML = '<span class="dlw-title">DATALIST</span>';
        this.container.appendChild(header);
        const el = document.createElement('div');
        el.className = 'dlw-empty';
        el.textContent = msg || __('未設定資料來源');
        this.container.appendChild(el);
    }

    _updateTitle() {
        if (!this._els.title) return;
        this._els.title.textContent = this.config.title || this.viewConfig?.name || '';

        // 新增按鈕（viewConfig 載入後才知道權限）
        if (this._canCreate() && this._els.toolbar && !this._els.createBtn) {
            const btn = document.createElement('button');
            btn.className = 'dlw-btn sm primary';
            btn.textContent = __('+新增');
            btn.addEventListener('click', () => this._openModal('create'));
            this._els.toolbar.appendChild(btn);
            this._els.createBtn = btn;
        }
    }

    _showLoading(show) {
        if (!this._els.body) return;
        if (show) {
            this._els.body.innerHTML = '<div class="dlw-loading">' + __('載入中...') + '</div>';
        }
    }

    _renderTable() {
        const body = this._els.body;
        if (!body) return;

        const cols = this._getDisplayColumns();
        const hasActions = this._canEdit() || this._canDelete();

        if (this.rows.length === 0) {
            body.innerHTML = '<div class="dlw-empty-data">' + __('尚無資料') + '</div>';
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
        if (hasActions) headHtml += '<th class="dlw-actions-th">' + __('操作') + '</th>';
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
                if (col.widget_type === 'file' && row[col.column]) {
                    const link = document.createElement('a');
                    link.href = '#';
                    link.textContent = __('附件');
                    link.title = __('下載附件');
                    link.style.fontSize = '12px';
                    const _fileSc = row[col.column];
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        this._tokenDownload(_fileSc);
                    });
                    td.appendChild(link);
                } else {
                    td.textContent = this._formatCell(row[col.column], col.column);
                }
                tr.appendChild(td);
            }
            if (hasActions) {
                const td = document.createElement('td');
                td.className = 'dlw-actions';
                if (this._canEdit()) {
                    const btn = document.createElement('button');
                    btn.className = 'dlw-btn sm';
                    btn.textContent = __('編輯');
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._openModal('edit', row._row_id);
                    });
                    td.appendChild(btn);
                }
                if (this._canDelete()) {
                    const btn = document.createElement('button');
                    btn.className = 'dlw-btn sm danger';
                    btn.textContent = __('刪除');
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
            '<span>' + __('共 {total} 筆，第 {page}/{pages} 頁', {total: this.pagination.total, page: this.pagination.page, pages: this.pagination.pages}) + '</span>'
            + '<div class="dlw-page-btns">'
            + '<button class="dlw-btn sm dlw-prev" ' + (this.pagination.page <= 1 ? 'disabled' : '') + '>' + __('上一頁') + '</button>'
            + '<button class="dlw-btn sm dlw-next" ' + (this.pagination.page >= this.pagination.pages ? 'disabled' : '') + '>' + __('下一頁') + '</button>'
            + '</div>';
        pager.querySelector('.dlw-prev')?.addEventListener('click', () => {
            if (this.pagination.page > 1) this._loadRows(this.pagination.page - 1);
        });
        pager.querySelector('.dlw-next')?.addEventListener('click', () => {
            if (this.pagination.page < this.pagination.pages) this._loadRows(this.pagination.page + 1);
        });
    }

    async _tokenDownload(fileSc) {
        try {
            const res = await fetch(window.__BP + '/api/files/' + fileSc + '/download-token', {
                method: 'POST',
            });
            const data = await res.json();
            if (data.success && data.url) {
                window.location.href = data.url;
            } else {
                alert(data.message || __('無法取得下載連結'));
            }
        } catch (e) {
            alert(e.message || __('下載失敗'));
        }
    }

    _formatCell(value, columnName) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'boolean') return value ? 'Y' : 'N';
        if (typeof value === 'object') return JSON.stringify(value);
        const s = String(value);
        // Lookup 翻譯
        if (columnName && this._lookupMaps[columnName]) {
            const label = this._lookupMaps[columnName][s];
            if (label) return label;
        }
        return s.length > 60 ? s.substring(0, 60) + '...' : s;
    }

    /**
     * 建立子系統/SiteMap context headers
     * 用於寫操作（create/edit/delete）的 CRUD 權限檢查
     */
    _buildContextHeaders() {
        const headers = {};
        if (this.config._siteMapNodeSc && this.config._subSystemSc) {
            headers['X-SiteMap-Node'] = this.config._siteMapNodeSc;
            headers['X-SubSystem-SC'] = this.config._subSystemSc;
        } else if (this.config._subSystemSspSc && this.config._subSystemSc) {
            headers['X-SubSystem-SSP'] = this.config._subSystemSspSc;
            headers['X-SubSystem-SC'] = this.config._subSystemSc;
        } else if (this.config._subSystemSc) {
            // Studio 設計模式: 只有 _subSystemSc，無 SiteMap/SSP context
            headers['X-SubSystem-SC'] = this.config._subSystemSc;
        }
        // Widget ID: 後端用來從 layout_json 定位 widget 做權限檢查
        if (this.id) {
            headers['X-Widget-Id'] = this.id;
        }
        return headers;
    }

    /**
     * 建立 context query string
     * 用於開新分頁（edit/new）時傳遞子系統 context
     */
    _buildContextQueryString() {
        const ss = this.config._subSystemSc || '';
        const smn = this.config._siteMapNodeSc || '';
        if (!ss) return '';
        let qs = '?_ss=' + encodeURIComponent(ss);
        if (smn) qs += '&_smn=' + encodeURIComponent(smn);
        return qs;
    }

    async _doDelete(rowId) {
        if (!confirm(__('確定要刪除此筆資料嗎?'))) return;
        try {
            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.viewCode + '/rows/' + rowId,
                { method: 'DELETE', headers: this._buildContextHeaders() }
            );
            const data = await res.json();
            if (data.success) {
                this._loadRows();
            } else {
                alert(__('刪除失敗: {msg}', {msg: data.error || ''}));
            }
        } catch (e) {
            alert(__('刪除失敗: {msg}', {msg: e.message}));
        }
    }

    // ===== Modal 表單 =====

    /**
     * 開啟新增/編輯 modal
     * @param {'create'|'edit'} mode
     * @param {string} [rowId] - 編輯模式的 row ID
     */
    async _openModal(mode, rowId) {
        // 防止重複開啟
        if (this._modalOverlay) return;

        const isEdit = mode === 'edit';
        const title = (isEdit ? __('編輯') : __('新增')) + ' - '
            + (this.config.title || this.viewConfig?.name || __('資料'));

        // 建立 overlay
        const overlay = document.createElement('div');
        overlay.className = 'dlw-modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'dlw-modal';

        // Header
        const header = document.createElement('div');
        header.className = 'dlw-modal-header';
        const titleEl = document.createElement('span');
        titleEl.className = 'dlw-modal-title';
        titleEl.textContent = title;
        const closeBtn = document.createElement('button');
        closeBtn.className = 'dlw-modal-close';
        closeBtn.innerHTML = '&#215;';
        closeBtn.addEventListener('click', () => this._closeModal());
        header.appendChild(titleEl);
        header.appendChild(closeBtn);
        modal.appendChild(header);

        // Body
        const body = document.createElement('div');
        body.className = 'dlw-modal-body';
        body.innerHTML = '<div class="dlw-modal-loading">' + __('載入中...') + '</div>';
        modal.appendChild(body);

        // Footer
        const footer = document.createElement('div');
        footer.className = 'dlw-modal-footer';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'dlw-btn';
        cancelBtn.textContent = __('取消');
        cancelBtn.addEventListener('click', () => this._closeModal());
        const saveBtn = document.createElement('button');
        saveBtn.className = 'dlw-btn primary';
        saveBtn.textContent = __('儲存');
        saveBtn.disabled = true;
        footer.appendChild(cancelBtn);
        footer.appendChild(saveBtn);
        modal.appendChild(footer);

        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._modalOverlay = overlay;

        // ESC 關閉
        this._modalEscHandler = (e) => {
            if (e.key === 'Escape') this._closeModal();
        };
        document.addEventListener('keydown', this._modalEscHandler);

        // 載入表單欄位
        let rowData = {};
        if (isEdit && rowId) {
            try {
                const res = await fetch(
                    window.__BP + '/api/nocode-builder/views/' + this.config.viewCode + '/rows/' + rowId,
                    { headers: this._buildContextHeaders() }
                );
                const data = await res.json();
                if (!data.success) {
                    body.innerHTML = '<div class="dlw-form-error">'
                        + __('載入資料失敗: {msg}', {msg: data.error || ''}) + '</div>';
                    return;
                }
                rowData = data.data || {};
            } catch (e) {
                body.innerHTML = '<div class="dlw-form-error">'
                    + __('載入資料失敗: {msg}', {msg: e.message}) + '</div>';
                return;
            }
        }

        // 渲染表單
        this._renderFormFields(body, mode, rowData);

        // 啟用儲存按鈕
        saveBtn.disabled = false;
        saveBtn.addEventListener('click', () => {
            this._submitForm(mode, rowId, body, saveBtn);
        });
    }

    /**
     * 關閉 modal
     */
    _closeModal() {
        if (this._modalOverlay) {
            this._modalOverlay.remove();
            this._modalOverlay = null;
        }
        if (this._modalEscHandler) {
            document.removeEventListener('keydown', this._modalEscHandler);
            this._modalEscHandler = null;
        }
    }

    /**
     * 渲染表單欄位到 modal body
     * @param {HTMLElement} body - modal body 容器
     * @param {'create'|'edit'} mode
     * @param {object} rowData - 編輯時的現有資料
     */
    _renderFormFields(body, mode, rowData) {
        body.innerHTML = '';
        const formCols = this._getFormColumns();
        const isEdit = mode === 'edit';

        // 收集自動填入欄位（fixed_filters + subSystemFilters）
        const autoFill = {};
        if (!isEdit) {
            // 新增時自動填入 fixed_filters
            const fixed = this.viewConfig?.fixed_filters || {};
            for (const [col, val] of Object.entries(fixed)) {
                if (typeof val === 'string' && val.startsWith('$')) continue;  // 變數由後端處理
                autoFill[col] = val;
            }
            // 新增時自動填入 subSystemFilters（已在前端替換變數）
            const sysFilters = this.config._subSystemFilters || {};
            for (const [col, val] of Object.entries(sysFilters)) {
                autoFill[col] = val;
            }
            // 新增時自動填入 externalFilters（PageContext 篩選）
            for (const [col, val] of Object.entries(this._externalFilters)) {
                autoFill[col] = val;
            }
        }

        for (const col of formCols) {
            const colName = col.column;
            const isPk = col.is_pk || false;
            const isReadonly = col.readonly || isPk || col.is_system || false;
            const isAutoFilled = !isEdit && colName in autoFill;
            const disabled = isReadonly || isAutoFilled;

            // 取值：編輯取 rowData，新增取 autoFill
            let value = isEdit ? (rowData[colName] ?? '') : (autoFill[colName] ?? '');

            const field = document.createElement('div');
            field.className = 'dlw-form-field';

            // Label
            const label = document.createElement('label');
            label.className = 'dlw-form-label';
            label.textContent = col.label || colName;
            if (!col.nullable && !isPk && !col.is_system) {
                const req = document.createElement('span');
                req.className = 'dlw-required';
                req.textContent = '*';
                label.appendChild(req);
            }
            field.appendChild(label);

            // 依據型別產生欄位
            const dbType = (col.db_type || '').toUpperCase();

            if (col.lookup_category_code && this._lookupMaps[colName]) {
                // Lookup → select
                const select = document.createElement('select');
                select.className = 'dlw-form-select';
                select.name = colName;
                select.disabled = disabled;

                const emptyOpt = document.createElement('option');
                emptyOpt.value = '';
                emptyOpt.textContent = __('-- 請選擇 --');
                select.appendChild(emptyOpt);

                const map = this._lookupMaps[colName];
                for (const [code, lbl] of Object.entries(map)) {
                    const opt = document.createElement('option');
                    opt.value = code;
                    opt.textContent = lbl;
                    if (String(value) === code) opt.selected = true;
                    select.appendChild(opt);
                }
                field.appendChild(select);

            } else if (dbType === 'BOOLEAN' || dbType === 'BOOL') {
                // Boolean → checkbox
                const wrap = document.createElement('div');
                wrap.className = 'dlw-form-check';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.name = colName;
                cb.checked = value === true || value === 'true' || value === 't';
                cb.disabled = disabled;
                const cbLabel = document.createElement('span');
                cbLabel.textContent = value === true || value === 'true' || value === 't' ? 'Y' : 'N';
                cb.addEventListener('change', () => {
                    cbLabel.textContent = cb.checked ? 'Y' : 'N';
                });
                wrap.appendChild(cb);
                wrap.appendChild(cbLabel);
                field.appendChild(wrap);

            } else if (dbType === 'JSONB' || dbType === 'JSON') {
                // JSON → textarea
                const ta = document.createElement('textarea');
                ta.className = 'dlw-form-textarea';
                ta.name = colName;
                ta.disabled = disabled;
                if (value && typeof value === 'object') {
                    ta.value = JSON.stringify(value, null, 2);
                } else {
                    ta.value = value !== null && value !== undefined ? String(value) : '';
                }
                field.appendChild(ta);

            } else if (dbType === 'DATE') {
                // Date
                const input = document.createElement('input');
                input.type = 'date';
                input.className = 'dlw-form-input';
                input.name = colName;
                input.disabled = disabled;
                // ISO date → YYYY-MM-DD
                if (value) {
                    input.value = String(value).substring(0, 10);
                }
                field.appendChild(input);

            } else if (dbType.indexOf('TIMESTAMP') >= 0) {
                // Timestamp → datetime-local
                const input = document.createElement('input');
                input.type = 'datetime-local';
                input.className = 'dlw-form-input';
                input.name = colName;
                input.disabled = disabled;
                if (value) {
                    // ISO 轉 datetime-local 格式
                    const s = String(value).replace('T', 'T').substring(0, 16);
                    input.value = s;
                }
                field.appendChild(input);

            } else if (this._isNumericType(dbType)) {
                // Numeric
                const input = document.createElement('input');
                input.type = 'number';
                input.className = 'dlw-form-input';
                input.name = colName;
                input.disabled = disabled;
                if (value !== '' && value !== null && value !== undefined) {
                    input.value = value;
                }
                // DECIMAL/NUMERIC 允許小數
                if (dbType === 'NUMERIC' || dbType === 'DECIMAL'
                    || dbType.indexOf('NUMERIC') >= 0 || dbType.indexOf('DECIMAL') >= 0) {
                    input.step = 'any';
                }
                field.appendChild(input);

            } else if (col.widget_type === 'file') {
                // File attachment → BkFileAttachment
                const fileWrap = document.createElement('div');
                fileWrap.className = 'dlw-file-widget';
                fileWrap.setAttribute('data-column', colName);

                if (disabled) {
                    // 唯讀：只顯示下載連結
                    if (value) {
                        const link = document.createElement('a');
                        link.href = '#';
                        link.className = 'dlw-btn sm';
                        link.textContent = __('下載附件');
                        link.style.textDecoration = 'none';
                        const _dlSc = value;
                        link.addEventListener('click', (e) => {
                            e.preventDefault();
                            this._tokenDownload(_dlSc);
                        });
                        fileWrap.appendChild(link);
                    } else {
                        fileWrap.textContent = __('無附件');
                        fileWrap.style.color = '#9ca3af';
                        fileWrap.style.fontSize = '12px';
                    }
                } else {
                    // 可編輯：上傳 / 替換 / 下載
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = colName;
                    hiddenInput.value = value || '';
                    fileWrap.appendChild(hiddenInput);

                    const statusSpan = document.createElement('span');
                    statusSpan.style.fontSize = '12px';
                    statusSpan.style.marginLeft = '8px';

                    // 現有檔案：顯示下載 + 清除
                    const existingWrap = document.createElement('span');
                    existingWrap.className = 'dlw-file-existing';
                    if (value) {
                        const dlLink = document.createElement('a');
                        dlLink.href = '#';
                        dlLink.textContent = __('下載現有附件');
                        dlLink.style.fontSize = '12px';
                        dlLink.style.marginRight = '8px';
                        const _dlSc2 = value;
                        dlLink.addEventListener('click', (e) => {
                            e.preventDefault();
                            this._tokenDownload(_dlSc2);
                        });
                        existingWrap.appendChild(dlLink);

                        const clearBtn = document.createElement('button');
                        clearBtn.type = 'button';
                        clearBtn.className = 'dlw-btn sm danger';
                        clearBtn.textContent = __('清除');
                        clearBtn.style.fontSize = '11px';
                        clearBtn.addEventListener('click', () => {
                            hiddenInput.value = '';
                            existingWrap.innerHTML = '';
                            statusSpan.textContent = __('已清除');
                            statusSpan.style.color = '#dc2626';
                        });
                        existingWrap.appendChild(clearBtn);
                    }
                    fileWrap.appendChild(existingWrap);

                    // 上傳按鈕
                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.style.display = 'none';
                    fileInput.addEventListener('change', async () => {
                        if (!fileInput.files || !fileInput.files[0]) return;
                        statusSpan.textContent = __('上傳中...');
                        statusSpan.style.color = '#6b7280';
                        try {
                            const fd = new FormData();
                            fd.append('file', fileInput.files[0]);
                            fd.append('context_type', 'subsystem_file');
                            fd.append('context_id', this.config.viewCode || '');
                            const res = await fetch(window.__BP + '/api/files/upload', { method: 'POST', body: fd });
                            const result = await res.json();
                            if (result.success) {
                                hiddenInput.value = result.data.secure_code;
                                statusSpan.textContent = __('{name} (已上傳)', {name: fileInput.files[0].name});
                                statusSpan.style.color = '#059669';
                            } else {
                                statusSpan.textContent = result.message || __('上傳失敗');
                                statusSpan.style.color = '#dc2626';
                            }
                        } catch (e) {
                            statusSpan.textContent = __('上傳失敗');
                            statusSpan.style.color = '#dc2626';
                        }
                        fileInput.value = '';
                    });

                    const uploadBtn = document.createElement('button');
                    uploadBtn.type = 'button';
                    uploadBtn.className = 'dlw-btn sm';
                    uploadBtn.innerHTML = '<i class="fas fa-upload"></i> ' + __('上傳');
                    uploadBtn.style.marginTop = '4px';
                    uploadBtn.addEventListener('click', () => fileInput.click());

                    fileWrap.appendChild(document.createElement('br'));
                    fileWrap.appendChild(fileInput);
                    fileWrap.appendChild(uploadBtn);
                    fileWrap.appendChild(statusSpan);
                }
                field.appendChild(fileWrap);

            } else if (dbType === 'TEXT') {
                // TEXT → textarea（較長文字）
                const ta = document.createElement('textarea');
                ta.className = 'dlw-form-textarea';
                ta.name = colName;
                ta.disabled = disabled;
                ta.style.fontFamily = 'inherit';
                ta.value = value !== null && value !== undefined ? String(value) : '';
                field.appendChild(ta);

            } else {
                // 預設: text input (VARCHAR, CHAR, etc.)
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'dlw-form-input';
                input.name = colName;
                input.disabled = disabled;
                input.value = value !== null && value !== undefined ? String(value) : '';
                field.appendChild(input);
            }

            // 提示訊息
            if (isPk && isEdit) {
                const hint = document.createElement('div');
                hint.className = 'dlw-form-hint';
                hint.textContent = __('主鍵，不可修改');
                field.appendChild(hint);
            } else if (isAutoFilled) {
                const hint = document.createElement('div');
                hint.className = 'dlw-form-hint';
                hint.textContent = __('自動填入');
                field.appendChild(hint);
            }

            body.appendChild(field);
        }

        if (formCols.length === 0) {
            body.innerHTML = '<div class="dlw-form-error">' + __('此視圖未設定表單欄位') + '</div>';
        }
    }

    /**
     * 判斷 db_type 是否為數值型別
     */
    _isNumericType(dbType) {
        var numTypes = ['INTEGER', 'BIGINT', 'SMALLINT', 'INT', 'INT4', 'INT8', 'INT2',
                        'NUMERIC', 'DECIMAL', 'REAL', 'FLOAT', 'DOUBLE', 'FLOAT4', 'FLOAT8'];
        for (var i = 0; i < numTypes.length; i++) {
            if (dbType.indexOf(numTypes[i]) >= 0) return true;
        }
        return false;
    }

    /**
     * 提交表單
     * @param {'create'|'edit'} mode
     * @param {string} [rowId]
     * @param {HTMLElement} body - modal body
     * @param {HTMLElement} saveBtn - 儲存按鈕
     */
    async _submitForm(mode, rowId, body, saveBtn) {
        const isEdit = mode === 'edit';
        const formCols = this._getFormColumns();
        const data = {};

        // 收集表單值
        for (const col of formCols) {
            const colName = col.column;
            const isPk = col.is_pk || false;
            const isReadonly = col.readonly || isPk || col.is_system || false;

            // PK 和 readonly 不送到後端（後端也會擋，但前端先過濾）
            if (isPk) continue;
            if (isReadonly) continue;

            const dbType = (col.db_type || '').toUpperCase();
            const el = body.querySelector('[name="' + colName + '"]');
            if (!el) continue;

            // 如果 disabled（autoFill），也要送值
            if (dbType === 'BOOLEAN' || dbType === 'BOOL') {
                data[colName] = el.checked;
            } else if (dbType === 'JSONB' || dbType === 'JSON') {
                const raw = el.value.trim();
                if (raw) {
                    try {
                        data[colName] = JSON.parse(raw);
                    } catch (e) {
                        alert(__('JSON 格式錯誤: {label}', {label: col.label}));
                        return;
                    }
                } else {
                    data[colName] = null;
                }
            } else if (this._isNumericType(dbType)) {
                const raw = el.value.trim();
                if (raw !== '') {
                    data[colName] = Number(raw);
                    if (isNaN(data[colName])) {
                        alert(__('數值格式錯誤: {label}', {label: col.label}));
                        return;
                    }
                } else {
                    data[colName] = null;
                }
            } else {
                const val = el.value;
                data[colName] = val === '' ? null : val;
            }
        }

        // 自動填入欄位也要送值（新增時）
        if (!isEdit) {
            const fixed = this.viewConfig?.fixed_filters || {};
            for (const [col, val] of Object.entries(fixed)) {
                if (typeof val === 'string' && val.startsWith('$')) continue;
                if (!(col in data)) data[col] = val;
            }
            const sysFilters = this.config._subSystemFilters || {};
            for (const [col, val] of Object.entries(sysFilters)) {
                if (!(col in data)) data[col] = val;
            }
            for (const [col, val] of Object.entries(this._externalFilters)) {
                if (!(col in data)) data[col] = val;
            }
        }

        // 送出
        saveBtn.disabled = true;
        saveBtn.textContent = __('儲存中...');

        try {
            let url, method;
            if (isEdit) {
                url = window.__BP + '/api/nocode-builder/views/' + this.config.viewCode + '/rows/' + rowId;
                method = 'PUT';
            } else {
                url = window.__BP + '/api/nocode-builder/views/' + this.config.viewCode + '/rows';
                method = 'POST';
            }

            const headers = Object.assign(
                { 'Content-Type': 'application/json' },
                this._buildContextHeaders()
            );

            const res = await fetch(url, {
                method: method,
                headers: headers,
                body: JSON.stringify(data),
            });
            const result = await res.json();

            if (result.success) {
                this._closeModal();
                this._loadRows();
            } else {
                alert(__('儲存失敗: {msg}', {msg: result.error || ''}));
                saveBtn.disabled = false;
                saveBtn.textContent = __('儲存');
            }
        } catch (e) {
            alert(__('儲存失敗: {msg}', {msg: e.message}));
            saveBtn.disabled = false;
            saveBtn.textContent = __('儲存');
        }
    }
}
