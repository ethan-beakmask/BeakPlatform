/**
 * fc-flow-overview.js — 流程總圖 mixin (子流程展開 + Mode B 替換 + Cytoscape 渲染)
 * 由 form-center.js 拆分而來
 */

// --- 流程總圖常數 (子流程展開 + Mode B 替換) ---
const _FC_VISIBLE_TYPES = new Set(['Start', 'FormAdapter', 'End', 'EmailAdapter']);
const _FC_REPLACE_LABEL = '系統node';
const _FC_SYS_COLOR = '#d1d5db';
const _FC_SYS_BORDER = '#9ca3af';
const _FC_NODE_COLORS = {
    'Start': '#22c55e', 'End': '#ef4444', 'FormAdapter': '#3b82f6',
    'EmailAdapter': '#f59e0b', 'default': '#E0E0E0'
};
const _FC_GROUP_COLORS = [
    { bg: 'rgba(59,130,246,0.08)', border: '#3b82f6' },
    { bg: 'rgba(139,92,246,0.10)', border: '#8b5cf6' },
    { bg: 'rgba(236,72,153,0.10)', border: '#ec4899' },
];

function fcFlowOverview() {
    return {
        // --- State ---
        showFlowOverviewModal: false,
        flowOverviewCy: null,
        flowOverviewLoading: false,
        flowOverviewError: null,
        flowOverviewInfo: {},

        // --- Methods ---
        _fcFlattenGraph(graph, codeToTab, depth, prefix, parentGroupId) {
            if (!graph) return { nodes: [], edges: [], groups: [] };

            let nodes = (graph.nodes || []).filter(n => n.type !== 'group');
            let edges = [...(graph.edges || [])];
            const groups = [];

            if (prefix) {
                nodes = nodes.map(n => ({
                    ...n, id: prefix + n.id,
                    position: { ...(n.position || { x: 0, y: 0 }) },
                    config: n.config
                }));
                edges = edges.map((e, i) => ({
                    ...e, id: prefix + (e.id || `e${i}`),
                    source: prefix + e.source, target: prefix + e.target
                }));
            }
            if (parentGroupId) nodes.forEach(n => { n.parent = parentGroupId; });

            const sfNodes = nodes.filter(n => n.type === 'Subflow' || n.type === 'SubFlow');
            for (const sfNode of sfNodes) {
                const origNode = prefix
                    ? (graph.nodes || []).find(n => (prefix + n.id) === sfNode.id)
                    : sfNode;
                const childFlowId = origNode?.config?.childFlowId;
                if (!childFlowId) continue;

                const childTab = codeToTab[childFlowId];
                if (!childTab || !childTab.graph) continue;

                const subGraph = childTab.graph;
                const subRealNodes = (subGraph.nodes || []).filter(n => n.type !== 'group');
                if (subRealNodes.length === 0) continue;

                let cx = 0, cy = 0;
                subRealNodes.forEach(n => { cx += (n.position?.x || 0); cy += (n.position?.y || 0); });
                cx /= subRealNodes.length; cy /= subRealNodes.length;
                const offsetX = sfNode.position.x - cx;
                const offsetY = sfNode.position.y - cy + 180 + depth * 40;

                const groupId = `group_${sfNode.id}`;
                groups.push({ id: groupId, label: childTab.name || '子流程', parent: parentGroupId || null, level: Math.min(depth, _FC_GROUP_COLORS.length - 1) });

                const subPrefix = `sf${depth}_${sfNode.id}_`;
                const subResult = this._fcFlattenGraph(subGraph, codeToTab, depth + 1, subPrefix, groupId);

                subResult.nodes.forEach(n => { n.position.x += offsetX; n.position.y += offsetY; });

                const subStartId = subResult.nodes.find(n => n.type === 'Start')?.id;
                const subEndIds = subResult.nodes.filter(n => n.type === 'End').map(n => n.id);

                if (subStartId) edges.forEach(e => { if (e.target === sfNode.id) e.target = subStartId; });
                const outEdges = edges.filter(e => e.source === sfNode.id);
                edges = edges.filter(e => e.source !== sfNode.id);
                for (const endId of subEndIds) {
                    for (const out of outEdges) {
                        edges.push({ id: `f_${endId}_${out.target}_${Math.random().toString(36).substr(2,5)}`, source: endId, target: out.target, label: '' });
                    }
                }

                nodes = nodes.filter(n => n.id !== sfNode.id);
                nodes.push(...subResult.nodes);
                edges.push(...subResult.edges);
                groups.push(...subResult.groups);
            }
            return { nodes, edges, groups };
        },

        _fcApplyReplace(flatResult) {
            const nodeMap = {};
            flatResult.nodes.forEach(n => { nodeMap[n.id] = n; });

            const resultNodes = flatResult.nodes.map(node => {
                if (_FC_VISIBLE_TYPES.has(node.type)) {
                    return { ...node, isSystem: false };
                }
                return { ...node, originalType: node.type, type: 'system', label: _FC_REPLACE_LABEL, isSystem: true };
            });

            const resultEdges = flatResult.edges.map((e, i) => ({
                id: e.id || `e-${i}`, source: e.source, target: e.target, label: e.label || '',
                isSystem: (nodeMap[e.source] && !_FC_VISIBLE_TYPES.has(nodeMap[e.source].type)) ||
                          (nodeMap[e.target] && !_FC_VISIBLE_TYPES.has(nodeMap[e.target].type))
            }));

            return { nodes: resultNodes, edges: resultEdges, groups: flatResult.groups };
        },

        _fcApplyStatus(result, data) {
            const history = data.execution_history || [];
            const statusMap = {};
            history.forEach(h => { statusMap[h.node_id] = h.status; });

            result.nodes.forEach(n => {
                const bareId = n.id.replace(/^sf\d+_[^_]+_/, '');
                n.execStatus = statusMap[n.id] || statusMap[bareId] || null;
            });
        },

        _fcRenderCytoscape(containerId, result) {
            const elements = [];

            // 群組
            [...result.groups].sort((a, b) => (a.level || 0) - (b.level || 0)).forEach(g => {
                const gc = _FC_GROUP_COLORS[g.level || 0];
                const data = { id: g.id, label: g.label, color: gc.bg, borderColor: gc.border };
                if (g.parent) data.parent = g.parent;
                elements.push({ data });
            });

            // 節點
            result.nodes.forEach(node => {
                const isSys = node.isSystem;
                const data = {
                    id: node.id, label: node.label || node.id, type: node.type,
                    color: isSys ? _FC_SYS_COLOR : (_FC_NODE_COLORS[node.type] || _FC_NODE_COLORS['default']),
                    borderColor: isSys ? _FC_SYS_BORDER : '#333'
                };
                if (node.parent) data.parent = node.parent;

                let classes = isSys ? 'system-node' : '';
                if (node.execStatus === 'RUNNING') classes += ' node-running';
                else if (node.execStatus === 'SUCCESS') classes += ' node-completed';
                else if (['FAILED','ERROR','TIMEOUT'].includes(node.execStatus)) classes += ' node-failed';

                elements.push({ data, position: { ...node.position }, classes: classes.trim() });
            });

            // 邊
            result.edges.forEach(edge => {
                elements.push({
                    data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label || '' },
                    classes: edge.isSystem ? 'system-edge' : ''
                });
            });

            const container = document.getElementById(containerId);
            const cy = cytoscape({
                container,
                elements,
                style: [
                    { selector: 'node', style: {
                        'background-color': 'data(color)', 'label': 'data(label)',
                        'text-valign': 'center', 'text-halign': 'center', 'font-size': '10px',
                        'width': 90, 'height': 36, 'border-width': 2, 'border-color': 'data(borderColor)',
                        'text-wrap': 'wrap', 'text-max-width': '80px', 'shape': 'roundrectangle'
                    }},
                    { selector: 'node[type="Start"]', style: { 'shape': 'ellipse', 'width': 50, 'height': 50 } },
                    { selector: 'node[type="End"]', style: { 'shape': 'ellipse', 'width': 50, 'height': 50 } },
                    { selector: 'edge', style: {
                        'width': 2, 'line-color': '#bbb', 'target-arrow-color': '#bbb',
                        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': '9px'
                    }},
                    { selector: '.system-node', style: {
                        'background-color': _FC_SYS_COLOR, 'border-color': _FC_SYS_BORDER,
                        'border-style': 'dashed', 'border-width': 2, 'font-size': '9px',
                        'color': '#6b7280', 'width': 80, 'height': 28
                    }},
                    { selector: '.system-edge', style: {
                        'line-color': '#d1d5db', 'target-arrow-color': '#d1d5db',
                        'line-style': 'dashed', 'width': 1.5
                    }},
                    { selector: '.node-running', style: {
                        'background-color': '#FFC107', 'border-color': '#FF9800', 'border-width': 3
                    }},
                    { selector: '.node-completed', style: {
                        'background-color': '#4CAF50', 'border-color': '#388E3C', 'border-width': 2
                    }},
                    { selector: '.node-failed', style: {
                        'background-color': '#F44336', 'border-color': '#D32F2F', 'border-width': 3
                    }},
                    { selector: ':parent', style: {
                        'background-color': 'data(color)', 'background-opacity': 1,
                        'border-color': 'data(borderColor)', 'border-width': 2, 'border-style': 'dashed',
                        'label': 'data(label)', 'text-valign': 'top', 'text-halign': 'center',
                        'font-size': '11px', 'font-weight': 'bold', 'color': 'data(borderColor)',
                        'padding': '25px', 'shape': 'roundrectangle', 'text-margin-y': '-8px'
                    }}
                ],
                layout: { name: 'preset' },
                userZoomingEnabled: true, userPanningEnabled: true, boxSelectionEnabled: false
            });

            // 延遲 fit：確保容器已完成 layout 且有實際尺寸
            const delayedFit = () => {
                if (container.offsetWidth > 0 && container.offsetHeight > 0) {
                    cy.resize();
                    cy.fit(null, 50);
                } else {
                    // 容器尚未可見，重試
                    requestAnimationFrame(delayedFit);
                }
            };
            requestAnimationFrame(delayedFit);

            return cy;
        },

        async openFlowOverview(item) {
            this.flowOverviewLoading = true;
            this.flowOverviewError = null;
            this.flowOverviewInfo = {};
            this.showFlowOverviewModal = true;

            await this.$nextTick();

            try {
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const res = await fetch(`/bp/api/form-center/executions/${instanceId}/path`);
                const result = await res.json();

                if (!result.success) {
                    this.flowOverviewError = result.error || '載入失敗';
                    this.flowOverviewLoading = false;
                    return;
                }

                const data = result.data;
                const tabs = data.workflow_tabs || [];
                const mainTab = tabs.find(t => t.is_main) || tabs[0];

                if (!mainTab) {
                    this.flowOverviewError = '找不到流程圖資料';
                    this.flowOverviewLoading = false;
                    return;
                }

                this.flowOverviewInfo = {
                    executionCode: mainTab.execution_code || '',
                    workflowName: mainTab.name || '',
                    flowStatus: data.instance_status || '-'
                };

                const codeToTab = {};
                tabs.forEach(t => { if (t.workflow_code) codeToTab[t.workflow_code] = t; });

                const flatResult = this._fcFlattenGraph(mainTab.graph, codeToTab, 0, '', null);
                const finalResult = this._fcApplyReplace(flatResult);
                this._fcApplyStatus(finalResult, data);

                this.flowOverviewLoading = false;
                await this.$nextTick();

                if (this.flowOverviewCy) this.flowOverviewCy.destroy();
                this.flowOverviewCy = this._fcRenderCytoscape('cy-flow-overview', finalResult);

            } catch (e) {
                this.flowOverviewError = '載入錯誤: ' + e.message;
                this.flowOverviewLoading = false;
            }
        },

        closeFlowOverviewModal() {
            if (this.flowOverviewCy) {
                this.flowOverviewCy.destroy();
                this.flowOverviewCy = null;
            }
            this.showFlowOverviewModal = false;
            this.flowOverviewInfo = {};
        },
    };
}
