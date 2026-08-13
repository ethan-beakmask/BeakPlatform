/* 站內使用者手冊的 Mermaid 渲染（封閉網路：只用本地 vendor/mermaid.min.js）
 *
 * docs/manual/ 的 md 是站內 /help/ 與 MkDocs 站共用的同一批來源。
 * MkDocs 端由 docs/javascripts/mermaid-init.js 處理 ```mermaid 區塊；
 * 站內是 python-markdown 直接渲染，產出的是
 *     <pre><code class="language-mermaid">flowchart LR ...</code></pre>
 * 沒有這支腳本的話，使用者看到的是幾十行流程圖原始碼。
 */
(function () {
    function render() {
        var blocks = document.querySelectorAll('pre > code.language-mermaid');
        if (!blocks.length) {
            return;
        }
        if (!window.mermaid) {
            console.error('mermaid not loaded: static/vendor/mermaid.min.js');
            return;
        }

        window.mermaid.initialize({
            startOnLoad: false,
            theme: 'neutral',
            securityLevel: 'strict',
            flowchart: { htmlLabels: true, curve: 'basis' }
        });

        for (var i = 0; i < blocks.length; i++) {
            var pre = blocks[i].parentNode;
            var div = document.createElement('div');
            div.className = 'manual-mermaid';
            div.textContent = blocks[i].textContent;
            pre.parentNode.replaceChild(div, pre);
        }
        window.mermaid.run({ querySelector: '.manual-mermaid' });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', render);
    } else {
        render();
    }
})();
