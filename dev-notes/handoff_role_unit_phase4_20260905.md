# 交接補篇：PF-247 第 4 期（主管來源統一）→ 新 session 執行（2026-09-05，第 1～3 期執行 session 撰寫）

> 給接手第 4 期的新 session。原交接檔 `dev-notes/handoff_role_unit_20260905.md` 的流程與坑仍全部有效，本篇只補「前四期做完之後才知道的事」。
> 設計文件 `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md` 第十一節有每一期的差異清單與複審結論，**第 4 期照 3.5 改寫版＋第六節第 4 列派**，不要用 3.5 原版（已作廢）。
> 原設計 session 照舊複審；每期完成後停下來回報 Ethan。

## 一、先讀（順序）

1. `CLAUDE.md`（引擎行為表已有「簽核者＝角色@單位」一列；PERM-03、TENANT-02、「跑測試」、「特定代理」段的模組 import 規則）
2. `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md` 全文，重點 3.2、3.5（改寫版）、第六節第 4 列、第十一節（四期差異＋複審）
3. `dev-notes/handoff_role_unit_20260905.md`（每期固定流程、第三節的坑）＋本篇
4. 前幾期 spec 當範本：`/opt/tmp/codex/20260905-pf247-phase{1,2,3,5}-spec.txt`（結構、規範貼法、測試要求寫法；第 2 期的「現況表」寫法最適合第 4 期）
5. `dev-notes/HR_LOOKUP_NODE_SPEC.md`（規則 3～7 要改寫）、`docs/manual/04_form_workflow/hr_lookup_node.md`、`docs/manual/03_org_setup/` 任職卡頁

## 二、前四期落地的介面（第 4 期會用到的）

| 東西 | 位置 | 要點 |
|---|---|---|
| `resolve_user_unit(user_sc, org_sc, today=None) -> str\|None` | `backend/app/services/unit_resolver.py` | 3.2 的唯一實作：SOLID membership → primary 快照 → 最早 start_date → PRIMARY 任職卡 → None |
| `get_unit(sc, org)`／`get_unit_ancestor_codes(sc, org)`（[父…根]）／`get_unit_descendant_codes(sc, org)` | 同上 | 全部同 org、未刪除；起點不存在回 None／[] |
| `resolve_role_holders(role_sc, org, unit_sc=None, include_descendant_units=False, today=None) -> list[str]` | 同上 | (角色, 單位) 持有者，含全企業指派（unit NULL）；順序 assigned_at；JOIN User 啟用未刪、`is_valid_on(today)`。**第 4 期 `resolve_direct_manager()` 找 `DEPT_MANAGER@U` 就用它** |
| `org_local_today(org)`／`org_local_now(org)`（第 5 期加） | 同上 | 企業當地日／當地時間（naive） |
| 授權端 `task_authorizer.resolve_acting_identity()` | `modules/form_workflow/services/task_authorizer.py` | 回 `{'via','delegator_secure_code','acted_as_role_code'}`；`_match_identity()` 順序：ROLE／DEPARTMENT 先看角色@單位（直接持有／全企業／非 POSITION 套圈）→ 缺席順位（副主管永遠、代理人僅主管缺席）→ 快照。**第 4 期不碰它** |
| handler `_resolve_assignee_spec()`／`_role_spec_data()`／`_apply_self_target()` | `modules/form_workflow/services/node_handlers/formadapter_handler.py` | 讀 config `unit_scope`／`unit_secure_code`／`unit_levels_up`／`absence_fallback`／`self_target_action`，寫 `result.data` 的 `assignee_*` key。**第 4 期不碰它** |
| `FwApprovalRecord.acted_as_role_code` | `modules/form_workflow/models/approval_record.py` | 第 3 期加的欄位，**bpserv 要手動 ALTER**（見第五節） |
| `GET /api/workflows/data/units`、`/data/roles` 帶 `role_type` | `modules/form_workflow/api/workflows.py` | 設計器用 |

**第 4 期的 `resolve_direct_manager(user_sc, org_sc, today=None)` 放 `unit_resolver.py`**（設計 3.5 改寫版明寫），回傳形狀由 spec 定（建議 `dict|None`：`manager_secure_code`、`unit_secure_code`、`unit_name`、`levels_up`），
OpHrLookup 的 `hr_direct_manager*` 與核決鏈都改吃它；副主管、代理人**不進**推導（那是簽核授權的缺席順位）。

## 三、第 4 期要動的檔案與現況行號（2026-09-05 19:15 盤點，動工前 `grep -rn direct_manager` 重新確認）

| 檔案 | 現況 | 處置（依 3.5 改寫版） |
|---|---|---|
| `modules/form_workflow/services/node_handlers/hr_lookup_handler.py` | 第 49～50 行輸出鍵清單含 `direct_manager`／`direct_manager_name`；**第 195 行** `manager = self._get_active_user(position.direct_manager_secure_code)`；**第 292 行**與**第 320 行**核決鏈沿 `position.direct_manager_secure_code` 往上 | 三處改呼叫 `resolve_direct_manager()`；核決鏈沿祖先單位主管；主管沒有有效任職卡視為上限 0 繼續往上（不再中止）；新增輸出 `hr_direct_manager_unit`／`hr_direct_manager_unit_name`／`hr_approver_unit`／`hr_approver_unit_name` |
| `backend/app/models/employee_position.py` | 第 82 行 `direct_manager_secure_code` 欄位、第 116 行 relationship、第 158 行 `get_manager_chain()`（**全專案無其他呼叫者**，可刪）、第 198 行 `to_dict` 的 `direct_manager_id`；`dotted_line_manager_secure_code`（第 90 行）**不動** | 移除欄位、relationship、`get_manager_chain()`、`to_dict` 兩個 key（`direct_manager_id` 與 `direct_manager` 子物件） |
| `backend/app/web/positions.py` | 第 91／131 行（create）、第 197／228 行（edit）讀寫 `direct_manager_secure_code` | 移除 |
| `backend/app/templates/pages/positions/create.html` 第 87～91 行、`edit.html` 第 83～87 行 | 直屬主管 select | 移除 |
| `backend/app/templates/pages/positions/view.html` 第 74～76 行、`list.html` 第 63～64 行 | 顯示 `position.direct_manager` | 移除或改顯示部門推導結果（spec 定；建議 view 頁顯示「直屬主管（依部門推導）」＋名字，list 頁拿掉欄） |
| `backend/app/web/hostconfig.py` 第 344 行 | 清理對照表 `('employee_positions', 'direct_manager_secure_code', 'set_null')` | 移除該列 |
| `scripts/seed_test_companies.py` | 第 776 行 `_direct_manager_usernames()`、第 812 行 `assign_direct_managers()`（第 844 行寫指標）、第 898／927 行兼任與代理職位複製指標、第 1130 行呼叫 | 改成：`is_unit_head=True` 者指派 `DEPT_MANAGER@unit`＋`user_unit_memberships(SOLID)`，其他人 `DEPT_MEMBER`＋`DEPT_EMPLOYEE@unit`；提供 `--sync-dept-roles` 冪等補種。**`_ensure_dept_membership()` 是 `backend/app/api/organizational_units.py` 的私有函式**（第 83～130 行），要嘛抽成 service 讓 seed 與 API 共用，要嘛 seed 內呼叫它（API 模組 import 到 seed 腳本可行但醜）——spec 要明講選哪個，不要讓 codex 複製一份 |
| dev 庫 | 欄位還在 | `ALTER TABLE employee_positions DROP COLUMN direct_manager_secure_code;` 然後 `bash scripts/check_schema_drift.sh` 必須綠（守恆檢查會抓 model 與 DB 不一致） |
| `dev-notes/HR_LOOKUP_NODE_SPEC.md` | 規則 3～7 寫任職卡指標 | 改寫成部門推導 |
| `docs/manual/04_form_workflow/hr_lookup_node.md`、`docs/manual/03_org_setup/`（任職卡頁） | 有「直屬主管」欄位說明 | 改寫；`mkdocs build --strict` 與 `scripts/docs_impact.py` 必跑 |
| `backend/tests/test_hr_lookup_node.py` | 第 152 行起用 `OrganizationalUnit`＋`EmployeePosition(direct_manager_secure_code=...)` 建測資 | 改成建 `DEPT_MANAGER@unit` 指派；增案：部門推導、本人是主管往上、職缺往上、無任職卡主管視為 0 |
| `scripts/examples/provision_hr_lookup_demo.py` | 不寫指標（已確認無 `direct_manager` 引用） | 不動 |

**沒有其他地方引用 `direct_manager_secure_code`／`get_manager_chain`**（2026-09-05 全專案 grep），`dotted_line_manager_secure_code` 留著。

## 四、驗收材料現況

### GHTRAVEL（seed 企業，第 4 期主戰場）

- 人資結構：`employee_positions` 22 筆（21 筆有 `direct_manager_secure_code`）、`user_role_assignments` 帶單位者 **1** 筆、`user_unit_memberships` **1** 筆、`work_schedules` 1 張
  → **部門角色幾乎是空的**，第 4 期 seed 對齊（`--sync-dept-roles`）跑完後應變成每人 `DEPT_MEMBER`＋`DEPT_EMPLOYEE`、部門主管 `DEPT_MANAGER`，再驗 `resolve_direct_manager()` 與舊指標結果一致
- 示範流程「差旅費申請（人事取值示範）」published `NfrmHdR6pVWLo2L2eCttCA`（mapping `MTz1S7Kc_uFCCMcP4ibhrC`，流程模板 `q1lfu30j8rQW4xwT7AlbUp`，2026-09-05 重發行過）；
  對照組憑證 `/opt/tmp/verify/20260902-hr-lookup-node.log`：領隊翎柏瑞（quick-login `oTBMqW0roaniN3UFhyKmZh`，L200）30 萬 → 燁凱文（L500）、500 萬 → 霄雅慧（L700）；
  10 億 → 找不到核決人 → PF-226 退回（`/opt/tmp/verify/20260905-pf226.log`）。**第 4 期重種後三組結果必須一字不差**
- 送單：`POST /api/form-center/submit`，body `published_secure_code`＋`subject`＋`form_data`（`amount`、`purpose`）

### BELUGA（手動企業，第 1～3、5 期主戰場）

- 已發行測試流程：`PF247_P2_A`（現為 `APPLICANT_UNIT`＋`escalate_or_self`，published `Mf7MSqu4IsXrmJBWsbKBfg`；舊 `H6FEV2Wkb4AKiIFdZW-z1g` Suspended）、
  `PF247_P2_B`（舊式 DEPARTMENT 資訊群，`eEIyQu9jLYNXurC66F9hlw`）、`PF247_P2_C`（`DEPT_MEMBER@資訊群` 指定單位，`mNVXMd-ouApXyODmCMdh2w`）；
  佈建腳本 `/opt/tmp/verify/pf247/provision_phase2_flow.py --org BELUGA --apply`（冪等，重跑會 bump revision 重發行）
- 測試單主旨都以 `PF247-P` 開頭，全部已簽掉或退回；測試指派／成員關係／請假列**零殘留**（標記 `PF247-P1-TEST`／`PF247-P5-TEST`）
- 常用 sc：企業 `_9c8TewkRkCBEf3XsUdqeF`；單位 行銷部門 `MmDNACxWEa39NW-7XrTEtg`、資訊群 `pzWlEAZ5TSwEvc-3gMy7OX`、軟體部 `2HqhV5jLzwPPx-PBqW4CHP`；
  角色 `DEPT_MANAGER` `KyllpLHcFzQ-t6wF1iq7uP`、`DEPT_MEMBER` `E6Dc6iB81l4tQUm0DCdNJZ`、`DEPT_DEPUTY` `Krs9B3CCWFxAR8M2kxzAzO`、`DEPT_PROXY1` `CKgknA7DpYCNBBb-7Wc73o`、`DEPT_PROXY2` `IU3XKlQ5CLbavAb3Mvv4Db`；
  帳號 ethanyu（副主管@行銷）`FhsmtyPjsnXYotN-iz_Q-X`、aaaa（代理一）`9De0TEngQTU35rbJn7q2Uk`、ssss（代理二）`tfVJFhivEDWoPQSwGqUUqy`、user（成員@行銷，SOLID）`EpFwno0dDyYhTIaAn8Tqb_`、
  shen.qing.zhe（無部門）`unSuAD3AonAoTQ8TDa7ipd`、admin-ethanyu（ORG_ADMIN）`jIYEQ-_lZMZNBkVy-hijal`
- **BELUGA 沒有預設班表**：`schedule_adjustments.original_periods` 會是 `[]`，時段級請假在這家企業一律等於整天（設計文件第十一節第 5 期記錄）

### `/opt/tmp/verify/pf247/` 工具

| 檔案 | 用途 |
|---|---|
| `assign.sh add\|del <user_sc> <role_sc> <unit_sc>` | 帶標記 `PF247-P1-TEST` 的角色指派（含 `created_at`／`updated_at`） |
| `membership.sh add <user_sc> <unit_sc>\|del-all` | 帶標記的 SOLID 成員關係 |
| `phase1_seed.sql`／`phase1_cleanup.sql`／`phase1_matrix.py`／`phase1_http.sh` | 合成佇列列＋HTTP 200／403 矩陣（授權端） |
| `provision_phase2_flow.py`、`phase2_flow.sh`、`phase3_flow.sh`、`phase5_flow.sh` | 實流程：送單 → 等 executor → 比對 `result.data` → 詳情 200／403 → approve |
| `phase2_published.txt` | A／B／C 的 published／wf／mapping sc |

腳本內的 helper（`submit`、`wait_fa`、`dump`、`check`、`approve`、`token`）可直接複製到第 4 期腳本；`approve` 的 payload 是
`{"decision":"approved","selected_edges":[...],"selected_option_value":"approved","comment":...}`。

## 五、bpserv 部署清單（第 4 期做完一起上）

1. `push github` → bpserv `sudo bash /opt/BeakPlatform/scripts/install.sh --update`
2. **手動 SQL**（create_all 不補也不刪欄位）：
   ```sql
   ALTER TABLE fw_approval_records ADD COLUMN IF NOT EXISTS acted_as_role_code VARCHAR(50);   -- 第 3 期
   ALTER TABLE employee_positions DROP COLUMN IF EXISTS direct_manager_secure_code;            -- 第 4 期
   ```
3. DemoSOC 沒有任職卡也沒有部門角色（soc1 只有全域角色），第 1～3 期的行為對它是「無單位範圍的 ROLE 照舊」，不需要補資料；要驗角色@單位得先在 DemoSOC 建部門與指派
4. 沒有新選單、沒有新 permission code、沒有新 `.env` 鍵

## 六、前四期累積、原交接檔沒有的坑

- **Bash 工具的 `cd` 會跨呼叫持續**：某次 `cd modules/.../js && grep ...` 之後，下一個呼叫的相對路徑（`modules/...`、`dev-notes/...`）全部 No such file。
  一律用絕對路徑，或每個指令開頭 `cd /opt/BeakPlatform-dev`
- `git diff --check` 要在 repo 內跑（cwd 漂到 `/opt/tmp` 會印一整頁 usage）
- **`_match_identity()` 的順序是刻意的**：快照命中放在角色@單位與缺席順位之後，否則副主管的 `acted_as_role_code` 永遠是 NULL（第 3 期驗收踩到）。放行集合不受順序影響
- 設計器「直接儲存流程」只在右側節點面板開著（`currentEditingNodeId`）時收集 modal 值；用 chrome-devtools 模擬要先 `showNodeInfo(node)` 再 `openFormAdapterModal(id)`，`window.cy` 是 cytoscape 實例
- chrome-devtools 登入：`new_page` 開 `/dev/quick-login`（用 `isolatedContext` 開新 session），`evaluate_script` 內 `fetch('/beakplatform/dev/quick-login', {method:'POST', body: JSON.stringify({user_id})})`，之後 `navigate_page`；
  表單中心的 Alpine 元件用 `Alpine.$data(document.querySelector('[x-data="formCenterManager()"]'))` 取，`openApprovalModal(item)`／`openReadForm({secure_code})` 直接呼叫
- `POST /api/calendar/events` 建請假：`{"calendar_kind":"PERSONAL","event_type":"LEAVE","title":...,"all_day":true,"start":"YYYY-MM-DD","end":"YYYY-MM-DD","visibility":"BUSY"}`，要 CSRF；同步寫出的 `schedule_adjustments` 列與事件同生共滅（軟刪除）；
  同人同日同型別有唯一約束，人工列要用 UPDATE 復活既有列而不是 INSERT
- 發行：`POST /api/mappings/<mapping sc>/publish`（CSRF 從 `/dashboard` meta），回 `data.secure_code` 是新 published sc、舊的變 Suspended；設計器儲存已 bump revision，不必手動 +1
- 全量測試約 23 分鐘，`nohup setsid` 起來後 shell 印 `[1]+ Done` 是假的（setsid fork），看 `pgrep -af "[p]ytest -q"`；撞車就 `pkill -f "[v]env/bin/python -m pytest"`、重建 `beakplatform_test`、單獨重跑
- 基準（2026-09-05 第 5 期後）：見 BBN #5400 第 5 期追記的全量數字（第 3 期後是 1074 passed／1 failed／2 skipped）；已知非綠只有 `test_admin_required_for_admin`（PF-34）

## 七、第 5 期結果（本 session 最後一期，2026-09-05 19:35 完成、待原 session 複審）

- 主管當日請假算缺席：`ScheduleService.is_on_leave(user, local_dt)`（LEAVE 列時段判定，`[]`／NULL＝整天）、`unit_resolver.org_local_now()`、
  `task_authorizer._unit_manager_present()`＝任一主管未請假才在職、handler 快照 `manager_vacant` 同步；測試 16 案；憑證 `/opt/tmp/verify/20260905-role-unit-phase5.log`
- 第 4 期會碰到的相關點：`resolve_direct_manager()` 找主管**不要**套用請假（核決鏈只認主管在不在職缺，請假是簽核授權層的事；設計 3.5 改寫版第 4 條）
- 三個驗收時才弄清楚的事實（寫在設計文件第十一節第 5 期記錄）：沒班表的企業時段級請假等於整天；單子在主管請假期間進關卡則代理人已在快照內、銷假後仍可簽（快照永不縮減）；
  `POST /api/calendar/events` 的回應形狀是 `{success, event:{secure_code,...}, delegation_hint}`，**不是** `data.secure_code`
- 複審結論與後續（原 session 填）：見設計文件第十一節「第 5 期複審」與 BBN #5400 追記
