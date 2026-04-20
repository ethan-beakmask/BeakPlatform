/**
 * BeakPlatform Broadcast Poller
 *
 * 定時 polling /api/broadcasts/active，處理兩種廣播：
 * 1. NavbarBroadcast: 在 navbar 和 menubar 之間顯示跑馬燈
 * 2. AlertBroadcast:  全頁強制彈窗，捲底勾選確認才能關閉
 *
 * 依賴：broadcast.css
 * 設定：window.__BROADCAST_POLL_INTERVAL (分鐘)
 */
(function () {
    'use strict';

    var POLL_INTERVAL = (window.__BROADCAST_POLL_INTERVAL || 1) * 60 * 1000;
    var CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var _timer = null;
    var _marqueeEl = null;
    var _currentNavbarItems = [];
    var _currentNavbarIndex = 0;
    var _rotateTimer = null;
    var _activeAlerts = {};  // secure_code -> true (prevent duplicate popups)

    // ================================================================
    // Init
    // ================================================================
    function init() {
        poll();
        _timer = setInterval(poll, POLL_INTERVAL);
    }

    function poll() {
        fetch(window.__BP + '/api/broadcasts/active', {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': CSRF_TOKEN }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (!data.success) return;
            handleNavbar(data.navbar || []);
            handleAlerts(data.alerts || []);
        })
        .catch(function () { /* silent */ });
    }

    // ================================================================
    // NavbarBroadcast - 跑馬燈
    // ================================================================
    function handleNavbar(items) {
        if (items.length === 0) {
            removeMarquee();
            return;
        }
        _currentNavbarItems = items;
        ensureMarquee();
        showNavbarItem(0);
        startRotation();
    }

    function ensureMarquee() {
        if (_marqueeEl) return;
        var topbar = document.querySelector('.bk-topbar-fixed');
        var menubar = document.querySelector('.bk-menubar');
        if (!topbar || !menubar) return;

        _marqueeEl = document.createElement('div');
        _marqueeEl.className = 'bk-broadcast-marquee';
        _marqueeEl.innerHTML = '<span class="bk-broadcast-marquee-inner"></span>';

        // 滑鼠懸停暫停
        _marqueeEl.addEventListener('mouseenter', function () {
            _marqueeEl.classList.add('bk-marquee-paused');
        });
        _marqueeEl.addEventListener('mouseleave', function () {
            _marqueeEl.classList.remove('bk-marquee-paused');
        });

        topbar.insertBefore(_marqueeEl, menubar);

        // 通知 topbar-offset 重新計算
        if (typeof window.adjustTopbarOffset === 'function') {
            setTimeout(window.adjustTopbarOffset, 50);
        }
    }

    function removeMarquee() {
        if (!_marqueeEl) return;
        _marqueeEl.remove();
        _marqueeEl = null;
        _currentNavbarItems = [];
        _currentNavbarIndex = 0;
        if (_rotateTimer) {
            clearInterval(_rotateTimer);
            _rotateTimer = null;
        }
        if (typeof window.adjustTopbarOffset === 'function') {
            setTimeout(window.adjustTopbarOffset, 50);
        }
    }

    function showNavbarItem(index) {
        if (!_marqueeEl || _currentNavbarItems.length === 0) return;
        var item = _currentNavbarItems[index % _currentNavbarItems.length];
        _marqueeEl.style.backgroundColor = item.bg_color || '#FDE047';
        _marqueeEl.style.color = item.text_color || '#000000';

        var inner = _marqueeEl.querySelector('.bk-broadcast-marquee-inner');
        if (inner) {
            inner.textContent = item.message;
            // 重置動畫
            inner.style.animation = 'none';
            inner.offsetHeight; // trigger reflow
            inner.style.animation = '';
        }
        _currentNavbarIndex = index;
    }

    function startRotation() {
        if (_rotateTimer) clearInterval(_rotateTimer);
        if (_currentNavbarItems.length <= 1) return;

        // 使用第一條的 display_seconds
        var sec = (_currentNavbarItems[0].display_seconds || 5) * 1000;
        // 每條至少 15 秒（含動畫走完時間）
        if (sec < 15000) sec = 15000;

        _rotateTimer = setInterval(function () {
            _currentNavbarIndex = (_currentNavbarIndex + 1) % _currentNavbarItems.length;
            showNavbarItem(_currentNavbarIndex);
        }, sec);
    }

    // ================================================================
    // AlertBroadcast - 緊急廣播彈窗
    // ================================================================
    function handleAlerts(items) {
        items.forEach(function (item) {
            if (_activeAlerts[item.secure_code]) return;
            _activeAlerts[item.secure_code] = true;
            showAlertDialog(item);
        });
    }

    function showAlertDialog(item) {
        var overlay = document.createElement('div');
        overlay.className = 'bk-alert-overlay';
        overlay.setAttribute('data-broadcast', item.secure_code);

        var requireAck = item.require_ack !== false;
        var ackSection = '';
        if (requireAck) {
            ackSection = '<div class="bk-alert-scroll-hint" id="bk-scroll-hint-' + item.secure_code + '">' +
                '(請捲至底部閱讀完整訊息)' +
                '</div>' +
                '<div class="bk-alert-ack-row">' +
                '<input type="checkbox" id="bk-ack-cb-' + item.secure_code + '" disabled>' +
                '<label for="bk-ack-cb-' + item.secure_code + '" class="bk-disabled" id="bk-ack-label-' + item.secure_code + '">' +
                '我已閱讀並知悉以上訊息' +
                '</label>' +
                '</div>' +
                '<button class="bk-alert-confirm-btn" disabled id="bk-ack-btn-' + item.secure_code + '">' +
                '已知道' +
                '</button>';
        } else {
            ackSection = '<button class="bk-alert-confirm-btn" id="bk-ack-btn-' + item.secure_code + '">' +
                '關閉' +
                '</button>';
        }

        overlay.innerHTML =
            '<div class="bk-alert-dialog">' +
                '<div class="bk-alert-header"><h2>' + escapeHtml(item.title) + '</h2></div>' +
                '<div class="bk-alert-body" id="bk-alert-body-' + item.secure_code + '">' +
                    item.message +
                '</div>' +
                '<div class="bk-alert-footer">' +
                    ackSection +
                '</div>' +
            '</div>';

        document.body.appendChild(overlay);

        var body = document.getElementById('bk-alert-body-' + item.secure_code);
        var btn = document.getElementById('bk-ack-btn-' + item.secure_code);

        if (requireAck) {
            var cb = document.getElementById('bk-ack-cb-' + item.secure_code);
            var label = document.getElementById('bk-ack-label-' + item.secure_code);
            var hint = document.getElementById('bk-scroll-hint-' + item.secure_code);

            // 捲動偵測 -- 捲到底才啟用 checkbox
            var scrolledToBottom = false;
            function checkScroll() {
                if (scrolledToBottom) return;
                // 容許 2px 誤差
                if (body.scrollHeight - body.scrollTop - body.clientHeight < 3) {
                    scrolledToBottom = true;
                    cb.disabled = false;
                    label.classList.remove('bk-disabled');
                    if (hint) hint.style.display = 'none';
                }
            }

            // 如果內容不需捲動（高度足夠），直接啟用
            setTimeout(function () {
                if (body.scrollHeight <= body.clientHeight + 3) {
                    scrolledToBottom = true;
                    cb.disabled = false;
                    label.classList.remove('bk-disabled');
                    if (hint) hint.style.display = 'none';
                }
            }, 100);

            body.addEventListener('scroll', checkScroll);

            cb.addEventListener('change', function () {
                btn.disabled = !cb.checked;
            });

            btn.addEventListener('click', function () {
                if (btn.disabled) return;
                acknowledgeAndClose(item.secure_code, overlay);
            });
        } else {
            btn.addEventListener('click', function () {
                closeAlert(item.secure_code, overlay);
            });
        }
    }

    function acknowledgeAndClose(securecode, overlay) {
        fetch(window.__BP + '/api/broadcasts/' + securecode + '/acknowledge', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN
            }
        })
        .then(function () { closeAlert(securecode, overlay); })
        .catch(function () { closeAlert(securecode, overlay); });
    }

    function closeAlert(securecode, overlay) {
        overlay.remove();
        delete _activeAlerts[securecode];
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ================================================================
    // Start
    // ================================================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
