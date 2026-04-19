/**
 * fc-data-loader.js — 資料載入與排序 mixin
 * 由 form-center.js 拆分而來
 */
function fcDataLoader() {
    return {
        // --- State ---
        availableForms: [],
        parentCategories: [],
        pendingApprovals: [],
        trackingList: [],
        signedList: [],
        historyList: [],
        signedHistoryList: [],
        loadingForms: true,
        loadingCategories: true,
        loadingPending: true,
        loadingTracking: true,
        loadingSigned: true,
        loadingHistory: true,
        loadingSignedHistory: true,
        pendingSort: { field: 'scheduled_at', order: 'asc' },
        trackingSort: { field: 'submitted_at', order: 'asc' },
        trackingSignedSort: { field: 'submitted_at', order: 'asc' },
        historySort: { field: 'workflow_completed_at', order: 'desc' },
        historySignedSort: { field: 'workflow_completed_at', order: 'desc' },

        // --- Methods ---

        async refreshAll() {
            const safeFetch = (url) => fetch(url).then(r => r.ok ? r.json() : null).catch(() => null);
            const ps = this.pendingSort;
            const ts = this.trackingSort;
            const tss = this.trackingSignedSort;
            const hs = this.historySort;
            const hss = this.historySignedSort;
            const [forms, approvals, tracking, signed, history, signedHist] = await Promise.all([
                safeFetch('/bp/api/form-center/available-forms'),
                safeFetch(`/bp/api/form-center/pending-tasks?sort=${ps.field}&order=${ps.order}`),
                safeFetch(`/bp/api/form-center/my-forms?status=RUNNING&sort=${ts.field}&order=${ts.order}`),
                safeFetch(`/bp/api/form-center/my-forms?signed=1&status=RUNNING&sort=${tss.field}&order=${tss.order}`),
                safeFetch(`/bp/api/form-center/my-forms?status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${hs.field}&order=${hs.order}`),
                safeFetch(`/bp/api/form-center/my-forms?signed=1&status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${hss.field}&order=${hss.order}`)
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

        async loadAvailableForms() {
            this.loadingForms = true;
            try {
                const res = await fetch('/bp/api/form-center/available-forms');
                const data = await res.json();
                if (data.success) this.availableForms = data.data || [];
            } catch (e) { console.error('載入可填寫表單失敗:', e); }
            finally { this.loadingForms = false; }
        },

        async loadCategories() {
            this.loadingCategories = true;
            try {
                const res = await fetch('/bp/api/form-workflow/categories?context=form_center');
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
                const res = await fetch(`/bp/api/form-center/pending-tasks?sort=${field}&order=${order}`);
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
                const res = await fetch(`/bp/api/form-center/my-forms?status=RUNNING&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.trackingList = data.data || [];
            } catch (e) { console.error('載入追蹤失敗:', e); }
            finally { this.loadingTracking = false; }
        },

        async loadSigned() {
            this.loadingSigned = true;
            try {
                const {field, order} = this.trackingSignedSort;
                const res = await fetch(`/bp/api/form-center/my-forms?signed=1&status=RUNNING&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.signedList = data.data || [];
            } catch (e) { console.error('載入簽核追蹤失敗:', e); }
            finally { this.loadingSigned = false; }
        },

        async loadHistory() {
            this.loadingHistory = true;
            try {
                const {field, order} = this.historySort;
                const res = await fetch(`/bp/api/form-center/my-forms?status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${field}&order=${order}`);
                const data = await res.json();
                if (data.success) this.historyList = data.data || [];
            } catch (e) { console.error('載入歷史失敗:', e); }
            finally { this.loadingHistory = false; }
        },

        async loadSignedHistory() {
            this.loadingSignedHistory = true;
            try {
                const {field, order} = this.historySignedSort;
                const res = await fetch(`/bp/api/form-center/my-forms?signed=1&status=COMPLETED,ERROR,CANCELLED,REJECTED&sort=${field}&order=${order}`);
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
    };
}
