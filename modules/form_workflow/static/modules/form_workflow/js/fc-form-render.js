/**
 * fc-form-render.js — 表單渲染共用 mixin (FormIO readonly、底圖、主題、欄位權限)
 * 由 form-center.js 拆分而來
 */
function fcFormRender() {
    return {
        // --- Methods ---

        async _renderFormReadOnly(containerId, schema, formData, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return null;

            // 補丁 file component storage
            if (window.BkFileProvider) BkFileProvider.patchSchema(schema);

            try {
                const form = await Formio.createForm(container, schema, {
                    readOnly: true,
                    viewAsHtml: false
                });

                if (formData) {
                    form.submission = { data: formData };
                }

                this.applyFormBackground(containerId, builderConfig);
                return form;
            } catch (e) {
                console.error('渲染唯讀表單失敗:', e);
                container.innerHTML = '<p style="color: #dc2626; text-align: center;">表單載入失敗</p>';
                return null;
            }
        },

        /**
         * 動態套用欄位權限覆蓋（來自 input_variables 評估結果）
         * @param {Object} formInstance - Formio form instance
         * @param {Object} overrides - { fieldKey: 'editable'|'readonly'|'hidden' }
         */
        _applyFieldPermissionOverrides(formInstance, overrides) {
            if (!formInstance || !overrides) return;

            const applyToComponent = (comp) => {
                const perm = overrides[comp.key];
                if (!perm) return;

                if (perm === 'hidden') {
                    comp.visible = false;
                } else if (perm === 'editable') {
                    comp.disabled = false;
                    comp.visible = true;
                } else if (perm === 'readonly') {
                    comp.disabled = true;
                    comp.visible = true;
                }
            };

            try {
                formInstance.everyComponent(applyToComponent);
                formInstance.redraw();
            } catch (e) {
                console.warn('動態欄位權限套用失敗:', e);
            }
        },

        applyFormBackground(containerId, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // 白色表單區域 + 陰影（匹配設計器 preview 行為）
            container.style.backgroundColor = '#ffffff';
            container.style.padding = '20px';
            container.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
            container.style.minHeight = '400px';

            // 套用風格主題
            const formTheme = builderConfig?.formTheme;
            if (formTheme && formTheme !== 'default') {
                container.setAttribute('data-form-theme', formTheme);
            } else {
                container.removeAttribute('data-form-theme');
            }

            // 套用寬度
            const formWidth = builderConfig?.formWidth;
            if (formWidth) {
                container.style.maxWidth = formWidth + 'px';
                container.style.margin = '0 auto';
            }

            // 套用底圖
            const bgConfig = builderConfig?.background;
            if (!bgConfig || !bgConfig.url) return;

            const opacity = (bgConfig.opacity || 30) / 100;
            const fit = bgConfig.fit || 'contain';
            const position = bgConfig.position || 'center center';
            const isTile = fit === 'tile';
            const isTileOffset = fit === 'tile-offset';

            container.classList.add('has-background');

            // 移除舊的動態 style
            let styleEl = document.getElementById(containerId + '-bg-style');
            if (!styleEl) {
                styleEl = document.createElement('style');
                styleEl.id = containerId + '-bg-style';
                document.head.appendChild(styleEl);
            }

            if (isTileOffset) {
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
                    styleEl.textContent = `
                        #${containerId}.has-background::before {
                            background-image: url(${dataUrl});
                            background-repeat: repeat;
                            background-size: auto;
                            opacity: ${opacity};
                        }
                    `;
                };
                img.src = bgConfig.url;
            } else {
                const bgSize = isTile ? 'auto' : fit;
                const bgRepeat = isTile ? 'repeat' : 'no-repeat';
                styleEl.textContent = `
                    #${containerId}.has-background::before {
                        background-image: url(${bgConfig.url});
                        background-repeat: ${bgRepeat};
                        background-size: ${bgSize};
                        background-position: ${position};
                        opacity: ${opacity};
                    }
                `;
            }
        },

        cleanupFormBackground(containerId) {
            const container = document.getElementById(containerId);
            if (container) {
                container.classList.remove('has-background');
                container.removeAttribute('data-form-theme');
                container.style.maxWidth = '';
                container.style.margin = '';
                container.style.backgroundColor = '';
                container.style.padding = '';
                container.style.boxShadow = '';
                container.style.minHeight = '';
            }
            const styleEl = document.getElementById(containerId + '-bg-style');
            if (styleEl) styleEl.remove();
        },
    };
}
