/**
 * wf-events.js -- Cytoscape 事件綁定 (bindEvents)
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js, wf-cy-init.js
 */


        // 綁定事件
        function bindEvents() {
            // 節點 mousedown 事件 - 用於區分畫線和拖動
            let undoSavedForDrag = false; // 避免拖曳期間重複存 undo

            cy.on('mousedown', 'node', function(evt) {
                const node = evt.target;

                // 忽略中繼點
                if (node.data('type') === 'relay') {
                    return;
                }

                undoSavedForDrag = false;

                // Alt 模式：標記節點以便脫離群組
                if (altPressed) {
                    nodePressedForDrag = node;
                    hasMoved = false;
                    alreadyLeftGroup = false;  // 重置標記
                }
            });

            // 節點 drag 事件 - 偵測拖動並立即脫離群組（視覺更即時）
            cy.on('drag', 'node', function(evt) {
                const node = evt.target;

                // 實際開始拖曳時才存 undo（避免單純點擊也存）
                if (!undoSavedForDrag && node.data('type') !== 'relay') {
                    pushUndoState();
                    undoSavedForDrag = true;
                }

                if (nodePressedForDrag && altPressed && nodePressedForDrag.id() === node.id()) {
                    hasMoved = true;

                    // 立即脫離群組（只執行一次）
                    if (!alreadyLeftGroup) {
                        const currentParent = node.parent();
                        if (currentParent.length > 0) {
                            node.move({ parent: null });
                            cy.style().update();
                            refreshEmptyGroupStyle(currentParent);
                            alreadyLeftGroup = true;

                            const isGroup = isGroupNode(node);
                            const nodeType = isGroup ? '群組' : '節點';
                            updateStatus(`🔓 ${nodeType}正在脫離群組 ${currentParent.data('label')}...`);
                        }
                    }
                }
            });

            // 節點點擊事件 - 支援 Shift 連續畫線模式
            cy.on('tap', 'node', function(evt) {
                const node = evt.target;

                // 忽略中繼點
                if (node.data('type') === 'relay') {
                    return;
                }

                // Shift + 點擊（未拖動）：連續畫線模式
                if (shiftPressed && !hasMoved) {
                    if (!continuousLineMode) {
                        // 開始連續畫線模式
                        continuousLineMode = true;
                        continuousLineNodes = [node];
                        node.addClass('continuous-line-highlight');
                        updateStatus('連續畫線模式：繼續點擊節點以畫線，放開 Shift 結束');
                    } else {
                        // 連續畫線中，與上一個節點連線
                        const lastNode = continuousLineNodes[continuousLineNodes.length - 1];
                        if (lastNode.id() !== node.id()) {
                            createEdge(lastNode, node);
                            continuousLineNodes.push(node);
                            node.addClass('continuous-line-highlight');
                            updateStatus(`已連接 ${continuousLineNodes.length} 個節點`);
                        } else {
                            updateStatus('不能連接到同一個節點', 'warning');
                        }
                    }
                }
                // 一般點擊：顯示資訊
                else if (!shiftPressed && !ctrlPressed) {
                    showNodeInfo(node);
                }

                // 重置拖動偵測變數
                nodePressedForDrag = null;
                hasMoved = false;
            });

            // 線段點擊事件（使用 mousedown 立即響應）
            let trackingMouseOnEdge = false;

            cy.on('mousedown', 'edge', function(evt) {
                let edge = evt.target;

                // 檢查是否為中間線段拖動（已在下方處理）
                if (edge.data('edgeType') === 'relay') {
                    const parentEdgeId = edge.data('parentEdge');
                    const controls = taxiControlPoints.get(parentEdgeId);
                    if (controls && controls.length === 2) {
                        const sourceId = edge.data('source');
                        const targetId = edge.data('target');
                        const isMiddleSegment = controls.some(c => c.id() === sourceId) &&
                                               controls.some(c => c.id() === targetId);
                        if (isMiddleSegment) {
                            return; // 中間線段拖動已在下方處理，這裡不處理
                        }
                    }
                    // 找到原始邊用於屬性控制
                    if (parentEdgeId) {
                        edge = cy.getElementById(parentEdgeId);
                        if (edge.length === 0) return;
                    }
                }

                // 如果點擊的是正交線段，找到原始邊
                if (evt.target.data('edgeType') === 'orthogonal-segment') {
                    const parentEdgeId = evt.target.data('parentEdge');
                    if (parentEdgeId) {
                        edge = cy.getElementById(parentEdgeId);
                        if (edge.length === 0) return;
                    }
                }

                // Ctrl + 點擊：編輯多點折線
                if (ctrlPressed && !edge.data('parentEdge')) {
                    selectEdgeForPolylineEditing(edge);
                }
                // 普通點擊：選取線段用於屬性控制
                else {
                    selectEdgeForPropertyControl(edge);

                    // 啟用滑鼠座標追蹤
                    trackingMouseOnEdge = true;

                    // 禁用畫布平移
                    cy.userPanningEnabled(false);

                    // 顯示初始座標
                    const pos = evt.position;
                    updateStatus(`滑鼠座標：X=${Math.round(pos.x)}, Y=${Math.round(pos.y)}`);
                }
            });

            // 滑鼠移動時更新座標
            cy.on('mousemove', function(evt) {
                if (trackingMouseOnEdge) {
                    const pos = evt.position;
                    updateStatus(`滑鼠座標：X=${Math.round(pos.x)}, Y=${Math.round(pos.y)}`);
                }
            });

            // 滑鼠放開時停止追蹤
            cy.on('mouseup', function(evt) {
                if (trackingMouseOnEdge) {
                    trackingMouseOnEdge = false;
                    // 不恢復 userPanningEnabled，保持 false
                    // 左鍵用於框選，右鍵用於平移（由自訂代碼控制）
                    updateStatus('就緒');
                }
            });

            // 保留 tap 事件作為備用
            cy.on('tap', 'edge', function(evt) {
                let edge = evt.target;

                // 如果點擊的是正交線段，找到原始邊
                if (edge.data('edgeType') === 'orthogonal-segment') {
                    const parentEdgeId = edge.data('parentEdge');
                    if (parentEdgeId) {
                        edge = cy.getElementById(parentEdgeId);
                        if (edge.length === 0) return;
                    }
                }
                // 如果點擊的是中繼線段（分段折線/直角折線），找到原始邊
                else if (edge.data('edgeType') === 'relay') {
                    const parentEdgeId = edge.data('parentEdge');
                    if (parentEdgeId) {
                        edge = cy.getElementById(parentEdgeId);
                        if (edge.length === 0) return;
                    }
                }

                // Ctrl + 點擊：編輯多點折線
                if (ctrlPressed && !edge.data('parentEdge')) {
                    selectEdgeForPolylineEditing(edge);
                }
                // 普通點擊：選取線段用於屬性控制
                else {
                    selectEdgeForPropertyControl(edge);
                }
            });

            // 中繼點點擊
            cy.on('tap', 'node[type="relay"]', function(evt) {
                const node = evt.target;
                const parentEdgeId = node.data('parentEdge');

                // 所有類型的控制點都選中原始邊顯示屬性面板
                if (parentEdgeId) {
                    const edge = cy.getElementById(parentEdgeId);
                    if (edge.length > 0) {
                        selectEdgeForPropertyControl(edge);
                    }
                }

                // 非正交折線的中繼點還需要高亮
                if (!node.data('orthogonalControl')) {
                    highlightRelayPoint(node.id());
                }
            });

            // 中繼點拖動開始
            cy.on('grab', 'node[type="relay"]', function(evt) {
                const node = evt.target;
                const parentEdgeId = node.data('parentEdge');

                if (node.data('orthogonalControl')) {
                    updateStatus('拖動正交折線控制點');
                    // 高亮相關線段
                    cy.edges(`[parentEdge="${parentEdgeId}"]`).addClass('highlighted');
                } else if (node.data('taxiControl')) {
                    updateStatus('拖動直角折線控制點 - 只能水平移動');
                    // 高亮相關線段
                    cy.edges(`[id="${parentEdgeId}"]`).addClass('highlighted');
                    cy.edges(`[parentEdge="${parentEdgeId}"]`).addClass('highlighted');
                } else {
                    updateStatus('拖動中繼點調整線段路徑');
                }
            });

            // 中繼點拖曳完成
            cy.on('dragfree', 'node[type="relay"]', function(evt) {
                const node = evt.target;
                const parentEdgeId = node.data('parentEdge');

                // 根據控制點類型顯示不同訊息
                if (node.data('orthogonalControl')) {
                    updateStatus('正交折線已更新');
                } else if (node.data('taxiControl')) {
                    node.removeData('dragStartY');
                    updateStatus('直角折線已更新');
                } else {
                    updateStatus('中繼點位置已更新');
                }

                // 移除高亮
                cy.edges().removeClass('highlighted');
            });

            // 中繼點拖動事件 - 為直角折線限制方向
            cy.on('drag', 'node[type="relay"]', function(evt) {
                const node = evt.target;

                // 如果正在拖動中間線段，不要限制藍點移動
                if (draggingMiddleSegment) {
                    return;
                }

                // 檢查是否為直角折線的控制點
                if (node.data('taxiControl')) {
                    const currentPos = node.position();
                    const parentEdge = node.data('parentEdge');

                    // 獲取拖動開始時的Y位置
                    if (!node.data('dragStartY')) {
                        node.data('dragStartY', currentPos.y);
                    }

                    const startY = node.data('dragStartY');

                    // 限制只能水平移動（保持Y不變）
                    node.position({ x: currentPos.x, y: startY });

                    // 不同步另一個轉角點，讓兩個點各自獨立移動
                }

                // 檢查是否為正交折線的控制點
                if (node.data('orthogonalControl')) {
                    handleOrthogonalControlDrag(node);
                }
            });

            // 中間線段拖動功能（使用畫布事件）
            let draggingMiddleSegment = null;
            let dragStartMouseY = 0;
            let dragStartControlsY = 0;

            // 中間線段拖動功能
            cy.on('mousedown', 'edge[edgeType="relay"]', function(evt) {
                const edge = evt.target;
                const parentEdgeId = edge.data('parentEdge');

                // 檢查是否為直角折線的中間線段
                const controls = taxiControlPoints.get(parentEdgeId);
                if (controls && controls.length === 2) {
                    // 確認這條線段連接兩個控制點
                    const sourceId = edge.data('source');
                    const targetId = edge.data('target');

                    const isMiddleSegment = controls.some(c => c.id() === sourceId) &&
                                           controls.some(c => c.id() === targetId);

                    if (isMiddleSegment) {
                        // 阻止預設的畫布拖拉行為
                        evt.preventDefault();
                        evt.stopPropagation();

                        draggingMiddleSegment = {
                            edge: edge,
                            controls: controls,
                            parentEdgeId: parentEdgeId
                        };
                        dragStartMouseY = evt.position.y;
                        dragStartMouseX = evt.position.x;
                        dragStartControlsY = controls[0].position().y;
                        dragStartControlsX = [controls[0].position().x, controls[1].position().x];

                        // 暫時禁用畫布平移
                        cy.userPanningEnabled(false);

                        updateStatus('拖動中間線段 - 可水平/垂直移動調整位置');
                    }
                }
            });

            // 記錄拖動開始時的 X 座標
            let dragStartMouseX = 0;
            let dragStartControlsX = [0, 0];

            cy.on('mousemove', function(evt) {
                if (!draggingMiddleSegment) return;

                const currentMousePos = evt.position;
                const deltaY = currentMousePos.y - dragStartMouseY;
                const deltaX = currentMousePos.x - dragStartMouseX;
                const newY = dragStartControlsY + deltaY;

                // 同時更新兩個藍點的座標
                draggingMiddleSegment.controls.forEach((ctrl, index) => {
                    const newX = dragStartControlsX[index] + deltaX;
                    ctrl.position({ x: newX, y: newY });
                });
            });

            cy.on('mouseup', function(evt) {
                if (draggingMiddleSegment) {
                    // 不恢復 userPanningEnabled，保持 false
                    // 左鍵用於框選，右鍵用於平移（由自訂代碼控制）
                    draggingMiddleSegment = null;
                    updateStatus('中間線段位置已更新');
                }
            });

            // 剪貼簿變數
            let clipboard = null;
            let isPasting = false; // 標記是否正在貼上
            let pasteCount = 0;   // 連續貼上次數（用於累計偏移）

            // 按鍵事件：Delete 刪除、Ctrl+C 複製、Ctrl+V 貼上
            document.addEventListener('keydown', function(e) {
                // 如果焦點在輸入框/文字區域,允許正常的複製貼上
                const activeElement = document.activeElement;
                const isInputField = activeElement && (
                    activeElement.tagName === 'INPUT' ||
                    activeElement.tagName === 'TEXTAREA' ||
                    activeElement.isContentEditable
                );

                // Ctrl+C 複製 (複製所有選中的元素)
                if ((e.ctrlKey || e.metaKey) && e.key === 'c' && !isInputField) {
                    const selected = cy.$(':selected');
                    if (selected.length > 0) {
                        // 過濾掉中繼點、中繼線段、Start 節點
                        let hasStartNode = false;
                        const validNodes = selected.nodes().filter(node => {
                            const nodeType = node.data('type');
                            const nodeId = node.data('id');
                            // 排除中繼點
                            if (nodeType === 'relay') return false;
                            // 排除 Start 節點
                            if (nodeId === 'node-Start' || nodeType === 'Start') {
                                hasStartNode = true;
                                return false;
                            }
                            return true;
                        });
                        const validEdges = selected.edges().filter(edge => !edge.data('edgeType') || edge.data('edgeType') !== 'relay');

                        if (validNodes.length === 0 && validEdges.length === 0) {
                            const msg = hasStartNode ? '⚠️ Start 節點不允許複製' : '無可複製的元素（中繼點和中繼線段不可單獨複製）';
                            updateStatus(msg, 'warning');
                            return;
                        }

                        // 儲存選取的元素到剪貼簿
                        clipboard = {
                            nodes: validNodes.map(node => ({
                                data: JSON.parse(JSON.stringify(node.data())),
                                position: { x: node.position('x'), y: node.position('y') },
                                classes: node.classes().filter(c => c !== 'selected') // 排除 selected class
                            })),
                            edges: validEdges.map(edge => ({
                                data: JSON.parse(JSON.stringify(edge.data())),
                                classes: edge.classes().filter(c => c !== 'selected') // 排除 selected class
                            }))
                        };

                        // 重置連續貼上計數
                        pasteCount = 0;

                        console.log('複製內容:', {
                            nodes: clipboard.nodes.map(n => ({ id: n.data.id, label: n.data.label, isGroup: n.data.isGroup, parent: n.data.parent })),
                            edges: clipboard.edges.map(e => ({ id: e.data.id, source: e.data.source, target: e.data.target }))
                        });

                        updateStatus(`已複製 ${validNodes.length} 個節點和 ${validEdges.length} 條線段`);
                        e.preventDefault();
                    }
                }

                // Ctrl+V 貼上（連續按 V 時累計偏移，避免重疊）
                if ((e.ctrlKey || e.metaKey) && e.key === 'v' && !isInputField) {
                    if (!clipboard || (clipboard.nodes.length === 0 && clipboard.edges.length === 0)) {
                        updateStatus('剪貼簿為空', 'warning');
                        return;
                    }

                    pushUndoState();
                    e.preventDefault();
                    isPasting = true; // 設定貼上標記
                    pasteCount++; // 累計貼上次數

                    const offset = 150 * pasteCount; // 每次貼上遞增偏移

                    // 先記錄原本選取的元素 ID (準備取消選取)
                    const originalSelected = cy.$(':selected').map(elem => elem.id());

                    // ID 映射表（舊ID -> 新ID）
                    const idMap = new Map();
                    const newElements = [];

                    // 先複製節點
                    clipboard.nodes.forEach(nodeData => {
                        const oldId = nodeData.data.id;
                        let newId;

                        // 根據節點類型生成新 ID
                        if (nodeData.data.isGroup) {
                            newId = `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                        } else {
                            newId = `node_${++nodeCounter}`;
                        }

                        idMap.set(oldId, newId);

                        const newNodeData = {
                            ...nodeData.data,
                            id: newId,
                            label: nodeData.data.label // 保持原標籤
                        };

                        // 如果節點有父群組,需要檢查父群組是否也被複製
                        if (newNodeData.parent) {
                            if (!idMap.has(newNodeData.parent)) {
                                // 父群組沒有被複製,移除 parent 屬性
                                delete newNodeData.parent;
                            }
                        }

                        newElements.push({
                            group: 'nodes',
                            data: newNodeData,
                            position: {
                                x: nodeData.position.x + offset,
                                y: nodeData.position.y + offset
                            },
                            classes: nodeData.classes
                        });
                    });

                    // 更新父群組引用
                    newElements.forEach(elem => {
                        if (elem.data.parent && idMap.has(elem.data.parent)) {
                            elem.data.parent = idMap.get(elem.data.parent);
                        }
                    });

                    // 再複製線段（只複製兩端節點都被複製的線段）
                    clipboard.edges.forEach(edgeData => {
                        const oldSource = edgeData.data.source;
                        const oldTarget = edgeData.data.target;

                        // 檢查兩端節點是否都被複製
                        if (idMap.has(oldSource) && idMap.has(oldTarget)) {
                            const newEdgeId = `edge_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

                            const newEdgeData = {
                                ...edgeData.data,
                                id: newEdgeId,
                                source: idMap.get(oldSource),
                                target: idMap.get(oldTarget)
                            };

                            newElements.push({
                                group: 'edges',
                                data: newEdgeData,
                                classes: edgeData.classes
                            });
                        }
                    });

                    console.log('準備貼上的元素:', {
                        pasteCount: pasteCount,
                        offset: offset,
                        nodes: newElements.filter(e => e.group === 'nodes').map(n => ({
                            id: n.data.id,
                            label: n.data.label,
                            isGroup: n.data.isGroup,
                            parent: n.data.parent,
                            position: n.position
                        })),
                        edges: newElements.filter(e => e.group === 'edges').map(e => ({
                            id: e.data.id,
                            source: e.data.source,
                            target: e.data.target
                        }))
                    });

                    // 添加新元素到圖中
                    const addedElements = cy.add(newElements);

                    // 重新套用節點圖示樣式（cy.add 不會自動套用 background-image）
                    addedElements.nodes().forEach(node => {
                        // 群組節點：恢復樣式（顏色、框線、圓角）
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
                            if (icon.startsWith('/static/') || icon.startsWith('http')) {
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

                    // 使用 setTimeout 確保選取狀態正確更新
                    setTimeout(() => {
                        // 明確取消原本選取的元素
                        originalSelected.forEach(id => {
                            const elem = cy.getElementById(id);
                            if (elem.length > 0) {
                                elem.unselect();
                            }
                        });

                        // 取消所有其他元素的選取 (保險措施)
                        cy.elements().unselect();

                        // 只選取新添加的元素
                        addedElements.select();

                        // 驗證選取狀態
                        const nowSelected = cy.$(':selected');
                        console.log('貼上後選取狀態:', {
                            total: nowSelected.length,
                            nodes: nowSelected.nodes().length,
                            edges: nowSelected.edges().length,
                            ids: nowSelected.map(e => e.id())
                        });

                        updateStatus(`已貼上 ${addedElements.nodes().length} 個節點和 ${addedElements.edges().length} 條線段 (第 ${pasteCount} 次貼上)`);

                        // 重置貼上標記
                        setTimeout(() => {
                            isPasting = false;
                        }, 100);
                    }, 10);
                }

                // Ctrl+Z 復原
                if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !isInputField) {
                    e.preventDefault();
                    undo();
                }

                if (e.key === 'Delete' && !isInputField) {
                    const selected = cy.$(':selected');
                    if (selected.length > 0) {
                        pushUndoState();
                        let deletedCount = 0;
                        let blockedCount = 0;
                        let deletedSubflow = false;

                        // 檢查是否刪除中繼點或中繼線段
                        selected.forEach(elem => {
                            if (elem.isNode() && elem.data('type') === 'relay') {
                                // 如果是正交折線控制點，禁止單獨刪除
                                if (elem.data('orthogonalControl')) {
                                    blockedCount++;
                                    return;
                                }
                                // 刪除中繼點
                                deleteRelayPoint(elem.id());
                                deletedCount++;
                            } else if (elem.isEdge() && elem.data('edgeType') === 'relay') {
                                // 禁止刪除中繼線段（折線點之間的線段）
                                blockedCount++;
                            } else if (elem.isEdge() && elem.data('edgeType') === 'orthogonal-segment') {
                                // 禁止刪除正交線段
                                blockedCount++;
                            } else {
                                // 保護 Start 節點不被刪除
                                const elemType = normalizeNodeType(elem.data('type'));
                                const elemId = elem.data('id');
                                if (elem.isNode() && (elemId === 'node-Start' || elemType === 'Start')) {
                                    blockedCount++;
                                    updateStatus('⚠️ Start 節點不允許刪除', 'warning');
                                } else if (elem.isNode() && isGroupNode(elem)) {
                                    // 刪除群組時，先清理所有子節點連接的邊控制點
                                    const children = elem.children();
                                    children.forEach(child => {
                                        const childType = child.data('type');
                                        const childId = child.data('id');
                                        if (childId === 'node-Start' || childType === 'Start') {
                                            child.move({ parent: null });
                                            updateStatus('Start 節點已自動移出群組', 'info');
                                        } else {
                                            cleanupNodeEdgeControlSystems(child);
                                        }
                                    });
                                    // 刪除群組（會連帶刪除剩餘的子節點）
                                    elem.remove();
                                    deletedCount++;
                                } else {
                                    // 檢查是否為 SUBFLOW 節點
                                    if (elem.isNode() && elemType === 'Subflow') {
                                        deletedSubflow = true;
                                    }
                                    // 刪除節點前，清理所有連接邊的控制點系統
                                    if (elem.isNode()) {
                                        cleanupNodeEdgeControlSystems(elem);
                                    }
                                    // 刪除一般元素
                                    elem.remove();
                                    deletedCount++;
                                }
                            }
                        });

                        if (deletedCount > 0) {
                            updateStatus(`已刪除 ${deletedCount} 個元素`);
                        }
                        if (blockedCount > 0) {
                            updateStatus(`無法單獨刪除正交折線或中繼線段的零件，請切換線段樣式後再刪除`);
                        }

                        // 更新線段選擇器
                        updateEdgeSelector();

                        // 如果刪除的是當前選中的線段，清空選擇
                        if (currentSelectedEdge && !cy.getElementById(currentSelectedEdge.id()).length) {
                            currentSelectedEdge = null;
                            document.getElementById('edge-selector').value = '';
                            document.getElementById('edge-info').classList.remove('show');
                        }

                        // 如果刪除了 SUBFLOW 節點，延遲 0.5 秒後重新整理流程樹系
                        if (deletedSubflow) {
                            setTimeout(() => {
                                refreshFlowTree();
                            }, 500);
                        }
                    }
                }
                // ESC 取消連線模式
                if (e.key === 'Escape' && connectingSourceNode) {
                    if (!globalNodeBorder) {
                        connectingSourceNode.addClass('no-border');
                    }
                    connectingSourceNode = null;
                    updateStatus('已取消連線');
                }
            });

            // 鷹眼更新事件
            cy.on('pan zoom', function() {
                updateMinimap();
                updateZoomDisplay();
                drawGridBackground(); // 重新繪製網格
            });

            cy.on('add remove', function() {
                updateMinimap();
            });

            cy.on('position', function() {
                updateMinimap();
            });

            // Node 移動後更新黃點位置和正交折線位置
            cy.on('position', 'node[type!="relay"]', function(evt) {
                const node = evt.target;

                // 找到所有連接到這個 node 的邊
                const connectedEdges = node.connectedEdges();

                connectedEdges.forEach(edge => {
                    // 檢查是否為黃點折線
                    if (yellowControlPoints.has(edge.id())) {
                        // 重新計算並更新黃點位置
                        updateYellowControlPoints(edge);
                    }

                    // 檢查是否為正交折線
                    if (orthogonalControlPoints.has(edge.id())) {
                        // 更新正交折線控制點位置
                        updateOrthogonalControlPointsOnNodeMove(edge.id(), node.id());
                    }
                });

                // 如果節點在已鎖定大小的群組內，強制維持群組固定尺寸
                // 已移除尺寸鎖定功能
            });

            // 網格對齊：當節點拖動結束時，自動對齊到網格
            cy.on('free', 'node', function(evt) {
                const node = evt.target;

                // 完全不處理中繼點和paper
                if (node.data('type') === 'relay' || node.data('type') === 'paper') return;

                const isGroup = isGroupNode(node);

                // 網格對齊（只對普通節點，群組不對齊避免影響內部節點）
                if (!isGroup && gridEnabled) {
                    const pos = node.position();
                    let targetX = Math.round(pos.x / gridSpacing) * gridSpacing;
                    let targetY = Math.round(pos.y / gridSpacing) * gridSpacing;

                    // 嚴格定位模式：檢查碰撞並自動移到最近可用點
                    const targetCoord = getGridCoord(targetX, targetY);
                    if (isGridOccupied(targetCoord.gridX, targetCoord.gridY, node.id())) {
                        // 碰撞！找到最近的可用位置
                        const freePos = findNearestFreeGrid(targetX, targetY, node.id());
                        targetX = freePos.x;
                        targetY = freePos.y;
                        updateStatus(`⚠️ 位置被佔用，已自動移至最近可用位置`);
                    }

                    node.position({
                        x: targetX,
                        y: targetY
                    });

                    // 更新網格佔用映射
                    updateGridOccupancy();
                }

                // Alt + 拖拉脫離群組：顯示完成訊息（已在 drag 事件中脫離）
                if (altPressed && hasMoved && nodePressedForDrag && nodePressedForDrag.id() === node.id() && alreadyLeftGroup) {
                    const nodeType = isGroup ? '群組' : '節點';
                    updateStatus(`✅ ${nodeType}已成功脫離群組`);
                    console.log(`✅ Alt+拖拉：${nodeType} ${node.id()} 已脫離群組`);

                    // 重置拖動標記
                    hasMoved = false;
                    nodePressedForDrag = null;
                    alreadyLeftGroup = false;
                    return;
                }

                // 已移除鎖定群組的自動脫離功能

                // 自動加入群組：檢測節點是否被拖到群組範圍內（支援巢狀群組）
                // 包括群組節點本身也可以加入其他群組
                const groups = cy.nodes('[type="group"]');

                if (groups.length > 0) {
                    const nodeBB = node.boundingBox();
                    const nodeCenterX = nodeBB.x1 + (nodeBB.x2 - nodeBB.x1) / 2;
                    const nodeCenterY = nodeBB.y1 + (nodeBB.y2 - nodeBB.y1) / 2;

                    // 檢查節點是否在任何群組的範圍內
                    // 優先選擇最內層的群組（巢狀群組）
                    let targetGroup = null;
                    let smallestArea = Infinity;

                    groups.forEach(group => {
                        // 避免自己拖進自己
                        if (node.id() === group.id()) return;

                        // 避免父群組拖進子群組（循環引用）
                        if (group.isChild() && group.ancestors().contains(node)) return;

                        const groupBB = group.boundingBox();
                        const groupArea = (groupBB.x2 - groupBB.x1) * (groupBB.y2 - groupBB.y1);

                        // 檢查節點中心是否在群組範圍內
                        if (nodeCenterX >= groupBB.x1 && nodeCenterX <= groupBB.x2 &&
                            nodeCenterY >= groupBB.y1 && nodeCenterY <= groupBB.y2) {
                            // 選擇面積最小的群組（最內層）
                            if (groupArea < smallestArea) {
                                targetGroup = group;
                                smallestArea = groupArea;
                            }
                        }
                    });

                    // 如果找到目標群組
                    if (targetGroup) {
                        const currentParent = node.parent();

                        // 只有當節點不在該群組內時才移動
                        if (currentParent.length === 0 || currentParent.id() !== targetGroup.id()) {
                            node.move({ parent: targetGroup.id() });

                            // 如果是群組節點，標記為巢狀群組並強制重新計算樣式
                            if (isGroup) {
                                // 延遲一點點讓 Cytoscape 更新 parent 關係
                                setTimeout(() => {
                                    cy.style().update();
                                    console.log(`🔶 巢狀群組已建立: ${node.id()} → ${targetGroup.id()}`);
                                }, 10);
                            } else {
                                cy.style().update();
                            }

                            // 舊群組可能變空，新群組恢復正常
                            if (currentParent.length > 0) refreshEmptyGroupStyle(currentParent);
                            refreshEmptyGroupStyle(targetGroup);

                            const nodeType = isGroup ? '群組' : '節點';
                            updateStatus(`${nodeType}已自動加入群組 ${targetGroup.data('label')}`);
                            console.log(`✅ ${nodeType} ${node.id()} 加入群組 ${targetGroup.id()}`);
                        }
                    } else {
                        // 檢查節點是否被拖出群組
                        const currentParent = node.parent();
                        if (currentParent.length > 0) {
                            // 節點原本在群組內，現在被拖到外面
                            node.move({ parent: null });

                            // 強制重新渲染
                            cy.style().update();
                            refreshEmptyGroupStyle(currentParent);

                            const nodeType = isGroup ? '群組' : '節點';
                            updateStatus(`${nodeType}已移出群組 ${currentParent.data('label')}`);
                            console.log(`✅ ${nodeType} ${node.id()} 移出群組 ${currentParent.id()}`);
                        }
                    }
                }
            });

            // 右鍵點擊事件
            cy.on('cxttap', function(evt) {
                const target = evt.target;

                if (target === cy) {
                    // 點擊畫布空白處，隱藏選單
                    hideContextMenu();
                } else {
                    // 點擊節點或邊
                    const renderedPosition = evt.renderedPosition || evt.cyRenderedPosition;
                    showContextMenu(renderedPosition.x, renderedPosition.y, target);
                }
            });

            // 點擊其他地方時隱藏右鍵選單
            document.addEventListener('click', function(e) {
                if (!e.target.closest('#contextMenu')) {
                    hideContextMenu();
                }
            });

            // 阻止瀏覽器預設右鍵選單
            document.getElementById('cy').addEventListener('contextmenu', function(e) {
                e.preventDefault();
            });

            // 右鍵拖拉平移畫布
            let rightDragPanning = false;
            let rightDragLastPos = null;

            document.getElementById('cy').addEventListener('mousedown', function(e) {
                if (e.button === 2) { // 右鍵
                    rightDragPanning = true;
                    rightDragLastPos = { x: e.clientX, y: e.clientY };
                }
            });

            document.addEventListener('mousemove', function(e) {
                if (rightDragPanning && rightDragLastPos) {
                    const dx = e.clientX - rightDragLastPos.x;
                    const dy = e.clientY - rightDragLastPos.y;
                    cy.panBy({ x: dx, y: dy });
                    rightDragLastPos = { x: e.clientX, y: e.clientY };
                }
            });

            document.addEventListener('mouseup', function(e) {
                if (e.button === 2) { // 右鍵
                    rightDragPanning = false;
                    rightDragLastPos = null;
                }
            });

            // 阻止滾輪事件觸發瀏覽器的上一頁/下一頁導航
            // 這會防止快速滾動時跳轉到上一頁
            document.getElementById('cy').addEventListener('wheel', function(e) {
                // 只阻止水平滾動的瀏覽器導航行為
                // 保留 Cytoscape 的縮放功能（透過 deltaY 垂直滾動）
                if (Math.abs(e.deltaX) > 0) {
                    e.preventDefault();
                }
            }, { passive: false });

            // 選擇計數更新
            let selectionTimeout = null;

            cy.on('select unselect', function(evt) {
                // 如果正在貼上,不處理選取事件（避免干擾）
                if (isPasting) {
                    return;
                }

                // 延遲更新選擇計數（避免頻繁更新）
                if (selectionTimeout) clearTimeout(selectionTimeout);
                selectionTimeout = setTimeout(() => {
                    const selected = cy.$(':selected');
                    const nodeCount = selected.nodes('[type != "relay"]').length;
                    const edgeCount = selected.edges().length;

                    if (ctrlPressed && edgeCount > 0) {
                        updateStatus(`已選擇 ${edgeCount} 條線`);
                    } else if (shiftPressed && nodeCount > 0) {
                        updateStatus(`已選擇 ${nodeCount} 個節點`);
                    } else if (nodeCount > 0 || edgeCount > 0) {
                        updateStatus(`已選擇 ${nodeCount} 個節點, ${edgeCount} 條線`);
                    }

                    // 更新群組資訊顯示（如果正在編輯群組名稱則跳過，避免輸入被覆蓋）
                    const groupNameInput = document.getElementById('group-name-input');
                    if (!groupNameInput || document.activeElement !== groupNameInput) {
                        updateGroupInfoDisplay();
                    }
                }, 100);
            });
        }
