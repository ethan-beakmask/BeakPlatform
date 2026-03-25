'use strict';

/**
 * 部門設定頁 — 使用獨立 Tree 元件 (取代 jstree+jQuery)
 *
 * 載入順序: beak-tree-model.js → beak-tree.js → beak-tree-drag.js → beak-tree-lines-dom.js → departments.js
 */

// ==================== 自訂 Renderer ====================
(function() {
    if (typeof BeakTree === 'undefined') return;
    var linesDom = BeakTree.renderers ? BeakTree.renderers['lines-dom'] : null;

    BeakTree.registerRenderer('dept-tree', {
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
            lbl.className = 'bt-label';
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
    var _ucMixin = userCreateMixin({
        orgSettings: window.__DEPT_CONFIG?.orgSettings || {},
        orgName: window.__DEPT_CONFIG?.orgName || '\u4F01\u696D'
    });

    return {
        ...codeInputMixin('department'),
        ..._ucMixin,

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
        isCreatingEmployee: false,
        formData: { code: '', name: '', parent_id: '' },
        totalUsers: 0,

        // 員工表單
        empTargetDept: null,
        empDomainName: window.__DEPT_CONFIG?.domainName || '',

        // Tree 實例
        _tree: null,

        // DnD 狀態
        dragOverZone: null,
        _dragData: null,        // 外部面板拖放: { source, type, person, role, deptId }
        draggedMember: null,    // 中間面板拖出的成員
        draggedLeader: null,    // 中間面板拖出的管理層
        draggedLeaderType: null,
        draggedUser: null,      // 右側未分配拖出
        ctrlHeld: false,       // Ctrl 鍵狀態（跨部門模式）
        _isDragging: false,     // 拖曳中旗標

        // ==================== 計算屬性 ====================

        get leaderIds() {
            return [this.leadership.manager?.id, this.leadership.deputy?.id,
                    this.leadership.proxy1?.id, this.leadership.proxy2?.id].filter(Boolean);
        },

        get regularMembers() {
            var base = this.members.filter(m => !this.leaderIds.includes(m.id));
            // 跨部門 MEMBER 也顯示在員工欄，帶 _isCross 標記
            var crossEmployees = this.crossMembers
                .filter(cm => cm.role_type === 'MEMBER' && cm.user)
                .map(cm => ({ ...cm.user, _isCross: true, _crossId: cm.id }));
            return base.concat(crossEmployees);
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

        get isCtrlCrossMode() {
            return this._isDragging && this.ctrlHeld && !this.draggedUser && !this.draggedMember && !this.draggedLeader;
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
                this.loadUnassignedUsers(),
                this.uc_init()
            ]);
            this.buildTree();
        },

        // ==================== 新增員工 ====================

        startCreateEmployee() {
            this.isCreating = false;
            this.isCreatingEmployee = true;
            this.empTargetDept = this.selectedDept || null;
            this.uc_reset();
            if (this.empTargetDept) {
                this.uc_departmentCode = this.empTargetDept.code;
            } else {
                this.uc_departmentCode = '';
            }
        },

        cancelCreateEmployee() {
            this.isCreatingEmployee = false;
        },

        async submitEmployee() {
            if (this.empTargetDept) {
                this.uc_departmentCode = this.empTargetDept.code;
            } else {
                this.uc_departmentCode = '';
            }

            var result = await this.uc_submit();
            if (!result) return;

            if (result.success) {
                this.showToast('\u5DF2\u5EFA\u7ACB\u54E1\u5DE5 ' + this.uc_nativeName, 'success');
                this.isCreatingEmployee = false;
                // 重新載入資料
                await this._refreshAll();
                // 如果有目標部門，導航到該部門
                if (this.empTargetDept && this._tree) {
                    this._tree.focusNode(this.empTargetDept.id, { expanded: true });
                    this.selectDepartment(this.empTargetDept.id);
                }
            } else {
                this.showToast(result.error, 'error');
            }
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

            this._tree = new BeakTree(container, {
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
                    if (this.ctrlHeld && node.data.deptId !== newParentId) {
                        await this._addCrossViaApi(newParentId, node.data.userId, 'MEMBER');
                        await this._refreshAll();
                    } else {
                        await this._movePersonToDept({
                            person: { id: node.data.userId },
                            deptId: node.data.deptId,
                            role: node.data.role
                        }, newParentId);
                    }
                } else {
                    await this._refreshAll();
                }
            }
        },

        // ==================== 選擇 / CRUD ====================

        selectRoot() {
            this.selectedDept = null;
            this.isCreating = false;
            this.isCreatingEmployee = false;
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
            this.isCreatingEmployee = false;
            this.formData = { code: dept.code, name: dept.name, parent_id: dept.parent_id || '' };
            await Promise.all([
                this.loadMembers(id),
                this.loadLeadership(id),
                this.loadCrossMembers(id)
            ]);
            this._mergeCrossToProxy();
        },

        startCreate() {
            var parentId = this.selectedDept ? this.selectedDept.id : '';
            this.isCreating = true;
            this.isCreatingEmployee = false;
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

        // ==================== 跨部門人員標示 ====================

        crossRoleTag(cm) {
            var map = { MANAGER: '\u4EE3', DEPUTY: '\u4EE3', PROXY1: '\u4EE3', PROXY2: '\u4EE3', MEMBER: '\u54E1' };
            return '[' + (map[cm.role_type] || '\u54E1') + ']';
        },

        crossRoleTagClass(cm) {
            if (['MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2'].includes(cm.role_type)) return 'leader';
            return 'employee';
        },

        _mergeCrossToProxy() {
            var crossMgr = this.crossMembers.find(cm => cm.role_type === 'MANAGER');
            if (crossMgr && !this.leadership.proxy1 && crossMgr.user) {
                this.leadership.proxy1 = { ...crossMgr.user, _isCross: true };
            }
            var crossDep = this.crossMembers.find(cm => cm.role_type === 'DEPUTY');
            if (crossDep && !this.leadership.proxy2 && crossDep.user) {
                this.leadership.proxy2 = { ...crossDep.user, _isCross: true };
            }
        },

        // ==================== 跨部門人員 ====================

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
                    await Promise.all([
                        this.loadLeadership(this.selectedDept.id),
                        this.loadCrossMembers(this.selectedDept.id)
                    ]);
                    this._mergeCrossToProxy();
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
            // 跨部門員工不可拖拉
            if (member._isCross) {
                e.preventDefault();
                return;
            }
            this.draggedMember = member;
            this._dragData = { source: 'external', type: 'person', person: member, role: 'member', deptId: this.selectedDept?.id };
            this._isDragging = true;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', member.id);
        },

        dragStartLeader(e, leader, type) {
            // 跨部門代理人不可拖拉
            if (leader._isCross) {
                e.preventDefault();
                return;
            }
            this.draggedLeader = leader;
            this.draggedLeaderType = type;
            this._dragData = { source: 'external', type: 'person', person: leader, role: type, deptId: this.selectedDept?.id };
            this._isDragging = true;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', leader.id);
        },

        dragStartUnassigned(e, user) {
            this.draggedUser = user;
            this._dragData = { source: 'external', type: 'person', person: user, role: null, deptId: null };
            this._isDragging = true;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', user.id);
        },

        onZoneDragOver(e, zone) {
            if (this._dragData || this.draggedMember || this.draggedLeader || this.draggedUser) {
                e.dataTransfer.dropEffect = 'move';
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
            this._isDragging = false;
            this.ctrlHeld = false;
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

            // 跨部門代理人不可在部門內拖拉異動
            if (person._isCross) {
                this.showToast('\u8DE8\u90E8\u9580\u4EE3\u7406\u4EBA\u4E0D\u53EF\u76F4\u63A5\u7570\u52D5\uFF0C\u8ACB\u5F9E\u8DE8\u90E8\u9580\u4EBA\u54E1\u5340\u7BA1\u7406', 'error');
                this.clearDrag();
                return;
            }

            // Ctrl + 非未分配來源 = 跨部門
            if (this._shouldCross(e)) {
                // manager/proxy1 → 代理人(一)，deputy/proxy2 → 代理人(二)
                // 對應代理席有人 → 阻擋
                if ((position === 'manager' || position === 'proxy1') && this.leadership.proxy1) {
                    this.showToast('\u4EE3\u7406\u4EBA(\u4E00)\u4F4D\u7F6E\u5DF2\u4F54\u4F4D\uFF0C\u8ACB\u5148\u79FB\u9664', 'error');
                    this.clearDrag();
                    return;
                }
                if ((position === 'deputy' || position === 'proxy2') && this.leadership.proxy2) {
                    this.showToast('\u4EE3\u7406\u4EBA(\u4E8C)\u4F4D\u7F6E\u5DF2\u4F54\u4F4D\uFF0C\u8ACB\u5148\u79FB\u9664', 'error');
                    this.clearDrag();
                    return;
                }
                var roleType = this._crossRoleType(position);
                await this._addCrossViaApi(this.selectedDept.id, person.id, roleType);
                await this._refreshAll();
                this.clearDrag();
                return;
            }

            // 從樹拖入: 先處理原部門
            if (fromTree && this._dragData.deptId) {
                var oldDeptId = this._dragData.deptId;
                var oldRole = this._dragData.role;
                if (oldRole && oldRole !== 'member') {
                    await this._apiDelete('/api/units/' + oldDeptId + '/leadership/' + oldRole);
                }
                if (oldDeptId !== this.selectedDept.id) {
                    // 404 表示非此部門主要成員，忽略即可
                    await this._apiDelete('/api/units/' + oldDeptId + '/members/' + person.id).catch(function() {});
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

            // 跨部門代理人不可在部門內拖拉異動
            if (person._isCross) {
                this.showToast('\u8DE8\u90E8\u9580\u4EE3\u7406\u4EBA\u4E0D\u53EF\u76F4\u63A5\u7570\u52D5\uFF0C\u8ACB\u5F9E\u8DE8\u90E8\u9580\u4EBA\u54E1\u5340\u7BA1\u7406', 'error');
                this.clearDrag();
                return;
            }

            // Ctrl + 非未分配來源 = 跨部門
            if (this._shouldCross(e)) {
                await this._addCrossViaApi(this.selectedDept.id, person.id, 'MEMBER');
                await this._refreshAll();
                this.clearDrag();
                return;
            }

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

        // ==================== Ctrl 跨部門輔助 ====================

        _shouldCross(e) {
            if (!e.ctrlKey) return false;
            if (this.draggedUser) return false;
            if (this.draggedMember || this.draggedLeader) return false;
            return true;
        },

        _crossRoleType(position) {
            // manager/proxy1 都對應代理人(一)，deputy/proxy2 都對應代理人(二)
            if (position === 'manager' || position === 'proxy1') return 'MANAGER';
            if (position === 'deputy' || position === 'proxy2') return 'DEPUTY';
            return 'MEMBER';
        },

        async _addCrossViaApi(deptId, userId, roleType) {
            var res = await this._apiPost('/api/units/' + deptId + '/cross-members', {
                user_id: userId, role_type: roleType
            });
            if (res.ok) {
                var data = await res.json();
                this.showToast(data.message || '已新增跨部門人員', 'success');
            } else {
                var errData = await res.json().catch(function() { return {}; });
                this.showToast(errData.error || '新增跨部門失敗', 'error');
            }
        },

        // ==================== 外部面板 -> Tree drop ====================

        _attachExternalDrop() {
            var container = document.getElementById('dept-tree');
            if (!container) return;
            var self = this;

            // 攔截 Tree 內部的 person 拖曳開始，讓外部面板 drop 能識別
            container.addEventListener('dragstart', function(e) {
                var tr = e.target.closest('tr.bt-row');
                if (!tr) return;
                var nodeId = tr.dataset.id;
                var node = self._tree._model.getNode(nodeId);
                if (node && node.data.type === 'person') {
                    self._dragData = {
                        source: 'tree', type: 'person',
                        person: { id: node.data.userId },
                        role: node.data.role, deptId: node.data.deptId
                    };
                    self._isDragging = true;
                } else {
                    self._dragData = null;
                    self._isDragging = false;
                }
            });

            container.addEventListener('dragend', function() {
                if (self._dragData && self._dragData.source === 'tree') {
                    self.clearDrag();
                }
            });

            container.addEventListener('dragover', function(e) {
                if (!self._dragData) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                container.querySelectorAll('.bk-tree-drop-highlight').forEach(el => el.classList.remove('bk-tree-drop-highlight'));
                var tr = e.target.closest('tr.bt-row');
                if (tr) {
                    var nodeId = tr.dataset.id;
                    var node = self._tree._model.getNode(nodeId);
                    if (node && node.data.type === 'dept') {
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
                container.querySelectorAll('.bk-tree-drop-highlight').forEach(el => el.classList.remove('bk-tree-drop-highlight'));
                var tr = e.target.closest('tr.bt-row');
                if (!tr || !self._dragData) return;
                // Tree 內部拖曳由 onNodeMoved 處理
                if (self._dragData.source === 'tree') return;
                var targetId = tr.dataset.id;
                var targetNode = self._tree._model.getNode(targetId);
                if (!targetNode || targetNode.data.type !== 'dept') return;

                var person = self.draggedMember || self.draggedLeader || self.draggedUser;
                if (!person && self._dragData.person) person = self._dragData.person;
                if (!person) return;

                // 跨部門代理人不可拖拉異動
                if (person._isCross) {
                    self.showToast('\u8DE8\u90E8\u9580\u4EE3\u7406\u4EBA\u4E0D\u53EF\u76F4\u63A5\u7570\u52D5\uFF0C\u8ACB\u5F9E\u8DE8\u90E8\u9580\u4EBA\u54E1\u5340\u7BA1\u7406', 'error');
                    self.clearDrag();
                    return;
                }

                // Ctrl + 非未分配 = 跨部門
                if (e.ctrlKey && !self.draggedUser) {
                    var sourceDeptId = self._dragData.deptId || self.selectedDept?.id;
                    if (sourceDeptId === targetId) {
                        self.showToast('無法對同部門設定跨部門', 'error');
                        self.clearDrag();
                        return;
                    }
                    await self._addCrossViaApi(targetId, person.id, 'MEMBER');
                    await self._refreshAll();
                    self.clearDrag();
                    return;
                }

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
                this._mergeCrossToProxy();
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
