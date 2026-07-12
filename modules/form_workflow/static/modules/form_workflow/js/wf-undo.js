/**
 * wf-undo.js -- Undo 系統
 * 從 workflow-main.js 拆分
 * 依賴: workflow-main.js (全域變數)
 */

        // ==================== Undo 系統 ====================
        const undoStack = [];
        const UNDO_MAX = 50;

        function pushUndoState() {
            if (!cy || cy.elements().length === 0) return;
            const state = cy.json().elements;
            undoStack.push(JSON.stringify(state));
            if (undoStack.length > UNDO_MAX) undoStack.shift();
        }

        function undo() {
            if (undoStack.length === 0) {
                updateStatus(__('沒有可復原的操作'), 'warning');
                return;
            }
            const state = JSON.parse(undoStack.pop());
            cy.elements().remove();
            cy.add(state);

            // 重新套用所有節點的樣式
            cy.nodes().forEach(node => {
                // 群組節點：恢復顏色、框線、圓角
                if (isGroupNode(node)) {
                    const gc = node.data('groupColor');
                    const borderStyle = node.data('borderStyle') || 'none';
                    const cornerStyle = node.data('cornerStyle') || 'round';
                    const styleObj = {
                        'shape': cornerStyle === 'round' ? 'roundrectangle' : 'rectangle'
                    };
                    if (gc) {
                        styleObj['background-color'] = `rgb(${gc.r}, ${gc.g}, ${gc.b})`;
                    }
                    if (borderStyle === 'none') {
                        styleObj['border-width'] = 0;
                        styleObj['background-opacity'] = 0.3;
                    } else {
                        styleObj['border-width'] = 2;
                        styleObj['border-style'] = borderStyle;
                        styleObj['background-opacity'] = 0.15;
                        styleObj['border-color'] = gc ? groupBorderColor(gc.r, gc.g, gc.b) : '#667eea';
                    }
                    node.style(styleObj);
                    return;
                }

                let iconUrl = node.data('iconUrl') || '';
                if (!iconUrl && node.data('icon')) {
                    const icon = node.data('icon');
                    if (icon.startsWith(window.__BP + '/static/') || icon.startsWith('http')) {
                        iconUrl = icon;
                    } else {
                        iconUrl = getSvgDataUrl(icon, '#333333');
                    }
                    node.data('iconUrl', iconUrl);
                }
                if (iconUrl) {
                    node.style({
                        'background-image': iconUrl,
                        'background-fit': 'contain',
                        'background-clip': 'none'
                    });
                }
                if (!globalNodeBorder) {
                    node.addClass('no-border');
                }
            });

            cy.style().update();

            // 重建控制點 Maps 和 bypass styles（undo 不保留這些）
            rebuildControlPointMaps();

            refreshAllEmptyGroups();
            updateMinimap();
            updateGridOccupancy();
            updateEdgeSelector();
            hasUnsavedChanges = true;
            updateSaveButtonState();
            updateStatus(`已復原 (剩餘 ${undoStack.length} 步)`);
        }

        function clearUndoState() {
            undoStack.length = 0;
            replaceNodeUndoBuffer = null;
        }

        // 重建所有控制點 Maps（undo/load 後呼叫）
        // cy.json().elements 不含 bypass styles，需從 data 屬性重建 Map 並重新套用視覺樣式
        function rebuildControlPointMaps() {
            orthogonalControlPoints.clear();
            yellowControlPoints.clear();
            taxiControlPoints.clear();

            // === Phase 1: 重建正交折線 Map ===
            const orthoNodesByEdge = new Map();
            cy.nodes('[type="relay"]').forEach(node => {
                if (!node.data('orthogonalControl')) return;
                const pid = node.data('parentEdge');
                if (!pid) return;
                if (!orthoNodesByEdge.has(pid)) orthoNodesByEdge.set(pid, []);
                orthoNodesByEdge.get(pid).push(node);
            });

            const orthoSegsByEdge = new Map();
            cy.edges('[edgeType="orthogonal-segment"]').forEach(seg => {
                const pid = seg.data('parentEdge');
                if (!pid) return;
                if (!orthoSegsByEdge.has(pid)) orthoSegsByEdge.set(pid, []);
                orthoSegsByEdge.get(pid).push(seg);
            });

            orthoNodesByEdge.forEach((relayNodes, edgeId) => {
                const edge = cy.getElementById(edgeId);
                if (edge.length === 0) return;

                relayNodes.sort((a, b) => (a.data('pointIndex') || 0) - (b.data('pointIndex') || 0));
                const relayEdges = (orthoSegsByEdge.get(edgeId) || []);
                relayEdges.sort((a, b) => (a.data('segmentIndex') || 0) - (b.data('segmentIndex') || 0));

                orthogonalControlPoints.set(edgeId, {
                    direction: edge.data('orthogonalDirection') || 'auto',
                    relayNodes: relayNodes,
                    relayEdges: relayEdges,
                    sourceId: edge.data('originalSource') || edge.data('source'),
                    targetId: edge.data('originalTarget') || edge.data('target')
                });

                // 隱藏原始邊
                edge.style('opacity', 0);
                edge.data('orthogonalEnabled', true);

                // 最後一段加箭頭
                if (relayEdges.length > 0) {
                    const lastSeg = relayEdges[relayEdges.length - 1];
                    lastSeg.style({
                        'target-arrow-shape': 'triangle',
                        'target-arrow-color': '#95a5a6'
                    });
                }
            });

            // === Phase 2: 重建黃點 Map ===
            const yellowByEdge = new Map();
            cy.nodes('[type="relay"][yellowControl]').forEach(node => {
                const pid = node.data('parentEdge');
                if (!pid) return;
                if (!yellowByEdge.has(pid)) yellowByEdge.set(pid, []);
                yellowByEdge.get(pid).push(node);
            });

            yellowByEdge.forEach((points, edgeId) => {
                yellowControlPoints.set(edgeId, points);
                const edge = cy.getElementById(edgeId);
                if (edge.length === 0) return;

                // 移除舊的 relay 線段，由 rebuildEdgeWithRelays 重建
                cy.edges(`[edgeType="relay"][parentEdge="${edgeId}"]`).remove();
                if (!edge.data('originalSource')) {
                    edge.data('originalSource', edge.data('source'));
                    edge.data('originalTarget', edge.data('target'));
                }
                rebuildEdgeWithRelays(edge);
            });

            // === Phase 3: 重建 Taxi Map ===
            cy.nodes('[type="relay"][taxiControl]').forEach(node => {
                const pid = node.data('parentEdge');
                if (!pid) return;
                if (!taxiControlPoints.has(pid)) {
                    taxiControlPoints.set(pid, []);
                }
                taxiControlPoints.get(pid).push(node);
            });

            taxiControlPoints.forEach((points, edgeId) => {
                // 已被 orthogonal 或 yellow 處理的跳過
                if (orthogonalControlPoints.has(edgeId)) return;
                if (yellowControlPoints.has(edgeId)) return;

                const edge = cy.getElementById(edgeId);
                if (edge.length === 0) return;
                cy.edges(`[edgeType="relay"][parentEdge="${edgeId}"]`).remove();
                if (!edge.data('originalSource')) {
                    edge.data('originalSource', edge.data('source'));
                    edge.data('originalTarget', edge.data('target'));
                }
                rebuildEdgeWithRelays(edge);
            });

            // === Phase 4: 處理無特殊標記的通用 relay 節點 ===
            const handledEdges = new Set([
                ...orthogonalControlPoints.keys(),
                ...yellowControlPoints.keys(),
                ...taxiControlPoints.keys()
            ]);

            const genericRelayEdgeIds = new Set();
            cy.nodes('[type="relay"]').forEach(node => {
                if (node.data('orthogonalControl') || node.data('yellowControl') || node.data('taxiControl')) return;
                const pid = node.data('parentEdge');
                if (pid && !handledEdges.has(pid)) {
                    genericRelayEdgeIds.add(pid);
                }
            });

            genericRelayEdgeIds.forEach(edgeId => {
                const edge = cy.getElementById(edgeId);
                if (edge.length === 0) return;
                cy.edges(`[edgeType="relay"][parentEdge="${edgeId}"]`).remove();
                if (!edge.data('originalSource')) {
                    edge.data('originalSource', edge.data('source'));
                    edge.data('originalTarget', edge.data('target'));
                }
                rebuildEdgeWithRelays(edge);
            });

            console.log(`🔄 rebuildControlPointMaps: orthogonal=${orthogonalControlPoints.size}, yellow=${yellowControlPoints.size}, taxi=${taxiControlPoints.size}, generic=${genericRelayEdgeIds.size}`);
        }

        // 從已保存的 relay 節點重建正交折線（用於 loadWorkflow）
        // 與 rebuildControlPointMaps 的差異：此函式會「創建」segment edges，而非從畫布掃描
        function rebuildOrthogonalFromSaved(edge) {
            const edgeId = edge.id();
            const source = cy.getElementById(edge.data('originalSource') || edge.data('source'));
            const target = cy.getElementById(edge.data('originalTarget') || edge.data('target'));

            if (source.length === 0 || target.length === 0) {
                console.warn(`rebuildOrthogonalFromSaved: 找不到源/目標節點, edgeId=${edgeId}`);
                return;
            }

            // 取得正交 relay 節點，按 pointIndex 排序
            const relayNodes = [];
            cy.nodes(`[type="relay"][orthogonalControl][parentEdge="${edgeId}"]`).forEach(n => {
                relayNodes.push(n);
            });
            relayNodes.sort((a, b) => (a.data('pointIndex') || 0) - (b.data('pointIndex') || 0));

            if (relayNodes.length !== 4) {
                console.warn(`rebuildOrthogonalFromSaved: 預期 4 個控制點，實際 ${relayNodes.length}，edgeId=${edgeId}，fallback 到通用重建`);
                rebuildEdgeWithRelays(edge);
                return;
            }

            // 隱藏原始邊
            edge.style('opacity', 0);
            edge.data('orthogonalEnabled', true);

            const direction = edge.data('orthogonalDirection') || 'auto';

            // 線段樣式
            const edgeStyle = {
                'width': 1,
                'line-color': '#95a5a6',
                'line-style': 'solid',
                'curve-style': 'straight',
                'target-arrow-shape': 'none'
            };

            // 創建 5 條線段：source → r1 → r2 → r3 → r4 → target
            const relayEdges = [];
            const segPoints = [source, ...relayNodes, target];

            for (let i = 0; i < 5; i++) {
                const seg = cy.add({
                    data: {
                        id: `orthogonal-${edgeId}-seg-${i + 1}`,
                        source: segPoints[i].id(),
                        target: segPoints[i + 1].id(),
                        edgeType: 'orthogonal-segment',
                        parentEdge: edgeId,
                        segmentIndex: i,
                        label: ''
                    }
                });
                if (i === 4) {
                    seg.style({
                        ...edgeStyle,
                        'target-arrow-shape': 'triangle',
                        'target-arrow-color': '#95a5a6'
                    });
                } else {
                    seg.style(edgeStyle);
                }
                relayEdges.push(seg);
            }

            // 填入 Map
            orthogonalControlPoints.set(edgeId, {
                direction: direction,
                relayNodes: relayNodes,
                relayEdges: relayEdges,
                sourceId: source.id(),
                targetId: target.id()
            });

            console.log(`✅ rebuildOrthogonalFromSaved: ${edgeId}, direction=${direction}`);
        }

        // 刪除節點前，清理該節點所有連接邊的控制點系統
        // Cytoscape 刪除節點只移除直接連接的邊，不清理 relay 節點和中間段
        function cleanupNodeEdgeControlSystems(node) {
            const edgeIdsToClean = new Set();
            node.connectedEdges().forEach(edge => {
                const parentEdgeId = edge.data('parentEdge');
                if (parentEdgeId) {
                    // 這是 relay/orthogonal segment，清理其 parent edge
                    edgeIdsToClean.add(parentEdgeId);
                } else {
                    edgeIdsToClean.add(edge.id());
                }
            });

            edgeIdsToClean.forEach(edgeId => {
                removeOrthogonalControlPoints(edgeId);
                removeYellowControlPoints(edgeId);
                removeTaxiControlPoints(edgeId);
                // 移除所有 relay 子元素
                cy.nodes(`[type="relay"][parentEdge="${edgeId}"]`).remove();
                cy.edges(`[parentEdge="${edgeId}"]`).remove();
            });
        }
        // ==================== Undo 系統結束 ====================
