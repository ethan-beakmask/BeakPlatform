# 交接：End 節點合併 Abandon ＋ 子流程 cancel 範圍修正

建立 2026-08-31。**動工前把本檔讀完**，裡面有三個「不知道就會做出錯誤實作」的事實。
上游脈絡：`dev-notes/NODE_TEST_INVENTORY.md` 的「附：子流程的結束語意」一節
（那節記的是**現況行為**，本檔記的是**要改成什麼**）。

## 目標（Ethan 2026-08-31 定調）

1. **把 Abandon 併進 End，然後把 Abandon 刪除乾淨**
   Abandon 是「End 還沒有三模式」時代的舊節點，後來被隱藏，最近某個 session 又把它顯示出來造成誤導。
2. **End 的 `cancel` 模式放在子流程時，只中斷「子流程自己與它的下層」，不得影響上一層。**
3. 中斷之後要**回應給上一層一個「本次是 cancel」的訊息**（目前上一層只會收到一個沒有區別的 SUCCESS）。
4. 文件要提醒設計師：子流程可以被多次執行（合理應用），因此**要自己防無限循環**。

## 一、Abandon 可以直接刪，不需要相容性處理

實查（2026-08-31）：

```
節點定義建立於            2025-12-22（與 End 同批）
現有流程模板使用數        0    （fw_workflow_templates.graph LIKE '%"Abandon"%'）
發行快照使用數            0    （fw_published_form_workflows.workflow_snapshot，共 55 個快照）
執行紀錄                  1 筆  node_id='node-Abandon-e2e'，是 2026-08-31 的 e2e 驗證自己造的
```

**存在八個多月、零個流程在用。** 所以不必比照 ParallelFork 保留 factory 註冊，
可以連 handler 一起刪。刪除清單見本檔第六節。

它與 End 的重複程度（同名方法逐一 diff）：

| 方法 | 差異行數 |
|---|---|
| `_find_parent_node_id` | **0**（一字不差） |
| `_complete_parent_subflow_node` | 2（只有 message 文字與 `abandoned` 標記） |
| `_trigger_parent_next_nodes` | 2 |

188 行裡唯一不可替代的是一行：`data['workflow_status'] = 'CANCELLED'`。

## 二、【最大的雷】子樹範圍不能用 `root_instance_code`

**這是本次改動最容易做錯、而且做錯會出大事的地方。**

### 為什麼

實務上不該規定子流程怎麼關聯，所以 **父 → A → B → A → B 這種組合是合理的**，
同一個名為 A 的子流程模板可能在多條支線上同時被呼叫。
必須**依上下層關係**判斷要中斷誰，**不可以「識別到是 A 就把所有 A 全中斷」**。

### schema 支不支援？支援，但現行程式碼沒在用

父子關聯的權威在 `fw_workflow_instances`，**不在 queue 表**：

| 欄位 | 內容 |
|---|---|
| `parent_instance_code` | 直接父流程（上一層） |
| `root_instance_code` | 整棵樹的根（`subflow_handler.py:134`：`parent.root_instance_code or parent.secure_code`）。**主流程自己是 NULL** |
| `workflow_depth` | 0 ＝ 主流程 |

queue 表的 `calling_instance_code` / `parent_node_id` **只有子流程的 Start 節點帶**
（`subflow_handler.py:195`），後續由 `advance_workflow()` 建的節點一律不帶——
`end_handler._find_parent_node_id()` 的註解明講了這件事。
所以「線索全在 queue 表」不成立，光靠 queue 表撈不到子流程的中間節點。

**每次 SubFlow 節點執行都會 `secrets.token_urlsafe(16)` 建立一個全新的 instance**
（`subflow_handler.py:143-157`），所以：

| 場景 | 區分得出來嗎 | 靠什麼 |
|---|---|---|
| 同一模板 A 被兩條支線呼叫 | ✔ | 兩個不同的 `secure_code` |
| 同一父流程裡兩個 SubFlow 節點都指向 A | ✔ | 兩個 instance；Start 節點的 `parent_node_id` 不同 |
| 同一個 SubFlow 節點迴圈執行 N 次 | ✔ | 每次一個新 instance（`parent_node_id` 相同但 instance 不同） |

**結論：識別資訊是足夠的，缺的是「有人去用它」。**

### 現行 `cancel_pending_nodes()` 的範圍是整棵樹（這就是要改的）

```python
root_instance_code = workflow_instance.root_instance_code or workflow_instance.secure_code
tree_instances = FwWorkflowInstance.query.filter(
    or_(FwWorkflowInstance.secure_code == root_instance_code,
        FwWorkflowInstance.root_instance_code == root_instance_code), ...)
```

放在子流程時，這會把**主流程與所有其他支線**一起收掉。正是 Ethan 說的「出大問題」。

### 正確寫法：走 `parent_instance_code` 的遞迴 CTE

```sql
WITH RECURSIVE subtree AS (
    SELECT secure_code, parent_instance_code, workflow_depth, 0 AS rel_depth
    FROM fw_workflow_instances
    WHERE secure_code = :self AND is_deleted = false
  UNION ALL
    SELECT i.secure_code, i.parent_instance_code, i.workflow_depth, s.rel_depth + 1
    FROM fw_workflow_instances i
    JOIN subtree s ON i.parent_instance_code = s.secure_code
    WHERE i.is_deleted = false
)
SELECT secure_code FROM subtree;
```

（2026-08-31 已對真實表實跑驗證語法，見本檔第七節。）

要一次撈整棵樹**運行中**的節點（維運排查用，非本次改動）則是：

```sql
SELECT q.* FROM fw_node_execution_queue q
JOIN fw_workflow_instances wi ON wi.secure_code = q.workflow_instance_secure_code
WHERE (wi.secure_code = :root OR wi.root_instance_code = :root)
  AND q.status = 'RUNNING' AND q.process_id IS NOT NULL;
```

（root 用主流程自己的 `secure_code`；主流程的 `root_instance_code` 是 NULL，所以要 `OR` 自己那一條。）

### 建議的實作形狀

`cancel_pending_nodes()` 加一個範圍參數，**不要新寫一支平行實作**
（它同時被管理員強制結案與 portal 撤單呼叫，行為必須一致）：

```python
def cancel_pending_nodes(workflow_instance_secure_code, exclude_queue_item_id=None,
                         scope='tree'):   # 'tree' = 現行整棵樹（主流程用）
                                          # 'subtree' = 自己與所有後代（子流程 End(cancel) 用）
```

呼叫端只有 `node_runner` 需要判斷：**該 instance 有 `parent_instance_code` 就用 `subtree`**。

## 三、要回給上一層什麼

現況：子流程結束時把上一層的 SubFlow queue item 標成 SUCCESS，
`result.data` 帶 `child_instance_code`；Abandon 版本多帶一個 `abandoned: True`，
但**那個 JSONB 沒有任何變數前綴讀得到**（`f. / fi. / v. / wi. / n. / t.` 六種都核對過）。

所以要讓上一層真的「收到訊息」，必須寫進 **`fw_workflow_variables`**
（流程變數的權威儲存，`variables` JSONB 那條路流程設計者引用不到）：

```python
VariableService.set_flow_var(parent_instance_code,
                             f'{parent_node_id}_result', 'cancelled', org_code)
```

建議至少寫兩個，讓 Branch 條件好寫：

| 變數 | 值 | 用途 |
|---|---|---|
| `${v.<subflow_node_id>_result}` | `completed` / `cancelled` | 上一層用 Branch 分流 |
| `${v.<subflow_node_id>_child}` | child instance secure_code | 排查用 |

**要在 `_complete_parent_subflow_node()` 標 SUCCESS 的同時寫入**，
而且必須在觸發 `cancel_pending_nodes(scope='subtree')` 之前——上一層不在 subtree 內，
不會被取消，所以順序上安全，但寫入要先於回傳。

## 四、必須一起修的兩個既有缺陷

### 4-1【安全性】`advance_workflow()` 沒有終態檢查，會讓已結束的流程復活

終態防護只存在於 `node_runner.advance_to_next_nodes()`（`node_runner.py:236`）：

```python
if workflow_instance and workflow_instance.status in ('COMPLETED','CANCELLED','ERROR','FAILED'):
    return
```

但 `end_handler._trigger_parent_next_nodes()` **直接呼叫
`WorkflowEngine.advance_workflow()`**，繞過這道檢查。
而 `workflow_executor` 撿節點時**只看 queue item 的 status、不看 instance 的 status**。

後果：上一層已經是終態時，子流程結束仍會在它裡面建出新的 PENDING 節點，
executor 撿起來繼續跑 —— **已結束的流程被復活**。

修法：`advance_workflow()` 開頭補同一段檢查（約 5 行）。
**這條與合併 Abandon 無關，是獨立的安全修補，建議第一個做。**

### 4-2 子流程 End 的兩個吞錯誤路徑會讓上一層永久卡死

`_handle_subflow_end()` 內：找不到 `parent_node_id` → 只 `log_warning`；
喚醒父流程拋例外 → 只 `log_error`。兩者都照常回成功。

而 `workflow_executor` 的兩處喚醒清單是 `['Delay','End','ParallelJoin','OsExecutor']`，
**`SubFlow` 不在內**，全 repo 也沒有 stale WAITING 的回收機制。
→ 上一層的 SubFlow 節點永久停在 WAITING，**不報錯、不逾時、無回收路徑**。

`end_handler.py:116` 的警告文字寫「父流程可能卡住」，實際上是「一定卡住」。

修法：喚醒失敗時把上一層的 SubFlow 節點標成 **FAILED**（而不是留在 WAITING），
並寫一筆流程變數記錄原因。讓流程以錯誤終止，至少看得見、查得到。

> Abandon 之所以「不會卡住」，只是因為它會 cancel 整棵樹順便把那個 WAITING 收掉——
> 那是副作用不是設計。合一之後這條路徑只需要在 End 修一次。

## 五、子流程可多次執行 → 文件必須提醒設計師防無限循環

**現況：完全沒有任何防護。** 實查：

- `subflow_handler` 沒有深度上限、沒有循環偵測（全檔只有 `child_depth = parent.workflow_depth + 1` 這個純計算）
- `workflow_depth` 全 repo **只有 `base.py:492` 讀它**（提供 `${wi.depth}` 變數），**沒有任何地方拿它做上限判斷**
- SubFlow 節點的 `config_schema` 只有 `{"childFlowId": "string"}`，沒有次數上限欄位
- partial unique index `idx_fw_queue_active_node` 是
  `(workflow_instance_secure_code, node_id) WHERE status IN ('PENDING','RUNNING','WAITING')`
  —— 只擋「同一節點同時有兩筆未完成」，**已完成的不受限，所以迴圈重複執行是被允許的**（這是對的，那是合理應用）

### 要寫進使用者文件的提醒（Ethan 指定）

> 子流程可以被同一條流程重複呼叫，這是刻意允許的。但平台**不會**自動偵測無限循環，
> 所以設計含迴圈的流程時，**必須自己設上限**：在 cancel（或 End）之前用
> `OpSet` 節點累加一個流程變數當計數器，再用 `Branch` 判斷是否超過上限並走出迴圈。

寫的位置：`docs/manual/` 的流程設計章節（使用者面），
以及 `dev-notes/WORKFLOW_DESIGNER_NOTES.md`（開發者面）。

**另一個選項是在 SubFlow 節點 config 加 `max_iterations`**（Ethan 提到「或者在 subflow node 設定上限」）。
若採這條，注意計數要記在**上一層的流程變數**（同一個 SubFlow 節點被執行幾次），
不能記在子流程自己身上——每次呼叫都是全新 instance，記在自己身上永遠是 1。
**這一項要先跟 Ethan 確認採哪一種再動工。**

## 六、改動清單

| # | 項目 | 檔案 | 性質 |
|---|---|---|---|
| 1 | `advance_workflow()` 補終態檢查 | `services/workflow_engine.py` | **獨立安全修補，先做** |
| 2 | `cancel_pending_nodes()` 加 `scope='subtree'`（遞迴 CTE） | 同上 | 核心 |
| 3 | End 新增 `end_status` 設定（`completed` / `cancelled`） | `node_handlers/end_handler.py` ＋ 設計器面板 ＋ `config_schema` | 合一 |
| 4 | 子流程 End(cancel) 走 `scope='subtree'` ＋ 寫流程變數回報上一層 | `end_handler.py`、`node_runner.py` | 核心 |
| 5 | End 兩個吞錯誤路徑改標 FAILED | `end_handler.py` | 原 PF-189-3 |
| 6 | `end_handler` 的 `wait_seconds` clamp（**兩處**：`:68` 與 `:108`） | `end_handler.py` | 原 PF-189-1，照抄 abandon 的 `_clamp_wait_seconds` |
| 7 | **刪除 Abandon** | 見下 | 最後做 |
| 8 | 文件：循環上限提醒、`ABANDON_SPEC.md` 標記退役、`NODE_TEST_INVENTORY.md` 更新 | `docs/manual/`、`dev-notes/` | 收尾 |

### 第 7 項的刪除清單

```
modules/form_workflow/services/node_handlers/abandon_handler.py     刪檔
node_handlers/factory.py                                            移除註冊
backend/tests/test_abandon_node.py                                  刪或改寫成 End 的對應案例
設計器面板（wf-accordion-flow.js 的 renderAbandonPanel）             移除
workflow_node_definitions                                           migration 軟刪除該筆
dev-notes/ABANDON_SPEC.md                                           標記退役（不刪檔，保留脈絡）
CLAUDE.md「Abandon 是唯一避開這件事的結束節點」那段                  改寫成 End 的 end_status
```

**`node_type` 是 factory 查 handler 的鍵**，但因為 graph 與快照都 0 筆使用，
不會有「舊字串找不到 handler 而拋 ValueError」的風險（這點已實查確認，見第一節）。

## 七、驗證方法（本機沒有任何子流程資料，必須自己造）

**實查：本機 894 個 `fw_workflow_instances` 全部是 `workflow_depth = 0`，
`parent_instance_code` 全為 NULL —— 一筆真實的子流程執行紀錄都沒有。**

所以這批改動**不能靠既有資料驗證**，必須自己造一棵樹。
造法沿用 `dev-notes/NODE_TEST_INVENTORY.md`「怎麼補測」那節
（直接建 `FwWorkflowInstance` ＋ 一筆 `node_type='Start'` 的 PENDING queue，
executor 會自己撿起來跑，不必經表單提交）。

必測的樹形，**這是本次的驗收核心**：

```
        主流程 P
        ├── A1 ── B1        ← 在 A1 的 End(cancel) 觸發
        └── A2 ── B2        ← A2/B2 必須毫髮無傷
```

| 斷言 | 預期 |
|---|---|
| A1、B1 的未完成節點 | 全部 `CANCELLED` |
| **P、A2、B2** | **完全不受影響，繼續執行** |
| P 的 SubFlow(A1) 節點 | `SUCCESS`，且 `${v.<node>_result}` == `cancelled` |
| `fw_form_instances.status` | **不變**（子流程不碰表單狀態，這是既有設計） |

用現行程式碼跑這個樹形，A2/B2/P 會一起被收掉 —— 那就是修好之前的基準行為，
**先跑一次記下來當對照組**。

### 順帶：本檔查證用過的指令

```bash
# Abandon 使用數
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -c "
SELECT count(*) FROM fw_workflow_templates WHERE graph::text LIKE '%\"Abandon\"%' AND is_deleted=false;
SELECT count(*) FROM fw_published_form_workflows WHERE workflow_snapshot::text LIKE '%\"Abandon\"%';"

# 子流程 instance 分布
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -c "
SELECT workflow_depth, count(*) FROM fw_workflow_instances WHERE is_deleted=false GROUP BY 1;"

# queue 的 partial unique index
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -c "
SELECT indexdef FROM pg_indexes WHERE indexname='idx_fw_queue_active_node';"
```

## 八、動工前必讀的既有規範

- **改 handler 後要重啟 executor，而重啟會殺掉當下所有 RUNNING 節點且永遠卡住**——
  重啟前先查 `SELECT node_type, node_id, started_at FROM fw_node_execution_queue WHERE status='RUNNING';`
  （CLAUDE.md「服務啟動」）
- 新增節點分類／設定項要改設計器四處，漏 `categoryOrder` 會被靜默略過
  （`dev-notes/WORKFLOW_DESIGNER_NOTES.md`）
- `graph` 與 `cytoscape_config` 兩欄都要寫；直接改 graph 不會 bump revision
- 測試一律 `bash scripts/run_tests.sh`，不要自己 source .env 後叫 pytest（會撞開發庫）
- 驗收留證落地 `/opt/tmp/verify/`（VERIFY-01）

---

## 九、【冷讀補洞 2026-08-31】codex 冷讀列出的缺口與補充

本檔寫完後交給 codex 做冷讀（假設接手者只有本檔與 CLAUDE.md），它列出 22 個需要猜測的點。
以下是其中會造成**做錯**或**試誤成本高**的，逐項補齊。

### 9-1 `end_status` 與既有 `finish_mode` 的關係（規格缺口，先定這個）

兩者**正交、各自獨立**，不是改名也不是取代：

| 欄位 | 選項 | 管什麼 |
|---|---|---|
| `finish_mode`（既有） | `detach` / `cancel` / `strict` | 其他分支怎麼處理 |
| `end_status`（新增） | `completed`（預設）/ `cancelled` | 終態記什麼 |

**舊 graph 的 backfill：不做 migration，改在 handler 讀取時給預設值**
`self.node_config.get('end_status', 'completed')`。

**`finish_mode='cancel'` 不得自動對應 `end_status='cancelled'`**——
現有 19 個含 End 的模板裡有人用 `cancel` 只是為了收掉並行分支，
自動轉換會讓他們的案子從「已核准」變成「已取消」。**這是靜默的行為變更，禁止。**

### 9-2 回報上一層的變數：完整矩陣與 org_code 來源

| 情境 | `${v.<node>_result}` | `${v.<node>_child}` |
|---|---|---|
| 子流程正常結束（`end_status=completed`） | `completed` | child instance secure_code |
| 子流程 End(cancel) 且 `end_status=cancelled` | `cancelled` | 同上 |
| 喚醒上一層失敗（見 9-3） | `error` | 同上（若拿得到） |

- **只有子流程的 End 寫這兩個變數**，主流程的 End 不寫（沒有上一層可寫）
- 三種情境都要寫 `_child`，排查時要靠它回查
- `org_code` 一律用 **`self.queue_item.org_secure_code`**（子流程 instance 建立時
  就是從父流程的 queue item 帶下來的，見 `subflow_handler.py:146`，父子必然同企業）

### 9-3 【冷讀挖到的真漏洞】找不到 `parent_node_id` 時，沒有父 queue item 可標 FAILED

本檔第四節 4-2 說「喚醒失敗時把上一層的 SubFlow 節點標成 FAILED」，
但**兩條失敗路徑的可用資訊不同**：

| 路徑 | 拿得到父 queue item 嗎 | 處置 |
|---|---|---|
| `_trigger_parent_next_nodes()` 拋例外 | **拿得到**（前一步已找到並標 SUCCESS） | 把它改標 FAILED ＋ 寫 `_result=error` |
| `_find_parent_node_id()` 回 None | **拿不到**，連父流程的哪個節點都不知道 | 見下 |

第二條路徑的處置：**改用 `workflow_instance.parent_instance_code`**
（那個值一定有，否則不會走進 `_handle_subflow_end`），
把上一層**所有 `status='WAITING'` 且 `node_type='SubFlow'` 的 queue item** 標 FAILED，
並在**子流程自己**的 `error_message` 記下原因。

會不會誤傷上一層其他正常等待中的 SubFlow 節點？會，但：
- 上一層有多個 SubFlow 同時 WAITING 本來就少見
- 誤標 FAILED（看得見、查得到）遠優於永久卡死（不報錯、無回收）
- 這條路徑本身就是「資料已經不一致」的異常狀態

**在該分支加註解寫明這個取捨**，否則下一個 session 會以為是 bug 想「修好」。

### 9-4 `cancel_pending_nodes` 的實作風格

該函式現行是純 ORM（`FwWorkflowInstance.query.filter(or_(...))`）。
遞迴 CTE 沒有 ORM 寫法，用 `db.session.execute(text(...))` 取出 secure_code 清單，
**再用既有的 `.in_(tree_codes)` 走原本的 ORM 流程**——
這樣兩種 scope 的下游（取消節點、terminate process、`_stop_os_dispatched_units`）
完全共用，log 格式與統計數字也自然一致。

**`scope='subtree'` 的 log 要標明 scope**，否則兩種範圍在 journal 裡分不出來。

### 9-5 驗證樹的具體建法（現成材料，不必從零造）

**Ethan 2026-08-31 正在建的子流程測試範本可以直接用**：

```
主流程模板   fX7oqrrSON2ppjpDDX6J8A  「subflow測試」（系統預設企業 system.local）
已建的子流程 mivA29i1emcFcyGn14y_Jw  sub_A_L2
             FLA-GRkUWF42AIaJX7-sHA  sub_C_L2_2   ← 這兩筆同名是 PF-202 的重現材料
             wjQNetqO9fkkauiF9j6TdA  sub_C_L2_2   ← 修好 PF-202 前不要清掉
quick-login  UC1oK01uDeKbG2MDwBflGD  （系統預設企業 ORG_ADMIN）
```

**它們目前是空架構**（graph 裡 4 個 SubFlow 節點的 `childFlowId` 全是 null），
所以動工前要先把 A1/B1/A2/B2 的引用接起來。**先跟 Ethan 確認能不能動這張圖**——
它是 Ethan 手上正在畫的東西。

不想動它就自己造，最小欄位（`FwWorkflowInstance` 與 `FwNodeExecutionQueue`
**都沒有 `created_by` 欄位，傳了直接 TypeError**）：

```python
FwWorkflowInstance(secure_code=..., org_secure_code=..., workflow_template_secure_code=...,
                   execution_code=..., status='RUNNING', started_at=datetime.utcnow(),
                   parent_instance_code=<上一層 sc 或 None>, root_instance_code=<root sc 或 None>,
                   workflow_depth=<層數>, graph_snapshot=<graph dict>)
FwNodeExecutionQueue(secure_code=..., org_secure_code=..., workflow_instance_secure_code=...,
                     node_id='start', node_type='Start', status='PENDING',
                     scheduled_at=datetime.utcnow())
```

executor 會自己撿起來跑，不必經表單提交。詳見 `NODE_TEST_INVENTORY.md`「怎麼補測」。

### 9-6 驗收斷言的實際 SQL

```sql
-- 樹上每個 instance 的終態
SELECT wi.secure_code, wi.workflow_depth, wi.status, wi.parent_instance_code
FROM fw_workflow_instances wi
WHERE wi.secure_code = :root OR wi.root_instance_code = :root
ORDER BY wi.workflow_depth, wi.created_at;

-- 每個 instance 底下節點的狀態分布（A2/B2 應該完全沒有 CANCELLED）
SELECT q.workflow_instance_secure_code, q.status, count(*)
FROM fw_node_execution_queue q
JOIN fw_workflow_instances wi ON wi.secure_code = q.workflow_instance_secure_code
WHERE wi.secure_code = :root OR wi.root_instance_code = :root
GROUP BY 1, 2 ORDER BY 1, 2;

-- 回報變數有沒有寫進去
SELECT name, value, scope FROM fw_workflow_variables
WHERE workflow_instance_secure_code = :parent_of_A1;
```

**主流程 End(cancel) 合併後也要驗**（本檔第七節只列了子流程的樹形）：

| 斷言 | 預期 |
|---|---|
| 主流程 End(`finish_mode=cancel`, `end_status=completed`) | instance `COMPLETED`、form_instance **`APPROVED`**（維持現行行為，不得因合併而改變） |
| 主流程 End(`finish_mode=cancel`, `end_status=cancelled`) | instance `CANCELLED`、form_instance **`CANCELLED`**（等同舊 Abandon） |

### 9-7 刪除 Abandon 的補充

- **migration 編號**：現行最大是 `130_sys_nodes_org_restricted.sql`，接 131 起。
  命名沿用 `<編號>_<動作>.sql`，**寫完要跑一次 `scripts/route_guard_inventory.py --update`**
  （若有動到路由；純 DB migration 不用）
- **刪除清單不保證完整**，收尾一定要跑一次全域搜尋確認沒有殘留：
  ```bash
  grep -rni "abandon" --include=*.py --include=*.js --include=*.html --include=*.sql \
    --include=*.po --include=*.json backend modules docs dev-notes | grep -v ABANDON_SPEC
  ```
  記得看 i18n（`backend/app/static/i18n/en.json` 與 `.po`）與 `docs/`
- **`backend/tests/test_abandon_node.py` 採「改寫成 End 的對應案例」**，不要直接刪——
  裡面的父子流程 fixture（`workflow_depth=1` 的三個案例）是現成的測試材料，
  正好是本次最缺的東西

### 9-8 新增 UI 文字要補 i18n

`end_status` 的兩個選項標籤與說明文字要包 `__()`／`_()`，並補進
`backend/app/static/i18n/en.json`。漏了不會報錯，只是英文介面顯示中文（I18N-01）。
