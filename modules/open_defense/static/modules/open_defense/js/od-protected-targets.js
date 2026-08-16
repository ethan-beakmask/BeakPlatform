/* od-protected-targets.js -- OpenDefense 封鎖保護清單 */

const OD_PROTECTED_API = window.__OD_API;

function odProtectedTargets() {
    return {
        OD: window.OD,
        loading: { targets: true },
        error: { targets: '' },
        protectedTargets: [],
        builtinNetworks: [],
        configNetworks: [],
        targetModal: { open: false, mode: 'create', secure_code: '', error: '' },
        targetForm: {},
        test: { target_value: '', result: null, error: '' },

        init() {
            this.targetForm = this.emptyTargetForm();
        },

        async load() {
            await this.loadTargets();
        },

        canAdmin() {
            return typeof BkCaps !== 'undefined' && BkCaps.can('open_defense.admin');
        },

        apiMessage(r, fallback) {
            return r.body?.message || r.body?.error || fallback || r.status;
        },

        async loadTargets() {
            this.loading.targets = true;
            this.error.targets = '';
            const r = await OD.fetchJSON(`${OD_PROTECTED_API}/protected-targets`);
            if (!r.ok) {
                this.error.targets = __('載入保護清單失敗: {message}', { message: this.apiMessage(r) });
                this.loading.targets = false;
                return;
            }
            this.protectedTargets = r.body.protected_targets || [];
            this.builtinNetworks = r.body.builtin_networks || [];
            this.configNetworks = r.body.config_networks || [];
            this.loading.targets = false;
        },

        sortedTargets() {
            return [...this.protectedTargets].sort((a, b) => {
                const t = String(a.entry_type || '').localeCompare(String(b.entry_type || ''));
                const v = String(a.target_value || '').localeCompare(String(b.target_value || ''));
                return t || v || String(a.secure_code || '').localeCompare(String(b.secure_code || ''));
            });
        },

        emptyTargetForm() {
            return {
                entry_type: 'protect',
                target_value: '',
                name: '',
                note: '',
                is_active: true,
            };
        },

        normalizeTargetForm(target) {
            return {
                entry_type: target.entry_type || 'protect',
                target_value: target.target_value || '',
                name: target.name || '',
                note: target.note || '',
                is_active: target.is_active !== false,
            };
        },

        openTargetModal(target = null) {
            if (!this.canAdmin()) return;
            this.targetModal = {
                open: true,
                mode: target ? 'edit' : 'create',
                secure_code: target?.secure_code || '',
                error: '',
            };
            this.targetForm = this.normalizeTargetForm(target || this.emptyTargetForm());
        },

        closeTargetModal() {
            this.targetModal.open = false;
            this.targetModal.error = '';
        },

        buildTargetPayload() {
            const targetValue = String(this.targetForm.target_value || '').trim();
            if (!targetValue) throw new Error(__('目標必填'));
            return {
                entry_type: this.targetForm.entry_type,
                target_value: targetValue,
                name: String(this.targetForm.name || '').trim(),
                note: String(this.targetForm.note || '').trim(),
                is_active: this.targetForm.is_active === true,
            };
        },

        async saveTarget() {
            if (!this.canAdmin()) return;
            this.targetModal.error = '';
            let payload;
            try {
                payload = this.buildTargetPayload();
            } catch (err) {
                this.targetModal.error = err.message;
                return;
            }
            const url = this.targetModal.mode === 'edit'
                ? `${OD_PROTECTED_API}/protected-targets/${this.targetModal.secure_code}`
                : `${OD_PROTECTED_API}/protected-targets`;
            const r = await OD.fetchJSON(url, {
                method: this.targetModal.mode === 'edit' ? 'PUT' : 'POST',
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                this.targetModal.error = __('儲存保護清單失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.closeTargetModal();
            await this.loadTargets();
        },

        async deleteTarget(target) {
            if (!this.canAdmin()) return;
            const label = target.name || target.target_value || target.secure_code;
            if (!confirm(__('刪除保護清單項目「{name}」?', { name: label }))) return;
            const r = await OD.fetchJSON(`${OD_PROTECTED_API}/protected-targets/${target.secure_code}`, {
                method: 'DELETE',
            });
            if (!r.ok) {
                alert(__('刪除保護清單失敗: {message}', { message: this.apiMessage(r) }));
                return;
            }
            await this.loadTargets();
        },

        async runTest() {
            this.test.error = '';
            this.test.result = null;
            const targetValue = String(this.test.target_value || '').trim();
            if (!targetValue) {
                this.test.error = __('目標必填');
                return;
            }
            const r = await OD.fetchJSON(`${OD_PROTECTED_API}/protected-targets/test`, {
                method: 'POST',
                body: JSON.stringify({ target_value: targetValue }),
            });
            if (!r.ok) {
                this.test.error = __('試算失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.test.result = r.body;
        },

        entryTypeLabel(entryType) {
            if (entryType === 'exempt') return __('豁免');
            return __('保護');
        },

        entryTypeHelp(entryType) {
            if (entryType === 'exempt') {
                return __('即使命中內建保護網段，仍允許封鎖；只有當封鎖目標完全落在豁免網段內才生效。');
            }
            return __('這個位址／網段不得被寫成封鎖決策。');
        },

        sourceLabel(source) {
            if (source === 'builtin') return __('內建');
            if (source === 'config') return __('設定來源');
            if (source === 'custom') return __('自訂');
            if (source === 'platform') return __('平台保護');
            return source || '-';
        },

        testHitText() {
            const hit = this.test.result?.hit;
            if (!hit) return '';
            if (!hit.network) {
                return __('（命中 {source} 網段）', { source: this.sourceLabel(hit.source) });
            }
            return __('（命中 {network}，來源 {source}）', {
                network: hit.network,
                source: this.sourceLabel(hit.source),
            });
        },
    };
}
