# 交接：SysTelegram 與 EmailRelay 在系統預設企業也看不見（2026-08-31）

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
