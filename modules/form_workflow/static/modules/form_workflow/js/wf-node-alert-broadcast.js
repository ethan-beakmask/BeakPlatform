/**
 * wf-node-alert-broadcast.js -- AlertBroadcast 緊急廣播節點配置
 * 從 wf-node-configs.js 拆分
 */

        function toggleAbTargetFields() {
            const targetType = document.getElementById('abTargetType')?.value;
            const fields = document.getElementById('abTargetFields');
            if (fields) {
                fields.style.display = targetType === 'specific' ? '' : 'none';
            }
        }
        window.toggleAbTargetFields = toggleAbTargetFields;

        function loadAlertBroadcastOptions(selectedRoles, selectedDepts) {
            // 載入角色
            fetch(window.__BP + '/api/form-workflow/data/org-roles', {
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
            })
            .then(r => r.json())
            .then(data => {
                const sel = document.getElementById('abTargetRoles');
                if (!sel) return;
                sel.innerHTML = '';
                (data.roles || data.data || []).forEach(role => {
                    const opt = document.createElement('option');
                    opt.value = role.secure_code || role.code;
                    opt.textContent = role.name;
                    if (selectedRoles.includes(opt.value)) opt.selected = true;
                    sel.appendChild(opt);
                });
            })
            .catch(() => {});

            // 載入部門
            fetch(window.__BP + '/api/form-workflow/data/org-departments', {
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || '' }
            })
            .then(r => r.json())
            .then(data => {
                const sel = document.getElementById('abTargetDepartments');
                if (!sel) return;
                sel.innerHTML = '';
                (data.departments || data.data || []).forEach(dept => {
                    const opt = document.createElement('option');
                    opt.value = dept.secure_code || dept.code;
                    opt.textContent = (dept.full_path || dept.name);
                    if (selectedDepts.includes(opt.value)) opt.selected = true;
                    sel.appendChild(opt);
                });
            })
            .catch(() => {});
        }
        window.loadAlertBroadcastOptions = loadAlertBroadcastOptions;

        function applyAlertBroadcastConfig(nodeId) {
            const node = applyNodeBasicInfo(nodeId, true);
            if (!node) return;

            const broadcastCode = document.getElementById('abBroadcastCode')?.value?.trim();
            const title = document.getElementById('abTitle')?.value?.trim();
            const message = document.getElementById('abMessage')?.value?.trim();

            if (!broadcastCode) {
                updateStatus('請輸入廣播代碼', 'warning');
                return;
            }
            if (!title) {
                updateStatus('請輸入標題', 'warning');
                return;
            }

            const targetType = document.getElementById('abTargetType')?.value || 'all';
            const requireAck = document.getElementById('abRequireAck')?.checked ?? true;
            const includeChildren = document.getElementById('abIncludeChildren')?.checked ?? true;

            const currentConfig = node.data('config') || {};
            const updatedConfig = {
                ...currentConfig,
                broadcast_code: broadcastCode,
                title: title,
                message: message,
                target_type: targetType,
                require_ack: requireAck,
            };

            if (targetType === 'specific') {
                const rolesEl = document.getElementById('abTargetRoles');
                const deptsEl = document.getElementById('abTargetDepartments');
                updatedConfig.target_roles = rolesEl ? Array.from(rolesEl.selectedOptions).map(o => o.value) : [];
                updatedConfig.target_departments = deptsEl ? Array.from(deptsEl.selectedOptions).map(o => o.value) : [];
                updatedConfig.include_children = includeChildren;
            }

            node.data('config', updatedConfig);
            updateStatus('緊急廣播設定已套用', 'success');
        }
        window.applyAlertBroadcastConfig = applyAlertBroadcastConfig;
