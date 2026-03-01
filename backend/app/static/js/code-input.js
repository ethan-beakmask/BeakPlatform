/**
 * code-input.js -- Code 欄位自動建議通用 mixin
 *
 * 用法: 在 Alpine.js 元件中展開 mixin:
 *   function myForm() {
 *       return {
 *           ...codeInputMixin('department'),
 *           // ... 其他屬性
 *       };
 *   }
 *
 * 提供:
 *   _ci_generatedCode   -- 自動產生的建議代碼
 *   _ci_suggestions     -- 建議列表
 *   _ci_codeValid       -- 驗證通過
 *   _ci_codeError       -- 驗證錯誤訊息
 *   _ci_loading         -- 正在呼叫 API
 *   ciGenerateCode(name) -- 根據名稱產生建議
 *   ciValidateCode(code) -- 驗證代碼格式與唯一性
 *   ciUseSuggestion(code) -- 採用建議值
 *   ciGetFinalCode(userInput) -- 取得最終代碼（空白時用建議值）
 */

function codeInputMixin(entityType) {
    var _debounceTimer = null;

    return {
        _ci_entityType: entityType,
        _ci_generatedCode: '',
        _ci_suggestions: [],
        _ci_codeValid: false,
        _ci_codeError: '',
        _ci_loading: false,

        _ci_getCSRFToken() {
            var meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.content : '';
        },

        async ciGenerateCode(name) {
            if (!name || !name.trim()) {
                this._ci_generatedCode = '';
                this._ci_suggestions = [];
                return;
            }

            this._ci_loading = true;
            try {
                var resp = await fetch('/api/code/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this._ci_getCSRFToken()
                    },
                    body: JSON.stringify({
                        entity_type: this._ci_entityType,
                        name: name.trim()
                    })
                });
                var data = await resp.json();
                if (resp.ok) {
                    this._ci_generatedCode = data.code || '';
                    this._ci_suggestions = data.suggestions || [];
                }
            } catch (e) {
                console.error('Code generate error:', e);
            } finally {
                this._ci_loading = false;
            }
        },

        ciGenerateCodeDebounced(name) {
            clearTimeout(_debounceTimer);
            _debounceTimer = setTimeout(function() {
                this.ciGenerateCode(name);
            }.bind(this), 500);
        },

        async ciValidateCode(code) {
            if (!code || !code.trim()) {
                this._ci_codeValid = false;
                this._ci_codeError = '';
                return;
            }

            this._ci_loading = true;
            try {
                var resp = await fetch('/api/code/validate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this._ci_getCSRFToken()
                    },
                    body: JSON.stringify({
                        entity_type: this._ci_entityType,
                        code: code.trim()
                    })
                });
                var data = await resp.json();
                if (data.valid) {
                    this._ci_codeValid = true;
                    this._ci_codeError = '';
                } else {
                    this._ci_codeValid = false;
                    this._ci_codeError = data.error || '驗證失敗';
                }
            } catch (e) {
                console.error('Code validate error:', e);
                this._ci_codeError = '驗證失敗';
            } finally {
                this._ci_loading = false;
            }
        },

        ciUseSuggestion(code) {
            // 自動偵測 code 欄位綁定位置
            if (typeof this.codeval !== 'undefined') {
                this.codeval = code;
            } else if (this.formData && typeof this.formData.code !== 'undefined') {
                this.formData.code = code;
            }
            // 同步 native input（傳統 form 需要）
            var codeField = this.$refs && this.$refs.codeField;
            if (codeField) {
                codeField.value = code;
            }
            this._ci_codeValid = true;
            this._ci_codeError = '';
        },

        ciGetFinalCode(userInput) {
            var val = (userInput || '').trim();
            return val || this._ci_generatedCode;
        }
    };
}
