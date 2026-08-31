/**
 * wf-node-os-file-read.js -- OsFileRead（檔案讀取）節點屬性面板
 */

let _fileReadConfig = {};

function _frEscapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function _frClampInt(value, min, max, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < min || parsed > max) return fallback;
    return parsed;
}

function _frPositiveInt(value, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed) || parsed < 1) return fallback;
    return parsed;
}

function _frToggleModeFields() {
    const mode = document.getElementById('frMode')?.value || 'whole';
    const linesFields = document.getElementById('frLinesFields');
    const aroundFields = document.getElementById('frAroundFields');
    const maxWindowsField = document.getElementById('frMaxWindowsField');
    const occurrence = document.getElementById('frOccurrence')?.value || 'first';

    if (linesFields) linesFields.style.display = (mode === 'head' || mode === 'tail') ? 'block' : 'none';
    if (aroundFields) aroundFields.style.display = mode === 'around' ? 'block' : 'none';
    if (maxWindowsField) maxWindowsField.style.display = (mode === 'around' && occurrence === 'all') ? 'block' : 'none';
}

// eslint-disable-next-line no-unused-vars
function renderOsFileReadPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    _fileReadConfig = cfg;

    const baseDir = cfg.base_dir || '';
    const filePath = cfg.file_path || '';
    const resultVar = cfg.result_var || '';
    const mode = cfg.mode || 'whole';
    const lines = cfg.lines || 50;
    const keyword = cfg.keyword || '';
    const before = cfg.before ?? 3;
    const after = cfg.after ?? 3;
    const occurrence = cfg.occurrence || 'first';
    const maxWindows = cfg.max_windows || 10;
    const matchScope = cfg.match_scope || 'anywhere';
    const matchMode = cfg.match_mode || 'literal';
    const maxScanBytes = cfg.max_scan_bytes || 67108864;
    const maxScanMs = cfg.max_scan_ms || 5000;
    const encoding = cfg.encoding || 'utf-8';
    const stopAfter = cfg.stop_after === true;

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('檔案讀取設定')}</h4>

        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            ${__('唯讀讀取，不經過 shell，而且只能讀取系統管理員允許的目錄底下的檔案。這個節點與『OS 命令』節點是分開授權的。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('允許的根目錄')} *</label>
        <input type="text" id="frBaseDir" value="${_frEscapeHtml(baseDir)}"
            style="width:100%;font-size:11px;margin-bottom:6px;">

        <label style="font-size:11px;color:#555;">${__('檔案路徑')} *</label>
        <input type="text" id="frFilePath" value="${_frEscapeHtml(filePath)}"
            style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="/var/log/app.log">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('可用 ${v.xxx} 變數')}
        </div>

        <label style="font-size:11px;color:#555;">${__('結果變數前綴')} *</label>
        <input type="text" id="frResultVar" value="${_frEscapeHtml(resultVar)}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="file_content">

        <label style="font-size:11px;color:#555;">${__('讀取模式')}</label>
        <select id="frMode" onchange="_frToggleModeFields()" style="width:100%;font-size:11px;margin-bottom:2px;">
            <option value="whole" ${mode === 'whole' ? 'selected' : ''}>${__('整份檔案')}</option>
            <option value="head" ${mode === 'head' ? 'selected' : ''}>${__('檔頭')}</option>
            <option value="tail" ${mode === 'tail' ? 'selected' : ''}>${__('檔尾')}</option>
            <option value="around" ${mode === 'around' ? 'selected' : ''}>${__('關鍵字前後')}</option>
        </select>
        <div style="font-size:10px;color:#888;line-height:1.5;margin-bottom:6px;">
            ${__('檔尾（tail）是讀 log 最常用的方式；關鍵字前後（around）相當於 grep 的前後文，另外會回報命中次數，可以用分支節點判斷。')}
        </div>

        <div id="frLinesFields" style="margin-bottom:6px;">
            <label style="font-size:11px;color:#555;">${__('行數')}</label>
            <input type="number" id="frLines" value="${_frEscapeHtml(lines)}" min="1" max="5000"
                style="width:100%;font-size:11px;">
        </div>

        <div id="frAroundFields" style="margin-bottom:6px;">
            <label style="font-size:11px;color:#555;">${__('關鍵字')} *</label>
            <input type="text" id="frKeyword" value="${_frEscapeHtml(keyword)}"
                style="width:100%;font-size:11px;margin-bottom:6px;">

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
                <div>
                    <label style="font-size:11px;color:#555;">${__('前文行數')}</label>
                    <input type="number" id="frBefore" value="${_frEscapeHtml(before)}" min="0" max="200"
                        style="width:100%;font-size:11px;">
                </div>
                <div>
                    <label style="font-size:11px;color:#555;">${__('後文行數')}</label>
                    <input type="number" id="frAfter" value="${_frEscapeHtml(after)}" min="0" max="200"
                        style="width:100%;font-size:11px;">
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
                <div>
                    <label style="font-size:11px;color:#555;">${__('命中位置')}</label>
                    <select id="frOccurrence" onchange="_frToggleModeFields()" style="width:100%;font-size:11px;">
                        <option value="first" ${occurrence === 'first' ? 'selected' : ''}>${__('第一筆')}</option>
                        <option value="last" ${occurrence === 'last' ? 'selected' : ''}>${__('最後一筆')}</option>
                        <option value="all" ${occurrence === 'all' ? 'selected' : ''}>${__('全部')}</option>
                    </select>
                </div>
                <div id="frMaxWindowsField">
                    <label style="font-size:11px;color:#555;">${__('最多視窗數')}</label>
                    <input type="number" id="frMaxWindows" value="${_frEscapeHtml(maxWindows)}" min="1" max="100"
                        style="width:100%;font-size:11px;">
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
                <div>
                    <label style="font-size:11px;color:#555;">${__('比對範圍')}</label>
                    <select id="frMatchScope" style="width:100%;font-size:11px;">
                        <option value="anywhere" ${matchScope === 'anywhere' ? 'selected' : ''}>${__('任意位置')}</option>
                        <option value="line_start" ${matchScope === 'line_start' ? 'selected' : ''}>${__('行首')}</option>
                    </select>
                </div>
                <div>
                    <label style="font-size:11px;color:#555;">${__('比對模式')}</label>
                    <select id="frMatchMode" style="width:100%;font-size:11px;">
                        <option value="literal" ${matchMode === 'literal' ? 'selected' : ''}>${__('純文字')}</option>
                        <option value="regex" ${matchMode === 'regex' ? 'selected' : ''}>${__('正規表示式')}</option>
                    </select>
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
                <div>
                    <label style="font-size:11px;color:#555;">${__('最大掃描位元組')}</label>
                    <input type="number" id="frMaxScanBytes" value="${_frEscapeHtml(maxScanBytes)}" min="1"
                        style="width:100%;font-size:11px;">
                </div>
                <div>
                    <label style="font-size:11px;color:#555;">${__('最大掃描毫秒')}</label>
                    <input type="number" id="frMaxScanMs" value="${_frEscapeHtml(maxScanMs)}" min="1"
                        style="width:100%;font-size:11px;">
                </div>
            </div>
        </div>

        <label style="font-size:11px;color:#555;">${__('編碼')}</label>
        <input type="text" id="frEncoding" value="${_frEscapeHtml(encoding)}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="utf-8">

        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="frStopAfter" ${stopAfter ? 'checked' : ''}>
            ${__('這一步做完就結束這條分支')}
        </label>
    </div>${setTimeout(_frToggleModeFields, 0), ''}`;
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectOsFileReadConfig() {
    const baseDir = document.getElementById('frBaseDir');
    if (!baseDir) return null;

    const mode = document.getElementById('frMode')?.value || 'whole';
    const occurrence = document.getElementById('frOccurrence')?.value || 'first';
    const matchScope = document.getElementById('frMatchScope')?.value || 'anywhere';
    const matchMode = document.getElementById('frMatchMode')?.value || 'literal';

    return {
        base_dir: baseDir.value.trim(),
        file_path: document.getElementById('frFilePath')?.value.trim() || '',
        result_var: document.getElementById('frResultVar')?.value.trim() || '',
        mode: ['whole', 'head', 'tail', 'around'].includes(mode) ? mode : 'whole',
        lines: _frClampInt(document.getElementById('frLines')?.value, 1, 5000, 50),
        keyword: document.getElementById('frKeyword')?.value.trim() || '',
        before: _frClampInt(document.getElementById('frBefore')?.value, 0, 200, 3),
        after: _frClampInt(document.getElementById('frAfter')?.value, 0, 200, 3),
        occurrence: ['first', 'last', 'all'].includes(occurrence) ? occurrence : 'first',
        max_windows: _frClampInt(document.getElementById('frMaxWindows')?.value, 1, 100, 10),
        match_scope: ['anywhere', 'line_start'].includes(matchScope) ? matchScope : 'anywhere',
        match_mode: ['literal', 'regex'].includes(matchMode) ? matchMode : 'literal',
        max_scan_bytes: _frPositiveInt(document.getElementById('frMaxScanBytes')?.value, 67108864),
        max_scan_ms: _frPositiveInt(document.getElementById('frMaxScanMs')?.value, 5000),
        encoding: document.getElementById('frEncoding')?.value.trim() || 'utf-8',
        stop_after: !!document.getElementById('frStopAfter')?.checked
    };
}
