/* od-service-accounts.js */

const API = window.__OD_API;

function odServiceAccounts() {
    return {
        loading: true,
        accounts: [],
        availableEPs: [
            'crowdsec', 'nftables', 'iptables', 'cloudflare',
            'fastly', 'aws_waf', 'app_internal', 'siem_tag', 'email_relay',
        ],
        createModal: false,
        newSA: { name: '', sa_id_hint: '', eps: [], created_sa_id: '' },
        newSecret: '',
        OD: window.OD,

        async load() {
            this.loading = true;
            const r = await OD.fetchJSON(`${API}/service-accounts`);
            if (!r.ok) { alert(__('載入失敗: {status}', { status: r.status })); this.loading = false; return; }
            this.accounts = r.body.accounts || [];
            this.loading = false;
        },

        openCreate() {
            this.newSA = { name: '', sa_id_hint: '', eps: [], created_sa_id: '' };
            this.newSecret = '';
            this.createModal = true;
        },
        closeCreate() {
            this.createModal = false;
            if (this.newSecret) this.load();
        },
        toggleEP(ep) {
            const i = this.newSA.eps.indexOf(ep);
            if (i >= 0) this.newSA.eps.splice(i, 1);
            else this.newSA.eps.push(ep);
        },
        async submit() {
            if (!this.newSA.name.trim()) { alert(__('名稱必填')); return; }
            const r = await OD.fetchJSON(`${API}/service-accounts`, {
                method: 'POST',
                body: JSON.stringify({
                    name: this.newSA.name,
                    sa_id_hint: this.newSA.sa_id_hint,
                    allowed_enforcement_points: this.newSA.eps,
                }),
            });
            if (!r.ok) {
                alert(__('建立失敗: {message}', { message: r.body?.message || r.body?.error || r.status }));
                return;
            }
            this.newSecret = r.body.sa_secret_b64;
            this.newSA.created_sa_id = r.body.account.sa_id;
        },

        async unlock(a) {
            if (!confirm(__('解鎖帳號「{name}」?(會清除失敗計數)', { name: a.name }))) return;
            const r = await OD.fetchJSON(`${API}/service-accounts/${a.secure_code}/unlock`,
                                         { method: 'POST' });
            if (!r.ok) { alert(__('解鎖失敗: {status}', { status: r.status })); return; }
            this.load();
        },
        async revoke(a) {
            if (!confirm(__('撤銷帳號「{name}」?\n撤銷後所有 JWT 立即失效。', { name: a.name }))) return;
            const r = await OD.fetchJSON(`${API}/service-accounts/${a.secure_code}`,
                                         { method: 'DELETE' });
            if (!r.ok) { alert(__('撤銷失敗: {status}', { status: r.status })); return; }
            this.load();
        },
    };
}
