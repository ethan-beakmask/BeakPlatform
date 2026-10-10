/**
 * wf-node-http-request.js -- HttpRequest（HTTP 呼叫）節點屬性面板
 */

function _hrqEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _hrqClampInt(value, min, max, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
}

function _hrqHeadersToText(headers) {
    if (!Array.isArray(headers)) return '';
    return headers
        .filter(h => h && h.name)
        .map(h => `${h.name}: ${h.value ?? ''}`)
        .join('\n');
}

function _hrqParseHeaders(text) {
    return String(text || '')
        .split(/\r?\n/)
        .map(line => {
            const idx = line.indexOf(':');
            if (idx <= 0) return null;
            const name = line.slice(0, idx).trim();
            const value = line.slice(idx + 1).trim();
            return /^[A-Za-z0-9-]+$/.test(name) ? { name, value } : null;
        })
        .filter(Boolean)
        .slice(0, 20);
}

function _hrqToggleBodyFields() {
    const mode = document.getElementById('hrqBodyMode')?.value || 'none';
    const bodyField = document.getElementById('hrqBodyField');
    const contentTypeField = document.getElementById('hrqContentTypeField');
    if (bodyField) bodyField.style.display = mode === 'none' ? 'none' : 'block';
    if (contentTypeField) contentTypeField.style.display = mode === 'raw' ? 'block' : 'none';
}

// eslint-disable-next-line no-unused-vars
function renderHttpRequestPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    const method = cfg.method || 'GET';
    const bodyMode = cfg.body_mode || 'none';
    const verifyTls = cfg.verify_tls !== false;
    const expectJson = cfg.expect_json !== false;

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('HTTP 呼叫設定')}</h4>
        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('目的地必須在系統管理員設定的白名單內；結果請看 <前綴>_ok 與 <前綴>_status。')}
        </div>

        <label style="font-size:11px;color:#555;display:flex;align-items:center;gap:4px;">${__('URL')} *
            <button type="button" onclick="VarPicker.open(this, document.getElementById('hrqUrl'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="${__('插入變數')}">{x}</button>
        </label>
        <input type="text" id="hrqUrl" value="${_hrqEscapeHtml(cfg.url || '')}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="https://api.example.com/webhook">

        <label style="font-size:11px;color:#555;">${__('方法')}</label>
        <select id="hrqMethod" style="width:100%;font-size:11px;margin-bottom:6px;">
            ${['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => `<option value="${m}" ${method === m ? 'selected' : ''}>${m}</option>`).join('')}
        </select>

        <label style="font-size:11px;color:#555;">${__('標頭')}</label>
        <textarea id="hrqHeaders" rows="4" style="width:100%;font-size:11px;margin-bottom:2px;font-family:monospace;" placeholder="Authorization: Bearer ...">${_hrqEscapeHtml(_hrqHeadersToText(cfg.headers))}</textarea>
        <div style="font-size:10px;color:#888;margin-bottom:6px;">${__('一行一個 Name: Value，最多 20 個；Host、Content-Length、Transfer-Encoding 會被忽略。')}</div>

        <label style="font-size:11px;color:#555;">${__('內容模式')}</label>
        <select id="hrqBodyMode" onchange="_hrqToggleBodyFields()" style="width:100%;font-size:11px;margin-bottom:6px;">
            <option value="none" ${bodyMode === 'none' ? 'selected' : ''}>${__('無')}</option>
            <option value="json" ${bodyMode === 'json' ? 'selected' : ''}>JSON</option>
            <option value="raw" ${bodyMode === 'raw' ? 'selected' : ''}>Raw</option>
        </select>

        <div id="hrqBodyField">
            <label style="font-size:11px;color:#555;display:flex;align-items:center;gap:4px;">${__('內容')}
                <button type="button" onclick="VarPicker.open(this, document.getElementById('hrqBody'))" style="margin-left:auto;padding:1px 5px;font-size:11px;background:#f0f0f0;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-family:monospace;color:#666;" title="${__('插入變數')}">{x}</button>
            </label>
            <textarea id="hrqBody" rows="6" style="width:100%;font-size:11px;margin-bottom:6px;font-family:monospace;">${_hrqEscapeHtml(cfg.body || '')}</textarea>
        </div>

        <div id="hrqContentTypeField">
            <label style="font-size:11px;color:#555;">Content-Type</label>
            <input type="text" id="hrqContentType" value="${_hrqEscapeHtml(cfg.content_type || 'text/plain')}"
                style="width:100%;font-size:11px;margin-bottom:6px;">
        </div>

        <label style="font-size:11px;color:#555;">${__('逾時秒數')}</label>
        <input type="number" id="hrqTimeoutSeconds" value="${_hrqEscapeHtml(cfg.timeout_seconds || 15)}" min="1" max="120"
            style="width:100%;font-size:11px;margin-bottom:6px;">

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="hrqVerifyTls" ${verifyTls ? 'checked' : ''}>
            ${__('驗證 TLS 憑證')}
        </label>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="hrqExpectJson" ${expectJson ? 'checked' : ''}>
            ${__('解析為 JSON')}
        </label>

        <label style="font-size:11px;color:#555;">${__('回應大小上限')}</label>
        <input type="number" id="hrqMaxResponseBytes" value="${_hrqEscapeHtml(cfg.max_response_bytes || 262144)}" min="1024" max="2097152"
            style="width:100%;font-size:11px;margin-bottom:6px;">

        <label style="font-size:11px;color:#555;">${__('結果變數前綴')} *</label>
        <input type="text" id="hrqResultVar" value="${_hrqEscapeHtml(cfg.result_var || '')}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="http">
    </div>${setTimeout(_hrqToggleBodyFields, 0), ''}`;
}

// eslint-disable-next-line no-unused-vars
function collectHttpRequestConfig() {
    const url = document.getElementById('hrqUrl');
    if (!url) return null;

    const method = document.getElementById('hrqMethod')?.value || 'GET';
    const bodyMode = document.getElementById('hrqBodyMode')?.value || 'none';

    return {
        url: url.value.trim(),
        method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].includes(method) ? method : 'GET',
        headers: _hrqParseHeaders(document.getElementById('hrqHeaders')?.value || ''),
        body_mode: ['none', 'json', 'raw'].includes(bodyMode) ? bodyMode : 'none',
        body: document.getElementById('hrqBody')?.value || '',
        content_type: document.getElementById('hrqContentType')?.value.trim() || 'text/plain',
        timeout_seconds: _hrqClampInt(document.getElementById('hrqTimeoutSeconds')?.value, 1, 120, 15),
        verify_tls: !!document.getElementById('hrqVerifyTls')?.checked,
        expect_json: !!document.getElementById('hrqExpectJson')?.checked,
        max_response_bytes: _hrqClampInt(document.getElementById('hrqMaxResponseBytes')?.value, 1024, 2097152, 262144),
        result_var: document.getElementById('hrqResultVar')?.value.trim() || ''
    };
}
