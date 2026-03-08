/**
 * sortable-table.js - Alpine.js 通用表格排序元件
 *
 * 適用於 Jinja2 後端渲染的 .data-table 表格，透過 DOM 操作實現前端排序。
 * 零依賴，僅需 Alpine.js（已全域載入）。
 *
 * 用法：
 *   <table class="data-table" x-data="sortableTable()">
 *     <thead>
 *       <tr>
 *         <th data-sort="text">名稱</th>
 *         <th data-sort="number">數量</th>
 *         <th data-sort="date">日期</th>
 *         <th>操作</th>              <!-- 無 data-sort = 不可排序 -->
 *       </tr>
 *     </thead>
 *     <tbody>
 *       {% for item in items %}
 *       <tr>
 *         <td>{{ item.name }}</td>
 *         <td>{{ item.count }}</td>
 *         <td>{{ item.date }}</td>
 *         <td><a href="...">編輯</a></td>
 *       </tr>
 *       {% endfor %}
 *     </tbody>
 *   </table>
 *
 * 排序類型：
 *   text   - 文字排序（zh-Hant locale）
 *   number - 數值排序（自動去除逗號、百分號）
 *   date   - 日期排序（支援 YYYY-MM-DD、YYYY/MM/DD 等標準格式）
 *
 * 自訂排序值：
 *   <td data-sort-value="1">啟用</td>
 *   <td data-sort-value="0">停用</td>
 */
function sortableTable() {
    return {
        _sortCol: -1,
        _sortDir: '',

        init: function() {
            var self = this;
            var table = this.$el;
            var headerRow = table.querySelector('thead tr');
            if (!headerRow) return;

            var ths = headerRow.children;
            for (var i = 0; i < ths.length; i++) {
                var th = ths[i];
                if (!th.hasAttribute('data-sort')) continue;

                th.classList.add('sortable');

                // 建立排序指示器
                var indicator = document.createElement('span');
                indicator.className = 'sort-indicator';
                indicator.textContent = ' \u2195';
                th.appendChild(indicator);

                // 綁定點擊事件
                (function(colIdx, thEl) {
                    thEl.addEventListener('click', function() {
                        self._doSort(table, colIdx, thEl);
                    });
                })(i, th);
            }
        },

        _doSort: function(table, colIdx, th) {
            // 切換排序方向
            if (this._sortCol === colIdx) {
                this._sortDir = this._sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this._sortCol = colIdx;
                this._sortDir = 'asc';
            }

            var sortType = th.getAttribute('data-sort');
            var dir = this._sortDir;

            // 更新所有指示器
            var indicators = table.querySelectorAll('thead .sort-indicator');
            for (var i = 0; i < indicators.length; i++) {
                indicators[i].textContent = ' \u2195';
            }
            th.querySelector('.sort-indicator').textContent = dir === 'asc' ? ' \u2191' : ' \u2193';

            // 更新 active 狀態
            var allThs = table.querySelectorAll('thead th');
            for (var i = 0; i < allThs.length; i++) {
                allThs[i].classList.remove('sort-active');
            }
            th.classList.add('sort-active');

            // 排序 tbody 行
            var tbody = table.querySelector('tbody');
            if (!tbody) return;

            var rows = [];
            for (var i = 0; i < tbody.rows.length; i++) {
                rows.push(tbody.rows[i]);
            }

            rows.sort(function(a, b) {
                var cellA = a.cells[colIdx];
                var cellB = b.cells[colIdx];
                if (!cellA || !cellB) return 0;

                var valA = cellA.getAttribute('data-sort-value');
                var valB = cellB.getAttribute('data-sort-value');
                if (valA === null) valA = cellA.textContent.trim();
                if (valB === null) valB = cellB.textContent.trim();

                var result = 0;
                if (sortType === 'number') {
                    var numA = parseFloat(valA.replace(/[,% ]/g, '')) || 0;
                    var numB = parseFloat(valB.replace(/[,% ]/g, '')) || 0;
                    result = numA - numB;
                } else if (sortType === 'date') {
                    var dateA = valA ? new Date(valA).getTime() : 0;
                    var dateB = valB ? new Date(valB).getTime() : 0;
                    if (isNaN(dateA)) dateA = 0;
                    if (isNaN(dateB)) dateB = 0;
                    result = dateA - dateB;
                } else {
                    result = valA.localeCompare(valB, 'zh-Hant');
                }

                return dir === 'desc' ? -result : result;
            });

            // 重排 DOM
            for (var i = 0; i < rows.length; i++) {
                tbody.appendChild(rows[i]);
            }
        }
    };
}
