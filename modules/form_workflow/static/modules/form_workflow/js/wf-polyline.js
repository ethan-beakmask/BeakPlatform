/**
 * wf-polyline.js -- 直角折線控制點、正交折線、黃點折線系統
 * 從 workflow-main.js 拆分
 */

        // ==================== 直角折線控制點系統 ====================

        // 為直角折線創建中繼點（使用現有的中繼點系統）
        function createTaxiControlPoints(edge) {
            // 只為 taxi 類型的線段創建控制點
            if (edge.style('curve-style') !== 'taxi') {
                return;
            }

            // 移除舊的控制點
            removeTaxiControlPoints(edge.id());

            // 改為直線樣式（中繼點系統需要）
            edge.style('curve-style', 'straight');

            const source = cy.getElementById(edge.data('originalSource') || edge.data('source'));
            const target = cy.getElementById(edge.data('originalTarget') || edge.data('target'));

            if (source.length === 0 || target.length === 0) {
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            // 創建兩個轉角中繼點（形成直角路徑）
            const midY = (sourcePos.y + targetPos.y) / 2;

            relayCounter++;
            const relay1Id = `taxi-relay-${edge.id()}_${relayCounter}`;
            const relay1 = cy.add({
                group: 'nodes',
                data: {
                    id: relay1Id,
                    type: 'relay',
                    parentEdge: edge.id(),
                    taxiControl: true,  // 標記為直角折線控制點
                    isVerticalLine: false  // 這個點在水平線上，只能垂直移動
                },
                position: { x: sourcePos.x, y: midY }
            });

            relayCounter++;
            const relay2Id = `taxi-relay-${edge.id()}_${relayCounter}`;
            const relay2 = cy.add({
                group: 'nodes',
                data: {
                    id: relay2Id,
                    type: 'relay',
                    parentEdge: edge.id(),
                    taxiControl: true,
                    isVerticalLine: false  // 這個點在水平線上，只能垂直移動
                },
                position: { x: targetPos.x, y: midY }
            });

            // 保存原始線段資訊
            edge.data('originalSource', source.id());
            edge.data('originalTarget', target.id());

            // 重建線段路徑
            rebuildEdgeWithRelays(edge);

            taxiControlPoints.set(edge.id(), [relay1, relay2]);
            return [relay1, relay2];
        }

        // 移除直角折線控制點
        function removeTaxiControlPoints(edgeId) {
            const controls = taxiControlPoints.get(edgeId);
            if (controls) {
                // 刪除中繼點及其相關線段
                controls.forEach(ctrl => {
                    deleteRelayPoint(ctrl.id());
                });
                taxiControlPoints.delete(edgeId);
            }
        }

        // 移除所有 taxi 控制點
        function removeAllTaxiControlPoints() {
            taxiControlPoints.forEach((controls, edgeId) => {
                controls.forEach(ctrl => ctrl.remove());
            });
            taxiControlPoints.clear();
        }

        // ==================== 正交折線系統 ====================
        // 正交折線：只有水平和垂直線段，拖動線段時保持約束

        // 創建正交折線控制點（4點版本：5段線）
        function createOrthogonalControlPoints(edge) {
            // 移除舊的控制點
            removeOrthogonalControlPoints(edge.id());

            const source = cy.getElementById(edge.data('originalSource') || edge.data('source'));
            const target = cy.getElementById(edge.data('originalTarget') || edge.data('target'));

            if (source.length === 0 || target.length === 0) {
                console.warn('正交折線：找不到源節點或目標節點');
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            const dx = targetPos.x - sourcePos.x;
            const dy = targetPos.y - sourcePos.y;

            // 取得起始方向設定
            const directionSelect = document.getElementById('orthogonal-direction');
            let direction = directionSelect ? directionSelect.value : 'auto';

            // 自動判斷：根據距離決定
            if (direction === 'auto') {
                direction = Math.abs(dx) >= Math.abs(dy) ? 'horizontal' : 'vertical';
            }

            // 節點尺寸和邊距（比照黃色控制點的設定）
            const nodeSize = 50;
            const offset = nodeSize / 2 + 10;  // 離開 node 邊緣 10px = 35

            // 計算 4 個控制點位置
            let relayPositions = [];

            if (direction === 'horizontal') {
                // 水平優先：H-V-H-V-H（5段線）
                // source ─ r1 ─ r2 ─ r3 ─ r4 ─ target
                //           │         │
                //           └─────────┘
                const exitX1 = sourcePos.x + offset;
                const exitX2 = targetPos.x - offset;
                const midY = (sourcePos.y + targetPos.y) / 2;

                relayPositions = [
                    { x: exitX1, y: sourcePos.y },   // relay1: 靠近 source，水平出去
                    { x: exitX1, y: midY },          // relay2: 第一個轉角下方
                    { x: exitX2, y: midY },          // relay3: 第二個轉角下方
                    { x: exitX2, y: targetPos.y }    // relay4: 靠近 target，水平進入
                ];
            } else {
                // 垂直優先：V-H-V-H-V（5段線）
                // source
                //    │
                //   r1 ─── r2
                //          │
                //   r3 ─── r4
                //          │
                //       target
                const exitY1 = sourcePos.y + offset;
                const exitY2 = targetPos.y - offset;
                const midX = (sourcePos.x + targetPos.x) / 2;

                relayPositions = [
                    { x: sourcePos.x, y: exitY1 },   // relay1: 靠近 source，垂直出去
                    { x: midX, y: exitY1 },          // relay2: 第一個轉角右方
                    { x: midX, y: exitY2 },          // relay3: 第二個轉角右方
                    { x: targetPos.x, y: exitY2 }    // relay4: 靠近 target，垂直進入
                ];
            }

            // 隱藏原始邊
            edge.style('opacity', 0);

            // 創建中繼節點和線段
            const relayNodes = [];
            const relayEdges = [];

            // 創建 4 個控制點（統一灰色 6x6）
            for (let i = 0; i < 4; i++) {
                const relayId = `orthogonal-${edge.id()}-relay-${i + 1}`;
                const relay = cy.add({
                    data: {
                        id: relayId,
                        type: 'relay',
                        orthogonalControl: true,
                        parentEdge: edge.id(),
                        pointIndex: i + 1  // 1-based index
                    },
                    position: relayPositions[i]
                });
                relay.style({
                    'width': 6,
                    'height': 6,
                    'background-color': '#95a5a6',
                    'shape': 'ellipse',
                    'border-width': 1,
                    'border-color': '#7f8c8d',
                    'label': '',
                    'z-index': 999
                });
                relayNodes.push(relay);
            }

            // 線段樣式（使用預設灰色細線）
            const edgeStyle = {
                'width': 1,
                'line-color': '#95a5a6',
                'line-style': 'solid',
                'curve-style': 'straight',
                'target-arrow-shape': 'none'
            };

            // 創建 5 條線段
            // 線段1：source → relay1
            const seg1 = cy.add({
                data: {
                    id: `orthogonal-${edge.id()}-seg-1`,
                    source: source.id(),
                    target: relayNodes[0].id(),
                    edgeType: 'orthogonal-segment',
                    parentEdge: edge.id(),
                    segmentIndex: 0,
                    label: ''
                }
            });
            seg1.style(edgeStyle);
            relayEdges.push(seg1);

            // 線段2：relay1 → relay2
            const seg2 = cy.add({
                data: {
                    id: `orthogonal-${edge.id()}-seg-2`,
                    source: relayNodes[0].id(),
                    target: relayNodes[1].id(),
                    edgeType: 'orthogonal-segment',
                    parentEdge: edge.id(),
                    segmentIndex: 1,
                    label: ''
                }
            });
            seg2.style(edgeStyle);
            relayEdges.push(seg2);

            // 線段3：relay2 → relay3
            const seg3 = cy.add({
                data: {
                    id: `orthogonal-${edge.id()}-seg-3`,
                    source: relayNodes[1].id(),
                    target: relayNodes[2].id(),
                    edgeType: 'orthogonal-segment',
                    parentEdge: edge.id(),
                    segmentIndex: 2,
                    label: ''
                }
            });
            seg3.style(edgeStyle);
            relayEdges.push(seg3);

            // 線段4：relay3 → relay4
            const seg4 = cy.add({
                data: {
                    id: `orthogonal-${edge.id()}-seg-4`,
                    source: relayNodes[2].id(),
                    target: relayNodes[3].id(),
                    edgeType: 'orthogonal-segment',
                    parentEdge: edge.id(),
                    segmentIndex: 3,
                    label: ''
                }
            });
            seg4.style(edgeStyle);
            relayEdges.push(seg4);

            // 線段5：relay4 → target（帶箭頭）
            const seg5 = cy.add({
                data: {
                    id: `orthogonal-${edge.id()}-seg-5`,
                    source: relayNodes[3].id(),
                    target: target.id(),
                    edgeType: 'orthogonal-segment',
                    parentEdge: edge.id(),
                    segmentIndex: 4,
                    label: ''
                }
            });
            seg5.style({
                ...edgeStyle,
                'target-arrow-shape': 'triangle',
                'target-arrow-color': '#95a5a6'
            });
            relayEdges.push(seg5);

            // 儲存控制點資訊
            orthogonalControlPoints.set(edge.id(), {
                direction: direction,
                relayNodes: relayNodes,
                relayEdges: relayEdges,
                sourceId: source.id(),
                targetId: target.id()
            });

            // 標記原始邊
            edge.data('orthogonalEnabled', true);

            console.log(`✅ 正交折線已創建（4點版）: ${edge.id()}, 方向: ${direction}`);
        }

        // 移除正交折線控制點
        function removeOrthogonalControlPoints(edgeId) {
            const data = orthogonalControlPoints.get(edgeId);
            if (data) {
                // 移除線段
                data.relayEdges.forEach(e => {
                    if (e && e.length > 0) e.remove();
                });
                // 移除中繼節點
                data.relayNodes.forEach(n => {
                    if (n && n.length > 0) n.remove();
                });
                orthogonalControlPoints.delete(edgeId);

                // 恢復原始邊的可見性並重置樣式為預設值
                const edge = cy.getElementById(edgeId);
                if (edge.length > 0) {
                    edge.style({
                        'opacity': 1,
                        'display': 'element',
                        'curve-style': 'straight',
                        'width': 1,
                        'line-color': '#95a5a6',
                        'line-style': 'solid',
                        'target-arrow-shape': 'triangle',
                        'target-arrow-color': '#95a5a6'
                    });
                    edge.data('orthogonalEnabled', false);
                }

                console.log(`🗑️ 正交折線已移除: ${edgeId}`);
            }
        }

        // 找反向邊輔助函數
        function findReverseEdge(edge) {
            const sourceId = edge.source().id();
            const targetId = edge.target().id();
            const reverseEdges = cy.edges().filter(e => {
                return e.source().id() === targetId &&
                       e.target().id() === sourceId &&
                       e.id() !== edge.id() &&
                       (!e.data('edgeType') || e.data('edgeType') !== 'relay');
            });
            return reverseEdges.length > 0 ? reverseEdges[0] : null;
        }

        // 更新正交折線方向
        function updateOrthogonalDirection() {
            if (!currentSelectedEdge) return;
            // 重新創建正交折線以應用新方向
            if (currentSelectedEdge.data('orthogonalEnabled')) {
                createOrthogonalControlPoints(currentSelectedEdge);
                updateStatus('✓ 正交折線方向已更新');
            }
        }

        // 當節點移動時更新正交折線控制點（4點版本，保持正交約束）
        function updateOrthogonalControlPointsOnNodeMove(edgeId, movedNodeId) {
            const data = orthogonalControlPoints.get(edgeId);
            if (!data) return;

            const source = cy.getElementById(data.sourceId);
            const target = cy.getElementById(data.targetId);
            if (source.length === 0 || target.length === 0) return;

            const sourcePos = source.position();
            const targetPos = target.position();
            const relays = data.relayNodes;

            if (data.direction === 'horizontal') {
                // 水平優先：H-V-H-V-H
                // relay1 和 relay4 的 Y 分別跟隨 source 和 target
                if (movedNodeId === data.sourceId) {
                    // source 移動了，更新 relay1 的 Y（保持 X 不變）
                    relays[0].position({ x: relays[0].position().x, y: sourcePos.y });
                } else if (movedNodeId === data.targetId) {
                    // target 移動了，更新 relay4 的 Y（保持 X 不變）
                    relays[3].position({ x: relays[3].position().x, y: targetPos.y });
                }
            } else {
                // 垂直優先：V-H-V-H-V
                // relay1 和 relay4 的 X 分別跟隨 source 和 target
                if (movedNodeId === data.sourceId) {
                    // source 移動了，更新 relay1 的 X（保持 Y 不變）
                    relays[0].position({ x: sourcePos.x, y: relays[0].position().y });
                } else if (movedNodeId === data.targetId) {
                    // target 移動了，更新 relay4 的 X（保持 Y 不變）
                    relays[3].position({ x: targetPos.x, y: relays[3].position().y });
                }
            }
        }

        // 計算點到線段的距離（用於檢測點擊了哪條線段）
        function pointToSegmentDistance(px, py, x1, y1, x2, y2) {
            const dx = x2 - x1;
            const dy = y2 - y1;
            const lengthSq = dx * dx + dy * dy;

            if (lengthSq === 0) return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);

            let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
            t = Math.max(0, Math.min(1, t));

            const nearestX = x1 + t * dx;
            const nearestY = y1 + t * dy;

            return Math.sqrt((px - nearestX) ** 2 + (py - nearestY) ** 2);
        }

        // 檢測點擊了正交折線的哪個線段
        function detectOrthogonalSegmentClick(edgeId, clickX, clickY) {
            const data = orthogonalControlPoints.get(edgeId);
            if (!data) return null;

            const threshold = 15;  // 點擊檢測閾值（像素）
            let minDist = Infinity;
            let clickedSegment = null;

            // 獲取當前節點位置
            const source = cy.getElementById(data.sourceId);
            const target = cy.getElementById(data.targetId);
            if (source.length === 0 || target.length === 0) return null;

            // 更新端點位置
            const points = [
                source.position(),
                data.relayNodes[0].position(),
                data.relayNodes[1].position(),
                target.position()
            ];

            // 檢測每個線段
            for (let i = 0; i < 3; i++) {
                const dist = pointToSegmentDistance(
                    clickX, clickY,
                    points[i].x, points[i].y,
                    points[i + 1].x, points[i + 1].y
                );

                if (dist < threshold && dist < minDist) {
                    minDist = dist;
                    // 判斷線段是水平還是垂直
                    const isHorizontal = Math.abs(points[i].y - points[i + 1].y) < 5;
                    clickedSegment = {
                        segmentIndex: i,
                        isHorizontal: isHorizontal,
                        p1: points[i],
                        p2: points[i + 1]
                    };
                }
            }

            return clickedSegment;
        }

        // 處理正交折線控制點拖動（4點版本，保持正交約束）
        function handleOrthogonalControlDrag(node) {
            const parentEdgeId = node.data('parentEdge');
            const pointIndex = node.data('pointIndex');  // 1, 2, 3, 4
            const data = orthogonalControlPoints.get(parentEdgeId);

            if (!data) return;

            const currentPos = node.position();
            const relays = data.relayNodes;

            // 獲取源節點和目標節點位置
            const source = cy.getElementById(data.sourceId);
            const target = cy.getElementById(data.targetId);
            if (source.length === 0 || target.length === 0) return;

            const sourcePos = source.position();
            const targetPos = target.position();

            if (data.direction === 'horizontal') {
                // 水平優先：H-V-H-V-H
                // relay1, relay2 靠近 source 側
                // relay3, relay4 靠近 target 側
                switch (pointIndex) {
                    case 1:  // relay1：只能左右移動，Y 跟隨 source
                        node.position({ x: currentPos.x, y: sourcePos.y });
                        relays[1].position({ x: currentPos.x, y: relays[1].position().y });
                        break;
                    case 2:  // relay2：只能上下移動，X 跟隨 relay1
                        node.position({ x: relays[0].position().x, y: currentPos.y });
                        relays[2].position({ x: relays[2].position().x, y: currentPos.y });
                        break;
                    case 3:  // relay3：只能上下移動，X 跟隨 relay4
                        node.position({ x: relays[3].position().x, y: currentPos.y });
                        relays[1].position({ x: relays[1].position().x, y: currentPos.y });
                        break;
                    case 4:  // relay4：只能左右移動，Y 跟隨 target
                        node.position({ x: currentPos.x, y: targetPos.y });
                        relays[2].position({ x: currentPos.x, y: relays[2].position().y });
                        break;
                }
            } else {
                // 垂直優先：V-H-V-H-V
                switch (pointIndex) {
                    case 1:  // relay1：只能上下移動，X 跟隨 source
                        node.position({ x: sourcePos.x, y: currentPos.y });
                        relays[1].position({ x: relays[1].position().x, y: currentPos.y });
                        break;
                    case 2:  // relay2：只能左右移動，Y 跟隨 relay1
                        node.position({ x: currentPos.x, y: relays[0].position().y });
                        relays[2].position({ x: currentPos.x, y: relays[2].position().y });
                        break;
                    case 3:  // relay3：只能左右移動，Y 跟隨 relay4
                        node.position({ x: currentPos.x, y: relays[3].position().y });
                        relays[1].position({ x: currentPos.x, y: relays[1].position().y });
                        break;
                    case 4:  // relay4：只能上下移動，X 跟隨 target
                        node.position({ x: targetPos.x, y: currentPos.y });
                        relays[2].position({ x: relays[2].position().x, y: currentPos.y });
                        break;
                }
            }
        }

        // 正交折線線段拖動狀態
        let orthogonalSegmentDrag = null;

        // 初始化正交折線線段拖動事件（4點版本：5條線段）
        function initOrthogonalSegmentDrag() {
            // 監聽正交折線線段的 mousedown
            cy.on('mousedown', 'edge[edgeType="orthogonal-segment"]', function(evt) {
                const edge = evt.target;
                const parentEdgeId = edge.data('parentEdge');
                const segmentIndex = edge.data('segmentIndex');  // 0-4
                const data = orthogonalControlPoints.get(parentEdgeId);

                if (!data) return;

                const mousePos = evt.position;
                const relays = data.relayNodes;

                // 判斷這條線段是水平還是垂直
                let isHorizontal;
                let p1, p2;

                if (segmentIndex === 0) {
                    p1 = cy.getElementById(data.sourceId).position();
                    p2 = relays[0].position();
                } else if (segmentIndex === 1) {
                    p1 = relays[0].position();
                    p2 = relays[1].position();
                } else if (segmentIndex === 2) {
                    p1 = relays[1].position();
                    p2 = relays[2].position();
                } else if (segmentIndex === 3) {
                    p1 = relays[2].position();
                    p2 = relays[3].position();
                } else {
                    p1 = relays[3].position();
                    p2 = cy.getElementById(data.targetId).position();
                }

                isHorizontal = Math.abs(p1.y - p2.y) < 5;

                orthogonalSegmentDrag = {
                    parentEdgeId: parentEdgeId,
                    segmentIndex: segmentIndex,
                    isHorizontal: isHorizontal,
                    startMouseX: mousePos.x,
                    startMouseY: mousePos.y,
                    data: data,
                    startRelays: relays.map(r => ({ ...r.position() }))
                };

                if (isHorizontal) {
                    updateStatus('🔄 拖動水平線段（只能上下移動）');
                } else {
                    updateStatus('🔄 拖動垂直線段（只能左右移動）');
                }

                evt.preventDefault();
                evt.stopPropagation();
            });

            // 監聽畫布的 mousemove
            cy.on('mousemove', function(evt) {
                if (!orthogonalSegmentDrag) return;

                const mousePos = evt.position;
                const drag = orthogonalSegmentDrag;
                const deltaX = mousePos.x - drag.startMouseX;
                const deltaY = mousePos.y - drag.startMouseY;
                const relays = drag.data.relayNodes;
                const startRelays = drag.startRelays;
                const segIdx = drag.segmentIndex;

                // 根據線段類型和方向移動相關控制點
                if (drag.data.direction === 'horizontal') {
                    // 水平優先：H-V-H-V-H
                    // 線段 0: source→r1 (H) - 不可拖
                    // 線段 1: r1→r2 (V) - 拖動時移動 r1, r2 的 X
                    // 線段 2: r2→r3 (H) - 拖動時移動 r2, r3 的 Y
                    // 線段 3: r3→r4 (V) - 拖動時移動 r3, r4 的 X
                    // 線段 4: r4→target (H) - 不可拖
                    if (segIdx === 1) {
                        // 垂直線段：左右移動 relay1, relay2
                        relays[0].position({ x: startRelays[0].x + deltaX, y: startRelays[0].y });
                        relays[1].position({ x: startRelays[1].x + deltaX, y: startRelays[1].y });
                    } else if (segIdx === 2) {
                        // 水平線段：上下移動 relay2, relay3
                        relays[1].position({ x: startRelays[1].x, y: startRelays[1].y + deltaY });
                        relays[2].position({ x: startRelays[2].x, y: startRelays[2].y + deltaY });
                    } else if (segIdx === 3) {
                        // 垂直線段：左右移動 relay3, relay4
                        relays[2].position({ x: startRelays[2].x + deltaX, y: startRelays[2].y });
                        relays[3].position({ x: startRelays[3].x + deltaX, y: startRelays[3].y });
                    }
                } else {
                    // 垂直優先：V-H-V-H-V
                    // 線段 0: source→r1 (V) - 不可拖
                    // 線段 1: r1→r2 (H) - 拖動時移動 r1, r2 的 Y
                    // 線段 2: r2→r3 (V) - 拖動時移動 r2, r3 的 X
                    // 線段 3: r3→r4 (H) - 拖動時移動 r3, r4 的 Y
                    // 線段 4: r4→target (V) - 不可拖
                    if (segIdx === 1) {
                        // 水平線段：上下移動 relay1, relay2
                        relays[0].position({ x: startRelays[0].x, y: startRelays[0].y + deltaY });
                        relays[1].position({ x: startRelays[1].x, y: startRelays[1].y + deltaY });
                    } else if (segIdx === 2) {
                        // 垂直線段：左右移動 relay2, relay3
                        relays[1].position({ x: startRelays[1].x + deltaX, y: startRelays[1].y });
                        relays[2].position({ x: startRelays[2].x + deltaX, y: startRelays[2].y });
                    } else if (segIdx === 3) {
                        // 水平線段：上下移動 relay3, relay4
                        relays[2].position({ x: startRelays[2].x, y: startRelays[2].y + deltaY });
                        relays[3].position({ x: startRelays[3].x, y: startRelays[3].y + deltaY });
                    }
                }
            });

            // 監聽畫布的 mouseup
            cy.on('mouseup', function(evt) {
                if (orthogonalSegmentDrag) {
                    updateStatus('✓ 線段位置已更新');
                    orthogonalSegmentDrag = null;
                }
            });
        }

        // ==================== 黃點折線系統 ====================
        // 黃點控制點集合（每條線有4個黃點）
        const yellowControlPoints = new Map();

        // 創建黃點折線系統（4個黃點，保持水平垂直）
        function createYellowControlPoints(edge) {
            // 移除舊的控制點
            removeYellowControlPoints(edge.id());

            // 重設為預設樣式
            edge.style({
                'curve-style': 'straight',
                'width': 1,
                'line-color': '#95a5a6',
                'line-style': 'solid',
                'target-arrow-shape': 'triangle',
                'target-arrow-color': '#95a5a6'
            });

            const source = cy.getElementById(edge.data('originalSource') || edge.data('source'));
            const target = cy.getElementById(edge.data('originalTarget') || edge.data('target'));

            if (source.length === 0 || target.length === 0) {
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            // 計算 node 的大小（假設是正方形，50x50）
            const nodeSize = 50;
            const offset = nodeSize / 2 + 10; // 離開 node 邊緣 10px

            // 決定出線方向（從 node 的哪一邊出去）
            // 簡單版本：根據目標方向決定
            const dx = targetPos.x - sourcePos.x;
            const dy = targetPos.y - sourcePos.y;

            // 近星點1：從起點 node 延伸出來
            let nearStar1Pos;
            if (Math.abs(dx) > Math.abs(dy)) {
                // 主要是水平方向
                nearStar1Pos = {
                    x: sourcePos.x + (dx > 0 ? offset : -offset),
                    y: sourcePos.y
                };
            } else {
                // 主要是垂直方向
                nearStar1Pos = {
                    x: sourcePos.x,
                    y: sourcePos.y + (dy > 0 ? offset : -offset)
                };
            }

            // 近星點2：從終點 node 延伸出來
            let nearStar2Pos;
            if (Math.abs(dx) > Math.abs(dy)) {
                // 主要是水平方向
                nearStar2Pos = {
                    x: targetPos.x - (dx > 0 ? offset : -offset),
                    y: targetPos.y
                };
            } else {
                // 主要是垂直方向
                nearStar2Pos = {
                    x: targetPos.x,
                    y: targetPos.y - (dy > 0 ? offset : -offset)
                };
            }

            // 折線點1和折線點2：中間的兩個轉角
            const midY = (nearStar1Pos.y + nearStar2Pos.y) / 2;
            const cornerPoint1Pos = { x: nearStar1Pos.x, y: midY };
            const cornerPoint2Pos = { x: nearStar2Pos.x, y: midY };

            // 創建4個黃點
            const yellowPoints = [];

            // 近星點1
            relayCounter++;
            const nearStar1 = cy.add({
                group: 'nodes',
                data: {
                    id: `yellow-nearstar1-${edge.id()}_${relayCounter}`,
                    type: 'relay',
                    parentEdge: edge.id(),
                    yellowControl: true,
                    pointType: 'nearStar'
                },
                position: nearStar1Pos
            });
            yellowPoints.push(nearStar1);

            // 折線點1
            relayCounter++;
            const corner1 = cy.add({
                group: 'nodes',
                data: {
                    id: `yellow-corner1-${edge.id()}_${relayCounter}`,
                    type: 'relay',
                    parentEdge: edge.id(),
                    yellowControl: true,
                    pointType: 'corner'
                },
                position: cornerPoint1Pos
            });
            yellowPoints.push(corner1);

            // 折線點2
            relayCounter++;
            const corner2 = cy.add({
                group: 'nodes',
                data: {
                    id: `yellow-corner2-${edge.id()}_${relayCounter}`,
                    type: 'relay',
                    parentEdge: edge.id(),
                    yellowControl: true,
                    pointType: 'corner'
                },
                position: cornerPoint2Pos
            });
            yellowPoints.push(corner2);

            // 近星點2
            relayCounter++;
            const nearStar2 = cy.add({
                group: 'nodes',
                data: {
                    id: `yellow-nearstar2-${edge.id()}_${relayCounter}`,
                    type: 'relay',
                    parentEdge: edge.id(),
                    yellowControl: true,
                    pointType: 'nearStar'
                },
                position: nearStar2Pos
            });
            yellowPoints.push(nearStar2);

            // 保存原始線段資訊
            edge.data('originalSource', source.id());
            edge.data('originalTarget', target.id());

            // 重建線段路徑
            rebuildEdgeWithRelays(edge);

            yellowControlPoints.set(edge.id(), yellowPoints);
            return yellowPoints;
        }

        // 移除黃點控制點
        function removeYellowControlPoints(edgeId) {
            const controls = yellowControlPoints.get(edgeId);
            if (controls) {
                controls.forEach(ctrl => {
                    deleteRelayPoint(ctrl.id());
                });
                yellowControlPoints.delete(edgeId);

                // 重置邊的樣式為預設值
                const edge = cy.getElementById(edgeId);
                if (edge.length > 0) {
                    edge.style({
                        'display': 'element',
                        'curve-style': 'straight',
                        'width': 1,
                        'line-color': '#95a5a6',
                        'line-style': 'solid',
                        'target-arrow-shape': 'triangle',
                        'target-arrow-color': '#95a5a6'
                    });
                }
            }
        }

        // 更新黃點位置（當 node 移動時）
        function updateYellowControlPoints(edge) {
            const yellowPoints = yellowControlPoints.get(edge.id());
            if (!yellowPoints || yellowPoints.length !== 4) return;

            const source = cy.getElementById(edge.data('originalSource') || edge.data('source'));
            const target = cy.getElementById(edge.data('originalTarget') || edge.data('target'));

            if (source.length === 0 || target.length === 0) return;

            const sourcePos = source.position();
            const targetPos = target.position();

            // 計算 node 的大小
            const nodeSize = 50;
            const offset = nodeSize / 2 + 10;

            // 決定出線方向
            const dx = targetPos.x - sourcePos.x;
            const dy = targetPos.y - sourcePos.y;

            // 更新近星點1位置
            let nearStar1Pos;
            if (Math.abs(dx) > Math.abs(dy)) {
                nearStar1Pos = {
                    x: sourcePos.x + (dx > 0 ? offset : -offset),
                    y: sourcePos.y
                };
            } else {
                nearStar1Pos = {
                    x: sourcePos.x,
                    y: sourcePos.y + (dy > 0 ? offset : -offset)
                };
            }

            // 更新近星點2位置
            let nearStar2Pos;
            if (Math.abs(dx) > Math.abs(dy)) {
                nearStar2Pos = {
                    x: targetPos.x - (dx > 0 ? offset : -offset),
                    y: targetPos.y
                };
            } else {
                nearStar2Pos = {
                    x: targetPos.x,
                    y: targetPos.y - (dy > 0 ? offset : -offset)
                };
            }

            // 更新折線點1和折線點2位置
            const midY = (nearStar1Pos.y + nearStar2Pos.y) / 2;
            const cornerPoint1Pos = { x: nearStar1Pos.x, y: midY };
            const cornerPoint2Pos = { x: nearStar2Pos.x, y: midY };

            // 更新4個黃點的位置
            yellowPoints[0].position(nearStar1Pos);  // 近星點1
            yellowPoints[1].position(cornerPoint1Pos); // 折線點1
            yellowPoints[2].position(cornerPoint2Pos); // 折線點2
            yellowPoints[3].position(nearStar2Pos);  // 近星點2

            // 重建線段
            rebuildEdgeWithRelays(edge);
        }

        // 更新所有 taxi 線段的控制點
        function updateAllTaxiControlPoints() {
            removeAllTaxiControlPoints();
            cy.edges().forEach(edge => {
                if (edge.style('curve-style') === 'taxi' && !edge.data('edgeType')) {
                    createTaxiControlPoints(edge);
                }
            });
        }

