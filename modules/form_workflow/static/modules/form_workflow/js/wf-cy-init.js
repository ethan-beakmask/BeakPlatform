/**
 * wf-cy-init.js -- Cytoscape 初始化、樣式定義、修飾鍵監聽
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js (全域變數)
 */


        // 監聯修飾鍵
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Shift' && !shiftPressed) {
                shiftPressed = true;
                document.getElementById('mode-indicator').classList.add('active');
                updateStatus(__('Shift 模式：圈選節點 / 連續畫線'));

                // Shift 模式：禁止線條被選中
                if (cy) {
                    cy.edges().unselectify();
                }
            }
            if (e.key === 'Control' && !ctrlPressed) {
                ctrlPressed = true;
                updateStatus(__('Ctrl 模式：圈選線條 / 編輯折線'));

                // Ctrl 模式：禁止節點被選中
                if (cy) {
                    cy.nodes('[type != "relay"]').unselectify();
                }
            }
            if (e.key === 'Alt' && !altPressed) {
                altPressed = true;
                updateStatus(__('Alt 模式：框選所有元素 / 拖動脫離群組'));

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
                    updateStatus(__('連續畫線模式已結束'));
                } else {
                    updateStatus(__('Shift 模式已關閉'));
                }
            }
            if (e.key === 'Control') {
                ctrlPressed = false;

                // 恢復節點可被選中
                if (cy) {
                    cy.nodes().selectify();
                }

                updateStatus(__('Ctrl 模式已關閉'));
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

                updateStatus(__('Alt 模式已關閉'));
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
                        // 系統級管理員專用節點：桃紅方形
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
