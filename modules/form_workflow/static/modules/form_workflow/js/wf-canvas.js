/**
 * wf-canvas.js -- 動畫控制、縮放、底圖管理、網格設定
 * 從 workflow-main.js 拆分
 */

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
                const response = await fetch(`${window.__BP}/api/workflows/backgrounds`);
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

                const response = await fetch(`${window.__BP}/api/workflows/backgrounds/upload`, {
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
                const response = await fetch(`${window.__BP}/api/workflows/backgrounds/${currentBackgroundId}`, {
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
                const response = await fetch(`${window.__BP}/api/workflows/backgrounds/${currentBackgroundId}`, {
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

