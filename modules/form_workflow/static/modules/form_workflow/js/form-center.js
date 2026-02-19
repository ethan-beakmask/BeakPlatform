/**
 * form_center.html — Alpine.js Manager
 * Window Bridge: reads window.__USER_TIMEZONE
 */
function formCenterManager() {
    return {
        // 資料
        availableForms: [],
        parentCategories: [],  // 樹狀分類 [{...parent, children: [...]}]
        pendingApprovals: [],
        trackingList: [],
        signedList: [],
        historyList: [],
        signedHistoryList: [],

        // 分類選擇（二層）
        selectedParent: null,   // 選中的父分類 secure_code
        selectedChild: null,    // 選中的子分類 secure_code

        // 載入狀態
        loadingForms: true,
        loadingCategories: true,
        loadingPending: true,
        loadingTracking: true,
        loadingSigned: true,
        loadingHistory: true,
        loadingSignedHistory: true,

        // 檢視模式: 'dashboard' = 總覽, 'list' = 清單展開
        viewMode: 'dashboard',
        listTab: 'pending',     // 'pending' | 'tracking' | 'history'
        listSubTab: 'mine',     // 子頁籤: 'mine' | 'signed'
        listPage: 1,
        listPageSize: 30,

        // 頁籤
        trackingTab: 'mine',
        historyTab: 'mine',

        // 分頁
        pendingPage: 1, pendingPageSize: 5,
        trackingPage: 1, trackingPageSize: 5,
        signedPage: 1, signedPageSize: 5,
        historyPage: 1, historyPageSize: 5,
        signedHistoryPage: 1, signedHistoryPageSize: 5,

        // 填寫表單
        showFillModal: false,
        selectedForm: null,
        formSchema: null,
        formInstance: null,
        formSubject: '',
        subjectError: '',
        loadingFormSchema: false,
        submitting: false,

        // 簽核
        showApprovalModal: false,
        currentApproval: null,
        approvalFormInstance: null,
        selectedEdges: [],
        approvalComment: '',
        loadingApproval: false,
        submittingApproval: false,

        // 簽核鎖定
        approvalLockTimer: null,
        approvalLockRemaining: 0,
        approvalLockInterval: null,
        _beforeUnloadHandler: null,

        // 監控
        showMonitorModal: false,
        monitoringExecution: null,
        cyInstance: null,
        autoRefresh: true,
        autoRefreshTimer: null,
        workflowTabs: [],
        activeWorkflowTab: null,
        workflowGraphCache: {},
        monitorPage: 'overview',  // 'overview' | 'detail' | 'formContent' | 'approvals'
        monitorData: null,        // logs API 資料
        logSearchQuery: '',       // 日誌搜尋
        monitorStatus: {
            flowStatus: '-',
            activeCount: 0,
            completedCount: 0,
            failedCount: 0,
            waitingCount: 0,
            executionHistory: []
        },

        // 表單詳情（歷史查看用）
        formDetail: null,
        loadingFormDetail: false,
        formDetailViewer: null,

        // 閱讀表單
        showReadFormModal: false,
        readFormData: null,
        readFormInstance: null,
        loadingReadForm: false,

        // 排序狀態
        pendingSort: { field: 'scheduled_at', order: 'asc' },
        trackingSort: { field: 'submitted_at', order: 'asc' },
        trackingSignedSort: { field: 'submitted_at', order: 'asc' },
        historySort: { field: 'workflow_completed_at', order: 'desc' },
        historySignedSort: { field: 'workflow_completed_at', order: 'desc' },

        // 簽核歷程排序（false = 最新在前）
        approvalSortAsc: false,

        // Toast
        toast: { show: false, message: '', type: 'success' },

        // 管理員旗標
        isAdmin: window.__IS_ADMIN || false,

        // 自動刷新
        autoRefreshInterval: null,
        _refreshFailCount: 0,
        _refreshBaseDelay: 5000,
        _refreshMaxDelay: 60000,
        _visibilityHandler: null,

        // 測試表單筆數（以 serial_number 前綴 TEST- 為準）
        get testFormCount() {
            return this.historyList.filter(i => (i.serial_number || '').startsWith('TEST-')).length;
        },

        init() {
            this.loadAvailableForms();
            this.loadCategories();
            this.loadPendingApprovals();
            this.loadTracking();
            this.loadSigned();
            this.loadHistory();
            this.loadSignedHistory();

            // 啟動自動刷新
            this._scheduleRefresh();

            // 分頁可見性：隱藏時暫停，顯示時恢復
            this._visibilityHandler = () => {
                if (document.hidden) {
                    this._clearRefreshTimer();
                } else {
                    this._refreshFailCount = 0;
                    this._scheduleRefresh();
                }
            };
            document.addEventListener('visibilitychange', this._visibilityHandler);
        },

        destroy() {
            this._clearRefreshTimer();
            if (this._visibilityHandler) {
                document.removeEventListener('visibilitychange', this._visibilityHandler);
                this._visibilityHandler = null;
            }
        },

        _getRefreshDelay() {
            if (this._refreshFailCount === 0) return this._refreshBaseDelay;
            const delay = this._refreshBaseDelay * Math.pow(2, this._refreshFailCount);
            return Math.min(delay, this._refreshMaxDelay);
        },

        _clearRefreshTimer() {
            if (this.autoRefreshInterval) {
                clearTimeout(this.autoRefreshInterval);
                this.autoRefreshInterval = null;
            }
        },

        _scheduleRefresh() {
            this._clearRefreshTimer();
            if (document.hidden) return;
            this.autoRefreshInterval = setTimeout(() => {
                this._doRefreshCycle();
            }, this._getRefreshDelay());
        },

        async _doRefreshCycle() {
            if (this.showFillModal || this.showApprovalModal || this.showReadFormModal) {
                this._scheduleRefresh();
                return;
            }
            const ok = await this.refreshAll();
            if (ok) {
                this._refreshFailCount = 0;
            } else {
                this._refreshFailCount = Math.min(this._refreshFailCount + 1, 5);
            }
            this._scheduleRefresh();
        },

        async refreshAll() {
            const safeFetch = (url) => fetch(url).then(r => r.json()).catch(() => null);
            const ps = this.pendingSort;
            const ts = this.trackingSort;
            const tss = this.trackingSignedSort;
            const hs = this.historySort;
            const hss = this.historySignedSort;
            const [forms, approvals, tracking, signed, history, signedHist] = await Promise.all([
                safeFetch('/api/form-center/available-forms'),
                safeFetch(`/api/form-center/pending-tasks?sort=${ps.field}&order=${ps.order}`),
                safeFetch(`/api/form-center/my-forms?status=RUNNING&sort=${ts.field}&order=${ts.order}`),
                safeFetch(`/api/form-center/my-forms?signed=1&status=RUNNING&sort=${tss.field}&order=${tss.order}`),
                safeFetch(`/api/form-center/my-forms?status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${hs.field}&order=${hs.order}`),
                safeFetch(`/api/form-center/my-forms?signed=1&status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${hss.field}&order=${hss.order}`)
            ]);
            // 全部 null 代表所有請求都失敗（連線中斷）
            const allFailed = [forms, approvals, tracking, signed, history, signedHist].every(r => r === null);
            if (forms?.success) this.availableForms = forms.data || [];
            if (approvals?.success) this.pendingApprovals = approvals.data || [];
            if (tracking?.success) this.trackingList = tracking.data || [];
            if (signed?.success) this.signedList = signed.data || [];
            if (history?.success) this.historyList = history.data || [];
            if (signedHist?.success) this.signedHistoryList = signedHist.data || [];
            return !allFailed;
        },

        // 計算屬性
        get currentChildren() {
            if (!this.selectedParent || this.selectedParent === '__uncategorized__') return [];
            const parent = this.parentCategories.find(c => c.secure_code === this.selectedParent);
            if (!parent) return [];
            const children = [...(parent.children || [])];
            // 追加「其他」收納沒有子分類的表單
            children.push({ secure_code: '__child_uncategorized__', name: '其他' });
            return children;
        },

        _allKnownCodes() {
            const codes = [];
            this.parentCategories.forEach(p => {
                if (p.secure_code !== '__uncategorized__') {
                    codes.push(p.secure_code);
                    (p.children || []).forEach(c => codes.push(c.secure_code));
                }
            });
            return codes;
        },

        get filteredForms() {
            if (this.selectedParent === null) return this.availableForms;
            if (this.selectedParent === '__uncategorized__') {
                const known = this._allKnownCodes();
                return this.availableForms.filter(f => !f.category_secure_code || !known.includes(f.category_secure_code));
            }
            const parent = this.parentCategories.find(c => c.secure_code === this.selectedParent);
            if (!parent) return this.availableForms;
            const children = parent.children || [];

            // 選了「其他」子分類 → 直接指向父分類的表單（未歸入任何子分類）
            if (this.selectedChild === '__child_uncategorized__') {
                return this.availableForms.filter(f => f.category_secure_code === parent.secure_code);
            }
            if (this.selectedChild) {
                return this.availableForms.filter(f => f.category_secure_code === this.selectedChild);
            }
            // 沒選子分類 → 匹配所有子分類 + 直接指向父分類的
            const childCodes = children.map(c => c.secure_code);
            return this.availableForms.filter(f =>
                childCodes.includes(f.category_secure_code) || f.category_secure_code === parent.secure_code
            );
        },

        getFormCountByParent(parentSc) {
            if (parentSc === '__uncategorized__') {
                const known = this._allKnownCodes();
                return this.availableForms.filter(f => !f.category_secure_code || !known.includes(f.category_secure_code)).length;
            }
            const parent = this.parentCategories.find(c => c.secure_code === parentSc);
            if (!parent) return 0;
            const children = parent.children || [];
            if (children.length === 0) {
                return this.availableForms.filter(f => f.category_secure_code === parentSc).length;
            }
            const childCodes = children.map(c => c.secure_code);
            return this.availableForms.filter(f =>
                childCodes.includes(f.category_secure_code) || f.category_secure_code === parentSc
            ).length;
        },

        selectParent(parentSc) {
            this.selectedParent = parentSc;
            // 自動選第一個子分類
            const children = this.currentChildren;
            this.selectedChild = children.length > 0 ? children[0].secure_code : null;
        },

        getFormCountByChild(childSc) {
            if (childSc === '__child_uncategorized__') {
                // 直接指向父分類的表單數量
                return this.availableForms.filter(f => f.category_secure_code === this.selectedParent).length;
            }
            return this.availableForms.filter(f => f.category_secure_code === childSc).length;
        },

        get pendingTotalPages() { return Math.ceil(this.pendingApprovals.length / this.pendingPageSize); },
        get pagedPendingApprovals() {
            const start = (this.pendingPage - 1) * this.pendingPageSize;
            return this.pendingApprovals.slice(start, start + this.pendingPageSize);
        },

        get trackingTotalPages() { return Math.ceil(this.trackingList.length / this.trackingPageSize); },
        get pagedTrackingList() {
            const start = (this.trackingPage - 1) * this.trackingPageSize;
            return this.trackingList.slice(start, start + this.trackingPageSize);
        },

        get pagedSignedList() {
            const start = (this.signedPage - 1) * this.signedPageSize;
            return this.signedList.slice(start, start + this.signedPageSize);
        },

        get pagedHistoryList() {
            const start = (this.historyPage - 1) * this.historyPageSize;
            return this.historyList.slice(start, start + this.historyPageSize);
        },

        get pagedSignedHistoryList() {
            const start = (this.signedHistoryPage - 1) * this.signedHistoryPageSize;
            return this.signedHistoryList.slice(start, start + this.signedHistoryPageSize);
        },

        // 清單模式
        get listDataSource() {
            if (this.listTab === 'pending') return this.pendingApprovals;
            if (this.listTab === 'tracking') return this.listSubTab === 'signed' ? this.signedList : this.trackingList;
            if (this.listTab === 'history') return this.listSubTab === 'signed' ? this.signedHistoryList : this.historyList;
            return [];
        },
        get listTotalPages() { return Math.max(1, Math.ceil(this.listDataSource.length / this.listPageSize)); },
        get pagedListData() {
            const start = (this.listPage - 1) * this.listPageSize;
            return this.listDataSource.slice(start, start + this.listPageSize);
        },
        switchToList(tab) {
            this.viewMode = 'list';
            this.listTab = tab;
            this.listSubTab = 'mine';
            this.listPage = 1;
        },

        // 過濾後的日誌
        get filteredLogs() {
            const logs = this.monitorData?.logs || [];
            if (!this.logSearchQuery) return logs;
            const q = this.logSearchQuery.toLowerCase();
            return logs.filter(log =>
                (log.message || '').toLowerCase().includes(q) ||
                (log.node_id || '').toLowerCase().includes(q) ||
                (log.workflow_name || '').toLowerCase().includes(q) ||
                JSON.stringify(log.data || {}).toLowerCase().includes(q)
            );
        },

        // 變數變化記錄
        get variableChanges() {
            const logs = this.monitorData?.logs || [];
            const changes = [];

            for (const log of logs) {
                const time = log.timestamp?.split(' ')[1] || '';
                const node = log.node_id?.replace('node-', '') || '';
                const displayName = log.display_name || node;
                const workflowName = log.workflow_name || '';
                const data = log.data || {};

                // 讀取欄位（OpFieldRead）
                if (log.message?.includes('讀取欄位:')) {
                    const match = log.message.match(/讀取欄位:\s*(\S+)\s*=\s*(.+)/);
                    if (match) {
                        changes.push({
                            timestamp: time,
                            node: node,
                            displayName: displayName,
                            workflowName: workflowName,
                            action: 'read',
                            actionLabel: 'read',
                            varName: match[1],
                            displayValue: match[2]
                        });
                    }
                }
                // 變數操作完成（OpSet）
                else if (log.message?.includes('變數操作完成:')) {
                    const match = log.message.match(/變數操作完成:\s*(\S+)\s*=\s*(.*)/);
                    if (match) {
                        changes.push({
                            timestamp: time,
                            node: node,
                            displayName: displayName,
                            workflowName: workflowName,
                            action: 'set',
                            actionLabel: data.operation || 'set',
                            varName: match[1],
                            displayValue: match[2] || '(空)'
                        });
                    }
                }
            }
            return changes;
        },

        // 載入函式
        async loadAvailableForms() {
            this.loadingForms = true;
            try {
                const res = await fetch('/api/form-center/available-forms');
                const data = await res.json();
                if (data.success) this.availableForms = data.data || [];
            } catch (e) { console.error('載入可填寫表單失敗:', e); }
            finally { this.loadingForms = false; }
        },

        async loadCategories() {
            this.loadingCategories = true;
            try {
                const res = await fetch('/api/form-workflow/categories?context=form_center');
                const data = await res.json();
                if (data.success) {
                    const cats = data.data || [];
                    const hasOther = cats.some(c => c.name === '其他');
                    if (!hasOther) {
                        cats.push({ secure_code: '__uncategorized__', name: '其他', children: [] });
                    }
                    this.parentCategories = cats;
                    if (!this.selectedParent && cats.length > 0) {
                        this.selectParent(cats[0].secure_code);
                    }
                }
            } catch (e) { /* 分類 API 可能不存在，忽略 */ }
            finally { this.loadingCategories = false; }
        },

        async loadPendingApprovals() {
            this.loadingPending = true;
            try {
                const {field, order} = this.pendingSort;
                const res = await fetch(`/api/form-center/pending-tasks?sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.pendingApprovals = data.data || [];
            } catch (e) { console.error('載入待簽核失敗:', e); }
            finally { this.loadingPending = false; }
        },

        async loadTracking() {
            this.loadingTracking = true;
            try {
                const {field, order} = this.trackingSort;
                const res = await fetch(`/api/form-center/my-forms?status=RUNNING&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.trackingList = data.data || [];
            } catch (e) { console.error('載入追蹤失敗:', e); }
            finally { this.loadingTracking = false; }
        },

        async loadSigned() {
            this.loadingSigned = true;
            try {
                const {field, order} = this.trackingSignedSort;
                const res = await fetch(`/api/form-center/my-forms?signed=1&status=RUNNING&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.signedList = data.data || [];
            } catch (e) { console.error('載入簽核追蹤失敗:', e); }
            finally { this.loadingSigned = false; }
        },

        async loadHistory() {
            this.loadingHistory = true;
            try {
                const {field, order} = this.historySort;
                const res = await fetch(`/api/form-center/my-forms?status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.historyList = data.data || [];
            } catch (e) { console.error('載入歷史失敗:', e); }
            finally { this.loadingHistory = false; }
        },

        async loadSignedHistory() {
            this.loadingSignedHistory = true;
            try {
                const {field, order} = this.historySignedSort;
                const res = await fetch(`/api/form-center/my-forms?signed=1&status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.signedHistoryList = data.data || [];
            } catch (e) { console.error('載入簽核歷史失敗:', e); }
            finally { this.loadingSignedHistory = false; }
        },

        // 排序切換
        toggleSort(listName, field) {
            const sortKey = listName + 'Sort';
            const s = this[sortKey];
            if (s.field === field) {
                s.order = s.order === 'asc' ? 'desc' : 'asc';
            } else {
                s.field = field;
                s.order = field === 'serial_number' ? 'asc' :
                          (listName === 'history' || listName === 'historySigned') ? 'desc' : 'asc';
            }
            this._reloadForSort(listName);
        },

        _reloadForSort(listName) {
            const loaders = {
                pending: () => this.loadPendingApprovals(),
                tracking: () => this.loadTracking(),
                trackingSigned: () => this.loadSigned(),
                history: () => this.loadHistory(),
                historySigned: () => this.loadSignedHistory(),
            };
            const fn = loaders[listName];
            if (fn) fn();
        },

        sortIcon(listName, field) {
            const s = this[listName + 'Sort'];
            if (!s || s.field !== field) return ' \u21C5';
            return s.order === 'asc' ? ' \u25B2' : ' \u25BC';
        },

        // 填寫表單
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
                }
            } catch (e) {
                console.error('載入表單結構失敗:', e);
            } finally {
                this.loadingFormSchema = false;
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

        // 簽核（先取鎖再開表單）
        async openApprovalModal(item) {
            this.currentApproval = null;
            this.selectedEdges = [];
            this.approvalComment = '';
            this.loadingApproval = true;

            try {
                // Step 1: 取得簽核鎖定
                const lockRes = await fetch(`/api/form-center/pending-tasks/${item.queue_secure_code}/lock`, {
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
                const res = await fetch(`/api/form-center/pending-tasks/${item.queue_secure_code}`);
                const data = await res.json();

                if (data.success) {
                    this.currentApproval = data.data;

                    // Step 3: 啟動倒數計時
                    this._startApprovalCountdown(lockData.remaining_seconds || 600);

                    // Step 4: 註冊 beforeunload 釋放鎖
                    const queueCode = item.queue_secure_code;
                    this._beforeUnloadHandler = () => {
                        fetch(`/api/form-center/pending-tasks/${queueCode}/lock`, {
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

        get approvalCountdownText() {
            const m = Math.floor(this.approvalLockRemaining / 60);
            const s = this.approvalLockRemaining % 60;
            return `${m}:${String(s).padStart(2, '0')}`;
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

                this.approvalFormInstance = await Formio.createForm(container, schema, formOptions);

                if (formData) {
                    this.approvalFormInstance.submission = { data: formData };
                }

                // 套用底圖和寬度
                this.applyFormBackground('approval-form-container', this.currentApproval?.builder_config);
            } catch (e) {
                console.error('簽核表單渲染失敗:', e);
                container.innerHTML = '<p style="color: #dc2626; text-align: center;">表單載入失敗</p>';
            }
        },

        closeApprovalModal() {
            // 釋放鎖定（best-effort）
            if (this.currentApproval?.queue_secure_code) {
                fetch(`/api/form-center/pending-tasks/${this.currentApproval.queue_secure_code}/lock`, {
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
            this.cleanupFormBackground('approval-form-container');
            const container = document.getElementById('approval-form-container');
            if (container) container.innerHTML = '';

            this.showApprovalModal = false;
            this.currentApproval = null;
            this.selectedEdges = [];
            this.approvalComment = '';
        },

        toggleEdgeSelection(edgeId) {
            const idx = this.selectedEdges.indexOf(edgeId);
            if (idx === -1) {
                this.selectedEdges.push(edgeId);
            } else {
                this.selectedEdges.splice(idx, 1);
            }
        },

        async submitApproval() {
            if (this.selectedEdges.length === 0 || this.submittingApproval) return;

            const minLen = this.currentApproval?.min_comment_length || 0;
            if (minLen > 0 && this.approvalComment.trim().length < minLen) {
                this.showToast(`簽核意見至少需要 ${minLen} 字`, 'warning');
                return;
            }

            this.submittingApproval = true;

            try {
                const payload = {
                    decision: 'approved',
                    selected_path: this.selectedEdges[0],
                    comment: this.approvalComment
                };

                if (this.currentApproval?.has_editable_fields && this.approvalFormInstance) {
                    payload.form_data = this.approvalFormInstance.submission.data;
                }

                const res = await fetch(`/api/form-center/pending-tasks/${this.currentApproval.queue_secure_code}/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (data.success) {
                    this._clearApprovalCountdown();  // 成功送出，停止倒數
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
                    this.cleanupFormBackground('approval-form-container');
                    const container = document.getElementById('approval-form-container');
                    if (container) container.innerHTML = '';
                    this.showApprovalModal = false;
                    this.currentApproval = null;
                    this.selectedEdges = [];
                    this.approvalComment = '';
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

        // 工具函式
        // 將 ISO 字串當 UTC 解析（後端存 UTC，isoformat() 不帶 Z）
        _parseUTC(dateStr) {
            if (!dateStr) return null;
            // 如果沒有時區標記，當作 UTC
            if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !/\d{2}:\d{2}$/.test(dateStr.slice(-6))) {
                dateStr = dateStr + 'Z';
            }
            return new Date(dateStr);
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            const d = this._parseUTC(dateStr);
            const tz = window.__USER_TIMEZONE || 'Asia/Taipei';
            return d.toLocaleDateString('zh-TW', { timeZone: tz }) + ' ' + d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', timeZone: tz });
        },

        formatWaitTime(isoString) {
            if (!isoString) return '-';
            const diff = Date.now() - this._parseUTC(isoString).getTime();
            if (diff < 0) return '-';
            return this._formatMs(diff);
        },

        formatDuration(startIso, endIso) {
            if (!startIso || !endIso) return '-';
            const diff = this._parseUTC(endIso).getTime() - this._parseUTC(startIso).getTime();
            if (diff < 0) return '-';
            return this._formatMs(diff);
        },

        _formatMs(ms) {
            const totalMin = Math.floor(ms / 60000);
            const days = Math.floor(totalMin / 1440);
            const hours = Math.floor((totalMin % 1440) / 60);
            const mins = totalMin % 60;
            const parts = [];
            if (days > 0) parts.push(days + '天');
            if (hours > 0) parts.push(hours + '小時');
            parts.push(mins + '分鐘');
            return parts.join('');
        },

        sortedApprovals(list) {
            if (!list || list.length === 0) return [];
            return [...list].sort((a, b) => {
                const tA = a.acted_at ? new Date(a.acted_at).getTime() : 0;
                const tB = b.acted_at ? new Date(b.acted_at).getTime() : 0;
                return this.approvalSortAsc ? tA - tB : tB - tA;
            });
        },

        getActionText(action) {
            const map = { 'approved': '核准', 'rejected': '退回', 'PENDING': '待簽', 'FORCE_END': '強制結束' };
            return map[action] || action;
        },

        getActionBadgeClass(action) {
            if (action === 'approved') return 'fc-badge-completed';
            if (action === 'rejected' || action === 'FORCE_END') return 'fc-badge-error';
            return 'fc-badge-pending';
        },

        shortSubject(text, max = 56) {
            if (!text) return '-';
            if (text.length <= max) return text;
            return text.slice(0, max) + '[...]';
        },

        getShortSerial(serial) {
            if (!serial) return '-';
            // TEST-20260127-0001 -> 0127-0001
            const parts = serial.split('-');
            if (parts.length >= 3) {
                const date = parts[1];
                const seq = parts[2];
                return date.slice(4) + '-' + seq;
            }
            return serial;
        },

        getStatusText(status) {
            const map = {
                'INITIAL': '草稿', 'PENDING': '待處理', 'RUNNING': '進行中',
                'COMPLETED': '已完成', 'REJECTED': '已退回', 'ERROR': '錯誤',
                'TERMINATED': '已終止', 'CANCELLED': '已取消'
            };
            return map[status] || status;
        },

        getStatusClass(status) {
            const map = {
                'RUNNING': 'fc-badge-running', 'COMPLETED': 'fc-badge-completed',
                'ERROR': 'fc-badge-error', 'REJECTED': 'fc-badge-error',
                'TERMINATED': 'fc-badge-error', 'CANCELLED': 'fc-badge-error'
            };
            return map[status] || '';
        },

        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        // --- 執行監控 methods (from _monitor_methods.html) ---

        // =============================================================
        // 執行監控
        // =============================================================

        async viewExecutionDetail(item) {
            console.log('檢視執行:', item);
            this.monitoringExecution = item;

            // 重置監控狀態
            this.monitorStatus = {
                flowStatus: item.workflow_status || item.status || '-',
                activeCount: 0,
                completedCount: 0,
                failedCount: 0,
                waitingCount: 0,
                executionHistory: []
            };

            this.workflowTabs = [];
            this.activeWorkflowTab = null;
            this.workflowGraphCache = {};
            this.monitorPage = 'overview';
            this.monitorData = null;
            this.logSearchQuery = '';
            this.formDetail = null;
            this.loadingFormDetail = false;
            this.showMonitorModal = true;

            await this.$nextTick();

            try {
                // 同時載入 path（含 workflow_tabs）和 logs
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const [pathLoaded, logsLoaded] = await Promise.all([
                    this.loadExecutionSnapshot(item),
                    this.loadExecutionLogs(instanceId)
                ]);

                // 從快取取得主流程的圖並初始化 Cytoscape
                const mainTab = this.workflowTabs.find(t => t.is_main);
                if (mainTab && this.workflowGraphCache[mainTab.instance_id]) {
                    this.initializeCytoscape(this.workflowGraphCache[mainTab.instance_id]);
                } else if (this.workflowTabs.length > 0) {
                    // 如果沒有標記為主流程，使用第一個
                    const firstTab = this.workflowTabs[0];
                    if (this.workflowGraphCache[firstTab.instance_id]) {
                        this.initializeCytoscape(this.workflowGraphCache[firstTab.instance_id]);
                    }
                } else {
                    console.warn('無法從追蹤資料取得流程圖');
                }

                // 啟動自動刷新
                if (this.autoRefresh) {
                    this.startAutoRefresh();
                }
            } catch (error) {
                console.error('載入流程追蹤錯誤:', error);
                this.showToast('載入流程圖失敗', 'error');
            }
        },

        async loadExecutionLogs(instanceId) {
            console.log('[LOGS] loadExecutionLogs 呼叫, instanceId:', instanceId);
            try {
                const url = `/api/form-center/executions/${instanceId}/logs`;
                console.log('[LOGS] 請求 URL:', url);
                const response = await fetch(url);
                console.log('[LOGS] 回應狀態:', response.status);
                const result = await response.json();
                console.log('[LOGS] 回應內容:', result);

                if (result.success) {
                    this.monitorData = result.data;
                    console.log('[LOGS] logs 數量:', result.data?.logs?.length || 0);
                    console.log('[LOGS] variables:', result.data?.variables);
                } else {
                    console.error('[LOGS] 載入失敗:', result.error);
                }
            } catch (error) {
                console.error('[LOGS] 載入錯誤:', error);
            }
        },

        async loadExecutionSnapshot(item) {
            try {
                // 使用 execution_code 或 workflow_instance_secure_code
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const response = await fetch(`/api/form-center/executions/${instanceId}/path`);
                const result = await response.json();

                if (result.success) {
                    const data = result.data;

                    // 更新監控狀態
                    this.monitorStatus.flowStatus = data.instance_status || item.status;
                    this.monitorStatus.activeCount = (data.active_nodes || []).length;
                    this.monitorStatus.completedCount = (data.completed_nodes || []).length;
                    this.monitorStatus.failedCount = (data.failed_nodes || []).length;
                    this.monitorStatus.waitingCount = (data.waiting_nodes || []).length;
                    this.monitorStatus.executionHistory = data.execution_history || [];

                    // 更新 workflow_tabs（主流程 + 子流程）
                    if (data.workflow_tabs && data.workflow_tabs.length > 0) {
                        this.workflowTabs = data.workflow_tabs;
                        // 快取每個流程的圖資料
                        data.workflow_tabs.forEach(tab => {
                            this.workflowGraphCache[tab.instance_id] = tab.graph;
                        });
                        // 如果尚未選擇 Tab，預設選擇主流程
                        if (!this.activeWorkflowTab) {
                            const mainTab = data.workflow_tabs.find(t => t.is_main);
                            if (mainTab) {
                                this.activeWorkflowTab = mainTab.instance_id;
                            } else if (data.workflow_tabs.length > 0) {
                                this.activeWorkflowTab = data.workflow_tabs[0].instance_id;
                            }
                        }
                    }

                    // 更新當前選中流程的節點樣式
                    this.updateCurrentTabNodeStyles(data);

                    console.log('執行快照已載入:', data);
                } else {
                    console.error('載入執行快照失敗:', result.error);
                }
            } catch (error) {
                console.error('載入執行快照錯誤:', error);
            }
        },

        updateCurrentTabNodeStyles(data) {
            if (!this.cyInstance) return;

            this.cyInstance.nodes().removeClass('node-running node-completed node-failed node-waiting');

            // 找出當前 Tab 對應的節點執行記錄
            const currentHistory = (data.execution_history || []).filter(
                h => h.workflow_instance_id === this.activeWorkflowTab
            );

            currentHistory.forEach(h => {
                const node = this.cyInstance.getElementById(h.node_id);
                if (node.length > 0) {
                    if (h.status === 'RUNNING') {
                        node.addClass('node-running');
                    } else if (h.status === 'SUCCESS') {
                        node.addClass('node-completed');
                    } else if (['FAILED', 'ERROR', 'TIMEOUT'].includes(h.status)) {
                        node.addClass('node-failed');
                    } else if (['WAITING', 'PENDING', 'INITIAL'].includes(h.status)) {
                        node.addClass('node-waiting');
                    }
                }
            });
        },

        async switchWorkflowTab(wf) {
            if (this.activeWorkflowTab === wf.instance_id) return;

            this.activeWorkflowTab = wf.instance_id;
            console.log('切換到流程:', wf.name);

            // 從快取載入流程圖
            const graphData = this.workflowGraphCache[wf.instance_id];
            if (graphData) {
                this.initializeCytoscape(graphData);
                // 重新載入快照以更新節點狀態
                if (this.monitoringExecution) {
                    await this.loadExecutionSnapshot(this.monitoringExecution);
                }
            } else {
                console.warn('找不到流程圖資料:', wf.name);
            }
        },

        initializeCytoscape(graphData) {
            if (!graphData) {
                console.error('無流程圖資料');
                return;
            }

            // 銷毀舊實例
            if (this.cyInstance) {
                this.cyInstance.destroy();
            }

            // 轉換 graph 資料為 Cytoscape 格式
            const elements = [];

            // 添加節點
            if (graphData.nodes) {
                graphData.nodes.forEach(node => {
                    elements.push({
                        data: {
                            id: node.id || node.data?.id,
                            label: node.data?.label || node.label || node.id,
                            type: node.data?.type || node.type
                        },
                        position: node.position || { x: 0, y: 0 }
                    });
                });
            }

            // 添加連線
            if (graphData.edges) {
                graphData.edges.forEach(edge => {
                    elements.push({
                        data: {
                            id: edge.id,
                            source: edge.source,
                            target: edge.target,
                            label: edge.label || edge.data?.label || ''
                        }
                    });
                });
            }

            // 建立 Cytoscape 實例
            this.cyInstance = cytoscape({
                container: document.getElementById('cy-monitor'),
                elements: elements,
                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': '#E0E0E0',
                            'label': 'data(label)',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'font-size': '11px',
                            'width': 80,
                            'height': 36,
                            'border-width': 2,
                            'border-color': '#999',
                            'text-wrap': 'wrap',
                            'text-max-width': '70px'
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 2,
                            'line-color': '#999',
                            'target-arrow-color': '#999',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'label': 'data(label)',
                            'font-size': '9px',
                            'text-rotation': 'autorotate'
                        }
                    },
                    // 執行中節點
                    {
                        selector: '.node-running',
                        style: {
                            'background-color': '#FFC107',
                            'border-color': '#FF9800',
                            'border-width': 3
                        }
                    },
                    // 已完成節點
                    {
                        selector: '.node-completed',
                        style: {
                            'background-color': '#4CAF50',
                            'border-color': '#388E3C',
                            'border-width': 2
                        }
                    },
                    // 失敗節點
                    {
                        selector: '.node-failed',
                        style: {
                            'background-color': '#F44336',
                            'border-color': '#D32F2F',
                            'border-width': 3
                        }
                    },
                    // 等待節點
                    {
                        selector: '.node-waiting',
                        style: {
                            'background-color': '#E3F2FD',
                            'border-color': '#2196F3',
                            'border-width': 3,
                            'border-style': 'dashed'
                        }
                    }
                ],
                layout: {
                    name: 'preset'
                },
                userZoomingEnabled: true,
                userPanningEnabled: true,
                boxSelectionEnabled: false
            });

            // 調整視圖以顯示所有節點
            this.cyInstance.fit(null, 50);

            console.log('Cytoscape 已初始化，節點數:', elements.filter(e => !e.data.source).length);
        },

        closeMonitorModal() {
            this.stopAutoRefresh();

            if (this.cyInstance) {
                this.cyInstance.destroy();
                this.cyInstance = null;
            }

            // 重置狀態
            this.monitorStatus = {
                flowStatus: '-',
                activeCount: 0,
                completedCount: 0,
                failedCount: 0,
                waitingCount: 0,
                executionHistory: []
            };

            this.workflowTabs = [];
            this.activeWorkflowTab = null;
            this.workflowGraphCache = {};
            this.monitorPage = 'overview';
            this.monitorData = null;
            this.logSearchQuery = '';
            this.formDetail = null;
            this.showMonitorModal = false;
            this.monitoringExecution = null;

            // 清理表單檢視器
            if (this.formDetailViewer) {
                this.formDetailViewer.destroy();
                this.formDetailViewer = null;
            }
            this.cleanupFormBackground('formDetailViewer');
        },

        // 切換到表單內容頁籤
        async switchToFormContent() {
            this.monitorPage = 'formContent';
            if (!this.formDetail) {
                await this.loadFormDetail();
            } else {
                // 已載入，重新渲染表單
                this.$nextTick(() => this.renderFormViewer());
            }
        },

        // 切換到簽核歷史頁籤
        async switchToApprovalHistory() {
            this.monitorPage = 'approvals';
            if (!this.formDetail) {
                await this.loadFormDetail();
            }
        },

        // 載入表單詳情
        async loadFormDetail() {
            if (!this.monitoringExecution) return;

            this.loadingFormDetail = true;
            try {
                const secureCode = this.monitoringExecution.secure_code;
                const response = await fetch(`/api/form-center/form-detail/${secureCode}`);
                const result = await response.json();

                if (result.success) {
                    this.formDetail = result.data;
                    console.log('表單詳情載入完成:', this.formDetail);

                    // 如果在表單內容頁，渲染表單
                    if (this.monitorPage === 'formContent') {
                        this.$nextTick(() => this.renderFormViewer());
                    }
                } else {
                    console.error('載入表單詳情失敗:', result.error);
                    this.showToast('載入表單詳情失敗', 'error');
                }
            } catch (error) {
                console.error('載入表單詳情錯誤:', error);
                this.showToast('載入表單詳情錯誤', 'error');
            } finally {
                this.loadingFormDetail = false;
            }
        },

        // 共用：渲染唯讀表單
        async _renderFormReadOnly(containerId, schema, formData, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return null;

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

        // 渲染表單檢視器（監控模態框 - 表單內容頁籤）
        async renderFormViewer() {
            if (!this.formDetail?.schema) return;
            if (this.formDetailViewer) {
                this.formDetailViewer.destroy();
                this.formDetailViewer = null;
            }
            this.formDetailViewer = await this._renderFormReadOnly(
                'formDetailViewer',
                this.formDetail.schema,
                this.formDetail.form_data,
                this.formDetail.builder_config
            );
        },

        toggleAutoRefresh() {
            if (this.autoRefresh) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        },

        startAutoRefresh() {
            this.stopAutoRefresh();
            if (this.autoRefresh && this.monitoringExecution) {
                this.autoRefreshTimer = setInterval(() => {
                    this.refreshMonitor();
                }, 5000);
                console.log('自動刷新已啟動（每5秒）');
            }
        },

        stopAutoRefresh() {
            if (this.autoRefreshTimer) {
                clearInterval(this.autoRefreshTimer);
                this.autoRefreshTimer = null;
                console.log('自動刷新已停止');
            }
        },

        async refreshMonitor() {
            if (!this.monitoringExecution) return;
            await this.loadExecutionSnapshot(this.monitoringExecution);
        },

        async confirmForceEnd() {
            if (!confirm('確定要強制結束此流程？此操作將取消所有執行中的節點並結束流程。')) return;
            await this.executeForceEnd();
        },

        async executeForceEnd() {
            const secureCode = this.monitoringExecution?.secure_code;
            if (!secureCode) return;
            try {
                const res = await fetch(`/api/form-center/force-end/${secureCode}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
                    }
                });
                const result = await res.json();
                if (result.success) {
                    this.showToast('流程已強制結束', 'success');
                    await this.refreshMonitor();
                    this.loadTracking();
                    this.loadSigned();
                    this.loadHistory();
                    this.loadSignedHistory();
                } else {
                    this.showToast(result.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        formatHistoryTime(dateStr) {
            if (!dateStr) return '-';
            const d = this._parseUTC(dateStr);
            const tz = window.__USER_TIMEZONE || 'Asia/Taipei';
            return d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: tz });
        },

        // =============================================================
        // 統一底圖/寬度渲染
        // =============================================================

        applyFormBackground(containerId, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // 白色表單區域 + 陰影（匹配設計器 preview 行為）
            container.style.backgroundColor = '#ffffff';
            container.style.padding = '20px';
            container.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
            container.style.minHeight = '400px';

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

        // --- 閱讀表單 methods (from _read_form_methods.html) ---

        // =============================================================
        // 閱讀表單
        // =============================================================

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
        },

        closeReadForm() {
            if (this.readFormInstance) {
                this.readFormInstance.destroy();
                this.readFormInstance = null;
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

        // (end of included methods)
    };
}
