/**
 * Access Center skeleton
 */
function acCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

async function acFetch(url, options) {
    const opts = Object.assign({}, options || {});
    const method = (opts.method || 'GET').toUpperCase();
    const headers = Object.assign({}, opts.headers || {});
    const hasFormData = opts.body instanceof FormData;

    if (!hasFormData) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    if (method !== 'GET') {
        headers['X-CSRFToken'] = headers['X-CSRFToken'] || acCsrfToken();
    }

    if (opts.body && typeof opts.body === 'object' && !hasFormData && !(opts.body instanceof Blob)) {
        opts.body = JSON.stringify(opts.body);
    }

    opts.method = method;
    opts.headers = headers;

    const response = await fetch((window.__BP || '') + url, opts);
    const contentType = response.headers.get('Content-Type') || '';
    const data = contentType.indexOf('application/json') !== -1
        ? await response.json()
        : await response.text();

    if (!response.ok) {
        const message = data && typeof data === 'object'
            ? (data.error || data.message || __('請求失敗'))
            : (data || __('請求失敗'));
        throw new Error(message);
    }

    return data;
}

function acRoleOriginLabel(role) {
    return role && role.is_system_role ? __('系統') : __('自訂');
}

function acRoleOriginClass(role) {
    return role && role.is_system_role ? 'ac-role-origin-system' : 'ac-role-origin-custom';
}

function acRoleOriginSuffix(role) {
    return '[' + acRoleOriginLabel(role) + ']';
}

function accessCenter() {
    const config = window.__AC_CONFIG || {};

    return {
        isSystemAdmin: !!config.isSystemAdmin,
        activeTab: 'functions',

        init() {
            window.addEventListener('ac:select-menu', () => {
                this.activeTab = 'functions';
            });
        },

        switchTab(tab) {
            if (this.isSystemAdmin && tab === 'accounts') {
                this.activeTab = 'functions';
                return;
            }
            this.activeTab = tab;
        }
    };
}

window.acFetch = acFetch;
window.acRoleOriginLabel = acRoleOriginLabel;
window.acRoleOriginClass = acRoleOriginClass;
window.acRoleOriginSuffix = acRoleOriginSuffix;
window.accessCenter = accessCenter;
