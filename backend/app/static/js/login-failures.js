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

        init() {
            if (!this.isSystemAdmin) {
                // ORG_ADMIN: 自動載入
                this.selectedOrgCode = this.userOrgCode;
                this.loadData();
            }
        },

        onOrgChange() {
            this.data = null;
            this.loaded = false;
            this.error = '';
            if (this.selectedOrgCode) {
                this.loadData();
            }
        },

        async loadData() {
            this.loading = true;
            this.error = '';
            try {
                let url = '/api/security/login-failures';
                if (this.isSystemAdmin && this.selectedOrgCode) {
                    url += '?org_code=' + encodeURIComponent(this.selectedOrgCode);
                }
                const resp = await fetch(url);
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                this.data = await resp.json();
                this.loaded = true;
            } catch (e) {
                this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        // ===== 熱力圖 =====
        get heatmapDates() {
            if (!this.data) return [];
            // time_range 已由後端轉為用戶時區，直接取日期部分
            const startDate = this.data.time_range.start.substring(0, 10);
            const endDate = this.data.time_range.end.substring(0, 10);
            const dates = [];
            const d = new Date(startDate + 'T00:00:00');
            const ed = new Date(endDate + 'T00:00:00');
            while (d <= ed) {
                dates.push(this._fmtDate(d));
                d.setDate(d.getDate() + 1);
            }
            return dates;
        },

        heatmapVal(dt, h) {
            if (!this.data || !this.data.heatmap[dt]) return 0;
            return this.data.heatmap[dt][String(h)] || 0;
        },

        heatmapMax() {
            if (!this.data) return 0;
            let mx = 0;
            for (const dt of Object.keys(this.data.heatmap)) {
                for (const h of Object.keys(this.data.heatmap[dt])) {
                    if (this.data.heatmap[dt][h] > mx) mx = this.data.heatmap[dt][h];
                }
            }
            return mx;
        },

        heatClass(v) {
            if (v === 0) return 'hc-0';
            const mx = this.heatmapMax();
            if (mx <= 1) return 'hc-5';
            const r = v / mx;
            if (r <= 0.2) return 'hc-1';
            if (r <= 0.4) return 'hc-2';
            if (r <= 0.6) return 'hc-3';
            if (r <= 0.8) return 'hc-4';
            return 'hc-5';
        },

        dayTotal(dt) {
            if (!this.data || !this.data.heatmap[dt]) return 0;
            let sum = 0;
            for (const h of Object.keys(this.data.heatmap[dt])) {
                sum += this.data.heatmap[dt][h];
            }
            return sum;
        },

        weekday(dt) {
            const names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            return names[new Date(dt + 'T00:00:00').getDay()];
        },

        isWeekend(dt) {
            const d = new Date(dt + 'T00:00:00').getDay();
            return d === 0 || d === 6;
        },

        // ===== IP 統計 =====
        get ipStatsSorted() {
            if (!this.data) return [];
            const arr = Object.entries(this.data.ip_stats).map(([ip, s]) => ({
                ip, ...s
            }));
            arr.sort((a, b) => b.count - a.count);
            return arr;
        },

        ipBarWidth(count) {
            const mx = this.ipStatsSorted.length > 0 ? this.ipStatsSorted[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        // ===== 帳號統計 =====
        get accountStatsSorted() {
            if (!this.data) return [];
            const arr = Object.entries(this.data.account_stats).map(([detail, s]) => ({
                detail, ...s
            }));
            arr.sort((a, b) => b.count - a.count);
            return arr;
        },

        accountBarWidth(count) {
            const mx = this.accountStatsSorted.length > 0 ? this.accountStatsSorted[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        // ===== 企業統計 =====
        get orgStatsSorted() {
            if (!this.data) return [];
            const arr = Object.entries(this.data.org_stats).map(([key, s]) => ({
                key, ...s
            }));
            arr.sort((a, b) => b.count - a.count);
            return arr;
        },

        orgBarWidth(count) {
            const mx = this.orgStatsSorted.length > 0 ? this.orgStatsSorted[0].count : 1;
            return Math.round((count / mx) * 80);
        },

        // ===== 類型標籤 =====
        typeTag(type) {
            const map = {
                wrong_password: ['Wrong Password', 'lf-tag-wrong-pw'],
                unknown_user: ['Unknown User', 'lf-tag-unknown-user'],
                unknown_domain: ['Unknown Domain', 'lf-tag-unknown-domain'],
                denied: ['Denied', 'lf-tag-denied'],
            };
            return map[type] || [type, 'lf-tag-unknown-user'];
        },

        // ===== 工具 =====
        _fmtDate(d) {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + dd;
        },

        hours: Array.from({length: 24}, (_, i) => i),
    };
}
