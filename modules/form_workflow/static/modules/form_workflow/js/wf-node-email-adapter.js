/**
 * wf-node-email-adapter.js -- EmailAdapter 企業郵件節點配置
 * 從 wf-node-configs.js 拆分
 */

        // SMTP 設定快取
        let emailAdapterSmtpConfigsCache = null;

        // 載入可用的 SMTP 設定
        async function loadEmailAdapterSmtpConfigs(selectedId) {
            const smtpSelect = document.getElementById('emailAdapterSmtpConfig');
            if (!smtpSelect) return;

            try {
                const response = await fetch('/bp/api/enterprise/data/settings/smtp/available');
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
                const response = await fetch('/bp/api/enterprise/data/settings/email-groups/available');
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
