/**
 * calendar.html — Alpine.js 行事曆（PF-229 第一期，唯讀投影）
 * Window Bridge: reads window.__CALENDAR_CONFIG
 *
 * 所有日期字串都是企業時區的 YYYY-MM-DD / YYYY-MM-DDTHH:MM（後端已換算），
 * 前端只做字串比對與鋪格子，不做瀏覧器時區運算（TZ-01）。
 * 日期加減一律走 Date.UTC，避開本地 DST。
 */
const LONG_SPAN_DAYS = 7;

function calPad(n) {
    return String(n).padStart(2, '0');
}

function calParse(str) {
    const parts = String(str).split('-').map(Number);
    return { y: parts[0], m: parts[1], d: parts[2] };
}

function calFromUTC(dt) {
    return `${dt.getUTCFullYear()}-${calPad(dt.getUTCMonth() + 1)}-${calPad(dt.getUTCDate())}`;
}

function calAddDays(str, n) {
    const p = calParse(str);
    return calFromUTC(new Date(Date.UTC(p.y, p.m - 1, p.d + n)));
}

function calStartOfMonth(str) {
    const p = calParse(str);
    return `${p.y}-${calPad(p.m)}-01`;
}

function calWeekday(str) {
    const p = calParse(str);
    return new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
}

function calendarApp() {
    const cfg = window.__CALENDAR_CONFIG || {};
    const today = cfg.today || calFromUTC(new Date());
    return {
        scope: cfg.scope || 'org',
        isOrgAdmin: !!cfg.isOrgAdmin,
        userSecureCode: cfg.userSecureCode || '',
        today: today,
        timezone: cfg.timezone || '',
        view: 'month',
        anchor: today,
        days: [],
        dayMap: {},
        events: [],
        loading: false,
        error: '',
        panel: { open: false, date: null },
        modal: { open: false, saving: false, error: '' },
        toast: { show: false, message: '', link: null, linkText: '' },
        toastTimer: null,
        form: {
            secure_code: '',
            calendar_kind: 'PERSONAL',
            event_type: 'MEETING',
            title: '',
            all_day: false,
            start: '',
            end: '',
            visibility: 'BUSY',
            note: ''
        },
        weekdayNames: [__('日'), __('一'), __('二'), __('三'), __('四'), __('五'), __('六')],

        init() {
            this.load();
        },

        range() {
            if (this.view === 'week') {
                const start = calAddDays(this.anchor, -calWeekday(this.anchor));
                return { start, end: calAddDays(start, 6) };
            }
            const first = calStartOfMonth(this.anchor);
            const start = calAddDays(first, -calWeekday(first));
            return { start, end: calAddDays(start, 41) };
        },

        async load() {
            const r = this.range();
            this.loading = true;
            this.error = '';
            try {
                const resp = await fetch(
                    `${window.__BP}/api/calendar/${this.scope}/events?start=${r.start}&end=${r.end}`,
                    { credentials: 'same-origin' }
                );
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || !data.success) {
                    this.error = (data && data.message) || __('行事曆載入失敗');
                    this.days = [];
                    this.dayMap = {};
                    this.events = [];
                    return;
                }
                this.days = data.days || [];
                const map = {};
                for (const d of this.days) map[d.date] = d;
                this.dayMap = map;
                this.events = data.events || [];
                if (data.today) this.today = data.today;
            } catch (e) {
                this.error = __('行事曆載入失敗');
            } finally {
                this.loading = false;
            }
        },

        shiftMonth(n) {
            const p = calParse(this.anchor);
            return calFromUTC(new Date(Date.UTC(p.y, p.m - 1 + n, 1)));
        },

        prev() {
            this.anchor = this.view === 'week' ? calAddDays(this.anchor, -7) : this.shiftMonth(-1);
            this.load();
        },

        next() {
            this.anchor = this.view === 'week' ? calAddDays(this.anchor, 7) : this.shiftMonth(1);
            this.load();
        },

        goToday() {
            this.anchor = this.today;
            this.load();
        },

        setView(v) {
            if (this.view === v) return;
            this.view = v;
            this.load();
        },

        rangeTitle() {
            if (this.view === 'week') {
                const r = this.range();
                return `${r.start} ~ ${r.end}`;
            }
            const p = calParse(this.anchor);
            return __('{y}年{m}月', { y: p.y, m: p.m });
        },

        makeCell(date, currentMonth) {
            const p = calParse(date);
            const events = this.eventsFor(date);
            return {
                date,
                day: p.d,
                inMonth: currentMonth === null || p.m === currentMonth,
                meta: this.dayMap[date] || null,
                events,
                chips: events.filter(ev => this.showsChipOn(ev, date)),
            };
        },

        // 長事件（超過 LONG_SPAN_DAYS 天，例：三個月的代理職位）只在起日與迄日出格子，
        // 否則每一格都被同一條 chip 佔掉；當日明細面板仍會列出它。
        spanDays(ev) {
            const a = calParse(ev.start_date), b = calParse(ev.end_date);
            return Math.round((Date.UTC(b.y, b.m - 1, b.d) - Date.UTC(a.y, a.m - 1, a.d)) / 86400000) + 1;
        },

        showsChipOn(ev, date) {
            if (this.spanDays(ev) <= LONG_SPAN_DAYS) return true;
            return ev.start_date === date || ev.end_date === date;
        },

        cells() {
            const r = this.range();
            const month = calParse(this.anchor).m;
            const out = [];
            for (let i = 0; i < 42; i++) out.push(this.makeCell(calAddDays(r.start, i), month));
            return out;
        },

        weekDays() {
            const r = this.range();
            const out = [];
            for (let i = 0; i < 7; i++) out.push(this.makeCell(calAddDays(r.start, i), null));
            return out;
        },

        eventsFor(date) {
            return this.events
                .filter(ev => ev.start_date <= date && date <= ev.end_date)
                .sort((a, b) => {
                    if (a.all_day !== b.all_day) return a.all_day ? -1 : 1;
                    return String(a.start_local || '').localeCompare(String(b.start_local || ''));
                });
        },

        dayClass(cell) {
            const classes = [];
            if (!cell.inMonth) classes.push('cal-day--outside');
            const meta = cell.meta;
            if (meta) {
                if (meta.is_today) classes.push('cal-day--today');
                if (meta.is_workday === false) classes.push('cal-day--off');
                if (meta.holiday) classes.push('cal-day--holiday-' + String(meta.holiday.type).toLowerCase());
            }
            const wd = calWeekday(cell.date);
            if (wd === 0 || wd === 6) classes.push('cal-day--weekend');
            return classes.join(' ');
        },

        holidayLabel(meta) {
            if (!meta || !meta.holiday) return '';
            const names = { HOLIDAY: __('假日'), COMP_OFF: __('補假'), WORKDAY: __('補班') };
            return names[meta.holiday.type] || meta.holiday.type;
        },

        chipClass(ev) {
            return 'cal-ev--' + ((ev.source_type === 'busy' || ev.masked) ? 'busy' : String(ev.event_type || 'other').toLowerCase());
        },

        chipLabel(ev, date) {
            let label = ev.masked
                ? (ev.owner_name ? ev.owner_name + '：' : '') + __('已排程')
                : (ev.title || '');
            if (date && this.spanDays(ev) > LONG_SPAN_DAYS) {
                if (ev.start_date === date && ev.end_date !== date) label = __('{t}（起）', { t: label });
                else if (ev.end_date === date && ev.start_date !== date) label = __('{t}（迄）', { t: label });
            }
            return label;
        },

        timeLabel(ev, date) {
            if (ev.all_day) return __('全天');
            const s = String(ev.start_local || '').slice(11, 16);
            const e = String(ev.end_local || '').slice(11, 16);
            const startsHere = ev.start_date === date;
            const endsHere = ev.end_date === date;
            if (startsHere && endsHere) return s === e ? s : `${s}–${e}`;
            if (startsHere) return `${s} →`;
            if (endsHere) return `→ ${e}`;
            return __('全天');
        },

        moreLabel(n) {
            return __('+{n} 筆', { n });
        },

        weekdayName(date) {
            if (!date) return '';
            return __('週{d}', { d: this.weekdayNames[calWeekday(date)] });
        },

        showOwner(ev) {
            return !ev.masked && ev.source_type === 'manual'
                && ev.calendar_kind === 'PERSONAL' && !!ev.owner_name;
        },

        delegationLinkFor(ev) {
            if (!this.isOrgAdmin
                || ev.source_type !== 'manual'
                || ev.calendar_kind !== 'PERSONAL'
                || ev.masked
                || (ev.event_type !== 'LEAVE' && ev.event_type !== 'TRIP')
                || !ev.owner_user_secure_code
                || ev.owner_user_secure_code === this.userSecureCode) {
                return null;
            }
            const params = new URLSearchParams({
                delegator: ev.owner_user_secure_code,
                effective_from: ev.start_date,
                effective_until: ev.end_date,
                reason: ev.title || '',
                next: window.location.pathname
            });
            return `${window.__BP}/delegations/create?${params.toString()}`;
        },

        ownerLabel(ev) {
            return ev.owner_name ? `（${ev.owner_name}）` : '';
        },

        openPanel(date) {
            this.panel = { open: true, date };
        },

        closePanel() {
            this.panel = { open: false, date: null };
        },

        panelEvents() {
            return this.panel.date ? this.eventsFor(this.panel.date) : [];
        },

        panelHoliday() {
            const meta = this.panel.date ? this.dayMap[this.panel.date] : null;
            if (!meta || !meta.holiday) return '';
            const label = this.holidayLabel(meta);
            return meta.holiday.description ? `${label}：${meta.holiday.description}` : label;
        },

        resetForm(kind, date) {
            // 從「在這天新增」進來時預設全天且起迄都是那一天；從工具列進來則全部留空
            this.form = {
                secure_code: '',
                calendar_kind: kind,
                event_type: kind === 'ORG' ? 'ORG_EVENT' : 'MEETING',
                title: '',
                all_day: !!date,
                start: date || '',
                end: date || '',
                visibility: 'BUSY',
                note: ''
            };
        },

        // 切換「全天」時把 start/end 換成該 input 型別吃得下的格式，
        // 否則 <input type="date"> 收到 YYYY-MM-DDTHH:MM 會顯示空白（值其實還在，只是看不到）
        onAllDayToggle() {
            const start = this.form.start || '';
            const end = this.form.end || '';
            if (this.form.all_day) {
                this.form.start = start.slice(0, 10);
                this.form.end = end.slice(0, 10);
            } else {
                if (start.length === 10) this.form.start = `${start}T09:00`;
                if (end.length === 10) this.form.end = `${end}T18:00`;
            }
        },

        openCreate(date) {
            const kind = this.scope === 'me' ? 'PERSONAL' : 'ORG';
            this.resetForm(kind, date || '');
            this.modal = { open: true, saving: false, error: '' };
        },

        openEdit(ev) {
            this.form = {
                secure_code: ev.source_secure_code || '',
                calendar_kind: ev.calendar_kind || 'PERSONAL',
                event_type: ev.event_type || 'MEETING',
                title: ev.title || '',
                all_day: !!ev.all_day,
                start: ev.all_day ? ev.start_date : ev.start_local,
                end: ev.all_day ? ev.end_date : ev.end_local,
                visibility: ev.visibility || 'BUSY',
                note: ev.note || ''
            };
            this.closePanel();
            this.modal = { open: true, saving: false, error: '' };
        },

        closeModal() {
            if (this.modal.saving) return;
            this.modal = { open: false, saving: false, error: '' };
        },

        csrfToken() {
            const el = document.querySelector('meta[name="csrf-token"]');
            return el ? el.content : '';
        },

        formPayload() {
            let start = this.form.start || '';
            let end = this.form.end || '';
            if (this.form.all_day) {
                start = start.slice(0, 10);
                end = end.slice(0, 10);
            } else {
                if (start.length === 10) start = `${start}T09:00`;
                if (end.length === 10) end = `${end}T18:00`;
            }
            return {
                calendar_kind: this.form.calendar_kind,
                event_type: this.form.event_type,
                title: this.form.title,
                all_day: !!this.form.all_day,
                start,
                end,
                visibility: this.form.visibility,
                note: this.form.note
            };
        },

        showHint(hint) {
            if (this.toastTimer) {
                clearTimeout(this.toastTimer);
                this.toastTimer = null;
            }
            if (!hint || !hint.needed) {
                this.toast = { show: false, message: '', link: null, linkText: '' };
                return;
            }
            const message = __('您在 {s} 至 {e} 期間有簽核職責（待簽核 {p} 件、可能派給您的流程 {t} 個）', {
                s: hint.start_date,
                e: hint.end_date,
                p: hint.pending_count || 0,
                t: hint.template_count || 0
            });
            if (hint.create_url) {
                this.toast = {
                    show: true,
                    message,
                    link: hint.create_url,
                    linkText: __('建立代理授權')
                };
            } else {
                this.toast = {
                    show: true,
                    message: message + __('，請通知管理員建立代理授權'),
                    link: null,
                    linkText: ''
                };
            }
            this.toastTimer = setTimeout(() => {
                this.toast.show = false;
                this.toastTimer = null;
            }, 15000);
        },

        async submitForm() {
            this.modal.saving = true;
            this.modal.error = '';
            const editing = !!this.form.secure_code;
            const url = editing
                ? `${window.__BP}/api/calendar/events/${this.form.secure_code}`
                : `${window.__BP}/api/calendar/events`;
            try {
                const resp = await fetch(url, {
                    method: editing ? 'PUT' : 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken()
                    },
                    body: JSON.stringify(this.formPayload())
                });
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || !data.success) {
                    this.modal.error = (data && data.message) || __('儲存失敗');
                    return;
                }
                this.modal = { open: false, saving: false, error: '' };
                this.showHint(data.delegation_hint);
                await this.load();
            } catch (e) {
                this.modal.error = __('儲存失敗');
            } finally {
                this.modal.saving = false;
            }
        },

        async deleteEvent(ev) {
            const title = ev.title || '';
            if (!confirm(__('確定要刪除「{t}」嗎？', { t: title }))) return;
            try {
                const resp = await fetch(`${window.__BP}/api/calendar/events/${ev.source_secure_code}`, {
                    method: 'DELETE',
                    credentials: 'same-origin',
                    headers: { 'X-CSRFToken': this.csrfToken() }
                });
                let data = null;
                try { data = await resp.json(); } catch (e) { data = null; }
                if (!resp.ok || !data || !data.success) {
                    alert((data && data.message) || __('刪除失敗'));
                    return;
                }
                this.closePanel();
                await this.load();
            } catch (e) {
                alert(__('刪除失敗'));
            }
        },
    };
}
