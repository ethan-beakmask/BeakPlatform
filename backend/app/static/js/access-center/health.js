/**
 * Access Center - Health tab
 */
function acHealthTab() {
    const config = window.__AC_CONFIG || {};

    return {
        isSystemAdmin: !!config.isSystemAdmin,
        organizations: config.organizations || [],
        selectedOrgCode: config.isSystemAdmin ? '' : (config.userOrgSecureCode || ''),
        orgLabel: config.userOrgLabel || config.userOrgSecureCode || '',

        conflicts: [],
        summary: { total: 0, errors: 0, warnings: 0, infos: 0 },
        importText: '',
        loading: false,
        exporting: false,
        importing: false,
        savingFactory: false,
        restoring: false,
        alert: { show: false, message: '', type: 'info' },

        conflictLabels: {
            MISSING_PERMISSION_DEF: __('選單指定的 RBAC 權限定義不存在'),
            MENU_PERM_NO_RBAC: __('選單可見身分沒有對應 RBAC 權限'),
            ROLE_REQ_NO_HOLDER: __('角色門檻沒有持有人'),
            ROLE_REQ_ROLE_INACTIVE: __('角色門檻使用停用角色'),
            DUAL_KEY_NO_INTERSECTION: __('鑰匙1與鑰匙2沒有交集'),
            ROLE_NO_PERMISSION: __('角色沒有 RBAC 權限或功能門檻'),
            STALE_ASSIGNMENT: __('角色指派指向停用或刪除帳號'),
            MENU_NO_ACCESS_CONTROL: __('選單沒有鑰匙1存取控制'),
            ORPHAN_PERMISSION: __('孤兒 RBAC 權限')
        },

        async init() {
            if (!this.isSystemAdmin) {
                await this.loadConflicts();
            }
        },

        get canLoad() {
            return !this.isSystemAdmin || !!this.selectedOrgCode;
        },

        get groupedConflicts() {
            const groups = {};
            for (const conflict of this.conflicts) {
                const type = conflict.type || 'UNKNOWN';
                if (!groups[type]) {
                    groups[type] = [];
                }
                groups[type].push(conflict);
            }
            return Object.keys(groups).sort().map(type => ({
                type,
                items: groups[type]
            }));
        },

        _orgQueryParam() {
            if (this.isSystemAdmin && this.selectedOrgCode) {
                return '?org_code=' + encodeURIComponent(this.selectedOrgCode);
            }
            return '';
        },

        async onOrgChange() {
            this.conflicts = [];
            this.summary = { total: 0, errors: 0, warnings: 0, infos: 0 };
            if (this.selectedOrgCode) {
                await this.loadConflicts();
            }
        },

        async loadConflicts() {
            if (!this.canLoad) return;
            this.loading = true;
            try {
                const data = await window.acFetch('/api/permissions/conflicts' + this._orgQueryParam());
                this.conflicts = data.conflicts || [];
                this.summary = data.summary || {
                    total: this.conflicts.length,
                    errors: this.conflicts.filter(c => c.severity === 'error').length,
                    warnings: this.conflicts.filter(c => c.severity === 'warning').length,
                    infos: this.conflicts.filter(c => c.severity === 'info').length
                };
            } catch (e) {
                this.showAlert(e.message || __('偵測失敗'), 'error');
            } finally {
                this.loading = false;
            }
        },

        async exportRbac() {
            if (!this.canLoad) return;
            this.exporting = true;
            try {
                const response = await fetch((window.__BP || '') + '/api/permissions/export' + this._orgQueryParam());
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || __('匯出失敗'));
                }
                const blob = await response.blob();
                const disposition = response.headers.get('Content-Disposition') || '';
                const match = disposition.match(/filename="?([^"]+)"?/);
                const filename = match ? match[1] : 'rbac_export.json';
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(link.href);
                this.showAlert(__('匯出完成'), 'success');
            } catch (e) {
                this.showAlert(e.message || __('匯出失敗'), 'error');
            } finally {
                this.exporting = false;
            }
        },

        async importRbac() {
            if (!this.canLoad) return;
            let payload;
            try {
                payload = JSON.parse(this.importText);
            } catch (e) {
                this.showAlert(__('JSON 格式無效'), 'error');
                return;
            }

            const scope = this.isSystemAdmin ? __('所選企業的出廠預設值') : __('本企業的角色權限');
            if (!this.confirmDanger(
                __('匯入會覆蓋 %s。').replace('%s', scope),
                __('請再次確認：匯入後既有 RBAC 設定會被 JSON 內容取代。')
            )) {
                return;
            }

            this.importing = true;
            try {
                const data = await window.acFetch('/api/permissions/import' + this._orgQueryParam(), {
                    method: 'POST',
                    body: payload
                });
                this.importText = '';
                this.showAlert(data.message || __('匯入完成'), 'success');
                await this.loadConflicts();
            } catch (e) {
                this.showAlert(e.message || __('匯入失敗'), 'error');
            } finally {
                this.importing = false;
            }
        },

        async saveFactoryDefaults() {
            if (!this.isSystemAdmin || !this.canLoad) return;
            if (!this.confirmDanger(
                __('將把所選企業目前 RBAC 組態設定為新的出廠值。'),
                __('請再次確認：後續恢復預設會以這份組態覆蓋企業權限。')
            )) {
                return;
            }

            this.savingFactory = true;
            try {
                const data = await window.acFetch('/api/permissions/save-factory-defaults' + this._orgQueryParam(), {
                    method: 'POST',
                    body: {}
                });
                this.showAlert(data.message || __('出廠值已更新'), 'success');
            } catch (e) {
                this.showAlert(e.message || __('儲存失敗'), 'error');
            } finally {
                this.savingFactory = false;
            }
        },

        async restoreDefaults() {
            if (this.isSystemAdmin || !this.canLoad) return;
            if (!this.confirmDanger(
                __('將以出廠值覆蓋本企業系統角色的 RBAC 權限。'),
                __('請再次確認：目前自訂的系統角色權限差異會被重設。')
            )) {
                return;
            }

            this.restoring = true;
            try {
                const data = await window.acFetch('/api/permissions/restore-defaults', {
                    method: 'POST',
                    body: {}
                });
                this.showAlert(data.message || __('已恢復預設權限'), 'success');
                await this.loadConflicts();
            } catch (e) {
                this.showAlert(e.message || __('恢復失敗'), 'error');
            } finally {
                this.restoring = false;
            }
        },

        confirmDanger(firstMessage, secondMessage) {
            return window.confirm(firstMessage) && window.confirm(secondMessage);
        },

        jumpToMenu(menuSecureCode) {
            if (!menuSecureCode) return;
            window.dispatchEvent(new CustomEvent('ac:select-menu', {
                detail: { secureCode: menuSecureCode, orgCode: this.selectedOrgCode }
            }));
        },

        conflictTypeLabel(type) {
            return this.conflictLabels[type] || type || __('未知類型');
        },

        severityLabel(severity) {
            if (severity === 'error') return __('錯誤');
            if (severity === 'warning') return __('警告');
            return __('資訊');
        },

        menuLabel(conflict) {
            const title = conflict.menu_title || '';
            const code = conflict.menu_code || '';
            return title && code ? title + ' (' + code + ')' : (title || code || '-');
        },

        roleLabel(conflict) {
            const name = conflict.role_name || '';
            const code = conflict.role_code || '';
            return name && code ? name + ' (' + code + ')' : (name || code || '-');
        },

        hasRoleOrigin(conflict) {
            return conflict && Object.prototype.hasOwnProperty.call(conflict, 'is_system_role');
        },

        roleOriginLabel(conflict) {
            return window.acRoleOriginLabel(conflict);
        },

        roleOriginClass(conflict) {
            return window.acRoleOriginClass(conflict);
        },

        conflictKey(conflict) {
            return [
                conflict.type || '',
                conflict.menu_secure_code || '',
                conflict.role_secure_code || '',
                conflict.permission_code || '',
                conflict.message || ''
            ].join(':');
        },

        showAlert(message, type) {
            this.alert = { show: true, message, type: type || 'info' };
            window.setTimeout(() => {
                this.alert.show = false;
            }, 3500);
        }
    };
}

window.acHealthTab = acHealthTab;
