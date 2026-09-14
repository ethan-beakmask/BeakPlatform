/**
 * form-designer-template.js -- TemplateManager 範本管理
 * 從 form-designer-main.js 拆分
 *
 * 依賴全域: formBuilder, hasUnsavedChanges (form-designer-main.js),
 *           Toast (form-designer-toast.js), PageManager (form-designer-init.js)
 */

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
                        console.log('範本上傳成功:', file.name);
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
            const response = await fetch(window.__BP + '/api/forms/data/formio-templates');
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
            if (!confirm(__('載入範本會覆蓋目前的表單內容，確定要繼續嗎？'))) {
                return;
            }
        }

        try {
            this.loadButton.disabled = true;
            this.loadButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>載入中...';

            const response = await fetch(`${window.__BP}/api/forms/data/formio-templates/${this.selectedTemplateId}`);
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
                        console.log('範本載入成功:', templateData.name);
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
                throw new Error(result.message || __('載入範本失敗'));
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
