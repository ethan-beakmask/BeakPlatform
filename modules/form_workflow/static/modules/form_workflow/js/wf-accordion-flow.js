/**
 * wf-accordion-flow.js -- 流程控制類節點面板
 * 從 wf-accordion.js 拆分
 * 包含: Converge, Delay, End, Abandon, Branch, ParallelFork, ParallelJoin, applyDelayConfig
 */

        // ==================== Converge 面板 ====================

        function renderConvergePanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const currentMode = currentConfig.mode || 'ALL';
            const isAnyMode = currentMode === 'ANY';

            return `
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

        // ==================== Delay 面板 ====================

        function renderDelayPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const delaySeconds = currentConfig.delay_seconds || 60;

            return `
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

        // ==================== End 面板 ====================

        function renderEndPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const finishMode = currentConfig.finish_mode || 'detach';
            const waitSeconds = currentConfig.wait_seconds !== undefined ? currentConfig.wait_seconds : 3;

            return `
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

        // ==================== Abandon 面板 ====================

        function renderAbandonPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const waitSeconds = currentConfig.wait_seconds !== undefined ? currentConfig.wait_seconds : 1;

            return `
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

        // ==================== Branch 面板 ====================

        function renderBranchPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const rules = currentConfig.rules || [];
            const fallback = currentConfig.fallback || { action: 'log', log_message: '無匹配規則' };

            return `
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
        }

        // ==================== ParallelFork 面板 ====================

        function renderParallelForkPanel(node, nodeId) {
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

            return `
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

        // ==================== ParallelJoin 面板 ====================

        function renderParallelJoinPanel(node, nodeId) {
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

            return `
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

        // ==================== 套用 Delay 配置 ====================

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

            updateStatus(`暫停設定已套用：${delaySeconds} 秒`, 'success');

            console.log('Delay 節點配置已更新:', {
                nodeId: nodeId,
                delay_seconds: delaySeconds,
                config: updatedConfig
            });
        }
        window.applyDelayConfig = applyDelayConfig;
