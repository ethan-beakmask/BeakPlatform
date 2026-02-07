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

---

## 服務配置

| 項目 | 值 |
|------|-----|
| 主服務 | http://192.168.0.16:7000 (Nginx port 80) |
| DevTools | http://192.168.0.16:7001 |
| 資料庫 | beakplatform_dev |
| Forgejo | http://192.168.0.16:3000/forgejoadmin/BeakPlatform |

---

*最後更新: 2026-02-07*
