/**
 * wf-core.js -- 核心初始化、事件綁定、工作流 CRUD
 * 從 workflow-main.js 拆分
 * 依賴: workflow-main.js, wf-undo.js
 */


        // 監聯修飾鍵
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Shift' && !shiftPressed) {
                shiftPressed = true;
                document.getElementById('mode-indicator').classList.add('active');
                updateStatus('Shift 模式：圈選節點 / 連續畫線');

                // Shift 模式：禁止線條被選中
                if (cy) {
                    cy.edges().unselectify();
                }
            }
            if (e.key === 'Control' && !ctrlPressed) {
                ctrlPressed = true;
                updateStatus('Ctrl 模式：圈選線條 / 編輯折線');

                // Ctrl 模式：禁止節點被選中
                if (cy) {
                    cy.nodes('[type != "relay"]').unselectify();
                }
            }
            if (e.key === 'Alt' && !altPressed) {
                altPressed = true;
                updateStatus('Alt 模式：框選所有元素 / 拖動脫離群組');

                // Alt 模式：允許節點和線段都可被選中，並禁用平移以啟用框選
                if (cy) {
                    cy.nodes().selectify();
                    cy.edges().selectify();

                    // 暫時禁用平移，讓框選功能生效
                    cy.userPanningEnabled(false);
                }
            }
        });

        document.addEventListener('keyup', function(e) {
            if (e.key === 'Shift') {
                shiftPressed = false;
                document.getElementById('mode-indicator').classList.remove('active');

                // 恢復線條可被選中
                if (cy) {
                    cy.edges().selectify();
                }

                // 結束連續畫線模式
                if (continuousLineMode) {
                    continuousLineMode = false;
                    continuousLineNodes = [];
                    // 清除所有節點的高亮
                    cy.nodes().removeClass('continuous-line-highlight');
                    updateStatus('連續畫線模式已結束');
                } else {
                    updateStatus('Shift 模式已關閉');
                }
            }
            if (e.key === 'Control') {
                ctrlPressed = false;

                // 恢復節點可被選中
                if (cy) {
                    cy.nodes().selectify();
                }

                updateStatus('Ctrl 模式已關閉');
            }
            if (e.key === 'Alt') {
                altPressed = false;
                // 重置拖動偵測變數
                nodePressedForDrag = null;
                hasMoved = false;
                alreadyLeftGroup = false;

                // 恢復到預設的選取模式（根據當前按住的鍵）
                if (cy) {
                    // 恢復平移為 false（本系統用右鍵平移，左鍵用於框選）
                    cy.userPanningEnabled(false);

                    if (shiftPressed) {
                        // 如果 Shift 仍按著,切換到 Shift 模式
                        cy.edges().unselectify();
                        cy.nodes().selectify();
                    } else if (ctrlPressed) {
                        // 如果 Ctrl 仍按著,切換到 Ctrl 模式
                        cy.nodes('[type != "relay"]').unselectify();
                        cy.edges().selectify();
                    } else {
                        // 都沒按,恢復預設（都可選）
                        cy.nodes().selectify();
                        cy.edges().selectify();
                    }
                }

                updateStatus('Alt 模式已關閉');
            }
        });

        // 初始化 Cytoscape
        function initCytoscape() {
            cy = cytoscape({
                container: document.getElementById('cy'),
                elements: [],

                // 啟用複合節點（群組）
                compound: true,

                // 啟用網格對齊
                autoungrabify: false,
                autounselectify: false,

                // 啟用框選功能（Shift + 拖動）
                boxSelectionEnabled: true,

                // 禁用左鍵平移（改用右鍵平移）
                userPanningEnabled: false,

                // 限制縮放級數（避免縮得太小或太大）
                minZoom: 0.1,
                maxZoom: 10,

                style: [
                    // 一般節點
                    {
                        selector: 'node[type!="relay"]',
                        style: {
                            'background-color': '#e8eaf6',
                            'label': 'data(label)',
                            'text-valign': 'bottom',
                            'text-halign': 'center',
                            'text-margin-y': 5,
                            'color': '#000000',
                            'font-size': '10px',
                            'font-weight': 'normal',
                            'shape': 'round-rectangle',
                            'width': 50,
                            'height': 50,
                            'text-wrap': 'wrap',
                            'text-max-width': 80,
                            'border-width': 1,
                            'border-color': '#333333',
                            'border-style': 'solid',
                            'background-fit': 'contain',
                            'background-clip': 'none'
                        }
                    },
                    // 群組（compound）節點 — 覆蓋一般節點的 label 設定
                    {
                        selector: ':parent',
                        style: {
                            'text-valign': 'top',
                            'text-halign': 'center',
                            'text-margin-y': -4,
                            'font-size': '11px',
                            'font-weight': 'bold',
                            'text-wrap': 'wrap',
                            'text-max-width': 200,
                            'padding': 12
                        }
                    },
                    // 中繼點樣式（一般）
                    {
                        selector: 'node[type="relay"][!taxiControl]',
                        style: {
                            'background-color': '#FF9800',
                            'width': 3,
                            'height': 3,
                            'shape': 'ellipse',
                            'border-width': 0,
                            'border-color': '#F57C00',
                            'label': '',
                            'z-index': 999
                        }
                    },
                    // 直角折線控制點樣式（藍點）
                    {
                        selector: 'node[type="relay"][taxiControl]',
                        style: {
                            'background-color': '#2196F3',
                            'width': 5,
                            'height': 5,
                            'shape': 'diamond',
                            'border-width': 1,
                            'border-color': '#1565C0',
                            'label': '',
                            'z-index': 999
                        }
                    },
                    // 黃點折線控制點樣式
                    {
                        selector: 'node[type="relay"][yellowControl]',
                        style: {
                            'background-color': '#FFC107',
                            'width': 8,
                            'height': 8,
                            'shape': 'ellipse',
                            'border-width': 2,
                            'border-color': '#FF9800',
                            'label': '',
                            'z-index': 999
                        }
                    },
                    // 正交折線控制點樣式
                    {
                        selector: 'node[type="relay"][orthogonalControl]',
                        style: {
                            'background-color': '#95a5a6',
                            'width': 6,
                            'height': 6,
                            'shape': 'ellipse',
                            'border-width': 1,
                            'border-color': '#7f8c8d',
                            'label': '',
                            'z-index': 999
                        }
                    },
                    // 正交折線線段樣式
                    {
                        selector: 'edge[edgeType="orthogonal-segment"]',
                        style: {
                            'curve-style': 'straight',
                            'width': 1,
                            'line-color': '#95a5a6',
                            'line-style': 'solid',
                            'target-arrow-shape': 'none',
                            'label': ''
                        }
                    },
                    // 選中的中繼點
                    {
                        selector: 'node[type="relay"]:selected',
                        style: {
                            'background-color': '#F44336',
                            'border-color': '#D32F2F',
                            'border-width': 1,
                            'width': 6,
                            'height': 6
                        }
                    },
                    {
                        selector: 'node[type="Start"]',
                        style: {
                            'background-color': '#4CAF50',
                            'shape': 'round-rectangle'
                        }
                    },
                    // End 節點預設樣式（藍色 - detach 模式）
                    {
                        selector: 'node[type="End"]',
                        style: {
                            'background-color': '#3B82F6',
                            'shape': 'round-rectangle'
                        }
                    },
                    // End 節點 - Detach 模式（藍色）
                    {
                        selector: 'node[type="End"][finishMode="detach"]',
                        style: {
                            'background-color': '#3B82F6'
                        }
                    },
                    // End 節點 - Cancel 模式（橘色）
                    {
                        selector: 'node[type="End"][finishMode="cancel"]',
                        style: {
                            'background-color': '#F97316'
                        }
                    },
                    // End 節點 - Strict 模式（綠色）
                    {
                        selector: 'node[type="End"][finishMode="strict"]',
                        style: {
                            'background-color': '#22C55E'
                        }
                    },
                    // Abandon 中止節點（淡紅色）
                    {
                        selector: 'node[type="Abandon"]',
                        style: {
                            'background-color': '#FCA5A5',
                            'shape': 'round-rectangle'
                        }
                    },
                    // Subflow 節點 - 通用子流程（藍色）
                    {
                        selector: 'node[type="Subflow"][subflowKind="common"]',
                        style: {
                            'background-color': '#6196ea'
                        }
                    },
                    // Subflow 節點 - 專屬子流程（綠色）
                    {
                        selector: 'node[type="Subflow"][subflowKind="dedicated"]',
                        style: {
                            'background-color': '#64aa89'
                        }
                    },
                    {
                        selector: 'node[type="sql_executor"]',
                        style: {
                            'background-color': '#2196F3'
                        }
                    },
                    {
                        selector: 'node[type="Telegram"], node[type="TELEGRAM"]',
                        style: {
                            'background-color': '#E0F7FA',
                            'shape': 'round-rectangle',
                            'border-width': 2,
                            'border-color': '#0088cc'
                        }
                    },
                    {
                        selector: 'node[type="EmailRelay"], node[type="EMAILRELAY"]',
                        style: {
                            'background-color': '#E8F5E9',
                            'shape': 'round-rectangle',
                            'border-width': 2,
                            'border-color': '#16A34A'
                        }
                    },
                    {
                        // 企業郵件節點：藍色圓角方形
                        selector: 'node[type="EmailAdapter"]',
                        style: {
                            'background-color': '#DBEAFE',
                            'shape': 'round-rectangle',
                            'border-width': 2,
                            'border-color': '#2563EB'
                        }
                    },
                    {
                        // 系統專用節點：桃紅方形
                        selector: 'node[type="SysTelegram"], node[type="SYS_TELEGRAM"]',
                        style: {
                            'background-color': '#FCE4EC',
                            'shape': 'round-rectangle',
                            'border-width': 2,
                            'border-color': '#DB2777',
                            'width': 50,
                            'height': 50
                        }
                    },
                    {
                        selector: 'node[type="subprocess"]',
                        style: {
                            'background-color': '#795548',
                            'shape': 'round-rectangle',
                            'border-width': 3,
                            'border-color': '#5D4037'
                        }
                    },
                    // 匯聚節點 - ALL 模式（預設，紫色）
                    {
                        selector: 'node[type="Converge"], node[type="CONVERGE"]',
                        style: {
                            'background-color': '#9C27B0',
                            'shape': 'round-rectangle',
                            'border-width': 3,
                            'border-color': '#7B1FA2'
                        }
                    },
                    // 匯聚節點 - ANY 模式（橘色）
                    {
                        selector: 'node[type="Converge"][?anyMode], node[type="CONVERGE"][?anyMode]',
                        style: {
                            'background-color': '#FF9800',
                            'shape': 'round-rectangle',
                            'border-width': 3,
                            'border-color': '#F57C00'
                        }
                    },
                    // Delay 暫停節點（青色）
                    {
                        selector: 'node[type="Delay"], node[type="DELAY"]',
                        style: {
                            'background-color': '#00BCD4',
                            'shape': 'round-rectangle',
                            'border-width': 2,
                            'border-color': '#0097A7'
                        }
                    },
                    // 一般線段
                    {
                        selector: 'edge',
                        style: {
                            'width': 1,
                            'line-color': '#95a5a6',
                            'target-arrow-color': '#95a5a6',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'straight',
                            'label': 'data(label)',
                            'font-size': '12px',
                            'text-rotation': 'autorotate',
                            'text-margin-y': -10
                        }
                    },
                    {
                        selector: 'edge:selected',
                        style: {
                            'width': 5,
                            'line-color': '#e74c3c',
                            'target-arrow-color': '#e74c3c'
                        }
                    },
                    // 高亮線段（用於屬性控制）
                    {
                        selector: 'edge.highlighted',
                        style: {
                            'width': 6,
                            'line-color': '#ffc107',
                            'target-arrow-color': '#ffc107',
                            'z-index': 999
                        }
                    },
                    // 全域邊框隱藏 class
                    {
                        selector: 'node.no-border',
                        style: {
                            'border-width': 0
                        }
                    },
                    // 連續畫線模式高亮節點（優先級高於 no-border）
                    {
                        selector: 'node.continuous-line-highlight',
                        style: {
                            'border-width': 4,
                            'border-color': '#ff9800',
                            'border-style': 'solid'
                        }
                    },
                    // 中繼線段（不顯示標籤）
                    {
                        selector: 'edge[edgeType="relay"]',
                        style: {
                            'label': ''
                        }
                    },
                    {
                        selector: 'edge.active',
                        style: {
                            'width': 5,
                            'line-color': '#ff0000',
                            'target-arrow-color': '#ff0000',
                            'line-style': 'solid',
                            'opacity': 1
                        }
                    },
                    {
                        selector: 'edge.completed',
                        style: {
                            'line-color': '#4CAF50',
                            'target-arrow-color': '#4CAF50'
                        }
                    },
                    // 群組（父節點）樣式
                    {
                        selector: '$node > node',
                        style: {
                            'padding-top': '10px',
                            'padding-left': '10px',
                            'padding-bottom': '10px',
                            'padding-right': '10px',
                            'text-valign': 'top',
                            'text-halign': 'center',
                            'background-color': 'rgba(102, 126, 234, 0.08)',
                            'border-width': 2,
                            'border-color': '#667eea',
                            'border-style': 'dashed'
                        }
                    },
                    {
                        selector: 'node[type="group"]',
                        style: {
                            'background-opacity': 0.15,
                            'shape': 'roundrectangle',
                            'border-width': 0,
                            'min-width': 150,
                            'min-height': 150,
                            'text-halign': 'center',
                            'text-valign': 'top',
                            'text-margin-y': 5,
                            'padding': 15
                        }
                    },
                    // 巢狀群組（群組中的群組）使用不同顏色
                    {
                        selector: 'node[type="group"]:child',
                        style: {
                            'background-color': 'rgba(255, 152, 0, 0.08)',
                            'border-color': '#ff9800',
                            'background-opacity': 0.2
                        }
                    },
                    {
                        selector: 'node[type="group"]:selected',
                        style: {
                            'border-width': 3,
                            'border-color': '#4CAF50'
                        }
                    },
                    // 一般節點選中樣式（邊框 + overlay 光暈）
                    {
                        selector: 'node:selected',
                        style: {
                            'border-width': 3,
                            'border-color': '#2196F3',
                            'overlay-color': '#2196F3',
                            'overlay-padding': 4,
                            'overlay-opacity': 0.15
                        }
                    }
                ],

                layout: {
                    name: 'preset'
                }
            });

            // 繪製網格背景
            drawGridBackground();

            // 綁定事件
            bindEvents();

            // 初始化正交折線線段拖動
            initOrthogonalSegmentDrag();
        }

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

        // 初始化拖拉功能
        function initDragAndDrop() {
            console.log('🎯 初始化拖放功能...');

            const paletteNodes = document.querySelectorAll('.palette-node');
            const cyContainer = document.getElementById('cy');

            console.log('  面板節點數:', paletteNodes.length);
            console.log('  畫布容器存在:', !!cyContainer);

            if (!cyContainer) {
                console.error('❌ 畫布容器不存在，無法綁定拖放事件');
                return;
            }

            // 綁定 dragstart 事件到左側節點
            let dragstartCount = 0;
            paletteNodes.forEach(node => {
                node.addEventListener('dragstart', function(e) {
                    const nodeType = this.getAttribute('data-node-type');
                    e.dataTransfer.setData('nodeType', nodeType);

                    // 測試節點使用特定的測試文字
                    let title = this.querySelector('.node-title').textContent;
                    if (nodeType === 'test_node_inside' || nodeType === 'test_node_outside') {
                        title = '測試圖形文字大小12345678';
                    } else if (nodeType === 'test_node_3colors') {
                        title = '三色圖案測試';
                    } else if (nodeType === 'test_node_image') {
                        title = '網路圖片測試';
                    } else if (nodeType === 'test_node_circle') {
                        title = '圓形遮罩測試';
                    }

                    e.dataTransfer.setData('nodeLabel', title);

                    // 取得節點圖示 - 優先從 data-node-icon 屬性，其次從 img 元素
                    let nodeIcon = this.getAttribute('data-node-icon') || '';
                    if (!nodeIcon) {
                        const imgElement = this.querySelector('.node-icon img');
                        if (imgElement && imgElement.src) {
                            nodeIcon = imgElement.src;
                        }
                    }
                    e.dataTransfer.setData('nodeIcon', nodeIcon);

                    console.log('🎯 拖拉開始:', nodeType, title, nodeIcon);
                });
                dragstartCount++;
            });
            console.log(`  ✓ 已綁定 ${dragstartCount} 個節點的 dragstart 事件`);

            // 綁定 dragover 事件到畫布
            cyContainer.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            console.log('  ✓ 已綁定畫布 dragover 事件');

            // 綁定 drop 事件到畫布
            cyContainer.addEventListener('drop', function(e) {
                e.preventDefault();
                console.log('🎯 Drop 事件觸發');

                const nodeType = e.dataTransfer.getData('nodeType');
                const nodeLabel = e.dataTransfer.getData('nodeLabel');
                const nodeIcon = e.dataTransfer.getData('nodeIcon');

                console.log('  節點類型:', nodeType);
                console.log('  節點標籤:', nodeLabel);
                console.log('  節點圖示:', nodeIcon);

                if (nodeType) {
                    const containerBB = cyContainer.getBoundingClientRect();
                    const mouseX = e.clientX - containerBB.left;
                    const mouseY = e.clientY - containerBB.top;

                    const pan = cy.pan();
                    const zoom = cy.zoom();

                    const modelX = (mouseX - pan.x) / zoom;
                    const modelY = (mouseY - pan.y) / zoom;

                    console.log('  添加節點到位置:', { x: modelX, y: modelY });
                    addNode(nodeType, nodeLabel, { x: modelX, y: modelY }, nodeIcon);
                } else {
                    console.warn('⚠️ 未取得節點類型');
                }
            });
            console.log('  ✓ 已綁定畫布 drop 事件');
            console.log('✅ 拖放功能初始化完成');
        }

        // Font Awesome class 到 SVG path 的映射表（使用 Font Awesome 6 的 SVG 路徑）
        const faIconSvgMap = {
            'fas fa-play': 'M73 39c-14.8-9.1-33.4-9.4-48.5-.9S0 62.6 0 80L0 432c0 17.4 9.4 33.4 24.5 41.9s33.7 8.1 48.5-.9L361 297c14.3-8.8 23-24.2 23-41s-8.7-32.2-23-41L73 39z',
            'fas fa-stop': 'M0 128C0 92.7 28.7 64 64 64L320 64c35.3 0 64 28.7 64 64l0 256c0 35.3-28.7 64-64 64L64 448c-35.3 0-64-28.7-64-64L0 128z',
            'fas fa-database': 'M448 80l0 48c0 44.2-100.3 80-224 80S0 172.2 0 128L0 80C0 35.8 100.3 0 224 0S448 35.8 448 80zM393.2 214.7c20.8-7.4 39.9-16.9 54.8-28.6L448 240c0 44.2-100.3 80-224 80S0 284.2 0 240l0-53.9c14.9 11.8 34 21.2 54.8 28.6C99.7 230.7 159.5 240 224 240s124.3-9.3 169.2-25.3zM0 346.1c14.9 11.8 34 21.2 54.8 28.6C99.7 390.7 159.5 400 224 400s124.3-9.3 169.2-25.3c20.8-7.4 39.9-16.9 54.8-28.6l0 85.9c0 44.2-100.3 80-224 80S0 476.2 0 432l0-85.9z',
            'fas fa-ban': 'M367.2 412.5L99.5 144.8C77.1 176.1 64 214.5 64 256c0 106 86 192 192 192c41.5 0 79.9-13.1 111.2-35.5zm45.3-45.3C434.9 335.9 448 297.5 448 256c0-106-86-192-192-192c-41.5 0-79.9 13.1-111.2 35.5L412.5 367.2zM0 256a256 256 0 1 1 512 0A256 256 0 1 1 0 256z',
            'fas fa-sitemap': 'M80 48a48 48 0 1 1 96 0A48 48 0 1 1 80 48zm64 193.7l0 65.1 51.2 35.8c11.3 7.9 13.9 23.5 5.9 34.8s-23.5 13.9-34.8 5.9L128 355.6l-38.4 26.9c-11.3 7.9-26.9 5.3-34.8-5.9s-5.3-26.9 5.9-34.8L112 306.7l0-65.1c-49.3-12.5-85.8-56.9-85.8-109.6C26.2 59.1 85.1 0 157.9 0s131.7 59.1 131.7 132C289.6 184.7 253.1 229.1 203.8 241.7z',
            'fas fa-clock': 'M256 0a256 256 0 1 1 0 512A256 256 0 1 1 256 0zM232 120l0 136c0 8 4 15.5 10.7 20l96 64c11 7.4 25.9 4.4 33.3-6.7s4.4-25.9-6.7-33.3L280 243.2 280 120c0-13.3-10.7-24-24-24s-24 10.7-24 24z',
            'fas fa-code-branch': 'M80 104a24 24 0 1 0 0-48 24 24 0 1 0 0 48zm80-24c0 32.8-19.7 61-48 73.3l0 87.8c18.8-10.9 40.7-17.1 64-17.1l96 0c35.3 0 64-28.7 64-64l0-6.7C307.7 141 288 112.8 288 80c0-44.2 35.8-80 80-80s80 35.8 80 80c0 32.8-19.7 61-48 73.3l0 6.7c0 70.7-57.3 128-128 128l-96 0c-35.3 0-64 28.7-64 64l0 6.7c28.3 12.3 48 40.5 48 73.3c0 44.2-35.8 80-80 80s-80-35.8-80-80c0-32.8 19.7-61 48-73.3l0-6.7 0-198.7C19.7 141 0 112.8 0 80C0 35.8 35.8 0 80 0s80 35.8 80 80zm232 0a24 24 0 1 0 -48 0 24 24 0 1 0 48 0zM80 456a24 24 0 1 0 0-48 24 24 0 1 0 0 48z',
            'fas fa-compress-arrows-alt': 'M436 192L392 192l-24 0 0-24 0-44 0-24 24 0 44 0 24 0 0 48-24 0-20 0 0 20 0 24-24 0 0 24 24 0 0 24 0 44 0 24-24 0-44 0-24 0 0-48 24 0 20 0 0-20 0-24 24 0 0-24zm-360 0l24 0 0 24-24 0 0 24 0 20-20 0-24 0 0 48 24 0 44 0 24 0 0-24 0-44 0-24-24 0 0-24 24 0 0-24 0-20 20 0 24 0 0-48-24 0-44 0-24 0 0 24 0 44 0 24z',
            'fas fa-clipboard-list': 'M280 64l40 0c35.3 0 64 28.7 64 64l0 320c0 35.3-28.7 64-64 64L64 512c-35.3 0-64-28.7-64-64L0 128C0 92.7 28.7 64 64 64l40 0 9.6 0C121 27.5 153.3 0 192 0s71 27.5 78.4 64l9.6 0zM64 112c-8.8 0-16 7.2-16 16l0 320c0 8.8 7.2 16 16 16l256 0c8.8 0 16-7.2 16-16l0-320c0-8.8-7.2-16-16-16l-16 0 0 24c0 13.3-10.7 24-24 24l-88 0-88 0c-13.3 0-24-10.7-24-24l0-24-16 0zm128-8a24 24 0 1 0 0-48 24 24 0 1 0 0 48z',
            'fas fa-calendar-times': 'M128 0c17.7 0 32 14.3 32 32l0 32 128 0 0-32c0-17.7 14.3-32 32-32s32 14.3 32 32l0 32 48 0c26.5 0 48 21.5 48 48l0 48L0 160l0-48C0 85.5 21.5 64 48 64l48 0 0-32c0-17.7 14.3-32 32-32zM0 192l448 0 0 272c0 26.5-21.5 48-48 48L48 512c-26.5 0-48-21.5-48-48L0 192z',
            'fas fa-envelope': 'M48 64C21.5 64 0 85.5 0 112c0 15.1 7.1 29.3 19.2 38.4L236.8 313.6c11.4 8.5 27 8.5 38.4 0L492.8 150.4c12.1-9.1 19.2-23.3 19.2-38.4c0-26.5-21.5-48-48-48L48 64zM0 176L0 384c0 35.3 28.7 64 64 64l384 0c35.3 0 64-28.7 64-64l0-208L294.4 339.2c-22.8 17.1-54 17.1-76.8 0L0 176z',
            'fas fa-copy': 'M208 0L332.1 0c12.7 0 24.9 5.1 33.9 14.1l67.9 67.9c9 9 14.1 21.2 14.1 33.9L448 336c0 26.5-21.5 48-48 48l-192 0c-26.5 0-48-21.5-48-48l0-288c0-26.5 21.5-48 48-48zM48 128l80 0 0 64-64 0 0 256 192 0 0-32 64 0 0 48c0 26.5-21.5 48-48 48L48 512c-26.5 0-48-21.5-48-48L0 176c0-26.5 21.5-48 48-48z',
            'fas fa-calculator': 'M64 0C28.7 0 0 28.7 0 64L0 448c0 35.3 28.7 64 64 64l256 0c35.3 0 64-28.7 64-64l0-384c0-35.3-28.7-64-64-64L64 0zM96 64l192 0c17.7 0 32 14.3 32 32l0 32c0 17.7-14.3 32-32 32L96 160c-17.7 0-32-14.3-32-32l0-32c0-17.7 14.3-32 32-32z',
            'fas fa-bell': 'M224 0c-17.7 0-32 14.3-32 32l0 19.2C119 66 64 130.6 64 208l0 18.8c0 47-17.3 92.4-48.5 127.6l-7.4 8.3c-8.4 9.4-10.4 22.9-5.3 34.4S19.4 416 32 416l384 0c12.6 0 24-7.4 29.2-18.9s3.1-25-5.3-34.4l-7.4-8.3C401.3 319.2 384 273.9 384 226.8l0-18.8c0-77.4-55-142-128-156.8L256 32c0-17.7-14.3-32-32-32zm45.3 493.3c12-12 18.7-28.3 18.7-45.3l-64 0-64 0c0 17 6.7 33.3 18.7 45.3s28.3 18.7 45.3 18.7s33.3-6.7 45.3-18.7z',
            'fas fa-route': 'M512 96c0 50.2-59.1 125.1-84.6 155c-3.8 4.4-9.4 6.1-14.5 5L320 256c-17.7 0-32 14.3-32 32s14.3 32 32 32l96 0c53 0 96 43 96 96s-43 96-96 96l-276.4 0c8.7-9.9 19.3-22.6 30-36.8c6.3-8.4 12.8-17.6 19-27.2L416 448c17.7 0 32-14.3 32-32s-14.3-32-32-32l-96 0c-53 0-96-43-96-96s43-96 96-96l39.8 0c-21-31.5-39.8-67.7-39.8-96c0-53 43-96 96-96s96 43 96 96z',
            'fas fa-plug': 'M96 0C78.3 0 64 14.3 64 32l0 96 64 0 0-96c0-17.7-14.3-32-32-32zm0 256l64 0 0-64-64 0 0 64zM320 0c-17.7 0-32 14.3-32 32l0 96 64 0 0-96c0-17.7-14.3-32-32-32zm32 256l0-64-64 0 0 64 64 0zm88-32c13.3 0 24-10.7 24-24s-10.7-24-24-24l-40 0 0-48c0-44.2-35.8-80-80-80l-192 0c-44.2 0-80 35.8-80 80l0 48-40 0c-13.3 0-24 10.7-24 24s10.7 24 24 24l40 0 0 80c0 80.2 59 146.6 136 158.2l0 49.8 80 0 0-49.8c77-11.6 136-78 136-158.2l0-80 40 0z',
            'fas fa-cog': 'M495.9 166.6c3.2 8.7 .5 18.4-6.4 24.6l-43.3 39.4c1.1 8.3 1.7 16.8 1.7 25.4s-.6 17.1-1.7 25.4l43.3 39.4c6.9 6.2 9.6 15.9 6.4 24.6c-4.4 11.9-9.7 23.3-15.8 34.3l-4.7 8.1c-6.6 11-14 21.4-22.1 31.2c-5.9 7.2-15.7 9.6-24.5 6.8l-55.7-17.7c-13.4 10.3-28.2 18.9-44 25.4l-12.5 57.1c-2 9.1-9 16.3-18.2 17.8c-13.8 2.3-28 3.5-42.5 3.5s-28.7-1.2-42.5-3.5c-9.2-1.5-16.2-8.7-18.2-17.8l-12.5-57.1c-15.8-6.5-30.6-15.1-44-25.4L83.1 425.9c-8.8 2.8-18.6 .3-24.5-6.8c-8.1-9.8-15.5-20.2-22.1-31.2l-4.7-8.1c-6.1-11-11.4-22.4-15.8-34.3c-3.2-8.7-.5-18.4 6.4-24.6l43.3-39.4C64.6 273.1 64 264.6 64 256s.6-17.1 1.7-25.4L22.4 191.2c-6.9-6.2-9.6-15.9-6.4-24.6c4.4-11.9 9.7-23.3 15.8-34.3l4.7-8.1c6.6-11 14-21.4 22.1-31.2c5.9-7.2 15.7-9.6 24.5-6.8l55.7 17.7c13.4-10.3 28.2-18.9 44-25.4l12.5-57.1c2-9.1 9-16.3 18.2-17.8C227.3 1.2 241.5 0 256 0s28.7 1.2 42.5 3.5c9.2 1.5 16.2 8.7 18.2 17.8l12.5 57.1c15.8 6.5 30.6 15.1 44 25.4l55.7-17.7c8.8-2.8 18.6-.3 24.5 6.8c8.1 9.8 15.5 20.2 22.1 31.2l4.7 8.1c6.1 11 11.4 22.4 15.8 34.3zM256 336a80 80 0 1 0 0-160 80 80 0 1 0 0 160z'
        };

        // 將 SVG path 轉換為 data URL
        function getSvgDataUrl(iconClass, color = '#333333') {
            const path = faIconSvgMap[iconClass];
            if (!path) return '';

            // 根據圖示調整 viewBox（大多數 FA 圖示是 512x512）
            const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path fill="${color}" d="${path}"/></svg>`;
            return 'data:image/svg+xml,' + encodeURIComponent(svg);
        }

        // Font Awesome class 到 Unicode 的映射表（備用）
        const faIconMap = {
            'fas fa-play': '\uf04b',
            'fas fa-stop': '\uf04d',
            'fas fa-database': '\uf1c0',
            'fas fa-ban': '\uf05e',
            'fas fa-sitemap': '\uf0e8',
            'fas fa-clock': '\uf017',
            'fas fa-code-branch': '\uf126',
            'fas fa-compress-arrows-alt': '\uf78c',
            'fas fa-clipboard-list': '\uf46d',
            'fas fa-calendar-times': '\uf273',
            'fas fa-envelope': '\uf0e0',
            'fas fa-copy': '\uf0c5',
            'fas fa-calculator': '\uf1ec',
            'fas fa-circle-dot': '\uf192',
            'fas fa-file-signature': '\uf573',
            'fas fa-bell': '\uf0f3',
            'fas fa-route': '\uf4d7',
            'fas fa-plug': '\uf1e6',
            'fas fa-cog': '\uf013',
            'fas fa-cogs': '\uf085'
        };

        // 新增節點
        function addNode(type, label, position, icon) {
            pushUndoState();
            type = normalizeNodeType(type) || type;
            nodeCounter++;
            const nodeId = `node-${type}-${nodeCounter}`;

            // 判斷 icon 是本地 SVG 路徑還是 Font Awesome class
            let iconUrl = '';
            if (icon) {
                if (icon.startsWith('/static/') || icon.startsWith('http')) {
                    // 已經是 URL 路徑，直接使用
                    iconUrl = icon;
                } else {
                    // 舊的 Font Awesome class，使用舊方法轉換（向後兼容）
                    iconUrl = getSvgDataUrl(icon, '#333333');
                }
            }

            const newNode = cy.add({
                data: {
                    id: nodeId,
                    label: label,           // 顯示名稱（預設為節點類型的中文名）
                    type: type,
                    icon: icon || '',       // 保存 icon 路徑或 class
                    iconUrl: iconUrl,       // 保存實際的圖示 URL
                    description: '',        // 描述預設為空
                    config: {}
                },
                position: position
            });

            // 套用圖示背景
            if (iconUrl) {
                newNode.style({
                    'background-image': iconUrl,
                    'background-fit': 'contain',
                    'background-clip': 'none'
                });
            }

            // 套用全域邊框隱藏 class
            if (!globalNodeBorder) {
                newNode.addClass('no-border');
            }

            updateStatus(`已新增節點: ${label} (${nodeId})`);

            // 自動選取新節點並切換設定面板
            cy.elements().unselect();
            newNode.select();
            showNodeInfo(newNode);
        }

        // 建立連線
        function createEdge(sourceNode, targetNode) {
            // 驗證 1：防止自連接
            if (sourceNode.id() === targetNode.id()) {
                updateStatus('❌ 不能連接節點到自己', 'error');
                return false;
            }

            // 驗證 2：防止異類連接（node ↔ group）
            const sourceIsCompound = isGroupNode(sourceNode);
            const targetIsCompound = isGroupNode(targetNode);

            // 檢查是否為異類連接
            if (sourceIsCompound !== targetIsCompound) {
                updateStatus('❌ 不能在節點與群組之間建立連線', 'error');
                return false;
            }

            // 通過驗證，建立連線
            pushUndoState();
            edgeCounter++;
            const edgeId = `edge-${edgeCounter}`;

            cy.add({
                data: {
                    id: edgeId,
                    source: sourceNode.id(),
                    target: targetNode.id(),
                    label: ''
                }
            });

            // 更新線段選擇器
            updateEdgeSelector();
            return true;
        }

        // 分類折疊功能（手風琴效果：點擊一個分類時，收合其他分類）
        function toggleCategory(categoryId) {
            const content = document.getElementById(categoryId);
            const icon = document.getElementById(categoryId + '-icon');

            if (content.classList.contains('open')) {
                // 已經打開的，點擊後收合
                content.classList.remove('open');
                icon.classList.remove('open');
            } else {
                // 手風琴效果：先收合所有其他分類
                const allCategories = document.querySelectorAll('.category-content');
                allCategories.forEach(cat => {
                    if (cat.id !== categoryId) {
                        cat.classList.remove('open');
                        const catIcon = document.getElementById(cat.id + '-icon');
                        if (catIcon) catIcon.classList.remove('open');
                    }
                });
                // 展開當前分類
                content.classList.add('open');
                icon.classList.add('open');
            }
        }

        // 全部打開分類（不包含流程清單）
        function expandAllCategories() {
            // 自動尋找所有類別（透過 CSS class）
            const categories = document.querySelectorAll('.category-content');
            categories.forEach(content => {
                const catId = content.id;
                const icon = document.getElementById(catId + '-icon');
                if (content && icon) {
                    content.classList.add('open');
                    icon.classList.add('open');
                }
            });
            updateStatus('已打開所有節點分類');
        }

        // 全部關閉分類
        function collapseAllCategories() {
            // 自動尋找所有類別（透過 CSS class）
            const categories = document.querySelectorAll('.category-content');
            categories.forEach(content => {
                const catId = content.id;
                const icon = document.getElementById(catId + '-icon');
                if (content && icon) {
                    content.classList.remove('open');
                    icon.classList.remove('open');
                }
            });
            updateStatus('已關閉所有節點分類');
        }

        // 切換全部分類（展開/收合）
        let allCategoriesExpanded = true;  // 預設展開
        function toggleAllCategories() {
            const btn = document.getElementById('toggle-all-categories-btn');
            const icon = btn ? btn.querySelector('i') : null;

            if (allCategoriesExpanded) {
                collapseAllCategories();
                if (icon) {
                    icon.className = 'fas fa-angles-down';
                }
            } else {
                expandAllCategories();
                if (icon) {
                    icon.className = 'fas fa-angles-up';
                }
            }
            allCategoriesExpanded = !allCategoriesExpanded;
        }

        // 鎖定界面（未選擇流程時）
        function lockInterface() {
            console.log('🔒 鎖定界面');

            // 顯示提示overlay
            const overlay = document.getElementById('no-workflow-overlay');
            if (overlay) {
                overlay.style.display = 'block';
                console.log('  ✓ 顯示提示overlay');
            }

            // 禁用所有節點拖拉
            const nodes = document.querySelectorAll('.palette-node');
            nodes.forEach(node => {
                node.style.opacity = '0.5';
                node.style.cursor = 'not-allowed';
                node.setAttribute('draggable', 'false');
            });
            console.log(`  ✓ 禁用 ${nodes.length} 個節點`);

            // 隱藏存檔按鈕
            document.getElementById('btn-save-workflow').style.display = 'none';
            document.getElementById('workflow-info').style.display = 'none';
            console.log('  ✓ 隱藏按鈕和流程資訊');

            // 清空畫布
            if (window.cy) {
                cy.elements().remove();
                console.log('  ✓ 清空畫布');
            }
        }

        // 解鎖界面（選擇流程後）- 已棄用，使用 enterDesignMode() 代替
        function unlockInterface(workflowName, workflowVersion, workflowDescription, workflowCategory) {
            console.log(`🔓 解鎖界面: ${workflowName} (版本 ${workflowVersion})`);

            // 啟用所有節點拖拉
            const nodes = document.querySelectorAll('.palette-node');
            nodes.forEach(node => {
                node.style.opacity = '1';
                node.style.cursor = 'move';
                node.setAttribute('draggable', 'true');
            });
            console.log(`  ✓ 啟用 ${nodes.length} 個節點`);

            // 顯示所有操作按鈕，並移除 disabled 屬性
            const saveBtn = document.getElementById('btn-save-workflow');
            const saveAndCloseBtn = document.getElementById('btn-save-and-close');
            const saveNewVersionBtn = document.getElementById('btn-save-new-version');
            const discardBtn = document.getElementById('btn-discard');

            saveBtn.style.display = 'inline-block';
            saveAndCloseBtn.style.display = 'inline-block';
            if (saveNewVersionBtn) saveNewVersionBtn.style.display = 'inline-block';
            discardBtn.style.display = 'inline-block';

            // 完整清除唯讀模式殘留樣式（disabled 屬性、class、inline style）
            [saveBtn, saveAndCloseBtn, saveNewVersionBtn, discardBtn].forEach(btn => {
                if (!btn) return;
                btn.removeAttribute('disabled');
                btn.disabled = false;
                btn.classList.remove('disabled');
                btn.style.opacity = '';
                btn.style.cursor = '';
                btn.title = '';
            });
            console.log('  ✓ 顯示操作按鈕並啟用');

            // 顯示流程資訊
            document.getElementById('workflow-info').style.display = 'flex';
            document.getElementById('current-workflow-name').value = workflowName || '未命名流程';
            document.getElementById('current-workflow-version').textContent = workflowVersion ? `版本 ${workflowVersion}` : 'v1.0';
            const categorySelect = document.getElementById('current-workflow-category');
            if (categorySelect) {
                categorySelect.value = workflowCategory || '';
            }
            const descPreview = (workflowDescription || '').split('\n')[0];
            document.getElementById('current-workflow-description').value = descPreview;
            console.log('  ✓ 更新流程資訊顯示');
        }

        // 更新流程名稱和描述
        async function updateWorkflowInfo() {
            if (!currentWorkflowId) return;

            const nameInput = document.getElementById('current-workflow-name');
            const categoryInput = document.getElementById('current-workflow-category');
            const newName = nameInput.value.trim();
            const newDescription = currentWorkflow?.description || '';
            const newCategorySc = categoryInput ? categoryInput.value : '';

            if (!newName) {
                updateStatus('流程名稱不能為空', 'warning');
                nameInput.value = currentWorkflow?.name || '未命名流程';
                return;
            }

            // 檢查是否有變更
            if (newName === currentWorkflow?.name &&
                newDescription === (currentWorkflow?.description || '') &&
                newCategorySc === (currentWorkflow?.category_secure_code || '')) {
                return; // 沒有變更
            }

            try {
                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: newName,
                        description: newDescription,
                        category_secure_code: newCategorySc
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const result = await response.json();
                currentWorkflow.name = newName;
                currentWorkflow.description = newDescription;
                currentWorkflow.category_secure_code = newCategorySc;
                updateStatus(`✅ 已更新流程資訊`, 'info');
                console.log('✅ 流程資訊已更新:', { name: newName, description: newDescription, category_secure_code: newCategorySc });
            } catch (error) {
                console.error('❌ 更新流程資訊失敗:', error);
                updateStatus('更新流程資訊失敗', 'warning');
                nameInput.value = currentWorkflow?.name || '未命名流程';
                document.getElementById('current-workflow-description').value = (currentWorkflow?.description || '').split('\n')[0];
                if (categoryInput) categoryInput.value = currentWorkflow?.category_secure_code || '';
            }
        }

        // 描述編輯 Modal
        window.openDescriptionModal = openDescriptionModal;
        window.closeDescriptionModal = closeDescriptionModal;
        window.saveDescription = saveDescription;

        function openDescriptionModal() {
            const textarea = document.getElementById('description-modal-textarea');
            textarea.value = currentWorkflow?.description || '';
            document.getElementById('description-modal').style.display = 'flex';
            textarea.focus();
        }

        function closeDescriptionModal() {
            document.getElementById('description-modal').style.display = 'none';
        }

        async function saveDescription() {
            const fullText = document.getElementById('description-modal-textarea').value;
            closeDescriptionModal();
            document.getElementById('current-workflow-description').value = fullText.split('\n')[0];
            if (!currentWorkflowId) return;
            try {
                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description: fullText })
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                currentWorkflow.description = fullText;
                updateStatus('✅ 已更新描述', 'info');
            } catch (error) {
                console.error('❌ 更新描述失敗:', error);
                updateStatus('更新描述失敗', 'warning');
                document.getElementById('current-workflow-description').value = (currentWorkflow?.description || '').split('\n')[0];
            }
        }

        // 進入設計模式（透過 URL 參數直接調用，不需要選擇對話框）
        async function enterDesignMode(workflowId) {
            console.log('🎨 進入設計模式:', workflowId);

            // 設置當前流程 ID
            currentWorkflowId = workflowId;

            // 重置表單欄位分頁狀態
            resetFormFieldsTab();

            // 載入流程並解鎖界面
            await loadWorkflow();

            console.log('✅ 已進入設計模式');
        }

        // 重置表單欄位分頁狀態
        function resetFormFieldsTab() {
            formFieldsLoaded = false;
            currentMappedForms = [];
            currentFormFields = [];
            selectedFormId = null;
            currentVersionType = 'design';

            // 重置 UI
            const listContainer = document.getElementById('mapped-forms-list');
            if (listContainer) {
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #999; font-size: 11px;">
                        <i class="fas fa-spinner fa-spin"></i> 載入中...
                    </div>
                `;
            }

            const tbody = document.getElementById('form-fields-tbody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 30px; color: #999;">
                            請先選擇表單
                        </td>
                    </tr>
                `;
            }

            const titleEl = document.getElementById('form-fields-title');
            if (titleEl) {
                titleEl.textContent = '';
            }

            const formsCountEl = document.getElementById('mapped-forms-count');
            if (formsCountEl) {
                formsCountEl.textContent = '共 0 張表單';
            }

            const fieldsCountEl = document.getElementById('form-fields-count');
            if (fieldsCountEl) {
                fieldsCountEl.textContent = '共 0 個欄位';
            }

            // 重置版本切換按鈕
            const btnDesign = document.getElementById('btn-form-design');
            const btnPublished = document.getElementById('btn-form-published');
            if (btnDesign && btnPublished) {
                btnDesign.style.background = '#667eea';
                btnDesign.style.color = 'white';
                btnPublished.style.background = '#e0e0e0';
                btnPublished.style.color = '#666';
            }
        }

        // 儲存並關閉
        async function saveAndClose() {
            console.log('💾 儲存並關閉');

            // 先儲存
            if (!currentWorkflowId) {
                updateStatus('請先選擇或建立一個流程', 'warning');
                return;
            }

            // 調用儲存函數
            await saveWorkflow();

            // 等待縮圖生成完成（最多等待 5 秒）
            console.log('📸 等待縮圖生成完成...');
            const thumbnailPromise = generateAndSaveThumbnail();
            const timeoutPromise = new Promise(resolve => setTimeout(resolve, 5000));

            await Promise.race([thumbnailPromise, timeoutPromise]);
            console.log('✓ 縮圖處理完成或超時');

            // 清空狀態歷史記錄
            clearStatusHistory();

            // 判斷來源：從樹系圖來的回到樹系圖，否則回清單
            const urlParams = new URLSearchParams(window.location.search);
            const fromTree = urlParams.get('from') === 'tree';
            const rootCode = urlParams.get('root');

            if (fromTree && rootCode) {
                window.location.href = '/forms/workflows/' + rootCode + '/tree';
            } else {
                window.location.href = '/forms/workflows';
            }

            console.log('✅ 已儲存並返回');
        }

        // 儲存新版本
        async function saveNewVersion(targetNode = null) {
            console.log('💾 儲存新版本', targetNode ? '(已指定目標節點)' : '');

            if (!currentWorkflowId) {
                updateStatus('請先選擇或建立一個流程', 'warning');
                return;
            }

            try {
                // 先儲存目前的變更
                await saveWorkflow();

                // 如果沒有指定 targetNode，先確認
                if (!targetNode) {
                    if (!confirm('確定要儲存為新版本？\n\n將會複製目前流程及綁定表單，版本號會遞增。')) {
                        return;
                    }
                }

                updateStatus('正在儲存新版本...', 'info');

                const requestBody = {
                    name: document.getElementById('current-workflow-name')?.value,
                    description: currentWorkflow?.description || ''
                };

                // 如果有指定目標節點
                if (targetNode) {
                    requestBody.target_node = targetNode;
                }

                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}/save-new-version`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                const result = await response.json();

                if (result.success) {
                    const newVersion = result.data.version;
                    const newSecureCode = result.data.secure_code;
                    const message = result.data.form_template_secure_code
                        ? `已在背景儲存為新版本 (${newVersion})，含綁定表單`
                        : `已在背景儲存為新版本 (${newVersion})`;

                    updateStatus(message, 'success');

                    // 不切換到新版本，保持在當前版本繼續編輯
                    // 顯示提示訊息，讓用戶知道新版本的位置
                    alert(`${message}\n\n新版本編號: ${newSecureCode}\n\n您仍在編輯目前版本，可從流程清單開啟新版本。`);
                } else if (result.needs_target_node) {
                    // 專屬子流程需要選擇目標 SubFlow 節點
                    showSubflowNodeSelector(result.available_nodes);
                } else {
                    updateStatus(`儲存新版本失敗: ${result.message}`, 'error');
                    if (!result.needs_target_node) {
                        alert(result.message);
                    }
                }
            } catch (error) {
                console.error('❌ 儲存新版本錯誤:', error);
                updateStatus(`儲存新版本發生錯誤: ${error.message}`, 'error');
            }
        }

        // 顯示 SubFlow 節點選擇器（專屬子流程另存新版時使用）
        function showSubflowNodeSelector(availableNodes) {
            // 移除舊的 modal（如果存在）
            const existingModal = document.getElementById('subflow-node-selector-modal');
            if (existingModal) {
                existingModal.remove();
            }

            // 建立選項列表 HTML
            const optionsHtml = availableNodes.map((node, index) => `
                <label class="flex items-center p-3 border rounded-lg cursor-pointer hover:bg-gray-50 transition-colors ${index === 0 ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}">
                    <input type="radio" name="target_node" value="${index}" ${index === 0 ? 'checked' : ''} class="mr-3">
                    <div>
                        <div class="font-medium text-gray-900">${node.display}</div>
                        <div class="text-sm text-gray-500">節點 ID: ${node.node_id}</div>
                    </div>
                </label>
            `).join('');

            // 建立 modal HTML
            const modalHtml = `
                <div id="subflow-node-selector-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
                    <div class="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[80vh] flex flex-col">
                        <div class="px-6 py-4 border-b border-gray-200">
                            <h3 class="text-lg font-semibold text-gray-900">選擇目標 SubFlow 節點</h3>
                            <p class="text-sm text-gray-600 mt-1">這是專屬子流程，請選擇新版本要綁定到哪個 SubFlow 節點</p>
                        </div>
                        <div class="px-6 py-4 overflow-y-auto flex-1 space-y-2">
                            ${optionsHtml}
                        </div>
                        <div class="px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
                            <button id="subflow-selector-cancel" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50">取消</button>
                            <button id="subflow-selector-confirm" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">確定另存新版</button>
                        </div>
                    </div>
                </div>
            `;

            // 插入到 body
            document.body.insertAdjacentHTML('beforeend', modalHtml);

            const modal = document.getElementById('subflow-node-selector-modal');
            const cancelBtn = document.getElementById('subflow-selector-cancel');
            const confirmBtn = document.getElementById('subflow-selector-confirm');

            // 取消按鈕
            cancelBtn.addEventListener('click', () => {
                modal.remove();
                updateStatus('已取消另存新版', 'info');
            });

            // 確定按鈕
            confirmBtn.addEventListener('click', () => {
                const selectedIndex = document.querySelector('input[name="target_node"]:checked')?.value;
                if (selectedIndex !== undefined) {
                    const selectedNode = availableNodes[parseInt(selectedIndex)];
                    modal.remove();

                    // 帶著選擇的目標節點重新呼叫 saveNewVersion
                    saveNewVersion({
                        workflow_secure_code: selectedNode.workflow_secure_code,
                        node_id: selectedNode.node_id
                    });
                }
            });

            // 點擊 radio 時更新樣式
            modal.querySelectorAll('input[name="target_node"]').forEach(radio => {
                radio.addEventListener('change', () => {
                    modal.querySelectorAll('label').forEach(label => {
                        label.classList.remove('border-blue-500', 'bg-blue-50');
                        label.classList.add('border-gray-200');
                    });
                    radio.closest('label').classList.remove('border-gray-200');
                    radio.closest('label').classList.add('border-blue-500', 'bg-blue-50');
                });
            });
        }

        // 變更追蹤變數
        let initialGraphState = null;
        let hasUnsavedChanges = false;
        let hasEverSaved = false;  // 追蹤是否曾經成功儲存過

        // 初始化變更追蹤
        function initChangeTracking() {
            if (cy) {
                // 記錄初始狀態
                initialGraphState = JSON.stringify(cy.json());
                hasUnsavedChanges = false;

                // 監聽任何圖形變更事件
                cy.on('add remove data position', function() {
                    checkForChanges();
                });
            }
        }

        // 檢查是否有變更
        function checkForChanges() {
            if (!cy || !initialGraphState) return false;

            const currentState = JSON.stringify(cy.json());
            hasUnsavedChanges = (currentState !== initialGraphState);
            return hasUnsavedChanges;
        }

        // 更新儲存按鈕狀態（反映未儲存變更）
        function updateSaveButtonState() {
            const saveBtn = document.getElementById('btn-save-workflow');
            if (!saveBtn) return;
            if (hasUnsavedChanges) {
                saveBtn.style.outline = '2px solid #f59e0b';
                saveBtn.title = '有未儲存的變更';
            } else {
                saveBtn.style.outline = '';
                saveBtn.title = '';
            }
        }

        // 更新初始狀態（在儲存後調用）
        function updateInitialState() {
            if (cy) {
                initialGraphState = JSON.stringify(cy.json());
                hasUnsavedChanges = false;
                updateSaveButtonState();
            }
        }

        // 放棄並關閉
        async function discardAndClose() {
            console.log('🚫 放棄變更並關閉');

            // 檢查是否有未儲存的變更
            const hasChanges = checkForChanges();

            if (hasChanges) {
                // 有變更，需要確認
                if (!confirm('您有未儲存的變更，確定要放棄並離開嗎？')) {
                    console.log('  用戶取消放棄操作');
                    return;
                }
                console.log('  用戶確認放棄所有未儲存的變更');
            } else {
                console.log('  沒有未儲存的變更，直接返回');
            }

            // 如果從未儲存過，刪除這個工作流程記錄
            if (!hasEverSaved && currentWorkflowId) {
                console.log('⚠️ 從未儲存過，刪除工作流程記錄:', currentWorkflowId);
                try {
                    const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`, {
                        method: 'DELETE'
                    });

                    if (response.ok) {
                        console.log('✅ 已刪除從未儲存的工作流程');
                    } else {
                        console.error('❌ 刪除工作流程失敗:', response.status);
                    }
                } catch (error) {
                    console.error('❌ 刪除工作流程時發生錯誤:', error);
                }
            }

            // 清空狀態歷史記錄
            clearStatusHistory();

            // 返回流程目錄頁
            window.location.href = '/forms/workflows';

            console.log('✅ 已放棄變更並返回流程目錄');
        }

        // 載入分類列表（二層結構）
        async function loadCategories() {
            try {
                const response = await fetch('/api/forms/data/categories');
                const result = await response.json();

                if (result.success) {
                    const categorySelect = document.getElementById('current-workflow-category');
                    if (categorySelect) {
                        categorySelect.innerHTML = '';

                        const categories = result.data || [];
                        categories.forEach(cat => {
                            const option = document.createElement('option');
                            option.value = cat.secure_code;
                            option.textContent = cat.display || cat.name;
                            categorySelect.appendChild(option);
                        });

                        console.log('✅ 已載入分類:', categories.length, '個');
                    }
                }
            } catch (error) {
                console.error('❌ 載入分類失敗:', error);
            }
        }

        // 載入流程列表
        async function loadWorkflowList() {
            try {
                const response = await fetch('/api/workflows/data/templates');
                const workflows = await response.json();

                // 渲染到大型流程選擇卡片
                const selectionList = document.getElementById('workflow-selection-list');
                if (selectionList) {
                    selectionList.innerHTML = '';

                    if (workflows.length === 0) {
                        selectionList.innerHTML = `
                            <div style="text-align: center; padding: 60px 20px; color: var(--text-tertiary);">
                                <i class="fas fa-folder-open" style="font-size: 4rem; margin-bottom: 20px; opacity: 0.3;"></i>
                                <p style="font-size: 1.1rem;">尚無任何流程</p>
                                <p style="font-size: 0.9rem;">點擊上方「新增流程」按鈕開始建立</p>
                            </div>
                        `;
                    } else {
                        workflows.forEach(w => {
                            const card = document.createElement('div');
                            card.className = 'workflow-selection-card';

                            // 格式化日期
                            const createdDate = w.created_at ? BkTime.format(w.created_at, 'date') : '未知';

                            // 計算節點數量
                            const nodeCount = w.cytoscape_config?.nodes?.length || 0;
                            const edgeCount = w.cytoscape_config?.edges?.length || 0;

                            card.innerHTML = `
                                <div class="card-header">
                                    <div style="flex: 1;">
                                        <h3 class="card-title">
                                            <i class="fas fa-project-diagram" style="color: var(--accent-primary);"></i>
                                            ${w.name}
                                        </h3>
                                        <div class="card-desc">${w.description || '無描述'}</div>
                                        <div class="card-meta">
                                            <div class="card-meta-item">
                                                <i class="fas fa-calendar-alt"></i>
                                                <span>${createdDate}</span>
                                            </div>
                                            <div class="card-meta-item">
                                                <i class="fas fa-circle-nodes"></i>
                                                <span>${nodeCount} 個節點</span>
                                            </div>
                                            <div class="card-meta-item">
                                                <i class="fas fa-link"></i>
                                                <span>${edgeCount} 條連線</span>
                                            </div>
                                        </div>
                                    </div>
                                    <button class="card-delete-btn">
                                        <i class="fas fa-trash"></i> 刪除
                                    </button>
                                </div>
                            `;

                            // 點擊卡片進入設計模式
                            card.onclick = (e) => {
                                // 如果點擊的是刪除按鈕，不要進入設計模式
                                if (!e.target.closest('.card-delete-btn')) {
                                    enterDesignMode(w.id);
                                }
                            };

                            // 刪除按鈕事件
                            const deleteBtn = card.querySelector('.card-delete-btn');
                            deleteBtn.onclick = (e) => {
                                e.stopPropagation();
                                deleteWorkflow(w.id);
                            };

                            selectionList.appendChild(card);
                        });
                    }
                }

                console.log(`✅ 已載入 ${workflows.length} 個流程`);
            } catch (error) {
                console.error('❌ 載入流程列表失敗:', error);
                const selectionList = document.getElementById('workflow-selection-list');
                if (selectionList) {
                    selectionList.innerHTML = '<div style="padding: 20px; color: var(--status-error); text-align: center;">載入失敗，請重新整理頁面</div>';
                }
            }
        }

        // 選擇流程 - 已棄用，直接使用 enterDesignMode()
        async function selectWorkflow(workflowId) {
            await enterDesignMode(workflowId);
        }

        // 刪除流程
        async function deleteWorkflow(workflowId) {
            // 直接刪除，不再確認

            try {
                const response = await fetch(`/api/workflows/data/templates/${workflowId}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    // 如果刪除的是當前流程，清空畫布並鎖定界面
                    if (workflowId === currentWorkflowId) {
                        currentWorkflowId = null;
                        cy.elements().remove();
                        lockInterface();
                    }

                    await loadWorkflowList();
                    updateStatus('流程已刪除');
                } else {
                    updateStatus('刪除流程失敗', 'warning');
                }
            } catch (error) {
                console.error('刪除流程失敗:', error);
                updateStatus('刪除流程失敗', 'warning');
            }
        }

        // 建立新流程
        async function createNewWorkflow() {
            const name = prompt('請輸入流程名稱：', '新流程');
            if (!name) return;

            try {
                console.log('🆕 開始建立新流程:', name);

                const response = await fetch('/api/workflows/data/templates', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: name,
                        description: ''
                    })
                });

                console.log('📡 後端回應狀態:', response.status);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const newWorkflow = await response.json();
                console.log('📦 新流程資料:', newWorkflow);

                // 後端可能返回 { success: true, workflow: {...} } 或直接返回 workflow
                const workflowData = newWorkflow.data || newWorkflow;
                console.log('  流程物件:', workflowData);
                console.log('  流程 ID:', workflowData.secure_code);

                // 進入設計模式
                await enterDesignMode(workflowData.secure_code);

                updateStatus(`✅ 已建立新流程：${name}`);
                console.log('✅ 新流程建立完成，已進入設計模式');
            } catch (error) {
                console.error('❌ 建立流程失敗:', error);
                console.error('錯誤堆疊:', error.stack);
                updateStatus('建立流程失敗：' + error.message, 'warning');
            }
        }

        // 防止重複建立流程的鎖
        let isCreatingWorkflow = false;

        // 從 URL 參數建立新流程並進入編輯模式
        async function createNewWorkflowAndEnter(name, categorySc, description) {
            // 防止重複調用
            if (isCreatingWorkflow) {
                console.log('⚠️ 已經在建立流程中，忽略重複調用');
                return;
            }

            isCreatingWorkflow = true;

            try {
                console.log('🆕 從 URL 建立新流程:', { name, category_secure_code: categorySc, description });

                const response = await fetch('/api/workflows/data/templates', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: name || '新流程',
                        category_secure_code: categorySc || '',
                        description: description || ''
                    })
                });

                console.log('📡 後端回應狀態:', response.status);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const newWorkflow = await response.json();
                console.log('📦 新流程資料:', newWorkflow);

                // 後端可能返回 { success: true, workflow: {...} } 或直接返回 workflow
                const workflowData = newWorkflow.data || newWorkflow;
                console.log('  流程物件:', workflowData);
                console.log('  流程 ID:', workflowData.secure_code);

                // 建立成功後，立即將 URL 改為編輯模式，防止重新整理時重複建立
                const newUrl = new URL(window.location.href);
                newUrl.searchParams.delete('new');
                newUrl.searchParams.delete('name');
                newUrl.searchParams.delete('category');
                newUrl.searchParams.delete('description');
                newUrl.searchParams.set('id', workflowData.secure_code);
                window.history.replaceState(null, '', newUrl);
                console.log('🔄 已更新 URL 為編輯模式:', newUrl.href);

                // 進入設計模式
                await enterDesignMode(workflowData.secure_code);

                // 後端已提供預設的 node-Start 和 node-End，不需要前端再添加
                console.log('✅ 已載入後端預設節點（node-Start, node-End）');

                updateStatus(`✅ 已建立新流程：${workflowData.name}`);
                console.log('✅ 新流程建立完成，已進入設計模式');
            } catch (error) {
                console.error('❌ 建立流程失敗:', error);
                console.error('錯誤堆疊:', error.stack);
                updateStatus('建立流程失敗：' + error.message, 'warning');
                // 失敗時重定向回列表頁
                window.location.href = '/forms/workflows';
            } finally {
                isCreatingWorkflow = false;
            }
        }

        // 載入流程
        async function loadWorkflow() {
            if (!currentWorkflowId) {
                cy.elements().remove();
                lockInterface();
                return;
            }

            // 切換流程時重置狀態
            clearUndoState();
            isReadOnly = false;
            // 移除上一個流程的唯讀提示與限制
            const prevWarning = document.getElementById('readonly-warning');
            if (prevWarning) prevWarning.remove();
            cy.autoungrabify(false);
            const nodeSettings = document.getElementById('nodeSettings');
            if (nodeSettings) {
                nodeSettings.style.pointerEvents = '';
                nodeSettings.style.opacity = '';
            }

            try {
                console.log(`📥 載入流程: ${currentWorkflowId}`);
                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const result = await response.json();
                console.log('📦 API 返回結果:', result);

                const workflow = result.data || result;
                console.log('📦 流程數據:', workflow);

                // 儲存到全域變數以供其他函數使用
                currentWorkflow = workflow;

                // 處理權限控制
                if (workflow._permissions) {
                    const perms = workflow._permissions;
                    console.log('🔐 權限資訊:', perms);

                    if (!perms.can_edit) {
                        // 沒有編輯權限：禁用儲存相關按鈕並顯示唯讀提示
                        const saveButtons = ['btn-save-workflow', 'btn-save-and-close', 'btn-save-new-version'];
                        saveButtons.forEach(id => {
                            const btn = document.getElementById(id);
                            if (btn) {
                                btn.disabled = true;
                                btn.classList.add('disabled');
                                btn.title = '您沒有編輯權限';
                                btn.style.opacity = '0.5';
                                btn.style.cursor = 'not-allowed';
                            }
                        });

                        // 在頂部顯示唯讀模式提示
                        const existingWarning = document.getElementById('readonly-warning');
                        if (!existingWarning) {
                            const toolbar = document.querySelector('.toolbar-row');
                            if (toolbar) {
                                const warning = document.createElement('div');
                                warning.id = 'readonly-warning';
                                warning.style.cssText = 'background: #fef3cd; border: 1px solid #ffc107; color: #856404; padding: 8px 16px; margin-bottom: 8px; border-radius: 4px; font-size: 13px;';
                                warning.innerHTML = '<i class="fas fa-lock" style="margin-right: 8px;"></i><strong>唯讀模式</strong> - 您只有檢視權限，無法編輯或儲存此工作流程。';
                                toolbar.parentNode.insertBefore(warning, toolbar);
                            }
                        }

                        console.log('🔒 唯讀模式已啟用');
                    }
                }

                // 通用子流程唯讀旗標（UI 在 unlockInterface 後套用）
                const urlParamsRO = new URLSearchParams(window.location.search);
                const isCommonSubflow = workflow.is_subprocess && !workflow.parent_workflow_secure_code;
                if (isCommonSubflow && urlParamsRO.get('editable') !== '1') {
                    isReadOnly = true;
                }

                // 檢查是否有cytoscape_config或graph（兼容舊資料）
                // 優先使用 cytoscape_config，如果沒有則使用 graph，都沒有則使用空配置
                let config = workflow.cytoscape_config || workflow.graph || { nodes: [], edges: [], relayPoints: [] };
                console.log('🎨 渲染配置:', config);
                console.log('  配置來源:', workflow.cytoscape_config ? 'cytoscape_config' : (workflow.graph ? 'graph' : '空配置'));

                renderWorkflow(config);

                // 新建流程（版本 AA 且未儲存過）自動適應視圖
                const ver = workflow.version || 'AA';
                const rev = workflow.revision || 0;
                if (ver === 'AA' && !rev) {
                    cy.fit(cy.elements(), 80);
                }

                updateStatus(`已載入流程：${workflow.name}`);

                // 解鎖界面並顯示流程資訊
                unlockInterface(workflow.name, (workflow.version || 'AA') + (workflow.revision || ''), workflow.description || '', workflow.category_secure_code || '');

                // 顯示建立者/最後編輯者
                const wfAuthorInfo = document.getElementById('wf-author-info');
                if (wfAuthorInfo) {
                    const infoParts = [];
                    if (workflow.created_by_name) {
                        infoParts.push('建立: ' + workflow.created_by_name);
                    }
                    if (workflow.updated_by_name) {
                        let updText = '編輯: ' + workflow.updated_by_name;
                        if (workflow.updated_at && typeof BkTime !== 'undefined') {
                            updText += ' (' + BkTime.format(workflow.updated_at, 'short') + ')';
                        }
                        infoParts.push(updText);
                    }
                    if (infoParts.length > 0) {
                        wfAuthorInfo.textContent = infoParts.join(' | ');
                        wfAuthorInfo.style.display = 'inline';
                    } else {
                        wfAuthorInfo.style.display = 'none';
                    }
                }

                // 通用子流程唯讀 UI（必須在 unlockInterface 之後，否則會被覆蓋）
                if (isReadOnly) {
                    // 禁用儲存按鈕
                    ['btn-save-workflow', 'btn-save-and-close', 'btn-save-new-version'].forEach(id => {
                        const btn = document.getElementById(id);
                        if (btn) {
                            btn.disabled = true;
                            btn.classList.add('disabled');
                            btn.title = '通用子流程唯讀，請從流程管理頁面開啟編輯';
                            btn.style.opacity = '0.5';
                            btn.style.cursor = 'not-allowed';
                        }
                    });
                    // 防止拖動節點
                    cy.autoungrabify(true);
                    // 禁用左側面板節點拖入
                    document.querySelectorAll('.palette-node').forEach(node => {
                        node.setAttribute('draggable', 'false');
                        node.style.opacity = '0.5';
                        node.style.cursor = 'default';
                    });
                    // 右側節點設定面板唯讀（可看不可改）
                    const nodeSettings = document.getElementById('nodeSettings');
                    if (nodeSettings) {
                        nodeSettings.style.pointerEvents = 'none';
                        nodeSettings.style.opacity = '0.55';
                    }
                    // 顯示唯讀提示
                    if (!document.getElementById('readonly-warning')) {
                        const toolbar = document.querySelector('.toolbar-row');
                        if (toolbar) {
                            const warning = document.createElement('div');
                            warning.id = 'readonly-warning';
                            warning.style.cssText = 'background: #e8f4fd; border: 1px solid #90caf9; color: #1565c0; padding: 6px 16px; margin-bottom: 8px; border-radius: 4px; font-size: 12px; display: flex; align-items: center; gap: 8px;';
                            warning.innerHTML = '<i class="fas fa-eye"></i><strong>唯讀模式</strong> — 通用子流程僅供檢視。如需編輯，請從<a href="/forms/workflows" style="color: #1565c0; margin-left: 2px;">流程管理</a>頁面開啟。';
                            toolbar.parentNode.insertBefore(warning, toolbar);
                        }
                    }
                    console.log('🔒 通用子流程唯讀模式已啟用');
                }

                // 初始化變更追蹤（載入完成後）
                setTimeout(() => {
                    initChangeTracking();
                    console.log('🔍 變更追蹤已初始化');
                }, 500);

                // 刷新流程樹
                refreshFlowTree();

                console.log('✅ 流程載入完成');
            } catch (error) {
                console.error('❌ 載入流程失敗:', error);
                updateStatus(`載入流程失敗：${error.message}\n\n請查看控制台了解詳細錯誤訊息`, 'warning');
                updateStatus('載入流程失敗');
                lockInterface();
            }
        }

        // 渲染流程圖
        function renderWorkflow(config) {
            console.log('🎨 開始渲染流程');
            console.log('  配置物件:', config);
            cy.elements().remove();

            // 安全檢查：確保config有必要的屬性
            if (!config) {
                console.warn('⚠️ 配置為空，使用空白畫布');
                return;
            }

            // 套用畫布設定（如果有的話）
            if (config.canvasSettings) {
                const settings = config.canvasSettings;
                console.log('🎨 套用畫布設定:', settings);

                // 套用背景顏色
                if (settings.backgroundColor) {
                    canvasBackgroundColor = settings.backgroundColor;
                    changeCanvasColor(settings.backgroundColor);
                }

                // 套用網格設定
                if (settings.gridEnabled !== undefined) gridEnabled = settings.gridEnabled;
                if (settings.gridStyle) gridStyle = settings.gridStyle;
                if (settings.gridSpacing) gridSpacing = settings.gridSpacing;

                // 同步更新 checkbox 狀態以符合載入的設定
                const gridLinesCheckbox = document.getElementById('grid-lines');
                const gridDotsCheckbox = document.getElementById('grid-dots');
                if (gridLinesCheckbox && gridDotsCheckbox) {
                    if (gridEnabled) {
                        gridLinesCheckbox.checked = (gridStyle === 'lines');
                        gridDotsCheckbox.checked = (gridStyle === 'dots');
                    } else {
                        gridLinesCheckbox.checked = false;
                        gridDotsCheckbox.checked = false;
                    }
                }

                // 套用圖紙設定
                if (settings.paperType) paperType = settings.paperType;
                if (settings.paperWidth) paperWidth = settings.paperWidth;
                if (settings.paperHeight) paperHeight = settings.paperHeight;

                // 套用底圖（新系統使用 backgroundId）
                if (settings.backgroundId) {
                    // 新的底圖系統：使用 background_id
                    const bg = availableBackgrounds.find(b => b.id === settings.backgroundId);
                    if (bg) {
                        selectBackground(bg.id, bg.url);
                    }
                } else if (settings.backgroundImage) {
                    // 舊系統相容：使用 base64 backgroundImage（已廢棄）
                    // 為了向後相容，暫時保留但不再更新狀態元素
                    console.warn('⚠️ 檢測到舊格式的底圖（base64），建議重新選擇底圖');
                }

                // 套用全域節點邊框設定
                if (settings.globalNodeBorder !== undefined) globalNodeBorder = settings.globalNodeBorder;

                // 重繪網格
                drawGridBackground();
            }

            // 載入欄位取值設定
            if (config.fieldReadConfig) {
                cy.data('fieldReadConfig', config.fieldReadConfig);
                console.log('📋 載入欄位取值設定:', config.fieldReadConfig);
            }

            let nodes = config.nodes || [];
            const edges = config.edges || [];
            const relayPoints = config.relayPoints || [];

            // ==================== Start/End 節點檢查與自動修復 ====================
            const startNodes = nodes.filter(n => n.type && n.type.toUpperCase() === 'START');
            const endNodes = nodes.filter(n => n.type && n.type.toUpperCase() === 'END');
            let repairMessages = [];

            // 檢查 Start 節點（必須恰好 1 個）
            if (startNodes.length === 0) {
                console.warn('⚠️ 流程缺少 Start 節點，自動補上');
                nodes.push({
                    id: 'node-Start',
                    label: 'Start',
                    type: 'Start',
                    icon: '/static/modules/form_workflow/icons/workflow/start.svg',
                    config: {},
                    description: '',
                    position: { x: -175, y: -50 }
                });
                repairMessages.push('自動補上 Start 節點');
            } else if (startNodes.length > 1) {
                console.warn(`⚠️ 流程有 ${startNodes.length} 個 Start 節點，僅保留第一個`);
                const firstStartId = startNodes[0].id;
                nodes = nodes.filter(n => !(n.type && n.type.toUpperCase() === 'START' && n.id !== firstStartId));
                repairMessages.push(`移除多餘的 Start 節點（原有 ${startNodes.length} 個）`);
            }

            // 檢查 End 節點（必須至少 1 個）
            if (endNodes.length === 0) {
                console.warn('⚠️ 流程缺少 End 節點，自動補上');
                nodes.push({
                    id: 'node-End',
                    label: 'End',
                    type: 'End',
                    icon: '/static/modules/form_workflow/icons/workflow/end.svg',
                    config: {},
                    description: '',
                    position: { x: 875, y: 350 }
                });
                repairMessages.push('自動補上 End 節點');
            }

            // 顯示修復訊息
            if (repairMessages.length > 0) {
                updateStatus(`⚠️ 流程結構已自動修復：\n${repairMessages.join('\n')}`, 'warning');
                // 標記為已變更，提醒用戶儲存
                setTimeout(() => {
                    hasUnsavedChanges = true;
                    updateSaveButtonState();
                }, 100);
            }
            // ==================== End of Start/End 檢查 ====================

            console.log('📊 渲染統計:');
            console.log(`  節點數: ${nodes.length}`);
            console.log(`  邊數: ${edges.length}`);
            console.log(`  中繼點數: ${relayPoints.length}`);

            // 渲染節點（分兩階段：先渲染群組，再渲染普通節點）
            console.log('🔷 開始渲染節點...');
            let successCount = 0;
            let failCount = 0;

            // 第一階段：渲染群組節點（支援舊資料：檢查 isGroup 或 type === 'group'）
            const groupNodes = nodes.filter(n => n.isGroup || n.type === 'group');
            const regularNodes = nodes.filter(n => !n.isGroup && n.type !== 'group');

            console.log(`  第一階段：渲染 ${groupNodes.length} 個群組節點`);
            groupNodes.forEach((node, index) => {
                try {
                    console.log(`  [${index + 1}/${groupNodes.length}] 渲染群組:`, node.id, node.label);

                    const groupData = {
                        id: node.id,
                        label: node.label ? node.label.replace('\\n', '\n') : '',
                        type: node.type || 'group',
                        borderStyle: node.borderStyle || 'dashed',
                        cornerStyle: node.cornerStyle || 'round'
                    };
                    // 恢復群組顏色
                    if (node.groupColor) {
                        groupData.groupColor = node.groupColor;
                    }

                    const groupNode = cy.add({
                        data: groupData,
                        position: node.position || { x: 0, y: 0 }
                    });

                    // 應用群組樣式
                    const borderStyle = node.borderStyle || 'dashed';
                    const cornerStyle = node.cornerStyle || 'round';
                    const gc = node.groupColor;

                    if (borderStyle === 'none') {
                        const styleObj = {
                            'border-width': 0,
                            'background-opacity': 0.3,
                            'shape': cornerStyle === 'round' ? 'roundrectangle' : 'rectangle'
                        };
                        if (gc) styleObj['background-color'] = `rgb(${gc.r}, ${gc.g}, ${gc.b})`;
                        groupNode.style(styleObj);
                    } else {
                        const styleObj = {
                            'border-width': 2,
                            'border-style': borderStyle,
                            'background-opacity': 0.15,
                            'shape': cornerStyle === 'round' ? 'roundrectangle' : 'rectangle'
                        };
                        if (gc) {
                            styleObj['background-color'] = `rgb(${gc.r}, ${gc.g}, ${gc.b})`;
                            styleObj['border-color'] = groupBorderColor(gc.r, gc.g, gc.b);
                        }
                        groupNode.style(styleObj);
                    }

                    successCount++;
                    console.log(`    ✅ 群組 ${node.id} 渲染成功`);
                } catch (err) {
                    failCount++;
                    console.error(`    ❌ 群組 ${node.id} 渲染失敗:`, err);
                }
            });

            // 第二階段：渲染普通節點
            console.log(`  第二階段：渲染 ${regularNodes.length} 個普通節點`);
            regularNodes.forEach((node, index) => {
                try {
                    console.log(`  [${index + 1}/${regularNodes.length}] 渲染節點:`, {
                        id: node.id,
                        type: node.type,
                        label: node.label,
                        parent: node.parent || '(無)'
                    });

                    // 取得圖示 URL（支援本地 SVG 路徑和 Font Awesome class）
                    let iconUrl = node.iconUrl || '';
                    if (!iconUrl && node.icon) {
                        if (node.icon.startsWith('/static/') || node.icon.startsWith('http')) {
                            // 已經是 URL 路徑，直接使用
                            iconUrl = node.icon;
                        } else {
                            // 舊的 Font Awesome class，使用舊方法轉換（向後兼容）
                            iconUrl = getSvgDataUrl(node.icon, '#333333');
                        }
                    }

                    const nodeData = {
                        id: node.id,
                        label: node.label ? node.label.replace('\\n', '\n') : '',
                        type: normalizeNodeType(node.type),
                        config: node.config || {},
                        icon: node.icon || '',
                        iconUrl: iconUrl,
                        description: node.description || ''
                    };

                    // End 節點：從 config 恢復 finishMode 供 CSS selector 變色
                    if (nodeData.type === 'End' && node.config && node.config.finish_mode) {
                        nodeData.finishMode = node.config.finish_mode;
                    }

                    // Subflow 節點：從 config 恢復 subflowKind 供 CSS selector 變色
                    if (nodeData.type === 'Subflow' && node.config && node.config.subflowKind) {
                        nodeData.subflowKind = node.config.subflowKind;
                    }

                    // 如果節點有父群組，設定父子關係
                    if (node.parent) {
                        nodeData.parent = node.parent;
                    }

                    const addedNode = cy.add({
                        data: nodeData,
                        position: node.position || { x: 0, y: 0 }
                    });

                    // 套用圖示背景
                    if (iconUrl) {
                        addedNode.style({
                            'background-image': iconUrl,
                            'background-fit': 'contain',
                            'background-clip': 'none'
                        });
                    }

                    successCount++;
                    console.log(`    ✅ 節點 ${node.id} 渲染成功`);
                } catch (err) {
                    failCount++;
                    console.error(`    ❌ 節點 ${node.id} 渲染失敗:`, err);
                }
            });

            console.log(`✅ 節點渲染完成: ${successCount} 成功, ${failCount} 失敗`);

            // 渲染邊
            console.log('🔗 開始渲染邊...');
            let edgeSuccessCount = 0;
            let edgeFailCount = 0;

            edges.forEach((edge, index) => {
                try {
                    console.log(`  [${index + 1}/${edges.length}] 渲染邊:`, {
                        id: edge.id,
                        source: edge.source,
                        target: edge.target,
                        label: edge.label
                    });

                    const edgeDataObj = {
                        id: edge.id,
                        source: edge.source,
                        target: edge.target,
                        label: edge.label || ''
                    };

                    // 恢復正交折線狀態
                    if (edge.orthogonalEnabled) {
                        edgeDataObj.orthogonalEnabled = true;
                        edgeDataObj.orthogonalDirection = edge.orthogonalDirection || 'auto';
                    }

                    const edgeElement = cy.add({ data: edgeDataObj });

                    // 如果有保存的樣式，應用它們（正交邊跳過，樣式由重建處理）
                    if (edge.style && !edge.orthogonalEnabled) {
                        edgeElement.style(edge.style);
                    }
                    edgeSuccessCount++;
                    console.log(`    ✅ 邊 ${edge.id} 渲染成功`);
                } catch (err) {
                    edgeFailCount++;
                    console.error(`    ❌ 邊 ${edge.id} 渲染失敗:`, err);
                }
            });

            console.log(`✅ 邊渲染完成: ${edgeSuccessCount} 成功, ${edgeFailCount} 失敗`);

            // 載入中繼點（如果有的話）
            if (relayPoints && relayPoints.length > 0) {
                relayCounter = relayPoints.length;
                relayPoints.forEach(relay => {
                    const nodeData = {
                        id: relay.id,
                        type: 'relay',
                        parentEdge: relay.parentEdge
                    };

                    // 恢復 taxiControl 標記
                    if (relay.taxiControl) {
                        nodeData.taxiControl = true;
                    }

                    // 恢復 yellowControl 標記
                    if (relay.yellowControl) {
                        nodeData.yellowControl = true;
                        nodeData.pointType = relay.pointType; // 'nearStar' or 'corner'
                    }

                    // 恢復 orthogonalControl 標記
                    if (relay.orthogonalControl) {
                        nodeData.orthogonalControl = true;
                        nodeData.pointIndex = relay.pointIndex;
                    }

                    cy.add({
                        data: nodeData,
                        position: relay.position
                    });

                    // 如果是 taxi 控制點，加入到控制點映射中
                    if (relay.taxiControl) {
                        const parentEdgeId = relay.parentEdge;
                        if (!taxiControlPoints.has(parentEdgeId)) {
                            taxiControlPoints.set(parentEdgeId, []);
                        }
                        // 稍後在重建後更新
                    }

                    // 如果是 yellow 控制點，加入到控制點映射中
                    if (relay.yellowControl) {
                        const parentEdgeId = relay.parentEdge;
                        if (!yellowControlPoints.has(parentEdgeId)) {
                            yellowControlPoints.set(parentEdgeId, []);
                        }
                        // 稍後在重建後更新
                    }
                });

                // 重建包含中繼點的線段
                config.edges.forEach(edge => {
                    if (edge.hasRelays) {
                        const originalEdge = cy.getElementById(edge.id);
                        originalEdge.data('originalSource', edge.source);
                        originalEdge.data('originalTarget', edge.target);

                        if (edge.orthogonalEnabled) {
                            // 正交折線：重建 5 段線和 Map
                            rebuildOrthogonalFromSaved(originalEdge);
                        } else {
                            rebuildEdgeWithRelays(originalEdge);

                            // 更新 taxiControlPoints 映射
                            const relayNodes = getRelayPointsForEdge(edge.id);
                            const taxiControls = relayNodes.filter(n => n.data('taxiControl'));
                            if (taxiControls.length > 0) {
                                taxiControlPoints.set(edge.id, taxiControls);
                            }

                            // 更新 yellowControlPoints 映射
                            const yellowControls = relayNodes.filter(n => n.data('yellowControl'));
                            if (yellowControls.length > 0) {
                                yellowControlPoints.set(edge.id, yellowControls);
                            }
                        }
                    }
                });
            }

            // 判斷是否為新檔案（只有預設的開始/結束節點或完全空白）
            const isNewWorkflow = nodes.length === 0 || (nodes.length === 2 &&
                nodes.some(n => n.type && n.type.toLowerCase() === 'start') &&
                nodes.some(n => n.type && n.type.toLowerCase() === 'end') &&
                edges.length === 0);

            if (isNewWorkflow) {
                // 新檔案：設定 zoom 為 125% (1.25)
                cy.zoom(1.25);
                cy.center();
                console.log('🆕 新工作流程，zoom 設為 125%');
            } else {
                // 現有檔案：設定 zoom 為 125% (1.25)
                cy.zoom(1.25);
                cy.center();
                console.log('📂 現有工作流程，zoom 設為 125%');
            }

            // 更新線段選擇器
            updateEdgeSelector();

            // 更新計數器，避免 ID 衝突
            // 找出最大的節點 ID 數字
            let maxNodeNum = 0;
            cy.nodes('[type!="relay"]').forEach(node => {
                // 匹配兩種格式：node-數字 或 node-類型-數字
                const match = node.id().match(/^node-.*?-?(\d+)$/) || node.id().match(/^node_(\d+)$/);
                if (match) {
                    maxNodeNum = Math.max(maxNodeNum, parseInt(match[1]));
                }
            });
            nodeCounter = maxNodeNum;

            // 找出最大的邊 ID 數字
            let maxEdgeNum = 0;
            cy.edges().forEach(edge => {
                const match = edge.id().match(/^edge-(\d+)$/);
                if (match) {
                    maxEdgeNum = Math.max(maxEdgeNum, parseInt(match[1]));
                }
            });
            edgeCounter = maxEdgeNum;

            // 找出最大的群組 ID 數字（包括 type='group' 的節點）
            let maxGroupNum = 0;
            cy.nodes().forEach(node => {
                // 檢查是否為群組
                if (isGroupNode(node)) {
                    const match = node.id().match(/^group_(\d+)$/);
                    if (match) {
                        maxGroupNum = Math.max(maxGroupNum, parseInt(match[1]));
                    }
                }
            });
            groupCounter = maxGroupNum;
            console.log(`  📊 更新群組計數器: groupCounter = ${groupCounter}`);

            // 初始化網格佔用映射
            updateGridOccupancy();

            // 套用全域邊框設定（使用 class，不用 bypass style）
            if (!globalNodeBorder) {
                cy.nodes('[type!="relay"][type!="paper"]').forEach(node => {
                    if (!isGroupNode(node)) node.addClass('no-border');
                });
            }
            const borderCheckbox = document.getElementById('global-node-border');
            if (borderCheckbox) borderCheckbox.checked = globalNodeBorder;

            // 載入後掃描空群組，強制虛線邊框
            refreshAllEmptyGroups();

            console.log(`✅ 渲染完成 (nodeCounter=${nodeCounter}, edgeCounter=${edgeCounter}, groupCounter=${groupCounter})`);
        }

        // 節點類型標準化（支援舊的大寫名稱和新的 PascalCase）
        function normalizeNodeType(type) {
            if (!type) return type;
            // key 全部 lowercase，value 為 JS 標準 PascalCase
            // 涵蓋 DB (ALL_CAPS)、API (PascalCase)、底線變體，統一輸出
            const typeMap = {
                'start': 'Start',
                'end': 'End',
                'formadapter': 'FormAdapter',
                'approve': 'FormAdapter',       // DB: APPROVE → 對應 FormAdapter
                'delay': 'Delay',
                'branch': 'Branch',
                'condition': 'Condition',
                'switch': 'Switch',
                'converge': 'Converge',
                'parallelfork': 'ParallelFork',
                'parallel_fork': 'ParallelFork',
                'paralleljoin': 'ParallelJoin',
                'parallel_join': 'ParallelJoin',
                'subflow': 'Subflow',
                'telegram': 'Telegram',
                'emailadapter': 'EmailAdapter',
                'opset': 'OpSet',
                'opfieldread': 'OpFieldRead',
                'op_fieldread': 'OpFieldRead',
                'opfieldwrite': 'OpFieldWrite',
                'op_fieldwrite': 'OpFieldWrite',
                'emailrelay': 'EmailRelay',
                'sqlexecutor': 'SqlExecutor',
                'sys_telegram': 'SysTelegram',
                'systelegram': 'SysTelegram',
                'abandon': 'Abandon',
                'navbarbroadcast': 'NavbarBroadcast',
                'navbar_broadcast': 'NavbarBroadcast',
                'alertbroadcast': 'AlertBroadcast',
                'alert_broadcast': 'AlertBroadcast',
            };
            return typeMap[type.toLowerCase()] || type;
        }

