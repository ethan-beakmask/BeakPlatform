/**
 * wf-accordion.js -- Accordion 節點設定面板（主分派器）
 * 原 2182 行拆分為主檔 + 5 個子模組：
 *   wf-accordion-subflow.js     -- 子流程節點
 *   wf-accordion-messaging.js   -- Telegram, SysTelegram, SysEmailRelay, EmailAdapter
 *   wf-accordion-broadcast.js   -- NavbarBroadcast, AlertBroadcast
 *   wf-accordion-flow.js        -- Delay, End, Branch, ParallelJoin
 *   wf-accordion-operations.js  -- OpSet, OpFieldWrite, FormAdapter, SubSystemProvision
 */

        // ==================== Accordion 通用函式 ====================

        // 切換 accordion section 展開/收合
        function toggleAccordion(sectionEl) {
            if (!sectionEl) return;
            sectionEl.classList.toggle('expanded');
        }

        // 用 section id 切換
        function toggleAccordionById(id) {
            toggleAccordion(document.getElementById(id));
        }

        // ==================== 顯示節點資訊（主分派器） ====================

        function showNodeInfo(node) {
            // 切換節點前，先自動套用前一個面板的設定
            autoApplyCurrentPanel();

            // 關閉可能還開著的 FormAdapter Modal
            closeFormAdapterModal();

            const rawType = node.data('type');
            const type = normalizeNodeType(rawType);  // 標準化節點類型
            const label = node.data('label');
            const nodeId = node.id();

            // 追蹤當前編輯的節點
            currentEditingNodeId = nodeId;
            currentEditingNodeType = type;

            // 隱藏線段編輯面板，顯示節點設定
            document.getElementById('edge-editing-panel').style.display = 'none';
            document.getElementById('edge-control-panel').style.display = 'none';
            document.getElementById('nodeSettings').style.display = 'block';

            // OP_FIELDREAD / OP_FIELDWRITE 節點：自動切換到表單欄位分頁並展開面板
            if (type === 'OpFieldRead' || type === 'OpFieldWrite') {
                switchTab('formfields');
                if (!isPanelExpanded) {
                    toggleControlPanel();
                }
                if (currentFormFields.length === 0 && currentMappedForms.length === 1) {
                    selectForm(currentMappedForms[0]);
                }
            }

            // OpSet 節點：自動切換到變數總覽分頁並展開面板
            if (type === 'OpSet') {
                switchTab('opsetvars');
                if (!isPanelExpanded) {
                    toggleControlPanel();
                }
                setTimeout(() => reloadAllVars(), 100);
            }

            const description = node.data('description') || '';

            // 有額外設定的節點類型（這些節點有自己的「套用」按鈕）
            const nodesWithSettings = [
                'Subflow', 'Delay', 'OpFieldWrite', 'OpSet', 'Telegram',
                'SysTelegram', 'SysEmailRelay', 'EmailAdapter', 'Branch',
                'FormAdapter', 'End', 'SysSqlExecutor', 'OsExecutor', 'OsFileRead',
                'ParallelJoin',
                'NavbarBroadcast', 'AlertBroadcast',
                'SubSystemProvision', 'ApiKeyAction',
                'DecisionWriter'
            ];
            const hasAdditionalSettings = nodesWithSettings.includes(type);

            // ---- 基本資訊區 ----
            let info = `
                <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                        <label style="font-size: 11px; color: #666; white-space: nowrap;">名稱</label>
                        <input type="text" id="node-label-input" value="${label}"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;"
                               placeholder="節點名稱">
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <label style="font-size: 11px; color: #666; white-space: nowrap;">描述</label>
                        <input type="text" id="node-description-input" value="${description}"
                               style="flex: 1; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;"
                               placeholder="選填">
                    </div>
                    ${!hasAdditionalSettings ? `
                    <button class="btn-primary" onclick="applyNodeBasicInfo('${nodeId}')" style="width: 100%; margin-top: 8px; padding: 5px; font-size: 11px;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                    ` : ''}
                </div>
            `;

            // ---- 分派到子模組 render 函式 ----
            if (type === 'Subflow')              info += renderSubflowPanel(node, nodeId);
            if (type === 'Delay')                info += renderDelayPanel(node, nodeId);
            if (type === 'SysSqlExecutor')       info += renderSysSqlExecutorPanel(node, nodeId);
            if (type === 'OsExecutor')           info += renderOsExecutorPanel(node, nodeId);
            if (type === 'OsFileRead')             info += renderOsFileReadPanel(node, nodeId);
            if (type === 'OsFileWrite')            info += renderOsFileWritePanel(node, nodeId);
            if (type === 'OpSet')                info += renderOpSetPanel(node, nodeId);
            if (type === 'OpHrLookup')           info += renderOpHrLookupPanel(node, nodeId);
            if (type === 'OpFieldWrite')         info += renderOpFieldWritePanel(node, nodeId);
            if (type === 'FormAdapter')          info += renderFormAdapterPanel(node, nodeId);
            if (type === 'Telegram')             info += renderTelegramPanel(node, nodeId);
            if (type === 'SysTelegram')          info += renderSysTelegramPanel(node, nodeId);
            if (type === 'SysEmailRelay')        info += renderSysEmailRelayPanel(node, nodeId);
            if (type === 'EmailAdapter')         info += renderEmailAdapterPanel(node, nodeId);
            if (type === 'NavbarBroadcast')      info += renderNavbarBroadcastPanel(node, nodeId);
            if (type === 'AlertBroadcast')       info += renderAlertBroadcastPanel(node, nodeId);
            if (type === 'Branch')               info += renderBranchPanel(node, nodeId);
            if (type === 'End')                  info += renderEndPanel(node, nodeId);
            if (type === 'SubSystemProvision')   info += renderSubSystemProvisionPanel(node, nodeId);
            if (type === 'ApiKeyAction')         info += renderApiKeyActionPanel(node, nodeId);
            if (type === 'AiAgent')              info += renderAiAgentPanel(node, nodeId);
            if (type === 'DecisionWriter')       info += renderDecisionWriterPanel(node, nodeId);
            if (type === 'ParallelJoin')         info += renderParallelJoinPanel(node, nodeId);

            // ---- 寫入 DOM ----
            document.getElementById('nodeSettings').innerHTML = info;

            // ---- Post-render hooks（需要 DOM 已存在才能執行） ----
            if (type === 'Subflow')         loadAvailableSubflows(nodeId);
            if (type === 'SysSqlExecutor')  setTimeout(() => initSysSqlExecutorPanel(nodeId), 50);
            if (type === 'OpSet') {
                const operations = (node.data('config') || {}).operations || [];
                setTimeout(() => renderOpsetOperations(operations), 50);
            }
            if (type === 'OpFieldWrite') {
                const targetField = (node.data('config') || {}).target_field || '';
                setTimeout(() => loadFieldWriteTargetFields(targetField), 500);
            }
            if (type === 'Telegram') {
                const cfg = node.data('config') || {};
                setTimeout(() => loadTelegramConfigs(cfg.config_id || null, cfg.channel_name), 100);
            }
            if (type === 'SysTelegram') {
                const cfg = node.data('config') || {};
                setTimeout(() => loadSysTelegramConfigs(cfg.config_id || null, cfg.channel_name), 100);
            }
            if (type === 'SysEmailRelay') {
                const groups = (node.data('config') || {}).recipient_groups || [];
                setTimeout(() => loadSysEmailRelayGroups(groups), 100);
            }
            if (type === 'EmailAdapter') {
                const cfg = node.data('config') || {};
                setTimeout(() => {
                    loadEmailAdapterSmtpConfigs(cfg.smtp_config_id);
                    loadEmailAdapterGroups(cfg.recipient_groups || []);
                }, 100);
            }
            if (type === 'AlertBroadcast') {
                const cfg = node.data('config') || {};
                setTimeout(() => loadAlertBroadcastOptions(cfg.target_roles || [], cfg.target_departments || []), 100);
            }
            if (type === 'ApiKeyAction') {
                const cfg = node.data('config') || {};
                setTimeout(() => loadApiKeyActionKeys(cfg.key_source === 'static' ? (cfg.key_id || '') : ''), 100);
            }
            if (type === 'DecisionWriter') setTimeout(() => toggleDwFields(), 50);
            if (type === 'Branch') {
                const cfg = node.data('config') || {};
                const rules = cfg.rules || [];
                const fallback = cfg.fallback || { action: 'log', log_message: '無匹配規則' };
                setTimeout(() => {
                    loadBranchOutgoingEdges(nodeId, fallback);
                    renderBranchRules(rules, nodeId);
                }, 50);
            }

            // 與 addNode 的「已新增節點」訊息格式一致：顯示名稱在前、內部 id 在後
            // （id 建立後固定不變，改節點名稱不會改 id，因為連線是靠 id 錨定的）
            updateStatus(`選中節點：${label} (${nodeId})`);
        }

        // ==================== 套用節點基本資訊 ====================

        // 參數 silent: 是否靜默模式（不顯示成功訊息，用於其他 apply 函數內部調用）
        function applyNodeBasicInfo(nodeId, silent = false) {
            const node = cy.getElementById(nodeId);
            if (!node) {
                updateStatus(__('找不到節點'), 'warning');
                return null;
            }

            const labelInput = document.getElementById('node-label-input');
            const descInput = document.getElementById('node-description-input');

            const newLabel = labelInput?.value?.trim() || node.data('label');
            const newDescription = descInput?.value?.trim() || '';

            // 更新節點資料
            node.data('label', newLabel);
            node.data('description', newDescription);

            if (!silent) {
                updateStatus(`已更新節點：${newLabel}`, 'success');
            }

            return node; // 返回 node 供其他函數使用
        }
