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
 *       allowedExts: ['pdf','doc','docx','xlsx'],  // 前端副檔名白名單
 *       maxFileSize: 50 * 1024 * 1024,             // 前端檔案大小上限 (bytes)
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
            allowedExts: [],
            maxFileSize: 0,
            currentUserSc: '',
            nodeId: '',
            onUpload: null,
            onDelete: null,
        }, config);

        // 正規化副檔名：全小寫、去點
        if (this.config.allowedExts.length > 0) {
            this.config.allowedExts = this.config.allowedExts.map(
                e => e.replace(/^\./, '').toLowerCase()
            );
        }

        this.files = [];
        this.uploading = false;
        this._els = {};
        this._modalId = 'bkfa-modal-' + Math.random().toString(36).slice(2, 8);
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
        // 移除 modal
        const modal = document.getElementById(this._modalId);
        if (modal) modal.remove();
    }

    // ===== Render =====

    _render() {
        this.container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'bkfa-root';

        // 上傳區（含拖拉）
        const uploadArea = document.createElement('div');
        uploadArea.className = 'bkfa-upload-area';

        const dropZone = document.createElement('div');
        dropZone.className = 'bkfa-dropzone';

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.multiple = true;
        fileInput.style.display = 'none';
        fileInput.addEventListener('change', (e) => this._handleFiles(e.target.files));

        // 拖拉區內容（圖示用 Font Awesome，確保各頁面皆可顯示）
        const dropContent = document.createElement('div');
        dropContent.className = 'bkfa-dropzone-content';
        dropContent.innerHTML =
            '<i class="fas fa-cloud-upload-alt bkfa-dropzone-icon"></i>'
            + '<span class="bkfa-dropzone-text">拖拉檔案至此，或</span>';

        const uploadBtn = document.createElement('button');
        uploadBtn.type = 'button';
        uploadBtn.className = 'bkfa-upload-btn';
        uploadBtn.innerHTML = '<i class="fas fa-paperclip"></i> 選擇檔案';
        uploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });
        dropContent.appendChild(uploadBtn);

        // 副檔名與大小提示
        if (this.config.allowedExts.length > 0 || this.config.maxFileSize > 0) {
            const hint = document.createElement('div');
            hint.className = 'bkfa-hint';
            const parts = [];
            if (this.config.allowedExts.length > 0) {
                parts.push(this.config.allowedExts.map(e => '.' + e).join(', '));
            }
            if (this.config.maxFileSize > 0) {
                parts.push('上限 ' + this._formatSize(this.config.maxFileSize));
            }
            hint.textContent = parts.join(' | ');
            dropContent.appendChild(hint);
        }

        dropZone.appendChild(fileInput);
        dropZone.appendChild(dropContent);

        // 點擊整個 dropzone 也觸發選擇檔案
        dropZone.addEventListener('click', (e) => {
            if (e.target !== uploadBtn && !uploadBtn.contains(e.target)) {
                fileInput.click();
            }
        });

        const status = document.createElement('span');
        status.className = 'bkfa-status';

        uploadArea.appendChild(dropZone);
        uploadArea.appendChild(status);

        // 拖拉事件（用 counter 避免子元素 dragleave 誤觸）
        let dragCounter = 0;
        dropZone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter++;
            dropZone.classList.add('bkfa-dropzone-active');
        });
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter--;
            if (dragCounter <= 0) {
                dragCounter = 0;
                dropZone.classList.remove('bkfa-dropzone-active');
            }
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dragCounter = 0;
            dropZone.classList.remove('bkfa-dropzone-active');
            if (e.dataTransfer && e.dataTransfer.files.length > 0) {
                this._handleFiles(e.dataTransfer.files);
            }
        });

        // 列表區
        const listArea = document.createElement('div');
        listArea.className = 'bkfa-list';

        root.appendChild(uploadArea);
        root.appendChild(listArea);
        this.container.appendChild(root);

        this._els = { root, uploadArea, dropZone, uploadBtn, fileInput, status, listArea };
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

            const isPending = f.status === 'pending_delete';

            // 名稱
            const tdName = document.createElement('td');
            tdName.className = 'bkfa-filename';
            const icon = this._fileIcon(f.file_ext);
            tdName.innerHTML = icon + ' ' + this._escHtml(f.original_name);
            if (isPending) {
                tdName.style.textDecoration = 'line-through';
                tdName.style.opacity = '0.5';
            }
            tr.appendChild(tdName);

            // 大小
            const tdSize = document.createElement('td');
            tdSize.style.textAlign = 'right';
            tdSize.textContent = this._formatSize(f.file_size);
            if (isPending) {
                tdSize.style.textDecoration = 'line-through';
                tdSize.style.opacity = '0.5';
            }
            tr.appendChild(tdSize);

            // 操作
            const tdActions = document.createElement('td');
            tdActions.style.textAlign = 'center';

            if (!isPending) {
                const dlBtn = document.createElement('button');
                dlBtn.type = 'button';
                dlBtn.className = 'bkfa-action-btn';
                dlBtn.title = '下載';
                dlBtn.innerHTML = '<i class="ri-download-2-line"></i>';
                dlBtn.addEventListener('click', () => this._downloadFile(f.secure_code));
                tdActions.appendChild(dlBtn);
            }

            if (!this.config.readonly && !isPending) {
                // 只有上傳者本人可刪除
                const canDelete = !this.config.currentUserSc || !f.uploader_sc
                    || f.uploader_sc === this.config.currentUserSc;
                if (canDelete) {
                    const delBtn = document.createElement('button');
                    delBtn.type = 'button';
                    delBtn.className = 'bkfa-action-btn bkfa-del-btn';
                    delBtn.title = '刪除';
                    delBtn.innerHTML = '<i class="ri-delete-bin-line"></i>';
                    delBtn.addEventListener('click', () => this._deleteFile(f.secure_code));
                    tdActions.appendChild(delBtn);
                }
            }

            if (isPending) {
                const tag = document.createElement('span');
                tag.textContent = '待確認刪除';
                tag.style.cssText = 'font-size:10px;color:#9ca3af;';
                tdActions.appendChild(tag);
            }

            tr.appendChild(tdActions);
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        this._updateUploadVisibility();
    }

    // ===== Validation =====

    _validateFiles(fileList) {
        const errors = [];
        const allowed = this.config.allowedExts;
        const maxSize = this.config.maxFileSize;

        for (const file of fileList) {
            const name = file.name || '';
            const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';

            if (allowed.length > 0 && !allowed.includes(ext)) {
                errors.push({
                    name: name,
                    reason: '不支援的檔案格式 (.' + (ext || '無副檔名') + ')',
                });
            } else if (maxSize > 0 && file.size > maxSize) {
                errors.push({
                    name: name,
                    reason: '檔案過大 (' + this._formatSize(file.size) + ')，上限 ' + this._formatSize(maxSize),
                });
            }
        }

        return errors;
    }

    // ===== Upload =====

    async _handleFiles(fileList) {
        if (!fileList || fileList.length === 0) return;
        if (this.uploading) return;

        const remaining = this.config.maxFiles - this.files.length;
        if (remaining <= 0) {
            this._showModal('上傳限制', '已達檔案數量上限 (' + this.config.maxFiles + ' 個)');
            return;
        }

        const toUpload = Array.from(fileList).slice(0, remaining);

        // 前端驗證：副檔名 + 檔案大小
        const valErrors = this._validateFiles(toUpload);
        if (valErrors.length > 0) {
            const lines = valErrors.map(
                e => '<li><strong>' + this._escHtml(e.name) + '</strong>: ' + this._escHtml(e.reason) + '</li>'
            ).join('');

            let detail = '';
            const allowed = this.config.allowedExts;
            const maxSize = this.config.maxFileSize;
            if (allowed.length > 0) {
                detail += '<div style="margin-top:8px;font-size:12px;color:#6b7280;">允許格式: ' + allowed.map(e => '.' + e).join(', ') + '</div>';
            }
            if (maxSize > 0) {
                detail += '<div style="font-size:12px;color:#6b7280;">大小上限: ' + this._formatSize(maxSize) + '</div>';
            }

            this._showModal('附件上傳失敗', '<ul style="margin-bottom:0;">' + lines + '</ul>' + detail);
            this._els.fileInput.value = '';
            return;
        }

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
                if (this.config.nodeId) {
                    formData.append('node_id', this.config.nodeId);
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
            this._showModal('上傳失敗', this._escHtml(lastError));
        }
    }

    // ===== Download (one-time token) =====

    async _downloadFile(fileSc) {
        try {
            const res = await fetch('/api/files/' + fileSc + '/download-token', {
                method: 'POST',
            });
            const data = await res.json();
            if (data.success && data.url) {
                window.location.href = data.url;
            } else {
                this._showModal('下載失敗', this._escHtml(data.message || '無法取得下載連結'));
            }
        } catch (e) {
            this._showModal('下載失敗', this._escHtml(e.message || '網路錯誤'));
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

    // ===== Modal =====

    _showModal(title, bodyHtml) {
        // 複用或建立 backdrop + dialog
        let backdrop = document.getElementById(this._modalId + '-backdrop');
        let dialog = document.getElementById(this._modalId);

        if (!dialog) {
            // backdrop
            backdrop = document.createElement('div');
            backdrop.id = this._modalId + '-backdrop';
            backdrop.className = 'bkfa-modal-backdrop';

            // dialog
            dialog = document.createElement('div');
            dialog.id = this._modalId;
            dialog.className = 'bkfa-modal';
            dialog.innerHTML =
                '<div class="bkfa-modal-dialog">'
                + '<div class="bkfa-modal-content">'
                +   '<div class="bkfa-modal-header">'
                +     '<h5 class="bkfa-modal-title"></h5>'
                +     '<button type="button" class="bkfa-modal-close">&times;</button>'
                +   '</div>'
                +   '<div class="bkfa-modal-body"></div>'
                +   '<div class="bkfa-modal-footer">'
                +     '<button type="button" class="bkfa-modal-btn">關閉</button>'
                +   '</div>'
                + '</div>'
                + '</div>';

            document.body.appendChild(backdrop);
            document.body.appendChild(dialog);

            // 關閉事件
            const close = () => {
                dialog.style.display = 'none';
                backdrop.style.display = 'none';
            };
            dialog.querySelector('.bkfa-modal-close').addEventListener('click', close);
            dialog.querySelector('.bkfa-modal-btn').addEventListener('click', close);
        }

        dialog.querySelector('.bkfa-modal-title').textContent = title;
        dialog.querySelector('.bkfa-modal-body').innerHTML = bodyHtml;
        backdrop.style.display = 'block';
        dialog.style.display = 'flex';
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
            pdf: 'ri-file-pdf-2-line', doc: 'ri-file-word-line', docx: 'ri-file-word-line',
            xls: 'ri-file-excel-line', xlsx: 'ri-file-excel-line', csv: 'ri-file-list-2-line',
            ppt: 'ri-file-ppt-line', pptx: 'ri-file-ppt-line',
            png: 'ri-file-image-line', jpg: 'ri-file-image-line', jpeg: 'ri-file-image-line',
            gif: 'ri-file-image-line', webp: 'ri-file-image-line', bmp: 'ri-file-image-line',
            zip: 'ri-file-zip-line', '7z': 'ri-file-zip-line', rar: 'ri-file-zip-line',
            txt: 'ri-file-text-line', rtf: 'ri-file-text-line',
        };
        const cls = map[e] || 'ri-file-line';
        return '<i class="' + cls + '"></i>';
    }

    _escHtml(s) {
        const d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }
}
