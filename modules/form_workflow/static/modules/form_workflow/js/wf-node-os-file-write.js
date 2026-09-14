/**
 * wf-node-os-file-write.js -- OsFileWrite（檔案寫入）節點屬性面板
 */

function _fwEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _fwPositiveInt(value, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < 1) return fallback;
    return parsed;
}

// eslint-disable-next-line no-unused-vars
function renderOsFileWritePanel(node, nodeId) {
    const cfg = node.data('config') || {};

    const baseDir = cfg.base_dir || '';
    const filePath = cfg.file_path || '';
    const content = cfg.content || '';
    const newlineSmart = cfg.newline_smart !== false;
    const newlineBefore = cfg.newline_before === true;
    const newlineAfter = cfg.newline_after !== false;
    const createIfMissing = cfg.create_if_missing !== false;
    const encoding = cfg.encoding || 'utf-8';
    const maxFileBytes = cfg.max_file_bytes || 67108864;
    const lockTimeoutMs = cfg.lock_timeout_ms || 5000;
    const resultVar = cfg.result_var || '';
    const stopAfter = cfg.stop_after === true;

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('檔案寫入設定')}</h4>

        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('這個節點會在檔案結尾追加文字。寫入前會先把檔案結尾原有的換行符號（Windows/Linux/Mac 三種都算）全部清掉，再依下面兩個勾選補上換行。檔案原本的內容與編碼不會被更動。它與『檔案讀取』『OS 命令』節點是分開授權的。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('允許的根目錄')} *</label>
        <input type="text" id="fwBaseDir" value="${_fwEscapeHtml(baseDir)}"
            style="width:100%;font-size:11px;margin-bottom:6px;">

        <label style="font-size:11px;color:#555;">${__('檔案路徑')} *</label>
        <input type="text" id="fwFilePath" value="${_fwEscapeHtml(filePath)}"
            style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="/opt/tmp/app.log">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('可用 ${v.xxx} 變數')}
        </div>

        <label style="font-size:11px;color:#555;">${__('寫入內容')}</label>
        <textarea id="fwContent" rows="4"
            style="width:100%;font-size:11px;margin-bottom:6px;">${_fwEscapeHtml(content)}</textarea>

        <label style="display:block;font-size:11px;margin-bottom:2px;">
            <input type="checkbox" id="fwNewlineSmart" ${newlineSmart ? 'checked' : ''} onchange="toggleFwNewlineSmartUi()">
            ${__('緊接上一筆，另起新行')}
        </label>
        <label id="fwNewlineBeforeLabel" style="display:block;font-size:11px;margin-bottom:2px;${newlineSmart ? 'opacity:0.5;' : ''}">
            <input type="checkbox" id="fwNewlineBefore" ${newlineBefore ? 'checked' : ''} ${newlineSmart ? 'disabled' : ''}>
            ${__('內容前面加一個換行')}
        </label>
        <div id="fwNewlineBeforeNote" style="font-size:10px;color:#888;margin-bottom:2px;${newlineSmart ? '' : 'display:none;'}">
            ${__('已由「緊接上一筆，另起新行」接管')}
        </div>
        <label style="display:block;font-size:11px;margin-bottom:2px;">
            <input type="checkbox" id="fwNewlineAfter" ${newlineAfter ? 'checked' : ''}>
            ${__('內容後面加一個換行')}
        </label>
        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:6px;">
            ${__('預設的「緊接上一筆，另起新行」會自動接在既有內容後面另起一行：檔案是空的就直接從第一行開始，不會多出空行。取消它之後才由「內容前面加一個換行」手動控制；三個都不勾則字串直接接在檔案最後一個字後面（組合字串用）。')}
        </div>

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="fwCreateIfMissing" ${createIfMissing ? 'checked' : ''}>
            ${__('檔案不存在時自動建立')}
        </label>

        <label style="font-size:11px;color:#555;">${__('編碼')}</label>
        <input type="text" id="fwEncoding" value="${_fwEscapeHtml(encoding)}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="utf-8">

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
                <label style="font-size:11px;color:#555;">${__('檔案大小上限（位元組）')}</label>
                <input type="number" id="fwMaxFileBytes" value="${_fwEscapeHtml(maxFileBytes)}" min="1"
                    style="width:100%;font-size:11px;">
            </div>
            <div>
                <label style="font-size:11px;color:#555;">${__('取鎖逾時（毫秒）')}</label>
                <input type="number" id="fwLockTimeoutMs" value="${_fwEscapeHtml(lockTimeoutMs)}" min="1"
                    style="width:100%;font-size:11px;">
            </div>
        </div>

        <label style="font-size:11px;color:#555;">${__('結果變數前綴')} *</label>
        <input type="text" id="fwResultVar" value="${_fwEscapeHtml(resultVar)}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="write_log">

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="fwStopAfter" ${stopAfter ? 'checked' : ''}>
            ${__('這一步做完就結束這條分支')}
        </label>
    </div>`;
}

// eslint-disable-next-line no-unused-vars
function toggleFwNewlineSmartUi() {
    const smart = !!document.getElementById('fwNewlineSmart')?.checked;
    const before = document.getElementById('fwNewlineBefore');
    const label = document.getElementById('fwNewlineBeforeLabel');
    const note = document.getElementById('fwNewlineBeforeNote');
    if (before) before.disabled = smart;
    if (label) label.style.opacity = smart ? '0.5' : '';
    if (note) note.style.display = smart ? '' : 'none';
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectOsFileWriteConfig() {
    const baseDir = document.getElementById('fwBaseDir');
    if (!baseDir) return null;

    return {
        base_dir: baseDir.value.trim(),
        file_path: document.getElementById('fwFilePath')?.value.trim() || '',
        content: document.getElementById('fwContent')?.value || '',
        newline_smart: !!document.getElementById('fwNewlineSmart')?.checked,
        newline_before: !!document.getElementById('fwNewlineBefore')?.checked,
        newline_after: !!document.getElementById('fwNewlineAfter')?.checked,
        create_if_missing: !!document.getElementById('fwCreateIfMissing')?.checked,
        encoding: document.getElementById('fwEncoding')?.value.trim() || 'utf-8',
        max_file_bytes: _fwPositiveInt(document.getElementById('fwMaxFileBytes')?.value, 67108864),
        lock_timeout_ms: _fwPositiveInt(document.getElementById('fwLockTimeoutMs')?.value, 5000),
        result_var: document.getElementById('fwResultVar')?.value.trim() || '',
        stop_after: !!document.getElementById('fwStopAfter')?.checked
    };
}
