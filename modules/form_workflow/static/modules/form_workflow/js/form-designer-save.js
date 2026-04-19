/**
 * form-designer-save.js -- CJK 處理、儲存/儲存關閉/新版/放棄
 * 從 form-designer-main.js 拆分
 *
 * 依賴全域: formBuilder, hasUnsavedChanges, currentFormId, currentFormWidth,
 *           currentFormTheme, hasEverSaved (form-designer-main.js),
 *           Toast (form-designer-toast.js), BackgroundManager (form-designer-background.js)
 * 提供全域: getProcessedSchema(), applyPlaceholderAsLabel()
 */

// ----------------------------------------------------------
// CJK 標籤處理：placeholder 含中文時，視為欄位名稱，儲存時交換到 label
// 這是為了繞過 form.io 的 camelCase key 生成無法處理 CJK 的限制
// ----------------------------------------------------------
const CJK_RE = /[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/;

function applyPlaceholderAsLabel(components) {
    (components || []).forEach(comp => {
        if (comp.placeholder && CJK_RE.test(comp.placeholder)) {
            comp.label = comp.placeholder;
            comp.placeholder = '';
        }
        // 遞迴處理容器元件
        if (comp.components) applyPlaceholderAsLabel(comp.components);
        if (comp.columns) comp.columns.forEach(col => applyPlaceholderAsLabel(col.components));
        if (comp.rows) comp.rows.forEach(row => (row || []).forEach(cell => applyPlaceholderAsLabel((cell || {}).components)));
    });
}

function getProcessedSchema() {
    const schema = JSON.parse(JSON.stringify(formBuilder.schema));
    applyPlaceholderAsLabel(schema.components);
    return schema;
}

// ==================== 組裝儲存用 payload 的共用函式 ====================
function _buildSavePayload() {
    const formNameInput = document.getElementById('form-name').value.trim();
    const formCategoryInput = document.getElementById('form-category').value;
    const formDescriptionInput = document.getElementById('form-description').value.trim();
    const schema = getProcessedSchema();
    const builderConfig = {
        formWidth: currentFormWidth,
        formTheme: currentFormTheme !== 'default' ? currentFormTheme : undefined,
        background: BackgroundManager.getConfig(),
        placeholderToLabel: document.getElementById('chk-placeholder-to-label').checked,
        fileUploadEnabled: document.getElementById('chk-file-upload').checked
    };
    return { formNameInput, formCategoryInput, formDescriptionInput, schema, builderConfig };
}

// 解析 HTTP 錯誤訊息
async function _parseErrorResponse(response) {
    let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
    try {
        const errorData = await response.json();
        if (errorData.message) {
            errorMsg = errorData.message;
        }
        if (errorData.errors) {
            errorMsg += '\n' + errorData.errors.map(e => `\u2022 ${e}`).join('\n');
        }
    } catch (e) {
        try {
            const errorText = await response.text();
            if (errorText) errorMsg += ': ' + errorText.substring(0, 200);
        } catch (e2) {}
    }
    return errorMsg;
}

// ==================== 儲存按鈕 ====================
document.getElementById('btn-save').addEventListener('click', async () => {
    if (!formBuilder) return;

    const { formNameInput, formCategoryInput, formDescriptionInput, schema, builderConfig } = _buildSavePayload();
    if (!formNameInput) {
        Toast.warning('請輸入表單檔名');
        return;
    }

    try {
        let response;

        if (currentFormId) {
            // 更新現有表單（背景生成縮圖）
            response = await Promise.race([
                fetch(`/bp/api/forms/data/templates/${currentFormId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: formNameInput,
                        schema: schema,
                        category_secure_code: formCategoryInput,
                        description: formDescriptionInput,
                        builder_config: builderConfig,
                        generate_thumbnail_async: true
                    })
                }),
                new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('請求超時（15秒）')), 15000)
                )
            ]);
        } else {
            // 建立新表單（背景生成縮圖）
            response = await Promise.race([
                fetch('/bp/api/forms/data/templates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: formNameInput,
                        schema: schema,
                        category_secure_code: formCategoryInput,
                        description: formDescriptionInput,
                        builder_config: builderConfig,
                        generate_thumbnail_async: true
                    })
                }),
                new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('請求超時（15秒）')), 15000)
                )
            ]);
        }

        if (!response.ok) {
            throw new Error(await _parseErrorResponse(response));
        }

        const result = await response.json();

        if (result.success) {
            hasUnsavedChanges = false;
            hasEverSaved = true;
            Toast.success('儲存成功');

            // 如果是新增，更新 currentFormId
            if (!currentFormId && result.data && result.data.secure_code) {
                currentFormId = result.data.secure_code;
                console.log('新表單 secure_code:', currentFormId);
            }

            // 更新版本號顯示（含 revision）
            if (result.data) {
                const vb = document.getElementById('form-version-badge');
                if (vb && result.data.version) {
                    vb.textContent = result.data.version + (result.data.revision || '');
                }
            }

            // 縮圖背景生成中，記錄待更新的模板
            if (result.thumbnail_pending && (currentFormId || result.data?.secure_code)) {
                sessionStorage.setItem('thumb_pending', currentFormId || result.data.secure_code);
            }
        } else {
            throw new Error(result.message || '儲存失敗');
        }
    } catch (error) {
        console.error('儲存失敗:', error);
        console.error('Error stack:', error.stack);
        Toast.error('儲存失敗：' + error.message);
    }
});

// ==================== 儲存並離開按鈕 ====================
document.getElementById('btn-save-close').addEventListener('click', async () => {
    if (!formBuilder) return;

    const { formNameInput, formCategoryInput, formDescriptionInput, schema, builderConfig } = _buildSavePayload();
    if (!formNameInput) {
        Toast.warning('請輸入表單檔名');
        return;
    }

    try {
        let response;

        if (currentFormId) {
            // 更新現有表單（背景生成縮圖）
            response = await fetch(`/bp/api/forms/data/templates/${currentFormId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: formNameInput,
                    schema: schema,
                    category_secure_code: formCategoryInput,
                    description: formDescriptionInput,
                    builder_config: builderConfig,
                    generate_thumbnail_async: true  // 背景模式
                })
            });
        } else {
            // 建立新表單（背景生成縮圖）
            response = await fetch('/bp/api/forms/data/templates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: formNameInput,
                    schema: schema,
                    category_secure_code: formCategoryInput,
                    description: formDescriptionInput,
                    builder_config: builderConfig,
                    generate_thumbnail_async: true  // 背景模式
                })
            });
        }

        if (!response.ok) {
            throw new Error(await _parseErrorResponse(response));
        }

        const result = await response.json();

        if (result.success) {
            hasUnsavedChanges = false;

            // 如果是新增，更新 currentFormId（保持邏輯一致）
            if (!currentFormId && result.data && result.data.secure_code) {
                currentFormId = result.data.secure_code;
            }

            // 縮圖背景生成中，記錄待更新的模板
            if (result.thumbnail_pending && (currentFormId || result.data?.secure_code)) {
                sessionStorage.setItem('thumb_pending', currentFormId || result.data.secure_code);
            }

            // 跳轉到表單清單頁面
            window.location.href = '/bp/forms/templates';
        } else {
            throw new Error(result.message || '儲存失敗');
        }
    } catch (error) {
        console.error('儲存失敗:', error);
        Toast.error('儲存失敗：' + error.message);
    }
});

// ==================== 儲存新版按鈕 ====================
document.getElementById('btn-save-new-version').addEventListener('click', async () => {
    if (!formBuilder) return;

    // 必須是編輯模式（已有 formId）
    if (!currentFormId) {
        Toast.warning('請先儲存表單，才能建立新版本');
        return;
    }

    const formNameInput = document.getElementById('form-name').value.trim();
    if (!formNameInput) {
        Toast.warning('請輸入表單檔名');
        return;
    }

    const formCategoryInput = document.getElementById('form-category').value;
    const formDescriptionInput = document.getElementById('form-description').value.trim();

    // 確認儲存新版
    if (!confirm('確定要另存為新版本？\n\n將會複製目前表單，版本號會遞增。')) {
        return;
    }

    try {
        // 先儲存目前的變更
        const schema = getProcessedSchema();
        const builderConfig = {
            formWidth: currentFormWidth,
            formTheme: currentFormTheme !== 'default' ? currentFormTheme : undefined,
            background: BackgroundManager.getConfig(),
            fileUploadEnabled: document.getElementById('chk-file-upload').checked
        };

        await fetch(`/bp/api/forms/data/templates/${currentFormId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: formNameInput,
                schema: schema,
                category_secure_code: formCategoryInput,
                description: formDescriptionInput,
                builder_config: builderConfig,
                generate_thumbnail_async: true
            })
        });

        // 呼叫儲存新版 API
        const response = await fetch(`/bp/api/forms/data/templates/${currentFormId}/save-new-version`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: formNameInput,
                description: formDescriptionInput
            })
        });

        if (!response.ok) {
            // 嘗試解析後端回傳的錯誤訊息
            let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.message) {
                    errorMsg = errorData.message;
                }
            } catch (e) {}
            throw new Error(errorMsg);
        }

        const result = await response.json();

        if (result.success) {
            const newVersion = result.data.version;
            const newSecureCode = result.data.secure_code;
            Toast.success(`已在背景儲存為新版本 (${newVersion})`);

            // 不切換到新版本，保持在當前版本繼續編輯
            alert(`已在背景儲存為新版本 (${newVersion})\n\n新版本編號: ${newSecureCode}\n\n您仍在編輯目前版本，可從表單清單開啟新版本。`);
        } else {
            throw new Error(result.message || '儲存新版本失敗');
        }
    } catch (error) {
        console.error('儲存新版本失敗:', error);
        Toast.error('儲存新版本失敗：' + error.message);
    }
});

// ==================== 放棄按鈕 ====================
// 清理剛建立但從未儲存的空白記錄
async function cleanupAndRedirect() {
    if (!hasEverSaved && currentFormId) {
        try {
            await fetch(`/bp/api/forms/data/templates/${currentFormId}`, {
                method: 'DELETE'
            });
            console.log('已刪除從未儲存的表單記錄:', currentFormId);
        } catch (e) {
            console.error('刪除未儲存表單失敗:', e);
        }
    }
    hasUnsavedChanges = false;
    window.location.href = '/bp/forms/templates';
}

const discardModal = document.getElementById('discard-confirm-modal');
document.getElementById('btn-discard').addEventListener('click', () => {
    if (hasUnsavedChanges) {
        // 顯示確認 modal
        discardModal.style.display = 'flex';
    } else {
        // 沒有未儲存變更，清理並離開
        cleanupAndRedirect();
    }
});

// 放棄 modal - 關閉按鈕
document.getElementById('discard-modal-close').addEventListener('click', () => {
    discardModal.style.display = 'none';
});

// 放棄 modal - 取消按鈕
document.getElementById('discard-cancel').addEventListener('click', () => {
    discardModal.style.display = 'none';
});

// 放棄 modal - 確認放棄按鈕
document.getElementById('discard-confirm').addEventListener('click', () => {
    cleanupAndRedirect();
});
