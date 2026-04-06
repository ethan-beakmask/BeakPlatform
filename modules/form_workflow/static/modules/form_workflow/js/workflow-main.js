/**
 * workflow-main.js -- Workflow Designer 主檔 (全域變數 + 群組 Helper)
 *
 * 子模組載入順序 (HTML 中須先於其他 wf-*.js 載入此檔):
 *   wf-undo.js, wf-core.js, wf-accordion.js, wf-node-configs.js,
 *   wf-form-adapter.js, wf-save.js, wf-canvas.js, wf-polyline.js,
 *   wf-edge-props.js, wf-ui-controls.js, wf-node-group.js,
 *   wf-tree.js, wf-variables.js, wf-init.js (必須最後)
 */

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
        let currentEditingGroupId = null;  // 群組設定面板正在編輯的群組 ID
        let isReadOnly = false;            // 唯讀模式（通用子流程從外部開啟時啟用）

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

        // 檢查並更新空群組外觀（空群組強制虛線邊框 + 保持顏色可見）
        function refreshEmptyGroupStyle(group) {
            if (!group || group.removed() || group.length === 0) return;
            if (group.data('type') !== 'group' && !group.isParent()) return;

            const children = group.children();
            const isEmpty = children.length === 0;

            if (isEmpty) {
                const gc = group.data('groupColor');
                const borderColor = gc ? groupBorderColor(gc.r, gc.g, gc.b) : '#667eea';
                const styleObj = {
                    'border-width': 2,
                    'border-style': 'dashed',
                    'background-opacity': 0.15,
                    'border-color': borderColor
                };
                // 無明確顏色時套用預設可見背景
                if (!gc) {
                    styleObj['background-color'] = 'rgba(102, 126, 234, 0.08)';
                }
                group.style(styleObj);
            } else {
                // 有子節點：依 data 中儲存的 borderStyle 還原
                const borderStyle = group.data('borderStyle') || 'none';
                const gc = group.data('groupColor');
                if (borderStyle === 'none') {
                    group.style({
                        'border-width': 0,
                        'background-opacity': 0.3
                    });
                } else {
                    const borderColor = gc ? groupBorderColor(gc.r, gc.g, gc.b) : '#667eea';
                    group.style({
                        'border-width': 2,
                        'border-style': borderStyle,
                        'background-opacity': 0.15,
                        'border-color': borderColor
                    });
                }
            }
        }

        // 掃描所有群組並更新空群組樣式
        function refreshAllEmptyGroups() {
            cy.nodes().forEach(node => {
                if (node.data('type') === 'group' || node.isParent()) {
                    refreshEmptyGroupStyle(node);
                }
            });
        }
