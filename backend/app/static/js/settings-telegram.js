/* settings-telegram.js — Telegram 設定管理 (Mode A) */

function telegramManager() {
    return {
        configs: [],
        loading: true,
        showModal: false,
        showDeleteModal: false,
        isEditing: false,
        configToDelete: null,
        formData: {
            name: '',
            description: '',
            bot_token: '',
            channels: [],
            default_channel: '',
            is_active: true
        },

        async init() {
            await this.loadConfigs();
        },

        async loadConfigs() {
            this.loading = true;
            try {
                var response = await fetch(window.__BP + '/api/admin/settings/telegram');
                var result = await response.json();
                if (result.success) {
                    this.configs = result.data;
                }
            } catch (error) {
                console.error('載入 Telegram 設定失敗:', error);
            } finally {
                this.loading = false;
            }
        },

        openCreateModal() {
            this.isEditing = false;
            this.formData = {
                name: '',
                description: '',
                bot_token: '',
                channels: [],
                default_channel: '',
                is_active: true
            };
            this.showModal = true;
        },

        async openEditModal(config) {
            this.isEditing = true;
            try {
                var response = await fetch(window.__BP + '/api/admin/settings/telegram/' + config.id);
                var result = await response.json();
                if (result.success) {
                    var data = result.data;
                    var channelsArray = Object.entries(data.channels || {}).map(function(entry) {
                        return { name: entry[0], chat_id: entry[1] };
                    });
                    this.formData = {
                        id: data.id,
                        name: data.name,
                        description: data.description || '',
                        bot_token: data.bot_token,
                        channels: channelsArray,
                        default_channel: data.default_channel || '',
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

        addChannel() {
            this.formData.channels.push({ name: '', chat_id: '' });
        },

        removeChannel(index) {
            var removed = this.formData.channels.splice(index, 1)[0];
            if (this.formData.default_channel === removed.name) {
                this.formData.default_channel = '';
            }
        },

        async saveConfig() {
            var channels = {};
            for (var i = 0; i < this.formData.channels.length; i++) {
                var ch = this.formData.channels[i];
                if (ch.name && ch.chat_id) {
                    channels[ch.name] = ch.chat_id;
                }
            }

            var data = {
                name: this.formData.name,
                description: this.formData.description,
                bot_token: this.formData.bot_token,
                channels: channels,
                default_channel: this.formData.default_channel,
                is_active: this.formData.is_active
            };

            try {
                var url = this.isEditing
                    ? window.__BP + '/api/admin/settings/telegram/' + this.formData.id
                    : window.__BP + '/api/admin/settings/telegram';
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
            var channels = config.channels || {};
            var channelNames = Object.keys(channels);

            var chatId = null;
            if (channelNames.length === 0) {
                alert('此設定沒有頻道，請先新增頻道');
                return;
            } else if (channelNames.length === 1) {
                chatId = channels[channelNames[0]];
            } else {
                var choice = prompt('選擇測試頻道 (' + channelNames.join(', ') + ')：', config.default_channel || channelNames[0]);
                if (!choice) return;
                chatId = channels[choice];
                if (!chatId) {
                    alert('找不到該頻道');
                    return;
                }
            }

            try {
                var response = await fetch(window.__BP + '/api/admin/settings/telegram/' + config.id + '/test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken()
                    },
                    body: JSON.stringify({ chat_id: chatId })
                });

                var result = await response.json();
                alert(result.message);
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
                var response = await fetch(window.__BP + '/api/admin/settings/telegram/' + this.configToDelete.id, {
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
