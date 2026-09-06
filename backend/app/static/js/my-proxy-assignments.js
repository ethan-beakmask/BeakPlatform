/**
 * Personal proxy assignments (/personal-settings)
 */
(function () {
    const PREFIX = window.__BP || '';
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

    async function api(path, options = {}) {
        const res = await fetch(PREFIX + path, {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            ...options,
        });
        return res.json();
    }

    function safeNext(value) {
        if (typeof value !== 'string' || !value.startsWith('/')) return null;
        if (value.length > 1 && (value[1] === '/' || value[1] === '\\')) return null;
        if (/[\s\x00-\x1F\x7F]/.test(value)) return null;
        return value;
    }

    window.myProxyAssignmentsManager = function () {
        return {
            given: [],
            received: [],
            candidates: [],
            proxyableRoles: [],
            loading: true,
            message: '',
            messageIsError: false,
            modal: { open: false, saving: false, error: '' },
            form: { delegate_secure_code: '', effective_from: '', effective_until: '', reason: '' },
            next: null,

            async init() {
                await Promise.all([this.load(), this.loadCandidates(), this.loadRoles()]);
                this.applyQueryPrefill();
            },

            applyQueryPrefill() {
                const q = new URLSearchParams(window.location.search);
                if (q.get('proxy') !== 'new') return;
                this.form.effective_from = q.get('effective_from') || '';
                this.form.effective_until = q.get('effective_until') || '';
                this.form.reason = q.get('reason') || '';
                this.next = safeNext(q.get('next'));
                this.modal.open = true;
                document.getElementById('my-proxy-assignments')?.scrollIntoView({ block: 'start' });
            },

            async load() {
                this.loading = true;
                try {
                    const data = await api('/api/my-proxy-assignments');
                    if (data.success) {
                        this.given = (data.data && data.data.given) || [];
                        this.received = (data.data && data.data.received) || [];
                    } else {
                        this.flash(data.message || __('載入失敗'), true);
                    }
                } catch (e) {
                    this.flash(__('載入失敗: {message}', { message: e.message }), true);
                }
                this.loading = false;
            },

            async loadCandidates() {
                try {
                    const data = await api('/api/my-proxy-assignments/candidates');
                    if (data.success) {
                        this.candidates = data.data || [];
                    } else {
                        this.flash(data.message || __('載入失敗'), true);
                    }
                } catch (e) {
                    this.flash(__('載入失敗: {message}', { message: e.message }), true);
                }
            },

            async loadRoles() {
                try {
                    const data = await api('/api/my-proxy-assignments/my-roles');
                    if (data.success) {
                        this.proxyableRoles = data.data || [];
                    } else {
                        this.flash(data.message || __('載入失敗'), true);
                    }
                } catch (e) {
                    this.flash(__('載入失敗: {message}', { message: e.message }), true);
                }
            },

            openCreate() {
                this.form = { delegate_secure_code: '', effective_from: '', effective_until: '', reason: '' };
                this.next = null;
                this.modal = { open: true, saving: false, error: '' };
            },

            closeModal() {
                this.modal = { open: false, saving: false, error: '' };
            },

            async submitCreate() {
                this.modal.error = '';
                if (!String(this.form.reason || '').trim()) {
                    this.modal.error = __('請填寫指派事由');
                    return;
                }
                this.modal.saving = true;
                try {
                    const data = await api('/api/my-proxy-assignments', {
                        method: 'POST',
                        body: JSON.stringify({
                            delegate_secure_code: this.form.delegate_secure_code,
                            effective_from: this.form.effective_from,
                            effective_until: this.form.effective_until,
                            reason: this.form.reason,
                        }),
                    });
                    if (!data.success) {
                        this.modal.error = data.message || __('建立失敗');
                        return;
                    }
                    if (this.next) {
                        window.location.href = this.next;
                        return;
                    }
                    this.closeModal();
                    const result = data.data || {};
                    let message = __('已建立 {n} 筆代理指派', { n: result.created || 0 });
                    if ((result.skipped || 0) > 0) {
                        message += __('，{m} 筆已有重疊效期而略過', { m: result.skipped });
                    }
                    this.flash(message);
                    await this.load();
                } catch (e) {
                    this.modal.error = __('建立失敗: {message}', { message: e.message });
                } finally {
                    this.modal.saving = false;
                }
            },

            async revoke(row, side) {
                const text = side === 'received'
                    ? __('確定放棄這筆代理指派？放棄後不能恢復。')
                    : __('確定撤銷這筆代理指派？撤銷後不能恢復。');
                if (!window.confirm(text)) return;
                try {
                    const data = await api('/api/my-proxy-assignments/' + row.assignment_secure_code + '/revoke', {
                        method: 'POST',
                        body: '{}',
                    });
                    if (!data.success) {
                        this.flash(data.message || __('撤銷失敗'), true);
                        return;
                    }
                    this.flash(side === 'received' ? __('已放棄代理指派') : __('已撤銷代理指派'));
                    await this.load();
                } catch (e) {
                    this.flash(__('撤銷失敗: {message}', { message: e.message }), true);
                }
            },

            roleLabel(row) {
                const roleName = row.role_name || '-';
                return row.unit_name ? roleName + '@' + row.unit_name : roleName;
            },

            rangeLabel(row) {
                return (row.valid_from || '-') + ' ~ ' + (row.valid_until || '-');
            },

            statusLabel(status) {
                return {
                    PENDING: __('待生效'),
                    ACTIVE: __('生效中'),
                    EXPIRED: __('已過期'),
                }[status] || status;
            },

            statusClass(status) {
                return {
                    PENDING: 'mpa-status-pending',
                    ACTIVE: 'text-success',
                    EXPIRED: 'text-muted',
                }[status] || '';
            },

            candidateLabel(candidate) {
                if (!candidate.employee_id) return candidate.display_name;
                return candidate.display_name + '（' + candidate.employee_id + '）';
            },

            flash(text, isError) {
                this.message = text;
                this.messageIsError = !!isError;
                if (!isError) setTimeout(() => { this.message = ''; }, 3500);
            },
        };
    };
})();
