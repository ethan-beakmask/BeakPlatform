/**
 * wf-node-sql-executor.js -- SQLExecutor SQL 查詢節點配置
 * 從 wf-node-configs.js 拆分
 */

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
