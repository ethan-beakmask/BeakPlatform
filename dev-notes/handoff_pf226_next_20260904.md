# 交接：PF-235／PF-71 已完成，下一步 PF-226（2026-09-04 19:50）

> 寫給下一個 session。本檔是一次性的；每個 session 都會用到的事實已歸位到 `CLAUDE.md`
> （假日表與預設班表段、特定代理段、bpserv 部署狀態列、平台層延後 import）。

## 一、現況

| 項目 | 狀態 |
|---|---|
| dev（`/opt/BeakPlatform-dev`） | HEAD `ea6043d5`：PF-235（假日表＋國別設定＋預設班表）`26b48416`、PF-71（特定代理）`ea6043d5`，工作區乾淨 |
| GitHub 過濾鏡像 | 本 session 收尾 `push both` 後含 PF-235 與 PF-71（推送前是 `e63bc7eb`＝只含 PF-235） |
| bpserv（`192.168.0.66:8000`） | 已部署 PF-235（GitHub `e63bc7eb`），**尚未部署 PF-71**；DemoSOC 留有已發佈的 2026 政府假日表 `B6c_XrYkLxGU4dhzEpe34u` |
| BBN 待辦 | PF-235、PF-71 已 `completed`；PF-69 剩 DEPARTMENT 型（另建「沒回答」卡）；PF-226 未動 |
| 憑證 | `/opt/tmp/verify/20260904-pf235.log`、`20260904-pf235-bpserv.log`、`20260904-pf71.log`、`20260904-pf235-fullsuite.log`（1023 passed / 1 failed＝既知 PF-34） |

## 二、待辦順序（Ethan 2026-09-04 第 1 次發言定案的次序：行事曆 → 代理人 → 流程設計）

### 1. bpserv 部署 PF-71（無 schema 變更，只要 `--update`）

本 session 實跑成功的指令（PF-235 那次，照抄）：

```bash
LOG=/opt/tmp/verify/$(date +%Y%m%d)-pf71-bpserv.log
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 'sudo bash /opt/BeakPlatform/scripts/install.sh --update' 2>&1 | grep -iE "error|fail|4/4|完成" | tee -a $LOG
# 驗證：admin-soc1 登入後建立頁要有 allowed_form_templates 多選
BASE=http://192.168.0.66:8000/beakplatform; CJ=/opt/tmp/verify/pf71-bpserv-cj.txt; rm -f $CJ
curl -s -c $CJ -X POST "$BASE/auth/login" -H 'Content-Type: application/json' -d '{"account":"admin-soc1@demo-soc.example","password":"DemoSoc-Staff2026#"}' -o /dev/null -w 'login http=%{http_code}\n'
curl -s -b $CJ "$BASE/delegations/create" | grep -c 'allowed_form_templates'     # 期望 >= 1
```

做完把 `CLAUDE.md` bpserv 表的「部署狀態」列前綴一段（格式照現有），並在 BBN #5122 追記。

### 2. PF-226：動態簽核人為空時的流程行為（先實測、再定案、再實作）

原子 `note_get(5377)`。要驗的假設：`OpHrLookup` 找不到核決人時把 `hr_approver` 寫成空字串，
若設計者沒接 Branch 直接接簽核節點「動態（從變數取）」，`FormAdapter._resolve_assignees('DYNAMIC')`
（`modules/form_workflow/services/node_handlers/formadapter_handler.py` 約第 595 行）回 `[]`，
佇列項 `result.data` 會是 `assignee_type='DYNAMIC'`、`assignees=[]`。依 `task_authorizer._identity_matches()`
的邏輯（`assignee_type` 有值、`assignees` 空、非 ROLE → 回 False），**預期症狀是「任務永遠 WAITING、沒有任何人能簽、不報錯」**——
但這只是讀碼推論，必須實測。

實測材料（範例企業 GHTRAVEL 已由 `scripts/examples/provision_hr_lookup_demo.py --org GHTRAVEL --apply` 佈建「差旅費申請（人事取值示範）」）：

```bash
BASE=http://192.168.0.16:7000/beakplatform
# 領隊翎柏瑞（L200）quick-login
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' -d '{"user_id":"oTBMqW0roaniN3UFhyKmZh"}'
TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
# 金額 10 億 → hr_approver_found=false（規格 dev-notes/HR_LOOKUP_NODE_SPEC.md）；form_data 的欄位鍵先用
#   curl -s -b cj.txt "$BASE/api/form-center/forms/ANHfz8A6yeY8zl-k7uJ0XA" 或直接查 fw_form_templates.schema 確認
curl -s -b cj.txt -X POST "$BASE/api/form-center/submit" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d '{"published_secure_code":"ANHfz8A6yeY8zl-k7uJ0XA","subject":"PF-226 測試 10 億","form_data":{"amount":1000000000}}'
```

送出後看佇列與變數（表名與欄位名見 CLAUDE.md「每個 session 都會撞一次的欄位名」）：

```sql
SELECT q.node_type, q.node_id, q.status, q.result->'data'->>'assignee_type' AS atype, q.result->'data'->'assignees' AS assignees, q.created_at
FROM fw_node_execution_queue q JOIN fw_workflow_instances wi ON wi.secure_code=q.workflow_instance_secure_code
WHERE wi.form_instance_secure_code=(SELECT secure_code FROM fw_form_instances WHERE subject='PF-226 測試 10 億' ORDER BY created_at DESC LIMIT 1)
ORDER BY q.created_at;
SELECT name, value FROM fw_workflow_variables WHERE workflow_instance_secure_code=(SELECT workflow_instance_secure_code FROM fw_form_instances WHERE subject='PF-226 測試 10 億' ORDER BY created_at DESC LIMIT 1);
```

`form_data` 的欄位鍵已查過（`fw_form_templates.schema`，模板 `HR_LOOKUP_TRAVEL_DEMO` sc `dAPov4u7nYWvOsE7px3hUX`）：`amount`、`purpose`，上面的範例可以直接送。

三種情況的測資（冷讀審核補的，2026-09-04 19:55 從 dev 庫查出）：

| 情境 | 怎麼造 | 還原 |
|---|---|---|
| 整條主管鏈都不夠核決 | 申請人翎柏瑞（`oTBMqW0roaniN3UFhyKmZh`）送 `amount: 1000000000` | 不必 |
| 主管已停用 | 先 `UPDATE users SET is_active=false WHERE secure_code='yIVOrZiT0ltlPjtBm6o8mQ';`（直屬主管燁凱文），再送 `amount: 300000`（原本會派給他） | `UPDATE users SET is_active=true WHERE secure_code='yIVOrZiT0ltlPjtBm6o8mQ';` |
| 找不到職位 | 用沒有任何職位的員工帳號「晧管理」`hKMgscJK_YthC46KpstLeN`（`gh.admin@…`，`employee_positions` 0 筆）quick-login 送件；若送件 403，先看該帳號有沒有表單中心的填寫權限，不要去改職位 | 不必 |

證據怎麼取（三種情境都一樣，寫進 verify log）：
1. SQL 看佇列項（上面那句）：`atype` 與 `assignees` 的實際值；
2. 預期簽核者 quick-login 後看待簽清單有沒有這張單：燁凱文 `yIVOrZiT0ltlPjtBm6o8mQ`、處長霄雅慧 `Jx4nMsw2S_tl2iVb7tcDlq`
   → `GET $BASE/api/form-center/pending-tasks`；再打 `GET $BASE/api/form-center/pending-tasks/<佇列 sc>` 看 200／403；
3. 流程管理頁（`/forms/instances`，ORG_ADMIN `S_m2bCV9HTkAKGbYzBaODr`）該實例的狀態與節點狀態。
「靜默無人可簽」的判準＝佇列 WAITING、`assignees=[]`、三個人都 403、流程管理頁沒有錯誤。

BBN 操作（下個 session 是帶 MCP 的 Claude）：讀 `note_get(5377)`；追記 `note_update(atom_id=5377, append_content='...')`；
結案 `note_task_status(ref='PF-226', status='completed')`；bpserv 部署 PF-71 後追記 `note_update(atom_id=5122, append_content='...')`。

要驗的三種情況（原子第 1 點）：找不到職位、主管已停用、整條主管鏈都不夠核決（10 億）。每種都把 queue 狀態、
待辦頁（quick-login 成處長霄雅慧或直屬主管燁凱文看 `GET /api/form-center/pending-tasks`）、`task_authorizer` 判定寫進
`/opt/tmp/verify/<日期>-pf226.log`。

定案選項（先問 Ethan，這是多方案）：(A) FormAdapter 對空 assignees 明確回 `error`（流程管理頁看得到）；
(B) 改派企業管理員角色當 fallback；(C) 兩者都做、由節點 config 選。實作後手冊
`docs/manual/04_form_workflow/hr_lookup_node.md` 常見問題要補實際症狀。

### 3. PF-69 剩餘：DEPARTMENT 型（等 Ethan 決定，已建「沒回答」卡）

現況：`_resolve_department_users()` 只讀 `users.primary_unit_secure_code`、不看 `user_unit_memberships`；
且部門調動不即時生效（刻意維持快照）。Ethan 2026-09-04 兩次被問都沒回答。**不要自己開工。**

## 三、本 session 驗證過、下個 session 會再用到的識別碼

| 用途 | 值 |
|---|---|
| BELUGA 企業預設班表 sc | `NQ0_14mKe-yNGcUmF6iptc`（PF-235 第一批種的 `DEFAULT`） |
| BELUGA 已發佈的 2026 政府假日表 sc | `vWXOCwWcnGtZB1IGxGHxkL`（22 筆，發佈到預設班表） |
| BELUGA 授權人（持 SECURITY_STAFF）ethanyu | quick-login `FhsmtyPjsnXYotN-iz_Q-X` |
| BELUGA 代理人（無資安角色）user@beluga.com | quick-login `EpFwno0dDyYhTIaAn8Tqb_` |
| BELUGA WAITING 的 OD 任務（ROLE=SECURITY_STAFF） | 佇列 sc `REYhGxsy_rqYlpVeAQHRxy`（OD-20260904-3D2C63FD） |
| 表單模板 SEC_IR_SOLO／API_KEY_REQUEST | `6cJ0m3-Ezw1f7I4zNUxSKs`／`5xiVlpEzd9Txv5wx-ZG_DY` |

**OD 案件不進表單中心待簽清單**（`fc_pending.py` 對 security category 分流），驗代理是否放行用詳情端點：
`GET /api/form-center/pending-tasks/<佇列 sc>` → 200（`user_role=approver`）或 403。`/api/open-defense/cases` 這條路徑不存在（404）。

## 四、本 session 踩到、下個 session 也會撞的三件事

1. **Claude Code harness 會以「記憶體不足」中止背景 Bash／Monitor**（`free` 顯示 free 1.1 GB 但 available 8 GB 時就會），
   今天中止了全量測試、等待迴圈、codex 派工各一次。長工作改用 `nohup setsid bash -c '...' > log 2>&1 &` 脫離 session，
   再用 Monitor 以 `until grep -q "^exit=" log; do sleep 20; done` 監看 log 尾行；Monitor 逾時（預設 5 分鐘）要重掛。
2. **codex 結尾撞 OpenAI「model at capacity」時 exit 1、沒有 `-o` 結果檔，但工作區的變更是完整的**（PF-235 第二批）。
   看 `git status` 與 stderr log 尾判斷完成度，自己驗收，不要重派（會在半成品上再做一次）。
3. **codex 在平台層 web 用模組層級 import 模組 model**，pytest 與 `import app` 都過但 flask 起不來（PF-71）。
   驗收時一律真的 `systemctl restart` 並等 `/auth/login` 回 200，不要只看測試。
