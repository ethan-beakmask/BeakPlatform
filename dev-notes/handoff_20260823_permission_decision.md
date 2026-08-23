# 交接：權限設計偏移的評估與「重寫 vs 修補」決策分析

**日期**：2026-08-23
**觸發**：使用者要求重新評估 PF-148/149/150（明確指示不採信 atom 的說詞），
接著延伸成「這套系統是否該打掉重做」的決策分析。
**時機**：使用者預計 ITHome 鐵人賽結束後（約 2026-10 下旬）才開工，本文件是那時的起點。

---

## 一、本次已經落地的東西

| commit | 內容 |
|---|---|
| `2fb20ac3` | 路由守門宣告表 + 一致性測試（PERM-05） |
| `7df1028a` | 宣告表加入 `answer_source` 欄位 |
| 本次 | `CLAUDE.md` PERM-01 的 Phase B 敘述修正（見下方第五節） |

新增檔案：`scripts/route_guard_inventory.py`、
`backend/app/security/route_guard_table.yaml`（831 個 endpoint，
已排除 Flask 內建 5 條與 `dev.py` 的 12 條）、
`backend/tests/test_route_guard_table.py`、`dev-notes/ROUTE_GUARD_TABLE_SPEC.md`。

驗收留證：`/opt/tmp/verify/20260823-route-guard-accept.log`、
`/opt/tmp/verify/20260823-pf148150-recheck.log`
（**`/opt/tmp/` 不在版控，重灌會消失**）。

---

## 二、PF-148 / 149 / 150 的重新評估結論

**三張單都是同一批 session 用掃描腳本產出的，範圍由腳本框架決定而不是由風險決定。**

### PF-148：成立，但原卡把範圍寫小了 → 需改寫

原卡結論是「唯一的實際缺口是 `/spec-formulate/<sc>/edit` 一頁」。實測不是。

在 TEST00 臨時加一張含 `nocode_builder` + `spec_formulate` 的合約，
用該企業純員工（只有 EMPLOYEE 角色）實測：

```
/spec-formulate/            列表頁    302 擋下
/spec-formulate/ABC123/edit 編輯器    200 進得去
/nocode-builder/sub-systems           200 進得去
/nocode-builder/my-projects           200 進得去
/nocode-builder/lookup                200 進得去
```

把臨時合約刪掉後全部變 403。**也就是說現在擋住這些頁的是「這家企業沒買這個模組」，
不是任何權限設計。** 原卡漏掉 NoCode 那片，是因為它的掃描以「route 型選單所屬的
blueprint」畫範圍，而 NoCode 選單目前刻意隱藏（DB 裡一筆記錄都沒有），整片不在範圍內。

**嚴重度**：進去之後 spec_formulate 的 31 支 API 全 403（PF-145 已掛好），
NoCode API 回自己企業資料且 `can_manage: false`。
所以是「企業內部誰能開得了開發工具」，**不是跨租戶資料外洩**。

**修法建議（不要照原卡走）**：原卡建議改該選單的 `link_type`，那只補一個洞。
建議改成「建立企業時自動 seed 模組 ACL 出廠值」——讓
`ModuleAccessService.check_user_access()` 的 fail-open 分支永遠不會被走到，
判定邏輯一行不改、也不影響任何現有企業。手法同 `od_protected_targets` 出廠值。

### PF-149：死碼一支，不值得留成待辦

`GET /api/mappings/available`：全專案 grep（js/html/py/md）**零個呼叫者**，
只有 PF-145 自己的文件提到它。功能與已存在的 `/api/mappings/published` 重疊，
自 `ddf4b3ed`「FormWorkflow 模組完整移轉」進來就沒被用過。

處置：刪端點、關單。留成待辦只會讓下一個 session 再花一輪判斷同一件事。

### PF-150：前提是錯的 → 應關閉

原卡說「`POST /api/users/` 忽略 `user_type`，一律建成 EMPLOYEE」。技術上沒錯，
但推論反了：

- **API 的參數名是 `role` 不是 `user_type`**。傳 `role: "external"` 會正確建成 EXTERNAL
  （`backend/app/web/users.py:217` `_get_user_type_from_role()`）
- 原卡最擔心的「順帶塞 EMPLOYEE 角色 → Key2 對 EXTERNAL 形同虛設」**已證偽**：
  `_assign_default_role()` 是依 user_type 對應（EXTERNAL → `EXTERNAL_USERS`），
  查 DB 現有三個 EXTERNAL 帳號拿到的都是 `EXTERNAL_USERS`
- `templates/pages/users/create.html:143` 有註解「角色固定為一般用戶，
  企業管理員與外部廠商由專用介面管理」+ `<input type="hidden" name="role" value="user">`
  ——這是刻意設計

剩下的只有「API 對未知欄位靜默忽略」，是通則性的 DX 小事，不值一張單。

---

## 三、「重寫 vs 修補」的決策分析

使用者提的六階段構想：1 權限總表一次成型／2 產品模組與權限配合評估／
3 表單+流程改內建／4 資安中心 UI + open-defense 內建／5 NoCode 改內建／
6 vuln 切出去獨立，走 API 與 SSO。

### 結論：只有第 1 項是重寫，其餘五項是重構，而且原地做風險更低

因此**真正的二分法不是「重寫 vs 修補」，是「權限核心要不要重寫」**，其餘是順序問題。

### 支撐決策的數據（2026-08-23，用宣告表算的；數字會腐爛，重跑 `--stats`）

831 個 endpoint 的歸屬（已排除 Flask 內建與 `dev.py`）：

| 歸屬 | endpoint | 佔比 |
|---|---:|---:|
| 平台核心 | 435 | 52% |
| form_workflow | 158 | 19% |
| nocode_builder | 143 | 17% |
| open_defense | 43 | 5% |
| spec_formulate | 34 | 4% |
| **vuln_lifecycle** | **18** | **2%** |

兩批問題的分佈，結論相反：

| 問題 | 數量 | 全部落在哪 |
|---|---:|---|
| 只掛 `module_access_required`（fail-open） | 167 | **全在模組裡，平台核心 0 條** |
| 完全沒有守門 decorator | 84 | **全在平台核心，模組 0 條** |

由此得到三個判斷：

1. **「模組改內建」是六項裡收益最大的，而且原地就能做。**
   那 167 條 fail-open 全部來自模組——「模組」這個概念就是 fail-open 的唯一來源。
   改成內建功能等於強制這 167 條去面對「到底該由誰守」。
2. **重寫解決不了那 84 條。** 它們全在平台核心、與模組無關，
   是「新增頁面沒掛守門」累積的。重寫會產生新的一批，除非驗證機制先存在。
3. **vuln 切出去的收益被高估了**（只有 2%）。切它的理由應該是產品邊界與維護權責
   （它確實是唯一真正符合「可獨立販售」語意的東西），不是簡化權限。

重寫規模：權限核心 `security/` 2351 行 ＋ 10 支權限 service 4896 行 ≈ **7250 行**，
消費端 **105 個檔案**、831 個 endpoint 全部要跟著遷移。

### 為什麼「現在不是重寫的時機」

這已經是第 7 版，前六次每次都是「重新設計會更乾淨」，而同一批問題每版都長回來。
差別在於：**前六版都是憑印象重新設計的，因為當時沒有任何文件能說清楚
「現在到底有幾條路由、各自由誰守」。2026-08-23 第一次有了。**

所以第 8 版要不要做，取決於有沒有規格書；而那份規格書就是 831 條的複審結果。
**兩種結局都需要先複審**：複審完要重寫 → 第 8 版可以真的一次成型；
複審完發現不用 → 第 7 版就夠用。

使用者對「規格書」一詞的修正（重要）：**前六代都有規格書，那是「設計規格」
（我打算怎麼做）；這次需要的是「現況清單」（實際上是怎麼樣），方向相反。**
前者寫完就開始腐爛，後者有測試綁著就不會。

### 「更穩」這一半

穩定性不來自新架構，來自有沒有東西在驗。那 167 條與 84 條不是因為架構爛才存在，
是因為**從第 1 版到第 7 版都沒有人在測**。第 8 版若沒把驗證機制列為第一個交付物，
會用更快的速度長出第 8 批——因為 vibe coding 現在比當年快得多。

---

## 四、建議的順序（鐵人賽後開工時）

| 順序 | 做什麼 | 理由 |
|---|---|---|
| 0 | **補測試庫 RBAC seed（PF-34）** | 否則之後每次驗證還是空的。測試庫沒有權限資料＝所有測試都跑在 fail-open 狀態 |
| 1 | 複審 831 條（按 `answer_source` 分堆，模組優先） | 兩條路的共同前置，也是第 8 版的規格書 |
| 2 | 模組→內建（構想的階段 3、4、5） | 收益最大且原地可做，直接消滅 167 條 fail-open 的成因 |
| 3 | vuln 切出（構想的階段 6） | 產品邊界清理，規模小、風險低 |
| 4 | **這時才判斷「權限總表一次成型」要不要重寫** | 屆時架構已簡化、規格已在手，判斷會容易得多 |

**明確反對的做法**：比賽結束後直接開第 8 版、跳過複審。那會重演前六次的模式，
而且這次連「至少留下一張表」都沒有。

預測（非結論）：做完 2 和 3 之後，「權限總表一次成型」很可能會從「重寫核心」
降級成「把現有的四層+角色整理成一張表並補上驗證」——因為屆時已經沒有「模組」
這個平行的授權維度在干擾。

---

## 四之二、動工前的已知缺口（2026-08-23 codex 冷讀補洞）

把本文件與 `CLAUDE.md` 交給不帶本對話記憶的 codex 冷讀，請它列出
「照此文件動工時哪裡需要猜測」。以下是它列出的 11 點與逐條回答。

### 關於步驟 0（測試庫 RBAC seed）

| 冷讀提出的疑問 | 回答 |
|---|---|
| PF-34 的完整內容不在文件裡 | BBN **PF-34**（atom **5031**，status=planning、urgency=L）「測試庫缺 RBAC seed，test_admin_required_for_admin 過不了」。`note_get(5031)` 取全文 |
| 缺「測試庫該 seed 哪些角色／使用者／指派」的權威對照 | **沒有現成的權威對照，這正是要做的事**。permission code 的權威清單是 `scripts/migrations/075_seed_resource_crud_permissions.py`；角色與指派要照 `backend/app/defaults/` 的出廠值推導 |
| 缺實作位置 | **建議放 `backend/tests/conftest.py` 的 session-scoped fixture**，理由：`scripts/run_tests.sh` 前置 seed 會在每次跑單一測試檔時也付出成本；而 `test_smoke.py` / `test_page_template_*.py` 各自定義的 app fixture 會覆蓋 conftest 的 app fixture，所以 seed 不能掛在 app fixture 上 |
| 缺「最小修補」與「完整 RBAC seed」的邊界 | **做最小修補即可**。目的是「讓測試不要跑在 fail-open 狀態」，不是重建整個 RBAC。驗收標準：`test_admin_required_for_admin` 轉綠，且完整測試沒有新增失敗 |
| 完成後怎麼回寫 BBN | `note_task_status(ref='PF-34', status='completed', reason='...')` |

### 關於步驟 1（複審 831 條）

| 冷讀提出的疑問 | 回答 |
|---|---|
| 「按 answer_source 分堆」缺精確順序 | **`none` 138 條先**（84 條完全沒守門風險最高、54 條只掛 `login_required`），再來是模組的 `db`（167 條 fail-open），最後才是 `code` 那 392 條（讀 decorator 就結案，最快） |
| `max_audience`「設計意圖」從哪來 | 多數情況從**該功能的選單 Key1** 反推（`menu_permissions` 記的就是設計意圖）。反推不出來的**不要猜**，`review` 留 `unreviewed`、`note` 寫「需產品決策」，收集完一批再一次問使用者 |
| `db` 類的基準資料狀態要看哪家企業 | **一律以「新建企業的出廠狀態」為基準**——那是最寬鬆、fail-open 會生效的狀態。現成的代表是 **TEST00**（新企業、零 `module_access_control` 記錄）。BELUGA 設過 ACL，拿它當基準會低估風險 |
| `none` 類要確認有沒有被 url 型選單前綴涵蓋，缺標準查詢 | 見下方指令 |
| 發現守門不足時怎麼開卡 | `note_task_create(title, content, project='/opt/BeakPlatform-dev')`，PF 編號自動配。**同一類問題合併成一張卡**（例如「form_workflow 的 X 支 API 缺 Key1」），不要一條路由一張，否則 831 條複審會產生無法管理的卡海 |
| `confirmed` 與 `intentional_open` 的判定門檻 | `confirmed` ＝ 守門符合設計意圖（不論寬嚴）；`intentional_open` ＝ **刻意**讓所有登入者可達，`note` 必須寫理由。判別問句：**「這條路由如果被 EXTERNAL 廠商帳號打到，會不會有問題？」** 不會＝`intentional_open`（例：個人設定、改密碼、表單中心系列）；會＝守門不足，記 `note` 並開卡 |

### 複審 `none` 類時用的查詢

`answer_source: none` 不等於沒有防線——它可能被某個 url 型選單的路徑前綴涵蓋
（那時 PageRoleGuard 會擋）。**要逐條對照這份清單**（26 筆，數字會腐爛，動工時重跑）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c "
SELECT code, link_target FROM menu_items
WHERE is_deleted=false AND is_active=true
  AND link_type IN ('url','route') AND link_target LIKE '/%'
ORDER BY length(link_target) DESC;"
```

判定方式與 `PageRoleGuard._find_matching_menu_items()` 策略 2 相同：
路由路徑 `== link_target.rstrip('/')` 或以 `link_target.rstrip('/') + '/'` 開頭即被涵蓋，
**多筆命中時取最長匹配**。`link_type='route'` 且 `link_target` 不以 `/` 開頭的
（30 筆）只守那一個 endpoint，不涵蓋子路由——那正是 PF-148。

### 複審時實測某條路由的最短路徑

```bash
BASE=http://192.168.0.16:7000/beakplatform
# TEST00 的純員工（只有 EMPLOYEE 角色，代表新企業最寬鬆狀態）
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
  -d '{"user_id":"XeJUHw_SeDB7iern_QNEz4"}'
curl -s -b cj.txt -o /dev/null -w '%{http_code}\n' "$BASE/<要測的路徑>"
```

**注意 302 會觸發 PageRoleGuard 的強制登出**，所以測到 302 之後要重新 quick-login
再測下一條，否則後續全部拿到 401（本次對話踩過，第一輪數據因此作廢）。

其他測試身分：TEST00 ORG_ADMIN `Lc-OeE0E23nlw02PdQUFsW`（`admin-ethan`）、
BELUGA EXTERNAL `gg`（secure_code 自行查，見 CLAUDE.md 的 quick-login 段）。

---

## 五、順帶處理與待處理

### 已處理

- **`CLAUDE.md` PERM-01 的 Phase B 敘述**：原文「Phase B 起頁面路由**不掛**身分
  decorator」前半是無條件祈使句、後半才有條件，被當成通則沿用，
  **是 PF-148 那批破口的來源**。已改成「頁面路由一律自己掛身分 decorator；
  雙鑰匙是額外一層，不是唯一一層」，並保留原文說明為什麼改。

### 使用者已決定但尚未執行

- **NoCode 選單維持隱藏**（2026-08-23 決定，先前討論過要恢復顯示，最後決定不動）。
  若日後恢復：DB 裡三筆 menu_items 已**完全不存在**（不是 is_deleted），
  要 `flask module sync --force` 重建，然後補 Key1/Key2。
  且重建出來是 route 型選單，**只會守住「子系統開發」那一頁**，
  workspace／ir-designer／my-projects 照樣不進雙鑰匙判定
- PF-149 刪端點、PF-150 關單（結論見第二節）

### atom 盤點的判準（給後續 session 批次處理用）

知識庫 atom 是三類資料裡**最危險的**：程式改了它不會變、沒有測試會紅、
AI 檢索到時也分不出這是三個月前的觀察還是現在的事實。優先序應為
**atom > 文件 > 程式**（程式有了 PERM-05 的測試就不需要人力盤點）。

判準很單純——**這句話會不會因為有人改了一筆資料就變成假的？**

| 種類 | 例子 | 處理 |
|---|---|---|
| 機制 | 「PageRoleGuard 對 endpoint 是精確比對、沒有前綴語意」 | 留，不會腐爛 |
| 當時的狀態 | 「目前四家企業都不會出事」「不受涵蓋的路由 49 條」「BELUGA 有設 ACL 所以擋得住」 | 標記需重驗或淘汰 |

另建議加一條規範：**引用 atom 裡的狀態類斷言前必須重驗，機制類可直接引用。**
本次對話之所以抓到 PF-150 的錯誤結論，是因為使用者明確說了「不採信 atom」——
這不該靠使用者每次記得說。
