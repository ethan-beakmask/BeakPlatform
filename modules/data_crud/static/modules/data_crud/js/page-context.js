/**
 * PageContext - 頁面共享狀態管理
 *
 * 全域單例，取代 WidgetBus 的 point-to-point binding。
 * 每個 widget 宣告 output（寫入 context key）和 input（訂閱 context key），
 * widget 之間不直接指向彼此。
 *
 * Cascading Clear: widget 收到 input 變更 → 清除自己所有 output（set null）
 * → 下游 widget 收到 null → 也清除 → 連鎖清空。depth 上限 10 防無限迴圈。
 */
const PageContext = (function() {
    const MAX_CASCADE_DEPTH = 10;

    // 共享狀態 { contextKey: value }
    const _state = {};

    // 訂閱 { contextKey: { widgetId: callback } }
    const _subscribers = {};

    // widget 登錄 { widgetId: true }
    const _registry = {};

    // widget 的 output keys { widgetId: Set<contextKey> }
    const _outputKeys = {};

    // cascade depth counter
    let _cascadeDepth = 0;

    return {
        /**
         * 登錄 widget
         */
        register(widgetId) {
            _registry[widgetId] = true;
        },

        /**
         * 取消登錄 widget，同時清除訂閱與 output keys
         */
        unregister(widgetId) {
            delete _registry[widgetId];
            delete _outputKeys[widgetId];
            for (const key of Object.keys(_subscribers)) {
                delete _subscribers[key][widgetId];
            }
        },

        /**
         * 設定 context key 值並通知訂閱者
         * @param {string} key - context key
         * @param {*} value - 值
         * @param {string} sourceWidgetId - 設定者 widget id（不通知自己）
         */
        set(key, value, sourceWidgetId) {
            _state[key] = value;

            const subs = _subscribers[key];
            if (!subs) return;

            for (const [widgetId, callback] of Object.entries(subs)) {
                if (widgetId === sourceWidgetId) continue;
                try {
                    callback(key, value);
                } catch (e) {
                    console.error('[PageContext] subscriber error:', widgetId, e);
                }
            }
        },

        /**
         * 取得 context key 值
         * @param {string} key
         * @returns {*}
         */
        get(key) {
            return _state[key] !== undefined ? _state[key] : null;
        },

        /**
         * 訂閱 context key 變更
         * @param {string} key - context key
         * @param {string} widgetId - 訂閱者 widget id
         * @param {function} callback - fn(key, value)
         */
        subscribe(key, widgetId, callback) {
            if (!_subscribers[key]) {
                _subscribers[key] = {};
            }
            _subscribers[key][widgetId] = callback;
        },

        /**
         * 取消訂閱（按 widget）
         * @param {string} widgetId
         */
        unsubscribe(widgetId) {
            for (const key of Object.keys(_subscribers)) {
                delete _subscribers[key][widgetId];
            }
        },

        /**
         * 登記 widget 的 output keys
         * @param {string} widgetId
         * @param {string[]} keys
         */
        registerOutputKeys(widgetId, keys) {
            _outputKeys[widgetId] = new Set(keys);
        },

        /**
         * 清除 widget 的所有 output（set null），觸發 cascading clear
         * @param {string} widgetId
         */
        clearWidgetOutputs(widgetId) {
            const keys = _outputKeys[widgetId];
            if (!keys || keys.size === 0) return;

            _cascadeDepth++;
            if (_cascadeDepth > MAX_CASCADE_DEPTH) {
                console.warn('[PageContext] cascade depth exceeded, stopping at', MAX_CASCADE_DEPTH);
                _cascadeDepth--;
                return;
            }

            try {
                for (const key of keys) {
                    this.set(key, null, widgetId);
                }
            } finally {
                _cascadeDepth--;
            }
        },

        /**
         * 重設所有狀態
         */
        reset() {
            for (const key of Object.keys(_state)) {
                delete _state[key];
            }
            for (const key of Object.keys(_subscribers)) {
                delete _subscribers[key];
            }
            for (const key of Object.keys(_registry)) {
                delete _registry[key];
            }
            for (const key of Object.keys(_outputKeys)) {
                delete _outputKeys[key];
            }
            _cascadeDepth = 0;
        }
    };
})();
