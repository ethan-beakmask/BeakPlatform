/**
 * wf-accordion-operations.js -- 操作類節點面板
 * 從 wf-accordion.js 拆分
 * 包含: OpSet, OpFieldWrite, SqlExecutor, FormAdapter, SubSystemProvision
 */

        // ==================== OpSet 面板 ====================

        function renderOpSetPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const operations = currentConfig.operations || [];

            return `
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
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+ - x ÷</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">目標 運算 值（累加模式）</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e3f2fd;"><code>連接</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">字串連接</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>+1 -1</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">遞增/遞減（不需值）</td></tr>
                        </table>
                    </div>

                    <!-- 範例 -->
                    <div id="opsetContentExamples" style="padding: 8px; font-size: 10px; line-height: 1.4; display: none;">
                        <div style="margin-bottom: 6px; padding: 4px; background: #e8f5e9; border-radius: 3px;">
                            <b>表達式運算（推薦）</b><br>
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
        }

        // ==================== OpFieldWrite 面板 ====================

        function renderOpFieldWritePanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const targetField = currentConfig.target_field || '';
            const content = currentConfig.content || '';
            const contentType = currentConfig.content_type || 'text';

            return `
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
                        ${_renderVarSyntaxTable()}
                    </div>
                </div>
            `;
        }

        // ==================== SqlExecutor 面板 ====================

        function renderSqlExecutorPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const queryType = currentConfig.query_type || '';
            const resultVar = currentConfig.result_var || '';

            return `
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
        }

        // ==================== FormAdapter 面板（摘要） ====================

        function renderFormAdapterPanel(node, nodeId) {
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

            return `
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

        // ==================== SubSystemProvision 面板 ====================

        function renderSubSystemProvisionPanel(node, nodeId) {
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

            return `
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
