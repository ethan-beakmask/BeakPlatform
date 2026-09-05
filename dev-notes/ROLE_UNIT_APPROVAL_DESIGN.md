# 簽核者＝角色@單位：「部門也是一種角色」的落地設計（2026-09-05 草案，待 Ethan 審）

> 狀態：**設計草案，未派工**。審過後依第六節分期派 codex。
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

### 3.5 直屬主管來源統一（OpHrLookup，第四期）

`hr_direct_manager` 改為：`EmployeePosition.direct_manager_secure_code` **有值＝明示覆寫，維持**（矩陣組織要用）；
**空值→由部門推導**：申請人單位 U 的 `DEPT_MANAGER@U` 持有者；申請人自己就是 U 的主管時往上一層取 parent 的主管；
一路到根都沒有→空字串（`hr_direct_manager_found='false'`）。核決鏈（3～7 條規則）沿同一推導往上走。
新增輸出 `hr_direct_manager_unit`／`hr_direct_manager_source`（`explicit`／`unit`）。
`seed_test_companies.py` 同步改：`is_unit_head=True` 的人**也指派 `DEPT_MANAGER@unit`**、其他人 DEPT_MEMBER＋DEPT_EMPLOYEE@unit，
讓兩套真相從此一致；既有三家範例企業用同一支腳本補（冪等）。

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
| 4 主管來源統一 | 3.5：OpHrLookup 推導、seed 對齊、`HR_LOOKUP_NODE_SPEC.md` | `hr_lookup_handler.py`、`scripts/seed_test_companies.py`、`scripts/examples/provision_hr_lookup_demo.py`（若有寫死指標） | `test_hr_lookup_node.py` 增案；GHTRAVEL 重跑 30 萬／500 萬對照組 |
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

## 九、不在本設計內（已另存 PF-246）

會簽決議型式（全員／任意／人數／比例）、滑步、逾時升級到上層、USER 型別指定帳號停用後的處置。

## 十、BBN

本設計待辦：PF-247（見本檔 commit 後由主 Claude 建卡並回填代號）。PF-245（DEPARTMENT 型）併入第 2 期，卡上兩個選項作廢。
