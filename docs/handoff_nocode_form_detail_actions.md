# 交接：NoCode 三個未完成元件（form / detail / actions）

> 建立日期：2026-07-29
> 前置交接檔：`docs/handoff_nocode_n1_n5.md`（N1~N5 的判定鏈、檔案地圖、十個踩坑）
> 本檔接續其 §6，處理「六個元件」中尚未完成的三個。

---

## 0. 開發順序（用戶已裁決，不要自行調整）

```
① form  →  ② detail 就地編輯  →  ③ actions
```

**三者皆已完成**：① 見 §1.4 / §1.4.1 / §1.4.2（2026-07-29），
② 由 §2.9 的主細表元件取代（2026-07-29），③ 見 §4.0（2026-07-30）。
以下的「未做 / 待裁決」字樣一律是歷史脈絡，不是現況。

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
| actions | 完成 | portal 動作按鈕 + 撤單（2026-07-30）→ 本檔 §4.0 |

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

## 2.9 【2026-07-29 完成】主細表元件 `master_detail`

**§3 的「detail 就地編輯 + 草稿」已被本節取代**，原文保留作為決策脈絡。
用戶原本說 detail 對應 form.io 的 data grid / edit grid，後來自己更正：

> 「我誤會了 form.io 的 datagrid, editgrid 的原理與 web 的運作，
> 所以才會說出前述兩個元件的錯誤對應。會綜合兩個元件的特性所以要新開發…
> 因 form.io 那兩個也不好用。需求是：**資料在業務表（detail widget + portal SQLite）
> 就是傳統的主細表，由兩個表用 FKey 關聯**。」

用戶另外裁決：日後也會在 `/forms/templates/` 的「平台元件」類別下出一個新元件
——**目前只做 portal 版**，`master_detail_service.py` 就是日後平台版可以接的那層
（它刻意不含 portal 權限判定，權限在路由層判完）。

### 用戶定義的三場景（電話客服）

| 場景 | 情境 | master | detail |
|---|---|---|---|
| 一 | 第一次來電、沒有客戶資料 | **新增**客戶基本資料 | 本次 1~n 筆服務項目 |
| 二 | 客戶已在主表 | **編輯或唯讀**（設計者決定） | 本次 1~n 筆服務項目 |
| 三 | 同二 | 同二 | 同二 + **此客戶歷史服務記錄**（唯讀，給客服參考） |

### 用戶已裁決、不要改的兩件事

1. **detail 的 1~n 筆在送出前只存前端**，送出時一次寫入兩表（單一交易）。
   不做草稿表、不做 `_draft_status` 標記。中途關瀏覽器就是全部消失。
   （§3.2 建議的草稿方案**已被否決**，不要照那段實作。）
2. **歷史用 Tabs 呈現**（「本次服務項目 N」/「歷史記錄 M」），不是上下並排。

### 檔案地圖

| 東西 | 位置 |
|---|---|
| schema | `schema_v3.json` 的 `master_detail_widget` / `md_master` / `md_detail` / `md_history` |
| 渲染 | `renderer._prepare_master_detail()` |
| 歷史查詢 | portal provider 的 `fetch_related()`（`pageir_portal_resources.py`） |
| 交易寫入 | `modules/nocode_builder/services/master_detail_service.py` |
| 送出 API | `POST /public/portal/<path_id>/api/pages/<page_sc>/widgets/<widget_id>/master-detail` |
| 建表 FK | `sub_system_api.create_portal_data_table` 的 `columns[i].references` |
| 設計器 | `_ir_designer_body.html` 的 `master_detail` 區塊 |

### 關鍵事實（省下重新查證的時間）

- `DataSourceManager().get_session()` **是交易 scope**（yield 後 commit、
  例外 rollback），`SqliteCrudService.create_row()` 只 `flush()` 不 commit
  → 主表 + n 筆明細寫在同一個 `with` 內就是單一交易
- `SqliteCrudService.query_rows()` **早就有 `dynamic_filters` 參數**
  （等值、identifier 驗證、參數化）→ 歷史查詢直接帶
  `{foreign_key: master_sc}`，**不要自己拼 SQL**，否則會繞過 view 的
  `soft_delete_column` 與 `fixed_filters`
- 每張 portal_data 表都有 `id INTEGER PRIMARY KEY AUTOINCREMENT`（建表 API 硬編）
- `create_row()` 已擴充回傳 `row_id`（取剛建立的 master id 用）

### 安全設計（改這支程式前務必讀）

- **FK 值一律 server 端覆寫**，做了雙重保險：路由層組 payload 時先剔除同名欄位，
  `save_master_detail()` 內再 `pop` 一次後賦值。
  前端能改 DevTools，讓明細掛到別人的主檔上就是資料竄改
- **`foreign_key` 必須在明細資源的 `writable_fields` 內**：
  渲染期 raise、送出端點 404。不擋的話 FK 會被 `create_row` 的白名單靜默濾掉，
  生出一堆孤兒明細列
- master 為唯讀時**忽略 `master.data` 但不報錯**——場景二/三本來就常是
  「客戶資料不能動，只加服務項目」
- `details` 上限 200 筆

### 驗收（本機實測，非推論）

| 測試 | 結果 |
|---|---|
| 場景一（無 `__sc`） | master 可填、無歷史 Tab |
| 場景二/三（`?md-widget__sc=1`） | master 唯讀、Tabs 出現「歷史記錄 4」 |
| 交易 rollback（第 2 筆明細違反 NOT NULL） | 400，**master 未建立** |
| FK 覆寫（送 `customer_id=999`） | 201，實存 `1` |
| FK 約束擋孤兒（繞過 API 直接 SQL） | `FOREIGN KEY constraint failed` |
| 偽造不存在的 `master_sc` | 404 |
| 201 筆明細 | 400 `too_many_details` |
| readonly master 竄改 `master.data` | 201 但主表未變 |
| edit 模式更新 master + 同交易新增明細 | 兩者都成功 |
| 設計器改「可編輯」→ 儲存 | portal 頁 mode 從 readonly 變 edit |

### 本機測試資料（是事實，不要重建）

```
子系統      : 8uopl3mNbDzGDUGAcNQqNe（portal path_id = ubwdM7Tp）
主細表頁    : qiHMpMCul-1KGxhU4Q7Trd（widget id = md-widget）
master view : f1hG0Do9ZGaLw2UaRdRc6H → md_customers_230517（name / phone）
detail view : ugptiXn7E0zs3t6Eb6DBqg → md_services_230517（customer_id / service / note）
portal 帳號 : p4tester / p4test123
```

`md_services_230517.customer_id` 有真的 FK 約束：
`INTEGER NOT NULL REFERENCES "md_customers_230517"("id")`

---

## 3.【已被 §2.9 取代】detail 元件：就地編輯 + 草稿

> 本節是 2026-07-29 上午的規劃，當時以為 detail 要做「送出前草稿」。
> 用戶後來澄清需求其實是**傳統主細表**（見 §2.9），
> 且明確裁決 detail 送出前只存前端、不做草稿表。
> **保留本節只為記錄決策脈絡，不要照著實作。**

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

## 4. actions 元件【2026-07-30 完成】

**§4.3 的三個裁決與 §4.3.1 的五步順序已全部落地並實測通過。**
以下 4.1~4.5 保留作決策脈絡，實作現況以 **§4.0** 為準。

### 4.0 完成內容（2026-07-30）

#### 落地的東西

| 項目 | 位置 |
|---|---|
| `action_button.permission` 改選填、`actions_widget` 加 `access_matrix` | `backend/app/pageir/schema_v3.json` |
| portal 世界的動作按鈕渲染（原本一律 `return []`） | `renderer._prepare_portal_action_buttons()` |
| 撤單端點 | `portal_public.portal_widget_cancel_submission` |
| portal action 註冊 `portal.form.cancel` | `modules/nocode_builder/__init__.py` `init_runtime()` |
| `can_cancel` 判定 | `pageir_formflow_resources._submission_row()` 的 `row["_can_cancel"]` |
| toast + 送出後回空白表單 + 撤單後回清單 | `backend/app/static/js/pageir.js`、`pageir.css` |
| 設計器 actions 面板（分組 select + 元件准入） | `ir-designer.js`、`_ir_designer_body.html` |
| 新測試 | `backend/tests/test_pageir_portal_action_cancel.py` |

基準測試 **198 → 205 passed**（新增 7 條）。

#### 定案的機制（改這塊前先讀）

- **actions widget 的 access_matrix 用 `read` + `update` 兩個 key**：
  `read` 決定 widget 看不看得到，**`update` 決定按鈕渲不渲染、端點准不准**。
  渲染端 `_prepare_portal_action_buttons()` 與撤單端點都是判 `update`，
  兩邊一致，改一邊等於開後門。
- **row action 的 record_sc 走 path placeholder**：portal 動作的 url 由
  `url_for(endpoint, record_sc=PORTAL_RECORD_PLACEHOLDER)` 產生，值是
  `__PIR_RECORD_SC__`；`renderer._action_url()` 在渲染每一列時替換成該列 `_sc`。
  平台動作維持舊契約 `?sc=<record_sc>`。**兩條路並存，不要統一掉**。
- **portal action config 的三個新欄位**：`requires_record`（需要單筆記錄，
  放在獨立 actions 區塊時該按鈕會被跳過）、`row_flag`（指向列上的底線欄位，
  falsy 就不渲染該列的按鈕，撤單用 `_can_cancel`）、`confirm`。
- **未註冊的 action_ref 在 portal 靜默跳過並記 `logger.warning`，不 raise**；
  平台世界維持 raise。N2A 驗收頁（`aq6WeXXsKU4HoA_rVCtpJK`）那兩個
  `nocode_builder.ref` 假 widget **已刪除**。
- **平台世界 button 沒有 `permission` 就不渲染**（fail-closed）。
  `_ACTIONS` 仍零註冊，設計器「平台」分組是空的，**這是預期行為**。

#### 撤單端點的准入鏈（順序不可調換）

`_resolve_portal_widget_common(..., 'update')` → widget 必須是 `actions` →
`check_widget_write_access(access_matrix, 'update')` → **widget 的 buttons 裡
必須有一顆解析得到、且 endpoint 正好是本端點的 portal action**（registry 不可繞過）
→ `_owned_submission(record_sc, ctx)` 三重過濾 → `wi.status == 'RUNNING'`。
前四關任一失敗一律 404 + `_log_portal_write_denied(reason=)`；
狀態不符回 409 `not_cancellable`。

**撤單的擁有權判定絕不可用 `applicant_secure_code`** —— portal 世界那一律是
企業公用帳號（`nocode-svc-<org>`），拿它判定等於所有 portal 用戶都是發起人。

軌跡寫 `FwApprovalRecord(node_id='FORCE_END', action='FORCE_END')`，
`approver_secure_code` 只能塞 `fi.applicant_secure_code`（portal 帳號不存在於
平台 `users` 表），真正的操作者記在 `approver_name`（`portal:<display_name>`）
與 `comment`（含 `user_ref=`）。

#### 這一輪新踩的坑（會再踩）

1. **`URLSearchParams.keys()` 不能用 `Array.prototype.slice.call()`** ——
   迭代器沒有 `length`，slice 回空陣列，於是「撤單後清掉 `*__sc=`」
   一個參數都沒刪掉，畫面看起來成功但仍停在 detail。必須 `Array.from()`。
   **症狀極不明顯**（動作真的成功了，只是網址沒清），curl 測不出來。
2. **formio 的 submit button 若 `input: true`，送出 payload 會多一個 `submit: true`
   欄位** → 後端 `extract_schema_field_keys` 白名單擋下，回 400 `unknown_field`。
   驗收頁加送出按鈕時要寫 `"input": false`。
3. 驗收頁 `FORMTEST00000000000001` 原本的 form schema **沒有送出按鈕**
   （歷來都用 curl 送件），本輪已補上（`input: false`）。

#### 順手發現、**尚未修**的既有問題（與 actions 無關）

- **portal 頁沒有載入 `timezone.js`**（`typeof BkTime === 'undefined'`），
  所以表格「捲動載入」的列時間直接印 API 回的 naive UTC ISO 字串
  （`2026-07-28T20:23:...`），與伺服器端渲染的第一頁（`2026-07-29 04:23`）不一致。
  違反 TZ-01。修法是 portal base 模板載入 timezone.js + appendRows 改用
  `BkTime.format()`，但牽涉 portal 世界的時區來源，本輪未動。
- **內容不足一屏時，無限捲動載不到第 3 頁以後**：sentinel 一直在視窗內，
  IntersectionObserver 不再觸發回呼。page_size 小、資料少時可重現。

#### 本機驗收資料（是事實，不要重建）

- 驗收頁 `FORMTEST00000000000001` 已有 `acts-1`（actions widget，一顆撤單按鈕，
  access_matrix read+update 皆 GUEST），`subs-1.row_actions_ref = 'acts-1'`。
- 撤單需要 `wi.status == 'RUNNING'`；該 mapping 的流程會很快跑完變 COMPLETED，
  要測就照 §4.3.2 的 SQL 手動改 status + 插一筆 WAITING 佇列。
- 測完記得清 queue 記錄與自動產生的子系統
  （`dc_sub_systems.provision_serial_number` 對得上送件序號）。

#### 瀏覽器實測項目（VERIFY-01，全部通過）

列動作只出現在 RUNNING 那一列、撤單 URL 帶 nginx 前綴、confirm → 撤單 →
toast「已完成」→ 800ms 後清掉 `*__sc=` 回清單、狀態變「已退回」、
待辦節點 CANCELLED、留下 FORCE_END 軌跡；表單送出 → toast「已送出」+
欄位清空 + 不 reload；捲動載入的第 2 頁列也有撤單按鈕且 record_sc 正確；
設計器面板 select 初次渲染正確（FRONT-08）、儲存後 `permission` 空值被清掉。
IDOR（撤別人的單）、打非 actions widget、缺 CSRF、重複撤單 → 404/404/400/409。

### 4.1 為什麼放最後

用戶：「這個『送出或確認』的行為應該可當 actions 的場景」。
form 的送件、detail 草稿的 submit，都是 action。
先把這兩個具體場景做出來，actions 的介面（參數、回傳、錯誤處理、權限）
才有真實需求可依循。

### 4.2 現況（2026-07-29 晚更新，先前的「registry 零註冊」已過時）

**portal 側的 action registry 已經存在並在用**（A 案，見 §1.4）：

```python
# backend/app/pageir/registry.py
_ACTIONS         # 平台世界，權限走 capability_service
_PORTAL_ACTIONS  # portal 世界，權限走 widget access_matrix
register_portal_action / get_portal_action / list_portal_actions
```

目前只註冊了一個，在 `modules/nocode_builder/__init__.py` 的 `init_runtime()`：

```python
register_portal_action('portal.form.submit', {
    'endpoint': 'nocode_public_portal.portal_widget_submit',
    'update_endpoint': 'nocode_public_portal.portal_widget_update_submission',
    'state_resolver': resolve_submission_state,
})
```

**平台側 `_ACTIONS` 仍然零註冊**，所以 `/api/pageir/meta` 的 `actions` 是空陣列。

### 4.2.1 actions widget 本身仍然完全沒做

**這是 actions 階段真正要做的東西，前面幾輪刻意沒動：**

```python
# renderer.py _prepare_action_buttons()
if get_render_context().get("world") == "portal":
    return []          # portal 的動作按鈕全部消失，至今未改
```

`table.row_actions_ref` 指向 actions widget，因此列動作在 portal 也還是空的。
（列**連結**已經能用了——那是 `row_link_ref`，見 §2.9 前的 commit，
與 actions 無關，不要混淆。）

### 4.2.2 已知的硬阻擋：`action_button.permission` 在 portal 世界無意義

schema 的 `action_button` 目前是：

```json
{"required": ["id","label_i18n","permission","action_ref"],
 "properties": {"style": {"enum": ["primary","secondary","danger"]}}}
```

`permission` 是**平台 permission code**，`_prepare_action_buttons()` 用
`capability_service.user_can(button["permission"])` 判定。
portal 世界沒有平台身分，這條路走不通。

依 §1.4 已定的 A 案（權限吃 widget `access_matrix`），合理的做法是：
`actions_widget` 加 `access_matrix`，portal 世界改用它判定，
`permission` 變成只在平台世界有意義的選填欄位。
**但 `permission` 目前是 `required`，改成選填要同時確認既有頁面沒有踩到。**

### 4.3 用戶已裁決（2026-07-29 晚，三題全部有答案，可直接動工）

#### 產品定位（先讀這段，它決定所有取捨）

> 「並無意建立第二套複雜的表單介面，就只是讓外部用戶在 web 上填寫資料。
> 比如客服申請、訂票訂位的介面，當然能查自己的歷史並取消（就是撤單）。」

→ **portal 這一側是「簡化版的表單中心」**。功能對齊 `/forms/center`，
但介面要簡單。不要把表單中心的複雜度整套搬過來。

#### 裁決一：撤單 = portal 版的「強制結束」

> 「應該會有一個未結束的表單清單（**限填單人自己送出的才能撤單**），
> 對應的是 `/beakplatform/forms/center` 的 **[強制結束]**。
> 那個 [追蹤中-我發起的表單] 加子系統代碼等 nocode 的那串，
> 就能組合當前 nocode 的用戶的 SQLite 內的帳號。」

**照抄的對象已查證**：`modules/form_workflow/api/fc_admin.py:24`
的 `force_end_workflow()`。它做三件事：

```python
WorkflowEngine.cancel_pending_nodes(wi.secure_code)       # 取消未完成節點
WorkflowEngine.complete_workflow(wi.secure_code, status='CANCELLED',
                                 end_message=f'由 {operator} 強制結束')
FwApprovalRecord(node_id='FORCE_END', action='FORCE_END', ...)  # 留軌跡
```

- **資料完全保留**（只改 status + 留一筆軌跡），符合用戶說的
  「資料會保存直到 DBA 刪除」
- 前置條件：`workflow_instance.status == 'RUNNING'`

**portal 版唯一要換掉的是權限判定。** 原版是：

```python
is_applicant = form_instance.applicant_secure_code == current_user.secure_code
```

portal 世界的 `applicant_secure_code` **一律是企業公用帳號**
（`nocode-svc-<org>`），拿它判定等於「所有 portal 用戶都是發起人」——
這是**致命的**，一定要換成：

```python
wi.nocode_sub_system_sc == <當前子系統>
and wi.nocode_user_ref == nocode_user_ref(sub_system_sc, portal_user)
```

也就是**沿用 `_owned_submission()` 那條三重過濾**
（`pageir_formflow_resources.py`），不要另寫一份。
用戶那句「加子系統代碼等 nocode 的那串就能組合當前 nocode 的用戶」
講的就是這件事。

#### 「未結束的表單清單」怎麼來

`formflow:submissions` 資源已經是「我發起的表單」了（§1.4.1），
但目前**沒有帶出「這筆能不能撤單」**。要加一個欄位，
比照表單中心 `fc_my_forms.py:161` 的 `can_force_end`：

```python
can_cancel = (wi.status == 'RUNNING')   # 擁有權已由三重過濾保證
```

（表單中心還要判 `applicant == current_user or is_org_admin`，
portal 這邊三重過濾已經涵蓋，不必再判。）

#### 裁決二：action 執行後的頁面行為

| 情境 | 行為 |
|---|---|
| **新填表單送出** | 底下浮現「填寫成功／失敗」訊息，**3 秒自動關閉**；同時**回到剛送出的那張表單的空白表單**，方便連續建立多張 |
| **撤單** | 回到「追蹤中-我發起的表單」清單 |

**這會改到已經完成的 form 元件行為。** 目前 `pageir.js` 的送出成功是
`alert(t('已送出'))` + `location.reload()`，兩點都不符：
alert 要手動關、reload 會保留 `?<widget>__sc=` 而不是回到空白表單。

toast 可照抄表單中心的
`modules/form_workflow/static/modules/form_workflow/js/fc-utils.js:108`：

```javascript
showToast(message, type = 'success') {
    this.toast = { show: true, message, type };
    setTimeout(() => { this.toast.show = false; }, 3000);
}
```

「回到空白表單」= 清掉 `?<widget_id>__sc=` 參數並重置 form.io 的 submission，
**不要整頁 reload**（reload 會讓連續建單的節奏斷掉，也違反「方便連續建立多張」）。

#### 裁決三：`action_button.permission` 改成選填 —— **接受**

依 A 案（§1.4）把 `actions_widget` 加上 `access_matrix`，portal 世界用它判定；
`permission` 從 `required` 移出，只在平台世界有意義。

**既有資料已查過（2026-07-29）**，結論是改成選填**沒有相容性風險**，
但有另一個坑：

`dc_page_layouts` 只有一頁含 actions widget ——
`aq6WeXXsKU4HoA_rVCtpJK`（N2A 驗收頁，掛在子系統 `8uopl3mNbDzGDUGAcNQqNe`），
裡面有兩個：

```json
{"id": "actions-1", "type": "actions", "buttons": [
  {"id": "btn-1", "action_ref": "nocode_builder.ref",
   "permission": "nocode_builder.view", "style": "secondary",
   "label_i18n": {"zh-TW": "執行", "en": "Run"}}]}
// actions-2 內容相同
```

- `permission` 改選填 → 這兩個仍帶著該欄位，**照樣合法**，零風險
- **但 `action_ref` 是 `nocode_builder.ref`，這個 ref 從來沒被註冊過**。
  目前不會爆，是因為 `_prepare_action_buttons()` 在 portal 一律回 `[]`
  根本沒去解析。**一旦 actions 階段讓 portal 開始解析 action_ref，
  這頁就會撞到「未註冊」而 raise → 整頁 422。**

  動工時要先決定：未註冊的 ref 在 portal 是 raise 還是靜默跳過。
  建議**靜默跳過該按鈕並記 log**（與 `_portal_form_submit_url()` 的
  fail-closed 一致：設定不完整就是不給那個能力，而不是整頁掛掉），
  平台世界維持現行的 raise 不變。
  順手把 N2A 驗收頁那兩個 widget 清掉或補上真的 ref 也可以。

### 4.3.1 建議的實作順序

三個裁決之間有依賴，照這個順序做最省事：

1. **`actions_widget` 加 `access_matrix`、`permission` 改選填**
   （schema + `_prepare_action_buttons()` 依 world 分流）
   —— 這是地基，不做的話 portal 一個按鈕都渲染不出來
2. **`formflow:submissions` 加 `can_cancel` 欄位**
   —— 撤單按鈕要靠它決定顯不顯示
3. **撤單 action**（註冊 portal action + 端點，照抄 `force_end_workflow`
   但換掉權限判定）
4. **送出後行為改成 toast + 回空白表單**
   —— 這條獨立於 1~3，可以先做也可以最後做，但**不要漏掉**，
   它是既有 form 元件的行為變更，不是新功能
5. 設計器 UI（actions widget 的按鈕清單編輯 + 准入）

### 4.3.2 冷讀補洞（2026-07-30，codex read-only 審核列出 15 個猜測點）

以下**全部已定案**，動工時照做即可；只有標 ★ 的三條是「建議」，
用戶可推翻，但沒有異議就照建議做，不要停下來問。

#### 命名與端點（原本沒定，現在定了）

| 項目 | 定案 |
|---|---|
| 撤單 action ref | `portal.form.cancel`（與 `portal.form.submit` 同族） |
| 撤單端點 | `POST /public/portal/<path_id>/api/pages/<page_sc>/widgets/<widget_id>/submissions/<record_sc>/cancel` |
| endpoint 名稱 | `portal_widget_cancel_submission` |
| request body | 不需要（識別碼全在 URL），有帶也忽略 |
| 成功回應 | `{"success": true, "data": {"execution_code": "..."}}`，200 |
| 失敗回應 | `{"success": false, "error": "<safe_code>"}`；權限／存在性一律 404 |

**回應形狀與既有 portal API 完全一致**（`success` + `error`），
前端 toast 依 `success` 決定顯示成功或失敗訊息。

#### 撤單作用在哪一筆

**`fw_form_instances.secure_code`** —— 也就是 `formflow:submissions`
每一列**既有的 `_sc`**。不必為此新增欄位，`can_cancel` 是唯一要加的。

後端拿到 `record_sc` 後走 `_owned_submission(record_sc, ctx)`
（`pageir_formflow_resources.py`）取得 `(wi, fi)`，三重過濾已在裡面。

#### row action 怎麼把「哪一列」傳給端點 —— 既有契約，不要重新發明

`renderer._action_url()`（第 769 行）已經定好了：

```python
def _action_url(url: str, record_sc: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'sc': record_sc})}"
```

模板端是 `pir_action_url(button.url, row.get('_sc'))`，
產生 `<action_url>?sc=<record_sc>`。**參數名就是 `sc`**。

→ 撤單端點若走 row action，`record_sc` 可以從 URL path 拿，
也可以沿用這個 `?sc=`。**建議走 path**（與 `submissions/<record_sc>` 的
既有形狀一致），並讓 actions widget 的 button 產生的 url 直接帶 path。

#### ★ actions widget 的 access_matrix 語意

**建議：整個 actions widget 共用一組 `access_matrix`**，
與 table / detail 一致，button 層不再細分。理由是元件准入 UI 已經是
widget 級的 macro，button 級會讓設計器面板複雜度爆掉，
而用戶明確要「簡化版的表單中心」。

撤單另外由 **後端強制的 `can_cancel` 二次判定**（`wi.status == 'RUNNING'`
＋三重過濾）把關，所以 widget 級權限夠用。

#### ★ 未註冊的 action_ref 在 portal 的行為

**建議：靜默跳過該按鈕並記 `logger.warning`，不 raise。**
與 `_portal_form_submit_url()` 的 fail-closed 一致——設定不完整就是不給那個能力，
而不是整頁掛掉。**平台世界維持現行的 raise 不變。**

不這樣做的話，N2A 驗收頁（`aq6WeXXsKU4HoA_rVCtpJK`）那兩個
`nocode_builder.ref` 會讓整頁 422。

#### ★ N2A 驗收頁的兩個假 actions widget

**建議：直接刪掉。** 它們是 N2A 階段的殘留，`action_ref` 從未註冊過，
留著只會在每次改 actions 時變成假警報。刪之前先確認該頁沒有別的驗收用途。

#### 撤單後「回到追蹤中清單」怎麼實作

portal 世界的「追蹤中-我發起的表單」就是**綁 `formflow:submissions` 的
table widget**，實務上與撤單按鈕同頁。所以：

**撤單成功後清掉網址上所有 `*__sc=` 參數並 reload**，
畫面自然就回到清單狀態（detail / form 區塊會因為沒有 `__sc` 而回到空狀態）。
不需要另外設定跳轉目標頁。

#### toast 放哪

`pageir.js` 動態建立一個 `.pir-toast` 容器 append 到 body，
CSS 寫進 `backend/app/static/css/pageir.css`（該檔已存在，主細表的 Tabs 就在裡面）。
**不要**在模板寫死容器——Page IR 的頁面組成是動態的。

3 秒自動關閉，行為照抄
`modules/form_workflow/static/modules/form_workflow/js/fc-utils.js:108`。

#### 設計器 UI 的資料模型

**既有的 actions widget 面板已經有按鈕清單編輯**
（`ir-designer.js` 的 `addActionButton()`，第 835 行），照它擴充即可：

```javascript
widget.buttons.push({
    id: this.nextId('btn'),
    label_i18n: { 'zh-TW': tr('執行'), en: 'Run' },
    style: 'secondary',
    permission: 'nocode_builder.view',        // 改選填後這行要拿掉
    action_ref: this.meta.actions[0] || 'nocode_builder.ref',   // 要改成分組下拉
});
```

要改的兩處：
- 預設值不要再塞 `permission`（改選填後塞了反而是垃圾欄位）
- `action_ref` 改成 `<optgroup>` 分組 select，來源
  `meta.portal_actions`（子系統 Portal）+ `meta.actions`（平台），
  **照 form widget 送出動作那個下拉抄**（上一輪做的，同檔案）

准入用既有 macro：`{{ access_matrix.render('actionsAccessActions', ...) }}`。

#### 平台世界維持現狀

`_ACTIONS` 仍然零註冊，所以設計器的「平台」分組會是空的 ——
**這是預期行為，不是 bug**，不要為了填滿它去註冊假 action。

#### 撤單的驗收頁

**用既有的 `FORMTEST00000000000001`**（它已經有 `subs-1` table 綁
`formflow:submissions`），加一個 actions widget 並把 `subs-1.row_actions_ref`
指過去即可。不必新建頁面。

該頁 `p4tester`（`u:1`）目前有數筆送件，但**多數已 COMPLETED**——
撤單需要 `status == 'RUNNING'` 的資料，驗收前先送一筆新的：

```bash
BASE=http://192.168.0.16:7000/beakplatform
curl -s -c p4.txt -X POST "$BASE/public/portal/ubwdM7Tp/login" \
  -d 'username=p4tester&password=p4test123'
T=$(curl -s -b p4.txt -c p4.txt "$BASE/public/portal/ubwdM7Tp/p/FORMTEST00000000000001" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -s -b p4.txt -X POST \
  "$BASE/public/portal/ubwdM7Tp/api/pages/FORMTEST00000000000001/widgets/form-1/submit" \
  -H "X-CSRFToken: $T" -H 'Content-Type: application/json' \
  -d '{"textField":"撤單驗收用"}'
```

**注意**：這個 mapping 是「子系統開發申請」，流程會跑到底並**真的建出子系統**
（`dc_sub_systems.provision_serial_number` 對得上送件序號），
而且會很快變成 COMPLETED。要測 RUNNING 狀態就得手動插一筆 WAITING 佇列：

```sql
UPDATE fw_workflow_instances SET status='RUNNING' WHERE execution_code='<你的>';
INSERT INTO fw_node_execution_queue (secure_code, org_secure_code,
  workflow_instance_secure_code, form_instance_secure_code, node_id, node_type,
  node_name, node_config, status, priority, scheduled_at, is_deleted,
  created_at, updated_at)
VALUES ('CANCELTEST000000000001', '_9c8TewkRkCBEf3XsUdqeF', '<wi_sc>', '<fi_sc>',
  'node-Approve-1', 'Approve', '部門主管審核', '{}'::json, 'WAITING', 10,
  now(), false, now(), now());
```

測完記得清掉 queue 記錄與自動產生的子系統
（`UPDATE dc_sub_systems SET is_deleted=true WHERE provision_serial_number='...'`）。

### 4.4 可以直接沿用的模式（不要重新發明）

前面三輪建立的東西，actions 階段照抄即可：

| 需求 | 照抄哪裡 |
|---|---|
| portal 端點的准入鏈 | `portal_public.py` 的 `portal_widget_submit`（共用前置 `_resolve_portal_widget_common`） |
| registry 不可被繞過 | 送出端點的 `submit_action_ref` 檢查（widget 沒設動作 → 直打 URL 也 404） |
| 公開端點限流 | `@limiter.limit('10 per minute; 100 per hour')` |
| 拒絕一律 404 + `_log_portal_write_denied(..., reason=)` | 同上 |
| 授權判定不可吃 VariableService 快取 | `pageir_formflow_resources.is_submission_editable()` 的註解 |
| 只能取到自己的資料 | `_owned_submission()` / `get_editable_submission()`（三重過濾在 SQL WHERE） |

### 4.5 落地時要補的驗收

第一個 action 落地時要補 E2E（`docs/handoff_nocode_n1_n5.md` §6.8 登記在案）。

**驗收方式的教訓**：涉及「使用者要點擊的連結或按鈕」時，
**必須用瀏覽器驗，不能只用 curl**。
Page IR 的排序連結從第一版起就缺 nginx 前綴、點下去 404，
一直沒被發現，就是因為歷來都用 curl 帶完整路徑測
（已於 2026-07-29 修正，見 `renderer._self_url()`）。

---

## 4.6 測試基準（2026-07-29 晚）

```bash
cd /opt/BeakPlatform-dev/backend
../venv/bin/python -m pytest tests/test_pageir_*.py tests/test_portal_*.py \
  tests/test_sitemap_access_matrix.py -q
```

**198 passed**（§5 底下寫的 155 是 2026-07-28 的舊基準，已過時）。

本輪（form → 簽核狀態 → 三狀態 → 列連結 → 主細表）的 commit：

```
1dc8bb5d  form 送件進簽核流程
88ac64e0  簽核狀態可見（formflow:submissions）
9ce87ac3  form 三狀態 + 流程變數寫入位置修正
f59d6957  列連結導覽 + 自連網址缺 nginx 前綴修正
32a4d15a  主細表後端
de383028  主細表設計器
```

---

## 5. 【2026-07-28 舊基準】這一輪已完成、可直接依賴的東西

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
