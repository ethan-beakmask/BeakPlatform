/**
 * wf-tree.js -- 流程樹功能 (父子流程導航)
 * 從 workflow-main.js 拆分
 */

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
                updateFlowTreeRootLabel();
            }
        }

        /**
         * 更新流程樹系標題旁的根流程名稱（已移除顯示元素，保留空函數避免呼叫錯誤）
         */
        function updateFlowTreeRootLabel() {}

        /**
         * 離開目前流程前的自動儲存
         * 規格：無提示、無條件儲存後才離開；存檔失敗時停在原地（避免靜默丟資料）
         * @returns {Promise<boolean>} true 代表可以離開
         */
        async function autoSaveBeforeLeave() {
            if (typeof isReadOnly !== 'undefined' && isReadOnly) return true;   // 唯讀本來就沒東西可存
            if (!currentWorkflowId) return true;

            // 先把當前節點面板的設定套進畫布，否則「剛改完面板就切換」會被判定成無變更
            if (typeof autoApplyCurrentPanel === 'function') {
                try {
                    autoApplyCurrentPanel();
                } catch (e) {
                    console.warn('套用面板設定失敗:', e);
                }
            }

            const dirty = (typeof checkForChanges === 'function') ? checkForChanges() : true;
            if (!dirty) return true;

            const saved = await saveWorkflow();
            if (saved !== true) {
                updateStatus(__('儲存失敗，已留在目前流程'), 'warning');
                return false;
            }
            return true;
        }

        /**
         * 開啟樹系圖頁面
         */
        async function openFlowTreePage() {
            const code = rootWorkflowId || currentWorkflowId;
            if (!code) return;

            // 整頁跳轉前先存檔，回來時才不會少一段
            if (!(await autoSaveBeforeLeave())) return;

            const params = new URLSearchParams({ from: 'designer' });
            if (currentWorkflowId) params.set('sc', currentWorkflowId);
            window.location.href = window.__BP + '/forms/workflows/' + code + '/tree?' + params.toString();
        }

        /**
         * 向上追溯到最頂端主流程
         */
        async function resolveTopRoot(secureCode) {
            const visited = new Set();
            let current = secureCode;
            let name = '';
            for (let i = 0; i < 10; i++) {
                if (visited.has(current)) break;
                visited.add(current);
                try {
                    const res = await fetch(`${window.__BP}/api/workflows/data/templates/${current}`);
                    const data = await res.json();
                    const wf = data.data || data;
                    name = wf.name;
                    if (wf.parent_workflow_secure_code) {
                        current = wf.parent_workflow_secure_code;
                    } else {
                        break;
                    }
                } catch (e) {
                    break;
                }
            }
            return { secureCode: current, name: name };
        }

        /**
         * 刷新流程樹（重新載入資料）
         * @param {boolean} forceReload - 是否強制重新載入（忽略快取）
         */
        async function refreshFlowTree(forceReload = false) {
            const container = document.getElementById('flow-tree-list');
            if (!container) return;

            // 如果沒有根主流程，追溯到最頂端
            if (!rootWorkflowId && currentWorkflowId) {
                try {
                    const top = await resolveTopRoot(currentWorkflowId);
                    setRootWorkflow(top.secureCode, top.name);
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
                    const response = await fetch(`${window.__BP}/api/workflows/data/templates/${wfId}`);
                    const result = await response.json();
                    const workflowData = result.data || result;

                    const node = {
                        id: workflowData.secure_code,
                        name: workflowData.name,
                        code: workflowData.code,
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
                    const subflowsResponse = await fetch(`${window.__BP}/api/workflows/data/subflows/available?parent_id=${wfId}`);
                    const subflowsResult = await subflowsResponse.json();
                    // API 回傳 { dedicated: [...], common_categories: [{category_name, subflows: [...]}] }
                    let availableSubflows = [];
                    if (subflowsResult.success && subflowsResult.data) {
                        const d = subflowsResult.data;
                        availableSubflows = (d.dedicated || []).concat(
                            (d.common_categories || []).flatMap(cat => cat.subflows || [])
                        );
                    }

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
                                    code: sfFromApi.code,
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
                                const sfResponse = await fetch(`${window.__BP}/api/workflows/data/templates/by-code/${code}`);
                                if (sfResponse.ok) {
                                    const sfResult = await sfResponse.json();
                                    const sfData = sfResult.data || sfResult;
                                    if (sfData && sfData.secure_code) {
                                        if (depth >= MAX_DEPTH) {
                                            node.children.push({
                                                id: sfData.secure_code,
                                                name: sfData.name,
                                                code: sfData.code,
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

            // 同名的流程在樹上分不出是哪一個，這種情況才把 code 一起顯示
            // （以 secureCode 去重，同一個流程被引用兩次不算同名）
            const nameCounts = {};
            const countedCodes = new Set();
            (function countNames(node) {
                if (!node) return;
                const key = node.secureCode || node.id;
                if (key && !countedCodes.has(key)) {
                    countedCodes.add(key);
                    nameCounts[node.name] = (nameCounts[node.name] || 0) + 1;
                }
                (node.children || []).forEach(countNames);
            })(treeData);
            const displayName = (node) =>
                (nameCounts[node.name] > 1 && node.code) ? `${node.name}（${node.code}）` : node.name;

            // 生成 HTML
            let html = '';

            // 先渲染主流程（根節點）
            const rootColor = depthColors[0];
            const rootCurrentClass = treeData.isCurrent ? 'current' : '';
            const rootClickHandler = `onclick="switchToWorkflow('${treeData.secureCode}')"`;
            html += `<div class="flow-tree-item ${rootCurrentClass}" style="padding-left: 6px;" ${rootClickHandler} title="${displayName(treeData)}">
                <span class="dot" style="background: ${rootColor};"></span>
                <span class="name">${displayName(treeData)}</span>
            </div>`;

            // 渲染子流程
            function addItem(node, depth) {
                const color = depthColors[(depth + 1) % depthColors.length];
                const indent = (depth + 1) * 12;
                const currentClass = node.isCurrent ? 'current' : '';
                const secureCode = node.secureCode || '';
                const clickHandler = secureCode ? `onclick="switchToWorkflow('${secureCode}')"` : '';

                html += `<div class="flow-tree-item ${currentClass}" style="padding-left: ${6 + indent}px;" ${clickHandler} title="${displayName(node)}">
                    <span class="dot" style="background: ${color};"></span>
                    <span class="name">${displayName(node)}</span>
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

            // 切換前無提示自動儲存；存檔失敗就停在原地，不帶著未存的變更跳走
            if (!(await autoSaveBeforeLeave())) return;

            updateStatus(`正在切換到流程...`);

            // 更新 URL 並載入新流程（移除 editable，讓通用子流程的唯讀檢查能生效）
            const newUrl = new URL(window.location.href);
            newUrl.pathname = window.__BP + '/forms/workflows/' + secureCode;
            newUrl.searchParams.delete('id');
            newUrl.searchParams.delete('new');
            newUrl.searchParams.delete('editable');
            window.__DESIGNER_ID = secureCode;
            window.history.pushState(null, '', newUrl);

            // 重置節點設定面板
            currentEditingNodeId = null;
            const nodeSettingsEl = document.getElementById('nodeSettings');
            if (nodeSettingsEl) {
                nodeSettingsEl.innerHTML = '';
                nodeSettingsEl.style.display = 'none';
            }

            // 重置表單欄位分頁狀態
            resetFormFieldsTab();

            // 載入新流程
            currentWorkflowId = secureCode;
            await loadWorkflow();

            // 刷新流程樹
            refreshFlowTree();

            updateStatus(`✅ 已切換到流程`);
        }

