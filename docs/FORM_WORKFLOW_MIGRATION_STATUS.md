# FormWorkflow 模組移轉進度報告

**來源專案**: `/opt/FormFlow/a6`
**目標專案**: `/opt/BeakPlatform/modules/form_workflow/`
**更新日期**: 2026-01-26

---

## 環境配置（已完成）

| 項目 | 值 |
|------|---|
| BeakPlatform Port | 7000 |
| 資料庫 | beakplatform_dev |
| systemd 服務 | beakplatform.service (enabled) |
| 訪問地址 | http://192.168.0.16:7000 |

BeakMask 已停止（port 5007, beakmask_dev）

---

## 模組結構（已建立）

```
/opt/BeakPlatform/modules/form_workflow/
├── __init__.py              ✓ MODULE_INFO + init_runtime()
├── models/
│   ├── __init__.py          ✓
│   ├── base.py              ✓ ModuleBaseModel
│   ├── form_template.py     ✓ FwFormTemplate
│   ├── form_instance.py     ✓ FwFormInstance
│   ├── workflow_template.py ✓ FwWorkflowTemplate
│   ├── workflow_instance.py ✓ FwWorkflowInstance
│   ├── workflow_variable.py ✓ FwWorkflowVariable
│   ├── node_execution_queue.py    ✓ FwNodeExecutionQueue
│   ├── node_execution_log.py      ✓ FwNodeExecutionLog
│   ├── approval_record.py         ✓ FwApprovalRecord
│   ├── form_workflow_mapping.py   ✓ FwFormWorkflowMapping
│   └── published_form_workflow.py ✓ FwPublishedFormWorkflow
├── services/
│   ├── __init__.py          ✓
│   ├── workflow_engine.py   ✓ WorkflowEngine
│   ├── workflow_executor.py ✓ WorkflowExecutor (背景輪詢)
│   ├── workflow_log_service.py ✓
│   ├── variable_service.py  ✓
│   ├── node_runner.py       ✓ subprocess 入口
│   └── node_handlers/       ✓ 27 個處理器
│       ├── factory.py
│       ├── base.py
│       ├── start_handler.py
│       ├── end_handler.py
│       ├── form_handler.py
│       ├── approval_handler.py
│       ├── email_handler.py
│       ├── telegram_handler.py
│       └── ... (其他節點處理器)
├── api/
│   ├── __init__.py          ✓ api_bp 註冊
│   ├── forms.py             ✓ 表單 CRUD API
│   ├── workflows.py         ✓ 工作流 CRUD API
│   ├── mappings.py          ✓ 配對 API
│   └── form_center.py       ✓ 表單中心 API
├── web/
│   └── __init__.py          ⚠ 只有空殼，缺頁面路由
└── templates/
    └── modules/             ⚠ 缺少前端模板
```

---

## 完成項目

### 1. 後端 API（已完成）
- [x] 表單模板 CRUD (`/api/forms/templates/`)
- [x] 工作流模板 CRUD (`/api/forms/workflows/`)
- [x] 配對管理 (`/api/mappings/`)
- [x] 表單中心 (`/api/form-center/`)
- [x] 發布/暫停/封存功能

### 2. 節點處理器（已完成，共 27 個）
- [x] Start, End, Form, Approval
- [x] Email, Telegram
- [x] FieldRead, FieldWrite, OpSet
- [x] Timer, Pause, Abandon
- [x] Condition, MultiCondition, Loop
- [x] SubFlow, Parallel, Gateway
- [x] Variable, Script, DataQuery
- [x] Notification, Webhook, SQLExecutor
- [x] SetVar, GetVar, VarOp

### 3. 工作流引擎（已完成）
- [x] WorkflowExecutor 背景輪詢
- [x] node_runner subprocess 執行
- [x] 變數服務 (GLOBAL/LOCAL)
- [x] 日誌服務
- [x] 自動推進到下一節點

### 4. 資料庫（已完成）
- [x] 10 個 fw_* 表已建立
- [x] 欄位已同步（手動遷移）

---

## 未完成項目

### 1. 前端頁面（未開始）
- [ ] 表單設計器頁面 (`/forms/templates/`)
- [ ] 流程設計器頁面 (`/forms/workflows/`)
- [ ] 配對管理頁面 (`/forms/mappings/`)
- [ ] 表單中心頁面 (`/forms/center/`)
- [ ] 我的表單頁面 (`/forms/my/`)
- [ ] 待簽核頁面 (`/forms/pending/`)

### 2. 前端資源
- [ ] 流程設計器 JS (Cytoscape.js)
- [ ] 表單設計器 JS (Form.io)
- [ ] 節點面板 UI
- [ ] CSS 樣式

### 3. 整合修正
- [ ] 錯誤頁面標題改為 BeakPlatform
- [ ] 選單項目實際可用
- [ ] 登入後權限檢查

---

## 已知問題

1. **BeakMask 殘留**: 錯誤頁面 title 還是 "BeakMask"
   - 檔案: `/opt/BeakPlatform/backend/app/templates/errors/*.html`

2. **Model vs DB 不一致**: 部分欄位需手動遷移
   - 已處理: fw_workflow_instances, fw_form_instances 新增欄位

3. **前端模板缺失**: `form_workflow/templates/` 基本為空

---

## 參考來源

A6 專案前端位置：
- 表單設計器: `/opt/FormFlow/a6/frontend/templates/form-designer.html`
- 流程設計器: `/opt/FormFlow/a6/frontend/templates/workflow-designer.html`
- 表單中心: `/opt/FormFlow/a6/frontend/templates/form-center.html`
- 靜態資源: `/opt/FormFlow/a6/frontend/static/`

---

## 下一步建議

1. **優先處理前端頁面移轉**
   - 從 A6 複製並修改模板
   - 調整 API 路徑和認證方式

2. **修正 BeakMask 殘留文字**
   - 全專案搜尋替換

3. **測試完整流程**
   - 建立表單 → 設計流程 → 配對 → 發布 → 填寫 → 簽核

---

## 重要檔案清單

| 類型 | 路徑 |
|------|------|
| 模組入口 | `/opt/BeakPlatform/modules/form_workflow/__init__.py` |
| API 註冊 | `/opt/BeakPlatform/modules/form_workflow/api/__init__.py` |
| 執行器 | `/opt/BeakPlatform/modules/form_workflow/services/workflow_executor.py` |
| 節點工廠 | `/opt/BeakPlatform/modules/form_workflow/services/node_handlers/factory.py` |
| 服務檔 | `/opt/BeakPlatform/beakplatform.service` |
| 重啟腳本 | `/opt/BeakPlatform/restart_flask.sh` |

---

*此文件由 Claude Code 自動生成*
