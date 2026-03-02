# BeakPlatform 平台化與模組化計劃

> 本文件是專案的架構藍圖與模組化標準，供 Claude Code 和開發者參考。
> 待辦事項請查看 [Forgejo Issues](http://192.168.0.16:3000/forgejoadmin/BeakPlatform/issues)。

---

## 專案背景

**問題**: 從 A6 移轉表單流程到舊專案 BeakMask 的方式錯誤（融入式移轉導致大量重寫）。

**解決方案**: 平台 + 模組架構
- **BeakPlatform** — 純平台（安全、權限、多租戶）
- **模組** — 業務功能以模組形式掛載
- **A6 改造** — 改造成符合模組標準，非移轉

```
/opt/BeakPlatform     ← 純平台（本專案）
/opt/FormFlow/a6      ← 表單流程 MVP（將改造為模組）
/opt/BeakMask         ← 舊專案（參考用）
```

---

## 開發步驟總覽

| Step | 說明 | 狀態 | 完成日期 |
|------|------|------|----------|
| 1 | 單純平台化 BeakPlatform | ✅ 完成 | 2026-01-23 |
| 2 | 建立模組化標準 | ✅ 完成 | 2026-01-24 |
| 3 | 依標準移轉表單流程系統 | ✅ 完成（整合測試待補，見 Issue #2） | 2026-01-24 |
| 4 | 模擬用戶環境驗證 | ✅ 完成 | 2026-01-25 |
| 5 | 驗證模組標準通用性 | ✅ 完成 | 2026-01-25 |

---

## 模組化標準（Step 2）

### 2.1 模組目錄結構
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

### 2.2 模組元資料
```python
MODULE_INFO = {
    'name': 'form_workflow',
    'display_name': '表單流程系統',
    'version': '1.0.0',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'menu_items': [...],
    'permissions': [...],
}
```

### 2.3 平台接口

**認證** (`app/platform/auth.py`):
```python
current_user, require_login, require_permission, has_permission
```

**資料** (`app/platform/data.py`):
```python
get_current_org, get_users, get_departments, get_roles, get_user_by_code
```

### 2.4 路由掛載
模組提供 Blueprint，平台 ModuleLoader 自動註冊。

### 2.5 資料庫
使用表名前綴（如 `fw_` = form_workflow），不使用獨立 schema。

### 2.6 安裝流程
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
| 表單渲染 | form.io | 4.x | 動態表單 schema 渲染與驗證 | form_workflow / data_crud 模組 |
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

*最後更新: 2026-03-03*
