/**
 * wf-accordion-messaging.js -- 訊息通知類節點面板
 * 從 wf-accordion.js 拆分
 * 包含: Telegram, SysTelegram, SysEmailRelay, EmailAdapter
 */

        // ==================== Telegram 面板 ====================

        function renderTelegramPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const configId = currentConfig.config_id || '';
            const channelName = currentConfig.channel_name || '';
            const message = currentConfig.message || '';
            const parseMode = currentConfig.parse_mode || 'HTML';
            const disableNotification = currentConfig.disable_notification || false;
            const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

            return `
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
                        <div style="color: #28a745; font-weight: bold; margin-bottom: 4px;">建議使用，最簡單</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;b&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;i&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;u&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><u>底線</u></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;s&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><s>刪除線</s></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;code&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;pre&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">程式碼區塊</td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>&lt;a href=""&gt;</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                        </table>
                        <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">&lt;b&gt;通知&lt;/b&gt;

申請人：&lt;code&gt;\${name}&lt;/code&gt;
金額：&lt;b&gt;\${amount}&lt;/b&gt; 元</div>
                        <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">不支援: &lt;font&gt;, &lt;br&gt;（直接換行即可）</div>
                    </div>

                    <!-- Markdown 說明 -->
                    <div id="tgContentMd" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                        <div style="color: #ffc107; font-weight: bold; margin-bottom: 4px;">基本格式，功能較少</div>
                        <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>*文字*</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><b>粗體</b></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>_文字_</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><i>斜體</i></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\`code\`</code></td><td style="padding: 2px 4px; border: 1px solid #eee;"><code>程式碼</code></td></tr>
                            <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>[文字](URL)</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">連結</td></tr>
                        </table>
                        <div style="margin-top: 6px; padding: 4px; background: #f8f9fa; border-radius: 3px; font-family: monospace; white-space: pre; overflow-x: auto;">*通知*

申請人：\`\${name}\`
金額：*\${amount}* 元</div>
                        <div style="color: #dc3545; font-size: 9px; margin-top: 4px;">不支援: 底線、刪除線</div>
                    </div>

                    <!-- MarkdownV2 說明 -->
                    <div id="tgContentMd2" style="padding: 8px; font-size: 10px; line-height: 1.5; display: none;">
                        <div style="color: #dc3545; font-weight: bold; margin-bottom: 4px;">功能最多但需跳脫特殊字元</div>
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
                        ${_renderVarSyntaxTable()}
                    </div>
                </div>
            `;
        }

        // ==================== SysTelegram 面板 ====================

        function renderSysTelegramPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const configId = currentConfig.config_id || '';
            const channelName = currentConfig.channel_name || '';
            const message = currentConfig.message || '';
            const parseMode = currentConfig.parse_mode || 'HTML';
            const disableNotification = currentConfig.disable_notification || false;
            const disableWebPagePreview = currentConfig.disable_web_page_preview || false;

            return `
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
                        ${_renderVarSyntaxTableCompact()}
                    </div>
                </div>
            `;
        }

        // ==================== SysEmailRelay 面板 ====================

        function renderSysEmailRelayPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const recipientType = currentConfig.recipient_type || 'group';
            const recipientGroups = currentConfig.recipient_groups || [];
            const recipientManual = currentConfig.recipient_manual || '';
            const ccManual = currentConfig.cc_manual || '';
            const subject = currentConfig.subject || '';
            const body = currentConfig.body || '';
            const bodyType = currentConfig.body_type || 'plain';
            const priority = currentConfig.priority || 'normal';

            return `
                <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                    <div style="font-weight: bold; color: #16A34A; font-size: 12px; margin-bottom: 8px;">
                        <i class="fas fa-envelope"></i> 系統郵件設定
                    </div>

                    <!-- 收件者類型 -->
                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者來源</label>
                        <select id="sysEmailRelayRecipientType" onchange="toggleSysEmailRelayRecipientFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                            <option value="group" ${recipientType === 'group' ? 'selected' : ''}>收件人群組</option>
                            <option value="manual" ${recipientType === 'manual' ? 'selected' : ''}>手動輸入</option>
                        </select>
                    </div>

                    <!-- 群組選擇 -->
                    <div id="sysEmailRelayGroupField" style="margin-bottom: 8px; ${recipientType !== 'group' ? 'display: none;' : ''}">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇群組（可多選）</label>
                        <select id="sysEmailRelayGroups" multiple style="width: 100%; height: 80px; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                            <option value="">載入中...</option>
                        </select>
                    </div>

                    <!-- 手動輸入收件者 -->
                    <div id="sysEmailRelayManualField" style="margin-bottom: 8px; ${recipientType !== 'manual' ? 'display: none;' : ''}">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">收件者 Email（逗號或換行分隔，支援變數 <code>\${var}</code>）</label>
                        <textarea id="sysEmailRelayRecipientManual" rows="2" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px; font-family: monospace;">${recipientManual}</textarea>
                    </div>

                    <!-- 副本 -->
                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">CC 副本（選填）</label>
                        <input type="text" id="sysEmailRelayCcManual" placeholder="逗號分隔，支援變數" value="${ccManual}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                    </div>

                    <!-- 主旨 -->
                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">主旨 <span style="color: #DC2626;">*</span>
                            <button type="button" onclick="VarPicker.open(this, document.getElementById('sysEmailRelaySubject'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                        </label>
                        <input type="text" id="sysEmailRelaySubject" placeholder="支援變數 \${v.name}, \${f.key}" value="${subject}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                    </div>

                    <!-- 內容 -->
                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">內容 <span style="color: #DC2626;">*</span>
                            <button type="button" onclick="VarPicker.open(this, document.getElementById('sysEmailRelayBody'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                        </label>
                        <textarea id="sysEmailRelayBody" rows="5" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; font-size: 11px; resize: vertical;" placeholder="輸入郵件內容...">${body}</textarea>
                    </div>

                    <!-- 格式與優先級 -->
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                        <div>
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">格式</label>
                            <select id="sysEmailRelayBodyType" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="plain" ${bodyType === 'plain' ? 'selected' : ''}>純文字</option>
                                <option value="html" ${bodyType === 'html' ? 'selected' : ''}>HTML</option>
                            </select>
                        </div>
                        <div>
                            <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">優先級</label>
                            <select id="sysEmailRelayPriority" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">
                                <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                <option value="normal" ${priority === 'normal' ? 'selected' : ''}>一般</option>
                                <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                            </select>
                        </div>
                    </div>

                    <button class="btn-primary" onclick="applySysEmailRelayConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                </div>

                <!-- 變數說明 -->
                <div style="background: white; border-radius: 6px; border: 1px solid #e0e0e0; padding: 8px;">
                    <div style="font-size: 11px; font-weight: bold; color: #666; margin-bottom: 6px;">可用變數 (v2)</div>
                    ${_renderVarSyntaxTableShort()}
                </div>
            `;
        }

        // ==================== EmailAdapter 面板 ====================

        function renderEmailAdapterPanel(node, nodeId) {
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

            return `
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
                    ${_renderVarSyntaxTableShort()}
                </div>
            `;
        }

        // ==================== 共用變數語法表 ====================

        // 完整變數語法表（用於 Telegram）
        function _renderVarSyntaxTable() {
            return `
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
            `;
        }

        // 緊湊變數語法表（用於 SysTelegram）
        function _renderVarSyntaxTableCompact() {
            return `
                <table style="width: 100%; border-collapse: collapse; font-size: 9px;">
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${f.欄位key}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">表單欄位值</td></tr>
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${fi.serial}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流水號</td></tr>
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${fi.applicant}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">申請人</td></tr>
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${v.變數名}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程變數</td></tr>
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${wi.name}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">流程名稱</td></tr>
                    <tr><td style="padding: 2px; border: 1px solid #e0e0e0;"><code>\${t.now}</code></td><td style="padding: 2px; border: 1px solid #e0e0e0;">當前時間</td></tr>
                </table>
            `;
        }

        // 短變數語法表（用於 SysEmailRelay/EmailAdapter）
        function _renderVarSyntaxTableShort() {
            return `
                <table style="width: 100%; border-collapse: collapse; font-size: 10px;">
                    <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #f0fdf4;"><code>\${v.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程變數</td></tr>
                    <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${f.key}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">表單欄位</td></tr>
                    <tr><td style="padding: 2px 4px; border: 1px solid #eee; background: #e0f2fe;"><code>\${wi.name}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">流程名稱</td></tr>
                    <tr><td style="padding: 2px 4px; border: 1px solid #eee;"><code>\${t.now}</code></td><td style="padding: 2px 4px; border: 1px solid #eee;">當前時間</td></tr>
                </table>
            `;
        }
