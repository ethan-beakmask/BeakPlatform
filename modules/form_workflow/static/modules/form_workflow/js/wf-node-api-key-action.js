/**
 * wf-node-api-key-action.js -- ApiKeyAction「API Key 處置」節點配置
 * 面板 render + 選項載入 + 套用 (P3, dev-notes/API_KEY_TRIGGER_SPEC.md)
 *
 * config: { action: 'suspend'|'resume',
 *           key_source: 'trigger'|'static'|'variable',
 *           key_id: string,   // static: key_id / variable: 變數運算式
 *           reason: string }  // suspend 時的暫停原因（支援變數）
 */

        function renderApiKeyActionPanel(node, nodeId) {
            const cfg = node.data('config') || {};
            const action = cfg.action || 'suspend';
            const keySource = cfg.key_source || 'trigger';
            const keyId = cfg.key_id || '';
            const reason = cfg.reason || '';

            return `
                <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
                    <div style="font-weight: bold; color: #DC2626; font-size: 12px; margin-bottom: 8px;">
                        <i class="ri-key-2-line"></i> API Key 處置設定
                    </div>

                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">處置動作</label>
                        <select id="akaAction" onchange="toggleAkaFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                            <option value="suspend" ${action === 'suspend' ? 'selected' : ''}>暫停 (suspend)</option>
                            <option value="resume" ${action === 'resume' ? 'selected' : ''}>復原 (resume)</option>
                        </select>
                    </div>

                    <div style="margin-bottom: 8px;">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">處置對象</label>
                        <select id="akaKeySource" onchange="toggleAkaFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                            <option value="trigger" ${keySource === 'trigger' ? 'selected' : ''}>發動本流程的 Key</option>
                            <option value="static" ${keySource === 'static' ? 'selected' : ''}>指定 Key</option>
                            <option value="variable" ${keySource === 'variable' ? 'selected' : ''}>變數指定 key_id</option>
                        </select>
                        <div style="font-size: 10px; color: #888; margin-top: 2px;">「發動本流程的 Key」僅適用於外部 API Key 發動的流程</div>
                    </div>

                    <div id="akaStaticField" style="margin-bottom: 8px; ${keySource !== 'static' ? 'display: none;' : ''}">
                        <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">選擇 Key <span style="color: #DC2626;">*</span></label>
                        <select id="akaKeyStatic" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                            <option value="">載入中...</option>
                        </select>
                    </div>

                    <div id="akaVariableField" style="margin-bottom: 8px; ${keySource !== 'variable' ? 'display: none;' : ''}">
                        <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">key_id 運算式 <span style="color: #DC2626;">*</span>
                            <button type="button" onclick="VarPicker.open(this, document.getElementById('akaKeyExpr'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                        </label>
                        <input type="text" id="akaKeyExpr" value="${keySource === 'variable' ? keyId : ''}" placeholder="如 \${f.key_id}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; font-family: monospace;">
                    </div>

                    <div id="akaReasonField" style="margin-bottom: 8px; ${action !== 'suspend' ? 'display: none;' : ''}">
                        <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">暫停原因
                            <button type="button" onclick="VarPicker.open(this, document.getElementById('akaReason'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="插入變數">{x}</button>
                        </label>
                        <textarea id="akaReason" rows="3" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; resize: vertical;" placeholder="如：流程自動處置 \${fi.serial}">${reason}</textarea>
                    </div>

                    <button class="btn-primary" onclick="applyApiKeyActionConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 11px;">
                        <i class="fas fa-check"></i> 套用
                    </button>
                </div>
            `;
        }
        window.renderApiKeyActionPanel = renderApiKeyActionPanel;

        function toggleAkaFields() {
            const keySource = document.getElementById('akaKeySource')?.value;
            const action = document.getElementById('akaAction')?.value;
            const staticField = document.getElementById('akaStaticField');
            const variableField = document.getElementById('akaVariableField');
            const reasonField = document.getElementById('akaReasonField');
            if (staticField) staticField.style.display = keySource === 'static' ? '' : 'none';
            if (variableField) variableField.style.display = keySource === 'variable' ? '' : 'none';
            if (reasonField) reasonField.style.display = action === 'suspend' ? '' : 'none';
            if (keySource === 'static') {
                const sel = document.getElementById('akaKeyStatic');
                if (sel && sel.options.length <= 1) loadApiKeyActionKeys(sel.dataset.selected || '');
            }
        }
        window.toggleAkaFields = toggleAkaFields;

        function loadApiKeyActionKeys(selectedKeyId) {
            const sel = document.getElementById('akaKeyStatic');
            if (!sel) return;
            sel.dataset.selected = selectedKeyId || '';
            fetch(window.__BP + '/api/workflows/data/org-api-keys', {
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
            })
            .then(r => r.json())
            .then(data => {
                sel.innerHTML = '<option value="">-- 請選擇 --</option>';
                (data.keys || []).forEach(k => {
                    const opt = document.createElement('option');
                    opt.value = k.key_id;
                    const statusLabel = k.status === 'active' ? '' : `［${k.status === 'suspended' ? __('暫停中') : k.status}］`;
                    opt.textContent = `${k.name} (${k.key_id}) ${statusLabel}`;
                    if (k.key_id === selectedKeyId) opt.selected = true;
                    sel.appendChild(opt);
                });
            })
            .catch(() => {
                sel.innerHTML = '<option value="">載入失敗</option>';
            });
        }
        window.loadApiKeyActionKeys = loadApiKeyActionKeys;

        function applyApiKeyActionConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const action = document.getElementById('akaAction')?.value || 'suspend';
            const keySource = document.getElementById('akaKeySource')?.value || 'trigger';

            let keyId = '';
            if (keySource === 'static') {
                keyId = document.getElementById('akaKeyStatic')?.value || '';
                if (!keyId) {
                    updateStatus(__('請選擇處置對象 Key'), 'warning');
                    return;
                }
            } else if (keySource === 'variable') {
                keyId = document.getElementById('akaKeyExpr')?.value?.trim() || '';
                if (!keyId) {
                    updateStatus(__('請輸入 key_id 運算式'), 'warning');
                    return;
                }
            }

            const currentConfig = node.data('config') || {};
            node.data('config', {
                ...currentConfig,
                action: action,
                key_source: keySource,
                key_id: keyId,
                reason: document.getElementById('akaReason')?.value?.trim() || '',
            });
            updateStatus(__('API Key 處置設定已套用'), 'success');
        }
        window.applyApiKeyActionConfig = applyApiKeyActionConfig;
