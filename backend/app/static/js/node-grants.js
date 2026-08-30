/* node-grants.js - 流程節點企業授權矩陣 */

var __NODE_GRANTS = window.__NODE_GRANTS || {};

function ngText(text, vars) {
    if (typeof __ === 'function') {
        return __(text, vars || {});
    }
    var result = text;
    vars = vars || {};
    Object.keys(vars).forEach(function (key) {
        result = result.replace('{' + key + '}', vars[key]);
    });
    return result;
}

function nodeGrantsManager() {
    return {
        nodes: [],
        orgs: [],
        grants: {},
        loading: false,
        busy: false,
        message: '',
        messageType: '',

        summaryText: function () {
            if (this.loading) {
                return ngText('載入中...');
            }
            return ngText('共 {nodes} 種受限節點、{orgs} 家企業', {
                nodes: this.nodes.length,
                orgs: this.orgs.length
            });
        },

        orgLabel: function (org) {
            return org.display_name || org.name || org.secure_code;
        },

        isGranted: function (node, org) {
            return Boolean(
                this.grants[node.node_type] &&
                this.grants[node.node_type][org.secure_code]
            );
        },

        grantRecord: function (node, org) {
            if (!this.grants[node.node_type]) {
                return null;
            }
            return this.grants[node.node_type][org.secure_code] || null;
        },

        grantBy: function (node, org) {
            var grant = this.grantRecord(node, org);
            return grant && grant.granted_by_name ? grant.granted_by_name : '';
        },

        grantTime: function (node, org) {
            var grant = this.grantRecord(node, org);
            if (!grant || !grant.created_at) {
                return '';
            }
            if (typeof BkTime !== 'undefined') {
                return BkTime.format(grant.created_at, 'short');
            }
            return grant.created_at;
        },

        showMessage: function (type, text) {
            this.messageType = type;
            this.message = text;
        },

        clearMessage: function () {
            this.message = '';
            this.messageType = '';
        },

        loadMatrix: async function () {
            this.loading = true;
            this.clearMessage();
            try {
                var res = await fetch(__NODE_GRANTS.matrixUrl);
                var data = await res.json();
                if (!res.ok || !data.success) {
                    throw new Error(data.message || ngText('讀取節點授權矩陣失敗'));
                }
                this.nodes = data.data.nodes || [];
                this.orgs = data.data.orgs || [];
                this.grants = data.data.grants || {};
            } catch (err) {
                this.showMessage('error', err.message || ngText('讀取節點授權矩陣失敗'));
            }
            this.loading = false;
        },

        postJson: async function (url, payload) {
            var res = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                },
                body: JSON.stringify(payload)
            });
            var data = await res.json();
            if (!res.ok || !data.success) {
                throw new Error(data.message || ngText('操作失敗'));
            }
            return data;
        },

        toggle: async function (node, org) {
            if (this.busy) {
                return;
            }

            var granted = this.isGranted(node, org);
            var orgName = this.orgLabel(org);
            if (granted && !confirm(ngText(
                '撤銷後，該企業的既有流程一旦執行到這個節點就會失敗。確定撤銷「{node}」對「{org}」的授權？',
                {node: node.display_name || node.node_type, org: orgName}
            ))) {
                return;
            }

            this.busy = true;
            this.clearMessage();
            try {
                await this.postJson(granted ? __NODE_GRANTS.revokeUrl : __NODE_GRANTS.grantUrl, {
                    node_type: node.node_type,
                    org_secure_code: org.secure_code
                });
                await this.loadMatrix();
                this.showMessage(
                    'success',
                    granted ? ngText('已撤銷授權') : ngText('已完成授權')
                );
            } catch (err) {
                this.showMessage('error', err.message || ngText('操作失敗'));
            }
            this.busy = false;
        },

        bulk: async function (node, action) {
            if (this.busy) {
                return;
            }

            if (action === 'revoke' && !confirm(ngText(
                '撤銷後，相關企業的既有流程一旦執行到這個節點就會失敗。確定撤銷「{node}」對所有企業的授權？',
                {node: node.display_name || node.node_type}
            ))) {
                return;
            }

            this.busy = true;
            this.clearMessage();
            try {
                var data = await this.postJson(__NODE_GRANTS.bulkUrl, {
                    node_type: node.node_type,
                    action: action
                });
                await this.loadMatrix();
                this.showMessage('success', ngText('已更新 {n} 筆授權', {
                    n: data.changed_count || 0
                }));
            } catch (err) {
                this.showMessage('error', err.message || ngText('批次操作失敗'));
            }
            this.busy = false;
        }
    };
}
