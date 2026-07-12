/* job-matrix.js — 職級職稱矩陣拖放邏輯 (Mode B) */

var __MATRIX_CONFIG = window.__MATRIX_CONFIG || {};

(function() {
    var draggedItem = null;
    var sourceCell = null;

    function showToast(message, type) {
        var toast = document.createElement('div');
        toast.className = 'toast ' + type;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function() { toast.remove(); }, 3000);
    }

    function getCSRFToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    async function updateTitlePosition(titleCode, newLevelCode, newFamilyCode) {
        try {
            var response = await fetch(__MATRIX_CONFIG.updateTitlePositionUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({
                    title_secure_code: titleCode,
                    new_level_secure_code: newLevelCode,
                    new_family_secure_code: newFamilyCode
                })
            });
            var data = await response.json();
            if (data.success) {
                showToast(data.message, 'success');
                return data.title;
            } else {
                showToast(__('更新失敗: ') + data.error, 'error');
                return null;
            }
        } catch (err) {
            showToast(__('請求失敗: ') + err.message, 'error');
            return null;
        }
    }

    document.querySelectorAll('.title-item[draggable="true"]').forEach(function(item) {
        item.addEventListener('dragstart', function(e) {
            draggedItem = this;
            sourceCell = this.parentElement;
            this.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', this.dataset.secureCode);
        });

        item.addEventListener('dragend', function() {
            this.classList.remove('dragging');
            draggedItem = null;
            sourceCell = null;
            document.querySelectorAll('.drag-over').forEach(function(cell) {
                cell.classList.remove('drag-over');
            });
        });
    });

    document.querySelectorAll('.title-cell').forEach(function(cell) {
        cell.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            this.classList.add('drag-over');
        });

        cell.addEventListener('dragleave', function() {
            this.classList.remove('drag-over');
        });

        cell.addEventListener('drop', async function(e) {
            e.preventDefault();
            this.classList.remove('drag-over');

            if (!draggedItem) return;

            var itemToMove = draggedItem;
            var fromCell = sourceCell;

            var targetLevel = this.dataset.level;
            var targetFamily = this.dataset.family;
            var srcLevel = fromCell.dataset.level;
            var srcFamily = fromCell.dataset.family;

            if (targetLevel === srcLevel && targetFamily === srcFamily) {
                return;
            }

            var titleCode = itemToMove.dataset.secureCode;
            var targetCell = this;

            var result = await updateTitlePosition(titleCode, targetLevel, targetFamily);
            if (result) {
                var targetEmpty = targetCell.querySelector('.empty-cell');
                if (targetEmpty) {
                    targetEmpty.remove();
                }

                targetCell.appendChild(itemToMove);

                if (result.is_supervisor) {
                    itemToMove.classList.add('supervisor');
                } else {
                    itemToMove.classList.remove('supervisor');
                }

                var remainingItems = fromCell.querySelectorAll('.title-item');
                if (remainingItems.length === 0) {
                    var emptySpan = document.createElement('span');
                    emptySpan.className = 'empty-cell';
                    emptySpan.textContent = '-';
                    fromCell.appendChild(emptySpan);
                }
            }
        });
    });
})();
