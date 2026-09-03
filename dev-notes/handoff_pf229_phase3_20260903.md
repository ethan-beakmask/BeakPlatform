# 交接：PF-229 第三期（行事曆衍生功能）— 2026-09-03

> 寫給下一個 session。第一、二期已上線並部署到 bpserv；第三期**尚未開工，先討論再寫 spec**。
> 母原子 BBN #5380（`note_get(5380)`），第三期範圍在該原子「第三期」段；本檔只放本 session 驗證過的指令與待決事項。

## 一、現況（2026-09-03 07:50）

| 項目 | 狀態 |
|---|---|
| dev（`/opt/BeakPlatform-dev`） | `bd152b13`，工作區乾淨。第二期 commit `650f2bc1` |
| bpserv（`192.168.0.66:8000`） | 已 `--update` 到 GitHub `70f5de6c`（＝dev `d7660a93`），行事曆選單已補種，`schedule_adjustments` 已補欄位＋唯一約束（PF-232 完成，憑證 `/opt/tmp/verify/20260903-pf232-bpserv-calendar.log`） |
| 第二期驗收憑證 | `/opt/tmp/verify/20260903-pf229-p2-api.log`（curl 矩陣）、`20260903-pf229-p2-browser.log`（chrome-devtools 實點） |
| 規格文件 | `dev-notes/CALENDAR_SPEC.md`（第六節＝第二期寫入規則與升級 SQL；六之二＝第三期入口） |
| 測試 | `bash scripts/run_tests.sh tests/test_calendar_events_api.py tests/test_calendar_projection.py tests/test_calendar_pages.py -q` → 32 passed（第二期當時） |

## 二、開工前必須先跟 Ethan 定案的兩件事（2026-09-03 提出，尚未回答）

1. **請假同步的粒度**：第二期是**日粒度**（事件觸及的每個當地日都寫一筆 `schedule_adjustments`，半天假也讓
   `ScheduleService.get_work_periods()` 回空）。第三期「工作時間逾時」要用 `calculate_working_seconds()` 扣請假，
   日粒度會把半天假算成整天不計時。選項：維持日粒度（簡單、與班表假日一致）／改時段級（`adjusted_periods` 存剩餘時段，
   `get_work_periods()` 的 LEAVE 分支要改成回 `adjusted_periods`）。
2. **面板行為**：按 [在這天新增] 時當日面板不關閉（存檔後面板即時列出新事件）。要不要改成關閉？純 UX，不擋開工。

## 三、第三期四項（摘自 #5380，動工順序建議 1 → 4 → 3 → 2）

| # | 項目 | 牽涉檔案（本 session 確認存在） | 備註 |
|---|---|---|---|
| 1 | 建立 LEAVE／TRIP 事件時，若本人是任何流程的簽核者，提示建代理授權並帶入期間 | `backend/app/services/calendar_event_service.py`（掛 hook 的唯一位置）、`modules/form_workflow/services/task_authorizer.py`（判定「是不是簽核者」的唯一實作）、`backend/app/web/delegations.py`＋`templates/pages/delegations/create.html`（代理授權頁，可加 query string 預填期間） | 前端只提示，不自動建代理（Ethan 2026-09-02 定調代理效期不依賴行事曆） |
| 2 | 簽核節點 `timeout_mode`（工作時間逾時） | `backend/app/services/schedule_service.py`（`calculate_working_seconds()` 已存在於第 142 行，見下方掃描；`timeout_mode` 全專案尚無人用）、`modules/form_workflow/services/workflow_executor.py`（**WAITING 喚醒清單兩處都要加**，CLAUDE.md「新增會回 waiting 的節點型別」） | 依賴第二點粒度決策 |
| 3 | TimeContext 起步：`who_on_leave(instant)` / `who_on_duty(instant)` | 新檔，讀 `schedule_adjustments`（`calendar_event_secure_code` 有值＝行事曆來的）＋班表 | 設計在 `dev-notes/knowledge/time-context-architecture.md` |
| 4 | 簽核紀錄補寫 `delegate_from_*` | `fw_approval_records` 欄位已存在但無人寫入；寫入點在 `task_authorizer.py` 判定代理成立的那條路徑 | 行事曆才能回溯「誰代誰簽了什麼」 |

## 四、本 session 實跑成功的指令（照抄即可）

### 登入與 token（dev，quick-login 免密碼）

```bash
BASE=http://192.168.0.16:7000/beakplatform
cd /tmp   # cookie 檔隨便放
login(){ curl -s -c $2 -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' -d "{\"user_id\":\"$1\"}" -o /dev/null -w "login $2 %{http_code}\n"; }
login FhsmtyPjsnXYotN-iz_Q-X emp.txt      # EMPLOYEE ethanyu@beluga.com（持 FLOW_DESIGNER + SECURITY_STAFF，是多個 OD 流程的簽核者 → 測第三期第 1 項的好樣本）
login EpFwno0dDyYhTIaAn8Tqb_ emp2.txt     # EMPLOYEE user@beluga.com（純員工，看遮罩用）
login jIYEQ-_lZMZNBkVy-hijal adm.txt      # ORG_ADMIN admin-ethanyu@beluga.com
tok(){ curl -s -b $1 -c $1 "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3; }
T1=$(tok emp.txt); TA=$(tok adm.txt)
# 服務剛重啟時先等 $BASE/auth/login 回 200 再登入，否則 nginx 回 502；重啟後所有 cookie 作廢要重登
```

### 建／改／刪事件（第二期 API，全部驗過）

```bash
call(){ curl -s -b $1 -X $3 "$BASE$4" -H 'Content-Type: application/json' -H "X-CSRFToken: $2" ${5:+-d "$5"} -w '\n[http %{http_code}]\n'; }
# 全天請假三天 → 201，回應 event.secure_code；同時產生 schedule_adjustments 三筆
call emp.txt $T1 POST /api/calendar/events '{"calendar_kind":"PERSONAL","event_type":"LEAVE","title":"P2特休","all_day":true,"start":"2026-09-21","end":"2026-09-23","visibility":"BUSY"}'
# 縮成一天 → 200；9/22、9/23 的 adjustments 變 is_deleted=true
call emp.txt $T1 PUT /api/calendar/events/<sc> '{"event_type":"LEAVE","title":"P2特休(縮)","all_day":true,"start":"2026-09-21","end":"2026-09-21","visibility":"BUSY"}'
# 刪除 → 200；全部軟刪
call emp.txt $T1 DELETE /api/calendar/events/<sc>
# 讀取（emp2 看 emp 的 BUSY 只拿到 masked=true、source_type='busy'）
curl -s -b emp2.txt "$BASE/api/calendar/org/events?start=2026-09-15&end=2026-09-17" | python3 -m json.tool | head -40
# 忘了帶 X-CSRFToken 回 400 不是 403；EMPLOYEE 建 ORG 回 403 forbidden；非 owner 改刪回 404
```

### 看請假同步結果（dev 庫）

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -A -c \
  "SELECT adjust_date, adjust_type, status, is_deleted, calendar_event_secure_code, note, original_periods FROM schedule_adjustments ORDER BY adjust_date;"
# BELUGA 沒有預設班表，所以 original_periods 是 []；要看有班表的情況用 GHTRAVEL（有完整人資結構）
```

### 清測試資料（用 UTC 時窗，不要用 CURRENT_DATE）

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -A \
  -c "DELETE FROM schedule_adjustments WHERE calendar_event_secure_code IN (SELECT secure_code FROM calendar_events WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '3 hours' AND title LIKE 'P2%');" \
  -c "DELETE FROM calendar_events WHERE created_at >= (now() AT TIME ZONE 'UTC') - interval '3 hours' AND title LIKE 'P2%';"
```

### 改 model 後必跑

```bash
bash scripts/check_schema_drift.sh        # 約 2 分鐘，「結果: 無差異（綠）」才算過
```

## 五、第三期會踩的既知坑（都在 CLAUDE.md，這裡只列指針）

- 新增會回 `waiting`／`pending` 的節點型別或狀態，`workflow_executor.py` 內**兩處** WAITING 清單都要加，漏了節點永遠不被喚醒（OsExecutor 2026-08-30 踩過）
- 改 handler 後要 `sudo systemctl restart beakplatform-dev-executor`，但重啟會殺掉正在跑的節點；先查 `SELECT node_type, node_id, started_at FROM fw_node_execution_queue WHERE status='RUNNING';`
- 流程變數權威在 `fw_workflow_variables`，`${wi.xxx}` 只支援五個欄位
- 系統級節點測試要用系統預設企業的 ORG_ADMIN（quick-login `UC1oK01uDeKbG2MDwBflGD`）
- 簽核授權判定只在 `task_authorizer.py`，第三期第 1 與第 4 項都從它下手，不要另寫「是不是簽核者」的判斷
## 六、現況掃描（2026-09-03 07:51 自動產生，第三期第 2 項的前置）
```
# calculate_working_seconds 是否存在：
backend/app/services/schedule_service.py:142:    def calculate_working_seconds(
backend/app/services/schedule_service.py:254:        working_seconds: int
backend/app/services/schedule_service.py:262:            working_seconds: 需要的工作秒數
backend/app/services/schedule_service.py:267:        remaining = working_seconds
backend/app/services/schedule_service.py:314:        return start_time + timedelta(seconds=working_seconds)
# timeout_mode 目前有沒有人用：
# delegate_from 欄位與寫入點：
modules/form_workflow/models/approval_record.py:34:    delegate_from_secure_code = Column(String(32), nullable=True)
modules/form_workflow/models/approval_record.py:35:    delegate_from_name = Column(String(200), nullable=True)
modules/form_workflow/services/sql_sync/converter.py:483:    ('delegate_from_secure_code', 'VARCHAR(32)', True),
modules/form_workflow/services/sql_sync/converter.py:484:    ('delegate_from_name', 'VARCHAR(200)', True),
modules/form_workflow/services/sql_sync/sync_service.py:398:    'delegate_from_secure_code',
modules/form_workflow/services/sql_sync/sync_service.py:399:    'delegate_from_name',
modules/form_workflow/services/sql_sync/sync_service.py:458:                        rec.delegate_from_secure_code,
modules/form_workflow/services/sql_sync/sync_service.py:459:                        rec.delegate_from_name,
# executor 的 WAITING 喚醒清單（兩處）：
134:                    FwNodeExecutionQueue.node_type.in_(['Delay', 'End', 'ParallelJoin', 'OsExecutor']),
272:            FwNodeExecutionQueue.node_type.in_(['Delay', 'End', 'ParallelJoin', 'OsExecutor']),
```
（空行＝該符號不存在，第三期要自己建。）


## 七、冷讀審核補洞（2026-09-03 codex 不帶對話記憶審出 12 點，已能回答的補在這裡）

**commit 關係（審核第 12 點）**：bpserv 的 GitHub `70f5de6c` 是 dev `d7660a93` 經 `push_github.sh` 過濾後的對應 commit；
dev 之後又多了 `bd152b13`（只改 CLAUDE.md 的 bpserv 狀態列）與本檔的 commit，程式碼與 bpserv 一致。從 dev HEAD 開工即可。

**第 1 項的驗收樣本（審核第 10 點）**：`ethanyu@beluga.com` 是多個 open_defense 案件的簽核者。
**行事曆 API 已不再回 `approval_task`**（Ethan 2026-09-03 定案移除待簽核投影，見 `CALENDAR_SPEC.md` 第三節），
所以「是不是簽核者」不能再從 `/api/calendar/me/events` 看，要用 SQL：

```sql
SELECT q.secure_code, q.node_type, q.node_name, q.scheduled_at, wi.execution_code
FROM fw_node_execution_queue q JOIN fw_workflow_instances wi ON wi.secure_code = q.workflow_instance_secure_code
WHERE q.status='WAITING' AND q.node_type IN ('Approve','FormAdapter') AND q.is_deleted=false
  AND q.org_secure_code=(SELECT secure_code FROM organizations WHERE code='BELUGA') ORDER BY q.scheduled_at DESC LIMIT 20;
-- 再用 can_act_on_task(task, 'FhsmtyPjsnXYotN-iz_Q-X', org_sc, actor) 判定哪些是他的（唯一實作在 task_authorizer.py）
```

**代理授權頁預填（審核第 11 點）**：`backend/app/web/delegations.py` 對 `request.args` / 效期欄位的現況（動工時自己再看一次）：

```
70:        effective_from_str = request.form.get('effective_from', '').strip()
71:        effective_until_str = request.form.get('effective_until', '').strip()
83:        if not effective_from_str:
85:        if not effective_until_str:
88:        effective_from = None
89:        effective_until = None
```

**第三期 spec 討論前要定案的問題（審核第 2、3、6、7、8、9 點，全部是設計決策不是交接缺漏）**：

| # | 問題 | 影響項目 |
|---|---|---|
| Q1 | 請假同步粒度：日粒度／時段級（PF-233 沒回答卡） | 2 |
| Q2 | 「本人是簽核者」的判定範圍：只看目前 WAITING 的任務？還是模板上可能命中（角色／部門／主管鏈解析）？ | 1 |
| Q3 | 代理建議的 UX：存檔後 toast 提示＋連結？還是 modal 內第二步？可忽略？連到代理頁後要不要回流行事曆？ | 1 |
| Q4 | `timeout_mode` 放哪：簽核節點 config（graph 內）；允許值 ABSOLUTE／WORKING／BOTH（`dev-notes/knowledge/time-management-spec.md` 第 1.2 節）；與既有 Delay 節點的關係 | 2 |
| Q5 | 工作時間逾時的計算時機：進 WAITING 時算一次 deadline（`get_deadline_from_working_seconds()` 已在 `schedule_service.py:254`），還是 executor 每次喚醒重算？班表／請假／代理變更後要不要重算？ | 2 |
| Q6 | `delegate_from_*` 存什麼：原簽核者的 user secure_code＋display_name（欄位型別 String(32)/String(200) 暗示是這個），還是 delegation 記錄 | 4 |
| Q7 | 面板 [在這天新增] 後要不要關面板（純 UX） | 前端 |

**#5380 第三期段原文（審核第 4 點，避免只靠 MCP 才讀得到）**：

> 1. **代理建議**：建立 `LEAVE` / `TRIP` 事件時，若本人是任何流程的簽核者（角色或指定人），提示建立代理授權並帶入期間；管理員在代理授權頁也能從行事曆挑期間
> 2. **工作時間逾時（time-management-spec 規則二）**：簽核節點加 `timeout_mode`，用 `ScheduleService.calculate_working_seconds()` 扣掉班表非工作時間與請假日；executor 的 WAITING 清單要一併加（CLAUDE.md「新增會回 waiting 的節點型別」那條）
> 3. **TimeContext 起步**（`dev-notes/knowledge/time-context-architecture.md`）：`who_on_leave(instant)` / `who_on_duty(instant)` 兩個查詢，先給 OD 路由與簽核者解析用
> 4. 簽核紀錄補寫 `delegate_from_*`（現在欄位存在但沒人寫入），行事曆才能回溯「這段期間誰代誰簽了什麼」
>
> 不做的事：不做跨企業共享行事曆（集團另案）、不做外部行事曆同步（封閉網路）、不把「效期判定」搬進行事曆。

第 3 項開工前**必讀** `dev-notes/knowledge/time-context-architecture.md`（審核第 5 點，本檔不重抄設計）。
