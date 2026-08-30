/**
 * wf-node-branch.js -- BRANCH 條件路由節點配置
 * 從 wf-node-configs.js 拆分
 */

        // 儲存當前編輯中的 BRANCH 規則
        let branchRulesData = [];
        let branchOutgoingEdges = [];
        let branchCurrentNodeId = null;

        // 載入節點的出線
        function loadBranchOutgoingEdges(nodeId, fallback) {
            branchCurrentNodeId = nodeId;
            branchOutgoingEdges = [];

            const node = cy.getElementById(nodeId);
            if (!node) return;

            // 找出所有從此節點出去的邊
            cy.edges().forEach(edge => {
                const edgeData = edge.data();
                if (edgeData.source === nodeId) {
                    const targetNode = cy.getElementById(edgeData.target);
                    const targetLabel = targetNode ? (targetNode.data('label') || targetNode.data('type') || edgeData.target) : edgeData.target;
                    const edgeLabel = edgeData.label || '';

                    branchOutgoingEdges.push({
                        id: edge.id(),
                        target: edgeData.target,
                        targetLabel: targetLabel,
                        edgeLabel: edgeLabel,
                        displayText: edgeLabel ? `${edgeLabel} → ${targetLabel}` : `→ ${targetLabel}`
                    });
                }
            });

            // 更新 fallback 目標選項並恢復已選擇的值
            updateBranchFallbackOptions(fallback);

            console.log('BRANCH 出線載入完成:', branchOutgoingEdges);
        }
        window.loadBranchOutgoingEdges = loadBranchOutgoingEdges;

        // 更新 fallback 目標下拉選單
        function updateBranchFallbackOptions(fallback) {
            const select = document.getElementById('branchFallbackTarget');
            if (!select) return;

            select.innerHTML = '<option value="">選擇目標出線...</option>';
            branchOutgoingEdges.forEach(edge => {
                const option = document.createElement('option');
                option.value = edge.id;
                option.textContent = edge.displayText;
                select.appendChild(option);
            });

            // 恢復已選擇的 fallback target
            if (fallback && fallback.target_edge) {
                select.value = fallback.target_edge;
            }
        }

        // 渲染分支規則列表
        function renderBranchRules(rules, nodeId) {
            branchRulesData = rules.map((r, i) => ({...r, _index: i}));
            branchCurrentNodeId = nodeId;

            const container = document.getElementById('branchRulesList');
            if (!container) return;

            if (branchRulesData.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: #999; font-size: 11px; padding: 15px;">尚無規則，請點擊「新增規則」</div>';
                return;
            }

            let html = '';
            branchRulesData.forEach((rule, ruleIdx) => {
                html += renderBranchRuleItem(rule, ruleIdx);
            });
            container.innerHTML = html;
        }
        window.renderBranchRules = renderBranchRules;

        // 渲染單一規則項目
        function renderBranchRuleItem(rule, ruleIdx) {
            const conditions = rule.conditions || [];
            const targetEdges = rule.target_edges || [];
            const ruleName = rule.name || `規則 ${ruleIdx + 1}`;

            // 建立出線選項 HTML
            let edgeOptionsHtml = '';
            branchOutgoingEdges.forEach(edge => {
                const checked = targetEdges.includes(edge.id) ? 'checked' : '';
                edgeOptionsHtml += `
                    <label style="display: flex; align-items: center; gap: 4px; font-size: 10px; padding: 2px 0; cursor: pointer;">
                        <input type="checkbox" ${checked}
                               onchange="updateBranchRuleTarget(${ruleIdx}, '${edge.id}', this.checked)"
                               style="margin: 0;">
                        <span>${edge.displayText}</span>
                    </label>
                `;
            });

            let conditionsHtml = '';
            conditions.forEach((cond, condIdx) => {
                conditionsHtml += renderBranchConditionItem(ruleIdx, condIdx, cond, condIdx < conditions.length - 1);
            });

            return `
                <div style="border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 8px; background: #fafafa;">
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; background: #f0f9f0; border-radius: 6px 6px 0 0; border-bottom: 1px solid #e0e0e0;">
                        <input type="text" value="${ruleName}" placeholder="規則名稱"
                               onchange="updateBranchRuleName(${ruleIdx}, this.value)"
                               style="border: none; background: transparent; font-weight: bold; color: #16A34A; font-size: 11px; width: 120px;">
                        <div style="display: flex; gap: 4px;">
                            <button onclick="addBranchCondition(${ruleIdx})" style="padding: 2px 6px; font-size: 9px; border: 1px solid #16A34A; background: white; color: #16A34A; border-radius: 3px; cursor: pointer;">+條件</button>
                            <button onclick="removeBranchRule(${ruleIdx})" style="padding: 2px 6px; font-size: 9px; border: 1px solid #DC2626; background: white; color: #DC2626; border-radius: 3px; cursor: pointer;">×</button>
                        </div>
                    </div>
                    <div style="padding: 8px;">
                        <div style="margin-bottom: 6px;">
                            ${conditionsHtml || '<div style="color: #999; font-size: 10px;">無條件（永遠符合）</div>'}
                        </div>
                        <div style="border-top: 1px dashed #ddd; padding-top: 6px;">
                            <div style="font-size: 10px; color: #666; margin-bottom: 4px;">目標路徑（可多選）：</div>
                            <div style="max-height: 80px; overflow-y: auto;">
                                ${edgeOptionsHtml || '<div style="color: #999; font-size: 10px;">此節點尚無出線</div>'}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // 渲染單一條件
        function renderBranchConditionItem(ruleIdx, condIdx, cond, hasNext) {
            const variable = cond.variable || '';
            const operator = cond.operator || '==';
            const value = cond.value || '';
            const logic = cond.logic || 'AND';

            const operators = [
                { val: '==', label: '==' },
                { val: '!=', label: '!=' },
                { val: '>', label: '>' },
                { val: '>=', label: '>=' },
                { val: '<', label: '<' },
                { val: '<=', label: '<=' },
                { val: 'contains', label: '包含' },
                { val: 'not_contains', label: '不含' },
                { val: 'startswith', label: '開頭' },
                { val: 'endswith', label: '結尾' },
                { val: 'in', label: '在' },
                { val: 'not_in', label: '不在' },
                { val: 'empty', label: '空' },
                { val: 'not_empty', label: '非空' },
                { val: 'matches', label: '正則' }
            ];

            let opOptions = operators.map(op =>
                `<option value="${op.val}" ${operator === op.val ? 'selected' : ''}>${op.label}</option>`
            ).join('');

            const showValue = !['empty', 'not_empty'].includes(operator);

            return `
                <div style="display: flex; gap: 4px; align-items: center; margin-bottom: 4px; flex-wrap: wrap;">
                    <input type="text" id="branch_var_${ruleIdx}_${condIdx}" value="${variable}" placeholder="\${v.name}"
                           onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'variable', this.value)"
                           style="width: 70px; padding: 3px 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px; font-family: monospace;">
                    <button type="button" onclick="VarPicker.open(this, document.getElementById('branch_var_${ruleIdx}_${condIdx}'))" style="padding:0 4px;font-size:10px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;line-height:18px;" title="插入變數">{x}</button>
                    <select onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'operator', this.value)"
                            style="padding: 3px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px;">
                        ${opOptions}
                    </select>
                    ${showValue ? `
                        <input type="text" id="branch_val_${ruleIdx}_${condIdx}" value="${value}" placeholder="值"
                               onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'value', this.value)"
                               style="width: 60px; padding: 3px 4px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px;">
                        <button type="button" onclick="VarPicker.open(this, document.getElementById('branch_val_${ruleIdx}_${condIdx}'))" style="padding:0 4px;font-size:10px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;line-height:18px;" title="插入變數">{x}</button>
                    ` : ''}
                    ${hasNext ? `
                        <select onchange="updateBranchCondition(${ruleIdx}, ${condIdx}, 'logic', this.value)"
                                style="padding: 3px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 10px; background: ${logic === 'OR' ? '#fef3c7' : '#dcfce7'};">
                            <option value="AND" ${logic === 'AND' ? 'selected' : ''}>AND</option>
                            <option value="OR" ${logic === 'OR' ? 'selected' : ''}>OR</option>
                        </select>
                    ` : ''}
                    <button onclick="removeBranchCondition(${ruleIdx}, ${condIdx})"
                            style="padding: 2px 5px; font-size: 9px; border: 1px solid #999; background: white; color: #666; border-radius: 3px; cursor: pointer;">×</button>
                </div>
            `;
        }

        // 新增規則
        function addBranchRule() {
            branchRulesData.push({
                name: `規則 ${branchRulesData.length + 1}`,
                conditions: [{ variable: '${status}', operator: '==', value: '' }],
                target_edges: []
            });
            renderBranchRules(branchRulesData, branchCurrentNodeId);
        }
        window.addBranchRule = addBranchRule;

        // 移除規則
        function removeBranchRule(ruleIdx) {
            branchRulesData.splice(ruleIdx, 1);
            renderBranchRules(branchRulesData, branchCurrentNodeId);
        }
        window.removeBranchRule = removeBranchRule;

        // 更新規則名稱
        function updateBranchRuleName(ruleIdx, name) {
            if (branchRulesData[ruleIdx]) {
                branchRulesData[ruleIdx].name = name;
            }
        }
        window.updateBranchRuleName = updateBranchRuleName;

        // 新增條件
        function addBranchCondition(ruleIdx) {
            if (branchRulesData[ruleIdx]) {
                if (!branchRulesData[ruleIdx].conditions) {
                    branchRulesData[ruleIdx].conditions = [];
                }
                branchRulesData[ruleIdx].conditions.push({
                    variable: '',
                    operator: '==',
                    value: '',
                    logic: 'AND'
                });
                renderBranchRules(branchRulesData, branchCurrentNodeId);
            }
        }
        window.addBranchCondition = addBranchCondition;

        // 移除條件
        function removeBranchCondition(ruleIdx, condIdx) {
            if (branchRulesData[ruleIdx] && branchRulesData[ruleIdx].conditions) {
                branchRulesData[ruleIdx].conditions.splice(condIdx, 1);
                renderBranchRules(branchRulesData, branchCurrentNodeId);
            }
        }
        window.removeBranchCondition = removeBranchCondition;

        // 更新條件
        function updateBranchCondition(ruleIdx, condIdx, field, value) {
            if (branchRulesData[ruleIdx] && branchRulesData[ruleIdx].conditions[condIdx]) {
                branchRulesData[ruleIdx].conditions[condIdx][field] = value;

                // 如果運算符改變，可能需要重新渲染（empty/not_empty 不需要 value）
                if (field === 'operator') {
                    renderBranchRules(branchRulesData, branchCurrentNodeId);
                }
            }
        }
        window.updateBranchCondition = updateBranchCondition;

        // 更新規則目標
        function updateBranchRuleTarget(ruleIdx, edgeId, checked) {
            if (branchRulesData[ruleIdx]) {
                if (!branchRulesData[ruleIdx].target_edges) {
                    branchRulesData[ruleIdx].target_edges = [];
                }
                if (checked) {
                    if (!branchRulesData[ruleIdx].target_edges.includes(edgeId)) {
                        branchRulesData[ruleIdx].target_edges.push(edgeId);
                    }
                } else {
                    branchRulesData[ruleIdx].target_edges = branchRulesData[ruleIdx].target_edges.filter(id => id !== edgeId);
                }
            }
        }
        window.updateBranchRuleTarget = updateBranchRuleTarget;

        // 切換 fallback 選項顯示
        function toggleBranchFallbackOptions() {
            const action = document.getElementById('branchFallbackAction')?.value;
            const msgInput = document.getElementById('branchFallbackMessage');
            const targetSelect = document.getElementById('branchFallbackTarget');

            if (msgInput) msgInput.style.display = action === 'route' ? 'none' : 'block';
            if (targetSelect) targetSelect.style.display = action === 'route' ? 'block' : 'none';
        }
        window.toggleBranchFallbackOptions = toggleBranchFallbackOptions;

        // 套用 BRANCH 設定
        function applyBranchConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const fallbackAction = document.getElementById('branchFallbackAction')?.value || 'log';
            const fallbackMessage = document.getElementById('branchFallbackMessage')?.value || __('無匹配規則');
            const fallbackTarget = document.getElementById('branchFallbackTarget')?.value || '';

            // 清理規則資料
            const cleanedRules = branchRulesData.map(rule => {
                const cleanRule = {
                    name: rule.name || '',
                    conditions: (rule.conditions || []).filter(c => c.variable),
                    target_edges: rule.target_edges || []
                };
                return cleanRule;
            }).filter(rule => rule.conditions.length > 0 || rule.target_edges.length > 0);

            const fallback = {
                action: fallbackAction
            };
            if (fallbackAction === 'log') {
                fallback.log_message = fallbackMessage;
            }
            if (fallbackAction === 'route' && fallbackTarget) {
                fallback.target_edge = fallbackTarget;
            }

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                rules: cleanedRules,
                fallback: fallback
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ BRANCH 設定已套用（${cleanedRules.length} 條規則）`, 'success');

            console.log('BRANCH 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyBranchConfig = applyBranchConfig;

        // BRANCH 說明頁籤切換
        function switchBranchHelpTab(tab) {
            ['Ops', 'Logic', 'Examples'].forEach(t => {
                const btn = document.getElementById('branchTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
                const content = document.getElementById('branchContent' + t);
                if (content) content.style.display = 'none';
            });

            const tabMap = { 'ops': 'Ops', 'logic': 'Logic', 'examples': 'Examples' };
            const activeBtn = document.getElementById('branchTab' + tabMap[tab]);
            const activeContent = document.getElementById('branchContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#16A34A';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchBranchHelpTab = switchBranchHelpTab;
