/**
 * wf-node-configs.js -- 節點類型配置
 * 從 workflow-main.js 拆分
 * 包含: ParallelJoin, FieldWrite, OPSET, SQLExecutor, Telegram, SysTelegram,
 *        EmailRelay, NavbarBroadcast, AlertBroadcast, EmailAdapter, BRANCH, Assignee
 */

        // ==================== ParallelJoin 並行匯合函數 ====================

        function toggleParallelJoinTimeout() {
            const checkbox = document.getElementById('pjEnableTimeout');
            const settingsDiv = document.getElementById('pjTimeoutSettings');
            if (checkbox && settingsDiv) {
                settingsDiv.style.display = checkbox.checked ? 'block' : 'none';
            }
        }
        window.toggleParallelJoinTimeout = toggleParallelJoinTimeout;

        function applyParallelJoinConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const enableTimeout = document.getElementById('pjEnableTimeout')?.checked || false;
            let timeoutMinutes = 0;
            let timeoutEdgeId = '';

            if (enableTimeout) {
                const minutesInput = document.getElementById('pjTimeoutMinutes');
                timeoutMinutes = parseInt(minutesInput?.value, 10);

                if (isNaN(timeoutMinutes) || timeoutMinutes < 1) {
                    updateStatus('逾時時間必須至少 1 分鐘', 'warning');
                    return;
                }
                if (timeoutMinutes > 14400) {
                    updateStatus('逾時時間不能超過 14400 分鐘（10 天）', 'warning');
                    return;
                }

                const edgeSelect = document.getElementById('pjTimeoutEdgeId');
                timeoutEdgeId = edgeSelect?.value || '';

                if (!timeoutEdgeId) {
                    updateStatus('啟用逾時時必須指定逾時去向', 'warning');
                    return;
                }
            }

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                enable_timeout: enableTimeout,
                timeout_minutes: enableTimeout ? timeoutMinutes : 0,
                timeout_edge_id: enableTimeout ? timeoutEdgeId : ''
            };

            node.data('config', updatedConfig);

            if (enableTimeout) {
                updateStatus(`並行匯合設定已套用：逾時 ${timeoutMinutes} 分鐘`, 'success');
            } else {
                updateStatus('並行匯合設定已套用：無逾時限制', 'success');
            }

            console.log('ParallelJoin 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyParallelJoinConfig = applyParallelJoinConfig;

        // ==================== OP_FIELDWRITE 表單寫值函數 ====================

        // 載入目標欄位選項（從綁定的表單取得）
        async function loadFieldWriteTargetFields(selectedValue, retryCount = 0) {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 如果 selectedValue 是 ${...} 格式，嘗試提取欄位名稱
            let cleanSelectedValue = selectedValue || '';
            if (cleanSelectedValue.startsWith('${') && cleanSelectedValue.endsWith('}')) {
                // 嘗試提取欄位名，例如 ${FORMCODE_fieldKey} 或 ${form.fieldKey}
                const inner = cleanSelectedValue.slice(2, -1);
                if (inner.startsWith('form.')) {
                    cleanSelectedValue = inner.slice(5);
                } else if (inner.includes('_')) {
                    // ${FORMCODE_fieldKey} 格式，取最後一個 _ 後面的部分
                    cleanSelectedValue = inner.split('_').pop();
                }
            }

            // 如果欄位尚未載入，等待並重試（最多重試 5 次）
            if (currentFormFields.length === 0 && retryCount < 5) {
                select.innerHTML = '<option value="">載入中...</option>';
                setTimeout(() => loadFieldWriteTargetFields(selectedValue, retryCount + 1), 300);
                return;
            }

            try {
                // 從已載入的表單欄位快取取得
                let fields = [];

                // 優先使用目前已載入的表單欄位
                if (currentFormFields && currentFormFields.length > 0) {
                    fields = currentFormFields;
                }

                // 如果沒有快取，嘗試從 triggerFormData 取得
                if (fields.length === 0 && window.triggerFormData && window.triggerFormData.schema) {
                    fields = extractFieldsFromSchema(window.triggerFormData.schema);
                }

                // 如果還是沒有，顯示手動輸入提示
                if (fields.length === 0) {
                    let options = '<option value="">請先選擇表單以載入欄位...</option>';
                    if (cleanSelectedValue) {
                        options = `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue}</option>`;
                    }
                    select.innerHTML = options;
                    return;
                }

                // 建構選項（顯示新式變數格式）
                let options = '<option value="">選擇目標欄位...</option>';

                // 取得表單 secure_code（從 selectedFormSecureCode 或 currentMappedForms）
                let formSecureCode = selectedFormSecureCode || null;
                if (!formSecureCode && currentMappedForms && currentMappedForms.length > 0) {
                    formSecureCode = currentMappedForms[0].form_secure_code;
                }

                fields.forEach(field => {
                    const key = field.key || field.name;
                    const label = field.label || key;
                    const selected = cleanSelectedValue === key ? 'selected' : '';

                    // 嘗試取得新式變數顯示
                    let displayName = label;
                    if (window.variableMapping && window.variableMapping.forward && formSecureCode) {
                        const internalKey = `${formSecureCode}_${key}`;
                        const displayVar = window.variableMapping.forward[internalKey];
                        if (displayVar) {
                            // 顯示新式變數格式（去掉 ${}）
                            displayName = displayVar.replace(/^\$\{/, '').replace(/\}$/, '');
                        }
                    }

                    options += `<option value="${key}" ${selected}>${displayName}</option>`;
                });

                select.innerHTML = options;

                // 如果有舊值且不在選項中，加入手動輸入選項
                if (cleanSelectedValue && !fields.find(f => (f.key || f.name) === cleanSelectedValue)) {
                    select.innerHTML += `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue} (手動輸入)</option>`;
                }

            } catch (error) {
                console.error('載入目標欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadFieldWriteTargetFields = loadFieldWriteTargetFields;

        /**
         * 重新載入 OP_FIELDWRITE 的目標欄位選項
         * - 優先使用用戶當前選擇的表單
         * - 如果沒有選擇，使用第一張配對表單
         * - 如果沒有配對表單，顯示提示訊息
         */
        async function reloadFieldWriteTargetFields() {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 檢查是否有配對表單
            if (!currentMappedForms || currentMappedForms.length === 0) {
                select.innerHTML = '<option value="">需要配對表單</option>';
                updateStatus('⚠ 請先在表單欄位分頁配對表單');
                return;
            }

            // 選擇表單：優先使用已選擇的，否則用第一張
            let targetForm = null;
            if (selectedFormId) {
                targetForm = currentMappedForms.find(f => f.form_id === selectedFormId);
            }
            if (!targetForm) {
                targetForm = currentMappedForms[0];
            }

            // 顯示載入中
            select.innerHTML = '<option value="">載入中...</option>';

            try {
                // 載入表單欄位（這也會更新 currentFormFields）
                await selectForm(targetForm);

                // 現在欄位應該已經載入，重新載入下拉選單
                const currentValue = select.value;
                await loadFieldWriteTargetFields(currentValue);

                updateStatus(`✅ 已載入表單「${targetForm.form_name}」的欄位`);
            } catch (error) {
                console.error('重新載入欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
                updateStatus('❌ 載入欄位失敗: ' + error.message);
            }
        }
        window.reloadFieldWriteTargetFields = reloadFieldWriteTargetFields;

        // 從 form.io schema 解析欄位列表
        function extractFieldsFromSchema(schema) {
            const fields = [];
            if (!schema || !schema.components) return fields;

            function extractFromComponents(components) {
                for (const comp of components) {
                    // 跳過容器類型元件（只處理實際欄位）
                    if (comp.type === 'button' || comp.type === 'htmlelement' || comp.type === 'content') {
                        continue;
                    }

                    // 如果有 key，視為欄位
                    if (comp.key && !comp.key.startsWith('panel') && !comp.key.startsWith('columns')) {
                        fields.push({
                            key: comp.key,
                            label: comp.label || comp.key,
                            type: comp.type
                        });
                    }

                    // 遞迴處理巢狀元件
                    if (comp.components) {
                        extractFromComponents(comp.components);
                    }
                    if (comp.columns) {
                        for (const col of comp.columns) {
                            if (col.components) {
                                extractFromComponents(col.components);
                            }
                        }
                    }
                }
            }

            extractFromComponents(schema.components);
            return fields;
        }
        window.extractFieldsFromSchema = extractFieldsFromSchema;

        function applyFieldWriteConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const targetFieldInput = document.getElementById('fieldWriteTargetField');
            const contentInput = document.getElementById('fieldWriteContent');
            const contentTypeRadio = document.querySelector('input[name="fieldWriteContentType"]:checked');

            if (!targetFieldInput || !contentInput) {
                updateStatus('找不到輸入欄位', 'warning');
                return;
            }

            const targetField = targetFieldInput.value.trim();
            const content = contentInput.value;
            const contentType = contentTypeRadio ? contentTypeRadio.value : 'text';

            // 驗證必填
            if (!targetField) {
                updateStatus('請輸入目標欄位 Key', 'warning');
                targetFieldInput.focus();
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                target_field: targetField,
                content: content,
                content_type: contentType
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 表單寫值設定已套用：${targetField}`, 'success');

            console.log('OP_FIELDWRITE 節點配置已更新:', {
                nodeId: nodeId,
                target_field: targetField,
                content_type: contentType,
                content_length: content.length,
                config: updatedConfig
            });
        }
        window.applyFieldWriteConfig = applyFieldWriteConfig;

        // ==================== OPSET 變數設定函數 ====================

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

        // ==================== SQLExecutor 相關函數 ====================

        // SQL 查詢類型描述
        const sqlQueryDescriptions = {
            'get_org_users': '查詢同企業的所有用戶，回傳 id、display_name、email 欄位，結果為陣列。',
            'get_org_user_count': '統計同企業的用戶總數，回傳單一數值 user_count。',
            'get_org_active_users': '查詢同企業最近 30 天有登入的活躍用戶，回傳 id、display_name、email、last_login_at 欄位。'
        };

        // 更新 SQL 查詢描述
        function updateSQLQueryDescription() {
            const select = document.getElementById('sqlQueryType');
            const descDiv = document.getElementById('sqlQueryDescription');
            if (!select || !descDiv) return;

            const queryType = select.value;
            if (queryType && sqlQueryDescriptions[queryType]) {
                descDiv.textContent = sqlQueryDescriptions[queryType];
                descDiv.style.color = '#333';
            } else {
                descDiv.textContent = '請選擇查詢類型';
                descDiv.style.color = '#666';
            }
        }
        window.updateSQLQueryDescription = updateSQLQueryDescription;

        // SQLExecutor 配置套用
        function applySQLExecutorConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 取得設定值
            const queryType = document.getElementById('sqlQueryType')?.value;
            const resultVar = document.getElementById('sqlResultVar')?.value?.trim();

            // 驗證
            if (!queryType) {
                updateStatus('❌ 請選擇查詢類型', 'error');
                return;
            }

            if (!resultVar) {
                updateStatus('❌ 請輸入結果變數名稱', 'error');
                return;
            }

            // 驗證變數名稱格式（只允許英文、數字、底線，不能以數字開頭）
            if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(resultVar)) {
                updateStatus('❌ 變數名稱格式不正確（只能使用英文、數字、底線，且不能以數字開頭）', 'error');
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                query_type: queryType,
                result_var: resultVar
            };

            node.data('config', updatedConfig);

            const queryName = sqlQueryDescriptions[queryType] ? queryType : '未知查詢';
            updateStatus(`✅ SQL 查詢設定已套用：${queryName} → $\{${resultVar}}`, 'success');

            console.log('SQLExecutor 節點配置已更新:', {
                nodeId: nodeId,
                query_type: queryType,
                result_var: resultVar,
                config: updatedConfig
            });

            // 自動儲存當前流程
            saveWorkflow().then(() => {
                console.log('✅ 流程已自動儲存');
            }).catch(err => {
                console.error('⚠️ 自動儲存失敗:', err);
            });
        }
        window.applySQLExecutorConfig = applySQLExecutorConfig;

        // ==================== Telegram 相關函數 ====================

        // Telegram 設定組快取
        let telegramConfigsCache = null;

        // 載入可用的 Telegram 設定組
        async function loadTelegramConfigs(selectedConfigId, selectedChannelName) {
            const configSelect = document.getElementById('telegramConfigId');
            if (!configSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/telegram/available');
                if (!response.ok) {
                    configSelect.innerHTML = '<option value="">無法載入設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    configSelect.innerHTML = '<option value="">沒有可用的設定</option>';
                    return;
                }

                telegramConfigsCache = data.data.configs;

                // 建構選項
                let options = '<option value="">請選擇設定組...</option>';
                data.data.configs.forEach(config => {
                    const isSystemLabel = config.is_system ? ' (系統)' : '';
                    const selected = selectedConfigId && config.id == selectedConfigId ? 'selected' : '';
                    // 從 channels 物件取得頻道名稱陣列（與系統級一致）
                    const channelNames = Object.keys(config.channels || {});
                    options += `<option value="${config.id}" data-channels='${JSON.stringify(channelNames)}' data-default-channel="${config.default_channel || ''}" ${selected}>${config.name}${isSystemLabel}</option>`;
                });
                configSelect.innerHTML = options;

                // 如果有預選的 config，觸發更新頻道列表
                if (selectedConfigId) {
                    updateTelegramChannels(selectedChannelName);
                }
            } catch (error) {
                console.error('載入 Telegram 設定失敗:', error);
                configSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadTelegramConfigs = loadTelegramConfigs;

        // 更新頻道列表
        function updateTelegramChannels(preselectedChannel) {
            const configSelect = document.getElementById('telegramConfigId');
            const channelSelect = document.getElementById('telegramChannelName');
            if (!configSelect || !channelSelect) return;

            const selectedOption = configSelect.options[configSelect.selectedIndex];
            if (!selectedOption || !selectedOption.value) {
                channelSelect.innerHTML = '<option value="">請先選擇 Bot 設定組...</option>';
                return;
            }

            try {
                const channels = JSON.parse(selectedOption.dataset.channels || '[]');
                if (channels.length === 0) {
                    channelSelect.innerHTML = '<option value="">此設定組沒有頻道</option>';
                    return;
                }

                // 取得預設頻道（來自 API 回傳）
                const defaultChannel = selectedOption.dataset.defaultChannel || '';

                // 決定要自動選擇的頻道：
                // 1. 如果有預選頻道（節點已有配置），使用預選的
                // 2. 否則，如果只有一個頻道，自動選擇該頻道
                // 3. 否則，如果有預設頻道，使用預設頻道
                let autoSelectChannel = preselectedChannel;
                if (!autoSelectChannel) {
                    if (channels.length === 1) {
                        autoSelectChannel = channels[0];
                    } else if (defaultChannel && channels.includes(defaultChannel)) {
                        autoSelectChannel = defaultChannel;
                    }
                }

                let options = '<option value="">請選擇頻道...</option>';
                channels.forEach(channel => {
                    const selected = autoSelectChannel === channel ? 'selected' : '';
                    // 標示預設頻道
                    const label = channel === defaultChannel ? `${channel} ★` : channel;
                    options += `<option value="${channel}" ${selected}>${label}</option>`;
                });
                channelSelect.innerHTML = options;
            } catch (error) {
                console.error('解析頻道失敗:', error);
                channelSelect.innerHTML = '<option value="">解析失敗</option>';
            }
        }
        window.updateTelegramChannels = updateTelegramChannels;

        // 套用 Telegram 節點配置
        function applyTelegramConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const configId = document.getElementById('telegramConfigId')?.value;
            const channelName = document.getElementById('telegramChannelName')?.value;
            const message = document.getElementById('telegramMessage')?.value;
            const parseMode = document.getElementById('telegramParseMode')?.value || 'HTML';
            const disableNotification = document.getElementById('telegramDisableNotification')?.checked || false;
            const disableWebPagePreview = document.getElementById('telegramDisableWebPagePreview')?.checked || false;

            // 驗證必填項
            if (!configId) {
                updateStatus('請選擇 Bot 設定組', 'warning');
                return;
            }
            if (!channelName) {
                updateStatus('請選擇頻道', 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus('請輸入訊息內容', 'warning');
                return;
            }

            // 更新節點 config（config_id 是 secure_code 字串，不能 parseInt）
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                config_id: configId,
                channel_name: channelName,
                message: message.trim(),
                parse_mode: parseMode,
                disable_notification: disableNotification,
                disable_web_page_preview: disableWebPagePreview
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ Telegram 設定已套用`, 'success');

            console.log('Telegram 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyTelegramConfig = applyTelegramConfig;

        // ==================== 系統級 Telegram (SYS_Telegram) ====================

        // 系統級 Telegram 設定組快取
        let sysTelegramConfigsCache = null;

        // 載入系統級 Telegram 設定組
        async function loadSysTelegramConfigs(selectedConfigId, selectedChannelName) {
            const configSelect = document.getElementById('sysTelegramConfigId');
            if (!configSelect) return;

            try {
                // 呼叫系統級 API（只回傳 org_secure_code 為 NULL 的設定）
                const response = await fetch('/api/system/data/settings/telegram');
                if (!response.ok) {
                    configSelect.innerHTML = '<option value="">無法載入設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    configSelect.innerHTML = '<option value="">沒有系統級設定</option>';
                    return;
                }

                sysTelegramConfigsCache = data.data.configs;

                // 建構選項
                let options = '<option value="">請選擇設定組...</option>';
                data.data.configs.forEach(config => {
                    const selected = selectedConfigId && config.id == selectedConfigId ? 'selected' : '';
                    // 從 channels 物件取得頻道名稱陣列
                    const channelNames = Object.keys(config.channels || {});
                    options += `<option value="${config.id}" data-channels='${JSON.stringify(channelNames)}' ${selected}>${config.name}</option>`;
                });
                configSelect.innerHTML = options;

                // 如果有預選的 config，觸發更新頻道列表
                if (selectedConfigId) {
                    updateSysTelegramChannels(selectedChannelName);
                }
            } catch (error) {
                console.error('載入系統級 Telegram 設定失敗:', error);
                configSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadSysTelegramConfigs = loadSysTelegramConfigs;

        // 更新系統級 Telegram 頻道列表
        function updateSysTelegramChannels(preselectedChannel) {
            const configSelect = document.getElementById('sysTelegramConfigId');
            const channelSelect = document.getElementById('sysTelegramChannelName');
            if (!configSelect || !channelSelect) return;

            const selectedOption = configSelect.options[configSelect.selectedIndex];
            if (!selectedOption || !selectedOption.value) {
                channelSelect.innerHTML = '<option value="">請先選擇 Bot 設定組...</option>';
                return;
            }

            try {
                const channels = JSON.parse(selectedOption.dataset.channels || '[]');
                if (channels.length === 0) {
                    channelSelect.innerHTML = '<option value="">此設定組沒有頻道</option>';
                    return;
                }

                let options = '<option value="">請選擇頻道...</option>';
                channels.forEach(channel => {
                    const selected = preselectedChannel === channel ? 'selected' : '';
                    options += `<option value="${channel}" ${selected}>${channel}</option>`;
                });
                channelSelect.innerHTML = options;
            } catch (error) {
                console.error('解析頻道失敗:', error);
                channelSelect.innerHTML = '<option value="">解析失敗</option>';
            }
        }
        window.updateSysTelegramChannels = updateSysTelegramChannels;

        // 套用系統級 Telegram 節點配置
        function applySysTelegramConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const configId = document.getElementById('sysTelegramConfigId')?.value;
            const channelName = document.getElementById('sysTelegramChannelName')?.value;
            const message = document.getElementById('sysTelegramMessage')?.value;
            const parseMode = document.getElementById('sysTelegramParseMode')?.value || 'HTML';
            const disableNotification = document.getElementById('sysTelegramDisableNotification')?.checked || false;
            const disableWebPagePreview = document.getElementById('sysTelegramDisableWebPagePreview')?.checked || false;

            // 驗證必填項
            if (!configId) {
                updateStatus('請選擇系統級 Bot 設定組', 'warning');
                return;
            }
            if (!channelName) {
                updateStatus('請選擇頻道', 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus('請輸入訊息內容', 'warning');
                return;
            }

            // 更新節點 config（config_id 是 secure_code 字串，不能 parseInt）
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                config_id: configId,
                channel_name: channelName,
                message: message.trim(),
                parse_mode: parseMode,
                disable_notification: disableNotification,
                disable_web_page_preview: disableWebPagePreview
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 系統級 Telegram 設定已套用`, 'success');

            console.log('SYS_Telegram 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applySysTelegramConfig = applySysTelegramConfig;

        // Telegram 格式說明頁籤切換
        function switchTgFormatTab(tab) {
            // 重置所有頁籤按鈕
            ['Html', 'Md', 'Md2'].forEach(t => {
                const btn = document.getElementById('tgTab' + t);
                if (btn) {
                    btn.style.background = 'transparent';
                    btn.style.color = '#666';
                }
            });
            // 隱藏所有內容
            ['Html', 'Md', 'Md2'].forEach(t => {
                const content = document.getElementById('tgContent' + t);
                if (content) content.style.display = 'none';
            });

            // 顯示選中的頁籤
            const tabMap = { 'html': 'Html', 'md': 'Md', 'md2': 'Md2' };
            const activeBtn = document.getElementById('tgTab' + tabMap[tab]);
            const activeContent = document.getElementById('tgContent' + tabMap[tab]);
            if (activeBtn) {
                activeBtn.style.background = '#667eea';
                activeBtn.style.color = 'white';
            }
            if (activeContent) activeContent.style.display = 'block';
        }
        window.switchTgFormatTab = switchTgFormatTab;

        // ============================================
        // EmailRelay 系統郵件節點函數
        // ============================================

        // 收件人群組快取
        let emailRelayGroupsCache = null;

        // 載入可用的收件人群組
        async function loadEmailRelayGroups(selectedIds) {
            const groupSelect = document.getElementById('emailRelayGroups');
            if (!groupSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/email-groups/available');
                if (!response.ok) {
                    groupSelect.innerHTML = '<option value="">無法載入群組</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.groups) {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                    return;
                }

                emailRelayGroupsCache = data.data.groups;

                // 建構選項
                let options = '';
                data.data.groups.forEach(group => {
                    const isSystem = group.scope === 'system' ? ' (系統)' : '';
                    const selected = selectedIds && selectedIds.includes(group.id) ? 'selected' : '';
                    options += `<option value="${group.id}" ${selected}>${group.name}${isSystem} (${group.recipient_count}人)</option>`;
                });

                if (options === '') {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                } else {
                    groupSelect.innerHTML = options;
                }
            } catch (error) {
                console.error('載入收件人群組失敗:', error);
                groupSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailRelayGroups = loadEmailRelayGroups;

        // 切換收件者類型欄位顯示
        function toggleEmailRelayRecipientFields() {
            const type = document.getElementById('emailRelayRecipientType')?.value;
            const groupField = document.getElementById('emailRelayGroupField');
            const manualField = document.getElementById('emailRelayManualField');

            if (groupField) groupField.style.display = type === 'group' ? 'block' : 'none';
            if (manualField) manualField.style.display = type === 'manual' ? 'block' : 'none';
        }
        window.toggleEmailRelayRecipientFields = toggleEmailRelayRecipientFields;

        // 套用 EmailRelay 節點配置
        function applyEmailRelayConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const recipientType = document.getElementById('emailRelayRecipientType')?.value || 'group';
            const subject = document.getElementById('emailRelaySubject')?.value;
            const body = document.getElementById('emailRelayBody')?.value;
            const bodyType = document.getElementById('emailRelayBodyType')?.value || 'plain';
            const priority = document.getElementById('emailRelayPriority')?.value || 'normal';
            const ccManual = document.getElementById('emailRelayCcManual')?.value || '';

            // 驗證必填項
            if (!subject || !subject.trim()) {
                updateStatus('請輸入郵件主旨', 'warning');
                return;
            }
            if (!body || !body.trim()) {
                updateStatus('請輸入郵件內容', 'warning');
                return;
            }

            // 收集收件者設定
            let recipientGroups = [];
            let recipientManual = '';

            if (recipientType === 'group') {
                const groupSelect = document.getElementById('emailRelayGroups');
                if (groupSelect) {
                    recipientGroups = Array.from(groupSelect.selectedOptions).map(opt => opt.value);
                }
                if (recipientGroups.length === 0) {
                    updateStatus('請選擇至少一個收件人群組', 'warning');
                    return;
                }
            } else if (recipientType === 'manual') {
                recipientManual = document.getElementById('emailRelayRecipientManual')?.value || '';
                if (!recipientManual.trim()) {
                    updateStatus('請輸入收件者 Email', 'warning');
                    return;
                }
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                recipient_type: recipientType,
                recipient_groups: recipientGroups,
                recipient_manual: recipientManual.trim(),
                cc_manual: ccManual.trim(),
                subject: subject.trim(),
                body: body.trim(),
                body_type: bodyType,
                priority: priority
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 系統郵件設定已套用`, 'success');

            console.log('EmailRelay 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyEmailRelayConfig = applyEmailRelayConfig;

        // ============================================
        // NavbarBroadcast 跑馬燈廣播節點函數
        // ============================================

        function toggleNbFields() {
            const mode = document.getElementById('nbMode')?.value;
            const startFields = document.getElementById('nbStartFields');
            if (startFields) {
                startFields.style.display = mode === 'end' ? 'none' : '';
            }
        }
        window.toggleNbFields = toggleNbFields;

        function applyNavbarBroadcastConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const mode = document.getElementById('nbMode')?.value || 'start';
            const broadcastCode = document.getElementById('nbBroadcastCode')?.value?.trim();

            if (!broadcastCode) {
                updateStatus('請輸入廣播代碼', 'warning');
                return;
            }

            const currentConfig = node.data('config') || {};
            const updatedConfig = { ...currentConfig, mode, broadcast_code: broadcastCode };

            if (mode === 'start') {
                const message = document.getElementById('nbMessage')?.value?.trim();
                if (!message) {
                    updateStatus('請輸入訊息內容', 'warning');
                    return;
                }
                updatedConfig.message = message;
                updatedConfig.text_color = document.getElementById('nbTextColor')?.value || '#000000';
                updatedConfig.bg_color = document.getElementById('nbBgColor')?.value || '#FDE047';
                updatedConfig.display_seconds = parseInt(document.getElementById('nbDisplaySeconds')?.value, 10) || 5;
                updatedConfig.duration_minutes = parseInt(document.getElementById('nbDurationMinutes')?.value, 10) || 0;
            }

            node.data('config', updatedConfig);
            updateStatus('跑馬燈廣播設定已套用', 'success');
        }
        window.applyNavbarBroadcastConfig = applyNavbarBroadcastConfig;

        // 預覽即時更新
        document.addEventListener('input', function(e) {
            if (['nbMessage', 'nbTextColor', 'nbBgColor'].includes(e.target?.id)) {
                const preview = document.getElementById('nbPreview');
                if (!preview) return;
                const msg = document.getElementById('nbMessage')?.value || '預覽：跑馬燈訊息';
                const tc = document.getElementById('nbTextColor')?.value || '#000000';
                const bg = document.getElementById('nbBgColor')?.value || '#FDE047';
                preview.textContent = msg;
                preview.style.color = tc;
                preview.style.backgroundColor = bg;
            }
        });

        // ============================================
        // AlertBroadcast 緊急廣播節點函數
        // ============================================

        function toggleAbTargetFields() {
            const targetType = document.getElementById('abTargetType')?.value;
            const fields = document.getElementById('abTargetFields');
            if (fields) {
                fields.style.display = targetType === 'specific' ? '' : 'none';
            }
        }
        window.toggleAbTargetFields = toggleAbTargetFields;

        function loadAlertBroadcastOptions(selectedRoles, selectedDepts) {
            // 載入角色
            fetch('/api/form-workflow/data/org-roles', {
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
            })
            .then(r => r.json())
            .then(data => {
                const sel = document.getElementById('abTargetRoles');
                if (!sel) return;
                sel.innerHTML = '';
                (data.roles || data.data || []).forEach(role => {
                    const opt = document.createElement('option');
                    opt.value = role.secure_code || role.code;
                    opt.textContent = role.name;
                    if (selectedRoles.includes(opt.value)) opt.selected = true;
                    sel.appendChild(opt);
                });
            })
            .catch(() => {});

            // 載入部門
            fetch('/api/form-workflow/data/org-departments', {
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
            })
            .then(r => r.json())
            .then(data => {
                const sel = document.getElementById('abTargetDepartments');
                if (!sel) return;
                sel.innerHTML = '';
                (data.departments || data.data || []).forEach(dept => {
                    const opt = document.createElement('option');
                    opt.value = dept.secure_code || dept.code;
                    opt.textContent = (dept.full_path || dept.name);
                    if (selectedDepts.includes(opt.value)) opt.selected = true;
                    sel.appendChild(opt);
                });
            })
            .catch(() => {});
        }
        window.loadAlertBroadcastOptions = loadAlertBroadcastOptions;

        function applyAlertBroadcastConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const broadcastCode = document.getElementById('abBroadcastCode')?.value?.trim();
            const title = document.getElementById('abTitle')?.value?.trim();
            const message = document.getElementById('abMessage')?.value?.trim();

            if (!broadcastCode) {
                updateStatus('請輸入廣播代碼', 'warning');
                return;
            }
            if (!title) {
                updateStatus('請輸入標題', 'warning');
                return;
            }

            const targetType = document.getElementById('abTargetType')?.value || 'all';
            const requireAck = document.getElementById('abRequireAck')?.checked ?? true;
            const includeChildren = document.getElementById('abIncludeChildren')?.checked ?? true;

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                broadcast_code: broadcastCode,
                title: title,
                message: message,
                target_type: targetType,
                require_ack: requireAck,
            };

            if (targetType === 'specific') {
                const rolesEl = document.getElementById('abTargetRoles');
                const deptsEl = document.getElementById('abTargetDepartments');
                updatedConfig.target_roles = rolesEl ? Array.from(rolesEl.selectedOptions).map(o => o.value) : [];
                updatedConfig.target_departments = deptsEl ? Array.from(deptsEl.selectedOptions).map(o => o.value) : [];
                updatedConfig.include_children = includeChildren;
            }

            node.data('config', updatedConfig);
            updateStatus('緊急廣播設定已套用', 'success');
        }
        window.applyAlertBroadcastConfig = applyAlertBroadcastConfig;

        // ============================================
        // EmailAdapter 企業郵件節點函數
        // ============================================

        // SMTP 設定快取
        let emailAdapterSmtpConfigsCache = null;

        // 載入可用的 SMTP 設定
        async function loadEmailAdapterSmtpConfigs(selectedId) {
            const smtpSelect = document.getElementById('emailAdapterSmtpConfig');
            if (!smtpSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/smtp/available');
                if (!response.ok) {
                    smtpSelect.innerHTML = '<option value="">無法載入 SMTP 設定</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.configs) {
                    smtpSelect.innerHTML = '<option value="">沒有可用的 SMTP 設定</option>';
                    return;
                }

                emailAdapterSmtpConfigsCache = data.data.configs;
                const configs = data.data.configs;

                // 如果只有一個設定且沒有指定選擇，自動選擇它
                let autoSelectId = null;
                if (configs.length === 1 && !selectedId) {
                    autoSelectId = configs[0].id;
                }

                // 建構選項
                let options = configs.length > 1 ? '<option value="">(使用預設設定)</option>' : '';
                configs.forEach(cfg => {
                    const isDefault = cfg.is_default ? ' ⭐預設' : '';
                    const provider = cfg.provider_type !== 'generic' ? ` [${cfg.provider_type}]` : '';
                    // 檢查是否被選中：明確選擇 > 自動選擇
                    const isSelected = (selectedId && String(selectedId) === String(cfg.id)) ||
                                       (!selectedId && autoSelectId === cfg.id);
                    const selected = isSelected ? 'selected' : '';
                    options += `<option value="${cfg.id}" ${selected}>${cfg.name}${provider}${isDefault}</option>`;
                });

                smtpSelect.innerHTML = options;

                // 如果有預設設定且沒有選擇（多於一個設定時），顯示提示
                const defaultConfig = data.data.default_config;
                if (defaultConfig && !selectedId && configs.length > 1) {
                    // 更新提示文字
                    const hint = smtpSelect.nextElementSibling;
                    if (hint) {
                        hint.textContent = `預設將使用: ${defaultConfig.name}`;
                    }
                }
            } catch (error) {
                console.error('載入 SMTP 設定失敗:', error);
                smtpSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailAdapterSmtpConfigs = loadEmailAdapterSmtpConfigs;

        // 載入可用的收件人群組
        async function loadEmailAdapterGroups(selectedIds) {
            const groupSelect = document.getElementById('emailAdapterGroups');
            if (!groupSelect) return;

            try {
                const response = await fetch('/api/enterprise/data/settings/email-groups/available');
                if (!response.ok) {
                    groupSelect.innerHTML = '<option value="">無法載入群組</option>';
                    return;
                }

                const data = await response.json();
                if (!data.success || !data.data || !data.data.groups) {
                    groupSelect.innerHTML = '<option value="">沒有可用的群組</option>';
                    return;
                }

                // 建構選項（只顯示企業群組，不顯示系統群組）
                let options = '';
                data.data.groups.forEach(group => {
                    // 企業郵件只使用企業級群組（scope: 'organization'）
                    if (group.scope === 'organization') {
                        const selected = selectedIds && selectedIds.includes(group.id) ? 'selected' : '';
                        options += `<option value="${group.id}" ${selected}>${group.name} (${group.recipient_count}人)</option>`;
                    }
                });

                if (options === '') {
                    groupSelect.innerHTML = '<option value="">沒有可用的企業群組</option>';
                } else {
                    groupSelect.innerHTML = options;
                }
            } catch (error) {
                console.error('載入收件人群組失敗:', error);
                groupSelect.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadEmailAdapterGroups = loadEmailAdapterGroups;

        // 切換收件者類型欄位顯示
        function toggleEmailAdapterRecipientFields() {
            const type = document.getElementById('emailAdapterRecipientType')?.value;
            const groupField = document.getElementById('emailAdapterGroupField');
            const manualField = document.getElementById('emailAdapterManualField');

            if (groupField) groupField.style.display = type === 'group' ? 'block' : 'none';
            if (manualField) manualField.style.display = type === 'manual' ? 'block' : 'none';
        }
        window.toggleEmailAdapterRecipientFields = toggleEmailAdapterRecipientFields;

        // 套用 EmailAdapter 節點配置
        async function applyEmailAdapterConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const smtpConfigId = document.getElementById('emailAdapterSmtpConfig')?.value || '';
            const recipientType = document.getElementById('emailAdapterRecipientType')?.value || 'manual';
            const subject = document.getElementById('emailAdapterSubject')?.value;
            const body = document.getElementById('emailAdapterBody')?.value;
            const bodyType = document.getElementById('emailAdapterBodyType')?.value || 'plain';
            const priority = document.getElementById('emailAdapterPriority')?.value || 'normal';
            const ccManual = document.getElementById('emailAdapterCcManual')?.value || '';

            // 驗證必填項
            if (!subject || !subject.trim()) {
                updateStatus('請輸入郵件主旨', 'warning');
                return;
            }
            if (!body || !body.trim()) {
                updateStatus('請輸入郵件內容', 'warning');
                return;
            }

            // 收集收件者設定
            let recipientGroups = [];
            let recipientManual = '';

            if (recipientType === 'group') {
                const groupSelect = document.getElementById('emailAdapterGroups');
                if (groupSelect) {
                    recipientGroups = Array.from(groupSelect.selectedOptions).map(opt => opt.value);
                }
                if (recipientGroups.length === 0) {
                    updateStatus('請選擇至少一個收件人群組', 'warning');
                    return;
                }
            } else if (recipientType === 'manual') {
                recipientManual = document.getElementById('emailAdapterRecipientManual')?.value || '';
                if (!recipientManual.trim()) {
                    updateStatus('請輸入收件者 Email', 'warning');
                    return;
                }
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                smtp_config_id: smtpConfigId || null,
                recipient_type: recipientType,
                recipient_groups: recipientGroups,
                recipient_manual: recipientManual.trim(),
                cc_manual: ccManual.trim(),
                subject: subject.trim(),
                body: body.trim(),
                body_type: bodyType,
                priority: priority
            };

            node.data('config', updatedConfig);

            // 自動儲存流程
            try {
                await saveWorkflow();
                updateStatus(`✅ 企業郵件設定已套用並儲存`, 'success');
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus(`⚠ 設定已套用，但儲存失敗: ${error.message}`, 'warning');
            }

            console.log('EmailAdapter 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyEmailAdapterConfig = applyEmailAdapterConfig;

        // ============================================
        // BRANCH 條件路由節點函數
        // ============================================

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
            const fallbackMessage = document.getElementById('branchFallbackMessage')?.value || '無匹配規則';
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
            if (fallbackAction === 'log' || fallbackAction === 'default') {
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

        // ============================================
        // END BRANCH 函數
        // ============================================

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
                const response = await fetch('/api/workflows/data/org-tree');
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
                const response = await fetch('/api/workflows/data/roles');
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
                if (msg) { msg.textContent = '請選擇或填寫簽核者'; msg.className = 'fa-modal-message warning'; }
                else { updateStatus('請選擇或填寫簽核者', 'warning'); }
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
                'INITIATOR': '發起人',
                'USER': '指定用戶',
                'ROLE': '指定角色',
                'DEPARTMENT': '指定部門',
                'DYNAMIC': '動態'
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

