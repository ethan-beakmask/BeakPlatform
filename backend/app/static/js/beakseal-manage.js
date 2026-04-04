/**
 * BeakSeal 管理頁 - Alpine.js Manager
 */
function beaksealManager() {
    return {
        tab: 'status',

        // Vault
        vaultStatus: null,
        vaultError: null,

        // Service
        serviceStatus: {},

        // File stats
        fileStats: null,

        // Config
        configYaml: '',
        configPath: '',

        // Audit
        auditLogs: [],
        auditFilter: { action: '', limit: 50 },

        // Chain
        chainResult: null,
        verifying: false,

        // Unseal dialog
        showUnsealDialog: false,
        unsealPassword: '',
        unsealError: '',
        unsealing: false,

        // Toast
        toast: { show: false, msg: '', error: false },
        _toastTimer: null,

        async init() {
            await this.refresh();
        },

        async refresh() {
            await Promise.all([
                this.loadVaultStatus(),
                this.loadServiceStatus(),
                this.loadFileStats(),
            ]);
        },

        // ===== Vault Status =====

        async loadVaultStatus() {
            try {
                const r = await fetch('/api/vault/status');
                const d = await r.json();
                if (d.success) {
                    this.vaultStatus = d.data;
                    this.vaultError = null;
                } else {
                    this.vaultError = d.error || 'Unknown error';
                }
            } catch (e) {
                this.vaultError = 'BeakSeal 服務無法連線';
            }
        },

        // ===== Service Status =====

        async loadServiceStatus() {
            try {
                const r = await fetch('/api/vault/service/status');
                const d = await r.json();
                if (d.success) this.serviceStatus = d.data;
            } catch (e) {
                this.serviceStatus = { active: 'unknown' };
            }
        },

        async serviceAction(action) {
            const labels = { start: '啟動', stop: '停止', restart: '重啟' };
            if (!confirm('確定要' + labels[action] + ' BeakSeal 服務?')) return;

            try {
                const r = await fetch('/api/vault/service/' + action, { method: 'POST' });
                const d = await r.json();
                if (d.success) {
                    this.showToast('服務已' + labels[action]);
                    // 等待服務狀態更新
                    setTimeout(() => this.refresh(), 2000);
                } else {
                    this.showToast(d.error || '操作失敗', true);
                }
            } catch (e) {
                this.showToast('操作失敗: ' + e.message, true);
            }
        },

        // ===== Unseal / Seal =====

        async unsealVault() {
            if (!this.unsealPassword) {
                this.unsealError = '請輸入密碼';
                return;
            }
            this.unsealing = true;
            this.unsealError = '';
            try {
                const r = await fetch('/api/vault/unseal', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password: this.unsealPassword }),
                });
                const d = await r.json();
                if (d.success) {
                    this.showUnsealDialog = false;
                    this.unsealPassword = '';
                    this.showToast('Vault 已 Unseal');
                    await this.loadVaultStatus();
                } else {
                    this.unsealError = d.error || 'Unseal 失敗';
                }
            } catch (e) {
                this.unsealError = 'Unseal 失敗: ' + e.message;
            } finally {
                this.unsealing = false;
            }
        },

        async sealVault() {
            if (!confirm('確定要 Seal Vault? 所有加解密操作將暫停。')) return;
            try {
                const r = await fetch('/api/vault/seal', { method: 'POST' });
                const d = await r.json();
                if (d.success) {
                    this.showToast('Vault 已 Seal');
                    await this.loadVaultStatus();
                } else {
                    this.showToast(d.error || 'Seal 失敗', true);
                }
            } catch (e) {
                this.showToast('Seal 失敗', true);
            }
        },

        // ===== File Stats =====

        async loadFileStats() {
            try {
                const r = await fetch('/api/vault/file-stats');
                const d = await r.json();
                if (d.success) this.fileStats = d.data;
            } catch (e) { /* ignore */ }
        },

        // ===== Config =====

        async loadConfig() {
            if (this.configYaml) return; // 已載入
            try {
                const r = await fetch('/api/vault/config');
                const d = await r.json();
                if (d.success) {
                    this.configYaml = this._yamlStringify(d.data.config);
                    this.configPath = d.data.config_path;
                }
            } catch (e) {
                this.configYaml = 'Error: ' + e.message;
            }
        },

        _yamlStringify(obj, indent) {
            indent = indent || 0;
            var lines = [];
            var pad = '  '.repeat(indent);
            if (Array.isArray(obj)) {
                for (var i = 0; i < obj.length; i++) {
                    if (typeof obj[i] === 'object' && obj[i] !== null) {
                        lines.push(pad + '-');
                        lines.push(this._yamlStringify(obj[i], indent + 1));
                    } else {
                        lines.push(pad + '- ' + obj[i]);
                    }
                }
            } else if (typeof obj === 'object' && obj !== null) {
                for (var key in obj) {
                    if (!obj.hasOwnProperty(key)) continue;
                    var val = obj[key];
                    if (typeof val === 'object' && val !== null) {
                        lines.push(pad + key + ':');
                        lines.push(this._yamlStringify(val, indent + 1));
                    } else {
                        lines.push(pad + key + ': ' + (val === null ? 'null' : val));
                    }
                }
            }
            return lines.join('\n');
        },

        // ===== Audit =====

        async loadAuditLogs() {
            try {
                var params = new URLSearchParams();
                if (this.auditFilter.action) params.set('action', this.auditFilter.action);
                if (this.auditFilter.limit) params.set('limit', this.auditFilter.limit);
                const r = await fetch('/api/vault/audit?' + params.toString());
                const d = await r.json();
                if (d.success) this.auditLogs = d.data || [];
            } catch (e) {
                console.error('Load audit logs failed:', e);
            }
        },

        async verifyChain() {
            this.verifying = true;
            try {
                const r = await fetch('/api/vault/audit/verify');
                const d = await r.json();
                if (d.success) this.chainResult = d.data;
            } catch (e) {
                console.error('Verify chain failed:', e);
            } finally {
                this.verifying = false;
            }
        },

        // ===== Formatters =====

        formatTime(ts) {
            if (!ts) return '-';
            if (typeof BkTime !== 'undefined') return BkTime.format(ts, 'full');
            return ts.replace('T', ' ').substring(0, 19);
        },

        formatUptime(sec) {
            if (!sec) return '-';
            var d = Math.floor(sec / 86400);
            var h = Math.floor((sec % 86400) / 3600);
            var m = Math.floor((sec % 3600) / 60);
            if (d > 0) return d + ' 天 ' + h + ' 時';
            if (h > 0) return h + ' 時 ' + m + ' 分';
            return m + ' 分 ' + (sec % 60) + ' 秒';
        },

        formatBytes(b) {
            b = parseInt(b) || 0;
            if (b === 0) return '0 B';
            if (b < 1024) return b + ' B';
            if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
            if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB';
            return (b / 1073741824).toFixed(2) + ' GB';
        },

        showToast(msg, isError) {
            this.toast = { show: true, msg: msg, error: !!isError };
            clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
