/**
 * wf-accordion.js -- Accordion 節點設定面板
 * 從 workflow-main.js 拆分
 * 包含: showNodeInfo, subflow 管理, applyNodeBasicInfo, applySubprocessConfig, applyDelayConfig
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

        // 顯示節點資訊
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
                // 切換到表單欄位分頁
                switchTab('formfields');
                // 如果面板未展開，展開它
                if (!isPanelExpanded) {
                    toggleControlPanel();
                }
                // 如果表單欄位尚未載入，且只有一張配對表單，自動載入它
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
                // 自動掃描所有變數
                setTimeout(() => reloadAllVars(), 100);
            }

            const typeNames = {
                // 標準命名（依 workflow_node_definitions 表）
                'Start': '開始節點',
                'End': '結束節點',
                'Switch': '條件分支',
                'Subflow': '子流程',
                'Converge': '匯聚節點',
                'Delay': '暫停',
                'OpSet': '設定變數',
                'FormAdapter': '簽核',
                'EmailAdapter': '郵件通知',
                'SQLExecutor': 'SQL 執行器',
                'Abandon': '放棄流程',
                'Telegram': 'Telegram 通知',
                'EmailRelay': '系統郵件',
                'NavbarBroadcast': '跑馬燈廣播',
                'AlertBroadcast': '緊急廣播'
            };

            const description = node.data('description') || '';

            // 有額外設定的節點類型（這些節點有自己的「套用」按鈕）
            const nodesWithSettings = [
                'Subflow', 'Delay', 'OpFieldWrite', 'OpSet', 'Telegram',
                'SysTelegram', 'EmailRelay', 'EmailAdapter', 'Branch',
                'FormAdapter', 'End', 'Converge', 'SqlExecutor',
                'ParallelFork', 'ParallelJoin',
                'NavbarBroadcast', 'AlertBroadcast'
            ];
            const hasAdditionalSettings = nodesWithSettings.includes(type);

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

            // 子流程節點配置
            if (type === 'Subflow') {
                const currentConfig = node.data('config') || {};
                const currentChildFlowId = currentConfig.childFlowId || '';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-sitemap"></i> 子流程說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">子流程節點可以呼叫其他已定義的工作流程，實現模組化設計和流程重用。</p>

                            <strong style="color: #333;">特性：</strong>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>變數自動共享：子流程與主流程共用變數</li>
                                <li>專屬綁定：子流程專屬於當前主流程</li>
                                <li>遞迴限制：最多支援 5 層嵌套</li>
                            </ul>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 子流程配置
                        </h4>
                        <div id="currentSubflowDisplay" style="margin-bottom: 12px; padding: 8px 12px; background: #f0f4ff; border-radius: 4px; font-size: 13px;">
                            目前：<strong>${currentChildFlowId ? '載入中...' : '未選擇'}</strong>
                        </div>
                        <input type="hidden" id="childFlowSelect" value="${currentChildFlowId}">
                        <div style="margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <strong style="font-size: 13px;">專屬子流程</strong>
                                <button class="btn-secondary" onclick="createNewSubflow('${nodeId}')" style="padding: 2px 10px; font-size: 12px;">
                                    <i class="fas fa-plus"></i> 新增
                                </button>
                            </div>
                            <div id="dedicatedSubflowList" style="border: 1px solid #e0e0e0; border-radius: 4px; max-height: 180px; overflow-y: auto;">
                                <div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">載入中...</div>
                            </div>
                        </div>
                        <div>
                            <strong style="font-size: 13px; display: block; margin-bottom: 6px;">通用子流程</strong>
                            <div id="commonSubflowList" style="border: 1px solid #e0e0e0; border-radius: 4px; max-height: 220px; overflow-y: auto;">
                                <div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">載入中...</div>
                            </div>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-exchange-alt"></i> 參數映射（選填）
                        </h4>
                        <p style="font-size: 12px; color: #666; margin-bottom: 15px;">
                            為共用子流程配置變數映射，專屬子流程會自動共享變數無需配置。
                        </p>

                        <div style="margin-bottom: 20px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                <strong style="font-size: 13px;">輸入參數（父流程 → 子流程）</strong>
                                <button onclick="addInputMapping('${nodeId}')" style="padding: 4px 10px; font-size: 11px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                    <i class="fas fa-plus"></i> 添加
                                </button>
                            </div>
                            <div id="inputMappingContainer" style="border: 1px solid #e5e7eb; border-radius: 4px; max-height: 200px; overflow-y: auto;">
                                <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                                    <thead style="background: #f9fafb; position: sticky; top: 0;">
                                        <tr>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">父流程變數</th>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">子流程變數</th>
                                            <th style="padding: 8px; text-align: center; border-bottom: 1px solid #e5e7eb; width: 60px;">操作</th>
                                        </tr>
                                    </thead>
                                    <tbody id="inputMappingTable">
                                        <tr>
                                            <td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <div style="margin-bottom: 15px;">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                                <strong style="font-size: 13px;">輸出參數（子流程 → 父流程）</strong>
                                <button onclick="addOutputMapping('${nodeId}')" style="padding: 4px 10px; font-size: 11px; background: #10b981; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                    <i class="fas fa-plus"></i> 添加
                                </button>
                            </div>
                            <div id="outputMappingContainer" style="border: 1px solid #e5e7eb; border-radius: 4px; max-height: 200px; overflow-y: auto;">
                                <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                                    <thead style="background: #f9fafb; position: sticky; top: 0;">
                                        <tr>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">子流程變數</th>
                                            <th style="padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb;">父流程變數</th>
                                            <th style="padding: 8px; text-align: center; border-bottom: 1px solid #e5e7eb; width: 60px;">操作</th>
                                        </tr>
                                    </thead>
                                    <tbody id="outputMappingTable">
                                        <tr>
                                            <td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applySubprocessConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // 匯聚節點配置
            if (type === 'Converge') {
                const currentConfig = node.data('config') || {};
                const currentMode = currentConfig.mode || 'ALL';
                const isAnyMode = currentMode === 'ANY';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-compress-arrows-alt"></i> 匯聚節點說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">等待多條前驅路徑完成後匯聚，可選擇等待全部或任一完成。</p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 匯聚模式
                        </h4>
                        <div style="display: flex; flex-direction: column; gap: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; border: 2px solid ${!isAnyMode ? '#9C27B0' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${!isAnyMode ? '#F3E5F5' : 'white'};">
                                <input type="radio" name="convergeMode" value="ALL" ${!isAnyMode ? 'checked' : ''}
                                       onchange="updateConvergeMode('${nodeId}', 'ALL')"
                                       style="margin-right: 12px; transform: scale(1.2);">
                                <div>
                                    <div style="font-weight: bold; color: #7B1FA2;">
                                        <i class="fas fa-users"></i> 等待全部 (ALL)
                                    </div>
                                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                                        等待所有前驅節點完成後才繼續下一步
                                    </div>
                                </div>
                            </label>
                            <label style="display: flex; align-items: center; padding: 12px; border: 2px solid ${isAnyMode ? '#FF9800' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${isAnyMode ? '#FFF3E0' : 'white'};">
                                <input type="radio" name="convergeMode" value="ANY" ${isAnyMode ? 'checked' : ''}
                                       onchange="updateConvergeMode('${nodeId}', 'ANY')"
                                       style="margin-right: 12px; transform: scale(1.2);">
                                <div>
                                    <div style="font-weight: bold; color: #F57C00;">
                                        <i class="fas fa-user"></i> 任一完成 (ANY)
                                    </div>
                                    <div style="font-size: 12px; color: #666; margin-top: 4px;">
                                        任一前驅節點完成就繼續下一步
                                    </div>
                                </div>
                            </label>
                        </div>
                        <p style="font-size: 11px; color: #999; margin-top: 15px;">
                            <i class="fas fa-info-circle"></i> 節點顏色會根據模式自動變更：紫色=等待全部，橘色=任一完成
                        </p>
                    </div>
                `;
            }

            // Delay 暫停節點配置
            if (type === 'Delay') {
                const currentConfig = node.data('config') || {};
                const delaySeconds = currentConfig.delay_seconds || 60;

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #667eea;">
                            <i class="fas fa-clock"></i> 暫停節點說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">暫停節點會讓流程等待指定的秒數後再繼續執行下一個節點。</p>
                            <p style="margin: 10px 0;">適用場景：</p>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>等待外部系統處理完成</li>
                                <li>控制 API 呼叫頻率</li>
                                <li>排程延遲執行</li>
                            </ul>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #667eea;">
                            <i class="fas fa-cog"></i> 延遲設定
                        </h4>
                        <div style="margin-bottom: 15px;">
                            <strong>延遲秒數：</strong><br>
                            <input type="number" id="delaySeconds" value="${delaySeconds}"
                                   min="0" max="86400"
                                   style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                            <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                <i class="fas fa-info-circle"></i> 最大 86400 秒（24 小時）
                            </p>
                        </div>
                        <div style="background: #f5f5f5; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                            <div style="font-size: 12px; color: #666;">
                                <strong>換算：</strong>
                                <span id="delayTimeDisplay">${Math.floor(delaySeconds/3600)}小時 ${Math.floor((delaySeconds%3600)/60)}分 ${delaySeconds%60}秒</span>
                            </div>
                        </div>
                        <button class="btn-primary" onclick="applyDelayConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // SqlExecutor SQL 查詢節點配置
            if (type === 'SqlExecutor') {
                const currentConfig = node.data('config') || {};
                const queryType = currentConfig.query_type || '';
                const resultVar = currentConfig.result_var || '';

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #4a90a4;">
                            <i class="fas fa-database"></i> SQL 查詢說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">此節點執行預定義的安全 SQL 查詢，自動依據表單發動者的企業進行資料隔離。</p>
                            <p style="margin: 10px 0; padding: 8px; background: #e8f5e9; border-radius: 4px;">
                                <i class="fas fa-shield-alt" style="color: #4caf50;"></i>
                                <strong>安全機制：</strong>org_secure_code 會自動注入，確保只能查詢同企業的資料。
                            </p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #4a90a4;">
                            <i class="fas fa-cog"></i> 查詢設定
                        </h4>
                        <div style="margin-bottom: 15px;">
                            <strong>查詢類型：</strong><br>
                            <select id="sqlQueryType" onchange="updateSQLQueryDescription()" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px;">
                                <option value="">請選擇查詢類型...</option>
                                <option value="get_org_users" ${queryType === 'get_org_users' ? 'selected' : ''}>取得企業用戶清單</option>
                                <option value="get_org_user_count" ${queryType === 'get_org_user_count' ? 'selected' : ''}>取得企業用戶數量</option>
                                <option value="get_org_active_users" ${queryType === 'get_org_active_users' ? 'selected' : ''}>取得企業活躍用戶</option>
                            </select>
                        </div>
                        <div style="margin-bottom: 15px;">
                            <strong>結果變數：</strong><br>
                            <input type="text" id="sqlResultVar" value="${resultVar}" placeholder="例：user_list"
                                   style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px; box-sizing: border-box;">
                            <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                <i class="fas fa-info-circle"></i> 查詢結果將存入此變數，可在後續節點使用 \${變數名} 引用
                            </p>
                        </div>
                        <div id="sqlPreviewArea" style="background: #f5f5f5; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 12px;">
                            <strong>查詢說明：</strong>
                            <div id="sqlQueryDescription" style="color: #666; margin-top: 5px;">請選擇查詢類型</div>
                        </div>
                        <button class="btn-primary" onclick="applySQLExecutorConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
                // 初始化描述（延遲以確保 DOM 已渲染）
                setTimeout(() => updateSQLQueryDescription(), 100);
            }

            // OPSET 變數設定節點配置
            if (type === 'OpSet') {
                const currentConfig = node.data('config') || {};
                const operations = currentConfig.operations || [];

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div id="opsetOperationsList" style="margin-bottom: 8px;">
                            <!-- 操作項目會動態生成 -->
                        </div>

                        <div style="display: flex; gap: 6px;">
                            <button class="btn-secondary" onclick="addOpsetOperation()" style="flex: 1; padding: 6px; font-size: 11px;">
                                <i class="fas fa-plus"></i> 新增
                            </button>
                            <button class="btn-primary" onclick="applyOpsetConfig('${nodeId}')" style="flex: 1; padding: 6px; font-size: 11px;">
                                <i class="fas fa-check"></i> 套用
                            </button>
                        </div>
                    </div>

                    <!-- 運算說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchOpsetHelpTab('ops')" id="opsetTabOps" style="flex: 1; padding: 5px; border: none; background: #EC4899; color: white; font-size: 10px; cursor: pointer;">操作類型</button>
                            <button onclick="switchOpsetHelpTab('examples')" id="opsetTabExamples" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">範例</button>
                            <button onclick="switchOpsetHelpTab('vars')" id="opsetTabVars" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">變數引用</button>
                        </div>

                        <!-- 操作類型說明 -->
                        <div id="opsetContentOps" style="padding: 8px; font-size: 10px; line-height: 1.4;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #fce4ec;"><code>=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">直接設定值</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e8f5e9;"><code>運算</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>表達式</b> 如 <code>1+2</code>, <code>\${a}*\${b}</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+ - × ÷</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">目標 運算 值（累加模式）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e3f2fd;"><code>連接</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">字串連接</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+1 -1</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">遞增/遞減（不需值）</td></tr>
                            </table>
                        </div>

                        <!-- 範例 -->
                        <div id="opsetContentExamples" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #e8f5e9; border-radius: 3px;">
                                <b>✨ 表達式運算（推薦）</b><br>
                                <code>result</code> 運算 → <code>1 + 2</code> 結果: 3<br>
                                <code>total</code> 運算 → <code>\${price} * \${qty}</code><br>
                                <code>avg</code> 運算 → <code>(\${a} + \${b}) / 2</code>
                            </div>
                            <div style="margin-bottom: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>組合訊息</b><br>
                                <code>msg</code> = → <code>金額：</code><br>
                                <code>msg</code> 連接 → <code>\${amount}</code>
                            </div>
                            <div style="padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>計數器</b><br>
                                <code>counter</code> +1
                            </div>
                        </div>

                        <!-- 變數引用 -->
                        <div id="opsetContentVars" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 3px 4px; border: 1px solid #eee;"><code>\${var}</code></td><td style="padding: 3px 4px; border: 1px solid #eee;">工作流程變數</td></tr>
                                <tr><td style="padding: 3px 4px; border: 1px solid #eee;"><code>\${form.field}</code></td><td style="padding: 3px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #e8f5e9; border-radius: 3px; font-size: 9px;">
                                <b>運算支援：</b> + - * / // % **（次方）<br>
                                括號優先：<code>(\${a} + \${b}) * 2</code>
                            </div>
                        </div>
                    </div>
                `;

                // 延遲渲染操作列表
                setTimeout(() => renderOpsetOperations(operations), 50);
            }

            // OP_FIELDWRITE 表單寫值節點配置
            if (type === 'OpFieldWrite') {
                const currentConfig = node.data('config') || {};
                const targetField = currentConfig.target_field || '';
                const content = currentConfig.content || '';
                const contentType = currentConfig.content_type || 'text';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #10B981; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-pen"></i> 表單寫值設定
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">目標欄位 <span style="color: #dc3545;">*</span></label>
                            <div style="display: flex; gap: 4px;">
                                <select id="fieldWriteTargetField" style="flex: 1; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                    <option value="">載入中...</option>
                                </select>
                                <button type="button" onclick="reloadFieldWriteTargetFields()" style="padding: 6px 10px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;" title="重新載入欄位清單">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                            <div style="font-size: 9px; color: #999; margin-top: 2px;">
                                <i class="fas fa-info-circle"></i> 點擊 reload 按鈕重新載入欄位
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">
                                寫入內容 <span style="color: #dc3545;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('fieldWriteContent'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="fieldWriteContent" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入內容或使用變數...&#10;支援換行：\\n">${content}</textarea>
                            <div style="font-size: 9px; color: #666; margin-top: 2px;">
                                <i class="fas fa-lightbulb"></i> 使用 <code>\${f.欄位key}</code> 讀取表單值，<code>\${v.變數名}</code> 讀取流程變數
                            </div>
                        </div>

                        <div style="margin-bottom: 10px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">內容格式</label>
                            <div style="display: flex; gap: 12px;">
                                <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer;">
                                    <input type="radio" name="fieldWriteContentType" value="text" ${contentType === 'text' ? 'checked' : ''} style="margin-right: 4px;">
                                    Text <span style="color: #999; font-size: 9px; margin-left: 2px;">(\\n→換行)</span>
                                </label>
                                <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer;">
                                    <input type="radio" name="fieldWriteContentType" value="html" ${contentType === 'html' ? 'checked' : ''} style="margin-right: 4px;">
                                    HTML <span style="color: #999; font-size: 9px; margin-left: 2px;">(\\n→&lt;br&gt;)</span>
                                </label>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyFieldWriteConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px; background: #10B981;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="background: #e8f4fd; padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">
                            <span style="font-size: 11px; font-weight: bold; color: #1976d2;"><i class="fas fa-code"></i> 變數語法 (v2)</span>
                        </div>
                        <div style="padding: 8px; font-size: 10px;">
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">格式</th>
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">說明</th>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${f.欄位key}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單欄位值</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${fi.serial}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流水號</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${fi.applicant}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">申請人</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${v.變數名}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程變數</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${wi.name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程名稱</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${t.now}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">當前時間</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入目標欄位選項
                // 延長等待時間，讓表單欄位有足夠時間載入
                setTimeout(() => loadFieldWriteTargetFields(targetField), 500);
            }

            // FormAdapter 簽核節點配置 — 右側面板只顯示摘要，設定在 Modal 中
            if (type === 'FormAdapter') {
                const currentConfig = node.data('config') || {};
                const assigneeType = currentConfig.assignee_type || 'INITIATOR';
                const assigneeLabel = currentConfig.assignee_label || '';
                const assigneeListConfig = currentConfig.assignee_list || [];
                const selectionMode = currentConfig.selection_mode || 'single';
                const allowComment = currentConfig.allow_comment !== false;
                const minCommentLength = currentConfig.min_comment_length !== undefined
                    ? parseInt(currentConfig.min_comment_length) || 0
                    : (currentConfig.require_comment === true ? 1 : 0);
                const useCustomDecisions = currentConfig.use_custom_decisions || false;
                const decisionCount = (currentConfig.decision_options || []).length;
                const inputVarCount = (currentConfig.input_variables || []).length;

                const typeLabels = {
                    'INITIATOR': '發起人',
                    'USER': '指定用戶',
                    'ROLE': '指定角色',
                    'DEPARTMENT': '指定部門',
                    'DYNAMIC': '動態'
                };

                // 簽核者摘要
                let assigneeSummary = typeLabels[assigneeType] || assigneeType;
                if (assigneeLabel) {
                    assigneeSummary += ' - ' + (assigneeLabel.length > 12 ? assigneeLabel.substring(0, 12) + '...' : assigneeLabel);
                }
                if (assigneeType === 'USER' && assigneeListConfig.length > 1) {
                    assigneeSummary += ` (${assigneeListConfig.length}人)`;
                }

                info += `
                    <div style="background: white; padding: 12px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-size: 12px; font-weight: 600; color: #667eea; margin-bottom: 10px;">
                            <i class="fas fa-user-check"></i> 簽核節點摘要
                        </div>

                        <div class="fa-summary-row">
                            <span class="fa-summary-label">簽核者</span>
                            <span class="fa-summary-value">${assigneeSummary}</span>
                        </div>
                        <div class="fa-summary-row">
                            <span class="fa-summary-label">選擇模式</span>
                            <span class="fa-summary-value">${selectionMode === 'single' ? '單選' : '複選'}</span>
                        </div>
                        <div class="fa-summary-row">
                            <span class="fa-summary-label">備註</span>
                            <span class="fa-summary-value">${allowComment ? (minCommentLength > 0 ? '必填 (' + minCommentLength + '字)' : '選填') : '關閉'}</span>
                        </div>
                        <div class="fa-summary-row">
                            <span class="fa-summary-label">決策控制器</span>
                            <span class="fa-summary-value">${useCustomDecisions ? decisionCount + ' 個選項' : '未啟用'}</span>
                        </div>
                        ${inputVarCount > 0 ? `
                        <div class="fa-summary-row">
                            <span class="fa-summary-label">來向變數</span>
                            <span class="fa-summary-value">${inputVarCount} 個</span>
                        </div>` : ''}

                        <button class="btn-primary" onclick="openFormAdapterModal('${nodeId}')" style="width: 100%; margin-top: 12px;">
                            <i class="fas fa-cog"></i> 打開設定
                        </button>
                    </div>
                `;
            }

            // Telegram 通知節點配置
            if (type === 'Telegram') {
                const currentConfig = node.data('config') || {};
                const configId = currentConfig.config_id || '';
                const channelName = currentConfig.channel_name || '';
                const message = currentConfig.message || '';
                const parseMode = currentConfig.parse_mode || 'HTML';
                const disableNotification = currentConfig.disable_notification || false;
                const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">Bot 設定組</label>
                                <select id="telegramConfigId" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" onchange="updateTelegramChannels()">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">頻道</label>
                                <select id="telegramChannelName" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                    <option value="">請先選擇 Bot...</option>
                                </select>
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">訊息內容 <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px; margin-left: 4px;">\${v.name}</code> <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px; margin-left: 2px;">\${f.key}</code>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('telegramMessage'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="telegramMessage" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入訊息內容...">${message}</textarea>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="telegramParseMode" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="HTML" ${parseMode === 'HTML' ? 'selected' : ''}>HTML</option>
                                    <option value="Markdown" ${parseMode === 'Markdown' ? 'selected' : ''}>Markdown</option>
                                    <option value="MarkdownV2" ${parseMode === 'MarkdownV2' ? 'selected' : ''}>MarkdownV2</option>
                                </select>
                            </div>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="telegramDisableNotification" ${disableNotification ? 'checked' : ''} style="margin-right: 4px;">
                                靜音
                            </label>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="telegramDisableWebPagePreview" ${disableWebPagePreview ? 'checked' : ''} style="margin-right: 4px;">
                                禁預覽
                            </label>
                        </div>

                        <button class="btn-primary" onclick="applyTelegramConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 格式說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchTgFormatTab('html')" id="tgTabHtml" style="flex: 1; padding: 6px 8px; border: none; background: #667eea; color: white; font-size: 11px; cursor: pointer;">HTML</button>
                            <button onclick="switchTgFormatTab('md')" id="tgTabMd" style="flex: 1; padding: 6px 8px; border: none; background: transparent; color: #666; font-size: 11px; cursor: pointer;">Markdown</button>
                            <button onclick="switchTgFormatTab('md2')" id="tgTabMd2" style="flex: 1; padding: 6px 8px; border: none; background: transparent; color: #666; font-size: 11px; cursor: pointer;">MarkdownV2</button>
                        </div>

                        <!-- HTML 說明 -->
                        <div id="tgContentHtml" style="padding: 8px; font-size: 10px; line-height: 1.5;">
                            <div style="color: #28a745; font-weight: bold; margin-bottom: 4px;">✓ 建議使用，最簡單</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;b&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;i&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;u&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><u>底線</u></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;s&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><s>刪除線</s></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;code&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;pre&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">程式碼區塊</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;a href=""&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">📋 &lt;b&gt;通知&lt;/b&gt;

申請人：&lt;code&gt;\${name}&lt;/code&gt;
金額：&lt;b&gt;\${amount}&lt;/b&gt; 元</div>
                            <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">⚠ 不支援: &lt;font&gt;, &lt;br&gt;（直接換行即可）</div>
                        </div>

                        <!-- Markdown 說明 -->
                        <div id="tgContentMd" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                            <div style="color: #ffc107; font-weight: bold; margin-bottom: 4px;">⚡ 基本格式，功能較少</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>*文字*</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>_文字_</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\`code\`</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>[文字](URL)</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">📋 *通知*

申請人：\`\${name}\`
金額：*\${amount}* 元</div>
                            <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">⚠ 不支援: 底線、刪除線</div>
                        </div>

                        <!-- MarkdownV2 說明 -->
                        <div id="tgContentMd2" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                            <div style="color: #dc3545; font-weight: bold; margin-bottom: 4px;">⚠ 功能最多但需跳脫特殊字元</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>*文字*</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>_文字_</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>__文字__</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><u>底線</u></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>~文字~</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><s>刪除線</s></td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>||文字||</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">隱藏文字</td></tr>
                            </table>
                            <div style="margin-top: 6px; padding: 4px; background: #fff3cd; border-radius: 3px; font-size: 9px;">
                                <b>必須跳脫的字元：</b><br>
                                <code>_ * [ ] ( ) ~ \` > # + - = | { } . !</code><br>
                                例：<code>100.5</code> → <code>100\\.5</code>
                            </div>
                        </div>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; margin-top: 8px; overflow: hidden;">
                        <div style="background: #e8f4fd; padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">
                            <span style="font-size: 11px; font-weight: bold; color: #1976d2;"><i class="fas fa-code"></i> 變數語法 (v2)</span>
                        </div>
                        <div style="padding: 8px; font-size: 10px;">
                            <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                                <tr style="background: #f5f5f5;">
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">格式</th>
                                    <th style="padding: 4px; border: 1px solid #e0e0e0; text-align: left;">說明</th>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${f.欄位key}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">表單欄位值</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${fi.serial}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流水號</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${fi.applicant}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">申請人</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${v.變數名}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程變數</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${wi.name}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">流程名稱</td>
                                </tr>
                                <tr>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;"><code>\${t.now}</code></td>
                                    <td style="padding: 3px 4px; border: 1px solid #e0e0e0;">當前時間</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入可用的 Telegram 設定
                setTimeout(() => loadTelegramConfigs(configId || null, channelName), 100);
            }

            // SYS_Telegram 系統級 Telegram 通知節點配置
            if (type === 'SysTelegram') {
                const currentConfig = node.data('config') || {};
                const configId = currentConfig.config_id || '';
                const channelName = currentConfig.channel_name || '';
                const message = currentConfig.message || '';
                const parseMode = currentConfig.parse_mode || 'HTML';
                const disableNotification = currentConfig.disable_notification || false;
                const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

                info += `
                    <div style="background: #FDF2F8; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 2px solid #DB2777;">
                        <div style="font-weight: bold; color: #DB2777; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-shield-alt"></i> 系統級 Telegram 設定
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">系統 Bot 設定組</label>
                                <select id="sysTelegramConfigId" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 12px;" onchange="updateSysTelegramChannels()">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">頻道</label>
                                <select id="sysTelegramChannelName" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 12px;">
                                    <option value="">請先選擇 Bot...</option>
                                </select>
                            </div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">訊息內容 <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px; margin-left: 4px;">\${v.name}</code> <code style="font-size: 10px; background: #f0f0f0; padding: 1px 4px; border-radius: 2px; margin-left: 2px;">\${f.key}</code>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('sysTelegramMessage'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="sysTelegramMessage" rows="5"
                                      style="width: 100%; padding: 6px; border: 1px solid #DB2777; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;"
                                      placeholder="輸入訊息內容...">${message}</textarea>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="sysTelegramParseMode" style="width: 100%; padding: 5px; border: 1px solid #DB2777; border-radius: 4px; font-size: 11px;">
                                    <option value="HTML" ${parseMode === 'HTML' ? 'selected' : ''}>HTML</option>
                                    <option value="Markdown" ${parseMode === 'Markdown' ? 'selected' : ''}>Markdown</option>
                                    <option value="MarkdownV2" ${parseMode === 'MarkdownV2' ? 'selected' : ''}>MarkdownV2</option>
                                </select>
                            </div>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="sysTelegramDisableNotification" ${disableNotification ? 'checked' : ''} style="margin-right: 4px;">
                                靜音
                            </label>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; padding-top: 16px;">
                                <input type="checkbox" id="sysTelegramDisableWebPagePreview" ${disableWebPagePreview ? 'checked' : ''} style="margin-right: 4px;">
                                禁預覽
                            </label>
                        </div>

                        <button class="btn-primary" onclick="applySysTelegramConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px; background: #DB2777;">
                            <i class="fas fa-check"></i> 套用
                        </button>

                        <!-- 變數說明 -->
                        <div style="margin-top: 8px; padding: 8px; background: #f8f9fa; border-radius: 4px; border: 1px solid #e0e0e0;">
                            <div style="font-size: 10px; font-weight: bold; color: #1976d2; margin-bottom: 4px;"><i class="fas fa-code"></i> 變數語法 (v2)</div>
                            <table style="width: 100%; border-collapse: collapse; font-size: 9px;">
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${f.欄位key}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">表單欄位值</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${fi.serial}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流水號</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${fi.applicant}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">申請人</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${v.變數名}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程變數</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${wi.name}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程名稱</td></tr>
                                <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${t.now}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">當前時間</td></tr>
                            </table>
                        </div>
                    </div>
                `;

                // 載入系統級 Telegram 設定
                setTimeout(() => loadSysTelegramConfigs(configId || null, channelName), 100);
            }

            // EmailRelay 系統郵件節點配置
            if (type === 'EmailRelay') {
                const currentConfig = node.data('config') || {};
                const recipientType = currentConfig.recipient_type || 'group';
                const recipientGroups = currentConfig.recipient_groups || [];
                const recipientManual = currentConfig.recipient_manual || '';
                const ccManual = currentConfig.cc_manual || '';
                const subject = currentConfig.subject || '';
                const body = currentConfig.body || '';
                const bodyType = currentConfig.body_type || 'plain';
                const priority = currentConfig.priority || 'normal';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #16A34A; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-envelope"></i> 系統郵件設定
                        </div>

                        <!-- 收件者類型 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者來源</label>
                            <select id="emailRelayRecipientType" onchange="toggleEmailRelayRecipientFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="group" ${recipientType === 'group' ? 'selected' : ''}>收件人群組</option>
                                <option value="manual" ${recipientType === 'manual' ? 'selected' : ''}>手動輸入</option>
                            </select>
                        </div>

                        <!-- 群組選擇 -->
                        <div id="emailRelayGroupField" style="margin-bottom: 8px; ${recipientType !== 'group' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇群組（可多選）</label>
                            <select id="emailRelayGroups" multiple style="width: 100%; height: 80px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="">載入中...</option>
                            </select>
                        </div>

                        <!-- 手動輸入收件者 -->
                        <div id="emailRelayManualField" style="margin-bottom: 8px; ${recipientType !== 'manual' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者 Email（逗號或換行分隔，支援變數 <code>\${var}</code>）</label>
                            <textarea id="emailRelayRecipientManual" rows="2" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; font-family: monospace;">${recipientManual}</textarea>
                        </div>

                        <!-- 副本 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">CC 副本（選填）</label>
                            <input type="text" id="emailRelayCcManual" placeholder="逗號分隔，支援變數" value="${ccManual}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                        </div>

                        <!-- 主旨 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">主旨 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('emailRelaySubject'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <input type="text" id="emailRelaySubject" placeholder="支援變數 \${v.name}, \${f.key}" value="${subject}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <!-- 內容 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">內容 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('emailRelayBody'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="emailRelayBody" rows="5" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;" placeholder="輸入郵件內容...">${body}</textarea>
                        </div>

                        <!-- 格式與優先級 -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="emailRelayBodyType" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="plain" ${bodyType === 'plain' ? 'selected' : ''}>純文字</option>
                                    <option value="html" ${bodyType === 'html' ? 'selected' : ''}>HTML</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">優先級</label>
                                <select id="emailRelayPriority" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                    <option value="normal" ${priority === 'normal' ? 'selected' : ''}>一般</option>
                                    <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                                </select>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyEmailRelayConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; padding: 8px;">
                        <div style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 6px;">可用變數 (v2)</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #f0fdf4;"><code>\${v.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程變數</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${f.key}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>\${wi.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程名稱</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${t.now}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">當前時間</td></tr>
                        </table>
                    </div>
                `;

                // 載入可用的收件人群組
                setTimeout(() => loadEmailRelayGroups(recipientGroups), 100);
            }

            // NavbarBroadcast 跑馬燈廣播節點配置
            if (type === 'NavbarBroadcast') {
                const currentConfig = node.data('config') || {};
                const mode = currentConfig.mode || 'start';
                const broadcastCode = currentConfig.broadcast_code || '';
                const message = currentConfig.message || '';
                const textColor = currentConfig.text_color || '#000000';
                const bgColor = currentConfig.bg_color || '#FDE047';
                const displaySeconds = currentConfig.display_seconds || 5;
                const durationMinutes = currentConfig.duration_minutes || 0;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #B45309; font-size: 12px; margin-bottom: 8px;">
                            <i class="ri-broadcast-line"></i> 跑馬燈廣播設定
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">模式</label>
                            <select id="nbMode" onchange="toggleNbFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="start" ${mode === 'start' ? 'selected' : ''}>StartBroadcast - 啟動跑馬燈</option>
                                <option value="end" ${mode === 'end' ? 'selected' : ''}>EndBroadcast - 停止跑馬燈</option>
                            </select>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">廣播代碼 <span style="color: #DC2626;">*</span></label>
                            <input type="text" id="nbBroadcastCode" value="${broadcastCode}" placeholder="唯一代碼，EndBroadcast 用此對應" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                            <div style="font-size: 10px; color: #888; margin-top: 2px;">EndBroadcast 填入相同代碼以停止對應跑馬燈</div>
                        </div>

                        <div id="nbStartFields" style="${mode === 'end' ? 'display: none;' : ''}">
                            <div style="margin-bottom: 8px;">
                                <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">訊息內容 <span style="color: #DC2626;">*</span>
                                    <button type="button" onclick="VarPicker.open(this, document.getElementById('nbMessage'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                                </label>
                                <textarea id="nbMessage" rows="3" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; resize: vertical;" placeholder="跑馬燈顯示的訊息...">${message}</textarea>
                            </div>

                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                                <div>
                                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">文字顏色</label>
                                    <input type="color" id="nbTextColor" value="${textColor}" style="width: 100%; height: 32px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer;">
                                </div>
                                <div>
                                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">背景顏色</label>
                                    <input type="color" id="nbBgColor" value="${bgColor}" style="width: 100%; height: 32px; border: 1px solid #ddd; border-radius: 4px; cursor: pointer;">
                                </div>
                            </div>

                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                                <div>
                                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">每則顯示秒數</label>
                                    <input type="number" id="nbDisplaySeconds" value="${displaySeconds}" min="3" max="60" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                </div>
                                <div>
                                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">自動過期(分鐘)</label>
                                    <input type="number" id="nbDurationMinutes" value="${durationMinutes}" min="0" placeholder="0=不過期" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                    <div style="font-size: 10px; color: #888; margin-top: 2px;">0 或留空=持續到 EndBroadcast</div>
                                </div>
                            </div>

                            <!-- 預覽 -->
                            <div id="nbPreview" style="margin-bottom: 8px; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; overflow: hidden; white-space: nowrap; background: ${bgColor}; color: ${textColor};">
                                ${message || '預覽：跑馬燈訊息將顯示在此'}
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyNavbarBroadcastConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // AlertBroadcast 緊急廣播節點配置
            if (type === 'AlertBroadcast') {
                const currentConfig = node.data('config') || {};
                const broadcastCode = currentConfig.broadcast_code || '';
                const title = currentConfig.title || '';
                const message = currentConfig.message || '';
                const requireAck = currentConfig.require_ack !== false;
                const targetType = currentConfig.target_type || 'all';
                const targetRoles = currentConfig.target_roles || [];
                const targetDepartments = currentConfig.target_departments || [];
                const includeChildren = currentConfig.include_children !== false;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #DC2626; font-size: 12px; margin-bottom: 8px;">
                            <i class="ri-alarm-warning-line"></i> 緊急廣播設定
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">廣播代碼 <span style="color: #DC2626;">*</span></label>
                            <input type="text" id="abBroadcastCode" value="${broadcastCode}" placeholder="唯一識別代碼" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">標題 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('abTitle'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <input type="text" id="abTitle" value="${title}" placeholder="大字標題" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">訊息內容 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('abMessage'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="abMessage" rows="4" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; resize: vertical;" placeholder="支援 HTML：&lt;b&gt;粗體&lt;/b&gt;、&lt;br&gt;換行">${message}</textarea>
                            <div style="font-size: 10px; color: #888; margin-top: 2px;">支援 HTML 標籤：&lt;b&gt; &lt;i&gt; &lt;br&gt; &lt;p&gt; &lt;ul&gt; &lt;li&gt;</div>
                        </div>

                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">目標對象</label>
                            <select id="abTargetType" onchange="toggleAbTargetFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="all" ${targetType === 'all' ? 'selected' : ''}>全企業</option>
                                <option value="specific" ${targetType === 'specific' ? 'selected' : ''}>指定對象</option>
                            </select>
                        </div>

                        <div id="abTargetFields" style="${targetType !== 'specific' ? 'display: none;' : ''}">
                            <div style="margin-bottom: 8px;">
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">角色（可多選）</label>
                                <select id="abTargetRoles" multiple style="width: 100%; height: 60px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <div style="margin-bottom: 8px;">
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">部門（可多選）</label>
                                <select id="abTargetDepartments" multiple style="width: 100%; height: 60px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="">載入中...</option>
                                </select>
                            </div>
                            <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; margin-bottom: 8px;">
                                <input type="checkbox" id="abIncludeChildren" ${includeChildren ? 'checked' : ''} style="margin-right: 4px;">
                                包含子部門
                            </label>
                        </div>

                        <label style="display: flex; align-items: center; font-size: 11px; cursor: pointer; margin-bottom: 8px;">
                            <input type="checkbox" id="abRequireAck" ${requireAck ? 'checked' : ''} style="margin-right: 4px;">
                            需要已讀確認（勾選後管理員可查看確認統計）
                        </label>

                        <button class="btn-primary" onclick="applyAlertBroadcastConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;

                // 載入角色和部門選項
                setTimeout(() => loadAlertBroadcastOptions(targetRoles, targetDepartments), 100);
            }

            // EmailAdapter 企業郵件節點配置
            if (type === 'EmailAdapter') {
                const currentConfig = node.data('config') || {};
                const smtpConfigId = currentConfig.smtp_config_id || '';
                const recipientType = currentConfig.recipient_type || 'manual';
                const recipientGroups = currentConfig.recipient_groups || [];
                const recipientManual = currentConfig.recipient_manual || '';
                const ccManual = currentConfig.cc_manual || '';
                const subject = currentConfig.subject || '';
                const body = currentConfig.body || '';
                const bodyType = currentConfig.body_type || 'plain';
                const priority = currentConfig.priority || 'normal';

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #2563EB; font-size: 12px; margin-bottom: 8px;">
                            <i class="fas fa-mail-bulk"></i> 企業郵件設定
                        </div>

                        <!-- SMTP 設定選擇 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">SMTP 郵件服務</label>
                            <select id="emailAdapterSmtpConfig" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="">載入中...</option>
                            </select>
                            <div style="font-size: 10px; color: #888; margin-top: 2px;">留空則使用預設設定（支援備援機制）</div>
                        </div>

                        <!-- 收件者類型 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者來源</label>
                            <select id="emailAdapterRecipientType" onchange="toggleEmailAdapterRecipientFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                                <option value="group" ${recipientType === 'group' ? 'selected' : ''}>收件人群組</option>
                                <option value="manual" ${recipientType === 'manual' ? 'selected' : ''}>手動輸入</option>
                            </select>
                        </div>

                        <!-- 群組選擇 -->
                        <div id="emailAdapterGroupField" style="margin-bottom: 8px; ${recipientType !== 'group' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇群組（可多選）</label>
                            <select id="emailAdapterGroups" multiple style="width: 100%; height: 80px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="">載入中...</option>
                            </select>
                        </div>

                        <!-- 手動輸入收件者 -->
                        <div id="emailAdapterManualField" style="margin-bottom: 8px; ${recipientType !== 'manual' ? 'display: none;' : ''}">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者 Email（逗號或換行分隔，支援變數 <code>\${var}</code>）</label>
                            <textarea id="emailAdapterRecipientManual" rows="2" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; font-family: monospace;">${recipientManual}</textarea>
                        </div>

                        <!-- 副本 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">CC 副本（選填）</label>
                            <input type="text" id="emailAdapterCcManual" placeholder="逗號分隔，支援變數" value="${ccManual}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                        </div>

                        <!-- 主旨 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">主旨 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('emailAdapterSubject'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <input type="text" id="emailAdapterSubject" placeholder="支援變數 \${v.name}, \${f.key}" value="${subject}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        </div>

                        <!-- 內容 -->
                        <div style="margin-bottom: 8px;">
                            <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">內容 <span style="color: #DC2626;">*</span>
                                <button type="button" onclick="VarPicker.open(this, document.getElementById('emailAdapterBody'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                            </label>
                            <textarea id="emailAdapterBody" rows="5" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;" placeholder="輸入郵件內容...">${body}</textarea>
                        </div>

                        <!-- 格式與優先級 -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                                <select id="emailAdapterBodyType" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="plain" ${bodyType === 'plain' ? 'selected' : ''}>純文字</option>
                                    <option value="html" ${bodyType === 'html' ? 'selected' : ''}>HTML</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">優先級</label>
                                <select id="emailAdapterPriority" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                    <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                    <option value="normal" ${priority === 'normal' ? 'selected' : ''}>一般</option>
                                    <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                                </select>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyEmailAdapterConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>

                    <!-- 變數說明 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; padding: 8px;">
                        <div style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 6px;">可用變數 (v2)</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #f0fdf4;"><code>\${v.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程變數</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${f.key}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>\${wi.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程名稱</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${t.now}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">當前時間</td></tr>
                        </table>
                    </div>
                `;

                // 載入 SMTP 設定和收件人群組
                setTimeout(() => {
                    loadEmailAdapterSmtpConfigs(smtpConfigId);
                    loadEmailAdapterGroups(recipientGroups);
                }, 100);
            }

            // BRANCH 條件路由節點配置
            if (type === 'Branch') {
                const currentConfig = node.data('config') || {};
                const rules = currentConfig.rules || [];
                const fallback = currentConfig.fallback || { action: 'log', log_message: '無匹配規則' };

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span style="font-weight: bold; color: #16A34A; font-size: 12px;"><i class="fas fa-code-branch"></i> 分支規則</span>
                            <button class="btn-secondary" onclick="addBranchRule()" style="padding: 3px 8px; font-size: 10px;">
                                <i class="fas fa-plus"></i> 新增規則
                            </button>
                        </div>
                        <div id="branchRulesList" style="max-height: 300px; overflow-y: auto;">
                            <!-- 規則會動態生成 -->
                        </div>
                    </div>

                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                        <div style="font-weight: bold; color: #DC2626; font-size: 11px; margin-bottom: 6px;">
                            <i class="fas fa-exclamation-triangle"></i> 無匹配時 (Fallback)
                        </div>
                        <div style="display: grid; grid-template-columns: auto 1fr; gap: 6px; align-items: center;">
                            <select id="branchFallbackAction" onchange="toggleBranchFallbackOptions()" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="log" ${fallback.action === 'log' ? 'selected' : ''}>只記錄 Log</option>
                                <option value="route" ${fallback.action === 'route' ? 'selected' : ''}>路由至節點</option>
                                <option value="default" ${fallback.action === 'default' ? 'selected' : ''}>走第一條出線</option>
                            </select>
                            <input type="text" id="branchFallbackMessage" placeholder="Log 訊息"
                                   value="${fallback.log_message || '無匹配規則'}"
                                   style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; ${fallback.action === 'route' ? 'display:none;' : ''}">
                            <select id="branchFallbackTarget" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; grid-column: span 2; ${fallback.action !== 'route' ? 'display:none;' : ''}">
                                <option value="">選擇目標出線...</option>
                            </select>
                        </div>
                    </div>

                    <button class="btn-primary" onclick="applyBranchConfig('${nodeId}')" style="width: 100%; padding: 8px; font-size: 12px; margin-bottom: 8px;">
                        <i class="fas fa-check"></i> 套用
                    </button>

                    <!-- 運算符說明頁籤 -->
                    <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; overflow: hidden;">
                        <div style="display: flex; background: #f5f5f5; border-bottom: 1px solid #e0e0e0;">
                            <button onclick="switchBranchHelpTab('ops')" id="branchTabOps" style="flex: 1; padding: 5px; border: none; background: #16A34A; color: white; font-size: 10px; cursor: pointer;">運算符</button>
                            <button onclick="switchBranchHelpTab('logic')" id="branchTabLogic" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">邏輯</button>
                            <button onclick="switchBranchHelpTab('examples')" id="branchTabExamples" style="flex: 1; padding: 5px; border: none; background: transparent; color: #666; font-size: 10px; cursor: pointer;">範例</button>
                        </div>

                        <div id="branchContentOps" style="padding: 8px; font-size: 10px; line-height: 1.4;">
                            <table style="width: 100%; border-collapse: collapse;">
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #dcfce7;"><code>==</code> <code>!=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">相等/不等（字串比較）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&gt;</code> <code>&gt;=</code> <code>&lt;</code> <code>&lt;=</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">數值比較</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>contains</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">包含子字串</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>startswith</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">開頭符合</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #fef3c7;"><code>in</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">在清單中 (逗號分隔)</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>empty</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">為空（不需比較值）</td></tr>
                                <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>matches</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">正則匹配</td></tr>
                            </table>
                        </div>

                        <div id="branchContentLogic" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #dcfce7; border-radius: 3px;">
                                <b>AND（且）</b>：所有條件都要符合<br>
                                <code>\${status}==approved AND \${amount}&gt;1000</code>
                            </div>
                            <div style="padding: 4px; background: #fef3c7; border-radius: 3px;">
                                <b>OR（或）</b>：任一條件符合即可<br>
                                <code>\${type}==urgent OR \${priority}==high</code>
                            </div>
                            <div style="margin-top: 6px; font-size: 9px; color: #666;">
                                同一規則內的條件，依序用「與下一條件的關係」串接
                            </div>
                        </div>

                        <div id="branchContentExamples" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                            <div style="margin-bottom: 6px; padding: 4px; background: #f0fdf4; border-radius: 3px;">
                                <b>金額判斷</b><br>
                                <code>\${amount}</code> <code>&gt;</code> <code>10000</code><br>
                                → 走「主管簽核」路徑
                            </div>
                            <div style="margin-bottom: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px;">
                                <b>狀態檢查</b><br>
                                <code>\${status}</code> <code>in</code> <code>approved,confirmed</code><br>
                                → 符合時走多條路徑（並行）
                            </div>
                            <div style="padding: 4px; background: #fef3c7; border-radius: 3px;">
                                <b>複合條件</b><br>
                                條件1: <code>\${dept}</code> <code>==</code> <code>IT</code> [AND]<br>
                                條件2: <code>\${level}</code> <code>&gt;=</code> <code>3</code>
                            </div>
                        </div>
                    </div>
                `;

                // 延遲渲染：先載入出線，再渲染規則（規則需要出線資料）
                setTimeout(() => {
                    loadBranchOutgoingEdges(nodeId, fallback);
                    renderBranchRules(rules, nodeId);
                }, 50);
            }

            // End 結束節點配置
            if (type === 'End') {
                const currentConfig = node.data('config') || {};
                const finishMode = currentConfig.finish_mode || 'detach';
                const waitSeconds = currentConfig.wait_seconds !== undefined ? currentConfig.wait_seconds : 3;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 11px; color: #666; white-space: nowrap;">
                                <i class="fas fa-clock" style="color: #667eea;"></i> 等待
                            </label>
                            <input type="number" id="endWaitSeconds" value="${waitSeconds}" min="0" max="300"
                                   style="width: 60px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; text-align: center;">
                            <span style="font-size: 11px; color: #666;">秒後結束流程</span>
                        </div>
                    </div>

                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="margin-bottom: 10px;">
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'detach' ? '#667eea' : '#e0e0e0'}; border-radius: 8px; margin-bottom: 10px; cursor: pointer; background: ${finishMode === 'detach' ? '#f0f4ff' : 'white'};">
                                <input type="radio" name="finishMode" value="detach" ${finishMode === 'detach' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #667eea;">分離執行模式 (Detach)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    流程直接結束，不處理未完成的節點。<br>
                                    <span style="color: #999;">適合：執行時間不確定的背景任務、單向通知流程</span>
                                </p>
                            </label>
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'cancel' ? '#ff6b00' : '#e0e0e0'}; border-radius: 8px; margin-bottom: 10px; cursor: pointer; background: ${finishMode === 'cancel' ? '#fff8f0' : 'white'};">
                                <input type="radio" name="finishMode" value="cancel" ${finishMode === 'cancel' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #ff6b00;">取消/終止模式 (Cancel)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    取消未執行的節點，強制終止執行中的節點。<br>
                                    <span style="color: #999;">適合：需要明確終止所有任務的流程</span>
                                </p>
                            </label>
                            <label style="display: block; padding: 12px; border: 2px solid ${finishMode === 'strict' ? '#28a745' : '#e0e0e0'}; border-radius: 8px; cursor: pointer; background: ${finishMode === 'strict' ? '#f0fff4' : 'white'};">
                                <input type="radio" name="finishMode" value="strict" ${finishMode === 'strict' ? 'checked' : ''} onchange="updateFinishModeSelection(this)" style="margin-right: 10px;">
                                <strong style="color: #28a745;">嚴格等待模式 (Strict)</strong>
                                <p style="margin: 5px 0 0 24px; font-size: 12px; color: #666;">
                                    等待所有節點完成，有錯誤則阻止結束。<br>
                                    <span style="color: #999;">適合：需要確保所有任務都完成的關鍵流程</span>
                                </p>
                            </label>
                        </div>
                        <button class="btn-primary" onclick="applyEndConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            // Abandon 中止節點配置
            if (type === 'Abandon') {
                const currentConfig = node.data('config') || {};
                const waitSeconds = currentConfig.wait_seconds !== undefined ? currentConfig.wait_seconds : 1;

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <label style="font-size: 11px; color: #666; white-space: nowrap;">
                                <i class="fas fa-clock" style="color: #991B1B;"></i> 等待
                            </label>
                            <input type="number" id="abandonWaitSeconds" value="${waitSeconds}" min="0" max="300"
                                   style="width: 60px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; text-align: center;">
                            <span style="font-size: 11px; color: #666;">秒後中止流程</span>
                        </div>
                    </div>

                    <div style="background: #fef2f2; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #fca5a5;">
                        <div style="font-size: 12px; color: #991B1B; margin-bottom: 6px;">
                            <i class="fas fa-exclamation-triangle"></i> <strong>中止模式</strong>
                        </div>
                        <p style="font-size: 11px; color: #666; margin: 0;">
                            取消所有未執行的節點，強制終止執行中的節點，立即結束流程。
                        </p>
                    </div>

                    <button class="btn-primary" onclick="applyAbandonConfig('${nodeId}')" style="width: 100%; background: #991B1B; border-color: #991B1B;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                `;
            }

            // SubSystemProvision 子系統配置節點
            if (type === 'SubSystemProvision') {
                const currentConfig = node.data('config') || {};
                const action = currentConfig.action || 'create';
                const ssName = currentConfig.sub_system_name || '';
                const ssIcon = currentConfig.sub_system_icon || '';
                const ssDeveloper = currentConfig.sub_system_developer || '';
                const ssCode = currentConfig.sub_system_code || '';

                const actions = [
                    { value: 'create',  label: '建立子系統', color: '#28a745', desc: '建立子系統 + 選單 + 授予開發者權限' },
                    { value: 'suspend', label: '停用子系統', color: '#ff6b00', desc: '停用子系統 + 停用選單' },
                    { value: 'delete',  label: '刪除子系統', color: '#dc3545', desc: '軟刪除子系統 + 停用選單 + 撤銷權限' },
                ];

                info += `
                    <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                        <div style="font-size: 12px; font-weight: bold; margin-bottom: 8px; color: #8B5CF6;">
                            <i class="fas fa-cog"></i> 動作類型
                        </div>
                        ${actions.map(a => `
                            <label style="display: block; padding: 8px; border: 2px solid ${action === a.value ? a.color : '#e0e0e0'}; border-radius: 6px; margin-bottom: 6px; cursor: pointer; background: ${action === a.value ? a.color + '10' : 'white'};">
                                <input type="radio" name="sspAction" value="${a.value}" ${action === a.value ? 'checked' : ''} onchange="toggleSSPFields()" style="margin-right: 8px;">
                                <strong style="color: ${a.color};">${a.label}</strong>
                                <p style="margin: 3px 0 0 22px; font-size: 11px; color: #666;">${a.desc}</p>
                            </label>
                        `).join('')}
                    </div>

                    <div id="sspCreateFields" style="display: ${action === 'create' ? 'block' : 'none'};">
                        <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                            <div style="font-size: 12px; font-weight: bold; margin-bottom: 8px; color: #333;">
                                建立參數
                            </div>
                            <div style="margin-bottom: 8px;">
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">
                                    子系統名稱 <span style="color: #dc3545;">*</span>
                                </label>
                                <input type="text" id="sspName" value="${ssName}" placeholder="\${f.sub_system_name}"
                                       style="width: 100%; padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; box-sizing: border-box;">
                                <div style="font-size: 10px; color: #999; margin-top: 2px;">支援變數，如 \${f.sub_system_name}</div>
                            </div>
                            <div style="margin-bottom: 8px;">
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">
                                    開發者
                                </label>
                                <input type="text" id="sspDeveloper" value="${ssDeveloper}" placeholder="\${fi.applicant_code}"
                                       style="width: 100%; padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; box-sizing: border-box;">
                                <div style="font-size: 10px; color: #999; margin-top: 2px;">空白時預設為申請者。變數如 \${f.sub_system_developer}</div>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">
                                    圖示 (選填)
                                </label>
                                <input type="text" id="sspIcon" value="${ssIcon}" placeholder="bi-box-seam"
                                       style="width: 100%; padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; box-sizing: border-box;">
                            </div>
                        </div>
                    </div>

                    <div id="sspTargetFields" style="display: ${action !== 'create' ? 'block' : 'none'};">
                        <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px solid #e0e0e0;">
                            <div style="font-size: 12px; font-weight: bold; margin-bottom: 8px; color: #333;">
                                目標子系統
                            </div>
                            <div>
                                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">
                                    子系統代碼 <span style="color: #dc3545;">*</span>
                                </label>
                                <input type="text" id="sspCode" value="${ssCode}" placeholder="\${v.sub_system_code}"
                                       style="width: 100%; padding: 6px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; box-sizing: border-box;">
                                <div style="font-size: 10px; color: #999; margin-top: 2px;">子系統的唯一代碼。變數如 \${v.sub_system_code}</div>
                            </div>
                        </div>
                    </div>

                    <button class="btn-primary" onclick="applySSPConfig('${nodeId}')" style="width: 100%; background: #8B5CF6; border-color: #8B5CF6;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                `;
            }

            // ParallelFork 並行分支節點配置
            if (type === 'ParallelFork') {
                // 取得出線資訊
                const outEdges = cy.edges().filter(e => e.source().id() === nodeId);
                const outCount = outEdges.length;

                let outList = '';
                if (outCount > 0) {
                    outEdges.forEach(e => {
                        const targetNode = e.target();
                        const targetLabel = targetNode.data('label') || targetNode.id();
                        const targetType = targetNode.data('type') || '?';
                        outList += `<li>${targetLabel} <span style="color:#999;">(${targetType})</span></li>`;
                    });
                } else {
                    outList = '<li style="color:#dc3545;">尚無出線，請連接目標節點</li>';
                }

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #2196F3;">
                            <i class="fas fa-code-branch"></i> 並行分支說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">流程到達此節點後，會同時往所有出線推進，啟動並行執行。</p>
                            <p style="margin: 10px 0;">通常搭配<strong>並行匯合 (ParallelJoin)</strong> 節點收攏分支。</p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #2196F3;">
                            <i class="fas fa-arrow-right"></i> 出線 (${outCount} 條)
                        </h4>
                        <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.8; color: #333;">
                            ${outList}
                        </ul>
                    </div>

                    <button class="btn-primary" onclick="applyNodeBasicInfo('${nodeId}')" style="width: 100%;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                `;
            }

            // ParallelJoin 並行匯合節點配置
            if (type === 'ParallelJoin') {
                const currentConfig = node.data('config') || {};
                const enableTimeout = currentConfig.enable_timeout || false;
                const timeoutMinutes = currentConfig.timeout_minutes || 5;
                const timeoutEdgeId = currentConfig.timeout_edge_id || '';

                // 取得入線資訊
                const inEdges = cy.edges().filter(e => e.target().id() === nodeId);
                const inCount = inEdges.length;

                let inList = '';
                if (inCount > 0) {
                    inEdges.forEach(e => {
                        const srcNode = e.source();
                        const srcLabel = srcNode.data('label') || srcNode.id();
                        const srcType = srcNode.data('type') || '?';
                        inList += `<li>${srcLabel} <span style="color:#999;">(${srcType})</span></li>`;
                    });
                } else {
                    inList = '<li style="color:#dc3545;">尚無入線，請從來源節點連接</li>';
                }

                // 取得出線清單（供逾時去向選擇）
                const outEdges = cy.edges().filter(e => e.source().id() === nodeId);
                let timeoutEdgeOptions = '<option value="">-- 請選擇逾時去向 --</option>';
                outEdges.forEach(e => {
                    const tgt = e.target();
                    const tgtLabel = tgt.data('label') || tgt.id();
                    const tgtType = tgt.data('type') || '?';
                    const selected = e.id() === timeoutEdgeId ? 'selected' : '';
                    timeoutEdgeOptions += `<option value="${e.id()}" ${selected}>${tgtLabel} (${tgtType})</option>`;
                });

                info += `
                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 10px 0; color: #9C27B0;">
                            <i class="fas fa-compress-arrows-alt"></i> 並行匯合說明
                        </h4>
                        <div style="font-size: 13px; line-height: 1.6; color: #666;">
                            <p style="margin: 10px 0;">等待所有入線的來源節點完成後才往下推進。</p>
                            <p style="margin: 10px 0;">可設定逾時機制：超過指定時間未到齊，走逾時專用出線。</p>
                        </div>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #9C27B0;">
                            <i class="fas fa-arrow-left"></i> 入線 (${inCount} 條)
                        </h4>
                        <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.8; color: #333;">
                            ${inList}
                        </ul>
                        <p style="font-size: 11px; color: #999; margin-top: 10px;">
                            <i class="fas fa-info-circle"></i> 流程執行時，需等待以上所有來源節點都完成才繼續
                        </p>
                    </div>

                    <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
                        <h4 style="margin: 0 0 15px 0; color: #9C27B0;">
                            <i class="fas fa-cog"></i> 逾時設定
                        </h4>
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; margin-bottom: 15px;">
                            <input type="checkbox" id="pjEnableTimeout" ${enableTimeout ? 'checked' : ''}
                                   onchange="toggleParallelJoinTimeout()"
                                   style="transform: scale(1.2);">
                            <span style="font-size: 13px; font-weight: bold;">啟用逾時機制</span>
                        </label>

                        <div id="pjTimeoutSettings" style="display: ${enableTimeout ? 'block' : 'none'};">
                            <div style="margin-bottom: 12px;">
                                <strong style="font-size: 12px;">逾時時間（分鐘）：</strong><br>
                                <input type="number" id="pjTimeoutMinutes" value="${timeoutMinutes}"
                                       min="1" max="14400"
                                       style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px; box-sizing: border-box;">
                                <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                    <i class="fas fa-info-circle"></i> 從第一條入線到達開始計時，最大 14400 分鐘（10 天）
                                </p>
                            </div>
                            <div style="margin-bottom: 12px;">
                                <strong style="font-size: 12px;">逾時去向：</strong><br>
                                <select id="pjTimeoutEdgeId"
                                        style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; margin-top: 5px; box-sizing: border-box;">
                                    ${timeoutEdgeOptions}
                                </select>
                                <p style="font-size: 11px; color: #999; margin-top: 5px;">
                                    <i class="fas fa-info-circle"></i> 逾時後走此出線；未到齊的分支將被略過
                                </p>
                            </div>
                        </div>

                        <button class="btn-primary" onclick="applyParallelJoinConfig('${nodeId}')" style="width: 100%;">
                            <i class="fas fa-check"></i> 套用
                        </button>
                    </div>
                `;
            }

            document.getElementById('nodeSettings').innerHTML = info;

            // 如果是子流程節點，載入可用子流程清單
            if (type === 'Subflow') {
                loadAvailableSubflows(nodeId);
            }

            updateStatus(`選中節點：${nodeId}`);
        }

        // 載入可用子流程清單（分區面板）
        async function loadAvailableSubflows(nodeId) {
            try {
                const parentId = currentWorkflowId;
                if (!parentId) {
                    console.error('無法取得當前工作流程 ID');
                    updateStatus('無法載入子流程清單：找不到父流程 ID', 'warning');
                    return;
                }

                const response = await fetch(`/api/workflows/data/subflows/available?parent_id=${parentId}`);
                const result = await response.json();

                const dedicatedList = document.getElementById('dedicatedSubflowList');
                const commonList = document.getElementById('commonSubflowList');
                const hiddenInput = document.getElementById('childFlowSelect');
                if (!dedicatedList || !commonList) return;

                // 取得當前選中的子流程
                const node = cy.getElementById(nodeId);
                const currentConfig = node.data('config') || {};
                const currentChildFlowId = currentConfig.childFlowId || '';

                if (!result.success || !result.data) {
                    dedicatedList.innerHTML = '<div style="padding: 10px; color: #c33; font-size: 12px;">載入失敗</div>';
                    commonList.innerHTML = '<div style="padding: 10px; color: #c33; font-size: 12px;">載入失敗</div>';
                    return;
                }

                const { dedicated, common_categories } = result.data;

                // 渲染專屬子流程列表
                if (dedicated.length === 0) {
                    dedicatedList.innerHTML = '<div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">尚無專屬子流程</div>';
                } else {
                    let html = '';
                    dedicated.forEach(sf => {
                        const isSelected = sf.code === currentChildFlowId;
                        const bgColor = isSelected ? '#e8f0fe' : 'transparent';
                        const borderLeft = isSelected ? '3px solid #667eea' : '3px solid transparent';
                        html += `<div style="display: flex; align-items: center; padding: 7px 10px; border-bottom: 1px solid #f0f0f0; background: ${bgColor}; border-left: ${borderLeft}; cursor: pointer;" onmouseover="this.style.background='${isSelected ? '#e8f0fe' : '#f8f9fa'}'" onmouseout="this.style.background='${bgColor}'" onclick="selectSubflow('${nodeId}', '${sf.code}', '${sf.name.replace(/'/g, "\\'")}', true)">
                            <span style="flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${sf.name}</span>`;
                        if (sf.is_referenced) {
                            html += `<span style="font-size: 11px; color: #667eea; margin-left: 8px; white-space: nowrap;">使用中</span>`;
                        } else {
                            html += `<button onclick="event.stopPropagation(); deleteSubflow('${sf.secure_code}', '${sf.name.replace(/'/g, "\\'")}', '${nodeId}')" style="background: none; border: none; color: #c33; cursor: pointer; padding: 2px 6px; font-size: 13px; margin-left: 8px;" title="刪除此子流程"><i class="fas fa-trash-alt"></i></button>`;
                        }
                        html += '</div>';
                    });
                    dedicatedList.innerHTML = html;
                }

                // 渲染通用子流程列表（按分類分組）
                if (common_categories.length === 0) {
                    commonList.innerHTML = '<div style="padding: 10px; color: #999; font-size: 12px; text-align: center;">尚無通用子流程</div>';
                } else {
                    let html = '';
                    common_categories.forEach(cat => {
                        const catId = 'cat_' + cat.category_name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_');
                        html += `<div>
                            <div onclick="const body=document.getElementById('${catId}'); const arrow=this.querySelector('.cat-arrow'); if(body.style.display==='none'){body.style.display='block';arrow.textContent='▾';}else{body.style.display='none';arrow.textContent='▸';}" style="padding: 7px 10px; background: #f5f5f5; cursor: pointer; font-size: 13px; font-weight: 600; border-bottom: 1px solid #e0e0e0; user-select: none;">
                                <span class="cat-arrow">▾</span> ${cat.category_name}
                                <span style="font-size: 11px; color: #999; font-weight: normal; margin-left: 4px;">(${cat.subflows.length})</span>
                            </div>
                            <div id="${catId}">`;
                        cat.subflows.forEach(sf => {
                            const isSelected = sf.code === currentChildFlowId;
                            const bgColor = isSelected ? '#e8f0fe' : 'transparent';
                            const borderLeft = isSelected ? '3px solid #667eea' : '3px solid transparent';
                            html += `<div style="display: flex; align-items: center; padding: 6px 10px 6px 24px; border-bottom: 1px solid #f0f0f0; background: ${bgColor}; border-left: ${borderLeft}; cursor: pointer;" onmouseover="this.style.background='${isSelected ? '#e8f0fe' : '#f8f9fa'}'" onmouseout="this.style.background='${bgColor}'" onclick="selectSubflow('${nodeId}', '${sf.code}', '${sf.name.replace(/'/g, "\\'")}', false)">
                                <span style="flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${sf.name}</span>
                            </div>`;
                        });
                        html += '</div></div>';
                    });
                    commonList.innerHTML = html;
                }

                // 更新「目前」顯示
                _updateCurrentSubflowDisplay(currentChildFlowId, dedicated, common_categories);

                // 自動補齊舊資料的 subflowKind（載入時節點已有 childFlowId 但沒有 subflowKind）
                if (currentChildFlowId && node.length > 0 && !node.data('subflowKind')) {
                    const isDed = dedicated.some(sf => sf.code === currentChildFlowId);
                    const kind = isDed ? 'dedicated' : 'common';
                    node.data('subflowKind', kind);
                    const cfg = node.data('config') || {};
                    cfg.subflowKind = kind;
                    node.data('config', cfg);
                }

                // 載入參數映射配置
                loadParamMapping(nodeId);

                console.log(`已載入子流程面板：${dedicated.length} 個專屬, ${common_categories.length} 個分類`);

            } catch (error) {
                console.error('載入子流程清單失敗:', error);
                updateStatus('無法載入子流程清單：' + error.message, 'warning');
            }
        }

        // 更新「目前」顯示文字
        function _updateCurrentSubflowDisplay(currentCode, dedicated, common_categories) {
            const display = document.getElementById('currentSubflowDisplay');
            if (!display) return;
            if (!currentCode) {
                display.innerHTML = '目前：<strong style="color: #999;">未選擇</strong>';
                return;
            }
            // 在專屬和通用中查找名稱
            let name = currentCode;
            for (const sf of dedicated) {
                if (sf.code === currentCode) { name = sf.name; break; }
            }
            if (name === currentCode) {
                for (const cat of common_categories) {
                    for (const sf of cat.subflows) {
                        if (sf.code === currentCode) { name = sf.name; break; }
                    }
                    if (name !== currentCode) break;
                }
            }
            display.innerHTML = `目前：<strong>${name}</strong>`;
        }

        // 選擇子流程
        function selectSubflow(nodeId, code, name, isDedicated) {
            const hiddenInput = document.getElementById('childFlowSelect');
            if (hiddenInput) hiddenInput.value = code;

            // 更新「目前」顯示
            const display = document.getElementById('currentSubflowDisplay');
            if (display) display.innerHTML = `目前：<strong>${name}</strong>`;

            // 設定 subflowKind 供節點變色
            const kind = isDedicated ? 'dedicated' : 'common';
            const node = cy.getElementById(nodeId);
            if (node && node.length > 0) {
                node.data('subflowKind', kind);
                const config = node.data('config') || {};
                config.subflowKind = kind;
                node.data('config', config);
            }

            // 套用配置
            applySubprocessConfig(nodeId);

            // 重新載入列表以更新高亮
            setTimeout(() => loadAvailableSubflows(nodeId), 600);
        }

        // 刪除專屬子流程
        async function deleteSubflow(secureCode, name, nodeId) {
            if (!confirm(`確定要刪除子流程「${name}」嗎？\n此操作無法復原。`)) return;

            try {
                const response = await fetch(`/api/workflows/data/subflows/${secureCode}`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' }
                });
                const result = await response.json();
                if (result.success) {
                    updateStatus(`已刪除子流程「${name}」`, 'success');
                    // 如果刪除的是當前選中的，清空選擇
                    const hiddenInput = document.getElementById('childFlowSelect');
                    if (hiddenInput) {
                        // 需要根據 code 判斷，但 API 用 secure_code，所以直接重新載入
                    }
                    await loadAvailableSubflows(nodeId);
                } else {
                    updateStatus('刪除失敗：' + (result.error || '未知錯誤'), 'warning');
                }
            } catch (error) {
                console.error('刪除子流程失敗:', error);
                updateStatus('刪除子流程失敗：' + error.message, 'warning');
            }
        }

        // 建立新子流程
        async function createNewSubflow(nodeId) {
            const subflowName = prompt('請輸入子流程名稱：');
            if (!subflowName || !subflowName.trim()) {
                return;
            }

            const parentId = currentWorkflowId;
            if (!parentId) {
                updateStatus('無法建立子流程：找不到父流程 ID', 'warning');
                return;
            }

            try {
                const response = await fetch(`/api/workflows/data/subflows/create`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: subflowName.trim(),
                        parent_id: parentId,
                        description: `子流程：${subflowName.trim()}`
                    })
                });

                if (!response.ok) {
                    const text = await response.text();
                    console.error('建立子流程 API 錯誤:', response.status, text.substring(0, 200));
                    updateStatus(`建立子流程失敗：HTTP ${response.status}`, 'warning');
                    return;
                }

                const result = await response.json();

                if (result.success) {
                    updateStatus(`子流程「${result.data.name}」已建立`, 'success');

                    // 重新載入子流程清單並自動選擇新建立的子流程
                    await loadAvailableSubflows(nodeId);
                    selectSubflow(nodeId, result.data.code, result.data.name, true);
                } else {
                    updateStatus('建立子流程失敗：' + (result.message || '未知錯誤'), 'warning');
                }
            } catch (error) {
                console.error('建立子流程失敗:', error);
                updateStatus('無法建立子流程：' + error.message, 'warning');
            }
        }

        // 載入參數映射配置
        function loadParamMapping(nodeId) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            // 載入輸入參數映射
            const inputTable = document.getElementById('inputMappingTable');
            if (inputTable) {
                const inputMapping = paramMapping.input || {};
                if (Object.keys(inputMapping).length === 0) {
                    inputTable.innerHTML = '<tr><td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td></tr>';
                } else {
                    let rows = '';
                    for (const [parentVar, childVar] of Object.entries(inputMapping)) {
                        rows += `
                            <tr data-parent-var="${parentVar}">
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${parentVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${childVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                                    <button onclick="removeInputMapping('${nodeId}', '${parentVar}')"
                                            style="padding: 4px 8px; font-size: 11px; background: #ef4444; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }
                    inputTable.innerHTML = rows;
                }
            }

            // 載入輸出參數映射
            const outputTable = document.getElementById('outputMappingTable');
            if (outputTable) {
                const outputMapping = paramMapping.output || {};
                if (Object.keys(outputMapping).length === 0) {
                    outputTable.innerHTML = '<tr><td colspan="3" style="padding: 20px; text-align: center; color: #9ca3af;">尚無映射規則</td></tr>';
                } else {
                    let rows = '';
                    for (const [childVar, parentVar] of Object.entries(outputMapping)) {
                        rows += `
                            <tr data-child-var="${childVar}">
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${childVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${parentVar}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">
                                    <button onclick="removeOutputMapping('${nodeId}', '${childVar}')"
                                            style="padding: 4px 8px; font-size: 11px; background: #ef4444; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </td>
                            </tr>
                        `;
                    }
                    outputTable.innerHTML = rows;
                }
            }
        }

        // 添加輸入參數映射
        function addInputMapping(nodeId) {
            const parentVar = prompt('請輸入父流程變數名稱：');
            if (!parentVar || !parentVar.trim()) return;

            const childVar = prompt('請輸入子流程變數名稱：');
            if (!childVar || !childVar.trim()) return;

            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (!paramMapping.input) paramMapping.input = {};
            paramMapping.input[parentVar.trim()] = childVar.trim();

            config.paramMapping = paramMapping;
            node.data('config', config);

            loadParamMapping(nodeId);
            updateStatus(`✅ 已添加輸入映射：${parentVar} → ${childVar}`, 'success');
        }

        // 添加輸出參數映射
        function addOutputMapping(nodeId) {
            const childVar = prompt('請輸入子流程變數名稱：');
            if (!childVar || !childVar.trim()) return;

            const parentVar = prompt('請輸入父流程變數名稱：');
            if (!parentVar || !parentVar.trim()) return;

            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (!paramMapping.output) paramMapping.output = {};
            paramMapping.output[childVar.trim()] = parentVar.trim();

            config.paramMapping = paramMapping;
            node.data('config', config);

            loadParamMapping(nodeId);
            updateStatus(`✅ 已添加輸出映射：${childVar} → ${parentVar}`, 'success');
        }

        // 刪除輸入參數映射
        function removeInputMapping(nodeId, parentVar) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (paramMapping.input && paramMapping.input[parentVar]) {
                delete paramMapping.input[parentVar];
                config.paramMapping = paramMapping;
                node.data('config', config);

                loadParamMapping(nodeId);
                updateStatus(`✅ 已刪除輸入映射：${parentVar}`, 'success');
            }
        }

        // 刪除輸出參數映射
        function removeOutputMapping(nodeId, childVar) {
            const node = cy.getElementById(nodeId);
            if (!node) return;

            const config = node.data('config') || {};
            const paramMapping = config.paramMapping || { input: {}, output: {} };

            if (paramMapping.output && paramMapping.output[childVar]) {
                delete paramMapping.output[childVar];
                config.paramMapping = paramMapping;
                node.data('config', config);

                loadParamMapping(nodeId);
                updateStatus(`✅ 已刪除輸出映射：${childVar}`, 'success');
            }
        }

        // 套用節點基本資訊（名稱與描述）- 內部輔助函數
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
                updateStatus(`✅ 已更新節點：${newLabel}`, 'success');
            }

            return node; // 返回 node 供其他函數使用
        }

        // 套用子流程節點配置
        function applySubprocessConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            // 從下拉選單取得選擇的子流程
            const selectElement = document.getElementById('childFlowSelect');
            if (!selectElement) {
                updateStatus('找不到子流程選單', 'warning');
                return;
            }

            const childFlowId = selectElement.value?.trim();
            if (!childFlowId) {
                updateStatus('請選擇子流程', 'warning');
                return;
            }

            // 取得選中的子流程名稱（從目前顯示區取）
            const displayEl = document.getElementById('currentSubflowDisplay');
            const strongEl = displayEl ? displayEl.querySelector('strong') : null;
            const childFlowName = (strongEl && strongEl.textContent !== '未選擇') ? strongEl.textContent : childFlowId;

            // 取得現有的 config，更新 childFlowId
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                childFlowId: childFlowId
            };

            // 儲存設定到節點的 config
            node.data('config', updatedConfig);

            updateStatus(`✅ 子流程設定已套用：${childFlowName}`, 'success');

            console.log('子流程節點配置已更新:', {
                nodeId: nodeId,
                childFlowId: childFlowId,
                config: updatedConfig
            });

            // 自動儲存當前流程
            saveWorkflow().then(() => {
                console.log('✅ 流程已自動儲存');
                // 延遲 0.5 秒後重新整理流程樹系
                setTimeout(() => {
                    refreshFlowTree();
                }, 500);
            }).catch(err => {
                console.error('⚠️ 自動儲存失敗:', err);
            });
        }

        // 套用 Delay 暫停節點配置
        function applyDelayConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const delaySecondsInput = document.getElementById('delaySeconds');
            if (!delaySecondsInput) {
                updateStatus('找不到延遲秒數輸入框', 'warning');
                return;
            }

            const delaySeconds = parseInt(delaySecondsInput.value, 10);
            if (isNaN(delaySeconds) || delaySeconds < 0) {
                updateStatus('延遲秒數必須是非負整數', 'warning');
                return;
            }

            if (delaySeconds > 86400) {
                updateStatus('延遲秒數不能超過 86400（24小時）', 'warning');
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                delay_seconds: delaySeconds
            };

            node.data('config', updatedConfig);

            // 更新換算顯示
            const hours = Math.floor(delaySeconds / 3600);
            const minutes = Math.floor((delaySeconds % 3600) / 60);
            const seconds = delaySeconds % 60;
            const displayEl = document.getElementById('delayTimeDisplay');
            if (displayEl) {
                displayEl.textContent = `${hours}小時 ${minutes}分 ${seconds}秒`;
            }

            updateStatus(`✅ 暫停設定已套用：${delaySeconds} 秒`, 'success');

            console.log('Delay 節點配置已更新:', {
                nodeId: nodeId,
                delay_seconds: delaySeconds,
                config: updatedConfig
            });
        }
        window.applyDelayConfig = applyDelayConfig;

