/**
 * wf-workflow-crud.js -- 儲存/關閉、版本管理、流程 CRUD、變更追蹤
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js, wf-workflow-ui.js
 */


        // 儲存並關閉
        async function saveAndClose() {
            console.log('💾 儲存並關閉');

            // 先儲存
            if (!currentWorkflowId) {
                updateStatus(__('請先選擇或建立一個流程'), 'warning');
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
                window.location.href = window.__BP + '/forms/workflows/' + rootCode + '/tree';
            } else {
                window.location.href = window.__BP + '/forms/workflows';
            }

            console.log('✅ 已儲存並返回');
        }

        // 儲存新版本
        async function saveNewVersion(targetNode = null) {
            console.log('💾 儲存新版本', targetNode ? '(已指定目標節點)' : '');

            if (!currentWorkflowId) {
                updateStatus(__('請先選擇或建立一個流程'), 'warning');
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

                updateStatus(__('正在儲存新版本...'), 'info');

                const requestBody = {
                    name: document.getElementById('current-workflow-name')?.value,
                    description: currentWorkflow?.description || ''
                };

                // 如果有指定目標節點
                if (targetNode) {
                    requestBody.target_node = targetNode;
                }

                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}/save-new-version`, {
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
                updateStatus(__('已取��另存新版'), 'info');
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
                saveBtn.title = __('有未儲存的變更');
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
                if (!confirm(__('您有未儲存的變更，確定要放棄並離開嗎？'))) {
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
                    const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}`, {
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
            window.location.href = window.__BP + '/forms/workflows';

            console.log('✅ 已放棄變更並返回流程目錄');
        }

        // 載入分類列表（二層結構）
        async function loadCategories() {
            try {
                const response = await fetch(window.__BP + '/api/forms/data/categories');
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
                console.error('❌ 載���分類失敗:', error);
            }
        }

        // 載入流程列表
        async function loadWorkflowList() {
            try {
                const response = await fetch(window.__BP + '/api/workflows/data/templates');
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
                            const createdDate = w.created_at ? BkTime.format(w.created_at, 'date') : __('未知');

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
                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${workflowId}`, {
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
                    updateStatus(__('流程已刪除'));
                } else {
                    updateStatus(__('刪除流程失敗'), 'warning');
                }
            } catch (error) {
                console.error('刪除流程失敗:', error);
                updateStatus(__('刪除流程失敗'), 'warning');
            }
        }

        // 建立新流程
        async function createNewWorkflow() {
            const name = prompt(__('請輸入流程名稱：'), '新流程');
            if (!name) return;

            try {
                console.log('🆕 開始建立新流程:', name);

                const response = await fetch(window.__BP + '/api/workflows/data/templates', {
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
                updateStatus(__('建立流程失敗：') + error.message, 'warning');
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

                const response = await fetch(window.__BP + '/api/workflows/data/templates', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: name || __('新流程'),
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
                newUrl.pathname = window.__BP + '/forms/workflows/' + workflowData.secure_code;
                newUrl.searchParams.delete('new');
                newUrl.searchParams.delete('name');
                newUrl.searchParams.delete('category');
                newUrl.searchParams.delete('description');
                newUrl.searchParams.delete('id');
                window.__DESIGNER_ID = workflowData.secure_code;
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
                updateStatus(__('建立流程失敗：') + error.message, 'warning');
                // 失敗時重定向回列表頁
                window.location.href = window.__BP + '/forms/workflows';
            } finally {
                isCreatingWorkflow = false;
            }
        }
