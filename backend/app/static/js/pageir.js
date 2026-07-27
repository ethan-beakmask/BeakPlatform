(function () {
  function t(msg) {
    return window.__ ? window.__(msg) : msg;
  }

  async function run(button) {
    if (button.dataset.pirConfirm === 'true' && !confirm(t('確定執行此動作？'))) {
      return;
    }
    var csrf = document.querySelector('meta[name="csrf-token"]');
    try {
      var res = await fetch(button.dataset.pirUrl, {
        method: button.dataset.pirMethod || 'POST',
        headers: { 'X-CSRFToken': csrf ? csrf.content : '' }
      });
      if (!res.ok) {
        throw new Error(t('動作執行失敗'));
      }
      location.reload();
    } catch (err) {
      alert(err.message || t('動作執行失敗'));
    }
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-pir-url]');
    if (button) {
      run(button);
    }
  });
}());
