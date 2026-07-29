# 交接：NoCode 三個未完成元件（form / detail / actions）

> 建立日期：2026-07-29
> 前置交接檔：`docs/handoff_nocode_n1_n5.md`（N1~N5 的判定鏈、檔案地圖、十個踩坑）
> 本檔接續其 §6，處理「六個元件」中尚未完成的三個。

---

## 0. 開發順序（用戶已裁決，不要自行調整）

```
① form  →  ② detail 就地編輯  →  ③ actions
```

**actions 排在最後是刻意的**：actions 的規格會被前兩者倒推出來。
用戶原話：「『送出或確認』的行為應該可當 actions 的場景」——
在 form 與 detail 的送出流程定案前，actions 的介面設計沒有依據，
提早做會做出用不上的抽象。

現況：`register_action()` 在 `backend/app/pageir/registry.py:91` 存在，
但平台側**零註冊**，設計器的動作選單是空的，`row_actions_ref` 連帶不可用。

---

## 1. 六個元件的完成度（2026-07-29 現況）

| 元件 | 狀態 | 說明 |
|---|---|---|
| layout | 完成 | 欄數 / 間距 |
| text | 完成 | h1~h3 / p + i18n |
| table | 完成 | 資料綁定、四動作准入、欄位遮罩、CRUD、捲動載入 |
| detail | **部分** | 只能檢視（含遮罩），無就地編輯 → 本檔 §3 |
| form | **部分** | FormIO 設計器可用，送出後沒有接上任何後端流程 → 本檔 §2 |
| actions | **未做** | registry 零註冊 → 本檔 §4 |

---

## 1.4 【2026-07-29 更新】form 元件（送件主線）已完成

**§1.5 描述的硬阻擋已解除，§2 的「未定案」已全部裁決並落地。**
本節是現況；§1.5 與 §2 的原文保留作為決策脈絡，讀的時候以本節為準。

### 用戶裁決（2026-07-29）

| 議題 | 裁決 |
|---|---|
| portal action 機制 | **A 案**：`_PORTAL_ACTIONS` 自成 registry，權限吃 widget `access_matrix` |
| 公用帳號 | `users` 真實 row、`user_type=EXTERNAL`、`is_service_account=True`、不可登入 |
| 匿名訪客送件 | **允許**。識別碼是 server 發的一次性 `guest_token`（只存 Flask session） |
| 識別碼存放 | `fw_workflow_instances` 加實體欄位 + 複合 index，並鏡射進 `variables.nocode` |

### 已落地的東西

| 能力 | 位置 |
|---|---|
| portal action registry | `registry.py`：`register_portal_action` / `get_portal_action` / `list_portal_actions` |
| 內建 portal action | `portal.form.submit`，在 `nocode_builder/__init__.py:init_runtime()` 註冊 |
| `form_widget` 新欄位 | `schema_v3.json`：`mapping_ref`、`access_matrix`（form 只用 `create`） |
| renderer 分流 | `renderer._prepare_form()` → portal 走 `_portal_form_submit_url()`，全程 fail-closed 回 `None`（唯讀），不 raise |
| render context | `set_render_context()` 加 `path_id` / `page_sc`（renderer 組送件 URL 要用） |
| 送件 API | `POST /public/portal/<path_id>/api/pages/<page_sc>/widgets/<widget_id>/submit` |
| 公用帳號 | `app/services/nocode_service_account.py:get_or_create(org_secure_code)` |
| guest token | `portal_auth_service.ensure_guest_token()` |
| mapping 引用守衛 | `nocode_builder/services/pageir_mapping_usage.py` + `mappings.py` 的 `_nocode_usage()` |
| 設計器面板 | form widget 可設配對／送出動作／元件准入；准入 UI 抽成 `_ir_designer_access_matrix.html` macro，table/detail/form 共用 |
| migration | `scripts/migrations/088_nocode_form_submit.sql` |

送件成立的三個條件（缺一即唯讀，**渲染層與 API 層都檢查**）：
`submit_action_ref` 已註冊 + `mapping_ref` 有值 + `access_matrix.create` 判定通過。

### 這一輪新踩的坑（會再踩，寫下來）

1. **portal action registry 差點形同虛設**。第一版送件 API 只檢查 access_matrix
   與 mapping_ref，**完全不看 `submit_action_ref`**。後果是設計者把「送出動作」
   清空、以為表單變唯讀，但知道 URL 的人仍能直接 POST 送件成功。
   教訓：新增抽象層時，要問「不走這層直接打 API 會怎樣」，
   而不是只驗證「走這層的路徑對不對」。
2. **匿名送件端點必須有 rate limit**。`allow_anonymous` 的子系統等於開放匿名寫入，
   沒有 limiter 就能無限灌流程實例。現為 `10 per minute; 100 per hour`。
   注意 **CSRF 檢查發生在 limiter 之前**，測 limiter 時必須帶正確的 token，
   否則全部 400、看不到 429。
3. **`dataScope` 推導不出純 form 頁**。設計器的「元件准入」UI 顯示條件是
   `x-if="dataScope"`，而 `dataScope` 原本只從
   `firstPortalBindingResource()`（找 `portal:` 前綴的 binding）推導。
   form widget 沒有 binding → 純 form 頁的 `dataScope` 永遠是空 →
   **准入 UI 不顯示 → create 無從設定 → 表單永遠送不出去**。
   修法：`GET /api/nocode-builder/pages/<sc>` 回傳 `sub_system_secure_code`
   （查 `dc_sub_system_pages` 掛載關係），`detectPortalScope()` 優先用它。
4. **`password_hash` 給非 bcrypt 值會讓 `bcrypt.checkpw` 拋 `ValueError`**，
   不是回 False。公用帳號的 `'!nologin'` 就是這種值，
   `User.check_password()` 已加 try/except。
5. **送件會真的跑完整條流程**。用「子系統開發申請」配對做 E2E 時，
   流程的 SubSystemProvision 節點會**真的建出子系統**
   （`dc_sub_systems.provision_serial_number` 對得上送件序號）。
   測完記得清，否則設計器的子系統下拉會被測試垃圾塞滿。

### 本機測試資料（是事實，不要重建）

```
測試頁 : FORMTEST00000000000001（Form 送件 E2E 頁），掛在 8uopl3mNbDzGDUGAcNQqNe
配對   : 7AVNBK7C-kQ5LSb2DEmeMw（子系統開發申請，已發行未封存）
公用帳號: nocode-svc-beluga / nocode-svc@beluga.local（企業 _9c8TewkRkCBEf3XsUdqeF）
```

頁面結構是一個 layout 包三個 form widget，刻意做成對照組：

| widget | 設定 | 預期 |
|---|---|---|
| `form-1` | 配對 + 動作 + create(不限群組/GUEST) | 可送出 |
| `form-2` | 同上（本輪驗收時由設計器補上動作） | 可送出 |
| `form-3` | create 設 VIP / ADMIN | 一般訪客唯讀，直打 API 回 404 |

---

## 1.4.1 【2026-07-29 更新】簽核狀態可見已完成

用戶裁決把這項插在 detail 之前做完。

### 做法：新增 portal 資源，不新增 widget 型別

資源 code：**`formflow:submissions`**
（`modules/nocode_builder/services/pageir_formflow_resources.py`）

設計者用**既有的 table / detail widget** 綁定它就能顯示「我送出的表單」。
分頁、排序、遮罩、元件准入、捲動載入全部沿用既有機制。

為此放寬了 `schema_v3.json` 的 `resource_ref` pattern：
`^([a-z][a-z0-9_-]{0,63}|(portal|formflow):[A-Za-z0-9_-]{8,64})$`
—— **明列兩個前綴，不是通配任意前綴**。日後要加第三種資源前綴，
照這個模式加，不要改成 `[a-z]+:`。

### 六個欄位（固定，設計者不可增減）

`serial_number` / `execution_code` / `subject` / `status_label` /
`current_step` / `submitted_at`

**刻意不放**申請人、簽核人、簽核意見、`form_data`、內部節點 id。
申請人一律是公用帳號，對外部用戶無意義且會洩漏內部帳號名。
用戶要的是「不必像表單中心那麼詳細」，**不要自行加欄位**。

`status_label` 是人話（審核中／處理中／已完成／已退回），
判定依據是 `fw_node_execution_queue` 有無 WAITING 的 Approve/FormAdapter 節點。
`current_step` 是該節點的 `node_name`（多個取 `scheduled_at` 最早）。

### 安全設計（改這支程式前務必讀）

- 三重過濾**全部在 SQL WHERE**：`org_secure_code` + `nocode_sub_system_sc`
  + `nocode_user_ref`。`fetch_detail` 是在同樣的 WHERE 上再加
  `fi.secure_code = record_sc`——**不是先查再比對**，後者就是 IDOR
- 唯讀是硬性的：`crud` 全 False **之外**，`create_row` / `update_row` /
  `delete_row` 也直接回 `(False, "readonly")`。不可留 `None`
  （呼叫端拿到 `None` 會 TypeError，而不是乾淨拒絕）
- 識別碼算法抽成 `portal_auth_service.nocode_user_ref()`，
  **送件端與查詢端共用同一份**。兩邊一旦漂移，輕則查不到自己的案子，
  重則查到別人的
- `portal_user` 不是 dict 時 helper 拋 `ValueError`，不回空字串
  （空字串會讓查詢條件變成比對空值）

### 匿名用戶的必然限制

匿名的 `user_ref` 是 `g:<guest_token>`，token 只存 Flask session。
**清 cookie 或換裝置就查不到自己先前送的案子**。
這是「一次性 token」方案的必然結果，用戶已知並裁決接受。
要支援跨裝置查詢就得讓匿名者留下可驗證的聯絡方式，那是另一個題目。

### 驗收（本機實測，非推論）

| 情境 | 結果 |
|---|---|
| p4tester（`u:1`）看清單 | 3 筆，全是自己的 |
| 原匿名 session（`g:Patkey...`） | 1 筆，只有自己的 |
| 全新匿名 session | 0 筆 |
| p4tester 用 `subs-2__sc=` 查匿名那筆 | 「請選擇一筆資料」（不洩漏存在與否） |
| 匿名查 p4tester 那筆 | 同上 |
| 捲動載入 API 跨用戶 | total 各自 3 / 1 |
| POST / PUT / DELETE rows | 全 404 |
| platform 世界 / 缺 ctx / `formflow:other` | 全部回 `None` |
| 造一筆 WAITING 的 Approve 節點 | 顯示「審核中」+「部門主管審核」 |

`backend/tests/test_pageir_formflow_submissions.py` 的隔離測試是真的建兩筆
不同 `nocode_user_ref` 的資料互查，不是 mock。

---

## 1.4.2 【2026-07-29 更新】form 三狀態已完成

用戶把 §2.2 的「兩種狀態」澄清為**三**狀態（原話重點）：

> 新增：填新表單。
> 修改：有些情境是能修改的，例如**還沒被別人簽之前修改比撤單重填省事**。
> 唯讀：如稽核人員，或**追蹤目前不在自己簽核的表單**就該唯讀。
> 「你定義一個流程變數即可，**流程設計者去負責**依用戶在流程階段的變遷
> 而有唯讀或修改狀態。」

**關鍵設計決定：可否修改由流程變數決定，平台只忠實執行，不自作主張加規則。**

### 流程變數 `nocode_editable`

- FLOW scope，流程設計者用既有的 **`OpSet`（設定變數）節點** 設定
- 判為可修改的值：`True` / `"true"` / `"True"` / `"1"` / `1`
- **未設定或其他任何值 → 唯讀**（fail-closed）
- 判定函式 `is_submission_editable()` 在
  `modules/nocode_builder/services/pageir_formflow_resources.py`

### 狀態判定（`renderer._prepare_form()`）

依 URL 的 `?<widget_id>__sc=<form_instance_sc>`：

| 情況 | mode |
|---|---|
| 無 `__sc`，或 state_resolver 回 `None`（含**別人的** sc） | `new` |
| 有 state、`editable` 為真、且 access_matrix 的 `update` 通過 | `edit` |
| 其餘 | `readonly` |

拿別人的 sc 會落回 `new`，不是「查無此筆」——**刻意不洩漏該筆是否存在**。

更新端點：`PUT .../widgets/<widget_id>/submissions/<record_sc>`
（`portal_widget_update_submission`）。
**只更新 `fw_form_instances.form_data`**，不動流程狀態、佇列、簽核軌跡。

### 兩個容易再犯的坑（本輪修掉的）

1. **流程變數的權威儲存是 `fw_workflow_variables` 表，不是
   `fw_workflow_instances.variables` JSONB**。
   上一輪把 nocode 識別碼鏡射進 JSONB，以為流程設計者能引用——引用不到：
   - `${v.xxx}` 走 `VariableService`，只讀那張表
   - `${wi.xxx}` 只支援 `base.py` 的
     `_WI_FIELDS = {'wi.code','wi.exec_code','wi.name','wi.status','wi.depth'}`

   現在送件成功後會用 `VariableService.set_flow_var()` 寫成真變數
   （`nocode_sub_system` / `nocode_user_ref`），流程設計者可用
   `${v.nocode_user_ref}`。實體欄位與 JSONB 鏡射保留（查詢用，index 靠它）。

2. **`is_submission_editable()` 刻意不走 `VariableService.get_flow_var()`**。
   那層有一份類別層級、**無 TTL** 的進程內快取。開發環境是 `flask run`
   單進程 + 同進程 daemon thread 跑流程引擎，所以看不出問題；
   多 worker 部署下，流程把變數改成 false 之後其他 worker 仍讀到舊的 true。
   **用過期值做顯示只是難看，用過期值做授權判定就是漏洞**，所以直接查 DB。
   已實測：SQL 改值後不重啟服務，下一次請求就從 `edit` 變 `readonly`。

3. 防禦深度：更新端點**不可以**自己再查一次 `FwFormInstance`。
   必須用 `get_editable_submission(record_sc, ctx)` 一次取得——
   它走同一個 `_base_query()`（三重過濾 + editable）。
   第一版曾是「先用 state 檢查、再用 org 條件重查一次 instance」，
   當下不是漏洞（record_sc 沒變），但只要有人拆掉前面的檢查就會變成 IDOR。

### 驗收（本機實測）

| 情境 | 結果 |
|---|---|
| 無 `__sc` | `mode=new`，有 submit_url |
| 有 `__sc`、未設 `nocode_editable` | `mode=readonly`，無任何 url，資料有帶入 |
| 拿別人的 `__sc` | `mode=new`，不帶資料（不洩漏） |
| 設 `nocode_editable=true` | `mode=edit`，有 update_url，資料帶入 |
| readonly 時直打 PUT | 404 |
| edit 時 PUT | 200，`form_data` 更新，流程狀態與佇列**完全未動** |
| 改別人那筆 | 404 |
| SQL 把變數改 false（不重啟） | 下一次請求即變 readonly，PUT 404 |
| 送新件後查流程變數 | `nocode_sub_system` / `nocode_user_ref` 都在 |

### 撤單（用戶已裁決，尚未做）

> 「至於撤單（資料會保存直到 DBA 刪除）應該用 action 做比較適合。」

→ 留到 actions 階段，本輪明確不做。

### 尚未做的必要配套

**目前沒有任何機制能從 table 列連到 `?<widget>__sc=`。**
detail widget 一直只能手改 URL，form 的 edit / readonly 模式同樣觸達不了。
計畫：table widget 加選填 `row_link_ref` 指向同頁 form/detail widget，
每列產生導覽連結。

### detail 階段動工前要問的事

用戶說「以上 form 的說明也適用於 detail，這算是對應 form.io 開發表單時的
data grid 或 edit grid」。這裡有個要攤開來確認的差異：

- form.io 的 **editgrid/datagrid 是表單內部的多列輸入元件**，
  資料落在 `fw_form_instances.form_data` 裡
- **detail widget 綁的是 portal SQLite 業務表**，資料落在 `portal_data.db`

「訂價單品項一直加」用哪一種，決定 detail 階段要做什麼。動工前必問。

---

## 1.5 【已解除，保留作決策脈絡】portal 世界原本完全不支援 action

冷讀審核時查證出來的硬阻擋。不先處理，form 元件做到一半必定卡住：

```python
# backend/app/pageir/registry.py:96  get_action()
if get_render_context().get("world") == "portal":
    return None          # portal 語境一律取不到 action

# backend/app/pageir/renderer.py:339  _prepare_action_buttons()
if get_render_context().get("world") == "portal":
    return []            # portal 的動作按鈕全部消失

# backend/app/pageir/renderer.py:369  _prepare_form()
action = get_action(submit_action_ref)
if action is None:
    raise PageIrRenderError(f"Unregistered form submit action: {ref}")
```

**後果**：IR schema 的 `form_widget` 有 `submit_action_ref` 欄位，
一旦填了值，該頁在 portal 渲染時 `get_action()` 回 None → **raise → portal 頁 422**。
而 form 元件的整個產品意圖就是給 portal 外部用戶用的。

這是**刻意的 fail-closed**（不是 bug）：`action_button.permission` 走
`capability_service.user_can()`，那是平台 capability，portal 世界沒有平台身分，
所以整條路被封死。

**因此 form 的第一步不是做 UI，是決定「portal 世界的 action 機制」**：
- 選項 A：portal action 自成一套 registry，權限用 widget 的 `access_matrix`
  （與元件准入同源，不碰平台 capability）
- 選項 B：沿用現有 registry，但為 portal 語境放行特定白名單 action，
  權限改吃 `portal_access_service`
- 建議 A（世界互斥是本專案刻意的設計，B 會在 registry 裡混兩套權限語意）

**這件事要先跟用戶確認再動工**，它決定 form 與 actions 的共同地基，
也是「actions 排最後」這個順序唯一的例外——底層機制必須先於 form 落地。

相關 schema（`backend/app/pageir/schema_v3.json`）：

```json
"form_widget":   {"required": ["id","type","formio_schema"],
                  "properties": {"submit_action_ref": {"$ref": "#/$defs/permission_ref"}}}
"actions_widget":{"required": ["id","type","buttons"]}
"action_button": {"required": ["id","label_i18n","permission","action_ref"],
                  "properties": {"style": {"enum": ["primary","secondary","danger"]}}}
```

`register_action(ref, config)` 的 config 目前被 renderer 消費的欄位：
`url`（必要）、`method`（只接受 POST，其他 raise）、`confirm`（bool）。

---

## 2. form 元件：外觀是網頁，實際是表單流程

### 2.1 用戶定義的產品意圖（原話重點）

> 「nocode 要給非 BeakPlatform 帳戶使用 /forms/center 時就用 form 元件觸發存在
> /forms/mappings，用的是統一的 Platform 的公用排程帳號。nocode 的用戶以為填寫的是
> 一般 web 介面寫入 DB，但其實是借用公用帳號填寫表單，依設計運作的複雜背景流程。
> 並非傳統設計方式的後續都寫程式處理，無視覺化流程工具也難以管理的方式。
> 簡單的說就是外觀是一般網頁，實際是表單流程。」

翻譯成技術語言：

```
portal 外部用戶 → 填 IR form widget → 以「企業公用帳號」身分
                → 送進既有 form_workflow mapping → 跑完整簽核流程
```

外部用戶完全不知道背後是簽核流程；設計者則能用既有的視覺化流程工具管理後續處理。

### 2.2 用戶已裁決的事項（不要再問）

| 議題 | 裁決 |
|---|---|
| 公用帳號層級 | **每企業一個**（表單中心本來就是企業級，公用帳號要帶企業識別碼）。此帳號**目前不存在，要新增** |
| 識別碼寫在哪 | **兩處都寫**：① 系統內對應表（可擴充 `fw_workflow_instances`）② 表單內欄位（**用戶不可視**），用途是流程運作中當變數使用 |
| 為何要兩個識別碼 | nocode 代碼 + 外部用戶識別碼，避免不同 nocode 子系統有同名帳號時對不起來 |
| 簽核狀態可見性 | **要做，但不必像表單中心那麼詳細**。用「待簽核」原理擴充 nocode 欄位，用戶進頁面（或 F5）時查一次即可 |
| 簽核者 | 平台內部帳號，由流程節點動態解析。外部用戶只有送件角色 |
| form 的兩種狀態 | **新增** 與 **簽核**，設計時要分開處理 |
| mapping 生命週期 | mapping 的**刪除/關閉必須檢查是否有 nocode 正在使用** |

### 2.3 既有可直接接的後端（已查證，不要重造）

**送件入口**：`modules/form_workflow/services/form_submit_service.py`

```python
create_instance_and_start(
    *, org_secure_code, serial_number, org_form_seq, subject, form_data,
    is_test, source_type, source_ip, source_api_key=None,
    form_name=..., form_code=..., form_version=..., form_schema=...,
    workflow_name=..., workflow_version=..., workflow_graph=...,
    published_sc=..., proc_prefix='PROC-',
    applicant_secure_code=None, applicant_name=None,
    applicant_username=None, applicant_email=None, applicant_dept=None,
)
# 回傳 (form_instance, workflow_instance)
# 建立 FwFormInstance + FwWorkflowInstance(RUNNING) + Start 節點入佇列，單一交易
```

`applicant_*` 就是「公用帳號」要填入的位置；`source_type` 可用來標記來源是 nocode portal。

**mapping 管理**：`modules/form_workflow/api/mappings.py`
- `delete_mapping()` 第 357 行、`archive_mapping()` 第 863 行
  → **這兩支要加上「是否被 nocode form widget 引用」的檢查**
- `publish_mapping()` 第 528 行；intake 與表單中心都只讀
  `fw_published_form_workflows` 的最新 Published 快照

**待簽核的權威來源**（用戶提供並已查證屬實）：

```sql
SELECT * FROM fw_node_execution_queue
WHERE org_secure_code = ?
  AND status = 'WAITING'
  AND node_type IN ('Approve','FormAdapter','FORMADAPTER')
ORDER BY scheduled_at;
```

| 表 | 角色 |
|---|---|
| `fw_node_execution_queue` | **待簽核任務**（`status='WAITING'` + `node_type='Approve'`）。簽核後改 SUCCESS/REJECTED |
| `fw_approval_records` | 已簽核歷史軌跡（誰、何時、意見、代簽人）。只有 approved / FORCE_END，**不存 pending** |
| `fw_form_instances` | 表單本體與資料 |
| `fw_workflow_instances` | 流程實例，`current_node_id` 指向當下節點 |

**關鍵陷阱**：queue 表**沒有「指派給誰」的欄位**。簽核人是執行時依 `node_config`
動態解析（部門主管、角色等）。「我的待簽」是先取 WAITING 任務、再逐筆算簽核人，
**不能**直接用 SQL 過濾 approver。
參考實作：`modules/form_workflow/api/fc_pending.py:31-50`
（它從 `task.result['data']['assignee_type'] / ['assignees']` 比對 user_code）。

### 2.3.1 冷讀補洞：查得到但容易試誤的位置

| 要找什麼 | 在哪 |
|---|---|
| mapping 表欄位（供「nocode 是否在用」查詢） | `fw_form_workflow_mappings`：`org_secure_code` / `form_template_secure_code` / `workflow_template_secure_code` / `is_active` / `is_published` / `publish_at` / `trigger_condition`(json) / `priority` |
| 「正在使用」的引用來源 | nocode 這端還沒有欄位——form widget 目前只有 `formio_schema` + `submit_action_ref`，**沒有存 mapping 參照**。要新增 widget 欄位（如 `mapping_ref`）才有得查。這是實作項目，不是查詢問題 |
| 簽核人動態解析 | `modules/form_workflow/services/node_handlers/formadapter_handler.py`：`_resolve_assignees(assignee_type, assignee_value)`，`assignee_type` ∈ ROLE/USER/DEPARTMENT/INITIATOR/DYNAMIC。**已是 handler 內的方法，尚未抽成獨立 service**——要複用得先評估抽出，不要複製一份 |
| 「我的待簽」過濾邏輯 | `modules/form_workflow/api/fc_pending.py:39-46`，讀 `task.result['data']['assignee_type']` 與 `['assignees']` 比對 user_code |
| 發行快照 | `fw_published_form_workflows`，intake 與表單中心只讀最新 Published。改模板不重發行等於沒改；直接改 graph 不會 bump revision（見 CLAUDE.md 備忘） |

### 2.4 實作前要自己確認的事（本檔作者未做決定，留給實作者）

1. **公用帳號怎麼建**：是 `users` 表的真實 row（`user_type` 用哪一層？）還是
   service account 型態？它會出現在簽核歷程與流程變數裡，命名要一眼看得出是系統帳號。
   建議：每企業一個，帳號格式如 `nocode-svc@<org_code>`，
   `is_active=True` 但**不可登入**（無密碼/拒絕 login flow），並確認
   `DATA-01`（帳號查詢過濾 is_deleted + is_active）不會把它從簽核人解析中誤刪。
2. **識別碼的存放形狀**：`fw_workflow_instances` 已有 `variables` JSONB 欄位
   （流程變數就從這裡取），**不必新增欄位就能滿足「當變數使用」**。
   但若要支援「查某外部用戶的所有案件」，JSONB 查詢需要 index。
   建議：加兩個實體欄位 `nocode_sub_system_sc` / `nocode_user_ref` + 複合 index，
   同時把值鏡射進 `variables` 供流程引用。**這是建議不是裁決，動工前跟用戶確認。**
3. **表單內的隱藏欄位**：用戶要求寫進表單欄位但「用戶不可視」。
   FormIO 的 hidden component 在前端仍可被改（DevTools），
   所以**後端送件時必須以 server 端的值覆寫**，不可信任前端送上來的識別碼。
4. **匿名訪客能不能送**：用戶未明確說。匿名問卷場景顯然要能送，
   但那樣「外部用戶識別碼」是什麼？（session id？一次性 token？）**要問用戶。**

---

## 3. detail 元件：就地編輯 + 草稿

### 3.1 用戶定義的場景（原話）

> 「detail 要能就地編輯，例如訂價單的品項一定是一直加，在最終送出之前都還能改，
> 所以沒有送出之前的修改不該寫入 DB 中，或者寫入暫存表，又或者寫入但加標記
> 等由你判斷哪樣適合。」

### 3.2 建議方案：**正式表 + draft 標記**（已向用戶說明，用戶未反對）

在業務表加兩個系統欄位：

| 欄位 | 用途 |
|---|---|
| `_draft_owner` | `<nocode 子系統代碼>:<外部用戶識別碼>`，草稿的擁有者 |
| `_draft_status` | `draft` / `submitted` |

規則：
- 編輯期間直接寫進正式表但標為 `draft`
- **所有查詢預設過濾掉 draft**，只有擁有者本人看得到自己的草稿
- 送出時改成 `submitted`（這個動作就是 actions 的第一個場景，見 §4）

**選這個方案的理由**（不是隨便選的，日後有人想改回暫存表請先讀這段）：
- 暫存表要維護兩套 schema 與搬移邏輯，schema 一改就要同步兩邊
- 純前端暫存一關瀏覽器就沒了，品項多的單子很痛
- 標記法只需在 portal resolver 的查詢層加一個固定過濾，
  與現有 `soft_delete_column` 機制同構（`sqlite_crud_service.query_rows()` 第 194 行
  已有 `soft_delete_column` 的相同寫法可照抄）

**代價**（必須一併處理，不做就是技術債）：
- 業務表多兩個系統欄位 → `create_portal_data_table` API（`api/sub_system_api.py`）
  的自動欄位要不要一起加？**要跟用戶確認**（不是所有表都需要草稿）
- 過期草稿要排程清理（超過 N 天未送出），
  依 heartbeat 規範寫入 `/opt/tmp/heartbeat/`，排程放 `/etc/crontab`
- `_draft_owner` 必須是 server 端算出來的，**不可信任前端送的值**，
  否則 A 用戶可以偷看/改 B 用戶的草稿

### 3.3 就地編輯的權限來源

沿用 table 的 `access_matrix.update`（同一套 `portal_access_service` 判定），
**不要**為 detail 另建一套。理由：兩者綁的是同一個資源與 view，
分兩套會出現「table 不能改但 detail 能改」的破口。

草稿階段的寫入仍要過 §2 既有的三重欄位交集
（`binding.fields ∩ resource.fields ∩ writable_fields`）與遮罩排除
（masked 欄位不可寫，見 `backend/app/pageir/masking.py`）。

---

## 4. actions 元件（最後做）

### 4.1 為什麼放最後

用戶：「這個『送出或確認』的行為應該可當 actions 的場景」。
form 的送件、detail 草稿的 submit，都是 action。
先把這兩個具體場景做出來，actions 的介面（參數、回傳、錯誤處理、權限）
才有真實需求可依循。

### 4.2 現況

- `backend/app/pageir/registry.py:91` 有 `register_action(ref, config)`
- 平台側與模組側都**沒有任何實際註冊**
- 設計器的 actions 元件可以拖進頁面，但動作下拉是空的
- `table.row_actions_ref` 指向 actions widget，因此列動作也不可用

### 4.3 做的時候必須先問用戶的事

1. 第一個真 action 的完整場景（資源、觸發點、預期行為、失敗時的 UI）
2. action 的權限模型：portal 世界沒有平台 permission code。
   是沿用 widget 的 `access_matrix` 四動作，還是 action 自帶一組條件？
3. action 執行後的頁面行為：留在原頁重整、跳轉、還是只跳訊息

### 4.4 落地時要補的驗收

第一個 action 落地時要補 E2E（交接檔 `handoff_nocode_n1_n5.md` §6.8 登記在案）。

---

## 5. 這一輪（2026-07-28~29）已完成、可直接依賴的東西

| 能力 | 位置 | 備註 |
|---|---|---|
| 元件准入四動作 UI | `_ir_designer_body.html` + `ir-designer.js` | read/create/update/delete 各自可設群組+階級 |
| 欄位視覺遮罩 | `backend/app/pageir/masking.py` | partial/full/email/phone；masked 欄位不可排序、不可寫 |
| 工作區「資料表」tab | `workspace.html` + `workspace-tables.js` | 建表限 portal_data，掛 `nocode_builder.manage` |
| portal 預覽 | `web/__init__.py` 的 `ir_designer_preview()` | `?sub=&group=&level=`，走真實判定鏈，portal 外殼、唯讀 |
| fixed_filters fail-closed | `services/sqlite_crud_service.py` | portal 語境只允許 `$TODAY`，其餘拒絕查詢 |

測試基準：**155 passed**

```bash
cd /opt/BeakPlatform-dev/backend
../venv/bin/python -m pytest tests/test_pageir_*.py tests/test_portal_*.py \
  tests/test_sitemap_access_matrix.py -q
```

### 5.1 本 session 實測過的 E2E 指令（照抄即可，勿憑印象改寫）

```bash
BASE=http://192.168.0.16:7000/beakplatform
PSC=SavnwD-Te3EGRF4rNS8Uj0    # P4 E2E Portal 頁（含 member-table 與 feedback-table）
SS=8uopl3mNbDzGDUGAcNQqNe     # 匿名問卷子系統，portal path_id = ubwdM7Tp

# ── 平台管理員登入（cookie jar: cj.txt）──
USC=$(PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
  -c "SELECT secure_code FROM users WHERE email='admin-ethanyu@beluga.com' AND is_deleted=false;")
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$USC\"}"
TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)

# ── portal 帳號登入（獨立 jar: p4_cj.txt；p4tester 目前 GENERAL / STAFF rank 50）──
curl -s -c p4_cj.txt -X POST "$BASE/public/portal/ubwdM7Tp/login" \
  -d 'username=p4tester&password=p4test123'

# ── 看元件准入判定結果（UI 與 API 是否同源）──
curl -s -b p4_cj.txt "$BASE/public/portal/ubwdM7Tp/p/$PSC" \
  | grep -o 'id="feedback-table".*data-pir-can-delete="[a-z]*"' | grep -o 'can-[a-z]*="[a-z]*"'

# ── portal 寫入 API（body 必須包在 data 裡，直接放欄位會回 invalid_data 400）──
API="$BASE/public/portal/ubwdM7Tp/api/pages/$PSC/widgets/feedback-table/rows"
PTOKEN=$(curl -s -b p4_cj.txt "$BASE/public/portal/ubwdM7Tp/p/$PSC" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -s -b p4_cj.txt -X POST "$API" -H "X-CSRFToken: $PTOKEN" \
  -H 'Content-Type: application/json' -d '{"data":{"title":"x","content":"y"}}'

# ── portal 預覽（模擬身分，走真實判定鏈）──
curl -s -b cj.txt "$BASE/nocode/ir-designer/$PSC/preview?sub=$SS&group=GENERAL&level=STAFF"

# ── 建表 API（限 portal_data，需 nocode_builder.manage）──
curl -s -b cj.txt -X POST "$BASE/api/nocode-builder/sub-systems/$SS/tables" \
  -H "X-CSRFToken: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"data_source":"portal_data","table_name":"demo","columns":[{"name":"c1","type":"TEXT","required":true}]}'

# ── 子系統 SQLite 直查 ──
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/$SS/portal.db \
  "SELECT username, group_code, level_code FROM portal_users;"
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/$SS/portal_data.db \
  "SELECT name FROM sqlite_master WHERE type='table';"   # feedback / orders

# ── 權限被拒的原因（一律回 404，不看 log 查不出來）──
sudo journalctl -u beakplatform-dev.service --since "-5 min" | grep reason=
```

**本機現有測試資料（是事實，不要重建）**：
- `feedback` 表：3~5 筆，`content` 欄位目前設了 `partial` 遮罩（keep_head 2 / keep_tail 2）
- `orders` 表：本 session 用建表 UI 建的，已有 CRUD View
- `feedback-table` widget 的 access_matrix：
  read=GUEST/不限、create=GENERAL/MEMBER、update=不限/STAFF、delete=VIP/ADMIN
- portal 帳號：`p4tester`（GENERAL/STAFF）+ `bulk01`~`bulk25`（GENERAL/MEMBER）

---

## 6. 動工前必讀（不讀會重蹈覆轍）

1. `docs/handoff_nocode_n1_n5.md` **§2 三層判定鏈**
   —— read 未宣告放行 / write 未宣告拒絕，語意刻意不同
2. `docs/handoff_nocode_n1_n5.md` **§4 踩過的坑**
   —— 特別是 4.1 Jinja2 `dict.update` 陷阱、4.5 帳號表不能當 CRUD 目標
3. 本輪新增的坑（補充 §4）：
   - **`x-model` 綁動態 `x-for` options 的 select，初次渲染會顯示成第一個選項**。
     修法是在 option 加 `:selected="<值> === <狀態>"`。
     這個 bug 讓設計器的「資料範圍/資源/欄位」長期顯示錯值，
     使用者會照著錯的顯示做設定。新增 select 一律照此寫。
   - **D2 的 `BkCaps.can()` 需要頁面自行注入 `window.__PAGE_CAPS`**
     （`build_caps([...])` 傳給模板）。沒注入就恆為 false，
     症狀是按鈕點了完全沒反應、console 也不報錯。
   - **改完 Python 一定要 `sudo systemctl restart beakplatform-dev.service`**。
     本輪曾對著舊碼驗收，得到 500 而誤判 codex 實作錯誤。
4. `CLAUDE.md` 的 **PERM-02**：觸及按鈕/動作 API 的工單，動工前要問用戶是否套 D2；
   全新頁面不必問，一律套。

---

## 7. 尚未定案、必須問用戶的清單（彙整）

| # | 項目 | 章節 |
|---|---|---|
| 1 | 公用帳號的實際型態與命名、是否可登入 | §2.4-1 |
| 2 | 識別碼用 `variables` JSONB 還是加實體欄位 + index | §2.4-2 |
| 3 | portal 匿名訪客能否送表單？匿名時的「外部用戶識別碼」是什麼 | §2.4-4 |
| 4 | 建表 API 是否自動加 `_draft_owner` / `_draft_status` | §3.2 |
| 5 | 過期草稿的保留天數與清理排程時機 | §3.2 |
| 6 | 第一個真 action 的完整場景 | §4.3 |
| 7 | **portal 世界的 action 機制走 A 案（自成 registry）還是 B 案（白名單放行）** | §1.5 |
| 8 | detail 就地編輯的互動細節：何時存、能否取消/還原、驗證失敗如何顯示、同一筆多人編輯如何處理 | §3 |
| 9 | detail 草稿「送出」只是改 `_draft_status`，還是同時觸發 form workflow | §3 / §4 |
| 10 | form widget 要新增哪個欄位存 mapping 參照（`mapping_ref`？），才能反查「nocode 是否在用」 | §2.3.1 |

> 第 7 項是**地基**，不先定案 form 做不下去（見 §1.5）。
> 其餘可在各自階段動工前再問。

---

## 8. 冷讀審核紀錄

2026-07-29 用 `codex exec --sandbox read-only` 做過一次冷讀（不帶本對話記憶），
列出 20 個「需要猜測或試誤」的點。處理方式：

- 11 點本來就是待用戶裁決事項 → 已在 §7 列表（不是文件缺口）
- 9 點是「查得到但文件沒寫」→ 已補進 §1.5、§2.3.1、§5.1、§7

其中 §1.5（portal 不支援 action）是冷讀才逼出來的**硬阻擋**，
原本的交接檔會讓新 session 做到 form 送出時才撞牆。
