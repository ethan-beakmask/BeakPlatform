function holidayCalendarsApp() {
    const cfg = window.__HOLIDAY_CAL_CONFIG || {};
    const csrfToken = () => document.querySelector('meta[name="csrf-token"]').content;
    return {
        schedules: cfg.schedules || [],
        selectedYear: cfg.year || new Date().getFullYear(),
        calendars: [],
        loading: false,
        message: '',
        messageType: '',
        showImportModal: false,
        showPublishModal: false,
        publishingCalendar: null,
        publishTargets: [],
        publishSummary: null,
        importForm: { source: 'TW_GOV', name: '', year: cfg.year || new Date().getFullYear(), file: null },

        init() {
            this.loadCalendars();
        },

        get yearOptions() {
            const y = cfg.year || new Date().getFullYear();
            return [y - 1, y, y + 1, y + 2];
        },

        sourceLabel(source) {
            return { TW_GOV: __('台灣政府行事曆'), CUSTOM: __('自訂') }[source] || source;
        },

        statusLabel(status) {
            return { PUBLISHED: __('已發佈'), DRAFT: __('底稿') }[status] || status;
        },

        formatTime(value) {
            if (!value) return '-';
            if (typeof BkTime !== 'undefined') return BkTime.format(value, 'short');
            return String(value).replace('T', ' ').slice(0, 16);
        },

        async loadCalendars() {
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/`, {
                    headers: { 'X-CSRFToken': csrfToken() }
                });
                const data = await res.json();
                if (data.success) {
                    this.calendars = data.data || [];
                } else {
                    this.showMessage(data.message || __('載入失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('載入失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
            }
        },

        async fetchTaiwan() {
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/fetch-taiwan`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({ year: this.selectedYear })
                });
                const data = await res.json();
                if (data.success) {
                    this.showMessage(__('已取得台灣行事曆底稿'), 'success');
                    await this.loadCalendars();
                } else {
                    this.showMessage(data.message || __('取得失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('取得失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
            }
        },

        openImportModal() {
            this.importForm = { source: 'TW_GOV', name: '', year: this.selectedYear, file: null };
            this.showImportModal = true;
        },

        closeImportModal() {
            this.showImportModal = false;
        },

        async importCalendar() {
            if (!this.importForm.file) {
                this.showMessage(__('請選擇檔案'), 'error');
                return;
            }
            const form = new FormData();
            form.append('file', this.importForm.file);
            form.append('source', this.importForm.source);
            form.append('name', this.importForm.name || '');
            form.append('year', this.importForm.year || '');
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/import`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken() },
                    body: form
                });
                const data = await res.json();
                if (data.success) {
                    this.closeImportModal();
                    this.showMessage(__('已上傳假日表底稿'), 'success');
                    await this.loadCalendars();
                } else {
                    this.showMessage(data.message || __('上傳失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('上傳失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
            }
        },

        openPublishModal(calendar) {
            this.publishingCalendar = calendar;
            const defaults = this.schedules.filter(s => s.is_default).map(s => s.id);
            this.publishTargets = (calendar.published_targets && calendar.published_targets.length) ? [...calendar.published_targets] : defaults;
            this.publishSummary = null;
            this.showPublishModal = true;
        },

        closePublishModal() {
            this.showPublishModal = false;
            this.publishingCalendar = null;
        },

        async publish() {
            if (!this.publishingCalendar) return;
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${this.publishingCalendar.id}/publish`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({ schedule_secure_codes: this.publishTargets })
                });
                const data = await res.json();
                if (data.success) {
                    this.publishSummary = data.data;
                    this.showMessage(__('已發佈假日表'), 'success');
                    await this.loadCalendars();
                } else {
                    this.showMessage(data.message || __('發佈失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('發佈失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
            }
        },

        async unpublish(calendar) {
            if (!confirm(__('確定要下架這份假日表嗎？'))) return;
            await this.postAction(calendar, 'unpublish', __('已下架假日表'));
        },

        async deleteCalendar(calendar) {
            if (!confirm(__('確定要刪除這份假日表嗎？'))) return;
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${calendar.id}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken() }
                });
                const data = await res.json();
                if (data.success) {
                    this.showMessage(data.message || __('已刪除'), 'success');
                    await this.loadCalendars();
                } else {
                    this.showMessage(data.message || __('刪除失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('刪除失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
            }
        },

        async postAction(calendar, action, successMessage) {
            this.loading = true;
            try {
                const res = await fetch(`${window.__BP}/api/admin/holiday-calendars/${calendar.id}/${action}`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken() }
                });
                const data = await res.json();
                if (data.success) {
                    this.showMessage(successMessage, 'success');
                    await this.loadCalendars();
                } else {
                    this.showMessage(data.message || __('操作失敗'), 'error');
                }
            } catch (e) {
                this.showMessage(__('操作失敗: {message}', {message: e.message}), 'error');
            } finally {
                this.loading = false;
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

        showMessage(msg, type) {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 5000);
        }
    };
}
