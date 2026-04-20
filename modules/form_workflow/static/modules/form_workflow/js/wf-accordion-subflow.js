/**
 * wf-accordion-subflow.js -- 子流程節點面板與管理函式
 * 從 wf-accordion.js 拆分
 * 包含: renderSubflowPanel, subflow CRUD, 參數映射, applySubprocessConfig
 */

        // ==================== Subflow 面板 HTML ====================

        function renderSubflowPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const currentChildFlowId = currentConfig.childFlowId || '';

            return `
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
                    <div id="currentSubflowDisplay" style="margin-bottom: 12px; padding: 8px 12px; background: #f0f4ff; border-radius: 4px; font-size: 13px;">
                        目前：<strong>${currentChildFlowId ? '載入中...' : '未選擇'}</strong>
                    </div>
                    <input type="hidden" id="childFlowSelect" value="${currentChildFlowId}">
                    <div style="margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <strong style="font-size: 13px;">專屬子流程</strong>
                            <button class="btn-secondary" onclick="createNewSubflow('${nodeId}')" style="padding: 2px 10px; font-size: 12px;">
                                <i class="fas fa-plus"></i> 新增
                            </button>
                        </div>
                        <div id="dedicatedSubflowList" style="border: 1px solid #e0e0e0; border-radius: 4px; max-height: 180px; overflow-y: auto;">
                            <div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">載入中...</div>
                        </div>
                    </div>
                    <div>
                        <strong style="font-size: 13px; display: block; margin-bottom: 6px;">通用子流程</strong>
                        <div id="commonSubflowList" style="border: 1px solid #e0e0e0; border-radius: 4px; max-height: 220px; overflow-y: auto;">
                            <div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">載入中...</div>
                        </div>
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

        // ==================== Subflow 管理函式 ====================

        // 載入可用子流程清單（分區面板）
        async function loadAvailableSubflows(nodeId) {
            try {
                const parentId = currentWorkflowId;
                if (!parentId) {
                    console.error('無法取得當前工作流程 ID');
                    updateStatus('無法載入子流程清單：找不到父流程 ID', 'warning');
                    return;
                }

                const response = await fetch(`${window.__BP}/api/workflows/data/subflows/available?parent_id=${parentId}`);
                const result = await response.json();

                const dedicatedList = document.getElementById('dedicatedSubflowList');
                const commonList = document.getElementById('commonSubflowList');
                const hiddenInput = document.getElementById('childFlowSelect');
                if (!dedicatedList || !commonList) return;

                // 取得當前選中的子流程
                const node = cy.getElementById(nodeId);
                const currentConfig = node.data('config') || {};
                const currentChildFlowId = currentConfig.childFlowId || '';

                if (!result.success || !result.data) {
                    dedicatedList.innerHTML = '<div style="padding: 10px; color: #c33; font-size: 12px;">載入失敗</div>';
                    commonList.innerHTML = '<div style="padding: 10px; color: #c33; font-size: 12px;">載入失敗</div>';
                    return;
                }

                const { dedicated, common_categories } = result.data;

                // 渲染專屬子流程列表
                if (dedicated.length === 0) {
                    dedicatedList.innerHTML = '<div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">尚無專屬子流程</div>';
                } else {
                    let html = '';
                    dedicated.forEach(sf => {
                        const isSelected = sf.code === currentChildFlowId;
                        const bgColor = isSelected ? '#e8f0fe' : 'transparent';
                        const borderLeft = isSelected ? '3px solid #667eea' : '3px solid transparent';
                        html += `<div style="display: flex; align-items: center; padding: 7px 10px; border-bottom: 1px solid #f0f0f0; background: ${bgColor}; border-left: ${borderLeft}; cursor: pointer;" onmouseover="this.style.background='${isSelected ? '#e8f0fe' : '#f8f9fa'}'" onmouseout="this.style.background='${bgColor}'" onclick="selectSubflow('${nodeId}', '${sf.code}', '${sf.name.replace(/'/g, "\\'")}', true)">
                            <span style="flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${sf.name}</span>`;
                        if (sf.is_referenced) {
                            html += `<span style="font-size: 11px; color: #667eea; margin-left: 8px; white-space: nowrap;">使用中</span>`;
                        } else {
                            html += `<button onclick="event.stopPropagation(); deleteSubflow('${sf.secure_code}', '${sf.name.replace(/'/g, "\\'")}', '${nodeId}')" style="background: none; border: none; color: #c33; cursor: pointer; padding: 2px 6px; font-size: 13px; margin-left: 8px;" title="刪除此子流程"><i class="fas fa-trash-alt"></i></button>`;
                        }
                        html += '</div>';
                    });
                    dedicatedList.innerHTML = html;
                }

                // 渲染通用子流程列表（按分類分組）
                if (common_categories.length === 0) {
                    commonList.innerHTML = '<div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">尚無通用子流程</div>';
                } else {
                    let html = '';
                    common_categories.forEach(cat => {
                        const catId = 'cat_' + cat.category_name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_');
                        html += `<div>
                            <div onclick="const body=document.getElementById('${catId}'); const arrow=this.querySelector('.cat-arrow'); if(body.style.display==='none'){body.style.display='block';arrow.textContent='▾';}else{body.style.display='none';arrow.textContent='▸';}" style="padding: 7px 10px; background: #f5f5f5; cursor: pointer; font-size: 13px; font-weight: 600; border-bottom: 1px solid #e0e0e0; user-select: none;">
                                <span class="cat-arrow">▾</span> ${cat.category_name}
                                <span style="font-size: 11px; color: #999; font-weight: normal; margin-left: 4px;">(${cat.subflows.length})</span>
                            </div>
                            <div id="${catId}">`;
                        cat.subflows.forEach(sf => {
                            const isSelected = sf.code === currentChildFlowId;
                            const bgColor = isSelected ? '#e8f0fe' : 'transparent';
                            const borderLeft = isSelected ? '3px solid #667eea' : '3px solid transparent';
                            html += `<div style="display: flex; align-items: center; padding: 6px 10px 6px 24px; border-bottom: 1px solid #f0f0f0; background: ${bgColor}; border-left: ${borderLeft}; cursor: pointer;" onmouseover="this.style.background='${isSelected ? '#e8f0fe' : '#f8f9fa'}'" onmouseout="this.style.background='${bgColor}'" onclick="selectSubflow('${nodeId}', '${sf.code}', '${sf.name.replace(/'/g, "\\'")}', false)">
                                <span style="flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${sf.name}</span>
                            </div>`;
                        });
                        html += '</div></div>';
                    });
                    commonList.innerHTML = html;
                }

                // 更新「目前」顯示
                _updateCurrentSubflowDisplay(currentChildFlowId, dedicated, common_categories);

                // 自動補齊舊資料的 subflowKind（載入時節點已有 childFlowId 但沒有 subflowKind）
                if (currentChildFlowId && node.length > 0 && !node.data('subflowKind')) {
                    const isDed = dedicated.some(sf => sf.code === currentChildFlowId);
                    const kind = isDed ? 'dedicated' : 'common';
                    node.data('subflowKind', kind);
                    const cfg = node.data('config') || {};
                    cfg.subflowKind = kind;
                    node.data('config', cfg);
                }

                // 載入參數映射配置
                loadParamMapping(nodeId);

                console.log(`已載入子流程面板：${dedicated.length} 個專屬, ${common_categories.length} 個分類`);

            } catch (error) {
                console.error('載入子流程清單失敗:', error);
                updateStatus('無法載入子流程清單：' + error.message, 'warning');
            }
        }

        // 更新「目前」顯示文字
        function _updateCurrentSubflowDisplay(currentCode, dedicated, common_categories) {
            const display = document.getElementById('currentSubflowDisplay');
            if (!display) return;
            if (!currentCode) {
                display.innerHTML = '目前：<strong style="color: #999;">未選擇</strong>';
                return;
            }
            // 在專屬和通用中查找名稱
            let name = currentCode;
            for (const sf of dedicated) {
                if (sf.code === currentCode) { name = sf.name; break; }
            }
            if (name === currentCode) {
                for (const cat of common_categories) {
                    for (const sf of cat.subflows) {
                        if (sf.code === currentCode) { name = sf.name; break; }
                    }
                    if (name !== currentCode) break;
                }
            }
            display.innerHTML = `目前：<strong>${name}</strong>`;
        }

        // 選擇子流程
        function selectSubflow(nodeId, code, name, isDedicated) {
            const hiddenInput = document.getElementById('childFlowSelect');
            if (hiddenInput) hiddenInput.value = code;

            // 更新「目前」顯示
            const display = document.getElementById('currentSubflowDisplay');
            if (display) display.innerHTML = `目前：<strong>${name}</strong>`;

            // 設定 subflowKind 供節點變色
            const kind = isDedicated ? 'dedicated' : 'common';
            const node = cy.getElementById(nodeId);
            if (node && node.length > 0) {
                node.data('subflowKind', kind);
                const config = node.data('config') || {};
                config.subflowKind = kind;
                node.data('config', config);
            }

            // 套用配置
            applySubprocessConfig(nodeId);

            // 重新載入列表以更新高亮
            setTimeout(() => loadAvailableSubflows(nodeId), 600);
        }

        // 刪除專屬子流程
        async function deleteSubflow(secureCode, name, nodeId) {
            if (!confirm(`確定要刪除子流程「${name}」嗎？\n此操作無法復原。`)) return;

            try {
                const response = await fetch(`${window.__BP}/api/workflows/data/subflows/${secureCode}`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' }
                });
                const result = await response.json();
                if (result.success) {
                    updateStatus(`已刪除子流程「${name}」`, 'success');
                    await loadAvailableSubflows(nodeId);
                } else {
                    updateStatus('刪除失敗：' + (result.error || '未知錯誤'), 'warning');
                }
            } catch (error) {
                console.error('刪除子流程失敗:', error);
                updateStatus('刪除子流程失敗：' + error.message, 'warning');
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
                const response = await fetch(`${window.__BP}/api/workflows/data/subflows/create`, {
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

                    // 重新載入子流程清單並自動選擇新建立的子流程
                    await loadAvailableSubflows(nodeId);
                    selectSubflow(nodeId, result.data.code, result.data.name, true);
                } else {
                    updateStatus('建立子流程失敗：' + (result.message || '未知錯誤'), 'warning');
                }
            } catch (error) {
                console.error('建立子流程失敗:', error);
                updateStatus('無法建立子流程：' + error.message, 'warning');
            }
        }

        // ==================== 參數映射 ====================

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
            updateStatus(`已添加輸入映射：${parentVar} → ${childVar}`, 'success');
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
            updateStatus(`已添加輸出映射：${childVar} → ${parentVar}`, 'success');
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
                updateStatus(`已刪除輸入映射：${parentVar}`, 'success');
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
                updateStatus(`已刪除輸出映射：${childVar}`, 'success');
            }
        }

        // ==================== 套用子流程配置 ====================

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

            // 取得選中的子流程名稱（從目前顯示區取）
            const displayEl = document.getElementById('currentSubflowDisplay');
            const strongEl = displayEl ? displayEl.querySelector('strong') : null;
            const childFlowName = (strongEl && strongEl.textContent !== '未選擇') ? strongEl.textContent : childFlowId;

            // 取得現有的 config，更新 childFlowId
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                childFlowId: childFlowId
            };

            // 儲存設定到節點的 config
            node.data('config', updatedConfig);

            updateStatus(`子流程設定已套用：${childFlowName}`, 'success');

            console.log('子流程節點配置已更新:', {
                nodeId: nodeId,
                childFlowId: childFlowId,
                config: updatedConfig
            });

            // 自動儲存當前流程
            saveWorkflow().then(() => {
                console.log('流程已自動儲存');
                // 延遲 0.5 秒後重新整理流程樹系
                setTimeout(() => {
                    refreshFlowTree();
                }, 500);
            }).catch(err => {
                console.error('自動儲存失敗:', err);
            });
        }
