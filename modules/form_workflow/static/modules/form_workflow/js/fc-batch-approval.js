/**
 * fc-batch-approval.js — 批次簽核 mixin
 * 由 form-center.js 拆分而來
 */
function fcBatchApproval() {
    return {
        // --- State ---
        batchSelected: [],          // 已勾選的 queue_secure_code 列表
        batchKey: null,             // 目前鎖定的批次鍵 'published_sc|node_id'
        showBatchApprovalModal: false,
        batchApprovalEdges: [],
        batchApprovalComment: '',
        batchApprovalOptionValue: null,
        batchApprovalOptionId: null,
        submittingBatchApproval: false,
        batchApprovalInfo: null,    // 批次簽核的節點資訊（從第一筆取得）
        loadingBatchInfo: false,

        // --- Computed ---

        get batchKeyOf() {
            // 回傳函式：取得某 item 的 batch key
            return (item) => (item.published_secure_code || '') + '|' + (item.node_id || '');
        },

        get batchSelectedCount() {
            return this.batchSelected.length;
        },

        /**
         * 判斷全選 checkbox 狀態
         */
        get batchAllChecked() {
            const source = this.viewMode === 'list' ? this.pagedListData : this.pagedPendingApprovals;
            if (source.length === 0 || this.batchSelected.length === 0) return false;
            const compatible = source.filter(i =>
                !(i.is_locked && !i.locked_by_self) && this.isBatchCompatible(i)
            );
            return compatible.length > 0 && compatible.every(i => this.batchSelected.includes(i.queue_secure_code));
        },

        /**
         * 取得批次簽核中選取項目的摘要資訊
         */
        get batchSelectedItems() {
            return this.pendingApprovals.filter(i => this.batchSelected.includes(i.queue_secure_code));
        },

        // --- Methods ---

        /**
         * 判斷 item 是否可被勾選（與目前已勾選的 batch key 相容）
         */
        isBatchCompatible(item) {
            if (!this.batchKey) return true;
            return this.batchKeyOf(item) === this.batchKey;
        },

        /**
         * 判斷 item 是否已被勾選
         */
        isBatchChecked(item) {
            return this.batchSelected.includes(item.queue_secure_code);
        },

        /**
         * 切換單筆勾選
         */
        batchToggle(item) {
            if (item.is_locked && !item.locked_by_self) return;
            const idx = this.batchSelected.indexOf(item.queue_secure_code);
            if (idx >= 0) {
                this.batchSelected.splice(idx, 1);
                if (this.batchSelected.length === 0) this.batchKey = null;
            } else {
                const key = this.batchKeyOf(item);
                if (this.batchKey && this.batchKey !== key) return; // 不相容
                if (!this.batchKey) this.batchKey = key;
                this.batchSelected.push(item.queue_secure_code);
            }
        },

        /**
         * 全選（僅選取與目前 batch key 相容的項目；若無 key 則以第一筆為準）
         */
        batchSelectAll() {
            const source = this.viewMode === 'list' ? this.pagedListData : this.pagedPendingApprovals;
            const selectable = source.filter(i => !(i.is_locked && !i.locked_by_self));
            if (selectable.length === 0) return;

            // 如果已全選，清空
            const allCodes = selectable.filter(i => this.isBatchCompatible(i)).map(i => i.queue_secure_code);
            if (allCodes.length > 0 && allCodes.every(c => this.batchSelected.includes(c))) {
                this.batchSelected = [];
                this.batchKey = null;
                return;
            }

            // 如果沒有 batch key，以第一個可選 item 的 key 為準
            if (!this.batchKey) {
                this.batchKey = this.batchKeyOf(selectable[0]);
            }
            const compatible = selectable.filter(i => this.batchKeyOf(i) === this.batchKey);
            this.batchSelected = compatible.map(i => i.queue_secure_code);
        },

        /**
         * 反選（在相容項目內反選）
         */
        batchInvertSelection() {
            const source = this.viewMode === 'list' ? this.pagedListData : this.pagedPendingApprovals;
            const selectable = source.filter(i => !(i.is_locked && !i.locked_by_self));

            if (!this.batchKey && selectable.length > 0) {
                // 尚無 key → 全選第一個 key
                this.batchKey = this.batchKeyOf(selectable[0]);
            }
            if (!this.batchKey) return;

            const compatible = selectable.filter(i => this.batchKeyOf(i) === this.batchKey);
            const newSelection = compatible
                .filter(i => !this.batchSelected.includes(i.queue_secure_code))
                .map(i => i.queue_secure_code);

            this.batchSelected = newSelection;
            if (this.batchSelected.length === 0) this.batchKey = null;
        },

        /**
         * 清空批次選取
         */
        batchClearSelection() {
            this.batchSelected = [];
            this.batchKey = null;
        },

        /**
         * 開啟批次簽核 Modal
         */
        async openBatchApprovalModal() {
            if (this.batchSelected.length < 1) return;

            this.batchApprovalEdges = [];
            this.batchApprovalComment = '';
            this.batchApprovalOptionValue = null;
            this.batchApprovalOptionId = null;
            this.batchApprovalInfo = null;
            this.loadingBatchInfo = true;
            this.showBatchApprovalModal = true;

            try {
                // 用第一筆取得節點資訊（因為同 batch key，所有項目的選項一致）
                const firstQsc = this.batchSelected[0];
                const res = await fetch(`/api/form-center/pending-tasks/${firstQsc}`);
                const data = await res.json();
                if (data.success) {
                    this.batchApprovalInfo = data.data;
                } else {
                    this.showToast(data.error || '載入簽核資訊失敗', 'error');
                    this.showBatchApprovalModal = false;
                }
            } catch (e) {
                this.showToast('載入簽核資訊失敗', 'error');
                this.showBatchApprovalModal = false;
            } finally {
                this.loadingBatchInfo = false;
            }
        },

        closeBatchApprovalModal() {
            this.showBatchApprovalModal = false;
            this.batchApprovalInfo = null;
        },

        /**
         * 批次簽核選擇決策選項
         */
        selectBatchDecisionOption(option) {
            this.batchApprovalOptionValue = option.value;
            this.batchApprovalOptionId = option.id;
            // 映射的 edges
            this.batchApprovalEdges = option.target_edges || [];
        },

        /**
         * 提交批次簽核
         */
        async submitBatchApproval() {
            const info = this.batchApprovalInfo;
            if (!info) return;

            const useCustom = info.use_custom_decisions || false;

            if (useCustom) {
                if (this.batchApprovalOptionValue === null) {
                    this.showToast('請選擇一個決策選項', 'warning');
                    return;
                }
            } else {
                if (this.batchApprovalEdges.length === 0) {
                    this.showToast('請選擇後續動作', 'warning');
                    return;
                }
            }

            const minLen = info.min_comment_length || 0;
            if (minLen > 0 && this.batchApprovalComment.trim().length < minLen) {
                this.showToast(`簽核意見至少需要 ${minLen} 字`, 'warning');
                return;
            }

            if (this.submittingBatchApproval) return;
            this.submittingBatchApproval = true;

            try {
                let decision = 'approved';
                if (useCustom && this.batchApprovalEdges.length === 0) {
                    const paths = info.available_paths || [];
                    const selectedOpt = paths.find(p => p.value === this.batchApprovalOptionValue);
                    if (selectedOpt && selectedOpt.style === 'danger') {
                        decision = 'rejected';
                    }
                }

                const payload = {
                    queue_secure_codes: this.batchSelected,
                    decision: decision,
                    selected_path: useCustom ? null : this.batchApprovalEdges[0],
                    selected_edges: useCustom ? this.batchApprovalEdges : null,
                    selected_option_value: this.batchApprovalOptionValue,
                    comment: this.batchApprovalComment
                };

                const res = await fetch('/api/form-center/pending-tasks/batch-approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (data.success) {
                    const msg = data.message || `成功 ${data.success_count} 筆`;
                    this.showToast(msg, data.fail_count > 0 ? 'warning' : 'success');
                    this.showBatchApprovalModal = false;
                    this.batchClearSelection();
                    this.loadPendingApprovals();
                    this.loadTracking();
                } else {
                    this.showToast(data.error || '批次簽核失敗', 'error');
                }
            } catch (e) {
                this.showToast('批次簽核失敗: ' + e.message, 'error');
            } finally {
                this.submittingBatchApproval = false;
            }
        },
    };
}
