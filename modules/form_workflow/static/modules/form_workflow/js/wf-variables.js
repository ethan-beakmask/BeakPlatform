/**
 * wf-variables.js -- 表單欄位分頁、變數拖放、變數總覽、欄位取值、變數配置、欄位權限 Modal
 * 從 workflow-main.js 拆分
 */

        // ==================== 表單欄位分頁功能 ====================

        /**
         * 載入當前流程配對的表單列表
         * @param {string} versionType - 版本類型 ('design' 或 'published')
         */
        async function loadMappedForms(versionType = 'design') {
            if (!currentWorkflowId) {
                updateStatus('⚠ 請先載入流程');
                return;
            }

            currentVersionType = versionType;

            // 更新版本切換按鈕樣式
            const btnDesign = document.getElementById('btn-form-design');
            const btnPublished = document.getElementById('btn-form-published');
            if (btnDesign && btnPublished) {
                if (versionType === 'design') {
                    btnDesign.style.background = '#667eea';
                    btnDesign.style.color = 'white';
                    btnPublished.style.background = '#e0e0e0';
                    btnPublished.style.color = '#666';
                } else {
                    btnDesign.style.background = '#e0e0e0';
                    btnDesign.style.color = '#666';
                    btnPublished.style.background = '#667eea';
                    btnPublished.style.color = 'white';
                }
            }

            // 顯示載入中
            const listContainer = document.getElementById('mapped-forms-list');
            if (listContainer) {
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #999; font-size: 11px;">
                        <i class="fas fa-spinner fa-spin"></i> 載入中...
                    </div>
                `;
            }

            try {
                const response = await fetch(`/api/workflows/data/templates/${currentWorkflowId}/mapped-forms?version_type=${versionType}`);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '載入失敗');
                }

                currentMappedForms = result.data.forms || [];
                formFieldsLoaded = true;

                renderMappedFormsList(currentMappedForms);

                // 更新計數
                const countEl = document.getElementById('mapped-forms-count');
                if (countEl) {
                    countEl.textContent = `共 ${currentMappedForms.length} 張表單`;
                }

                // 載入變數映射表
                await loadVariableMapping();

                // 如果只有一張表單，自動選擇並分析
                if (result.data.auto_select && currentMappedForms.length === 1) {
                    selectForm(currentMappedForms[0]);
                }

            } catch (error) {
                console.error('載入配對表單失敗:', error);
                if (listContainer) {
                    listContainer.innerHTML = `
                        <div style="text-align: center; padding: 20px; color: #e74c3c; font-size: 11px;">
                            <i class="fas fa-exclamation-circle"></i> 載入失敗: ${error.message}
                        </div>
                    `;
                }
            }
        }
        window.loadMappedForms = loadMappedForms;

        /**
         * 載入變數映射表
         * 從後端取得新式變數（人類可讀格式）與舊式變數（secure_code 格式）的對照表
         */
        async function loadVariableMapping() {
            if (!currentWorkflowId || currentMappedForms.length === 0) {
                variableMapping = null;
                return;
            }

            try {
                // 取得配對表單的 ID 列表
                const formIds = currentMappedForms.map(f => f.form_id);

                const response = await fetch('/api/workflows/data/variable-mapping', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ form_ids: formIds })
                });

                const result = await response.json();
                if (result.success) {
                    variableMapping = result.data;
                    console.log('📋 變數映射表已載入:', variableMapping);
                } else {
                    console.warn('載入變數映射表失敗:', result.message);
                    variableMapping = null;
                }
            } catch (error) {
                console.error('載入變數映射表失敗:', error);
                variableMapping = null;
            }
        }

        /**
         * 取得欄位的新式變數格式
         * @param {string} secureCode - 表單 secure_code
         * @param {string} fieldKey - 欄位 key
         * @returns {string} 新式變數語法，如 ${表單名稱::欄位標籤}
         */
        function getDisplayVariable(secureCode, fieldKey) {
            if (!variableMapping || !variableMapping.forward) {
                // 沒有映射表時返回舊格式
                return `\${${secureCode}_${fieldKey}}`;
            }

            const internalVar = `${secureCode}_${fieldKey}`;
            const displayVar = variableMapping.forward[internalVar];
            return displayVar ? `\${${displayVar}}` : `\${${internalVar}}`;
        }

        /**
         * 渲染配對表單列表
         * @param {Array} forms - 表單列表
         */
        function renderMappedFormsList(forms) {
            const listContainer = document.getElementById('mapped-forms-list');
            if (!listContainer) return;

            if (forms.length === 0) {
                listContainer.innerHTML = `
                    <div style="text-align: center; padding: 20px; color: #999; font-size: 11px;">
                        <i class="fas fa-info-circle"></i> 此流程尚未配對任何表單
                    </div>
                `;
                return;
            }

            let html = '';
            for (const form of forms) {
                // 使用 form_secure_code 或 form_id 進行比對
                const formIdentifier = form.form_secure_code || form.form_id;
                const isSelected = selectedFormId === formIdentifier;
                const selectedStyle = isSelected ? 'background: #e3f2fd; border-left: 3px solid #667eea;' : 'border-left: 3px solid transparent;';
                const versionBadge = form.source === 'published'
                    ? `<span style="background: #27ae60; color: white; padding: 1px 4px; border-radius: 2px; font-size: 9px; margin-left: 5px;">v${form.publish_version}</span>`
                    : `<span style="background: #f39c12; color: white; padding: 1px 4px; border-radius: 2px; font-size: 9px; margin-left: 5px;">設計中</span>`;

                html += `
                    <div onclick="selectForm(${JSON.stringify(form).replace(/"/g, '&quot;')})"
                         style="padding: 8px 10px; cursor: pointer; border-bottom: 1px solid #eee; ${selectedStyle} transition: all 0.2s;"
                         onmouseover="if(!this.style.background.includes('e3f2fd')) this.style.background='#f5f5f5'"
                         onmouseout="if(!this.style.background.includes('e3f2fd')) this.style.background='transparent'">
                        <div style="font-weight: 500; font-size: 12px; color: #333;">${form.form_name}</div>
                        <div style="font-size: 10px; color: #666; margin-top: 2px;">
                            版本 ${form.form_version} / 修訂 ${form.form_revision}
                            ${versionBadge}
                        </div>
                    </div>
                `;
            }

            listContainer.innerHTML = html;
        }

        /**
         * 選擇表單並載入欄位
         * @param {Object} form - 表單資料
         */
        async function selectForm(form) {
            // 優先使用 form_secure_code
            selectedFormId = form.form_secure_code || form.form_id;
            selectedFormSecureCode = form.form_secure_code || '';

            // 重新渲染列表以更新選中狀態
            renderMappedFormsList(currentMappedForms);

            // 更新標題
            const titleEl = document.getElementById('form-fields-title');
            if (titleEl) {
                titleEl.textContent = ` - ${form.form_name}`;
            }

            // 載入欄位
            await loadFormFields(form);
        }
        window.selectForm = selectForm;

        /**
         * 載入指定表單的欄位
         * @param {Object} form - 表單資料
         */
        async function loadFormFields(form) {
            const tbody = document.getElementById('form-fields-tbody');
            if (!tbody) return;

            // 顯示載入中
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 30px; color: #999;">
                        <i class="fas fa-spinner fa-spin"></i> 分析欄位中...
                    </td>
                </tr>
            `;

            try {
                // 優先使用 form_secure_code，若無則使用 form_id
                const formIdentifier = form.form_secure_code || form.form_id;
                let url = `/api/workflows/data/forms/${formIdentifier}/fields?version_type=${currentVersionType}`;
                if (form.mapping_id) {
                    url += `&mapping_id=${form.mapping_id}`;
                }
                if (form.publish_version) {
                    url += `&publish_version=${form.publish_version}`;
                }

                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '分析失敗');
                }

                currentFormFields = result.data.fields || [];
                renderFormFieldsTable(currentFormFields);

                // 載入已儲存的勾選狀態
                loadFieldReadConfigForCurrentForm();

                // 更新計數
                const countEl = document.getElementById('form-fields-count');
                if (countEl) {
                    countEl.textContent = `共 ${currentFormFields.length} 個欄位`;
                }

            } catch (error) {
                console.error('載入表單欄位失敗:', error);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 30px; color: #e74c3c;">
                            <i class="fas fa-exclamation-circle"></i> 分析失敗: ${error.message}
                        </td>
                    </tr>
                `;
            }
        }

        /**
         * 渲染欄位表格
         * @param {Array} fields - 欄位列表
         */
        function renderFormFieldsTable(fields) {
            const tbody = document.getElementById('form-fields-tbody');
            if (!tbody) return;

            if (fields.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 30px; color: #999;">
                            <i class="fas fa-info-circle"></i> 此表單沒有資料欄位
                        </td>
                    </tr>
                `;
                return;
            }

            // 取得目前此表單已勾選的欄位
            const selectedFields = getSelectedFieldsForCurrentForm();

            // Form.io 類型中文對照
            const typeLabels = {
                'textfield': '文字欄位',
                'textarea': '多行文字',
                'number': '數字',
                'password': '密碼',
                'email': '電子郵件',
                'phoneNumber': '電話號碼',
                'url': '網址',
                'currency': '貨幣',
                'checkbox': '核取方塊',
                'selectboxes': '多選方塊',
                'select': '下拉選單',
                'radio': '單選按鈕',
                'datetime': '日期時間',
                'day': '日期(日)',
                'time': '時間',
                'date': '日期',
                'hidden': '隱藏欄位',
                'signature': '簽名',
                'file': '檔案上傳',
                'tags': '標籤',
                'address': '地址',
                'datagrid': '資料表格',
                'editgrid': '編輯表格',
                'survey': '問卷'
            };

            // 資料類型標籤顏色
            const dataTypeColors = {
                'string': '#3498db',
                'number': '#27ae60',
                'boolean': '#9b59b6',
                'datetime': '#e67e22',
                'date': '#e67e22',
                'array': '#e74c3c',
                'object': '#1abc9c'
            };

            let html = '';
            for (const field of fields) {
                const typeLabel = typeLabels[field.type] || field.type;
                const dataTypeColor = dataTypeColors[field.data_type] || '#666';
                const indentStyle = field.nested_level > 0 ? `padding-left: ${field.nested_level * 15 + 8}px;` : '';
                const nestedIndicator = field.nested_level > 0 ? '<span style="color: #999; margin-right: 3px;">└</span>' : '';

                // 檢查是否已勾選取值
                const isSelected = selectedFields.includes(field.key);

                // 處理預設值/選項
                let defaultOrOptions = '-';
                if (field.options && field.options.length > 0) {
                    const optionsList = field.options.map(o => `${o.label}(${o.value})`).join(', ');
                    defaultOrOptions = `<span title="${optionsList}" style="cursor: help; color: #667eea;">[${field.options.length}個選項]</span>`;
                } else if (field.default_value !== null && field.default_value !== undefined && field.default_value !== '') {
                    defaultOrOptions = `<code style="background: #f5f5f5; padding: 1px 4px; border-radius: 2px; font-size: 10px;">${field.default_value}</code>`;
                }

                // 組合變數語法（v2 引用語法 + 內部變數）
                const displayVar = `\${f.${field.key}}`;
                const internalVar = selectedFormSecureCode ? `\${${selectedFormSecureCode}_${field.key}}` : `\${${field.key}}`;

                html += `
                    <tr class="field-row" data-key="${field.key}" data-label="${field.label}"
                        data-display-var="${displayVar.replace(/"/g, '&quot;')}"
                        data-internal-var="${internalVar.replace(/"/g, '&quot;')}"
                        style="border-bottom: 1px solid #eee;"
                        onmouseover="this.style.background='#f8f9fa'"
                        onmouseout="this.style.background='transparent'">
                        <td style="padding: 6px 8px; text-align: center;">
                            <input type="checkbox" class="field-read-checkbox" data-key="${field.key}"
                                ${isSelected ? 'checked' : ''}
                                onchange="onFieldSelectionChange()"
                                style="cursor: pointer; width: 16px; height: 16px;">
                        </td>
                        <td style="padding: 6px 8px; ${indentStyle} font-size: 11px; color: #333; white-space: nowrap;">
                            ${nestedIndicator}${field.label || field.key}
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px;">
                            <code style="background: #fff3cd; padding: 2px 4px; border-radius: 3px; cursor: grab; color: #856404;"
                                  draggable="true"
                                  ondragstart="handleVarDragStart(event, '${internalVar.replace(/'/g, "\\'")}')"
                                  ondragend="handleVarDragEnd(event)"
                                  onclick="copyVarSyntax(this, '${internalVar.replace(/'/g, "\\'")}')" title="拖拉到設定區或點擊複製">${internalVar}</code>
                        </td>
                        <td style="padding: 6px 8px; font-family: monospace; font-size: 10px;">
                            <code style="background: #d4edda; padding: 2px 4px; border-radius: 3px; cursor: grab; color: #155724;"
                                  draggable="true"
                                  ondragstart="handleVarDragStart(event, '${displayVar.replace(/'/g, "\\'")}')"
                                  ondragend="handleVarDragEnd(event)"
                                  onclick="copyVarSyntax(this, '${displayVar.replace(/'/g, "\\'")}')" title="拖拉到設定區或點擊複製">${displayVar}</code>
                        </td>
                        <td style="padding: 6px 8px; color: #666;">${typeLabel}</td>
                        <td style="padding: 6px 8px;">
                            <span style="background: ${dataTypeColor}; color: white; padding: 1px 5px; border-radius: 2px; font-size: 10px;">${field.data_type}</span>
                        </td>
                        <td style="padding: 6px 8px; text-align: center;">
                            ${field.required ? '<i class="fas fa-check" style="color: #27ae60;"></i>' : '<i class="fas fa-minus" style="color: #ccc;"></i>'}
                        </td>
                        <td style="padding: 6px 8px; font-size: 10px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${defaultOrOptions}
                        </td>
                    </tr>
                `;
            }

            tbody.innerHTML = html;
        }

        /**
         * 篩選表單欄位
         */
        function filterFormFields() {
            const searchInput = document.getElementById('field-search');
            if (!searchInput) return;

            const keyword = searchInput.value.toLowerCase().trim();
            const rows = document.querySelectorAll('#form-fields-tbody .field-row');

            let visibleCount = 0;
            rows.forEach(row => {
                const key = (row.dataset.key || '').toLowerCase();
                const label = (row.dataset.label || '').toLowerCase();

                if (!keyword || key.includes(keyword) || label.includes(keyword)) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            // 更新計數
            const countEl = document.getElementById('form-fields-count');
            if (countEl) {
                if (keyword) {
                    countEl.textContent = `顯示 ${visibleCount} / ${currentFormFields.length} 個欄位`;
                } else {
                    countEl.textContent = `共 ${currentFormFields.length} 個欄位`;
                }
            }
        }

        /**
         * HTML 特殊字元跳脫
         * @param {string} text - 要跳脫的文字
         * @returns {string} 跳脫後的文字
         */
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        /**
         * 複製文字到剪貼簿
         * @param {string} text - 要複製的文字
         */
        async function copyToClipboard(text) {
            try {
                await navigator.clipboard.writeText(text);
                updateStatus(`✅ 已複製: ${text}`);
            } catch (err) {
                console.error('複製失敗:', err);
                // 備用方案：使用 execCommand
                try {
                    const textarea = document.createElement('textarea');
                    textarea.value = text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    updateStatus(`✅ 已複製: ${text}`);
                } catch (e) {
                    updateStatus('❌ 複製失敗');
                }
            }
        }

        /**
         * 複製變數語法到剪貼簿（含視覺反饋）
         * @param {HTMLElement} element - 被點擊的元素
         * @param {string} text - 要複製的文字
         */
        function copyVarSyntax(element, text) {
            // 使用備用方案確保複製成功
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製: ${text}`);

                // 視覺反饋
                if (element) {
                    const originalBg = element.style.background;
                    const originalColor = element.style.color;
                    element.style.background = '#28a745';
                    element.style.color = 'white';
                    setTimeout(() => {
                        element.style.background = originalBg || '';
                        element.style.color = originalColor || '';
                    }, 300);
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製勾選的新式變數到剪貼簿
         */
        function copySelectedDisplayVars() {
            // 取得所有勾選的欄位行
            const checkedRows = document.querySelectorAll('#form-fields-tbody .field-row input.field-read-checkbox:checked');

            if (checkedRows.length === 0) {
                updateStatus('⚠ 請先勾選要複製的欄位');
                return;
            }

            // 收集所有勾選欄位的新式變數
            const displayVars = [];
            checkedRows.forEach(checkbox => {
                const row = checkbox.closest('.field-row');
                if (row && row.dataset.displayVar) {
                    displayVars.push(row.dataset.displayVar);
                }
            });

            if (displayVars.length === 0) {
                updateStatus('⚠ 沒有可複製的變數');
                return;
            }

            // 複製到剪貼簿（用換行分隔）
            const text = displayVars.join('\n');

            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製 ${displayVars.length} 個新式變數到剪貼簿`);
                // 複製成功後自動收合面板
                if (isPanelExpanded) {
                    toggleControlPanel();
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製勾選欄位的舊式變數到剪貼簿
         */
        function copySelectedOldVars() {
            // 取得所有勾選的欄位行
            const checkedRows = document.querySelectorAll('#form-fields-tbody .field-row input.field-read-checkbox:checked');

            if (checkedRows.length === 0) {
                updateStatus('⚠ 請先勾選要複製的欄位');
                return;
            }

            // 收集所有勾選欄位的舊式變數
            const internalVars = [];
            checkedRows.forEach(checkbox => {
                const row = checkbox.closest('.field-row');
                if (row && row.dataset.internalVar) {
                    internalVars.push(row.dataset.internalVar);
                }
            });

            if (internalVars.length === 0) {
                updateStatus('⚠ 沒有可複製的變數');
                return;
            }

            // 複製到剪貼簿（用換行分隔）
            const text = internalVars.join('\n');

            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();

            try {
                document.execCommand('copy');
                updateStatus(`✅ 已複製 ${internalVars.length} 個舊式變數到剪貼簿`);
                // 複製成功後自動收合面板
                if (isPanelExpanded) {
                    toggleControlPanel();
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗');
            }

            document.body.removeChild(textarea);
        }

        /**
         * 複製欄位表格內容
         */
        function copyFieldsTable() {
            if (currentFormFields.length === 0) {
                updateStatus('⚠ 沒有欄位可複製');
                return;
            }

            // 建立 TSV 格式 (Tab-Separated Values)
            let tsv = '欄位代碼\t顯示名稱\t類型\t資料型別\t必填\t路徑\n';
            for (const field of currentFormFields) {
                tsv += `${field.key}\t${field.label}\t${field.type}\t${field.data_type}\t${field.required ? '是' : '否'}\t${field.path}\n`;
            }

            copyToClipboard(tsv);
        }

        // ==================== 變數拖放功能 ====================

        /**
         * 變數拖放開始事件處理
         */
        function handleVarDragStart(e, varText) {
            e.dataTransfer.setData('text/plain', varText);
            e.dataTransfer.effectAllowed = 'copy';
            e.target.style.opacity = '0.5';
        }

        /**
         * 變數拖放結束事件處理
         */
        function handleVarDragEnd(e) {
            e.target.style.opacity = '1';
        }
        window.handleVarDragStart = handleVarDragStart;
        window.handleVarDragEnd = handleVarDragEnd;

        /**
         * 初始化設定區輸入框的拖放接收
         */
        function initDropTargets() {
            // 為 nodeSettings 區域內的所有 input 和 textarea 添加拖放支援
            const nodeSettings = document.getElementById('nodeSettings');
            if (!nodeSettings) return;

            nodeSettings.addEventListener('dragover', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'copy';
                    target.style.background = '#e8f4fd';
                    target.style.borderColor = '#2196f3';
                }
            });

            nodeSettings.addEventListener('dragleave', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    target.style.background = '';
                    target.style.borderColor = '';
                }
            });

            nodeSettings.addEventListener('drop', function(e) {
                const target = e.target;
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    e.preventDefault();
                    const varText = e.dataTransfer.getData('text/plain');
                    if (varText) {
                        // 在游標位置插入變數
                        const start = target.selectionStart || 0;
                        const end = target.selectionEnd || 0;
                        const currentValue = target.value;
                        target.value = currentValue.substring(0, start) + varText + currentValue.substring(end);
                        // 設定游標位置到插入文字之後
                        const newPos = start + varText.length;
                        target.setSelectionRange(newPos, newPos);
                        target.focus();
                        updateStatus(`✅ 已插入變數 ${varText}`);
                    }
                    target.style.background = '';
                    target.style.borderColor = '';
                }
            });
        }

        // 頁面載入後初始化拖放目標
        setTimeout(initDropTargets, 500);

        // ==================== 流程變數總覽功能 ====================

        // 當前篩選狀態
        let _varsCurrentFilter = 'all';

        // 節點類型簡稱 & icon 對照
        const _varNodeTypeLabels = {
            'OpSet': { label: '設定變數', icon: 'fa-calculator' },
            'FormAdapter': { label: '簽核', icon: 'fa-file-signature' },
            'SqlExecutor': { label: 'SQL', icon: 'fa-database' },
            'Branch': { label: '分支', icon: 'fa-code-branch' },
            'Subflow': { label: '子流程', icon: 'fa-project-diagram' },
            'Telegram': { label: 'TG通知', icon: 'fa-paper-plane' },
            'EmailAdapter': { label: '郵件', icon: 'fa-envelope' },
            'OpFieldWrite': { label: '欄位寫入', icon: 'fa-pen' }
        };

        // OpSet 運算元中文對照
        const _opSetLabels = {
            'set': '設定', 'add': '加法', 'subtract': '減法',
            'multiply': '乘法', 'divide': '除法', 'concat': '字串連接',
            'convert': '型別轉換', 'increment': '遞增', 'decrement': '遞減',
            'expr': '表達式'
        };

        /**
         * 從文字中提取 ${xxx} 流程變數引用
         * 排除表單/系統前綴 (f./fi./wi./n./t. 和舊 form.*)
         * 保留 v. 前綴和無前綴裸名
         */
        function _extractVarRefs(text) {
            if (!text) return [];
            const matches = [];
            const regex = /\$\{([^}]+)\}/g;
            const excludePrefixes = ['f.', 'fi.', 'wi.', 'n.', 't.', 'form.'];
            let m;
            while ((m = regex.exec(text)) !== null) {
                const varName = m[1].trim();
                const excluded = excludePrefixes.some(p => varName.startsWith(p));
                if (!excluded) {
                    matches.push(varName);
                }
            }
            return [...new Set(matches)];
        }

        /**
         * 掃描所有節點的變數並更新總覽表
         * @param {string} filter - 'all' | 'set' | 'read'
         */
        function reloadAllVars(filter) {
            filter = filter || _varsCurrentFilter || 'all';
            _varsCurrentFilter = filter;

            // 更新篩選按鈕高亮
            ['all', 'set', 'read'].forEach(f => {
                const btn = document.getElementById('var-filter-' + f);
                if (btn) {
                    if (f === filter) {
                        btn.style.background = '#667eea';
                        btn.style.color = 'white';
                    } else {
                        btn.style.background = '#e0e0e0';
                        btn.style.color = '#666';
                    }
                }
            });

            const tbody = document.getElementById('opset-vars-tbody');
            const countEl = document.getElementById('opset-vars-count');
            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            if (!tbody) return;

            if (selectAllCheckbox) selectAllCheckbox.checked = false;

            if (!window.cy) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 30px; color: #999;"><i class="fas fa-exclamation-circle"></i> 流程圖尚未載入</td></tr>';
                if (countEl) countEl.textContent = '';
                return;
            }

            // 收集所有變數
            const allVars = [];

            cy.nodes().forEach(node => {
                const type = node.data('type') || '';
                const nodeId = node.id();
                const displayName = node.data('display_name') || node.data('label') || nodeId;
                const config = node.data('config') || {};

                switch (type) {
                    case 'OpSet': {
                        const operations = config.operations || [];
                        operations.forEach(op => {
                            if (!op.target_var) return;
                            const opLabel = _opSetLabels[op.operation] || op.operation || 'set';
                            const valDisplay = op.value ? `${opLabel}: ${op.value}` : opLabel;
                            allVars.push({
                                category: 'SET', nodeId, displayName, type,
                                varName: 'v.' + op.target_var, detail: valDisplay
                            });
                        });
                        break;
                    }
                    case 'FormAdapter': {
                        // output_variable → SET
                        if (config.output_variable) {
                            allVars.push({
                                category: 'SET', nodeId, displayName, type,
                                varName: 'v.' + config.output_variable, detail: '決策輸出變數'
                            });
                        }
                        // input_variables → READ
                        const inputVars = config.input_variables || [];
                        inputVars.forEach(iv => {
                            if (!iv.var_name) return;
                            allVars.push({
                                category: 'READ', nodeId, displayName, type,
                                varName: 'v.' + iv.var_name, detail: '輸入變數控制'
                            });
                        });
                        break;
                    }
                    case 'SqlExecutor': {
                        if (config.result_var) {
                            allVars.push({
                                category: 'SET', nodeId, displayName, type,
                                varName: 'v.' + config.result_var, detail: 'SQL 查詢結果'
                            });
                        }
                        break;
                    }
                    case 'Branch': {
                        const rules = config.rules || [];
                        const formPrefixes = ['f.', 'fi.', 'form.'];
                        rules.forEach((rule, ri) => {
                            const conditions = rule.conditions || [];
                            conditions.forEach(cond => {
                                let varName = (cond.variable || '').trim();
                                if (!varName) return;
                                // 去除 ${} 包裹
                                if (varName.startsWith('${') && varName.endsWith('}')) {
                                    varName = varName.slice(2, -1);
                                }
                                // 排除表單類前綴
                                if (formPrefixes.some(p => varName.startsWith(p))) return;
                                // 無前綴裸名加 v. 前綴顯示
                                const displayVar = varName.startsWith('v.') ? varName : 'v.' + varName;
                                const condDesc = `${rule.name || '規則' + (ri+1)}: ${cond.operator || '=='} ${cond.value || ''}`;
                                allVars.push({
                                    category: 'READ', nodeId, displayName, type,
                                    varName: displayVar, detail: condDesc
                                });
                            });
                        });
                        break;
                    }
                    case 'Subflow': {
                        const pm = config.paramMapping || { input: {}, output: {} };
                        // input: parent→child (READ parent var)
                        const inputMap = pm.input || {};
                        Object.keys(inputMap).forEach(parentVar => {
                            allVars.push({
                                category: 'READ', nodeId, displayName, type,
                                varName: 'v.' + parentVar, detail: `輸入→子: ${inputMap[parentVar]}`
                            });
                        });
                        // output: child→parent (SET parent var)
                        const outputMap = pm.output || {};
                        Object.keys(outputMap).forEach(childVar => {
                            allVars.push({
                                category: 'SET', nodeId, displayName, type,
                                varName: 'v.' + outputMap[childVar], detail: `子: ${childVar}→父`
                            });
                        });
                        break;
                    }
                    case 'Telegram':
                    case 'SysTelegram': {
                        const refs = _extractVarRefs(config.message || '');
                        refs.forEach(v => {
                            allVars.push({
                                category: 'READ', nodeId, displayName, type: 'Telegram',
                                varName: v, detail: '訊息引用'
                            });
                        });
                        break;
                    }
                    case 'EmailAdapter':
                    case 'EmailRelay': {
                        const fields = [config.subject, config.body, config.recipient_manual].filter(Boolean).join(' ');
                        const refs2 = _extractVarRefs(fields);
                        refs2.forEach(v => {
                            allVars.push({
                                category: 'READ', nodeId, displayName, type: 'EmailAdapter',
                                varName: v, detail: '郵件引用'
                            });
                        });
                        break;
                    }
                    case 'OpFieldWrite': {
                        const refs3 = _extractVarRefs(config.content || '');
                        refs3.forEach(v => {
                            allVars.push({
                                category: 'READ', nodeId, displayName, type,
                                varName: v, detail: '欄位寫入引用'
                            });
                        });
                        break;
                    }
                }
            });

            // 按 filter 篩選
            const filtered = filter === 'all' ? allVars
                : allVars.filter(v => v.category === filter.toUpperCase());

            if (filtered.length === 0) {
                const emptyMsg = filter === 'all' ? '流程中沒有偵測到變數'
                    : filter === 'set' ? '沒有設定(SET)類型的變數' : '沒有讀取(READ)類型的變數';
                tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 30px; color: #999;"><i class="fas fa-info-circle"></i> ${emptyMsg}</td></tr>`;
                if (countEl) countEl.textContent = `（${allVars.length} 個變數中 0 個符合）`;
                return;
            }

            // 交替色（按節點分組）
            const bgColors = ['#ffffff', '#f7f9fc'];
            let lastNodeId = '', colorIdx = 0;

            let html = '';
            filtered.forEach(v => {
                if (v.nodeId !== lastNodeId) {
                    colorIdx = lastNodeId ? (colorIdx + 1) % 2 : 0;
                    lastNodeId = v.nodeId;
                }
                const bg = bgColors[colorIdx];
                const varText = `\${${v.varName}}`;
                const typeInfo = _varNodeTypeLabels[v.type] || { label: v.type, icon: 'fa-cog' };
                const badgeColor = v.category === 'SET' ? '#e67e22' : '#3498db';
                const badgeLabel = v.category === 'SET' ? 'SET' : 'READ';

                html += `<tr style="border-bottom: 1px solid #eee; background: ${bg}; cursor: pointer;" title="點擊跳轉到節點">
                    <td style="padding: 5px 6px; text-align: center;" onclick="event.stopPropagation();">
                        <input type="checkbox" class="opset-var-checkbox" data-var="${escapeHtml(varText)}">
                    </td>
                    <td style="padding: 5px 6px; text-align: center;" onclick="focusOnNode('${v.nodeId}')">
                        <span style="display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; color: white; background: ${badgeColor};">${badgeLabel}</span>
                    </td>
                    <td style="padding: 5px 6px; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" onclick="focusOnNode('${v.nodeId}')" title="${escapeHtml(v.displayName)}">
                        <span style="color: #667eea; text-decoration: underline; font-size: 11px;">${escapeHtml(v.displayName)}</span>
                    </td>
                    <td style="padding: 5px 6px; text-align: center;" onclick="focusOnNode('${v.nodeId}')">
                        <span title="${escapeHtml(typeInfo.label)}" style="font-size: 10px; color: #666;"><i class="fas ${typeInfo.icon}" style="margin-right: 2px;"></i>${escapeHtml(typeInfo.label)}</span>
                    </td>
                    <td style="padding: 5px 6px;" onclick="event.stopPropagation();">
                        <code style="background: #e8f4fd; padding: 2px 6px; border-radius: 3px; color: #1976d2; cursor: grab; font-size: 11px;"
                              draggable="true"
                              ondragstart="handleVarDragStart(event, '${escapeHtml(varText)}')"
                              ondragend="handleVarDragEnd(event)"
                              onclick="copyVarToClipboard('${escapeHtml(v.varName)}')"
                              title="拖拉到設定區或點擊複製">${escapeHtml(varText)}</code>
                    </td>
                    <td style="padding: 5px 6px; font-size: 10px; color: #666; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" onclick="focusOnNode('${v.nodeId}')" title="${escapeHtml(v.detail)}">
                        ${escapeHtml(v.detail)}
                    </td>
                </tr>`;
            });

            tbody.innerHTML = html;
            const totalInfo = filter === 'all' ? `共 ${filtered.length} 個`
                : `${filtered.length} / ${allVars.length} 個`;
            if (countEl) countEl.textContent = `（${totalInfo}）`;

            const setCount = allVars.filter(v => v.category === 'SET').length;
            const readCount = allVars.filter(v => v.category === 'READ').length;
            updateStatus(`✅ 掃描完成：SET ${setCount} 個，READ ${readCount} 個，共 ${allVars.length} 個變數`);
        }
        window.reloadAllVars = reloadAllVars;
        // 向下相容
        window.reloadOpsetVars = function() { reloadAllVars(); };

        /**
         * 點擊變數名稱複製到剪貼簿
         */
        function copyVarToClipboard(varName) {
            const varText = `\${${varName}}`;
            copyToClipboard(varText);
            updateStatus(`✅ 已複製變數 ${varText} 到剪貼簿`);
        }
        window.copyVarToClipboard = copyVarToClipboard;
        window.copyOpsetVarToClipboard = copyVarToClipboard;

        /**
         * 全選/取消全選變數
         */
        function toggleAllOpsetVarSelection() {
            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            const checkboxes = document.querySelectorAll('.opset-var-checkbox');

            checkboxes.forEach(cb => {
                cb.checked = selectAllCheckbox.checked;
            });
        }
        window.toggleAllOpsetVarSelection = toggleAllOpsetVarSelection;

        /**
         * 複製選中的變數到剪貼簿
         */
        function copySelectedVars() {
            const checkboxes = document.querySelectorAll('.opset-var-checkbox:checked');

            if (checkboxes.length === 0) {
                updateStatus('⚠ 請先勾選要複製的變數');
                return;
            }

            const vars = [];
            checkboxes.forEach(cb => {
                vars.push(cb.getAttribute('data-var'));
            });

            const text = vars.join('\n');
            copyToClipboard(text);
            updateStatus(`✅ 已複製 ${vars.length} 個變數到剪貼簿`);

            const selectAllCheckbox = document.getElementById('opset-var-select-all');
            if (selectAllCheckbox) selectAllCheckbox.checked = false;
            document.querySelectorAll('.opset-var-checkbox').forEach(cb => cb.checked = false);
        }
        window.copySelectedVars = copySelectedVars;
        window.copySelectedOpsetVars = copySelectedVars;

        /**
         * 複製變數表格到剪貼簿（TSV 格式）
         */
        function copyVarsTable() {
            if (!window.cy) {
                updateStatus('⚠ 流程圖尚未載入');
                return;
            }

            // 用當前篩選重新收集
            const rows = document.querySelectorAll('#opset-vars-tbody tr');
            if (!rows.length || (rows.length === 1 && rows[0].querySelector('td[colspan]'))) {
                updateStatus('⚠ 沒有變數可複製');
                return;
            }

            let tsv = '分類\t節點\t類型\t變數\t說明\n';
            rows.forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length < 6) return;
                const category = (cells[1].textContent || '').trim();
                const nodeName = (cells[2].textContent || '').trim();
                const nodeType = (cells[3].textContent || '').trim();
                const varName = (cells[4].textContent || '').trim();
                const detail = (cells[5].textContent || '').trim();
                tsv += `${category}\t${nodeName}\t${nodeType}\t${varName}\t${detail}\n`;
            });

            copyToClipboard(tsv);
            updateStatus('✅ 已複製變數表格到剪貼簿');
        }
        window.copyVarsTable = copyVarsTable;
        window.copyOpsetVarsTable = copyVarsTable;

        /**
         * 跳轉到指定節點並選中
         */
        function focusOnNode(nodeId) {
            if (!window.cy) return;

            const node = cy.getElementById(nodeId);
            if (node.length === 0) {
                updateStatus('⚠ 找不到節點: ' + nodeId);
                return;
            }

            // 取消所有選擇
            cy.elements().unselect();

            // 選中目標節點
            node.select();

            // 將視圖移動到節點
            cy.animate({
                center: { eles: node },
                duration: 300
            });

            // 顯示節點資訊
            showNodeInfo(node);
        }
        window.focusOnNode = focusOnNode;

        // ==================== 欄位取值設定功能 ====================

        // 用於追蹤設定是否已修改
        let fieldReadConfigDirty = false;
        // 防抖動計時器
        let fieldReadSaveDebounceTimer = null;

        /**
         * 從 cytoscape_config 取得目前選中表單的已勾選欄位
         * @returns {Array} 已勾選的欄位 key 陣列
         */
        function getSelectedFieldsForCurrentForm() {
            if (!selectedFormId || !cy) return [];

            // 從 cytoscape 的設定中取得 fieldReadConfig
            const config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${selectedFormId}`;

            if (config[formKey] && Array.isArray(config[formKey].fields)) {
                return config[formKey].fields;
            }

            return [];
        }

        /**
         * 全選/取消全選欄位
         */
        function toggleAllFieldSelection() {
            const selectAll = document.getElementById('field-select-all');
            if (!selectAll) return;

            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = selectAll.checked;
            });

            onFieldSelectionChange();
        }

        /**
         * 當欄位勾選狀態改變時（勾選即自動儲存）
         */
        function onFieldSelectionChange() {
            fieldReadConfigDirty = true;
            updateSelectAllCheckbox();

            // 顯示儲存中狀態
            const statusEl = document.getElementById('field-config-status');
            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;
            if (statusEl) {
                statusEl.innerHTML = `<span style="color: #3498db;"><i class="fas fa-spinner fa-spin"></i> 已選 ${checkedCount} 個欄位 (儲存中...)</span>`;
            }

            // 防抖動：300ms 後自動儲存
            if (fieldReadSaveDebounceTimer) {
                clearTimeout(fieldReadSaveDebounceTimer);
            }
            fieldReadSaveDebounceTimer = setTimeout(() => {
                saveFieldReadConfig();
            }, 300);
        }

        /**
         * 更新全選 checkbox 的狀態
         */
        function updateSelectAllCheckbox() {
            const selectAll = document.getElementById('field-select-all');
            if (!selectAll) return;

            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;

            if (checkedCount === 0) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            } else if (checkedCount === checkboxes.length) {
                selectAll.checked = true;
                selectAll.indeterminate = false;
            } else {
                selectAll.checked = false;
                selectAll.indeterminate = true;
            }
        }

        /**
         * 更新欄位設定狀態顯示
         */
        function updateFieldConfigStatus() {
            const statusEl = document.getElementById('field-config-status');
            if (!statusEl) return;

            const checkedCount = document.querySelectorAll('.field-read-checkbox:checked').length;

            if (fieldReadConfigDirty) {
                statusEl.innerHTML = `<span style="color: #e67e22;"><i class="fas fa-exclamation-circle"></i> 已選 ${checkedCount} 個欄位 (未儲存)</span>`;
            } else {
                statusEl.innerHTML = `<span style="color: #27ae60;"><i class="fas fa-check-circle"></i> 已選 ${checkedCount} 個欄位</span>`;
            }
        }

        /**
         * 取得目前勾選的欄位列表
         * @returns {Array} 勾選的欄位 key 陣列
         */
        function getCheckedFieldKeys() {
            const checkboxes = document.querySelectorAll('.field-read-checkbox:checked');
            return Array.from(checkboxes).map(cb => cb.dataset.key);
        }

        /**
         * 儲存欄位取值設定到 cytoscape_config
         */
        async function saveFieldReadConfig() {
            if (!selectedFormId || !cy) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            // 取得目前勾選的欄位
            const selectedKeys = getCheckedFieldKeys();

            // 取得目前選中的表單資訊
            const currentForm = currentMappedForms.find(f => f.form_id === selectedFormId);
            if (!currentForm) {
                updateStatus('❌ 找不到表單資訊');
                return;
            }

            // 取得或建立 fieldReadConfig
            let config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${selectedFormId}`;

            // 更新此表單的設定
            if (selectedKeys.length > 0) {
                config[formKey] = {
                    formName: currentForm.form_name,
                    formSecureCode: currentForm.form_secure_code,
                    fields: selectedKeys
                };
            } else {
                // 沒有勾選則移除此表單的設定
                delete config[formKey];
            }

            // 儲存回 cytoscape
            cy.data('fieldReadConfig', config);

            // 標記為需要儲存流程
            fieldReadConfigDirty = false;
            updateFieldConfigStatus();

            // 觸發流程儲存
            try {
                await saveWorkflow();
                updateStatus(`✅ 已儲存「${currentForm.form_name}」的欄位取值設定 (${selectedKeys.length} 個欄位)`);
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus('❌ 儲存失敗: ' + error.message);
                fieldReadConfigDirty = true;
                updateFieldConfigStatus();
            }
        }

        /**
         * 載入表單欄位時同步載入已儲存的勾選狀態
         */
        function loadFieldReadConfigForCurrentForm() {
            if (!selectedFormId || !cy) return;

            const selectedFields = getSelectedFieldsForCurrentForm();

            // 更新 checkbox 狀態
            const checkboxes = document.querySelectorAll('.field-read-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = selectedFields.includes(cb.dataset.key);
            });

            // 重置 dirty 狀態
            fieldReadConfigDirty = false;
            updateSelectAllCheckbox();
            updateFieldConfigStatus();
        }

        // ==================== 變數配置功能 ====================

        // 變數配置專用的暫存資料
        let varConfigReadFields = [];   // FieldRead 的欄位清單
        let varConfigWriteFields = [];  // FieldWrite 的欄位清單
        let varConfigReadFormId = null;
        let varConfigWriteFormId = null;
        let varConfigReadFormCode = '';
        let varConfigWriteFormCode = '';

        /**
         * 切換表單欄位子分頁
         * @param {string} subTabName - 子分頁名稱 (fieldlist / varconfig)
         */
        function switchFormFieldsSubTab(subTabName) {
            const subtabFieldlist = document.getElementById('subtab-fieldlist');
            const subtabVarconfig = document.getElementById('subtab-varconfig');
            const contentFieldlist = document.getElementById('subtab-fieldlist-content');
            const contentVarconfig = document.getElementById('subtab-varconfig-content');

            // 重置所有子分頁按鈕
            if (subtabFieldlist) {
                subtabFieldlist.style.background = '#e0e0e0';
                subtabFieldlist.style.color = '#666';
            }
            if (subtabVarconfig) {
                subtabVarconfig.style.background = '#e0e0e0';
                subtabVarconfig.style.color = '#666';
            }

            // 隱藏所有內容
            if (contentFieldlist) contentFieldlist.style.display = 'none';
            if (contentVarconfig) contentVarconfig.style.display = 'none';

            // 啟用選中的子分頁
            if (subTabName === 'fieldlist') {
                if (subtabFieldlist) {
                    subtabFieldlist.style.background = '#667eea';
                    subtabFieldlist.style.color = 'white';
                }
                if (contentFieldlist) contentFieldlist.style.display = 'flex';
            } else if (subTabName === 'varconfig') {
                if (subtabVarconfig) {
                    subtabVarconfig.style.background = '#667eea';
                    subtabVarconfig.style.color = 'white';
                }
                if (contentVarconfig) contentVarconfig.style.display = 'block';
                // 首次切換到變數配置時，載入表單選項
                populateVarConfigFormSelects();
            }
        }

        /**
         * 填充變數配置的表單下拉選單
         */
        function populateVarConfigFormSelects() {
            const readSelect = document.getElementById('varconfig-read-form');
            const writeSelect = document.getElementById('varconfig-write-form');

            if (!readSelect || !writeSelect) return;

            // 確保已載入配對表單
            if (currentMappedForms.length === 0) {
                readSelect.innerHTML = '<option value="">-- 請先載入配對表單 --</option>';
                writeSelect.innerHTML = '<option value="">-- 請先載入配對表單 --</option>';
                return;
            }

            let optionsHtml = '<option value="">-- 請選擇表單 --</option>';
            for (const form of currentMappedForms) {
                optionsHtml += `<option value="${form.form_id}" data-code="${form.form_secure_code}" data-name="${form.form_name}">${form.form_name} (${form.form_secure_code})</option>`;
            }

            readSelect.innerHTML = optionsHtml;
            writeSelect.innerHTML = optionsHtml;
        }

        /**
         * 當變數配置的表單選擇改變時
         * @param {string} mode - 'read' 或 'write'
         */
        async function onVarConfigFormChange(mode) {
            const select = document.getElementById(`varconfig-${mode}-form`);
            const fieldsContainer = document.getElementById(`varconfig-${mode}-fields`);

            if (!select || !fieldsContainer) return;

            const formId = select.value;
            const selectedOption = select.options[select.selectedIndex];
            const formCode = selectedOption.dataset.code || '';
            const formName = selectedOption.dataset.name || '';

            if (!formId) {
                fieldsContainer.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                        請先選擇表單
                    </div>
                `;
                if (mode === 'read') {
                    varConfigReadFields = [];
                    varConfigReadFormId = null;
                    varConfigReadFormCode = '';
                } else {
                    varConfigWriteFields = [];
                    varConfigWriteFormId = null;
                    varConfigWriteFormCode = '';
                }
                updateVarConfigPreview(mode);
                return;
            }

            // 儲存表單資訊
            if (mode === 'read') {
                varConfigReadFormId = parseInt(formId);
                varConfigReadFormCode = formCode;
            } else {
                varConfigWriteFormId = parseInt(formId);
                varConfigWriteFormCode = formCode;
            }

            // 載入欄位
            fieldsContainer.innerHTML = `
                <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                    <i class="fas fa-spinner fa-spin"></i> 載入欄位中...
                </div>
            `;

            try {
                const form = currentMappedForms.find(f => f.form_id === parseInt(formId));
                let url = `/api/workflows/data/forms/${formId}/fields?version_type=${currentVersionType}`;
                if (form && form.mapping_id) {
                    url += `&mapping_id=${form.mapping_id}`;
                }

                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) {
                    throw new Error(result.message || '載入失敗');
                }

                const fields = result.data.fields || [];

                if (mode === 'read') {
                    varConfigReadFields = fields;
                } else {
                    varConfigWriteFields = fields;
                }

                renderVarConfigFields(mode, fields, formCode);

            } catch (error) {
                console.error('載入欄位失敗:', error);
                fieldsContainer.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #e74c3c; font-size: 11px;">
                        <i class="fas fa-exclamation-circle"></i> 載入失敗: ${error.message}
                    </div>
                `;
            }
        }

        /**
         * 渲染變數配置的欄位清單
         * @param {string} mode - 'read' 或 'write'
         * @param {Array} fields - 欄位列表
         * @param {string} formCode - 表單代碼
         */
        function renderVarConfigFields(mode, fields, formCode) {
            const container = document.getElementById(`varconfig-${mode}-fields`);
            if (!container) return;

            if (fields.length === 0) {
                container.innerHTML = `
                    <div style="padding: 15px; text-align: center; color: #999; font-size: 11px;">
                        此表單沒有資料欄位
                    </div>
                `;
                return;
            }

            let html = '';
            for (const field of fields) {
                const varName = `${formCode}_${field.key}`;
                html += `
                    <div style="padding: 6px 10px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 8px;"
                         onmouseover="this.style.background='#f8f9fa'" onmouseout="this.style.background='white'">
                        <input type="checkbox" class="varconfig-${mode}-checkbox" data-key="${field.key}" data-label="${field.label}"
                               onchange="updateVarConfigPreview('${mode}')" style="cursor: pointer;">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 11px; font-weight: 500; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                                ${field.label}
                            </div>
                            <div style="font-size: 10px; color: #667eea; font-family: monospace;">${field.key}</div>
                        </div>
                    </div>
                `;
            }

            container.innerHTML = html;
            updateVarConfigPreview(mode);
        }

        /**
         * 取得目前流程中已設定的所有變數名稱（用於衝突檢測）
         * @returns {Set} 已存在的變數名稱集合
         */
        function getExistingVarNames() {
            const existingVars = new Set();

            if (!cy) return existingVars;

            // 從 fieldReadConfig 取得已設定的變數
            const fieldReadConfig = cy.data('fieldReadConfig') || {};
            for (const formKey in fieldReadConfig) {
                const formConfig = fieldReadConfig[formKey];
                if (formConfig.formSecureCode && formConfig.fields) {
                    for (const fieldKey of formConfig.fields) {
                        // 加入帶前綴和不帶前綴的變數名稱
                        existingVars.add(`${formConfig.formSecureCode}_${fieldKey}`);
                        existingVars.add(fieldKey);
                    }
                }
            }

            return existingVars;
        }

        /**
         * 更新變數配置預覽
         * @param {string} mode - 'read' 或 'write'
         */
        function updateVarConfigPreview(mode) {
            const preview = document.getElementById(`varconfig-${mode}-preview`);
            const countEl = document.getElementById(`varconfig-${mode}-count`);
            const formCode = mode === 'read' ? varConfigReadFormCode : varConfigWriteFormCode;

            if (!preview) return;

            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox:checked`);
            const selectedFields = Array.from(checkboxes).map(cb => ({
                key: cb.dataset.key,
                label: cb.dataset.label
            }));

            // 更新計數
            if (countEl) {
                countEl.textContent = `(${selectedFields.length})`;
            }

            if (selectedFields.length === 0) {
                preview.innerHTML = `
                    <div style="padding: 10px; text-align: center; color: #999;">
                        尚未選擇欄位
                    </div>
                `;
                return;
            }

            // 取得已存在的變數名稱（用於衝突檢測）
            const existingVars = getExistingVarNames();

            let html = '<table style="width: 100%; border-collapse: collapse;">';
            html += '<tr style="background: #f5f5f5;"><th style="padding: 4px 8px; text-align: left; font-size: 10px; border-bottom: 1px solid #ddd;">欄位</th><th style="padding: 4px 8px; text-align: left; font-size: 10px; border-bottom: 1px solid #ddd;">變數名稱</th></tr>';

            for (const field of selectedFields) {
                const varName = `${formCode}_${field.key}`;
                const hasConflict = existingVars.has(varName) || existingVars.has(field.key);
                const conflictIndicator = hasConflict ? '<span style="color: #dc3545; margin-right: 4px;" title="變數已存在，將被覆蓋">●</span>' : '';

                html += `
                    <tr style="border-bottom: 1px solid #f0f0f0;">
                        <td style="padding: 4px 8px; font-size: 10px;">${field.label}</td>
                        <td style="padding: 4px 8px; font-size: 10px; font-family: monospace;">
                            ${conflictIndicator}<code style="background: #e8f4fd; padding: 1px 4px; border-radius: 2px;">${varName}</code>
                        </td>
                    </tr>
                `;
            }
            html += '</table>';

            preview.innerHTML = html;
        }

        /**
         * 全選欄位
         * @param {string} mode - 'read' 或 'write'
         */
        function varConfigSelectAll(mode) {
            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox`);
            checkboxes.forEach(cb => cb.checked = true);
            updateVarConfigPreview(mode);
        }

        /**
         * 清除選擇
         * @param {string} mode - 'read' 或 'write'
         */
        function varConfigDeselectAll(mode) {
            const checkboxes = document.querySelectorAll(`.varconfig-${mode}-checkbox`);
            checkboxes.forEach(cb => cb.checked = false);
            updateVarConfigPreview(mode);
        }

        /**
         * 套用 FieldRead 變數配置
         */
        async function applyVarConfigRead() {
            if (!varConfigReadFormId || !varConfigReadFormCode) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            const checkboxes = document.querySelectorAll('.varconfig-read-checkbox:checked');
            const selectedKeys = Array.from(checkboxes).map(cb => cb.dataset.key);

            if (selectedKeys.length === 0) {
                updateStatus('⚠ 請至少選擇一個欄位');
                return;
            }

            // 取得表單資訊
            const form = currentMappedForms.find(f => f.form_id === varConfigReadFormId);
            if (!form) {
                updateStatus('❌ 找不到表單資訊');
                return;
            }

            // 取得或建立 fieldReadConfig
            let config = cy.data('fieldReadConfig') || {};
            const formKey = `formId_${varConfigReadFormId}`;

            // 更新此表單的設定
            config[formKey] = {
                formName: form.form_name,
                formSecureCode: varConfigReadFormCode,
                fields: selectedKeys
            };

            // 儲存回 cytoscape
            cy.data('fieldReadConfig', config);

            // 觸發流程儲存
            try {
                await saveWorkflow();
                updateStatus(`✅ 已套用 FieldRead 設定：${form.form_name} (${selectedKeys.length} 個欄位)`);

                // 同步更新「欄位查詢」分頁的勾選狀態（如果是同一個表單）
                if (selectedFormId === varConfigReadFormId) {
                    loadFieldReadConfigForCurrentForm();
                }
            } catch (error) {
                console.error('儲存失敗:', error);
                updateStatus('❌ 儲存失敗: ' + error.message);
            }
        }

        /**
         * 複製 FieldWrite 變數語法
         */
        function copyVarConfigWriteSyntax() {
            if (!varConfigWriteFormCode) {
                updateStatus('⚠ 請先選擇表單');
                return;
            }

            const checkboxes = document.querySelectorAll('.varconfig-write-checkbox:checked');

            const selectedFields = Array.from(checkboxes).map(cb => ({
                key: cb.dataset.key,
                label: cb.dataset.label
            }));

            if (selectedFields.length === 0) {
                updateStatus('⚠ 請至少選擇一個欄位');
                return;
            }

            // 產生變數語法
            const syntaxLines = selectedFields.map(field => {
                const varName = `${varConfigWriteFormCode}_${field.key}`;
                return `\${${varName}}`;
            });

            // 選取大於1個時每個後面加換行，只選1個時無換行
            const syntaxText = selectedFields.length > 1
                ? syntaxLines.join('\n')
                : syntaxLines[0];

            // 複製到剪貼簿（使用 fallback 方法）
            copyToClipboard(syntaxText, selectedFields.length);
        }
        window.copyVarConfigWriteSyntax = copyVarConfigWriteSyntax;

        /**
         * 通用複製到剪貼簿函數（含 fallback）
         */
        function copyToClipboard(text, count) {
            // 嘗試使用現代 API
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    updateStatus(`✅ 已複製 ${count} 個變數語法到剪貼簿`);
                }).catch(err => {
                    // 失敗時使用 fallback
                    fallbackCopyToClipboard(text, count);
                });
            } else {
                // 不支援時使用 fallback
                fallbackCopyToClipboard(text, count);
            }
        }

        /**
         * Fallback 複製方法（使用隱藏 textarea）
         */
        function fallbackCopyToClipboard(text, count) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            textarea.style.top = '-9999px';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();

            try {
                const successful = document.execCommand('copy');
                if (successful) {
                    updateStatus(`✅ 已複製 ${count} 個變數語法到剪貼簿`);
                } else {
                    updateStatus('❌ 複製失敗');
                }
            } catch (err) {
                console.error('複製失敗:', err);
                updateStatus('❌ 複製失敗: ' + err.message);
            }

            document.body.removeChild(textarea);
        }

        // =============================================================================
        // 欄位權限設定 Modal
        // =============================================================================

        let fieldPermCurrentNodeId = null;
        let fieldPermFormFields = [];

        /**
         * 開啟欄位權限設定 Modal
         */
        async function openFieldPermissionsModal(nodeId) {
            fieldPermCurrentNodeId = nodeId;
            const node = cy.getElementById(nodeId);
            if (!node || node.length === 0) return;

            // 確保 Modal DOM 存在
            ensureFieldPermissionsModal();

            const modal = document.getElementById('fieldPermModal');
            modal.style.display = 'flex';

            const content = document.getElementById('fieldPermContent');
            content.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;"><i class="fas fa-spinner fa-spin"></i> 載入表單欄位中...</div>';

            // 載入配對表單的欄位
            if (!currentMappedForms || currentMappedForms.length === 0) {
                await loadMappedForms('design');
            }

            if (!currentMappedForms || currentMappedForms.length === 0) {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> 此流程尚未配對任何表單，請先到「配對管理」建立配對。</div>';
                return;
            }

            // 取得第一張配對表單的欄位
            const form = currentMappedForms[0];
            const formIdentifier = form.form_secure_code || form.form_id;
            let url = `/api/workflows/data/forms/${formIdentifier}/fields?version_type=design`;
            if (form.mapping_id) url += `&mapping_id=${form.mapping_id}`;

            try {
                const response = await fetch(url);
                const result = await response.json();

                if (!result.success) throw new Error(result.message || '載入失敗');

                fieldPermFormFields = result.data.fields || [];
                renderFieldPermissionsTable(node, form.form_name);
            } catch (error) {
                content.innerHTML = `<div style="text-align: center; padding: 40px; color: #e74c3c;"><i class="fas fa-exclamation-circle"></i> ${error.message}</div>`;
            }
        }
        window.openFieldPermissionsModal = openFieldPermissionsModal;

        /**
         * 確保 Modal DOM 存在
         */
        function ensureFieldPermissionsModal() {
            if (document.getElementById('fieldPermModal')) return;

            const modal = document.createElement('div');
            modal.id = 'fieldPermModal';
            modal.style.cssText = 'display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:10000; justify-content:center; align-items:center;';
            modal.innerHTML = `
                <div style="background:white; width:90%; max-width:900px; max-height:90vh; border-radius:8px; display:flex; flex-direction:column; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <div style="padding:16px 20px; border-bottom:1px solid #e0e0e0; display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0; font-size:16px;"><i class="fas fa-shield-alt"></i> 欄位權限設定</h3>
                        <button onclick="closeFieldPermissionsModal()" style="background:none; border:none; font-size:20px; cursor:pointer; color:#666;">&times;</button>
                    </div>
                    <div id="fieldPermContent" style="padding:20px; overflow-y:auto; flex:1;"></div>
                    <div style="padding:12px 20px; border-top:1px solid #e0e0e0; display:flex; justify-content:flex-end; gap:8px;">
                        <button onclick="closeFieldPermissionsModal()" style="padding:8px 16px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:4px; cursor:pointer;">取消</button>
                        <button onclick="saveFieldPermissions()" style="padding:8px 16px; background:#667eea; color:white; border:none; border-radius:4px; cursor:pointer;"><i class="fas fa-save"></i> 儲存</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        function closeFieldPermissionsModal() {
            const modal = document.getElementById('fieldPermModal');
            if (modal) modal.style.display = 'none';
            fieldPermCurrentNodeId = null;
        }
        window.closeFieldPermissionsModal = closeFieldPermissionsModal;

        /**
         * 渲染欄位權限表格
         */
        function renderFieldPermissionsTable(node, formName) {
            const content = document.getElementById('fieldPermContent');
            const currentConfig = node.data('config') || {};
            const savedPerms = currentConfig.field_permissions || {};
            const approverPerms = savedPerms.approver || {};
            const readerPerms = savedPerms.reader || {};

            if (fieldPermFormFields.length === 0) {
                content.innerHTML = '<div style="text-align: center; padding: 40px; color: #999;">此表單沒有可設定的欄位</div>';
                return;
            }

            const permOptions = [
                { value: 'readonly', label: '唯讀' },
                { value: 'editable', label: '可修改' },
                { value: 'hidden', label: '隱藏' },
            ];

            function makeSelect(name, currentVal) {
                return `<select data-perm="${name}" style="width:100%; padding:4px 6px; border:1px solid #d1d5db; border-radius:3px; font-size:12px; background:white;">
                    ${permOptions.map(o => `<option value="${o.value}" ${currentVal === o.value ? 'selected' : ''}>${o.label}</option>`).join('')}
                </select>`;
            }

            let rows = '';
            fieldPermFormFields.forEach(field => {
                const aVal = approverPerms[field.key] || 'readonly';
                const rVal = readerPerms[field.key] || 'readonly';
                rows += `<tr style="border-bottom:1px solid #f3f4f6;">
                    <td style="padding:8px 10px; font-size:12px; font-weight:500; white-space:nowrap;">${field.label || field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#666;">${field.key}</td>
                    <td style="padding:8px 10px; font-size:11px; color:#888;">${field.type}</td>
                    <td style="padding:8px 10px;">${makeSelect('approver_' + field.key, aVal)}</td>
                    <td style="padding:8px 10px;">${makeSelect('reader_' + field.key, rVal)}</td>
                </tr>`;
            });

            content.innerHTML = `
                <div style="margin-bottom:12px; font-size:13px; color:#374151;">
                    <strong>表單：</strong>${formName}
                    <span style="margin-left:16px; font-size:12px; color:#6b7280;">共 ${fieldPermFormFields.length} 個欄位</span>
                </div>
                <div style="margin-bottom:12px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button onclick="fpBatchSet('approver', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">簽核者全部唯讀</button>
                    <button onclick="fpBatchSet('approver', 'editable')" style="padding:4px 10px; font-size:11px; background:#dbeafe; border:1px solid #93c5fd; border-radius:3px; cursor:pointer;">簽核者全部可修改</button>
                    <button onclick="fpBatchSet('reader', 'readonly')" style="padding:4px 10px; font-size:11px; background:#f3f4f6; border:1px solid #d1d5db; border-radius:3px; cursor:pointer;">閱讀者全部唯讀</button>
                    <button onclick="fpBatchSet('reader', 'hidden')" style="padding:4px 10px; font-size:11px; background:#fee2e2; border:1px solid #fca5a5; border-radius:3px; cursor:pointer;">閱讀者全部隱藏</button>
                </div>
                <div style="border:1px solid #e5e7eb; border-radius:4px; overflow:hidden;">
                    <table style="width:100%; border-collapse:collapse;">
                        <thead>
                            <tr style="background:#f9fafb;">
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">欄位標籤</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">Key</th>
                                <th style="padding:10px; text-align:left; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap;">類型</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#eff6ff;">簽核者</th>
                                <th style="padding:10px; text-align:center; font-size:12px; border-bottom:1px solid #e5e7eb; white-space:nowrap; min-width:100px; background:#fefce8;">閱讀者</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="margin-top:12px; font-size:11px; color:#6b7280;">
                    <i class="fas fa-info-circle"></i>
                    未設定的欄位預設為「唯讀」。簽核者 = FormAdapter 指定的簽核人，閱讀者 = 其他檢視者。
                </div>
            `;
        }

        /**
         * 批次設定權限
         */
        function fpBatchSet(role, value) {
            const selects = document.querySelectorAll(`select[data-perm^="${role}_"]`);
            selects.forEach(sel => { sel.value = value; });
        }
        window.fpBatchSet = fpBatchSet;

        /**
         * 儲存欄位權限到節點 config
         */
        function saveFieldPermissions() {
            if (!fieldPermCurrentNodeId) return;
            const node = cy.getElementById(fieldPermCurrentNodeId);
            if (!node || node.length === 0) return;

            const approverPerms = {};
            const readerPerms = {};

            fieldPermFormFields.forEach(field => {
                const aSelect = document.querySelector(`select[data-perm="approver_${field.key}"]`);
                const rSelect = document.querySelector(`select[data-perm="reader_${field.key}"]`);
                if (aSelect) approverPerms[field.key] = aSelect.value;
                if (rSelect) readerPerms[field.key] = rSelect.value;
            });

            // 更新 node config
            const currentConfig = node.data('config') || {};
            currentConfig.field_permissions = {
                approver: approverPerms,
                reader: readerPerms,
            };
            node.data('config', currentConfig);

            // 統計
            const editableCount = Object.values(approverPerms).filter(v => v === 'editable').length;
            const hiddenCount = Object.values(approverPerms).filter(v => v === 'hidden').length;
            const readerHiddenCount = Object.values(readerPerms).filter(v => v === 'hidden').length;

            closeFieldPermissionsModal();
            updateStatus(`✅ 欄位權限已儲存 (簽核者: ${editableCount} 可修改, ${hiddenCount} 隱藏 / 閱讀者: ${readerHiddenCount} 隱藏)`, 'success');
        }
        window.saveFieldPermissions = saveFieldPermissions;

