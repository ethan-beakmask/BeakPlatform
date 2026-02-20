/**
 * FormAdapter 自定義決策選項管理
 *
 * 提供 Designer 面板中決策選項的 CRUD、edge 映射、
 * input_variables 設定 UI。
 */
(function () {
    'use strict';

    // ========================================
    // 決策選項 CRUD
    // ========================================

    /**
     * 產生 UUID-like ID
     */
    function generateOptionId() {
        var s = 'xxxxxxxxxxxx'.replace(/x/g, function () {
            return (Math.random() * 16 | 0).toString(16);
        });
        return 'opt-' + s;
    }

    /**
     * 取得當前節點的所有出邊 (從 cytoscape)
     */
    function getOutgoingEdges(nodeId) {
        if (!window.cy) return [];
        const edges = [];
        window.cy.edges().forEach(function (edge) {
            const src = edge.data('source');
            if (src === nodeId) {
                edges.push({
                    id: edge.id(),
                    label: edge.data('label') || '',
                    target: edge.data('target')
                });
            }
        });
        return edges;
    }

    /**
     * 取得目標節點的 label
     */
    function getNodeLabel(nodeId) {
        if (!window.cy) return nodeId;
        const node = window.cy.getElementById(nodeId);
        if (node && node.length > 0) {
            return node.data('label') || node.data('type') || nodeId;
        }
        return nodeId;
    }

    /**
     * 渲染決策選項列表
     */
    function renderDecisionOptions(nodeId, options, outEdges) {
        const container = document.getElementById('decisionOptionsContainer');
        if (!container) return;

        if (!options || options.length === 0) {
            container.innerHTML = '<div style="color: #999; font-size: 12px; text-align: center; padding: 15px;">尚無決策選項，請點擊下方按鈕新增</div>';
            _ensureAutoSave(container, nodeId, 'decisions');
            return;
        }

        let html = '';
        options.forEach(function (opt, idx) {
            const styleClass = opt.style || 'default';
            const borderColors = {
                'primary': '#667eea',
                'success': '#28a745',
                'warning': '#ffc107',
                'danger': '#dc3545',
                'default': '#6c757d'
            };
            const borderColor = borderColors[styleClass] || borderColors['default'];

            html += '<div class="decision-option-card" data-option-id="' + opt.id + '" style="border: 2px solid ' + borderColor + '; border-radius: 6px; padding: 12px; margin-bottom: 10px; background: white;">';

            // 標題列
            html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
            html += '<span style="font-weight: bold; font-size: 13px; color: ' + borderColor + ';">#' + (idx + 1) + '</span>';
            html += '<div>';
            if (idx > 0) {
                html += '<button onclick="window._faDecisions.moveOption(\'' + nodeId + '\', ' + idx + ', -1)" style="background: none; border: none; cursor: pointer; color: #666; padding: 2px 4px;" title="上移"><i class="fas fa-arrow-up"></i></button>';
            }
            if (idx < options.length - 1) {
                html += '<button onclick="window._faDecisions.moveOption(\'' + nodeId + '\', ' + idx + ', 1)" style="background: none; border: none; cursor: pointer; color: #666; padding: 2px 4px;" title="下移"><i class="fas fa-arrow-down"></i></button>';
            }
            html += '<button onclick="window._faDecisions.removeOption(\'' + nodeId + '\', \'' + opt.id + '\')" style="background: none; border: none; cursor: pointer; color: #dc3545; padding: 2px 4px;" title="刪除"><i class="fas fa-trash"></i></button>';
            html += '</div></div>';

            // Label 與 Value
            html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">';
            html += '<div>';
            html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">顯示名稱</label>';
            html += '<input type="text" data-field="label" value="' + _escapeAttr(opt.label || '') + '" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：核准">';
            html += '</div>';
            html += '<div>';
            html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">傳出值</label>';
            html += '<input type="text" data-field="value" value="' + _escapeAttr(opt.value || '') + '" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：approved">';
            html += '</div></div>';

            // Style 選擇
            html += '<div style="margin-bottom: 8px;">';
            html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">按鈕風格</label>';
            html += '<select data-field="style" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">';
            var styles = [
                { v: 'primary', l: '主要 (藍)' },
                { v: 'success', l: '成功 (綠)' },
                { v: 'warning', l: '警告 (黃)' },
                { v: 'danger', l: '危險 (紅)' },
                { v: 'default', l: '預設 (灰)' }
            ];
            styles.forEach(function (s) {
                html += '<option value="' + s.v + '"' + (styleClass === s.v ? ' selected' : '') + '>' + s.l + '</option>';
            });
            html += '</select></div>';

            // Target Edges (checkboxes)
            html += '<div style="margin-bottom: 8px;">';
            html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 4px;">目標連接線 (N:M 映射)</label>';
            if (outEdges.length === 0) {
                html += '<div style="color: #999; font-size: 11px;">此節點尚無出線</div>';
            } else {
                var selectedEdges = opt.target_edges || [];
                outEdges.forEach(function (edge) {
                    var checked = selectedEdges.indexOf(edge.id) >= 0 ? ' checked' : '';
                    var targetLabel = getNodeLabel(edge.target);
                    var displayText = edge.label ? edge.label + ' → ' + targetLabel : '→ ' + targetLabel;
                    html += '<label style="display: flex; align-items: center; font-size: 12px; margin-bottom: 3px; cursor: pointer;">';
                    html += '<input type="checkbox" data-edge-id="' + edge.id + '"' + checked + ' style="margin-right: 6px;">';
                    html += '<span>' + _escapeHtml(displayText) + '</span>';
                    html += '<span style="color: #aaa; font-size: 10px; margin-left: 4px;">(' + edge.id + ')</span>';
                    html += '</label>';
                });
            }
            html += '<div style="font-size: 10px; color: #888; margin-top: 3px;">空 = 觸發 REJECTED 終態</div>';
            html += '</div>';

            // Visible When (簡易條件)
            var vw = opt.visible_when || {};
            html += '<div style="border-top: 1px solid #eee; padding-top: 8px;">';
            html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 4px;">條件顯示 (可選)</label>';
            html += '<div style="display: grid; grid-template-columns: 1fr auto 1fr; gap: 4px;">';
            html += '<input type="text" data-field="vw_variable" value="' + _escapeAttr(vw.variable || '') + '" placeholder="變數名" style="padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
            html += '<select data-field="vw_operator" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
            var ops = ['==', '!=', '>', '>=', '<', '<=', 'contains', 'not_empty', 'empty'];
            ops.forEach(function (op) {
                html += '<option value="' + op + '"' + (vw.operator === op ? ' selected' : '') + '>' + op + '</option>';
            });
            html += '</select>';
            html += '<input type="text" data-field="vw_value" value="' + _escapeAttr(vw.value || '') + '" placeholder="比較值" style="padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
            html += '</div></div>';

            html += '</div>';  // card end
        });

        container.innerHTML = html;

        // 掛上自動存檔（event delegation，input/change 即時回寫 config）
        _ensureAutoSave(container, nodeId, 'decisions');
    }

    /**
     * 在容器上掛 event delegation，DOM 變更即時寫回 cytoscape node config。
     * 切換節點時移除舊 handler、重新掛載新的。
     */
    function _ensureAutoSave(container, nodeId, type) {
        var flagKey = '_autoSave_' + type;
        var handlerKey = '_autoSaveHandler_' + type;

        // 同一節點已掛載，跳過
        if (container[flagKey] === nodeId) return;

        // 移除舊 handler（切換到不同節點時）
        if (container[handlerKey]) {
            container.removeEventListener('input', container[handlerKey]);
            container.removeEventListener('change', container[handlerKey]);
        }

        container[flagKey] = nodeId;

        var handler = function () {
            var node = window.cy ? window.cy.getElementById(nodeId) : null;
            if (!node || node.length === 0) return;
            var config = node.data('config') || {};

            if (type === 'decisions') {
                config.decision_options = collectDecisionOptions();
            } else if (type === 'inputVars') {
                config.input_variables = collectInputVariables();
            }
            node.data('config', config);
        };

        container[handlerKey] = handler;
        container.addEventListener('input', handler);
        container.addEventListener('change', handler);
    }

    /**
     * 從 DOM 收集決策選項資料
     */
    function collectDecisionOptions() {
        const container = document.getElementById('decisionOptionsContainer');
        if (!container) return [];

        var cards = container.querySelectorAll('.decision-option-card');
        var options = [];
        cards.forEach(function (card) {
            var optId = card.getAttribute('data-option-id');
            var label = card.querySelector('[data-field="label"]').value.trim();
            var value = card.querySelector('[data-field="value"]').value.trim();
            var style = card.querySelector('[data-field="style"]').value;

            // 收集 target_edges
            var targetEdges = [];
            card.querySelectorAll('[data-edge-id]').forEach(function (cb) {
                if (cb.checked) {
                    targetEdges.push(cb.getAttribute('data-edge-id'));
                }
            });

            // 收集 visible_when
            var vwVar = card.querySelector('[data-field="vw_variable"]').value.trim();
            var vwOp = card.querySelector('[data-field="vw_operator"]').value;
            var vwVal = card.querySelector('[data-field="vw_value"]').value.trim();
            var visibleWhen = null;
            if (vwVar) {
                visibleWhen = { variable: vwVar, operator: vwOp, value: vwVal };
            }

            options.push({
                id: optId,
                label: label,
                value: value,
                target_edges: targetEdges,
                style: style,
                visible_when: visibleWhen
            });
        });

        return options;
    }

    /**
     * 新增決策選項
     */
    function addOption(nodeId) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = config.decision_options || [];
        options.push({
            id: generateOptionId(),
            label: '',
            value: '',
            target_edges: [],
            style: 'default',
            visible_when: null
        });

        config.decision_options = options;
        config.use_custom_decisions = true;
        node.data('config', config);

        var outEdges = getOutgoingEdges(nodeId);
        renderDecisionOptions(nodeId, options, outEdges);
    }

    /**
     * 移除決策選項
     */
    function removeOption(nodeId, optionId) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = (config.decision_options || []).filter(function (o) { return o.id !== optionId; });
        config.decision_options = options;
        node.data('config', config);

        var outEdges = getOutgoingEdges(nodeId);
        renderDecisionOptions(nodeId, options, outEdges);
    }

    /**
     * 移動決策選項 (上/下)
     */
    function moveOption(nodeId, index, direction) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = config.decision_options || [];
        var newIndex = index + direction;
        if (newIndex < 0 || newIndex >= options.length) return;

        var temp = options[index];
        options[index] = options[newIndex];
        options[newIndex] = temp;

        config.decision_options = options;
        node.data('config', config);

        var outEdges = getOutgoingEdges(nodeId);
        renderDecisionOptions(nodeId, options, outEdges);
    }

    // ========================================
    // Input Variables UI
    // ========================================

    /**
     * 渲染 input_variables 設定 UI
     */
    function renderInputVariables(nodeId, inputVars) {
        var container = document.getElementById('inputVariablesContainer');
        if (!container) return;

        if (!inputVars || inputVars.length === 0) {
            container.innerHTML = '<div style="color: #999; font-size: 12px; text-align: center; padding: 10px;">尚無來向變數控制規則</div>';
            _ensureAutoSave(container, nodeId, 'inputVars');
            return;
        }

        var html = '';
        inputVars.forEach(function (varDef, vIdx) {
            html += '<div class="input-var-card" data-var-index="' + vIdx + '" style="border: 1px solid #e0e0e0; border-radius: 6px; padding: 10px; margin-bottom: 8px; background: #fafafa;">';

            // 變數名稱 + 刪除
            html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
            html += '<div style="flex: 1; margin-right: 8px;">';
            html += '<label style="font-size: 11px; color: #666;">變數名稱</label>';
            html += '<input type="text" data-field="var_name" value="' + _escapeAttr(varDef.var_name || '') + '" style="width: 100%; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：approval_level">';
            html += '</div>';
            html += '<button onclick="window._faDecisions.removeInputVar(\'' + nodeId + '\', ' + vIdx + ')" style="background: none; border: none; cursor: pointer; color: #dc3545; margin-top: 14px;" title="刪除"><i class="fas fa-trash"></i></button>';
            html += '</div>';

            // Controls
            var controls = varDef.controls || [];
            controls.forEach(function (ctrl, cIdx) {
                html += '<div class="input-var-control" data-ctrl-index="' + cIdx + '" style="border: 1px dashed #ccc; border-radius: 4px; padding: 8px; margin-bottom: 6px; background: white;">';

                html += '<div style="display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap;">';
                // 控制類型
                html += '<select data-field="ctrl_type" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
                html += '<option value="decision_visibility"' + (ctrl.type === 'decision_visibility' ? ' selected' : '') + '>決策顯示</option>';
                html += '<option value="field_permission"' + (ctrl.type === 'field_permission' ? ' selected' : '') + '>欄位權限</option>';
                html += '</select>';

                // 條件
                html += '<select data-field="ctrl_operator" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
                var ops = ['==', '!=', '>', '>=', '<', '<=', 'contains', 'not_empty', 'empty'];
                ops.forEach(function (op) {
                    var selOp = (ctrl.condition || {}).operator || '==';
                    html += '<option value="' + op + '"' + (selOp === op ? ' selected' : '') + '>' + op + '</option>';
                });
                html += '</select>';
                html += '<input type="text" data-field="ctrl_cond_value" value="' + _escapeAttr((ctrl.condition || {}).value || '') + '" placeholder="比較值" style="width: 80px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';

                // 刪除控制規則
                html += '<button onclick="window._faDecisions.removeControl(\'' + nodeId + '\', ' + vIdx + ', ' + cIdx + ')" style="background: none; border: none; cursor: pointer; color: #dc3545; font-size: 11px;" title="刪除"><i class="fas fa-times"></i></button>';
                html += '</div>';

                // 類型相關欄位
                if (ctrl.type === 'decision_visibility') {
                    var targetIds = (ctrl.target_option_ids || []).join(', ');
                    html += '<div><label style="font-size: 10px; color: #666;">目標選項 ID (逗號分隔)</label>';
                    html += '<input type="text" data-field="ctrl_target_option_ids" value="' + _escapeAttr(targetIds) + '" style="width: 100%; padding: 3px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;" placeholder="opt-xxx, opt-yyy"></div>';
                } else if (ctrl.type === 'field_permission') {
                    html += '<div style="display: flex; gap: 6px;">';
                    html += '<div style="flex: 1;"><label style="font-size: 10px; color: #666;">欄位 Key</label>';
                    html += '<input type="text" data-field="ctrl_field_key" value="' + _escapeAttr(ctrl.field_key || '') + '" style="width: 100%; padding: 3px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;"></div>';
                    html += '<div><label style="font-size: 10px; color: #666;">權限</label>';
                    html += '<select data-field="ctrl_permission" style="padding: 3px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
                    ['readonly', 'editable', 'hidden'].forEach(function (p) {
                        html += '<option value="' + p + '"' + (ctrl.permission === p ? ' selected' : '') + '>' + p + '</option>';
                    });
                    html += '</select></div></div>';
                }

                html += '</div>';  // control end
            });

            html += '<button onclick="window._faDecisions.addControl(\'' + nodeId + '\', ' + vIdx + ')" style="width: 100%; padding: 4px; border: 1px dashed #aaa; border-radius: 4px; background: white; cursor: pointer; font-size: 11px; color: #666;">';
            html += '<i class="fas fa-plus"></i> 新增控制規則</button>';

            html += '</div>';  // var card end
        });

        container.innerHTML = html;

        // 掛上自動存檔
        _ensureAutoSave(container, nodeId, 'inputVars');
    }

    /**
     * 從 DOM 收集 input_variables 資料
     */
    function collectInputVariables() {
        var container = document.getElementById('inputVariablesContainer');
        if (!container) return [];

        var cards = container.querySelectorAll('.input-var-card');
        var result = [];

        cards.forEach(function (card) {
            var varName = card.querySelector('[data-field="var_name"]').value.trim();
            if (!varName) return;

            var controls = [];
            card.querySelectorAll('.input-var-control').forEach(function (ctrlEl) {
                var ctrlType = ctrlEl.querySelector('[data-field="ctrl_type"]').value;
                var ctrlOp = ctrlEl.querySelector('[data-field="ctrl_operator"]').value;
                var ctrlCondValue = ctrlEl.querySelector('[data-field="ctrl_cond_value"]').value.trim();

                var ctrl = {
                    type: ctrlType,
                    condition: { operator: ctrlOp, value: ctrlCondValue }
                };

                if (ctrlType === 'decision_visibility') {
                    var idsStr = (ctrlEl.querySelector('[data-field="ctrl_target_option_ids"]') || {}).value || '';
                    ctrl.target_option_ids = idsStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
                } else if (ctrlType === 'field_permission') {
                    ctrl.field_key = (ctrlEl.querySelector('[data-field="ctrl_field_key"]') || {}).value || '';
                    ctrl.permission = (ctrlEl.querySelector('[data-field="ctrl_permission"]') || {}).value || 'readonly';
                }

                controls.push(ctrl);
            });

            result.push({ var_name: varName, controls: controls });
        });

        return result;
    }

    function addInputVar(nodeId) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var ivs = config.input_variables || [];
        ivs.push({ var_name: '', controls: [] });
        config.input_variables = ivs;
        node.data('config', config);
        renderInputVariables(nodeId, ivs);
    }

    function removeInputVar(nodeId, varIndex) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var ivs = config.input_variables || [];
        ivs.splice(varIndex, 1);
        config.input_variables = ivs;
        node.data('config', config);
        renderInputVariables(nodeId, ivs);
    }

    function addControl(nodeId, varIndex) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var ivs = config.input_variables || [];
        if (!ivs[varIndex]) return;
        if (!ivs[varIndex].controls) ivs[varIndex].controls = [];
        ivs[varIndex].controls.push({
            type: 'decision_visibility',
            condition: { operator: '==', value: '' },
            target_option_ids: []
        });
        config.input_variables = ivs;
        node.data('config', config);
        renderInputVariables(nodeId, ivs);
    }

    function removeControl(nodeId, varIndex, ctrlIndex) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var ivs = config.input_variables || [];
        if (!ivs[varIndex] || !ivs[varIndex].controls) return;
        ivs[varIndex].controls.splice(ctrlIndex, 1);
        config.input_variables = ivs;
        node.data('config', config);
        renderInputVariables(nodeId, ivs);
    }

    // ========================================
    // Helpers
    // ========================================

    function _escapeAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _escapeHtml(str) {
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /**
     * checkbox toggle 時同步寫入 node config，並觸發初始渲染
     */
    function toggleCustomDecisions(nodeId, enabled) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        config.use_custom_decisions = enabled;
        node.data('config', config);

        // 切換面板顯示
        var panel = document.getElementById('customDecisionsPanel');
        if (panel) panel.style.display = enabled ? 'block' : 'none';

        // 啟用時渲染已有的選項
        if (enabled) {
            var outEdges = getOutgoingEdges(nodeId);
            renderDecisionOptions(nodeId, config.decision_options || [], outEdges);
            renderInputVariables(nodeId, config.input_variables || []);
        }
    }

    // ========================================
    // 公開 API
    // ========================================
    window._faDecisions = {
        generateOptionId: generateOptionId,
        getOutgoingEdges: getOutgoingEdges,
        renderDecisionOptions: renderDecisionOptions,
        collectDecisionOptions: collectDecisionOptions,
        addOption: addOption,
        removeOption: removeOption,
        moveOption: moveOption,
        renderInputVariables: renderInputVariables,
        collectInputVariables: collectInputVariables,
        addInputVar: addInputVar,
        removeInputVar: removeInputVar,
        addControl: addControl,
        removeControl: removeControl,
        toggleCustomDecisions: toggleCustomDecisions
    };

})();
