/**
 * form_center.html — Alpine.js Manager
 * Window Bridge: reads window.__USER_TIMEZONE
 */

// --- 流程總圖常數 (子流程展開 + Mode B 替換) ---
const _FC_VISIBLE_TYPES = new Set(['Start', 'FormAdapter', 'End', 'EmailAdapter']);
const _FC_REPLACE_LABEL = '系統node';
const _FC_SYS_COLOR = '#d1d5db';
const _FC_SYS_BORDER = '#9ca3af';
const _FC_NODE_COLORS = {
    'Start': '#22c55e', 'End': '#ef4444', 'FormAdapter': '#3b82f6',
    'EmailAdapter': '#f59e0b', 'default': '#E0E0E0'
};
const _FC_GROUP_COLORS = [
    { bg: 'rgba(59,130,246,0.08)', border: '#3b82f6' },
    { bg: 'rgba(139,92,246,0.10)', border: '#8b5cf6' },
    { bg: 'rgba(236,72,153,0.10)', border: '#ec4899' },
];

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
        pendingFiles: [],       // 待上傳附件（submit 後才上傳）

        // 簽核
        showApprovalModal: false,
        currentApproval: null,
        approvalFormInstance: null,
        selectedEdges: [],
        approvalComment: '',
        selectedOptionValue: null,   // 自定義決策選項的 value（送後端用）
        selectedOptionId: null,      // 自定義決策選項的 id（UI 高亮用）
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

        // 流程總圖（獨立對話窗）
        showFlowOverviewModal: false,
        flowOverviewCy: null,
        flowOverviewLoading: false,
        flowOverviewError: null,
        flowOverviewInfo: {},

        // 流程總圖（監控對話框內的分頁）
        monitorFlowChartCy: null,

        // 簽核歷程排序（false = 最新在前）
        approvalSortAsc: false,

        // Toast
        toast: { show: false, message: '', type: 'success' },

        // 管理員旗標
        isAdmin: window.__IS_ADMIN || false,
        isSystemAdmin: window.__IS_SYSTEM_ADMIN || false,
        userRoleCodes: window.__USER_ROLE_CODES || [],
        currentUserSc: window.__USER_SC || '',

        // 權限 computed：可查看執行詳情（系統管理員/企業管理員/流程設計師）
        get canViewExecution() {
            return this.isSystemAdmin || this.isAdmin || this.userRoleCodes.includes('FLOW_DESIGNER');
        },
        // 外部廠商：只能看閱讀表單
        get isExternalUser() {
            return this.userRoleCodes.includes('EXTERNAL_USERS');
        },

        // 欄位顯示設定
        columnConfig: {},
        showColumnConfigModal: false,
        columnConfigLocale: '*',
        columnConfigEditing: {},
        columnConfigLocales: [],
        savingColumnConfig: false,

        // 自動刷新
        autoRefreshInterval: null,
        _refreshFailCount: 0,
        _refreshBaseDelay: 5000,
        _refreshMaxDelay: 60000,
        _visibilityHandler: null,

        // 批次簽核
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

        // 簽核片語
        cannedMessages: [],
        loadingCanned: false,
        showPhraseManager: false,
        cannedNewText: '',
        cannedEditId: null,
        cannedEditText: '',

        // 批次 computed
        get batchKeyOf() {
            // 回傳函式：取得某 item 的 batch key
            return (item) => (item.published_secure_code || '') + '|' + (item.node_id || '');
        },

        get batchSelectedCount() {
            return this.batchSelected.length;
        },

        // 測試表單筆數（以 serial_number 前綴 TEST- 為準）
        get testFormCount() {
            return this.historyList.filter(i => (i.serial_number || '').startsWith('TEST-')).length;
        },

        init() {
            this.loadColumnConfig();
            this.loadAvailableForms();
            this.loadCategories();
            this.loadPendingApprovals();
            this.loadTracking();
            this.loadSigned();
            this.loadHistory();
            this.loadSignedHistory();
            this.loadCannedMessages();

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
            const safeFetch = (url) => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null);
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
            // 任一請求失敗即視為失敗（觸發退避）
            const results = [forms, approvals, tracking, signed, history, signedHist];
            const anyFailed = results.some(r => r === null);
            if (forms?.success) this.availableForms = forms.data || [];
            if (approvals?.success) this.pendingApprovals = approvals.data || [];
            if (tracking?.success) this.trackingList = tracking.data || [];
            if (signed?.success) this.signedList = signed.data || [];
            if (history?.success) this.historyList = history.data || [];
            if (signedHist?.success) this.signedHistoryList = signedHist.data || [];
            return !anyFailed;
        },

        // 計算屬性
        get currentChildren() {
            if (!this.selectedParent || this.selectedParent === 'SYS_CAT_OTHER') return [];
            const parent = this.parentCategories.find(c => c.secure_code === this.selectedParent);
            if (!parent) return [];
            const children = [...(parent.children || [])];
            // 追加「未歸子分類」收納只掛在父分類的表單
            children.push({ secure_code: '__child_uncategorized__', name: '其他' });
            return children;
        },

        _allKnownCodes() {
            const codes = [];
            this.parentCategories.forEach(p => {
                codes.push(p.secure_code);
                (p.children || []).forEach(c => codes.push(c.secure_code));
            });
            return codes;
        },

        get filteredForms() {
            if (this.selectedParent === null) return this.availableForms;
            if (this.selectedParent === 'SYS_CAT_OTHER') {
                return this.availableForms.filter(f => !f.category_secure_code || f.category_secure_code === 'SYS_CAT_OTHER');
            }
            const parent = this.parentCategories.find(c => c.secure_code === this.selectedParent);
            if (!parent) return this.availableForms;
            const children = parent.children || [];

            // 選了「其他」子分類 -> 直接指向父分類的表單（未歸入任何子分類）
            if (this.selectedChild === '__child_uncategorized__') {
                return this.availableForms.filter(f => f.category_secure_code === parent.secure_code);
            }
            if (this.selectedChild) {
                return this.availableForms.filter(f => f.category_secure_code === this.selectedChild);
            }
            // 沒選子分類 -> 匹配所有子分類 + 直接指向父分類的
            const childCodes = children.map(c => c.secure_code);
            return this.availableForms.filter(f =>
                childCodes.includes(f.category_secure_code) || f.category_secure_code === parent.secure_code
            );
        },

        getFormCountByParent(parentSc) {
            if (parentSc === 'SYS_CAT_OTHER') {
                return this.availableForms.filter(f => !f.category_secure_code || f.category_secure_code === 'SYS_CAT_OTHER').length;
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
                const time = typeof BkTime !== 'undefined' ? BkTime.format(log.timestamp, 'time') : (log.timestamp?.split(' ')[1] || '');
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
                if (data.success) {
                    this.pendingApprovals = data.data || [];
                    // 清除已不存在的勾選項
                    const codes = new Set(this.pendingApprovals.map(i => i.queue_secure_code));
                    this.batchSelected = this.batchSelected.filter(c => codes.has(c));
                    if (this.batchSelected.length === 0) this.batchKey = null;
                }
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
            this.pendingFiles = [];
        },

        // 附件：選取檔案（暫存在 pendingFiles，submit 後才上傳）
        addPendingFiles(event) {
            const files = event.target.files;
            if (!files) return;
            for (let i = 0; i < files.length; i++) {
                if (this.pendingFiles.length >= 10) break;
                this.pendingFiles.push(files[i]);
            }
            event.target.value = '';
        },

        removePendingFile(index) {
            this.pendingFiles.splice(index, 1);
        },

        formatFileSize(bytes) {
            if (!bytes) return '0 B';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / 1024 / 1024).toFixed(1) + ' MB';
        },

        // 上傳暫存附件到 FileService
        async _uploadPendingFiles(formInstanceSc) {
            if (!this.pendingFiles.length) return;
            let ok = 0;
            const errors = [];
            for (const file of this.pendingFiles) {
                try {
                    const fd = new FormData();
                    fd.append('file', file);
                    fd.append('context_type', 'form_attachment');
                    fd.append('context_id', formInstanceSc);
                    const res = await fetch('/api/files/upload', { method: 'POST', body: fd });
                    const data = await res.json();
                    if (data.success) {
                        ok++;
                    } else {
                        errors.push(file.name + ': ' + (data.message || '上傳失敗'));
                    }
                } catch (e) {
                    errors.push(file.name + ': 上傳失敗');
                }
            }
            if (errors.length > 0) {
                this.showToast(errors.join('\n'), 'error');
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
                    // 表單建立成功後上傳附件
                    const fiSc = data.data?.form_instance_secure_code;
                    if (fiSc && this.pendingFiles.length > 0) {
                        await this._uploadPendingFiles(fiSc);
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

            // 初始化附件（簽核者可上傳）
            const fiSc = this.currentApproval?.form_instance_secure_code;
            const attEl = document.getElementById('approval-form-attachments');
            if (attEl && fiSc && typeof BkFileAttachment !== 'undefined') {
                this._approvalAttachment = new BkFileAttachment(attEl, {
                    contextType: 'form_attachment',
                    contextId: fiSc,
                    readonly: false,
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
            // 回復偽刪除的附件（best-effort）
            const fiSc = this.currentApproval?.form_instance_secure_code;
            if (fiSc) {
                fetch('/api/files/revert-deletes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ context_id: fiSc }),
                }).catch(() => {});
            }

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

        /**
         * 取得可見的決策選項
         */
        get visibleDecisionOptions() {
            if (!this.currentApproval?.use_custom_decisions) return [];
            const paths = this.currentApproval?.available_paths || [];
            return paths.filter(opt => this.isOptionVisible(opt));
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

        // =================================================================
        // 批次簽核
        // =================================================================

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
         * 全選（僅選取與目前 batch key 相容的項目；若無 key 則以第��筆為準）
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

        /**
         * 取得批次簽核中選取項目的摘要資訊
         */
        get batchSelectedItems() {
            return this.pendingApprovals.filter(i => this.batchSelected.includes(i.queue_secure_code));
        },

        // =================================================================
        // 簽核片語
        // =================================================================

        async loadCannedMessages() {
            try {
                const res = await fetch('/api/form-center/canned-messages');
                const data = await res.json();
                if (data.success) this.cannedMessages = data.data || [];
            } catch (e) { console.error('載入簽核片語失敗:', e); }
        },

        /**
         * 追加簽核片語到指定 model（approvalComment 或 batchApprovalComment）
         */
        applyCannedMessage(text, target) {
            const prop = target || 'approvalComment';
            if (this[prop] && !this[prop].endsWith('\n') && this[prop].length > 0) {
                this[prop] += '\n';
            }
            this[prop] += text;
        },

        async addCannedMessage() {
            const text = (this.cannedNewText || '').trim();
            if (!text) return;
            try {
                const res = await fetch('/api/form-center/canned-messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await res.json();
                if (data.success) {
                    this.cannedMessages.push(data.data);
                    this.cannedNewText = '';
                } else {
                    this.showToast(data.error || '新增失敗', 'error');
                }
            } catch (e) { this.showToast('新增失敗', 'error'); }
        },

        startEditCanned(msg) {
            this.cannedEditId = msg.secure_code;
            this.cannedEditText = msg.text;
        },

        cancelEditCanned() {
            this.cannedEditId = null;
            this.cannedEditText = '';
        },

        async saveEditCanned(sc) {
            const text = (this.cannedEditText || '').trim();
            if (!text) return;
            try {
                const res = await fetch(`/api/form-center/canned-messages/${sc}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await res.json();
                if (data.success) {
                    const idx = this.cannedMessages.findIndex(m => m.secure_code === sc);
                    if (idx >= 0) this.cannedMessages[idx] = data.data;
                    this.cannedEditId = null;
                    this.cannedEditText = '';
                } else {
                    this.showToast(data.error || '修改失敗', 'error');
                }
            } catch (e) { this.showToast('修改失敗', 'error'); }
        },

        async deleteCannedMessage(sc) {
            if (!confirm('確定刪除此簽核片語？')) return;
            try {
                const res = await fetch(`/api/form-center/canned-messages/${sc}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    this.cannedMessages = this.cannedMessages.filter(m => m.secure_code !== sc);
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) { this.showToast('刪除失敗', 'error'); }
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
            return BkTime.format(dateStr, 'short');
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
            // 舊格式 TEST-20260127-0001 / FORM-20260127-0001 -> 0127-0001
            if (serial.startsWith('TEST-') || serial.startsWith('FORM-')) {
                const parts = serial.split('-');
                if (parts.length >= 3) {
                    const date = parts[1];
                    const seq = parts[2];
                    return date.slice(4) + '-' + seq;
                }
            }
            // 新格式（企業自訂，如 DEF-2603-00001）直接顯示
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
            if (this.monitorFlowChartCy) {
                this.monitorFlowChartCy.destroy();
                this.monitorFlowChartCy = null;
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

        // 切換到流程總圖頁籤（監控對話框內）
        async switchToMonitorFlowChart() {
            this.monitorPage = 'flowChart';
            // 等兩次 nextTick：第一次讓 Alpine 更新 x-show，第二次讓瀏覽器完成 layout
            await this.$nextTick();
            await this.$nextTick();

            const mainTab = this.workflowTabs.find(t => t.is_main) || this.workflowTabs[0];
            if (!mainTab) return;

            // graph 可能在 tab 物件上或在 workflowGraphCache 中
            const graph = mainTab.graph || this.workflowGraphCache[mainTab.instance_id];
            if (!graph) return;

            const codeToTab = {};
            this.workflowTabs.forEach(t => {
                if (t.workflow_code) {
                    if (!t.graph && this.workflowGraphCache[t.instance_id]) {
                        t.graph = this.workflowGraphCache[t.instance_id];
                    }
                    codeToTab[t.workflow_code] = t;
                }
            });

            const flatResult = this._fcFlattenGraph(graph, codeToTab, 0, '', null);
            const finalResult = this._fcApplyReplace(flatResult);
            this._fcApplyStatus(finalResult, { execution_history: this.monitorStatus.executionHistory });

            if (this.monitorFlowChartCy) {
                this.monitorFlowChartCy.destroy();
            }
            this.monitorFlowChartCy = this._fcRenderCytoscape('cy-monitor-flowchart', finalResult);
        },

        // === 流程總圖共用渲染 ===

        _fcFlattenGraph(graph, codeToTab, depth, prefix, parentGroupId) {
            if (!graph) return { nodes: [], edges: [], groups: [] };

            let nodes = (graph.nodes || []).filter(n => n.type !== 'group');
            let edges = [...(graph.edges || [])];
            const groups = [];

            if (prefix) {
                nodes = nodes.map(n => ({
                    ...n, id: prefix + n.id,
                    position: { ...(n.position || { x: 0, y: 0 }) },
                    config: n.config
                }));
                edges = edges.map((e, i) => ({
                    ...e, id: prefix + (e.id || `e${i}`),
                    source: prefix + e.source, target: prefix + e.target
                }));
            }
            if (parentGroupId) nodes.forEach(n => { n.parent = parentGroupId; });

            const sfNodes = nodes.filter(n => n.type === 'Subflow' || n.type === 'SubFlow');
            for (const sfNode of sfNodes) {
                const origNode = prefix
                    ? (graph.nodes || []).find(n => (prefix + n.id) === sfNode.id)
                    : sfNode;
                const childFlowId = origNode?.config?.childFlowId;
                if (!childFlowId) continue;

                const childTab = codeToTab[childFlowId];
                if (!childTab || !childTab.graph) continue;

                const subGraph = childTab.graph;
                const subRealNodes = (subGraph.nodes || []).filter(n => n.type !== 'group');
                if (subRealNodes.length === 0) continue;

                let cx = 0, cy = 0;
                subRealNodes.forEach(n => { cx += (n.position?.x || 0); cy += (n.position?.y || 0); });
                cx /= subRealNodes.length; cy /= subRealNodes.length;
                const offsetX = sfNode.position.x - cx;
                const offsetY = sfNode.position.y - cy + 180 + depth * 40;

                const groupId = `group_${sfNode.id}`;
                groups.push({ id: groupId, label: childTab.name || '子流程', parent: parentGroupId || null, level: Math.min(depth, _FC_GROUP_COLORS.length - 1) });

                const subPrefix = `sf${depth}_${sfNode.id}_`;
                const subResult = this._fcFlattenGraph(subGraph, codeToTab, depth + 1, subPrefix, groupId);

                subResult.nodes.forEach(n => { n.position.x += offsetX; n.position.y += offsetY; });

                const subStartId = subResult.nodes.find(n => n.type === 'Start')?.id;
                const subEndIds = subResult.nodes.filter(n => n.type === 'End').map(n => n.id);

                if (subStartId) edges.forEach(e => { if (e.target === sfNode.id) e.target = subStartId; });
                const outEdges = edges.filter(e => e.source === sfNode.id);
                edges = edges.filter(e => e.source !== sfNode.id);
                for (const endId of subEndIds) {
                    for (const out of outEdges) {
                        edges.push({ id: `f_${endId}_${out.target}_${Math.random().toString(36).substr(2,5)}`, source: endId, target: out.target, label: '' });
                    }
                }

                nodes = nodes.filter(n => n.id !== sfNode.id);
                nodes.push(...subResult.nodes);
                edges.push(...subResult.edges);
                groups.push(...subResult.groups);
            }
            return { nodes, edges, groups };
        },

        _fcApplyReplace(flatResult) {
            const nodeMap = {};
            flatResult.nodes.forEach(n => { nodeMap[n.id] = n; });

            const resultNodes = flatResult.nodes.map(node => {
                if (_FC_VISIBLE_TYPES.has(node.type)) {
                    return { ...node, isSystem: false };
                }
                return { ...node, originalType: node.type, type: 'system', label: _FC_REPLACE_LABEL, isSystem: true };
            });

            const resultEdges = flatResult.edges.map((e, i) => ({
                id: e.id || `e-${i}`, source: e.source, target: e.target, label: e.label || '',
                isSystem: (nodeMap[e.source] && !_FC_VISIBLE_TYPES.has(nodeMap[e.source].type)) ||
                          (nodeMap[e.target] && !_FC_VISIBLE_TYPES.has(nodeMap[e.target].type))
            }));

            return { nodes: resultNodes, edges: resultEdges, groups: flatResult.groups };
        },

        _fcApplyStatus(result, data) {
            const history = data.execution_history || [];
            const statusMap = {};
            history.forEach(h => { statusMap[h.node_id] = h.status; });

            result.nodes.forEach(n => {
                const bareId = n.id.replace(/^sf\d+_[^_]+_/, '');
                n.execStatus = statusMap[n.id] || statusMap[bareId] || null;
            });
        },

        _fcRenderCytoscape(containerId, result) {
            const elements = [];

            // 群組
            [...result.groups].sort((a, b) => (a.level || 0) - (b.level || 0)).forEach(g => {
                const gc = _FC_GROUP_COLORS[g.level || 0];
                const data = { id: g.id, label: g.label, color: gc.bg, borderColor: gc.border };
                if (g.parent) data.parent = g.parent;
                elements.push({ data });
            });

            // 節點
            result.nodes.forEach(node => {
                const isSys = node.isSystem;
                const data = {
                    id: node.id, label: node.label || node.id, type: node.type,
                    color: isSys ? _FC_SYS_COLOR : (_FC_NODE_COLORS[node.type] || _FC_NODE_COLORS['default']),
                    borderColor: isSys ? _FC_SYS_BORDER : '#333'
                };
                if (node.parent) data.parent = node.parent;

                let classes = isSys ? 'system-node' : '';
                if (node.execStatus === 'RUNNING') classes += ' node-running';
                else if (node.execStatus === 'SUCCESS') classes += ' node-completed';
                else if (['FAILED','ERROR','TIMEOUT'].includes(node.execStatus)) classes += ' node-failed';

                elements.push({ data, position: { ...node.position }, classes: classes.trim() });
            });

            // 邊
            result.edges.forEach(edge => {
                elements.push({
                    data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label || '' },
                    classes: edge.isSystem ? 'system-edge' : ''
                });
            });

            const container = document.getElementById(containerId);
            const cy = cytoscape({
                container,
                elements,
                style: [
                    { selector: 'node', style: {
                        'background-color': 'data(color)', 'label': 'data(label)',
                        'text-valign': 'center', 'text-halign': 'center', 'font-size': '10px',
                        'width': 90, 'height': 36, 'border-width': 2, 'border-color': 'data(borderColor)',
                        'text-wrap': 'wrap', 'text-max-width': '80px', 'shape': 'roundrectangle'
                    }},
                    { selector: 'node[type="Start"]', style: { 'shape': 'ellipse', 'width': 50, 'height': 50 } },
                    { selector: 'node[type="End"]', style: { 'shape': 'ellipse', 'width': 50, 'height': 50 } },
                    { selector: 'edge', style: {
                        'width': 2, 'line-color': '#bbb', 'target-arrow-color': '#bbb',
                        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'font-size': '9px'
                    }},
                    { selector: '.system-node', style: {
                        'background-color': _FC_SYS_COLOR, 'border-color': _FC_SYS_BORDER,
                        'border-style': 'dashed', 'border-width': 2, 'font-size': '9px',
                        'color': '#6b7280', 'width': 80, 'height': 28
                    }},
                    { selector: '.system-edge', style: {
                        'line-color': '#d1d5db', 'target-arrow-color': '#d1d5db',
                        'line-style': 'dashed', 'width': 1.5
                    }},
                    { selector: '.node-running', style: {
                        'background-color': '#FFC107', 'border-color': '#FF9800', 'border-width': 3
                    }},
                    { selector: '.node-completed', style: {
                        'background-color': '#4CAF50', 'border-color': '#388E3C', 'border-width': 2
                    }},
                    { selector: '.node-failed', style: {
                        'background-color': '#F44336', 'border-color': '#D32F2F', 'border-width': 3
                    }},
                    { selector: ':parent', style: {
                        'background-color': 'data(color)', 'background-opacity': 1,
                        'border-color': 'data(borderColor)', 'border-width': 2, 'border-style': 'dashed',
                        'label': 'data(label)', 'text-valign': 'top', 'text-halign': 'center',
                        'font-size': '11px', 'font-weight': 'bold', 'color': 'data(borderColor)',
                        'padding': '25px', 'shape': 'roundrectangle', 'text-margin-y': '-8px'
                    }}
                ],
                layout: { name: 'preset' },
                userZoomingEnabled: true, userPanningEnabled: true, boxSelectionEnabled: false
            });

            // 延遲 fit：確保容器已完成 layout 且有實際尺寸
            const delayedFit = () => {
                if (container.offsetWidth > 0 && container.offsetHeight > 0) {
                    cy.resize();
                    cy.fit(null, 50);
                } else {
                    // 容器尚未可見，重試
                    requestAnimationFrame(delayedFit);
                }
            };
            requestAnimationFrame(delayedFit);

            return cy;
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

        // 共用：渲染唯讀表��
        async _renderFormReadOnly(containerId, schema, formData, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return null;

            // 補丁 file component storage
            if (window.BkFileProvider) BkFileProvider.patchSchema(schema);

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
            return BkTime.format(dateStr, 'time');
        },

        // =============================================================
        // 統一底圖/寬度渲染
        // =============================================================

        /**
         * 動態套用欄位權限覆蓋（來自 input_variables 評估結果）
         * @param {Object} formInstance - Formio form instance
         * @param {Object} overrides - { fieldKey: 'editable'|'readonly'|'hidden' }
         */
        _applyFieldPermissionOverrides(formInstance, overrides) {
            if (!formInstance || !overrides) return;

            const applyToComponent = (comp) => {
                const perm = overrides[comp.key];
                if (!perm) return;

                if (perm === 'hidden') {
                    comp.visible = false;
                } else if (perm === 'editable') {
                    comp.disabled = false;
                    comp.visible = true;
                } else if (perm === 'readonly') {
                    comp.disabled = true;
                    comp.visible = true;
                }
            };

            try {
                formInstance.everyComponent(applyToComponent);
                formInstance.redraw();
            } catch (e) {
                console.warn('動態欄位權限套用失敗:', e);
            }
        },

        applyFormBackground(containerId, builderConfig) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // 白色表單區域 + 陰影（匹配設計器 preview 行為）
            container.style.backgroundColor = '#ffffff';
            container.style.padding = '20px';
            container.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
            container.style.minHeight = '400px';

            // 套用風格主題
            const formTheme = builderConfig?.formTheme;
            if (formTheme && formTheme !== 'default') {
                container.setAttribute('data-form-theme', formTheme);
            } else {
                container.removeAttribute('data-form-theme');
            }

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
                container.removeAttribute('data-form-theme');
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

        async openFlowOverview(item) {
            this.flowOverviewLoading = true;
            this.flowOverviewError = null;
            this.flowOverviewInfo = {};
            this.showFlowOverviewModal = true;

            await this.$nextTick();

            try {
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const res = await fetch(`/api/form-center/executions/${instanceId}/path`);
                const result = await res.json();

                if (!result.success) {
                    this.flowOverviewError = result.error || '載入失敗';
                    this.flowOverviewLoading = false;
                    return;
                }

                const data = result.data;
                const tabs = data.workflow_tabs || [];
                const mainTab = tabs.find(t => t.is_main) || tabs[0];

                if (!mainTab) {
                    this.flowOverviewError = '找不到流程圖資料';
                    this.flowOverviewLoading = false;
                    return;
                }

                this.flowOverviewInfo = {
                    executionCode: mainTab.execution_code || '',
                    workflowName: mainTab.name || '',
                    flowStatus: data.instance_status || '-'
                };

                const codeToTab = {};
                tabs.forEach(t => { if (t.workflow_code) codeToTab[t.workflow_code] = t; });

                const flatResult = this._fcFlattenGraph(mainTab.graph, codeToTab, 0, '', null);
                const finalResult = this._fcApplyReplace(flatResult);
                this._fcApplyStatus(finalResult, data);

                this.flowOverviewLoading = false;
                await this.$nextTick();

                if (this.flowOverviewCy) this.flowOverviewCy.destroy();
                this.flowOverviewCy = this._fcRenderCytoscape('cy-flow-overview', finalResult);

            } catch (e) {
                this.flowOverviewError = '載入錯誤: ' + e.message;
                this.flowOverviewLoading = false;
            }
        },

        closeFlowOverviewModal() {
            if (this.flowOverviewCy) {
                this.flowOverviewCy.destroy();
                this.flowOverviewCy = null;
            }
            this.showFlowOverviewModal = false;
            this.flowOverviewInfo = {};
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

        // =================================================================
        // 欄位顯示設定
        // =================================================================

        // 欄位定義（column_key -> 預設值、標籤、說明）
        _columnDefs: {
            serial_number:  { label: '單號',       defaultWidth: 140 },
            form_name:      { label: '表單名稱',    defaultWidth: 120 },
            subject:        { label: '主旨',        defaultWidth: null, flex: true, noHide: true },
            applicant:      { label: '發起人',      defaultWidth: 100 },
            category:       { label: '表單類別',    defaultWidth: 80 },
            current_node:   { label: '目前關卡',    defaultWidth: 140 },
            wait_time:      { label: '等待時間',    defaultWidth: 150 },
            submit_time:    { label: '送單時間',    defaultWidth: 130 },
            signed_elapsed: { label: '簽核後歷時',  defaultWidth: 130 },
            end_time:       { label: '結束時間',    defaultWidth: 130 },
            status:         { label: '狀態',        defaultWidth: 70 },
            duration:       { label: '流程耗時',    defaultWidth: 100 },
            actions:        { label: '操作',        defaultWidth: 110, noHide: true },
        },

        async loadColumnConfig() {
            try {
                const res = await fetch('/api/form-center/column-config');
                const data = await res.json();
                if (data.success) {
                    this.columnConfig = data.data.config || {};
                }
            } catch (e) {
                console.error('載入欄位設定失敗:', e);
            }
        },

        /** 取得欄位寬度 style 字串 */
        colW(key) {
            const cfg = this.columnConfig[key];
            const def = this._columnDefs[key];
            if (def && def.flex) return '';
            const w = cfg ? cfg.width : (def ? def.defaultWidth : null);
            return w ? `width: ${w}px;` : '';
        },

        /** 欄位是否可見 */
        colV(key) {
            const cfg = this.columnConfig[key];
            if (!cfg) return true;
            return !cfg.hidden;
        },

        // --- 管理員：欄位設定 Modal ---

        async openColumnConfigModal() {
            this.showColumnConfigModal = true;
            this.savingColumnConfig = false;
            try {
                const res = await fetch('/api/form-center/column-config/all');
                const data = await res.json();
                if (data.success) {
                    this.columnConfigLocales = data.data.configs.map(c => c.locale);
                    if (!this.columnConfigLocales.includes('*')) {
                        this.columnConfigLocales.unshift('*');
                    }
                    // 載入第一個有設定的語系，或 '*'
                    this.columnConfigLocale = this.columnConfigLocales[0] || '*';
                    this._loadConfigForLocale(data.data);
                }
            } catch (e) {
                console.error('載入欄位設定失敗:', e);
            }
        },

        _loadConfigForLocale(allData) {
            const existing = (allData.configs || []).find(c => c.locale === this.columnConfigLocale);
            const saved = existing ? existing.config : {};
            const defaults = allData.defaults || {};
            const editing = {};
            for (const [key, def] of Object.entries(this._columnDefs)) {
                const s = saved[key] || defaults[key] || {};
                editing[key] = {
                    label: def.label,
                    width: s.width != null ? s.width : def.defaultWidth,
                    hidden: !!s.hidden,
                    flex: !!def.flex,
                    noHide: !!def.noHide,
                };
            }
            this.columnConfigEditing = editing;
        },

        async switchColumnConfigLocale(locale) {
            this.columnConfigLocale = locale;
            try {
                const res = await fetch('/api/form-center/column-config/all');
                const data = await res.json();
                if (data.success) {
                    this._loadConfigForLocale(data.data);
                }
            } catch (e) {
                console.error('載入語系設定失敗:', e);
            }
        },

        addColumnConfigLocale(locale) {
            if (!locale || this.columnConfigLocales.includes(locale)) return;
            this.columnConfigLocales.push(locale);
            this.columnConfigLocale = locale;
            // 初始化為預設值
            const editing = {};
            for (const [key, def] of Object.entries(this._columnDefs)) {
                editing[key] = {
                    label: def.label,
                    width: def.defaultWidth,
                    hidden: false,
                    flex: !!def.flex,
                    noHide: !!def.noHide,
                };
            }
            this.columnConfigEditing = editing;
        },

        async saveColumnConfig() {
            this.savingColumnConfig = true;
            try {
                const config = {};
                for (const [key, val] of Object.entries(this.columnConfigEditing)) {
                    config[key] = {
                        width: val.flex ? null : (parseInt(val.width) || null),
                        hidden: !!val.hidden,
                    };
                }
                const res = await fetch('/api/form-center/column-config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        locale: this.columnConfigLocale,
                        config: config
                    })
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('欄位設定已儲存');
                    // 重新載入當前用戶的設定
                    await this.loadColumnConfig();
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗', 'error');
            } finally {
                this.savingColumnConfig = false;
            }
        },

        // (end of included methods)
    };
}
