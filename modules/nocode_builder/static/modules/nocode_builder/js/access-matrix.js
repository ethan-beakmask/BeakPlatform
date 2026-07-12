/**
 * access-matrix.js -- 准入矩陣
 * BeakTrellis 元件: 行=網頁節點(樹狀), 列=角色, 格=勾選(能/不能進入)
 *
 * 使用方式:
 *   accessMatrixManager(subSystemSc) -- Alpine.js component
 */
function accessMatrixManager(subSystemSc) {
    var ROLES = ['GUEST', 'MANAGER', 'DEPUTY', 'PROXY1', 'PROXY2', 'MEMBER'];
    var ROLE_LABELS = {
        'GUEST': __('GUEST (任何人)'),
        'MANAGER': __('MANAGER (團長)'),
        'DEPUTY': __('DEPUTY (副團長)'),
        'PROXY1': __('PROXY1 (代理一)'),
        'PROXY2': __('PROXY2 (代理二)'),
        'MEMBER': __('MEMBER (團員)'),
    };

    return {
        loading: true,
        saving: false,
        dirty: false,
        _grid: null,
        _nodeMap: {},  // secure_code → { access_roles: [...] }
        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadAndRender();
        },

        async loadAndRender() {
            this.loading = true;
            try {
                var res = await fetch(window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map');
                var json = await res.json();
                if (!json.success) {
                    this.showToast(json.error || __('載入失敗'), 'error');
                    this.loading = false;
                    return;
                }
                this._buildMatrix(json.data || []);
            } catch (e) {
                this.showToast(__('載入失敗: {msg}', {msg: e.message}), 'error');
            }
            this.loading = false;
        },

        _buildMatrix(tree) {
            var self = this;
            this._nodeMap = {};
            this.dirty = false;

            // 攤平樹為 BeakTrellis data 格式
            function toTrellisData(nodes) {
                return nodes.map(function(n) {
                    self._nodeMap[n.secure_code] = {
                        access_roles: (n.access_roles || []).slice(),
                        original: (n.access_roles || []).slice(),
                        node_type: n.node_type,
                    };
                    var item = {
                        id: n.secure_code,
                        label: n.name,
                        data: {
                            node_type: n.node_type,
                            icon: n.icon,
                            is_active: n.is_active,
                        },
                    };
                    if (n.children && n.children.length > 0) {
                        item.children = toTrellisData(n.children);
                        item.expanded = true;
                    }
                    return item;
                });
            }

            var data = toTrellisData(tree);
            if (data.length === 0) {
                var el = document.getElementById('access-matrix');
                if (el) el.innerHTML = '<div style="padding: 40px; text-align: center; color: #999;">' + __('尚無網站地圖節點') + '</div>';
                return;
            }

            // 建立 BeakTrellis columns
            var columns = [
                { id: '_tree', label: __('頁面'), width: '260px' },
            ];

            ROLES.forEach(function(role) {
                columns.push({
                    id: role,
                    label: role,
                    width: '110px',
                    sortable: false,
                    resizable: false,
                    renderer: function(value, node, column, grid) {
                        var nodeInfo = self._nodeMap[node.id];
                        if (!nodeInfo || nodeInfo.node_type === 'folder') {
                            return '';  // folder 不顯示 checkbox
                        }

                        var div = document.createElement('div');
                        div.style.textAlign = 'center';

                        var cb = document.createElement('input');
                        cb.type = 'checkbox';
                        cb.checked = nodeInfo.access_roles.indexOf(role) >= 0;
                        cb.style.cursor = 'pointer';

                        cb.addEventListener('change', function() {
                            self._toggleAccess(node.id, role, cb.checked);
                        });

                        div.appendChild(cb);
                        return div;
                    },
                });
            });

            // 銷毀舊的
            if (this._grid) {
                var el = document.getElementById('access-matrix');
                if (el) el.innerHTML = '';
                this._grid = null;
            }

            this.$nextTick(function() {
                var el = document.getElementById('access-matrix');
                if (!el || typeof BeakTrellis === 'undefined') {
                    console.error('BeakTrellis not loaded or container not found');
                    return;
                }

                self._grid = new BeakTrellis(el, {
                    data: data,
                    columns: columns,
                    treeMode: 'lines-dom',
                });
            });
        },

        _toggleAccess(nodeId, role, checked) {
            var info = this._nodeMap[nodeId];
            if (!info) return;

            if (role === 'GUEST' && checked) {
                // GUEST 表示任何人，勾選 GUEST 時清除其他角色
                info.access_roles = ['GUEST'];
            } else if (role === 'GUEST' && !checked) {
                // 取消 GUEST
                info.access_roles = info.access_roles.filter(function(r) { return r !== 'GUEST'; });
            } else if (checked) {
                // 勾選非 GUEST 角色時，移除 GUEST（有角色限制就不是任何人了）
                info.access_roles = info.access_roles.filter(function(r) { return r !== 'GUEST'; });
                if (info.access_roles.indexOf(role) < 0) {
                    info.access_roles.push(role);
                }
            } else {
                // 取消勾選
                info.access_roles = info.access_roles.filter(function(r) { return r !== role; });
            }

            this.dirty = true;
            // 重新渲染以更新 checkbox 狀態（GUEST 互斥邏輯）
            if (this._grid) {
                this._grid.updateNodeData(nodeId, {});
            }
        },

        async saveAll() {
            if (!this.dirty) return;
            this.saving = true;

            var updates = [];
            var self = this;
            Object.keys(this._nodeMap).forEach(function(sc) {
                var info = self._nodeMap[sc];
                if (info.node_type === 'folder') return;

                var origStr = JSON.stringify(info.original.slice().sort());
                var currStr = JSON.stringify(info.access_roles.slice().sort());
                if (origStr !== currStr) {
                    updates.push({ secure_code: sc, access_roles: info.access_roles });
                }
            });

            if (updates.length === 0) {
                this.dirty = false;
                this.saving = false;
                return;
            }

            var failed = 0;
            for (var i = 0; i < updates.length; i++) {
                try {
                    var res = await fetch(
                        window.__BP + '/api/nocode-builder/sub-systems/' + subSystemSc + '/site-map/nodes/' + updates[i].secure_code,
                        {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ access_roles: updates[i].access_roles }),
                        }
                    );
                    var json = await res.json();
                    if (!json.success) failed++;
                } catch (e) {
                    failed++;
                }
            }

            if (failed > 0) {
                this.showToast(__('{n} 筆更新失敗', {n: failed}), 'error');
            } else {
                this.showToast(__('已儲存 {n} 筆准入設定', {n: updates.length}), 'success');
                // 更新 original 記錄
                Object.keys(this._nodeMap).forEach(function(sc) {
                    self._nodeMap[sc].original = self._nodeMap[sc].access_roles.slice();
                });
                this.dirty = false;
            }
            this.saving = false;
        },

        showToast(message, type) {
            this.toast = { show: true, message: message, type: type };
            var self = this;
            setTimeout(function() { self.toast.show = false; }, 3000);
        },
    };
}
