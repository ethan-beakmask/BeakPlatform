# 自己開發一個流程節點

這份文件寫給**想替 BeakPlatform 的流程設計器加一種新節點**的人。讀完你會知道一個節點由哪幾層組成、
每一層的檔案在哪、照哪個既有節點抄最快、哪些地方漏掉會「不報錯但沒效果」。

文件末尾附一份完整的範例規格：**HTTP 呼叫節點（`HttpRequest`）**。它是本平台目前真正缺的一塊
（既有的通知節點都是寫死對象，沒有任何節點能打任意 REST API），規格寫到可以直接照著實作的粒度。
這份文件已經用一個方式驗證過：把全文交給 AI 程式助理當指令，它能據此做出可用的節點。
所以如果你用 AI 寫程式，也可以直接這樣用。

前提：你會 Python 與 JavaScript，手邊有一份可以跑起來的平台（含資料庫），而且是從原始碼目錄執行，
不是只有安裝好的二進位。以下 `<repo>` 代表原始碼根目錄。

---

## 一、一個節點由哪幾層組成

流程引擎只認兩樣東西：資料庫裡的**節點定義**（設計器靠它畫出工具列）與 Python 的**處理器（handler）**
（執行期靠它跑）。其餘都是讓人用得順的配套。下表每一列都是必做，右欄是漏掉時你會看到什麼。

| 層 | 檔案 | 漏掉的症狀 |
|---|---|---|
| 1. 處理器 | `modules/form_workflow/services/node_handlers/<name>_handler.py` | 節點執行時拋 `找不到節點類型 X 的處理器`，流程卡住 |
| 2. 處理器註冊 | 同目錄 `factory.py` 的 `register_builtin_handlers()` | 同上 |
| 3. 節點定義 | 資料表 `workflow_node_definitions` 一筆 | 設計器工具列沒有這個節點（也不報錯） |
| 4. 定義匯出成安裝種子 | `scripts/export_node_definitions_seed.py` 重跑 → `scripts/sql/seed_workflow_node_definitions.sql` | 你的機器有、**全新安裝的機器沒有**，而且不報錯 |
| 5. 圖示 | `modules/form_workflow/static/modules/form_workflow/icons/workflow/<name>.svg` | 畫布上是空方框 |
| 6. 設計器型別正規化 | `wf-render.js` 的 `normalizeNodeType()` typeMap | 只有大小寫變體進來時才出事；新節點照加一筆 |
| 7. 設計器面板派送 | `wf-accordion.js`：`nodesWithSettings` 清單、render 分派、post-render hook | 點節點只看到名稱與描述，沒有設定欄位 |
| 8. 設計器面板本體 | 新檔 `wf-node-<name>.js`（render ＋ collect） | 同上 |
| 9. 儲存時收集面板值 | `wf-save.js` 的 `autoApplyCurrentPanel()` switch 加一個 `case` | 面板填了、按「儲存」卻存回舊值（**最常見的靜默失敗**） |
| 10. 模板掛 script | `templates/modules/form_workflow/workflow_designer.html` 加一行 `<script>` | console 噴 `renderXxxPanel is not defined`，面板空白 |
| 11. 多語系 | JS 字串包 `__()`，`backend/app/static/i18n/en.json` 補 key；Python 面向使用者的字串包 `_()` | 英文介面出現中文 |
| 12. 測試 | `backend/tests/test_<name>_node.py` | 沒有症狀，這正是問題 |
| 13. 文件 | `docs/manual/04_form_workflow/<name>_node.md`（給設計者）；需要主機設定的再加 `docs/install/<name>.md`（給維運） | 使用者不知道怎麼用 |

列出既有節點在整個專案的全部觸點，是確認「我沒漏」最可靠的方法。挑一個與你最像的既有節點，例如
`OsFileRead`，執行：

```bash
cd <repo>
grep -rln "OsFileRead" --include=*.js --include=*.py --include=*.html --include=*.sql --include=*.json --include=*.md backend modules scripts docs
```

跑出來的每一個檔案，都問自己一次「我的節點要不要也出現在這裡」。

---

## 二、動手前的三個決定

### 1. 企業級，還是受限節點？

| | 企業級（`org_restricted=false`） | 受限節點（`org_restricted=true`） |
|---|---|---|
| 誰看得到 | 所有有流程設計權限的企業 | 只有在「節點授權」頁被系統管理員勾選的企業 |
| 適合 | 不碰主機、不碰平台自己的資料庫、風險可用白名單圈住的功能 | 執行 OS 命令、讀寫主機檔案、直接下 SQL 這類等同把主機交出去的功能 |
| 既有例子 | `Telegram`、`OpHrLookup`、`Branch` | `OsExecutor`、`OsFileRead`、`SysSqlExecutor` |

受限節點除了定義欄位不同，執行期與 graph 儲存期都會自動被授權服務擋下，不需要你另外寫。
處理器內仍要呼叫 `is_node_allowed(node_type, org_secure_code)` 當最後防線（企業級節點呼叫它會回 `True`，照寫即可）。

### 2. 失敗要讓流程「紅燈」，還是「綠燈但把真相寫進變數」？

處理器回 `{'status': 'error'}` 時，佇列會把這個節點標成失敗並**自動重試三次**。
對查詢、純計算這類可重跑的動作，這是對的。對**有副作用**的動作（送出 HTTP POST、寫檔、寄信），
重試等於重複副作用，不能用。

有副作用的節點採用平台既有的做法（`OsExecutor`、`OsFileWrite` 都是這樣）：
**一律回 `success`，把成敗真相寫進流程變數**（例如 `<前綴>_result`、`<前綴>_ok`），
讓下游的「分支」節點依變數決定走哪條路。設計者在流程管理頁會看到節點一片綠，
要知道真的成功與否得看變數，這要寫進使用手冊。

唯一例外是**設定本身就錯**（必填欄位沒填、變數名稱不合法）：這時在 `validate()` 拋 `ValueError`，
因為還沒發生任何副作用，讓節點直接失敗是正確的。

### 3. 節點需要「等」嗎？

不需要等的節點（絕大多數）處理完就回 `success`。需要等的節點有兩條路：

| 路徑 | 怎麼被喚醒 | 例子 |
|---|---|---|
| 時間到 | 回 `{'status': 'waiting'}` 並把 `queue_item.scheduled_at` 設成目標時間；執行器只對**名單內的節點型別**做這件事，名單在 `workflow_executor.py`，而且**有兩處**，要一起加 | `Delay`、`ParallelJoin` |
| 外部事件 | 回 `waiting`，由某支 API 在事件發生時把佇列項改回 `PENDING`；逾時另用結果 JSON 裡的期限欄位 | `FormAdapter`（簽核 API 喚醒它） |

不在名單內、又沒有 API 會改它狀態的節點，一旦進入 `WAITING` 就**永遠不會再被執行**，流程靜止且不報錯。
這份文件的範例節點不需要等；需要等的做法留給下一篇（等待外部回呼節點）。

---

## 三、逐層實作

以下假設新節點叫 `MyNode`。檔名用小寫底線，型別名用大駝峰，兩者要對得上。

### 3.1 處理器

繼承 `BaseNodeHandler`（`node_handlers/base.py`），至少實作 `handle()`，通常也覆寫 `validate()`。
基底類別提供的東西，用這些就夠，不要自己重寫：

| 方法 | 用途 |
|---|---|
| `get_config_value(key, default)` | 讀節點在設計器存下的設定 |
| `replace_variables(text, include_form=True, include_workflow=True)` | 把 `${v.xxx}`／`${f.欄位}`／`${fi.applicant}` 這類變數替換成實際值。**所有來自設計者的字串**（URL、訊息、路徑）都要過這一步 |
| `set_flow_var(name, value)` | 寫流程級變數，值可以是字串、數字、布林、dict、list（存成 JSONB） |
| `get_var(name, default)` | 讀變數 |
| `report_running()` | `handle()` 第一行呼叫，標記開始執行 |
| `log_info / log_warning / log_error(message, details)` | 寫入流程執行紀錄，設計者在流程管理頁看得到 |
| `self.queue_item.org_secure_code` | 這個節點所屬企業；**租戶隔離一律用它**，不要從設定值讀企業 |

回傳格式：

```python
return {'status': 'success', 'message': '一句話', 'data': {...給流程管理頁看的摘要...}}
```

處理器在**獨立子行程**裡執行，標準輸出不會進任何 log，想留紀錄只能靠 `log_*()` 與流程變數。
每個節點都有逾時，但 `workflow_node_definitions` 的 `default_timeout_seconds` **沒有程式讀它**，
處理器自己對外部呼叫設 timeout 才算數。

把「不碰資料庫的純邏輯」（白名單比對、格式驗證、結果整形）寫成模組層級的純函式，測試會好寫很多。

### 3.2 註冊

`factory.py` 的 `register_builtin_handlers()` 加兩行：

```python
from .my_node_handler import MyNodeHandler
NodeHandlerFactory.register('MyNode', MyNodeHandler)
```

### 3.3 節點定義

對開發用資料庫插一筆（欄位說明見 `modules/form_workflow/models/node_definition.py`）：

```sql
INSERT INTO workflow_node_definitions (
    secure_code, node_type, scope, category, display_name, description, icon,
    execution_handler, config_schema, canvas_shape, canvas_color,
    canvas_width, canvas_height, max_input_connections, max_output_connections,
    default_timeout_seconds, max_timeout_seconds, require_system_admin,
    is_active, is_deleted, org_restricted, created_at, updated_at
) VALUES (
    substr(md5(random()::text || clock_timestamp()::text), 1, 24),
    'MyNode', 'SYSTEM', '整合', '我的節點', '一句話說明',
    '/static/modules/form_workflow/icons/workflow/mynode.svg',
    'modules.form_workflow.services.node_handlers.my_node_handler.MyNodeHandler',
    '{"some_field": "string"}'::jsonb, 'roundrectangle', '#0EA5E9',
    120, 60, -1, -1, 120, 3600, FALSE,
    TRUE, FALSE, FALSE, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
);
```

- `category` 是中文分類名，**必須是既有的那幾個**：基本／表單／通知／控制／變數／操作／整合／安全／資安處置／系統。
  想加新分類要同時改 `api/workflows.py` 的 `category_map`、`workflow-designer-init.js` 的
  `CATEGORY_NAMES`／`CATEGORY_ICONS`／`categoryOrder`、`workflow-designer.css`，漏任一處分類就不出現
- `icon` 存不含部署前綴的路徑（`/static/...`），API 回傳時會自動補前綴
- `require_system_admin` 已無作用，固定 `FALSE`

然後**匯出成安裝種子**，否則全新安裝不會有這個節點：

```bash
cd <repo> && set -a && source .env && set +a
venv/bin/python scripts/export_node_definitions_seed.py
git diff --stat scripts/sql/seed_workflow_node_definitions.sql   # 應該只多出你那一筆
```

### 3.4 圖示

照既有檔案的格式：24×24 viewBox、`fill="none"`、`stroke="currentColor"`、`stroke-width="1"`，只用 `<path>`／`<circle>`／`<line>`。

### 3.5 設計器

五個檔案，建議開著 `grep -rn "OsFileRead" modules/form_workflow/static` 的結果對照改：

1. **`wf-render.js`** `normalizeNodeType()` 的 typeMap 加 `'mynode': 'MyNode'`
2. **`wf-accordion.js`** 三處：`nodesWithSettings` 陣列加 `'MyNode'`（這樣基本資訊區不會再長出自己的「套用」鈕）；
   `showNodeInfo()` 分派區加 `if (type === 'MyNode') info += renderMyNodePanel(node, nodeId);`；
   面板需要在 DOM 出現後載資料時，在 post-render hooks 區加
3. **`wf-save.js`** `autoApplyCurrentPanel()` 的 switch 加：
   ```js
   case 'MyNode': {
       const c = collectMyNodeConfig();
       if (c) { Object.assign(config, c); changed = true; }
       break;
   }
   ```
   這一步決定「切換到別的節點」與「按儲存」時面板的值會不會寫回 graph。漏了就是第一節表格第 9 列的症狀。
4. **新檔 `wf-node-my-node.js`**，兩個全域函式：
   - `renderMyNodePanel(node, nodeId)`：讀 `node.data('config')`，回傳 HTML 字串。每個欄位給唯一的 `id`
     （加前綴避免與其他面板撞名）。**`<select>` 的 option 一律依目前值輸出 `selected`**，
     否則初次渲染永遠顯示第一個選項、手動改一次才正常。使用者輸入的值放進 HTML 前要跳脫（照 `wf-node-os-file-read.js` 的 `_frEscapeHtml`）
   - `collectMyNodeConfig()`：面板不存在時回 `null`；存在時讀 DOM、做型別與範圍收斂（整數夾在合法區間、枚舉值不在清單就回預設），
     回傳要合併進 config 的物件
   - 所有顯示文字包 `__('中文')`
5. **`workflow_designer.html`** 在其他 `wf-node-*.js` 旁邊加 `<script src="{{ app_prefix }}/static/modules/form_workflow/js/wf-node-my-node.js"></script>`

畫布上的節點樣式（底色、邊框）在 `wf-cy-init.js` 依型別寫；不加也能用，只是拿預設樣式。

### 3.6 多語系

- JS 字串 `__('中文')`，並在 `backend/app/static/i18n/en.json` 加對應英文（扁平物件，key 就是中文原文）
- Python 面向使用者的訊息 `from flask_babel import gettext as _`，`_('中文')`；
  **不要包** 寫進流程變數的值、log 訊息、拿來做 `==` 比對的代碼字串
- 寫完跑 `pybabel extract`／`update`／`compile`（指令見 `backend/babel.cfg` 旁的說明或既有 commit），
  `update` 產生的 fuzzy 配對幾乎都錯，要逐條確認並清掉 fuzzy 標記

### 3.7 測試

照 `backend/tests/test_os_file_write_node.py` 的寫法：

- 純函式直接測，不碰資料庫
- 處理器用 `types.SimpleNamespace` 假造 `queue_item`（至少要有 `node_config`、`org_secure_code`、`node_type`、`node_id`、`secure_code`、`id`、`status`、`workflow_instance_secure_code`），
  用 `monkeypatch` 把 `set_flow_var`、`log_info` 等換成收集器，把對外呼叫（HTTP、DNS）換成假物件
- 需要資料庫的（例如 `SystemSetting`）用 conftest 的 `app` fixture
- **一律在原始碼根目錄用 `bash scripts/run_tests.sh tests/test_my_node.py -q` 跑**（測試路徑相對 `backend/`，指令本身在根目錄下），它會把資料庫指向拋棄式測試庫。
  直接 `pytest` 會打在你的開發庫上，收尾的 `drop_all()` 會刪光它
- 測試要涵蓋「設定被竄改」的情境：graph 可以透過 API 直接改寫，設計器的下拉選單與前端驗證都不是防線

### 3.8 文件

- 給流程設計者看的：`docs/manual/04_form_workflow/<name>_node.md`，照同目錄既有頁面的 frontmatter
  （`title`、`audience`、`order`、`nav_menu: form_workflow.workflows`、`covers` 列出處理器與面板 JS 路徑），
  並在 `mkdocs.yml` 的 nav「表單與流程」底下加一行。沒加進 nav 的頁面建置不會報錯、站上也點不到
- 需要主機設定（白名單、開關）的：`docs/install/<name>.md`，並在 `docs/install/README.md` 的表格加一列
- 寫完 `NO_MKDOCS_2_WARNING=1 ./venv-docs/bin/mkdocs build --strict` 要過

---

## 四、範例規格：HTTP 呼叫節點（`HttpRequest`）

以下是一份完整到可以直接實作的規格。它刻意選了會踩到第二節全部三個決定的題目：
它有副作用（所以結果走變數）、它對外連線（所以要白名單與 SSRF 防護）、它不需要等（所以不碰執行器名單）。

### 4.1 定位

讓流程呼叫任何 HTTP(S) API，把回應的狀態碼、標頭、內容寫進流程變數，供後續「分支」判斷、「寫入欄位」回填、「通知」引用。
有了它，Slack／Teams／Discord 的 incoming webhook、工單系統建單、自家系統的 REST API，全都不必再各寫一個節點。

| 欄位 | 值 |
|---|---|
| `node_type` | `HttpRequest` |
| `display_name` | `HTTP 呼叫` |
| `category` | `整合` |
| `icon` | `/static/modules/form_workflow/icons/workflow/httprequest.svg` |
| `execution_handler` | `modules.form_workflow.services.node_handlers.http_request_handler.HttpRequestHandler` |
| `canvas_color` | `#0EA5E9` |
| `org_restricted` | `FALSE`（企業級；安全靠白名單） |
| 入／出線上限 | `-1`／`-1` |

### 4.2 節點設定（graph 內的 `config`）

| key | 型別 | 必填 | 預設 | 說明 |
|---|---|---|---|---|
| `url` | string | 是 | | 支援變數替換；替換後必須是 `http://` 或 `https://` 開頭 |
| `method` | enum | | `GET` | `GET`／`POST`／`PUT`／`PATCH`／`DELETE`，不在清單就當 `GET` |
| `headers` | list of `{name, value}` | | `[]` | 最多 20 個；`name` 只允許 `^[A-Za-z0-9-]+$`；`value` 支援變數替換；`Host`、`Content-Length`、`Transfer-Encoding` 一律忽略 |
| `body_mode` | enum | | `none` | `none`／`json`／`raw` |
| `body` | string | | `''` | 支援變數替換。`json` 模式下不可為空、替換後必須能 `json.loads`，否則結果 `config_error`；送出時 `Content-Type: application/json` |
| `content_type` | string | | `text/plain` | 只在 `raw` 模式使用 |
| `timeout_seconds` | int | | `15` | 夾在 1～120 |
| `verify_tls` | bool | | `true` | 關掉時在 log 留 WARNING |
| `expect_json` | bool | | `true` | 嘗試把回應解析成 JSON 放進 `_json` |
| `max_response_bytes` | int | | `262144` | 夾在 1024～2097152；超過的部分截掉並標記 `_truncated` |
| `result_var` | string | 是 | | 變數前綴，`^[A-Za-z_][A-Za-z0-9_]*$` |

`validate()` 只檢查 `url` 非空、`result_var` 合法、`method` 合法，不合法拋 `ValueError`。
其餘問題都在執行期進變數。

### 4.3 結果變數（全部以 `result_var` 為前綴）

| 後綴 | 型別 | 內容 |
|---|---|---|
| `_result` | string | `ok`／`http_error`／`timeout`／`connection_error`／`not_allowed`／`config_error`／`exception` |
| `_ok` | bool | 只有 `_result == 'ok'`（狀態碼 2xx）才是 `true` |
| `_status` | int 或 null | HTTP 狀態碼；沒收到回應為 null |
| `_body` | string | 回應內容（文字），超過上限截斷 |
| `_json` | any 或 null | `expect_json` 開啟、內容未截斷且可解析時才有值 |
| `_headers` | object | 回應標頭，名稱轉小寫；最多 50 個、值最長 1000 字元；不含 `set-cookie` |
| `_duration_ms` | int | 從送出到讀完回應 |
| `_error` | string | 失敗原因（人看的），成功時空字串 |
| `_truncated` | bool | 回應是否被截斷 |
| `_url` | string | 變數替換後實際送出的網址 |

處理器**永遠回 `status: 'success'`**（理由見第二節第 2 點），`data` 放 `_result`、`_status`、`_duration_ms`、`_url` 供流程管理頁顯示。
3xx 回應歸類為 `http_error`（本節點不跟隨轉址，見 4.5），`Location` 會在 `_headers` 裡。

### 4.4 目的地白名單（平台設定，fail-closed）

兩個 `system_settings` 鍵，值都是 JSON：

| key | 型別 | 說明 |
|---|---|---|
| `http_request_allowed_hosts` | list | 全平台允許的目的地。**空清單或不存在 ＝ 任何呼叫都被拒**（`_result = not_allowed`） |
| `http_request_org_allowed_hosts` | object | `{"<企業 secure_code>": [...]}`，有列出的企業必須**同時**通過平台清單與自己的清單；沒列出的企業只看平台清單 |

清單項目的寫法：

| 寫法 | 意思 |
|---|---|
| `api.example.com` | 這個主機名，任何埠 |
| `api.example.com:8443` | 這個主機名，只有這個埠 |
| `*.example.com` | 一層以上的子網域（不含 `example.com` 本身） |
| `203.0.113.10`／`203.0.113.0/24` | IP 或網段，任何埠；也可接 `:埠` |

判定規則（寫成純函式 `is_destination_allowed(hostname, port, resolved_ips, entries) -> (bool, reason)`）：

1. 平台清單為空就直接回 `not_allowed`，**連 DNS 都不查**（設計者填的主機名不該在平台開放前就外洩到解析器）；否則把 URL 的主機名解析成全部 IP（`socket.getaddrinfo`），解析失敗 → `connection_error`
2. 主機名符合任一主機名項目，**或**任一解析出的 IP 落在任一 IP／網段項目 → 初步通過；否則 `not_allowed`
3. **私有與保留位址只能由 IP／網段項目明確放行**：解析出的每一個 IP 若是 private／loopback／link-local／multicast／reserved／unspecified
   （用 `ipaddress` 模組判斷），就必須落在某個 IP／網段項目內，否則 `not_allowed`。
   主機名項目不能放行私有位址——這是 SSRF 防護的核心，`*.example.com` 解析到 `10.0.0.5` 也會被擋
4. 埠：項目沒寫埠就不限埠；寫了埠就只放行該埠。URL 沒寫埠時 http 視為 80、https 視為 443

寫測試時注意：Python 的 `ipaddress` 把文件專用範例網段 `192.0.2.0/24`、`198.51.100.0/24`、`203.0.113.0/24` 也判成特殊位址，拿它們當「公網」測資會被第 3 條正確擋下；要測放行路徑請用真正的公網位址（例如 `93.184.216.34`）。

已知限制要寫進文件：解析 IP 與實際連線之間仍有短暫的時間差（DNS 重綁定攻擊的理論窗口），
本節點不做連線層 IP 釘選；對高敏感環境請在清單只寫 IP／網段、不寫主機名。

### 4.5 送出與讀取

- 用 `requests.request(...)`，`allow_redirects=False`（**不跟隨轉址**：跟隨等於讓對方決定下一個目的地，繞過白名單）、
  `verify=verify_tls`、`timeout=(min(5, timeout_seconds), timeout_seconds)`、`stream=True`
- 用 `iter_content` 讀取，讀到 `max_response_bytes` 就停、關閉連線、標記 `_truncated`
- 預設送出 `User-Agent: BeakPlatform-HttpRequest/1`；設計者可用 `headers` 覆蓋
- `requests` 的 `Timeout` → `timeout`；`SSLError`／`ConnectionError` → `connection_error`；其他例外 → `exception`，訊息進 `_error`，完整堆疊進 `log_error`

### 4.6 不能漏的安全細節

- **敏感標頭不進 log**：名稱符合 `authorization`、`cookie`、`proxy-authorization`、含 `token`、`secret`、`key`、`password`（不分大小寫）的，
  log 一律顯示 `<已遮蔽>`。`log_info` 開始時記 method 與 URL（**不記**標頭值）；結束時記 `_result`、`_status`、`_duration_ms`
- **回應內容進 log 最多 500 字元**
- `_url` 會含設計者放在 query string 的任何東西，文件要提醒不要把金鑰放 URL
- 本版**沒有秘密儲存**：標頭值寫在流程圖裡，能編輯流程的人都看得到。文件要明說，並建議把長期金鑰放在
  API 端只允許特定來源 IP 的設定上，或等「設定組」功能
- 處理器開頭呼叫 `is_node_allowed('HttpRequest', org_secure_code)`，回 `False` 時 `_result = not_allowed`
- 所有數字設定都夾在 4.2 表格的範圍內，不信任 graph 裡的值

### 4.7 設計器面板

欄位依序：URL（含變數選取鈕，照 `wf-accordion-messaging.js` 的 `VarPicker.open(...)` 用法）、方法下拉、
標頭（`textarea`，一行一個 `Name: Value`，收集時解析成 list）、內容模式下拉、內容 `textarea`（`none` 時隱藏）、
Content-Type（只在 `raw` 時顯示）、逾時秒數、「驗證 TLS 憑證」勾選、「解析為 JSON」勾選、回應大小上限、結果變數前綴。
面板頂端一段灰底說明：目的地必須在系統管理員設定的白名單內、結果看 `<前綴>_ok` 與 `<前綴>_status`。

### 4.8 測試清單（不連網）

純函式：

- 主機名精確比對、`*.` 萬用字元（含「不含裸網域」）、埠限制、IP 與網段比對
- 私有位址：主機名項目解析到 `10.x`／`127.x`／`169.254.x`／`::1` 全擋；同一情況加上對應網段項目就放行
- 空清單拒絕；企業清單與平台清單取交集
- 標頭名稱驗證、禁用標頭被忽略、超過 20 個被截
- 敏感標頭遮蔽
- `json` 模式內容不是 JSON → `config_error`
- 回應截斷：`_truncated` 為真且 `_json` 為 null

處理器（`requests.request` 與 `socket.getaddrinfo` 用 `monkeypatch` 換掉）：

- 200 JSON → `_ok` true、`_json` 有值、`_status` 200
- 500 → `_result` `http_error`、`_ok` false，但 handler 回傳 `status == 'success'`
- 302 → `http_error`，`_headers['location']` 存在，沒有發出第二個請求
- Timeout／ConnectionError 例外 → 對應 `_result`
- 白名單未設定 → `not_allowed` 且**沒有呼叫** `requests.request`
- `validate()`：缺 `url`、`result_var` 含連字號 → `ValueError`

### 4.9 示範與驗收

- `scripts/examples/http_mock_server.py`：純標準庫的小型 HTTP 伺服器，`GET /ping` 回 `{"pong": true}`、`POST /echo` 原樣回傳 JSON、
  `GET /status/<code>` 回指定狀態碼、`GET /slow?seconds=N` 延遲回應。無參數時印中文用法；`--host`／`--port` 可調
- `scripts/examples/provision_nodedemo_httprequest.py --org <企業代碼> --apply`：佈建一張表單（網址欄＋結果欄）與一條流程
  Start → HttpRequest（GET `${f.url}`，前綴 `http`）→ Branch（`${v.http_ok}` 為真／否）→ 兩個 OpFieldWrite 分別把 `${v.http_body}` 或 `${v.http_error}` 寫回結果欄 → End；
  冪等，重跑沿用既有表單與流程
- 端對端驗收步驟：在背景啟動 mock server（在自動化環境用 `setsid -f` 或 `nohup`，單純 `&` 可能隨 shell 結束被收掉）→ 把它的位址加進 `http_request_allowed_hosts`（本機位址屬私有範圍，**必須用 IP 寫法**才放得行）→
  佈建示範 → 重啟平台服務 → 在表單中心送單填 mock 的 `/ping` 網址 → 表單結果欄出現 `{"pong": true}`；
  再送一次填一個不在白名單的網址 → 結果欄出現 `not_allowed` 的錯誤文字，而且 mock server 的存取紀錄沒有新請求

---

## 五、交付前的檢查清單

- [ ] 第一節表格 13 層每一層都有對應變更；`grep -rn "HttpRequest"` 的結果與 `grep -rn "OsFileRead"` 的檔案集合對得上（扣掉受限節點專屬的授權相關檔）
- [ ] `node --check` 每一支改過的 JS；`python -c "import app"` 過
- [ ] `bash scripts/run_tests.sh tests/test_http_request_node.py -q` 全綠
- [ ] 種子 SQL 的 diff 只多一筆
- [ ] 重啟服務後，設計器「整合」分類出現新節點、拖出來點開有面板、填值按儲存再重新載入流程值還在
- [ ] 示範流程跑完，流程變數表（`fw_workflow_variables`）裡有全套 `http_*` 變數
- [ ] 英文介面切換後面板沒有中文
- [ ] `mkdocs build --strict` 過，新頁面在站上點得到
