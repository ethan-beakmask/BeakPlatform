/* od-dashboard.js */
const API = window.__OD_API;

function odDashboard() {
    return {
        stats: {},
        recent_events: [],
        recent_pending: [],
        OD: window.OD,

        async load() {
            const r = await OD.fetchJSON(`${API}/dashboard/stats`);
            if (!r.ok) { alert('載入失敗: ' + r.status); return; }
            this.stats = r.body.stats || {};
            this.recent_events = r.body.recent_events || [];
            this.recent_pending = r.body.recent_pending || [];
        },
    };
}
