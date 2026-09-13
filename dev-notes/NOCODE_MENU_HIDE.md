# NoCode_Builder 選單隱藏（2026-08-07 起，PCHOME 鐵人賽期間）

## 狀態：2026-09-13 已解除

Ethan 定案：現在解除隱藏；鐵人賽（至 2026-10）期間不修改 nocode 程式；
以公告告知使用者「尚未完工、考慮移出本專案、請勿使用」。

- **解除方式**：只做了下方「賽後復原」的**第 1 步（`.env` 加 `NOCODE_BUILDER_MENU=on`）
  與第 3 步（重啟）**，**沒有執行第 2 步的 SQL UPDATE**——當日查證
  `menu_items.code ILIKE 'nocode%'` 已是 **0 筆**（不是本檔原寫的「is_deleted=true 的三筆」），
  原因未查（可能是先前某次清理或 module sync 連同刪除，而非本檔記載的隱藏機制本身所為）。
  重啟後模組同步（force=False）發現選單不存在便自動新建，行為與本檔「只想在新環境開啟」
  段落描述的路徑一致。
- 驗收結果（SQL、四種身分 API/頁面測試、chrome-devtools 導覽列實測）留證：
  `/opt/tmp/verify/20260913-nocode-unhide-exec.log`
- **bpserv（讀者安裝驗證機）解凍時要做的事**：見專案根 `CLAUDE.md`「bpserv 部署凍結」
  累積待做表新增列（`.env` 加 `NOCODE_BUILDER_MENU=on` 後重啟；bpserv 本身沒有這三筆
  選單殘留，重啟時模組同步會自建；DemoSOC 無 nocode 合約，選單不出現是預期）。
- **賽後（含比賽期間）的資安處置**：已知 P1/P2 缺口見 BBN 待辦 **PF-271** 與
  `dev-notes/NOCODE_UNHIDE_SECURITY_AUDIT_20260913.md`，比賽期間不修改
  `modules/nocode_builder/` 程式碼。

以下內容（隱藏機制原理、「賽後復原」步驟原文、隱藏前後各身分可見性）保留作歷史紀錄。
「賽後復原」第 2 步的 SQL 已不適用（該三筆選單當時已不存在），實際只採用了第 1、3 步。

---


## 這是什麼

比賽期間（約 2026-08 ~ 2026-10）NoCode_Builder 尚未完成，**只把它從介面上藏起來**，
避免出現在使用手冊的截圖裡。模組本身照常載入 —— 路由、API、portal 公開頁全部可用，
直接輸入網址仍進得去。**這是刻意的**：藏得越少，賽後復原越簡單。

沒有動的東西（都是為了好復原）：

- 模組 `enabled` 仍為 `True`，blueprint 全部照註冊
- `INSTALLED_MODULES` lookup 仍含 `nocode_builder` → 模組管理頁、合約的「可授權模組」照舊列出
- `permissions` 的 `nocode_builder.view` / `.manage` 仍 active → `/access/` 照舊列出
- `menu_permissions`（3 筆）、`menu_role_requirements`（12 筆）全部保留
- 角色 `SUBSYS_DESIGNER`、合約 `modules_config` 的 `nocode_builder` 都沒動

## 隱藏由兩件事構成

**1. 程式碼（隨 GitHub 走）** — `modules/nocode_builder/__init__.py`

環境變數 `NOCODE_BUILDER_MENU` 不等於 `on` 時，`MODULE_INFO['menu_items']` 為空陣列，
模組不註冊任何平台選單。`.env` 在 `.gitignore` 內，所以**從 GitHub 重裝的環境預設就是隱藏**。

**2. 資料庫（這台開發機既有的三筆選單）**

```
menu_items.code IN ('nocode_builder', 'nocode_builder.sub_systems', 'nocode_builder.lookup')
  → is_deleted = true
```

用 `is_deleted` 而不是 `is_active=false` 是刻意的：`module_menu_service._register_menu_item()`
在 `force` 模式下會把 `is_active=false` 設回 true，而「已被管理員刪除的選單」連 `--force`
也不重建（同檔 line 126 附近）。比賽期間開發 open_defense 很可能會跑
`flask module sync --force`，用 `is_active` 會被意外復活。

## 賽後復原（三步，約 2 分鐘）

```bash
# 1. .env 加一行
echo 'NOCODE_BUILDER_MENU=on' >> /opt/BeakPlatform-dev/.env

# 2. 把三筆選單救回來
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -c "
UPDATE menu_items SET is_deleted = false, deleted_at = NULL, is_active = true, updated_at = NOW()
WHERE code IN ('nocode_builder','nocode_builder.sub_systems','nocode_builder.lookup');"

# 3. 重啟
sudo systemctl restart beakplatform-dev.service && systemctl is-active beakplatform-dev.service
```

驗收：以 ORG_ADMIN（`admin-ethanyu@beluga.com`）登入，導覽列應重新出現
「子系統開發模組 → 子系統開發 / 選項-清單-資料樹」。

只想在新環境開啟（DB 沒有那三筆選單的情況）：做第 1 步再重啟即可，
模組選單同步會自動建立。

## 誰原本看得到（隱藏前的實查結果）

| 身分 | 隱藏前 | 原因 |
|---|---|---|
| ORG_ADMIN | **看得到** | Key1 `menu_permissions` 只發給 ORG_ADMIN；且 ORG_ADMIN bypass Key2 角色過濾（`_menu_tree.py:129`） |
| EMPLOYEE / EXTERNAL | 看不到 | 沒有 Key1 記錄。要看到必須「模組 ACL 指派」**且**「有 `SUBSYS_DESIGNER` 角色」兩者兼備 |
| SYSTEM_ADMIN | 看不到 | 系統管理員不注入模組選單（`_menu_tree.py:71`） |

所以隱藏的實際受眾就是 ORG_ADMIN —— 也正是手冊截圖用的身分。

## 隱藏當日的驗收留證

`/opt/tmp/verify/20260807-nocode-menu-hide.log`
（ORG_ADMIN 導覽列實測、`/api/menu` 53 節點無 nocode、六個 nocode 端點仍 200、
工作區瀏覽器實測正常渲染）

備份：`/opt/tmp/backup/nocode-menu-hide-20260807/`（`__init__.py` 原檔 + 三筆選單 CSV）
