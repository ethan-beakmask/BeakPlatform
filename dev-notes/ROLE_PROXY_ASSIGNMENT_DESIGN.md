# 角色級代理指派設計（PF-251）

> 撰寫：2026-09-06 主 Claude，依 Ethan 同日定案的六點（BBN #5402 末段）。前作 `ROLE_UNIT_APPROVAL_DESIGN.md`（PF-247）
> 把簽核者做成 (角色, 單位)，本文件把「代理」與「候補」也收進同一張表、同一條判定，退役兩個 PROXY 角色與人對人代理授權。
> 執行方式沿用 PF-247：撰寫本文件的 session 留守審查，執行 session 依第六節逐期派 codex 並驗收，每期完成後在第十一節寫差異清單。

## 一、一句話

代理人不是另一種角色，是**在一段期間內持有被代理的那個角色@單位**。`user_role_assignments` 每一列多一個「指派性質」：
`regular`（正式持有）、`proxy`（有效期內視同持有，記被代理人）、`standby`（候補，只在該角色@單位沒有任何可用的正式或代理持有者時生效）。
授權判定只剩一句話：**行為人今天持有有效的 (角色, 單位)**。任何角色都能被代理，主管只是關卡指定的角色之一；
`DEPT_PROXY1`／`DEPT_PROXY2` 與 `task_authorizer` 只認識 `DEPT_MANAGER` 的缺席順位一起退役，人對人的 `delegations` 併入同一張表。
PF-71 的「限定表單」維度保留，做在指派列上。

## 二、現況盤點（2026-09-06，附行號；會腐爛，派工前重查）

### 2.1 判定端：`modules/form_workflow/services/task_authorizer.py`（488 行）

| 位置 | 現況 | 本設計要改成 |
|---|---|---|
| `29-32` `FALLBACK_ROLE_CODES = {'DEPT_MANAGER': ('DEPT_DEPUTY','DEPT_PROXY1','DEPT_PROXY2')}`、`ALWAYS_ALLOWED_FALLBACK_CODES` | 順位表硬編碼，只有主管一項 | **刪除** |
| `35-53` `get_actor_role_units()` | 取 (role, unit) 集合，只看 `is_deleted`＋`is_valid_on(today)`，不分性質 | 改回 `{(role, unit): kind}`；`standby` 要另外判可用性 |
| `56-62` `_build_identity()`／`179-186` `_identity_role_units()` | 身分字典含 `role_units`、`role_codes` | 加 `standby_units`，`role_codes` 保留給 `approver_exposure_service.py:75` |
| `72-115` `_get_delegated_identity_data()`、`140-158` `build_actor()` | 查 `delegations` 表把授權人整組身分掛進 `actor['delegations']`，SPECIFIC 型的表單 scope 放 `delegation_scopes` | 第 1 期保留並存；第 3 期遷移後**刪除**，代理改由指派列直接進 `role_units` |
| `247-265` `_holds()` | 直接持有／全企業超集／非 POSITION 套圈 | 加「proxy 視同持有」「standby 僅在無可用持有者時」與 `allowed_form_templates` 檢查 |
| `268-298` `_unit_manager_present()` | 只為缺席順位服務：查 `DEPT_MANAGER@U` 持有者是否有人未請假 | 通用化成 `role_holding_service.has_available_holder(role, unit)`，任何角色都能問 |
| `301-342` `_match_identity()` | `319-335` 順位迴圈；`337-338` 帶 key 不看快照；`340-341` 舊佇列項快照相容 | 順位迴圈刪除；其餘不變 |
| `345-371` 表單模板快取與 `_delegation_scope_allows_task()` | 只對 delegations 的 scope 用 | 改為對任何帶 `allowed_form_templates` 的指派列用，快取沿用 |
| `374-424` `resolve_acting_identity()` | 回 `{'via': self/delegation, 'delegator_secure_code', 'acted_as_role_code'}` | 多回 `acted_as_kind`（regular／proxy／standby），`delegator_secure_code` 改由指派列的 `acting_for` 填 |
| `427-450` `delegate_from_fields()` | 把 delegation 換成 `delegate_from_*` 欄位 | 改讀 `acting_for`；輸出欄位不變 |

`can_view_task` 不存在（2026-09-06 盤點確認，別再找）；對外入口是 `can_act_on_task()`（453-466）與 `is_pending_assignee()`（469-487）。

### 2.2 節點端：`modules/form_workflow/services/node_handlers/formadapter_handler.py`（1177 行）

| 位置 | 現況 |
|---|---|
| `372-419` `_role_spec_data()` | 快照組法：`389-391` 主管清單當基底，`392-405` 依 `FALLBACK_ROLE_CODES` 加副主管（永遠）與代理人（`manager_vacant` 時），`406` 去重保序；`manager_vacant` 只是區域變數，**沒有寫進 `result.data`** |
| `347-353` `_normalized_absence_fallback()`、`154`、`330-331`、`505-533` | `absence_fallback` config 的正規化與消費 |
| `536-572` `_apply_self_target()` | 決策點 7 的三選一；「本人在快照內」的判定依賴快照含副主管與代理人 |

### 2.3 資料層與寫入路徑

- `backend/app/models/associations.py:68-119` `UserRoleAssignment`：`user／role／unit_secure_code`（unit 可 NULL＝全企業）、`valid_from`／`valid_until`（Date，105-106）、`assigned_at`、`assigned_by`（String100）。效期判定 `is_valid`（121-124）／`is_valid_on(today)`（126-132）；標準讀取 `get_active_assignments()`（145-166）與 `get_active_role_secure_codes()`（168-174），`permission_service.py:346-361`、`_menu_tree.py:224-226`、`task_authorizer` 都走這兩支。`to_dict()`（176-201）。
- **DB 沒有 (user, role, unit) 複合唯一約束**（dev 庫 `\d user_role_assignments` 只有 PK 與 `secure_code` unique，其餘單欄索引）；重複由應用層擋（`role_assignment_service.assign_role` 的 dup 查詢、`dept_membership_service.ensure_role_assignment` 的 existing 查詢）。
- 寫入點與是否過層界檢查 `role_assignment_service.ensure_role_layer_compatible()`（`63-86`，CLAUDE.md 稱 PERM-03，函式註解寫 PERM-01，同一支）：

| 寫入點 | 過層界檢查 |
|---|---|
| `role_assignment_service.assign_role()` `159-216`（權限中心 `/access/api/assign`，`api/access_center.py:44-66`） | **是**（177） |
| `dept_membership_service.ensure_role_assignment()` `37-60`、`set_dept_manager()`、`reconcile_dept_manager()` | 否（呼叫端自管） |
| `api/organizational_units.py:1056-1063` `set_unit_leadership()` 直接 `UserRoleAssignment(...)`（`role_map` 992-997：manager／deputy／proxy1／proxy2） | 否，且**繞過服務**（PF-250） |
| `api/organizational_units.py:836-840` `remove_unit_manager()` | 否 |
| `web/users.py:254-260`、`web/external_users.py:78-84`、`web/org_admins.py:237-259,423-431`、`organization_service.py:148-154`、`defaults/system_org_defaults.py:157-163` | 否（按 user_type 固定配對，結構安全） |

- 角色出廠：`organization_service._create_default_roles()` `218-510`（唯一種入函式，`create_organization` 135 行與 `init_system_organization` 980 行呼叫）：`DEPT_MEMBER`（244-258, ROLE）、`DEPT_MANAGER`（260-275, POSITION）、`DEPT_EMPLOYEE`（277-292, ROLE）、`DEPT_DEPUTY`（294-308, POSITION）、`DEPT_PROXY1`（310-324）、`DEPT_PROXY2`（326-340）、`GROUP_*`（342-390，全 ROLE）。`dept_membership_service.py:24` `DEPT_POSITION_ROLE_CODES`、`role_assignment_service.py:38-40,266` 也列了四個職位碼。
- 部門頁：`templates/pages/admin/departments.html:355-424` 四個拖放區（主管／副主管／代理人一／代理人二），`static/js/departments.js:733-825` 打 `POST/DELETE /api/units/<sc>/leadership/<position>`；`GET /<sc>/leadership`（917-976）逐一查四個角色。社群頁（`groups.js:264-287`）走 `user_unit_memberships.role_type`，**不經角色指派**，本設計不動它。
- 權限中心帳號配角色：`_tab_accounts.html:96-103` 只顯示角色名＋單位名；`access-center/accounts.js:26-30,141` 表單只有角色與單位；`role_assignment_service._build_user_roles()` `342-381` 不輸出效期。

### 2.4 人對人代理授權（`delegations`）

- Model `backend/app/models/delegation.py`：`delegator／delegate_secure_code`、`delegation_type`（FULL／APPROVAL／SPECIFIC，26-30）、`status` 快照（81-86，畫面一律用 `effective_status` 140-150）、`effective_from／until`（Date，89-90）、`approval_limit`（93）、`allowed_process_types`（97；PF-71 起存表單模板 sc 的 JSON 陣列，`get_allowed_form_templates()` 192-202 解析失敗回空＝fail-closed）、`reason`、`revoked_*`。
- **沒有 service 層**：CRUD 直接寫在 `web/delegations.py:126-247,250-343`（管理員頁，無路由級 decorator，靠 PageRoleGuard 雙鑰匙）與 `api/my_delegations.py:108-174`（PF-236 員工自助，類型寫死 FULL，`_deny_non_member` 擋 EXTERNAL／SYSTEM_ADMIN）。**兩條建立路徑都沒有層界檢查**，管理員頁的候選人（129-133）連 EXTERNAL 都沒濾掉。
- 讀取端：`task_authorizer.py:72-115`（第四層身分）、`calendar_projection_service.py:287-321`（投影成行事曆事件）、`approver_exposure_service.py:33-43`（請假是否已被代理蓋住）、`api/calendar.py:140-163`（LEAVE 事件的 `delegation_hint.create_url`）、`resource_gateway.py:50,87`（已註冊 `delegation` 資源型，`my_delegations.py` 全部 `check_permission=False` 繞過）、`permission_condition.py:288-289` 的 `has_valid_delegation` 沒有任何執行器（`permission_service.py:721` 留 TODO，死定義）。
- 前端：`templates/pages/delegations/*.html`、`pages/_my_delegations.html`（personal_settings 187 行 include）、`static/js/my-delegations.js`、`css/my-delegations.css`。
- 手冊：`docs/manual/03_org_setup/delegations.md`（86 行，ORG_ADMIN）、`01_getting_started/personal_settings.md:72-93`、`07_daily_work/calendar.md:25-27,48-49,65-66,92-98,106-108`、`07_daily_work/my_delegation.md`（佔位稿）、`04_form_workflow/workflows.md:162-177`（缺席順位敘述）。
- 資料現況：dev 庫 4 筆（FULL 3／SPECIFIC 1；有效 1、PENDING 1、REVOKED 2），BELUGA 3、傳統文化製造集團 1；bpserv DemoSOC 1 筆（soc1→admin-soc1，2026-09-05 到期）。**APPROVAL 型零筆**，且 `task_authorizer.py:96-97` 本來就整筆跳過。

### 2.5 簽核記錄與顯示

- `modules/form_workflow/models/approval_record.py:34-37`：`delegate_from_secure_code／name`、`acted_as_role_code`（PF-247，值為 DEPT_DEPUTY／PROXY1／PROXY2）。寫入：`api/fc_pending.py:409,532-533`、`fc_batch.py:133`、`instance_routes.py:249`。
- 顯示：`static/.../fc-utils.js:63-66` `getActedAsText()` 三個 code 對中文；`_read_form_modal.html:62-65`、`_form_center_approval_modal.html:71-74`、`_monitor_modal.html:334-337` 顯示「（代 X 簽核）」「（以Y身分）」；`open_defense/.../security_cases.html:177-178` 只顯示 `delegate_from_name`。
- 設計器：`wf-form-adapter.js:62-63,158-170`（`faSelfTargetAction` select、`faAbsenceFallback` checkbox）、`wf-node-form-adapter.js:443-444,468-469`、`wf-save.js:127,150-151`。

### 2.6 測試現況

- `test_task_authorizer_role_unit.py` 25 案，其中 14 案直接斷言順位語意（`test_deputy_can_always_act_for_department_manager`、`test_proxy_roles_require_manager_vacancy`、`test_manager_presence_checks_*`、`test_fallback_can_be_disabled_*`、`test_deputy_in_other_department_*`、`test_delegation_uses_role_unit_identity_and_fallback`、`test_snapshot_only_user_is_denied_but_deputy_*`、`test_proxy_in_snapshot_loses_access_*`、`test_manager_full_day_leave_*`、`test_proxy_permission_follows_manager_partial_leave_time`、`test_any_present_manager_blocks_proxy_*`、`test_leave_on_another_date_*`、`test_absence_fallback_false_ignores_manager_leave`、`test_legacy_actor_without_local_now_*`）——第 1 期**改語意重寫**，不是刪。
- `test_formadapter_role_unit.py` 23 案，5 案依賴順位（`test_unit_position_snapshot_*` 三案、`test_self_target_escalation_uses_absence_fallback_on_parent`、`test_timeout_reference_user_receives_role_unit_snapshot`）。
- `test_task_authorizer_delegate_from.py` 11 案（PF-71 表單 scope）、`test_my_delegations_api.py` 13 案、`test_delegations_prefill.py` 5 案、`test_delegation_effective_status.py` 5 案——第 3 期遷移時改寫成指派列語意。
- `test_dept_membership_service.py`、`test_hr_lookup_node.py:203`、`test_approval_record_acted_as.py:34` 用 DEPT_DEPUTY／PROXY 當 fixture，PROXY 退役後改角色碼即可。

### 2.7 順帶發現（不在本設計內，記在 PF-250）

- `api/organizational_units.py:418-422` 對 `unit.manager_secure_code` 等四個**不存在的欄位**賦值（model 與 DB 都沒有），是無效賦值不報錯；PF-249 改 `soft_delete_unit()` 時原樣保留了。
- `backend/app/platform/data.py:315` `_department_to_dict()` 讀 `dept.manager_secure_code`，同一個不存在的欄位，被觸發會 `AttributeError`（呼叫點 196／224／336）。

## 三、目標模型

### 3.1 指派列的新欄位（`user_role_assignments`）

| 欄位 | 型別 | 語意 |
|---|---|---|
| `assignment_kind` | VARCHAR(10) NOT NULL DEFAULT `'regular'` | `regular`／`proxy`／`standby` |
| `acting_for_user_secure_code` | VARCHAR(32) NULL，FK users | 被代理的人；`proxy` 必填，`standby` 可空（候補的是位子不是人），`regular` 一律 NULL |
| `allowed_form_templates` | JSONB NULL | 表單模板 sc 陣列；NULL＝不限。`regular` 一律 NULL |
| `source_ref` | VARCHAR(100) NULL | 來源：流程實例 `execution_code`、`admin:<user sc>`、`migration:<腳本>`、`self:<user sc>` |
| `grant_reason` | TEXT NULL | 事由（自 `delegations.reason` 遷入） |

既有欄位沿用：`valid_from`／`valid_until`（Date）是 proxy 的效期，`assigned_by` 記操作者，`is_deleted`＝撤銷。
**不加 (user, role, unit) 唯一約束**：同一個人可以同時是某角色@單位的 `regular` 與另一列 `proxy`（副主管同時被指定代理主管），性質不同就是兩列。
索引加 `(org_secure_code, role_secure_code, unit_secure_code, assignment_kind) WHERE is_deleted = false`。

`fw_approval_records` 加 `acted_as_kind VARCHAR(10) NULL`（regular／proxy／standby）；`acted_as_role_code` 保留，改記「以代理／候補身分命中的角色碼」，regular 一律 NULL。

### 3.2 三種性質的語意

| kind | 何時算持有 (R, U) | 誰能建 | 撤銷 |
|---|---|---|---|
| `regular` | `is_valid_on(today)` | 既有路徑不變 | 既有路徑不變 |
| `proxy` | `is_valid_on(today)`，與 regular 完全等價；另受 `allowed_form_templates` 限制 | R@U 的 `regular` 持有者本人（同意流程或自助）、ORG_ADMIN 直接指派 | 被代理人、代理人本人（放棄）、ORG_ADMIN；軟刪除 |
| `standby` | `is_valid_on(today)` **且** R@U 此刻沒有任何「可用」的 regular／proxy 持有者 | ORG_ADMIN（部門頁候補代理人區塊）、R@U 的 regular 持有者 | 同上 |

「可用」＝帳號未刪除且啟用、指派今天有效、此刻不在請假時段（`ScheduleService.is_on_leave(user, org_local_now)`，第 5 期定義，不看來源）。
多個 standby 同時生效，不分順位（現況 PROXY1／PROXY2 在職缺時本來就同時放行）。
`standby` 不參與套圈（它跟 POSITION 一樣是「位子」）；`proxy` 套圈與否跟被代理的角色一致（代理資訊群成員就套圈到子單位，代理主管不套圈）。
**代理不得轉代理**：只有 `regular` 持有者能授出 proxy／standby；`proxy` 持有者對該角色沒有授權能力。
**層界**：建立 proxy／standby 一律過 `ensure_role_layer_compatible(user, role)`，EXTERNAL 帳號不能當內部角色的代理人，反向亦然。

### 3.3 判定規則（取代前作 3.3 第 4 條之後與 3.4 整節）

```
holds(actor, R, U, task):
  for (r, u, kind, scope) in actor.assignments:           # 今天有效、未刪
    if r != R: continue
    if kind == 'standby' and has_available_holder(R, u): continue
    if scope is not None and task.form_template not in scope: continue
    if u == U or u is None: return kind                    # 直接持有／全企業超集
    if U is None: return kind
    if role_type(R) != POSITION and U in ancestors(u): return kind   # 套圈，standby 不套（上一行已排除 standby 的 u != U）
  return None
```

`has_available_holder(R, U)` 唯一實作在新檔 `backend/app/services/role_holding_service.py`：查 R@U（含全企業指派）的 regular／proxy 持有者，過濾帳號狀態、效期、請假；結果快取在 actor。
`_match_identity()` 對 ROLE／DEPARTMENT 帶 key 的任務：`holds()` 回 kind 就放行並記 `acted_as_kind`，否則拒絕；舊佇列項（無 key）維持快照相容；USER／INITIATOR／DYNAMIC 不變。

### 3.4 正副主管是三個角色，不是一個角色加順位（Ethan 2026-09-06 定案 A）

前作把「副主管永遠可簽」寫進順位表，是因為只有一個 `DEPT_MANAGER` 角色。Ethan 定案：**部門有三個主管類角色**，
關卡指哪一個由流程設計師決定，判定端不需要任何特判：

部門角色因此共五個，兩個成員類（ROLE，套圈）、三個主管類（POSITION，不套圈）：

| 角色碼 | 顯示名 | 型別 | 誰持有 | 用途 |
|---|---|---|---|---|
| `DEPT_MEMBER`（既有） | 部門成員 | ROLE，套圈 | 部門內**所有人，含正副主管**（出廠說明：「部門通用成員角色，部門內所有人(主管+員工)皆擁有」） | 「資訊部全員」這類關卡（全員開會簽到）指它，不必主管一次員工一次；`DEPARTMENT` 舊型別的別名 |
| `DEPT_EMPLOYEE`（既有） | 部門員工 | ROLE，套圈 | 非管理職；設為正主管或副主管時撤銷（決策點 I） | 只要員工不要主管的關卡 |
| `DEPT_HEAD`（新） | 部門主管 | POSITION | 正主管與副主管**都**持有 | 「正副任一即可」的關卡；正副互相代理，兩人都缺席才輪到候補／代理 |
| `DEPT_MANAGER`（既有，改顯示名） | 部門正主管 | POSITION | 只有正主管 | 必須正主管本人（或其代理）的關卡 |
| `DEPT_DEPUTY`（既有） | 部門副主管 | POSITION | 只有副主管 | 必須副主管本人（或其代理）的關卡 |

- 三個都是 POSITION 型、都不套圈，都以 (角色, 單位) 指派——「xx部門正主管」就是 `DEPT_MANAGER@xx`，**建立部門不需要新增角色列**，
  刪除部門時 PF-249 的 `purge_unit_memberships()` 會把三種指派一起收掉。若 Ethan 要的是每個部門一組獨立角色列，那是角色模型的變更
  （`roles.code` 跨企業不唯一、權限中心以「角色@單位」顯示、`ensure_role_layer_compatible` 以角色為單位），本設計不採，理由寫在此供覆核。
- `DEPT_HEAD@U` 由部門頁**連帶**授予：設正主管＝`DEPT_MANAGER@U`＋`DEPT_HEAD@U`，設副主管＝`DEPT_DEPUTY@U`＋`DEPT_HEAD@U`，
  卸任時連帶撤銷；唯一寫入實作在 `dept_membership_service`（第 3 期）。既有企業由第 1 期遷移腳本回填。
- 代理由發動人決定代理哪一個：正主管可授出 `DEPT_MANAGER@U` 與／或 `DEPT_HEAD@U`；副主管可授出 `DEPT_DEPUTY@U` 與／或 `DEPT_HEAD@U`。
  正副互相代理不需要任何指派，因為兩人本來就都持有 `DEPT_HEAD@U`。
- 設計器的「主管缺席時由副主管／代理人接手」勾選**移除**；`absence_fallback` config 保留讀取但不再有作用。
  既有 graph 與發行快照中「`DEPT_MANAGER`＋`absence_fallback=true`」的關卡，語意是「正主管，副主管永遠可簽」，最接近 `DEPT_HEAD`——
  由遷移腳本自動改指 `DEPT_HEAD`（保留今天的行為，決策點 H 定案）；`absence_fallback=false` 的維持 `DEPT_MANAGER`。

### 3.5 限定表單維度（Ethan 定案：保留）

`allowed_form_templates` 存在指派列上，判定沿用 `task_authorizer._delegation_scope_allows_task()` 的比對與 `_task_form_template_secure_code()` 快取，改成對每一列指派做。
`regular` 列一律 NULL；UI 上只有 proxy／standby 的建立表單提供「限定表單」多選（沿用 `web/delegations.py` 的 `allowed_form_templates[]` 與 PF-71 的模板清單來源）。
決策點 C 定案：standby 也吃。**範圍只限制簽核任務**：`get_active_assignments()` 給權限與選單用時不看 `allowed_form_templates`，限定表單的代理人在效期內仍拿到該角色的選單與 permission code（第 1 期複審確認，刻意接受——限定的是「能簽什麼」不是「能看什麼」）。

### 3.6 直屬主管推導、快照、投影不受代理影響的部分

- `unit_resolver.iter_manager_chain()`／`resolve_direct_manager()` **只認 `regular`**：核決鏈找的是「誰的職等決定上限」，代理人簽核不改變上限。每一站的「主管」＝`DEPT_HEAD@U` 的 regular 持有者（正副皆算），代表人取正主管、沒有才取副主管（職等上限用代表人的），一位都沒有才往上一層（決策點 J 定案）。`resolve_role_holders()` 加 `kinds=('regular',)` 參數，預設維持現行語意。
- 快照 `assignees`（只供顯示與逾時參考人）＝此刻能簽的人：regular ∪ 有效 proxy ∪（無可用持有者時的 standby），由 `role_holding_service.effective_holders()` 產出；FormAdapter `_role_spec_data()` 改呼叫它，刪掉順位迴圈。`_apply_self_target()` 的「本人在快照內」語意不變。
- 行事曆投影 `_delegation_events` 改投影 proxy 列（授權人與代理人各自看得到，ORG_ADMIN 看全部）；`approver_exposure_service._has_covering_delegation()` 改查「請假區間內是否有 proxy 列涵蓋本人所有 regular 角色」。

### 3.7 簽核記錄歸因

`resolve_acting_identity()` 回 `{'via', 'delegator_secure_code', 'acted_as_role_code', 'acted_as_kind'}`：
`via='self'` 且 kind=regular → 三個 NULL；kind=proxy → `delegate_from_*`＝`acting_for`、`acted_as_kind='proxy'`、`acted_as_role_code`＝該角色碼；kind=standby → `acted_as_kind='standby'`、`acted_as_role_code`＝該角色碼、`delegate_from_*` 依 `acting_for` 有無。
顯示文字：「（代 X 簽核）」沿用；「（候補代理 部門主管）」新增（第 2 期定案只印角色名，`fw_approval_records` 沒有單位欄位）；「（以副主管身分）」這種文字**消失**——副主管簽 `DEPT_HEAD` 關卡就是正式持有者，不需要標示（`fc-utils.js:63-66` 三個寫死的 code 刪除，改查角色名）。

### 3.8 `delegations` 表與相關 UI 的去留（決策點 B）

建議**整套退役**，理由：兩套判定是本設計要消滅的東西；FULL 過度授權；沒有 service 層與層界檢查；`has_valid_delegation` 條件是死定義；APPROVAL 型零資料且授權端本來就跳過（決策點 D：直接退役）。

| 現況 | 去處 |
|---|---|
| `/delegations/` 管理員頁 | 退役。管理員在權限中心「帳號配角色」直接建 proxy／standby（表單多「性質、被代理人、效期、限定表單、事由」），或在部門頁候補代理人區塊建 standby |
| `/api/my-delegations`＋個人設定「我的代理授權」 | 過渡期改寫成「我的代理指派」：`given`＝我授出的 proxy 列、`received`＝我持有的 proxy 列；建立＝FULL 語法糖（對本人所有 regular 角色各建一列 proxy，`source_ref='self:<sc>'`）。第 4 期同意流程上線後這條無同意的自助路徑**移除**（Ethan 定案） |
| `Delegation` model、`delegations` 表 | 遷移後軟刪 model；表留一版考古，`org_data_purge_service`／`hostconfig` 的表清單同步 |
| `api/calendar.py:140-163` 的 `delegation_hint` | 導向改成「我的代理指派」或同意流程入口 |
| 手冊 `delegations.md`、`personal_settings.md:72-93`、`calendar.md` 四段、`my_delegation.md` 佔位稿 | 第 3 期改寫成指派語意；`workflows.md:162-177` 順位敘述改成「候補代理人」 |

遷移規則（一次性腳本 `scripts/migrate_proxy_assignments.py --dry-run/--apply`，冪等）：
1. 每筆 `DEPT_PROXY1`／`DEPT_PROXY2`@U 的有效指派 → 一列 `standby` 的 `DEPT_MANAGER`@U（`source_ref='migration:pf251'`），原列軟刪；兩個角色在各企業軟刪，`_create_default_roles` 不再種。
2. 每筆未撤銷、`effective_until >= today` 的 delegation（FULL／SPECIFIC）→ 對授權人當下每一列 regular 指派各建一列 `proxy` 給代理人（同角色@同單位、效期同 delegation、SPECIFIC 的清單進 `allowed_form_templates`、`acting_for`＝授權人、`grant_reason`＝reason）；已到期或撤銷的不遷（記錄留在舊表）。
3. 遷移前後對同一批 WAITING 任務跑判定矩陣，結果必須一字不差（第七節 #8）。

### 3.9 代理指定同意流程（第 4 期，決策 6 的第二階段）

- 表單「代理指定申請」：申請人（授權人）用新的 form.io 元件 `myRolePicker`（列出本人所有 regular 角色@單位，多選）、`userPicker` 選代理人、起迄日、限定表單（可選，沿用 `formPicker`）、事由。元件依 FRONT-12 在 `form_designer.html` 與 `form_center.html` 都掛。
- 流程：Start → FormAdapter（`assignee_type='DYNAMIC'`，值＝表單的代理人欄位；決策「同意／拒絕」）→ `OpProxyGrant` 節點（同意分支）→ End。`OpProxyGrant` 讀表單變數，逐角色建 `proxy` 列（層界檢查、只能是申請人的 regular 角色——申請人送單當下與節點執行當下各驗一次，fail-closed），`source_ref`＝流程實例 `execution_code`；拒絕分支不建列。
- 出廠：與 `backend/app/defaults/api_key_request_defaults.py` 同一套做法，新企業種入表單＋流程＋配對（`create_contract`／`flask module sync`），既有企業用 `scripts/examples/provision_*` 補。個人設定頁「我的代理指派」加「指定代理人」按鈕直接開表單中心填寫頁。
- 節點型別加進 `workflow_node_definitions`，重跑 `scripts/export_node_definitions_seed.py`；handler 註冊在 `node_handlers/factory.py:89-185`；歸「作業」既有分類，不新增分類。

## 四、判定偽碼（完整版）

```python
# build_actor：一次查
assignments = [(a.role_secure_code, a.unit_secure_code or None, a.assignment_kind,
                a.allowed_form_templates, a.acting_for_user_secure_code)
               for a in active_assignments(user, org, today)]
role_types  = {role_sc: role_type}                           # 一次查
ancestors   = {}                                             # 懶查、快取
available   = {}                                             # (R,U) -> bool，懶查、快取（role_holding_service）

def holds(actor, R, U, task):
    for r, u, kind, scope, acting_for in actor.assignments:
        if r != R: continue
        if kind == 'standby' and available(R, u): continue
        if scope is not None and task_form_template(task) not in scope: continue
        if u == U or u is None or U is None: return kind, acting_for
        if kind != 'standby' and role_types[R] != 'POSITION' and U in ancestors[u]: return kind, acting_for
    return None

def _match_identity(data, user_sc, actor):
    if not data.get('assignee_type'): return {'acted_as_kind': None}
    if data['assignee_type'] in ('ROLE', 'DEPARTMENT'):
        R = data['assignee_value']                            # 單一角色；正副主管的彈性靠 3.4 的三個角色，不靠多角色關卡
        hit = holds(actor, R, data.get('assignee_unit_secure_code'), task)
        if hit: return {'acted_as_kind': hit[0], 'acting_for': hit[1], 'acted_as_role_code': code(R) if hit[0] != 'regular' else None}
        if 'assignee_unit_secure_code' in data: return None
    return {'acted_as_kind': None} if user_sc in data.get('assignees', []) else None
```

## 五、UI

- 權限中心「帳號配角色」：指派列顯示性質標籤（正式／代理 X／候補）與效期；指派表單多「性質」select（預設正式）、性質非正式時展開被代理人（proxy 必填）、起迄日（proxy 必填）、限定表單多選、事由。
- 部門頁：「代理人一」「代理人二」兩區合併成「候補代理人」（可多人拖放，寫 standby 的 DEPT_MANAGER@U）；主管、副主管區不變。
- 個人設定「我的代理指派」：我授出的（可撤銷）、我持有的（可放棄）、「指定代理人」按鈕（第 4 期接同意流程；第 3 期先接自助建立）。
- 設計器 FormAdapter：`faAbsenceFallback` 勾選移除；角色下拉自然列出「部門主管／部門正主管／部門副主管」三個；`self_target_action` 不動（「本人在快照內」改由 `effective_holders()` 判）。
- 表單中心／案件中心歷程：加「（候補代理）」；「（以…身分）」改查角色名。
- 行事曆：proxy 列投影，文案「X 代理 Y（角色@單位）」。

## 六、分期（每期一個 codex 任務，順序不可調；每期 spec 貼 `_footer.md`、`security.md`，第 2～4 期另貼 `frontend.md`＋`i18n.md`）

| 期 | 內容 | 檔案 | 測試／驗收 |
|---|---|---|---|
| 1 資料層與判定核心 | 3.1 欄位（model＋dev ALTER＋守恆檢查）；新系統角色 `DEPT_HEAD`（`_create_default_roles` 種入＋既有企業補種＋回填給現有正副主管，遷移腳本第一段）；`DEPT_MANAGER` 顯示名改「部門正主管」；新檔 `role_holding_service.py`（`effective_holders`／`has_available_holder`／`holds`）；`task_authorizer` 刪順位表、`_holds` 依 3.3、`resolve_acting_identity` 多回 `acted_as_kind`；`delegations` 路徑**保留並存**；`resolve_role_holders` 加 `kinds` 參數；`api/organizational_units.py:418-422` 死賦值順手刪 | `models/associations.py`、`services/role_holding_service.py`（新）、`services/unit_resolver.py`、`modules/form_workflow/services/task_authorizer.py` | `test_task_authorizer_role_unit.py` 14 案改語意重寫＋新增（proxy 效期內外、proxy 限定表單、standby 在職／請假／職缺／銷假、standby 不套圈、proxy 套圈跟角色、regular＋proxy 並存）；新檔 `test_role_holding_service.py`；`test_task_authorizer_delegate_from.py` 不動仍綠 |
| 2 節點解析、歸因、顯示 | `_role_spec_data()` 改走 `effective_holders()`；`absence_fallback` 失效、設計器勾選移除；既有 `DEPT_MANAGER`＋`absence_fallback=true` 關卡由遷移腳本改指 `DEPT_HEAD`（graph＋發行快照，決策點 H 定案）；`fw_approval_records.acted_as_kind`（model＋ALTER）；三處寫入點；`fc-utils.js` 顯示；設計器 modal 與 `wf-save.js` 兩條儲存路徑；i18n | `formadapter_handler.py`、`approval_record.py`、`fc_pending.py`／`fc_batch.py`／`instance_routes.py`、`fc-utils.js`、`wf-form-adapter.js`／`wf-node-form-adapter.js`／`wf-save.js`、三個 modal 模板、`en.json` | `test_formadapter_role_unit.py` 5 案改寫＋多角色關卡案；瀏覽器實點（設計器兩條儲存路徑、歷程文字） |
| 3 寫入路徑收斂與遷移 | **決策點 J：`iter_manager_chain()`／`resolve_direct_manager()` 改看 `DEPT_HEAD@U` regular 持有者（第 1 期執行記錄第 3 點挪入）**；`dept_membership_service` 加 `grant_proxy()`／`grant_standby()`／`revoke_grant()`（含層界與「只能授出自己 regular 持有的角色」檢查）；`role_assignment_service.assign_role()` 收 kind 等欄位並輸出效期；`set_unit_leadership` 改走服務（**併 PF-250**）、設正副主管連帶授撤 `DEPT_HEAD@U`（副主管與正主管同樣撤 `DEPT_EMPLOYEE`，決策點 I 定案）；部門頁候補代理人；權限中心 UI；`DEPT_PROXY1/2` 退役（種入函式、常數、`role_map`）；遷移腳本（3.8）；`/delegations/`、`Delegation` model、`my-delegations` 依決策點 B 處置；行事曆投影與 `approver_exposure` 改讀 proxy 列；`task_authorizer` 刪 delegations 路徑；手冊六頁；`route_guard_inventory.py --update` | 見 2.3／2.4 清單 | `test_dept_membership_service.py`、`test_my_delegations_api.py`（改語意）、`test_delegations_prefill.py`（退役或改寫）、`test_calendar_projection.py`；dev 遷移前後矩陣（第七節 #8）；瀏覽器實點部門頁與權限中心 |
| 4 代理指定同意流程 | 3.9：`formio-my-role-picker.js`、`OpProxyGrant` handler＋定義＋seed 匯出、出廠表單／流程／配對、個人設定入口、手冊 `my_delegation.md` 正文 | `backend/app/static/js/formio-my-role-picker.js`、`form_designer.html`／`form_center.html`、`node_handlers/op_proxy_grant_handler.py`（新）、`factory.py`、`defaults/proxy_request_defaults.py`（新）、`scripts/export_node_definitions_seed.py` 重跑 | 新檔 `test_op_proxy_grant.py`；實流程：送單→代理人同意→列出現／拒絕→無列／選了非持有角色→擋；bpserv 部署 |

bpserv 部署清單（`--update` 的 create_all 不補欄位）：

```sql
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS assignment_kind VARCHAR(10) NOT NULL DEFAULT 'regular';
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS acting_for_user_secure_code VARCHAR(32) REFERENCES users(secure_code);
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS allowed_form_templates JSONB;
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS source_ref VARCHAR(100);
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS grant_reason TEXT;
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_role_unit_kind
  ON user_role_assignments (org_secure_code, role_secure_code, unit_secure_code, assignment_kind) WHERE is_deleted = false;
ALTER TABLE fw_approval_records ADD COLUMN IF NOT EXISTS acted_as_kind VARCHAR(10);
```

之後跑 `scripts/migrate_proxy_assignments.py --apply`（六段＋全域收尾一次做完；bpserv 現況：無 PROXY 指派、1 筆已到期 delegation，預期 proxy 0 列遷入、PROXY 角色退役 2 筆、`condition_retired=1`、無 `delegations` 選單所以 `menu_retired=0`）。

## 七、驗收矩陣（主 Claude 執行，憑證 `/opt/tmp/verify/<日期>-role-proxy-<期>.log`）

BELUGA（行銷部門：ethanyu 副主管、aaaa／ssss 現為代理人一二、user 成員、shen 可暫任主管）與 GHTRAVEL（seed 企業）：

| # | 情境 | 期望 |
|---|---|---|
| 1 | shen 為行銷主管，管理員建 proxy：aaaa 代理 shen 的 `DEPT_MANAGER@行銷` 9/10～9/14 | 效期內 aaaa 200、記錄 `acted_as_kind=proxy`＋`delegate_from=shen`；效期外 403 |
| 2 | 同上但 `allowed_form_templates=[A 表單]` | A 表單任務 200、B 表單任務 403（沿用 PF-71 測法） |
| 3 | ssss 為 standby `DEPT_MANAGER@行銷`；主管在職 | ssss 403 |
| 4 | 主管走 `POST /api/calendar/events` 登記整天請假 | ssss 200、`acted_as_kind=standby`；`DELETE` 銷假即時 403 |
| 5 | 主管卸任（職缺） | ssss 200；shen 回任即時 403 |
| 6 | 三角色：關卡 `DEPT_HEAD@行銷` vs `DEPT_MANAGER@行銷` vs `DEPT_DEPUTY@行銷`，shen 正主管、ethanyu 副主管 | HEAD：兩人 200、`acted_as` 全 NULL；MANAGER：shen 200、ethanyu 403；DEPUTY：反之；兩人都請假 → HEAD 的 standby 200、單一人請假 → standby 403 |
| 7 | 既有 `SECURITY_STAFF` 任務 `REYhGxsy_rqYlpVeAQHRxy` 與 PF-247 舊佇列項 | 判定一字不差 |
| 8 | 遷移：dev 的 PROXY 指派與有效 delegations 跑 `--apply` 前後 | 同一批 WAITING 任務五帳號矩陣一致；`--apply` 連跑兩次第二次 0 列 |
| 9 | 越權：user（非持有者）替自己建 proxy；EXTERNAL `gg@gmail.com` 當代理人；aaaa（proxy 持有者）再授出 | 全部 403／400，錯誤碼可辨識 |
| 10 | 直屬主管：GHTRAVEL 30 萬／500 萬對照組，另在燁凱文的角色上插一列 proxy 給別人 | 核決人不變（proxy 不進推導） |
| 11 | 部門頁候補代理人拖放、權限中心建 proxy 與顯示效期 | chrome-devtools 實點，`evaluate_script` 取 innerText |
| 12 | 第 4 期：shen 送「代理指定申請」給 aaaa → aaaa 同意／拒絕；shen 選了自己沒持有的角色 | 同意→proxy 列出現且 `source_ref=execution_code`；拒絕→無列；非持有→表單驗證擋 |

## 八、定案記錄（2026-09-06，全部定案，可派第 1 期）

| # | 問題 | Ethan 定案 |
|---|---|---|
| A | 正副主管怎麼表達 | 三個角色（3.4），關卡指哪個由設計師選；順位特判與設計器勾選移除 |
| B | `delegations` 去留；同意流程上線後的無同意自助路徑 | 整套退役；自助路徑第 4 期上線後**移除** |
| C | standby 也吃限定表單 | 是 |
| D | APPROVAL 限額型 | 直接退役 |
| E | 效期粒度 | 維持日；撤銷＝軟刪除當下生效 |
| F | 管理員直接指派時事由 | 必填 |
| G | 性質中文 | 正式／代理／**候補**（Ethan 改用人類習慣的詞；程式碼仍 `standby`） |
| H | 既有 `DEPT_MANAGER`＋`absence_fallback=true` 關卡 | 遷移腳本自動改指 `DEPT_HEAD` |
| I | 全員角色與副主管 | 全員角色＝既有 `DEPT_MEMBER`（含正副主管，套圈），不新增；副主管與正主管同樣撤 `DEPT_EMPLOYEE` |
| K | 部門頁「候補代理人」寫哪個角色的 standby（2026-09-06 19:1x） | **K2**：`DEPT_HEAD`／`DEPT_MANAGER`／`DEPT_DEPUTY`@U 各寫一列；既有 `DEPT_PROXY1/2` 指派遷移方向相同（一列 PROXY → 三列 standby） |
| J | 直屬主管推導 | 每站主管＝`DEPT_HEAD@U` 持有者，代表人正主管優先、再副主管、都沒有才往上。關卡找不到人的處置全部交給既有設計師選項（PF-226 退回／改派、self_target、簽核逾時），**本設計不再加任何新的自動處置**（Ethan：設計太精細更容易卡住） |

## 九、不在本設計內

會簽決議型式、逾時升級到上層、USER 型指定帳號停用後的處置（PF-246）；社群的團長／副團長／代理人（走 `user_unit_memberships.role_type`，不經角色指派，日後若要候補語意再套本模型）；`permission_condition.has_valid_delegation` 死定義的清理（併 B 退役時順手刪）。

## 十、BBN

待辦 PF-251；定案記錄 BBN #5402 末段；審查模式 #5401。前作 PF-247（#5400）、PF-248、PF-249 已結案，PF-250（leadership 端點繞過服務）併入第 3 期。

## 十一、執行記錄

（每期完成後由執行 session 在此追加「與設計的差異／補充」與憑證路徑；原 session 追加複審結論。）

### 第 1 期（2026-09-06，執行 session；codex 實作、主 Claude 驗收）

憑證：`/opt/tmp/verify/20260906-role-proxy-1.log`（矩陣 #1～#7）、`-baseline.log`（動工前 6 檔 94 passed）、`-related.log`（改後 8 檔 112 passed）、`-full-c1.log`～`-full-c5.log`（全量分七批：1127 passed／2 skipped／0 failed，harness 兩度以記憶體不足砍掉背景 pytest，改前景分批跑，`tests/security/` 子目錄要另列）。
spec：`/opt/tmp/codex/20260906-pf251-phase1.txt`。codex 在跑全量到 45% 時被系統以記憶體不足砍掉（實作與自驗已完成、
未寫回報），其餘驗收由主 Claude 接手。

**與設計的差異／補充**（第 1～5 點在派工前決定並寫進 spec，第 6 點驗收時改）：

1. `UserRoleAssignment.get_active_assignments()`／`get_active_role_secure_codes()` 加 `kinds` 參數，**預設 `('regular','proxy')` 排除 standby**——
   permission_service／page_role_guard／_menu_tree／doc_catalog 全走這支，候補是否生效取決於他人當下可用與否，不能讓選單與權限隨請假翻動。
   設計文件 3.2 沒寫到這支函式，此為補充。
2. 順位常數 `FALLBACK_ROLE_CODES`／`ALWAYS_ALLOWED_FALLBACK_CODES` 從 `task_authorizer` 刪除，但 `formadapter_handler._role_spec_data()` 還在用，
   第 1 期先搬成該檔模組區域常數（行為零變更），第 2 期改走 `effective_holders()` 時整段刪。
3. **決策點 J（主管鏈改看 `DEPT_HEAD`）挪到第 3 期**，與部門頁連帶授撤 `DEPT_HEAD@U` 同期。第六節沒把 J 分到任何一期；若第 1 期就讓
   `iter_manager_chain()` 讀 HEAD，而部門頁設新主管還沒連帶授予 HEAD，會出現「新主管不在核決鏈」的靜默斷層。本期 `iter_manager_chain` 只透過
   `resolve_role_holders(kinds=('regular',))` 預設值變成「只認 regular」。
4. `dept_membership_service` 的 `ensure_role_assignment`／`revoke_role_assignment`／`set_dept_manager`／`reconcile_dept_manager` 查詢加
   `assignment_kind='regular'` 條件（換主管不得把主管的 proxy 列降成部門員工、不得復活 proxy 列）；設計把該檔整個排在第 3 期。
5. `DEPT_DEPUTY` 顯示名同步改「部門副主管」（3.4 表已列，第六節只寫 MANAGER）；`DEPT_HEAD` 屬性單一來源 `organization_service.DEPT_HEAD_ROLE_SPEC`／
   `build_dept_head_role()`，`_create_default_roles()` 與遷移腳本共用；舊→新名稱對照 `DEPT_ROLE_RENAMES`。
6. codex 為了讓「不得修改」的 `test_task_authorizer_delegate_from.py` 兩個整包 dict 斷言仍綠，加了帶自訂 `__eq__` 的 `ActingIdentity(dict)`
   ——生產碼配合測試斷言，驗收時移除，改回純 dict、兩個斷言補 `acted_as_kind: None`。

**實作落點**：`backend/app/models/associations.py`（`AssignmentKind`、五欄位、部分索引、`get_allowed_form_templates()` fail-closed）、
`backend/app/services/role_holding_service.py`（新；`load_actor_assignments`／`has_available_holder`／`effective_holders`／`holds` 純函式）、
`task_authorizer.py`（`_holds` 回 `(kind, acting_for)`、`_match_identity` 依偽碼、`resolve_acting_identity` 多回 `acted_as_kind`、
`delegate_from_fields` 只看 `delegator_secure_code`、delegations 路徑並存）、`unit_resolver.resolve_role_holders(kinds=)`、
`organization_service`（DEPT_HEAD 種入、正副主管改名）、`dept_membership_service.DEPT_POSITION_ROLE_CODES` 加 HEAD、
`scripts/migrate_proxy_assignments.py`（三段：補種角色／改名／回填 HEAD，`--dry-run`／`--apply`／`--org`，冪等）、
`api/organizational_units.py` 死賦值刪除、manifests 三檔。

**dev 資料現況**：7 個未刪除企業各補種 `DEPT_HEAD`（`TEST00` 已軟刪除，刻意跳過，其角色名仍是舊的）；回填 35 列 regular `DEPT_HEAD@U`
（BELUGA 1、BRIGHTCODE 11、GHTRAVEL 13、SHIELDEDGE 10），第二次 `--apply` 全 0。

**驗收**：矩陣 #1～#6 在 app context 對 dev 庫實跑（真實帳號與角色，暫時指派列在交易內、結束 rollback，殘留 0）全 PASS；
矩陣 #7 六個真實 `SECURITY_STAFF` WAITING 任務 × 7 個 BELUGA 帳號經 `GET /api/form-center/pending-tasks/<sc>` 部署前後狀態碼一字不差；
遷移腳本 `--help` exit 0、無參數 exit 1；`check_schema_drift.sh` 硬判定區零差異。

**既定斷層（分期本身造成，dev 上可見、bpserv 四期完成才部署）**：第 1 期起 `task_authorizer` 沒有順位，
`DEPT_PROXY1/2` 持有者（遷移成 standby 在第 3 期）與「`DEPT_MANAGER`＋`absence_fallback=true`」關卡的副主管（關卡改指 `DEPT_HEAD` 在第 2 期）
在此之前失去簽核權；FormAdapter 快照仍含他們（顯示用），但帶 key 的任務不看快照。

### 第 1 期複審（原 session，2026-09-06 17:39）——**通過，可派第 2 期**

親自重跑 7 檔 108 passed（`test_role_holding_service`／`test_task_authorizer_role_unit`／`test_task_authorizer_delegate_from`／`test_formadapter_role_unit`／
`test_dept_membership_service`／`test_hr_lookup_node`／`test_smoke`）、`check_schema_drift.sh` 綠（108 表／1821 欄）；讀完 `task_authorizer`、`associations`、
`role_holding_service`、`dept_membership_service`、`organization_service`、`unit_resolver`、`formadapter_handler` 的 diff 與遷移腳本全文；
憑證矩陣 26 PASS／0 FAIL（含三角色矩陣 #6a～#6i、HEAD standby 正副都請假才生效）、#7 六任務×七帳號部署前後一字不差、全量七批 1127 passed；
dev 庫五欄位＋部分索引在、7 企業 DEPT_HEAD 種入且正副主管改名、HEAD 回填 35 列、`assignment_kind` 現況 270 列全 regular、殘留引用 0。
六點差異全部採納：第 1 點（`get_active_assignments` 排除 standby）是對的，候補不能讓選單隨請假翻動；第 3 點（J 挪第 3 期）避免「新主管不在核決鏈」的斷層，正確；第 6 點移除配合測試的 `ActingIdentity` 是該做的。

**帶進第 2 期 spec 的事**：

1. 刪掉 `formadapter_handler.py` 頂端暫放的 `FALLBACK_ROLE_CODES`／`ALWAYS_ALLOWED_FALLBACK_CODES`，`_role_spec_data()` 改走 `role_holding_service.effective_holders()`
   （第 1 期快照刻意只含 regular，proxy／standby 持有者要等這一步才出現在待簽清單與逾時參考人）
2. 決策點 H 的遷移：graph 與發行快照中 `assignee_value=DEPT_MANAGER` 且 `absence_fallback` 缺 key 或為 true 的 FormAdapter 改指該企業的 `DEPT_HEAD`
   （角色 sc 逐企業查），`absence_fallback=false` 的不動；併入 `scripts/migrate_proxy_assignments.py` 第四段，`--dry-run` 要列出受影響的模板與快照數
3. `role_holding_service.has_available_holder()` 對非 POSITION 角色**不含後代單位持有者**（standby 給「位子」用，成員類角色不該掛 standby）——
   第 2 期在 docstring 明寫，不改邏輯
4. `fw_approval_records.acted_as_kind` 欄位＋三處寫入點；`fc-utils.js:63-66` 三個寫死的 code 刪除；歷程文字依 3.7
5. 設計器 `faAbsenceFallback` 勾選移除、`wf-save.js` 兩條路徑都不再收集；`self_target_action`「本人在快照內」改由 `effective_holders()` 判

**帶進第 3 期的備忘**（不在第 2 期）：`remove_dept_membership()` 只撤 regular 列，成員被移出部門時其 proxy／standby@該單位列留著（刪整個單位時 PF-249 的 purge 會收）；
`dept_membership_service` 連帶授撤 `DEPT_HEAD@U` 時要處理 unit 為 NULL 的全企業正副主管（dev 現況 0 列，bpserv 未查）。



### 第 3a 期（2026-09-06，執行 session；codex＋主 Claude 分工實作、主 Claude 驗收）

憑證：`/opt/tmp/verify/20260906-role-proxy-3a.log`（基準、遷移第五段、J 對照組、部門頁與權限中心瀏覽器、矩陣 #9）、`-related.log`（12 檔 128 passed）、`-full-c1.log`～`-full-c7.log`（全量分七批：1149 passed／2 skipped／0 failed）。
spec：`/opt/tmp/codex/20260906-pf251-phase3a.txt`＋接續 `-resume.txt`。決策點 **K＝K2**（Ethan 19:1x）。

**分工經過**：codex 改完 `role_assignment_service.py`／`dept_membership_service.py` 後撞到用量上限（20:38 重置）。依「配額耗盡例外」由主 Claude 直做後端隔離項
（J、遷移第五段、出廠不種 PROXY、leadership API 走服務＋PF-250、`_department_to_dict`、權限中心 API 與 `role-holders`、守門表），20:39 以 `codex exec resume` 接回原 session 做
部門頁與權限中心前端、`test_role_assignment_kinds`、dept_membership 增案、fixture 清理、i18n（pybabel 五模組、fuzzy 0、obsolete 數不變 1137）、manifests。

**與設計／複審清單的差異（待複審）**：

1. proxy／standby 的授撤放 `role_assignment_service.assign_role(kind=...)`（複審清單寫 `dept_membership_service.grant_proxy()` 等）：代理對象是任何角色不只部門角色，
   權限中心與部門頁共用同一支；授權者檢查 `_assert_can_grant()`（ORG_ADMIN／SYSTEM_ADMIN，或該 R@U 的 regular 持有者且只能授出 proxy／standby；proxy 持有者不得再授出；非管理員不得指派 regular）。
   撤銷改依 `assignment_secure_code`（同一人同角色可有 regular＋proxy 兩列，user＋role 不再唯一）。
2. **J 的實作是三主管角色 regular 持有者的聯集**（`unit_resolver.DEPT_HEAD_ROLE_PRIORITY = MANAGER > DEPUTY > HEAD`），不是只看 `DEPT_HEAD`：資料一致時聯集＝HEAD，
   但能容忍 bpserv 遷移前、或權限中心直接指派 `DEPT_MANAGER` 而沒連帶 HEAD 的列。GHTRAVEL 對照組不變（燁凱文→霄雅慧→晧志遠）；BELUGA 行銷正主管職缺時 user 的直屬主管＝副主管 ethanyu。
3. 部門頁登記候補的事由固定為「部門頁登記候補代理人」（`source_ref=admin:<sc>`）：拖放 UX 不宜跳事由對話框，決策點 F 的「事由必填」落在權限中心表單。
4. `_list_assignable_roles(kind)`：regular 仍只列 GLOBAL／EXTERNAL，proxy／standby 開放 DEPARTMENT／GROUP 範圍（否則權限中心建不了「代理部門正主管」）；
   新增 `GET /api/access/role-holders` 供被代理人下拉；頁面注入 `window.__AC_CONFIG.formTemplates` 給限定表單多選。
5. 跨部門主管／副主管不再借用代理人格顯示（原 `_mergeCrossToProxy()` 刪除），只在跨部門人員區列出。
6. `remove_dept_membership()` 改為軟刪該人在該單位的**所有**指派列（任何角色、任何性質），不再逐一比對 `DEPT_ROLE_CODES`。
7. 權限中心 chip 對「今天不在效期內」的列（含尚未生效的未來 proxy）套 `ac-kind-expired` 灰化，class 名稱偏窄但行為正確。
8. `DEPT_MANAGER` 標籤在權限中心部門欄改顯示「正主管」、`DEPT_HEAD` 只在沒有正副身分時顯示「部門主管」（MANAGER／DEPUTY 優先於 HEAD）。

**實作落點**：`role_assignment_service.py`（assign_role 三性質、`_assert_can_grant`、`_assert_regular_holder`、`_filter_overlapping`、`revoke_assignment(sc)`、`_build_user_roles` 新欄位、`_list_assignable_roles(kind)`）、
`dept_membership_service.py`（`_sync_head`／`set_dept_deputy`／`remove_dept_manager`／`remove_dept_deputy`、`DEPT_POSITION_ROLE_CODES` 三個）、`unit_resolver.py`（J）、
新檔 `services/proxy_role_migration.py`（第五段）、`scripts/migrate_proxy_assignments.py`（第五段掛接、第三段 unit NULL、輸出依 key）、`organization_service.py`（不種 PROXY）、
`api/organizational_units.py`（leadership 全走服務、`STANDBY_ROLE_CODES`、`DELETE /leadership/standby/<user>`）、`platform/data.py`（`_department_manager_code`）、
`api/access_center.py`＋`web/access_center.py`＋`index.html`、`_tab_accounts.html`／`accounts.js`／`access-center.css`、`departments.html`／`departments.js`、
守門表（864 端點）、i18n（.po／.mo／en.json）、manifests（`units.yaml`、`permissions.yaml`）。

**dev 資料現況**：遷移第五段已 `--apply`：BELUGA aaaa／ssss 各三列 standby（HEAD／MANAGER／DEPUTY@行銷，`source_ref=migration:pf251`）、原 PROXY 列軟刪，7 企業 14 個 PROXY 角色軟刪；第二次 `--apply` 全 0。

**驗收**：部門頁（chrome-devtools，synthetic drag event 呼叫 `dropToLeadership`／`dropToEmployee`）候補格列出遷移來的兩人、user 拖入建三列／拖出軟刪、user 拖成正主管得 MANAGER＋HEAD／拖回恢復 EMPLOYEE；
權限中心 chip「候補」標籤、指派 modal 代理流程（角色清單切換、被代理人下拉載入 regular 持有者、`:selected`、建立後 chip 顯示「代理 X 09-10～09-14」、撤銷依 sc）；
矩陣 #9：EXTERNAL 當 proxy 400（層界）、acting_for 非持有者 400、EMPLOYEE 打 assign／standby API 403；J 對照組；12 檔相關測試與全量見 log。

**帶進 3b 的備忘**：`test_task_authorizer_delegate_from.py` 仍用 `delegations`（3b 改寫）；`role_assignment_service._membership_role_labels()` 的 `MembershipRole.PROXY1/2`（跨部門／社群）刻意不動；
`approver_exposure_service` 與行事曆投影仍讀 `delegations`；手冊 `departments.md`／`delegations.md` 等六頁在 3b。

### 第 2 期（2026-09-06，執行 session；codex 實作、主 Claude 驗收）

憑證：`/opt/tmp/verify/20260906-role-proxy-2.log`（遷移第四段核對、重啟、瀏覽器）、`-related.log`（9 檔 119 passed；Claude 改後 `test_formadapter_role_unit.py` 27 passed）、`-full-c1.log`～`-full-c5.log`（全量分七批：1131 passed／2 skipped／0 failed）。
spec：`/opt/tmp/codex/20260906-pf251-phase2.txt`（複審五點全部併入）。codex 回報 `-result.txt`（9 檔 119 passed、drift 綠、遷移三次、executor 重啟前 RUNNING=0）。

**與設計／spec 的差異（驗收時改）**：

1. codex 在 `FormAdapterHandler.validate()` 加了「發現舊 config 有 `absence_fallback` 就 pop 掉並 `flag_modified(queue_item, 'node_config')`」——
   驗證步驟裡對佇列項做寫入，是 spec 之外的清洗；已移除，handler 對該鍵完全不讀不寫，舊佇列項與舊 graph 殘留的鍵不動。三個對應的
   `node_config` 斷言一併拿掉（`result.data` 不含該鍵的斷言保留）。
2. 歷程第二個 span 的條件從 `acted_as_kind !== 'standby' && acted_as_role_code` 收成 `!acted_as_kind && acted_as_role_code`：
   前者會讓 proxy 命中（kind='proxy'、code 有值）多印一句「（以部門正主管身分）」，設計 3.7 說 proxy 只沿用「（代 X 簽核）」。
   現在四態：舊記錄（kind NULL、code 有值）→「（以{角色名}身分）」；standby →「（候補代理 {角色名}）」；proxy → 只有「（代 X 簽核）」；regular → 無標籤。
3. 「（候補代理 部門主管@行銷）」的 `@單位` **沒做**：`fw_approval_records` 沒有單位欄位，只顯示角色名。要單位就得多一欄，留待有需求再加。
4. 角色名由後端查（`approval_history.serialize_approval_history()` 多回 `acted_as_role_name`，同一請求內 code→name 一次查），
   前端不再對 code 表；`fc-utils.getActedAsText()` 刪除。

**實作落點**：`formadapter_handler.py`（`_role_spec_data` 改 `effective_holders(..., today=local_now.date(), local_now=self._local_now())`，
順位常數／`_present_managers`／`_normalized_absence_fallback` 刪除，`result.data` 不再有 `absence_fallback`）、`approval_record.py`（`acted_as_kind`）、
`fc_pending`／`fc_batch`／`instance_routes` 三處寫入、`services/approval_history.py`（新，`fc_pending`／`fc_monitor` 共用）、
`services/manager_gate_migration.py`（新；`migrate_gate_nodes()` 純函式＋`migrate_org_manager_gates()`，graph／cytoscape_config／快照兩處四處都改、`flag_modified`）、
`scripts/migrate_proxy_assignments.py` 第四段、三個 modal 模板＋`security_cases.html`、`wf-form-adapter.js`／`wf-node-form-adapter.js`／`wf-save.js`、
`en.json`、`docs/manual/04_form_workflow/workflows.md`、manifests。

**dev 資料現況**：決策點 H 只命中 BELUGA `b5YR6Qjj6fmyBAakkT1LbB`（`node-Approve`，APPLICANT_UNIT）與其兩個快照（Published fb=true、Suspended 缺 key），
四處都改指 `DEPT_HEAD`、label 改「部門主管@…」、鍵已刪；第三次 `--apply` 四段全 0；全 dev 已無「DEPT_MANAGER＋非 false」關卡。
BBN 卡片說「OD 三條處置流程在此列」不對——那些關卡是 SECURITY_STAFF／SOC_SUPERVISOR。

**驗收**：設計器（admin-ethanyu，chrome-devtools）角色下拉列出部門主管／部門正主管／部門副主管（POSITION）、遷移後選中「部門主管」、
`#faAbsenceFallback`／`#faAbsenceRow` 不存在、`toggleAbsenceRow` 為 undefined；modal「套用並關閉」後節點 config 無 `absence_fallback`，
「儲存」攔到的 PUT body 內該節點亦無、DB revision 4→5 且 graph 仍指 DEPT_HEAD。表單中心 read modal 對舊記錄 Form-260900018 顯示「（以部門副主管身分）」，
同筆資料在 Alpine 上切換 kind 驗四態文字全對。API `form-detail` 每筆帶 `acted_as_kind`／`acted_as_role_name`。

**第 3 期之前的斷層更新**：關卡已改指 `DEPT_HEAD`，副主管恢復可簽；`DEPT_PROXY1/2` 持有者仍要等第 3 期遷成 standby。

### 第 2 期複審（原 session，2026-09-06 19:05）——**通過，可派第 3 期（建議拆 3a／3b）**

親自重跑 8 檔 88 passed（`test_formadapter_role_unit` 27／`test_manager_gate_migration` 2／`test_approval_record_acted_as` 2／`test_task_authorizer_role_unit` 32／
`test_role_holding_service` 5／`test_formadapter_no_assignee` 6／`test_formadapter_timeout` 12／`test_route_guard_table` 2）、守恆檢查綠（108 表／1822 欄）、
`mkdocs build --strict` 過；讀完 handler／model／`approval_history`／`manager_gate_migration`／遷移腳本第四段／三處寫入點／三個 modal＋案件中心／三支設計器 JS／i18n／手冊的 diff；
憑證：遷移第四段四處改指 `DEPT_HEAD` 且第三次 `--apply` 全 0、瀏覽器實點（角色下拉三主管角色、勾選消失、兩條儲存路徑 config 無 `absence_fallback`、revision 5）、歷程四態文字、全量 1131 passed。
dev 庫自查：模板與發行快照都沒有殘留的「`DEPT_MANAGER`＋非 false」關卡、graph 內 `absence_fallback` 鍵 0、**進關卡中的 260 筆 WAITING FormAdapter 沒有一筆 spec 指向 `DEPT_MANAGER`**（遷移前進關卡的任務不會卡在舊規格）。
四點差異全部採納：移除 codex 在 `validate()` 內對佇列項的清洗寫入是對的；proxy 只印「（代 X 簽核）」符合 3.7；`@單位` 不做（3.7 文字據此修正為只印角色名）；角色名後端查是正確的收斂。

**第 3 期範圍太大，建議拆兩期各一個 codex 任務**（PF-247 的教訓：最重的一期不要超過執行 session 三成 context）：

**3a 寫入路徑收斂、部門頁、PROXY 退役**：
1. `dept_membership_service` 新增 `grant_proxy()`／`grant_standby()`／`revoke_grant()`：層界檢查 `ensure_role_layer_compatible()`；只有該角色@單位的 `regular` 持有者本人或 ORG_ADMIN 能授出；proxy 不得再授出；`acting_for` 必填（proxy）；`grant_reason` 管理員路徑必填（F）；`allowed_form_templates` 可選
2. 設正主管＝`DEPT_MANAGER@U`＋`DEPT_HEAD@U`、設副主管＝`DEPT_DEPUTY@U`＋`DEPT_HEAD@U`，卸任連帶撤；副主管與正主管同樣撤 `DEPT_EMPLOYEE`（I）；unit 為 NULL 的全企業正副主管同樣處理（dev 現況 0 列）
3. `set_unit_leadership`／`remove_unit_leadership` 改走服務（**PF-250 併入**），`role_map` 去掉 proxy1／proxy2；`remove_dept_membership()` 連同該成員在該單位的 proxy／standby 列一起撤（人離開部門就不該再代理或候補該部門的位子）
4. 部門頁「代理人一／二」合併成「候補代理人」（多人）；**寫哪個角色的 standby 見決策點 K**
5. 權限中心帳號配角色：列表顯示性質標籤與效期；指派表單多「性質、被代理人、起迄日、限定表單、事由」；`role_assignment_service.assign_role()` 收新欄位並走上面的 grant 函式
6. `DEPT_PROXY1`／`DEPT_PROXY2` 退役：既有指派遷成 standby（遷移腳本第五段，依決策點 K），角色逐企業軟刪，`_create_default_roles`／`DEPT_POSITION_ROLE_CODES`／`role_assignment_service.py:38-40,266` 同步
7. J：`iter_manager_chain()` 每站看 `DEPT_HEAD@U` 的 regular 持有者，代表人正主管優先、再副主管，都沒有才往上；`test_hr_lookup_node` 增案，GHTRAVEL 30 萬／500 萬對照組不變

**3b delegations 退役與遷移**：
1. 遷移腳本第六段：未到期、未撤銷的 delegation → 對授權人每一列 regular 指派各建一列 proxy（SPECIFIC 清單進 `allowed_form_templates`、`acting_for`＝授權人、`grant_reason`＝reason、`source_ref='migration:pf251:<delegation sc>'`），冪等；dev 現況有效 1 筆、bpserv 0 筆
2. `task_authorizer` 刪 delegations 路徑（`_get_delegated_identity_data`、`actor['delegations']`）；`test_task_authorizer_delegate_from.py` 改寫成 proxy 語意
3. `calendar_projection_service._delegation_events` 與 `approver_exposure_service._has_covering_delegation` 改讀 proxy 列；`api/calendar.py` 的 `delegation_hint` 導向改成個人設定「我的代理指派」
4. `/delegations/` 管理頁、`Delegation` model、`permission_condition.has_valid_delegation` 死定義、`org_data_purge_service`／`hostconfig` 表清單、`resource_gateway` 的 `delegation` 資源型登記，全部退役；`route_guard_inventory.py --update`
5. `/api/my-delegations`＋個人設定區塊改寫成「我的代理指派」（given／received／建立＝對本人所有 regular 角色各建 proxy／撤銷）；第 4 期上線後移除建立入口
6. 手冊：`delegations.md` 改寫成「代理與候補」（ORG_ADMIN，在權限中心與部門頁操作）、`personal_settings.md:72-93`、`calendar.md` 四段、`my_delegation.md` 正文、`departments.md` 由佔位稿補正副主管與候補代理人一節；`docs_impact.py` 過

**決策點 K（3a 開工前 Ethan 定）**：部門頁登記的「候補代理人」寫哪個角色的 standby？
K1（建議）只寫 `DEPT_HEAD@U`——對應「正副都休假才輪到候補」；指定「正主管本人」的關卡在正主管請假時沒有候補，由正主管事前授出 proxy 或走設計師的退回／逾時。
K2 三個主管角色各寫一列——正主管一人請假、關卡指定正主管時候補就接手，範圍較寬。
既有 `DEPT_PROXY1/2` 指派的遷移方向跟著 K 走。

### 第 3a 期複審（原 session，2026-09-06 22:29）——**通過，附補丁 3a-1（小，派 3b 前同 session 做）**

親自重跑 10 檔 115 passed（`test_role_assignment_kinds` 6／`test_unit_leadership_api` 3／`test_access_center_assign_kinds` 2／`test_proxy_role_migration` 2／
`test_dept_membership_service` 13／`test_hr_lookup_node` 23／`test_task_authorizer_role_unit` 32／`test_formadapter_role_unit` 27／`test_route_guard_table` 2／`test_role_layer_guard` 5）、
守恆檢查綠、守門表一致；讀完 `role_assignment_service`／`dept_membership_service`／`unit_resolver`／`organization_service`／`proxy_role_migration`／遷移腳本／
`organizational_units` API／`platform/data.py`／權限中心 API 與 web 的 diff，前端摘讀 API 呼叫與性質分支；憑證：遷移第五段 dry-run→apply→第二次全 0、J 對照組三站一字不差、
部門頁與權限中心瀏覽器實點、矩陣 #9 越權四項、全量 1149 passed。dev 自查：standby 6 列／regular 268 列、每一列 regular 正副主管都有對應 `DEPT_HEAD@U`（缺漏 0）、
副主管仍持 `DEPT_EMPLOYEE` 0 列、PROXY 指派 active 0、PROXY 角色只剩已軟刪企業 TEST00 的兩筆（刻意跳過，正確）；殘留的 `proxy1／proxy2` 字串全在社群頁（membership role_type）與 `client_ip.py` 註解，不在範圍。
八點差異全部採納：授撤放 `role_assignment_service.assign_role(kind=)` 比部門服務更對（代理對象不限部門角色）；J 取三角色聯集能容忍未連帶 HEAD 的舊資料，接受；`remove_dept_membership` 撤該人在該單位所有列符合 3a 清單第 3 條。

**補丁 3a-1（三件，一次派工）**：

1. **平台 API 檔內新增的直接查詢搬進服務層**（TENANT-02：新寫的平台 API 一律走 gateway 或不在 API 檔內查）：`api/organizational_units.py` 的 `_load_active_user`／`_regular_holder`／`_standby_rows`／`_standby_users`
   與 `remove_unit_standby` 內的 `User.query`，`api/access_center.py::role_holders` 內的 `User.query`——搬成 `dept_membership_service.list_unit_leadership()`／`remove_unit_standby()` 與
   `role_assignment_service.list_regular_holders()`，API 只呼叫。semgrep `beakplatform-direct-model-query-in-api` 對平台 API 的命中已從基準 91 降到 79（leadership 重寫淨減），
   補丁後 `access_center.py` 應為 0、`organizational_units.py` 不得高於補丁前扣掉這 6 處
2. **`_assert_can_grant()` 非管理員路徑的單位比對要精確**：現在對 `unit_sc=None` 呼叫 `resolve_role_holders(unit=None)` 會把「任一單位的 regular 持有者」都算成可授出全企業範圍的代理。
   改成：`unit_sc` 有值→操作者須持 (R, unit_sc) 或 (R, None) 的 regular；`unit_sc` 為 None→操作者須持 (R, None) 的 regular。今天 API 層全是 `@admin_required` 所以碰不到，
   **第 4 期 `OpProxyGrant` 以申請人身分呼叫時就會碰到**，一定要在那之前修；`test_role_assignment_kinds` 補兩案
3. **部門頁登記候補的「已是候補」判定不要比對訊息字串**：`set_unit_leadership()` 用 `'候補' in str(exc) and '已是' in str(exc)` 判斷重複，訊息經 gettext 翻譯，英文介面下會變成整組 400 並 rollback
   （例：權限中心先建了某人 `DEPT_HEAD@U` 的候補，再到部門頁拖同一人）。改成呼叫前用既有的 `_standby_rows(user_sc)` 算出缺哪幾列只補那幾列，或讓 `assign_role` 拋帶 `code` 的例外由呼叫端辨識；`test_unit_leadership_api` 補「三列已有一列」案

補丁不必重跑全量：跑 `test_role_assignment_kinds`＋`test_unit_leadership_api`＋`test_access_center_assign_kinds`＋`test_dept_membership_service`＋semgrep 兩檔計數即可，憑證接 3a log 尾。

**3b 照第 2 期複審的清單派**，另補三條：`role_assignment_service._membership_role_labels()` 的 `MembershipRole.PROXY1/2` 是社群跨部門成員的顯示標籤，不在範圍、不要動；
手冊 `departments.md` 補正副主管與候補代理人一節時要寫「候補對三個主管角色都生效」（K2）；bpserv 部署清單加第五段遷移（DemoSOC 無 PROXY 指派，預期 0 列、角色退役 2 筆）。

### 補丁 3a-1（2026-09-06 23:0x，執行 session，主 Claude 直做）

三件都做：(1) `api/organizational_units.py` 的 `_load_active_user`／`_regular_holder`／`_standby_rows`／`_standby_users`／`remove_unit_standby` 內的 `User.query`，以及 `api/access_center.py::role_holders` 的 `User.query`，
搬成 `dept_membership_service.list_unit_leadership()`／`regular_position_holder()`／`standby_rows()`／`standby_role_codes_held()`／`remove_unit_standby()`／`user_brief()` 與 `role_assignment_service.list_regular_holders()`，API 只呼叫；
semgrep `beakplatform-direct-model-query-in-api`：`access_center.py` 1→0、`organizational_units.py` 6→5（剩下 191／217／739／799／909 是既有的目標帳號查詢樣式，不在補丁清單）。
(2) `_assert_can_grant()` 非管理員路徑改 `_operator_holds_regular()`：`unit_sc` 有值須持 (R, unit) 或 (R, NULL) 的 regular，`unit_sc` 為 None 只認 (R, NULL)；`test_role_assignment_kinds` 補兩案（單位持有者不能授出全企業或別的單位、全企業持有者可授出任一單位）。
(3) `set_unit_leadership()` 的 standby 分支先 `standby_role_codes_held()` 算缺哪幾列只補那幾列，刪掉訊息字串比對；`test_unit_leadership_api` 補「權限中心先建 HEAD 候補、部門頁再拖同一人 → 200 補齊三列、先建列不動」案。
四檔 27 passed（`test_role_assignment_kinds` 8／`test_unit_leadership_api` 4／`test_access_center_assign_kinds` 2／`test_dept_membership_service` 13）；憑證接 `/opt/tmp/verify/20260906-role-proxy-3a.log` 尾。


### 第 3b 期（2026-09-06 23:1x 派工、2026-09-07 00:0x～ 主 Claude 接手驗收；codex 實作、主 Claude 驗收）

憑證：`/opt/tmp/verify/20260906-role-proxy-3b.log`（遷移 help／無參數／第二次 apply 全 0、quick-login API、矩陣 #8、瀏覽器四段、行事曆四身分受眾、越權 404、清理）、
`-baseline.log`（派工前 12 檔 148 passed）、`-related-a.log`（改寫與新增 8 檔 109 passed）、`-related-b.log`（不得改語意 9 檔＋重構後 API 測試，10 檔 98 passed）、`-drift.log`（綠：108 表 1822 欄）、`-full-c1.log`～`-full-c7.log`（全量七批、乾淨測試庫：**1147 passed／2 skipped／0 failed**）。
spec：`/opt/tmp/codex/20260906-pf251-phase3b.txt`（724 行）。派工前 HEAD `7c143d9f`。

**經過**：codex 一次做完全部實作（含 dev 遷移 `--apply`、pybabel、守門表 `--update`、`git add -A`），在最終重跑相關測試時被 harness 以記憶體不足砍掉（stderr 最後一則「剩 HR lookup、route guard、permission defaults 與 manager gate」，未寫回報檔）。
主 Claude 接手：讀完全部後端 diff 與前端三檔、靜態檢查、測試分兩批、dev 實跑、瀏覽器實點。**沒有退回**，只改一處（下列第 9 點）。

**spec 層決定（Ethan／原 session 複審）**：

1. `delegations` 表與 `Delegation` model 檔**都留**（守恆檢查以 model 為權威），只改 docstring 標退役；`org_data_purge_service`／`hostconfig`／seed 腳本的表名清單因此不動。全平台其餘讀寫全部移除，殘留 grep 0
2. 新服務 `backend/app/services/proxy_assignment_service.py` 是「我的代理指派」＋請假涵蓋判定＋遷移來源列的唯一實作；`IDENTITY_ROLE_CODES=(SYSTEM_ADMIN, ORG_ADMIN, EMPLOYEE, EXTERNAL_USERS)` 三處共用——
   **FULL 語法糖與遷移排除層界身分角色**：`get_active_assignments()` 的 HOLDING 含 proxy，代理 ORG_ADMIN 角色會把管理員選單與權限整包給代理人，舊 FULL 只影響簽核，不能擴權；EMPLOYEE 雙方都有、建了是雜訊
3. `role_assignment_service.assign_role()`／`revoke_assignment()` 加 `commit=True` keyword（False 時 flush），供自助建立多列 all-or-nothing；`_filter_overlapping` 改公開名 `filter_overlapping` 給服務共用
4. 自助建立**事由必填**（400 `reason_required`；`assign_role` 對 proxy 本來就要求）
5. 行事曆請假提示：管理員與員工**同走**個人設定「我的代理指派」（`?proxy=new&…#my-proxy-assignments`）；企業行事曆面板上管理員替**別人**建代理的連結（`delegationLinkFor`）刪除——權限中心沒有帳號 deep link 可帶入
6. 命名：`/api/my-delegations` → `/api/my-proxy-assignments`（多一支 `GET /my-roles` 給 modal 預覽「將代理以下角色」）；回應 key `delegation_hint` → `proxy_hint`、`already_delegated` → `already_covered`；投影 `source_type='proxy'`／`event_type='PROXY'`、同一 (代理人, 被代理人, 效期) 合併一筆、`note` 列出角色@單位、ORG_ADMIN 的 `link` 指 `/access/`
7. 遷移第六段**不動 `delegations` 列**，冪等靠 `source_ref='migration:pf251:<delegation sc>'`；另加全域收尾 `retire_delegation_globals()` 軟刪 `menu_items.code='delegations'`（出廠 `menu_defaults.py` 本來沒種，只有 dev 那筆）與 `permission_conditions.code='DELEGATED'`；`resource_gateway` 兩處 `'Delegation'`、`ResourceType.DELEGATION`、`permission_service` 的 DELEGATE 分支一併移除
8. codex 的兩個小取捨，接受：`delegation_migrated` 只計「有建或復活列」的筆（skipped 不計），第二次 `--apply` 全 0 更乾淨；`_proxy_events` 多一次查詢只為對 `valid_from`／`valid_until` 為 NULL 的 proxy 列印 warning
9. 主 Claude 改一處：API 檔把「僅企業成員」檢查內聯了五次，收成 `_deny_non_member()`（舊檔本來就有這支 helper）

**待 Ethan 決策（矩陣 #8 發現，不阻擋本期）**：人對人 FULL 代理曾涵蓋 **USER／DYNAMIC 指名到被代理人本人**的任務，角色代理不涵蓋。
dev 實例：GHTRAVEL 差旅費流程的 `hr_approver`（OpHrLookup 解析成人）DYNAMIC 任務 `dNkJ35nmaK-bwsmyvWG2Ap` 指名燁凱文；燁凱文→翎柏瑞的 FULL（09-08～09-12）遷成三列 proxy 後，
09-08 起翎柏瑞對 `DEPT_MANAGER@團體旅遊部` 的 ROLE 任務放行（`acted_as_kind='proxy'`），對那筆 DYNAMIC 任務**不放行**（舊路徑會放行）。今天（09-07，delegation PENDING、proxy 未生效）兩邊判定一字不差、全 None。
選項：A 維持（代理的是角色不是人，指名到人的關卡本來就不該由代理接手；HR lookup 指名人是流程設計層的事）；B `_match_identity` 對非 ROLE 規格也認「proxy 列的 `acting_for` 在快照內」（回復人對人語意，但代理任一角色就能簽被代理人所有指名任務，比舊 FULL 還寬）；
C OpHrLookup 多輸出核決人的角色@單位讓關卡改用 ROLE 規格。**建議 A，並在第 4 期同意流程的手冊寫清楚**；要 C 另開待辦。

**驗收**（憑證 `20260906-role-proxy-3b.log`）：遷移 `--help` exit 0／無參數 exit 1／第二次 `--apply` 七企業全 0、全域 0；dev 現況 GHTRAVEL 翎柏瑞三列 proxy（HEAD／MANAGER／MEMBER@團體旅遊部、09-08～09-12、`migration:pf251:81b66f04…`）、`menu_items.delegations` 與 `permission_conditions.DELEGATED` 皆 `is_deleted=t`；
quick-login：翎柏瑞 `GET /api/my-proxy-assignments` received 3 列 PENDING、ethanyu `/my-roles` 列 4 角色無 EMPLOYEE、`/delegations/`／`/delegations/create`／`/api/my-delegations`／`/candidates` 全 404、EXTERNAL gg@gmail.com 403；
chrome-devtools（ethanyu）：區塊標題「我的代理指派」、[指定代理人] modal `display=flex`、候選 5 人 `:selected`、角色預覽 4 項無 EMPLOYEE、事由空白 → 「請填寫指派事由」、建立 → 「已建立 4 筆代理指派」given 4 列待生效（DB `source_ref=self:<sc>`）、
行事曆 `POST /api/calendar/events` LEAVE 回 `proxy_hint.create_url=/beakplatform/personal-settings?proxy=new&effective_from=2026-09-23&…#my-proxy-assignments`、開該 URL modal 自動開啟且日期／事由預填、[撤銷] 4→3；（user）我代理的 3 列、[放棄] 3→2；
行事曆 API 四身分：ethanyu／user 各看到 1 筆「user 代理 ethanyu」（note 四個角色）、aaaa 0 筆無遮罩、ORG_ADMIN 1 筆 `link=/beakplatform/access/`；越權：user／aaaa 撤銷 GHTRAVEL 的 proxy 列皆 404；測試列與請假事件已清理（self: 列 0）。
靜態：node 兩支 ok、import ok、殘留 grep 0、semgrep `my_proxy_assignments.py` 0（`calendar.py` 5 筆與 HEAD 相同，是既有 `page_keys_required` 未被規則認得）、`mkdocs build --strict` 過、`docs_impact --verify-covers` 244 條全對、`.po` untranslated 0／fuzzy 0、en.json +9。

**dev 資料現況**：`delegations` 4 筆原樣保留（2 REVOKED、1 SPECIFIC 已到期、1 FULL PENDING 已遷）；proxy 列 3（遷移）＋0（自助，驗收後撤銷）；standby 6 列不變。

**帶進第 4 期**：自助建立入口（[指定代理人] 與 `POST /api/my-proxy-assignments`）第 4 期同意流程上線後移除（決策點 B 後半）；`OpProxyGrant` 以申請人身分呼叫 `assign_role` 前確認 3a-1 的 `_operator_holds_regular` 仍在；上面的待決點若選 C 要一併設計。
bpserv 部署：`--update` 後跑 `scripts/migrate_proxy_assignments.py --apply`（六段＋全域收尾一次做完；DemoSOC 那筆 soc1→admin-soc1 已於 09-05 到期，預期 0 列；bpserv 沒有 `delegations` 選單，`menu_retired` 預期 0、`condition_retired` 1）。

### 第 3b 期複審（原 session，2026-09-07 01:00 起，中途 session 中斷，2026-09-08 00:00 完成）——**通過，可派第 4 期**

親自重跑 14 檔 143 passed（`test_delegation_migration` 6／`test_my_proxy_assignments_api` 12／`test_task_authorizer_delegate_from` 10／`test_task_authorizer_role_unit` 32／
`test_calendar_events_api` 29／`test_calendar_projection` 13／`test_role_assignment_kinds` 8／`test_unit_leadership_api` 4／`test_access_center_assign_kinds` 2／`test_route_guard_table` 2／
`test_permission_defaults` 5／`test_role_layer_guard` 5／`test_dept_membership_service` 13／`test_proxy_role_migration` 2）、守恆檢查綠（108 表／1822 欄）、`mkdocs --strict` 過、
`docs_impact --verify-covers` 50 份文件 244 條全對、守門表 859／859 一致、semgrep 平台 API 79→**77**（`my_proxy_assignments.py` 0）、`.po` fuzzy 0；
讀完 `task_authorizer`／`proxy_assignment_service`／`delegation_migration`／`my_proxy_assignments`／`calendar` 三處／`approver_exposure`／`resource_gateway`／`permission_service`／
`permission_condition`／`permission`／遷移腳本／`role_assignment_service` 的 diff 與前端摘讀、手冊五頁與 CLAUDE.md／CALENDAR_SPEC 第九節。
憑證：遷移第二次 `--apply` 七企業＋全域全 0、退役路由四條 404、EXTERNAL 403、矩陣 #8 今昔對照、瀏覽器四段（建立／預填／撤銷／放棄）、行事曆四身分受眾、越權兩筆 404、清理後殘留 0、全量 1147 passed。
dev 自查：`delegations` 4 筆原樣（未被遷移動過）、proxy 3 列皆帶 `migration:pf251:<sc>`、`menu_items.delegations` 與 `permission_conditions.DELEGATED` 皆 `is_deleted=t`、
指派現況 regular 268／standby 6／proxy 3；殘留 `Delegation` 引用只剩 `models/__init__.py` 的 export 與三支腳本的**表名字串**清單（符合「表與 model 留考古」的決定）。

**額外自驗（憑證沒有、CLAUDE.md 點名必查）**：`delegations.md` 的 `nav_menu` 由 `delegations`（已軟刪）改綁 `access_center_org`，這條綁錯會「整頁誰都看不到且不報錯」。
實測 ORG_ADMIN 的 `/help/` 列出「代理與候補」「部門設定」、單頁 200；EMPLOYEE 對這兩頁 404（`audience: ORG_ADMIN` 的預期）、其 `/help/` 列出「設定代理人」且單頁 200、ORG_ADMIN 對該頁 404。三頁可見性正確。

九點 spec 層決定全部採納。三點值得記：`IDENTITY_ROLE_CODES` 排除四個層界身分角色是本期最重要的一個判斷——`get_active_assignments()` 的 HOLDING 含 proxy，
代理 ORG_ADMIN 會把管理員選單與權限整包給代理人，比舊 FULL 的簽核語意寬得多；`has_covering_proxy()` 從「有任一涵蓋的 delegation」收緊成「每一個可代理角色都要有涵蓋的 proxy」，
方向安全（提示更容易出現而非更少）；行事曆 `link` 指 `/access/` 而非帳號 deep link 是現況限制，不是遺漏。

**待 Ethan 決策（矩陣 #8，不阻擋本期、第 4 期前要答）**：舊人對人 FULL 代理會涵蓋「USER／DYNAMIC 指名到被代理人本人」的任務，角色代理不涵蓋。
dev 實例已在第 3b 期記錄（GHTRAVEL `hr_approver` 指名燁凱文的 DYNAMIC 任務，翎柏瑞 09-08 起對 ROLE 任務放行、對該 DYNAMIC 任務不放行）。
**複審同意執行 session 的建議 A（維持現狀）**：代理的是角色不是人；OpHrLookup 把核決人解析成「人」再指名，是流程設計層把角色壓成人的結果，不該由授權層回補。
選 A 要在第 4 期手冊寫明「代理只涵蓋以角色指定的簽核關卡」。若 Ethan 要 C（OpHrLookup 多輸出角色@單位讓關卡改用 ROLE 規格）另開待辦，不併第 4 期。

**第 4 期 spec 要帶的事**：

1. 3.9 全部（`myRolePicker` 元件依 FRONT-12 兩個模板都掛、`OpProxyGrant` handler＋nodedef＋`export_node_definitions_seed.py` 重跑、出廠表單／流程／配對、個人設定入口）
2. **`OpProxyGrant` 以申請人身分呼叫 `assign_role` 時會走到 3a-1 的 `_operator_holds_regular()`**（管理員路徑之外的第一個真實使用者），送單當下與節點執行當下各驗一次、fail-closed
3. 決策點 B 後半：同意流程上線後移除自助建立入口（`[指定代理人]` 按鈕與 `POST /api/my-proxy-assignments`），`GET`／`revoke` 保留
4. 手冊 `my_delegation.md` 改寫成同意流程；`delegations.md` 的「成員能不能自己設」一段跟著改
5. 憑證回到 expect／got 的 PASS／FAIL 逐項格式（本期改成敘述式，內容具體可覆核但不易一眼看出漏項）

**小備忘（不必單獨修）**：`test_task_authorizer_delegate_from.py` 檔名沿用舊語意（內容已全改 proxy，`delegate_from_fields` 函式仍在，尚算有據），第 4 期若動到該檔可順手更名；
`_proxy_events()` 每次行事曆請求會多一次「無效期 proxy 列」的全企業查詢，因 `assign_role` 強制 proxy 有起迄日，實務上恆 0 列，可留。

**四期完成後才部署 bpserv**：`--update` → 兩句 ALTER（第 1／2 期欄位）→ `scripts/migrate_proxy_assignments.py --apply`（六段＋全域收尾一次做完）。

### 第 4 期（2026-09-08，執行 session；codex 實作、主 Claude 驗收）

憑證：`/opt/tmp/verify/20260908-role-proxy-4.log`（CLI 預演／apply／冪等）、`-related-a.log`（首輪，2 failed）、`-related-a2.log`（修正後 4 檔 47 passed）、
`-full-c1.log`～`-full-c7.log`（全量七批、乾淨測試庫：**1153 passed／2 skipped／0 failed**）。spec：`/opt/tmp/codex/20260908-pf251-phase4.txt`（868 行）。派工前 HEAD `3201a0e5`。
矩陣 #8 依複審定案 **A（維持現狀）**，只寫進手冊、授權層未動。

**經過**：codex 一次做完全部實作（含節點定義種入、seed 重匯出、i18n、守門表），在最終驗證階段被 harness 以記憶體不足砍掉（與 3b 同一個現象），主 Claude 接手驗證與驗收。**沒有退回**，改了四處（下列）。

**主 Claude 改的四處**：

1. **`assignee_value` 從 `'PROXY_REQUEST_delegate'` 改成 `'delegate'`（spec 寫錯，會整條流程靜默失效）**：
   `OpFieldRead` 的變數前綴取的是 `form_instance.form_template_secure_code`（`fieldread_handler.py:38` 的 `form_code = form_instance.form_template_secure_code or form_instance.form_code`），
   **不是表單模板的 code**，所以帶前綴的名字是 `<模板 sc>_delegate`、每個企業都不一樣，出廠 graph 寫不出來。用不帶前綴的簡單名，作用域是單一流程實例、不會撞名。
   沒改的話 DYNAMIC 解析為空 → 走 PF-226 的 `no_assignee` → 每一張申請單都被退回申請人，**單元測試抓不到**（不跑整條流程）
2. **`myRolePicker` 的值加 `role_name`／`unit_name` 名稱快照**：元件的選項來源是 `/api/my-proxy-assignments/my-roles`（**登入者本人**的角色），簽核者開單時載入的是自己的角色清單，
   永遠解析不出申請人的角色名 → 只能顯示 secure_code，等於要對方盲簽。快照存在值裡，顯示優先用它、退回 `_findOption`、再退回 sc；後端 handler 只讀兩個 secure_code 欄位（`_normalize_roles` 忽略其他 key）
3. **`myRolePicker` 覆寫 `setValue` 在唯讀時重繪**：Form.io 先 attach 再由 submission 設值，元件沒有重繪就停在 attach 當下的空狀態，實測簽核者看到「已選 0 個角色」而 `dataValue` 其實有兩筆。
   **重繪限定唯讀模式**——可編輯時每次勾選都重建整個清單會讓捲動位置與焦點跳掉（實測連續勾選第二項會失敗）
4. **組填寫頁網址收進 `proxy_assignment_service.proxy_request_fill_url()` 一處**：codex 原本讓 service 回 `'/forms/center?fill=<sc>'` 路徑字串，`main.py` 與 `calendar.py` 各自 `split('?', 1)[1]` 再重組。
   改成 service 直接回完整網址；**保留 `current_app.view_functions` 的 endpoint 存在性檢查**——模組 blueprint 只註冊在進程內第一個 app，測試 app 沒有它時 `url_for` 會拋 `BuildError`
   （我一度移除這個檢查，`test_calendar_events_api` 兩案立刻紅，是移除造成的）

**與 spec 的差異（codex 的判斷，接受）**：`_normalize_forms` 已回 None 或非空 list，handler 仍寫 `forms or None`（冗餘但無害）；`describe_org_state` 不回 `org_admin_role_secure_code`（本流程簽核者是 DYNAMIC，不綁角色，spec 已說明）。

**驗收（端到端實跑，chrome-devtools）**：
BELUGA 跑 CLI 種入（表單 `xvIG_i5kAFZxtD5S4vhMQu` / 流程 `PRhkpB1_lIdkoWJFGHvAYb` / 配對 `eYN7CnmiCyeNNQrXc8RU4w` / 發行 `R81cDdRMDWdDzOFSnJN5fQ`，第二次 apply 全部 exists）→
個人設定 [指定代理人] 是 `<a href="/beakplatform/forms/center?fill=R81cDdRMDWdDzOFSnJN5fQ">`、建立 modal 已移除 →
開該網址填寫 modal 自動開啟、六個欄位渲染（`userPicker`／`myRolePicker`／`datetime`×2／`formPicker`／`textarea`）、代理人欄位**沒有**帶入本人（`defaultToCurrentUser: False` 生效）、
myRolePicker 列出 ethanyu 四個角色且**不含 EMPLOYEE 身分角色** →
送出後 `form_data.proxy_roles` 是物件陣列含名稱快照、`node-FieldRead-delegate` SUCCESS、`node-FormAdapter-consent` WAITING 且 **`assignees=["<user sc>"]`（DYNAMIC 解析成功）** →
代理人開簽核看到「流程設計師、部門主管@行銷部門，已選 2 個角色」→ [同意代理] → 全節點 SUCCESS、**建立 2 列 proxy**（`flow:PROC-20260908-0002`、`acting_for=ethanyu`、效期 11-02～11-06、事由正確）、
表單「處理結果」寫回「user 已同意代理，共建立 2 筆代理指派：流程設計師、部門主管@行銷部門，效期 2026-11-02 至 2026-11-06。」→
另一張單 [拒絕] → 走 `node-FieldWrite-rejected` → End，**proxy 列沒有增加**、結果欄位寫「代理人未同意這次委任，沒有建立任何代理指派。」→
流程設計器（ethanyu／FLOW_DESIGNER）節點面板出現「代理指定授出」。
靜態：node 四支 ok、import ok、en.json 合法、殘留 grep 0、semgrep 兩檔 0、守恆檢查綠（108 表 1822 欄）、守門表 857 一致、`mkdocs --strict` 過、`docs_impact --verify-covers` 246 條全對、`.po` untranslated 0／fuzzy 0。
**驗收建立的 2 列 proxy 已軟刪清理**；兩張申請單實例（Form-260900019 拒絕／260900020 同意）刻意保留當樣本；BELUGA 的出廠鏈路保留。

**帶進複審／後續的備忘**：

- **`myRolePicker` 的名稱快照是顯示用，不是判定用**。`OpProxyGrant` 只信 secure_code，執行當下再用 `proxyable_regular_assignments()` fail-closed 重驗一次（實測撤角色後整筆 error 且一列都沒建）
- **`/api/my-proxy-assignments/my-roles` 現在有兩個消費者**（元件與個人設定），它回的是**登入者本人**的角色。若日後要讓管理員代填申請單，需要像 formPicker 的 `beneficiaryKey` 那樣加對象參數並重新評估授權
- 個人設定的 `[指定代理人]` 在企業還沒種出廠表單時**不渲染**（fail-closed），改顯示「目前沒有可用的代理指定申請單，請聯絡企業管理員。」
- 既有企業補種走 `venv/bin/python scripts/examples/provision_proxy_request_flow.py --org <org> --apply`（冪等）；新企業由 `create_organization`／`init_system_organization`／`seed_system_org_defaults` 三個觸發點自動種
- bpserv 部署：`--update` → 第 1／2 期的兩句 ALTER → `scripts/migrate_proxy_assignments.py --apply` → **本期另加** `provision_proxy_request_flow.py --org <DemoSOC> --apply`（`--update` 不會回填既有企業的出廠表單）

### 第 4 期複審（原 session，2026-09-08 02:47）——**通過。PF-251 四期全部完成、全部複審通過。**

親自重跑 8 檔 95 passed（`test_op_proxy_grant` 7／`test_proxy_request_defaults` 2／`test_my_proxy_assignments_api` 8／`test_calendar_events_api` 30／
`test_task_authorizer_role_unit` 32／`test_role_assignment_kinds` 8／`test_route_guard_table` 2／`test_delegation_migration` 6）、守恆檢查綠（108 表／1822 欄）、
`mkdocs --strict` 過、`docs_impact --verify-covers` 246 條全對、守門表 857／857 一致、semgrep 平台 API 77（新檔 `my_proxy_assignments`／`proxy_request_defaults` 皆 0，與 3b 持平沒有新技術債）；
讀完 `op_proxy_grant_handler` 全文、`proxy_assignment_service`／`my_proxy_assignments`／`calendar`／`main.py` 的 diff、`myRolePicker` 與 `userPicker` 關鍵段、
出廠 graph 的節點與 `assignee_value`、三個觸發點、節點註冊與 seed、`?fill=` 深連結、FRONT-12 兩個模板都掛。
dev 自查：`workflow_node_definitions` 有 `OpProxyGrant`（active、非受限）、BELUGA 出廠表單在、兩張驗收單 COMPLETED（樣本保留）、
proxy 列只剩 3 列遷移來的（驗收建立的 2 列確已清理）、自助建立入口殘留 grep 0。

**四處驗收改動全部採納，其中兩處是必修**：

1. `assignee_value` 改 `'delegate'`：`OpFieldRead` 的變數前綴取的是 `form_instance.form_template_secure_code` 而非表單 code，出廠 graph 寫不出帶前綴的名字。
   spec 的原值會讓 DYNAMIC 解析為空 → 每張申請單都走 PF-226 退回，而**單元測試不跑整條流程、抓不到**。這是本期最重要的一次驗收攔截
2. `myRolePicker` 的名稱快照：元件選項來源是**登入者本人**的角色，簽核者開單時解析不出申請人的角色名，只會看到 secure_code，等於要對方盲簽。
   快照只進顯示層、handler 只信 secure_code（`_normalize_roles` 忽略其他 key），分層正確
3. `setValue` 唯讀重繪且**限定唯讀**：可編輯時重繪會讓焦點與捲動跳掉，這個限定條件是對的
4. 網址收斂到 `proxy_request_fill_url()` 一處，且保留 `current_app.view_functions` 的存在性檢查——模組 blueprint 只註冊在進程內第一個 app，移除該檢查會讓 `test_calendar_events_api` 兩案紅（執行 session 實測過）

**授權面**：`OpProxyGrant` 是雙重防線——handler 進場先用 `proxyable_regular_assignments()` 對執行當下的 regular 持有狀態 fail-closed 重驗（送單到同意之間角色被撤就整筆 error、一列都不建），
`assign_role(operator=applicant_user)` 再走一次 3a-1 的 `_operator_holds_regular()`。這正是 3b 複審點名要注意的地方，處理正確。
all-or-nothing（`commit=False` 逐列、最後一次 commit、任何例外 rollback）與 RLS context 設定都在。

**提交衛生問題（不影響功能，但要處理）**：canary 廢除（2026-09-07，與 PF-251 無關）這件工作被切成三段：

| 段 | 位置 |
|---|---|
| 刪 `scripts/cron/od_canary_check.py`、`sec-vm-bootstrap/host-cron/secstack-canary` | **`916a5528`（本 session 的第 3b 期複審 commit）** |
| `sec-vm-bootstrap/` 五個檔案的文件更新 | `23121f77`（第 4 期） |
| `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`、`SEC_STACK_ARCHITECTURE.md`、`manifests/mod-open-defense.yaml` | **尚未提交，留在工作區** |

第一段是**原 session 自己的疏失**：`git add <單一檔案> && git commit` 不帶路徑時，會把工作區當時**已 staged** 的內容一併提交，別人 staged 的兩個刪除因此進了複審 commit。
第二段是執行 session 的 `git add -A`。結果是「程式與設定的刪除已提交、說明文件還在工作區」——現在 push 的話，遠端會看到 canary 腳本被刪卻沒有任何說明。
執行 session 回報的「工作區乾淨」與實況不符（三個 M）。

**處置建議（交 Ethan 決定，本 session 不擅自提交他人工作）**：不改寫歷史（21 個 commit 未 push，rebase 的風險大於收益），
把工作區那三個文件檔案提交成一個獨立的 canary 廢除 commit，讓那件事在文件上完整，再一起 push。
**流程教訓**：`git commit` 前先 `git status --short` 確認 staged 內容；只想提交特定檔案時用 `git commit <path>` 而不是 `git add <path> && git commit`。

## 十二、全案狀態（2026-09-08）

**dev 端四期全部完成並複審通過。** 判定核心、節點解析、寫入路徑、代理與候補、`DEPT_PROXY` 與 `delegations` 退役、同意流程都已落地。

**剩下的收尾（依序）**：

1. 工作區三個 canary 文件的處置（見上）
2. `push both`
3. bpserv 部署：`--update` → 兩句 ALTER（第 1 期五欄位＋索引、第 2 期 `fw_approval_records.acted_as_kind`，SQL 在第六節）→
   `scripts/migrate_proxy_assignments.py --apply`（六段＋全域收尾一次做完）→
   **`venv/bin/python scripts/examples/provision_proxy_request_flow.py --org DEMOSOC --apply`**（`--update` 不回填既有企業的出廠表單）
4. bpserv 驗收：DemoSOC 無部門角色，重點是既有 ROLE 任務判定不變、個人設定 [指定代理人] 連結可開、跑一張申請單走完同意流程
