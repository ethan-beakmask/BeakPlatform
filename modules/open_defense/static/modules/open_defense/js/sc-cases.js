/* sc-cases.js -- 資安案件處置中心（Alpine.js）
 * 簽核動作直接走既有 /api/form-center/pending-tasks API（不 clone 引擎）。
 */
function scCases() {
    const BP = window.__BP || '';
    return {
        stats: {},
        cases: [],
        statusFilter: 'open',
        // 值班預設視角：只列輪到自己簽核的案件（僅對「進行中」生效，
        // 已結案案件沒有 WAITING 節點，過濾後必然全空）
        onlyMine: true,
        selected: null,        // 清單項
        detail: null,          // pending-tasks 詳情（進行中案件才有）
        payload: null,         // native payload 明細與原始欄位
        decisions: [],
        comment: '',
        acting: false,
        loading: false,
        payloadLoading: false,
        activeTab: 'summary',
        _clock: null,
        now: Date.now(),

        async load() {
            this.loading = true;
            const mine = (this.onlyMine && this.statusFilter === 'open') ? '&mine=1' : '';
            try {
                const [s, c] = await Promise.all([
                    OD.fetchJSON(`${BP}/api/open_defense/cases/stats`),
                    OD.fetchJSON(
                        `${BP}/api/open_defense/cases?status=${this.statusFilter}${mine}`),
                ]);
                if (s.body?.success) this.stats = s.body.data;
                if (c.body?.success) this.cases = c.body.data;
            } finally {
                this.loading = false;
            }
            if (!this._clock) {
                this._clock = setInterval(() => { this.now = Date.now(); }, 1000);
            }
        },

        async setFilter(f) {
            this.statusFilter = f;
            this._resetSelection();
            await this.load();
        },

        /** 切換「僅我可簽核 / 全部案件」（只在進行中視角有按鈕） */
        async toggleMine() {
            this.onlyMine = !this.onlyMine;
            this._resetSelection();
            await this.load();
        },

        _resetSelection() {
            this.selected = null;
            this.detail = null;
            this.payload = null;
            this.activeTab = 'summary';
        },

        async selectCase(c) {
            this.selected = c;
            this.detail = null;
            this.payload = null;
            this.decisions = [];
            this.comment = '';
            this.activeTab = 'summary';
            this.payloadLoading = true;

            const wiSc = c.workflow_instance_secure_code;
            const jobs = [
                OD.fetchJSON(`${BP}/api/open_defense/cases/${wiSc}/decisions`),
                OD.fetchJSON(`${BP}/api/open_defense/cases/${wiSc}/payload`),
            ];
            if (c.waiting_node) {
                jobs.push(OD.fetchJSON(
                    `${BP}/api/form-center/pending-tasks/${c.waiting_node.queue_secure_code}`));
            }
            try {
                const [d, payload, pending] = await Promise.all(jobs);
                if (d.body?.success) this.decisions = d.body.data;
                if (payload.body?.success) this.payload = payload.body.data;
                if (pending && pending.body?.success) this.detail = pending.body.data;
                this.ensureActiveTab();
            } finally {
                this.payloadLoading = false;
            }

            this.$nextTick(() => {
                if (window.BkEgress) BkEgress.bind(document.getElementById('sc-detail'));
            });
        },

        /** 1-click 處置：鎖定 + 簽核一鍵完成（decision 選項來自流程定義） */
        async act(option) {
            if (this.acting || !this.selected?.waiting_node) return;
            const minLen = this.detail?.min_comment_length || 0;
            if (minLen > 0 && this.comment.trim().length < minLen) {
                alert(__('簽核意見至少需要 {n} 字', { n: minLen }));
                return;
            }
            if (!confirm(__('確定執行「{action}」？', { action: option.label }))) return;

            this.acting = true;
            const qsc = this.selected.waiting_node.queue_secure_code;
            try {
                const lock = await OD.fetchJSON(
                    `${BP}/api/form-center/pending-tasks/${qsc}/lock`, { method: 'POST' });
                if (!lock.body?.success) {
                    alert(lock.body?.error || __('無法取得簽核鎖定'));
                    return;
                }
                // target_edges 為空且 style=danger → 終態退回（誤判結案語意）
                const decision = (option.style === 'danger' &&
                    (!option.target_edges || option.target_edges.length === 0))
                    ? 'rejected' : 'approved';
                const r = await OD.fetchJSON(
                    `${BP}/api/form-center/pending-tasks/${qsc}/approve`, {
                        method: 'POST',
                        body: JSON.stringify({
                            decision: decision,
                            selected_edges: option.target_edges || [],
                            selected_option_value: option.value,
                            comment: this.comment,
                        }),
                    });
                if (r.body?.success) {
                    this.selected = null;
                    this.detail = null;
                    await this.load();
                } else {
                    alert(r.body?.error || __('處置失敗'));
                    OD.fetchJSON(`${BP}/api/form-center/pending-tasks/${qsc}/lock`,
                        { method: 'DELETE' });
                }
            } finally {
                this.acting = false;
            }
        },

        /** 決策選項清單（自訂決策節點才有） */
        get actionOptions() {
            return this.detail?.available_paths || [];
        },
        /* 純 getter：不可在此寫 this.activeTab。
         * x-for 會在 effect 中讀取本 getter，在 effect 內寫入自己的依賴會讓
         * Alpine 的更新順序不穩定 —— 實測症狀是點分頁後 activeTab 已經改了、
         * 但 x-show 沒有跟著重算，畫面停在前一個分頁。 */
        get tabs() {
            const items = [{ id: 'summary', label: __('案件摘要') }];
            if (this.payload?.detail?.rows?.length) {
                items.push({ id: 'detail', label: __('事件明細') });
            }
            if (this.payload?.fields?.length) {
                items.push({ id: 'fields', label: __('原始欄位') });
            }
            return items;
        },
        ensureActiveTab() {
            if (!this.tabs.some((tab) => tab.id === this.activeTab)) {
                this.activeTab = 'summary';
            }
        },

        // ---- 顯示 helper ----
        sevNum(v) {
            return (v && typeof v === 'object') ? '?' : (v ?? '-');
        },
        val(v) {
            if (window.BkEgress && BkEgress.isMasked(v)) return BkEgress.render(v);
            if (v === null || v === undefined || v === '') return '-';
            const div = document.createElement('div');
            div.textContent = String(v);
            return div.innerHTML;
        },
        cellVal(row, key) {
            return this.val(row ? row[key] : undefined);
        },
        riskClass(score) {
            const n = parseInt(score, 10) || 0;
            return n >= 60 ? 'high' : (n >= 30 ? 'mid' : 'low');
        },
        fmtTime(iso) { return OD.formatTime(iso, 'short'); },

        /** SLA 倒數文字與樣式（起點 submitted_at，時限依嚴重度由後端給定） */
        slaInfo(c) {
            if (!c.sla_minutes || !c.submitted_at || c.status !== 'RUNNING') {
                return null;
            }
            // DB 時間為 UTC 無時區後綴，補 Z 避免被當本地時間（TZ-01）
            const iso = c.submitted_at.endsWith('Z')
                ? c.submitted_at : c.submitted_at + 'Z';
            const deadline = new Date(iso).getTime() + c.sla_minutes * 60000;
            const remain = Math.floor((deadline - this.now) / 1000);
            if (remain <= 0) {
                const over = Math.floor(-remain / 60);
                return { cls: 'overdue', text: __('逾時 {n} 分', { n: over }) };
            }
            const m = Math.floor(remain / 60);
            const s = remain % 60;
            return {
                cls: remain < 300 ? 'warn' : '',
                text: `SLA ${m}:${String(s).padStart(2, '0')}`,
            };
        },
    };
}
