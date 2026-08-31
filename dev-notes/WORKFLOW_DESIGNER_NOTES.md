# 流程設計器與 graph 操作備忘

> 2026-08-30 從 `CLAUDE.md` 移出（三個小節共 90 行）。
> **用腳本或 API 改 `fw_workflow_templates.graph`、新增節點型別或分類、
> 或要發行（publish）配對之前，整份讀完。**
> 流程引擎的執行語意（Branch/End/skip_advance）仍留在 `CLAUDE.md`。
> 節點盤點見 `NODE_TEST_INVENTORY.md`。

---

## 流程設計器的節點清單與分類（2026-08-24 PF-84 期間釐清）

**`require_system_admin=true` 在本平台的實際效果是「沒有任何帳號看得到」**，
不是「限系統管理員」：`/api/workflows/data/node-definitions` 掛
`@module_access_required('form_workflow')`，而唯一的 SYSTEM_ADMIN
（`admin@system.local`，屬系統企業）沒有這個模組的合約，打該端點回 **403**。
所以 `DecisionWriter` 從 2026-05-09 上線到 2026-08-24 之間，**左側工具列對任何人都不存在**。
（已於 migration 114 改成 false，暴露面是流程設計頁雙鑰匙放行的 ORG_ADMIN 與
`FLOW_DESIGNER`。判斷理由寫在該 migration 的註解裡。）

**新增一個節點分類要改四個地方，漏任一處的症狀都是「類別不出現」且不報錯**：

| 位置 | 內容 |
|---|---|
| DB `workflow_node_definitions.category` | 中文分類名（例 `資安處置`） |
| `api/workflows.py::get_node_definitions` 的 `category_map` | 中文 → key（`security_ops`） |
| `workflow-designer-init.js` | `CATEGORY_NAMES`、`CATEGORY_ICONS`、**`categoryOrder`** 三個都要；沒列進 `categoryOrder` 的分類會被**靜默略過** |
| `workflow-designer.css` | `.palette-node.<key>`（沒加只是沒顏色，不影響功能） |

**畫布上的節點 id 有兩種來源，格式不同是正常的**：

| 來源 | id 長相 |
|---|---|
| 建置腳本直接寫 graph JSON（如 `od_workflow_graphs.py`） | 作者自取的語意化字串 `node-Decision-confirm` |
| 設計器拖拉（`wf-dnd-nodes.js::addNode`） | `` `node-${型別}-${流水號}` `` |

流水號 `nodeCounter` 是**全域共用不分型別**，載入既有流程時由
`wf-render.js` 掃描所有節點 id 的數字尾碼取最大值續編（所以會跳號，那是防撞號）。
**id 建立後固定不變**——連線靠它錨定，改節點名稱不會改 id。

**要驗防禦決策面板時開這個**（beluga，五顆 DecisionWriter 節點涵蓋
block／unblock／observe 三種 action）：

```
http://192.168.0.16:7000/beakplatform/forms/workflows/7LJRvpSPUYcmK1M1wcOTzY
```

另外兩個含該節點的流程：`8bhmC3N-TDYYT7W5s0bYC3`（SOC 團隊版，2 顆）、
`1bBpvNh6bWi5lVZwBz2NHQ`（標準版，1 顆）。**畫布是 canvas，DOM 點不到節點**，
自動化驗收一律 `cy.$('#<node-id>').emit('tap')` 觸發面板，面板本身才是 DOM。

## 用腳本產生流程 graph 時的三個坑（2026-08-20，全部實際踩到）

**一、`graph` 與 `cytoscape_config` 兩個欄位都要寫。**
`fw_workflow_templates` 有兩個欄位存同一份圖：流程引擎讀 `graph`，
**設計器讀 `cytoscape_config`**（`wf-render.js`：
`workflow.cytoscape_config || workflow.graph`，前者優先）。
設計器自己存檔時是同一份物件寫進兩欄（`wf-save.js:488-489`）。
只寫 `graph` 的症狀是**流程跑的是新版、設計器畫的是舊版，而且不報錯**——
看起來就像「我的流程沒存到」或「節點裡沒有值」。
（腳本產生、從未經設計器存過的流程 `cytoscape_config` 是 NULL，會 fallback 到
`graph`，所以不會有這個症狀；**被設計器存過一次之後才會開始不同步**。）

**二、載入既有流程時 pan 不是固定值，座標排在哪都不保證看得到。**
實測同一個流程連續重新載入，pan 得到 -143.75 / -193.75 / -275 / -350。
原本只有「版本 AA 且 revision 0」的新流程才 `cy.fit()`，其餘一律沿用當下視野，
所以座標離 pan 較遠的節點就直接在畫面外。2026-08-20 已在 `wf-render.js` 補
「載入後若有節點不在視野內就自動 fit」（本來就完整可見的流程不動視野，
避免大流程被 fit 到看不清字）。

**三、節點 icon 不要用 `f'{ICON_BASE}/{node_type.lower()}.svg'` 硬推。**
檔名與型別名不是一對一（AiAgent 原本借用 `sqlexecutor.svg`，2026-08-20 才補
`aiagent.svg`）。一律從 `workflow_node_definitions.icon` 讀該型別登記的圖示。

範例腳本：`scripts/examples/provision_node_demo_flows.py`（兩個節點示範流程）。

## form_workflow 發行（publish）陷阱
- `POST /api/mappings/<sc>/publish` 以表單/流程模板的 **version+revision** 判斷有無變更；
  直接改 `fw_workflow_templates.graph`（SQL 或 PUT API）**不會** bump revision，
  publish 會回「版本未變更」並沿用舊快照
- 解法：改完 graph 先 `UPDATE fw_workflow_templates SET revision = revision+1 WHERE ...` 再 publish
- intake / 表單中心都只讀 `fw_published_form_workflows` 最新 Published 快照，改模板不重發行等於沒改
- 流程變數：流程編號（OD-YYYYMMDD-NNNN）是 `${wi.exec_code}`；`${wi.code}` 是 workflow instance 的 secure_code，
  沒有 `${wi.execution_code}` 這個變數（替換結果為空字串）

**`FwPublishedFormWorkflow.suspend()` / `reopen()` 內部有 `db.session.commit()`**
（`modules/form_workflow/models/published_form_workflow.py:168`，2026-08-28 踩到）。
在「呼叫端負責 commit」的服務或 seed 函式裡呼叫它，會把上游尚未完成的交易
**從中間切開**——例如建立企業的流程呼叫出廠 seed、seed 又呼叫 suspend()，
企業只建了一半就先被 commit。這類地方要自己展開那三行（含 `status == 'Archived'`
的檢查），範例見 `backend/app/defaults/api_key_request_defaults.py` 的
「刻意不呼叫 existing.suspend()」註解。**看到那段不要當成重複的死碼改回去。**

**出廠預設的表單／流程在 `backend/app/defaults/api_key_request_defaults.py`**，
建企業時由 `organization_service.create_organization()` 與
`init_system_organization()` **兩處**呼叫（後者不走前者）。
`scripts/examples/provision_api_key_request_flow.py` 是它的 CLI 外殼、
反過來 import defaults——**要改表單欄位或流程 graph 一律改 defaults 那一份**，
改腳本不會生效。既有企業由 `scripts/migrations/116_seed_api_key_request_flow_existing_orgs.py` 補。

## 樹系圖有兩份幾乎相同的實作（2026-08-31 PF-201 期間發現）

同一張「流程樹系圖」在兩個地方各有一份渲染程式碼，**改一份另一份不會跟著變，
而且兩邊畫出來一模一樣、看不出是哪一份**：

| 入口 | 實作 | 型態 |
|---|---|---|
| 清單頁 `/forms/workflows/` 每列的 [樹系圖] | `workflow-list.js::_renderTree()`（`openTree(w)` 開） | 頁內 overlay，**不換頁** |
| 設計器左側「流程樹系 → 開啟樹系圖」 | `fw-workflow-tree.js::_renderTree()` + `workflow_tree.html` | 獨立頁 `/forms/workflows/<sc>/tree` |

兩份的 `renderCard()` / `renderChildren()` 是複本（連 `STEM_X=111`、`CARD_MID=85`
這些常數都一樣）。動其中一份時記得問「另一份要不要一起動」。

另有第三份**不同**的東西不要混淆：設計器左側面板那個文字清單是
`wf-tree.js::renderFlowTree()`（純文字縮排樹，點了走 `switchToWorkflow()` 同頁切換）。

### 三個入口的「返回 / 離開」語意（2026-08-31 PF-201 定版）

- 獨立樹系圖頁的返回按鈕**依來源決定**：`?from=designer&sc=<設計器那張的 sc>`
  就回那張設計圖，沒有參數（＝從清單來）就回清單。判斷在後端
  `web/__init__.py::workflow_tree()`（算出 `back_url` 傳給模板），
  `sc` 過 `_SECURE_CODE_RE` 白名單
- 卡片連結帶 `?from=tree&root=<根流程 sc>`，設計器的「儲存並返回」
  （`wf-workflow-crud.js::saveAndClose()`）讀這組參數決定回樹系圖或回清單。
  **獨立頁的根節點也帶**（回獨立樹系圖頁），**清單 overlay 的根節點刻意不帶**
  （overlay 本來就疊在清單上，回清單才對）
- 設計器內切換流程（左側文字樹）與「開啟樹系圖」一律**先無提示自動儲存**再走，
  存檔失敗就停在原地並在狀態列報錯（`wf-tree.js::autoSaveBeforeLeave()`）。
  `saveWorkflow()` 因此改成**回傳 boolean**——在此之前它 catch 掉所有錯誤、
  一律回 undefined，而且用 `if (data)` 判斷成功，**後端回 4xx 也會顯示「已儲存」**

### 自動儲存會連帶生成縮圖，而縮圖綁在「當下的 currentWorkflowId 與 cy」上

`saveWorkflow()` 成功後排 `setTimeout(..., 100)` 生成縮圖。設計器裡按儲存按鈕時
畫布不會變，所以一直沒事；但「切換流程時先自動儲存」讓呼叫端在**存檔後幾毫秒內**
就換掉 `currentWorkflowId` 與 `cy`，100ms 後那支縮圖函式看到的已經是**下一張流程**：

```
A 存檔 10:55:31.468  →  縮圖 PUT 打到 B  10:55:31.690（差 222ms）
結果：A 的縮圖沒更新，B 被寫入一張不屬於它的圖
```

修法是在存檔成功的當下**同步** `cy.png()` 把畫面截下來、同時記住流程 id，
再把兩者一起交給 `generateAndSaveThumbnail(targetWorkflowId, prefetchedPngRaw)`
（兩個參數都可省略，儲存按鈕那類路徑維持原行為）。
**日後若再加「離開前自動儲存」的路徑，記得縮圖也要跟著綁 id。**

### 這裡曾經有一段永遠不會執行的死碼

`wf-tree.js::switchToWorkflow()` 原本寫 `typeof hasUnsavedChanges === 'function'
&& hasUnsavedChanges()`，但 `hasUnsavedChanges` 是 `wf-workflow-crud.js` 的
**布林變數**（`let hasUnsavedChanges = false`），`typeof` 恆為 `'boolean'`——
所以那個「確定要切換嗎」的 confirm **從來沒有跳過**，切換流程一直是靜默丟棄變更。
待辦卡當時記的是「會跳確認框」，與實際不符。判斷這類跨檔案共享狀態時，
先確認它是變數還是函式（這些 js 是各自 `<script src>`，共享 script-level scope，
`function` 宣告掛得到 `window`、`let`/`const` 掛不到）。

## 子流程同名：DB 不擋，改由兩個 API 入口擋（2026-08-31 PF-202）

`fw_workflow_templates` 的唯一索引**只有 `secure_code`**（`code` 是非唯一索引、
`name` 連索引都沒有），所以同一個父流程下可以建出兩個同名子流程，
而清單與樹系圖都只顯示 `name` ——使用者看到兩個一模一樣的項目，
改其中一個的名字就會覺得「兩個都變了」。

**不加 DB 唯一約束**（跨流程樹同名是合理的，兩棵樹各有一個「通知」子流程），
改成在兩個入口擋，都走 `api/workflows.py::_find_duplicate_subflow_name()`：

| 入口 | 位置 | 比對範圍 |
|---|---|---|
| 建立子流程 | `create_subflow()` | 同一 `parent_workflow_secure_code` 底下 |
| 改名 | `update_template()`（只在 `is_subprocess` 時） | 同上；通用子流程（無 parent）則比同企業所有通用子流程 |

衝突一律回 **409** + `error` 訊息，前端 `createNewSubflow()` 與
`updateWorkflowInfo()` 會 alert 出原因（狀態列訊息容易被忽略）。
**主流程不受此限**——同名主流程沿用既有行為，沒有改。

**新增任何「會建立或改名子流程」的路徑時要一併掛這道檢查**，
漏掛不會報錯，症狀就是清單上又出現兩個分不出來的同名項目。

**兩條刻意不擋的路徑**（反向檢查時查過，都在程式碼留了註解）：

| 路徑 | 為什麼不擋 |
|---|---|
| `POST /api/form-workflow/workflows/batch/import` | 還原語意，去重只看 `code`；擋名稱會讓合法備份檔匯不進來 |
| `POST /data/templates/<sc>/save-new-version` | 另存新版本來就是同名不同 `version`（AA → AB） |

兩者建出的同名項目靠上面說的 code 後綴辨識。

已經同名的既有資料不會被回頭清理，所以三處清單（子流程面板、設計器左側文字樹、
樹系圖卡片×2 份）**在偵測到同名時會把 code 一起顯示**成
`sub_C_L2_2（SF0EADE7C5）`；不同名時維持只顯示名稱。判定以 `secure_code` 去重，
同一個子流程被引用兩次不算同名。

### 順帶修掉的：`delete_subflow` 一定回 500

`for _ in range(10)` 把 `from flask_babel import gettext as _` 覆寫成 int，
函式尾端的 `_('已刪除 %(count)s 個子流程')` 直接 `TypeError: 'int' object is
not callable`。**軟刪除已經 commit 成功才炸**，所以症狀是
「前端說刪除失敗、重新整理卻發現真的刪掉了」。同檔 `list_available_subflows()`
有同樣寫法（該函式尾端剛好沒用到 `_()` 才沒爆），兩處都改成 `for _hop in range(10)`。

## End／SubFlow 的 PF-200 語意（2026-08-31）

- `End(finish_mode='cancel')`＝**中止**：終態 CANCELLED（主流程連表單）。
  正常完工用 `detach`。子流程裡 cancel 只收自己＋下層（subtree），上一層照常跑。
- SubFlow 節點 config 新增兩項（面板「執行控制」卡）：
  - `max_iterations`：迴圈上限，計數在含節點那一層的流程變數 `<節點ID>_runs`
  - `resultRouting`：`{'completed': [edgeId], 'cancelled': [edgeId]}`，
    依子流程結束方式選出邊；未配置＝所有出邊
- 子流程結束會寫父層變數 `${v.<節點ID>_result}`（completed/cancelled）與 `_child`。
- **queue 的 node_type 逐字複製 graph，設計器寫的是 `Subflow`（小寫 f）**——
  引擎端比對一律 `func.lower()`，寫死 `'SubFlow'` 會靜默 miss。
- 完整定案：`dev-notes/handoff_end_subflow_cancel_20260831.md` 第十節。
