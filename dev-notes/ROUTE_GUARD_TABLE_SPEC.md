# 路由守門宣告表規範

## 這張表是什麼、不是什麼

`backend/app/security/route_guard_table.yaml` 記錄的是「這條路由由哪個機制守」：例如
`admin_required`、`page_keys_required`、`module_access_required`、HMAC decorator，或函式內部
疑似有額外權限判斷。這是程式碼事實，會跟著路由與 decorator 改動而穩定變更。

它不是「哪些身分實際進得來」。實際可達性是 DB 資料的結果，會隨企業、合約、ACL、角色
指派與選單設定改變。禁止在這張表中加入任何隨企業變動的資訊。

## 新增路由的 SOP

1. 寫完路由與既定守門邏輯。
2. 執行 `venv/bin/python scripts/route_guard_inventory.py --update`。
3. 對新增 endpoint 填寫 `max_audience` 與 `review`。
4. 執行 `bash scripts/run_tests.sh tests/test_route_guard_table.py -q`，確認測試綠。

工具另有 `--check`（只比對、不寫檔，有差異時退出碼 1，適合掛 CI）與 `--stats`
（印守門組合分布與未複審條數）。

## 改動守門時的 SOP

1. 修改 decorator 或函式內守門邏輯。
2. 執行 `venv/bin/python scripts/route_guard_inventory.py --update`。
3. 確認 diff 只有預期改動的那幾條 endpoint。
4. 重新跑路由守門宣告表測試。

## 四類守門的強度對照表

| 守門 | 檢查四階身分 | 沒有設定資料時 |
|---|---|---|
| `system_admin_required` / `admin_required` | 有 | — |
| `page_keys_required` | 有（Key1+Key2） | 擋（fail-closed） |
| `require_permission` / `permission_required` / `require_any_permission` | **沒有** | 擋 |
| `module_access_required` | **沒有** | **放行**（該企業無 ACL 記錄時，fail-open） |
| 函式內部的 `if` 判斷 | 看寫法 | 看寫法，**掃描抓不到，只能靠 `has_internal_check` 旗標提醒** |

## `has_internal_check: true` 的意義

`has_internal_check: true` 表示 decorator 不是全部。掃描器在函式體內看到 403/401 類型的
拒絕分支，因此人工複審該條 endpoint 時必須讀函式內文，不能只看 decorator 清單。

`internal_identity_check: true` 只是線索：代表函式體內引用 `is_org_admin`、
`is_system_admin` 或 `user_type`。它不是授權結論。

## 欄位允許值

| 欄位 | 允許值 |
|---|---|
| `answer_source` | `code` / `db` / `none`（自動欄位，見下節） |
| `max_audience` | `null`（未判定），或 `SYSTEM_ADMIN` / `ORG_ADMIN` / `EMPLOYEE` / `EXTERNAL` / `ANONYMOUS` / `NON_HUMAN` 的清單 |
| `review` | `unreviewed`（尚未人工判斷）／ `confirmed`（守門正確）／ `intentional_open`（刻意對所有登入者開放，`note` 必須寫理由） |

## `answer_source`：「誰進得來」這個問題由誰回答

複審一條路由時第一個要問的就是這件事，所以它是自動欄位、每條都有。

| 值 | 意思 | 複審時怎麼做 |
|---|---|---|
| `code` | decorator 直接鎖死身分上限 | 讀 decorator 就能確認，最快 |
| `db` | 要查資料庫（選單 Key1/Key2、模組合約與 ACL、permission 指派）才有答案 | **答案隨企業而異**，`note` 要寫明「在什麼資料狀態下成立」 |
| `none` | 沒有任何收斂身分的守門 | 這就是要優先處理的那批 |

分類規則（`classify_answer_source()`）：有任何一個 `system_admin_required` /
`admin_required` / `public_route` / 三個非人身分 decorator → `code`；
否則有 `page_keys_required` / `module_access_required` / permission 系列 → `db`；
否則 `none`。**`login_required` 刻意不算入任何一邊**——它只要求登入，
不收斂到某一階身分，所以只掛它的路由是 `none`。

**建立當時的分布（2026-08-23）**：`code` 392（47%）／`db` 301（36%）／`none` 138（16%）。
`none` 那 138 條 ＝ 84 條完全沒有白名單 decorator ＋ 54 條只掛 `login_required`。

### 這個欄位的已知限制

**只從 decorator 推導，不含 PageRoleGuard 的選單前綴涵蓋**——那需要查 `menu_items`，
而工具刻意不連資料庫（測試才能在無 DB 環境跑）。

所以**標成 `none` 的路由，仍可能被某個 url 型選單的領地涵蓋**（雙鑰匙會擋）。
複審 `none` 的條目時要另外確認這件事，不能直接判定成破口。
反過來說，`link_type='route'` 的選單只守單一 endpoint、不涵蓋子路由（PF-148），
所以「同 blueprint 的隔壁那條有守」不能當成這條也有守的理由。

## 複審流程

後續 session 需要把 `review: unreviewed` 的條目逐條判斷，填入 `max_audience`，再改成
`confirmed` 或 `intentional_open`。若是 `intentional_open`，`note` 必須寫明理由。

**建立當時的現況（2026-08-23，數字會腐爛，要現況跑 `--stats`）**：831 筆全部
`unreviewed`，其中 109 筆 `has_internal_check: true`、53 筆 `internal_identity_check: true`。

複審一條時實際要回答的問題，按順序：

1. **這條路由的 `guards` 裡有沒有任何一項會檢查四階身分？**（見上方強度對照表）
   沒有 → 它對 EXTERNAL 是開放的，除非函式內部另有判斷。
2. **`has_internal_check` 是不是 true？** 是 → 一定要讀函式內文，decorator 清單不是全部。
3. **只掛 `module_access_required` 的**：它在該企業沒有 ACL 記錄時等於放行
   （fail-open）。判斷時要問「這條路由是否可以接受該模組的全體使用者都進得來」，
   而不是「BELUGA 現在擋得住嗎」——後者是資料狀態，不是設計。
4. 填 `max_audience` 時填的是**設計意圖的上限**，不是現在實際進得來的人。

**不要在複審時順手改程式碼。** 發現守門不足就記在 `note` 裡並開待辦，
守門的增減是獨立的變更，要單獨評估與驗收。

目前已知未收斂的重災區是 `modules/form_workflow/` 與 `modules/nocode_builder/`。

## 測試抓得到什麼、抓不到什麼（不要高估這道防線）

`backend/tests/test_route_guard_table.py` 有兩個測試：

- `test_table_schema_valid`：表的結構與人工欄位值域（同進程，快）
- `test_route_guard_table_matches_code`：**用 subprocess 跑 `--check`**，比對
  endpoint 集合與 `guards` / `guard_args`

**一致性那項刻意跑在獨立進程裡，不要改成在測試進程內建 app。**
`app.module_loader.module_loader` 是進程層級單例，第二個以後建立的 app
不會再註冊模組 blueprint——單獨跑本檔時 url_map 有 859 條，
與其他測試一起跑只剩 449 條，表裡的模組 endpoint 會被誤判成「已不存在」。
重設 `_loaded` 也救不回來（實測只還原到 732 條）。這個坑已經踩過一次。

比對範圍的界線：

| 變更 | 測試會不會紅 |
|---|---|
| 新增路由沒登記 | **會** |
| 刪除路由沒清表 | **會** |
| 加上或拿掉一個守門 decorator | **會** |
| 改 decorator 的參數（換 menu_code、`check_acl` 由 True 改 False） | **會** |
| 手改表裡的 `answer_source` | **會**（它由 `guards` 推導，比對時一併驗） |
| **在函式內部加上或拿掉權限判斷**（`has_internal_check` 變動） | **不會** |
| **改動 URL 路徑但 endpoint 名不變** | **不會** |

後兩項刻意不納入比對：`has_internal_check` 是「函式體內有沒有回 403」的啟發式偵測，
把它納入會讓每個新增的錯誤處理都變成紅燈，噪音大過訊號。代價是**函式內部的守門變更
沒有自動防線**，只能靠複審時把它讀進 `note`。

因此「表是綠的」不等於「守門是對的」，只等於「守門與登記一致」。

### 產表與比對用同一條路徑

工具與測試都走 `scripts/route_guard_inventory.py`（`create_app('development')`），
所以不存在「產表用一種 config、比對用另一種」的分歧。
**不要為了讓測試快一點而改成在測試進程內直接建 app**，那會同時踩回上面兩個坑。

### 刻意排除的來源

| 排除對象 | 理由 |
|---|---|
| `venv/` 底下（Flask 內建的 5 條） | 不是本專案的程式碼 |
| `backend/app/web/dev.py`（12 條 `/dev/*`） | 開發專用工具，正式部署不存在 |

`dev.py` 在 `scripts/push_github.sh` 的排除清單內，開源版沒有這個檔，
blueprint 註冊處是 `try/except ImportError`（`backend/app/web/__init__.py:50`）。
**若把那 12 條收進表，開源版一跑測試就會拿到 12 條「表中已不存在的 endpoint」。**
清單在工具的 `DEV_ONLY_SOURCES`，新增同性質的開發專用檔時要一併加進去。

已實測：把 `dev.py` 暫時移走後 `--check` 與兩項測試都通過，放回去也通過。

## 與執行期實測分開

這張表不驗證執行期行為。實際可達性要用另一支工具在指定企業上實測。兩者刻意分開：
宣告表只放程式碼守門事實，不能把企業實測結果寫回這張表。
