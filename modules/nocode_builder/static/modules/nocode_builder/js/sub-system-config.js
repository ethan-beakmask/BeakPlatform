/**
 * sub_system_config.html - Alpine.js Manager
 * 子系統設定：基本資訊 + 權限政策組管理
 */
function subSystemConfigManager() {
    return {
        loading: true,
        secureCode: '',
        form: {
            name: '',
            description: '',
            icon: '',
        },
        developerNames: [],

        // 權限政策組
        policyGroups: [],
        showPolicyModal: false,
        editingPolicy: null,
        policyForm: { name: '', description: '' },

        // 規則編輯
        showRulePanel: null,
        newRule: {
            grant_type: 'department',
            grant_target: '',
            grant_target_name: '',
            include_children: false,
            _selectedName: '',
        },
        ruleTargetOptions: [],
        ruleTreeLoading: false,
        _ruleTreeInstance: null,

        toast: { show: false, message: '', type: 'success' },

        async init() {
            const config = window.__SSC_CONFIG || {};
            this.secureCode = config.secureCode || '';

            await Promise.all([
                this.loadSubSystem(),
                this.loadPolicies(),
            ]);
            this.loading = false;
        },

        // =================================================================
        // 基本資訊
        // =================================================================

        async loadSubSystem() {
            try {
                const res = await fetch('/api/nocode-builder/sub-systems/' + this.secureCode);
                const data = await res.json();
                if (data.success) {
                    const d = data.data;
                    this.form.name = d.name || '';
                    this.form.description = d.description || '';
                    this.form.icon = d.icon || '';
                    this.developerNames = d.developer_names || [];
                }
            } catch (e) {
                console.error('Load sub-system failed:', e);
            }
        },

        async save() {
            if (!this.form.name.trim()) {
                this.showToast('名稱不可為空', 'error');
                return;
            }
            try {
                const res = await fetch('/api/nocode-builder/sub-systems/' + this.secureCode, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.form),
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已儲存', 'success');
                } else {
                    this.showToast(data.error || '儲存失敗', 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
        },

        // =================================================================
        // 權限政策組 CRUD
        // =================================================================

        async loadPolicies() {
            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode + '/permission-policies'
                );
                const data = await res.json();
                if (data.success) {
                    this.policyGroups = data.data || [];
                }
            } catch (e) {
                console.error('Load policies failed:', e);
            }
        },

        openAddPolicy() {
            this.editingPolicy = null;
            this.policyForm = { name: '', description: '' };
            this.showPolicyModal = true;
        },

        openEditPolicy(pg) {
            this.editingPolicy = pg;
            this.policyForm = { name: pg.name, description: pg.description || '' };
            this.showPolicyModal = true;
        },

        async savePolicy() {
            if (!this.policyForm.name.trim()) {
                this.showToast('政策組名稱不可為空', 'error');
                return;
            }
            try {
                let url, method;
                if (this.editingPolicy) {
                    url = '/api/nocode-builder/sub-systems/' + this.secureCode
                        + '/permission-policies/' + this.editingPolicy.secure_code;
                    method = 'PUT';
                } else {
                    url = '/api/nocode-builder/sub-systems/' + this.secureCode
                        + '/permission-policies';
                    method = 'POST';
                }
                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.policyForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showPolicyModal = false;
                    this.showToast(this.editingPolicy ? '政策組已更新' : '政策組已建立', 'success');
                    await this.loadPolicies();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗: ' + e.message, 'error');
            }
        },

        async deletePolicy(pg) {
            const msg = pg.usage_count > 0
                ? `此政策組有 ${pg.usage_count} 個網頁正在使用，刪除後這些網頁將變為禁止狀態。確定刪除?`
                : '確定刪除此政策組?';
            if (!confirm(msg)) return;

            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/permission-policies/' + pg.secure_code,
                    { method: 'DELETE' }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '已刪除', 'success');
                    if (this.showRulePanel === pg.secure_code) {
                        this.showRulePanel = null;
                    }
                    await this.loadPolicies();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // =================================================================
        // 規則管理
        // =================================================================

        toggleRulePanel(pg) {
            if (this.showRulePanel === pg.secure_code) {
                this.showRulePanel = null;
            } else {
                this.showRulePanel = pg.secure_code;
                this.resetNewRule();
            }
        },

        resetNewRule() {
            this.newRule = {
                grant_type: 'department',
                grant_target: '',
                grant_target_name: '',
                include_children: false,
                _selectedName: '',
            };
            this.ruleTargetOptions = [];
            this._destroyRuleTree();
        },

        getPolicyRules(pgSc) {
            const pg = this.policyGroups.find(g => g.secure_code === pgSc);
            return pg ? (pg.rules || []) : [];
        },

        async onRuleTypeChange() {
            this.newRule.grant_target = '';
            this.newRule.grant_target_name = '';
            this.newRule._selectedName = '';
            this.ruleTargetOptions = [];
            this._destroyRuleTree();

            if (this.newRule.grant_type === 'user') {
                await this._loadUserTargets();
            } else {
                await this._loadTreeTargets();
            }
        },

        async _loadUserTargets() {
            try {
                const type = 'ACCOUNT';
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/site-map/targets?type=' + type
                );
                const data = await res.json();
                if (data.success) {
                    this.ruleTargetOptions = (data.data || []).map(t => ({
                        value: t.secure_code || t.value,
                        label: t.display_name || t.name || t.label || t.value,
                    }));
                }
            } catch (e) {
                console.error('Load user targets failed:', e);
            }
        },

        async _loadTreeTargets() {
            this.ruleTreeLoading = true;
            try {
                const type = this.newRule.grant_type === 'department' ? 'DEPARTMENT' : 'GROUP';
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/site-map/targets?type=' + type
                );
                const data = await res.json();
                if (data.success) {
                    const items = data.data || [];
                    this.$nextTick(() => {
                        this._renderRuleTree(items);
                    });
                }
            } catch (e) {
                console.error('Load tree targets failed:', e);
            } finally {
                this.ruleTreeLoading = false;
            }
        },

        _renderRuleTree(items) {
            this._destroyRuleTree();
            const container = document.getElementById('pp-rule-tree-container');
            if (!container || !items.length) return;

            const treeData = items.map(item => ({
                title: item.display_name || item.name || item.label || '',
                key: item.secure_code || item.value,
                children: (item.children || []).map(c => ({
                    title: c.display_name || c.name || c.label || '',
                    key: c.secure_code || c.value,
                })),
            }));

            const self = this;
            this._ruleTreeInstance = new mar10.Wunderbaum({
                element: container,
                source: treeData,
                selectMode: '1',
                click(e) {
                    const node = e.node;
                    if (node) {
                        self.newRule.grant_target = node.key;
                        self.newRule.grant_target_name = node.title;
                        self.newRule._selectedName = node.title;
                    }
                },
            });
        },

        _destroyRuleTree() {
            if (this._ruleTreeInstance) {
                try { this._ruleTreeInstance.destroy(); } catch (_) {}
                this._ruleTreeInstance = null;
            }
            const container = document.getElementById('pp-rule-tree-container');
            if (container) container.innerHTML = '';
        },

        async addRule(pgSc) {
            if (!this.newRule.grant_target) {
                this.showToast('請選擇目標', 'error');
                return;
            }
            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/permission-policies/' + pgSc + '/rules',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            grant_type: this.newRule.grant_type,
                            grant_target: this.newRule.grant_target,
                            grant_target_name: this.newRule.grant_target_name || this.newRule._selectedName,
                            include_children: this.newRule.include_children,
                        }),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast('規則已新增', 'success');
                    this.resetNewRule();
                    await this.loadPolicies();
                } else {
                    this.showToast(data.error || '新增失敗', 'error');
                }
            } catch (e) {
                this.showToast('新增失敗: ' + e.message, 'error');
            }
        },

        async deleteRule(pgSc, ruleSc) {
            if (!confirm('確定刪除此規則?')) return;
            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/permission-policies/rules/' + ruleSc,
                    { method: 'DELETE' }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast('規則已刪除', 'success');
                    await this.loadPolicies();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        // =================================================================
        // 輔助
        // =================================================================

        getPermTypeLabel(type) {
            return { department: '部門', group: '社群', user: '個人' }[type] || type;
        },

        getPermTypeCss(type) {
            return { department: 'dept', group: 'group', user: 'user' }[type] || '';
        },

        ruleSummary(pg) {
            const rules = pg.rules || [];
            if (!rules.length) return '(無規則)';
            const items = rules.slice(0, 3).map(r => {
                const label = this.getPermTypeLabel(r.grant_type);
                return label + ':' + (r.grant_target_name || r.grant_target);
            });
            if (rules.length > 3) items.push('...(共' + rules.length + '條)');
            return items.join(', ');
        },

        showToast(message, type) {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
