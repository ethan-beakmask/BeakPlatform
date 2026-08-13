# BeakPlatform 權限模型（4+1）

> 2026-07 權限簡化工程定版。取代散落各處的舊描述；與實作不符時以本文為準並回報修正。
> 演進脈絡：四層 user_type 硬區隔（2025-09）→ 角色細化（2025-11）→ 三軌並存的複雜化 → 本次收斂為兩軌。

## 1. 模型總覽：四層身分 + 一個公開資料隔離區

```
身分階梯（帳號體系，user_type 硬界線）
  SYSTEM_ADMIN ─ ORG_ADMIN ─ EMPLOYEE ─ EXTERNAL     ← 四層，互不穿透
                                                        同一自然人跨層 = 兩個帳號

公開資料隔離區（非帳號體系，另一維度）
  NoCode Portal 公開用戶（GUEST / PUBLIC_USER）
  - 獨立 session（不用 Flask-Login），@public_route 白名單進入
  - 只碰 per-子系統 SQLite，碰不到主 PostgreSQL
  - 資料流僅經 DataBridgeService 單向橋接（外→內限 survey_response/registration/feedback）
  - 現況：僅認證骨架，公開資料展示尚未接線（portal_public.html 為 stub）
```

**不稱「五層」的理由**：四層是「帳號身分」的階梯；公開區是「無帳號 + 資料面物理隔離」，
性質不同。硬編成第五階會誤導後續開發把它接進角色系統。

## 2. 三段式授權（各司其職）

| 段 | 問題 | 機制 | 資料 |
|----|------|------|------|
| 層界 | 這功能開放給哪幾層？ | 鑰匙 1：MenuPermission（user_type）+ 路由 decorator | menu_permissions（全站一份） |
| 層內 | 層內誰真的看得到/進得去？ | 鑰匙 2：MenuRoleRequirement × UserRoleAssignment | menu_role_requirements（每企業一份） |
| 欄位 | 看到的畫面露出哪些欄位？ | EGRESS-01 出口政策（clear/masked/hidden） | egress policy（每資源） |

核心原則（明文化，取代散落 12 處的隱性特例）：

1. **user_type 是唯一的身分硬界線**。角色永不跨層——不存在「一個角色讓 EMPLOYEE 取得 ORG_ADMIN 能力」。
2. **角色只做層內細分，且僅對 EMPLOYEE / EXTERNAL 生效**。
   SYSTEM_ADMIN / ORG_ADMIN 在選單樹與 PageRoleGuard 一律 bypass 角色檢查
   （`_menu_tree.py`、`page_role_guard.py`）——這是規則，不是妥協。
   ORG_ADMIN 層內若未來需要細分（副管理員），延伸同一機制另案處理。
3. **雙鑰匙 fail-closed**：選單無角色需求 → EMPLOYEE/EXTERNAL 一律不可見、URL 直接存取被
   PageRoleGuard 擋下並強制登出。
4. **SEC-02 裁決**：「SYSTEM_ADMIN 不享特權」只適用於 RBAC permission code（資源層）與模組合約；
   選單樹與 PageRoleGuard 對 SYSTEM_ADMIN 的 bypass 是刻意設計（其隔離靠 menu_permissions
   層屬性 + `@system_admin_required`）。兩者並存不是矛盾。

## 3. 功能開放給多層的標準做法（SOP）

例：帳號管理原為 ORG_ADMIN 專用，要開放給 EMPLOYEE 層的人資角色協同管理：

1. **路由層**：目標路由由 `@admin_required` 改為不鎖管理員（參考 `open_defense_web.security_cases`
   刻意不鎖的寫法），存取交給鑰匙 2。API 若涉及資源層另行評估。
2. **鑰匙 1**：選單的 menu_permissions 增列 EMPLOYEE（模組選單改模組定義的 `user_types`
   再 `flask module sync --force`，直接改 DB 會被同步沖掉；父 header 同步增列，
   員工無可見子項時 header 會被 `_prune_empty_parents` 自動裁剪）。
3. **鑰匙 2**：各企業管理員在 權限中央 → 功能視角 → 角色存取需求 [編輯] 勾選層內角色
   （可含企業自訂角色）；或 SYSTEM_ADMIN 在 /menu/ 編輯頁以系統預設角色批量套用全企業。
4. **欄位級**（如需要）：為資源設 egress policy 決定該角色語境下的欄位呈現。

這是「功能宣告多層 + 各層角色細分」，不是「角色跨層」。

**「能看見就能用」試點（2026-07-16，open_defense.dashboard）**：web 頁面路由不掛
身分 decorator（僅留 `@module_access_required`），身分+角色統一由 PageRoleGuard
雙鑰匙把關；頁面消費的資料 API 掛 `@page_keys_required('<menu_code>')` 與所屬選單頁
共用同一組鑰匙（`security/decorators.py`）。目標：改選單/角色設定即改實際存取，
不再出現「選單看得見、進去 403」。試點驗證後逐步推廣到全平台頁面路由；
無對應 MenuItem 的孤兒路由仍須保留 decorator（PageRoleGuard 對其放行）。

**Phase B 全平台推廣（2026-07-17，migration 084）**：「選單即授權」已推到全部
`@admin_required` web 頁面路由。做法（方案 B「URL 領地」）：

- **route 型選單改 url 型**：17 個平台選單的 link_target 由 endpoint 名稱改為 URL
  路徑（如 `users.list_users` → `/users/`），使 PageRoleGuard 的**最長前綴匹配**罩住
  該區全部子路由（create/edit/delete/view），執法單一來源。`menu_defaults`（factory
  還原預設）同步更新。
- **web 層 `@admin_required` 全面移除**（99 處 → 剩 2 處孤兒：`admin.index`、
  `admin.test_treegrid`，因無 MenuItem 對應而保留）。
- **孤兒頁補選單**：`positions`（職位設定，掛職級職稱）、`delegations`（代理授權，
  掛帳號管理）、`units`（組織單位，頂層），Key1=ORG_ADMIN、Key2 複製 users 選單的
  各企業 ORG_ADMIN 角色。
- **注意**：新增此類頁面路由時**不掛身分 decorator**，改為確保 menu_items 有 url 型
  選單（路徑前綴 = 該區領地）；區內新增子路由自動被罩住。API 路由（`/api/` 前綴）
  不在 guard 範圍，單頁專屬資料 API 掛 `@page_keys_required('<menu_code>')`。

**Phase C 權限管理中心（2026-07-17，migrations 085/086）**：`/access/` 四 tab
（功能授權雙鑰匙 / 角色含 exclusive_group 與 RBAC / 帳號配角色 / 健檢）成為權限
管理唯一入口；舊 `/permissions/`、`/roles/`、`/admin/account-roles/` 已退役，
`/menu/` 瘦身為純結構編輯（建立頁保留 Key1 初始勾選）。規格：
`dev-notes/ACCESS_CENTER_SPEC.md`。互斥群組檢查收斂於
`services/role_assignment_service.py`。

### 3.1 模組預設角色（module default roles，2026-07-16）

模組可在 `MODULE_INFO` 宣告 `default_roles`（角色）與 `default_menu_role_requirements`
（鑰匙 2），採購該模組的企業自動獲得這套角色，解決「買了模組卻無角色可配發」的缺口：

- **Seeding 時機**：(a) 新增合約時（`OrganizationService.create_contract` 依 modules_config
  觸發）；(b) `flask module sync` 對所有持有效合約的企業補種（冪等）
- **碰撞政策**：企業已有同 code 角色 → 跳過不覆蓋（保護企業自訂），但鑰匙 2 仍綁到既有角色
- **角色屬性**：`role_level=MODULE`、`is_system_role=true`、scope GLOBAL
- **設計哲學**：模組只給最小預設集合（如 open_defense 的「資安人員」SECURITY_STAFF），
  值班分工（L1/L2/主管等）由企業依 `docs/guides/SOC_ROLE_DESIGN_GUIDE.md` 自行設計
- 實作：`services/module_role_service.py`；合約到期/停用時角色保留（選單已被合約過濾擋下）
- 待辦（另案）：form_workflow 的 FORM_DESIGNER/FLOW_DESIGNER 目前烘在平台 17 個預設角色
  （`organization_service._create_default_roles`），應遷移到本機制

## 4. 保留的資源層（軌 C 現況）

permission code（permissions / role_permissions）已退出選單/頁面授權，但仍活躍於：

- **ResourceGateway** 資源 CRUD 檢查（`LIST_RBAC_ENFORCED_MODELS` 約 24 個 model，員工 API 授權）
- **模組 API**：`platform/auth.py` 的 `has_permission` / `require_permission`（form_workflow 使用中）
- 管理入口：權限中央的角色權限矩陣（仍可編輯，服務上述兩者）

已退役/移除：

- `menu_items.required_permission` 不再參與選單可見性（欄位保留，僅供參考顯示）
- `@permission_required` decorator（唯一使用點已改 `@admin_required`）
- `URLAccessPolicy`、page access 攔截層（fail-open no-op）、`platform/auth` 以外的重複 RBAC 查詢

## 5. 已知注意事項（非 bug，設計備忘）

- **停用角色仍讓選單可見**：鑰匙 2 比對 UserRoleAssignment 不查 Role.is_active
  （`UserRoleAssignment.get_active_role_secure_codes`）；permission_service 端則有查。
  權限中央衝突偵測會標示「角色已停用」。如需收緊，統一在 get_active_* 加 Role JOIN。
- **無對應 MenuItem 的路由 PageRoleGuard 放行**：只剩 decorator 把關。新增敏感路由必掛
  decorator；SEC-03 啟動稽核只涵蓋有 MenuItem 的 route 型端點。
- **ABAC 未實作項**：RANK / DELEGATE 條件與 `is_subordinate_of` 運算子恆回 False（fail-closed）。
- **admin 帳號持員工角色無效果**：ORG_ADMIN bypass 角色檢查，指派角色給管理員帳號不會有作用
  （兩帳號制下應指派給其 EMPLOYEE 帳號）。

## 6. 相關檔案

- 攔截鏈：`auth_interceptor.py` → `PageRoleGuard.enforce`（鑰匙 1+2，強制登出）→ decorator → ResourceGateway
- 選單樹：`services/_menu_tree.py`（過濾順序見 `get_user_menu_tree` docstring）
- 角色有效性唯一實作：`models/associations.py` `UserRoleAssignment.get_active_*`
- 企業級鑰匙 2 管理：`api/menu.py` `/api/menu/<sc>/roles`（GET/PUT，@admin_required）+ 權限中央功能視角
- 出口政策：`dev-notes/EGRESS_POLICY_SPEC.md`
- NoCode 公開區：`modules/nocode_builder/`（portal_auth_service / data_source_manager / data_bridge_service）
