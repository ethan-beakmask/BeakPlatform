/**
 * Personal API Keys (/personal-settings)
 */
(function () {
    const PREFIX = window.__BP || '';
    const config = window.__PAGE_CONFIG || {};
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

    function shellSingle(value) {
        return "'" + String(value || '').replace(/'/g, "'\"'\"'") + "'";
    }

    window.myApiKeysManager = function () {
        return {
            keys: [],
            loading: true,
            message: '',
            messageIsError: false,
            showModal: false,
            modalMode: 'example',
            modalKey: null,
            secret: '',
            selectedFormCode: '',
            subject: __('外部系統觸發'),
            exampleFields: {},
            secretCopied: false,
            curlCopied: false,
            baseUrl: config.apiTriggerBaseUrl || '',

            async init() {
                await this.load();
            },

            async load() {
                this.loading = true;
                try {
                    const data = await api('/api/my-api-keys');
                    if (data.success) {
                        this.keys = data.data || [];
                    } else {
                        this.flash(data.error || __('載入失敗'), true);
                    }
                } catch (e) {
                    this.flash(__('載入失敗: {message}', {message: e.message}), true);
                }
                this.loading = false;
            },

            flash(text, isError) {
                this.message = text;
                this.messageIsError = !!isError;
                if (!isError) setTimeout(() => { this.message = ''; }, 3500);
            },

            fmtTime(iso) {
                if (!iso) return '-';
                return (typeof BkTime !== 'undefined' && BkTime.format)
                    ? BkTime.format(iso, 'short')
                    : iso;
            },

            isExpired(iso) {
                if (!iso) return false;
                const normalized = /[Zz]$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + 'Z';
                return new Date(normalized).getTime() < Date.now();
            },

            statusLabel(status) {
                return {
                    active: __('啟用中'),
                    suspended: __('已暫停'),
                    revoked: __('已撤銷'),
                }[status] || status;
            },

            expiryLabel(iso) {
                if (!iso) return __('永久有效');
                if (this.isExpired(iso)) return __('已過期') + ' ' + this.fmtTime(iso);
                return __('有效期限: ') + this.fmtTime(iso);
            },

            claimLabel(key) {
                const claim = key.claim || {state: 'none'};
                if (claim.state === 'pending') return __('尚未領取');
                if (claim.state === 'claimed') {
                    return __('已於 {time} 領取', {time: this.fmtTime(claim.claimed_at)});
                }
                if (claim.state === 'expired') return __('領取期限已過');
                return __('未建立領取憑證');
            },

            modalForms() {
                return (this.modalKey && this.modalKey.triggerable_forms) || [];
            },

            selectedForm() {
                const forms = this.modalForms();
                return forms.find(f => f.form_code === this.selectedFormCode) || forms[0] || null;
            },

            selectedFieldKeys() {
                const form = this.selectedForm();
                return form && form.field_keys ? form.field_keys : [];
            },

            resetExampleFields() {
                const next = {};
                this.selectedFieldKeys().forEach(key => {
                    next[key] = this.exampleFields[key] || '';
                });
                this.exampleFields = next;
            },

            openModal(key, mode, secret) {
                this.modalKey = key;
                this.modalMode = mode;
                this.secret = secret || '';
                this.subject = __('外部系統觸發');
                const forms = this.modalForms();
                this.selectedFormCode = forms.length ? forms[0].form_code : '';
                this.exampleFields = {};
                this.secretCopied = false;
                this.curlCopied = false;
                this.resetExampleFields();
                this.showModal = true;
            },

            closeModal() {
                this.showModal = false;
                this.secret = '';
                this.modalKey = null;
                this.exampleFields = {};
                this.secretCopied = false;
                this.curlCopied = false;
            },

            modalWarning() {
                if (this.secret) {
                    return __('這串金鑰只會顯示這一次。關閉後將無法再次查看，遺失時只能重新產生。');
                }
                return __('金鑰已領取過，範例中以環境變數佔位。請自行代入當初保存的金鑰。');
            },

            async claim(key) {
                try {
                    const data = await api('/api/my-api-keys/' + key.secure_code + '/claim', {
                        method: 'POST',
                        body: '{}',
                    });
                    if (!data.success) {
                        this.flash(data.error || __('領取失敗'), true);
                        return;
                    }
                    this.openModal(key, 'claim', data.data.secret);
                    await this.load();
                } catch (e) {
                    this.flash(__('領取失敗: {message}', {message: e.message}), true);
                }
            },

            openExample(key) {
                this.openModal(key, 'example', '');
            },

            async regenerate(key) {
                const ok = confirm(__('重新產生後，舊的金鑰立即失效，所有正在使用它的系統都會連不上。確定要繼續嗎？'));
                if (!ok) return;
                try {
                    const data = await api('/api/my-api-keys/' + key.secure_code + '/regenerate', {
                        method: 'POST',
                        body: '{}',
                    });
                    if (!data.success) {
                        this.flash(data.error || __('重新產生失敗'), true);
                        return;
                    }
                    this.openModal(key, 'regenerate', data.data.secret);
                    await this.load();
                } catch (e) {
                    this.flash(__('重新產生失敗: {message}', {message: e.message}), true);
                }
            },

            exampleBody() {
                const form = this.selectedForm();
                const formData = {};
                this.selectedFieldKeys().forEach(key => {
                    const value = this.exampleFields[key];
                    if (value !== undefined && value !== '') formData[key] = value;
                });
                return {
                    form_code: form ? form.form_code : '',
                    subject: this.subject || __('外部系統觸發'),
                    form_data: formData,
                };
            },

            curlCommand() {
                const body = JSON.stringify(this.exampleBody());
                const base = this.baseUrl || __('（尚未設定系統對外網址，請聯絡管理員）');
                const keyId = this.modalKey ? this.modalKey.key_id : '';
                // 領到真金鑰時用單引號包字面值；沒有金鑰時給的是環境變數佔位，
                // 單引號在 shell 內不展開變數，必須用雙引號，否則使用者設好
                // BP_API_KEY_SECRET 貼上範例仍會拿字面字串去解 base64 而恆得 401。
                const secretLine = this.secret
                    ? 'SECRET=' + shellSingle(this.secret)
                    : 'SECRET="$BP_API_KEY_SECRET"';
                return [
                    'BASE=' + shellSingle(base),
                    'KEY_ID=' + shellSingle(keyId),
                    secretLine,
                    'BODY=' + shellSingle(body),
                    'TS=$(date +%s)',
                    'KEY_HEX=$(printf \'%s\' "$SECRET" | tr \'_-\' \'/+\' | base64 -d | xxd -p | tr -d \'\\n\')',
                    'SIG=$(printf \'%s\\n%s\' "$TS" "$BODY" | openssl dgst -sha256 -mac HMAC -macopt hexkey:"$KEY_HEX" -hex | awk \'{print $NF}\')',
                    'curl -s -X POST "$BASE/api/trigger/form" \\',
                    '  -H \'Content-Type: application/json\' \\',
                    '  -H "X-BP-Key-Id: $KEY_ID" \\',
                    '  -H "X-BP-Timestamp: $TS" \\',
                    '  -H "X-BP-Signature: sha256=$SIG" \\',
                    '  -d "$BODY"',
                ].join('\n');
            },

            async copySecret() {
                this.secretCopied = await Utils.copyToClipboard(this.secret || '$BP_API_KEY_SECRET');
                setTimeout(() => { this.secretCopied = false; }, 1800);
            },

            async copyCurl() {
                this.curlCopied = await Utils.copyToClipboard(this.curlCommand());
                setTimeout(() => { this.curlCopied = false; }, 1800);
            },
        };
    };
})();
