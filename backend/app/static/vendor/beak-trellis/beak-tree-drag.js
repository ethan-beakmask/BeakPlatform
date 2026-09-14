/**
 * Tree Drag & Drop Plugin
 * 拖曳節點實現同層排序、跨層移動
 *
 * 功能：
 *   - 拖曳節點到同層其他位置（排序）
 *   - 拖曳節點到另一個節點下（成為子節點）
 *   - 拖曳節點到根層
 *   - 防止循環參照（不能拖進自己的後代）
 *   - 拖曳中自動展開收合的節點
 *   - 視覺回饋：插入線、容器高亮
 *
 * 使用方式：
 *   載入此檔（在 tree.js 之後），並設定 options.draggable = true
 *
 * 回呼：
 *   options.onNodeMoved(nodeId, newParentId, newIndex, node)
 *   options.canDrop(sourceNode, targetNode, action) -- 回傳 false 阻止放置
 *
 * 依賴：tree.js, tree-model.js
 * 授權：MIT
 */
'use strict';

(function() {

    // 放置區域常數
    var DROP_ZONE_EDGE = 0.3;  // 上下 30% 為「插入前/後」

    // 拖曳途中懸停展開的延遲（ms）
    var HOVER_EXPAND_DELAY = 600;

    // ========== 掛載到 Tree 原型 ==========

    var _origRender = BeakTree.prototype.render;
    var _origRefresh = BeakTree.prototype._refresh;

    /**
     * 覆寫 render，完成後初始化拖曳
     */
    BeakTree.prototype.render = function() {
        _origRender.call(this);
        if (this.options.draggable) {
            this._initDrag();
        }
    };

    /**
     * 覆寫 _refresh，完成後重新綁定拖曳
     */
    BeakTree.prototype._refresh = function() {
        _origRefresh.call(this);
        if (this.options.draggable) {
            this._initDrag();
        }
    };

    // ========== 拖曳初始化 ==========

    BeakTree.prototype._initDrag = function() {
        if (!this._tbodyEl) return;

        var self = this;
        var rows = this._tbodyEl.querySelectorAll('tr.bt-row');

        for (var i = 0; i < rows.length; i++) {
            var tr = rows[i];
            tr.draggable = true;

            // 移除舊事件（避免重複綁定）
            tr.removeEventListener('dragstart', tr._onDragStart);
            tr.removeEventListener('dragend', tr._onDragEnd);

            tr._onDragStart = _makeDragStart(self, tr);
            tr._onDragEnd = _makeDragEnd(self);

            tr.addEventListener('dragstart', tr._onDragStart);
            tr.addEventListener('dragend', tr._onDragEnd);
        }

        // tbody 層級的 dragover / drop
        this._tbodyEl.removeEventListener('dragover', this._tbodyEl._onDragOver);
        this._tbodyEl.removeEventListener('drop', this._tbodyEl._onDrop);
        this._tbodyEl.removeEventListener('dragleave', this._tbodyEl._onDragLeave);

        this._tbodyEl._onDragOver = _makeDragOver(self);
        this._tbodyEl._onDrop = _makeDrop(self);
        this._tbodyEl._onDragLeave = _makeDragLeave(self);

        this._tbodyEl.addEventListener('dragover', this._tbodyEl._onDragOver);
        this._tbodyEl.addEventListener('drop', this._tbodyEl._onDrop);
        this._tbodyEl.addEventListener('dragleave', this._tbodyEl._onDragLeave);

        // 確保 indicator 存在
        if (!this._dragIndicator) {
            var ind = document.createElement('div');
            ind.className = 'bk-tree-drag-indicator';
            ind.style.display = 'none';
            this.container.appendChild(ind);
            this._dragIndicator = ind;
        }
    };

    // ========== 事件工廠 ==========

    function _makeDragStart(tree, tr) {
        return function(e) {
            var nodeId = tr.dataset.id;
            var node = tree._model.getNode(nodeId);
            if (!node) return;

            tree._dragSource = {
                id: nodeId,
                node: node,
                tr: tr
            };

            // 設定拖曳資料（必要，否則某些瀏覽器不啟動拖曳）
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', nodeId);

            // 延遲加樣式（否則 ghost 會帶上透明度）
            requestAnimationFrame(function() {
                tr.classList.add('bk-tree-drag-source');
            });
        };
    }

    function _makeDragEnd(tree) {
        return function() {
            _clearDragState(tree);
        };
    }

    function _makeDragOver(tree) {
        return function(e) {
            if (!tree._dragSource) return;

            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            var tr = _findRow(e.target);
            if (!tr) {
                _hideIndicator(tree);
                return;
            }

            var targetId = tr.dataset.id;
            var sourceId = tree._dragSource.id;

            // 不能放到自己身上
            if (targetId === sourceId) {
                _hideIndicator(tree);
                return;
            }

            // 不能放到自己的後代
            if (tree._model.isDescendantOf(targetId, sourceId)) {
                _hideIndicator(tree);
                e.dataTransfer.dropEffect = 'none';
                return;
            }

            var targetNode = tree._model.getNode(targetId);

            // canDrop 回呼：呼叫端自訂禁止規則
            if (tree.options.canDrop && targetNode) {
                var rect0 = tr.getBoundingClientRect();
                var y0 = e.clientY - rect0.top;
                var ratio0 = y0 / rect0.height;
                var preAction = ratio0 < DROP_ZONE_EDGE ? 'before'
                              : ratio0 > (1 - DROP_ZONE_EDGE) ? 'after'
                              : 'inside';
                if (tree.options.canDrop(tree._dragSource.node, targetNode, preAction) === false) {
                    _hideIndicator(tree);
                    e.dataTransfer.dropEffect = 'none';
                    return;
                }
            }

            var rect = tr.getBoundingClientRect();
            var y = e.clientY - rect.top;
            var ratio = y / rect.height;

            var dropAction;
            if (ratio < DROP_ZONE_EDGE) {
                dropAction = 'before';
            } else if (ratio > (1 - DROP_ZONE_EDGE)) {
                dropAction = 'after';
            } else {
                dropAction = 'inside';
            }

            tree._dropTarget = {
                id: targetId,
                tr: tr,
                action: dropAction
            };

            _showIndicator(tree, tr, dropAction);

            // 懸停展開
            _handleHoverExpand(tree, targetId, dropAction);
        };
    }

    function _makeDrop(tree) {
        return function(e) {
            e.preventDefault();

            if (!tree._dragSource || !tree._dropTarget) {
                _clearDragState(tree);
                return;
            }

            var sourceId = tree._dragSource.id;
            var sourceNode = tree._dragSource.node;
            var targetId = tree._dropTarget.id;
            var action = tree._dropTarget.action;
            var targetNode = tree._model.getNode(targetId);

            if (!targetNode) {
                _clearDragState(tree);
                return;
            }

            // canDrop 回呼：最終確認
            if (tree.options.canDrop) {
                if (tree.options.canDrop(sourceNode, targetNode, action) === false) {
                    _clearDragState(tree);
                    return;
                }
            }

            var newParentId, newIndex;

            if (action === 'inside') {
                // 放入目標節點成為子節點（最後一個）
                newParentId = targetId;
                newIndex = targetNode.children.length;
                // 如果自己已經是這個 parent 的子節點，要扣除自己
                if (sourceNode.parentId === targetId) {
                    var currentIdx = targetNode.children.indexOf(sourceNode);
                    if (currentIdx >= 0 && currentIdx < newIndex) {
                        newIndex--;
                    }
                }
            } else {
                // before/after：插入到目標節點的同層
                newParentId = targetNode.parentId;
                // 隱藏 root 模式下，最上層節點的 parentId 可能非 null
                var siblings;
                if (newParentId) {
                    var parent = tree._model.getNode(newParentId);
                    siblings = parent ? parent.children : [];
                } else {
                    siblings = tree._model.getRootNodes();
                }

                var targetIdx = -1;
                for (var i = 0; i < siblings.length; i++) {
                    if (siblings[i].id === targetId) {
                        targetIdx = i;
                        break;
                    }
                }

                if (action === 'after') {
                    targetIdx++;
                }

                // 如果來源在同一個 parent 且在目標之前，需要調整索引
                if (sourceNode.parentId === newParentId) {
                    var sourceIdx = -1;
                    for (var i = 0; i < siblings.length; i++) {
                        if (siblings[i].id === sourceId) {
                            sourceIdx = i;
                            break;
                        }
                    }
                    if (sourceIdx >= 0 && sourceIdx < targetIdx) {
                        targetIdx--;
                    }
                }

                newIndex = Math.max(0, targetIdx);
            }

            // 執行移動
            var result = tree._model.moveNode(sourceId, newParentId, newIndex);

            _clearDragState(tree);

            if (result) {
                tree._refresh();

                // 通知回呼
                if (tree.options.onNodeMoved) {
                    tree.options.onNodeMoved(sourceId, newParentId, newIndex, sourceNode);
                }
            }
        };
    }

    function _makeDragLeave(tree) {
        return function(e) {
            // 只在離開整個 tbody 時清除
            var related = e.relatedTarget;
            if (related && tree._tbodyEl.contains(related)) return;
            _hideIndicator(tree);
            tree._dropTarget = null;
        };
    }

    // ========== 指示器 ==========

    function _showIndicator(tree, tr, action) {
        var ind = tree._dragIndicator;
        if (!ind) return;

        // 清除所有 row 的 drop highlight
        var oldHl = tree._tbodyEl.querySelector('.bk-tree-drop-highlight');
        if (oldHl) oldHl.classList.remove('bk-tree-drop-highlight');

        if (action === 'inside') {
            // 高亮目標列
            tr.classList.add('bk-tree-drop-highlight');
            ind.style.display = 'none';
        } else {
            // 顯示插入線
            var containerRect = tree.container.getBoundingClientRect();
            var trRect = tr.getBoundingClientRect();

            // 計算相對於 container 的位置
            var scrollTop = tree.container.scrollTop;
            var scrollLeft = tree.container.scrollLeft;

            var lineY;
            if (action === 'before') {
                lineY = trRect.top - containerRect.top + scrollTop;
            } else {
                lineY = trRect.bottom - containerRect.top + scrollTop;
            }

            // 根據目標節點的縮排計算 left
            var node = tree._model.getNode(tr.dataset.id);
            var indentPx = node ? node.level * 20 + 8 : 8;

            ind.style.display = 'block';
            ind.style.top = lineY + 'px';
            ind.style.left = indentPx + 'px';
            ind.style.right = '8px';
        }
    }

    function _hideIndicator(tree) {
        if (tree._dragIndicator) {
            tree._dragIndicator.style.display = 'none';
        }
        var oldHl = tree._tbodyEl ? tree._tbodyEl.querySelector('.bk-tree-drop-highlight') : null;
        if (oldHl) oldHl.classList.remove('bk-tree-drop-highlight');
    }

    // ========== 懸停展開 ==========

    function _handleHoverExpand(tree, targetId, action) {
        // 只在 inside 模式下自動展開
        if (action !== 'inside') {
            _cancelHoverExpand(tree);
            return;
        }

        if (tree._hoverExpandId === targetId) return; // 已經在等待

        _cancelHoverExpand(tree);
        tree._hoverExpandId = targetId;

        var node = tree._model.getNode(targetId);
        if (!node || node.children.length === 0) return;
        if (tree._model.isExpanded(targetId)) return; // 已展開

        tree._hoverExpandTimer = setTimeout(function() {
            tree._hoverExpandId = null;
            tree._hoverExpandTimer = null;
            tree.expand(targetId);
        }, HOVER_EXPAND_DELAY);
    }

    function _cancelHoverExpand(tree) {
        if (tree._hoverExpandTimer) {
            clearTimeout(tree._hoverExpandTimer);
            tree._hoverExpandTimer = null;
        }
        tree._hoverExpandId = null;
    }

    // ========== 工具 ==========

    function _findRow(el) {
        while (el && el.tagName !== 'TR') {
            el = el.parentElement;
        }
        if (el && el.classList.contains('bt-row')) return el;
        return null;
    }

    function _clearDragState(tree) {
        _hideIndicator(tree);
        _cancelHoverExpand(tree);

        // 清除 source 樣式
        if (tree._dragSource && tree._dragSource.tr) {
            tree._dragSource.tr.classList.remove('bk-tree-drag-source');
        }

        tree._dragSource = null;
        tree._dropTarget = null;
    }

})();
