# 交接：SysTelegram 與 EmailRelay 在系統預設企業也看不見（2026-08-31）

> ## 【已結案 2026-08-31】PF-188 全部處置完成
>
> 本檔以下內容是**動工前的調查記錄**，保留作為脈絡。實際處置與現況：
>
> | 項目 | 結果 |
> |---|---|
> | `EmailRelay` -> `SysEmailRelay` | 已改名（node_type / handler 檔與 class / svg / 面板 JS / DOM id） |
> | 兩節點的授權機制 | 改用 `org_restricted` ＋ `workflow_node_org_grants`，出廠只 grant 系統預設企業 |
> | `require_system_admin` | **過濾邏輯已從 `get_node_definitions()` 移除**，欄位保留但全平台 0 筆為 true（Ethan 裁示） |
> | `EmailRelay` 的 category | 「整合」-> 「系統」 |
> | handler 執行期授權 | `telegram_handler`（服務 `SysTelegram`）與 `sys_emailrelay_handler` 都補上 `is_node_allowed()` |
> | 第二節的破口 | 一般企業 PUT graph / publish 皆已回 403（實測） |
> | 第 6.5 節的「最大未知」 | **答案是「handler 完全沒有企業檢查」**，見下方「調查補記」 |
>
> **migration**：`scripts/migrations/legacy/130_sys_nodes_org_restricted.sql`（已執行、已登記、冪等重跑 0 筆）
> **驗收留證**：`/opt/tmp/verify/20260831-pf188.log`（含兩組企業矩陣、publish、瀏覽器實測、執行期）
>
> ### 調查補記（原本不在本檔，是動工時才查出來的）
>
> 1. **`SysEmailRelayHandler` 直接 `subprocess` 呼叫本機 `emailrelay-submit`**，
>    收件者全由節點 config 決定，**沒有任何企業檢查**——未授權企業一旦讓該節點執行，
>    就是拿平台當郵件跳板。這是本次判定嚴重性的關鍵，已修。
> 2. **`TelegramHandler` 的 `TelegramConfig` 查詢原本沒有任何 `org_secure_code` 條件**，
>    所以節點填別家企業的 `config_id` 就拿得到別人的 Bot Token。
>    同型態問題還有 `email_handler` 的 `smtp_config_id` 與**兩處** `RecipientGroup`
>    （其中一處在 `email_handler`，codex 第一版只移除了整數 ID 相容卻漏加 org 條件，驗收時補上）。
>    已全部限縮為「自己企業 or 系統企業」並移除可枚舉的整數 ID 向下相容。
> 3. **「用系統企業的設定組」是刻意設計，不是破口**：
>    `backend/app/api/enterprise_data.py::available_telegram_configs()` 明確把系統企業的
>    設定列給所有企業並標 `is_system: true`。所以限縮的邊界是「自己＋系統」而非「只有自己」。
> 4. **`SysTelegram` 的設定組下拉從以前就壞著**：前端寫死
>    `/api/system/data/settings/telegram`，該端點**從來不存在**（實測 404），
>    症狀是下拉永遠顯示「無法載入設定」。已改用
>    `/api/enterprise/data/settings/telegram/available`。
>    **這件事讓「節點看得見」本身沒有意義**——沒修的話 PF-188 只做完一半。
> 5. `sys_emailrelay_handler` 的 `FileNotFoundError` 分支原本引用不存在的
>    `EMAILRELAY_SUBMIT`，走到會拋 `NameError` 蓋掉真正的錯誤，已修。
>
> ### 仍未做的（不屬 PF-188，別誤以為漏了）
>
> - **實際寄信／實際發 Telegram 未驗**（NT-14 / NT-18 仍記為「授權面已驗」）。
>   授權四層與租戶隔離都用真實 dev 資料實測過，但沒有真的送出訊息。
> - `email_handler` 的「企業級 -> 系統級」SMTP 自動 fallback **刻意保留**（Ethan 裁示）。


Ethan 的原話：

> 系統級 SysTelegram、EmailRelay 兩個 node 沒出現在系統級專用區，也沒出現在 /node-grants/

**動手前先讀第零節。那是每個 session 都會誤會的專案史，不知道就會把問題判反。**

---

## 零、先搞懂「系統級 node」的設計本意（Ethan 2026-08-31 口述的開發史）

> 「系統級 node」就是系統管理員才能用，但**系統級沒有流程設計的 UI，這不是錯誤是分責**。
> 所以才會有一個屬性特別的、**安裝時就會建立的「系統預設企業」**——
> 此預設企業代表 BeakPlatform 這個平台本身，是**唯一能看見系統級 node 的企業**。
> 沒特別提醒就很容易在測試時把它當成一般企業，於是誤判成
> 「給一般企業看見系統級功能」，或「系統級功能在這預設企業也看不見」。

也就是說：

- **系統級能力的邊界單位是「企業」，不是「帳號 user_type」。**
  系統預設企業（`organizations.is_system_org=true`，code `SYSTEM`、
  secure_code `system.local`）＝平台自己，它的管理員本來就該看得到系統級節點
- `OsExecutor` / `OsFileRead` / `OsFileWrite` 走的 `org_restricted` +
  `workflow_node_org_grants`（PF-185）**正是這個設計的正確實作**
- **測試時務必分開跑「系統預設企業」與「一般企業」兩組**，只跑一組必然誤判。
  Ethan 2026-08-31 特別交代：破口的真偽也要用這兩組各測一次才算數

Ethan 補充：**SysTelegram 與 EmailRelay「設計完工時我用過好幾次，所以很確定是後來才消失的」**。
下面的實測證實了這件事，而且找出了消失的機制。

---

## 一、實測結果：這兩個節點目前對「任何人」都不可見

`GET /api/workflows/data/node-definitions`（設計器工具列的唯一來源），2026-08-31 實測：

| 身分 | API | SysTelegram | EmailRelay | OsFileWrite（對照組） |
|---|---|---|---|---|
| **SYSTEM_ADMIN**（`admin@system.local`） | **403 Forbidden** | — | — | — |
| **系統預設企業 ORG_ADMIN** | 200 | **false** | **false** | **true** |
| 一般企業 ORG_ADMIN（BELUGA） | 200 | false | false | false |

### 這是一個死鎖，兩道各自合理的規則疊在一起把節點鎖死了

```
require_system_admin=true  ->  只有 user_type=SYSTEM_ADMIN 通得過
                               （api/workflows.py::get_node_definitions() 直接 continue）
模組 ACL（PERM-04）        ->  SYSTEM_ADMIN 打 modules/form_workflow/api/ 恆 403
                               （系統企業自己有 ROLE 型 ACL，admin@system.local 沒那些角色）
```

**唯一通得過第一道的身分，被第二道擋在 API 外；能進 API 的身分，通不過第一道。**
結果就是 Ethan 說的「後來才消失」——很可能就是模組 ACL 那個變化順帶造成的，
而 `require_system_admin` 這條路從此再也沒有人走得到。
（PERM-04 是 2026-08-31 才寫進 CLAUDE.md 的發現，時間點吻合，但**因果請新 session
自己查 git log 確認**，不要照抄這個推測。）

### 兩套機制的差別，就是問題的核心

| 機制 | 判準 | 擋可見性 | 擋 graph 寫入 / publish | 擋執行期 | 系統預設企業的 ORG_ADMIN |
|---|---|---|---|---|---|
| `require_system_admin`（舊） | **帳號 user_type** | 是 | **否** | **否** | **看不到** |
| `org_restricted` + grants（PF-185） | **企業** | 是 | 是 | 是 | **看得到** |

第零節說「邊界單位是企業」，所以**舊機制的判準從一開始就選錯了維度**。

---

## 二、順帶實測到的破口（Ethan 判定為嚴重問題，要修）

一般企業（BELUGA）ORG_ADMIN 直接打 API：

```
設計器面板列出 SysTelegram / EmailRelay  -> false / false（可見性有擋）
PUT /api/workflows/data/templates/<sc> 塞 SysTelegram -> 200   存進去了
PUT 同上塞 EmailRelay                                  -> 200   存進去了
PUT 同上塞 OsFileWrite（對照組）                       -> 403  「本企業未獲授權的節點型別」
```

`require_system_admin` **只擋設計器可見性，不擋 graph 寫入與 publish**
（CLAUDE.md 早有這句話，這次拿到證據）。

### Ethan 的指示：真偽必須兩組各測一次

**只測一般企業不算數。** 要跑的矩陣至少是：

| 測項 | 系統預設企業 | 一般企業 |
|---|---|---|
| 面板可見性 | 應可見（修好後） | 應不可見 |
| PUT graph 塞該節點 | 應 200 | **應 403** |
| publish 帶該節點 | 應成功 | **應被擋** |
| **執行期真的送出訊息** | 應成功 | **應被擋** |

**最後一列是目前最大的未知，也是判斷嚴重性的關鍵**：
`telegram_handler.TelegramHandler` 同時服務 `Telegram` 與 `SysTelegram`，
`emailrelay_handler.EmailRelayHandler` 同理。要讀它們執行期用哪個企業的設定、
有沒有身分或企業檢查。**handler 若沒檢查，一般企業就真的能借用平台的
Telegram / Email 轉發能力**——那是可利用的越權，不只是分類問題。

---

## 三、建議的處置方向（Ethan 尚未裁示細節）

**主方向：把這兩個節點改用 `org_restricted` 機制，與 OsExecutor 三兄弟一致。**
這同時解掉第一節的死鎖與第二節的破口，因為 `node_grant_service` 是唯一判定實作，
三個消費點（面板可見性 / graph 寫入 7 個入口 / handler 執行期）會自動涵蓋。

具體：

1. `EmailRelay` 的 `category` 從「整合」改成「系統」（`SysTelegram` 已經是「系統」，不用改）
2. 兩者 `org_restricted=true`，出廠只 grant 系統預設企業
3. `require_system_admin` 是否保留要決定：
   - **保留** = 雙保險，但**死鎖依舊**（SYSTEM_ADMIN 進不了模組 API，
     而系統預設企業的 ORG_ADMIN 仍被它擋下）→ **等於沒修好**
   - **拿掉** = 統一由企業授權管，與第零節的設計本意一致 → **建議這個**
4. handler 執行期補上 `is_node_allowed()` 檢查（比照 `os_file_write_handler`）
5. 出廠預設同步：DB migration ＋ 節點定義的 seed 檔（只改 DB 的話新企業會長回舊樣子）

**命名**：依 Ethan 2026-08-31 定的規範，**碰觸作業系統的才加 `Os` 前綴**。
這兩個碰的是外部服務不是 OS，`SysTelegram` 已有 `Sys` 前綴；`EmailRelay` 要不要
改成 `SysEmailRelay` **需請示 Ethan**（前一 session 問過，尚未回覆）。

**先查用量再動手**：改 `org_restricted` 會讓沒有 grant 的企業無法 publish 含該節點的流程。

```sql
SELECT 'templates' AS src, count(*) FROM fw_workflow_templates
 WHERE (graph::text LIKE '%SysTelegram%' OR graph::text LIKE '%EmailRelay%') AND is_deleted=false
UNION ALL SELECT 'published', count(*) FROM fw_published_form_workflows
 WHERE workflow_snapshot::text LIKE '%SysTelegram%' OR workflow_snapshot::text LIKE '%EmailRelay%';
```

---

## 四、動手前的環境事實

- **quick-login user_id**：
  SYSTEM_ADMIN `nH5liUKQikH1NM2osVVXuF`（**注意它打模組 API 會 403，開不了設計器**）、
  **系統預設企業 ORG_ADMIN `UC1oK01uDeKbG2MDwBflGD`**（測系統級功能用這個）、
  一般企業 BELUGA ORG_ADMIN `jIYEQ-_lZMZNBkVy-hijal`、LION `1W0Fkn7IK1RW1qwE8HkYQu`
- **測授權矩陣一律先取 CSRF token**，沒帶會回 400 蓋掉授權判定
- 服務重啟：`sudo systemctl restart beakplatform-dev.service` / `-executor`，
  **重啟 executor 前先確認沒有 RUNNING 節點**；重啟後所有登入 session 失效
- **migration 序號已用到 129，下一個從 130 開始**
- 相關實作：`modules/form_workflow/services/node_grant_service.py`（唯一判定實作）、
  `backend/app/api/node_grants.py`、`api/workflows.py::get_node_definitions()`、
  `modules/form_workflow/services/node_handlers/telegram_handler.py` 與 `emailrelay_handler.py`
- 前一 session 的驗證輸出：`/opt/tmp/verify/20260831-*.log`

## 五、一個要避開的坑（前一 session 踩過）

`GET /api/workflows/data/templates/<sc>` 的回應是 `{success: true, **result}`，
**graph 在最外層，不是 `data.graph`**（與同專案多數 API 不一致，見
`api/workflows.py:202-205`）。誤寫 `cur.data.graph` 會拿到 undefined，
fallback 成空 graph 再 PUT 出去就把模板清空了。

前一 session 因此清空了 BELUGA 的測試模板「多支線範例」，
**Ethan 2026-08-31 回覆「弄壞的模板是測試用的，沒關係，不用處理，我已經把他刪除」，此事已結案**。
留這段只是提醒寫驗證腳本時**先確認讀到的 graph 不是空的再送出**。

---

## 六、冷讀補洞（codex 以「全新接手者只有本檔＋CLAUDE.md」的視角列出的 10 個缺口）

冷讀原始輸出：`/opt/tmp/verify/20260831-handoff-coldread.log`

### 6.1 哪些可以直接做、哪些要等 Ethan

| 項目 | 狀態 |
|---|---|
| 查清 handler 執行期有無企業檢查（唯讀調查） | **直接做**，這是判斷嚴重性的前提 |
| 補齊兩組企業的測試矩陣（第二節） | **直接做** |
| `EmailRelay` 的 `category` 改「系統」 | **直接做**，分類錯置沒有爭議 |
| 兩者 `org_restricted=true` + 出廠 grant 系統預設企業 | **直接做**，這是主方向 |
| **拿掉 `require_system_admin`** | **要等 Ethan**——它是既有的授權欄位，拿掉等於改變授權模型 |
| `EmailRelay` 改名 `SysEmailRelay` | **要等 Ethan**（已在第三節註明） |

先做前四項並把結果攤給 Ethan，後兩項一起請示。

### 6.2 測試用的 secure_code：系統預設企業目前一個模板都沒有

```sql
-- 一般企業（BELUGA）現成可用的（挑節點少的，改壞了影響小）
--   ODio5SzspVcNsrodKG8Wwl  API Key 申請核發流程   5 nodes
--   1bBpvNh6bWi5lVZwBz2NHQ  資安事件處置流程       9 nodes
-- 系統預設企業（SYSTEM）**沒有任何流程模板**，要測它得自己建一個：
SELECT t.secure_code, o.code, t.name, t.revision
FROM fw_workflow_templates t JOIN organizations o ON o.secure_code=t.org_secure_code
WHERE t.is_deleted=false AND o.code IN ('SYSTEM','BELUGA') ORDER BY o.code;
```

**建系統預設企業的測試模板**：用系統預設企業 ORG_ADMIN 登入後
`POST /api/workflows/data/templates`（欄位照 `api/workflows.py:208` 的實作），
或直接在設計器 `/forms/workflows/` 列表頁按新增。

### 6.3 PUT 驗證的安全做法（前一 session 就是這裡把模板清空的）

**不要拿現成模板直接 PUT**。先複製一份再測，或至少加 sanity assertion：

```javascript
const cur = await fetch(`/beakplatform/api/workflows/data/templates/${sc}`).then(r => r.json());
// 這支 API 回的是 {success, **result}，graph 在最外層——不是 cur.data.graph
if (!cur.graph || !Array.isArray(cur.graph.nodes)) throw new Error('讀不到 graph，中止');
const graph = JSON.parse(JSON.stringify(cur.graph));
graph.nodes.push({id: 'probe_SysTelegram', type: 'SysTelegram', name: 'probe', config: {}});
const r = await fetch(`/beakplatform/api/workflows/data/templates/${sc}`, {
  method: 'PUT',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': token},
  body: JSON.stringify({graph, cytoscape_config: cur.cytoscape_config})});
// 預期：一般企業 403、系統預設企業 200
```

**測完把 probe_ 節點移除**（前一 session 的清理腳本可參考
`/tmp/.../scratchpad/cleanup_probe.py` 的邏輯：讀出 → filter 掉 id 以 `probe_` 開頭的 → 寫回）。

### 6.4 publish 路徑

publish 走 `POST /api/mappings/<mapping_sc>/publish`（`api/mappings.py::publish_mapping`，
它是 graph 寫入的 7 個入口之一，也是 `find_unauthorized_node_types` 的消費點）。
**直接改 graph 不會 bump revision**，publish 會回「版本未變更」沿用舊快照，
要先 `UPDATE fw_workflow_templates SET revision = revision + 1 WHERE secure_code='<sc>'`。
細節見 `dev-notes/WORKFLOW_DESIGNER_NOTES.md`。

### 6.5 執行期測試的外部服務資源

本機現況：`telegram_configs` 1 筆、`smtp_configs` 1 筆。

**先讀碼判斷，不要一開始就真的送出訊息**：
`modules/form_workflow/services/node_handlers/telegram_handler.py`（同時服務
`Telegram` 與 `SysTelegram` 兩個 node_type）與 `emailrelay_handler.py`，
看它們用 `queue_item.org_secure_code` 還是寫死系統企業去撈設定。
**光是這一步就能回答「一般企業塞了這個節點會不會借到平台的設定」**，
不必真的發訊息。要實測發送再處理收件者與擾民問題。

### 6.6 參考實作的完整路徑

| 用途 | 路徑 |
|---|---|
| handler 執行期授權的範本 | `modules/form_workflow/services/node_handlers/os_file_write_handler.py`（授權段在 `_check_authorized()`） |
| 唯一判定實作 | `modules/form_workflow/services/node_grant_service.py`（`is_node_allowed` / `find_unauthorized_node_types` / `restricted_node_types`） |
| 面板可見性過濾 | `modules/form_workflow/api/workflows.py::get_node_definitions()` |
| /node-grants/ 的 API | `backend/app/api/node_grants.py`（第 84 行是 `org_restricted.is_(True)` 的篩選） |

### 6.7 節點定義的 seed 檔在哪

- **全平台節點的出廠預設**：`modules/form_workflow/migrations/013_seed_node_definitions.sql`
  （`SysTelegram` / `EmailRelay` 的定義在這裡）
- **後來單獨加的節點**：`scripts/migrations/legacy/1XX_seed_<node>_node.sql`
  （範本：`120_seed_os_executor_node.sql` / `121_seed_file_read_node.sql` / `124_seed_file_write_node.sql`，
  含 `is_active=FALSE` 出廠與只 grant 系統企業的寫法，**照抄這三個就對了**）

**只改 DB 不改 seed 檔的話，新建的企業/新環境會長回舊的樣子且不報錯。**

### 6.8 migration 的命名、執行與登記

- 檔名 `scripts/migrations/NNN_描述.sql`（或 `.py`），**下一個序號是 130**
- SQL 要冪等（以舊值為 WHERE 條件，重跑 0 筆），範本
  `scripts/migrations/legacy/129_os_prefix_for_system_nodes.sql`
- 執行：`PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -f <檔>`
- **登記**：`INSERT INTO schema_migrations (filename) VALUES ('130_xxx.sql') ON CONFLICT DO NOTHING;`
  （欄位是 **`filename`** 含副檔名，不是 `version`）
- **不要跑 `scripts/run_migrations.py --run`**：`--status` 顯示有 20+ 個歷史 migration 未登記，
  `--run` 會把它們全部重跑一遍（屬 PF-168 的範圍，不要在這個任務裡順手處理）

### 6.9 前一 session 的 log 對應表

| log | 內容 |
|---|---|
| `/opt/tmp/verify/20260831-filewrite.log` | OsFileWrite 的 10 項驗收、三層授權實測、executor 端對端 |
| `/opt/tmp/verify/20260831-abandon.log` | Abandon 實測、C 案端對端、migration 127 |
| `/opt/tmp/verify/20260831-sqlexecutor-isolation.log` | SqlExecutor 紅隊測試 536 行 |
| `/opt/tmp/verify/20260831-os-prefix-rename.log` | Os 前綴改名的 migration 與端對端 |
| `/opt/tmp/verify/20260831-drop-retired-db.log` | 退役庫 DROP 的備份與還原演練 |
| `/opt/tmp/verify/20260831-handoff-coldread.log` | 本節的冷讀原始輸出 |
| `/opt/tmp/verify/20260831-final-fulltests.log` / `-os-prefix-fulltests.log` | 兩次全量測試 |

**本次問題的實測（三身分 × 節點可見性、一般企業 PUT graph）是在瀏覽器 console 做的，
沒有落地成 log**——數據在本檔第一、二節，要復現照第 6.3 節的腳本跑。

### 6.10 `/node-grants/` 修好後應該長什麼樣

那頁是「企業當列、節點當欄」的矩陣（PF-185）。兩個節點改成 `org_restricted=true` 後，
應該各多出一欄，欄位標題是 `display_name` + node_type 兩行。預期呈現：

| | SysTelegram | EmailRelay |
|---|---|---|
| system.local（系統預設企業） | 勾選 | 勾選 |
| beluga / lion | 空 | 空 |

**要一併測撤銷與再授權**（`workflow_node_org_grants` 是軟刪除 + partial unique index，
撤銷後再授權會新增一列，那張表本身就是授權歷史）。
頁面在 `/node-grants/`，`@system_admin_required`——
**注意它是平台層 API（`backend/app/api/node_grants.py`）不是模組 API，
所以 SYSTEM_ADMIN 打得進去**（模組 API 才會 403，見 CLAUDE.md 的 PERM-04）。
