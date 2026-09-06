/**
 * Access Center - Account roles tab
 */
function acAccountsTab() {
    const config = window.__AC_CONFIG || {};

    function emptyForm() {
        return {
            kind: 'regular',
            roleSecureCode: '',
            unitSecureCode: '',
            actingForSecureCode: '',
            validFrom: '',
            validUntil: '',
            allowedFormTemplates: [],
            grantReason: ''
        };
    }

    return {
        users: [],
        assignableRoles: [],
        assignableRolesForGrant: [],
        units: [],
        formTemplates: config.formTemplates || [],
        roleHolders: [],
        roleHoldersLoading: false,
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
        form: emptyForm(),
        accountTypeOptions: [
            { value: '', label: __('全部') },
            { value: 'ORG_ADMIN', label: __('企業管理員') },
            { value: 'EMPLOYEE', label: __('企業成員') },
            { value: 'EXTERNAL', label: __('外部廠商') }
        ],
        assignmentKindOptions: [
            { value: 'regular', label: __('正式') },
            { value: 'proxy', label: __('代理') },
            { value: 'standby', label: __('候補') }
        ],

        async init() {
            await this.loadAccounts();
        },

        get activeRoleSource() {
            return this.form.kind === 'regular' ? this.assignableRoles : this.assignableRolesForGrant;
        },

        get selectedRole() {
            return this.activeRoleSource.find(role => role.secure_code === this.form.roleSecureCode) || null;
        },

        // PERM-01 層界：EXTERNAL 帳號只列外部範圍角色，內部帳號不列外部範圍角色。
        get roleOptions() {
            if (!this.selectedUser) return this.activeRoleSource;
            const isExternal = this.selectedUser.account_type === 'EXTERNAL';
            return this.activeRoleSource.filter(role => (role.scope_type === 'EXTERNAL') === isExternal);
        },

        get selectedRoleNeedsUnit() {
            return !!(this.selectedRole && ['DEPARTMENT', 'GROUP'].indexOf(this.selectedRole.scope_type) !== -1);
        },

        get unitOptions() {
            if (!this.selectedRole) return [];
            const unitType = this.selectedRole.scope_type === 'DEPARTMENT' ? 'DEPARTMENT' : 'GROUP';
            return this.units.filter(unit => unit.unit_type === unitType);
        },

        get canLoadRoleHolders() {
            if (this.form.kind === 'regular' || !this.form.roleSecureCode) return false;
            if (this.selectedRoleNeedsUnit && !this.form.unitSecureCode) return false;
            return true;
        },

        get roleHoldersPlaceholder() {
            if (this.roleHoldersLoading) return __('載入中');
            if (!this.canLoadRoleHolders) return __('請先選擇角色與單位');
            return this.form.kind === 'proxy' ? __('請選擇被代理人') : __('不指定');
        },

        get canAssign() {
            if (this.saving || !this.form.roleSecureCode) return false;
            if (this.selectedRoleNeedsUnit && !this.form.unitSecureCode) return false;
            if (this.form.kind === 'proxy') {
                return !!(this.form.actingForSecureCode && this.form.validFrom && this.form.validUntil && this.form.grantReason);
            }
            if (this.form.kind === 'standby') {
                return !!this.form.grantReason;
            }
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
                this.assignableRolesForGrant = data.assignable_roles_for_grant || [];
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
            this.form = emptyForm();
            this.roleHolders = [];
            this.modalError = '';
            this.modalOpen = true;
        },

        closeModal() {
            this.modalOpen = false;
            this.selectedUser = null;
            this.modalError = '';
            this.saving = false;
        },

        onKindChange() {
            this.form.roleSecureCode = '';
            this.form.unitSecureCode = '';
            this.form.actingForSecureCode = '';
            this.form.validFrom = '';
            this.form.validUntil = '';
            this.form.allowedFormTemplates = [];
            this.form.grantReason = '';
            this.roleHolders = [];
            this.modalError = '';
        },

        async onRoleChange() {
            this.form.unitSecureCode = '';
            this.form.actingForSecureCode = '';
            this.roleHolders = [];
            this.modalError = '';
            await this.loadRoleHoldersIfReady();
        },

        async onUnitChange() {
            this.form.actingForSecureCode = '';
            this.roleHolders = [];
            this.modalError = '';
            await this.loadRoleHoldersIfReady();
        },

        async loadRoleHoldersIfReady() {
            if (!this.canLoadRoleHolders) return;
            this.roleHoldersLoading = true;
            const params = new URLSearchParams();
            params.set('role_secure_code', this.form.roleSecureCode);
            if (this.form.unitSecureCode) params.set('unit_secure_code', this.form.unitSecureCode);
            try {
                const data = await window.acFetch('/api/access/role-holders?' + params.toString());
                this.roleHolders = data.holders || [];
            } catch (e) {
                this.modalError = e.message || __('載入被代理人失敗');
            } finally {
                this.roleHoldersLoading = false;
            }
        },

        async assignSelectedRole() {
            if (!this.canAssign || !this.selectedUser) return;
            this.saving = true;
            this.modalError = '';
            try {
                const body = {
                    user_secure_code: this.selectedUser.secure_code,
                    role_secure_code: this.form.roleSecureCode,
                    kind: this.form.kind
                };
                if (this.selectedRoleNeedsUnit) {
                    body.unit_secure_code = this.form.unitSecureCode;
                }
                if (this.form.kind !== 'regular') {
                    body.acting_for_secure_code = this.form.actingForSecureCode || null;
                    body.valid_from = this.form.validFrom || null;
                    body.valid_until = this.form.validUntil || null;
                    body.allowed_form_templates = this.form.allowedFormTemplates;
                    body.grant_reason = this.form.grantReason;
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
                        assignment_secure_code: role.assignment_secure_code
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

        roleKindLabel(role) {
            const kind = role.assignment_kind || 'regular';
            const range = this.roleDateRange(role);
            if (kind === 'proxy') {
                const name = role.acting_for_name || role.acting_for_secure_code || '';
                return (name ? __('代理 {name}', { name }) : __('代理')) + (range ? ' ' + range : '');
            }
            if (kind === 'standby') {
                return __('候補') + (range ? ' ' + range : '');
            }
            return '';
        },

        roleDateRange(role) {
            const from = this.shortDate(role.valid_from);
            const until = this.shortDate(role.valid_until);
            if (from && until) return from + '～' + until;
            if (from) return from + '～';
            if (until) return '～' + until;
            return '';
        },

        shortDate(value) {
            if (!value || value.length < 10) return '';
            return value.slice(5, 10);
        },

        roleOptionLabel(role) {
            const scope = this.scopeLabel(role.scope_type);
            return role.name + ' ' + window.acRoleOriginSuffix(role) + ' - ' + scope;
        },

        holderLabel(holder) {
            return holder.employee_id
                ? holder.employee_id + ' ' + holder.display_name
                : holder.display_name;
        },

        formTemplateLabel(template) {
            const code = template.code ? '[' + template.code + '] ' : '';
            return code + template.name;
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
