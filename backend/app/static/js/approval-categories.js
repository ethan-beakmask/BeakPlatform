/**
 * 核決權限類別管理 - Master-Detail + Create Modal + BeakTrellis 矩陣
 * 使用 Window Bridge 模式接收 Jinja2 變數
 */
function approvalCategoriesManager() {
    var config = window.__APPROVAL_CATEGORIES_CONFIG || {};
    var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

    return {
        categories: config.categories || [],
        selected: null,
        editForm: {},
        editErrors: [],
        editMessage: '',

        showCreateModal: false,
        createForm: {
            code: '',
            name: '',
            name_en: '',
            currency: 'TWD',
            sort_order: 0,
            description: ''
        },
        createErrors: [],
        createSubmitting: false,

        editSubmitting: false,
        deleteConfirm: false,
        _matrixGrid: null,

        init: function() {
            var self = this;
            this.$nextTick(function() { self._initMatrix(); });
        },

        /**
         * 初始化核決金額矩陣 (BeakTrellis)
         */
        _initMatrix: function() {
            var container = document.getElementById('matrix-container');
            if (!container) return;

            var treeData = config.matrixTree || [];
            var columns = config.matrixColumns || [];

            if (treeData.length === 0 || columns.length === 0) {
                container.style.display = 'none';
                return;
            }

            this._matrixGrid = new BeakTrellis(container, {
                data: treeData,
                treeMode: 'lines-dom',
                splitPane: true,
                columns: columns.map(function(col) {
                    return {
                        id: col.id,
                        label: col.label,
                        width: '130px',
                        sortable: false,
                        renderer: function(value) {
                            if (value === undefined || value === null || value === 0) return '0';
                            return Number(value).toLocaleString();
                        }
                    };
                }),
                onRowClick: function() {}
            });
        },

        /**
         * 選擇類別，載入編輯表單
         */
        selectCategory: function(cat) {
            this.selected = cat;
            this.editForm = {
                name: cat.name,
                name_en: cat.name_en,
                currency: cat.currency,
                description: cat.description,
                sort_order: cat.sort_order,
                is_active: cat.is_active
            };
            this.editErrors = [];
            this.editMessage = '';
            this.deleteConfirm = false;
            this._scrollMatrixToColumn(cat.secure_code);
        },

        /**
         * 將矩陣水平捲動到指定類別的欄位
         */
        _scrollMatrixToColumn: function(secureCode) {
            var grid = this._matrixGrid;
            if (!grid || !grid._rightPane) return;
            var th = grid._rightTableEl
                ? grid._rightTableEl.querySelector('th[data-column-id="' + secureCode + '"]')
                : null;
            if (!th) return;
            var pane = grid._rightPane;
            var paneRect = pane.getBoundingClientRect();
            var thRect = th.getBoundingClientRect();
            // 計算目標欄位相對於右面板的水平位置
            var targetLeft = thRect.left - paneRect.left + pane.scrollLeft;
            pane.scrollLeft = Math.max(0, targetLeft - 10);
        },

        /**
         * 新增 Modal：英文名稱自動產生代碼
         */
        autoGenerateCode: function() {
            this.createForm.code = this.createForm.name_en
                .toUpperCase()
                .replace(/\s+/g, '_')
                .replace(/[^A-Z0-9_]/g, '');
        },

        /**
         * 開啟新增 Modal
         */
        openCreateModal: function() {
            this.createForm = {
                code: '',
                name: '',
                name_en: '',
                currency: 'TWD',
                sort_order: 0,
                description: ''
            };
            this.createErrors = [];
            this.createSubmitting = false;
            this.showCreateModal = true;
        },

        /**
         * 提交新增 — 成功後重載頁面
         */
        submitCreate: async function() {
            this.createErrors = [];
            this.createSubmitting = true;

            var form = new FormData();
            form.append('csrf_token', csrfToken);
            form.append('code', this.createForm.code);
            form.append('name', this.createForm.name);
            form.append('name_en', this.createForm.name_en);
            form.append('currency', this.createForm.currency);
            form.append('sort_order', this.createForm.sort_order);
            form.append('description', this.createForm.description);

            try {
                var resp = await fetch(config.createUrl, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    },
                    body: form
                });
                var data = await resp.json();

                if (data.success) {
                    location.reload();
                } else {
                    this.createErrors = data.errors || ['建立失敗'];
                    this.createSubmitting = false;
                }
            } catch (e) {
                this.createErrors = ['網路錯誤: ' + e.message];
                this.createSubmitting = false;
            }
        },

        /**
         * 提交編輯 — 成功後重載頁面
         */
        submitEdit: async function() {
            if (!this.selected) return;
            this.editErrors = [];
            this.editMessage = '';
            this.editSubmitting = true;

            var form = new FormData();
            form.append('csrf_token', csrfToken);
            form.append('name', this.editForm.name);
            form.append('name_en', this.editForm.name_en);
            form.append('currency', this.editForm.currency);
            form.append('sort_order', this.editForm.sort_order);
            form.append('description', this.editForm.description);
            form.append('is_active', this.editForm.is_active ? 'true' : 'false');

            var editUrl = config.editUrlTemplate.replace('__SC__', this.selected.secure_code);

            try {
                var resp = await fetch(editUrl, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    },
                    body: form
                });
                var data = await resp.json();

                if (data.success) {
                    location.reload();
                } else {
                    this.editErrors = data.errors || ['更新失敗'];
                    this.editSubmitting = false;
                }
            } catch (e) {
                this.editErrors = ['網路錯誤: ' + e.message];
                this.editSubmitting = false;
            }
        },

        /**
         * 刪除類別 — 成功後重載頁面
         */
        submitDelete: async function() {
            if (!this.selected) return;

            var deleteUrl = config.deleteUrlTemplate.replace('__SC__', this.selected.secure_code);

            try {
                var resp = await fetch(deleteUrl, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    },
                    body: new URLSearchParams({ csrf_token: csrfToken })
                });
                var data = await resp.json();

                if (data.success) {
                    location.reload();
                } else {
                    this.editErrors = data.errors || ['刪除失敗'];
                    this.deleteConfirm = false;
                }
            } catch (e) {
                this.editErrors = ['網路錯誤: ' + e.message];
                this.deleteConfirm = false;
            }
        },

        /**
         * 取得設定上限的 URL
         */
        getLimitsUrl: function() {
            if (!this.selected) return '#';
            return config.limitsUrlTemplate.replace('__SC__', this.selected.secure_code);
        }
    };
}
