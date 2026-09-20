/**
 * Shared helpers for Form.io form template picker components.
 */
'use strict';

(function () {
    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        var div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    function createOptionsLoader(buildUrl) {
        var optionsCache = {};
        var loadingCache = {};
        return function fetchOptions(cacheKey) {
            var key = cacheKey || '';
            if (optionsCache[key]) return Promise.resolve(optionsCache[key]);
            if (loadingCache[key]) return loadingCache[key];

            loadingCache[key] = fetch(buildUrl(key))
                .then(function (r) { return r.json(); })
                .then(function (json) {
                    if (json && json.success) {
                        optionsCache[key] = json.data || [];
                        return optionsCache[key];
                    }
                    throw new Error((json && (json.message || json.error)) || __('載入失敗'));
                })
                .finally(function () { delete loadingCache[key]; });

            return loadingCache[key];
        };
    }

    function findOption(options, sc) {
        var opts = options || [];
        for (var i = 0; i < opts.length; i++) {
            if (opts[i].secure_code === sc) return opts[i];
        }
        return null;
    }

    function optionLabel(opt) {
        if (!opt) return '';
        return (opt.name || '') + (opt.code ? ' (' + opt.code + ')' : '');
    }

    function renderReadOnlyList(list, selected, options, unresolvedSuffix) {
        if (!selected.length) {
            list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                + escapeHtml(__('(未選擇)')) + '</div>';
            return;
        }
        selected.forEach(function (sc) {
            var opt = findOption(options, sc);
            var row = document.createElement('div');
            row.style.cssText = 'padding:6px 10px;border-bottom:1px solid #f3f4f6;line-height:1.4;';
            if (opt) {
                row.innerHTML = '<span style="color:#111827;">' + escapeHtml(opt.name) + '</span>'
                    + (opt.code ? '<span style="color:#9ca3af;margin-left:6px;font-size:12px;">'
                        + escapeHtml(opt.code) + '</span>' : '');
            } else {
                row.innerHTML = '<span style="color:#111827;">' + escapeHtml(sc) + '</span>'
                    + '<span style="color:#b45309;margin-left:6px;font-size:12px;">'
                    + escapeHtml(unresolvedSuffix) + '</span>';
            }
            list.appendChild(row);
        });
    }

    function renderPickerList(config) {
        var list = config.list;
        list.innerHTML = '';

        if (config.options === null) {
            list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                + escapeHtml(__('載入中...')) + '</div>';
            return;
        }

        var selected = Array.isArray(config.selected) ? config.selected : [];
        if (config.readOnly) {
            renderReadOnlyList(
                list, selected, config.options || [],
                config.unresolvedSuffix || __('(無法解析：可能已停用)'));
            return;
        }

        var filter = (config.filter || '').toLowerCase();
        var items = (config.options || []).filter(function (o) {
            if (!filter) return true;
            return (o.name || '').toLowerCase().indexOf(filter) >= 0
                || (o.code || '').toLowerCase().indexOf(filter) >= 0;
        });

        if (!items.length) {
            list.innerHTML = '<div style="padding:12px;color:#9ca3af;">'
                + escapeHtml(config.emptyMessage) + '</div>';
            return;
        }

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
                config.onToggle(opt.secure_code, cb.checked);
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
    }

    function selectedLabels(values, options, unresolvedSuffix) {
        var scs = Array.isArray(values) ? values : [];
        if (!scs.length) return __('(未選擇)');
        return scs.map(function (sc) {
            var opt = findOption(options || [], sc);
            return opt ? optionLabel(opt) : sc + (unresolvedSuffix ? ' ' + unresolvedSuffix : '');
        }).join('、');
    }

    window.BkFormPickerBase = {
        createOptionsLoader: createOptionsLoader,
        escapeHtml: escapeHtml,
        findOption: findOption,
        optionLabel: optionLabel,
        renderPickerList: renderPickerList,
        selectedLabels: selectedLabels,
    };
})();
