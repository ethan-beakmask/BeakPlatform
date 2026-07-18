/* od-decisions.js -- 決策列表 + 手動撤銷 */

const API = window.__OD_API;

function odDecisions() {
    return {
        loading: true,
        decisions: [],
        filters: { status: 'pending', action: '', target: '', limit: 100 },
        OD: window.OD,

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
    };
}
