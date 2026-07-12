/* approval-limits.js — 核決上限儲存邏輯 (Mode B) */

var __LIMITS_CONFIG = window.__LIMITS_CONFIG || {};

async function saveLimits() {
    var btn = document.getElementById('btn-save');
    var msg = document.getElementById('save-message');

    btn.disabled = true;
    btn.textContent = __('儲存中...');
    msg.textContent = '';
    msg.className = '';

    var limitsData = [];
    document.querySelectorAll('.limit-input').forEach(function(input) {
        var levelCode = input.dataset.level;
        var value = parseInt(input.value, 10);
        if (isNaN(value) || value < 0) value = 0;
        limitsData.push({
            job_level_secure_code: levelCode,
            approval_limit: value
        });
    });

    try {
        var resp = await fetch(__LIMITS_CONFIG.saveUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify({ limits: limitsData })
        });
        var data = await resp.json();
        if (data.success) {
            window.location.href = __LIMITS_CONFIG.listUrl;
            return;
        } else {
            msg.className = 'msg-error';
            msg.textContent = __('儲存失敗: ') + data.error;
        }
    } catch (err) {
        msg.className = 'msg-error';
        msg.textContent = __('請求失敗: ') + err.message;
    }

    btn.disabled = false;
    btn.textContent = __('儲存變更');
    setTimeout(function() { msg.textContent = ''; }, 3000);
}
