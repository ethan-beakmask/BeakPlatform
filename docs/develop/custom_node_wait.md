# 自己開發一個流程節點（二）：會等待的節點，以及給外部系統打回來的端點

這是《[自己開發一個流程節點](custom_node.md)》的第二篇。第一篇的 `HttpRequest` 送出去就完事，
對同步 API 夠用；對**非同步**的對手（工單要人處理、外部批次要跑幾小時、對方「收到了、稍後通知你」）
它只知道「對方收到了」，不知道結果。這一篇補上另一半：**等待外部回呼節點（`ExternalWait`）**，
兩個節點合起來才是完整的 webhook 往返：

```
HttpRequest（把回呼網址一起送出） → ExternalWait（停住，等對方打回來） → Branch（依回呼內容分路）
```

這一篇新增的知識有三塊，都是第一篇沒碰到的：節點怎麼「等」而不會卡死、一個讓外部系統不登入就能呼叫的端點該長什麼樣、
以及怎麼替變數系統加一個新前綴。讀之前請先讀完第一篇，這裡不重複第一篇的 13 層。

---

## 一、會等待的節點：引擎只會喚醒它認得的東西

處理器回 `{'status': 'waiting'}` 時，佇列項目進入 `WAITING`，之後**不會有任何東西自動再碰它**，
除非符合執行器輪詢條件之一（`modules/form_workflow/services/workflow_executor.py`）：

| 條件 | 寫法 | 適用 |
|---|---|---|
| A. 時間到 | 節點型別在 `node_type.in_([...])` 名單內，且 `scheduled_at <= now` | `Delay`、`ParallelJoin`、`OsExecutor` 排隊 |
| B. 結果 JSON 裡的期限到 | `result.data.timeout_at <= now`（`formadapter_timeout_due_clause`） | `FormAdapter` 的簽核逾時 |
| C. 外部事件 | 某支 API 直接把佇列項目往下推 | `FormAdapter` 由簽核 API 推進 |

**名單在執行器裡出現兩次**（主輪詢與備援輪詢），加型別時兩處都要加，漏一處的症狀是「偶爾卡住」。
不在任何條件內的 `WAITING` 節點就是死的：流程停住、不報錯、流程管理頁一片正常。

`ExternalWait` 用的是最單純的組合：**條件 A 加一個「推一下」的 API**。

- 進入等待時把 `scheduled_at` 設成逾時時刻；沒設逾時就放一個遠期哨兵值（`9999-12-31`），因為這個欄位是 `NOT NULL`，而遠期時間永遠不會被執行器當成到期
- 回呼端點收到合法回呼時，先把內容寫進流程變數，再把 `scheduled_at` 改成現在
- 執行器下一輪就會把它當成「時間到」撿起來、改回 `PENDING`、重跑處理器；處理器看到變數裡已有回呼內容就完成

這樣只需要在兩份名單各加一個字串，不必新增查詢條款；而且執行器恢復 `WAITING` 節點時會保留原本的 `started_at`，
「等了多久」算得出來。為什麼不照 `FormAdapter` 那樣另寫一條條款？因為 `FormAdapter` 的 `scheduled_at` 被表單中心拿去當「送件時間」顯示，
動它會讓清單顯示錯，`ExternalWait` 沒有這個包袱。

### 重跑時處理器看到的是什麼

處理器每次被喚醒都是**從頭執行一次 `handle()`**，沒有「上次跑到哪」的記憶，只有兩樣東西留著：
`queue_item.result`（上一次回傳的整個 dict，含 `data`）與流程變數。所以：

- 第一次進入時決定的東西（逾時時刻、回呼網址）要放進 `result.data`，下一次從 `self.queue_item.result['data']` 讀回來，**而且回傳 `waiting` 時要再放一次**，因為每次回傳都會整個覆蓋
- 「回呼有沒有來」看流程變數，不看 `result`

### 回呼比節點更早到怎麼辦

對方處理太快、或流程在 `HttpRequest` 與 `ExternalWait` 之間還夾了別的節點，回呼可能在 `ExternalWait` 尚未進入 `WAITING`（甚至尚未建立佇列項目）時就到了。
不處理這個 race，症狀是「偶爾卡死、不報錯」，很難重現。

解法是**端點永遠先寫變數**，不管節點到了沒；處理器**進入時永遠先查變數**，有就直接完成、不等。這樣早到、準時、晚到三種時序走的是同一條路。

還有一個更窄的窗口：回呼剛好在處理器「讀完變數（沒有）」與「寫完 `scheduled_at`、回傳 `waiting`」之間到達。此時佇列項目是 `RUNNING`，端點若只在 `WAITING` 時才推 `scheduled_at`，這一則回呼就會被埋到逾時。兩邊各讓一步就能關掉它：端點對 `WAITING`／`RUNNING`／`PENDING` 都把 `scheduled_at` 推到現在；處理器在 commit 自己的 `scheduled_at` **之後再查一次變數**，有就直接走收到的路。後者保證端點寫在前面的會被看到，前者保證寫在後面的不會被處理器的 commit 蓋掉（執行器寫回 `WAITING` 前會 `refresh`，拿到的是端點改過的值）。

### 一次性

同一個等待只接受一次回呼。端點判斷：節點已結束（`SUCCESS`／`FAILED`／`CANCELLED`）、或變數裡已有尚未消化或已消化的回呼，一律回 `409`。

---

## 二、不登入就能呼叫的端點

外部系統打回來時沒有登入身分，端點要靠**網址裡的簽章**驗證。平台的規則：

| 項目 | 做法 |
|---|---|
| 免登入 | 路由函式掛 `@public_route`（`app.security.decorators`），否則全域攔截器直接回 401 |
| CSRF | `@csrf.exempt`（`from app import csrf`），機器端點沒有 CSRF token |
| 節流 | **必須**掛 `@limiter.limit(...)`（`from app import limiter`），匿名端點沒有帳號可鎖，節流是唯一手段；平台的 `limiter` 預設已用 `client_ip_key` 分桶，不要另外傳 `get_remote_address` |
| 來源 IP | 稽核一律 `get_client_ip()`（`app.security.client_ip`），不要讀 `request.remote_addr` |
| 守門宣告表 | 新增路由後跑 `venv/bin/python scripts/route_guard_inventory.py --update`，否則 `test_route_guard_table.py` 會紅 |
| 錯誤回應 | 簽章錯、流程不存在、節點不存在一律回**同一個 404**，不要讓對方分辨哪一段猜對了 |
| 輸入上限 | 大小上限（讀 `request.get_data()` 前先看 `Content-Length`，超過回 413）、JSON 深度上限、非 JSON 回 400 |

### 簽章怎麼做才不用多一張表

回呼網址在 `HttpRequest` 送出時就要存在，但那時 `ExternalWait` 還沒跑，沒有機會「發一個 token 存起來」。
所以 token 不存 DB，用**可重算的 HMAC**：

```
token = HMAC-SHA256( key = HMAC-SHA256(SECRET_KEY, "external-wait-callback-v1"),
                     msg = "<流程實例 secure_code>|<ExternalWait 節點 id>" ) 取前 32 個十六進位字元
回呼網址 = <系統對外網址><應用前綴>/api/external-wait/callback/<實例 sc>/<節點 id>/<token>
```

端點拿路徑裡的三段重算一次、`hmac.compare_digest` 比對。流程實例 secure_code 本身不可猜，再加簽章，
拿到網址的只有收到那一則 `HttpRequest` 的對方。簽章綁定實例與節點，所以同一流程裡兩個 `ExternalWait` 的網址互不相通。

**系統對外網址**來自主機設定的「系統對外網址」（`system_base_url`），**應用前綴**來自環境變數 `APP_PREFIX`（預設 `/beakplatform`）。
處理器跑在沒有 HTTP request 的子行程裡，`request.script_root` 拿不到，**不能**用 `url_for(_external=True)`，要自己接前綴；
沒設定系統對外網址時回呼網址解析成空字串並記 WARNING，文件要告訴管理員先去設。

---

## 三、替變數系統加一個前綴

`HttpRequest` 的 body 要能寫 `${cb.node-Wait}` 拿到下游那顆 `ExternalWait` 的回呼網址。變數替換的唯一實作是
`node_handlers/base.py` 的 `replace_variables()`，前綴以 `if var_expr.startswith('xx.')` 逐一派送。加一個前綴就是在那裡加一個分支，
呼叫自己的 `_resolve_cb(node_id)`，裡面用上一節的規則組網址。

兩個要點：

- 分支放在 `t.` 之後、舊語法 fallback 之前；`node_id` 要過白名單正則（`^[A-Za-z0-9_-]{1,100}$`），不合法回空字串
- 組網址的邏輯放在獨立的 service 模組（處理器、端點、變數解析三處共用），`base.py` 只做轉呼叫。**簽章的實作只能有一份**，否則端點與產生端各算各的，某天其中一邊改了就全部對不上

---

## 四、範例規格：等待外部回呼節點（`ExternalWait`）

### 4.1 定位

| 欄位 | 值 |
|---|---|
| `node_type` | `ExternalWait` |
| `display_name` | `等待外部回呼` |
| `category` | `整合` |
| `icon` | `/static/modules/form_workflow/icons/workflow/externalwait.svg` |
| `execution_handler` | `modules.form_workflow.services.node_handlers.external_wait_handler.ExternalWaitHandler` |
| `canvas_color` | `#F59E0B` |
| `org_restricted` | `FALSE` |
| 入／出線上限 | `-1`／`-1` |

### 4.2 共用 service：`modules/form_workflow/services/external_wait_service.py`

| 函式 | 行為 |
|---|---|
| `callback_token(instance_code, node_id) -> str` | 上一節的 HMAC；key 從 `current_app.config['SECRET_KEY']` 派生 |
| `verify_token(instance_code, node_id, token) -> bool` | `hmac.compare_digest` |
| `build_callback_url(instance_code, node_id) -> str \| None` | `system_base_url` 未設回 `None`；否則 `base + APP_PREFIX + /api/external-wait/callback/...` |
| `payload_var_name(node_id)`／`meta_var_name(node_id)` | 內部變數名 `_extwait_<node_id>_payload`／`_extwait_<node_id>_meta`（FLOW scope） |
| `json_depth(obj) -> int` | 巢狀深度 |
| `receive_callback(instance_code, node_id, token, raw_body: bytes, source_ip) -> (http_status, dict)` | 端點的全部邏輯（見 4.4），端點本身只做參數格式檢查與呼叫 |

常數：`MAX_PAYLOAD_BYTES = 65536`、`MAX_JSON_DEPTH = 10`、`TOKEN_RE = ^[0-9a-f]{32}$`、`NODE_ID_RE = ^[A-Za-z0-9_-]{1,100}$`、`INSTANCE_CODE_RE = ^[A-Za-z0-9_-]{16,40}$`。

### 4.3 節點設定

| key | 型別 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `result_var` | string | 是 | | 結果變數前綴，`^[A-Za-z_][A-Za-z0-9_]*$` |
| `timeout_enabled` | bool | | `false` | |
| `timeout_minutes` | int | 啟用時必填 | | 1～14400 |

`validate()`：`result_var` 不合法、或啟用逾時但分鐘數不在範圍 → `ValueError`。
刻意**沒有逾時出線**：結果用變數表達，下游接「分支」依 `<前綴>_result` 分路，與 `HttpRequest` 一致，處理器也不必讀 graph。

### 4.4 端點行為：`POST /api/external-wait/callback/<instance_code>/<node_id>/<token>`

Blueprint `external_wait_bp`（`url_prefix='/api/external-wait'`，檔案 `modules/form_workflow/api/external_wait.py`，登進 `api/__init__.py` 的 `additional_blueprints`）。
裝飾器：`@public_route`、`@csrf.exempt`、`@limiter.limit('60 per minute; 600 per hour')`。
三個路徑參數先過正則，不合格直接 404。`receive_callback()` 依序：

| 步驟 | 回應 |
|---|---|
| 流程實例不存在，或 token 驗證失敗 | `404 {"error": "not_found"}`（兩者同一回應） |
| 實例狀態不是 `RUNNING` | `409 {"error": "workflow_not_running"}` |
| 佇列中該 `node_id`、型別 `ExternalWait` 的最新一筆已是 `SUCCESS`／`FAILED`／`CANCELLED` | `409 {"error": "already_completed"}` |
| `meta` 變數已存在（不論是否消化） | `409 {"error": "already_received"}` |
| `Content-Length` 或實際長度 > 64 KiB | `413 {"error": "payload_too_large"}` |
| body 非空但不是 JSON | `400 {"error": "invalid_json"}`；空 body 視為 `{}` |
| JSON 深度 > 10 | `400 {"error": "payload_too_deep"}` |
| 通過 | 以實例的 `org_secure_code` 寫兩個 FLOW 變數：`payload`（原 JSON）、`meta`＝`{"received_at": <UTC ISO>, "source_ip": ..., "consumed": false}`；佇列項目若是 `WAITING`／`RUNNING`／`PENDING` 就把 `scheduled_at` 設為現在並回 `202 {"accepted": true, "state": "woken"}`，佇列項目尚不存在則 `202 {"accepted": true, "state": "buffered"}`；若佇列項目存在，另以 `WorkflowLogService` 記一筆 INFO「收到外部回呼」含來源 IP |

錯誤碼是機器讀的，**不要包翻譯函式**。

### 4.5 處理器

`handle()`：

1. `report_running()`；讀 `existing = (queue_item.result or {}).get('data') or {}`
2. 讀 `meta`／`payload` 變數。**有 `meta` 且 `consumed` 為假** → 寫結果變數（下表）、把 `meta.consumed` 改 `true` 寫回、回 `success`
3. 沒有回呼：
   - `existing` 沒有 `timeout_at` ＝ 第一次進入：若啟用逾時，`timeout_at = utcnow + minutes`，`queue_item.scheduled_at = timeout_at`；否則 `scheduled_at = NO_TIMEOUT_SENTINEL`（`9999-12-31`）。commit 之後**再查一次 `meta`**，有就走第 2 步的收到路徑（race 關閉，見第一節）。`callback_url = build_callback_url(...)`（`None` 時記 WARNING）。回 `waiting`，`data` 帶 `timeout_at`、`callback_url`、`waiting_since`
   - `existing` 有 `timeout_at` 且 `now >= timeout_at` → 結果變數 `_result='timeout'`，回 `success`
   - `existing` 有 `timeout_at` 但未到（被喚醒卻沒有回呼，理論上不會發生）→ 重設 `scheduled_at = timeout_at`，回 `waiting` 並原樣帶回 `existing`

結果變數（前綴 `result_var`）：

| 後綴 | 內容 |
|---|---|
| `_result` | `received`／`timeout` |
| `_payload` | 回呼 JSON（逾時為 `null`） |
| `_received_at` | UTC ISO 字串或 `null` |
| `_source_ip` | 回呼來源 IP 或 `null` |
| `_callback_url` | 本節點的回呼網址 |
| `_waited_seconds` | 從 `waiting_since` 到完成的秒數 |

### 4.6 執行器

`workflow_executor.py` 兩處 `node_type.in_(['Delay', 'End', 'ParallelJoin', 'OsExecutor'])` 都加上 `'ExternalWait'`，旁邊的註解與 log 字串同步。**不改其他邏輯。**

### 4.7 變數前綴 `cb.`

`base.py::replace_variables` 加 `cb.` 分支 → `_resolve_cb(node_id)`：驗 `NODE_ID_RE`、取 `self._get_workflow_instance_code()`、呼叫 `build_callback_url`；`None` 或不合法回 `''` 並 `logger.warning`。

### 4.8 設計器面板

欄位：結果變數前綴、「啟用逾時」勾選、逾時分鐘數（勾選才顯示）。面板上方以唯讀方式顯示**本節點的 id** 與可直接複製的字串 `${cb.<節點 id>}`，
說明文字：「把這個字串放進上游 HTTP 呼叫的內容，對方就拿得到回呼網址；需要先在主機設定填系統對外網址」。
接線點與第一篇相同（`wf-render.js`、`wf-accordion.js` 三處、`wf-save.js`、新檔 `wf-node-external-wait.js`、模板 script）。

### 4.9 示範

- `scripts/examples/http_mock_server.py` 加 `POST /callback-later`：body `{"callback_url": "...", "payload": {...}, "delay_seconds": N}`，
  立刻回 `202`，背景執行緒等 N 秒（上限 300，逾時場景要能超過節點的 2 分鐘）後把 `payload` 以 JSON `POST` 到 `callback_url`，並把對方回的狀態碼印到 stdout
- `scripts/examples/provision_nodedemo_externalwait.py --org <企業代碼> --apply`：表單欄位 `mock_url`、`delay_seconds`、結果欄；流程
  Start → HttpRequest（`POST ${f.mock_url}/callback-later`，JSON 內容 `{"callback_url": "${cb.node-Wait}", "payload": {"ticket": "${fi.serial}", "status": "closed"}, "delay_seconds": ${f.delay_seconds}}`，前綴 `http`）
  → ExternalWait（節點 id 固定 `node-Wait`，前綴 `cb`，逾時 2 分鐘）→ Branch（`${v.cb_result}` 是否為 `received`）→ 兩個 OpFieldWrite 把 `${v.cb_payload}` 或「逾時」寫回結果欄 → End
- 端對端：mock 在白名單內 → 送單填 mock 位址與 `delay_seconds=5` → 約 10 秒後結果欄出現 `{"ticket": ..., "status": "closed"}`，變數 `cb_result=received`、`cb_waited_seconds` 約 5～10；
  再對同一個回呼網址多打一次 → `409 already_received`；改一個字元的 token → `404`；送單填 `delay_seconds=150`（超過 2 分鐘逾時）→ `cb_result=timeout`

### 4.10 測試清單

- token：同輸入同輸出、改任一段就不同、`verify_token` 對錯 token 回 False
- `build_callback_url`：未設系統對外網址回 `None`；設了則含 `APP_PREFIX` 與三段路徑
- `json_depth`、大小上限、非 JSON、空 body 視為 `{}`
- `receive_callback`（用 `app` fixture 建實例與佇列列）：404 兩種情境同一回應；非 RUNNING 409；已完成 409；重複 409；`WAITING` 與 `RUNNING` → `woken` 且 `scheduled_at` 被改；尚未建佇列列 → `buffered` 且變數已寫
- 處理器：第一次進入回 `waiting`、`scheduled_at == timeout_at`、`data` 帶三個 key；變數已有回呼 → `success` 且六個結果變數正確、`meta.consumed` 變真；`timeout_at` 已到 → `timeout`；不啟用逾時時 `scheduled_at` 是遠期哨兵值
- `replace_variables('${cb.node-Wait}')` 在假的 handler 上解析出正確網址；不合法 node id 回空字串
- API：`client` fixture 不登入 `POST` 合法 token → 202；錯 token → 404；確認不被 CSRF 擋（回應不是 400）

---

## 五、交付前的檢查清單

- [ ] 第一篇的 13 層都有，加上本篇新增的：執行器兩份名單、`base.py` 前綴、service、API blueprint 與註冊、守門宣告表 `--update`
- [ ] `bash scripts/run_tests.sh tests/test_external_wait_node.py tests/test_route_guard_table.py -q` 全綠
- [ ] 設計器拖出節點、面板顯示 `${cb.<id>}`、存檔重載值還在
- [ ] 示範流程三種時序都跑過：準時回呼、重複回呼 409、逾時
- [ ] 文件：手冊頁寫清楚「要先設系統對外網址」與「回呼網址等同一次性密碼，不要寫進 log 或聊天工具」
