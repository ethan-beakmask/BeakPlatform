'use strict';

/**
 * 職稱管理頁 — BeakTrellis 樹狀格線 + Modal 新增/編輯
 *
 * 樹結構：職系(群組) → 職稱(資料列)
 * 點擊職稱列開啟編輯 Modal，職系列不可點擊
 *
 * Window Bridge: window.__JOB_TITLES_CONFIG
 */

function jobTitlesManager() {
    var config = window.__JOB_TITLES_CONFIG || {};

    return {
        // Modal 狀態
        showCreateModal: false,
        showEditModal: false,

        // 新增表單
        createForm: {
            name: '',
            code: '',
            name_en: '',
            short_name: '',
            job_level_secure_code: '',
            job_family_secure_code: '',
            is_supervisor: false,
            description: '',
            sort_order: 0
        },

        // 編輯表單
        editForm: {
            secure_code: '',
            code: '',
            name: '',
            name_en: '',
            short_name: '',
            job_level_secure_code: '',
            job_family_secure_code: '',
            is_supervisor: false,
            description: '',
            sort_order: 0,
            is_active: true,
            is_system_default: false
        },

        // UI 狀態
        formErrors: [],
        submitting: false,

        // 下拉選單選項
        familyOptions: config.familyOptions || [],
        levelOptions: config.levelOptions || [],

        // BeakTrellis 實例
        grid: null,

        init: function() {
            var self = this;
            this.$nextTick(function() { self._initGrid(); });
        },

        _initGrid: function() {
            var container = document.getElementById('trellis-container');
            if (!container || !config.treeData) return;

            var self = this;

            this.grid = new BeakTrellis(container, {
                data: config.treeData,
                treeMode: 'lines-dom',
                splitPane: true,
                columns: [
                    {
                        id: 'code',
                        label: __('代碼'),
                        width: '100px',
                        sortable: true,
                        renderer: function(value, row) {
                            if (row && row.data && row.data._isFamily) return '';
                            return '<code>' + (value || '') + '</code>';
                        }
                    },
                    {
                        id: 'name_en',
                        label: __('英文名稱'),
                        width: '180px',
                        sortable: true,
                        renderer: function(value, row) {
                            if (row && row.data && row.data._isFamily) return '';
                            return value || '-';
                        }
                    },
                    {
                        id: 'job_level_text',
                        label: __('職等'),
                        width: '160px',
                        sortable: true,
                        renderer: function(value, row) {
                            if (row && row.data && row.data._isFamily) return '';
                            return value || '-';
                        }
                    },
                    {
                        id: 'is_supervisor',
                        label: __('管理職'),
                        width: '70px',
                        renderer: function(value, row) {
                            if (row && row.data && row.data._isFamily) return '';
                            return value ? __('<span style="color:#0066cc;">是</span>') : '-';
                        }
                    },
                    {
                        id: 'is_active',
                        label: __('狀態'),
                        width: '60px',
                        renderer: function(value, row) {
                            if (row && row.data && row.data._isFamily) return '';
                            return value ? __('啟用') : __('<span style="color:#999;">停用</span>');
                        }
                    }
                ],
                onRowClick: function(id, node, e) {
                    // 只有職稱節點可點擊編輯
                    if (node.data && node.data._isTitle) {
                        self.openEditModal(node.data);
                    }
                }
            });

            this.grid.expandAll();
        },

        // ==================== 新增 Modal ====================

        openCreateModal: function() {
            this.createForm = {
                name: '',
                code: '',
                name_en: '',
                short_name: '',
                job_level_secure_code: '',
                job_family_secure_code: '',
                is_supervisor: false,
                description: '',
                sort_order: 0
            };
            this.formErrors = [];
            this.submitting = false;
            this.showCreateModal = true;
        },

        submitCreate: function() {
            if (this.submitting) return;
            this.formErrors = [];
            this.submitting = true;

            var self = this;
            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);
            formData.append('name', this.createForm.name);
            formData.append('code', this.createForm.code);
            formData.append('name_en', this.createForm.name_en);
            formData.append('short_name', this.createForm.short_name);
            formData.append('job_level_secure_code', this.createForm.job_level_secure_code);
            formData.append('job_family_secure_code', this.createForm.job_family_secure_code);
            formData.append('is_supervisor', this.createForm.is_supervisor ? 'true' : 'false');
            formData.append('description', this.createForm.description);
            formData.append('sort_order', this.createForm.sort_order);

            fetch(config.urls.create, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            })
            .then(function(resp) { return resp.json(); })
            .then(function(result) {
                if (result.success) {
                    location.reload();
                } else {
                    self.formErrors = result.errors || [__('操作失敗')];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = [__('網路錯誤')];
                self.submitting = false;
            });
        },

        // ==================== 編輯 Modal ====================

        openEditModal: function(data) {
            this.editForm = {
                secure_code: data.secure_code,
                code: data.code,
                name: data.name,
                name_en: data.name_en || '',
                short_name: data.short_name || '',
                job_level_secure_code: data.job_level_secure_code,
                job_family_secure_code: data.job_family_secure_code,
                is_supervisor: data.is_supervisor,
                description: data.description || '',
                sort_order: data.sort_order,
                is_active: data.is_active,
                is_system_default: data.is_system_default
            };
            this.formErrors = [];
            this.submitting = false;
            this.showEditModal = true;
        },

        submitEdit: function() {
            if (this.submitting) return;
            this.formErrors = [];
            this.submitting = true;

            var self = this;
            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);
            formData.append('name', this.editForm.name);
            formData.append('name_en', this.editForm.name_en);
            formData.append('short_name', this.editForm.short_name);
            formData.append('job_level_secure_code', this.editForm.job_level_secure_code);
            formData.append('job_family_secure_code', this.editForm.job_family_secure_code);
            formData.append('is_supervisor', this.editForm.is_supervisor ? 'true' : 'false');
            formData.append('description', this.editForm.description);
            formData.append('sort_order', this.editForm.sort_order);
            formData.append('is_active', this.editForm.is_active ? 'true' : 'false');

            var url = config.urls.edit.replace('__SC__', this.editForm.secure_code);
            fetch(url, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            })
            .then(function(resp) { return resp.json(); })
            .then(function(result) {
                if (result.success) {
                    location.reload();
                } else {
                    self.formErrors = result.errors || [__('操作失敗')];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = [__('網路錯誤')];
                self.submitting = false;
            });
        },

        // ==================== 刪除 ====================

        submitDelete: function() {
            var name = this.editForm.name;
            if (!confirm(__('確定要刪除職稱「') + name + __('」嗎？'))) return;
            if (this.submitting) return;

            this.formErrors = [];
            this.submitting = true;

            var self = this;
            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);

            var url = config.urls['delete'].replace('__SC__', this.editForm.secure_code);
            fetch(url, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            })
            .then(function(resp) { return resp.json(); })
            .then(function(result) {
                if (result.success) {
                    location.reload();
                } else {
                    self.formErrors = result.errors || [__('刪除失敗')];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = [__('網路錯誤')];
                self.submitting = false;
            });
        }
    };
}
