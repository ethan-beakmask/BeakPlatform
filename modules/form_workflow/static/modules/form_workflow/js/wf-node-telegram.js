/**
 * wf-node-telegram.js -- Telegram + SYS_Telegram 節點配置
 * 從 wf-node-configs.js 拆分
 * 包含企業級 Telegram 與系統級 SYS_Telegram
 */

        // ==================== 企業級 Telegram ====================

        // Telegram 設定組快取
        let telegramConfigsCache = null;

        // 載入可用的 Telegram 設定組
        async function loadTelegramConfigs(selectedConfigId, selectedChannelName) {
            const configSelect = document.getElementById('telegramConfigId');
            if (!configSelect) return;

            try {
                const response = await fetch(window.__BP + '/api/enterprise/data/settings/telegram/available');
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
                    const isSystemLabel = config.is_system ? __(' (系統)') : '';
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
                updateStatus(__('請選擇 Bot 設定組'), 'warning');
                return;
            }
            if (!channelName) {
                updateStatus(__('請選擇頻道'), 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus(__('請輸入訊息內容'), 'warning');
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
                // 與企業級共用同一支：回傳「自己企業 + 系統企業」的設定組。
                // SysTelegram 是 org_restricted 節點，只有獲授權的企業（出廠是系統
                // 預設企業）看得到這個面板，所以這裡拿到的就是系統級設定組。
                // 舊的 /api/system/data/settings/telegram 從來不存在（恆 404），
                // 症狀是下拉永遠顯示「無法載入設定」。
                const response = await fetch(window.__BP + '/api/enterprise/data/settings/telegram/available');
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
                updateStatus(__('請選擇系統級 Bot 設定組'), 'warning');
                return;
            }
            if (!channelName) {
                updateStatus(__('請選擇頻道'), 'warning');
                return;
            }
            if (!message || !message.trim()) {
                updateStatus(__('請輸入訊息內容'), 'warning');
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
