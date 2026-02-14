/* fw-pending-list.js — 待簽核任務列表 (Mode A) */

function pendingListManager() {
    return {
        tasks: [],
        loading: true,

        showDetailModal: false,
        viewingTask: null,

        showApproveModal: false,
        currentTask: null,
        taskDetail: null,
        availablePaths: [],
        selectedPath: null,
        comment: '',
        submitting: false,

        async init() {
            await this.loadTasks();
        },

        async loadTasks() {
            this.loading = true;
            try {
                var res = await fetch('/api/form-workflow/pending-tasks');
                var data = await res.json();
                if (data.success) {
                    this.tasks = data.data.tasks || [];
                }
            } catch (e) {
                console.error('載入失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        viewTask(task) {
            this.viewingTask = task;
            this.showDetailModal = true;
        },

        async openApproveModal(task) {
            this.currentTask = task;
            this.taskDetail = null;
            this.availablePaths = [];
            this.selectedPath = null;
            this.comment = '';
            this.showApproveModal = true;

            try {
                var res = await fetch('/api/form-workflow/pending-tasks/' + task.queue_secure_code);
                var data = await res.json();
                if (data.success) {
                    this.taskDetail = data.data;
                    this.availablePaths = data.data.available_paths || [];
                    if (this.availablePaths.length === 1) {
                        this.selectedPath = this.availablePaths[0].id;
                    }
                }
            } catch (e) {
                console.error('載入詳情失敗:', e);
            }
        },

        closeApproveModal() {
            this.showApproveModal = false;
            this.currentTask = null;
            this.taskDetail = null;
        },

        async submitApproval() {
            if (this.submitting) return;
            if (this.availablePaths.length > 0 && !this.selectedPath) {
                alert('請選擇路徑');
                return;
            }

            this.submitting = true;
            try {
                var res = await fetch('/api/form-workflow/pending-tasks/' + this.currentTask.queue_secure_code + '/approve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        selected_path: this.selectedPath,
                        comment: this.comment
                    })
                });
                var data = await res.json();

                if (data.success) {
                    alert('簽核完成');
                    this.closeApproveModal();
                    this.loadTasks();
                } else {
                    alert('簽核失敗: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('簽核失敗: ' + e.message);
            } finally {
                this.submitting = false;
            }
        },

        formatDate(dateStr) {
            if (!dateStr) return '-';
            var d = new Date(dateStr);
            return d.toLocaleDateString('zh-TW') + ' ' + d.toLocaleTimeString('zh-TW', {hour: '2-digit', minute: '2-digit'});
        }
    };
}
