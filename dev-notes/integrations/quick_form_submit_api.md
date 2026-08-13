# 快速建立表單並進入流程 -- 程式化 API 指南

**適用版本**: 2026-07-07
**Base URL**: `http://192.168.0.16:7000/beakplatform`（`APP_PREFIX` 環境變數控制，預設 `/beakplatform`，由 `backend/app/__init__.py` 的 DispatcherMiddleware 掛載）

本文件說明兩條「不經過瀏覽器 UI、用程式/指令直接建立表單實例並啟動 workflow」的路徑：

| 路徑 | 對應頁面 | 認證方式 | 適用情境 |
|---|---|---|---|
| A. 表單中心 Submit API | `/beakplatform/forms/center` | 平台帳號 session cookie | 內部自動化、測試腳本、批次開單 |
| B. Open Defense Intake Webhook | `/beakplatform/open-defense/dashboard` | HMAC-SHA256 簽章（Intake Key） | 外部安全事件來源端（Suricata/Coraza/Falco 等） |

兩條路徑最終殊途同歸：建立 `FwFormInstance` + `FwWorkflowInstance`（status=RUNNING）+ Start 節點入 `FwNodeExecutionQueue`（status=PENDING），之後由 `workflow_executor` 背景執行緒（`modules/form_workflow/services/workflow_executor.py`，隨 Flask app 啟動，見 `modules/form_workflow/__init__.py:192`）輪詢消化佇列、推進流程。**送出成功後不需要任何額外動作，流程自動跑。**

---

## 路徑 A：表單中心 Submit API

### 程式碼位置

| 元件 | 檔案 |
|---|---|
| 送出端點 | `modules/form_workflow/api/fc_fill.py` -- `POST /api/form-center/submit`（`@csrf.exempt`，不需 CSRF token） |
| 可用表單列表 | `modules/form_workflow/api/fc_available.py` -- `GET /api/form-center/available-forms` |
| 取表單定義 | `modules/form_workflow/api/fc_fill.py` -- `GET /api/form-center/forms/<secure_code>` |
| 登入 | `backend/app/api/auth.py` -- `POST /auth/login`（支援 JSON，`@csrf.exempt`） |

### 步驟 1：登入取得 session cookie

JSON 登入不走三欄位防護機制，帳號格式為 `username@domain_name`：

```bash
BASE="http://192.168.0.16:7000/beakplatform"
JAR=/tmp/bp_cookies.txt

curl -s -c "$JAR" -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"account": "admin@acme.com.tw", "password": "..."}'
```

注意：登入有 rate limit（per 帳號），失敗會有 enforce_delay 延遲回應。

### 步驟 2：查可填寫的表單，取得 secure_code

```bash
curl -s -b "$JAR" "$BASE/api/form-center/available-forms"
```

回傳每筆含 `_status`（`published` / `test`）與 `secure_code`：
- `_status=published` → `secure_code` 是 **FwPublishedFormWorkflow**（已發行快照）的 SC，正式模式用
- `_status=test` → 對應設計稿，回傳含 `mapping_secure_code`，測試模式用

權限：一般用戶只看得到 `fw_mapping_permissions` 授權的已發行表單；SYSTEM_ADMIN / FLOW_DESIGNER / FORM_DESIGNER 角色全部可見；測試表單需管理員或 `form_workflow.design.tryout` 權限。

（選用）查表單 schema 以得知欄位 key：

```bash
curl -s -b "$JAR" "$BASE/api/form-center/forms/<published_sc>"          # 正式
curl -s -b "$JAR" "$BASE/api/form-center/forms/<template_sc>?source=mapping"  # 測試
```

### 步驟 3：送出表單（即建立實例 + 啟動流程）

```bash
curl -s -b "$JAR" -X POST "$BASE/api/form-center/submit" \
  -H "Content-Type: application/json" \
  -d '{
    "published_secure_code": "<published_sc>",
    "subject": "自動化開單測試",
    "form_data": {"field_a": "value", "field_b": 123}
  }'
```

**Request 欄位**：

| 欄位 | 必填 | 說明 |
|---|---|---|
| `published_secure_code` | 二選一 | 正式模式，用已發行快照。序號走萬用編號系統（NumberingService），流程編號 `PROC-YYYYMMDD-NNNN` |
| `mapping_secure_code` | 二選一 | 測試模式（`is_test=True`），需管理員或 `form_workflow.design.tryout` 權限。序號 `TEST-YYYYMMDD-NNNN` |
| `subject` | 是 | 表單主旨，空值回 400 |
| `form_data` | 否 | 表單欄位資料 dict，key 對應 form schema 的欄位 key |

**Response（201）**：

```json
{
  "success": true,
  "message": "表單已送出，流程已啟動",
  "data": {
    "form_instance_secure_code": "...",
    "serial_number": "FORM-20260707-00001",
    "workflow_instance_secure_code": "...",
    "execution_code": "PROC-20260707-0001",
    "is_test": false
  }
}
```

### Python 一鍵腳本範例

```python
import requests

BASE = 'http://192.168.0.16:7000/beakplatform'
s = requests.Session()

# 1. 登入
r = s.post(f'{BASE}/auth/login', json={
    'account': 'admin@acme.com.tw', 'password': '...',
})
r.raise_for_status()

# 2. 找目標表單（以名稱比對）
forms = s.get(f'{BASE}/api/form-center/available-forms').json()['data']
target = next(f for f in forms
              if f['_status'] == 'published' and '請假' in f['name'])

# 3. 送出 → 流程自動啟動
r = s.post(f'{BASE}/api/form-center/submit', json={
    'published_secure_code': target['secure_code'],
    'subject': '自動化請假單',
    'form_data': {'reason': 'API 測試', 'days': 1},
})
print(r.json())  # data.execution_code 即流程編號
```

送出後可在 `/beakplatform/forms/center` 的「我的表單」或 `/beakplatform/forms/instances` 查看進度。

---

## 路徑 B：Open Defense Intake Webhook

外部事件 → 自動開單啟動流程。完整對外契約見 `dev-notes/integrations/open_defense_contract.md`（v1.0），此處摘要操作面。

### 程式碼位置

| 元件 | 檔案 |
|---|---|
| Webhook 端點 | `modules/open_defense/api/intake.py` -- `POST /api/open_defense/intake` |
| 處理邏輯 | `modules/open_defense/services/intake_service.py`（冪等 → 白名單 → mapping → 建實例啟流程） |
| HMAC 驗證 | `modules/open_defense/services/hmac_verifier.py` + `@webhook_hmac_required` |

### 前置條件（一次性設定，UI 操作）

1. **建立 Intake Key**：`/beakplatform/open-defense/intake-keys` 建立，取得 `key_id`（如 `ik_a3f9c2e1`）與 `secret`（**僅顯示一次**），並設定 `allowed_source_systems` 白名單。
2. **設定 event_class → form_template 對應**：同頁設定 `OdFormTemplateMapping`。無 mapping 的 event_class 會被 422 `no_mapping` 拒收。
3. **表單必須已發行**：mapping 指向的 form_template 必須有 Published 版本（表單設計器發行），否則 422 `form_not_published`。Webhook 不支援測試模式。

### 呼叫方式（HMAC 簽章）

簽章規則：`HMAC-SHA256(secret, "{timestamp}\n{原始 body bytes}")`，timestamp 為 Unix 秒、5 分鐘內有效。**簽章後不得重新序列化 body。**

```bash
BASE="http://192.168.0.16:7000/beakplatform"
KEY_ID="ik_a3f9c2e1"
SECRET="<建立時取得的 32-byte secret>"

TIMESTAMP=$(date +%s)
BODY='{"correlation_id":"'$(uuidgen)'","source_system":"coraza","event_class":"web_activity","occurred_at":"2026-07-07T00:00:00Z","severity_id":4,"finding":{"title":"SQLi attempt on /login","rule_id":"942100","rule_set":"OWASP CRS 4.0"},"actor":{"ip":"203.0.113.42"},"target":{"host":"app.example.com","url":"/login"}}'
SIG=$(printf '%s\n%s' "$TIMESTAMP" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')

curl -s -X POST "$BASE/api/open_defense/intake" \
  -H "Content-Type: application/json" \
  -H "X-OD-Key-Id: $KEY_ID" \
  -H "X-OD-Timestamp: $TIMESTAMP" \
  -H "X-OD-Signature: sha256=$SIG" \
  -d "$BODY"
```

**必填欄位**：`correlation_id`（全域唯一冪等鍵，重送同 ID 回 `duplicate:true`）、`source_system`（須在 key 白名單）、`event_class`（`detection_finding` / `network_activity` / `web_activity` / `process_activity`）、`occurred_at`（ISO-8601 UTC）、`severity_id`（0-6）、`finding.title`；network/web 類另須 `actor.ip`。

**成功 Response（200）**：

```json
{"success": true, "duplicate": false, "case_secure_code": "<workflow_instance_sc>", "workflow_started": true}
```

`case_secure_code` 即 workflow_instance 的 secure_code，案件會出現在 `/beakplatform/open-defense/dashboard`。

**與路徑 A 的差異**：
- 申請人固定為 `OpenDefense Webhook`（`applicant_secure_code=None`），`source_type='WEBHOOK_OD'`
- 序號 `OD-YYYYMMDD-<8 hex>`、流程編號 `OD-YYYYMMDD-NNNN`（PostgreSQL advisory lock 序列化）
- `form_data` 由 `_build_form_data()` 從 OCSF 事件抽取固定關鍵欄位（不是自由傳入）
- Rate limit：per `key_id` 100/min、5000/hour

### 常見錯誤

| 狀態 | error code | 原因 |
|---|---|---|
| 401 | `auth_failed` | 簽章錯 / timestamp 超過 5 分鐘 / key_id 不存在（檢查主機時鐘 NTP） |
| 403 | `source_not_allowed` | `source_system` 不在該 key 的白名單 |
| 422 | `no_mapping` | 該 `event_class` 未設定 form_template mapping |
| 422 | `form_not_published` | mapping 指向的表單無 Published 版本 |
| 400 | `validation_error` | body 不符 OCSF schema，`details` 有逐欄說明 |

---

## 流程啟動後的機制（兩條路徑共通）

1. 送出當下：`FwFormInstance`（status=INITIAL）+ `FwWorkflowInstance`（status=RUNNING）+ Start 節點 queue item（status=PENDING）同交易寫入。
2. `workflow_executor` 背景執行緒撿起 PENDING 節點依 graph 推進；簽核節點會產生待辦，出現在 `/beakplatform/forms/pending`。
3. Open Defense 流程若含 `decision_writer` 節點，決策會寫入 `od_defense_decisions` 供執行端以 Service Account JWT 拉取（見契約 §5）。
