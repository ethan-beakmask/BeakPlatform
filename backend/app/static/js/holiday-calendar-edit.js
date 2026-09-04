function holidayCalendarEditApp() {
    const cfg = window.__HOLIDAY_CAL_EDIT_CONFIG || {};
    const csrfToken = () => document.querySelector('meta[name="csrf-token"]').content;
    return {
        scheduleId: '',
        schedules: cfg.schedules || [],
        calendar: {},
        draftEntries: [],
        publishedEntries: [],
        year: cfg.year || new Date().getFullYear(),
        fixedYear: false,
        monthNames: [__('1月'), __('2月'), __('3月'), __('4月'), __('5月'), __('6月'), __('7月'), __('8月'), __('9月'), __('10月'), __('11月'), __('12月')],
        message: '',
        messageType: '',
        saving: false,
        loading: false,
        showEntryModal: false,
        editingEntry: null,
        showImportModal: false,
        showPublishModal: false,
        publishingCalendar: null,
        publishTargets: [],
        publishSummary: null,
        importForm: { source: 'TW_GOV', name: '', year: cfg.year || new Date().getFullYear(), file: null },
        form: { entry_date: '', holiday_type: 'HOLIDAY', description: '', work_periods_str: '' },

        init() {
            this.loadCalendar();
        },

        get visibleEntries() {
            return this.draftEntries.filter(e => Number(e.entry_date.slice(0, 4)) === this.year);
        },

        get entryMap() {
            const map = {};
            for (const entry of this.visibleEntries) map[entry.entry_date] = entry;
            return map;
        },

        async loadCalendar() {
            const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${cfg.calendarId}`, {
                headers: { 'X-CSRFToken': csrfToken() }
            });
            const data = await res.json();
            if (!data.success) {
                this.showMessage(data.message || __('載入失敗'), 'error');
                return;
            }
            this.calendar = data.data.calendar;
            this.draftEntries = data.data.draft_entries || [];
            this.publishedEntries = data.data.published_entries || [];
            this.fixedYear = !!this.calendar.year;
            if (this.fixedYear) this.year = this.calendar.year;
            this.publishingCalendar = this.calendar;
        },

        sourceLabel(source) {
            return { TW_GOV: __('台灣政府行事曆'), CUSTOM: __('自訂') }[source] || source;
        },

        statusLabel(status) {
            return { PUBLISHED: __('已發佈'), DRAFT: __('底稿') }[status] || status;
        },

        getTypeBadgeClass(type) {
            return { HOLIDAY: 'badge-holiday', COMP_OFF: 'badge-comp_off', WORKDAY: 'badge-workday' }[type] || 'badge-holiday';
        },

        getTypeLabel(type) {
            return { HOLIDAY: __('假日'), COMP_OFF: __('補假'), WORKDAY: __('補班') }[type] || type;
        },

        changeYear(delta) {
            if (this.fixedYear) return;
            this.year += delta;
            window.history.replaceState({}, '', `?year=${this.year}`);
        },

        getMonthCells(month) {
            const cells = [];
            const firstDay = new Date(this.year, month - 1, 1).getDay();
            const daysInMonth = new Date(this.year, month, 0).getDate();
            for (let i = 0; i < firstDay; i++) cells.push({ key: `empty-${month}-${i}`, day: null });
            for (let d = 1; d <= daysInMonth; d++) cells.push({ key: `day-${month}-${d}`, day: d, month });
            return cells;
        },

        getDayClass(cell) {
            if (!cell.day) return 'empty';
            const dateStr = `${this.year}-${String(cell.month).padStart(2, '0')}-${String(cell.day).padStart(2, '0')}`;
            const entry = this.entryMap[dateStr];
            return entry ? entry.holiday_type.toLowerCase() : '';
        },

        openEntryModal(month, day) {
            const dateStr = `${this.year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const existing = this.entryMap[dateStr];
            if (existing) {
                this.editEntry(existing);
                return;
            }
            this.editingEntry = null;
            this.form = { entry_date: dateStr, holiday_type: 'HOLIDAY', description: '', work_periods_str: '' };
            this.showEntryModal = true;
        },

        editEntry(entry) {
            this.editingEntry = entry;
            this.form = {
                entry_date: entry.entry_date,
                holiday_type: entry.holiday_type,
                description: entry.description || '',
                work_periods_str: entry.work_periods ? entry.work_periods.join(',') : ''
            };
            this.showEntryModal = true;
        },

        closeEntryModal() {
            this.showEntryModal = false;
            this.editingEntry = null;
        },

        async saveEntry() {
            const payload = {
                entry_date: this.form.entry_date,
                holiday_type: this.form.holiday_type,
                description: this.form.description,
                work_periods: this.form.holiday_type === 'WORKDAY'
                    ? this.form.work_periods_str.split(',').map(s => s.trim()).filter(s => s)
                    : null
            };
            const url = this.editingEntry
                ? `${window.__BP}/api/admin/holiday-calendars/${cfg.calendarId}/draft-entries/${this.editingEntry.id}`
                : `${window.__BP}/api/admin/holiday-calendars/${cfg.calendarId}/draft-entries`;
            this.saving = true;
            try {
                const res = await fetch(url, {
                    method: this.editingEntry ? 'PUT' : 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    this.closeEntryModal();
                    this.showMessage(data.message || __('已儲存'), 'success');
                    await this.loadCalendar();
                } else {
                    this.showMessage(data.message || __('儲存失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('儲存失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.saving = false;
            }
        },

        async deleteEntry(entry) {
            if (!confirm(__('確定要刪除 {date} 的設定嗎？', {date: entry.entry_date}))) return;
            const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${cfg.calendarId}/draft-entries/${entry.id}`, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': csrfToken() }
            });
            const data = await res.json();
            if (data.success) {
                this.showMessage(data.message || __('已刪除'), 'success');
                await this.loadCalendar();
            } else {
                this.showMessage(data.message || __('刪除失敗'), 'error');
            }
        },

        openPublishModal() {
            this.publishingCalendar = this.calendar;
            const defaults = this.schedules.filter(s => s.is_default).map(s => s.id);
            this.publishTargets = (this.calendar.published_targets && this.calendar.published_targets.length) ? [...this.calendar.published_targets] : defaults;
            this.publishSummary = null;
            this.showPublishModal = true;
        },

        closePublishModal() {
            this.showPublishModal = false;
        },

        async publish() {
            this.loading = true;
            const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${cfg.calendarId}/publish`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify({ schedule_secure_codes: this.publishTargets })
            });
            const data = await res.json();
            this.loading = false;
            if (data.success) {
                this.publishSummary = data.data;
                this.showMessage(data.message || __('已發佈'), 'success');
                await this.loadCalendar();
            } else {
                this.showMessage(data.message || __('發佈失敗'), 'error');
            }
        },

        summaryLine(target) {
            return __('{name}：新增 {inserted}／取代 {replaced}／略過手動 {manual}／略過較低優先 {lower}／缺時段略過 {noPeriods}', {
                name: target.name,
                inserted: target.inserted,
                replaced: target.replaced,
                manual: target.skipped_manual,
                lower: target.skipped_lower_priority,
                noPeriods: target.skipped_no_periods
            });
        },

        closeImportModal() {},
        importCalendar() {},

        showMessage(msg, type) {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 5000);
        }
    };
}
