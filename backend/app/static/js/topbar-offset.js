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
        if (topbar) {
            var h = topbar.offsetHeight;
            document.documentElement.style.setProperty('--topbar-height', h + 'px');
            if (main) {
                main.style.paddingTop = h + 'px';
            }
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
})();
