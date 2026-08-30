/**
 * wf-node-parallel-join.js -- ParallelJoin 並行匯合節點配置
 * 從 wf-node-configs.js 拆分
 */

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
            const joinMode = document.querySelector('input[name="pjJoinMode"]:checked')?.value || 'ALL';
            const releaseOnce = document.getElementById('pjReleaseOnce')?.checked !== false;
            let timeoutMinutes = 0;
            let timeoutEdgeId = '';

            if (enableTimeout) {
                const minutesInput = document.getElementById('pjTimeoutMinutes');
                timeoutMinutes = parseInt(minutesInput?.value, 10);

                if (isNaN(timeoutMinutes) || timeoutMinutes < 1) {
                    updateStatus(__('逾時時間必須至少 1 分鐘'), 'warning');
                    return;
                }
                if (timeoutMinutes > 14400) {
                    updateStatus(__('逾時時間不能超過 14400 分鐘（10 天）'), 'warning');
                    return;
                }

                const edgeSelect = document.getElementById('pjTimeoutEdgeId');
                timeoutEdgeId = edgeSelect?.value || '';

                if (!timeoutEdgeId) {
                    updateStatus(__('啟用逾時時必須指定逾時去向'), 'warning');
                    return;
                }
            }

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                enable_timeout: enableTimeout,
                timeout_minutes: enableTimeout ? timeoutMinutes : 0,
                timeout_edge_id: enableTimeout ? timeoutEdgeId : '',
                join_mode: joinMode,
                release_once: releaseOnce
            };

            node.data('config', updatedConfig);

            if (enableTimeout) {
                updateStatus(`並行匯合設定已套用：逾時 ${timeoutMinutes} 分鐘`, 'success');
            } else {
                updateStatus(__('並行匯合設定已套用：無逾時限制'), 'success');
            }

            console.log('ParallelJoin 節點配置已更新:', {
                nodeId: nodeId,
                config: updatedConfig
            });
        }
        window.applyParallelJoinConfig = applyParallelJoinConfig;
