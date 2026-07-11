/**
 * BkI18n - 前端 i18n 機制
 *
 * 設計原則（與後端 Flask-Babel 一致）：
 * - 繁體中文原文當 key
 * - locale 為 zh-TW 時直接回傳原文，零成本
 * - 查無翻譯時 fallback 回原文，不會 broken
 *
 * 使用方式：
 *   alert(__('確定要刪除嗎？'));
 *   __('已刪除 {n} 筆', {n: 3})  // 佔位符插值
 *
 * 字典來源：
 * - 平台核心：/static/i18n/<locale>.json（base.html 於非 zh-TW 時載入）
 * - 模組擴充：BkI18n.loadModule(dict)，由模組頁面自行載入合併
 */
const BkI18n = {
    _locale: 'zh-TW',
    _dict: {},

    init: function(locale, coreDict) {
        this._locale = locale || 'zh-TW';
        this._dict = coreDict || {};
    },

    loadModule: function(moduleDict) {
        Object.assign(this._dict, moduleDict || {});
    },

    t: function(text, params) {
        var result = text;
        if (this._locale !== 'zh-TW') {
            result = this._dict[text] || text;
        }
        if (params) {
            Object.keys(params).forEach(function(key) {
                result = result.split('{' + key + '}').join(params[key]);
            });
        }
        return result;
    }
};

function __(text, params) {
    return BkI18n.t(text, params);
}
