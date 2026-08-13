/* 本地 Mermaid 初始化（封閉網路：不從任何 CDN 載入）
 *
 * pymdownx.superfences 把 ```mermaid 產出成 <pre class="mermaid-diagram">，
 * 這裡把它換成 <div class="mermaid-rendered"> 再交給本地 mermaid 渲染。
 * 刻意避開 Material 內建的 .mermaid class，否則 Material 會另外去 unpkg 抓一份。
 */
(function () {
  function currentTheme() {
    var scheme = document.body.getAttribute('data-md-color-scheme');
    return scheme === 'slate' ? 'dark' : 'neutral';
  }

  function render() {
    if (!window.mermaid) {
      console.error('mermaid 未載入，檢查 assets/mermaid.min.js');
      return;
    }
    window.mermaid.initialize({
      startOnLoad: false,
      theme: currentTheme(),
      securityLevel: 'strict',
      flowchart: { htmlLabels: true, curve: 'basis' }
    });

    var pres = document.querySelectorAll('pre.mermaid-diagram');
    for (var i = 0; i < pres.length; i++) {
      var div = document.createElement('div');
      div.className = 'mermaid-rendered';
      div.textContent = pres[i].textContent;
      pres[i].parentNode.replaceChild(div, pres[i]);
    }
    if (document.querySelector('.mermaid-rendered')) {
      window.mermaid.run({ querySelector: '.mermaid-rendered' });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else {
    render();
  }
})();
