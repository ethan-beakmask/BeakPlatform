(function () {
  function t(msg) {
    return window.__ ? window.__(msg) : msg;
  }

  function csrfToken() {
    var csrf = document.querySelector('meta[name="csrf-token"]');
    return csrf ? csrf.content : '';
  }

  var crudErrorMessages = {
    invalid_data: '資料格式不正確',
    no_valid_data: '資料格式不正確',
    no_writable_fields: '沒有可寫入欄位',
    portal_db_missing: '資料庫不存在',
    write_failed: '寫入失敗',
    not_allowed: '沒有權限執行此操作',
    csrf_failed: '頁面已過期，請重新整理後再試',
    row_not_found: '找不到資料',
    invalid_row: '找不到資料',
    row_identifier_missing: '找不到資料',
    too_many_details: '明細筆數過多'
  };

  var tableCrudInitialized = false;

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

  async function formioOptions(readOnly) {
    var locale = formioLocale();
    var options = {
      language: locale,
      readOnly: readOnly
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
    var updateUrl = el.dataset.pirUpdateUrl || '';
    var mode = el.dataset.pirFormMode || (submitUrl ? 'new' : 'readonly');
    var record = null;
    var recordEl = document.querySelector('[data-pir-form-record="' + id + '"]');
    if (recordEl) {
      try {
        record = JSON.parse(recordEl.textContent || '{}');
      } catch (err) {
        el.textContent = t('表單設定格式錯誤');
        return;
      }
    }
    var form = await Formio.createForm(el, schema, await formioOptions(mode === 'readonly'));
    if (record !== null) {
      form.submission = { data: record };
    }
    if (mode === 'readonly') {
      return;
    }
    var requestUrl = mode === 'edit' ? updateUrl : submitUrl;
    var requestMethod = mode === 'edit' ? 'PUT' : 'POST';
    if (requestUrl) {
      form.on('submit', async function (submission) {
        try {
          var res = await fetch(requestUrl, {
            method: requestMethod,
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
          alert(mode === 'edit' ? t('已更新') : t('已送出'));
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
    var rowLinkTarget = wrap.dataset.pirRowLink || '';
    var canUpdate = wrap.dataset.pirCanUpdate === 'true';
    var canDelete = wrap.dataset.pirCanDelete === 'true';
    var widgetId = wrap.dataset.pirTable;
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
        // 捲動載入的列不經過 renderer，沒有後端算好的 _link，
        // 這裡自行組出與 _row_link_url() 同語意的網址（保留現有 query 參數）。
        if (rowLinkTarget && row && row._sc) {
          var link = document.createElement('a');
          link.className = 'pir-btn pir-btn-secondary';
          var url = new URL(window.location.href);
          url.searchParams.set(rowLinkTarget + '__sc', row._sc);
          link.href = url.pathname + url.search;
          link.textContent = t('開啟');
          actionCell.appendChild(link);
        }
        if (canUpdate) {
          actionCell.appendChild(crudButton('edit', widgetId, row && row._sc));
        }
        if (canDelete) {
          actionCell.appendChild(crudButton('delete', widgetId, row && row._sc));
        }
        tr.appendChild(actionCell);
      }
      tbody.appendChild(tr);
    });
  }

  function crudButton(action, widgetId, rowId) {
    var button = document.createElement('button');
    button.type = 'button';
    if (action === 'delete') {
      button.className = 'pir-btn pir-btn-danger';
      button.dataset.pirDelete = widgetId || '';
      button.textContent = t('刪除');
    } else {
      button.className = 'pir-btn pir-btn-secondary';
      button.dataset.pirEdit = widgetId || '';
      button.textContent = t('編輯');
    }
    button.dataset.pirRow = rowId === null || rowId === undefined ? '' : String(rowId);
    return button;
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

  function initTableCrud() {
    if (!window.__PIR_ROWS_URL_BASE || tableCrudInitialized) {
      return;
    }
    tableCrudInitialized = true;

    document.addEventListener('click', function (event) {
      var button = event.target.closest('[data-pir-create]');
      if (button) {
        openCrudModal('create', button.dataset.pirCreate, '', {});
        return;
      }

      button = event.target.closest('[data-pir-edit]');
      if (button) {
        var editWidgetId = button.dataset.pirEdit;
        var wrap = findTableWrap(editWidgetId);
        openCrudModal('update', editWidgetId, button.dataset.pirRow || '', wrap ? rowValuesFromDom(wrap, button) : {});
        return;
      }

      button = event.target.closest('[data-pir-delete]');
      if (button) {
        deleteRow(button.dataset.pirDelete, button.dataset.pirRow || '');
      }
    });
  }

  function findTableWrap(widgetId) {
    var wraps = document.querySelectorAll('[data-pir-table]');
    for (var i = 0; i < wraps.length; i += 1) {
      if (wraps[i].dataset.pirTable === widgetId) {
        return wraps[i];
      }
    }
    return null;
  }

  function formFields(widgetId) {
    var scripts = document.querySelectorAll('[data-pir-form-fields]');
    for (var i = 0; i < scripts.length; i += 1) {
      if (scripts[i].dataset.pirFormFields === widgetId) {
        try {
          var parsed = JSON.parse(scripts[i].textContent || '[]');
          return Array.isArray(parsed) ? parsed : [];
        } catch (err) {
          console.error('[PageIR] table form fields parse failed:', err);
          return [];
        }
      }
    }
    return [];
  }

  function rowValuesFromDom(wrap, button) {
    var values = {};
    var fields = Array.prototype.map.call(
      wrap.querySelectorAll('thead th[data-field]'),
      function (th) {
        return th.dataset.field;
      }
    );
    var tr = button.closest('tr');
    if (!tr) {
      return values;
    }
    fields.forEach(function (field, index) {
      var cell = tr.children[index];
      values[field] = cell ? cell.textContent.trim() : '';
    });
    return values;
  }

  function rowsUrl(widgetId, rowId) {
    var url = window.__PIR_ROWS_URL_BASE + '/' + encodeURIComponent(widgetId) + '/rows';
    if (rowId) {
      url += '/' + encodeURIComponent(rowId);
    }
    return url;
  }

  function showCrudError(el, code) {
    var key = typeof code === 'string' ? code : '';
    el.textContent = t(crudErrorMessages[key] || '操作失敗');
    el.classList.add('pir-modal-error-visible');
  }

  function closeModal(overlay) {
    overlay.classList.remove('pir-modal-open');
    overlay.remove();
  }

  function openCrudModal(mode, widgetId, rowId, initialValues) {
    var fields = formFields(widgetId);
    var overlay = document.createElement('div');
    overlay.className = 'pir-modal-overlay';

    var dialog = document.createElement('div');
    dialog.className = 'pir-modal-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');

    var title = document.createElement('h2');
    title.className = 'pir-modal-title';
    title.textContent = mode === 'create' ? t('新增') : t('編輯');
    dialog.appendChild(title);

    var error = document.createElement('div');
    error.className = 'pir-modal-error';
    dialog.appendChild(error);

    var form = document.createElement('form');
    form.className = 'pir-modal-form';
    fields.forEach(function (fieldDef) {
      var field = fieldDef && fieldDef.field ? String(fieldDef.field) : '';
      if (!field) {
        return;
      }

      var group = document.createElement('label');
      group.className = 'pir-modal-field';

      var label = document.createElement('span');
      label.textContent = fieldDef.label || field;
      group.appendChild(label);

      var input = document.createElement('input');
      input.type = 'text';
      input.name = field;
      var value = Object.prototype.hasOwnProperty.call(initialValues, field) ? initialValues[field] : '';
      input.value = value === null || value === undefined ? '' : String(value);
      group.appendChild(input);
      form.appendChild(group);
    });

    var actions = document.createElement('div');
    actions.className = 'pir-modal-actions';

    var save = document.createElement('button');
    save.type = 'submit';
    save.className = 'pir-btn pir-btn-primary';
    save.textContent = t('儲存');
    actions.appendChild(save);

    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'pir-btn pir-btn-secondary';
    cancel.textContent = t('取消');
    cancel.addEventListener('click', function () {
      closeModal(overlay);
    });
    actions.appendChild(cancel);
    form.appendChild(actions);

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      error.classList.remove('pir-modal-error-visible');
      error.textContent = '';

      var data = {};
      fields.forEach(function (fieldDef) {
        var field = fieldDef && fieldDef.field ? String(fieldDef.field) : '';
        var input = field ? form.elements[field] : null;
        if (input) {
          data[field] = input.value;
        }
      });

      fetch(rowsUrl(widgetId, mode === 'update' ? rowId : ''), {
        method: mode === 'create' ? 'POST' : 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken()
        },
        body: JSON.stringify({ data: data })
      })
        .then(function (res) {
          return res.json().catch(function () {
            return {};
          }).then(function (payload) {
            if (!res.ok || payload.success === false) {
              throw new Error(payload.error || 'operation_failed');
            }
            return payload;
          });
        })
        .then(function () {
          closeModal(overlay);
          location.reload();
        })
        .catch(function (err) {
          showCrudError(error, err && err.message);
        });
    });

    dialog.appendChild(form);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    overlay.classList.add('pir-modal-open');
  }

  function deleteRow(widgetId, rowId) {
    if (!rowId || !confirm(t('確定刪除這筆資料？'))) {
      return;
    }
    fetch(rowsUrl(widgetId, rowId), {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      }
    })
      .then(function (res) {
        return res.json().catch(function () {
          return {};
        }).then(function (payload) {
          if (!res.ok || payload.success === false) {
            throw new Error(payload.error || 'operation_failed');
          }
          return payload;
        });
      })
      .then(function () {
        location.reload();
      })
      .catch(function (err) {
        alert(t(crudErrorMessages[(err && err.message) || ''] || '操作失敗'));
      });
  }

  function masterDetailColumns(wrap) {
    var id = wrap.dataset.pirMasterDetail || '';
    var script = document.querySelector('[data-pir-md-columns="' + id + '"]');
    if (!script) {
      return [];
    }
    try {
      var parsed = JSON.parse(script.textContent || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      console.error('[PageIR] master-detail columns parse failed:', err);
      return [];
    }
  }

  function updateMasterDetailCount(wrap) {
    var count = wrap.querySelectorAll('[data-pir-md-row]').length;
    var target = wrap.querySelector('[data-pir-md-count-current]');
    if (target) {
      target.textContent = String(count);
    }
    var empty = wrap.querySelector('[data-pir-md-empty]');
    if (empty) {
      empty.hidden = count > 0;
    }
  }

  function addMasterDetailRow(wrap) {
    var columns = masterDetailColumns(wrap);
    var tbody = wrap.querySelector('[data-pir-md-current-body]');
    if (!tbody || !columns.length) {
      return;
    }
    var tr = document.createElement('tr');
    tr.dataset.pirMdRow = 'true';
    columns.forEach(function (column) {
      var td = document.createElement('td');
      var input = document.createElement('input');
      input.type = 'text';
      input.name = column.field || '';
      input.dataset.pirMdDetailField = column.field || '';
      td.appendChild(input);
      tr.appendChild(td);
    });
    var actionCell = document.createElement('td');
    actionCell.className = 'pir-actions-cell';
    var remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'pir-btn pir-btn-secondary';
    remove.dataset.pirMdRemove = 'true';
    remove.textContent = t('移除');
    actionCell.appendChild(remove);
    tr.appendChild(actionCell);
    tbody.appendChild(tr);
    updateMasterDetailCount(wrap);
  }

  function collectMasterDetailPayload(wrap) {
    var master = {};
    wrap.querySelectorAll('[data-pir-md-master-field]').forEach(function (input) {
      master[input.dataset.pirMdMasterField] = input.value;
    });
    var details = [];
    wrap.querySelectorAll('[data-pir-md-row]').forEach(function (row) {
      var item = {};
      row.querySelectorAll('[data-pir-md-detail-field]').forEach(function (input) {
        item[input.dataset.pirMdDetailField] = input.value;
      });
      details.push(item);
    });
    return {
      master: {
        sc: wrap.dataset.pirMasterSc || null,
        data: master
      },
      details: details
    };
  }

  function submitMasterDetail(wrap, button) {
    var submitUrl = wrap.dataset.pirSubmitUrl || '';
    if (!submitUrl) {
      return;
    }
    button.disabled = true;
    fetch(submitUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken()
      },
      body: JSON.stringify(collectMasterDetailPayload(wrap))
    })
      .then(function (res) {
        return res.json().catch(function () {
          return {};
        }).then(function (payload) {
          if (!res.ok || payload.success === false) {
            throw new Error(payload.error || 'operation_failed');
          }
          return payload;
        });
      })
      .then(function () {
        alert(t('已送出'));
        location.reload();
      })
      .catch(function (err) {
        alert(t(crudErrorMessages[(err && err.message) || ''] || '送出失敗'));
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  function initMasterDetails() {
    document.querySelectorAll('[data-pir-master-detail]').forEach(function (wrap) {
      updateMasterDetailCount(wrap);
    });
  }

  function initPageIr() {
    initForms();
    initInfiniteTables();
    initTableCrud();
    initMasterDetails();
  }

  document.addEventListener('click', function (event) {
    var tab = event.target.closest('[data-pir-md-tab]');
    if (tab) {
      var tabWrap = tab.closest('[data-pir-master-detail]');
      if (tabWrap) {
        tabWrap.querySelectorAll('[data-pir-md-tab]').forEach(function (item) {
          item.classList.toggle('pir-md-tab-active', item === tab);
        });
        tabWrap.querySelectorAll('[data-pir-md-panel]').forEach(function (panel) {
          panel.classList.toggle('pir-md-panel-active', panel.dataset.pirMdPanel === tab.dataset.pirMdTab);
        });
      }
      return;
    }

    var add = event.target.closest('[data-pir-md-add]');
    if (add) {
      var addWrap = add.closest('[data-pir-master-detail]');
      if (addWrap) {
        addMasterDetailRow(addWrap);
      }
      return;
    }

    var remove = event.target.closest('[data-pir-md-remove]');
    if (remove) {
      var removeWrap = remove.closest('[data-pir-master-detail]');
      var row = remove.closest('[data-pir-md-row]');
      if (row) {
        row.remove();
      }
      if (removeWrap) {
        updateMasterDetailCount(removeWrap);
      }
      return;
    }

    var submit = event.target.closest('[data-pir-md-submit]');
    if (submit) {
      var submitWrap = submit.closest('[data-pir-master-detail]');
      if (submitWrap) {
        submitMasterDetail(submitWrap, submit);
      }
      return;
    }

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
