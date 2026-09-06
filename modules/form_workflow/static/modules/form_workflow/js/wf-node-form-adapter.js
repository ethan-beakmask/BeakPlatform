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
        let unitsListData = null;

        function escapeHtml(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        // 載入角色列表到指定 select
        async function loadRoleOptionsInto(selectId, selectedValue, afterRender) {
            if (rolesListData) {
                // 已有快取，延遲渲染（等 DOM 準備好）
                setTimeout(() => {
                    const sel = document.getElementById(selectId);
                    if (sel) {
                        renderRolesSelect(sel, rolesListData, selectedValue);
                        if (typeof afterRender === 'function') afterRender(sel);
                    }
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
                        const sel = document.getElementById(selectId);
                        if (sel) {
                            renderRolesSelect(sel, rolesListData, selectedValue);
                            if (typeof afterRender === 'function') afterRender(sel);
                        }
                    }, 50);
                }
            } catch (error) {
                console.error('載入角色列表失敗:', error);
                setTimeout(() => {
                    const sel = document.getElementById(selectId);
                    if (sel) sel.innerHTML = '<option value="">載入失敗</option>';
                }, 50);
            }
        }
        window.loadRoleOptionsInto = loadRoleOptionsInto;

        function renderRolesSelect(select, roles, selectedValue) {
            let html = `<option value="">-- ${__('請選擇角色')} --</option>`;
            for (const role of roles) {
                const selected = role.secure_code === selectedValue ? 'selected' : '';
                html += `<option value="${escapeHtml(role.secure_code)}" data-role-type="${escapeHtml(role.role_type || 'ROLE')}" ${selected}>${escapeHtml(role.name)}</option>`;
            }
            select.innerHTML = html;
        }

        async function loadUnitOptionsInto(selectId, selectedValue) {
            if (unitsListData) {
                setTimeout(() => {
                    const sel = document.getElementById(selectId);
                    if (sel) renderUnitsSelect(sel, unitsListData, selectedValue);
                }, 50);
                return;
            }

            try {
                const response = await fetch(window.__BP + '/api/workflows/data/units');
                const result = await response.json();
                if (result.success) {
                    unitsListData = result.data;
                    setTimeout(() => {
                        const sel = document.getElementById(selectId);
                        if (sel) renderUnitsSelect(sel, unitsListData, selectedValue);
                    }, 50);
                }
            } catch (error) {
                console.error('載入單位列表失敗:', error);
                setTimeout(() => {
                    const sel = document.getElementById(selectId);
                    if (sel) sel.innerHTML = `<option value="">${__('載入失敗')}</option>`;
                }, 50);
            }
        }
        window.loadUnitOptionsInto = loadUnitOptionsInto;

        function renderUnitsSelect(select, units, selectedValue) {
            let html = `<option value="">-- ${__('請選擇單位')} --</option>`;
            for (const unit of units) {
                const selected = unit.secure_code === selectedValue ? 'selected' : '';
                const indent = unit.unit_type === 'DEPARTMENT' ? '　'.repeat(Math.max((parseInt(unit.level, 10) || 1) - 1, 0)) : '';
                const suffix = unit.unit_type === 'GROUP' ? `（${__('社群')}）` : '';
                html += `<option value="${escapeHtml(unit.secure_code)}" data-unit-name="${escapeHtml(unit.name)}" ${selected}>${indent}${escapeHtml(unit.name)}${suffix}</option>`;
            }
            select.innerHTML = html;
        }
        window.renderUnitsSelect = renderUnitsSelect;

        function toggleUnitScopeRows() {
            const unitScope = document.getElementById('faUnitScope')?.value || 'GLOBAL';
            const unitRow = document.getElementById('faUnitRow');
            const levelsRow = document.getElementById('faUnitLevelsRow');
            const selfTargetRow = document.getElementById('faSelfTargetRow');
            if (unitRow) unitRow.style.display = unitScope === 'UNIT' ? 'block' : 'none';
            if (levelsRow) levelsRow.style.display = unitScope === 'APPLICANT_ANCESTOR' ? 'flex' : 'none';
            if (selfTargetRow) selfTargetRow.style.display = ['APPLICANT_UNIT', 'APPLICANT_ANCESTOR'].includes(unitScope) ? 'block' : 'none';
        }
        window.toggleUnitScopeRows = toggleUnitScopeRows;

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
                toggleUnitScopeRows();
            } else if (assigneeType === 'DYNAMIC') {
                if (dynamicInputContainer) dynamicInputContainer.style.display = 'block';
            }

            // 清除之前的選擇
            clearAssigneeSelection();
        }
        window.toggleAssigneeValue = toggleAssigneeValue;

        function toggleNoAssigneeRoleRow() {
            const action = document.getElementById('faNoAssigneeAction')?.value || 'return';
            const roleRow = document.getElementById('faNoAssigneeRoleRow');
            if (roleRow) roleRow.style.display = action === 'fallback_role' ? 'block' : 'none';
        }
        window.toggleNoAssigneeRoleRow = toggleNoAssigneeRoleRow;

        // 套用 FormAdapter 簽核節點配置
        function applyFormAdapterConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return false;

            // 讀取表單值
            const assigneeType = document.getElementById('formAdapterAssigneeType')?.value || 'INITIATOR';
            let assigneeValue = '';
            let assigneeLabel = '';
            let assigneeList = [];  // 多用戶列表
            let roleUnitConfig = {};

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
                const roleName = roleSelect?.selectedOptions[0]?.text || assigneeValue;
                const unitScopeEl = document.getElementById('faUnitScope');
                const rawUnitScope = unitScopeEl?.value || 'GLOBAL';
                const unitScope = ['GLOBAL', 'UNIT', 'APPLICANT_UNIT', 'APPLICANT_ANCESTOR'].includes(rawUnitScope) ? rawUnitScope : 'GLOBAL';
                const unitSelect = document.getElementById('faUnitSecureCode');
                const unitSecureCode = unitScope === 'UNIT' ? (unitSelect?.value || '') : '';
                const unitLabel = unitScope === 'UNIT' ? (unitSelect?.selectedOptions[0]?.dataset.unitName || unitSelect?.selectedOptions[0]?.text || '') : '';
                const rawLevels = parseInt(document.getElementById('faUnitLevelsUp')?.value, 10);
                const unitLevelsUp = Number.isNaN(rawLevels) ? 1 : rawLevels;  // 0 或負數要留給下方驗證擋，不能被 || 1 吃掉
                const rawSelfTargetAction = document.getElementById('faSelfTargetAction')?.value || 'escalate_or_return';
                const selfTargetAction = ['escalate_or_return', 'escalate_or_self', 'self'].includes(rawSelfTargetAction) ? rawSelfTargetAction : 'escalate_or_return';
                const msg = document.getElementById('faModalMessage');
                if (unitScope === 'UNIT' && !unitSecureCode) {
                    const error = __('單位範圍為指定單位時必須選擇單位');
                    if (msg) { msg.textContent = error; msg.className = 'fa-modal-message warning'; }
                    else { updateStatus(error, 'warning'); }
                    return false;
                }
                if (unitScope === 'APPLICANT_ANCESTOR' && unitLevelsUp < 1) {
                    const error = __('往上層數必須是 1 以上的整數');
                    if (msg) { msg.textContent = error; msg.className = 'fa-modal-message warning'; }
                    else { updateStatus(error, 'warning'); }
                    return false;
                }
                if (unitScope === 'GLOBAL') assigneeLabel = roleName;
                else if (unitScope === 'UNIT') assigneeLabel = `${roleName}@${unitLabel}`;
                else if (unitScope === 'APPLICANT_UNIT') assigneeLabel = `${roleName}@${__('申請人所屬單位')}`;
                else assigneeLabel = `${roleName}@${__('申請人單位上 {n} 層', { n: unitLevelsUp })}`;
                roleUnitConfig = {
                    unit_scope: unitScope,
                    unit_secure_code: unitSecureCode,
                    unit_label: unitLabel,
                    unit_levels_up: unitLevelsUp,
                    self_target_action: selfTargetAction
                };
            } else if (assigneeType === 'DYNAMIC') {
                assigneeValue = document.getElementById('formAdapterDynamicValue')?.value || '';
                assigneeLabel = assigneeValue;
            }

            const selectionModeRadio = document.querySelector('input[name="selectionMode"]:checked');
            const selectionMode = selectionModeRadio?.value || 'single';
            const allowComment = document.getElementById('formAdapterAllowComment')?.checked !== false;
            const minCommentLength = parseInt(document.getElementById('formAdapterMinCommentLength')?.value) || 0;
            const currentConfig = node.data('config') || {};

            // 驗證
            if (assigneeType !== 'INITIATOR' && !assigneeValue.trim()) {
                const msg = document.getElementById('faModalMessage');
                if (msg) { msg.textContent = __('請選擇或填寫簽核者'); msg.className = 'fa-modal-message warning'; }
                else { updateStatus(__('請選擇或填寫簽核者'), 'warning'); }
                return false;
            }

            // 簽核逾時（PF-229 第三期第 2 項）
            const timeoutEnabled = document.getElementById('faTimeoutEnabled')?.checked || false;
            const timeoutMinutes = parseInt(document.getElementById('faTimeoutMinutes')?.value, 10) || 0;
            const timeoutMode = document.getElementById('faTimeoutMode')?.value === 'WORKING' ? 'WORKING' : 'ABSOLUTE';
            const timeoutPathId = document.getElementById('faTimeoutPathId')?.value || '';
            if (timeoutEnabled) {
                const msg = document.getElementById('faModalMessage');
                let timeoutError = '';
                if (timeoutMinutes < 1 || timeoutMinutes > 14400) timeoutError = __('逾時時間必須是 1 到 14400 分鐘');
                else if (!timeoutPathId) timeoutError = __('啟用簽核逾時時必須指定逾時去向');
                if (timeoutError) {
                    if (msg) { msg.textContent = timeoutError; msg.className = 'fa-modal-message warning'; }
                    else { updateStatus(timeoutError, 'warning'); }
                    return false;
                }
            }

            const noAssigneeActionEl = document.getElementById('faNoAssigneeAction');
            const noAssigneeAction = noAssigneeActionEl
                ? (noAssigneeActionEl.value === 'fallback_role' ? 'fallback_role' : 'return')
                : (currentConfig.no_assignee_action === 'fallback_role' ? 'fallback_role' : 'return');
            const noAssigneeRoleSelect = document.getElementById('faNoAssigneeRole');
            const noAssigneeRoleSecureCode = noAssigneeAction === 'fallback_role'
                ? (noAssigneeRoleSelect ? (noAssigneeRoleSelect.value || '') : (currentConfig.no_assignee_role_secure_code || '')) : '';
            const noAssigneeRoleLabel = noAssigneeAction === 'fallback_role'
                ? (noAssigneeRoleSelect ? (noAssigneeRoleSelect.selectedOptions[0]?.text || '') : (currentConfig.no_assignee_role_label || '')) : '';
            if (noAssigneeAction === 'fallback_role' && !noAssigneeRoleSecureCode) {
                const msg = document.getElementById('faModalMessage');
                const error = __('改派給角色時必須選擇角色');
                if (msg) { msg.textContent = error; msg.className = 'fa-modal-message warning'; }
                else { updateStatus(error, 'warning'); }
                return false;
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
                input_variables: inputVariables,
                timeout_enabled: timeoutEnabled,
                timeout_minutes: timeoutEnabled ? timeoutMinutes : 0,
                timeout_mode: timeoutMode,
                timeout_path_id: timeoutEnabled ? timeoutPathId : '',
                no_assignee_action: noAssigneeAction,
                no_assignee_role_secure_code: noAssigneeRoleSecureCode,
                no_assignee_role_label: noAssigneeRoleLabel,
                ...roleUnitConfig
            };

            node.data('config', updatedConfig);

            const typeLabels = {
                'INITIATOR': __('發起人'),
                'USER': __('指定用戶'),
                'ROLE': __('指定角色'),
                'DEPARTMENT': __('指定部門（舊）'),
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
            return true;
        }
        window.applyFormAdapterConfig = applyFormAdapterConfig;
