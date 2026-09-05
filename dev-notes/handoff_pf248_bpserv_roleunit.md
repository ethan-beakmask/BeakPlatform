# PF-248：bpserv 上實測角色@單位（一次性交接，2026-09-06 原 session 寫，codex 冷讀補洞後版本）

> PF-247 已部署 bpserv（GitHub `056a052d`＝dev `09014ce7`），但 DemoSOC 沒有部門、沒有單位角色指派、沒有任職卡，
> 部署驗收只跑了「無單位範圍的 ROLE 舊路徑」。本卡把角色@單位、缺席順位、直屬主管推導在 bpserv 跑一次。
> bpserv 憑證與登入方式見 `CLAUDE.md`「bpserv 測試機」表；本檔只放本卡專用的識別碼與指令。

## 一、DemoSOC 現成識別碼（2026-09-06 00:15 查 bpserv DB）

| 東西 | 值 |
|---|---|
| 企業 | code `DEMOSOC`，sc `ugRNno6lA97ZicqIbBvBEb` |
| soc1（EMPLOYEE，持 SECURITY_STAFF＋SOC_SUPERVISOR） | `fQcm2wcc7007tL615tat-g` |
| admin-soc1（ORG_ADMIN） | `kw1FAtbOQzgCVsZvCNVemo` |
| 角色 `DEPT_MANAGER`／`DEPT_DEPUTY`／`DEPT_PROXY1`／`DEPT_PROXY2`（POSITION） | `6rpOC-BxWK5SVs0ajB4UbF`／`374xd6XIhjncJraSJmm3M9`／`JFJhBaHsGA7J6rbINRNhF6`／`yoAMaFd6fMNCyG9zw_EGoo` |
| 角色 `DEPT_MEMBER`／`DEPT_EMPLOYEE`（ROLE） | `bwn7r14e7pdzM8eRS2umAM`／`sGukffDex1eParq2jLF4H8` |
| 單位 | 只有一個社群「外部廠商專用群組」`kpqCbNKQHzwZyWYdmWImOR`；**沒有任何部門** |
| 既有流程模板／配對 | API Key 申請核發流程 `_RFYmn7Jhaix4Dyb1nb6sI`（mapping `ynE69G9SxFxnM3meLhCHJ8`，表單 `Owh64l06bgZClnqGU3Xx7r`）；三條資安事件處置流程不要動 |

## 二、最小測資（兩個 EMPLOYEE 就能跑 #1 與 #7；#2／#3／#9 要再多建帳號當副主管／代理人）

部門 D（新建）；soc1 加入 D 並設主管；新建 EMPLOYEE `pf248member` 加入 D 當成員兼申請人。**部門成員與主管的三支 POST 只收 EMPLOYEE**（PERM-03），ORG_ADMIN 不能當成員。

```bash
BASE=http://192.168.0.66:8000/beakplatform
curl -s -c cj_admin.txt -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"account":"admin-soc1@demo-soc.example","password":"DemoSoc-Staff2026#"}' -o /dev/null -w 'http=%{http_code}\n'   # 500 就重試一次
TOKEN=$(curl -s -b cj_admin.txt -c cj_admin.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
H=(-b cj_admin.txt -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN")

# 1. 建帳號（必填四項＋email；password 留空會寄暫時密碼到 lionsecbot@gmail.com 且 must_change_password=true）
curl -s "${H[@]}" -X POST "$BASE/api/users/" -d '{"native_name":"PF248成員","english_name":"PF248 Member","username":"pf248member","employee_id":"PF248001","email":"pf248member@demo-soc.example"}'
#    讓它能直接登入（測試機做法，未在本 session 實打；正規路徑是照 CLAUDE.md AUTH-04 走 POST /auth/change-password）：
#    sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 sudo -u postgres psql -d beakplatform -tA <<'SQL'
#    UPDATE users SET password_hash=(SELECT password_hash FROM users WHERE username='soc1'), must_change_password=false WHERE username='pf248member';
#    SQL
#    之後 pf248member 的密碼＝soc1 的密碼。

# 2. 建部門（body 欄位：name / code / unit_type / parent_id，來自 organizational_units.py create 端點 docstring）
curl -s "${H[@]}" -X POST "$BASE/api/units/" -d '{"name":"PF248測試部","code":"PF248DEPT","unit_type":"DEPARTMENT","parent_id":null}'
#    → 記下回傳的 secure_code 當 UNIT
# 3. 加成員（body {"user_id": users.secure_code}）、設主管（同 body；position 可為 manager/deputy/proxy1/proxy2）
curl -s "${H[@]}" -X POST "$BASE/api/units/$UNIT/members" -d '{"user_id":"fQcm2wcc7007tL615tat-g"}'
curl -s "${H[@]}" -X POST "$BASE/api/units/$UNIT/members" -d '{"user_id":"<pf248member sc>"}'
curl -s "${H[@]}" -X POST "$BASE/api/units/$UNIT/leadership/manager" -d '{"user_id":"fQcm2wcc7007tL615tat-g"}'
```

驗指派有沒有進去（heredoc，單行 `-c` 會被遠端 shell 拆引號）：

```bash
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 sudo -u postgres psql -d beakplatform -tA <<'SQL'
SELECT u.username, r.code, ou.name FROM user_role_assignments a JOIN users u ON u.secure_code=a.user_secure_code JOIN roles r ON r.secure_code=a.role_secure_code LEFT JOIN organizational_units ou ON ou.secure_code=a.unit_secure_code WHERE a.org_secure_code='ugRNno6lA97ZicqIbBvBEb' AND a.unit_secure_code IS NOT NULL AND a.is_deleted=false ORDER BY 1,2;
SQL
```

## 三、流程

用設計器（chrome-devtools 登入法在 CLAUDE.md bpserv 表）新建流程「PF248 角色@單位」：Start → FormAdapter → End。
FormAdapter modal：簽核者類型「指定角色」＝部門主管、單位範圍「申請人所屬單位」、「申請人本人就是簽核者時」留預設、缺席接手勾選；決策用預設（核准／駁回）。
配對：配對管理新建，表單用「API Key 申請」`Owh64l06bgZClnqGU3Xx7r`（form_data 的欄位鍵先查
`SELECT jsonb_path_query_array(schema,'$.components[*].key') FROM fw_form_templates WHERE secure_code='Owh64l06bgZClnqGU3Xx7r';`），發行：

```bash
curl -s "${H[@]}" -X POST "$BASE/api/mappings/<mapping sc>/publish" -d '{}'      # 回 data.secure_code＝published sc
```

dev 的佈建腳本 `/opt/tmp/verify/pf247/provision_phase2_flow.py --org <CODE> --apply` 是靠 quick-login，bpserv 沒有，**不要直接拿來跑**；只參考它的 `build_graph()` 組 FormAdapter config 的寫法。

## 四、跑與判定

```bash
# 申請人送單（pf248member 登入後）
curl -s -b cj_member.txt -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN_M" -X POST "$BASE/api/form-center/submit" \
  -d '{"published_secure_code":"<published sc>","subject":"PF248 #1","form_data":{...}}'
# 等 executor（gunicorn 進程內撿，約 10～15 秒）後查佇列
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 sudo -u postgres psql -d beakplatform -tA <<'SQL'
SELECT q.secure_code, q.status, q.result->'data'->>'assignee_role_code', q.result->'data'->>'assignee_unit_name', q.result->'data'->'assignees' FROM fw_node_execution_queue q WHERE q.node_type='FormAdapter' ORDER BY q.created_at DESC LIMIT 3;
SQL
# 判定（200／403）
curl -s -b cj_soc1.txt  -o /dev/null -w 'soc1=%{http_code}\n'  "$BASE/api/form-center/pending-tasks/<佇列 sc>"
curl -s -b cj_admin.txt -o /dev/null -w 'admin=%{http_code}\n' "$BASE/api/form-center/pending-tasks/<佇列 sc>"
# 簽核（CSRF 帶簽核者自己的 token）
curl -s -b cj_soc1.txt -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN_S" -X POST "$BASE/api/form-center/pending-tasks/<佇列 sc>/approve" \
  -d '{"decision":"approved","selected_option_value":"approved","comment":"PF248"}'
```

| # | 情境 | 期望 |
|---|---|---|
| 1 | pf248member 送單 | 佇列 `assignee_role_code=DEPT_MANAGER`、`assignee_unit_name=PF248測試部`、`assignees=[soc1]`；soc1 200、admin-soc1 403 |
| 7 | 單在關卡上，`DELETE /api/units/$UNIT/leadership/manager`（或改指派）換人當主管 | 新主管詳情 200、soc1 403（角色是活的，不看快照） |
| 直屬主管 | 若要驗人事取值：DemoSOC 沒有任職卡與職等，`hr_approver` 會是空；只驗 `hr_direct_manager` 可在流程加 OpHrLookup 節點（`target_source=applicant`，不開 approver_mode）→ 變數 `hr_direct_manager` 應＝soc1、`hr_direct_manager_unit=PF248DEPT` |

記錄：`SELECT approver_name, action, acted_as_role_code FROM fw_approval_records WHERE workflow_instance_secure_code='<wi sc>';`

## 五、收尾

- 測試單簽掉（上面 approve）；流程模板與配對可留（改名帶 PF248 前綴）或 `DELETE /api/mappings/<sc>`
- 部門：`DELETE /api/units/$UNIT`（`_remove_dept_membership` 會軟刪該部門的所有 DEPT_* 指派與成員關係）；或只拆成員 `DELETE /api/units/$UNIT/members/<user sc>`
- 帳號 pf248member：`DELETE /api/users/<sc>`（軟刪除）
- 憑證固定檔名 `/opt/tmp/verify/<YYYYMMDD>-pf248-bpserv-roleunit.log`，記：指派查詢輸出、佇列 `result.data` 三欄、每個帳號的 200／403、簽核記錄列
