/**
 * wf-node-os-executor.js -- OsExecutor（OS 命令）節點屬性面板
 */

let _osExecutorConfig = {};

function _osEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _osClampInt(value, min, max, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < min || parsed > max) return fallback;
    return parsed;
}

function _osParseExitCodes(value) {
    const codes = String(value || '')
        .split(',')
        .map((part) => parseInt(part.trim(), 10))
        .filter((num) => !Number.isNaN(num));
    return codes.length > 0 ? codes : [0];
}

function _osParseEnv(value) {
    const env = {};
    String(value || '').split(/\r?\n/).forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.includes('=')) return;
        const idx = trimmed.indexOf('=');
        const name = trimmed.slice(0, idx).trim();
        if (!name) return;
        env[name] = trimmed.slice(idx + 1);
    });
    return env;
}

function _osParseList(value) {
    return String(value || '')
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean);
}

function _osToggleModeFields() {
    const waitSelect = document.getElementById('osWaitForResult');
    if (!waitSelect) return;

    const waitForResult = waitSelect.value === 'true';
    const timeoutFields = document.getElementById('osWaitFields');
    const detachFields = document.getElementById('osDetachFields');
    const detachNote = document.getElementById('osDetachNote');
    const cancelScope = document.getElementById('osCancelScope');

    if (timeoutFields) timeoutFields.style.display = waitForResult ? 'grid' : 'none';
    if (detachFields) detachFields.style.display = waitForResult ? 'none' : 'block';

    if (detachNote && cancelScope) {
        detachNote.style.display = (!waitForResult && cancelScope.value === 'detach') ? 'block' : 'none';
    }
}

// eslint-disable-next-line no-unused-vars
function renderOsExecutorPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    _osExecutorConfig = cfg;

    const command = cfg.command || '';
    const resultVar = cfg.result_var || '';
    const timeout = cfg.timeout_seconds || 60;
    const waitForResult = cfg.wait_for_result !== false;
    const exitCodes = Array.isArray(cfg.expect_exit_codes) ? cfg.expect_exit_codes.join(', ') : (cfg.expect_exit_codes || '0');
    const expectPattern = cfg.expect_pattern || '';
    const expectJson = cfg.expect_json === true;
    const cwd = cfg.cwd || '';
    const extraEnv = cfg.extra_env && typeof cfg.extra_env === 'object'
        ? Object.entries(cfg.extra_env).map(([key, value]) => `${key}=${value}`).join('\n')
        : '';
    const killOnTimeout = cfg.kill_on_timeout || 'group';
    const cancelScope = cfg.cancel_scope || 'unit';
    const stopAfter = cfg.stop_after === true;
    const notifyOnException = cfg.notify_on_exception !== false;
    const notifyTo = Array.isArray(cfg.notify_to) ? cfg.notify_to.join(', ') : (cfg.notify_to || '');

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('OS 命令設定')}</h4>

        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('這個節點會在平台主機上執行命令，權限等同流程執行服務的作業系統帳號。需要系統管理員先啟用並把本企業加入白名單，否則節點會被拒絕執行。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('命令模板')} *</label>
        <textarea id="osCommand" rows="4"
            style="width:100%;font-size:11px;font-family:monospace;margin-bottom:2px;">${_osEscapeHtml(command)}</textarea>
        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;">
            ${__('填表人填入的變數值一律會被引號化後才代入，不會被當成命令執行。確實需要讓變數帶多個參數時，在變數後面加上 `!raw`（例：`${v.opts!raw}`）')}
            <span style="color:#c00;">${__('該變數若可能被外部使用者控制，等於把命令執行權交出去。')}</span>
        </div>

        <label style="font-size:11px;color:#555;">${__('結果變數前綴')} *</label>
        <input type="text" id="osResultVar" value="${_osEscapeHtml(resultVar)}"
            style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="cmd_result">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('後續節點用 ${v.變數名} 取用')}
        </div>

        <label style="font-size:11px;color:#555;">${__('執行模式')}</label>
        <select id="osWaitForResult" onchange="_osToggleModeFields()" style="width:100%;font-size:11px;margin-bottom:6px;">
            <option value="true" ${waitForResult === true ? 'selected' : ''}>${__('等待結果')}</option>
            <option value="false" ${waitForResult === false ? 'selected' : ''}>${__('交給 OS 執行')}</option>
        </select>

        <div id="osWaitFields" style="grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
                <label style="font-size:11px;color:#555;">${__('逾時（秒）')}</label>
                <input type="number" id="osTimeout" value="${_osEscapeHtml(timeout)}" min="1" max="3600"
                    style="width:100%;font-size:11px;">
            </div>
            <div>
                <label style="font-size:11px;color:#555;">${__('逾時終止方式')}</label>
                <select id="osKillOnTimeout" style="width:100%;font-size:11px;">
                    <option value="group" ${killOnTimeout === 'group' ? 'selected' : ''}>${__('程序群組')}</option>
                    <option value="process" ${killOnTimeout === 'process' ? 'selected' : ''}>${__('單一程序')}</option>
                    <option value="none" ${killOnTimeout === 'none' ? 'selected' : ''}>${__('不終止')}</option>
                </select>
            </div>
        </div>

        <div id="osDetachFields" style="margin-bottom:6px;">
            <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:6px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
                ${__('交給作業系統背景執行，這一次不等結果，逾時設定不適用。需要系統管理員設定過 sudoers 才能使用。')}
            </div>
            <label style="font-size:11px;color:#555;">${__('取消範圍')}</label>
            <select id="osCancelScope" onchange="_osToggleModeFields()" style="width:100%;font-size:11px;margin-bottom:2px;">
                <option value="unit" ${cancelScope === 'unit' ? 'selected' : ''}>${__('跟隨流程取消')}</option>
                <option value="detach" ${cancelScope === 'detach' ? 'selected' : ''}>${__('脫離流程')}</option>
            </select>
            <div id="osDetachNote" style="font-size:10px;color:#c00;line-height:1.5;margin-bottom:6px;">
                ${__('流程被取消後這個作業仍會繼續執行。')}
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
                <label style="font-size:11px;color:#555;">${__('預期結束碼')}</label>
                <input type="text" id="osExpectExitCodes" value="${_osEscapeHtml(exitCodes)}"
                    style="width:100%;font-size:11px;" placeholder="0">
            </div>
            <div>
                <label style="font-size:11px;color:#555;">${__('預期輸出樣式')}</label>
                <input type="text" id="osExpectPattern" value="${_osEscapeHtml(expectPattern)}" maxlength="200"
                    style="width:100%;font-size:11px;">
            </div>
        </div>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="osExpectJson" ${expectJson ? 'checked' : ''}>
            ${__('輸出必須是合法 JSON')}
        </label>

        <label style="font-size:11px;color:#555;">${__('工作目錄')}</label>
        <input type="text" id="osCwd" value="${_osEscapeHtml(cwd)}"
            style="width:100%;font-size:11px;margin-bottom:2px;">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('留空＝每次用新的暫存目錄')}
        </div>

        <label style="font-size:11px;color:#555;">${__('額外環境變數')}</label>
        <textarea id="osExtraEnv" rows="3"
            style="width:100%;font-size:11px;font-family:monospace;margin-bottom:2px;"
            placeholder="NAME=value">${_osEscapeHtml(extraEnv)}</textarea>
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('每行 NAME=value，空行會略過')}
        </div>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="osStopAfter" ${stopAfter ? 'checked' : ''}>
            ${__('這一步做完就結束這條分支')}
        </label>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="osNotifyOnException" ${notifyOnException ? 'checked' : ''}>
            ${__('例外時寄信通知')}
        </label>

        <label style="font-size:11px;color:#555;">${__('通知收件人')}</label>
        <input type="text" id="osNotifyTo" value="${_osEscapeHtml(notifyTo)}"
            style="width:100%;font-size:11px;margin-bottom:2px;">
        <div style="font-size:10px;color:#888;">
            ${__('收件人識別碼，逗號分隔；留空＝取流程模板最後修改者')}
        </div>
    </div>${setTimeout(_osToggleModeFields, 0), ''}`;
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectOsExecutorConfig() {
    const command = document.getElementById('osCommand');
    if (!command) return null;

    const waitForResult = document.getElementById('osWaitForResult')?.value !== 'false';
    const pattern = document.getElementById('osExpectPattern')?.value.trim() || '';

    return {
        command: command.value,
        result_var: document.getElementById('osResultVar')?.value.trim() || '',
        timeout_seconds: _osClampInt(document.getElementById('osTimeout')?.value, 1, 3600, 60),
        wait_for_result: waitForResult,
        expect_exit_codes: _osParseExitCodes(document.getElementById('osExpectExitCodes')?.value),
        expect_pattern: pattern.slice(0, 200),
        expect_json: !!document.getElementById('osExpectJson')?.checked,
        cwd: document.getElementById('osCwd')?.value.trim() || '',
        extra_env: _osParseEnv(document.getElementById('osExtraEnv')?.value),
        kill_on_timeout: document.getElementById('osKillOnTimeout')?.value || 'group',
        cancel_scope: document.getElementById('osCancelScope')?.value || 'unit',
        stop_after: !!document.getElementById('osStopAfter')?.checked,
        notify_on_exception: !!document.getElementById('osNotifyOnException')?.checked,
        notify_to: _osParseList(document.getElementById('osNotifyTo')?.value)
    };
}
