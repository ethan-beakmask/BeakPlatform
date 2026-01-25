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
│   ├── mappings.py          ✓ 配對 API（含 unmapped-forms, workflows-for-mapping）
│   └── form_center.py       ✓ 表單中心 API
├── web/
│   └── __init__.py          ✓ 11 個 Web 路由
└── templates/
    └── modules/form_workflow/
        ├── dashboard.html       ✓ 儀表板
        ├── template_list.html   ✓ 表單模板列表
        ├── workflow_list.html   ✓ 工作流列表
        ├── mappings_list.html   ✓ 配對管理（新增）
        ├── form_center.html     ✓ 表單中心（新增）
        ├── instance_list.html   ✓ 我的表單
        ├── pending_list.html    ✓ 待簽核
        ├── form_designer.html   ✓ 表單設計器
        └── workflow_designer.html ✓ 工作流設計器
```

---

## 完成項目

### 1. 後端 API（已完成）
- [x] 表單模板 CRUD (`/api/form-workflow/templates/`)
- [x] 工作流模板 CRUD (`/api/form-workflow/workflows/`)
- [x] 配對管理 (`/api/mappings/`)
- [x] 表單中心 (`/api/form-center/`)
- [x] 發布/暫停/封存功能
- [x] 未配對表單列表 (`/api/mappings/unmapped-forms`)
- [x] 可配對流程列表 (`/api/mappings/workflows-for-mapping`)

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

### 5. 前端頁面（已完成）
- [x] 儀表板 (`/forms/dashboard`)
- [x] 表單模板列表 (`/forms/templates`)
- [x] 工作流列表 (`/forms/workflows`)
- [x] 配對管理頁面 (`/forms/mappings`) - 2026-01-26 新增
- [x] 表單中心頁面 (`/forms/center`) - 2026-01-26 新增
- [x] 我的表單頁面 (`/forms/instances`)
- [x] 待簽核頁面 (`/forms/pending`)
- [x] 表單設計器 (`/forms/templates/<code>`)
- [x] 工作流設計器 (`/forms/workflows/<code>`)

### 6. 整合修正（已完成）
- [x] 錯誤頁面標題改為 BeakPlatform - 2026-01-26
- [x] 主要 layout 標題改為 BeakPlatform - 2026-01-26
- [x] 登入頁面標題改為 BeakPlatform - 2026-01-26

### 7. 工作流設計器移植（已完成）- 2026-01-26
- [x] 複製靜態資源（CSS、JS、SVG 圖標）
- [x] 複製並調整設計器模板
- [x] 調整 API 路徑對應
- [x] 節點定義 API 按分類分組返回
- [x] 新增流程後自動跳轉到設計器
- [x] 編輯按鈕跳轉到設計器

### 8. 表單設計器移植（已完成）- 2026-01-26
- [x] 複製 Form.io 主題 CSS
- [x] 複製並調整表單設計器模板
- [x] 添加 designer/standalone 路由
- [x] 添加 categories API
- [x] 新增表單後自動跳轉到設計器
- [x] 編輯按鈕跳轉到設計器

---

## 待完成項目

### 1. 前端資源優化
- [ ] 流程設計器節點面板 UI 優化
- [ ] 表單設計器欄位面板優化

### 2. 完整流程測試
- [ ] 建立表單 → 設計流程 → 配對 → 發布 → 填寫 → 簽核

---

## Web 路由清單

| 路由 | 頁面 | 狀態 |
|------|------|------|
| `/forms/` | 儀表板 | ✓ |
| `/forms/dashboard` | 儀表板 | ✓ |
| `/forms/templates` | 表單模板列表 | ✓ |
| `/forms/templates/<code>` | 表單設計器 | ✓ |
| `/forms/workflows` | 工作流列表 | ✓ |
| `/forms/workflows/<code>` | 工作流設計器 | ✓ |
| `/forms/mappings` | 配對管理 | ✓ |
| `/forms/center` | 表單中心 | ✓ |
| `/forms/instances` | 我的表單 | ✓ |
| `/forms/pending` | 待簽核 | ✓ |

---

## 重要檔案清單

| 類型 | 路徑 |
|------|------|
| 模組入口 | `/opt/BeakPlatform/modules/form_workflow/__init__.py` |
| API 註冊 | `/opt/BeakPlatform/modules/form_workflow/api/__init__.py` |
| Web 路由 | `/opt/BeakPlatform/modules/form_workflow/web/__init__.py` |
| 執行器 | `/opt/BeakPlatform/modules/form_workflow/services/workflow_executor.py` |
| 節點工廠 | `/opt/BeakPlatform/modules/form_workflow/services/node_handlers/factory.py` |
| 服務檔 | `/opt/BeakPlatform/beakplatform.service` |
| 重啟腳本 | `/opt/BeakPlatform/restart_flask.sh` |
| 工作流設計器 CSS | `/opt/BeakPlatform/backend/app/static/css/workflow-designer.css` |
| 工作流設計器 JS | `/opt/BeakPlatform/backend/app/static/js/workflow-main.js` |
| 節點圖標 | `/opt/BeakPlatform/backend/app/static/icons/workflow/*.svg` |
| Form.io 主題 CSS | `/opt/BeakPlatform/backend/app/static/css/formio-theme.css` |

---

*最後更新: 2026-01-26 (表單設計器移植完成)*
