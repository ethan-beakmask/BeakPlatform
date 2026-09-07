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

    window.myProxyAssignmentsManager = function () {
        return {
            given: [],
            received: [],
            loading: true,
            message: '',
            messageIsError: false,

            async init() {
                await this.load();
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

            flash(text, isError) {
                this.message = text;
                this.messageIsError = !!isError;
                if (!isError) setTimeout(() => { this.message = ''; }, 3500);
            },
        };
    };
})();
