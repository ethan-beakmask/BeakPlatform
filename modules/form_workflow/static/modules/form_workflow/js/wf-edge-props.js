/**
 * wf-edge-props.js -- 線段屬性控制 (樣式、箭頭、標籤、條件、預設集)
 * 從 workflow-main.js 拆分
 */

        // ==================== 線段屬性控制函數 ====================

        // 更新線段選擇器下拉選單
        function updateEdgeSelector() {
            const selector = document.getElementById('edge-selector');
            selector.innerHTML = '<option value="">-- 點擊線段以選取 --</option>';

            cy.edges().forEach(edge => {
                // 過濾掉正交線段和中繼線段（這些是子元素）
                if (edge.data('edgeType') === 'orthogonal-segment') return;
                if (edge.data('edgeType') === 'relay') return;
                if (edge.data('type') === 'relay') return;

                const option = document.createElement('option');
                option.value = edge.id();
                const sourceLabel = edge.source().data('label') || edge.source().id();
                const targetLabel = edge.target().data('label') || edge.target().id();
                // 正交折線加上標記
                const suffix = edge.data('orthogonalEnabled') ? __(' [正交]') : '';
                option.textContent = `${sourceLabel} → ${targetLabel}${suffix}`;
                selector.appendChild(option);
            });
        }

        // 當線段被點擊時選取（用於屬性控制）
        function selectEdgeForPropertyControl(edge) {
            currentSelectedEdge = edge;
            const selector = document.getElementById('edge-selector');
            selector.value = edge.id();
            loadEdgeProperties(edge);
            document.getElementById('edge-info').classList.add('show');
            document.getElementById('edge-info').textContent =
                `已選取: ${edge.source().data('label')} → ${edge.target().data('label')}`;

            // 隱藏其他面板，顯示線段屬性控制面板
            document.getElementById('nodeSettings').style.display = 'none';
            document.getElementById('edge-editing-panel').style.display = 'none';
            document.getElementById('edge-control-panel').style.display = 'block';
        }

        // 從下拉選單選擇線段
        function onEdgeSelected() {
            const selector = document.getElementById('edge-selector');
            const edgeId = selector.value;

            if (edgeId) {
                const edge = cy.getElementById(edgeId);
                currentSelectedEdge = edge;
                loadEdgeProperties(edge);
                document.getElementById('edge-info').classList.add('show');
                document.getElementById('edge-info').textContent =
                    `已選取: ${edge.source().data('label')} → ${edge.target().data('label')}`;

                // 高亮選中的線段
                cy.edges().removeClass('highlighted');
                edge.addClass('highlighted');

                // 顯示線段屬性控制面板
                document.getElementById('nodeSettings').style.display = 'none';
                document.getElementById('edge-editing-panel').style.display = 'none';
                document.getElementById('edge-control-panel').style.display = 'block';
            } else {
                currentSelectedEdge = null;
                document.getElementById('edge-info').classList.remove('show');
                cy.edges().removeClass('highlighted');
            }
        }

        // 載入線段屬性到控制面板
        function loadEdgeProperties(edge) {
            // 曲線樣式（檢查是否為正交折線或黃點折線）
            let curveStyle = edge.style('curve-style') || 'bezier';
            if (edge.data('orthogonalEnabled')) {
                curveStyle = 'orthogonal';
            } else if (yellowControlPoints.has(edge.id())) {
                curveStyle = 'yellow-control';
            } else if (curveStyle === 'unbundled-bezier') {
                // unbundled-bezier 在 UI 上顯示為 bezier
                curveStyle = 'bezier';
            }
            document.getElementById('curve-style').value = curveStyle;

            // 載入貝茲曲線控制參數
            if (curveStyle === 'bezier') {
                const distances = edge.style('control-point-distances');
                const weights = edge.style('control-point-weights');
                // 解析陣列格式的值
                let distance = 0;
                let weight = 0.5;
                if (distances) {
                    const distStr = String(distances).replace(/[\[\]px]/g, '');
                    distance = parseInt(distStr) || 0;
                }
                if (weights) {
                    const weightStr = String(weights).replace(/[\[\]]/g, '');
                    weight = parseFloat(weightStr) || 0.5;
                }
                document.getElementById('control-distance').value = distance;
                document.getElementById('control-distance-value').textContent = distance;
                document.getElementById('control-weight').value = weight;
                document.getElementById('control-weight-value').textContent = weight.toFixed(1);
            }

            // 線條屬性
            document.getElementById('line-width').value = parseInt(edge.style('width')) || 1;
            document.getElementById('line-width-value').textContent = parseInt(edge.style('width')) || 1;
            document.getElementById('line-color').value = rgbToHex(edge.style('line-color')) || '#e67e22';
            document.getElementById('line-style').value = edge.style('line-style') || 'solid';

            // 箭頭屬性
            const arrowShape = edge.style('target-arrow-shape') || 'triangle';
            document.getElementById('arrow-shape').value = arrowShape;
            const arrowScale = parseFloat(edge.style('arrow-scale')) || 1;
            document.getElementById('arrow-scale').value = arrowScale;
            document.getElementById('arrow-scale-value').textContent = arrowScale.toFixed(1);

            // 條件分支屬性
            document.getElementById('edge-label').value = edge.data('label') || '';

            // 根據是否為客製線段設定預設段落
            const childSegments = getChildSegments(edge);
            const defaultSegment = childSegments.length > 0 ? 3 : 1; // 客製線預設第3段，一般線預設第1段
            document.getElementById('edge-label-segment').value = edge.data('labelSegment') || defaultSegment;
            document.getElementById('edge-label-rotation').value = edge.data('labelRotation') || 'autorotate';
            document.getElementById('edge-condition').value = edge.data('condition') || '';
            document.getElementById('edge-is-default').checked = edge.data('isDefault') === true;

            // 顯示/隱藏相關控制
            toggleCurveControls(curveStyle);
        }

        // RGB 轉 HEX 格式（用於 color input）
        function rgbToHex(color) {
            if (!color) return null;
            // 如果已經是 hex 格式，直接返回
            if (color.startsWith('#')) return color;
            // 解析 rgb(r, g, b) 格式
            const match = color.match(/rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/i);
            if (match) {
                const r = parseInt(match[1]).toString(16).padStart(2, '0');
                const g = parseInt(match[2]).toString(16).padStart(2, '0');
                const b = parseInt(match[3]).toString(16).padStart(2, '0');
                return `#${r}${g}${b}`;
            }
            return color;
        }

        // 切換曲線控制顯示
        function toggleCurveControls(curveStyle) {
            const bezierControls = document.getElementById('bezier-controls');
            const taxiControls = document.getElementById('taxi-controls');
            const orthogonalControls = document.getElementById('orthogonal-controls');

            // 隱藏所有控制面板
            bezierControls.style.display = 'none';
            taxiControls.style.display = 'none';
            if (orthogonalControls) orthogonalControls.style.display = 'none';

            // 顯示對應的控制面板
            if (curveStyle === 'bezier') {
                bezierControls.style.display = 'block';
            } else if (curveStyle === 'taxi') {
                taxiControls.style.display = 'block';
            } else if (curveStyle === 'orthogonal') {
                if (orthogonalControls) orthogonalControls.style.display = 'block';
            }
        }

        // 更新曲線樣式
        function updateEdgeStyle() {
            if (!currentSelectedEdge) return;

            const curveStyle = document.getElementById('curve-style').value;
            const styleNames = {
                'straight': __('直線'),
                'bezier': __('曲線'),
                'taxi': __('直角折線')
            };

            // 特殊處理：yellow-control 創建黃點控制點
            if (curveStyle === 'yellow-control') {
                removeOrthogonalControlPoints(currentSelectedEdge.id());  // 先移除正交折線
                currentSelectedEdge.style('curve-style', 'straight');
                toggleCurveControls('straight');
                createYellowControlPoints(currentSelectedEdge);
                updateStatus(`✓ 已切換為直角折線(黃點)，4個黃點保持水平垂直`);
            }
            // 特殊處理：orthogonal 正交折線
            else if (curveStyle === 'orthogonal') {
                // 先移除其他類型的控制點
                removeTaxiControlPoints(currentSelectedEdge.id());
                removeYellowControlPoints(currentSelectedEdge.id());
                removeOrthogonalControlPoints(currentSelectedEdge.id());

                // 創建正交折線控制點
                createOrthogonalControlPoints(currentSelectedEdge);
                toggleCurveControls('orthogonal');

                // 智慧連動
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, 'orthogonal');
                if (reverseEdgeResult) {
                    // 也為反向邊創建正交控制點
                    const reverseEdge = findReverseEdge(currentSelectedEdge);
                    if (reverseEdge) {
                        removeOrthogonalControlPoints(reverseEdge.id());
                        createOrthogonalControlPoints(reverseEdge);
                    }
                    updateStatus(`✓ 已切換為正交折線（反向邊已同步）`);
                } else {
                    updateStatus(`✓ 已切換為正交折線，點擊線段拖動調整`);
                }
            }
            else {
                // 移除 taxi、黃點、正交折線控制點（如果有）
                removeTaxiControlPoints(currentSelectedEdge.id());
                removeYellowControlPoints(currentSelectedEdge.id());
                removeOrthogonalControlPoints(currentSelectedEdge.id());

                // 曲線使用 unbundled-bezier 以支援手動控制
                if (curveStyle === 'bezier') {
                    const distance = parseInt(document.getElementById('control-distance').value) || 0;
                    const weight = parseFloat(document.getElementById('control-weight').value) || 0.5;
                    currentSelectedEdge.style({
                        'curve-style': 'unbundled-bezier',
                        'control-point-distances': [distance],
                        'control-point-weights': [weight]
                    });
                } else {
                    currentSelectedEdge.style('curve-style', curveStyle);
                }

                toggleCurveControls(curveStyle);

                // 智慧連動：自動同步反向邊的曲線樣式
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, curveStyle);
                if (reverseEdgeResult) {
                    updateStatus(`✓ 曲線樣式已更新為: ${styleNames[curveStyle] || curveStyle}（反向邊已同步）`);
                } else {
                    updateStatus(`✓ 曲線樣式已更新為: ${styleNames[curveStyle] || curveStyle}`);
                }
            }
        }

        // 智慧連動：同步反向邊的曲線樣式
        function syncReverseEdgeCurveStyle(edge, curveStyle) {
            const sourceId = edge.source().id();
            const targetId = edge.target().id();

            // 找反向邊（target → source）
            const reverseEdge = cy.edges().filter(e => {
                return e.source().id() === targetId &&
                       e.target().id() === sourceId &&
                       e.id() !== edge.id() &&
                       (!e.data('edgeType') || e.data('edgeType') !== 'relay');
            });

            if (reverseEdge.length > 0) {
                reverseEdge.forEach(re => {
                    // 曲線使用 unbundled-bezier
                    if (curveStyle === 'bezier') {
                        const distance = parseInt(document.getElementById('control-distance').value) || 0;
                        const weight = parseFloat(document.getElementById('control-weight').value) || 0.5;
                        re.style({
                            'curve-style': 'unbundled-bezier',
                            'control-point-distances': [-distance], // 反向邊使用相反的距離
                            'control-point-weights': [weight]
                        });
                    } else {
                        re.style('curve-style', curveStyle);
                    }
                    console.log(`🔗 自動同步反向邊 ${re.id()} 曲線樣式為: ${curveStyle}`);
                });
                return true;
            }
            return false;
        }

        // 更新貝茲曲線控制
        function updateBezierControls() {
            if (!currentSelectedEdge) return;

            const distance = parseInt(document.getElementById('control-distance').value);
            const weight = parseFloat(document.getElementById('control-weight').value);

            document.getElementById('control-distance-value').textContent = distance;
            document.getElementById('control-weight-value').textContent = weight.toFixed(1);

            // 使用 unbundled-bezier 以支援手動控制點
            // control-point-distances: 控制點與直線的垂直距離
            // control-point-weights: 控制點在邊上的位置 (0=起點, 1=終點)
            currentSelectedEdge.style({
                'curve-style': 'unbundled-bezier',
                'control-point-distances': [distance],
                'control-point-weights': [weight]
            });

            // 同步更新子線段
            const childSegments = getChildSegments(currentSelectedEdge);
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style({
                        'curve-style': 'unbundled-bezier',
                        'control-point-distances': [distance],
                        'control-point-weights': [weight]
                    });
                }
            });

            updateStatus(__('貝茲曲線參數已更新'));
        }

        // 更新計程車曲線控制
        function updateTaxiControls() {
            if (!currentSelectedEdge) return;

            const direction = document.getElementById('taxi-direction').value;
            const turn = parseInt(document.getElementById('taxi-turn').value);

            document.getElementById('taxi-turn-value').textContent = turn;

            currentSelectedEdge.style({
                'taxi-direction': direction,
                'taxi-turn': turn,
                'taxi-turn-min-distance': 10
            });

            updateStatus(__('計程車曲線參數已更新'));
        }

        // 更新線條樣式
        // 獲取線段的所有子線段（包括正交、黃點、taxi、polyline）
        function getChildSegments(edge) {
            const edgeId = edge.id();
            const childEdges = [];

            // 正交折線子線段
            if (orthogonalControlPoints.has(edgeId)) {
                const data = orthogonalControlPoints.get(edgeId);
                if (data && data.relayEdges) {
                    childEdges.push(...data.relayEdges);
                }
            }

            // 黃點折線 - 找到所有 parentEdge 為此邊的線段
            // taxi 折線和 polyline 也是用 parentEdge
            cy.edges(`[parentEdge="${edgeId}"]`).forEach(e => {
                childEdges.push(e);
            });

            return childEdges;
        }

        function updateLineStyle() {
            if (!currentSelectedEdge) return;

            const width = parseInt(document.getElementById('line-width').value);
            const color = document.getElementById('line-color').value;
            const style = document.getElementById('line-style').value;

            document.getElementById('line-width-value').textContent = width;

            const lineStyle = {
                'width': width,
                'line-color': color,
                'line-style': style,
                'target-arrow-color': color
            };

            // 更新原始邊
            currentSelectedEdge.style(lineStyle);

            // 更新所有子線段
            const childSegments = getChildSegments(currentSelectedEdge);
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style(lineStyle);
                }
            });

            updateStatus(__('線條樣式已更新'));
        }

        // 更新箭頭樣式
        function updateArrowStyle() {
            if (!currentSelectedEdge) return;

            const shape = document.getElementById('arrow-shape').value;
            const scale = parseFloat(document.getElementById('arrow-scale').value);

            document.getElementById('arrow-scale-value').textContent = scale.toFixed(1);

            const arrowStyle = {
                'target-arrow-shape': shape,
                'arrow-scale': scale,
                'target-arrow-color': document.getElementById('line-color').value
            };

            // 更新原始邊
            currentSelectedEdge.style(arrowStyle);

            // 更新所有子線段（只有最後一段需要箭頭）
            const childSegments = getChildSegments(currentSelectedEdge);
            if (childSegments.length > 0) {
                // 先將所有子線段的箭頭移除
                childSegments.forEach(seg => {
                    if (seg && seg.length > 0) {
                        seg.style({
                            'target-arrow-shape': 'none',
                            'arrow-scale': scale
                        });
                    }
                });
                // 最後一段加上箭頭
                const lastSeg = childSegments[childSegments.length - 1];
                if (lastSeg && lastSeg.length > 0) {
                    lastSeg.style(arrowStyle);
                }
            }

            updateStatus(__('箭頭樣式已更新'));
        }

        // 更新邊的標籤
        function updateEdgeLabel() {
            if (!currentSelectedEdge) return;

            const label = document.getElementById('edge-label').value;
            const segmentIndex = parseInt(document.getElementById('edge-label-segment').value); // 1-based (人類習慣)
            const rotation = document.getElementById('edge-label-rotation').value;

            // 計算旋轉值
            let textRotation;
            if (rotation === 'autorotate') {
                textRotation = 'autorotate';
            } else {
                textRotation = parseInt(rotation) * Math.PI / 180; // 轉為弧度
            }

            // 儲存標籤設定到原始邊的 data
            currentSelectedEdge.data('label', label);
            currentSelectedEdge.data('labelSegment', segmentIndex);
            currentSelectedEdge.data('labelRotation', rotation);

            // 獲取所有子線段
            const childSegments = getChildSegments(currentSelectedEdge);

            // 先清除所有線段的標籤
            currentSelectedEdge.style('label', '');
            childSegments.forEach(seg => {
                if (seg && seg.length > 0) {
                    seg.style('label', '');
                    seg.data('label', '');
                }
            });

            // 設定標籤樣式
            const labelStyle = {
                'label': label,
                'font-size': '12px',
                'text-rotation': textRotation,
                'text-margin-y': -10,
                'text-background-color': '#ffffff',
                'text-background-opacity': 0.8,
                'text-background-padding': '3px'
            };

            // 根據選擇的段落顯示標籤
            if (childSegments.length === 0) {
                // 一般線段（沒有子線段），顯示在原始邊上
                currentSelectedEdge.style(labelStyle);
            } else {
                // 客製線段，顯示在指定的子線段上
                // segmentIndex 是 1-based，轉換為 0-based
                const targetIndex = segmentIndex - 1;
                if (targetIndex >= 0 && targetIndex < childSegments.length) {
                    const targetSeg = childSegments[targetIndex];
                    if (targetSeg && targetSeg.length > 0) {
                        targetSeg.style(labelStyle);
                        targetSeg.data('label', label);
                    }
                } else {
                    // 如果選擇的段落超出範圍，顯示在中間段
                    const midIndex = Math.floor(childSegments.length / 2);
                    const midSeg = childSegments[midIndex];
                    if (midSeg && midSeg.length > 0) {
                        midSeg.style(labelStyle);
                        midSeg.data('label', label);
                    }
                }
            }

            updateStatus(__('邊標籤已更新'));
        }

        // 更新邊的條件表達式
        function updateEdgeCondition() {
            if (!currentSelectedEdge) return;

            const condition = document.getElementById('edge-condition').value;
            currentSelectedEdge.data('condition', condition);

            updateStatus(__('條件表達式已更新'));
        }

        // 更新邊是否為預設路徑
        function updateEdgeIsDefault() {
            if (!currentSelectedEdge) return;

            const isDefault = document.getElementById('edge-is-default').checked;
            currentSelectedEdge.data('isDefault', isDefault);

            // 如果設為預設，取消其他邊的預設狀態
            if (isDefault) {
                const sourceNode = currentSelectedEdge.source();
                cy.edges().forEach(edge => {
                    if (edge.source().id() === sourceNode.id() && edge.id() !== currentSelectedEdge.id()) {
                        edge.data('isDefault', false);
                    }
                });
            }

            updateStatus(isDefault ? __('已設為預設路徑') : __('已取消預設路徑'));
        }

        // 測試條件表達式
        function testConditionExpression() {
            const condition = document.getElementById('edge-condition').value;

            if (!condition || condition.trim() === '') {
                updateStatus(__('請先輸入條件表達式'), 'warning');
                return;
            }

            // 彈出對話框讓用戶輸入測試變數
            const varsInput = prompt(
                '請輸入測試變數 (JSON 格式):\n\n' +
                '範例: {"age": 25, "status": "approved", "score": 85}\n\n' +
                '按「確定」開始測試:',
                '{"age": 25, "status": "approved"}'
            );

            if (!varsInput) return;

            try {
                // 解析 JSON
                const testVars = JSON.parse(varsInput);

                // 模擬後端的評估邏輯
                const context = {
                    vars: testVars,
                    Math: Math,
                    String: String,
                    Number: Number,
                    Boolean: Boolean,
                    Date: Date,
                    includes: (str, search) => String(str).includes(search),
                    startsWith: (str, search) => String(str).startsWith(search),
                    endsWith: (str, search) => String(str).endsWith(search),
                    length: (arr) => arr?.length || 0,
                    isEmpty: (val) => !val || (Array.isArray(val) && val.length === 0),
                    isNull: (val) => val === null || val === undefined
                };

                const func = new Function(...Object.keys(context), `
                    'use strict';
                    return (${condition});
                `);

                const result = func(...Object.values(context));

                updateStatus(
                    `測試結果: ${result ? '✅ true' : '❌ false'}\n\n` +
                    `條件表達式: ${condition}\n` +
                    `測試變數: ${JSON.stringify(testVars, null, 2)}`,
                    'warning'
                );
            } catch (error) {
                updateStatus(`測試失敗:\n\n${error.message}\n\n請檢查條件表達式是否正確`, 'warning');
            }
        }

        // 套用預設樣式
        function applyPreset(presetName) {
            if (!currentSelectedEdge) {
                updateStatus(__('請先選擇一條線段'), 'warning');
                return;
            }

            const presets = {
                'straight': {
                    'curve-style': 'straight',
                    'width': 1,
                    'line-color': '#95a5a6',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1
                },
                'bezier': {
                    'curve-style': 'bezier',
                    'width': 1,
                    'line-color': '#667eea',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1,
                    'control-point-step-size': 0,
                    'control-point-weight': 0.5
                },
                'polyline': {
                    'curve-style': 'straight',
                    'width': 1,
                    'line-color': '#2196F3',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1
                },
                'taxi': {
                    'curve-style': 'taxi',
                    'width': 1,
                    'line-color': '#34495e',
                    'line-style': 'solid',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 1,
                    'taxi-direction': 'auto',
                    'taxi-turn': 20
                }
            };

            const preset = presets[presetName];
            if (preset) {
                // 分段折線需要提示使用者
                if (presetName === 'polyline') {
                    updateStatus(__('分段折線需要使用 Shift + 點擊線段 來添加中繼點'), 'warning');
                }

                currentSelectedEdge.style(preset);
                loadEdgeProperties(currentSelectedEdge);

                // 智慧連動：同步反向邊的曲線樣式
                const curveStyle = preset['curve-style'];
                const reverseEdgeResult = syncReverseEdgeCurveStyle(currentSelectedEdge, curveStyle);
                if (reverseEdgeResult) {
                    updateStatus(`已套用預設: ${presetName}（反向邊已同步）`);
                } else {
                    updateStatus(`已套用預設: ${presetName}`);
                }
            }
        }

        // 刪除當前選中的線段
        function deleteSelectedEdge() {
            if (!currentSelectedEdge) {
                updateStatus(__('請先選擇一條線段'), 'warning');
                return;
            }

            pushUndoState();
            const edgeId = currentSelectedEdge.id();
            const sourceLabel = currentSelectedEdge.source().data('label') || currentSelectedEdge.source().id();
            const targetLabel = currentSelectedEdge.target().data('label') || currentSelectedEdge.target().id();

            // 移除相關的控制點（正交、黃點、taxi）
            removeOrthogonalControlPoints(edgeId);
            removeYellowControlPoints(edgeId);
            removeTaxiControlPoints(edgeId);

            // 移除所有關聯的中繼點和中繼線段
            cy.nodes(`[type="relay"][parentEdge="${edgeId}"]`).remove();
            cy.edges(`[parentEdge="${edgeId}"]`).remove();

            // 移除原始邊
            currentSelectedEdge.remove();

            // 清除選擇狀態
            currentSelectedEdge = null;
            document.getElementById('edge-selector').value = '';
            document.getElementById('edge-info').classList.remove('show');
            document.getElementById('edge-info').textContent = __('請先選擇一條線段以調整其屬性');

            // 更新線段選擇器
            updateEdgeSelector();

            updateStatus(`已刪除線段: ${sourceLabel} → ${targetLabel}`);
        }

