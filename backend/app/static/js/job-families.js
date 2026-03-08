'use strict';

/**
 * 職系管理頁 — BeakTrellis 樹狀格線 + Modal 編輯
 *
 * 載入順序: beak-tree-model.js → beak-trellis.js → beak-trellis-splitpane.js
 *           → beak-tree-lines-dom.js → job-families.js
 *
 * Window Bridge: window.__JOB_FAMILIES_CONFIG
 */

function jobFamiliesManager() {
    var config = window.__JOB_FAMILIES_CONFIG || {};

    return {
        // Modal 狀態
        showCreateModal: false,
        showEditModal: false,

        // 新增表單
        createForm: {
            name: '',
            code: '',
            name_en: '',
            family_type: 'PROFESSIONAL',
            parent_secure_code: '',
            description: '',
            sort_order: 0
        },

        // 編輯表單
        editForm: {
            secure_code: '',
            code: '',
            name: '',
            name_en: '',
            family_type: '',
            parent_secure_code: '',
            description: '',
            sort_order: 0,
            is_active: true,
            is_system_default: false
        },

        // 錯誤訊息
        formErrors: [],
        submitting: false,

        // 設定
        parentOptions: config.parentOptions || [],
        familyTypes: config.familyTypes || [],

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
                        label: '代碼',
                        width: '100px',
                        sortable: true
                    },
                    {
                        id: 'name_en',
                        label: '英文名稱',
                        width: '150px',
                        sortable: true,
                        renderer: function(value) {
                            return value || '-';
                        }
                    },
                    {
                        id: 'family_type',
                        label: '類型',
                        width: '100px',
                        sortable: true,
                        renderer: function(value) {
                            if (value === 'MANAGER') {
                                return '<span style="color:#0066cc;">管理職</span>';
                            }
                            return '<span style="color:#009933;">專業職</span>';
                        }
                    },
                    {
                        id: 'sort_order',
                        label: '排序',
                        width: '60px',
                        sortable: true
                    },
                    {
                        id: 'is_active',
                        label: '狀態',
                        width: '60px',
                        renderer: function(value) {
                            return value ? '啟用' : '<span style="color:#999;">停用</span>';
                        }
                    }
                ],
                onRowClick: function(id, node, e) {
                    self.openEditModal(node.data);
                }
            });

            // 預設展開所有節點
            this.grid.expandAll();
        },

        // ==================== 新增 Modal ====================

        openCreateModal: function() {
            this.createForm = {
                name: '',
                code: '',
                name_en: '',
                family_type: 'PROFESSIONAL',
                parent_secure_code: '',
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
            formData.append('family_type', this.createForm.family_type);
            formData.append('parent_secure_code', this.createForm.parent_secure_code);
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
                    self.formErrors = result.errors || ['操作失敗'];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = ['網路錯誤'];
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
                family_type: data.family_type,
                parent_secure_code: data.parent_secure_code || '',
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
            formData.append('family_type', this.editForm.family_type);
            formData.append('parent_secure_code', this.editForm.parent_secure_code);
            formData.append('description', this.editForm.description);
            formData.append('sort_order', this.editForm.sort_order);
            if (this.editForm.is_active) {
                formData.append('is_active', 'true');
            }

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
                    self.formErrors = result.errors || ['操作失敗'];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = ['網路錯誤'];
                self.submitting = false;
            });
        },

        // ==================== 刪除 ====================

        submitDelete: function(cascadeDelete) {
            var name = this.editForm.name;
            var msg = cascadeDelete
                ? '確定要刪除職系「' + name + '」及其所有職稱嗎？此操作無法復原。'
                : '確定要刪除職系「' + name + '」嗎？';

            if (!confirm(msg)) return;
            if (this.submitting) return;

            this.formErrors = [];
            this.submitting = true;

            var self = this;
            var formData = new FormData();
            formData.append('csrf_token', config.csrfToken);
            if (cascadeDelete) {
                formData.append('cascade_delete', 'true');
            }

            var url = config.urls.delete.replace('__SC__', this.editForm.secure_code);
            fetch(url, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: formData
            })
            .then(function(resp) { return resp.json(); })
            .then(function(result) {
                if (result.success) {
                    location.reload();
                } else if (result.confirm_cascade) {
                    // 後端回傳需要連動刪除確認
                    self.submitting = false;
                    var count = result.title_count || 0;
                    if (confirm('此職系有 ' + count + ' 個職稱使用中，確定要連同職稱一併刪除嗎？')) {
                        self.submitDelete(true);
                    }
                } else {
                    self.formErrors = result.errors || ['刪除失敗'];
                    self.submitting = false;
                }
            })
            .catch(function() {
                self.formErrors = ['網路錯誤'];
                self.submitting = false;
            });
        }
    };
}
