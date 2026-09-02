# 企業行事曆／我的行事曆（PF-229）— 第一期實作記錄與二、三期指引

> 2026-09-02 建立。第一期（資料模型 + 唯讀投影）已上線；二、三期規格見 BBN #5380（`note_get(5380)`）。
> 手冊頁：`docs/manual/07_daily_work/calendar.md`；manifest：`dev-notes/manifests/calendar.yaml`。

## 一、定位（不要把效期判定搬進來）

| 層 | 內容 | 規則 |
|---|---|---|
| 效期判定 | 合約、角色指派、職位、代理「今天有沒有效」 | **不走行事曆**。各自用 `Organization.local_today()` 即時判定（合約 PF-125、代理 2026-09-02、角色指派 `UserRoleAssignment.is_valid_on()` 同日對齊） |
| 規劃時間 | 誰請假、誰出差、公司放假、公司活動、簽核期限 | 行事曆是唯一入口與來源 |
| 呈現與私密 | 月／週視圖、公開／僅顯示已排程／私人 | 行事曆 UI |

## 二、檔案

| 角色 | 檔案 |
|---|---|
| model | `backend/app/models/calendar_event.py`（`calendar_events`；`CalendarKind` / `CalendarEventType` / `CalendarVisibility`） |
| 投影（唯一實作） | `backend/app/services/calendar_projection_service.py::CalendarProjectionService.build(org, viewer, scope, start, end)` |
| 可見性（唯一實作） | `backend/app/services/calendar_visibility.py::apply_visibility(event, viewer)` |
| API | `backend/app/api/calendar.py`：`GET /api/calendar/org/events` / `GET /api/calendar/me/events`（`?start=&end=`，當地日曆日、含、≤ 62 天） |
| 頁面 | `backend/app/web/calendar.py`（`/calendar/`、`/calendar/me`）、`templates/pages/calendar/calendar.html`、`static/js/calendar.js`、`static/css/calendar.css`（前綴 `cal-`） |
| 選單 | `menu_defaults.py`：header `calendar_menu`（display_order 19）＋ `calendar` / `calendar_me`（route 型），Key1 `ORG_ADMIN`/`EMPLOYEE`，Key2 同 |
| 既有環境補選單 | `scripts/seed_missing_platform_menus.py --dry-run|--apply`（通用：補 `CORE_MENUS` 缺的 code ＋所有企業 Key2；冪等） |
| 測試 | `backend/tests/test_calendar_projection.py`、`test_calendar_pages.py` |

守門：頁面與 API 都掛 `@page_keys_required('calendar' | 'calendar_me')`。SYSTEM_ADMIN／ORG_ADMIN bypass；
EXTERNAL 沒有 Key1 → API 403、頁面被 PageRoleGuard 302。

## 三、投影來源與受眾（第一期）

事件先正規化成同一個 dict（`key` / `source_type` / `calendar_kind` / `owner_*` / `event_type` / `title` /
`start_local` / `end_local` / `start_date` / `end_date` / `visibility` / `link` / `audience`），再逐筆過 `apply_visibility`。

| source_type | 來源 | kind | 誰看得到 |
|---|---|---|---|
| `manual` | `calendar_events` | 依欄位 | ORG → 全企業；PERSONAL → owner 全看；`PUBLIC` 全看；`BUSY` 他人只見 `masked=true`（無 title/note/link，`event_type='BUSY'`）；`PRIVATE` 他人一律隱藏，**ORG_ADMIN 不例外** |
| `holiday` | `schedule_holidays`（org 視圖用企業預設班表；me 視圖用 `ScheduleService.get_user_schedule()`） | ORG | 全企業。`COMP_OFF` 視同 `HOLIDAY`（event_type `HOLIDAY`）；`WORKDAY` → event_type `WORKDAY` |
| `delegation` | `delegations`（非 REVOKED，日期重疊；**不讀 `status`**） | PERSONAL(owner=授權人) | audience：授權人、被授權人、ORG_ADMIN；其他人**不顯示也不遮罩**。`link` 只給 ORG_ADMIN（員工開不了 `/delegations/<sc>`） |
| `position` | `employee_positions`（只投影 `effective_until IS NOT NULL`） | PERSONAL | 本人、ORG_ADMIN |
| `broadcast` | `lookup_items`（`category_code='broadcast'`，**要先 `set_config('app.current_org')`，該表有 RLS**） | ORG | navbar 型（有 `expires_at`）→ 期間；alert 型 → 發布日點事件並過 `_user_in_target()` |
| `approval_task` | `fw_node_execution_queue` WAITING（Approve/FormAdapter）＋ `can_act_on_task()` | PERSONAL | **只在 me 視圖**、只給本人；`link` 到 `/forms/center` |
| `flow_delay` | `fw_node_execution_queue` WAITING `Delay` | ORG | **只在 org 視圖、只給 ORG_ADMIN** |

`days[]`：每日 `is_workday`（`None`＝企業沒班表）、`holiday`、`is_today`。不逐日呼叫 `get_day_periods()`，
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
- 第一期**沒有任何寫入**：沒有新增／編輯按鈕，`calendar_events` 只能由 SQL 或未來的第二期 API 寫入。

## 六、第二期／第三期入口

規格在 BBN #5380。動工前先讀本檔第三節的受眾表——新增來源時只要產出正規化 dict 並決定 `audience`，
不要在 `apply_visibility` 外面另寫可見性判斷。第二期寫入 API 要：PERSONAL 必填 owner、ORG 一律 PUBLIC、
`LEAVE`/`TRIP` 同步寫 `schedule_adjustments`。

## 七、已知取捨

- ORG_ADMIN 的「我的行事曆」也會看到別人的代理授權（audience 規則不分 scope）。要改就在 `_delegation_events` 依 scope 收斂。
- `alert` 型廣播只落在發布日，不做期間（它沒有結束時間）。
- `calendar_events` 沒有 RLS policy（與 delegations／work_schedules 相同現況），隔離靠 service 層顯式 `org_secure_code` 過濾。
