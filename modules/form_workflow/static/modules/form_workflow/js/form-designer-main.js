/**
 * form_designer.html — Main JS (merged from inline + 4 partials)
 */

// 第一時間覆寫 CDN — 封閉網路環境，指向本地 vendor
// 必須用 setBaseUrl() 才會觸發 updateUrls() 重新計算所有路徑
if (Formio.cdn && typeof Formio.cdn.setBaseUrl === 'function') {
    Formio.cdn.setBaseUrl('/static/vendor');
    console.log('Formio CDN 已覆寫，ACE 路徑:', Formio.cdn.ace);
}
Formio.ace = { basePath: '/static/vendor/ace' };

// v5 預設改用 Bootstrap Icons，強制使用 Font Awesome
Formio.icons = 'fontawesome';

console.log('Form.io 版本:', Formio.version || '未知');


// Toast 通知系統
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            console.error('❌ Toast container not found!');
        }
    },

    show(message, type = 'info', duration = 3000) {
        if (!this.container) {
            this.init();
        }

        if (!this.container) {
            console.error('❌ Toast container 初始化失敗！');
            return null;
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            info: 'fa-info-circle',
            warning: 'fa-exclamation-triangle'
        };

        toast.innerHTML = `
            <i class="fas ${icons[type]} toast-icon"></i>
            <div class="toast-message">${message}</div>
        `;

        this.container.appendChild(toast);

        // 自動移除
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);

        return toast;
    },

    success(message, duration) {
        return this.show(message, 'success', duration);
    },

    error(message, duration) {
        return this.show(message, 'error', duration);
    },

    info(message, duration) {
        return this.show(message, 'info', duration);
    },

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
};


let formBuilder;
let hasUnsavedChanges = false;
let currentFormId = null;  // 目前編輯的表單 ID
let currentFormWidth = null;  // 目前表單寬度（null 表示全寬）

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


// 底圖管理物件
const BackgroundManager = {
    currentConfig: {
        url: null,
        opacity: 30,
        fit: 'contain',
        position: 'center center'
    },
    orgSecureCode: null,
    galleryItems: [],

    async init() {
        // 從 user 資訊取得 org_secure_code
        try {
            const response = await AuthModule.authenticatedFetch('/auth/me');
            const data = await response.json();
            const user = data.data || data.user;
            if (user && user.org_secure_code) {
                this.orgSecureCode = user.org_secure_code.toUpperCase();
                console.log('✅ 底圖管理器初始化，組織代碼:', this.orgSecureCode);
            }
        } catch (error) {
            console.error('❌ 取得組織代碼失敗:', error);
        }

        this.bindEvents();
    },

    bindEvents() {
        // 底圖按鈕
        document.getElementById('btn-background').addEventListener('click', () => this.openModal());

        // 模態框關閉
        document.getElementById('background-modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('background-cancel').addEventListener('click', () => this.closeModal());

        // 套用按鈕
        document.getElementById('background-apply').addEventListener('click', () => this.applyBackground());

        // 移除底圖
        document.getElementById('btn-remove-bg').addEventListener('click', () => this.removeBackground());

        // 上傳按鈕
        document.getElementById('btn-upload-bg').addEventListener('click', () => this.uploadBackground());

        // 透明度滑桿
        document.getElementById('bg-opacity').addEventListener('input', (e) => {
            document.getElementById('bg-opacity-value').textContent = e.target.value + '%';
            this.updatePreview();
        });

        // 顯示方式和位置
        document.getElementById('bg-fit').addEventListener('change', () => this.updatePreview());
        document.getElementById('bg-position').addEventListener('change', () => this.updatePreview());
    },

    openModal() {
        const modal = document.getElementById('background-modal');
        modal.style.display = 'flex';

        // 載入圖庫
        this.loadGallery();

        // 恢復目前設定
        this.restoreCurrentSettings();
    },

    closeModal() {
        document.getElementById('background-modal').style.display = 'none';
    },

    restoreCurrentSettings() {
        document.getElementById('bg-opacity').value = this.currentConfig.opacity;
        document.getElementById('bg-opacity-value').textContent = this.currentConfig.opacity + '%';
        document.getElementById('bg-fit').value = this.currentConfig.fit;
        document.getElementById('bg-position').value = this.currentConfig.position;
        this.updatePreviewPanel();
    },

    async loadGallery() {
        const gallery = document.getElementById('bg-gallery');

        try {
            const response = await fetch('/api/workflows/backgrounds');
            const result = await response.json();

            if (result.success && result.data.length > 0) {
                this.galleryItems = result.data;
                gallery.innerHTML = result.data.map(bg => `
                    <div class="col-3">
                        <div class="bg-gallery-item ${this.currentConfig.url === bg.url ? 'selected' : ''}"
                             data-url="${bg.url}" data-id="${bg.id}">
                            <img src="${bg.url}" alt="${bg.description || bg.original_filename}">
                            <div class="bg-name">${bg.description || bg.original_filename || '未命名'}</div>
                        </div>
                    </div>
                `).join('');

                // 綁定點擊事件
                gallery.querySelectorAll('.bg-gallery-item').forEach(item => {
                    item.addEventListener('click', () => {
                        gallery.querySelectorAll('.bg-gallery-item').forEach(i => i.classList.remove('selected'));
                        item.classList.add('selected');
                        this.currentConfig.url = item.dataset.url;
                        this.updatePreviewPanel();
                    });
                });
            } else {
                gallery.innerHTML = '<div class="col-12 text-center text-muted py-3">尚無底圖，請上傳</div>';
            }
        } catch (error) {
            console.error('❌ 載入圖庫失敗:', error);
            gallery.innerHTML = '<div class="col-12 text-center text-danger py-3">載入失敗</div>';
        }
    },

    async uploadBackground() {
        const fileInput = document.getElementById('bg-file-input');
        const file = fileInput.files[0];

        if (!file) {
            Toast.warning('請選擇檔案');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/workflows/backgrounds/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                Toast.success('上傳成功');
                fileInput.value = '';
                this.currentConfig.url = result.data.url;
                await this.loadGallery();
                this.updatePreviewPanel();
            } else {
                Toast.error(result.message || '上傳失敗');
            }
        } catch (error) {
            console.error('❌ 上傳失敗:', error);
            Toast.error('上傳失敗');
        }
    },

    updatePreviewPanel() {
        const preview = document.getElementById('current-bg-preview');
        if (this.currentConfig.url) {
            const opacity = document.getElementById('bg-opacity').value / 100;
            const fit = document.getElementById('bg-fit').value;
            const position = document.getElementById('bg-position').value;

            preview.innerHTML = `<img src="${this.currentConfig.url}" style="max-width:100%; max-height:140px; opacity:${opacity}; object-fit:${fit};">`;
        } else {
            preview.innerHTML = '<span class="text-muted">尚未設定底圖</span>';
        }
    },

    updatePreview() {
        this.updatePreviewPanel();
    },

    removeBackground() {
        this.currentConfig.url = null;
        document.querySelectorAll('.bg-gallery-item').forEach(i => i.classList.remove('selected'));
        this.updatePreviewPanel();
    },

    applyBackground() {
        // 儲存設定
        this.currentConfig.opacity = parseInt(document.getElementById('bg-opacity').value);
        this.currentConfig.fit = document.getElementById('bg-fit').value;
        this.currentConfig.position = document.getElementById('bg-position').value;

        // 套用到設計區
        this.applyToDesigner();

        // 標記有變更
        hasUnsavedChanges = true;

        this.closeModal();
        Toast.success('底圖已套用');
    },

    applyToDesigner() {
        const formarea = document.querySelector('#builder .formarea');
        if (!formarea) return;

        if (this.currentConfig.url) {
            formarea.classList.add('has-background');
            const opacity = this.currentConfig.opacity / 100;
            formarea.style.setProperty('--bg-image', `url(${this.currentConfig.url})`);
            formarea.style.setProperty('--bg-opacity', opacity);
            formarea.style.setProperty('--bg-size', this.currentConfig.fit);
            formarea.style.setProperty('--bg-position', this.currentConfig.position);

            // 直接設定 ::before 的樣式（透過 style 標籤）
            let styleEl = document.getElementById('formarea-bg-style');
            if (!styleEl) {
                styleEl = document.createElement('style');
                styleEl.id = 'formarea-bg-style';
                document.head.appendChild(styleEl);
            }

            // 判斷顯示模式
            const fit = this.currentConfig.fit;
            const isTile = fit === 'tile';
            const isTileOffset = fit === 'tile-offset';
            let cssContent = '';

            if (isTileOffset) {
                // 磚塊式交錯：用 Canvas 生成組合圖
                const bgUrl = this.currentConfig.url;

                // 如果已有快取的組合圖，直接使用
                if (this._tileOffsetCache && this._tileOffsetCache.originalUrl === bgUrl) {
                    cssContent = `
                        .formarea.has-background::before {
                            background-image: url(${this._tileOffsetCache.dataUrl});
                            opacity: ${opacity};
                            background-size: auto;
                            background-position: 0 0;
                            background-repeat: repeat;
                        }
                    `;
                    styleEl.textContent = cssContent;
                    return;
                }

                // 生成組合圖
                const img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    const w = img.width;
                    const h = img.height;
                    const halfW = Math.floor(w / 2);

                    // 組合圖高度是原圖的 2 倍
                    canvas.width = w;
                    canvas.height = h * 2;

                    // 上半部：原圖
                    ctx.drawImage(img, 0, 0);

                    // 下半部：左右對調
                    ctx.drawImage(img, halfW, 0, w - halfW, h, 0, h, w - halfW, h);
                    ctx.drawImage(img, 0, 0, halfW, h, w - halfW, h, halfW, h);

                    const dataUrl = canvas.toDataURL('image/png');

                    // 快取結果
                    this._tileOffsetCache = { originalUrl: bgUrl, dataUrl };


                    const offsetCss = `
                        .formarea.has-background::before {
                            background-image: url(${dataUrl});
                            opacity: ${opacity};
                            background-size: auto;
                            background-position: 0 0;
                            background-repeat: repeat;
                        }
                    `;
                    document.getElementById('formarea-bg-style').textContent = offsetCss;
                };
                img.onerror = () => {
                    console.error('🎨 拼圖位移：圖片載入失敗');
                    Toast.error('圖片載入失敗，無法生成位移效果');
                };
                img.src = bgUrl;

                // 先顯示原圖，等組合圖生成後再替換
                cssContent = `
                    .formarea.has-background::before {
                        background-image: url(${bgUrl});
                        opacity: ${opacity};
                        background-size: auto;
                        background-position: 0 0;
                        background-repeat: repeat;
                    }
                `;
            } else if (isTile) {
                // 普通拼圖模式
                cssContent = `
                    .formarea.has-background::before {
                        background-image: url(${this.currentConfig.url});
                        opacity: ${opacity};
                        background-size: auto;
                        background-position: ${this.currentConfig.position};
                        background-repeat: repeat;
                    }
                `;
            } else {
                // 其他模式：符合、填滿、拉伸、原始大小
                cssContent = `
                    .formarea.has-background::before {
                        background-image: url(${this.currentConfig.url});
                        opacity: ${opacity};
                        background-size: ${fit};
                        background-position: ${this.currentConfig.position};
                        background-repeat: no-repeat;
                    }
                `;
            }

            styleEl.textContent = cssContent;
        } else {
            formarea.classList.remove('has-background');
            const styleEl = document.getElementById('formarea-bg-style');
            if (styleEl) styleEl.remove();
        }
    },

    getConfig() {
        return this.currentConfig.url ? { ...this.currentConfig } : null;
    },

    setConfig(config) {
        if (config) {
            this.currentConfig = { ...this.currentConfig, ...config };
            this.applyToDesigner();
        }
    },

    // 套用底圖到指定容器（供預覽、列印預覽使用）
    applyToContainer(container, styleId) {
        if (!container || !this.currentConfig.url) return;

        const opacity = this.currentConfig.opacity / 100;
        const fit = this.currentConfig.fit;
        const position = this.currentConfig.position;
        const bgUrl = this.currentConfig.url;

        // 移除舊的樣式
        let styleEl = document.getElementById(styleId);
        if (!styleEl) {
            styleEl = document.createElement('style');
            styleEl.id = styleId;
            document.head.appendChild(styleEl);
        }

        container.classList.add('has-background');

        const isTile = fit === 'tile';
        const isTileOffset = fit === 'tile-offset';

        if (isTileOffset) {
            // 位移交錯：用 Canvas 生成組合圖
            if (this._tileOffsetCache && this._tileOffsetCache.originalUrl === bgUrl) {
                // 使用快取
                this._setContainerBgStyle(styleEl, container.id, this._tileOffsetCache.dataUrl, opacity, 'auto', 'repeat', '0 0');
            } else {
                const img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');
                    const w = img.width;
                    const h = img.height;
                    const halfW = Math.floor(w / 2);

                    canvas.width = w;
                    canvas.height = h * 2;
                    ctx.drawImage(img, 0, 0);
                    ctx.drawImage(img, halfW, 0, w - halfW, h, 0, h, w - halfW, h);
                    ctx.drawImage(img, 0, 0, halfW, h, w - halfW, h, halfW, h);

                    const dataUrl = canvas.toDataURL('image/png');
                    this._tileOffsetCache = { originalUrl: bgUrl, dataUrl };
                    this._setContainerBgStyle(styleEl, container.id, dataUrl, opacity, 'auto', 'repeat', '0 0');
                };
                img.src = bgUrl;
            }
        } else if (isTile) {
            this._setContainerBgStyle(styleEl, container.id, bgUrl, opacity, 'auto', 'repeat', position);
        } else {
            this._setContainerBgStyle(styleEl, container.id, bgUrl, opacity, fit, 'no-repeat', position);
        }
    },

    _setContainerBgStyle(styleEl, containerId, url, opacity, size, repeat, position) {
        styleEl.textContent = `
            #${containerId}.has-background {
                position: relative;
                min-height: 300px;
            }
            #${containerId}.has-background::before {
                content: '';
                position: absolute;
                top: 0; left: 0; right: 0; bottom: 0;
                background-image: url(${url});
                background-size: ${size};
                background-repeat: ${repeat};
                background-position: ${position};
                opacity: ${opacity};
                pointer-events: none;
                z-index: 0;
            }
            #${containerId}.has-background > * {
                position: relative;
                z-index: 1;
            }
        `;
    },

    removeContainerBg(container, styleId) {
        if (container) container.classList.remove('has-background');
        const styleEl = document.getElementById(styleId);
        if (styleEl) styleEl.remove();
    }
};

// 從 URL 取得參數
const urlParams = new URLSearchParams(window.location.search);
const formId = urlParams.get('id');
const isNewForm = urlParams.get('new') === '1';
const wasJustCreated = urlParams.get('created') === '1';
let hasEverSaved = false;  // 追蹤是否曾在設計器儲存過
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
            console.log('✅ Form.io 中文翻譯載入成功，共', Object.keys(formioI18n).length, '個字串');
        }
    } catch (error) {
        console.warn('⚠️ 載入中文翻譯失敗，使用英文介面:', error);
    }
}

// 初始化 Form.io Builder
const options = {
    language: 'zh-TW',
    noDefaultSubmitButton: true,  // 禁用自動產生的 Submit 按鈕
    i18n: {
        'zh-TW': formioI18n
    },
    builder: {
        basic: {
            title: '基本元件',
            weight: 0,
            default: true,
            components: {
                textfield: true,
                textarea: true,
                number: true,
                email: true,
                phoneNumber: true,
                checkbox: true,
                selectboxes: true,
                select: true,
                radio: true,
                button: true
            }
        },
        advanced: {
            title: '進階元件',
            weight: 10,
            components: {
                file: true,
                datetime: true,
                day: true,
                time: true,
                currency: true,
                survey: true
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
                tabs: true,
                well: true
            }
        }
    }
};

// 載入表單資料
async function loadFormData() {
    if (formId) {
        // 編輯模式 - 載入現有表單
        try {
            console.log('📂 載入表單 ID:', formId);
            const response = await fetch(`/api/forms/data/templates/${formId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const result = await response.json();
            console.log('✅ 表單資料載入成功:', result);

            const formData = result.data;

            // 處理權限控制
            if (formData._permissions) {
                const perms = formData._permissions;
                console.log('🔐 權限資訊:', perms);

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

                    console.log('🔒 唯讀模式已啟用');
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
                    }
                }, 100);
                // 恢復底圖設定
                if (formData.builder_config.background) {
                    setTimeout(() => {
                        BackgroundManager.setConfig(formData.builder_config.background);
                    }, 500);
                }
                // 恢復 placeholder→label 開關
                if (formData.builder_config.placeholderToLabel) {
                    document.getElementById('chk-placeholder-to-label').checked = true;
                }
            }

            // 返回 schema
            return formData.schema || { components: [] };
        } catch (error) {
            console.error('❌ 載入表單失敗:', error);
            Toast.error('載入表單失敗：' + error.message);
            return { components: [] };
        }
    } else if (isNewForm) {
        // 新增模式 - 使用 URL 預設值
        console.log('📝 新增表單模式');
        document.getElementById('form-name').value = formName;
        document.getElementById('form-category').value = urlCategory;
        document.getElementById('form-description').value = urlDescription;
        const titleText = formName || '表單標題';
        return { components: [
            { type: 'htmlelement', tag: 'h3', attrs: [{ attr: 'style', value: 'text-align:center; margin:0 0 0.5rem 0;' }], content: titleText, key: 'formTitle', input: false, tableView: false }
        ] };
    } else {
        // 無參數 - 新增空白表單
        console.log('📝 無參數，建立空白表單');
        document.getElementById('form-name').value = '新表單';
        return { components: [
            { type: 'htmlelement', tag: 'h3', attrs: [{ attr: 'style', value: 'text-align:center; margin:0 0 0.5rem 0;' }], content: '表單標題', key: 'formTitle', input: false, tableView: false }
        ] };
    }
}

// 初始化 Builder (先載入翻譯)
loadFormioTranslations().then(() => {
    // 更新 options 中的翻譯
    options.i18n = { 'zh-TW': formioI18n };

    return loadFormData();
}).then(initialSchema => {
    Formio.builder(document.getElementById('builder'), initialSchema, options)
        .then(builder => {
            formBuilder = builder;
            console.log('✅ Form.io Builder 初始化成功');

            // placeholder→label 自動填入（可由 checkbox 開關）
            // 非拉丁文字（CJK、日韓、泰文等）觸發
            // 支援 || 分隔符：前段→label，後段→placeholder
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
                    // 有 || — 前段→label，後段→placeholder（只處理第一組 ||）
                    component.label = component.placeholder.substring(0, sepIdx);
                    component.placeholder = component.placeholder.substring(sepIdx + 2);
                }
                setTimeout(() => builder.redraw(), 50);
            });

            // 監聽變更
            builder.on('change', () => {
                console.log('📝 表單已變更');
                hasUnsavedChanges = true;
            });

            // 如果是載入的表單，初始不算變更
            if (formId || isNewForm) {
                hasUnsavedChanges = false;
            }

            // 初始化分頁管理器
            setTimeout(() => {
                PageManager.init();
                console.log('✅ 分頁管理器初始化成功');
            }, 300);

            // 初始化底圖管理器
            BackgroundManager.init();
            console.log('✅ 底圖管理器初始化成功');
        })
        .catch(error => {
            console.error('❌ Builder 初始化失敗:', error);
            Toast.error('初始化失敗：' + error.message);
        });
});

// 表單寬度設定功能
function setFormWidth(width) {
    // 相容舊資料：null 視為瀏覽器寬度
    if (width === null || width === undefined) {
        width = document.documentElement.clientWidth;
    }

    console.log('📐 設定表單寬度:', width);
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

// Schema 彈出視窗控制
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
        console.log('✅ Schema 已即時套用');
    } catch (error) {
        console.error('Schema 解析錯誤:', error);
        schemaError.textContent = 'JSON 格式錯誤: ' + error.message;
        schemaError.style.display = 'block';
    }
});

// 預覽模態框控制（含全覽切換）
const previewModal = document.getElementById('preview-modal');
const previewModalClose = document.getElementById('preview-modal-close');
const previewModalBody = document.getElementById('preview-modal-body');
const previewFormWrapper = document.getElementById('preview-form-wrapper');
const previewFormContainer = document.getElementById('preview-form');
const previewModeNormal = document.getElementById('preview-mode-normal');
const previewModeOverview = document.getElementById('preview-mode-overview');
const previewScaleInfo = document.getElementById('preview-scale-info');
let previewFormInstance = null;
let isOverviewMode = false;

// 切換預覽模式
function setPreviewMode(overview) {
    isOverviewMode = overview;

    // 更新按鈕狀態
    previewModeNormal.classList.toggle('active', !overview);
    previewModeOverview.classList.toggle('active', overview);

    if (overview) {
        // 全覽模式：先捲動到頂部，再計算縮放
        previewModalBody.scrollTop = 0;

        // 加底部空間讓使用者明確知道表單結束
        previewFormWrapper.style.paddingBottom = '40px';
        previewFormWrapper.style.background = 'linear-gradient(to bottom, white calc(100% - 40px), #e9ecef calc(100% - 40px))';

        setTimeout(() => {
            const formHeight = previewFormWrapper.scrollHeight;
            const formWidth = previewFormWrapper.scrollWidth;
            const availableHeight = previewModalBody.clientHeight - 20;
            const availableWidth = previewModalBody.clientWidth - 40;

            const scaleH = availableHeight / formHeight;
            const scaleW = availableWidth / formWidth;
            const scale = Math.min(1, Math.min(scaleH, scaleW));

            previewFormWrapper.style.transform = scale < 1 ? `scale(${scale})` : '';
            previewFormWrapper.style.transformOrigin = 'top center';
            previewModalBody.style.overflow = 'hidden';

            previewScaleInfo.textContent = `縮放 ${Math.round(scale * 100)}%`;
            previewScaleInfo.style.display = 'inline';

            console.log(`📐 全覽：${formWidth}x${formHeight}px → 縮放 ${Math.round(scale * 100)}%`);
        }, 100);
    } else {
        // 正常模式：移除縮放與底部空間
        previewFormWrapper.style.transform = '';
        previewFormWrapper.style.paddingBottom = '';
        previewFormWrapper.style.background = '';
        previewModalBody.style.overflow = 'auto';
        previewScaleInfo.style.display = 'none';
    }
}

// 預覽模式切換按鈕
previewModeNormal.addEventListener('click', () => setPreviewMode(false));
previewModeOverview.addEventListener('click', () => setPreviewMode(true));

// 預覽按鈕
document.getElementById('btn-preview').addEventListener('click', async () => {
    if (!formBuilder) return;

    const schema = getProcessedSchema();
    console.log('👁️ 預覽表單:', schema);

    // 清空預覽容器
    previewFormContainer.innerHTML = '';
    previewFormWrapper.style.transform = '';

    // 如果有舊的實例，先銷毀
    if (previewFormInstance) {
        try {
            previewFormInstance.destroy();
        } catch (e) {
            console.warn('銷毀舊預覽實例失敗:', e);
        }
        previewFormInstance = null;
    }

    // 重置為正常模式
    isOverviewMode = false;
    previewModeNormal.classList.add('active');
    previewModeOverview.classList.remove('active');
    previewScaleInfo.style.display = 'none';
    previewModalBody.style.overflow = 'auto';

    // 顯示模態框
    previewModal.classList.add('show');

    // 創建預覽表單
    try {
        previewFormInstance = await Formio.createForm(previewFormContainer, schema, {
            readOnly: false,  // 允許輸入以便測試表單
            noAlerts: false,  // 顯示驗證訊息
            language: 'zh-TW',
            i18n: { 'zh-TW': formioI18n }
        });
        console.log('✅ 預覽表單建立成功');

        // 套用底圖
        BackgroundManager.applyToContainer(previewFormContainer, 'preview-bg-style');

        // 套用寬度
        if (currentFormWidth) {
            previewFormContainer.style.maxWidth = currentFormWidth + 'px';
            previewFormContainer.style.margin = '0 auto';
            previewFormContainer.style.background = '#fff';
            previewFormContainer.style.padding = '20px';
            previewFormContainer.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        } else {
            previewFormContainer.style.maxWidth = '';
            previewFormContainer.style.margin = '';
            previewFormContainer.style.background = '';
            previewFormContainer.style.padding = '';
            previewFormContainer.style.boxShadow = '';
        }
    } catch (error) {
        console.error('❌ 建立預覽表單失敗:', error);
        previewFormContainer.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <strong>錯誤：</strong>無法建立預覽表單<br>
                ${error.message}
            </div>
        `;
    }
});

// 關閉預覽模態框
function closePreviewModal() {
    previewModal.classList.remove('show');
    BackgroundManager.removeContainerBg(previewFormContainer, 'preview-bg-style');
    previewFormWrapper.style.transform = '';
    if (previewFormInstance) {
        try {
            previewFormInstance.destroy();
        } catch (e) {
            console.warn('銷毀預覽實例失敗:', e);
        }
        previewFormInstance = null;
    }
}

previewModalClose.addEventListener('click', closePreviewModal);

// 點擊模態框外部關閉
previewModal.addEventListener('click', (e) => {
    if (e.target === previewModal) {
        closePreviewModal();
    }
});

// 列印預覽功能
const printPreviewModal = document.getElementById('print-preview-modal');
const printPreviewModalClose = document.getElementById('print-preview-modal-close');
const printPreviewContainer = document.getElementById('print-preview-container');
const printButton = document.getElementById('print-button');
let printPreviewFormInstance = null;

// 列印預覽按鈕
document.getElementById('btn-print-preview').addEventListener('click', async () => {
    if (!formBuilder) return;

    const schema = getProcessedSchema();
    console.log('🖨️ 列印預覽:', schema);

    // 清空容器
    printPreviewContainer.innerHTML = '';

    // 如果有舊的實例，先銷毀
    if (printPreviewFormInstance) {
        try {
            printPreviewFormInstance.destroy();
        } catch (e) {
            console.warn('銷毀舊列印預覽實例失敗:', e);
        }
        printPreviewFormInstance = null;
    }

    // 顯示模態框
    printPreviewModal.classList.add('show');

    // 創建表單容器
    const formContainer = document.createElement('div');
    formContainer.id = 'print-form';
    printPreviewContainer.appendChild(formContainer);

    // 創建列印預覽表單（唯讀模式）
    try {
        printPreviewFormInstance = await Formio.createForm(formContainer, schema, {
            readOnly: true,  // 列印預覽使用唯讀模式
            language: 'zh-TW',
            i18n: { 'zh-TW': formioI18n }
        });
        console.log('✅ 列印預覽表單建立成功');

        // 套用底圖
        BackgroundManager.applyToContainer(printPreviewContainer, 'print-preview-bg-style');

        // 套用寬度
        if (currentFormWidth) {
            printPreviewContainer.style.maxWidth = currentFormWidth + 'px';
            printPreviewContainer.style.margin = '0 auto';
        } else {
            printPreviewContainer.style.maxWidth = '';
            printPreviewContainer.style.margin = '';
        }
    } catch (error) {
        console.error('❌ 建立列印預覽表單失敗:', error);
        printPreviewContainer.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <strong>錯誤：</strong>無法建立列印預覽<br>
                ${error.message}
            </div>
        `;
    }
});

// 列印按鈕
printButton.addEventListener('click', () => {
    console.log('🖨️ 執行列印');
    window.print();
});

// 關閉列印預覽模態框
function closePrintPreviewModal() {
    printPreviewModal.classList.remove('show');
    BackgroundManager.removeContainerBg(printPreviewContainer, 'print-preview-bg-style');
    if (printPreviewFormInstance) {
        try {
            printPreviewFormInstance.destroy();
        } catch (e) {
            console.warn('銷毀列印預覽實例失敗:', e);
        }
        printPreviewFormInstance = null;
    }
}

printPreviewModalClose.addEventListener('click', closePrintPreviewModal);

// 點擊模態框外部關閉
printPreviewModal.addEventListener('click', (e) => {
    if (e.target === printPreviewModal) {
        closePrintPreviewModal();
    }
});

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

// 儲存按鈕
document.getElementById('btn-save').addEventListener('click', async () => {
    if (!formBuilder) return;

    const formNameInput = document.getElementById('form-name').value.trim();
    if (!formNameInput) {
        Toast.warning('請輸入表單檔名');
        return;
    }

    const formCategoryInput = document.getElementById('form-category').value;
    const formDescriptionInput = document.getElementById('form-description').value.trim();
    const schema = getProcessedSchema();
    const builderConfig = {
        formWidth: currentFormWidth,
        background: BackgroundManager.getConfig(),
        placeholderToLabel: document.getElementById('chk-placeholder-to-label').checked
    };

    try {
        let response;

        if (currentFormId) {
            // 更新現有表單（背景生成縮圖）
            response = await Promise.race([
                fetch(`/api/forms/data/templates/${currentFormId}`, {
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
                fetch('/api/forms/data/templates', {
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
            // 嘗試解析後端回傳的錯誤訊息
            let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.message) {
                    errorMsg = errorData.message;
                }
                if (errorData.errors) {
                    errorMsg += '\n' + errorData.errors.map(e => `• ${e}`).join('\n');
                }
            } catch (e) {
                // 如果不是 JSON，嘗試讀取純文字
                try {
                    const errorText = await response.text();
                    if (errorText) errorMsg += ': ' + errorText.substring(0, 200);
                } catch (e2) {}
            }
            throw new Error(errorMsg);
        }

        const result = await response.json();

        if (result.success) {
            hasUnsavedChanges = false;
            hasEverSaved = true;
            Toast.success('儲存成功');

            // 如果是新增，更新 currentFormId
            if (!currentFormId && result.data && result.data.secure_code) {
                currentFormId = result.data.secure_code;
                console.log('✅ 新表單 secure_code:', currentFormId);
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
        console.error('❌ 儲存失敗:', error);
        console.error('❌ Error stack:', error.stack);
        Toast.error('儲存失敗：' + error.message);
    }
});

// 儲存並離開按鈕（使用背景模式生成縮圖）
document.getElementById('btn-save-close').addEventListener('click', async () => {
    if (!formBuilder) return;

    const formNameInput = document.getElementById('form-name').value.trim();
    if (!formNameInput) {
        Toast.warning('請輸入表單檔名');
        return;
    }

    const formCategoryInput = document.getElementById('form-category').value;
    const formDescriptionInput = document.getElementById('form-description').value.trim();
    const schema = getProcessedSchema();
    const builderConfig = {
        formWidth: currentFormWidth,
        background: BackgroundManager.getConfig(),
        placeholderToLabel: document.getElementById('chk-placeholder-to-label').checked
    };

    try {
        let response;

        if (currentFormId) {
            // 更新現有表單（背景生成縮圖）
            response = await fetch(`/api/forms/data/templates/${currentFormId}`, {
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
            response = await fetch('/api/forms/data/templates', {
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
            // 嘗試解析後端回傳的錯誤訊息
            let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.message) {
                    errorMsg = errorData.message;
                }
                if (errorData.errors) {
                    errorMsg += '\n' + errorData.errors.map(e => `• ${e}`).join('\n');
                }
            } catch (e) {
                try {
                    const errorText = await response.text();
                    if (errorText) errorMsg += ': ' + errorText.substring(0, 200);
                } catch (e2) {}
            }
            throw new Error(errorMsg);
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
            window.location.href = '/forms/templates';
        } else {
            throw new Error(result.message || '儲存失敗');
        }
    } catch (error) {
        console.error('儲存失敗:', error);
        Toast.error('儲存失敗：' + error.message);
    }
});

// 儲存新版按鈕
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
            background: BackgroundManager.getConfig()
        };

        await fetch(`/api/forms/data/templates/${currentFormId}`, {
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
        const response = await fetch(`/api/forms/data/templates/${currentFormId}/save-new-version`, {
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

// 放棄按鈕 — 清理剛建立但從未儲存的空白記錄
async function cleanupAndRedirect() {
    if (!hasEverSaved && currentFormId) {
        try {
            await fetch(`/api/forms/data/templates/${currentFormId}`, {
                method: 'DELETE'
            });
            console.log('✅ 已刪除從未儲存的表單記錄:', currentFormId);
        } catch (e) {
            console.error('刪除未儲存表單失敗:', e);
        }
    }
    hasUnsavedChanges = false;
    window.location.href = '/forms/templates';
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

// ==================== 範本載入功能 ====================
const TemplateManager = {
    templates: [],
    selectedTemplateId: null,
    modal: null,
    listContainer: null,
    loadButton: null,

    init() {
        this.modal = document.getElementById('template-modal');
        this.listContainer = document.getElementById('template-list');
        this.loadButton = document.getElementById('template-load');

        // 綁定事件
        document.getElementById('btn-load-template').addEventListener('click', () => this.openModal());
        document.getElementById('template-modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('template-cancel').addEventListener('click', () => this.closeModal());
        document.getElementById('template-load').addEventListener('click', () => this.loadSelectedTemplate());

        // 上傳範本功能
        document.getElementById('btn-upload-template').addEventListener('click', () => {
            document.getElementById('template-file-input').click();
        });
        document.getElementById('template-file-input').addEventListener('change', (e) => this.handleFileUpload(e));
    },

    handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        // 檢查副檔名
        if (!file.name.endsWith('.json')) {
            Toast.error('請選擇 JSON 格式的範本檔案');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const schema = JSON.parse(e.target.result);

                // 驗證是否為有效的 Form.io schema
                if (!schema.components && !Array.isArray(schema)) {
                    Toast.error('無效的範本格式：缺少 components 欄位');
                    return;
                }

                // 套用到設計器
                if (formBuilder) {
                    formBuilder.setForm(schema).then(() => {
                        console.log('✅ 範本上傳成功:', file.name);
                        Toast.success(`已載入範本: ${file.name}`);
                        hasUnsavedChanges = true;
                    }).catch(error => {
                        console.error('套用範本失敗:', error);
                        Toast.error('套用範本失敗: ' + error.message);
                    });
                }
            } catch (error) {
                console.error('解析範本失敗:', error);
                Toast.error('範本檔案格式錯誤: ' + error.message);
            }
        };
        reader.readAsText(file);

        // 清除 input 以便重複選擇同一檔案
        event.target.value = '';
    },

    async openModal() {
        this.modal.style.display = 'flex';
        this.selectedTemplateId = null;
        this.loadButton.disabled = true;
        await this.loadTemplateList();
    },

    closeModal() {
        this.modal.style.display = 'none';
    },

    async loadTemplateList() {
        this.listContainer.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-spinner fa-spin me-2"></i>載入中...
            </div>
        `;

        try {
            const response = await fetch('/api/forms/data/formio-templates');
            const result = await response.json();

            if (result.success && result.data.length > 0) {
                this.templates = result.data;
                this.renderTemplateList();
            } else {
                this.listContainer.innerHTML = `
                    <div class="text-center py-4 text-muted">
                        <i class="fas fa-inbox fa-2x mb-2"></i>
                        <p>目前沒有可用的範本</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('載入範本清單失敗:', error);
            this.listContainer.innerHTML = `
                <div class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>載入失敗: ${error.message}
                </div>
            `;
        }
    },

    renderTemplateList() {
        this.listContainer.innerHTML = this.templates.map(template => `
            <a href="#" class="list-group-item list-group-item-action template-item" data-id="${template.id}">
                <div class="d-flex w-100 justify-content-between align-items-start">
                    <div>
                        <h6 class="mb-1">
                            <i class="fas fa-file-alt me-2 text-success"></i>${template.name}
                        </h6>
                        <p class="mb-1 text-muted small">${template.description || '無描述'}</p>
                    </div>
                    <div class="text-end">
                        <span class="badge bg-secondary">${template.category}</span>
                        <small class="d-block text-muted mt-1">v${template.version}</small>
                    </div>
                </div>
            </a>
        `).join('');

        // 綁定選擇事件
        this.listContainer.querySelectorAll('.template-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                // 移除其他選中狀態
                this.listContainer.querySelectorAll('.template-item').forEach(i => i.classList.remove('active'));
                // 設定目前選中
                item.classList.add('active');
                this.selectedTemplateId = item.dataset.id;
                this.loadButton.disabled = false;
            });
        });
    },

    async loadSelectedTemplate() {
        if (!this.selectedTemplateId) {
            Toast.warning('請先選擇一個範本');
            return;
        }

        // 檢查是否有未儲存的變更
        if (hasUnsavedChanges) {
            if (!confirm('載入範本會覆蓋目前的表單內容，確定要繼續嗎？')) {
                return;
            }
        }

        try {
            this.loadButton.disabled = true;
            this.loadButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>載入中...';

            const response = await fetch(`/api/forms/data/formio-templates/${this.selectedTemplateId}`);
            const result = await response.json();

            if (result.success) {
                const templateData = result.data;

                // 設定表單名稱（如果目前是空的）
                const formNameInput = document.getElementById('form-name');
                if (!formNameInput.value.trim()) {
                    formNameInput.value = templateData.name;
                }

                // 設定分類（如果有）
                if (templateData.category_secure_code) {
                    const categorySelect = document.getElementById('form-category');
                    const optionExists = Array.from(categorySelect.options).some(opt => opt.value === templateData.category_secure_code);
                    if (optionExists) {
                        categorySelect.value = templateData.category_secure_code;
                    }
                }

                // 設定描述
                const descInput = document.getElementById('form-description');
                if (!descInput.value.trim() && templateData.description) {
                    descInput.value = templateData.description;
                }

                // 載入 schema 到 builder
                if (formBuilder && templateData.schema) {
                    formBuilder.setForm(templateData.schema).then(() => {
                        console.log('✅ 範本載入成功:', templateData.name);
                        Toast.success(`已載入範本: ${templateData.name}`);
                        hasUnsavedChanges = true;

                        // 更新分頁管理器
                        setTimeout(() => {
                            PageManager.updatePageInfo();
                        }, 300);
                    }).catch(error => {
                        console.error('載入範本到 builder 失敗:', error);
                        Toast.error('載入範本失敗: ' + error.message);
                    });
                }

                this.closeModal();
            } else {
                throw new Error(result.message || '載入範本失敗');
            }
        } catch (error) {
            console.error('載入範本失敗:', error);
            Toast.error('載入範本失敗: ' + error.message);
        } finally {
            this.loadButton.disabled = false;
            this.loadButton.innerHTML = '<i class="fas fa-check"></i> 載入範本';
        }
    }
};

// 初始化範本管理器
TemplateManager.init();
