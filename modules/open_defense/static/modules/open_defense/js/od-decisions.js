/* od-decisions.js -- 決策列表 + 手動撤銷 */

const API = window.__OD_API;

function odDecisions() {
    return {
        activeTab: 'active',
        loading: true,
        activeLoading: true,
        decisions: [],
        activeRows: [],
        orphanRows: [],
        activeSummary: {},
        bridge: { available: true },
        expandedTarget: null,
        historyCache: {},
        historyLoading: {},
        filters: { status: 'pending', action: '', target: '', limit: 100 },
        OD: window.OD,

        async refresh() {
            if (this.activeTab === 'active') {
                await this.loadActive();
                return;
            }
            await this.load();
        },

        async loadActive() {
            this.activeLoading = true;
            const r = await OD.fetchJSON(`${API}/decisions/enforcement-state`);
            if (!r.ok) {
                alert(__('生效中名單載入失敗: {status}', { status: r.status }));
                this.activeLoading = false;
                return;
            }
            this.activeRows = r.body.active || [];
            this.orphanRows = r.body.orphans || [];
            this.activeSummary = r.body.summary || {};
            this.bridge = r.body.bridge || { available: false };
            this.activeLoading = false;
        },

        async load() {
            this.loading = true;
            const params = new URLSearchParams();
            for (const [k, v] of Object.entries(this.filters)) {
                if (v !== '' && v !== null && v !== undefined) params.set(k, v);
            }
            const r = await OD.fetchJSON(`${API}/decisions?${params}`);
            if (!r.ok) { alert(__('載入失敗: {status}', { status: r.status })); this.loading = false; return; }
            this.decisions = r.body.decisions || [];
            this.loading = false;
        },

        async revoke(d) {
            if (typeof BkCaps !== 'undefined' && !BkCaps.can('open_defense.decision.write')) return;
            const reason = prompt(__('撤銷 {action} {targetType}/{targetValue}?\n填入撤銷理由(會產生 unblock 決策):', {
                action: d.action,
                targetType: d.target_type,
                targetValue: d.target_value,
            }));
            if (reason === null) return;
            const r = await OD.fetchJSON(`${API}/decisions/${d.secure_code}/revoke`, {
                method: 'POST',
                body: JSON.stringify({ reason: reason || __('人工手動撤銷') }),
            });
            if (!r.ok) {
                alert(__('撤銷失敗: {message}', { message: r.body?.message || r.body?.error || r.status }));
                return;
            }
            alert(__('已產生 unblock 決策: {code}', { code: r.body.unblock_secure_code }));
            this.load();
        },

        rowKey(row) {
            return `${row.target_type}:${row.target_value}`;
        },

        isExpanded(row) {
            return this.expandedTarget === this.rowKey(row);
        },

        async toggleHistory(row) {
            const key = this.rowKey(row);
            if (this.expandedTarget === key) {
                this.expandedTarget = null;
                return;
            }
            this.expandedTarget = key;
            if (this.historyCache[key]) return;

            this.historyLoading[key] = true;
            const params = new URLSearchParams({
                target: row.target_value,
                target_type: row.target_type,
                limit: '200',
            });
            const r = await OD.fetchJSON(`${API}/decisions/target-history?${params}`);
            if (!r.ok) {
                alert(__('時間軸載入失敗: {status}', { status: r.status }));
                this.historyLoading[key] = false;
                return;
            }
            this.historyCache[key] = r.body.history || [];
            this.historyLoading[key] = false;
        },

        verdictLabel(verdict) {
            if (verdict === 'in_sync') return __('同步');
            if (verdict === 'missing_downstream') return __('缺漏');
            if (verdict === 'orphan_downstream') return __('殘留');
            return __('未對帳');
        },

        verdictClass(verdict) {
            if (verdict === 'in_sync') return 'od-badge-applied';
            if (verdict === 'missing_downstream') return 'od-badge-failed';
            if (verdict === 'orphan_downstream') return 'od-badge-failed';
            return 'od-badge-picked';
        },

        formatRemaining(seconds) {
            if (seconds === null || seconds === undefined) return '';
            if (seconds <= 0) return __('已到期');
            if (seconds < 60) return __('剩 {count} 秒', { count: seconds });
            if (seconds < 3600) return __('剩 {count} 分', { count: Math.floor(seconds / 60) });
            return __('剩 {count} 小時', { count: Math.floor(seconds / 3600) });
        },
    };
}
