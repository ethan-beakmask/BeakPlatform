/**
 * wf-node-form-adapter.js -- Assignee/FormAdapter 簽核節點配置
 * 從 wf-node-configs.js 拆分
 */

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
                const response = await fetch(window.__BP + '/api/workflows/data/org-tree');
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
                const response = await fetch(window.__BP + '/api/workflows/data/roles');
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
                const msg = document.getElementById('faModalMessage');
                if (msg) { msg.textContent = __('請選擇或填寫簽核者'); msg.className = 'fa-modal-message warning'; }
                else { updateStatus(__('請選擇或填寫簽核者'), 'warning'); }
                return;
            }

            // 自定義決策選項相關
            const useCustomDecisions = document.getElementById('faUseCustomDecisions')?.checked || false;
            const outputVariable = document.getElementById('faOutputVariable')?.value?.trim() || '';

            // 收集決策選項和來向變數（從 DOM）
            let decisionOptions = [];
            let inputVariables = [];
            if (useCustomDecisions && window._faDecisions) {
                decisionOptions = window._faDecisions.collectDecisionOptions();
                inputVariables = window._faDecisions.collectInputVariables();
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
                min_comment_length: minCommentLength,
                use_custom_decisions: useCustomDecisions,
                output_variable: outputVariable,
                decision_options: decisionOptions,
                input_variables: inputVariables
            };

            node.data('config', updatedConfig);

            const typeLabels = {
                'INITIATOR': __('發起人'),
                'USER': __('指定用戶'),
                'ROLE': __('指定角色'),
                'DEPARTMENT': __('指定部門'),
                'DYNAMIC': __('動態')
            };

            const modeInfo = assigneeList.length > 1 ? `(${assigneeList.length}人，任一人簽)` : '';
            const decisionInfo = useCustomDecisions ? ` | 自定義決策 ${decisionOptions.length} 項` : '';
            updateStatus(`✅ 簽核設定已套用：${typeLabels[assigneeType]}${assigneeLabel ? ' - ' + assigneeLabel : ''} ${modeInfo}${decisionInfo}`, 'success');

            console.log('FormAdapter 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });

            // 同步更新變數總覽
            if (typeof reloadAllVars === 'function') reloadAllVars();
        }
        window.applyFormAdapterConfig = applyFormAdapterConfig;
