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

### Step 4: 模擬用戶環境驗證
**目標**: 在乾淨環境驗證平台+模組的安裝流程

**步驟**:
1. 準備新的 Ubuntu VM
2. 安裝 BeakPlatform（文件化安裝步驟）
3. 安裝 form_workflow 模組
4. 驗證所有功能正常
5. 記錄問題並修正

**產出**:
- 平台安裝文件
- 模組安裝文件
- 常見問題排除指南

---

### Step 5: 開發全新模組
**目標**: 開發第二個模組，驗證模組標準的通用性

**候選模組**:
- 公告系統模組
- 差勤系統模組
- 請假系統模組

**驗收標準**:
1. 新模組可以無痛安裝
2. 不需要修改平台程式碼
3. 模組標準足夠通用

---

## 當前狀態

**目前階段**: Step 1 完成，準備進入 Step 2

**Step 1 完成項目** (2026-01-23):
- 專案初始化與 Git/Forgejo 設定
- 移除表單流程程式碼（Models, API, Web routes）
- 清理殘留引用（TimeoutTracker, hostconfig, admin/settings）
- 清理資料庫選單項目
- 建立資料庫初始化腳本
- 驗證平台可獨立運行

**服務配置**:
- 主服務: http://192.168.0.16:7000 (Nginx port 80)
- DevTools: http://192.168.0.16:7001
- 資料庫: beakplatform_dev

**下一步**: Step 2 - 建立模組化標準

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

*最後更新: 2026-01-23*
