/**
 * GridLayoutEditor - Matrix-based Grid Layout Editor
 *
 * Based on proven matrix approach: 2D array tracks cell IDs,
 * colWidths/rowHeights arrays for fr units, merge/split/undo/resize.
 *
 * Integrates with studio.js via class interface:
 *   - constructor(container, { rows, cols })
 *   - loadLayout(layoutJson v3) / toLayoutJson()
 *   - render()
 *   - onZoneSelect / onWidgetSelect / onChanged callbacks
 *   - addWidgetToSelected(type) / updateWidget(zoneId, config)
 *   - widgetMap, clearSelection()
 */
class GridLayoutEditor {

    constructor(container, options) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;

        const rows = (options && options.rows) || 4;
        const cols = (options && options.cols) || 4;

        // Core state (matrix-based)
        this.matrix = [];
        this.colWidths = [];
        this.rowHeights = [];
        this.nextId = 1;
        this.selected = new Set();  // selected region IDs
        this.history = [];
        this.MAX_HISTORY = 50;
        this.MAX_GRID = 50;

        // Drag selection state
        this._isDragging = false;
        this._didDrag = false;
        this._dragStart = null;
        this._dragCtrl = false;
        this._dragBase = new Set();

        // Resize handle state
        this._resizing = null;

        // Widget storage: regionId -> widget config
        this.widgetMap = {};

        // DataListWidget live instances: zoneKey -> DataListWidget
        this._dlwInstances = {};

        // Callbacks
        this.onZoneSelect = null;
        this.onWidgetSelect = null;
        this.onChanged = null;

        // DOM refs
        this._toolbar = null;
        this._gridWrapper = null;
        this._gridContainer = null;
        this._statusBar = null;
        this._modalOverlay = null;

        // Build shell
        this._buildShell();

        // Global mouseup
        this._onMouseUpBound = () => this._onMouseUp();
        document.addEventListener('mouseup', this._onMouseUpBound);

        // Keyboard
        this._onKeyDownBound = (e) => this._onKeyDown(e);
        document.addEventListener('keydown', this._onKeyDownBound);

        // Init grid
        this._initGrid(rows, cols);
    }

    // ===== Shell (toolbar + grid + status bar) =====

    _buildShell() {
        this.container.innerHTML = '';
        this.container.classList.add('gle-root');

        // Toolbar
        this._toolbar = document.createElement('div');
        this._toolbar.className = 'gle-toolbar';
        this._toolbar.innerHTML = `
            <div class="gle-tb-group">
                <label>列:</label>
                <input type="number" class="gle-input-rows" value="4" min="1" max="30">
                <label>欄:</label>
                <input type="number" class="gle-input-cols" value="4" min="1" max="30">
                <button class="gle-tb-btn primary" data-action="create">建立</button>
            </div>
            <div class="gle-tb-sep"></div>
            <div class="gle-tb-group">
                <button class="gle-tb-btn" data-action="merge" disabled>合併 <span class="gle-shortcut">M</span></button>
            </div>
            <div class="gle-tb-sep"></div>
            <div class="gle-tb-group">
                <label>拆分:</label>
                <button class="gle-tb-btn" data-action="split-h" disabled>左右</button>
                <button class="gle-tb-btn" data-action="split-v" disabled>上下</button>
                <button class="gle-tb-btn" data-action="split-2x2" disabled>田字</button>
                <button class="gle-tb-btn" data-action="split-custom" disabled>自訂</button>
            </div>
            <div class="gle-tb-sep"></div>
            <div class="gle-tb-group">
                <button class="gle-tb-btn" data-action="undo" disabled>復原 <span class="gle-shortcut">Ctrl+Z</span></button>
            </div>
        `;
        this.container.appendChild(this._toolbar);

        // Toolbar events
        this._toolbar.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn || btn.disabled) return;
            this._onToolbarAction(btn.dataset.action);
        });

        // Grid wrapper
        this._gridWrapper = document.createElement('div');
        this._gridWrapper.className = 'gle-wrapper';
        this.container.appendChild(this._gridWrapper);

        this._gridContainer = document.createElement('div');
        this._gridContainer.className = 'gle-grid';
        this._gridWrapper.appendChild(this._gridContainer);

        // Status bar
        this._statusBar = document.createElement('div');
        this._statusBar.className = 'gle-statusbar';
        this._statusBar.innerHTML = '<span class="gle-st-grid"></span><span class="gle-st-cells"></span><span class="gle-st-sel"></span>';
        this.container.appendChild(this._statusBar);

        // Custom split modal
        this._modalOverlay = document.createElement('div');
        this._modalOverlay.className = 'gle-modal-overlay';
        this._modalOverlay.innerHTML = `
            <div class="gle-modal">
                <h3>自訂拆分</h3>
                <div class="gle-modal-row"><label>列數:</label><input type="number" class="gle-split-r" value="2" min="1" max="20"></div>
                <div class="gle-modal-row"><label>欄數:</label><input type="number" class="gle-split-c" value="2" min="1" max="20"></div>
                <div class="gle-modal-actions">
                    <button class="gle-tb-btn" data-modal="cancel">取消</button>
                    <button class="gle-tb-btn primary" data-modal="confirm">拆分</button>
                </div>
            </div>
        `;
        this.container.appendChild(this._modalOverlay);

        this._modalOverlay.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-modal]');
            if (!btn) return;
            if (btn.dataset.modal === 'cancel') {
                this._modalOverlay.classList.remove('show');
            } else if (btn.dataset.modal === 'confirm') {
                this._doCustomSplit();
            }
        });

        // Click empty area to deselect
        this._gridWrapper.addEventListener('mousedown', (e) => {
            if (e.target === this._gridWrapper) {
                this.selected.clear();
                this._updateSelUI();
                this._updateButtons();
            }
        });
    }

    _onToolbarAction(action) {
        switch (action) {
            case 'create': this._createFromInput(); break;
            case 'merge': this._mergeSelected(); break;
            case 'split-h': this._splitSelected('h'); break;
            case 'split-v': this._splitSelected('v'); break;
            case 'split-2x2': this._splitSelected('2x2'); break;
            case 'split-custom': this._showCustomSplit(); break;
            case 'undo': this._doUndo(); break;
        }
    }

    // ===== Grid Init =====

    _createFromInput() {
        const r = this._clamp(parseInt(this._toolbar.querySelector('.gle-input-rows').value) || 4, 1, 30);
        const c = this._clamp(parseInt(this._toolbar.querySelector('.gle-input-cols').value) || 4, 1, 30);
        this.widgetMap = {};
        this._initGrid(r, c);
        this._fireChanged();
    }

    _initGrid(rows, cols) {
        this.matrix = [];
        this.nextId = 1;
        this.selected.clear();
        this.history = [];
        for (let r = 0; r < rows; r++) {
            this.matrix[r] = [];
            for (let c = 0; c < cols; c++) {
                this.matrix[r][c] = this.nextId++;
            }
        }
        this.colWidths = new Array(cols).fill(1);
        this.rowHeights = new Array(rows).fill(1);
        this._toolbar.querySelector('.gle-input-rows').value = rows;
        this._toolbar.querySelector('.gle-input-cols').value = cols;
        this.render();
    }

    // ===== Undo =====

    _saveState() {
        this.history.push({
            matrix: this.matrix.map(r => [...r]),
            colWidths: [...this.colWidths],
            rowHeights: [...this.rowHeights],
            nextId: this.nextId,
        });
        if (this.history.length > this.MAX_HISTORY) this.history.shift();
        this._updateButtons();
    }

    _doUndo() {
        if (!this.history.length) return;
        const s = this.history.pop();
        this.matrix = s.matrix;
        this.colWidths = s.colWidths;
        this.rowHeights = s.rowHeights;
        this.nextId = s.nextId;
        this.selected.clear();
        this.render();
        this._fireChanged();
    }

    // ===== Region Helpers =====

    _getRegions() {
        const map = {};
        for (let r = 0; r < this.matrix.length; r++) {
            for (let c = 0; c < this.matrix[0].length; c++) {
                const id = this.matrix[r][c];
                if (!map[id]) map[id] = { id, r1: r, c1: c, r2: r, c2: c };
                else {
                    map[id].r2 = Math.max(map[id].r2, r);
                    map[id].c2 = Math.max(map[id].c2, c);
                }
            }
        }
        return Object.values(map).sort((a, b) => a.r1 !== b.r1 ? a.r1 - b.r1 : a.c1 - b.c1);
    }

    _getBounds(id) {
        let r1 = Infinity, c1 = Infinity, r2 = -1, c2 = -1;
        for (let r = 0; r < this.matrix.length; r++)
            for (let c = 0; c < this.matrix[0].length; c++)
                if (this.matrix[r][c] === id) {
                    r1 = Math.min(r1, r); c1 = Math.min(c1, c);
                    r2 = Math.max(r2, r); c2 = Math.max(c2, c);
                }
        return { r1, c1, r2, c2 };
    }

    // ===== Merge =====

    _mergeSelected() {
        if (this.selected.size < 2) return;
        let r1 = Infinity, c1 = Infinity, r2 = -1, c2 = -1;
        let count = 0;
        for (let r = 0; r < this.matrix.length; r++)
            for (let c = 0; c < this.matrix[0].length; c++)
                if (this.selected.has(this.matrix[r][c])) {
                    r1 = Math.min(r1, r); c1 = Math.min(c1, c);
                    r2 = Math.max(r2, r); c2 = Math.max(c2, c);
                    count++;
                }
        if (count !== (r2 - r1 + 1) * (c2 - c1 + 1)) {
            return; // not a rectangle
        }
        this._saveState();

        // Collect widgets from selected regions, keep at most one
        const oldIds = new Set(this.selected);
        let keptWidget = null;
        for (const rid of oldIds) {
            const key = 'r' + rid;
            if (this.widgetMap[key]) {
                if (!keptWidget) keptWidget = this.widgetMap[key];
                delete this.widgetMap[key];
            }
        }

        const mid = this.nextId++;
        for (let r = r1; r <= r2; r++)
            for (let c = c1; c <= c2; c++) this.matrix[r][c] = mid;

        if (keptWidget) this.widgetMap['r' + mid] = keptWidget;

        this.selected.clear();
        this.selected.add(mid);
        this.render();
        this._fireChanged();
    }

    // ===== Split =====

    _splitSelected(mode) {
        if (this.selected.size !== 1) return;
        const id = [...this.selected][0];
        switch (mode) {
            case 'h': this._doSplit(id, 1, 2); break;
            case 'v': this._doSplit(id, 2, 1); break;
            case '2x2': this._doSplit(id, 2, 2); break;
        }
    }

    _doSplit(regionId, sRows, sCols) {
        if (sRows < 1 || sCols < 1 || (sRows === 1 && sCols === 1)) return;
        this._saveState();

        // Remove widget from split region
        delete this.widgetMap['r' + regionId];

        let b = this._getBounds(regionId);
        let curR = b.r2 - b.r1 + 1;
        let curC = b.c2 - b.c1 + 1;

        while (curR < sRows) {
            if (this.matrix.length >= this.MAX_GRID) return;
            this._insertRow(b.r2);
            b = this._getBounds(regionId);
            curR = b.r2 - b.r1 + 1;
        }
        while (curC < sCols) {
            if (this.matrix[0].length >= this.MAX_GRID) return;
            this._insertCol(b.c2);
            b = this._getBounds(regionId);
            curC = b.c2 - b.c1 + 1;
        }

        const rd = this._distribute(curR, sRows);
        const cd = this._distribute(curC, sCols);
        let sr = b.r1;
        for (let i = 0; i < sRows; i++) {
            let sc = b.c1;
            for (let j = 0; j < sCols; j++) {
                const nid = this.nextId++;
                for (let r = sr; r < sr + rd[i]; r++)
                    for (let c = sc; c < sc + cd[j]; c++) this.matrix[r][c] = nid;
                sc += cd[j];
            }
            sr += rd[i];
        }
        this.selected.clear();
        this.render();
        this._fireChanged();
    }

    _insertRow(atRow) {
        const newRow = [...this.matrix[atRow]];
        this.matrix.splice(atRow + 1, 0, newRow);
        const h = this.rowHeights[atRow] / 2;
        this.rowHeights.splice(atRow, 1, h, h);
    }

    _insertCol(atCol) {
        for (let r = 0; r < this.matrix.length; r++)
            this.matrix[r].splice(atCol + 1, 0, this.matrix[r][atCol]);
        const w = this.colWidths[atCol] / 2;
        this.colWidths.splice(atCol, 1, w, w);
    }

    _distribute(total, parts) {
        const base = Math.floor(total / parts);
        const rem = total % parts;
        return Array.from({ length: parts }, (_, i) => base + (i < rem ? 1 : 0));
    }

    // ===== Custom Split Modal =====

    _showCustomSplit() {
        if (this.selected.size !== 1) return;
        this._modalOverlay.querySelector('.gle-split-r').value = 2;
        this._modalOverlay.querySelector('.gle-split-c').value = 2;
        this._modalOverlay.classList.add('show');
    }

    _doCustomSplit() {
        const sr = this._clamp(parseInt(this._modalOverlay.querySelector('.gle-split-r').value) || 2, 1, 20);
        const sc = this._clamp(parseInt(this._modalOverlay.querySelector('.gle-split-c').value) || 2, 1, 20);
        this._modalOverlay.classList.remove('show');
        this._doSplit([...this.selected][0], sr, sc);
    }

    // ===== Selection (drag) =====

    _onCellDown(e, regionId) {
        if (this._resizing) return;
        e.preventDefault();
        this._isDragging = true;
        this._didDrag = false;
        this._dragStart = regionId;
        this._dragCtrl = e.ctrlKey || e.metaKey;
        this._dragBase = new Set(this._dragCtrl ? this.selected : []);
        this.selected = new Set(this._dragBase);
        this.selected.add(regionId);
        this._updateSelUI();
        this._updateButtons();

        // Notify zone select
        if (this.selected.size === 1) {
            const key = 'r' + regionId;
            if (this.widgetMap[key] && this.onWidgetSelect) {
                this.onWidgetSelect(key, this.widgetMap[key]);
            } else if (this.onZoneSelect) {
                this.onZoneSelect(key);
            }
        }
    }

    _onCellEnter(regionId) {
        if (!this._isDragging || this._resizing) return;
        this._didDrag = true;
        const sb = this._getBounds(this._dragStart);
        const cb = this._getBounds(regionId);
        const r1 = Math.min(sb.r1, cb.r1), c1 = Math.min(sb.c1, cb.c1);
        const r2 = Math.max(sb.r2, cb.r2), c2 = Math.max(sb.c2, cb.c2);
        this.selected = new Set(this._dragBase);
        for (let r = r1; r <= r2; r++)
            for (let c = c1; c <= c2; c++) this.selected.add(this.matrix[r][c]);
        this._updateSelUI();
        this._updateButtons();
    }

    _onMouseUp() {
        if (this._isDragging && !this._didDrag && this._dragCtrl && this._dragBase.has(this._dragStart)) {
            this.selected = new Set(this._dragBase);
            this.selected.delete(this._dragStart);
            this._updateSelUI();
            this._updateButtons();
        }
        this._isDragging = false;
    }

    _updateSelUI() {
        this._gridContainer.querySelectorAll('.gle-cell').forEach(el => {
            el.classList.toggle('selected', this.selected.has(parseInt(el.dataset.rid)));
        });
        this._updateStatus();
    }

    _updateButtons() {
        const n = this.selected.size;
        const tb = this._toolbar;
        const q = (sel) => tb.querySelector(`[data-action="${sel}"]`);
        q('merge').disabled = n < 2;
        const canSplit = n === 1;
        q('split-h').disabled = !canSplit;
        q('split-v').disabled = !canSplit;
        q('split-2x2').disabled = !canSplit;
        q('split-custom').disabled = !canSplit;
        q('undo').disabled = !this.history.length;
    }

    // ===== Resize Handles =====

    _initHandles() {
        this._gridWrapper.querySelectorAll('.gle-col-handle,.gle-row-handle').forEach(e => e.remove());

        const totalC = this.colWidths.reduce((a, b) => a + b, 0);
        let acc = 0;
        for (let c = 0; c < this.colWidths.length - 1; c++) {
            acc += this.colWidths[c];
            const h = document.createElement('div');
            h.className = 'gle-col-handle';
            h.style.left = `calc(${(acc / totalC) * 100}% - 4px)`;
            h.dataset.idx = c;
            h.addEventListener('mousedown', (e) => this._startColResize(e));
            this._gridWrapper.appendChild(h);
        }

        const totalR = this.rowHeights.reduce((a, b) => a + b, 0);
        acc = 0;
        for (let r = 0; r < this.rowHeights.length - 1; r++) {
            acc += this.rowHeights[r];
            const h = document.createElement('div');
            h.className = 'gle-row-handle';
            h.style.top = `calc(${(acc / totalR) * 100}% - 4px)`;
            h.dataset.idx = r;
            h.addEventListener('mousedown', (e) => this._startRowResize(e));
            this._gridWrapper.appendChild(h);
        }
    }

    _startColResize(e) {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(e.target.dataset.idx);
        const rect = this._gridContainer.getBoundingClientRect();
        this._resizing = { type: 'col', idx, startX: e.clientX, w: rect.width, orig: [...this.colWidths] };
        e.target.classList.add('active');
        this._onResizeBound = (ev) => this._onResize(ev);
        this._endResizeBound = () => this._endResize();
        document.addEventListener('mousemove', this._onResizeBound);
        document.addEventListener('mouseup', this._endResizeBound);
    }

    _startRowResize(e) {
        e.preventDefault();
        e.stopPropagation();
        const idx = parseInt(e.target.dataset.idx);
        const rect = this._gridContainer.getBoundingClientRect();
        this._resizing = { type: 'row', idx, startY: e.clientY, h: rect.height, orig: [...this.rowHeights] };
        e.target.classList.add('active');
        this._onResizeBound = (ev) => this._onResize(ev);
        this._endResizeBound = () => this._endResize();
        document.addEventListener('mousemove', this._onResizeBound);
        document.addEventListener('mouseup', this._endResizeBound);
    }

    _onResize(e) {
        if (!this._resizing) return;
        const s = this._resizing;
        if (s.type === 'col') {
            const totalFr = s.orig.reduce((a, b) => a + b, 0);
            const dFr = (e.clientX - s.startX) / s.w * totalFr;
            this.colWidths[s.idx] = Math.max(0.1, s.orig[s.idx] + dFr);
            this.colWidths[s.idx + 1] = Math.max(0.1, s.orig[s.idx + 1] - dFr);
        } else {
            const totalFr = s.orig.reduce((a, b) => a + b, 0);
            const dFr = (e.clientY - s.startY) / s.h * totalFr;
            this.rowHeights[s.idx] = Math.max(0.1, s.orig[s.idx] + dFr);
            this.rowHeights[s.idx + 1] = Math.max(0.1, s.orig[s.idx + 1] - dFr);
        }
        this._applyTemplate();
        this._initHandles();
    }

    _endResize() {
        this._gridWrapper.querySelectorAll('.gle-col-handle.active,.gle-row-handle.active')
            .forEach(e => e.classList.remove('active'));
        this._resizing = null;
        document.removeEventListener('mousemove', this._onResizeBound);
        document.removeEventListener('mouseup', this._endResizeBound);
        this._fireChanged();
    }

    // ===== Keyboard =====

    _onKeyDown(e) {
        // Only handle if our container or descendants are focused context
        if (e.key === 'Escape') {
            this.selected.clear();
            this._updateSelUI();
            this._updateButtons();
            this._modalOverlay.classList.remove('show');
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
            // Only if not typing in an input outside our editor
            if (this.container.contains(document.activeElement) || document.activeElement === document.body) {
                e.preventDefault();
                this._doUndo();
            }
        }
        if ((e.key === 'm' || e.key === 'M') && document.activeElement.tagName !== 'INPUT') {
            this._mergeSelected();
        }
    }

    // ===== Render =====

    render() {
        // Destroy all existing DataListWidget instances before re-rendering
        this._destroyAllDlw();

        this._gridContainer.innerHTML = '';
        this._applyTemplate();

        const regions = this._getRegions();
        regions.forEach((reg, i) => {
            const el = document.createElement('div');
            el.className = 'gle-cell';
            if (this.selected.has(reg.id)) el.classList.add('selected');
            el.dataset.rid = reg.id;
            el.style.gridRow = `${reg.r1 + 1} / ${reg.r2 + 2}`;
            el.style.gridColumn = `${reg.c1 + 1} / ${reg.c2 + 2}`;

            const rs = reg.r2 - reg.r1 + 1;
            const cs = reg.c2 - reg.c1 + 1;

            // Check widget
            const wKey = 'r' + reg.id;
            const widget = this.widgetMap[wKey];

            if (widget) {
                el.classList.add('has-widget');

                // 共用: 建立 container + mousedown 攔截
                const wContainer = document.createElement('div');
                wContainer.className = 'gle-dlw-container';
                el.appendChild(wContainer);

                wContainer.addEventListener('mousedown', (e) => {
                    e.stopPropagation();
                    this.selected.clear();
                    this.selected.add(reg.id);
                    this._updateSelUI();
                    this._updateButtons();
                    if (this.onWidgetSelect) {
                        this.onWidgetSelect(wKey, this.widgetMap[wKey]);
                    }
                });

                if (widget.type === 'SITEMENU' && typeof SiteMenuWidget !== 'undefined') {
                    // SITEMENU live preview
                    setTimeout(() => {
                        const smw = new SiteMenuWidget(wContainer, Object.assign({}, widget));
                        smw.init();
                        this._dlwInstances[wKey] = smw;
                    }, 0);
                } else if (widget.viewCode && typeof DataListWidget !== 'undefined') {
                    // DATALIST live preview
                    setTimeout(() => {
                        const dlw = new DataListWidget(wContainer, Object.assign({}, widget, {
                            showSearch: false,
                            showPagination: true,
                            allowCreate: false,
                            allowEdit: false,
                            allowDelete: false,
                            pageSize: 5,
                        }));
                        dlw.init();
                        this._dlwInstances[wKey] = dlw;
                    }, 0);
                } else {
                    // Static placeholder
                    const wp = document.createElement('div');
                    wp.className = 'gle-widget-preview';
                    const typeLabel = document.createElement('div');
                    typeLabel.className = 'gle-wp-type';
                    typeLabel.textContent = widget.type || 'DATALIST';
                    wp.appendChild(typeLabel);
                    const detail = document.createElement('div');
                    detail.className = 'gle-wp-detail';
                    detail.textContent = widget.type === 'SITEMENU' ? 'SITEMENU' : '(未設定資料來源)';
                    detail.style.color = '#f59e0b';
                    wp.appendChild(detail);
                    wContainer.appendChild(wp);
                }
            } else {
                // Zone number label
                const label = document.createElement('span');
                label.className = 'gle-cell-label';
                label.textContent = i + 1;
                el.appendChild(label);
                if (rs > 1 || cs > 1) {
                    el.title = `${rs} x ${cs}`;
                    el.classList.add('merged');
                }
            }

            // Drag events
            el.addEventListener('mousedown', (e) => this._onCellDown(e, reg.id));
            el.addEventListener('mouseenter', () => this._onCellEnter(reg.id));

            // Drop widget from component library
            el.addEventListener('dragover', (e) => {
                e.preventDefault();
                el.classList.add('drag-over');
            });
            el.addEventListener('dragleave', () => {
                el.classList.remove('drag-over');
            });
            el.addEventListener('drop', (e) => {
                e.preventDefault();
                el.classList.remove('drag-over');
                const type = e.dataTransfer.getData('text/plain');
                if (type) this._placeWidget(reg.id, type);
            });

            // Right click context menu
            el.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this._showContextMenu(e.clientX, e.clientY, reg.id);
            });

            this._gridContainer.appendChild(el);
        });

        this._initHandles();
        this._updateButtons();
        this._updateStatus();
    }

    _applyTemplate() {
        this._gridContainer.style.gridTemplateColumns = this.colWidths.map(w => w + 'fr').join(' ');
        this._gridContainer.style.gridTemplateRows = this.rowHeights.map(h => h + 'fr').join(' ');
    }

    // ===== Context Menu =====

    _showContextMenu(x, y, regionId) {
        this._closeContextMenu();
        const menu = document.createElement('div');
        menu.className = 'gle-ctx-menu';
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';

        const wKey = 'r' + regionId;
        const widget = this.widgetMap[wKey];
        const b = this._getBounds(regionId);
        const isMerged = (b.r2 - b.r1 > 0) || (b.c2 - b.c1 > 0);

        if (widget) {
            this._addCtxItem(menu, '移除元件', () => {
                delete this.widgetMap[wKey];
                this.render();
                this._fireChanged();
            });
            this._addCtxSep(menu);
        }

        if (isMerged) {
            this._addCtxItem(menu, '取消合併', () => {
                this._saveState();
                delete this.widgetMap[wKey];
                // Split back: assign new IDs to each cell
                for (let r = b.r1; r <= b.r2; r++)
                    for (let c = b.c1; c <= b.c2; c++)
                        this.matrix[r][c] = this.nextId++;
                this.selected.clear();
                this.render();
                this._fireChanged();
            });
        }

        document.body.appendChild(menu);
        this._contextMenu = menu;

        setTimeout(() => {
            const handler = (ev) => {
                if (!menu.contains(ev.target)) {
                    this._closeContextMenu();
                    document.removeEventListener('click', handler);
                }
            };
            document.addEventListener('click', handler);
        }, 0);
    }

    _addCtxItem(menu, label, action) {
        const item = document.createElement('div');
        item.className = 'gle-ctx-item';
        item.textContent = label;
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            this._closeContextMenu();
            action();
        });
        menu.appendChild(item);
    }

    _addCtxSep(menu) {
        const sep = document.createElement('div');
        sep.className = 'gle-ctx-sep';
        menu.appendChild(sep);
    }

    _closeContextMenu() {
        if (this._contextMenu) {
            this._contextMenu.remove();
            this._contextMenu = null;
        }
    }

    // ===== Status Bar =====

    _updateStatus() {
        const rows = this.matrix.length;
        const cols = this.matrix[0] ? this.matrix[0].length : 0;
        const regions = this._getRegions();
        const sb = this._statusBar;
        sb.querySelector('.gle-st-grid').textContent = `矩陣: ${rows} x ${cols}`;
        sb.querySelector('.gle-st-cells').textContent = `區塊: ${regions.length}`;
        if (this.selected.size === 0) {
            sb.querySelector('.gle-st-sel').textContent = '未選取';
        } else if (this.selected.size === 1) {
            const b = this._getBounds([...this.selected][0]);
            const rs = b.r2 - b.r1 + 1, cs = b.c2 - b.c1 + 1;
            sb.querySelector('.gle-st-sel').textContent = `已選取 1 區塊 (${rs}x${cs})`;
        } else {
            sb.querySelector('.gle-st-sel').textContent = `已選取 ${this.selected.size} 區塊`;
        }
    }

    // ===== Widget Operations (studio.js interface) =====

    _placeWidget(regionId, type) {
        const key = 'r' + regionId;
        if (this.widgetMap[key]) return;

        if (type === 'SITEMENU') {
            this.widgetMap[key] = {
                id: 'w_' + Math.random().toString(36).slice(2, 8),
                type: 'SITEMENU', title: '',
                startNodeSc: '', startLevel: 'children',
                orientation: 'vertical',
                bgColor: '#ffffff', itemBgColor: '#ffffff', itemTextColor: '#333333',
                itemHoverBgColor: '#e9ecef', itemHoverTextColor: '#333333',
                itemGap: 6, hoverExpand: true, hoverExpandDelay: 300,
                contextOutputs: [], contextInputs: [],
            };
        } else {
            this.widgetMap[key] = {
                id: 'w_' + Math.random().toString(36).slice(2, 8),
                type: type,
                viewCode: '', title: '',
                pageSize: 10, showSearch: true, showPagination: true,
                allowCreate: false, allowEdit: false, allowDelete: false,
                contextOutputs: [], contextInputs: [],
            };
        }

        this.selected.clear();
        this.selected.add(regionId);
        this.render();
        this._fireChanged();

        if (this.onWidgetSelect) {
            this.onWidgetSelect(key, this.widgetMap[key]);
        }
    }

    /** studio.js calls this: add widget to currently selected empty zone */
    addWidgetToSelected(type) {
        if (this.selected.size !== 1) return;
        const regionId = [...this.selected][0];
        const key = 'r' + regionId;
        if (!this.widgetMap[key]) {
            this._placeWidget(regionId, type);
        }
    }

    /** studio.js calls this: update widget config */
    updateWidget(zoneId, config) {
        if (!this.widgetMap[zoneId]) return;
        Object.assign(this.widgetMap[zoneId], config);
        this.render();
        this._fireChanged();
    }

    clearSelection() {
        this.selected.clear();
        this.render();
    }

    // ===== Layout JSON v3 Import/Export =====

    /**
     * Export to layout_json v3:
     * { version:3, mode:'grid', gridSize:[R,C],
     *   colWidths, rowHeights, matrix,
     *   zones:[{id,row,col,rowSpan,colSpan}],
     *   widgets:[{zoneId, widget:{...}}] }
     */
    toLayoutJson() {
        const regions = this._getRegions();
        const zones = regions.map((reg, i) => ({
            id: 'r' + reg.id,
            row: reg.r1 + 1,
            col: reg.c1 + 1,
            rowSpan: reg.r2 - reg.r1 + 1,
            colSpan: reg.c2 - reg.c1 + 1,
        }));

        const widgets = [];
        for (const [zoneId, config] of Object.entries(this.widgetMap)) {
            widgets.push({ zoneId, widget: Object.assign({}, config) });
        }

        return {
            version: 3,
            mode: 'grid',
            gridSize: [this.matrix.length, this.matrix[0] ? this.matrix[0].length : 0],
            colWidths: [...this.colWidths],
            rowHeights: [...this.rowHeights],
            matrix: this.matrix.map(r => [...r]),
            zones: zones,
            widgets: widgets,
        };
    }

    /**
     * Load from layout_json v3 (with matrix data for precise restore)
     */
    loadLayout(layoutJson) {
        if (!layoutJson || layoutJson.version !== 3) {
            this._initGrid(4, 4);
            return;
        }

        const gs = layoutJson.gridSize || [4, 4];

        // If we have matrix data, use it directly (precise)
        if (layoutJson.matrix && layoutJson.matrix.length > 0) {
            this.matrix = layoutJson.matrix.map(r => [...r]);
            this.colWidths = layoutJson.colWidths ? [...layoutJson.colWidths] : new Array(gs[1]).fill(1);
            this.rowHeights = layoutJson.rowHeights ? [...layoutJson.rowHeights] : new Array(gs[0]).fill(1);
            // Recover nextId
            this.nextId = 0;
            for (const row of this.matrix)
                for (const v of row)
                    this.nextId = Math.max(this.nextId, v);
            this.nextId++;
        } else {
            // Rebuild matrix from zones
            const rows = gs[0] || 4;
            const cols = gs[1] || 4;
            this.matrix = [];
            this.nextId = 1;
            for (let r = 0; r < rows; r++) {
                this.matrix[r] = [];
                for (let c = 0; c < cols; c++) this.matrix[r][c] = this.nextId++;
            }
            this.colWidths = new Array(cols).fill(1);
            this.rowHeights = new Array(rows).fill(1);

            // Apply zones
            if (layoutJson.zones) {
                for (const z of layoutJson.zones) {
                    const zid = this.nextId++;
                    for (let r = z.row - 1; r < z.row - 1 + z.rowSpan; r++)
                        for (let c = z.col - 1; c < z.col - 1 + z.colSpan; c++)
                            if (r < rows && c < cols) this.matrix[r][c] = zid;
                }
            }
        }

        // Load widgets
        this.widgetMap = {};
        if (layoutJson.widgets) {
            for (const w of layoutJson.widgets) {
                if (w.zoneId && w.widget) {
                    this.widgetMap[w.zoneId] = Object.assign({}, w.widget);
                }
            }
        }

        this.selected.clear();
        this.history = [];

        // Update toolbar inputs
        this._toolbar.querySelector('.gle-input-rows').value = this.matrix.length;
        this._toolbar.querySelector('.gle-input-cols').value = this.matrix[0] ? this.matrix[0].length : 0;

        this.render();
    }

    /** Resize (used by studio.js) */
    resize(rows, cols) {
        this.widgetMap = {};
        this._initGrid(rows, cols);
        this._fireChanged();
    }

    /** Cleanup: remove document-level event listeners */
    destroy() {
        this._destroyAllDlw();
        if (this._onMouseUpBound) {
            document.removeEventListener('mouseup', this._onMouseUpBound);
            this._onMouseUpBound = null;
        }
        if (this._onKeyDownBound) {
            document.removeEventListener('keydown', this._onKeyDownBound);
            this._onKeyDownBound = null;
        }
        this.onZoneSelect = null;
        this.onWidgetSelect = null;
        this.onChanged = null;
    }

    // ===== DataListWidget Instance Management =====

    _destroyAllDlw() {
        for (const key of Object.keys(this._dlwInstances)) {
            this._dlwInstances[key].destroy();
        }
        this._dlwInstances = {};
    }

    _destroyDlw(zoneKey) {
        if (this._dlwInstances[zoneKey]) {
            this._dlwInstances[zoneKey].destroy();
            delete this._dlwInstances[zoneKey];
        }
    }

    // ===== Helpers =====

    _fireChanged() {
        if (this.onChanged) this.onChanged();
    }

    _clamp(v, min, max) {
        return Math.min(max, Math.max(min, v));
    }
}
