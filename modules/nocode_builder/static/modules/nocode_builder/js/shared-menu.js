/* global __ */
(function () {
    const BP = window.__BP || '';
    const apiBase = `${BP}/api/nocode-builder`;

    function tr(text) {
        return window.__ ? window.__(text) : text;
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    async function requestJson(url, options) {
        const res = await fetch(url, options || {});
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || tr('共用選單操作失敗'));
        return data.data || null;
    }

    function list(subSystemSc) {
        return requestJson(`${apiBase}/sub-systems/${encodeURIComponent(subSystemSc)}/shared-components?widget_type=menu`);
    }

    function create(subSystemSc, payload) {
        return requestJson(`${apiBase}/sub-systems/${encodeURIComponent(subSystemSc)}/shared-components`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(payload || {}),
        });
    }

    function update(subSystemSc, secureCode, payload) {
        return requestJson(`${apiBase}/sub-systems/${encodeURIComponent(subSystemSc)}/shared-components/${encodeURIComponent(secureCode)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify(payload || {}),
        });
    }

    function remove(subSystemSc, secureCode) {
        return requestJson(`${apiBase}/sub-systems/${encodeURIComponent(subSystemSc)}/shared-components/${encodeURIComponent(secureCode)}`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrfToken() },
        });
    }

    window.BkSharedComponent = { list, create, update, remove };
}());
