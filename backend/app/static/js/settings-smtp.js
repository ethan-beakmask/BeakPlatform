/* settings-smtp.js — SMTP 設定管理 (Mode A) */

function smtpManager() {
    return {
        configs: [],
        loading: true,
        showModal: false,
        showDeleteModal: false,
        isEditing: false,
        configToDelete: null,
        presets: {},
        formData: {
            name: '',
            smtp_host: '',
            smtp_port: 587,
            use_tls: true,
            use_ssl: false,
            username: '',
            password: '',
            from_email: '',
            from_name: '',
            provider_type: 'generic',
            use_app_password: false,
            is_default: false,
            is_active: true
        },

        async init() {
            await Promise.all([
                this.loadConfigs(),
                this.loadPresets()
            ]);
        },

        async loadConfigs() {
            this.loading = true;
            try {
                var response = await fetch('/bp/api/admin/settings/smtp');
                var result = await response.json();
                if (result.success) {
                    this.configs = result.data;
                }
            } catch (error) {
                console.error('載入 SMTP 設定失敗:', error);
            } finally {
                this.loading = false;
            }
        },

        async loadPresets() {
            try {
                var response = await fetch('/bp/api/admin/settings/smtp/presets');
                var result = await response.json();
                if (result.success) {
                    this.presets = result.data;
                }
            } catch (error) {
                console.error('載入預設值失敗:', error);
            }
        },

        applyPreset() {
            var preset = this.presets[this.formData.provider_type];
            if (preset) {
                this.formData.smtp_host = preset.smtp_host;
                this.formData.smtp_port = preset.smtp_port;
                this.formData.use_tls = preset.use_tls;
                this.formData.use_ssl = preset.use_ssl;
            }
        },

        openCreateModal() {
            this.isEditing = false;
            this.formData = {
                name: '',
                smtp_host: '',
                smtp_port: 587,
                use_tls: true,
                use_ssl: false,
                username: '',
                password: '',
                from_email: '',
                from_name: '',
                provider_type: 'generic',
                use_app_password: false,
                is_default: false,
                is_active: true
            };
            this.showModal = true;
        },

        async openEditModal(config) {
            this.isEditing = true;
            try {
                var response = await fetch('/bp/api/admin/settings/smtp/' + config.id);
                var result = await response.json();
                if (result.success) {
                    var data = result.data;
                    this.formData = {
                        id: data.id,
                        name: data.name,
                        smtp_host: data.smtp_host,
                        smtp_port: data.smtp_port,
                        use_tls: data.use_tls,
                        use_ssl: data.use_ssl,
                        username: data.username,
                        password: '',
                        from_email: data.from_email,
                        from_name: data.from_name || '',
                        provider_type: data.provider_type,
                        use_app_password: data.use_app_password || false,
                        is_default: data.is_default,
                        is_active: data.is_active
                    };
                    this.showModal = true;
                }
            } catch (error) {
                alert('載入設定失敗：' + error.message);
            }
        },

        closeModal() {
            this.showModal = false;
        },

        async saveConfig() {
            var data = Object.assign({}, this.formData);
            if (this.isEditing && !data.password) {
                delete data.password;
            }

            try {
                var url = this.isEditing
                    ? '/bp/api/admin/settings/smtp/' + this.formData.id
                    : '/bp/api/admin/settings/smtp';
                var method = this.isEditing ? 'PUT' : 'POST';

                var response = await fetch(url, {
                    method: method,
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify(data)
                });

                var result = await response.json();
                if (result.success) {
                    this.closeModal();
                    await this.loadConfigs();
                } else {
                    alert(result.message || '操作失敗');
                }
            } catch (error) {
                alert('操作失敗：' + error.message);
            }
        },

        async testConfig(config) {
            if (!confirm('要發送測試郵件嗎？')) return;
            var recipient = prompt('請輸入測試收件人信箱：');
            if (!recipient) return;

            try {
                var response = await fetch('/bp/api/admin/settings/smtp/' + config.id + '/test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ test_recipient: recipient })
                });

                var result = await response.json();
                alert(result.message);
                if (result.success) {
                    await this.loadConfigs();
                }
            } catch (error) {
                alert('測試失敗：' + error.message);
            }
        },

        confirmDelete(config) {
            this.configToDelete = config;
            this.showDeleteModal = true;
        },

        async deleteConfig() {
            if (!this.configToDelete) return;

            try {
                var response = await fetch('/bp/api/admin/settings/smtp/' + this.configToDelete.id, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': getCsrfToken()
                    }
                });

                var result = await response.json();
                if (result.success) {
                    this.showDeleteModal = false;
                    this.configToDelete = null;
                    await this.loadConfigs();
                } else {
                    alert(result.message || '刪除失敗');
                }
            } catch (error) {
                alert('刪除失敗：' + error.message);
            }
        }
    };
}
