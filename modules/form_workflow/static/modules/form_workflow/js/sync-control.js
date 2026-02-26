/**
 * sync-control.js -- 同步中控台
 * Alpine.js component
 */

function syncControl() {
    const cfg = window.__SYNC_CONFIG || {};
    const ftSc = cfg.formTemplateSc;
    const apiBase = '/api/form-workflow/specs/' + ftSc;

    return {
        ftSc: ftSc,
        loading: true,
        syncing: false,
        status: null,
        driftData: null,
        alsoUpdateSpec: false,

        // 確認 Modal
        showConfirmModal: false,
        confirmTitle: '',
        confirmMessage: '',
        confirmNeedTableName: false,
        confirmTableInput: '',
        pendingSyncAction: null,

        // --- 生命週期 ---
        async init() {
            await this.loadStatus();
        },

        async loadStatus() {
            this.loading = true;
            try {
                const [statusRes, driftRes] = await Promise.all([
                    fetch(apiBase + '/full-status'),
                    fetch(apiBase + '/compare').catch(() => null),
                ]);

                const statusData = await statusRes.json();
                if (statusData.success) {
                    this.status = statusData.data;
                } else {
                    _scToast('error', statusData.error || '載入失敗');
                    this.loading = false;
                    return;
                }

                if (driftRes) {
                    const driftJson = await driftRes.json();
                    if (driftJson.success) {
                        this.driftData = driftJson.data;
                    }
                }
            } catch (e) {
                _scToast('error', '載入失敗: ' + e.message);
            }
            this.loading = false;
        },

        // --- 比對狀態 ---
        getComparisonLabel(comp) {
            if (!comp) return '-';
            if (comp.status === 'match') return '一致';
            if (comp.status === 'mismatch') return '偏移 (' + comp.drift_count + ')';
            return '不可用';
        },

        getSyncBtnClass(compKey, available) {
            if (!available) return 'unavailable';
            if (!this.status || !this.status.comparisons) return '';
            const comp = this.status.comparisons[compKey];
            if (!comp) return '';
            return comp.status;
        },

        // --- 同步操作 ---
        doSync(direction) {
            const dirMap = {
                'spec-to-formio': {
                    title: 'Spec -> FormIO',
                    message: '將 Spec 欄位定義套用到 FormIO schema。<br>表單設計器中的欄位會被更新。',
                    needTable: false,
                    apiPath: '/sync-spec-to-formio',
                    method: 'POST',
                },
                'formio-to-spec': {
                    title: 'FormIO -> Spec',
                    message: '從 FormIO schema 擷取欄位定義，更新 Spec。<br>Spec 會新增一個版本。',
                    needTable: false,
                    apiPath: '/sync-from-formio',
                    method: 'POST',
                },
                'spec-to-sql': {
                    title: 'Spec -> SQL',
                    message: '依 Spec 欄位定義調整 SQL 表結構。<br>可能包含新增、修改、刪除欄位。',
                    needTable: true,
                    apiPath: '/sync-spec-to-sql',
                    method: 'POST',
                },
                'sql-to-spec': {
                    title: 'SQL -> Spec',
                    message: '從企業 DB 實際表結構反向建立 Spec。<br>Spec 會新增一個版本。',
                    needTable: false,
                    apiPath: '/sync-from-sql',
                    method: 'POST',
                },
                'formio-to-sql': {
                    title: 'FormIO -> SQL',
                    message: '依 FormIO schema 調整 SQL 表結構。<br>可能包含 ALTER TABLE。',
                    needTable: true,
                    apiPath: '/sync-formio-to-sql',
                    method: 'POST',
                },
                'sql-to-formio': {
                    title: 'SQL -> FormIO',
                    message: '從企業 DB 表結構更新 FormIO schema。<br>表單設計器中的欄位會被更新。',
                    needTable: false,
                    apiPath: '/sync-sql-to-formio',
                    method: 'POST',
                },
            };

            const config = dirMap[direction];
            if (!config) return;

            // FormIO<->SQL 方向顯示 alsoUpdateSpec 資訊
            let extraMsg = '';
            if ((direction === 'formio-to-sql' || direction === 'sql-to-formio') && this.alsoUpdateSpec) {
                extraMsg = '<br><br><strong>同時更新 Spec</strong>（會新增一版）';
            }

            this.confirmTitle = config.title;
            this.confirmMessage = config.message + extraMsg;
            this.confirmNeedTableName = config.needTable;
            this.confirmTableInput = '';
            this.pendingSyncAction = { direction, config };
            this.showConfirmModal = true;
        },

        async executeConfirmed() {
            if (!this.pendingSyncAction) return;

            const { direction, config } = this.pendingSyncAction;
            this.showConfirmModal = false;
            this.syncing = true;

            try {
                const body = {};

                // FormIO<->SQL 帶 also_update_spec
                if (direction === 'formio-to-sql' || direction === 'sql-to-formio') {
                    body.also_update_spec = this.alsoUpdateSpec;
                }

                // Spec->SQL 帶 confirm_table_name
                if (config.needTable && this.confirmTableInput) {
                    body.confirm_table_name = this.confirmTableInput;
                }

                const res = await fetch(apiBase + config.apiPath, {
                    method: config.method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });

                const data = await res.json();
                if (data.success) {
                    _scToast('success', data.message || '同步完成');
                    // 重新載入狀態
                    await this.loadStatus();
                } else {
                    _scToast('error', data.error || '同步失敗');
                }
            } catch (e) {
                _scToast('error', '同步失敗: ' + e.message);
            }

            this.syncing = false;
            this.pendingSyncAction = null;
        },

        // --- 跳轉 ---
        goSpecEditor() {
            window.open('/forms/templates/' + this.ftSc + '/spec', '_blank');
        },

        // --- 工具 ---
        formatDate(iso) {
            if (!iso) return '-';
            const d = new Date(iso);
            return d.toLocaleDateString('zh-TW') + ' ' +
                   d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        },
    };
}

function _scToast(type, msg) {
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;padding:10px 18px;border-radius:4px;font-size:13px;max-width:400px;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    if (type === 'success') {
        el.style.background = '#d1fae5';
        el.style.color = '#065f46';
        el.style.border = '1px solid #6ee7b7';
    } else if (type === 'error') {
        el.style.background = '#fee2e2';
        el.style.color = '#991b1b';
        el.style.border = '1px solid #fca5a5';
    } else {
        el.style.background = '#e0e7ff';
        el.style.color = '#3730a3';
        el.style.border = '1px solid #a5b4fc';
    }
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}
