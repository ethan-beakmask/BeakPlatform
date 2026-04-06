/**
 * wf-node-opset.js -- OPSET 變數設定節點配置
 * 從 wf-node-configs.js 拆分
 */

        // OPSET 操作列表暫存
        let opsetOperationsTemp = [];

        // 渲染 OPSET 操作列表
        function renderOpsetOperations(operations) {
            opsetOperationsTemp = operations ? [...operations] : [];
            const container = document.getElementById('opsetOperationsList');
            if (!container) return;

            if (opsetOperationsTemp.length === 0) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 12px; color: #999; font-size: 11px;">
                        <i class="fas fa-info-circle"></i> 點擊「新增」開始設定
                    </div>
                `;
                return;
            }

            let html = '';
            opsetOperationsTemp.forEach((op, idx) => {
                html += renderOpsetOperationItem(op, idx);
            });
            container.innerHTML = html;
        }

        // 渲染單一操作項目
        function renderOpsetOperationItem(op, idx) {
            const operationOptions = [
                { value: 'set', label: '=' },
                { value: 'expr', label: '運算' },
                { value: 'add', label: '+' },
                { value: 'subtract', label: '-' },
                { value: 'multiply', label: '×' },
                { value: 'divide', label: '÷' },
                { value: 'concat', label: '連接' },
                { value: 'increment', label: '+1' },
                { value: 'decrement', label: '-1' }
            ];

            const optionsHtml = operationOptions.map(o =>
                `<option value="${o.value}" ${op.operation === o.value ? 'selected' : ''}>${o.label}</option>`
            ).join('');

            const needsValue = !['increment', 'decrement'].includes(op.operation);

            return `
                <div style="border: 1px solid #ddd; border-radius: 4px; padding: 6px; margin-bottom: 6px; background: #fafafa;">
                    <div style="display: flex; gap: 4px; align-items: center; margin-bottom: ${needsValue ? '4px' : '0'};">
                        <input type="text" id="opset_target_${idx}" value="${op.target_var || ''}"
                               placeholder="變數名"
                               onchange="updateOpsetOperation(${idx}, 'target_var', this.value)"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; font-family: monospace;">
                        <select id="opset_op_${idx}" onchange="updateOpsetOperation(${idx}, 'operation', this.value); updateOpsetValueVisibility(${idx})"
                                style="width: 55px; padding: 4px 2px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; text-align: center;">
                            ${optionsHtml}
                        </select>
                        <button onclick="removeOpsetOperation(${idx})" style="background: none; border: none; color: #dc3545; cursor: pointer; font-size: 12px; padding: 2px 4px;" title="刪除">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div id="opset_value_container_${idx}" style="display: ${needsValue ? 'block' : 'none'};">
                        <div style="display:flex;align-items:center;margin-bottom:2px;">
                            <span style="font-size:10px;color:#999;">值</span>
                            <button type="button" onclick="VarPicker.open(this, document.getElementById('opset_value_${idx}'))" style="margin-left:auto;padding:1px 5px;font-size:10px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                        </div>
                        <textarea id="opset_value_${idx}" rows="2"
                               placeholder="值或 \${v.name}，支援多行"
                               onchange="updateOpsetOperation(${idx}, 'value', this.value)"
                               style="width: 100%; padding: 4px 6px; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; font-family: monospace; resize: vertical;">${op.value !== undefined ? op.value : ''}</textarea>
                    </div>
                </div>
            `;
        }

        // 新增操作
        function addOpsetOperation() {
            opsetOperationsTemp.push({
                target_var: '',
                operation: 'set',
                value: ''
            });
            renderOpsetOperations(opsetOperationsTemp);
        }
        window.addOpsetOperation = addOpsetOperation;

        // 刪除操作
        function removeOpsetOperation(idx) {
            opsetOperationsTemp.splice(idx, 1);
            renderOpsetOperations(opsetOperationsTemp);
        }
        window.removeOpsetOperation = removeOpsetOperation;

        // 更新操作屬性
        function updateOpsetOperation(idx, field, value) {
            if (opsetOperationsTemp[idx]) {
                opsetOperationsTemp[idx][field] = value;
            }
        }
        window.updateOpsetOperation = updateOpsetOperation;

        // 更新值輸入框可見性
        function updateOpsetValueVisibility(idx) {
            const opSelect = document.getElementById(`opset_op_${idx}`);
            const valueContainer = document.getElementById(`opset_value_container_${idx}`);
            if (opSelect && valueContainer) {
                const needsValue = !['increment', 'decrement'].includes(opSelect.value);
                valueContainer.style.display = needsValue ? 'block' : 'none';
            }
        }
        window.updateOpsetValueVisibility = updateOpsetValueVisibility;

        // 套用 OPSET 設定
        function applyOpsetConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 驗證操作
            const validOperations = [];
            let hasError = false;
            const seenVarNames = new Set();  // 用於檢查重複變數名稱

            opsetOperationsTemp.forEach((op, idx) => {
                if (!op.target_var || !op.target_var.trim()) {
                    updateStatus(`操作 ${idx + 1} 缺少目標變數名稱`, 'warning');
                    hasError = true;
                    return;
                }

                const varName = op.target_var.trim();

                // 檢查同一節點內是否有重複變數名稱
                if (seenVarNames.has(varName)) {
                    updateStatus(`❌ 變數名稱「${varName}」重複，同一節點內不可有相同名稱的變數`, 'error');
                    hasError = true;
                    return;
                }
                seenVarNames.add(varName);

                const needsValue = !['increment', 'decrement'].includes(op.operation);
                if (needsValue && (op.value === undefined || op.value === '')) {
                    updateStatus(`操作 ${idx + 1} 缺少值`, 'warning');
                    hasError = true;
                    return;
                }

                validOperations.push({
                    target_var: varName,
                    operation: op.operation,
                    value: op.value
                });
            });

            if (hasError) {
                // 自動切換到常用控制分頁，讓用戶看到錯誤訊息
                if (typeof switchTab === 'function') {
                    switchTab('canvas');
                }
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                operations: validOperations
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 變數設定已套用：${validOperations.length} 個操作`, 'success');

            console.log('OPSET 節點配置已更新:', {
                nodeId: nodeId,
                operations: validOperations,
                config: updatedConfig
            });
        }
        window.applyOpsetConfig = applyOpsetConfig;

        // OPSET 說明頁籤切換
        function switchOpsetHelpTab(tab) {
            // 重置所有頁籤按鈕
            ['Ops', 'Examples', 'Vars'].forEach(t => {
                const btn = document.getElementById('opsetTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
            });
            // 隱藏所有內容
            ['Ops', 'Examples', 'Vars'].forEach(t => {
                const content = document.getElementById('opsetContent' + t);
                if (content) content.style.display = 'none';
            });

            // 顯示選中的頁籤
            const tabMap = { 'ops': 'Ops', 'examples': 'Examples', 'vars': 'Vars' };
            const activeBtn = document.getElementById('opsetTab' + tabMap[tab]);
            const activeContent = document.getElementById('opsetContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#EC4899';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchOpsetHelpTab = switchOpsetHelpTab;
