/**
 * form-designer-background.js -- BackgroundManager 底圖管理
 * 從 form-designer-main.js 拆分
 *
 * 依賴全域: Toast (form-designer-toast.js), AuthModule,
 *           hasUnsavedChanges (form-designer-main.js)
 * 提供全域: BackgroundManager
 */

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
            const response = await AuthModule.authenticatedFetch(window.__BP + '/auth/me');
            const data = await response.json();
            const user = data.data || data.user;
            if (user && user.org_secure_code) {
                this.orgSecureCode = user.org_secure_code.toUpperCase();
                console.log('底圖管理器初始化，組織代碼:', this.orgSecureCode);
            }
        } catch (error) {
            console.error('取得組織代碼失敗:', error);
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
            const response = await fetch(window.__BP + '/api/workflows/backgrounds');
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
            console.error('載入圖庫失敗:', error);
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
            const response = await fetch(window.__BP + '/api/workflows/backgrounds/upload', {
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
                Toast.error(result.message || __('上傳失敗'));
            }
        } catch (error) {
            console.error('上傳失敗:', error);
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
                    console.error('拼圖位移：圖片載入失敗');
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
