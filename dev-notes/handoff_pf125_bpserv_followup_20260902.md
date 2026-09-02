# 交接：bpserv 套用「合約效期依企業時區」修正並做 mutation 驗證（PF-125 後續）

> 建立：2026-09-02 08:20。前情：PF-125 走查（BBN atom 5216 的 2026-09-02 追記）在全新環境
> 抓到合約效期用 `date.today()`（伺服器 UTC 日期）判定的 bug，dev 已修並 push（commit `25c05fe5`，
> GitHub 過濾鏡像 `6811f693`）。**bpserv 上跑的還是舊碼**，本檔是把修正套到 bpserv 並用真實請求驗證的步驟。
> 本檔所有指令都是 2026-09-02 在本 session 實際跑過成功的，照抄即可；環境事實（IP、帳密、識別碼）以專案 CLAUDE.md 的 bpserv 表為準。

## 0. 前提

**在哪裡跑**：`ssh` 開頭的指令才是在 bpserv 上執行；其餘所有 `curl` 都在開發機 .16 跑、打 bpserv 的 URL（.16 在 EDL 白名單內，且 `/opt/tmp/verify/` 在 .16）。開工先：

```bash
mkdir -p /opt/tmp/verify; LOG=/opt/tmp/verify/$(date +%Y%m%d)-pf125-bpserv-tz-mutation.log
```

之後每段指令尾端接 `2>&1 | tee -a $LOG`（下面範例已寫好），登入與建合約的完整回應都要進 log。

- bpserv = `192.168.0.66`，SSH：`sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66`（sudo NOPASSWD）
- 平台 URL：`http://192.168.0.66:8000/beakplatform`（必帶 `:8000` 與前綴）
- bpserv **系統時鐘是 UTC**，`sudo -u postgres psql -d beakplatform -At -c "SELECT now() AT TIME ZONE 'UTC';"` 看伺服器現在日期
- 帳號（皆在 CLAUDE.md bpserv 表）：SYSTEM_ADMIN `admin@sys-1271967103b6` / `BpservTest2026Changed`；
  DemoSOC 員工 `soc1@demo-soc.example` / `DemoSoc-Staff2026#`（EMPLOYEE，持 SECURITY_STAFF）；企業 sc `ugRNno6lA97ZicqIbBvBEb`
- bpserv 沒有 quick-login，登入一律 `POST /auth/login` JSON（`{"account":..., "password":...}`，成功 200）

## 1. 套用更新

```bash
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 'sudo bash /opt/BeakPlatform/scripts/install.sh --update 2>&1 | tail -15; systemctl is-active beakplatform; cd /opt/BeakPlatform && sudo git log --oneline -1'
```

預期最後一行是 GitHub 鏡像的新 commit（`6811f693` 或更新）。`--update` 會 `git reset --hard` 再 restart 服務；
**重啟會殺掉正在跑的流程節點**，先確認 `SELECT count(*) FROM fw_node_execution_queue WHERE status='RUNNING';` 是 0。
不是 0 時：等 30 秒重查（正常節點幾秒內結束）；若同一筆 RUNNING 超過 10 分鐘就是已經死掉的殭屍（PF-125 走查當天所有節點都已 SUCCESS/CANCELLED，不會有真的在跑的），照樣 `--update`，事後 `UPDATE fw_node_execution_queue SET status='FAILED' WHERE id=<那筆>;`。
若 `.git/config` 的 PAT 已到期（read-only fine-grained，2026-10 初到期）會要 token：**向 Ethan 要新的 GitHub PAT**（repo `ethan-beakmask/BeakPlatform` 唯讀即可），不是 Forgejo token；貼給 `--update` 的互動提示即可，它會寫回 `.git/config`。

確認新碼已在：

```bash
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 'grep -n "def local_today" /opt/BeakPlatform/backend/app/utils/timezone.py /opt/BeakPlatform/backend/app/models/organization.py'
```

## 2. Mutation 驗證（先看得到壞、再看得到好）

原理：企業 DemoSOC 時區是 Asia/Taipei（出廠預設）。修正後合約「今天」＝台北日曆日，與伺服器 UTC 日期無關。
**判定邏輯**：更新已先做了，所以看不到舊碼壞掉的樣子；能證明修正生效的是 2c——「起日＝企業時區今天、但伺服器 UTC 日期還是昨天」的合約必須立刻有效。
這個條件在台北 00:00～08:00 自然成立（`TZ=Asia/Taipei date +%F` 與 `date -u +%F` 不同天就對了）。
**其他時段**改用 2d 的替代法：把 DemoSOC 的時區暫時改成 `Pacific/Kiritimati`（UTC+14，台北 10:00～24:00 之間它已是隔天），
用它的「今天」建合約，舊碼會判尚未生效（403）、新碼會放行（200）。2b 只是負案例（明天生效必須 403），證明日期比較沒被拿掉。

### 2a. 準備：把 DemoSOC 既有的兩份 open_defense 合約停用，只留一份可控的

以 SYSTEM_ADMIN 登入並取 CSRF（每次 restart 後 session 仍在，因為 production 用 redis session；失效就重登）：

```bash
BASE=http://192.168.0.66:8000/beakplatform; CJ=/opt/tmp/verify/cj_bpserv_sys.txt
curl -s -c $CJ -b $CJ -X POST "$BASE/auth/login" -H 'Content-Type: application/json' -d '{"account":"admin@sys-1271967103b6","password":"BpservTest2026Changed"}'
TOKEN=$(curl -s -b $CJ -c $CJ "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3); echo ${#TOKEN}
```

既有合約 sc：`lqb6U38jhszBEhPCQZdsAu`（start 2026-09-02，走查時被 UTC 判尚未生效）與 `-3NUO7IRdqfiqjpK9-e6wU`（start 2026-09-01）。
停用走 `PATCH /api/contracts/<sc>/disable`（停用後不能再啟用，見手冊「企業與合約管理」）：

```bash
for sc in lqb6U38jhszBEhPCQZdsAu -3NUO7IRdqfiqjpK9-e6wU; do
  curl -s -b $CJ -c $CJ -X PATCH "$BASE/api/contracts/$sc/disable" -H "X-CSRFToken: $TOKEN" -w '\nHTTP %{http_code}\n' | tail -c 200; done
```

回 200 是停成功；回 400/404（已停用或找不到）**可忽略**，判準只有一個：跑完後 DemoSOC 只剩你接下來建的合約含 open_defense。查現況：

```bash
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 "sudo -u postgres psql -d beakplatform -At -c \"SELECT secure_code, status, start_date, end_date, modules_config FROM contracts WHERE org_secure_code='ugRNno6lA97ZicqIbBvBEb' AND is_deleted=false ORDER BY id;\"" 2>&1 | tee -a $LOG
```

（試用合約 `CTR-20260901-0001` 只含 form_workflow，不影響 open_defense 判定，可不動。）

### 2b. 壞的案例：起日＝台北明天 → 員工開處置中心必須 403

```bash
TPE_TOMORROW=$(TZ=Asia/Taipei date -d tomorrow '+%F'); END=$(date -d '+1 year' '+%F')
curl -s -b $CJ -c $CJ -X POST "$BASE/api/contracts/" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d "{\"org_id\":\"ugRNno6lA97ZicqIbBvBEb\",\"start_date\":\"$TPE_TOMORROW\",\"end_date\":\"$END\",\"name\":\"mutation 明天生效\",\"modules_config\":[\"form_workflow\",\"open_defense\"]}" \
  | tee -a $LOG | python3 -c "import json,sys; d=json.load(sys.stdin)['contract']; print('SC_TOMORROW=', d['secure_code'], 'is_active=', d['is_active'])"
# 預期 is_active= False（修正後 to_dict 的 is_active 依台北日期）；記下 SC_TOMORROW，收尾要用
CJS=/opt/tmp/verify/cj_bpserv_soc1.txt
curl -s -c $CJS -b $CJS -X POST "$BASE/auth/login" -H 'Content-Type: application/json' -d '{"account":"soc1@demo-soc.example","password":"DemoSoc-Staff2026#"}' -o /dev/null -w 'login HTTP %{http_code}\n'
curl -s -o /dev/null -b $CJS -w 'security-cases HTTP %{http_code}\n' "$BASE/open-defense/security-cases/" 2>&1 | tee -a $LOG
# 預期 403
```

### 2c. 好的案例：起日＝台北今天 → 同一個員工立刻 200（不必等 UTC 日界）

```bash
echo "taipei=$(TZ=Asia/Taipei date +%F) utc=$(date -u +%F)" | tee -a $LOG   # 兩者不同天才是決定性的 2c；相同就改跑 2d
TPE_TODAY=$(TZ=Asia/Taipei date '+%F'); END=$(date -d '+1 year' '+%F')
curl -s -b $CJ -c $CJ -X POST "$BASE/api/contracts/" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d "{\"org_id\":\"ugRNno6lA97ZicqIbBvBEb\",\"start_date\":\"$TPE_TODAY\",\"end_date\":\"$END\",\"name\":\"mutation 今天生效\",\"modules_config\":[\"form_workflow\",\"open_defense\"]}" \
  | tee -a $LOG | python3 -c "import json,sys; d=json.load(sys.stdin)['contract']; print('SC_TODAY=', d['secure_code'], 'is_active=', d['is_active'])"
# 預期 is_active= True —— 修正前在台北 00:00~08:00 這裡會是 False（走查當時就是）
curl -s -o /dev/null -b $CJS -w 'security-cases HTTP %{http_code}\n' "$BASE/open-defense/security-cases/" 2>&1 | tee -a $LOG
# 預期 200

### 2d. 替代法（台北 08:00 之後跑時用）：把企業時區暫改 UTC+14 製造「企業今天 ≠ UTC 今天」

```bash
# 改時區（organizations.settings 是存 JSON 的 text 欄位）
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 "sudo -u postgres psql -d beakplatform -At -c \"UPDATE organizations SET settings = jsonb_set(coalesce(settings,'{}')::jsonb, '{timezone}', '\\\"Pacific/Kiritimati\\\"')::text WHERE secure_code='ugRNno6lA97ZicqIbBvBEb'; SELECT settings FROM organizations WHERE secure_code='ugRNno6lA97ZicqIbBvBEb';\"" 2>&1 | tee -a $LOG
KIR_TODAY=$(TZ=Pacific/Kiritimati date '+%F'); echo "kiritimati=$KIR_TODAY utc=$(date -u +%F)" | tee -a $LOG   # 台北 10:00~24:00 之間兩者一定不同天
# 先把 2c 建的合約停掉（否則它已讓 open_defense 有效，看不出差別）：PATCH /api/contracts/$SC_TODAY/disable
# 再用 KIR_TODAY 當 start_date 重跑 2c 的建合約＋soc1 GET，預期 is_active= True 且 200；舊碼在此會是 False / 403
# 驗完改回台北，否則處置中心的「今日」統計會跟著跑掉：
sshpass -p 'P@ssw0rd' ssh -o StrictHostKeyChecking=no ethan@192.168.0.66 "sudo -u postgres psql -d beakplatform -At -c \"UPDATE organizations SET settings = jsonb_set(coalesce(settings,'{}')::jsonb, '{timezone}', '\\\"Asia/Taipei\\\"')::text WHERE secure_code='ugRNno6lA97ZicqIbBvBEb';\"" 2>&1 | tee -a $LOG
```
```

**判定**：2b 是 403，且 2c（台北 00:00～08:00）或 2d（其他時段）是 200 才算通過。2c/2d 仍 403 代表 `--update` 沒把新碼帶上或服務沒重啟（回頭看步驟 1 的 `grep def local_today`）。

## 3. 收尾

- 2b 建的「明天生效」合約（`$SC_TOMORROW`）留著無妨（明天就會生效、與 2c 疊加），要乾淨就 `PATCH /api/contracts/$SC_TOMORROW/disable`。跑過 2d 的話確認時區已改回 Asia/Taipei。
- 結果回寫 BBN：MCP `note_update(atom_id=5216, append_content=<結果與 log 路徑>)`，待辦 PF-214 用 `note_task_update` 標完成（先 `note_search("PF-214")` 取 atom_id）。

## 附：全新企業從零到可收案的 curl 鏈（本 session 實跑成功，需要重演時用）

```bash
BASE=http://192.168.0.66:8000/beakplatform
# SYSTEM_ADMIN 建企業（必填 code/name/domain_name/admin_password；回應含 organization.secure_code）
curl -s -b $CJ -c $CJ -X POST "$BASE/api/organizations/" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d '{"code":"DEMOSOC","name":"示範企業 DemoSOC","domain_name":"demo-soc.example","admin_password":"DemoSocInit2026Pass"}'
# 合約（org_id 是企業 secure_code；start_date 用台北日期）
curl -s -b $CJ -c $CJ -X POST "$BASE/api/contracts/" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d '{"org_id":"<ORG_SC>","start_date":"<YYYY-MM-DD>","end_date":"2027-09-01","name":"正式合約","modules_config":["form_workflow","open_defense"]}'
# 原始管理員 admin@<domain> 首登 → 必改密（JSON POST /auth/change-password，X-CSRFToken 取自該頁 hidden input name="csrf_token"）
# → GET /dashboard 會 302 到 /admin/initial-setup → POST form（native_name/english_name/username/employee_id(空=自動)/password/confirm_password/csrf_token）
#    密碼政策要含特殊符號，否則 flash「密碼必須包含特殊符號」且不建帳號
# → 產生 <username>@<domain>（EMPLOYEE）與 admin-<username>@<domain>（ORG_ADMIN），原始 admin 停用
# ORG_ADMIN 指派角色：POST /api/access/assign {"user_secure_code":..., "role_secure_code":...}（SECURITY_STAFF 由 open_defense 合約種入）
# bpserv 上（beakplatform 帳號）建 OD 鏈路：
#   sudo -u beakplatform bash -c "cd /opt/BeakPlatform && set -a && source .env && set +a && \
#     venv/bin/python scripts/examples/provision_od_intake_for_org.py --org demo-soc.example --apply --source-system elk && \
#     venv/bin/python scripts/examples/provision_od_workflow_variants.py --org <ORG_SC> --supervisor <username>@<domain> --with-routing --apply"
#   （intake 腳本會印 API Key id 與一次性 secret）
# 啟用路由：PUT /api/open_defense/admin/routing-rules/<rule_sc> {"match_rules":[{"field":"severity_id","op":"gte","value":3}],"is_active":true}
# 從 .16 送事件：
#   export BP_BASE_URL=$BASE BP_API_KEY_ID=<key_id> BP_API_KEY_SECRET='<secret>'
#   python3 scripts/examples/od_intake_send_event.py --source-system elk --event-class web_activity --severity 5 \
#     --title "測試" --rule-id R-1 --actor-ip 203.0.113.42 --target-host portal.demo-soc.example
#   （重演要換 --rule-id / --actor-ip / --target-host，否則被聚合進既有案件）
# EDL：sudo -u beakplatform bash -c "cd /opt/BeakPlatform && venv/bin/python scripts/cron/od_render_edl.py"; cat /opt/BeakPlatform/data/edl/<ORG_SC>/blocklist.txt
```
