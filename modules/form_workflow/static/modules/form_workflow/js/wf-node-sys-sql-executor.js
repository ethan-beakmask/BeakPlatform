/**
 * wf-node-sys-sql-executor.js -- SysSqlExecutor（系統 SQL 執行器）節點屬性面板
 *
 * 面板只允許選擇後端白名單內的 stored procedure，不能自由輸入 SQL。
 */

let _sqlProcedures = [];
let _sqlExecutorConfig = {};
let _sqlParamValues = {};

function _sqlEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _rememberSqlParamValues() {
    const container = document.getElementById('sqlParamFields');
    if (!container) return;
    container.querySelectorAll('[id^="sqlParam_"]').forEach((el) => {
        const name = el.id.replace('sqlParam_', '');
        if (name) _sqlParamValues[name] = el.value || '';
    });
}

function _getSelectedSqlProcedure() {
    const code = document.getElementById('sqlProcedureCode')?.value || '';
    return _sqlProcedures.find((proc) => proc.code === code) || null;
}

function _renderSqlProcedureDescription(proc) {
    const desc = document.getElementById('sqlProcedureDesc');
    if (!desc) return;

    if (!proc) {
        desc.textContent = __('請選擇預存程序');
        desc.style.color = '#888';
        return;
    }

    const parts = [];
    if (proc.description) parts.push(proc.description);
    if (proc.result_mode) parts.push(`${__('結果模式')}：${proc.result_mode}`);
    if (Array.isArray(proc.result_columns) && proc.result_columns.length > 0) {
        const columns = proc.result_columns
            .map((col) => col.label || col.name)
            .filter(Boolean)
            .join(', ');
        if (columns) parts.push(`${__('回傳欄位')}：${columns}`);
    }
    if (proc.max_rows !== undefined && proc.max_rows !== null) {
        parts.push(`${__('最多筆數')}：${proc.max_rows}`);
    }

    desc.textContent = parts.join('；') || __('此預存程序沒有說明');
    desc.style.color = '#555';
}

// eslint-disable-next-line no-unused-vars
function renderSysSqlExecutorPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    _sqlExecutorConfig = cfg;
    _sqlParamValues = { ...(cfg.params || {}) };

    const resultVar = cfg.result_var || '';
    const timeout = cfg.timeout_seconds || 10;
    const writeNote = cfg.write_approval_note === true;
    const noteTemplate = cfg.note_template || '';
    const onError = cfg.on_error || 'error';

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('SQL 執行器設定')}</h4>

        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;">
            ${__('只能執行平台預先登錄的 stored procedure，不能自由輸入 SQL。企業識別碼由系統強制帶入，查不到其他企業的資料。查詢一律唯讀。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('預存程序')} *</label>
        <select id="sqlProcedureCode" style="width:100%;font-size:11px;margin-bottom:4px;">
            <option value="">${__('載入中...')}</option>
        </select>
        <div id="sqlProcedureDesc" style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;">
            ${__('載入預存程序清單中')}
        </div>

        <div id="sqlParamFields" style="margin-bottom:8px;"></div>

        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('企業識別碼 p_org_secure_code：由系統自動帶入，不可指定')}
        </div>

        <label style="font-size:11px;color:#555;">${__('結果寫入變數')} *</label>
        <input type="text" id="sqlResultVar" value="${_sqlEscapeHtml(resultVar)}"
            style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="stock">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('後續節點用 ${v.變數名} 取用')}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
                <label style="font-size:11px;color:#555;">${__('逾時（秒）')}</label>
                <input type="number" id="sqlTimeout" value="${_sqlEscapeHtml(timeout)}" min="1" max="60"
                    style="width:100%;font-size:11px;">
            </div>
            <div>
                <label style="font-size:11px;color:#555;">${__('失敗時')}</label>
                <select id="sqlOnError" style="width:100%;font-size:11px;">
                    <option value="error" ${onError === 'error' ? 'selected' : ''}>${__('視為節點錯誤，走 error 邊')}</option>
                    <option value="continue" ${onError === 'continue' ? 'selected' : ''}>${__('繼續流程')}</option>
                </select>
            </div>
        </div>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="sqlWriteNote" ${writeNote ? 'checked' : ''}>
            ${__('把查詢結果寫成簽核註記供人員參考')}
        </label>

        <label style="font-size:11px;color:#555;">${__('註記內容樣板')}</label>
        <textarea id="sqlNoteTemplate" rows="3"
            style="width:100%;font-size:11px;font-family:monospace;margin-bottom:2px;"
            placeholder="${__('庫存查詢結果：')}\${v.stock_qty_on_hand}">${_sqlEscapeHtml(noteTemplate)}</textarea>
        <div style="font-size:10px;color:#888;">
            ${__('可用 ${v.xxx} 引用流程變數，勾選寫成簽核註記時才會使用。')}
        </div>
    </div>`;
}

// eslint-disable-next-line no-unused-vars
async function initSysSqlExecutorPanel(nodeId) {
    const select = document.getElementById('sqlProcedureCode');
    const desc = document.getElementById('sqlProcedureDesc');
    if (!select || !desc) return;

    const selectedCode = _sqlExecutorConfig.procedure_code || '';

    try {
        const response = await fetch(`${window.__BP}/api/workflows/data/sql-procedures`, {
            credentials: 'same-origin'
        });
        const payload = await response.json();
        if (!response.ok || payload.success !== true || !Array.isArray(payload.data)) {
            throw new Error(payload.message || 'Failed to load SQL procedures');
        }

        _sqlProcedures = payload.data;
        if (_sqlProcedures.length === 0) {
            select.innerHTML = `<option value="">${__('（沒有可用的預存程序）')}</option>`;
            desc.textContent = __('沒有可用的預存程序');
            desc.style.color = '#888';
            renderSqlParamFields();
            return;
        }

        select.innerHTML = [
            `<option value="">${__('請選擇預存程序...')}</option>`,
            ..._sqlProcedures.map((proc) => {
                const code = proc.code || '';
                const label = proc.display_name || code;
                return `<option value="${_sqlEscapeHtml(code)}" ${code === selectedCode ? 'selected' : ''}>${_sqlEscapeHtml(label)}</option>`;
            })
        ].join('');
        select.value = selectedCode;
        select.onchange = () => renderSqlParamFields();
        renderSqlParamFields();
    } catch (err) {
        console.error('Failed to load SQL procedures:', err);
        _sqlProcedures = [];
        select.innerHTML = `<option value="">${__('（沒有可用的預存程序）')}</option>`;
        desc.textContent = __('載入預存程序清單失敗，請稍後再試。');
        desc.style.color = '#c53030';
        renderSqlParamFields();
    }
}

// eslint-disable-next-line no-unused-vars
function renderSqlParamFields() {
    _rememberSqlParamValues();

    const container = document.getElementById('sqlParamFields');
    if (!container) return;

    const proc = _getSelectedSqlProcedure();
    _renderSqlProcedureDescription(proc);

    if (!proc) {
        container.innerHTML = '';
        return;
    }

    const params = (proc.parameters || []).filter((param) => param.name !== 'p_org_secure_code');
    if (params.length === 0) {
        container.innerHTML = `<div style="font-size:10px;color:#888;margin-bottom:6px;">${__('此預存程序不需要參數')}</div>`;
        return;
    }

    container.innerHTML = params.map((param) => {
        const name = param.name || '';
        const fieldId = `sqlParam_${name}`;
        const label = param.label || name;
        const required = param.required ? ' *' : '';
        const value = _sqlParamValues[name] || '';
        const description = param.description || '';

        if (param.type === 'boolean') {
            return `
                <div style="margin-bottom:6px;">
                    <label style="font-size:11px;color:#555;">${_sqlEscapeHtml(label)}${required}</label>
                    <select id="${_sqlEscapeHtml(fieldId)}" style="width:100%;font-size:11px;margin-bottom:2px;">
                        <option value="true" ${value === 'true' ? 'selected' : ''}>true</option>
                        <option value="false" ${value === 'false' ? 'selected' : ''}>false</option>
                    </select>
                    ${description ? `<div style="font-size:10px;color:#888;">${_sqlEscapeHtml(description)}</div>` : ''}
                </div>`;
        }

        return `
            <div style="margin-bottom:6px;">
                <label style="font-size:11px;color:#555;">${_sqlEscapeHtml(label)}${required}</label>
                <input type="text" id="${_sqlEscapeHtml(fieldId)}" value="${_sqlEscapeHtml(value)}"
                    style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="\${f.${_sqlEscapeHtml(name)}}">
                ${description ? `<div style="font-size:10px;color:#888;">${_sqlEscapeHtml(description)}</div>` : ''}
            </div>`;
    }).join('');
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectSysSqlExecutorConfig() {
    const resultVar = document.getElementById('sqlResultVar');
    const procedureCode = document.getElementById('sqlProcedureCode');
    if (!resultVar || !procedureCode) return null;

    const params = {};
    const container = document.getElementById('sqlParamFields');
    if (container) {
        container.querySelectorAll('[id^="sqlParam_"]').forEach((el) => {
            const name = el.id.replace('sqlParam_', '');
            if (name) params[name] = el.value || '';
        });
    }
    delete params['p_org_secure_code'];

    let timeout = parseInt(document.getElementById('sqlTimeout')?.value, 10);
    if (Number.isNaN(timeout) || timeout < 1 || timeout > 60) timeout = 10;

    const onError = document.getElementById('sqlOnError')?.value === 'continue' ? 'continue' : 'error';

    return {
        procedure_code: procedureCode.value || '',
        params: params,
        result_var: resultVar.value.trim(),
        timeout_seconds: timeout,
        write_approval_note: !!document.getElementById('sqlWriteNote')?.checked,
        note_template: document.getElementById('sqlNoteTemplate')?.value || '',
        on_error: onError,
    };
}
