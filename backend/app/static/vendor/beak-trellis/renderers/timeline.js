/**
 * Timeline 渲染器
 * 在表格欄位內繪製時間軸區段
 *
 * 支援：
 * - 自動計算時間範圍（所有可見資料的 min/max）
 * - 每個節點依 start/end 繪製水平色條
 * - 嚴重等級對應色彩
 * - hover 顯示詳細時間
 * - 時間刻度標題列
 */
'use strict';

var TimelineRenderer = (function() {

    /**
     * 建立 Timeline 欄位渲染器
     * @param {Object} options
     * @param {string} options.startField - 資料中的開始時間欄位名
     * @param {string} options.endField - 資料中的結束時間欄位名
     * @param {string} [options.colorField] - 色彩依據欄位（如 severity）
     * @param {Object} [options.colorMap] - 值到色彩的對應表
     * @param {string} [options.rangeStart] - 固定時間範圍起點（不設則自動）
     * @param {string} [options.rangeEnd] - 固定時間範圍終點（不設則自動）
     * @param {number} [options.barHeight=14] - 色條高度(px)
     * @returns {Function} renderer function
     */
    function create(options) {
        var opts = Object.assign({
            startField: 'start',
            endField: 'end',
            colorField: 'severity',
            colorMap: {
                'CRITICAL': '#c00',
                'HIGH': '#e60',
                'MEDIUM': '#e90',
                'LOW': '#999',
                'INFO': '#69c'
            },
            rangeStart: null,
            rangeEnd: null,
            barHeight: 14
        }, options || {});

        // 內部快取：整體時間範圍
        var _cachedRange = null;
        var _cacheKey = '';

        /**
         * 計算所有可見節點的時間範圍
         */
        function computeRange(grid) {
            var nodes = grid._flatNodes;
            var key = nodes.map(function(n) { return n.id; }).join(',');
            if (key === _cacheKey && _cachedRange) return _cachedRange;

            var minTime = Infinity;
            var maxTime = -Infinity;

            for (var i = 0; i < nodes.length; i++) {
                var d = nodes[i].data;
                var s = d[opts.startField];
                var e = d[opts.endField];
                if (s) {
                    var st = new Date(s).getTime();
                    if (!isNaN(st) && st < minTime) minTime = st;
                }
                if (e) {
                    var et = new Date(e).getTime();
                    if (!isNaN(et) && et > maxTime) maxTime = et;
                }
            }

            // 固定範圍覆蓋
            if (opts.rangeStart) minTime = new Date(opts.rangeStart).getTime();
            if (opts.rangeEnd) maxTime = new Date(opts.rangeEnd).getTime();

            // 防呆：範圍為零時擴展 1 小時
            if (minTime >= maxTime) {
                maxTime = minTime + 3600000;
            }

            // 前後各加 5% 邊距
            var padding = (maxTime - minTime) * 0.05;
            minTime -= padding;
            maxTime += padding;

            _cachedRange = { min: minTime, max: maxTime, span: maxTime - minTime };
            _cacheKey = key;
            return _cachedRange;
        }

        /**
         * 格式化時間為顯示用字串
         */
        function formatTime(ts) {
            var d = new Date(ts);
            var mm = String(d.getMonth() + 1).padStart(2, '0');
            var dd = String(d.getDate()).padStart(2, '0');
            var hh = String(d.getHours()).padStart(2, '0');
            var mi = String(d.getMinutes()).padStart(2, '0');
            return mm + '/' + dd + ' ' + hh + ':' + mi;
        }

        /**
         * Cell 渲染函式
         * @param {*} cellValue - 原始 cell 值（未使用，timeline 資料從 node.data 取）
         * @param {Object} node - 節點物件
         * @param {Object} col - 欄位定義
         * @param {BeakTrellis} [grid] - BeakTrellis 實例（自動由 BeakTrellis 傳入）
         * @returns {HTMLElement}
         */
        function renderer(cellValue, node, col, grid) {
            var container = document.createElement('div');
            container.className = 'bt-timeline-cell';

            // 自動記錄 grid 參照（由 BeakTrellis._createRow 第四參數傳入）
            if (grid) renderer._gridRef = grid;

            var startVal = node.data[opts.startField];
            var endVal = node.data[opts.endField];

            if (!startVal || !endVal) {
                container.innerHTML = '<span class="bt-timeline-nodata">--</span>';
                return container;
            }

            var startTs = new Date(startVal).getTime();
            var endTs = new Date(endVal).getTime();

            if (isNaN(startTs) || isNaN(endTs)) {
                container.innerHTML = '<span class="bt-timeline-nodata">--</span>';
                return container;
            }

            // 優先使用第四參數 grid，其次用快取的 _gridRef
            var gridRef = grid || renderer._gridRef;
            var range = gridRef
                ? computeRange(gridRef)
                : { min: startTs - 3600000, max: endTs + 3600000, span: (endTs - startTs) + 7200000 };

            // 計算百分比位置
            var leftPct = ((startTs - range.min) / range.span) * 100;
            var widthPct = ((endTs - startTs) / range.span) * 100;

            // 最小寬度 1%
            if (widthPct < 1) widthPct = 1;
            // 邊界限制
            if (leftPct < 0) leftPct = 0;
            if (leftPct + widthPct > 100) widthPct = 100 - leftPct;

            // 色彩
            var color = '#69c'; // 預設
            if (opts.colorField && node.data[opts.colorField] && opts.colorMap[node.data[opts.colorField]]) {
                color = opts.colorMap[node.data[opts.colorField]];
            }

            // 繪製軌道
            var track = document.createElement('div');
            track.className = 'bt-timeline-track';

            var bar = document.createElement('div');
            bar.className = 'bt-timeline-bar';
            bar.style.left = leftPct + '%';
            bar.style.width = widthPct + '%';
            bar.style.height = opts.barHeight + 'px';
            bar.style.background = color;
            bar.title = formatTime(startTs) + ' ~ ' + formatTime(endTs) +
                (node.data[opts.colorField] ? ' [' + node.data[opts.colorField] + ']' : '');

            track.appendChild(bar);
            container.appendChild(track);

            return container;
        }

        // 公開方法：讓外部傳入 grid 參照
        renderer.setGrid = function(grid) {
            renderer._gridRef = grid;
        };

        // 公開方法：重置快取
        renderer.resetCache = function() {
            _cachedRange = null;
            _cacheKey = '';
        };

        // 公開方法：產生時間刻度標頭
        renderer.createScaleHeader = function(grid) {
            var range = computeRange(grid);
            var container = document.createElement('div');
            container.className = 'bt-timeline-scale';

            // 計算合適的刻度間距
            var spanHours = range.span / 3600000;
            var tickInterval; // 毫秒
            var tickFormat;

            if (spanHours <= 2) {
                tickInterval = 15 * 60000;       // 15 分鐘
                tickFormat = 'HH:mm';
            } else if (spanHours <= 12) {
                tickInterval = 3600000;            // 1 小時
                tickFormat = 'HH:mm';
            } else if (spanHours <= 72) {
                tickInterval = 6 * 3600000;        // 6 小時
                tickFormat = 'MM/DD HH:mm';
            } else {
                tickInterval = 24 * 3600000;       // 1 天
                tickFormat = 'MM/DD';
            }

            // 從整點開始
            var firstTick = Math.ceil(range.min / tickInterval) * tickInterval;

            for (var t = firstTick; t <= range.max; t += tickInterval) {
                var pct = ((t - range.min) / range.span) * 100;
                var tick = document.createElement('span');
                tick.className = 'bt-timeline-tick';
                tick.style.left = pct + '%';
                tick.textContent = formatTime(t);
                container.appendChild(tick);
            }

            return container;
        };

        return renderer;
    }

    return { create: create };

})();
