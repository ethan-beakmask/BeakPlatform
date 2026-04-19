/**
 * fc-canned-messages.js — 簽核片語管理 mixin
 * 由 form-center.js 拆分而來
 */
function fcCannedMessages() {
    return {
        // --- State ---
        cannedMessages: [],
        loadingCanned: false,
        showPhraseManager: false,
        cannedNewText: '',
        cannedEditId: null,
        cannedEditText: '',

        // --- Methods ---

        async loadCannedMessages() {
            try {
                const res = await fetch('/bp/api/form-center/canned-messages');
                const data = await res.json();
                if (data.success) this.cannedMessages = data.data || [];
            } catch (e) { console.error('載入簽核片語失敗:', e); }
        },

        /**
         * 追加簽核片語到指定 model（approvalComment 或 batchApprovalComment）
         */
        applyCannedMessage(text, target) {
            const prop = target || 'approvalComment';
            if (this[prop] && !this[prop].endsWith('\n') && this[prop].length > 0) {
                this[prop] += '\n';
            }
            this[prop] += text;
        },

        async addCannedMessage() {
            const text = (this.cannedNewText || '').trim();
            if (!text) return;
            try {
                const res = await fetch('/bp/api/form-center/canned-messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await res.json();
                if (data.success) {
                    this.cannedMessages.push(data.data);
                    this.cannedNewText = '';
                } else {
                    this.showToast(data.error || '新增失敗', 'error');
                }
            } catch (e) { this.showToast('新增失敗', 'error'); }
        },

        startEditCanned(msg) {
            this.cannedEditId = msg.secure_code;
            this.cannedEditText = msg.text;
        },

        cancelEditCanned() {
            this.cannedEditId = null;
            this.cannedEditText = '';
        },

        async saveEditCanned(sc) {
            const text = (this.cannedEditText || '').trim();
            if (!text) return;
            try {
                const res = await fetch(`/bp/api/form-center/canned-messages/${sc}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await res.json();
                if (data.success) {
                    const idx = this.cannedMessages.findIndex(m => m.secure_code === sc);
                    if (idx >= 0) this.cannedMessages[idx] = data.data;
                    this.cannedEditId = null;
                    this.cannedEditText = '';
                } else {
                    this.showToast(data.error || '修改失敗', 'error');
                }
            } catch (e) { this.showToast('修改失敗', 'error'); }
        },

        async deleteCannedMessage(sc) {
            if (!confirm('確定刪除此簽核片語？')) return;
            try {
                const res = await fetch(`/bp/api/form-center/canned-messages/${sc}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    this.cannedMessages = this.cannedMessages.filter(m => m.secure_code !== sc);
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) { this.showToast('刪除失敗', 'error'); }
        },
    };
}
