/* organizations.js - 企業管理頁面邏輯 */

const config = window.__ORG_PAGE_CONFIG || {};
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
const selectedOrgCode = config.selectedOrgCode || '';

function orgManager() {
    return {
        searchText: config.search || '',
        conglomerateFilter: config.conglomerateFilter || '',
        selectedOrgCode: selectedOrgCode,

        // 集團模式
        conglomerateMode: false,
        selectedOrgs: [],
        newConglomerateName: '',
        editingConglomerate: null,

        // 合約 Modal
        contractModal: {
            show: false,
            editing: null,
            message: '',
            error: false,
            form: {
                name: '',
                start_date: '',
                end_date: '',
                amount: '',
                description: '',
                notes: '',
                disabled: false
            }
        },

        selectOrg(secureCode) {
            if (this.conglomerateMode) {
                this.toggleOrgSelection(secureCode);
            } else {
                const url = new URL(window.location.href);
                url.searchParams.set('org', secureCode);
                window.location.href = url.toString();
            }
        },

        applyFilter() {
            const url = new URL(window.location.href);
            url.searchParams.delete('org');
            url.searchParams.delete('page');
            if (this.searchText) {
                url.searchParams.set('search', this.searchText);
            } else {
                url.searchParams.delete('search');
            }
            if (this.conglomerateFilter) {
                url.searchParams.set('conglomerate', this.conglomerateFilter);
            } else {
                url.searchParams.delete('conglomerate');
            }
            window.location.href = url.toString();
        },

        // === 集團功能 ===
        toggleConglomerateMode() {
            this.conglomerateMode = !this.conglomerateMode;
            if (!this.conglomerateMode) {
                this.selectedOrgs = [];
                this.newConglomerateName = '';
                this.editingConglomerate = null;
            }
        },

        toggleOrgSelection(secureCode) {
            const idx = this.selectedOrgs.indexOf(secureCode);
            if (idx > -1) {
                this.selectedOrgs.splice(idx, 1);
            } else {
                this.selectedOrgs.push(secureCode);
            }
        },

        async createConglomerate() {
            if (!this.newConglomerateName.trim()) {
                alert('請輸入集團名稱');
                return;
            }
            if (this.selectedOrgs.length < 2) {
                alert('請選擇至少兩家企業');
                return;
            }

            try {
                const resp = await fetch('/api/conglomerates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({
                        name: this.newConglomerateName.trim(),
                        org_secure_codes: this.selectedOrgs
                    })
                });
                const data = await resp.json();
                if (resp.ok) {
                    alert('已建立集團: ' + data.conglomerate.name);
                    location.reload();
                } else {
                    alert(data.error || '建立失敗');
                }
            } catch (e) {
                alert('建立失敗: ' + e.message);
            }
        },

        async editConglomerateById(secureCode) {
            if (!this.conglomerateMode) {
                this.conglomerateMode = true;
            }
            try {
                const resp = await fetch('/api/conglomerates/' + secureCode, {
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.editingConglomerate = data.conglomerate;
                    this.selectedOrgs = data.organizations.map(o => o.id || o.secure_code);
                } else {
                    alert(data.error || '載入失敗');
                }
            } catch (e) {
                alert('載入失敗: ' + e.message);
            }
        },

        async updateConglomerate() {
            if (!this.editingConglomerate || this.selectedOrgs.length < 2) {
                alert('請選擇至少兩家企業');
                return;
            }
            const conglomerateId = this.editingConglomerate.id || this.editingConglomerate.secure_code;
            try {
                await fetch('/api/conglomerates/' + conglomerateId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ name: this.editingConglomerate.name })
                });
                const resp = await fetch('/api/conglomerates/' + conglomerateId + '/members', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ org_secure_codes: this.selectedOrgs })
                });
                if (resp.ok) {
                    alert('已更新集團');
                    location.reload();
                } else {
                    const data = await resp.json();
                    alert(data.error || '更新失敗');
                }
            } catch (e) {
                alert('更新失敗: ' + e.message);
            }
        },

        async dissolveConglomerate() {
            if (!this.editingConglomerate) return;
            if (!confirm('確定要解散集團「' + this.editingConglomerate.name + '」嗎？')) return;

            const conglomerateId = this.editingConglomerate.id || this.editingConglomerate.secure_code;
            try {
                const resp = await fetch('/api/conglomerates/' + conglomerateId, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                if (resp.ok) {
                    alert('已解散集團');
                    location.reload();
                } else {
                    const data = await resp.json();
                    alert(data.error || '解散失敗');
                }
            } catch (e) {
                alert('解散失敗: ' + e.message);
            }
        },

        cancelEditConglomerate() {
            this.editingConglomerate = null;
            this.selectedOrgs = [];
        },

        // === 合約功能 ===
        openContractModal() {
            const today = new Date();
            const nextMonth = new Date(today);
            nextMonth.setMonth(nextMonth.getMonth() + 1);

            this.contractModal.editing = null;
            this.contractModal.message = '';
            this.contractModal.form = {
                name: '',
                start_date: this.formatDate(today),
                end_date: this.formatDate(nextMonth),
                amount: '',
                description: '',
                notes: '',
                disabled: false
            };
            this.contractModal.show = true;
        },

        async editContract(secureCode) {
            try {
                const resp = await fetch('/api/contracts/' + secureCode, {
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok && data.contract) {
                    const c = data.contract;
                    this.contractModal.editing = secureCode;
                    this.contractModal.message = '';
                    this.contractModal.form = {
                        name: c.name || '',
                        start_date: c.start_date,
                        end_date: c.end_date,
                        amount: c.amount || '',
                        description: c.description || '',
                        notes: c.notes || '',
                        disabled: c.status === 'DISABLED'
                    };
                    this.contractModal.show = true;
                } else {
                    alert(data.error || '載入失敗');
                }
            } catch (e) {
                alert('載入失敗: ' + e.message);
            }
        },

        async saveContract() {
            const form = this.contractModal.form;
            if (!form.start_date || !form.end_date) {
                this.showContractMessage('請填寫開始和結束日期', true);
                return;
            }

            const orgSecureCode = config.selectedOrgCode || '';

            try {
                let resp;
                if (this.contractModal.editing) {
                    const payload = {
                        name: form.name || null,
                        start_date: form.start_date,
                        end_date: form.end_date,
                        amount: form.amount ? parseFloat(form.amount) : null,
                        description: form.description || null,
                        notes: form.notes || null,
                        status: form.disabled ? 'DISABLED' : 'ACTIVE'
                    };
                    resp = await fetch('/api/contracts/' + this.contractModal.editing, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify(payload)
                    });
                } else {
                    const payload = {
                        org_id: orgSecureCode,
                        name: form.name || null,
                        start_date: form.start_date,
                        end_date: form.end_date,
                        amount: form.amount ? parseFloat(form.amount) : null,
                        description: form.description || null,
                        notes: form.notes || null
                    };
                    resp = await fetch('/api/contracts/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                        body: JSON.stringify(payload)
                    });
                }

                const data = await resp.json();
                if (resp.ok) {
                    location.reload();
                } else {
                    this.showContractMessage(data.error || data.message || '儲存失敗', true);
                }
            } catch (e) {
                this.showContractMessage('儲存失敗: ' + e.message, true);
            }
        },

        async deleteContract() {
            if (!this.contractModal.editing) return;
            if (!confirm('確定要刪除此合約嗎？')) return;

            try {
                const resp = await fetch('/api/contracts/' + this.contractModal.editing, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (data.success) {
                    location.reload();
                } else {
                    this.showContractMessage(data.message || '刪除失敗', true);
                }
            } catch (e) {
                this.showContractMessage('刪除失敗: ' + e.message, true);
            }
        },

        showContractMessage(msg, isError) {
            this.contractModal.message = msg;
            this.contractModal.error = isError;
            setTimeout(() => { this.contractModal.message = ''; }, 5000);
        },

        formatDate(date) {
            const y = date.getFullYear();
            const m = String(date.getMonth() + 1).padStart(2, '0');
            const d = String(date.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + d;
        }
    };
}
