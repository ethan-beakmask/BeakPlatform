(function() {
    'use strict';

    const BP = window.__BP || '';
    const ENDPOINT = window.__CURRENT_ENDPOINT || '';
    const PATH = window.location.pathname.startsWith(BP)
        ? window.location.pathname.slice(BP.length) || '/'
        : window.location.pathname;

    // 不在登入頁等公開頁顯示
    if (window.__HIDE_HELP_BUTTON) return;

    function buildButton() {
        const btn = document.createElement('button');
        btn.className = 'bk-help-btn';
        btn.title = __('本頁說明');
        btn.setAttribute('aria-label', __('本頁說明'));
        btn.innerHTML = '<i class="ri-question-line"></i>';
        btn.addEventListener('click', openModal);
        document.body.appendChild(btn);
    }

    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[c]);
    }

    async function openModal() {
        const overlay = document.createElement('div');
        overlay.className = 'bk-help-modal-overlay';
        overlay.innerHTML = `
            <div class="bk-help-modal" role="dialog" aria-modal="true">
                <div class="bk-help-modal-header">
                    <div class="bk-help-modal-title">${__('載入說明中...')}</div>
                    <button type="button" class="bk-help-modal-close" aria-label="${__('關閉')}">&times;</button>
                </div>
                <div class="bk-help-modal-body">
                    <div class="bk-help-empty">${__('載入中...')}</div>
                </div>
                <div class="bk-help-footer"></div>
            </div>
        `;
        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        overlay.querySelector('.bk-help-modal-close').addEventListener('click', close);
        overlay.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
        // 不用 click.away 關閉，避免誤觸；只能透過 X 或 Esc 關閉

        const titleEl = overlay.querySelector('.bk-help-modal-title');
        const bodyEl = overlay.querySelector('.bk-help-modal-body');
        const footerEl = overlay.querySelector('.bk-help-footer');

        try {
            const params = new URLSearchParams();
            if (ENDPOINT) params.set('endpoint', ENDPOINT);
            params.set('path', PATH);
            const resp = await fetch(`${BP}/help/api/page?${params.toString()}`);
            const data = await resp.json();

            if (!data.found) {
                titleEl.textContent = __('本頁說明');
                bodyEl.innerHTML = `
                    <div class="bk-help-empty">
                        <p>${escapeHtml(data.message || __('此頁面尚未提供說明文件'))}</p>
                    </div>
                `;
                footerEl.innerHTML = `<a href="${BP}/help/">${__('查看完整說明文件')}</a>`;
                return;
            }

            titleEl.textContent = data.title || __('本頁說明');
            const sectionsHtml = (data.sections || []).map(sec => {
                const tag = sec.audience && sec.audience !== '*'
                    ? `<div class="bk-help-audience-tag">${__('適用：{audience}', {audience: escapeHtml(sec.audience)})}</div>`
                    : '';
                return `<div class="bk-help-section">${tag}${sec.html}</div>`;
            }).join('');
            bodyEl.innerHTML = sectionsHtml || `<div class="bk-help-empty">${__('內容為空')}</div>`;
            footerEl.innerHTML = `
                <a href="${BP}/help/page/${encodeURIComponent(data.menu_code)}" target="_blank">${__('在新視窗開啟完整版')}</a>
                &nbsp;|&nbsp;
                <a href="${BP}/help/">${__('所有說明文件')}</a>
            `;
        } catch (err) {
            titleEl.textContent = __('載入失敗');
            bodyEl.innerHTML = `<div class="bk-help-empty">${__('載入說明時發生錯誤：{message}', {message: escapeHtml(err.message || err)})}</div>`;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', buildButton);
    } else {
        buildButton();
    }
})();
