/**
 * wf-workflow-ui.js -- 分類折疊、介面鎖定/解鎖、流程資訊、設計模式
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js
 */


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
            updateStatus(__('已打開所有節點分類'));
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
            updateStatus(__('已關閉所有節點分類'));
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

            // 完整清除唯讀模式殘留樣式（disabled 屬性、class、inline style）
            [saveBtn, saveAndCloseBtn, saveNewVersionBtn, discardBtn].forEach(btn => {
                if (!btn) return;
                btn.removeAttribute('disabled');
                btn.disabled = false;
                btn.classList.remove('disabled');
                btn.style.opacity = '';
                btn.style.cursor = '';
                btn.title = '';
            });
            console.log('  ✓ 顯示操作按鈕並啟用');

            // 顯示流程資訊
            document.getElementById('workflow-info').style.display = 'flex';
            document.getElementById('current-workflow-name').value = workflowName || __('未命名流程');
            document.getElementById('current-workflow-version').textContent = workflowVersion ? `版本 ${workflowVersion}` : 'v1.0';
            const categorySelect = document.getElementById('current-workflow-category');
            if (categorySelect) {
                categorySelect.value = workflowCategory || '';
            }
            const descPreview = (workflowDescription || '').split('\n')[0];
            document.getElementById('current-workflow-description').value = descPreview;
            console.log('  ✓ 更新流程資訊顯示');
        }

        // 更新流程名稱和描述
        async function updateWorkflowInfo() {
            if (!currentWorkflowId) return;

            const nameInput = document.getElementById('current-workflow-name');
            const categoryInput = document.getElementById('current-workflow-category');
            const newName = nameInput.value.trim();
            const newDescription = currentWorkflow?.description || '';
            const newCategorySc = categoryInput ? categoryInput.value : '';

            if (!newName) {
                updateStatus(__('流程名稱不能為空'), 'warning');
                nameInput.value = currentWorkflow?.name || __('未命名流程');
                return;
            }

            // 檢查是否有變更
            if (newName === currentWorkflow?.name &&
                newDescription === (currentWorkflow?.description || '') &&
                newCategorySc === (currentWorkflow?.category_secure_code || '')) {
                return; // 沒有變更
            }

            try {
                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}`, {
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
                updateStatus(__('更新流程資訊失敗'), 'warning');
                nameInput.value = currentWorkflow?.name || __('未命名流程');
                document.getElementById('current-workflow-description').value = (currentWorkflow?.description || '').split('\n')[0];
                if (categoryInput) categoryInput.value = currentWorkflow?.category_secure_code || '';
            }
        }

        // 描述編輯 Modal
        window.openDescriptionModal = openDescriptionModal;
        window.closeDescriptionModal = closeDescriptionModal;
        window.saveDescription = saveDescription;

        function openDescriptionModal() {
            const textarea = document.getElementById('description-modal-textarea');
            textarea.value = currentWorkflow?.description || '';
            document.getElementById('description-modal').style.display = 'flex';
            textarea.focus();
        }

        function closeDescriptionModal() {
            document.getElementById('description-modal').style.display = 'none';
        }

        async function saveDescription() {
            const fullText = document.getElementById('description-modal-textarea').value;
            closeDescriptionModal();
            document.getElementById('current-workflow-description').value = fullText.split('\n')[0];
            if (!currentWorkflowId) return;
            try {
                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ description: fullText })
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                currentWorkflow.description = fullText;
                updateStatus(__('✅ 已更新描述'), 'info');
            } catch (error) {
                console.error('❌ 更新描述失敗:', error);
                updateStatus(__('更新描述失敗'), 'warning');
                document.getElementById('current-workflow-description').value = (currentWorkflow?.description || '').split('\n')[0];
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
                formsCountEl.textContent = __('共 0 張表單');
            }

            const fieldsCountEl = document.getElementById('form-fields-count');
            if (fieldsCountEl) {
                fieldsCountEl.textContent = __('共 0 個欄位');
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
