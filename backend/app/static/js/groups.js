'use strict';

/**
 * 社群設定頁 -- 使用獨立 Tree 元件 (取代 jstree+jQuery)
 *
 * 載入順序: beak-tree-model.js -> beak-tree.js -> beak-tree-drag.js -> beak-tree-lines-dom.js -> groups.js
 */

// ==================== 自訂 Renderer ====================
(function() {
    if (typeof BeakTree === 'undefined') return;
    var linesDom = BeakTree.renderers ? BeakTree.renderers['lines-dom'] : null;

    BeakTree.registerRenderer('group-tree', {
        renderTreeCell: function(node, ancestors, tree) {
            var cell = document.createElement('div');
            cell.className = 'bt-tree-cell bt-dom-cell';

            for (var i = 0; i < ancestors.length; i++) {
                var sp = document.createElement('span');
                sp.className = 'bt-indent bt-indent-blank';
                cell.appendChild(sp);
            }
            if (node.level > 0) {
                var br = document.createElement('span');
                br.className = 'bt-branch';
                cell.appendChild(br);
            }
            var model = tree._model;
            if (model.hasChildren(node.id)) {
                var tog = document.createElement('span');
                tog.className = 'bt-toggle';
                tog.classList.add(model.isExpanded(node.id) ? 'bt-toggle-expanded' : 'bt-toggle-collapsed');
                tog.textContent = model.isExpanded(node.id) ? '[-]' : '[+]';
                cell.appendChild(tog);
            } else {
                var leaf = document.createElement('span');
                leaf.className = 'bt-leaf-spacer';
                cell.appendChild(leaf);
            }

            var nodeType = node.data.type;
            if (nodeType === 'root') {
                var icon = document.createElement('span');
                icon.className = 'tg-node-icon root';
                icon.textContent = '\u25A0';
                cell.appendChild(icon);
            } else if (nodeType === 'ext_root') {
                var iconExt = document.createElement('span');
                iconExt.className = 'tg-node-icon ext-root';
                iconExt.textContent = '\u25A0';
                cell.appendChild(iconExt);
            } else if (nodeType === 'group') {
                var icon2 = document.createElement('span');
                icon2.className = 'tg-node-icon grp';
                icon2.textContent = '\u25C6';
                cell.appendChild(icon2);
            } else if (nodeType === 'person') {
                // 管理層: 團/副/代，外部廠商名字紅字警示
                // 一般成員: 員(EMPLOYEE) 或 外(EXTERNAL 紅底白字)
                var tag = document.createElement('span');
                var role = node.data.role;
                if (role === 'MANAGER') { tag.className = 'role-tag leader'; tag.textContent = '\u5718'; }
                else if (role === 'DEPUTY') { tag.className = 'role-tag leader'; tag.textContent = '\u526F'; }
                else if (role === 'PROXY1' || role === 'PROXY2') { tag.className = 'role-tag leader'; tag.textContent = '\u4EE3'; }
                else if (node.data.isExternal) { tag.className = 'ext-badge'; tag.textContent = '\u5916'; }
                else { tag.className = 'role-tag employee'; tag.textContent = '\u54E1'; }
                cell.appendChild(tag);
            }

            var lbl = document.createElement('span');
            lbl.className = 'bt-label';
            if (nodeType === 'person') {
                lbl.textContent = node.data.displayName || node.label;
                // 外部廠商擔任管理層: 名字紅字
                if (node.data.isExternal && ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(node.data.role)) {
                    lbl.style.color = '#dc3545';
                    lbl.style.fontWeight = 'bold';
                }
            } else {
                lbl.textContent = node.label;
            }
            cell.appendChild(lbl);

            return cell;
        },
        afterRender: function(tree) {
            if (linesDom && linesDom.afterRender) {
                linesDom.afterRender(tree);
            }
        }
    });
})();


function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}


function groupManager() {
    var __cfg = window.__GROUPS_CONFIG || {};

    return {
        ...codeInputMixin('group'),
        isAdmin: __cfg.isAdmin || false,

        // 資料
        groups: [],
        allUsers: [],
        filteredUsers: [],
        userSearch: '',
        selectedGroup: null,
        members: [],
        leadership: { manager: null, deputy: null, proxy1: null, proxy2: null },
        showPeopleInTree: false,
        isCreating: false,
        formData: { code: '', name: '', description: '', parent_id: '' },
        totalUsers: 0,

        // Tree 實例
        _tree: null,

        // DnD 狀態
        dragOverZone: null,
        _dragData: null,
        draggedUser: null,
        draggedMember: null,
        draggedLeader: null,
        draggedLeaderType: null,

        // ==================== 計算屬性 ====================

        get regularMembers() {
            // 排序: 外人在前，企業成員在後
            var filtered = this.members.filter(function(m) {
                return !['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(m.role_type);
            });
            return filtered.sort(function(a, b) {
                var aExt = a.user?.user_type === 'EXTERNAL' ? 0 : 1;
                var bExt = b.user?.user_type === 'EXTERNAL' ? 0 : 1;
                if (aExt !== bExt) return aExt - bExt;
                var aName = a.user?.native_name || a.user?.display_name || '';
                var bName = b.user?.native_name || b.user?.display_name || '';
                return aName.localeCompare(bName);
            });
        },

        get totalCount() {
            return this.members.length;
        },

        get allGroupsFlat() {
            var result = [];
            var flatten = function(items, level) {
                for (var i = 0; i < items.length; i++) {
                    result.push(Object.assign({}, items[i], { level: level }));
                    if (items[i].children && items[i].children.length > 0) flatten(items[i].children, level + 1);
                }
            };
            flatten(this.groups, 0);
            return result;
        },

        get availableParents() {
            if (this.isCreating || !this.selectedGroup) return this.allGroupsFlat;
            var excludeIds = new Set([this.selectedGroup.id]);
            var collectDescendants = function(items) {
                for (var i = 0; i < items.length; i++) {
                    excludeIds.add(items[i].id);
                    if (items[i].children) collectDescendants(items[i].children);
                }
            };
            var sel = this.findGroupById(this.selectedGroup.id);
            if (sel && sel.children) collectDescendants(sel.children);
            return this.allGroupsFlat.filter(function(g) { return !excludeIds.has(g.id); });
        },

        get leaderIds() {
            return [
                this.leadership.manager?.id,
                this.leadership.deputy?.id,
                this.leadership.proxy1?.id,
                this.leadership.proxy2?.id
            ].filter(Boolean);
        },

        isMember: function(userId) {
            return this.members.some(function(m) { return m.user_secure_code === userId; });
        },

        // ==================== 初始化 ====================

        async init() {
            // 統一使用 group-member-candidates (含 EMPLOYEE + EXTERNAL)
            try {
                var res = await fetch('/bp/api/units/group-member-candidates?per_page=1000');
                if (res.ok) {
                    var data = await res.json();
                    this.allUsers = (data.users || []).filter(function(u) {
                        return !u.is_deleted && u.is_active !== false &&
                            (u.user_type === 'EMPLOYEE' || u.user_type === 'EXTERNAL');
                    });
                    this.filteredUsers = this.allUsers.slice();
                    this.totalUsers = this.allUsers.length;
                }
            } catch (e) {}

            if (this.totalUsers >= 30) {
                this.showPeopleInTree = false;
            } else {
                this.showPeopleInTree = true;
            }

            await this.loadGroups();
            this.buildTree();
        },

        // ==================== API 載入 ====================

        async loadGroups() {
            try {
                var res = await fetch('/bp/api/units/groups?tree=true');
                var data = await res.json();
                if (res.ok) {
                    this.groups = data.units || [];
                    if (this.showPeopleInTree) await this.loadAllPeople();
                }
            } catch (err) {
                this.showToast('載入失敗', 'error');
            }
        },

        async loadAllPeople() {
            var self = this;
            var loadForGroup = async function(group) {
                try {
                    var res = await fetch('/bp/api/units/' + group.id + '/cross-members');
                    if (res.ok) {
                        var data = await res.json();
                        group._members = data.cross_members || [];
                    }
                } catch (e) {}
                if (group.children) {
                    for (var i = 0; i < group.children.length; i++) {
                        await loadForGroup(group.children[i]);
                    }
                }
            };
            for (var i = 0; i < this.groups.length; i++) {
                await loadForGroup(this.groups[i]);
            }
        },

        async loadMembers(groupId) {
            try {
                var res = await fetch('/bp/api/units/' + groupId + '/cross-members');
                var data = await res.json();
                if (res.ok) {
                    var rawMembers = data.cross_members || [];
                    this.members = rawMembers;

                    var newLeadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
                    for (var i = 0; i < rawMembers.length; i++) {
                        var m = rawMembers[i];
                        var userData = {
                            id: m.user_secure_code,
                            membershipId: m.id,
                            employee_id: m.user?.employee_id,
                            native_name: m.user?.native_name,
                            display_name: m.user?.display_name,
                            english_name: m.user?.english_name,
                            user_type: m.user?.user_type
                        };
                        if (m.role_type === 'MANAGER') newLeadership.manager = userData;
                        else if (m.role_type === 'DEPUTY') newLeadership.deputy = userData;
                        else if (m.role_type === 'PROXY1') newLeadership.proxy1 = userData;
                        else if (m.role_type === 'PROXY2') newLeadership.proxy2 = userData;
                    }
                    this.leadership = newLeadership;
                    this.members = rawMembers.slice();
                    this.leadership = Object.assign({}, this.leadership);
                }
            } catch (err) {
                this.members = [];
                this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
            }
        },

        filterUsers: function() {
            var search = this.userSearch.toLowerCase().trim();
            if (!search) {
                this.filteredUsers = this.allUsers.slice();
                return;
            }
            this.filteredUsers = this.allUsers.filter(function(u) {
                return (u.display_name || '').toLowerCase().includes(search) ||
                    (u.native_name || '').toLowerCase().includes(search) ||
                    (u.english_name || '').toLowerCase().includes(search) ||
                    (u.employee_id || '').toLowerCase().includes(search);
            });
        },

        // ==================== Tree 建構 ====================

        buildTree: function() {
            var container = document.getElementById('group-tree');
            if (!container) return;

            if (this._tree) {
                this._tree.destroy();
                this._tree = null;
            }

            var treeData = this._buildTreeData();
            var self = this;

            this._tree = new BeakTree(container, {
                treeMode: 'group-tree',
                data: treeData,
                draggable: this.isAdmin,
                hideRoot: false,
                hideHeader: true,
                maxExpanded: 500,
                onNodeClick: function(id, node) {
                    self._onNodeClick(id, node);
                },
                onNodeMoved: function(nodeId, newParentId, newIndex, node) {
                    self._onNodeMoved(nodeId, newParentId, newIndex, node);
                },
                canDrop: function(sourceNode, targetNode, action) {
                    // 只限制群組節點的跨樹拖拉
                    if (sourceNode.data.type !== 'group') return true;
                    // 人員節點不受此規則限制（由 dropToRole 處理）
                    if (sourceNode.data.type === 'person') return true;

                    // 判斷來源與目標的樹系
                    var srcExt = self._isInExternalTree(sourceNode.id);
                    var tgtExt;
                    if (action === 'inside') {
                        tgtExt = self._isInExternalTree(targetNode.id);
                    } else {
                        // before/after: 目標的 parent 決定樹系
                        tgtExt = targetNode.parentId
                            ? self._isInExternalTree(targetNode.parentId)
                            : (targetNode.data.type === 'ext_root');
                    }

                    // 跨樹系 → 禁止
                    if (srcExt !== tgtExt) return false;
                    return true;
                }
            });

            if (this.isAdmin) this._attachExternalDrop();
        },

        _buildTreeData: function() {
            var self = this;
            var rootLabel = __cfg.orgName || '\u4F01\u696D';

            var build = function(items) {
                return items.map(function(item) {
                    var node = {
                        id: item.id,
                        label: item.name,
                        expanded: true,
                        children: [],
                        data: { type: 'group', code: item.code, name: item.name, parent_id: item.parent_id || null, description: item.description || '', is_system_unit: item.is_system_unit || false }
                    };
                    // 成員模式：加入人員節點 (排序: 團長→副團長→外人→企業成員)
                    if (self.showPeopleInTree && item._members) {
                        var sorted = self._sortMembers(item._members);
                        for (var i = 0; i < sorted.length; i++) {
                            node.children.push(self._personNode(sorted[i], item.id));
                        }
                    }
                    // 子社群
                    if (item.children && item.children.length > 0) {
                        node.children = node.children.concat(build(item.children));
                    }
                    return node;
                });
            };

            // 分離外部廠商群組與內部群組
            var extGroups = [];
            var intGroups = [];
            for (var i = 0; i < this.groups.length; i++) {
                var g = this.groups[i];
                if (g.code === 'EXTERNAL_VENDORS' || g.code === 'external_vendors') {
                    extGroups.push(g);
                } else {
                    intGroups.push(g);
                }
            }

            var roots = [{
                id: 'root',
                label: rootLabel,
                expanded: true,
                children: build(intGroups),
                data: { type: 'root' }
            }];

            // 外部廠商樹：以 EXTERNAL_VENDORS 群組為根
            if (extGroups.length > 0) {
                var extBuilt = build(extGroups);
                // 直接用第一個 EXTERNAL_VENDORS 群組節點作為第二根
                roots.push({
                    id: extBuilt[0].id,
                    label: extBuilt[0].label,
                    expanded: true,
                    children: extBuilt[0].children,
                    data: { type: 'ext_root', code: extBuilt[0].data.code, name: extBuilt[0].data.name, description: extBuilt[0].data.description, is_system_unit: true }
                });
            }

            return roots;
        },

        _personNode: function(member, groupId) {
            var name = member.user?.native_name || member.user?.display_name || '?';
            var role = member.role_type || 'MEMBER';
            var tagClass = ['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(role) ? 'leader' : 'employee';
            var isExternal = member.user?.user_type === 'EXTERNAL';
            return {
                id: 'p_' + role + '_' + groupId + '_' + member.user_secure_code,
                label: name,
                children: [],
                data: {
                    type: 'person',
                    userId: member.user_secure_code,
                    groupId: groupId,
                    role: role,
                    tagClass: tagClass,
                    displayName: name,
                    isExternal: isExternal,
                    membershipId: member.id
                }
            };
        },

        // 成員排序: 團長→副團長→代理人→外人→企業成員
        _sortMembers: function(members) {
            var order = { MANAGER: 0, DEPUTY: 1, PROXY1: 2, PROXY2: 3 };
            return members.slice().sort(function(a, b) {
                var aRole = order[a.role_type] !== undefined ? order[a.role_type] : 10;
                var bRole = order[b.role_type] !== undefined ? order[b.role_type] : 10;
                if (aRole !== bRole) return aRole - bRole;
                // 同為一般成員: 外人在前
                var aExt = a.user?.user_type === 'EXTERNAL' ? 0 : 1;
                var bExt = b.user?.user_type === 'EXTERNAL' ? 0 : 1;
                if (aExt !== bExt) return aExt - bExt;
                var aName = a.user?.native_name || a.user?.display_name || '';
                var bName = b.user?.native_name || b.user?.display_name || '';
                return aName.localeCompare(bName);
            });
        },

        // ==================== 樹系判斷 ====================

        /**
         * 判斷 Tree 節點是否屬於 EXTERNAL_VENDORS 樹系。
         * 沿 parent chain 往上走，碰到 ext_root 回傳 true，碰到 'root' 回傳 false。
         */
        _isInExternalTree: function(nodeId) {
            if (!this._tree) return false;
            var model = this._tree._model;
            var cur = model.getNode(nodeId);
            while (cur) {
                if (cur.data.type === 'ext_root') return true;
                if (cur.id === 'root') return false;
                cur = cur.parentId ? model.getNode(cur.parentId) : null;
            }
            return false;
        },

        /**
         * 用 groups 原始資料判斷一個群組 ID 是否屬於 EXTERNAL_VENDORS 子樹。
         * 不依賴 _tree 實例，適合在右側面板拖入時使用。
         */
        _isGroupInExternalVendors: function(groupId) {
            var self = this;
            var _find = function(items) {
                for (var i = 0; i < items.length; i++) {
                    if (items[i].id === groupId) return true;
                    if (items[i].children && _find(items[i].children)) return true;
                }
                return false;
            };
            // 在 groups 中找 EXTERNAL_VENDORS 根，檢查 groupId 是否在其子樹
            for (var i = 0; i < this.groups.length; i++) {
                var g = this.groups[i];
                if (g.code === 'EXTERNAL_VENDORS' || g.code === 'external_vendors') {
                    if (g.id === groupId) return true;
                    if (g.children && _find(g.children)) return true;
                }
            }
            return false;
        },

        // ==================== Tree 事件 ====================

        _onNodeClick: function(id, node) {
            if (id === 'root') {
                this.selectRoot();
                return;
            }
            if (node.data.type === 'ext_root') {
                this.selectGroup(id);
                return;
            }
            if (node.data.type === 'group') {
                this.selectGroup(id);
            }
            // 選取標示
            var container = document.getElementById('group-tree');
            if (container) {
                container.querySelectorAll('.tg-selected').forEach(function(el) { el.classList.remove('tg-selected'); });
                var row = container.querySelector('tr[data-id="' + id + '"]');
                if (row) row.classList.add('tg-selected');
            }
        },

        async _onNodeMoved(nodeId, newParentId, newIndex, node) {
            if (node.data.type === 'group' && this.isAdmin) {
                var parentId = (newParentId === 'root') ? null : newParentId;
                try {
                    var res = await fetch('/bp/api/units/' + nodeId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ parent_id: parentId })
                    });
                    if (res.ok) {
                        this.showToast('社群已移動', 'success');
                    } else {
                        var data = await res.json();
                        this.showToast(data.error || '移動失敗', 'error');
                    }
                } catch (e) { this.showToast('移動失敗', 'error'); }
                await this._refreshAll();
            } else {
                // 人員節點或非 admin: 還原
                this.buildTree();
            }
        },

        // ==================== 選擇 / CRUD ====================

        selectRoot: function() {
            this.selectedGroup = null;
            this.isCreating = false;
            this.members = [];
            this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
        },

        async selectGroup(groupData) {
            var id = groupData.id || groupData;
            var group = this.findGroupById(id);
            if (!group) group = groupData;
            this.selectedGroup = group;
            this.isCreating = false;
            this.formData = {
                code: group.code || '',
                name: group.name || '',
                description: group.description || '',
                parent_id: group.parent_id || ''
            };
            await this.loadMembers(id);
        },

        startCreate: function() {
            var parentId = this.selectedGroup ? this.selectedGroup.id : '';
            this.isCreating = true;
            this.formData = { code: '', name: '', description: '', parent_id: parentId };
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
        },

        cancelEdit: function() {
            this.isCreating = false;
            if (this.selectedGroup) {
                this.formData = {
                    code: this.selectedGroup.code || '',
                    name: this.selectedGroup.name || '',
                    description: this.selectedGroup.description || '',
                    parent_id: this.selectedGroup.parent_id || ''
                };
            }
        },

        async createGroup() {
            try {
                var res = await fetch('/bp/api/units/', {
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
                    await this._refreshAll();
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (err) { this.showToast('建立失敗', 'error'); }
        },

        async updateGroup() {
            if (!this.selectedGroup) return;
            try {
                var res = await fetch('/bp/api/units/' + this.selectedGroup.id, {
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
                    await this._refreshAll();
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '更新失敗', 'error');
                }
            } catch (err) { this.showToast('更新失敗', 'error'); }
        },

        async deleteGroup() {
            if (!this.selectedGroup) return;
            if (this.selectedGroup.is_system_unit) {
                this.showToast('系統保留群組不可刪除', 'error');
                return;
            }
            try {
                var checkRes = await fetch('/bp/api/units/' + this.selectedGroup.id + '?check_only=true&cascade=true', {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                var checkData = await checkRes.json();

                var msgs = ['\u78BA\u5B9A\u522A\u9664\u300C' + this.selectedGroup.name + '\u300D\uFF1F'];
                if (checkData.children_count > 0) msgs.push('\n\u5305\u542B ' + checkData.children_count + ' \u500B\u5B50\u793E\u7FA4');
                if (checkData.members_count > 0) msgs.push('\n\u5171 ' + checkData.members_count + ' \u4F4D\u6210\u54E1\u5C07\u88AB\u79FB\u9664');

                if (!confirm(msgs.join(''))) return;

                var url = '/bp/api/units/' + this.selectedGroup.id + '?cascade=true&confirm_members=true';
                var res = await fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': getCsrfToken() } });
                var data = await res.json();
                if (res.ok) {
                    this.showToast(data.message || '刪除成功', 'success');
                    this.selectedGroup = null;
                    await this._refreshAll();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (err) { this.showToast('刪除失敗', 'error'); }
        },

        findGroupById: function(id) {
            var find = function(items) {
                for (var i = 0; i < items.length; i++) {
                    if (items[i].id === id) return items[i];
                    if (items[i].children) {
                        var f = find(items[i].children);
                        if (f) return f;
                    }
                }
                return null;
            };
            return find(this.groups);
        },

        // ==================== DnD: 拖動開始 ====================

        dragStartUser: function(e, user) {
            this.draggedUser = user;
            this._dragData = { source: 'users-panel', type: 'person', person: user };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', user.id);
        },

        dragStartMember: function(e, member) {
            this.draggedMember = member;
            this._dragData = { source: 'member-area', type: 'person', person: member };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', member.id);
        },

        dragStartLeader: function(e, leader, type) {
            this.draggedLeader = leader;
            this.draggedLeaderType = type;
            this._dragData = { source: 'member-area', type: 'person', person: leader, role: type };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', leader.id);
        },

        onZoneDragOver: function(e, zone) {
            if (this._dragData || this.draggedUser || this.draggedMember || this.draggedLeader) {
                this.dragOverZone = zone;
            }
        },

        clearDrag: function() {
            this.draggedUser = null;
            this.draggedMember = null;
            this.draggedLeader = null;
            this.draggedLeaderType = null;
            this._dragData = null;
            this.dragOverZone = null;
        },

        // ==================== DnD: Drop 處理 ====================

        async dropToRole(e, roleType) {
            e.preventDefault();
            e.stopPropagation();
            this.dragOverZone = null;
            if (!this.selectedGroup) { this.clearDrag(); return; }

            // 判斷被拖入的用戶
            var userId = null;
            if (this.draggedUser) {
                userId = this.draggedUser.id;
            } else if (this.draggedMember) {
                userId = this.draggedMember.user_secure_code;
            } else if (this.draggedLeader) {
                userId = this.draggedLeader.id;
            }
            if (!userId) { this.clearDrag(); return; }

            // EXTERNAL 用戶不可加入企業樹群組
            var dragUserType = null;
            if (this.draggedUser) {
                dragUserType = this.draggedUser.user_type;
            } else if (this.draggedMember) {
                dragUserType = this.draggedMember.user?.user_type;
            } else if (this.draggedLeader) {
                dragUserType = this.draggedLeader.user_type;
            }
            if (dragUserType === 'EXTERNAL' && !this._isGroupInExternalVendors(this.selectedGroup.id)) {
                this.showToast('外部人員不可加入企業群組', 'error');
                this.clearDrag();
                return;
            }

            var existing = this.members.find(function(m) { return m.user_secure_code === userId; });

            try {
                // 唯一角色（團長/副團長/代理人）：先將現任降級為團員
                if (['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(roleType)) {
                    var currentHolder = this.members.find(function(m) { return m.role_type === roleType; });
                    if (currentHolder && currentHolder.user_secure_code !== userId) {
                        await fetch('/bp/api/units/' + this.selectedGroup.id + '/cross-members/' + currentHolder.id, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                            body: JSON.stringify({ role_type: 'MEMBER' })
                        });
                    }
                }

                if (existing) {
                    // 已是成員：更新角色
                    var res = await fetch('/bp/api/units/' + this.selectedGroup.id + '/cross-members/' + existing.id, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ role_type: roleType })
                    });
                    if (res.ok) {
                        this.showToast('角色已更新', 'success');
                    } else {
                        var errData = await res.json();
                        this.showToast(errData.error || '更新失敗', 'error');
                    }
                } else {
                    // 新增成員
                    var res2 = await fetch('/bp/api/units/' + this.selectedGroup.id + '/cross-members', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ user_id: userId, role_type: roleType })
                    });
                    if (res2.ok) {
                        this.showToast('已加入社群', 'success');
                    } else {
                        var errData2 = await res2.json();
                        this.showToast(errData2.error || '加入失敗', 'error');
                    }
                }

                await this.loadMembers(this.selectedGroup.id);
                if (this.showPeopleInTree) {
                    await this._refreshGroupPeople(this.selectedGroup.id);
                    this.buildTree();
                }
            } catch (err) {
                this.showToast('操作失敗', 'error');
            }

            this.clearDrag();
        },

        // 移除管理層成員
        async removeMember(leader, type) {
            if (!this.selectedGroup || !leader) return;
            var userName = leader.native_name || leader.display_name || '此成員';
            if (!confirm('\u78BA\u5B9A\u5C07 ' + userName + ' \u79FB\u51FA\u793E\u7FA4\uFF1F')) return;

            try {
                var res = await fetch('/bp/api/units/' + this.selectedGroup.id + '/cross-members/' + leader.membershipId, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                if (res.ok) {
                    this.showToast('已移出社群', 'success');
                    await this.loadMembers(this.selectedGroup.id);
                    if (this.showPeopleInTree) {
                        await this._refreshGroupPeople(this.selectedGroup.id);
                        this.buildTree();
                    }
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (err) { this.showToast('移除失敗', 'error'); }
        },

        // 移除團員
        async removeMemberDirect(member) {
            if (!this.selectedGroup) return;
            var userName = member.user?.native_name || member.user?.display_name || '此成員';
            if (!confirm('\u78BA\u5B9A\u5C07 ' + userName + ' \u79FB\u51FA\u793E\u7FA4\uFF1F')) return;

            try {
                var res = await fetch('/bp/api/units/' + this.selectedGroup.id + '/cross-members/' + member.id, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                if (res.ok) {
                    this.showToast('已移出社群', 'success');
                    await this.loadMembers(this.selectedGroup.id);
                    if (this.showPeopleInTree) {
                        await this._refreshGroupPeople(this.selectedGroup.id);
                        this.buildTree();
                    }
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (err) { this.showToast('移除失敗', 'error'); }
        },

        // ==================== 右側面板 -> Tree 拖入 (admin) ====================

        _attachExternalDrop: function() {
            var container = document.getElementById('group-tree');
            if (!container) return;
            var self = this;

            container.addEventListener('dragover', function(e) {
                if (!self.draggedUser) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                container.querySelectorAll('.bk-tree-drop-highlight').forEach(function(el) { el.classList.remove('bk-tree-drop-highlight'); });
                var tr = e.target.closest('tr.bt-row');
                if (tr) {
                    var nodeId = tr.dataset.id;
                    var node = self._tree._model.getNode(nodeId);
                    if (node && (node.data.type === 'group' || node.data.type === 'ext_root')) {
                        // EXTERNAL 用戶不可拖入企業樹群組
                        var userType = self.draggedUser.user_type;
                        var targetIsExt = self._isInExternalTree(nodeId);
                        if (userType === 'EXTERNAL' && !targetIsExt) {
                            e.dataTransfer.dropEffect = 'none';
                            return;
                        }
                        tr.classList.add('bk-tree-drop-highlight');
                    }
                }
            });

            container.addEventListener('dragleave', function(e) {
                var tr = e.target.closest('tr.bt-row');
                if (tr) tr.classList.remove('bk-tree-drop-highlight');
            });

            container.addEventListener('drop', async function(e) {
                e.preventDefault();
                container.querySelectorAll('.bk-tree-drop-highlight').forEach(function(el) { el.classList.remove('bk-tree-drop-highlight'); });
                var tr = e.target.closest('tr.bt-row');
                if (!tr || !self.draggedUser) return;
                var targetId = tr.dataset.id;
                var targetNode = self._tree._model.getNode(targetId);
                if (!targetNode || (targetNode.data.type !== 'group' && targetNode.data.type !== 'ext_root')) return;

                // EXTERNAL 用戶不可加入企業樹群組
                var userType = self.draggedUser.user_type;
                var targetIsExt = self._isInExternalTree(targetId);
                if (userType === 'EXTERNAL' && !targetIsExt) {
                    self.showToast('外部人員不可加入企業群組', 'error');
                    self.clearDrag();
                    return;
                }

                var userId = self.draggedUser.id;
                try {
                    var res = await fetch('/bp/api/units/' + targetId + '/cross-members', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ user_id: userId, role_type: 'MEMBER' })
                    });
                    if (res.ok) {
                        var group = self.findGroupById(targetId);
                        self.showToast('已加入 ' + (group?.name || targetId), 'success');
                    } else {
                        var errData = await res.json();
                        self.showToast(errData.error || '加入失敗', 'error');
                    }
                } catch (err) { self.showToast('加入失敗', 'error'); }

                // 如果拖入的社群是當前選取的社群，重新載入成員
                if (self.selectedGroup && self.selectedGroup.id === targetId) {
                    await self.loadMembers(targetId);
                }
                if (self.showPeopleInTree) {
                    await self._refreshGroupPeople(targetId);
                    self.buildTree();
                }
                self.clearDrag();
            });
        },

        // ==================== 模式切換 ====================

        switchToGroupMode: function() {
            this.showPeopleInTree = false;
            this.buildTree();
        },

        async switchToDetailMode() {
            this.showPeopleInTree = true;
            var firstGroup = this.groups[0];
            if (firstGroup && !firstGroup._members) {
                await this.loadAllPeople();
            }
            this.buildTree();
        },

        // ==================== 工具函式 ====================

        async _refreshGroupPeople(groupId) {
            var self = this;
            var findAndUpdate = async function(items) {
                for (var i = 0; i < items.length; i++) {
                    if (items[i].id === groupId) {
                        var res = await fetch('/bp/api/units/' + items[i].id + '/cross-members');
                        if (res.ok) {
                            var data = await res.json();
                            items[i]._members = data.cross_members || [];
                        }
                        return true;
                    }
                    if (items[i].children && await findAndUpdate(items[i].children)) return true;
                }
                return false;
            };
            await findAndUpdate(this.groups);
            this.groups = this.groups.slice();
        },

        async _refreshAll() {
            await this.loadGroups();
            if (this.selectedGroup) {
                await this.loadMembers(this.selectedGroup.id);
            }
            this.buildTree();
            if (this.selectedGroup) {
                var self = this;
                this.$nextTick(function() {
                    var container = document.getElementById('group-tree');
                    if (container) {
                        var row = container.querySelector('tr[data-id="' + self.selectedGroup.id + '"]');
                        if (row) row.classList.add('tg-selected');
                    }
                });
            }
        },

        showToast: function(msg, type) {
            type = type || 'success';
            var toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(function() { toast.remove(); }, 3000);
        }
    };
}
