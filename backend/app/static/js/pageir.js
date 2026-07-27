(function () {
  function t(msg) {
    return window.__ ? window.__(msg) : msg;
  }

  function csrfToken() {
    var csrf = document.querySelector('meta[name="csrf-token"]');
    return csrf ? csrf.content : '';
  }

  async function run(button) {
    if (button.dataset.pirConfirm === 'true' && !confirm(t('確定執行此動作？'))) {
      return;
    }
    try {
      var res = await fetch(button.dataset.pirUrl, {
        method: button.dataset.pirMethod || 'POST',
        headers: { 'X-CSRFToken': csrfToken() }
      });
      if (!res.ok) {
        throw new Error(t('動作執行失敗'));
      }
      location.reload();
    } catch (err) {
      alert(err.message || t('動作執行失敗'));
    }
  }

  function formioLocale() {
    return (typeof BkI18n !== 'undefined' && BkI18n._locale) || 'zh-TW';
  }

  async function formioOptions(submitUrl) {
    var locale = formioLocale();
    var options = {
      language: locale,
      readOnly: !submitUrl
    };
    if (locale === 'zh-TW') {
      try {
        var res = await fetch((window.__BP || '') + '/static/vendor/formio-i18n-zh-TW.json');
        if (res.ok) {
          options.i18n = { 'zh-TW': await res.json() };
        }
      } catch (err) {
        console.warn('[PageIR] form.io i18n load failed:', err);
      }
    }
    return options;
  }

  async function initForm(el) {
    if (typeof Formio === 'undefined') {
      el.textContent = t('表單載入失敗');
      return;
    }
    var id = el.dataset.pirFormId;
    var schemaEl = document.querySelector('[data-pir-form-schema="' + id + '"]');
    if (!schemaEl) {
      el.textContent = t('表單設定不存在');
      return;
    }
    var schema;
    try {
      schema = JSON.parse(schemaEl.textContent || '{}');
    } catch (err) {
      el.textContent = t('表單設定格式錯誤');
      return;
    }
    var submitUrl = el.dataset.pirSubmitUrl || '';
    var form = await Formio.createForm(el, schema, await formioOptions(submitUrl));
    if (submitUrl) {
      form.on('submit', async function (submission) {
        try {
          var res = await fetch(submitUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken()
            },
            body: JSON.stringify((submission && submission.data) || {})
          });
          var data = {};
          try {
            data = await res.json();
          } catch (err) {
            data = {};
          }
          if (!res.ok || data.success === false) {
            throw new Error(data.error || t('送出失敗'));
          }
          alert(t('已送出'));
          location.reload();
        } catch (err) {
          alert(err.message || t('送出失敗'));
        }
      });
    }
  }

  function initForms() {
    document.querySelectorAll('[data-pir-form-id]').forEach(function (el) {
      initForm(el).catch(function (err) {
        console.error('[PageIR] form init failed:', err);
        el.textContent = t('表單載入失敗');
      });
    });
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-pir-url]');
    if (button) {
      run(button);
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initForms);
  } else {
    initForms();
  }
}());
