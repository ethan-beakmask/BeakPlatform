/**
 * formio-local-cdn.js -- Form.io lazy-load 資源改指本地 vendor
 *
 * 平台 CSP 為 script-src 'self'，cdn.form.io 一律被擋；封閉網路環境更到不了。
 * datetime 元件（flatpickr）等 lazy-load 資源必須從本地 vendor 供應，
 * 否則元件靜默退化成純文字輸入（PF-207 / PF-160 實害）。
 *
 * 鏡像佈局：CDN 類別的 buildUrl() 只在官方 cdn.form.io 網址才附版本段，
 * 自訂 baseUrl 一律是 `${base}/<lib>/...`（**不帶版本目錄**，與 vendor/ace 同慣例）：
 *   static/vendor/flatpickr-formio/flatpickr.min.{js,css}
 *   static/vendor/flatpickr-formio/l10n/flatpickr-<locale>.js
 * 版本記在 vendor/flatpickr-formio/VERSION（VENDOR-01）。
 *
 * 引入位置：所有載入 formio.full.min.js 的模板，緊接其後。
 * prefix 從本檔自身 src 推導（nginx 的 /beakplatform 前綴，FRONT-10），
 * 平台頁與 portal 頁都適用，不依賴任何 window bridge。
 */
(function () {
    'use strict';
    if (typeof Formio === 'undefined') return;
    var src = (document.currentScript && document.currentScript.src) || '';
    var m = src.match(/^(.*)\/static\/js\/formio-local-cdn\.js/);
    var base = (m ? m[1] : '') + '/static/vendor';
    if (Formio.cdn && typeof Formio.cdn.setBaseUrl === 'function') {
        Formio.cdn.setBaseUrl(base);
    }
})();
