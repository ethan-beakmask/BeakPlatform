/**
 * holidays.html — Alpine.js Manager
 * Window Bridge: reads window.__HOLIDAYS_CONFIG
 */
function holidaysApp() {
    const cfg = window.__HOLIDAYS_CONFIG || {};
    return {
        scheduleId: cfg.scheduleId || '',
        year: cfg.year || new Date().getFullYear(),
        holidays: [],
        holidayMap: {},
        showModal: false,
        editingHoliday: null,
        saving: false,
        message: '',
        messageType: '',
        monthNames: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
        weeklyHours: cfg.weeklyHours || {},
        form: {
            holiday_date: '',
            end_date: '',
            holiday_type: 'HOLIDAY',
            work_periods_str: '',
            description: '',
            cancelMode: false
        },

        init() {
            this.loadHolidays();
        },

        getTypeBadgeClass(type) {
            const classes = { 'HOLIDAY': 'badge-holiday', 'COMP_OFF': 'badge-comp_off', 'WORKDAY': 'badge-workday' };
            return classes[type] || 'badge-holiday';
        },

        getTypeLabel(type) {
            const labels = { 'HOLIDAY': '假日', 'COMP_OFF': '補假', 'WORKDAY': '補班' };
            return labels[type] || type;
        },

        async loadHolidays() {
            try {
                const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays?year=${this.year}`);
                const result = await response.json();
                if (result.success) {
                    this.holidays = result.data;
                    this.buildHolidayMap();
                }
            } catch (error) {
                console.error('載入假日失敗:', error);
            }
        },

        buildHolidayMap() {
            this.holidayMap = {};
            for (const h of this.holidays) {
                this.holidayMap[h.holiday_date] = h;
            }
        },

        changeYear(delta) {
            this.year += delta;
            window.history.replaceState({}, '', `?year=${this.year}`);
            this.loadHolidays();
        },

        getMonthCells(month) {
            const cells = [];
            const firstDay = new Date(this.year, month - 1, 1).getDay();
            const daysInMonth = new Date(this.year, month, 0).getDate();
            for (let i = 0; i < firstDay; i++) {
                cells.push({ key: `empty-${i}`, day: null });
            }
            for (let d = 1; d <= daysInMonth; d++) {
                cells.push({ key: `day-${d}`, day: d, month });
            }
            return cells;
        },

        getDayClass(cell) {
            if (!cell.day) return 'empty';
            const classes = [];
            const dateStr = `${this.year}-${String(cell.month).padStart(2, '0')}-${String(cell.day).padStart(2, '0')}`;
            const dayOfWeek = new Date(this.year, cell.month - 1, cell.day).getDay();
            if (this.holidayMap[dateStr]) {
                classes.push(this.holidayMap[dateStr].holiday_type.toLowerCase());
            } else {
                const dayName = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'][dayOfWeek];
                const periods = this.weeklyHours[dayName];
                if (!periods || periods.length === 0) {
                    classes.push('weekend');
                }
            }
            const today = new Date();
            if (this.year === today.getFullYear() && cell.month === today.getMonth() + 1 && cell.day === today.getDate()) {
                classes.push('today');
            }
            return classes.join(' ');
        },

        onDayClick(month, day) {
            const dateStr = `${this.year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            this.form = { holiday_date: dateStr, end_date: '', holiday_type: 'HOLIDAY', work_periods_str: '', description: '', cancelMode: false };
            this.editingHoliday = null;
            this.showModal = true;
        },

        openAddModal() {
            this.editingHoliday = null;
            this.form = { holiday_date: '', end_date: '', holiday_type: 'HOLIDAY', work_periods_str: '', description: '', cancelMode: false };
            this.showModal = true;
        },

        editHoliday(h) {
            this.editingHoliday = h;
            this.form = {
                holiday_date: h.holiday_date,
                holiday_type: h.holiday_type,
                work_periods_str: h.work_periods ? h.work_periods.join(',') : '',
                description: h.description || ''
            };
            this.showModal = true;
        },

        closeModal() {
            this.showModal = false;
            this.editingHoliday = null;
        },

        isScheduleRestDay(dateStr) {
            const d = new Date(dateStr);
            const dayOfWeek = d.getDay();
            const dayMap = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
            const dayKey = dayMap[dayOfWeek];
            const periods = this.weeklyHours[dayKey];
            return !periods || periods.length === 0;
        },

        getDateRange(startStr, endStr) {
            const dates = [];
            const start = new Date(startStr);
            const end = endStr ? new Date(endStr) : start;
            for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
                dates.push(d.toISOString().split('T')[0]);
            }
            return dates;
        },

        async saveHoliday() {
            if (!this.form.holiday_date) {
                this.showMessage('請選擇日期', 'error');
                return;
            }
            if (this.editingHoliday) { await this.saveSingleHoliday(); return; }
            if (this.form.cancelMode) { await this.deleteHolidayRange(); return; }

            const dates = this.getDateRange(this.form.holiday_date, this.form.end_date);
            const restDays = dates.filter(d => this.isScheduleRestDay(d));
            const workDays = dates.filter(d => !this.isScheduleRestDay(d));
            let datesToSave = dates;

            if (restDays.length > 0 && workDays.length > 0) {
                const restDayNames = restDays.map(d => {
                    const date = new Date(d);
                    const dayNames = ['日', '一', '二', '三', '四', '五', '六'];
                    return `${d} (週${dayNames[date.getDay()]})`;
                }).join('\n');
                const choice = confirm(`選取範圍包含以下班表休息日：\n${restDayNames}\n\n按「確定」：包含休息日一起設定\n按「取消」：僅設定工作日`);
                if (!choice) datesToSave = workDays;
            }

            if (datesToSave.length === 0) {
                this.showMessage('選取範圍內沒有需要設定的日期', 'error');
                return;
            }

            const holidays = datesToSave.map(date => ({
                date: date,
                type: this.form.holiday_type,
                description: this.form.description,
                work_periods: this.form.holiday_type === 'WORKDAY'
                    ? this.form.work_periods_str.split(',').map(s => s.trim()).filter(s => s)
                    : null
            }));

            if (this.form.holiday_type === 'WORKDAY') {
                const periods = this.form.work_periods_str.split(',').map(s => s.trim()).filter(s => s);
                if (periods.length === 0) {
                    this.showMessage('補班日請設定工作時段', 'error');
                    return;
                }
            }

            this.saving = true;
            try {
                const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays/batch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
                    body: JSON.stringify({ holidays, replace_year: false })
                });
                const result = await response.json();
                if (result.success) {
                    this.showMessage(`已新增 ${datesToSave.length} 天假日設定`, 'success');
                    this.closeModal();
                    await this.loadHolidays();
                } else {
                    this.showMessage(result.message, 'error');
                }
            } catch (error) {
                this.showMessage('操作失敗: ' + error.message, 'error');
            } finally {
                this.saving = false;
            }
        },

        async saveSingleHoliday() {
            const data = { holiday_date: this.form.holiday_date, holiday_type: this.form.holiday_type, description: this.form.description };
            if (this.form.holiday_type === 'WORKDAY') {
                const periods = this.form.work_periods_str.split(',').map(s => s.trim()).filter(s => s);
                if (periods.length === 0) { this.showMessage('補班日請設定工作時段', 'error'); return; }
                data.work_periods = periods;
            }
            this.saving = true;
            try {
                const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays/${this.editingHoliday.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
                    body: JSON.stringify(data)
                });
                const result = await response.json();
                if (result.success) { this.showMessage(result.message, 'success'); this.closeModal(); await this.loadHolidays(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
            finally { this.saving = false; }
        },

        async deleteHoliday(h) {
            if (!confirm(`確定要刪除 ${h.holiday_date} 的設定嗎？`)) return;
            try {
                const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays/${h.id}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
                });
                const result = await response.json();
                if (result.success) { this.showMessage(result.message, 'success'); await this.loadHolidays(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
        },

        async deleteHolidayRange() {
            const dates = this.getDateRange(this.form.holiday_date, this.form.end_date);
            const holidaysToDelete = dates.filter(d => this.holidayMap[d]).map(d => this.holidayMap[d]);
            if (holidaysToDelete.length === 0) {
                this.showMessage('選取範圍內沒有假日/補班設定，無需取消', 'error');
                return;
            }
            this.saving = true;
            let successCount = 0, failCount = 0;
            try {
                for (const h of holidaysToDelete) {
                    try {
                        const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays/${h.id}`, {
                            method: 'DELETE',
                            headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
                        });
                        const result = await response.json();
                        if (result.success) successCount++; else failCount++;
                    } catch { failCount++; }
                }
                if (failCount === 0) this.showMessage(`已取消 ${successCount} 筆設定，回復班表預設值`, 'success');
                else this.showMessage(`取消完成：成功 ${successCount} 筆，失敗 ${failCount} 筆`, 'error');
                this.closeModal();
                await this.loadHolidays();
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
            finally { this.saving = false; }
        },

        async importTWHolidays() {
            const twHolidays2026 = [
                { date: '2026-01-01', type: 'HOLIDAY', description: '中華民國開國紀念日' },
                { date: '2026-01-02', type: 'HOLIDAY', description: '彈性放假' },
                { date: '2026-02-16', type: 'HOLIDAY', description: '農曆除夕' },
                { date: '2026-02-17', type: 'HOLIDAY', description: '春節' },
                { date: '2026-02-18', type: 'HOLIDAY', description: '春節' },
                { date: '2026-02-19', type: 'HOLIDAY', description: '春節' },
                { date: '2026-02-20', type: 'HOLIDAY', description: '春節補假' },
                { date: '2026-02-28', type: 'HOLIDAY', description: '和平紀念日' },
                { date: '2026-04-04', type: 'HOLIDAY', description: '兒童節' },
                { date: '2026-04-05', type: 'HOLIDAY', description: '清明節' },
                { date: '2026-04-06', type: 'HOLIDAY', description: '彈性放假' },
                { date: '2026-05-31', type: 'HOLIDAY', description: '端午節' },
                { date: '2026-10-04', type: 'HOLIDAY', description: '中秋節' },
                { date: '2026-10-05', type: 'HOLIDAY', description: '中秋節補假' },
                { date: '2026-10-10', type: 'HOLIDAY', description: '國慶日' }
            ];
            if (this.year !== 2026) {
                this.showMessage('目前僅支援 2026 年台灣假日資料', 'error');
                return;
            }
            if (!confirm('確定要匯入 2026 年台灣國定假日嗎？已存在的日期將略過。')) return;
            try {
                const response = await fetch(`/api/admin/work-schedules/${this.scheduleId}/holidays/batch`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
                    body: JSON.stringify({ holidays: twHolidays2026, replace_year: false })
                });
                const result = await response.json();
                if (result.success) { this.showMessage(result.message, 'success'); await this.loadHolidays(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('匯入失敗: ' + error.message, 'error'); }
        },

        showMessage(msg, type) {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 5000);
        }
    };
}
