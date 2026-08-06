# BeakPlatform - Claude Code 專案規範

## 這份文件的範圍（2026-07-29 重整）

本檔只放**「不知道就會做錯」的規範與環境事實**。細節與可重複使用的內容已分流：

| 找什麼 | 去哪 |
|---|---|
| 派工給 codex 時要貼的規範片段 | **`docs/codex_spec/`**（frontend / i18n / security / portal / _footer） |
| 檔案上傳下載的完整 API 用法 | `docs/FILE_SERVICE.md` |
| 改哪些檔案（工單導向） | `docs/manifests/README.yaml` → 對應 manifest |
| 安全踩坑清單 | `docs/manifests/SECURITY_PITFALLS.md` |
| 權限模型定版 | `docs/PERMISSION_MODEL.md`、`docs/COMPONENT_VISIBILITY_GUIDE.md` |
| 名詞對照 | `docs/GLOSSARY.md` |
| 跨 session 待辦與決策脈絡 | BeakBroodNest 知識庫（`note_search` / `note_get`） |

**維護原則**：新的踩坑先問「這是 codex 猜不到的專案特有事實，還是通用工程常識？」
前者才寫進來；屬於「派工時要貼給 codex」的，寫進 `docs/codex_spec/` 並在本檔留指針。

## 開發模式（Codex-first，2026-08-05 定版）

**本專案的標準開發迴路：主 Claude 寫 spec → `codex exec` 實作 → 主 Claude 驗收。**
呼叫規範（sandbox 參數、timeout、stdin 餵 prompt）見
`~/.claude/knowledge_base/standards/coding_standards/codex_first_policy.md`。

### 組 spec 的固定步驟

1. **檔案清單**：讀 `docs/manifests/README.yaml` → 對應 manifest，spec 中列出精確檔案
   路徑與現有結構說明（codex 對專案無記憶，context 要餵足）
2. **規範片段**：依觸及範圍貼 `docs/codex_spec/` 對應檔（frontend / i18n / security /
   portal），**`_footer.md` 每次必貼**。codex 不讀 CLAUDE.md——沒貼進 prompt 的規範
   一律視同不存在
3. **本檔的專案特有事實**（nginx 前綴、CSS 變數白名單、TZ-01、FILE-01 等）凡與任務
   相關，逐條複製進 spec，不能只給檔案路徑

### 驗收（主 Claude 專屬職責，不可外包）

- **VERIFY-03**：codex 開不了瀏覽器，它的自我檢查表不算驗收。互動元素一律由主 Claude
  用 chrome-devtools 實際點過（VERIFY-01），輸出落地 `/opt/tmp/verify/`（VERIFY-02）
- **反向檢查先於功能測試**：每個抽象層搜尋「繞過它的直接寫法」（全域 CLAUDE.md
  Agent 協作規範）
- codex 常見瑕疵必查：死碼、拆字串規避檢查、manifest 只刪不補、裸中文未包 gettext、
  沒重啟服務就宣稱驗證通過
- 退回上限 2 次，之後改由 Claude 依既有規範直接實作

### Claude 直接動手的例外

約 10 行內微改、codex 連續失敗 2 次、配額耗盡/限流、緊急修復、純文件/設定變更。

## 專案定位

**BeakPlatform 是一個多租戶權限管理平台**

這是一個**純平台**，核心功能：
- 安全控制（認證、授權、攔截）
- 多租戶隔離（企業資料隔離、RLS）
- RBAC 權限系統
- 動態選單系統
- 組織架構管理（部門、群組、角色）
- 人資架構管理（職等、職系、職稱）

**業務功能透過「模組」掛載，不在平台內實作。**

---

## 溝通對照表

用戶提到系統功能時，參照 `docs/GLOSSARY.md` 快速定位。

用戶溝通慣例：
- `/path/` — URL 路徑（如 `/menu/` = `http://192.168.0.16:7000/beakplatform/menu/`，**app 掛在 nginx 的 `/beakplatform` 前綴下，缺前綴會 404**）
- `'名詞'` — 功能名稱或字串，多名詞時混用 `""` 區別
- `[按鈕]` — UI 按鈕或超連結元素
- `(URL)` — 從瀏覽器複製的完整 URL

---

## 每次對話必做

### 1. Git Commit (對話結束)
**每次對話結束前**：

```bash
cd /opt/BeakPlatform-dev
git add -A
git commit -m "類型: 簡短摘要

- 完成項目 1
- 完成項目 2

Generated with Claude Code"
```

**注意：commit 和 push 是兩件事。只 commit，不主動 push。用戶說 push 才 push。**

**GitHub 推送必須使用過濾腳本：**
- **push** → `git push origin main` (Forgejo，直接推)
- **push github** → `bash scripts/push_github.sh` (GitHub，過濾推送)
- **push both** → 先 `git push origin main`，再 `bash scripts/push_github.sh`
- **禁止** 直接執行 `git push github main`，會把 CLAUDE.md 等內部檔案推上去
- 過濾腳本要求工作區乾淨，有未 commit 的變更時先 `git stash --include-untracked`，推完再 `git stash pop`
- GitHub 的 history 與 origin 不同步是正常的（過濾 commit），不要 merge github/main 回 local

### 2. 更新追蹤
- 完成 BBN 待辦（PF-xx）時，回寫該原子標註完成狀態
- 如果涉及架構變更，更新相關文件

---

## Manifest 導向開發流程（強制）

**所有程式修改必須先查 manifest，禁止盲目探索。**
（Codex-first 模式下，manifest 同時是「組 codex spec 檔案清單」的唯一來源。）

### 流程

1. **收到工單** → 讀 `docs/manifests/README.yaml` 找到目標 manifest
2. **讀 manifest** → 取得精確的檔案清單（route、api、service、model、template、js）
3. **只讀 manifest 列出的檔案** → 定位問題後把檔案清單與結構說明寫進 codex spec
   （Claude 直接動手的例外情況則自行修正）
4. **如果不夠** → 向用戶說明需要查看哪些額外檔案及原因，等確認後再讀

### 禁止

- **禁止** 收到 URL 後自行 grep/glob 搜尋相關程式（manifest 已列出）
- **禁止** 在 manifest 範圍外自行讀取檔案（除非向用戶說明並獲同意）
- **禁止** 修改 `security-core.yaml` 列出的安全核心檔案（除非用戶明確要求）

### 安全防雷

修改程式前必須查閱 `docs/manifests/SECURITY_PITFALLS.md`，確認不踩以下坑：
- 租戶隔離（org_secure_code 過濾）
- 帳號狀態過濾（is_deleted + is_active）
- ResourceGateway 使用（API 層禁止 Model.query）
- 雙鑰匙選單安全（MenuPermission + MenuRoleRequirement）
- 時區處理（TZ-01 規範）

### 工單格式

用戶會以此格式提交工單：
```
目標頁面: /users/
問題類型: bug | 功能調整 | 新增欄位 | UI 修正
症狀: （問題描述）
影響範圍: list / create / edit / view
已知線索: （選填）
```

完整工單模板見 `docs/manifests/TICKET_TEMPLATE.md`。

---

## 當前開發階段

平台基礎建設與模組化標準已完成。目前處於**功能完善階段**。

待辦事項以 **BBN 待辦為主**（ref_code `PF-xx`，`project_tasks` 查詢、
`note_search("PF-xx")` 取全文）。Forgejo Issues 已全數移回 BBN，若見殘留直接忽略，
不需搬移或關閉（用戶會自行在 BBN 新增）。
架構與模組化標準詳見 `docs/PLATFORM_MODULARIZATION_PLAN.md`。

---

## 安全標準 (必須遵守)

### AUTH-01: 全域認證攔截
- 所有請求經過 `before_request` 認證檢查
- 未登入訪問非白名單路由 → 401

### AUTH-02: 統一認證 Decorator
```python
@public_route          # 公開路由
@login_required        # 需要登入
@admin_required        # 需要企業管理員
@system_admin_required # 需要系統管理員
```

### PERM-01: 權限模型（4+1）
- 四層 user_type 硬界線（角色永不跨層）+ NoCode 公開資料隔離區
- 選單/頁面 = 雙鑰匙（Key1 user_type 層界 + Key2 角色，僅 EMPLOYEE/EXTERNAL 吃 Key2）；欄位 = EGRESS-01
- `menu_items.required_permission` 已退役不再影響選單；permission code 僅存在 API/資源層
- 定版文件：`docs/PERMISSION_MODEL.md`（bypass 規則、功能開放多層 SOP、已知備忘）
- 權限管理 UI 統一入口：`/access/` 權限管理中心（功能授權/角色/帳號配角色/健檢；
  舊 `/permissions/`、`/roles/`、`/admin/account-roles/` 已退役，`/menu/` 只管選單結構）；
  規格 `docs/ACCESS_CENTER_SPEC.md`
- Phase B 起頁面路由**不掛身分 decorator**：url 型選單路徑前綴即 PageRoleGuard 領地；
  單頁專屬資料 API 掛 `@page_keys_required('<menu_code>')`
- Phase D 元件級：動作按鈕一律包 `{% if can('<permission_code>') %}`（JS 用 `BkCaps.can()`），
  對應動作 API 掛 `@permission_required('<permission_code>')`（capability_service）；
  指引 `docs/COMPONENT_VISIBILITY_GUIDE.md`（四層防線總表 + NoCode_Builder 消費規則）

### PERM-02: D2 元件級推廣檢查（強制，2026-07-18 起）

**任何開發或修改工單，凡觸及「頁面模板、動作按鈕（增刪改查/簽核/撤銷等）、動作型 API」，
動工前必須先問用戶：「本次是否依 D2 標準進行？」**，取得答覆後才能實作。

- D2 標準 = 按鈕包 `can()`、動作 API 掛 `@permission_required`、code 沿用 API 層既有
  permission code（詳見 `docs/COMPONENT_VISIBILITY_GUIDE.md` §2.5）
- 用戶答「是」→ 該工單範圍內的按鈕與 API 一併完成 D2 改造；答「否」→ 照原樣修改，不擅自加
- 純資料修正、CSS、i18n、文件等不觸及按鈕/動作 API 的工單不必問
- 全新頁面**不必問，一律直接套 D2 標準**（新程式碼沒有理由用舊模式）

### TENANT-01: 強制企業隔離
- 所有查詢包含 `org_secure_code` 過濾
- PostgreSQL RLS 作為最後防線

### TENANT-02: ResourceGateway 要求
- API 層禁止直接使用 `Model.query`
- 必須透過 `ResourceGateway` 存取

### DATA-01: 帳號查詢必須過濾刪除與停用
- **所有查詢用戶/帳號的地方**，必須同時過濾 `is_deleted=False` 和 `is_active=True`
- 包含但不限於：用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析
- 關聯查詢（如透過角色/部門取用戶）需 JOIN User 表確認帳號狀態

### EGRESS-01: 資料出口政策

設有出口政策的資源，欄位依 (角色, 語境) 呈現 clear / masked / hidden。
規格：`docs/EGRESS_POLICY_SPEC.md`，防雷：`docs/manifests/SECURITY_PITFALLS.md` 第 9 節。

- API 序列化：to_dict 之後過 `egress_service.apply(resource, context, items)`
- 後端模板：`egress_value()` / `egress_visibility()` template globals + `BkEgress.bind()`
- **禁止** list 回應內嵌預載 detail 資料（master-detail 必須分開請求）
- **禁止** 繞過 `POST /api/egress/reveal` 另開端點回傳 masked 欄位真值

### MENU-01: 選單項目新增規範

**新增 menu_items 記錄時，必須遵守以下規則：**

**link_type 有效值**（`_resolve_link()` in `menu_service.py` 只認以下值）：

| link_type | link_target 格式 | 說明 |
|-----------|-----------------|------|
| `url` | `/security/alert-broadcasts/` | 直接 URL 路徑（最常用） |
| `route` | `admin.settings` 或 `/path/` | Flask endpoint 名稱，或以 `/` 開頭的路徑 |
| `page` | `page_secure_code` | 動態頁面，自動加 `/p/` 前綴 |
| `divider` | （空） | 分隔線 |
| `header` | （空） | 群組標題 |

**其他 link_type 值（如 `path`）會導致 href 變成 `#`，選單點了沒反應。**

**參考既有同類選單**：新增前先查 DB 中同層級或同功能的選單用什麼 link_type，照著用。
```sql
SELECT code, link_type, link_target FROM menu_items WHERE parent_secure_code = '目標父選單SC';
```

**禁止事項**：
- **禁止** 為了「選單無法點擊」而修改 `menu_service.py` 的 `_resolve_link()` -- 問題一定出在 DB 的 link_type 設定
- **禁止** 為了選單顯示問題而修改權限控制邏輯（`auth_interceptor`、`page_permission_service`、`page_role_guard`）-- 這些是安全核心，選單顯示異常的根因是 DB 資料設定錯誤

### FILE-01: 檔案上傳/下載統一規範

**所有檔案操作必須透過 `file_service`，禁止自行實作上傳/下載邏輯。**

- 加密由 `storage_type` 自動決定（`form_attachment` / `subsystem_file` 走 AES-256-GCM），
  程式不需手動呼叫加密函式
- 前端一律用 `BkFileAttachment` 元件，不要自己寫上傳 API 呼叫
- **禁止**繞過 `file_service` 直接讀寫 uploads/ 或 encrypted_storage/
- **禁止**手動呼叫 `crypto/engine.py`
- **禁止**將 `ENCRYPTION_MASTER_KEY` 硬編碼或寫入版控

完整 API 用法、context_type 對應表、金鑰架構：**`docs/FILE_SERVICE.md`**

**回送檔案內容時 `Content-Type` 一律用 `file_service.get_serve_mime(record)`**
（副檔名 → MIME 白名單），**禁止使用 `platform_files.mime_type`**——
該欄位存的是上傳時 multipart 宣告的值，**完全由上傳者控制**。
2026-08-05 因此修掉一個儲存型 XSS：傳 `.png` 卻宣告 `Content-Type: text/html`
（或直接傳 `.svg`），serve 端原樣回送，JS 就在平台同源執行。
`nosniff` 擋不住（型別是攻擊者明確宣告的，nosniff 反而確保照他說的渲染），
全域 CSP 的 `unsafe-inline` 也擋不住。修補配套三件，缺一不可：

```python
mimetype=file_service.get_serve_mime(record)          # 白名單推導
g._bk_strict_file_csp = True                          # → default-src 'none'; sandbox
if ext in file_service.FORCE_DOWNLOAD_EXT:            # 目前是 {'svg'}
    headers['Content-Disposition'] = _make_cd_header(record.original_name)
```

`<img src>` 不理會 `Content-Disposition`，所以 SVG 加 attachment **不會**弄壞
logo／背景（已實測）。詳見知識庫 #5048。

**通用上傳端點只收兩種 context_type**（PF-43，2026-08-05 起）：
`/api/files/upload` 只接受 `file_service.GENERIC_UPLOAD_CONTEXT_TYPES`
＝ `{'form_attachment', 'subsystem_file'}`，其餘一律 400。
在此之前它只有 `@login_required`、不檢查 context_type 與身分的關係，
任何登入帳號（含 EXTERNAL）都能寫入 `org_logo` / `nc_background` /
`wf_background` 這三個 `PUBLIC_CONTEXT_TYPES`（匿名可讀、**無租戶隔離**）。
**新增 context_type 時要一併決定它走哪個端點**——通用端點只放通用附件，
其餘各自建專屬端點並自行授權（`org_logo`→`/api/enterprise-settings/logo`、
`nc_background`→`/api/nocode-builder/backgrounds/upload`、
`wf_background`→`/api/form-workflow/backgrounds/upload`、
`portal_file`→`/api/nocode-builder/sub-systems/<ss>/portal-files`）。
未知 context_type 一律拒絕不只是授權問題：`CONTEXT_ALLOWED_EXT.get()` 對未知鍵回
`None`，副檔名白名單會**整個被跳過**。

**PF-43 的另一半尚未做**：讀取端 `/api/files/<sc>/serve` 仍是無語境的全域路徑，
`PUBLIC_CONTEXT_TYPES` 的檔案在任何子系統路徑下都取得到。

### NET-01: 來源 IP 一律走 `get_client_ip()`（2026-08-05 起）

**禁止直接讀 `request.remote_addr`、`X-Forwarded-For`、`CF-Connecting-IP`，
也禁止用 flask_limiter 的 `get_remote_address`。**
唯一實作是 `backend/app/security/client_ip.py`：

```python
from app.security.client_ip import get_client_ip    # 一般用途，可能回 None
from app.security.client_ip import client_ip_key    # 限流 key_func 用，保證回字串
```

平台有兩條互斥的信任鏈（**這是環境事實，猜不到**）：

```
LAN 直連    訪客 → nginx 192.168.0.16:7000 → Flask
Cloudflare  訪客 → CF edge → cloudflared(.16) → nginx 192.168.0.20:8080
                  → nginx 192.168.0.16:7000 → Flask
```

`create_app()` 掛的 `ProxyFix(x_for=1)` 取 XFF 最右一筆＝「直連我方 nginx 的對象」：
LAN 路徑得到真實訪客 IP，**Cloudflare 路徑恆為 `192.168.0.20`**，真實訪客 IP
只存在於 `CF-Connecting-IP`。因此信任邊界看直連對象：`remote_addr` 落在
`TRUSTED_PROXY_IPS`（config.py，預設 `192.168.0.20`，env 可覆寫）時才採信該 header，
否則一律用 `remote_addr` —— 直連者自帶 header 偽造不了。

**為什麼這條非寫不可**：此前全專案缺 ProxyFix，`remote_addr` 恆為 `127.0.0.1`，
造成三個機制**靜默失效且不報錯**：`dev.internal_network_only` 內網判定恆真、
未認證限流全站共用單一 bucket、`api_key_service.check_source_ip()` 的來源 IP
限制形同虛設。改用 `remote_addr` 而不處理 CF 分支則會走向另一個極端：
所有外網訪客塌縮成 `192.168.0.20` 一個身分。

**回傳 None 的處理**：`get_client_ip()` 在無 request 語境會回 `None`，
呼叫點若假設是字串（字串格式化、DB 非空欄位、比對）必須自己給 fallback；
限流 key_func 一律用 `client_ip_key()`（保證回字串）。

**哪些該改**：只要該值代表「請求從哪裡來」就要改——稽核 `ip_address=`／
`source_ip=`、log 訊息裡的來源、任何 IP 比對或分桶。測試檔裡刻意造的
`REMOTE_ADDR` environ 不算。

**本機模擬兩條路徑驗收**（不必真的走 Cloudflare，本 session 驗證過可用）：

```python
from app import create_app
from app.security.client_ip import get_client_ip
app = create_app('development')
# 經 CF：remote_addr 為可信代理，採信 header
with app.test_request_context('/', environ_base={'REMOTE_ADDR': '192.168.0.20'},
                              headers={'CF-Connecting-IP': '203.0.113.7'}):
    assert get_client_ip() == '203.0.113.7'
# 非可信代理送同一個 header：必須被忽略
with app.test_request_context('/', environ_base={'REMOTE_ADDR': '192.168.0.50'},
                              headers={'CF-Connecting-IP': '203.0.113.7'}):
    assert get_client_ip() == '192.168.0.50'
```

尚未收斂的 28 處記錄用 `remote_addr`（`api/auth.py` 12、`api/files.py` 6、
四個模組 10）見待辦 **PF-36**（內含完整 grep 指令與驗收步驟）。

### 開發工具 `/dev/*` 的三層防護（別再重查一次）

`/dev/quick-login` 這類工具的「僅限內網」由三層構成，**真正在管來源 IP 的是第一層**：

| 層 | 位置 | 作用 |
|---|---|---|
| iptables | `/etc/iptables/rules.v4`（netfilter-persistent 持久化） | 來源白名單，清單外一律 DROP |
| nginx | LAN vhost 只 `listen 192.168.0.16:7000`；tunnel vhost 對 `^/beakplatform/dev(/\|$)` `return 444` | 阻斷公開通道 |
| 應用層 | `dev.py::internal_network_only`（`ipaddress` 網段判定 + `get_client_ip()`） | 縱深防禦最內層 |

現行 iptables 白名單：`.10/.12/.13/.16` 全 port、`.20` 80/7000/8000/2222、
`.100` 7000/8000、`.17` 5180/5050、`.14` 7000。新增裝置要連 7000 就得加規則，
否則症狀是**連線逾時而非 403**（封包在 nginx 之前就被丟掉）。

```bash
sudo cp /etc/iptables/rules.v4 /etc/iptables/rules.v4.bak.$(date +%Y%m%d-%H%M)
sudo iptables -I INPUT <最後DROP的行號> -s <IP>/32 -p tcp --dport 7000 \
  -m comment --comment "<用途>" -j ACCEPT
sudo netfilter-persistent save
```

---

## 專案結構

```
/opt/BeakPlatform-dev/
├── backend/
│   ├── app/
│   │   ├── security/       # 安全核心（勿隨意修改）
│   │   ├── crypto/         # 檔案加密模組 (AES-256-GCM)
│   │   ├── api/            # API 路由
│   │   ├── web/            # Web 路由
│   │   ├── models/         # 資料模型
│   │   ├── services/       # 業務邏輯
│   │   └── templates/      # Jinja2 模板
│   └── tests/
├── modules/                # 模組目錄
├── docs/
│   ├── GLOSSARY.md                    # 溝通對照表
│   ├── PLATFORM_MODULARIZATION_PLAN.md  # 架構與模組化標準
│   └── archive/                       # 已完成的歷史文件
├── scripts/
│   └── migrations/         # 資料庫遷移
└── .semgrep/               # 安全規則
```

---

## 模組靜態檔案規範

模組的 JS/CSS/圖片等靜態資源由 `module_loader.py` 自動註冊 serve。

**目錄結構：**
```
modules/<module_name>/static/modules/<module_name>/
  ├── js/           # JavaScript
  ├── css/          # 樣式表
  └── icons/        # 圖示
```

**存取 URL：** `/static/modules/<module_name>/js/xxx.js`

**禁止** 將模組靜態檔案複製到 `backend/app/static/`。
`backend/app/static/` 只放平台級資源（themes.css、vendor/、auth.js 等）。
模組資源一律放在 `modules/<name>/static/` 下，由 module_loader 自動 serve。

---

## 前端開發規範

### FRONT-01: JS/CSS 分離原則

**HTML 模板中禁止大量內嵌 JS/CSS。**

| 類型 | 規範 |
|------|------|
| CSS | 抽為 `.css` 靜態檔 |
| JS 邏輯 | 抽為 `.js` 靜態檔 |
| 膠水碼（初始化、Jinja2 變數注入） | 可留在 HTML，不超過 30 行 |

平台層：`backend/app/static/js|css/`；模組層：`modules/<name>/static/modules/<name>/js|css/`

需要把 Jinja2 變數帶進 JS 時用 window bridge（`window.__PAGE_CONFIG = {...}`）。
JS 與 Jinja2 深度交織無法乾淨分離時，才保留 `{% include "_xxx_methods.html" %}` partial。

抽離模式範例與完整說明：**`docs/codex_spec/frontend.md`**


### FRONT-02: HTML 模板行數上限

- 單一 HTML 模板不應超過 **500 行**（含 HTML + 內嵌 JS/CSS）
- 超過時必須拆分：CSS → 靜態檔、模態框 → `_*_modals.html`、JS → `.js` 靜態檔或 `_*_methods.html` partial
- 參考已完成的拆分模式：`form_center.html`、`departments.html`、`form_designer.html`

### FRONT-03: Node Type 定義禁止硬編碼

- **禁止**在 API 程式碼中硬編碼 node type 定義
- `workflow_node_definitions` DB 表是 **single source of truth**
- API 透過 `WorkflowNodeDefinition` ORM Model 查詢
- 新增 node type 流程見 `docs/archive/NODE_TYPE_NORMALIZATION_PLAN.md`

### FRONT-04: Code 欄位自動建議規範

需要唯一識別碼的建立表單，統一 UX：輸入名稱 → debounce 500ms → `POST /api/code/generate`
取得建議值當 placeholder → 手動輸入時 `POST /api/code/validate` 即時驗證 →
留空提交時後端採用建議值。不強制大小寫轉換。

前端引入 `/static/js/code-input.js` 的 `codeInputMixin(entityType)`，
標準區塊 HTML 用 `{% include "partials/_code_input.html" %}`。

### FRONT-05 / FRONT-06 / FRONT-08: 前端框架陷阱

以下三條寫錯會造成排版錯亂或功能靜默失效，**派工給 codex 時必須貼進 prompt**
（完整說明與範例在 `docs/codex_spec/frontend.md`）：

- **FRONT-05**：CSS 全寬規則必須排除 radio/checkbox
  （`input:not([type="radio"]):not([type="checkbox"])`），否則同列文字被擠成直排
- **FRONT-06**：有 `x-show` 的元素禁止 inline style 設 `display`
  （x-show 還原時會清掉，佈局遺失）
- **FRONT-08**：select 綁動態 `x-for` options 時，option 必須加
  `:selected="<值> === <狀態>"`，否則初次渲染顯示第一個選項
  （症狀：一進頁面顯示錯的，手動改一次就正常，極易漏看）


### FRONT-07: 模組 CSS 命名與排版規範

**平台未載入 Bootstrap。** 全域 CSS 只有 `common.css` + `base-layout.css`，
提供 `.btn` / `.data-table` / `.form-control` / `.modal-overlay`，**沒有 Grid 系統**。

- 禁止 `row` / `col-md-*` / `card` / `table-sm` / `mb-3` / `d-flex` 等 Bootstrap class
  （寫了完全無效果，排版會全部擠在一起）
- 排版用 CSS Grid / Flexbox；模組 class 加前綴（`wks-`、`ird-`、`fw-`、`pir-`）

**CSS 變數白名單**（只能用這些，禁止自創）：

```
--color-primary  --color-text  --color-text-secondary  --color-text-muted
--color-bg  --color-bg-white  --color-bg-light  --color-border
```

自創 `--text-primary`、`--surface-color` 這類不存在的變數時，CSS fallback 值會生效，
曾造成整頁深色 fallback、白底白字。**派工給 codex/agent 時必須在 prompt 明列此白名單。**

版型範例：`modules/form_workflow/static/modules/form_workflow/css/fw-dashboard.css`


### FRONT-09: D2 的 `BkCaps.can()` 需要頁面注入 `__PAGE_CAPS`

`capability.js` 的 `BkCaps.can(code)` 讀 `window.__PAGE_CAPS`，
**該變數由各頁面自行注入，沒有全域預設值**。漏注入時 `can()` 恆為 `false`，
症狀是**按鈕點下去完全沒反應、console 也不報錯**。

```python
from app.services.capability_service import build_caps
return render_template('...', page_caps=build_caps(['module.permission_code']))
```
```html
<script>window.__PAGE_CAPS = {{ page_caps | default({}) | tojson }};</script>
```

模板層的 `{% if can('...') %}` 走後端 Jinja2 global，**與此無關**——
所以會出現「按鈕有渲染出來但點了沒用」的矛盾現象，這正是漏注入的特徵。
（`layouts/base.html` 已載入 capability.js，不必重複引入。）


### FRONT-10: 後端組「指向本頁」的網址必須帶 `request.script_root`

app 掛在 nginx 的 `/beakplatform` 前綴下，而 **Flask 的 `request.path` 不含該前綴**。
只用 `request.path` 組出的 `/public/portal/...` 在瀏覽器上會被當成缺前綴的
絕對路徑而 404。

```python
# 錯：點下去 404
f"{request.path}?{urlencode(args)}"
# 對
f"{request.script_root}{request.path}?{urlencode(args)}"
```

Page IR 的排序連結**從第一版起就是壞的**，直到 2026-07-29 才發現
（`renderer._self_url()` 已修）。原因見下條。

### VERIFY-01: 使用者要點擊的東西，驗收必須用瀏覽器

curl 對「連結、按鈕、select 初次渲染值」有**結構性盲區**：

- 用 curl 測連結時都是自己帶完整路徑，永遠測不出網址少了前綴（FRONT-10 的成因）
- select 顯示錯值（FRONT-08）在 HTML 原始碼裡看不出來，要渲染後才知道
- `BkCaps.can()` 漏注入（FRONT-09）的症狀是「按鈕點了沒反應、console 不報錯」

→ 只要變更涉及使用者要點的東西，curl 驗完**還要**用 chrome-devtools 實際點一次。

### VERIFY-03: AI 產出的自我檢查表不算驗收（2026-08-04 起）

codex／subagent **開不了瀏覽器**，它的「自我檢查七項全過」只證明程式碼有寫，
不證明串得起來。2026-08-04 menu 設計器面板那批，codex 自述七項全過，實測抓到兩個 P1：

- 底圖下拉存錯 sc（`DcBackground.secure_code` vs `platform_files.secure_code`）
  → 選了底圖**完全沒反應也不報錯**
- 「不使用底圖」寫入空字串違反 schema pattern
  → **整頁存不了**，而且 400 指向不相干的 widget，使用者無從聯想

**工具能力歸屬**：chrome-devtools MCP 只有主 Claude 有，codex／subagent 沒有。
所以「要點、要 hover、要看渲染結果」的驗收**只能由主 Claude 做**，不可外包後採信回報。

→ 凡 AI 產出的前端與跨層串接，一律自己用 chrome-devtools 走一次真實操作；
驗收 checklist 逐項自己跑，不採信它的回報。與 VERIFY-01 同源，
差別在這裡強調「AI 說通過」比「沒測」更危險——它讀起來像已驗收。

### VERIFY-02: 驗收輸出必須留證（2026-08-01 起）

**驗收的原始輸出一律落地到 `/opt/tmp/verify/<日期>-<主題>.log`，不要只留在對話裡。**

```bash
mkdir -p /opt/tmp/verify
curl ... 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
../venv/bin/python -m pytest tests/test_xxx.py -q 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
```

瀏覽器驗收同理：chrome-devtools 的截圖存檔、關鍵 console/network 觀察貼進同一個 log。

**chrome-devtools 的截圖不能直接寫 `/opt/tmp`**（工具限制在 workspace root 內，
會回 `Access denied: path ... is not within any of the configured workspace roots`）。
做法是先存到專案內再搬走：

```
take_screenshot(filePath="/opt/BeakPlatform-dev/.verify-xxx.png")
mv /opt/BeakPlatform-dev/.verify-xxx.png /opt/tmp/verify/<日期>-xxx.png
```

**但 2026-08-04 起 `take_screenshot` 在本機一律逾時**
（`Page.captureScreenshot timed out`，png / jpeg 皆然，各卡滿 120s 才失敗，
試過三次）。**留證改用 `evaluate_script` 取關鍵區塊的 `innerText`**——
成本更低、可 grep、也更適合寫進 log：

```
evaluate_script(function="() => document.querySelector('.modal-overlay').innerText")
→ 把回傳文字貼進 /opt/tmp/verify/<日期>-<主題>.log
```

DOM 狀態類的斷言（class 有沒有、按鈕文字、哪個卡片 active、欄位可見性）
一律用 `evaluate_script` 回結構化 JSON，比截圖更精確也更好覆核。
截圖工具修好之前不要再浪費 120s 去試。

**理由**：2026-08-01 對四個 session 做事後幻覺稽核（363 條事實斷言逐條查證，見知識庫 #4957），
41 條判定為 UNVERIFIABLE——絕大多數是瀏覽器實測與 rate-limit 觀察，**輸出當下就沒落地，
事後無論花多少成本都查不回來**。「我測過了」若沒有留下輸出，事後與「我以為我測過了」無法區分。
留證的成本是一個 `tee`，缺證的成本是整段驗收失去可覆核性。

### CACHE-01: 靜態資源 Cache-Busting

**Flask 全站機制，確保 JS/CSS 變更後瀏覽器立即載入新版，無需 F5。**

實作位置：`backend/app/__init__.py` 的 `register_static_cache_busting()`

| 層 | 覆蓋範圍 | 原理 |
|---|---|---|
| `url_defaults` | `url_for('static', ...)` 引入的檔案 | 自動附加 `?v=<啟動時間戳>`，重啟服務即換版本號 |
| `after_request` | 裸路徑 `/static/...` 引入的檔案 | JS/CSS 回應加 `Cache-Control: no-cache, must-revalidate`，強制條件請求 |

**開發時注意事項：**
- 兩種引入方式都已涵蓋，新增模板時用哪種都可以
- 檔案有變更 -> 瀏覽器拿 200 新內容；沒變更 -> 304（不浪費頻寬）
- 重啟 Flask 後版本號自動更新

---

## 多語系規範 (I18N-01)

平台支援 zh-TW（原文即 key）+ en。**所有新 user-facing 字串必須包翻譯函式**：
Python `_('中文')`、Jinja2 `{{ _('中文') }}`、JS `__('中文')`。

**四條地雷**（違反會 500 或讓功能失效）：
- msgid 含字面 `%` 必須寫 `%%`（flask_babel 一律做 % 插值）
- **禁止**包裹參與 `==`/`===` 比較的字串與機器可讀錯誤碼（包了前端比對即失效）
- **禁止**包裹 logger/console 訊息、寫入 DB 的資料值、email 主旨內文
- pybabel update 的 fuzzy 配對幾乎全錯，必須逐條重翻並清 fuzzy flag

**extract 必須帶齊全部已包裹模組目錄**（open_defense / vuln_lifecycle / spec_formulate /
nocode_builder / form_workflow）——少帶任何一個，該模組 msgid 會被打成 obsolete
並喪失翻譯（已發生過事故）。新模組包裹後要加進清單。

完整指令、JS 字典規則、FormIO locale 陷阱：**`docs/codex_spec/i18n.md`**
進度計畫：`docs/I18N_PLAN.md`


## 時區處理規範 (TZ-01)

**DB 一律存 UTC**（`datetime.utcnow()`，欄位 `timestamp without time zone`）。
純日期欄位（`effective_from`、合約日期）不涉及時區，直接存日曆日期。

顯示時區優先序由 `auth_interceptor.py` 設定：**用戶個人 > 企業設定 > `Asia/Taipei`**（`g.timezone`）。

| 位置 | 必須 | 禁止 |
|---|---|---|
| 後端模板 | `{{ dt\|tz_format('%Y-%m-%d %H:%M') }}` | `dt.strftime()`（會顯示 UTC） |
| 前端 JS | `BkTime.format(dateStr, 'short')` | `new Date(x).toLocaleString()`（會用瀏覽器時區） |
| 後端 API 回格式化字串 | 先 `.replace(tzinfo=UTC).astimezone(user_tz)` 再 strftime | 直接 strftime |

`BkTime` 由 `timezone.js` 在 base.html 全域載入，style 可用 `full`/`short`/`date`/`time`。

**自行做時間運算時（SLA 倒數、時間差）**：DB 回的 ISO 字串是 naive UTC（無 `Z` 後綴），
直接 `new Date(iso)` 會被當本地時間、差 8 小時（已踩過：SLA 顯示逾時 465 分）：

```javascript
const iso = s.endsWith('Z') ? s : s + 'Z';   // naive UTC 補 Z
const deadline = new Date(iso).getTime() + slaMinutes * 60000;
```


## 禁止事項

1. **禁止** 繞過認證攔截器
2. **禁止** API 直接查詢 Model
3. **禁止** 在 URL 使用自增 ID
4. **禁止** 硬編碼密鑰/密碼
5. **禁止** SQL 字串拼接
6. **禁止** 在平台內實作業務功能（應透過模組）
7. **禁止** 將模組靜態檔案複製到 `backend/app/static/`（會造成雙份不同步）
8. **禁止** 在 API 程式碼中硬編碼 node type 定義（應查 DB）
9. **禁止** HTML 模板內嵌大量 JS/CSS（應抽為獨立靜態檔或 partial）
10. **禁止** 後端模板直接 `.strftime()` 顯示 datetime 欄位（應用 `|tz_format`，參見 TZ-01）
11. **禁止** 前端 JS 用 `new Date().toLocaleString()` 顯示 DB 時間（應用 `BkTime.format()`，參見 TZ-01）
12. **禁止** 繞過 `file_service` 直接操作檔案儲存目錄（參見 FILE-01）
13. **禁止** 手動呼叫 `crypto/engine.py` 加解密（應透過 `file_service` 自動處理）
14. **禁止** 在有 `x-show` 的元素上用 inline style 設定 `display`（應用 CSS class，參見 FRONT-06）
15. **禁止** select 綁動態 `x-for` options 卻不加 `:selected`（初次渲染會顯示錯值，參見 FRONT-05/06 段）

---

## 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

---

## 備忘

### Forgejo
- **URL**: http://192.168.0.16:3000/
- **Repo**: http://192.168.0.16:3000/forgejoadmin/BeakPlatform
- **API Token**: `be6f8e52f155aa026ac12c5bd470114aa7c54333`

### 開發測試登入（本開發機獨有）
- **快速切換帳號（免密碼）**: `http://192.168.0.16:7000/beakplatform/dev/quick-login`，點帳號即登入
- **用完必按該頁 [登出] 按鈕**（曾發生登出不乾淨，該按鈕即為補救設計）
- SYSTEM_ADMIN 唯一帳號: `admin@system.local`（密碼不明，不要用猜的，會鎖定）
- curl 自動化登入（E2E 用，JSON 版；表單版有防機器人三欄位，勿用）:
  ```bash
  BASE=http://192.168.0.16:7000/beakplatform
  curl -s -c cj.txt -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    -d '{"account":"admin-ethanyu@beluga.com","password":"ApiKeyTest2026"}'
  ```
- curl 快速切換**任意帳號**（免密碼免 CSRF，POST JSON 版，E2E 多帳號矩陣測試首選）:
  ```bash
  USC=$(psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
    -c "SELECT secure_code FROM users WHERE email='ethan@lion.com' AND is_deleted=false;")
  curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
    -H 'Content-Type: application/json' -d "{\"user_id\":\"$USC\"}"
  ```
- 常用 API 回應格式備忘：`GET /api/menu` 回 `{menu:[...]}`（樹狀，key 是 `menu` 不是 items）；
  權限中央 API（/api/permissions/*）的企業參數名是 `org_code`（不是 org）
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```

### NoCode Builder / Portal 開發備忘（2026-07-28 起）

**環境事實（2026-08-03 晚間更新）：開發機上目前有一個可用的 NoCode 子系統。**

當日稍早為了清空舊制 access_matrix，8 個子系統連同 site map 節點、頁面、
portal SQLite 全數刪除（備份 `/opt/tmp/backup/nocode-20260803-1507/`）。
之後以 `scripts/examples/provision_relief_donation_demo.py --force` 重建了教學實例：

| 項目 | 值 |
|---|---|
| 子系統（published） | `HJGEoAh6PBv5IXNHhMTu5P`（急難救助物資捐贈） |
| portal_path_id | `HdjFFvF-` |
| welcome 頁（2026-08-04 起已 published，內含雙 menu 示範） | `QlqVasK5fsLFMfUpPEvvFz` |
| 我的捐贈登記（要 `donation.manage`） | `Gqm4tuQEsBgituXVaDrCrr` |
| 物資公佈欄（要 `bulletin.read`） | `Ogi303_5kwPZdEE2IildYG` |

另有一個 `DzSQ8oTRKCnMVbuxS-431u`（`Ethan的test`，draft，用戶自建，**不要動**）。
重建腳本會**產生全新識別碼**，跑過就要回頭更新本表。
`tests/test_e2e_portal_cancel.py` 因依賴的驗收頁已刪而 **skip，這是預期狀態不是退步**。

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
- **Page IR v3 menu widget（PF-8c 起，2026-08-03/04 強化定版）**：

  ```jsonc
  {"type":"menu","id":"menu-1","title_i18n":{...},
   "items":[{"kind":"node","node":"<site_map_node_sc>","children":[...]},
            {"kind":"system","link":"login|register|logout"}],
   "orientation":"vertical|horizontal","item_gap":6,"hover_expand":true,
   "nav_source":"self|parent_selection","nav_key":"nav",
   "style":{"bg_color":"#ffffff", ...六色..., "border_color":"#dddddd",
            "border_width":1,"border_radius":4,
            "background_file":"<platform_files.secure_code>",
            "background_size":"cover","background_repeat":"no-repeat",
            "background_position":"center"}}
  ```

  **items 是完全自訂的樹**：陣列順序＝顯示順序、`children` 巢狀＝階層（深度上限 5），
  **不再跟著 site map 的結構與順序走**（2026-08-03 用戶定案改的，早期版本相反）。
  名稱與圖示仍即時取自 site map，所以改名會反映；節點被刪或停用時該項連同
  children 整枝消失（fail-closed）。
  顯示條件 = 在 items 樹中 AND `check_page_access` 通過（menu 是導覽、不是授權邊界，
  各頁自己仍會再判一次）。
  **樣式顏色一律 `^#[0-9a-fA-F]{6}$`**（schema 擋一次、renderer `_menu_style()`
  白名單化再擋一次——值最後會進 inline style，兩道防線缺一不可）；
  底圖只認 `context_type == 'nc_background'` 的 platform file，不接受任意 URL。
  **底圖存的是 `platform_files.secure_code`，不是 `DcBackground.secure_code`**
  （`/api/nocode-builder/backgrounds` 的 `platform_file_sc` 欄位），
  存錯的話症狀是「選了底圖完全沒反應、也不報錯」。
  兩個 menu 聯動：`nav_source=parent_selection` 依 `?<nav_key>=` 只渲染該節點的
  children，純伺服器端；聯動連結**只沿用本頁各 menu 的 nav_key**
  （`renderer._menu_nav_keys()`），不可整包複製 `request.args`（表格的
  `xxx__page`／`xxx__sort` 會被帶去別頁撞上同 id 的 widget）。
  橫式子選單是純 CSS hover 浮出，父子之間的 gap 必須有透明 `::before` 橋接，
  否則滑鼠移過去的瞬間就離開 `:hover`、子選單當場消失（commit `71e8ea54`）。
  平台層走 registry：`register_menu_provider(world, fn)`，portal 實作在
  `services/pageir_portal_menu.py`；**platform world 沒有 provider 是預期狀態**
  （entries 回空陣列，不 raise）。
  `system_link` 值域是**後端白名單**（login/register/logout），不接受任意 URL；
  login/register 只在未登入時出現，register 另需 `allow_registration`，logout 反之。
  **設計器預覽的 menu 連結留在預覽語境**（2026-08-06 起，commit `a0272748`）：
  `portal_user['user_type'] == 'PREVIEW'` 時，node 連結組成
  `/nocode/ir-designer/<目標頁sc>/preview?sub=&level=&group=`（沿用當前預覽身分），
  system_link 一律不輸出（預覽沒有 portal session，登入／登出走不通）。
  在此之前連結一律指向公開 portal，**未發布的子系統／頁面點下去必定 404**
  ——症狀是「直接按預覽正常、從預覽的選單點過去 404」。正式 portal 行為不變。
  site map 的 `folder` 節點型別已放行（不建 page layout、不可當根節點）。
  設計器屬性面板已完備（已選項目樹的 ↑↓ 排序／→← 升降階／× 連 children 移除、
  可加入的網頁清單、方向／間隔／懸停展開、選單來源與聯動參數名、七個色票、
  框線寬度與圓角、底圖選取／上傳／預覽）。
  尚未移植 v2 SITEMENU 的：橫式圖示位置、選單高度、懸停延遲
  （BBN 待辦 **PF-19**，內含 v2 的值域／預設值、要改的檔案清單、驗收與留證方式；
  用 `note_search("PF-19")` → `note_get` 取全文，**動工前先讀，不要自己猜規格**）。
- **Page IR v3 有三個版面引擎**（2026-08-05 起，定版 `docs/PAGE_IR_LAYOUT_ENGINES.md`）：
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
  細節與 `owner_ref` 傳參規則見 `docs/codex_spec/portal.md`
- **判斷一個 NoCode 頁面「還活著」必須走雙路徑 OR**，只看 site map 會誤判：
  ```
  存活 = (有存活 dc_site_map_nodes 指向 且 該節點的子系統存活)
      OR (有存活 dc_sub_system_pages 掛載 且 該子系統存活)
  ```
  portal 頁**不一定掛在 site map 節點下**，可能只透過 `dc_sub_system_pages` 關聯
  （`FORMTEST00000000000001`、`qiHMpMCul-1KGxhU4Q7Trd` 就是這種；
  這兩個 sc 已隨 2026-08-03 的全面清除而不存在，例子留著是為了說明形態）。
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
  2026-07-31 清孤兒時只看 site map，把這兩個 published 驗收頁誤刪，
  其中前者是 `test_e2e_portal_cancel.py` 的依賴，**刪掉會讓 E2E 靜默 skip 而不是報錯**。
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
- 權限模型與判定鏈：`docs/PORTAL_ACCOUNT_SPEC.md`；
  完整交接與踩坑清單：`docs/handoff_nocode_n1_n5.md`
- v2 `layout_json` 已退役，`/p/` 遇到會回 410；設計器只認 `ir_version: 3`
- **頁面版面樣板庫（PF-24~28、PF-32，2026-08-04 起）**：`dc_page_templates` 有三種
  `scope`——`system`（平台內建，`org_secure_code` 與 `sub_system_secure_code`
  **必須為 NULL**，DB 有 CHECK 約束；**只能由種子腳本建立，API 一律 403**）／
  `org`（企業自建）／`sub_system`（子系統私有）。

  | 端點 | 用途 |
  |---|---|
  | `GET /api/nocode-builder/templates?sub_system=<sc>[&include_hidden=1]` | 三段 union：內建 + 本企業 + 該子系統私有 |
  | `POST /api/nocode-builder/templates` | 另存為樣板（`scope='system'` → 403） |
  | `POST /api/nocode-builder/templates/<sc>/instantiate` | 以樣板建頁，回 `{page, report}` |
  | `POST /api/nocode-builder/sub-systems/<ss>/template-hides` | 隱藏內建樣板（冪等，非 system → 400） |
  | `DELETE /api/nocode-builder/sub-systems/<ss>/template-hides/<tpl>` | 取消隱藏（冪等） |

  **`scope='sub_system'` 的樣板只有來源子系統看得到**（`list_templates` 第三段以
  `sub_system_secure_code` 過濾）。所以**跨子系統套用在 UI 上唯一走得到的路徑是
  `scope='org'` 樣板**——要重現淨化行為時別選 sub_system 的（會看不到），
  也別選內建的（零綁定、淨化是 no-op）。

  **隱藏是「可見性」不是「授權邊界」**（PF-32）：`dc_sub_system_template_hides`
  記錄 per 子系統的隱藏名單，只作用於 `scope='system'`。
  `list_templates` 預設扣掉、`include_hidden=1` 保留並標 `is_hidden`。
  `instantiate` **刻意不檢查隱藏**（UI 觸發不到，且隱藏不是安全邊界）。
  **取消隱藏一律硬刪列**（`db.session.delete`），不可軟刪
  ——unique `(sub_system_secure_code, template_secure_code)` 會擋住之後重新隱藏。
  隱藏**不得**用「軟刪 system 樣板」實作：種子腳本會把 `is_deleted` 設回 False 復活它。

  `instantiate` **只建 `DcPageLayout`**，不建 site map 節點、不做子系統掛載
  ——那是前端 `workspace.js` 的 `finishPageCreation()` 接手做的。
  它也會把 IR 的 `page.title_i18n` 覆寫成新頁名稱（不覆寫的話 portal 上會顯示樣板名）。

  **同子系統套用完全不淨化**（`sanitized = (not source) or (source != target)`，
  `page_template_service.py:18` 一開頭就 `return`）——所以 menu 的 `items[].node`、
  `shared_ref`、access_matrix **原封不動保留**，`create_template` 也是原樣存
  `layout_json` 不做任何處理。「另存為樣板」存的是**當下那頁的完整 IR**，
  不是內建樣板的副本；內建樣板的「零綁定」是那六筆種子資料的內容，
  **不是會傳染的屬性**（2026-08-06 API 實測確認）。
  要讓新頁一建出來就有選單，正解是先設好一頁（menu 引用共用選單）再另存為
  子系統私有樣板；既有頁面沒有批次套用的方法，見待辦 **PF-47**。

  **跨子系統套用一定會淨化**（判定依據是樣板的 `source_sub_system_sc`；
  為 NULL 一律走淨化路徑）。唯一實作是
  `modules/nocode_builder/services/page_template_service.py::sanitize_template_ir()`，
  純函式、不碰 DB，**禁止各處自行清理引用**。規則的分水嶺是 schema 能不能省略：
  menu 的 `items[].node` 可整枝移除；`binding.resource` 是必填 → 整個 widget 移除
  （並同步清 canvas `widget_ids`／layout `children`／`row_link_ref`）；
  權限碼類（`action_ref`／`access_matrix`）**保留並列進 `report.warnings`**
  ——系統本來就 fail-closed，擅自清掉反而讓使用者以為設定過了。
  `report` 內是**機器可讀碼**（`binding_unavailable` 等），中文對照在前端
  `page-template.js` 的 `describeReport()`，**後端不要翻譯**。

  內建樣板用 `scripts/seed_system_page_templates.py --apply` 種入（冪等，
  固定 secure_code `sys_tpl_*` 六個：`top_left_main` / `top_main` / `left_main` /
  `single` / `dashboard` / `free_blank`）。它們**一律零綁定**（空 menu + 佔位 text）
  ——會被所有企業的所有子系統套用，任何綁定必然是錯的。
  `--purge-legacy` 可軟刪沒有 `ir_version` 的 v2 舊樣板（預設不做）。

  `thumbnail_svg` **留空即可**，前端 `templateThumbnailSrc()` 會從 IR 即時生成，
  不要在 Python 裡重寫 SVG 產生器。該欄位是可經 API 寫入的自由文字，
  所以**一律用 `<img src="data:image/svg+xml,...">` 呈現、禁止 `x-html`**
  （img 內的 SVG 不執行腳本），後端另有 `_validate_thumbnail_svg()` 擋
  `<script>`／`on*=`／`xlink:href`／超長。

  **IR 的 `zone.row` / `zone.col` 是 1-based**（schema `minimum: 1`），
  換算成陣列索引要減 1。`gridSvg` 犯過這個錯，所有 zone 疊在同一格、
  縮圖只剩右下一塊（2026-08-04 commit `324842d8` 修）。

- **子系統層級共用元件（2026-08-06 起，取代 PF-29 的「共用選單」）**：
  樣板是**複製語意**，共用元件是**引用語意**——改一次，所有引用它的頁面同步生效。
  定版規格 `docs/SHARED_COMPONENTS_SPEC.md`。

  **舊的 `dc_shared_menus` 表與 `/shared-menus` 端點已停用**（表保留為備份、
  程式不再讀寫，13 筆資料已由 `scripts/migrations/094_shared_components.sql`
  遷入新表）。看到舊名一律視為過時。

  `dc_shared_components`（子系統層級）：`name`（同子系統內唯一）、
  `widget_type`、`widget_json`（**完整 widget 組態，不含 id**）。
  頁面端只寫 `{"type":"menu","id":"menu-1","shared_ref":"<sc>"}`。

  | 端點（全部 `@permission_required('nocode_builder.manage')`） | 用途 |
  |---|---|
  | `GET /api/nocode-builder/sub-systems/<ss>/shared-components?widget_type=menu` | 列出（型別選填） |
  | `POST` 同上路徑 | 建立（`widget_type` 由 `widget_json.type` 推導；名稱重複 → 409） |
  | `PUT/DELETE .../shared-components/<sc>` | 更新／刪除（被引用 → 409 並回 `usages`） |

  **完全共用（2026-08-06 使用者裁決，推翻 PF-29 的合併優先序）**：
  引用時**一律取共用元件的值，頁面端不覆寫任何欄位**。
  同一份選單要 A 頁橫式、B 頁縱式 → **建兩個共用元件**（menu-1 橫、menu-2 直）。

  **唯一例外是 `access_matrix`，語意是交集**：共用元件與頁面 widget 兩份
  **都要通過**才渲染（`renderer._widget_read_allowed` 兩份都判）。
  它是授權邊界不是外觀，取其一會讓某邊設定靜默失效。

  **展開只在 `renderer._prepare_widget` 開頭一處做**（dispatch 之前，
  所有 widget 型別共用），透過
  `registry.register_shared_component_resolver(world, fn)`（portal 實作在
  `services/pageir_shared_component.py`，**platform world 不註冊是預期狀態**）。
  三個渲染入口（`portal_public.py`、平台 `/p/`、設計器預覽）都吃得到，
  **不要在入口各判一次**——這專案已因「三處各自查」在正式 portal 上全數 404 過。
  resolver 驗 ctx 的 `sub_system_sc` **與 `org_secure_code`**，
  所以**每個 `set_render_context('portal', ...)` 呼叫點都必須傳 `org_secure_code`**
  （目前 9 處都有），漏傳的路徑上共用元件會整批消失。
  解析不到一律 **fail-closed：整個 widget 不渲染**（不是空選單），並記 warning。

  schema 八個 widget 型別**全部**是 `required: ["id","type"]` 加
  `anyOf: [{required:[<原必填>]}, {required:["shared_ref"]}]`；
  `validator` 對任何有 `shared_ref` 的 widget 跳過欄位語意檢查。

  **跨子系統套用樣板時清掉所有型別的 `shared_ref`**（report 碼
  `shared_component_refs`）：menu 清掉後補 `items: []`（少補的話淨化產物過不了
  `validate_page_ir`，整個 instantiate 會 500），其他型別因缺必填欄位
  **整個 widget 移除**（reason `shared_component_unavailable`）。

  **設計器 UI（PF-53 批次 3，2026-08-06 起泛化到 `menu` / `table` / `detail` /
  `form` / `actions` / `text` / `layout` 七型別；`master_detail` 後端支援但
  設計器未開放）**：共用元件區塊是
  `_ir_designer_shared_component.html` 的 `render()` macro，在
  `_ir_designer_props.html` 對 `master_detail` 以外的型別統一呼叫一次——
  **要改這組 UI 只改 macro，不要在各型別面板各寫一份**。
  未引用時是引用下拉（依 `widget.type` 過濾）＋[另存為共用元件]；
  引用中是名稱＋[編輯共用元件]／[解除引用]（共用元件不存在時兩鈕 disabled）。

  **引用中的 widget 在頁面 IR 只留 `id` / `type` / `shared_ref` / `access_matrix`**，
  其餘設定鍵由 `ir-designer.js::stripLocalConfig` 剝除。因此
  `normalizeWidgets` / `normalizeWidgetMasks` 兩個補預設值的函式都必須
  `if (widget.shared_ref) continue;`——漏了就會把 `items`、`title_i18n`
  這類不會生效的設定寫回頁面。同理 `localSaveErrors` 也整個略過引用中的 widget。

  **[編輯共用元件] 不是 modal，是把右側屬性面板就地切換成編輯
  `sharedComponentEditor.draft`**（`get selectedWidget()` 在編輯模式回 draft、
  `markDirty()` 改標 `editor.dirty`、`selectWidget()` 與 `addWidget()` 一律 return）。
  這樣七個型別的既有欄位標記完全複用，不必複製第二份屬性面板。
  代價是**共用 layout 的 children 無法在編輯模式增修**（左側樹顯示的是頁面不是 draft），
  要改內容得先解除引用、在頁面上編好再另存為新的共用元件。

  建立／更新共用元件的 `widget_json` 一律走 `buildSharedWidgetJson()`：
  剝掉 `id` / `shared_ref` / `access_matrix`，table 另剝
  `row_actions_ref` / `row_link_ref`（指向同頁其他 widget，在共用元件的
  單 widget 假頁面裡必然 `dangling_ref` → 後端 400）。
  `access_matrix` 留在頁面端、引用中仍可編輯（§交集語意）；
  解除引用時以頁面端那份為準，頁面端沒有才取共用元件的。

  **寫入端要正規化 `style.background_file`**：UI 上「不使用底圖」是空字串，
  但 schema 的 pattern 不收空字串。頁面存檔走
  `ir-designer.js::normalizeMenuOnSave`，共用元件走
  `shared_component_api._normalize_widget_json`——**兩條路都要有**，
  漏掉的那條會讓使用者一編輯舊資料就 400。

- **menu 自動模式（2026-08-06 起）**：`source_mode: "manual" | "auto"`
  （預設 manual）＋ `include_system_links`（預設 false）。

  `auto` 時**忽略 items**，由
  `pageir_portal_menu._build_auto_items()` 依 site map 即時生成同形狀的 items 樹
  （`parent_secure_code` 組樹、`display_order` 排序、深度上限 5），
  再交給既有 `_build_item_entry` ——**權限過濾、預覽語境連結、nav 聯動全部沿用，
  不要另寫一套**，`_build_auto_items` 內**不做**任何 `check_page_access`。
  renderer 不查 site map，只把 `menu_source_mode` / `menu_include_system_links`
  放進 `menu_ctx`。

  schema 為此在 `menu_widget` 的 `anyOf` 加第三支
  `{"required":["source_mode"],"properties":{"source_mode":{"const":"auto"}}}`
  ——只有 auto 免寫 items。前端 `localSaveErrors` 的
  「選單尚未選擇任何網頁」也要排除 auto，否則自動模式一律存不了。

- **grid／free 引擎下，widget 只加進 `page.widgets` 不會顯示**，
  必須同時放進某個 `canvas.zones[].widget_ids`（free 是 `frames[]`）。
  `_canvas_widgets` 對未放置者靜默略過（只記 info log），
  症狀是「存了、DB 裡也有、畫面就是沒有」。用 API 直接改 IR 時最容易踩到。

### NoCode Builder API 操作備忘（2026-08-03 以 API 全程建出一個子系統後實測）

以下每一條都是**靠試誤才弄對**的，照抄可省一輪除錯。
完整可執行範例：`scripts/examples/provision_relief_donation_demo.py`（建置，九步）
與 `verify_relief_donation_demo.py`（端對端驗收，11 項）。

- **API 前綴是 `/api/nocode-builder`**（不是 `/api/nocode`）
- **部分 API 未豁免 CSRF**（例如建表 `POST /sub-systems/<sc>/tables`），
  token 只能從登入後頁面的 meta 取，登入回應不含
- `POST /sub-systems` 回傳的是 **`sub_system_secure_code` / `portal_path_id`**，
  沒有 `secure_code` 這個 key
- **子系統 `status` 不是 `published`，公開 portal 全部 404**
  → `POST /projects/<sc>/publish`（連動啟用選單與 portal 路徑）
- 頁面同樣要發布：`PATCH /pages/<sc>/publish`
- portal rows API 回應是**頂層 `rows`**，不是 `data.rows`
- master-detail submit 成功回 **201**（不是 200）
- `portal_settings`（`allow_registration` / `allow_anonymous`）**沒有 API**，
  只能直接寫子系統的 `portal.db`
- 建表 API 一律自動加 `id` / `created_at` / `portal_user_ref`，
  自行宣告這三欄會被擋成 `reserved_column_name`
- `POST /views` 的 `data_source` 只收 `org` / `conglomerate`；
  portal 業務表要用 `POST /sub-systems/<sc>/resolve-view`（會自動讀表結構生成 columns_config）
- **`admin-ethanyu@beluga.com` 的密碼 `ApiKeyTest2026` 已失效**（2026-08-03 實測 401，
  不要再猜密碼會鎖定）。自動化一律走 quick-login：

```bash
BASE=http://192.168.0.16:7000/beakplatform
# ORG_ADMIN admin-ethanyu@beluga.com
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
  -H 'Content-Type: application/json' -d '{"user_id":"jIYEQ-_lZMZNBkVy-hijal"}'
TOKEN=$(curl -s -b cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
```

**NoCode 沒有聚合能力**：`DcCrudView` 只 SELECT 單一實體表、無 GROUP BY／SUM，
且 `SqliteCrudService` 只認 `sqlite_master.type='table'`，**SQLite VIEW 綁不上去**。
要做統計只能「實體彙總表 + SQLite trigger」，這步必然落在 SQL 層。
範例見 `docs/examples/RELIEF_DONATION_DEMO.md` 第 2 節。

### 跑測試一律用 `scripts/run_tests.sh`（2026-08-05 起，強制）

```bash
cd /opt/BeakPlatform-dev
bash scripts/run_tests.sh                                  # 全部
bash scripts/run_tests.sh tests/test_pageir_shared_menu.py -q
bash scripts/run_tests.sh -k menu -q
```

**不要自己 `source .env` 之後直接叫 pytest。**
`TestingConfig` 的資料庫是 `os.getenv('DATABASE_URL', 'sqlite:///:memory:')`，
而 `.env` 的 `DATABASE_URL` 指向**開發庫 `beakplatform_dev`**；
`conftest.py` 與另外三個測試檔的 `app` fixture 收尾都會呼叫 **`db.drop_all()`**。
也就是說照舊寫法跑測試 ＝ 對開發資料庫 create_all + drop_all。
在 2026-08-05 之前一直沒毀掉資料，**只是因為 `drop_all()` 被 FK 相依擋下來而拋例外**
（那批 `ERROR at teardown` 就是它），不是有防護。

`scripts/run_tests.sh` 會在 source .env **之後**把 `DATABASE_URL` 覆寫成
拋棄式的 `beakplatform_test`。另有一道防呆在
`backend/tests/conftest.py::pytest_configure`：庫名不是 `_test` 結尾且非 sqlite
就直接 `pytest.exit`（放在 `pytest_configure` 而不是 app fixture，因為
`test_smoke.py` / `test_page_template_instantiate.py` / `test_page_template_scope.py`
各自定義的 app fixture 會覆蓋 conftest 的版本）。

測試庫不存在時（`beakplatform` 帳號沒有 CREATEDB 權限）：
```bash
sudo -u postgres createdb -O beakplatform beakplatform_test
```
本機 `ethan` 可直接 sudo、不需密碼。連線參數就是上面「資料庫資訊」那組
（`localhost:5432 / beakplatform / postgres123`）；`run_tests.sh` 可用
`TEST_DB_NAME` / `DB_USER` / `DB_PASS` / `DB_HOST` 環境變數覆寫。

**測試庫可以一直重複使用、不必每次重建**——每個 app fixture 都是
`create_all()` 開場、`drop_all()` 收尾。反過來說**不要拿它存任何想留的東西**。

**`tests/test_e2e_portal_cancel.py` 需要 systemd 服務實際在跑**：
```bash
sudo systemctl restart beakplatform-dev.service && systemctl is-active beakplatform-dev.service
bash scripts/run_tests.sh tests/test_e2e_portal_cancel.py -q
```
服務沒起來它會 skip（不是 fail），所以看到 skip 先確認服務狀態再下結論。

**跑出基準以外的失敗時，歸因順序**（照這個順序查，不要跳）：
1. 先看是不是**測試資料殘留**——`bash scripts/run_tests.sh -q` 重跑一次，
   結果不同就是殘留或測試間互相污染，不是功能回歸
2. 再看 log 有沒有 `Unknown permission code` / `Modules already loaded`
   這類**環境訊息**（前者是測試庫缺 seed，見 PF-34）
3. 都不是才當作功能回歸，用 `git stash` 比對改動前後

**基準（2026-08-05，commit `0e1e1157`，測試庫上跑完整 `tests/`）：
`382 passed, 1 failed, 1 skipped`（約 4 分鐘）。** 以此比對是否退步；
數字對不上時先看下面的歸因順序，不要直接假設是自己改壞的。

那 **1 failed 是已知且成因明確**（不是「不明原因，別管它」）：
`test_auth_interceptor.py::TestAuthDecorators::test_admin_required_for_admin`
拿到 403 而非 200，因為測試庫是 `db.create_all()` 建的空表、**沒有 RBAC seed**
（log 會印 `Unknown permission code: user:read`）。
要修就補 permission → role → `user_role_assignments` 整條鏈，
權威清單在 `scripts/migrations/075_seed_resource_crud_permissions.py`（BBN 待辦 PF-34）。
1 skipped 是 `test_e2e_portal_cancel.py`（需要實跑服務）。

**`tests/test_e2e_portal_cancel.py` 需要本機實跑服務**（掛 `pytest.mark.e2e`，
服務沒起來會 skip）。要跑它就單獨跑：
`bash scripts/run_tests.sh tests/test_e2e_portal_cancel.py -q`

#### 歷史註記：別再相信「13 個 error 是 SQLite JSONB 問題，不要修」

那句話只對**沒有** `DATABASE_URL` 時（走 SQLite in-memory）成立。
一旦 source 過 .env，錯誤集合完全不同（撞開發庫的殘留 + drop_all 失敗），
卻長期被歸進同一句「已知問題」而沒人再看。
改用測試庫後，先前被判定為「既有環境問題、12 個 error」的
`tests/test_page_template_instantiate.py` 直接變成 **14 passed**。
寫「已知問題不要修」時務必連**成因與判別方式**一起寫，否則它會保護錯的東西。

### form_workflow 發行（publish）陷阱
- `POST /api/mappings/<sc>/publish` 以表單/流程模板的 **version+revision** 判斷有無變更；
  直接改 `fw_workflow_templates.graph`（SQL 或 PUT API）**不會** bump revision，
  publish 會回「版本未變更」並沿用舊快照
- 解法：改完 graph 先 `UPDATE fw_workflow_templates SET revision = revision+1 WHERE ...` 再 publish
- intake / 表單中心都只讀 `fw_published_form_workflows` 最新 Published 快照，改模板不重發行等於沒改
- 流程變數：流程編號（OD-YYYYMMDD-NNNN）是 `${wi.exec_code}`；`${wi.code}` 是 workflow instance 的 secure_code，
  沒有 `${wi.execution_code}` 這個變數（替換結果為空字串）

### form_workflow 流程變數的儲存位置（寫錯地方＝流程引用不到）

**流程變數的權威儲存是 `fw_workflow_variables` 表，不是
`fw_workflow_instances.variables` JSONB。**

- `${v.xxx}` 走 `VariableService`，**只讀那張表**
- `${wi.xxx}` 只支援五個欄位（`base.py` 的
  `_WI_FIELDS = {'wi.code','wi.exec_code','wi.name','wi.status','wi.depth'}`）
- **兩條路都到不了 `variables` JSONB** —— 寫進 JSONB 只有自己查得到，
  流程設計者引用不到。要讓流程引用得到就用
  `VariableService.set_flow_var(instance_code, name, value, org_code)`
- 流程設計者設變數用既有的 **`OpSet`（設定變數）節點**

**`VariableService._cache` 是類別層級、無 TTL 的進程內快取。**
開發環境是 `flask run` 單進程 + 同進程 daemon thread 跑流程引擎，看不出問題；
多 worker 部署下，流程改了變數之後其他 worker 仍讀到舊值。
**用過期值做顯示只是難看，用過期值做授權判定就是漏洞** ——
授權判定一律繞過快取直接查 `FwWorkflowVariable`
（範例：`pageir_formflow_resources.is_submission_editable()`）。

### 正式環境已退役（2026-08-05 起，看到 :8000 回 502 先讀這段）

`/opt/BeakPlatform` 已改名 `/opt/BeakPlatform_OLD`，三個 systemd unit
（`beakplatform.service` / `-executor` / `-sync-worker`）已 disable + 刪檔，
用戶將從 GitHub 重新安裝。**本機唯一活著的 BeakPlatform 是 `/opt/BeakPlatform-dev`。**

| 現象 | 是不是故障 |
|---|---|
| `192.168.0.16:8000` 回 502 | **預期**。nginx 設定與 iptables 白名單刻意保留（重裝後沿用），後端沒了 |
| 外網 Cloudflare `/beakplatform/` 不通 | **預期**，同上 |
| `systemctl status beakplatform.service` 查無此 unit | **預期**，已刪檔 |

不要為了「修好 502」去改 nginx、重啟 gunicorn 或復活 unit。
重裝步驟與必須沿用的 `ENCRYPTION_MASTER_KEY` 見 BBN 待辦 **PF-39**
（`note_search("PF-39")`），舊 unit 原檔備份在
`/opt/tmp/backup/systemd-beakplatform-20260805/`。

`scripts/init_database.sh` 的路徑一律由 `${BASH_SOURCE[0]}` 推導 `REPO_ROOT`、
`DB_NAME` 從該 repo `.env` 的 `DATABASE_URL` 解析（`DB_NAME` 環境變數可覆寫），
一份腳本 dev 與正式環境通用。**禁止再往裡面寫死 `/opt/BeakPlatform` 或 `-dev`。**

### 服務啟動
- **正式管道是 systemd 服務**：`sudo systemctl restart beakplatform-dev.service`（重啟後 `systemctl is-active` 確認）
- 開發服務以**非 debug 模式**跑，Python/模板變更**不會自動重載，必須重啟**
- **踩坑**：若曾手動 `flask run`，殘留進程會佔住 7000 埠導致 systemd 服務 crash loop（`is-active` 一直是 `activating`）。用 `ss -tlnp | grep :7000` 找出佔埠 PID kill 掉，服務即自動接手
- **flask CLI 必須先載入 .env**（缺 SECRET_KEY 直接 ValueError）：
  ```bash
  cd /opt/BeakPlatform-dev && set -a && source .env && set +a
  cd backend && ../venv/bin/flask module sync --force   # 同步模組選單/權限定義到 DB
  ```
  模組選單的 user_types 改在模組 `__init__.py` 定義後需跑此指令；啟動時的自動同步**不含**權限覆寫（僅 --force 才會）
- 手動啟動（僅除錯用，用完要 kill）：
```bash
cd /opt/BeakPlatform-dev
source venv/bin/activate
set -a && source .env && set +a
cd backend && flask run --host=127.0.0.1 --port=7000
```
- 對外經 nginx `192.168.0.16:7000/beakplatform` 反代，flask 只綁 127.0.0.1

### 檔案輸出
- **輸出目錄**: `/mnt/smb`（SMB 共享）
- Windows 路徑: `\\192.168.0.16\smb`

---

*最後更新: 2026-08-05（定版 Codex-first 開發模式、待辦改指 BBN 白板）*
