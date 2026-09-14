/**
 * wf-node-field-write.js -- OP_FIELDWRITE 表單寫值節點配置
 * 從 wf-node-configs.js 拆分
 */

        // 載入目標欄位選項（從綁定的表單取得）
        async function loadFieldWriteTargetFields(selectedValue, retryCount = 0) {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 如果 selectedValue 是 ${...} 格式，嘗試提取欄位名稱
            let cleanSelectedValue = selectedValue || '';
            if (cleanSelectedValue.startsWith('${') && cleanSelectedValue.endsWith('}')) {
                // 嘗試提取欄位名，例如 ${FORMCODE_fieldKey} 或 ${form.fieldKey}
                const inner = cleanSelectedValue.slice(2, -1);
                if (inner.startsWith('form.')) {
                    cleanSelectedValue = inner.slice(5);
                } else if (inner.includes('_')) {
                    // ${FORMCODE_fieldKey} 格式，取最後一個 _ 後面的部分
                    cleanSelectedValue = inner.split('_').pop();
                }
            }

            // 如果欄位尚未載入，等待並重試（最多重試 5 次）
            if (currentFormFields.length === 0 && retryCount < 5) {
                select.innerHTML = '<option value="">載入中...</option>';
                setTimeout(() => loadFieldWriteTargetFields(selectedValue, retryCount + 1), 300);
                return;
            }

            try {
                // 從已載入的表單欄位快取取得
                let fields = [];

                // 優先使用目前已載入的表單欄位
                if (currentFormFields && currentFormFields.length > 0) {
                    fields = currentFormFields;
                }

                // 如果沒有快取，嘗試從 triggerFormData 取得
                if (fields.length === 0 && window.triggerFormData && window.triggerFormData.schema) {
                    fields = extractFieldsFromSchema(window.triggerFormData.schema);
                }

                // 如果還是沒有，顯示手動輸入提示
                if (fields.length === 0) {
                    let options = '<option value="">請先選擇表單以載入欄位...</option>';
                    if (cleanSelectedValue) {
                        options = `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue}</option>`;
                    }
                    select.innerHTML = options;
                    return;
                }

                // 建構選項（顯示新式變數格式）
                let options = '<option value="">選擇目標欄位...</option>';

                // 取得表單 secure_code（從 selectedFormSecureCode 或 currentMappedForms）
                let formSecureCode = selectedFormSecureCode || null;
                if (!formSecureCode && currentMappedForms && currentMappedForms.length > 0) {
                    formSecureCode = currentMappedForms[0].form_secure_code;
                }

                fields.forEach(field => {
                    const key = field.key || field.name;
                    const label = field.label || key;
                    const selected = cleanSelectedValue === key ? 'selected' : '';

                    // 嘗試取得新式變數顯示
                    let displayName = label;
                    if (window.variableMapping && window.variableMapping.forward && formSecureCode) {
                        const internalKey = `${formSecureCode}_${key}`;
                        const displayVar = window.variableMapping.forward[internalKey];
                        if (displayVar) {
                            // 顯示新式變數格式（去掉 ${}）
                            displayName = displayVar.replace(/^\$\{/, '').replace(/\}$/, '');
                        }
                    }

                    options += `<option value="${key}" ${selected}>${displayName}</option>`;
                });

                select.innerHTML = options;

                // 如果有舊值且不在選項中，加入手動輸入選項
                if (cleanSelectedValue && !fields.find(f => (f.key || f.name) === cleanSelectedValue)) {
                    select.innerHTML += `<option value="${cleanSelectedValue}" selected>${cleanSelectedValue} (手動輸入)</option>`;
                }

            } catch (error) {
                console.error('載入目標欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
            }
        }
        window.loadFieldWriteTargetFields = loadFieldWriteTargetFields;

        /**
         * 重新載入 OP_FIELDWRITE 的目標欄位選項
         * - 優先使用用戶當前選擇的表單
         * - 如果沒有選擇，使用第一張配對表單
         * - 如果沒有配對表單，顯示提示訊息
         */
        async function reloadFieldWriteTargetFields() {
            const select = document.getElementById('fieldWriteTargetField');
            if (!select) return;

            // 檢查是否有配對表單
            if (!currentMappedForms || currentMappedForms.length === 0) {
                select.innerHTML = '<option value="">需要配對表單</option>';
                updateStatus(__('⚠ 請先在表單欄位分頁配對表單'));
                return;
            }

            // 選擇表單：優先使用已選擇的，否則用第一張
            let targetForm = null;
            if (selectedFormId) {
                targetForm = currentMappedForms.find(f => f.form_id === selectedFormId);
            }
            if (!targetForm) {
                targetForm = currentMappedForms[0];
            }

            // 顯示載入中
            select.innerHTML = '<option value="">載入中...</option>';

            try {
                // 載入表單欄位（這也會更新 currentFormFields）
                await selectForm(targetForm);

                // 現在欄位應該已經載入，重新載入下拉選單
                const currentValue = select.value;
                await loadFieldWriteTargetFields(currentValue);

                updateStatus(`✅ 已載入表單「${targetForm.form_name}」的欄位`);
            } catch (error) {
                console.error('重新載入欄位失敗:', error);
                select.innerHTML = '<option value="">載入失敗</option>';
                updateStatus(__('❌ 載入欄位失敗: ') + error.message);
            }
        }
        window.reloadFieldWriteTargetFields = reloadFieldWriteTargetFields;

        // 從 form.io schema 解析欄位列表
        function extractFieldsFromSchema(schema) {
            const fields = [];
            if (!schema || !schema.components) return fields;

            function extractFromComponents(components) {
                for (const comp of components) {
                    // 跳過容器類型元件（只處理實際欄位）
                    if (comp.type === 'button' || comp.type === 'htmlelement' || comp.type === 'content') {
                        continue;
                    }

                    // 如果有 key，視為欄位
                    if (comp.key && !comp.key.startsWith('panel') && !comp.key.startsWith('columns')) {
                        fields.push({
                            key: comp.key,
                            label: comp.label || comp.key,
                            type: comp.type
                        });
                    }

                    // 遞迴處理巢狀元件
                    if (comp.components) {
                        extractFromComponents(comp.components);
                    }
                    if (comp.columns) {
                        for (const col of comp.columns) {
                            if (col.components) {
                                extractFromComponents(col.components);
                            }
                        }
                    }
                }
            }

            extractFromComponents(schema.components);
            return fields;
        }
        window.extractFieldsFromSchema = extractFieldsFromSchema;

        function applyFieldWriteConfig(nodeId) {
            // 先儲存基本資訊（名稱與描述）
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const targetFieldInput = document.getElementById('fieldWriteTargetField');
            const contentInput = document.getElementById('fieldWriteContent');
            const contentTypeRadio = document.querySelector('input[name="fieldWriteContentType"]:checked');

            if (!targetFieldInput || !contentInput) {
                updateStatus(__('找不到輸入欄位'), 'warning');
                return;
            }

            const targetField = targetFieldInput.value.trim();
            const content = contentInput.value;
            const contentType = contentTypeRadio ? contentTypeRadio.value : 'text';

            // 驗證必填
            if (!targetField) {
                updateStatus(__('請輸入目標欄位 Key'), 'warning');
                targetFieldInput.focus();
                return;
            }

            // 更新節點 config
            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                target_field: targetField,
                content: content,
                content_type: contentType
            };

            node.data('config', updatedConfig);

            updateStatus(`✅ 表單寫值設定已套用：${targetField}`, 'success');

            console.log('OP_FIELDWRITE 節點配置已更新:', {
                nodeId: nodeId,
                target_field: targetField,
                content_type: contentType,
                content_length: content.length,
                config: updatedConfig
            });
        }
        window.applyFieldWriteConfig = applyFieldWriteConfig;
