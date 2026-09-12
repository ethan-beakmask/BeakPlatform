/**
 * wf-render.js -- 載入流程、渲染流程圖、節點類型標準化
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js, wf-workflow-ui.js, wf-relay.js
 */


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
                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}`);

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
                                btn.title = __('您沒有編輯權限');
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
                } else if (cy.nodes().length > 0 && !allNodesInViewport()) {
                    // 有節點沒落在視野內 -> 使用者會看到殘缺甚至整片空白的畫布，
                    // 以為流程壞掉或沒存到（2026-08-20 實際回報）。
                    //
                    // 為什麼不能靠「把座標排在安全範圍內」解決：載入時的 pan
                    // **不是固定值**，實測連續重新載入同一個流程會得到
                    // -143.75 / -193.75 / -275，所以沒有任何一組座標保證看得到。
                    // 唯一可靠的做法是載入後確認視野，不對就 fit。
                    console.warn('⚠️ 有節點落在視野外，自動 fit');
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
                            btn.title = __('通用子流程唯讀，請從流程管理頁面開啟編輯');
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
                    const nodeSettingsRO = document.getElementById('nodeSettings');
                    if (nodeSettingsRO) {
                        nodeSettingsRO.style.pointerEvents = 'none';
                        nodeSettingsRO.style.opacity = '0.55';
                    }
                    // 顯示唯讀提示
                    if (!document.getElementById('readonly-warning')) {
                        const toolbar = document.querySelector('.toolbar-row');
                        if (toolbar) {
                            const warning = document.createElement('div');
                            warning.id = 'readonly-warning';
                            warning.style.cssText = 'background: #e8f4fd; border: 1px solid #90caf9; color: #1565c0; padding: 6px 16px; margin-bottom: 8px; border-radius: 4px; font-size: 12px; display: flex; align-items: center; gap: 8px;';
                            warning.innerHTML = '<i class="fas fa-eye"></i><strong>唯讀模式</strong> — 通用子流程僅供檢視。如需編輯，請從<a href=window.__BP + "/forms/workflows" style="color: #1565c0; margin-left: 2px;">流程管理</a>頁面開啟。';
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
                updateStatus(__('載入流程失敗'));
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
                    icon: window.__BP + '/static/modules/form_workflow/icons/workflow/start.svg',
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
                    icon: window.__BP + '/static/modules/form_workflow/icons/workflow/end.svg',
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
                        parent: node.parent || __('(無)')
                    });

                    // 取得圖示 URL（唯一實作見 wf-dnd-nodes.js::resolveNodeIconUrl）
                    const iconUrl = node.iconUrl || resolveNodeIconUrl(node.icon);

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

        // 所有節點是否都完整落在目前視野內（含節點自身的寬高）
        function allNodesInViewport() {
            const ext = cy.extent();
            return cy.nodes().every(function (n) {
                const bb = n.boundingBox();
                return bb.x1 >= ext.x1 && bb.x2 <= ext.x2
                    && bb.y1 >= ext.y1 && bb.y2 <= ext.y2;
            });
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
                'sysemailrelay': 'SysEmailRelay',
                'syssqlexecutor': 'SysSqlExecutor',
                'sqlexecutor': 'SysSqlExecutor',   // 舊名殘留仍導向新型別
                'osexecutor': 'OsExecutor',
                'os_executor': 'OsExecutor',
                'fileread': 'OsFileRead',
                'file_read': 'OsFileRead',
                'sys_telegram': 'SysTelegram',
                'systelegram': 'SysTelegram',
                'navbarbroadcast': 'NavbarBroadcast',
                'navbar_broadcast': 'NavbarBroadcast',
                'alertbroadcast': 'AlertBroadcast',
                'alert_broadcast': 'AlertBroadcast',
                'subsystemprovision': 'SubSystemProvision',
                'sub_system_provision': 'SubSystemProvision',
                'apikeyaction': 'ApiKeyAction',
                'api_key_action': 'ApiKeyAction',
            };
            return typeMap[type.toLowerCase()] || type;
        }
