/**
 * fc-approval.js — 單筆簽核 mixin (取鎖、渲染、送出、倒數計時)
 * 由 form-center.js 拆分而來
 */
function fcApproval() {
    return {
        // --- State ---
        showApprovalModal: false,
        currentApproval: null,
        approvalFormInstance: null,
        selectedEdges: [],
        approvalComment: '',
        selectedOptionValue: null,   // 自定義決策選項的 value（送後端用）
        selectedOptionId: null,      // 自定義決策選項的 id（UI 高亮用）
        loadingApproval: false,
        submittingApproval: false,
        approvalLockTimer: null,
        approvalLockRemaining: 0,
        approvalLockInterval: null,
        _beforeUnloadHandler: null,

        // --- Computed ---
        get approvalCountdownText() {
            const m = Math.floor(this.approvalLockRemaining / 60);
            const s = this.approvalLockRemaining % 60;
            return `${m}:${String(s).padStart(2, '0')}`;
        },

        /**
         * 取得可見的決策選項
         */
        get visibleDecisionOptions() {
            if (!this.currentApproval?.use_custom_decisions) return [];
            const paths = this.currentApproval?.available_paths || [];
            return paths.filter(opt => this.isOptionVisible(opt));
        },

        // --- Methods ---

        // 簽核（先取鎖再開表單）
        async openApprovalModal(item) {
            this.currentApproval = null;
            this.selectedEdges = [];
            this.approvalComment = '';
            this.selectedOptionValue = null;
            this.selectedOptionId = null;
            this.loadingApproval = true;

            try {
                // Step 1: 取得簽核鎖定
                const lockRes = await fetch(`/bp/api/form-center/pending-tasks/${item.queue_secure_code}/lock`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const lockData = await lockRes.json();

                if (!lockData.success) {
                    this.showToast(lockData.error || '無法取得簽核鎖定', 'error');
                    this.loadingApproval = false;
                    return;
                }

                // Step 2: 取得任務詳情
                this.showApprovalModal = true;
                const res = await fetch(`/bp/api/form-center/pending-tasks/${item.queue_secure_code}`);
                const data = await res.json();

                if (data.success) {
                    this.currentApproval = data.data;

                    // Step 3: 啟動倒數計時
                    this._startApprovalCountdown(lockData.remaining_seconds || 600);

                    // Step 4: 註冊 beforeunload 釋放鎖
                    const queueCode = item.queue_secure_code;
                    this._beforeUnloadHandler = () => {
                        fetch(`/bp/api/form-center/pending-tasks/${queueCode}/lock`, {
                            method: 'DELETE',
                            keepalive: true
                        }).catch(() => {});
                    };
                    window.addEventListener('beforeunload', this._beforeUnloadHandler);

                    await this.$nextTick();
                    this.renderApprovalForm();
                } else {
                    this.showToast(data.error || '載入失敗', 'error');
                    this.closeApprovalModal();
                }
            } catch (e) {
                console.error('載入簽核詳情失敗:', e);
                this.showToast('載入失敗', 'error');
                this.closeApprovalModal();
            } finally {
                this.loadingApproval = false;
            }
        },

        _startApprovalCountdown(seconds) {
            this._clearApprovalCountdown();
            this.approvalLockRemaining = seconds;
            this.approvalLockInterval = setInterval(() => {
                this.approvalLockRemaining--;
                if (this.approvalLockRemaining <= 0) {
                    this._clearApprovalCountdown();
                    this.showToast('簽核逾時，表單已自動關閉', 'warning');
                    this.closeApprovalModal();
                    this.loadPendingApprovals();
                }
            }, 1000);
        },

        _clearApprovalCountdown() {
            if (this.approvalLockInterval) {
                clearInterval(this.approvalLockInterval);
                this.approvalLockInterval = null;
            }
            this.approvalLockRemaining = 0;
        },

        async renderApprovalForm() {
            const container = document.getElementById('approval-form-container');
            if (!container || !this.currentApproval) return;

            const schema = this.currentApproval.form_schema;
            const formData = this.currentApproval.form_data;
            const hasEditable = this.currentApproval.has_editable_fields;

            if (!schema) {
                container.innerHTML = '<p style="color: #6b7280; text-align: center;">無表單內容</p>';
                return;
            }

            try {
                if (this.approvalFormInstance) {
                    this.approvalFormInstance.destroy();
                    this.approvalFormInstance = null;
                }

                // 如果有可編輯欄位，不使用 readOnly 模式
                // 後端已根據 field_permissions 設好各欄位的 disabled 屬性
                const formOptions = hasEditable
                    ? { noDefaultSubmitButton: true }
                    : { readOnly: true, viewAsHtml: false };

                // 補丁 file component storage
                if (window.BkFileProvider) BkFileProvider.patchSchema(schema);

                this.approvalFormInstance = await Formio.createForm(container, schema, formOptions);

                if (formData) {
                    this.approvalFormInstance.submission = { data: formData };
                }

                // 動態欄位權限覆蓋（來自 input_variables 評估結果）
                const fieldOverrides = this.currentApproval?.input_variable_results?.field_permission_overrides;
                if (fieldOverrides && this.approvalFormInstance) {
                    this._applyFieldPermissionOverrides(this.approvalFormInstance, fieldOverrides);
                }

                // 套用底圖和寬度
                this.applyFormBackground('approval-form-container', this.currentApproval?.builder_config);
            } catch (e) {
                console.error('簽核表單渲染失敗:', e);
                container.innerHTML = '<p style="color: #dc2626; text-align: center;">表單載入失敗</p>';
            }

            // 初始化附件（deferred 模式，簽核成功後才上傳）
            const fiSc = this.currentApproval?.form_instance_secure_code;
            const attEl = document.getElementById('approval-form-attachments');
            if (attEl && fiSc && typeof BkFileAttachment !== 'undefined') {
                this._approvalAttachment = new BkFileAttachment(attEl, {
                    contextType: 'form_attachment',
                    contextId: fiSc,
                    deferred: true,
                    allowedExts: ['pdf','doc','docx','xls','xlsx','ppt','pptx',
                                  'odt','ods','csv','txt','rtf',
                                  'png','jpg','jpeg','gif','webp','bmp',
                                  'zip','7z','rar'],
                    maxFileSize: 50 * 1024 * 1024,
                    currentUserSc: this.currentUserSc || '',
                    nodeId: this.currentApproval?.node_id || '',
                });
                this._approvalAttachment.init();
            }
        },

        closeApprovalModal() {
            // deferred 模式不需 revert-deletes，暫存檔案未上傳直接丟棄

            // 釋放鎖定（best-effort）
            if (this.currentApproval?.queue_secure_code) {
                fetch(`/bp/api/form-center/pending-tasks/${this.currentApproval.queue_secure_code}/lock`, {
                    method: 'DELETE'
                }).catch(() => {});
            }

            // 清除倒數計時
            this._clearApprovalCountdown();

            // 移除 beforeunload
            if (this._beforeUnloadHandler) {
                window.removeEventListener('beforeunload', this._beforeUnloadHandler);
                this._beforeUnloadHandler = null;
            }

            if (this.approvalFormInstance) {
                this.approvalFormInstance.destroy();
                this.approvalFormInstance = null;
            }
            if (this._approvalAttachment) {
                this._approvalAttachment.destroy();
                this._approvalAttachment = null;
            }
            this.cleanupFormBackground('approval-form-container');
            const container = document.getElementById('approval-form-container');
            if (container) container.innerHTML = '';

            this.showApprovalModal = false;
            this.currentApproval = null;
            this.selectedEdges = [];
            this.approvalComment = '';
            this.selectedOptionValue = null;
            this.selectedOptionId = null;
        },

        toggleEdgeSelection(edgeId) {
            const idx = this.selectedEdges.indexOf(edgeId);
            if (idx === -1) {
                this.selectedEdges.push(edgeId);
            } else {
                this.selectedEdges.splice(idx, 1);
            }
        },

        /**
         * 選擇自定義決策選項
         */
        selectDecisionOption(option) {
            if (!option) return;
            this.selectedOptionId = option.id;
            this.selectedOptionValue = option.value;
            this.selectedEdges = option.target_edges || [];
        },

        /**
         * 判斷決策選項是否可見（根據 input_variable_results）
         */
        isOptionVisible(option) {
            if (!this.currentApproval) return true;
            const hiddenIds = this.currentApproval.input_variable_results?.hidden_option_ids || [];
            return !hiddenIds.includes(option.id);
        },

        async submitApproval() {
            const useCustom = this.currentApproval?.use_custom_decisions || false;

            // 驗證選擇
            if (useCustom) {
                if (this.selectedOptionValue === null) {
                    this.showToast('請選擇一個決策選項', 'warning');
                    return;
                }
            } else {
                if (this.selectedEdges.length === 0) {
                    this.showToast('請選擇後續動作', 'warning');
                    return;
                }
            }

            if (this.submittingApproval) return;

            const minLen = this.currentApproval?.min_comment_length || 0;
            if (minLen > 0 && this.approvalComment.trim().length < minLen) {
                this.showToast(`簽核意見至少需要 ${minLen} 字`, 'warning');
                return;
            }

            this.submittingApproval = true;

            try {
                // 決定 decision: 如果 target_edges 為空且 style=danger → rejected
                let decision = 'approved';
                if (useCustom && this.selectedEdges.length === 0) {
                    // 查找選中的 option
                    const paths = this.currentApproval?.available_paths || [];
                    const selectedOpt = paths.find(p => p.value === this.selectedOptionValue);
                    if (selectedOpt && selectedOpt.style === 'danger') {
                        decision = 'rejected';
                    }
                }

                const payload = {
                    decision: decision,
                    selected_path: useCustom ? null : this.selectedEdges[0],
                    selected_edges: useCustom ? this.selectedEdges : null,
                    selected_option_value: this.selectedOptionValue,
                    comment: this.approvalComment
                };

                if (this.currentApproval?.has_editable_fields && this.approvalFormInstance) {
                    payload.form_data = this.approvalFormInstance.submission.data;
                }

                const res = await fetch(`/bp/api/form-center/pending-tasks/${this.currentApproval.queue_secure_code}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (data.success) {
                    this._clearApprovalCountdown();  // 成功送出，停止倒數

                    // 簽核成功後上傳暫存附件
                    const approvalFiSc = this.currentApproval?.form_instance_secure_code;
                    if (approvalFiSc && this._approvalAttachment && this._approvalAttachment.getPendingCount() > 0) {
                        const flushResult = await this._approvalAttachment.flush(approvalFiSc);
                        if (flushResult.errors.length > 0) {
                            this.showToast(flushResult.errors.join('\n'), 'error');
                        }
                    }

                    this.showToast('簽核完成');
                    // 不走 closeApprovalModal（避免重複 DELETE lock），直接清理 UI
                    if (this._beforeUnloadHandler) {
                        window.removeEventListener('beforeunload', this._beforeUnloadHandler);
                        this._beforeUnloadHandler = null;
                    }
                    if (this.approvalFormInstance) {
                        this.approvalFormInstance.destroy();
                        this.approvalFormInstance = null;
                    }
                    if (this._approvalAttachment) {
                        this._approvalAttachment.destroy();
                        this._approvalAttachment = null;
                    }
                    this.cleanupFormBackground('approval-form-container');
                    const container = document.getElementById('approval-form-container');
                    if (container) container.innerHTML = '';
                    this.showApprovalModal = false;
                    this.currentApproval = null;
                    this.selectedEdges = [];
                    this.approvalComment = '';
                    this.selectedOptionValue = null;
                    this.selectedOptionId = null;
                    this.loadPendingApprovals();
                    this.loadTracking();
                } else {
                    // 處理特定錯誤碼
                    if (data.code === 'LOCK_EXPIRED') {
                        this._clearApprovalCountdown();
                        this.showToast('簽核逾時，請重新開啟', 'error');
                        this.closeApprovalModal();
                        this.loadPendingApprovals();
                    } else if (data.code === 'LOCKED') {
                        this.showToast(data.error || '此表單正由他人簽核中', 'error');
                        this.closeApprovalModal();
                        this.loadPendingApprovals();
                    } else if (data.code === 'DUPLICATE') {
                        this.showToast('您已簽核過此節點', 'error');
                        this.closeApprovalModal();
                        this.loadPendingApprovals();
                    } else {
                        this.showToast(data.error || '簽核失敗', 'error');
                    }
                }
            } catch (e) {
                this.showToast('簽核失敗: ' + e.message, 'error');
            } finally {
                this.submittingApproval = false;
            }
        },
    };
}
