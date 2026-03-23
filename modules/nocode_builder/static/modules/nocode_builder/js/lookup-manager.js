/**
 * lookup-manager.js -- 選項清單管理器
 * Alpine.js component (模式 A: 無 Jinja2 變數)
 *
 * 右側 items 使用 BeakTrellis treegrid 呈現:
 * - 非階層類別: 扁平列表，拖拉排序
 * - 階層類別: 樹狀展開(預設全展開)，拖拉排序+跨層移動
 */

// 值欄位名稱對照
var _VALUE_FIELDS = ['value_str', 'value_int', 'value_decimal', 'value_date', 'value_time', 'value_datetime'];

function lookupManager() {
    var mixin = codeInputMixin('lookup_category');

    return {
        ...mixin,

        // 類別
        categories: [],
        catFilter: '',
        selectedCat: null,
        loading: true,

        // 選項 (raw data from API)
        items: [],
        itemsLoading: false,

        // BeakTrellis instance
        _btGrid: null,

        // Category Modal
        showCatModal: false,
        catForm: { secure_code: null, code: '', name: '', description: '', is_hierarchical: false },
        catSaving: false,

        // Item Modal
        showItemModal: false,
        itemForm: _emptyItemForm(),
        itemSaving: false,

        // Toast
        toast: { show: false, message: '', type: 'success' },

        get filteredCategories() {
            if (!this.catFilter) return this.categories;
            var q = this.catFilter.toLowerCase();
            return this.categories.filter(function(c) {
                return c.name.toLowerCase().indexOf(q) >= 0 || c.code.toLowerCase().indexOf(q) >= 0;
            });
        },

        async init() {
            await this.loadCategories();
        },

        // ===== Categories =====

        async loadCategories() {
            this.loading = true;
            try {
                var res = await fetch('/api/lookup/categories');
                var data = await res.json();
                if (data.success) {
                    this.categories = data.data || [];
                }
            } catch (e) {
                console.error('loadCategories:', e);
            }
            this.loading = false;
        },

        async selectCategory(cat) {
            this.selectedCat = cat;
            await this.loadItems();
        },

        openCategoryModal(cat) {
            if (cat) {
                this.catForm = {
                    secure_code: cat.secure_code,
                    code: cat.code,
                    name: cat.name,
                    description: cat.description || '',
                    is_hierarchical: cat.is_hierarchical || false,
                };
            } else {
                this.catForm = { secure_code: null, code: '', name: '', description: '', is_hierarchical: false };
            }
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
            this.showCatModal = true;
        },

        // 覆寫 ciUseSuggestion: 根據當前 modal 設定正確欄位
        ciUseSuggestion(code) {
            if (this.showCatModal) {
                this.catForm.code = code;
            } else if (this.showItemModal) {
                this.itemForm.code = code;
            }
            this._ci_codeValid = true;
            this._ci_codeError = '';
        },

        async saveCategory() {
            if (!this.catForm.name.trim()) {
                this.showToast('請填寫名稱', 'error');
                return;
            }
            // 代碼留空時採用建議值
            if (!this.catForm.code.trim() && this._ci_generatedCode) {
                this.catForm.code = this._ci_generatedCode;
            }
            if (!this.catForm.code.trim()) {
                this.showToast('請填寫代碼', 'error');
                return;
            }
            this.catSaving = true;
            try {
                var url, method;
                if (this.catForm.secure_code) {
                    url = '/api/lookup/categories/' + this.catForm.secure_code;
                    method = 'PUT';
                } else {
                    url = '/api/lookup/categories';
                    method = 'POST';
                }
                var body = {
                    code: this.catForm.code.trim(),
                    name: this.catForm.name.trim(),
                    description: this.catForm.description || null,
                    is_hierarchical: this.catForm.is_hierarchical,
                };
                var res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '已儲存', 'success');
                    this.showCatModal = false;
                    await this.loadCategories();
                    if (data.data) {
                        var sc = data.data.secure_code;
                        this.selectedCat = this.categories.find(function(c) { return c.secure_code === sc; }) || null;
                    }
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
            this.catSaving = false;
        },

        async toggleCategoryActive() {
            if (!this.selectedCat || this.selectedCat.is_system) return;
            var newActive = !this.selectedCat.is_active;
            var msg = newActive ? '確定要啟用類別「' + this.selectedCat.name + '」？'
                                : '確定要停用類別「' + this.selectedCat.name + '」？';
            if (!confirm(msg)) return;
            try {
                var res = await fetch('/api/lookup/categories/' + this.selectedCat.secure_code, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: newActive }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast(newActive ? '已啟用' : '已停用', 'success');
                    var sc = this.selectedCat.secure_code;
                    await this.loadCategories();
                    this.selectedCat = this.categories.find(function(c) { return c.secure_code === sc; }) || null;
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗: ' + e.message, 'error');
            }
        },

        async deleteCategory() {
            if (!this.selectedCat) return;
            if (this.selectedCat.is_system) {
                this.showToast('系統級類別不可刪除', 'error');
                return;
            }
            if (this.selectedCat.is_active !== false) {
                this.showToast('請先停用類別後再刪除', 'error');
                return;
            }
            if (!confirm('確定要刪除類別「' + this.selectedCat.name + '」及其所有選項？\n\n刪除之後，與此代碼對應的項目可能無法顯示甚至因無正確對應而發生錯誤。')) return;
            try {
                var res = await fetch('/api/lookup/categories/' + this.selectedCat.secure_code, {
                    method: 'DELETE',
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast('已刪除', 'success');
                    this.selectedCat = null;
                    this.items = [];
                    this._destroyGrid();
                    await this.loadCategories();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // ===== Items =====

        async loadItems() {
            if (!this.selectedCat) return;
            this.itemsLoading = true;
            try {
                var res = await fetch('/api/lookup/categories/' + this.selectedCat.secure_code + '/items');
                var data = await res.json();
                if (data.success) {
                    this.items = data.data || [];
                }
            } catch (e) {
                console.error('loadItems:', e);
            }
            this.itemsLoading = false;
            this._renderGrid();
        },

        // ===== BeakTrellis TreeGrid =====

        /**
         * 將 API 回傳的 flat items 轉為 BeakTrellis 樹狀資料。
         * BeakTrellis 格式: { id, label, data: {}, children: [] }
         */
        _buildTreeData(items) {
            var isHier = this.selectedCat && this.selectedCat.is_hierarchical;

            var sorted = items.slice().sort(function(a, b) {
                return (a.sort_order || 0) - (b.sort_order || 0);
            });

            function itemToNodeData(item) {
                return {
                    secure_code: item.secure_code,
                    code: item.code,
                    label: item.label,
                    parent_code: item.parent_code || '',
                    sort_order: item.sort_order || 0,
                    is_active: item.is_active,
                    value: item.value,
                    value_str: item.value_str,
                    value_int: item.value_int,
                    value_decimal: item.value_decimal,
                    value_date: item.value_date,
                    value_time: item.value_time,
                    value_datetime: item.value_datetime
                };
            }

            if (!isHier) {
                return sorted.map(function(item) {
                    return {
                        id: item.secure_code,
                        label: item.label,
                        data: itemToNodeData(item)
                    };
                });
            }

            // 階層: 組裝樹
            var childrenMap = {};
            for (var i = 0; i < sorted.length; i++) {
                var pc = sorted[i].parent_code || '';
                if (!childrenMap[pc]) childrenMap[pc] = [];
                childrenMap[pc].push(sorted[i]);
            }

            function buildChildren(parentCode) {
                var list = childrenMap[parentCode] || [];
                return list.map(function(item) {
                    return {
                        id: item.secure_code,
                        label: item.label,
                        data: itemToNodeData(item),
                        children: buildChildren(item.code),
                        expanded: true
                    };
                });
            }
            return buildChildren('');
        },

        _destroyGrid() {
            this._btGrid = null;
            var el = document.getElementById('bt-lookup-tree');
            if (el) {
                if (this._gridClickHandler) {
                    el.removeEventListener('click', this._gridClickHandler);
                    this._gridClickHandler = null;
                }
                el.innerHTML = '';
            }
        },

        _renderGrid() {
            var self = this;
            this._destroyGrid();

            this.$nextTick(function() {
                var el = document.getElementById('bt-lookup-tree');
                if (!el || !self.items.length) return;
                if (typeof BeakTrellis === 'undefined') {
                    console.error('BeakTrellis not loaded');
                    return;
                }

                var isHier = self.selectedCat && self.selectedCat.is_hierarchical;
                var treeData = self._buildTreeData(self.items);

                var columns = [
                    {
                        id: 'code',
                        label: '代碼',
                        width: '130px',
                        sortable: false,
                        renderer: function(value, node) {
                            var d = node.data || {};
                            return '<code style="color:#555;">' + self._esc(d.code || '') + '</code>';
                        }
                    },
                    {
                        id: 'values',
                        label: '值',
                        width: '280px',
                        sortable: false,
                        renderer: function(value, node) {
                            var d = node.data || {};
                            return _renderValueColumn(d);
                        }
                    },
                    {
                        id: 'status',
                        label: '狀態',
                        width: '60px',
                        sortable: false,
                        renderer: function(value, node) {
                            var d = node.data || {};
                            if (d.is_active) {
                                return '<span style="color:#276749;">啟用</span>';
                            }
                            return '<span style="color:#c53030;">停用</span>';
                        }
                    },
                    {
                        id: 'actions',
                        label: '操作',
                        width: '220px',
                        sortable: false,
                        renderer: function(value, node) {
                            var d = node.data || {};
                            var sc = self._esc(d.secure_code || '');
                            var html = '';
                            if (isHier) {
                                html += '<button class="btn btn-secondary btn-sm lk-act-btn" data-action="add-child" data-code="' + self._esc(d.code || '') + '">+子</button> ';
                            }
                            html += '<button class="btn btn-secondary btn-sm lk-act-btn" data-action="edit" data-sc="' + sc + '">編輯</button> ';
                            html += '<button class="btn btn-secondary btn-sm lk-act-btn" data-action="toggle" data-sc="' + sc + '">' + (d.is_active ? '停用' : '啟用') + '</button> ';
                            if (!d.is_active) {
                                html += '<button class="btn btn-danger btn-sm lk-act-btn" data-action="delete" data-sc="' + sc + '">刪除</button>';
                            }
                            return html;
                        }
                    }
                ];

                self._btGrid = new BeakTrellis(el, {
                    data: treeData,
                    columns: columns,
                    treeMode: 'lines-dom',
                    draggable: true,
                    dragFlatOnly: !isHier,
                    showExpandCollapseButtons: false,
                    onNodeMoved: function(nodeId, newParentId, newIndex, node) {
                        self._persistOrder();
                    },
                    onRowClick: function(nodeId, node) {
                        // 不做選取，操作靠按鈕
                    }
                });

                // 一律全展開，禁止收合
                self._btGrid.expandAll();
                self._btGrid.toggle = function() {};
                self._btGrid.collapse = function() {};
                self._btGrid.collapseAll = function() {};

                // 委派按鈕事件（存為屬性，_destroyGrid 時移除，避免重複綁定）
                self._gridClickHandler = function(e) {
                    var btn = e.target.closest('.lk-act-btn');
                    if (!btn) return;
                    e.stopPropagation();
                    var action = btn.dataset.action;
                    var sc = btn.dataset.sc;
                    var code = btn.dataset.code;

                    if (action === 'edit') {
                        var item = self.items.find(function(i) { return i.secure_code === sc; });
                        if (item) self.openItemModal(item);
                    } else if (action === 'delete') {
                        self._deleteItem(sc);
                    } else if (action === 'toggle') {
                        self._toggleActive(sc);
                    } else if (action === 'add-child') {
                        self.openItemModal(null, code);
                    }
                };
                el.addEventListener('click', self._gridClickHandler);
            });
        },

        _esc(str) {
            var div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        },

        /**
         * 從 BeakTrellis 當前樹結構序列化排序，送出 reorder API
         */
        async _persistOrder() {
            if (!this._btGrid || !this.selectedCat) return;
            var isHier = this.selectedCat && this.selectedCat.is_hierarchical;
            var orderList = [];
            var model = this._btGrid._model;

            // 走訪所有可見節點
            var flatNodes = model.computeFlatNodes();

            // 需要走訪完整樹（包含收合的），用 _nodeMap
            function walkTree(nodes, parentCode) {
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i];
                    var d = n.data || {};
                    if (!d.secure_code) continue;
                    if (isHier) {
                        orderList.push({
                            secure_code: d.secure_code,
                            parent_code: parentCode || null,
                            sort_order: i,
                        });
                    } else {
                        orderList.push(d.secure_code);
                    }
                    if (n.children && n.children.length > 0) {
                        walkTree(n.children, d.code);
                    }
                }
            }

            var rootNodes = model.getRootNodes();
            walkTree(rootNodes, null);

            if (orderList.length === 0) return;

            try {
                var res = await fetch(
                    '/api/lookup/categories/' + this.selectedCat.secure_code + '/items/reorder',
                    {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ order: orderList }),
                    }
                );
                var data = await res.json();
                if (!data.success) {
                    this.showToast(data.error || '排序儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('排序儲存失敗: ' + e.message, 'error');
            }
        },

        async _toggleActive(secureCode) {
            var item = this.items.find(function(i) { return i.secure_code === secureCode; });
            if (!item) return;
            try {
                var res = await fetch('/api/lookup/items/' + secureCode, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !item.is_active }),
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast(item.is_active ? '已停用' : '已啟用', 'success');
                    await this.loadItems();
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
            }
        },

        async _deleteItem(secureCode) {
            var item = this.items.find(function(i) { return i.secure_code === secureCode; });
            if (!item) return;
            if (item.is_active) {
                this.showToast('請先停用選項後再刪除', 'error');
                return;
            }
            if (!confirm('確定要刪除選項「' + item.label + '」？\n\n刪除之後，與此代碼對應的項目可能無法顯示甚至因無正確對應而發生錯誤。')) return;
            try {
                var res = await fetch('/api/lookup/items/' + secureCode, {
                    method: 'DELETE',
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast('已刪除', 'success');
                    await this.loadItems();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // ===== Item Modal =====

        openItemModal(item, parentCode) {
            if (item) {
                this.itemForm = {
                    secure_code: item.secure_code,
                    code: item.code,
                    label: item.label,
                    parent_code: item.parent_code || '',
                    sort_order: item.sort_order || 0,
                    value_str: item.value_str || '',
                    value_int: (item.value_int != null) ? item.value_int : '',
                    value_decimal: (item.value_decimal != null) ? item.value_decimal : '',
                    value_date: item.value_date || '',
                    value_time: item.value_time || '',
                    value_datetime: item.value_datetime ? item.value_datetime.replace(' ', 'T') : '',
                    valueJson: item.value ? JSON.stringify(item.value, null, 2) : '',
                    jsonMode: 'simple',
                    jsonPairs: _jsonToPairs(item.value),
                    is_active: item.is_active,
                };
            } else {
                var maxSort = this.items.length > 0
                    ? Math.max.apply(null, this.items.map(function(i) { return i.sort_order || 0; }))
                    : -1;
                this.itemForm = _emptyItemForm();
                this.itemForm.parent_code = parentCode || '';
                this.itemForm.sort_order = maxSort + 1;
            }
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
            this.showItemModal = true;
        },

        // JSON 模式切換
        toggleJsonMode() {
            if (this.itemForm.jsonMode === 'simple') {
                // simple -> raw: 將 pairs 序列化為 JSON
                var obj = _pairsToJson(this.itemForm.jsonPairs);
                this.itemForm.valueJson = obj !== null ? JSON.stringify(obj, null, 2) : '';
                this.itemForm.jsonMode = 'raw';
            } else {
                // raw -> simple: 嘗試解析 JSON 為 pairs
                if (!this.itemForm.valueJson || !this.itemForm.valueJson.trim()) {
                    this.itemForm.jsonPairs = [];
                    this.itemForm.jsonMode = 'simple';
                    return;
                }
                try {
                    var parsed = JSON.parse(this.itemForm.valueJson);
                    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
                        // 檢查是否為扁平物件
                        var isFlat = true;
                        for (var k in parsed) {
                            var v = parsed[k];
                            if (typeof v === 'object' && v !== null) {
                                isFlat = false;
                                break;
                            }
                        }
                        if (isFlat) {
                            this.itemForm.jsonPairs = _jsonToPairs(parsed);
                            this.itemForm.jsonMode = 'simple';
                        } else {
                            this.showToast('JSON 含巢狀結構，無法轉為簡易模式', 'error');
                        }
                    } else {
                        this.showToast('JSON 非物件格式，無法轉為簡易模式', 'error');
                    }
                } catch (e) {
                    this.showToast('JSON 格式錯誤，無法切換', 'error');
                }
            }
        },

        async saveItem() {
            if (!this.itemForm.label.trim()) {
                this.showToast('請填寫顯示文字', 'error');
                return;
            }
            // 代碼留空時採用建議值
            if (!this.itemForm.code.trim() && this._ci_generatedCode) {
                this.itemForm.code = this._ci_generatedCode;
            }
            if (!this.itemForm.code.trim()) {
                this.showToast('請填寫代碼', 'error');
                return;
            }

            // 組裝 JSON value
            var parsedValue = null;
            if (this.itemForm.jsonMode === 'simple') {
                parsedValue = _pairsToJson(this.itemForm.jsonPairs);
            } else {
                if (this.itemForm.valueJson && this.itemForm.valueJson.trim()) {
                    try {
                        parsedValue = JSON.parse(this.itemForm.valueJson);
                    } catch (e) {
                        this.showToast('JSON 附加資料格式錯誤', 'error');
                        return;
                    }
                }
            }

            this.itemSaving = true;
            try {
                var url, method;
                if (this.itemForm.secure_code) {
                    url = '/api/lookup/items/' + this.itemForm.secure_code;
                    method = 'PUT';
                } else {
                    url = '/api/lookup/categories/' + this.selectedCat.secure_code + '/items';
                    method = 'POST';
                }
                var body = {
                    code: this.itemForm.code.trim(),
                    label: this.itemForm.label.trim(),
                    parent_code: this.itemForm.parent_code || null,
                    sort_order: this.itemForm.sort_order,
                    value: parsedValue,
                    value_str: this.itemForm.value_str || null,
                    value_int: (this.itemForm.value_int !== '' && this.itemForm.value_int != null) ? this.itemForm.value_int : null,
                    value_decimal: (this.itemForm.value_decimal !== '' && this.itemForm.value_decimal != null) ? this.itemForm.value_decimal : null,
                    value_date: this.itemForm.value_date || null,
                    value_time: this.itemForm.value_time || null,
                    value_datetime: this.itemForm.value_datetime || null,
                    is_active: this.itemForm.is_active,
                };
                var res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '已儲存', 'success');
                    this.showItemModal = false;
                    await this.loadItems();
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
            this.itemSaving = false;
        },

        // ===== Toast =====

        showToast(message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function() { self.toast.show = false; }, 3000);
        }
    };
}

// ===== 輔助函式 =====

function _emptyItemForm() {
    return {
        secure_code: null,
        code: '',
        label: '',
        parent_code: '',
        sort_order: 0,
        value_str: '',
        value_int: '',
        value_decimal: '',
        value_date: '',
        value_time: '',
        value_datetime: '',
        valueJson: '',
        jsonMode: 'simple',
        jsonPairs: [],
        is_active: true
    };
}

/**
 * 將 JSONB 物件轉為 key-value pairs 陣列
 * 每個 pair: { key, value, type }
 * type: 'auto' | 'string' | 'number' | 'boolean'
 */
function _jsonToPairs(obj) {
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
    var pairs = [];
    for (var k in obj) {
        if (!obj.hasOwnProperty(k)) continue;
        var v = obj[k];
        var t = 'auto';
        if (typeof v === 'boolean') {
            t = 'boolean';
            v = v ? 'true' : 'false';
        } else if (typeof v === 'number') {
            t = 'number';
            v = String(v);
        } else if (typeof v === 'string') {
            t = 'string';
        } else {
            // 巢狀物件/陣列 -- 轉為字串表示
            t = 'string';
            v = JSON.stringify(v);
        }
        pairs.push({ key: k, value: v, type: t });
    }
    return pairs;
}

/**
 * 將 key-value pairs 陣列轉回 JSON 物件
 * 自動偵測型別
 */
function _pairsToJson(pairs) {
    if (!pairs || pairs.length === 0) return null;
    // 過濾空行
    var validPairs = pairs.filter(function(p) { return p.key && p.key.trim(); });
    if (validPairs.length === 0) return null;

    var obj = {};
    for (var i = 0; i < validPairs.length; i++) {
        var p = validPairs[i];
        var key = p.key.trim();
        var val = (p.value || '').trim();
        var type = p.type || 'auto';

        if (type === 'boolean') {
            obj[key] = (val === 'true');
        } else if (type === 'number') {
            var n = Number(val);
            obj[key] = isNaN(n) ? val : n;
        } else if (type === 'string') {
            obj[key] = val;
        } else {
            // auto: 自動推斷
            if (val === 'true') {
                obj[key] = true;
            } else if (val === 'false') {
                obj[key] = false;
            } else if (val !== '' && !isNaN(Number(val))) {
                obj[key] = Number(val);
            } else {
                obj[key] = val;
            }
        }
    }
    return obj;
}

/**
 * 根據 node data 產生值欄位 HTML（badge + 實際值）
 * 每個有值的欄位顯示一行: [badge] 值
 */
function _renderValueColumn(d) {
    var lines = [];
    var badge = 'display:inline-block;font-size:9px;font-weight:600;padding:0 3px;line-height:14px;margin-right:3px;vertical-align:middle;';
    var valSty = 'font-size:0.8em;color:#333;vertical-align:middle;';
    var mono = valSty + 'font-family:monospace;';

    if (d.value_str != null && d.value_str !== '') {
        var s = d.value_str.length > 30 ? d.value_str.substring(0, 30) + '...' : d.value_str;
        lines.push(
            '<span style="' + badge + 'color:#276749;background:#c6f6d5;border:1px solid #9ae6b4;">STR</span>' +
            '<span style="' + valSty + '" title="' + _escAttr(d.value_str) + '">' + _escHtml(s) + '</span>'
        );
    }
    if (d.value_int != null) {
        lines.push(
            '<span style="' + badge + 'color:#2b6cb0;background:#bee3f8;border:1px solid #90cdf4;">INT</span>' +
            '<span style="' + mono + '">' + d.value_int + '</span>'
        );
    }
    if (d.value_decimal != null) {
        lines.push(
            '<span style="' + badge + 'color:#2b6cb0;background:#bee3f8;border:1px solid #90cdf4;">DEC</span>' +
            '<span style="' + mono + '">' + Number(d.value_decimal).toFixed(2) + '</span>'
        );
    }
    if (d.value_date) {
        lines.push(
            '<span style="' + badge + 'color:#9c4221;background:#feebc8;border:1px solid #fbd38d;">DATE</span>' +
            '<span style="' + mono + '">' + _escHtml(d.value_date) + '</span>'
        );
    }
    if (d.value_time) {
        lines.push(
            '<span style="' + badge + 'color:#9c4221;background:#feebc8;border:1px solid #fbd38d;">TIME</span>' +
            '<span style="' + mono + '">' + _escHtml(d.value_time) + '</span>'
        );
    }
    if (d.value_datetime) {
        var dt = d.value_datetime.replace('T', ' ');
        lines.push(
            '<span style="' + badge + 'color:#9c4221;background:#feebc8;border:1px solid #fbd38d;">DT</span>' +
            '<span style="' + mono + '">' + _escHtml(dt) + '</span>'
        );
    }
    if (d.value && typeof d.value === 'object' && Object.keys(d.value).length > 0) {
        var keys = Object.keys(d.value);
        var summary = keys.length <= 3 ? keys.join(', ') : keys.slice(0, 3).join(', ') + '...';
        lines.push(
            '<span style="' + badge + 'color:#553c9a;background:#e9d8fd;border:1px solid #d6bcfa;">JSON</span>' +
            '<span style="' + valSty + '" title="' + _escAttr(JSON.stringify(d.value)) + '">{' + _escHtml(summary) + '}</span>'
        );
    }
    if (lines.length === 0) return '<span style="color:#aaa;font-size:0.8em;">--</span>';
    return '<div style="line-height:18px;">' + lines.join('<br>') + '</div>';
}

function _escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function _escAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
