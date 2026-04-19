/* settings-recipients.js — 收件人群組管理 (Mode A) */

function recipientGroupManager() {
    return {
        groups: [],
        orgTree: [],
        userCache: {},
        unitCache: {},
        loading: true,
        showModal: false,
        showDeleteModal: false,
        showPreviewModal: false,
        isEditing: false,
        groupToDelete: null,
        previewGroup: null,
        previewRecipientsList: [],
        sourceTab: 'units',
        userSearch: '',
        searchedUsers: [],
        formData: {
            name: '',
            description: '',
            is_active: true,
            included_units: [],
            included_users: [],
            excluded_units: [],
            excluded_users: []
        },

        async init() {
            await Promise.all([
                this.loadGroups(),
                this.loadOrgTree()
            ]);
        },

        async loadGroups() {
            this.loading = true;
            try {
                var response = await fetch('/bp/api/admin/settings/recipient-groups');
                var result = await response.json();
                if (result.success) {
                    this.groups = result.data;
                }
            } catch (error) {
                console.error('載入收件人群組失敗:', error);
            } finally {
                this.loading = false;
            }
        },

        async loadOrgTree() {
            try {
                var response = await fetch('/bp/api/admin/settings/org-tree');
                var result = await response.json();
                if (result.success) {
                    this.orgTree = result.data;
                    for (var i = 0; i < result.data.length; i++) {
                        this.unitCache[result.data[i].id] = result.data[i];
                    }
                }
            } catch (error) {
                console.error('載入組織樹失敗:', error);
            }
        },

        async searchUsers() {
            if (!this.userSearch.trim()) {
                this.searchedUsers = [];
                return;
            }
            try {
                var response = await fetch('/bp/api/admin/settings/org-users?search=' + encodeURIComponent(this.userSearch));
                var result = await response.json();
                if (result.success) {
                    this.searchedUsers = result.data;
                    for (var i = 0; i < result.data.length; i++) {
                        this.userCache[result.data[i].id] = result.data[i];
                    }
                }
            } catch (error) {
                console.error('搜尋用戶失敗:', error);
            }
        },

        getUnitName(unitId) {
            var unit = this.unitCache[unitId];
            return unit ? unit.name : unitId;
        },

        getUserName(userId) {
            var user = this.userCache[userId];
            return user ? user.name : userId;
        },

        isUnitSelected(unitId) {
            return this.formData.included_units.some(function(u) { return u.id === unitId; });
        },

        isUserSelected(userId) {
            return this.formData.included_users.includes(userId);
        },

        toggleUnit(unit) {
            var idx = this.formData.included_units.findIndex(function(u) { return u.id === unit.id; });
            if (idx >= 0) {
                this.formData.included_units.splice(idx, 1);
            } else {
                this.formData.included_units.push({
                    id: unit.id,
                    include_children: false
                });
            }
        },

        toggleUser(user) {
            var idx = this.formData.included_users.indexOf(user.id);
            if (idx >= 0) {
                this.formData.included_users.splice(idx, 1);
            } else {
                this.formData.included_users.push(user.id);
                this.userCache[user.id] = user;
            }
        },

        removeUnit(idx) {
            this.formData.included_units.splice(idx, 1);
        },

        removeUser(idx) {
            this.formData.included_users.splice(idx, 1);
        },

        openCreateModal() {
            this.isEditing = false;
            this.formData = {
                name: '',
                description: '',
                is_active: true,
                included_units: [],
                included_users: [],
                excluded_units: [],
                excluded_users: []
            };
            this.sourceTab = 'units';
            this.userSearch = '';
            this.searchedUsers = [];
            this.showModal = true;
        },

        async openEditModal(group) {
            this.isEditing = true;
            try {
                var response = await fetch('/bp/api/admin/settings/recipient-groups/' + group.id);
                var result = await response.json();
                if (result.success) {
                    var data = result.data;
                    this.formData = {
                        id: data.id,
                        name: data.name,
                        description: data.description || '',
                        is_active: data.is_active,
                        included_units: data.included_units || [],
                        included_users: data.included_users || [],
                        excluded_units: data.excluded_units || [],
                        excluded_users: data.excluded_users || []
                    };
                    this.sourceTab = 'units';
                    this.userSearch = '';
                    this.searchedUsers = [];
                    this.showModal = true;
                }
            } catch (error) {
                alert('載入群組失敗：' + error.message);
            }
        },

        closeModal() {
            this.showModal = false;
        },

        async saveGroup() {
            var data = {
                name: this.formData.name,
                description: this.formData.description,
                is_active: this.formData.is_active,
                included_units: this.formData.included_units,
                included_users: this.formData.included_users,
                excluded_units: this.formData.excluded_units,
                excluded_users: this.formData.excluded_users
            };

            try {
                var url = this.isEditing
                    ? '/bp/api/admin/settings/recipient-groups/' + this.formData.id
                    : '/bp/api/admin/settings/recipient-groups';
                var method = this.isEditing ? 'PUT' : 'POST';

                var response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(data)
                });

                var result = await response.json();
                if (result.success) {
                    this.closeModal();
                    await this.loadGroups();
                } else {
                    alert(result.message || '操作失敗');
                }
            } catch (error) {
                alert('操作失敗：' + error.message);
            }
        },

        async previewRecipients(group) {
            this.previewGroup = group;
            this.previewRecipientsList = [];
            this.showPreviewModal = true;

            try {
                var response = await fetch('/bp/api/admin/settings/recipient-groups/' + group.id + '/resolve');
                var result = await response.json();
                if (result.success) {
                    this.previewRecipientsList = result.data.recipients;
                }
            } catch (error) {
                console.error('載入預覽失敗:', error);
            }
        },

        confirmDelete(group) {
            this.groupToDelete = group;
            this.showDeleteModal = true;
        },

        async deleteGroup() {
            if (!this.groupToDelete) return;

            try {
                var response = await fetch('/bp/api/admin/settings/recipient-groups/' + this.groupToDelete.id, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                });

                var result = await response.json();
                if (result.success) {
                    this.showDeleteModal = false;
                    this.groupToDelete = null;
                    await this.loadGroups();
                } else {
                    alert(result.message || '刪除失敗');
                }
            } catch (error) {
                alert('刪除失敗：' + error.message);
            }
        }
    };
}
