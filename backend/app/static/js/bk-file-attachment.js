/**
 * BkFileAttachment - 通用附件上傳/下載/刪除元件
 *
 * 統一呼叫 /api/files/ 系列 API，傳入 contextType + contextId 即可使用。
 * 加密/解密在後端自動處理，前端不需關心 storage_type。
 *
 * 用法:
 *   const att = new BkFileAttachment(containerEl, {
 *       contextType: 'form_attachment',
 *       contextId: 'FORM_SC_xxx',
 *       readonly: false,
 *       maxFiles: 10,
 *       onUpload: (file) => {},   // 上傳完成回呼
 *       onDelete: (fileSc) => {}, // 刪除完成回呼
 *   });
 *   att.init();
 *
 * 外部控制:
 *   att.setContextId('new_sc');  // 動態切換 context
 *   att.setReadonly(true);       // 切換唯讀
 *   att.refresh();               // 重新載入列表
 *   att.destroy();               // 銷毀
 */
class BkFileAttachment {

    constructor(container, config) {
        this.container = typeof container === 'string'
            ? document.querySelector(container) : container;

        this.config = Object.assign({
            contextType: '',
            contextId: '',
            readonly: false,
            maxFiles: 10,
            onUpload: null,
            onDelete: null,
        }, config);

        this.files = [];
        this.uploading = false;
        this._els = {};
    }

    // ===== Public API =====

    async init() {
        this._render();
        if (this.config.contextId) {
            await this.refresh();
        }
    }

    async refresh() {
        if (!this.config.contextId) {
            this.files = [];
            this._renderList();
            return;
        }
        try {
            const params = new URLSearchParams({
                context_type: this.config.contextType,
                context_id: this.config.contextId,
            });
            const res = await fetch('/api/files/list?' + params.toString());
            const data = await res.json();
            this.files = data.success ? (data.data || []) : [];
        } catch (e) {
            console.error('BkFileAttachment: refresh failed', e);
            this.files = [];
        }
        this._renderList();
    }

    setContextId(contextId) {
        this.config.contextId = contextId;
        this.refresh();
    }

    setReadonly(readonly) {
        this.config.readonly = readonly;
        this._updateUploadVisibility();
        this._renderList();
    }

    destroy() {
        if (this.container) {
            this.container.innerHTML = '';
        }
        this._els = {};
    }

    // ===== Render =====

    _render() {
        this.container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'bkfa-root';

        // 上傳區
        const uploadArea = document.createElement('div');
        uploadArea.className = 'bkfa-upload-area';

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.multiple = true;
        fileInput.style.display = 'none';
        fileInput.addEventListener('change', (e) => this._handleFiles(e.target.files));

        const uploadBtn = document.createElement('button');
        uploadBtn.type = 'button';
        uploadBtn.className = 'bkfa-upload-btn';
        uploadBtn.innerHTML = '<i class="fas fa-paperclip"></i> 上傳附件';
        uploadBtn.addEventListener('click', () => fileInput.click());

        const status = document.createElement('span');
        status.className = 'bkfa-status';

        uploadArea.appendChild(fileInput);
        uploadArea.appendChild(uploadBtn);
        uploadArea.appendChild(status);

        // 列表區
        const listArea = document.createElement('div');
        listArea.className = 'bkfa-list';

        root.appendChild(uploadArea);
        root.appendChild(listArea);
        this.container.appendChild(root);

        this._els = { root, uploadArea, uploadBtn, fileInput, status, listArea };
        this._updateUploadVisibility();
    }

    _updateUploadVisibility() {
        if (!this._els.uploadArea) return;
        const hide = this.config.readonly || this.files.length >= this.config.maxFiles;
        this._els.uploadArea.style.display = hide ? 'none' : '';
    }

    _renderList() {
        const list = this._els.listArea;
        if (!list) return;
        list.innerHTML = '';

        if (this.files.length === 0) {
            // 不顯示任何空白提示
            this._updateUploadVisibility();
            return;
        }

        const table = document.createElement('table');
        table.className = 'bkfa-table';

        // thead
        const thead = document.createElement('thead');
        thead.innerHTML = '<tr>'
            + '<th>檔案名稱</th>'
            + '<th style="width:80px;text-align:right;">大小</th>'
            + '<th style="width:100px;text-align:center;">操作</th>'
            + '</tr>';
        table.appendChild(thead);

        // tbody
        const tbody = document.createElement('tbody');
        for (const f of this.files) {
            const tr = document.createElement('tr');

            // 名稱
            const tdName = document.createElement('td');
            tdName.className = 'bkfa-filename';
            const icon = this._fileIcon(f.file_ext);
            tdName.innerHTML = icon + ' ' + this._escHtml(f.original_name);
            tr.appendChild(tdName);

            // 大小
            const tdSize = document.createElement('td');
            tdSize.style.textAlign = 'right';
            tdSize.textContent = this._formatSize(f.file_size);
            tr.appendChild(tdSize);

            // 操作
            const tdActions = document.createElement('td');
            tdActions.style.textAlign = 'center';

            const dlBtn = document.createElement('a');
            dlBtn.href = '/api/files/' + f.secure_code + '/download';
            dlBtn.className = 'bkfa-action-btn';
            dlBtn.title = '下載';
            dlBtn.innerHTML = '<i class="fas fa-download"></i>';
            tdActions.appendChild(dlBtn);

            if (!this.config.readonly) {
                const delBtn = document.createElement('button');
                delBtn.type = 'button';
                delBtn.className = 'bkfa-action-btn bkfa-del-btn';
                delBtn.title = '刪除';
                delBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
                delBtn.addEventListener('click', () => this._deleteFile(f.secure_code));
                tdActions.appendChild(delBtn);
            }

            tr.appendChild(tdActions);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        this._updateUploadVisibility();
    }

    // ===== Upload =====

    async _handleFiles(fileList) {
        if (!fileList || fileList.length === 0) return;
        if (this.uploading) return;

        const remaining = this.config.maxFiles - this.files.length;
        if (remaining <= 0) {
            this._showStatus('已達檔案數量上限', true);
            return;
        }

        const toUpload = Array.from(fileList).slice(0, remaining);
        this.uploading = true;
        this._els.uploadBtn.disabled = true;
        this._showStatus('上傳中...', false);

        let successCount = 0;
        let lastError = '';

        for (const file of toUpload) {
            try {
                const formData = new FormData();
                formData.append('file', file);
                formData.append('context_type', this.config.contextType);
                if (this.config.contextId) {
                    formData.append('context_id', this.config.contextId);
                }

                const res = await fetch('/api/files/upload', {
                    method: 'POST',
                    body: formData,
                });
                const data = await res.json();

                if (data.success) {
                    successCount++;
                    if (typeof this.config.onUpload === 'function') {
                        this.config.onUpload(data.data);
                    }
                } else {
                    lastError = data.message || '上傳失敗';
                }
            } catch (e) {
                lastError = e.message || '上傳失敗';
            }
        }

        this.uploading = false;
        this._els.uploadBtn.disabled = false;
        this._els.fileInput.value = '';

        if (successCount > 0) {
            await this.refresh();
            this._showStatus(successCount + ' 個檔案上傳成功', false);
        }
        if (lastError) {
            this._showStatus(lastError, true);
        }
    }

    // ===== Delete =====

    async _deleteFile(fileSc) {
        if (!confirm('確定要刪除此附件？')) return;

        try {
            const res = await fetch('/api/files/' + fileSc, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                if (typeof this.config.onDelete === 'function') {
                    this.config.onDelete(fileSc);
                }
                await this.refresh();
            } else {
                this._showStatus(data.message || '刪除失敗', true);
            }
        } catch (e) {
            this._showStatus(e.message || '刪除失敗', true);
        }
    }

    // ===== Helpers =====

    _showStatus(msg, isError) {
        const el = this._els.status;
        if (!el) return;
        el.textContent = msg;
        el.style.color = isError ? '#dc2626' : '#059669';
        if (msg) {
            clearTimeout(this._statusTimer);
            this._statusTimer = setTimeout(() => { el.textContent = ''; }, 4000);
        }
    }

    _formatSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    }

    _fileIcon(ext) {
        const e = (ext || '').toLowerCase();
        const map = {
            pdf: 'fa-file-pdf', doc: 'fa-file-word', docx: 'fa-file-word',
            xls: 'fa-file-excel', xlsx: 'fa-file-excel', csv: 'fa-file-csv',
            ppt: 'fa-file-powerpoint', pptx: 'fa-file-powerpoint',
            png: 'fa-file-image', jpg: 'fa-file-image', jpeg: 'fa-file-image',
            gif: 'fa-file-image', webp: 'fa-file-image', bmp: 'fa-file-image',
            zip: 'fa-file-archive', '7z': 'fa-file-archive', rar: 'fa-file-archive',
            txt: 'fa-file-alt', rtf: 'fa-file-alt',
        };
        const cls = map[e] || 'fa-file';
        return '<i class="fas ' + cls + '"></i>';
    }

    _escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }
}
