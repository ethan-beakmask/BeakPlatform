/**
 * FormIO 自訂 Storage Provider: bkfile
 *
 * 將 FormIO file component 的上傳/下載導向 BeakPlatform file_service，
 * 取代預設的 base64 內嵌行為。
 *
 * 上傳: POST /api/files/upload (context_type=form_attachment)
 * 下載: POST /api/files/<sc>/download-token → GET /api/files/dl/<token>
 * 刪除: DELETE /api/files/<sc>
 *
 * form_data 只存 { storage, name, url(=secure_code), size, type, originalName }
 * 不再將整個檔案 base64 塞進 JSON。
 *
 * 依賴: formio.full.min.js（必須在本檔之前載入）
 */
(function () {
    'use strict';

    if (typeof Formio === 'undefined') {
        console.error('[bkfile] Formio 尚未載入，provider 註冊失敗');
        return;
    }

    /**
     * Provider factory（FormIO 規定 signature）
     */
    function bkfileProvider(formio) {
        return {
            title: 'BeakPlatform File',
            name: 'bkfile',

            /**
             * 上傳檔案到 file_service
             */
            uploadFile(file, fileName, dir, progressCallback, url, options,
                       fileKey, groupPermissions, groupId, abortCallback) {

                const fd = new FormData();
                fd.append('file', file);
                fd.append('context_type', 'form_attachment');

                return new Promise(function (resolve, reject) {
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', window.__BP + '/api/files/upload');

                    // 進度回報
                    if (typeof progressCallback === 'function') {
                        xhr.upload.addEventListener('progress', function (e) {
                            if (e.lengthComputable) {
                                progressCallback(e.loaded / e.total * 100);
                            }
                        });
                    }

                    // 支援中斷
                    if (typeof abortCallback === 'function') {
                        abortCallback(function () { xhr.abort(); });
                    }

                    xhr.onload = function () {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            var result;
                            try {
                                result = JSON.parse(xhr.responseText);
                            } catch (e) {
                                return reject(new Error('回應格式錯誤'));
                            }
                            if (!result.success) {
                                return reject(new Error(result.message || '上傳失敗'));
                            }
                            // FormIO 存入 submission.data 的檔案物件
                            resolve({
                                storage: 'bkfile',
                                name: fileName,
                                originalName: file.name,
                                url: result.data.secure_code,
                                size: file.size,
                                type: file.type
                            });
                        } else {
                            var msg = '上傳失敗 (' + xhr.status + ')';
                            try {
                                var err = JSON.parse(xhr.responseText);
                                if (err.message) msg = err.message;
                            } catch (e) { /* ignore */ }
                            reject(new Error(msg));
                        }
                    };

                    xhr.onerror = function () {
                        reject(new Error('網路錯誤，無法上傳'));
                    };

                    xhr.onabort = function () {
                        reject(new Error('上傳已取消'));
                    };

                    xhr.send(fd);
                });
            },

            /**
             * 下載檔案（透過一次性 token）
             */
            downloadFile(file) {
                if (!file || !file.url) {
                    return Promise.reject(new Error('無效的檔案參考'));
                }

                // file.url 是 secure_code
                return fetch(window.__BP + '/api/files/' + file.url + '/download-token', {
                    method: 'POST'
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (!data.success) {
                        throw new Error(data.message || '無法取得下載連結');
                    }
                    // 開啟下載（一次性 token URL）
                    window.open(data.url, '_blank');
                    // FormIO 期望回傳 file 物件
                    return file;
                });
            },

            /**
             * 刪除檔案
             */
            deleteFile(file) {
                if (!file || !file.url) {
                    return Promise.resolve();
                }

                return fetch(window.__BP + '/api/files/' + file.url, {
                    method: 'DELETE'
                })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (!data.success) {
                        console.warn('[bkfile] 刪除失敗:', data.message);
                    }
                });
            }
        };
    }

    // 註冊 provider
    Formio.Providers.addProvider('storage', 'bkfile', bkfileProvider);

    /**
     * 自動補丁：遍歷 schema 中所有 file component，
     * 將缺少 storage 或 storage='base64' 的補為 'bkfile'。
     *
     * 用法：在 Formio.createForm / Formio.builder 之前呼叫
     *   BkFileProvider.patchSchema(schema)
     */
    function patchFileStorage(components) {
        if (!Array.isArray(components)) return;
        for (var i = 0; i < components.length; i++) {
            var c = components[i];
            if (!c) continue;
            if (c.type === 'file' && (!c.storage || c.storage === 'base64')) {
                c.storage = 'bkfile';
            }
            // 遞迴子元件
            if (c.components) patchFileStorage(c.components);
            if (c.columns) {
                for (var j = 0; j < c.columns.length; j++) {
                    if (c.columns[j] && c.columns[j].components) {
                        patchFileStorage(c.columns[j].components);
                    }
                }
            }
            if (c.rows) {
                for (var j = 0; j < c.rows.length; j++) {
                    var row = c.rows[j];
                    if (Array.isArray(row)) {
                        for (var k = 0; k < row.length; k++) {
                            if (row[k] && row[k].components) {
                                patchFileStorage(row[k].components);
                            }
                        }
                    }
                }
            }
            if (c.tabs) {
                for (var j = 0; j < c.tabs.length; j++) {
                    if (c.tabs[j] && c.tabs[j].components) {
                        patchFileStorage(c.tabs[j].components);
                    }
                }
            }
        }
    }

    // 公開 API
    window.BkFileProvider = {
        patchSchema: function (schema) {
            if (schema && schema.components) {
                patchFileStorage(schema.components);
            }
            return schema;
        }
    };

})();
