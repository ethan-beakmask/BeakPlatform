/**
 * 工作流子流程階層圖 - 使用 d3-org-chart
 * 將 API 回傳的樹狀結構渲染為組織架構圖
 */
(function () {
    'use strict';

    // 節點尺寸
    const NODE_WIDTH = 200;
    const NODE_HEIGHT = 140;
    const THUMB_WIDTH = 180;
    const THUMB_HEIGHT = 90;

    /**
     * 將巢狀樹結構攤平為 d3-org-chart 所需的扁平陣列
     * @param {Array} trees - API 回傳的 flowTrees
     * @returns {Array} 扁平化的節點陣列，含 id / parentId
     */
    function flattenTrees(trees) {
        const nodes = [];

        function walk(node, parentId) {
            const entry = {
                id: node.secure_code,
                parentId: parentId,
                name: node.name || '未命名',
                code: node.code || '',
                thumbnail: node.thumbnail_2x1 || null,
                nodeCount: node.node_count || 0,
                isRoot: !parentId
            };
            nodes.push(entry);

            if (node.children && node.children.length > 0) {
                node.children.forEach(function (child) {
                    walk(child, node.secure_code);
                });
            }
        }

        trees.forEach(function (tree) {
            walk(tree, null);
        });

        return nodes;
    }

    /**
     * 產生節點 HTML 內容
     */
    function renderNodeContent(d) {
        var data = d.data;
        var isRoot = data.isRoot;
        var borderColor = isRoot ? '#0066cc' : '#ddd';
        var borderWidth = isRoot ? '2px' : '1px';
        var label = data.name;
        var bgColor = isRoot ? '#f0f6ff' : '#fff';

        var thumbHtml;
        if (data.thumbnail) {
            thumbHtml = '<img src="' + data.thumbnail + '" ' +
                'style="max-width:100%;max-height:100%;object-fit:contain;" />';
        } else {
            thumbHtml = '<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#ccc;">' +
                '<i class="ri-flow-chart" style="font-size:28px;"></i></div>';
        }

        return '<div style="' +
            'width:' + NODE_WIDTH + 'px;' +
            'height:' + NODE_HEIGHT + 'px;' +
            'background:' + bgColor + ';' +
            'border:' + borderWidth + ' solid ' + borderColor + ';' +
            'display:flex;flex-direction:column;' +
            'font-family:inherit;' +
            'cursor:pointer;' +
            '">' +
            '<div style="' +
                'width:' + THUMB_WIDTH + 'px;' +
                'height:' + THUMB_HEIGHT + 'px;' +
                'margin:8px auto 0;' +
                'background:#f5f5f5;' +
                'border:1px solid #eee;' +
                'display:flex;align-items:center;justify-content:center;' +
                'overflow:hidden;' +
            '">' + thumbHtml + '</div>' +
            '<div style="' +
                'text-align:center;' +
                'padding:4px 8px 0;' +
                'font-size:12px;' +
                'font-weight:' + (isRoot ? '600' : '500') + ';' +
                'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;' +
                'color:#333;' +
            '" title="' + data.name + '">' + label + '</div>' +
            '<div style="text-align:center;font-size:10px;color:#999;">' +
                (isRoot ? '<span style="color:#0066cc;font-weight:600;">主流程</span> | ' : '') +
                data.nodeCount + ' 節點' +
                (data.code ? ' | ' + data.code : '') +
            '</div>' +
        '</div>';
    }

    /**
     * 渲染組織架構圖
     * @param {string} containerId - 容器元素 ID (含 #)
     * @param {Array} trees - API 回傳的 flowTrees 陣列
     * @param {Object} options - 選項
     * @param {Function} options.onNodeClick - 點擊節點回呼 (nodeData) => void
     */
    function renderFlowTreeChart(containerId, trees, options) {
        options = options || {};

        var container = document.querySelector(containerId);
        if (!container) return null;

        // 清空容器
        container.innerHTML = '';

        var flatData = flattenTrees(trees);
        if (flatData.length === 0) return null;

        // 如果有多棵樹，加一個虛擬根節點
        var roots = flatData.filter(function (n) { return !n.parentId; });
        if (roots.length > 1) {
            flatData.unshift({
                id: '__virtual_root__',
                parentId: null,
                name: '所有流程',
                code: '',
                thumbnail: null,
                nodeCount: 0,
                isRoot: false,
                _isVirtual: true
            });
            roots.forEach(function (r) {
                r.parentId = '__virtual_root__';
                r.isRoot = true;
            });
        }

        var chart = new d3.OrgChart()
            .container(containerId)
            .data(flatData)
            .nodeWidth(function () { return NODE_WIDTH + 20; })
            .nodeHeight(function () { return NODE_HEIGHT + 10; })
            .childrenMargin(function () { return 50; })
            .siblingsMargin(function () { return 30; })
            .neighbourMargin(function () { return 50; })
            .compactMarginBetween(function () { return 25; })
            .compactMarginPair(function () { return 50; })
            .nodeContent(function (d) {
                if (d.data._isVirtual) {
                    return '<div style="width:' + NODE_WIDTH + 'px;height:40px;' +
                        'display:flex;align-items:center;justify-content:center;' +
                        'font-size:14px;font-weight:600;color:#666;' +
                        'background:#f9f9f9;border:1px dashed #ccc;">所有流程樹</div>';
                }
                return renderNodeContent(d);
            })
            .nodeUpdate(function (d) {
                // 移除預設外框
                d3.select(this).select('.node-rect').attr('stroke', 'none').attr('fill', 'none');
            })
            .onNodeClick(function (d) {
                if (d.data._isVirtual) return;
                if (options.onNodeClick) {
                    options.onNodeClick(d.data);
                }
            })
            .layout('top')
            .compact(false)
            .initialExpandLevel(10)
            .render();

        // 初次渲染後 fit 到畫面
        setTimeout(function () {
            chart.fit();
        }, 500);

        return chart;
    }

    // 導出到全域
    window.WorkflowTreeChart = {
        render: renderFlowTreeChart
    };
})();
