/* groups.js — 社群設定頁 (groupManager) */

const __groupsConfig = window.__GROUPS_CONFIG || {};

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

function groupManager() {
    return {
        ...codeInputMixin('group'),
        groups: [],
        expandedNodes: {},
        selectedGroup: null,
        members: [],  // 原始成員資料 (from cross-members API)
        leadership: { manager: null, deputy: null, proxy1: null, proxy2: null },
        allUsers: [],
        filteredUsers: [],
        userSearch: '',
        formData: { code: '', name: '', description: '', parent_id: '' },
        isCreating: false,
        showPeopleInTree: false,
        treeExpanded: false,
        totalUsers: 0,

        // 拖拉狀態
        draggedUser: null,
        draggedMember: null,
        draggedLeader: null,
        draggedLeaderType: null,
        dragOverZone: null,
        draggedTreePerson: null,

        async init() {
            // 取得帳號
            try {
                const res = await fetch('/api/users?per_page=1000');
                if (res.ok) {
                    const data = await res.json();
                    this.allUsers = (data.users || []).filter(u => !u.is_deleted && u.is_active);
                    this.filteredUsers = [...this.allUsers];
                    this.totalUsers = this.allUsers.length;
                }
            } catch (e) {}

            // 帳號 >= 30：社群模式+展開，否則成員模式
            if (this.totalUsers >= 30) {
                this.showPeopleInTree = false;
                this.treeExpanded = true;
            } else {
                this.showPeopleInTree = true;
                this.treeExpanded = false;
            }

            await this.loadGroups();
            // 確保 jQuery 和 jstree 已載入
            if (typeof $ !== 'undefined' && $.fn.jstree) {
                this.initJsTree();
            } else {
                console.error('jQuery or jstree not loaded');
            }
        },

        // jstree 初始化
        initJsTree() {
            const self = this;
            const $tree = $('#group-tree');

            // 銷毀舊實例
            if ($tree.jstree(true)) {
                $tree.jstree('destroy');
            }

            $tree.jstree({
                core: {
                    data: this.buildJsTreeData(),
                    themes: { dots: true, icons: true },
                    check_callback: (op, node, parent) => {
                        // 允許拖放操作
                        if (op === 'move_node') {
                            // 人員只能放到社群節點
                            if (node.data?.type === 'person') {
                                return parent.data?.type === 'group';
                            }
                            // 社群不能放到人員節點或自己的子節點下
                            if (node.data?.type === 'group') {
                                return parent.id === '#' || parent.data?.type === 'group' || parent.data?.type === 'root';
                            }
                        }
                        return true;
                    },
                    worker: false
                },
                plugins: ['wholerow', 'dnd'],
                dnd: {
                    is_draggable: (nodes) => {
                        const type = nodes[0].data?.type;
                        return type === 'group' || type === 'person';
                    },
                    copy: false
                }
            });

            // 選擇事件
            $tree.on('select_node.jstree', (e, data) => {
                if (data.node.data?.type === 'group') {
                    const group = self.findGroupById(data.node.id);
                    if (group) self.selectGroup(group);
                }
            });

            // 拖放事件 - 社群階層調整
            $tree.on('move_node.jstree', async (e, data) => {
                const movedNode = data.node;
                const newParentId = data.parent === '#' ? null : data.parent;

                // 社群節點移動 = 改父社群
                if (movedNode.data?.type === 'group') {
                    await fetch(`/api/units/${movedNode.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ parent_id: newParentId === 'root' ? null : newParentId })
                    });
                    self.showToast('社群已移動', 'success');
                    await self.loadGroups();
                }
                self.refreshJsTree();
            });

            // jstree 拖動開始/結束事件
            $(document).on('dnd_start.vakata', (e, data) => {
                const node = data.data.nodes[0];
                const $tree = $('#group-tree');
                const nodeData = $tree.jstree(true).get_node(node)?.data;
                if (nodeData?.type === 'person') {
                    self.draggedTreePerson = {
                        id: nodeData.userId,
                        groupId: nodeData.groupId,
                        role: nodeData.role,
                        membershipId: nodeData.membershipId
                    };
                }
            });
            $(document).on('dnd_stop.vakata', (e, data) => {
                setTimeout(() => {
                    self.draggedTreePerson = null;
                    $('.jstree-drop-target').removeClass('jstree-drop-target');
                }, 100);
            });

            // jstree 拖動中
            $(document).on('dnd_move.vakata', (e, data) => {
                if (!self.draggedTreePerson) return;
                const $target = $(data.event.target);
                $('.jstree-drop-target').removeClass('jstree-drop-target');

                const $proxy = $target.closest('.proxy-section');
                const $col = $target.closest('.staff-column');

                if ($proxy.length) {
                    $proxy.addClass('jstree-drop-target');
                } else if ($col.length) {
                    $col.addClass('jstree-drop-target');
                }
            });

            // 滑鼠放開時處理外部區域的 drop
            $(document).on('mouseup', '.staff-column, .proxy-section', async function(e) {
                if (!self.draggedTreePerson) return;

                const $this = $(this);

                // 代理人區
                if ($this.hasClass('proxy-section')) {
                    const labelText = $this.find('.proxy-label').text();
                    const roleType = labelText.includes('(一)') ? 'PROXY1' : 'PROXY2';
                    self.dropToRole(e, roleType);
                }
                // 團長/副團長欄
                else if ($this.hasClass('staff-column') && !$this.hasClass('member-col')) {
                    let roleType = 'MANAGER';
                    if ($this.hasClass('deputy-col')) roleType = 'DEPUTY';
                    self.dropToRole(e, roleType);
                }
                // 團員欄
                else if ($this.hasClass('member-col')) {
                    self.dropToRole(e, 'MEMBER');
                }
            });
        },

        buildJsTreeData() {
            const self = this;
            const build = (items) => items.map(item => {
                const node = {
                    id: item.id,
                    text: item.name,
                    icon: 'icon-group',
                    state: { opened: true },
                    data: { type: 'group', ...item },
                    children: []
                };
                // 成員模式：加入人員節點
                if (self.showPeopleInTree && item._members) {
                    item._members.forEach((m) => {
                        let roleTag = '員';
                        let roleClass = 'employee';
                        if (m.role_type === 'MANAGER') { roleTag = '團'; roleClass = 'leader'; }
                        else if (m.role_type === 'DEPUTY') { roleTag = '副'; roleClass = 'leader'; }
                        else if (m.role_type === 'PROXY1') { roleTag = '代'; roleClass = 'leader'; }
                        else if (m.role_type === 'PROXY2') { roleTag = '代'; roleClass = 'leader'; }

                        node.children.push({
                            id: 'p_' + item.id + '_' + m.id,
                            text: `<span class="role-tag ${roleClass}">${roleTag}</span>${m.user?.native_name || m.user?.display_name || '?'}`,
                            icon: false,
                            data: {
                                type: 'person',
                                userId: m.user_secure_code,
                                groupId: item.id,
                                role: m.role_type,
                                membershipId: m.id
                            }
                        });
                    });
                }
                // 子社群
                if (item.children?.length > 0) {
                    node.children = node.children.concat(build(item.children));
                }
                return node;
            });
            // 根節點
            return [{
                id: 'root',
                text: __groupsConfig.orgName || '企業',
                icon: 'icon-company',
                state: { opened: true },
                data: { type: 'root' },
                children: build(this.groups)
            }];
        },

        refreshJsTree() {
            const $tree = $('#group-tree');
            if ($tree.jstree(true)) {
                $tree.jstree(true).settings.core.data = this.buildJsTreeData();
                $tree.jstree(true).refresh();
            }
        },

        findGroupById(id) {
            const find = (items) => {
                for (const item of items) {
                    if (item.id === id) return item;
                    if (item.children) {
                        const found = find(item.children);
                        if (found) return found;
                    }
                }
                return null;
            };
            return find(this.groups);
        },

        // 計算屬性
        get allGroupsFlat() {
            const result = [];
            const flatten = (items, level) => {
                for (const item of items) {
                    result.push({ ...item, level });
                    if (item.children?.length > 0) flatten(item.children, level + 1);
                }
            };
            flatten(this.groups, 0);
            return result;
        },

        get availableParents() {
            if (this.isCreating || !this.selectedGroup) return this.allGroupsFlat;
            const excludeIds = new Set([this.selectedGroup.id]);
            const collectDescendants = (items) => {
                for (const item of items) {
                    excludeIds.add(item.id);
                    if (item.children) collectDescendants(item.children);
                }
            };
            if (this.selectedGroup.children) collectDescendants(this.selectedGroup.children);
            return this.allGroupsFlat.filter(g => !excludeIds.has(g.id));
        },

        get leaderIds() {
            return [
                this.leadership.manager?.id,
                this.leadership.deputy?.id,
                this.leadership.proxy1?.id,
                this.leadership.proxy2?.id
            ].filter(Boolean);
        },

        get regularMembers() {
            // 排除管理層的一般團員
            return this.members.filter(m => !['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(m.role_type));
        },

        get totalCount() {
            return this.members.length;
        },

        // 檢查用戶是否已是成員
        isMember(userId) {
            return this.members.some(m => m.user_secure_code === userId);
        },

        // API
        async loadGroups() {
            try {
                const res = await fetch('/api/units/groups?tree=true');
                const data = await res.json();
                if (res.ok) {
                    this.groups = data.units || [];
                    this.allGroupsFlat.forEach(g => {
                        if (this.expandedNodes[g.id] === undefined) this.expandedNodes[g.id] = true;
                    });
                    if (this.showPeopleInTree) await this.loadAllPeople();
                }
            } catch (err) {
                this.showToast('載入失敗', 'error');
            }
        },

        async loadAllPeople() {
            // 遞迴載入每個社群的人員資料
            const loadForGroup = async (group) => {
                try {
                    const res = await fetch(`/api/units/${group.id}/cross-members`);
                    if (res.ok) {
                        const data = await res.json();
                        group._members = data.cross_members || [];
                    }
                } catch (e) {}
                if (group.children) {
                    for (const child of group.children) {
                        await loadForGroup(child);
                    }
                }
            };
            for (const group of this.groups) {
                await loadForGroup(group);
            }
        },

        switchToGroupMode() {
            this.showPeopleInTree = false;
            this.refreshJsTree();
        },

        async switchToDetailMode() {
            this.showPeopleInTree = true;
            const firstGroup = this.groups[0];
            if (firstGroup && !firstGroup._members) {
                await this.loadAllPeople();
                this.groups = [...this.groups];
            }
            this.refreshJsTree();
        },

        async loadMembers(groupId) {
            try {
                const res = await fetch(`/api/units/${groupId}/cross-members`);
                const data = await res.json();
                if (res.ok) {
                    const rawMembers = data.cross_members || [];
                    this.members = rawMembers;

                    // 解析管理層
                    const newLeadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
                    for (const m of rawMembers) {
                        const userData = {
                            id: m.user_secure_code,
                            membershipId: m.id,
                            employee_id: m.user?.employee_id,
                            native_name: m.user?.native_name,
                            display_name: m.user?.display_name,
                            english_name: m.user?.english_name
                        };
                        if (m.role_type === 'MANAGER') newLeadership.manager = userData;
                        else if (m.role_type === 'DEPUTY') newLeadership.deputy = userData;
                        else if (m.role_type === 'PROXY1') newLeadership.proxy1 = userData;
                        else if (m.role_type === 'PROXY2') newLeadership.proxy2 = userData;
                    }
                    this.leadership = newLeadership;
                    // 強制觸發響應式更新
                    this.members = [...this.members];
                    this.leadership = { ...this.leadership };
                }
            } catch (err) {
                this.members = [];
                this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
            }
        },

        filterUsers() {
            const search = this.userSearch.toLowerCase().trim();
            if (!search) {
                this.filteredUsers = [...this.allUsers];
                return;
            }
            this.filteredUsers = this.allUsers.filter(u =>
                (u.display_name || '').toLowerCase().includes(search) ||
                (u.native_name || '').toLowerCase().includes(search) ||
                (u.english_name || '').toLowerCase().includes(search) ||
                (u.employee_id || '').toLowerCase().includes(search)
            );
        },

        // 選擇
        toggleExpand(group) { this.expandedNodes[group.id] = !this.expandedNodes[group.id]; },

        selectRoot() {
            this.selectedGroup = null;
            this.isCreating = false;
            this.members = [];
            this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
        },

        async selectGroup(group) {
            this.selectedGroup = group;
            this.isCreating = false;
            this.formData = {
                code: group.code,
                name: group.name,
                description: group.description || '',
                parent_id: group.parent_id || ''
            };
            await this.loadMembers(group.id);
        },

        startCreate() {
            const parentId = this.selectedGroup ? this.selectedGroup.id : '';
            this.isCreating = true;
            this.formData = { code: '', name: '', description: '', parent_id: parentId };
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
        },

        cancelEdit() {
            this.isCreating = false;
            if (this.selectedGroup) {
                this.formData = {
                    code: this.selectedGroup.code,
                    name: this.selectedGroup.name,
                    description: this.selectedGroup.description || '',
                    parent_id: this.selectedGroup.parent_id || ''
                };
            }
        },

        // CRUD
        async createGroup() {
            try {
                const res = await fetch('/api/units', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({
                        code: this.ciGetFinalCode(this.formData.code),
                        name: this.formData.name,
                        description: this.formData.description,
                        parent_id: this.formData.parent_id || null,
                        unit_type: 'GROUP'
                    })
                });
                if (res.ok) {
                    this.showToast('社群建立成功', 'success');
                    this.isCreating = false;
                    await this.loadGroups();
                    this.refreshJsTree();
                } else {
                    const data = await res.json();
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (err) { this.showToast('建立失敗', 'error'); }
        },

        async updateGroup() {
            if (!this.selectedGroup) return;
            try {
                const res = await fetch(`/api/units/${this.selectedGroup.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({
                        name: this.formData.name,
                        description: this.formData.description,
                        parent_id: this.formData.parent_id || null
                    })
                });
                if (res.ok) {
                    this.showToast('更新成功', 'success');
                    await this.loadGroups();
                    this.refreshJsTree();
                } else {
                    const data = await res.json();
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (err) { this.showToast('更新失敗', 'error'); }
        },

        async deleteGroup() {
            if (!this.selectedGroup) return;

            // 先檢查
            const checkRes = await fetch(`/api/units/${this.selectedGroup.id}?check_only=true&cascade=true`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
            const checkData = await checkRes.json();

            let msgs = [`確定刪除「${this.selectedGroup.name}」？`];
            if (checkData.children_count > 0) {
                msgs.push(`\n包含 ${checkData.children_count} 個子社群`);
            }
            if (checkData.members_count > 0) {
                msgs.push(`\n共 ${checkData.members_count} 位成員將被移除`);
            }

            if (!confirm(msgs.join(''))) return;

            try {
                const url = `/api/units/${this.selectedGroup.id}?cascade=true&confirm_members=true`;
                const res = await fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': getCsrfToken() } });
                const data = await res.json();

                if (res.ok) {
                    this.showToast(data.message || '刪除成功', 'success');
                    this.selectedGroup = null;
                    await this.loadGroups();
                    this.refreshJsTree();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (err) { this.showToast('刪除失敗', 'error'); }
        },

        // 拖拉：從右側拖入用戶
        dragStartUser(e, user) {
            this.draggedUser = user;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', user.id);
        },

        // 拖拉：成員
        dragStartMember(e, member) {
            this.draggedMember = member;
            e.dataTransfer.effectAllowed = 'move';
        },

        // 拖拉：管理層
        dragStartLeader(e, leader, type) {
            this.draggedLeader = leader;
            this.draggedLeaderType = type;
            e.dataTransfer.effectAllowed = 'move';
        },

        // Drop 到角色欄
        async dropToRole(e, roleType) {
            e.preventDefault();
            this.dragOverZone = null;
            if (!this.selectedGroup) return;

            // 決定要處理的用戶
            let userId = null;
            let existingMembership = null;

            if (this.draggedUser) {
                userId = this.draggedUser.id;
            } else if (this.draggedMember) {
                userId = this.draggedMember.user_secure_code;
                existingMembership = this.draggedMember;
            } else if (this.draggedLeader) {
                userId = this.draggedLeader.id;
                existingMembership = { id: this.draggedLeader.membershipId };
            } else if (this.draggedTreePerson) {
                userId = this.draggedTreePerson.id;
                if (this.draggedTreePerson.groupId === this.selectedGroup.id) {
                    existingMembership = { id: this.draggedTreePerson.membershipId };
                }
            }

            if (!userId) {
                this.clearDrag();
                return;
            }

            // 檢查是否已是此社群成員
            const existing = this.members.find(m => m.user_secure_code === userId);

            try {
                // 如果是唯一角色（團長/副團長/代理人），先將原本擔任者降級為團員
                if (['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(roleType)) {
                    const currentHolder = this.members.find(m => m.role_type === roleType);
                    if (currentHolder && currentHolder.user_secure_code !== userId) {
                        // 將原本的人降級為團員
                        await fetch(`/api/units/${this.selectedGroup.id}/cross-members/${currentHolder.id}`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                            body: JSON.stringify({ role_type: 'MEMBER' })
                        });
                    }
                }

                if (existing) {
                    // 已是成員，更新角色
                    const res = await fetch(`/api/units/${this.selectedGroup.id}/cross-members/${existing.id}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ role_type: roleType })
                    });
                    if (res.ok) {
                        this.showToast('角色已更新', 'success');
                    } else {
                        const data = await res.json();
                        this.showToast(data.error || '更新失敗', 'error');
                    }
                } else {
                    // 新增成員
                    const res = await fetch(`/api/units/${this.selectedGroup.id}/cross-members`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({
                            user_id: userId,
                            role_type: roleType
                        })
                    });
                    if (res.ok) {
                        this.showToast('已加入社群', 'success');
                    } else {
                        const data = await res.json();
                        this.showToast(data.error || '加入失敗', 'error');
                    }
                }

                await this.loadMembers(this.selectedGroup.id);
                if (this.showPeopleInTree) {
                    await this.refreshGroupPeople(this.selectedGroup.id);
                    this.refreshJsTree();
                }
            } catch (err) {
                this.showToast('操作失敗', 'error');
            }

            this.clearDrag();
        },

        // 移除成員（管理層）
        async removeMember(leader, type) {
            if (!this.selectedGroup || !leader) return;
            const userName = leader.native_name || leader.display_name || '此成員';
            if (!confirm(`確定將 ${userName} 移出社群？`)) return;

            try {
                const res = await fetch(`/api/units/${this.selectedGroup.id}/cross-members/${leader.membershipId}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                if (res.ok) {
                    this.showToast('已移出社群', 'success');
                    await this.loadMembers(this.selectedGroup.id);
                    if (this.showPeopleInTree) {
                        await this.refreshGroupPeople(this.selectedGroup.id);
                        this.refreshJsTree();
                    }
                } else {
                    const data = await res.json();
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (err) {
                this.showToast('移除失敗', 'error');
            }
        },

        // 移除團員
        async removeMemberDirect(member) {
            if (!this.selectedGroup) return;
            const userName = member.user?.native_name || member.user?.display_name || '此成員';
            if (!confirm(`確定將 ${userName} 移出社群？`)) return;

            try {
                const res = await fetch(`/api/units/${this.selectedGroup.id}/cross-members/${member.id}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                if (res.ok) {
                    this.showToast('已移出社群', 'success');
                    await this.loadMembers(this.selectedGroup.id);
                    if (this.showPeopleInTree) {
                        await this.refreshGroupPeople(this.selectedGroup.id);
                        this.refreshJsTree();
                    }
                } else {
                    const data = await res.json();
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (err) {
                this.showToast('移除失敗', 'error');
            }
        },

        async refreshGroupPeople(groupId) {
            const findAndUpdate = async (items) => {
                for (const group of items) {
                    if (group.id === groupId) {
                        const res = await fetch(`/api/units/${group.id}/cross-members`);
                        if (res.ok) {
                            const data = await res.json();
                            group._members = data.cross_members || [];
                        }
                        return true;
                    }
                    if (group.children && await findAndUpdate(group.children)) return true;
                }
                return false;
            };
            await findAndUpdate(this.groups);
            this.groups = [...this.groups];
        },

        clearDrag() {
            this.draggedUser = null;
            this.draggedMember = null;
            this.draggedLeader = null;
            this.draggedLeaderType = null;
            this.draggedTreePerson = null;
        },

        showToast(msg, type = 'success') {
            const toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
    };
}
