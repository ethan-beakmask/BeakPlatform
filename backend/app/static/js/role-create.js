/* role-create.js — 新增角色表單 (Mode B) */

var __ROLE_CONFIG = window.__ROLE_CONFIG || {};

function roleCreateForm() {
    return {
        formData: {
            name: '',
            code: '',
            is_internal: false,
            role_type: 'ROLE',
            scope_type: 'GLOBAL',
            is_manager: false,
            description: '',
            sort_order: 0
        },
        generatedCode: '',
        suggestions: [],
        codeValid: false,
        codeError: '',
        isSubmitting: false,
        submitError: '',

        getCSRFToken() {
            return document.querySelector('meta[name="csrf-token"]')?.content || '';
        },

        onInternalChange() {
            if (!this.formData.is_internal) {
                this.formData.role_type = 'ROLE';
                this.formData.is_manager = false;
            }
        },

        async generateCode() {
            if (!this.formData.name.trim()) {
                this.generatedCode = '';
                this.suggestions = [];
                return;
            }

            try {
                var resp = await fetch('/api/roles/generate-code', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({ name: this.formData.name })
                });
                var data = await resp.json();

                if (resp.ok) {
                    this.generatedCode = data.code;
                    this.suggestions = data.suggestions || [];
                    if (!this.formData.code) {
                        this.codeValid = true;
                        this.codeError = '';
                    }
                }
            } catch (e) {
                console.error('Generate code error:', e);
            }
        },

        async validateCode() {
            var code = this.formData.code.trim();

            if (!code) {
                this.codeValid = false;
                this.codeError = '';
                return;
            }

            try {
                var resp = await fetch('/api/roles/validate-code', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify({ code: code })
                });
                var data = await resp.json();

                if (data.valid) {
                    this.codeValid = true;
                    this.codeError = '';
                } else {
                    this.codeValid = false;
                    this.codeError = data.error;
                }
            } catch (e) {
                console.error('Validate code error:', e);
                this.codeError = '驗證失敗';
            }
        },

        async useGeneratedCode() {
            this.formData.code = this.generatedCode;
            await this.validateCode();
        },

        async submitForm() {
            this.isSubmitting = true;
            this.submitError = '';

            var payload = {
                name: this.formData.name.trim(),
                role_type: this.formData.role_type,
                scope_type: this.formData.scope_type,
                is_manager: this.formData.is_manager,
                description: this.formData.description.trim(),
                sort_order: this.formData.sort_order
            };

            if (this.formData.code.trim()) {
                payload.code = this.formData.code.trim();
            }

            try {
                var resp = await fetch('/api/roles/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: JSON.stringify(payload)
                });
                var data = await resp.json();

                if (resp.ok) {
                    window.location.href = __ROLE_CONFIG.listUrl;
                } else {
                    this.submitError = data.error || '建立失敗';
                }
            } catch (e) {
                console.error('Submit error:', e);
                this.submitError = '網路錯誤，請稍後再試';
            } finally {
                this.isSubmitting = false;
            }
        }
    };
}
