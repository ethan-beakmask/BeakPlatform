/**
 * Scope Lines 渲染器
 * 兩種模式：
 *   1. scope-brackets: 括號式，同層首尾用大括號包裹
 *   2. scope-lines: 垂直線段式 (Indent Guides)，同層用垂直線標示範圍
 *
 * scope-brackets 視覺效果：
 * { WAF 警示事件
 *   { SQL Injection 攻擊
 *     { 來源 IP: 203.0.113.45
 *       [ URI: /api/users?id=1 OR 1=1 ]
 *       [ URI: /api/login UNION SELECT ]
 *     }
 *     [ 來源 IP: 198.51.100.78 ]
 *   }
 *   [ XSS 攻擊 ]
 * }
 *
 * scope-lines 視覺效果：
 * +--- WAF 警示事件
 * | +--- SQL Injection 攻擊
 * | | +--- 來源 IP: 203.0.113.45
 * | | |  URI: /api/users?id=1 OR 1=1
 * | | |  URI: /api/login UNION SELECT
 * | | +---
 * | |  來源 IP: 198.51.100.78
 * | +---
 * |  XSS 攻擊
 * +---
 */
'use strict';

(function() {

    // ========== scope-brackets 渲染器 ==========

    function renderBracketsCell(node, ancestors, grid) {
        var container = document.createElement('div');
        container.className = 'bt-scope-cell bt-scope-brackets-cell';

        var hasChildren = node.children.length > 0;
        var isExpanded = grid.isExpanded(node.id);

        // 1. 祖先層的垂直範圍線（每層一個 indent 區塊）
        for (var i = 0; i < ancestors.length; i++) {
            var indent = document.createElement('span');
            indent.className = 'bt-scope-indent';

            // 判斷這個祖先是否展開（展開才有垂直線）
            if (grid.isExpanded(ancestors[i].id)) {
                indent.classList.add('bt-scope-indent-active');
                // 顏色依層級
                indent.dataset.level = ancestors[i].level;
            }
            container.appendChild(indent);
        }

        // 2. 本層的括號標記
        var bracket = document.createElement('span');
        bracket.className = 'bt-scope-bracket';

        if (hasChildren && isExpanded) {
            // 展開的父節點：開括號 {
            bracket.classList.add('bt-scope-bracket-open');
            bracket.textContent = '{';
        } else if (hasChildren && !isExpanded) {
            // 收合的父節點：[+]
            bracket.classList.add('bt-scope-bracket-collapsed');
            bracket.textContent = '{+}';
        } else {
            // 葉節點：用方括號或不顯示
            // 判斷是否同層只有一個
            var parent = node.parentId ? grid.getNode(node.parentId) : null;
            if (parent && parent.children.length === 1) {
                bracket.classList.add('bt-scope-bracket-single');
                bracket.textContent = '';
            } else {
                bracket.classList.add('bt-scope-bracket-leaf');
                bracket.textContent = '';
            }
        }
        container.appendChild(bracket);

        // 3. 展開/收合按鈕（用括號本身當按鈕）
        if (hasChildren) {
            bracket.classList.add('bt-toggle');
            bracket.style.cursor = 'pointer';
        }

        // 4. 節點標籤
        var label = document.createElement('span');
        label.className = 'bt-scope-label';
        label.textContent = node.label;
        container.appendChild(label);

        // 5. 如果是展開狀態且是同層最後一個子節點的下一行需要閉括號
        //    閉括號由 _injectClosingBrackets 在 render 後處理

        return container;
    }

    // ========== scope-lines 渲染器 ==========

    function renderScopeLinesCell(node, ancestors, grid) {
        var container = document.createElement('div');
        container.className = 'bt-scope-cell bt-scope-lines-cell';

        var hasChildren = node.children.length > 0;
        var isExpanded = grid.isExpanded(node.id);

        // 1. 祖先層的垂直範圍線
        for (var i = 0; i < ancestors.length; i++) {
            var indent = document.createElement('span');
            indent.className = 'bt-scope-indent';

            if (grid.isExpanded(ancestors[i].id)) {
                indent.classList.add('bt-scope-indent-active');
                indent.dataset.level = ancestors[i].level;
            }
            container.appendChild(indent);
        }

        // 2. 本層的 scope 標記
        var marker = document.createElement('span');
        marker.className = 'bt-scope-marker';

        if (hasChildren && isExpanded) {
            // 展開的父節點：上邊界 +---
            marker.classList.add('bt-scope-marker-open');
        } else if (hasChildren && !isExpanded) {
            // 收合的父節點：[+]---
            marker.classList.add('bt-scope-marker-collapsed');
            marker.textContent = '[+]';
        } else {
            // 葉節點：空白佔位
            marker.classList.add('bt-scope-marker-leaf');
        }
        container.appendChild(marker);

        // 3. 展開/收合
        if (hasChildren) {
            marker.classList.add('bt-toggle');
            marker.style.cursor = 'pointer';
        }

        // 4. 節點標籤
        var label = document.createElement('span');
        label.className = 'bt-scope-label';
        label.textContent = node.label;
        container.appendChild(label);

        return container;
    }

    // ========== 閉括號注入（scope-brackets 專用） ==========
    // 在渲染完成後，為每個展開的父節點在其最後一個可見子孫後插入閉括號列

    function afterRender(grid, mode) {
        if (mode !== 'scope-brackets') return;

        var tbody = grid._tbodyEl;
        if (!tbody) return;

        var rows = tbody.querySelectorAll('tr');
        var flatNodes = grid._flatNodes;

        // 找出所有需要閉括號的節點（已展開且有子節點）
        // 從後往前插入，避免索引偏移
        var closingEntries = [];

        for (var i = 0; i < flatNodes.length; i++) {
            var node = flatNodes[i];
            if (grid.isExpanded(node.id) && node.children.length > 0) {
                // 找到這個節點的最後一個可見子孫在 flatNodes 中的位置
                var lastVisibleIdx = _findLastVisibleDescendantIdx(flatNodes, i, node.id, grid);
                closingEntries.push({
                    parentNode: node,
                    insertAfterIdx: lastVisibleIdx
                });
            }
        }

        // 排序：從後往前插入
        closingEntries.sort(function(a, b) { return b.insertAfterIdx - a.insertAfterIdx; });

        for (var j = 0; j < closingEntries.length; j++) {
            var entry = closingEntries[j];
            var pNode = entry.parentNode;
            var afterRow = rows[entry.insertAfterIdx];
            if (!afterRow) continue;

            // 建立閉括號列
            var closingTr = document.createElement('tr');
            closingTr.className = 'bt-row bt-row-closing';
            closingTr.dataset.closingFor = pNode.id;

            // 計算需要多少欄位
            var totalCols = 1; // tree 欄
            var hasCb = grid.options.columns.some(function(c) { return c.type === 'checkbox'; });
            if (hasCb) totalCols++;
            var dataCols = grid.options.columns.filter(function(c) { return c.type !== 'checkbox'; });
            totalCols += dataCols.length;

            // checkbox 佔位
            if (hasCb) {
                var tdCb = document.createElement('td');
                tdCb.className = 'bt-td bt-td-checkbox';
                closingTr.appendChild(tdCb);
            }

            // 閉括號 cell
            var tdClose = document.createElement('td');
            tdClose.className = 'bt-td bt-td-tree';

            var closeDiv = document.createElement('div');
            closeDiv.className = 'bt-scope-cell bt-scope-brackets-cell bt-scope-closing';

            // 祖先層縮排
            var ancestors = grid.getAncestors(pNode.id);
            for (var k = 0; k < ancestors.length; k++) {
                var indent = document.createElement('span');
                indent.className = 'bt-scope-indent';
                if (grid.isExpanded(ancestors[k].id)) {
                    indent.classList.add('bt-scope-indent-active');
                    indent.dataset.level = ancestors[k].level;
                }
                closeDiv.appendChild(indent);
            }

            var closeBracket = document.createElement('span');
            closeBracket.className = 'bt-scope-bracket bt-scope-bracket-close';
            closeBracket.textContent = '}';
            closeDiv.appendChild(closeBracket);

            tdClose.appendChild(closeDiv);
            closingTr.appendChild(tdClose);

            // 資料欄佔位
            for (var m = 0; m < dataCols.length; m++) {
                var tdEmpty = document.createElement('td');
                tdEmpty.className = 'bt-td bt-td-data';
                closingTr.appendChild(tdEmpty);
            }

            // 插入到目標列後面
            if (afterRow.nextSibling) {
                tbody.insertBefore(closingTr, afterRow.nextSibling);
            } else {
                tbody.appendChild(closingTr);
            }

            // 更新 rows 參照（重新查詢因為 DOM 已改變）
            rows = tbody.querySelectorAll('tr');
        }
    }

    /**
     * 找到某節點在 flatNodes 中最後一個可見子孫的索引
     */
    function _findLastVisibleDescendantIdx(flatNodes, parentIdx, parentId, grid) {
        var lastIdx = parentIdx;
        var parentLevel = flatNodes[parentIdx].level;

        for (var i = parentIdx + 1; i < flatNodes.length; i++) {
            if (flatNodes[i].level <= parentLevel) {
                break;
            }
            lastIdx = i;
        }
        return lastIdx;
    }

    // ========== 渲染器註冊 ==========

    var bracketsDef = {
        renderTreeCell: renderBracketsCell,
        afterRender: function(grid) { afterRender(grid, 'scope-brackets'); }
    };
    var scopeLinesDef = {
        renderTreeCell: renderScopeLinesCell,
        afterRender: function(grid) { afterRender(grid, 'scope-lines'); }
    };

    if (typeof BeakTrellis !== 'undefined' && BeakTrellis.registerRenderer) {
        BeakTrellis.registerRenderer('scope-brackets', bracketsDef);
        BeakTrellis.registerRenderer('scope-lines', scopeLinesDef);
    }
    if (typeof BeakTree !== 'undefined' && BeakTree.registerRenderer) {
        BeakTree.registerRenderer('scope-brackets', bracketsDef);
        BeakTree.registerRenderer('scope-lines', scopeLinesDef);
    }

})();
