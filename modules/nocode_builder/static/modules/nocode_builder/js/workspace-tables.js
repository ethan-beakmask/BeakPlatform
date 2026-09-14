/* global __, BkCaps */
function wksTablesManager(subSystemSc) {
    const BP = window.__BP || '';
    const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
    const MAX_IDENTIFIER_LENGTH = 63;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    return {
        subSystemSc: subSystemSc || '',
        sources: [],
        sourceKey: '',
        tables: [],
        selectedTable: '',
        columns: [],
        loading: false,
        error: '',
        message: '',
        showCreateModal: false,
        newTable: { name: '', columns: [{ name: '', type: 'TEXT', required: false }] },
        columnTypes: ['TEXT', 'INTEGER', 'REAL', 'DATE', 'DATETIME', 'BOOLEAN'],

        async init() {
            await this.loadSources();
        },

        async loadSources() {
            this.loading = true;
            this.clearMessages();
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/data-sources`
                );
                this.sources = data.data || [];
                const firstAvailable = this.sources.find((source) => source.available);
                this.sourceKey = firstAvailable ? firstAvailable.key : '';
                if (this.sourceKey) {
                    await this.loadTables();
                }
            } catch (err) {
                this.error = this.formatError(err.message, __('載入資料來源失敗'));
            } finally {
                this.loading = false;
            }
        },

        async loadTables() {
            if (!this.sourceKey) {
                this.tables = [];
                this.selectedTable = '';
                this.columns = [];
                return;
            }

            this.loading = true;
            this.clearMessages();
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/data-sources/${encodeURIComponent(this.sourceKey)}/tables`
                );
                this.tables = data.data || [];
                this.selectedTable = '';
                this.columns = [];
            } catch (err) {
                this.error = this.formatError(err.message, __('載入資料表失敗'));
            } finally {
                this.loading = false;
            }
        },

        async selectTable(name) {
            this.selectedTable = name || '';
            this.columns = [];
            if (!this.selectedTable || !this.sourceKey) return;

            this.loading = true;
            this.clearMessages();
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/data-sources/${encodeURIComponent(this.sourceKey)}/tables/${encodeURIComponent(this.selectedTable)}/columns`
                );
                this.columns = data.data || [];
            } catch (err) {
                this.error = this.formatError(err.message, __('載入欄位失敗'));
            } finally {
                this.loading = false;
            }
        },

        openCreateModal() {
            if (!this.canManage()) return;
            this.clearMessages();
            this.newTable = { name: '', columns: [{ name: '', type: 'TEXT', required: false }] };
            this.showCreateModal = true;
        },

        closeCreateModal() {
            this.showCreateModal = false;
        },

        addNewColumn() {
            if (this.newTable.columns.length >= 30) {
                this.error = __('欄位最多 30 個');
                return;
            }
            this.newTable.columns.push({ name: '', type: 'TEXT', required: false });
        },

        removeNewColumn(idx) {
            if (this.newTable.columns.length <= 1) return;
            this.newTable.columns.splice(idx, 1);
        },

        async createTable() {
            if (!this.canManage()) return;
            this.clearMessages();
            const payload = this.buildCreatePayload();
            if (!payload) return;

            this.loading = true;
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/tables`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                        body: JSON.stringify(payload),
                    }
                );
                this.showCreateModal = false;
                this.sourceKey = 'portal_data';
                await this.loadTables();
                await this.selectTable(data.data.table_name);
                this.message = __('資料表已建立');
            } catch (err) {
                this.error = this.formatError(err.message, __('建立資料表失敗'));
            } finally {
                this.loading = false;
            }
        },

        async resolveView() {
            if (!this.canManage()) return;
            this.clearMessages();
            if (!this.sourceKey || !this.selectedTable) {
                this.error = __('請先選擇資料表');
                return;
            }

            this.loading = true;
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/resolve-view`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                        body: JSON.stringify({
                            data_source: this.sourceKey,
                            table_name: this.selectedTable,
                        }),
                    }
                );
                this.message = data.created ? __('CRUD View 已建立') : __('CRUD View 已存在');
            } catch (err) {
                this.error = this.formatError(err.message, __('建立 CRUD View 失敗'));
            } finally {
                this.loading = false;
            }
        },

        canManage() {
            return typeof BkCaps === 'undefined' || BkCaps.can('nocode_builder.manage');
        },

        buildCreatePayload() {
            const tableName = String(this.newTable.name || '').trim();
            if (!this.validIdentifier(tableName)) {
                this.error = __('表名格式不正確');
                return null;
            }
            const loweredTableName = tableName.toLowerCase();
            if (loweredTableName.startsWith('sqlite_') || loweredTableName.startsWith('portal_')) {
                this.error = __('表名不可使用保留前綴');
                return null;
            }

            if (!Array.isArray(this.newTable.columns) || this.newTable.columns.length < 1) {
                this.error = __('請至少新增一個欄位');
                return null;
            }
            if (this.newTable.columns.length > 30) {
                this.error = __('欄位最多 30 個');
                return null;
            }

            const seen = new Set();
            const columns = [];
            for (const column of this.newTable.columns) {
                const name = String(column.name || '').trim();
                if (!this.validIdentifier(name)) {
                    this.error = __('欄位名格式不正確');
                    return null;
                }
                const loweredName = name.toLowerCase();
                if (loweredName === 'id' || loweredName === 'created_at') {
                    this.error = __('欄位名不可使用系統欄位');
                    return null;
                }
                if (seen.has(loweredName)) {
                    this.error = __('欄位名不可重複');
                    return null;
                }
                seen.add(loweredName);

                const type = String(column.type || '').toUpperCase();
                if (!this.columnTypes.includes(type)) {
                    this.error = __('欄位型別不支援');
                    return null;
                }
                columns.push({ name, type, required: column.required === true });
            }

            return {
                data_source: 'portal_data',
                table_name: tableName,
                columns,
            };
        },

        validIdentifier(value) {
            const text = String(value || '').trim();
            return text.length > 0 && text.length <= MAX_IDENTIFIER_LENGTH && IDENTIFIER_RE.test(text);
        },

        async fetchJson(url, options) {
            const res = await fetch(url, options || {});
            let data = null;
            try {
                data = await res.json();
            } catch (err) {
                throw new Error(__('伺服器回應格式不正確'));
            }
            if (!res.ok || !data.success) {
                throw new Error(data.error || __('請求失敗'));
            }
            return data;
        },

        formatError(code, fallback) {
            const messages = {
                table_exists: __('已存在同名資料表'),
                invalid_data_source: __('只能在 portal_data 新建資料表'),
                invalid_table_name: __('表名格式不正確'),
                invalid_columns: __('欄位設定不正確'),
                invalid_column_name: __('欄位名格式不正確'),
                reserved_column_name: __('欄位名不可使用系統欄位'),
                duplicate_column_name: __('欄位名不可重複'),
                invalid_column_type: __('欄位型別不支援'),
                table_not_found: __('找不到資料表'),
                create_table_failed: __('建立資料表失敗'),
            };
            return messages[code] || code || fallback;
        },

        clearMessages() {
            this.error = '';
            this.message = '';
        },
    };
}
