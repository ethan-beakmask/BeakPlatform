/**
 * timezone.js - 統一時區格式化工具
 *
 * 使用 window.__TIMEZONE (由 base.html 注入) 作為顯示時區，
 * 確保所有頁面依據用戶/企業時區設定顯示時間，而非瀏覽器本地時區。
 *
 * 用法:
 *   BkTime.format('2026-03-22 13:45:30')           // '2026-03-22 13:45:30'
 *   BkTime.format('2026-03-22T13:45:30', 'date')   // '2026-03-22'
 *   BkTime.format('2026-03-22T13:45:30', 'time')   // '13:45:30'
 *   BkTime.format('2026-03-22T13:45:30', 'short')  // '2026-03-22 13:45'
 *   BkTime.tz                                       // 'Asia/Taipei'
 */
const BkTime = (function () {
    const tz = window.__TIMEZONE || 'Asia/Taipei';

    // Intl formatters (cached)
    const _cache = {};

    function _formatter(style) {
        if (_cache[style]) return _cache[style];
        let opts = { timeZone: tz };
        switch (style) {
            case 'full':
                opts = {
                    ...opts,
                    year: 'numeric', month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit', second: '2-digit',
                    hour12: false,
                };
                break;
            case 'short':
                opts = {
                    ...opts,
                    year: 'numeric', month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit',
                    hour12: false,
                };
                break;
            case 'date':
                opts = {
                    ...opts,
                    year: 'numeric', month: '2-digit', day: '2-digit',
                };
                break;
            case 'time':
                opts = {
                    ...opts,
                    hour: '2-digit', minute: '2-digit', second: '2-digit',
                    hour12: false,
                };
                break;
        }
        _cache[style] = new Intl.DateTimeFormat('sv-SE', opts);
        return _cache[style];
    }

    /**
     * 將時間字串標準化為可解析的 UTC ISO 格式。
     * DB 儲存的是 UTC (datetime.utcnow)，API 回傳不帶時區標記，
     * 這裡統一加上 'Z' 讓 JS Date 正確識別為 UTC。
     */
    function _toUTC(str) {
        str = String(str).trim();
        // 已帶時區標記 (Z, +HH:MM, -HH:MM) → 不處理
        if (/[Zz]$/.test(str) || /[+-]\d{2}:\d{2}$/.test(str)) return str;
        // 'YYYY-MM-DD HH:MM:SS' → 'YYYY-MM-DDTHH:MM:SSZ'
        if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(str)) {
            return str.replace(' ', 'T') + 'Z';
        }
        // 'YYYY-MM-DDTHH:MM:SS' → 加 Z
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(str)) {
            return str + 'Z';
        }
        return str;
    }

    /**
     * 格式化時間字串
     * @param {string|Date} input - ISO 8601 或 'YYYY-MM-DD HH:MM:SS' 格式 (視為 UTC)
     * @param {string} style - 'full'(預設), 'short', 'date', 'time'
     * @returns {string} 格式化後的時間字串 (YYYY-MM-DD HH:MM:SS)
     */
    function format(input, style) {
        if (!input) return '-';
        style = style || 'full';
        try {
            const d = (input instanceof Date) ? input : new Date(_toUTC(input));
            if (isNaN(d.getTime())) return String(input);
            return _formatter(style).format(d);
        } catch (e) {
            return String(input);
        }
    }

    /**
     * 取得指定時區下的日期部分 (YYYY-MM-DD)
     * 適用於熱力圖等需要按日期分組的場景
     * @param {Date} d - Date 物件
     * @returns {string} 'YYYY-MM-DD'
     */
    function dateOf(d) {
        return _formatter('date').format(d);
    }

    /**
     * 取得指定時區下的小時 (0-23)
     * @param {Date|string} input
     * @returns {number}
     */
    function hourOf(input) {
        if (!input) return 0;
        const d = (input instanceof Date) ? input : new Date(_toUTC(input));
        // 使用 formatToParts 取得指定時區的 hour
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: tz, hour: 'numeric', hour12: false,
        }).formatToParts(d);
        const hourPart = parts.find(p => p.type === 'hour');
        return hourPart ? parseInt(hourPart.value, 10) : 0;
    }

    return { format, dateOf, hourOf, tz };
})();
