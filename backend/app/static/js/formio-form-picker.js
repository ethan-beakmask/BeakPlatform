/**
 * Form.io FormPicker 自訂元件（API Key 申請單的「授權表單」欄位）
 *
 * 值：["<form_template_secure_code>", ...]
 */
'use strict';

(function () {
    if (typeof Formio === 'undefined') {
        console.error('[FormPicker] Formio is not loaded');
        return;
    }
    if (!window.BkFormPickerBase) {
        console.error('[FormPicker] BkFormPickerBase is not loaded');
        return;
    }

    var Base = window.BkFormPickerBase;
    var DEFAULT_BENEFICIARY_KEY = 'beneficiary';
    var fetchOptions = Base.createOptionsLoader(function (cacheKey) {
        var url = window.__BP + '/api/form-center/fillable-form-templates';
        if (cacheKey) url += '?user=' + encodeURIComponent(cacheKey);
        return url;
    });

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
                title: __('API表單選擇'),
                group: 'systemForms',
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
                        {
                            key: 'apiFormPickerHelp',
                            type: 'htmlelement',
                            tag: 'div',
                            input: false,
                            content: __('API Key 申請單專用：讓申請人勾選這把 API Key 可以代填哪些表單，只列出 Key 歸屬人自己填得到的表單。流程中需搭配 ApiKeyIssue 節點；單獨放進一般表單沒有作用。'),
                            weight: -10,
                        },
                        { key: 'label', type: 'textfield', label: __('欄位標籤'), input: true, weight: 0 },
                        { key: 'key', type: 'textfield', label: __('欄位 Key'), input: true, weight: 10 },
                        { key: 'description', type: 'textfield', label: __('說明文字'), input: true, weight: 20 },
                        {
                            key: 'beneficiaryKey',
                            type: 'select',
                            label: __('Key 歸屬人欄位'),
                            defaultValue: DEFAULT_BENEFICIARY_KEY,
                            input: true,
                            weight: 30,
                            dataSrc: 'custom',
                            valueProperty: 'value',
                            template: '<span>{{ item.label }}</span>',
                            data: {
                                custom: [
                                    'values = [];',
                                    'var current = (data && data.beneficiaryKey !== undefined) ? data.beneficiaryKey : "";',
                                    'var seen = {};',
                                    'try {',
                                    '  var rootComponents = (((instance || {}).options || {}).editForm || {}).components || [];',
                                    '  Formio.Utils.eachComponent(rootComponents, function(component) {',
                                    '    if (component && component.type === "userPicker" && component.key) {',
                                    '      var label = (component.label || component.key) + " (" + component.key + ")";',
                                    '      values.push({ label: label, value: component.key });',
                                    '      seen[component.key] = true;',
                                    '    }',
                                    '  }, true);',
                                    '} catch (err) {}',
                                    'if (current && !seen[current]) values.push({ label: current + " (" + current + ")", value: current });',
                                ].join('\n'),
                            },
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
                this._pickerOptions = null;
                this._pickerLoadedFor = undefined;
                this._pickerError = '';
                this._pickerFilter = '';
            }
        }

        render() {
            var tpl = '<div ref="fpRoot" class="bk-form-picker">';
            if (!this.isPickerReadOnly) {
                tpl += '<input ref="fpSearch" type="text" class="form-control" '
                    + 'placeholder="' + Base.escapeHtml(__('搜尋表單名稱或代碼...')) + '" '
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

            this.on('change', function () {
                self._syncBeneficiary();
            });

            this._renderList();
            setTimeout(function () { self._syncBeneficiary(); }, 0);

            return super.attach(element);
        }

        setValue(value, flags) {
            var changed = super.setValue(value, flags);
            if (this.isPickerReadOnly && this.refs && this.refs.fpList) {
                this._renderList();
            }
            return changed;
        }

        getValueAt(index) {
            return this.dataValue;
        }

        setValueAt(index, value) {
            this.dataValue = Array.isArray(value) ? value : [];
        }

        getValueAsString(value) {
            var scs = Array.isArray(value) ? value : (this.dataValue || []);
            return Base.selectedLabels(scs, this._pickerOptions || []);
        }

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
                if (self._pickerLoadedFor !== sc) return;
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
            if (this.isPickerReadOnly) return;
            var cur = this.dataValue;
            if (!Array.isArray(cur) || !cur.length) return;
            var self = this;
            var kept = cur.filter(function (sc) {
                return !!Base.findOption(self._pickerOptions, sc);
            });
            if (kept.length !== cur.length) {
                this.setValue(kept, { modified: true });
            }
        }

        _renderList() {
            if (!this.refs.fpList) return;
            Base.renderPickerList({
                list: this.refs.fpList,
                options: this._pickerOptions,
                selected: Array.isArray(this.dataValue) ? this.dataValue : [],
                filter: this._pickerFilter,
                readOnly: this.isPickerReadOnly,
                unresolvedSuffix: __('(無法解析：可能已停用或超出對象權限)'),
                emptyMessage: this._pickerError
                    || (this._pickerFilter ? __('沒有符合的表單') : __('沒有可申請的表單')),
                onToggle: this._toggle.bind(this),
            });
            this._renderSummary();
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
