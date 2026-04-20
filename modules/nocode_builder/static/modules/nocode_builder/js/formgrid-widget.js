/**
 * FormGridWidget - 主細元件 (FORMGRID)
 *
 * 單一元件完成二表三態的資料操作。
 * 佈局：上左 Master 簡式清單 + 上右 Master 欄位展開 + 下方 Detail 表。
 *
 * 三態：List（瀏覽選擇）、View（唯讀檢視）、Edit（編輯模式）
 *
 * 特性：
 *   - Master/Detail 各自對應一個 CRUD View
 *   - Master 的 PKey 欄位可設定 numbering 規則或 auto+1
 *   - Detail 的 FKey 欄位自動填入 Master 的 PKey 值
 *   - is_locked 鎖定機制：鎖定後 Master + Detail 皆不可修改
 *   - PageContext 對外通訊（整個 FORMGRID 作為一個 widget）
 *
 * 用法：
 *   const widget = new FormGridWidget(containerEl, {
 *       masterViewCode: 'xxx',
 *       detailViewCode: 'yyy',
 *       masterPkeyColumn: 'order_no',
 *       detailFkeyColumn: 'order_no',
 *       masterListColumns: ['order_no', 'subject'],
 *       detailPageSize: 5,
 *       numberingRuleSc: null,
 *       ...
 *   });
 *   widget.init();
 */
class FormGridWidget {

    constructor(container, config) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;
        this.id = config.id || ('fgw_' + Math.random().toString(36).slice(2, 8));

        this.config = Object.assign({
            masterViewCode: null,
            detailViewCode: null,
            masterPkeyColumn: '',
            detailFkeyColumn: '',
            masterListColumns: [],   // 左上清單顯示的欄位
            detailPageSize: 5,
            numberingRuleSc: null,    // numbering 規則 SC (null = auto+1)
            title: '',
            allowCreate: true,
            allowEdit: true,
            allowDelete: true,
            contextOutputs: [],
            contextInputs: [],
        }, config);

        // 狀態
        this.masterViewConfig = null;
        this.detailViewConfig = null;
        this.masterRows = [];         // Master 簡式清單資料
        this.selectedMasterRowId = null;
        this.selectedMasterData = null; // 選中 master 的完整資料
        this.detailRows = [];
        this.detailPagination = { page: 1, pages: 0, total: 0, per_page: 5 };
        this.detailSortCol = '';
        this.detailSortDir = 'ASC';

        // 三態: 'list' | 'view' | 'edit'
        this.mode = 'list';
        this.isLocked = false;

        // Lookup 映射
        this._masterLookupMaps = {};
        this._detailLookupMaps = {};

        // DOM 快取
        this._els = {};

        // Modal 狀態
        this._modalOverlay = null;

        // 外部篩選 (PageContext input)
        this._externalFilters = {};
    }

    // ===== 初始化 =====

    async init() {
        // PageContext 登錄
        if (typeof PageContext !== 'undefined') {
            PageContext.register(this.id);
            const outputKeys = (this.config.contextOutputs || []).map(o => o.contextKey);
            if (outputKeys.length > 0) {
                PageContext.registerOutputKeys(this.id, outputKeys);
            }
            for (const input of (this.config.contextInputs || [])) {
                PageContext.subscribe(input.contextKey, this.id, (key, value) => {
                    this._onContextChange(key, value);
                });
            }
        }

        console.log('[FORMGRID] init config:', JSON.stringify({
            masterViewCode: this.config.masterViewCode,
            detailViewCode: this.config.detailViewCode,
            masterPkeyColumn: this.config.masterPkeyColumn,
            detailFkeyColumn: this.config.detailFkeyColumn,
            masterListColumns: this.config.masterListColumns,
        }));

        if (!this.config.masterViewCode) {
            this._renderEmpty('未設定 Master 資料來源');
            return;
        }

        this._renderSkeleton();

        // 並行載入 master + detail view config
        await Promise.all([
            this._loadMasterViewConfig(),
            this.config.detailViewCode ? this._loadDetailViewConfig() : Promise.resolve(),
        ]);

        if (!this.masterViewConfig) return;

        // 載入 lookup
        await Promise.all([
            this._loadLookupMaps(this.masterViewConfig, this._masterLookupMaps),
            this.detailViewConfig ? this._loadLookupMaps(this.detailViewConfig, this._detailLookupMaps) : Promise.resolve(),
        ]);

        this.detailPagination.per_page = this.config.detailPageSize || 5;

        // 載入 Master 清單
        await this._loadMasterList();
    }

    destroy() {
        this._closeModal();
        if (typeof PageContext !== 'undefined') {
            PageContext.unregister(this.id);
        }
        if (this.container) {
            this.container.innerHTML = '';
        }
    }

    getConfig() {
        return Object.assign({}, this.config);
    }

    updateConfig(newConfig) {
        Object.assign(this.config, newConfig);
        this.destroy();
        this.init();
    }

    // ===== PageContext =====

    _onContextChange(key, value) {
        if (typeof PageContext !== 'undefined') {
            PageContext.clearWidgetOutputs(this.id);
        }
        this._rebuildFiltersFromContext();
        const hasValue = Object.values(this._externalFilters).some(
            v => v !== null && v !== undefined && v !== ''
        );
        if (hasValue) {
            this.selectedMasterRowId = null;
            this.selectedMasterData = null;
            this.mode = 'list';
            this._loadMasterList();
        } else {
            this.masterRows = [];
            this._renderMasterList();
            this._renderMasterDetail();
            this._renderDetailTable();
        }
    }

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

    _emitMasterSelect(masterData) {
        if (typeof PageContext === 'undefined') return;
        for (const output of (this.config.contextOutputs || [])) {
            if (output.event === 'row-select') {
                const value = masterData ? masterData[output.sourceColumn] : null;
                PageContext.set(output.contextKey, value, this.id);
            }
        }
    }

    // ===== Context Headers (寫操作用) =====

    _buildContextHeaders() {
        const headers = {};
        if (this.config._siteMapNodeSc && this.config._subSystemSc) {
            headers['X-SiteMap-Node'] = this.config._siteMapNodeSc;
            headers['X-SubSystem-SC'] = this.config._subSystemSc;
        }
        if (this.id) {
            headers['X-Widget-Id'] = this.id;
        }
        return headers;
    }

    // ===== 資料載入 =====

    async _loadMasterViewConfig() {
        try {
            const res = await fetch(window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode);
            const data = await res.json();
            if (data.success) {
                this.masterViewConfig = data.data;
            } else {
                this._renderEmpty('Master 載入失敗: ' + (data.error || ''));
            }
        } catch (e) {
            this._renderEmpty('Master 載入失敗: ' + e.message);
        }
    }

    async _loadDetailViewConfig() {
        try {
            const res = await fetch(window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode);
            const data = await res.json();
            if (data.success) {
                this.detailViewConfig = data.data;
            }
        } catch (e) {
            console.error('[FormGridWidget] loadDetailViewConfig error:', e);
        }
    }

    async _loadLookupMaps(viewConfig, targetMap) {
        if (!viewConfig || !viewConfig.columns_config) return;
        const lookupCols = viewConfig.columns_config.filter(c => c.lookup_category_code);
        if (lookupCols.length === 0) return;

        const codes = [...new Set(lookupCols.map(c => c.lookup_category_code))];
        const fetches = codes.map(code =>
            fetch(window.__BP + '/api/lookup/by-code/' + encodeURIComponent(code))
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const map = {};
                        (data.data || []).forEach(item => { map[item.code] = item.label; });
                        return { code, map };
                    }
                    return { code, map: {} };
                })
                .catch(() => ({ code, map: {} }))
        );

        const results = await Promise.all(fetches);
        const categoryMaps = {};
        results.forEach(r => { categoryMaps[r.code] = r.map; });

        for (const col of lookupCols) {
            targetMap[col.column] = categoryMaps[col.lookup_category_code] || {};
        }
    }

    // ===== Master List 載入 =====

    async _loadMasterList() {
        if (!this.masterViewConfig) return;

        try {
            let url = window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode + '/rows'
                + '?page=1&per_page=200';

            // 排序: 優先用 update_date (若欄位存在)，否則用 view 預設
            const hasSortCol = (this.masterViewConfig.columns_config || []).some(
                c => c.column === 'update_date'
            );
            if (hasSortCol) {
                url += '&sort=update_date&dir=DESC';
            } else if (this.masterViewConfig.default_sort_column) {
                url += '&sort=' + this.masterViewConfig.default_sort_column
                    + '&dir=' + (this.masterViewConfig.default_sort_dir || 'DESC');
            }

            // 附加外部篩選
            for (const [col, val] of Object.entries(this._externalFilters)) {
                if (val !== null && val !== undefined && val !== '') {
                    url += '&filter_' + encodeURIComponent(col) + '=' + encodeURIComponent(val);
                }
            }
            // 子系統篩選
            const sysFilters = this.config._subSystemFilters || {};
            for (const [col, val] of Object.entries(sysFilters)) {
                if (val !== null && val !== undefined && val !== '') {
                    url += '&filter_' + encodeURIComponent(col) + '=' + encodeURIComponent(val);
                }
            }

            const res = await fetch(url);
            const data = await res.json();
            if (data.success) {
                this.masterRows = data.data.rows || [];
            }
        } catch (e) {
            console.error('[FormGridWidget] loadMasterList error:', e);
        }

        this._renderMasterList();
        this._renderMasterDetail();
        this._renderDetailTable();
    }

    // ===== Detail 載入 =====

    async _loadDetailRows(page) {
        if (!this.detailViewConfig || !this.selectedMasterData) return;
        if (page !== undefined) this.detailPagination.page = page;

        const pkeyCol = this.config.masterPkeyColumn;
        const fkeyCol = this.config.detailFkeyColumn;
        const pkeyVal = this.selectedMasterData[pkeyCol];

        console.log('[FORMGRID] _loadDetailRows:', {
            pkeyCol, fkeyCol, pkeyVal,
            masterKeys: Object.keys(this.selectedMasterData),
            detailViewCode: this.config.detailViewCode,
        });

        if (!pkeyVal && pkeyVal !== 0) {
            console.warn('[FORMGRID] pkeyVal is empty, clearing detail.');
            this.detailRows = [];
            this._renderDetailTableBody();
            return;
        }

        try {
            let url = window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode + '/rows'
                + '?page=' + this.detailPagination.page
                + '&per_page=' + this.detailPagination.per_page;

            // FKey 篩選
            url += '&filter_' + encodeURIComponent(fkeyCol) + '=' + encodeURIComponent(pkeyVal);

            if (this.detailSortCol) {
                url += '&sort=' + this.detailSortCol + '&dir=' + this.detailSortDir;
            }

            const res = await fetch(url);
            const data = await res.json();
            if (data.success) {
                this.detailRows = data.data.rows || [];
                this.detailPagination.page = data.data.page;
                this.detailPagination.pages = data.data.pages;
                this.detailPagination.total = data.data.total;
            }
        } catch (e) {
            console.error('[FormGridWidget] loadDetailRows error:', e);
        }

        this._renderDetailTableBody();
    }

    // ===== Master 選擇 =====

    async _selectMaster(rowId) {
        if (!rowId) return;
        this.selectedMasterRowId = rowId;

        // 載入完整 Master 資料
        try {
            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode + '/rows/' + rowId
            );
            const data = await res.json();
            if (data.success) {
                this.selectedMasterData = data.data || {};
                this.isLocked = !!this.selectedMasterData.is_locked;
                this.mode = 'view';
                this._emitMasterSelect(this.selectedMasterData);
            }
        } catch (e) {
            console.error('[FormGridWidget] selectMaster error:', e);
        }

        this._renderMasterList();
        this._renderMasterDetail();
        await this._loadDetailRows(1);
    }

    // ===== DOM: 骨架 =====

    _renderSkeleton() {
        const c = this.container;
        c.innerHTML = '';
        c.classList.add('fgw-root');

        // Header
        const header = document.createElement('div');
        header.className = 'fgw-header';
        const titleSpan = document.createElement('span');
        titleSpan.className = 'fgw-title';
        titleSpan.textContent = this.config.title || 'FORMGRID';
        header.appendChild(titleSpan);
        const toolbar = document.createElement('div');
        toolbar.className = 'fgw-toolbar';
        header.appendChild(toolbar);
        c.appendChild(header);
        this._els.header = header;
        this._els.title = titleSpan;
        this._els.toolbar = toolbar;

        // Master 區域
        const masterArea = document.createElement('div');
        masterArea.className = 'fgw-master-area';

        // 左: Master List
        const masterList = document.createElement('div');
        masterList.className = 'fgw-master-list';
        const mlHeader = document.createElement('div');
        mlHeader.className = 'fgw-ml-header';
        mlHeader.innerHTML = '<span>Master</span>';
        masterList.appendChild(mlHeader);
        const mlBody = document.createElement('div');
        mlBody.className = 'fgw-ml-body';
        masterList.appendChild(mlBody);
        masterArea.appendChild(masterList);
        this._els.mlHeader = mlHeader;
        this._els.mlBody = mlBody;

        // 右: Master Detail
        const masterDetail = document.createElement('div');
        masterDetail.className = 'fgw-master-detail';
        masterArea.appendChild(masterDetail);
        this._els.masterDetail = masterDetail;

        c.appendChild(masterArea);

        // Detail 區域
        const detailArea = document.createElement('div');
        detailArea.className = 'fgw-detail-area';
        const dtHeader = document.createElement('div');
        dtHeader.className = 'fgw-dt-header';
        dtHeader.innerHTML = '<span>Detail</span><div class="fgw-dt-toolbar"></div>';
        detailArea.appendChild(dtHeader);
        const dtBody = document.createElement('div');
        dtBody.className = 'fgw-dt-body';
        detailArea.appendChild(dtBody);
        this._els.dtHeader = dtHeader;
        this._els.dtToolbar = dtHeader.querySelector('.fgw-dt-toolbar');
        this._els.dtBody = dtBody;

        // Detail 分頁
        const dtPager = document.createElement('div');
        dtPager.className = 'fgw-dt-pager';
        dtPager.style.display = 'none';
        detailArea.appendChild(dtPager);
        this._els.dtPager = dtPager;

        c.appendChild(detailArea);

        // Master list 新增按鈕
        if (this.config.allowCreate) {
            const addBtn = document.createElement('button');
            addBtn.className = 'fgw-btn sm primary';
            addBtn.textContent = '+';
            addBtn.title = '新增 Master';
            addBtn.addEventListener('click', () => this._openMasterModal('create'));
            this._els.mlHeader.appendChild(addBtn);
        }
    }

    _renderEmpty(msg) {
        this.container.innerHTML = '';
        this.container.classList.add('fgw-root');
        const header = document.createElement('div');
        header.className = 'fgw-header';
        header.innerHTML = '<span class="fgw-title">FORMGRID</span>';
        this.container.appendChild(header);
        const el = document.createElement('div');
        el.className = 'fgw-empty';
        el.textContent = msg || '未設定資料來源';
        this.container.appendChild(el);
    }

    // ===== DOM: Master List =====

    _renderMasterList() {
        const body = this._els.mlBody;
        if (!body) return;
        body.innerHTML = '';

        if (this.masterRows.length === 0) {
            body.innerHTML = '<div class="fgw-ml-empty">尚無資料</div>';
            return;
        }

        const listCols = this.config.masterListColumns || [];
        const pkeyCol = this.config.masterPkeyColumn;

        for (const row of this.masterRows) {
            const item = document.createElement('div');
            item.className = 'fgw-ml-item';
            if (row._row_id === this.selectedMasterRowId) {
                item.classList.add('active');
            }

            // 主鍵
            const keySpan = document.createElement('div');
            keySpan.className = 'fgw-ml-key';
            keySpan.textContent = this._formatCell(row[pkeyCol], pkeyCol, this._masterLookupMaps) || row._row_id;

            // 鎖定標記
            if (row.is_locked) {
                const lockSpan = document.createElement('span');
                lockSpan.className = 'fgw-ml-lock';
                lockSpan.textContent = '[鎖定]';
                keySpan.appendChild(lockSpan);
            }
            item.appendChild(keySpan);

            // 次要欄位
            const subParts = [];
            for (const col of listCols) {
                if (col === pkeyCol) continue;
                const val = this._formatCell(row[col], col, this._masterLookupMaps);
                if (val) subParts.push(val);
            }
            if (subParts.length > 0) {
                const subSpan = document.createElement('div');
                subSpan.className = 'fgw-ml-sub';
                subSpan.textContent = subParts.join(' | ');
                item.appendChild(subSpan);
            }

            const _rowId = row._row_id;
            item.addEventListener('click', () => this._selectMaster(_rowId));
            body.appendChild(item);
        }
    }

    // ===== DOM: Master Detail (右上) =====

    _renderMasterDetail() {
        const area = this._els.masterDetail;
        if (!area) return;
        area.innerHTML = '';

        if (!this.selectedMasterData) {
            area.innerHTML = '<div class="fgw-md-placeholder">請從左側選擇一筆 Master 資料</div>';
            return;
        }

        // Toolbar
        const toolbar = document.createElement('div');
        toolbar.className = 'fgw-md-toolbar';

        // 鎖定狀態標記
        if (this.isLocked) {
            const badge = document.createElement('span');
            badge.className = 'fgw-locked-badge';
            badge.textContent = '已鎖定';
            toolbar.appendChild(badge);
        } else {
            const badge = document.createElement('span');
            badge.className = 'fgw-unlocked-badge';
            badge.textContent = '未鎖定';
            toolbar.appendChild(badge);
        }

        // 模式切換 / 操作按鈕
        if (this.mode === 'view' && !this.isLocked && this.config.allowEdit) {
            const editBtn = document.createElement('button');
            editBtn.className = 'fgw-btn sm primary';
            editBtn.textContent = '編輯';
            editBtn.addEventListener('click', () => {
                this.mode = 'edit';
                this._renderMasterDetail();
                this._renderDetailTable();
            });
            toolbar.appendChild(editBtn);
        }
        if (this.mode === 'edit') {
            const saveBtn = document.createElement('button');
            saveBtn.className = 'fgw-btn sm primary';
            saveBtn.textContent = '儲存';
            saveBtn.addEventListener('click', () => this._saveMasterEdit(saveBtn));
            toolbar.appendChild(saveBtn);

            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'fgw-btn sm';
            cancelBtn.textContent = '取消';
            cancelBtn.addEventListener('click', () => {
                this.mode = 'view';
                this._selectMaster(this.selectedMasterRowId);
            });
            toolbar.appendChild(cancelBtn);
        }

        // 鎖定/解鎖 按鈕
        if (this.config.allowEdit && this.mode === 'view') {
            const lockBtn = document.createElement('button');
            lockBtn.className = 'fgw-btn sm ' + (this.isLocked ? 'warn' : '');
            lockBtn.textContent = this.isLocked ? '解鎖' : '鎖定';
            lockBtn.addEventListener('click', () => this._toggleLock());
            toolbar.appendChild(lockBtn);
        }

        // 刪除 (未鎖定 + view 模式)
        if (this.mode === 'view' && !this.isLocked && this.config.allowDelete) {
            const delBtn = document.createElement('button');
            delBtn.className = 'fgw-btn sm danger';
            delBtn.textContent = '刪除';
            delBtn.addEventListener('click', () => this._deleteMaster());
            toolbar.appendChild(delBtn);
        }

        area.appendChild(toolbar);

        // 欄位區域
        const fields = document.createElement('div');
        fields.className = 'fgw-md-fields';

        const formCols = this._getMasterFormColumns();
        const isEditing = this.mode === 'edit';

        for (const col of formCols) {
            // 不顯示 is_locked 欄位（由 UI 按鈕控制）
            if (col.column === 'is_locked') continue;

            const field = document.createElement('div');
            field.className = 'fgw-field';

            const label = document.createElement('div');
            label.className = 'fgw-field-label';
            label.textContent = col.label || col.column;
            if (!col.nullable && !col.is_pk && !col.is_system && isEditing) {
                const req = document.createElement('span');
                req.className = 'fgw-field-required';
                req.textContent = '*';
                label.appendChild(req);
            }
            field.appendChild(label);

            const valueWrap = document.createElement('div');
            valueWrap.className = 'fgw-field-value';

            const value = this.selectedMasterData[col.column];
            const isPk = col.is_pk || false;
            const isSystem = col.is_system || false;
            const isReadonly = col.readonly || isPk || isSystem;

            if (isEditing && !isReadonly) {
                this._renderFieldInput(valueWrap, col, value, this._masterLookupMaps);
            } else {
                const text = document.createElement('div');
                text.className = 'fgw-field-text';
                text.textContent = this._formatCell(value, col.column, this._masterLookupMaps);
                valueWrap.appendChild(text);
            }

            field.appendChild(valueWrap);
            fields.appendChild(field);
        }

        area.appendChild(fields);
    }

    // ===== DOM: Detail Table (下方) =====

    _renderDetailTable() {
        const body = this._els.dtBody;
        if (!body) return;

        if (!this.selectedMasterData || !this.detailViewConfig) {
            body.innerHTML = '<div class="fgw-dt-empty">' +
                (this.selectedMasterData ? '未設定 Detail 資料來源' : '請先選擇 Master') + '</div>';
            this._els.dtPager.style.display = 'none';

            // 清除 detail toolbar
            if (this._els.dtToolbar) this._els.dtToolbar.innerHTML = '';
            return;
        }

        // Detail toolbar: 新增按鈕
        if (this._els.dtToolbar) {
            this._els.dtToolbar.innerHTML = '';
            if (this.config.allowCreate && !this.isLocked) {
                const addBtn = document.createElement('button');
                addBtn.className = 'fgw-btn sm primary';
                addBtn.textContent = '+新增';
                addBtn.addEventListener('click', () => this._openDetailModal('create'));
                this._els.dtToolbar.appendChild(addBtn);
            }
        }

        this._renderDetailTableBody();
    }

    _renderDetailTableBody() {
        const body = this._els.dtBody;
        if (!body) return;

        const cols = this._getDetailDisplayColumns();
        const canEdit = this.config.allowEdit && !this.isLocked;
        const canDelete = this.config.allowDelete && !this.isLocked;
        const hasActions = canEdit || canDelete;

        if (this.detailRows.length === 0) {
            body.innerHTML = '<div class="fgw-dt-empty">尚無明細資料</div>';
            if (this._els.dtPager) this._els.dtPager.style.display = 'none';
            return;
        }

        // 建表
        const table = document.createElement('table');
        table.className = 'fgw-dt-table';

        // thead
        const thead = document.createElement('thead');
        let headHtml = '<tr>';
        for (const col of cols) {
            const isActive = this.detailSortCol === col.column;
            const arrow = isActive ? (this.detailSortDir === 'ASC' ? ' ^' : ' v') : '';
            headHtml += '<th class="fgw-sortable" data-col="' + col.column + '">'
                + (col.label || col.column)
                + '<span class="fgw-sort-arrow">' + arrow + '</span></th>';
        }
        if (hasActions) headHtml += '<th class="fgw-dt-actions-th">操作</th>';
        headHtml += '</tr>';
        thead.innerHTML = headHtml;
        table.appendChild(thead);

        // 排序事件
        thead.querySelectorAll('.fgw-sortable').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.dataset.col;
                if (this.detailSortCol === col) {
                    this.detailSortDir = this.detailSortDir === 'ASC' ? 'DESC' : 'ASC';
                } else {
                    this.detailSortCol = col;
                    this.detailSortDir = 'ASC';
                }
                this._loadDetailRows(1);
            });
        });

        // tbody
        const tbody = document.createElement('tbody');
        for (const row of this.detailRows) {
            const tr = document.createElement('tr');

            for (const col of cols) {
                const td = document.createElement('td');
                td.textContent = this._formatCell(row[col.column], col.column, this._detailLookupMaps);
                tr.appendChild(td);
            }

            if (hasActions) {
                const td = document.createElement('td');
                td.className = 'fgw-dt-actions';
                if (canEdit) {
                    const btn = document.createElement('button');
                    btn.className = 'fgw-btn sm';
                    btn.textContent = '編輯';
                    const _rid = row._row_id;
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._openDetailModal('edit', _rid);
                    });
                    td.appendChild(btn);
                }
                if (canDelete) {
                    const btn = document.createElement('button');
                    btn.className = 'fgw-btn sm danger';
                    btn.textContent = '刪除';
                    const _rid = row._row_id;
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        this._deleteDetail(_rid);
                    });
                    td.appendChild(btn);
                }
                tr.appendChild(td);
            }

            tbody.appendChild(tr);
        }
        table.appendChild(tbody);

        body.innerHTML = '';
        body.appendChild(table);

        // 分頁
        this._renderDetailPager();
    }

    _renderDetailPager() {
        const pager = this._els.dtPager;
        if (!pager) return;
        if (this.detailPagination.pages <= 1) {
            pager.style.display = 'none';
            return;
        }
        pager.style.display = 'flex';
        pager.innerHTML =
            '<span>共 ' + this.detailPagination.total + ' 筆，第 '
            + this.detailPagination.page + '/' + this.detailPagination.pages + ' 頁</span>'
            + '<div class="fgw-dt-page-btns">'
            + '<button class="fgw-btn sm fgw-prev" ' + (this.detailPagination.page <= 1 ? 'disabled' : '') + '>上一頁</button>'
            + '<button class="fgw-btn sm fgw-next" ' + (this.detailPagination.page >= this.detailPagination.pages ? 'disabled' : '') + '>下一頁</button>'
            + '</div>';
        pager.querySelector('.fgw-prev')?.addEventListener('click', () => {
            if (this.detailPagination.page > 1) this._loadDetailRows(this.detailPagination.page - 1);
        });
        pager.querySelector('.fgw-next')?.addEventListener('click', () => {
            if (this.detailPagination.page < this.detailPagination.pages) this._loadDetailRows(this.detailPagination.page + 1);
        });
    }

    // ===== 欄位操作 =====

    _getMasterFormColumns() {
        if (!this.masterViewConfig || !this.masterViewConfig.columns_config) return [];
        return this.masterViewConfig.columns_config
            .filter(c => c.visible_in_form)
            .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
    }

    _getDetailDisplayColumns() {
        if (!this.detailViewConfig || !this.detailViewConfig.columns_config) return [];
        return this.detailViewConfig.columns_config
            .filter(c => c.visible && c.column !== this.config.detailFkeyColumn)
            .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
    }

    _getDetailFormColumns() {
        if (!this.detailViewConfig || !this.detailViewConfig.columns_config) return [];
        return this.detailViewConfig.columns_config
            .filter(c => c.visible_in_form)
            .sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999));
    }

    _formatCell(value, columnName, lookupMaps) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'boolean') return value ? 'Y' : 'N';
        if (typeof value === 'object') return JSON.stringify(value);
        const s = String(value);
        if (columnName && lookupMaps && lookupMaps[columnName]) {
            const label = lookupMaps[columnName][s];
            if (label) return label;
        }
        return s.length > 60 ? s.substring(0, 60) + '...' : s;
    }

    _isNumericType(dbType) {
        var numTypes = ['INTEGER', 'BIGINT', 'SMALLINT', 'INT', 'INT4', 'INT8', 'INT2',
                        'NUMERIC', 'DECIMAL', 'REAL', 'FLOAT', 'DOUBLE', 'FLOAT4', 'FLOAT8'];
        for (var i = 0; i < numTypes.length; i++) {
            if (dbType.indexOf(numTypes[i]) >= 0) return true;
        }
        return false;
    }

    // ===== 欄位渲染 (共用: Master Detail 和 Modal 表單) =====

    _renderFieldInput(container, col, value, lookupMaps) {
        const colName = col.column;
        const dbType = (col.db_type || '').toUpperCase();

        if (col.lookup_category_code && lookupMaps[colName]) {
            const select = document.createElement('select');
            select.name = colName;
            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = '-- 請選擇 --';
            select.appendChild(emptyOpt);
            const map = lookupMaps[colName];
            for (const [code, lbl] of Object.entries(map)) {
                const opt = document.createElement('option');
                opt.value = code;
                opt.textContent = lbl;
                if (String(value) === code) opt.selected = true;
                select.appendChild(opt);
            }
            container.appendChild(select);
        } else if (dbType === 'BOOLEAN' || dbType === 'BOOL') {
            const wrap = document.createElement('div');
            wrap.className = 'fgw-check-wrap';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.name = colName;
            cb.checked = value === true || value === 'true' || value === 't';
            const cbLabel = document.createElement('span');
            cbLabel.textContent = cb.checked ? 'Y' : 'N';
            cb.addEventListener('change', () => { cbLabel.textContent = cb.checked ? 'Y' : 'N'; });
            wrap.appendChild(cb);
            wrap.appendChild(cbLabel);
            container.appendChild(wrap);
        } else if (dbType === 'DATE') {
            const input = document.createElement('input');
            input.type = 'date';
            input.name = colName;
            if (value) input.value = String(value).substring(0, 10);
            container.appendChild(input);
        } else if (dbType.indexOf('TIMESTAMP') >= 0) {
            const input = document.createElement('input');
            input.type = 'datetime-local';
            input.name = colName;
            if (value) input.value = String(value).substring(0, 16);
            container.appendChild(input);
        } else if (this._isNumericType(dbType)) {
            const input = document.createElement('input');
            input.type = 'number';
            input.name = colName;
            if (value !== '' && value !== null && value !== undefined) input.value = value;
            if (dbType.indexOf('NUMERIC') >= 0 || dbType.indexOf('DECIMAL') >= 0) input.step = 'any';
            container.appendChild(input);
        } else if (dbType === 'TEXT' || dbType === 'JSONB' || dbType === 'JSON') {
            const ta = document.createElement('textarea');
            ta.name = colName;
            if (value && typeof value === 'object') {
                ta.value = JSON.stringify(value, null, 2);
            } else {
                ta.value = value !== null && value !== undefined ? String(value) : '';
            }
            container.appendChild(ta);
        } else {
            const input = document.createElement('input');
            input.type = 'text';
            input.name = colName;
            input.value = value !== null && value !== undefined ? String(value) : '';
            container.appendChild(input);
        }
    }

    // ===== 表單值收集 =====

    _collectFormValues(container, formCols) {
        const data = {};
        for (const col of formCols) {
            const colName = col.column;
            if (col.is_pk || col.is_system || col.readonly) continue;

            const dbType = (col.db_type || '').toUpperCase();
            const el = container.querySelector('[name="' + colName + '"]');
            if (!el) continue;

            if (dbType === 'BOOLEAN' || dbType === 'BOOL') {
                data[colName] = el.checked;
            } else if (dbType === 'JSONB' || dbType === 'JSON') {
                const raw = el.value.trim();
                if (raw) {
                    try { data[colName] = JSON.parse(raw); }
                    catch (e) { alert('JSON 格式錯誤: ' + col.label); return null; }
                } else {
                    data[colName] = null;
                }
            } else if (this._isNumericType(dbType)) {
                const raw = el.value.trim();
                if (raw !== '') {
                    data[colName] = Number(raw);
                    if (isNaN(data[colName])) { alert('數值格式錯誤: ' + col.label); return null; }
                } else {
                    data[colName] = null;
                }
            } else {
                const val = el.value;
                data[colName] = val === '' ? null : val;
            }
        }
        return data;
    }

    // ===== Master CRUD =====

    async _saveMasterEdit(saveBtn) {
        const formCols = this._getMasterFormColumns().filter(c => c.column !== 'is_locked');
        const fieldsContainer = this._els.masterDetail.querySelector('.fgw-md-fields');
        if (!fieldsContainer) return;

        const data = this._collectFormValues(fieldsContainer, formCols);
        if (data === null) return; // 驗證失敗

        saveBtn.disabled = true;
        saveBtn.textContent = '儲存中...';

        try {
            const headers = Object.assign(
                { 'Content-Type': 'application/json' },
                this._buildContextHeaders()
            );
            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode
                + '/rows/' + this.selectedMasterRowId,
                { method: 'PUT', headers, body: JSON.stringify(data) }
            );
            const result = await res.json();
            if (result.success) {
                this.mode = 'view';
                await this._loadMasterList();
                await this._selectMaster(this.selectedMasterRowId);
            } else {
                alert('儲存失敗: ' + (result.error || ''));
                saveBtn.disabled = false;
                saveBtn.textContent = '儲存';
            }
        } catch (e) {
            alert('儲存失敗: ' + e.message);
            saveBtn.disabled = false;
            saveBtn.textContent = '儲存';
        }
    }

    async _toggleLock() {
        if (!this.selectedMasterRowId) return;
        const newLocked = !this.isLocked;
        const action = newLocked ? '鎖定' : '解鎖';
        if (!confirm('確定要' + action + '此筆資料嗎？' + (newLocked ? '鎖定後將無法修改。' : ''))) return;

        try {
            const headers = Object.assign(
                { 'Content-Type': 'application/json' },
                this._buildContextHeaders()
            );
            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode
                + '/rows/' + this.selectedMasterRowId,
                { method: 'PUT', headers, body: JSON.stringify({ is_locked: newLocked }) }
            );
            const result = await res.json();
            if (result.success) {
                await this._loadMasterList();
                await this._selectMaster(this.selectedMasterRowId);
            } else {
                alert(action + '失敗: ' + (result.error || ''));
            }
        } catch (e) {
            alert(action + '失敗: ' + e.message);
        }
    }

    async _deleteMaster() {
        if (!confirm('確定要刪除此筆 Master 資料嗎？所有關聯的 Detail 資料也將被刪除。')) return;

        try {
            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode
                + '/rows/' + this.selectedMasterRowId,
                { method: 'DELETE', headers: this._buildContextHeaders() }
            );
            const result = await res.json();
            if (result.success) {
                this.selectedMasterRowId = null;
                this.selectedMasterData = null;
                this.mode = 'list';
                this.detailRows = [];
                this._emitMasterSelect(null);
                await this._loadMasterList();
            } else {
                alert('刪除失敗: ' + (result.error || ''));
            }
        } catch (e) {
            alert('刪除失敗: ' + e.message);
        }
    }

    // ===== Master Modal (新增) =====

    async _openMasterModal(mode) {
        if (this._modalOverlay) return;

        const title = '新增 Master - ' + (this.config.title || '');
        const formCols = this._getMasterFormColumns().filter(c => c.column !== 'is_locked');

        // 若有 numbering 規則，先取得建議值
        let suggestedPkey = null;
        const pkeyCol = this.config.masterPkeyColumn;
        if (this.config.numberingRuleSc && pkeyCol) {
            try {
                const res = await fetch(window.__BP + '/api/numbering/next?rule_sc=' + this.config.numberingRuleSc);
                const data = await res.json();
                if (data.success) suggestedPkey = data.number;
            } catch (e) { /* 忽略，使用者手動輸入 */ }
        }

        const { overlay, body, saveBtn } = this._createModal(title);

        // 渲染表單
        for (const col of formCols) {
            if (col.is_pk || col.is_system) continue;

            const field = document.createElement('div');
            field.className = 'fgw-form-field';

            const label = document.createElement('label');
            label.className = 'fgw-form-label';
            label.textContent = col.label || col.column;
            if (!col.nullable) {
                const req = document.createElement('span');
                req.style.color = '#dc2626';
                req.style.marginLeft = '2px';
                req.textContent = '*';
                label.appendChild(req);
            }
            field.appendChild(label);

            // PKey 欄位帶建議值
            let defaultValue = '';
            if (col.column === pkeyCol && suggestedPkey) {
                defaultValue = suggestedPkey;
            }

            const valueWrap = document.createElement('div');
            this._renderFieldInput(valueWrap, col, defaultValue, this._masterLookupMaps);

            // PKey 建議值提示
            if (col.column === pkeyCol && suggestedPkey) {
                const hint = document.createElement('div');
                hint.className = 'fgw-form-hint';
                hint.textContent = '建議編號 (可手動修改)';
                valueWrap.appendChild(hint);
            }

            field.appendChild(valueWrap);
            body.appendChild(field);
        }

        saveBtn.disabled = false;
        saveBtn.addEventListener('click', async () => {
            const data = this._collectFormValues(body, formCols.filter(c => !c.is_pk && !c.is_system));
            if (data === null) return;

            // 若使用 numbering，消耗編號
            if (this.config.numberingRuleSc && pkeyCol && data[pkeyCol] === suggestedPkey) {
                try {
                    await fetch(window.__BP + '/api/numbering/consume', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ rule_sc: this.config.numberingRuleSc }),
                    });
                } catch (e) { /* 忽略 */ }
            }

            saveBtn.disabled = true;
            saveBtn.textContent = '儲存中...';

            try {
                const headers = Object.assign(
                    { 'Content-Type': 'application/json' },
                    this._buildContextHeaders()
                );
                const res = await fetch(
                    window.__BP + '/api/nocode-builder/views/' + this.config.masterViewCode + '/rows',
                    { method: 'POST', headers, body: JSON.stringify(data) }
                );
                const result = await res.json();
                if (result.success) {
                    this._closeModal();
                    await this._loadMasterList();
                } else {
                    alert('新增失敗: ' + (result.error || ''));
                    saveBtn.disabled = false;
                    saveBtn.textContent = '儲存';
                }
            } catch (e) {
                alert('新增失敗: ' + e.message);
                saveBtn.disabled = false;
                saveBtn.textContent = '儲存';
            }
        });
    }

    // ===== Detail Modal (新增/編輯) =====

    async _openDetailModal(mode, rowId) {
        if (this._modalOverlay) return;

        const isEdit = mode === 'edit';
        const title = (isEdit ? '編輯' : '新增') + ' Detail';
        const formCols = this._getDetailFormColumns();

        const { overlay, body, saveBtn } = this._createModal(title);

        let rowData = {};
        if (isEdit && rowId) {
            try {
                const res = await fetch(
                    window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode + '/rows/' + rowId
                );
                const data = await res.json();
                if (data.success) rowData = data.data || {};
            } catch (e) {
                body.innerHTML = '<div class="fgw-form-error">載入資料失敗</div>';
                return;
            }
        }

        // 渲染表單
        const fkeyCol = this.config.detailFkeyColumn;
        const pkeyCol = this.config.masterPkeyColumn;
        const pkeyVal = this.selectedMasterData ? this.selectedMasterData[pkeyCol] : '';

        for (const col of formCols) {
            if (col.is_pk || col.is_system) continue;

            const field = document.createElement('div');
            field.className = 'fgw-form-field';

            const label = document.createElement('label');
            label.className = 'fgw-form-label';
            label.textContent = col.label || col.column;
            if (!col.nullable) {
                const req = document.createElement('span');
                req.style.color = '#dc2626';
                req.style.marginLeft = '2px';
                req.textContent = '*';
                label.appendChild(req);
            }
            field.appendChild(label);

            const valueWrap = document.createElement('div');
            let value = isEdit ? (rowData[col.column] ?? '') : '';

            // FKey 欄位自動填入
            if (col.column === fkeyCol) {
                value = isEdit ? (rowData[col.column] ?? pkeyVal) : pkeyVal;
                const input = document.createElement('input');
                input.type = 'text';
                input.name = col.column;
                input.value = value;
                input.disabled = true;
                valueWrap.appendChild(input);
                const hint = document.createElement('div');
                hint.className = 'fgw-form-hint';
                hint.textContent = '自動填入 (Master PKey)';
                valueWrap.appendChild(hint);
            } else {
                this._renderFieldInput(valueWrap, col, value, this._detailLookupMaps);
            }

            field.appendChild(valueWrap);
            body.appendChild(field);
        }

        saveBtn.disabled = false;
        saveBtn.addEventListener('click', async () => {
            const data = this._collectFormValues(body, formCols.filter(c => !c.is_pk && !c.is_system));
            if (data === null) return;

            // 確保 FKey 填入
            if (fkeyCol) {
                data[fkeyCol] = pkeyVal;
            }

            saveBtn.disabled = true;
            saveBtn.textContent = '儲存中...';

            try {
                let url, method;
                if (isEdit) {
                    url = window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode + '/rows/' + rowId;
                    method = 'PUT';
                } else {
                    url = window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode + '/rows';
                    method = 'POST';
                }

                const headers = Object.assign(
                    { 'Content-Type': 'application/json' },
                    this._buildContextHeaders()
                );

                // 鎖定檢查 header
                headers['X-Lock-Check-View'] = this.config.masterViewCode;
                headers['X-Lock-Check-RowId'] = this.selectedMasterRowId;

                const res = await fetch(url, { method, headers, body: JSON.stringify(data) });
                const result = await res.json();
                if (result.success) {
                    this._closeModal();
                    await this._loadDetailRows(isEdit ? this.detailPagination.page : 1);
                } else {
                    alert('儲存失敗: ' + (result.error || ''));
                    saveBtn.disabled = false;
                    saveBtn.textContent = '儲存';
                }
            } catch (e) {
                alert('儲存失敗: ' + e.message);
                saveBtn.disabled = false;
                saveBtn.textContent = '儲存';
            }
        });
    }

    async _deleteDetail(rowId) {
        if (!confirm('確定要刪除此筆 Detail 資料嗎？')) return;

        try {
            const headers = Object.assign({}, this._buildContextHeaders());
            headers['X-Lock-Check-View'] = this.config.masterViewCode;
            headers['X-Lock-Check-RowId'] = this.selectedMasterRowId;

            const res = await fetch(
                window.__BP + '/api/nocode-builder/views/' + this.config.detailViewCode + '/rows/' + rowId,
                { method: 'DELETE', headers }
            );
            const result = await res.json();
            if (result.success) {
                await this._loadDetailRows();
            } else {
                alert('刪除失敗: ' + (result.error || ''));
            }
        } catch (e) {
            alert('刪除失敗: ' + e.message);
        }
    }

    // ===== Modal 建立/關閉 =====

    _createModal(title) {
        const overlay = document.createElement('div');
        overlay.className = 'fgw-modal-overlay';

        const modal = document.createElement('div');
        modal.className = 'fgw-modal';

        const header = document.createElement('div');
        header.className = 'fgw-modal-header';
        const titleEl = document.createElement('span');
        titleEl.className = 'fgw-modal-title';
        titleEl.textContent = title;
        const closeBtn = document.createElement('button');
        closeBtn.className = 'fgw-modal-close';
        closeBtn.innerHTML = '&#215;';
        closeBtn.addEventListener('click', () => this._closeModal());
        header.appendChild(titleEl);
        header.appendChild(closeBtn);
        modal.appendChild(header);

        const body = document.createElement('div');
        body.className = 'fgw-modal-body';
        modal.appendChild(body);

        const footer = document.createElement('div');
        footer.className = 'fgw-modal-footer';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'fgw-btn';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', () => this._closeModal());
        const saveBtn = document.createElement('button');
        saveBtn.className = 'fgw-btn primary';
        saveBtn.textContent = '儲存';
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

        return { overlay, body, saveBtn };
    }

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
}
