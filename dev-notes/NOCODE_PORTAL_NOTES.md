# NoCode Builder / Portal 開發備忘

> 2026-08-30 從 `CLAUDE.md` 移出（原「備忘」章的三個小節，共 317 行）。
> 移出理由：這批內容只有在動 NoCode Builder 或 portal 時才用得到，
> 但它在 CLAUDE.md 裡是每個 session 都要載入的固定成本。
>
> **動 `modules/nocode_builder/`、`/public/portal/` 或 Page IR 之前，整份讀完。**
> 相關規格：`PORTAL_ACCOUNT_SPEC.md`（權限模型與判定鏈）、
> `handoff_nocode_n1_n5.md`（完整交接與踩坑清單）、
> `PAGE_IR_SPEC.md` / `PAGE_IR_LAYOUT_ENGINES.md`（IR schema 與版面引擎）、
> `SHARED_COMPONENTS_SPEC.md`（共用元件）、`PAGE_TEMPLATE_SPEC.md`（樣板庫）、
> `codex_spec/portal.md`（派工片段與 API 實測陷阱）、
> `NOCODE_MENU_HIDE.md`（選單隱藏機制與 2026-09-13 解除隱藏的過程記錄）。

---

## NoCode Builder / Portal 開發備忘（2026-07-28 起）

**環境事實：開發機上目前有一個可用的 NoCode 子系統**，由
`scripts/examples/provision_relief_donation_demo.py --force` 建置：

| 項目 | 值 |
|---|---|
| 子系統（published） | `HJGEoAh6PBv5IXNHhMTu5P`（急難救助物資捐贈） |
| portal_path_id | `HdjFFvF-` |
| welcome 頁（2026-08-04 起已 published，內含雙 menu 示範） | `QlqVasK5fsLFMfUpPEvvFz` |
| 我的捐贈登記（要 `donation.manage`） | `Gqm4tuQEsBgituXVaDrCrr` |
| 物資公佈欄（要 `bulletin.read`） | `Ogi303_5kwPZdEE2IildYG` |

另有一個 `DzSQ8oTRKCnMVbuxS-431u`（`Ethan的test`，draft，用戶自建，**不要動**）。
重建腳本會**產生全新識別碼**，跑過就要回頭更新本表。

**portal 測試帳號**（username 是完整 e-mail，密碼一律 `relief123456`）：

| username | 階級 | 管理角色 |
|---|---|---|
| `guest_demo@example.com` | GUEST (0) | — |
| `member_demo@example.com` | MEMBER (10) | — |
| `staff_demo@example.com` | STAFF (50) | — |
| `admin_demo@example.com` | ADMIN (90) | SYSTEM_ADMIN |
| `bulletin_mgr@example.com` | MEMBER (10) | BULLETIN_MANAGER |
| `auditor_demo@example.com` | MEMBER (10) | AUDITOR |
| `donor_a_pf13@example.com` / `donor_b_pf13@example.com` | MEMBER (10) | — |

`bulletin_mgr` / `auditor` 的管理角色刻意留在 MEMBER 階級，
才驗得出「管理角色是聯集、不隨階級繼承」；`donor_a` / `donor_b` **有捐贈資料**，
可驗列級隔離（兩人互相看不到對方）。

**識別碼被重建後怎麼重查**（provision 只印子系統 sc 與 path_id）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c "
SELECT s.secure_code, s.name, s.status, n.secure_code AS node_sc, n.name, n.node_type,
       n.parent_secure_code, n.page_layout_secure_code
FROM dc_sub_systems s LEFT JOIN dc_site_map_nodes n
  ON n.sub_system_secure_code = s.secure_code AND n.is_deleted = false
WHERE s.is_deleted = false ORDER BY s.created_at DESC, n.display_order;"
# portal_path_id
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c \
  "SELECT code, value_str FROM lookup_items WHERE value_str LIKE '%' ORDER BY id DESC LIMIT 20;"
# portal 帳號
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/<SS>/portal.db \
  "SELECT username, group_code, level_code, is_active FROM portal_users;"
```

**portal 帳號快速切換（開發工具，2026-08-03 起）**：
`/dev/portal-quick-login` 選子系統 + 帳號即免密碼切換，
之後走**正式**公開路由，列級擁有權／管理角色／個人覆寫全部真實生效
——這是 IR 設計器「預覽階級」做不到的（那是合成身分，`user_id=None`、`roles=[]`，
只驗得了階級/群組層的准入）。curl 版：

```bash
BASE=http://192.168.0.16:7000/beakplatform; SS=HJGEoAh6PBv5IXNHhMTu5P
USC=$(curl -s "$BASE/dev/portal-quick-login/users/$SS" | python3 -c \
  "import sys,json;d=json.load(sys.stdin);print([x['secure_code'] for x in d['data'] if x['username']=='member_demo@example.com'][0])")
curl -s -c q.txt -b q.txt -X POST "$BASE/dev/portal-quick-login" \
  -H 'Content-Type: application/json' \
  -d "{\"sub_system_sc\":\"$SS\",\"user_secure_code\":\"$USC\"}"
curl -s -b q.txt -o /dev/null -w '%{http_code}\n' "$BASE/public/portal/HdjFFvF-/p/$PAGE_SC"
```

**免密碼登入的邏輯一律留在 `backend/app/web/dev.py`**（該檔在 `push_github.sh`
排除清單、正式部署整個移除）。`portal_auth_service` 只提供
`build_session_data()` / `store_session()` 兩個**不含身分驗證語意**的介面。
**禁止**在正式服務層新增任何可免密碼登入的函式——那會被推上公開 repo，
等於在正式程式碼裡預留後門。

**架構原則（2026-08-03 用戶定案，違反者不是 bug 是架構錯誤）**：

- NoCode 子系統的資料**自給自足**。要與平台交換一律是**平台寫入、平台去讀**，
  不從 SQLite / NoCode 側取用平台資料（流程元件取資料算平台本身的功能，不在此限）。
  目的有二：把 NoCode 側的 SQL injection 受害範圍鎖在 SQLite 內攻不進平台；
  以及保持 **NoCode 本來就能獨立成單一專案**的可分離性（整合進 BeakPlatform 是產品策略）
- 因此 `registry.get_resource()` 在 portal 語境對無 prefix 的平台資源一律回 None
  （`backend/app/pageir/registry.py:46-47`）**是這條原則的實作，不要放寬**。
  症狀會是 `PageIrRenderError: Unregistered resource: user` → 422，
  正解是把頁面改綁 `portal:` / `formflow:` 資源，不是去改 registry
- **所有 nocode 子系統頁面一律以 portal 方式渲染**（員工也一樣，只是身分來源不同），
  平台端不存在「nocode 頁面」。故 `_ACTIONS`（平台側動作白名單）永遠是 0 筆，
  那是預期狀態不是待補項

**兩個帳號世界完全分離**，測試時 cookie jar 要分開（同一個 jar 也能並存，但別混淆）：

| | 平台世界 | Portal 世界 |
|---|---|---|
| 入口 | `/nocode/workspace/<sub_system_sc>`（統一工作區） | `/public/portal/<path_id>/...` |
| 帳號 | PostgreSQL `users` | 子系統 SQLite `portal.db` 的 `portal_users` |
| session | Flask-Login | `session['portal_sessions'][sub_sc]`（per 子系統並存） |
| 渲染語境 | `platform` | `portal`（互斥，跨界解析一律 fail-closed） |

```bash
# portal 帳號登入（表單 POST，非 JSON；用獨立 cookie jar）
curl -s -c p4_cj.txt -X POST "$BASE/public/portal/<path_id>/login" \
  -d 'username=<帳號>&password=<密碼>'

# portal 頁的 CSRF token 在頁面 meta（平台的 /dashboard 取不到 portal 用的）
TOKEN=$(curl -s -b p4_cj.txt "$BASE/public/portal/<path_id>/p/<page_sc>" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)

# 子系統 SQLite 直查（portal.db=帳號/群組/階級，portal_data.db=業務資料）
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/<sub_system_sc>/portal.db \
  "SELECT username, group_code, level_code FROM portal_users;"
```

- `path_id` 不等於 `sub_system_sc`，對照在 `lookup_items.value_str`：
  `SELECT code, value_str FROM lookup_items WHERE value_str='<sub_system_sc>';`
- **Page IR 設計器網址是 `/nocode/ir-designer/<page_layout_secure_code>`**
  （預覽是同路徑 `+ /preview`）。它吃的是**頁面** secure_code，不是子系統 sc，
  路由定義在 `modules/nocode_builder/web/__init__.py:42`
- **設計器模板已於 2026-08-04 拆分**（`_ir_designer_body.html` 只剩 4.5KB 外殼，
  舊文件與舊卡片都還指著它，照著找會找不到東西）：

  ```
  ir_designer.html
  └── _ir_designer_body.html          外殼 + 頂部工具列（預覽身分區塊）
      ├── _ir_designer_issue_modal.html
      ├── _ir_designer_save_template.html
      ├── _ir_designer_layout.html     版面編輯區
      └── _ir_designer_props.html      全部 widget 屬性面板（42KB，改屬性面板來這裡）
          ├── (import) _ir_designer_access_matrix.html   元件准入 macro render()
          └── (include) _ir_designer_menu.html           menu widget 面板
  ```

  元件准入是 `access_matrix.render(actions_expr, write_hint)` macro，
  在 props 內被呼叫四次（一般 widget／master_detail／actions／form），
  **改准入 UI 只要改 macro 一處**，不要在四個地方各改一份
- **`_ir_designer_body.html` 有兩個宿主頁，`<script>` 清單各自維護**
  （2026-08-06 踩到，commit `86a75b75`）：

  | 宿主 | 網址 | 特徵 |
  |---|---|---|
  | `ir_designer.html` | `/nocode/ir-designer/<頁sc>` | 單頁設計器，**沒有 Site Map** |
  | `workspace.html` | `/nocode/workspace/<子系統sc>` | 工作區「頁面設計」分頁，**內嵌整套設計器** |

  兩邊共用同一份 partial 與同一個 Alpine 元件 `irDesigner()`，
  但 `{% block scripts %}` 是各寫各的。**新增設計器要用的 JS 時兩邊都要加**——
  PF-29 加當時的 `shared-menu.js` 時只加了 `ir_designer.html`，
  導致工作區內該檔掛的全域恆 `undefined`，
  按[另存為共用選單]噴 `Cannot read properties of undefined (reading 'create')`。
  （該檔 2026-08-06 已更名 `shared-component.js`、全域改為 `BkSharedComponent`。）
  **日常用的是工作區那邊，冷門的單頁設計器反而是好的**，所以測試時要測工作區。
  現行依賴：`window.BkCaps`（base.html 的 capability.js）／`BkPageTemplate`
  （`page-template.js`）／`BkSharedComponent`（`shared-component.js`）
- **portal 頁是獨立模板 `portal_page_v3.html`，不繼承 `layouts/base.html`**。
  平台頁自動有的東西（`timezone.js`／`BkTime`、i18n、capability.js）在這裡
  **都要自己載入**。portal 又是公開路由，`auth_interceptor` 在設定
  `g.locale` / `g.timezone` 之前就 return 了，所以時區一律吃 fallback `Asia/Taipei`
- **這條對 portal 的錯誤頁與任何新增 portal 模板一律適用**，不只主頁。
  錯誤路徑最容易漏：`pageir/page_error.html` 繼承了 `layouts/base.html`，
  被 portal 端共用了很久，導致 portal 渲染失敗時**外部訪客拿到帶平台
  navbar／選單／`capability.js` 的頁面**（2026-08-03 commit `853b5aaf` 修，
  改用 `modules/nocode_builder/portal_page_error.html`）。
  **新增任何 portal 端要用的模板前，先確認它沒有 `{% extends "layouts/base.html" %}`。**
  平台世界的 `/p/` 與純平台預覽仍用原本的平台版錯誤頁，那是正確的
- **在 Page IR 頁面放 form.io 送出按鈕時必須寫 `"input": false`**，
  否則 payload 會多一個 `submit: true` 欄位，被後端欄位白名單擋成
  400 `unknown_field`
- **portal.db schema 現行版本 v4**。v3（PF-7，2026-08-03 起）新增六張權限碼制表
  `portal_permissions` / `portal_admin_roles` / `portal_role_permissions` /
  `portal_user_roles` / `portal_user_permissions` / `portal_level_permissions`；
  v4（PF-44 階段 A，2026-08-05 起）新增 `portal_files` / `portal_file_acl`
  （portal 檔案元件的歸屬與個別檔案 ACL，實體與加密仍在平台 `platform_files`）。
  升級由 `ensure_portal_schema()` 階梯式自動執行（0→2→3→4，冪等，**lazy**
  ——子系統被存取到才升，所以看到某個子系統還是舊版本不代表壞掉），
  **改 portal.db schema 一律加在該函式，不要另寫 migration 腳本**。
- **Page IR widget 的設定值一律直接掛在 widget 物件上**
  （`{"type": "file_box", "upload_by": "designer", ...}`），**沒有 `settings` 子物件**。
  這條對所有 widget 皆然，但 `file_box` 上已經有人猜錯過一次——
  讀成 `widget["settings"]` 時每個欄位都回退預設值，症狀是**設定看起來存了、
  行為卻永遠是預設值**（設計者上傳被判成 `upload_by=portal_user` 而全數 400）。
  有效權限計算的唯一實作是 `services/portal_permission_service.py`
  （階級 rank 向下繼承、管理角色聯集不繼承、個人 deny 最優先、停用帳號回空集合、
  匿名只吃階級權限），**禁止各處自行組 SQL 算權限**。
  access_matrix 規則**只認**權限碼制 `{"required_permissions": [...], "match_mode": "any"|"all"}`
  （PF-13，2026-08-03 起）。舊的 `{groups, min_level}` 形式已完全移除，寫入會被 400 擋下，
  runtime 判定回 `bad_matrix`（`group_denied` / `level_missing` / `level_denied` 三個 reason
  已不存在）。`portal_groups` / `portal_levels` 兩張表**仍在**——階級 rank 是
  `portal_level_permissions` 的權限來源，群組則降為單純的帳號屬性、不再參與准入判定。
  寫入端驗證有兩處，改格式要同時改：`api/site_map_api.py::_validate_access_matrix`
  與 `backend/app/pageir/schema_v3.json` 的 `$defs.portal_access_rule`。
  權限碼格式固定 `resource.action`（小寫 snake_case），與平台的 permission code 不共用。
  管理面（PF-8a/8b）在 `services/portal_permission_admin_service.py` +
  `api/portal_permission_api.py`（前綴 `/api/nocode-builder/sub-systems/<ss>/portal/...`）與
  工作區第四個分頁「權限矩陣」（`_workspace_perms.html` + `workspace-perms.js`）。
  角色／階級權限與帳號角色一律**整組覆寫**（PUT 全量 codes），不是增量。
  建立子系統會自動 seed 六個 `is_system` 管理角色；既有子系統在首次讀 permission-model 時補 seed。
  權限碼被角色／階級／個人覆寫／site map access_matrix 引用時**拒絕刪除（409）**。
- **Page IR v3 menu widget**：完整欄位規格見 `dev-notes/PAGE_IR_SPEC.md` §3.7
  （自動模式在 `dev-notes/SHARED_COMPONENTS_SPEC.md` §5）。三件最容易靜默失效的：
  - **items 是完全自訂的樹**，不跟著 site map 的結構與順序走（早期版本相反）。
    名稱與圖示仍即時取自 site map；節點被刪或停用時該項連同 children 整枝消失
  - **底圖存 `platform_files.secure_code`，不是 `DcBackground.secure_code`**
    （用 `/api/nocode-builder/backgrounds` 回應的 `platform_file_sc`）——
    存錯的症狀是「選了底圖完全沒反應、也不報錯」
  - 顏色一律 `^#[0-9a-fA-F]{6}$`，schema 與 renderer `_menu_style()` **兩道都要擋**
    （值最後會進 inline style）
- **Page IR v3 有三個版面引擎**（2026-08-05 起，定版 `dev-notes/PAGE_IR_LAYOUT_ENGINES.md`）：
  `page.engine` = `flow`（預設，即原本的縱向流 + layout widget 等分）／
  `grid`（矩陣切格合併，欄寬 fr、列高 px）／`free`（12 欄 × `row_unit` 自由放置）。
  **沒有 `engine` 欄位＝flow，既有 IR 一行都不用改。**
  核心約束：**三個引擎只差外殼，zone／frame 內部一律是既有 flow widget 序列**，
  `render_widget` macro 不因引擎而異，禁止跨引擎巢狀。
  `grid`／`free` 的窄螢幕行為是**水平捲動 + `min_width`，不塌不縮放**（設計者自己決定場景）。
  `pageir.css` 那條 720px 塌一欄的規則只作用於 flow 才輸出的 `--responsive` 變體，
  **新增任何會受該規則影響的 widget 時要記得跟著輸出這個 class**
  （master_detail 的 master 區塊就漏過一次）。
  **menu widget 的 provider 要求 render context 同時有 `sub_system_sc`、`portal_user`、
  `path_id`**（連結必須指向 `/public/portal/<path_id>/...`），少任何一個一律回空陣列，
  畫面上就是「沒有可顯示的項目」。IR 設計器預覽從 menu widget 上線起就漏傳 `path_id`，
  導致**預覽的選單永遠是空的**（2026-08-05 修，`web/__init__.py::ir_designer_preview`）。
  新增任何會呼叫 `set_render_context('portal', ...)` 的路徑時，
  對照 `portal_public.py` 的參數清單，不要只傳前兩個。
  設計器在 `/nocode/ir-designer/<page_sc>`：grid 用 `grid-layout-editor.js` 的
  `layoutOnly` 模式，free 用 GridStack。**zone／frame 消失時（合併、重建矩陣、刪除框）
  裡面的元件必須有去處**（併入接手的 zone 或回未放置清單），
  否則會靜默遺失且使用者無從察覺——這個坑 grid 與 free 各踩過一次。
- **portal 業務表有列級擁有權**（2026-07-30 起）：表固定有系統欄位 `portal_user_ref`
  （值 `u:<portal user_id>` / `g:<guest_token>`），視圖 `DcCrudView.row_owner_scope`
  預設 **`own`**（只能存取自己建的列），要共享的表必須明確設 `all`。
  `portal_user_ref IS NULL` 的舊列在 own 模式下誰都看不到——
  **「portal 頁表格突然空了」第一個要查的就是這個**，不是權限判定壞了。
  既有表補欄位用 `scripts/add_portal_user_ref.py --apply`（冪等）。
  細節與 `owner_ref` 傳參規則見 `dev-notes/codex_spec/portal.md`
- **判斷一個 NoCode 頁面「還活著」必須走雙路徑 OR**，只看 site map 會誤判：
  ```
  存活 = (有存活 dc_site_map_nodes 指向 且 該節點的子系統存活)
      OR (有存活 dc_sub_system_pages 掛載 且 該子系統存活)
  ```
  portal 頁**不一定掛在 site map 節點下**，可能只透過 `dc_sub_system_pages` 關聯。
  **反向也成立**：只掛在 site map 節點、沒有 `dc_sub_system_pages` 的頁（每個子系統的
  welcome 就是），只查 `DcSubSystemPage` 一樣會誤判。`/api/nocode-builder/pages/<sc>`
  的 `sub_system_secure_code` 就犯過這個錯，害設計器的 menu 面板選不到任何節點
  （2026-08-03 commit `d61b79fb` 改走 `get_owner_sub_system_codes()` 修正）。
  **同一個坑犯過第二次**：`ir_designer_preview()` 帶 `?sub=` 時也只查
  `dc_sub_system_pages`，導致**每個子系統的 welcome 頁 portal 預覽必然 404**
  （commit `93c648fa` 修）。
  **第三次、而且是在公開路由上**：`portal_public.py` 三處掛載判定
  （`portal_page` / `portal_widget_rows` / `_resolve_portal_widget_common`）
  同樣只查 `dc_sub_system_pages`，導致**每個子系統的 welcome 頁在正式 portal 上
  必定 404**，即使已 published。現收斂成單一 `_portal_page_mounted()`：雙路徑 OR，
  有掛載記錄但全部停用一律拒絕，走 site map 節點時可見性交給 `check_page_access`。
  凡是要判斷「這頁屬不屬於這個子系統」，
  一律用 `get_owner_sub_system_codes()`，不要自己查單一張表。
  2026-07-31 清孤兒時只看 site map，就這樣誤刪了兩個 published 驗收頁，
  其中一個是 `test_e2e_portal_cancel.py` 寫死依賴的
  `FORMTEST00000000000001`，**刪掉會讓 E2E 靜默 skip 而不是報錯**（至今未恢復）。
  此判定的**唯一實作**是
  `modules/nocode_builder/services/page_ownership_service.py`
  （`is_page_reachable()` / `get_owner_sub_system_codes()`），
  存取層、刪除級聯、清理腳本共用，**禁止各自重寫**。
  注意 `is_page_reachable()` 對「零關聯」回 `True`（純平台 IR 頁要放行），
  所以判斷「該不該刪這個頁」時條件要寫成
  `not is_page_reachable(sc) or not get_owner_sub_system_codes(sc)`。
  既有孤兒用 `scripts/cleanup_orphan_nocode_pages.py --dry-run/--apply`（冪等）清。
- **建立子系統會自動附贈一個 welcome 節點 + welcome 頁面**，
  且 **site map 只允許一個根頁面**（再建根節點會回 400
  「Site Map 只能有一個根頁面 (welcome)」，新節點要指定 `parent_secure_code`）。
  測級聯或建測試資料時會撞到。
- 權限判定失敗**一律回 404**（不洩漏存在與否）；查原因看
  `sudo journalctl -u beakplatform-dev.service --since "-5 min" | grep reason=`
- 權限模型與判定鏈：`dev-notes/PORTAL_ACCOUNT_SPEC.md`；
  完整交接與踩坑清單：`dev-notes/handoff_nocode_n1_n5.md`
- v2 `layout_json` 已退役，`/p/` 遇到會回 410；設計器只認 `ir_version: 3`
- **頁面版面樣板庫（PF-24~28、PF-32）＝複製語意**，規格 `dev-notes/PAGE_TEMPLATE_SPEC.md`。
  只有三件事在動工前非知道不可：
  - **同子系統套用完全不淨化**（menu 的 `items[].node`、`shared_ref`、access_matrix
    原封不動保留）。「另存為樣板」存的是**當下那頁的完整 IR**，內建樣板的「零綁定」
    是那六筆種子資料的內容、**不是會傳染的屬性**。跨子系統才淨化，唯一實作是
    `page_template_service.sanitize_template_ir()`，**禁止各處自行清理引用**
  - `instantiate` **只建 `DcPageLayout`**，site map 節點與子系統掛載是前端
    `workspace.js::finishPageCreation()` 接手做的
  - `scope='system'` 只能由 `scripts/seed_system_page_templates.py` 建立，API 一律 403

- **子系統層級共用元件＝引用語意**（2026-08-06 起，取代 PF-29 的「共用選單」）——
  改一次，所有引用它的頁面同步生效。**定版規格 `dev-notes/SHARED_COMPONENTS_SPEC.md`
  （資料模型、API、schema、設計器 UI、menu 自動模式全在裡面，動工前整份讀完）**。
  頁面端只寫 `{"type":"menu","id":"menu-1","shared_ref":"<sc>"}`。
  留在本檔的是四條「猜不到且錯了會靜默失效」：
  - **完全共用**：引用時一律取共用元件的值，**頁面端不覆寫任何欄位**。
    同一份選單要 A 頁橫式、B 頁縱式 → 建兩個共用元件
  - **唯一例外 `access_matrix` 是交集**：共用元件與頁面 widget 兩份都要通過才渲染。
    它是授權邊界不是外觀，取其一會讓某邊設定靜默失效
  - **展開只在 `renderer._prepare_widget` 開頭一處做**（dispatch 之前，所有型別共用），
    三個渲染入口都吃得到，**不要在入口各判一次**——這專案已因「三處各自查」
    在正式 portal 上全數 404 過。resolver 驗 ctx 的 `sub_system_sc` **與
    `org_secure_code`**，所以**每個 `set_render_context('portal', ...)` 呼叫點
    都必須傳 `org_secure_code`**，漏傳的路徑上共用元件會整批消失
  - 解析不到一律 **fail-closed：整個 widget 不渲染**（不是空選單），並記 warning
  - （舊的 `dc_shared_menus` 表與 `/shared-menus` 端點已停用、程式無殘留，
    看到舊名一律視為過時）

- **grid／free 引擎下，widget 只加進 `page.widgets` 不會顯示**，
  必須同時放進某個 `canvas.zones[].widget_ids`（free 是 `frames[]`）。
  `_canvas_widgets` 對未放置者靜默略過（只記 info log），
  症狀是「存了、DB 裡也有、畫面就是沒有」。用 API 直接改 IR 時最容易踩到。

## NoCode 選單已於 2026-09-13 解除隱藏

2026-08-07 起曾用環境變數 `NOCODE_BUILDER_MENU`（不等於 `on` 即 `MODULE_INFO['menu_items']`
為空）將「子系統開發模組」選單藏起，避免出現在鐵人賽期間的手冊截圖裡；機制原理與解除
過程見 `dev-notes/NOCODE_MENU_HIDE.md`。

**鐵人賽期間（至 2026-10）不修改 `modules/nocode_builder/` 程式碼**——已知的 P1/P2
資安缺口見 BBN 待辦 **PF-271** 與 `dev-notes/NOCODE_UNHIDE_SECURITY_AUDIT_20260913.md`，
賽後才處置，看到不要當新發現回報。使用者面已用公告告知模組尚未完工、正在評估是否
移出本專案、請勿使用或存放真實資料（擬稿見 `dev-notes/NOCODE_UNHIDE_NOTICE_20260913.md`）。

## 用 API 操作 NoCode 子系統

前綴是 `/api/nocode-builder`（不是 `/api/nocode`）。**11 條實測陷阱
（CSRF 未豁免、發布狀態、回應 key、保留欄名、聚合能力缺口等）在
`dev-notes/codex_spec/portal.md` 尾段「以 API 操作子系統時的實測陷阱」**，
動手前整段讀完可省一輪除錯。
可執行範例：`scripts/examples/provision_relief_donation_demo.py`（建置）
與 `verify_relief_donation_demo.py`（端對端驗收）。
