/**
 * module-permissions.js
 * 模組權限管理 - ACL 互動邏輯
 */
function modulePermissions() {
    return {
        expandedModule: null,
        aclList: [],
        aclLoading: false,

        // 類型標籤
        typeLabels: {
            'ROLE': __('角色'),
            'DEPARTMENT': __('部門'),
            'GROUP': __('群組'),
            'ACCOUNT': __('帳號'),
        },

        // 新增模態框
        showAddModal: false,
        addModuleCode: '',
        addTargetType: '',
        addTargetSC: '',
        targetSearch: '',
        targetList: [],

        async toggleACL(moduleCode, moduleLabel) {
            if (this.expandedModule === moduleCode) {
                this.expandedModule = null;
                this.aclList = [];
                return;
            }
            this.expandedModule = moduleCode;
            await this.loadACL(moduleCode);
        },

        async loadACL(moduleCode) {
            this.aclLoading = true;
            this.aclList = [];
            try {
                const res = await fetch(window.__BP + '/api/module-access/' + encodeURIComponent(moduleCode));
                const data = await res.json();
                if (data.success) {
                    this.aclList = data.data;
                }
            } catch (e) {
                console.error('[ModPerm] loadACL error:', e);
            }
            this.aclLoading = false;
        },

        openAddModal(moduleCode) {
            this.addModuleCode = moduleCode;
            this.addTargetType = '';
            this.addTargetSC = '';
            this.targetSearch = '';
            this.targetList = [];
            this.showAddModal = true;
        },

        async loadTargets() {
            if (!this.addTargetType) {
                this.targetList = [];
                return;
            }
            try {
                const params = new URLSearchParams({
                    type: this.addTargetType,
                    q: this.targetSearch,
                });
                const res = await fetch(window.__BP + '/api/module-access/targets?' + params);
                const data = await res.json();
                if (data.success) {
                    this.targetList = data.data;
                }
            } catch (e) {
                console.error('[ModPerm] loadTargets error:', e);
            }
        },

        async submitAdd() {
            if (!this.addTargetSC || !this.addModuleCode || !this.addTargetType) return;

            try {
                const res = await fetch(window.__BP + '/api/module-access/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        module_code: this.addModuleCode,
                        target_type: this.addTargetType,
                        target_secure_code: this.addTargetSC,
                    }),
                });
                const data = await res.json();
                if (data.success) {
                    this.showAddModal = false;
                    await this.loadACL(this.addModuleCode);
                } else {
                    alert(data.error || __('新增失敗'));
                }
            } catch (e) {
                alert(__('新增失敗: ') + e.message);
            }
        },

        async removeACL(secureCode) {
            if (!confirm(__('確定要移除此使用權指派？'))) return;

            try {
                const res = await fetch(window.__BP + '/api/module-access/' + secureCode, {
                    method: 'DELETE',
                });
                const data = await res.json();
                if (data.success) {
                    await this.loadACL(this.expandedModule);
                } else {
                    alert(data.error || __('移除失敗'));
                }
            } catch (e) {
                alert(__('移除失敗: ') + e.message);
            }
        },
    };
}
