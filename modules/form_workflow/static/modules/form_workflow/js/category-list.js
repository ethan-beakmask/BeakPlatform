/* category-list.js — 分類管理 */

function categoryManager() {
    return {
        categories: [],
        loading: true,
        expanded: {},

        showModal: false,
        editingCategory: null,
        formData: {
            name: '',
            description: '',
            display_order: 0,
            parent_secure_code: null,
            show_in_form_design: true,
            show_in_workflow_design: true,
            show_in_form_center: true
        },
        saving: false,

        showDeleteModal: false,
        deletingCategory: null,

        get modalTitle() {
            if (this.editingCategory) {
                return this.editingCategory.parent_secure_code ? '編輯子分類' : '編輯父分類';
            }
            return this.formData.parent_secure_code ? '新增子分類' : '新增父分類';
        },

        async init() {
            await this.loadCategories();
        },

        async loadCategories() {
            this.loading = true;
            try {
                const res = await fetch(window.__BP + '/api/form-workflow/categories');
                const data = await res.json();
                if (data.success) {
                    this.categories = data.data || [];
                    for (const cat of this.categories) {
                        if (this.expanded[cat.secure_code] === undefined) {
                            this.expanded[cat.secure_code] = true;
                        }
                    }
                }
            } catch (e) {
                console.error('載入失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        toggleExpand(sc) {
            this.expanded[sc] = !this.expanded[sc];
        },

        getParentName(parentSc) {
            if (!parentSc) return '';
            const cat = this.categories.find(c => c.secure_code === parentSc);
            return cat ? cat.name : '';
        },

        openCreateModal(parentSc) {
            this.editingCategory = null;
            this.formData = {
                name: '',
                description: '',
                display_order: 0,
                parent_secure_code: parentSc || null,
                show_in_form_design: true,
                show_in_workflow_design: true,
                show_in_form_center: true
            };
            this.showModal = true;
        },

        editCategory(cat) {
            if (cat.is_system) return;
            this.editingCategory = cat;
            this.formData = {
                name: cat.name,
                description: cat.description || '',
                display_order: cat.display_order || 0,
                parent_secure_code: cat.parent_secure_code || null,
                show_in_form_design: cat.show_in_form_design !== false,
                show_in_workflow_design: cat.show_in_workflow_design !== false,
                show_in_form_center: cat.show_in_form_center !== false
            };
            this.showModal = true;
        },

        closeModal() {
            this.showModal = false;
            this.editingCategory = null;
        },

        async saveCategory() {
            if (this.saving) return;
            this.saving = true;

            try {
                const url = this.editingCategory
                    ? `${window.__BP}/api/form-workflow/categories/${this.editingCategory.secure_code}`
                    : window.__BP + '/api/form-workflow/categories';
                const method = this.editingCategory ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.formData)
                });
                const data = await res.json();

                if (data.success) {
                    this.closeModal();
                    this.loadCategories();
                } else {
                    alert('操作失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('操作失敗: ' + e.message);
            } finally {
                this.saving = false;
            }
        },

        confirmDelete(cat) {
            if (cat.is_system) return;
            this.deletingCategory = cat;
            this.showDeleteModal = true;
        },

        async deleteCategory() {
            if (!this.deletingCategory) return;

            try {
                const res = await fetch(`${window.__BP}/api/form-workflow/categories/${this.deletingCategory.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();

                if (data.success) {
                    this.showDeleteModal = false;
                    this.deletingCategory = null;
                    this.loadCategories();
                } else {
                    alert('刪除失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('刪除失敗: ' + e.message);
            }
        }
    };
}
