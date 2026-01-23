# BeakPlatform - Claude Code 專案規範

## 專案定位

**BeakPlatform 是一個多租戶權限管理平台**

核心功能：
- 安全控制（認證、授權、攔截）
- 多租戶隔離（企業資料隔離、RLS）
- RBAC 權限系統
- 動態選單系統
- 組織架構管理（部門、群組、角色）
- 人資架構管理（職等、職系、職稱）

**不包含業務功能** — 業務功能應透過「模組」掛載。

---

## 📋 每次對話必做

### 0. 對話開始 (啟動檢查)
**每次對話開始時**，主動執行以下步驟：

1. **閱讀本文件的「下次作業項目」區塊**
2. **查看 Forgejo Issues**: `curl -s http://192.168.0.16:3000/api/v1/repos/forgejoadmin/BeakPlatform/issues?state=open | jq '.[] | {number, title}'`
3. **比較兩邊**：列出待辦事項，與用戶討論

### 1. Git Commit (對話結束)
**每次對話結束前**，提交變更到 Git：

```bash
cd /opt/BeakPlatform
git add -A
git commit -m "類型: 簡短摘要

- 完成項目 1
- 完成項目 2

🤖 Generated with Claude Code"

git push origin main
```

**Commit 類型**：
- `feat:` 新功能
- `fix:` 修復 bug
- `refactor:` 重構
- `docs:` 文件更新
- `security:` 安全相關

---

## 🔒 安全標準 (必須遵守)

### AUTH-01: 全域認證攔截
- 所有請求經過 `before_request` 認證檢查
- 未登入訪問非白名單路由 → 401

### AUTH-02: 統一認證 Decorator
所有路由**必須**使用以下裝飾器之一：
```python
@public_route          # 公開路由
@login_required        # 需要登入
@admin_required        # 需要企業管理員
@system_admin_required # 需要系統管理員
```

### TENANT-01: 強制企業隔離
- 所有查詢自動包含 `org_secure_code` 過濾
- PostgreSQL RLS 作為最後防線

### TENANT-02: ResourceGateway 要求
- API 層**禁止**直接使用 `Model.query`
- 必須透過 `ResourceGateway` 存取資源

---

## 📁 專案結構

```
/opt/BeakPlatform/
├── backend/                # 主應用
│   ├── app/
│   │   ├── security/       # 安全核心 (勿隨意修改)
│   │   ├── api/            # API 路由
│   │   ├── web/            # Web 路由 (HTML 頁面)
│   │   ├── models/         # 資料模型
│   │   ├── services/       # 業務邏輯
│   │   └── templates/      # Jinja2 模板
│   └── tests/
├── docs/
│   └── knowledge/          # 知識庫
├── scripts/
│   └── migrations/         # 資料庫遷移
└── .semgrep/               # 安全規則
```

---

## 🛠️ 開發流程

### 新增 API 路由
1. 在 `backend/app/api/` 建立檔案
2. 使用統一認證 decorator
3. 透過 ResourceGateway 存取資源

### 新增 Model
1. 繼承 `TenantBaseModel` (多租戶) 或 `BaseModel`
2. 使用 `secure_code` 作為外部識別碼
3. 不要暴露自增 `id`

---

## 🚫 禁止事項

1. **禁止** 繞過認證攔截器
2. **禁止** API 直接查詢 Model
3. **禁止** 在 URL 使用自增 ID
4. **禁止** 硬編碼密鑰/密碼
5. **禁止** SQL 字串拼接
6. **禁止** 加入業務功能（應透過模組）

---

## 📊 資料庫資訊

- **Host**: localhost
- **Database**: beakplatform_dev (待建立)
- **User**: beakplatform
- **Password**: postgres123 (開發環境)

---

## 🎯 當前開發階段

**Phase 1: 平台基礎** ← 目前
- [x] 從 BeakMask 提取核心平台功能
- [ ] 清理表單流程相關引用
- [ ] 建立獨立資料庫
- [ ] 驗證平台可獨立運行

**Phase 2: 模組標準制定**
- [ ] 認證接口標準
- [ ] 資料接口標準
- [ ] 權限接口標準
- [ ] 選單整合標準
- [ ] 路由掛載標準
- [ ] 資料庫隔離標準

**Phase 3: 模組範例**
- [ ] 將 A6 (FormFlow) 改造為第一個模組

---

## 🔜 下次作業項目

### 平台清理
| 項目 | 狀態 |
|------|------|
| 移除表單流程 Models | ✅ 已完成 |
| 移除表單流程 API | ✅ 已完成 |
| 移除表單流程 Web | ✅ 已完成 |
| 清理 __init__.py 引用 | ✅ 已完成 |
| 檢查其他檔案的引用 | ⏳ 待執行 |
| 建立獨立資料庫 | ⏳ 待執行 |
| 驗證平台可運行 | ⏳ 待執行 |

### 模組標準制定
| 項目 | 狀態 |
|------|------|
| 認證接口標準 | ⏳ 待執行 |
| 資料接口標準 | ⏳ 待執行 |
| 權限接口標準 | ⏳ 待執行 |
| 選單整合標準 | ⏳ 待執行 |
| 路由掛載標準 | ⏳ 待執行 |
| 資料庫隔離標準 | ⏳ 待執行 |

---

## 📝 備忘

### Forgejo (版本控制)
- **URL**: http://192.168.0.16:3000/
- **Repo**: http://192.168.0.16:3000/forgejoadmin/BeakPlatform
- **API Token**: `be6f8e52f155aa026ac12c5bd470114aa7c54333`

### 相關專案
- **BeakMask**: `/opt/BeakMask` — 完整系統（含表單流程）
- **A6 (FormFlow)**: `/opt/FormFlow/a6` — 表單流程 MVP

---

*最後更新: 2026-01-23 (專案初始化)*
