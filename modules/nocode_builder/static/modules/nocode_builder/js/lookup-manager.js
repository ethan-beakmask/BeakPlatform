/**
 * lookup-manager.js -- 選項清單管理器
 * Alpine.js component (模式 A: 無 Jinja2 變數)
 *
 * 右側 items 使用 BeakTrellis treegrid 呈現:
 * - 非階層類別: 扁平列表，拖拉排序
 * - 階層類別: 樹狀展開(預設全展開)，拖拉排序+跨層移動
 */
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
        itemForm: { secure_code: null, code: '', label: '', parent_code: '', sort_order: 0, valueJson: '', is_active: true },
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

            if (!isHier) {
                return sorted.map(function(item) {
                    return {
                        id: item.secure_code,
                        label: item.label,
                        data: {
                            secure_code: item.secure_code,
                            code: item.code,
                            label: item.label,
                            parent_code: item.parent_code || '',
                            sort_order: item.sort_order || 0,
                            is_active: item.is_active,
                            value: item.value
                        }
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
                    var node = {
                        id: item.secure_code,
                        label: item.label,
                        data: {
                            secure_code: item.secure_code,
                            code: item.code,
                            label: item.label,
                            parent_code: item.parent_code || '',
                            sort_order: item.sort_order || 0,
                            is_active: item.is_active,
                            value: item.value
                        },
                        children: buildChildren(item.code),
                        expanded: true
                    };
                    return node;
                });
            }
            return buildChildren('');
        },

        _destroyGrid() {
            this._btGrid = null;
            var el = document.getElementById('bt-lookup-tree');
            if (el) el.innerHTML = '';
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
                        width: '140px',
                        sortable: false,
                        renderer: function(value, node) {
                            var d = node.data || {};
                            return '<code style="color:#555;">' + self._esc(d.code || '') + '</code>';
                        }
                    },
                    {
                        id: 'status',
                        label: '狀態',
                        width: '70px',
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
                    showExpandCollapseButtons: isHier,
                    onNodeMoved: function(nodeId, newParentId, newIndex, node) {
                        self._persistOrder();
                    },
                    onRowClick: function(nodeId, node) {
                        // 不做選取，操作靠按鈕
                    }
                });

                // 委派按鈕事件
                el.addEventListener('click', function(e) {
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
                });
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
                    valueJson: item.value ? JSON.stringify(item.value, null, 2) : '',
                    is_active: item.is_active,
                };
            } else {
                var maxSort = this.items.length > 0
                    ? Math.max.apply(null, this.items.map(function(i) { return i.sort_order || 0; }))
                    : -1;
                this.itemForm = {
                    secure_code: null,
                    code: '',
                    label: '',
                    parent_code: parentCode || '',
                    sort_order: maxSort + 1,
                    valueJson: '',
                    is_active: true,
                };
            }
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
            this.showItemModal = true;
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

            var parsedValue = null;
            if (this.itemForm.valueJson && this.itemForm.valueJson.trim()) {
                try {
                    parsedValue = JSON.parse(this.itemForm.valueJson);
                } catch (e) {
                    this.showToast('附加資料 JSON 格式錯誤', 'error');
                    return;
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
