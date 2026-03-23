/**
 * BeakTrellis Drag & Drop Plugin
 * 拖曳節點實現同層排序、跨層移動（多欄 TreeGrid 版）
 *
 * 功能：
 *   - 拖曳節點到同層其他位置（排序）
 *   - 拖曳節點到另一個節點下（成為子節點）
 *   - 拖曳節點到根層
 *   - 防止循環參照（不能拖進自己的後代）
 *   - 拖曳中自動展開收合的節點
 *   - 視覺回饋：插入線、容器高亮
 *   - Split Pane 模式：左右面板同步高亮與來源標記
 *
 * 使用方式：
 *   載入此檔（在 beak-trellis-splitpane.js 之後），並設定 options.draggable = true
 *
 * 不支援：
 *   - virtualScroll 模式（VS 下 DOM 動態重建，暫不支援拖曳）
 *
 * 回呼：
 *   options.onNodeMoved(nodeId, newParentId, newIndex, node)
 *
 * 依賴：beak-trellis.js, beak-tree-model.js
 * 授權：MIT
 */
'use strict';

(function() {

    // 放置區域常數
    var DROP_ZONE_EDGE = 0.3;  // 上下 30% 為「插入前/後」

    // 拖曳途中懸停展開的延遲（ms）
    var HOVER_EXPAND_DELAY = 600;

    // ========== 掛載到 BeakTrellis 原型 ==========

    var _origRender = BeakTrellis.prototype.render;
    var _origRefresh = BeakTrellis.prototype._refresh;

    /**
     * 覆寫 render，完成後初始化拖曳
     */
    BeakTrellis.prototype.render = function() {
        _origRender.call(this);
        if (this.options.draggable) {
            this._initTrellisDrag();
        }
    };

    /**
     * 覆寫 _refresh，完成後重新綁定拖曳
     */
    BeakTrellis.prototype._refresh = function() {
        _origRefresh.call(this);
        if (this.options.draggable) {
            this._initTrellisDrag();
        }
    };

    // ========== 拖曳初始化 ==========

    BeakTrellis.prototype._initTrellisDrag = function() {
        // VS 模式不支援拖曳
        if (this.options.virtualScroll && this._vsState) return;

        var self = this;

        // 加上 bt-draggable class（讓 CSS cursor: grab 生效）
        this.container.classList.add('bt-draggable');

        // 收集要綁定事件的 tbody
        var tbodies = [];
        if (this.options.splitPane && this._leftTbodyEl && this._rightTbodyEl) {
            tbodies.push(this._leftTbodyEl);
            tbodies.push(this._rightTbodyEl);
        } else if (this._tbodyEl) {
            tbodies.push(this._tbodyEl);
        }

        if (tbodies.length === 0) return;

        // 設定所有行可拖曳 + 綁定事件
        for (var t = 0; t < tbodies.length; t++) {
            var rows = tbodies[t].querySelectorAll('tr.bt-row');
            for (var i = 0; i < rows.length; i++) {
                var tr = rows[i];
                tr.draggable = true;

                // 移除舊事件（避免重複綁定）
                tr.removeEventListener('dragstart', tr._onTrellisDragStart);
                tr.removeEventListener('dragend', tr._onTrellisDragEnd);

                tr._onTrellisDragStart = _makeDragStart(self, tr);
                tr._onTrellisDragEnd = _makeDragEnd(self);

                tr.addEventListener('dragstart', tr._onTrellisDragStart);
                tr.addEventListener('dragend', tr._onTrellisDragEnd);
            }
        }

        // tbody 層級的 dragover / drop / dragleave
        for (var t = 0; t < tbodies.length; t++) {
            var tbody = tbodies[t];
            tbody.removeEventListener('dragover', tbody._onTrellisDragOver);
            tbody.removeEventListener('drop', tbody._onTrellisDrop);
            tbody.removeEventListener('dragleave', tbody._onTrellisDragLeave);

            tbody._onTrellisDragOver = _makeDragOver(self);
            tbody._onTrellisDrop = _makeDrop(self);
            tbody._onTrellisDragLeave = _makeDragLeave(self, tbodies);

            tbody.addEventListener('dragover', tbody._onTrellisDragOver);
            tbody.addEventListener('drop', tbody._onTrellisDrop);
            tbody.addEventListener('dragleave', tbody._onTrellisDragLeave);
        }

        // 確保 indicator 存在
        if (!this._trellisDragIndicator) {
            var ind = document.createElement('div');
            ind.className = 'bt-trellis-drag-indicator';
            ind.style.display = 'none';
            this.container.appendChild(ind);
            this._trellisDragIndicator = ind;
        }
    };

    // ========== 事件工廠 ==========

    function _makeDragStart(grid, tr) {
        return function(e) {
            var nodeId = tr.dataset.id;
            var node = grid._model.getNode(nodeId);
            if (!node) return;

            grid._trellisDragSource = {
                id: nodeId,
                node: node
            };

            // 設定拖曳資料（必要，否則某些瀏覽器不啟動拖曳）
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', nodeId);

            // 延遲加樣式（否則 ghost 會帶上透明度）
            requestAnimationFrame(function() {
                _applyToMatchingRows(grid, nodeId, function(row) {
                    row.classList.add('bt-trellis-drag-source');
                });
            });
        };
    }

    function _makeDragEnd(grid) {
        return function() {
            _clearDragState(grid);
        };
    }

    function _makeDragOver(grid) {
        return function(e) {
            if (!grid._trellisDragSource) return;

            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            var tr = _findRow(e.target);
            if (!tr) {
                _hideIndicator(grid);
                return;
            }

            var targetId = tr.dataset.id;
            var sourceId = grid._trellisDragSource.id;

            // 不能放到自己身上
            if (targetId === sourceId) {
                _hideIndicator(grid);
                return;
            }

            // 不能放到自己的後代
            if (grid._model.isDescendantOf(targetId, sourceId)) {
                _hideIndicator(grid);
                e.dataTransfer.dropEffect = 'none';
                return;
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

            // dragFlatOnly: 禁止拖入子層，只允許同層排序
            if (grid.options.dragFlatOnly && dropAction === 'inside') {
                dropAction = 'after';
            }

            grid._trellisDropTarget = {
                id: targetId,
                tr: tr,
                action: dropAction
            };

            _showIndicator(grid, tr, dropAction);

            // 懸停展開
            _handleHoverExpand(grid, targetId, dropAction);
        };
    }

    function _makeDrop(grid) {
        return function(e) {
            e.preventDefault();

            if (!grid._trellisDragSource || !grid._trellisDropTarget) {
                _clearDragState(grid);
                return;
            }

            var sourceId = grid._trellisDragSource.id;
            var sourceNode = grid._trellisDragSource.node;
            var targetId = grid._trellisDropTarget.id;
            var action = grid._trellisDropTarget.action;
            var targetNode = grid._model.getNode(targetId);

            if (!targetNode) {
                _clearDragState(grid);
                return;
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
                var siblings;
                if (newParentId) {
                    var parent = grid._model.getNode(newParentId);
                    siblings = parent ? parent.children : [];
                } else {
                    siblings = grid._model.getRootNodes();
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
            var result = grid._model.moveNode(sourceId, newParentId, newIndex);

            _clearDragState(grid);

            if (result) {
                grid._refresh();

                // 通知回呼
                if (grid.options.onNodeMoved) {
                    grid.options.onNodeMoved(sourceId, newParentId, newIndex, sourceNode);
                }
            }
        };
    }

    function _makeDragLeave(grid, tbodies) {
        return function(e) {
            // 只在離開所有 tbody 時清除
            var related = e.relatedTarget;
            if (related) {
                for (var i = 0; i < tbodies.length; i++) {
                    if (tbodies[i].contains(related)) return;
                }
            }
            _hideIndicator(grid);
            grid._trellisDropTarget = null;
        };
    }

    // ========== 指示器 ==========

    function _showIndicator(grid, tr, action) {
        var ind = grid._trellisDragIndicator;
        if (!ind) return;

        // 清除所有 row 的 drop highlight
        _clearDropHighlight(grid);

        if (action === 'inside') {
            // 高亮目標列（split pane 下同時高亮左右）
            _applyToMatchingRows(grid, tr.dataset.id, function(row) {
                row.classList.add('bt-trellis-drop-highlight');
            });
            ind.style.display = 'none';
        } else {
            // 顯示插入線
            var containerRect = grid.container.getBoundingClientRect();
            var trRect = tr.getBoundingClientRect();

            // 計算相對於 container 的位置
            var scrollTop = grid.container.scrollTop;

            var lineY;
            if (action === 'before') {
                lineY = trRect.top - containerRect.top + scrollTop;
            } else {
                lineY = trRect.bottom - containerRect.top + scrollTop;
            }

            // 指示線橫跨整個容器
            ind.style.display = 'block';
            ind.style.top = lineY + 'px';
            ind.style.left = '0';
            ind.style.right = '0';
        }
    }

    function _hideIndicator(grid) {
        if (grid._trellisDragIndicator) {
            grid._trellisDragIndicator.style.display = 'none';
        }
        _clearDropHighlight(grid);
    }

    function _clearDropHighlight(grid) {
        var els = grid.container.querySelectorAll('.bt-trellis-drop-highlight');
        for (var i = 0; i < els.length; i++) {
            els[i].classList.remove('bt-trellis-drop-highlight');
        }
    }

    // ========== 懸停展開 ==========

    function _handleHoverExpand(grid, targetId, action) {
        // 只在 inside 模式下自動展開
        if (action !== 'inside') {
            _cancelHoverExpand(grid);
            return;
        }

        if (grid._trellisHoverExpandId === targetId) return; // 已經在等待

        _cancelHoverExpand(grid);
        grid._trellisHoverExpandId = targetId;

        var node = grid._model.getNode(targetId);
        if (!node || node.children.length === 0) return;
        if (grid._model.isExpanded(targetId)) return; // 已展開

        grid._trellisHoverExpandTimer = setTimeout(function() {
            grid._trellisHoverExpandId = null;
            grid._trellisHoverExpandTimer = null;
            grid.expand(targetId);
        }, HOVER_EXPAND_DELAY);
    }

    function _cancelHoverExpand(grid) {
        if (grid._trellisHoverExpandTimer) {
            clearTimeout(grid._trellisHoverExpandTimer);
            grid._trellisHoverExpandTimer = null;
        }
        grid._trellisHoverExpandId = null;
    }

    // ========== 工具 ==========

    /**
     * 向上找到最近的 tr.bt-row
     */
    function _findRow(el) {
        while (el && el.tagName !== 'TR') {
            el = el.parentElement;
        }
        if (el && el.classList.contains('bt-row')) return el;
        return null;
    }

    /**
     * 對所有匹配 data-id 的 row 執行 fn（split pane 下左右各一）
     */
    function _applyToMatchingRows(grid, nodeId, fn) {
        var rows = grid.container.querySelectorAll('tr.bt-row[data-id="' + nodeId + '"]');
        for (var i = 0; i < rows.length; i++) {
            fn(rows[i]);
        }
    }

    function _clearDragState(grid) {
        _hideIndicator(grid);
        _cancelHoverExpand(grid);

        // 清除 source 樣式（split pane 下左右都要清）
        if (grid._trellisDragSource) {
            _applyToMatchingRows(grid, grid._trellisDragSource.id, function(row) {
                row.classList.remove('bt-trellis-drag-source');
            });
        }

        grid._trellisDragSource = null;
        grid._trellisDropTarget = null;
    }

})();
