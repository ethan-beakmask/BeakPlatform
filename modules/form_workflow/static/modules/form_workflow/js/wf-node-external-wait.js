/**
 * wf-node-external-wait.js -- ExternalWait（等待外部回呼）節點屬性面板
 */

function _ewEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _ewClampInt(value, min, max, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
}

function _ewToggleTimeoutFields() {
    const enabled = !!document.getElementById('ewTimeoutEnabled')?.checked;
    const field = document.getElementById('ewTimeoutMinutesField');
    if (field) field.style.display = enabled ? 'block' : 'none';
}

function _ewCopyTokenText() {
    const input = document.getElementById('ewCallbackVar');
    if (!input) return;
    input.select();
    input.setSelectionRange(0, input.value.length);
    if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(input.value);
    } else {
        document.execCommand('copy');
    }
}

// eslint-disable-next-line no-unused-vars
function renderExternalWaitPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    const timeoutEnabled = !!cfg.timeout_enabled;
    const callbackVar = '${cb.' + nodeId + '}';

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('等待外部回呼設定')}</h4>
        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('把這個字串放進上游 HTTP 呼叫的內容，對方就拿得到回呼網址；需要先在主機設定填系統對外網址。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('本節點 ID')}</label>
        <input type="text" value="${_ewEscapeHtml(nodeId)}" readonly
            style="width:100%;font-size:11px;margin-bottom:6px;background:#f8f8f8;">

        <label style="font-size:11px;color:#555;display:flex;align-items:center;gap:4px;">${__('回呼網址變數')}
            <button type="button" onclick="_ewCopyTokenText()" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;" title="${__('複製')}">
                <i class="fas fa-copy"></i>
            </button>
        </label>
        <input type="text" id="ewCallbackVar" value="${_ewEscapeHtml(callbackVar)}" readonly
            style="width:100%;font-size:11px;margin-bottom:6px;font-family:monospace;background:#f8f8f8;">

        <label style="font-size:11px;color:#555;">${__('結果變數前綴')} *</label>
        <input type="text" id="ewResultVar" value="${_ewEscapeHtml(cfg.result_var || '')}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="cb">

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="ewTimeoutEnabled" onchange="_ewToggleTimeoutFields()" ${timeoutEnabled ? 'checked' : ''}>
            ${__('啟用逾時')}
        </label>

        <div id="ewTimeoutMinutesField">
            <label style="font-size:11px;color:#555;">${__('逾時分鐘數')}</label>
            <input type="number" id="ewTimeoutMinutes" value="${_ewEscapeHtml(cfg.timeout_minutes || 120)}" min="1" max="14400"
                style="width:100%;font-size:11px;margin-bottom:6px;">
        </div>
    </div>${setTimeout(_ewToggleTimeoutFields, 0), ''}`;
}

// eslint-disable-next-line no-unused-vars
function collectExternalWaitConfig() {
    const resultVar = document.getElementById('ewResultVar');
    if (!resultVar) return null;
    const timeoutEnabled = !!document.getElementById('ewTimeoutEnabled')?.checked;
    return {
        result_var: resultVar.value.trim(),
        timeout_enabled: timeoutEnabled,
        timeout_minutes: timeoutEnabled
            ? _ewClampInt(document.getElementById('ewTimeoutMinutes')?.value, 1, 14400, 120)
            : 120
    };
}
