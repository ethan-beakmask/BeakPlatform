/**
 * VarPicker — 變數插入器
 * 讓用戶從下拉清單選取變數，自動插入 ${prefix.name} 語法到目標輸入欄位。
 */
(function() {
    'use strict';

    var panelEl = null;   // 當前開啟的面板 DOM
    var targetEl = null;  // 當前目標輸入框

    // ── 固定清單 ──

    var FI_ITEMS = [
        { key: 'applicant',       label: __('申請人') },
        { key: 'applicant_dept',  label: __('申請人部門') },
        { key: 'applicant_email', label: __('申請人信箱') },
        { key: 'serial',         label: __('流水號') },
        { key: 'name',           label: __('表單名稱') },
        { key: 'subject',        label: __('表單主旨') },
        { key: 'code',           label: __('表單代碼') },
        { key: 'status',         label: __('表單狀態') }
    ];

    var WI_ITEMS = [
        { key: 'code',      label: __('流程代碼') },
        { key: 'exec_code', label: __('流程執行代碼') },
        { key: 'name',      label: __('流程名稱') },
        { key: 'status',    label: __('流程狀態') },
        { key: 'depth',     label: __('流程深度') }
    ];

    var N_ITEMS = [
        { key: 'name', label: __('節點名稱') },
        { key: 'id',   label: __('節點 ID') },
        { key: 'type', label: __('節點類型') }
    ];

    var T_ITEMS = [
        { key: 'now',  label: __('當前時間') },
        { key: 'date', label: __('當前日期') },
        { key: 'time', label: __('當前時刻') }
    ];

    // ── collectVars ──

    function collectVars() {
        var groups = [];

        // 1) f.* — 表單欄位
        var formItems = [];
        if (window.currentFormFields && window.currentFormFields.length > 0) {
            window.currentFormFields.forEach(function(f) {
                formItems.push({ key: f.key, label: f.label || f.key });
            });
        }
        // 2) fi.* — 表單實例
        var fiItems = FI_ITEMS.map(function(it) {
            return { key: it.key, label: it.label };
        });

        if (formItems.length > 0 || fiItems.length > 0) {
            groups.push({
                title: __('表單類'),
                items: formItems.map(function(it) {
                    return { prefix: 'f', key: it.key, label: it.label };
                }).concat(fiItems.map(function(it) {
                    return { prefix: 'fi', key: it.key, label: it.label };
                }))
            });
        }

        // 3) v.* — 流程變數 (掃描 cy graph)
        var varItems = [];
        if (window.cy) {
            window.cy.nodes().forEach(function(node) {
                var type = node.data('type') || '';
                var config = node.data('config') || {};
                var nodeName = node.data('display_name') || node.data('label') || node.id();

                if (type === 'OpSet') {
                    var ops = config.operations || [];
                    ops.forEach(function(op) {
                        if (op.target_var) {
                            varItems.push({ key: op.target_var, label: nodeName });
                        }
                    });
                }
                if (type === 'FormAdapter' && config.output_variable) {
                    varItems.push({ key: config.output_variable, label: nodeName });
                }
                if (type === 'SysSqlExecutor' && config.result_var) {
                    varItems.push({ key: config.result_var, label: nodeName });
                }
            });
        }
        // 去重
        var seen = {};
        varItems = varItems.filter(function(it) {
            if (seen[it.key]) return false;
            seen[it.key] = true;
            return true;
        });

        // 4) wi.* / n.* / t.*
        var flowItems = [];
        WI_ITEMS.forEach(function(it) {
            flowItems.push({ prefix: 'wi', key: it.key, label: it.label });
        });
        N_ITEMS.forEach(function(it) {
            flowItems.push({ prefix: 'n', key: it.key, label: it.label });
        });
        T_ITEMS.forEach(function(it) {
            flowItems.push({ prefix: 't', key: it.key, label: it.label });
        });

        if (varItems.length > 0 || flowItems.length > 0) {
            var vMapped = varItems.map(function(it) {
                return { prefix: 'v', key: it.key, label: it.label };
            });
            groups.push({
                title: __('流程類'),
                items: vMapped.concat(flowItems)
            });
        }

        return groups;
    }

    // ── 建立面板 DOM ──

    function buildPanel(groups) {
        var wrap = document.createElement('div');
        wrap.className = 'varpicker-panel';
        wrap.style.cssText = 'position:absolute;z-index:99999;width:260px;max-height:320px;background:#fff;border:1px solid #ccc;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.15);overflow:hidden;font-size:12px;';

        // 搜尋欄
        var search = document.createElement('input');
        search.type = 'text';
        search.placeholder = '搜尋變數...';
        search.style.cssText = 'width:100%;padding:6px 8px;border:none;border-bottom:1px solid #e0e0e0;outline:none;font-size:12px;box-sizing:border-box;';
        wrap.appendChild(search);

        // 列表容器
        var list = document.createElement('div');
        list.style.cssText = 'max-height:274px;overflow-y:auto;';
        wrap.appendChild(list);

        function renderList(filter) {
            list.innerHTML = '';
            var lowerFilter = (filter || '').toLowerCase();
            var hasAny = false;

            groups.forEach(function(group) {
                var filtered = group.items.filter(function(it) {
                    if (!lowerFilter) return true;
                    var full = it.prefix + '.' + it.key;
                    return full.toLowerCase().indexOf(lowerFilter) !== -1 ||
                           it.label.toLowerCase().indexOf(lowerFilter) !== -1;
                });
                if (filtered.length === 0) return;
                hasAny = true;

                // 群組標題
                var header = document.createElement('div');
                header.style.cssText = 'padding:4px 8px;font-size:10px;font-weight:bold;color:#999;background:#f7f7f7;border-bottom:1px solid #eee;';
                header.textContent = group.title;
                list.appendChild(header);

                filtered.forEach(function(it) {
                    var row = document.createElement('div');
                    row.style.cssText = 'padding:5px 8px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #f5f5f5;';
                    row.onmouseenter = function() { row.style.background = '#f0f7ff'; };
                    row.onmouseleave = function() { row.style.background = ''; };

                    var left = document.createElement('code');
                    left.style.cssText = 'font-size:11px;color:#333;';
                    left.textContent = it.prefix + '.' + it.key;

                    var right = document.createElement('span');
                    right.style.cssText = 'font-size:10px;color:#999;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                    right.textContent = it.label;

                    row.appendChild(left);
                    row.appendChild(right);

                    row.addEventListener('click', function() {
                        insertVar(it.prefix + '.' + it.key);
                    });

                    list.appendChild(row);
                });
            });

            if (!hasAny) {
                var empty = document.createElement('div');
                empty.style.cssText = 'padding:16px;text-align:center;color:#999;font-size:11px;';
                empty.textContent = __('無匹配變數');
                list.appendChild(empty);
            }
        }

        search.addEventListener('input', function() {
            renderList(search.value);
        });

        renderList('');

        // 自動 focus 搜尋
        setTimeout(function() { search.focus(); }, 50);

        return wrap;
    }

    // ── 插入變數 ──

    function insertVar(varExpr) {
        if (!targetEl) return;
        var text = '${' + varExpr + '}';

        if (typeof targetEl.selectionStart === 'number') {
            var start = targetEl.selectionStart;
            var end = targetEl.selectionEnd;
            var val = targetEl.value;
            targetEl.value = val.substring(0, start) + text + val.substring(end);
            targetEl.selectionStart = targetEl.selectionEnd = start + text.length;
        } else {
            targetEl.value += text;
        }

        // 觸發 change + input 事件
        targetEl.dispatchEvent(new Event('change', { bubbles: true }));
        targetEl.dispatchEvent(new Event('input', { bubbles: true }));

        close();
        targetEl.focus();
    }

    // ── 定位面板 ──

    function positionPanel(anchorEl) {
        if (!panelEl || !anchorEl) return;
        var rect = anchorEl.getBoundingClientRect();
        var scrollY = window.pageYOffset || document.documentElement.scrollTop;
        var scrollX = window.pageXOffset || document.documentElement.scrollLeft;

        var top = rect.bottom + scrollY + 2;
        var left = rect.left + scrollX;

        // 右邊界檢查
        if (left + 260 > window.innerWidth) {
            left = window.innerWidth - 270;
        }
        // 下邊界檢查：如果超出視窗，改為向上開
        if (rect.bottom + 324 > window.innerHeight) {
            top = rect.top + scrollY - 324;
            if (top < 0) top = scrollY + 4;
        }

        panelEl.style.top = top + 'px';
        panelEl.style.left = left + 'px';
    }

    // ── 外部點擊 / Escape 關閉 ──

    function onDocClick(e) {
        if (panelEl && !panelEl.contains(e.target)) {
            close();
        }
    }

    function onKeyDown(e) {
        if (e.key === 'Escape') {
            close();
        }
    }

    // ── Public API ──

    function open(anchorEl, tgtEl) {
        close(); // 先關閉舊的
        targetEl = tgtEl;

        var groups = collectVars();
        panelEl = buildPanel(groups);
        document.body.appendChild(panelEl);
        positionPanel(anchorEl);

        setTimeout(function() {
            document.addEventListener('mousedown', onDocClick, true);
            document.addEventListener('keydown', onKeyDown, true);
        }, 0);
    }

    function close() {
        if (panelEl) {
            panelEl.remove();
            panelEl = null;
        }
        targetEl = null;
        document.removeEventListener('mousedown', onDocClick, true);
        document.removeEventListener('keydown', onKeyDown, true);
    }

    window.VarPicker = {
        open: open,
        close: close,
        collectVars: collectVars
    };
})();
