# BeakPlatform 溝通對照表

> 用戶提到功能名稱時，Claude 依此表快速定位對應的選單、路徑與程式位置。
> 名稱來源：資料庫 menu_items 表的 title 欄位。

---

## 用戶溝通慣例

| 符號 | 意義 | 範例 |
|------|------|------|
| `/path/` | URL 路徑（基底 `http://192.168.0.16:7000`） | `/menu/` = 權限管理 > 選單管理 |
| `'名詞'` | 功能名稱或字串，多名詞時混用 `""` 區別 | '表單中心'、'流程設計' |
| `[文字]` | UI 按鈕或超連結元素 | [啟動]、[儲存] |
| `(URL)` | 瀏覽器複製的完整 URL | (http://192.168.0.16:7000/forms/center) |

**注意：** `[按鈕]` 和 `(URL)` 不要直接相鄰，避免被 Markdown 解讀為連結語法。

---

## 選單結構對照

### 頂層獨立項目

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 儀表板 | `/dashboard` | 首頁儀表板 |
| 表單中心 | `/forms/center` | 使用者填寫表單的入口 |
| 個人設定 | `/personal-settings` | 個人資料與密碼 |
| 主機設定 | `/hostconfig/` | 主機環境設定 |

### 人機互動流程模組（模組：form_workflow）

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 表單儀表板 | `/forms/` | 表單流程模組首頁 |
| 表單範本 | `/forms/templates/` | 表單範本 CRUD |
| 流程設計 | `/forms/workflows/` | 工作流範本 CRUD |
| 配對管理 | `/forms/mappings` | 表單-流程配對 |
| 分類管理 | `/forms/categories` | 表單分類 |
| 表單風格管理 | `/forms/form-themes` | Form.io 主題管理 |

### 規格制定模組（模組：spec_formulate）

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 資料表規格 | `/spec-formulate/` | 資料表欄位規格定義（SQL/JSON/規格三相工具） |

### 子系統開發模組（模組：nocode_builder）

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 子系統開發 | `/nocode-builder/sub-systems` | 子系統列表與開發入口 |
| 視圖管理 | `/nocode-builder/` | CRUD 視圖管理 |
| 頁面管理 | `/nocode-builder/lab` | 自由介面頁面設計器 |
| 選項清單 | `/nocode-builder/lookup` | 子系統選單開發測試 |

### 企業管理

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 企業與合約管理 | `/organizations/` | 企業 CRUD + 合約管理 |
| 企業獨立資料庫管理 | `/org-databases/system` | 系統管理員視角的企業 DB |

### 權限管理

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 選單管理 | `/menu/` | 動態選單 CRUD |
| 模組管理 | `/modules/` | 模組啟停管理 |

### 模組區

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 模組權限管理 | `/admin/module-permissions` | 企業管理員控制模組使用權 |

### 系統管理

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 系統設定 | `/admin/settings` | Logo、密碼政策等 |
| 企業管理員 | `/org-admins/` | 各企業管理員帳號 |
| 獨立資料庫 | `/org-databases/` | 企業管理員視角的 DB |

### 帳號管理

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 員工帳號 | `/users/` | 使用者 CRUD |
| 角色管理 | `/roles/` | 角色 CRUD |
| 外部廠商 | `/external-users/` | 外部廠商管理 |
| 編號設定 | `/admin/numbering` | 自動編號規則 |
| 基本班表 | `/admin/settings/work-schedules` | 班表與假日設定 |

### 職級職稱

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 職級職稱矩陣 | `/job-levels/matrix` | 職等 x 職系矩陣 |
| 職等設定 | `/job-levels/` | 職等 CRUD |
| 職系設定 | `/job-families/` | 職系 CRUD |
| 職稱設定 | `/job-titles/` | 職稱 CRUD |
| 核決權限 | `/job-approval-categories/` | 核決類別管理 |

### 其他

| 選單名稱 | URL 路徑 | 說明 |
|----------|----------|------|
| 部門設定 | `/departments/` | 部門樹管理 |
| 社群設定 | `/groups/` | 社群管理 |
| 模組用戶設定 | `/admin/module-users` | 模組用戶管理 |
| 系統級帳號管理 | `/sys-accounts/` | 系統管理員帳號 |

---

## 常用術語

| 術語 | 指的是 |
|------|--------|
| 平台 | BeakPlatform 本體（安全、權限、多租戶） |
| 模組 | 掛載在平台上的業務功能（form_workflow、nocode_builder、spec_formulate） |
| 企業 / 租戶 | 多租戶架構中的一個組織單位 |
| secure_code | 32 字元唯一識別碼，取代自增 ID 用於 URL |
| RLS | PostgreSQL Row Level Security，租戶隔離最後防線 |
| ResourceGateway | API 層強制租戶隔離的資料存取層 |
| 配對 | 表單範本與工作流範本的綁定關係 |
| 子系統 | NoCode Builder 中開發的獨立應用 |
| provision | 子系統申請通過後的自動配置流程 |

---

*最後更新: 2026-03-13*
