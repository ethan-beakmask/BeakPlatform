/* settings.js — 系統設定頁面 (企業資訊 + 一般設定 + 密碼政策 + 選單高亮) */

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

// Logo 設定
function logoSettings() {
    return {
        logoUrl: null,
        uploading: false,
        message: '',
        messageType: 'success',

        async init() {
            await this.loadLogo();
        },

        async loadLogo() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/logo');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.data.logo_url) {
                        this.logoUrl = data.data.logo_url;
                    }
                }
            } catch (err) {
                console.error('載入 Logo 失敗:', err);
            }
        },

        async uploadLogo(event) {
            const file = event.target.files[0];
            if (!file) return;

            this.uploading = true;
            this.message = '';

            const formData = new FormData();
            formData.append('logo', file);

            try {
                const response = await fetch(window.__BP + '/api/admin/settings/logo', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    this.logoUrl = data.data.logo_url + '?t=' + Date.now();  // 避免快取
                    this.message = __('Logo 上傳成功');
                    this.messageType = 'success';
                } else {
                    this.message = data.message || __('上傳失敗');
                    this.messageType = 'error';
                }
            } catch (err) {
                this.message = __('上傳失敗: ') + err.message;
                this.messageType = 'error';
            } finally {
                this.uploading = false;
                event.target.value = '';  // 清除檔案選擇
                setTimeout(() => { this.message = ''; }, 3000);
            }
        },

        async deleteLogo() {
            if (!confirm(__('確定要刪除企業 Logo 嗎？'))) return;

            try {
                const response = await fetch(window.__BP + '/api/admin/settings/logo', {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                });

                const data = await response.json();

                if (data.success) {
                    this.logoUrl = null;
                    this.message = __('Logo 已刪除');
                    this.messageType = 'success';
                } else {
                    this.message = data.message || __('刪除失敗');
                    this.messageType = 'error';
                }
            } catch (err) {
                this.message = __('刪除失敗: ') + err.message;
                this.messageType = 'error';
            }
            setTimeout(() => { this.message = ''; }, 3000);
        }
    };
}

// 一般設定
function generalSettings() {
    return {
        settings: {
            allow_user_self_edit: true,
            locale: 'zh-TW',
            country: 'TW',
            timezone: 'Asia/Taipei',
            name_connector: '.',
            display_name_field: 'native_name'
        },
        saveMessage: '',

        async init() {
            await this.loadSettings();
        },

        async loadSettings() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/general');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        this.settings = data.data;
                    }
                }
            } catch (err) {
                console.error('載入設定失敗:', err);
            }
        },

        async saveSettings() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/general', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(this.settings)
                });

                const data = await response.json();
                if (data.success) {
                    this.saveMessage = __('設定已儲存');
                    setTimeout(() => { this.saveMessage = ''; }, 2000);
                } else {
                    alert(__('儲存失敗: ') + (data.message || __('未知錯誤')));
                }
            } catch (err) {
                console.error('儲存設定失敗:', err);
                alert(__('儲存失敗: ') + err.message);
            }
        }
    };
}

// 登入頁面品牌設定
function loginBrandingSettings() {
    return {
        settings: {
            login_employee_show_logo: true,
            login_employee_show_name: true,
            login_external_show_logo: true,
            login_external_show_name: true
        },
        saveMessage: '',

        async init() {
            await this.loadSettings();
        },

        async loadSettings() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/general');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        const d = data.data;
                        this.settings.login_employee_show_logo = d.login_employee_show_logo !== false;
                        this.settings.login_employee_show_name = d.login_employee_show_name !== false;
                        this.settings.login_external_show_logo = d.login_external_show_logo !== false;
                        this.settings.login_external_show_name = d.login_external_show_name !== false;
                    }
                }
            } catch (err) {
                console.error('載入登入品牌設定失敗:', err);
            }
        },

        async saveSetting(key, value) {
            try {
                const payload = {};
                payload[key] = value;
                const response = await fetch(window.__BP + '/api/admin/settings/general', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();
                if (data.success) {
                    this.saveMessage = __('設定已儲存');
                    setTimeout(() => { this.saveMessage = ''; }, 2000);
                } else {
                    alert(__('儲存失敗: ') + (data.message || __('未知錯誤')));
                }
            } catch (err) {
                console.error('儲存設定失敗:', err);
                alert(__('儲存失敗: ') + err.message);
            }
        }
    };
}

function passwordPolicySettings() {
    return {
        policy: {
            enabled: true,
            min_length: 12,
            require_uppercase: true,
            require_lowercase: true,
            require_digit: true,
            require_special: true,
            history_count: 5,
            max_failed_attempts: 5,
            lockout_duration_minutes: 15,
            lockout_multiplier: 2
        },
        systemMailReady: false,
        saveMessage: '',

        async init() {
            await this.loadPolicy();
        },

        async loadPolicy() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/password-policy');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        this.policy = { ...this.policy, ...data.data.policy };
                        this.systemMailReady = data.data.system_mail_ready;
                    }
                }
            } catch (err) {
                console.error('載入密碼政策失敗:', err);
            }
        },

        async savePolicy() {
            try {
                const response = await fetch(window.__BP + '/api/admin/settings/password-policy', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(this.policy)
                });

                const data = await response.json();
                if (data.success) {
                    this.systemMailReady = data.data.system_mail_ready;
                    this.saveMessage = __('設定已儲存');
                    setTimeout(() => { this.saveMessage = ''; }, 2000);
                } else {
                    alert(__('儲存失敗: ') + (data.message || __('未知錯誤')));
                }
            } catch (err) {
                console.error('儲存密碼政策失敗:', err);
                alert(__('儲存失敗: ') + err.message);
            }
        }
    };
}

// 左側選單高亮
document.addEventListener('DOMContentLoaded', function() {
    const navLinks = document.querySelectorAll('.settings-nav a');
    const sections = document.querySelectorAll('.settings-section');

    function updateActiveLink() {
        let current = '';
        sections.forEach(section => {
            const rect = section.getBoundingClientRect();
            if (rect.top <= 100) {
                current = section.id;
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === '#' + current) {
                link.classList.add('active');
            }
        });
    }

    window.addEventListener('scroll', updateActiveLink);
    updateActiveLink();

    // 處理 hash 導覽
    if (window.location.hash) {
        const target = document.querySelector(window.location.hash);
        if (target) {
            setTimeout(() => target.scrollIntoView({ behavior: 'smooth' }), 100);
        }
    }
});
