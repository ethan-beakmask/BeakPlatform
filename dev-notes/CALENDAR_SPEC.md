# 企業行事曆／我的行事曆（PF-229）— 第一、二期實作記錄與第三期指引

> 2026-09-02 建立，2026-09-03 補第二期。第一期（資料模型 + 唯讀投影）與第二期（事件 CRUD、請假同步班表、BUSY 合併）已上線；
> 第三期規格見 BBN #5380（`note_get(5380)`）。
> 手冊頁：`docs/manual/07_daily_work/calendar.md`；manifest：`dev-notes/manifests/calendar.yaml`。

## 一、定位（不要把效期判定搬進來）

| 層 | 內容 | 規則 |
|---|---|---|
| 效期判定 | 合約、角色指派、職位、代理「今天有沒有效」 | **不走行事曆**。各自用 `Organization.local_today()` 即時判定（合約 PF-125、代理 2026-09-02、角色指派 `UserRoleAssignment.is_valid_on()` 同日對齊） |
| 規劃時間 | 誰請假、誰出差、公司放假、公司活動 | 行事曆是唯一入口與來源。**待簽核不算**（沒有確定時間的是待辦，看表單中心） |
| 呈現與私密 | 月／週視圖、公開／僅顯示已排程／私人 | 行事曆 UI |

## 二、檔案

| 角色 | 檔案 |
|---|---|
| model | `backend/app/models/calendar_event.py`（`calendar_events`；`CalendarKind` / `CalendarEventType` / `CalendarVisibility`；第二期加 `PERSONAL_EVENT_TYPES` / `ORG_EVENT_TYPES` / `LEAVE_LIKE_TYPES`）、`schedule_adjustment.py`（第二期加 `calendar_event_secure_code` 與既有唯一約束宣告） |
| 投影（唯一實作） | `backend/app/services/calendar_projection_service.py::CalendarProjectionService.build(org, viewer, scope, start, end)`；第二期加 `editable` 欄位與 `_merge_masked()` |
| 可見性（唯一實作） | `backend/app/services/calendar_visibility.py::apply_visibility(event, viewer)` |
| 寫入（唯一實作，第二期） | `backend/app/services/calendar_event_service.py::CalendarEventService.create/update/delete/resync_leave_adjustments`；錯誤用 `CalendarEventError.code`（`validation` / `forbidden` / `not_found` / `kind_immutable` / `not_editable`） |
| 時區工具 | `backend/app/utils/calendar_time.py`（`local_date_to_utc` / `local_naive_to_utc` / `utc_to_local` / `format_local` / `event_local_dates`） |
| API | `backend/app/api/calendar.py`：`GET /api/calendar/org/events` / `GET /api/calendar/me/events`（`?start=&end=`，當地日曆日、含、≤ 62 天）；第二期 `POST /api/calendar/events`、`PUT|DELETE /api/calendar/events/<sc>`（都掛 `page_keys_required('calendar_me')`） |
| 頁面 | `backend/app/web/calendar.py`（`/calendar/`、`/calendar/me`）、`templates/pages/calendar/calendar.html` ＋ `_event_modal.html`、`static/js/calendar.js`、`static/css/calendar.css`（前綴 `cal-`） |
| 選單 | `menu_defaults.py`：header `calendar_menu`（display_order 19）＋ `calendar` / `calendar_me`（route 型），Key1 `ORG_ADMIN`/`EMPLOYEE`，Key2 同 |
| 既有環境補選單 | `scripts/seed_missing_platform_menus.py --dry-run|--apply`（通用：補 `CORE_MENUS` 缺的 code ＋所有企業 Key2；冪等） |
| 測試 | `backend/tests/test_calendar_projection.py`、`test_calendar_pages.py`、`test_calendar_events_api.py`（第二期 16 條） |

守門：頁面與 API 都掛 `@page_keys_required('calendar' | 'calendar_me')`。SYSTEM_ADMIN／ORG_ADMIN bypass；
EXTERNAL 沒有 Key1 → API 403、頁面被 PageRoleGuard 302。

## 三、投影來源與受眾（第一期）

事件先正規化成同一個 dict（`key` / `source_type` / `calendar_kind` / `owner_*` / `event_type` / `title` /
`start_local` / `end_local` / `start_date` / `end_date` / `visibility` / `link` / `audience`），再逐筆過 `apply_visibility`。

| source_type | 來源 | kind | 誰看得到 |
|---|---|---|---|
| `manual` | `calendar_events` | 依欄位 | ORG → 全企業；PERSONAL → owner 全看；`PUBLIC` 全看；`BUSY` 他人只見 `masked=true`（無 title/note/link，`event_type='BUSY'`），且同一 owner 重疊／相接的 BUSY 會被 `_merge_masked()` 併成一筆 `source_type='busy'`；`PRIVATE` 他人一律隱藏，**ORG_ADMIN 不例外**。`editable`＝本人的 PERSONAL 或 ORG_ADMIN 看 ORG |
| `holiday` | `schedule_holidays`（org 視圖用企業預設班表；me 視圖用 `ScheduleService.get_user_schedule()`） | ORG | 全企業。`COMP_OFF` 視同 `HOLIDAY`（event_type `HOLIDAY`）；`WORKDAY` → event_type `WORKDAY` |
| `delegation` | `delegations`（非 REVOKED，日期重疊；**不讀 `status`**） | PERSONAL(owner=授權人) | audience：授權人、被授權人、ORG_ADMIN；其他人**不顯示也不遮罩**。`link` 只給 ORG_ADMIN（員工開不了 `/delegations/<sc>`） |
| `position` | `employee_positions`（只投影 `effective_until IS NOT NULL`） | PERSONAL | 本人、ORG_ADMIN |
| `broadcast` | `lookup_items`（`category_code='broadcast'`，**要先 `set_config('app.current_org')`，該表有 RLS**） | ORG | navbar 型（有 `expires_at`）→ 期間；alert 型 → 發布日點事件並過 `_user_in_target()` |
| `flow_delay` | `fw_node_execution_queue` WAITING `Delay` | ORG | **只在 org 視圖、只給 ORG_ADMIN** |

**待簽核任務刻意不投影**（Ethan 2026-09-03 定案，第一期曾有 `approval_task` 來源、同日移除）：
沒有確定開始時間的是待辦不是行事曆，而且表單量大、已有表單中心。`fw_node_execution_queue` 只投影有到期時刻的
`Delay`。日後不要以「順手」為由把 Approve／FormAdapter 加回來。

`days[]`：每日 `is_workday`（`None`＝企業沒班表的平日；**沒班表的六、日一律 `False`**，Ethan 2026-09-03 定案「六日預設用假日底色，除非補班」，而補班只能由班表假日表標記）、`holiday`、`is_today`。不逐日呼叫 `get_day_periods()`，
一次撈 range 內假日再用 `weekly_hours` 推。

## 四、時區（TZ-01）

- `start`/`end` 是企業時區（`org.get_setting('timezone')`）的當地日曆日；service 用 `_local_date_to_utc()` 換成 `[start_utc, end_utc)`。
- 回應的 `start_local`/`end_local`（`YYYY-MM-DDTHH:MM`）與 `start_date`/`end_date` 都已是當地值，**前端不做任何時區運算**，日期加減走 `Date.UTC`。
- 全天事件 `ends_at` 落在當地零點時 `end_date` 減一天（exclusive 語意），見 `_event_local_dates()`。

## 五、前端行為（實測 2026-09-02，憑證 `/opt/tmp/verify/20260902-pf229-calendar.log`）

- 月視圖 42 格（週日起），週視圖 7 欄；每格最多 3 個 chip，超過顯示 `+N 筆`。
- **超過 7 天的事件只在起日／迄日出 chip**（標「（起）」「（迄）」），否則三個月的代理職位會把每一格都佔掉；
  當日明細面板仍會列出它（`LONG_SPAN_DAYS` 在 `calendar.js`）。
- 明細面板用 `.modal-overlay`，關閉走按鈕或 ESC，沒有 `@click.away`。
- 第一期**沒有任何寫入**；第二期起的新增／編輯／刪除見第六節。

## 六、第二期（2026-09-03 上線）：事件 CRUD、請假同步班表、BUSY 合併

實測憑證 `/opt/tmp/verify/20260903-pf229-p2-api.log`（三身分 curl 矩陣）與 `20260903-pf229-p2-browser.log`（chrome-devtools 點擊）。

### 寫入規則（全在 `CalendarEventService`）

| 項目 | 規則 |
|---|---|
| PERSONAL | owner 永遠是 actor（payload 帶 `owner_user_secure_code` 直接忽略）；只有 owner 能改刪，**ORG_ADMIN 改別人的也是 404**（不洩漏存在） |
| ORG | 只有 `is_org_admin` 能建改刪（EMPLOYEE 建 → 403 `forbidden`）；`visibility` 一律存 `PUBLIC`，payload 給別的值靜默覆蓋 |
| event_type | PERSONAL 限 LEAVE/TRIP/MEETING/OTHER，ORG 限 MEETING/ORG_EVENT/OTHER；`HOLIDAY` 不開放手建（假日在班表頁維護） |
| calendar_kind | 建立後不可改（→ 400 `kind_immutable`） |
| start/end | 企業時區當地值：全天 `YYYY-MM-DD`（`ends_at` 存隔日 00:00 UTC，exclusive，與 `event_local_dates()` 互為反函式）、非全天 `YYYY-MM-DDTHH:MM`；跨度 ≤ 366 天 |
| 守門 | 三支寫入 API 都掛 `page_keys_required('calendar_me')`：SYSTEM_ADMIN／ORG_ADMIN bypass、EMPLOYEE 要持「我的行事曆」雙鑰匙、EXTERNAL 403；ORG 的管理員判定在 service |
| CSRF | 不 exempt，前端帶 `X-CSRFToken`；curl 忘了帶回 400 不是 403 |

### 請假同步（`resync_leave_adjustments(org, owner, dates)`）

- 觸發：PERSONAL 且新或舊 `event_type` 在 `LEAVE_LIKE_TYPES`（LEAVE／TRIP）的 create／update／delete；`dates`＝舊日集合 ∪ 新日集合
- **日粒度**：事件觸及的每個當地日都成為一筆 `schedule_adjustments`（`adjust_type='LEAVE'`、`status='APPROVED'`、
  `approved_by`＝本人、`original_periods`＝當時 `get_work_periods()` 的值、`note`＝事件標題、`calendar_event_secure_code`＝事件）。
  非全天 `09-10T14:00 ~ 09-11T10:00` 會產生 10 與 11 兩天（時段級扣除留給第三期）
- 表有 `(user_secure_code, adjust_date, adjust_type)` 唯一約束（model 第二期才補宣告），所以回收一律**軟刪除**、
  再次覆蓋同日一律**復活既有列**（改指向新事件），不 INSERT
- `calendar_event_secure_code IS NULL` 的列（表單／人工建的請假）**不建立、不改、不刪**
- 同一天被兩個事件覆蓋時取 `starts_at` 最早的那個當 `covered[d]`

### 前端

- `[新增事件]`（me）／`[新增企業事件]`（org 且 ORG_ADMIN）在工具列；當日面板底部 `[在這天新增]` 預填成該日全天事件
- 面板每筆 `editable` 事件有 `[編輯]` `[刪除]`（`x-show="ev.editable"`）；遮罩事件 `editable` 恆 false
- 表單 modal 在 `_event_modal.html`：類型 select 依 kind 用兩組**靜態** option（`x-if` 切換）；全天與非全天各一組 input（`x-show` 切換），
  切換 checkbox 時 `onAllDayToggle()` 把值換成該 input 型別吃得下的格式（否則 `<input type="date">` 收到含時間的字串會顯示空白）
- 關閉走 [取消]／×／ESC（`@keydown.escape.window` 同時關面板與表單），無 `@click.away`

### 既有環境升級（bpserv）

`install.sh --update` 的 create_all 只補新表不補欄位，第二期要另外對 DB 下：

```sql
ALTER TABLE schedule_adjustments ADD COLUMN IF NOT EXISTS calendar_event_secure_code VARCHAR(32);
CREATE INDEX IF NOT EXISTS ix_schedule_adjustments_calendar_event_secure_code ON schedule_adjustments (calendar_event_secure_code);
-- 2026-09-02 之前 fresh 安裝的環境沒有這條唯一約束（model 第二期才宣告；bpserv 2026-09-03 PF-232 補過）
ALTER TABLE schedule_adjustments ADD CONSTRAINT schedule_adjustments_user_secure_code_adjust_date_adjust_ty_key
  UNIQUE (user_secure_code, adjust_date, adjust_type);
```

bpserv 已於 2026-09-03（PF-232）補齊三者，之後新裝的環境由 `create_all()` 直接建出。

## 六之二、第三期入口

規格在 BBN #5380 第三期段。代理建議、工作時間逾時、TimeContext、簽核紀錄補 `delegate_from_*`。
動工前先讀本檔第三節的受眾表與第六節的寫入規則——衍生功能一律從 `CalendarEventService` 的寫入點掛 hook，
不要另開寫入路徑。

**2026-09-03 Ethan 定案**（全文 BBN #5385 / PF-233）：

| # | 問題 | 定案 |
|---|---|---|
| Q1 | 請假同步粒度 | **改時段級（B）**：`adjusted_periods` 存剩餘工作時段，`schedule_service.get_work_periods()` 的 LEAVE 分支改回 `adjusted_periods or []`；resync 做同日多事件聯集與當地時間減法。是第 3 項與第 2 項的前置 |
| Q2 | 「本人是簽核者」的判定 | 聯集：WAITING 任務 `is_pending_assignee()` ∪ 發行快照 Approve／FormAdapter 的 `USER` 指名本人 ∪ `ROLE` 為本人持有角色；不解析主管鏈 |
| Q3 | 代理建議 UX | 存檔後 toast；`/delegations/` 雙鑰匙僅 ORG_ADMIN，所以員工只有文字提示、[建立代理授權] 連結只給 ORG_ADMIN（query string 預填 ＋ `next` 回流）；企業行事曆面板對別人未遮罩的 LEAVE／TRIP 也給 ORG_ADMIN 同款連結 |
| Q4 | `timeout_mode` | 簽核節點 config；先做 ABSOLUTE（預設）／WORKING，BOTH 不做；簽核者無班表退回 ABSOLUTE |
| Q5 | 計算時機 | 進 WAITING 算一次寫 `scheduled_at`；executor 喚醒時重算剩餘工作秒數，>0 就往後推。`schedule_service` 用 naive 本地時間，`scheduled_at` 是 UTC，呼叫前後要換算 |
| Q6 | `delegate_from_*` | 原簽核者 user secure_code ＋ display_name |
| Q7 | 面板 [在這天新增] 後 | 維持不關閉 |

動工順序：**1（代理建議）→ 4（delegate_from_*）→ B（時段級請假）→ 3（TimeContext）→ 2（timeout_mode）**。

## 六之三、第三期第 1 項：代理建議（2026-09-03 完成）

| 層 | 實作 |
|---|---|
| 判定（唯一實作） | `backend/app/services/approver_exposure_service.py::ApproverExposureService.describe(org, user, start, end)` → `needed / already_delegated / pending_count / template_count`。a. WAITING 的 Approve／FormAdapter 任務逐筆 `task_authorizer.is_pending_assignee()`；b. `fw_published_form_workflows.status='Published'` 的 `workflow_snapshot.graph.nodes` 中 `assignee_type='USER'` 指名本人或 `'ROLE'` 為本人持有角色（其他型別不算）；c. 本人為授權人、未撤銷、效期涵蓋整段的 `delegations` 存在則 `needed=False`。form_workflow 在函式內 lazy import，`ImportError` 視為 0 |
| 掛點 | `CalendarEventService.delegation_hint(org, actor, row)`：PERSONAL 且 LEAVE／TRIP 才有值；`POST/PUT /api/calendar/events` 回應多 `delegation_hint`（可為 null），API 層只在 `is_org_admin` 時補 `create_url`（`url_for('delegations.create_delegation', delegator=, effective_from=, effective_until=, reason=, next=url_for('calendar_web.my_calendar'))`） |
| 前端 | `calendar.js::showHint()` 存檔後顯示 15 秒 toast（`common.css` 的 `.toast.warning` ＋ `calendar.css` 的 `.cal-toast`）；有 `create_url` 才有 [建立代理授權] 連結，否則句尾接「請通知管理員建立代理授權」。`delegationLinkFor(ev)`：ORG_ADMIN 在面板看**別人**未遮罩的 manual LEAVE／TRIP 才回 URL（`next=location.pathname`） |
| 代理授權頁 | `web/delegations.py::create_delegation()` 以 `prefill` dict 餵模板（POST 值優先、其次 query string `delegator / effective_from / effective_until / reason / next`）；`_safe_next()` 只收單一 `/` 開頭、無 `//`、`\`、空白與控制字元；建立成功 `redirect(next)`，否則回列表 |

三件要知道的：

- **`/delegations/` 雙鑰匙只開給 ORG_ADMIN**（Key1／Key2 三家企業都只有 ORG_ADMIN），所以員工端刻意只有文字提示、沒有連結——給員工連結會 302 到登入頁。Ethan 2026-09-03 21:50 定案**要開放**員工自助建立代理授權（授權人限本人），待辦 PF-236、尚未實作；做法見該卡選項 B（後端強制 `delegator_secure_code = current_user.secure_code`，`/delegations/` 管理頁維持 ORG_ADMIN，注意 PERM-03 與 DATA-01）
- 判定是**提示等級**，誤報可接受：BELUGA 的 `user@beluga.com`（只有 EMPLOYEE 角色）也會 `needed=true`，因為有發行流程把簽核指派給 `EMPLOYEE` 角色。不要為了消除這種案例去改判定
- `web/dev.py::_is_safe_relative_path()` 是另一份較寬鬆的同類判定（dev 工具專用）。日後第三處需要 `next` 防護時先抽成 `app/utils/` 共用，不要再複製第三份
- 驗收憑證 `/opt/tmp/verify/20260903-pf229-p3-item1.log`（curl 10 步＋瀏覽器 B1～B4：員工 toast 無連結、員工面板無連結、管理員面板連結 href 正確、管理員 toast 連結 → 代理頁預填 → 送出回流 `/calendar/me`）；測試 `test_calendar_events_api.py` 新增 7 條、`test_delegations_prefill.py` 3 條

## 七、已知取捨

- ORG_ADMIN 的「我的行事曆」也會看到別人的代理授權（audience 規則不分 scope）。要改就在 `_delegation_events` 依 scope 收斂。
- `alert` 型廣播只落在發布日，不做期間（它沒有結束時間）。
- `calendar_events` 沒有 RLS policy（與 delegations／work_schedules 相同現況），隔離靠 service 層顯式 `org_secure_code` 過濾。
- 第二期的 BUSY 合併只看 `start_local`／`end_local` 字串比較，全天 BUSY（`end_local` 是隔日 00:00）會與隔日 00:00 開始的事件「相接」而併入，這是刻意的（外人本來就只該看到一段「有安排」）。
- 請假同步目前仍是日粒度：半天假也讓 `get_work_periods()` 回空。2026-09-03 已定案改時段級（六之二 Q1），排在第三期第 3、2 項之前實作；做完後刪掉這條。
- `original_periods` 在企業沒有預設班表時是 `[]`（dev BELUGA 就是這樣），不影響功能。
