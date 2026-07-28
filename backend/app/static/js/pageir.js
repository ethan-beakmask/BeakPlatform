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

  function appendRows(wrap, rows) {
    var tbody = wrap.querySelector('tbody');
    if (!tbody) {
      return;
    }
    var empty = tbody.querySelector('tr .pir-empty');
    if (empty && empty.closest('tr')) {
      empty.closest('tr').remove();
    }
    var fields = Array.prototype.map.call(
      wrap.querySelectorAll('thead th[data-field]'),
      function (th) {
        return th.dataset.field;
      }
    );
    var hasActions = wrap.dataset.pirActions === 'true';
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      fields.forEach(function (field) {
        var td = document.createElement('td');
        var value = row && Object.prototype.hasOwnProperty.call(row, field) ? row[field] : '';
        td.textContent = value === null || value === undefined ? '' : String(value);
        tr.appendChild(td);
      });
      if (hasActions) {
        var actionCell = document.createElement('td');
        actionCell.className = 'pir-actions-cell';
        tr.appendChild(actionCell);
      }
      tbody.appendChild(tr);
    });
  }

  function initInfiniteTables() {
    if (!window.__PIR_ROWS_URL_BASE || typeof IntersectionObserver === 'undefined') {
      return;
    }
    document.querySelectorAll('[data-pir-table]').forEach(function (wrap) {
      var pagination = wrap.querySelector('.pir-pagination');
      if (pagination) {
        pagination.hidden = true;
      }

      var sentinel = document.createElement('div');
      sentinel.className = 'pir-scroll-sentinel';
      wrap.appendChild(sentinel);

      var loading = false;
      var stopped = false;
      var observer = new IntersectionObserver(function (entries) {
        var visible = entries.some(function (entry) {
          return entry.isIntersecting;
        });
        if (!visible || loading || stopped) {
          return;
        }

        var page = parseInt(wrap.dataset.pirPage || '1', 10) || 1;
        var pages = parseInt(wrap.dataset.pirPages || '1', 10) || 1;
        if (page >= pages) {
          sentinel.textContent = t('已載入全部');
          stopped = true;
          observer.unobserve(sentinel);
          return;
        }

        var next = page + 1;
        var widgetId = wrap.dataset.pirTable;
        var params = new URLSearchParams();
        params.set('page', String(next));
        if (wrap.dataset.pirSort) {
          params.set('sort', wrap.dataset.pirSort);
        }
        if (wrap.dataset.pirDir) {
          params.set('dir', wrap.dataset.pirDir);
        }

        loading = true;
        sentinel.textContent = t('載入中...');
        fetch(
          window.__PIR_ROWS_URL_BASE + '/' + encodeURIComponent(widgetId) + '/rows?' + params.toString(),
          { headers: { 'Accept': 'application/json' } }
        )
          .then(function (res) {
            if (!res.ok) {
              throw new Error(t('載入失敗'));
            }
            return res.json();
          })
          .then(function (data) {
            if (!data || data.success === false || !Array.isArray(data.rows)) {
              throw new Error(t('載入失敗'));
            }
            appendRows(wrap, data.rows);
            wrap.dataset.pirPage = String(data.page || next);
            wrap.dataset.pirPages = String(data.pages || pages);
            sentinel.textContent = data.has_more ? '' : t('已載入全部');
            if (!data.has_more) {
              stopped = true;
              observer.unobserve(sentinel);
            }
          })
          .catch(function (err) {
            stopped = true;
            sentinel.textContent = err.message || t('載入失敗');
            observer.unobserve(sentinel);
          })
          .finally(function () {
            loading = false;
          });
      });
      observer.observe(sentinel);
    });
  }

  function initPageIr() {
    initForms();
    initInfiniteTables();
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-pir-url]');
    if (button) {
      run(button);
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPageIr);
  } else {
    initPageIr();
  }
}());
