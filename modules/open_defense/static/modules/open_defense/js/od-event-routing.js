/* od-event-routing.js -- OpenDefense 事件路由設定 */

const OD_EVENT_API = window.__OD_API;
const FW_TEMPLATE_API = window.__FW_TEMPLATE_API;

function odEventRouting() {
    return {
        OD: window.OD,
        activeTab: 'rules',
        loading: { rules: true, profiles: true, templates: true },
        error: { rules: '', profiles: '', templates: '' },
        rules: [],
        profiles: [],
        templates: [],
        eventClasses: ['detection_finding', 'network_activity', 'web_activity', 'process_activity'],
        matchOps: ['eq', 'ne', 'in', 'not_in', 'gt', 'gte', 'lt', 'lte', 'contains', 'startswith', 'endswith', 'exists'],
        severityLevels: [0, 1, 2, 3, 4, 5],
        axisFields: [
            { key: 'severity_id', label: __('嚴重度') },
            { key: 'actor_ip', label: __('攻擊者 IP') },
            { key: 'target_host', label: __('目標主機') },
            { key: 'source_system', label: __('來源系統') },
            { key: 'finding_rule_id', label: __('規則 ID') },
            { key: 'occurred_at', label: __('發生時間') },
        ],
        ruleModal: { open: false, mode: 'create', secure_code: '', error: '' },
        ruleForm: {},
        profileModal: { open: false, mode: 'create', secure_code: '', error: '' },
        profileForm: {},
        ruleTest: { input: '', payload_kind: 'native', matched: null, evaluated: [], error: '' },
        profileTest: { secure_code: '', input: '', result: null, error: '' },

        /* modal 內容用 x-show 渲染，關閉狀態下 DOM 仍存在並持續求值，
         * 所以兩份表單狀態一開始就要有完整結構。留成 {} 會讓
         * x-model="profileForm.field_map[field.key]" 在頁面載入當下就噴
         * "Cannot read properties of undefined"。 */
        init() {
            this.ruleForm = this.emptyRuleForm();
            this.profileForm = this.emptyProfileForm();
        },

        async load() {
            await Promise.all([this.loadTemplates(), this.loadRules(), this.loadProfiles()]);
        },

        /* fail-closed：capability.js 由 layouts/base.html 全域載入，
         * 取不到就代表頁面壞了，不可反過來放行（後端仍有 @permission_required 把關）。*/
        canAdmin() {
            return typeof BkCaps !== 'undefined' && BkCaps.can('open_defense.admin');
        },

        apiMessage(r, fallback) {
            return r.body?.message || r.body?.error || fallback || r.status;
        },

        async loadRules() {
            this.loading.rules = true;
            this.error.rules = '';
            const r = await OD.fetchJSON(`${OD_EVENT_API}/routing-rules`);
            if (!r.ok) {
                this.error.rules = __('載入路由規則失敗: {message}', { message: this.apiMessage(r) });
                this.loading.rules = false;
                return;
            }
            this.rules = r.body.routing_rules || [];
            this.loading.rules = false;
        },

        async loadProfiles() {
            this.loading.profiles = true;
            this.error.profiles = '';
            const r = await OD.fetchJSON(`${OD_EVENT_API}/payload-profiles`);
            if (!r.ok) {
                this.error.profiles = __('載入來源格式失敗: {message}', { message: this.apiMessage(r) });
                this.loading.profiles = false;
                return;
            }
            this.profiles = r.body.payload_profiles || [];
            if (!this.profileTest.secure_code && this.profiles.length) {
                this.profileTest.secure_code = this.profiles[0].secure_code;
            }
            this.loading.profiles = false;
        },

        async loadTemplates() {
            this.loading.templates = true;
            this.error.templates = '';
            const r = await OD.fetchJSON(FW_TEMPLATE_API);
            if (!r.ok) {
                this.error.templates = __('載入表單模板失敗: {message}', { message: this.apiMessage(r) });
                this.loading.templates = false;
                return;
            }
            this.templates = r.body.data?.templates || [];
            this.loading.templates = false;
        },

        sortedRules() {
            return [...this.rules].sort((a, b) => {
                const p = Number(b.priority || 0) - Number(a.priority || 0);
                return p || String(a.name || '').localeCompare(String(b.name || ''));
            });
        },

        templateName(secureCode) {
            const tpl = this.templates.find((item) => item.secure_code === secureCode);
            if (!tpl) return secureCode || '-';
            return this.templateOptionLabel(tpl);
        },

        templateOptionLabel(tpl) {
            return tpl.code ? `${tpl.name} (${tpl.code})` : tpl.name;
        },

        emptyRuleForm() {
            return {
                name: '',
                priority: 0,
                payload_kind: '',
                event_class: '',
                form_template_secure_code: '',
                match_rules: [],
                is_active: true,
                note: '',
            };
        },

        openRuleModal(rule = null) {
            if (!this.canAdmin()) return;
            this.ruleModal = {
                open: true,
                mode: rule ? 'edit' : 'create',
                secure_code: rule?.secure_code || '',
                error: '',
            };
            this.ruleForm = this.normalizeRuleForm(rule || this.emptyRuleForm());
        },

        closeRuleModal() {
            this.ruleModal.open = false;
            this.ruleModal.error = '';
        },

        normalizeRuleForm(rule) {
            const form = {
                name: rule.name || '',
                priority: Number(rule.priority || 0),
                payload_kind: rule.payload_kind || '',
                event_class: rule.event_class || '',
                form_template_secure_code: rule.form_template_secure_code || '',
                is_active: rule.is_active !== false,
                note: rule.note || '',
                match_rules: (rule.match_rules || []).map((cond) => {
                    const copy = {
                        field: cond.field || '',
                        op: cond.op || 'eq',
                        value: cond.value,
                    };
                    if ((copy.op === 'in' || copy.op === 'not_in') && Array.isArray(copy.value)) {
                        copy.value = copy.value.join(', ');
                    }
                    if (copy.op === 'exists') copy.value = copy.value === true;
                    if (copy.value === undefined || copy.value === null) copy.value = copy.op === 'exists' ? true : '';
                    return copy;
                }),
            };
            return form;
        },

        addMatchRule() {
            this.ruleForm.match_rules.push({ field: '', op: 'eq', value: '' });
        },

        removeMatchRule(index) {
            this.ruleForm.match_rules.splice(index, 1);
        },

        normalizeConditionValue(cond) {
            if (cond.op === 'exists') cond.value = true;
            else if (Array.isArray(cond.value)) cond.value = cond.value.join(', ');
            else if (cond.value === true || cond.value === false) cond.value = '';
        },

        parseConditionValue(cond) {
            if (cond.op === 'exists') return cond.value === true || cond.value === 'true';
            if (cond.op === 'in' || cond.op === 'not_in') {
                return String(cond.value || '')
                    .split(',')
                    .map((item) => item.trim())
                    .filter((item) => item !== '');
            }
            if (['gt', 'gte', 'lt', 'lte'].includes(cond.op)) {
                const n = Number(cond.value);
                return Number.isFinite(n) ? n : cond.value;
            }
            return cond.value;
        },

        buildRulePayload() {
            const matchRules = [];
            for (const cond of this.ruleForm.match_rules) {
                const field = String(cond.field || '').trim();
                if (!field) throw new Error(__('條件 field 必填'));
                if (!this.matchOps.includes(cond.op)) throw new Error(__('條件 op 不支援'));
                const value = this.parseConditionValue(cond);
                if ((cond.op === 'in' || cond.op === 'not_in') && value.length === 0) {
                    throw new Error(__('in/not_in 至少要有一個值'));
                }
                if (cond.op !== 'exists' && (value === '' || value === null || value === undefined)) {
                    throw new Error(__('條件 value 必填'));
                }
                matchRules.push({ field, op: cond.op, value });
            }
            if (!String(this.ruleForm.form_template_secure_code || '').trim()) {
                throw new Error(__('目標表單必填'));
            }
            return {
                name: String(this.ruleForm.name || '').trim(),
                priority: Number(this.ruleForm.priority || 0),
                payload_kind: this.ruleForm.payload_kind || '',
                event_class: this.ruleForm.event_class || '',
                form_template_secure_code: this.ruleForm.form_template_secure_code,
                match_rules: matchRules,
                is_active: this.ruleForm.is_active === true,
                note: String(this.ruleForm.note || '').trim(),
            };
        },

        async saveRule() {
            if (!this.canAdmin()) return;
            this.ruleModal.error = '';
            let payload;
            try {
                payload = this.buildRulePayload();
            } catch (err) {
                this.ruleModal.error = err.message;
                return;
            }
            const url = this.ruleModal.mode === 'edit'
                ? `${OD_EVENT_API}/routing-rules/${this.ruleModal.secure_code}`
                : `${OD_EVENT_API}/routing-rules`;
            const r = await OD.fetchJSON(url, {
                method: this.ruleModal.mode === 'edit' ? 'PUT' : 'POST',
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                this.ruleModal.error = __('儲存路由規則失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.closeRuleModal();
            await this.loadRules();
        },

        async deleteRule(rule) {
            if (!this.canAdmin()) return;
            if (!confirm(__('刪除路由規則「{name}」?', { name: rule.name || rule.secure_code }))) return;
            const r = await OD.fetchJSON(`${OD_EVENT_API}/routing-rules/${rule.secure_code}`, { method: 'DELETE' });
            if (!r.ok) {
                alert(__('刪除路由規則失敗: {message}', { message: this.apiMessage(r) }));
                return;
            }
            await this.loadRules();
        },

        async runRuleTest() {
            this.ruleTest.error = '';
            this.ruleTest.matched = null;
            this.ruleTest.evaluated = [];
            let parsed;
            try {
                parsed = JSON.parse(this.ruleTest.input || '{}');
            } catch (err) {
                this.ruleTest.error = __('事件 JSON 格式錯誤');
                return;
            }
            let body;
            if (this.ruleTest.payload_kind === 'native') {
                body = { payload_kind: 'native', payload: parsed };
            } else {
                body = Object.assign({}, parsed, { payload_kind: 'ocsf' });
            }
            const r = await OD.fetchJSON(`${OD_EVENT_API}/routing-rules/test`, {
                method: 'POST',
                body: JSON.stringify(body),
            });
            if (!r.ok) {
                this.ruleTest.error = __('試算失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.ruleTest.matched = r.body.matched || null;
            this.ruleTest.evaluated = r.body.evaluated || [];
        },

        formatCondition(cond) {
            if (!cond) return '-';
            return `${cond.field} ${cond.op} ${this.displayValue(cond.value)}`;
        },

        emptyProfileForm() {
            return {
                code: '',
                name: '',
                source_system: '',
                correlation_id_path: '',
                field_map: this.emptyFieldMap(),
                severity_rows: [],
                detail_path: '',
                detail_item_key: '',
                detail_columns: [],
                subject_detail_key: '',
                kv_expansions: [],
                is_active: true,
                note: '',
            };
        },

        emptyFieldMap() {
            const map = {};
            this.axisFields.forEach((field) => { map[field.key] = ''; });
            return map;
        },

        normalizeProfileForm(profile) {
            const fieldMap = this.emptyFieldMap();
            for (const field of this.axisFields) {
                fieldMap[field.key] = profile.field_map?.[field.key] || '';
            }
            const severityRows = Object.entries(profile.severity_map || {}).map(([source, platform]) => ({
                source,
                platform: Number(platform),
            }));
            return {
                code: profile.code || '',
                name: profile.name || '',
                source_system: profile.source_system || '',
                correlation_id_path: profile.correlation_id_path || '',
                field_map: fieldMap,
                severity_rows: severityRows,
                detail_path: profile.detail_path || '',
                detail_item_key: profile.detail_item_key || '',
                detail_columns: (profile.detail_columns || []).map((col) => ({
                    key: col.key || '',
                    label: col.label || '',
                })),
                subject_detail_key: profile.subject_detail_key || '',
                kv_expansions: (profile.kv_expansions || []).map((kv) => ({
                    path: kv.path || '',
                    key_field: kv.key_field || '',
                    value_field: kv.value_field || '',
                    prefix: kv.prefix || '',
                })),
                is_active: profile.is_active !== false,
                note: profile.note || '',
            };
        },

        openProfileModal(profile = null) {
            if (!this.canAdmin()) return;
            this.profileModal = {
                open: true,
                mode: profile ? 'edit' : 'create',
                secure_code: profile?.secure_code || '',
                error: '',
            };
            this.profileForm = profile ? this.normalizeProfileForm(profile) : this.emptyProfileForm();
        },

        closeProfileModal() {
            this.profileModal.open = false;
            this.profileModal.error = '';
        },

        addSeverityMapRow() {
            this.profileForm.severity_rows.push({ source: '', platform: 3 });
        },

        removeSeverityMapRow(index) {
            this.profileForm.severity_rows.splice(index, 1);
        },

        addDetailColumn() {
            this.profileForm.detail_columns.push({ key: '', label: '' });
        },

        removeDetailColumn(index) {
            this.profileForm.detail_columns.splice(index, 1);
        },

        moveDetailColumn(index, delta) {
            const next = index + delta;
            if (next < 0 || next >= this.profileForm.detail_columns.length) return;
            const rows = this.profileForm.detail_columns;
            const item = rows.splice(index, 1)[0];
            rows.splice(next, 0, item);
        },

        addKvExpansion() {
            this.profileForm.kv_expansions.push({ path: '', key_field: '', value_field: '', prefix: '' });
        },

        removeKvExpansion(index) {
            this.profileForm.kv_expansions.splice(index, 1);
        },

        buildProfilePayload() {
            for (const field of ['code', 'name', 'source_system', 'correlation_id_path']) {
                if (!String(this.profileForm[field] || '').trim()) {
                    throw new Error(__('{field} 必填', { field }));
                }
            }
            const fieldMap = this.emptyFieldMap();
            for (const field of this.axisFields) {
                fieldMap[field.key] = String(this.profileForm.field_map[field.key] || '').trim();
            }
            const severityMap = {};
            for (const row of this.profileForm.severity_rows) {
                const source = String(row.source || '').trim();
                if (!source) throw new Error(__('severity_map 來源值必填'));
                const platform = Number(row.platform);
                if (!this.severityLevels.includes(platform)) throw new Error(__('平台嚴重度必須為 0 到 5'));
                severityMap[source] = platform;
            }
            const detailColumns = this.profileForm.detail_columns.map((col) => ({
                key: String(col.key || '').trim(),
                label: String(col.label || '').trim(),
            })).filter((col) => col.key);
            const kvExpansions = this.profileForm.kv_expansions.map((kv) => ({
                path: String(kv.path || '').trim(),
                key_field: String(kv.key_field || '').trim(),
                value_field: String(kv.value_field || '').trim(),
                prefix: String(kv.prefix || '').trim(),
            })).filter((kv) => kv.path || kv.key_field || kv.value_field || kv.prefix);
            for (const kv of kvExpansions) {
                if (!kv.path || !kv.key_field || !kv.value_field) {
                    throw new Error(__('kv_expansions 的 path/key_field/value_field 必填'));
                }
            }
            return {
                code: String(this.profileForm.code || '').trim(),
                name: String(this.profileForm.name || '').trim(),
                source_system: String(this.profileForm.source_system || '').trim(),
                correlation_id_path: String(this.profileForm.correlation_id_path || '').trim(),
                field_map: fieldMap,
                severity_map: severityMap,
                detail_path: String(this.profileForm.detail_path || '').trim(),
                detail_item_key: String(this.profileForm.detail_item_key || '').trim(),
                detail_columns: detailColumns,
                subject_detail_key: String(this.profileForm.subject_detail_key || '').trim(),
                kv_expansions: kvExpansions,
                is_active: this.profileForm.is_active === true,
                note: String(this.profileForm.note || '').trim(),
            };
        },

        async saveProfile() {
            if (!this.canAdmin()) return;
            this.profileModal.error = '';
            let payload;
            try {
                payload = this.buildProfilePayload();
            } catch (err) {
                this.profileModal.error = err.message;
                return;
            }
            const url = this.profileModal.mode === 'edit'
                ? `${OD_EVENT_API}/payload-profiles/${this.profileModal.secure_code}`
                : `${OD_EVENT_API}/payload-profiles`;
            const r = await OD.fetchJSON(url, {
                method: this.profileModal.mode === 'edit' ? 'PUT' : 'POST',
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                this.profileModal.error = __('儲存來源格式失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.closeProfileModal();
            await this.loadProfiles();
        },

        async deleteProfile(profile) {
            if (!this.canAdmin()) return;
            if (!confirm(__('刪除來源格式「{code}」?', { code: profile.code }))) return;
            const r = await OD.fetchJSON(`${OD_EVENT_API}/payload-profiles/${profile.secure_code}`, { method: 'DELETE' });
            if (!r.ok) {
                alert(__('刪除來源格式失敗: {message}', { message: this.apiMessage(r) }));
                return;
            }
            if (r.body.warning) alert(r.body.warning);
            await this.loadProfiles();
        },

        selectProfileTest(profile) {
            this.profileTest.secure_code = profile.secure_code;
            this.activeTab = 'profiles';
        },

        async runProfileTest() {
            this.profileTest.error = '';
            this.profileTest.result = null;
            if (!this.profileTest.secure_code) {
                this.profileTest.error = __('請選擇設定檔');
                return;
            }
            let parsed;
            try {
                parsed = JSON.parse(this.profileTest.input || '{}');
            } catch (err) {
                this.profileTest.error = __('事件 JSON 格式錯誤');
                return;
            }
            const r = await OD.fetchJSON(`${OD_EVENT_API}/payload-profiles/${this.profileTest.secure_code}/test`, {
                method: 'POST',
                body: JSON.stringify({ payload: parsed }),
            });
            if (!r.ok) {
                this.profileTest.error = __('試算失敗: {message}', { message: this.apiMessage(r) });
                return;
            }
            this.profileTest.result = r.body;
        },

        displayValue(value) {
            if (value === null || value === undefined || value === '') return '-';
            if (typeof value === 'object') return JSON.stringify(value);
            return String(value);
        },

        formatJSON(value) {
            if (value === null || value === undefined) return '';
            return JSON.stringify(value, null, 2);
        },
    };
}
