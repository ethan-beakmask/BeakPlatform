/**
 * wf-save.js -- 儲存前自動套用 + saveWorkflow + 縮圖產生
 * 從 workflow-main.js 拆分
 */

        // ==================== 儲存前自動套用面板設定 ====================

        /**
         * 自動套用當前開啟面板的節點設定
         * 解決用戶在面板填值後忘記按「套用」就直接按「儲存」的問題
         * 此函數靜默執行，不顯示驗證警告、不搶 focus
         */
        function autoApplyCurrentPanel() {
            if (!currentEditingNodeId) return true;

            const node = cy.getElementById(currentEditingNodeId);
            if (!node || node.length === 0) return true;

            const type = currentEditingNodeType;
            const config = node.data('config') || {};
            let changed = false;

            // 自動套用基本資訊（名稱、描述）
            const labelInput = document.getElementById('node-label-input');
            const descInput = document.getElementById('node-description-input');
            if (labelInput) {
                const newLabel = labelInput.value.trim();
                if (newLabel && newLabel !== node.data('label')) {
                    node.data('label', newLabel);
                }
            }
            if (descInput) {
                const newDesc = descInput.value.trim();
                if (newDesc !== (node.data('description') || '')) {
                    node.data('description', newDesc);
                }
            }

            // 各節點類型的專用設定
            switch (type) {
                case 'OpFieldWrite': {
                    const target = document.getElementById('fieldWriteTargetField');
                    const content = document.getElementById('fieldWriteContent');
                    const contentTypeRadio = document.querySelector('input[name="fieldWriteContentType"]:checked');
                    if (target && content && target.value.trim()) {
                        config.target_field = target.value.trim();
                        config.content = content.value;
                        config.content_type = contentTypeRadio ? contentTypeRadio.value : 'text';
                        changed = true;
                    }
                    break;
                }
                case 'OpSet': {
                    if (typeof opsetOperationsTemp !== 'undefined' && opsetOperationsTemp.length > 0) {
                        config.operations = [...opsetOperationsTemp];
                        changed = true;
                    }
                    break;
                }
                case 'Delay': {
                    const delayInput = document.getElementById('delaySeconds');
                    if (delayInput && delayInput.value) {
                        config.delay_seconds = parseInt(delayInput.value) || 0;
                        changed = true;
                    }
                    break;
                }
                case 'Subflow': {
                    const childSelect = document.getElementById('childFlowSelect');
                    if (childSelect && childSelect.value) {
                        config.childFlowId = childSelect.value;
                        changed = true;
                    }
                    break;
                }
                case 'End': {
                    const finishMode = document.querySelector('input[name="finishMode"]:checked');
                    const waitSeconds = document.getElementById('endWaitSeconds');
                    if (finishMode) {
                        config.finish_mode = finishMode.value;
                        changed = true;
                    }
                    if (waitSeconds && waitSeconds.value) {
                        config.wait_seconds = parseInt(waitSeconds.value) || 3;
                        changed = true;
                    }
                    break;
                }
                case 'SubSystemProvision': {
                    const sspAction = document.querySelector('input[name="sspAction"]:checked');
                    if (sspAction) {
                        config.action = sspAction.value;
                        if (sspAction.value === 'create') {
                            const nameEl = document.getElementById('sspName');
                            const devEl = document.getElementById('sspDeveloper');
                            const iconEl = document.getElementById('sspIcon');
                            if (nameEl) config.sub_system_name = nameEl.value.trim();
                            if (devEl) config.sub_system_developer = devEl.value.trim();
                            if (iconEl) config.sub_system_icon = iconEl.value.trim();
                        } else {
                            const codeEl = document.getElementById('sspCode');
                            if (codeEl) config.sub_system_code = codeEl.value.trim();
                        }
                        changed = true;
                    }
                    break;
                }
                case 'FormAdapter': {
                    const assigneeType = document.getElementById('formAdapterAssigneeType');
                    const selectionMode = document.querySelector('input[name="selectionMode"]:checked');
                    const allowComment = document.getElementById('formAdapterAllowComment');
                    const minCommentLen = document.getElementById('formAdapterMinCommentLength');
                    if (assigneeType && assigneeType.value) {
                        config.assignee_type = assigneeType.value;
                        if (assigneeType.value === 'ROLE') {
                            const roleSelect = document.getElementById('formAdapterRoleValue');
                            if (roleSelect && roleSelect.value) {
                                config.assignee_value = roleSelect.value;
                                const roleName = roleSelect.options[roleSelect.selectedIndex]?.text || '';
                                const rawUnitScope = document.getElementById('faUnitScope')?.value || 'GLOBAL';
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
                                if (unitScope === 'GLOBAL') config.assignee_label = roleName;
                                else if (unitScope === 'UNIT') config.assignee_label = `${roleName}@${unitLabel}`;
                                else if (unitScope === 'APPLICANT_UNIT') config.assignee_label = `${roleName}@${__('申請人所屬單位')}`;
                                else config.assignee_label = `${roleName}@${__('申請人單位上 {n} 層', { n: unitLevelsUp })}`;
                                config.unit_scope = unitScope;
                                config.unit_secure_code = unitSecureCode;
                                config.unit_label = unitLabel;
                                config.unit_levels_up = unitLevelsUp;
                                config.self_target_action = selfTargetAction;
                            }
                        } else if (assigneeType.value === 'DYNAMIC') {
                            const dynInput = document.getElementById('formAdapterDynamicValue');
                            if (dynInput) config.assignee_value = dynInput.value.trim();
                        }
                        if (typeof selectedAssigneeList !== 'undefined' && selectedAssigneeList.length > 0) {
                            config.assignee_list = [...selectedAssigneeList];
                        }
                        if (selectionMode) config.selection_mode = selectionMode.value;
                        if (allowComment) config.allow_comment = allowComment.checked;
                        if (minCommentLen) config.min_comment_length = parseInt(minCommentLen.value) || 0;
                        const faTimeoutEnabled = document.getElementById('faTimeoutEnabled');
                        if (faTimeoutEnabled) {
                            config.timeout_enabled = faTimeoutEnabled.checked;
                            config.timeout_minutes = faTimeoutEnabled.checked
                                ? (parseInt(document.getElementById('faTimeoutMinutes')?.value, 10) || 0) : 0;
                            config.timeout_mode = document.getElementById('faTimeoutMode')?.value === 'WORKING' ? 'WORKING' : 'ABSOLUTE';
                            config.timeout_path_id = faTimeoutEnabled.checked
                                ? (document.getElementById('faTimeoutPathId')?.value || '') : '';
                        }
                        const noAssigneeActionEl = document.getElementById('faNoAssigneeAction');
                        if (noAssigneeActionEl) {
                            const noAssigneeAction = noAssigneeActionEl.value === 'fallback_role' ? 'fallback_role' : 'return';
                            const noAssigneeRoleSelect = document.getElementById('faNoAssigneeRole');
                            const noAssigneeRoleSecureCode = noAssigneeAction === 'fallback_role' ? (noAssigneeRoleSelect?.value || '') : '';
                            if (noAssigneeAction === 'fallback_role' && !noAssigneeRoleSecureCode) {
                                const msg = document.getElementById('faModalMessage');
                                const error = __('改派給角色時必須選擇角色');
                                if (msg) { msg.textContent = error; msg.className = 'fa-modal-message warning'; }
                                else { updateStatus(error, 'warning'); }
                                return false;
                            }
                            config.no_assignee_action = noAssigneeAction;
                            config.no_assignee_role_secure_code = noAssigneeRoleSecureCode;
                            config.no_assignee_role_label = noAssigneeAction === 'fallback_role'
                                ? (noAssigneeRoleSelect?.selectedOptions[0]?.text || '') : '';
                        }
                        changed = true;
                    }
                    break;
                }
                case 'Branch': {
                    const fallbackAction = document.getElementById('branchFallbackAction');
                    const fallbackMsg = document.getElementById('branchFallbackMessage');
                    const fallbackTarget = document.getElementById('branchFallbackTarget');
                    if (typeof branchRulesData !== 'undefined' && branchRulesData.length > 0) {
                        config.rules = [...branchRulesData];
                        changed = true;
                    }
                    if (fallbackAction) {
                        const fallback = { action: fallbackAction.value };
                        if (fallbackAction.value === 'log' && fallbackMsg) {
                            fallback.log_message = fallbackMsg.value;
                        }
                        if (fallbackAction.value === 'route' && fallbackTarget && fallbackTarget.value) {
                            fallback.target_edge = fallbackTarget.value;
                        }
                        config.fallback = fallback;
                        changed = true;
                    }
                    break;
                }
                case 'ParallelJoin': {
                    const enableTimeoutEl = document.getElementById('pjEnableTimeout');
                    const timeoutMinutesEl = document.getElementById('pjTimeoutMinutes');
                    const timeoutEdgeEl = document.getElementById('pjTimeoutEdgeId');
                    const joinModeEl = document.querySelector('input[name="pjJoinMode"]:checked');
                    const releaseOnceEl = document.getElementById('pjReleaseOnce');
                    if (enableTimeoutEl) {
                        const enableTimeout = enableTimeoutEl.checked;
                        config.enable_timeout = enableTimeout;
                        if (enableTimeout) {
                            if (timeoutMinutesEl && timeoutMinutesEl.value) {
                                config.timeout_minutes = parseInt(timeoutMinutesEl.value, 10) || 0;
                            }
                            if (timeoutEdgeEl && timeoutEdgeEl.value) {
                                config.timeout_edge_id = timeoutEdgeEl.value;
                            }
                        } else {
                            config.timeout_minutes = 0;
                            config.timeout_edge_id = '';
                        }
                        changed = true;
                    }
                    if (joinModeEl) {
                        config.join_mode = joinModeEl.value;
                        changed = true;
                    }
                    if (releaseOnceEl) {
                        config.release_once = releaseOnceEl.checked;
                        changed = true;
                    }
                    break;
                }
                case 'SqlExecutor': {
                    const sqlCfg = collectSqlExecutorConfig();
                    if (sqlCfg) {
                        Object.assign(config, sqlCfg);
                        changed = true;
                    }
                    break;
                }
                case 'OsExecutor': {
                    const osCfg = collectOsExecutorConfig();
                    if (osCfg) {
                        Object.assign(config, osCfg);
                        changed = true;
                    }
                    break;
                }
                case 'OsFileRead': {
                    const frCfg = collectOsFileReadConfig();
                    if (frCfg) {
                        Object.assign(config, frCfg);
                        changed = true;
                    }
                    break;
                }
                case 'OsFileWrite': {
                    const fwCfg = collectOsFileWriteConfig();
                    if (fwCfg) {
                        Object.assign(config, fwCfg);
                        changed = true;
                    }
                    break;
                }
                case 'OpHrLookup': {
                    const hrCfg = collectOpHrLookupConfig();
                    if (hrCfg) {
                        Object.assign(config, hrCfg);
                        changed = true;
                    }
                    break;
                }
                case 'Telegram': {
                    const cfgId = document.getElementById('telegramConfigId');
                    const channel = document.getElementById('telegramChannelName');
                    const msg = document.getElementById('telegramMessage');
                    const parseMode = document.getElementById('telegramParseMode');
                    const disableNotif = document.getElementById('telegramDisableNotification');
                    const disablePreview = document.getElementById('telegramDisableWebPagePreview');
                    if (cfgId && msg) {
                        config.config_id = cfgId.value;
                        config.channel_name = channel ? channel.value : '';
                        config.message = msg.value;
                        if (parseMode) config.parse_mode = parseMode.value;
                        if (disableNotif) config.disable_notification = disableNotif.checked;
                        if (disablePreview) config.disable_web_page_preview = disablePreview.checked;
                        changed = true;
                    }
                    break;
                }
                case 'SysTelegram': {
                    const cfgId = document.getElementById('sysTelegramConfigId');
                    const channel = document.getElementById('sysTelegramChannelName');
                    const msg = document.getElementById('sysTelegramMessage');
                    const parseMode = document.getElementById('sysTelegramParseMode');
                    const disableNotif = document.getElementById('sysTelegramDisableNotification');
                    const disablePreview = document.getElementById('sysTelegramDisableWebPagePreview');
                    if (cfgId && msg) {
                        config.config_id = cfgId.value;
                        config.channel_name = channel ? channel.value : '';
                        config.message = msg.value;
                        if (parseMode) config.parse_mode = parseMode.value;
                        if (disableNotif) config.disable_notification = disableNotif.checked;
                        if (disablePreview) config.disable_web_page_preview = disablePreview.checked;
                        changed = true;
                    }
                    break;
                }
                case 'SysEmailRelay': {
                    const recipType = document.getElementById('sysEmailRelayRecipientType');
                    const subject = document.getElementById('sysEmailRelaySubject');
                    const body = document.getElementById('sysEmailRelayBody');
                    const bodyType = document.getElementById('sysEmailRelayBodyType');
                    const priority = document.getElementById('sysEmailRelayPriority');
                    const ccManual = document.getElementById('sysEmailRelayCcManual');
                    if (recipType && subject && body) {
                        config.recipient_type = recipType.value;
                        config.subject = subject.value;
                        config.body = body.value;
                        if (bodyType) config.body_type = bodyType.value;
                        if (priority) config.priority = priority.value;
                        if (ccManual) config.cc_manual = ccManual.value.trim();
                        if (recipType.value === 'group') {
                            const groupSelect = document.getElementById('sysEmailRelayGroups');
                            if (groupSelect) {
                                config.recipient_groups = Array.from(groupSelect.selectedOptions).map(o => o.value);
                            }
                        } else if (recipType.value === 'manual') {
                            const manualInput = document.getElementById('sysEmailRelayRecipientManual');
                            if (manualInput) config.recipient_manual = manualInput.value.trim();
                        }
                        changed = true;
                    }
                    break;
                }
                case 'EmailAdapter': {
                    const smtpCfg = document.getElementById('emailAdapterSmtpConfig');
                    const recipType = document.getElementById('emailAdapterRecipientType');
                    const subject = document.getElementById('emailAdapterSubject');
                    const body = document.getElementById('emailAdapterBody');
                    const bodyType = document.getElementById('emailAdapterBodyType');
                    const priority = document.getElementById('emailAdapterPriority');
                    const ccManual = document.getElementById('emailAdapterCcManual');
                    if (recipType && subject && body) {
                        if (smtpCfg) config.smtp_config_id = smtpCfg.value;
                        config.recipient_type = recipType.value;
                        config.subject = subject.value;
                        config.body = body.value;
                        if (bodyType) config.body_type = bodyType.value;
                        if (priority) config.priority = priority.value;
                        if (ccManual) config.cc_manual = ccManual.value.trim();
                        if (recipType.value === 'GROUP') {
                            const groupSelect = document.getElementById('emailAdapterGroups');
                            if (groupSelect) {
                                config.recipient_groups = Array.from(groupSelect.selectedOptions).map(o => o.value);
                            }
                        } else if (recipType.value === 'MANUAL') {
                            const manualInput = document.getElementById('emailAdapterRecipientManual');
                            if (manualInput) config.recipient_manual = manualInput.value.trim();
                        }
                        changed = true;
                    }
                    break;
                }
                case 'NavbarBroadcast': {
                    const modeEl = document.getElementById('nbMode');
                    const broadcastCodeEl = document.getElementById('nbBroadcastCode');
                    const messageEl = document.getElementById('nbMessage');
                    const textColorEl = document.getElementById('nbTextColor');
                    const bgColorEl = document.getElementById('nbBgColor');
                    const displaySecondsEl = document.getElementById('nbDisplaySeconds');
                    const durationMinutesEl = document.getElementById('nbDurationMinutes');
                    if (modeEl && modeEl.value) {
                        config.mode = modeEl.value;
                        changed = true;
                    }
                    if (broadcastCodeEl && broadcastCodeEl.value.trim()) {
                        config.broadcast_code = broadcastCodeEl.value.trim();
                        changed = true;
                    }
                    // 與 applyNavbarBroadcastConfig 一致：只有 start 模式才有訊息與外觀欄位。
                    // stop 模式照樣寫入會在 config 留下用不到的殘值。
                    const nbMode = modeEl ? modeEl.value : (config.mode || 'start');
                    if (nbMode === 'start') {
                        if (messageEl && messageEl.value.trim()) {
                            config.message = messageEl.value.trim();
                            changed = true;
                        }
                        if (textColorEl && textColorEl.value) {
                            config.text_color = textColorEl.value;
                            changed = true;
                        }
                        if (bgColorEl && bgColorEl.value) {
                            config.bg_color = bgColorEl.value;
                            changed = true;
                        }
                        if (displaySecondsEl && displaySecondsEl.value) {
                            config.display_seconds = parseInt(displaySecondsEl.value, 10) || 5;
                            changed = true;
                        }
                        if (durationMinutesEl && durationMinutesEl.value) {
                            config.duration_minutes = parseInt(durationMinutesEl.value, 10) || 0;
                            changed = true;
                        }
                    }
                    break;
                }
                case 'AlertBroadcast': {
                    const broadcastCodeEl = document.getElementById('abBroadcastCode');
                    const titleEl = document.getElementById('abTitle');
                    const messageEl = document.getElementById('abMessage');
                    const targetTypeEl = document.getElementById('abTargetType');
                    const requireAckEl = document.getElementById('abRequireAck');
                    const includeChildrenEl = document.getElementById('abIncludeChildren');
                    const rolesEl = document.getElementById('abTargetRoles');
                    const deptsEl = document.getElementById('abTargetDepartments');
                    if (broadcastCodeEl && broadcastCodeEl.value.trim()) {
                        config.broadcast_code = broadcastCodeEl.value.trim();
                        changed = true;
                    }
                    if (titleEl && titleEl.value.trim()) {
                        config.title = titleEl.value.trim();
                        changed = true;
                    }
                    if (messageEl && messageEl.value.trim()) {
                        config.message = messageEl.value.trim();
                        changed = true;
                    }
                    if (targetTypeEl && targetTypeEl.value) {
                        config.target_type = targetTypeEl.value;
                        changed = true;
                    }
                    if (requireAckEl) {
                        config.require_ack = requireAckEl.checked;
                        changed = true;
                    }
                    // 與 applyAlertBroadcastConfig 一致：只有 specific 模式才寫這三個欄位。
                    // 另外 abTargetRoles / abTargetDepartments 的 options 是非同步 fetch 載入的，
                    // 尚未載完時 selectedOptions 為空，無條件寫入會把既有設定清成空陣列。
                    const abTargetType = targetTypeEl ? targetTypeEl.value : (config.target_type || 'all');
                    if (abTargetType === 'specific') {
                        if (includeChildrenEl) {
                            config.include_children = includeChildrenEl.checked;
                            changed = true;
                        }
                        if (rolesEl && rolesEl.options.length > 0) {
                            config.target_roles = Array.from(rolesEl.selectedOptions).map(o => o.value);
                            changed = true;
                        }
                        if (deptsEl && deptsEl.options.length > 0) {
                            config.target_departments = Array.from(deptsEl.selectedOptions).map(o => o.value);
                            changed = true;
                        }
                    }
                    break;
                }
                case 'ApiKeyAction': {
                    const akaAction = document.getElementById('akaAction');
                    const akaSource = document.getElementById('akaKeySource');
                    if (akaAction && akaSource) {
                        config.action = akaAction.value;
                        config.key_source = akaSource.value;
                        if (akaSource.value === 'static') {
                            config.key_id = document.getElementById('akaKeyStatic')?.value || '';
                        } else if (akaSource.value === 'variable') {
                            config.key_id = document.getElementById('akaKeyExpr')?.value?.trim() || '';
                        } else {
                            config.key_id = '';
                        }
                        config.reason = document.getElementById('akaReason')?.value?.trim() || '';
                        changed = true;
                    }
                    break;
                }
                case 'AiAgent': {
                    const aiCfg = collectAiAgentConfig();
                    if (aiCfg) {
                        Object.assign(config, aiCfg);
                        changed = true;
                    }
                    break;
                }
                case 'DecisionWriter': {
                    if (typeof applyDecisionWriterToConfig === 'function'
                        && applyDecisionWriterToConfig(config)) {
                        changed = true;
                    }
                    break;
                }
            }

            if (changed) {
                node.data('config', config);
                console.log('💾 autoApply: 自動套用面板設定到', currentEditingNodeId, type);
            }
            return true;
        }

        // 儲存流程
        // 回傳 true 代表確實存檔成功；呼叫端可據此決定要不要離開目前流程
        async function saveWorkflow() {
            if (isReadOnly) {
                updateStatus(__('唯讀模式，無法儲存'), 'warning');
                return false;
            }
            // 儲存前自動套用當前面板的設定
            if (autoApplyCurrentPanel() === false) return false;

            console.log('💾 saveWorkflow 被調用');
            console.log('  currentWorkflowId:', currentWorkflowId);
            console.log('  currentWorkflowId 類型:', typeof currentWorkflowId);
            console.log('  currentWorkflowId 是否為空:', !currentWorkflowId);

            if (!currentWorkflowId) {
                console.error('❌ currentWorkflowId 未設置！');
                updateStatus(__('請先選擇或建立一個流程'), 'warning');
                return false;
            }

            try {
                console.log('💾 開始儲存流程:', currentWorkflowId);

                // 檢查 Cytoscape 實例狀態
                console.log('🔍 Cytoscape 狀態:');
                console.log('  cy 存在:', !!cy);
                console.log('  畫布上的節點總數:', cy.nodes().length);
                console.log('  畫布上的邊總數:', cy.edges().length);

                const nodes = [];
                const relayPoints = [];

                cy.nodes().forEach(node => {
                    if (node.data('type') === 'relay') {
                        // 保存中繼點資訊，包括 taxiControl 和 yellowControl 標記
                        const relayData = {
                            id: node.id(),
                            parentEdge: node.data('parentEdge'),
                            position: node.position()
                        };

                        // 如果是藍點控制點，額外保存標記
                        if (node.data('taxiControl')) {
                            relayData.taxiControl = true;
                        }

                        // 如果是正交折線控制點，額外保存標記
                        if (node.data('orthogonalControl')) {
                            relayData.orthogonalControl = true;
                            relayData.pointIndex = node.data('pointIndex');
                        }

                        // 如果是黃點控制點，額外保存標記
                        if (node.data('yellowControl')) {
                            relayData.yellowControl = true;
                            relayData.pointType = node.data('pointType'); // 保存點的類型（nearStar 或 corner）
                        }

                        relayPoints.push(relayData);
                        console.log('  ⚪ 收集中繼點:', relayData.id);
                    } else {
                        const nodeData = {
                            id: node.id(),
                            label: node.data('label'),
                            type: node.data('type'),
                            position: node.position(),
                            config: node.data('config') || {},
                            icon: node.data('icon') || '',
                            description: node.data('description') || ''
                        };

                        // 如果是群組節點，保存樣式資訊
                        if (isGroupNode(node)) {
                            nodeData.isGroup = true;
                            nodeData.borderStyle = node.data('borderStyle') || 'dashed';
                            nodeData.cornerStyle = node.data('cornerStyle') || 'round';
                            // 保存群組顏色
                            if (node.data('groupColor')) {
                                nodeData.groupColor = node.data('groupColor');
                            }
                        }

                        // 如果節點屬於某個群組，保存父群組ID
                        const parent = node.parent();
                        if (parent.length > 0) {
                            nodeData.parent = parent.id();
                        }

                        nodes.push(nodeData);
                        console.log('  🔷 收集節點:', nodeData.type, nodeData.label || nodeData.id, nodeData.isGroup ? ' (群組)' : '', nodeData.parent ? ` (屬於 ${nodeData.parent})` : '');
                    }
                });

                const edges = [];
                cy.edges('[!parentEdge]').forEach(edge => {
                    const hasRelays = getRelayPointsForEdge(edge.id()).length > 0;

                    // 保存線段的基本屬性和樣式
                    const edgeData = {
                        id: edge.id(),
                        source: edge.data('originalSource') || edge.data('source'),
                        target: edge.data('originalTarget') || edge.data('target'),
                        label: edge.data('label') || '',
                        hasRelays: hasRelays
                    };

                    // 保存正交折線狀態
                    if (edge.data('orthogonalEnabled')) {
                        edgeData.orthogonalEnabled = true;
                        // 從 Map 取方向
                        const orthoData = orthogonalControlPoints.get(edge.id());
                        if (orthoData) {
                            edgeData.orthogonalDirection = orthoData.direction || 'auto';
                        }
                    }

                    // 保存線段樣式屬性（所有線條類型都儲存）
                    const curveStyle = edge.style('curve-style') || 'straight';
                    const lineColor = edge.style('line-color') || '#95a5a6';

                    edgeData.style = {
                        'curve-style': curveStyle,
                        'width': parseFloat(edge.style('width')) || 3,
                        'line-color': lineColor,
                        'line-style': edge.style('line-style') || 'solid',
                        'target-arrow-shape': edge.style('target-arrow-shape') || 'triangle',
                        'target-arrow-color': edge.style('target-arrow-color') || lineColor,
                        'arrow-scale': parseFloat(edge.style('arrow-scale')) || 1
                    };

                    // 保存曲線特定參數
                    if (curveStyle === 'bezier' || curveStyle === 'unbundled-bezier') {
                        const distances = edge.style('control-point-distances');
                        const weights = edge.style('control-point-weights');
                        if (distances) {
                            const distStr = String(distances).replace(/[\[\]px]/g, '');
                            edgeData.style['control-point-distances'] = [parseFloat(distStr) || 0];
                        }
                        if (weights) {
                            const weightStr = String(weights).replace(/[\[\]]/g, '');
                            edgeData.style['control-point-weights'] = [parseFloat(weightStr) || 0.5];
                        }
                    } else if (curveStyle === 'taxi') {
                        const taxiDirection = edge.style('taxi-direction');
                        const taxiTurn = edge.style('taxi-turn');
                        if (taxiDirection) edgeData.style['taxi-direction'] = taxiDirection;
                        if (taxiTurn) edgeData.style['taxi-turn'] = parseFloat(taxiTurn);
                    }

                    edges.push(edgeData);
                    console.log('  🔗 收集邊:', edgeData.source, '→', edgeData.target);
                });

                // 收集畫布設定
                const canvasSettings = {
                    backgroundColor: canvasBackgroundColor,
                    backgroundId: currentBackgroundId, // 新系統：儲存底圖 ID 而非 base64
                    gridEnabled: gridEnabled,
                    gridStyle: gridStyle,
                    gridSpacing: gridSpacing,
                    paperType: paperType,
                    paperWidth: paperWidth,
                    paperHeight: paperHeight,
                    globalNodeBorder: globalNodeBorder
                };

                // 取得欄位取值設定
                const fieldReadConfig = cy.data('fieldReadConfig') || {};

                const cytoscape_config = {
                    nodes: nodes,
                    edges: edges,
                    relayPoints: relayPoints,
                    canvasSettings: canvasSettings,
                    fieldReadConfig: fieldReadConfig
                };

                console.log('📊 收集統計:');
                console.log('  節點數:', nodes.length);
                console.log('  邊數:', edges.length);
                console.log('  中繼點數:', relayPoints.length);
                console.log('  畫布設定:', canvasSettings);
                console.log('  欄位取值設定:', fieldReadConfig);
                console.log('📤 準備發送的配置:', cytoscape_config);

                const response = await fetch(`${window.__BP}/api/workflows/data/templates/${currentWorkflowId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        cytoscape_config: cytoscape_config,
                        graph: cytoscape_config  // 同時保存到 graph 以確保兼容性
                    })
                });

                console.log('📡 後端回應狀態:', response.status, response.statusText);
                const data = await response.json();
                console.log('📦 後端回應資料:', data);

                // 後端失敗時同樣回 JSON（含 success:false），只判斷 data 存在會誤判成功
                if (response.ok && data && data.success !== false) {
                    updateStatus(__('✅ 流程已儲存'));
                    console.log('✅ 儲存成功');

                    // 更新版本號顯示（含 revision）
                    if (data.version) {
                        document.getElementById('current-workflow-version').textContent =
                            `版本 ${data.version}${data.revision || ''}`;
                    }

                    // 標記為已成功儲存過
                    hasEverSaved = true;

                    // 儲存後清除 undo stack 和替換 buffer
                    clearUndoState();

                    // 更新初始狀態（儲存後沒有未儲存的變更）
                    updateInitialState();

                    // 清空狀態歷史記錄
                    setTimeout(() => {
                        clearStatusHistory();
                    }, 1000);

                    // 背景生成縮圖（前端）
                    // 這裡就同步把畫面截下來並綁定流程 id：呼叫端（例如流程樹系切換）
                    // 可能在下一刻就換掉 cy 與 currentWorkflowId，延遲到 setTimeout 才截圖
                    // 會把「這張圖」存到「下一張流程」上
                    const thumbTargetId = currentWorkflowId;
                    let thumbPngRaw = null;
                    try {
                        thumbPngRaw = cy ? cy.png({ output: 'base64', bg: 'white', full: true, scale: 2 }) : null;
                    } catch (e) {
                        console.warn('截取流程畫面失敗，改由縮圖函式自行截圖:', e);
                    }
                    setTimeout(() => {
                        generateAndSaveThumbnail(thumbTargetId, thumbPngRaw);
                    }, 100);

                    return true;
                } else {
                    const reason = (data && (data.error || data.message)) || `HTTP ${response.status}`;
                    updateStatus(__('儲存失敗：') + reason, 'warning');
                    console.log('❌ 儲存失敗：', response.status, data);
                    return false;
                }
            } catch (error) {
                console.error('❌ 儲存流程失敗:', error);
                console.error('錯誤堆疊:', error.stack);
                updateStatus(__('儲存失敗：') + error.message, 'warning');
                return false;
            }
        }

        // 生成並儲存縮圖（前端使用 Cytoscape PNG 導出 + Canvas 調整尺寸）
        // targetWorkflowId / prefetchedPngRaw 由呼叫端在「畫布還是那張圖」時綁定，
        // 不給就沿用當下狀態（儲存按鈕、saveAndClose 這類不會馬上換圖的路徑）
        async function generateAndSaveThumbnail(targetWorkflowId, prefetchedPngRaw) {
            const workflowId = targetWorkflowId || currentWorkflowId;
            if (!workflowId || (!prefetchedPngRaw && !cy)) {
                console.log('⚠️ 無法生成縮圖：缺少 workflow ID 或 Cytoscape 實例');
                return;
            }

            try {
                console.log('📸 開始生成縮圖...', workflowId);

                // 使用 Cytoscape 的 PNG 導出功能，full: true 會自動涵蓋所有元素範圍
                const pngBase64Raw = prefetchedPngRaw || cy.png({
                    output: 'base64',
                    bg: 'white',
                    full: true,
                    scale: 2
                });

                console.log('✓ Cytoscape PNG 已生成');

                // cy.png() 回傳的是純 base64，需要加上 data URI 前綴
                const pngBase64 = `data:image/png;base64,${pngBase64Raw}`;

                // 使用 Canvas 生成 600x400 (3:2 橫式) 縮圖
                // 用 Promise 包裝 img.onload，確保 saveAndClose 能正確等待上傳完成
                await new Promise((resolve, reject) => {
                    const img = new Image();
                    img.onload = async function() {
                        try {
                            console.log(`  原始尺寸: ${img.width}x${img.height}`);

                            const canvas = document.createElement('canvas');
                            canvas.width = 600;
                            canvas.height = 400;
                            const ctx = canvas.getContext('2d');
                            ctx.fillStyle = 'white';
                            ctx.fillRect(0, 0, 600, 400);

                            // 圖片內容內縮，保留白邊
                            const pad = 24;
                            const drawW = 600 - pad * 2;
                            const drawH = 400 - pad * 2;
                            const scale = Math.min(drawW / img.width, drawH / img.height);
                            const scaledWidth = img.width * scale;
                            const scaledHeight = img.height * scale;
                            const x = pad + (drawW - scaledWidth) / 2;
                            const y = pad + (drawH - scaledHeight) / 2;

                            ctx.drawImage(img, x, y, scaledWidth, scaledHeight);
                            const thumbnail_2x1 = canvas.toDataURL('image/png');

                            console.log('✓ 3:2 縮圖已生成 (600x400)');

                            // 上傳縮圖到後端
                            const response = await fetch(`${window.__BP}/api/workflows/data/templates/${workflowId}`, {
                                method: 'PUT',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    thumbnail_2x1: thumbnail_2x1
                                })
                            });

                            if (response.ok) {
                                console.log('✅ 縮圖已儲存到資料庫');
                            } else {
                                console.error('❌ 縮圖儲存失敗:', response.status);
                            }
                            resolve();
                        } catch (err) {
                            console.error('❌ 縮圖處理失敗:', err);
                            resolve(); // 不阻塞主流程
                        }
                    };

                    img.onerror = function(error) {
                        console.error('❌ 圖片載入失敗');
                        console.error('  錯誤:', error);
                        resolve(); // 不阻塞主流程
                    };

                    img.src = pngBase64;
                });

            } catch (error) {
                console.error('❌ 生成縮圖失敗:', error);
                // 縮圖失敗不影響主流程，只記錄錯誤
            }
        }
