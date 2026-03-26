/**
 * menu-tree.js
 * 選單管理 - BeakTrellis 拖曳排序元件
 *
 * 依賴: beak-tree-model.js, beak-trellis.js, beak-trellis-splitpane.js,
 *       beak-trellis-drag.js, renderers/beak-tree-lines-dom.js
 */
'use strict';

// ========== CSRF ==========
var _menuTreeCsrf = document.querySelector('meta[name="csrf-token"]');
var _menuTreeCsrfToken = _menuTreeCsrf ? _menuTreeCsrf.content : '';

// ========== 自訂 Renderer ==========
(function() {
    if (typeof BeakTrellis === 'undefined') return;
    var linesDom = BeakTrellis.renderers ? BeakTrellis.renderers['lines-dom'] : null;

    BeakTrellis.registerRenderer('menu-tree', {
        renderTreeCell: function(node, ancestors, grid) {
            var cell = document.createElement('div');
            cell.className = 'bt-tree-cell bt-dom-cell';

            // 縮排
            for (var i = 0; i < ancestors.length; i++) {
                var sp = document.createElement('span');
                sp.className = 'bt-indent bt-indent-blank';
                cell.appendChild(sp);
            }

            // 分支線
            if (node.level > 0) {
                var br = document.createElement('span');
                br.className = 'bt-branch';
                cell.appendChild(br);
            }

            // 展開/收合按鈕
            var model = grid._model;
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

            // Icon
            if (node.data.icon) {
                var icon = document.createElement('i');
                icon.className = node.data.icon;
                icon.style.marginRight = '4px';
                icon.style.fontSize = '13px';
                cell.appendChild(icon);
            }

            // 標題
            var lbl = document.createElement('span');
            lbl.className = 'bt-label';
            lbl.textContent = node.label;
            cell.appendChild(lbl);

            return cell;
        },
        afterRender: function(grid) {
            if (linesDom && linesDom.afterRender) {
                linesDom.afterRender(grid);
            }
        }
    });
})();


// ========== 權限勾選 Renderer ==========
function _permRenderer(permKey) {
    return function(val, node) {
        var perms = node.data.perms || {};
        if (perms[permKey]) return '<span class="mt-perm-yes">V</span>';
        return '<span class="mt-perm-no">-</span>';
    };
}


// ========== Alpine.js 元件 ==========

function menuTreeManager() {
    return {
        _grid: null,
        saving: false,
        message: '',
        messageType: '',
        showRootHeaderModal: false,
        showFactoryResetModal: false,

        init: function() {
            this.buildTree();
        },

        buildTree: function() {
            var container = document.getElementById('menu-trellis');
            if (!container) return;

            // 清除舊實例
            if (this._grid) {
                this._grid.destroy();
                this._grid = null;
            }

            var treeData = window.__MENU_TRELLIS_DATA || [];
            if (treeData.length === 0) return;

            var self = this;

            this._grid = new BeakTrellis(container, {
                data: treeData,
                treeMode: 'menu-tree',
                draggable: true,
                columns: [
                    {
                        id: '_edit',
                        label: '',
                        width: '40px',
                        sortable: false,
                        resizable: false,
                        renderer: function(val, node) {
                            return '<a href="/menu/' + node.id + '/edit">[編輯]</a>';
                        }
                    },
                    {
                        id: 'perm_sys',
                        label: '系統',
                        width: '36px',
                        sortable: false,
                        resizable: false,
                        renderer: _permRenderer('SYSTEM_ADMIN')
                    },
                    {
                        id: 'perm_org',
                        label: '企業',
                        width: '36px',
                        sortable: false,
                        resizable: false,
                        renderer: _permRenderer('ORG_ADMIN')
                    },
                    {
                        id: 'perm_emp',
                        label: '員工',
                        width: '36px',
                        sortable: false,
                        resizable: false,
                        renderer: _permRenderer('EMPLOYEE')
                    },
                    {
                        id: 'perm_ext',
                        label: '外部',
                        width: '36px',
                        sortable: false,
                        resizable: false,
                        renderer: _permRenderer('EXTERNAL')
                    },
                    {
                        id: 'code',
                        label: '代碼',
                        width: '280px',
                        sortable: false,
                        resizable: false
                    },
                    {
                        id: 'link_type',
                        label: '類型',
                        width: '60px',
                        sortable: false,
                        resizable: false
                    },
                    {
                        id: 'link_target',
                        label: '連結目標',
                        width: '360px',
                        sortable: false,
                        resizable: false,
                        renderer: function(val) {
                            if (!val) return '-';
                            return '<code>' + val + '</code>';
                        }
                    },
                    {
                        id: 'is_active',
                        label: '狀態',
                        width: '50px',
                        sortable: false,
                        resizable: false,
                        renderer: function(val) {
                            if (val === true) return '<span class="mt-status-active">啟用</span>';
                            return '<span class="mt-status-inactive">停用</span>';
                        }
                    }
                ],
                rowClassFn: function(node) {
                    return node.data.row_class || '';
                },
                onNodeMoved: function(nodeId, newParentId, newIndex, node) {
                    self._onNodeMoved(nodeId, newParentId, newIndex);
                }
            });
        },

        _onNodeMoved: async function(nodeId, newParentId, newIndex) {
            var model = this._grid._model;
            var siblings;
            if (newParentId) {
                var parent = model.getNode(newParentId);
                siblings = parent ? parent.children : [];
            } else {
                siblings = model.getRootNodes();
            }

            // 建立批量更新資料
            var items = [];
            for (var i = 0; i < siblings.length; i++) {
                var sibling = siblings[i];
                var entry = {
                    secure_code: sibling.id,
                    display_order: i
                };
                if (sibling.id === nodeId) {
                    entry.parent_secure_code = newParentId || null;
                }
                items.push(entry);
            }

            this.saving = true;
            this.message = '';

            try {
                var resp = await fetch('/api/menu/reorder', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': _menuTreeCsrfToken
                    },
                    body: JSON.stringify({ items: items })
                });
                var data = await resp.json();
                if (resp.ok && data.success) {
                    this.message = '順序已儲存';
                    this.messageType = 'success';
                } else {
                    this.message = '儲存失敗: ' + (data.error || resp.status);
                    this.messageType = 'error';
                }
            } catch (e) {
                this.message = '儲存失敗: ' + e.message;
                this.messageType = 'error';
            }

            this.saving = false;

            var self = this;
            setTimeout(function() { self.message = ''; }, 3000);
        },

        resetPositions: async function() {
            this.saving = true;
            this.message = '';

            try {
                var resp = await fetch('/api/menu/reset-positions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': _menuTreeCsrfToken
                    }
                });
                var data = await resp.json();
                if (resp.ok && data.success) {
                    this.message = '位置已重置 (' + data.updated + ' 項更新)';
                    this.messageType = 'success';
                    setTimeout(function() { location.reload(); }, 800);
                } else {
                    this.message = '重置失敗: ' + (data.error || resp.status);
                    this.messageType = 'error';
                }
            } catch (e) {
                this.message = '重置失敗: ' + e.message;
                this.messageType = 'error';
            }

            this.saving = false;
        },

        resetFactory: async function() {
            this.showFactoryResetModal = false;
            this.saving = true;
            this.message = '';

            try {
                var resp = await fetch('/api/menu/reset-factory', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': _menuTreeCsrfToken
                    }
                });
                var data = await resp.json();
                if (resp.ok && data.success) {
                    var roleReqMsg = data.role_requirements_reset
                        ? ', ' + data.role_requirements_reset + ' 筆角色需求'
                        : '';
                    this.message = '出廠值已重置 (' + data.updated + ' 項更新' + roleReqMsg + ')';
                    this.messageType = 'success';
                    setTimeout(function() { location.reload(); }, 800);
                } else {
                    this.message = '重置失敗: ' + (data.error || resp.status);
                    this.messageType = 'error';
                }
            } catch (e) {
                this.message = '重置失敗: ' + e.message;
                this.messageType = 'error';
            }

            this.saving = false;
        }
    };
}
