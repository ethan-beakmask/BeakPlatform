/**
 * Form.io FormPicker 自訂元件（PF-160 API Key 申請單的「授權表單」欄位）
 *
 * 功能：
 *   - 多選「已發行且該使用者填得到」的表單模板，值存 fw_form_templates.secure_code 陣列
 *   - 選項來源依「被代申請人」計算，不是登入者 --
 *     依登入者算的話，A 可以幫 B 申請一把「B 手動填不到的表單」的 key（提權）
 *   - 被代申請人（userPicker 欄位）改變時自動重載，並移除新對象填不到的已選項目
 *
 * 值：["<form_template_secure_code>", ...]
 *   對應 api_keys.scopes.form_template 與 ApiKeyIssue 節點的 forms_field。
 *
 * 前端過濾只是體驗，不是防線：核發前由 ApiKeyIssue handler 用
 * fill_permission_service 重驗一次（form_data 由送單人控制）。
 *
 * 依賴：Form.io (Formio global)
 * 註冊方式：Formio.use() 外掛，升級 Form.io 不受影響
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[FormPicker] Formio is not loaded');
        return;
    }

    var DEFAULT_BENEFICIARY_KEY = 'beneficiary';

    // ========================================
    // 選項來源（依被代申請人快取）
    // ========================================
    var _optionsCache = {};   // userSc('' = 自己) -> [{secure_code, name, code, ...}]
    var _loadingCache = {};

    function fetchOptions(userSc) {
        var cacheKey = userSc || '';
        if (_optionsCache[cacheKey]) return Promise.resolve(_optionsCache[cacheKey]);
        if (_loadingCache[cacheKey]) return _loadingCache[cacheKey];

        var url = window.__BP + '/api/form-center/fillable-form-templates';
        if (cacheKey) url += '?user=' + encodeURIComponent(cacheKey);

        _loadingCache[cacheKey] = fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (json) {
                if (json && json.success) {
                    _optionsCache[cacheKey] = json.data || [];
                    return _optionsCache[cacheKey];
                }
                throw new Error((json && json.message) || __('載入失敗'));
            })
            .finally(function () { delete _loadingCache[cacheKey]; });

        return _loadingCache[cacheKey];
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        var div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    // ========================================
    // Form.io 自訂元件
    // ========================================
    var FieldComponent = Formio.Components.components.field;

    class FormPickerComponent extends FieldComponent {

        static schema(...extend) {
            return FieldComponent.schema({
                type: 'formPicker',
                label: __('授權表單'),
                key: 'authorized_forms',
                input: true,
                tableView: true,
                persistent: true,
                beneficiaryKey: DEFAULT_BENEFICIARY_KEY,
            }, ...extend);
        }

        static get builderInfo() {
            return {
                title: __('表單選擇'),
                group: 'custom',
                icon: 'fa fa-list-check',
                weight: 11,
                schema: FormPickerComponent.schema(),
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
                        {
                            key: 'beneficiaryKey',
                            type: 'textfield',
                            label: __('對象欄位 Key'),
                            tooltip: __('指向本表單中的人員選擇欄位；選項依該對象可填寫的表單計算。留空則依登入者本人。'),
                            defaultValue: DEFAULT_BENEFICIARY_KEY,
                            input: true,
                            weight: 30,
                        },
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
            return FormPickerComponent.schema();
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
                this._pickerOptions = null;      // null = 尚未載入
                this._pickerLoadedFor = undefined;
                this._pickerError = '';
                this._pickerFilter = '';
            }
        }

        render() {
            var tpl = '<div ref="fpRoot" class="bk-form-picker">';
            if (!this.isPickerReadOnly) {
                tpl += '<input ref="fpSearch" type="text" class="form-control" '
                    + 'placeholder="' + escapeHtml(__('搜尋表單名稱或代碼...')) + '" '
                    + 'style="margin-bottom:6px;font-size:13px;padding:6px 10px;">';
            }
            tpl += '<div ref="fpList" style="border:1px solid #d1d5db;border-radius:4px;'
                + 'max-height:240px;overflow-y:auto;background:#fff;font-size:13px;"></div>'
                + '<div ref="fpSummary" style="margin-top:4px;font-size:12px;color:#6b7280;"></div>'
                + '</div>';
            return super.render(tpl);
        }

        attach(element) {
            this.loadRefs(element, {
                fpRoot: 'single',
                fpSearch: 'single',
                fpList: 'single',
                fpSummary: 'single',
            });

            var self = this;

            if (this.refs.fpSearch) {
                this.refs.fpSearch.value = this._pickerFilter || '';
                var timer = null;
                this.addEventListener(this.refs.fpSearch, 'input', function () {
                    clearTimeout(timer);
                    timer = setTimeout(function () {
                        self._pickerFilter = self.refs.fpSearch.value.trim();
                        self._renderList();
                    }, 200);
                });
            }

            // 被代申請人改變時重載選項（Component.on 由 destroy 自動解綁）
            this.on('change', function () {
                self._syncBeneficiary();
            });

            this._renderList();
            // 延遲一個 tick，讓 Form.io 的 submission = { data } 先設定完成
            setTimeout(function () { self._syncBeneficiary(); }, 0);

            return super.attach(element);
        }

        getValueAt(index) {
            return this.dataValue;
        }

        setValueAt(index, value) {
            this.dataValue = Array.isArray(value) ? value : [];
        }

        getValueAsString(value) {
            var scs = Array.isArray(value) ? value : (this.dataValue || []);
            if (!scs.length) return __('(未選擇)');
            var self = this;
            return scs.map(function (sc) {
                var opt = self._findOption(sc);
                return opt ? (opt.name + (opt.code ? ' (' + opt.code + ')' : '')) : sc;
            }).join('、');
        }

        // ------------------------------------
        // 選項載入
        // ------------------------------------
        _beneficiarySc() {
            var key = this.component.beneficiaryKey;
            if (key === undefined) key = DEFAULT_BENEFICIARY_KEY;
            if (!key) return '';
            var data = (this.root && this.root.data) || {};
            var val = data[key];
            return typeof val === 'string' ? val.trim() : '';
        }

        _syncBeneficiary() {
            var sc = this._beneficiarySc();
            if (sc === this._pickerLoadedFor) return;
            this._pickerLoadedFor = sc;
            this._pickerOptions = null;
            this._pickerError = '';
            this._renderList();

            var self = this;
            fetchOptions(sc).then(function (opts) {
                if (self._pickerLoadedFor !== sc) return;   // 已被更新的請求取代
                self._pickerOptions = opts;
                self._pickerError = '';
                self._pruneValue();
                self._renderList();
            }).catch(function (err) {
                if (self._pickerLoadedFor !== sc) return;
                self._pickerOptions = [];
                self._pickerError = err && err.message ? err.message : __('載入失敗');
                // 載入失敗時不動已選值：清空會讓使用者以為送出了空授權
                self._renderList();
            });
        }

        _pruneValue() {
            // 換對象後移除新對象填不到的項目（唯讀檢視不改值，那是申請當下的內容）
            if (this.isPickerReadOnly) return;
            var cur = this.dataValue;
            if (!Array.isArray(cur) || !cur.length) return;
            var self = this;
            var kept = cur.filter(function (sc) { return !!self._findOption(sc); });
            if (kept.length !== cur.length) {
                this.setValue(kept, { modified: true });
            }
        }

        _findOption(sc) {
            var opts = this._pickerOptions || [];
            for (var i = 0; i < opts.length; i++) {
                if (opts[i].secure_code === sc) return opts[i];
            }
            return null;
        }

        // ------------------------------------
        // 清單渲染
        // ------------------------------------
        _renderList() {
            if (!this.refs.fpList) return;
            var list = this.refs.fpList;
            list.innerHTML = '';

            if (this._pickerOptions === null) {
                list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                    + escapeHtml(__('載入中...')) + '</div>';
                this._renderSummary();
                return;
            }

            var selected = Array.isArray(this.dataValue) ? this.dataValue : [];

            if (this.isPickerReadOnly) {
                this._renderReadOnly(list, selected);
                this._renderSummary();
                return;
            }

            var filter = (this._pickerFilter || '').toLowerCase();
            var items = this._pickerOptions.filter(function (o) {
                if (!filter) return true;
                return (o.name || '').toLowerCase().indexOf(filter) >= 0
                    || (o.code || '').toLowerCase().indexOf(filter) >= 0;
            });

            if (!items.length) {
                list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                    + escapeHtml(this._pickerError
                        || (filter ? __('沒有符合的表單') : __('沒有可申請的表單')))
                    + '</div>';
                this._renderSummary();
                return;
            }

            var self = this;
            var lastCategory = null;
            items.forEach(function (opt) {
                var catName = opt.category_name || __('未分類');
                if (catName !== lastCategory) {
                    lastCategory = catName;
                    var head = document.createElement('div');
                    head.style.cssText = 'padding:4px 10px;background:#f3f4f6;color:#374151;'
                        + 'font-weight:600;font-size:12px;position:sticky;top:0;';
                    head.textContent = catName;
                    list.appendChild(head);
                }

                var row = document.createElement('label');
                row.style.cssText = 'display:flex;align-items:flex-start;gap:8px;'
                    + 'padding:6px 10px;cursor:pointer;border-bottom:1px solid #f3f4f6;';

                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = opt.secure_code;
                cb.checked = selected.indexOf(opt.secure_code) >= 0;
                cb.style.cssText = 'margin-top:2px;flex-shrink:0;';
                cb.addEventListener('change', function () {
                    self._toggle(opt.secure_code, cb.checked);
                });

                var text = document.createElement('span');
                text.style.cssText = 'flex:1;line-height:1.4;';
                text.innerHTML = '<span style="color:#111827;">' + escapeHtml(opt.name) + '</span>'
                    + (opt.code ? '<span style="color:#9ca3af;margin-left:6px;font-size:12px;">'
                        + escapeHtml(opt.code) + '</span>' : '');

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
            selected.forEach(function (sc) {
                var opt = self._findOption(sc);
                var row = document.createElement('div');
                row.style.cssText = 'padding:6px 10px;border-bottom:1px solid #f3f4f6;line-height:1.4;';
                if (opt) {
                    row.innerHTML = '<span style="color:#111827;">' + escapeHtml(opt.name) + '</span>'
                        + (opt.code ? '<span style="color:#9ca3af;margin-left:6px;font-size:12px;">'
                            + escapeHtml(opt.code) + '</span>' : '');
                } else {
                    row.innerHTML = '<span style="color:#111827;">' + escapeHtml(sc) + '</span>'
                        + '<span style="color:#b45309;margin-left:6px;font-size:12px;">'
                        + escapeHtml(__('(無法解析：可能已停用或超出對象權限)')) + '</span>';
                }
                list.appendChild(row);
            });
        }

        _renderSummary() {
            if (!this.refs.fpSummary) return;
            var selected = Array.isArray(this.dataValue) ? this.dataValue : [];
            var parts = [__('已選 {n} 張', {n: selected.length})];
            if (this._pickerError) {
                parts.push(this._pickerError);
                this.refs.fpSummary.style.color = '#b45309';
            } else {
                this.refs.fpSummary.style.color = '#6b7280';
            }
            this.refs.fpSummary.textContent = parts.join(' / ');
        }

        _toggle(sc, checked) {
            var cur = Array.isArray(this.dataValue) ? this.dataValue.slice() : [];
            var idx = cur.indexOf(sc);
            if (checked && idx < 0) cur.push(sc);
            if (!checked && idx >= 0) cur.splice(idx, 1);
            this.setValue(cur, { modified: true });
            this._renderSummary();
        }
    }

    Formio.use({
        components: {
            formPicker: FormPickerComponent,
        },
    });

    console.log('[FormPicker] Form.io formPicker component registered');
})();
