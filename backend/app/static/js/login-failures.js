/**
 * login-failures.js - 登入錯誤監看
 */
function loginFailures() {
    return {
        isSystemAdmin: window.__LF_CONFIG.isSystemAdmin,
        organizations: window.__LF_CONFIG.organizations || [],
        orgLabel: window.__LF_CONFIG.orgLabel || '',
        userOrgCode: window.__LF_CONFIG.userOrgCode || '',
        selectedOrgCode: '',
        loading: false,
        loaded: false,
        data: null,
        error: '',

        // IP 過濾 (預設隱藏 loopback 與內網)
        hideLoopback: true,
        hideInternal: true,

        // 熱力圖分頁 (1=近10天, 2=近三個月)
        heatmapPage: 1,

        // 過濾後快取 (由 _recompute 更新)
        _timeline: [],
        _heatmap: {},
        _summary: { total: 0, unknown_domain: 0, unique_accounts: 0, unique_ips: 0, target_orgs: 0 },
        _ipStats: [],
        _accountStats: [],
        _orgStats: [],
        _heatmapMax10: 0,
        _heatmapMaxFull: 0,

        init() {
            this.$watch('hideLoopback', () => this._recompute());
            this.$watch('hideInternal', () => this._recompute());
            if (!this.isSystemAdmin) {
                this.selectedOrgCode = this.userOrgCode;
                this.loadData();
            }
        },

        onOrgChange() {
            this.data = null;
            this.loaded = false;
            this.error = '';
            this._recompute();
            if (this.selectedOrgCode) {
                this.loadData();
            }
        },

        async loadData() {
            this.loading = true;
            this.error = '';
            try {
                let url = window.__BP + '/api/security/login-failures';
                if (this.isSystemAdmin && this.selectedOrgCode) {
                    url += '?org_code=' + encodeURIComponent(this.selectedOrgCode);
                }
                const resp = await fetch(url);
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                this.data = await resp.json();
                this.loaded = true;
                this._recompute();
            } catch (e) {
                this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        // ===== IP 分類與過濾 =====

        _isLoopback(ip) {
            return ip !== 'unknown' && ip.startsWith('127.');
        },

        _isInternalIP(ip) {
            if (ip === 'unknown') return false;
            if (ip.startsWith('10.')) return true;
            if (ip.startsWith('192.168.')) return true;
            if (ip.startsWith('172.')) {
                var s = parseInt(ip.split('.')[1], 10);
                return s >= 16 && s <= 31;
            }
            return false;
        },

        _shouldHideIP(ip) {
            if (this.hideLoopback && this._isLoopback(ip)) return true;
            if (this.hideInternal && this._isInternalIP(ip)) return true;
            return false;
        },

        // ===== 過濾後資料重算 =====

        _recompute() {
            if (!this.data) {
                this._timeline = [];
                this._heatmap = {};
                this._summary = { total: 0, unknown_domain: 0, unique_accounts: 0, unique_ips: 0, target_orgs: 0 };
                this._ipStats = [];
                this._accountStats = [];
                this._orgStats = [];
                this._heatmapMax10 = 0;
                this._heatmapMaxFull = 0;
                return;
            }

            // 過濾 timeline
            var tl = this.data.timeline.filter(r => !this._shouldHideIP(r.ip));
            this._timeline = tl;

            // 熱力圖
            var hm = {};
            for (var i = 0; i < tl.length; i++) {
                var r = tl[i];
                var dt = r.time.substring(0, 10);
                var h = String(parseInt(r.time.substring(11, 13), 10));
                if (!hm[dt]) hm[dt] = {};
                hm[dt][h] = (hm[dt][h] || 0) + 1;
            }
            this._heatmap = hm;

            // 熱力圖 max (全部)
            var mxFull = 0;
            var hmKeys = Object.keys(hm);
            for (var i = 0; i < hmKeys.length; i++) {
                var hours = Object.keys(hm[hmKeys[i]]);
                for (var j = 0; j < hours.length; j++) {
                    if (hm[hmKeys[i]][hours[j]] > mxFull) mxFull = hm[hmKeys[i]][hours[j]];
                }
            }
            this._heatmapMaxFull = mxFull;

            // 熱力圖 max (近 10 天)
            var last10 = this.heatmapDates.slice(-10);
            var mx10 = 0;
            for (var i = 0; i < last10.length; i++) {
                var d = last10[i];
                if (!hm[d]) continue;
                var hours = Object.keys(hm[d]);
                for (var j = 0; j < hours.length; j++) {
                    if (hm[d][hours[j]] > mx10) mx10 = hm[d][hours[j]];
                }
            }
            this._heatmapMax10 = mx10;

            // 摘要
            var accounts = new Set();
            var ips = new Set();
            var orgs = new Set();
            var unknownDomain = 0;
            for (var i = 0; i < tl.length; i++) {
                accounts.add(tl[i].details);
                ips.add(tl[i].ip);
                orgs.add(tl[i].org_secure_code || '(NULL)');
                if (tl[i].type === 'unknown_domain') unknownDomain++;
            }
            this._summary = {
                total: tl.length,
                unknown_domain: unknownDomain,
                unique_accounts: accounts.size,
                unique_ips: ips.size,
                target_orgs: orgs.size,
            };

            // IP 統計
            var ipMap = {};
            for (var i = 0; i < tl.length; i++) {
                var r = tl[i];
                var ip = r.ip;
                if (!ipMap[ip]) {
                    ipMap[ip] = { ip: ip, count: 0, accounts: [], uas: [], first: null, last: null };
                }
                ipMap[ip].count++;
                if (ipMap[ip].accounts.indexOf(r.details) === -1) ipMap[ip].accounts.push(r.details);
                if (ipMap[ip].uas.indexOf(r.ua_brief) === -1) ipMap[ip].uas.push(r.ua_brief);
                var ts = r.time.substring(0, 16);
                if (!ipMap[ip].first) ipMap[ip].first = ts;
                ipMap[ip].last = ts;
            }
            this._ipStats = Object.values(ipMap).sort(function(a, b) { return b.count - a.count; });

            // 帳號統計
            var accMap = {};
            for (var i = 0; i < tl.length; i++) {
                var r = tl[i];
                var detail = r.details;
                if (!accMap[detail]) {
                    accMap[detail] = { detail: detail, count: 0, ips: [], type: r.type, org_name: r.org_name };
                }
                accMap[detail].count++;
                if (accMap[detail].ips.indexOf(r.ip) === -1) accMap[detail].ips.push(r.ip);
            }
            this._accountStats = Object.values(accMap).sort(function(a, b) { return b.count - a.count; });

            // 企業統計
            var orgMap = {};
            for (var i = 0; i < tl.length; i++) {
                var r = tl[i];
                var key = r.org_secure_code || '(NULL)';
                if (!orgMap[key]) {
                    orgMap[key] = { key: key, count: 0, name: r.org_name, domain: r.org_domain };
                }
                orgMap[key].count++;
            }
            this._orgStats = Object.values(orgMap).sort(function(a, b) { return b.count - a.count; });
        },

        // ===== 熱力圖 =====
        get heatmapDates() {
            if (!this.data) return [];
            var startDate = this.data.time_range.start.substring(0, 10);
            var endDate = this.data.time_range.end.substring(0, 10);
            var dates = [];
            var d = new Date(startDate + 'T00:00:00');
            var ed = new Date(endDate + 'T00:00:00');
            while (d <= ed) {
                dates.push(this._fmtDate(d));
                d.setDate(d.getDate() + 1);
            }
            return dates;
        },

        get displayedHeatmapDates() {
            var all = this.heatmapDates;
            return this.heatmapPage === 1 ? all.slice(-10) : all;
        },

        heatmapVal(dt, h) {
            if (!this._heatmap[dt]) return 0;
            return this._heatmap[dt][String(h)] || 0;
        },

        heatClass(v) {
            if (v === 0) return 'hc-0';
            var mx = this.heatmapPage === 1 ? this._heatmapMax10 : this._heatmapMaxFull;
            if (mx <= 1) return 'hc-5';
            var r = v / mx;
            if (r <= 0.2) return 'hc-1';
            if (r <= 0.4) return 'hc-2';
            if (r <= 0.6) return 'hc-3';
            if (r <= 0.8) return 'hc-4';
            return 'hc-5';
        },

        dayTotal(dt) {
            if (!this._heatmap[dt]) return 0;
            var sum = 0;
            var hours = Object.keys(this._heatmap[dt]);
            for (var i = 0; i < hours.length; i++) {
                sum += this._heatmap[dt][hours[i]];
            }
            return sum;
        },

        weekday(dt) {
            var names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            return names[new Date(dt + 'T00:00:00').getDay()];
        },

        isWeekend(dt) {
            var d = new Date(dt + 'T00:00:00').getDay();
            return d === 0 || d === 6;
        },

        // ===== 長條圖寬度 =====
        ipBarWidth(count) {
            var mx = this._ipStats.length > 0 ? this._ipStats[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        accountBarWidth(count) {
            var mx = this._accountStats.length > 0 ? this._accountStats[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        orgBarWidth(count) {
            var mx = this._orgStats.length > 0 ? this._orgStats[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        // ===== 類型標籤 =====
        typeTag(type) {
            var map = {
                wrong_password: ['Wrong Password', 'lf-tag-wrong-pw'],
                unknown_user: ['Unknown User', 'lf-tag-unknown-user'],
                unknown_domain: ['Unknown Domain', 'lf-tag-unknown-domain'],
                denied: ['Denied', 'lf-tag-denied'],
            };
            return map[type] || [type, 'lf-tag-unknown-user'];
        },

        // ===== 工具 =====
        _fmtDate(d) {
            var y = d.getFullYear();
            var m = String(d.getMonth() + 1).padStart(2, '0');
            var dd = String(d.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + dd;
        },

        hours: Array.from({length: 24}, function(_, i) { return i; }),
    };
}
