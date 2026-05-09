/* od-intake-keys.js -- Intake Keys 管理頁 */

const API = window.__OD_API;

function odIntakeKeys() {
    return {
        loading: true,
        keys: [],
        availableSources: [
            'suricata', 'coraza', 'falco', 'crowdsec',
            'vector', 'wazuh', 'zeek', 'custom',
        ],
        createModal: false,
        newKey: { name: '', sources: [], expires_at: '', created_key_id: '' },
        newSecret: '',

        async load() {
            this.loading = true;
            const r = await OD.fetchJSON(`${API}/intake-keys`);
            if (!r.ok) { alert('載入失敗: ' + r.status); this.loading = false; return; }
            this.keys = r.body.keys || [];
            this.loading = false;
        },

        openCreate() {
            this.newKey = { name: '', sources: [], expires_at: '', created_key_id: '' };
            this.newSecret = '';
            this.createModal = true;
        },
        closeCreate() {
            this.createModal = false;
            if (this.newSecret) this.load();
        },
        toggleSource(s) {
            const i = this.newKey.sources.indexOf(s);
            if (i >= 0) this.newKey.sources.splice(i, 1);
            else this.newKey.sources.push(s);
        },
        async submit() {
            if (!this.newKey.name.trim()) { alert('名稱必填'); return; }
            if (this.newKey.sources.length === 0) { alert('至少選一個 source_system'); return; }
            const r = await OD.fetchJSON(`${API}/intake-keys`, {
                method: 'POST',
                body: JSON.stringify({
                    name: this.newKey.name,
                    allowed_source_systems: this.newKey.sources,
                    expires_at: this.newKey.expires_at || null,
                }),
            });
            if (!r.ok) {
                alert('建立失敗: ' + (r.body?.message || r.body?.error || r.status));
                return;
            }
            this.newSecret = r.body.secret_b64;
            this.newKey.created_key_id = r.body.key.key_id;
        },

        formatTime: OD.formatTime,

        async revoke(k) {
            if (!confirm(`確定撤銷金鑰「${k.name}」?\n撤銷後對方再用此金鑰簽章會直接 401。`)) return;
            const r = await OD.fetchJSON(`${API}/intake-keys/${k.secure_code}`,
                                         { method: 'DELETE' });
            if (!r.ok) { alert('撤銷失敗: ' + r.status); return; }
            this.load();
        },
    };
}
