/**
 * Tree Lines 渲染器
 * OS tree 指令風格的連續線條
 *
 * 視覺效果：
 * ├── 節點A
 * │   ├── 子節點A1
 * │   │   └── 孫節點A1a
 * │   └── 子節點A2
 * └── 節點B
 *
 * 使用 CSS border 繪製連線，非 Unicode box-drawing 字元
 * 確保跨瀏覽器、跨字型一致性
 */
'use strict';

(function() {

    const RENDERER_NAME = 'lines';

    /**
     * 渲染單個 Tree Cell
     * @param {Object} node - 節點物件
     * @param {Array} ancestors - 祖先節點陣列（從根到父）
     * @param {BeakTrellis} grid - BeakTrellis 實例
     * @returns {HTMLElement}
     */
    function renderTreeCell(node, ancestors, grid) {
        const container = document.createElement('div');
        container.className = 'bt-tree-cell';

        // 1. 祖先層的垂直連線（每一層一個 indent 區塊）
        for (let i = 0; i < ancestors.length; i++) {
            const ancestor = ancestors[i];
            const indent = document.createElement('span');
            indent.className = 'bt-indent';

            // 如果該祖先是其同層的最後一個，後面不需要垂直線
            if (ancestor._isLast) {
                indent.classList.add('bt-indent-blank');
            } else {
                indent.classList.add('bt-indent-vline');
            }
            container.appendChild(indent);
        }

        // 2. 本節點的分支連線
        const branch = document.createElement('span');
        branch.className = 'bt-branch';
        if (node.level > 0) {
            if (node._isLast) {
                branch.classList.add('bt-branch-last');   // └──
            } else {
                branch.classList.add('bt-branch-mid');    // ├──
            }
        }
        container.appendChild(branch);

        // 3. 展開/收合按鈕
        if (node.children.length > 0) {
            const toggle = document.createElement('span');
            toggle.className = 'bt-toggle bt-toggle';
            if (grid.isExpanded(node.id)) {
                toggle.classList.add('bt-toggle-expanded');
                toggle.textContent = '[-]';
            } else {
                toggle.classList.add('bt-toggle-collapsed');
                toggle.textContent = '[+]';
            }
            container.appendChild(toggle);
        } else {
            // 葉節點：佔位
            const leaf = document.createElement('span');
            leaf.className = 'bt-leaf-spacer';
            container.appendChild(leaf);
        }

        // 4. 節點標籤
        const label = document.createElement('span');
        label.className = 'bt-label';
        label.textContent = node.label;
        container.appendChild(label);

        return container;
    }

    // 註冊渲染器
    var rendererDef = { renderTreeCell: renderTreeCell };
    if (typeof BeakTrellis !== 'undefined' && BeakTrellis.registerRenderer) {
        BeakTrellis.registerRenderer(RENDERER_NAME, rendererDef);
    }
    if (typeof BeakTree !== 'undefined' && BeakTree.registerRenderer) {
        BeakTree.registerRenderer(RENDERER_NAME, rendererDef);
    }

})();
