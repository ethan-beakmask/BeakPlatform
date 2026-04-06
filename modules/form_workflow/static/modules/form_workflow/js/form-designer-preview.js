/**
 * form-designer-preview.js -- 預覽 + 列印預覽
 * 從 form-designer-main.js 拆分
 *
 * 依賴全域: formBuilder, currentFormWidth, currentFormTheme (form-designer-main.js),
 *           Toast (form-designer-toast.js), BackgroundManager (form-designer-background.js),
 *           getProcessedSchema (form-designer-save.js), formioI18n (form-designer-init.js)
 */

// ==================== 預覽模態框 ====================
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

            console.log(`全覽：${formWidth}x${formHeight}px -> 縮放 ${Math.round(scale * 100)}%`);
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
    console.log('預覽表單:', schema);

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

    // 補丁 file component storage
    if (window.BkFileProvider) BkFileProvider.patchSchema(schema);

    // 創建預覽表單
    try {
        previewFormInstance = await Formio.createForm(previewFormContainer, schema, {
            readOnly: false,  // 允許輸入以便測試表單
            noAlerts: false,  // 顯示驗證訊息
            language: 'zh-TW',
            i18n: { 'zh-TW': formioI18n }
        });
        console.log('預覽表單建立成功');

        // 套用底圖
        BackgroundManager.applyToContainer(previewFormContainer, 'preview-bg-style');

        // 套用風格主題
        if (currentFormTheme && currentFormTheme !== 'default') {
            previewFormWrapper.setAttribute('data-form-theme', currentFormTheme);
        } else {
            previewFormWrapper.removeAttribute('data-form-theme');
        }

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
        console.error('建立預覽表單失敗:', error);
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
    previewFormWrapper.removeAttribute('data-form-theme');
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


// ==================== 列印預覽 ====================
const printPreviewModal = document.getElementById('print-preview-modal');
const printPreviewModalClose = document.getElementById('print-preview-modal-close');
const printPreviewContainer = document.getElementById('print-preview-container');
const printButton = document.getElementById('print-button');
let printPreviewFormInstance = null;

// 列印預覽按鈕
document.getElementById('btn-print-preview').addEventListener('click', async () => {
    if (!formBuilder) return;

    const schema = getProcessedSchema();
    console.log('列印預覽:', schema);

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

    // 補丁 file component storage
    if (window.BkFileProvider) BkFileProvider.patchSchema(schema);

    // 創建列印預覽表單（唯讀模式）
    try {
        printPreviewFormInstance = await Formio.createForm(formContainer, schema, {
            readOnly: true,  // 列印預覽使用唯讀模式
            language: 'zh-TW',
            i18n: { 'zh-TW': formioI18n }
        });
        console.log('列印預覽表單建立成功');

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
        console.error('建立列印預覽表單失敗:', error);
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
    console.log('執行列印');
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
