/* mappings.js — 表單流程配對列表頁 */

function mappingsManager() {
    return {
        mappings: [],
        archivedMappings: [],
        unmappedForms: [],
        workflows: [],
        numberingRules: [],
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

        get defaultRuleName() {
            const def = this.numberingRules.find(r => r.is_form_default);
            return def ? def.name : '';
        },

        async init() {
            // numberingRules 必須先載入，否則 select 的 option 不存在導致綁定失敗
            await this.loadNumberingRules();
            await this.loadMappings();
            await Promise.all([
                this.loadArchivedMappings(),
                this.loadUnmappedForms(),
                this.loadWorkflows(),
            ]);
        },

        async loadMappings() {
            this.loading = true;
            try {
                const res = await fetch('/api/mappings/');
                const data = await res.json();
                if (data.success) {
                    this.mappings = (data.data || []).map(m => ({
                        ...m,
                        numbering_rule_secure_code: m.numbering_rule_secure_code || ''
                    }));
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
                    // 載入每個已啟用 SQL sync 版本的同步狀態
                    for (const v of this.publishedVersions) {
                        if (v.sql_sync_enabled) {
                            this.loadSyncStatus(v);
                        }
                    }
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

        confirmDeleteArchived(a) {
            this.deletingMapping = a;
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
                    await this.loadArchivedMappings();
                    await this.loadUnmappedForms();
                } else {
                    this.showToast(data.error || '刪除失敗', 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            }
        },

        async toggleSqlSync(v, enabled) {
            // 只允許啟用，不允許關閉（後端也有擋）
            if (!enabled) {
                v.sql_sync_enabled = true; // revert checkbox
                return;
            }
            if (!confirm('啟用 SQL 同步後無法關閉，確定啟用？')) {
                v.sql_sync_enabled = false; // revert checkbox
                return;
            }
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/sql-sync`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sql_sync_enabled: true })
                });
                const data = await res.json();
                if (data.success) {
                    v.sql_sync_enabled = true;
                    this.showToast(data.message || 'SQL 同步已啟用');
                    this.loadSyncStatus(v);
                } else {
                    this.showToast(data.error || '操作失敗', 'error');
                    v.sql_sync_enabled = !enabled; // revert
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
                v.sql_sync_enabled = !enabled;
            }
        },

        async loadSyncStatus(v) {
            try {
                const res = await fetch(`/api/mappings/published/${v.secure_code}/sql-sync/status`);
                const data = await res.json();
                if (data.success && data.data.table) {
                    v._syncInfo = `${data.data.table.row_count || 0} 筆`;
                    v._tableName = data.data.table.table_name || '';
                }
            } catch (e) {
                // silent
            }
        },

        async loadNumberingRules() {
            try {
                const res = await fetch('/api/mappings/numbering-rules');
                const data = await res.json();
                if (data.success) {
                    this.numberingRules = data.data || [];
                }
            } catch (e) {
                console.error('載入編號規則失敗:', e);
            }
        },

        getNumberingPreview(m) {
            const sc = m.numbering_rule_secure_code;
            if (!sc) {
                // 企業預設
                const def = this.numberingRules.find(r => r.is_form_default);
                return def ? def.preview : '';
            }
            const rule = this.numberingRules.find(r => r.secure_code === sc);
            return rule ? rule.preview : '';
        },

        async updateNumberingRule(m, ruleSecureCode) {
            try {
                const res = await fetch(`/api/mappings/${m.secure_code}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ numbering_rule_secure_code: ruleSecureCode || null })
                });
                const data = await res.json();
                if (data.success) {
                    m.numbering_rule_secure_code = ruleSecureCode || null;
                    this.showToast('編號規則已更新');
                } else {
                    this.showToast(data.error || '更新失敗', 'error');
                    await this.loadMappings();
                }
            } catch (e) {
                this.showToast('更新失敗: ' + e.message, 'error');
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
