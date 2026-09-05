# 簽核者＝角色@單位：「部門也是一種角色」的落地設計（2026-09-05 草案，待 Ethan 審）

> 狀態：**八個決策點已定案；第 1～3、5 期複審通過，第 4 期（直屬主管來源統一＋任職卡指標退役＋決策點 8）2026-09-05 由新 session 完成並通過執行 session 驗收，待原 session 複審（見第十一節末段）**。
> 起因：PF-226 收尾時 Ethan 指出歷來 session 忽略了「部門也是一種角色」這個核心概念；
> 本文件盤點現況、定義目標模型、給出遷移與分期。BBN 待辦見本檔末尾。
> 撰寫者是 PF-226／PF-71 的 session（保留中，負責審結果）；執行者是新 session，**照本檔做，不要自行詮釋**。

## 一、一句話

簽核關卡指定的不是「人」也不是「一個扁平的角色」，而是 **(角色, 單位範圍)**：
「軟體部主管」＝ `DEPT_MANAGER@軟體部`、「申請人的部門主管」＝ `DEPT_MANAGER@申請人所屬單位`、
「資訊群成員」＝ `DEPT_MEMBER@資訊群`（含子單位成員，套圈）。授權判定**執行時**比對行為人當下持有的
(角色, 單位) 集合；人員異動、職缺、補人都不需要動流程。

## 二、現況盤點（2026-09-05 dev 庫實查）

### 2.1 資料層：已經是「部門即角色」

| 東西 | 事實 | 位置 |
|---|---|---|
| 角色分類 | `roles.scope_type` ∈ GLOBAL／DEPARTMENT／GROUP／EXTERNAL；`role_type` ∈ ROLE／POSITION；`exclusive_group` 有 per-unit 互斥（DEPT_POSITION、GROUP_POSITION） | `backend/app/models/role.py:16-65` |
| 單位型角色指派 | `user_role_assignments.unit_secure_code`（NULL＝全企業）；`valid_from/valid_until`；`is_valid_on(today)` | `backend/app/models/associations.py:78-125` |
| 部門系統角色 | `DEPT_MEMBER`（基底，所有部門人員）、`DEPT_EMPLOYEE`／`DEPT_MANAGER`（互斥）、`DEPT_DEPUTY`、`DEPT_PROXY1`、`DEPT_PROXY2`；加入部門時 `_ensure_dept_membership()` 同時寫 `user_unit_memberships(SOLID)` ＋ 指派 DEPT_MEMBER＋DEPT_EMPLOYEE@unit；設主管走 `set_unit_leadership()` 換 DEPT_MANAGER@unit | `backend/app/api/organizational_units.py:83-130, 1165-1185` |
| 社群系統角色 | `GROUP_MEMBER`／`GROUP_MANAGER`／`GROUP_EMPLOYEE`，同樣 per-unit | `backend/app/services/organization_service.py:347-380` |
| 單位樹 | `organizational_units.parent_secure_code`、`unit_type` ∈ DEPARTMENT／GROUP、`get_ancestors()`／`get_descendants()` 已實作 | `backend/app/models/organizational_unit.py:53, 125-150` |
| 名詞定版 | 「單位職務（POSITION）就是角色的一種，簽核找位子，位子在單位裡」；`EmployeePosition` 是任職卡、「不參與權限判斷」 | `dev-notes/ROLE_TAXONOMY.md:12-35` |

beluga 行銷部門的實際資料（Ethan 2026-09-05 設定）：ethanyu＝DEPT_DEPUTY@行銷部門、aaaa＝DEPT_PROXY1、ssss＝DEPT_PROXY2、
user＝DEPT_MEMBER＋DEPT_EMPLOYEE。單位樹：資訊群 → 軟體部／網管部／資安部／伺服器部／資訊部。

### 2.2 消費層（form_workflow）：把它壓扁了

| 消費點 | 現況 | 偏差 |
|---|---|---|
| `task_authorizer.get_actor_role_codes()` | `{a.role_secure_code}`，**丟掉 `unit_secure_code`** | 「部門主管」變成全企業一個角色；任何部門的主管都能簽 |
| `task_authorizer._identity_matches()` | ROLE：`assignee_value in role_codes`；DEPARTMENT：快照 only；其餘看 `assignees` 清單 | 無單位、無套圈 |
| `FormAdapter._resolve_role_users()` | 全企業持該角色的人 | 同上 |
| `FormAdapter._resolve_department_users()` | 讀 `users.primary_unit_secure_code` 快照，不看指派也不看成員表 | PF-245；多數帳號沒 primary_unit，幾乎派不到人 |
| `OpHrLookup` 的 `hr_direct_manager` | `EmployeePosition.direct_manager_secure_code`（任職卡上的**人對人指標**） | 與 `DEPT_MANAGER@unit` 是兩套真相；範例企業只建任職卡，部門角色零成員 |
| 副主管／代理人(一)(二) | **不參與任何簽核判定**（授權只看 `delegations`） | Ethan 設的行銷部門副主管與代理人對簽核無效 |
| 設計器角色清單 `GET /api/workflows/data/roles` | 列 `roles` 表全部 | 「部門主管」只有一筆，寫不出軟體部主管／申請人部門主管／上層 |
| 單位階層 | `get_ancestors()` 在 `modules/form_workflow` 零使用（只有部門下拉用到 `OrganizationalUnit`） | 無套圈 |

### 2.3 資料普查（會腐爛，動工前重跑）

```sql
SELECT o.code,
  (SELECT count(*) FROM user_role_assignments a WHERE a.org_secure_code=o.secure_code AND a.unit_secure_code IS NOT NULL AND a.is_deleted=false) AS unit_role_assign,
  (SELECT count(*) FROM user_unit_memberships m WHERE m.org_secure_code=o.secure_code AND m.is_deleted=false) AS memberships,
  (SELECT count(*) FROM employee_positions p WHERE p.org_secure_code=o.secure_code AND p.is_deleted=false) AS positions,
  (SELECT count(*) FROM users u WHERE u.org_secure_code=o.secure_code AND u.is_deleted=false AND u.primary_unit_secure_code IS NOT NULL) AS users_with_primary
FROM organizations o WHERE o.is_deleted=false ORDER BY 1;
```

2026-09-05：BELUGA 5／5／0／4，LION 4／7／0／2，GHTRAVEL／BRIGHTCODE／SHIELDEDGE 各 0／1／22／20。
**兩種企業各走一套**：手動建的企業有部門角色沒任職卡，seed 建的企業有任職卡沒部門角色。

既有流程模板的簽核者型別（`fw_workflow_templates.graph`，未刪除）：ROLE 17 個節點（全是**全域**角色：
ORG_ADMIN／SECURITY_STAFF／SOC_SUPERVISOR／EMPLOYEE）、DYNAMIC 2、DEPARTMENT 0、USER 0。
→ 相容風險低：只要「沒有單位範圍的 ROLE」行為不變，既有模板與發行快照全部照舊。

## 三、目標模型

### 3.1 簽核者規格（node config 與佇列項 `result.data`）

`assignee_type='ROLE'` 保留，**新增三個 key**：

| key | 值 | 語意 |
|---|---|---|
| `unit_scope` | `GLOBAL`（預設，缺 key 亦同）／`UNIT`／`APPLICANT_UNIT`／`APPLICANT_ANCESTOR` | 單位範圍 |
| `unit_secure_code` | 單位 sc | 只在 `UNIT` 用 |
| `unit_levels_up` | 整數 ≥ 1，預設 1 | 只在 `APPLICANT_ANCESTOR` 用：申請人單位往上 N 層（超過根就取根） |
| `absence_fallback` | bool，預設 true | 角色是 POSITION 型（主管）時，主管缺席改看副主管／代理人（見 3.4） |

進入關卡時 handler 把範圍**解析成具體單位**寫進 `result.data`：`assignee_unit_secure_code`（解析結果，GLOBAL 為 null）、
`assignee_unit_name`、`assignee_role_code`、`assignee_role_type`（ROLE／POSITION）、`assignees`（當下持有者快照，**只供顯示與逾時參考人**，不做授權）。
授權一律看規格＋執行時身分，不看 `assignees`。

`assignee_type='DEPARTMENT'` **退役為別名**：執行期視同 `ROLE=DEPT_MEMBER, unit_scope=UNIT, unit_secure_code=<原值>`；
設計器不再提供，舊 graph 照跑。這就是 PF-245 的解法（快照語意消失，改為即時比對）。

### 3.2 申請人所屬單位怎麼取

順序：`user_unit_memberships`（`membership_type='SOLID'`、未刪、日期有效）→ 若多筆取 `users.primary_unit_secure_code` 對得上的那筆 →
仍多筆取 `start_date` 最早 → 都沒有則看 `EmployeePosition`（PRIMARY、有效）的 `unit_secure_code` → 都沒有＝解析失敗。
解析失敗走 PF-226 的 `no_assignee_action`（退回或改派全域角色）。唯一實作放 `backend/app/services/unit_resolver.py`（新檔），
OpHrLookup 第四期改用同一支。

### 3.3 行為人身分展開（`build_actor`）

```
role_units = {(role_sc, unit_sc)}  # 來自 user_role_assignments，unit_sc 可為 None（全企業）
```

**套圈規則**：判定「行為人是否持有 (R, U)」時：

1. 直接持有 (R, U) → 是
2. 持有 (R, None)（全企業指派）→ 對任何 U 都是（全域是超集）
3. R 的 `role_type != 'POSITION'` 且持有 (R, D)，D 是 U 的**後代**單位 → 是（軟體部成員也是資訊群成員）
4. R 是 POSITION（主管、副主管、代理人）→ **不套圈**（軟體部主管不是資訊群主管）

祖先／後代關係一次查出快取在 actor 內（`unit_ancestors: {unit_sc: [祖先 sc...]}`），同一請求內不重查。
代理授權（`delegations`）不變：授權人的身分用同一套展開。

### 3.4 主管缺席順位（POSITION 型且 `absence_fallback=true`）

目標 `DEPT_MANAGER@U` 時，判定集合依序：`DEPT_MANAGER@U` → `DEPT_DEPUTY@U` → `DEPT_PROXY1@U` → `DEPT_PROXY2@U`。

- **副主管永遠可簽**（副主管是常設的共同簽核者，不是備援）
- **代理人(一)(二)只在主管缺席時可簽**。缺席＝該單位沒有任何有效、啟用、未刪除的人持有 `DEPT_MANAGER@U`（職缺）；
  第五期再加「主管當日請假」（`schedule_adjustments` LEAVE，PF-229 已有資料）
- 社群同構：`GROUP_MANAGER` → `GROUP_EMPLOYEE`？**不對**——社群沒有副主管與代理人角色，只有團長；缺席順位對社群只做「無團長→不放行」，不自創角色
- 簽核記錄照實記簽的人（`approver_*`），另在 `fw_approval_records` 加 `acted_as_role_code`（記「以副主管身分」），
  `delegate_from_*` 維持代理授權專用

### 3.5 直屬主管一律由部門推導，任職卡指標退役（OpHrLookup，第四期；2026-09-05 依決策點 4 改寫）

> 原文「任職卡 `direct_manager_secure_code` 有值＝明示覆寫」已作廢。Ethan 定案：**一律由部門推導、欄位退役**。

**推導規則**（唯一實作放 `backend/app/services/unit_resolver.py`，新增 `resolve_direct_manager(user_sc, org_sc, today)`）：

1. 申請人單位 U ＝ `resolve_user_unit()`（3.2）；解析不到 → 空字串、`hr_direct_manager_found='false'`
2. U 的主管 ＝ 持有 `DEPT_MANAGER@U`（**單位指派優先**）且有效（`is_valid_on(today)`）、帳號啟用未刪的人；單位指派沒有人時才退回全企業持有 `DEPT_MANAGER`（unit NULL）者。同類內多人取 `assigned_at` 最早（互斥群組本就該擋住多人）。（2026-09-05 第 4 期複審改寫：原文「全企業持有者也算」會讓全企業指派壓過每一層的單位主管）
3. 申請人**本人就是** U 的主管，或 U **沒有**主管（職缺）→ 往上一層（`get_unit_ancestor_codes()` 順序）重複第 2 條；到根仍無 → 空字串、`found='false'`
4. 副主管、代理人(一)(二)**不進**推導：那是簽核授權的缺席順位（第 1 期已在 `task_authorizer`），核決鏈只認主管
5. 新增輸出：`hr_direct_manager_unit`／`hr_direct_manager_unit_name`（主管所屬單位）、`hr_approver_unit`／`hr_approver_unit_name`

**核決鏈**（`HR_LOOKUP_NODE_SPEC.md` 規則 3～7 改寫）：從第 2～3 條找到的主管開始，沿祖先單位的主管往上；每站職等仍看該主管的有效任職卡
（`EmployeePosition` 保留為職等／職稱／部門的來源，只退役 `direct_manager_secure_code`）。**主管沒有有效任職卡時視為該站上限 0、繼續往上**（不再中止），
因為部門推導不保證每位主管都有任職卡。迴圈與 20 站上限維持。

**欄位退役清單**（第四期 spec 逐項列）：

| 位置 | 處置 |
|---|---|
| `modules/form_workflow/services/node_handlers/hr_lookup_handler.py:195, 292, 320` | 改呼叫 `resolve_direct_manager()`；不再讀指標 |
| `backend/app/models/employee_position.py` | 移除 `direct_manager_secure_code` 欄位、`get_manager_chain()`（若無其他呼叫者）；**`dotted_line_manager_secure_code`（虛線主管）不動** |
| `backend/app/web/positions.py:91-131, 197-228` 與 `templates/pages/positions/create.html`／`edit.html` | 移除直屬主管下拉與表單欄位 |
| `backend/app/web/hostconfig.py:344` | 清理對照表移除該列 |
| `scripts/seed_test_companies.py:844, 898, 927` | 不再寫指標；`is_unit_head=True` 者改指派 `DEPT_MANAGER@unit`＋`user_unit_memberships(SOLID)`，其他人 `DEPT_MEMBER`＋`DEPT_EMPLOYEE@unit`（走 `organizational_units.py` 既有的 `_ensure_dept_membership` 邏輯，不要另寫一份）；提供 `--sync-dept-roles` 冪等補種給既有三家範例企業 |
| dev 庫 | 一次性 `ALTER TABLE employee_positions DROP COLUMN direct_manager_secure_code;`，`bash scripts/check_schema_drift.sh` 過 |
| `docs/manual/03_org_setup/`（任職卡頁）與 `04_form_workflow/hr_lookup_node.md` | 移除「直屬主管」欄位說明；改寫「直屬主管由部門主管推導」 |

### 3.6 與 PF-226 的關係

不變。差別只在「空」的定義：ROLE@單位型別下，進關卡時 `assignees` 快照為空**不觸發**退回（ROLE 本來就不觸發），
只有**單位解析失敗**（申請人沒有單位）才觸發 `no_assignee_action`。`fallback_role` 仍是全域角色。

## 四、判定偽碼

```python
# build_actor
role_units = {(a.role_secure_code, a.unit_secure_code) for a in valid_assignments}
role_types = {role_sc: role.role_type}                     # 一次查
unit_ancestors = {u: [ancestors...] for u in units_seen}   # 一次查

def holds(actor, role_sc, unit_sc):
    if (role_sc, unit_sc) in actor.role_units or (role_sc, None) in actor.role_units: return True
    if unit_sc is None: return any(r == role_sc for r, _ in actor.role_units)
    if actor.role_types.get(role_sc) == 'POSITION': return False
    return any(r == role_sc and u and unit_sc in actor.unit_ancestors.get(u, []) for r, u in actor.role_units)

def _identity_matches(data, user_sc, actor):
    if not data.get('assignee_type'): return True
    if user_sc in data.get('assignees') or []: return True        # USER / INITIATOR / DYNAMIC 的指定人
    if data['assignee_type'] in ('ROLE', 'DEPARTMENT'):
        role_sc, unit_sc = _spec_from(data)                          # DEPARTMENT → (DEPT_MEMBER, unit)
        if holds(actor, role_sc, unit_sc): return True
        if data.get('assignee_role_type') == 'POSITION' and data.get('absence_fallback', True):
            for r in ordered_fallback_roles(role_sc):                # DEPUTY 永遠；PROXY 需主管缺席
                if holds(actor, r, unit_sc) and _fallback_allowed(r, unit_sc): return True
    return False
```

舊佇列項（沒有 `assignee_unit_secure_code` key）：`_spec_from()` 回 (role_sc, None)，行為與今天完全相同。

## 五、UI

設計器 FormAdapter modal「簽核者類型＝指定角色」區塊改成：
角色 select（現有）＋「單位範圍」select（不限／指定單位／申請人所屬單位／申請人單位的上層 N 層）＋
指定單位時的單位下拉（`GET /api/workflows/data/departments` 已有，要加社群）＋
角色是 POSITION 型時顯示「主管缺席時由副主管／代理人接手」checkbox。
「指定部門」型別從 select 移除（舊值仍可讀出並以唯讀標示「舊：指定部門＝該部門成員」）。
待簽清單與詳情顯示「部門主管@軟體部」；`fc-utils.js` 的標籤表補 `acted_as_role_code`。

## 六、分期（每期一個 codex 任務，順序不可調）

| 期 | 內容 | 檔案 | 測試 |
|---|---|---|---|
| 1 授權核心 | `build_actor` 展開 (role, unit)＋祖先快取；`_identity_matches` 依第四節；舊佇列項相容；`unit_resolver.py` 新檔（3.2） | `modules/form_workflow/services/task_authorizer.py`、`backend/app/services/unit_resolver.py` | 新檔 `test_task_authorizer_role_unit.py`：直接持有／全域超集／套圈／POSITION 不套圈／副主管永遠／代理人僅缺席／舊 data 相容／代理授權疊加 |
| 2 節點解析 | FormAdapter 讀 `unit_scope` 等 key，進關卡解析單位寫 `result.data`；DEPARTMENT 別名；解析失敗走 PF-226；逾時參考人用快照 | `formadapter_handler.py` | `test_formadapter_role_unit.py` |
| 3 設計器與顯示 | 第五節 UI、i18n、手冊 `workflows.md` | `wf-form-adapter.js`、`wf-node-form-adapter.js`、`wf-save.js`、`fc-utils.js`、`en.json`、`docs/manual/04_form_workflow/workflows.md` | 主 Claude 瀏覽器實點 |
| 4 主管來源統一 | 3.5（改寫版）：`resolve_direct_manager()` 新增；OpHrLookup 改用；任職卡指標退役（model、web、模板、hostconfig、seed）；dev 庫 DROP COLUMN；`HR_LOOKUP_NODE_SPEC.md` 規則 3～7 改寫 | `unit_resolver.py`、`hr_lookup_handler.py`、`employee_position.py`、`web/positions.py`、`positions/*.html`、`hostconfig.py`、`seed_test_companies.py`、手冊兩頁 | `test_hr_lookup_node.py` 增案（部門推導、本人是主管往上、職缺往上、無任職卡主管視為 0）；GHTRAVEL 重種後 30 萬／500 萬對照組一致、10 億走 PF-226 退回；**另含決策點 8**：`_match_identity()` 帶 spec key 的 ROLE／DEPARTMENT 任務不看快照（`test_task_authorizer_role_unit.py` 增案） |
| 5 請假缺席 | 缺席定義加入當日 LEAVE | `task_authorizer.py` | 增案 |

每期派工 spec 都要貼：`dev-notes/codex_spec/_footer.md`（必）、`security.md`（TENANT-01：所有查詢帶 org）、
第 3 期另貼 `frontend.md`＋`i18n.md`。**每期完成後主 Claude 驗收再派下一期**，不要合併派。

## 七、驗收矩陣（主 Claude 執行，憑證落 `/opt/tmp/verify/<日期>-role-unit-<期>.log`）

用 beluga（手動建的企業，有部門角色）與 GHTRAVEL（seed 企業，第四期後有部門角色）各跑：

| # | 情境 | 期望 |
|---|---|---|
| 1 | 節點 `DEPT_MANAGER@APPLICANT_UNIT`，申請人＝行銷部門 user | 行銷部門主管詳情 200；其他部門主管 403 |
| 2 | 同上，行銷部門**沒有**主管（職缺）、ethanyu 是副主管 | ethanyu 200；aaaa（代理人一）200；ssss 200；無關者 403 |
| 3 | 同上，行銷部門有主管在職 | 副主管 200；代理人(一)(二) **403** |
| 4 | 節點 `DEPT_MEMBER@資訊群`，行為人是軟體部成員 | 200（套圈） |
| 5 | 節點 `DEPT_MANAGER@資訊群`，行為人是軟體部主管 | 403（POSITION 不套圈） |
| 6 | 既有模板 `SECURITY_STAFF`（無單位）之 WAITING 任務 | 修前修後判定一字不差（用 PF-71 留下的 `REYhGxsy_rqYlpVeAQHRxy`） |
| 7 | Ethan 情境 2：單已在關卡、A 卸任、B 補上同角色@同單位 | B 待簽清單出現、詳情 200 |
| 8 | 申請人沒有任何單位 | 走 PF-226：退回或改派 |
| 9 | 代理授權：B 代理 A，A 是行銷部門主管 | B 200（授權人身分展開含單位） |
| 10 | 第四期：GHTRAVEL 30 萬／500 萬 | 與 `/opt/tmp/verify/20260902-hr-lookup-node.log` 對照組同一結果 |

## 八、待 Ethan 定案（審本檔時回答）

1. 套圈只對非 POSITION 角色（3.3 第 3～4 條）——對嗎？**Ethan 2026-09-05 定案：對**
2. 全企業指派（unit NULL）視為任何單位的超集（3.3 第 2 條）——對嗎？**Ethan 2026-09-05 定案：對**
3. 副主管永遠可簽、代理人只在主管職缺時可簽（3.4）——或副主管也只在缺席時？**Ethan 2026-09-05 定案：對**
4. 任職卡 `direct_manager_secure_code` 保留為明示覆寫（3.5）——或一律改由部門推導、把欄位退役？**Ethan 2026-09-05 定案：一律由部門推導、欄位退役**
5. `DEPARTMENT` 型別退役為別名（3.1）——同意？**Ethan 2026-09-05 定案：同意**
6. 第五期「主管請假算缺席」——**Ethan 2026-09-05 定案：要做**。「LEAVE」指 `schedule_adjustments.adjust_type='LEAVE'` 的班表調整列（語意：該人該日這些時段不工作；`status='APPROVED'`）。現況唯一寫入者是個人行事曆：員工建 LEAVE（請假）或 TRIP（出差）事件時由 `calendar_event_service` 同步寫入並帶 `calendar_event_secure_code`；`NULL` 來源（請假單流程、人工）目前**沒有任何程式會寫**、dev 庫 0 列。採用定義（除非 Ethan 反對）：**認全部 LEAVE 列不看來源、以時段判定**——判定當下（企業時區）落在該列請假時段內才算缺席（`adjusted_periods` 為 `[]` 或 NULL＝整天），出差同樣視為缺席。判定走 `ScheduleService.get_work_periods()` 既有優先序，不另寫查詢。

7. **申請人本人持有目標角色@單位時怎麼辦**（例：申請人就是自己部門的主管，節點是「部門主管@申請人所屬單位」）。第 2 期實作會派給自己簽。**Ethan 2026-09-05 定案：交給流程設計師決定**，含「無上層主管時自己簽自己給不給過」。實作為單一 config `self_target_action`（只在 `APPLICANT_UNIT`／`APPLICANT_ANCESTOR` 範圍有效；`UNIT`／`GLOBAL` 不受影響）：

   | 值 | 語意 |
   |---|---|
   | `escalate_or_return`（**預設**） | 本人持有目標 (角色, 單位) 就以同一規則往上一層重解析；到根仍是本人（或上層無人）→ 走 PF-226 `no_assignee_action`（預設退回申請人） |
   | `escalate_or_self` | 同上往上找；到根仍是本人 → 派給本人簽 |
   | `self` | 不往上，直接派給本人 |

   往上重解析時 POSITION 的缺席順位照舊（上層主管職缺→上層的副主管、代理人）。面板上做成一個 select「申請人本人就是簽核者時」三選一，`result.data` 寫 `self_target_action` 與實際發生的 `self_target_escalated_levels`（往上了幾層）。第 3 期一併做（handler＋測試＋面板）。

8. **ROLE 型任務的「快照命中永遠放行」要不要收掉？**（第 5 期複審提出）現況：`_match_identity()` 對 ROLE／DEPARTMENT 先看角色@單位與缺席順位，都不成立時仍以進關卡當下的 `assignees` 快照放行（2026-08-09 L1 的「快照永不縮減」語意）。後果：單子在主管請假期間進關卡，代理人已在快照內，主管銷假後代理人**仍可簽**；同理主管卸任後、被撤角色的人若在快照內也仍可簽。與「角色是活的、人是快照」不一致。原 session 建議：**帶有效 spec（`assignee_unit_secure_code` key 存在）的 ROLE／DEPARTMENT 任務不再看快照**，快照只供顯示與逾時參考人；舊佇列項（無 spec key）與 USER／INITIATOR／DYNAMIC 維持快照放行。改動只在 `task_authorizer._match_identity()` 一處＋測試，可併第 4 期或獨立小期。——**Ethan 2026-09-05 定案：收掉**。實作規則：`_match_identity()` 對 `assignee_type in (ROLE, DEPARTMENT)` 且 `assignee_unit_secure_code` key **存在**（含值為 null 的 GLOBAL 範圍，因為第 2 期起 handler 一律寫這個 key）時，只走角色@單位＋缺席順位，**不看 `assignees` 快照**；key 不存在（第 2 期前的舊佇列項）維持快照放行；USER／INITIATOR／DYNAMIC 不變。附帶效果：主管銷假、卸任、被撤角色即時失去簽核權；逾時參考人與待簽清單顯示仍用快照。測試：既有 `test_deputy_in_snapshot_still_records_acted_as` 要改成「快照有、角色沒有 → 不放行」；補「主管銷假後代理人 403」「舊佇列項無 key 仍放行」兩案。**併入第 4 期 spec**。

## 九、不在本設計內（已另存 PF-246）

會簽決議型式（全員／任意／人數／比例）、滑步、逾時升級到上層、USER 型別指定帳號停用後的處置。

## 十、BBN

本設計待辦：PF-247（見本檔 commit 後由主 Claude 建卡並回填代號）。PF-245（DEPARTMENT 型）併入第 2 期，卡上兩個選項作廢。

## 十一、執行記錄

### 第 1 期 授權核心——完成（2026-09-05 13:40，執行 session 驗收通過，待原 session 複審）

codex 一次過（spec `/opt/tmp/codex/20260905-pf247-phase1-spec.txt`，結果 `...-result.txt`），主 Claude 只還原了它順手砍掉的六段 docstring。
改動：`modules/form_workflow/services/task_authorizer.py`（重寫為 (role, unit) identity＋套圈＋缺席順位）、
新檔 `backend/app/services/unit_resolver.py`（`org_local_today` / `resolve_user_unit` / `get_unit_ancestor_codes`）、
新測試 `backend/tests/test_task_authorizer_role_unit.py`（15 案）、既有 `test_task_authorizer_delegate_from.py` 兩個相等斷言補 key、三份 manifest。

**與設計文件的差異／補充（複審請看這段）**：

1. `resolve_acting_identity()` 回傳值多一個 key `acted_as_role_code`（`None` / `DEPT_DEPUTY` / `DEPT_PROXY1` / `DEPT_PROXY2`）。
   3.4 說的 `fw_approval_records.acted_as_role_code` 欄位**本期沒加**（不動 schema），寫入與顯示留到第 3 期，屆時消費這個 key
2. DEPARTMENT 別名在**授權端**本期已生效（`_spec_from()`：DEPARTMENT → `DEPT_MEMBER@unit`，含套圈；企業沒有 `DEPT_MEMBER` 系統角色時 fail-closed 只認快照）。
   handler 端的解析（顯示用 `assignees` 快照）仍是第 2 期
3. `_holds()` 對「角色在該 org 查不到」的情況只認直接持有與全域持有、不套圈；ROLE 型任務的角色 sc 在該 org 查不到時整個 spec 視為無效（fail-closed）——設計文件沒寫到這兩個邊界，是 spec 補的
4. 缺席順位只在 `unit_sc` 不為 None 時做（無單位的 POSITION 任務沒有「該單位的主管」可言）
5. 主管「在職」的判定含全企業（unit NULL）持有 `DEPT_MANAGER` 的人（與套圈規則 2 一致），驗收案 8 有測
6. `unit_resolver.resolve_user_unit()` 的任職卡 fallback 路徑已實作但**測試留到第 4 期**（要建 JobFamily／JobLevel／JobTitle，codex 依 spec 允許先跳過並在測試註解說明）
7. `backend/app/services/approver_exposure_service.py::_snapshot_mentions_actor()` 仍用扁平 `actor['role_codes']` 比對流程**樣板**的 ROLE 簽核者——那是曝光計數用的超集判定，多算無害；第 3 期做設計器 `unit_scope` 時一併決定要不要收斂
8. **決策點 4（直屬主管一律由部門推導、任職卡 `direct_manager_secure_code` 退役）與 3.5 本文「有值＝明示覆寫，維持」相反**。第 1 期不受影響；**派第 4 期前必須先改寫 3.5 與第六節第 4 列**（含欄位退役的遷移：`hr_lookup_handler` 的 `direct_manager` 輸出、`EmployeePosition.get_manager_chain()`、任職卡 UI 的直屬主管欄位怎麼處置）

**驗收憑證** `/opt/tmp/verify/20260905-role-unit-phase1.log`：修前基準（#6 五帳號）→ 自跑 26 passed → 合成佇列列（新 key 由第 2 期 handler 才會寫，本期以 SQL 種六筆帶新 key 的 WAITING 列，驗完刪除）
＋ 帶標記的 SQL 角色指派，對 beluga 五個帳號跑第七節 #1～#7、#9、DEPARTMENT 別名、舊資料無單位，HTTP 200／403 共 43 項 PASS，
直接呼叫矩陣印出 `via` / 授權人 / `acted_as_role_code`。第一輪 12 個 FAIL 是驗收工具的 INSERT 缺 `created_at`／`updated_at`（ORM 預設、DB 無預設），不是程式問題，log 內有註明。
全量測試結果見 BBN #5400 追記。工具在 `/opt/tmp/verify/pf247/`（`phase1_http.sh` 可重跑，第 2 期驗收可沿用合成列的 key 形狀當 handler 輸出的對照）。

### 第 1 期複審（原 session，2026-09-05 15:24）——**通過，派第 2 期**

親自重跑 `test_task_authorizer_role_unit.py`＋`delegate_from`＋`formadapter_no_assignee` 32 passed；讀完 `task_authorizer.py` 全部 diff、
`unit_resolver.py`、15 條測試的斷言主體（各不相同）、憑證第二輪 43 項 PASS＋階段 B／C 全 PASS。判定邏輯與第三、四節一致：
直接持有／全域超集／非 POSITION 套圈方向正確（持有者在後代單位、目標在祖先）／POSITION 不套圈／副主管永遠／代理人僅職缺／
DEPARTMENT 別名走 DEPT_MEMBER 並套圈／舊佇列項無 `assignee_unit_secure_code` 時退回扁平比對／代理授權人身分同樣展開。

**要帶進第 2 期 spec 的三件事（不退回，併入下一期）**：

1. `get_actor_role_codes()` 已無任何呼叫者（只剩定義）——死碼，第 2 期順手刪除；`get_delegated_identities()` 只剩 `test_delegation_effective_status.py` 在用，保留
2. 缺席順位依賴佇列項 `assignee_role_type == 'POSITION'`，**第 2 期 handler 進關卡時必須從 `Role.role_type` 寫入這個 key**（不能寫死、不能省），
   否則新流程永遠不會走順位；`absence_fallback` 也要照 config 寫進 `result.data`
3. `_spec_from()` 對「角色 sc 在該企業查不到（含軟刪除）」回 None＝該任務無人可簽（fail-closed）——比修前嚴（修前只要指派還在就能簽）。可接受，
   但第 2 期 handler 在進關卡時就要驗角色存在，存在才寫 spec，否則走 PF-226 的 `no_assignee_action`，不要讓死角色留到授權端才被擋

### 第 2 期 節點解析——完成（2026-09-05 15:55，執行 session 驗收通過，待原 session 複審）

codex 一次過（spec `/opt/tmp/codex/20260905-pf247-phase2-spec.txt`）。複審的三件事都已落地：`get_actor_role_codes()` 刪除；
handler 進關卡時 `assignee_role_type` 從 `Role.role_type` 寫、`absence_fallback` 照 config 正規化後寫；角色在該企業查不到（含軟刪除、別家企業）
一律在進關卡時走 PF-226 `no_assignee_action`（原因 `角色 <sc> 不存在或已刪除`）。改動：`formadapter_handler.py`（`validate()` 正規化
`unit_scope`／`unit_secure_code`／`unit_levels_up`／`absence_fallback`；`_resolve_assignee_spec()` 解析四種範圍；`_role_spec_data()` 組快照與 key，
`fallback_role` 路徑共用）、`unit_resolver.py` 新增 `get_unit()`／`get_unit_descendant_codes()`／`resolve_role_holders()`、
`task_authorizer._unit_manager_present()` 改用 `resolve_role_holders()`、新測試 `test_formadapter_role_unit.py`（13 案）、manifest 兩份。

**與設計文件的差異／補充（複審請看這段）**：

1. **快照＝「當下能簽的人」而不只是「持有者」**：POSITION 目標且 `absence_fallback` 為真時，主管在職＝主管＋副主管；職缺＝副主管＋代理一＋代理二
   （順序即此，去重保序）；非 POSITION 目標含後代單位持有者；全企業持有者一律算。3.1 原文只寫「當下持有者快照」，主管職缺時會顯示空白但副主管其實能簽，
   所以改成與授權端 `_match_identity()` 鏡像。逾時參考人（WORKING 模式）吃同一份快照，主管在前
2. **DEPARTMENT 在 handler 端正規化成 ROLE**：`result.data.assignee_type` 變 `'ROLE'`、`assignee_value` 變該企業 `DEPT_MEMBER` 的 sc、
   `assignee_unit_scope='DEPARTMENT'`、`original_assignee_type/value` 保留原值；快照＝持有 `DEPT_MEMBER@部門`（含子部門）的人，
   **不再看 `users.primary_unit_secure_code`**（PF-245 至此關單條件成立，實流程 B1 驗過）。授權端第 1 期的 DEPARTMENT 別名分支只剩舊佇列項在用
3. `resolve_role_holders()` 會過濾 `valid_from/valid_until`，被它取代的舊 `_resolve_role_users()` 不會——這是修正不是回歸；
   `_resolve_department_users()` 一併刪除
4. `APPLICANT_ANCESTOR` 且申請人單位已是根 → 目標＝該單位本身（「超過根就取根」的邊界）
5. 快照為空（ROLE 語意）**不退回**，只有角色／單位／申請人單位解析失敗才走 PF-226；`fallback_role` 改派後的 data 也帶完整的 role spec key（unit None、`GLOBAL`）
6. **設計器還不能設 `unit_scope`**（第 3 期），本期實流程驗收是用腳本直接寫 graph 並發行：BELUGA 留下三條已發行流程
   `PF247_P2_A`（`DEPT_MANAGER@APPLICANT_UNIT`）／`PF247_P2_B`（舊式 `DEPARTMENT 資訊群`）／`PF247_P2_C`（`DEPT_MEMBER@資訊群` 指定單位），
   佈建腳本 `/opt/tmp/verify/pf247/provision_phase2_flow.py`（冪等，可重跑）。**第 3 期驗設計器時直接開這三條**；驗完不要的話把 mapping／published 軟刪除即可
7. **未處理、提給 Ethan**：`APPLICANT_UNIT`＋`DEPT_MANAGER` 時，**申請人自己就是該單位主管**會派給自己簽（3.5 只對 OpHrLookup 規定「本人是主管就往上一層」，
   FormAdapter 端沒有這條）。要的話第 3 期加一個 config 開關（例如 `skip_self_manager`：申請人為目標單位主管時改取上一層），不要就維持
8. `approver_exposure_service._snapshot_mentions_actor()` 仍用扁平 `role_codes` 比對**樣板**（第 1 期已註記），第 3 期做設計器 `unit_scope` 時一併看

**驗收憑證** `/opt/tmp/verify/20260905-role-unit-phase2.log`：自跑六支測試 61 passed → 重啟 web（executor 以 subprocess 跑 handler，不必重啟，
本期沒有 RUNNING 節點）→ 實流程 55 項全 PASS：A1（主管職缺：快照＝副主管、代理一、代理二；三人 200、成員與外人 403）、A2（shen 就任主管：快照＝主管、副主管；
代理人轉 403、shen 待簽清單有單）、A3（沒有單位的申請人送單：`complete_workflow`＋REJECTED＋`no_assignee` 記錄「申請人沒有所屬單位」）、
B1（舊式 DEPARTMENT：正規化成 ROLE、快照只有持 `DEPT_MEMBER@軟體部` 的 ssss、套圈 200）、C1（指定單位同上）、#6 既有任務五帳號不變、
副主管 ethanyu 走 approve 端點核准 A1 成功（記錄 `approved`）。收尾把 A2／B1／C1 三張測試單也簽掉，測試指派 0 殘留。全量測試見 BBN #5400 追記。

### 第 2 期複審（原 session，2026-09-05 16:24）——**通過，派第 3 期**

親自重跑四個測試檔 45 passed；讀完 handler 全部 diff（`validate()` 正規化、`_resolve_assignee_spec()` 四種範圍、`_role_spec_data()` 快照＝當下能簽的人、
DEPARTMENT 正規化、失敗一律走 PF-226）、`unit_resolver` 新增三支、`task_authorizer` 死碼刪除與 `_unit_manager_present` 改用 `resolve_role_holders`、
13 條測試斷言（各不相同）、憑證 45 項 PASS 與全量 1062 passed。第 1 期複審的三件事全部落地。快照鏡像授權端（主管在職＝主管＋副主管、職缺＝副主管＋代理一二）是合理的補充，採納。
附件授權 `file_authorizer.py` 走 `is_pending_assignee()` 即時判定、不吃快照，確認過沒有「補進角色的人簽得了卻看不到附件」的問題。

**要帶進第 3 期 spec 的五件事**：

1. 第八節**決策點 7**（`skip_self`）——等 Ethan 回答；答「開」就在第 3 期一併做 handler＋測試＋面板 checkbox
2. `modules/form_workflow/services/file_authorizer.py` 第 10 行 docstring 仍寫「result['data']['assignees']」，實際走 `is_pending_assignee()`，改成正確描述（一行）
3. `approver_exposure_service._snapshot_mentions_actor()` 的扁平 `role_codes` 比對：第 3 期讀完決定收斂或明文保留，不要再往後拖
4. 第 3 期 commit 要一併更新 `CLAUDE.md`：「流程 graph 的引擎行為」表加一列「簽核者＝角色@單位（PF-247）」（config key、`result.data` 新 key、DEPARTMENT 別名、快照只供顯示、授權即時），
   並把 PERM-03 區段的「`roles` 表沒有 `user_type`」那段旁邊補一句指向本設計文件；「每個 session 都會撞一次的欄位名」表加 `user_role_assignments.unit_secure_code` 的語意
5. 設計器：`unit_scope` 四種、`UNIT` 的單位下拉要含社群（`/api/workflows/data/departments` 現只列部門，查 `workflows.py:1242`）、
   `APPLICANT_ANCESTOR` 的層數輸入、POSITION 角色才顯示 `absence_fallback`；舊 graph 的「指定部門」唯讀顯示；**套用與儲存流程兩條路徑都收集**（PF-226 的坑）。
   驗收直接用第 2 期留下的 `PF247_P2_A/B/C` 三條已發行流程，改設定→儲存→重發行→重送，憑證要有瀏覽器實點的 evaluate 輸出

### 第 3 期 設計器與顯示、self_target_action、acted_as 記錄——完成（2026-09-05 18:20，執行 session 驗收通過，待原 session 複審）

codex 一次過（spec `/opt/tmp/codex/20260905-pf247-phase3-spec.txt`），主 Claude 驗收時修了兩處（見下）。複審交辦五件事全部落地：決策點 7 的 `self_target_action`
（handler＋測試＋面板）；`file_authorizer.py` docstring；`approver_exposure_service` 明文保留（加註解）；CLAUDE.md 三處（引擎行為表加列、PERM-03 指向本設計、欄位表加
`user_role_assignments.unit_secure_code`）；設計器 UI 五個要點含兩條儲存路徑。改動 24 檔：handler（`SELF_TARGET_ACTIONS`、`_apply_self_target()`、`assignee_role_name`）、
`FwApprovalRecord.acted_as_role_code`（**schema 變更**：dev 已 `ALTER TABLE fw_approval_records ADD COLUMN acted_as_role_code VARCHAR(50)`，守恆檢查綠；
**bpserv 等既有環境 `--update` 後要手動下同一句**）、三支簽核 API 寫入、待簽清單／詳情／表單詳情 API 補顯示欄位、新 API `GET /api/workflows/data/units`
（守門同 `/data/roles`，守門表已 `--update`）、`/data/roles` 加 `role_type`、設計器 modal 與 `wf-node-form-adapter.js`／`wf-save.js`、`fc-utils.js`、四個模板、en.json 25 條、
手冊一節、新測試 `test_approval_record_acted_as.py`＋`test_formadapter_role_unit.py` 追加 12 案＋`test_task_authorizer_role_unit.py` 追加 1 案。

**與設計文件的差異／補充（複審請看這段）**：

1. **`self_target_action` 的兩個界定**（spec 時定的，寫進 3.1 附近請一併採納或退回）：「本人就是簽核者」＝申請人在該關卡**快照**內（含副主管、代理人）；
   **只對 POSITION 型目標角色做**——成員類角色（`DEPT_MEMBER@申請人所屬單位`）申請人本來就在集合內且會套圈到根，做了等於永遠退回。`result.data` 對 APPLICANT 範圍
   寫 `self_target_action`／`self_target_escalated_levels`，GLOBAL／UNIT／DEPARTMENT 別名不寫
2. **`escalate_or_self` 到根仍是本人時採用原本那一層**（`self_target_escalated_levels=0`），不是根層
3. **驗收抓到並修掉：副主管簽核記錄的 `acted_as_role_code` 一律 NULL**。成因是第 2 期起快照含副主管／代理人，而 `_match_identity()` 先看快照命中（回 `acted_as=None`）
   才看角色@單位；改成 ROLE／DEPARTMENT 先看角色@單位再看快照——**放不放行完全不變，只影響 `acted_as_role_code` 歸因**。回歸測試
   `test_deputy_in_snapshot_still_records_acted_as`；實流程 S3 第一輪 FAIL、修後 PASS（憑證有兩輪）
4. 驗收抓到並修掉：設計器兩條路徑的 `parseInt(...) || 1` 把層數 0 吃成 1，「往上層數必須是 1 以上」的驗證永遠到不了；改成 `Number.isNaN` 判斷
5. `wf-save.js` 的「直接儲存流程」收集只在右側節點面板開著（`currentEditingNodeId` 有值）時進行——這是既有設計，PF-226 也如此；只開 modal 不開面板的話儲存不會收集 modal 值。
   實測照真實操作（點節點開面板 → 開 modal → 改值 → 儲存）DB 正確
6. `/api/workflows/data/units` 的單位下拉依 `organizational_units.level` 縮排；BELUGA 有幾個舊單位 `level` 存錯（子單位也是 1，例如 BBBBB／cxzczx），縮排跟著錯，
   **是資料不是程式**；資訊群底下的五個部門 level=2 縮排正確
7. `loadRolesList()` 改版後無呼叫者，已刪（死碼）
8. 舊「指定部門」型別：modal 只在現值是 DEPARTMENT 時渲染一個標成「（舊）」的 option，切走就消失；`wf-accordion` 摘要標籤同步改「指定部門（舊）」

**驗收憑證** `/opt/tmp/verify/20260905-role-unit-phase3.log`：自跑七支測試 69 passed（修歸因後再跑四支 50 passed）→ 守恆檢查綠 → mkdocs strict 過 →
實流程兩輪（第二輪 FAIL=0）：S1 本人是根單位主管預設退回（reason「申請人本人為簽核者，往上 0 層仍無其他簽核人」）、S2 軟體部主管送單派給資訊群主管 levels=1
且清單／詳情帶 `assignee_role_name`／`assignee_unit_name`、S3 副主管核准記錄 `DEPT_DEPUTY` 且詳情 approvals 帶出、S4 `/data/units` 含社群且 EMPLOYEE 403、
`/data/roles` 帶 `role_type` → chrome-devtools 實點：設計器 modal 初次渲染值、四個 row 的顯示切換、單位下拉縮排與社群後綴、套用路徑的驗證與 config、
儲存路徑寫進 DB（revision 4）、重新發行後 `escalate_or_self` 實流程本人簽（S1b，記錄 `acted_as=NULL`）、ethanyu 待簽清單列與簽核 modal 表頭顯示「部門主管@行銷部門」、
申請人閱讀表單 modal 歷程顯示「ethanyu（以副主管身分）核准」、三頁 console error 0。全量測試見 BBN #5400 追記。
BELUGA 的 `PF247_P2_A` 現在是 `APPLICANT_UNIT`＋`escalate_or_self`（published `Mf7MSqu4IsXrmJBWsbKBfg`），B／C 未動。

### 第 3 期複審（原 session，2026-09-05 18:52）——**通過**

親自重跑六個測試檔（含 `test_route_guard_table`）58 passed；`check_schema_drift.sh` 綠（108 表／1817 欄一致）；mkdocs strict 無 anchor 訊息；
讀完 handler `_apply_self_target()`、`_match_identity()` 歸因順序調整（放行集合不變，只影響 `acted_as_role_code`）、新 API `/data/units` 守門、
四支 JS diff（兩條儲存路徑都收集、`escapeHtml` 補上、`loadRolesList` 死碼已刪、層數 0 不再被吃掉）、13 條新測試名；憑證第二輪 FAIL=0，
瀏覽器實點有 evaluate 輸出（modal 初值、四個 row 切換、單位下拉縮排與社群後綴、套用與儲存兩條路徑寫進 DB、待簽列與 modal 表頭「部門主管@行銷部門」、
歷程「（以副主管身分）」、三頁 console error 0）。執行 session 自己抓到並修掉的兩個問題（acted_as 歸因順序、層數 0）是真問題，處理正確。
第 1 條界定（本人＝在快照內、只對 POSITION）採納，已視同 3.1 補充。

**帶進後續的事**：

1. `fw_approval_records.acted_as_role_code` 是 schema 變更：**bpserv 部署時 `--update` 後要手動 `ALTER TABLE fw_approval_records ADD COLUMN acted_as_role_code VARCHAR(50);`**，
   與第 4 期的 `DROP COLUMN direct_manager_secure_code` 一起列在部署清單
2. `wf-save.js` 只在右側面板開著時收集 modal 值（既有設計，PF-226 同）——記進 `dev-notes/WORKFLOW_DESIGNER_NOTES.md`，不改
3. BELUGA `PF247_P2_A` 已是 `APPLICANT_UNIT`＋`escalate_or_self`（published `Mf7MSqu4IsXrmJBWsbKBfg`），B／C 未動；第 4、5 期驗收可沿用，全部做完後決定留或軟刪

### 執行 session 的接續安排（原 session 建議，2026-09-05 18:52）

執行 session 已用 67% context。第 4 期（主管來源統一：`resolve_direct_manager()`、OpHrLookup 改寫、任職卡欄位退役含 model／web／模板／hostconfig／seed／DROP COLUMN、
HR 規格與手冊、GHTRAVEL 重種驗收）是五期中最重的一期，估 20～30%，做到一半斷掉比現在換手更糟。**建議：**

- 現在的執行 session **先做第 5 期**（主管請假算缺席，只動 `task_authorizer._unit_manager_present()`／快照的 `manager_vacant` 判定＋測試＋手冊一句，估 5～8%），
  第 4、5 期彼此獨立，順序對調沒有依賴問題
- 第 5 期複審通過後，該 session **寫交接補篇** `dev-notes/handoff_role_unit_phase4_20260905.md`（它累積的坑、`/opt/tmp/verify/pf247/` 工具清單與用法、
  BELUGA／GHTRAVEL 現況、bpserv 待做的兩句 SQL、第 4 期 spec 要貼的檔案清單與現況行號），然後結束
- **新 session 做第 4 期**，照本文件 3.5 改寫版＋第六節第 4 列＋交接補篇；原 session 照舊複審

### 第 5 期 主管當日請假算缺席——完成（2026-09-05 19:35，執行 session 驗收通過，待原 session 複審）

codex 一次過（spec `/opt/tmp/codex/20260905-pf247-phase5-spec.txt`），主 Claude 驗收時只刪了 `is_on_leave()` 內一段重複的區間減法（見第 2 點）。
改動：`ScheduleService.is_on_leave(user, local_dt)`（新）、`unit_resolver.org_local_now()`（新）、`task_authorizer`（`build_actor` 多放 `_local_now`、
`_unit_manager_present()` 改成「任一主管未請假才算在職」）、handler `_role_spec_data()` 的 `manager_vacant` 改看 `_present_managers()`（快照鏡像）、
新測試 `test_schedule_is_on_leave.py`（8 案）＋授權 6 案＋handler 2 案、手冊一句、manifest 兩份。**不動 schema、不動 API、不動前端。**

**與設計文件的差異／補充（複審請看這段）**：

1. 第八節第 6 條寫「判定走 `ScheduleService.get_work_periods()` 既有優先序」——**沒有直接呼叫 `get_work_periods()`**，因為它回的是「剩餘工作時段」，
   分不出「請假中」與「下班了」，而且沒班表的企業永遠回 `[]`。改成 `ScheduleService.is_on_leave()`：同一組 LEAVE 列查詢條件（APPROVED、未刪、當地日），
   `adjusted_periods` 為 NULL／`[]`＝整天；否則請假時段＝`original_periods`（空時退回 `get_base_work_periods()`）− `adjusted_periods`，當下落在內才算。
   決策的四個要點（不看來源、時段判定、`[]`／NULL＝整天、出差同樣算——行事曆 TRIP 也寫 LEAVE 列）全部成立
2. 區間減法沒用 `work_periods.subtract_periods()`（它刻意丟掉跨午夜的午夜後片段，給 resync 存 `HH:MM` 字串用），`ScheduleService._subtract_period_intervals()`
   自己做，跨午夜底（`22:00-06:00`）也判得對；codex 原本兩套都算再聯集，驗收時刪成一套
3. **沒有班表的企業（dev BELUGA）時段級請假等於整天**：resync 寫出的 `original_periods=[]`、`adjusted_periods=[]`，落入「`[]`＝整天」。這是決策 6 定義的自然結果，
   有班表的企業（GHTRAVEL）才有真正的時段級；人工列若自帶 `original_periods` 則不受班表影響（S5d 驗過）
4. **快照永不縮減的既有語意在這裡會顯現**：單子在主管請假期間進關卡，代理人已寫進快照，主管銷假後代理人**仍可簽**；反過來（進關卡時主管在職）銷假即時生效。
   驗收第三輪誤判過一次，第四輪按正確順序驗過（見憑證）。要不要改成「快照命中也要重驗缺席」是另一個決策，本期不動
5. 主管本人請假中**仍可簽**（授權端不擋主管；請假只解鎖代理人），快照也保留主管；副主管不受影響
6. `TimeContextService.who_on_leave()`（管理員視角、看行事曆事件、不看 `adjusted_periods`）與本期 `is_on_leave()` 是兩個消費端、兩套判法，**刻意不合併**
7. 判定時刻＝企業時區當下（`org_local_now()`／handler `_local_now()`），授權端每個 actor 算一次快取在 `_local_now`；測試用 `actor['_local_now'] = datetime(...)` 或
   monkeypatch `FormAdapterHandler._local_now` 固定時間

**驗收憑證** `/opt/tmp/verify/20260905-role-unit-phase5.log`：自跑 `test_schedule_is_on_leave.py` 8 passed（codex 自跑六支 105 passed）→ mkdocs strict 過 →
實流程（BELUGA，shen 暫任行銷主管）：S5a 在職＝快照 `[shen, ethanyu]`、代理人 403；S5b shen 走**真實路徑** `POST /api/calendar/events` 登記今天整天請假 →
`schedule_adjustments` 出現 LEAVE 列（`adjusted=[]`、帶 `calendar_event_secure_code`）→ 同一張單代理人一二 200、主管本人 200、新單快照 `[shen, ethanyu, aaaa, ssss]`、
代理人一核准記錄 `acted_as=DEPT_PROXY1`；S5c（第四輪）在職時進關卡 → 請假 200 → `DELETE /api/calendar/events/<sc>` 銷假（列軟刪除）→ 403 即時生效；
S5d 人工列（不看來源）`original=['00:00-23:59']`、`adjusted` 挖掉涵蓋現在的一小時 → 200、改成不涵蓋 → 403。前三輪的 FAIL 都是驗收腳本（事件 sc 在回應的
`event.secure_code` 不在 `data`；第三輪用了請假期間進關卡的單），已修正腳本並註明。全量測試見 BBN #5400 追記。測試指派／請假列／事件零殘留。

### 第 5 期複審（原 session，2026-09-05 20:24）——**通過**

親自重跑 `test_schedule_is_on_leave`＋授權＋handler 三檔 54 passed；讀完 `is_on_leave()`／`_subtract_period_intervals()`（跨午夜自做減法的理由成立）、
`org_local_now()`、`_unit_manager_present()` 改「任一主管未請假才在職」、handler `_present_managers()` 鏡像；16 條新測試斷言各不相同；
憑證最終輪 S5a～S5d 全 PASS（前三輪的 FAIL 是驗收腳本讀錯事件 sc 與情境順序，log 內註明），全量 1090 passed。
第 1 條差異（不呼叫 `get_work_periods()`，改 `is_on_leave()`）理由成立，採納，視同第八節第 6 條的實作定義。

**兩件事**：

1. 第 4 條差異（快照永不縮減 → 代理人在主管銷假後仍可簽）不是第 5 期的 bug，是 L1 既有語意與本設計的衝突，已提為**第八節決策點 8**，等 Ethan 定案
2. `is_on_leave()` 對跨午夜班（`22:00-06:00`）的「隔日凌晨」是用同一列＋1440 分鐘比對，等於把 D 日列的午夜後片段算在 D 日凌晨；夜班企業的請假列語意要與班表引擎一致，
   目前 dev 沒有夜班班表，**不列缺陷、記在此**，日後做夜班時一併定

第 1～3、5 期完成，dev HEAD `76ec9940`＋本複審 commit，**origin 落後 11 筆未 push**（執行 session 只 commit）。第 4 期換新 session，照交接補篇 `handoff_role_unit_phase4_20260905.md`。

### 第 4 期 直屬主管來源統一、任職卡指標退役、決策點 8——完成（2026-09-05 21:35，執行 session（新）驗收通過，待原 session 複審）

codex 一次過（spec `/opt/tmp/codex/20260905-pf247-phase4-spec.txt`，結果 `...-result.txt`，40 分鐘上限內 36 分鐘完成），主 Claude **沒有改任何一行程式**。
改動 28 檔＋2 新檔：`unit_resolver.py` 新增 `iter_manager_chain()`（generator，每站 `{manager_secure_code, unit_secure_code, unit_name, levels_up}`）與
`resolve_direct_manager()`（＝第一站）；`hr_lookup_handler.py` 的 `hr_direct_manager*` 與核決鏈改吃它，新增 `hr_direct_manager_unit(_name)`／`hr_approver_unit(_name)`，
主管沒有有效任職卡＝該站上限 0 繼續往上、迴圈偵測連同 `visited` 刪除（單位鏈不會迴圈，20 站上限維持）；`EmployeePosition` 刪 `direct_manager_secure_code`／relationship／
`get_manager_chain()`／`to_dict` 兩個 key；`web/positions.py` 三個 handler 與四個模板、`users/view.html` 職位列、`hostconfig.PURGE_ORPHAN_CLEANUP`、`add_column_comments.sql` 同步退役；
**新檔 `backend/app/services/dept_membership_service.py`**：`organizational_units.py` 五個私有 helper 原樣搬成公開函式＋新增 `set_dept_manager()`（＝原 `set_unit_manager` 端點 try 區塊），
API 四個呼叫點改用、`set_unit_leadership()` 不動；`seed_test_companies.py` 刪 `assign_direct_managers()`、新增 `sync_dept_roles()`（依 PRIMARY 任職卡種 SOLID membership＋`DEPT_MEMBER`／
`DEPT_EMPLOYEE`，head → `DEPT_MANAGER@unit`，持有者集合已等於預期就跳過）與 `--sync-dept-roles`；`task_authorizer._match_identity()` 一處（決策點 8）；
測試四檔（`test_hr_lookup_node.py` fixture 改成兩層單位＋角色指派、+6 案、迴圈案改成「無任職卡主管視為 0」；`test_task_authorizer_role_unit.py` 改 1 案＋3 案；
`test_users_position_display.py` 改 helper＋3 案；新檔 `test_dept_membership_service.py` 4 案）；`HR_LOOKUP_NODE_SPEC.md` 新增「直屬主管推導」節、規則 3～7 改寫；
手冊 `hr_lookup_node.md`／`positions.md`／`job_matrix.md`；manifest 四份；po 三條新翻譯。dev 庫已 `DROP COLUMN direct_manager_secure_code`，守恆檢查綠（108 表／1816 欄一致，比第 3 期少 1 欄）。

**與設計文件的差異／補充（複審請看這段）**：

1. **交接補篇第三節「沒有其他地方引用」是錯的**，盤點多抓到三處並一併處理：`users/view.html` 職位列的 `／ 主管名` 片段（直接拿掉，該列只剩 類型／職稱／部門／期間）、
   `test_users_position_display.py`（`_assign_position()` 的 `direct_manager` 參數與 `test_inactive_direct_manager_name_is_hidden`，後者改成職位詳情頁推導主管的三案）、
   `scripts/add_column_comments.sql` 的 COMMENT 列
2. **3.5 第 2 條「多人時取 `assigned_at` 最早」照字面實作**：`resolve_role_holders(DEPT_MANAGER, unit=U)` 回「單位 U 指派 ∪ 全企業指派」依 `assigned_at` 排序，取第一個不是本人、
   也還沒在鏈上出現過的人。後果：**全企業持有 `DEPT_MANAGER`（unit NULL）的人會在每一層與單位主管競爭，指派較早者贏**（`test_direct_manager_uses_global_manager_assignment` 驗的就是這個）。
   本期依「照本檔做，不要自行詮釋」沒有改成「單位指派優先」；要不要改請複審決定（改動只在 `iter_manager_chain()` 一處）。已寫進 `HR_LOOKUP_NODE_SPEC.md` 已知限制
3. **「本人是主管往上」的實作是「跳過本人再看同單位其他持有者」**，不是「本人持有就整層跳過」：同單位若另有第二位主管（例如全企業指派），先取那一位；沒有才往上。
   單一主管的情境兩種讀法結果相同
4. `iter_manager_chain()` 用 `visited`（含申請人本人）去重：同一人身兼兩層單位主管只算一站——所以 3.5 說的「迴圈與 20 站上限維持」裡的迴圈偵測其實不再需要
   （單位祖先鏈本身防循環），handler 只留 20 站上限
5. 職位詳情頁（`/positions/<sc>`）改顯示「直屬主管（依部門推導）」＋連結＋單位名，沒有主管時顯示「無（所屬部門及其上層都沒有在職主管）」；列表頁直接拿掉該欄（9→8 欄）。
   `view_position()` 取推導主管的 User 走 `ResourceGateway.get(User, ...)`（會查 `user:read`），所以測試要種 `user:read` 與 `employee_position:read` 兩個 permission
6. `sync_dept_roles()` 對「持有者集合已等於預期主管」的單位仍呼叫 `ensure_dept_membership()` 再 `revoke_role_assignment(DEPT_EMPLOYEE)`，每次重跑會把該主管的 `DEPT_EMPLOYEE@unit` 列復活再軟刪一次
   （列數不變、`updated_at` 會動）。冪等以「列數／持有者集合」為準成立（第二次跑三家全 0），這個小瑕疵不影響結果，記在此供複審判斷要不要收
7. codex 順手做了兩件 spec 沒要求的事：seed 腳本加 `signal.signal(signal.SIGPIPE, signal.SIG_DFL)`（避免 `| head` 時 BrokenPipe）、把 `OrganizationService` import 移進 `seed_one_company()`。
   兩者無害、未退回，記在此
8. 決策點 8 的實作位置：`_match_identity()` 的 ROLE／DEPARTMENT 分支結尾加 `if 'assignee_unit_secure_code' in task_result_data: return None`——所以 `_spec_from()` 回 None（角色查不到）且 key 存在時也是 None（fail-closed），
   無 key 的舊佇列項與 USER／INITIATOR／DYNAMIC 落到原本的 `in_snapshot` 判定。**S8 實流程證明「角色是活的」**：shen 就任行銷主管後快照不變、代理人一二即時 403，卸任後即時 200

**驗收憑證** `/opt/tmp/verify/20260905-role-unit-phase4.log`：反向檢查殘留引用為空 → dev 庫 DROP COLUMN → 重啟 web＋executor →
`--sync-dept-roles` 兩次（第一次 GHTRAVEL `positions 20 / memberships_created 20 / roles_created 52 / managers_set 12`，jason.ling 既有的 `DEPT_MANAGER@企業旅遊部` 沒重複；第二次三家全 0）→
**舊指標對照 60/60 PASS**（DROP COLUMN 前存檔的三家範例企業 PRIMARY 任職卡指標 vs `resolve_direct_manager()`，含最頂層主管＝空；brian.ling 核決鏈 kevin.ye@團體旅遊部 → amy.xiao@業務處 → david.hao@總經理室）→
實流程 FAIL=0：G1 翎柏瑞 30 萬 → 燁凱文（`hr_direct_manager_unit=GROUP_TOUR`、`hr_approver_level_code=L500`、`hr_approver_unit_name=團體旅遊部`，kevin 200／amy 403／brian 403）、
G2 500 萬 → 霄雅慧（L700、`hr_approver_unit=SALES_DIV`）、G3 10 億 → `hr_approver_found=false`、`complete_workflow`＋REJECTED＋`no_assignee` 記錄（與 2026-09-02／09-05 對照組一字不差）、
G4 七個頁面斷言（列表無直屬主管欄、詳情頁有推導主管＋單位、david.hao 詳情頁顯示無主管、新增／編輯頁無 `direct_manager_secure_code`、users 詳情頁職位列無主管名）、
S8（BELUGA `PF247_P2_A`）主管職缺快照 `[ethanyu, aaaa, ssss]` 三人 200 → shen 就任後快照未變、aaaa／ssss 403、ethanyu／shen 200 → 卸任後 aaaa 200、shen 403、
#6 既有 SECURITY_STAFF 舊佇列項五帳號判定不變 → chrome-devtools 實點（職位詳情頁 evaluate 回 `href=/beakplatform/users/yIVOrZiT0ltlPjtBm6o8mQ`、點下去落在燁凱文用戶詳情、
用戶詳情職位列無主管段、列表 8 欄表頭與儲存格一致、新增頁 select 只有四個；四頁 console error/warn 0）。自跑 12 檔 115 passed（含 12 檔既有回歸）；mkdocs strict 過、po `untranslated []`／`fuzzy []`；
全量 1105 passed／1 failed（`test_admin_required_for_admin`，PF-34 已知）／2 skipped（第 5 期後基準 1090，+15 皆為本期新案，無回歸）。測試單全部簽掉、測試指派零殘留。

### 第 4 期複審（原 session，2026-09-05 22:09）——**通過，附補丁 4a（小，同 session 做）**

親自重跑五個測試檔 79 passed；守恆檢查綠（108 表／1816 欄）；殘留引用 `direct_manager_secure_code`／`get_manager_chain` 為空；
讀完 `iter_manager_chain()`／`resolve_direct_manager()`、OpHrLookup 改寫、`_match_identity()` 決策點 8 一行、CLAUDE.md 三處與 HR 規格改寫；
憑證：舊指標對照 60/60、實流程 FAIL=0（G1～G4、S8、#6）、瀏覽器實點四頁 console 0、全量 1105。執行 session 盤點出交接補篇漏列的三處並一併處理，正確。
差異 3、4、5、7、8 採納。

**補丁 4a（併一次派工，不另開期）**：

1. **差異 2 改掉**：`iter_manager_chain()` 每一站**先取單位指派**（`unit_secure_code == U`）的 `DEPT_MANAGER` 持有者，**沒有才退回全企業指派**（unit NULL）；
   同類內仍依 `assigned_at` 最早。理由：全企業指派是「什麼單位都算」的超集語意（3.3 規則 2），用在授權判定對；用在「誰是我的直屬主管」會讓一個全企業指派較早的人
   壓過每一層的真正單位主管。`resolve_role_holders()` 不改簽章，在 `iter_manager_chain()` 內分兩次查（或加 `unit_only` 參數，spec 定）。
   測試：`test_direct_manager_uses_global_manager_assignment` 改語意（單位主管優先，全企業只在職缺時上），HR 規格「已知限制」那條改成規則
2. **差異 6 收掉**：`sync_dept_roles()` 對持有者集合已正確的單位不要再 `ensure`＋`revoke` 一輪（`updated_at` 不該動）；冪等以「第二次跑三家全 0 且無列被觸碰」驗
3. 設計文件 3.5 第 2 條同步改寫為「單位指派優先、全企業指派僅職缺時候補」（原 session 已改，見下）

4a 做完不必重跑全量，跑 `test_hr_lookup_node.py`＋`test_dept_membership_service.py`＋守恆檢查＋GHTRAVEL G1／G2 兩張單即可；憑證接在 phase4 log 尾。

### 補丁 4a——完成（2026-09-05 23:20，執行 session；待原 session 複審）

codex 做完兩支 service、seed 與 HR 測試後撞 ChatGPT 用量上限（exit=1，停用至 09-07；spec `/opt/tmp/codex/20260905-pf247-phase4a-spec.txt`），
`test_dept_membership_service.py` 三案與 `HR_LOOKUP_NODE_SPEC.md` 改寫依 codex-first 例外由主 Claude 補齊。

1. **差異 2 改掉**：`resolve_role_holders()` 加 keyword `unit_only=False`（預設行為一字不差，三個既有呼叫端未動）；
   `iter_manager_chain()` 每站先取 `unit_only=True` 的單位指派持有者（排除 visited），沒有才從「單位 ∪ 全企業」中取不在單位集合內的全企業指派。
   合成語意：本人是單位指派主管且另有全企業指派 G → 該站是 G（差異 3 保留）；職缺 → 在該站候補 G，不是往上。
   測試：`test_direct_manager_uses_global_manager_assignment` 更名 `test_direct_manager_prefers_unit_assignment_over_global`（單位主管贏 → 軟刪後 G 在 RD 站候補），
   新增 `test_direct_manager_global_fallback_when_applicant_heads_own_unit`、`test_resolve_role_holders_unit_only_excludes_global`。HR 規格第 4 條改成規則、「已知限制」該條刪除。
2. **差異 6 收掉**：`dept_membership_service` 抽出 `ensure_solid_membership(user, unit)`、新增 `reconcile_dept_manager(manager, unit, operator) -> bool`
   （active 持有者＝{manager} 時只做三個 no-op 安全操作：SOLID membership、`DEPT_MEMBER` ensure、`DEPT_EMPLOYEE` revoke-if-active，回 False；否則 `set_dept_manager()` 回 True）；
   `sync_dept_roles()` 第二迴圈改呼叫它。測試 `test_reconcile_dept_manager_sets_manager_then_is_a_no_op`（第二次呼叫 `session.dirty` 無兩表物件、`deleted_at`／`updated_at`／count 不變）、
   `test_reconcile_dept_manager_replaces_previous_manager`、`test_ensure_solid_membership_only_touches_membership`。
3. CLAUDE.md 引擎行為表該句同步改寫。

驗收（憑證接 `/opt/tmp/verify/20260905-role-unit-phase4.log` 尾）：四檔 78 passed（hr_lookup 22／dept 7／task_authorizer 25／formadapter 24）；守恆檢查綠（108 表／1816 欄）；
GHTRAVEL 實流程 G1／G2 與第 4 期一字不差，**另加 G1x**：晧志遠（GM）插一筆全企業 `DEPT_MANAGER`、`assigned_at` 早 30 天，翎柏瑞 30 萬的直屬主管與核決人仍是燁凱文（修前會變成晧志遠），22/22 PASS；
`--sync-dept-roles` 連跑兩次三家全 0，`user_role_assignments`／`user_unit_memberships` 的 `id|is_deleted|deleted_at|updated_at` 雜湊與 4a 前完全一致（修前每跑一次主管的 `DEPT_EMPLOYEE` 列 `deleted_at`／`updated_at` 都會變）。
不重跑全量（複審裁示）。
