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

        // 合約列表（排序/篩選）
        contracts: config.contracts || [],
        contractSort: { field: 'start_date', dir: 'desc' },
        contractStatusFilter: 'all',
        copiedLoginUrl: '',

        // 合約 Modal
        contractModal: {
            show: false,
            editing: null,
            originalStatus: null,
            message: '',
            error: false,
            availableModules: config.availableModules || [],
            form: {
                name: '',
                start_date: '',
                end_date: '',
                amount: '',
                description: '',
                notes: '',
                modules: []
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

        async copyLoginUrl(kind, url) {
            const ok = await Utils.copyToClipboard(url);
            if (!ok) {
                alert(__('複製失敗，請手動選取'));
                return;
            }
            this.copiedLoginUrl = kind;
            setTimeout(() => {
                if (this.copiedLoginUrl === kind) {
                    this.copiedLoginUrl = '';
                }
            }, 1600);
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
                alert(__('請輸入集團名稱'));
                return;
            }
            if (this.selectedOrgs.length < 2) {
                alert(__('請選擇至少兩家企業'));
                return;
            }

            try {
                const resp = await fetch(window.__BP + '/api/conglomerates', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({
                        name: this.newConglomerateName.trim(),
                        org_secure_codes: this.selectedOrgs
                    })
                });
                const data = await resp.json();
                if (resp.ok) {
                    alert(__('已建立集團: ') + data.conglomerate.name);
                    location.reload();
                } else {
                    alert(data.error || __('建立失敗'));
                }
            } catch (e) {
                alert(__('建立失敗: ') + e.message);
            }
        },

        async editConglomerateById(secureCode) {
            if (!this.conglomerateMode) {
                this.conglomerateMode = true;
            }
            try {
                const resp = await fetch(window.__BP + '/api/conglomerates/' + secureCode, {
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.editingConglomerate = data.conglomerate;
                    this.selectedOrgs = data.organizations.map(o => o.secure_code);
                } else {
                    alert(data.error || __('載入失敗'));
                }
            } catch (e) {
                alert(__('載入失敗: ') + e.message);
            }
        },

        async updateConglomerate() {
            if (!this.editingConglomerate || this.selectedOrgs.length < 2) {
                alert(__('請選擇至少兩家企業'));
                return;
            }
            const conglomerateId = this.editingConglomerate.secure_code;
            try {
                await fetch(window.__BP + '/api/conglomerates/' + conglomerateId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ name: this.editingConglomerate.name })
                });
                const resp = await fetch(window.__BP + '/api/conglomerates/' + conglomerateId + '/members', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ org_secure_codes: this.selectedOrgs })
                });
                if (resp.ok) {
                    alert(__('已更新集團'));
                    location.reload();
                } else {
                    const data = await resp.json();
                    alert(data.error || __('更新失敗'));
                }
            } catch (e) {
                alert(__('更新失敗: ') + e.message);
            }
        },

        async dissolveConglomerate() {
            if (!this.editingConglomerate) return;
            if (!confirm(__('確定要解散集團「') + this.editingConglomerate.name + __('」嗎？'))) return;

            const conglomerateId = this.editingConglomerate.secure_code;
            try {
                const resp = await fetch(window.__BP + '/api/conglomerates/' + conglomerateId, {
                    method: 'DELETE',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                if (resp.ok) {
                    alert(__('已解散集團'));
                    location.reload();
                } else {
                    const data = await resp.json();
                    alert(data.error || __('解散失敗'));
                }
            } catch (e) {
                alert(__('解散失敗: ') + e.message);
            }
        },

        async provisionSharedDb() {
            if (!this.editingConglomerate) return;
            if (!confirm(__('確定要為集團「') + this.editingConglomerate.name + __('」建立共享資料庫嗎？'))) return;

            const sc = this.editingConglomerate.secure_code;
            try {
                const resp = await fetch(window.__BP + '/api/conglomerates/' + sc + '/provision-db', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok) {
                    this.editingConglomerate.has_shared_db = true;
                    this.editingConglomerate.shared_db_name = data.db_name;
                    alert(__('共享資料庫建立成功: ') + data.db_name);
                } else {
                    alert(data.error || __('建立失敗'));
                }
            } catch (e) {
                alert(__('建立失敗: ') + e.message);
            }
        },

        cancelEditConglomerate() {
            this.editingConglomerate = null;
            this.selectedOrgs = [];
        },

        // === 合約列表排序/篩選 ===
        sortContracts(field) {
            if (this.contractSort.field === field) {
                this.contractSort.dir = this.contractSort.dir === 'asc' ? 'desc' : 'asc';
            } else {
                this.contractSort.field = field;
                this.contractSort.dir = (field === 'amount') ? 'desc' : 'asc';
            }
        },

        contractSortIcon(field) {
            if (this.contractSort.field !== field) return '\u2195';
            return this.contractSort.dir === 'asc' ? '\u25B2' : '\u25BC';
        },

        filteredContracts() {
            let list = this.contracts;

            // 狀態篩選
            if (this.contractStatusFilter === 'active') {
                list = list.filter(c => c.status === 'ACTIVE' && c.is_active);
            } else if (this.contractStatusFilter === 'inactive') {
                list = list.filter(c => c.status === 'DISABLED' || c.is_expired || !c.is_active);
            }

            // 排序
            const field = this.contractSort.field;
            const dir = this.contractSort.dir === 'asc' ? 1 : -1;
            list = [...list].sort((a, b) => {
                let va = a[field];
                let vb = b[field];
                if (va == null) va = '';
                if (vb == null) vb = '';
                if (field === 'amount') {
                    return (Number(va) - Number(vb)) * dir;
                }
                if (va < vb) return -1 * dir;
                if (va > vb) return 1 * dir;
                return 0;
            });

            return list;
        },

        // === 合約 Modal ===
        openContractModal() {
            const today = new Date();
            const nextMonth = new Date(today);
            nextMonth.setMonth(nextMonth.getMonth() + 1);

            this.contractModal.editing = null;
            this.contractModal.originalStatus = null;
            this.contractModal.message = '';
            this.contractModal.form = {
                name: '',
                start_date: this.formatDate(today),
                end_date: this.formatDate(nextMonth),
                amount: '',
                description: '',
                notes: '',
                modules: []
            };
            this.contractModal.show = true;
        },

        async editContract(secureCode) {
            try {
                const resp = await fetch(window.__BP + '/api/contracts/' + secureCode, {
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok && data.contract) {
                    const c = data.contract;
                    this.contractModal.editing = secureCode;
                    this.contractModal.originalStatus = c.status;
                    this.contractModal.message = '';
                    this.contractModal.form = {
                        name: c.name || '',
                        start_date: c.start_date,
                        end_date: c.end_date,
                        amount: c.amount || '',
                        description: c.description || '',
                        notes: c.notes || '',
                        modules: c.modules_config || []
                    };
                    this.contractModal.show = true;
                } else {
                    alert(data.error || __('載入失敗'));
                }
            } catch (e) {
                alert(__('載入失敗: ') + e.message);
            }
        },

        async saveContract() {
            const form = this.contractModal.form;
            if (!form.start_date || !form.end_date) {
                this.showContractMessage(__('請填寫開始和結束日期'), true);
                return;
            }

            const orgSecureCode = config.selectedOrgCode || '';

            try {
                const payload = {
                    org_id: orgSecureCode,
                    name: form.name || null,
                    start_date: form.start_date,
                    end_date: form.end_date,
                    amount: form.amount ? parseFloat(form.amount) : null,
                    description: form.description || null,
                    notes: form.notes || null,
                    modules_config: form.modules
                };
                const resp = await fetch(window.__BP + '/api/contracts/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify(payload)
                });

                const data = await resp.json();
                if (resp.ok) {
                    location.reload();
                } else {
                    this.showContractMessage(data.error || data.message || __('儲存失敗'), true);
                }
            } catch (e) {
                this.showContractMessage(__('儲存失敗: ') + e.message, true);
            }
        },

        async disableContract() {
            if (!this.contractModal.editing) return;
            if (!confirm(__('確定要停用此合約嗎？停用後不可再啟用，如需恢復服務請建立新合約。'))) return;

            try {
                const resp = await fetch(window.__BP + '/api/contracts/' + this.contractModal.editing + '/disable', {
                    method: 'PATCH',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await resp.json();
                if (resp.ok) {
                    location.reload();
                } else {
                    this.showContractMessage(data.error || __('停用失敗'), true);
                }
            } catch (e) {
                this.showContractMessage(__('停用失敗: ') + e.message, true);
            }
        },

        showContractMessage(msg, isError) {
            this.contractModal.message = msg;
            this.contractModal.error = isError;
            setTimeout(() => { this.contractModal.message = ''; }, 5000);
        },

        toggleModule(code) {
            const idx = this.contractModal.form.modules.indexOf(code);
            if (idx > -1) {
                this.contractModal.form.modules.splice(idx, 1);
            } else {
                this.contractModal.form.modules.push(code);
            }
        },

        formatDate(date) {
            const y = date.getFullYear();
            const m = String(date.getMonth() + 1).padStart(2, '0');
            const d = String(date.getDate()).padStart(2, '0');
            return y + '-' + m + '-' + d;
        }
    };
}
