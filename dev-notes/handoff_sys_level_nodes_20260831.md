# 交接：SysTelegram 與 EmailRelay 的系統級歸屬（2026-08-31）

Ethan 的原話：

> 系統級 SysTelegram、EmailRelay 兩個 node 沒出現在系統級專用區，也沒出現在 /node-grants/

前一個 session 已把成因查清楚並實測，本檔是交接。**動手前先讀完，尤其第四節那個
我自己造成的資料損失，不要重蹈。**

---

## 一、現況（已查證，2026-08-31）

```sql
SELECT node_type, display_name, category, org_restricted, require_system_admin
FROM workflow_node_definitions WHERE is_deleted = false;
```

| node_type | category | `org_restricted` | `require_system_admin` |
|---|---|---|---|
| `OsExecutor` / `OsFileRead` / `OsFileWrite` | 系統 | **true** | false |
| `SysTelegram` | **系統** | **false** | **true** |
| `EmailRelay` | **整合** | **false** | **true** |
| `Telegram` / `EmailAdapter`（一般企業用的那兩個） | 通知 | false | false |

於是出現 Ethan 看到的三個現象，成因各不相同：

1. **SysTelegram 沒出現在「系統級管理員專用」區** —— 它的 `category` **是**「系統」，
   分類沒錯。看不到是因為 `require_system_admin=true`，
   `api/workflows.py::get_node_definitions()` 對非 SYSTEM_ADMIN 直接 `continue` 跳過。
   **用 SYSTEM_ADMIN 身分開設計器就看得到**（前一 session 是用系統企業 ORG_ADMIN
   `UC1oK01uDeKbG2MDwBflGD` 驗的，所以沒出現）。
   **待確認**：SYSTEM_ADMIN 打模組 API 常因模組 ACL 回 403（CLAUDE.md 的 PERM-04），
   所以它到底開不開得了設計器要實測。這一條先驗，可能會改變整個處置方向。
2. **EmailRelay 沒出現在該區** —— 它的 `category` 是「整合」，分類本身就錯置。
   它 `require_system_admin=true`，是系統級能力卻掛在一般整合分類下。
3. **兩者都沒出現在 `/node-grants/`** —— 那頁只列 `org_restricted=true` 的節點
   （`backend/app/api/node_grants.py:84`、`node_grant_service.restricted_node_types()`），
   兩者都是 false，所以不在名單內。

---

## 二、根本問題：兩套並存的機制，其中一套擋不住 API

| 機制 | 判準 | 擋設計器可見性 | 擋 graph 寫入 / publish | 擋執行期 |
|---|---|---|---|---|
| `require_system_admin`（舊） | 帳號 `user_type` | 是 | **否** | **否** |
| `org_restricted` + `workflow_node_org_grants`（PF-185 新機制） | 企業 | 是 | 是 | 是（handler 內） |

CLAUDE.md 已寫過這句：「`require_system_admin` 不是替代方案：它的判準是帳號 user_type
而非企業，且只擋設計器可見性、不擋 graph 寫入與 publish。」
**這次實測拿到了證據。**

### 已驗證的破口（2026-08-31 實測，BELUGA ORG_ADMIN `jIYEQ-_lZMZNBkVy-hijal`）

```
設計器面板是否列出 SysTelegram / EmailRelay   -> false / false（可見性有擋）
PUT /api/workflows/data/templates/<sc> 塞 SysTelegram -> 200  ← 存進去了
PUT 同上塞 EmailRelay                                  -> 200  ← 存進去了
PUT 同上塞 OsFileWrite（對照組）                       -> 403「本企業未獲授權的節點型別」
```

也就是說**一般企業的流程設計者只要繞過 UI 直接打 API，就能在自己的流程裡使用
系統企業專用的 Telegram 與 Email 轉發能力**。

**還沒驗的下一步（新 session 必做）**：存進去之後**執行時**會不會真的送出訊息？
`telegram_handler.TelegramHandler` 同時服務 `Telegram` 與 `SysTelegram` 兩個 node_type，
`emailrelay_handler.EmailRelayHandler` 同理。要看它們在執行期用的是哪個企業的設定、
有沒有身分檢查。**如果 handler 沒檢查，這就是可利用的越權，不只是分類問題。**

---

## 三、處置方向（未定案，Ethan 尚未裁示）

方向 A（推薦）：**把這兩個節點也納入 `org_restricted` 機制**
- `EmailRelay` 的 `category` 改「系統」
- 兩者 `org_restricted=true`，出廠只 grant 系統企業（與 OsExecutor 三兄弟一致）
- `require_system_admin` 要不要保留是另一個決定：保留＝雙保險；拿掉＝統一由企業授權管
- 好處：三個層面（面板、graph 寫入、執行期）自動涵蓋，`node_grant_service` 是唯一判定實作，
  新增受限節點三處都會自動生效（CLAUDE.md 已記載）
- 代價：現有使用這兩個節點的流程要確認不受影響（先查 graph 用量）

方向 B：只修分類（`EmailRelay` 移到「系統」），不動授權機制
- 只解決「看起來不一致」，破口照舊。**不建議。**

命名：若採方向 A，依 Ethan 2026-08-31 定的規範，**碰觸作業系統的才加 `Os` 前綴**。
這兩個節點碰的是外部服務不是 OS，`SysTelegram` 已有 `Sys` 前綴，`EmailRelay` 要不要
改名（例如 `SysEmailRelay`）需請示——前一 session 已就此徵詢過，Ethan 尚未回覆。

---

## 四、前一 session 造成的資料損失（誠實交代，也是給你的警告）

**BELUGA 的流程模板「多支線範例」（`0wAaLoEGu0w4nym6LkJKCA`）的 graph 與
cytoscape_config 已被我清空，救不回來**（無發行快照、無其他版本）。

成因是我的驗證腳本讀錯 API 回應結構：

```javascript
// GET /api/workflows/data/templates/<sc> 的回應是
//   { success: true, ...result }      ← graph 在最外層
// 不是
//   { success: true, data: {...} }
const graph = cur.data.graph || {nodes: [], edges: []};   // 錯：cur.data 是 undefined
//                              ^^^^^^^^^^^^^^^^^^^^^^ fallback 成空 graph，PUT 就清空了
const graph = cur.graph || {nodes: [], edges: []};        // 對
```

**注意這個回應結構與同專案其他 API 不一致**（多數是 `{success, data}`，
這支是 `{success, **result}`，見 `api/workflows.py:202-205`）。

**教訓與要求**：用 PUT 驗證守門時，**先確認讀到的 graph 不是空的再送出**，
或改用讀取型探測（例如只送一個明知會被擋的最小 payload）。
守門有效的節點（OsFileWrite）因為被 403 擋下，模板毫髮無傷；
**正是這次要修的這兩個節點沒有守門，才把資料寫壞了**——這件事本身就是破口存在的代價。

---

## 五、動手前的環境事實

- 服務：`sudo systemctl restart beakplatform-dev.service` / `-executor`，
  **重啟 executor 前先確認沒有 RUNNING 節點**，重啟後所有登入 session 失效
- quick-login user_id：SYSTEM_ADMIN `nH5liUKQikH1NM2osVVXuF`、
  系統企業 ORG_ADMIN `UC1oK01uDeKbG2MDwBflGD`、BELUGA ORG_ADMIN `jIYEQ-_lZMZNBkVy-hijal`
- **測授權矩陣一律先取 CSRF token**，沒帶會回 400 蓋掉授權判定（CLAUDE.md 已記載）
- migration 序號已用到 **129**，下一個從 **130** 開始
- 相關實作：`modules/form_workflow/services/node_grant_service.py`（唯一判定實作）、
  `backend/app/api/node_grants.py`、`api/workflows.py::get_node_definitions()`
- 前一 session 的驗證輸出：`/opt/tmp/verify/20260831-*.log`
