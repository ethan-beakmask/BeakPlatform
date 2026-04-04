/**
 * workstation_list.html -- Alpine.js Manager
 * 工作站與標籤管理
 */
function workstationManager() {
    return {
        // 工作站
        workstations: [],
        loading: true,

        // 標籤
        tags: [],
        loadingTags: true,

        // 工作站 Modal
        showModal: false,
        editingWs: null,
        saving: false,
        form: _emptyWsForm(),
        wsPermissions: [],
        permForm: { grant_type: 'department', grant_target: '', grant_target_name: '', include_children: false },

        // 標籤 Modal
        showTagModal: false,
        editingTag: null,
        savingTag: false,
        tagForm: _emptyTagForm(),

        init() {
            this.loadAll();
        },

        async loadAll() {
            this.loadWorkstations();
            this.loadTags();
        },

        // =====================================================================
        // 工作站 CRUD
        // =====================================================================

        async loadWorkstations() {
            this.loading = true;
            try {
                const res = await fetch('/api/form-workflow/workstations?all=1');
                const data = await res.json();
                if (data.success) this.workstations = data.data || [];
            } catch (e) { console.error('載入工作站失敗:', e); }
            finally { this.loading = false; }
        },

        openCreate() {
            this.editingWs = null;
            this.form = _emptyWsForm();
            this.wsPermissions = [];
            this.showModal = true;
        },

        async openEdit(ws) {
            this.editingWs = ws;
            const rules = ws.filter_rules || {};
            const uiCfg = ws.ui_config || {};
            this.form = {
                code: ws.code,
                name: ws.name,
                description: ws.description || '',
                icon: ws.icon || '',
                display_order: ws.display_order || 0,
                filter_categories: (rules.categories || []).join(', '),
                filter_tags: (rules.tags || []).join(', '),
                filter_source_type: (rules.source_types || [])[0] || '',
                match_mode: rules.match_mode || 'all',
                default_section: uiCfg.default_section || 'pending',
                auto_refresh_interval: uiCfg.auto_refresh_interval || 5,
            };

            // 載入權限
            try {
                const res = await fetch(`/api/form-workflow/workstations/${ws.secure_code}`);
                const data = await res.json();
                if (data.success) this.wsPermissions = data.data.permissions || [];
            } catch (e) { this.wsPermissions = []; }

            this.showModal = true;
        },

        _buildPayload() {
            const f = this.form;
            const filter_rules = { match_mode: f.match_mode };

            const cats = f.filter_categories.split(',').map(s => s.trim()).filter(Boolean);
            if (cats.length) filter_rules.categories = cats;

            const tags = f.filter_tags.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
            if (tags.length) filter_rules.tags = tags;

            if (f.filter_source_type) filter_rules.source_types = [f.filter_source_type];

            const ui_config = {
                default_section: f.default_section,
                auto_refresh_interval: f.auto_refresh_interval,
                sections: {
                    available: { visible: true, label: '可用表單' },
                    pending: { visible: true, label: '待處理' },
                    tracking: { visible: true, label: '追蹤中' },
                    history: { visible: true, label: '歷史' },
                }
            };

            return {
                code: f.code,
                name: f.name,
                description: f.description,
                icon: f.icon,
                display_order: f.display_order,
                filter_rules,
                ui_config,
            };
        },

        async saveWorkstation() {
            if (!this.form.code || !this.form.name) return alert('代碼和名稱為必填');
            this.saving = true;
            try {
                const payload = this._buildPayload();
                const url = this.editingWs
                    ? `/api/form-workflow/workstations/${this.editingWs.secure_code}`
                    : '/api/form-workflow/workstations';
                const method = this.editingWs ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    this.showModal = false;
                    this.loadWorkstations();
                } else {
                    alert(data.message || '儲存失敗');
                }
            } catch (e) { alert('儲存失敗: ' + e.message); }
            finally { this.saving = false; }
        },

        async toggleActive(ws) {
            try {
                const res = await fetch(`/api/form-workflow/workstations/${ws.secure_code}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !ws.is_active })
                });
                const data = await res.json();
                if (data.success) this.loadWorkstations();
            } catch (e) { alert('操作失敗'); }
        },

        async deleteWs(ws) {
            if (!confirm(`確定刪除工作站「${ws.name}」？`)) return;
            try {
                const res = await fetch(`/api/form-workflow/workstations/${ws.secure_code}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) this.loadWorkstations();
                else alert(data.message || '刪除失敗');
            } catch (e) { alert('刪除失敗'); }
        },

        // 權限
        async addPermission() {
            const p = this.permForm;
            if (!p.grant_target) return alert('目標為必填');
            try {
                const res = await fetch(`/api/form-workflow/workstations/${this.editingWs.secure_code}/permissions`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(p)
                });
                const data = await res.json();
                if (data.success) {
                    this.wsPermissions.push(data.data);
                    this.permForm = { grant_type: 'department', grant_target: '', grant_target_name: '', include_children: false };
                } else {
                    alert(data.message || '新增失敗');
                }
            } catch (e) { alert('新增失敗'); }
        },

        async removePermission(sc) {
            try {
                const res = await fetch(`/api/form-workflow/workstations/permissions/${sc}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    this.wsPermissions = this.wsPermissions.filter(p => p.secure_code !== sc);
                }
            } catch (e) { alert('刪除失敗'); }
        },

        // =====================================================================
        // 標籤 CRUD
        // =====================================================================

        async loadTags() {
            this.loadingTags = true;
            try {
                const res = await fetch('/api/form-workflow/tags');
                const data = await res.json();
                if (data.success) this.tags = data.data || [];
            } catch (e) { console.error('載入標籤失敗:', e); }
            finally { this.loadingTags = false; }
        },

        openCreateTag() {
            this.editingTag = null;
            this.tagForm = _emptyTagForm();
            this.showTagModal = true;
        },

        openEditTag(tag) {
            this.editingTag = tag;
            this.tagForm = {
                code: tag.code,
                name: tag.name,
                description: tag.description || '',
                color: tag.color || '#3b82f6',
                display_order: tag.display_order || 0,
            };
            this.showTagModal = true;
        },

        async saveTag() {
            if (!this.tagForm.code || !this.tagForm.name) return alert('代碼和名稱為必填');
            this.savingTag = true;
            try {
                const url = this.editingTag
                    ? `/api/form-workflow/tags/${this.editingTag.secure_code}`
                    : '/api/form-workflow/tags';
                const method = this.editingTag ? 'PUT' : 'POST';

                const res = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.tagForm)
                });
                const data = await res.json();
                if (data.success) {
                    this.showTagModal = false;
                    this.loadTags();
                } else {
                    alert(data.message || '儲存失敗');
                }
            } catch (e) { alert('儲存失敗: ' + e.message); }
            finally { this.savingTag = false; }
        },

        async deleteTag(tag) {
            if (!confirm(`確定刪除標籤「${tag.name}」？`)) return;
            try {
                const res = await fetch(`/api/form-workflow/tags/${tag.secure_code}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) this.loadTags();
                else alert(data.message || '刪除失敗');
            } catch (e) { alert('刪除失敗'); }
        },
    };
}

function _emptyWsForm() {
    return {
        code: '', name: '', description: '', icon: '', display_order: 0,
        filter_categories: '', filter_tags: '', filter_source_type: '', match_mode: 'all',
        default_section: 'pending', auto_refresh_interval: 5,
    };
}

function _emptyTagForm() {
    return { code: '', name: '', description: '', color: '#3b82f6', display_order: 0 };
}
