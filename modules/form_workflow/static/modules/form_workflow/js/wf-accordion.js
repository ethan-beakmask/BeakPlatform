/**
 * wf-accordion.js -- Accordion 節點設定面板（主分派器）
 * 原 2182 行拆分為主檔 + 5 個子模組：
 *   wf-accordion-subflow.js     -- 子流程節點
 *   wf-accordion-messaging.js   -- Telegram, SysTelegram, EmailRelay, EmailAdapter
 *   wf-accordion-broadcast.js   -- NavbarBroadcast, AlertBroadcast
 *   wf-accordion-flow.js        -- Converge, Delay, End, Abandon, Branch, ParallelFork, ParallelJoin
 *   wf-accordion-operations.js  -- OpSet, OpFieldWrite, SqlExecutor, FormAdapter, SubSystemProvision
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

            // 節點類型顯示名稱（對應 DB workflow_node_definitions）
            const typeNames = {
                'Start': '開始節點',
                'End': '結束節點',
                'Switch': '條件分支',
                'Subflow': '子流程',
                'Converge': '匯聚節點',
                'Delay': '暫停',
                'OpSet': '設定變數',
                'OpFieldRead': '讀取欄位',
                'OpFieldWrite': '寫入欄位',
                'FormAdapter': '簽核',
                'EmailAdapter': '郵件通知',
                'SqlExecutor': 'SQL 執行器',
                'Abandon': '放棄流程',
                'Telegram': 'Telegram 通知',
                'SysTelegram': '系統 Telegram',
                'EmailRelay': '系統郵件',
                'NavbarBroadcast': '跑馬燈廣播',
                'AlertBroadcast': '緊急廣播',
                'Branch': '條件路由',
                'ParallelFork': '並行分支',
                'ParallelJoin': '並行匯合',
                'SubSystemProvision': '子系統配置'
            };

            const description = node.data('description') || '';

            // 有額外設定的節點類型（這些節點有自己的「套用」按鈕）
            const nodesWithSettings = [
                'Subflow', 'Delay', 'OpFieldWrite', 'OpSet', 'Telegram',
                'SysTelegram', 'EmailRelay', 'EmailAdapter', 'Branch',
                'FormAdapter', 'End', 'Converge', 'SqlExecutor',
                'ParallelFork', 'ParallelJoin',
                'NavbarBroadcast', 'AlertBroadcast',
                'Abandon', 'SubSystemProvision'
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
            if (type === 'Converge')             info += renderConvergePanel(node, nodeId);
            if (type === 'Delay')                info += renderDelayPanel(node, nodeId);
            if (type === 'SqlExecutor')          info += renderSqlExecutorPanel(node, nodeId);
            if (type === 'OpSet')                info += renderOpSetPanel(node, nodeId);
            if (type === 'OpFieldWrite')         info += renderOpFieldWritePanel(node, nodeId);
            if (type === 'FormAdapter')          info += renderFormAdapterPanel(node, nodeId);
            if (type === 'Telegram')             info += renderTelegramPanel(node, nodeId);
            if (type === 'SysTelegram')          info += renderSysTelegramPanel(node, nodeId);
            if (type === 'EmailRelay')           info += renderEmailRelayPanel(node, nodeId);
            if (type === 'EmailAdapter')         info += renderEmailAdapterPanel(node, nodeId);
            if (type === 'NavbarBroadcast')      info += renderNavbarBroadcastPanel(node, nodeId);
            if (type === 'AlertBroadcast')       info += renderAlertBroadcastPanel(node, nodeId);
            if (type === 'Branch')               info += renderBranchPanel(node, nodeId);
            if (type === 'End')                  info += renderEndPanel(node, nodeId);
            if (type === 'Abandon')              info += renderAbandonPanel(node, nodeId);
            if (type === 'SubSystemProvision')   info += renderSubSystemProvisionPanel(node, nodeId);
            if (type === 'ParallelFork')         info += renderParallelForkPanel(node, nodeId);
            if (type === 'ParallelJoin')         info += renderParallelJoinPanel(node, nodeId);

            // ---- 寫入 DOM ----
            document.getElementById('nodeSettings').innerHTML = info;

            // ---- Post-render hooks（需要 DOM 已存在才能執行） ----
            if (type === 'Subflow')         loadAvailableSubflows(nodeId);
            if (type === 'SqlExecutor')     setTimeout(() => updateSQLQueryDescription(), 100);
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
            if (type === 'EmailRelay') {
                const groups = (node.data('config') || {}).recipient_groups || [];
                setTimeout(() => loadEmailRelayGroups(groups), 100);
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
            if (type === 'Branch') {
                const cfg = node.data('config') || {};
                const rules = cfg.rules || [];
                const fallback = cfg.fallback || { action: 'log', log_message: '無匹配規則' };
                setTimeout(() => {
                    loadBranchOutgoingEdges(nodeId, fallback);
                    renderBranchRules(rules, nodeId);
                }, 50);
            }

            updateStatus(`選中節點：${nodeId}`);
        }

        // ==================== 套用節點基本資訊 ====================

        // 參數 silent: 是否靜默模式（不顯示成功訊息，用於其他 apply 函數內部調用）
        function applyNodeBasicInfo(nodeId, silent = false) {
            const node = cy.getElementById(nodeId);
            if (!node) {
                updateStatus('找不到節點', 'warning');
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
