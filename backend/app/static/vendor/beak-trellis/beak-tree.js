/**
 * Tree - 獨立樹狀元件
 * 基於 BeakTreeModel 的 DOM 渲染，可單獨使用
 *
 * 功能：樹狀列表、展開/收合、checkbox 多選、可插拔渲染器
 * 依賴：tree-model.js
 *
 * 授權：MIT
 */
'use strict';

class BeakTree {
    /**
     * @param {HTMLElement} container - 容器元素
     * @param {Object} options
     * @param {Array} options.data - 樹狀資料陣列
     * @param {string} [options.treeMode='lines-dom'] - 渲染模式
     * @param {boolean} [options.checkbox=false] - 是否顯示 checkbox
     * @param {number} [options.maxExpanded=500] - 最大展開節點數
     * @param {Function} [options.onChecked] - 勾選回呼
     * @param {Function} [options.onExpand] - 展開回呼
     * @param {Function} [options.onCollapse] - 收合回呼
     * @param {Function} [options.onExpandLimited] - 展開超限回呼
     * @param {boolean} [options.hideRoot=false] - 隱藏唯一的 root 節點
     * @param {boolean} [options.draggable=false] - 啟用拖曳（需載入 tree-drag.js）
     * @param {Function} [options.onNodeMoved] - 拖曳完成回呼 (nodeId, newParentId, newIndex, node)
     * @param {Function} [options.onNodeClick] - 節點點擊回呼
     */
    constructor(container, options) {
        if (!container || !(container instanceof HTMLElement)) {
            throw new Error('BeakTree: container 必須是有效的 HTMLElement');
        }
        if (!options || !options.data) {
            throw new Error('BeakTree: options 必須包含 data');
        }

        this.container = container;
        this.options = Object.assign({
            treeMode: 'lines-dom',
            checkbox: false,
            hideRoot: false,
            hideHeader: true,
            headerText: '',
            onHeaderClick: null,
            draggable: false,
            maxExpanded: 500,
            onChecked: null,
            onExpand: null,
            onCollapse: null,
            onExpandLimited: null,
            onNodeMoved: null,
            onNodeClick: null
        }, options);

        // 建立 BeakTreeModel
        this._model = new BeakTreeModel(options.data, {
            maxExpanded: this.options.maxExpanded,
            hideRoot: this.options.hideRoot,
            onExpand: this.options.onExpand,
            onCollapse: this.options.onCollapse,
            onExpandLimited: this.options.onExpandLimited,
            onChecked: this.options.onChecked
        });

        // DOM 參照
        this._tableEl = null;
        this._tbodyEl = null;

        // 渲染器
        this._renderer = null;
        this._initRenderer();

        // 首次渲染
        this.render();
    }

    // ========== Getter proxy（與 BeakTrellis 相容，供渲染器存取） ==========

    get _flatNodes() { return this._model._flatNodes; }
    set _flatNodes(v) { this._model._flatNodes = v; }
    get _nodeMap() { return this._model._nodeMap; }
    get _expandedSet() { return this._model._expandedSet; }
    get _checkedSet() { return this._model._checkedSet; }
    get _expandedCount() { return this._model._expandedCount; }

    // ========== 渲染器 ==========

    _initRenderer() {
        var renderers = BeakTree.renderers || {};
        var mode = this.options.treeMode;

        if (renderers[mode]) {
            this._renderer = renderers[mode];
        } else {
            // 預設簡單縮排
            var model = this._model;
            this._renderer = {
                renderTreeCell: function(node, ancestors, tree) {
                    var indent = '';
                    for (var i = 0; i < node.level; i++) indent += '\u00A0\u00A0';
                    var toggle = node.children.length > 0
                        ? (model.isExpanded(node.id) ? '[-] ' : '[+] ')
                        : '    ';
                    var span = document.createElement('span');
                    span.textContent = indent + toggle + node.label;
                    return span;
                }
            };
        }
    }

    // ========== 渲染 ==========

    render() {
        this._model.computeFlatNodes();
        this.container.innerHTML = '';
        this.container.classList.add('bk-tree-container');

        var table = document.createElement('table');
        table.className = 'bk-tree-table';

        // 表頭（hideHeader=false 且 headerText 有值時才顯示）
        var showHeader = !this.options.hideHeader && !!this.options.headerText;
        if (showHeader || this.options.checkbox) {
            var thead = document.createElement('thead');
            var headerRow = document.createElement('tr');

            if (this.options.checkbox) {
                var thCb = document.createElement('th');
                thCb.className = 'tree-th bk-tree-th-checkbox';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'bk-tree-checkbox-all';
                var self = this;
                cb.addEventListener('change', function() {
                    cb.checked ? self.checkAll() : self.uncheckAll();
                });
                thCb.appendChild(cb);
                headerRow.appendChild(thCb);
            }

            var thTree = document.createElement('th');
            thTree.className = 'tree-th bk-tree-th-tree';
            if (showHeader) {
                if (this.options.onHeaderClick) {
                    var a = document.createElement('a');
                    a.href = 'javascript:void(0)';
                    a.textContent = this.options.headerText;
                    a.style.cssText = 'color:inherit;text-decoration:none;cursor:pointer;';
                    var clickHandler = this.options.onHeaderClick;
                    a.addEventListener('click', function(e) {
                        e.preventDefault();
                        clickHandler(e);
                    });
                    thTree.appendChild(a);
                } else {
                    thTree.textContent = this.options.headerText;
                }
            }
            headerRow.appendChild(thTree);

            thead.appendChild(headerRow);
            table.appendChild(thead);
        }

        // 表身
        var tbody = document.createElement('tbody');
        var flatNodes = this._model._flatNodes;
        for (var i = 0; i < flatNodes.length; i++) {
            tbody.appendChild(this._createRow(flatNodes[i]));
        }
        table.appendChild(tbody);

        this.container.appendChild(table);
        this._tableEl = table;
        this._tbodyEl = tbody;

        // 渲染器後處理
        if (this._renderer && this._renderer.afterRender) {
            this._renderer.afterRender(this);
        }
    }

    _createRow(node) {
        var self = this;
        var tr = document.createElement('tr');
        tr.className = 'bt-row bt-level-' + node.level;
        tr.dataset.id = node.id;

        if (this._model._checkedSet.has(node.id)) {
            tr.classList.add('bt-row-checked');
        }

        // Checkbox
        if (this.options.checkbox) {
            var tdCb = document.createElement('td');
            tdCb.className = 'bt-td bt-td-checkbox';
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'bt-checkbox';
            cb.dataset.id = node.id;

            var state = this._model.getCheckState(node.id);
            cb.checked = (state === 'checked');
            cb.indeterminate = (state === 'indeterminate');

            cb.addEventListener('change', function(e) {
                e.stopPropagation();
                self.toggleCheck(node.id);
            });
            tdCb.appendChild(cb);
            tr.appendChild(tdCb);
        }

        // Tree cell
        var tdTree = document.createElement('td');
        tdTree.className = 'bt-td bt-td-tree';

        var ancestors = this._model.getAncestors(node.id);
        if (this._renderer && this._renderer.renderTreeCell) {
            var content = this._renderer.renderTreeCell(node, ancestors, this);
            if (typeof content === 'string') {
                tdTree.innerHTML = content;
            } else if (content instanceof HTMLElement) {
                tdTree.appendChild(content);
            }
        }

        if (node.children.length > 0) {
            tdTree.classList.add('bt-has-children');
            tdTree.addEventListener('click', function(e) {
                if (e.target.classList.contains('bt-toggle') || e.target === tdTree) {
                    self.toggle(node.id);
                }
            });
        }

        tr.appendChild(tdTree);

        // 列點擊
        tr.addEventListener('click', function(e) {
            if (e.target.tagName === 'INPUT') return;
            // 清除 focusNode 高亮
            var oldFocus = self.container.querySelector('.bt-row-focused');
            if (oldFocus) oldFocus.classList.remove('bt-row-focused');
            if (self.options.onNodeClick) {
                self.options.onNodeClick(node.id, node, e);
            }
        });

        return tr;
    }

    _refresh() {
        this._model.computeFlatNodes();
        if (!this._tbodyEl || !this._tableEl) {
            this.render();
            return;
        }

        var newTbody = document.createElement('tbody');
        var flatNodes = this._model._flatNodes;
        for (var i = 0; i < flatNodes.length; i++) {
            newTbody.appendChild(this._createRow(flatNodes[i]));
        }
        this._tableEl.replaceChild(newTbody, this._tbodyEl);
        this._tbodyEl = newTbody;

        if (this._renderer && this._renderer.afterRender) {
            this._renderer.afterRender(this);
        }

        this._refreshHeaderCheckbox();
    }

    _refreshCheckboxes() {
        if (!this._tbodyEl) return;

        var checkboxes = this._tbodyEl.querySelectorAll('.bt-checkbox');
        for (var i = 0; i < checkboxes.length; i++) {
            var cb = checkboxes[i];
            var id = cb.dataset.id;
            var state = this._model.getCheckState(id);
            cb.checked = (state === 'checked');
            cb.indeterminate = (state === 'indeterminate');

            var tr = cb.closest('tr');
            if (tr) {
                tr.classList.toggle('bt-row-checked', state === 'checked');
            }
        }

        this._refreshHeaderCheckbox();
    }

    _refreshHeaderCheckbox() {
        var headerCb = this.container.querySelector('.bk-tree-checkbox-all');
        if (!headerCb) return;

        var totalLeaves = this._model.countLeaves();
        var checkedLeaves = this._model.countCheckedLeaves();

        headerCb.checked = (totalLeaves > 0 && checkedLeaves === totalLeaves);
        headerCb.indeterminate = (checkedLeaves > 0 && checkedLeaves < totalLeaves);
    }

    // ========== 公開 API（代理 BeakTreeModel） ==========

    // 展開/收合
    expand(id, recursive) {
        var result = this._model.expand(id, recursive);
        if (result) this._refresh();
        return result;
    }

    collapse(id, recursive) {
        var result = this._model.collapse(id, recursive);
        if (result) this._refresh();
        return result;
    }

    toggle(id) {
        if (this._model.isExpanded(id)) {
            this.collapse(id);
        } else {
            this.expand(id);
        }
    }

    expandAll() {
        var result = this._model.expandAll();
        if (result) this._refresh();
        return result;
    }

    collapseAll() {
        this._model.collapseAll();
        this._refresh();
    }

    // 查詢
    isExpanded(id) { return this._model.isExpanded(id); }
    hasChildren(id) { return this._model.hasChildren(id); }
    getNode(id) { return this._model.getNode(id); }
    getRootNodes() { return this._model.getRootNodes(); }
    getAncestors(id) { return this._model.getAncestors(id); }
    getDescendants(id) { return this._model.getDescendants(id); }
    getVisibleCount() { return this._model.getVisibleCount(); }

    // Checkbox
    getCheckState(id) { return this._model.getCheckState(id); }

    toggleCheck(id) {
        this._model.toggleCheck(id);
        this._refreshCheckboxes();
    }

    getCheckedIds(leafOnly) { return this._model.getCheckedIds(leafOnly); }

    checkAll() {
        this._model.checkAll();
        this._refreshCheckboxes();
    }

    uncheckAll() {
        this._model.uncheckAll();
        this._refreshCheckboxes();
    }

    // 節點移動
    isDescendantOf(targetId, ancestorId) {
        return this._model.isDescendantOf(targetId, ancestorId);
    }

    moveNode(nodeId, newParentId, newIndex) {
        var result = this._model.moveNode(nodeId, newParentId, newIndex);
        if (result) this._refresh();
        return result;
    }

    // 動態資料
    addChildren(parentId, childrenData) {
        var result = this._model.addChildren(parentId, childrenData);
        if (result) this._refresh();
        return result;
    }

    removeChildren(parentId) {
        var result = this._model.removeChildren(parentId);
        if (result) this._refresh();
        return result;
    }

    updateNodeData(id, data) {
        var result = this._model.updateNodeData(id, data);
        if (result) this._refresh();
        return result;
    }

    // 導航
    focusNode(id, opts) {
        var node = this._model.getNode(id);
        if (!node) return false;

        opts = Object.assign({ expanded: false, highlight: true }, opts || {});

        // 展開所有祖先
        var ancestors = this._model.getAncestors(id);
        var needRefresh = false;
        for (var i = 0; i < ancestors.length; i++) {
            if (!this._model.isExpanded(ancestors[i].id)) {
                this._model.expand(ancestors[i].id);
                needRefresh = true;
            }
        }

        // 展開節點本身
        if (opts.expanded && node.children.length > 0 && !this._model.isExpanded(id)) {
            this._model.expand(id);
            needRefresh = true;
        }

        if (needRefresh) this._refresh();

        // 找到 DOM row 並捲動
        var row = this._tbodyEl ? this._tbodyEl.querySelector('tr[data-id="' + id + '"]') : null;
        if (!row) return false;

        row.scrollIntoView({ block: 'center', behavior: 'smooth' });

        // 高亮
        if (opts.highlight) {
            // 清除前一個 focus
            var oldFocus = this.container.querySelector('.bt-row-focused');
            if (oldFocus) oldFocus.classList.remove('bt-row-focused');

            row.classList.add('bt-row-focused');
        }

        return true;
    }

    setData(data) {
        this._model.setData(data);
        this.render();
    }

    setTreeMode(mode) {
        this.options.treeMode = mode;
        this._initRenderer();
        this.render();
    }

    destroy() {
        this.container.innerHTML = '';
        this._model.destroy();
        this._tableEl = null;
        this._tbodyEl = null;
    }
}

// 靜態屬性：渲染器註冊表
BeakTree.renderers = {};

BeakTree.registerRenderer = function(name, renderer) {
    BeakTree.renderers[name] = renderer;
};
