/**
 * wf-node-decision-writer.js -- DecisionWriter（防禦決策）節點屬性面板
 *
 * 對應後端 handler:
 *   modules/form_workflow/services/node_handlers/decision_writer_handler.py
 */

const dwEscapeHtml = value => {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

const dwNormalizeEnforcementPoints = value => {
    if (Array.isArray(value)) {
        return value.map(v => String(v).trim()).filter(Boolean);
    }
    if (typeof value === 'string') {
        return value.split(',').map(v => v.trim()).filter(Boolean);
    }
    return ['nftables', 'edl'];
};

const dwSelected = (current, value) => {
    return current === value ? 'selected' : '';
};

// eslint-disable-next-line no-unused-vars
function renderDecisionWriterPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    const action = cfg.action || 'block';
    const targetType = cfg.target_type || 'ip';
    const targetValue = cfg.target_value || '';
    const enforcementPoints = dwNormalizeEnforcementPoints(cfg.enforcement_points);
    const fixedEps = ['nftables', 'edl', 'crowdsec', 'cloudflare'];
    const otherEps = enforcementPoints.filter(ep => !fixedEps.includes(ep)).join(', ');
    const severity = cfg.severity || '';
    const ttl = cfg.ttl_seconds ?? '';
    const decidedVia = cfg.decided_via || '';
    const reason = cfg.reason_template || '';
    const allowProtected = cfg.allow_protected_target === true;
    const onProtected = cfg.on_protected || 'error';

    return `
        <div style="background: white; padding: 10px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e0e0e0;">
            <div style="font-weight: bold; color: #DC2626; font-size: 12px; margin-bottom: 8px;">
                <i class="ri-shield-check-line"></i> ${__('防禦決策設定')}
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">
                <div>
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('動作')}</label>
                    <select id="dwAction" onchange="toggleDwFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        <option value="block" ${dwSelected(action, 'block')}>${__('封鎖 (block)')}</option>
                        <option value="unblock" ${dwSelected(action, 'unblock')}>${__('解除封鎖 (unblock)')}</option>
                        <option value="allow" ${dwSelected(action, 'allow')}>${__('放行 (allow)')}</option>
                        <option value="escalate" ${dwSelected(action, 'escalate')}>${__('升級處理 (escalate)')}</option>
                        <option value="observe" ${dwSelected(action, 'observe')}>${__('持續觀察 (observe)')}</option>
                    </select>
                </div>
                <div>
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('目標型別')}</label>
                    <select id="dwTargetType" onchange="toggleDwFields()" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        <option value="ip" ${dwSelected(targetType, 'ip')}>ip</option>
                        <option value="ipv6" ${dwSelected(targetType, 'ipv6')}>ipv6</option>
                        <option value="cidr" ${dwSelected(targetType, 'cidr')}>${__('網段 (cidr)')}</option>
                        <option value="domain" ${dwSelected(targetType, 'domain')}>domain</option>
                        <option value="url" ${dwSelected(targetType, 'url')}>url</option>
                        <option value="asn" ${dwSelected(targetType, 'asn')}>asn</option>
                        <option value="country" ${dwSelected(targetType, 'country')}>country</option>
                        <option value="user_agent" ${dwSelected(targetType, 'user_agent')}>user_agent</option>
                        <option value="jwt_sub" ${dwSelected(targetType, 'jwt_sub')}>jwt_sub</option>
                    </select>
                </div>
            </div>

            <div style="margin-bottom: 8px;">
                <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">${__('目標值')}
                    <button type="button" onclick="VarPicker.open(this, document.getElementById('dwTargetValue'))"
                        style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="${__('插入變數')}">{x}</button>
                </label>
                <input type="text" id="dwTargetValue" value="${dwEscapeHtml(targetValue)}" placeholder="\${f.actor_ip}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; font-family: monospace;">
                <div style="font-size: 10px; color: #888; margin-top: 2px;">${__('支援流程變數，例如 ${f.actor_ip}')}</div>
            </div>

            <div style="margin-bottom: 8px;">
                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('執行點')}</label>
                <label style="font-size: 11px; margin-right: 8px;"><input type="checkbox" id="dwEpNftables" ${enforcementPoints.includes('nftables') ? 'checked' : ''}> nftables</label>
                <label style="font-size: 11px; margin-right: 8px;"><input type="checkbox" id="dwEpEdl" ${enforcementPoints.includes('edl') ? 'checked' : ''}> edl</label>
                <label style="font-size: 11px; margin-right: 8px;"><input type="checkbox" id="dwEpCrowdsec" ${enforcementPoints.includes('crowdsec') ? 'checked' : ''}> crowdsec</label>
                <label style="font-size: 11px;"><input type="checkbox" id="dwEpCloudflare" ${enforcementPoints.includes('cloudflare') ? 'checked' : ''}> cloudflare</label>
                <div style="margin-top: 6px;">
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('其他執行點（逗號分隔）')}</label>
                    <input type="text" id="dwEpOther" value="${dwEscapeHtml(otherEps)}" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; font-family: monospace;">
                </div>
                <div id="dwEdlNote" style="font-size: 10px; color: #888; margin-top: 4px;">
                    ${__('執行點決定這筆決策會被哪些外部執行端拉走。edl 會進入防火牆黑名單。')}
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">
                <div>
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('嚴重度')}</label>
                    <select id="dwSeverity" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        <option value="" ${dwSelected(severity, '')}>${__('（未指定）')}</option>
                        <option value="info" ${dwSelected(severity, 'info')}>info</option>
                        <option value="low" ${dwSelected(severity, 'low')}>low</option>
                        <option value="medium" ${dwSelected(severity, 'medium')}>medium</option>
                        <option value="high" ${dwSelected(severity, 'high')}>high</option>
                        <option value="critical" ${dwSelected(severity, 'critical')}>critical</option>
                    </select>
                </div>
                <div>
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('TTL 秒')}</label>
                    <input type="number" id="dwTtl" value="${dwEscapeHtml(ttl)}" min="0" step="1" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                    <div style="font-size: 10px; color: #888; margin-top: 2px;">${__('留空表示永久，直到人工或流程解除。')}</div>
                </div>
            </div>

            <div style="margin-bottom: 8px;">
                <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('決策來源')}</label>
                <select id="dwDecidedVia" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                    <option value="" ${dwSelected(decidedVia, '')}>${__('自動推斷')}</option>
                    <option value="human" ${dwSelected(decidedVia, 'human')}>${__('人工決策 (human)')}</option>
                    <option value="auto" ${dwSelected(decidedVia, 'auto')}>${__('自動決策 (auto)')}</option>
                    <option value="ai" ${dwSelected(decidedVia, 'ai')}>${__('AI 判定 (ai)')}</option>
                </select>
                <div style="font-size: 10px; color: #888; margin-top: 2px;">${__('並行分支下的自動推斷不可靠，建議明確指定。')}</div>
            </div>

            <div style="margin-bottom: 8px;">
                <label style="font-size: 11px; color: #666; display: flex; align-items: center; margin-bottom: 3px;">${__('理由範本')}
                    <button type="button" onclick="VarPicker.open(this, document.getElementById('dwReason'))"
                        style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="${__('插入變數')}">{x}</button>
                </label>
                <textarea id="dwReason" rows="3" style="width: 100%; padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; resize: vertical; font-family: monospace;" placeholder="${__('例如：流程自動處置')} \${f.finding_title}">${dwEscapeHtml(reason)}</textarea>
            </div>

            <div style="border-top: 1px solid #eee; padding-top: 8px; margin-bottom: 8px;">
                <div style="font-weight: bold; color: #555; font-size: 11px; margin-bottom: 6px;">${__('封鎖保護清單')}</div>
                <div id="dwProtectedBlock">
                    <label style="display: block; font-size: 11px; margin-bottom: 3px;">
                        <input type="checkbox" id="dwAllowProtected" ${allowProtected ? 'checked' : ''}>
                        ${__('允許封鎖受保護目標（覆寫保護清單）')}
                    </label>
                    <div style="font-size: 10px; color: #888; margin-bottom: 6px;">${__('勾選後仍會在決策紀錄留下覆寫痕跡供稽核。')}</div>
                    <label style="font-size: 11px; color: #666; display: block; margin-bottom: 3px;">${__('命中保護清單時')}</label>
                    <select id="dwOnProtected" style="width: 100%; padding: 5px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">
                        <option value="error" ${dwSelected(onProtected, 'error')}>${__('視為節點錯誤（流程停住等人處理）')}</option>
                        <option value="skip" ${dwSelected(onProtected, 'skip')}>${__('略過並繼續流程')}</option>
                    </select>
                </div>
                <div id="dwProtectedNote" style="display:none;font-size: 10px; color: #888;">
                    ${__('此動作與目標型別組合不經過封鎖保護清單檢查（僅「封鎖」搭配 ip／ipv6／cidr 時才檢查）。')}
                </div>
            </div>

            <button class="btn-primary" onclick="applyDecisionWriterConfig('${nodeId}')" style="width: 100%; padding: 6px; font-size: 11px;">
                <i class="fas fa-check"></i> ${__('套用')}
            </button>
        </div>
    `;
}
window.renderDecisionWriterPanel = renderDecisionWriterPanel;

function toggleDwFields() {
    const action = document.getElementById('dwAction')?.value || 'block';
    const targetType = document.getElementById('dwTargetType')?.value || 'ip';
    const edl = document.getElementById('dwEpEdl');
    const edlNote = document.getElementById('dwEdlNote');
    const protectedBlock = document.getElementById('dwProtectedBlock');
    const protectedNote = document.getElementById('dwProtectedNote');
    const edlAllowed = action === 'block' || action === 'allow' || action === 'unblock';
    const protectedApplies = action === 'block' && ['ip', 'ipv6', 'cidr'].includes(targetType);

    if (edl) {
        edl.disabled = !edlAllowed;
        if (!edlAllowed) edl.checked = false;
    }
    if (edlNote) {
        edlNote.textContent = edlAllowed
            ? __('執行點決定這筆決策會被哪些外部執行端拉走。edl 會進入防火牆黑名單。')
            : __('observe／escalate 不可送 EDL：外部 EDL 執行端只接受 block／allow／unblock，收到其他動作會讓整筆決策從「已套用」掉成「部分套用」。');
    }
    if (protectedBlock) protectedBlock.style.display = protectedApplies ? '' : 'none';
    if (protectedNote) protectedNote.style.display = protectedApplies ? 'none' : '';
}
window.toggleDwFields = toggleDwFields;

function applyDecisionWriterToConfig(config) {
    const actionEl = document.getElementById('dwAction');
    if (!actionEl) return false;

    const fixedEps = [
        ['dwEpNftables', 'nftables'],
        ['dwEpEdl', 'edl'],
        ['dwEpCrowdsec', 'crowdsec'],
        ['dwEpCloudflare', 'cloudflare'],
    ];
    const enforcementPoints = [];
    fixedEps.forEach(([id, value]) => {
        if (document.getElementById(id)?.checked) enforcementPoints.push(value);
    });
    (document.getElementById('dwEpOther')?.value || '')
        .split(',')
        .map(v => v.trim())
        .filter(Boolean)
        .forEach(value => {
            if (!enforcementPoints.includes(value)) enforcementPoints.push(value);
        });

    config.action = actionEl.value;
    config.target_type = document.getElementById('dwTargetType')?.value || 'ip';
    config.target_value = document.getElementById('dwTargetValue')?.value || '';
    config.enforcement_points = enforcementPoints;

    const severity = document.getElementById('dwSeverity')?.value || '';
    if (severity) config.severity = severity;
    else delete config.severity;

    const ttlRaw = document.getElementById('dwTtl')?.value?.trim() || '';
    if (ttlRaw) config.ttl_seconds = parseInt(ttlRaw, 10);
    else delete config.ttl_seconds;

    const reason = document.getElementById('dwReason')?.value?.trim() || '';
    if (reason) config.reason_template = reason;
    else delete config.reason_template;

    const decidedVia = document.getElementById('dwDecidedVia')?.value || '';
    if (decidedVia) config.decided_via = decidedVia;
    else delete config.decided_via;

    if (document.getElementById('dwAllowProtected')?.checked) config.allow_protected_target = true;
    else delete config.allow_protected_target;

    const onProtected = document.getElementById('dwOnProtected')?.value || 'error';
    if (onProtected !== 'error') config.on_protected = onProtected;
    else delete config.on_protected;

    return true;
}
window.applyDecisionWriterToConfig = applyDecisionWriterToConfig;

function applyDecisionWriterConfig(nodeId) {
    const node = applyNodeBasicInfo(nodeId, true);
    if (!node) return;

    const targetValue = document.getElementById('dwTargetValue')?.value?.trim() || '';
    if (!targetValue) {
        updateStatus(__('請輸入目標值'), 'warning');
        return;
    }

    const config = node.data('config') || {};
    applyDecisionWriterToConfig(config);
    node.data('config', config);
    updateStatus(__('防禦決策設定已套用'), 'success');
}
window.applyDecisionWriterConfig = applyDecisionWriterConfig;
