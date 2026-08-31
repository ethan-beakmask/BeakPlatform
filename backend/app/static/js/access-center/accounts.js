/**
 * Access Center - Account roles tab
 */
function acAccountsTab() {
    return {
        users: [],
        assignableRoles: [],
        units: [],
        loading: false,
        saving: false,
        removingRoleCode: '',
        modalOpen: false,
        modalError: '',
        alert: { show: false, message: '', type: 'info' },
        filters: {
            accountType: '',
            keyword: ''
        },
        page: 1,
        pagination: {
            page: 1,
            pages: 1,
            total: 0,
            has_prev: false,
            has_next: false
        },
        selectedUser: null,
        form: {
            roleSecureCode: '',
            unitSecureCode: ''
        },
        accountTypeOptions: [
            { value: '', label: __('全部') },
            { value: 'ORG_ADMIN', label: __('企業管理員') },
            { value: 'EMPLOYEE', label: __('企業成員') },
            { value: 'EXTERNAL', label: __('外部廠商') }
        ],

        async init() {
            await this.loadAccounts();
        },

        get selectedRole() {
            return this.assignableRoles.find(role => role.secure_code === this.form.roleSecureCode) || null;
        },

        // PERM-01 層界：EXTERNAL 帳號只列外部範圍角色，內部帳號不列外部範圍角色
        // （後端 ensure_role_layer_compatible 才是防線，這裡只是不讓人選到必被退回的選項）
        get roleOptions() {
            if (!this.selectedUser) return this.assignableRoles;
            const isExternal = this.selectedUser.account_type === 'EXTERNAL';
            return this.assignableRoles.filter(role => (role.scope_type === 'EXTERNAL') === isExternal);
        },

        get selectedRoleNeedsUnit() {
            return !!(this.selectedRole && ['DEPARTMENT', 'GROUP'].indexOf(this.selectedRole.scope_type) !== -1);
        },

        get unitOptions() {
            if (!this.selectedRole) return [];
            const unitType = this.selectedRole.scope_type === 'DEPARTMENT' ? 'DEPARTMENT' : 'GROUP';
            return this.units.filter(unit => unit.unit_type === unitType);
        },

        get canAssign() {
            if (this.saving || !this.form.roleSecureCode) return false;
            if (this.selectedRoleNeedsUnit && !this.form.unitSecureCode) return false;
            return true;
        },

        async loadAccounts() {
            this.loading = true;
            const params = new URLSearchParams();
            if (this.filters.accountType) params.set('account_type', this.filters.accountType);
            if (this.filters.keyword) params.set('keyword', this.filters.keyword);
            params.set('page', this.page);

            try {
                const data = await window.acFetch('/api/access/account-roles?' + params.toString());
                this.users = data.users || [];
                this.assignableRoles = data.assignable_roles || [];
                this.units = data.units || [];
                this.pagination = data.pagination || this.pagination;
                this.page = this.pagination.page || this.page;
            } catch (e) {
                this.showAlert(e.message || __('載入帳號角色失敗'), 'error');
            } finally {
                this.loading = false;
            }
        },

        async applyFilters() {
            this.page = 1;
            await this.loadAccounts();
        },

        async goPrev() {
            if (!this.pagination.has_prev || this.loading) return;
            this.page = Math.max(1, this.page - 1);
            await this.loadAccounts();
        },

        async goNext() {
            if (!this.pagination.has_next || this.loading) return;
            this.page += 1;
            await this.loadAccounts();
        },

        openAssign(user) {
            this.selectedUser = user;
            this.form = {
                roleSecureCode: '',
                unitSecureCode: ''
            };
            this.modalError = '';
            this.modalOpen = true;
        },

        closeModal() {
            this.modalOpen = false;
            this.selectedUser = null;
            this.modalError = '';
            this.saving = false;
        },

        onRoleChange() {
            this.form.unitSecureCode = '';
            this.modalError = '';
        },

        async assignSelectedRole() {
            if (!this.canAssign || !this.selectedUser) return;
            this.saving = true;
            this.modalError = '';
            try {
                const body = {
                    user_secure_code: this.selectedUser.secure_code,
                    role_secure_code: this.form.roleSecureCode
                };
                if (this.selectedRoleNeedsUnit) {
                    body.unit_secure_code = this.form.unitSecureCode;
                }
                const data = await window.acFetch('/api/access/assign', {
                    method: 'POST',
                    body
                });
                this.showAlert(data.message || __('角色已指派'), 'success');
                this.closeModal();
                await this.loadAccounts();
            } catch (e) {
                this.modalError = e.message || __('指派角色失敗');
            } finally {
                this.saving = false;
            }
        },

        async revokeRole(user, role) {
            const message = __('確定要移除 {user} 的「{role}」角色？', {
                user: user.display_name,
                role: role.name
            });
            if (!window.confirm(message)) return;

            this.removingRoleCode = role.assignment_secure_code || role.secure_code;
            try {
                const data = await window.acFetch('/api/access/revoke', {
                    method: 'POST',
                    body: {
                        user_secure_code: user.secure_code,
                        role_secure_code: role.secure_code
                    }
                });
                this.showAlert(data.message || __('角色已移除'), 'success');
                await this.loadAccounts();
            } catch (e) {
                this.showAlert(e.message || __('移除角色失敗'), 'error');
            } finally {
                this.removingRoleCode = '';
            }
        },

        roleDisplayName(role) {
            let label = role.name || '';
            if (role.unit_name) {
                label += ' / ' + role.unit_name;
            }
            return label;
        },

        roleOptionLabel(role) {
            const scope = this.scopeLabel(role.scope_type);
            return role.name + ' ' + window.acRoleOriginSuffix(role) + ' - ' + scope;
        },

        roleOriginLabel(role) {
            return window.acRoleOriginLabel(role);
        },

        roleOriginClass(role) {
            return window.acRoleOriginClass(role);
        },

        scopeLabel(scopeType) {
            const labels = {
                GLOBAL: __('全企業'),
                DEPARTMENT: __('部門'),
                GROUP: __('社群'),
                EXTERNAL: __('外部')
            };
            return labels[scopeType] || scopeType || '';
        },

        accountTypeClass(accountType) {
            return 'ac-account-type-' + String(accountType || '').toLowerCase().replace('_', '-');
        },

        showAlert(message, type) {
            this.alert = { show: true, message, type: type || 'info' };
            window.setTimeout(() => {
                this.alert.show = false;
            }, 3600);
        }
    };
}

window.acAccountsTab = acAccountsTab;
