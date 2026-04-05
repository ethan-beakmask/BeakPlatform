/**
 * fc-read-form.js — 閱讀表單 mixin (唯讀檢視、待簽核預覽、測試表單刪除)
 * 由 form-center.js 拆分而來
 */
function fcReadForm() {
    return {
        // --- State ---
        showReadFormModal: false,
        readFormData: null,
        readFormInstance: null,
        loadingReadForm: false,

        // --- Computed ---

        // 測試表單筆數（以 serial_number 前綴 TEST- 為準）
        get testFormCount() {
            return this.historyList.filter(i => (i.serial_number || '').startsWith('TEST-')).length;
        },

        // --- Methods ---

        // 待簽核：唯讀閱讀表單（不取鎖）
        async openPendingReadForm(item) {
            this.readFormData = null;
            this.showReadFormModal = true;
            this.loadingReadForm = true;

            try {
                const res = await fetch(`/api/form-center/pending-tasks/${item.queue_secure_code}`);
                const result = await res.json();

                if (result.success) {
                    this.readFormData = {
                        schema: result.data.form_schema,
                        form_data: result.data.form_data,
                        builder_config: result.data.builder_config,
                        form_name: result.data.form_name,
                        serial_number: result.data.serial_number,
                        form_subject: result.data.form_subject,
                        applicant_name: result.data.applicant_name,
                        approvals: result.data.approvals,
                        form_instance_secure_code: result.data.form_instance_secure_code,
                    };
                    await this.$nextTick();
                    this.renderReadForm();
                } else {
                    this.showToast(result.error || '載入失敗', 'error');
                    this.closeReadForm();
                }
            } catch (e) {
                console.error('載入閱讀表單失敗:', e);
                this.showToast('載入失敗', 'error');
                this.closeReadForm();
            } finally {
                this.loadingReadForm = false;
            }
        },

        async openReadForm(item) {
            this.readFormData = null;
            this.showReadFormModal = true;
            this.loadingReadForm = true;

            try {
                const secureCode = item.secure_code;
                const response = await fetch(`/api/form-center/form-detail/${secureCode}`);
                const result = await response.json();

                if (result.success) {
                    this.readFormData = result.data;
                    await this.$nextTick();
                    this.renderReadForm();
                } else {
                    this.showToast(result.error || '載入失敗', 'error');
                    this.closeReadForm();
                }
            } catch (e) {
                console.error('載入閱讀表單失敗:', e);
                this.showToast('載入失敗', 'error');
                this.closeReadForm();
            } finally {
                this.loadingReadForm = false;
            }
        },

        async renderReadForm() {
            if (!this.readFormData?.schema) {
                const container = document.getElementById('read-form-container');
                if (container) container.innerHTML = '<p style="color: #6b7280; text-align: center;">無表單內容</p>';
                return;
            }
            if (this.readFormInstance) {
                this.readFormInstance.destroy();
                this.readFormInstance = null;
            }
            this.readFormInstance = await this._renderFormReadOnly(
                'read-form-container',
                this.readFormData.schema,
                this.readFormData.form_data,
                this.readFormData.builder_config
            );

            // 初始化附件檢視（唯讀）
            const fiSc = this.readFormData.form_instance_secure_code
                || this.readFormData.secure_code;
            const attEl = document.getElementById('read-form-attachments');
            if (attEl && fiSc && typeof BkFileAttachment !== 'undefined') {
                this._readFormAttachment = new BkFileAttachment(attEl, {
                    contextType: 'form_attachment',
                    contextId: fiSc,
                    readonly: true,
                });
                this._readFormAttachment.init();
            }
        },

        closeReadForm() {
            if (this.readFormInstance) {
                this.readFormInstance.destroy();
                this.readFormInstance = null;
            }
            if (this._readFormAttachment) {
                this._readFormAttachment.destroy();
                this._readFormAttachment = null;
            }
            this.cleanupFormBackground('read-form-container');
            const container = document.getElementById('read-form-container');
            if (container) container.innerHTML = '';

            this.showReadFormModal = false;
            this.readFormData = null;
        },

        // 批量刪除測試表單
        async deleteTestForms() {
            const count = this.testFormCount;
            if (count === 0) return;
            if (!confirm(`確定要刪除 ${count} 筆測試表單嗎？\n\n此操作僅刪除您發起的已結束測試表單（TEST-），不影響正式表單。`)) return;

            try {
                const res = await fetch('/api/form-center/my-test-forms', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast(`已刪除 ${data.deleted_count} 筆測試表單`, 'success');
                    this.loadHistory();
                    this.loadSignedHistory();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                console.error('刪除測試表單失敗:', e);
                this.showToast('刪除失敗，請稍後再試', 'error');
            }
        },
    };
}
