# Abandon（中止）節點規格【已退役】

> **【PF-200，2026-08-31 晚】本檔描述的節點已刪除。** 下方「存廢定案：保留」是
> 同日稍早的結論，**當晚被 Ethan 推翻**：Abandon 併入 `End(finish_mode='cancel')`
> （cancel 自此＝中止語意，記 CANCELLED），節點的 handler／factory 註冊／設計器面板
> 全數移除，nodedef 由 migration 131 軟刪除。定案與實作記錄見
> `dev-notes/handoff_end_subflow_cancel_20260831.md` 第十節。
> 本檔保留當時的分析脈絡，**內容不再反映現況，不要依它動工**。

> 2026-08-31 建立。Abandon 節點自 2026-02-17（commit `45dfa233`）上線以來從未有規格文件，
> `dev-notes/NODE_TEST_INVENTORY.md` 的 NT-17 標記「未驗證」。本檔是實測後的第一份規格，
> 所有結論附實測證據（`/opt/tmp/verify/20260831-abandon.log`）或讀碼引用。
>
> 實作：`modules/form_workflow/services/node_handlers/abandon_handler.py`。
> 設計器面板：`wf-accordion-flow.js::renderAbandonPanel()` +
> `wf-form-adapter.js::applyAbandonConfig()`（見第五節）。

## 零、一句話結論（2026-08-31 當天下午改寫，見下方「存廢定案」）

**Abandon 是唯一會把流程與表單記成「已中止」的結束方式。** handler 回傳
`data.workflow_status='CANCELLED'`，`node_runner` 依白名單採用它；`End` 的三種
`finish_mode` 一律落到 `COMPLETED`，`complete_workflow()` 再把表單記成 `APPROVED`。

在此之前它與 `End(finish_mode='cancel')` **完全等價**，唯一差異（子流程的
`abandoned: true` 標記）**沒有任何變數語法讀得到**（第四節），是不折不扣的冗餘節點。

---

## 零之一、存廢定案（Ethan 2026-08-31 提供歷史脈絡後）

**原始設計動機（Ethan 提供，程式碼與 git log 都查不到）**：最古老的流程版本
**限定一個流程只能有一個 End 節點**，流程圖大而複雜時，每條支線都要拉一條線回到那個
End，線太多太亂。Abandon 就是為了「不必拉線也能收掉流程」而生的。

**該理由在「允許多個 End + 三種結束模式」之後已經完全消失**——現在每條支線末端各放一個
End 即可，不會產生長線。所以 2026-08-31 上午的評估結論是：Abandon 當時確實只是冗餘。

**保留的決定與代價**：與其退役，不如讓它承擔一個 `End` 做不到、而且平台確實需要的
語意——「這個案子是被擋下來的，不是談成的」。理由是這修掉一個真實的資料正確性缺陷
（見下方），且成本只有 `node_runner` 加一段白名單分支。

- **被中止的案子原本會被記成「已核准」**：`fw_workflow_instances.status='COMPLETED'`
  → `fw_form_instances.status='APPROVED'` → 表單中心顯示「已核准」
- 更嚴重的是下游：`complete_workflow()` 無條件呼叫 `enqueue_sync_safe()`，而
  `enqueue_sync()` **不看表單狀態、一律 `action='upsert'`**，所以那個錯誤終態會被
  **寫進該企業的獨立資料庫 `org_<id>`**，而 SQL Sync 一旦啟用就無法關閉
  （`api/mappings.py:439` 硬擋），**沒有回收路徑**
- 平台本來就有一條把中止表達正確的路徑：`fc_admin.py:73`（管理員強制結束）傳
  `status='CANCELLED'`，`complete_workflow()` 的 `elif status == 'CANCELLED'` 分支
  早就在了。**Abandon 只是走不到它**

**連帶處置**：Abandon 的 `require_system_admin` 與 `org_restricted` 都是 false
（所有企業都看得到），放在「系統級管理員專用」分類本來就是錯的，
已移到「基本」分類與 `End` 並列（`scripts/migrations/legacy/128_abandon_move_to_basic.sql`）。

**`End(cancel)` 維持原樣**——它的語意是「正常結束並清理未完成節點」，記成完成是對的。

實測憑證：`/opt/tmp/verify/20260831-abandon.log`（真實 executor 端對端，
`queue=SUCCESS` / `workflow_status=CANCELLED` / 流程與表單雙雙 `CANCELLED`）。
測試：`backend/tests/test_abandon_node.py::test_abandon_reports_cancelled_workflow_status`
與 `::test_node_runner_honours_workflow_status_and_rejects_junk`。

---

## 一、這個節點在停止什麼（精確範圍）

停止的單位是**整個 workflow instance tree**（`root_instance_code` 展開，含主流程與
所有層級的子流程），不是「觸發 Abandon 的那一條分支」。並行分支中一條走到 Abandon，
**同一個 instance 內其他所有分支**（不論並行與否）都會被牽連取消。

實測（`/opt/tmp/verify/20260831-abandon.log:1-67`）：建立 Start 分兩條並行邊
——一條走 `OsExecutor`（`sleep 25`，`wait_for_result=true`）、另一條走
`Delay(3s) -> Abandon`。Abandon 觸發約 3 秒後，`OsExecutor` 仍在 RUNNING（離
25 秒還遠），但立刻被標成 `CANCELLED`，對應的 `sleep 25` OS process **真的被殺掉**
（`ps` 復查已消失，行 33-38）。

### 依節點狀態的下場

| 節點原狀態 | 下場 | 依據 |
|---|---|---|
| PENDING | 直接標記 `CANCELLED`，永遠不會被執行 | `cancel_pending_nodes()` 查詢 `status IN ('PENDING','RUNNING','WAITING')` |
| WAITING（含未到時間的 Delay、等待簽核的 FormAdapter、等待子流程的 SubFlow） | 直接標記 `CANCELLED`，**沒有任何專屬處理或通知**——簽核人不會被告知任務已被撤銷，只是下次查詢時該任務消失 | 同上，一視同仁 |
| RUNNING，命令由 `node_runner` 子行程自己執行（例：`OsExecutor` 的 `wait_for_result=true` 模式，子命令與 `node_runner` 同一個 process group） | **真的會被終止**：SIGTERM，等 3 秒未結束再 SIGKILL | 實測見上；機制見 `workflow_engine.py::_terminate_node_process()`，2026-08-30 commit `f2e0ecf7` 修復（此前只改 DB 欄位不碰 process） |
| RUNNING，已 dispatch 給 systemd 的 `OsExecutor`（`wait_for_result=false`，`os_dispatch.unit` 記在 result） | 額外機制 `_stop_os_dispatched_units()` 主動 `systemctl stop <unit>`。**讀碼確認、本次未端到端實測**（`sudo -n systemctl` 需要 sudoers 配合），建議主 Claude 補驗 | `workflow_engine.py:99-165` |
| RUNNING，命令交給外部系統執行且該系統只認連線斷開（例：`SysSqlExecutor` 發動的 PostgreSQL 查詢） | **不會被中斷**，會跑到自然結束或 `statement_timeout`（上限 60 秒）為止。PostgreSQL 只有在要寫回 socket 時才會發現 client 已斷線，殺掉 node_runner 對已送出的查詢無效 | BBN atom 5300（2026-08-30 End cancel 修復時的實測結論，`pg_sleep(45)` 在 client 死後仍活 75 秒） |
| 已送出的外部 HTTP 請求（EmailAdapter / SysEmailRelay / Telegram） | **不會被收回** | 同上，性質相同（無法用 process signal 中止已送出的請求） |
| 子進程且與 node_runner 同 process group（例：`AiAgent` 呼叫的 `claude` CLI） | 會被一起收掉 | BBN atom 5300 |

**結論（回答 briefing「它可能只改 DB 狀態，外部副作用照跑」的疑慮）**：
對 `OsExecutor` 這類「命令本身就是 node_runner 子進程」的節點，Abandon **確實**會
中止外部副作用，這點已用真實 OS process 驗證過，不是空話。但對 `SysSqlExecutor`
這類「交給另一個系統執行、只能靠對方主動偵測斷線」的節點，Abandon **只改了 DB
狀態，實際查詢照跑到 timeout**——這不是 Abandon 或 cancel 模式本身的缺陷，是
「殺行程 vs 取消遠端作業」在作業系統層級的固有差異，`pg_cancel_backend()` 方案已被
提出但 Ethan 尚未決策（BBN atom 5303 / PF-173，未涵蓋在 Ethan 對 End cancel 修復的
回覆裡）。**Abandon 固定用 cancel 模式，這個既有邊界對它同樣適用。**

---

## 二、成功條件與失敗條件

**Abandon 節點自己沒有失敗路徑。** 不論找不找得到父節點、喚醒父流程是否拋例外，
`handle()` 一律回傳 `status: 'complete_workflow'`（成功），差別只在 log 等級：

- 找不到父流程 SubFlow 節點 ID → `log_warning`，仍視為成功
- 喚醒父流程時拋例外（`advance_workflow` 內部錯誤）→ `log_error`，仍視為成功

**這是刻意設計還是缺陷？判斷：這是缺陷級的設計疏忽，但後果比 handler 自己的
註解描述的輕**（見下段與第四節的修正）。理由：

1. `abandon_handler.py` 的註解寫「子流程將中止但父流程可能卡住」，**實測不成立**
   （見第四節）——只要 `root_instance_code` 正確指向父流程，父流程會被
   `cancel_pending_nodes` 的樹狀範圍連帶標記 `CANCELLED`，不會卡住。
2. 但「喚醒父流程失敗」（`advance_workflow` 拋例外）與「找不到父節點 ID」是兩種不同
   情境的錯誤都被吞掉、且用同一句籠統訊息記錄，事後無法區分是「資料本來就沒有
   `parent_node_id`」還是「引擎呼叫出錯」。建議至少讓 `except Exception` 分支
   `raise` 或回 `status: 'error'`，因為那代表引擎本身出了非預期狀況，靜默吞掉
   等於少了一個察覺引擎 bug 的機會。

### `fw_workflow_instances.status` 的最終值（重要，與直覺不符）

`node_runner.py` 對 `complete_workflow` 的狀態判斷只有一條規則：

```python
wf_status = 'FAILED' if (finish_mode == 'strict' and has_failures) else 'COMPLETED'
```

Abandon 固定 `finish_mode='cancel'`，永遠不滿足 `strict`，所以**觸發 Abandon 的那個
instance，最終狀態被寫成 `COMPLETED`**——與正常走完流程的狀態完全相同。
連帶：若該 instance 有掛 `fw_form_instances`，`WorkflowEngine.complete_workflow()`
把 `status='COMPLETED'` 對應到 `form_instance.status = 'APPROVED'`。

**也就是說：被 Abandon 中止的申請單，在表單中心會顯示成「已核准」。**
這是本次盤點發現最嚴重的語意缺陷，已用測試釘住現況
（`backend/tests/test_abandon_node.py::test_cancel_complete_marks_form_instance_approved_not_cancelled`）。
不是 Abandon 專屬——`End` 的 `cancel`／`detach` 模式共用同一段判斷，一樣會被記成
`COMPLETED`/`APPROVED`。**是否要新增 `CANCELLED` 狀態並讓 cancel 模式對應過去，
是要 Ethan 決策的架構變更（牽動 `node_runner.py` 與所有讀 `form_instance.status`
的前端），不在本次 Abandon 節點盤點的授權範圍內修改。**

#### 下游影響：錯誤的終態會流進企業獨立資料庫（主 Claude 總驗收時補，2026-08-31）

這個缺陷不只是「表單中心顯示錯」。`complete_workflow()` 在寫完狀態後**無條件**呼叫
`enqueue_sync_safe()`（`workflow_engine.py:614`），而 `enqueue_sync()`
（`sync_service.py:26`）**完全不看表單狀態**、一律 `action='upsert'`。所以只要該
published 表單有啟用 SQL Sync（`fw_sql_form_registries.status='active'`），
**被 Abandon 中止的案子會以「已核准」的終態被 upsert 進該企業的獨立資料庫
`org_<id>`**。SQL Sync 一旦啟用就無法關閉（`api/mappings.py:439` 硬擋），
所以這筆錯誤終態沒有回收路徑。

#### 平台已經有一條把「中止」表達正確的路徑

`fc_admin.py:73`（管理員強制結束）呼叫的是
`complete_workflow(status='CANCELLED', end_message='由 X 強制結束')`，
`complete_workflow()` 的 `elif status == 'CANCELLED'` 分支把
`form_instance.status` 正確寫成 `CANCELLED`。

**也就是說 `CANCELLED` 不是要新增的概念，是既有且正在使用的分支**，
只是流程設計器裡的 Abandon 走不到它。這讓修法的影響評估比第三節的 A/B 兩案更樂觀，
並且直接給出第三個選項：

- **C（讓 Abandon 走 CANCELLED，End(cancel) 維持現狀）**：`AbandonHandler` 在回傳的
  `data` 多帶一個旗標（例如 `workflow_status: 'CANCELLED'`），`node_runner.py:174`
  的那一行改成優先採用該旗標、沒有才走舊規則。影響面只有 Abandon 這一個節點型別，
  既有 `End(cancel)` 流程行為完全不變。
  **這同時回答了第三節「為何需要獨立節點」**：改完之後 Abandon 與 End(cancel) 就有了
  不可替代的差異——**Abandon 是唯一會把案子記成「已中止」的結束方式**，
  而 End(cancel) 是「正常結束並清理未完成節點」。
  代價：讀 `form_instance.status` 的前端要確認有處理 `CANCELLED`
  （`fc-utils.js` 已有 REJECTED/CANCELLED 的文案對應，需實測確認）。

**被連帶取消的其他 instance（同一棵樹上除了觸發 Abandon 的那筆）則是 `CANCELLED`**——
`cancel_pending_nodes()` 內 `cancelled_instances` 迴圈直接寫 `status='CANCELLED'`，
不經過 `complete_workflow()`，所以不受上面那條規則影響。**結果是同一次「中止」事件，
樹上不同 instance 最終被貼上不一致的狀態**：觸發節點所在的 instance 是
`COMPLETED`，其餘（含父流程，見第四節）是 `CANCELLED`。

---

## 三、與 End(cancel) 的差異與選用建議

| 項目 | Abandon | End(`finish_mode='cancel'`) |
|---|---|---|
| 可選模式 | 固定 cancel，無法選 detach/strict | detach / cancel / strict 三選一 |
| 主流程回傳 data | `finish_mode`, `completed_at` | 同左 |
| 子流程回傳 data | 多 `abandoned: true` | `finish_mode: 'subflow_end'`，無此欄位 |
| 父流程 SubFlow queue item 的 result.data | 多 `abandoned: true` | 只有 `child_instance_code` / `completed_at` |
| 設計器面板文案 | 「取消所有未執行的節點，強制終止執行中的節點，立即結束流程」（紅色警示樣式） | 三模式各自的中性說明 |
| wait_seconds 預設 | 1 | 主流程 3 / 子流程 1 |
| wait_seconds 上限 | **後端 300 秒**（2026-08-31 本次補上，見第五節） | **仍無上限**（讀碼確認，本次未修，屬 `end_handler.py`，不在本次授權的檔案領地內） |

**設計意圖查證**：commit `45dfa233`（2026-02-17）訊息只寫「Abandon 中止節點 handler +
設計器配置面板」，沒有說明動機；BBN 知識庫搜尋 "Abandon 中止節點" 沒有找到當時的
設計討論記錄。從程式碼與面板文案看，意圖應該是**給設計者一個「語意明確、不必選
模式」的異常終止入口**——End 節點三選一的介面對「我就是要中止」這個常見需求不夠
直覺，容易選錯模式（例如誤選 detach，未完成節點不會被清理）。

**結論與建議**：Abandon 目前在行為上完全可以用 `End + finish_mode='cancel'` 取代，
**唯一「差異」（`abandoned` 標記）目前是死資料，讀不到就等於沒有**。建議二選一：

- **A（保留，補齊語意）**：把 `abandoned` 標記寫入 `fw_workflow_variables`
  （用既有的 `VariableService.set_flow_var()`，例如
  `<subflow_node_id>_abandoned=true`），讓父流程的 Branch 條件真的能判斷「子流程是
  被中止還是正常結束」。這樣 Abandon 才有不可替代的價值：**它是唯一能讓父流程
  分辨「異常終止」與「正常結束」的子流程收尾方式**。
- **B（退役）**：如果 Ethan 認為「異常終止 vs 正常結束」對父流程不重要，直接退役
  Abandon，統一用 `End(cancel)`，減少設計器面板一個容易混淆的選項。

**兩案都不在本次授權範圍內執行**——briefing 明確要求「給結論，但不要自己執行退役」。
本次已完成的是 A 案的前置：加上 `wait_seconds` 上限保護（第五節），使 Abandon 與
`End` 在資安/穩定性面先拉平。

---

## 四、子流程語意（含父流程如何得知）

### 4.1 父流程「不會真的繼續往下跑到底」（修正 briefing 原始假設）

briefing 原始描述「子流程中止 → 父流程繼續往下跑」只對了一半。實測
（`/opt/tmp/verify/20260831-abandon.log:834-851`，父流程 `Start->SubFlow->After`，
子流程 `Start->Abandon`）：

1. 子流程 Abandon 執行時，`_handle_subflow_abandon()` **先**把父流程的 SubFlow
   queue item 標成 `SUCCESS`（帶 `abandoned: true`），**並呼叫
   `WorkflowEngine.advance_workflow()` 真的建立了父流程的下一個節點**
   （`node-After-1`，狀態 `PENDING`）——這一步看起來像「父流程繼續往下跑」。
2. 但 Abandon handler 回傳 `complete_workflow` 給 `node_runner` 後，`node_runner`
   看到 `finish_mode='cancel'`，對**整棵樹**（`root_instance_code` 展開，含父流程）
   呼叫 `cancel_pending_nodes()`——此時剛建立的 `node-After-1`（仍是 PENDING）
   與父流程 instance 本身，**全部在同一輪被取消**。
3. 最終狀態：`node-After-1` = `CANCELLED`、父流程 instance = `CANCELLED`、
   子流程 instance（觸發 Abandon 的那個）= `COMPLETED`（見第二節的狀態不一致問題）。

**淨效果是「整棵流程樹一起終止」，不是「子流程死了、父流程活著繼續跑」**。
這點與 handler 檔頭註解「子流程中止時，同樣喚醒父流程的 SubFlow 節點並推進父流程」
字面上暗示的行為（推進＝繼續執行）有落差，實際上推進只是短暫的中間狀態，
下一瞬間就被同一輪 cancel 波及。**這是正確且一致的行為，只是文字描述容易誤導。**

### 4.2「找不到父節點 ID」不會讓父流程卡住（只要 root_instance_code 正確）

handler 註解與 briefing 都假設「找不到父節點 ID → 父流程可能永遠卡住」。
實測推翻這個假設（`backend/tests/test_abandon_node.py::test_subflow_abandon_missing_parent_node_id_still_cancels_real_parent`）：
即使 `_find_parent_node_id()` 回 `None`、`_trigger_parent_next_nodes()` 完全沒被
呼叫，父流程的 WAITING SubFlow 節點與父流程 instance 本身**仍然會**因為
`cancel_pending_nodes()` 用 `root_instance_code` 展開整棵樹而被連帶標記
`CANCELLED`——**不會卡住**。

真正會卡住的情境只剩一種：子流程的 `root_instance_code` 本身沒有正確指向父流程
（資料異常，例如手動造資料時漏設，或未來某個 bug 導致 `SubFlowHandler` 建立子流程
時沒寫入這個欄位）。這種情況下 `cancel_pending_nodes()` 找不到父流程在同一棵樹，
父流程才會真的與子流程失聯、永遠卡在 WAITING。**建議把 handler 的註解文字
（`'找不到父流程 SubFlow 節點 ID，子流程將中止但父流程可能卡住'`）修正為更精確的
描述**，避免下一個維護者誤判影響範圍——但這是純文字修正，本次先在 SPEC 記錄，
交主 Claude 決定是否連帶改 log 訊息。

### 4.3 `abandoned` 標記讀不到（見零節結論的依據）

`abandoned: true` 被寫進兩個地方：Abandon 自己回傳的 `result.data.abandoned`，以及
父流程 SubFlow queue item 的 `result.data.abandoned`。**兩者都只是
`fw_node_execution_queue.result` 這個 JSON 欄位裡的值，不是流程變數。**

流程設計者能用的變數語法（`BaseNodeHandler.replace_variables()`，
`modules/form_workflow/services/node_handlers/base.py:355-467`）只有六種前綴：

| 前綴 | 涵蓋範圍 |
|---|---|
| `f.` | 表單欄位（`form_data` JSON） |
| `fi.` | 表單資訊（固定欄位白名單） |
| `v.` | 流程變數（`fw_workflow_variables` 表，`VariableService`） |
| `wi.` | 流程資訊，只有 `code`/`exec_code`/`name`/`status`/`depth` 五個固定欄位 |
| `n.` | **只有 `n.name` / `n.id` / `n.type` 三個，是「目前正在執行的節點」自己的資訊** |
| `t.` | 時間 |

**沒有任何語法能讀取「指定節點 ID 的 `result` 內容」**，`n.` 前綴看似像是入口，
但只回傳呼叫節點自己的 name/id/type，不能查詢別的節點。`abandoned` 標記也沒有
被寫進 `fw_workflow_variables`（`VariableService` 的權威儲存），所以 `${v.xxx}`
同樣讀不到。**結論：父流程目前完全沒有辦法判斷「子流程是被中止還是正常結束」**，
`abandoned` 標記是寫了但沒有任何讀取路徑的死資料。

**建議**（若採第三節的 A 案）：在 `_complete_parent_subflow_node()` 內，除了寫入
`result.data.abandoned`，額外呼叫
`VariableService.set_flow_var(parent_instance_code, f'{parent_node_id}_abandoned', True, org_code)`，
讓父流程能用 `${v.<SubFlow節點id>_abandoned}` 判斷。**本次未實作**（屬於「是否保留
Abandon」的決策範圍，briefing 要求不擅自執行）。

### 4.4 巢狀子流程（depth=2）

未做獨立於 4.1/4.2 之外的巢狀（depth=2）實測。但根據 `cancel_pending_nodes()` 用
`root_instance_code`（鏈式繼承，見 `test_cancel_pending_nodes_reaches_grandchild_instance`
既有測試）展開整棵樹的機制，可以合理推論：不論 Abandon 出現在哪一層，
`root_instance_code` 都指向最頂層主流程，取消範圍都會涵蓋整棵樹，行為與 depth=1
一致。**這是讀碼＋既有測試的推論，非本次重新實測**，建議主 Claude 或下次維護時
若有餘裕可以補一次三層巢狀的端到端驗證。

---

## 五、config 欄位表

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `wait_seconds` | number | 1 | 節點啟動後、執行中止邏輯前的等待秒數（給並行分支一點收尾時間）。**設計器面板有暴露**（`wf-accordion-flow.js::renderAbandonPanel()`，`<input type="number" min="0" max="300">`），但那只是前端 input 屬性，`node_config` 可被 `PUT /api/workflows/...` 等 graph 寫入端點直接改寫，後端本身**原本完全沒有驗證或夾限**（`workflow_node_definitions.config_schema` 對 Abandon 是空物件 `{}`，沒有 JSON schema 檢查）。塞 `wait_seconds: 86400` 會讓該節點對應的 `node_runner` 子行程 `time.sleep(86400)` 阻塞 24 小時——不影響其他節點（每節點是獨立子行程），但會讓這個 Abandon 節點形同失聯，流程無法真正結束，也浪費一個子行程的生命週期 |
| `finish_mode` | string | （無效） | 設計器面板的 `applyAbandonConfig()` 會寫入 `finish_mode: 'cancel'`，但 handler 完全不讀這個 key（`_handle_main_flow_abandon`/`_handle_subflow_abandon` 都是寫死 `'cancel'`），純粹是前端習慣性沿用 End 面板的欄位命名，對行為無影響 |

**本次已修（`abandon_handler.py`，2026-08-31）**：新增 `MAX_WAIT_SECONDS = 300`
（與設計器面板 `input[max]` 一致）與 `_clamp_wait_seconds()`，超過上限夾限並
`log_warning`；負值夾成 0；非數字型別回退預設值 1。**只改了 `abandon_handler.py`，
`end_handler.py` 有完全相同的缺口（`wait_seconds` 同樣無上限）未修**——那個檔案在本次
briefing 是「唯讀為主」的領地，建議主 Claude 決定是否要同步處理。

---

## 六、已驗證的行為清單（實測證據）

全部原始輸出見 `/opt/tmp/verify/20260831-abandon.log`。

| # | 驗證項目 | 方法 | 證據行號 |
|---|---|---|---|
| 1 | 並行分支下，RUNNING 的 OsExecutor（wait_for_result 模式）會被 Abandon 真正終止（OS process 消失） | 端到端：手動建立 workflow_instance + Start 分兩支（OsExecutor sleep 25 / Delay 3s->Abandon），交給正在跑的 `beakplatform-dev-executor` daemon 執行 | 1-67 |
| 2 | `fw_node_execution_logs` 對被牽連 cancel 的節點（node-OS-1）**沒有留下任何紀錄**，只有 Abandon 自己的兩筆 INFO log | 同上，查 `fw_node_execution_logs` join `fw_workflow_instances` | 46-57 |
| 3 | `cancel_pending_nodes`/`_terminate_node_process` 的執行細節（SIGTERM/SIGKILL 結果）**不進系統 journal**（stdout/stderr DEVNULL，在 node_runner 子行程內執行） | `journalctl -u beakplatform-dev-executor` 比對同時段 | 未單獨截取，見對話記錄 T+18s 附近 |
| 4 | 觸發 Abandon 的 workflow_instance 最終狀態是 `COMPLETED`，不是 `CANCELLED` | 同上，查 `fw_workflow_instances.status` | 44-45 |
| 5 | 子流程走到 Abandon：父流程 SubFlow 節點被推進、建立新節點，但同一輪 cancel 又把新節點與父流程本身標成 CANCELLED；子流程自己是 COMPLETED、父流程是 CANCELLED（狀態不一致） | 端到端：手動建 parent/child instance + queue items，模擬 SubFlow 已建立完成的狀態 | 834-851 |
| 6 | 找不到父節點 ID 時，父流程仍會被連帶 CANCELLED（不會卡住），前提是 root_instance_code 正確 | pytest：`test_subflow_abandon_missing_parent_node_id_still_cancels_real_parent` | `backend/tests/test_abandon_node.py` |
| 7 | `abandoned: true` 標記正確寫入父流程 SubFlow queue item 的 result，但變數解析（`f./fi./v./wi./n./t.`）沒有任何路徑能讀到它 | 讀碼：`base.py::replace_variables()` 全部前綴逐一核對 | `modules/form_workflow/services/node_handlers/base.py:355-570` |
| 8 | `wait_seconds` 修復前完全無上限、無驗證；`workflow_node_definitions.config_schema` 對 Abandon 是空物件 | 讀碼＋DB 查詢 | DB 查詢見對話記錄；grep 結果無輸出 |
| 9 | 主流程 Abandon 回傳結構、wait_seconds 夾限（86400→300、-5→0、非數字→1）、子流程喚醒父流程含 abandoned 標記、cancel 對同儕 RUNNING 節點的連鎖效應、cancel 完成後 form_instance 變成 APPROVED | pytest 8 項全綠 | `backend/tests/test_abandon_node.py`，log 456-863 |
| 10 | 既有 `test_workflow_cancel_mode.py` 5 項在本次改動後仍全綠（無回歸） | `bash scripts/run_tests.sh tests/test_abandon_node.py tests/test_workflow_cancel_mode.py -q` | 817-827 |

**未端到端實測、僅讀碼確認的項目**（建議主 Claude 視需要補驗）：

- `_stop_os_dispatched_units()` 對已 dispatch（`wait_for_result=false`）的 OsExecutor
  是否真的能 `systemctl stop`（需要 sudoers 對 `sudo -n systemctl` 的授權配合，
  本次為求時間效率沒有另建 dispatched 模式的測試流程）
- 三層以上巢狀子流程（depth≥2）的連鎖取消範圍
- 設計器實際點擊 Abandon 面板、輸入 wait_seconds、儲存、重新載入的 UI 互動
  （本次沒有 chrome-devtools MCP，只讀了面板原始碼）

---

## 七、已知限制與未決事項

**需要 Ethan 決策的項目**（不在本次授權範圍內擅自執行）：

1. **Abandon 是否保留**——第三節的 A（補上變數可讀性）/B（退役統一用 End cancel）二選一。
2. **cancel 模式下 workflow/form 狀態該不該有獨立的 CANCELLED/已中止狀態**，而不是
   共用 COMPLETED/APPROVED（第二節）。這是跨 `node_runner.py` 的架構變更，影響所有
   讀 `form_instance.status` 的前端（表單中心、流程管理頁），範圍遠超 Abandon 節點本身。
3. **`pg_cancel_backend()` 方案要不要做**（BBN atom 5303 / PF-173，Ethan 尚未回覆的
   選項）——影響 SysSqlExecutor 被 cancel 時是否真的能中斷已發動的查詢。

**本次已修，不需要再決策**：

- `wait_seconds` 後端上限保護（`abandon_handler.py`，300 秒）。

**本次記錄但未修**（在其他 session 或未來任務的領地內）：

- `end_handler.py` 的 `wait_seconds` 同樣無上限，本次 briefing 明確要求該檔以唯讀
  為主，只記錄不修改。
- handler 內「找不到父節點 ID」與「喚醒父流程拋例外」被吞成同一句籠統 log、且都
  回成功——建議至少讓後者（真正的例外）改回 `status: 'error'` 或在 log 內容上
  區分兩種情境，未在本次執行（涉及行為變更，非單純加保護）。
- handler 註解「子流程將中止但父流程可能卡住」的文字誤導性（第 4.2 節），
  建議修正但未執行（純文字風險低，可視為 10 行內微改，留給主 Claude 決定是否
  一併處理）。

**建議登記進 `dev-notes/NODE_TEST_INVENTORY.md`**（本次未直接修改該檔，
依 COMMON_RULES 禁止清單）：NT-17 Abandon 狀態從「未驗證」更新為「已驗證」，
備註指向本檔。
