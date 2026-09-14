/**
 * Access Center - Roles tab
 */
function acRolesTab() {
    const config = window.__AC_CONFIG || {};

    return {
        isSystemAdmin: !!config.isSystemAdmin,
        organizations: config.organizations || [],
        selectedOrgCode: config.isSystemAdmin ? '' : (config.userOrgSecureCode || ''),
        orgLabel: config.userOrgLabel || config.userOrgSecureCode || '',

        roles: [],
        permissions: [],
        selectedPermissionCodes: [],
        roleUsers: {},
        expandedRoleCode: '',
        loadingRoles: false,
        loadingPermissions: false,
        loadingUsersCode: '',
        savingRole: false,
        modalOpen: false,
        editingRole: null,
        alert: { show: false, message: '', type: 'info' },
        codePlaceholder: '',
        codeMessage: '',
        codeValid: true,
        codeTimer: null,

        roleTypeOptions: [
            { value: 'ROLE', label: __('角色') },
            { value: 'POSITION', label: __('職務') }
        ],
        scopeTypeOptions: [
            { value: 'GLOBAL', label: __('全企業') },
            { value: 'DEPARTMENT', label: __('部門') },
            { value: 'GROUP', label: __('社群') },
            { value: 'EXTERNAL', label: __('外部') }
        ],
        exclusiveGroupOptions: [
            { value: '', label: __('無'), help: __('此角色不參與互斥檢查') },
            { value: 'IDENTITY_TYPE', label: __('身分類型互斥(全域)'), help: __('同一用戶全企業只能持有一個身分類型角色') },
            { value: 'DEPT_POSITION', label: __('部門職務互斥(同單位)'), help: __('同一用戶在同一部門只能持有一個部門職務') },
            { value: 'GROUP_POSITION', label: __('社群職務互斥(同單位)'), help: __('同一用戶在同一社群只能持有一個社群職務') }
        ],

        async init() {
            if (!this.isSystemAdmin) {
                await this.loadRoles();
            }
        },

        get canLoadRoles() {
            return !this.isSystemAdmin || !!this.selectedOrgCode;
        },

        get canSave() {
            if (!this.form.name || this.savingRole) return false;
            if (!this.editingRole && this.form.code && !this.codeValid) return false;
            return true;
        },

        get isLockedRole() {
            return !!(this.editingRole && this.editingRole.is_system_role);
        },

        get exclusiveGroupHelp() {
            const selected = this.exclusiveGroupOptions.find(option => option.value === this.form.exclusive_group);
            return selected ? selected.help : '';
        },

        get tableRows() {
            const rows = [];
            for (const role of this.roles) {
                rows.push({ key: role.secure_code + ':role', kind: 'role', role });
                if (this.expandedRoleCode === role.secure_code) {
                    rows.push({ key: role.secure_code + ':users', kind: 'users', role });
                }
            }
            return rows;
        },

        get permissionGroups() {
            const groups = {};
            for (const permission of this.permissions) {
                const level = permission.permission_level || __('未分類');
                if (!groups[level]) groups[level] = [];
                groups[level].push(permission);
            }
            return Object.keys(groups).sort().map(level => ({
                level,
                permissions: groups[level]
            }));
        },

        form: {
            name: '',
            code: '',
            role_type: 'ROLE',
            scope_type: 'GLOBAL',
            is_manager: false,
            description: '',
            sort_order: 0,
            is_active: true,
            exclusive_group: ''
        },

        _orgQueryParam() {
            if (this.isSystemAdmin && this.selectedOrgCode) {
                return '?org_code=' + encodeURIComponent(this.selectedOrgCode);
            }
            return '';
        },

        async onOrgChange() {
            this.roles = [];
            this.expandedRoleCode = '';
            this.roleUsers = {};
            if (this.selectedOrgCode) {
                await this.loadRoles();
            }
        },

        async loadRoles() {
            if (!this.canLoadRoles) return;
            this.loadingRoles = true;
            try {
                const data = await window.acFetch('/api/roles/' + this._orgQueryParam());
                this.roles = data.roles || [];
            } catch (e) {
                this.showAlert(e.message || __('載入角色失敗'), 'error');
            } finally {
                this.loadingRoles = false;
            }
        },

        async loadPermissions() {
            if (this.permissions.length) return;
            this.loadingPermissions = true;
            try {
                const data = await window.acFetch('/api/permissions/all' + this._orgQueryParam());
                this.permissions = data.permissions || [];
            } catch (e) {
                this.showAlert(e.message || __('載入權限失敗'), 'error');
            } finally {
                this.loadingPermissions = false;
            }
        },

        async loadRolePermissions(role) {
            this.selectedPermissionCodes = [];
            if (!role || !role.secure_code) return;
            try {
                const data = await window.acFetch('/api/permissions/role-view/' + encodeURIComponent(role.secure_code) + this._orgQueryParam());
                this.selectedPermissionCodes = (data.rbac_permissions || []).map(permission => permission.permission_secure_code);
            } catch (e) {
                this.showAlert(e.message || __('載入角色權限失敗'), 'error');
            }
        },

        async toggleUsers(role) {
            if (this.expandedRoleCode === role.secure_code) {
                this.expandedRoleCode = '';
                return;
            }
            this.expandedRoleCode = role.secure_code;
            if (this.roleUsers[role.secure_code]) return;

            this.loadingUsersCode = role.secure_code;
            try {
                const data = await window.acFetch('/api/roles/' + encodeURIComponent(role.secure_code) + '/users' + this._orgQueryParam());
                this.roleUsers[role.secure_code] = data.users || [];
            } catch (e) {
                this.showAlert(e.message || __('載入持有人失敗'), 'error');
                this.roleUsers[role.secure_code] = [];
            } finally {
                this.loadingUsersCode = '';
            }
        },

        openCreate() {
            this.editingRole = null;
            this.resetForm();
            this.selectedPermissionCodes = [];
            this.codePlaceholder = '';
            this.codeMessage = __('名稱輸入後會自動建議 Code');
            this.codeValid = true;
            this.modalOpen = true;
        },

        async openEdit(role) {
            this.editingRole = role;
            this.form = {
                name: role.name || '',
                code: role.code || '',
                role_type: role.role_type || 'ROLE',
                scope_type: role.scope_type || 'GLOBAL',
                is_manager: !!role.is_manager,
                description: role.description || '',
                sort_order: role.sort_order || 0,
                is_active: !!role.is_active,
                exclusive_group: role.exclusive_group || ''
            };
            this.codePlaceholder = role.code || '';
            this.codeMessage = '';
            this.codeValid = true;
            this.modalOpen = true;
            await this.loadPermissions();
            await this.loadRolePermissions(role);
        },

        closeModal() {
            this.modalOpen = false;
            this.editingRole = null;
            if (this.codeTimer) {
                window.clearTimeout(this.codeTimer);
                this.codeTimer = null;
            }
        },

        resetForm() {
            this.form = {
                name: '',
                code: '',
                role_type: 'ROLE',
                scope_type: 'GLOBAL',
                is_manager: false,
                description: '',
                sort_order: 0,
                is_active: true,
                exclusive_group: ''
            };
        },

        onNameInput() {
            if (this.editingRole || this.form.code) return;
            if (this.codeTimer) {
                window.clearTimeout(this.codeTimer);
            }
            this.codeTimer = window.setTimeout(async () => {
                await this.generateCodeSuggestion();
            }, 500);
        },

        async generateCodeSuggestion() {
            if (!this.form.name) {
                this.codePlaceholder = '';
                return;
            }
            try {
                const data = await window.acFetch('/api/roles/generate-code' + this._orgQueryParam(), {
                    method: 'POST',
                    body: { name: this.form.name }
                });
                this.codePlaceholder = data.code || '';
                this.codeMessage = data.code ? __('建議 Code：{code}', { code: data.code }) : '';
            } catch (e) {
                this.codeMessage = e.message || __('無法產生 Code 建議');
            }
        },

        async onCodeInput() {
            if (this.editingRole) return;
            const code = (this.form.code || '').trim();
            if (!code) {
                this.codeValid = true;
                this.codeMessage = this.codePlaceholder ? __('留空將使用建議 Code') : '';
                return;
            }
            try {
                const data = await window.acFetch('/api/roles/validate-code' + this._orgQueryParam(), {
                    method: 'POST',
                    body: { code }
                });
                this.codeValid = !!data.valid;
                this.codeMessage = data.valid ? __('Code 可使用') : (data.error || __('Code 不可使用'));
            } catch (e) {
                this.codeValid = false;
                this.codeMessage = e.message || __('Code 驗證失敗');
            }
        },

        async onPermissionDetailsToggle(event) {
            if (event.target.open) {
                await this.loadPermissions();
            }
        },

        payloadForSave() {
            if (this.isLockedRole) {
                return {
                    description: this.form.description,
                    sort_order: this.form.sort_order,
                    is_active: this.form.is_active
                };
            }
            const payload = {
                name: this.form.name,
                role_type: this.form.role_type,
                scope_type: this.form.scope_type,
                is_manager: this.form.is_manager,
                description: this.form.description,
                sort_order: this.form.sort_order,
                is_active: this.form.is_active,
                exclusive_group: this.form.exclusive_group || null
            };
            if (!this.editingRole && this.form.code) {
                payload.code = this.form.code.trim();
            }
            return payload;
        },

        async saveRole() {
            if (!this.canSave) return;
            this.savingRole = true;
            try {
                const roleUrl = this.editingRole
                    ? '/api/roles/' + encodeURIComponent(this.editingRole.secure_code) + this._orgQueryParam()
                    : '/api/roles/' + this._orgQueryParam();
                const roleData = await window.acFetch(roleUrl, {
                    method: this.editingRole ? 'PUT' : 'POST',
                    body: this.payloadForSave()
                });
                const savedRole = roleData.role;

                await window.acFetch('/api/permissions/role-permissions' + this._orgQueryParam(), {
                    method: 'PUT',
                    body: {
                        role_secure_code: savedRole.secure_code,
                        permission_secure_codes: this.selectedPermissionCodes
                    }
                });

                this.showAlert(this.editingRole ? __('角色已更新') : __('角色已建立'), 'success');
                this.closeModal();
                await this.loadRoles();
            } catch (e) {
                this.showAlert(e.message || __('儲存角色失敗'), 'error');
            } finally {
                this.savingRole = false;
            }
        },

        async deleteRole(role) {
            if (role.is_system_role) return;
            const count = role.holder_count || 0;
            const firstMessage = count
                ? __('此角色已有 {count} 位用戶使用，是否刪除？', { count })
                : __('確定刪除此角色？');
            if (!window.confirm(firstMessage)) return;

            let force = false;
            if (count > 0) {
                if (!window.confirm(__('刪除後會一併移除這些角色指派，是否強制刪除？'))) return;
                force = true;
            }

            try {
                const query = this._orgQueryParam();
                const forceJoiner = query ? '&' : '?';
                const url = '/api/roles/' + encodeURIComponent(role.secure_code) + query + (force ? forceJoiner + 'force=true' : '');
                await window.acFetch(url, { method: 'DELETE' });
                this.showAlert(__('角色已刪除'), 'success');
                if (this.expandedRoleCode === role.secure_code) {
                    this.expandedRoleCode = '';
                }
                await this.loadRoles();
            } catch (e) {
                this.showAlert(e.message || __('刪除角色失敗'), 'error');
            }
        },

        labelFor(options, value) {
            const option = options.find(item => item.value === (value || ''));
            return option ? option.label : (value || '-');
        },

        roleOriginLabel(role) {
            return window.acRoleOriginLabel(role);
        },

        roleOriginClass(role) {
            return window.acRoleOriginClass(role);
        },

        showAlert(message, type) {
            this.alert = { show: true, message, type: type || 'info' };
            window.setTimeout(() => {
                this.alert.show = false;
            }, 3500);
        }
    };
}

window.acRolesTab = acRolesTab;
