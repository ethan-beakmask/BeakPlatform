/* global __, BkCaps */
function wksPermsManager(subSystemSc) {
    const BP = window.__BP || '';
    const PERM_RE = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/;
    const ROLE_RE = /^[A-Z][A-Z0-9_]{0,31}$/;

    return {
        subSystemSc: subSystemSc || '',
        loading: true,
        saving: false,
        error: '',
        permissions: [],
        roles: [],
        levels: [],
        users: [],
        templates: [],
        pageRows: [],
        matchModes: ['any', 'all'],
        permissionForm: { code: '', description: '', risk_level: 'normal' },
        roleForm: { code: '', name: '', description: '', display_order: 0 },
        overrideForms: {},
        toast: { show: false, message: '' },

        async init() {
            await this.loadAll();
        },

        async loadAll() {
            this.loading = true;
            this.error = '';
            try {
                await Promise.all([this.loadModel(), this.loadTemplates(), this.loadSiteMap()]);
                this.ensureOverrideForms();
            } catch (err) {
                this.error = err.message || __('載入權限矩陣失敗');
            } finally {
                this.loading = false;
            }
        },

        async loadModel() {
            const data = await this.fetchJson(this.portalUrl('/permission-model'));
            const model = data.data || {};
            this.permissions = model.permissions || [];
            this.roles = model.roles || [];
            this.levels = model.levels || [];
            // overrideForms 必須先於 users 就緒：模板的 x-model 直接取
            // overrideForms[user.secure_code].code，晚一步會在首次渲染丟 Alpine 錯誤
            this.overrideForms = this.buildOverrideForms(model.users || []);
            this.users = model.users || [];
        },

        buildOverrideForms(users) {
            const firstCode = this.permissions.length ? this.permissions[0].code : '';
            const forms = { ...this.overrideForms };
            users.forEach((user) => {
                if (!forms[user.secure_code]) {
                    forms[user.secure_code] = { code: firstCode, effect: 'allow' };
                } else if (!forms[user.secure_code].code) {
                    forms[user.secure_code].code = firstCode;
                }
            });
            return forms;
        },

        async loadTemplates() {
            const data = await this.fetchJson(this.portalUrl('/permission-templates'));
            this.templates = data.data || [];
        },

        async loadSiteMap() {
            const data = await this.fetchJson(`${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/site-map`);
            this.pageRows = this.flattenPages(data.data || []);
        },

        flattenPages(nodes, depth = 0) {
            const rows = [];
            (nodes || []).forEach((node) => {
                if (node.node_type === 'page') {
                    const row = Object.assign({}, node, { depth });
                    this.syncPageState(row);
                    rows.push(row);
                }
                rows.push(...this.flattenPages(node.children || [], depth + 1));
            });
            return rows;
        },

        syncPageState(row) {
            const readRule = this.readRule(row);
            row.perm_codes = readRule ? [...(readRule.required_permissions || [])] : [];
            row.perm_match_mode = readRule && this.matchModes.includes(readRule.match_mode) ? readRule.match_mode : 'any';
            row.perm_original_status = this.accessStatus(row);
        },

        portalUrl(path) {
            return `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/portal${path}`;
        },

        async fetchJson(url, options) {
            const res = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
            let data = {};
            try {
                data = await res.json();
            } catch (err) {
                throw new Error(__('伺服器回應格式錯誤'));
            }
            if (!res.ok || !data.success) {
                throw new Error(data.error || data.message || __('操作失敗'));
            }
            return data;
        },

        requestOptions(method, payload) {
            return {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            };
        },

        canManage() {
            return typeof BkCaps === 'undefined' || BkCaps.can('nocode_builder.manage');
        },

        ensureCanManage() {
            if (this.canManage()) return true;
            this.showToast(__('沒有權限執行此操作'));
            return false;
        },

        async createPermission() {
            if (!this.ensureCanManage()) return;
            const code = String(this.permissionForm.code || '').trim();
            if (!PERM_RE.test(code)) {
                this.showToast(__('權限碼格式不正確'));
                return;
            }
            this.saving = true;
            try {
                const data = await this.fetchJson(this.portalUrl('/permissions'), this.requestOptions('POST', {
                    code,
                    description: String(this.permissionForm.description || '').trim(),
                    risk_level: this.permissionForm.risk_level || 'normal',
                }));
                this.permissionForm = { code: '', description: '', risk_level: 'normal' };
                await this.loadModel();
                this.showToast(data.message || __('權限碼已新增'));
            } catch (err) {
                this.showToast(err.message || __('新增權限碼失敗'));
            } finally {
                this.saving = false;
            }
        },

        async deletePermission(perm) {
            if (!this.ensureCanManage()) return;
            if (!confirm(__('確定刪除此權限碼？'))) return;
            this.saving = true;
            try {
                const data = await this.fetchJson(this.portalUrl(`/permissions/${encodeURIComponent(perm.code)}`), { method: 'DELETE', credentials: 'same-origin' });
                await this.loadAll();
                this.showToast(data.message || __('權限碼已刪除'));
            } catch (err) {
                this.showToast(err.message || __('刪除權限碼失敗'));
            } finally {
                this.saving = false;
            }
        },

        readRule(row) {
            const access = row.access_matrix || {};
            const rule = access.read || access;
            if (rule && Array.isArray(rule.required_permissions)) return rule;
            return null;
        },

        legacyRule(row) {
            const access = row.access_matrix || {};
            const rule = access.read || access;
            return !!(rule && (Object.prototype.hasOwnProperty.call(rule, 'groups') || Object.prototype.hasOwnProperty.call(rule, 'min_level')));
        },

        accessStatus(row) {
            if (!row.access_matrix) return 'open';
            if (this.readRule(row)) return 'permission';
            if (this.legacyRule(row)) return 'legacy';
            return 'legacy';
        },

        accessStatusLabel(row) {
            const status = this.accessStatus(row);
            if (status === 'open') return __('未設限');
            if (status === 'permission') return __('權限碼制');
            return __('舊制（群組＋階級）');
        },

        pageHasPermission(row, code) {
            return (row.perm_codes || []).includes(code);
        },

        async togglePagePermission(row, code, checked) {
            if (!this.ensureCanManage()) {
                this.syncPageState(row);
                return;
            }
            const next = new Set(row.perm_codes || []);
            if (checked) next.add(code);
            else next.delete(code);
            await this.savePageRule(row, [...next]);
        },

        async updatePageMatchMode(row) {
            if (!this.ensureCanManage()) {
                this.syncPageState(row);
                return;
            }
            await this.savePageRule(row, row.perm_codes || []);
        },

        async savePageRule(row, codes) {
            if (row.perm_original_status === 'legacy') {
                if (!confirm(__('將改用權限碼制，原本的群組與階級設定會被取代'))) {
                    this.syncPageState(row);
                    return;
                }
            }
            if (!codes.length && !confirm(__('此頁將對所有訪客開放'))) {
                this.syncPageState(row);
                return;
            }

            const matrix = codes.length ? {
                read: {
                    required_permissions: codes,
                    match_mode: this.matchModes.includes(row.perm_match_mode) ? row.perm_match_mode : 'any',
                },
            } : null;
            this.saving = true;
            try {
                const data = await this.fetchJson(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/site-map/access-matrix/batch`,
                    this.requestOptions('POST', { node_secure_codes: [row.secure_code], access_matrix: matrix })
                );
                row.access_matrix = matrix;
                this.syncPageState(row);
                this.showToast(data.message || __('網頁權限已更新'));
            } catch (err) {
                this.showToast(err.message || __('網頁權限更新失敗'));
                await this.loadSiteMap();
            } finally {
                this.saving = false;
            }
        },

        sortedLevels() {
            return [...(this.levels || [])].sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
        },

        sortedRoles() {
            return [...(this.roles || [])].sort((a, b) => {
                const order = Number(a.display_order || 0) - Number(b.display_order || 0);
                return order || String(a.code || '').localeCompare(String(b.code || ''));
            });
        },

        hasPermission(item, code) {
            return (item.permissions || []).includes(code);
        },

        async toggleLevelPermission(level, code, checked) {
            const codes = this.nextCodes(level.permissions || [], code, checked);
            await this.overwritePermissionSet(level, codes, this.portalUrl(`/levels/${encodeURIComponent(level.code)}/permissions`), __('等級權限已更新'));
        },

        async toggleRolePermission(role, code, checked) {
            const codes = this.nextCodes(role.permissions || [], code, checked);
            await this.overwritePermissionSet(role, codes, this.portalUrl(`/admin-roles/${encodeURIComponent(role.code)}/permissions`), __('角色權限已更新'));
        },

        nextCodes(source, code, checked) {
            const set = new Set(source || []);
            if (checked) set.add(code);
            else set.delete(code);
            return [...set];
        },

        async overwritePermissionSet(item, codes, url, successMessage) {
            if (!this.ensureCanManage()) return;
            const previous = [...(item.permissions || [])];
            item.permissions = codes;
            this.saving = true;
            try {
                const data = await this.fetchJson(url, this.requestOptions('PUT', { codes }));
                this.showToast(data.message || successMessage);
            } catch (err) {
                item.permissions = previous;
                this.showToast(err.message || __('權限更新失敗'));
            } finally {
                this.saving = false;
            }
        },

        async createRole() {
            if (!this.ensureCanManage()) return;
            const code = String(this.roleForm.code || '').trim();
            const name = String(this.roleForm.name || '').trim();
            if (!ROLE_RE.test(code)) {
                this.showToast(__('角色 code 格式不正確'));
                return;
            }
            if (!name) {
                this.showToast(__('請輸入角色名稱'));
                return;
            }
            this.saving = true;
            try {
                const data = await this.fetchJson(this.portalUrl('/admin-roles'), this.requestOptions('POST', {
                    code,
                    name,
                    description: String(this.roleForm.description || '').trim(),
                    display_order: Number(this.roleForm.display_order || 0),
                }));
                this.roleForm = { code: '', name: '', description: '', display_order: 0 };
                await this.loadModel();
                this.showToast(data.message || __('角色已新增'));
            } catch (err) {
                this.showToast(err.message || __('新增角色失敗'));
            } finally {
                this.saving = false;
            }
        },

        async deleteRole(role) {
            if (!this.ensureCanManage()) return;
            if (!confirm(__('確定刪除此角色？'))) return;
            this.saving = true;
            try {
                const data = await this.fetchJson(this.portalUrl(`/admin-roles/${encodeURIComponent(role.code)}`), { method: 'DELETE', credentials: 'same-origin' });
                await this.loadModel();
                this.showToast(data.message || __('角色已刪除'));
            } catch (err) {
                this.showToast(err.message || __('刪除角色失敗'));
            } finally {
                this.saving = false;
            }
        },

        userHasRole(user, code) {
            return (user.roles || []).includes(code);
        },

        async toggleUserRole(user, code, checked) {
            if (!this.ensureCanManage()) return;
            const previous = [...(user.roles || [])];
            const role_codes = this.nextCodes(previous, code, checked);
            user.roles = role_codes;
            this.saving = true;
            try {
                const data = await this.fetchJson(
                    this.portalUrl(`/users/${encodeURIComponent(user.secure_code)}/roles`),
                    this.requestOptions('PUT', { role_codes })
                );
                this.showToast(data.message || __('帳號角色已更新'));
            } catch (err) {
                user.roles = previous;
                this.showToast(err.message || __('帳號角色更新失敗'));
            } finally {
                this.saving = false;
            }
        },

        ensureOverrideForms() {
            this.overrideForms = this.buildOverrideForms(this.users || []);
        },

        async saveOverride(user) {
            if (!this.ensureCanManage()) return;
            const form = this.overrideForms[user.secure_code] || {};
            if (!form.code) {
                this.showToast(__('請選擇權限碼'));
                return;
            }
            await this.putOverride(user, form.code, form.effect || 'allow');
        },

        async removeOverride(user, override) {
            if (!this.ensureCanManage()) return;
            await this.putOverride(user, override.code, null);
        },

        async putOverride(user, code, effect) {
            this.saving = true;
            try {
                const data = await this.fetchJson(
                    this.portalUrl(`/users/${encodeURIComponent(user.secure_code)}/permission-override`),
                    this.requestOptions('PUT', { code, effect, reason: 'workspace_permission_matrix' })
                );
                await this.loadModel();
                this.ensureOverrideForms();
                this.showToast(data.message || __('個人覆寫已更新'));
            } catch (err) {
                this.showToast(err.message || __('個人覆寫更新失敗'));
            } finally {
                this.saving = false;
            }
        },

        async applyTemplate(tpl) {
            if (!this.ensureCanManage()) return;
            if (!confirm(__('確定套用此權限模板？'))) return;
            this.saving = true;
            try {
                const data = await this.fetchJson(this.portalUrl(`/permission-templates/${encodeURIComponent(tpl.code)}/apply`), { method: 'POST', credentials: 'same-origin' });
                await this.loadModel();
                this.ensureOverrideForms();
                this.showToast(data.message || __('權限模板已套用'));
            } catch (err) {
                this.showToast(err.message || __('套用權限模板失敗'));
            } finally {
                this.saving = false;
            }
        },

        levelName(code) {
            const level = (this.levels || []).find((item) => item.code === code);
            return level ? `${level.name} (${level.code})` : (code || '-');
        },

        riskLabel(level) {
            const labels = {
                low: __('低'),
                normal: __('一般'),
                high: __('高'),
                critical: __('重大'),
            };
            return labels[level] || (level || '-');
        },

        truthy(value) {
            return value === true || value === 1 || value === '1';
        },

        showToast(message) {
            this.toast = { show: true, message };
            setTimeout(() => { this.toast.show = false; }, 2600);
        },
    };
}
