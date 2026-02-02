# BeakPlatform 平台化與模組化計劃

> 本文件是整個專案的開發藍圖，供 Claude Code 和開發者參考

---

## 專案背景

### 問題
原本從 A6 (FormFlow) 移轉表單流程系統到 BeakMask 的方式錯誤：
- 把 A6 程式碼「融入」BeakMask，導致大量重寫
- BeakMask 從「平台」變成「產品」
- 移轉不完整，95% 功能需要重新開發

### 解決方案
改變架構思維：
1. **BeakPlatform** — 純平台，只負責安全、權限、多租戶
2. **模組** — 業務功能（如表單流程）以模組形式掛載
3. **A6 改造** — 不是移轉，而是改造成符合模組標準

### 專案關係
```
/opt/BeakPlatform     ← 純平台（本專案）
/opt/FormFlow/a6      ← 表單流程 MVP（將改造為模組）
/opt/BeakMask         ← 完整系統（參考用，最終將廢棄）
```

---

## 開發步驟

### Step 1: 單純平台化 BeakPlatform
**目標**: 確保 BeakPlatform 可以獨立運行，不含任何業務功能

**已完成**:
- [x] 從 BeakMask 複製核心平台功能
- [x] 移除表單流程 Models
- [x] 移除表單流程 API
- [x] 移除表單流程 Web routes
- [x] 清理 __init__.py 引用
- [x] 建立 Git repo 並推送到 Forgejo
- [x] 檢查所有檔案是否還有表單流程引用
- [x] 清理前端模板中的表單流程相關連結（admin/settings.html）
- [x] 清理選單資料中的表單流程項目（資料庫）
- [x] 建立獨立資料庫 `beakplatform_dev`
- [x] 建立資料庫初始化腳本（scripts/init_database.sh）
- [x] 驗證 Flask 可啟動
- [x] 驗證登入/登出正常（快速登入 API）
- [x] 驗證認證攔截器正常（401/200）

**驗收標準**:
1. `flask run` 可以啟動，沒有 import 錯誤
2. 可以登入系統
3. 所有平台功能正常運作
4. 沒有任何表單流程相關的 UI 或 API

---

### Step 2: 建立模組化標準
**目標**: 制定模組開發和掛載的標準規範

**標準項目**:

#### 2.1 模組目錄結構標準
```
modules/
└── form_workflow/              # 模組名稱（snake_case）
    ├── __init__.py             # 模組元資料（名稱、版本、依賴）
    ├── requirements.txt        # 模組專用依賴
    ├── models/                 # 資料模型
    │   ├── __init__.py
    │   └── *.py
    ├── api/                    # API 路由
    │   ├── __init__.py
    │   └── *.py
    ├── web/                    # Web 路由
    │   ├── __init__.py
    │   └── *.py
    ├── services/               # 業務邏輯
    │   ├── __init__.py
    │   └── *.py
    ├── templates/              # Jinja2 模板
    │   └── modules/form_workflow/
    ├── static/                 # 靜態資源
    │   └── modules/form_workflow/
    └── migrations/             # 資料庫遷移
        └── *.sql
```

#### 2.2 模組元資料標準
```python
# modules/form_workflow/__init__.py
MODULE_INFO = {
    'name': 'form_workflow',
    'display_name': '表單流程系統',
    'version': '1.0.0',
    'description': '表單設計、流程設計、簽核功能',
    'author': 'BeakPlatform Team',
    'dependencies': [],  # 依賴的其他模組
    'platform_version': '>=1.0.0',  # 平台最低版本
    'menu_items': [...],  # 模組選單項目
    'permissions': [...],  # 模組權限定義
}
```

#### 2.3 認證接口標準
模組不實作認證，透過平台提供的接口取得用戶資訊：
```python
from beakplatform.auth import (
    current_user,           # 當前登入用戶
    get_user_permissions,   # 取得用戶權限
    require_login,          # 裝飾器：需要登入
    require_permission,     # 裝飾器：需要特定權限
)
```

#### 2.4 資料接口標準
模組透過平台接口查詢用戶、部門、角色等：
```python
from beakplatform.data import (
    get_current_org,        # 當前企業
    get_users,              # 查詢用戶
    get_departments,        # 查詢部門
    get_roles,              # 查詢角色
    get_user_by_code,       # 依 secure_code 取得用戶
)
```

#### 2.5 權限接口標準
模組在 MODULE_INFO 中定義權限，平台負責檢查：
```python
MODULE_INFO = {
    'permissions': [
        {'code': 'form_workflow.form.create', 'name': '建立表單'},
        {'code': 'form_workflow.form.approve', 'name': '簽核表單'},
    ]
}

# 使用
@require_permission('form_workflow.form.create')
def create_form():
    pass
```

#### 2.6 選單整合標準
模組在 MODULE_INFO 中定義選單，平台負責渲染：
```python
MODULE_INFO = {
    'menu_items': [
        {
            'code': 'form_workflow',
            'name': '表單流程',
            'icon': 'file-text',
            'parent': None,
            'sort_order': 100,
            'children': [
                {'code': 'form_workflow.forms', 'name': '表單管理', 'url': '/forms/'},
                {'code': 'form_workflow.workflows', 'name': '流程管理', 'url': '/workflows/'},
            ]
        }
    ]
}
```

#### 2.7 路由掛載標準
模組提供 Blueprint，平台負責註冊：
```python
# modules/form_workflow/api/__init__.py
from flask import Blueprint
api_bp = Blueprint('form_workflow_api', __name__, url_prefix='/api/form-workflow')

# modules/form_workflow/web/__init__.py
from flask import Blueprint
web_bp = Blueprint('form_workflow_web', __name__, url_prefix='/forms')
```

#### 2.8 資料庫標準
模組使用獨立 schema 或表名前綴：
```python
# 選項 A: 獨立 schema
class FormTemplate(db.Model):
    __tablename__ = 'form_templates'
    __table_args__ = {'schema': 'form_workflow'}

# 選項 B: 表名前綴（推薦）
class FormTemplate(db.Model):
    __tablename__ = 'fw_form_templates'  # fw_ = form_workflow
```

#### 2.9 模組安裝流程
```bash
# 1. 複製模組到 modules 目錄
cp -r /path/to/form_workflow /opt/BeakPlatform/modules/

# 2. 安裝模組依賴
pip install -r modules/form_workflow/requirements.txt

# 3. 執行資料庫遷移
python manage.py module migrate form_workflow

# 4. 註冊模組（自動掃描 modules/ 目錄）
python manage.py module register

# 5. 重啟服務
systemctl restart beakplatform
```

---

### Step 3: 依模組化標準移轉表單流程系統
**目標**: 將 A6 改造為符合模組標準的 `form_workflow` 模組

**步驟**:
1. 在 A6 目錄建立模組結構
2. 實作認證接口對接
3. 實作資料接口對接
4. 修改路由使用 Blueprint
5. 修改資料庫表名（加前綴）
6. 測試模組安裝流程
7. 根據問題調整模組標準

**預期調整**:
- 標準可能需要多次修正
- 平台可能需要新增接口
- 安裝流程可能需要優化

---

### Step 4: 模擬用戶環境驗證 ✅
**目標**: 在乾淨環境驗證平台+模組的安裝流程

**已完成**:
- [x] 建立安裝文件 (`docs/INSTALL.md`)
- [x] 建立自動化安裝腳本 (`scripts/install.sh`)
- [x] 建立驗證腳本 (`scripts/verify_install.sh`)
- [x] 建立環境變數範例 (`.env.example`)
- [x] 建立選單初始化腳本 (`scripts/init_menus.py`)
- [x] 在新 Ubuntu VM 執行安裝測試 (192.168.0.13)

**產出**:
- `docs/INSTALL.md` - 完整安裝指南
- `scripts/install.sh` - 自動化安裝腳本
- `scripts/init_database.sh` - 資料庫初始化腳本
- `scripts/init_menus.py` - 選單初始化腳本
- `scripts/verify_install.sh` - 安裝驗證腳本
- `.env.example` - 環境變數範例

**修正的問題**:
- 模組同步順序問題（新增 `SKIP_MODULE_SYNC` 環境變數）
- Session 目錄權限問題（安裝時自動清除）
- 表單流程路由修正（`/forms/my/` → `/forms/instances`）
- 密碼雜湊格式（使用 bcrypt 而非 werkzeug）

---

### Step 5: 驗證模組標準通用性 ✅
**目標**: 驗證模組標準的通用性

**已完成**:
- [x] sample_module 範例模組測試通過
- [x] form_workflow 表單流程模組測試通過
- [x] 模組 API 端點正常運作
- [x] 模組權限正確註冊

**驗收標準**:
1. ✅ 新模組可以無痛安裝（安裝腳本自動處理）
2. ✅ 不需要修改平台程式碼（模組放入 modules/ 即可）
3. ✅ 模組標準足夠通用（兩個模組都正常運作）

---

## 當前狀態

**目前階段**: Step 5 完成 ✅ - 模組標準驗證通過

**待辦**:

### ⚠️ 下次對話優先處理（2026-02-03 標記）
1. **ACE 錯誤調查** — 表單設計器拖入元件開啟編輯時出現 ACE/CDN 載入錯誤。建立 form.io 官方 demo 頁面，直接比對問題來源（是 form.io 本身行為 or 我們的環境造成）
2. **新建時產生空白檔案** — 表單與流程進入編輯頁面後，即使按「放棄」仍會產生空白設計檔。改為第一次儲存時才建立記錄
3. **流程自動建立對應表單** — 評估流程儲存時同時建立並配對表單的做法是否繼續保留
4. **CI/CD 安全檢查移轉** — BeakMask 有 semgrep 程式碼安全檢查 CI/CD，需移轉到本專案

---

- 完善表單流程模組功能
- [x] 驗證 WorkflowExecutor 背景服務正常運作（送出表單後流程自動推進）
  - 2026-01-30 端對端測試通過
  - 流程: Start → OpFieldRead → OpFieldWrite → FormAdapter(簽核) → Delay(20s) → End
  - Executor 輪詢(5s)正常、subprocess 啟動正常、Delay 到期恢復正常
  - Workflow COMPLETED、Form APPROVED
- [x] JSONB Primary + SQL Sync 功能實作（2026-02-02）
  - 獨立 DB (beakform_data) + 專用帳號 (beakform)
  - 連線池 + converter + table_manager + sync_service
  - 自動化測試通過（建表/UPSERT/更新/安全模式）
- [x] SQL Sync 實機測試（2026-02-02）
  - 配對頁面 SQL 開關：Toggle ON/OFF/Status API 正常
  - 發行 → 自動建表：fw_data_vdz6ynxc_v2 自動建立，含動態欄位
  - 提交表單 → SQL 同步：UPSERT 正確，所有欄位值吻合
  - 簽核修改 → SQL 更新：approver 修改 textArea 後 SQL 表同步更新
  - 容錯驗證：DB 故障不影響主流程 (HTTP 201)，恢復後自動復原
- [x] 表單設計器 CJK 中文標籤支援（2026-02-03）
  - 根因：form.io 的 lodash camelCase 無法處理 CJK，產生空 key 觸發驗證錯誤
  - 解法：placeholder 輸入中文 → saveComponent 事件即時交換到 label + 後端 API 雙重處理
  - alertMessage 翻譯補齊（formio-i18n-zh-TW.json）
  - form.io 5.2.6 升級測試後退回 5.2.3（5.2.6 未修 CJK 且引入 ACE CDN 問題）
- [x] 新建表單預設「表單主旨」欄位（2026-02-03）
  - _get_default_schema() + workflows.py 自動建立 + 前端新增模式統一預設 formSubject 欄位

---

**Step 1 完成項目** (2026-01-23):
- 專案初始化與 Git/Forgejo 設定
- 移除表單流程程式碼（Models, API, Web routes）
- 清理殘留引用（TimeoutTracker, hostconfig, admin/settings）
- 清理資料庫選單項目
- 建立資料庫初始化腳本
- 驗證平台可獨立運行
- Git tag: v0.1.0

**Step 2 已完成** (2026-01-24):
- [x] 2.1 模組目錄結構 - 建立 `modules/` 目錄
- [x] 2.2 模組元資料 - MODULE_INFO 規範和讀取機制
- [x] 2.3 認證接口 - `app/platform/auth.py`
- [x] 2.4 資料接口 - `app/platform/data.py`
- [x] 2.7 路由掛載 - 自動註冊 Blueprint (ModuleLoader)
- [x] 範例模組 - `modules/sample_module/` 驗證機制
- [x] 2.5 權限接口 - `ModulePermissionService` 權限註冊機制
- [x] 2.6 選單整合 - `ModuleMenuService` 選單註冊機制
- [x] 2.9 安裝流程 - Flask CLI `flask module` 命令

**服務配置**:
- 主服務: http://192.168.0.16:7000 (Nginx port 80)
- DevTools: http://192.168.0.16:7001
- 資料庫: beakplatform_dev

**Step 3 進行中** (2026-01-24):
- [x] 建立 form_workflow 模組目錄結構
- [x] 定義 MODULE_INFO（權限、選單）
- [x] 建立核心 Models（使用 fw_ 前綴）
  - FwFormTemplate - 表單模板
  - FwWorkflowTemplate - 工作流模板
  - FwFormInstance - 表單實例
  - FwWorkflowInstance - 工作流實例
  - FwApprovalRecord - 簽核記錄
  - FwNodeExecutionQueue - 節點執行隊列
- [x] 建立基礎 API Blueprint
- [x] 移轉工作流引擎 (WorkflowEngine)
  - `services/workflow_engine.py` - 核心引擎（start_workflow, advance_workflow, complete_workflow）
  - `services/workflow_executor.py` - 背景執行器（輪詢和 subprocess 啟動）
  - `services/node_runner.py` - CLI 入口點
- [x] 移轉節點處理器 (NodeHandlers) - 14 種類型
  - 流程控制: StartHandler, EndHandler
  - 時間控制: DelayHandler
  - 簽核: ApproveHandler (含 FormAdapter 別名)
  - 分支匯合: BranchHandler, SwitchHandler, ConvergeHandler
  - 變數操作: OpSetHandler
  - 通知: NotifyHandler (含 Telegram, Email 別名)
  - 子流程: SubFlowHandler (含 Subprocess 別名)
- [x] 建立資料庫遷移腳本
  - `migrations/001_create_tables.sql` - 建立 7 個資料表
  - `migrations/001_drop_tables.sql` - 回滾腳本
  - `migrations/002_add_subflow_columns.sql` - 子流程欄位
- [x] 建立節點處理器測試
  - `tests/test_workflow_engine.py` - 10 個測試案例
- [x] 建立前端模板 (5 個頁面)
  - `templates/modules/form_workflow/dashboard.html` - 模組儀表板
  - `templates/modules/form_workflow/template_list.html` - 表單模板管理
  - `templates/modules/form_workflow/workflow_list.html` - 流程模板管理
  - `templates/modules/form_workflow/instance_list.html` - 表單實例列表
  - `templates/modules/form_workflow/pending_list.html` - 待簽核任務
- [x] 建立完整 API 端點 (19 個)
  - CRUD: templates, workflows
  - 查詢: instances, pending-tasks
  - 操作: approve
  - 統計: stats
- [x] 建立 Web 路由 (11 個)
  - /forms/, /forms/dashboard
  - /forms/templates, /forms/workflows
  - /forms/instances, /forms/pending
- [ ] 完整整合測試

**Step 3 完成** (2026-01-24)

**2.5 權限接口實作細節**:
- `ModulePermissionService` (`app/services/module_permission_service.py`)
  - 將模組 `MODULE_INFO['permissions']` 同步到 Permission 資料表
  - 支援新增、更新、停用模組權限
  - 在模組載入時自動執行
- 模組可用的權限接口 (`app/platform/auth.py`):
  - `get_module_permissions(module_name)` - 取得模組權限列表
  - `get_user_roles(user)` - 取得用戶角色
  - `require_permission(code)` - 權限裝飾器
  - `has_permission(code)` - 權限檢查函數

**2.6 選單整合實作細節**:
- `ModuleMenuService` (`app/services/module_menu_service.py`)
  - 將模組 `MODULE_INFO['menu_items']` 同步到 MenuItem 資料表
  - 支援巢狀選單結構（遞迴處理 children）
  - 自動設定 MenuPermission（預設所有用戶類型可見）
  - 模組選單歸屬於 `system.local` 組織
  - 在模組載入時自動執行
- 選單定義格式:
  ```python
  'menu_items': [{
      'code': 'module_name',
      'name': '模組名稱',
      'icon': 'box',
      'sort_order': 900,
      'children': [
          {'code': 'module_name.feature', 'name': '功能', 'url': '/path/'}
      ]
  }]
  ```

**2.9 安裝流程實作細節**:
- Flask CLI 命令 (`app/cli.py`):
  ```bash
  flask module list           # 列出所有模組
  flask module info <name>    # 顯示模組詳細資訊
  flask module sync           # 同步權限和選單到資料庫
  flask module status         # 顯示模組系統狀態
  flask module register       # 掃描並註冊新模組
  flask module enable <name>  # 啟用模組
  flask module disable <name> # 停用模組
  ```

---

## 檔案參考

| 檔案 | 說明 |
|------|------|
| `/opt/BeakPlatform/CLAUDE.md` | 專案規範（Claude Code 必讀）|
| `/opt/BeakPlatform/docs/PLATFORM_MODULARIZATION_PLAN.md` | 本文件 |
| `/opt/FormFlow/a6/` | 表單流程 MVP（待改造為模組）|

---

## 決策記錄

### 2026-01-23: 架構重構決策
- **問題**: 從 A6 移轉表單流程到 BeakMask 的方式錯誤
- **決策**: 改為平台+模組架構
- **原因**: BeakMask 定位是「整合平台」而非「產品」

### 2026-01-23: 資料庫隔離方式
- **選項 A**: 獨立 schema
- **選項 B**: 表名前綴
- **決策**: 表名前綴（推薦）
- **原因**: 相容性較好，不需要處理 cross-schema join

---

**Step 4 完成** (2026-01-25):
- 安裝腳本已在新 Ubuntu VM 測試通過
- 平台核心功能正常運作
- 表單流程模組已整合

**Step 5 完成** (2026-01-25):
- sample_module 和 form_workflow 模組測試通過
- 模組標準驗證完成，無需修改平台程式碼

---

*最後更新: 2026-02-03 (CJK 中文標籤支援 + 預設表單主旨欄位)*
