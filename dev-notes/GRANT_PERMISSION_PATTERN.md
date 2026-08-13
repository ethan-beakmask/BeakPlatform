# Grant-Based Permission Pattern (部門/社群/個人准入模式)

## 概述

BeakPlatform 通用的細粒度權限控制模式，用於控制「誰可以存取特定資源」。

取代簡單的角色 checkbox 方式，改用部門/社群/個人三種 grant_type 的多重選擇，
支援階層繼承（include_children），實現精確的存取控制。

## 適用場景

- 子系統網頁准入控制（已實作: `DcSiteMapPermission`）
- 表單填寫權限（已實作: `FwMappingPermission`）
- 未來任何需要「誰可以存取 X」的功能

## 資料模型

### 必要欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `grant_type` | VARCHAR(20) | `department` / `group` / `user` |
| `grant_target` | VARCHAR(100) | 目標的 secure_code（部門/社群/帳號），或 `__ORG_ROOT__` 虛擬企業根 |
| `grant_target_name` | VARCHAR(200) | 顯示名稱（寫入時記錄，避免查詢時解析） |
| `include_children` | BOOLEAN | 僅 department/group 有效。TRUE = 含子部門或下層群組 |

### 關聯欄位

依附的目標資源欄位，如 `node_secure_code`（SiteMap）、`mapping_secure_code`（FormWorkflow）。

### 准入邏輯

```
if 資源無任何 grant permission 記錄:
    → 開放（依上層系統預設，如：社群成員皆可進入）

if 資源有 grant permission 記錄:
    for each permission:
        if grant_type == 'user' and grant_target == 當前用戶:
            → 允許
        if grant_type == 'department':
            if include_children:
                → 用戶所屬部門的祖先鏈是否包含 grant_target
            else:
                → 用戶是否直接屬於 grant_target 部門
        if grant_type == 'group':
            if include_children:
                → 用戶所屬群組的祖先鏈是否包含 grant_target
            else:
                → 用戶是否直接屬於 grant_target 群組
    → 全不匹配則拒絕
```

多條規則之間為 **OR 邏輯**（匹配任一即允許）。

### 虛擬企業根 `__ORG_ROOT__`

選擇企業根 + include_children = 匹配該企業下所有部門（或所有群組）。
用於快速設定「全企業」權限。

## 祖先鏈演算法

```python
def _build_ancestors(unit_sc, ancestors, org_sc):
    """遞迴建立單位祖先鏈（含自身 + 虛擬企業根）"""
    current = unit_sc
    while current:
        ancestors.add(current)
        unit = OrganizationalUnit.query.filter_by(
            secure_code=current, org_secure_code=org_sc, is_deleted=False
        ).first()
        if not unit or not unit.parent_secure_code:
            break
        current = unit.parent_secure_code
    ancestors.add('__ORG_ROOT__')
```

延遲建立：只有遇到 `include_children=True` 的規則時才建立祖先鏈，避免不必要的查詢。

## 後端 API 慣例

### 新增規則

```
POST /api/.../permissions
Body: {
    "grant_type": "department",
    "grant_target": "<secure_code>",
    "grant_target_name": "顯示名稱",
    "include_children": true
}
```

### 取得規則列表

```
GET /api/.../permissions
Response: {
    "success": true,
    "data": [
        {
            "secure_code": "...",
            "grant_type": "department",
            "grant_target": "...",
            "grant_target_name": "研發部",
            "include_children": true
        }
    ]
}
```

### 刪除規則

```
DELETE /api/.../permissions/<secure_code>
```

## 前端 UI 慣例

### HTML 結構

1. **規則列表**: `dc-perm-list` 容器，每行顯示類型標籤 + 名稱 + 刪除按鈕
2. **新增區域**: 類型選擇 + 目標選擇 + include_children checkbox + 新增按鈕
3. **目標選擇器**:
   - 部門/社群: 樹狀選擇器 (`dc-perm-tree-box`)，從 `/api/units/departments?tree=true` 或 `/api/units/groups?tree=true` 載入
   - 個人: 下拉選單，從 `/api/users?per_page=100` 載入

### CSS class 前綴

- nocode_builder 模組: `dc-perm-*`
- form_workflow 模組: `fw-perm-*`
- 新模組建議使用各自前綴

### JS 方法命名慣例

| 方法 | 用途 |
|------|------|
| `loadXxxPermissions(targetSc)` | 載入規則列表 |
| `addXxxPermRule()` | 新增規則 |
| `deleteXxxPermRule(permSc)` | 刪除規則 |
| `onPermTypeChange()` | 類型切換時重載目標選項 |
| `_loadPermTargets(grantType)` | 載入指定類型的可選目標 |
| `_renderPermTree(container, nodes, depth)` | 渲染樹狀選擇器 |

## 實作參考

| 功能 | Model | API | JS | CSS |
|------|-------|-----|----|----|
| SiteMap 准入 | `nocode_builder/models/site_map_permission.py` | `nocode_builder/api/site_map_api.py` | `nocode_builder/js/site-map-editor.js` | `nocode_builder/css/nocode-builder.css` (dc-perm-*) |
| 表單填寫權限 | `form_workflow/models/mapping_permission.py` | `form_workflow/api/mapping_permissions.py` | `form_workflow/js/mappings.js` | `form_workflow/css/mappings.css` (fw-perm-*) |

## 新功能接入步驟

1. 建立 permission model（參考 `DcSiteMapPermission` 或 `FwMappingPermission`）
2. 建立 migration（加 grant_type/grant_target/grant_target_name/include_children）
3. 建立 API（GET/POST/DELETE）
4. 前端：複用樹狀選擇器邏輯，加入規則列表 UI
5. 准入檢查：引入祖先鏈演算法，在 service 層做 permission 匹配

---

*最後更新: 2026-04-07*
