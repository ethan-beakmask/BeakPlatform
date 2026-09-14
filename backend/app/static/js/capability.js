/**
 * capability.js - UI capability mirror.
 *
 * 防線在後端 API，此處僅 UI 鏡射。
 */
window.BkCaps = (function () {
    function can(code) {
        const caps = window.__PAGE_CAPS;
        if (!caps || typeof caps !== 'object') return false;
        return caps[code] === true;
    }

    return { can };
})();
