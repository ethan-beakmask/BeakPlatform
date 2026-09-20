/**
 * Form.io ProxyFormPicker 自訂元件（代理指定申請單的「限定表單」欄位）
 *
 * 值：{ mode: "all" | "limited", forms: ["<form_template_secure_code>", ...] }
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[ProxyFormPicker] Formio is not loaded');
        return;
    }
    if (!window.BkFormPickerBase) {
        console.error('[ProxyFormPicker] BkFormPickerBase is not loaded');
        return;
    }

    var Base = window.BkFormPickerBase;
    var fetchOptions = Base.createOptionsLoader(function () {
        return window.__BP + '/api/form-center/published-form-templates';
    });
    var FieldComponent = Formio.Components.components.field;

    function normalizeValue(value) {
        if (Array.isArray(value)) {
            return value.length
                ? { mode: 'limited', forms: normalizeForms(value) }
                : { mode: 'all', forms: [] };
        }
        if (!value || typeof value !== 'object') {
            return { mode: 'all', forms: [] };
        }
        var mode = value.mode === 'limited' ? 'limited' : 'all';
        return {
            mode: mode,
            forms: mode === 'limited' ? normalizeForms(value.forms) : [],
        };
    }

    function normalizeForms(value) {
        if (!Array.isArray(value)) return [];
        var forms = [];
        value.forEach(function (item) {
            if (typeof item !== 'string') return;
            var sc = item.trim();
            if (sc && forms.indexOf(sc) < 0) forms.push(sc);
        });
        return forms;
    }

    class ProxyFormPickerComponent extends FieldComponent {
        static schema(...extend) {
            return FieldComponent.schema({
                type: 'proxyFormPicker',
                label: __('限定表單'),
                key: 'authorized_forms',
                input: true,
                tableView: true,
                persistent: true,
            }, ...extend);
        }

        static get builderInfo() {
            return {
                title: __('代理限定表單選擇'),
                group: 'systemForms',
                icon: 'fa fa-list-check',
                weight: 12,
                schema: ProxyFormPickerComponent.schema(),
            };
        }

        static editForm() {
            return FieldComponent.editForm([
                {
                    key: 'display',
                    components: [
                        {
                            key: 'proxyFormPickerHelp',
                            type: 'htmlelement',
                            tag: 'div',
                            input: false,
                            content: __('代理指定申請單專用：讓申請人限定代理人只能代簽哪幾種表單。流程中需搭配 OpProxyGrant 節點；單獨放進一般表單沒有作用。'),
                            weight: -10,
                        },
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
            return ProxyFormPickerComponent.schema();
        }

        get emptyValue() {
            return { mode: 'all', forms: [] };
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
                this._pickerFilter = '';
            }
        }

        render() {
            var value = normalizeValue(this.dataValue);
            var limitedChecked = value.mode === 'limited' ? ' checked' : '';
            var allChecked = value.mode === 'limited' ? '' : ' checked';
            var tpl = '<div ref="pfpRoot" class="bk-proxy-form-picker">';
            if (!this.isPickerReadOnly) {
                tpl += '<div ref="pfpModes" style="display:grid;gap:6px;margin-bottom:8px;">'
                    + '<label style="display:flex;gap:8px;align-items:flex-start;">'
                    + '<input ref="pfpModeAll" type="radio" name="' + this.id + '-mode" value="all"' + allChecked + '>'
                    + '<span>' + Base.escapeHtml(__('不限：代理人可代簽所委任角色的所有表單')) + '</span></label>'
                    + '<label style="display:flex;gap:8px;align-items:flex-start;">'
                    + '<input ref="pfpModeLimited" type="radio" name="' + this.id + '-mode" value="limited"' + limitedChecked + '>'
                    + '<span>' + Base.escapeHtml(__('限定以下表單')) + '</span></label>'
                    + '</div>'
                    + '<div ref="pfpLimitedBox">'
                    + '<input ref="pfpSearch" type="text" class="form-control" '
                    + 'placeholder="' + Base.escapeHtml(__('搜尋表單名稱或代碼...')) + '" '
                    + 'style="margin-bottom:6px;font-size:13px;padding:6px 10px;">';
            }
            tpl += '<div ref="pfpList" style="border:1px solid #d1d5db;border-radius:4px;'
                + 'max-height:240px;overflow-y:auto;background:#fff;font-size:13px;"></div>'
                + '<div ref="pfpSummary" style="margin-top:4px;font-size:12px;color:#6b7280;"></div>';
            if (!this.isPickerReadOnly) tpl += '</div>';
            tpl += '</div>';
            return super.render(tpl);
        }

        attach(element) {
            this.loadRefs(element, {
                pfpRoot: 'single',
                pfpModes: 'single',
                pfpModeAll: 'single',
                pfpModeLimited: 'single',
                pfpLimitedBox: 'single',
                pfpSearch: 'single',
                pfpList: 'single',
                pfpSummary: 'single',
            });

            var self = this;
            if (this.refs.pfpModeAll) {
                this.addEventListener(this.refs.pfpModeAll, 'change', function () {
                    if (self.refs.pfpModeAll.checked) self._setMode('all');
                });
            }
            if (this.refs.pfpModeLimited) {
                this.addEventListener(this.refs.pfpModeLimited, 'change', function () {
                    if (self.refs.pfpModeLimited.checked) self._setMode('limited');
                });
            }
            if (this.refs.pfpSearch) {
                this.refs.pfpSearch.value = this._pickerFilter || '';
                var timer = null;
                this.addEventListener(this.refs.pfpSearch, 'input', function () {
                    clearTimeout(timer);
                    timer = setTimeout(function () {
                        self._pickerFilter = self.refs.pfpSearch.value.trim();
                        self._renderList();
                    }, 200);
                });
            }

            this._renderList();
            this._loadOptions();
            return super.attach(element);
        }

        setValue(value, flags) {
            var changed = super.setValue(normalizeValue(value), flags);
            if (this.refs && this.refs.pfpList) {
                this._renderList();
            }
            return changed;
        }

        getValueAt(index) {
            return normalizeValue(this.dataValue);
        }

        setValueAt(index, value) {
            this.dataValue = normalizeValue(value);
        }

        getValueAsString(value) {
            var normalized = normalizeValue(value || this.dataValue);
            if (normalized.mode !== 'limited') return __('不限');
            if (!normalized.forms.length) return __('(未選擇)');
            return Base.selectedLabels(
                normalized.forms,
                this._pickerOptions || [],
                __('(無法解析：可能已停用)'));
        }

        checkValidity(data, dirty, row, options) {
            var valid = super.checkValidity(data, dirty, row, options);
            var value = normalizeValue(this.dataValue);
            if (value.mode === 'limited' && !value.forms.length) {
                this.setCustomValidity(__('請至少勾選一張表單，或改選「不限」'), dirty);
                return false;
            }
            if (valid) this.setCustomValidity('', dirty);
            return valid;
        }

        _loadOptions() {
            var self = this;
            fetchOptions('').then(function (opts) {
                self._pickerOptions = opts;
                self._pickerError = '';
                self._renderList();
            }).catch(function (err) {
                self._pickerOptions = [];
                self._pickerError = err && err.message ? err.message : __('載入失敗');
                // 載入失敗時不動已選值：清空會讓使用者以為送出了不限定的委任。
                self._renderList();
            });
        }

        _setMode(mode) {
            var value = normalizeValue(this.dataValue);
            if (mode === 'all') {
                this.setValue({ mode: 'all', forms: [] }, { modified: true });
            } else {
                this.setValue({ mode: 'limited', forms: value.forms || [] }, { modified: true });
            }
            this._renderList();
        }

        _renderList() {
            if (!this.refs.pfpList) return;
            var value = normalizeValue(this.dataValue);
            if (this.refs.pfpLimitedBox) {
                this.refs.pfpLimitedBox.style.display = value.mode === 'limited' ? '' : 'none';
            }
            if (this.refs.pfpModeAll) this.refs.pfpModeAll.checked = value.mode !== 'limited';
            if (this.refs.pfpModeLimited) this.refs.pfpModeLimited.checked = value.mode === 'limited';

            if (value.mode !== 'limited' && !this.isPickerReadOnly) {
                this.refs.pfpList.innerHTML = '';
                this._renderSummary();
                return;
            }
            if (this.isPickerReadOnly && value.mode !== 'limited') {
                this.refs.pfpList.innerHTML = '<div style="padding:12px;color:#111827;">'
                    + Base.escapeHtml(__('不限')) + '</div>';
                this._renderSummary();
                return;
            }

            Base.renderPickerList({
                list: this.refs.pfpList,
                options: this._pickerOptions,
                selected: value.forms,
                filter: this._pickerFilter,
                readOnly: this.isPickerReadOnly,
                unresolvedSuffix: __('(無法解析：可能已停用)'),
                emptyMessage: this._pickerError
                    || (this._pickerFilter ? __('沒有符合的表單') : __('沒有已發行表單')),
                onToggle: this._toggle.bind(this),
            });
            this._renderSummary();
        }

        _renderSummary() {
            if (!this.refs.pfpSummary) return;
            var value = normalizeValue(this.dataValue);
            var parts = value.mode === 'limited'
                ? [__('已選 {n} 張', {n: value.forms.length})]
                : [__('不限')];
            if (this._pickerError) {
                parts.push(this._pickerError);
                this.refs.pfpSummary.style.color = '#b45309';
            } else {
                this.refs.pfpSummary.style.color = '#6b7280';
            }
            this.refs.pfpSummary.textContent = parts.join(' / ');
        }

        _toggle(sc, checked) {
            var value = normalizeValue(this.dataValue);
            var cur = value.forms.slice();
            var idx = cur.indexOf(sc);
            if (checked && idx < 0) cur.push(sc);
            if (!checked && idx >= 0) cur.splice(idx, 1);
            this.setValue({ mode: 'limited', forms: cur }, { modified: true });
            this._renderSummary();
        }
    }

    Formio.use({
        components: {
            proxyFormPicker: ProxyFormPickerComponent,
        },
    });

    console.log('[ProxyFormPicker] Form.io proxyFormPicker component registered');
})();
