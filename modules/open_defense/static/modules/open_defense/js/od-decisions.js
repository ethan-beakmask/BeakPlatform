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
            if (!r.ok) { alert('載入失敗: ' + r.status); this.loading = false; return; }
            this.decisions = r.body.decisions || [];
            this.loading = false;
        },

        async revoke(d) {
            const reason = prompt(`撤銷 ${d.action} ${d.target_type}/${d.target_value}?\n填入撤銷理由(會產生 unblock 決策):`);
            if (reason === null) return;
            const r = await OD.fetchJSON(`${API}/decisions/${d.secure_code}/revoke`, {
                method: 'POST',
                body: JSON.stringify({ reason: reason || '人工手動撤銷' }),
            });
            if (!r.ok) {
                alert('撤銷失敗: ' + (r.body?.message || r.body?.error || r.status));
                return;
            }
            alert(`已產生 unblock 決策: ${r.body.unblock_secure_code}`);
            this.load();
        },
    };
}
