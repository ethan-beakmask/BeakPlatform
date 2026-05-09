/* od-common.js -- OpenDefense 共用 helper */

window.OD = window.OD || {};

OD.csrfToken = function () {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
};

OD.fetchJSON = async function (url, options = {}) {
    const headers = Object.assign({
        'Content-Type': 'application/json',
        'X-CSRFToken': OD.csrfToken(),
    }, options.headers || {});
    const r = await fetch(url, Object.assign({
        credentials: 'same-origin',
    }, options, { headers }));
    let body = null;
    try { body = await r.json(); } catch (e) { body = null; }
    return { ok: r.ok, status: r.status, body };
};

OD.formatTime = function (iso, style = 'short') {
    if (!iso) return '-';
    if (window.BkTime) return BkTime.format(iso, style);
    return new Date(iso).toLocaleString();
};
