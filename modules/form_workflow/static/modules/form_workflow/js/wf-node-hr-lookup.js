/**
 * wf-node-hr-lookup.js -- OpHrLookup（人事資料取值）節點屬性面板
 */

let opHrApprovalCategoriesData = null;
let opHrApprovalCategoriesLoading = false;

// eslint-disable-next-line no-unused-vars
function renderOpHrLookupPanel(node, nodeId) {
    const cfg = node.data('config') || {};
    const targetSource = cfg.target_source || 'applicant';
    const targetExpr = cfg.target_expr || '';
    const varPrefix = cfg.var_prefix || 'hr';
    const approvalCategoryCode = cfg.approval_category_code || '';
    const approverMode = cfg.approver_mode === true;
    const amountExpr = cfg.amount_expr || '';

    setTimeout(() => {
        toggleOpHrTargetExprUi();
        toggleOpHrApproverUi();
        updateOpHrVariablePreview();
        loadOpHrApprovalCategories(approvalCategoryCode);
    }, 50);

    return `
    <div class="node-config-section">
        <h4 style="margin:10px 0 6px;font-size:13px;">${__('人事資料取值設定')}</h4>

        <label style="font-size:11px;color:#555;display:block;margin-bottom:4px;">${__('對象')}</label>
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:6px;font-size:11px;">
            <label style="display:flex;gap:4px;align-items:center;">
                <input type="radio" name="opHrTargetSource" value="applicant" ${targetSource !== 'variable' ? 'checked' : ''} onchange="toggleOpHrTargetExprUi()">
                ${__('表單申請人')}
            </label>
            <label style="display:flex;gap:4px;align-items:center;">
                <input type="radio" name="opHrTargetSource" value="variable" ${targetSource === 'variable' ? 'checked' : ''} onchange="toggleOpHrTargetExprUi()">
                ${__('變數')}
            </label>
        </div>

        <div id="opHrTargetExprWrap" style="margin-bottom:6px;">
            <label style="font-size:11px;color:#555;">${__('對象變數表達式')}</label>
            <input type="text" id="opHrTargetExpr" value="${_fwEscapeHtml(targetExpr)}"
                style="width:100%;font-size:11px;" placeholder="${_fwEscapeHtml('${v.hr_direct_manager}')}">
        </div>

        <label style="font-size:11px;color:#555;">${__('變數前綴')}</label>
        <input type="text" id="opHrVarPrefix" value="${_fwEscapeHtml(varPrefix)}"
            style="width:100%;font-size:11px;margin-bottom:6px;" placeholder="hr" oninput="updateOpHrVariablePreview()">

        <label style="font-size:11px;color:#555;">${__('核決類別')}</label>
        <div id="opHrApprovalCategoryWrap" style="margin-bottom:6px;">
            <select id="opHrApprovalCategoryCode" data-selected="${_fwEscapeHtml(approvalCategoryCode)}"
                style="width:100%;font-size:11px;">
                <option value="">${__('載入中')}</option>
            </select>
        </div>

        <label style="display:flex;gap:4px;align-items:center;font-size:11px;margin-bottom:6px;">
            <input type="checkbox" id="opHrApproverMode" ${approverMode ? 'checked' : ''} onchange="toggleOpHrApproverUi()">
            ${__('依金額找核決人')}
        </label>

        <div id="opHrAmountExprWrap" style="margin-bottom:6px;">
            <label style="font-size:11px;color:#555;">${__('金額表達式')}</label>
            <input type="text" id="opHrAmountExpr" value="${_fwEscapeHtml(amountExpr)}"
                style="width:100%;font-size:11px;" placeholder="${_fwEscapeHtml('${f.amount}')}">
        </div>

        <div style="font-size:10px;color:#666;line-height:1.6;margin-top:8px;padding:6px;background:#f8f8f8;border:1px solid #eee;border-radius:4px;">
            <div style="font-weight:600;margin-bottom:3px;">${__('會寫入的變數')}</div>
            <div id="opHrVariablePreview"></div>
        </div>
    </div>`;
}

// eslint-disable-next-line no-unused-vars
function toggleOpHrTargetExprUi() {
    const source = document.querySelector('input[name="opHrTargetSource"]:checked')?.value || 'applicant';
    const wrap = document.getElementById('opHrTargetExprWrap');
    if (wrap) wrap.style.display = source === 'variable' ? '' : 'none';
}

// eslint-disable-next-line no-unused-vars
function toggleOpHrApproverUi() {
    const enabled = !!document.getElementById('opHrApproverMode')?.checked;
    const wrap = document.getElementById('opHrAmountExprWrap');
    if (wrap) wrap.style.display = enabled ? '' : 'none';
}

// eslint-disable-next-line no-unused-vars
function updateOpHrVariablePreview() {
    const input = document.getElementById('opHrVarPrefix');
    const preview = document.getElementById('opHrVariablePreview');
    if (!preview) return;

    const raw = input?.value.trim() || 'hr';
    const prefix = /^[A-Za-z_][A-Za-z0-9_]*$/.test(raw) ? raw : 'hr';
    const suffixes = [
        '_found',
        '_job_level_order',
        '_is_supervisor',
        '_job_family_code',
        '_direct_manager',
        '_approval_limit',
        '_approver'
    ];
    preview.innerHTML = suffixes
        .map((suffix) => `<code style="display:inline-block;margin:1px 4px 1px 0;">${_fwEscapeHtml(prefix + suffix)}</code>`)
        .join('');
}

async function loadOpHrApprovalCategories(selectedValue) {
    if (opHrApprovalCategoriesData) {
        setTimeout(() => renderOpHrApprovalCategories(selectedValue), 20);
        return;
    }
    if (opHrApprovalCategoriesLoading) return;

    opHrApprovalCategoriesLoading = true;
    try {
        const response = await fetch(window.__BP + '/api/workflows/data/approval-categories');
        const result = await response.json();
        if (!result.success) throw new Error(result.error || 'load failed');
        opHrApprovalCategoriesData = result.data || [];
        renderOpHrApprovalCategories(selectedValue);
    } catch (error) {
        console.error('載入核決類別失敗:', error);
        renderOpHrApprovalCategoryFallback(selectedValue);
    } finally {
        opHrApprovalCategoriesLoading = false;
    }
}

function renderOpHrApprovalCategories(selectedValue) {
    const select = document.getElementById('opHrApprovalCategoryCode');
    if (!select) return;
    const selected = selectedValue ?? select.dataset.selected ?? '';
    let html = `<option value="">${__('不查核決上限')}</option>`;
    for (const item of opHrApprovalCategoriesData || []) {
        const code = item.code || '';
        const label = item.currency ? `${item.code} - ${item.name} (${item.currency})` : `${item.code} - ${item.name}`;
        html += `<option value="${_fwEscapeHtml(code)}" ${code === selected ? 'selected' : ''}>${_fwEscapeHtml(label)}</option>`;
    }
    select.innerHTML = html;
}

function renderOpHrApprovalCategoryFallback(selectedValue) {
    const wrap = document.getElementById('opHrApprovalCategoryWrap');
    if (!wrap) return;
    wrap.innerHTML = `<input type="text" id="opHrApprovalCategoryCode" value="${_fwEscapeHtml(selectedValue || '')}"
        style="width:100%;font-size:11px;" placeholder="TRAVEL">`;
}

/** 收集面板設定，回傳要合併進 node config 的物件；面板不存在時回傳 null */
// eslint-disable-next-line no-unused-vars
function collectOpHrLookupConfig() {
    const prefix = document.getElementById('opHrVarPrefix');
    if (!prefix) return null;

    return {
        target_source: document.querySelector('input[name="opHrTargetSource"]:checked')?.value || 'applicant',
        target_expr: document.getElementById('opHrTargetExpr')?.value.trim() || '',
        var_prefix: prefix.value.trim() || 'hr',
        approval_category_code: document.getElementById('opHrApprovalCategoryCode')?.value.trim().toUpperCase() || '',
        approver_mode: !!document.getElementById('opHrApproverMode')?.checked,
        amount_expr: document.getElementById('opHrAmountExpr')?.value.trim() || ''
    };
}
