/**
 * wf-node-group.js -- 替換節點、群組管理、updateStatus、小地圖
 * 從 workflow-main.js 拆分
 */

        // ==================== 替換節點功能 ====================
        let replaceNodeTarget = null;  // 要被替換的節點
        let replaceNodeDefinitions = null;  // 快取節點定義
        let replaceNodeUndoBuffer = null;  // 最後一次替換的舊節點資料（記憶體保留，不在畫布上）

        // 顯示替換節點面板
        async function showReplaceNodePanel() {
            if (!contextMenuTarget) {
                updateStatus(__('⚠️ 請先選取要替換的節點'), 'warning');
                return;
            }

            replaceNodeTarget = contextMenuTarget;
            hideContextMenu();

            // 載入節點定義（若尚未載入）
            if (!replaceNodeDefinitions) {
                try {
                    const response = await fetch(window.__BP + '/api/workflows/data/node-definitions');
                    const result = await response.json();
                    if (!result.success) {
                        throw new Error(result.message || __('載入節點定義失敗'));
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
                'basic': __('基本節點'),
                'form': __('表單處理'),
                'notification': __('通知機制'),
                'flow_control': __('流程控制'),
                'data': __('資料處理'),
                'operation': __('運算操作'),
                'integration': __('系統整合'),
                'system_admin': __('系統級管理員專用')
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
                updateStatus(__('⚠️ 沒有可還原的替換記錄'), 'warning');
                closeReplaceNodeModal();
                return;
            }

            pushUndoState();
            const buf = replaceNodeUndoBuffer;

            // 找到當前佔位的新節點
            const currentNode = cy.getElementById(buf.newNodeId);
            if (!currentNode || currentNode.length === 0) {
                updateStatus(__('⚠️ 找不到替換後的節點，可能已被刪除'), 'warning');
                replaceNodeUndoBuffer = null;
                closeReplaceNodeModal();
                return;
            }

            // 關閉選單
            closeReplaceNodeModal();

            const currentId = currentNode.id();
            const currentLabel = currentNode.data('label') || currentId;

            // 1. 收集當前節點的所有連線資料（含完整樣式）
            const connectedEdges = currentNode.connectedEdges().filter(e => !e.data('parentEdge'));
            const edgeInfoList = [];
            connectedEdges.forEach(edge => {
                const curveStyle = edge.style('curve-style') || 'straight';
                const lineColor = edge.style('line-color') || '#95a5a6';
                const info = {
                    id: edge.id(),
                    sourceId: edge.data('source'),
                    targetId: edge.data('target'),
                    label: edge.data('label') || '',
                    style: {
                        'curve-style': curveStyle,
                        'width': parseFloat(edge.style('width')) || 1,
                        'line-color': lineColor,
                        'line-style': edge.style('line-style') || 'solid',
                        'target-arrow-shape': edge.style('target-arrow-shape') || 'triangle',
                        'target-arrow-color': edge.style('target-arrow-color') || lineColor,
                        'arrow-scale': parseFloat(edge.style('arrow-scale')) || 1
                    }
                };
                if (curveStyle === 'bezier' || curveStyle === 'unbundled-bezier') {
                    const distances = edge.style('control-point-distances');
                    const weights = edge.style('control-point-weights');
                    if (distances) info.style['control-point-distances'] = String(distances).replace(/[\[\]px]/g, '');
                    if (weights) info.style['control-point-weights'] = String(weights).replace(/[\[\]]/g, '');
                } else if (curveStyle === 'taxi') {
                    const taxiDir = edge.style('taxi-direction');
                    const taxiTurn = edge.style('taxi-turn');
                    if (taxiDir) info.style['taxi-direction'] = taxiDir;
                    if (taxiTurn) info.style['taxi-turn'] = parseFloat(taxiTurn);
                }
                if (edge.data('orthogonalEnabled')) {
                    info.orthogonalEnabled = true;
                }
                edgeInfoList.push(info);
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
            const iconUrl = buf.data.iconUrl || resolveNodeIconUrl(buf.icon);
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

            // 4. 重建連線（保留原始樣式）
            edgeInfoList.forEach(info => {
                const newEdge = cy.add({
                    group: 'edges',
                    data: {
                        source: info.sourceId === currentId ? restoredNodeId : info.sourceId,
                        target: info.targetId === currentId ? restoredNodeId : info.targetId,
                        label: info.label,
                        orthogonalEnabled: info.orthogonalEnabled || false
                    }
                });
                if (info.style) {
                    newEdge.style(info.style);
                }
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
                updateStatus(__('⚠️ 替換目標遺失'), 'warning');
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

            // 1. 收集舊節點的所有連線資料（含完整樣式）
            const connectedEdges = oldNode.connectedEdges().filter(e => !e.data('parentEdge'));
            const edgeInfoList = [];
            connectedEdges.forEach(edge => {
                const curveStyle = edge.style('curve-style') || 'straight';
                const lineColor = edge.style('line-color') || '#95a5a6';
                const info = {
                    id: edge.id(),
                    sourceId: edge.data('source'),
                    targetId: edge.data('target'),
                    label: edge.data('label') || '',
                    style: {
                        'curve-style': curveStyle,
                        'width': parseFloat(edge.style('width')) || 1,
                        'line-color': lineColor,
                        'line-style': edge.style('line-style') || 'solid',
                        'target-arrow-shape': edge.style('target-arrow-shape') || 'triangle',
                        'target-arrow-color': edge.style('target-arrow-color') || lineColor,
                        'arrow-scale': parseFloat(edge.style('arrow-scale')) || 1
                    }
                };
                // 保存曲線特定參數
                if (curveStyle === 'bezier' || curveStyle === 'unbundled-bezier') {
                    const distances = edge.style('control-point-distances');
                    const weights = edge.style('control-point-weights');
                    if (distances) {
                        info.style['control-point-distances'] = String(distances).replace(/[\[\]px]/g, '');
                    }
                    if (weights) {
                        info.style['control-point-weights'] = String(weights).replace(/[\[\]]/g, '');
                    }
                } else if (curveStyle === 'taxi') {
                    const taxiDir = edge.style('taxi-direction');
                    const taxiTurn = edge.style('taxi-turn');
                    if (taxiDir) info.style['taxi-direction'] = taxiDir;
                    if (taxiTurn) info.style['taxi-turn'] = parseFloat(taxiTurn);
                }
                // 保存正交折線狀態
                if (edge.data('orthogonalEnabled')) {
                    info.orthogonalEnabled = true;
                }
                edgeInfoList.push(info);
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
                const iconUrl = resolveNodeIconUrl(newIcon);
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

            // 4. 重建所有連線（保留原始樣式）
            edgeInfoList.forEach(info => {
                const newEdge = cy.add({
                    group: 'edges',
                    data: {
                        source: info.sourceId === oldId ? newNodeId : info.sourceId,
                        target: info.targetId === oldId ? newNodeId : info.targetId,
                        label: info.label,
                        orthogonalEnabled: info.orthogonalEnabled || false
                    }
                });
                if (info.style) {
                    newEdge.style(info.style);
                }
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
                updateStatus(__('請先選取至少一個節點（Ctrl+點擊選取多個）'), 'warning');
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
                updateStatus(__('請先選取要加入的節點'), 'warning');
                return;
            }

            if (groups.length === 0) {
                updateStatus(__('請選取一個群組節點'), 'warning');
                return;
            }

            if (groups.length > 1) {
                updateStatus(__('只能選取一個群組'), 'warning');
                return;
            }

            const groupId = groups[0].id();
            const targetGroup = groups[0];

            // 將節點移入群組
            nodes.forEach(node => {
                node.move({ parent: groupId });
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            // 群組恢復非空，還原原始邊框設定
            refreshEmptyGroupStyle(targetGroup);

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
                updateStatus(__('請選取群組內的節點'), 'warning');
                return;
            }

            // 記錄受影響的群組（移動前）
            const affectedGroupIds = new Set();
            selectedNodes.forEach(node => {
                const parent = node.parent();
                if (parent.length > 0) affectedGroupIds.add(parent.id());
            });

            selectedNodes.forEach(node => {
                node.move({ parent: null });
            });

            // 清除選取狀態
            cy.nodes().unselect();

            // 強制重新渲染以避免視覺錯誤
            cy.style().update();

            // 檢查受影響群組是否變空
            affectedGroupIds.forEach(groupId => {
                refreshEmptyGroupStyle(cy.getElementById(groupId));
            });

            updateStatus(`已從群組移出 ${selectedNodes.length} 個節點`);
            updateMinimap();
        }

        // 解散群組
        function dissolveGroup() {
            pushUndoState();
            const selectedGroups = cy.nodes(':selected').filter(node => isGroupNode(node));

            if (selectedGroups.length === 0) {
                updateStatus(__('請選取要解散的群組節點'), 'warning');
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
                currentEditingGroupId = null;
                panel.innerHTML = '<div style="color: #999; font-style: italic; padding: 8px 0;">選取群組後可在此調整設定</div>';
                return;
            }

            if (selectedGroups.length > 1) {
                currentEditingGroupId = null;
                panel.innerHTML = `<div style="color: #666; padding: 8px 0;">已選擇 ${selectedGroups.length} 個群組</div>`;
                return;
            }

            const group = selectedGroups[0];
            currentEditingGroupId = group.id();
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
                            onblur="updateGroupNameFromPanel(true)"
                            oninput="updateGroupNameFromPanel(false)"
                            onkeydown="if(event.key==='Enter') this.blur()"
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

        // 從面板更新群組名稱（commitUndo: blur 時才 push undo，oninput 時只同步資料）
        function updateGroupNameFromPanel(commitUndo) {
            const input = document.getElementById('group-name-input');
            if (!input) return;
            // 使用儲存的群組 ID 而非查詢選取狀態（避免 blur 時群組已被取消選取的競態條件）
            if (!currentEditingGroupId) return;
            const group = cy.getElementById(currentEditingGroupId);
            if (!group || group.length === 0) return;
            const newLabel = input.value.trim();
            if (newLabel !== group.data('label')) {
                if (commitUndo) pushUndoState();
                group.data('label', newLabel);
                // 同步右側節點設定面板的名稱輸入框（避免 autoApplyCurrentPanel 用舊值覆蓋）
                const nodeLabelInput = document.getElementById('node-label-input');
                if (nodeLabelInput && currentEditingNodeId === currentEditingGroupId) {
                    nodeLabelInput.value = newLabel;
                }
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

