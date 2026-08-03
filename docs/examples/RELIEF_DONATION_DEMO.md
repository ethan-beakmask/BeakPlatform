# NoCode 教學實例：急難救助物資捐贈系統

**建立日期**：2026-08-03
**目的**：給 NoCode 設計者學習用的完整實例。全程不改任何平台程式碼，
只用 NoCode Builder 的 API 與子系統自己的 SQLite。

---

## 1. 這個系統做什麼

給「外人」（非平台帳號的一般民眾）使用的公開物資捐贈登記：

| 步驟 | 對應機制 |
|---|---|
| 用 e-mail 自助註冊、登入 | portal 帳號體系（`portal.db` 的 `portal_users`） |
| 建立自己的基本資料（姓名、電話） | master_detail widget 的 **master** |
| 登錄自己能提供的物資（可多筆） | 同一 widget 的 **detail** |
| 每個人只看得見自己的項目 | `DcCrudView.row_owner_scope = own` |
| 不具名公佈欄（物資項目 + 累積數量） | 彙總表 + SQLite trigger，view 用 `scope = all` |

### 存取位置

| 項目 | 值 |
|---|---|
| 子系統 secure_code | `kRsmLJEwJiUghp_rB_Rjwc` |
| portal path_id | `8AMAUAh9` |
| 公開入口 | `http://192.168.0.16:7000/beakplatform/public/portal/8AMAUAh9/` |
| 我的捐贈登記 | `.../public/portal/8AMAUAh9/p/F85ufjhbcx7UPLVprZiMnY` |
| 物資公佈欄 | `.../public/portal/8AMAUAh9/p/Iup0VyTNqpuv6HSSI506ZV` |
| 設計器 | `/beakplatform/nocode/ir-designer/<上面兩個頁面 sc>` |

建置腳本：`scripts/examples/provision_relief_donation_demo.py`
驗收腳本：`scripts/examples/verify_relief_donation_demo.py`（11 項全通過）

---

## 2. 資料模型（`portal_data.db`）

三張表都由 `POST /api/nocode-builder/sub-systems/<sc>/tables` 建立，
建表 API 一律自動加上 `id` / `created_at` / `portal_user_ref` 三個系統欄位
（自行宣告會被擋成 `reserved_column_name`）。

```
donor_profile   (master)  full_name, phone
relief_offer    (detail)  donor_id -> donor_profile.id, item_name, quantity,
                          unit, available_until, note
bulletin_board  (彙總)    item_name, unit, total_quantity, offer_count, donor_count
```

### 為什麼公佈欄需要一張實體表

NoCode 的 `DcCrudView` 只會對**單一實體表**做 SELECT，
**沒有 GROUP BY / SUM 這類聚合能力**，而且 `SqliteCrudService` 判斷目標存在與否時
只認 `sqlite_master.type = 'table'`——**SQLite VIEW 綁不上去**。

所以「累積數量」用一張實體彙總表 + 三個 trigger（INSERT / UPDATE / DELETE）維護。
重算方式是「把該 (item_name, unit) 整組刪掉再重建」，天生冪等，
也不怕 UPDATE 改掉 `item_name`（舊鍵與新鍵都重算）。

**這是目前 NoCode 唯一能做聚合的方式**，設計者必須知道這一步落在 SQL 層、
不在 NoCode UI 裡。

---

## 3. 權限設計（三層 + 列級）

### 列級擁有權才是「只看得見自己的」的關鍵

| view | `row_owner_scope` | 效果 |
|---|---|---|
| 捐贈者基本資料 | `own` | 只查得到 `portal_user_ref = 'u:<自己>'` 的列 |
| 可提供物資 | `own` | 同上 |
| 物資公佈欄（彙總） | `all` | 不過濾擁有者，所有人看到同一份 |

彙總表由 trigger 寫入，`portal_user_ref` 是 NULL。
**`own` 模式下 NULL 擁有者的列誰都看不到**（刻意的 fail-closed），
所以公佈欄的 view 一定要設成 `all`，否則會出現「表裡有資料、頁面永遠空白」。

### widget 級 access_matrix

```
我的捐贈登記 / donation (master_detail)
    read/create/update = {groups: [GENERAL], min_level: MEMBER}
物資公佈欄 / bulletin (table)
    read = {groups: null, min_level: GUEST}      <- 只宣告 read
```

`read` 未宣告是**放行**，`create` / `update` / `delete` 未宣告是**拒絕**。
公佈欄只宣告 `read`，所以任何寫入請求都被擋（驗收實測回 404）。
搭配 view 層 `allow_create/edit/delete = false`，是兩道獨立的鎖。

### 頁面級 access_matrix（site map 節點）

捐贈頁 `min_level: MEMBER`（要註冊才進得去）、
公佈欄 `min_level: GUEST`（匿名可看）。
子系統的 `allow_anonymous = true` 讓沒登入的訪客自動取得 GUEST session。

---

## 4. 頁面組成（Page IR v3）

### 我的捐贈登記

```
text        說明文字
table       my-profile   binding -> donor_profile(own)，row_link_ref = donation
master_detail donation   master -> donor_profile(detail 視圖)
                         detail -> relief_offer，foreign_key = donor_id
                         history.enabled = true
```

**設計者最容易卡的地方**：`master_detail` 的 master 是靠網址參數
`?<widget_id>__sc=<master id>` 載入的，**沒有「自動帶出本人那一列」的機制**。
本例的解法是同頁再放一個 table widget 綁同一張表（own scope 下只會有自己那列），
用 `row_link_ref` 指向 master_detail widget，點「開啟」就把 `donation__sc` 帶上。

第一次進來時清單是空的，直接在下方表單填寫並送出即可建立（`mode = new`）。

### 物資公佈欄

```
text   說明文字
table  bulletin   binding -> bulletin_board(all)
                  columns: 物資項目 / 累積數量 / 單位 / 提供人數
                  default_sort: total_quantity desc
```

欄位刻意**只選彙總欄**，捐贈者姓名、電話、備註完全不在 binding 裡，
從資料出口就沒有外洩管道（不是靠前端隱藏）。

---

## 5. 建置順序（腳本九步）

1. `POST /sub-systems` 建子系統（連帶自動建 portal 路徑、SQLite、welcome 首頁）
2. `POST /sub-systems/<sc>/tables` ×3 建業務表
3. 直接對 `portal_data.db` 建三個彙總 trigger
4. `POST /sub-systems/<sc>/resolve-view` ×3 產生 CRUD View（自動讀表結構生成 columns_config）
5. `PUT /views/<sc>` 調整 `row_owner_scope` 與 CRUD 開關
6. `POST /pages` 建兩個 Page IR v3 頁面，`PATCH /pages/<sc>/publish` 發布
7. `POST /sub-systems/<sc>/pages` 掛載 + `POST .../site-map/nodes` 建節點
8. `POST .../site-map/access-matrix/batch` 設頁面級准入；寫 `portal_settings`
   開 `allow_registration` / `allow_anonymous`
9. `POST /projects/<sc>/publish` 上線

### 三個一定會踩的順序陷阱

- **子系統 `status` 不是 `published`，公開 portal 全部 404**（第 9 步不能省）
- 頁面 `status` 不是 `published`，`/p/<sc>` 也是 404
- `portal_settings` 目前**沒有 API**，只能直接寫子系統的 `portal.db`

---

## 6. 驗收結果（2026-08-03）

`scripts/examples/verify_relief_donation_demo.py` 11 項全通過，
輸出留存於 `/opt/tmp/verify/20260803-relief-verify.log`：

- 兩位民眾以 e-mail 註冊、送出基本資料 + 各 2 筆物資
- 各自的清單只有自己那列
- 甲帶乙的 master id 開頁面也看不到乙的姓名與備註
- 匿名訪客可讀公佈欄；礦泉水 120 + 80 = 200、提供人數 2
- 公佈欄回應不含任何捐贈者識別欄位
- 對公佈欄 widget 寫入回 404

瀏覽器實測（VERIFY-01）：註冊 → 填寫 → 送出 → 點「開啟」→ master 回填 +
歷史記錄正確；公佈欄排序連結正常；console 無 error/warn。
截圖 `/opt/tmp/verify/20260803-relief-{donate,bulletin}-page.png`。

---

## 7. 這個實例暴露出的平台缺口

以下都不是本實例的設定錯誤，是 NoCode 目前的能力邊界。
2026-08-03 已由用戶逐條裁決並開單，決策脈絡見知識庫 atom #4993。

| 缺口 | 影響 | 目前的替代做法 | 追蹤 |
|---|---|---|---|
| 無聚合視圖（GROUP BY / SUM） | 任何「統計、彙總、排行」都做不出來 | 彙總表 + SQLite trigger（要寫 SQL） | #28 |
| CRUD View 綁不上 SQLite VIEW | 同上，連唯讀彙總都不能用 view 表達 | 同上 | #28 |
| master_detail 無「載入本人那列」 | 一人一筆的 master 需要額外一個 table + row_link 才進得去 | 本例的 `my-profile` widget | #28 |
| portal 首頁不列出可用頁面 | 使用者進站後只看到「Portal 已就緒」，**走不到任何頁面** | 只能給對方頁面直達網址 | #29 |
| Page IR v3 沒有連結／導覽 widget | 頁與頁之間無法互相跳轉 | 同上 | #29 |
| `portal_settings` 無 API | 開放註冊／匿名只能直接改 SQLite | 建置腳本第 8 步 | #30 |
| 欄位無選項清單（lookup）可綁 | 物資項目自由輸入，彙總會因錯字而分裂 | 無，只能靠說明文字 | #31 |

其中**導覽（#29）對「給外人用的公開系統」影響最大**：
沒有導覽等於使用者進得來、走不動，實務上必須先解決。

### 已查證的實作事實（動工前必讀）

- v2 的 SITEMENU widget 仍在（`js/sitemenu-widget.js`、`SiteMapService.get_menu_tree()`），
  但 Page IR v3 schema 沒有對應 widget
- `get_menu_tree()` 吃的是**平台 user**、走平台 grant permission，
  portal 世界不能直接沿用
- v2 SITEMENU 只有子樹起點（`startNodeSc` / `startLevel`），**沒有逐頁勾選**
- 匿名身分 `g:<token>` 在 own scope 下同樣被隔離，
  破口不在匿名本身而在「view 被設成 `all`」或「widget 誤宣告寫入 action」
