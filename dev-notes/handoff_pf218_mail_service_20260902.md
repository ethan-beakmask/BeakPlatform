# PF-218 交接：系統級發信服務二選一——剩下的兩段驗收（2026-09-02）

主體已完成並部署在 dev（commit `04c87cdd` / `e1ea77ac`，決策與驗收記錄在 BBN #5364）。
本檔只寫**還沒做完的兩段驗收**，指令全部是 2026-09-02 這個 session 實際跑過成功的，照抄即可。
機制說明見 `CLAUDE.md`「系統級發信只有一個入口：EmailService」一段，這裡不重複。

## 冷讀後補的七件事（2026-09-02 codex 冷讀指出，照這裡做不用猜）

1. **Gmail 應用程式密碼只有 Ethan 有**（Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼，16 碼、畫面顯示帶空格）。
   對話裡沒拿到就停在 A-1，**不要用一般密碼試、也不要猜**——Gmail 會鎖帳號。B-4 用同一組
2. **本檔不授權 push**。B-1 的 `push both` 要 Ethan 在對話裡說「push both」（或「push github」）才做；
   在那之前 B 整段都做不了，先做 A
3. 交接時的 git 狀態：工作區乾淨、`main` 在 `e1ea77ac`（含 PF-218 兩個 commit `04c87cdd`、`e1ea77ac`），
   `origin/main`（Forgejo）已同步到這裡；GitHub 鏡像還沒推。`push both` 推的是整條 `main`，
   不會只挑 PF-218。推完用 `git log github/main -1 --oneline` 記下鏡像 commit，bpserv `--update` 後
   `sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 'cd /opt/BeakPlatform && git log -1 --oneline'` 要對得上
4. `note_update` / `note_search` 是 Claude Code session 裡的 BeakBroodNest MCP 工具（`mcp__beak_broodnest__*`），
   不是 CLI；MCP 不可用時把結果寫在回覆裡請 Ethan 貼進 #5364
5. 憑證檔名（續寫這些，不要另開）：`/opt/tmp/verify/20260902-pf218-api.log`（API 矩陣）、
   `20260902-pf218-forgot-e2e.log`（忘記密碼 E2E）、`20260902-pf218-browser.log`（瀏覽器實測）。
   bpserv 那段另開 `20260902-pf218-bpserv.log`
6. B-4 記下的 `secure_code` 用在兩處：`POST /api/system-settings/smtp/<sc>/test`（只測登入）與
   事後要刪就 `DELETE /api/system-settings/smtp/<sc>`（不刪也可以，見「完成後」）
7. B-5 的 chrome-devtools 是**選做**（只有主 Claude 有），curl 那幾段就是完整驗收；沒有瀏覽器工具就跳過

## 為什麼還有兩段沒做

| 段 | 卡在哪 |
|---|---|
| A. dev 併發實寄（「收到兩封」） | dev 系統級 SMTP 設定組 `lionsecbot@gmail.com`（sc `9V_rPCngCX-q65mbSbICJa`）存的不是 Gmail 應用程式密碼，Gmail 回 534。Ethan 2026-09-02 說要自己去找密碼 |
| B. bpserv（fresh、沒裝 E-MailRelay） | 程式要先 `push github` 再 `install.sh --update`，push 要 Ethan 下令 |

---

## A. dev：換好 SMTP 密碼後驗「併發收到兩封」

### A-1 換密碼（UI 或 API 二選一）

UI：`http://192.168.0.16:7000/beakplatform/hostconfig/server-settings` → [發信服務] → 最下方「SMTP 設定組（系統級）」→
`lionsecbot@gmail.com` 那列 [編輯] → 密碼欄貼 `xxxx xxxx xxxx xxxx` → [儲存] → 同列 [測試]（收件人留空只測登入）。

API（SYSTEM_ADMIN，quick-login 免密碼）：

```bash
BASE=http://192.168.0.16:7000/beakplatform
curl -s -c cj_sys.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' -d '{"user_id":"nH5liUKQikH1NM2osVVXuF"}'
TS=$(curl -s -b cj_sys.txt -c cj_sys.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
# 換密碼（密碼欄非空才會改，其他欄位不動）
curl -s -b cj_sys.txt -X PUT "$BASE/api/system-settings/smtp/9V_rPCngCX-q65mbSbICJa" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TS" -d '{"password":"<應用程式密碼>"}'
# 只測登入，不寄信；要看到 {"success":true,"message":"SMTP 連線成功"}
curl -s -b cj_sys.txt -X POST "$BASE/api/system-settings/smtp/9V_rPCngCX-q65mbSbICJa/test" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TS" -d '{}'
```

`POST /api/system-settings/smtp/<sc>/test` 是既有端點，2026-09-02 對這組回「認證失敗：帳號或密碼錯誤」，換密碼後應變成連線成功。

### A-2 指定併發

```bash
curl -s -b cj_sys.txt -X PUT "$BASE/api/system-settings/mail-service" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TS" -d '{"primary":"emailrelay","send_both":true}'
# 期望 HTTP 200，data.readiness.ready=true，messages.overall=「系統信將由 E-MailRelay 與 SMTP 同時寄出」
```

### A-3 用忘記密碼流程實寄，看兩路都成功

收件人用平台自己的 SMTP 帳號自寄（`lionsecbot@gmail.com`），不要用 `@beluga.com` 這種可能是真實網域的地址。
測試帳號 `ssss@beluga.com`（BELUGA 的 EMPLOYEE 測試資料，密碼本來就不明、平常走 quick-login）。

```bash
export PGPASSWORD=postgres123
PSQL="psql -h localhost -U beakplatform -d beakplatform_dev -q -t -A"
$PSQL -c "UPDATE users SET backup_email_1='lionsecbot@gmail.com' WHERE email='ssss@beluga.com';"

# 忘記密碼：POST 後不要 -L（curl -X POST -L 會把轉址後的 GET 也變 POST，flash 就抓不到）
LOC=$(curl -s -c cj_fp.txt -b cj_fp.txt -o /dev/null -w '%{redirect_url}' -X POST \
  "$BASE/auth/org/beluga.com/forgot-password" -d 'username=ssss')
curl -s -c cj_fp.txt -b cj_fp.txt "$LOC" | grep -o "已寄送密碼重設驗證信[^<]*\|驗證信[^<]*失敗[^<]*"
# 期望「已寄送密碼重設驗證信到您的信箱…」（兩路都成功）；
# 只成功一路會是「驗證信已寄出，但其中一個發信服務失敗…」——那就去看 journal 哪一路失敗

# 兩路的證據
ls /opt/emailrelay/spool            # E-MailRelay 路：submit 後立刻有 *.envelope + *.content（daemon 每 10 秒轉寄，晚幾秒就空了）
journalctl -u beakplatform-dev.service --since "2 min ago" --no-pager | grep "\[EMAIL\]"
# 成功只有 logger.info（journal 看不到），失敗才有 "[EMAIL] send via smtp failed: ..."；沒有 failed 行＝兩路都成功

# 還原
$PSQL -c "UPDATE users SET backup_email_1='ssss@beluga.com' WHERE email='ssss@beluga.com';"
$PSQL -c "UPDATE password_reset_tokens SET is_deleted=true WHERE email='ssss@beluga.com' AND is_deleted=false;"
curl -s -b cj_sys.txt -X PUT "$BASE/api/system-settings/mail-service" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TS" -d '{"primary":"emailrelay","send_both":false}'
```

同一個 username 在 10 分鐘內 POST 忘記密碼超過幾次會 429（速率限制 key 是 username＋IP）；被擋就換一個 BELUGA 測試帳號（`user@beluga.com` 的 username 是 `user`）。

若還想驗「暫時密碼」那一步：驗證碼在 DB，

```bash
$PSQL -c "SELECT verification_url_token||' '||verification_code FROM password_reset_tokens WHERE email='ssss@beluga.com' AND is_deleted=false ORDER BY id DESC LIMIT 1;"
curl -s -c cj_fp.txt -b cj_fp.txt -X POST "$BASE/auth/verify-reset/<url_token>" -d "code=<六碼>"
```

驗完 `ssss@beluga.com` 的密碼會變成暫時密碼且 `must_change_password=true`，用
`UPDATE users SET must_change_password=false WHERE email='ssss@beluga.com';` 收掉即可（原密碼本來就沒人知道）。

---

## B. bpserv：fresh 環境、沒裝 E-MailRelay

### B-1 部署（先取得 Ethan 的 push 指令）

```bash
cd /opt/BeakPlatform-dev && git push origin main && bash scripts/push_github.sh     # ＝ push both
sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 'sudo bash /opt/BeakPlatform/scripts/install.sh --update'
```

`--update` 會 create_all（`system_settings` 是既有表，不需新表）、重啟服務。PAT 已在 `.git/config`，不會再問。

### B-2 登入（bpserv 沒有 quick-login）

```bash
B=http://192.168.0.66:8000/beakplatform
curl -s -c cj_bp.txt -X POST "$B/auth/login" -H 'Content-Type: application/json' \
  -d '{"account":"admin@sys-1271967103b6","password":"BpservTest2026Changed"}'      # SYSTEM_ADMIN，200
TB=$(curl -s -b cj_bp.txt -c cj_bp.txt "$B/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
```

（`sys-1271967103b6` 是 2026-09-02 重裝後的 SYSTEM_ORG_CODE，重裝過會變，以 `CLAUDE.md` bpserv 表為準。）

### B-3 驗「指定 E-MailRelay 而它不存在 → 儲存被擋」

```bash
curl -s -b cj_bp.txt "$B/api/system-settings/mail-service"
# 期望 primary=null、readiness.reason=not_selected、services.emailrelay.reason=submit_missing（detail 是 /opt/E-MailRelay/sbin/emailrelay-submit）
curl -s -b cj_bp.txt -X PUT "$B/api/system-settings/mail-service" -H 'Content-Type: application/json' -H "X-CSRFToken: $TB" \
  -d '{"primary":"emailrelay"}' -w '\nHTTP %{http_code}\n'
# 期望 400，message「無法指定 E-MailRelay 為發信服務：找不到 emailrelay-submit：…」
```

### B-4 建系統級 SMTP 設定組、指定 SMTP、忘記密碼真的寄到

```bash
curl -s -b cj_bp.txt -X POST "$B/api/system-settings/smtp" -H 'Content-Type: application/json' -H "X-CSRFToken: $TB" -d '{
  "name":"lionsecbot","smtp_host":"smtp.gmail.com","smtp_port":587,"use_tls":true,"use_ssl":false,
  "username":"lionsecbot@gmail.com","password":"<應用程式密碼>","from_email":"lionsecbot@gmail.com",
  "from_name":"BeakPlatform bpserv","provider_type":"gmail","is_default":true,"is_active":true}'
# 回 201，記下 data.secure_code（下一行測登入、事後 DELETE 都用它）
curl -s -b cj_bp.txt -X POST "$B/api/system-settings/smtp/<secure_code>/test" -H 'Content-Type: application/json' -H "X-CSRFToken: $TB" -d '{}'
# 要看到「SMTP 連線成功」再往下
curl -s -b cj_bp.txt -X PUT "$B/api/system-settings/mail-service" -H 'Content-Type: application/json' -H "X-CSRFToken: $TB" \
  -d '{"primary":"smtp","send_both":false}' -w '\nHTTP %{http_code}\n'
# 期望 200，overall「系統信將由 SMTP 寄出」；沒建 is_default 設定組時會是 400「沒有啟用中且勾選「設為預設」的系統級 SMTP 設定組」
```

忘記密碼對象用 DemoSOC 的 `soc1@demo-soc.example`（EMPLOYEE，ORG domain `demo-soc.example`），先把它的備用信箱改成 `lionsecbot@gmail.com`：

```bash
sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 "sudo -u postgres psql -d beakplatform -c \"UPDATE users SET backup_email_1='lionsecbot@gmail.com' WHERE email='soc1@demo-soc.example';\""
LOC=$(curl -s -c cj_bpf.txt -b cj_bpf.txt -o /dev/null -w '%{redirect_url}' -X POST "$B/auth/org/demo-soc.example/forgot-password" -d 'username=soc1')
curl -s -c cj_bpf.txt -b cj_bpf.txt "$LOC" | grep -o "已寄送密碼重設驗證信[^<]*\|系統發信服務尚未就緒[^<]*\|驗證信[^<]*失敗[^<]*"
sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 'sudo journalctl -u beakplatform --since "2 min ago" --no-pager | grep "\[EMAIL\]"'   # 沒有 failed 行＝成功
```

信會到 `lionsecbot@gmail.com` 收件匣（自寄）。驗完把 `backup_email_1` 改回 `soc1@demo-soc.example`，
並 `UPDATE password_reset_tokens SET is_deleted=true WHERE email='soc1@demo-soc.example';`。
DemoSOC 帳號密碼與其他識別碼見 `CLAUDE.md` bpserv 表。

### B-5 順手看 UI（選做；只有主 Claude 有 chrome-devtools，用 isolated context 免得跟 dev 的 cookie 打架）

`new_page(url='http://192.168.0.66:8000/beakplatform/auth/login', isolatedContext='bpserv')` 登入後開
`/hostconfig/server-settings`：sidebar 第一項「發信服務」、E-MailRelay badge 應為紅色「找不到 emailrelay-submit：…」、
橫幅紅色「尚未指定發信服務，系統信目前無法寄出」。

---

## 完成後

- BBN #5364 追記兩段結果（`note_update(5364, append_content=...)`），憑證落 `/opt/tmp/verify/20260902-pf218-*.log` 同一組檔名續寫
- bpserv 那組 SMTP 設定組與 mail-service 設定可以留著（bpserv 就是要有系統信）
- 本檔任務完成後可刪除；機制說明已在 `CLAUDE.md`，不需要搬
