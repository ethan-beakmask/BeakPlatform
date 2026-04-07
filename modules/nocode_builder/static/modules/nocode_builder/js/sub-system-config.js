/**
 * sub_system_config.html - Alpine.js Manager
 * 子系統設定：基本資訊 + 權限政策組管理
 *
 * 權限政策組規則選擇器參考 form_workflow/mappings.js 的做法：
 * - 自建 DOM tree（非 Wunderbaum）
 * - 部門：虛擬企業根 __ORG_ROOT__ + 部門樹
 * - 社群：雙根（企業內部群組 + 外部廠商群組）
 * - 個人：下拉選單
 * - 資料快取避免重複載入
 */
function subSystemConfigManager() {
    return {
        loading: true,
        secureCode: '',
        orgName: '',
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

        // 樹狀資料快取
        _permCache: {
            departments: null,
            groups: null,
            users: null,
        },

        toast: { show: false, message: '', type: 'success' },

        async init() {
            const config = window.__SSC_CONFIG || {};
            this.secureCode = config.secureCode || '';
            this.orgName = config.orgName || '企業';

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

        async quickAddPolicy() {
            // 一鍵建立：自動命名，建立後直接展開規則面板
            const idx = this.policyGroups.length + 1;
            const autoName = '政策組 ' + idx;
            try {
                const res = await fetch(
                    '/api/nocode-builder/sub-systems/' + this.secureCode + '/permission-policies',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: autoName, description: '' }),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    await this.loadPolicies();
                    // 自動展開新建的政策組規則面板
                    const newSc = data.data?.secure_code;
                    if (newSc) {
                        this.showRulePanel = newSc;
                        this.resetNewRule();
                        this.$nextTick(() => this._loadPermTargets(this.newRule.grant_type));
                    }
                    this.showToast('政策組已建立，可直接新增規則', 'success');
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            }
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
                const url = '/api/nocode-builder/sub-systems/' + this.secureCode
                    + '/permission-policies/' + this.editingPolicy.secure_code;
                const res = await fetch(url, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.policyForm),
                });
                const data = await res.json();
                if (data.success) {
                    this.showPolicyModal = false;
                    this.showToast('政策組已更新', 'success');
                    await this.loadPolicies();
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
            }
        },

        async deletePolicy(pg) {
            const msg = pg.usage_count > 0
                ? '此政策組有 ' + pg.usage_count + ' 個網頁正在使用，刪除後這些網頁將變為禁止狀態。確定刪除?'
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
                // 自動載入預設類型的樹（解決原本要手動切換才載入的問題）
                this.$nextTick(() => this._loadPermTargets(this.newRule.grant_type));
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
        },

        getPolicyRules(pgSc) {
            const pg = this.policyGroups.find(g => g.secure_code === pgSc);
            return pg ? (pg.rules || []) : [];
        },

        async onRuleTypeChange() {
            this.newRule.grant_target = '';
            this.newRule.grant_target_name = '';
            this.newRule._selectedName = '';
            this.newRule.include_children = false;
            this.ruleTargetOptions = [];
            await this._loadPermTargets(this.newRule.grant_type);
        },

        // =================================================================
        // 樹狀/下拉目標載入（同 mappings.js 做法）
        // =================================================================

        async _loadPermTargets(grantType) {
            this.ruleTargetOptions = [];
            const containerId = 'pp-rule-tree-' + this.showRulePanel;
            const container = document.getElementById(containerId);

            if (grantType === 'department' || grantType === 'group') {
                this.ruleTreeLoading = true;
                if (container) container.innerHTML = '';

                try {
                    let treeRoots = [];

                    if (grantType === 'department') {
                        if (!this._permCache.departments) {
                            const res = await fetch('/api/units/departments?tree=true');
                            const data = await res.json();
                            this._permCache.departments = data.units || [];
                        }
                        treeRoots = [{
                            secure_code: '__ORG_ROOT__',
                            name: this.orgName,
                            full_path: this.orgName,
                            children: this._permCache.departments,
                            _isVirtualRoot: true,
                        }];
                    } else {
                        // 社群：雙根（企業內部 + 外部廠商）
                        if (!this._permCache.groups) {
                            const res = await fetch('/api/units/groups?tree=true');
                            const data = await res.json();
                            this._permCache.groups = data.units || [];
                        }
                        var intGroups = [];
                        var extGroups = [];
                        for (var i = 0; i < this._permCache.groups.length; i++) {
                            var g = this._permCache.groups[i];
                            if (g.code === 'EXTERNAL_VENDORS' || g.code === 'external_vendors') {
                                extGroups.push(g);
                            } else {
                                intGroups.push(g);
                            }
                        }
                        // 企業內部群組根
                        treeRoots.push({
                            secure_code: '__ORG_ROOT__',
                            name: this.orgName,
                            full_path: this.orgName,
                            children: intGroups,
                            _isVirtualRoot: true,
                        });
                        // 外部廠商根（使用實際 DB 節點，展開其子群組）
                        for (var j = 0; j < extGroups.length; j++) {
                            treeRoots.push(extGroups[j]);
                        }
                    }

                    if (container) {
                        this._renderTree(container, treeRoots, 0);
                    }
                } catch (e) {
                    console.error('Load tree targets failed:', e);
                } finally {
                    this.ruleTreeLoading = false;
                }

            } else if (grantType === 'user') {
                if (!this._permCache.users) {
                    const res = await fetch('/api/users?per_page=100');
                    const data = await res.json();
                    if (data.users) {
                        this._permCache.users = data.users;
                    }
                }
                this.ruleTargetOptions = (this._permCache.users || []).map(u => ({
                    value: u.secure_code || u.id,
                    label: u.display_name || u.native_name || u.employee_id || u.id,
                }));
            }
        },

        _renderTree(container, nodes, depth) {
            const self = this;
            for (const node of nodes) {
                const hasChildren = node.children && node.children.length > 0;
                const isRoot = (depth === 0);
                const nodeEl = document.createElement('div');
                nodeEl.className = 'dc-perm-tree-node';

                // 行
                const row = document.createElement('div');
                row.className = 'dc-perm-tree-row';
                if (isRoot) row.classList.add('dc-perm-tree-root');
                row.style.paddingLeft = (8 + depth * 16) + 'px';

                // 展開/收合
                const toggle = document.createElement('span');
                toggle.className = 'dc-perm-tree-toggle';
                if (hasChildren) {
                    toggle.textContent = '\u25BC';  // 預設展開
                    toggle.style.cursor = 'pointer';
                }
                row.appendChild(toggle);

                // 標籤
                const label = document.createElement('span');
                label.className = 'dc-perm-tree-label';
                label.textContent = node.name;
                row.appendChild(label);

                nodeEl.appendChild(row);

                // 子節點容器
                let childContainer = null;
                if (hasChildren) {
                    childContainer = document.createElement('div');
                    childContainer.className = 'dc-perm-tree-children';
                    childContainer.style.display = 'block';
                    this._renderTree(childContainer, node.children, depth + 1);
                    nodeEl.appendChild(childContainer);
                }

                // 展開/收合事件
                if (hasChildren) {
                    toggle.addEventListener('click', function(e) {
                        e.stopPropagation();
                        var isOpen = childContainer.style.display !== 'none';
                        childContainer.style.display = isOpen ? 'none' : 'block';
                        toggle.textContent = isOpen ? '\u25B6' : '\u25BC';
                    });
                }

                // 選擇事件
                const sc = node.secure_code || node.id;
                const nodeName = node.full_path || node.name;
                row.addEventListener('click', function() {
                    // 清除同樹所有選中
                    var treeBox = container.closest('.dc-perm-tree-box');
                    if (treeBox) {
                        treeBox.querySelectorAll('.dc-perm-tree-row.selected')
                            .forEach(function(el) { el.classList.remove('selected'); });
                    }
                    row.classList.add('selected');
                    self.newRule.grant_target = sc;
                    self.newRule._selectedName = nodeName;
                });

                container.appendChild(nodeEl);
            }
        },

        async addRule(pgSc) {
            if (!this.newRule.grant_target) {
                this.showToast('請選擇目標', 'error');
                return;
            }

            // 組合顯示名稱
            let targetName = this.newRule._selectedName;
            if (!targetName) {
                const opt = this.ruleTargetOptions.find(o => o.value === this.newRule.grant_target);
                targetName = opt ? opt.label : this.newRule.grant_target;
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
                            grant_target_name: targetName,
                            include_children: this.newRule.include_children,
                        }),
                    }
                );
                const data = await res.json();
                if (data.success) {
                    this.showToast('規則已新增', 'success');
                    // 清除選取狀態，保持樹不動
                    this.newRule.grant_target = '';
                    this.newRule._selectedName = '';
                    this.newRule.include_children = false;
                    var treeContainer = document.getElementById('pp-rule-tree-' + pgSc);
                    if (treeContainer) {
                        var treeBox = treeContainer.closest('.dc-perm-tree-box');
                        if (treeBox) {
                            treeBox.querySelectorAll('.dc-perm-tree-row.selected')
                                .forEach(function(el) { el.classList.remove('selected'); });
                        }
                    }
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
