/**
 * wf-node-navbar-broadcast.js -- NavbarBroadcast 跑馬燈廣播節點配置
 * 從 wf-node-configs.js 拆分
 */

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
