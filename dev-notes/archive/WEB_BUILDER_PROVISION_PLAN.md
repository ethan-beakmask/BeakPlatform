# Web Builder 子系統申請配置流程計劃

> 本文件為上下文傳承用，記錄完整流程規格、已完成與待做項目。
> 來源: `temp_WEB_Builder全程序.txt` + 2026-03-06 對話討論

---

## 完整業務流程

```
A. 系統管理員
   1. [略] 模組安裝驗證 (等 GitHub 發表)
   2. [未做] 模組清單 /admin/module-list (顯示模組+企業+期限)
   3. [完成] 透過合約管理 /organizations/ 授權企業使用模組

B. 企業管理員
   4. [完成] 模組權限管理 /admin/module-permissions
      - 四種 target: ROLE / DEPARTMENT / GROUP / ACCOUNT
      - 目前只控制「能不能用」(選單可見性 + 路由攔截)

C. 模組使用者 (以 Web Builder 為例)
   6. [完成] 子系統開發申請流程:
      a. [完成] 表單申請 -> 審批通過 -> 自動配置 (provision_service)
      b. [完成] 配置內容: 建立子系統 + 社群 + 選單 + 模組權限
      c. [完成-A] 選單建立時 is_active=false (申請通過不可見)
      d. [完成-B] 開發者按「上線」時 menu is_active=true
      e. [完成-C] 子系統選單可見性: 社群成員身份過濾
      f. [完成-D] 社群管理權限下放給團長

D. 一般用戶
   - [完成] 團長: 管理社群成員 (拉團員) -- /my-groups/ 入口
   - 團員: 從子系統 menu 看到已上線的子系統，使用設計者設定的頁面
```

---

## 已完成項目 (2026-03-06)

### 1. @module_access_required decorator
- **檔案**: `backend/app/security/decorators.py`
- **功能**: 路由層模組權限檢查，admin 自動放行
- **用法**: `@module_access_required('web_builder')`

### 2. Web Builder 路由權限隔離
- **受保護路由** (需 web_builder 模組權限):

| 檔案 | 路由 | 說明 |
|------|------|------|
| `modules/nocode_builder/web/__init__.py` | `/nocode-builder/sub-systems` | 子系統管理列表 |
| 同上 | `/nocode-builder/sub-systems/<sc>/config` | 子系統配置 |
| 同上 | `/nocode-builder/my-projects` | 我的開發案 |
| 同上 | `/nocode-builder/studio/<sc>` | 設計器 |
| 同上 | `/nocode-builder/studio-test/<sc>` | Grid 測試頁 |
| 同上 | `/nocode-builder/lab` | 佈局設計器 (新) |
| 同上 | `/nocode-builder/lab/<sc>` | 佈局設計器 (編輯) |
| `modules/nocode_builder/api/project_api.py` | `/api/nocode-builder/projects*` | 全部 10 條 API |

- **不受限路由** (登入+內部成員檢查):

| 路由 | 說明 | 內部檢查 |
|------|------|----------|
| `/nocode-builder/sub-systems/<sc>/portal` | 團員 Portal 入口 | role_type 檢查 |
| `/nocode-builder/pages/<sc>` | 頁面預覽 | 無額外限制 |
| `/api/nocode-builder/views/<sc>/rows*` | 資料 API | _check_sub_system_crud |

### 3. SubSystemProvisionService
- **檔案**: `modules/nocode_builder/services/provision_service.py`
- **觸發條件**: form_name='子系統開發申請' OR form_code='FORM_WF8AEB7774_EA31'
- **Hook 位置**: `modules/form_workflow/services/workflow_engine.py` complete_workflow() 尾部
- **配置內容**:
  1. 建立社群 (OrganizationalUnit, type=GROUP, code=PRJ_{NAME})
  2. 建立子系統 (DcSubSystem, status=draft, developers=[申請者])
  3. 申請者成為社群 MANAGER
  4. 建立選單項 (MenuItem, parent=sub_system, link=portal URL)
  5. 關聯子系統 menu_item_secure_code
  6. 授予申請者 web_builder ACCOUNT 權限 (ModuleAccessService.add_access)
- **防重複**: 選單 code 衝突時擋下
- **Tenant context**: 用 form_instance.org_secure_code 設定 g.current_org_secure_code

### 4. UI 變更
- 子系統列表加「設計器」按鈕 -> `/nocode-builder/studio/<sc>`
- 硬寫的「訂餐系統」選單 (SkAjp3WaR6WeLmlaMn8VfG) 已軟刪除

### 5. 測試驗證
- FORM-20260305-0001 provision 成功
- 子系統 SC: `hCsbAeeuxUQVSnHQa14J6M`
- 選單 SC: `w5PrMLQWyICI_Av91G_YvZ`
- 模組權限: `nH5liUKQikH1NM2osVVXuF` (ACCOUNT -> web_builder)
- 重複 provision 正確擋下

---

## 待做項目

### A. Provision 時 menu is_active=false [小改]
- **檔案**: `modules/nocode_builder/services/provision_service.py`
- **改動**: `_create_menu_item()` 中 `is_active=True` -> `is_active=False`
- **效果**: 申請通過後選單存在但不可見，只有管理員在選單管理看得到

### B. Publish/Unpublish 連動 menu is_active [小改]
- **檔案**: `modules/nocode_builder/services/project_service.py`
- **改動**:
  - `publish()`: 找到子系統關聯的 menu_item，設 is_active=True
  - `unpublish()`: 設 is_active=False
- **前提**: DcSubSystem.menu_item_secure_code 已有值 (provision 時設定)

### C. 子系統選單可見性: 社群成員過濾 [中改]
- **問題**: 目前子系統 menu 下的選單項對所有人可見 (只要 is_active=True)
- **目標**: 只有該子系統社群的成員才能看到對應選單項
- **方案**: 在 menu_service.py 的選單建構流程中，加入子系統選單過濾邏輯
  - 子系統 menu 下的子項 -> 查 MenuItem.link_target 解析出 sub_system SC
  - 查 DcSubSystem.group_unit_secure_code -> 查 UserUnitMembership
  - 有成員身份才加入可見選單
- **涉及檔案**:
  - `backend/app/services/menu_service.py` -- 加入 Step 6.7 或修改 _build_tree
  - 可能需要新增 helper 方法
- **注意**: 企業管理員/系統管理員不過濾

### D. 社群管理權限下放給團長 [完成]
- **方案**: 方案 A+B 混合 -- `/admin/groups/` 改為 admin+團長可用，另建 `/my-groups/` 別名入口
- **改動內容**:
  1. `backend/app/web/groups.py`: `@admin_required` -> `@login_required` + 權限檢查 (admin 或有管理社群)
  2. `backend/app/web/groups.py`: 新增 `my_groups_bp` 別名路由 `/my-groups/`
  3. `backend/app/api/organizational_units.py`:
     - `list_groups()`: `@login_required`，admin 看全部，團長只看管理的社群
     - cross-member CRUD (4 條): `@login_required` + `_is_group_leader()` 檢查
     - 新增 `/api/units/group-member-candidates`: 團長用的帳號搜尋 (代替 admin-only `/api/users`)
     - 新增 helper: `_is_admin()`, `_is_group_leader()`, `_get_managed_group_scs()`
  4. `backend/app/templates/pages/admin/groups.html`: 依 `is_admin` 控制 UI
     - 非 admin: 隱藏新增/刪除/編輯社群功能，只顯示社群唯讀資訊 + 成員管理
  5. `backend/app/static/js/groups.js`:
     - 讀取 `isAdmin` flag
     - 非 admin: 使用 `/api/units/group-member-candidates` 取代 `/api/users`
     - 非 admin: 禁用社群拖放重組 (jstree dnd)

---

## 關鍵資料表關聯

```
fw_form_instances (申請單)
  |-- applicant_secure_code -> users.secure_code
  |-- form_data (JSONB): menu_items_code, dc_sub_systems_name, ...
  |
  v [provision_service]
dc_sub_systems (子系統)
  |-- group_unit_secure_code -> organizational_units.secure_code (社群)
  |-- menu_item_secure_code -> menu_items.secure_code (選單)
  |-- developers (JSONB): [user_secure_code, ...]
  |
  v
organizational_units (社群, type=GROUP)
  |-- user_unit_memberships (成員: MANAGER/DEPUTY/MEMBER)
  |
menu_items (選單)
  |-- parent_secure_code -> menu_items.secure_code (子系統 header)
  |-- link_target: /nocode-builder/sub-systems/{ss_sc}/portal
  |-- is_active: false(draft) / true(published)
  |
module_access_control (模組使用權)
  |-- module_code: 'web_builder'
  |-- target_type: 'ACCOUNT'
  |-- target_secure_code -> users.secure_code
```

---

## 選單可見性決策流程 (目標狀態)

```
用戶請求選單樹
  |
  v
MenuService.get_user_menu_tree(user)
  |
  +-- Step 1: MenuPermission 基礎
  +-- Step 1.5: 模組選單注入 (module_access_control)
  +-- Step 2-6: RBAC/合約/模組過濾
  +-- Step 6.7 [待做-C]: 子系統選單過濾
  |     |-- 「子系統」header 下的子項
  |     |-- link_target 解析 sub_system SC
  |     |-- 查社群成員身份
  |     |-- 非成員移除
  |     |-- admin 不過濾
  +-- Step 7-8: 預載 + 建構樹
```

---

*最後更新: 2026-03-14 (data_crud → nocode_builder 正名化)*
