/**
 * form_center.html — Alpine.js Manager
 * Window Bridge: reads window.__USER_TIMEZONE
 *
 * Mixin 載入順序 (HTML 中須先於此檔載入):
 *   fc-flow-overview.js, fc-data-loader.js, fc-utils.js, fc-form-render.js,
 *   fc-form-fill.js, fc-approval.js, fc-batch-approval.js, fc-canned-messages.js,
 *   fc-monitor.js, fc-read-form.js, fc-column-config.js
 */

/**
 * 合併 mixin 到目標物件，保留 getter/setter descriptor（避免 spread 觸發 getter 執行）
 */
function _fcMergeMixin(target, mixin) {
    const descriptors = Object.getOwnPropertyDescriptors(mixin);
    Object.defineProperties(target, descriptors);
}

function formCenterManager() {
    const self = {
        // =============================================================
        // 核心 State (不屬於任何 mixin 的全域狀態)
        // =============================================================

        // 分類選擇（二層）
        selectedParent: null,
        selectedChild: null,

        // 檢視模式
        viewMode: 'dashboard',
        listTab: 'pending',
        listSubTab: 'mine',
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

        // Toast
        toast: { show: false, message: '', type: 'success' },

        // 管理員旗標
        isAdmin: window.__IS_ADMIN || false,
        isSystemAdmin: window.__IS_SYSTEM_ADMIN || false,
        userRoleCodes: window.__USER_ROLE_CODES || [],
        currentUserSc: window.__USER_SC || '',

        // 自動刷新
        autoRefreshInterval: null,
        _refreshFailCount: 0,
        _refreshBaseDelay: 5000,
        _refreshMaxDelay: 60000,
        _visibilityHandler: null,

        // =============================================================
        // Computed — 權限
        // =============================================================

        get canViewExecution() {
            return this.isSystemAdmin || this.isAdmin || this.userRoleCodes.includes('FLOW_DESIGNER');
        },

        get isExternalUser() {
            return this.userRoleCodes.includes('EXTERNAL_USERS');
        },

        // =============================================================
        // Computed — 分類
        // =============================================================

        get currentChildren() {
            if (!this.selectedParent || this.selectedParent === 'SYS_CAT_OTHER') return [];
            const parent = this.parentCategories.find(c => c.secure_code === this.selectedParent);
            if (!parent) return [];
            const children = [...(parent.children || [])];
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

            if (this.selectedChild === '__child_uncategorized__') {
                return this.availableForms.filter(f => f.category_secure_code === parent.secure_code);
            }
            if (this.selectedChild) {
                return this.availableForms.filter(f => f.category_secure_code === this.selectedChild);
            }
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
            const children = this.currentChildren;
            this.selectedChild = children.length > 0 ? children[0].secure_code : null;
        },

        getFormCountByChild(childSc) {
            if (childSc === '__child_uncategorized__') {
                return this.availableForms.filter(f => f.category_secure_code === this.selectedParent).length;
            }
            return this.availableForms.filter(f => f.category_secure_code === childSc).length;
        },

        // =============================================================
        // Computed — 分頁
        // =============================================================

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

        // =============================================================
        // Computed — 清單模式
        // =============================================================

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

        // =============================================================
        // Lifecycle
        // =============================================================

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

        // =============================================================
        // 自動刷新
        // =============================================================

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
    };

    // Mixin 合併（使用 defineProperties 保留 getter/setter，避免提前觸發）
    const mixins = [
        fcDataLoader(), fcUtils(), fcFormRender(), fcFormFill(),
        fcApproval(), fcBatchApproval(), fcCannedMessages(),
        fcMonitor(), fcFlowOverview(), fcReadForm(), fcColumnConfig()
    ];
    for (const mixin of mixins) {
        _fcMergeMixin(self, mixin);
    }

    return self;
}
