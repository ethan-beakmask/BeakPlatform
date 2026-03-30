# 企業預設值檢查表

建立新企業時，系統自動建立的預設項目清單。

## 實作狀態

| 項目 | 狀態 | 說明 | 實作位置 |
|------|------|------|----------|
| 企業管理員帳號 | OK | `admin@{domain}`, 密碼 `ChangeMe123!` | `OrganizationService._create_default_admin()` |
| 預設角色 (4個) | OK | ORG_ADMIN, DEPT_MANAGER, GROUP_CONVENER, EMPLOYEE | `OrganizationService._create_default_roles()` |
| 管理員專用單位 | OK | 特殊單位，供管理員專用分類使用 | `OrganizationService._create_default_units()` |
| 預設表單分類 | OK | flow-log (流程記錄) | `OrganizationService._create_default_form_categories()` |

## 詳細規格

### 1. 企業管理員帳號
- **帳號**: `admin@{domain_name}`
- **密碼**: `ChangeMe123!` (首次登入需變更)
- **類型**: `UserType.ORG_ADMIN`
- **標記**: `is_original_admin=True`, `must_change_password=True`

### 2. 預設角色

| 代碼 | 名稱 | 範圍 | 主管 |
|------|------|------|------|
| ORG_ADMIN | 企業管理員 | GLOBAL | Yes |
| DEPT_MANAGER | 部門主管 | DEPARTMENT | Yes |
| GROUP_CONVENER | 群組召集人 | GROUP | Yes |
| EMPLOYEE | 企業成員 | GLOBAL | No |

### 3. 管理員專用單位

用於表單流程分類的「表單中心可見部門/群組」設定，讓某些分類只有管理員能看見。

| 欄位 | 值 |
|------|-----|
| code | `ADMIN_ONLY` |
| name | `管理員專用` |
| unit_type | `GROUP` |
| description | `系統保留群組，僅管理員可見` |
| is_system_unit | `True` (新增欄位) |

**可見性規則**:
- 系統管理員 (`UserType.SYSTEM_ADMIN`) 視為屬於此單位
- 企業管理員 (`UserType.ORG_ADMIN`) 視為屬於此單位
- 一般用戶不屬於此單位

### 4. 預設表單流程分類

| 代碼 | 名稱 | 說明 | 可見部門 |
|------|------|------|----------|
| `flow-log` | 流程記錄 | 系統預設記錄流程的 log | 管理員專用 |

**欄位設定**:
```python
{
    'code': 'flow-log',
    'name': '流程記錄',
    'description': '系統預設記錄流程的 log',
    'visible_in_form_design': True,
    'visible_in_workflow_design': True,
    'visible_in_form_center': True,
    'allowed_units': ['{ADMIN_ONLY_UNIT_SECURE_CODE}'],
    'display_order': 999,
    'is_active': True
}
```

---

## 預設值設定

| 設定項 | 預設值 | 說明 | 狀態 |
|--------|--------|------|------|
| user_limit | 5 | 新企業預設帳號上限 | OK |
| admin_password | `ChangeMe123!` | 預設管理員密碼 | OK |
| customer_type | TRIAL | 預設客戶類型 | OK |

---

## 實作注意事項

1. 所有預設項目在 `OrganizationService.create_organization()` 中建立
2. 管理員專用單位需標記 `is_system_unit=True`，避免被誤刪
3. `allowed_units` 存儲的是 `secure_code`，不是 `code`
4. 表單分類的 `code` 在企業內唯一

---

*最後更新: 2025-12-27*
