/**
 * Form.io MyRolePicker 自訂元件（代理指定申請單的「要委任的角色」欄位）
 *
 * 功能：
 *   - 多選「登入者本人目前 regular 持有且可委任」的角色@單位
 *   - 值存物件陣列：[{role_secure_code, unit_secure_code}]
 *
 * 前端過濾只是體驗，不是防線：OpProxyGrant 節點會在執行當下用
 * proxy_assignment_service.proxyable_regular_assignments() 重驗一次。
 *
 * 依賴：Form.io (Formio global)
 * 註冊方式：Formio.use() 外掛，升級 Form.io 不受影響
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[MyRolePicker] Formio is not loaded');
        return;
    }

    var _optionsCache = null;
    var _loadingPromise = null;

    function fetchOptions() {
        if (_optionsCache) return Promise.resolve(_optionsCache);
        if (_loadingPromise) return _loadingPromise;

        _loadingPromise = fetch(window.__BP + '/api/my-proxy-assignments/my-roles')
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json && json.success) {
                    _optionsCache = json.data || [];
                    return _optionsCache;
                }
                throw new Error((json && json.message) || __('載入失敗'));
            })
            .finally(function () { _loadingPromise = null; });

        return _loadingPromise;
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        var div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    function normalizeItem(value) {
        if (!value || typeof value !== 'object') return null;
        var roleSc = String(value.role_secure_code || '').trim();
        if (!roleSc) return null;
        var unitRaw = value.unit_secure_code;
        var unitSc = unitRaw === null || unitRaw === undefined ? null : String(unitRaw).trim();
        // role_name / unit_name 是勾選當下的名稱快照。簽核者看這張單時，選項清單
        // 載入的是「簽核者自己」的角色，解析不到申請人的角色；沒有快照就只能顯示
        // secure_code，等於要對方盲簽。後端 handler 只讀兩個 secure_code 欄位。
        return {
            role_secure_code: roleSc,
            unit_secure_code: unitSc || null,
            role_name: String(value.role_name || '').trim() || null,
            unit_name: String(value.unit_name || '').trim() || null,
        };
    }

    function itemLabel(item) {
        if (!item) return '';
        if (item.role_name) {
            return item.role_name + (item.unit_name ? '@' + item.unit_name : '');
        }
        return '';
    }

    function itemKey(value) {
        var item = normalizeItem(value);
        if (!item) return '';
        return item.role_secure_code + '|' + (item.unit_secure_code || '');
    }

    function optionLabel(opt) {
        if (!opt) return '';
        return opt.role_name + (opt.unit_name ? '@' + opt.unit_name : '');
    }

    var FieldComponent = Formio.Components.components.field;

    class MyRolePickerComponent extends FieldComponent {

        static schema(...extend) {
            return FieldComponent.schema({
                type: 'myRolePicker',
                label: __('要委任的角色'),
                key: 'proxy_roles',
                input: true,
                tableView: true,
                persistent: true,
            }, ...extend);
        }

        static get builderInfo() {
            return {
                title: __('我的角色選擇'),
                group: 'custom',
                icon: 'fa fa-user-shield',
                weight: 12,
                schema: MyRolePickerComponent.schema(),
            };
        }

        static editForm() {
            return FieldComponent.editForm([
                {
                    key: 'display',
                    components: [
                        { key: 'label', type: 'textfield', label: __('欄位標籤'), input: true, weight: 0 },
                        { key: 'key', type: 'textfield', label: __('欄位 Key'), input: true, weight: 10 },
                        { key: 'description', type: 'textfield', label: __('說明文字'), input: true, weight: 20 },
                    ],
                },
                {
                    key: 'validation',
                    components: [
                        { key: 'validate.required', type: 'checkbox', label: __('必填'), input: true, weight: 0 },
                    ],
                },
            ]);
        }

        get defaultSchema() {
            return MyRolePickerComponent.schema();
        }

        get emptyValue() {
            return [];
        }

        get inputInfo() {
            var info = super.inputInfo;
            info.type = 'input';
            info.attr.type = 'hidden';
            return info;
        }

        get isPickerReadOnly() {
            return !!(this.options.readOnly || this.component.disabled || this.disabled);
        }

        init() {
            super.init();
            if (this._pickerOptions === undefined) {
                this._pickerOptions = null;
                this._pickerError = '';
            }
        }

        render() {
            var tpl = '<div ref="mrpRoot" class="bk-my-role-picker">'
                + '<div ref="mrpList" style="border:1px solid #d1d5db;border-radius:4px;'
                + 'max-height:240px;overflow-y:auto;background:#fff;font-size:13px;"></div>'
                + '<div ref="mrpSummary" style="margin-top:4px;font-size:12px;color:#6b7280;"></div>'
                + '</div>';
            return super.render(tpl);
        }

        attach(element) {
            this.loadRefs(element, {
                mrpRoot: 'single',
                mrpList: 'single',
                mrpSummary: 'single',
            });

            this._renderList();
            this._loadOptions();
            return super.attach(element);
        }

        setValue(value, flags) {
            var changed = super.setValue(value, flags);
            // Form.io 先 attach 再由 submission 設值；唯讀檢視（簽核、已完成單）
            // 不在這裡重繪的話，畫面會停在 attach 當下的空狀態，顯示「已選 0 個角色」
            // 但 dataValue 其實有值。可編輯時不重繪：勾選是使用者自己觸發的，
            // 重建整個清單會讓捲動位置與焦點跳掉。
            if (this.isPickerReadOnly && this.refs && this.refs.mrpList) {
                this._renderList();
            }
            return changed;
        }

        getValueAt(index) {
            return this.dataValue;
        }

        setValueAt(index, value) {
            this.dataValue = Array.isArray(value) ? value.map(normalizeItem).filter(Boolean) : [];
        }

        getValueAsString(value) {
            var items = Array.isArray(value) ? value : (this.dataValue || []);
            if (!items.length) return __('(未選擇)');
            var self = this;
            return items.map(function (item) {
                var normalized = normalizeItem(item);
                var snapshot = itemLabel(normalized);
                if (snapshot) return snapshot;
                var opt = self._findOption(item);
                if (opt) return optionLabel(opt);
                return normalized ? normalized.role_secure_code : '';
            }).filter(Boolean).join('、');
        }

        _loadOptions() {
            var self = this;
            fetchOptions().then(function (opts) {
                self._pickerOptions = opts;
                self._pickerError = '';
                self._renderList();
            }).catch(function (err) {
                self._pickerOptions = [];
                self._pickerError = err && err.message ? err.message : __('載入失敗');
                // 載入失敗時不動已選值：清空會讓使用者以為送出了空委任。
                self._renderList();
            });
        }

        _findOption(value) {
            var key = itemKey(value);
            if (!key) return null;
            var opts = this._pickerOptions || [];
            for (var i = 0; i < opts.length; i++) {
                if (itemKey(opts[i]) === key) return opts[i];
            }
            return null;
        }

        _renderList() {
            if (!this.refs.mrpList) return;
            var list = this.refs.mrpList;
            list.innerHTML = '';

            if (this._pickerOptions === null) {
                list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                    + escapeHtml(__('載入中...')) + '</div>';
                this._renderSummary();
                return;
            }

            var selected = Array.isArray(this.dataValue)
                ? this.dataValue.map(normalizeItem).filter(Boolean)
                : [];

            if (this.isPickerReadOnly) {
                this._renderReadOnly(list, selected);
                this._renderSummary();
                return;
            }

            var items = this._pickerOptions || [];
            if (!items.length) {
                list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                    + escapeHtml(this._pickerError || __('你目前沒有可委任的角色'))
                    + '</div>';
                this._renderSummary();
                return;
            }

            var selectedKeys = selected.map(itemKey);
            var self = this;
            items.forEach(function (opt) {
                var row = document.createElement('label');
                row.style.cssText = 'display:flex;align-items:flex-start;gap:8px;'
                    + 'padding:6px 10px;cursor:pointer;border-bottom:1px solid #f3f4f6;';

                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = selectedKeys.indexOf(itemKey(opt)) >= 0;
                cb.style.cssText = 'margin-top:2px;flex-shrink:0;';
                cb.addEventListener('change', function () {
                    self._toggle(opt, cb.checked);
                });

                var text = document.createElement('span');
                text.style.cssText = 'flex:1;line-height:1.4;color:#111827;';
                text.textContent = optionLabel(opt);

                row.appendChild(cb);
                row.appendChild(text);
                row.addEventListener('mouseenter', function () { row.style.backgroundColor = '#f9fafb'; });
                row.addEventListener('mouseleave', function () { row.style.backgroundColor = ''; });
                list.appendChild(row);
            });

            this._renderSummary();
        }

        _renderReadOnly(list, selected) {
            if (!selected.length) {
                list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                    + escapeHtml(__('(未選擇)')) + '</div>';
                return;
            }
            var self = this;
            selected.forEach(function (item) {
                var opt = self._findOption(item);
                var label = itemLabel(item) || (opt ? optionLabel(opt) : '');
                var row = document.createElement('div');
                row.style.cssText = 'padding:6px 10px;border-bottom:1px solid #f3f4f6;line-height:1.4;';
                if (label) {
                    row.innerHTML = '<span style="color:#111827;">' + escapeHtml(label) + '</span>';
                } else {
                    row.innerHTML = '<span style="color:#111827;">' + escapeHtml(item.role_secure_code) + '</span>'
                        + '<span style="color:#b45309;margin-left:6px;font-size:12px;">'
                        + escapeHtml(__('(無法解析：可能已撤銷或不再持有)')) + '</span>';
                }
                list.appendChild(row);
            });
        }

        _renderSummary() {
            if (!this.refs.mrpSummary) return;
            var selected = Array.isArray(this.dataValue) ? this.dataValue : [];
            var parts = [__('已選 {n} 個角色', {n: selected.length})];
            if (this._pickerError) {
                parts.push(this._pickerError);
                this.refs.mrpSummary.style.color = '#b45309';
            } else {
                this.refs.mrpSummary.style.color = '#6b7280';
            }
            this.refs.mrpSummary.textContent = parts.join(' / ');
        }

        _toggle(opt, checked) {
            var cur = Array.isArray(this.dataValue)
                ? this.dataValue.map(normalizeItem).filter(Boolean)
                : [];
            var key = itemKey(opt);
            var idx = cur.map(itemKey).indexOf(key);
            if (checked && idx < 0) {
                cur.push({
                    role_secure_code: opt.role_secure_code,
                    unit_secure_code: opt.unit_secure_code || null,
                    role_name: opt.role_name || null,
                    unit_name: opt.unit_name || null,
                });
            }
            if (!checked && idx >= 0) cur.splice(idx, 1);
            this.setValue(cur, { modified: true });
            this._renderSummary();
        }
    }

    Formio.use({
        components: {
            myRolePicker: MyRolePickerComponent,
        },
    });

    console.log('[MyRolePicker] Form.io myRolePicker component registered');
})();
