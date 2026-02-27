/**
 * view_config.html - Alpine.js Manager
 * 選表 + 欄位配置
 */
function viewConfigManager() {
    const config = window.__DC_CONFIG || {};

    return {
        isEdit: !!config.secureCode,
        secureCode: config.secureCode,
        tables: [],
        columns: [],
        dbName: '',
        loadingCols: false,
        saving: false,
        toast: { show: false, message: '', type: 'success' },

        form: {
            name: '',
            table_name: '',
            description: '',
            allow_create: true,
            allow_edit: true,
            allow_delete: true,
            is_active: true,
            page_size: 20,
            default_sort_column: '',
            default_sort_dir: 'ASC',
            soft_delete_column: '',
        },

        async init() {
            await this.loadDbInfo();
            await this.loadTables();
            if (this.isEdit) {
                await this.loadView();
            }
        },

        async loadDbInfo() {
            try {
                const res = await fetch('/api/data-crud/db-info');
                const data = await res.json();
                if (data.success) {
                    this.dbName = data.data.db_name || '';
                }
            } catch (e) {
                console.error('Load db info failed:', e);
            }
        },

        async loadTables() {
            try {
                const res = await fetch('/api/data-crud/schema/tables');
                const data = await res.json();
                if (data.success) {
                    this.tables = data.data || [];
                }
            } catch (e) {
                console.error('Load tables failed:', e);
            }
        },

        async loadView() {
            try {
                const res = await fetch(`/api/data-crud/views/${this.secureCode}`);
                const data = await res.json();
                if (data.success) {
                    const v = data.data;
                    this.form.name = v.name;
                    this.form.table_name = v.table_name;
                    this.form.description = v.description || '';
                    this.form.allow_create = v.allow_create;
                    this.form.allow_edit = v.allow_edit;
                    this.form.allow_delete = v.allow_delete;
                    this.form.is_active = v.is_active;
                    this.form.page_size = v.page_size;
                    this.form.default_sort_column = v.default_sort_column || '';
                    this.form.default_sort_dir = v.default_sort_dir || 'ASC';
                    this.form.soft_delete_column = v.soft_delete_column || '';

                    // 載入欄位，然後 merge 已存的 config
                    await this.loadColumns(v.table_name);
                    this.mergeColumnsConfig(v.columns_config || []);
                } else {
                    this.showToast('載入失敗: ' + (data.error || ''), 'error');
                }
            } catch (e) {
                this.showToast('載入失敗', 'error');
            }
        },

        async onTableChange() {
            if (this.form.table_name) {
                await this.loadColumns(this.form.table_name);
                // 自動偵測軟刪除欄位
                const hasIsDeleted = this.columns.some(c => c.column === 'is_deleted');
                if (hasIsDeleted) {
                    this.form.soft_delete_column = 'is_deleted';
                }
            } else {
                this.columns = [];
            }
        },

        async loadColumns(tableName) {
            this.loadingCols = true;
            try {
                const res = await fetch(`/api/data-crud/schema/tables/${tableName}/columns`);
                const data = await res.json();
                if (data.success) {
                    this.columns = (data.data || []).map((col, idx) => {
                        const isSys = !!col.is_system;
                        return {
                            column: col.column,
                            db_type: col.db_type,
                            nullable: col.nullable,
                            is_pk: col.is_pk,
                            is_system: isSys,
                            system_reason: col.system_reason || null,
                            label: col.comment || col.column,
                            visible: true,
                            // 系統欄位預設不勾表單，但允許用戶勾選；強制唯讀
                            visible_in_form: !col.is_pk && !isSys,
                            readonly: isSys ? true : col.is_pk,
                            width: 150,
                            sort_order: idx + 1,
                        };
                    });
                }
            } catch (e) {
                console.error('Load columns failed:', e);
            } finally {
                this.loadingCols = false;
            }
        },

        mergeColumnsConfig(savedConfig) {
            // 用已存的 config 覆蓋欄位設定
            const savedMap = {};
            savedConfig.forEach(c => { savedMap[c.column] = c; });

            this.columns = this.columns.map((col, idx) => {
                const saved = savedMap[col.column];
                if (saved) {
                    const merged = {
                        ...col,
                        label: saved.label || col.column,
                        visible: saved.visible !== undefined ? saved.visible : true,
                        visible_in_form: saved.visible_in_form !== undefined ? saved.visible_in_form : !col.is_pk,
                        readonly: saved.readonly !== undefined ? saved.readonly : col.is_pk,
                        width: saved.width || 150,
                        sort_order: saved.sort_order !== undefined ? saved.sort_order : idx + 1,
                    };
                    // 系統欄位: 強制唯讀（表單可見性尊重用戶設定）
                    if (col.is_system) {
                        merged.readonly = true;
                    }
                    return merged;
                }
                return col;
            });

            // 按 sort_order 排序
            this.columns.sort((a, b) => a.sort_order - b.sort_order);
        },

        async save() {
            if (!this.form.name.trim()) {
                this.showToast('請輸入視圖名稱', 'error');
                return;
            }
            if (!this.form.table_name) {
                this.showToast('請選擇資料表', 'error');
                return;
            }

            // 組裝 columns_config
            const columnsConfig = this.columns.map((col, idx) => ({
                column: col.column,
                label: col.label || col.column,
                visible: col.visible,
                visible_in_form: col.visible_in_form,
                readonly: col.is_system ? true : col.readonly,
                width: col.width,
                sort_order: idx + 1,
                db_type: col.db_type,
                nullable: col.nullable,
                is_pk: col.is_pk,
                is_system: col.is_system || false,
                system_reason: col.system_reason || null,
            }));

            const payload = {
                name: this.form.name.trim(),
                table_name: this.form.table_name,
                description: this.form.description,
                columns_config: columnsConfig,
                allow_create: this.form.allow_create,
                allow_edit: this.form.allow_edit,
                allow_delete: this.form.allow_delete,
                is_active: this.form.is_active,
                page_size: this.form.page_size,
                default_sort_column: this.form.default_sort_column || null,
                default_sort_dir: this.form.default_sort_dir,
                soft_delete_column: this.form.soft_delete_column || null,
            };

            this.saving = true;
            try {
                const url = this.isEdit
                    ? `/api/data-crud/views/${this.secureCode}`
                    : '/api/data-crud/views';
                const method = this.isEdit ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    if (!this.isEdit) {
                        // 新建: 跳轉到配置頁
                        window.location.href = `/data-crud/views/${data.data.secure_code}/config`;
                    } else {
                        this.showToast('已儲存', 'success');
                    }
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗', 'error');
            } finally {
                this.saving = false;
            }
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
