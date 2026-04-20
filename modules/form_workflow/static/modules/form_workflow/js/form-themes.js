/**
 * 表單風格主題管理 — Alpine.js Manager
 */
function formThemeManager() {
    return {
        themes: [],
        loading: true,

        // Modal
        showModal: false,
        modalTitle: '',
        editingTheme: null,
        saving: false,
        formData: {
            name: '',
            display_name: '',
            description: '',
            sort_order: 50,
            css_content: '',
        },

        // Upload
        showUploadModal: false,
        uploadTarget: null,
        uploadFile: null,
        uploadFileName: '',
        uploadFileSize: 0,
        uploading: false,

        // Delete
        showDeleteModal: false,
        deletingTheme: null,

        // Toast
        toast: { show: false, message: '', type: 'info' },

        init() {
            this.loadThemes();
        },

        async loadThemes() {
            this.loading = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/form-themes?all=1');
                const json = await res.json();
                if (json.success) {
                    this.themes = json.data;
                } else {
                    this.showToast(json.message || '載入失敗', 'error');
                }
            } catch (e) {
                this.showToast('載入主題失敗: ' + e.message, 'error');
            }
            this.loading = false;
        },

        // --- Create / Edit ---

        openCreateModal() {
            this.editingTheme = null;
            this.modalTitle = '新增主題';
            this.formData = {
                name: '',
                display_name: '',
                description: '',
                sort_order: 50,
                css_content: '',
            };
            this.showModal = true;
        },

        async editTheme(theme) {
            // 取得含 CSS 的完整資料
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/form-themes/${theme.secure_code}`);
                const json = await res.json();
                if (!json.success) {
                    this.showToast(json.message || '載入失敗', 'error');
                    return;
                }
                const full = json.data;
                this.editingTheme = theme;
                this.modalTitle = '編輯主題';
                this.formData = {
                    name: full.name,
                    display_name: full.display_name,
                    description: full.description || '',
                    sort_order: full.sort_order || 0,
                    css_content: full.css_content || '',
                };
                this.showModal = true;
            } catch (e) {
                this.showToast('載入主題詳情失敗: ' + e.message, 'error');
            }
        },

        async saveTheme() {
            this.saving = true;
            try {
                let url, method;
                if (this.editingTheme) {
                    url = `${window.__BP}/api/form-workflow/form-themes/${this.editingTheme.secure_code}`;
                    method = 'PUT';
                } else {
                    url = window.__BP + '/api/form-workflow/form-themes';
                    method = 'POST';
                }

                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.formData)
                });
                const json = await res.json();

                if (json.success) {
                    this.showToast(json.message, 'success');
                    this.closeModal();
                    this.loadThemes();
                } else {
                    this.showToast(json.message || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
            this.saving = false;
        },

        closeModal() {
            this.showModal = false;
            this.editingTheme = null;
        },

        // --- Upload CSS ---

        openUploadModal(theme) {
            this.uploadTarget = theme;
            this.uploadFile = null;
            this.uploadFileName = '';
            this.uploadFileSize = 0;
            this.showUploadModal = true;
            // 清除 file input
            this.$nextTick(() => {
                const input = document.getElementById('css-file-input');
                if (input) input.value = '';
            });
        },

        handleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.uploadFile = file;
                this.uploadFileName = file.name;
                this.uploadFileSize = file.size;
            }
        },

        async uploadCSS() {
            if (!this.uploadFile || !this.uploadTarget) return;
            this.uploading = true;
            try {
                const formData = new FormData();
                formData.append('file', this.uploadFile);
                formData.append('secure_code', this.uploadTarget.secure_code);

                const res = await fetch(window.__BP + '/api/form-workflow/form-themes/upload', {
                    method: 'POST',
                    body: formData
                });
                const json = await res.json();

                if (json.success) {
                    this.showToast(json.message, 'success');
                    this.showUploadModal = false;
                    this.loadThemes();
                } else {
                    this.showToast(json.message || '上傳失敗', 'error');
                }
            } catch (e) {
                this.showToast('上傳失敗: ' + e.message, 'error');
            }
            this.uploading = false;
        },

        // --- Download CSS ---

        async downloadCSS(theme) {
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/form-themes/${theme.secure_code}`);
                const json = await res.json();
                if (!json.success || !json.data.css_content) {
                    this.showToast('無 CSS 內容可下載', 'warning');
                    return;
                }

                const blob = new Blob([json.data.css_content], { type: 'text/css' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `formio-theme-${theme.name}.css`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                this.showToast('下載失敗: ' + e.message, 'error');
            }
        },

        // --- Toggle Active ---

        async toggleActive(theme) {
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/form-themes/${theme.secure_code}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !theme.is_active })
                });
                const json = await res.json();

                if (json.success) {
                    this.showToast(json.message, 'success');
                    this.loadThemes();
                } else {
                    this.showToast(json.message || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗: ' + e.message, 'error');
            }
        },

        // --- Delete ---

        confirmDelete(theme) {
            this.deletingTheme = theme;
            this.showDeleteModal = true;
        },

        async deleteTheme() {
            if (!this.deletingTheme) return;
            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/form-themes/${this.deletingTheme.secure_code}`, {
                    method: 'DELETE'
                });
                const json = await res.json();

                if (json.success) {
                    this.showToast(json.message, 'success');
                    this.showDeleteModal = false;
                    this.deletingTheme = null;
                    this.loadThemes();
                } else {
                    this.showToast(json.message || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // --- Utility ---

        formatSize(bytes) {
            if (!bytes || bytes === 0) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            return (bytes / 1024).toFixed(1) + ' KB';
        },

        showToast(message, type = 'info') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
