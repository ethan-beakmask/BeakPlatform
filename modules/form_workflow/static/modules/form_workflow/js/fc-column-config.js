/**
 * fc-column-config.js — 欄位顯示設定 mixin
 * 由 form-center.js 拆分而來
 */
function fcColumnConfig() {
    return {
        // --- State ---
        columnConfig: {},
        showColumnConfigModal: false,
        columnConfigLocale: '*',
        columnConfigEditing: {},
        columnConfigLocales: [],
        savingColumnConfig: false,

        // --- Properties ---
        _columnDefs: {
            serial_number:  { label: '單號',       defaultWidth: 140 },
            form_name:      { label: '表單名稱',    defaultWidth: 120 },
            subject:        { label: '主旨',        defaultWidth: null, flex: true, noHide: true },
            applicant:      { label: '發起人',      defaultWidth: 100 },
            category:       { label: '表單類別',    defaultWidth: 80 },
            current_node:   { label: '目前關卡',    defaultWidth: 140 },
            wait_time:      { label: '等待時間',    defaultWidth: 150 },
            submit_time:    { label: '送單時間',    defaultWidth: 130 },
            signed_elapsed: { label: '簽核後歷時',  defaultWidth: 130 },
            end_time:       { label: '結束時間',    defaultWidth: 130 },
            status:         { label: '狀態',        defaultWidth: 70 },
            duration:       { label: '流程耗時',    defaultWidth: 100 },
            actions:        { label: '操作',        defaultWidth: 110, noHide: true },
        },

        // --- Methods ---

        async loadColumnConfig() {
            try {
                const res = await fetch('/bp/api/form-center/column-config');
                const data = await res.json();
                if (data.success) {
                    this.columnConfig = data.data.config || {};
                }
            } catch (e) {
                console.error('載入欄位設定失敗:', e);
            }
        },

        /** 取得欄位寬度 style 字串 */
        colW(key) {
            const cfg = this.columnConfig[key];
            const def = this._columnDefs[key];
            if (def && def.flex) return '';
            const w = cfg ? cfg.width : (def ? def.defaultWidth : null);
            return w ? `width: ${w}px;` : '';
        },

        /** 欄位是否可見 */
        colV(key) {
            const cfg = this.columnConfig[key];
            if (!cfg) return true;
            return !cfg.hidden;
        },

        // --- 管理員：欄位設定 Modal ---

        async openColumnConfigModal() {
            this.showColumnConfigModal = true;
            this.savingColumnConfig = false;
            try {
                const res = await fetch('/bp/api/form-center/column-config/all');
                const data = await res.json();
                if (data.success) {
                    this.columnConfigLocales = data.data.configs.map(c => c.locale);
                    if (!this.columnConfigLocales.includes('*')) {
                        this.columnConfigLocales.unshift('*');
                    }
                    // 載入第一個有設定的語系，或 '*'
                    this.columnConfigLocale = this.columnConfigLocales[0] || '*';
                    this._loadConfigForLocale(data.data);
                }
            } catch (e) {
                console.error('載入欄位設定失敗:', e);
            }
        },

        _loadConfigForLocale(allData) {
            const existing = (allData.configs || []).find(c => c.locale === this.columnConfigLocale);
            const saved = existing ? existing.config : {};
            const defaults = allData.defaults || {};
            const editing = {};
            for (const [key, def] of Object.entries(this._columnDefs)) {
                const s = saved[key] || defaults[key] || {};
                editing[key] = {
                    label: def.label,
                    width: s.width != null ? s.width : def.defaultWidth,
                    hidden: !!s.hidden,
                    flex: !!def.flex,
                    noHide: !!def.noHide,
                };
            }
            this.columnConfigEditing = editing;
        },

        async switchColumnConfigLocale(locale) {
            this.columnConfigLocale = locale;
            try {
                const res = await fetch('/bp/api/form-center/column-config/all');
                const data = await res.json();
                if (data.success) {
                    this._loadConfigForLocale(data.data);
                }
            } catch (e) {
                console.error('載入語系設定失敗:', e);
            }
        },

        addColumnConfigLocale(locale) {
            if (!locale || this.columnConfigLocales.includes(locale)) return;
            this.columnConfigLocales.push(locale);
            this.columnConfigLocale = locale;
            // 初始化為預設值
            const editing = {};
            for (const [key, def] of Object.entries(this._columnDefs)) {
                editing[key] = {
                    label: def.label,
                    width: def.defaultWidth,
                    hidden: false,
                    flex: !!def.flex,
                    noHide: !!def.noHide,
                };
            }
            this.columnConfigEditing = editing;
        },

        async saveColumnConfig() {
            this.savingColumnConfig = true;
            try {
                const config = {};
                for (const [key, val] of Object.entries(this.columnConfigEditing)) {
                    config[key] = {
                        width: val.flex ? null : (parseInt(val.width) || null),
                        hidden: !!val.hidden,
                    };
                }
                const res = await fetch('/bp/api/form-center/column-config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        locale: this.columnConfigLocale,
                        config: config
                    })
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('欄位設定已儲存');
                    // 重新載入當前用戶的設定
                    await this.loadColumnConfig();
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗', 'error');
            } finally {
                this.savingColumnConfig = false;
            }
        },
    };
}
