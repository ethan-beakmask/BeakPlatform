# 簽核流程執行順序

> 建立日期：2026-01-22
> 狀態：持續更新中

## 概述

本文件記錄表單簽核流程的完整執行順序，包含前端、API、流程引擎、背景服務的互動關係。

---

## 執行順序

### 階段一：顯示待簽核列表

```
1. form_center.py (list_pending_approvals)
   - 查詢 NodeExecutionQueue
   - 條件：node_type=APPROVE, status=RUNNING-WAITING, assignee_ids 包含當前用戶
   - 返回：待簽核項目列表、edges（可選路徑）、selection_mode
```

### 階段二：開啟簽核對話框

```
2. center.html (openApproval)
   - 設定 approvalDialog 狀態
   - 根據 selection_mode 決定單選/多選模式

3. form_center.py (get_approval_form)
   - 返回表單詳情、builder_config、edges、selection_mode
```

### 階段三：提交簽核

```
4. form_center.py (execute_approval)
   - 接收：queue_id, decision, selected_edges, comment
   - 更新 node_queue.result = {decision, selected_edges, approver, ...}
   - 重設 node_queue.status = INITIAL（讓 executor 重新執行）
```

### 階段四：流程引擎處理

```
5. workflow_executor.py (背景輪詢)
   - 每 5 秒輪詢 INITIAL/PENDING 狀態的節點
   - 撈取待處理節點

6. node_runner.py (subprocess)
   - 獨立 subprocess 執行單一節點
   - 載入對應的 handler

7. approve.py (_handle_decision)
   - 檢查 result 中的 selected_edges
   - 若有 selected_edges：返回 ExecutionResult(next_edge_ids=selected_edges)
   - 若無：使用 decision 對應的 edge label

8. graph_utils.py (get_targets_by_edge_ids)
   - 根據邊 ID 列表找出目標節點

9. engine.py / node_runner.py
   - 根據 next_edge_ids 建立下一節點的執行佇列
   - 若使用 next_edge_label，則用 get_target_by_edge_label 匹配
```

### 階段五：流程完成與歸檔

```
10. workflow_executor.py (_check_and_archive_completed_workflows)
    - 每 60 秒檢查已完成流程
    - 將 NodeExecutionQueue 複製到 NodeExecutionQueueArchive
    - 日誌保留（node_queue_id 設為 NULL）
    - 刪除原始佇列記錄
```

### 階段六：監控與視覺化

```
11. workflow_monitoring.py (get_execution_graph)
    - 從 archive 表取得節點狀態
    - 從 result.selected_edges 取得已執行的邊
    - 返回 elements（含 executed 標記）

12. center.html (renderGraph)
    - Cytoscape.js 渲染流程圖
    - 已執行邊：綠色粗線高亮
    - 節點依狀態上色（COMPLETED=綠、RUNNING=橘、ERROR=紅）
```

---

## 關鍵檔案

| 層級 | 檔案 | 職責 |
|------|------|------|
| API | `form_center.py` | 待簽核列表、簽核詳情、執行簽核 |
| API | `workflow_monitoring.py` | 監控日誌、流程圖 |
| Handler | `approve.py` | APPROVE 節點執行邏輯 |
| Engine | `engine.py` | 流程引擎核心 |
| Engine | `node_runner.py` | 節點執行器（subprocess） |
| Engine | `graph_utils.py` | 流程圖工具函數 |
| Engine | `executor.py` | ExecutionResult 定義 |
| Service | `workflow_executor.py` | 背景輪詢、歸檔 |
| Frontend | `center.html` | 表單中心 UI |

---

## 資料流

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│    API      │────▶│   Database  │
│ center.html │     │form_center  │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐             │
                    │  Executor   │◀────────────┘
                    │ (背景服務)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ node_runner │
                    │ (subprocess)│
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Handler    │
                    │ approve.py  │
                    └─────────────┘
```

---

## 狀態轉換

### NodeExecutionQueue.status

```
INITIAL ──▶ RUNNING ──▶ RUNNING-WAITING ──▶ INITIAL ──▶ RUNNING ──▶ COMPLETED
   │                         │                              │
   │      (等待簽核)          │         (簽核後)              │
   └─────────────────────────┴──────────────────────────────┘
```

### 簽核節點生命週期

1. **INITIAL**：節點剛建立，等待 executor 撈取
2. **RUNNING**：executor 啟動 node_runner 執行
3. **RUNNING-WAITING**：等待用戶簽核
4. **INITIAL**：用戶簽核後重設，等待再次執行
5. **RUNNING**：executor 再次執行，處理簽核結果
6. **COMPLETED**：根據 selected_edges 建立下一節點後完成

---

## 多選模式（Parallel Fork）處理流程

### 並行分支概述

並行分支允許流程同時執行多條路徑，適用於需要多部門/多人同時處理的場景。

### 相關節點類型

| 節點類型 | 說明 | Handler |
|---------|------|---------|
| PARALLEL_FORK | 分支節點，將流程分成多條並行路徑 | `parallel.py:ParallelForkExecutor` |
| PARALLEL_JOIN | 匯合節點，等待並行路徑完成後繼續 | `parallel.py:ParallelJoinExecutor` |

### 執行流程

```
1. PARALLEL_FORK 執行
   - 取得所有出邊目標節點
   - 記錄分支資訊到流程變數 (_fork_{node_id})
   - 返回 ExecutionResult.success_parallel(next_node_ids=[...])
   - 所有目標節點同時建立執行佇列（INITIAL 狀態）

2. 各分支並行執行
   - WorkflowExecutor 輪詢時同時啟動多個分支
   - 各分支獨立執行，互不影響

3. PARALLEL_JOIN 等待
   - 檢查所有入邊來源節點的完成狀態
   - join_mode 配置：
     - "all": 等待全部分支完成（預設）
     - "any": 任一分支完成即可繼續
   - 未完成時返回 RUNNING-WAITING 狀態
```

### PARALLEL_FORK 配置

```json
{
  "branches": ["branch1", "branch2"]  // 可選，指定分支名稱
}
```

### PARALLEL_JOIN 配置

```json
{
  "join_mode": "all",        // "all" 或 "any"
  "timeout_seconds": 3600    // 超時秒數（可選）
}
```

### 簽核多選模式

簽核節點也支援多選模式，允許同時選擇多條後續路徑：

```
1. 設計器配置
   - selection_mode: "single" | "multiple"
   - 多選時前端顯示 checkbox，單選時顯示 radio

2. 提交簽核時
   - API 接收 selected_edges: ["edge-4", "edge-5"]
   - 存入 node_queue.result

3. Handler 處理
   - _handle_decision() 檢查 result.selected_edges
   - 若有值：返回 ExecutionResult(next_edge_ids=selected_edges)
   - 引擎呼叫 graph_utils.get_targets_by_edge_ids()
   - 建立多個目標節點的執行佇列
```

### 資料流

```
┌──────────────┐
│ PARALLEL_FORK│
└──────┬───────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
┌───┐     ┌───┐
│ A │     │ B │   (並行執行)
└─┬─┘     └─┬─┘
  │         │
  └────┬────┘
       │
       ▼
┌──────────────┐
│ PARALLEL_JOIN│  (等待 A、B 完成)
└──────────────┘
```

---

## 子流程（Subflow）執行順序

### 概述

子流程允許將複雜流程拆分成可重用的模組，主流程可以呼叫子流程並等待其完成。

### 相關檔案

| 檔案 | 職責 |
|------|------|
| `subprocess.py` | SUBPROCESS/SUBFLOW 節點執行器 |
| `engine.py:start_workflow()` | 啟動子流程實例 |
| `engine.py:_notify_parent_workflow()` | 子流程完成通知父流程 |

### 節點配置

```json
{
  "subflow_template_id": "xxx",    // 子流程範本 secure_code
  "wait_for_completion": true,      // 是否等待完成
  "pass_variables": ["var1"],       // 傳遞給子流程的變數
  "return_variables": ["result1"]   // 從子流程返回的變數
}
```

### 執行順序

```
階段一：啟動子流程

1. SubprocessExecutor.execute()
   - 檢查 subflow_template_id 配置
   - 查詢 WorkflowTemplate（必須 is_subprocess=True）
   - 呼叫 WorkflowEngine.start_workflow()
     - parent_instance 參數傳遞父流程實例
     - 計算 workflow_depth（深度 +1）
     - 檢查深度限制（max_subprocess_depth）
   - 記錄 node_queue.calling_instance_id = 子流程 ID
   - 若 wait_for_completion=True，返回 RUNNING-WAITING

階段二：子流程執行

2. 子流程獨立執行
   - 與一般流程相同的執行順序
   - 有自己的 execution_code
   - 共享 form_instance

階段三：子流程完成

3. engine.py:_complete_workflow()
   - 檢查 parent_instance_id
   - 呼叫 _notify_parent_workflow()

4. engine.py:_notify_parent_workflow()
   - 查詢父流程中等待的節點
     - calling_instance_id = 子流程 ID
     - status = RUNNING-WAITING
   - 更新 waiting_node.result
   - 設定 status = RUNNING（讓 executor 重新執行）

階段四：父流程繼續

5. SubprocessExecutor.execute()（第二次執行）
   - 檢查 calling_instance_id 已設定
   - 查詢子流程狀態
   - 若已完成：根據 end_mode 決定下一條邊
     - approved → 'approved'
     - rejected → 'rejected'
     - cancelled → 'cancelled'
     - 其他 → 'default'
```

### 父子關係

```
WorkflowInstance 關聯：
- parent_instance_id: 父流程 ID（子流程才有）
- root_instance_id: 根流程 ID（巢狀子流程用）
- workflow_depth: 目前深度（0=主流程, 1=一層子流程...）
- child_instances: 所有子流程列表（relationship）
```

### 資料流

```
┌─────────────────────────────────────────────────────┐
│ 主流程 (depth=0)                                     │
│                                                      │
│   ┌───────┐    ┌───────────┐    ┌───────┐           │
│   │ START │───▶│ SUBPROCESS│───▶│  ...  │           │
│   └───────┘    └─────┬─────┘    └───────┘           │
│                      │                               │
└──────────────────────│───────────────────────────────┘
                       │
                       ▼ 啟動子流程
┌─────────────────────────────────────────────────────┐
│ 子流程 (depth=1)                                     │
│                                                      │
│   ┌───────┐    ┌─────────┐    ┌───────┐             │
│   │ START │───▶│ APPROVE │───▶│  END  │             │
│   └───────┘    └─────────┘    └───────┘             │
│                                     │               │
└─────────────────────────────────────│───────────────┘
                                      │
                                      ▼ 通知父流程
```

---

## 超時處理流程

### 超時機制概述

系統支援兩種超時場景：
1. **DELAY 節點**：等待指定時間後自動繼續
2. **APPROVE 節點**：超過期限自動處理（核准/駁回/上報）

### 相關檔案

| 檔案 | 職責 |
|------|------|
| `delay.py` | DELAY 節點執行器 |
| `approve.py:on_timeout()` | 簽核超時處理 |
| `workflow_executor.py:_poll_timeout_nodes()` | 喚醒超時節點 |
| `executor.py:NodeExecutor.on_timeout()` | 超時處理介面 |

### DELAY 節點超時

```
1. 首次執行
   - 計算 resume_at 時間（根據 delay_type）
   - 設定 node_queue.timeout_at = resume_at
   - 返回 PENDING 狀態（程式結束，節省 CPU/RAM）

2. WorkflowExecutor 喚醒
   - _poll_timeout_nodes() 每 60 秒檢查
   - 條件：status=PENDING, timeout_at <= now
   - 重新啟動 subprocess 執行

3. 二次執行
   - 檢查 timeout_at 已到期
   - 返回 success_continue() 繼續流程
```

DELAY 配置：

```json
{
  "delay_type": "fixed",       // fixed | until_time | until_date
  "delay_value": 300,          // 秒數（fixed 模式）
  "until_time": "09:00",       // 時間（until_time 模式）
  "until_date": "2024-12-25",  // 日期（until_date 模式）
  "timezone": "Asia/Taipei"
}
```

### APPROVE 節點超時

```
1. 首次執行
   - 計算 timeout_at = now + timeout_hours
   - 進入 RUNNING-WAITING 等待簽核

2. 超時觸發（尚未實作自動觸發）
   - TODO: WorkflowExecutor 檢查簽核超時
   - 呼叫 ApproveExecutor.on_timeout()

3. 超時處理（approve.py:on_timeout）
   - timeout_action: "auto_approve"
     → 返回 next_edge_label='approved'
   - timeout_action: "auto_reject"（預設）
     → 返回 next_edge_label='rejected'
   - timeout_action: "escalate"
     → 保持等待，上報處理（TODO）
```

APPROVE 超時配置：

```json
{
  "timeout_hours": 48,
  "timeout_action": "auto_reject"  // auto_approve | auto_reject | escalate
}
```

### 超時輪詢機制

```
WorkflowExecutor._poll_timeout_nodes()
│
├─ 查詢條件：
│   - status = PENDING
│   - timeout_at IS NOT NULL
│   - timeout_at <= now
│
├─ 對每個節點：
│   1. 檢查流程是否已終止
│   2. 若已終止：標記 COMPLETED_CANCELLED
│   3. 若未終止：重新啟動 subprocess
│
└─ 輪詢間隔：PENDING_POLL_INTERVAL_SECONDS (60秒)
```

---

## 錯誤處理與重試機制

### 錯誤處理層級

```
層級 1: Handler 內部處理
├─ 捕捉異常，返回 ExecutionResult.failure(error_message)
└─ 記錄錯誤日誌 context.log_error()

層級 2: node_runner.py 處理
├─ try-except 捕捉 execute_handler() 異常
├─ 呼叫 handle_error() 更新狀態
└─ node_queue.status = ERROR

層級 3: engine.py 處理
├─ _execute_node() 捕捉異常
├─ node_queue.set_error(str(e))
└─ db.session.commit()

層級 4: workflow_executor.py 處理
├─ _poll_and_execute() 捕捉異常
├─ 記錄錯誤日誌
└─ 繼續處理其他節點（不中斷輪詢）
```

### 錯誤狀態更新

```python
# 節點層級
node_queue.status = NodeStatus.ERROR
node_queue.error_message = error_message
node_queue.completed_at = datetime.utcnow()
node_queue.result = result.result_data

# 流程層級
workflow_instance.status = WorkflowInstanceStatus.ERROR
workflow_instance.error_message = error_message
workflow_instance.error_node_id = node_queue.node_id
```

### ExecutionResult.failure()

```python
@classmethod
def failure(cls, error_message: str) -> 'ExecutionResult':
    """執行失敗"""
    return cls(
        success=False,
        completed=True,
        error_message=error_message,
        node_status='ERROR'
    )
```

### 錯誤處理流程

```
1. Handler 執行出錯
   ↓
2. 返回 ExecutionResult.failure('錯誤訊息')
   ↓
3. update_result() 處理
   - node_queue.status = ERROR
   - workflow_instance.status = ERROR
   ↓
4. 流程停止，等待人工處理
```

### 錯誤恢復（現況）

目前系統**沒有自動重試機制**，錯誤節點需要人工處理：

1. 查看錯誤日誌確認原因
2. 修復問題（資料、配置、外部服務）
3. 手動將節點狀態改回 INITIAL
4. WorkflowExecutor 會重新執行

---

## 變數傳遞機制

### 概述

流程變數允許節點間傳遞資料，支援動態決策和資料處理。

### 相關元件

| 元件 | 說明 |
|------|------|
| `WorkflowVariable` | 流程變數 Model |
| `ExecutionContext.variables` | 執行時變數字典 |
| `ExecutionResult.variables_to_update` | 節點執行後更新的變數 |
| `engine.py:_load_variables()` | 載入流程變數 |
| `engine.py:_update_variables()` | 更新流程變數 |

### WorkflowVariable Model

```python
class WorkflowVariable(db.Model):
    id: int
    org_secure_code: str
    workflow_instance_id: int
    var_name: str              # 變數名稱
    var_value: Any             # 變數值（JSON）
    scope: VariableScope       # GLOBAL / NODE / FORM
    created_at: datetime
    updated_at: datetime
```

### 變數作用域

| 作用域 | 說明 |
|--------|------|
| GLOBAL | 整個流程共享 |
| NODE | 特定節點內部使用 |
| FORM | 來自表單資料 |

### 變數傳遞流程

```
1. 載入變數（節點執行前）
   ├─ engine.py:_load_variables()
   ├─ 查詢 WorkflowVariable（workflow_instance_id）
   └─ 組成 dict 傳入 ExecutionContext.variables

2. 節點使用變數
   ├─ context.variables['var_name']
   ├─ context.form_data['field_name']  // 表單資料
   └─ 動態簽核人：config.assignee_variable

3. 節點更新變數
   ├─ 返回 ExecutionResult(variables_to_update={'key': 'value'})
   └─ PARALLEL_FORK 範例：
      variables_to_update={
          f'_fork_{context.node_id}': {
              'fork_node_id': context.node_id,
              'branch_count': len(next_node_ids),
              ...
          }
      }

4. 儲存變數（節點執行後）
   ├─ engine.py:_update_variables() / node_runner.py:update_result()
   ├─ 已存在：更新 var_value, updated_at
   └─ 不存在：建立新 WorkflowVariable
```

### 內建變數

| 變數名稱 | 設定者 | 說明 |
|---------|--------|------|
| `_fork_{node_id}` | PARALLEL_FORK | 分支資訊 |

### 表單資料存取

```python
# ExecutionContext 中
@property
def form_data(self) -> Dict[str, Any]:
    """取得表單資料"""
    return self.form_instance.form_data or {}

# Handler 中使用
amount = context.form_data.get('amount', 0)
applicant_name = context.form_data.get('applicant_name')
```

### 動態簽核人範例

```json
// 節點配置
{
  "assignee_type": "DYNAMIC",
  "assignee_value": "next_approver"  // 變數名稱
}

// 前一節點設定變數
ExecutionResult.success_continue(
    variables_to_update={
        'next_approver': ['user-abc', 'user-xyz']
    }
)

// ApproveExecutor 解析
var_name = config.get('assignee_value')  # 'next_approver'
dynamic_ids = context.variables.get(var_name)  # ['user-abc', 'user-xyz']
```

### 資料流圖

```
┌─────────────────┐
│ WorkflowVariable│  (資料庫)
└────────┬────────┘
         │
         ▼ _load_variables()
┌─────────────────┐
│ context.variables│  (dict)
└────────┬────────┘
         │
         ▼ handler 讀取/寫入
┌─────────────────┐
│ result.variables│
│ _to_update      │
└────────┬────────┘
         │
         ▼ _update_variables()
┌─────────────────┐
│ WorkflowVariable│  (資料庫)
└─────────────────┘
```

---

*最後更新：2026-01-23*
