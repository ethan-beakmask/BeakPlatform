/**
 * FormAdapter 自定義決策選項管理
 *
 * 決策組態方塊 + 連連看映射 + input_variables 設定 UI。
 */
(function () {
    'use strict';

    // ========================================
    // 基礎工具
    // ========================================

    function generateOptionId() {
        var s = 'xxxxxxxxxxxx'.replace(/x/g, function () {
            return (Math.random() * 16 | 0).toString(16);
        });
        return 'opt-' + s;
    }

    function getOutgoingEdges(nodeId) {
        if (!window.cy) return [];
        var edges = [];
        window.cy.edges().forEach(function (edge) {
            if (edge.data('source') === nodeId) {
                edges.push({
                    id: edge.id(),
                    label: edge.data('label') || '',
                    target: edge.data('target')
                });
            }
        });
        return edges;
    }

    function getNodeLabel(nodeId) {
        if (!window.cy) return nodeId;
        var node = window.cy.getElementById(nodeId);
        if (node && node.length > 0) {
            return node.data('label') || node.data('type') || nodeId;
        }
        return nodeId;
    }

    function _escapeAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _escapeHtml(str) {
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ========================================
    // 決策組態方塊 (Config Block)
    // ========================================

    var _editingOptionIndex = -1;

    /**
     * 渲染決策組態方塊 — 靜態 HTML 結構，
     * 實際資料由 _loadOptionToConfigBlock 填入。
     */
    function renderDecisionConfigBlock(nodeId, options) {
        var container = document.getElementById('decisionConfigBlock');
        if (!container) return;

        _editingOptionIndex = -1;

        var html = '';

        // Fields panel (hidden until a decision option is clicked)
        html += '<div id="dcFieldsPanel" class="dc-fields-panel" style="display: none;">';

        // Title row
        html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
        html += '<span id="dcTitle" style="font-weight: bold; font-size: 13px; color: #667eea;"></span>';
        html += '<div>';
        html += '<button onclick="window._faDecisions.moveCurrentOption(-1)" style="background: none; border: none; cursor: pointer; color: #666; padding: 2px 4px;" title="上移"><i class="fas fa-arrow-up"></i></button>';
        html += '<button onclick="window._faDecisions.moveCurrentOption(1)" style="background: none; border: none; cursor: pointer; color: #666; padding: 2px 4px;" title="下移"><i class="fas fa-arrow-down"></i></button>';
        html += '<button onclick="window._faDecisions.removeCurrentOption()" style="background: none; border: none; cursor: pointer; color: #dc3545; padding: 2px 4px;" title="刪除"><i class="fas fa-trash"></i></button>';
        html += '</div></div>';

        // Label & Value
        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">';
        html += '<div>';
        html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">顯示名稱</label>';
        html += '<input type="text" id="dc-label" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：核准">';
        html += '</div><div>';
        html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">傳出值</label>';
        html += '<input type="text" id="dc-value" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：approved">';
        html += '</div></div>';

        // Style
        html += '<div style="margin-bottom: 8px;">';
        html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 2px;">按鈕風格</label>';
        html += '<select id="dc-style" style="width: 100%; padding: 5px 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;">';
        var styles = [
            { v: 'primary', l: '主要 (藍)' },
            { v: 'success', l: '成功 (綠)' },
            { v: 'warning', l: '警告 (黃)' },
            { v: 'danger', l: '危險 (紅)' },
            { v: 'default', l: '預設 (灰)' }
        ];
        styles.forEach(function (s) {
            html += '<option value="' + s.v + '">' + s.l + '</option>';
        });
        html += '</select></div>';

        // Visible When
        html += '<div style="border-top: 1px solid #eee; padding-top: 8px;">';
        html += '<label style="font-size: 11px; color: #666; display: block; margin-bottom: 4px;">條件顯示 (可選)</label>';
        html += '<div style="display: grid; grid-template-columns: 1fr auto 1fr; gap: 4px;">';
        html += '<input type="text" id="dc-vw-variable" placeholder="變數名" style="padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
        html += '<select id="dc-vw-operator" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
        var ops = ['==', '!=', '>', '>=', '<', '<=', 'contains', 'not_empty', 'empty'];
        ops.forEach(function (op) {
            html += '<option value="' + op + '">' + op + '</option>';
        });
        html += '</select>';
        html += '<input type="text" id="dc-vw-value" placeholder="比較值" style="padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
        html += '</div></div>';

        html += '</div>'; // dcFieldsPanel

        container.innerHTML = html;

        // Auto-save: config block field changes → write to config
        var panel = document.getElementById('dcFieldsPanel');
        if (panel) {
            var handler = function () {
                _saveConfigBlockToCurrentOption();
                _refreshMappingDisplay();
            };
            panel.addEventListener('input', handler);
            panel.addEventListener('change', handler);
        }
    }

    /**
     * 將指定 option 的資料載入組態方塊
     */
    function _loadOptionToConfigBlock(index) {
        _editingOptionIndex = index;

        var fieldsPanel = document.getElementById('dcFieldsPanel');
        if (!fieldsPanel) return;

        if (index < 0 || !_mappingOptions[index]) {
            fieldsPanel.style.display = 'none';
            return;
        }

        var opt = _mappingOptions[index];
        var color = MAPPING_COLORS[opt.style] || MAPPING_COLORS['default'];

        fieldsPanel.style.display = 'block';
        fieldsPanel.style.borderColor = color;

        var titleEl = document.getElementById('dcTitle');
        if (titleEl) {
            titleEl.textContent = '#' + (index + 1) + ' ' + (opt.label || '(未命名)');
            titleEl.style.color = color;
        }

        document.getElementById('dc-label').value = opt.label || '';
        document.getElementById('dc-value').value = opt.value || '';
        document.getElementById('dc-style').value = opt.style || 'default';

        var vw = opt.visible_when || {};
        document.getElementById('dc-vw-variable').value = vw.variable || '';
        document.getElementById('dc-vw-operator').value = vw.operator || '==';
        document.getElementById('dc-vw-value').value = vw.value || '';
    }

    function _clearConfigBlock() {
        _editingOptionIndex = -1;
        var fieldsPanel = document.getElementById('dcFieldsPanel');
        if (fieldsPanel) fieldsPanel.style.display = 'none';
    }

    /**
     * 從組態方塊 DOM 存回目前編輯中的 option
     */
    function _saveConfigBlockToCurrentOption() {
        if (_editingOptionIndex < 0 || !_mappingNodeId || !window.cy) return;
        var labelEl = document.getElementById('dc-label');
        if (!labelEl) return;

        var node = window.cy.getElementById(_mappingNodeId);
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = config.decision_options || [];
        var opt = options[_editingOptionIndex];
        if (!opt) return;

        opt.label = labelEl.value.trim();
        opt.value = document.getElementById('dc-value').value.trim();
        opt.style = document.getElementById('dc-style').value;

        var vwVar = document.getElementById('dc-vw-variable').value.trim();
        opt.visible_when = vwVar ? {
            variable: vwVar,
            operator: document.getElementById('dc-vw-operator').value,
            value: document.getElementById('dc-vw-value').value.trim()
        } : null;

        config.decision_options = options;
        _mappingOptions = options;
        node.data('config', config);

        // 同步更新組態方塊外觀
        var color = MAPPING_COLORS[opt.style] || MAPPING_COLORS['default'];
        var fieldsPanel = document.getElementById('dcFieldsPanel');
        if (fieldsPanel) fieldsPanel.style.borderColor = color;
        var titleEl = document.getElementById('dcTitle');
        if (titleEl) {
            titleEl.textContent = '#' + (_editingOptionIndex + 1) + ' ' + (opt.label || '(未命名)');
            titleEl.style.color = color;
        }
    }

    // ========================================
    // Edge Mapping 連連看 UI
    // ========================================

    var _mappingConnections = [];
    var _mappingSelected = null;
    var _mappingNodeId = null;
    var _mappingOutEdges = [];
    var _mappingOptions = [];

    var MAPPING_COLORS = {
        'primary': '#667eea',
        'success': '#28a745',
        'warning': '#e0a800',
        'danger': '#dc3545',
        'default': '#6c757d'
    };

    function renderEdgeMapping(nodeId, options, outEdges) {
        var container = document.getElementById('edgeMappingContainer');
        if (!container) return;

        _mappingNodeId = nodeId;
        _mappingOptions = options || [];
        _mappingOutEdges = outEdges || [];
        _mappingSelected = null;

        // 從 decision_options 的 target_edges 建立 connections
        _mappingConnections = [];
        _mappingOptions.forEach(function (opt) {
            (opt.target_edges || []).forEach(function (edgeId) {
                var edgeExists = _mappingOutEdges.some(function (e) { return e.id === edgeId; });
                if (edgeExists) {
                    _mappingConnections.push({ optionId: opt.id, edgeId: edgeId });
                }
            });
        });

        if (_mappingOptions.length === 0 && _mappingOutEdges.length === 0) {
            container.innerHTML = '<div style="color: #999; font-size: 11px; text-align: center; padding: 10px;">新增決策選項並連接出線後，在此配對映射</div>';
            return;
        }

        var html = '';
        html += '<div id="edgeMappingArea" class="edge-mapping-area">';

        // 左欄：決策選項
        html += '<div class="edge-mapping-col">';
        if (_mappingOptions.length === 0) {
            html += '<div style="color: #999; font-size: 11px; padding: 6px 12px;">無決策選項</div>';
        } else {
            _mappingOptions.forEach(function (opt, idx) {
                var color = MAPPING_COLORS[opt.style] || MAPPING_COLORS['default'];
                var hasConn = _mappingConnections.some(function (c) { return c.optionId === opt.id; });
                var isEditing = idx === _editingOptionIndex;
                var label = opt.label || '#' + (idx + 1);
                var cls = 'edge-mapping-node';
                if (hasConn) cls += ' has-conn';
                if (isEditing) cls += ' editing';
                html += '<div class="' + cls + '" ';
                html += 'data-side="left" data-index="' + idx + '" ';
                html += 'style="border-color: ' + color + ';" ';
                html += 'title="' + _escapeAttr(label) + '">';
                html += _escapeHtml(label);
                html += '</div>';
            });
        }
        html += '</div>';

        // SVG
        html += '<svg id="edgeMappingSvg" class="edge-mapping-svg"></svg>';

        // 右欄：出邊目標
        html += '<div class="edge-mapping-col">';
        if (_mappingOutEdges.length === 0) {
            html += '<div style="color: #999; font-size: 11px; padding: 6px 12px;">無出線</div>';
        } else {
            _mappingOutEdges.forEach(function (edge, idx) {
                var targetLabel = getNodeLabel(edge.target);
                var displayText = edge.label || targetLabel;
                var hasConn = _mappingConnections.some(function (c) { return c.edgeId === edge.id; });
                html += '<div class="edge-mapping-node' + (hasConn ? ' has-conn' : '') + '" ';
                html += 'data-side="right" data-index="' + idx + '" ';
                html += 'title="&rarr; ' + _escapeAttr(targetLabel) + '">';
                html += _escapeHtml(displayText);
                html += '</div>';
            });
        }
        html += '</div>';

        html += '</div>';
        html += '<div class="edge-mapping-hint">點選左方再點右方配對，重複點同組合可取消 | 未配對 = REJECTED 終態</div>';

        container.innerHTML = html;

        container.querySelectorAll('.edge-mapping-node').forEach(function (node) {
            node.addEventListener('click', _onMappingNodeClick);
        });

        setTimeout(function () { _drawMappingLines(); }, 0);
    }

    function _onMappingNodeClick(e) {
        var node = e.currentTarget;
        var side = node.dataset.side;
        var index = parseInt(node.dataset.index);

        if (!_mappingSelected) {
            _mappingSelected = { side: side, index: index };
        } else if (_mappingSelected.side === side) {
            if (_mappingSelected.index === index) {
                _mappingSelected = null;
            } else {
                _mappingSelected = { side: side, index: index };
            }
        } else {
            var leftIdx = side === 'left' ? index : _mappingSelected.index;
            var rightIdx = side === 'right' ? index : _mappingSelected.index;
            _toggleMappingConnection(leftIdx, rightIdx);
            _mappingSelected = null;
        }

        // 點選左方 → 載入組態方塊
        if (side === 'left') {
            _saveConfigBlockToCurrentOption();
            _loadOptionToConfigBlock(index);
        }

        _updateMappingNodeStyles();
        _drawMappingLines();
    }

    function _toggleMappingConnection(leftIdx, rightIdx) {
        if (leftIdx >= _mappingOptions.length || rightIdx >= _mappingOutEdges.length) return;

        var optionId = _mappingOptions[leftIdx].id;
        var edgeId = _mappingOutEdges[rightIdx].id;

        var idx = _mappingConnections.findIndex(function (c) {
            return c.optionId === optionId && c.edgeId === edgeId;
        });

        if (idx >= 0) {
            _mappingConnections.splice(idx, 1);
        } else {
            _mappingConnections.push({ optionId: optionId, edgeId: edgeId });
        }

        _saveMappingToConfig();
    }

    function _saveMappingToConfig() {
        if (!_mappingNodeId || !window.cy) return;
        var node = window.cy.getElementById(_mappingNodeId);
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = config.decision_options || [];

        options.forEach(function (opt) {
            opt.target_edges = _mappingConnections
                .filter(function (c) { return c.optionId === opt.id; })
                .map(function (c) { return c.edgeId; });
        });

        config.decision_options = options;
        node.data('config', config);
    }

    function _drawMappingLines() {
        var svg = document.getElementById('edgeMappingSvg');
        var area = document.getElementById('edgeMappingArea');
        if (!svg || !area) return;

        var areaRect = area.getBoundingClientRect();
        svg.innerHTML = '';

        _mappingConnections.forEach(function (conn) {
            var leftIdx = _mappingOptions.findIndex(function (o) { return o.id === conn.optionId; });
            var rightIdx = _mappingOutEdges.findIndex(function (e) { return e.id === conn.edgeId; });
            if (leftIdx < 0 || rightIdx < 0) return;

            var leftNode = area.querySelector('[data-side="left"][data-index="' + leftIdx + '"]');
            var rightNode = area.querySelector('[data-side="right"][data-index="' + rightIdx + '"]');
            if (!leftNode || !rightNode) return;

            var lRect = leftNode.getBoundingClientRect();
            var rRect = rightNode.getBoundingClientRect();

            var x1 = lRect.right - areaRect.left;
            var y1 = lRect.top + lRect.height / 2 - areaRect.top;
            var x2 = rRect.left - areaRect.left;
            var y2 = rRect.top + rRect.height / 2 - areaRect.top;

            var color = MAPPING_COLORS[_mappingOptions[leftIdx].style] || MAPPING_COLORS['default'];

            var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x1);
            line.setAttribute('y1', y1);
            line.setAttribute('x2', x2);
            line.setAttribute('y2', y2);
            line.setAttribute('stroke', color);
            line.setAttribute('stroke-width', '2');
            line.setAttribute('stroke-linecap', 'round');
            svg.appendChild(line);
        });
    }

    function _updateMappingNodeStyles() {
        var area = document.getElementById('edgeMappingArea');
        if (!area) return;

        area.querySelectorAll('.edge-mapping-node').forEach(function (node) {
            var side = node.dataset.side;
            var index = parseInt(node.dataset.index);

            node.classList.remove('selected', 'has-conn', 'editing');

            if (_mappingSelected && _mappingSelected.side === side && _mappingSelected.index === index) {
                node.classList.add('selected');
            }

            if (side === 'left' && index === _editingOptionIndex) {
                node.classList.add('editing');
            }

            var hasConn;
            if (side === 'left') {
                var optId = _mappingOptions[index] ? _mappingOptions[index].id : null;
                hasConn = _mappingConnections.some(function (c) { return c.optionId === optId; });
            } else {
                var edgeId = _mappingOutEdges[index] ? _mappingOutEdges[index].id : null;
                hasConn = _mappingConnections.some(function (c) { return c.edgeId === edgeId; });
            }

            if (hasConn) {
                node.classList.add('has-conn');
            }
        });
    }

    function _refreshMappingDisplay() {
        var area = document.getElementById('edgeMappingArea');
        if (!area) return;

        area.querySelectorAll('.edge-mapping-node[data-side="left"]').forEach(function (node) {
            var idx = parseInt(node.dataset.index);
            if (_mappingOptions[idx]) {
                var color = MAPPING_COLORS[_mappingOptions[idx].style] || MAPPING_COLORS['default'];
                node.style.borderColor = color;
                var label = _mappingOptions[idx].label || '#' + (idx + 1);
                node.textContent = label;
                node.title = label;
            }
        });

        _drawMappingLines();
    }

    // ========================================
    // Option CRUD
    // ========================================

    function addOption(nodeId) {
        _saveConfigBlockToCurrentOption();

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
        renderEdgeMapping(nodeId, options, outEdges);

        // 自動選取新項目進行編輯
        _editingOptionIndex = options.length - 1;
        _loadOptionToConfigBlock(_editingOptionIndex);
        _updateMappingNodeStyles();
    }

    function removeOption(nodeId, optionId) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        var options = config.decision_options || [];
        var removedIndex = options.findIndex(function (o) { return o.id === optionId; });
        options = options.filter(function (o) { return o.id !== optionId; });
        config.decision_options = options;
        node.data('config', config);

        var outEdges = getOutgoingEdges(nodeId);
        renderEdgeMapping(nodeId, options, outEdges);

        if (options.length === 0 || _editingOptionIndex === removedIndex) {
            _clearConfigBlock();
        } else if (_editingOptionIndex > removedIndex) {
            _editingOptionIndex--;
            _loadOptionToConfigBlock(_editingOptionIndex);
        }
        _updateMappingNodeStyles();
    }

    function moveOption(nodeId, index, direction) {
        _saveConfigBlockToCurrentOption();

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
        renderEdgeMapping(nodeId, options, outEdges);

        _editingOptionIndex = newIndex;
        _loadOptionToConfigBlock(newIndex);
        _updateMappingNodeStyles();
    }

    function moveCurrentOption(direction) {
        if (_editingOptionIndex < 0 || !_mappingNodeId) return;
        moveOption(_mappingNodeId, _editingOptionIndex, direction);
    }

    function removeCurrentOption() {
        if (_editingOptionIndex < 0 || !_mappingNodeId) return;
        var opt = _mappingOptions[_editingOptionIndex];
        if (!opt) return;
        removeOption(_mappingNodeId, opt.id);
    }

    /**
     * 收集決策選項（從 config 直接讀取，因即時自動存檔）
     */
    function collectDecisionOptions() {
        _saveConfigBlockToCurrentOption();
        if (!_mappingNodeId || !window.cy) return [];
        var node = window.cy.getElementById(_mappingNodeId);
        if (!node || node.length === 0) return [];
        var config = node.data('config') || {};
        return config.decision_options || [];
    }

    // ========================================
    // Input Variables UI
    // ========================================

    function _ensureAutoSave(container, nodeId, type) {
        var flagKey = '_autoSave_' + type;
        var handlerKey = '_autoSaveHandler_' + type;

        if (container[flagKey] === nodeId) return;

        if (container[handlerKey]) {
            container.removeEventListener('input', container[handlerKey]);
            container.removeEventListener('change', container[handlerKey]);
        }

        container[flagKey] = nodeId;

        var handler = function () {
            var node = window.cy ? window.cy.getElementById(nodeId) : null;
            if (!node || node.length === 0) return;
            var config = node.data('config') || {};

            if (type === 'inputVars') {
                config.input_variables = collectInputVariables();
            }
            node.data('config', config);
        };

        container[handlerKey] = handler;
        container.addEventListener('input', handler);
        container.addEventListener('change', handler);
    }

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

            html += '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">';
            html += '<div style="flex: 1; margin-right: 8px;">';
            html += '<label style="font-size: 11px; color: #666;">變數名稱</label>';
            html += '<input type="text" data-field="var_name" value="' + _escapeAttr(varDef.var_name || '') + '" style="width: 100%; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px;" placeholder="例如：approval_level">';
            html += '</div>';
            html += '<button onclick="window._faDecisions.removeInputVar(\'' + nodeId + '\', ' + vIdx + ')" style="background: none; border: none; cursor: pointer; color: #dc3545; margin-top: 14px;" title="刪除"><i class="fas fa-trash"></i></button>';
            html += '</div>';

            var controls = varDef.controls || [];
            controls.forEach(function (ctrl, cIdx) {
                html += '<div class="input-var-control" data-ctrl-index="' + cIdx + '" style="border: 1px dashed #ccc; border-radius: 4px; padding: 8px; margin-bottom: 6px; background: white;">';

                html += '<div style="display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap;">';
                html += '<select data-field="ctrl_type" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
                html += '<option value="decision_visibility"' + (ctrl.type === 'decision_visibility' ? ' selected' : '') + '>決策顯示</option>';
                html += '<option value="field_permission"' + (ctrl.type === 'field_permission' ? ' selected' : '') + '>欄位權限</option>';
                html += '</select>';

                html += '<select data-field="ctrl_operator" style="padding: 4px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';
                var ops = ['==', '!=', '>', '>=', '<', '<=', 'contains', 'not_empty', 'empty'];
                ops.forEach(function (op) {
                    var selOp = (ctrl.condition || {}).operator || '==';
                    html += '<option value="' + op + '"' + (selOp === op ? ' selected' : '') + '>' + op + '</option>';
                });
                html += '</select>';
                html += '<input type="text" data-field="ctrl_cond_value" value="' + _escapeAttr((ctrl.condition || {}).value || '') + '" placeholder="比較值" style="width: 80px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 11px;">';

                html += '<button onclick="window._faDecisions.removeControl(\'' + nodeId + '\', ' + vIdx + ', ' + cIdx + ')" style="background: none; border: none; cursor: pointer; color: #dc3545; font-size: 11px;" title="刪除"><i class="fas fa-times"></i></button>';
                html += '</div>';

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

                html += '</div>';
            });

            html += '<button onclick="window._faDecisions.addControl(\'' + nodeId + '\', ' + vIdx + ')" style="width: 100%; padding: 4px; border: 1px dashed #aaa; border-radius: 4px; background: white; cursor: pointer; font-size: 11px; color: #666;">';
            html += '<i class="fas fa-plus"></i> 新增控制規則</button>';

            html += '</div>';
        });

        container.innerHTML = html;
        _ensureAutoSave(container, nodeId, 'inputVars');
    }

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
    // Toggle & Public API
    // ========================================

    function toggleCustomDecisions(nodeId, enabled) {
        var node = window.cy ? window.cy.getElementById(nodeId) : null;
        if (!node || node.length === 0) return;

        var config = node.data('config') || {};
        config.use_custom_decisions = enabled;
        node.data('config', config);

        var panel = document.getElementById('customDecisionsPanel');
        if (panel) panel.style.display = enabled ? 'block' : 'none';

        if (enabled) {
            var outEdges = getOutgoingEdges(nodeId);
            renderDecisionConfigBlock(nodeId, config.decision_options || []);
            renderEdgeMapping(nodeId, config.decision_options || [], outEdges);
            renderInputVariables(nodeId, config.input_variables || []);
        }
    }

    window._faDecisions = {
        generateOptionId: generateOptionId,
        getOutgoingEdges: getOutgoingEdges,
        renderDecisionConfigBlock: renderDecisionConfigBlock,
        collectDecisionOptions: collectDecisionOptions,
        addOption: addOption,
        removeOption: removeOption,
        moveOption: moveOption,
        moveCurrentOption: moveCurrentOption,
        removeCurrentOption: removeCurrentOption,
        renderEdgeMapping: renderEdgeMapping,
        renderInputVariables: renderInputVariables,
        collectInputVariables: collectInputVariables,
        addInputVar: addInputVar,
        removeInputVar: removeInputVar,
        addControl: addControl,
        removeControl: removeControl,
        toggleCustomDecisions: toggleCustomDecisions,
        redrawMappingLines: _drawMappingLines
    };

})();
