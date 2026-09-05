/**
 * wf-form-adapter.js -- FormAdapter 設定 Modal
 * 從 workflow-main.js 拆分
 * 包含: openFormAdapterModal, field permissions tab, end/SSP config
 */

        // ==================== FormAdapter 設定 Modal ====================

        // 開啟 FormAdapter 設定 Modal
        function buildTimeoutPathOptions(nodeId, config, selectedId) {
            const escape = (v) => String(v == null ? '' : v)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            let items = [];
            if (config.use_custom_decisions && Array.isArray(config.decision_options)) {
                items = config.decision_options.map(opt => ({ id: opt.id, label: opt.label || opt.value || opt.id }));
            } else if (window._faDecisions && typeof window._faDecisions.getOutgoingEdges === 'function') {
                items = window._faDecisions.getOutgoingEdges(nodeId).map(e => {
                    const tn = window.cy ? window.cy.getElementById(e.target) : null;
                    const tnLabel = (tn && tn.length) ? (tn.data('label') || e.target) : e.target;
                    return { id: e.id, label: e.label ? `${e.label} → ${tnLabel}` : tnLabel };
                });
            }
            const options = ['<option value="">-- 請選擇逾時去向 --</option>'];
            items.forEach(item => {
                if (!item.id) return;
                const sel = item.id === selectedId ? ' selected' : '';
                options.push(`<option value="${escape(item.id)}"${sel}>${escape(item.label)}</option>`);
            });
            return options.join('');
        }

        function openFormAdapterModal(nodeId) {
            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            const currentConfig = node.data('config') || {};
            const label = node.data('label') || '';
            const description = node.data('description') || '';
            const assigneeType = currentConfig.assignee_type || 'INITIATOR';
            const assigneeValue = currentConfig.assignee_value || '';
            const assigneeLabel = currentConfig.assignee_label || '';
            const assigneeListConfig = currentConfig.assignee_list || [];
            const selectionMode = currentConfig.selection_mode || 'single';
            const allowComment = currentConfig.allow_comment !== false;
            const minCommentLength = currentConfig.min_comment_length !== undefined
                ? parseInt(currentConfig.min_comment_length) || 0
                : (currentConfig.require_comment === true ? 1 : 0);
            const useCustomDecisions = currentConfig.use_custom_decisions || false;
            const outputVariable = currentConfig.output_variable || '';
            // 簽核逾時（PF-229 第三期第 2 項）：去向清單在開啟時依「自定義決策／出線」算一次
            const timeoutEnabled = currentConfig.timeout_enabled === true;
            const timeoutMinutes = parseInt(currentConfig.timeout_minutes, 10) || 480;
            const timeoutMode = currentConfig.timeout_mode === 'WORKING' ? 'WORKING' : 'ABSOLUTE';
            const timeoutPathId = currentConfig.timeout_path_id || '';
            const timeoutPathOptions = buildTimeoutPathOptions(nodeId, currentConfig, timeoutPathId);
            const noAssigneeAction = currentConfig.no_assignee_action === 'fallback_role' ? 'fallback_role' : 'return';
            const noAssigneeRoleSecureCode = currentConfig.no_assignee_role_secure_code || '';

            // 恢復已選擇的簽核者列表
            restoreSelectedAssignees(assigneeType, assigneeValue, assigneeLabel, assigneeListConfig);

            // 移除舊 Modal
            const old = document.getElementById('faConfigModal');
            if (old) old.remove();

            const modal = document.createElement('div');
            modal.id = 'faConfigModal';
            modal.className = 'fa-modal-overlay';
            modal.innerHTML = `
                <div class="fa-modal">
                    <div class="fa-modal-header">
                        <h3><i class="fas fa-user-check"></i> 簽核節點設定 — ${label}</h3>
                        <button class="fa-modal-close" onclick="closeFormAdapterModal()"><i class="fas fa-times"></i></button>
                    </div>
                    <div class="fa-modal-body">
                        <div class="fa-tab-nav">
                            <button class="fa-tab-btn active" onclick="switchFaTab(0)">基本設定</button>
                            <button class="fa-tab-btn" onclick="switchFaTab(1)">決策控制器</button>
                            <button class="fa-tab-btn" onclick="switchFaTab(2)">欄位權限設定</button>
                        </div>

                        <!-- Tab 0: 基本設定 -->
                        <div class="fa-tab-panel active" data-tab="0">
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
                                <div class="fa-modal-field">
                                    <label>節點名稱</label>
                                    <input type="text" id="fa-modal-label" value="${label}" placeholder="節點名稱">
                                </div>
                                <div class="fa-modal-field">
                                    <label>描述</label>
                                    <input type="text" id="fa-modal-desc" value="${description}" placeholder="選填">
                                </div>
                            </div>

                            <div class="fa-modal-field">
                                <strong>簽核者類型</strong>
                                <select id="formAdapterAssigneeType" onchange="toggleAssigneeValue()" style="margin-top: 4px;">
                                    <option value="INITIATOR" ${assigneeType === 'INITIATOR' ? 'selected' : ''}>發起人 (表單建立者)</option>
                                    <option value="USER" ${assigneeType === 'USER' ? 'selected' : ''}>指定用戶</option>
                                    <option value="DEPARTMENT" ${assigneeType === 'DEPARTMENT' ? 'selected' : ''}>指定部門</option>
                                    <option value="ROLE" ${assigneeType === 'ROLE' ? 'selected' : ''}>指定角色</option>
                                    <option value="DYNAMIC" ${assigneeType === 'DYNAMIC' ? 'selected' : ''}>動態 (從變數取)</option>
                                </select>
                            </div>

                            <div id="orgTreeContainer" class="fa-modal-field" style="display: ${['USER', 'DEPARTMENT'].includes(assigneeType) ? 'block' : 'none'};">
                                <strong>從組織樹選擇<span id="multiSelectHint" style="color: #667eea; font-size: 11px; display: ${assigneeType === 'USER' ? 'inline' : 'none'};"> (可多選)</span></strong>
                                <div style="margin-top: 4px; border: 1px solid #ddd; border-radius: 4px; background: #fafafa; max-height: 200px; overflow: auto;">
                                    <div id="orgTreeContent" style="padding: 8px; font-size: 12px;">
                                        <span style="color: #999;"><i class="fas fa-spinner fa-spin"></i> 載入中...</span>
                                    </div>
                                </div>
                                <div id="selectedAssignees" style="margin-top: 6px; padding: 8px; background: #e8f4fd; border-radius: 4px; display: none;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                        <span style="font-weight: bold; font-size: 12px;"><i class="fas fa-users" style="color: #28a745;"></i> 已選擇：</span>
                                        <button onclick="clearAllAssignees()" style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 11px;">
                                            <i class="fas fa-times"></i> 全部清除
                                        </button>
                                    </div>
                                    <div id="selectedAssigneesList" style="display: flex; flex-wrap: wrap; gap: 4px;"></div>
                                </div>
                            </div>

                            <div id="roleInputContainer" class="fa-modal-field" style="display: ${assigneeType === 'ROLE' ? 'block' : 'none'};">
                                <strong>選擇角色</strong>
                                <select id="formAdapterRoleValue" style="margin-top: 4px;">
                                    <option value="">載入中...</option>
                                </select>
                                <div style="margin-top: 3px; font-size: 10px; color: #888;">此角色下的所有用戶都可簽核</div>
                            </div>

                            <div id="dynamicInputContainer" class="fa-modal-field" style="display: ${assigneeType === 'DYNAMIC' ? 'block' : 'none'};">
                                <strong>變數名稱</strong>
                                <input type="text" id="formAdapterDynamicValue" value="${assigneeType === 'DYNAMIC' ? assigneeValue : ''}"
                                       placeholder="例如: manager_id" style="margin-top: 4px;">
                            </div>

                            <div class="fa-modal-field">
                                <strong>選擇模式</strong>
                                <div style="display: flex; gap: 8px; margin-top: 6px;">
                                    <label style="display: flex; align-items: center; padding: 8px 14px; border: 2px solid ${selectionMode === 'single' ? '#667eea' : '#e0e0e0'}; border-radius: 6px; cursor: pointer; flex: 1; background: ${selectionMode === 'single' ? '#f0f4ff' : 'white'};">
                                        <input type="radio" name="selectionMode" value="single" ${selectionMode === 'single' ? 'checked' : ''} style="margin-right: 6px;">
                                        <div><div style="font-weight: bold;">單選</div><div style="font-size: 10px; color: #666;">Radio</div></div>
                                    </label>
                                    <label style="display: flex; align-items: center; padding: 8px 14px; border: 2px solid ${selectionMode === 'multiple' ? '#667eea' : '#e0e0e0'}; border-radius: 6px; cursor: pointer; flex: 1; background: ${selectionMode === 'multiple' ? '#f0f4ff' : 'white'};">
                                        <input type="radio" name="selectionMode" value="multiple" ${selectionMode === 'multiple' ? 'checked' : ''} style="margin-right: 6px;">
                                        <div><div style="font-weight: bold;">複選</div><div style="font-size: 10px; color: #666;">Checkbox</div></div>
                                    </label>
                                </div>
                            </div>

                            <div class="fa-modal-field" style="border-top: 1px solid #eee; padding-top: 12px;">
                                <strong>備註設定</strong>
                                <label style="display: flex; align-items: center; margin-top: 6px; cursor: pointer;">
                                    <input type="checkbox" id="formAdapterAllowComment" ${allowComment ? 'checked' : ''} style="margin-right: 8px;"
                                           onchange="document.getElementById('minCommentLengthRow').style.display = this.checked ? 'flex' : 'none';">
                                    顯示備註欄位
                                </label>
                                <div id="minCommentLengthRow" style="display: ${allowComment ? 'flex' : 'none'}; align-items: center; margin-top: 6px; gap: 8px;">
                                    <span style="white-space: nowrap;">最少字數：</span>
                                    <input type="number" id="formAdapterMinCommentLength" value="${minCommentLength}" min="0" max="500" step="1"
                                           style="width: 80px; text-align: center;">
                                    <span style="font-size: 10px; color: #999;">0 = 不需留言</span>
                                </div>
                            </div>

                            <div class="fa-modal-field" style="border-top: 1px solid #eee; padding-top: 12px;">
                                <strong>簽核逾時</strong>
                                <label style="display: flex; align-items: center; margin-top: 6px; cursor: pointer;">
                                    <input type="checkbox" id="faTimeoutEnabled" ${timeoutEnabled ? 'checked' : ''} style="margin-right: 8px;"
                                           onchange="document.getElementById('faTimeoutSettings').style.display = this.checked ? 'block' : 'none';">
                                    啟用逾時自動處理
                                </label>
                                <div id="faTimeoutSettings" style="display: ${timeoutEnabled ? 'block' : 'none'}; margin-top: 6px;">
                                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                                        <span style="white-space: nowrap;">逾時時間（分鐘）：</span>
                                        <input type="number" id="faTimeoutMinutes" value="${timeoutMinutes}" min="1" max="14400" step="1"
                                               style="width: 90px; text-align: center;">
                                        <span style="font-size: 10px; color: #999;">最大 14400（10 天）</span>
                                    </div>
                                    <div style="margin-bottom: 6px;">
                                        <span>計時方式：</span>
                                        <select id="faTimeoutMode" style="margin-top: 4px; width: 100%;">
                                            <option value="ABSOLUTE" ${timeoutMode === 'ABSOLUTE' ? 'selected' : ''}>絕對時間（24/7 倒數）</option>
                                            <option value="WORKING" ${timeoutMode === 'WORKING' ? 'selected' : ''}>工作時間（只在簽核者班表內倒數，扣掉請假；無班表退回絕對時間）</option>
                                        </select>
                                    </div>
                                    <div>
                                        <span>逾時去向：</span>
                                        <select id="faTimeoutPathId" style="margin-top: 4px; width: 100%;">
                                            ${timeoutPathOptions}
                                        </select>
                                        <div style="font-size: 10px; color: #888; margin-top: 3px;">
                                            逾時後由系統自動採用這個決策（自定義決策）或走這條出線；未配對出線的決策視為駁回終態。
                                            切換自定義決策或改了出線後，請重新開啟本設定更新清單。
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="fa-modal-field" style="border-top: 1px solid #eee; padding-top: 12px;">
                                <strong>${__('找不到簽核人時')}</strong>
                                <select id="faNoAssigneeAction" onchange="toggleNoAssigneeRoleRow()" style="margin-top: 6px; width: 100%;">
                                    <option value="return" ${noAssigneeAction === 'return' ? 'selected' : ''}>${__('退回申請人重送（預設）')}</option>
                                    <option value="fallback_role" ${noAssigneeAction === 'fallback_role' ? 'selected' : ''}>${__('改派給角色')}</option>
                                </select>
                                <div id="faNoAssigneeRoleRow" style="display: ${noAssigneeAction === 'fallback_role' ? 'block' : 'none'}; margin-top: 6px;">
                                    <select id="faNoAssigneeRole" style="width: 100%;">
                                        <option value="">${__('載入中...')}</option>
                                    </select>
                                </div>
                                <div style="font-size: 10px; color: #888; margin-top: 3px; line-height: 1.5;">
                                    ${__('簽核者清單解析為空時（例如動態變數沒有值、人事取值找不到核決人）依此處理。')}
                                    ${__('改派給角色後，管理員把人加進該角色即可簽核；角色當下沒有成員也不會退回。')}
                                </div>
                            </div>
                        </div>

                        <!-- Tab 1: 決策控制器 -->
                        <div class="fa-tab-panel" data-tab="1">
                            <div class="fa-modal-field">
                                <label style="display: flex; align-items: center; cursor: pointer;">
                                    <input type="checkbox" id="faUseCustomDecisions" ${useCustomDecisions ? 'checked' : ''} style="margin-right: 8px;"
                                           onchange="if(window._faDecisions) window._faDecisions.toggleCustomDecisions('${nodeId}', this.checked);">
                                    <strong>啟用自定義決策選項</strong>
                                </label>
                            </div>

                            <div id="customDecisionsPanel" style="display: ${useCustomDecisions ? 'block' : 'none'};">
                                <div class="fa-modal-field">
                                    <label style="color: #666;">傳出變數名稱</label>
                                    <input type="text" id="faOutputVariable" value="${outputVariable}"
                                           placeholder="例如: fa_decision"
                                           oninput="if(window.cy){var n=window.cy.getElementById('${nodeId}');if(n&&n.length){var c=n.data('config')||{};c.output_variable=this.value.trim();n.data('config',c);}}">
                                    <div style="font-size: 10px; color: #888; margin-top: 2px;">決策值寫入此全域變數，供下游節點讀取（Branch、通知、子流程等）</div>
                                </div>

                                <div style="margin-bottom: 6px;">
                                    <strong>決策 → 流程去向</strong>
                                </div>
                                <div id="edgeMappingContainer"></div>

                                <div style="margin-top: 8px; margin-bottom: 8px;">
                                    <button onclick="window._faDecisions.addOption('${nodeId}')" style="padding: 3px 10px; border: 1px solid #667eea; border-radius: 4px; background: #f0f4ff; cursor: pointer; font-size: 11px; color: #667eea;">
                                        <i class="fas fa-plus"></i> 新增決策
                                    </button>
                                </div>

                                <div id="decisionConfigBlock" style="margin-bottom: 10px;"></div>

                                <div style="margin-top: 14px; border-top: 1px solid #eee; padding-top: 10px;">
                                    <strong>來向變數控制</strong>
                                    <div style="font-size: 10px; color: #888; margin-bottom: 6px;">根據上游變數動態控制決策選項顯示/欄位權限</div>
                                    <div id="inputVariablesContainer"></div>
                                    <button onclick="window._faDecisions.addInputVar('${nodeId}')" style="width: 100%; padding: 6px; border: 1px dashed #28a745; border-radius: 4px; background: #f0fff4; cursor: pointer; font-size: 11px; color: #28a745;">
                                        <i class="fas fa-plus"></i> 新增來向變數
                                    </button>
                                </div>
                            </div>

                            <div class="fa-modal-hint">
                                <i class="fas fa-lightbulb"></i>
                                <strong>按鈕名稱來源：</strong>edge label → 目標節點 label → 節點類型。
                                選取連接線，在右側「條件分支設定」區塊設定「標籤文字」作為按鈕名稱。
                            </div>
                        </div>

                        <!-- Tab 2: 欄位權限設定 -->
                        <div class="fa-tab-panel" data-tab="2">
                            <div id="fieldPermTabContent">
                                <div style="text-align: center; padding: 40px; color: #999;">
                                    <i class="fas fa-shield-alt" style="font-size: 24px; margin-bottom: 8px; display: block;"></i>
                                    切換到此頁籤時自動載入欄位權限
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="fa-modal-footer">
                        <span id="faModalMessage" class="fa-modal-message"></span>
                        <button class="fa-modal-btn-cancel" onclick="closeFormAdapterModal()">取消</button>
                        <button class="fa-modal-btn-save" onclick="saveFormAdapterModal('${nodeId}')"><i class="fas fa-check"></i> 套用並關閉</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // 重置 Tab 狀態
            _faTabCurrentNodeId = nodeId;
            _faTabFieldPermLoaded = false;

            // DOM ready 後初始化子元件
            setTimeout(function() {
                initOrgTree(assigneeType);
                loadRolesList(assigneeValue);
                loadRoleOptionsInto('faNoAssigneeRole', noAssigneeRoleSecureCode);
                if (window._faDecisions && useCustomDecisions) {
                    const outEdges = window._faDecisions.getOutgoingEdges(nodeId);
                    window._faDecisions.renderDecisionConfigBlock(nodeId, currentConfig.decision_options || []);
                    window._faDecisions.renderEdgeMapping(nodeId, currentConfig.decision_options || [], outEdges);
                    window._faDecisions.renderInputVariables(nodeId, currentConfig.input_variables || []);
                    // 已啟用自定義決策：直接跳到決策控制器頁籤
                    switchFaTab(1);
                }
            }, 50);
        }
        window.openFormAdapterModal = openFormAdapterModal;

        // 關閉 FormAdapter Modal
        function closeFormAdapterModal() {
            const modal = document.getElementById('faConfigModal');
            if (modal) modal.remove();
        }
        window.closeFormAdapterModal = closeFormAdapterModal;

        // FormAdapter 頁籤切換
        let _faTabFieldPermLoaded = false;
        let _faTabCurrentNodeId = null;

        function switchFaTab(index) {
            const modal = document.getElementById('faConfigModal');
            if (!modal) return;

            modal.querySelectorAll('.fa-tab-btn').forEach(function(btn, i) {
                btn.classList.toggle('active', i === index);
            });
            modal.querySelectorAll('.fa-tab-panel').forEach(function(panel) {
                panel.classList.toggle('active', parseInt(panel.dataset.tab) === index);
            });

            // Tab 1: 重繪連連看連線（從隱藏狀態切換過來後 getBoundingClientRect 才有值）
            if (index === 1 && window._faDecisions) {
                setTimeout(function() { window._faDecisions.redrawMappingLines(); }, 0);
            }

            // Tab 2: 自動載入欄位權限
            if (index === 2 && !_faTabFieldPermLoaded && _faTabCurrentNodeId) {
                _faTabFieldPermLoaded = true;
                loadFieldPermissionsInTab(_faTabCurrentNodeId);
            }
        }
        window.switchFaTab = switchFaTab;

        // 在 Tab 2 內嵌載入欄位權限
        async function loadFieldPermissionsInTab(nodeId) {
            const content = document.getElementById('fieldPermTabContent');
            if (!content) return;

            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            fieldPermCurrentNodeId = nodeId;
            content.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;"><i class="fas fa-spinner fa-spin"></i> 載入表單欄位中...</div>';

            if (!currentMappedForms || currentMappedForms.length === 0) {
                await loadMappedForms('design');
            }

            if (!currentMappedForms || currentMappedForms.length === 0) {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> 此流程尚未配對任何表單，請先到「配對管理」建立配對。</div>';
                return;
            }

            const form = currentMappedForms[0];
            const formIdentifier = form.form_secure_code || form.form_id;
            let url = `${window.__BP}/api/workflows/data/forms/${formIdentifier}/fields?version_type=design`;
            if (form.mapping_id) url += `&mapping_id=${form.mapping_id}`;

            try {
                const response = await fetch(url);
                const result = await response.json();
                if (!result.success) throw new Error(result.message || __('載入失敗'));

                fieldPermFormFields = result.data.fields || [];
                renderFieldPermissionsInTab(node, form.form_name, content);
            } catch (error) {
                content.innerHTML = `<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> ${error.message}</div>`;
            }
        }

        // 在指定容器內渲染欄位權限表格
        function renderFieldPermissionsInTab(node, formName, container) {
            const currentConfig = node.data('config') || {};
            const savedPerms = currentConfig.field_permissions || {};
            const approverPerms = savedPerms.approver || {};
            const readerPerms = savedPerms.reader || {};

            if (fieldPermFormFields.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">此表單沒有可設定的欄位</div>';
                return;
            }

            const permOptions = [
                { value: 'readonly', label: '唯讀' },
                { value: 'editable', label: '可修改' },
                { value: 'hidden', label: '隱藏' },
            ];

            function makeSelect(name, currentVal) {
                return `<select data-perm-tab="${name}" style="width:100%; padding:4px 6px; border:1px solid #d1d5db; border-radius:3px; font-size:12px; background:white;">
                    ${permOptions.map(o => `<option value="${o.value}" ${currentVal === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                </select>`;
            }

            let rows = '';
            fieldPermFormFields.forEach(field => {
                const aVal = approverPerms[field.key] || 'readonly';
                const rVal = readerPerms[field.key] || 'readonly';
                rows += `<tr style="border-bottom:1px solid #f3f4f6;">
                    <td style="padding:8px 10px; font-size:12px; font-weight:500; white-space:nowrap;">${field.label || field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#666;">${field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#888;">${field.type}</td>
                    <td style="padding:8px 10px;">${makeSelect('approver_' + field.key, aVal)}</td>
                    <td style="padding:8px 10px;">${makeSelect('reader_' + field.key, rVal)}</td>
                </tr>`;
            });

            container.innerHTML = `
                <div style="margin-bottom:12px; font-size:13px; color:#374151;">
                    <strong>表單：</strong>${formName}
                    <span style="margin-left:16px; font-size:12px; color:#6b7280;">共 ${fieldPermFormFields.length} 個欄位</span>
                </div>
                <div style="margin-bottom:12px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button onclick="fpBatchSetTab('approver', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">簽核者全部唯讀</button>
                    <button onclick="fpBatchSetTab('approver', 'editable')" style="padding:4px 10px; font-size:11px; background:#dbeafe; border:1px solid #93c5fd; border-radius:3px; cursor:pointer;">簽核者全部可修改</button>
                    <button onclick="fpBatchSetTab('reader', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">閱讀者全部唯讀</button>
                    <button onclick="fpBatchSetTab('reader', 'hidden')" style="padding:4px 10px; font-size:11px; background:#fee2e2; border:1px solid #fca5a5; border-radius:3px; cursor:pointer;">閱讀者全部隱藏</button>
                </div>
                <div style="border:1px solid #e5e7eb; border-radius:4px; overflow:hidden;">
                    <table style="width:100%; border-collapse:collapse;">
                        <thead>
                            <tr style="background:#f9fafb;">
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">欄位標籤</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">Key</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">類型</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#eff6ff;">簽核者</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#fefce8;">閱讀者</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="margin-top:12px; font-size:11px; color:#6b7280;">
                    <i class="fas fa-info-circle"></i>
                    未設定的欄位預設為「唯讀」。簽核者 = FormAdapter 指定的簽核人，閱讀者 = 其他檢視者。
                </div>
            `;
        }

        // Tab 內批次設定權限
        function fpBatchSetTab(role, value) {
            const selects = document.querySelectorAll(`select[data-perm-tab^="${role}_"]`);
            selects.forEach(sel => { sel.value = value; });
        }
        window.fpBatchSetTab = fpBatchSetTab;

        // 從 Tab 2 收集欄位權限並存入 node config
        function saveFieldPermissionsFromTab(nodeId) {
            if (!fieldPermFormFields || fieldPermFormFields.length === 0) return;

            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            const approverPerms = {};
            const readerPerms = {};

            fieldPermFormFields.forEach(field => {
                const aSelect = document.querySelector(`select[data-perm-tab="approver_${field.key}"]`);
                const rSelect = document.querySelector(`select[data-perm-tab="reader_${field.key}"]`);
                if (aSelect) approverPerms[field.key] = aSelect.value;
                if (rSelect) readerPerms[field.key] = rSelect.value;
            });

            const currentConfig = node.data('config') || {};
            currentConfig.field_permissions = {
                approver: approverPerms,
                reader: readerPerms,
            };
            node.data('config', currentConfig);
        }

        // 套用並關閉 FormAdapter Modal
        function saveFormAdapterModal(nodeId) {
            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            // 0. 清除先前訊息
            const msgEl = document.getElementById('faModalMessage');
            if (msgEl) { msgEl.textContent = ''; msgEl.className = 'fa-modal-message'; }

            // 驗證：啟用自定義決策時，所有決策選項和去向都必須有連線
            const useCustom = document.getElementById('faUseCustomDecisions')?.checked || false;
            if (useCustom && window._faDecisions) {
                const options = window._faDecisions.collectDecisionOptions();
                const outEdges = window._faDecisions.getOutgoingEdges(nodeId);

                if (options.length > 0 && outEdges.length > 0) {
                    // 檢查每個決策選項是否都有連線
                    const unmappedOptions = options.filter(opt => !opt.target_edges || opt.target_edges.length === 0);
                    if (unmappedOptions.length > 0) {
                        const names = unmappedOptions.map((o, i) => o.label || __('(未命名)')).join('、');
                        if (msgEl) { msgEl.textContent = __('決策選項 [') + names + '] 尚未連接去向'; msgEl.className = 'fa-modal-message warning'; }
                        const tab1 = document.querySelectorAll('.fa-modal-tab')[1];
                        if (tab1) tab1.click();
                        return;
                    }

                    // 檢查每個去向是否都有決策選項連到它
                    const connectedEdgeIds = new Set();
                    options.forEach(opt => (opt.target_edges || []).forEach(eid => connectedEdgeIds.add(eid)));
                    const unmappedEdges = outEdges.filter(e => !connectedEdgeIds.has(e.id));
                    if (unmappedEdges.length > 0) {
                        const names = unmappedEdges.map(e => {
                            if (e.label) return e.label;
                            const tn = cy.getElementById(e.target);
                            return (tn && tn.length) ? (tn.data('label') || e.target) : e.target;
                        }).join('、');
                        if (msgEl) { msgEl.textContent = __('去向 [') + names + '] 沒有任何決策選項連接'; msgEl.className = 'fa-modal-message warning'; }
                        const tab1 = document.querySelectorAll('.fa-modal-tab')[1];
                        if (tab1) tab1.click();
                        return;
                    }
                }
            }

            // 1. 從 Modal 讀取名稱/描述（Modal 用不同 ID 避免衝突）
            const modalLabel = document.getElementById('fa-modal-label');
            const modalDesc = document.getElementById('fa-modal-desc');
            if (modalLabel) node.data('label', modalLabel.value.trim() || node.data('label'));
            if (modalDesc) node.data('description', modalDesc.value.trim());

            // 2. 同步到右側面板的 input（讓 applyFormAdapterConfig 的 applyNodeBasicInfo 不覆蓋）
            const panelLabel = document.getElementById('node-label-input');
            const panelDesc = document.getElementById('node-description-input');
            if (panelLabel) panelLabel.value = node.data('label');
            if (panelDesc) panelDesc.value = node.data('description') || '';

            // 3. 呼叫原本的 apply 函式（讀取 Modal 內的表單元素）
            if (applyFormAdapterConfig(nodeId) === false) return;

            // 4. 若 Tab 2 已載入欄位權限，一併儲存
            if (_faTabFieldPermLoaded) {
                saveFieldPermissionsFromTab(nodeId);
            }

            // 5. 關閉 Modal 並刷新摘要
            closeFormAdapterModal();
            if (node && node.length) {
                showNodeInfo(node);
            }
        }
        window.saveFormAdapterModal = saveFormAdapterModal;

        // 更新 End 節點 finish_mode 選擇樣式
        function updateFinishModeSelection(radio) {
            // 重設所有選項的樣式
            document.querySelectorAll('input[name="finishMode"]').forEach(input => {
                const label = input.closest('label');
                if (input.value === 'detach') {
                    label.style.borderColor = input.checked ? '#667eea' : '#e0e0e0';
                    label.style.background = input.checked ? '#f0f4ff' : 'white';
                } else if (input.value === 'cancel') {
                    label.style.borderColor = input.checked ? '#ff6b00' : '#e0e0e0';
                    label.style.background = input.checked ? '#fff8f0' : 'white';
                } else if (input.value === 'strict') {
                    label.style.borderColor = input.checked ? '#28a745' : '#e0e0e0';
                    label.style.background = input.checked ? '#f0fff4' : 'white';
                }
            });
        }
        window.updateFinishModeSelection = updateFinishModeSelection;

        // 套用 END 結束節點配置
        function applyEndConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const finishModeInput = document.querySelector('input[name="finishMode"]:checked');
            if (!finishModeInput) {
                updateStatus(__('請選擇結束模式'), 'warning');
                return;
            }

            const finishMode = finishModeInput.value;

            // 讀取等待秒數
            const waitSecondsInput = document.getElementById('endWaitSeconds');
            const waitSeconds = waitSecondsInput ? parseInt(waitSecondsInput.value) || 3 : 3;

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                finish_mode: finishMode,
                wait_seconds: waitSeconds
            };

            node.data('config', updatedConfig);
            node.data('finishMode', finishMode);

            // 根據模式顯示不同訊息
            const modeNames = {
                'detach': __('分離執行模式'),
                'cancel': __('取消/終止模式'),
                'strict': __('嚴格等待模式')
            };

            updateStatus(`✅ 結束模式：${modeNames[finishMode]}，等待 ${waitSeconds} 秒`, 'success');

            console.log('END 節點配置已更新:', {
                nodeId: nodeId,
                finish_mode: finishMode,
                wait_seconds: waitSeconds,
                config: updatedConfig
            });
        }
        window.applyEndConfig = applyEndConfig;

        // SubSystemProvision 子系統配置節點

        function toggleSSPFields() {
            const action = document.querySelector('input[name="sspAction"]:checked');
            if (!action) return;
            const createFields = document.getElementById('sspCreateFields');
            const targetFields = document.getElementById('sspTargetFields');
            if (createFields) createFields.style.display = action.value === 'create' ? 'block' : 'none';
            if (targetFields) targetFields.style.display = action.value !== 'create' ? 'block' : 'none';
        }
        window.toggleSSPFields = toggleSSPFields;

        function applySSPConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const actionEl = document.querySelector('input[name="sspAction"]:checked');
            if (!actionEl) {
                updateStatus(__('請選擇動作類型'), 'warning');
                return;
            }
            const action = actionEl.value;
            const currentConfig = node.data('config') || {};
            const updatedConfig = { ...currentConfig, action };

            if (action === 'create') {
                const nameEl = document.getElementById('sspName');
                const devEl = document.getElementById('sspDeveloper');
                const iconEl = document.getElementById('sspIcon');
                updatedConfig.sub_system_name = nameEl ? nameEl.value.trim() : '';
                updatedConfig.sub_system_developer = devEl ? devEl.value.trim() : '';
                updatedConfig.sub_system_icon = iconEl ? iconEl.value.trim() : '';
                if (!updatedConfig.sub_system_name) {
                    updateStatus(__('子系統名稱為必填'), 'warning');
                    return;
                }
            } else {
                const codeEl = document.getElementById('sspCode');
                updatedConfig.sub_system_code = codeEl ? codeEl.value.trim() : '';
                if (!updatedConfig.sub_system_code) {
                    updateStatus(__('子系統代碼為必填'), 'warning');
                    return;
                }
            }

            node.data('config', updatedConfig);
            const labels = { create: __('建立'), suspend: __('停用'), delete: __('刪除') };
            updateStatus(`子系統配置：${labels[action] || action}`, 'success');

            console.log('SubSystemProvision 配置已更新:', {
                nodeId, action, config: updatedConfig
            });
        }
        window.applySSPConfig = applySSPConfig;
