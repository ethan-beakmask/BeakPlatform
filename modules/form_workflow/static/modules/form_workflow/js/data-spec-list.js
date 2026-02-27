/**
 * data-spec-list.js -- 資料表規格管理
 * Alpine.js component
 */

function dataSpecManager() {
    return {
        items: [],
        loading: true,
        totalRegistries: 0,

        // 獨立規格
        standaloneSpecs: [],
        deletingSpec: false,

        // 隱藏/選取狀態
        hiddenRegistries: [],
        selectedRegistries: [],
        allExpanded: true,
        lowerAllExpanded: false,

        // 新增 Modal
        showNewModal: false,
        availableTemplates: [],
        loadingTemplates: false,
        selectedTemplateSc: null,

        // 比對 Modal
        showCompareModal: false,
        compareResult: null,
        compareTemplateName: '',
        comparing: false,

        // 建立中
        creating: false,

        // --- computed-like getters ---
        get selectedCount() {
            return this.selectedRegistries.length;
        },

        // 手動隱藏數量
        get hiddenCount() {
            return this.hiddenRegistries.length;
        },

        // 下方清單總數（自動 + 手動）
        get lowerCount() {
            let count = 0;
            for (const item of this.items) {
                for (const reg of (item.registries || [])) {
                    if (this._isLower(reg)) count++;
                }
            }
            return count;
        },

        get visibleRegistryCount() {
            let count = 0;
            for (const item of this.items) {
                for (const reg of (item.registries || [])) {
                    if (!this._isLower(reg)) count++;
                }
            }
            return count;
        },

        // --- 隱藏/選取 helpers ---
        _isManuallyHidden(sc) {
            return this.hiddenRegistries.indexOf(sc) !== -1;
        },

        _isAutoHidden(reg) {
            return reg.published_status === 'Archived';
        },

        _isLower(reg) {
            return this._isAutoHidden(reg) || this._isManuallyHidden(reg.registry_secure_code);
        },

        isSelected(sc) {
            return this.selectedRegistries.indexOf(sc) !== -1;
        },

        hasVisibleRegistries(item) {
            const regs = item.registries || [];
            // 無 registry 的項目（有 spec 但尚未建 SQL 表）也要顯示
            if (regs.length === 0) return true;
            return regs.some(r => !this._isLower(r));
        },

        hasHiddenRegistries(item) {
            return (item.registries || []).some(r => this._isLower(r));
        },

        // --- 選取操作 ---
        toggleRegistrySelect(sc) {
            const idx = this.selectedRegistries.indexOf(sc);
            if (idx === -1) {
                this.selectedRegistries.push(sc);
            } else {
                this.selectedRegistries.splice(idx, 1);
            }
        },

        invertSelection() {
            const allUpper = [];
            for (const item of this.items) {
                for (const reg of (item.registries || [])) {
                    if (!this._isLower(reg)) {
                        allUpper.push(reg.registry_secure_code);
                    }
                }
            }
            this.selectedRegistries = allUpper.filter(
                sc => this.selectedRegistries.indexOf(sc) === -1
            );
        },

        // --- 隱藏/還原操作 ---
        hideSelected() {
            if (this.selectedRegistries.length === 0) return;
            for (const sc of this.selectedRegistries) {
                if (this.hiddenRegistries.indexOf(sc) === -1) {
                    this.hiddenRegistries.push(sc);
                }
            }
            this.selectedRegistries = [];
            this._saveHidden();
        },

        unhideRegistry(sc) {
            const idx = this.hiddenRegistries.indexOf(sc);
            if (idx !== -1) {
                this.hiddenRegistries.splice(idx, 1);
            }
            this._saveHidden();
        },

        unhideAll() {
            this.hiddenRegistries = [];
            this._saveHidden();
        },

        // --- 展開/閉合 ---
        toggleExpandAll(which) {
            if (which === 'upper') {
                this.allExpanded = !this.allExpanded;
                for (const item of this.items) {
                    item.expanded = this.allExpanded;
                }
            } else {
                this.lowerAllExpanded = !this.lowerAllExpanded;
                for (const item of this.items) {
                    item.lowerExpanded = this.lowerAllExpanded;
                }
            }
        },

        // --- localStorage ---
        _saveHidden() {
            try {
                localStorage.setItem('ds_hidden_registries', JSON.stringify(this.hiddenRegistries));
            } catch (e) { /* ignore */ }
        },

        _loadHidden() {
            try {
                const saved = localStorage.getItem('ds_hidden_registries');
                if (saved) {
                    const arr = JSON.parse(saved);
                    if (Array.isArray(arr)) {
                        this.hiddenRegistries = arr;
                    }
                }
            } catch (e) { /* ignore */ }
        },

        // --- 生命週期 ---
        async init() {
            this._loadHidden();
            await this.loadData();
        },

        async loadData() {
            this.loading = true;
            this.selectedRegistries = [];
            try {
                // 並行載入 registry overview 和獨立規格
                const [regRes, saRes] = await Promise.all([
                    fetch('/api/form-workflow/specs/registry-overview'),
                    fetch('/api/form-workflow/specs/standalone'),
                ]);
                const regData = await regRes.json();
                const saData = await saRes.json();

                if (regData.success) {
                    this.items = (regData.data || []).map(item => ({
                        ...item,
                        expanded: true,
                        lowerExpanded: false,
                    }));
                    this.totalRegistries = this.items.reduce(
                        (sum, item) => sum + (item.registries || []).length, 0
                    );
                    // 清理已不存在的 hidden entries
                    const allScs = new Set();
                    for (const item of this.items) {
                        for (const reg of (item.registries || [])) {
                            allScs.add(reg.registry_secure_code);
                        }
                    }
                    const cleaned = this.hiddenRegistries.filter(sc => allScs.has(sc));
                    if (cleaned.length !== this.hiddenRegistries.length) {
                        this.hiddenRegistries = cleaned;
                        this._saveHidden();
                    }
                } else {
                    _dsToast('error', regData.error || '載入失敗');
                }

                if (saData.success) {
                    this.standaloneSpecs = saData.data || [];
                }
            } catch (e) {
                _dsToast('error', '載入失敗: ' + e.message);
            }
            this.loading = false;
        },

        toggleExpand(item) {
            item.expanded = !item.expanded;
        },

        // --- 新增規格 ---
        async openNewSpec() {
            this.showNewModal = true;
            this.selectedTemplateSc = null;
            this.loadingTemplates = true;
            try {
                const res = await fetch('/api/form-workflow/specs/available-templates');
                const data = await res.json();
                if (data.success) {
                    this.availableTemplates = data.data || [];
                } else {
                    _dsToast('error', data.error || '載入範本失敗');
                }
            } catch (e) {
                _dsToast('error', '載入範本失敗: ' + e.message);
            }
            this.loadingTemplates = false;
        },

        selectTemplate(sc) {
            this.selectedTemplateSc = sc;
        },

        confirmNewSpec() {
            if (!this.selectedTemplateSc) {
                _dsToast('error', '請選擇表單範本');
                return;
            }
            this.showNewModal = false;
            window.location.href = '/forms/templates/' + this.selectedTemplateSc + '/spec';
        },

        // --- 跳轉編輯器 ---
        goToSpecEditor(ftSc) {
            window.location.href = '/forms/templates/' + ftSc + '/spec';
        },

        // --- 建立規格 (sync-from-formio) ---
        async createSpec(item) {
            if (this.creating) return;
            this.creating = true;
            try {
                const res = await fetch(
                    '/api/form-workflow/specs/' + item.form_template_secure_code + '/sync-from-formio',
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}',
                    }
                );
                const data = await res.json();
                if (data.success) {
                    _dsToast('success', data.message || '規格已建立');
                    await this.loadData();
                } else {
                    _dsToast('error', data.error || '建立失敗');
                }
            } catch (e) {
                _dsToast('error', '建立失敗: ' + e.message);
            }
            this.creating = false;
        },

        // --- 三向比對 ---
        async runCompare(item) {
            this.comparing = true;
            this.compareTemplateName = item.form_template_name;
            try {
                const res = await fetch(
                    '/api/form-workflow/specs/' + item.form_template_secure_code + '/compare'
                );
                const data = await res.json();
                if (data.success) {
                    this.compareResult = data.data;
                    this.showCompareModal = true;
                } else {
                    _dsToast('error', data.error || '比對失敗');
                }
            } catch (e) {
                _dsToast('error', '比對失敗: ' + e.message);
            }
            this.comparing = false;
        },

        // --- 獨立規格操作 ---
        goNewStandalone() {
            window.location.href = '/forms/data-specs/new';
        },

        goEditStandalone(specSc) {
            window.location.href = '/forms/data-specs/' + specSc + '/edit';
        },

        goSyncControl(ftSc) {
            window.location.href = '/forms/data-specs/' + ftSc + '/sync';
        },

        async deleteStandalone(specSc) {
            if (!confirm('確定要刪除此獨立規格？此操作無法復原。')) return;
            this.deletingSpec = true;
            try {
                const res = await fetch('/api/form-workflow/specs/standalone/' + specSc, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                });
                const data = await res.json();
                if (data.success) {
                    _dsToast('success', '已刪除');
                    await this.loadData();
                } else {
                    _dsToast('error', data.error || '刪除失敗');
                }
            } catch (e) {
                _dsToast('error', '刪除失敗: ' + e.message);
            }
            this.deletingSpec = false;
        },

        // --- 工具 ---
        formatDate(iso) {
            if (!iso) return '-';
            const d = new Date(iso);
            return d.toLocaleDateString('zh-TW') + ' ' +
                   d.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
        },

        getStatusClass(status) {
            if (!status) return 'none';
            const s = status.toLowerCase();
            if (s === 'published') return 'published';
            if (s === 'suspended') return 'suspended';
            if (s === 'archived') return 'archived';
            return 'none';
        },

        getStatusLabel(status) {
            if (!status) return '-';
            const map = {
                'Published': '已發行',
                'Suspended': '已停用',
                'Archived': '已封存',
            };
            return map[status] || status;
        },
    };
}

function _dsToast(type, msg) {
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;top:16px;right:16px;z-index:9999;padding:10px 18px;border-radius:4px;font-size:13px;max-width:400px;box-shadow:0 2px 8px rgba(0,0,0,0.15);';
    if (type === 'success') {
        el.style.background = '#d1fae5';
        el.style.color = '#065f46';
        el.style.border = '1px solid #6ee7b7';
    } else if (type === 'error') {
        el.style.background = '#fee2e2';
        el.style.color = '#991b1b';
        el.style.border = '1px solid #fca5a5';
    } else {
        el.style.background = '#e0e7ff';
        el.style.color = '#3730a3';
        el.style.border = '1px solid #a5b4fc';
    }
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}
