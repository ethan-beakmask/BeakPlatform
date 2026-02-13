        // 全域變數 (window.orgCode 在 HTML 中注入)

        let cy;
        let currentWorkflowId = null;
        let nodeCounter = 0;
        let edgeCounter = 0;
        let isConnectingMode = false;
        let connectingSourceNode = null;
        let shiftPressed = false;
        let ctrlPressed = false;
        let altPressed = false;
        let selectedEdge = null;
        let relayCounter = 0;

        // 連續畫線模式相關變數
        let continuousLineMode = false;
        let continuousLineNodes = [];  // 儲存連續畫線的節點序列
        let nodePressedForDrag = null;  // 記錄按下的節點（用於區分畫線/拖動）
        let hasMoved = false;  // 是否已經開始拖動
        let alreadyLeftGroup = false;  // 是否已經脫離群組（避免重複處理）

        // 動畫相關變數
        let animationIntervals = [];
        let flowAnimationEnabled = false;
        let pulseAnimationEnabled = false;
        let animationSpeed = 1.0;

        // 線段屬性控制相關變數
        let currentSelectedEdge = null;  // 當前選中用於屬性控制的線段

        // Taxi 控制點相關變數
        let taxiControlCounter = 0;
        let taxiControlPoints = new Map();  // edgeId -> [controlPoint1, controlPoint2, ...]

        // 正交折線相關變數
        let orthogonalControlPoints = new Map();  // edgeId -> { points: [{x,y}, ...], segments: [...] }
        let orthogonalDragging = null;  // { edgeId, segmentIndex, isHorizontal, startPos }

        // 網格對齊相關變數
        let gridEnabled = true;
        let gridSpacing = 25;
        let gridStyle = 'dots'; // 'lines' 或 'dots' - 預設為 dots 以符合 HTML checkbox 的初始狀態

        // 畫布設定
        let canvasBackgroundColor = '#fafafa';
        // let canvasBackgroundImage = null; // 已廢棄：舊系統使用 base64，新系統使用 currentBackgroundUrl
        let globalNodeBorder = true; // 全域節點邊框設定

        // 圖紙設定
        let paperType = 'none';
        let paperWidth = 0;
        let paperHeight = 0;

        // 網格佔用映射（用於嚴格定位模式）
        // key: "x,y" (網格座標), value: node.id()
        let gridOccupancy = new Map();

        // 流程樹相關變數
        let rootWorkflowId = null;  // 根主流程 ID（永遠不變）
        let rootWorkflowName = null;  // 根主流程名稱

        // 表單欄位分頁相關變數
        let formFieldsLoaded = false;  // 是否已載入過配對表單
        let currentMappedForms = [];   // 當前配對的表單列表
        let currentFormFields = [];    // 當前表單的欄位列表
        let selectedFormId = null;     // 當前選中的表單 ID
        let selectedFormSecureCode = '';  // 當前選中的表單 secure_code
        let currentVersionType = 'design';  // 當前版本類型 (design/published)
        let variableMapping = null;    // 變數映射表（新式變數 <-> 舊式變數）
        let currentEditingNodeId = null;   // 當前開啟設定面板的節點 ID
        let currentEditingNodeType = null; // 當前開啟設定面板的節點類型

        // ==================== 群組 Helper ====================
        function isGroupNode(node) {
            return node.isParent() || node.data('type') === 'group';
        }

        // 群組顏色色盤（30色，6排5列）
        const GROUP_COLORS = [
            // Row 1: 紅橙黃系
            { r: 200, g: 80, b: 80, label: '紅' },
            { r: 200, g: 120, b: 60, label: '橙紅' },
            { r: 200, g: 160, b: 50, label: '橙' },
            { r: 200, g: 190, b: 50, label: '金黃' },
            { r: 180, g: 200, b: 50, label: '黃綠' },
            // Row 2: 綠系
            { r: 100, g: 200, b: 80, label: '亮綠' },
            { r: 60, g: 180, b: 100, label: '翠綠' },
            { r: 50, g: 180, b: 140, label: '薄荷' },
            { r: 50, g: 175, b: 175, label: '青' },
            { r: 60, g: 160, b: 200, label: '湖藍' },
            // Row 3: 藍紫系
            { r: 80, g: 130, b: 200, label: '天藍' },
            { r: 100, g: 100, b: 200, label: '藍' },
            { r: 120, g: 80, b: 200, label: '靛藍' },
            { r: 150, g: 70, b: 200, label: '紫' },
            { r: 180, g: 60, b: 190, label: '洋紫' },
            // Row 4: 粉棕系
            { r: 200, g: 60, b: 160, label: '桃粉' },
            { r: 200, g: 80, b: 120, label: '玫瑰' },
            { r: 200, g: 100, b: 100, label: '珊瑚' },
            { r: 180, g: 120, b: 90, label: '棕' },
            { r: 160, g: 140, b: 80, label: '橄欖' },
            // Row 5: 淡色系
            { r: 160, g: 180, b: 200, label: '淡藍' },
            { r: 180, g: 200, b: 180, label: '淡綠' },
            { r: 200, g: 180, b: 160, label: '淡橙' },
            { r: 200, g: 160, b: 180, label: '淡粉' },
            { r: 180, g: 170, b: 200, label: '淡紫' },
            // Row 6: 灰系
            { r: 180, g: 180, b: 180, label: '淺灰' },
            { r: 140, g: 140, b: 140, label: '灰' },
            { r: 100, g: 100, b: 100, label: '深灰' },
            { r: 140, g: 160, b: 170, label: '藍灰' },
            { r: 160, g: 150, b: 140, label: '暖灰' },
        ];

        // 根據群組顏色計算邊框色
        function groupBorderColor(r, g, b) {
            return `rgb(130, ${Math.round(g * 0.7)}, ${b})`;
        }

        // 套用群組顏色
        function applyGroupColor(node, colorObj) {
            if (!colorObj) return;
            const { r, g, b } = colorObj;
            node.data('groupColor', { r, g, b });
            node.style('background-color', `rgb(${r}, ${g}, ${b})`);

            // 如果有邊框，同步更新邊框色
            const borderWidth = node.numericStyle('border-width');
            if (borderWidth > 0) {
                node.style('border-color', groupBorderColor(r, g, b));
            }

            updateGroupSettingsPanel();
            updateMinimap();
        }

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
                updateStatus('沒有可復原的操作', 'warning');
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

            cy.style().update();
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
        // ==================== Undo 系統結束 ====================

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
                                    // 刪除群組時，先將 Start 節點移出群組
                                    const children = elem.children();
                                    children.forEach(child => {
                                        const childType = child.data('type');
                                        const childId = child.data('id');
                                        if (childId === 'node-Start' || childType === 'Start') {
                                            child.move({ parent: null });
                                            updateStatus('Start 節點已自動移出群組', 'info');
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

                    // 更新群組資訊顯示
                    updateGroupInfoDisplay();
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

            saveBtn.removeAttribute('disabled');
            saveAndCloseBtn.removeAttribute('disabled');
            if (saveNewVersionBtn) saveNewVersionBtn.removeAttribute('disabled');
            discardBtn.removeAttribute('disabled');
            console.log('  ✓ 顯示操作按鈕並啟用');

            // 顯示流程資訊
            document.getElementById('workflow-info').style.display = 'block';
            document.getElementById('current-workflow-name').value = workflowName || '未命名流程';
            document.getElementById('current-workflow-version').textContent = workflowVersion ? `版本 ${workflowVersion}` : 'v1.0';
            const categorySelect = document.getElementById('current-workflow-category');
            if (categorySelect) {
                categorySelect.value = workflowCategory || '';
            }
            document.getElementById('current-workflow-description').value = workflowDescription || '';
            console.log('  ✓ 更新流程資訊顯示');
        }

        // 更新流程名稱和描述
        async function updateWorkflowInfo() {
            if (!currentWorkflowId) return;

            const nameInput = document.getElementById('current-workflow-name');
            const descInput = document.getElementById('current-workflow-description');
            const categoryInput = document.getElementById('current-workflow-category');
            const newName = nameInput.value.trim();
            const newDescription = descInput.value.trim();
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
                descInput.value = currentWorkflow?.description || '';
                if (categoryInput) categoryInput.value = currentWorkflow?.category_secure_code || '';
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
                    description: document.getElementById('current-workflow-description')?.value
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
                            const createdDate = w.created_at ? new Date(w.created_at).toLocaleDateString('zh-TW', {
                                year: 'numeric',
                                month: '2-digit',
                                day: '2-digit'
                            }) : '未知';

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

            // 切換流程時清除 undo stack
            clearUndoState();

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

                // 檢查是否有cytoscape_config或graph（兼容舊資料）
                // 優先使用 cytoscape_config，如果沒有則使用 graph，都沒有則使用空配置
                let config = workflow.cytoscape_config || workflow.graph || { nodes: [], edges: [], relayPoints: [] };
                console.log('🎨 渲染配置:', config);
                console.log('  配置來源:', workflow.cytoscape_config ? 'cytoscape_config' : (workflow.graph ? 'graph' : '空配置'));

                renderWorkflow(config);
                updateStatus(`已載入流程：${workflow.name}`);

                // 解鎖界面並顯示流程資訊
                unlockInterface(workflow.name, (workflow.version || 'AA') + (workflow.revision || ''), workflow.description || '', workflow.category_secure_code || '');

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

                    const edgeElement = cy.add({
                        data: {
                            id: edge.id,
                            source: edge.source,
                            target: edge.target,
                            label: edge.label || ''
                        }
                    });

                    // 如果有保存的樣式，應用它們
                    if (edge.style) {
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
                'notification': 'Notification',
                'telegram': 'Telegram',
                'emailadapter': 'EmailAdapter',
                'opset': 'OpSet',
                'opfieldread': 'OpFieldRead',
                'op_fieldread': 'OpFieldRead',
                'opfieldwrite': 'OpFieldWrite',
                'op_fieldwrite': 'OpFieldWrite',
                'formexp': 'FormExp',
                'emailrelay': 'EmailRelay',
                'sqlexecutor': 'SqlExecutor',
                'sys_telegram': 'SysTelegram',
                'systelegram': 'SysTelegram',
                'abandon': 'Abandon',
            };
            return typeMap[type.toLowerCase()] || type;
        }

        // 顯示節點資訊
        function showNodeInfo(node) {
            // 切換節點前，先自動套用前一個面板的設定
            autoApplyCurrentPanel();

            const rawType = node.data('type');
            const type = normalizeNodeType(rawType);  // 標準化節點類型
            const label = node.data('label');
            const nodeId = node.id();

            // 追蹤當前編輯的節點
            currentEditingNodeId = nodeId;
            currentEditingNodeType = type;

            // 隱藏線段編輯面板，顯示節點設定
            document.getElementById('edge-editing-panel').style.display = 'none';
            document.getElementById('edge-control-panel').style.display = 'none';
            document.getElementById('nodeSettings').style.display = 'block';

            // OP_FIELDREAD / OP_FIELDWRITE 節點：自動切換到表單欄位分頁並展開面板
            if (type === 'OpFieldRead' || type === 'OpFieldWrite') {
                // 切換到表單欄位分頁
                switchTab('formfields');
                // 如果面板未展開，展開它
                if (!isPanelExpanded) {
                    toggleControlPanel();
                }
                // 如果表單欄位尚未載入，且只有一張配對表單，自動載入它
                if (currentFormFields.length === 0 && currentMappedForms.length === 1) {
                    selectForm(currentMappedForms[0]);
                }
            }

            // OpSet 節點：自動切換到 OPSET 變數分頁並展開面板
            if (type === 'OpSet') {
                switchTab('opsetvars');
                if (!isPanelExpanded) {
                    toggleControlPanel();
                }
                // 自動掃描 OPSET 變數
                setTimeout(() => reloadOpsetVars(), 100);
            }

            const typeNames = {
                // 標準命名（依 workflow_node_definitions 表）
                'Start': '開始節點',
                'End': '結束節點',
                'Switch': '條件分支',
                'Subflow': '子流程',
                'Converge': '匯聚節點',
                'Delay': '暫停',
                'OpSet': '設定變數',
                'FormExp': '表單過期',
                'FormAdapter': '簽核',
                'EmailAdapter': '郵件通知',
                'SQLExecutor': 'SQL 執行器',
                'Abandon': '放棄流程',
                'Telegram': 'Telegram 通知',
                'EmailRelay': '系統郵件'
            };

            const description = node.data('description') || '';

            // 有額外設定的節點類型（這些節點有自己的「套用」按鈕）
            const nodesWithSettings = [
                'Subflow', 'Delay', 'OpFieldWrite', 'OpSet', 'Telegram',
                'SysTelegram', 'EmailRelay', 'EmailAdapter', 'Branch',
                'FormAdapter', 'End', 'Converge', 'SqlExecutor'
            ];
            const hasAdditionalSettings = nodesWithSettings.includes(type);

            let info = `
                <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                        <label style="font-size: 11px; color: #666; white-space: nowrap;">名稱</label>
                        <input type="text" id="node-label-input" value="${label}"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;"
                               placeholder="節點名稱">
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <label style="font-size: 11px; color: #666; white-space: nowrap;">描述</label>
                        <input type="text" id="node-description-input" value="${description}"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;"
                               placeholder="選填">
                    </div>
                    ${!hasAdditionalSettings ? `
                    <button class="btn-primary" onclick="applyNodeBasicInfo('${nodeId}')" style="width: 100%; margin-top: 8px; padding: 5px; font-size: 11px;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                    ` : ''}
                </div>
            `;

            // 子流程節點配置
            if (type === 'Subflow') {
                const currentConfig = node.data('config') || {};
                const currentChildFlowId = currentConfig.childFlowId || '';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-sitemap"></i> 子流程說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">子流程節點可以呼叫其他已定義的工作流程，實現模組化設計和流程重用。</p>

                            <strong style="color: #333;">特性：</strong>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>變數自動共享：子流程與主流程共用變數</li>
                                <li>專屬綁定：子流程專屬於當前主流程</li>
                                <li>遞迴限制：最多支援 5 層嵌套</li>
                            </ul>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 子流程配置
                        </h4>
                        <div style="margin-bottom: 15px;">
                            <strong>選擇子流程：</strong><br>
                            <select id="childFlowSelect" onchange="if(this.value) applySubprocessConfig('${nodeId}')" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                                <option value="">載入中...</option>
                            </select>
                            <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                <i class="fas fa-info-circle"></i> 只顯示可用的子流程
                            </p>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <button class="btn-secondary" onclick="createNewSubflow('${nodeId}')" style="width: 100%;">
                                <i class="fas fa-plus"></i> 建立新子流程
                            </button>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-exchange-alt"></i> 參數映射（選填）
                        </h4>
                        <p style="font-size: 12px; color: #666; margin-bottom: 15px;">
                            為共用子流程配置變數映射，專屬子流程會自動共享變數無需配置。
                        </p>

                        <div style="margin-bottom: 20px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                <strong style="font-size: 13px;">輸入參數（父流程 → 子流程）</strong>
                                <button onclick="addInputMapping('${nodeId}')" style="padding: 4px 10px; font-size: 11px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                    <i class="fas fa-plus"></i> 添加
                                </button>
                            </div>
                            <div id="inputMappingContainer" style="border: 1px solid #e5e7eb; border-radius: 4px; max-height: 200px; overflow-y: auto;">
                                <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                                    <thead style="background: #f9fafb; position: sticky; top: 0;">
                                        <tr>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">父流程變數</th>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">子流程變數</th>
                                            <th style="padding: 8px; text-align: center; border-bottom: 1px solid #e5e7eb; width: 60px;">操作</th>
                                        </tr>
                                    </thead>
                                    <tbody id="inputMappingTable">
                                        <tr>
                                            <td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div style="margin-bottom: 15px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                <strong style="font-size: 13px;">輸出參數（子流程 → 父流程）</strong>
                                <button onclick="addOutputMapping('${nodeId}')" style="padding: 4px 10px; font-size: 11px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                    <i class="fas fa-plus"></i> 添加
                                </button>
                            </div>
                            <div id="outputMappingContainer" style="border: 1px solid #e5e7eb; border-radius: 4px; max-height: 200px; overflow-y: auto;">
                                <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                                    <thead style="background: #f9fafb; position: sticky; top: 0;">
                                        <tr>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">子流程變數</th>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">父流程變數</th>
                                            <th style="padding: 8px; text-align: center; border-bottom: 1px solid #e5e7eb; width: 60px;">操作</th>
                                        </tr>
                                    </thead>
                                    <tbody id="outputMappingTable">
                                        <tr>
                                            <td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applySubprocessConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // 匯聚節點配置
            if (type === 'Converge') {
                const currentConfig = node.data('config') || {};
                const currentMode = currentConfig.mode || 'ALL';
                const isAnyMode = currentMode === 'ANY';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-compress-arrows-alt"></i> 匯聚節點說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">等待多條前驅路徑完成後匯聚，可選擇等待全部或任一完成。</p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 匯聚模式
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; border: 2px solid ${!isAnyMode ? '#9C27B0' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${!isAnyMode ? '#F3E5F5' : 'white'};">
                                <input type="radio" name="convergeMode" value="ALL" ${!isAnyMode ? 'checked' : ''}
                                       onchange="updateConvergeMode('${nodeId}', 'ALL')"
                                       style="margin-right: 12px; transform: scale(1.2);">
                                <div>
                                    <div style="font-weight: bold; color: #7B1FA2;">
                                        <i class="fas fa-users"></i> 等待全部 (ALL)
                                    </div>
                                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                                        等待所有前驅節點完成後才繼續下一步
                                    </div>
                                </div>
                            </label>
                            <label style="display: flex; align-items: center; padding: 12px; border: 2px solid ${isAnyMode ? '#FF9800' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${isAnyMode ? '#FFF3E0' : 'white'};">
                                <input type="radio" name="convergeMode" value="ANY" ${isAnyMode ? 'checked' : ''}
                                       onchange="updateConvergeMode('${nodeId}', 'ANY')"
                                       style="margin-right: 12px; transform: scale(1.2);">
                                <div>
                                    <div style="font-weight: bold; color: #F57C00;">
                                        <i class="fas fa-user"></i> 任一完成 (ANY)
                                    </div>
                                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                                        任一前驅節點完成就繼續下一步
                                    </div>
                                </div>
                            </label>
                        </div>
                        <p style="font-size: 11px; color: #999; margin-top: 15px;">
                            <i class="fas fa-info-circle"></i> 節點顏色會根據模式自動變更：紫色=等待全部，橘色=任一完成
                        </p>
                    </div>
                `;
            }

            // Delay 暫停節點配置
            if (type === 'Delay') {
                const currentConfig = node.data('config') || {};
                const delaySeconds = currentConfig.delay_seconds || 60;

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-clock"></i> 暫停節點說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">暫停節點會讓流程等待指定的秒數後再繼續執行下一個節點。</p>
                            <p style="margin: 10px 0;">適用場景：</p>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>等待外部系統處理完成</li>
                                <li>控制 API 呼叫頻率</li>
                                <li>排程延遲執行</li>
                            </ul>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 延遲設定
                        </h4>
                        <div style="margin-bottom: 15px;">
                            <strong>延遲秒數：</strong><br>
                            <input type="number" id="delaySeconds" value="${delaySeconds}"
                                   min="0" max="86400"
                                   style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                            <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                <i class="fas fa-info-circle"></i> 最大 86400 秒（24 小時）
                            </p>
                        </div>
                        <div style="background: #f5f5f5; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                            <div style="font-size: 12px; color: #666;">
                                <strong>換算：</strong>
                                <span id="delayTimeDisplay">${Math.floor(delaySeconds/3600)}小時 ${Math.floor((delaySeconds%3600)/60)}分 ${delaySeconds%60}秒</span>
                            </div>
                        </div>
                        <button class="btn-primary" onclick="applyDelayConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // SqlExecutor SQL 查詢節點配置
            if (type === 'SqlExecutor') {
                const currentConfig = node.data('config') || {};
                const queryType = currentConfig.query_type || '';
                const resultVar = currentConfig.result_var || '';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #4a90a4;">
                            <i class="fas fa-database"></i> SQL 查詢說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">此節點執行預定義的安全 SQL 查詢，自動依據表單發動者的企業進行資料隔離。</p>
                            <p style="margin: 10px 0; padding: 8px; background: #e8f5e9; border-radius: 4px;">
                                <i class="fas fa-shield-alt" style="color: #4caf50;"></i>
                                <strong>安全機制：</strong>org_secure_code 會自動注入，確保只能查詢同企業的資料。
                            </p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #4a90a4;">
                            <i class="fas fa-cog"></i> 查詢設定
                        </h4>
                        <div style="margin-bottom: 15px;">
                            <strong>查詢類型：</strong><br>
                            <select id="sqlQueryType" onchange="updateSQLQueryDescription()" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                                <option value="">請選擇查詢類型...</option>
                                <option value="get_org_users" ${queryType === 'get_org_users' ? 'selected' : ''}>取得企業用戶清單</option>
                                <option value="get_org_user_count" ${queryType === 'get_org_user_count' ? 'selected' : ''}>取得企業用戶數量</option>
                                <option value="get_org_active_users" ${queryType === 'get_org_active_users' ? 'selected' : ''}>取得企業活躍用戶</option>
                            </select>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <strong>結果變數：</strong><br>
                            <input type="text" id="sqlResultVar" value="${resultVar}" placeholder="例：user_list"
                                   style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px; box-sizing: border-box;">
                            <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                <i class="fas fa-info-circle"></i> 查詢結果將存入此變數，可在後續節點使用 \${變數名} 引用
                            </p>
                        </div>
                        <div id="sqlPreviewArea" style="background: #f5f5f5; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 12px;">
                            <strong>查詢說明：</strong>
                            <div id="sqlQueryDescription" style="color: #666; margin-top: 5px;">請選擇查詢類型</div>
                        </div>
                        <button class="btn-primary" onclick="applySQLExecutorConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
                // 初始化描述（延遲以確保 DOM 已渲染）
                setTimeout(() => updateSQLQueryDescription(), 100);
            }

            // OPSET 變數設定節點配置
            if (type === 'OpSet') {
                const currentConfig = node.data('config') || {};
                const operations = currentConfig.operations || [];

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div id="opsetOperationsList" style="margin-bottom: 8px;">
                            <!-- 操作項目會動態生成 -->
                        </div>

                        <div style="display: flex; gap: 6px;">
                            <button class="btn-secondary" onclick="addOpsetOperation()" style="flex: 1; padding: 6px; font-size: 11px;">
                                <i class="fas fa-plus"></i> 新增
                            </button>
                            <button class="btn-primary" onclick="applyOpsetConfig('${nodeId}')" style="flex: 1; padding: 6px; font-size: 11px;">
                                <i class="fas fa-check"></i> 套用
                            </button>
                        </div>
                    </div>

                    <!-- 運算說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchOpsetHelpTab('ops')" id="opsetTabOps" style="flex: 1; padding: 5px; border: none; background: #EC4899; color: white; font-size: 10px; cursor: pointer;">操作類型</button>
                            <button onclick="switchOpsetHelpTab('examples')" id="opsetTabExamples" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">範例</button>
                            <button onclick="switchOpsetHelpTab('vars')" id="opsetTabVars" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">變數引用</button>
                        </div>

                        <!-- 操作類型說明 -->
                        <div id="opsetContentOps" style="padding: 8px; font-size: 10px; line-height: 1.4;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #fce4ec;"><code>=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">直接設定值</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e8f5e9;"><code>運算</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>表達式</b> 如 <code>1+2</code>, <code>\${a}*\${b}</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+ - × ÷</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">目標 運算 值（累加模式）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e3f2fd;"><code>連接</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">字串連接</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+1 -1</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">遞增/遞減（不需值）</td></tr>
                            </table>
                        </div>

                        <!-- 範例 -->
                        <div id="opsetContentExamples" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #e8f5e9; border-radius: 3px;">
                                <b>✨ 表達式運算（推薦）</b><br>
                                <code>result</code> 運算 → <code>1 + 2</code> 結果: 3<br>
                                <code>total</code> 運算 → <code>\${price} * \${qty}</code><br>
                                <code>avg</code> 運算 → <code>(\${a} + \${b}) / 2</code>
                            </div>
                            <div style="margin-bottom: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>組合訊息</b><br>
                                <code>msg</code> = → <code>金額：</code><br>
                                <code>msg</code> 連接 → <code>\${amount}</code>
                            </div>
                            <div style="padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>計數器</b><br>
                                <code>counter</code> +1
                            </div>
                        </div>

                        <!-- 變數引用 -->
                        <div id="opsetContentVars" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 3px 4px; border: 1px solid #eee;"><code>\${var}</code></td><td style="padding: 3px 4px; border: 1px solid #eee;">工作流程變數</td></tr>
                                <tr><td style="padding: 3px 4px; border: 1px solid #eee;"><code>\${form.field}</code></td><td style="padding: 3px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #e8f5e9; border-radius: 3px; font-size: 9px;">
                                <b>運算支援：</b> + - * / // % **（次方）<br>
                                括號優先：<code>(\${a} + \${b}) * 2</code>
                            </div>
                        </div>
                    </div>
                `;

                // 延遲渲染操作列表
                setTimeout(() => renderOpsetOperations(operations), 50);
            }

            // OP_FIELDWRITE 表單寫值節點配置
            if (type === 'OpFieldWrite') {
                const currentConfig = node.data('config') || {};
                const targetField = currentConfig.target_field || '';
                const content = currentConfig.content || '';
                const contentType = currentConfig.content_type || 'text';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #10B981; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-pen"></i> 表單寫值設定
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">目標欄位 <span style="color: #dc3545;">*</span></label>
                            <div style="display: flex; gap: 4px;">
                                <select id="fieldWriteTargetField" style="flex: 1; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                    <option value="">載入中...</option>
                                </select>
                                <button type="button" onclick="reloadFieldWriteTargetFields()" style="padding: 6px 10px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;" title="重新載入欄位清單">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                            <div style="font-size: 9px; color: #999; margin-top: 2px;">
                                <i class="fas fa-info-circle"></i> 點擊 reload 按鈕重新載入欄位
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">
                                寫入內容 <span style="color: #dc3545;">*</span>
                            </label>
                            <textarea id="fieldWriteContent" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入內容或使用變數...&#10;支援換行：\\n">${content}</textarea>
                            <div style="font-size: 9px; color: #666; margin-top: 2px;">
                                <i class="fas fa-lightbulb"></i> 使用 <code>\${form.欄位key}</code> 讀取表單值，如 <code>\${form.textField}</code>
                            </div>
                        </div>

                        <div style="margin-bottom: 10px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">內容格式</label>
                            <div style="display: flex; gap: 12px;">
                                <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer;">
                                    <input type="radio" name="fieldWriteContentType" value="text" ${contentType === 'text' ? 'checked' : ''} style="margin-right: 4px;">
                                    Text <span style="color: #999; font-size: 9px; margin-left: 2px;">(\\n→換行)</span>
                                </label>
                                <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer;">
                                    <input type="radio" name="fieldWriteContentType" value="html" ${contentType === 'html' ? 'checked' : ''} style="margin-right: 4px;">
                                    HTML <span style="color: #999; font-size: 9px; margin-left: 2px;">(\\n→&lt;br&gt;)</span>
                                </label>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyFieldWriteConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px; background: #10B981;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="background: #e8f4fd; padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">
                            <span style="font-size: 11px; font-weight: bold; color: #1976d2;"><i class="fas fa-code"></i> 變數語法</span>
                        </div>
                        <div style="padding: 8px; font-size: 10px;">
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">格式</th>
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">說明</th>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.欄位key}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">發動表單欄位值</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.instance_id}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單實例 ID</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.serial_number}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單編號</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.display_name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單名稱</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${變數名}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程變數</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${workflow.instance_id}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程實例 ID</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${workflow.name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程名稱</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入目標欄位選項
                // 延長等待時間，讓表單欄位有足夠時間載入
                setTimeout(() => loadFieldWriteTargetFields(targetField), 500);
            }

            // FormAdapter 簽核節點配置
            if (type === 'FormAdapter') {
                const currentConfig = node.data('config') || {};
                const assigneeType = currentConfig.assignee_type || 'INITIATOR';
                const assigneeValue = currentConfig.assignee_value || '';
                const assigneeLabel = currentConfig.assignee_label || '';
                const assigneeListConfig = currentConfig.assignee_list || [];
                const selectionMode = currentConfig.selection_mode || 'single';
                const allowComment = currentConfig.allow_comment !== false;
                // 向後相容：若無 min_comment_length 但有 require_comment=true，視為 1
                const minCommentLength = currentConfig.min_comment_length !== undefined
                    ? parseInt(currentConfig.min_comment_length) || 0
                    : (currentConfig.require_comment === true ? 1 : 0);

                // 從 config 恢復已選擇的簽核者列表
                restoreSelectedAssignees(assigneeType, assigneeValue, assigneeLabel, assigneeListConfig);

                // 載入組織樹並渲染
                initOrgTree(assigneeType);
                // 載入角色列表
                loadRolesList(assigneeValue);

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-user-check"></i> 簽核節點說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">流程到達此節點時會暫停，等待指定人員選擇後續路徑。</p>
                            <p style="margin: 10px 0;"><strong>按鈕名稱來源：</strong>edge label → 目標節點 label → 節點類型</p>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border: 1px solid #ffc107; margin-top: 10px;">
                                <i class="fas fa-lightbulb" style="color: #856404;"></i>
                                <span style="color: #856404; font-size: 12px;">選取連接線，在右側「條件分支設定」區塊設定「標籤文字」作為按鈕名稱</span>
                            </div>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 簽核設定
                        </h4>

                        <div style="margin-bottom: 15px;">
                            <strong>簽核者類型：</strong><br>
                            <select id="formAdapterAssigneeType" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;" onchange="toggleAssigneeValue()">
                                <option value="INITIATOR" ${assigneeType === 'INITIATOR' ? 'selected' : ''}>發起人 (表單建立者)</option>
                                <option value="USER" ${assigneeType === 'USER' ? 'selected' : ''}>指定用戶</option>
                                <option value="DEPARTMENT" ${assigneeType === 'DEPARTMENT' ? 'selected' : ''}>指定部門</option>
                                <option value="ROLE" ${assigneeType === 'ROLE' ? 'selected' : ''}>指定角色</option>
                                <option value="DYNAMIC" ${assigneeType === 'DYNAMIC' ? 'selected' : ''}>動態 (從變數取)</option>
                            </select>
                        </div>

                        <!-- 組織樹選擇器 (USER / DEPARTMENT) -->
                        <div id="orgTreeContainer" style="margin-bottom: 15px; display: ${['USER', 'DEPARTMENT'].includes(assigneeType) ? 'block' : 'none'};">
                            <strong>從組織樹選擇<span id="multiSelectHint" style="color: #667eea; font-size: 11px; display: ${assigneeType === 'USER' ? 'inline' : 'none'};"> (可多選，任一人簽核)</span>：</strong>
                            <div style="margin-top: 8px; border: 1px solid #ddd; border-radius: 4px; background: #fafafa; max-height: 200px; overflow: auto;">
                                <div id="orgTreeContent" style="padding: 8px; font-size: 12px;">
                                    <span style="color: #999;"><i class="fas fa-spinner fa-spin"></i> 載入中...</span>
                                </div>
                            </div>
                            <div id="selectedAssignees" style="margin-top: 8px; padding: 8px; background: #e8f4fd; border-radius: 4px; display: none;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-weight: bold; font-size: 12px;"><i class="fas fa-users" style="color: #28a745;"></i> 已選擇：</span>
                                    <button onclick="clearAllAssignees()" style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 11px;">
                                        <i class="fas fa-times"></i> 全部清除
                                    </button>
                                </div>
                                <div id="selectedAssigneesList" style="display: flex; flex-wrap: wrap; gap: 4px;"></div>
                            </div>
                        </div>

                        <!-- ROLE 角色選擇 -->
                        <div id="roleInputContainer" style="margin-bottom: 15px; display: ${assigneeType === 'ROLE' ? 'block' : 'none'};">
                            <strong>選擇角色：</strong><br>
                            <select id="formAdapterRoleValue" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                                <option value="">載入中...</option>
                            </select>
                            <div style="margin-top: 4px; font-size: 11px; color: #888;">此角色下的所有用戶都可簽核</div>
                        </div>

                        <!-- DYNAMIC 變數輸入 -->
                        <div id="dynamicInputContainer" style="margin-bottom: 15px; display: ${assigneeType === 'DYNAMIC' ? 'block' : 'none'};">
                            <strong>變數名稱：</strong><br>
                            <input type="text" id="formAdapterDynamicValue" value="${assigneeType === 'DYNAMIC' ? assigneeValue : ''}"
                                   placeholder="例如: manager_id"
                                   style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                        </div>

                        <div style="margin-bottom: 15px;">
                            <strong>選擇模式：</strong><br>
                            <div style="display: flex; gap: 10px; margin-top: 8px;">
                                <label style="display: flex; align-items: center; padding: 10px 15px; border: 2px solid ${selectionMode === 'single' ? '#667eea' : '#e0e0e0'}; border-radius: 6px; cursor: pointer; flex: 1; background: ${selectionMode === 'single' ? '#f0f4ff' : 'white'};">
                                    <input type="radio" name="selectionMode" value="single" ${selectionMode === 'single' ? 'checked' : ''} style="margin-right: 8px;">
                                    <div>
                                        <div style="font-weight: bold; font-size: 13px;">單選</div>
                                        <div style="font-size: 11px; color: #666;">Radio 按鈕</div>
                                    </div>
                                </label>
                                <label style="display: flex; align-items: center; padding: 10px 15px; border: 2px solid ${selectionMode === 'multiple' ? '#667eea' : '#e0e0e0'}; border-radius: 6px; cursor: pointer; flex: 1; background: ${selectionMode === 'multiple' ? '#f0f4ff' : 'white'};">
                                    <input type="radio" name="selectionMode" value="multiple" ${selectionMode === 'multiple' ? 'checked' : ''} style="margin-right: 8px;">
                                    <div>
                                        <div style="font-weight: bold; font-size: 13px;">複選</div>
                                        <div style="font-size: 11px; color: #666;">Checkbox</div>
                                    </div>
                                </label>
                            </div>
                        </div>

                        <div style="margin-bottom: 15px; border-top: 1px solid #eee; padding-top: 15px;">
                            <strong>備註設定：</strong><br>
                            <label style="display: flex; align-items: center; margin-top: 8px; cursor: pointer;">
                                <input type="checkbox" id="formAdapterAllowComment" ${allowComment ? 'checked' : ''} style="margin-right: 8px;"
                                       onchange="document.getElementById('minCommentLengthRow').style.display = this.checked ? 'flex' : 'none';">
                                顯示備註欄位
                            </label>
                            <div id="minCommentLengthRow" style="display: ${allowComment ? 'flex' : 'none'}; align-items: center; margin-top: 8px; gap: 8px;">
                                <span style="white-space: nowrap;">最少字數：</span>
                                <input type="number" id="formAdapterMinCommentLength" value="${minCommentLength}" min="0" max="500" step="1"
                                       style="width: 80px; padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; text-align: center;">
                                <span style="font-size: 11px; color: #999;">0 = 不需留言</span>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyFormAdapterConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>

                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee;">
                            <button class="btn-secondary" onclick="openFieldPermissionsModal('${nodeId}')" style="width: 100%; background: #6c757d; color: white; border: none; padding: 10px; border-radius: 4px; cursor: pointer;">
                                <i class="fas fa-shield-alt"></i> 欄位權限設定
                            </button>
                            <div style="margin-top: 4px; font-size: 11px; color: #888; text-align: center;">
                                設定簽核者/閱讀者對各欄位的可見與編輯權限
                            </div>
                        </div>
                    </div>
                `;
            }

            // Telegram 通知節點配置
            if (type === 'Telegram') {
                const currentConfig = node.data('config') || {};
                const configId = currentConfig.config_id || '';
                const channelName = currentConfig.channel_name || '';
                const message = currentConfig.message || '';
                const parseMode = currentConfig.parse_mode || 'HTML';
                const disableNotification = currentConfig.disable_notification || false;
                const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">Bot 設定組</label>
                                <select id="telegramConfigId" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" onchange="updateTelegramChannels()">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">頻道</label>
                                <select id="telegramChannelName" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                    <option value="">請先選擇 Bot...</option>
                                </select>
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">訊息內容 <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px;">\${var}</code> <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px;">\${form.field}</code></label>
                            <textarea id="telegramMessage" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入訊息內容...">${message}</textarea>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="telegramParseMode" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="HTML" ${parseMode === 'HTML' ? 'selected' : ''}>HTML</option>
                                    <option value="Markdown" ${parseMode === 'Markdown' ? 'selected' : ''}>Markdown</option>
                                    <option value="MarkdownV2" ${parseMode === 'MarkdownV2' ? 'selected' : ''}>MarkdownV2</option>
                                </select>
                            </div>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="telegramDisableNotification" ${disableNotification ? 'checked' : ''} style="margin-right: 4px;">
                                靜音
                            </label>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="telegramDisableWebPagePreview" ${disableWebPagePreview ? 'checked' : ''} style="margin-right: 4px;">
                                禁預覽
                            </label>
                        </div>

                        <button class="btn-primary" onclick="applyTelegramConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 格式說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchTgFormatTab('html')" id="tgTabHtml" style="flex: 1; padding: 6px 8px; border: none; background: #667eea; color: white; font-size: 11px; cursor: pointer;">HTML</button>
                            <button onclick="switchTgFormatTab('md')" id="tgTabMd" style="flex: 1; padding: 6px 8px; border: none; background: transparent; color: #666; font-size: 11px; cursor: pointer;">Markdown</button>
                            <button onclick="switchTgFormatTab('md2')" id="tgTabMd2" style="flex: 1; padding: 6px 8px; border: none; background: transparent; color: #666; font-size: 11px; cursor: pointer;">MarkdownV2</button>
                        </div>

                        <!-- HTML 說明 -->
                        <div id="tgContentHtml" style="padding: 8px; font-size: 10px; line-height: 1.5;">
                            <div style="color: #28a745; font-weight: bold; margin-bottom: 4px;">✓ 建議使用，最簡單</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;b&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;i&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;u&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><u>底線</u></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;s&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><s>刪除線</s></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;code&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;pre&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">程式碼區塊</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;a href=""&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">📋 &lt;b&gt;通知&lt;/b&gt;

申請人：&lt;code&gt;\${name}&lt;/code&gt;
金額：&lt;b&gt;\${amount}&lt;/b&gt; 元</div>
                            <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">⚠ 不支援: &lt;font&gt;, &lt;br&gt;（直接換行即可）</div>
                        </div>

                        <!-- Markdown 說明 -->
                        <div id="tgContentMd" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                            <div style="color: #ffc107; font-weight: bold; margin-bottom: 4px;">⚡ 基本格式，功能較少</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>*文字*</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>_文字_</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\`code\`</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>[文字](URL)</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">📋 *通知*

申請人：\`\${name}\`
金額：*\${amount}* 元</div>
                            <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">⚠ 不支援: 底線、刪除線</div>
                        </div>

                        <!-- MarkdownV2 說明 -->
                        <div id="tgContentMd2" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                            <div style="color: #dc3545; font-weight: bold; margin-bottom: 4px;">⚠ 功能最多但需跳脫特殊字元</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>*文字*</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>_文字_</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>__文字__</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><u>底線</u></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>~文字~</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><s>刪除線</s></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>||文字||</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">隱藏文字</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #fff3cd; border-radius: 3px; font-size: 9px;">
                                <b>必須跳脫的字元：</b><br>
                                <code>_ * [ ] ( ) ~ \` > # + - = | { } . !</code><br>
                                例：<code>100.5</code> → <code>100\\.5</code>
                            </div>
                        </div>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; margin-top: 8px; overflow: hidden;">
                        <div style="background: #e8f4fd; padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">
                            <span style="font-size: 11px; font-weight: bold; color: #1976d2;"><i class="fas fa-code"></i> 變數語法</span>
                        </div>
                        <div style="padding: 8px; font-size: 10px;">
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">格式</th>
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">說明</th>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.欄位key}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">發動表單欄位值</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.instance_id}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單實例 ID</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.serial_number}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單編號</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${form.display_name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單名稱</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${變數名}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程變數</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${workflow.instance_id}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程實例 ID</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${workflow.name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程名稱</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入可用的 Telegram 設定
                setTimeout(() => loadTelegramConfigs(configId || null, channelName), 100);
            }

            // SYS_Telegram 系統級 Telegram 通知節點配置
            if (type === 'SysTelegram') {
                const currentConfig = node.data('config') || {};
                const configId = currentConfig.config_id || '';
                const channelName = currentConfig.channel_name || '';
                const message = currentConfig.message || '';
                const parseMode = currentConfig.parse_mode || 'HTML';
                const disableNotification = currentConfig.disable_notification || false;
                const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

                info += `
                    <div style="background: #FDF2F8; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 2px solid #DB2777;">
                        <div style="font-weight: bold; color: #DB2777; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-shield-alt"></i> 系統級 Telegram 設定
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">系統 Bot 設定組</label>
                                <select id="sysTelegramConfigId" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 12px;" onchange="updateSysTelegramChannels()">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">頻道</label>
                                <select id="sysTelegramChannelName" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 12px;">
                                    <option value="">請先選擇 Bot...</option>
                                </select>
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">訊息內容 <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px;">\${var}</code> <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px;">\${form.field}</code></label>
                            <textarea id="sysTelegramMessage" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #DB2777; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入訊息內容...">${message}</textarea>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="sysTelegramParseMode" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 11px;">
                                    <option value="HTML" ${parseMode === 'HTML' ? 'selected' : ''}>HTML</option>
                                    <option value="Markdown" ${parseMode === 'Markdown' ? 'selected' : ''}>Markdown</option>
                                    <option value="MarkdownV2" ${parseMode === 'MarkdownV2' ? 'selected' : ''}>MarkdownV2</option>
                                </select>
                            </div>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="sysTelegramDisableNotification" ${disableNotification ? 'checked' : ''} style="margin-right: 4px;">
                                靜音
                            </label>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="sysTelegramDisableWebPagePreview" ${disableWebPagePreview ? 'checked' : ''} style="margin-right: 4px;">
                                禁預覽
                            </label>
                        </div>

                        <button class="btn-primary" onclick="applySysTelegramConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px; background: #DB2777;">
                            <i class="fas fa-check"></i> 套用
                        </button>

                        <!-- 變數說明 -->
                        <div style="margin-top: 8px; padding: 8px; background: #f8f9fa; border-radius: 4px; border: 1px solid #e0e0e0;">
                            <div style="font-size: 10px; font-weight: bold; color: #1976d2; margin-bottom: 4px;"><i class="fas fa-code"></i> 變數語法</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 9px;">
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${form.欄位key}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">發動表單欄位值</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${form.instance_id}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">表單實例 ID</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${form.serial_number}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">表單編號</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${form.display_name}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">表單名稱</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${變數名}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程變數</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${workflow.instance_id}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程實例 ID</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${workflow.name}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程名稱</td></tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入系統級 Telegram 設定
                setTimeout(() => loadSysTelegramConfigs(configId || null, channelName), 100);
            }

            // EmailRelay 系統郵件節點配置
            if (type === 'EmailRelay') {
                const currentConfig = node.data('config') || {};
                const recipientType = currentConfig.recipient_type || 'group';
                const recipientGroups = currentConfig.recipient_groups || [];
                const recipientManual = currentConfig.recipient_manual || '';
                const ccManual = currentConfig.cc_manual || '';
                const subject = currentConfig.subject || '';
                const body = currentConfig.body || '';
                const bodyType = currentConfig.body_type || 'plain';
                const priority = currentConfig.priority || 'normal';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #16A34A; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-envelope"></i> 系統郵件設定
                        </div>

                        <!-- 收件者類型 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者來源</label>
                            <select id="emailRelayRecipientType" onchange="toggleEmailRelayRecipientFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="group" ${recipientType === 'group' ? 'selected' : ''}>收件人群組</option>
                                <option value="manual" ${recipientType === 'manual' ? 'selected' : ''}>手動輸入</option>
                            </select>
                        </div>

                        <!-- 群組選擇 -->
                        <div id="emailRelayGroupField" style="margin-bottom: 8px; ${recipientType !== 'group' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇群組（可多選）</label>
                            <select id="emailRelayGroups" multiple style="width: 100%; height: 80px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="">載入中...</option>
                            </select>
                        </div>

                        <!-- 手動輸入收件者 -->
                        <div id="emailRelayManualField" style="margin-bottom: 8px; ${recipientType !== 'manual' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者 Email（逗號或換行分隔，支援變數 <code>\${var}</code>）</label>
                            <textarea id="emailRelayRecipientManual" rows="2" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; font-family: monospace;">${recipientManual}</textarea>
                        </div>

                        <!-- 副本 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">CC 副本（選填）</label>
                            <input type="text" id="emailRelayCcManual" placeholder="逗號分隔，支援變數" value="${ccManual}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                        </div>

                        <!-- 主旨 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">主旨 <span style="color: #DC2626;">*</span></label>
                            <input type="text" id="emailRelaySubject" placeholder="支援變數 \${var}, \${form.field}" value="${subject}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <!-- 內容 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">內容 <span style="color: #DC2626;">*</span></label>
                            <textarea id="emailRelayBody" rows="5" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;" placeholder="輸入郵件內容...">${body}</textarea>
                        </div>

                        <!-- 格式與優先級 -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="emailRelayBodyType" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="plain" ${bodyType === 'plain' ? 'selected' : ''}>純文字</option>
                                    <option value="html" ${bodyType === 'html' ? 'selected' : ''}>HTML</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">優先級</label>
                                <select id="emailRelayPriority" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                    <option value="normal" ${priority === 'normal' ? 'selected' : ''}>一般</option>
                                    <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                                </select>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyEmailRelayConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; padding: 8px;">
                        <div style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 6px;">可用變數</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #f0fdf4;"><code>\${var_name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">工作流變數</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${form.field}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>\${workflow.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">工作流名稱</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${timestamp}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">發送時間</td></tr>
                        </table>
                    </div>
                `;

                // 載入可用的收件人群組
                setTimeout(() => loadEmailRelayGroups(recipientGroups), 100);
            }

            // EmailAdapter 企業郵件節點配置
            if (type === 'EmailAdapter') {
                const currentConfig = node.data('config') || {};
                const smtpConfigId = currentConfig.smtp_config_id || '';
                const recipientType = currentConfig.recipient_type || 'manual';
                const recipientGroups = currentConfig.recipient_groups || [];
                const recipientManual = currentConfig.recipient_manual || '';
                const ccManual = currentConfig.cc_manual || '';
                const subject = currentConfig.subject || '';
                const body = currentConfig.body || '';
                const bodyType = currentConfig.body_type || 'plain';
                const priority = currentConfig.priority || 'normal';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #2563EB; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-mail-bulk"></i> 企業郵件設定
                        </div>

                        <!-- SMTP 設定選擇 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">SMTP 郵件服務</label>
                            <select id="emailAdapterSmtpConfig" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="">載入中...</option>
                            </select>
                            <div style="font-size: 10px; color: #888; margin-top: 2px;">留空則使用預設設定（支援備援機制）</div>
                        </div>

                        <!-- 收件者類型 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者來源</label>
                            <select id="emailAdapterRecipientType" onchange="toggleEmailAdapterRecipientFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="group" ${recipientType === 'group' ? 'selected' : ''}>收件人群組</option>
                                <option value="manual" ${recipientType === 'manual' ? 'selected' : ''}>手動輸入</option>
                            </select>
                        </div>

                        <!-- 群組選擇 -->
                        <div id="emailAdapterGroupField" style="margin-bottom: 8px; ${recipientType !== 'group' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇群組（可多選）</label>
                            <select id="emailAdapterGroups" multiple style="width: 100%; height: 80px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="">載入中...</option>
                            </select>
                        </div>

                        <!-- 手動輸入收件者 -->
                        <div id="emailAdapterManualField" style="margin-bottom: 8px; ${recipientType !== 'manual' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者 Email（逗號或換行分隔，支援變數 <code>\${var}</code>）</label>
                            <textarea id="emailAdapterRecipientManual" rows="2" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; font-family: monospace;">${recipientManual}</textarea>
                        </div>

                        <!-- 副本 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">CC 副本（選填）</label>
                            <input type="text" id="emailAdapterCcManual" placeholder="逗號分隔，支援變數" value="${ccManual}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                        </div>

                        <!-- 主旨 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">主旨 <span style="color: #DC2626;">*</span></label>
                            <input type="text" id="emailAdapterSubject" placeholder="支援變數 \${var}, \${form.field}" value="${subject}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <!-- 內容 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">內容 <span style="color: #DC2626;">*</span></label>
                            <textarea id="emailAdapterBody" rows="5" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;" placeholder="輸入郵件內容...">${body}</textarea>
                        </div>

                        <!-- 格式與優先級 -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="emailAdapterBodyType" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="plain" ${bodyType === 'plain' ? 'selected' : ''}>純文字</option>
                                    <option value="html" ${bodyType === 'html' ? 'selected' : ''}>HTML</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">優先級</label>
                                <select id="emailAdapterPriority" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                    <option value="normal" ${priority === 'normal' ? 'selected' : ''}>一般</option>
                                    <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                                </select>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyEmailAdapterConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; padding: 8px;">
                        <div style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 6px;">可用變數</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #f0fdf4;"><code>\${var_name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">工作流變數</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${form.field}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>\${workflow.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">工作流名稱</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${timestamp}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">發送時間</td></tr>
                        </table>
                    </div>
                `;

                // 載入 SMTP 設定和收件人群組
                setTimeout(() => {
                    loadEmailAdapterSmtpConfigs(smtpConfigId);
                    loadEmailAdapterGroups(recipientGroups);
                }, 100);
            }

            // BRANCH 條件路由節點配置
            if (type === 'Branch') {
                const currentConfig = node.data('config') || {};
                const rules = currentConfig.rules || [];
                const fallback = currentConfig.fallback || { action: 'log', log_message: '無匹配規則' };

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-weight: bold; color: #16A34A; font-size: 12px;"><i class="fas fa-code-branch"></i> 分支規則</span>
                            <button class="btn-secondary" onclick="addBranchRule()" style="padding: 3px 8px; font-size: 10px;">
                                <i class="fas fa-plus"></i> 新增規則
                            </button>
                        </div>
                        <div id="branchRulesList" style="max-height: 300px; overflow-y: auto;">
                            <!-- 規則會動態生成 -->
                        </div>
                    </div>

                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #DC2626; font-size: 11px; margin-bottom: 6px;">
                            <i class="fas fa-exclamation-triangle"></i> 無匹配時 (Fallback)
                        </div>
                        <div style="display: grid; grid-template-columns: auto 1fr; gap: 6px; align-items: center;">
                            <select id="branchFallbackAction" onchange="toggleBranchFallbackOptions()" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="log" ${fallback.action === 'log' ? 'selected' : ''}>只記錄 Log</option>
                                <option value="route" ${fallback.action === 'route' ? 'selected' : ''}>路由至節點</option>
                                <option value="default" ${fallback.action === 'default' ? 'selected' : ''}>走第一條出線</option>
                            </select>
                            <input type="text" id="branchFallbackMessage" placeholder="Log 訊息"
                                   value="${fallback.log_message || '無匹配規則'}"
                                   style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; ${fallback.action === 'route' ? 'display:none;' : ''}">
                            <select id="branchFallbackTarget" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; grid-column: span 2; ${fallback.action !== 'route' ? 'display:none;' : ''}">
                                <option value="">選擇目標出線...</option>
                            </select>
                        </div>
                    </div>

                    <button class="btn-primary" onclick="applyBranchConfig('${nodeId}')" style="width: 100%; padding: 8px; font-size: 12px; margin-bottom: 8px;">
                        <i class="fas fa-check"></i> 套用
                    </button>

                    <!-- 運算符說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchBranchHelpTab('ops')" id="branchTabOps" style="flex: 1; padding: 5px; border: none; background: #16A34A; color: white; font-size: 10px; cursor: pointer;">運算符</button>
                            <button onclick="switchBranchHelpTab('logic')" id="branchTabLogic" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">邏輯</button>
                            <button onclick="switchBranchHelpTab('examples')" id="branchTabExamples" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">範例</button>
                        </div>

                        <div id="branchContentOps" style="padding: 8px; font-size: 10px; line-height: 1.4;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #dcfce7;"><code>==</code> <code>!=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">相等/不等（字串比較）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&gt;</code> <code>&gt;=</code> <code>&lt;</code> <code>&lt;=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">數值比較</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>contains</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">包含子字串</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>startswith</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">開頭符合</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #fef3c7;"><code>in</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">在清單中 (逗號分隔)</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>empty</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">為空（不需比較值）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>matches</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">正則匹配</td></tr>
                            </table>
                        </div>

                        <div id="branchContentLogic" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #dcfce7; border-radius: 3px;">
                                <b>AND（且）</b>：所有條件都要符合<br>
                                <code>\${status}==approved AND \${amount}&gt;1000</code>
                            </div>
                            <div style="padding: 4px; background: #fef3c7; border-radius: 3px;">
                                <b>OR（或）</b>：任一條件符合即可<br>
                                <code>\${type}==urgent OR \${priority}==high</code>
                            </div>
                            <div style="margin-top: 6px; font-size: 9px; color: #666;">
                                同一規則內的條件，依序用「與下一條件的關係」串接
                            </div>
                        </div>

                        <div id="branchContentExamples" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #f0fdf4; border-radius: 3px;">
                                <b>金額判斷</b><br>
                                <code>\${amount}</code> <code>&gt;</code> <code>10000</code><br>
                                → 走「主管簽核」路徑
                            </div>
                            <div style="margin-bottom: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>狀態檢查</b><br>
                                <code>\${status}</code> <code>in</code> <code>approved,confirmed</code><br>
                                → 符合時走多條路徑（並行）
                            </div>
                            <div style="padding: 4px; background: #fef3c7; border-radius: 3px;">
                                <b>複合條件</b><br>
                                條件1: <code>\${dept}</code> <code>==</code> <code>IT</code> [AND]<br>
                                條件2: <code>\${level}</code> <code>&gt;=</code> <code>3</code>
                            </div>
                        </div>
                    </div>
                `;

                // 延遲渲染：先載入出線，再渲染規則（規則需要出線資料）
                setTimeout(() => {
                    loadBranchOutgoingEdges(nodeId, fallback);
                    renderBranchRules(rules, nodeId);
                }, 50);
            }

            // End 結束節點配置
            if (type === 'End') {
                const currentConfig = node.data('config') || {};
                const finishMode = currentConfig.finish_mode || 'detach';
                const waitSeconds = currentConfig.wait_seconds !== undefined ? currentConfig.wait_seconds : 3;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 11px; color: #666; white-space: nowrap;">
                                <i class="fas fa-clock" style="color: #667eea;"></i> 等待
                            </label>
                            <input type="number" id="endWaitSeconds" value="${waitSeconds}" min="0" max="300"
                                   style="width: 60px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; text-align: center;">
                            <span style="font-size: 11px; color: #666;">秒後結束流程</span>
                        </div>
                    </div>

                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="margin-bottom: 10px;">
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'detach' ? '#667eea' : '#e0e0e0'}; border-radius: 8px; margin-bottom: 10px; cursor: pointer; background: ${finishMode === 'detach' ? '#f0f4ff' : 'white'};">
                                <input type="radio" name="finishMode" value="detach" ${finishMode === 'detach' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #667eea;">分離執行模式 (Detach)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    流程直接結束，不處理未完成的節點。<br>
                                    <span style="color: #999;">適合：執行時間不確定的背景任務、單向通知流程</span>
                                </p>
                            </label>
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'cancel' ? '#ff6b00' : '#e0e0e0'}; border-radius: 8px; margin-bottom: 10px; cursor: pointer; background: ${finishMode === 'cancel' ? '#fff8f0' : 'white'};">
                                <input type="radio" name="finishMode" value="cancel" ${finishMode === 'cancel' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #ff6b00;">取消/終止模式 (Cancel)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    取消未執行的節點，強制終止執行中的節點。<br>
                                    <span style="color: #999;">適合：需要明確終止所有任務的流程</span>
                                </p>
                            </label>
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'strict' ? '#28a745' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${finishMode === 'strict' ? '#f0fff4' : 'white'};">
                                <input type="radio" name="finishMode" value="strict" ${finishMode === 'strict' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #28a745;">嚴格等待模式 (Strict)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    等待所有節點完成，有錯誤則阻止結束。<br>
                                    <span style="color: #999;">適合：需要確保所有任務都完成的關鍵流程</span>
                                </p>
                            </label>
                        </div>
                        <button class="btn-primary" onclick="applyEndConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            document.getElementById('nodeSettings').innerHTML = info;

            // 如果是子流程節點，載入可用子流程清單
            if (type === 'Subflow') {
                loadAvailableSubflows(nodeId);
            }

            updateStatus(`選中節點：${nodeId}`);
        }

        // 載入可用子流程清單到下拉選單
        async function loadAvailableSubflows(nodeId) {
            try {
                // 取得當前工作流程 ID
                const parentId = currentWorkflowId;
                if (!parentId) {
                    console.error('無法取得當前工作流程 ID');
                    updateStatus('無法載入子流程清單：找不到父流程 ID', 'warning');
                    return;
                }

                const response = await fetch(`/api/workflows/data/subflows/available?parent_id=${parentId}`);
                const result = await response.json();

                const selectElement = document.getElementById('childFlowSelect');
                if (!selectElement) {
                    console.error('找不到子流程下拉選單元素');
                    return;
                }

                // 取得當前配置的子流程
                const node = cy.getElementById(nodeId);
                const currentConfig = node.data('config') || {};
                const currentChildFlowId = currentConfig.childFlowId || '';

                // 清空並填充選項
                selectElement.innerHTML = '<option value="">請選擇子流程...</option>';

                if (result.success && result.data) {
                    result.data.forEach(subflow => {
                        const option = document.createElement('option');
                        option.value = subflow.code;
                        option.textContent = `${subflow.name}${subflow.is_bound ? ' (專屬)' : ' (通用)'}`;
                        if (subflow.code === currentChildFlowId) {
                            option.selected = true;
                        }
                        selectElement.appendChild(option);
                    });
                    console.log(`已載入 ${result.data.length} 個子流程到下拉選單`);
                } else {
                    console.error('載入子流程清單失敗:', result.message);
                    updateStatus('載入子流程清單失敗：' + (result.message || '未知錯誤'), 'warning');
                }

                // 載入參數映射配置
                loadParamMapping(nodeId);

            } catch (error) {
                console.error('載入子流程清單失敗:', error);
                updateStatus('無法載入子流程清單：' + error.message, 'warning');
            }
        }

        // 建立新子流程
        async function createNewSubflow(nodeId) {
            const subflowName = prompt('請輸入子流程名稱：');
            if (!subflowName || !subflowName.trim()) {
                return;
            }

            const parentId = currentWorkflowId;
            if (!parentId) {
                updateStatus('無法建立子流程：找不到父流程 ID', 'warning');
                return;
            }

            try {
                const response = await fetch(`/api/workflows/data/subflows/create`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: subflowName.trim(),
                        parent_id: parentId,
                        description: `子流程：${subflowName.trim()}`
                    })
                });

                if (!response.ok) {
                    const text = await response.text();
                    console.error('建立子流程 API 錯誤:', response.status, text.substring(0, 200));
                    updateStatus(`建立子流程失敗：HTTP ${response.status}`, 'warning');
                    return;
                }

                const result = await response.json();

                if (result.success) {
                    updateStatus(`子流程「${result.data.name}」已建立`, 'success');

                    // 重新載入子流程清單
                    await loadAvailableSubflows(nodeId);

                    // 自動選擇新建立的子流程並套用
                    const selectElement = document.getElementById('childFlowSelect');
                    if (selectElement) {
                        selectElement.value = result.data.code;
                        applySubprocessConfig(nodeId);
                    }
                } else {
                    updateStatus('建立子流程失敗：' + (result.message || '未知錯誤'), 'warning');
                }
            } catch (error) {
                console.error('建立子流程失敗:', error);
                updateStatus('無法建立子流程：' + error.message, 'warning');
            }
        }

        // 載入參數映射配置
        function loadParamMapping(nodeId) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            // 載入輸入參數映射
            const inputTable = document.getElementById('inputMappingTable');
            if (inputTable) {
                const inputMapping = paramMapping.input || {};
                if (Object.keys(inputMapping).length === 0) {
                    inputTable.innerHTML = '<tr><td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td></tr>';
                } else {
                    let rows = '';
                    for (const [parentVar, childVar] of Object.entries(inputMapping)) {
                        rows += `
                            <tr data-parent-var="${parentVar}">
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${parentVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${childVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                                    <button onclick="removeInputMapping('${nodeId}', '${parentVar}')"
                                            style="padding: 4px 8px; font-size: 11px; background: #ef4444; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }
                    inputTable.innerHTML = rows;
                }
            }

            // 載入輸出參數映射
            const outputTable = document.getElementById('outputMappingTable');
            if (outputTable) {
                const outputMapping = paramMapping.output || {};
                if (Object.keys(outputMapping).length === 0) {
                    outputTable.innerHTML = '<tr><td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td></tr>';
                } else {
                    let rows = '';
                    for (const [childVar, parentVar] of Object.entries(outputMapping)) {
                        rows += `
                            <tr data-child-var="${childVar}">
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${childVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${parentVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                                    <button onclick="removeOutputMapping('${nodeId}', '${childVar}')"
                                            style="padding: 4px 8px; font-size: 11px; background: #ef4444; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }
                    outputTable.innerHTML = rows;
                }
            }
        }

        // 添加輸入參數映射
        function addInputMapping(nodeId) {
            const parentVar = prompt('請輸入父流程變數名稱：');
            if (!parentVar || !parentVar.trim()) return;

            const childVar = prompt('請輸入子流程變數名稱：');
            if (!childVar || !childVar.trim()) return;

            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (!paramMapping.input) paramMapping.input = {};
            paramMapping.input[parentVar.trim()] = childVar.trim();

            config.paramMapping = paramMapping;
            node.data('config', config);

            loadParamMapping(nodeId);
            updateStatus(`✅ 已添加輸入映射：${parentVar} → ${childVar}`, 'success');
        }

        // 添加輸出參數映射
        function addOutputMapping(nodeId) {
            const childVar = prompt('請輸入子流程變數名稱：');
            if (!childVar || !childVar.trim()) return;

            const parentVar = prompt('請輸入父流程變數名稱：');
            if (!parentVar || !parentVar.trim()) return;

            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (!paramMapping.output) paramMapping.output = {};
            paramMapping.output[childVar.trim()] = parentVar.trim();

            config.paramMapping = paramMapping;
            node.data('config', config);

            loadParamMapping(nodeId);
            updateStatus(`✅ 已添加輸出映射：${childVar} → ${parentVar}`, 'success');
        }

        // 刪除輸入參數映射
        function removeInputMapping(nodeId, parentVar) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (paramMapping.input && paramMapping.input[parentVar]) {
                delete paramMapping.input[parentVar];
                config.paramMapping = paramMapping;
                node.data('config', config);

                loadParamMapping(nodeId);
                updateStatus(`✅ 已刪除輸入映射：${parentVar}`, 'success');
            }
        }

        // 刪除輸出參數映射
        function removeOutputMapping(nodeId, childVar) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (paramMapping.output && paramMapping.output[childVar]) {
                delete paramMapping.output[childVar];
                config.paramMapping = paramMapping;
                node.data('config', config);

                loadParamMapping(nodeId);
                updateStatus(`✅ 已刪除輸出映射：${childVar}`, 'success');
            }
        }

        // 套用節點基本資訊（名稱與描述）- 內部輔助函數
        // 參數 silent: 是否靜默模式（不顯示成功訊息，用於其他 apply 函數內部調用）
        function applyNodeBasicInfo(nodeId, silent = false) {
            const node = cy.getElementById(nodeId);
            if (!node) {
                updateStatus('找不到節點', 'warning');
                return null;
            }

            const labelInput = document.getElementById('node-label-input');
            const descInput = document.getElementById('node-description-input');

            const newLabel = labelInput?.value?.trim() || node.data('label');
            const newDescription = descInput?.value?.trim() || '';

            // 更新節點資料
            node.data('label', newLabel);
            node.data('description', newDescription);

            if (!silent) {
                updateStatus(`✅ 已更新節點：${newLabel}`, 'success');
            }

            return node; // 返回 node 供其他函數使用
        }

        // 套用子流程節點配置
        function applySubprocessConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 從下拉選單取得選擇的子流程
            const selectElement = document.getElementById('childFlowSelect');
            if (!selectElement) {
                updateStatus('找不到子流程選單', 'warning');
                return;
            }

            const childFlowId = selectElement.value?.trim();
            if (!childFlowId) {
                updateStatus('請選擇子流程', 'warning');
                return;
            }

            // 取得選中的子流程名稱（用於顯示）
            const selectedOption = selectElement.options[selectElement.selectedIndex];
            const childFlowName = selectedOption ? selectedOption.textContent : childFlowId;

            // 取得現有的 config，更新 childFlowId
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                childFlowId: childFlowId
            };

            // 儲存設定到節點的 config
            node.data('config', updatedConfig);

            updateStatus(`✅ 子流程設定已套用：${childFlowName}`, 'success');

            console.log('子流程節點配置已更新:', {
                nodeId: nodeId,
                childFlowId: childFlowId,
                config: updatedConfig
            });

            // 自動儲存當前流程
            saveWorkflow().then(() => {
                console.log('✅ 流程已自動儲存');
                // 延遲 0.5 秒後重新整理流程樹系
                setTimeout(() => {
                    refreshFlowTree();
                }, 500);
            }).catch(err => {
                console.error('⚠️ 自動儲存失敗:', err);
            });
        }

        // 套用 Delay 暫停節點配置
        function applyDelayConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const delaySecondsInput = document.getElementById('delaySeconds');
            if (!delaySecondsInput) {
                updateStatus('找不到延遲秒數輸入框', 'warning');
                return;
            }

            const delaySeconds = parseInt(delaySecondsInput.value, 10);
            if (isNaN(delaySeconds) || delaySeconds < 0) {
                updateStatus('延遲秒數必須是非負整數', 'warning');
                return;
            }

            if (delaySeconds > 86400) {
                updateStatus('延遲秒數不能超過 86400（24小時）', 'warning');
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                delay_seconds: delaySeconds
            };

            node.data('config', updatedConfig);

            // 更新換算顯示
            const hours = Math.floor(delaySeconds / 3600);
            const minutes = Math.floor((delaySeconds % 3600) / 60);
            const seconds = delaySeconds % 60;
            const displayEl = document.getElementById('delayTimeDisplay');
            if (displayEl) {
                displayEl.textContent = `${hours}小時 ${minutes}分 ${seconds}秒`;
            }

            updateStatus(`✅ 暫停設定已套用：${delaySeconds} 秒`, 'success');

            console.log('Delay 節點配置已更新:', {
                nodeId: nodeId,
                delay_seconds: delaySeconds,
                config: updatedConfig
            });
        }
        window.applyDelayConfig = applyDelayConfig;

        // ==================== OP_FIELDWRITE 表單寫值函數 ====================

        // 載入目標欄位選項（從綁定的表單取得）
        async function loadFieldWriteTargetFields(selectedValue, retryCount = 0) {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 如果 selectedValue 是 ${...} 格式，嘗試提取欄位名稱
            let cleanSelectedValue = selectedValue || '';
            if (cleanSelectedValue.startsWith('${') && cleanSelectedValue.endsWith('}')) {
                // 嘗試提取欄位名，例如 ${FORMCODE_fieldKey} 或 ${form.fieldKey}
                const inner = cleanSelectedValue.slice(2, -1);
                if (inner.startsWith('form.')) {
                    cleanSelectedValue = inner.slice(5);
                } else if (inner.includes('_')) {
                    // ${FORMCODE_fieldKey} 格式，取最後一個 _ 後面的部分
                    cleanSelectedValue = inner.split('_').pop();
                }
            }

            // 如果欄位尚未載入，等待並重試（最多重試 5 次）
            if (currentFormFields.length === 0 && retryCount < 5) {
                select.innerHTML = '<option value="">載入中...</option>';
                setTimeout(() => loadFieldWriteTargetFields(selectedValue, retryCount + 1), 300);
                return;
            }

            try {
                // 從已載入的表單欄位快取取得
                let fields = [];

                // 優先使用目前已載入的表單欄位
                if (currentFormFields && currentFormFields.length > 0) {
                    fields = currentFormFields;
                }

                // 如果沒有快取，嘗試從 triggerFormData 取得
                if (fields.length === 0 && window.triggerFormData && window.triggerFormData.schema) {
                    fields = extractFieldsFromSchema(window.triggerFormData.schema);
                }

                // 如果還是沒有，顯示手動輸入提示
                if (fields.length === 0) {
                    let options = '<option value="">請先選擇表單以載入欄位...</option>';
                    if (cleanSelectedValue) {
                        options = `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue}</option>`;
                    }
                    select.innerHTML = options;
                    return;
                }

                // 建構選項（顯示新式變數格式）
                let options = '<option value="">選擇目標欄位...</option>';

                // 取得表單 secure_code（從 selectedFormSecureCode 或 currentMappedForms）
                let formSecureCode = selectedFormSecureCode || null;
                if (!formSecureCode && currentMappedForms && currentMappedForms.length > 0) {
                    formSecureCode = currentMappedForms[0].form_secure_code;
                }

                fields.forEach(field => {
                    const key = field.key || field.name;
                    const label = field.label || key;
                    const selected = cleanSelectedValue === key ? 'selected' : '';

                    // 嘗試取得新式變數顯示
                    let displayName = label;
                    if (window.variableMapping && window.variableMapping.forward && formSecureCode) {
                        const internalKey = `${formSecureCode}_${key}`;
                        const displayVar = window.variableMapping.forward[internalKey];
                        if (displayVar) {
                            // 顯示新式變數格式（去掉 ${}）
                            displayName = displayVar.replace(/^\$\{/, '').replace(/\}$/, '');
                        }
                    }

                    options += `<option value="${key}" ${selected}>${displayName}</option>`;
                });

                select.innerHTML = options;

                // 如果有舊值且不在選項中，加入手動輸入選項
                if (cleanSelectedValue && !fields.find(f => (f.key || f.name) === cleanSelectedValue)) {
                    select.innerHTML += `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue} (手動輸入)</option>`;
                }

            } catch (error) {
                console.error('載入目標欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadFieldWriteTargetFields = loadFieldWriteTargetFields;

        /**
         * 重新載入 OP_FIELDWRITE 的目標欄位選項
         * - 優先使用用戶當前選擇的表單
         * - 如果沒有選擇，使用第一張配對表單
         * - 如果沒有配對表單，顯示提示訊息
         */
        async function reloadFieldWriteTargetFields() {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 檢查是否有配對表單
            if (!currentMappedForms || currentMappedForms.length === 0) {
                select.innerHTML = '<option value="">需要配對表單</option>';
                updateStatus('⚠ 請先在表單欄位分頁配對表單');
                return;
            }

            // 選擇表單：優先使用已選擇的，否則用第一張
            let targetForm = null;
            if (selectedFormId) {
                targetForm = currentMappedForms.find(f => f.form_id === selectedFormId);
            }
            if (!targetForm) {
                targetForm = currentMappedForms[0];
            }

            // 顯示載入中
            select.innerHTML = '<option value="">載入中...</option>';

            try {
                // 載入表單欄位（這也會更新 currentFormFields）
                await selectForm(targetForm);

                // 現在欄位應該已經載入，重新載入下拉選單
                const currentValue = select.value;
                await loadFieldWriteTargetFields(currentValue);

                updateStatus(`✅ 已載入表單「${targetForm.form_name}」的欄位`);
            } catch (error) {
                console.error('重新載入欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
                updateStatus('❌ 載入欄位失敗: ' + error.message);
            }
        }
        window.reloadFieldWriteTargetFields = reloadFieldWriteTargetFields;

        // 從 form.io schema 解析欄位列表
        function extractFieldsFromSchema(schema) {
            const fields = [];
            if (!schema || !schema.components) return fields;

            function extractFromComponents(components) {
                for (const comp of components) {
                    // 跳過容器類型元件（只處理實際欄位）
                    if (comp.type === 'button' || comp.type === 'htmlelement' || comp.type === 'content') {
                        continue;
                    }

                    // 如果有 key，視為欄位
                    if (comp.key && !comp.key.startsWith('panel') && !comp.key.startsWith('columns')) {
                        fields.push({
                            key: comp.key,
                            label: comp.label || comp.key,
                            type: comp.type
                        });
                    }

                    // 遞迴處理巢狀元件
                    if (comp.components) {
                        extractFromComponents(comp.components);
                    }
                    if (comp.columns) {
                        for (const col of comp.columns) {
                            if (col.components) {
                                extractFromComponents(col.components);
                            }
                        }
                    }
                }
            }

            extractFromComponents(schema.components);
            return fields;
        }
        window.extractFieldsFromSchema = extractFieldsFromSchema;

        function applyFieldWriteConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const targetFieldInput = document.getElementById('fieldWriteTargetField');
            const contentInput = document.getElementById('fieldWriteContent');
            const contentTypeRadio = document.querySelector('input[name="fieldWriteContentType"]:checked');

            if (!targetFieldInput || !contentInput) {
                updateStatus('找不到輸入欄位', 'warning');
                return;
            }

            const targetField = targetFieldInput.value.trim();
            const content = contentInput.value;
            const contentType = contentTypeRadio ? contentTypeRadio.value : 'text';

            // 驗證必填
            if (!targetField) {
                updateStatus('請輸入目標欄位 Key', 'warning');
                targetFieldInput.focus();
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                target_field: targetField,
                content: content,
                content_type: contentType
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 表單寫值設定已套用：${targetField}`, 'success');

            console.log('OP_FIELDWRITE 節點配置已更新:', {
                nodeId: nodeId,
                target_field: targetField,
                content_type: contentType,
                content_length: content.length,
                config: updatedConfig
            });
        }
        window.applyFieldWriteConfig = applyFieldWriteConfig;

        // ==================== OPSET 變數設定函數 ====================

        // OPSET 操作列表暫存
        let opsetOperationsTemp = [];

        // 渲染 OPSET 操作列表
        function renderOpsetOperations(operations) {
            opsetOperationsTemp = operations ? [...operations] : [];
            const container = document.getElementById('opsetOperationsList');
            if (!container) return;

            if (opsetOperationsTemp.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 12px; color: #999; font-size: 11px;">
                        <i class="fas fa-info-circle"></i> 點擊「新增」開始設定
                    </div>
                `;
                return;
            }

            let html = '';
            opsetOperationsTemp.forEach((op, idx) => {
                html += renderOpsetOperationItem(op, idx);
            });
            container.innerHTML = html;
        }

        // 渲染單一操作項目
        function renderOpsetOperationItem(op, idx) {
            const operationOptions = [
                { value: 'set', label: '=' },
                { value: 'expr', label: '運算' },
                { value: 'add', label: '+' },
                { value: 'subtract', label: '-' },
                { value: 'multiply', label: '×' },
                { value: 'divide', label: '÷' },
                { value: 'concat', label: '連接' },
                { value: 'increment', label: '+1' },
                { value: 'decrement', label: '-1' }
            ];

            const optionsHtml = operationOptions.map(o =>
                `<option value="${o.value}" ${op.operation === o.value ? 'selected' : ''}>${o.label}</option>`
            ).join('');

            const needsValue = !['increment', 'decrement'].includes(op.operation);

            return `
                <div style="border: 1px solid #ddd; border-radius: 4px; padding: 6px; margin-bottom: 6px; background: #fafafa;">
                    <div style="display: flex; gap: 4px; align-items: center; margin-bottom: ${needsValue ? '4px' : '0'};">
                        <input type="text" id="opset_target_${idx}" value="${op.target_var || ''}"
                               placeholder="變數名"
                               onchange="updateOpsetOperation(${idx}, 'target_var', this.value)"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; font-family: monospace;">
                        <select id="opset_op_${idx}" onchange="updateOpsetOperation(${idx}, 'operation', this.value); updateOpsetValueVisibility(${idx})"
                                style="width: 55px; padding: 4px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; text-align: center;">
                            ${optionsHtml}
                        </select>
                        <button onclick="removeOpsetOperation(${idx})" style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 12px; padding: 2px 4px;" title="刪除">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div id="opset_value_container_${idx}" style="display: ${needsValue ? 'block' : 'none'};">
                        <textarea id="opset_value_${idx}" rows="2"
                               placeholder="值或 \${var}，支援多行"
                               onchange="updateOpsetOperation(${idx}, 'value', this.value)"
                               style="width: 100%; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; font-family: monospace; resize: vertical;">${op.value !== undefined ? op.value : ''}</textarea>
                    </div>
                </div>
            `;
        }

        // 新增操作
        function addOpsetOperation() {
            opsetOperationsTemp.push({
                target_var: '',
                operation: 'set',
                value: ''
            });
            renderOpsetOperations(opsetOperationsTemp);
        }
        window.addOpsetOperation = addOpsetOperation;

        // 刪除操作
        function removeOpsetOperation(idx) {
            opsetOperationsTemp.splice(idx, 1);
            renderOpsetOperations(opsetOperationsTemp);
        }
        window.removeOpsetOperation = removeOpsetOperation;

        // 更新操作屬性
        function updateOpsetOperation(idx, field, value) {
            if (opsetOperationsTemp[idx]) {
                opsetOperationsTemp[idx][field] = value;
            }
        }
        window.updateOpsetOperation = updateOpsetOperation;

        // 更新值輸入框可見性
        function updateOpsetValueVisibility(idx) {
            const opSelect = document.getElementById(`opset_op_${idx}`);
            const valueContainer = document.getElementById(`opset_value_container_${idx}`);
            if (opSelect && valueContainer) {
                const needsValue = !['increment', 'decrement'].includes(opSelect.value);
                valueContainer.style.display = needsValue ? 'block' : 'none';
            }
        }
        window.updateOpsetValueVisibility = updateOpsetValueVisibility;

        // 套用 OPSET 設定
        function applyOpsetConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 驗證操作
            const validOperations = [];
            let hasError = false;
            const seenVarNames = new Set();  // 用於檢查重複變數名稱

            opsetOperationsTemp.forEach((op, idx) => {
                if (!op.target_var || !op.target_var.trim()) {
                    updateStatus(`操作 ${idx + 1} 缺少目標變數名稱`, 'warning');
                    hasError = true;
                    return;
                }

                const varName = op.target_var.trim();

                // 檢查同一節點內是否有重複變數名稱
                if (seenVarNames.has(varName)) {
                    updateStatus(`❌ 變數名稱「${varName}」重複，同一節點內不可有相同名稱的變數`, 'error');
                    hasError = true;
                    return;
                }
                seenVarNames.add(varName);

                const needsValue = !['increment', 'decrement'].includes(op.operation);
                if (needsValue && (op.value === undefined || op.value === '')) {
                    updateStatus(`操作 ${idx + 1} 缺少值`, 'warning');
                    hasError = true;
                    return;
                }

                validOperations.push({
                    target_var: varName,
                    operation: op.operation,
                    value: op.value
                });
            });

            if (hasError) {
                // 自動切換到常用控制分頁，讓用戶看到錯誤訊息
                if (typeof switchTab === 'function') {
                    switchTab('canvas');
                }
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                operations: validOperations
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 變數設定已套用：${validOperations.length} 個操作`, 'success');

            console.log('OPSET 節點配置已更新:', {
                nodeId: nodeId,
                operations: validOperations,
                config: updatedConfig
            });
        }
        window.applyOpsetConfig = applyOpsetConfig;

        // OPSET 說明頁籤切換
        function switchOpsetHelpTab(tab) {
            // 重置所有頁籤按鈕
            ['Ops', 'Examples', 'Vars'].forEach(t => {
                const btn = document.getElementById('opsetTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
            });
            // 隱藏所有內容
            ['Ops', 'Examples', 'Vars'].forEach(t => {
                const content = document.getElementById('opsetContent' + t);
                if (content) content.style.display = 'none';
            });

            // 顯示選中的頁籤
            const tabMap = { 'ops': 'Ops', 'examples': 'Examples', 'vars': 'Vars' };
            const activeBtn = document.getElementById('opsetTab' + tabMap[tab]);
            const activeContent = document.getElementById('opsetContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#EC4899';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchOpsetHelpTab = switchOpsetHelpTab;

        // ==================== SQLExecutor 相關函數 ====================

        // SQL 查詢類型描述
        const sqlQueryDescriptions = {
            'get_org_users': '查詢同企業的所有用戶，回傳 id、display_name、email 欄位，結果為陣列。',
            'get_org_user_count': '統計同企業的用戶總數，回傳單一數值 user_count。',
            'get_org_active_users': '查詢同企業最近 30 天有登入的活躍用戶，回傳 id、display_name、email、last_login_at 欄位。'
        };

        // 更新 SQL 查詢描述
        function updateSQLQueryDescription() {
            const select = document.getElementById('sqlQueryType');
            const descDiv = document.getElementById('sqlQueryDescription');
            if (!select || !descDiv) return;

            const queryType = select.value;
            if (queryType && sqlQueryDescriptions[queryType]) {
                descDiv.textContent = sqlQueryDescriptions[queryType];
                descDiv.style.color = '#333';
            } else {
                descDiv.textContent = '請選擇查詢類型';
                descDiv.style.color = '#666';
            }
        }
        window.updateSQLQueryDescription = updateSQLQueryDescription;

        // SQLExecutor 配置套用
        function applySQLExecutorConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 取得設定值
            const queryType = document.getElementById('sqlQueryType')?.value;
            const resultVar = document.getElementById('sqlResultVar')?.value?.trim();

            // 驗證
            if (!queryType) {
                updateStatus('❌ 請選擇查詢類型', 'error');
                return;
            }

            if (!resultVar) {
                updateStatus('❌ 請輸入結果變數名稱', 'error');
                return;
            }

            // 驗證變數名稱格式（只允許英文、數字、底線，不能以數字開頭）
            if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(resultVar)) {
                updateStatus('❌ 變數名稱格式不正確（只能使用英文、數字、底線，且不能以數字開頭）', 'error');
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                query_type: queryType,
                result_var: resultVar
            };

            node.data('config', updatedConfig);

            const queryName = sqlQueryDescriptions[queryType] ? queryType : '未知查詢';
            updateStatus(`✅ SQL 查詢設定已套用：${queryName} → $\{${resultVar}}`, 'success');

            console.log('SQLExecutor 節點配置已更新:', {
                nodeId: nodeId,
                query_type: queryType,
                result_var: resultVar,
                config: updatedConfig
            });

            // 自動儲存當前流程
            saveWorkflow().then(() => {
                console.log('✅ 流程已自動儲存');
            }).catch(err => {
                console.error('⚠️ 自動儲存失敗:', err);
            });
        }
        window.applySQLExecutorConfig = applySQLExecutorConfig;

        // ==================== Telegram 相關函數 ====================

        // Telegram 設定組快取
        let telegramConfigsCache = null;

        // 載入可用的 Telegram 設定組
        async function loadTelegramConfigs(selectedConfigId, selectedChannelName) {
            const configSelect = document.getElementById('telegramConfigId');
            if (!configSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/telegram/available');
                if (!response.ok) {
                    configSelect.innerHTML = '<option value="">無法載入設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    configSelect.innerHTML = '<option value="">沒有可用的設定</option>';
                    return;
                }

                telegramConfigsCache = data.data.configs;

                // 建構選項
                let options = '<option value="">請選擇設定組...</option>';
                data.data.configs.forEach(config => {
                    const isSystemLabel = config.is_system ? ' (系統)' : '';
                    const selected = selectedConfigId && config.id == selectedConfigId ? 'selected' : '';
                    // 從 channels 物件取得頻道名稱陣列（與系統級一致）
                    const channelNames = Object.keys(config.channels || {});
                    options += `<option value="${config.id}" data-channels='${JSON.stringify(channelNames)}' data-default-channel="${config.default_channel || ''}" ${selected}>${config.name}${isSystemLabel}</option>`;
                });
                configSelect.innerHTML = options;

                // 如果有預選的 config，觸發更新頻道列表
                if (selectedConfigId) {
                    updateTelegramChannels(selectedChannelName);
                }
            } catch (error) {
                console.error('載入 Telegram 設定失敗:', error);
                configSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadTelegramConfigs = loadTelegramConfigs;

        // 更新頻道列表
        function updateTelegramChannels(preselectedChannel) {
            const configSelect = document.getElementById('telegramConfigId');
            const channelSelect = document.getElementById('telegramChannelName');
            if (!configSelect || !channelSelect) return;

            const selectedOption = configSelect.options[configSelect.selectedIndex];
            if (!selectedOption || !selectedOption.value) {
                channelSelect.innerHTML = '<option value="">請先選擇 Bot 設定組...</option>';
                return;
            }

            try {
                const channels = JSON.parse(selectedOption.dataset.channels || '[]');
                if (channels.length === 0) {
                    channelSelect.innerHTML = '<option value="">此設定組沒有頻道</option>';
                    return;
                }

                // 取得預設頻道（來自 API 回傳）
                const defaultChannel = selectedOption.dataset.defaultChannel || '';

                // 決定要自動選擇的頻道：
                // 1. 如果有預選頻道（節點已有配置），使用預選的
                // 2. 否則，如果只有一個頻道，自動選擇該頻道
                // 3. 否則，如果有預設頻道，使用預設頻道
                let autoSelectChannel = preselectedChannel;
                if (!autoSelectChannel) {
                    if (channels.length === 1) {
                        autoSelectChannel = channels[0];
                    } else if (defaultChannel && channels.includes(defaultChannel)) {
                        autoSelectChannel = defaultChannel;
                    }
                }

                let options = '<option value="">請選擇頻道...</option>';
                channels.forEach(channel => {
                    const selected = autoSelectChannel === channel ? 'selected' : '';
                    // 標示預設頻道
                    const label = channel === defaultChannel ? `${channel} ★` : channel;
                    options += `<option value="${channel}" ${selected}>${label}</option>`;
                });
                channelSelect.innerHTML = options;
            } catch (error) {
                console.error('解析頻道失敗:', error);
                channelSelect.innerHTML = '<option value="">解析失敗</option>';
            }
        }
        window.updateTelegramChannels = updateTelegramChannels;

        // 套用 Telegram 節點配置
        function applyTelegramConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const configId = document.getElementById('telegramConfigId')?.value;
            const channelName = document.getElementById('telegramChannelName')?.value;
            const message = document.getElementById('telegramMessage')?.value;
            const parseMode = document.getElementById('telegramParseMode')?.value || 'HTML';
            const disableNotification = document.getElementById('telegramDisableNotification')?.checked || false;
            const disableWebPagePreview = document.getElementById('telegramDisableWebPagePreview')?.checked || false;

            // 驗證必填項
            if (!configId) {
                updateStatus('請選擇 Bot 設定組', 'warning');
                return;
            }
            if (!channelName) {
                updateStatus('請選擇頻道', 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus('請輸入訊息內容', 'warning');
                return;
            }

            // 更新節點 config（config_id 是 secure_code 字串，不能 parseInt）
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                config_id: configId,
                channel_name: channelName,
                message: message.trim(),
                parse_mode: parseMode,
                disable_notification: disableNotification,
                disable_web_page_preview: disableWebPagePreview
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ Telegram 設定已套用`, 'success');

            console.log('Telegram 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyTelegramConfig = applyTelegramConfig;

        // ==================== 系統級 Telegram (SYS_Telegram) ====================

        // 系統級 Telegram 設定組快取
        let sysTelegramConfigsCache = null;

        // 載入系統級 Telegram 設定組
        async function loadSysTelegramConfigs(selectedConfigId, selectedChannelName) {
            const configSelect = document.getElementById('sysTelegramConfigId');
            if (!configSelect) return;

            try {
                // 呼叫系統級 API（只回傳 org_secure_code 為 NULL 的設定）
                const response = await fetch('/api/system/data/settings/telegram');
                if (!response.ok) {
                    configSelect.innerHTML = '<option value="">無法載入設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    configSelect.innerHTML = '<option value="">沒有系統級設定</option>';
                    return;
                }

                sysTelegramConfigsCache = data.data.configs;

                // 建構選項
                let options = '<option value="">請選擇設定組...</option>';
                data.data.configs.forEach(config => {
                    const selected = selectedConfigId && config.id == selectedConfigId ? 'selected' : '';
                    // 從 channels 物件取得頻道名稱陣列
                    const channelNames = Object.keys(config.channels || {});
                    options += `<option value="${config.id}" data-channels='${JSON.stringify(channelNames)}' ${selected}>${config.name}</option>`;
                });
                configSelect.innerHTML = options;

                // 如果有預選的 config，觸發更新頻道列表
                if (selectedConfigId) {
                    updateSysTelegramChannels(selectedChannelName);
                }
            } catch (error) {
                console.error('載入系統級 Telegram 設定失敗:', error);
                configSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadSysTelegramConfigs = loadSysTelegramConfigs;

        // 更新系統級 Telegram 頻道列表
        function updateSysTelegramChannels(preselectedChannel) {
            const configSelect = document.getElementById('sysTelegramConfigId');
            const channelSelect = document.getElementById('sysTelegramChannelName');
            if (!configSelect || !channelSelect) return;

            const selectedOption = configSelect.options[configSelect.selectedIndex];
            if (!selectedOption || !selectedOption.value) {
                channelSelect.innerHTML = '<option value="">請先選擇 Bot 設定組...</option>';
                return;
            }

            try {
                const channels = JSON.parse(selectedOption.dataset.channels || '[]');
                if (channels.length === 0) {
                    channelSelect.innerHTML = '<option value="">此設定組沒有頻道</option>';
                    return;
                }

                let options = '<option value="">請選擇頻道...</option>';
                channels.forEach(channel => {
                    const selected = preselectedChannel === channel ? 'selected' : '';
                    options += `<option value="${channel}" ${selected}>${channel}</option>`;
                });
                channelSelect.innerHTML = options;
            } catch (error) {
                console.error('解析頻道失敗:', error);
                channelSelect.innerHTML = '<option value="">解析失敗</option>';
            }
        }
        window.updateSysTelegramChannels = updateSysTelegramChannels;

        // 套用系統級 Telegram 節點配置
        function applySysTelegramConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const configId = document.getElementById('sysTelegramConfigId')?.value;
            const channelName = document.getElementById('sysTelegramChannelName')?.value;
            const message = document.getElementById('sysTelegramMessage')?.value;
            const parseMode = document.getElementById('sysTelegramParseMode')?.value || 'HTML';
            const disableNotification = document.getElementById('sysTelegramDisableNotification')?.checked || false;
            const disableWebPagePreview = document.getElementById('sysTelegramDisableWebPagePreview')?.checked || false;

            // 驗證必填項
            if (!configId) {
                updateStatus('請選擇系統級 Bot 設定組', 'warning');
                return;
            }
            if (!channelName) {
                updateStatus('請選擇頻道', 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus('請輸入訊息內容', 'warning');
                return;
            }

            // 更新節點 config（config_id 是 secure_code 字串，不能 parseInt）
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                config_id: configId,
                channel_name: channelName,
                message: message.trim(),
                parse_mode: parseMode,
                disable_notification: disableNotification,
                disable_web_page_preview: disableWebPagePreview
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 系統級 Telegram 設定已套用`, 'success');

            console.log('SYS_Telegram 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applySysTelegramConfig = applySysTelegramConfig;

        // Telegram 格式說明頁籤切換
        function switchTgFormatTab(tab) {
            // 重置所有頁籤按鈕
            ['Html', 'Md', 'Md2'].forEach(t => {
                const btn = document.getElementById('tgTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
            });
            // 隱藏所有內容
            ['Html', 'Md', 'Md2'].forEach(t => {
                const content = document.getElementById('tgContent' + t);
                if (content) content.style.display = 'none';
            });

            // 顯示選中的頁籤
            const tabMap = { 'html': 'Html', 'md': 'Md', 'md2': 'Md2' };
            const activeBtn = document.getElementById('tgTab' + tabMap[tab]);
            const activeContent = document.getElementById('tgContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#667eea';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchTgFormatTab = switchTgFormatTab;

        // ============================================
        // EmailRelay 系統郵件節點函數
        // ============================================

        // 收件人群組快取
        let emailRelayGroupsCache = null;

        // 載入可用的收件人群組
        async function loadEmailRelayGroups(selectedIds) {
            const groupSelect = document.getElementById('emailRelayGroups');
            if (!groupSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/email-groups/available');
                if (!response.ok) {
                    groupSelect.innerHTML = '<option value="">無法載入群組</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.groups) {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                    return;
                }

                emailRelayGroupsCache = data.data.groups;

                // 建構選項
                let options = '';
                data.data.groups.forEach(group => {
                    const isSystem = group.scope === 'system' ? ' (系統)' : '';
                    const selected = selectedIds && selectedIds.includes(group.id) ? 'selected' : '';
                    options += `<option value="${group.id}" ${selected}>${group.name}${isSystem} (${group.recipient_count}人)</option>`;
                });

                if (options === '') {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                } else {
                    groupSelect.innerHTML = options;
                }
            } catch (error) {
                console.error('載入收件人群組失敗:', error);
                groupSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailRelayGroups = loadEmailRelayGroups;

        // 切換收件者類型欄位顯示
        function toggleEmailRelayRecipientFields() {
            const type = document.getElementById('emailRelayRecipientType')?.value;
            const groupField = document.getElementById('emailRelayGroupField');
            const manualField = document.getElementById('emailRelayManualField');

            if (groupField) groupField.style.display = type === 'group' ? 'block' : 'none';
            if (manualField) manualField.style.display = type === 'manual' ? 'block' : 'none';
        }
        window.toggleEmailRelayRecipientFields = toggleEmailRelayRecipientFields;

        // 套用 EmailRelay 節點配置
        function applyEmailRelayConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const recipientType = document.getElementById('emailRelayRecipientType')?.value || 'group';
            const subject = document.getElementById('emailRelaySubject')?.value;
            const body = document.getElementById('emailRelayBody')?.value;
            const bodyType = document.getElementById('emailRelayBodyType')?.value || 'plain';
            const priority = document.getElementById('emailRelayPriority')?.value || 'normal';
            const ccManual = document.getElementById('emailRelayCcManual')?.value || '';

            // 驗證必填項
            if (!subject || !subject.trim()) {
                updateStatus('請輸入郵件主旨', 'warning');
                return;
            }
            if (!body || !body.trim()) {
                updateStatus('請輸入郵件內容', 'warning');
                return;
            }

            // 收集收件者設定
            let recipientGroups = [];
            let recipientManual = '';

            if (recipientType === 'group') {
                const groupSelect = document.getElementById('emailRelayGroups');
                if (groupSelect) {
                    recipientGroups = Array.from(groupSelect.selectedOptions).map(opt => opt.value);
                }
                if (recipientGroups.length === 0) {
                    updateStatus('請選擇至少一個收件人群組', 'warning');
                    return;
                }
            } else if (recipientType === 'manual') {
                recipientManual = document.getElementById('emailRelayRecipientManual')?.value || '';
                if (!recipientManual.trim()) {
                    updateStatus('請輸入收件者 Email', 'warning');
                    return;
                }
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                recipient_type: recipientType,
                recipient_groups: recipientGroups,
                recipient_manual: recipientManual.trim(),
                cc_manual: ccManual.trim(),
                subject: subject.trim(),
                body: body.trim(),
                body_type: bodyType,
                priority: priority
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 系統郵件設定已套用`, 'success');

            console.log('EmailRelay 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyEmailRelayConfig = applyEmailRelayConfig;

        // ============================================
        // EmailAdapter 企業郵件節點函數
        // ============================================

        // SMTP 設定快取
        let emailAdapterSmtpConfigsCache = null;

        // 載入可用的 SMTP 設定
        async function loadEmailAdapterSmtpConfigs(selectedId) {
            const smtpSelect = document.getElementById('emailAdapterSmtpConfig');
            if (!smtpSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/smtp/available');
                if (!response.ok) {
                    smtpSelect.innerHTML = '<option value="">無法載入 SMTP 設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    smtpSelect.innerHTML = '<option value="">沒有可用的 SMTP 設定</option>';
                    return;
                }

                emailAdapterSmtpConfigsCache = data.data.configs;
                const configs = data.data.configs;

                // 如果只有一個設定且沒有指定選擇，自動選擇它
                let autoSelectId = null;
                if (configs.length === 1 && !selectedId) {
                    autoSelectId = configs[0].id;
                }

                // 建構選項
                let options = configs.length > 1 ? '<option value="">(使用預設設定)</option>' : '';
                configs.forEach(cfg => {
                    const isDefault = cfg.is_default ? ' ⭐預設' : '';
                    const provider = cfg.provider_type !== 'generic' ? ` [${cfg.provider_type}]` : '';
                    // 檢查是否被選中：明確選擇 > 自動選擇
                    const isSelected = (selectedId && String(selectedId) === String(cfg.id)) ||
                                       (!selectedId && autoSelectId === cfg.id);
                    const selected = isSelected ? 'selected' : '';
                    options += `<option value="${cfg.id}" ${selected}>${cfg.name}${provider}${isDefault}</option>`;
                });

                smtpSelect.innerHTML = options;

                // 如果有預設設定且沒有選擇（多於一個設定時），顯示提示
                const defaultConfig = data.data.default_config;
                if (defaultConfig && !selectedId && configs.length > 1) {
                    // 更新提示文字
                    const hint = smtpSelect.nextElementSibling;
                    if (hint) {
                        hint.textContent = `預設將使用: ${defaultConfig.name}`;
                    }
                }
            } catch (error) {
                console.error('載入 SMTP 設定失敗:', error);
                smtpSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailAdapterSmtpConfigs = loadEmailAdapterSmtpConfigs;

        // 載入可用的收件人群組
        async function loadEmailAdapterGroups(selectedIds) {
            const groupSelect = document.getElementById('emailAdapterGroups');
            if (!groupSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/email-groups/available');
                if (!response.ok) {
                    groupSelect.innerHTML = '<option value="">無法載入群組</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.groups) {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                    return;
                }

                // 建構選項（只顯示企業群組，不顯示系統群組）
                let options = '';
                data.data.groups.forEach(group => {
                    // 企業郵件只使用企業級群組（scope: 'organization'）
                    if (group.scope === 'organization') {
                        const selected = selectedIds && selectedIds.includes(group.id) ? 'selected' : '';
                        options += `<option value="${group.id}" ${selected}>${group.name} (${group.recipient_count}人)</option>`;
                    }
                });

                if (options === '') {
                    groupSelect.innerHTML = '<option value="">沒有可用的企業群組</option>';
                } else {
                    groupSelect.innerHTML = options;
                }
            } catch (error) {
                console.error('載入收件人群組失敗:', error);
                groupSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailAdapterGroups = loadEmailAdapterGroups;

        // 切換收件者類型欄位顯示
        function toggleEmailAdapterRecipientFields() {
            const type = document.getElementById('emailAdapterRecipientType')?.value;
            const groupField = document.getElementById('emailAdapterGroupField');
            const manualField = document.getElementById('emailAdapterManualField');

            if (groupField) groupField.style.display = type === 'group' ? 'block' : 'none';
            if (manualField) manualField.style.display = type === 'manual' ? 'block' : 'none';
        }
        window.toggleEmailAdapterRecipientFields = toggleEmailAdapterRecipientFields;

        // 套用 EmailAdapter 節點配置
        async function applyEmailAdapterConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const smtpConfigId = document.getElementById('emailAdapterSmtpConfig')?.value || '';
            const recipientType = document.getElementById('emailAdapterRecipientType')?.value || 'manual';
            const subject = document.getElementById('emailAdapterSubject')?.value;
            const body = document.getElementById('emailAdapterBody')?.value;
            const bodyType = document.getElementById('emailAdapterBodyType')?.value || 'plain';
            const priority = document.getElementById('emailAdapterPriority')?.value || 'normal';
            const ccManual = document.getElementById('emailAdapterCcManual')?.value || '';

            // 驗證必填項
            if (!subject || !subject.trim()) {
                updateStatus('請輸入郵件主旨', 'warning');
                return;
            }
            if (!body || !body.trim()) {
                updateStatus('請輸入郵件內容', 'warning');
                return;
            }

            // 收集收件者設定
            let recipientGroups = [];
            let recipientManual = '';

            if (recipientType === 'group') {
                const groupSelect = document.getElementById('emailAdapterGroups');
                if (groupSelect) {
                    recipientGroups = Array.from(groupSelect.selectedOptions).map(opt => opt.value);
                }
                if (recipientGroups.length === 0) {
                    updateStatus('請選擇至少一個收件人群組', 'warning');
                    return;
                }
            } else if (recipientType === 'manual') {
                recipientManual = document.getElementById('emailAdapterRecipientManual')?.value || '';
                if (!recipientManual.trim()) {
                    updateStatus('請輸入收件者 Email', 'warning');
                    return;
                }
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                smtp_config_id: smtpConfigId || null,
                recipient_type: recipientType,
                recipient_groups: recipientGroups,
                recipient_manual: recipientManual.trim(),
                cc_manual: ccManual.trim(),
                subject: subject.trim(),
                body: body.trim(),
                body_type: bodyType,
                priority: priority
            };

            node.data('config', updatedConfig);

            // 自動儲存流程
            try {
                await saveWorkflow();
                updateStatus(`✅ 企業郵件設定已套用並儲存`, 'success');
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus(`⚠ 設定已套用，但儲存失敗: ${error.message}`, 'warning');
            }

            console.log('EmailAdapter 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyEmailAdapterConfig = applyEmailAdapterConfig;

        // ============================================
        // BRANCH 條件路由節點函數
        // ============================================

        // 儲存當前編輯中的 BRANCH 規則
        let branchRulesData = [];
        let branchOutgoingEdges = [];
        let branchCurrentNodeId = null;

        // 載入節點的出線
        function loadBranchOutgoingEdges(nodeId, fallback) {
            branchCurrentNodeId = nodeId;
            branchOutgoingEdges = [];

            const node = cy.getElementById(nodeId);
            if (!node) return;

            // 找出所有從此節點出去的邊
            cy.edges().forEach(edge => {
                const edgeData = edge.data();
                if (edgeData.source === nodeId) {
                    const targetNode = cy.getElementById(edgeData.target);
                    const targetLabel = targetNode ? (targetNode.data('label') || targetNode.data('type') || edgeData.target) : edgeData.target;
                    const edgeLabel = edgeData.label || '';

                    branchOutgoingEdges.push({
                        id: edge.id(),
                        target: edgeData.target,
                        targetLabel: targetLabel,
                        edgeLabel: edgeLabel,
                        displayText: edgeLabel ? `${edgeLabel} → ${targetLabel}` : `→ ${targetLabel}`
                    });
                }
            });

            // 更新 fallback 目標選項並恢復已選擇的值
            updateBranchFallbackOptions(fallback);

            console.log('BRANCH 出線載入完成:', branchOutgoingEdges);
        }
        window.loadBranchOutgoingEdges = loadBranchOutgoingEdges;

        // 更新 fallback 目標下拉選單
        function updateBranchFallbackOptions(fallback) {
            const select = document.getElementById('branchFallbackTarget');
            if (!select) return;

            select.innerHTML = '<option value="">選擇目標出線...</option>';
            branchOutgoingEdges.forEach(edge => {
                const option = document.createElement('option');
                option.value = edge.id;
                option.textContent = edge.displayText;
                select.appendChild(option);
            });

            // 恢復已選擇的 fallback target
            if (fallback && fallback.target_edge) {
                select.value = fallback.target_edge;
            }
        }

        // 渲染分支規則列表
        function renderBranchRules(rules, nodeId) {
            branchRulesData = rules.map((r, i) => ({...r, _index: i}));
            branchCurrentNodeId = nodeId;

            const container = document.getElementById('branchRulesList');
            if (!container) return;

            if (branchRulesData.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: #999; font-size: 11px; padding: 15px;">尚無規則，請點擊「新增規則」</div>';
                return;
            }

            let html = '';
            branchRulesData.forEach((rule, ruleIdx) => {
                html += renderBranchRuleItem(rule, ruleIdx);
            });
            container.innerHTML = html;
        }
        window.renderBranchRules = renderBranchRules;

        // 渲染單一規則項目
        function renderBranchRuleItem(rule, ruleIdx) {
            const conditions = rule.conditions || [];
            const targetEdges = rule.target_edges || [];
            const ruleName = rule.name || `規則 ${ruleIdx + 1}`;

            // 建立出線選項 HTML
            let edgeOptionsHtml = '';
            branchOutgoingEdges.forEach(edge => {
                const checked = targetEdges.includes(edge.id) ? 'checked' : '';
                edgeOptionsHtml += `
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 10px; padding: 2px 0; cursor: pointer;">
                        <input type="checkbox" ${checked}
                               onchange="updateBranchRuleTarget(${ruleIdx}, '${edge.id}', this.checked)"
                               style="margin: 0;">
                        <span>${edge.displayText}</span>
                    </label>
                `;
            });

            let conditionsHtml = '';
            conditions.forEach((cond, condIdx) => {
                conditionsHtml += renderBranchConditionItem(ruleIdx, condIdx, cond, condIdx < conditions.length - 1);
            });

            return `
                <div style="border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 8px; background: #fafafa;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; background: #f0f9f0; border-radius: 6px 6px 0 0; border-bottom: 1px solid #e0e0e0;">
                        <input type="text" value="${ruleName}" placeholder="規則名稱"
                               onchange="updateBranchRuleName(${ruleIdx}, this.value)"
                               style="border: none; background: transparent; font-weight: bold; color: #16A34A; font-size: 11px; width: 120px;">
                        <div style="display: flex; gap: 4px;">
                            <button onclick="addBranchCondition(${ruleIdx})" style="padding: 2px 6px; font-size: 9px; border: 1px solid #16A34A; background: white; color: #16A34A; border-radius: 3px; cursor: pointer;">+條件</button>
                            <button onclick="removeBranchRule(${ruleIdx})" style="padding: 2px 6px; font-size: 9px; border: 1px solid #DC2626; background: white; color: #DC2626; border-radius: 3px; cursor: pointer;">×</button>
                        </div>
                    </div>
                    <div style="padding: 8px;">
                        <div style="margin-bottom: 6px;">
                            ${conditionsHtml || '<div style="color: #999; font-size: 10px;">無條件（永遠符合）</div>'}
                        </div>
                        <div style="border-top: 1px dashed #ddd; padding-top: 6px;">
                            <div style="font-size: 10px; color: #666; margin-bottom: 4px;">目標路徑（可多選）：</div>
                            <div style="max-height: 80px; overflow-y: auto;">
                                ${edgeOptionsHtml || '<div style="color: #999; font-size: 10px;">此節點尚無出線</div>'}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // 渲染單一條件
        function renderBranchConditionItem(ruleIdx, condIdx, cond, hasNext) {
            const variable = cond.variable || '';
            const operator = cond.operator || '==';
            const value = cond.value || '';
            const logic = cond.logic || 'AND';

            const operators = [
                { val: '==', label: '==' },
                { val: '!=', label: '!=' },
                { val: '>', label: '>' },
                { val: '>=', label: '>=' },
                { val: '<', label: '<' },
                { val: '<=', label: '<=' },
                { val: 'contains', label: '包含' },
                { val: 'not_contains', label: '不含' },
                { val: 'startswith', label: '開頭' },
                { val: 'endswith', label: '結尾' },
                { val: 'in', label: '在' },
                { val: 'not_in', label: '不在' },
                { val: 'empty', label: '空' },
                { val: 'not_empty', label: '非空' },
                { val: 'matches', label: '正則' }
            ];

            let opOptions = operators.map(op =>
                `<option value="${op.val}" ${operator === op.val ? 'selected' : ''}>${op.label}</option>`
            ).join('');

            const showValue = !['empty', 'not_empty'].includes(operator);

            return `
                <div style="display: flex; gap: 4px; align-items: center; margin-bottom: 4px; flex-wrap: wrap;">
                    <input type="text" value="${variable}" placeholder="\${var}"
                           onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'variable', this.value)"
                           style="width: 70px; padding: 3px 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px; font-family: monospace;">
                    <select onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'operator', this.value)"
                            style="padding: 3px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px;">
                        ${opOptions}
                    </select>
                    ${showValue ? `
                        <input type="text" value="${value}" placeholder="值"
                               onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'value', this.value)"
                               style="width: 60px; padding: 3px 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px;">
                    ` : ''}
                    ${hasNext ? `
                        <select onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'logic', this.value)"
                                style="padding: 3px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px; background: ${logic === 'OR' ? '#fef3c7' : '#dcfce7'};">
                            <option value="AND" ${logic === 'AND' ? 'selected' : ''}>AND</option>
                            <option value="OR" ${logic === 'OR' ? 'selected' : ''}>OR</option>
                        </select>
                    ` : ''}
                    <button onclick="removeBranchCondition(${ruleIdx}, ${condIdx})"
                            style="padding: 2px 5px; font-size: 9px; border: 1px solid #999; background: white; color: #666; border-radius: 3px; cursor: pointer;">×</button>
                </div>
            `;
        }

        // 新增規則
        function addBranchRule() {
            branchRulesData.push({
                name: `規則 ${branchRulesData.length + 1}`,
                conditions: [{ variable: '${status}', operator: '==', value: '' }],
                target_edges: []
            });
            renderBranchRules(branchRulesData, branchCurrentNodeId);
        }
        window.addBranchRule = addBranchRule;

        // 移除規則
        function removeBranchRule(ruleIdx) {
            branchRulesData.splice(ruleIdx, 1);
            renderBranchRules(branchRulesData, branchCurrentNodeId);
        }
        window.removeBranchRule = removeBranchRule;

        // 更新規則名稱
        function updateBranchRuleName(ruleIdx, name) {
            if (branchRulesData[ruleIdx]) {
                branchRulesData[ruleIdx].name = name;
            }
        }
        window.updateBranchRuleName = updateBranchRuleName;

        // 新增條件
        function addBranchCondition(ruleIdx) {
            if (branchRulesData[ruleIdx]) {
                if (!branchRulesData[ruleIdx].conditions) {
                    branchRulesData[ruleIdx].conditions = [];
                }
                branchRulesData[ruleIdx].conditions.push({
                    variable: '',
                    operator: '==',
                    value: '',
                    logic: 'AND'
                });
                renderBranchRules(branchRulesData, branchCurrentNodeId);
            }
        }
        window.addBranchCondition = addBranchCondition;

        // 移除條件
        function removeBranchCondition(ruleIdx, condIdx) {
            if (branchRulesData[ruleIdx] && branchRulesData[ruleIdx].conditions) {
                branchRulesData[ruleIdx].conditions.splice(condIdx, 1);
                renderBranchRules(branchRulesData, branchCurrentNodeId);
            }
        }
        window.removeBranchCondition = removeBranchCondition;

        // 更新條件
        function updateBranchCondition(ruleIdx, condIdx, field, value) {
            if (branchRulesData[ruleIdx] && branchRulesData[ruleIdx].conditions[condIdx]) {
                branchRulesData[ruleIdx].conditions[condIdx][field] = value;

                // 如果運算符改變，可能需要重新渲染（empty/not_empty 不需要 value）
                if (field === 'operator') {
                    renderBranchRules(branchRulesData, branchCurrentNodeId);
                }
            }
        }
        window.updateBranchCondition = updateBranchCondition;

        // 更新規則目標
        function updateBranchRuleTarget(ruleIdx, edgeId, checked) {
            if (branchRulesData[ruleIdx]) {
                if (!branchRulesData[ruleIdx].target_edges) {
                    branchRulesData[ruleIdx].target_edges = [];
                }
                if (checked) {
                    if (!branchRulesData[ruleIdx].target_edges.includes(edgeId)) {
                        branchRulesData[ruleIdx].target_edges.push(edgeId);
                    }
                } else {
                    branchRulesData[ruleIdx].target_edges = branchRulesData[ruleIdx].target_edges.filter(id => id !== edgeId);
                }
            }
        }
        window.updateBranchRuleTarget = updateBranchRuleTarget;

        // 切換 fallback 選項顯示
        function toggleBranchFallbackOptions() {
            const action = document.getElementById('branchFallbackAction')?.value;
            const msgInput = document.getElementById('branchFallbackMessage');
            const targetSelect = document.getElementById('branchFallbackTarget');

            if (msgInput) msgInput.style.display = action === 'route' ? 'none' : 'block';
            if (targetSelect) targetSelect.style.display = action === 'route' ? 'block' : 'none';
        }
        window.toggleBranchFallbackOptions = toggleBranchFallbackOptions;

        // 套用 BRANCH 設定
        function applyBranchConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const fallbackAction = document.getElementById('branchFallbackAction')?.value || 'log';
            const fallbackMessage = document.getElementById('branchFallbackMessage')?.value || '無匹配規則';
            const fallbackTarget = document.getElementById('branchFallbackTarget')?.value || '';

            // 清理規則資料
            const cleanedRules = branchRulesData.map(rule => {
                const cleanRule = {
                    name: rule.name || '',
                    conditions: (rule.conditions || []).filter(c => c.variable),
                    target_edges: rule.target_edges || []
                };
                return cleanRule;
            }).filter(rule => rule.conditions.length > 0 || rule.target_edges.length > 0);

            const fallback = {
                action: fallbackAction
            };
            if (fallbackAction === 'log' || fallbackAction === 'default') {
                fallback.log_message = fallbackMessage;
            }
            if (fallbackAction === 'route' && fallbackTarget) {
                fallback.target_edge = fallbackTarget;
            }

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                rules: cleanedRules,
                fallback: fallback
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ BRANCH 設定已套用（${cleanedRules.length} 條規則）`, 'success');

            console.log('BRANCH 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyBranchConfig = applyBranchConfig;

        // BRANCH 說明頁籤切換
        function switchBranchHelpTab(tab) {
            ['Ops', 'Logic', 'Examples'].forEach(t => {
                const btn = document.getElementById('branchTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
                const content = document.getElementById('branchContent' + t);
                if (content) content.style.display = 'none';
            });

            const tabMap = { 'ops': 'Ops', 'logic': 'Logic', 'examples': 'Examples' };
            const activeBtn = document.getElementById('branchTab' + tabMap[tab]);
            const activeContent = document.getElementById('branchContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#16A34A';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchBranchHelpTab = switchBranchHelpTab;

        // ============================================
        // END BRANCH 函數
        // ============================================

        // 組織樹快取
        let orgTreeData = null;
        let orgTreeLoading = false;
        // 已選擇的簽核者列表 [{code, label, type}]
        let selectedAssigneeList = [];

        // 從節點 config 恢復已選擇的簽核者
        function restoreSelectedAssignees(assigneeType, assigneeValue, assigneeLabel, assigneeListConfig) {
            selectedAssigneeList = [];

            if (assigneeType === 'USER' && assigneeListConfig && assigneeListConfig.length > 0) {
                // 從 assignee_list 恢復（多用戶）
                selectedAssigneeList = assigneeListConfig.map(a => ({
                    code: a.code,
                    label: a.label,
                    type: 'user'
                }));
            } else if (assigneeType === 'USER' && assigneeValue) {
                // 從 assignee_value 恢復（單用戶，向下相容）
                const codes = assigneeValue.split(',').filter(v => v.trim());
                const labels = assigneeLabel ? assigneeLabel.split('、') : codes;
                selectedAssigneeList = codes.map((code, i) => ({
                    code: code.trim(),
                    label: labels[i] || code.trim(),
                    type: 'user'
                }));
            } else if (assigneeType === 'DEPARTMENT' && assigneeValue) {
                // 部門（單選）
                selectedAssigneeList = [{
                    code: assigneeValue,
                    label: assigneeLabel || assigneeValue,
                    type: 'department'
                }];
            }
        }
        window.restoreSelectedAssignees = restoreSelectedAssignees;

        // 初始化組織樹（載入+渲染）
        async function initOrgTree(assigneeType) {
            if (orgTreeLoading) return;

            if (orgTreeData) {
                // 已有資料，延遲渲染（等 DOM 準備好）
                setTimeout(() => {
                    renderOrgTree();
                    renderSelectedAssignees();
                }, 50);
                return;
            }

            orgTreeLoading = true;
            try {
                const response = await fetch('/api/workflows/data/org-tree');
                const result = await response.json();
                if (result.success) {
                    orgTreeData = result.data;
                    // 延遲渲染（等 DOM 準備好）
                    setTimeout(() => {
                        renderOrgTree();
                        renderSelectedAssignees();
                    }, 50);
                }
            } catch (error) {
                console.error('載入組織樹失敗:', error);
            } finally {
                orgTreeLoading = false;
            }
        }
        window.initOrgTree = initOrgTree;

        // 角色列表快取
        let rolesListData = null;

        // 載入角色列表
        async function loadRolesList(selectedValue) {
            if (rolesListData) {
                // 已有快取，延遲渲染（等 DOM 準備好）
                setTimeout(() => {
                    const sel = document.getElementById('formAdapterRoleValue');
                    if (sel) renderRolesSelect(sel, rolesListData, selectedValue);
                }, 50);
                return;
            }

            try {
                const response = await fetch('/api/workflows/data/roles');
                const result = await response.json();
                if (result.success) {
                    rolesListData = result.data;
                    // 延遲渲染（等 DOM 準備好）
                    setTimeout(() => {
                        const sel = document.getElementById('formAdapterRoleValue');
                        if (sel) renderRolesSelect(sel, rolesListData, selectedValue);
                    }, 50);
                }
            } catch (error) {
                console.error('載入角色列表失敗:', error);
                setTimeout(() => {
                    const sel = document.getElementById('formAdapterRoleValue');
                    if (sel) sel.innerHTML = '<option value="">載入失敗</option>';
                }, 50);
            }
        }
        window.loadRolesList = loadRolesList;

        function renderRolesSelect(select, roles, selectedValue) {
            let html = '<option value="">-- 請選擇角色 --</option>';
            for (const role of roles) {
                const selected = role.secure_code === selectedValue ? 'selected' : '';
                html += `<option value="${role.secure_code}" ${selected}>${role.name}</option>`;
            }
            select.innerHTML = html;
        }

        // 載入組織樹（相容舊版）
        async function loadOrgTree() {
            return initOrgTree();
        }
        window.loadOrgTree = loadOrgTree;

        // 渲染組織樹（橫式緊密結構）
        function renderOrgTree() {
            const container = document.getElementById('orgTreeContent');
            if (!container || !orgTreeData) return;

            const assigneeType = document.getElementById('formAdapterAssigneeType')?.value;
            const showUsers = assigneeType === 'USER';
            const showDepts = assigneeType === 'DEPARTMENT';

            // 更新多選提示
            const multiSelectHint = document.getElementById('multiSelectHint');
            if (multiSelectHint) {
                multiSelectHint.style.display = showUsers ? 'inline' : 'none';
            }

            function renderNode(node, level = 0) {
                let html = '';
                const indent = level * 12;

                if (node.type === 'department') {
                    // 部門節點
                    const hasChildren = node.children && node.children.length > 0;
                    const deptIcon = hasChildren ? 'fa-folder-open' : 'fa-folder';
                    const isSelected = selectedAssigneeList.some(a => a.code === node.secure_code);

                    if (showDepts) {
                        // 可選擇部門（單選）
                        html += `<div style="padding: 3px 0; margin-left: ${indent}px; display: flex; align-items: center; gap: 4px;">
                            <i class="fas ${deptIcon}" style="color: #f0ad4e; font-size: 11px;"></i>
                            <span class="org-tree-item org-tree-dept"
                                  data-type="department"
                                  data-code="${node.secure_code}"
                                  data-label="${node.name}"
                                  onclick="selectAssignee(this)"
                                  style="cursor: pointer; padding: 2px 6px; border-radius: 3px; background: ${isSelected ? '#ffe082' : '#fff8e1'}; color: #795548; font-size: 11px; ${isSelected ? 'font-weight: bold; box-shadow: 0 0 0 2px #667eea;' : ''}"
                                  onmouseover="this.style.background='#ffe082'"
                                  onmouseout="this.style.background='${isSelected ? '#ffe082' : '#fff8e1'}'">${node.name}</span>
                        </div>`;
                    } else {
                        // 僅顯示部門名稱（不可選）
                        html += `<div style="padding: 3px 0; margin-left: ${indent}px; display: flex; align-items: center; gap: 4px;">
                            <i class="fas ${deptIcon}" style="color: #f0ad4e; font-size: 11px;"></i>
                            <span style="color: #795548; font-size: 11px; font-weight: 500;">${node.name}</span>
                        </div>`;
                    }

                    // 渲染子節點
                    if (node.children) {
                        for (const child of node.children) {
                            html += renderNode(child, level + 1);
                        }
                    }
                } else if (node.type === 'user' && showUsers) {
                    // 用戶節點（可多選）
                    const isSelected = selectedAssigneeList.some(a => a.code === node.secure_code);
                    html += `<div style="padding: 2px 0; margin-left: ${indent}px; display: flex; align-items: center; gap: 4px;">
                        <i class="fas fa-user" style="color: #5c6bc0; font-size: 10px;"></i>
                        <span class="org-tree-item org-tree-user"
                              data-type="user"
                              data-code="${node.secure_code}"
                              data-label="${node.label}"
                              onclick="toggleAssignee(this)"
                              style="cursor: pointer; padding: 2px 6px; border-radius: 3px; background: ${isSelected ? '#c5cae9' : '#e8eaf6'}; color: #3949ab; font-size: 11px; ${isSelected ? 'font-weight: bold; box-shadow: 0 0 0 2px #667eea;' : ''}"
                              onmouseover="if(!this.classList.contains('selected')) this.style.background='#c5cae9'"
                              onmouseout="if(!this.classList.contains('selected')) this.style.background='${isSelected ? '#c5cae9' : '#e8eaf6'}'">${isSelected ? '✓ ' : ''}${node.label}</span>
                    </div>`;
                }

                return html;
            }

            let html = '';
            for (const node of orgTreeData) {
                html += renderNode(node, 0);
            }

            container.innerHTML = html || '<span style="color: #999;">無資料</span>';
        }
        window.renderOrgTree = renderOrgTree;

        // 切換用戶選擇（多選）
        function toggleAssignee(element) {
            const type = element.dataset.type;
            const code = element.dataset.code;
            const label = element.dataset.label;

            const existingIndex = selectedAssigneeList.findIndex(a => a.code === code);
            if (existingIndex >= 0) {
                // 已選擇，移除
                selectedAssigneeList.splice(existingIndex, 1);
            } else {
                // 未選擇，加入
                selectedAssigneeList.push({ code, label, type });
            }

            // 重新渲染樹和已選列表
            renderOrgTree();
            renderSelectedAssignees();
        }
        window.toggleAssignee = toggleAssignee;

        // 選擇簽核者（單選，用於部門）
        function selectAssignee(element) {
            const type = element.dataset.type;
            const code = element.dataset.code;
            const label = element.dataset.label;

            // 清除之前的選擇，只保留一個
            selectedAssigneeList = [{ code, label, type }];

            // 重新渲染
            renderOrgTree();
            renderSelectedAssignees();
        }
        window.selectAssignee = selectAssignee;

        // 渲染已選擇的簽核者列表
        function renderSelectedAssignees() {
            const container = document.getElementById('selectedAssignees');
            const listContainer = document.getElementById('selectedAssigneesList');
            if (!container || !listContainer) return;

            if (selectedAssigneeList.length === 0) {
                container.style.display = 'none';
                return;
            }

            container.style.display = 'block';
            listContainer.innerHTML = selectedAssigneeList.map(a => `
                <span style="display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; background: ${a.type === 'user' ? '#e8eaf6' : '#fff8e1'}; border-radius: 12px; font-size: 11px;">
                    <i class="fas ${a.type === 'user' ? 'fa-user' : 'fa-building'}" style="font-size: 10px;"></i>
                    ${a.label}
                    <button onclick="removeAssignee('${a.code}')" style="background: none; border: none; color: #999; cursor: pointer; padding: 0; margin-left: 2px;">
                        <i class="fas fa-times" style="font-size: 9px;"></i>
                    </button>
                </span>
            `).join('');
        }
        window.renderSelectedAssignees = renderSelectedAssignees;

        // 移除單個簽核者
        function removeAssignee(code) {
            selectedAssigneeList = selectedAssigneeList.filter(a => a.code !== code);
            renderOrgTree();
            renderSelectedAssignees();
        }
        window.removeAssignee = removeAssignee;

        // 清除所有選擇
        function clearAllAssignees() {
            selectedAssigneeList = [];
            renderOrgTree();
            renderSelectedAssignees();
        }
        window.clearAllAssignees = clearAllAssignees;

        // 清除選擇（相容舊版）
        function clearAssigneeSelection() {
            clearAllAssignees();
        }
        window.clearAssigneeSelection = clearAssigneeSelection;

        // FormAdapter 簽核節點：切換簽核者值輸入框顯示
        function toggleAssigneeValue() {
            const typeSelect = document.getElementById('formAdapterAssigneeType');
            const orgTreeContainer = document.getElementById('orgTreeContainer');
            const roleInputContainer = document.getElementById('roleInputContainer');
            const dynamicInputContainer = document.getElementById('dynamicInputContainer');

            if (!typeSelect) return;

            const assigneeType = typeSelect.value;

            // 隱藏所有輸入區
            if (orgTreeContainer) orgTreeContainer.style.display = 'none';
            if (roleInputContainer) roleInputContainer.style.display = 'none';
            if (dynamicInputContainer) dynamicInputContainer.style.display = 'none';

            // 根據類型顯示對應輸入區
            if (assigneeType === 'USER' || assigneeType === 'DEPARTMENT') {
                if (orgTreeContainer) orgTreeContainer.style.display = 'block';
                // 重新渲染樹（切換 USER/DEPARTMENT 時顯示不同內容）
                renderOrgTree();
            } else if (assigneeType === 'ROLE') {
                if (roleInputContainer) roleInputContainer.style.display = 'block';
            } else if (assigneeType === 'DYNAMIC') {
                if (dynamicInputContainer) dynamicInputContainer.style.display = 'block';
            }

            // 清除之前的選擇
            clearAssigneeSelection();
        }
        window.toggleAssigneeValue = toggleAssigneeValue;

        // 套用 FormAdapter 簽核節點配置
        function applyFormAdapterConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 讀取表單值
            const assigneeType = document.getElementById('formAdapterAssigneeType')?.value || 'INITIATOR';
            let assigneeValue = '';
            let assigneeLabel = '';
            let assigneeList = [];  // 多用戶列表

            // 根據類型取得對應的值
            if (assigneeType === 'USER') {
                // USER 支援多選
                if (selectedAssigneeList.length > 0) {
                    assigneeList = selectedAssigneeList.map(a => ({ code: a.code, label: a.label }));
                    assigneeValue = assigneeList.map(a => a.code).join(',');
                    assigneeLabel = assigneeList.map(a => a.label).join('、');
                }
            } else if (assigneeType === 'DEPARTMENT') {
                // DEPARTMENT 單選
                if (selectedAssigneeList.length > 0) {
                    assigneeValue = selectedAssigneeList[0].code;
                    assigneeLabel = selectedAssigneeList[0].label;
                }
            } else if (assigneeType === 'ROLE') {
                const roleSelect = document.getElementById('formAdapterRoleValue');
                assigneeValue = roleSelect?.value || '';
                assigneeLabel = roleSelect?.selectedOptions[0]?.text || assigneeValue;
            } else if (assigneeType === 'DYNAMIC') {
                assigneeValue = document.getElementById('formAdapterDynamicValue')?.value || '';
                assigneeLabel = assigneeValue;
            }

            const selectionModeRadio = document.querySelector('input[name="selectionMode"]:checked');
            const selectionMode = selectionModeRadio?.value || 'single';
            const allowComment = document.getElementById('formAdapterAllowComment')?.checked !== false;
            const minCommentLength = parseInt(document.getElementById('formAdapterMinCommentLength')?.value) || 0;

            // 驗證
            if (assigneeType !== 'INITIATOR' && !assigneeValue.trim()) {
                updateStatus('請選擇或填寫簽核者', 'warning');
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                assignee_type: assigneeType,
                assignee_value: assigneeValue.trim(),
                assignee_label: assigneeLabel,
                assignee_list: assigneeList,  // 多用戶詳細列表
                selection_mode: selectionMode,
                allow_comment: allowComment,
                min_comment_length: minCommentLength
            };

            node.data('config', updatedConfig);

            const typeLabels = {
                'INITIATOR': '發起人',
                'USER': '指定用戶',
                'ROLE': '指定角色',
                'DEPARTMENT': '指定部門',
                'DYNAMIC': '動態'
            };

            const modeInfo = assigneeList.length > 1 ? `(${assigneeList.length}人，任一人簽)` : '';
            updateStatus(`✅ 簽核設定已套用：${typeLabels[assigneeType]}${assigneeLabel ? ' - ' + assigneeLabel : ''} ${modeInfo}`, 'success');

            console.log('FormAdapter 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyFormAdapterConfig = applyFormAdapterConfig;

        // 更新 End 節點 finish_mode 選擇樣式
        function updateFinishModeSelection(radio) {
            // 重設所有選項的樣式
            document.querySelectorAll('input[name="finishMode"]').forEach(input => {
                const label = input.closest('label');
                if (input.value === 'detach') {
                    label.style.borderColor = input.checked ? '#667eea' : '#e0e0e0';
                    label.style.background = input.checked ? '#f0f4ff' : 'white';
                } else if (input.value === 'cancel') {
                    label.style.borderColor = input.checked ? '#ff6b00' : '#e0e0e0';
                    label.style.background = input.checked ? '#fff8f0' : 'white';
                } else if (input.value === 'strict') {
                    label.style.borderColor = input.checked ? '#28a745' : '#e0e0e0';
                    label.style.background = input.checked ? '#f0fff4' : 'white';
                }
            });
        }
        window.updateFinishModeSelection = updateFinishModeSelection;

        // 套用 END 結束節點配置
        function applyEndConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const finishModeInput = document.querySelector('input[name="finishMode"]:checked');
            if (!finishModeInput) {
                updateStatus('請選擇結束模式', 'warning');
                return;
            }

            const finishMode = finishModeInput.value;

            // 讀取等待秒數
            const waitSecondsInput = document.getElementById('endWaitSeconds');
            const waitSeconds = waitSecondsInput ? parseInt(waitSecondsInput.value) || 3 : 3;

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                finish_mode: finishMode,
                wait_seconds: waitSeconds
            };

            node.data('config', updatedConfig);
            node.data('finishMode', finishMode);

            // 根據模式顯示不同訊息
            const modeNames = {
                'detach': '分離執行模式',
                'cancel': '取消/終止模式',
                'strict': '嚴格等待模式'
            };

            updateStatus(`✅ 結束模式：${modeNames[finishMode]}，等待 ${waitSeconds} 秒`, 'success');

            console.log('END 節點配置已更新:', {
                nodeId: nodeId,
                finish_mode: finishMode,
                wait_seconds: waitSeconds,
                config: updatedConfig
            });
        }
        window.applyEndConfig = applyEndConfig;

        // 更新匯聚節點的模式
        function updateConvergeMode(nodeId, mode) {
            const node = cy.getElementById(nodeId);
            if (!node) {
                updateStatus('找不到節點', 'warning');
                return;
            }

            // 更新節點配置
            const currentConfig = node.data('config') || {};
            currentConfig.mode = mode;
            node.data('config', currentConfig);

            // 更新節點的 anyMode 標記（用於樣式切換）
            if (mode === 'ANY') {
                node.data('anyMode', true);
            } else {
                node.removeData('anyMode');
            }

            // 重新渲染面板以更新選中狀態
            showNodeSettings(node);

            const modeText = mode === 'ANY' ? '任一完成' : '等待全部';
            updateStatus(`✅ 匯聚模式已設為：${modeText}`);

            console.log('匯聚節點配置已更新:', {
                nodeId: nodeId,
                mode: mode
            });
        }

        // ==================== 儲存前自動套用面板設定 ====================

        /**
         * 自動套用當前開啟面板的節點設定
         * 解決用戶在面板填值後忘記按「套用」就直接按「儲存」的問題
         * 此函數靜默執行，不顯示驗證警告、不搶 focus
         */
        function autoApplyCurrentPanel() {
            if (!currentEditingNodeId) return;

            const node = cy.getElementById(currentEditingNodeId);
            if (!node || node.length === 0) return;

            const type = currentEditingNodeType;
            const config = node.data('config') || {};
            let changed = false;

            // 自動套用基本資訊（名稱、描述）
            const labelInput = document.getElementById('node-label-input');
            const descInput = document.getElementById('node-description-input');
            if (labelInput) {
                const newLabel = labelInput.value.trim();
                if (newLabel && newLabel !== node.data('label')) {
                    node.data('label', newLabel);
                }
            }
            if (descInput) {
                const newDesc = descInput.value.trim();
                if (newDesc !== (node.data('description') || '')) {
                    node.data('description', newDesc);
                }
            }

            // 各節點類型的專用設定
            switch (type) {
                case 'OpFieldWrite': {
                    const target = document.getElementById('fieldWriteTargetField');
                    const content = document.getElementById('fieldWriteContent');
                    const contentTypeRadio = document.querySelector('input[name="fieldWriteContentType"]:checked');
                    if (target && content && target.value.trim()) {
                        config.target_field = target.value.trim();
                        config.content = content.value;
                        config.content_type = contentTypeRadio ? contentTypeRadio.value : 'text';
                        changed = true;
                    }
                    break;
                }
                case 'OpSet': {
                    if (typeof opsetOperationsTemp !== 'undefined' && opsetOperationsTemp.length > 0) {
                        config.operations = [...opsetOperationsTemp];
                        changed = true;
                    }
                    break;
                }
                case 'Delay': {
                    const delayInput = document.getElementById('delaySeconds');
                    if (delayInput && delayInput.value) {
                        config.delay_seconds = parseInt(delayInput.value) || 0;
                        changed = true;
                    }
                    break;
                }
                case 'Subflow': {
                    const childSelect = document.getElementById('childFlowSelect');
                    if (childSelect && childSelect.value) {
                        config.childFlowId = childSelect.value;
                        changed = true;
                    }
                    break;
                }
                case 'End': {
                    const finishMode = document.querySelector('input[name="finishMode"]:checked');
                    const waitSeconds = document.getElementById('endWaitSeconds');
                    if (finishMode) {
                        config.finish_mode = finishMode.value;
                        changed = true;
                    }
                    if (waitSeconds && waitSeconds.value) {
                        config.wait_seconds = parseInt(waitSeconds.value) || 3;
                        changed = true;
                    }
                    break;
                }
                case 'FormAdapter': {
                    const assigneeType = document.getElementById('formAdapterAssigneeType');
                    const selectionMode = document.querySelector('input[name="selectionMode"]:checked');
                    const allowComment = document.getElementById('formAdapterAllowComment');
                    const minCommentLen = document.getElementById('formAdapterMinCommentLength');
                    if (assigneeType && assigneeType.value) {
                        config.assignee_type = assigneeType.value;
                        if (assigneeType.value === 'ROLE') {
                            const roleSelect = document.getElementById('formAdapterRoleValue');
                            if (roleSelect && roleSelect.value) {
                                config.assignee_value = roleSelect.value;
                                config.assignee_label = roleSelect.options[roleSelect.selectedIndex]?.text || '';
                            }
                        } else if (assigneeType.value === 'DYNAMIC') {
                            const dynInput = document.getElementById('formAdapterDynamicValue');
                            if (dynInput) config.assignee_value = dynInput.value.trim();
                        }
                        if (typeof selectedAssigneeList !== 'undefined' && selectedAssigneeList.length > 0) {
                            config.assignee_list = [...selectedAssigneeList];
                        }
                        if (selectionMode) config.selection_mode = selectionMode.value;
                        if (allowComment) config.allow_comment = allowComment.checked;
                        if (minCommentLen) config.min_comment_length = parseInt(minCommentLen.value) || 0;
                        changed = true;
                    }
                    break;
                }
                case 'Branch': {
                    const fallbackAction = document.getElementById('branchFallbackAction');
                    const fallbackMsg = document.getElementById('branchFallbackMessage');
                    const fallbackTarget = document.getElementById('branchFallbackTarget');
                    if (typeof branchRulesData !== 'undefined' && branchRulesData.length > 0) {
                        config.rules = [...branchRulesData];
                        changed = true;
                    }
                    if (fallbackAction) {
                        config.fallback = {
                            action: fallbackAction.value,
                            message: fallbackMsg ? fallbackMsg.value : '',
                            target: fallbackTarget ? fallbackTarget.value : ''
                        };
                        changed = true;
                    }
                    break;
                }
                case 'SqlExecutor': {
                    const queryType = document.getElementById('sqlQueryType');
                    const resultVar = document.getElementById('sqlResultVar');
                    if (queryType && queryType.value && resultVar && resultVar.value.trim()) {
                        config.query_type = queryType.value;
                        config.result_var = resultVar.value.trim();
                        changed = true;
                    }
                    break;
                }
                case 'Telegram': {
                    const cfgId = document.getElementById('telegramConfigId');
                    const channel = document.getElementById('telegramChannelName');
                    const msg = document.getElementById('telegramMessage');
                    const parseMode = document.getElementById('telegramParseMode');
                    const disableNotif = document.getElementById('telegramDisableNotification');
                    const disablePreview = document.getElementById('telegramDisableWebPagePreview');
                    if (cfgId && msg) {
                        config.config_id = cfgId.value;
                        config.channel_name = channel ? channel.value : '';
                        config.message = msg.value;
                        if (parseMode) config.parse_mode = parseMode.value;
                        if (disableNotif) config.disable_notification = disableNotif.checked;
                        if (disablePreview) config.disable_web_page_preview = disablePreview.checked;
                        changed = true;
                    }
                    break;
                }
                case 'SysTelegram': {
                    const cfgId = document.getElementById('sysTelegramConfigId');
                    const channel = document.getElementById('sysTelegramChannelName');
                    const msg = document.getElementById('sysTelegramMessage');
                    const parseMode = document.getElementById('sysTelegramParseMode');
                    const disableNotif = document.getElementById('sysTelegramDisableNotification');
                    const disablePreview = document.getElementById('sysTelegramDisableWebPagePreview');
                    if (cfgId && msg) {
                        config.config_id = cfgId.value;
                        config.channel_name = channel ? channel.value : '';
                        config.message = msg.value;
                        if (parseMode) config.parse_mode = parseMode.value;
                        if (disableNotif) config.disable_notification = disableNotif.checked;
                        if (disablePreview) config.disable_web_page_preview = disablePreview.checked;
                        changed = true;
                    }
                    break;
                }
                case 'EmailRelay': {
                    const recipType = document.getElementById('emailRelayRecipientType');
                    const subject = document.getElementById('emailRelaySubject');
                    const body = document.getElementById('emailRelayBody');
                    const bodyType = document.getElementById('emailRelayBodyType');
                    const priority = document.getElementById('emailRelayPriority');
                    const ccManual = document.getElementById('emailRelayCcManual');
                    if (recipType && subject && body) {
                        config.recipient_type = recipType.value;
                        config.subject = subject.value;
                        config.body = body.value;
                        if (bodyType) config.body_type = bodyType.value;
                        if (priority) config.priority = priority.value;
                        if (ccManual) config.cc_manual = ccManual.value.trim();
                        if (recipType.value === 'GROUP') {
                            const groupSelect = document.getElementById('emailRelayGroups');
                            if (groupSelect) {
                                config.recipient_groups = Array.from(groupSelect.selectedOptions).map(o => o.value);
                            }
                        } else if (recipType.value === 'MANUAL') {
                            const manualInput = document.getElementById('emailRelayRecipientManual');
                            if (manualInput) config.recipient_manual = manualInput.value.trim();
                        }
                        changed = true;
                    }
                    break;
                }
                case 'EmailAdapter': {
                    const smtpCfg = document.getElementById('emailAdapterSmtpConfig');
                    const recipType = document.getElementById('emailAdapterRecipientType');
                    const subject = document.getElementById('emailAdapterSubject');
                    const body = document.getElementById('emailAdapterBody');
                    const bodyType = document.getElementById('emailAdapterBodyType');
                    const priority = document.getElementById('emailAdapterPriority');
                    const ccManual = document.getElementById('emailAdapterCcManual');
                    if (recipType && subject && body) {
                        if (smtpCfg) config.smtp_config_id = smtpCfg.value;
                        config.recipient_type = recipType.value;
                        config.subject = subject.value;
                        config.body = body.value;
                        if (bodyType) config.body_type = bodyType.value;
                        if (priority) config.priority = priority.value;
                        if (ccManual) config.cc_manual = ccManual.value.trim();
                        if (recipType.value === 'GROUP') {
                            const groupSelect = document.getElementById('emailAdapterGroups');
                            if (groupSelect) {
                                config.recipient_groups = Array.from(groupSelect.selectedOptions).map(o => o.value);
                            }
                        } else if (recipType.value === 'MANUAL') {
                            const manualInput = document.getElementById('emailAdapterRecipientManual');
                            if (manualInput) config.recipient_manual = manualInput.value.trim();
                        }
                        changed = true;
                    }
                    break;
                }
                // Converge: 即時寫入 config，不需要在此處理
            }

            if (changed) {
                node.data('config', config);
                console.log('💾 autoApply: 自動套用面板設定到', currentEditingNodeId, type);
            }
        }

        // 儲存流程
        async function saveWorkflow() {
            // 儲存前自動套用當前面板的設定
            autoApplyCurrentPanel();

            console.log('💾 saveWorkflow 被調用');
            console.log('  currentWorkflowId:', currentWorkflowId);
            console.log('  currentWorkflowId 類型:', typeof currentWorkflowId);
            console.log('  currentWorkflowId 是否為空:', !currentWorkflowId);

            if (!currentWorkflowId) {
                console.error('❌ currentWorkflowId 未設置！');
                updateStatus('請先選擇或建立一個流程', 'warning');
                return;
            }

            try {
                console.log('💾 開始儲存流程:', currentWorkflowId);

                // 檢查 Cytoscape 實例狀態
                console.log('🔍 Cytoscape 狀態:');
                console.log('  cy 存在:', !!cy);
                console.log('  畫布上的節點總數:', cy.nodes().length);
                console.log('  畫布上的邊總數:', cy.edges().length);

                const nodes = [];
                const relayPoints = [];

                cy.nodes().forEach(node => {
                    if (node.data('type') === 'relay') {
                        // 保存中繼點資訊，包括 taxiControl 和 yellowControl 標記
                        const relayData = {
                            id: node.id(),
                            parentEdge: node.data('parentEdge'),
                            position: node.position()
                        };

                        // 如果是藍點控制點，額外保存標記
                        if (node.data('taxiControl')) {
                            relayData.taxiControl = true;
                        }

                        // 如果是黃點控制點，額外保存標記
                        if (node.data('yellowControl')) {
                            relayData.yellowControl = true;
                            relayData.pointType = node.data('pointType'); // 保存點的類型（nearStar 或 corner）
                        }

                        relayPoints.push(relayData);
                        console.log('  ⚪ 收集中繼點:', relayData.id);
                    } else {
                        const nodeData = {
                            id: node.id(),
                            label: node.data('label'),
                            type: node.data('type'),
                            position: node.position(),
                            config: node.data('config') || {},
                            icon: node.data('icon') || '',
                            description: node.data('description') || ''
                        };

                        // 如果是群組節點，保存樣式資訊
                        if (isGroupNode(node)) {
                            nodeData.isGroup = true;
                            nodeData.borderStyle = node.data('borderStyle') || 'dashed';
                            nodeData.cornerStyle = node.data('cornerStyle') || 'round';
                            // 保存群組顏色
                            if (node.data('groupColor')) {
                                nodeData.groupColor = node.data('groupColor');
                            }
                        }

                        // 如果節點屬於某個群組，保存父群組ID
                        const parent = node.parent();
                        if (parent.length > 0) {
                            nodeData.parent = parent.id();
                        }

                        nodes.push(nodeData);
                        console.log('  🔷 收集節點:', nodeData.type, nodeData.label || nodeData.id, nodeData.isGroup ? ' (群組)' : '', nodeData.parent ? ` (屬於 ${nodeData.parent})` : '');
                    }
                });

                const edges = [];
                cy.edges('[!parentEdge]').forEach(edge => {
                    const hasRelays = getRelayPointsForEdge(edge.id()).length > 0;

                    // 保存線段的基本屬性和樣式
                    const edgeData = {
                        id: edge.id(),
                        source: edge.data('originalSource') || edge.data('source'),
                        target: edge.data('originalTarget') || edge.data('target'),
                        label: edge.data('label') || '',
                        hasRelays: hasRelays
                    };

                    // 保存線段樣式屬性（所有線條類型都儲存）
                    const curveStyle = edge.style('curve-style') || 'straight';
                    const lineColor = edge.style('line-color') || '#95a5a6';

                    edgeData.style = {
                        'curve-style': curveStyle,
                        'width': parseFloat(edge.style('width')) || 3,
                        'line-color': lineColor,
                        'line-style': edge.style('line-style') || 'solid',
                        'target-arrow-shape': edge.style('target-arrow-shape') || 'triangle',
                        'target-arrow-color': edge.style('target-arrow-color') || lineColor,
                        'arrow-scale': parseFloat(edge.style('arrow-scale')) || 1
                    };

                    // 保存曲線特定參數
                    if (curveStyle === 'bezier' || curveStyle === 'unbundled-bezier') {
                        const distances = edge.style('control-point-distances');
                        const weights = edge.style('control-point-weights');
                        if (distances) {
                            const distStr = String(distances).replace(/[\[\]px]/g, '');
                            edgeData.style['control-point-distances'] = [parseFloat(distStr) || 0];
                        }
                        if (weights) {
                            const weightStr = String(weights).replace(/[\[\]]/g, '');
                            edgeData.style['control-point-weights'] = [parseFloat(weightStr) || 0.5];
                        }
                    } else if (curveStyle === 'taxi') {
                        const taxiDirection = edge.style('taxi-direction');
                        const taxiTurn = edge.style('taxi-turn');
                        if (taxiDirection) edgeData.style['taxi-direction'] = taxiDirection;
                        if (taxiTurn) edgeData.style['taxi-turn'] = parseFloat(taxiTurn);
                    }

                    edges.push(edgeData);
                    console.log('  🔗 收集邊:', edgeData.source, '→', edgeData.target);
                });

                // 收集畫布設定
                const canvasSettings = {
                    backgroundColor: canvasBackgroundColor,
                    backgroundId: currentBackgroundId, // 新系統：儲存底圖 ID 而非 base64
                    gridEnabled: gridEnabled,
                    gridStyle: gridStyle,
                    gridSpacing: gridSpacing,
                    paperType: paperType,
                    paperWidth: paperWidth,
                    paperHeight: paperHeight,
                    globalNodeBorder: globalNodeBorder
                };

                // 取得欄位取值設定
                const fieldReadConfig = cy.data('fieldReadConfig') || {};

                const cytoscape_config = {
                    nodes: nodes,
                    edges: edges,
                    relayPoints: relayPoints,
                    canvasSettings: canvasSettings,
                    fieldReadConfig: fieldReadConfig
                };

                console.log('📊 收集統計:');
                console.log('  節點數:', nodes.length);
                console.log('  邊數:', edges.length);
                console.log('  中繼點數:', relayPoints.length);
                console.log('  畫布設定:', canvasSettings);
                console.log('  欄位取值設定:', fieldReadConfig);
                console.log('📤 準備發送的配置:', cytoscape_config);

                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        cytoscape_config: cytoscape_config,
                        graph: cytoscape_config  // 同時保存到 graph 以確保兼容性
                    })
                });

                console.log('📡 後端回應狀態:', response.status, response.statusText);
                const data = await response.json();
                console.log('📦 後端回應資料:', data);

                if (data) {
                    updateStatus('✅ 流程已儲存');
                    console.log('✅ 儲存成功');

                    // 更新版本號顯示（含 revision）
                    if (data.version) {
                        document.getElementById('current-workflow-version').textContent =
                            `版本 ${data.version}${data.revision || ''}`;
                    }

                    // 標記為已成功儲存過
                    hasEverSaved = true;

                    // 儲存後清除 undo stack 和替換 buffer
                    clearUndoState();

                    // 更新初始狀態（儲存後沒有未儲存的變更）
                    updateInitialState();

                    // 清空狀態歷史記錄
                    setTimeout(() => {
                        clearStatusHistory();
                    }, 1000);

                    // 背景生成縮圖（前端）
                    setTimeout(() => {
                        generateAndSaveThumbnail();
                    }, 100);
                } else {
                    updateStatus('儲存失敗', 'warning');
                    console.log('❌ 儲存失敗：後端返回空資料');
                }
            } catch (error) {
                console.error('❌ 儲存流程失敗:', error);
                console.error('錯誤堆疊:', error.stack);
                updateStatus('儲存失敗：' + error.message, 'warning');
            }
        }

        // 生成並儲存縮圖（前端使用 Cytoscape PNG 導出 + Canvas 調整尺寸）
        async function generateAndSaveThumbnail() {
            if (!currentWorkflowId || !cy) {
                console.log('⚠️ 無法生成縮圖：缺少 workflow ID 或 Cytoscape 實例');
                return;
            }

            try {
                console.log('📸 開始生成縮圖...');

                // 先調整視圖以顯示所有內容
                cy.fit(cy.elements(), 50);

                // 使用 Cytoscape 的 PNG 導出功能，獲取 base64 字串
                const pngBase64Raw = cy.png({
                    output: 'base64',
                    bg: 'white',
                    full: true,
                    scale: 2
                });

                console.log('✓ Cytoscape PNG 已生成');
                console.log('  PNG 資料長度:', pngBase64Raw ? pngBase64Raw.length : 0);

                // cy.png() 回傳的是純 base64，需要加上 data URI 前綴
                const pngBase64 = `data:image/png;base64,${pngBase64Raw}`;
                console.log('✓ 已加上 data URI 前綴');

                // 在前端使用 Canvas 生成不同尺寸的縮圖
                const img = new Image();
                img.onload = async function() {
                    console.log('✓ 圖片已載入，開始調整尺寸...');
                    console.log(`  原始尺寸: ${img.width}x${img.height}`);

                    // 生成 2:1 縮圖 (400x200)
                    const canvas2x1 = document.createElement('canvas');
                    canvas2x1.width = 400;
                    canvas2x1.height = 200;
                    const ctx2x1 = canvas2x1.getContext('2d');
                    ctx2x1.fillStyle = 'white';
                    ctx2x1.fillRect(0, 0, 400, 200);

                    // 計算縮放以適應 2:1 比例
                    const scale2x1 = Math.min(400 / img.width, 200 / img.height);
                    const scaledWidth = img.width * scale2x1;
                    const scaledHeight = img.height * scale2x1;
                    const x = (400 - scaledWidth) / 2;
                    const y = (200 - scaledHeight) / 2;

                    ctx2x1.drawImage(img, x, y, scaledWidth, scaledHeight);
                    const thumbnail_2x1 = canvas2x1.toDataURL('image/png');

                    console.log('✓ 2:1 縮圖已生成 (400x200) - 橫向');

                    // 生成 1:1 縮圖 (400x400) - 正方
                    const canvas1x1 = document.createElement('canvas');
                    canvas1x1.width = 400;
                    canvas1x1.height = 400;
                    const ctx1x1 = canvas1x1.getContext('2d');

                    ctx1x1.fillStyle = 'white';
                    ctx1x1.fillRect(0, 0, 400, 400);

                    // 計算縮放以適應 1:1 比例
                    const scale1x1 = Math.min(400 / img.width, 400 / img.height);
                    const scaledWidth1x1 = img.width * scale1x1;
                    const scaledHeight1x1 = img.height * scale1x1;
                    const x1x1 = (400 - scaledWidth1x1) / 2;
                    const y1x1 = (400 - scaledHeight1x1) / 2;

                    ctx1x1.drawImage(img, x1x1, y1x1, scaledWidth1x1, scaledHeight1x1);
                    const thumbnail_1x1 = canvas1x1.toDataURL('image/png');

                    console.log('✓ 1:1 縮圖已生成 (400x400) - 正方');

                    // 生成 1:2 縮圖 (200x400) - 直向
                    const canvas1x2 = document.createElement('canvas');
                    canvas1x2.width = 200;
                    canvas1x2.height = 400;
                    const ctx1x2 = canvas1x2.getContext('2d');

                    ctx1x2.fillStyle = 'white';
                    ctx1x2.fillRect(0, 0, 200, 400);

                    // 計算縮放以適應 1:2 比例
                    const scale1x2 = Math.min(200 / img.width, 400 / img.height);
                    const scaledWidth1x2 = img.width * scale1x2;
                    const scaledHeight1x2 = img.height * scale1x2;
                    const x1x2 = (200 - scaledWidth1x2) / 2;
                    const y1x2 = (400 - scaledHeight1x2) / 2;

                    ctx1x2.drawImage(img, x1x2, y1x2, scaledWidth1x2, scaledHeight1x2);
                    const thumbnail_1x2 = canvas1x2.toDataURL('image/png');

                    console.log('✓ 1:2 縮圖已生成 (200x400) - 直向');

                    // 更新流程，儲存三種尺寸的縮圖
                    console.log('📤 上傳三種尺寸縮圖到後端...');
                    const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            thumbnail_2x1: thumbnail_2x1,
                            thumbnail_1x1: thumbnail_1x1,
                            thumbnail_1x2: thumbnail_1x2
                        })
                    });

                    if (response.ok) {
                        console.log('✅ 縮圖已儲存到資料庫');
                    } else {
                        console.error('❌ 縮圖儲存失敗:', response.status);
                    }
                };

                img.onerror = function(error) {
                    console.error('❌ 圖片載入失敗');
                    console.error('  錯誤:', error);
                };

                img.src = pngBase64;

            } catch (error) {
                console.error('❌ 生成縮圖失敗:', error);
                // 縮圖失敗不影響主流程，只記錄錯誤
            }
        }

        // ==================== 動畫控制函數 ====================

        // 切換流動動畫
        function toggleFlowAnimation() {
            const checkbox = document.getElementById('enable-flow-animation');
            if (checkbox.checked) {
                if (pulseAnimationEnabled) {
                    document.getElementById('enable-pulse-animation').checked = false;
                    stopAllAnimations();
                }
                flowAnimationEnabled = true;
                startFlowAnimation();
            } else {
                flowAnimationEnabled = false;
                stopAllAnimations();
            }
        }

        // 切換脈衝效果
        function togglePulseAnimation() {
            const checkbox = document.getElementById('enable-pulse-animation');
            if (checkbox.checked) {
                if (flowAnimationEnabled) {
                    document.getElementById('enable-flow-animation').checked = false;
                    stopAllAnimations();
                }
                pulseAnimationEnabled = true;
                startPulseAnimation();
            } else {
                pulseAnimationEnabled = false;
                stopAllAnimations();
            }
        }

        // 更新動畫速度
        function updateAnimationSpeed() {
            animationSpeed = parseFloat(document.getElementById('animation-speed').value);
            document.getElementById('animation-speed-value').textContent = animationSpeed.toFixed(1);
            // 重新啟動當前動畫以應用新速度
            if (flowAnimationEnabled) {
                stopAllAnimations();
                flowAnimationEnabled = true;
                startFlowAnimation();
            } else if (pulseAnimationEnabled) {
                stopAllAnimations();
                pulseAnimationEnabled = true;
                startPulseAnimation();
            }
        }

        // 啟動流動動畫
        function startFlowAnimation() {
            cy.edges().forEach(edge => {
                edge.style('line-style', 'dashed');
                edge.style('line-dash-pattern', [10, 5]);
                let offset = 0;
                const baseSpeed = 50;
                const interval = setInterval(() => {
                    offset -= 1;
                    edge.style('line-dash-offset', offset);
                }, baseSpeed / animationSpeed);
                animationIntervals.push(interval);
            });
            updateStatus('流動動畫已啟動');
        }

        // 啟動脈衝效果
        function startPulseAnimation() {
            cy.edges().forEach(edge => {
                let width = parseInt(edge.style('width')) || 3;
                let growing = true;
                const baseSpeed = 100;
                const interval = setInterval(() => {
                    if (growing) {
                        width += 0.5;
                        if (width > 10) growing = false;
                    } else {
                        width -= 0.5;
                        if (width < 2) growing = true;
                    }
                    edge.style('width', width);
                }, baseSpeed / animationSpeed);
                animationIntervals.push(interval);
            });
            updateStatus('脈衝效果已啟動');
        }

        // 停止所有動畫
        function stopAllAnimations() {
            animationIntervals.forEach(interval => clearInterval(interval));
            animationIntervals = [];
            flowAnimationEnabled = false;
            pulseAnimationEnabled = false;
            cy.edges().forEach(edge => {
                edge.style('line-style', 'solid');
                edge.style('line-dash-offset', 0);
                edge.style('width', 1); // 重置為預設寬度
            });
            updateStatus('所有動畫已停止');
        }

        // 改變畫布顏色
        function changeCanvasColor(color) {
            const cyContainer = document.getElementById('cy');
            cyContainer.style.backgroundColor = color;
            document.getElementById('canvas-color-picker').value = color;
            document.getElementById('canvas-color-display').textContent = color;
            updateStatus('畫布顏色已變更: ' + color);
        }

        // 從調色盤改變畫布顏色
        function changeCanvasColorFromPicker() {
            const color = document.getElementById('canvas-color-picker').value;
            changeCanvasColor(color);
        }

        // 置中顯示所有節點
        function fitToView() {
            cy.fit(cy.nodes(':visible'), 50); // 50px padding
            updateStatus('已置中所有節點');
            updateZoomDisplay();
            drawGridBackground(); // 重新繪製網格
        }

        // 縮放到指定倍率
        function zoomTo(level) {
            cy.zoom({
                level: level,
                renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 }
            });
            updateStatus(`縮放至 ${Math.round(level * 100)}%`);
            updateZoomDisplay();
            drawGridBackground(); // 重新繪製網格
        }

        // 放大
        function zoomIn() {
            const currentZoom = cy.zoom();
            const newZoom = Math.min(currentZoom * 1.5, 10); // 最大 10 倍
            cy.zoom({
                level: newZoom,
                renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 }
            });
            updateStatus(`放大至 ${Math.round(newZoom * 100)}%`);
            updateZoomDisplay();
            drawGridBackground(); // 重新繪製網格
        }

        // 縮小
        function zoomOut() {
            const currentZoom = cy.zoom();
            const newZoom = Math.max(currentZoom / 1.5, 0.1); // 最小 0.1 倍
            cy.zoom({
                level: newZoom,
                renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 }
            });
            updateStatus(`縮小至 ${Math.round(newZoom * 100)}%`);
            updateZoomDisplay();
            drawGridBackground(); // 重新繪製網格
        }

        // 更新縮放顯示
        function updateZoomDisplay() {
            const zoomLevel = cy.zoom();
            const zoomPercent = Math.round(zoomLevel * 100);
            document.getElementById('zoom-display').textContent = `${zoomPercent}%`;
        }

        // 底圖管理變數
        let availableBackgrounds = [];
        let currentBackgroundId = null;
        let currentBackgroundUrl = null;

        // 載入底圖列表
        async function loadBackgrounds() {
            try {
                const response = await fetch(`/api/workflows/backgrounds`);
                const data = await response.json();

                if (data.success) {
                    availableBackgrounds = data.data;
                    renderBackgroundList();
                } else {
                    console.error('載入底圖列表失敗:', data.message);
                }
            } catch (error) {
                console.error('載入底圖列表錯誤:', error);
            }
        }

        // 渲染底圖列表（方塊牆模式）
        function renderBackgroundList() {
            const container = document.getElementById('background-list');

            let html = '';

            // 無底圖選項（方塊）
            html += `
                <div onclick="clearBackground()" style="cursor: pointer; border: 2px solid ${currentBackgroundId === null ? '#667eea' : '#e0e0e0'}; border-radius: 8px; background: ${currentBackgroundId === null ? '#f0f4ff' : '#fff'}; padding: 8px; text-align: center; transition: all 0.2s;">
                    <div style="width: 100%; aspect-ratio: 1; background: #f5f5f5; border-radius: 6px; border: 1px solid #ddd; display: flex; align-items: center; justify-content: center; margin-bottom: 6px;">
                        <i class="fas fa-ban" style="color: #999; font-size: 24px;"></i>
                    </div>
                    <div style="font-size: 10px; font-weight: ${currentBackgroundId === null ? 'bold' : 'normal'}; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        無底圖
                    </div>
                    ${currentBackgroundId === null ? '<div style="margin-top: 4px;"><i class="fas fa-check-circle" style="color: #667eea; font-size: 12px;"></i></div>' : ''}
                </div>
            `;

            if (availableBackgrounds.length === 0) {
                html += '<div style="grid-column: 1 / -1; text-align: center; padding: 20px; color: #999; font-size: 11px;">尚無底圖，請先上傳</div>';
            } else {
                html += availableBackgrounds.map(bg => `
                    <div onclick="selectBackground('${bg.id}', '${bg.url}')" style="cursor: pointer; border: 2px solid ${currentBackgroundId === bg.id ? '#667eea' : '#e0e0e0'}; border-radius: 8px; background: ${currentBackgroundId === bg.id ? '#f0f4ff' : '#fff'}; padding: 8px; text-align: center; transition: all 0.2s;">
                        <div style="width: 100%; aspect-ratio: 1; overflow: hidden; border-radius: 6px; border: 1px solid #ddd; margin-bottom: 6px;">
                            <img src="${bg.url}" style="width: 100%; height: 100%; object-fit: cover;">
                        </div>
                        <div style="font-size: 10px; font-weight: ${currentBackgroundId === bg.id ? 'bold' : 'normal'}; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${bg.description || bg.filename}">
                            ${bg.description || bg.filename}
                        </div>
                        <div style="font-size: 8px; color: #999;">
                            ${bg.width} × ${bg.height}
                        </div>
                        ${currentBackgroundId === bg.id ? '<div style="margin-top: 4px;"><i class="fas fa-check-circle" style="color: #667eea; font-size: 12px;"></i></div>' : ''}
                    </div>
                `).join('');
            }

            container.innerHTML = html;
        }

        // 上傳新底圖
        async function uploadNewBackground() {
            const fileInput = document.getElementById('background-upload-input');
            const file = fileInput.files[0];

            if (!file) return;

            // 檢查檔案大小（限制5MB）
            if (file.size > 5 * 1024 * 1024) {
                updateStatus('檔案太大！請選擇小於 5MB 的圖片', 'warning');
                return;
            }

            // 詢問底圖名稱（可選）
            const description = prompt('請輸入底圖名稱（可留空使用檔案名稱）:', '');

            // 如果用戶按下取消，則中止上傳
            if (description === null) {
                fileInput.value = '';
                return;
            }

            // 顯示上傳進度
            document.getElementById('upload-progress').style.display = 'block';

            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('description', description.trim());

                const response = await fetch(`/api/workflows/backgrounds/upload`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    updateStatus('底圖上傳成功');
                    await loadBackgrounds(); // 重新載入列表
                } else {
                    updateStatus('上傳失敗: ' + data.message, 'warning');
                }
            } catch (error) {
                console.error('上傳錯誤:', error);
                updateStatus('上傳失敗', 'warning');
            } finally {
                document.getElementById('upload-progress').style.display = 'none';
                fileInput.value = ''; // 清空檔案選擇
            }
        }

        // 選擇底圖
        function selectBackground(bgId, bgUrl) {
            currentBackgroundId = bgId;
            currentBackgroundUrl = bgUrl;

            // 更新顯示
            const bg = availableBackgrounds.find(b => b.id === bgId);
            const displayName = bg ? (bg.description || bg.filename) : '(無)';
            document.getElementById('current-background-name').value = displayName;

            renderBackgroundList();
            applyBackgroundImage();
            updateStatus('已選擇底圖: ' + displayName);
        }

        // 清除底圖選擇
        function clearBackground() {
            currentBackgroundId = null;
            currentBackgroundUrl = null;
            document.getElementById('current-background-name').value = '(無)';
            renderBackgroundList();
            applyBackgroundImage();
            updateStatus('已清除底圖');
        }

        // 儲存底圖描述
        async function saveBackgroundDescription() {
            if (!currentBackgroundId) {
                updateStatus('請先選擇底圖', 'warning');
                return;
            }

            const nameInput = document.getElementById('current-background-name');
            const newDescription = nameInput.value.trim();

            if (!newDescription) {
                updateStatus('名稱不能為空', 'warning');
                return;
            }

            try {
                const response = await fetch(`/api/workflows/backgrounds/${currentBackgroundId}`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        description: newDescription
                    })
                });

                const data = await response.json();

                if (data.success) {
                    updateStatus('名稱已更新');

                    // 更新 availableBackgrounds 陣列中的描述
                    const bgIndex = availableBackgrounds.findIndex(bg => bg.id === currentBackgroundId);
                    if (bgIndex !== -1) {
                        availableBackgrounds[bgIndex].description = newDescription;
                    }

                    // 重新渲染縮圖牆
                    renderBackgroundList();
                } else {
                    updateStatus('更新失敗: ' + data.message, 'warning');
                }
            } catch (error) {
                console.error('更新錯誤:', error);
                updateStatus('更新失敗', 'warning');
            }
        }

        // 刪除當前底圖
        async function deleteCurrentBackground() {
            if (!currentBackgroundId) {
                updateStatus('請先選擇要刪除的底圖', 'warning');
                return;
            }

            try {
                const response = await fetch(`/api/workflows/backgrounds/${currentBackgroundId}`, {
                    method: 'DELETE'
                });

                const data = await response.json();

                if (data.success) {
                    updateStatus('底圖已刪除');

                    // 切換成無底圖
                    clearBackground();

                    // 重新載入底圖列表
                    await loadBackgrounds();
                } else {
                    updateStatus('刪除失敗: ' + data.message, 'warning');
                }
            } catch (error) {
                console.error('刪除錯誤:', error);
                updateStatus('刪除失敗', 'warning');
            }
        }

        // 套用底圖到畫布（置中顯示）
        function applyBackgroundImage() {
            const cyContainer = document.getElementById('cy');

            // 移除舊的底圖
            const oldBgImage = cyContainer.querySelector('.background-image-layer');
            if (oldBgImage) oldBgImage.remove();

            // 如果有底圖，新增底圖層（置中）
            if (currentBackgroundUrl) {
                const bgLayer = document.createElement('div');
                bgLayer.className = 'background-image-layer';
                bgLayer.style.position = 'absolute';
                bgLayer.style.top = '50%';
                bgLayer.style.left = '50%';
                bgLayer.style.transform = 'translate(-50%, -50%)';
                bgLayer.style.pointerEvents = 'none';
                bgLayer.style.zIndex = '0';
                bgLayer.style.opacity = '0.3';

                // 建立 img 元素以取得實際尺寸
                const img = document.createElement('img');
                img.src = currentBackgroundUrl;
                img.style.display = 'block';
                img.style.maxWidth = 'none'; // 不限制尺寸，以實際大小顯示
                img.style.maxHeight = 'none';

                bgLayer.appendChild(img);
                cyContainer.insertBefore(bgLayer, cyContainer.firstChild);

                updateStatus('底圖已套用（置中顯示）');
            }
        }

        // 切換全域節點邊框
        function toggleGlobalNodeBorder() {
            const checkbox = document.getElementById('global-node-border');
            globalNodeBorder = checkbox.checked;

            // 套用到所有現有節點（排除relay和paper類型）
            cy.nodes('[type!="relay"][type!="paper"]').forEach(node => {
                // 群組節點不處理（它們有自己的邊框樣式）
                if (isGroupNode(node)) return;

                if (globalNodeBorder) {
                    node.removeClass('no-border');
                } else {
                    node.addClass('no-border');
                }
            });

            updateStatus(`節點邊框: ${globalNodeBorder ? '顯示' : '隱藏'}`);
        }

        // ==================== 網格嚴格定位系統 ====================

        // 將畫布座標轉換為網格座標
        function getGridCoord(x, y) {
            return {
                gridX: Math.round(x / gridSpacing),
                gridY: Math.round(y / gridSpacing)
            };
        }

        // 生成網格key
        function getGridKey(gridX, gridY) {
            return `${gridX},${gridY}`;
        }

        // 檢查網格點是否被佔用（考慮2網格間距）
        function isGridOccupied(gridX, gridY, excludeNodeId = null) {
            // 檢查該點及周圍2格範圍（保持間距）
            for (let dx = -2; dx <= 2; dx++) {
                for (let dy = -2; dy <= 2; dy++) {
                    const key = getGridKey(gridX + dx, gridY + dy);
                    const occupier = gridOccupancy.get(key);
                    if (occupier && occupier !== excludeNodeId) {
                        return true; // 被佔用
                    }
                }
            }
            return false; // 可用
        }

        // 標記網格點為已佔用
        function occupyGrid(gridX, gridY, nodeId) {
            const key = getGridKey(gridX, gridY);
            gridOccupancy.set(key, nodeId);
        }

        // 釋放網格點
        function freeGrid(gridX, gridY) {
            const key = getGridKey(gridX, gridY);
            gridOccupancy.delete(key);
        }

        // 取得node佔用的所有網格點
        function getOccupiedGridsForNode(node) {
            const pos = node.position();
            const coord = getGridCoord(pos.x, pos.y);
            // 目前一個node只佔1個格子（中心點），未來可擴展為多格
            return [coord];
        }

        // 找到最近的可用網格點（螺旋搜索）
        function findNearestFreeGrid(targetX, targetY, excludeNodeId = null) {
            const target = getGridCoord(targetX, targetY);

            // 如果目標位置可用，直接返回
            if (!isGridOccupied(target.gridX, target.gridY, excludeNodeId)) {
                return {
                    x: target.gridX * gridSpacing,
                    y: target.gridY * gridSpacing
                };
            }

            // 螺旋搜索最近的可用格子
            const maxRadius = 50; // 最多搜索50格半徑
            for (let radius = 1; radius <= maxRadius; radius++) {
                // 搜索半徑為radius的正方形邊界
                for (let dx = -radius; dx <= radius; dx++) {
                    for (let dy = -radius; dy <= radius; dy++) {
                        // 只檢查邊界上的點（避免重複檢查內部）
                        if (Math.abs(dx) !== radius && Math.abs(dy) !== radius) continue;

                        const gridX = target.gridX + dx;
                        const gridY = target.gridY + dy;

                        if (!isGridOccupied(gridX, gridY, excludeNodeId)) {
                            return {
                                x: gridX * gridSpacing,
                                y: gridY * gridSpacing
                            };
                        }
                    }
                }
            }

            // 如果找不到，返回原始目標位置（不應該發生）
            console.warn('⚠️ 找不到可用的網格點，返回原始位置');
            return {
                x: target.gridX * gridSpacing,
                y: target.gridY * gridSpacing
            };
        }

        // 更新網格佔用映射（重新計算所有node的佔用）
        function updateGridOccupancy() {
            gridOccupancy.clear();

            cy.nodes('[type!="relay"][type!="paper"]').forEach(node => {
                // 群組節點不參與網格佔用計算
                if (isGroupNode(node)) return;

                const grids = getOccupiedGridsForNode(node);
                grids.forEach(coord => {
                    occupyGrid(coord.gridX, coord.gridY, node.id());
                });
            });
        }

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

        // ==================== 線段屬性控制函數 ====================

        // 更新線段選擇器下拉選單
        function updateEdgeSelector() {
            const selector = document.getElementById('edge-selector');
            selector.innerHTML = '<option value="">-- 點擊線段以選取 --</option>';

            cy.edges().forEach(edge => {
                // 過濾掉正交線段和中繼線段（這些是子元素）
                if (edge.data('edgeType') === 'orthogonal-segment') return;
                if (edge.data('edgeType') === 'relay') return;
                if (edge.data('type') === 'relay') return;

                const option = document.createElement('option');
                option.value = edge.id();
                const sourceLabel = edge.source().data('label') || edge.source().id();
                const targetLabel = edge.target().data('label') || edge.target().id();
                // 正交折線加上標記
                const suffix = edge.data('orthogonalEnabled') ? ' [正交]' : '';
                option.textContent = `${sourceLabel} → ${targetLabel}${suffix}`;
                selector.appendChild(option);
            });
        }

        // 當線段被點擊時選取（用於屬性控制）
        function selectEdgeForPropertyControl(edge) {
            currentSelectedEdge = edge;
            const selector = document.getElementById('edge-selector');
            selector.value = edge.id();
            loadEdgeProperties(edge);
            document.getElementById('edge-info').classList.add('show');
            document.getElementById('edge-info').textContent =
                `已選取: ${edge.source().data('label')} → ${edge.target().data('label')}`;

            // 隱藏其他面板，顯示線段屬性控制面板
            document.getElementById('nodeSettings').style.display = 'none';
            document.getElementById('edge-editing-panel').style.display = 'none';
            document.getElementById('edge-control-panel').style.display = 'block';
        }

        // 從下拉選單選擇線段
        function onEdgeSelected() {
            const selector = document.getElementById('edge-selector');
            const edgeId = selector.value;

            if (edgeId) {
                const edge = cy.getElementById(edgeId);
                currentSelectedEdge = edge;
                loadEdgeProperties(edge);
                document.getElementById('edge-info').classList.add('show');
                document.getElementById('edge-info').textContent =
                    `已選取: ${edge.source().data('label')} → ${edge.target().data('label')}`;

                // 高亮選中的線段
                cy.edges().removeClass('highlighted');
                edge.addClass('highlighted');

                // 顯示線段屬性控制面板
                document.getElementById('nodeSettings').style.display = 'none';
                document.getElementById('edge-editing-panel').style.display = 'none';
                document.getElementById('edge-control-panel').style.display = 'block';
            } else {
                currentSelectedEdge = null;
                document.getElementById('edge-info').classList.remove('show');
                cy.edges().removeClass('highlighted');
            }
        }

        // 載入線段屬性到控制面板
        function loadEdgeProperties(edge) {
            // 曲線樣式（檢查是否為正交折線或黃點折線）
            let curveStyle = edge.style('curve-style') || 'bezier';
            if (edge.data('orthogonalEnabled')) {
                curveStyle = 'orthogonal';
            } else if (yellowControlPoints.has(edge.id())) {
                curveStyle = 'yellow-control';
            } else if (curveStyle === 'unbundled-bezier') {
                // unbundled-bezier 在 UI 上顯示為 bezier
                curveStyle = 'bezier';
            }
            document.getElementById('curve-style').value = curveStyle;

            // 載入貝茲曲線控制參數
            if (curveStyle === 'bezier') {
                const distances = edge.style('control-point-distances');
                const weights = edge.style('control-point-weights');
                // 解析陣列格式的值
                let distance = 0;
                let weight = 0.5;
                if (distances) {
                    const distStr = String(distances).replace(/[\[\]px]/g, '');
                    distance = parseInt(distStr) || 0;
                }
                if (weights) {
                    const weightStr = String(weights).replace(/[\[\]]/g, '');
                    weight = parseFloat(weightStr) || 0.5;
                }
                document.getElementById('control-distance').value = distance;
                document.getElementById('control-distance-value').textContent = distance;
                document.getElementById('control-weight').value = weight;
                document.getElementById('control-weight-value').textContent = weight.toFixed(1);
            }

            // 線條屬性
            document.getElementById('line-width').value = parseInt(edge.style('width')) || 1;
            document.getElementById('line-width-value').textContent = parseInt(edge.style('width')) || 1;
            document.getElementById('line-color').value = rgbToHex(edge.style('line-color')) || '#e67e22';
            document.getElementById('line-style').value = edge.style('line-style') || 'solid';

            // 箭頭屬性
            const arrowShape = edge.style('target-arrow-shape') || 'triangle';
            document.getElementById('arrow-shape').value = arrowShape;
            const arrowScale = parseFloat(edge.style('arrow-scale')) || 1;
            document.getElementById('arrow-scale').value = arrowScale;
            document.getElementById('arrow-scale-value').textContent = arrowScale.toFixed(1);

            // 條件分支屬性
            document.getElementById('edge-label').value = edge.data('label') || '';

            // 根據是否為客製線段設定預設段落
            const childSegments = getChildSegments(edge);
            const defaultSegment = childSegments.length > 0 ? 3 : 1; // 客製線預設第3段，一般線預設第1段
            document.getElementById('edge-label-segment').value = edge.data('labelSegment') || defaultSegment;
            document.getElementById('edge-label-rotation').value = edge.data('labelRotation') || 'autorotate';
            document.getElementById('edge-condition').value = edge.data('condition') || '';
            document.getElementById('edge-is-default').checked = edge.data('isDefault') === true;

            // 顯示/隱藏相關控制
            toggleCurveControls(curveStyle);
        }

        // RGB 轉 HEX 格式（用於 color input）
        function rgbToHex(color) {
            if (!color) return null;
            // 如果已經是 hex 格式，直接返回
            if (color.startsWith('#')) return color;
            // 解析 rgb(r, g, b) 格式
            const match = color.match(/rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/i);
            if (match) {
                const r = parseInt(match[1]).toString(16).padStart(2, '0');
                const g = parseInt(match[2]).toString(16).padStart(2, '0');
                const b = parseInt(match[3]).toString(16).padStart(2, '0');
                return `#${r}${g}${b}`;
            }
            return color;
        }

        // 切換曲線控制顯示
        function toggleCurveControls(curveStyle) {
            const bezierControls = document.getElementById('bezier-controls');
            const taxiControls = document.getElementById('taxi-controls');
            const orthogonalControls = document.getElementById('orthogonal-controls');

            // 隱藏所有控制面板
            bezierControls.style.display = 'none';
            taxiControls.style.display = 'none';
            if (orthogonalControls) orthogonalControls.style.display = 'none';

            // 顯示對應的控制面板
            if (curveStyle === 'bezier') {
                bezierControls.style.display = 'block';
            } else if (curveStyle === 'taxi') {
                taxiControls.style.display = 'block';
            } else if (curveStyle === 'orthogonal') {
                if (orthogonalControls) orthogonalControls.style.display = 'block';
            }
        }

        // 更新曲線樣式
        function updateEdgeStyle() {
            if (!currentSelectedEdge) return;

            const curveStyle = document.getElementById('curve-style').value;
            const styleNames = {
                'straight': '直線',
                'bezier': '曲線',
                'taxi': '直角折線'
            };

            // 特殊處理：yellow-control 創建黃點控制點
            if (curveStyle === 'yellow-control') {
                removeOrthogonalControlPoints(currentSelectedEdge.id());  // 先移除正交折線
                currentSelectedEdge.style('curve-style', 'straight');
                toggleCurveControls('straight');
                createYellowControlPoints(currentSelectedEdge);
                updateStatus(`✓ 已切換為直角折線(黃點)，4個黃點保持水平垂直`);
            }
            // 特殊處理：orthogonal 正交折線
            else if (curveStyle === 'orthogonal') {
                // 先移除其他類型的控制點
                removeTaxiControlPoints(currentSelectedEdge.id());
                removeYellowControlPoints(currentSelectedEdge.id());
                removeOrthogonalControlPoints(currentSelectedEdge.id());

                // 創建正交折線控制點
                createOrthogonalControlPoints(currentSelectedEdge);
                toggleCurveControls('orthogonal');

                // 智慧連動
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, 'orthogonal');
                if (reverseEdgeResult) {
                    // 也為反向邊創建正交控制點
                    const reverseEdge = findReverseEdge(currentSelectedEdge);
                    if (reverseEdge) {
                        removeOrthogonalControlPoints(reverseEdge.id());
                        createOrthogonalControlPoints(reverseEdge);
                    }
                    updateStatus(`✓ 已切換為正交折線（反向邊已同步）`);
                } else {
                    updateStatus(`✓ 已切換為正交折線，點擊線段拖動調整`);
                }
            }
            else {
                // 移除 taxi、黃點、正交折線控制點（如果有）
                removeTaxiControlPoints(currentSelectedEdge.id());
                removeYellowControlPoints(currentSelectedEdge.id());
                removeOrthogonalControlPoints(currentSelectedEdge.id());

                // 曲線使用 unbundled-bezier 以支援手動控制
                if (curveStyle === 'bezier') {
                    const distance = parseInt(document.getElementById('control-distance').value) || 0;
                    const weight = parseFloat(document.getElementById('control-weight').value) || 0.5;
                    currentSelectedEdge.style({
                        'curve-style': 'unbundled-bezier',
                        'control-point-distances': [distance],
                        'control-point-weights': [weight]
                    });
                } else {
                    currentSelectedEdge.style('curve-style', curveStyle);
                }

                toggleCurveControls(curveStyle);

                // 智慧連動：自動同步反向邊的曲線樣式
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, curveStyle);
                if (reverseEdgeResult) {
                    updateStatus(`✓ 曲線樣式已更新為: ${styleNames[curveStyle] || curveStyle}（反向邊已同步）`);
                } else {
                    updateStatus(`✓ 曲線樣式已更新為: ${styleNames[curveStyle] || curveStyle}`);
                }
            }
        }

        // 智慧連動：同步反向邊的曲線樣式
        function syncReverseEdgeCurveStyle(edge, curveStyle) {
            const sourceId = edge.source().id();
            const targetId = edge.target().id();

            // 找反向邊（target → source）
            const reverseEdge = cy.edges().filter(e => {
                return e.source().id() === targetId &&
                       e.target().id() === sourceId &&
                       e.id() !== edge.id() &&
                       (!e.data('edgeType') || e.data('edgeType') !== 'relay');
            });

            if (reverseEdge.length > 0) {
                reverseEdge.forEach(re => {
                    // 曲線使用 unbundled-bezier
                    if (curveStyle === 'bezier') {
                        const distance = parseInt(document.getElementById('control-distance').value) || 0;
                        const weight = parseFloat(document.getElementById('control-weight').value) || 0.5;
                        re.style({
                            'curve-style': 'unbundled-bezier',
                            'control-point-distances': [-distance], // 反向邊使用相反的距離
                            'control-point-weights': [weight]
                        });
                    } else {
                        re.style('curve-style', curveStyle);
                    }
                    console.log(`🔗 自動同步反向邊 ${re.id()} 曲線樣式為: ${curveStyle}`);
                });
                return true;
            }
            return false;
        }

        // 更新貝茲曲線控制
        function updateBezierControls() {
            if (!currentSelectedEdge) return;

            const distance = parseInt(document.getElementById('control-distance').value);
            const weight = parseFloat(document.getElementById('control-weight').value);

            document.getElementById('control-distance-value').textContent = distance;
            document.getElementById('control-weight-value').textContent = weight.toFixed(1);

            // 使用 unbundled-bezier 以支援手動控制點
            // control-point-distances: 控制點與直線的垂直距離
            // control-point-weights: 控制點在邊上的位置 (0=起點, 1=終點)
            currentSelectedEdge.style({
                'curve-style': 'unbundled-bezier',
                'control-point-distances': [distance],
                'control-point-weights': [weight]
            });

            // 同步更新子線段
            const childSegments = getChildSegments(currentSelectedEdge);
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style({
                        'curve-style': 'unbundled-bezier',
                        'control-point-distances': [distance],
                        'control-point-weights': [weight]
                    });
                }
            });

            updateStatus('貝茲曲線參數已更新');
        }

        // 更新計程車曲線控制
        function updateTaxiControls() {
            if (!currentSelectedEdge) return;

            const direction = document.getElementById('taxi-direction').value;
            const turn = parseInt(document.getElementById('taxi-turn').value);

            document.getElementById('taxi-turn-value').textContent = turn;

            currentSelectedEdge.style({
                'taxi-direction': direction,
                'taxi-turn': turn,
                'taxi-turn-min-distance': 10
            });

            updateStatus('計程車曲線參數已更新');
        }

        // 更新線條樣式
        // 獲取線段的所有子線段（包括正交、黃點、taxi、polyline）
        function getChildSegments(edge) {
            const edgeId = edge.id();
            const childEdges = [];

            // 正交折線子線段
            if (orthogonalControlPoints.has(edgeId)) {
                const data = orthogonalControlPoints.get(edgeId);
                if (data && data.relayEdges) {
                    childEdges.push(...data.relayEdges);
                }
            }

            // 黃點折線 - 找到所有 parentEdge 為此邊的線段
            // taxi 折線和 polyline 也是用 parentEdge
            cy.edges(`[parentEdge="${edgeId}"]`).forEach(e => {
                childEdges.push(e);
            });

            return childEdges;
        }

        function updateLineStyle() {
            if (!currentSelectedEdge) return;

            const width = parseInt(document.getElementById('line-width').value);
            const color = document.getElementById('line-color').value;
            const style = document.getElementById('line-style').value;

            document.getElementById('line-width-value').textContent = width;

            const lineStyle = {
                'width': width,
                'line-color': color,
                'line-style': style,
                'target-arrow-color': color
            };

            // 更新原始邊
            currentSelectedEdge.style(lineStyle);

            // 更新所有子線段
            const childSegments = getChildSegments(currentSelectedEdge);
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style(lineStyle);
                }
            });

            updateStatus('線條樣式已更新');
        }

        // 更新箭頭樣式
        function updateArrowStyle() {
            if (!currentSelectedEdge) return;

            const shape = document.getElementById('arrow-shape').value;
            const scale = parseFloat(document.getElementById('arrow-scale').value);

            document.getElementById('arrow-scale-value').textContent = scale.toFixed(1);

            const arrowStyle = {
                'target-arrow-shape': shape,
                'arrow-scale': scale,
                'target-arrow-color': document.getElementById('line-color').value
            };

            // 更新原始邊
            currentSelectedEdge.style(arrowStyle);

            // 更新所有子線段（只有最後一段需要箭頭）
            const childSegments = getChildSegments(currentSelectedEdge);
            if (childSegments.length > 0) {
                // 先將所有子線段的箭頭移除
                childSegments.forEach(seg => {
                    if (seg && seg.length > 0) {
                        seg.style({
                            'target-arrow-shape': 'none',
                            'arrow-scale': scale
                        });
                    }
                });
                // 最後一段加上箭頭
                const lastSeg = childSegments[childSegments.length - 1];
                if (lastSeg && lastSeg.length > 0) {
                    lastSeg.style(arrowStyle);
                }
            }

            updateStatus('箭頭樣式已更新');
        }

        // 更新邊的標籤
        function updateEdgeLabel() {
            if (!currentSelectedEdge) return;

            const label = document.getElementById('edge-label').value;
            const segmentIndex = parseInt(document.getElementById('edge-label-segment').value); // 1-based (人類習慣)
            const rotation = document.getElementById('edge-label-rotation').value;

            // 計算旋轉值
            let textRotation;
            if (rotation === 'autorotate') {
                textRotation = 'autorotate';
            } else {
                textRotation = parseInt(rotation) * Math.PI / 180; // 轉為弧度
            }

            // 儲存標籤設定到原始邊的 data
            currentSelectedEdge.data('label', label);
            currentSelectedEdge.data('labelSegment', segmentIndex);
            currentSelectedEdge.data('labelRotation', rotation);

            // 獲取所有子線段
            const childSegments = getChildSegments(currentSelectedEdge);

            // 先清除所有線段的標籤
            currentSelectedEdge.style('label', '');
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style('label', '');
                    seg.data('label', '');
                }
            });

            // 設定標籤樣式
            const labelStyle = {
                'label': label,
                'font-size': '12px',
                'text-rotation': textRotation,
                'text-margin-y': -10,
                'text-background-color': '#ffffff',
                'text-background-opacity': 0.8,
                'text-background-padding': '3px'
            };

            // 根據選擇的段落顯示標籤
            if (childSegments.length === 0) {
                // 一般線段（沒有子線段），顯示在原始邊上
                currentSelectedEdge.style(labelStyle);
            } else {
                // 客製線段，顯示在指定的子線段上
                // segmentIndex 是 1-based，轉換為 0-based
                const targetIndex = segmentIndex - 1;
                if (targetIndex >= 0 && targetIndex < childSegments.length) {
                    const targetSeg = childSegments[targetIndex];
                    if (targetSeg && targetSeg.length > 0) {
                        targetSeg.style(labelStyle);
                        targetSeg.data('label', label);
                    }
                } else {
                    // 如果選擇的段落超出範圍，顯示在中間段
                    const midIndex = Math.floor(childSegments.length / 2);
                    const midSeg = childSegments[midIndex];
                    if (midSeg && midSeg.length > 0) {
                        midSeg.style(labelStyle);
                        midSeg.data('label', label);
                    }
                }
            }

            updateStatus('邊標籤已更新');
        }

        // 更新邊的條件表達式
        function updateEdgeCondition() {
            if (!currentSelectedEdge) return;

            const condition = document.getElementById('edge-condition').value;
            currentSelectedEdge.data('condition', condition);

            updateStatus('條件表達式已更新');
        }

        // 更新邊是否為預設路徑
        function updateEdgeIsDefault() {
            if (!currentSelectedEdge) return;

            const isDefault = document.getElementById('edge-is-default').checked;
            currentSelectedEdge.data('isDefault', isDefault);

            // 如果設為預設，取消其他邊的預設狀態
            if (isDefault) {
                const sourceNode = currentSelectedEdge.source();
                cy.edges().forEach(edge => {
                    if (edge.source().id() === sourceNode.id() && edge.id() !== currentSelectedEdge.id()) {
                        edge.data('isDefault', false);
                    }
                });
            }

            updateStatus(isDefault ? '已設為預設路徑' : '已取消預設路徑');
        }

        // 測試條件表達式
        function testConditionExpression() {
            const condition = document.getElementById('edge-condition').value;

            if (!condition || condition.trim() === '') {
                updateStatus('請先輸入條件表達式', 'warning');
                return;
            }

            // 彈出對話框讓用戶輸入測試變數
            const varsInput = prompt(
                '請輸入測試變數 (JSON 格式):\n\n' +
                '範例: {"age": 25, "status": "approved", "score": 85}\n\n' +
                '按「確定」開始測試:',
                '{"age": 25, "status": "approved"}'
            );

            if (!varsInput) return;

            try {
                // 解析 JSON
                const testVars = JSON.parse(varsInput);

                // 模擬後端的評估邏輯
                const context = {
                    vars: testVars,
                    Math: Math,
                    String: String,
                    Number: Number,
                    Boolean: Boolean,
                    Date: Date,
                    includes: (str, search) => String(str).includes(search),
                    startsWith: (str, search) => String(str).startsWith(search),
                    endsWith: (str, search) => String(str).endsWith(search),
                    length: (arr) => arr?.length || 0,
                    isEmpty: (val) => !val || (Array.isArray(val) && val.length === 0),
                    isNull: (val) => val === null || val === undefined
                };

                const func = new Function(...Object.keys(context), `
                    'use strict';
                    return (${condition});
                `);

                const result = func(...Object.values(context));

                updateStatus(
                    `測試結果: ${result ? '✅ true' : '❌ false'}\n\n` +
                    `條件表達式: ${condition}\n` +
                    `測試變數: ${JSON.stringify(testVars, null, 2)}`,
                    'warning'
                );
            } catch (error) {
                updateStatus(`測試失敗:\n\n${error.message}\n\n請檢查條件表達式是否正確`, 'warning');
            }
        }

        // 套用預設樣式
        function applyPreset(presetName) {
            if (!currentSelectedEdge) {
                updateStatus('請先選擇一條線段', 'warning');
                return;
            }

            const presets = {
                'straight': {
                    'curve-style': 'straight',
                    'width': 1,
                    'line-color': '#95a5a6',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1
                },
                'bezier': {
                    'curve-style': 'bezier',
                    'width': 1,
                    'line-color': '#667eea',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1,
                    'control-point-step-size': 0,
                    'control-point-weight': 0.5
                },
                'polyline': {
                    'curve-style': 'straight',
                    'width': 1,
                    'line-color': '#2196F3',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1
                },
                'taxi': {
                    'curve-style': 'taxi',
                    'width': 1,
                    'line-color': '#34495e',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1,
                    'taxi-direction': 'auto',
                    'taxi-turn': 20
                }
            };

            const preset = presets[presetName];
            if (preset) {
                // 分段折線需要提示使用者
                if (presetName === 'polyline') {
                    updateStatus('分段折線需要使用 Shift + 點擊線段 來添加中繼點', 'warning');
                }

                currentSelectedEdge.style(preset);
                loadEdgeProperties(currentSelectedEdge);

                // 智慧連動：同步反向邊的曲線樣式
                const curveStyle = preset['curve-style'];
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, curveStyle);
                if (reverseEdgeResult) {
                    updateStatus(`已套用預設: ${presetName}（反向邊已同步）`);
                } else {
                    updateStatus(`已套用預設: ${presetName}`);
                }
            }
        }

        // 刪除當前選中的線段
        function deleteSelectedEdge() {
            if (!currentSelectedEdge) {
                updateStatus('請先選擇一條線段', 'warning');
                return;
            }

            pushUndoState();
            const edgeId = currentSelectedEdge.id();
            const sourceLabel = currentSelectedEdge.source().data('label') || currentSelectedEdge.source().id();
            const targetLabel = currentSelectedEdge.target().data('label') || currentSelectedEdge.target().id();

            // 移除相關的控制點（正交、黃點、taxi）
            removeOrthogonalControlPoints(edgeId);
            removeYellowControlPoints(edgeId);
            removeTaxiControlPoints(edgeId);

            // 移除所有關聯的中繼點和中繼線段
            cy.nodes(`[type="relay"][parentEdge="${edgeId}"]`).remove();
            cy.edges(`[parentEdge="${edgeId}"]`).remove();

            // 移除原始邊
            currentSelectedEdge.remove();

            // 清除選擇狀態
            currentSelectedEdge = null;
            document.getElementById('edge-selector').value = '';
            document.getElementById('edge-info').classList.remove('show');
            document.getElementById('edge-info').textContent = '請先選擇一條線段以調整其屬性';

            // 更新線段選擇器
            updateEdgeSelector();

            updateStatus(`已刪除線段: ${sourceLabel} → ${targetLabel}`);
        }

        // ==================== 直角折線座標控制 ====================

        let currentTaxiEdge = null; // 當前正在調整的直角折線

        // 顯示直角折線座標控制面板
        function showTaxiCoordPanel(edge) {
            currentTaxiEdge = edge;

            // 隱藏其他面板
            document.getElementById('nodeSettings').style.display = 'none';
            document.getElementById('edge-editing-panel').style.display = 'none';
            document.getElementById('edge-control-panel').style.display = 'none';
            document.getElementById('taxi-coord-panel').style.display = 'block';

            // 獲取控制點
            const controls = taxiControlPoints.get(edge.id());
            if (!controls || controls.length === 0) {
                updateStatus('錯誤：找不到直角折線控制點');
                return;
            }

            // 獲取第一個控制點的位置（兩個控制點的Y座標相同）
            const ctrl = controls[0];
            const pos = ctrl.position();

            // 判斷中間段是垂直還是水平
            const sourceId = edge.data('originalSource') || edge.data('source');
            const targetId = edge.data('originalTarget') || edge.data('target');
            const source = cy.getElementById(sourceId);
            const target = cy.getElementById(targetId);

            if (source.length === 0 || target.length === 0) {
                updateStatus('錯誤：找不到來源或目標節點');
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            // 判斷中間段方向
            const isHorizontal = Math.abs(sourcePos.x - targetPos.x) > Math.abs(sourcePos.y - targetPos.y);

            if (isHorizontal) {
                // 水平線 - 調整 Y 座標
                document.getElementById('taxi-segment-type').textContent = '水平線';
                document.getElementById('taxi-current-coord').textContent = `Y = ${pos.y.toFixed(1)}`;
                document.getElementById('taxi-coord-input').value = Math.round(pos.y);
            } else {
                // 垂直線 - 調整 X 座標
                document.getElementById('taxi-segment-type').textContent = '垂直線';
                document.getElementById('taxi-current-coord').textContent = `X = ${pos.x.toFixed(1)}`;
                document.getElementById('taxi-coord-input').value = Math.round(pos.x);
            }

            updateStatus(`調整直角折線: ${edge.id()}`);
        }

        // 調整直角折線座標（相對調整）
        function adjustTaxiCoord(delta) {
            if (!currentTaxiEdge) {
                updateStatus('請先選擇一條直角折線', 'warning');
                return;
            }

            const controls = taxiControlPoints.get(currentTaxiEdge.id());
            if (!controls || controls.length === 0) {
                updateStatus('錯誤：找不到控制點', 'warning');
                return;
            }

            // 獲取來源和目標節點
            const sourceId = currentTaxiEdge.data('originalSource') || currentTaxiEdge.data('source');
            const targetId = currentTaxiEdge.data('originalTarget') || currentTaxiEdge.data('target');
            const source = cy.getElementById(sourceId);
            const target = cy.getElementById(targetId);
            const sourcePos = source.position();
            const targetPos = target.position();

            // 判斷方向
            const isHorizontal = Math.abs(sourcePos.x - targetPos.x) > Math.abs(sourcePos.y - targetPos.y);

            // 調整所有控制點
            controls.forEach(ctrl => {
                const pos = ctrl.position();
                if (isHorizontal) {
                    // 水平線 - 調整 Y
                    ctrl.position({ x: pos.x, y: pos.y + delta });
                } else {
                    // 垂直線 - 調整 X
                    ctrl.position({ x: pos.x + delta, y: pos.y });
                }
            });

            // 更新顯示
            showTaxiCoordPanel(currentTaxiEdge);
            updateStatus(`已調整 ${delta > 0 ? '+' : ''}${delta}`);
        }

        // 設置直角折線座標（絕對設置）
        function setTaxiCoord() {
            if (!currentTaxiEdge) {
                updateStatus('請先選擇一條直角折線', 'warning');
                return;
            }

            const newValue = parseFloat(document.getElementById('taxi-coord-input').value);
            if (isNaN(newValue)) {
                updateStatus('請輸入有效的數字', 'warning');
                return;
            }

            const controls = taxiControlPoints.get(currentTaxiEdge.id());
            if (!controls || controls.length === 0) {
                updateStatus('錯誤：找不到控制點', 'warning');
                return;
            }

            // 獲取來源和目標節點
            const sourceId = currentTaxiEdge.data('originalSource') || currentTaxiEdge.data('source');
            const targetId = currentTaxiEdge.data('originalTarget') || currentTaxiEdge.data('target');
            const source = cy.getElementById(sourceId);
            const target = cy.getElementById(targetId);
            const sourcePos = source.position();
            const targetPos = target.position();

            // 判斷方向
            const isHorizontal = Math.abs(sourcePos.x - targetPos.x) > Math.abs(sourcePos.y - targetPos.y);

            // 設置所有控制點
            controls.forEach(ctrl => {
                const pos = ctrl.position();
                if (isHorizontal) {
                    // 水平線 - 設置 Y
                    ctrl.position({ x: pos.x, y: newValue });
                } else {
                    // 垂直線 - 設置 X
                    ctrl.position({ x: newValue, y: pos.y });
                }
            });

            // 更新顯示
            showTaxiCoordPanel(currentTaxiEdge);
            updateStatus(`已設置座標為 ${newValue}`);
        }

        // 關閉直角折線座標控制面板
        function closeTaxiCoordPanel() {
            currentTaxiEdge = null;
            document.getElementById('taxi-coord-panel').style.display = 'none';
            updateStatus('已關閉座標控制面板');
        }

        // 繪製網格背景
        function drawGridBackground() {
            const container = document.getElementById('cy');
            const existingCanvas = container.querySelector('.grid-canvas');
            if (existingCanvas) {
                existingCanvas.remove();
            }

            if (!gridEnabled) return;

            const canvas = document.createElement('canvas');
            canvas.className = 'grid-canvas';
            canvas.width = container.offsetWidth * 2; // 2倍解析度
            canvas.height = container.offsetHeight * 2;
            canvas.style.position = 'absolute';
            canvas.style.top = '0';
            canvas.style.left = '0';
            canvas.style.width = '100%';
            canvas.style.height = '100%';
            canvas.style.pointerEvents = 'none';
            canvas.style.zIndex = '0';
            container.style.position = 'relative';
            container.insertBefore(canvas, container.firstChild);

            const ctx = canvas.getContext('2d');
            const zoom = cy.zoom();
            const pan = cy.pan();

            // 縮放低於 75% 時不繪製網格
            if (zoom < 0.75) return;

            // 計算可視範圍（模型座標）
            const extent = cy.extent();
            const viewportWidth = container.offsetWidth / zoom;
            const viewportHeight = container.offsetHeight / zoom;

            // 擴展繪製範圍，確保整個可視區域都有網格
            const startX = Math.floor((extent.x1 - viewportWidth) / gridSpacing) * gridSpacing;
            const endX = Math.ceil((extent.x2 + viewportWidth) / gridSpacing) * gridSpacing;
            const startY = Math.floor((extent.y1 - viewportHeight) / gridSpacing) * gridSpacing;
            const endY = Math.ceil((extent.y2 + viewportHeight) / gridSpacing) * gridSpacing;

            // 模型座標轉螢幕座標的函數
            function modelToScreen(modelX, modelY) {
                return {
                    x: (modelX * zoom + pan.x) * 2,
                    y: (modelY * zoom + pan.y) * 2
                };
            }

            // 淡色系配色
            if (gridStyle === 'lines') {
                ctx.strokeStyle = 'rgba(102, 126, 234, 0.15)'; // 淡紫色
                ctx.lineWidth = 1;

                // 繪製垂直線
                for (let x = startX; x <= endX; x += gridSpacing) {
                    const topPoint = modelToScreen(x, startY);
                    const bottomPoint = modelToScreen(x, endY);
                    ctx.beginPath();
                    ctx.moveTo(topPoint.x, topPoint.y);
                    ctx.lineTo(bottomPoint.x, bottomPoint.y);
                    ctx.stroke();
                }

                // 繪製水平線
                for (let y = startY; y <= endY; y += gridSpacing) {
                    const leftPoint = modelToScreen(startX, y);
                    const rightPoint = modelToScreen(endX, y);
                    ctx.beginPath();
                    ctx.moveTo(leftPoint.x, leftPoint.y);
                    ctx.lineTo(rightPoint.x, rightPoint.y);
                    ctx.stroke();
                }
            } else if (gridStyle === 'dots') {
                ctx.fillStyle = 'rgba(102, 126, 234, 0.3)'; // 淡紫色點

                // 繪製點陣
                for (let x = startX; x <= endX; x += gridSpacing) {
                    for (let y = startY; y <= endY; y += gridSpacing) {
                        const point = modelToScreen(x, y);
                        ctx.beginPath();
                        ctx.arc(point.x, point.y, 2, 0, Math.PI * 2);
                        ctx.fill();
                    }
                }
            }
        }

        // 切換頁籤
        function switchTab(tabName) {
            // 取得所有頁籤按鈕
            const canvasTab = document.getElementById('tab-canvas');
            const controlsTab = document.getElementById('tab-controls');
            const groupsTab = document.getElementById('tab-groups');
            const formfieldsTab = document.getElementById('tab-formfields');
            const opsetvarsTab = document.getElementById('tab-opsetvars');

            // 取得所有內容區
            const canvasContent = document.getElementById('canvas-tab-content');
            const controlsContent = document.getElementById('controls-tab-content');
            const groupsContent = document.getElementById('groups-tab-content');
            const formfieldsContent = document.getElementById('formfields-tab-content');
            const opsetvarsContent = document.getElementById('opsetvars-tab-content');

            // 重置所有頁籤為未啟用狀態
            canvasTab.style.background = '#e0e0e0';
            canvasTab.style.color = '#666';
            canvasTab.style.borderBottom = 'none';
            controlsTab.style.background = '#e0e0e0';
            controlsTab.style.color = '#666';
            controlsTab.style.borderBottom = 'none';
            groupsTab.style.background = '#e0e0e0';
            groupsTab.style.color = '#666';
            groupsTab.style.borderBottom = 'none';
            if (formfieldsTab) {
                formfieldsTab.style.background = '#e0e0e0';
                formfieldsTab.style.color = '#666';
                formfieldsTab.style.borderBottom = 'none';
            }
            if (opsetvarsTab) {
                opsetvarsTab.style.background = '#e0e0e0';
                opsetvarsTab.style.color = '#666';
                opsetvarsTab.style.borderBottom = 'none';
            }

            // 隱藏所有內容
            canvasContent.style.display = 'none';
            controlsContent.style.display = 'none';
            groupsContent.style.display = 'none';
            if (formfieldsContent) {
                formfieldsContent.style.display = 'none';
            }
            if (opsetvarsContent) {
                opsetvarsContent.style.display = 'none';
            }

            // 啟用選中的頁籤和內容
            if (tabName === 'canvas') {
                canvasTab.style.background = '#667eea';
                canvasTab.style.color = 'white';
                canvasTab.style.borderBottom = '3px solid #667eea';
                canvasContent.style.display = 'flex';
            } else if (tabName === 'controls') {
                controlsTab.style.background = '#667eea';
                controlsTab.style.color = 'white';
                controlsTab.style.borderBottom = '3px solid #667eea';
                controlsContent.style.display = 'flex';
            } else if (tabName === 'groups') {
                groupsTab.style.background = '#667eea';
                groupsTab.style.color = 'white';
                groupsTab.style.borderBottom = '3px solid #667eea';
                groupsContent.style.display = 'flex';
            } else if (tabName === 'formfields') {
                if (formfieldsTab) {
                    formfieldsTab.style.background = '#667eea';
                    formfieldsTab.style.color = 'white';
                    formfieldsTab.style.borderBottom = '3px solid #667eea';
                }
                if (formfieldsContent) {
                    formfieldsContent.style.display = 'flex';
                }
                // 切換到表單欄位分頁時自動載入配對表單
                // 如果尚未載入過，或載入過但沒有表單（可能後來新增了配對），都重新載入
                if (!formFieldsLoaded || currentMappedForms.length === 0) {
                    loadMappedForms('design');
                }
            } else if (tabName === 'opsetvars') {
                if (opsetvarsTab) {
                    opsetvarsTab.style.background = '#667eea';
                    opsetvarsTab.style.color = 'white';
                    opsetvarsTab.style.borderBottom = '3px solid #667eea';
                }
                if (opsetvarsContent) {
                    opsetvarsContent.style.display = 'flex';
                }
                // 首次切換到 OPSET 變數分頁時自動載入
                reloadOpsetVars();
            }
        }

        // 切換底部控制面板的展開/收起狀態
        let isPanelExpanded = false;

        function toggleControlPanel() {
            const controlArea = document.querySelector('.canvas-control-area');

            // 取得所有展開按鈕（包含側邊欄頂部、原本的位置和分頁列）
            const btnTop = document.getElementById('toggle-panel-btn-top');
            const btnTemp = document.getElementById('toggle-panel-btn-temp');
            const btnOriginal = document.getElementById('toggle-panel-btn');
            const btnTab = document.getElementById('toggle-panel-btn-tab');

            if (!controlArea) {
                console.error('找不到控制區域');
                return;
            }

            isPanelExpanded = !isPanelExpanded;

            const cyElement = document.getElementById('cy');
            const statusHistory = document.getElementById('status-history');

            if (isPanelExpanded) {
                // 使用 inline style 直接設定高度（最高優先級）
                controlArea.style.height = '600px';
                controlArea.classList.add('expanded');

                // 更新所有展開按鈕的文字
                if (btnTop) btnTop.innerHTML = '<i class="fas fa-chevron-down"></i> 收起控制面板';
                if (btnTemp) btnTemp.innerHTML = '<i class="fas fa-chevron-down"></i> 收起';
                if (btnOriginal) btnOriginal.innerHTML = '<i class="fas fa-chevron-down"></i> 收起';
                if (btnTab) btnTab.innerHTML = '<i class="fas fa-chevron-down"></i> 收起';

                // 展開時設定各區域的最大高度（擴大但不移除限制）
                if (statusHistory) {
                    statusHistory.style.setProperty('max-height', '525px', 'important');
                    // 捲動到最底部
                    setTimeout(() => {
                        statusHistory.scrollTop = statusHistory.scrollHeight;
                    }, 100);
                }

                // 同步調整表單欄位和 OPSET 變數分頁的捲動區高度
                const formFieldsScroll = document.getElementById('form-fields-scroll');
                const opsetVarsScroll = document.getElementById('opset-vars-scroll');
                const mappedFormsList = document.getElementById('mapped-forms-list');
                if (formFieldsScroll) formFieldsScroll.style.setProperty('max-height', '525px', 'important');
                if (opsetVarsScroll) opsetVarsScroll.style.setProperty('max-height', '525px', 'important');
                if (mappedFormsList) mappedFormsList.style.setProperty('max-height', '525px', 'important');

                // 計算 #cy 新高度 = 當前高度 - (600 - 270)
                if (cyElement) {
                    const currentHeight = cyElement.offsetHeight;
                    const newHeight = currentHeight - 330; // 600 - 270 = 330
                    cyElement.style.height = newHeight + 'px';
                }
            } else {
                // 恢復預設高度
                controlArea.style.height = '270px';
                controlArea.classList.remove('expanded');

                // 更新所有展開按鈕的文字
                if (btnTop) btnTop.innerHTML = '<i class="fas fa-chevron-up"></i> 展開控制面板';
                if (btnTemp) btnTemp.innerHTML = '<i class="fas fa-chevron-up"></i> 展開';
                if (btnOriginal) btnOriginal.innerHTML = '<i class="fas fa-chevron-up"></i> 展開';
                if (btnTab) btnTab.innerHTML = '<i class="fas fa-chevron-up"></i> 展開';

                // 收合時恢復各區域的最大高度限制
                if (statusHistory) {
                    statusHistory.style.setProperty('max-height', '175px', 'important');
                    // 捲動到最底部
                    setTimeout(() => {
                        statusHistory.scrollTop = statusHistory.scrollHeight;
                    }, 100);
                }

                // 同步調整表單欄位和 OPSET 變數分頁的捲動區高度
                const formFieldsScroll = document.getElementById('form-fields-scroll');
                const opsetVarsScroll = document.getElementById('opset-vars-scroll');
                const mappedFormsList = document.getElementById('mapped-forms-list');
                if (formFieldsScroll) formFieldsScroll.style.setProperty('max-height', '175px', 'important');
                if (opsetVarsScroll) opsetVarsScroll.style.setProperty('max-height', '175px', 'important');
                if (mappedFormsList) mappedFormsList.style.setProperty('max-height', '175px', 'important');

                // 恢復 #cy 高度
                if (cyElement) {
                    const currentHeight = cyElement.offsetHeight;
                    const newHeight = currentHeight + 330; // 加回 330
                    cyElement.style.height = newHeight + 'px';
                }
            }

            // 通知 Cytoscape 重新計算大小
            setTimeout(() => {
                if (window.cy) {
                    cy.resize();
                    // 移除 cy.fit()，避免展開/收合時改變畫布比例

                    // 重繪網格背景，避免展開/收合時網格變形
                    drawGridBackground();
                }
            }, 350); // 等待 CSS transition 完成（300ms + 50ms 緩衝）
        }

        // 切換網格樣式（按鈕版本，保留以防其他地方使用）
        function toggleGridStyle(style) {
            if (style === 'off') {
                gridEnabled = false;
            } else {
                gridEnabled = true;
                gridStyle = style;
            }
            drawGridBackground();
            updateStatus(`網格樣式: ${style === 'off' ? '關閉' : style === 'lines' ? '線條' : '點陣'}`);
        }

        // 切換網格勾選框
        function toggleGridCheckbox() {
            const linesCheckbox = document.getElementById('grid-lines');
            const dotsCheckbox = document.getElementById('grid-dots');
            const linesChecked = linesCheckbox.checked;
            const dotsChecked = dotsCheckbox.checked;

            // 線與點互斥：當勾選一個時，自動取消另一個
            if (linesChecked && dotsChecked) {
                // 找出哪個是剛剛被勾選的，取消另一個
                if (event && event.target === linesCheckbox) {
                    dotsCheckbox.checked = false;
                } else {
                    linesCheckbox.checked = false;
                }
            }

            // 更新網格狀態
            if (linesCheckbox.checked) {
                gridEnabled = true;
                gridStyle = 'lines';
                updateStatus('網格樣式: 線條');
            } else if (dotsCheckbox.checked) {
                gridEnabled = true;
                gridStyle = 'dots';
                updateStatus('網格樣式: 點陣');
            } else {
                gridEnabled = false;
                updateStatus('網格樣式: 關閉');
            }

            drawGridBackground();
        }

        // 群組管理功能
        let groupCounter = 0;

        // 右鍵選單相關變數
        let contextMenuTarget = null; // 當前右鍵點擊的目標

        // 顯示右鍵選單
        function showContextMenu(x, y, target) {
            contextMenuTarget = target;
            const menu = document.getElementById('contextMenu');
            menu.innerHTML = ''; // 清空舊選單

            const isNode = target.isNode && target.isNode();
            const isEdge = target.isEdge && target.isEdge();

            // Edge 的右鍵選單暫不顯示（未來可擴展）
            if (isEdge) {
                hideContextMenu();
                return;
            }

            const isGroup = isNode && isGroupNode(target);
            const isInGroup = isNode && target.parent().length > 0;

            if (isGroup) {
                // 建立色盤格子 HTML
                let colorGridItems = '';
                GROUP_COLORS.forEach(c => {
                    colorGridItems += `<div onclick="setGroupColorFromMenu(${c.r}, ${c.g}, ${c.b})" title="${c.label}" style="width: 16px; height: 16px; background: rgb(${c.r}, ${c.g}, ${c.b}); border: 1px solid #aaa; border-radius: 2px; cursor: pointer;"></div>`;
                });

                // 群組節點的右鍵選單
                menu.innerHTML = `
                    <div class="context-menu-item" onclick="editGroupLabel()">
                        <i class="fas fa-edit"></i>
                        <span>編輯群組名稱</span>
                    </div>
                    <div class="context-menu-separator"></div>
                    <div class="context-menu-item context-menu-submenu">
                        <i class="fas fa-palette"></i>
                        <span>群組顏色</span>
                        <div class="submenu-content context-menu" style="padding: 8px; min-width: auto;">
                            <div style="display: grid; grid-template-columns: repeat(10, 16px); gap: 3px;">
                                ${colorGridItems}
                            </div>
                            <div class="context-menu-separator" style="margin: 6px 0;"></div>
                            <div class="context-menu-item" onclick="clearGroupColorFromMenu()" style="font-size: 11px;">
                                <i class="fas fa-undo"></i>
                                <span>重設顏色</span>
                            </div>
                        </div>
                    </div>
                    <div class="context-menu-item context-menu-submenu">
                        <i class="fas fa-border-style"></i>
                        <span>框線樣式</span>
                        <div class="submenu-content context-menu">
                            <div class="context-menu-item" onclick="setGroupBorderStyle('solid')">
                                <i class="fas fa-minus"></i>
                                <span>實線</span>
                            </div>
                            <div class="context-menu-item" onclick="setGroupBorderStyle('dashed')">
                                <i class="fas fa-grip-lines"></i>
                                <span>虛線</span>
                            </div>
                            <div class="context-menu-item" onclick="setGroupBorderStyle('none')">
                                <i class="fas fa-ban"></i>
                                <span>無框線</span>
                            </div>
                        </div>
                    </div>
                    <div class="context-menu-item context-menu-submenu">
                        <i class="fas fa-square"></i>
                        <span>圓角樣式</span>
                        <div class="submenu-content context-menu">
                            <div class="context-menu-item" onclick="setGroupCornerStyle('round')">
                                <i class="fas fa-square"></i>
                                <span>圓角</span>
                            </div>
                            <div class="context-menu-item" onclick="setGroupCornerStyle('square')">
                                <i class="far fa-square"></i>
                                <span>直角</span>
                            </div>
                        </div>
                    </div>
                    <div class="context-menu-separator"></div>
                    <div class="context-menu-item" onclick="dissolveGroupFromMenu()">
                        <i class="fas fa-times-circle"></i>
                        <span>解散群組</span>
                    </div>
                `;
            } else if (isNode && !isGroup) {
                // 一般節點的右鍵選單
                const menuItems = [];
                const nodeType = target.data('type');
                const nodeId = target.data('id');
                // Start 節點不允許刪除和替換
                const isStartNode = (nodeId === 'node-Start' || nodeType === 'Start');

                // Start 節點以外都可以替換
                if (!isStartNode) {
                    menuItems.push(`
                        <div class="context-menu-item" onclick="showReplaceNodePanel()">
                            <i class="fas fa-exchange-alt"></i>
                            <span>替換節點</span>
                        </div>
                    `);
                }

                if (isInGroup) {
                    menuItems.push(`
                        <div class="context-menu-item" onclick="removeNodeFromGroupMenu()">
                            <i class="fas fa-arrow-up"></i>
                            <span>移出群組</span>
                        </div>
                    `);
                }

                // Start 節點不允許刪除
                if (!isStartNode) {
                    menuItems.push(`
                        <div class="context-menu-item" onclick="deleteNodeFromMenu()">
                            <i class="fas fa-trash"></i>
                            <span>刪除節點</span>
                        </div>
                    `);
                }

                // 如果沒有任何選單項目，不顯示右鍵選單
                if (menuItems.length === 0) {
                    hideContextMenu();
                    return;
                }

                menu.innerHTML = menuItems.join('');
            }

            // 定位選單
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
            menu.style.display = 'block';
        }

        // 隱藏右鍵選單
        function hideContextMenu() {
            const menu = document.getElementById('contextMenu');
            menu.style.display = 'none';
            contextMenuTarget = null;
        }

        // 右鍵選單：移出群組
        function removeNodeFromGroupMenu() {
            if (contextMenuTarget) {
                contextMenuTarget.move({ parent: null });
                cy.style().update();
                updateStatus('節點已移出群組');
                updateMinimap();
            }
            hideContextMenu();
        }

        // 右鍵選單：刪除節點
        function deleteNodeFromMenu() {
            if (contextMenuTarget) {
                // 保護 Start 節點不被刪除
                const nodeType = normalizeNodeType(contextMenuTarget.data('type'));
                const nodeId = contextMenuTarget.data('id');
                if (nodeId === 'node-Start' || nodeType === 'Start') {
                    updateStatus('⚠️ Start 節點不允許刪除', 'warning');
                    hideContextMenu();
                    return;
                }
                // 檢查是否為 Subflow 節點
                const isSubflow = nodeType === 'Subflow';
                contextMenuTarget.remove();
                updateStatus('節點已刪除');
                updateMinimap();
                // 如果刪除了 SUBFLOW 節點，延遲 0.5 秒後重新整理流程樹系
                if (isSubflow) {
                    setTimeout(() => {
                        refreshFlowTree();
                    }, 500);
                }
            }
            hideContextMenu();
        }

        // 右鍵選單：編輯群組名稱
        function editGroupLabel() {
            if (contextMenuTarget) {
                const currentLabel = contextMenuTarget.data('label');
                const newLabel = prompt('輸入群組名稱:', currentLabel);
                if (newLabel !== null && newLabel.trim() !== '') {
                    contextMenuTarget.data('label', newLabel.trim());
                    updateGroupSettingsPanel();
                    updateStatus('群組名稱已更新');
                    hasUnsavedChanges = true;
                    updateSaveButtonState();
                }
            }
            hideContextMenu();
        }

        // 右鍵選單：設定群組框線樣式
        function setGroupBorderStyle(style) {
            if (contextMenuTarget) {
                contextMenuTarget.data('borderStyle', style);
                const gc = contextMenuTarget.data('groupColor');

                if (style === 'none') {
                    contextMenuTarget.style({
                        'border-width': 0,
                        'background-opacity': 0.3
                    });
                } else {
                    const borderColor = gc ? groupBorderColor(gc.r, gc.g, gc.b) : '#667eea';
                    contextMenuTarget.style({
                        'border-width': 2,
                        'border-style': style,
                        'background-opacity': 0.15,
                        'border-color': borderColor
                    });
                }

                updateStatus(`群組框線已設為: ${style === 'solid' ? '實線' : style === 'dashed' ? '虛線' : '無框線'}`);
                updateGroupSettingsPanel();
                hasUnsavedChanges = true;
                updateSaveButtonState();
            }
            hideContextMenu();
        }

        // 右鍵選單：設定群組圓角樣式
        function setGroupCornerStyle(style) {
            if (contextMenuTarget) {
                contextMenuTarget.data('cornerStyle', style);
                contextMenuTarget.style({
                    'shape': style === 'round' ? 'roundrectangle' : 'rectangle'
                });

                updateStatus(`群組形狀已設為: ${style === 'round' ? '圓角' : '直角'}`);
                updateGroupSettingsPanel();
                hasUnsavedChanges = true;
                updateSaveButtonState();
            }
            hideContextMenu();
        }

        // 右鍵選單：設定群組顏色
        function setGroupColorFromMenu(r, g, b) {
            if (contextMenuTarget && isGroupNode(contextMenuTarget)) {
                pushUndoState();
                applyGroupColor(contextMenuTarget, { r, g, b });
                updateStatus(`群組顏色已更新`);
                hasUnsavedChanges = true;
                updateSaveButtonState();
            }
            hideContextMenu();
        }

        // 右鍵選單：清除群組顏色
        function clearGroupColorFromMenu() {
            if (contextMenuTarget && isGroupNode(contextMenuTarget)) {
                pushUndoState();
                contextMenuTarget.removeData('groupColor');
                contextMenuTarget.style('background-color', 'rgba(102, 126, 234, 0.08)');
                const borderWidth = contextMenuTarget.numericStyle('border-width');
                if (borderWidth > 0) {
                    contextMenuTarget.style('border-color', '#667eea');
                }
                updateGroupSettingsPanel();
                updateMinimap();
                updateStatus('群組顏色已重設');
                hasUnsavedChanges = true;
                updateSaveButtonState();
            }
            hideContextMenu();
        }

        // 右鍵選單：解散群組
        function dissolveGroupFromMenu() {
            if (contextMenuTarget) {
                const children = contextMenuTarget.children();
                children.forEach(child => {
                    child.move({ parent: null });
                });
                contextMenuTarget.remove();
                cy.style().update();
                updateStatus('群組已解散');
                updateMinimap();
            }
            hideContextMenu();
        }

        // ==================== 替換節點功能 ====================
        let replaceNodeTarget = null;  // 要被替換的節點
        let replaceNodeDefinitions = null;  // 快取節點定義
        let replaceNodeUndoBuffer = null;  // 最後一次替換的舊節點資料（記憶體保留，不在畫布上）

        // 顯示替換節點面板
        async function showReplaceNodePanel() {
            if (!contextMenuTarget) {
                updateStatus('⚠️ 請先選取要替換的節點', 'warning');
                return;
            }

            replaceNodeTarget = contextMenuTarget;
            hideContextMenu();

            // 載入節點定義（若尚未載入）
            if (!replaceNodeDefinitions) {
                try {
                    const response = await fetch('/api/workflows/data/node-definitions');
                    const result = await response.json();
                    if (!result.success) {
                        throw new Error(result.message || '載入節點定義失敗');
                    }
                    replaceNodeDefinitions = result.data;
                } catch (error) {
                    updateStatus(`❌ 載入節點定義失敗: ${error.message}`, 'warning');
                    return;
                }
            }

            // 建立並顯示面板
            showReplaceNodeModal();
        }

        // 顯示替換節點的模態框
        function showReplaceNodeModal() {
            // 移除可能存在的舊面板
            const existingModal = document.getElementById('replaceNodeModal');
            if (existingModal) {
                existingModal.remove();
            }

            const currentNodeType = replaceNodeTarget.data('type');
            const currentNodeLabel = replaceNodeTarget.data('label');

            // 分類名稱對應
            const CATEGORY_NAMES = {
                'basic': '基本節點',
                'form': '表單處理',
                'notification': '通知機制',
                'flow_control': '流程控制',
                'data': '資料處理',
                'operation': '運算操作',
                'integration': '系統整合',
                'system_admin': '系統專用'
            };

            // 建立模態框
            const modal = document.createElement('div');
            modal.id = 'replaceNodeModal';
            modal.className = 'replace-node-modal';
            modal.innerHTML = `
                <div class="replace-node-modal-content">
                    <div class="replace-node-modal-header">
                        <h3><i class="fas fa-exchange-alt"></i> 替換節點</h3>
                        <button class="replace-node-close-btn" onclick="closeReplaceNodeModal()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="replace-node-modal-info">
                        <span>目前節點：</span>
                        <strong>${currentNodeLabel || currentNodeType}</strong>
                        <span class="replace-node-type-badge">${currentNodeType}</span>
                    </div>
                    <div class="replace-node-modal-body" id="replaceNodeList">
                        <!-- 節點列表將由 JS 填充 -->
                    </div>
                    <div class="replace-node-modal-footer">
                        <button class="btn-secondary" onclick="closeReplaceNodeModal()">取消</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // 填充節點列表
            const listContainer = document.getElementById('replaceNodeList');

            // 先檢查是否有 undo buffer 可供還原
            if (replaceNodeUndoBuffer) {
                const buf = replaceNodeUndoBuffer;
                const restoreDiv = document.createElement('div');
                restoreDiv.className = 'replace-node-category';
                restoreDiv.innerHTML = `
                    <div class="replace-node-category-header replace-node-restore-header">
                        <i class="fas fa-undo"></i> 還原上次替換
                    </div>
                    <div class="replace-node-category-items">
                        <div class="replace-node-item replace-node-restore-item" onclick="executeRestoreNode()">
                            <img src="${buf.icon || ''}" class="replace-node-icon" alt="">
                            <div class="replace-node-item-info">
                                <div class="replace-node-item-label">${buf.label || buf.type}</div>
                                <div class="replace-node-item-desc">${buf.type} → 還原到 ${buf.newNodeId}</div>
                            </div>
                        </div>
                    </div>
                `;
                listContainer.appendChild(restoreDiv);
            }

            // 正常的節點類型列表
            const categoryOrder = ['basic', 'form', 'notification', 'flow_control', 'data', 'operation', 'integration', 'system_admin'];

            categoryOrder.forEach(categoryKey => {
                const nodes = replaceNodeDefinitions[categoryKey];
                if (!nodes || nodes.length === 0) return;

                // 過濾掉 Start 和當前節點類型
                const availableNodes = nodes.filter(n =>
                    n.type !== 'Start' && n.type !== currentNodeType
                );
                if (availableNodes.length === 0) return;

                const categoryDiv = document.createElement('div');
                categoryDiv.className = 'replace-node-category';
                categoryDiv.innerHTML = `
                    <div class="replace-node-category-header">
                        ${CATEGORY_NAMES[categoryKey] || categoryKey}
                    </div>
                    <div class="replace-node-category-items">
                        ${availableNodes.map(node => `
                            <div class="replace-node-item" onclick="executeReplaceNode('${node.type}', '${node.label}', '${node.icon || ''}')">
                                <img src="${node.icon}" class="replace-node-icon" alt="">
                                <div class="replace-node-item-info">
                                    <div class="replace-node-item-label">${node.label}</div>
                                    <div class="replace-node-item-desc">${node.description || ''}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
                listContainer.appendChild(categoryDiv);
            });
        }

        // 還原上次替換（從記憶體 buffer 還原）
        function executeRestoreNode() {
            if (!replaceNodeUndoBuffer) {
                updateStatus('⚠️ 沒有可還原的替換記錄', 'warning');
                closeReplaceNodeModal();
                return;
            }

            pushUndoState();
            const buf = replaceNodeUndoBuffer;

            // 找到當前佔位的新節點
            const currentNode = cy.getElementById(buf.newNodeId);
            if (!currentNode || currentNode.length === 0) {
                updateStatus('⚠️ 找不到替換後的節點，可能已被刪除', 'warning');
                replaceNodeUndoBuffer = null;
                closeReplaceNodeModal();
                return;
            }

            // 關閉選單
            closeReplaceNodeModal();

            const currentId = currentNode.id();
            const currentLabel = currentNode.data('label') || currentId;

            // 1. 收集當前節點的所有連線資料
            const connectedEdges = currentNode.connectedEdges();
            const edgeInfoList = [];
            connectedEdges.forEach(edge => {
                edgeInfoList.push({
                    sourceId: edge.data('source'),
                    targetId: edge.data('target'),
                    label: edge.data('label') || ''
                });
            });

            // 2. 移除當前節點
            const parentId = (currentNode.parent() && currentNode.parent().length > 0) ? currentNode.parent().id() : null;
            cy.remove(currentNode);

            // 3. 從 buffer 還原舊節點到原位置
            const restoredNodeId = `node-${buf.type}-${Date.now()}`;
            const restoredNode = cy.add({
                group: 'nodes',
                data: {
                    ...buf.data,
                    id: restoredNodeId
                },
                position: buf.position
            });

            // 套用圖示
            let iconUrl = buf.data.iconUrl || '';
            if (!iconUrl && buf.icon) {
                if (buf.icon.startsWith('/static/') || buf.icon.startsWith('http')) {
                    iconUrl = buf.icon;
                } else {
                    iconUrl = getSvgDataUrl(buf.icon, '#333333');
                }
            }
            if (iconUrl) {
                restoredNode.style({
                    'background-image': iconUrl,
                    'background-fit': 'contain',
                    'background-clip': 'none'
                });
            }
            if (!globalNodeBorder) {
                restoredNode.addClass('no-border');
            }
            if (parentId || buf.parentId) {
                restoredNode.move({ parent: parentId || buf.parentId });
            }

            // 4. 重建連線
            edgeInfoList.forEach(info => {
                cy.add({
                    group: 'edges',
                    data: {
                        source: info.sourceId === currentId ? restoredNodeId : info.sourceId,
                        target: info.targetId === currentId ? restoredNodeId : info.targetId,
                        label: info.label
                    }
                });
            });

            // 5. 清除 buffer
            replaceNodeUndoBuffer = null;

            // 6. 更新畫布
            cy.style().update();
            updateMinimap();
            updateGridOccupancy();

            // 7. 選取還原的節點
            cy.nodes().unselect();
            restoredNode.select();

            // 8. 標記為未儲存
            hasUnsavedChanges = true;
            updateSaveButtonState();

            updateStatus(`✅ 節點已還原：${currentLabel} → ${buf.label}`);
        }

        // 關閉替換節點面板
        function closeReplaceNodeModal() {
            const modal = document.getElementById('replaceNodeModal');
            if (modal) {
                modal.remove();
            }
            replaceNodeTarget = null;
        }

        // 執行替換節點
        function executeReplaceNode(newType, newLabel, newIcon) {
            if (!replaceNodeTarget) {
                updateStatus('⚠️ 替換目標遺失', 'warning');
                closeReplaceNodeModal();
                return;
            }

            pushUndoState();

            // 先保存目標節點的參照，再關閉選單
            const oldNode = replaceNodeTarget;
            closeReplaceNodeModal();

            const oldId = oldNode.id();
            const oldLabel = oldNode.data('label') || oldId;
            const oldPosition = { ...oldNode.position() };
            const oldParent = oldNode.parent();
            const parentId = (oldParent && oldParent.length > 0) ? oldParent.id() : null;

            // 1. 收集舊節點的所有連線資料
            const connectedEdges = oldNode.connectedEdges();
            const edgeInfoList = [];
            connectedEdges.forEach(edge => {
                edgeInfoList.push({
                    sourceId: edge.data('source'),
                    targetId: edge.data('target'),
                    label: edge.data('label') || ''
                });
            });

            // 2. 將舊節點完整資料存入 undo buffer（記憶體保留，不在畫布上）
            const newNodeId = `node-${newType}-${Date.now()}`;
            replaceNodeUndoBuffer = {
                data: JSON.parse(JSON.stringify(oldNode.data())),
                position: oldPosition,
                parentId: parentId,
                type: oldNode.data('type'),
                label: oldLabel,
                icon: oldNode.data('icon') || '',
                newNodeId: newNodeId  // 記錄替換後的新節點 ID，供還原時找到目標
            };

            // 3. 移除舊節點，在原位置建立新節點
            cy.remove(oldNode);

            const newNode = cy.add({
                group: 'nodes',
                data: {
                    id: newNodeId,
                    label: newLabel,
                    type: newType,
                    icon: newIcon,
                    config: {}
                },
                position: oldPosition
            });

            // 套用新節點的圖示
            if (newIcon) {
                let iconUrl = newIcon;
                if (!newIcon.startsWith('/static/') && !newIcon.startsWith('http')) {
                    iconUrl = getSvgDataUrl(newIcon, '#333333');
                }
                newNode.style({
                    'background-image': iconUrl,
                    'background-fit': 'contain',
                    'background-clip': 'none'
                });
            }
            if (!globalNodeBorder) {
                newNode.addClass('no-border');
            }

            // 如果原節點在群組內，新節點也加入同一群組
            if (parentId) {
                newNode.move({ parent: parentId });
            }

            // 4. 重建所有連線
            edgeInfoList.forEach(info => {
                cy.add({
                    group: 'edges',
                    data: {
                        source: info.sourceId === oldId ? newNodeId : info.sourceId,
                        target: info.targetId === oldId ? newNodeId : info.targetId,
                        label: info.label
                    }
                });
            });

            // 5. 更新畫布
            cy.style().update();
            updateMinimap();
            updateGridOccupancy();

            // 6. 選取新節點
            cy.nodes().unselect();
            newNode.select();

            // 7. 標記為未儲存
            hasUnsavedChanges = true;
            updateSaveButtonState();

            updateStatus(`✅ 節點已替換：${oldLabel} → ${newLabel}`);
        }
        // ==================== 替換節點功能結束 ====================

        // 建立群組
        function createGroup() {
            pushUndoState();
            const selectedNodes = cy.nodes(':selected').filter(node => {
                // 排除中繼點和已經是群組的節點
                return node.data('type') !== 'relay' && !isGroupNode(node);
            });

            if (selectedNodes.length === 0) {
                updateStatus('請先選取至少一個節點（Ctrl+點擊選取多個）', 'warning');
                return;
            }

            // 建立群組節點
            groupCounter++;
            const groupId = `group_${groupCounter}`;

            const groupNode = cy.add({
                group: 'nodes',
                data: {
                    id: groupId,
                    label: `群組 ${groupCounter}`,
                    type: 'group',
                    borderStyle: 'none',      // 預設無框
                    cornerStyle: 'round'      // 預設圓角
                }
            });

            // 將選中的節點加入群組
            selectedNodes.forEach(node => {
                node.move({ parent: groupId });
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            updateStatus(`已建立群組: ${groupId}，包含 ${selectedNodes.length} 個節點`);
            updateMinimap();
        }

        // 加入節點到現有群組
        function addToGroup() {
            pushUndoState();
            const selected = cy.nodes(':selected');

            // 分離出節點和群組
            const nodes = selected.filter(n => !isGroupNode(n) && n.data('type') !== 'relay');
            const groups = selected.filter(n => isGroupNode(n));

            if (nodes.length === 0) {
                updateStatus('請先選取要加入的節點', 'warning');
                return;
            }

            if (groups.length === 0) {
                updateStatus('請選取一個群組節點', 'warning');
                return;
            }

            if (groups.length > 1) {
                updateStatus('只能選取一個群組', 'warning');
                return;
            }

            const groupId = groups[0].id();

            // 將節點移入群組
            nodes.forEach(node => {
                node.move({ parent: groupId });
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            updateStatus(`已將 ${nodes.length} 個節點加入群組 ${groupId}`);
            updateMinimap();
        }

        // 從群組移出節點
        function removeFromGroup() {
            pushUndoState();
            const selectedNodes = cy.nodes(':selected').filter(node => {
                return node.data('type') !== 'relay' && !isGroupNode(node) && node.parent().length > 0;
            });

            if (selectedNodes.length === 0) {
                updateStatus('請選取群組內的節點', 'warning');
                return;
            }

            selectedNodes.forEach(node => {
                node.move({ parent: null });
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            updateStatus(`已從群組移出 ${selectedNodes.length} 個節點`);
            updateMinimap();
        }

        // 解散群組
        function dissolveGroup() {
            pushUndoState();
            const selectedGroups = cy.nodes(':selected').filter(node => isGroupNode(node));

            if (selectedGroups.length === 0) {
                updateStatus('請選取要解散的群組節點', 'warning');
                return;
            }

            selectedGroups.forEach(group => {
                // 將所有子節點移出群組
                const children = group.children();
                children.forEach(child => {
                    child.move({ parent: null });
                });

                // 刪除群組節點
                group.remove();
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            updateStatus(`已解散 ${selectedGroups.length} 個群組`);
            updateMinimap();
        }

        // 更新狀態
        let statusBlinkTimeout = null;
        function updateStatus(message, type = 'normal') {
            // 更新歷史記錄面板
            const historyPanel = document.getElementById('status-history');
            if (historyPanel) {
                const now = new Date();
                const timeStr = now.toLocaleTimeString('zh-TW', { hour12: false });

                // 根據類型設定顏色
                let color = '#333';
                if (type === 'error') color = '#dc3545';
                else if (type === 'warning' || type === 'alert') color = '#ff6b00';
                else if (type === 'success') color = '#28a745';

                // 建立訊息元素
                const msgDiv = document.createElement('div');
                msgDiv.style.color = color;
                msgDiv.style.marginBottom = '4px';
                msgDiv.innerHTML = `<span style="color: #666;">[${timeStr}]</span> ${message}`;

                // 附加到面板
                historyPanel.appendChild(msgDiv);

                // 自動捲動到底部
                historyPanel.scrollTop = historyPanel.scrollHeight;
            }

            // 保留舊的狀態列更新（向後相容）
            const statusElement = document.getElementById('status');
            const statusBar = document.querySelector('.status-bar');

            if (statusElement) statusElement.textContent = message;

            // 清除之前的定時器
            if (statusBlinkTimeout) {
                clearTimeout(statusBlinkTimeout);
                statusBlinkTimeout = null;
            }

            // 移除所有樣式類別
            if (statusBar) statusBar.classList.remove('warning');

            if (type === 'warning' || type === 'alert') {
                // 添加警告閃爍樣式
                if (statusBar) statusBar.classList.add('warning');

                // 顯示並閃爍警告燈號
                const alertIndicator = document.getElementById('alert-indicator');
                if (alertIndicator) {
                    alertIndicator.style.display = 'inline-block';
                    let flashCount = 0;
                    const flashInterval = setInterval(() => {
                        if (flashCount % 2 === 0) {
                            // 紅字黃底
                            alertIndicator.style.color = '#dc3545';
                            alertIndicator.style.background = '#ffc107';
                        } else {
                            // 黃字紅底
                            alertIndicator.style.color = '#ffc107';
                            alertIndicator.style.background = '#dc3545';
                        }
                        flashCount++;
                    }, 500); // 每0.5秒切換一次

                    // 3秒後停止閃爍
                    setTimeout(() => {
                        clearInterval(flashInterval);
                        alertIndicator.style.display = 'none';
                    }, 3000);
                }

                // 3秒後停止閃爍，恢復正常
                statusBlinkTimeout = setTimeout(() => {
                    if (statusBar) statusBar.classList.remove('warning');
                }, 3000);
            }
        }

        // 清空狀態歷史記錄
        function clearStatusHistory() {
            const historyPanel = document.getElementById('status-history');
            if (historyPanel) {
                historyPanel.innerHTML = '';
            }
        }

        // 更新群組設定面板
        function updateGroupSettingsPanel() {
            const panel = document.getElementById('group-settings-content');
            if (!panel || !cy) return;

            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));

            if (selectedGroups.length === 0) {
                panel.innerHTML = '<div style="color: #999; font-style: italic; padding: 8px 0;">選取群組後可在此調整設定</div>';
                return;
            }

            if (selectedGroups.length > 1) {
                panel.innerHTML = `<div style="color: #666; padding: 8px 0;">已選擇 ${selectedGroups.length} 個群組</div>`;
                return;
            }

            const group = selectedGroups[0];
            const currentLabel = group.data('label') || '';
            const currentBorderStyle = group.data('borderStyle') || 'none';
            const currentCornerStyle = group.data('cornerStyle') || 'round';
            const currentColor = group.data('groupColor');

            // 建立色盤 HTML (6行5列)
            let colorGridHtml = '';
            GROUP_COLORS.forEach((c, i) => {
                const isActive = currentColor && currentColor.r === c.r && currentColor.g === c.g && currentColor.b === c.b;
                const borderMark = isActive ? '2px solid #333' : '1px solid #ccc';
                colorGridHtml += `<div onclick="setGroupColor(${c.r}, ${c.g}, ${c.b})" title="${c.label}" style="width: 18px; height: 18px; background: rgb(${c.r}, ${c.g}, ${c.b}); border: ${borderMark}; border-radius: 2px; cursor: pointer; display: inline-block;"></div>`;
            });

            const html = `
                <div style="display: flex; flex-direction: column; gap: 6px;">
                    <!-- 群組名稱 -->
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="white-space: nowrap; color: #666;">名稱:</span>
                        <input type="text" id="group-name-input" value="${currentLabel.replace(/"/g, '&quot;')}"
                            onblur="updateGroupNameFromPanel()"
                            onkeypress="if(event.key==='Enter') this.blur()"
                            style="flex: 1; padding: 3px 6px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px;">
                    </div>

                    <!-- 顏色 -->
                    <div>
                        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 4px;">
                            <span style="color: #666;">顏色:</span>
                            <span onclick="clearGroupColor()" title="清除顏色" style="cursor: pointer; font-size: 10px; color: #999; text-decoration: underline;">重設</span>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(10, 18px); gap: 2px;">
                            ${colorGridHtml}
                        </div>
                    </div>

                    <!-- 框線 + 圓角 -->
                    <div style="display: flex; gap: 12px;">
                        <div>
                            <span style="color: #666;">框線:</span>
                            <span onclick="setGroupBorderStyleFromPanel('none')" style="cursor: pointer; padding: 2px 5px; border-radius: 3px; font-size: 10px; ${currentBorderStyle === 'none' ? 'background: #667eea; color: white;' : 'background: #eee;'}">無</span>
                            <span onclick="setGroupBorderStyleFromPanel('solid')" style="cursor: pointer; padding: 2px 5px; border-radius: 3px; font-size: 10px; ${currentBorderStyle === 'solid' ? 'background: #667eea; color: white;' : 'background: #eee;'}">實線</span>
                            <span onclick="setGroupBorderStyleFromPanel('dashed')" style="cursor: pointer; padding: 2px 5px; border-radius: 3px; font-size: 10px; ${currentBorderStyle === 'dashed' ? 'background: #667eea; color: white;' : 'background: #eee;'}">虛線</span>
                        </div>
                        <div>
                            <span style="color: #666;">圓角:</span>
                            <span onclick="setGroupCornerStyleFromPanel('round')" style="cursor: pointer; padding: 2px 5px; border-radius: 3px; font-size: 10px; ${currentCornerStyle === 'round' ? 'background: #667eea; color: white;' : 'background: #eee;'}">圓角</span>
                            <span onclick="setGroupCornerStyleFromPanel('square')" style="cursor: pointer; padding: 2px 5px; border-radius: 3px; font-size: 10px; ${currentCornerStyle === 'square' ? 'background: #667eea; color: white;' : 'background: #eee;'}">直角</span>
                        </div>
                    </div>
                </div>
            `;

            panel.innerHTML = html;
        }

        // 舊名稱相容
        function updateGroupInfoDisplay() {
            updateGroupSettingsPanel();
        }

        // 從面板設定群組顏色
        function setGroupColor(r, g, b) {
            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));
            if (selectedGroups.length === 0) return;
            pushUndoState();
            selectedGroups.forEach(group => {
                applyGroupColor(group, { r, g, b });
            });
            hasUnsavedChanges = true;
            updateSaveButtonState();
        }

        // 清除群組顏色（恢復預設）
        function clearGroupColor() {
            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));
            if (selectedGroups.length === 0) return;
            pushUndoState();
            selectedGroups.forEach(group => {
                group.removeData('groupColor');
                group.style('background-color', 'rgba(102, 126, 234, 0.08)');
                const borderWidth = group.numericStyle('border-width');
                if (borderWidth > 0) {
                    group.style('border-color', '#667eea');
                }
            });
            updateGroupSettingsPanel();
            updateMinimap();
            hasUnsavedChanges = true;
            updateSaveButtonState();
        }

        // 從面板更新群組名稱
        function updateGroupNameFromPanel() {
            const input = document.getElementById('group-name-input');
            if (!input) return;
            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));
            if (selectedGroups.length !== 1) return;
            const group = selectedGroups[0];
            const newLabel = input.value.trim();
            if (newLabel !== group.data('label')) {
                pushUndoState();
                group.data('label', newLabel);
                hasUnsavedChanges = true;
                updateSaveButtonState();
                updateMinimap();
            }
        }

        // 從面板設定群組框線樣式
        function setGroupBorderStyleFromPanel(style) {
            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));
            if (selectedGroups.length === 0) return;
            pushUndoState();
            selectedGroups.forEach(group => {
                group.data('borderStyle', style);
                const gc = group.data('groupColor');
                if (style === 'none') {
                    group.style({
                        'border-width': 0,
                        'background-opacity': 0.3
                    });
                } else {
                    const borderColor = gc ? groupBorderColor(gc.r, gc.g, gc.b) : '#667eea';
                    group.style({
                        'border-width': 2,
                        'border-style': style,
                        'background-opacity': 0.15,
                        'border-color': borderColor
                    });
                }
            });
            updateGroupSettingsPanel();
            updateMinimap();
            hasUnsavedChanges = true;
            updateSaveButtonState();
        }

        // 從面板設定群組圓角樣式
        function setGroupCornerStyleFromPanel(style) {
            const selectedGroups = cy.$(':selected').filter(node => isGroupNode(node));
            if (selectedGroups.length === 0) return;
            pushUndoState();
            selectedGroups.forEach(group => {
                group.data('cornerStyle', style);
                group.style('shape', style === 'round' ? 'roundrectangle' : 'rectangle');
            });
            updateGroupSettingsPanel();
            updateMinimap();
            hasUnsavedChanges = true;
            updateSaveButtonState();
        }

        // 鷹眼（縮略圖）功能
        let minimapCanvas, minimapCtx, minimapViewport;
        let isDraggingViewport = false;
        let viewportDragOffset = { x: 0, y: 0 };

        function initMinimap() {
            minimapCanvas = document.getElementById('minimap-canvas');
            minimapViewport = document.getElementById('minimap-viewport');

            if (!minimapCanvas) return;

            minimapCtx = minimapCanvas.getContext('2d');

            // 設置畫布實際解析度
            const rect = minimapCanvas.getBoundingClientRect();
            minimapCanvas.width = rect.width * 2; // 使用2倍解析度以獲得更清晰的效果
            minimapCanvas.height = rect.height * 2;

            // 視口框拖拉事件
            minimapViewport.addEventListener('mousedown', function(e) {
                e.preventDefault();
                e.stopPropagation();
                isDraggingViewport = true;

                const viewportRect = minimapViewport.getBoundingClientRect();
                viewportDragOffset.x = e.clientX - viewportRect.left;
                viewportDragOffset.y = e.clientY - viewportRect.top;
            });

            document.addEventListener('mousemove', function(e) {
                if (!isDraggingViewport) return;

                const canvasRect = minimapCanvas.getBoundingClientRect();
                const viewportRect = minimapViewport.getBoundingClientRect();

                // 計算焦點框的中心點位置
                let centerX = e.clientX - canvasRect.left;
                let centerY = e.clientY - canvasRect.top;

                // 限制在 canvas 範圍內（考慮焦點框的寬高）
                const viewportWidth = parseFloat(minimapViewport.style.width) || 0;
                const viewportHeight = parseFloat(minimapViewport.style.height) || 0;

                // 限制 X 座標
                centerX = Math.max(viewportWidth / 2, Math.min(canvasRect.width - viewportWidth / 2, centerX));
                // 限制 Y 座標
                centerY = Math.max(viewportHeight / 2, Math.min(canvasRect.height - viewportHeight / 2, centerY));

                // 轉換為比例（0-1）
                const xRatio = centerX / canvasRect.width;
                const yRatio = centerY / canvasRect.height;

                // 計算實際畫布位置
                const extent = cy.elements().boundingBox();
                const targetX = extent.x1 + (extent.x2 - extent.x1) * xRatio;
                const targetY = extent.y1 + (extent.y2 - extent.y1) * yRatio;

                // 立即平移到目標位置
                cy.pan({
                    x: -targetX * cy.zoom() + cy.container().offsetWidth / 2,
                    y: -targetY * cy.zoom() + cy.container().offsetHeight / 2
                });
            });

            document.addEventListener('mouseup', function() {
                isDraggingViewport = false;
            });

            // 添加點擊事件以導航到點擊位置（只在非拖拉視口時觸發）
            minimapCanvas.addEventListener('click', function(e) {
                // 檢查是否點擊在視口框內
                const viewportRect = minimapViewport.getBoundingClientRect();
                const clickX = e.clientX;
                const clickY = e.clientY;

                if (clickX >= viewportRect.left && clickX <= viewportRect.right &&
                    clickY >= viewportRect.top && clickY <= viewportRect.bottom) {
                    return; // 點擊在視口框內，不處理
                }

                const rect = minimapCanvas.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;

                // 計算實際畫布位置
                const extent = cy.elements().boundingBox();
                const targetX = extent.x1 + (extent.x2 - extent.x1) * x;
                const targetY = extent.y1 + (extent.y2 - extent.y1) * y;

                // 平移到目標位置
                cy.animate({
                    center: { x: targetX, y: targetY },
                    duration: 300
                });
            });

            // 初始化縮略圖
            updateMinimap();
        }

        function updateMinimap() {
            if (!minimapCanvas || !minimapCtx || !cy) return;

            const width = minimapCanvas.width;
            const height = minimapCanvas.height;

            // 清空畫布
            minimapCtx.clearRect(0, 0, width, height);
            minimapCtx.fillStyle = '#ffffff';
            minimapCtx.fillRect(0, 0, width, height);

            // 如果沒有元素，不繪製
            if (cy.elements().length === 0) {
                minimapViewport.style.display = 'none';
                return;
            }

            // 獲取所有元素的邊界框
            const extent = cy.elements().boundingBox();
            const extentWidth = extent.x2 - extent.x1;
            const extentHeight = extent.y2 - extent.y1;

            if (extentWidth === 0 || extentHeight === 0) {
                minimapViewport.style.display = 'none';
                return;
            }

            // 計算縮放比例（保留邊距）
            const padding = 20;
            const scaleX = (width - padding * 2) / extentWidth;
            const scaleY = (height - padding * 2) / extentHeight;
            const scale = Math.min(scaleX, scaleY);

            // 計算偏移量以居中
            const offsetX = (width - extentWidth * scale) / 2 - extent.x1 * scale;
            const offsetY = (height - extentHeight * scale) / 2 - extent.y1 * scale;

            // 繪製所有邊
            cy.edges().forEach(edge => {
                const sourcePos = edge.source().position();
                const targetPos = edge.target().position();

                minimapCtx.strokeStyle = '#95a5a6';
                minimapCtx.lineWidth = 1;
                minimapCtx.beginPath();
                minimapCtx.moveTo(
                    sourcePos.x * scale + offsetX,
                    sourcePos.y * scale + offsetY
                );
                minimapCtx.lineTo(
                    targetPos.x * scale + offsetX,
                    targetPos.y * scale + offsetY
                );
                minimapCtx.stroke();
            });

            // 繪製所有節點
            cy.nodes().forEach(node => {
                const pos = node.position();
                const nodeWidth = node.width() * scale;
                const nodeHeight = node.height() * scale;

                // 檢查是否為群組（parent node）
                const isGroup = isGroupNode(node);

                // 根據節點類型設置顏色
                let color = '#667eea';
                if (node.data('type') === 'relay') {
                    color = '#2196F3';
                } else if (node.data('category')) {
                    // 根據分類設置不同顏色
                    const category = node.data('category');
                    if (category === 'basic') color = '#667eea';
                    else if (category === 'logic') color = '#f093fb';
                    else if (category === 'integration') color = '#4facfe';
                    else if (category === 'data') color = '#43e97b';
                    else if (category === 'notification') color = '#fa709a';
                }

                if (isGroup) {
                    // 群組：使用群組自訂顏色或預設色
                    const gc = node.data('groupColor');
                    if (gc) {
                        color = `rgb(${gc.r}, ${gc.g}, ${gc.b})`;
                    }
                    // 繪製半透明填滿 + 邊框
                    minimapCtx.fillStyle = color;
                    minimapCtx.globalAlpha = 0.2;
                    minimapCtx.fillRect(
                        pos.x * scale + offsetX - nodeWidth / 2,
                        pos.y * scale + offsetY - nodeHeight / 2,
                        Math.max(nodeWidth, 3),
                        Math.max(nodeHeight, 3)
                    );
                    minimapCtx.globalAlpha = 1.0;
                    minimapCtx.strokeStyle = color;
                    minimapCtx.lineWidth = 2;
                    minimapCtx.strokeRect(
                        pos.x * scale + offsetX - nodeWidth / 2,
                        pos.y * scale + offsetY - nodeHeight / 2,
                        Math.max(nodeWidth, 3),
                        Math.max(nodeHeight, 3)
                    );
                } else {
                    // 一般節點：填滿
                    minimapCtx.fillStyle = color;
                    minimapCtx.fillRect(
                        pos.x * scale + offsetX - nodeWidth / 2,
                        pos.y * scale + offsetY - nodeHeight / 2,
                        Math.max(nodeWidth, 3),
                        Math.max(nodeHeight, 3)
                    );
                }
            });

            // 繪製視口矩形
            const pan = cy.pan();
            const zoom = cy.zoom();
            const container = cy.container();
            const containerWidth = container.offsetWidth;
            const containerHeight = container.offsetHeight;

            // 計算視口在縮略圖中的位置和大小
            const viewportX = (-pan.x / zoom) * scale + offsetX;
            const viewportY = (-pan.y / zoom) * scale + offsetY;
            const viewportWidth = (containerWidth / zoom) * scale;
            const viewportHeight = (containerHeight / zoom) * scale;

            // 更新視口矩形元素（位置相對於 canvas）
            const canvasRect = minimapCanvas.getBoundingClientRect();
            const actualViewportX = viewportX / 2; // 除以2因為canvas解析度是2倍
            const actualViewportY = viewportY / 2;
            const actualViewportWidth = viewportWidth / 2;
            const actualViewportHeight = viewportHeight / 2;

            // 限制在 canvas 範圍內
            const clampedX = Math.max(0, Math.min(canvasRect.width - actualViewportWidth, actualViewportX));
            const clampedY = Math.max(0, Math.min(canvasRect.height - actualViewportHeight, actualViewportY));

            minimapViewport.style.display = 'block';
            minimapViewport.style.left = clampedX + 'px';
            minimapViewport.style.top = clampedY + 'px';
            minimapViewport.style.width = actualViewportWidth + 'px';
            minimapViewport.style.height = actualViewportHeight + 'px';
        }

        // ==================== 權限檢查與 UI 控制 ====================
        function checkPermissionsAndUpdateUI() {
            // 檢查所有帶有 data-permission 屬性的元素
            document.querySelectorAll('[data-permission]').forEach(element => {
                const requiredPermissions = element.getAttribute('data-permission').split(',');
                const hasAccess = requiredPermissions.some(perm => AuthModule.hasPermission(perm.trim()));

                if (!hasAccess) {
                    element.style.display = 'none';
                    element.setAttribute('disabled', 'disabled');
                }
            });

            console.log('✅ 權限檢查完成');
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', async function() {
            console.log('🚀 初始化 Workflow Designer');

            // 防止瀏覽器縮放和導航手勢
            document.addEventListener('wheel', function(e) {
                /* 調試用：記錄所有滾輪事件
                const wheelLog = {
                    timestamp: new Date().toISOString(),
                    deltaX: e.deltaX,
                    deltaY: e.deltaY,
                    deltaZ: e.deltaZ || 0,
                    deltaMode: e.deltaMode,
                    ctrlKey: e.ctrlKey,
                    metaKey: e.metaKey,
                    shiftKey: e.shiftKey,
                    altKey: e.altKey,
                    target: e.target.className || e.target.tagName,
                    clientX: e.clientX,
                    clientY: e.clientY
                };

                try {
                    const logs = JSON.parse(localStorage.getItem('workflow_wheel_logs') || '[]');
                    logs.push(wheelLog);
                    if (logs.length > 50) logs.shift();
                    localStorage.setItem('workflow_wheel_logs', JSON.stringify(logs));
                } catch (err) {
                    console.error('無法儲存滾輪日誌:', err);
                }
                */

                // 1. 防止 Ctrl/Cmd + 滾輪縮放
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    console.log('🛑 已阻止 Ctrl+滾輪縮放');
                    return;
                }

                // 2. 防止水平滾動觸發後退/前進手勢
                // 注意：只在明確是水平滾動時才阻止
                if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 10) {
                    // 明顯的水平滾動手勢，可能觸發導航
                    e.preventDefault();
                    console.warn('🛑 已阻止水平滾動手勢（可能觸發後退）', wheelLog);
                    return;
                }
            }, { passive: false });

            // 防止鍵盤縮放快捷鍵 (Ctrl +, Ctrl -, Ctrl 0)
            document.addEventListener('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
                    e.preventDefault();
                }
            });

            // 防止觸控板雙指縮放手勢
            document.addEventListener('gesturestart', function(e) {
                e.preventDefault();
            });

            document.addEventListener('gesturechange', function(e) {
                e.preventDefault();
            });

            document.addEventListener('gestureend', function(e) {
                e.preventDefault();
            });

            // 防止瀏覽器後退按鈕造成的意外離開（加入歷史記錄鎖定）
            // 使用更激進的方式阻止後退
            let preventBackCount = 0;

            // 持續推入歷史記錄
            window.history.pushState(null, '', window.location.href);

            window.addEventListener('popstate', function(e) {
                preventBackCount++;

                // 記錄詳細的後退資訊到 localStorage（用於調試）
                const backLog = {
                    timestamp: new Date().toISOString(),
                    preventCount: preventBackCount,
                    hasUnsavedChanges: hasUnsavedChanges,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    screenSize: `${window.innerWidth}x${window.innerHeight}`,
                    scrollPosition: { x: window.scrollX, y: window.scrollY },
                    stackTrace: new Error().stack
                };

                try {
                    localStorage.setItem('workflow_back_log', JSON.stringify(backLog));
                } catch (e) {
                    console.error('無法儲存後退日誌:', e);
                }

                // 用戶按了後退按鈕
                console.warn(`⚠️ 偵測到後退操作 (第 ${preventBackCount} 次)`, backLog);

                // 立即推入新的歷史記錄，阻止後退
                window.history.pushState(null, '', window.location.href);

                // 只在第一次時詢問用戶
                if (preventBackCount === 1) {
                    // 檢查是否有未儲存的變更
                    if (hasUnsavedChanges) {
                        // 有未儲存的變更，顯示警告
                        const confirmLeave = confirm('您有未儲存的變更，確定要離開嗎？');
                        if (confirmLeave) {
                            // 用戶確認離開
                            console.log('✅ 用戶確認離開');
                            window.location.href = '/forms/workflows';
                        } else {
                            console.log('❌ 用戶取消離開');
                            updateStatus('已取消離開，繼續編輯', 'info');
                        }
                    } else {
                        // 沒有未儲存的變更，詢問是否要離開
                        const confirmLeave = confirm('確定要返回流程目錄嗎？');
                        if (confirmLeave) {
                            console.log('✅ 用戶確認返回目錄');
                            window.location.href = '/forms/workflows';
                        } else {
                            console.log('❌ 用戶取消');
                            updateStatus('已取消返回，繼續編輯', 'info');
                        }
                    }
                } else {
                    // 後續的後退嘗試，直接阻止並提示
                    if (preventBackCount === 2) {
                        updateStatus('🛡️ 後退已被阻擋（請使用上方的「放棄」按鈕返回目錄）', 'warning');
                    }
                }
            });

            // 防止頁面關閉時丟失未儲存的變更
            window.addEventListener('beforeunload', function(e) {
                if (hasUnsavedChanges) {
                    e.preventDefault();
                    e.returnValue = ''; // Chrome 需要這行
                    return '您有未儲存的變更，確定要離開嗎？';
                }
            });

            /* 調試用：顯示後退日誌
            try {
                const backLog = localStorage.getItem('workflow_back_log');
                const wheelLogs = localStorage.getItem('workflow_wheel_logs');

                if (backLog) {
                    console.warn('📋 上次後退操作記錄:', JSON.parse(backLog));
                    const logData = JSON.parse(backLog);
                    updateStatus(`⚠️ 偵測到後退操作 (${new Date(logData.timestamp).toLocaleString()})`, 'warning');
                }

                if (wheelLogs) {
                    const logs = JSON.parse(wheelLogs);
                    if (logs.length > 0) {
                        console.warn('📋 水平滾動攔截記錄:', logs);
                    }
                }
            } catch (e) {
                console.error('讀取日誌失敗:', e);
            }

            // 調試函數
            window.showBackLogs = function() {
                try {
                    const backLog = localStorage.getItem('workflow_back_log');
                    const wheelLogs = localStorage.getItem('workflow_wheel_logs');

                    console.group('📋 導航日誌');
                    if (backLog) {
                        console.warn('後退操作:', JSON.parse(backLog));
                    } else {
                        console.log('無後退記錄');
                    }

                    if (wheelLogs) {
                        console.warn('水平滾動攔截:', JSON.parse(wheelLogs));
                    } else {
                        console.log('無滾輪記錄');
                    }
                    console.groupEnd();
                } catch (e) {
                    console.error('讀取日誌失敗:', e);
                }
            };

            window.clearBackLogs = function() {
                localStorage.removeItem('workflow_back_log');
                localStorage.removeItem('workflow_wheel_logs');
                console.log('✅ 已清除所有導航日誌');
            };

            window.exportWheelLogs = function() {
                try {
                    const logs = JSON.parse(localStorage.getItem('workflow_wheel_logs') || '[]');
                    if (logs.length === 0) {
                        console.log('無滾輪記錄');
                        return;
                    }

                    console.log(`📊 共 ${logs.length} 筆滾輪記錄`);
                    console.table(logs);

                    const last10 = logs.slice(-10);
                    console.group('🔍 最後 10 筆滾輪事件分析');
                    last10.forEach((log, i) => {
                        const ratio = Math.abs(log.deltaX) / Math.abs(log.deltaY);
                        const direction = Math.abs(log.deltaX) > Math.abs(log.deltaY) ? '水平' : '垂直';
                        console.log(`${i + 1}. ${direction} | deltaX:${log.deltaX.toFixed(2)} deltaY:${log.deltaY.toFixed(2)} | 比例:${ratio.toFixed(2)} | target:${log.target}`);
                    });
                    console.groupEnd();

                    const horizontalScrolls = logs.filter(log => Math.abs(log.deltaX) > Math.abs(log.deltaY));
                    if (horizontalScrolls.length > 0) {
                        console.warn(`⚠️ 發現 ${horizontalScrolls.length} 筆水平滾動事件:`, horizontalScrolls);
                    }
                } catch (e) {
                    console.error('匯出日誌失敗:', e);
                }
            };

            console.log('💡 調試提示: showBackLogs() | exportWheelLogs() | clearBackLogs()');
            */

            initCytoscape();
            initDragAndDrop();
            initMinimap();

            // 初始化頁籤（預設顯示第一個）
            switchTab('canvas');

            // 載入底圖列表（必須在載入流程前完成，否則無法還原底圖設定）
            await loadBackgrounds();

            // 載入分類列表（必須 await，否則後續設定 category 時 option 尚未填入）
            await loadCategories();

            // 從 URL 取得參數
            const urlParams = new URLSearchParams(window.location.search);
            const workflowId = urlParams.get('id');
            const isNewWorkflow = urlParams.get('new') === '1';
            const workflowName = urlParams.get('name') || '';
            const workflowCategory = urlParams.get('category') || '';
            const workflowDescription = urlParams.get('description') || '';

            // 判斷行為
            if (workflowId) {
                // 有 id，直接開啟舊檔案進行編輯
                const wasJustCreated = urlParams.get('created') === '1';
                console.log('📂 開啟現有流程:', workflowId, wasJustCreated ? '(剛建立)' : '');
                hasEverSaved = !wasJustCreated;  // 剛建立的標記為未儲存
                await enterDesignMode(workflowId);
                updateStatus('載入流程中...');
            } else if (isNewWorkflow) {
                // 新增流程，直接進入設計模式
                console.log('✨ 新增流程');
                hasEverSaved = false;  // 新建流程，標記為從未儲存
                createNewWorkflowAndEnter(workflowName, workflowCategory, workflowDescription);
                updateStatus('新增流程中...');
            } else {
                // 沒有參數，自動進入新增模式
                console.log('✨ 無參數，自動建立新流程');
                hasEverSaved = false;  // 新建流程，標記為從未儲存
                createNewWorkflowAndEnter('新流程', '', '');
                updateStatus('新增流程中...');
            }

            // 等待 auth.js 載入後執行權限檢查
            setTimeout(() => {
                if (typeof AuthModule !== 'undefined' && AuthModule.isAuthenticated()) {
                    checkPermissionsAndUpdateUI();
                }
            }, 100);

            console.log('✅ 初始化完成');

            // 初始化流程樹
            initFlowTree();
        });

        // ==================== 流程樹功能（父子流程導航 - 純 HTML 版本）====================

        /**
         * 初始化流程樹（純 HTML，無需 Cytoscape）
         */
        function initFlowTree() {
            console.log('✅ 流程樹初始化完成（HTML 版本）');
        }

        /**
         * 設定根主流程（第一次載入時調用）
         */
        function setRootWorkflow(secureCode, name) {
            if (!rootWorkflowId) {
                rootWorkflowId = secureCode;
                rootWorkflowName = name;
                console.log('🌳 設定根主流程:', name, secureCode);
            }
        }

        /**
         * 刷新流程樹（重新載入資料）
         * @param {boolean} forceReload - 是否強制重新載入（忽略快取）
         */
        async function refreshFlowTree(forceReload = false) {
            const container = document.getElementById('flow-tree-list');
            if (!container) return;

            // 如果沒有根主流程，使用當前流程作為根
            if (!rootWorkflowId && currentWorkflowId) {
                // 第一次載入，先取得當前流程資訊來設定根
                try {
                    const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}`);
                    const result = await response.json();
                    const workflowData = result.data || result;
                    setRootWorkflow(workflowData.secure_code, workflowData.name);
                } catch (error) {
                    console.error('❌ 取得流程資訊失敗:', error);
                }
            }

            if (!rootWorkflowId) {
                container.innerHTML = '<div style="padding: 10px; text-align: center; color: #999; font-size: 9px;">尚未載入流程</div>';
                return;
            }

            try {
                // 永遠從根主流程載入樹結構
                const treeData = await loadFlowTreeData(rootWorkflowId);
                renderFlowTree(treeData);
            } catch (error) {
                console.error('❌ 刷新流程樹失敗:', error);
                container.innerHTML = '<div style="padding: 10px; text-align: center; color: #e74c3c; font-size: 9px;">載入失敗</div>';
            }
        }

        /**
         * 從流程圖中提取子流程引用
         * @param {Object} graph - 流程圖資料
         * @returns {Array} 子流程 code 列表
         */
        function extractSubflowsFromGraph(graph) {
            const subflowCodes = [];
            if (!graph || !graph.nodes) return subflowCodes;

            graph.nodes.forEach(node => {
                const nodeData = node.data || node;
                const nodeType = normalizeNodeType(nodeData.type);
                if (nodeType === 'Subflow' && nodeData.config && nodeData.config.childFlowId) {
                    subflowCodes.push(nodeData.config.childFlowId);
                }
            });

            return subflowCodes;
        }

        /**
         * 從 cy 畫布中提取當前 SUBFLOW 節點引用（即時狀態）
         * @returns {Array} 子流程 code 列表
         */
        function extractSubflowsFromCanvas() {
            const subflowCodes = [];
            if (!cy) return subflowCodes;

            cy.nodes().forEach(node => {
                const nodeType = normalizeNodeType(node.data('type'));
                const config = node.data('config');
                if (nodeType === 'Subflow' && config && config.childFlowId) {
                    subflowCodes.push(config.childFlowId);
                }
            });

            return subflowCodes;
        }

        /**
         * 從後端載入流程樹資料（永遠從根主流程開始，遞迴載入所有層級）
         * @param {string} workflowId - 根主流程 secure_code
         * @returns {Object} 樹狀結構資料
         */
        async function loadFlowTreeData(workflowId) {
            // 快取已載入的節點（防止重複載入，並允許重複引用）
            const nodeCache = new Map();

            // 顯示深度上限（防止無限遞迴，但不限制用戶設計）
            const MAX_DEPTH = 10;

            // 遞迴載入單一流程及其子流程
            // isRoot: 是否為根主流程
            // depth: 當前深度（0=主流程, 1=L1, 2=L2, ...）
            async function loadNode(wfId, isRoot = false, depth = 0) {
                // 如果已經載入過，直接返回快取的節點
                if (nodeCache.has(wfId)) {
                    return nodeCache.get(wfId);
                }

                // 先佔位，防止循環引用時無限遞迴
                nodeCache.set(wfId, null);

                try {
                    // 取得流程資訊
                    const response = await fetch(`/api/workflows/data/templates/${wfId}`);
                    const result = await response.json();
                    const workflowData = result.data || result;

                    const node = {
                        id: workflowData.secure_code,
                        name: workflowData.name,
                        secureCode: workflowData.secure_code,
                        isCurrent: (workflowData.secure_code === currentWorkflowId),
                        children: []
                    };

                    // 從流程圖的 SUBFLOW 節點提取子流程引用
                    // 如果是當前編輯中的流程，使用畫布即時狀態；否則從後端資料取得
                    let subflowCodes;
                    if (wfId === currentWorkflowId) {
                        subflowCodes = extractSubflowsFromCanvas();
                    } else {
                        const graph = workflowData.cytoscape_config || workflowData.graph;
                        subflowCodes = extractSubflowsFromGraph(graph);
                    }

                    // 只處理實際被引用的子流程（不合併「可用子流程」）
                    // subflowCodes 是從 graph/畫布的 SUBFLOW 節點提取的 childFlowId

                    // 從後端取得子流程的詳細資訊（用於取得 secure_code、name 等）
                    const subflowsResponse = await fetch(`/api/workflows/data/subflows/available?parent_id=${wfId}`);
                    const subflowsResult = await subflowsResponse.json();
                    const availableSubflows = (subflowsResult.success && subflowsResult.data) ? subflowsResult.data : [];

                    // 遞迴載入每個「實際被引用」的子流程（但要檢查深度限制）
                    for (const code of subflowCodes) {
                        // 從 API 結果中找到對應的子流程詳細資訊
                        const sfFromApi = availableSubflows.find(sf => sf.code === code);

                        if (sfFromApi && sfFromApi.secure_code) {
                            // 檢查深度限制：如果已達到 MAX_DEPTH，不再遞迴載入子流程
                            if (depth >= MAX_DEPTH) {
                                // 達到最大深度，顯示節點但不載入其子流程
                                node.children.push({
                                    id: sfFromApi.secure_code,
                                    name: sfFromApi.name,
                                    secureCode: sfFromApi.secure_code,
                                    isCurrent: (sfFromApi.secure_code === currentWorkflowId),
                                    children: []  // 不再遞迴載入
                                });
                            } else {
                                // 遞迴載入子流程的子流程
                                const childNode = await loadNode(sfFromApi.secure_code, false, depth + 1);
                                if (childNode) {
                                    node.children.push(childNode);
                                }
                            }
                        } else {
                            // 無法從 API 取得詳細資訊，嘗試直接用 code 載入
                            // 這可能是通用子流程（跨流程引用）
                            try {
                                // 用 code 查詢子流程
                                const sfResponse = await fetch(`/api/workflows/data/templates/by-code/${code}`);
                                if (sfResponse.ok) {
                                    const sfResult = await sfResponse.json();
                                    const sfData = sfResult.data || sfResult;
                                    if (sfData && sfData.secure_code) {
                                        if (depth >= MAX_DEPTH) {
                                            node.children.push({
                                                id: sfData.secure_code,
                                                name: sfData.name,
                                                secureCode: sfData.secure_code,
                                                isCurrent: (sfData.secure_code === currentWorkflowId),
                                                children: []
                                            });
                                        } else {
                                            const childNode = await loadNode(sfData.secure_code, false, depth + 1);
                                            if (childNode) {
                                                node.children.push(childNode);
                                            }
                                        }
                                        continue;
                                    }
                                }
                            } catch (e) {
                                console.warn(`無法載入子流程 ${code}:`, e);
                            }

                            // 真的找不到，顯示 code 作為名稱
                            node.children.push({
                                id: code,
                                name: `[${code}]`,
                                secureCode: null,
                                code: code,
                                isCurrent: false,
                                children: []
                            });
                        }
                    }

                    // 更新快取
                    nodeCache.set(wfId, node);
                    return node;
                } catch (error) {
                    console.error(`載入流程 ${wfId} 失敗:`, error);
                    nodeCache.delete(wfId);  // 移除佔位
                    return null;
                }
            }

            const treeData = await loadNode(workflowId, true);  // 根主流程

            // 更新根主流程名稱
            if (treeData) {
                rootWorkflowName = treeData.name;
            }

            return treeData;
        }

        /**
         * 渲染流程樹（純 HTML）
         * @param {Object} treeData - 樹狀結構資料
         */
        function renderFlowTree(treeData) {
            const container = document.getElementById('flow-tree-list');
            if (!container) return;

            // 每層不同顏色
            const depthColors = ['#2ecc71', '#3498db', '#9b59b6', '#e67e22', '#e74c3c'];

            // 生成 HTML
            let html = '';

            // 先渲染主流程（根節點）
            const rootColor = depthColors[0];
            const rootCurrentClass = treeData.isCurrent ? 'current' : '';
            const rootClickHandler = `onclick="switchToWorkflow('${treeData.secureCode}')"`;
            html += `<div class="flow-tree-item ${rootCurrentClass}" style="padding-left: 6px;" ${rootClickHandler} title="${treeData.name}">
                <span class="dot" style="background: ${rootColor};"></span>
                <span class="name">${treeData.name}</span>
            </div>`;

            // 渲染子流程
            function addItem(node, depth) {
                const color = depthColors[(depth + 1) % depthColors.length];
                const indent = (depth + 1) * 12;
                const currentClass = node.isCurrent ? 'current' : '';
                const secureCode = node.secureCode || '';
                const clickHandler = secureCode ? `onclick="switchToWorkflow('${secureCode}')"` : '';

                html += `<div class="flow-tree-item ${currentClass}" style="padding-left: ${6 + indent}px;" ${clickHandler} title="${node.name}">
                    <span class="dot" style="background: ${color};"></span>
                    <span class="name">${node.name}</span>
                </div>`;

                if (node.children && node.children.length > 0) {
                    node.children.forEach(child => addItem(child, depth + 1));
                }
            }

            if (treeData.children && treeData.children.length > 0) {
                treeData.children.forEach(child => addItem(child, 0));
            }

            container.innerHTML = html;
        }

        /**
         * 切換到指定流程
         * @param {string} secureCode - 目標流程的 secure_code
         */
        async function switchToWorkflow(secureCode) {
            if (!secureCode || secureCode === currentWorkflowId) {
                return;
            }

            // 檢查是否有未儲存的變更
            if (typeof hasUnsavedChanges === 'function' && hasUnsavedChanges()) {
                const confirmed = confirm('目前有未儲存的變更，確定要切換到其他流程嗎？');
                if (!confirmed) {
                    return;
                }
            }

            updateStatus(`正在切換到流程...`);

            // 更新 URL 並載入新流程
            const newUrl = new URL(window.location.href);
            newUrl.searchParams.set('id', secureCode);
            newUrl.searchParams.delete('new');
            window.history.pushState(null, '', newUrl);

            // 重置表單欄位分頁狀態
            resetFormFieldsTab();

            // 載入新流程
            currentWorkflowId = secureCode;
            await loadWorkflow();

            // 刷新流程樹
            refreshFlowTree();

            updateStatus(`✅ 已切換到流程`);
        }

        // ==================== 表單欄位分頁功能 ====================

        /**
         * 載入當前流程配對的表單列表
         * @param {string} versionType - 版本類型 ('design' 或 'published')
         */
        async function loadMappedForms(versionType = 'design') {
            if (!currentWorkflowId) {
                updateStatus('⚠ 請先載入流程');
                return;
            }

            currentVersionType = versionType;

            // 更新版本切換按鈕樣式
            const btnDesign = document.getElementById('btn-form-design');
            const btnPublished = document.getElementById('btn-form-published');
            if (btnDesign && btnPublished) {
                if (versionType === 'design') {
                    btnDesign.style.background = '#667eea';
                    btnDesign.style.color = 'white';
                    btnPublished.style.background = '#e0e0e0';
                    btnPublished.style.color = '#666';
                } else {
                    btnDesign.style.background = '#e0e0e0';
                    btnDesign.style.color = '#666';
                    btnPublished.style.background = '#667eea';
                    btnPublished.style.color = 'white';
                }
            }

            // 顯示載入中
            const listContainer = document.getElementById('mapped-forms-list');
            if (listContainer) {
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #999; font-size: 11px;">
                        <i class="fas fa-spinner fa-spin"></i> 載入中...
                    </div>
                `;
            }

            try {
                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}/mapped-forms?version_type=${versionType}`);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '載入失敗');
                }

                currentMappedForms = result.data.forms || [];
                formFieldsLoaded = true;

                renderMappedFormsList(currentMappedForms);

                // 更新計數
                const countEl = document.getElementById('mapped-forms-count');
                if (countEl) {
                    countEl.textContent = `共 ${currentMappedForms.length} 張表單`;
                }

                // 載入變數映射表
                await loadVariableMapping();

                // 如果只有一張表單，自動選擇並分析
                if (result.data.auto_select && currentMappedForms.length === 1) {
                    selectForm(currentMappedForms[0]);
                }

            } catch (error) {
                console.error('載入配對表單失敗:', error);
                if (listContainer) {
                    listContainer.innerHTML = `
                        <div style="text-align: center; padding: 20px; color: #e74c3c; font-size: 11px;">
                            <i class="fas fa-exclamation-circle"></i> 載入失敗: ${error.message}
                        </div>
                    `;
                }
            }
        }
        window.loadMappedForms = loadMappedForms;

        /**
         * 載入變數映射表
         * 從後端取得新式變數（人類可讀格式）與舊式變數（secure_code 格式）的對照表
         */
        async function loadVariableMapping() {
            if (!currentWorkflowId || currentMappedForms.length === 0) {
                variableMapping = null;
                return;
            }

            try {
                // 取得配對表單的 ID 列表
                const formIds = currentMappedForms.map(f => f.form_id);

                const response = await fetch('/api/workflows/data/variable-mapping', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ form_ids: formIds })
                });

                const result = await response.json();
                if (result.success) {
                    variableMapping = result.data;
                    console.log('📋 變數映射表已載入:', variableMapping);
                } else {
                    console.warn('載入變數映射表失敗:', result.message);
                    variableMapping = null;
                }
            } catch (error) {
                console.error('載入變數映射表失敗:', error);
                variableMapping = null;
            }
        }

        /**
         * 取得欄位的新式變數格式
         * @param {string} secureCode - 表單 secure_code
         * @param {string} fieldKey - 欄位 key
         * @returns {string} 新式變數語法，如 ${表單名稱::欄位標籤}
         */
        function getDisplayVariable(secureCode, fieldKey) {
            if (!variableMapping || !variableMapping.forward) {
                // 沒有映射表時返回舊格式
                return `\${${secureCode}_${fieldKey}}`;
            }

            const internalVar = `${secureCode}_${fieldKey}`;
            const displayVar = variableMapping.forward[internalVar];
            return displayVar ? `\${${displayVar}}` : `\${${internalVar}}`;
        }

        /**
         * 渲染配對表單列表
         * @param {Array} forms - 表單列表
         */
        function renderMappedFormsList(forms) {
            const listContainer = document.getElementById('mapped-forms-list');
            if (!listContainer) return;

            if (forms.length === 0) {
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #999; font-size: 11px;">
                        <i class="fas fa-info-circle"></i> 此流程尚未配對任何表單
                    </div>
                `;
                return;
            }

            let html = '';
            for (const form of forms) {
                // 使用 form_secure_code 或 form_id 進行比對
                const formIdentifier = form.form_secure_code || form.form_id;
                const isSelected = selectedFormId === formIdentifier;
                const selectedStyle = isSelected ? 'background: #e3f2fd; border-left: 3px solid #667eea;' : 'border-left: 3px solid transparent;';
                const versionBadge = form.source === 'published'
                    ? `<span style="background: #27ae60; color: white; padding: 1px 4px; border-radius: 2px; font-size: 9px; margin-left: 5px;">v${form.publish_version}</span>`
                    : `<span style="background: #f39c12; color: white; padding: 1px 4px; border-radius: 2px; font-size: 9px; margin-left: 5px;">設計中</span>`;

                html += `
                    <div onclick="selectForm(${JSON.stringify(form).replace(/"/g, '&quot;')})"
                         style="padding: 8px 10px; cursor: pointer; border-bottom: 1px solid #eee; ${selectedStyle} transition: all 0.2s;"
                         onmouseover="if(!this.style.background.includes('e3f2fd')) this.style.background='#f5f5f5'"
                         onmouseout="if(!this.style.background.includes('e3f2fd')) this.style.background='transparent'">
                        <div style="font-weight: 500; font-size: 12px; color: #333;">${form.form_name}</div>
                        <div style="font-size: 10px; color: #666; margin-top: 2px;">
                            版本 ${form.form_version} / 修訂 ${form.form_revision}
                            ${versionBadge}
                        </div>
                    </div>
                `;
            }

            listContainer.innerHTML = html;
        }

        /**
         * 選擇表單並載入欄位
         * @param {Object} form - 表單資料
         */
        async function selectForm(form) {
            // 優先使用 form_secure_code
            selectedFormId = form.form_secure_code || form.form_id;
            selectedFormSecureCode = form.form_secure_code || '';

            // 重新渲染列表以更新選中狀態
            renderMappedFormsList(currentMappedForms);

            // 更新標題
            const titleEl = document.getElementById('form-fields-title');
            if (titleEl) {
                titleEl.textContent = ` - ${form.form_name}`;
            }

            // 載入欄位
            await loadFormFields(form);
        }
        window.selectForm = selectForm;

        /**
         * 載入指定表單的欄位
         * @param {Object} form - 表單資料
         */
        async function loadFormFields(form) {
            const tbody = document.getElementById('form-fields-tbody');
            if (!tbody) return;

            // 顯示載入中
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 30px; color: #999;">
                        <i class="fas fa-spinner fa-spin"></i> 分析欄位中...
                    </td>
                </tr>
            `;

            try {
                // 優先使用 form_secure_code，若無則使用 form_id
                const formIdentifier = form.form_secure_code || form.form_id;
                let url = `/api/workflows/data/forms/${formIdentifier}/fields?version_type=${currentVersionType}`;
                if (form.mapping_id) {
                    url += `&mapping_id=${form.mapping_id}`;
                }
                if (form.publish_version) {
                    url += `&publish_version=${form.publish_version}`;
                }

                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '分析失敗');
                }

                currentFormFields = result.data.fields || [];
                renderFormFieldsTable(currentFormFields);

                // 載入已儲存的勾選狀態
                loadFieldReadConfigForCurrentForm();

                // 更新計數
                const countEl = document.getElementById('form-fields-count');
                if (countEl) {
                    countEl.textContent = `共 ${currentFormFields.length} 個欄位`;
                }

            } catch (error) {
                console.error('載入表單欄位失敗:', error);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 30px; color: #e74c3c;">
                            <i class="fas fa-exclamation-circle"></i> 分析失敗: ${error.message}
                        </td>
                    </tr>
                `;
            }
        }

        /**
         * 渲染欄位表格
         * @param {Array} fields - 欄位列表
         */
        function renderFormFieldsTable(fields) {
            const tbody = document.getElementById('form-fields-tbody');
            if (!tbody) return;

            if (fields.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 30px; color: #999;">
                            <i class="fas fa-info-circle"></i> 此表單沒有資料欄位
                        </td>
                    </tr>
                `;
                return;
            }

            // 取得目前此表單已勾選的欄位
            const selectedFields = getSelectedFieldsForCurrentForm();

            // Form.io 類型中文對照
            const typeLabels = {
                'textfield': '文字欄位',
                'textarea': '多行文字',
                'number': '數字',
                'password': '密碼',
                'email': '電子郵件',
                'phoneNumber': '電話號碼',
                'url': '網址',
                'currency': '貨幣',
                'checkbox': '核取方塊',
                'selectboxes': '多選方塊',
                'select': '下拉選單',
                'radio': '單選按鈕',
                'datetime': '日期時間',
                'day': '日期(日)',
                'time': '時間',
                'date': '日期',
                'hidden': '隱藏欄位',
                'signature': '簽名',
                'file': '檔案上傳',
                'tags': '標籤',
                'address': '地址',
                'datagrid': '資料表格',
                'editgrid': '編輯表格',
                'survey': '問卷'
            };

            // 資料類型標籤顏色
            const dataTypeColors = {
                'string': '#3498db',
                'number': '#27ae60',
                'boolean': '#9b59b6',
                'datetime': '#e67e22',
                'date': '#e67e22',
                'array': '#e74c3c',
                'object': '#1abc9c'
            };

            let html = '';
            for (const field of fields) {
                const typeLabel = typeLabels[field.type] || field.type;
                const dataTypeColor = dataTypeColors[field.data_type] || '#666';
                const indentStyle = field.nested_level > 0 ? `padding-left: ${field.nested_level * 15 + 8}px;` : '';
                const nestedIndicator = field.nested_level > 0 ? '<span style="color: #999; margin-right: 3px;">└</span>' : '';

                // 檢查是否已勾選取值
                const isSelected = selectedFields.includes(field.key);

                // 處理預設值/選項
                let defaultOrOptions = '-';
                if (field.options && field.options.length > 0) {
                    const optionsList = field.options.map(o => `${o.label}(${o.value})`).join(', ');
                    defaultOrOptions = `<span title="${optionsList}" style="cursor: help; color: #667eea;">[${field.options.length}個選項]</span>`;
                } else if (field.default_value !== null && field.default_value !== undefined && field.default_value !== '') {
                    defaultOrOptions = `<code style="background: #f5f5f5; padding: 1px 4px; border-radius: 2px; font-size: 10px;">${field.default_value}</code>`;
                }

                // 組合變數語法（新式變數和舊式變數）
                const displayVar = getDisplayVariable(selectedFormSecureCode, field.key);
                const internalVar = selectedFormSecureCode ? `\${${selectedFormSecureCode}_${field.key}}` : `\${${field.key}}`;

                html += `
                    <tr class="field-row" data-key="${field.key}" data-label="${field.label}"
                        data-display-var="${displayVar.replace(/"/g, '&quot;')}"
                        data-internal-var="${internalVar.replace(/"/g, '&quot;')}"
                        style="border-bottom: 1px solid #eee;"
                        onmouseover="this.style.background='#f8f9fa'"
                        onmouseout="this.style.background='transparent'">
                        <td style="padding: 6px 8px; text-align: center;">
                            <input type="checkbox" class="field-read-checkbox" data-key="${field.key}"
                                ${isSelected ? 'checked' : ''}
                                onchange="onFieldSelectionChange()"
                                style="cursor: pointer; width: 16px; height: 16px;">
                        </td>
                        <td style="padding: 6px 8px; ${indentStyle} font-size: 11px; color: #333; white-space: nowrap;">
                            ${nestedIndicator}${field.label || field.key}
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px;">
                            <code style="background: #fff3cd; padding: 2px 4px; border-radius: 3px; cursor: grab; color: #856404;"
                                  draggable="true"
                                  ondragstart="handleVarDragStart(event, '${internalVar.replace(/'/g, "\\'")}')"
                                  ondragend="handleVarDragEnd(event)"
                                  onclick="copyVarSyntax(this, '${internalVar.replace(/'/g, "\\'")}')" title="拖拉到設定區或點擊複製">${internalVar}</code>
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px;">
                            <code style="background: #d4edda; padding: 2px 4px; border-radius: 3px; cursor: grab; color: #155724;"
                                  draggable="true"
                                  ondragstart="handleVarDragStart(event, '${displayVar.replace(/'/g, "\\'")}')"
                                  ondragend="handleVarDragEnd(event)"
                                  onclick="copyVarSyntax(this, '${displayVar.replace(/'/g, "\\'")}')" title="拖拉到設定區或點擊複製">${displayVar}</code>
                        </td>
                        <td style="padding: 6px 8px; color: #666;">${typeLabel}</td>
                        <td style="padding: 6px 8px;">
                            <span style="background: ${dataTypeColor}; color: white; padding: 1px 5px; border-radius: 2px; font-size: 10px;">${field.data_type}</span>
                        </td>
                        <td style="padding: 6px 8px; text-align: center;">
                            ${field.required ? '<i class="fas fa-check" style="color: #27ae60;"></i>' : '<i class="fas fa-minus" style="color: #ccc;"></i>'}
                        </td>
                        <td style="padding: 6px 8px; font-size: 10px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${defaultOrOptions}
                        </td>
                    </tr>
                `;
            }

            tbody.innerHTML = html;
        }

        /**
         * 篩選表單欄位
         */
        function filterFormFields() {
            const searchInput = document.getElementById('field-search');
            if (!searchInput) return;

            const keyword = searchInput.value.toLowerCase().trim();
            const rows = document.querySelectorAll('#form-fields-tbody .field-row');

            let visibleCount = 0;
            rows.forEach(row => {
                const key = (row.dataset.key || '').toLowerCase();
                const label = (row.dataset.label || '').toLowerCase();

                if (!keyword || key.includes(keyword) || label.includes(keyword)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            // 更新計數
            const countEl = document.getElementById('form-fields-count');
            if (countEl) {
                if (keyword) {
                    countEl.textContent = `顯示 ${visibleCount} / ${currentFormFields.length} 個欄位`;
                } else {
                    countEl.textContent = `共 ${currentFormFields.length} 個欄位`;
                }
            }
        }

        /**
         * HTML 特殊字元跳脫
         * @param {string} text - 要跳脫的文字
         * @returns {string} 跳脫後的文字
         */
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        /**
         * 複製文字到剪貼簿
         * @param {string} text - 要複製的文字
         */
        async function copyToClipboard(text) {
            try {
                await navigator.clipboard.writeText(text);
                updateStatus(`✅ 已複製: ${text}`);
            } catch (err) {
                console.error('複製失敗:', err);
                // 備用方案：使用 execCommand
                try {
                    const textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    updateStatus(`✅ 已複製: ${text}`);
                } catch (e) {
                    updateStatus('❌ 複製失敗');
                }
            }
        }

        /**
         * 複製變數語法到剪貼簿（含視覺反饋）
         * @param {HTMLElement} element - 被點擊的元素
         * @param {string} text - 要複製的文字
         */
        function copyVarSyntax(element, text) {
            // 使用備用方案確保複製成功
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製: ${text}`);

                // 視覺反饋
                if (element) {
                    const originalBg = element.style.background;
                    const originalColor = element.style.color;
                    element.style.background = '#28a745';
                    element.style.color = 'white';
                    setTimeout(() => {
                        element.style.background = originalBg || '';
                        element.style.color = originalColor || '';
                    }, 300);
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製勾選的新式變數到剪貼簿
         */
        function copySelectedDisplayVars() {
            // 取得所有勾選的欄位行
            const checkedRows = document.querySelectorAll('#form-fields-tbody .field-row input.field-read-checkbox:checked');

            if (checkedRows.length === 0) {
                updateStatus('⚠ 請先勾選要複製的欄位');
                return;
            }

            // 收集所有勾選欄位的新式變數
            const displayVars = [];
            checkedRows.forEach(checkbox => {
                const row = checkbox.closest('.field-row');
                if (row && row.dataset.displayVar) {
                    displayVars.push(row.dataset.displayVar);
                }
            });

            if (displayVars.length === 0) {
                updateStatus('⚠ 沒有可複製的變數');
                return;
            }

            // 複製到剪貼簿（用換行分隔）
            const text = displayVars.join('\n');

            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製 ${displayVars.length} 個新式變數到剪貼簿`);
                // 複製成功後自動收合面板
                if (isPanelExpanded) {
                    toggleControlPanel();
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製勾選欄位的舊式變數到剪貼簿
         */
        function copySelectedOldVars() {
            // 取得所有勾選的欄位行
            const checkedRows = document.querySelectorAll('#form-fields-tbody .field-row input.field-read-checkbox:checked');

            if (checkedRows.length === 0) {
                updateStatus('⚠ 請先勾選要複製的欄位');
                return;
            }

            // 收集所有勾選欄位的舊式變數
            const internalVars = [];
            checkedRows.forEach(checkbox => {
                const row = checkbox.closest('.field-row');
                if (row && row.dataset.internalVar) {
                    internalVars.push(row.dataset.internalVar);
                }
            });

            if (internalVars.length === 0) {
                updateStatus('⚠ 沒有可複製的變數');
                return;
            }

            // 複製到剪貼簿（用換行分隔）
            const text = internalVars.join('\n');

            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製 ${internalVars.length} 個舊式變數到剪貼簿`);
                // 複製成功後自動收合面板
                if (isPanelExpanded) {
                    toggleControlPanel();
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製欄位表格內容
         */
        function copyFieldsTable() {
            if (currentFormFields.length === 0) {
                updateStatus('⚠ 沒有欄位可複製');
                return;
            }

            // 建立 TSV 格式 (Tab-Separated Values)
            let tsv = '欄位代碼\t顯示名稱\t類型\t資料型別\t必填\t路徑\n';
            for (const field of currentFormFields) {
                tsv += `${field.key}\t${field.label}\t${field.type}\t${field.data_type}\t${field.required ? '是' : '否'}\t${field.path}\n`;
            }

            copyToClipboard(tsv);
        }

        // ==================== 變數拖放功能 ====================

        /**
         * 變數拖放開始事件處理
         */
        function handleVarDragStart(e, varText) {
            e.dataTransfer.setData('text/plain', varText);
            e.dataTransfer.effectAllowed = 'copy';
            e.target.style.opacity = '0.5';
        }

        /**
         * 變數拖放結束事件處理
         */
        function handleVarDragEnd(e) {
            e.target.style.opacity = '1';
        }
        window.handleVarDragStart = handleVarDragStart;
        window.handleVarDragEnd = handleVarDragEnd;

        /**
         * 初始化設定區輸入框的拖放接收
         */
        function initDropTargets() {
            // 為 nodeSettings 區域內的所有 input 和 textarea 添加拖放支援
            const nodeSettings = document.getElementById('nodeSettings');
            if (!nodeSettings) return;

            nodeSettings.addEventListener('dragover', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'copy';
                    target.style.background = '#e8f4fd';
                    target.style.borderColor = '#2196f3';
                }
            });

            nodeSettings.addEventListener('dragleave', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    target.style.background = '';
                    target.style.borderColor = '';
                }
            });

            nodeSettings.addEventListener('drop', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    e.preventDefault();
                    const varText = e.dataTransfer.getData('text/plain');
                    if (varText) {
                        // 在游標位置插入變數
                        const start = target.selectionStart || 0;
                        const end = target.selectionEnd || 0;
                        const currentValue = target.value;
                        target.value = currentValue.substring(0, start) + varText + currentValue.substring(end);
                        // 設定游標位置到插入文字之後
                        const newPos = start + varText.length;
                        target.setSelectionRange(newPos, newPos);
                        target.focus();
                        updateStatus(`✅ 已插入變數 ${varText}`);
                    }
                    target.style.background = '';
                    target.style.borderColor = '';
                }
            });
        }

        // 頁面載入後初始化拖放目標
        setTimeout(initDropTargets, 500);

        // ==================== OPSET 自訂變數統計功能 ====================

        /**
         * 掃描所有 OPSET 節點並更新變數統計表
         */
        function reloadOpsetVars() {
            const tbody = document.getElementById('opset-vars-tbody');
            const countEl = document.getElementById('opset-vars-count');
            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            if (!tbody) return;

            // 重置全選勾選框
            if (selectAllCheckbox) selectAllCheckbox.checked = false;

            // 檢查是否有 Cytoscape 實例
            if (!window.cy) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 30px; color: #999;">
                            <i class="fas fa-exclamation-circle"></i> 流程圖尚未載入
                        </td>
                    </tr>
                `;
                if (countEl) countEl.textContent = '';
                return;
            }

            // 運算元中文對照
            const operationLabels = {
                'set': '設定',
                'add': '加法',
                'subtract': '減法',
                'multiply': '乘法',
                'divide': '除法',
                'concat': '字串連接',
                'convert': '型別轉換',
                'increment': '遞增',
                'decrement': '遞減',
                'expr': '表達式'
            };

            // 掃描所有 OPSET 節點
            const opsetNodes = cy.nodes().filter(n => {
                const nodeType = n.data('type') || '';
                return nodeType.toLowerCase() === 'opset';
            });

            if (opsetNodes.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 30px; color: #999;">
                            <i class="fas fa-info-circle"></i> 流程圖中沒有 OPSET 節點
                        </td>
                    </tr>
                `;
                if (countEl) countEl.textContent = '（0 個變數）';
                return;
            }

            // 交替背景色（按節點）
            const nodeColors = ['#e5f4ff', '#ebffff'];

            // 收集所有變數（同時記錄節點索引）
            const allVars = [];
            opsetNodes.forEach((node, nodeIndex) => {
                const nodeId = node.id();
                const displayName = node.data('display_name') || node.data('label') || nodeId;
                const config = node.data('config') || {};
                const operations = config.operations || [];
                // 描述存在 node.data('description')，不是 config.description
                const description = node.data('description') || '';

                // 提取 node ID 中的數字部分
                const nodeNumber = nodeId.replace(/^node-(OPSET|OpSet)-/i, '');

                // 該節點使用的背景色（奇數=0, 偶數=1）
                const bgColor = nodeColors[nodeIndex % 2];

                operations.forEach(op => {
                    allVars.push({
                        nodeId: nodeId,
                        nodeNumber: nodeNumber,
                        displayName: displayName,
                        description: description,
                        targetVar: op.target_var || '',
                        operation: op.operation || 'set',
                        value: op.value || '',
                        bgColor: bgColor
                    });
                });
            });

            if (allVars.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 30px; color: #999;">
                            <i class="fas fa-info-circle"></i> OPSET 節點尚未設定任何變數
                        </td>
                    </tr>
                `;
                if (countEl) countEl.textContent = '（0 個變數）';
                return;
            }

            // 生成表格
            let html = '';
            allVars.forEach(v => {
                const opLabel = operationLabels[v.operation] || v.operation;
                // 處理多行值：用 <br> 顯示
                const displayValue = String(v.value || '').replace(/\n/g, '<br>');
                const varText = `\${${v.targetVar}}`;

                html += `
                    <tr style="border-bottom: 1px solid #ddd; background: ${v.bgColor}; cursor: pointer;"
                        title="點擊跳轉到節點">
                        <td style="padding: 6px 8px; text-align: center;" onclick="event.stopPropagation();">
                            <input type="checkbox" class="opset-var-checkbox" data-var="${escapeHtml(varText)}">
                        </td>
                        <td style="padding: 6px 8px;" onclick="focusOnNode('${v.nodeId}')">
                            <span style="color: #667eea; text-decoration: underline;">${escapeHtml(v.displayName)}</span>
                        </td>
                        <td style="padding: 6px 8px; font-size: 10px; color: #666; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" onclick="focusOnNode('${v.nodeId}')" title="${escapeHtml(v.description)}">
                            ${escapeHtml(v.description) || '-'}
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px; color: #666;" onclick="focusOnNode('${v.nodeId}')">
                            ${v.nodeNumber}
                        </td>
                        <td style="padding: 6px 8px;" onclick="event.stopPropagation();">
                            <code style="background: #e8f4fd; padding: 2px 6px; border-radius: 3px; color: #1976d2; cursor: grab;"
                                  draggable="true"
                                  ondragstart="handleVarDragStart(event, '${escapeHtml(varText)}')"
                                  ondragend="handleVarDragEnd(event)"
                                  onclick="copyOpsetVarToClipboard('${escapeHtml(v.targetVar)}')"
                                  title="拖拉到設定區或點擊複製">${escapeHtml(varText)}</code>
                        </td>
                        <td style="padding: 6px 8px;" onclick="focusOnNode('${v.nodeId}')">
                            <span style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 10px;">${opLabel}</span>
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px; max-width: 300px; overflow: hidden; text-overflow: ellipsis;" onclick="focusOnNode('${v.nodeId}')">
                            ${displayValue}
                        </td>
                    </tr>
                `;
            });

            tbody.innerHTML = html;
            if (countEl) countEl.textContent = `（共 ${allVars.length} 個變數）`;

            updateStatus(`✅ 已掃描 ${opsetNodes.length} 個 OPSET 節點，共 ${allVars.length} 個自訂變數`);
        }
        window.reloadOpsetVars = reloadOpsetVars;

        /**
         * 點擊變數名稱複製到剪貼簿
         */
        function copyOpsetVarToClipboard(varName) {
            const varText = `\${${varName}}`;
            copyToClipboard(varText);
            updateStatus(`✅ 已複製變數 ${varText} 到剪貼簿`);
        }
        window.copyOpsetVarToClipboard = copyOpsetVarToClipboard;

        /**
         * 全選/取消全選 OPSET 變數
         */
        function toggleAllOpsetVarSelection() {
            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            const checkboxes = document.querySelectorAll('.opset-var-checkbox');

            checkboxes.forEach(cb => {
                cb.checked = selectAllCheckbox.checked;
            });
        }
        window.toggleAllOpsetVarSelection = toggleAllOpsetVarSelection;

        /**
         * 複製選中的 OPSET 變數到剪貼簿
         */
        function copySelectedOpsetVars() {
            const checkboxes = document.querySelectorAll('.opset-var-checkbox:checked');

            if (checkboxes.length === 0) {
                updateStatus('⚠ 請先勾選要複製的變數');
                return;
            }

            const vars = [];
            checkboxes.forEach(cb => {
                vars.push(cb.getAttribute('data-var'));
            });

            const text = vars.join('\n');
            copyToClipboard(text);
            updateStatus(`✅ 已複製 ${vars.length} 個變數到剪貼簿`);

            // 取消所有勾選
            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            if (selectAllCheckbox) selectAllCheckbox.checked = false;
            document.querySelectorAll('.opset-var-checkbox').forEach(cb => cb.checked = false);
        }
        window.copySelectedOpsetVars = copySelectedOpsetVars;

        /**
         * 複製 OPSET 變數表格到剪貼簿
         */
        function copyOpsetVarsTable() {
            if (!window.cy) {
                updateStatus('⚠ 流程圖尚未載入');
                return;
            }

            // 掃描所有 OPSET 節點
            const opsetNodes = cy.nodes().filter(n => {
                const nodeType = n.data('type') || '';
                return nodeType.toLowerCase() === 'opset';
            });

            if (opsetNodes.length === 0) {
                updateStatus('⚠ 沒有 OPSET 節點可複製');
                return;
            }

            // 收集所有變數（含描述欄位）
            let tsv = '節點名稱\t描述\tNode ID\t變數名稱\t運算元\t值/表達式\n';

            opsetNodes.forEach(node => {
                const nodeId = node.id();
                const displayName = node.data('display_name') || node.data('label') || nodeId;
                const config = node.data('config') || {};
                const operations = config.operations || [];
                // 描述存在 node.data('description')，不是 config.description
                const description = (node.data('description') || '').replace(/\t/g, ' ').replace(/\n/g, '\\n');
                const nodeNumber = nodeId.replace(/^node-(OPSET|OpSet)-/i, '');

                operations.forEach(op => {
                    const targetVar = op.target_var || '';
                    const operation = op.operation || 'set';
                    const value = String(op.value || '').replace(/\t/g, ' ').replace(/\n/g, '\\n');
                    tsv += `${displayName}\t${description}\t${nodeNumber}\t\${${targetVar}}\t${operation}\t${value}\n`;
                });
            });

            copyToClipboard(tsv);
            updateStatus('✅ 已複製 OPSET 變數表格到剪貼簿');
        }
        window.copyOpsetVarsTable = copyOpsetVarsTable;

        /**
         * 跳轉到指定節點並選中
         */
        function focusOnNode(nodeId) {
            if (!window.cy) return;

            const node = cy.getElementById(nodeId);
            if (node.length === 0) {
                updateStatus('⚠ 找不到節點: ' + nodeId);
                return;
            }

            // 取消所有選擇
            cy.elements().unselect();

            // 選中目標節點
            node.select();

            // 將視圖移動到節點
            cy.animate({
                center: { eles: node },
                duration: 300
            });

            // 顯示節點資訊
            showNodeInfo(node);
        }
        window.focusOnNode = focusOnNode;

        // ==================== 欄位取值設定功能 ====================

        // 用於追蹤設定是否已修改
        let fieldReadConfigDirty = false;
        // 防抖動計時器
        let fieldReadSaveDebounceTimer = null;

        /**
         * 從 cytoscape_config 取得目前選中表單的已勾選欄位
         * @returns {Array} 已勾選的欄位 key 陣列
         */
        function getSelectedFieldsForCurrentForm() {
            if (!selectedFormId || !cy) return [];

            // 從 cytoscape 的設定中取得 fieldReadConfig
            const config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${selectedFormId}`;

            if (config[formKey] && Array.isArray(config[formKey].fields)) {
                return config[formKey].fields;
            }

            return [];
        }

        /**
         * 全選/取消全選欄位
         */
        function toggleAllFieldSelection() {
            const selectAll = document.getElementById('field-select-all');
            if (!selectAll) return;

            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });

            onFieldSelectionChange();
        }

        /**
         * 當欄位勾選狀態改變時（勾選即自動儲存）
         */
        function onFieldSelectionChange() {
            fieldReadConfigDirty = true;
            updateSelectAllCheckbox();

            // 顯示儲存中狀態
            const statusEl = document.getElementById('field-config-status');
            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;
            if (statusEl) {
                statusEl.innerHTML = `<span style="color: #3498db;"><i class="fas fa-spinner fa-spin"></i> 已選 ${checkedCount} 個欄位 (儲存中...)</span>`;
            }

            // 防抖動：300ms 後自動儲存
            if (fieldReadSaveDebounceTimer) {
                clearTimeout(fieldReadSaveDebounceTimer);
            }
            fieldReadSaveDebounceTimer = setTimeout(() => {
                saveFieldReadConfig();
            }, 300);
        }

        /**
         * 更新全選 checkbox 的狀態
         */
        function updateSelectAllCheckbox() {
            const selectAll = document.getElementById('field-select-all');
            if (!selectAll) return;

            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;

            if (checkedCount === 0) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            } else if (checkedCount === checkboxes.length) {
                selectAll.checked = true;
                selectAll.indeterminate = false;
            } else {
                selectAll.checked = false;
                selectAll.indeterminate = true;
            }
        }

        /**
         * 更新欄位設定狀態顯示
         */
        function updateFieldConfigStatus() {
            const statusEl = document.getElementById('field-config-status');
            if (!statusEl) return;

            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;

            if (fieldReadConfigDirty) {
                statusEl.innerHTML = `<span style="color: #e67e22;"><i class="fas fa-exclamation-circle"></i> 已選 ${checkedCount} 個欄位 (未儲存)</span>`;
            } else {
                statusEl.innerHTML = `<span style="color: #27ae60;"><i class="fas fa-check-circle"></i> 已選 ${checkedCount} 個欄位</span>`;
            }
        }

        /**
         * 取得目前勾選的欄位列表
         * @returns {Array} 勾選的欄位 key 陣列
         */
        function getCheckedFieldKeys() {
            const checkboxes = document.querySelectorAll('.field-read-checkbox:checked');
            return Array.from(checkboxes).map(cb => cb.dataset.key);
        }

        /**
         * 儲存欄位取值設定到 cytoscape_config
         */
        async function saveFieldReadConfig() {
            if (!selectedFormId || !cy) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            // 取得目前勾選的欄位
            const selectedKeys = getCheckedFieldKeys();

            // 取得目前選中的表單資訊
            const currentForm = currentMappedForms.find(f => f.form_id === selectedFormId);
            if (!currentForm) {
                updateStatus('❌ 找不到表單資訊');
                return;
            }

            // 取得或建立 fieldReadConfig
            let config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${selectedFormId}`;

            // 更新此表單的設定
            if (selectedKeys.length > 0) {
                config[formKey] = {
                    formName: currentForm.form_name,
                    formSecureCode: currentForm.form_secure_code,
                    fields: selectedKeys
                };
            } else {
                // 沒有勾選則移除此表單的設定
                delete config[formKey];
            }

            // 儲存回 cytoscape
            cy.data('fieldReadConfig', config);

            // 標記為需要儲存流程
            fieldReadConfigDirty = false;
            updateFieldConfigStatus();

            // 觸發流程儲存
            try {
                await saveWorkflow();
                updateStatus(`✅ 已儲存「${currentForm.form_name}」的欄位取值設定 (${selectedKeys.length} 個欄位)`);
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus('❌ 儲存失敗: ' + error.message);
                fieldReadConfigDirty = true;
                updateFieldConfigStatus();
            }
        }

        /**
         * 載入表單欄位時同步載入已儲存的勾選狀態
         */
        function loadFieldReadConfigForCurrentForm() {
            if (!selectedFormId || !cy) return;

            const selectedFields = getSelectedFieldsForCurrentForm();

            // 更新 checkbox 狀態
            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = selectedFields.includes(cb.dataset.key);
            });

            // 重置 dirty 狀態
            fieldReadConfigDirty = false;
            updateSelectAllCheckbox();
            updateFieldConfigStatus();
        }

        // ==================== 變數配置功能 ====================

        // 變數配置專用的暫存資料
        let varConfigReadFields = [];   // FieldRead 的欄位清單
        let varConfigWriteFields = [];  // FieldWrite 的欄位清單
        let varConfigReadFormId = null;
        let varConfigWriteFormId = null;
        let varConfigReadFormCode = '';
        let varConfigWriteFormCode = '';

        /**
         * 切換表單欄位子分頁
         * @param {string} subTabName - 子分頁名稱 (fieldlist / varconfig)
         */
        function switchFormFieldsSubTab(subTabName) {
            const subtabFieldlist = document.getElementById('subtab-fieldlist');
            const subtabVarconfig = document.getElementById('subtab-varconfig');
            const contentFieldlist = document.getElementById('subtab-fieldlist-content');
            const contentVarconfig = document.getElementById('subtab-varconfig-content');

            // 重置所有子分頁按鈕
            if (subtabFieldlist) {
                subtabFieldlist.style.background = '#e0e0e0';
                subtabFieldlist.style.color = '#666';
            }
            if (subtabVarconfig) {
                subtabVarconfig.style.background = '#e0e0e0';
                subtabVarconfig.style.color = '#666';
            }

            // 隱藏所有內容
            if (contentFieldlist) contentFieldlist.style.display = 'none';
            if (contentVarconfig) contentVarconfig.style.display = 'none';

            // 啟用選中的子分頁
            if (subTabName === 'fieldlist') {
                if (subtabFieldlist) {
                    subtabFieldlist.style.background = '#667eea';
                    subtabFieldlist.style.color = 'white';
                }
                if (contentFieldlist) contentFieldlist.style.display = 'flex';
            } else if (subTabName === 'varconfig') {
                if (subtabVarconfig) {
                    subtabVarconfig.style.background = '#667eea';
                    subtabVarconfig.style.color = 'white';
                }
                if (contentVarconfig) contentVarconfig.style.display = 'block';
                // 首次切換到變數配置時，載入表單選項
                populateVarConfigFormSelects();
            }
        }

        /**
         * 填充變數配置的表單下拉選單
         */
        function populateVarConfigFormSelects() {
            const readSelect = document.getElementById('varconfig-read-form');
            const writeSelect = document.getElementById('varconfig-write-form');

            if (!readSelect || !writeSelect) return;

            // 確保已載入配對表單
            if (currentMappedForms.length === 0) {
                readSelect.innerHTML = '<option value="">-- 請先載入配對表單 --</option>';
                writeSelect.innerHTML = '<option value="">-- 請先載入配對表單 --</option>';
                return;
            }

            let optionsHtml = '<option value="">-- 請選擇表單 --</option>';
            for (const form of currentMappedForms) {
                optionsHtml += `<option value="${form.form_id}" data-code="${form.form_secure_code}" data-name="${form.form_name}">${form.form_name} (${form.form_secure_code})</option>`;
            }

            readSelect.innerHTML = optionsHtml;
            writeSelect.innerHTML = optionsHtml;
        }

        /**
         * 當變數配置的表單選擇改變時
         * @param {string} mode - 'read' 或 'write'
         */
        async function onVarConfigFormChange(mode) {
            const select = document.getElementById(`varconfig-${mode}-form`);
            const fieldsContainer = document.getElementById(`varconfig-${mode}-fields`);

            if (!select || !fieldsContainer) return;

            const formId = select.value;
            const selectedOption = select.options[select.selectedIndex];
            const formCode = selectedOption.dataset.code || '';
            const formName = selectedOption.dataset.name || '';

            if (!formId) {
                fieldsContainer.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                        請先選擇表單
                    </div>
                `;
                if (mode === 'read') {
                    varConfigReadFields = [];
                    varConfigReadFormId = null;
                    varConfigReadFormCode = '';
                } else {
                    varConfigWriteFields = [];
                    varConfigWriteFormId = null;
                    varConfigWriteFormCode = '';
                }
                updateVarConfigPreview(mode);
                return;
            }

            // 儲存表單資訊
            if (mode === 'read') {
                varConfigReadFormId = parseInt(formId);
                varConfigReadFormCode = formCode;
            } else {
                varConfigWriteFormId = parseInt(formId);
                varConfigWriteFormCode = formCode;
            }

            // 載入欄位
            fieldsContainer.innerHTML = `
                <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                    <i class="fas fa-spinner fa-spin"></i> 載入欄位中...
                </div>
            `;

            try {
                const form = currentMappedForms.find(f => f.form_id === parseInt(formId));
                let url = `/api/workflows/data/forms/${formId}/fields?version_type=${currentVersionType}`;
                if (form && form.mapping_id) {
                    url += `&mapping_id=${form.mapping_id}`;
                }

                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '載入失敗');
                }

                const fields = result.data.fields || [];

                if (mode === 'read') {
                    varConfigReadFields = fields;
                } else {
                    varConfigWriteFields = fields;
                }

                renderVarConfigFields(mode, fields, formCode);

            } catch (error) {
                console.error('載入欄位失敗:', error);
                fieldsContainer.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #e74c3c; font-size: 11px;">
                        <i class="fas fa-exclamation-circle"></i> 載入失敗: ${error.message}
                    </div>
                `;
            }
        }

        /**
         * 渲染變數配置的欄位清單
         * @param {string} mode - 'read' 或 'write'
         * @param {Array} fields - 欄位列表
         * @param {string} formCode - 表單代碼
         */
        function renderVarConfigFields(mode, fields, formCode) {
            const container = document.getElementById(`varconfig-${mode}-fields`);
            if (!container) return;

            if (fields.length === 0) {
                container.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                        此表單沒有資料欄位
                    </div>
                `;
                return;
            }

            let html = '';
            for (const field of fields) {
                const varName = `${formCode}_${field.key}`;
                html += `
                    <div style="padding: 6px 10px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 8px;"
                         onmouseover="this.style.background='#f8f9fa'" onmouseout="this.style.background='white'">
                        <input type="checkbox" class="varconfig-${mode}-checkbox" data-key="${field.key}" data-label="${field.label}"
                               onchange="updateVarConfigPreview('${mode}')" style="cursor: pointer;">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 11px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${field.label}
                            </div>
                            <div style="font-size: 10px; color: #667eea; font-family: monospace;">${field.key}</div>
                        </div>
                    </div>
                `;
            }

            container.innerHTML = html;
            updateVarConfigPreview(mode);
        }

        /**
         * 取得目前流程中已設定的所有變數名稱（用於衝突檢測）
         * @returns {Set} 已存在的變數名稱集合
         */
        function getExistingVarNames() {
            const existingVars = new Set();

            if (!cy) return existingVars;

            // 從 fieldReadConfig 取得已設定的變數
            const fieldReadConfig = cy.data('fieldReadConfig') || {};
            for (const formKey in fieldReadConfig) {
                const formConfig = fieldReadConfig[formKey];
                if (formConfig.formSecureCode && formConfig.fields) {
                    for (const fieldKey of formConfig.fields) {
                        // 加入帶前綴和不帶前綴的變數名稱
                        existingVars.add(`${formConfig.formSecureCode}_${fieldKey}`);
                        existingVars.add(fieldKey);
                    }
                }
            }

            return existingVars;
        }

        /**
         * 更新變數配置預覽
         * @param {string} mode - 'read' 或 'write'
         */
        function updateVarConfigPreview(mode) {
            const preview = document.getElementById(`varconfig-${mode}-preview`);
            const countEl = document.getElementById(`varconfig-${mode}-count`);
            const formCode = mode === 'read' ? varConfigReadFormCode : varConfigWriteFormCode;

            if (!preview) return;

            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox:checked`);
            const selectedFields = Array.from(checkboxes).map(cb => ({
                key: cb.dataset.key,
                label: cb.dataset.label
            }));

            // 更新計數
            if (countEl) {
                countEl.textContent = `(${selectedFields.length})`;
            }

            if (selectedFields.length === 0) {
                preview.innerHTML = `
                    <div style="padding: 10px; text-align: center; color: #999;">
                        尚未選擇欄位
                    </div>
                `;
                return;
            }

            // 取得已存在的變數名稱（用於衝突檢測）
            const existingVars = getExistingVarNames();

            let html = '<table style="width: 100%; border-collapse: collapse;">';
            html += '<tr style="background: #f5f5f5;"><th style="padding: 4px 8px; text-align: left; font-size: 10px; border-bottom: 1px solid #ddd;">欄位</th><th style="padding: 4px 8px; text-align: left; font-size: 10px; border-bottom: 1px solid #ddd;">變數名稱</th></tr>';

            for (const field of selectedFields) {
                const varName = `${formCode}_${field.key}`;
                const hasConflict = existingVars.has(varName) || existingVars.has(field.key);
                const conflictIndicator = hasConflict ? '<span style="color: #dc3545; margin-right: 4px;" title="變數已存在，將被覆蓋">●</span>' : '';

                html += `
                    <tr style="border-bottom: 1px solid #f0f0f0;">
                        <td style="padding: 4px 8px; font-size: 10px;">${field.label}</td>
                        <td style="padding: 4px 8px; font-size: 10px; font-family: monospace;">
                            ${conflictIndicator}<code style="background: #e8f4fd; padding: 1px 4px; border-radius: 2px;">${varName}</code>
                        </td>
                    </tr>
                `;
            }
            html += '</table>';

            preview.innerHTML = html;
        }

        /**
         * 全選欄位
         * @param {string} mode - 'read' 或 'write'
         */
        function varConfigSelectAll(mode) {
            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox`);
            checkboxes.forEach(cb => cb.checked = true);
            updateVarConfigPreview(mode);
        }

        /**
         * 清除選擇
         * @param {string} mode - 'read' 或 'write'
         */
        function varConfigDeselectAll(mode) {
            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox`);
            checkboxes.forEach(cb => cb.checked = false);
            updateVarConfigPreview(mode);
        }

        /**
         * 套用 FieldRead 變數配置
         */
        async function applyVarConfigRead() {
            if (!varConfigReadFormId || !varConfigReadFormCode) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            const checkboxes = document.querySelectorAll('.varconfig-read-checkbox:checked');
            const selectedKeys = Array.from(checkboxes).map(cb => cb.dataset.key);

            if (selectedKeys.length === 0) {
                updateStatus('⚠ 請至少選擇一個欄位');
                return;
            }

            // 取得表單資訊
            const form = currentMappedForms.find(f => f.form_id === varConfigReadFormId);
            if (!form) {
                updateStatus('❌ 找不到表單資訊');
                return;
            }

            // 取得或建立 fieldReadConfig
            let config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${varConfigReadFormId}`;

            // 更新此表單的設定
            config[formKey] = {
                formName: form.form_name,
                formSecureCode: varConfigReadFormCode,
                fields: selectedKeys
            };

            // 儲存回 cytoscape
            cy.data('fieldReadConfig', config);

            // 觸發流程儲存
            try {
                await saveWorkflow();
                updateStatus(`✅ 已套用 FieldRead 設定：${form.form_name} (${selectedKeys.length} 個欄位)`);

                // 同步更新「欄位查詢」分頁的勾選狀態（如果是同一個表單）
                if (selectedFormId === varConfigReadFormId) {
                    loadFieldReadConfigForCurrentForm();
                }
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus('❌ 儲存失敗: ' + error.message);
            }
        }

        /**
         * 複製 FieldWrite 變數語法
         */
        function copyVarConfigWriteSyntax() {
            if (!varConfigWriteFormCode) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            const checkboxes = document.querySelectorAll('.varconfig-write-checkbox:checked');

            const selectedFields = Array.from(checkboxes).map(cb => ({
                key: cb.dataset.key,
                label: cb.dataset.label
            }));

            if (selectedFields.length === 0) {
                updateStatus('⚠ 請至少選擇一個欄位');
                return;
            }

            // 產生變數語法
            const syntaxLines = selectedFields.map(field => {
                const varName = `${varConfigWriteFormCode}_${field.key}`;
                return `\${${varName}}`;
            });

            // 選取大於1個時每個後面加換行，只選1個時無換行
            const syntaxText = selectedFields.length > 1
                ? syntaxLines.join('\n')
                : syntaxLines[0];

            // 複製到剪貼簿（使用 fallback 方法）
            copyToClipboard(syntaxText, selectedFields.length);
        }
        window.copyVarConfigWriteSyntax = copyVarConfigWriteSyntax;

        /**
         * 通用複製到剪貼簿函數（含 fallback）
         */
        function copyToClipboard(text, count) {
            // 嘗試使用現代 API
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    updateStatus(`✅ 已複製 ${count} 個變數語法到剪貼簿`);
                }).catch(err => {
                    // 失敗時使用 fallback
                    fallbackCopyToClipboard(text, count);
                });
            } else {
                // 不支援時使用 fallback
                fallbackCopyToClipboard(text, count);
            }
        }

        /**
         * Fallback 複製方法（使用隱藏 textarea）
         */
        function fallbackCopyToClipboard(text, count) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            textarea.style.top = '-9999px';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            try {
                const successful = document.execCommand('copy');
                if (successful) {
                    updateStatus(`✅ 已複製 ${count} 個變數語法到剪貼簿`);
                } else {
                    updateStatus('❌ 複製失敗');
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗: ' + err.message);
            }

            document.body.removeChild(textarea);
        }

        // =============================================================================
        // 欄位權限設定 Modal
        // =============================================================================

        let fieldPermCurrentNodeId = null;
        let fieldPermFormFields = [];

        /**
         * 開啟欄位權限設定 Modal
         */
        async function openFieldPermissionsModal(nodeId) {
            fieldPermCurrentNodeId = nodeId;
            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            // 確保 Modal DOM 存在
            ensureFieldPermissionsModal();

            const modal = document.getElementById('fieldPermModal');
            modal.style.display = 'flex';

            const content = document.getElementById('fieldPermContent');
            content.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;"><i class="fas fa-spinner fa-spin"></i> 載入表單欄位中...</div>';

            // 載入配對表單的欄位
            if (!currentMappedForms || currentMappedForms.length === 0) {
                await loadMappedForms('design');
            }

            if (!currentMappedForms || currentMappedForms.length === 0) {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> 此流程尚未配對任何表單，請先到「配對管理」建立配對。</div>';
                return;
            }

            // 取得第一張配對表單的欄位
            const form = currentMappedForms[0];
            const formIdentifier = form.form_secure_code || form.form_id;
            let url = `/api/workflows/data/forms/${formIdentifier}/fields?version_type=design`;
            if (form.mapping_id) url += `&mapping_id=${form.mapping_id}`;

            try {
                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) throw new Error(result.message || '載入失敗');

                fieldPermFormFields = result.data.fields || [];
                renderFieldPermissionsTable(node, form.form_name);
            } catch (error) {
                content.innerHTML = `<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> ${error.message}</div>`;
            }
        }
        window.openFieldPermissionsModal = openFieldPermissionsModal;

        /**
         * 確保 Modal DOM 存在
         */
        function ensureFieldPermissionsModal() {
            if (document.getElementById('fieldPermModal')) return;

            const modal = document.createElement('div');
            modal.id = 'fieldPermModal';
            modal.style.cssText = 'display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:10000; justify-content:center; align-items:center;';
            modal.innerHTML = `
                <div style="background:white; width:90%; max-width:900px; max-height:90vh; border-radius:8px; display:flex; flex-direction:column; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <div style="padding:16px 20px; border-bottom:1px solid #e0e0e0; display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0; font-size:16px;"><i class="fas fa-shield-alt"></i> 欄位權限設定</h3>
                        <button onclick="closeFieldPermissionsModal()" style="background:none; border:none; font-size:20px; cursor:pointer; color:#666;">&times;</button>
                    </div>
                    <div id="fieldPermContent" style="padding:20px; overflow-y:auto; flex:1;"></div>
                    <div style="padding:12px 20px; border-top:1px solid #e0e0e0; display:flex; justify-content:flex-end; gap:8px;">
                        <button onclick="closeFieldPermissionsModal()" style="padding:8px 16px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:4px; cursor:pointer;">取消</button>
                        <button onclick="saveFieldPermissions()" style="padding:8px 16px; background:#667eea; color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fas fa-save"></i> 儲存</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        function closeFieldPermissionsModal() {
            const modal = document.getElementById('fieldPermModal');
            if (modal) modal.style.display = 'none';
            fieldPermCurrentNodeId = null;
        }
        window.closeFieldPermissionsModal = closeFieldPermissionsModal;

        /**
         * 渲染欄位權限表格
         */
        function renderFieldPermissionsTable(node, formName) {
            const content = document.getElementById('fieldPermContent');
            const currentConfig = node.data('config') || {};
            const savedPerms = currentConfig.field_permissions || {};
            const approverPerms = savedPerms.approver || {};
            const readerPerms = savedPerms.reader || {};

            if (fieldPermFormFields.length === 0) {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">此表單沒有可設定的欄位</div>';
                return;
            }

            const permOptions = [
                { value: 'readonly', label: '唯讀' },
                { value: 'editable', label: '可修改' },
                { value: 'hidden', label: '隱藏' },
            ];

            function makeSelect(name, currentVal) {
                return `<select data-perm="${name}" style="width:100%; padding:4px 6px; border:1px solid #d1d5db; border-radius:3px; font-size:12px; background:white;">
                    ${permOptions.map(o => `<option value="${o.value}" ${currentVal === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                </select>`;
            }

            let rows = '';
            fieldPermFormFields.forEach(field => {
                const aVal = approverPerms[field.key] || 'readonly';
                const rVal = readerPerms[field.key] || 'readonly';
                rows += `<tr style="border-bottom:1px solid #f3f4f6;">
                    <td style="padding:8px 10px; font-size:12px; font-weight:500; white-space:nowrap;">${field.label || field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#666;">${field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#888;">${field.type}</td>
                    <td style="padding:8px 10px;">${makeSelect('approver_' + field.key, aVal)}</td>
                    <td style="padding:8px 10px;">${makeSelect('reader_' + field.key, rVal)}</td>
                </tr>`;
            });

            content.innerHTML = `
                <div style="margin-bottom:12px; font-size:13px; color:#374151;">
                    <strong>表單：</strong>${formName}
                    <span style="margin-left:16px; font-size:12px; color:#6b7280;">共 ${fieldPermFormFields.length} 個欄位</span>
                </div>
                <div style="margin-bottom:12px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button onclick="fpBatchSet('approver', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">簽核者全部唯讀</button>
                    <button onclick="fpBatchSet('approver', 'editable')" style="padding:4px 10px; font-size:11px; background:#dbeafe; border:1px solid #93c5fd; border-radius:3px; cursor:pointer;">簽核者全部可修改</button>
                    <button onclick="fpBatchSet('reader', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">閱讀者全部唯讀</button>
                    <button onclick="fpBatchSet('reader', 'hidden')" style="padding:4px 10px; font-size:11px; background:#fee2e2; border:1px solid #fca5a5; border-radius:3px; cursor:pointer;">閱讀者全部隱藏</button>
                </div>
                <div style="border:1px solid #e5e7eb; border-radius:4px; overflow:hidden;">
                    <table style="width:100%; border-collapse:collapse;">
                        <thead>
                            <tr style="background:#f9fafb;">
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">欄位標籤</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">Key</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">類型</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#eff6ff;">簽核者</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#fefce8;">閱讀者</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="margin-top:12px; font-size:11px; color:#6b7280;">
                    <i class="fas fa-info-circle"></i>
                    未設定的欄位預設為「唯讀」。簽核者 = FormAdapter 指定的簽核人，閱讀者 = 其他檢視者。
                </div>
            `;
        }

        /**
         * 批次設定權限
         */
        function fpBatchSet(role, value) {
            const selects = document.querySelectorAll(`select[data-perm^="${role}_"]`);
            selects.forEach(sel => { sel.value = value; });
        }
        window.fpBatchSet = fpBatchSet;

        /**
         * 儲存欄位權限到節點 config
         */
        function saveFieldPermissions() {
            if (!fieldPermCurrentNodeId) return;
            const node = cy.getElementById(fieldPermCurrentNodeId);
            if (!node || node.length === 0) return;

            const approverPerms = {};
            const readerPerms = {};

            fieldPermFormFields.forEach(field => {
                const aSelect = document.querySelector(`select[data-perm="approver_${field.key}"]`);
                const rSelect = document.querySelector(`select[data-perm="reader_${field.key}"]`);
                if (aSelect) approverPerms[field.key] = aSelect.value;
                if (rSelect) readerPerms[field.key] = rSelect.value;
            });

            // 更新 node config
            const currentConfig = node.data('config') || {};
            currentConfig.field_permissions = {
                approver: approverPerms,
                reader: readerPerms,
            };
            node.data('config', currentConfig);

            // 統計
            const editableCount = Object.values(approverPerms).filter(v => v === 'editable').length;
            const hiddenCount = Object.values(approverPerms).filter(v => v === 'hidden').length;
            const readerHiddenCount = Object.values(readerPerms).filter(v => v === 'hidden').length;

            closeFieldPermissionsModal();
            updateStatus(`✅ 欄位權限已儲存 (簽核者: ${editableCount} 可修改, ${hiddenCount} 隱藏 / 閱讀者: ${readerHiddenCount} 隱藏)`, 'success');
        }
        window.saveFieldPermissions = saveFieldPermissions;

