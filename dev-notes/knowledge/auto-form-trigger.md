# 外部發動表單 -- 程式觸發表單流程（自動單）

> 建立日期：2026-04-05
> 最後更新：2026-07-07
> 狀態：現況文件（已對照程式碼驗證）

## 概述

「外部發動表單」（自動單）指由程式（非人工 UI 操作）發起的表單流程，分兩類：

| 類別 | 觸發路徑 | 認證 | 典型來源 |
|------|---------|------|---------|
| **一般表單** | 表單中心 Submit API（HTTP） | 平台帳號 session cookie | 內部自動化、排程程式、批次開單 |
| **資安表單** | Open Defense Intake Webhook（HTTP） | HMAC-SHA256 簽章（Intake Key） | SIEM / Suricata / Coraza / Falco 等偵測端 |

兩條路徑殊途同歸：建立 `FwFormInstance` + `FwWorkflowInstance`（status=RUNNING）+ Start 節點入 `FwNodeExecutionQueue`（status=PENDING），之後由 `workflow_executor` 背景執行緒（隨 Flask app 啟動，`modules/form_workflow/__init__.py`）輪詢推進。**送出成功後不需任何額外動作，流程自動跑。**

完整的 HTTP 操作細節（curl 範例、欄位規格、錯誤碼）見 `dev-notes/integrations/quick_form_submit_api.md`，本文件聚焦架構與選型。

---

## 應用場景範例

**高權限帳號登入風險評估（資安表單）**

```
SIEM / Log 偵測到高權限用戶登入
  |
  v
偵測端比對：
  - 是否有對應的申請記錄（變更單、維護申請）
  - 是否在上班時間內 / 來源 IP 是否在白名單
  |
  v
風險判斷 → 以 OCSF 事件 POST 到 Intake Webhook
  |
  +-- 低風險 --> 流程模板條件分支 → End（僅留存記錄）
  |
  +-- 中風險 --> 通知節點 → 管理者確認
  |
  +-- 高風險 --> 緊急簽核流程
```

風險分支邏輯放在**流程模板的條件節點**（依 `form_data` 欄位判斷），偵測端只負責送事件。

---

## 路徑一：一般表單 -- 表單中心 Submit API

- **端點**：`POST /api/form-center/submit`（`modules/form_workflow/api/fc_fill.py`，`@csrf.exempt`）
- **認證**：先 `POST /auth/login`（JSON）取得 session cookie，帳號格式 `username@domain_name`
- **必要參數**：`published_secure_code`（正式）或 `mapping_secure_code`（測試）二選一 + `subject` + 選填 `form_data`
- **序號**：由 NumberingService 自動編（`FORM-YYYYMMDD-NNNNN` / 流程 `PROC-YYYYMMDD-NNNN`）
- **限制**：表單必須已發行（Published）；一般用戶僅能送 `fw_mapping_permissions` 授權的表單
- 建議為自動化建立**專用系統帳號**，權限只授予目標表單

```python
import requests

BASE = 'http://192.168.0.16:7000/beakplatform'
s = requests.Session()
s.post(f'{BASE}/auth/login', json={'account': 'bot@acme.com.tw', 'password': '...'}).raise_for_status()
r = s.post(f'{BASE}/api/form-center/submit', json={
    'published_secure_code': '<published_sc>',
    'subject': '自動化開單',
    'form_data': {'field_a': 'value'},
})
print(r.json())  # data.execution_code 即流程編號
```

## 路徑二：資安表單 -- Open Defense Intake Webhook

- **端點**：`POST /api/open_defense/intake`（`modules/open_defense/api/intake.py`）
- **認證**：HMAC-SHA256（`X-OD-Key-Id` / `X-OD-Timestamp` / `X-OD-Signature`），簽章內容 `"{timestamp}\n{原始 body bytes}"`，5 分鐘時效
- **前置設定**（UI 一次性）：建 Intake Key + 來源白名單；設 `event_class → form_template` mapping（`OdFormTemplateMapping`）；表單須已發行
- **事件格式**：OCSF 子集，必填 `correlation_id`（冪等鍵）、`source_system`、`event_class`、`occurred_at`、`severity_id`、`finding.title`
- **與路徑一差異**：申請人固定 `OpenDefense Webhook`（無平台帳號）、`source_type='WEBHOOK_OD'`、序號 `OD-YYYYMMDD-*`、`form_data` 由 `intake_service._build_form_data()` 從事件抽取（不可自由傳入）
- 對外契約：`dev-notes/integrations/open_defense_contract.md`

## 選型

| 判斷 | 用路徑 |
|------|--------|
| 觸發端是外部安全偵測系統、事件為 OCSF 形態 | 二（Webhook） |
| 觸發端是平台內部/同主機自動化，要自由控制 form_data | 一（Submit API） |
| 需要測試模式（不進正式資料） | 一（`mapping_secure_code`，序號 TEST-*） |

---

## 附錄：In-Process 直接呼叫（僅限平台內部程式）

在 Flask app context 內可直接呼叫引擎，跳過 HTTP 層。**僅適用於平台自身的背景程式**（如排程節點、模組內部邏輯）；外部程式一律走上述 HTTP 路徑。

### WorkflowEngine.start_workflow() -- 有表單資料

**位置**：`modules/form_workflow/services/workflow_engine.py:67`

自行建立 `FwFormInstance` 時注意（`modules/form_workflow/models/form_instance.py`）：

- `serial_number` 為 **NOT NULL + unique**，必須自行編號（建議走 NumberingService，參考 `fc_fill.py` 的做法）
- `form_data` 為 NOT NULL
- `source_type` 現行已用值：`WEB`（表單中心）、`WEBHOOK_OD`（Open Defense）；自動程式建議自訂如 `SYSTEM` 並保持一致
- `is_test` 參數預設為 `True`，正式單要明確傳 `is_test=False`

```python
from modules.form_workflow.services.workflow_engine import WorkflowEngine

workflow_instance = WorkflowEngine.start_workflow(
    form_instance_secure_code=form_instance.secure_code,
    workflow_template_secure_code='流程模板SC',  # 可選，不給則從 form_template 關聯查
    is_test=False,
)
```

### WorkflowEngine.start_pure_workflow() -- 純流程、無表單模板

**位置**：`modules/form_workflow/services/workflow_engine.py:201`

引擎自動建立記錄用 FormInstance（`form_data={'_workflow_record': True}`），適用純通知/純審批。

```python
workflow_instance = WorkflowEngine.start_pure_workflow(
    workflow_template_secure_code='流程模板SC',
    org_secure_code='企業SC',
    applicant_secure_code='系統帳號SC',
    applicant_name='資安自動偵測',
)
```

### Flask App Context

```python
from backend.app import create_app

app = create_app()
with app.app_context():
    ...  # 在這裡呼叫引擎
```

---

## 流程模板設計要點（自動單共通）

- **條件節點**：依 `form_data` 中的風險欄位（如 `severity_id`、`risk_level`）分支
- **簽核人**：可用 DYNAMIC assignee，由 form_data 帶入
- **超時處理**：自動單建議設定 `timeout_action`，避免無人值守時卡關

---

*相關文件：`dev-notes/integrations/quick_form_submit_api.md`（HTTP 操作細節）、`dev-notes/integrations/open_defense_contract.md`（Webhook 對外契約）*
