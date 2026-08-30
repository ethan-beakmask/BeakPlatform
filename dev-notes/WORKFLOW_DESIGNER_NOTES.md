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
