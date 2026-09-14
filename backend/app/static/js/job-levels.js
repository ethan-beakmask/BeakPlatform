/**
 * 職等管理 - 左表格 + 右編輯面板 + 新增 Modal
 *
 * Window Bridge: window.__JOB_LEVELS_CONFIG
 *   - levels: 職等列表 JSON
 *   - csrfToken: CSRF token
 *   - urls: { create, edit, delete } (含 placeholder)
 */
function jobLevelsManager() {
    const config = window.__JOB_LEVELS_CONFIG || {};
    const csrfToken = config.csrfToken || '';

    return {
        // 資料
        levels: config.levels || [],
        selected: null,

        // 編輯表單
        editForm: {
            name: '',
            name_en: '',
            level_order: 0,
            is_manager_level: false,
            management_scope: '',
            description: '',
            is_active: true
        },
        editSaving: false,
        editMessage: '',
        editMessageType: '',

        // 新增 Modal
        showCreateModal: false,
        createForm: {
            name: '',
            code: '',
            name_en: '',
            level_order: '',
            is_manager_level: false,
            management_scope: '',
            description: ''
        },
        createSaving: false,
        createMessage: '',
        createMessageType: '',

        // 選擇職等
        selectLevel(level) {
            this.selected = level;
            this.editForm = {
                name: level.name,
                name_en: level.name_en,
                level_order: level.level_order,
                is_manager_level: level.is_manager_level,
                management_scope: level.management_scope,
                description: level.description,
                is_active: level.is_active
            };
            this.editMessage = '';
        },

        // 新增 Modal 開啟/關閉
        openCreateModal() {
            this.createForm = {
                name: '',
                code: '',
                name_en: '',
                level_order: '',
                is_manager_level: false,
                management_scope: '',
                description: ''
            };
            this.createMessage = '';
            this.showCreateModal = true;
        },
        closeCreateModal() {
            this.showCreateModal = false;
        },

        // 提交新增
        async submitCreate() {
            if (!this.createForm.name.trim()) {
                this.createMessage = __('職等名稱為必填');
                this.createMessageType = 'error';
                return;
            }
            if (this.createForm.level_order === '' || this.createForm.level_order === null) {
                this.createMessage = __('職等序號為必填');
                this.createMessageType = 'error';
                return;
            }

            this.createSaving = true;
            this.createMessage = '';

            const formData = new FormData();
            formData.append('csrf_token', csrfToken);
            formData.append('name', this.createForm.name.trim());
            formData.append('code', this.createForm.code.trim());
            formData.append('name_en', this.createForm.name_en.trim());
            formData.append('level_order', this.createForm.level_order);
            if (this.createForm.is_manager_level) {
                formData.append('is_manager_level', 'true');
            }
            formData.append('management_scope', this.createForm.management_scope.trim());
            formData.append('description', this.createForm.description.trim());

            try {
                const resp = await fetch(config.urls.create, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                const data = await resp.json();

                if (data.success) {
                    // 插入到列表中正確位置（由高到低排序）
                    const newLevel = data.data;
                    const idx = this.levels.findIndex(l => l.level_order < newLevel.level_order);
                    if (idx === -1) {
                        this.levels.push(newLevel);
                    } else {
                        this.levels.splice(idx, 0, newLevel);
                    }
                    this.showCreateModal = false;
                    this.selectLevel(newLevel);
                } else {
                    this.createMessage = (data.errors || [__('建立失敗')]).join(', ');
                    this.createMessageType = 'error';
                }
            } catch (err) {
                this.createMessage = __('網路錯誤: ') + err.message;
                this.createMessageType = 'error';
            } finally {
                this.createSaving = false;
            }
        },

        // 提交編輯
        async submitEdit() {
            if (!this.selected) return;

            if (!this.editForm.name.trim()) {
                this.editMessage = __('職等名稱為必填');
                this.editMessageType = 'error';
                return;
            }

            // 停用檢查：從啟用變停用時，查詢引用此職等的職稱
            if (this.selected.is_active && !this.editForm.is_active) {
                const checkUrl = config.urls.checkUsage.replace('__SC__', this.selected.secure_code);
                try {
                    const checkResp = await fetch(checkUrl, {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    const checkData = await checkResp.json();
                    if (checkData.success && checkData.count > 0) {
                        const titleList = checkData.titles.join(', ');
                        const msg = __('此職等有 ') + checkData.count + __(' 個啟用中的職稱引用:\n') +
                                    titleList + '\n\n' +
                                    __('停用後可能影響簽核流程，確定要停用嗎?');
                        if (!confirm(msg)) {
                            this.editForm.is_active = true;
                            return;
                        }
                    }
                } catch (err) {
                    this.editMessage = __('檢查引用失敗: ') + err.message;
                    this.editMessageType = 'error';
                    return;
                }
            }

            this.editSaving = true;
            this.editMessage = '';

            const url = config.urls.edit.replace('__SC__', this.selected.secure_code);
            const formData = new FormData();
            formData.append('csrf_token', csrfToken);
            formData.append('name', this.editForm.name.trim());
            formData.append('name_en', (this.editForm.name_en || '').trim());
            formData.append('level_order', this.editForm.level_order);
            if (this.editForm.is_manager_level) {
                formData.append('is_manager_level', 'true');
            }
            formData.append('management_scope', (this.editForm.management_scope || '').trim());
            formData.append('description', (this.editForm.description || '').trim());
            if (this.editForm.is_active) {
                formData.append('is_active', 'true');
            }

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                const data = await resp.json();

                if (data.success) {
                    // 更新列表中的資料
                    const updated = data.data;
                    const idx = this.levels.findIndex(l => l.secure_code === updated.secure_code);
                    if (idx !== -1) {
                        this.levels[idx] = updated;
                    }
                    this.selected = updated;

                    // 重新排序（level_order 可能變了）
                    this.levels.sort((a, b) => b.level_order - a.level_order);

                    this.editMessage = __('已儲存');
                    this.editMessageType = 'success';
                    setTimeout(() => { this.editMessage = ''; }, 2000);
                } else {
                    this.editMessage = (data.errors || [__('更新失敗')]).join(', ');
                    this.editMessageType = 'error';
                }
            } catch (err) {
                this.editMessage = __('網路錯誤: ') + err.message;
                this.editMessageType = 'error';
            } finally {
                this.editSaving = false;
            }
        },

        // 刪除
        async submitDelete() {
            if (!this.selected) return;
            if (this.selected.is_system_default) return;

            if (!confirm(__('確定要刪除職等「') + this.selected.name + __('」嗎？此操作無法復原。'))) {
                return;
            }

            const url = config.urls.delete.replace('__SC__', this.selected.secure_code);
            const formData = new FormData();
            formData.append('csrf_token', csrfToken);

            try {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    body: formData
                });
                const data = await resp.json();

                if (data.success) {
                    this.levels = this.levels.filter(l => l.secure_code !== this.selected.secure_code);
                    this.selected = null;
                    this.editMessage = '';
                } else {
                    this.editMessage = (data.errors || [__('刪除失敗')]).join(', ');
                    this.editMessageType = 'error';
                }
            } catch (err) {
                this.editMessage = __('網路錯誤: ') + err.message;
                this.editMessageType = 'error';
            }
        }
    };
}
