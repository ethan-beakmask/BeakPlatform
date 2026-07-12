/**
 * wf-node-email-relay.js -- EmailRelay 系統郵件節點配置
 * 從 wf-node-configs.js 拆分
 */

        // 收件人群組快取
        let emailRelayGroupsCache = null;

        // 載入可用的收件人群組
        async function loadEmailRelayGroups(selectedIds) {
            const groupSelect = document.getElementById('emailRelayGroups');
            if (!groupSelect) return;

            try {
                const response = await fetch(window.__BP + '/api/enterprise/data/settings/email-groups/available');
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
                    const isSystem = group.scope === 'system' ? __(' (系統)') : '';
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
                updateStatus(__('請輸入郵件主旨'), 'warning');
                return;
            }
            if (!body || !body.trim()) {
                updateStatus(__('請輸入郵件內容'), 'warning');
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
                    updateStatus(__('請選擇至少一個收件人群組'), 'warning');
                    return;
                }
            } else if (recipientType === 'manual') {
                recipientManual = document.getElementById('emailRelayRecipientManual')?.value || '';
                if (!recipientManual.trim()) {
                    updateStatus(__('請輸入收件者 Email'), 'warning');
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
