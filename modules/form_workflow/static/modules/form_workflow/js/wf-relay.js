/**
 * wf-relay.js -- 中繼點 CRUD (折線編輯)
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js, wf-cy-init.js
 */


        // 選擇線段進行多點折線編輯
        function selectEdgeForPolylineEditing(edge) {
            if (selectedEdge) {
                selectedEdge.unselect();
            }

            selectedEdge = edge;
            selectedEdge.select();

            // 檢查是否為直角折線
            const hasTaxiControls = taxiControlPoints.has(edge.id());

            if (hasTaxiControls) {
                // 顯示直角折線座標控制面板
                showTaxiCoordPanel(edge);
            } else {
                // 顯示一般線段編輯面板
                document.getElementById('nodeSettings').style.display = 'none';
                document.getElementById('edge-editing-panel').style.display = 'block';
                document.getElementById('taxi-coord-panel').style.display = 'none';
                document.getElementById('edge-control-panel').style.display = 'none';

                updateRelayPointsList();
                updateStatus(`編輯線段: ${edge.id()}`);
            }
        }

        // 新增中繼點
        function addRelayPoints() {
            if (!selectedEdge || selectedEdge.data('parentEdge')) {
                updateStatus('請先選擇一條主要線段（Shift+點擊線段）', 'warning');
                return;
            }

            // 禁止在正交折線和黃點折線上新增中繼點
            if (selectedEdge.data('orthogonalEnabled')) {
                updateStatus('正交折線不支援新增中繼點，請先切換為其他樣式', 'warning');
                return;
            }
            if (yellowControlPoints.has(selectedEdge.id())) {
                updateStatus('黃點折線不支援新增中繼點，請先切換為其他樣式', 'warning');
                return;
            }

            const count = parseInt(document.getElementById('relay-count').value);

            const source = cy.getElementById(selectedEdge.data('originalSource') || selectedEdge.data('source'));
            const target = cy.getElementById(selectedEdge.data('originalTarget') || selectedEdge.data('target'));

            if (source.length === 0 || target.length === 0) {
                updateStatus('ERROR: 找不到來源或目標節點');
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            const newRelays = [];

            for (let i = 1; i <= count; i++) {
                const ratio = i / (count + 1);
                const x = sourcePos.x + (targetPos.x - sourcePos.x) * ratio;
                const y = sourcePos.y + (targetPos.y - sourcePos.y) * ratio;

                const relayId = `relay_${selectedEdge.id()}_${++relayCounter}`;

                newRelays.push({
                    data: {
                        id: relayId,
                        type: 'relay',
                        parentEdge: selectedEdge.id()
                    },
                    position: { x: x, y: y }
                });
            }

            // 新增中繼點到圖中
            cy.batch(() => {
                newRelays.forEach(relay => {
                    cy.add(relay);
                });
            });

            // 重建線段
            rebuildEdgeWithRelays(selectedEdge);

            updateRelayPointsList();
            updateStatus(`已新增 ${count} 個中繼點`);
        }

        // 取得線段的所有中繼點
        function getRelayPointsForEdge(edgeId) {
            return cy.nodes(`[type="relay"][parentEdge="${edgeId}"]`).sort((a, b) => {
                const aId = parseInt(a.id().split('_').pop());
                const bId = parseInt(b.id().split('_').pop());
                return aId - bId;
            });
        }

        // 重建包含中繼點的線段
        function rebuildEdgeWithRelays(originalEdge) {
            const edgeId = originalEdge.id();
            const relayPoints = getRelayPointsForEdge(edgeId);

            if (relayPoints.length === 0) return;

            // 儲存原始資料
            if (!originalEdge.data('originalSource')) {
                originalEdge.data('originalSource', originalEdge.data('source'));
                originalEdge.data('originalTarget', originalEdge.data('target'));
            }

            const sourceId = originalEdge.data('originalSource');
            const targetId = originalEdge.data('originalTarget');
            const label = originalEdge.data('label');

            // 取得原始邊的樣式
            const originalArrowShape = originalEdge.style('target-arrow-shape') || 'triangle';
            const originalArrowColor = originalEdge.style('target-arrow-color') || originalEdge.style('line-color');
            const originalLineColor = originalEdge.style('line-color');
            const originalLineWidth = originalEdge.style('width');

            // 移除舊的分段線段
            cy.remove(`edge[parentEdge="${edgeId}"]`);

            // 隱藏原始線段
            originalEdge.style('display', 'none');

            // 建立新線段串
            const points = [sourceId, ...relayPoints.map(r => r.id()), targetId];
            const lastIndex = points.length - 2; // 最後一段的索引

            // 先創建所有線段
            const segmentIds = [];
            cy.batch(() => {
                for (let i = 0; i < points.length - 1; i++) {
                    const segmentId = `${edgeId}_segment_${i}`;
                    segmentIds.push({ id: segmentId, isLast: (i === lastIndex) });

                    cy.add({
                        data: {
                            id: segmentId,
                            source: points[i],
                            target: points[i + 1],
                            edgeType: 'relay',
                            parentEdge: edgeId,
                            label: (i === 0) ? label : ''
                        }
                    });
                }
            });

            // 在 batch 外設定樣式，確保正確應用
            segmentIds.forEach(({ id, isLast }) => {
                const seg = cy.getElementById(id);
                if (seg.length > 0) {
                    seg.style({
                        'line-color': originalLineColor,
                        'width': originalLineWidth,
                        'target-arrow-shape': isLast ? originalArrowShape : 'none',
                        'target-arrow-color': isLast ? originalArrowColor : originalLineColor
                    });
                }
            });
        }

        // 更新中繼點列表
        function updateRelayPointsList() {
            if (!selectedEdge) return;

            const listDiv = document.getElementById('relay-points-list');
            const relayPoints = getRelayPointsForEdge(selectedEdge.id());

            if (relayPoints.length === 0) {
                listDiv.innerHTML = '<div style="color: #333; text-align: center; padding: 10px;">無中繼點</div>';
            } else {
                listDiv.innerHTML = '';
                relayPoints.forEach((relay, index) => {
                    const item = document.createElement('div');
                    item.className = 'relay-point-item';
                    item.id = `relay-item-${relay.id()}`;
                    item.innerHTML = `
                        <span>中繼點 ${index + 1}</span>
                        <button class="btn-danger btn-small" onclick="deleteRelayPoint('${relay.id()}'); event.stopPropagation();">
                            <i class="fas fa-trash"></i>
                        </button>
                    `;
                    item.onclick = function(e) {
                        if (!e.target.classList.contains('btn-danger')) {
                            highlightRelayPoint(relay.id());
                        }
                    };
                    listDiv.appendChild(item);
                });
            }
        }

        // 高亮中繼點
        function highlightRelayPoint(relayId) {
            // 清除其他高亮
            document.querySelectorAll('.relay-point-item').forEach(item => {
                item.classList.remove('selected');
            });

            // 高亮選中項
            const item = document.getElementById(`relay-item-${relayId}`);
            if (item) {
                item.classList.add('selected');
            }

            // 選中圖中的節點
            cy.nodes().unselect();
            cy.getElementById(relayId).select();
        }

        // 刪除中繼點
        function deleteRelayPoint(relayId) {
            const relay = cy.getElementById(relayId);
            if (relay.length === 0) return;

            const parentEdgeId = relay.data('parentEdge');

            // 移除中繼點
            cy.remove(relay);

            // 重建線段
            const remainingRelays = getRelayPointsForEdge(parentEdgeId);

            // 移除所有相關線段
            cy.remove(`edge[parentEdge="${parentEdgeId}"]`);

            if (remainingRelays.length === 0) {
                // 恢復原始線段
                const originalEdge = cy.getElementById(parentEdgeId);
                originalEdge.style('display', 'element');
            } else {
                // 重建線段串
                const originalEdge = cy.getElementById(parentEdgeId);
                rebuildEdgeWithRelays(originalEdge);
            }

            updateRelayPointsList();
            updateStatus(`已刪除中繼點`);
        }

        // 清除所有中繼點
        function removeAllRelayPoints() {
            if (!selectedEdge) return;

            const edgeId = selectedEdge.id();
            const relayPoints = getRelayPointsForEdge(edgeId);

            // 移除所有中繼點和相關線段
            cy.batch(() => {
                relayPoints.forEach(relay => {
                    cy.remove(relay);
                });
                cy.remove(`edge[parentEdge="${edgeId}"]`);
            });

            // 恢復原始線段
            selectedEdge.style('display', 'element');

            updateRelayPointsList();
            updateStatus('已清除所有中繼點');
        }
