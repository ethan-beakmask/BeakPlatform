/* global __ */
function wksOrgManager(subSystemSc) {
    const BP = window.__BP || '';
    const CODE_RE = /^[A-Z][A-Z0-9_]{0,31}$/;

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    return {
        subSystemSc: subSystemSc || '',
        loading: true,
        saving: false,
        groups: [],
        levels: [],
        users: [],
        draggingUserSc: '',
        groupForm: { open: false, editing: false, code: '', name: '', display_order: 0 },
        levelForm: { open: false, editing: false, code: '', name: '', rank: 0, display_order: 0 },
        assignmentPanel: { open: false, user: null, group_code: '', level_code: '' },
        toast: { show: false, message: '' },

        async init() {
            await this.loadOrg();
        },

        async loadOrg() {
            this.loading = true;
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/portal/org`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('載入帳號權限資料失敗'));
                    return;
                }
                this.groups = data.data.groups || [];
                this.levels = data.data.levels || [];
                this.users = data.data.users || [];
            } catch (err) {
                this.showToast(err.message || __('載入帳號權限資料失敗'));
            } finally {
                this.loading = false;
            }
        },

        activeGroups() {
            return (this.groups || []).filter((group) => this.truthy(group.is_active));
        },

        matrixGroups() {
            const groups = this.activeGroups().sort((a, b) => {
                const order = Number(a.display_order || 0) - Number(b.display_order || 0);
                return order || String(a.code || '').localeCompare(String(b.code || ''));
            });
            groups.push({ code: '', name: __('未歸屬'), display_order: 999999 });
            return groups;
        },

        sortedLevelsDesc() {
            return (this.levels || []).filter((level) => this.truthy(level.is_active)).sort((a, b) => {
                const rank = Number(b.rank || 0) - Number(a.rank || 0);
                const order = Number(a.display_order || 0) - Number(b.display_order || 0);
                return rank || order || String(a.code || '').localeCompare(String(b.code || ''));
            });
        },

        matrixLevels() {
            const levels = this.sortedLevelsDesc();
            levels.push({ code: '', name: __('未歸屬'), rank: '', display_order: 999999 });
            return levels;
        },

        knownGroup(code) {
            return (this.groups || []).some((group) => group.code === code && this.truthy(group.is_active));
        },

        knownLevel(code) {
            return (this.levels || []).some((level) => level.code === code && this.truthy(level.is_active));
        },

        userGroupCode(user) {
            return user && this.knownGroup(user.group_code) ? user.group_code : '';
        },

        userLevelCode(user) {
            return user && this.knownLevel(user.level_code) ? user.level_code : '';
        },

        usersForCell(group, level) {
            const groupCode = group.code || '';
            const levelCode = level.code || '';
            return (this.users || []).filter((user) => (
                this.userGroupCode(user) === groupCode && this.userLevelCode(user) === levelCode
            ));
        },

        truthy(value) {
            return value === true || value === 1 || value === '1';
        },

        onDragStart(event, user) {
            this.draggingUserSc = user.secure_code;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', user.secure_code);
        },

        onDragEnd(event) {
            this.draggingUserSc = '';
            this.clearDragOver();
            if (event && event.currentTarget) {
                event.currentTarget.classList.remove('wks-user-chip-dragging');
            }
        },

        onDragOver(event, group, level) {
            event.dataTransfer.dropEffect = group.code && level.code ? 'move' : 'none';
            event.currentTarget.classList.add('wks-matrix-drag-over');
        },

        onDragLeave(event) {
            event.currentTarget.classList.remove('wks-matrix-drag-over');
        },

        async onDrop(event, group, level) {
            event.currentTarget.classList.remove('wks-matrix-drag-over');
            const userSc = event.dataTransfer.getData('text/plain') || this.draggingUserSc;
            if (!userSc) return;

            if (!group.code || !level.code) {
                this.showToast(__('未歸屬格不允許拖放'));
                return;
            }

            const user = this.users.find((item) => item.secure_code === userSc);
            if (!user) return;
            if (user.group_code === group.code && user.level_code === level.code) return;

            await this.updateAssignment(user, group.code, level.code);
        },

        clearDragOver() {
            document.querySelectorAll('.wks-matrix-drag-over').forEach((el) => {
                el.classList.remove('wks-matrix-drag-over');
            });
        },

        openAssignmentPanel(user) {
            const activeGroups = this.activeGroups();
            const activeLevels = this.sortedLevelsDesc();
            if (!activeGroups.length || !activeLevels.length) {
                this.showToast(__('請先建立群組與階級'));
                return;
            }
            this.assignmentPanel = {
                open: true,
                user,
                group_code: this.knownGroup(user.group_code) ? user.group_code : activeGroups[0].code,
                level_code: this.knownLevel(user.level_code) ? user.level_code : activeLevels[0].code,
            };
        },

        closeAssignmentPanel() {
            this.assignmentPanel = { open: false, user: null, group_code: '', level_code: '' };
        },

        async saveAssignmentPanel() {
            const panel = this.assignmentPanel;
            if (!panel.user) return;
            await this.updateAssignment(panel.user, panel.group_code, panel.level_code);
            this.closeAssignmentPanel();
        },

        async updateAssignment(user, groupCode, levelCode) {
            if (!groupCode || !levelCode) {
                this.showToast(__('請選擇群組與階級'));
                return false;
            }
            this.saving = true;
            try {
                const res = await fetch(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}/portal/users/${encodeURIComponent(user.secure_code)}/assignment`,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                        body: JSON.stringify({ group_code: groupCode, level_code: levelCode }),
                    }
                );
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('帳號歸屬更新失敗'));
                    return false;
                }
                user.group_code = groupCode;
                user.level_code = levelCode;
                this.showToast(data.message || __('帳號歸屬已更新'));
                return true;
            } catch (err) {
                this.showToast(err.message || __('帳號歸屬更新失敗'));
                return false;
            } finally {
                this.saving = false;
                this.draggingUserSc = '';
            }
        },

        startGroupForm(group) {
            this.cancelForms();
            this.groupForm = {
                open: true,
                editing: !!group,
                code: group ? group.code : '',
                name: group ? group.name : '',
                display_order: group ? Number(group.display_order || 0) : 0,
            };
        },

        editGroup(group) {
            this.startGroupForm(group);
        },

        startLevelForm(level) {
            this.cancelForms();
            this.levelForm = {
                open: true,
                editing: !!level,
                code: level ? level.code : '',
                name: level ? level.name : '',
                rank: level ? Number(level.rank || 0) : 0,
                display_order: level ? Number(level.display_order || 0) : 0,
            };
        },

        editLevel(level) {
            this.startLevelForm(level);
        },

        cancelForms() {
            this.groupForm = { open: false, editing: false, code: '', name: '', display_order: 0 };
            this.levelForm = { open: false, editing: false, code: '', name: '', rank: 0, display_order: 0 };
        },

        validateCode(code, label) {
            if (!CODE_RE.test(String(code || '').trim())) {
                this.showToast(__('{label}代碼格式不正確', { label }));
                return false;
            }
            return true;
        },

        async saveGroup() {
            const form = this.groupForm;
            const code = String(form.code || '').trim();
            const name = String(form.name || '').trim();
            if (!this.validateCode(code, __('群組'))) return;
            if (!name) {
                this.showToast(__('請輸入群組名稱'));
                return;
            }
            await this.postOrgUnit('/portal/groups', {
                code,
                name,
                display_order: Number(form.display_order || 0),
            }, __('群組已儲存'));
        },

        async saveLevel() {
            const form = this.levelForm;
            const code = String(form.code || '').trim();
            const name = String(form.name || '').trim();
            if (!this.validateCode(code, __('階級'))) return;
            if (!name) {
                this.showToast(__('請輸入階級名稱'));
                return;
            }
            await this.postOrgUnit('/portal/levels', {
                code,
                name,
                rank: Number(form.rank || 0),
                display_order: Number(form.display_order || 0),
            }, __('階級已儲存'));
        },

        async postOrgUnit(path, payload, fallbackMessage) {
            this.saving = true;
            try {
                const res = await fetch(
                    `${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.subSystemSc)}${path}`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                        body: JSON.stringify(payload),
                    }
                );
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.showToast(data.error || __('儲存失敗'));
                    return;
                }
                this.cancelForms();
                await this.loadOrg();
                this.showToast(data.message || fallbackMessage);
            } catch (err) {
                this.showToast(err.message || __('儲存失敗'));
            } finally {
                this.saving = false;
            }
        },

        showToast(message) {
            this.toast = { show: true, message };
            setTimeout(() => { this.toast.show = false; }, 2600);
        },
    };
}
