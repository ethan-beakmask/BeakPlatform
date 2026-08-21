/* ai-usage.js - AiAgent usage and quota administration */

function aiUsageManager() {
    const emptySummary = {
        enabled: true,
        timezone: 'Asia/Taipei',
        daily: { runs: 0, runs_limit: 0, cost: 0, cost_limit: 0, period_start: null },
        monthly: { runs: 0, runs_limit: 0, cost: 0, cost_limit: 0, period_start: null },
        recent_blocked: 0
    };

    return {
        summary: emptySummary,
        summaryLoading: true,
        configLoading: true,
        configSaving: false,
        configItems: [],
        form: {
            enabled: true,
            daily_max_runs: 0,
            monthly_max_runs: 0,
            daily_max_cost_usd: 0,
            monthly_max_cost_usd: 0
        },
        configMessage: '',
        // 載入時的有效值快照。儲存只送出「使用者真的改過」的欄位，否則按一次儲存
        // 會把五項全部寫成企業覆寫，日後平台調整系統預設時這家企業不會跟著變，
        // 而使用者從畫面上看不出自己鎖定了沒動過的項目。
        configBaseline: {},
        numericFields: [
            { key: 'daily_max_runs', label: __('每日執行次數上限'), step: 1 },
            { key: 'monthly_max_runs', label: __('每月執行次數上限'), step: 1 },
            { key: 'daily_max_cost_usd', label: __('每日估算成本上限（USD）'), step: 0.01 },
            { key: 'monthly_max_cost_usd', label: __('每月估算成本上限（USD）'), step: 0.01 }
        ],
        records: [],
        recordsLoading: true,
        total: 0,
        pagination: { page: 1, per_page: 20 },
        filters: { status: '', start: '', end: '' },
        expandedRecords: {},

        async init() {
            await this.refreshAll();
        },

        csrfToken() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.content : '';
        },

        canManage() {
            return typeof BkCaps !== 'undefined' && BkCaps.can('form_workflow.admin');
        },

        async refreshAll() {
            await Promise.all([
                this.loadSummary(),
                this.loadConfig(),
                this.loadRecords()
            ]);
        },

        async loadSummary() {
            this.summaryLoading = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/ai-usage/summary');
                const data = await res.json();
                if (data.success) {
                    this.summary = data.data || emptySummary;
                } else {
                    alert(__('載入用量失敗: ') + (data.message || data.error || ''));
                }
            } catch (e) {
                alert(__('載入用量失敗: ') + e.message);
            } finally {
                this.summaryLoading = false;
            }
        },

        async loadConfig() {
            this.configLoading = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/ai-usage/config');
                const data = await res.json();
                if (data.success) {
                    this.applyConfig(data.data);
                } else {
                    alert(__('載入配額設定失敗: ') + (data.message || data.error || ''));
                }
            } catch (e) {
                alert(__('載入配額設定失敗: ') + e.message);
            } finally {
                this.configLoading = false;
            }
        },

        applyConfig(data) {
            const config = (data && data.config) || {};
            this.configItems = (data && data.items) || [];
            this.form = {
                enabled: config.enabled === true,
                daily_max_runs: Number(config.daily_max_runs || 0),
                monthly_max_runs: Number(config.monthly_max_runs || 0),
                daily_max_cost_usd: Number(config.daily_max_cost_usd || 0),
                monthly_max_cost_usd: Number(config.monthly_max_cost_usd || 0)
            };
            this.configBaseline = Object.assign({}, this.form);
        },

        changedConfig() {
            const changed = {};
            Object.keys(this.form).forEach((key) => {
                if (this.form[key] !== this.configBaseline[key]) {
                    changed[key] = this.form[key];
                }
            });
            return changed;
        },

        async saveConfig() {
            if (this.configSaving || !this.canManage()) return;
            const changed = this.changedConfig();
            if (Object.keys(changed).length === 0) {
                this.configMessage = __('沒有變更');
                return;
            }
            this.configSaving = true;
            this.configMessage = '';
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/ai-usage/config', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken()
                    },
                    body: JSON.stringify(changed)
                });
                const data = await res.json();
                if (data.success) {
                    this.applyConfig(data.data);
                    this.configMessage = __('配額設定已儲存');
                    await this.loadSummary();
                } else {
                    alert(__('儲存失敗: ') + (data.message || data.error || ''));
                }
            } catch (e) {
                alert(__('儲存失敗: ') + e.message);
            } finally {
                this.configSaving = false;
            }
        },

        async restoreDefault(key) {
            if (this.configSaving || !this.canManage()) return;
            this.configSaving = true;
            this.configMessage = '';
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/ai-usage/config', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken()
                    },
                    body: JSON.stringify({ clear: [key] })
                });
                const data = await res.json();
                if (data.success) {
                    this.applyConfig(data.data);
                    this.configMessage = __('已回復系統預設');
                    await this.loadSummary();
                } else {
                    alert(__('回復失敗: ') + (data.message || data.error || ''));
                }
            } catch (e) {
                alert(__('回復失敗: ') + e.message);
            } finally {
                this.configSaving = false;
            }
        },

        async loadRecords() {
            this.recordsLoading = true;
            const params = new URLSearchParams({
                page: String(this.pagination.page),
                per_page: String(this.pagination.per_page)
            });
            if (this.filters.status) params.set('status', this.filters.status);
            if (this.filters.start) params.set('start', this.filters.start);
            if (this.filters.end) params.set('end', this.filters.end);
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/ai-usage/records?' + params.toString());
                const data = await res.json();
                if (data.success) {
                    this.records = data.data.items || [];
                    this.total = data.data.total || 0;
                    this.pagination.page = data.data.page || 1;
                    this.pagination.per_page = data.data.per_page || 20;
                } else {
                    alert(__('載入明細失敗: ') + (data.message || data.error || ''));
                }
            } catch (e) {
                alert(__('載入明細失敗: ') + e.message);
            } finally {
                this.recordsLoading = false;
            }
        },

        applyFilters() {
            this.pagination.page = 1;
            this.loadRecords();
        },

        resetFilters() {
            this.filters = { status: '', start: '', end: '' };
            this.pagination.page = 1;
            this.loadRecords();
        },

        prevPage() {
            if (this.pagination.page <= 1) return;
            this.pagination.page -= 1;
            this.loadRecords();
        },

        nextPage() {
            if (this.pagination.page >= this.totalPages()) return;
            this.pagination.page += 1;
            this.loadRecords();
        },

        totalPages() {
            return Math.max(1, Math.ceil(this.total / this.pagination.per_page));
        },

        pageText() {
            return __('第 {page} / {pages} 頁，共 {total} 筆', {
                page: this.pagination.page,
                pages: this.totalPages(),
                total: this.total
            });
        },

        sourceOf(key) {
            const item = this.configItems.find(row => row.key === key);
            return item ? item.source : '';
        },

        sourceLabel(key) {
            const source = this.sourceOf(key);
            if (source === 'org') return __('企業覆寫');
            if (source === 'system') return __('系統預設');
            return __('內建預設');
        },

        systemDefaultText(key) {
            const item = this.configItems.find(row => row.key === key);
            if (!item) return '';
            if (key === 'enabled') return '';
            return __('系統預設: {value}', { value: this.limitText(item.system_default, key.includes('cost')) });
        },

        limitText(value, cost) {
            const numeric = Number(value || 0);
            if (numeric === 0) return __('不限');
            return cost ? this.money(numeric) : String(numeric);
        },

        usageText(used, limit) {
            return `${Number(used || 0)} / ${this.limitText(limit, false)}`;
        },

        costUsageText(used, limit) {
            return `${this.money(used)} / ${this.limitText(limit, true)}`;
        },

        money(value) {
            return '$' + Number(value || 0).toFixed(4);
        },

        meterWidth(used, limit) {
            const max = Number(limit || 0);
            if (max <= 0) return '0%';
            return Math.min(100, Math.round((Number(used || 0) / max) * 100)) + '%';
        },

        meterClass(used, limit) {
            const max = Number(limit || 0);
            if (max <= 0) return 'fw-meter-fill';
            const ratio = Number(used || 0) / max;
            if (ratio >= 1) return 'fw-meter-fill danger';
            if (ratio >= 0.8) return 'fw-meter-fill warning';
            return 'fw-meter-fill success';
        },

        periodText(value) {
            if (!value) return '';
            return __('期間起點: {time}', { time: this.formatTime(value) });
        },

        formatTime(value) {
            if (!value) return '-';
            if (typeof BkTime !== 'undefined') {
                return BkTime.format(value, 'short');
            }
            return value;
        },

        statusLabel(status) {
            if (status === 'running') return __('執行中');
            if (status === 'success') return __('成功');
            if (status === 'failed') return __('失敗');
            if (status === 'blocked') return __('已擋下');
            return status || '-';
        },

        statusClass(status) {
            if (status === 'running') return 'info';
            if (status === 'success') return 'success';
            if (status === 'failed') return 'danger';
            if (status === 'blocked') return 'warning';
            return '';
        },

        tokenText(record) {
            const input = Number(record.input_tokens || 0);
            const output = Number(record.output_tokens || 0);
            return `${input} / ${output}`;
        },

        durationText(value) {
            const ms = Number(value || 0);
            if (!ms) return '-';
            if (ms < 1000) return __('{n} ms', { n: ms });
            return __('{n} 秒', { n: (ms / 1000).toFixed(1) });
        },

        truncate(value) {
            if (!value) return '-';
            const text = String(value);
            return text.length > 80 ? text.slice(0, 80) + '...' : text;
        },

        toggleRecord(code) {
            this.expandedRecords[code] = !this.expandedRecords[code];
        },

        modelRows(record) {
            const usage = record.model_usage || {};
            return Object.keys(usage).sort().map(name => {
                const row = usage[name] || {};
                return {
                    name,
                    input: Number(row.inputTokens || row.input_tokens || 0),
                    output: Number(row.outputTokens || row.output_tokens || 0),
                    cost: Number(row.costUSD || row.cost_usd || 0)
                };
            });
        }
    };
}
