# PF-145 階段二：模組 API 的 Key1 系統性盤點

**2026-08-23 產出。這一份只出清單、不改程式**（交付邊界見待辦 PF-145 冷讀補洞第 4 點）。
階段一（open_defense 資安案件五支）已於 commit `809ea8ba` 完成。

機器可讀版：`dev-notes/pf145_module_api_audit.csv`（334 筆，欄位
`level,module,url,file,line,func,gates,callers,menu_candidates`）。
重跑指令：`venv/bin/python scripts/audit_module_api_gates.py`（AST 解析，不靠 grep 猜）。

---

## 一、結論摘要：三件比「某支 API 沒掛 decorator」更要緊的事

### 1. 模組 ACL 是 fail-open，而新企業預設就是全開狀態（實測確認）

> **2026-09-01 已修（PF-145 階段三之一）**：`check_user_access()` 改為
> fail-closed（零筆 ACL＝拒絕），配套 `default_acl_roles` 種入機制與
> migration 135。本節以下是 2026-08-23 的歷史現況，現行規範見 CLAUDE.md PERM-04。

`ModuleAccessService.check_user_access()` 第 96~97 行：

```python
if count == 0:
    return True  # 無 ACL = 不限制
```

也就是說 `@module_access_required('form_workflow')`（`check_acl=True`）**在該企業沒有任何
`module_access_control` 記錄時，效力等同 `check_acl=False`**——只驗合約。

2026-08-23 各企業的 ACL 記錄現況：

| 企業 | 有 ACL 記錄的模組 | 有合約但無 ACL 的模組 |
|---|---|---|
| BELUGA | form_workflow(2), nocode_builder(3), spec_formulate(1) | open_defense, vuln_lifecycle |
| SYSTEM | form_workflow(2), nocode_builder(1), spec_formulate(1) | — |
| LION | **無** | open_defense（其餘合約已過期） |
| TEST00 | **無** | form_workflow |

**實測（TEST00 的純員工 `ethan@test00.com`，無任何內部角色）：**

```
/api/workflows/data/org-tree         -> 200  全企業組織樹
/api/workflows/data/org-roles        -> 200  全企業角色清單（1733 bytes）
/api/workflows/data/org-departments  -> 200
/api/workflows/data/org-api-keys     -> 200  企業 API Key 清單
/api/workflows/data/sql-procedures   -> 200  SqlExecutor 白名單 SP 定義與說明
/api/forms/data/formio-templates     -> 200
/api/workflows/list, /api/forms/list -> 200  （回傳的是設計器整頁 HTML，見第 3 點）
```

對照組：同一批端點對 BELUGA 的 EXTERNAL 與純員工全部 403（因為 BELUGA 設了 ACL）。

**所以 B 級那 153 支的實際防護力不是程式決定的，是「該企業管理員有沒有去設 ACL」決定的。**
留證：`/opt/tmp/verify/20260823-pf145-stage2-probe.log`。

### 2. 已確認的越權：`/api/form-center/org-tree` 對 EXTERNAL 回傳全企業組織樹

BELUGA 的 EXTERNAL 帳號 `gg@gmail.com`（只有 `EXTERNAL_USERS` 角色）實打：

```
/api/form-center/org-tree        -> 200  1802 bytes，含「行銷部門」等完整部門與人員樹
/api/form-center/available-forms -> 200  （空陣列，該帳號確實沒有可填表單）
/api/form-center/pending-tasks   -> 200  （空陣列，同上）
```

後兩支回空陣列是**正確**行為——它們以呼叫者身分為過濾條件，回的是「自己的」資料。
`org-tree` 不是：它回的是全企業組織架構，與呼叫者身分無關。
**廠商帳號看得到客戶的組織圖與人員名單，這是實質洩漏。**

### 3. 有 4 支「頁面」掛在 `/api/` 前綴下，因此永遠不吃雙鑰匙

`/api/workflows/list`、`/api/workflows/designer`、`/api/forms/list`、`/api/forms/designer`
回的是 HTML 整頁（實測 19~33 KB，`<!DOCTYPE html>` 開頭）。
`/api/` 在 `PageRoleGuard.SKIP_PREFIXES` 內，所以這四頁**結構上不可能被雙鑰匙保護**，
不論選單怎麼設。它們是不是還在用要先查（前端反查不到呼叫者），
能刪就刪，要留就搬到 `/forms/` 底下。

### 4. 待辦卡上「spec_formulate 路由數 0」是錯的，實際 32 支

成因：卡上的 grep 用 `^@.*\.route(`，而 `spec_formulate` 的路由全部寫在
`def register(bp):` 內部、decorator 有縮排，所以一支都沒抓到。
那 32 支全是 B 級（`@module_access_required('spec_formulate')`），
在無 ACL 的企業一樣是 fail-open。

---

## 二、分級定義

判級取「最強的那個閘門」，同一支有多個 decorator 時不重複計。

| 級 | 定義 | user_type 硬界線 | 支數 |
|---|---|---|---|
| **A** | 只有 `@module_access_required(mod, False)` — 僅驗企業合約 | 無 | 35 |
| **B** | 只有 `@module_access_required(mod)` — 合約 + 模組 ACL（**無 ACL 記錄時 fail-open**） | 無 | 153 |
| **C** | `@require_permission` / `@permission_required` / `@require_any_permission` — 角色制 | **無**（PERM-03） | 45 |
| **D** | `@page_keys_required` / `@admin_required` / `@system_admin_required` | **有** | 89 |
| **E** | webhook HMAC / service account / api key HMAC / `@public_route` | 各自認證 | 12 |

各模組分布：

| 模組 | A | B | C | D | E | 合計 |
|---|---:|---:|---:|---:|---:|---:|
| form_workflow | 24 | 66 | 32 | 14 | 5 | 141 |
| nocode_builder | 11 | 55 | 1 | 46 | 1 | 114 |
| open_defense | 0 | 0 | 1 | 29 | 5 | 35 |
| spec_formulate | 0 | 32 | 0 | 0 | 0 | 32 |
| vuln_lifecycle | 0 | 0 | 11 | 0 | 1 | 12 |
| **合計** | **35** | **153** | **45** | **89** | **12** | **334** |

**沒有任何模組 blueprint 掛 `before_request`**（已查證），所以上表就是全部的閘門，
沒有隱形防線。

---

## 三、各級的處理建議

### D 級（89 支）：不動

已有 user_type 硬檢查。**但若日後要「開放給非管理員」，必須同時補 Key1，
不能只把 `@admin_required` 換成角色制**——那是 PF-145 的根因（見 CLAUDE.md PERM-03）。

### E 級（12 支）：不動

走各自的認證管道，不在雙鑰匙的討論範圍。

### C 級（45 支）：本次不修，但要知道它的暴露條件

要越權必須先讓 EXTERNAL 帳號拿到含該 permission 的角色。實測 BELUGA 的 EXTERNAL
與純員工打 C 級端點全部 403 —— 也就是**預設狀態是安全的**，
風險來自「管理員把內部角色指派給 EXTERNAL」這個誤操作，
而那正是**階段三**（`roles` 加 user_type 約束）要從根本擋掉的事。

在階段三完成前，C 級的最小成本補強是：
`vuln_lifecycle` 11 支與 `form_workflow` 的 ai-usage 4 支各自只對應單一選單頁
（`vuln_lifecycle.*`、`form_workflow.ai_usage`），可以直接加掛 `@page_keys_required`
與既有 permission 併存（兩者是 AND，不衝突）。

### B 級（153 支）：主戰場，但**不要 153 支全掛**

分三類處理：

1. **選單候選唯一（47 支）** → 直接加掛該頁的 `@page_keys_required`，最安全
2. **反查不到前端呼叫者（104 支）** → 要先確認它還活著。多半是設計器內部
   API 或已無人使用的舊端點，**逐支確認前再動**
3. **選單候選多於一個（2 支）** → **不要掛**，會誤擋（PF-142 已踩過一次）

**但真正該優先做的不是逐支加掛，而是決定「模組 ACL 要不要改成 fail-closed」**：
把 `check_user_access()` 的 `count == 0 -> True` 改成 fail-closed，
等於一次修好 153 支；代價是所有沒設 ACL 的企業會全部被擋（TEST00、LION 現在就是），
需要配套「建企業時自動 seed 一筆全員 ACL」。
**這是全平台變更，屬階段三的範圍，要單獨評估、單獨驗收，不要在階段二順手做。**

### A 級（35 支）：分兩種，不要一視同仁

- **24 支 form-center**：表單中心是「所有企業成員都要用」的終端頁面，
  `check_acl=False` 是刻意設計（decorator docstring 明寫「終端用戶頁面可設 False」）。
  這些端點多數以呼叫者身分為過濾條件（`pending-tasks`、`my-forms` 對 EXTERNAL 回空陣列），
  **掛 `page_keys_required` 反而會擋掉正常使用者**。
  **唯一該修的是 `/api/form-center/org-tree`**（見第一節第 2 點）：
  它回全企業組織樹、與呼叫者身分無關。修法不是掛 Key1（表單中心對 EXTERNAL 是開放的），
  而是**依呼叫者身分裁剪回傳範圍**，或確認呼叫端（`fc-*.js`）是否真的需要整棵樹。
- **11 支 nocode_builder**：portal / site-map context 類，走 portal 世界的判定，
  要對照 `dev-notes/codex_spec/portal.md` 判斷，不適用平台雙鑰匙。

---

## 四、建議的施工順序（第二次交付用）

| 順序 | 內容 | 規模 | 風險 |
|---|---|---|---|
| ~~1~~ | ~~`/api/form-center/org-tree` 依身分裁剪~~ **已完成 2026-08-23**（見本節下方） | 小 | 低 |
| ~~2~~ | ~~C 級中選單唯一的 15 支加掛 `page_keys_required`~~ **已完成 2026-08-23，實際是 29 支**（見本節下方） | 小 | 低 |
| ~~3~~ | ~~B 級「選單候選唯一」47 支，一模組一 commit~~ **已完成 2026-08-23，實際掛 52 支**（見本節下方） | 中 | 中（要逐支實測） |
| ~~4~~ | ~~四支掛在 `/api/` 下的頁面路由~~ **已完成 2026-09-01，確認零引用後刪除**（commit `640ddc2b`） | 小 | 低 |
| ~~5~~ | ~~B 級反查不到呼叫者的 104 支~~ **已完成 2026-09-01**（見本節下方「第 5 項已完成」；實際可動範圍是 form_workflow 36 + spec_formulate 1，nocode_builder 55 支因選單隱藏中另案） | 大 | — |
| 6 | （階段三）模組 ACL fail-open → fail-closed + 建企業時 seed | 大 | **高，全平台** |
| 7 | （階段三）`roles` 加 user_type 約束 | 大 | **高，全平台** |

### 第 1 項已完成（2026-08-23）

做法是 A + C 併行，**沒有**加掛 `page_keys_required`（表單中心對 EXTERNAL 是刻意開放的，
掛了會擋掉正常的廠商填單）：

- **A**：`current_user.is_external` 時直接回空樹。UserPicker 的可選對象本來就只有
  EMPLOYEE/ORG_ADMIN，廠商拿這棵樹沒有用途
- **C**：`data` 不再帶 `username`，`label` 也不再是「顯示名 (username)」

**C 案原本設計的「重名改用部門名區隔」在真實資料下不夠用**——兩帳號制
（同一個活人的企業成員帳號與管理員帳號，`PERMISSION_MODEL.md` §5.1）下，
兩個帳號 `display_name` 相同、又都沒有部門，拿掉 username 後畫面上會出現
兩個一模一樣的選項，使用者選簽核人時無從分辨。

重名時的區隔資訊改成兩層（Ethan 2026-08-23 定案）：

```
第一順位 部門名     最直覺，同部門又同名的機率極低
第二順位 員工編號   users.employee_id，欄位註解寫明「組織內唯一」，實測無重複
```

兩者都取不到就不加後綴。**暱稱（`native_name`）與 `username` 都不能拿來墊**：
前者可免填、後者正是這次要停止外流的東西。

**已知落差**：兩帳號制的管理員帳號**沒有 `employee_id`**（實測全平台 4 個空值
帳號全是 ORG_ADMIN），所以同名的那組會是「成員帳號有 (編號)、管理員帳號沒有後綴」。
仍分得出來但要靠推理；要更明確就得幫管理員帳號補編號。
實測結果 `ethanyu (0001)` 與 `ethanyu`。

驗收留證 `/opt/tmp/verify/20260823-pf145-orgtree.log`：
EXTERNAL 拿到 26 bytes 空樹；內部身分的樹無任何 `username` 欄位；
瀏覽器實測選人 modal 渲染正常、點選後 `secure_code` 正確寫進 `submission.data`。

反向檢查：全專案模組 API 只剩兩處輸出 `username`
（`fc_utils.py:103` 的 `/current-user`、`site_map_api.py:560` 的 `$CURRENT_USER_NAME`），
兩處都是呼叫者自己的資料；平台 API 側輸出 `username` 的端點閘門逐一查過，
沒有第二條把他人帳號名交給 EXTERNAL 的路徑。

### 第 2 項已完成（2026-08-23），數字更正為 29 支

**先前寫的「15 支」是錯的**：那是憑印象估的（vuln_lifecycle 11 + ai_usage 4），
沒有實際跑篩選。而且 `scripts/audit_module_api_gates.py` 當時的反查只從 `.js` caller
往回推 template，漏掉「template 內嵌 script 直接打 API」的寫法（vuln_lifecycle 五個
頁面全是這樣），所以那 11 支在 CSV 裡是「無選單候選」。腳本已修，重跑後 C 級的
分布是：**選單唯一 29、多候選 7、無候選 9**。

掛上的 29 支：

| 選單 code | 支數 | 檔案 |
|---|---:|---|
| `form_workflow.workflows` | 13 | `workflow_routes.py` |
| `form_workflow.ai_usage` | 4 | `ai_usage.py` |
| `form_workflow.templates` | 4 | `template_routes.py`（只有 batch/*） |
| `vuln_lifecycle.kynd` | 4 | `vuln_lifecycle/api/__init__.py` |
| `vuln_lifecycle.assets` | 2 | 同上 |
| `vuln_lifecycle.risk` | 2 | 同上 |

**沒掛的 7 支多候選**：`/api/form-workflow/templates` 五支同時被
`open_defense.event_routing` 頁使用，`/api/vuln-lifecycle/dashboard/summary` 與
`/health` 同時對到 dashboard 與 open_defense.dashboard。掛了會誤擋（PF-142 實測過）。

#### vuln_lifecycle 那 8 支要先修選單，不然會擋掉正牌使用者

`vuln_lifecycle.assets/.kynd/.risk` 的 Key1 只開 ORG_ADMIN、Key2 是空的，
但 `RISK_CONTROLLER` 角色（EMPLOYEE 型）握有全部 `vuln_lifecycle.*` permission，
API 實測全部 200 —— 症狀是「API 打得到、選單看不到」，與 form_workflow 那邊相反。

處置（Ethan 2026-08-23 拍板）：先讓選單與 API 一致，再掛 page_keys。

- `scripts/migrations/legacy/111_open_vuln_lifecycle_menu_to_risk_controller.py`
  （冪等，`--dry-run` / `--run`）：Key1 補 EMPLOYEE 5 筆、Key2 補 RISK_CONTROLLER 28 筆
- 出廠預設同步改兩處（MENU-01：只改 DB 的話新建企業會長回舊樣子）：
  `modules/vuln_lifecycle/__init__.py` 的 `user_types`、
  `backend/app/defaults/menu_defaults.py` 的 `MENU_ROLE_DEFAULTS`
- 父選單 `vuln_lifecycle` 是 header 型，依規範只補 Key1、不列入 Key2

#### 驗收

六種身分 × 七支代表性端點，**修改前後狀態碼完全相同**（留證
`/opt/tmp/verify/20260823-pf145-clevel.log`）—— 這 29 支是加防線，不改變現有行為。

正因為全綠，兩批都做了 **mutation 驗證**（把 `page_keys_required` 暫時 stash 掉再測）：

| 情境 | 移除修復 | 裝回修復 |
|---|---|---|
| EXTERNAL 持 `FLOW_DESIGNER` 打 workflows 三支 | 200 200 200 | 403 403 403 |
| EXTERNAL 持 `RISK_CONTROLLER` 打 vuln 三支 | 200 200 200 | 403 403 403 |

瀏覽器實測：`RISK_CONTROLLER` 的 shen.qing.zhe 現在 navbar 出現「弱點管理」，
`/vuln/assets` 正常載入 544 筆資產，console 無錯誤。
完整測試 1 failed（PF-34 已知）/ 623 passed / 2 skipped。

**每一支改完都要用該端點的實際使用者身分實測**（CLAUDE.md TENANT-02 末段），
測試庫沒有 RBAC seed，單元測試抓不到權限鏈的問題。

### 第 3 項已完成（2026-08-23），實際掛 52 支

commit `bc21a720`（form_workflow）+ `97b6b892`（spec_formulate），一模組一 commit。
留證 `/opt/tmp/verify/20260823-pf145-stage3.log`。

CSV 篩出來的「B 級 + 選單唯一」是 **45 支**（不是先前寫的 47，腳本修過反查後數字變了），
最後掛了 52 支，差額都有明確理由：

| 處置 | 支數 | 說明 |
|---|---:|---|
| `@page_keys_required('form_workflow.mappings')` | 18 | `mappings.py`；19 支中扣掉 `list_mappings` |
| `@page_keys_required('form_workflow.workflows')` | 1 | `workflows.py::delete_subflow` |
| `@admin_required`（**不是** page_keys） | 2 | `fc_utils.py` 的 column-config 兩支 |
| `@page_keys_required('spec_formulate.spec_schema')` | 31 | 5 個 `_mf_*.py`；CSV 列 23 支，另 8 支見下 |
| 刻意不掛 | 1 | `list_mappings` |

#### 三個「不能照 CSV 機械執行」的判斷

**一、`GET /api/mappings`（`list_mappings`）不掛。**
CSV 的 `callers` 欄是按 URL 前綴聚合的，看起來 19 支都被三個檔案呼叫，
實際逐行查是：`api-keys.js:96` 只打 `/api/mappings/published?status=Published`、
`ir-designer.js:379` 只打 `/api/mappings?is_published=true&is_archived=false`。
後者是 NoCode IR 設計器的「已發行表單」下拉，掛了會擋掉沒有
FLOW/FORM_DESIGNER 的 NoCode 設計者。
`GET /api/mappings/published` 的第二個消費者 `api_keys.html` 則沒問題——
該頁選單 `api_key_manage` 的 Key1 只開 ORG_ADMIN，而 ORG_ADMIN 一律 bypass page_keys。

**判讀 CSV 時的通則：`callers` 欄只能當「要去看哪幾個檔案」的線索，
不能當成「這支端點的呼叫者清單」。** 逐支確認要 grep 完整路徑。

**二、`form_workflow.center` 的 column-config 兩支改掛 `@admin_required`。**
（`GET /column-config/all`、`PUT /column-config`，docstring 都寫「管理員用」，
前端按鈕是 `x-show="isAdmin"`，`isAdmin` 來自 `web/__init__.py:183` 的 `is_org_admin`。）

掛該頁的 page_keys **等於沒掛**：表單中心的 Key1 含 EXTERNAL、
Key2 是人人都有的 `EMPLOYEE`/`EXTERNAL_USERS`，所有能開表單中心的人都通得過。
這兩支真正缺的是 D2 的後端那半（前端隱藏不是防線）。Ethan 2026-08-23 拍板改掛
`admin_required`；代價是 BELUGA 的 FLOW_DESIGNER 由 200 轉 403，
但該按鈕對他本來就是隱藏的，沒有正常用途。

**「B 級選單唯一 → 掛該頁 page_keys」不是萬用規則。**
遇到「該頁的鑰匙比這支端點的實際受眾寬很多」時，page_keys 只是裝飾，
要回頭看端點自己的受眾是誰。

**三、spec_formulate 掛 31 支而非 CSV 的 23 支。**
另外 8 支（`cg/info`、`cg/tables`、`cg/tables/<t>/introspect`、`export/pdf`、
`available-templates`、`pg/ensure-db`、`pg/tables`、`pg/tables/<t>/introspect`）
被腳本歸為「無選單候選」，**成因是編輯器頁 `/spec-formulate/<spec_sc>/edit`
不是選單項目**——`spec_formulate.spec_schema` 是 `route` 型、`link_target` 指向
`spec_formulate_web.spec_schema` 這個 endpoint，PageRoleGuard 的
endpoint 精確匹配因此只涵蓋列表頁。它們與那 23 支同屬一個功能、同一批 JS 呼叫。
Ethan 2026-08-23 拍板一起掛。

唯一沒掛的 `get_or_create_spec_by_form_template`（`/by-form-template/<ft_sc>`）
呼叫者是 `form_designer.html`，屬 `form_workflow.templates` 頁，掛了會誤擋。

#### 順帶修掉的選單設定缺陷：表單中心對新企業的廠商是關著的

`MENU_ROLE_DEFAULTS['form_workflow.center']` 是 `['ORG_ADMIN', 'EMPLOYEE']`，
**漏了 `EXTERNAL_USERS`**。BELUGA/LION/SYSTEM 的 DB 有人補過所以正常，
依出廠值新建的企業（TEST00 起）沒有 —— 廠商帳號開 `/forms/center` 會被
PageRoleGuard Key2 擋成 302 強制登出，與 CLAUDE.md「表單中心對 EXTERNAL 刻意開放」矛盾，
而且不報任何錯。

處置（MENU-01 兩件事都做）：`menu_defaults.py` 補 `EXTERNAL_USERS`；
`scripts/migrations/legacy/113_form_center_menu_external_users.py`（冪等）對既有企業補同一筆，
實際只有 TEST00 缺。

#### 驗收

修改前後各跑一次「六身分 × 45 端點」矩陣，另補跑無 ACL 企業的純員工
（TEST00，PERM-04 fail-open 的實際曝露面）。**唯一預期外的變動要能解釋**：

| 身分 | 變動 | 解釋 |
|---|---|---|
| FLOW_DESIGNER / RISK_CONTROLLER | colcfg 兩支 200 → 403 | `admin_required` 的預期收緊 |
| TEST00 純員工 | mappings 全組 200/404 → 403、colcfg 200 → 403 | 收緊；該企業的 `/forms/mappings` 頁本來就 302 |
| TEST00 純員工 | `list_mappings` 維持 200 | 刻意不掛 |
| 其餘 | 逐格相同 | 加防線不改行為 |

全綠的部分照規矩做 mutation（`git stash` 掉 api 檔，重啟後再測）：

| 情境 | 移除修復 | 裝回修復 |
|---|---|---|
| EXTERNAL `gg` 持 `FLOW_DESIGNER` 打 mappings/subflow/colcfg 六支 | 404 200 200 200 500 200 | 全 403 |
| EXTERNAL `gg` 持 `SPEC_DESIGNER` 打 spec 十支 | 與 ORG_ADMIN 完全相同（含 `pg/tables` 這類 DB introspection） | 全 403 |
| migration 113：TEST00 臨時 EXTERNAL 帳號開 `/forms/center` | 移除該 Key2 → 302 | 有該 Key2 → 200 |

測試用的角色指派與臨時帳號都已撤銷／硬刪除（`users`／`user_role_assignments`／
`audit_logs`／`used_user_numbers` 殘留皆為 0）。

瀏覽器實測（ORG_ADMIN 與 FLOW_DESIGNER，chrome-devtools）：配對頁 11 列、
API Key 頁 `publishedForms` 7 筆、表單中心欄位設定 modal 開啟 13 欄並儲存成功、
FLOW_DESIGNER 的欄位設定鈕 `offsetParent === null`、規格管理 2 筆、
規格編輯器實際點擊 [讀入資料表]（走新掛的 `pg/tables`）回 5 張表，全程 console error = 0。

完整測試 1 failed（PF-34 已知）/ 623 passed / 2 skipped，與基準相同。

重跑盤點後分級：**A35 / B101 / C16 / D170 / E12**（B 減 52、D 增 52）。
**B 級選單唯一只剩 1 支**，就是刻意不掛的 `list_mappings`。

#### 施工3 發現、已另外開單的三件

| 單號 | 內容 |
|---|---|
| **PF-148** | route 型選單（`link_target` 是 endpoint 名）只守那一個 endpoint，同 blueprint 的子路由不進雙鑰匙判定。實測 49 條不受涵蓋的頁面路由逐條判過，真正的缺口只有 `/spec-formulate/<sc>/edit` |
| **PF-149** | `GET /api/mappings/available` 反查不到呼叫者（`mappings.py` 裡唯一沒處理的一支） |
| **PF-150** | `POST /api/users/` 忽略 `user_type`、一律建成 EMPLOYEE 並順帶指派 `EMPLOYEE` 角色 |

---

### 第 4、5 項已完成（2026-09-01，commit 見 git log）

**第 4 項**：`/api/workflows/list|designer`、`/api/forms/list|designer` 確認全專案
零引用（無 JS/HTML、無 `url_for`、無選單、無測試）且與 `form_workflow_web` 正牌頁
渲染同一批模板、守門更弱，直接刪除。留證 `/opt/tmp/verify/20260901-pf145-stage4.log`。

**第 5 項**：逐支精確反查（不信 CSV 的前綴聚合 callers，逐 URL grep ＋ JS→template
對映 ＋ HTTP method 比對）後的處置：

| 處置 | 支數 | 明細 |
|---|---:|---|
| 掛 `@page_keys_required('form_workflow.templates')` | 8 | forms.py 7（formio-templates ×2、templates CRUD 5：create/get/update/delete/save-new-version）＋ spec_formulate `by-form-template`（呼叫者唯一是 form_designer.html，跨模組掛呼叫頁的鑰匙） |
| 掛 `@page_keys_required('form_workflow.workflows')` | 20 | workflows.py 18（templates CRUD 6、org-* 4、node-definitions、sql-procedures、roles、forms/<id>/fields、subflows ×2、mapped-forms、variable-mapping）＋ backgrounds.py 2（update/delete——只有 wf-canvas.js 呼叫） |
| **刪除（歷史上從未有呼叫者**，`git log -S/-G` 全歷史零命中，皆為模組移轉 `ddf4b3ed` 帶進來的死板面） | 6 | forms 側 `list_templates`(GET)、`get_template_fields`、`publish_template`、`unpublish_template`；`get_node_schema`（/api/workflows/nodes/<t>/schema）；`list_available_forms`（/api/mappings/available，**PF-149 一併收掉**） |
| 跨頁不掛（兩個設計器共用，單一 menu_code 會誤擋；decorator 屬 security-core 禁改，不擴充） | 3 | `GET /api/forms/data/categories`、`GET /api/workflows/backgrounds`、`POST /api/workflows/backgrounds/upload` |
| 不動（NoCode 選單隱藏中，page_keys 對不存在選單 fail-closed，掛了全擋死） | 55 | nocode_builder 全部 B 級，等選單復原或改走 D2 判準，另案 |

驗收（留證 `/opt/tmp/verify/20260901-pf145-stage5.log`）：
六身分 × 15 端點矩陣前後比對——TEST00（臨時合約重現無 ACL fail-open）純員工
整排 200→403、BELUGA FLOW_DESIGNER 表單側 200→403 而流程側維持 200、
管理員與既有 403 全數不變；mutation 三段（EXTERNAL gg 暫掛三設計者角色：
修復在位 403 → stash 200 漏洞重現 → pop 403）；瀏覽器實測 FLOW_DESIGNER
流程設計器與 ORG_ADMIN 表單設計器 XHR 全 200。臨時合約、測試角色指派已清除。

**順帶發現（未處理）**：`wf-tree.js:268` 呼叫的
`/api/workflows/data/templates/by-code/<code>` 端點**從來不存在**（try + `.ok` 包著
所以靜默失敗，樹系圖少掉該節點）。表單設計器 console 既有
`static/vendor/flatpickr-formio/*` 404（formio 對 datetime 欄位的 lazy-load，
目錄不在 repo），與守門無關。

刪除後 `/api/mappings/available` 落入 `GET /api/mappings/<sc>` 動態路由
（已掛 `form_workflow.mappings` 鑰匙），持鑰者 404、無鑰者 403，屬預期。

## 五、逐支清單

**這一節是 2026-08-23 第一次交付當下的快照，施工1~3 之後已經腐爛**（B 級由 153 降到 101）。要看現況一律重跑
`venv/bin/python scripts/audit_module_api_gates.py` 並讀 CSV，不要引用下面的數字。

### A 級明細（35 支）

| 端點 | 現有閘門 | 前端呼叫者 | 選單候選 |
|---|---|---|---|
| `/api/form-center/available-forms` | `module_access_required('form_workflow', False)` | fc-data-loader.js | form_workflow.center |
| `/api/form-center/canned-messages` | `module_access_required('form_workflow', False)` | fc-canned-messages.js | form_workflow.center |
| `/api/form-center/canned-messages` | `module_access_required('form_workflow', False)` | fc-canned-messages.js | form_workflow.center |
| `/api/form-center/canned-messages/<secure_code>` | `module_access_required('form_workflow', False)` | fc-canned-messages.js | form_workflow.center |
| `/api/form-center/canned-messages/<secure_code>` | `module_access_required('form_workflow', False)` | fc-canned-messages.js | form_workflow.center |
| `/api/form-center/column-config` | `module_access_required('form_workflow', False)` | fc-column-config.js | form_workflow.center |
| `/api/form-center/current-user` | `module_access_required('form_workflow', False)` | formio-user-picker.js | form_workflow.center |
| `/api/form-center/executions/<instance_id>/logs` | `module_access_required('form_workflow', False)` | fc-flow-overview.js,fc-monitor.js… | form_workflow.center;form_workflow.workflows |
| `/api/form-center/executions/<instance_id>/path` | `module_access_required('form_workflow', False)` | fc-flow-overview.js,fc-monitor.js… | form_workflow.center;form_workflow.workflows |
| `/api/form-center/force-end/<secure_code>` | `module_access_required('form_workflow', False)` | fc-monitor.js | form_workflow.center |
| `/api/form-center/form-detail/<secure_code>` | `module_access_required('form_workflow', False)` | fc-monitor.js,fc-read-form.js | form_workflow.center |
| `/api/form-center/forms/<secure_code>` | `module_access_required('form_workflow', False)` | fc-form-fill.js | form_workflow.center |
| `/api/form-center/my-forms` | `module_access_required('form_workflow', False)` | fc-data-loader.js | form_workflow.center |
| `/api/form-center/my-forms/<secure_code>` | `module_access_required('form_workflow', False)` | fc-data-loader.js | form_workflow.center |
| `/api/form-center/my-test-forms` | `module_access_required('form_workflow', False)` | fc-read-form.js | form_workflow.center |
| `/api/form-center/org-tree` | `module_access_required('form_workflow', False)` | formio-user-picker.js | form_workflow.center |
| `/api/form-center/pending-tasks` | `module_access_required('form_workflow', False)` | fc-approval.js,fc-batch-approval.js… | form_workflow.center;open_defense.security_cases |
| `/api/form-center/pending-tasks/<secure_code>` | `module_access_required('form_workflow', False)` | fc-approval.js,fc-batch-approval.js… | form_workflow.center;open_defense.security_cases |
| `/api/form-center/pending-tasks/<secure_code>/approve` | `module_access_required('form_workflow', False)` | fc-approval.js,fc-batch-approval.js… | form_workflow.center;open_defense.security_cases |
| `/api/form-center/pending-tasks/<secure_code>/lock` | `module_access_required('form_workflow', False)` | fc-approval.js,fc-batch-approval.js… | form_workflow.center;open_defense.security_cases |
| `/api/form-center/pending-tasks/<secure_code>/lock` | `module_access_required('form_workflow', False)` | fc-approval.js,fc-batch-approval.js… | form_workflow.center;open_defense.security_cases |
| `/api/form-center/pending-tasks/batch-approve` | `module_access_required('form_workflow', False)` | fc-batch-approval.js | form_workflow.center |
| `/api/form-center/submit` | `module_access_required('form_workflow', False)` | fc-form-fill.js | form_workflow.center |
| `/api/form-center/workflow-progress/<secure_code>` | `module_access_required('form_workflow', False)` | — | — |
| `/api/nocode-builder/sub-systems/<secure_code>/portal` | `module_access_required('nocode_builder', False)` | ir-designer.js,page-template.js… | — |
| `/api/nocode-builder/sub-systems/<ss_sc>/pages/<ssp_sc>/context` | `module_access_required('nocode_builder', False)` | ir-designer.js,page-template.js… | — |
| `/api/nocode-builder/sub-systems/<ss_sc>/site-map/menu-tree` | `module_access_required('nocode_builder', False)` | ir-designer.js,page-template.js… | — |
| `/api/nocode-builder/sub-systems/<ss_sc>/site-map/nodes/<node_sc>/context` | `module_access_required('nocode_builder', False)` | ir-designer.js,page-template.js… | — |
| `/api/nocode-builder/sub-systems/<ss_sc>/site-map/user-tree` | `module_access_required('nocode_builder', False)` | ir-designer.js,page-template.js… | — |
| `/api/nocode-builder/views/<secure_code>/formio-schema` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |
| `/api/nocode-builder/views/<secure_code>/rows` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |
| `/api/nocode-builder/views/<secure_code>/rows` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |
| `/api/nocode-builder/views/<secure_code>/rows/<row_id>` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |
| `/api/nocode-builder/views/<secure_code>/rows/<row_id>` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |
| `/api/nocode-builder/views/<secure_code>/rows/<row_id>` | `module_access_required('nocode_builder', False)` | datalist-widget.js,formgrid-widget.js | — |

### B 級中「選單候選唯一」的（47 支，優先處理）

| 端點 | 現有閘門 | 前端呼叫者 | 選單候選 |
|---|---|---|---|
| `/api/form-center/column-config` | `module_access_required('form_workflow')` | fc-column-config.js | form_workflow.center |
| `/api/form-center/column-config/all` | `module_access_required('form_workflow')` | fc-column-config.js | form_workflow.center |
| `/api/form-workflow/form-themes` | `module_access_required('form_workflow')` | form-designer-theme.js,form-themes.js… | form_workflow.form_themes |
| `/api/form-workflow/form-themes/<secure_code>` | `module_access_required('form_workflow')` | form-designer-theme.js,form-themes.js… | form_workflow.form_themes |
| `/api/mappings` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>/archive` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>/publish` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/<secure_code>/unarchive` | `module_access_required('form_workflow')` | api-keys.js,mappings.js… | form_workflow.mappings |
| `/api/mappings/numbering-rules` | `module_access_required('form_workflow')` | mappings.js | form_workflow.mappings |
| `/api/mappings/published` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>/archive` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>/reopen` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>/sql-sync` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>/sql-sync/status` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/published/<secure_code>/suspend` | `module_access_required('form_workflow')` | api-keys.js,mappings.js | form_workflow.mappings |
| `/api/mappings/unmapped-forms` | `module_access_required('form_workflow')` | mappings.js | form_workflow.mappings |
| `/api/mappings/workflows-for-mapping` | `module_access_required('form_workflow')` | mappings.js | form_workflow.mappings |
| `/api/workflows/data/subflows/<secure_code>` | `module_access_required('form_workflow')` | wf-accordion-subflow.js,wf-tree.js… | form_workflow.workflows |
| `/api/spec-formulate/schema/data-classes` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/data-classes/<data_class>/facet-defaults/<facet_name>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/export/docx` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/cg/apply-to-table` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/cg/compare/<table_name>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/cg/create-table` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/create-form` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/history` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/link-form` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/pg/apply-to-table` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/pg/compare/<table_name>` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/pg/create-table` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/pg/unlink-table` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/populate-facet` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/sync-to-form` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/unlink-form` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/specs/<spec_sc>/versions` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |
| `/api/spec-formulate/schema/translate` | `module_access_required('spec_formulate')` | spec-schema-editor.js,spec-schema.js | spec_formulate.spec_schema |

### B 級中「反查不到選單」的（104 支，需人工判讀）

| 前綴 | 支數 | 檔案 |
|---|---|---|
| `/api/nocode-builder/sub-systems` | 28 | __init__.py, portal_org_api.py, portal_permission_api.py, site_map_api.py… |
| `/api/nocode-builder/projects` | 19 | bridge_api.py, project_api.py |
| `/api/workflows/data` | 18 | workflows.py |
| `/api/forms/data` | 12 | forms.py |
| `/api/spec-formulate/schema` | 9 | _mf_cg.py, _mf_export.py, _mf_form_link.py, _mf_pg.py |
| `/api/workflows/backgrounds` | 4 | backgrounds.py |
| `/api/nocode-builder/schema` | 2 | __init__.py |
| `/api/nocode-builder/views` | 2 | __init__.py |
| `/api/nocode-builder/pages` | 2 | __init__.py |
| `/api/forms/list` | 1 | forms.py |
| `/api/forms/designer` | 1 | forms.py |
| `/api/mappings/available` | 1 | mappings.py |
| `/api/workflows/list` | 1 | workflows.py |
| `/api/workflows/designer` | 1 | workflows.py |
| `/api/workflows/nodes` | 1 | workflows.py |
| `/api/nocode-builder/db-info` | 1 | __init__.py |
| `/api/nocode-builder/backgrounds` | 1 | __init__.py |

### B 級中「選單候選多於一個」的（2 支，多頁共用，掛了會誤擋）

| 端點 | 選單候選 |
|---|---|
| `/api/form-workflow/categories` | form_workflow.categories;form_workflow.center;form_workflow.templates;form_workflow.workflows |
| `/api/form-workflow/categories/<secure_code>` | form_workflow.categories;form_workflow.center;form_workflow.templates;form_workflow.workflows |

### C 級明細（45 支）

| 端點 | permission code | 選單候選 |
|---|---|---|
| `/api/form-workflow/ai-usage/config` | `module_access_required('form_workflow') + require_permission('form_workflow.admin')` | form_workflow.ai_usage |
| `/api/form-workflow/ai-usage/config` | `module_access_required('form_workflow') + require_permission('form_workflow.admin')` | form_workflow.ai_usage |
| `/api/form-workflow/ai-usage/records` | `module_access_required('form_workflow') + require_permission('form_workflow.admin')` | form_workflow.ai_usage |
| `/api/form-workflow/ai-usage/summary` | `module_access_required('form_workflow') + require_permission('form_workflow.admin')` | form_workflow.ai_usage |
| `/api/form-workflow/instances` | `module_access_required('form_workflow') + require_permission('form_workflow.form.view')` | — |
| `/api/form-workflow/instances/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.form.view')` | — |
| `/api/form-workflow/pending-tasks` | `module_access_required('form_workflow') + require_permission('form_workflow.form.approve')` | — |
| `/api/form-workflow/pending-tasks/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.form.approve')` | — |
| `/api/form-workflow/pending-tasks/<secure_code>/approve` | `module_access_required('form_workflow') + require_permission('form_workflow.form.approve')` | — |
| `/api/form-workflow/stats` | `module_access_required('form_workflow') + require_permission('form_workflow.template.view')` | — |
| `/api/form-workflow/templates` | `module_access_required('form_workflow') + require_permission('form_workflow.template.view')` | form_workflow.templates |
| `/api/form-workflow/templates` | `module_access_required('form_workflow') + require_permission('form_workflow.template.create')` | form_workflow.templates |
| `/api/form-workflow/templates/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.template.view')` | form_workflow.templates |
| `/api/form-workflow/templates/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.template.edit')` | form_workflow.templates |
| `/api/form-workflow/templates/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.template.delete')` | form_workflow.templates |
| `/api/form-workflow/templates/batch/delete` | `module_access_required('form_workflow') + require_permission('form_workflow.template.delete')` | form_workflow.templates |
| `/api/form-workflow/templates/batch/export` | `module_access_required('form_workflow') + require_permission('form_workflow.template.view')` | form_workflow.templates |
| `/api/form-workflow/templates/batch/import` | `module_access_required('form_workflow') + require_permission('form_workflow.template.create')` | form_workflow.templates |
| `/api/form-workflow/templates/batch/save-new-version` | `module_access_required('form_workflow') + require_permission('form_workflow.template.edit')` | form_workflow.templates |
| `/api/form-workflow/workflows` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.create')` | form_workflow.workflows |
| `/api/form-workflow/workflows/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.edit')` | form_workflow.workflows |
| `/api/form-workflow/workflows/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.delete')` | form_workflow.workflows |
| `/api/form-workflow/workflows/<secure_code>/flow-overview` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows/<secure_code>/unused-subflows` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows/batch/delete` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.delete')` | form_workflow.workflows |
| `/api/form-workflow/workflows/batch/export` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows/batch/import` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.create')` | form_workflow.workflows |
| `/api/form-workflow/workflows/batch/save-new-version` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.edit')` | form_workflow.workflows |
| `/api/form-workflow/workflows/flow-trees` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/form-workflow/workflows/flow-trees/<secure_code>` | `module_access_required('form_workflow') + require_permission('form_workflow.workflow.view')` | form_workflow.workflows |
| `/api/nocode-builder/sub-systems/<secure_code>/tables` | `module_access_required('nocode_builder') + permission_required('nocode_builder.manage')` | — |
| `/api/open_defense/admin/decisions/<secure_code>/revoke` | `permission_required('open_defense.decision.write')` | — |
| `/api/vuln-lifecycle/assets` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.asset.view')` | — |
| `/api/vuln-lifecycle/assets/<int:asset_id>/findings` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.finding.view')` | — |
| `/api/vuln-lifecycle/dashboard/summary` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.dashboard.view')` | — |
| `/api/vuln-lifecycle/health` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.dashboard.view')` | — |
| `/api/vuln-lifecycle/kynd/findings` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.kynd.view')` | — |
| `/api/vuln-lifecycle/kynd/risk/adjust` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.risk.adjust')` | — |
| `/api/vuln-lifecycle/kynd/risk/adjustments` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.risk.view')` | — |
| `/api/vuln-lifecycle/kynd/sessions` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.kynd.view')` | — |
| `/api/vuln-lifecycle/kynd/summary` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.kynd.view')` | — |
| `/api/vuln-lifecycle/risk/adjust` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.risk.adjust')` | — |
| `/api/vuln-lifecycle/risk/adjustments` | `module_access_required('vuln_lifecycle') + require_permission('vuln_lifecycle.risk.view')` | — |