/**
 * 工作流子流程階層圖 - 使用 d3-org-chart
 * 橫向樹狀目錄佈局：主流程在左上角，子流程往右展開
 */
(function () {
    'use strict';

    // 節點尺寸 (卡片式：上方 3:2 橫式縮圖 + 下方資訊)
    var NODE_WIDTH = 240;
    var NODE_HEIGHT = 195;
    var THUMB_WIDTH = 224;
    var THUMB_HEIGHT = 150;

    /**
     * 將巢狀樹結構攤平為 d3-org-chart 所需的扁平陣列
     */
    function flattenTrees(trees) {
        var nodes = [];

        function walk(node, parentId, depth) {
            var entry = {
                id: node.secure_code,
                parentId: parentId,
                name: node.name || '未命名',
                code: node.code || '',
                thumbnail: node.thumbnail_2x1 || null,
                nodeCount: node.node_count || 0,
                isRoot: !parentId,
                depth: depth
            };
            nodes.push(entry);

            if (node.children && node.children.length > 0) {
                node.children.forEach(function (child) {
                    walk(child, node.secure_code, depth + 1);
                });
            }
        }

        trees.forEach(function (tree) {
            walk(tree, null, 0);
        });

        return nodes;
    }

    /**
     * 產生卡片式節點 HTML（上方縮圖 + 下方資訊列）
     */
    function renderNodeContent(d) {
        var data = d.data;
        var isRoot = data.isRoot;

        var borderColor = isRoot ? '#3b82f6' : '#d1d5db';
        var borderWidth = isRoot ? '2px' : '1px';
        var bgColor = isRoot ? '#eff6ff' : '#fff';
        var labelColor = isRoot ? '#1e40af' : '#374151';

        // 縮圖
        var thumbHtml;
        if (data.thumbnail) {
            thumbHtml = '<img src="' + data.thumbnail + '" style="' +
                'width:100%;height:100%;object-fit:contain;" />';
        } else {
            var iconBg = isRoot ? '#dbeafe' : '#f3f4f6';
            var iconColor = isRoot ? '#3b82f6' : '#9ca3af';
            thumbHtml = '<div style="display:flex;align-items:center;justify-content:center;' +
                'width:100%;height:100%;background:' + iconBg + ';">' +
                '<i class="ri-flow-chart" style="font-size:28px;color:' + iconColor + ';"></i>' +
                '</div>';
        }

        // 資訊列
        var badge = isRoot
            ? '<span style="color:#3b82f6;font-weight:600;">主流程</span>'
            : '<span style="color:#9ca3af;">' + data.nodeCount + ' 節點</span>';

        if (data.code) {
            badge += '<span style="color:#9ca3af;margin-left:6px;">' + data.code + '</span>';
        }

        return '<div style="' +
            'width:' + NODE_WIDTH + 'px;' +
            'height:' + NODE_HEIGHT + 'px;' +
            'background:' + bgColor + ';' +
            'border:' + borderWidth + ' solid ' + borderColor + ';' +
            'border-radius:6px;' +
            'display:flex;flex-direction:column;' +
            'cursor:pointer;font-family:inherit;' +
            'box-shadow:0 1px 2px rgba(0,0,0,0.05);' +
            'overflow:hidden;' +
        '">' +
            '<div style="' +
                'width:' + THUMB_WIDTH + 'px;height:' + THUMB_HEIGHT + 'px;' +
                'margin:4px auto 0;' +
                'border:1px solid #e5e7eb;' +
                'overflow:hidden;' +
            '">' + thumbHtml + '</div>' +
            '<div style="' +
                'padding:3px 8px 0;' +
                'font-size:12px;font-weight:' + (isRoot ? '600' : '500') + ';' +
                'color:' + labelColor + ';' +
                'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;' +
                'text-align:center;line-height:1.3;' +
            '" title="' + data.name + '">' + data.name + '</div>' +
            '<div style="text-align:center;font-size:10px;line-height:1.3;">' + badge + '</div>' +
        '</div>';
    }

    /**
     * 渲染橫向樹狀圖
     */
    function renderFlowTreeChart(containerId, trees, options) {
        options = options || {};

        var container = document.querySelector(containerId);
        if (!container) return null;

        container.innerHTML = '';

        var flatData = flattenTrees(trees);
        if (flatData.length === 0) return null;

        // 多棵樹時加虛擬根節點
        var roots = flatData.filter(function (n) { return !n.parentId; });
        if (roots.length > 1) {
            flatData.unshift({
                id: '__virtual_root__',
                parentId: null,
                name: '所有流程樹',
                code: '',
                thumbnail: null,
                nodeCount: 0,
                isRoot: false,
                depth: 0,
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
            .childrenMargin(function () { return 40; })
            .siblingsMargin(function () { return 12; })
            .neighbourMargin(function () { return 30; })
            .compactMarginBetween(function () { return 12; })
            .compactMarginPair(function () { return 30; })
            .nodeContent(function (d) {
                if (d.data._isVirtual) {
                    return '<div style="' +
                        'width:' + NODE_WIDTH + 'px;height:36px;' +
                        'display:flex;align-items:center;justify-content:center;' +
                        'font-size:12px;font-weight:600;color:#6b7280;' +
                        'background:#f9fafb;border:1px dashed #d1d5db;border-radius:6px;' +
                    '">所有流程樹</div>';
                }
                return renderNodeContent(d);
            })
            .nodeUpdate(function (d) {
                d3.select(this).select('.node-rect').attr('stroke', 'none').attr('fill', 'none');
            })
            .onNodeClick(function (d) {
                if (d.data._isVirtual) return;
                if (options.onNodeClick) {
                    options.onNodeClick(d.data);
                }
            })
            .layout('left')
            .compact(true)
            .initialExpandLevel(10)
            .render();

        // 初次渲染後 fit
        setTimeout(function () {
            chart.fit();
        }, 300);

        return chart;
    }

    window.WorkflowTreeChart = {
        render: renderFlowTreeChart
    };
})();
