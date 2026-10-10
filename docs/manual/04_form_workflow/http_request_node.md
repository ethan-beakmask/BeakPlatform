---
title: HTTP 呼叫節點
audience: ORG_ADMIN
order: 35
nav_menu: form_workflow.workflows
requires:
  - manual/04_form_workflow/workflows
produces:
  - HTTP 回應流程變數
  - 外部 API 呼叫結果
covers:
  - modules/form_workflow/services/node_handlers/http_request_handler.py
  - modules/form_workflow/static/modules/form_workflow/js/wf-node-http-request.js
---

# HTTP 呼叫節點

「HTTP 呼叫」（`HttpRequest`）讓流程呼叫已被平台管理員允許的 HTTP 或 HTTPS API，
並把狀態碼、回應內容、回應標頭、JSON 解析結果寫進流程變數。常見用途是呼叫自家系統、
incoming webhook、工單系統建單，或把表單資料交給其他 REST API。

!!! abstract "作業：呼叫一個 REST API 並依結果分流"
    **MENU**：表單流程 ／ 流程設計

    1. 從左側「整合」分類拖出 [HTTP 呼叫]，接在 Start 之後
    2. URL 填固定網址或變數，例如 `${f.url}`；方法選 GET／POST／PUT／PATCH／DELETE
    3. 結果變數前綴填 `http`
    4. 後面接「分支」，條件判斷 `${v.http_ok}` 是否為 `True`

## 會寫出哪些變數

以下以前綴 `http` 為例：

| 變數 | 內容 |
|---|---|
| `http_result` | `ok`、`http_error`、`timeout`、`connection_error`、`not_allowed`、`config_error`、`exception` |
| `http_ok` | 只有 2xx 回應才是 `true` |
| `http_status` | HTTP 狀態碼，沒有收到回應時為空 |
| `http_body` | 回應文字，超過上限會截斷 |
| `http_json` | 勾選「解析為 JSON」、未截斷且可解析時的 JSON 值 |
| `http_headers` | 回應標頭，名稱會轉小寫；不含 `set-cookie` |
| `http_duration_ms` | 呼叫耗時 |
| `http_error` | 失敗原因 |
| `http_truncated` | 回應是否被截斷 |
| `http_url` | 變數替換後實際呼叫的 URL |

## 畫面上看不出來的規則

- **節點永遠回成功狀態**：HTTP 呼叫有副作用，平台不會因為 500、逾時或白名單拒絕而自動重試。真正結果請看 `http_result` 與 `http_ok`
- **不跟隨轉址**：3xx 會歸類成 `http_error`，`Location` 會留在 `http_headers.location`
- **目的地必須在白名單**：空白名單就是全部拒絕。若主機名稱解析到私有、loopback、link-local、保留或 multicast 位址，必須用 IP 或 CIDR 明確放行
- **本版沒有秘密儲存**：標頭值存在流程圖裡，能編輯流程的人都看得到。不要把長期金鑰放在 URL query string；需要金鑰時，優先讓 API 端限制來源 IP，或等平台的設定組功能
- **關閉 TLS 驗證會留警告紀錄**：只應用在內部測試或明確知道憑證風險的環境

## 常見問題

**填了 URL 但結果是 `not_allowed`。**
請平台管理員檢查 `http_request_allowed_hosts`，若有企業專屬限制也要檢查 `http_request_org_allowed_hosts`。本機或內網位址必須用 IP／CIDR 放行，不能只寫主機名。

**HTTP 302 為什麼不是成功？**
這顆節點不跟隨轉址，避免對方用 redirect 把流程帶到沒有白名單檢查過的目的地。

**JSON 回應沒有出現在 `http_json`。**
如果回應被截斷、內容不是合法 JSON，或「解析為 JSON」未勾選，`http_json` 會是空值；原始文字仍可從 `http_body` 查看。
