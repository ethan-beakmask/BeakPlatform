/* od-intake-keys.js -- Intake Keys 遺留清單頁(P2 起唯讀)
 * 金鑰管理已遷移至 /security/api-keys/(scope: od_intake) */

const API = window.__OD_API;

function odIntakeKeys() {
    return {
        loading: true,
        keys: [],
        createModal: false,

        async load() {
            this.loading = true;
            const r = await OD.fetchJSON(`${API}/intake-keys`);
            if (!r.ok) { alert('載入失敗: ' + r.status); this.loading = false; return; }
            this.keys = r.body.keys || [];
            this.loading = false;
        },

        formatTime: OD.formatTime,
    };
}
