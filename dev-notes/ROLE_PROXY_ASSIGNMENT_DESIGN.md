# 角色級代理指派設計（PF-251）

> 撰寫：2026-09-06 主 Claude，依 Ethan 同日定案的六點（BBN #5402 末段）。前作 `ROLE_UNIT_APPROVAL_DESIGN.md`（PF-247）
> 把簽核者做成 (角色, 單位)，本文件把「代理」與「備位」也收進同一張表、同一條判定，退役兩個 PROXY 角色與人對人代理授權。
> 執行方式沿用 PF-247：撰寫本文件的 session 留守審查，執行 session 依第六節逐期派 codex 並驗收，每期完成後在第十一節寫差異清單。

## 一、一句話

代理人不是另一種角色，是**在一段期間內持有被代理的那個角色@單位**。`user_role_assignments` 每一列多一個「指派性質」：
`regular`（正式持有）、`proxy`（有效期內視同持有，記被代理人）、`standby`（備位，只在該角色@單位沒有任何可用的正式或代理持有者時生效）。
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
| `acting_for_user_secure_code` | VARCHAR(32) NULL，FK users | 被代理的人；`proxy` 必填，`standby` 可空（備位的是位子不是人），`regular` 一律 NULL |
| `allowed_form_templates` | JSONB NULL | 表單模板 sc 陣列；NULL＝不限。`regular` 一律 NULL |
| `source_ref` | VARCHAR(100) NULL | 來源：流程實例 `execution_code`、`admin:<user sc>`、`migration:<腳本>`、`self:<user sc>` |
| `grant_reason` | TEXT NULL | 事由（自 `delegations.reason` 遷入） |

既有欄位沿用：`valid_from`／`valid_until`（Date）是 proxy 的效期，`assigned_by` 記操作者，`is_deleted`＝撤銷。
**不加 (user, role, unit) 唯一約束**：同一個人可以同時是某角色@單位的 `regular` 與另一列 `proxy`（副主管同時被指定代理主管），性質不同就是兩列。
索引加 `(org_secure_code, role_secure_code, unit_secure_code, assignment_kind) WHERE is_deleted = false`。

`fw_approval_records` 加 `acted_as_kind VARCHAR(10) NULL`（regular／proxy／standby）；`acted_as_role_code` 保留，改記「實際命中的角色碼」（副主管以 `DEPT_DEPUTY` 命中多角色關卡時記它）。

### 3.2 三種性質的語意

| kind | 何時算持有 (R, U) | 誰能建 | 撤銷 |
|---|---|---|---|
| `regular` | `is_valid_on(today)` | 既有路徑不變 | 既有路徑不變 |
| `proxy` | `is_valid_on(today)`，與 regular 完全等價；另受 `allowed_form_templates` 限制 | R@U 的 `regular` 持有者本人（同意流程或自助）、ORG_ADMIN 直接指派 | 被代理人、代理人本人（放棄）、ORG_ADMIN；軟刪除 |
| `standby` | `is_valid_on(today)` **且** R@U 此刻沒有任何「可用」的 regular／proxy 持有者 | ORG_ADMIN（部門頁備位代理人區塊）、R@U 的 regular 持有者 | 同上 |

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

### 3.4 副主管的共同簽核（決策點 A）

現況「副主管永遠可簽」靠順位表的 `ALWAYS_ALLOWED`。順位表刪除後有兩種表達：

- **A1 多角色關卡（建議）**：FormAdapter config 加 `assignee_roles: [role_sc, ...]`（`assignee_value` 保留為第一個，舊 graph 相容），同一個單位範圍下持有任一角色即可簽；設計器選「部門主管」時預設連帶勾「部門副主管」。通用：也能表達「採購核決人 或 財務主管」。`acted_as_role_code` 記實際命中的角色碼。
- A2 勾選語法糖：保留 `absence_fallback` checkbox，handler 對 `DEPT_MANAGER` 自動把 `DEPT_DEPUTY` 加進目標——仍是主管特判，只是搬到 handler。

### 3.5 限定表單維度（Ethan 定案：保留）

`allowed_form_templates` 存在指派列上，判定沿用 `task_authorizer._delegation_scope_allows_task()` 的比對與 `_task_form_template_secure_code()` 快取，改成對每一列指派做。
`regular` 列一律 NULL；UI 上只有 proxy／standby 的建立表單提供「限定表單」多選（沿用 `web/delegations.py` 的 `allowed_form_templates[]` 與 PF-71 的模板清單來源）。
決策點 C：standby 是否也吃這個維度（建議吃，規則通用、不多寫程式）。

### 3.6 直屬主管推導、快照、投影不受代理影響的部分

- `unit_resolver.iter_manager_chain()`／`resolve_direct_manager()` **只認 `regular`**：核決鏈找的是「誰的職等決定上限」，代理人簽核不改變上限；主管職缺（無 regular）照舊往上。`resolve_role_holders()` 加 `kinds=('regular',)` 參數，預設維持現行語意。
- 快照 `assignees`（只供顯示與逾時參考人）＝此刻能簽的人：regular ∪ 有效 proxy ∪（無可用持有者時的 standby），由 `role_holding_service.effective_holders()` 產出；FormAdapter `_role_spec_data()` 改呼叫它，刪掉順位迴圈。`_apply_self_target()` 的「本人在快照內」語意不變。
- 行事曆投影 `_delegation_events` 改投影 proxy 列（授權人與代理人各自看得到，ORG_ADMIN 看全部）；`approver_exposure_service._has_covering_delegation()` 改查「請假區間內是否有 proxy 列涵蓋本人所有 regular 角色」。

### 3.7 簽核記錄歸因

`resolve_acting_identity()` 回 `{'via', 'delegator_secure_code', 'acted_as_role_code', 'acted_as_kind'}`：
`via='self'` 且 kind=regular → 三個 NULL；kind=proxy → `delegate_from_*`＝`acting_for`、`acted_as_kind='proxy'`；kind=standby → `acted_as_kind='standby'`、`delegate_from_*` 依 `acting_for` 有無；多角色關卡命中非主要角色 → `acted_as_role_code`＝命中角色碼。
顯示文字：「（代 X 簽核）」沿用；「（備位代理）」新增；「（以副主管身分）」改由 `acted_as_role_code` 對角色名，不再寫死三個 code（`fc-utils.js:63-66`）。

### 3.8 `delegations` 表與相關 UI 的去留（決策點 B）

建議**整套退役**，理由：兩套判定是本設計要消滅的東西；FULL 過度授權；沒有 service 層與層界檢查；`has_valid_delegation` 條件是死定義；APPROVAL 型零資料且授權端本來就跳過（決策點 D：直接退役）。

| 現況 | 去處 |
|---|---|
| `/delegations/` 管理員頁 | 退役。管理員在權限中心「帳號配角色」直接建 proxy／standby（表單多「性質、被代理人、效期、限定表單、事由」），或在部門頁備位代理人區塊建 standby |
| `/api/my-delegations`＋個人設定「我的代理授權」 | 過渡期改寫成「我的代理指派」：`given`＝我授出的 proxy 列、`received`＝我持有的 proxy 列；建立＝FULL 語法糖（對本人所有 regular 角色各建一列 proxy，`source_ref='self:<sc>'`）。同意流程（第 4 期）上線後這條「無同意的自助」保留為緊急路徑或移除——Ethan 定 |
| `Delegation` model、`delegations` 表 | 遷移後軟刪 model；表留一版考古，`org_data_purge_service`／`hostconfig` 的表清單同步 |
| `api/calendar.py:140-163` 的 `delegation_hint` | 導向改成「我的代理指派」或同意流程入口 |
| 手冊 `delegations.md`、`personal_settings.md:72-93`、`calendar.md` 四段、`my_delegation.md` 佔位稿 | 第 3 期改寫成指派語意；`workflows.md:162-177` 順位敘述改成「備位代理人」 |

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
        for R in target_roles(data):                          # A1：assignee_roles；A2：assignee_value
            hit = holds(actor, R, data.get('assignee_unit_secure_code'), task)
            if hit: return {'acted_as_kind': hit[0], 'acting_for': hit[1], 'acted_as_role_code': code(R) if R != primary else None}
        if 'assignee_unit_secure_code' in data: return None
    return {'acted_as_kind': None} if user_sc in data.get('assignees', []) else None
```

## 五、UI

- 權限中心「帳號配角色」：指派列顯示性質標籤（正式／代理 X／備位）與效期；指派表單多「性質」select（預設正式）、性質非正式時展開被代理人（proxy 必填）、起迄日（proxy 必填）、限定表單多選、事由。
- 部門頁：「代理人一」「代理人二」兩區合併成「備位代理人」（可多人拖放，寫 standby 的 DEPT_MANAGER@U）；主管、副主管區不變。
- 個人設定「我的代理指派」：我授出的（可撤銷）、我持有的（可放棄）、「指定代理人」按鈕（第 4 期接同意流程；第 3 期先接自助建立）。
- 設計器 FormAdapter：`faAbsenceFallback` 依決策點 A 改成角色多選（A1）或保留勾選改文案（A2）；`self_target_action` 不動。
- 表單中心／案件中心歷程：加「（備位代理）」；「（以…身分）」改查角色名。
- 行事曆：proxy 列投影，文案「X 代理 Y（角色@單位）」。

## 六、分期（每期一個 codex 任務，順序不可調；每期 spec 貼 `_footer.md`、`security.md`，第 2～4 期另貼 `frontend.md`＋`i18n.md`）

| 期 | 內容 | 檔案 | 測試／驗收 |
|---|---|---|---|
| 1 資料層與判定核心 | 3.1 欄位（model＋dev ALTER＋守恆檢查）；新檔 `role_holding_service.py`（`effective_holders`／`has_available_holder`／`holds`）；`task_authorizer` 刪順位表、`_holds` 依 3.3、`resolve_acting_identity` 多回 `acted_as_kind`；`delegations` 路徑**保留並存**；`resolve_role_holders` 加 `kinds` 參數；`api/organizational_units.py:418-422` 死賦值順手刪 | `models/associations.py`、`services/role_holding_service.py`（新）、`services/unit_resolver.py`、`modules/form_workflow/services/task_authorizer.py` | `test_task_authorizer_role_unit.py` 14 案改語意重寫＋新增（proxy 效期內外、proxy 限定表單、standby 在職／請假／職缺／銷假、standby 不套圈、proxy 套圈跟角色、regular＋proxy 並存）；新檔 `test_role_holding_service.py`；`test_task_authorizer_delegate_from.py` 不動仍綠 |
| 2 節點解析、歸因、顯示 | `_role_spec_data()` 改走 `effective_holders()`；多角色關卡（A1）或勾選語意（A2）；`fw_approval_records.acted_as_kind`（model＋ALTER）；三處寫入點；`fc-utils.js` 顯示；設計器 modal 與 `wf-save.js` 兩條儲存路徑；i18n | `formadapter_handler.py`、`approval_record.py`、`fc_pending.py`／`fc_batch.py`／`instance_routes.py`、`fc-utils.js`、`wf-form-adapter.js`／`wf-node-form-adapter.js`／`wf-save.js`、三個 modal 模板、`en.json` | `test_formadapter_role_unit.py` 5 案改寫＋多角色關卡案；瀏覽器實點（設計器兩條儲存路徑、歷程文字） |
| 3 寫入路徑收斂與遷移 | `dept_membership_service` 加 `grant_proxy()`／`grant_standby()`／`revoke_grant()`（含層界與「只能授出自己 regular 持有的角色」檢查）；`role_assignment_service.assign_role()` 收 kind 等欄位並輸出效期；`set_unit_leadership` 改走服務（**併 PF-250**）；部門頁備位代理人；權限中心 UI；`DEPT_PROXY1/2` 退役（種入函式、常數、`role_map`）；遷移腳本（3.8）；`/delegations/`、`Delegation` model、`my-delegations` 依決策點 B 處置；行事曆投影與 `approver_exposure` 改讀 proxy 列；`task_authorizer` 刪 delegations 路徑；手冊六頁；`route_guard_inventory.py --update` | 見 2.3／2.4 清單 | `test_dept_membership_service.py`、`test_my_delegations_api.py`（改語意）、`test_delegations_prefill.py`（退役或改寫）、`test_calendar_projection.py`；dev 遷移前後矩陣（第七節 #8）；瀏覽器實點部門頁與權限中心 |
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

之後跑 `scripts/migrate_proxy_assignments.py --apply`（bpserv 現況：無 PROXY 指派、1 筆已到期 delegation，預期 0 列遷入）。

## 七、驗收矩陣（主 Claude 執行，憑證 `/opt/tmp/verify/<日期>-role-proxy-<期>.log`）

BELUGA（行銷部門：ethanyu 副主管、aaaa／ssss 現為代理人一二、user 成員、shen 可暫任主管）與 GHTRAVEL（seed 企業）：

| # | 情境 | 期望 |
|---|---|---|
| 1 | shen 為行銷主管，管理員建 proxy：aaaa 代理 shen 的 `DEPT_MANAGER@行銷` 9/10～9/14 | 效期內 aaaa 200、記錄 `acted_as_kind=proxy`＋`delegate_from=shen`；效期外 403 |
| 2 | 同上但 `allowed_form_templates=[A 表單]` | A 表單任務 200、B 表單任務 403（沿用 PF-71 測法） |
| 3 | ssss 為 standby `DEPT_MANAGER@行銷`；主管在職 | ssss 403 |
| 4 | 主管走 `POST /api/calendar/events` 登記整天請假 | ssss 200、`acted_as_kind=standby`；`DELETE` 銷假即時 403 |
| 5 | 主管卸任（職缺） | ssss 200；shen 回任即時 403 |
| 6 | 副主管 ethanyu（決策點 A） | 主管在職與職缺皆 200，`acted_as_role_code=DEPT_DEPUTY` |
| 7 | 既有 `SECURITY_STAFF` 任務 `REYhGxsy_rqYlpVeAQHRxy` 與 PF-247 舊佇列項 | 判定一字不差 |
| 8 | 遷移：dev 的 PROXY 指派與有效 delegations 跑 `--apply` 前後 | 同一批 WAITING 任務五帳號矩陣一致；`--apply` 連跑兩次第二次 0 列 |
| 9 | 越權：user（非持有者）替自己建 proxy；EXTERNAL `gg@gmail.com` 當代理人；aaaa（proxy 持有者）再授出 | 全部 403／400，錯誤碼可辨識 |
| 10 | 直屬主管：GHTRAVEL 30 萬／500 萬對照組，另在燁凱文的角色上插一列 proxy 給別人 | 核決人不變（proxy 不進推導） |
| 11 | 部門頁備位代理人拖放、權限中心建 proxy 與顯示效期 | chrome-devtools 實點，`evaluate_script` 取 innerText |
| 12 | 第 4 期：shen 送「代理指定申請」給 aaaa → aaaa 同意／拒絕；shen 選了自己沒持有的角色 | 同意→proxy 列出現且 `source_ref=execution_code`；拒絕→無列；非持有→表單驗證擋 |

## 八、待 Ethan 定案（審本檔時回答；未回答的項目第 1 期不開工）

1. **A 副主管共同簽核的表達**：A1 多角色關卡（建議）／A2 勾選語法糖。
2. **B `delegations` 整套退役**（3.8 表）；以及同意流程上線後「無同意的自助 proxy」留作緊急路徑還是移除。
3. **C standby 也吃 `allowed_form_templates`**（建議吃）。
4. **D APPROVAL 限額型直接退役**（零資料、授權端本來就跳過）。
5. **E proxy 效期粒度維持日**（Date）；時段級的缺席交給 standby 處理，不做到時分。
6. **F 管理員直接指派 proxy／standby 時 `grant_reason` 是否必填**（建議必填，補上「無當事人同意」的稽核缺口）。
7. **G 命名**：節點 `OpProxyGrant`（顯示「建立代理指派」）、元件 `myRolePicker`、指派性質中文「正式／代理／備位」。

## 九、不在本設計內

會簽決議型式、逾時升級到上層、USER 型指定帳號停用後的處置（PF-246）；社群的團長／副團長／代理人（走 `user_unit_memberships.role_type`，不經角色指派，日後若要備位語意再套本模型）；`permission_condition.has_valid_delegation` 死定義的清理（併 B 退役時順手刪）。

## 十、BBN

待辦 PF-251；定案記錄 BBN #5402 末段；審查模式 #5401。前作 PF-247（#5400）、PF-248、PF-249 已結案，PF-250（leadership 端點繞過服務）併入第 3 期。

## 十一、執行記錄

（每期完成後由執行 session 在此追加「與設計的差異／補充」與憑證路徑；原 session 追加複審結論。）
