/**
 * schedules.html — Alpine.js Manager
 * Window Bridge: reads window.__SCHEDULES_CONFIG
 */
function schedulesApp() {
    const cfg = window.__SCHEDULES_CONFIG || {};

    // 產生時間選項 (00:00 ~ 23:30，每 30 分鐘)
    const times = [];
    for (let h = 0; h < 24; h++) {
        for (let m = 0; m < 60; m += 30) {
            times.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
        }
    }

    return {
        schedules: cfg.schedules || [],
        showModal: false,
        editingSchedule: null,
        saving: false,
        message: '',
        messageType: '',
        copyToOthers: false,
        timeOptions: times,
        dayNames: { mon: '一', tue: '二', wed: '三', thu: '四', fri: '五', sat: '六', sun: '日' },
        form: { schedule_code: '', name: '', timezone: 'Asia/Taipei', weekly_hours: {}, description: '', is_default: false },
        dayConfig: {
            mon: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
            tue: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
            wed: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
            thu: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
            fri: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
            sat: { isWorkday: 'false', startTime: '09:00', endTime: '18:00', breaks: [] },
            sun: { isWorkday: 'false', startTime: '09:00', endTime: '18:00', breaks: [] }
        },

        addBreak(day) {
            if (this.dayConfig[day].breaks.length < 3) {
                this.dayConfig[day].breaks.push({ start: '12:00', end: '13:00' });
            }
        },

        removeBreak(day, idx) { this.dayConfig[day].breaks.splice(idx, 1); },

        onWorkdayChange(day) { /* Alpine x-model handles it */ },

        dayConfigToWeeklyHours() {
            const result = {};
            const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
            if (this.copyToOthers) {
                const firstWorkday = days.find(d => this.dayConfig[d].isWorkday === 'true');
                if (firstWorkday) {
                    const src = this.dayConfig[firstWorkday];
                    for (const day of days) {
                        if (this.dayConfig[day].isWorkday === 'true') {
                            this.dayConfig[day].startTime = src.startTime;
                            this.dayConfig[day].endTime = src.endTime;
                            this.dayConfig[day].breaks = JSON.parse(JSON.stringify(src.breaks));
                        }
                    }
                }
            }
            for (const day of days) {
                const c = this.dayConfig[day];
                if (c.isWorkday !== 'true') { result[day] = null; }
                else {
                    const periods = this.buildPeriods(c.startTime, c.endTime, c.breaks);
                    result[day] = periods.length > 0 ? periods : null;
                }
            }
            return result;
        },

        buildPeriods(start, end, breaks) {
            if (!start || !end) return [];
            const sortedBreaks = [...breaks].filter(b => b.start && b.end).sort((a, b) => a.start.localeCompare(b.start));
            const periods = [];
            let currentStart = start;
            for (const brk of sortedBreaks) {
                if (brk.start > currentStart && brk.start < end) {
                    periods.push(`${currentStart}-${brk.start}`);
                    currentStart = brk.end;
                }
            }
            if (currentStart < end) periods.push(`${currentStart}-${end}`);
            return periods;
        },

        weeklyHoursToDayConfig(weeklyHours) {
            const days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
            const newConfig = {};
            for (const day of days) {
                const periods = weeklyHours[day];
                if (!periods || periods.length === 0) {
                    newConfig[day] = { isWorkday: 'false', startTime: '09:00', endTime: '18:00', breaks: [] };
                } else {
                    const parsed = this.parsePeriodsToDayConfig(periods);
                    newConfig[day] = { isWorkday: 'true', startTime: parsed.startTime, endTime: parsed.endTime, breaks: parsed.breaks };
                }
            }
            this.dayConfig = newConfig;
        },

        parsePeriodsToDayConfig(periods) {
            if (!periods || periods.length === 0) return { startTime: '09:00', endTime: '18:00', breaks: [] };
            let startTime = '23:59', endTime = '00:00';
            const breaks = [];
            for (let i = 0; i < periods.length; i++) {
                const [s, e] = periods[i].split('-');
                if (s < startTime) startTime = s;
                if (e > endTime) endTime = e;
                if (i > 0) {
                    const prevEnd = periods[i - 1].split('-')[1];
                    if (prevEnd < s) breaks.push({ start: prevEnd, end: s });
                }
            }
            return { startTime, endTime, breaks };
        },

        openCreateModal() {
            this.editingSchedule = null;
            this.copyToOthers = false;
            this.resetForm();
            this.resetDayConfig();
            this.showModal = true;
        },

        openEditModal(schedule) {
            this.editingSchedule = schedule;
            this.copyToOthers = false;
            this.form = {
                schedule_code: schedule.schedule_code, name: schedule.name,
                timezone: schedule.timezone,
                weekly_hours: JSON.parse(JSON.stringify(schedule.weekly_hours)),
                description: schedule.description || '', is_default: schedule.is_default
            };
            this.showModal = true;
            this.$nextTick(() => { this.weeklyHoursToDayConfig(schedule.weekly_hours); });
        },

        closeModal() { this.showModal = false; this.editingSchedule = null; },

        resetForm() {
            this.form = { schedule_code: '', name: '', timezone: 'Asia/Taipei', weekly_hours: {}, description: '', is_default: false };
        },

        resetDayConfig() {
            this.dayConfig = {
                mon: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
                tue: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
                wed: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
                thu: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
                fri: { isWorkday: 'true', startTime: '09:00', endTime: '18:00', breaks: [{ start: '12:00', end: '13:00' }] },
                sat: { isWorkday: 'false', startTime: '09:00', endTime: '18:00', breaks: [] },
                sun: { isWorkday: 'false', startTime: '09:00', endTime: '18:00', breaks: [] }
            };
        },

        async saveSchedule() {
            if (!this.form.schedule_code || !this.form.name) {
                this.showMessage('請填寫必填欄位', 'error');
                return;
            }
            this.form.weekly_hours = this.dayConfigToWeeklyHours();
            this.saving = true;
            try {
                const url = this.editingSchedule ? `${window.__BP}/api/admin/work-schedules/${this.editingSchedule.id}` : window.__BP + '/api/admin/work-schedules';
                const method = this.editingSchedule ? 'PUT' : 'POST';
                const response = await fetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content },
                    body: JSON.stringify(this.form)
                });
                const result = await response.json();
                if (result.success) { window.location.reload(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
            finally { this.saving = false; }
        },

        async setDefault(schedule) {
            try {
                const response = await fetch(`${window.__BP}/api/admin/work-schedules/${schedule.id}/default`, {
                    method: 'PUT',
                    headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
                });
                const result = await response.json();
                if (result.success) { this.showMessage(result.message, 'success'); await this.loadSchedules(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
        },

        async deleteSchedule(schedule) {
            if (!confirm(`確定要刪除班表「${schedule.name}」嗎？`)) return;
            try {
                const response = await fetch(`${window.__BP}/api/admin/work-schedules/${schedule.id}`, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
                });
                const result = await response.json();
                if (result.success) { this.showMessage(result.message, 'success'); await this.loadSchedules(); }
                else { this.showMessage(result.message, 'error'); }
            } catch (error) { this.showMessage('操作失敗: ' + error.message, 'error'); }
        },

        async loadSchedules() {
            try {
                const response = await fetch(window.__BP + '/api/admin/work-schedules');
                const result = await response.json();
                if (result.success) this.schedules = result.data;
            } catch (error) { console.error('載入班表失敗:', error); }
        },

        showMessage(msg, type) {
            this.message = msg;
            this.messageType = type;
            setTimeout(() => { this.message = ''; }, 5000);
        },

        formatDaySchedule(periods) {
            if (!periods || periods.length === 0) return '休';
            const result = [];
            const firstStart = periods[0].split('-')[0];
            const lastEnd = periods[periods.length - 1].split('-')[1];
            result.push(`<div style="font-weight:600;">${firstStart}~${lastEnd}</div>`);
            const breaks = [];
            for (let i = 0; i < periods.length - 1; i++) {
                const currEnd = periods[i].split('-')[1];
                const nextStart = periods[i + 1].split('-')[0];
                if (currEnd < nextStart) breaks.push(`${currEnd}~${nextStart}`);
            }
            if (breaks.length > 0) result.push(`<div style="font-size:10px;color:#888;">休: ${breaks.join(', ')}</div>`);
            return result.join('');
        }
    };
}
