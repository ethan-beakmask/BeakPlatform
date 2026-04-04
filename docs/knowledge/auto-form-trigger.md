# 自動單 -- 程式觸發表單流程

> 建立日期：2026-04-05
> 狀態：規格草案

## 概述

「自動單」指由背景程式（非人工操作）自動發起的表單流程。
典型場景：資安事件偵測後，程式依據風險判斷結果自動建立表單，走簽核或僅留存記錄。

---

## 應用場景範例

**高權限帳號登入風險評估**

```
SIEM / Log 偵測到高權限用戶登入
  |
  v
背景程式比對：
  - 是否有對應的申請記錄（變更單、維護申請）
  - 是否在上班時間內
  - 來源 IP 是否在白名單
  - 是否為假日 / 非常規時段
  |
  v
風險判斷
  |
  +-- 低風險 --> 建立「自動單」僅留存記錄，流程自動結束
  |
  +-- 中風險 --> 建立「自動單」通知管理者確認
  |
  +-- 高風險 --> 建立「自動單」走緊急簽核流程
```

---

## 觸發方式

### 方式一：start_workflow() -- 有表單資料

先建立 `FwFormInstance`，再啟動流程。適用於需要填入偵測資料（IP、時間、帳號等）的場景。

**位置**: `modules/form_workflow/services/workflow_engine.py:67`

```python
from modules.form_workflow.services.workflow_engine import WorkflowEngine
from modules.form_workflow.models import FwFormInstance
from app.extensions import db

# 1. 建立表單實例
form_instance = FwFormInstance(
    org_secure_code='企業SC',
    form_template_secure_code='表單模板SC',
    applicant_secure_code='系統帳號SC',      # 觸發的系統帳號
    applicant_name='資安自動偵測',
    subject='高權限登入風險評估 - admin@10.0.0.5',
    form_data={
        'event_type': 'privileged_login',
        'username': 'admin',
        'source_ip': '10.0.0.5',
        'login_time': '2026-04-05T02:30:00+08:00',
        'risk_level': 'medium',
        'risk_factors': ['非上班時間', '無對應申請記錄'],
        'matched_rules': ['RULE-PLG-001'],
    },
    status='INITIAL',
    source_type='SYSTEM',
)
db.session.add(form_instance)
db.session.flush()

# 2. 啟動流程
workflow_instance = WorkflowEngine.start_workflow(
    form_instance_secure_code=form_instance.secure_code,
    workflow_template_secure_code='流程模板SC',   # 可選，不給會自動查配對
    is_test=False
)
```

### 方式二：start_pure_workflow() -- 純流程、無表單模板

不需預先建表單，引擎自動建立記錄用的 FormInstance。適用於只走流程、不需要表單欄位的場景。

**位置**: `modules/form_workflow/services/workflow_engine.py:201`

```python
from modules.form_workflow.services.workflow_engine import WorkflowEngine

workflow_instance = WorkflowEngine.start_pure_workflow(
    workflow_template_secure_code='流程模板SC',
    org_secure_code='企業SC',
    applicant_secure_code='系統帳號SC',
    applicant_name='資安自動偵測'
)
```

---

## 觸發後的自動執行鏈

```
程式呼叫 start_workflow / start_pure_workflow
  |
  v
建立 FwWorkflowInstance (status=RUNNING)
建立 FwNodeExecutionQueue (status=PENDING, node_type=Start)
db.session.commit()
  |
  v
WorkflowExecutor (背景常駐，每 5 秒輪詢)
  撈到 PENDING 節點
  |
  v
node_runner.py (subprocess)
  執行 Start 節點 -> 推進到下一節點
  |
  v
依流程圖自動推進：
  通知節點 / 簽核節點 / 條件分支 / 結束節點...
```

---

## 前提條件

### Flask App Context

背景程式必須在 Flask app context 內執行（ORM 和 DB 需要）：

```python
from backend.app import create_app

app = create_app()
with app.app_context():
    # 在這裡呼叫 start_workflow / start_pure_workflow
    ...
```

### 必要參數

| 參數 | 來源 | 說明 |
|------|------|------|
| `org_secure_code` | `organizations` 表 | 目標企業識別碼 |
| `workflow_template_secure_code` | `fw_workflow_templates` 表 | 要觸發的流程模板 |
| `form_template_secure_code` | `fw_form_templates` 表 | 表單模板（方式一需要） |
| `applicant_secure_code` | `users` 表 | 系統帳號 SC（建議建立專用系統帳號） |

### 流程模板設計要點

自動單的流程模板需要配合設計：

- **條件節點**：根據 `form_data` 中的 `risk_level` 分支
  - 低風險 -> End（僅記錄）
  - 中/高風險 -> Approve 節點（通知管理者）
- **簽核人**：可用 DYNAMIC assignee，由 form_data 帶入
- **超時處理**：自動單建議設定 `timeout_action`，避免卡關

---

## 方式選擇

| | start_workflow | start_pure_workflow |
|---|---|---|
| 需要填入偵測資料 | O | X（form_data 僅 `_workflow_record: True`） |
| 需要表單模板 | O | X |
| 自動建立 FormInstance | X（自己建） | O |
| 適用場景 | 資安事件帶完整上下文 | 純通知 / 純審批 |

資安自動單通常選 **方式一**，因為需要在表單中呈現事件細節供審核者判讀。

---

*最後更新：2026-04-05*
