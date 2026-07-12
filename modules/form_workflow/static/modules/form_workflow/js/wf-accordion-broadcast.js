/**
 * wf-accordion-broadcast.js -- 廣播類節點面板
 * 從 wf-accordion.js 拆分
 * 包含: NavbarBroadcast, AlertBroadcast
 */

        // ==================== NavbarBroadcast 面板 ====================

        function renderNavbarBroadcastPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const mode = currentConfig.mode || 'start';
            const broadcastCode = currentConfig.broadcast_code || '';
            const message = currentConfig.message || '';
            const textColor = currentConfig.text_color || '#000000';
            const bgColor = currentConfig.bg_color || '#FDE047';
            const displaySeconds = currentConfig.display_seconds || 5;
            const durationMinutes = currentConfig.duration_minutes || 0;

            return `
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
                            ${message || __('預覽：跑馬燈訊息將顯示在此')}
                        </div>
                    </div>

                    <button class="btn-primary" onclick="applyNavbarBroadcastConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 12px;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                </div>
            `;
        }

        // ==================== AlertBroadcast 面板 ====================

        function renderAlertBroadcastPanel(node, nodeId) {
            const currentConfig = node.data('config') || {};
            const broadcastCode = currentConfig.broadcast_code || '';
            const title = currentConfig.title || '';
            const message = currentConfig.message || '';
            const requireAck = currentConfig.require_ack !== false;
            const targetType = currentConfig.target_type || 'all';
            const targetRoles = currentConfig.target_roles || [];
            const targetDepartments = currentConfig.target_departments || [];
            const includeChildren = currentConfig.include_children !== false;

            return `
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
        }
