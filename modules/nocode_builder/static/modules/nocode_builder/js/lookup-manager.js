/**
 * lookup-manager.js -- 選項清單管理器
 * Alpine.js component (模式 A: 無 Jinja2 變數)
 *
 * 右側 items 使用 Wunderbaum treegrid 呈現:
 * - 非階層類別: 扁平列表，同層拖拉排序
 * - 階層類別: 樹狀展開(預設全展開)，同層拖拉排序，跨層拖拉需 confirm
 */
function lookupManager() {
    return {
        // 類別
        categories: [],
        catFilter: '',
        selectedCat: null,
        loading: true,

        // 選項 (raw data from API)
        items: [],
        itemsLoading: false,

        // Wunderbaum instance
        _wbTree: null,

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
            this.showCatModal = true;
        },

        async saveCategory() {
            if (!this.catForm.code.trim() || !this.catForm.name.trim()) {
                this.showToast('請填寫代碼和名稱', 'error');
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

        async deleteCategory() {
            if (!this.selectedCat) return;
            if (this.selectedCat.is_system) {
                this.showToast('系統級類別不可刪除', 'error');
                return;
            }
            if (!confirm('確定要刪除類別「' + this.selectedCat.name + '」及其所有選項？')) return;
            try {
                var res = await fetch('/api/lookup/categories/' + this.selectedCat.secure_code, {
                    method: 'DELETE',
                });
                var data = await res.json();
                if (data.success) {
                    this.showToast('已刪除', 'success');
                    this.selectedCat = null;
                    this.items = [];
                    this._destroyTree();
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
            this._renderTree();
        },

        // ===== Wunderbaum Treegrid =====

        /**
         * 將 item 屬性展開到 Wunderbaum source node 上。
         * 注意: Wunderbaum v0.13.0 的 "data" 不在 reserved set，
         * 若用 {data: item} 會存成 node.data.data 而非 node.data，
         * 因此必須直接展開屬性讓 Wunderbaum 存入 node.data。
         */
        _itemToSourceNode(item, extra) {
            var node = Object.assign({
                title: item.label,
                key: item.secure_code,
            }, item, extra || {});
            return node;
        },

        _buildTreeSource(items) {
            var self = this;
            var isHier = this.selectedCat && this.selectedCat.is_hierarchical;
            if (!isHier) {
                // 扁平: 按 sort_order 排列
                var sorted = items.slice().sort(function(a, b) {
                    return (a.sort_order || 0) - (b.sort_order || 0);
                });
                return sorted.map(function(item) {
                    return self._itemToSourceNode(item);
                });
            }
            // 階層: 組裝
            var childrenMap = {};
            for (var i = 0; i < items.length; i++) {
                var pc = items[i].parent_code || '';
                if (!childrenMap[pc]) childrenMap[pc] = [];
                childrenMap[pc].push(items[i]);
            }
            // 每組依 sort_order 排序
            for (var key in childrenMap) {
                childrenMap[key].sort(function(a, b) {
                    return (a.sort_order || 0) - (b.sort_order || 0);
                });
            }
            function buildChildren(parentCode) {
                var list = childrenMap[parentCode] || [];
                return list.map(function(item) {
                    var kids = buildChildren(item.code);
                    var node = self._itemToSourceNode(item, { expanded: true });
                    if (kids.length > 0) {
                        node.children = kids;
                    }
                    return node;
                });
            }
            return buildChildren('');
        },

        _destroyTree() {
            if (this._wbTree) {
                try { this._wbTree.destroy(); } catch (e) { /* ignore */ }
                this._wbTree = null;
            }
            var el = document.getElementById('wb-tree');
            if (el) el.innerHTML = '';
        },

        _renderTree() {
            var self = this;
            this._destroyTree();

            // 等 DOM 更新後再初始化
            this.$nextTick(function() {
                var el = document.getElementById('wb-tree');
                if (!el || !self.items.length) return;
                if (typeof mar10 === 'undefined' || !mar10.Wunderbaum) {
                    console.error('Wunderbaum not loaded');
                    return;
                }

                var isHier = self.selectedCat && self.selectedCat.is_hierarchical;
                var source = self._buildTreeSource(self.items);

                var columns = [
                    { id: '*', title: '選項', width: '250px' },
                    { id: 'code', title: '代碼', width: '120px' },
                    { id: 'status', title: '狀態', width: '80px' },
                    { id: 'actions', title: '操作', width: '*' },
                ];

                self._wbTree = new mar10.Wunderbaum({
                    element: el,
                    id: 'lk-items',
                    source: source,
                    columns: columns,

                    render: function(e) {
                        var node = e.node;
                        var d = node.data || {};
                        var cols = e.renderColInfosById;
                        if (!cols) return;

                        // code 欄
                        if (cols.code) {
                            cols.code.elem.textContent = d.code || '';
                            cols.code.elem.style.fontFamily = 'monospace';
                            cols.code.elem.style.color = '#666';
                        }

                        // 狀態欄 -- 顏色文字 (Demo 2 style)
                        if (cols.status) {
                            var active = d.is_active;
                            var statusEl = cols.status.elem;
                            statusEl.textContent = active ? '啟用' : '停用';
                            statusEl.style.color = active ? '#276749' : '#c53030';
                            statusEl.style.cursor = 'pointer';
                            statusEl.style.fontSize = '0.85em';
                            statusEl.onclick = function(ev) {
                                ev.stopPropagation();
                                self._toggleActive(node);
                            };
                        }

                        // 操作欄 -- 每次 render 都重建 (虛擬渲染會複用 DOM)
                        if (cols.actions) {
                            var td = cols.actions.elem;
                            td.innerHTML = '';
                            td.style.whiteSpace = 'nowrap';

                            if (isHier) {
                                var addBtn = document.createElement('button');
                                addBtn.className = 'dc-btn sm';
                                addBtn.textContent = '+子';
                                addBtn.title = '新增子項';
                                addBtn.onclick = function(ev) {
                                    ev.stopPropagation();
                                    self.openItemModal(null, node.data.code);
                                };
                                td.appendChild(addBtn);
                                td.appendChild(document.createTextNode(' '));
                            }

                            var editBtn = document.createElement('button');
                            editBtn.className = 'dc-btn sm';
                            editBtn.textContent = '編輯';
                            editBtn.onclick = function(ev) {
                                ev.stopPropagation();
                                self.openItemModal(node.data);
                            };
                            td.appendChild(editBtn);
                            td.appendChild(document.createTextNode(' '));

                            var delBtn = document.createElement('button');
                            delBtn.className = 'dc-btn sm danger';
                            delBtn.textContent = '刪除';
                            delBtn.onclick = function(ev) {
                                ev.stopPropagation();
                                self._deleteByNode(node);
                            };
                            td.appendChild(delBtn);
                        }
                    },

                    // 拖放
                    dnd: {
                        effectAllowed: 'move',
                        dropEffectDefault: 'move',

                        dragStart: function(e) {
                            return true;
                        },

                        dragEnter: function(e) {
                            // 階層: 允許 before/after/over(成為子節點)
                            // 非階層: 只允許 before/after(同層排序)
                            if (isHier) {
                                return ['before', 'after', 'over'];
                            }
                            return ['before', 'after'];
                        },

                        drop: function(e) {
                            var srcNode = e.sourceNode;
                            var tgtNode = e.node;
                            if (!srcNode || !tgtNode) return;

                            var srcParent = srcNode.parent;
                            var tgtParent = tgtNode.parent;
                            var mode = e.suggestedDropMode; // 'before', 'after', 'appendChild'

                            // 判斷是否跨層
                            var isCrossLevel = false;
                            if (mode === 'appendChild') {
                                // 拖入另一個節點下: 一定是跨層(除非原本就是子節點)
                                isCrossLevel = (srcParent !== tgtNode);
                            } else {
                                // before/after: 目標的父節點 != 來源的父節點 → 跨層
                                isCrossLevel = (srcParent !== tgtParent);
                            }

                            if (isCrossLevel) {
                                if (!confirm('即將移動「' + srcNode.title + '」到不同層級，確定要跨層移動嗎？')) {
                                    return;
                                }
                            }

                            srcNode.moveTo(tgtNode, mode);
                            self._persistOrder();
                        },
                    },
                });
            });
        },

        /**
         * 將 Wunderbaum 當前樹狀結構序列化，送出 reorder API
         */
        async _persistOrder() {
            if (!this._wbTree || !this.selectedCat) return;
            var orderList = [];
            var isHier = this.selectedCat && this.selectedCat.is_hierarchical;

            this._wbTree.visit(function(node) {
                var d = node.data || {};
                if (!d.secure_code) return;
                var parentData = (node.parent && node.parent.data) || {};
                var parentCode = parentData.code || null;
                // 計算同層中的 sort_order
                var siblings = node.parent ? node.parent.children : [];
                var sortIdx = siblings ? siblings.indexOf(node) : 0;

                if (isHier) {
                    orderList.push({
                        secure_code: d.secure_code,
                        parent_code: parentCode,
                        sort_order: sortIdx,
                    });
                } else {
                    orderList.push(d.secure_code);
                }
            });

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

        async _toggleActive(node) {
            var d = node.data || {};
            try {
                var res = await fetch('/api/lookup/items/' + d.secure_code, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !d.is_active }),
                });
                var data = await res.json();
                if (data.success) {
                    d.is_active = !d.is_active;
                    node.update();
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
            }
        },

        async _deleteByNode(node) {
            var d = node.data || {};
            if (!confirm('確定要刪除選項「' + d.label + '」？')) return;
            try {
                var res = await fetch('/api/lookup/items/' + d.secure_code, {
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
            this.showItemModal = true;
        },

        async saveItem() {
            if (!this.itemForm.code.trim() || !this.itemForm.label.trim()) {
                this.showToast('請填寫代碼和顯示文字', 'error');
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
