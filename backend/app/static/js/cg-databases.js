/**
 * cg-databases.js - 集團資料庫總覽
 */
function cgdbOverview() {
    return {
        databases: [],
        loading: true,
        error: null,

        get summaryText() {
            if (!this.databases.length) return '';
            const total = this.databases.length;
            const orphans = this.databases.filter(d => d.is_orphan).length;
            const ghosts = this.databases.filter(d => d.is_ghost_record).length;
            let text = total + ' 個資料庫';
            if (orphans > 0) text += ', ' + orphans + ' 個孤兒';
            if (ghosts > 0) text += ', ' + ghosts + ' 個記錄無對應 DB';
            return text;
        },

        init() {
            this.loadData();
        },

        async loadData() {
            this.loading = true;
            this.error = null;
            try {
                const resp = await fetch(window.__BP + '/admin/cg-databases/data');
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                this.databases = (data.databases || []).map(db => ({
                    ...db,
                    _expanded: false,
                    _logs: null,
                    _logsLoading: false,
                }));
            } catch (e) {
                this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        async toggle(db) {
            db._expanded = !db._expanded;

            if (db._expanded) {
                // lazy load logs
                if (!db._logs && db.conglomerate_secure_code && !db._logsLoading) {
                    db._logsLoading = true;
                    try {
                        const resp = await fetch(window.__BP + '/admin/cg-databases/' + db.conglomerate_secure_code + '/logs');
                        if (resp.ok) {
                            const data = await resp.json();
                            db._logs = data.logs || [];
                        }
                    } catch (e) {
                        db._logs = [];
                    } finally {
                        db._logsLoading = false;
                    }
                }
            }
        },
    };
}
