'use strict';

/**
 * 部門設定頁 — 使用獨立 Tree 元件 (取代 jstree+jQuery)
 *
 * 載入順序: tree-model.js → tree.js → tree-drag.js → tree-lines-dom.js → departments.js
 */

// ==================== 自訂 Renderer ====================
(function() {
    if (typeof Tree === 'undefined') return;
    var linesDom = Tree.renderers ? Tree.renderers['lines-dom'] : null;

    Tree.registerRenderer('dept-tree', {
        renderTreeCell: function(node, ancestors, tree) {
            var cell = document.createElement('div');
            cell.className = 'tg-tree-cell tg-dom-cell';

            for (var i = 0; i < ancestors.length; i++) {
                var sp = document.createElement('span');
                sp.className = 'tg-indent tg-indent-blank';
                cell.appendChild(sp);
            }
            if (node.level > 0) {
                var br = document.createElement('span');
                br.className = 'tg-branch';
                cell.appendChild(br);
            }
            var model = tree._model;
            if (model.hasChildren(node.id)) {
                var tog = document.createElement('span');
                tog.className = 'tg-toggle treegrid-toggle';
                tog.classList.add(model.isExpanded(node.id) ? 'tg-toggle-expanded' : 'tg-toggle-collapsed');
                tog.textContent = model.isExpanded(node.id) ? '[-]' : '[+]';
                cell.appendChild(tog);
            } else {
                var leaf = document.createElement('span');
                leaf.className = 'tg-leaf-spacer';
                cell.appendChild(leaf);
            }

            var nodeType = node.data.type;
            if (nodeType === 'root') {
                var icon = document.createElement('span');
                icon.className = 'tg-node-icon root';
                icon.textContent = '\u25A0';
                cell.appendChild(icon);
            } else if (nodeType === 'dept') {
                var icon2 = document.createElement('span');
                icon2.className = 'tg-node-icon dept';
                icon2.textContent = '\u25A1';
                cell.appendChild(icon2);
            } else if (nodeType === 'person') {
                var tag = document.createElement('span');
                tag.className = 'role-tag ' + (node.data.tagClass || 'employee');
                var roleLabels = { manager: '\u4E3B', deputy: '\u526F', proxy1: '\u4EE3', proxy2: '\u4EE3', member: '\u54E1' };
                tag.textContent = roleLabels[node.data.role] || '\u54E1';
                cell.appendChild(tag);
            }

            var lbl = document.createElement('span');
            lbl.className = 'tg-label';
            lbl.textContent = (nodeType === 'person') ? (node.data.displayName || node.label) : node.label;
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


function departmentManager() {
    return {
        ...codeInputMixin('department'),

        // 資料
        departments: [],
        allUsers: [],
        unassignedUsers: [],
        selectedDept: null,
        members: [],
        leadership: { manager: null, deputy: null, proxy1: null, proxy2: null },
        crossMembers: [],
        showPeopleInTree: false,
        isCreating: false,
        formData: { code: '', name: '', parent_id: '' },
        totalUsers: 0,

        // 跨部門手動新增
        newCrossMember: { user_id: '', role_type: 'MEMBER' },

        // Tree 實例
        _tree: null,

        // DnD 狀態
        dragOverZone: null,
        _dragData: null,        // 外部面板拖放: { source, type, person, role, deptId }
        draggedMember: null,    // 中間面板拖出的成員
        draggedLeader: null,    // 中間面板拖出的管理層
        draggedLeaderType: null,
        draggedUser: null,      // 右側未分配拖出

        // ==================== 計算屬性 ====================

        get leaderIds() {
            return [this.leadership.manager?.id, this.leadership.deputy?.id,
                    this.leadership.proxy1?.id, this.leadership.proxy2?.id].filter(Boolean);
        },

        get regularMembers() {
            return this.members.filter(m => !this.leaderIds.includes(m.id));
        },

        get membersExcludeLeaders() { return this.regularMembers; },

        get totalCount() {
            return this.leaderIds.length + this.regularMembers.length;
        },

        get allDepartmentsFlat() {
            var result = [];
            var flatten = (items, level) => {
                for (var item of items) {
                    result.push({ ...item, level });
                    if (item.children?.length > 0) flatten(item.children, level + 1);
                }
            };
            flatten(this.departments, 0);
            return result;
        },

        get availableParents() {
            if (this.isCreating || !this.selectedDept) return this.allDepartmentsFlat;
            var excludeIds = new Set([this.selectedDept.id]);
            var collectDescendants = (items) => {
                for (var item of items) {
                    excludeIds.add(item.id);
                    if (item.children) collectDescendants(item.children);
                }
            };
            var dept = this.findDeptById(this.selectedDept.id);
            if (dept && dept.children) collectDescendants(dept.children);
            return this.allDepartmentsFlat.filter(d => !excludeIds.has(d.id));
        },

        get availableCrossUsers() {
            if (!this.selectedDept) return [];
            var memberIds = new Set(this.members.map(m => m.id));
            var crossIds = new Set(this.crossMembers.map(cm => cm.user_secure_code));
            return this.allUsers.filter(u =>
                !memberIds.has(u.id) && !crossIds.has(u.id)
            );
        },

        // ==================== 初始化 ====================

        async init() {
            try {
                var res = await fetch('/api/users');
                if (res.ok) {
                    var data = await res.json();
                    this.allUsers = data.users || [];
                    this.totalUsers = this.allUsers.length;
                }
            } catch (e) {}

            if (this.totalUsers >= 30) {
                this.showPeopleInTree = false;
            } else {
                this.showPeopleInTree = true;
            }

            await Promise.all([
                this.loadDepartments(),
                this.loadUnassignedUsers()
            ]);
            this.buildTree();
        },

        // ==================== API 載入 ====================

        async loadDepartments() {
            try {
                var res = await fetch('/api/units/departments?tree=true');
                var data = await res.json();
                if (res.ok) {
                    this.departments = data.units || [];
                    if (this.showPeopleInTree) await this.loadAllPeople();
                }
            } catch (err) {
                this.showToast('載入失敗', 'error');
            }
        },

        async loadAllPeople() {
            var load = async (dept) => {
                try {
                    var [mRes, lRes] = await Promise.all([
                        fetch(`/api/units/${dept.id}/members`),
                        fetch(`/api/units/${dept.id}/leadership`)
                    ]);
                    if (mRes.ok) dept._members = (await mRes.json()).members || [];
                    if (lRes.ok) dept._leadership = await lRes.json();
                } catch (e) {}
                if (dept.children) {
                    for (var child of dept.children) await load(child);
                }
            };
            for (var dept of this.departments) await load(dept);
        },

        async loadUnassignedUsers() {
            try {
                var res = await fetch('/api/units/unassigned-users');
                var data = await res.json();
                if (res.ok) this.unassignedUsers = data.users || [];
            } catch (err) {}
        },

        async loadMembers(deptId) {
            try {
                var res = await fetch(`/api/units/${deptId}/members`);
                var data = await res.json();
                this.members = res.ok ? data.members || [] : [];
            } catch (err) { this.members = []; }
        },

        async loadLeadership(deptId) {
            try {
                var res = await fetch(`/api/units/${deptId}/leadership`);
                var data = await res.json();
                if (res.ok) this.leadership = data;
            } catch (err) {
                this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
            }
        },

        async loadCrossMembers(deptId) {
            try {
                var res = await fetch(`/api/units/${deptId}/cross-members`);
                var data = await res.json();
                if (res.ok) {
                    this.crossMembers = (data.cross_members || []).map(cm => ({
                        ...cm,
                        is_leader: ['MANAGER', 'DEPUTY'].includes(cm.role_type)
                    }));
                }
            } catch (err) { this.crossMembers = []; }
        },

        // ==================== Tree 建構 ====================

        buildTree() {
            var container = document.getElementById('dept-tree');
            if (!container) return;

            if (this._tree) {
                this._tree.destroy();
                this._tree = null;
            }

            var treeData = this._buildTreeData();
            var self = this;
            var cgName = window.__DEPT_CONFIG?.conglomerateName || '';

            this._tree = new Tree(container, {
                treeMode: 'dept-tree',
                data: treeData,
                draggable: true,
                hideRoot: false,
                hideHeader: !cgName,
                headerText: cgName,
                maxExpanded: 500,
                onNodeClick: function(id, node) {
                    self._onNodeClick(id, node);
                },
                onNodeMoved: function(nodeId, newParentId, newIndex, node) {
                    self._onNodeMoved(nodeId, newParentId, newIndex, node);
                }
            });

            this._attachExternalDrop();
        },

        _buildTreeData() {
            var self = this;
            var rootLabel = window.__DEPT_CONFIG?.orgName || '\u4F01\u696D';
            var build = (items) => items.map(item => {
                var node = {
                    id: item.id,
                    label: item.name,
                    expanded: true,
                    children: [],
                    data: { type: 'dept', code: item.code, name: item.name, parent_id: item.parent_id || null }
                };
                if (self.showPeopleInTree && item._leadership) {
                    var l = item._leadership;
                    if (l.manager) node.children.push(self._personNode(l.manager, item.id, 'manager', 'leader'));
                    if (l.deputy)  node.children.push(self._personNode(l.deputy,  item.id, 'deputy',  'leader'));
                    if (l.proxy1)  node.children.push(self._personNode(l.proxy1,  item.id, 'proxy1',  'leader'));
                    if (l.proxy2)  node.children.push(self._personNode(l.proxy2,  item.id, 'proxy2',  'leader'));
                    if (item._members) {
                        var lIds = [l.manager?.id, l.deputy?.id, l.proxy1?.id, l.proxy2?.id].filter(Boolean);
                        item._members.filter(m => !lIds.includes(m.id)).forEach(m => {
                            node.children.push(self._personNode(m, item.id, 'member', 'employee'));
                        });
                    }
                }
                if (item.children?.length > 0) {
                    node.children = node.children.concat(build(item.children));
                }
                return node;
            });

            return [{
                id: 'root',
                label: rootLabel,
                expanded: true,
                children: build(this.departments),
                data: { type: 'root' }
            }];
        },

        _personNode(person, deptId, role, tagClass) {
            var name = person.native_name || person.display_name || '?';
            return {
                id: 'p_' + role + '_' + deptId + '_' + person.id,
                label: name,
                children: [],
                data: {
                    type: 'person', userId: person.id, deptId: deptId,
                    role: role, tagClass: tagClass, displayName: name
                }
            };
        },

        // ==================== Tree 事件 ====================

        _onNodeClick(id, node) {
            if (id === 'root') {
                this.selectRoot();
                return;
            }
            if (node.data.type === 'dept') {
                this.selectDepartment(id);
            }
            // 選取標示
            var container = document.getElementById('dept-tree');
            if (container) {
                container.querySelectorAll('.tg-selected').forEach(el => el.classList.remove('tg-selected'));
                var row = container.querySelector('tr[data-id="' + id + '"]');
                if (row) row.classList.add('tg-selected');
            }
        },

        async _onNodeMoved(nodeId, newParentId, newIndex, node) {
            if (node.data.type === 'dept') {
                var parentId = (newParentId === 'root') ? null : newParentId;
                try {
                    var res = await fetch('/api/units/' + nodeId, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                        body: JSON.stringify({ parent_id: parentId })
                    });
                    if (res.ok) {
                        this.showToast('部門已移動', 'success');
                    } else {
                        var data = await res.json();
                        this.showToast(data.error || '移動失敗', 'error');
                    }
                } catch (e) { this.showToast('移動失敗', 'error'); }
                await this._refreshAll();
            } else if (node.data.type === 'person') {
                var targetNode = this._tree._model.getNode(newParentId);
                if (targetNode && targetNode.data.type === 'dept') {
                    await this._movePersonToDept({
                        person: { id: node.data.userId },
                        deptId: node.data.deptId,
                        role: node.data.role
                    }, newParentId);
                } else {
                    await this._refreshAll();
                }
            }
        },

        // ==================== 選擇 / CRUD ====================

        selectRoot() {
            this.selectedDept = null;
            this.isCreating = false;
            this.members = [];
            this.leadership = { manager: null, deputy: null, proxy1: null, proxy2: null };
            this.crossMembers = [];
        },

        async selectDepartment(deptData) {
            var id = deptData.id || deptData;
            var dept = this.findDeptById(id);
            if (!dept) dept = deptData;
            this.selectedDept = dept;
            this.isCreating = false;
            this.formData = { code: dept.code, name: dept.name, parent_id: dept.parent_id || '' };
            this.newCrossMember = { user_id: '', role_type: 'MEMBER' };
            await Promise.all([
                this.loadMembers(id),
                this.loadLeadership(id),
                this.loadCrossMembers(id)
            ]);
        },

        startCreate() {
            var parentId = this.selectedDept ? this.selectedDept.id : '';
            this.isCreating = true;
            this.formData = { code: '', name: '', parent_id: parentId };
            this._ci_generatedCode = '';
            this._ci_suggestions = [];
            this._ci_codeValid = false;
            this._ci_codeError = '';
        },

        cancelEdit() {
            this.isCreating = false;
            if (this.selectedDept) {
                this.formData = {
                    code: this.selectedDept.code,
                    name: this.selectedDept.name,
                    parent_id: this.selectedDept.parent_id || ''
                };
            }
        },

        async createDepartment() {
            try {
                var payload = {
                    name: this.formData.name,
                    code: this.ciGetFinalCode(this.formData.code),
                    parent_id: this.formData.parent_id,
                    unit_type: 'DEPARTMENT'
                };
                var res = await fetch('/api/units', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    this.showToast('部門建立成功', 'success');
                    this.isCreating = false;
                    await this._refreshAll();
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (err) { this.showToast('建立失敗', 'error'); }
        },

        async updateDepartment() {
            if (!this.selectedDept) return;
            try {
                var res = await fetch('/api/units/' + this.selectedDept.id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({ name: this.formData.name, parent_id: this.formData.parent_id || null })
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

        async deleteDepartment() {
            if (!this.selectedDept) return;
            try {
                var checkRes = await fetch('/api/units/' + this.selectedDept.id + '?check_only=true&cascade=true', {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                var checkData = await checkRes.json();

                var msgs = ['\u78BA\u5B9A\u522A\u9664\u300C' + this.selectedDept.name + '\u300D\uFF1F'];
                if (checkData.children_count > 0) msgs.push('\n\u5305\u542B ' + checkData.children_count + ' \u500B\u5B50\u90E8\u9580');
                if (checkData.members_count > 0) msgs.push('\n\u5171 ' + checkData.members_count + ' \u4F4D\u6210\u54E1\u5C07\u79FB\u81F3\u300C\u672A\u5206\u914D\u54E1\u5DE5\u300D');

                if (!confirm(msgs.join(''))) return;

                var url = '/api/units/' + this.selectedDept.id + '?cascade=true&confirm_members=true';
                var res = await fetch(url, { method: 'DELETE', headers: { 'X-CSRFToken': getCsrfToken() } });
                var data = await res.json();
                if (res.ok) {
                    this.showToast(data.message || '刪除成功', 'success');
                    this.selectedDept = null;
                    await this._refreshAll();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (err) { this.showToast('刪除失敗', 'error'); }
        },

        findDeptById(id) {
            var find = (items) => {
                for (var item of items) {
                    if (item.id === id) return item;
                    if (item.children) { var f = find(item.children); if (f) return f; }
                }
                return null;
            };
            return find(this.departments);
        },

        formatPersonFull(p) {
            var parts = [];
            if (p.employee_id) parts.push(p.employee_id);
            if (p.native_name) parts.push(p.native_name);
            else if (p.display_name) parts.push(p.display_name);
            if (p.english_name) parts.push(p.english_name);
            return parts.join(' ');
        },

        // ==================== 跨部門人員 ====================

        async addCrossMember() {
            if (!this.selectedDept || !this.newCrossMember.user_id) return;
            try {
                var res = await fetch('/api/units/' + this.selectedDept.id + '/cross-members', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                    body: JSON.stringify({
                        user_id: this.newCrossMember.user_id,
                        role_type: this.newCrossMember.role_type
                    })
                });
                if (res.ok) {
                    var data = await res.json();
                    this.showToast(data.message || '已新增跨部門人員', 'success');
                    this.newCrossMember = { user_id: '', role_type: 'MEMBER' };
                    await this.loadCrossMembers(this.selectedDept.id);
                } else {
                    var data2 = await res.json();
                    this.showToast(data2.error || '新增失敗', 'error');
                }
            } catch (err) { this.showToast('新增失敗', 'error'); }
        },

        async removeCrossMember(cm) {
            if (!this.selectedDept) return;
            var userName = cm.user?.native_name || cm.user?.display_name || '此人員';
            if (!confirm('\u78BA\u5B9A\u79FB\u9664 ' + userName + ' \u7684\u8DE8\u90E8\u9580\u95DC\u4FC2\uFF1F')) return;
            try {
                var res = await fetch('/api/units/' + this.selectedDept.id + '/cross-members/' + cm.id, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                if (res.ok) {
                    this.showToast('已移除跨部門關係', 'success');
                    await this.loadCrossMembers(this.selectedDept.id);
                } else {
                    var data = await res.json();
                    this.showToast(data.error || '移除失敗', 'error');
                }
            } catch (err) { this.showToast('移除失敗', 'error'); }
        },

        async removeCrossIfExists(userId) {
            var crossMember = this.crossMembers.find(cm => cm.user_secure_code === userId);
            if (crossMember) {
                await fetch('/api/units/' + this.selectedDept.id + '/cross-members/' + crossMember.id, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': getCsrfToken() }
                });
                this.crossMembers = this.crossMembers.filter(cm => cm.id !== crossMember.id);
            }
        },

        // ==================== 外部面板 DnD ====================

        dragStartMember(e, member) {
            this.draggedMember = member;
            this._dragData = { source: 'external', type: 'person', person: member, role: 'member', deptId: this.selectedDept?.id };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', member.id);
        },

        dragStartLeader(e, leader, type) {
            this.draggedLeader = leader;
            this.draggedLeaderType = type;
            this._dragData = { source: 'external', type: 'person', person: leader, role: type, deptId: this.selectedDept?.id };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', leader.id);
        },

        dragStartUnassigned(e, user) {
            this.draggedUser = user;
            this._dragData = { source: 'external', type: 'person', person: user, role: null, deptId: null };
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', user.id);
        },

        onZoneDragOver(e, zone) {
            if (this._dragData || this.draggedMember || this.draggedLeader || this.draggedUser) {
                this.dragOverZone = zone;
            }
        },

        clearDrag() {
            this.draggedUser = null;
            this.draggedMember = null;
            this.draggedLeader = null;
            this.draggedLeaderType = null;
            this._dragData = null;
            this.dragOverZone = null;
        },

        async dropToLeadership(e, position) {
            e.preventDefault();
            e.stopPropagation();
            this.dragOverZone = null;
            if (!this.selectedDept) return;

            var person = this.draggedUser || this.draggedMember || this.draggedLeader;
            var fromTree = false;
            if (!person && this._dragData?.type === 'person') {
                person = this._dragData.person;
                fromTree = this._dragData.source === 'tree';
            }
            if (!person) return;

            // 從樹拖入: 先處理原部門
            if (fromTree && this._dragData.deptId) {
                var oldDeptId = this._dragData.deptId;
                var oldRole = this._dragData.role;
                if (oldRole && oldRole !== 'member') {
                    await this._apiDelete('/api/units/' + oldDeptId + '/leadership/' + oldRole);
                }
                if (oldDeptId !== this.selectedDept.id) {
                    await this._apiDelete('/api/units/' + oldDeptId + '/members/' + person.id);
                }
            }
            // 管理層職位互換
            else if (this.draggedLeader && this.draggedLeaderType !== position) {
                await this._apiDelete('/api/units/' + this.selectedDept.id + '/leadership/' + this.draggedLeaderType);
            }

            var res = await this._apiPost('/api/units/' + this.selectedDept.id + '/leadership/' + position, { user_id: person.id });
            if (res.ok) {
                var data = await res.json();
                await this.removeCrossIfExists(person.id);
                this.showToast(data.message || '已設定', 'success');
                await this._refreshAll();
            } else {
                var errData = await res.json().catch(() => ({}));
                this.showToast(errData.error || '操作失敗', 'error');
            }
            this.clearDrag();
        },

        async dropToEmployee(e) {
            e.preventDefault();
            this.dragOverZone = null;
            if (!this.selectedDept) return;

            var person = this.draggedUser || this.draggedLeader;
            var fromTree = false;
            if (!person && this._dragData?.type === 'person') {
                person = this._dragData.person;
                fromTree = this._dragData.source === 'tree';
            }
            if (!person) return;

            if (fromTree && this._dragData.deptId) {
                var oldDeptId = this._dragData.deptId;
                var oldRole = this._dragData.role;
                if (oldRole && oldRole !== 'member') {
                    await this._apiDelete('/api/units/' + oldDeptId + '/leadership/' + oldRole);
                }
                if (oldDeptId !== this.selectedDept.id) {
                    await this._apiDelete('/api/units/' + oldDeptId + '/members/' + person.id);
                    await this._apiPost('/api/units/' + this.selectedDept.id + '/members', { user_id: person.id });
                    await this.removeCrossIfExists(person.id);
                    this.showToast('已調至此部門', 'success');
                } else {
                    this.showToast('已移除管理層角色', 'success');
                }
            } else if (this.draggedLeader) {
                await this._apiDelete('/api/units/' + this.selectedDept.id + '/leadership/' + this.draggedLeaderType);
                this.showToast('已移除管理層角色', 'success');
            } else if (this.draggedUser) {
                await this._apiPost('/api/units/' + this.selectedDept.id + '/members', { user_id: person.id });
                await this.removeCrossIfExists(person.id);
                this.showToast('已加入部門', 'success');
            }

            await this._refreshAll();
            this.clearDrag();
        },

        async dropToUnassigned(e) {
            e.preventDefault();
            this.dragOverZone = null;

            var person = this.draggedMember || this.draggedLeader;
            var fromTree = false;
            var deptId = this.selectedDept?.id;

            if (!person && this._dragData?.type === 'person') {
                person = this._dragData.person;
                deptId = this._dragData.deptId;
                fromTree = this._dragData.source === 'tree';
            }
            if (!person || !deptId) return;

            if (fromTree && this._dragData?.role && this._dragData.role !== 'member') {
                await this._apiDelete('/api/units/' + deptId + '/leadership/' + this._dragData.role);
            } else if (this.draggedLeader) {
                await this._apiDelete('/api/units/' + deptId + '/leadership/' + this.draggedLeaderType);
            }

            await this._apiDelete('/api/units/' + deptId + '/members/' + person.id);
            this.showToast('已移出部門', 'success');
            await this._refreshAll();
            this.clearDrag();
        },

        async dropToCross(e) {
            e.preventDefault();
            this.dragOverZone = null;
            if (!this.selectedDept) return;

            var userId = null;
            var fromDeptId = null;

            if (this._dragData?.type === 'person') {
                userId = this._dragData.person?.id || this._dragData.person;
                fromDeptId = this._dragData.deptId;
            } else if (this.draggedUser) {
                userId = this.draggedUser.id;
            }
            if (!userId) return;

            if (fromDeptId === this.selectedDept.id) {
                this.showToast('此人已是本部門正式成員', 'error');
                this.clearDrag();
                return;
            }

            try {
                var res = await this._apiPost('/api/units/' + this.selectedDept.id + '/cross-members', {
                    user_id: userId, role_type: 'MEMBER'
                });
                if (res.ok) {
                    var data = await res.json();
                    this.showToast(data.message || '已新增跨部門人員', 'success');
                    await this.loadCrossMembers(this.selectedDept.id);
                } else {
                    var errData = await res.json();
                    this.showToast(errData.error || '新增失敗', 'error');
                }
            } catch (err) { this.showToast('新增失敗', 'error'); }
            this.clearDrag();
        },

        // ==================== 外部面板 -> Tree drop ====================

        _attachExternalDrop() {
            var container = document.getElementById('dept-tree');
            if (!container) return;
            var self = this;

            container.addEventListener('dragover', function(e) {
                if (!self._dragData) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                container.querySelectorAll('.tree-drop-highlight').forEach(el => el.classList.remove('tree-drop-highlight'));
                var tr = e.target.closest('tr.treegrid-row');
                if (tr) {
                    var nodeId = tr.dataset.id;
                    var node = self._tree._model.getNode(nodeId);
                    if (node && node.data.type === 'dept') {
                        tr.classList.add('tree-drop-highlight');
                    }
                }
            });

            container.addEventListener('dragleave', function(e) {
                var tr = e.target.closest('tr.treegrid-row');
                if (tr) tr.classList.remove('tree-drop-highlight');
            });

            container.addEventListener('drop', async function(e) {
                e.preventDefault();
                container.querySelectorAll('.tree-drop-highlight').forEach(el => el.classList.remove('tree-drop-highlight'));
                var tr = e.target.closest('tr.treegrid-row');
                if (!tr || !self._dragData) return;
                var targetId = tr.dataset.id;
                var targetNode = self._tree._model.getNode(targetId);
                if (!targetNode || targetNode.data.type !== 'dept') return;

                var person = self.draggedMember || self.draggedLeader || self.draggedUser;
                if (!person && self._dragData.person) person = self._dragData.person;
                if (!person) return;

                // 管理層先移除職位
                if (self.draggedLeader && self.selectedDept) {
                    await self._apiDelete('/api/units/' + self.selectedDept.id + '/leadership/' + self.draggedLeaderType);
                }
                // 從原部門移除再加入新部門
                if (self.selectedDept) {
                    await self._apiDelete('/api/units/' + self.selectedDept.id + '/members/' + person.id);
                }
                await self._apiPost('/api/units/' + targetId + '/members', { user_id: person.id });
                var targetDept = self.findDeptById(targetId);
                self.showToast('已調至 ' + (targetDept?.name || targetId), 'success');
                await self._refreshAll();
                self.clearDrag();
            });
        },

        // ==================== 模式切換 ====================

        switchToDeptMode() {
            this.showPeopleInTree = false;
            this.buildTree();
        },

        async switchToDetailMode() {
            this.showPeopleInTree = true;
            var firstDept = this.departments[0];
            if (firstDept && !firstDept._leadership) {
                await this.loadAllPeople();
            }
            this.buildTree();
        },

        // ==================== 工具 ====================

        async _movePersonToDept(drag, targetDeptId) {
            var personId = drag.person?.id || drag.person;
            if (drag.role && drag.role !== 'member' && drag.deptId) {
                await this._apiDelete('/api/units/' + drag.deptId + '/leadership/' + drag.role);
            }
            if (drag.deptId && drag.deptId !== targetDeptId) {
                await this._apiDelete('/api/units/' + drag.deptId + '/members/' + personId);
            }
            if (targetDeptId && targetDeptId !== 'root') {
                await this._apiPost('/api/units/' + targetDeptId + '/members', { user_id: personId });
                var dept = this.findDeptById(targetDeptId);
                this.showToast('已調至 ' + (dept?.name || targetDeptId), 'success');
            }
            await this._refreshAll();
        },

        async _apiPost(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
                body: JSON.stringify(body)
            });
        },

        async _apiDelete(url) {
            return fetch(url, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': getCsrfToken() }
            });
        },

        async _refreshAll() {
            await this.loadDepartments();
            await this.loadUnassignedUsers();
            if (this.selectedDept) {
                await Promise.all([
                    this.loadMembers(this.selectedDept.id),
                    this.loadLeadership(this.selectedDept.id),
                    this.loadCrossMembers(this.selectedDept.id)
                ]);
            }
            this.buildTree();
            if (this.selectedDept) {
                this.$nextTick(() => {
                    var container = document.getElementById('dept-tree');
                    if (container) {
                        var row = container.querySelector('tr[data-id="' + this.selectedDept.id + '"]');
                        if (row) row.classList.add('tg-selected');
                    }
                });
            }
        },

        showToast(msg, type) {
            type = type || 'success';
            var toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(function() { toast.remove(); }, 3000);
        }
    };
}
