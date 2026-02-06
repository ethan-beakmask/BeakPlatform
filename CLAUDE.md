# BeakPlatform - Claude Code 專案規範

## 專案定位

**BeakPlatform 是一個多租戶權限管理平台**

這是一個**純平台**，核心功能：
- 安全控制（認證、授權、攔截）
- 多租戶隔離（企業資料隔離、RLS）
- RBAC 權限系統
- 動態選單系統
- 組織架構管理（部門、群組、角色）
- 人資架構管理（職等、職系、職稱）

**業務功能透過「模組」掛載，不在平台內實作。**

---

## 📖 必讀文件

開始工作前，請先閱讀：
1. **本文件** — 專案規範
2. **`docs/PLATFORM_MODULARIZATION_PLAN.md`** — 完整開發計劃

---

## 📋 每次對話必做

### 0. 對話開始 (啟動檢查)
**每次對話開始時**，主動執行：

1. 讀取 `docs/PLATFORM_MODULARIZATION_PLAN.md` 了解當前進度
2. 查看 Forgejo Issues：
   ```bash
   curl -s http://192.168.0.16:3000/api/v1/repos/forgejoadmin/BeakPlatform/issues?state=open | jq '.[] | {number, title}'
   ```
3. 與用戶確認本次要處理的項目

### 1. Git Commit (對話結束)
**每次對話結束前**：

```bash
cd /opt/BeakPlatform
git add -A
git commit -m "類型: 簡短摘要

- 完成項目 1
- 完成項目 2

🤖 Generated with Claude Code"

git push origin main
```

### 2. 更新追蹤
- 完成 Forgejo Issue 時，用 API 關閉：`curl -X PATCH ... -d '{"state":"closed"}'`
- 如果涉及架構變更，更新 `docs/PLATFORM_MODULARIZATION_PLAN.md`

---

## 🎯 當前開發階段

Step 1~5 全部完成。目前處於**功能完善階段**。

待辦事項追蹤在 [Forgejo Issues](http://192.168.0.16:3000/forgejoadmin/BeakPlatform/issues)。
架構與模組化標準詳見 `docs/PLATFORM_MODULARIZATION_PLAN.md`。

---

## 🔒 安全標準 (必須遵守)

### AUTH-01: 全域認證攔截
- 所有請求經過 `before_request` 認證檢查
- 未登入訪問非白名單路由 → 401

### AUTH-02: 統一認證 Decorator
```python
@public_route          # 公開路由
@login_required        # 需要登入
@admin_required        # 需要企業管理員
@system_admin_required # 需要系統管理員
```

### TENANT-01: 強制企業隔離
- 所有查詢包含 `org_secure_code` 過濾
- PostgreSQL RLS 作為最後防線

### TENANT-02: ResourceGateway 要求
- API 層禁止直接使用 `Model.query`
- 必須透過 `ResourceGateway` 存取

### DATA-01: 帳號查詢必須過濾刪除與停用
- **所有查詢用戶/帳號的地方**，必須同時過濾 `is_deleted=False` 和 `is_active=True`
- 包含但不限於：用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析
- 關聯查詢（如透過角色/部門取用戶）需 JOIN User 表確認帳號狀態

---

## 📁 專案結構

```
/opt/BeakPlatform/
├── backend/
│   ├── app/
│   │   ├── security/       # 安全核心（勿隨意修改）
│   │   ├── api/            # API 路由
│   │   ├── web/            # Web 路由
│   │   ├── models/         # 資料模型
│   │   ├── services/       # 業務邏輯
│   │   └── templates/      # Jinja2 模板
│   └── tests/
├── modules/                # 模組目錄（Step 2 後建立）
├── docs/
│   ├── PLATFORM_MODULARIZATION_PLAN.md  # 開發計劃
│   └── knowledge/          # 知識庫
├── scripts/
│   └── migrations/         # 資料庫遷移
└── .semgrep/               # 安全規則
```

---

## 📦 模組靜態檔案規範

模組的 JS/CSS/圖片等靜態資源由 `module_loader.py` 自動註冊 serve。

**目錄結構：**
```
modules/<module_name>/static/modules/<module_name>/
  ├── js/           # JavaScript
  ├── css/          # 樣式表
  └── icons/        # 圖示
```

**存取 URL：** `/static/modules/<module_name>/js/xxx.js`

**禁止** 將模組靜態檔案複製到 `backend/app/static/`。
`backend/app/static/` 只放平台級資源（themes.css、vendor/、auth.js 等）。
模組資源一律放在 `modules/<name>/static/` 下，由 module_loader 自動 serve。

---

## 🚫 禁止事項

1. **禁止** 繞過認證攔截器
2. **禁止** API 直接查詢 Model
3. **禁止** 在 URL 使用自增 ID
4. **禁止** 硬編碼密鑰/密碼
5. **禁止** SQL 字串拼接
6. **禁止** 在平台內實作業務功能（應透過模組）
7. **禁止** 將模組靜態檔案複製到 `backend/app/static/`（會造成雙份不同步）

---

## 📊 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev（待建立）
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

---

## 📝 備忘

### Forgejo
- **URL**: http://192.168.0.16:3000/
- **Repo**: http://192.168.0.16:3000/forgejoadmin/BeakPlatform
- **API Token**: `be6f8e52f155aa026ac12c5bd470114aa7c54333`

### 相關專案
| 專案 | 路徑 | 說明 |
|------|------|------|
| BeakPlatform | `/opt/BeakPlatform` | 本專案（純平台）|
| A6 (FormFlow) | `/opt/FormFlow/a6` | 表單流程 MVP（待改造為模組）|
| BeakMask | `/opt/BeakMask` | 舊專案（參考用）|

### 服務啟動
```bash
cd /opt/BeakPlatform
source venv/bin/activate  # 如果有 venv
set -a && source .env && set +a
cd backend && flask run --host=0.0.0.0 --port=5009
```

### 檔案輸出
- **輸出目錄**: `/mnt/smb`（SMB 共享）
- Windows 路徑: `\\192.168.0.16\smb`

---

*最後更新: 2026-01-23*
