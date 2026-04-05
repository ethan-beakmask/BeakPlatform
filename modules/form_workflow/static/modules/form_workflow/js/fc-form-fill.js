/**
 * fc-form-fill.js — 表單填寫 mixin (開啟、渲染、送出)
 * 由 form-center.js 拆分而來
 */
function fcFormFill() {
    return {
        // --- State ---
        showFillModal: false,
        selectedForm: null,
        formSchema: null,
        formInstance: null,
        formSubject: '',
        subjectError: '',
        loadingFormSchema: false,
        submitting: false,
        _fillAttachment: null,

        // --- Methods ---

        async openFormFill(form) {
            this.selectedForm = form;
            this.formSchema = null;
            this.showFillModal = true;
            this.loadingFormSchema = true;

            try {
                // 根據來源決定 API 參數
                const source = form._source || 'published';
                const url = `/api/form-center/forms/${form.secure_code}?source=${source}`;
                const res = await fetch(url);
                const data = await res.json();

                if (data.success && data.data.schema) {
                    this.formSchema = data.data.schema;
                    this.selectedForm = { ...this.selectedForm, ...data.data };

                    await this.$nextTick();
                    this.renderFillForm();
                    this._initFillAttachment();
                }
            } catch (e) {
                console.error('載入表單結構失敗:', e);
            } finally {
                this.loadingFormSchema = false;
            }
        },

        _initFillAttachment() {
            if (this._fillAttachment) {
                this._fillAttachment.destroy();
                this._fillAttachment = null;
            }
            const attEl = document.getElementById('fill-form-attachments');
            if (attEl && typeof BkFileAttachment !== 'undefined') {
                this._fillAttachment = new BkFileAttachment(attEl, {
                    contextType: 'form_attachment',
                    deferred: true,
                    allowedExts: ['pdf','doc','docx','xls','xlsx','ppt','pptx',
                                  'odt','ods','csv','txt','rtf',
                                  'png','jpg','jpeg','gif','webp','bmp',
                                  'zip','7z','rar'],
                    maxFileSize: 50 * 1024 * 1024,
                });
                this._fillAttachment.init();
            }
        },

        async renderFillForm() {
            const formioTarget = document.getElementById('form-fill-formio');
            if (!formioTarget || !this.formSchema) return;

            try {
                // 銷毀舊實例
                if (this.formInstance) {
                    this.formInstance.destroy();
                    this.formInstance = null;
                }

                // 補丁 file component storage
                if (window.BkFileProvider) BkFileProvider.patchSchema(this.formSchema);

                // 渲染 Form.io 到子容器
                this.formInstance = await Formio.createForm(formioTarget, this.formSchema, {
                    readOnly: false
                });

                // 套用底圖和寬度到外層容器
                this.applyFormBackground('form-fill-container', this.selectedForm?.builder_config);

                console.log('表單渲染成功');
            } catch (e) {
                console.error('表單渲染失敗:', e);
                formioTarget.innerHTML = '<p style="color: #dc2626; text-align: center;">表單載入失敗</p>';
            }
        },

        closeFillModal() {
            if (this.formInstance) {
                this.formInstance.destroy();
                this.formInstance = null;
            }
            this.cleanupFormBackground('form-fill-container');
            const formioTarget = document.getElementById('form-fill-formio');
            if (formioTarget) formioTarget.innerHTML = '';

            this.showFillModal = false;
            this.selectedForm = null;
            this.formSchema = null;
            this.formSubject = '';
            this.subjectError = '';
            if (this._fillAttachment) {
                this._fillAttachment.destroy();
                this._fillAttachment = null;
            }
        },

        async submitForm() {
            if (this.submitting || !this.formInstance) return;

            // 驗證主旨
            this.subjectError = '';
            const subject = (this.formSubject || '').trim();
            if (!subject) {
                this.subjectError = '請填寫表單主旨';
                document.getElementById('form-subject-input')?.focus();
                return;
            }

            this.submitting = true;

            try {
                // 取得表單資料
                const submission = this.formInstance.submission || {};
                const formData = submission.data || {};

                // 準備請求資料
                const payload = { form_data: formData, subject: subject };

                // 根據來源決定使用哪個參數
                if (this.selectedForm._source === 'mapping' || this.selectedForm._status === 'test') {
                    payload.mapping_secure_code = this.selectedForm.mapping_secure_code;
                } else {
                    payload.published_secure_code = this.selectedForm.secure_code;
                }

                const res = await fetch('/api/form-center/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (data.success) {
                    // 表單建立成功後上傳暫存附件
                    const fiSc = data.data?.form_instance_secure_code;
                    if (fiSc && this._fillAttachment && this._fillAttachment.getPendingCount() > 0) {
                        const result = await this._fillAttachment.flush(fiSc);
                        if (result.errors.length > 0) {
                            this.showToast(result.errors.join('\n'), 'error');
                        }
                    }
                    this.showToast(data.message || '表單已送出');
                    this.closeFillModal();
                    this.loadTracking();
                } else {
                    this.showToast(data.error || '送出失敗', 'error');
                }
            } catch (e) {
                this.showToast('送出失敗: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },
    };
}
