---
title: 等待外部回呼節點
audience: ORG_ADMIN
order: 36
nav_menu: form_workflow.workflows
requires:
  - manual/04_form_workflow/workflows
  - manual/04_form_workflow/http_request_node
produces:
  - 外部回呼流程變數
  - 一次性回呼網址
covers:
  - modules/form_workflow/services/node_handlers/external_wait_handler.py
  - modules/form_workflow/services/external_wait_service.py
  - modules/form_workflow/static/modules/form_workflow/js/wf-node-external-wait.js
---

# 等待外部回呼節點

「等待外部回呼」（`ExternalWait`）讓流程停在某個節點，等外部系統用簽章網址打回來後再繼續。
常見搭配是先用「HTTP 呼叫」把 `${cb.<等待節點 ID>}` 送給對方，再由本節點接收結果。

!!! abstract "作業：送出非同步請求並等待回呼"
    **MENU**：表單流程 ／ 流程設計

    1. 從左側「整合」分類拖出 [HTTP 呼叫] 與 [等待外部回呼]
    2. 在等待節點設定「結果變數前綴」，例如 `cb`
    3. 將等待節點面板上的 `${cb.<節點 ID>}` 放進上游 HTTP 呼叫的 JSON 內容
    4. 後面接「分支」，依 `${v.cb_result}` 是否為 `received` 分流

## 會寫出哪些變數

以下以前綴 `cb` 為例：

| 變數 | 內容 |
|---|---|
| `cb_result` | `received` 或 `timeout` |
| `cb_payload` | 外部系統 POST 的 JSON；逾時時為空 |
| `cb_received_at` | 收到回呼的 UTC 時間；逾時時為空 |
| `cb_source_ip` | 回呼來源 IP；逾時時為空 |
| `cb_callback_url` | 本次等待使用的回呼網址 |
| `cb_waited_seconds` | 從開始等待到完成的秒數 |

## 設定欄位

| 欄位 | 說明 |
|---|---|
| 結果變數前綴 | 必填，只能用英文字母、數字與底線，且不能以數字開頭 |
| 啟用逾時 | 勾選後，時間到仍未收到回呼時會完成節點並寫入 `timeout` |
| 逾時分鐘數 | 1 到 14400 分鐘 |

## 畫面上看不出來的規則

- **要先設定系統對外網址**：回呼網址由主機設定 `system_base_url` 加上應用前綴組成。未設定時 `${cb.<id>}` 會解析成空字串
- **回呼網址等同一次性密碼**：拿到網址的人就能完成該次等待。不要把完整 URL 寫進聊天工具、公開 issue 或不必要的 log
- **同一個等待只接受一次回呼**：第二次打同一個 URL 會得到 `409 already_received`
- **逾時後的回呼不會改結果**：節點已完成後再打回來會得到 `409 already_completed`
- **外部系統必須送 JSON**：空 body 會視為 `{}`；非 JSON 或巢狀太深會被拒絕

## 範例 JSON

上游「HTTP 呼叫」可以送出：

```json
{
  "callback_url": "${cb.node-Wait}",
  "payload": {
    "ticket": "${fi.serial}",
    "status": "closed"
  },
  "delay_seconds": 5
}
```

外部系統處理完成後，對 `callback_url` POST：

```json
{
  "status": "closed",
  "comment": "done"
}
```

後續分支可用 `${v.cb_result}` 判斷是否收到，用 `${v.cb_payload}` 寫回表單欄位。
