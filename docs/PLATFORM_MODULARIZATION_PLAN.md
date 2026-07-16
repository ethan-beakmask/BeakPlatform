# BeakPlatform 架構與模組化標準

> 本文件是專案的架構藍圖與模組化標準，供 Claude Code 和開發者參考。
> 待辦事項請查看 [Forgejo Issues](http://192.168.0.16:3000/forgejoadmin/BeakPlatform/issues)。
> 選單名稱與路徑對照請參考 `docs/GLOSSARY.md`。

---

## 模組化標準

### 模組目錄結構
```
modules/<module_name>/
├── __init__.py             # MODULE_INFO（名稱、版本、權限、選單）
├── requirements.txt
├── models/
├── api/                    # API Blueprint
├── web/                    # Web Blueprint
├── services/
├── templates/modules/<module_name>/
├── static/modules/<module_name>/
└── migrations/*.sql
```

### 模組元資料
```python
MODULE_INFO = {
    'name': 'form_workflow',
    'display_name': '表單流程系統',
    'version': '1.0.0',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'menu_items': [...],
    'permissions': [...],
    # 模組預設角色（選填）：採購本模組的企業自動獲得，見 docs/PERMISSION_MODEL.md 3.1
    'default_roles': [{'code': 'SECURITY_STAFF', 'name': '資安人員', 'description': '...'}],
    'default_menu_role_requirements': {'open_defense.security_cases': ['SECURITY_STAFF']},
}
```

### 平台接口

**認證** (`app/platform/auth.py`):
```python
current_user, require_login, require_permission, has_permission
```

**資料** (`app/platform/data.py`):
```python
get_current_org, get_users, get_departments, get_roles, get_user_by_code
```

### 路由掛載
模組提供 Blueprint，平台 ModuleLoader 自動註冊。

### 資料庫
使用表名前綴（如 `fw_` = form_workflow），不使用獨立 schema。

### 安裝流程
```bash
flask module list       # 列出模組
flask module sync       # 同步權限和選單
flask module register   # 掃描並註冊
flask module enable/disable <name>
```

---

## 決策記錄

| 日期 | 決策 | 原因 |
|------|------|------|
| 2026-01-23 | 平台+模組架構（取代融入式移轉） | 舊 BeakMask 定位是平台而非產品 |
| 2026-01-23 | 資料庫表名前綴（非獨立 schema） | 相容性較好，無 cross-schema join 問題 |
| 2026-02-08 | Node Type 定義改為 DB 驅動 (Issue #10) | 消除 API 287 行硬編碼，DB 為 single source of truth |
| 2026-02-08 | 前端 JS/CSS 分離規範 (Issue #7) | HTML 模板瘦身，單檔不超過 500 行 |

---

## 前端技術棧

| 類別 | 技術 | 版本 | 用途 | 備註 |
|------|------|------|------|------|
| 模板引擎 | Jinja2 | Flask 內建 | 伺服器端 HTML 渲染 | |
| 響應式框架 | Alpine.js | 3.x | 頁面互動、元件狀態管理 | 主力框架，所有頁面使用 |
| 表單渲染 | form.io | 4.x | 動態表單 schema 渲染與驗證 | form_workflow / nocode_builder 模組 |
| 佈局拖拉 | GridStack.js | 10.x | Web Builder 頁面佈局設計器 | `vendor/gridstack/` |
| 樹/Treegrid | Wunderbaum | 0.13.0 | 樹狀結構、多欄 treegrid、拖拉排序 | `vendor/wunderbaum/`，Fancytree 繼任者，零依賴 |
| CSS | 自建 + Bootstrap (部分) | -- | 導覽列自建 `bk-*`，內容區可用 Bootstrap | 見 CLAUDE.md CSS 規範 |
| 圖示 | Bootstrap Icons | 1.11.3 | Wunderbaum 預設圖示、通用 icon | `vendor/fonts/` + `vendor/wunderbaum/bootstrap-icons.css` |

### 技術選型原則

- **禁用 CDN**：所有套件 vendor 化到 `backend/app/static/vendor/`，確保封閉網路可用
- **零/少依賴優先**：Alpine.js (零依賴)、Wunderbaum (零依賴)、GridStack (零依賴)
- **評估時機**：當需求涉及 tree / treegrid / 階層拖拉時，Wunderbaum 應與其他 JS 方案一起評估

---

## 服務配置

| 項目 | 值 |
|------|-----|
| 主服務 | http://192.168.0.16:7000 (Nginx port 80) |
| DevTools | http://192.168.0.16:7001 |
| 資料庫 | beakplatform_dev |
| Forgejo | http://192.168.0.16:3000/forgejoadmin/BeakPlatform |

---

*最後更新: 2026-03-14*
