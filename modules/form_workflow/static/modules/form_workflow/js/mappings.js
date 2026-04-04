/* mappings.js — 表單流程配對列表頁 */

function mappingsManager() {
    return {
        mappings: [],
        archivedMappings: [],
        unmappedForms: [],
        workflows: [],
        numberingRules: [],
        loading: true,

        showCreateModal: false,
        newMapping: { form_template_secure_code: '', workflow_template_secure_code: '' },
        saving: false,

        showVersionsModal: false,
        viewingMapping: null,
        publishedVersions: [],

        showHelpModal: false,
        showDeleteModal: false,
        deletingMapping: null,
        showArchivedList: false,

        // 權限 Modal
        showPermModal: false,
        permMapping: null,
        permRules: [],
        permTargetOptions: [],
        permTreeLoading: false,
        permSaving: false,
        newPerm: { grant_type: 'department', grant_target: '', include_children: false, _selectedName: '' },
        _permCache: {
            departments: null,
            groups: null,
            users: null,
        },

        toast: { show: false, message: '', type: 'success' },

        async init() {
            // numberingRules 必須先載入，否則 select 的 option 不存在導致綁定失敗
            await this.loadNumberingRules();
            await this.loadMappings();
            await Promise.all([
                this.loadArchivedMappings(),
                this.loadUnmappedForms(),
                this.loadWorkflows(),
            ]);
        },

        async loadMappings() {
            this.loading = true;
            try {
                const res = await fetch('/api/mappings/');
                const data = await res.json();
                if (data.success) {
                    const defaultRule = this.numberingRules.find(r => r.is_form_default);
                    const defaultCode = defaultRule ? defaultRule.secure_code : '';
                    this.mappings = (data.data || []).map(m => ({
                        ...m,
                        numbering_rule_secure_code: m.numbering_rule_secure_code || defaultCode,
                        _perm_count: 0,
                    }));
                    // 非同步載入每個配對的權限數量
                    this._loadPermCounts();
                }
            } catch (e) {
                console.error('載入配對失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        async loadArchivedMappings() {
            try {
                const res = await fetch('/api/mappings/?is_archived=true');
                const data = await res.json();
                if (data.success) {
                    this.archivedMappings = data.data || [];
                }
            } catch (e) {
                console.error('載入封存清單失敗:', e);
            }
        },

        async loadUnmappedForms() {
            try {
                const res = await fetch('/api/mappings/unmapped-forms');
                const data = await res.json();
                if (data.success) {
                    this.unmappedForms = data.data || [];
                }
            } catch (e) {
                console.error('載入未配對表單失敗:', e);
            }
        },

        async loadWorkflows() {
            try {
                const res = await fetch('/api/mappings/workflows-for-mapping');
                const data = await res.json();
                if (data.success) {
                    this.workflows = data.data || [];
                }
            } catch (e) {
                console.error('載入流程失敗:', e);
            }
        },

        async openCreateModal() {
            this.newMapping = { form_template_secure_code: '', workflow_template_secure_code: '' };
            this.showCreateModal = true;
            await Promise.all([this.loadUnmappedForms(), this.loadWorkflows()]);
        },

        closeCreateModal() {
            this.showCreateModal = false;
        },

        async createMapping() {
            if (this.saving) return;
            this.saving = true;

            try {
                const res = await fetch('/api/mappings/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.newMapping)
                });
                const data = await res.json();

                if (data.success) {
                    this.closeCreateModal();
                    this.showToast('配對建立成功');
                    await this.loadMappings();
                    await this.loadUnmappedForms();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            } finally {
                this.saving = false;
            }
        },

        async publishMapping(m) {
            if (!confirm(`確定要新發行「${m.form_template_name}」與「${m.workflow_template_name}」的配對嗎？`)) return;

            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/publish`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();

                if (data.success) {
                    this.showToast(data.message || '發行成功');
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '發行失敗', 'error');
                }
            } catch (e) {
                this.showToast('發行失敗: ' + e.message, 'error');
            }
        },

        async viewPublished(m) {
            this.viewingMapping = m;
            this.publishedVersions = [];
            this.showVersionsModal = true;

            try {
                const res = await fetch(`/api/mappings/published?mapping_secure_code=${m.secure_code}`);
                const data = await res.json();
                if (data.success) {
                    this.publishedVersions = data.data || [];
                    // 載入每個已啟用 SQL sync 版本的同步狀態
                    for (const v of this.publishedVersions) {
                        if (v.sql_sync_enabled) {
                            this.loadSyncStatus(v);
                        }
                    }
                }
            } catch (e) {
                console.error('載入版本失敗:', e);
            }
        },

        async suspendVersion(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/suspend`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已暫停');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async reopenVersion(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/reopen`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已重新開放');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async archiveVersion(v) {
            if (!confirm('確定要封存此版本嗎？封存後無法重新開放。')) return;

            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/archive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已封存');
                    await this.viewPublished(this.viewingMapping);
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async archiveMapping(m) {
            if (!confirm(`確定要封存「${m.form_template_name}」與「${m.workflow_template_name}」的配對嗎？`)) return;

            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/archive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('配對已封存');
                    await this.loadMappings();
                    await this.loadArchivedMappings();
                } else {
                    this.showToast(data.error || '封存失敗', 'error');
                }
            } catch (e) {
                this.showToast('封存失敗: ' + e.message, 'error');
            }
        },

        async unarchiveMapping(a) {
            try {
                const res = await fetch(`/api/mappings/${a.secure_code}/unarchive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('配對已恢復');
                    await this.loadMappings();
                    await this.loadArchivedMappings();
                } else {
                    this.showToast(data.error || '恢復失敗', 'error');
                }
            } catch (e) {
                this.showToast('恢復失敗: ' + e.message, 'error');
            }
        },

        async deleteVersion(v) {
            if (!confirm(`確定要刪除版本 v${v.publish_version} 嗎？此操作無法還原。`)) return;

            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '版本已刪除');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        confirmDelete(m) {
            this.deletingMapping = m;
            this.showDeleteModal = true;
        },

        confirmDeleteArchived(a) {
            this.deletingMapping = a;
            this.showDeleteModal = true;
        },

        async deleteMapping() {
            if (!this.deletingMapping) return;

            try {
                const res = await fetch(`/api/mappings/${this.deletingMapping.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();

                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('配對已解除');
                    await this.loadMappings();
                    await this.loadArchivedMappings();
                    await this.loadUnmappedForms();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        async toggleSqlSync(v, enabled) {
            // 只允許啟用，不允許關閉（後端也有擋）
            if (!enabled) {
                v.sql_sync_enabled = true; // revert checkbox
                return;
            }
            if (!confirm('啟用 SQL 同步後無法關閉，確定啟用？')) {
                v.sql_sync_enabled = false; // revert checkbox
                return;
            }
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/sql-sync`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sql_sync_enabled: true })
                });
                const data = await res.json();
                if (data.success) {
                    v.sql_sync_enabled = true;
                    this.showToast(data.message || 'SQL 同步已啟用');
                    this.loadSyncStatus(v);
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                    v.sql_sync_enabled = !enabled; // revert
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
                v.sql_sync_enabled = !enabled;
            }
        },

        async loadSyncStatus(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/sql-sync/status`);
                const data = await res.json();
                if (data.success && data.data.table) {
                    v._syncInfo = `${data.data.table.row_count || 0} 筆`;
                    v._tableName = data.data.table.table_name || '';
                }
            } catch (e) {
                // silent
            }
        },

        async loadNumberingRules() {
            try {
                const res = await fetch('/api/mappings/numbering-rules');
                const data = await res.json();
                if (data.success) {
                    this.numberingRules = data.data || [];
                }
            } catch (e) {
                console.error('載入編號規則失敗:', e);
            }
        },

        getNumberingPreview(m) {
            const rule = this.numberingRules.find(r => r.secure_code === m.numbering_rule_secure_code);
            return rule ? rule.preview : '';
        },

        async updateNumberingRule(m, ruleSecureCode) {
            try {
                const res = await fetch(`/api/mappings/${m.secure_code}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ numbering_rule_secure_code: ruleSecureCode || null })
                });
                const data = await res.json();
                if (data.success) {
                    m.numbering_rule_secure_code = ruleSecureCode || null;
                    this.showToast('編號規則已更新');
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                    await this.loadMappings();
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
            }
        },

        // =====================================================================
        // 權限管理
        // =====================================================================

        async _loadPermCounts() {
            for (const m of this.mappings) {
                try {
                    const res = await fetch(`/api/mapping-permissions/${m.secure_code}`);
                    const data = await res.json();
                    if (data.success) {
                        m._perm_count = (data.data || []).length;
                    }
                } catch (e) { /* ignore */ }
            }
        },

        async openPermModal(m) {
            this.permMapping = m;
            this.permRules = [];
            this.newPerm = { grant_type: 'department', grant_target: '', include_children: false, _selectedName: '' };
            this.showPermModal = true;
            await this._loadPermRules(m.secure_code);
            await this._loadPermTargets('department');
        },

        async _loadPermRules(mappingSc) {
            try {
                const res = await fetch(`/api/mapping-permissions/${mappingSc}`);
                const data = await res.json();
                if (data.success) {
                    this.permRules = data.data || [];
                    // 同步更新清單中的計數
                    const m = this.mappings.find(x => x.secure_code === mappingSc);
                    if (m) m._perm_count = this.permRules.length;
                }
            } catch (e) {
                console.error('載入權限規則失敗:', e);
            }
        },

        async onPermTypeChange() {
            this.newPerm.grant_target = '';
            this.newPerm.include_children = false;
            this.newPerm._selectedName = '';
            await this._loadPermTargets(this.newPerm.grant_type);
        },

        async _loadPermTargets(grantType) {
            this.permTargetOptions = [];
            const container = document.getElementById('perm-tree-container');

            if (grantType === 'department' || grantType === 'group') {
                this.permTreeLoading = true;
                if (container) container.innerHTML = '';
                try {
                    let treeData = null;
                    if (grantType === 'department') {
                        if (!this._permCache.departments) {
                            const res = await fetch('/api/units/departments?tree=true');
                            const data = await res.json();
                            this._permCache.departments = data.units || [];
                        }
                        treeData = this._permCache.departments;
                    } else {
                        if (!this._permCache.groups) {
                            const res = await fetch('/api/units/groups?tree=true');
                            const data = await res.json();
                            this._permCache.groups = data.units || [];
                        }
                        treeData = this._permCache.groups;
                    }
                    if (container) {
                        this._renderTree(container, treeData, 0);
                    }
                } catch (e) {
                    console.error('載入樹狀資料失敗:', e);
                } finally {
                    this.permTreeLoading = false;
                }
            } else if (grantType === 'user') {
                if (!this._permCache.users) {
                    const res = await fetch('/api/users?per_page=100');
                    const data = await res.json();
                    if (data.users) {
                        this._permCache.users = data.users;
                    }
                }
                this.permTargetOptions = (this._permCache.users || []).map(u => ({
                    value: u.secure_code || u.id,
                    label: (u.display_name || u.native_name || u.employee_id || u.id),
                }));
            }
        },

        _renderTree(container, nodes, depth) {
            const self = this;
            for (const node of nodes) {
                const hasChildren = node.children && node.children.length > 0;
                const nodeEl = document.createElement('div');
                nodeEl.className = 'fw-perm-tree-node';

                // 行
                const row = document.createElement('div');
                row.className = 'fw-perm-tree-row';
                row.style.paddingLeft = (8 + depth * 16) + 'px';

                // 展開/收合
                const toggle = document.createElement('span');
                toggle.className = 'fw-perm-tree-toggle';
                if (hasChildren) {
                    toggle.textContent = '\u25B6';  // ▶
                    toggle.style.cursor = 'pointer';
                }
                row.appendChild(toggle);

                // 標籤
                const label = document.createElement('span');
                label.className = 'fw-perm-tree-label';
                label.textContent = node.name;
                row.appendChild(label);

                nodeEl.appendChild(row);

                // 子節點容器
                let childContainer = null;
                if (hasChildren) {
                    childContainer = document.createElement('div');
                    childContainer.className = 'fw-perm-tree-children';
                    childContainer.style.display = 'none';
                    this._renderTree(childContainer, node.children, depth + 1);
                    nodeEl.appendChild(childContainer);
                }

                // 展開/收合事件
                if (hasChildren) {
                    toggle.addEventListener('click', function(e) {
                        e.stopPropagation();
                        const isOpen = childContainer.style.display !== 'none';
                        childContainer.style.display = isOpen ? 'none' : 'block';
                        toggle.textContent = isOpen ? '\u25B6' : '\u25BC';  // ▶ / ▼
                    });
                }

                // 選擇事件
                const sc = node.secure_code || node.id;
                const nodeName = node.full_path || node.name;
                row.addEventListener('click', function() {
                    // 清除所有選中
                    container.closest('.fw-perm-tree-box').querySelectorAll('.fw-perm-tree-row.selected').forEach(el => el.classList.remove('selected'));
                    row.classList.add('selected');
                    self.newPerm.grant_target = sc;
                    self.newPerm._selectedName = nodeName;
                });

                container.appendChild(nodeEl);
            }
        },

        async addPermRule() {
            if (!this.newPerm.grant_target || !this.permMapping) return;
            this.permSaving = true;

            // 找到目標名稱（樹狀用 _selectedName，下拉用 options 查找）
            let targetName = this.newPerm._selectedName;
            if (!targetName) {
                const opt = this.permTargetOptions.find(o => o.value === this.newPerm.grant_target);
                targetName = opt ? opt.label : this.newPerm.grant_target;
            }

            try {
                const res = await fetch(`/api/mapping-permissions/${this.permMapping.secure_code}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        grant_type: this.newPerm.grant_type,
                        grant_target: this.newPerm.grant_target,
                        grant_target_name: targetName,
                        include_children: this.newPerm.include_children,
                    })
                });
                const data = await res.json();
                if (data.success) {
                    await this._loadPermRules(this.permMapping.secure_code);
                    this.newPerm.grant_target = '';
                    this.newPerm._selectedName = '';
                    // 清除樹狀選中
                    const treeBox = document.querySelector('.fw-perm-tree-box');
                    if (treeBox) treeBox.querySelectorAll('.fw-perm-tree-row.selected').forEach(el => el.classList.remove('selected'));
                    this.showToast('權限規則已新增');
                } else {
                    this.showToast(data.message || '新增失敗', 'error');
                }
            } catch (e) {
                this.showToast('新增失敗: ' + e.message, 'error');
            } finally {
                this.permSaving = false;
            }
        },

        async deletePermRule(secureCcode) {
            if (!confirm('確定要刪除此權限規則？')) return;
            try {
                const res = await fetch(`/api/mapping-permissions/rule/${secureCcode}`, {
                    method: 'DELETE',
                });
                const data = await res.json();
                if (data.success) {
                    await this._loadPermRules(this.permMapping.secure_code);
                    this.showToast('權限規則已刪除');
                } else {
                    this.showToast(data.message || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
        },

        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
