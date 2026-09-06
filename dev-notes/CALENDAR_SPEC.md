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
- **時段級**：事件觸及的每個當地日仍成為一筆 `schedule_adjustments`（`adjust_type='LEAVE'`、`status='APPROVED'`、
  `approved_by`＝本人、`note`＝事件標題、`calendar_event_secure_code`＝事件）。`original_periods`＝同步當下排除 LEAVE 後的底，
  `adjusted_periods`＝扣掉同日所有 LEAVE／TRIP 請假區間聯集後的剩餘工作時段。全天事件扣成 `[]`；既有資料
  `adjusted_periods IS NULL` 仍視為整天請假。跨日事件依企業時區切成各當地日區間；跨日班別若被請假切開，午夜後剩餘段不保留。
  `ScheduleService.get_work_periods()` 先看 LEAVE，LEAVE 列優先於同日其他調整。
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
| Q1 | 請假同步粒度 | **改時段級（B）**：`adjusted_periods` 存剩餘工作時段，`schedule_service.get_work_periods()` 的 LEAVE 分支改回 `adjusted_periods or []`；resync 做同日多事件聯集與當地時間減法。是第 3 項與第 2 項的前置。**2026-09-03 完成**：純函式 `app/utils/work_periods.py`（parse／format／merge／subtract，禁輸出 `24:00`）、`ScheduleService.get_base_work_periods()`（排除 LEAVE 的底，resync 算底專用）、`_event_leave_intervals()`；GHTRAVEL 實測半天假 → `["12:00-14:00","15:00-18:00"]`（與同日外出聯集）、跨日 → 前日 `["09:00-16:00"]`／次日 `["10:00-18:00"]`，憑證 `/opt/tmp/verify/20260903-pf229-itemB-leave-periods.log`；codex 交付時把「軟刪除列復活」多加了「限行事曆來的列」條件（人工列軟刪除那天會因唯一約束建不出請假列），驗收改回並補回歸測試 |
| Q2 | 「本人是簽核者」的判定 | 聯集：WAITING 任務 `is_pending_assignee()` ∪ 發行快照 Approve／FormAdapter 的 `USER` 指名本人 ∪ `ROLE` 為本人持有角色；不解析主管鏈 |
| Q3 | 代理建議 UX | 存檔後 toast；`/delegations/` 雙鑰匙僅 ORG_ADMIN，所以員工只有文字提示、[建立代理授權] 連結只給 ORG_ADMIN（query string 預填 ＋ `next` 回流）；企業行事曆面板對別人未遮罩的 LEAVE／TRIP 也給 ORG_ADMIN 同款連結 |
| Q4 | `timeout_mode` | 簽核節點 config；先做 ABSOLUTE（預設）／WORKING，BOTH 不做；簽核者無班表退回 ABSOLUTE |
| Q5 | 計算時機 | 進 WAITING 算一次寫 `scheduled_at`；executor 喚醒時重算剩餘工作秒數，>0 就往後推。`schedule_service` 用 naive 本地時間，`scheduled_at` 是 UTC，呼叫前後要換算 |
| Q6 | `delegate_from_*` | 原簽核者 user secure_code ＋ display_name。**2026-09-03 完成**（六之五） |
| Q7 | 面板 [在這天新增] 後 | 維持不關閉 |

動工順序：**1（代理建議）→ 4（delegate_from_*）→ B（時段級請假）→ 3（TimeContext）→ 2（timeout_mode）**。

## 六之三、第三期第 1 項：代理建議（2026-09-03 完成）

| 層 | 實作 |
|---|---|
| 判定（唯一實作） | `backend/app/services/approver_exposure_service.py::ApproverExposureService.describe(org, user, start, end)` → `needed / already_delegated / pending_count / template_count`。a. WAITING 的 Approve／FormAdapter 任務逐筆 `task_authorizer.is_pending_assignee()`；b. `fw_published_form_workflows.status='Published'` 的 `workflow_snapshot.graph.nodes` 中 `assignee_type='USER'` 指名本人或 `'ROLE'` 為本人持有角色（其他型別不算）；c. 本人為授權人、未撤銷、效期涵蓋整段的 `delegations` 存在則 `needed=False`。form_workflow 在函式內 lazy import，`ImportError` 視為 0 |
| 掛點 | `CalendarEventService.delegation_hint(org, actor, row)`：PERSONAL 且 LEAVE／TRIP 才有值；`POST/PUT /api/calendar/events` 回應多 `delegation_hint`（可為 null），API 層依身分補 `create_url`：ORG_ADMIN → `url_for('delegations.create_delegation', delegator=, effective_from=, effective_until=, reason=, next=url_for('calendar_web.my_calendar'))`；EMPLOYEE → `url_for('main.personal_settings', delegation='new', effective_from=, effective_until=, reason=, next=, _anchor='my-delegations')`（PF-236，六之四）；其餘 `None` |
| 前端 | `calendar.js::showHint()` 存檔後顯示 15 秒 toast（`common.css` 的 `.toast.warning` ＋ `calendar.css` 的 `.cal-toast`）；有 `create_url` 才有 [建立代理授權] 連結，否則句尾接「請通知管理員建立代理授權」。`delegationLinkFor(ev)`：ORG_ADMIN 在面板看**別人**未遮罩的 manual LEAVE／TRIP 才回 URL（`next=location.pathname`） |
| 代理授權頁 | `web/delegations.py::create_delegation()` 以 `prefill` dict 餵模板（POST 值優先、其次 query string `delegator / effective_from / effective_until / reason / next`）；`_safe_next()` 只收單一 `/` 開頭、無 `//`、`\`、空白與控制字元；建立成功 `redirect(next)`，否則回列表 |

三件要知道的：

- **`/delegations/` 雙鑰匙只開給 ORG_ADMIN**（Key1／Key2 三家企業都只有 ORG_ADMIN），給員工那條連結會 302 到登入頁。第 1 項上線當天員工端只有文字提示；同日 Ethan 定案開放員工自助（PF-236），員工端的 `create_url` 改指向個人設定頁，見六之四
- 判定是**提示等級**，誤報可接受：BELUGA 的 `user@beluga.com`（只有 EMPLOYEE 角色）也會 `needed=true`，因為有發行流程把簽核指派給 `EMPLOYEE` 角色。不要為了消除這種案例去改判定
- `web/dev.py::_is_safe_relative_path()` 是另一份較寬鬆的同類判定（dev 工具專用）。日後第三處需要 `next` 防護時先抽成 `app/utils/` 共用，不要再複製第三份
- 驗收憑證 `/opt/tmp/verify/20260903-pf229-p3-item1.log`（curl 10 步＋瀏覽器 B1～B4：員工 toast 無連結、員工面板無連結、管理員面板連結 href 正確、管理員 toast 連結 → 代理頁預填 → 送出回流 `/calendar/me`）；測試 `test_calendar_events_api.py` 新增 7 條、`test_delegations_prefill.py` 3 條

## 六之四、PF-236：員工自助建立代理授權（授權人限本人，2026-09-03 完成）

| 層 | 實作 |
|---|---|
| API（唯一寫入路徑） | `backend/app/api/my_delegations.py`（`/api/my-delegations`，全部 `@login_required` ＋ `_deny_non_member()`：只有 `is_employee` 或 `is_org_admin` 可用，EXTERNAL／SYSTEM_ADMIN 一律 403 `forbidden`）。`GET`（`given`＝我授權的、`received`＝我代理的、`today`）／`GET /candidates`／`POST`（建立）／`POST /<sc>/revoke`。走 `ResourceGateway`（`Delegation`、`User` 都在 `LIST_RBAC_ENFORCED_MODELS`，所以一律 `check_permission=False` 並註解理由），CSRF 不 exempt |
| 建立規則 | `delegator_secure_code` **強制** `current_user.secure_code`（payload 的 `delegator_secure_code`／`delegation_type`／`org_secure_code` 一律忽略）；`delegation_type` 固定 `FULL`；被授權人必須在 `_candidate_users()` 集合內（同企業、`is_active`、未刪除、非服務帳號、`user_type` ∈ EMPLOYEE／ORG_ADMIN、非本人），否則 400 `invalid_delegate`（不區分原因）；`effective_until` 不得早於 `organization.local_today()`（400 `expired_range`）；建立後 `check_and_update_status()` |
| 撤銷 | 只能撤 `delegator == 本人` 的未刪除記錄，其餘 404（含自己是被授權人的那筆）；已撤銷再撤 400 `already_revoked` |
| 頁面 | `/personal-settings` 新區塊 `id="my-delegations"`（partial `pages/_my_delegations.html`，只在 `is_employee or is_org_admin` 時 include）＋ `static/js/my-delegations.js`／`css/my-delegations.css`（`mdl-` 前綴）。query string `?delegation=new&effective_from=&effective_until=&reason=&next=#my-delegations` 會開 modal 預填並捲到區塊；`next` 走與後端 `_safe_next()` 同規則的 `safeNext()`，建立成功後 `location.href = next` |
| 行事曆 | `api/calendar.py::_delegation_hint()` 第二分支：EMPLOYEE 的 `create_url` 指向上述 query string；`calendar.js::showHint()` 不變（有 `create_url` 就顯示 [建立代理授權]） |
| 守門宣告表 | 四條 `api_my_delegations.*` 標 `review: confirmed`、`max_audience: [EMPLOYEE, ORG_ADMIN]`；403 藏在 helper 內，掃描器的 `has_internal_check` 抓不到，note 有寫 |

三件要知道的：

- **`/delegations/` 管理頁與列表維持 ORG_ADMIN 不動**；員工自助只給「授權人＝本人」這一種，限額／特定代理仍由管理員建
- 撤銷「自己授權出去的」是 Claude 加的（Ethan 定案只寫建立），理由是員工建錯只能找管理員收拾；不要的話拿掉 `revoke_my_delegation` 與模板的 [撤銷] 即可
- 憑證 `/opt/tmp/verify/20260903-pf236-my-delegations.log`（curl 21 步：五種身分矩陣、冒用授權人、候選人排除、CSRF、hint URL；瀏覽器 B1～B2：toast 連結 → 預填 modal → 建立回流 `/calendar/me` → 行事曆投影出現 → 撤銷）；測試 `test_my_delegations_api.py` 13 條、`test_calendar_events_api.py` 員工 hint 斷言改為 personal-settings URL。codex 派工時把守門表的 `note`／`max_audience`／`confirmed` 寫到檔案開頭四條無關的 access_center 端點（「機制對、目標錯」），驗收時發現並改回

## 六之五、第三期第 4 項：簽核紀錄補寫 `delegate_from_*`（2026-09-03 完成）

| 層 | 實作 |
|---|---|
| 判定（唯一實作） | `modules/form_workflow/services/task_authorizer.py::resolve_acting_identity(task, user, org, actor=None)` → `{'via': 'self'}` 或 `{'via': 'delegation', 'delegator_secure_code': sc}`；本人優先，多位授權人依 secure_code 排序取第一個（決定性）。`can_act_on_task()` 改為它的薄包裝（`is not None`），清單／詳情／鎖定端點繼續用 bool 版 |
| 欄位值 | `delegate_from_fields(identity, org)`：本人簽核回 `{}`；代理簽核回 `{'delegate_from_secure_code': 授權人 sc, 'delegate_from_name': display_name or username}`。查 `User` 刻意不加 `is_active`（記錄用，授權已在 `get_delegated_identities()` 判過），找不到就用 sc 當名字 |
| 寫入點（三處人工簽核） | `fc_pending.py::approve_task()`、`fc_batch.py::batch_approve_tasks()`（沿用 actor，無 N+1）、`instance_routes.py::approve_task()`：`FwApprovalRecord(..., **delegate_from_fields(...))`，`task.result` 多 `delegate_from`。FORCE_END／portal 撤單／SqlExecutor／AiAgent 的自動紀錄不涉及代理，未動 |
| 呈現 | `FwApprovalRecord.to_dict()`、`fc_pending.get_pending_task`、`fc_monitor` 兩處序列化多 `delegate_from_name`；`_read_form_modal` / `_form_center_approval_modal` / `_monitor_modal`（form_workflow）與 `security_cases.html`（open_defense，吃同一支 form-detail API）在簽核者後接「（代 X 簽核）」（`fc-delegate-tag` / `sc-approval-delegate`） |
| SQL Sync | `converter.py` / `sync_service.py` 早已同步這兩欄，本項讓值不再恆為 NULL，不必改 |

實測（`/opt/tmp/verify/20260903-pf229-item4-delegate-from.log`）：ethanyu 用 PF-236 的 API 建當日代理給 `user@beluga.com`（無 SECURITY_STAFF），
user 簽 OD-20260903-0002「上班後複核」（選「維持觀察」）→ `fw_approval_records`：`approver=user`、`delegate_from_secure_code=ethanyu sc`、
`delegate_from_name=ethanyu`；`fw_node_execution_queue.result.delegate_from` 同值。測試 `test_task_authorizer_delegate_from.py` 7 條（含本人優先、排序決定性、SPECIFIC／過期不放行、停用授權人仍記名）。

兩件要知道的：

- **OD 案件的待簽在表單中心清單是刻意不顯示的**（`fc_pending.list_pending_tasks` 的資安分類隔離），代理人要從資安案件處置中心接手；`can_act_on_task` 對代理人回 True 但清單看不到，不是代理判定壞了
- `fc_monitor.get_workflow_progress()`（`/api/form-center/workflow-progress/<sc>`）序列化用的是 `approval.decision` / `approval.approved_at`，`FwApprovalRecord` 沒有這兩個屬性——**既有潛在 500**，本項只加了 `delegate_from_name` 沒動它（待辦另記 → PF-237，2026-09-04 確認全專案無人呼叫，端點已刪除）

## 六之六、第三期第 3 項：TimeContext 起步（2026-09-03 完成）

唯一實作 `backend/app/services/time_context_service.py::TimeContextService`（`who_on_duty` / `who_on_leave` / `snapshot`，naive UTC 進出）與 `GET /api/calendar/time-context?at=YYYY-MM-DDTHH:MM`（企業當地時間，**`@admin_required` 專用**——`who_on_leave` 會揭露成員此刻在假中，含 PRIVATE 事件）。`who_on_leave` 看行事曆 LEAVE／TRIP 事件是否涵蓋這一刻＋當地日的人工 LEAVE 列，**刻意不看** `schedule_adjustments.adjusted_periods`（沒有班表的企業判不出來）；`who_on_duty` 逐人 `ScheduleService.is_working_time()`（已含時段級請假）。設計與取捨全文在 `dev-notes/knowledge/time-context-architecture.md` 檔尾；尚未接任何消費端（OD 路由／簽核者解析另案）。憑證 `/opt/tmp/verify/20260903-pf229-item3-time-context.log`（GHTRAVEL 22 人值班、領隊半天假期間內外切換、下班／週末空、EMPLOYEE／EXTERNAL 403）。

## 六之七、第三期第 2 項：簽核節點逾時 `timeout_mode`（2026-09-03 完成）

| 層 | 實作 |
|---|---|
| 節點 config（`FormAdapter`） | `timeout_enabled`（bool）、`timeout_minutes`（1～14400）、`timeout_mode`（`ABSOLUTE`＝24/7 倒數／`WORKING`＝只在簽核者班表內倒數，含時段級請假）、`timeout_path_id`（自定義決策的 option id，或出線 edge id）。`validate()` 檢查三者；去向不在 `available_paths` 內時**不啟動倒數但不擋簽核**（log ERROR） |
| 期限計算（唯一實作） | `formadapter_handler.compute_timeout_deadline(user, now_utc, minutes, mode, tz)`：WORKING 用 `ScheduleService.estimate_working_end_time()`（naive 當地時間，換算走 `calendar_time`）；簽核者順序取第一個有共用班表的人當參考（`timeout_reference_user`），沒有就退回 ABSOLUTE（Q4 定案）。結果寫進 `result.data`：`timeout_at`／`timeout_started_at`／`timeout_mode_effective` 等 |
| 喚醒 | `WorkflowExecutor.formadapter_timeout_due_clause(now)`：WAITING 的 FormAdapter 且 `result->data->>timeout_at`（cast timestamp）到期。**刻意不動 `scheduled_at`**——表單中心待簽清單拿它當送件時間顯示。兩處輪詢查詢都加了這條（不是加進 node_type 清單） |
| 重入（`_handle_timeout_reentry`） | 期限未到→原 data 原樣回 `waiting_form_action`（不重設 `waiting_since`、不重解析簽核者）；WORKING 用 `recompute_working_deadline()` 重算剩餘工作秒數（Q5 定案），>0 就往後推再等（等待期間請假／改班表都會反映）；真逾時→寫 `fw_approval_records`（`action='timeout'`、`approver_secure_code=NULL`、`approver_name='系統（逾時自動處理）'`）、設 `output_variable`、`selected_edges`＝去向的 target_edges；**未配對出線的決策＝REJECTED 終態**（回 `complete_workflow` + `workflow_status='REJECTED'`，與人工駁回同語意） |
| 設計器 | `wf-form-adapter.js` 基本設定分頁新增「簽核逾時」區塊（去向清單依「自定義決策／出線」在開啟時算一次，改了要重開）；`wf-node-form-adapter.js::applyFormAdapterConfig()` 與 `wf-save.js` 都寫入四個 key |
| 簽核歷程 | `fc-utils.js::getActionText` 認得 `timeout`（「逾時自動處理」）、model `ACTION_NAMES` 同步 |

三件要知道的：

- **競態**：期限到時若簽核者正在填寫（表單已鎖定），executor 仍會喚醒並自動處理，簽核者送出時會拿到「找不到任務或已處理」。逾時通常以小時／天計，暫不處理；要保護鎖定中的任務，在 `_handle_timeout_reentry` 開頭檢查 `queue_item.is_locked` 往後推即可
- **既有 WAITING 簽核不受影響**：沒有 `timeout_at` 的列永遠不符合喚醒條件；也不需要資料回填
- 憑證 `/opt/tmp/verify/20260903-pf229-item2-timeout.log`（拋棄式實例：executor 喚醒 → 走逾時出線 → 簽核紀錄 `timeout` → End 完成）；測試 `test_formadapter_timeout.py` 12 條（ABSOLUTE／WORKING／無班表退回／請假扣除／重算往後推／重入未逾時／出線與自定義決策／終態駁回／去向不存在／validate／executor 條件）。codex 當時 OpenAI 端 404，由 Claude 直接實作

## 七、已知取捨

- ORG_ADMIN 的「我的行事曆」也會看到別人的代理授權（audience 規則不分 scope）。要改就在 `_delegation_events` 依 scope 收斂。
- `alert` 型廣播只落在發布日，不做期間（它沒有結束時間）。
- `calendar_events` 沒有 RLS policy（與 delegations／work_schedules 相同現況），隔離靠 service 層顯式 `org_secure_code` 過濾。
- 第二期的 BUSY 合併只看 `start_local`／`end_local` 字串比較，全天 BUSY（`end_local` 是隔日 00:00）會與隔日 00:00 開始的事件「相接」而併入，這是刻意的（外人本來就只該看到一段「有安排」）。
- 請假同步的 `adjusted_periods` 是同步當下算出的快照；之後班表或假日改了不會自動重算，只有事件改動才重算。
- 跨日班別被請假切開時，午夜後的剩餘段落不保留。
- `original_periods` 在企業沒有預設班表時是 `[]`（dev BELUGA 就是這樣），不影響功能。

## 八、企業假日表（PF-235，2026-09-04）

三層模型：

1. `work_schedules` 是真正的上下班時間，帳號指定班表時最優先。
2. `holiday_calendars` / `holiday_calendar_entries` 是企業假日表底稿；管理員可從台灣政府行事曆 URL 抓取，或上傳自訂 CSV/JSON。
3. 企業預設班表仍由 `ScheduleService.ensure_default_schedule(org)` 提供，沒有指定班表的帳號走預設班表。

發佈不是讀取端多查一張表，而是把 PUBLISHED 條目寫進目標班表的 `schedule_holidays`，並在 `schedule_holidays.holiday_calendar_secure_code` 標記來源；NULL 代表手動設定。`WorkSchedule.get_day_periods()`、`ScheduleService`、行事曆投影維持只讀 `schedule_holidays`。

兩張新表：

- `holiday_calendars`：`source` 為 `TW_GOV` / `CUSTOM`，`status` 為 `DRAFT` / `PUBLISHED`；同企業同年度未刪除的 `TW_GOV` 只有一份。
- `holiday_calendar_entries`：同一假日表、同一 stage、同一天唯一；底稿重匯與發佈複製都是硬刪舊 entries 再插入。

發佈規則：

- 發佈時先把 DRAFT 複製成 PUBLISHED，再軟刪所有來自本假日表的 `schedule_holidays`，最後寫入本次目標班表。
- 班表上同日若已有手動列（來源 NULL）一律保留並略過。
- 同日若已有另一份假日表來源，自訂表優先於政府表；同級或本份較高時取代，較低時略過。
- `WORKDAY` 條目若未帶 `work_periods`，發佈時用目標班表 `weekly_hours['mon']` 推導，沒有週一就取一週第一個非空工作時段；全週都空則略過。

重算規則：

- 發佈與下架後，受影響日期是舊 PUBLISHED 日期與新 PUBLISHED 日期聯集，受影響班表是舊目標與新目標聯集。
- 受影響使用者限同企業、未刪除、啟用中；指定受影響班表的人，加上「未指定班表且企業預設班表受影響」的人。
- 只有在受影響日期已有行事曆同步請假列（`calendar_event_secure_code IS NOT NULL`、`adjust_type='LEAVE'`、未刪除）的人，才呼叫 `CalendarEventService.resync_leave_adjustments(org, user_sc, dates)`。

API 清單：

- `GET /api/admin/holiday-calendars/`（列表）、`POST /api/admin/holiday-calendars/fetch-taiwan`（抓取台灣政府行事曆，只有年份可變）
- `POST /api/admin/holiday-calendars/import`
- `GET/PUT/DELETE /api/admin/holiday-calendars/<sc>`
- `POST /api/admin/holiday-calendars/<sc>/draft-entries`
- `PUT/DELETE /api/admin/holiday-calendars/<sc>/draft-entries/<esc>`
- `POST /api/admin/holiday-calendars/<sc>/publish`
- `POST /api/admin/holiday-calendars/<sc>/unpublish`

既有環境升級：

- 新表由 `install.sh --update` 觸發 ORM `db.create_all()` 建出。
- 既有 `schedule_holidays` 欄位需手動補：

```sql
ALTER TABLE schedule_holidays ADD COLUMN IF NOT EXISTS holiday_calendar_secure_code VARCHAR(32);
CREATE INDEX IF NOT EXISTS ix_schedule_holidays_holiday_calendar_secure_code ON schedule_holidays (holiday_calendar_secure_code);
```

第一批（同日）配套：企業設定新增 `country`（ISO 3166-1 alpha-2，預設 `TW`，`/admin/settings` 可改；唯一對照表
`backend/app/utils/regions.py`），`ScheduleService.ensure_default_schedule(org)` 在 `create_organization()` 建企業時
自動種一張 `DEFAULT` 預設班表（週休日依 `country`，工時 09-12／13-18），既有環境用
`scripts/seed_default_work_schedules.py --dry-run` → `--apply` 補種（系統企業刻意跳過）。

已知取捨（2026-09-04 驗收時確認，皆為刻意）：

- **下架較高優先的假日表不會恢復被它取代的列**：自訂表在同日取代了政府表的列（那列被軟刪除），自訂表下架後那天就沒有假日，
  要重新發佈政府表才會回來。驗收憑證 `/opt/tmp/verify/20260904-pf235.log`（01-01 案例）。
- 重匯到既有假日表時 `source` 必須與該表相同，否則 `invalid_source`（避免把政府表底稿換成自訂內容）。
- 解析錯誤的細節不在 service 組中文：`HolidayCalendarError.detail` 帶 `{'reason': 'bad_header'|'bad_columns'|'duplicate_date'|'bad_row', 'line': n}`，
  API 層 `_parse_failed_message()` 才翻譯。
- 班表頁的年度 select 只決定「從網路取得」抓哪一年，假日表列表一律列出全部（含跨年度的自訂表）。
- 政府表匯入時落在週六日但有假名的日子（例如週六的春節）也收為 `HOLIDAY`，所以 2026 年是 22 筆（16 假日＋6 補假），不是平日的 16 筆；
  週末且 `description` 空的 104 天一律跳過。
- 舊的 `holidays.js::importTWHolidays()`（寫死且與官方不符的 2026 清單）與 model 內的 `DEFAULT_TW_HOLIDAYS_2026` 已刪除。

## 九、PF-251 第 3b 期後的變更（2026-09-07）：`delegations` 退役，代理改讀 `user_role_assignments` 的 proxy 列

第六節（六之一投影表的 `delegation` 列、六之三代理建議、六之四員工自助）描述的是 2026-09-03 的實作，**2026-09-07 起以本節為準**，那幾段僅供考古：

| 舊（六之一～六之四） | 現在 |
|---|---|
| 投影 `source_type='delegation'`／`event_type='DELEGATION'`，讀 `delegations` | `calendar_projection_service._proxy_events()`：讀 `user_role_assignments` `assignment_kind='proxy'`、未刪、效期與區間相交；**同一 (代理人, 被代理人, valid_from, valid_until) 合併成一筆** `source_type='proxy'`／`event_type='PROXY'`（`key=proxy:<第一列 sc>`），title「X 代理 Y」、`note` 列出「角色名@單位名」以「、」串接；audience 仍是被代理人、代理人、ORG_ADMIN；`link` 只給 ORG_ADMIN 且指 `/access/`（權限中心無帳號 deep link） |
| `CalendarEventService.delegation_hint()`、回應 key `delegation_hint`、`already_delegated` | `proxy_hint()`、`proxy_hint`、`already_covered`；涵蓋判定改 `proxy_assignment_service.has_covering_proxy()`：本人**每一列**可代理的 regular 角色（排除四個層界身分角色）都要有一列 `acting_for=本人` 的 proxy 效期涵蓋整段才算 True |
| `create_url`：ORG_ADMIN → `/delegations/create?delegator=…`；EMPLOYEE → 個人設定 `?delegation=new…#my-delegations` | **兩種身分同一條**：`url_for('main.personal_settings', proxy='new', effective_from=, effective_until=, reason=, next=, _anchor='my-proxy-assignments')`；其餘身分 `None` |
| `calendar.js::delegationLinkFor()`（管理員在面板對別人的 LEAVE／TRIP 給 [建立代理授權]） | **刪除**；toast 的連結文字改 [設定代理人]，無連結時句尾「請通知管理員建立代理指派」；圖例「代理指派」、CSS class `.cal-ev--proxy` |
| `/api/my-delegations`、`_my_delegations.html`／`my-delegations.js`／`my-delegations.css`（`mdl-`） | `/api/my-proxy-assignments`（`GET` given／received／`today`、`GET /candidates`、`GET /my-roles`、`POST`、`POST /<assignment_sc>/revoke`）、`_my_proxy_assignments.html`／`my-proxy-assignments.js`／`my-proxy-assignments.css`（`mpa-`）；建立＝對本人每一列可代理的 regular 角色各建一列 proxy（`source_ref='self:<sc>'`，事由必填，重疊效期的列略過並回 `skipped`），撤銷 given／放棄 received 同一支 revoke；唯一實作 `backend/app/services/proxy_assignment_service.py` |
| `/delegations/` 管理頁、`test_delegations_prefill.py`、`test_my_delegations_api.py`、`test_delegation_effective_status.py` | 頁面退役（404）；測試改 `test_my_proxy_assignments_api.py`、`test_delegation_migration.py`，行事曆兩檔改 proxy 語意 |

設計與分期見 `dev-notes/ROLE_PROXY_ASSIGNMENT_DESIGN.md`（第十一節「第 3b 期」有驗收憑證與待決點）。
