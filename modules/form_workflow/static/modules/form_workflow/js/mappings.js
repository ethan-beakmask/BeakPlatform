/* mappings.js — 表單流程配對列表頁 */

function mappingsManager() {
    return {
        mappings: [],
        archivedMappings: [],
        unmappedForms: [],
        workflows: [],
        loading: true,

        showCreateModal: false,
        newMapping: { form_template_secure_code: '', workflow_template_secure_code: '' },
        saving: false,

        showVersionsModal: false,
        viewingMapping: null,
        publishedVersions: [],

        showHelpModal: false,
        showDeleteModal: false,
        deletingMapping: null,
        showArchivedList: false,

        toast: { show: false, message: '', type: 'success' },

        async init() {
            await this.loadMappings();
            await Promise.all([
                this.loadArchivedMappings(),
                this.loadUnmappedForms(),
                this.loadWorkflows(),
            ]);
            // 載入每個 mapping 的 SQL sync 狀態
            for (const m of this.mappings) {
                if (m.sql_sync_enabled) {
                    this.loadSyncStatus(m);
                }
            }
        },

        async loadMappings() {
            this.loading = true;
            try {
                const res = await fetch('/api/mappings/');
                const data = await res.json();
                if (data.success) {
                    this.mappings = data.data || [];
                }
            } catch (e) {
                console.error('載入配對失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        async loadArchivedMappings() {
            try {
                const res = await fetch('/api/mappings/?is_archived=true');
                const data = await res.json();
                if (data.success) {
                    this.archivedMappings = data.data || [];
                }
            } catch (e) {
                console.error('載入封存清單失敗:', e);
            }
        },

        async loadUnmappedForms() {
            try {
                const res = await fetch('/api/mappings/unmapped-forms');
                const data = await res.json();
                if (data.success) {
                    this.unmappedForms = data.data || [];
                }
            } catch (e) {
                console.error('載入未配對表單失敗:', e);
            }
        },

        async loadWorkflows() {
            try {
                const res = await fetch('/api/mappings/workflows-for-mapping');
                const data = await res.json();
                if (data.success) {
                    this.workflows = data.data || [];
                }
            } catch (e) {
                console.error('載入流程失敗:', e);
            }
        },

        async openCreateModal() {
            this.newMapping = { form_template_secure_code: '', workflow_template_secure_code: '' };
            this.showCreateModal = true;
            await Promise.all([this.loadUnmappedForms(), this.loadWorkflows()]);
        },

        closeCreateModal() {
            this.showCreateModal = false;
        },

        async createMapping() {
            if (this.saving) return;
            this.saving = true;

            try {
                const res = await fetch('/api/mappings/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.newMapping)
                });
                const data = await res.json();

                if (data.success) {
                    this.closeCreateModal();
                    this.showToast('配對建立成功');
                    await this.loadMappings();
                    await this.loadUnmappedForms();
                } else {
                    this.showToast(data.error || '建立失敗', 'error');
                }
            } catch (e) {
                this.showToast('建立失敗: ' + e.message, 'error');
            } finally {
                this.saving = false;
            }
        },

        async publishMapping(m) {
            if (!confirm(`確定要新發行「${m.form_template_name}」與「${m.workflow_template_name}」的配對嗎？`)) return;

            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/publish`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();

                if (data.success) {
                    this.showToast(data.message || '發行成功');
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '發行失敗', 'error');
                }
            } catch (e) {
                this.showToast('發行失敗: ' + e.message, 'error');
            }
        },

        async viewPublished(m) {
            this.viewingMapping = m;
            this.publishedVersions = [];
            this.showVersionsModal = true;

            try {
                const res = await fetch(`/api/mappings/published?mapping_secure_code=${m.secure_code}`);
                const data = await res.json();
                if (data.success) {
                    this.publishedVersions = data.data || [];
                }
            } catch (e) {
                console.error('載入版本失敗:', e);
            }
        },

        async suspendVersion(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/suspend`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已暫停');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async reopenVersion(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/reopen`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已重新開放');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async archiveVersion(v) {
            if (!confirm('確定要封存此版本嗎？封存後無法重新開放。')) return;

            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/archive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('已封存');
                    await this.viewPublished(this.viewingMapping);
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        async archiveMapping(m) {
            if (!confirm(`確定要封存「${m.form_template_name}」與「${m.workflow_template_name}」的配對嗎？`)) return;

            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/archive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('配對已封存');
                    await this.loadMappings();
                    await this.loadArchivedMappings();
                } else {
                    this.showToast(data.error || '封存失敗', 'error');
                }
            } catch (e) {
                this.showToast('封存失敗: ' + e.message, 'error');
            }
        },

        async unarchiveMapping(a) {
            try {
                const res = await fetch(`/api/mappings/${a.secure_code}/unarchive`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast('配對已恢復');
                    await this.loadMappings();
                    await this.loadArchivedMappings();
                } else {
                    this.showToast(data.error || '恢復失敗', 'error');
                }
            } catch (e) {
                this.showToast('恢復失敗: ' + e.message, 'error');
            }
        },

        async deleteVersion(v) {
            if (!confirm(`確定要刪除版本 v${v.publish_version} 嗎？此操作無法還原。`)) return;

            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (data.success) {
                    this.showToast(data.message || '版本已刪除');
                    await this.viewPublished(this.viewingMapping);
                    await this.loadMappings();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        confirmDelete(m) {
            this.deletingMapping = m;
            this.showDeleteModal = true;
        },

        async deleteMapping() {
            if (!this.deletingMapping) return;

            try {
                const res = await fetch(`/api/mappings/${this.deletingMapping.secure_code}`, {
                    method: 'DELETE'
                });
                const data = await res.json();

                if (data.success) {
                    this.showDeleteModal = false;
                    this.showToast('配對已解除');
                    await this.loadMappings();
                    await this.loadUnmappedForms();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        async toggleSqlSync(m, enabled) {
            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/sql-sync`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sql_sync_enabled: enabled })
                });
                const data = await res.json();
                if (data.success) {
                    m.sql_sync_enabled = enabled;
                    this.showToast(data.message || (enabled ? 'SQL 同步已啟用' : 'SQL 同步已停用'));
                    if (enabled) {
                        this.loadSyncStatus(m);
                    } else {
                        m._syncInfo = '';
                    }
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                    m.sql_sync_enabled = !enabled; // revert
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
                m.sql_sync_enabled = !enabled;
            }
        },

        async loadSyncStatus(m) {
            try {
                const res = await fetch(`/api/mappings/${m.secure_code}/sql-sync/status`);
                const data = await res.json();
                if (data.success && data.data.tables && data.data.tables.length > 0) {
                    const latest = data.data.tables[0]; // 按 publish_version desc
                    m._syncInfo = `${latest.row_count || 0} 筆`;
                }
            } catch (e) {
                // silent
            }
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            const d = new Date(dateStr);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', {hour: '2-digit', minute: '2-digit'});
        },

        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        }
    };
}
