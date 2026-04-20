/**
 * Form.io UserPicker 自訂元件
 *
 * 功能：
 *   - 表單開啟時自動帶入當前登入者（顯示名字+部門，存 secure_code）
 *   - 點擊「選擇」按鈕彈出部門人員樹（BaekTree），可改選他人
 *   - 存入 form_data 的值為 user secure_code（字串）
 *
 * 依賴：
 *   - Form.io (Formio global)
 *   - BaekTree (beak-tree.js + beak-tree-model.js + renderers/beak-tree-lines-dom.js)
 *
 * 註冊方式：Formio.use() 外掛，升級 Form.io 不受影響
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[UserPicker] Formio is not loaded');
        return;
    }

    // ========================================
    // 快取
    // ========================================
    var _orgTreeCache = null;
    var _orgTreeLoading = null;

    function fetchOrgTree() {
        if (_orgTreeCache) return Promise.resolve(_orgTreeCache);
        if (_orgTreeLoading) return _orgTreeLoading;
        _orgTreeLoading = fetch(window.__BP + '/api/form-center/org-tree')
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json.success) {
                    _orgTreeCache = json.data;
                    return _orgTreeCache;
                }
                throw new Error(json.error || 'Failed to load org tree');
            })
            .finally(function () { _orgTreeLoading = null; });
        return _orgTreeLoading;
    }

    var _currentUserCache = null;

    function fetchCurrentUser() {
        if (_currentUserCache) return Promise.resolve(_currentUserCache);
        return fetch(window.__BP + '/api/form-center/current-user')
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json.success) {
                    _currentUserCache = json.data;
                    return _currentUserCache;
                }
                throw new Error(json.error || 'Failed to load current user');
            });
    }

    // ========================================
    // 工具：從 tree data 中依 secure_code 找人
    // ========================================
    function findPersonInTree(nodes, sc) {
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (n.data && n.data.type === 'person' && n.data.secure_code === sc) {
                return n.data;
            }
            if (n.children && n.children.length) {
                var found = findPersonInTree(n.children, sc);
                if (found) return found;
            }
        }
        return null;
    }

    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ========================================
    // 模態框管理（全域單例）
    // ========================================
    var _modal = null;
    var _treeInstance = null;
    var _onSelect = null;
    var _fullTreeData = null;

    function _ensureModalDom() {
        if (_modal) return;

        var overlay = document.createElement('div');
        overlay.id = 'user-picker-modal-overlay';
        overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;width:100%;height:100%;'
            + 'background:rgba(0,0,0,0.4);z-index:10000;justify-content:center;align-items:center;';

        var dialog = document.createElement('div');
        dialog.style.cssText = 'background:#fff;border-radius:8px;width:480px;max-width:90vw;'
            + 'max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,0.2);';

        // header
        var header = document.createElement('div');
        header.style.cssText = 'padding:12px 16px;border-bottom:1px solid #e5e7eb;display:flex;'
            + 'justify-content:space-between;align-items:center;flex-shrink:0;';
        header.innerHTML = '<span style="font-weight:600;font-size:15px;">選擇人員</span>';
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.textContent = 'X';
        closeBtn.style.cssText = 'border:none;background:none;font-size:16px;cursor:pointer;'
            + 'color:#6b7280;padding:2px 6px;';
        closeBtn.onclick = function () { _closeModal(); };
        header.appendChild(closeBtn);

        // search
        var searchBar = document.createElement('div');
        searchBar.style.cssText = 'padding:8px 16px;border-bottom:1px solid #f3f4f6;flex-shrink:0;';
        var searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.placeholder = '搜尋姓名...';
        searchInput.id = 'user-picker-search';
        searchInput.style.cssText = 'width:100%;padding:6px 10px;border:1px solid #d1d5db;'
            + 'border-radius:4px;font-size:13px;outline:none;';
        searchBar.appendChild(searchInput);

        // body (tree container)
        var body = document.createElement('div');
        body.id = 'user-picker-tree-container';
        body.style.cssText = 'flex:1;overflow-y:auto;padding:8px 0;min-height:200px;';

        // footer
        var footer = document.createElement('div');
        footer.style.cssText = 'padding:10px 16px;border-top:1px solid #e5e7eb;text-align:right;flex-shrink:0;';
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.textContent = '取消';
        cancelBtn.style.cssText = 'padding:6px 16px;border:1px solid #d1d5db;background:#fff;'
            + 'border-radius:4px;cursor:pointer;font-size:13px;';
        cancelBtn.onclick = function () { _closeModal(); };
        footer.appendChild(cancelBtn);

        dialog.appendChild(header);
        dialog.appendChild(searchBar);
        dialog.appendChild(body);
        dialog.appendChild(footer);
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        _modal = overlay;

        // 搜尋過濾
        var searchTimer = null;
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                _filterTree(searchInput.value.trim());
            }, 200);
        });
    }

    function _openModal(onSelect) {
        _ensureModalDom();
        _onSelect = onSelect;
        _modal.style.display = 'flex';
        var searchInput = document.getElementById('user-picker-search');
        if (searchInput) {
            searchInput.value = '';
            setTimeout(function () { searchInput.focus(); }, 100);
        }
        _loadTree();
    }

    function _closeModal() {
        if (_modal) _modal.style.display = 'none';
        _onSelect = null;
    }

    function _loadTree() {
        var container = document.getElementById('user-picker-tree-container');
        if (!container) return;
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#9ca3af;">載入中...</div>';

        fetchOrgTree().then(function (data) {
            _fullTreeData = data;
            _renderTree(data);
        }).catch(function (err) {
            container.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626;">載入失敗: '
                + escapeHtml(err.message) + '</div>';
        });
    }

    function _renderTree(data) {
        var container = document.getElementById('user-picker-tree-container');
        if (!container) return;
        container.innerHTML = '';

        if (_treeInstance) {
            _treeInstance.destroy();
            _treeInstance = null;
        }

        if (typeof BeakTree === 'undefined') {
            _renderFallbackList(container, data);
            return;
        }

        _treeInstance = new BeakTree(container, {
            data: data,
            treeMode: 'lines-dom',
            checkbox: false,
            hideRoot: true,
            maxExpanded: 500,
            onNodeClick: function (id, node) {
                if (node.data && node.data.type === 'person') {
                    if (_onSelect) {
                        _onSelect({
                            secure_code: node.data.secure_code,
                            username: node.data.username || '',
                            display_name: node.data.display_name,
                            dept_name: node.data.dept_name || '',
                        });
                    }
                    _closeModal();
                }
            }
        });
        _treeInstance.render();
        _stylizePersonNodes(container);
    }

    function _stylizePersonNodes(container) {
        var rows = container.querySelectorAll('tr[data-node-id]');
        rows.forEach(function (row) {
            var nodeId = row.getAttribute('data-node-id');
            if (nodeId && !nodeId.startsWith('dept_') && nodeId !== 'root') {
                row.style.cursor = 'pointer';
                row.addEventListener('mouseenter', function () { row.style.backgroundColor = '#eff6ff'; });
                row.addEventListener('mouseleave', function () { row.style.backgroundColor = ''; });
            }
        });
    }

    function _filterTree(query) {
        if (!_fullTreeData) return;
        if (!query) { _renderTree(_fullTreeData); return; }
        var filtered = _filterNodes(_fullTreeData, query.toLowerCase());
        _renderTree(filtered);
    }

    function _filterNodes(nodes, query) {
        var result = [];
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (n.data && n.data.type === 'person') {
                var name = (n.data.display_name || n.label || '').toLowerCase();
                if (name.indexOf(query) >= 0) {
                    result.push(n);
                }
            } else if (n.children && n.children.length) {
                var childResult = _filterNodes(n.children, query);
                if (childResult.length > 0) {
                    result.push({
                        id: n.id, label: n.label, expanded: true,
                        data: n.data, children: childResult,
                    });
                }
            }
        }
        return result;
    }

    function _renderFallbackList(container, nodes) {
        var list = document.createElement('div');
        list.style.cssText = 'padding:8px 16px;';

        function _walk(items, depth) {
            for (var i = 0; i < items.length; i++) {
                var n = items[i];
                var div = document.createElement('div');
                div.style.cssText = 'padding:4px 8px;padding-left:' + (depth * 20 + 8) + 'px;font-size:13px;'
                    + 'cursor:' + (n.data && n.data.type === 'person' ? 'pointer' : 'default') + ';';

                if (n.data && n.data.type === 'person') {
                    div.textContent = n.label;
                    div.style.color = '#1d4ed8';
                    (function (nodeData) {
                        div.addEventListener('click', function () {
                            if (_onSelect) {
                                _onSelect({
                                    secure_code: nodeData.secure_code,
                                    username: nodeData.username || '',
                                    display_name: nodeData.display_name,
                                    dept_name: nodeData.dept_name || '',
                                });
                            }
                            _closeModal();
                        });
                        div.addEventListener('mouseenter', function () { div.style.backgroundColor = '#eff6ff'; });
                        div.addEventListener('mouseleave', function () { div.style.backgroundColor = ''; });
                    })(n.data);
                } else {
                    div.textContent = n.label;
                    div.style.fontWeight = '600';
                    div.style.color = '#374151';
                }

                list.appendChild(div);
                if (n.children && n.children.length) { _walk(n.children, depth + 1); }
            }
        }

        _walk(nodes, 0);
        container.appendChild(list);
    }

    // ========================================
    // Form.io 自訂元件 (ES6 class 繼承)
    // ========================================

    var FieldComponent = Formio.Components.components.field;

    class UserPickerComponent extends FieldComponent {

        static schema(...extend) {
            return FieldComponent.schema({
                type: 'userPicker',
                label: '人員選擇',
                key: 'user_picker',
                input: true,
                tableView: true,
                persistent: true,
            }, ...extend);
        }

        static get builderInfo() {
            return {
                title: '人員選擇',
                group: 'custom',
                icon: 'fa fa-user',
                weight: 10,
                schema: UserPickerComponent.schema(),
            };
        }

        static editForm() {
            return FieldComponent.editForm([
                {
                    key: 'display',
                    components: [
                        { key: 'label', type: 'textfield', label: '欄位標籤', input: true, weight: 0 },
                        { key: 'key', type: 'textfield', label: '欄位 Key', input: true, weight: 10 },
                        { key: 'description', type: 'textfield', label: '說明文字', input: true, weight: 20 },
                    ],
                },
                {
                    key: 'validation',
                    components: [
                        { key: 'validate.required', type: 'checkbox', label: '必填', input: true, weight: 0 },
                    ],
                },
            ]);
        }

        get defaultSchema() {
            return UserPickerComponent.schema();
        }

        get inputInfo() {
            var info = super.inputInfo;
            info.type = 'input';
            info.attr.type = 'hidden';
            return info;
        }

        init() {
            super.init();
            if (this._pickerDisplayName === undefined) {
                this._pickerDisplayName = '';
                this._pickerUsername = '';
                this._pickerDeptName = '';
                this._defaultLoaded = false;
                this._resolving = false;
            }
        }

        render() {
            var value = this.dataValue || '';
            var displayText = this._pickerDisplayName
                || (value ? '載入中...' : '(未選擇)');
            if (this._pickerUsername && this._pickerDisplayName !== this._pickerUsername) {
                displayText += ' (' + this._pickerUsername + ')';
            }
            var deptText = this._pickerDeptName ? ' / ' + this._pickerDeptName : '';

            var tpl = '<div ref="userPickerWrapper" style="display:flex;align-items:center;gap:8px;">'
                + '<div ref="userPickerDisplay" style="flex:1;padding:6px 10px;border:1px solid #d1d5db;'
                + 'border-radius:4px;background:#f9fafb;font-size:13px;min-height:34px;'
                + 'display:flex;align-items:center;">'
                + '<span ref="userPickerName" style="color:#111827;">' + escapeHtml(displayText) + '</span>'
                + '<span ref="userPickerDept" style="color:#9ca3af;margin-left:4px;font-size:12px;">'
                + escapeHtml(deptText) + '</span>'
                + '</div>';

            if (!this.options.readOnly && !this.component.disabled) {
                tpl += '<button type="button" ref="userPickerBtn" class="btn btn-sm btn-outline-secondary" '
                    + 'style="white-space:nowrap;padding:5px 12px;font-size:13px;">'
                    + '<i class="fas fa-sitemap" style="margin-right:4px;"></i>選擇</button>';
            }

            tpl += '</div>';

            return super.render(tpl);
        }

        attach(element) {
            this.loadRefs(element, {
                userPickerWrapper: 'single',
                userPickerDisplay: 'single',
                userPickerName: 'single',
                userPickerDept: 'single',
                userPickerBtn: 'single',
            });

            var self = this;

            if (this.refs.userPickerBtn) {
                this.addEventListener(this.refs.userPickerBtn, 'click', function () {
                    _openModal(function (person) {
                        self._setSelectedUser(person);
                    });
                });
            }

            // 延遲一個 tick，讓 Form.io 的 submission = { data } 先設定完成
            // 延遲一個 tick，讓 Form.io 的 submission = { data } 先設定完成
            setTimeout(function () {
                var curVal = self.dataValue || '';
                if (curVal && !self._pickerDisplayName && !self._resolving) {
                    self._resolving = true;
                    self._resolveDisplay(curVal);
                } else if (!self._defaultLoaded && !curVal && !self.options.readOnly) {
                    self._defaultLoaded = true;
                    fetchCurrentUser().then(function (user) {
                        if (!self.dataValue) {
                            self._setSelectedUser({
                                secure_code: user.secure_code,
                                username: user.username || '',
                                display_name: user.display_name,
                                dept_name: user.dept_name,
                            });
                        }
                    }).catch(function () {});
                }
            }, 0);

            return super.attach(element);
        }

        getValueAt(index) {
            return this.dataValue;
        }

        setValueAt(index, value) {
            this.dataValue = value;
        }

        getValueAsString(value) {
            if (this._pickerDisplayName) {
                var text = this._pickerDisplayName;
                if (this._pickerUsername && this._pickerDisplayName !== this._pickerUsername) {
                    text += ' (' + this._pickerUsername + ')';
                }
                if (this._pickerDeptName) text += ' / ' + this._pickerDeptName;
                return text;
            }
            return value ? '載入中...' : '(未選擇)';
        }

        _setSelectedUser(person) {
            this._pickerDisplayName = person.display_name;
            this._pickerUsername = person.username || '';
            this._pickerDeptName = person.dept_name || '';
            this.setValue(person.secure_code);
            this._updateDisplay();
        }

        _updateDisplay() {
            if (this.refs.userPickerName) {
                var nameText = this._pickerDisplayName || this.dataValue || '(未選擇)';
                if (this._pickerUsername && this._pickerDisplayName && this._pickerDisplayName !== this._pickerUsername) {
                    nameText += ' (' + this._pickerUsername + ')';
                }
                this.refs.userPickerName.textContent = nameText;
            }
            if (this.refs.userPickerDept) {
                this.refs.userPickerDept.textContent = this._pickerDeptName ? ' / ' + this._pickerDeptName : '';
            }
        }

        _resolveDisplay(secureCode) {
            var self = this;
            fetchOrgTree().then(function (data) {
                var person = findPersonInTree(data, secureCode);
                self._resolving = false;
                if (person) {
                    self._pickerDisplayName = person.display_name;
                    self._pickerUsername = person.username || '';
                    self._pickerDeptName = person.dept_name || '';
                    self._updateDisplay();
                    if (self.options.readOnly) {
                        self.redraw();
                    }
                }
            }).catch(function () {
                self._resolving = false;
            });
        }
    }

    // ========================================
    // 透過 Formio.use() 註冊
    // ========================================
    Formio.use({
        components: {
            userPicker: UserPickerComponent,
        },
    });

    console.log('[UserPicker] Form.io userPicker component registered');
})();
