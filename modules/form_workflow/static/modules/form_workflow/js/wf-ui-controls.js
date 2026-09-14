/**
 * wf-ui-controls.js -- 座標控制面板、格線背景繪製、Tab 切換、右鍵選單
 * 從 workflow-main.js 拆分
 */

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
                updateStatus(__('錯誤：找不到直角折線控制點'));
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
                updateStatus(__('錯誤：找不到來源或目標節點'));
                return;
            }

            const sourcePos = source.position();
            const targetPos = target.position();

            // 判斷中間段方向
            const isHorizontal = Math.abs(sourcePos.x - targetPos.x) > Math.abs(sourcePos.y - targetPos.y);

            if (isHorizontal) {
                // 水平線 - 調整 Y 座標
                document.getElementById('taxi-segment-type').textContent = __('水平線');
                document.getElementById('taxi-current-coord').textContent = `Y = ${pos.y.toFixed(1)}`;
                document.getElementById('taxi-coord-input').value = Math.round(pos.y);
            } else {
                // 垂直線 - 調整 X 座標
                document.getElementById('taxi-segment-type').textContent = __('垂直線');
                document.getElementById('taxi-current-coord').textContent = `X = ${pos.x.toFixed(1)}`;
                document.getElementById('taxi-coord-input').value = Math.round(pos.x);
            }

            updateStatus(`調整直角折線: ${edge.id()}`);
        }

        // 調整直角折線座標（相對調整）
        function adjustTaxiCoord(delta) {
            if (!currentTaxiEdge) {
                updateStatus(__('請先選擇一條直角折線'), 'warning');
                return;
            }

            const controls = taxiControlPoints.get(currentTaxiEdge.id());
            if (!controls || controls.length === 0) {
                updateStatus(__('錯誤：找不到控制點'), 'warning');
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
                updateStatus(__('請先選擇一條直角折線'), 'warning');
                return;
            }

            const newValue = parseFloat(document.getElementById('taxi-coord-input').value);
            if (isNaN(newValue)) {
                updateStatus(__('請輸入有效的數字'), 'warning');
                return;
            }

            const controls = taxiControlPoints.get(currentTaxiEdge.id());
            if (!controls || controls.length === 0) {
                updateStatus(__('錯誤：找不到控制點'), 'warning');
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
            updateStatus(__('已關閉座標控制面板'));
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
                // 切換到變數總覽分頁時自動載入
                reloadAllVars();
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
            updateStatus(`網格樣式: ${style === 'off' ? __('關閉') : style === 'lines' ? __('線條') : __('點陣')}`);
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
                updateStatus(__('網格樣式: 線條'));
            } else if (dotsCheckbox.checked) {
                gridEnabled = true;
                gridStyle = 'dots';
                updateStatus(__('網格樣式: 點陣'));
            } else {
                gridEnabled = false;
                updateStatus(__('網格樣式: 關閉'));
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
                const oldParent = contextMenuTarget.parent();
                contextMenuTarget.move({ parent: null });
                cy.style().update();
                if (oldParent.length > 0) refreshEmptyGroupStyle(oldParent);
                updateStatus(__('節點已移出群組'));
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
                    updateStatus(__('⚠️ Start 節點不允許刪除'), 'warning');
                    hideContextMenu();
                    return;
                }
                // 檢查是否為 Subflow 節點
                const isSubflow = nodeType === 'Subflow';
                contextMenuTarget.remove();
                updateStatus(__('節點已刪除'));
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
                const newLabel = prompt(__('輸入群組名稱:'), currentLabel);
                if (newLabel !== null && newLabel.trim() !== '') {
                    contextMenuTarget.data('label', newLabel.trim());
                    updateGroupSettingsPanel();
                    updateStatus(__('群組名稱已更新'));
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

                updateStatus(`群組框線已設為: ${style === 'solid' ? __('實線') : style === 'dashed' ? __('虛線') : __('無框線')}`);
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

                updateStatus(`群組形狀已設為: ${style === 'round' ? __('圓角') : __('直角')}`);
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
                updateStatus(__('群組顏色已重設'));
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
                updateStatus(__('群組已解散'));
                updateMinimap();
            }
            hideContextMenu();
        }

