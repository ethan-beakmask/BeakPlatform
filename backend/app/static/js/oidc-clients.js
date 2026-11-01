/* OIDC client administration (PF-327 P1). */
var __OIDC_CLIENTS = window.__OIDC_CLIENTS || {};

function oidcClientsManager() {
    return {
        clients: [], keys: [], meta: {}, detail: {organizations: [], available_organizations: []},
        loading: false, busy: false, message: '', error: false,
        sortKey: 'name', sortDirection: 'asc', editing: null,
        formModal: false, orgModal: false, secretModal: false,
        selectedOrgCodes: [], oneTimeSecret: '',
        userTypeOptions: ['ORG_ADMIN', 'EMPLOYEE', 'SYSTEM_ADMIN'],
        form: {name: '', redirectText: '', allowed_user_types: [], extra_claims: [], is_active: true},

        async init() {
            await Promise.all([this.loadClients(), this.loadMeta(), this.loadKeys()]);
        },

        csrf() {
            var el = document.querySelector('meta[name="csrf-token"]');
            return el ? el.content : '';
        },

        async request(url, options) {
            options = options || {};
            options.headers = Object.assign({
                'Content-Type': 'application/json', 'X-CSRFToken': this.csrf()
            }, options.headers || {});
            var response = await fetch(url, options);
            var data = await response.json();
            if (!response.ok || data.success === false) {
                throw new Error(data.error || __('操作失敗'));
            }
            return data;
        },

        notify(text, isError) {
            this.message = text;
            this.error = Boolean(isError);
        },

        async loadClients() {
            this.loading = true;
            try {
                var data = await this.request(__OIDC_CLIENTS.api);
                this.clients = data.clients || [];
            } catch (err) {
                this.notify(err.message, true);
            } finally {
                this.loading = false;
            }
        },

        async loadMeta() {
            try {
                var data = await this.request(__OIDC_CLIENTS.meta);
                this.meta = data;
            } catch (err) {
                this.notify(err.message, true);
            }
        },

        async loadKeys() {
            try {
                var data = await this.request(__OIDC_CLIENTS.keys);
                this.keys = data.keys || [];
            } catch (err) {
                this.notify(err.message, true);
            }
        },

        sortedClients() {
            var key = this.sortKey;
            var direction = this.sortDirection === 'asc' ? 1 : -1;
            return this.clients.slice().sort(function (a, b) {
                var left = a[key]; var right = b[key];
                if (left === right) { return 0; }
                return (left > right ? 1 : -1) * direction;
            });
        },

        setSort(key) {
            if (this.sortKey === key) {
                this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortKey = key;
                this.sortDirection = 'asc';
            }
        },

        sortSymbol(key) {
            if (this.sortKey !== key) { return '↕'; }
            return this.sortDirection === 'asc' ? '↑' : '↓';
        },

        formatTime(value) {
            if (!value) { return ''; }
            if (typeof BkTime !== 'undefined') { return BkTime.format(value, 'short'); }
            return value;
        },

        resetForm() {
            this.form = {
                name: '', redirectText: '',
                allowed_user_types: ['ORG_ADMIN', 'EMPLOYEE', 'SYSTEM_ADMIN'],
                extra_claims: [], is_active: true
            };
        },

        openCreate() {
            this.editing = null;
            this.resetForm();
            this.formModal = true;
        },

        openEdit(client) {
            this.editing = client;
            this.form = {
                name: client.name,
                redirectText: (client.redirect_uris || []).join('\n'),
                allowed_user_types: (client.allowed_user_types || []).slice(),
                extra_claims: (client.extra_claims || []).slice(),
                is_active: client.is_active
            };
            this.formModal = true;
        },

        payload() {
            return {
                name: this.form.name,
                redirect_uris: this.form.redirectText.split('\n').map(function (v) { return v.trim(); }).filter(Boolean),
                allowed_user_types: this.form.allowed_user_types,
                extra_claims: this.form.extra_claims,
                is_active: this.form.is_active
            };
        },

        async saveClient() {
            this.busy = true;
            try {
                var url = this.editing ? __OIDC_CLIENTS.api + this.editing.secure_code : __OIDC_CLIENTS.api;
                var method = this.editing ? 'PUT' : 'POST';
                var body = this.payload();
                if (!this.editing) { delete body.is_active; }
                var data = await this.request(url, {method: method, body: JSON.stringify(body)});
                this.formModal = false;
                await this.loadClients();
                if (data.client && data.client.client_secret) {
                    this.oneTimeSecret = data.client.client_secret;
                    this.secretModal = true;
                }
                this.notify(this.editing ? __('client 已更新') : __('client 已建立'), false);
            } catch (err) {
                this.notify(err.message, true);
            } finally {
                this.busy = false;
            }
        },

        async openOrgs(client) {
            this.editing = client;
            this.selectedOrgCodes = [];
            try {
                var data = await this.request(__OIDC_CLIENTS.api + client.secure_code);
                this.detail = data.client;
                this.orgModal = true;
            } catch (err) {
                this.notify(err.message, true);
            }
        },

        ungrantedOrgs() {
            var granted = new Set((this.detail.organizations || []).map(function (org) { return org.secure_code; }));
            return (this.detail.available_organizations || []).filter(function (org) { return !granted.has(org.secure_code); });
        },

        async refreshDetail() {
            var data = await this.request(__OIDC_CLIENTS.api + this.editing.secure_code);
            this.detail = data.client;
            await this.loadClients();
        },

        async addSelectedOrgs() {
            this.busy = true;
            try {
                for (var i = 0; i < this.selectedOrgCodes.length; i += 1) {
                    await this.request(__OIDC_CLIENTS.api + this.editing.secure_code + '/orgs', {
                        method: 'POST', body: JSON.stringify({org_secure_code: this.selectedOrgCodes[i]})
                    });
                }
                this.selectedOrgCodes = [];
                await this.refreshDetail();
                this.notify(__('企業授權已新增'), false);
            } catch (err) {
                this.notify(err.message, true);
            } finally {
                this.busy = false;
            }
        },

        async revokeOrg(org) {
            if (!confirm(__('確定撤銷此企業的 OIDC 授權？'))) { return; }
            this.busy = true;
            try {
                await this.request(__OIDC_CLIENTS.api + this.editing.secure_code + '/orgs/' + org.secure_code, {method: 'DELETE'});
                await this.refreshDetail();
                this.notify(__('企業授權已撤銷'), false);
            } catch (err) {
                this.notify(err.message, true);
            } finally {
                this.busy = false;
            }
        },

        async rotateSecret(client) {
            if (!confirm(__('輪替後舊 secret 會立即失效，確定繼續？'))) { return; }
            try {
                var data = await this.request(__OIDC_CLIENTS.api + client.secure_code + '/rotate-secret', {method: 'POST'});
                this.oneTimeSecret = data.client_secret;
                this.secretModal = true;
            } catch (err) {
                this.notify(err.message, true);
            }
        },

        async deactivate(client) {
            if (!confirm(__('確定停用此 client？'))) { return; }
            try {
                await this.request(__OIDC_CLIENTS.api + client.secure_code, {method: 'PUT', body: JSON.stringify({is_active: false})});
                await this.loadClients();
                this.notify(__('client 已停用'), false);
            } catch (err) { this.notify(err.message, true); }
        },

        async removeClient(client) {
            if (!confirm(__('確定刪除此 client？此操作不會保留可用狀態。'))) { return; }
            try {
                await this.request(__OIDC_CLIENTS.api + client.secure_code, {method: 'DELETE'});
                await this.loadClients();
                this.notify(__('client 已刪除'), false);
            } catch (err) { this.notify(err.message, true); }
        },

        async rotateKey() {
            if (!confirm(__('確定輪替 RS256 簽章金鑰？'))) { return; }
            this.busy = true;
            try {
                await this.request(__OIDC_CLIENTS.rotateKey, {method: 'POST'});
                await this.loadKeys();
                this.notify(__('簽章金鑰已輪替'), false);
            } catch (err) {
                this.notify(err.message, true);
            } finally { this.busy = false; }
        },

        async copySecret() {
            var copied = await Utils.copyToClipboard(this.oneTimeSecret);
            this.notify(copied ? __('已複製') : __('複製失敗'), !copied);
        },

        closeSecret() {
            this.oneTimeSecret = '';
            this.secretModal = false;
        }
    };
}
