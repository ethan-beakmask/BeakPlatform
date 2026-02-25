/**
 * org-databases.js - 企業獨立資料庫監視頁面
 */
function odbMonitor() {
    const config = window.__ODB_CONFIG || {};
    return {
        expanded: {},

        init() {
            // 只有一個 DB 時自動展開
            if (config.dbCount === 1 && config.orgIds && config.orgIds.length === 1) {
                this.expanded['db_' + config.orgIds[0]] = true;
            }
        },

        toggle(key) {
            this.expanded[key] = !this.expanded[key];
        }
    };
}
