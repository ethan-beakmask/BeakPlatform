/**
 * BeakPlatform Egress Mask
 *
 * 遮罩哨兵渲染 + hover 揭示。搭配後端 egress_service（規格見
 * dev-notes/EGRESS_POLICY_SPEC.md）：masked 欄位的 API 值為
 *   { "__masked": true, "resource": "...", "record_sc": "...", "field": "..." }
 * 真值不在初始 payload，hover 時才逐格呼叫 POST /api/egress/reveal。
 *
 * 用法一（JS 渲染，如 Alpine.js）：
 *   BkEgress.isMasked(value)           判斷哨兵
 *   BkEgress.render(value)             回傳遮罩 HTML 字串（含揭示屬性）
 *   之後呼叫 BkEgress.bind(container)  綁定容器內揭示事件（可重複呼叫）
 *
 * 用法二（後端模板）：
 *   <span class="bk-egress-mask" data-egress-resource=".." data-egress-record=".."
 *         data-egress-field=".."></span>
 *   頁尾呼叫 BkEgress.bind() 即可。
 *
 * 揭示後滑鼠移出即復原遮罩（值不留在 DOM），再次 hover 走 session 快取。
 */
(function () {
    'use strict';

    var CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var HOVER_DELAY_MS = 350;   // 避免滑過即揭示造成誤計量
    var MASK_TEXT = '●●●●●●';
    var _cache = {};            // "res|sc|field" -> 已揭示的值（頁面生命週期內）

    function isMasked(value) {
        return !!(value && typeof value === 'object' && value.__masked === true);
    }

    function esc(s) {
        var div = document.createElement('div');
        div.textContent = String(s);
        return div.innerHTML;
    }

    function render(value) {
        if (!isMasked(value)) {
            return value == null ? '' : esc(value);
        }
        return '<span class="bk-egress-mask" ' +
            'data-egress-resource="' + esc(value.resource) + '" ' +
            'data-egress-record="' + esc(value.record_sc) + '" ' +
            'data-egress-field="' + esc(value.field) + '" ' +
            'title="' + esc(typeof __ === 'function' ? __('滑鼠停留以揭示') : '滑鼠停留以揭示') + '"' +
            '>' + MASK_TEXT + '</span>';
    }

    function revealFetch(resource, recordSc, field) {
        var key = resource + '|' + recordSc + '|' + field;
        if (key in _cache) {
            return Promise.resolve(_cache[key]);
        }
        return fetch((window.__BP || '') + '/api/egress/reveal', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({
                resource: resource,
                record_sc: recordSc,
                field: field,
            }),
        }).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok || !data.success) {
                    throw new Error(data.message || 'reveal failed');
                }
                _cache[key] = data.value;
                return data.value;
            });
        });
    }

    function attach(el) {
        if (el.__bkEgressBound) return;
        el.__bkEgressBound = true;
        var timer = null;

        el.addEventListener('mouseenter', function () {
            timer = setTimeout(function () {
                el.classList.add('bk-egress-loading');
                revealFetch(
                    el.dataset.egressResource,
                    el.dataset.egressRecord,
                    el.dataset.egressField
                ).then(function (value) {
                    el.classList.remove('bk-egress-loading');
                    el.classList.add('bk-egress-revealed');
                    el.textContent = value == null ? '-' : String(value);
                }).catch(function () {
                    el.classList.remove('bk-egress-loading');
                    el.textContent = MASK_TEXT;
                });
            }, HOVER_DELAY_MS);
        });

        el.addEventListener('mouseleave', function () {
            if (timer) { clearTimeout(timer); timer = null; }
            // 值不留在 DOM，復原遮罩（再次 hover 走快取，不重複計量）
            el.classList.remove('bk-egress-revealed', 'bk-egress-loading');
            el.textContent = MASK_TEXT;
        });
    }

    function bind(container) {
        var root = container || document;
        var nodes = root.querySelectorAll('.bk-egress-mask');
        for (var i = 0; i < nodes.length; i++) {
            attach(nodes[i]);
        }
    }

    window.BkEgress = {
        isMasked: isMasked,
        render: render,
        bind: bind,
        reveal: revealFetch,
    };
})();
