/**
 * form-designer-init.js -- Builder 初始化、寬度、Schema、分類載入
 * 從 form-designer-main.js 拆分（最後載入）
 *
 * 依賴全域: formBuilder, hasUnsavedChanges, currentFormId, currentFormWidth,
 *           currentFormTheme, hasEverSaved (form-designer-main.js),
 *           Toast (form-designer-toast.js),
 *           DEFAULT_THEME_FOR_NEW_FORM, setFormTheme, getThemeComponentDefaults,
 *           loadFormThemes (form-designer-theme.js),
 *           BackgroundManager (form-designer-background.js)
 * 提供全域: WIDTH_PRESETS, PageManager, formioI18n, buildBuilderGroups,
 *           loadFormData, setFormWidth
 */

// 預設寬度常數
const WIDTH_PRESETS = {
    narrow: 900,   // 窄版
    wide: 1200     // 寬版
};

// 分頁管理物件（已簡化，保留介面相容性）
const PageManager = {
    init() { /* 不再使用分頁功能 */ },
    updatePageInfo() { /* 不再使用分頁功能 */ }
};

// 從 URL 取得參數
const urlParams = new URLSearchParams(window.location.search);
const formId = urlParams.get('id');
const isNewForm = urlParams.get('new') === '1';
const wasJustCreated = urlParams.get('created') === '1';
const formName = urlParams.get('name') || '';
const urlCategory = urlParams.get('category') || '';
const urlDescription = urlParams.get('description') || '';

// 載入分類清單（二層結構）
async function loadCategories() {
    try {
        const response = await fetch('/api/forms/data/categories?context=form_design');
        const result = await response.json();
        if (result.success) {
            const select = document.getElementById('form-category');
            select.innerHTML = '';
            result.data.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat.secure_code;
                option.textContent = cat.display || cat.name;
                select.appendChild(option);
            });
            // 如果 select 還沒被設定值，設定預設值
            if (!select.value && select.options.length > 0) {
                // 新表單用 URL 帶入的 category，否則不覆蓋
                if (urlCategory) {
                    select.value = urlCategory;
                }
            }
        }
    } catch (error) {
        console.error('載入分類失敗:', error);
    }
}

// 頁面載入時載入分類
loadCategories();

// 載入 Form.io 中文翻譯
let formioI18n = {};
async function loadFormioTranslations() {
    try {
        const response = await fetch('/static/vendor/formio-i18n-zh-TW.json');
        if (response.ok) {
            formioI18n = await response.json();
            console.log('Form.io 中文翻譯載入成功，共', Object.keys(formioI18n).length, '個字串');
        }
    } catch (error) {
        console.warn('載入中文翻譯失敗，使用英文介面:', error);
    }
}

// 取得元件預設 builderInfo 的工具函式
const _bi = (type) => Formio.Components.components[type]?.builderInfo || {};

// 設計器權限配置
const _designerConfig = window.__DESIGNER_CONFIG || {};
const _isOrgAdminOrAbove = ['ORG_ADMIN', 'SYSTEM_ADMIN'].indexOf(_designerConfig.userType) >= 0;

// 建構 builderGroups（依主題注入元件預設屬性）
function buildBuilderGroups() {
    const defaults = getThemeComponentDefaults();

    // 將主題預設屬性注入元件的 schema
    // 從 builderInfo.schema 取得基礎 schema（含 type/label/key 等必要欄位），
    // 再疊加主題屬性。不使用 CompClass.schema() 以避免 widget 等複雜屬性
    // 在不完整的 builder context 中引發錯誤
    function _themed(type, overrides) {
        const bi = overrides || _bi(type);
        if (!defaults) return overrides || true;
        const baseSchema = (bi && bi.schema) ? bi.schema : { type };
        return { ...bi, schema: { ...baseSchema, ...defaults } };
    }

    const groups = {
        basic: {
            title: '基本元件',
            weight: 0,
            default: true,
            components: {
                textfield: _themed('textfield'),
                textarea: _themed('textarea'),
                number: _themed('number'),
                email: _themed('email'),
                phoneNumber: _themed('phoneNumber'),
                checkbox: _themed('checkbox'),
                selectboxes: _themed('selectboxes'),
                select: _themed('select'),
                radio: _themed('radio', { ..._bi('radio'), icon: 'far fa-circle-dot' }),
                button: true
            }
        },
        advanced: {
            title: '進階元件',
            weight: 10,
            components: {
                file: _themed('file', { ..._bi('file'), schema: { ..._bi('file').schema, storage: 'bkfile' } }),
                datetime: _themed('datetime'),
                day: _themed('day'),
                time: _themed('time', { ..._bi('time'), icon: 'far fa-clock' }),
                currency: _themed('currency'),
                survey: _themed('survey'),
                // 排除已移至 basic 群組的元件，防止 defaultsDeep 從 Form.io
                // 預設 advanced 群組補回未含主題的 schema 而覆蓋我們的設定
                email: false,
                phoneNumber: false
            }
        },
        layout: {
            title: '版面配置',
            weight: 20,
            components: {
                htmlelement: true,
                content: true,
                columns: true,
                fieldset: true,
                panel: true,
                table: true,
                tabs: { ..._bi('tabs'), icon: 'fas fa-folder' },
                well: { ..._bi('well'), icon: 'far fa-square' }
            }
        }
    };

    // 自行開發元件：僅企業管理員以上可見
    if (_isOrgAdminOrAbove) {
        groups.custom = {
            title: '平台元件',
            weight: 5,
            components: {
                formTitle: true,
                userPicker: true
            }
        };
    }

    return groups;
}

// options 延後在初始化時組裝（需等主題載入）
let builderOptions = null;

// 載入表單資料
async function loadFormData() {
    if (formId) {
        // 編輯模式 - 載入現有表單
        try {
            console.log('載入表單 ID:', formId);
            const response = await fetch(`/api/forms/data/templates/${formId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const result = await response.json();
            console.log('表單資料載入成功:', result);

            const formData = result.data;

            // 處理權限控制
            if (formData._permissions) {
                const perms = formData._permissions;
                console.log('權限資訊:', perms);

                if (!perms.can_edit) {
                    // 沒有編輯權限：禁用儲存相關按鈕並顯示唯讀提示
                    const saveButtons = ['btn-save', 'btn-save-close', 'btn-save-new-version'];
                    saveButtons.forEach(id => {
                        const btn = document.getElementById(id);
                        if (btn) {
                            btn.disabled = true;
                            btn.classList.add('disabled');
                            btn.title = '您沒有編輯權限';
                        }
                    });

                    // 在工具列上方顯示唯讀模式提示
                    const toolbar = document.querySelector('.designer-toolbar');
                    if (toolbar) {
                        const warning = document.createElement('div');
                        warning.className = 'alert alert-warning mb-2 py-2';
                        warning.innerHTML = '<i class="fas fa-lock me-2"></i><strong>唯讀模式</strong> - 您只有檢視權限，無法編輯或儲存此表單。';
                        toolbar.insertBefore(warning, toolbar.firstChild);
                    }

                    console.log('唯讀模式已啟用');
                }
            }

            // 設定檔名、分類、描述
            document.getElementById('form-name').value = formData.name;
            document.getElementById('form-category').value = formData.category_secure_code || '';
            document.getElementById('form-description').value = formData.description || '';
            currentFormId = formData.secure_code;
            // 只有非剛建立的才標記為已儲存
            if (!wasJustCreated) {
                hasEverSaved = true;
            }

            // 顯示版本號（含 revision）
            const versionBadge = document.getElementById('form-version-badge');
            if (versionBadge && formData.version) {
                versionBadge.textContent = formData.version + (formData.revision || '');
                versionBadge.style.display = 'inline-block';
            }

            // 顯示建立者/最後編輯者
            const authorInfo = document.getElementById('form-author-info');
            if (authorInfo) {
                const parts = [];
                if (formData.created_by_name) {
                    parts.push('建立: ' + formData.created_by_name);
                }
                if (formData.updated_by_name) {
                    let updatedText = '編輯: ' + formData.updated_by_name;
                    if (formData.updated_at) {
                        updatedText += ' (' + BkTime.format(formData.updated_at, 'short') + ')';
                    }
                    parts.push(updatedText);
                }
                if (parts.length > 0) {
                    authorInfo.textContent = parts.join(' | ');
                    authorInfo.style.display = 'inline';
                }
            }

            // 恢復 builder_config（表單寬度等）
            if (formData.builder_config) {
                // 恢復表單寬度設定
                setTimeout(() => {
                    if (formData.builder_config.formWidth !== undefined) {
                        // 新格式：直接使用 formWidth
                        setFormWidth(formData.builder_config.formWidth);
                    } else if (formData.builder_config.pageMode) {
                        // 舊格式相容：pageMode 轉換為 formWidth
                        const modeToWidth = {
                            'portrait': WIDTH_PRESETS.narrow,
                            'landscape': WIDTH_PRESETS.wide,
                            'infinite': null
                        };
                        setFormWidth(modeToWidth[formData.builder_config.pageMode] || null);
                    } else if (wasJustCreated) {
                        // 新建表單預設寬版
                        setFormWidth(WIDTH_PRESETS.wide);
                    }
                }, 100);
                // 恢復底圖設定
                if (formData.builder_config.background) {
                    setTimeout(() => {
                        BackgroundManager.setConfig(formData.builder_config.background);
                    }, 500);
                }
                // 恢復 placeholder->label 開關
                if (formData.builder_config.placeholderToLabel) {
                    document.getElementById('chk-placeholder-to-label').checked = true;
                }
                // 恢復附件上傳開關（預設啟用，僅明確 false 才關閉）
                const chkFile = document.getElementById('chk-file-upload');
                if (chkFile) {
                    chkFile.checked = formData.builder_config.fileUploadEnabled !== false;
                }
                // 恢復風格主題（剛建立的表單若無已儲存主題，套用新表單預設主題）
                const savedTheme = formData.builder_config.formTheme;
                setFormTheme(savedTheme || (wasJustCreated ? DEFAULT_THEME_FOR_NEW_FORM : 'default'));
            } else if (wasJustCreated) {
                // 無 builder_config 的新建表單，套用新表單預設值
                setFormTheme(DEFAULT_THEME_FOR_NEW_FORM);
                setTimeout(() => setFormWidth(WIDTH_PRESETS.wide), 100);
            }

            // 返回 schema
            return formData.schema || { components: [] };
        } catch (error) {
            console.error('載入表單失敗:', error);
            Toast.error('載入表單失敗：' + error.message);
            return { components: [] };
        }
    } else if (isNewForm) {
        // 新增模式 - 使用 URL 預設值，套用預設主題
        console.log('新增表單模式');
        document.getElementById('form-name').value = formName;
        document.getElementById('form-category').value = urlCategory;
        document.getElementById('form-description').value = urlDescription;
        setFormTheme(DEFAULT_THEME_FOR_NEW_FORM);
        const titleText = formName || '請設定表單名稱';
        return { components: [
            { type: 'formTitle', tag: 'h3', attrs: [{ attr: 'style', value: 'text-align:center; margin:0 0 0.5rem 0;' }], content: titleText, key: 'formTitle', input: false, tableView: false }
        ] };
    } else {
        // 無參數 - 新增空白表單，套用預設主題
        console.log('無參數，建立空白表單');
        document.getElementById('form-name').value = '新表單';
        setFormTheme(DEFAULT_THEME_FOR_NEW_FORM);
        return { components: [
            { type: 'formTitle', tag: 'h3', attrs: [{ attr: 'style', value: 'text-align:center; margin:0 0 0.5rem 0;' }], content: '請設定表單名稱', key: 'formTitle', input: false, tableView: false }
        ] };
    }
}

// 初始化 Builder (先載入翻譯 + 主題)
Promise.all([loadFormioTranslations(), loadFormThemes()]).then(() => {
    return loadFormData();
}).then(initialSchema => {
    // loadFormData 已設定 currentFormTheme，此時建構 builder options 才能正確注入主題預設屬性
    builderOptions = {
        language: 'zh-TW',
        noDefaultSubmitButton: true,
        i18n: { 'zh-TW': formioI18n },
        builder: buildBuilderGroups()
    };
    Formio.builder(document.getElementById('builder'), initialSchema, builderOptions)
        .then(builder => {
            formBuilder = builder;
            console.log('Form.io Builder 初始化成功');

            // placeholder->label 自動填入（可由 checkbox 開關）
            // 非拉丁文字（CJK、日韓、泰文等）觸發
            // 支援 || 分隔符：前段->label，後段->placeholder
            const NON_LATIN_RE = /[^\u0000-\u024F\u1E00-\u1EFF]/;
            builder.on('saveComponent', (component) => {
                const chk = document.getElementById('chk-placeholder-to-label');
                if (!chk || !chk.checked) return;
                if (!component.placeholder || !NON_LATIN_RE.test(component.placeholder)) return;

                const sepIdx = component.placeholder.indexOf('||');
                if (sepIdx === -1) {
                    // 沒有 || — 整段複製到 label，清空 placeholder
                    component.label = component.placeholder;
                    component.placeholder = '';
                } else {
                    // 有 || — 前段->label，後段->placeholder（只處理第一組 ||）
                    component.label = component.placeholder.substring(0, sepIdx);
                    component.placeholder = component.placeholder.substring(sepIdx + 2);
                }
                setTimeout(() => builder.redraw(), 50);
            });

            // 新拖入元件套用主題預設屬性
            // Form.io v3 的 builder 對部分元件（如 phoneNumber、email）不會採用
            // builder group 定義中的 schema，改用 addComponent 事件可靠地注入
            builder.on('addComponent', (component) => {
                const defaults = getThemeComponentDefaults();
                if (!defaults || component.input === false) return;
                const props = ['labelPosition', 'labelWidth', 'labelMargin'];
                props.forEach(prop => {
                    if (defaults[prop] !== undefined) {
                        component[prop] = defaults[prop];
                    }
                });
            });

            // 監聽變更
            builder.on('change', () => {
                console.log('表單已變更');
                hasUnsavedChanges = true;
            });

            // 如果是載入的表單，初始不算變更
            if (formId || isNewForm) {
                hasUnsavedChanges = false;
            }

            // 初始化分頁管理器
            setTimeout(() => {
                PageManager.init();
                console.log('分頁管理器初始化成功');
            }, 300);

            // 初始化底圖管理器
            BackgroundManager.init();
            console.log('底圖管理器初始化成功');
        })
        .catch(error => {
            console.error('Builder 初始化失敗:', error);
            Toast.error('初始化失敗：' + error.message);
        });
});

// ==================== 表單寬度設定 ====================
function setFormWidth(width) {
    // 相容舊資料：null 視為瀏覽器寬度
    if (width === null || width === undefined) {
        width = document.documentElement.clientWidth;
    }

    console.log('設定表單寬度:', width);
    currentFormWidth = width;

    const widthInput = document.getElementById('form-width-input');

    // 取得或建立動態樣式元素
    let styleEl = document.getElementById('form-width-style');
    if (!styleEl) {
        styleEl = document.createElement('style');
        styleEl.id = 'form-width-style';
        document.head.appendChild(styleEl);
    }

    const browserWidth = document.documentElement.clientWidth;
    if (width >= browserWidth) {
        // 全寬模式 - 寬度等於或大於瀏覽器寬度，不限制
        styleEl.textContent = '';
    } else {
        // 限制寬度模式 - 對 .formarea 本身設定寬度（讓它成為畫布）
        styleEl.textContent = `
            #builder .formarea {
                max-width: ${width}px !important;
                margin: 0 auto !important;
                background-color: #ffffff !important;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1) !important;
                min-height: 400px;
            }
        `;
    }
    widthInput.value = width;

    // 更新按鈕狀態
    document.querySelectorAll('#btn-width-narrow, #btn-width-wide, #btn-width-full').forEach(btn => {
        btn.classList.remove('active');
    });
    if (width >= browserWidth) {
        document.getElementById('btn-width-full').classList.add('active');
    } else if (width === WIDTH_PRESETS.narrow) {
        document.getElementById('btn-width-narrow').classList.add('active');
    } else if (width === WIDTH_PRESETS.wide) {
        document.getElementById('btn-width-wide').classList.add('active');
    }

    // 標記有變更
    hasUnsavedChanges = true;
}

// 綁定寬度設定按鈕和輸入框
document.getElementById('btn-width-narrow').addEventListener('click', () => setFormWidth(WIDTH_PRESETS.narrow));
document.getElementById('btn-width-wide').addEventListener('click', () => setFormWidth(WIDTH_PRESETS.wide));
document.getElementById('btn-width-full').addEventListener('click', () => {
    // 取得瀏覽器可用寬度作為表單寬度
    const browserWidth = document.documentElement.clientWidth;
    setFormWidth(browserWidth);
});
document.getElementById('form-width-input').addEventListener('change', (e) => {
    const value = parseInt(e.target.value);
    if (value && value >= 300) {
        setFormWidth(value);
    } else if (!e.target.value) {
        // 清空輸入框時，使用瀏覽器寬度
        const browserWidth = document.documentElement.clientWidth;
        setFormWidth(browserWidth);
    }
});

// 點擊輸入框時，若無值則預設 1400
document.getElementById('form-width-input').addEventListener('focus', (e) => {
    if (!e.target.value) {
        e.target.value = 1400;
    }
});

// 綁定風格主題下拉選單
document.getElementById('form-theme').addEventListener('change', (e) => {
    setFormTheme(e.target.value);
});

// ==================== Schema 彈出視窗 ====================
const schemaModal = document.getElementById('schema-modal');
const schemaModalClose = document.getElementById('schema-modal-close');
const schemaModalCancel = document.getElementById('schema-modal-cancel');
const schemaModalApply = document.getElementById('schema-modal-apply');
const schemaOutput = document.getElementById('schema-output');
const schemaError = document.getElementById('schema-error');

function closeSchemaModal() {
    schemaModal.classList.remove('show');
    schemaError.style.display = 'none';
}

document.getElementById('btn-get-schema').addEventListener('click', () => {
    if (formBuilder) {
        const schema = formBuilder.schema;
        schemaOutput.value = JSON.stringify(schema, null, 2);
        schemaError.style.display = 'none';
        schemaModal.classList.add('show');
    }
});

schemaModalClose.addEventListener('click', closeSchemaModal);
schemaModalCancel.addEventListener('click', closeSchemaModal);

schemaModal.addEventListener('click', (e) => {
    if (e.target === schemaModal) {
        closeSchemaModal();
    }
});

// 套用 Schema 變更
schemaModalApply.addEventListener('click', async () => {
    try {
        const newSchema = JSON.parse(schemaOutput.value);

        // 驗證基本結構
        if (!newSchema.components && !Array.isArray(newSchema)) {
            throw new Error('Schema 必須包含 components 欄位');
        }

        // 套用到 Form Builder
        await formBuilder.setForm(newSchema);
        hasUnsavedChanges = true;

        Toast.success('Schema 已套用，請記得儲存表單');
        closeSchemaModal();
        console.log('Schema 已即時套用');
    } catch (error) {
        console.error('Schema 解析錯誤:', error);
        schemaError.textContent = 'JSON 格式錯誤: ' + error.message;
        schemaError.style.display = 'block';
    }
});
