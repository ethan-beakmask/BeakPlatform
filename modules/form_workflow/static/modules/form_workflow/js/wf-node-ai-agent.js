/**
 * wf-node-ai-agent.js -- AiAgent（AI 分析）節點屬性面板
 *
 * 對應後端 handler:
 *   modules/form_workflow/services/node_handlers/ai_agent_handler.py
 *
 * 面板只負責收集設定，所有安全防護（canary 驗證、規則層 injection 偵測、
 * 輸出跳脫、CLI 沙箱隔離）都在後端 handler，前端改不掉也繞不過。
 */

// eslint-disable-next-line no-unused-vars
function renderAiAgentPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    const instruction = cfg.instruction || '';
    const payloadTpl = cfg.payload_template || '';
    const resultVar = cfg.result_var || '';
    const model = cfg.model || 'claude-sonnet-5';
    const timeout = cfg.timeout_seconds || 60;
    const decode = cfg.decode_payload !== false;
    const writeNote = cfg.write_approval_note !== false;
    const onError = cfg.on_error || 'error';

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('AI 分析設定')}</h4>

        <label style="font-size:11px;color:#555;">${__('給 AI 的指示')}</label>
        <textarea id="aiInstruction" rows="2"
            style="width:100%;font-size:11px;margin-bottom:6px;"
            placeholder="${__('留空使用預設：HTTP 流量安全分析器')}">${instruction}</textarea>

        <label style="font-size:11px;color:#555;">${__('要分析的內容')} *</label>
        <textarea id="aiPayloadTpl" rows="3"
            style="width:100%;font-size:11px;font-family:monospace;margin-bottom:2px;"
            placeholder="\${f.raw_request}">${payloadTpl}</textarea>
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('可用流程變數，例如 ${f.欄位} 或 ${v.變數}。內容視為不可信資料，會包在邊界標記內送給 AI。')}
        </div>

        <label style="font-size:11px;color:#555;">${__('結果寫入變數')} *</label>
        <input type="text" id="aiResultVar" value="${resultVar}"
            style="width:100%;font-size:11px;margin-bottom:2px;" placeholder="ai_verdict">
        <div style="font-size:10px;color:#888;margin-bottom:6px;">
            ${__('後續節點用 ${v.變數名} 取用，內含 verdict / score / reasons / note / rule_hits')}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
                <label style="font-size:11px;color:#555;">${__('模型')}</label>
                <select id="aiModel" style="width:100%;font-size:11px;">
                    <option value="claude-sonnet-5" ${model === 'claude-sonnet-5' ? 'selected' : ''}>claude-sonnet-5</option>
                    <option value="claude-opus-5" ${model === 'claude-opus-5' ? 'selected' : ''}>claude-opus-5</option>
                    <option value="claude-haiku-4-5" ${model === 'claude-haiku-4-5' ? 'selected' : ''}>claude-haiku-4-5</option>
                </select>
            </div>
            <div>
                <label style="font-size:11px;color:#555;">${__('逾時（秒）')}</label>
                <input type="number" id="aiTimeout" value="${timeout}" min="10" max="300"
                    style="width:100%;font-size:11px;">
            </div>
        </div>

        <label style="display:block;font-size:11px;margin-bottom:4px;">
            <input type="checkbox" id="aiDecode" ${decode ? 'checked' : ''}>
            ${__('自動解碼（Base64／URL encoding，最多 3 層）')}
        </label>
        <label style="display:block;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="aiWriteNote" ${writeNote ? 'checked' : ''}>
            ${__('把分析結果寫成簽核註記供人員參考')}
        </label>

        <label style="font-size:11px;color:#555;">${__('AI 失敗時')}</label>
        <select id="aiOnError" style="width:100%;font-size:11px;margin-bottom:4px;">
            <option value="error" ${onError === 'error' ? 'selected' : ''}>${__('視為節點錯誤（走 error 邊）')}</option>
            <option value="continue" ${onError === 'continue' ? 'selected' : ''}>${__('繼續流程（只留規則層結果）')}</option>
        </select>
        <div style="font-size:10px;color:#888;">
            ${__('AI 輸出未通過 canary 驗證時一律作廢，不會重試到通過為止。規則層的 injection 偵測不經過 AI，一定生效。')}
        </div>
    </div>`;
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectAiAgentConfig() {
    const resultVar = document.getElementById('aiResultVar');
    const payloadTpl = document.getElementById('aiPayloadTpl');
    if (!resultVar || !payloadTpl) return null;
    return {
        instruction: document.getElementById('aiInstruction')?.value?.trim() || '',
        payload_template: payloadTpl.value || '',
        result_var: resultVar.value.trim(),
        model: document.getElementById('aiModel')?.value || 'claude-sonnet-5',
        timeout_seconds: parseInt(document.getElementById('aiTimeout')?.value, 10) || 60,
        decode_payload: !!document.getElementById('aiDecode')?.checked,
        write_approval_note: !!document.getElementById('aiWriteNote')?.checked,
        on_error: document.getElementById('aiOnError')?.value || 'error',
    };
}
