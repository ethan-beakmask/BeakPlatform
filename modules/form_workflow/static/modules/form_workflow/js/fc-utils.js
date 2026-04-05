/**
 * fc-utils.js — 通用工具函式 mixin (格式化、狀態文字、Toast)
 * 由 form-center.js 拆分而來
 */
function fcUtils() {
    return {
        // --- Methods ---

        // 將 ISO 字串當 UTC 解析（後端存 UTC，isoformat() 不帶 Z）
        _parseUTC(dateStr) {
            if (!dateStr) return null;
            // 如果沒有時區標記，當作 UTC
            if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !/\d{2}:\d{2}$/.test(dateStr.slice(-6))) {
                dateStr = dateStr + 'Z';
            }
            return new Date(dateStr);
        },

        formatDate(dateStr) {
            return BkTime.format(dateStr, 'short');
        },

        formatWaitTime(isoString) {
            if (!isoString) return '-';
            const diff = Date.now() - this._parseUTC(isoString).getTime();
            if (diff < 0) return '-';
            return this._formatMs(diff);
        },

        formatDuration(startIso, endIso) {
            if (!startIso || !endIso) return '-';
            const diff = this._parseUTC(endIso).getTime() - this._parseUTC(startIso).getTime();
            if (diff < 0) return '-';
            return this._formatMs(diff);
        },

        _formatMs(ms) {
            const totalMin = Math.floor(ms / 60000);
            const days = Math.floor(totalMin / 1440);
            const hours = Math.floor((totalMin % 1440) / 60);
            const mins = totalMin % 60;
            const parts = [];
            if (days > 0) parts.push(days + '天');
            if (hours > 0) parts.push(hours + '小時');
            parts.push(mins + '分鐘');
            return parts.join('');
        },

        sortedApprovals(list) {
            if (!list || list.length === 0) return [];
            return [...list].sort((a, b) => {
                const tA = a.acted_at ? new Date(a.acted_at).getTime() : 0;
                const tB = b.acted_at ? new Date(b.acted_at).getTime() : 0;
                return this.approvalSortAsc ? tA - tB : tB - tA;
            });
        },

        getActionText(action) {
            const map = { 'approved': '核准', 'rejected': '退回', 'PENDING': '待簽', 'FORCE_END': '強制結束' };
            return map[action] || action;
        },

        getActionBadgeClass(action) {
            if (action === 'approved') return 'fc-badge-completed';
            if (action === 'rejected' || action === 'FORCE_END') return 'fc-badge-error';
            return 'fc-badge-pending';
        },

        shortSubject(text, max = 56) {
            if (!text) return '-';
            if (text.length <= max) return text;
            return text.slice(0, max) + '[...]';
        },

        getShortSerial(serial) {
            if (!serial) return '-';
            // 舊格式 TEST-20260127-0001 / FORM-20260127-0001 -> 0127-0001
            if (serial.startsWith('TEST-') || serial.startsWith('FORM-')) {
                const parts = serial.split('-');
                if (parts.length >= 3) {
                    const date = parts[1];
                    const seq = parts[2];
                    return date.slice(4) + '-' + seq;
                }
            }
            // 新格式（企業自訂，如 DEF-2603-00001）直接顯示
            return serial;
        },

        getStatusText(status) {
            const map = {
                'INITIAL': '草稿', 'PENDING': '待處理', 'RUNNING': '進行中',
                'COMPLETED': '已完成', 'REJECTED': '已退回', 'ERROR': '錯誤',
                'TERMINATED': '已終止', 'CANCELLED': '已取消'
            };
            return map[status] || status;
        },

        getStatusClass(status) {
            const map = {
                'RUNNING': 'fc-badge-running', 'COMPLETED': 'fc-badge-completed',
                'ERROR': 'fc-badge-error', 'REJECTED': 'fc-badge-error',
                'TERMINATED': 'fc-badge-error', 'CANCELLED': 'fc-badge-error'
            };
            return map[status] || '';
        },

        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },
    };
}
