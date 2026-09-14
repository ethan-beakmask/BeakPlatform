/**
 * topbar-offset.js
 * 動態計算 .bk-topbar-fixed 高度，設定：
 *   1. .main-content 的 padding-top（內容不被遮擋）
 *   2. CSS 變數 --topbar-height（供各頁面 sticky thead 使用）
 */
(function () {
    function adjustOffset() {
        var topbar = document.querySelector('.bk-topbar-fixed');
        var main = document.querySelector('.main-content');
        var h = topbar ? topbar.offsetHeight : 0;
        document.documentElement.style.setProperty('--topbar-height', h + 'px');
        if (main) {
            main.style.paddingTop = topbar ? (h + 30) + 'px' : '0';
        }
    }

    // DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', adjustOffset);
    } else {
        adjustOffset();
    }

    // 視窗縮放時重算（選單可能換行）
    window.addEventListener('resize', adjustOffset);

    // 提供給外部呼叫（如 broadcast-poller 插入跑馬燈後重算）
    window.adjustTopbarOffset = adjustOffset;
})();
