# OsFileWrite 節點規格（NT-30，2026-08-31 實作完成）

對應 handler：`modules/form_workflow/services/node_handlers/os_file_write_handler.py`
設計器面板：`modules/form_workflow/static/modules/form_workflow/js/wf-node-os-file-write.js`
migration：`scripts/migrations/124_seed_file_write_node.sql`
測試：`backend/tests/test_os_file_write_node.py`
部署說明（會推 GitHub）：`docs/install/os_file_write_node.md`

姊妹節點：`OsFileRead`（NT-29）與 `OsExecutor`（NT-28），規格見 `dev-notes/OS_EXECUTOR_SPEC.md`。

---

## 一、定位：三個系統級節點的授權階梯

| 節點 | 能力 | 相對風險 |
|---|---|---|
| `OsFileRead` | 唯讀，不經 shell，鎖在允許目錄內 | 最低 |
| **`OsFileWrite`** | **只能對允許目錄內的一般檔案「追加」字串**，不經 shell、不能覆寫既有內容、不能刪檔、不能建目錄 | 中 |
| `OsExecutor` | 在平台主機執行命令 | 最高 |

**三者的 `.env` 開關與企業授權刻意各自獨立。**
`OS_FILE_READ_NODE_ENABLED` 與 `OS_FILE_WRITE_NODE_ENABLED` 是兩個變數，
`workflow_node_org_grants` 也是兩筆記錄——**可讀不等於可寫**，
`os_file_read_base_dirs` 與 `os_file_write_base_dirs` 同樣不共用。

企業可以只取得「把處理結果寫進一個 log 檔」的能力，而不必同時取得讀取
主機任意允許檔案或執行命令的權限。

### 使用者的原始需求（2026-08-31，逐字保留）

> 這是系統級專用元件，功能是對作業系統的路徑+檔案進行寫入字串的動作，特別的要求是要能
> 控制字串的最後/或前面要不要換列(勾選)。而當原本就有換列符號時，一律把最後一個字符的
> 後面的 linux/windows/Mac 的換列符都去除，只依換列(勾選)的結果插入。不變更檔案原本的
> 編碼與其他多餘動作，就只是單純的在檔案裡加資料。你可理解是在寫文字檔型的 log，
> 以及組合字串輸出，所以可能前面或後面加換列。先做這樣。

### 命名：為什麼不是改 `OpFieldWrite`

使用者一度以為這個功能該做進 `OpFieldWrite`。**那是另一回事**：
`OpFieldWrite`（`display_name='寫入欄位'`、`category='變數'`）是把字串寫進
**表單實例的欄位**（`fw_form_instances.form_data`），與 OS 檔案無關，
handler 是 `fieldwrite_handler.py`。把 OS 檔案寫入塞進去會同時破壞既有語意、
並繞過 `org_restricted` 的系統級授權（`OpFieldWrite` 不是 restricted 節點）。

---

## 二、寫入演算法（核心，不得「優化」）

對已通過授權與路徑檢查、已取得排他鎖的目標檔：

1. 取 `size_before = os.fstat(fd).st_size`
2. **從檔尾往回分塊掃（每塊 8192 bytes），數出尾端連續的換行位元組個數**。
   換行位元組定義為 `0x0A`（`\n`）與 `0x0D`（`\r`），**任意組合、任意數量**
   （涵蓋 LF / CRLF / 舊 Mac CR）。得到 `trimmed_bytes`
3. `trimmed_bytes > 0` 時 `os.ftruncate(fd, size_before - trimmed_bytes)`
4. 組 payload（2026-08-31 PF-191 起）：
   - `prefix` = 換行 **當且僅當** `(newline_smart 或 newline_before)` 為真 **且截斷後檔案非空**
   - `body` = `content`（變數替換後）以 `encoding` 編碼的位元組
   - `suffix` = 換行 **當且僅當** `newline_after` 為真

   `newline_smart`（面板「緊接上一筆，另起新行」）**預設 true，config 缺 key 也視為 true**。
   啟用時 `newline_before` 完全無作用（面板 disable＋灰化）；關閉時 `newline_before`
   恢復原本的條件式行為（為真且截斷後非空才補——**不是**無條件補，舊 graph 行為不變）。
5. `lseek` 到檔尾，**迴圈 `os.write`** 直到 payload 全部寫出，再 `fsync`

截斷點之前的既有位元組**逐位元組不變**：不重寫、不做編碼轉換、不加 BOM、
不加時間戳、不排序、不去重。

### 出廠預設（PF-191 起）就是一筆一行

出廠組合 `newline_smart=True` ＋ `newline_after=True` ＋ `newline_before=False`：

```
初始 ''      → 寫 A → 'A\n'          （截斷後為空，不加 prefix）
'A\n'        → 寫 B → 清掉 \n 得 'A' → 'A\nB\n'
'A\nB\n'     → 寫 C → 'A\nB\nC\n'
```

一筆一行、檔首無空行、檔尾單一換行，且節點**不需要知道自己是不是第一筆**
（這就是 `newline_smart` 的全部價值：prefix 的「非空才補」讓空檔與續寫都正確）。

### 舊出廠預設的坑（只在 `newline_smart=False` 時存在）

**`smart=False` ＋ `before=False` ＋ `after=True` 連續寫入會全部黏成同一行**，
因為每一次寫入都會先把「上一次留下的尾端換行」清掉：

```
初始 ''      → 寫 L1 → 'L1\n'
'L1\n'       → 寫 L2 → 清掉 \n 得 'L1' → 'L1L2\n'      ← 黏在一起
```

2026-08-31 PF-191 之前這正是出廠預設，「要一筆一行必須勾前面」的舊敘述
（CLAUDE.md／面板提示／部署文件）已隨改版更新。三個都不勾＝字串直接接在
檔案最後一個字後面（組合字串用），這個用法不受改版影響。

### 空檔的特例

prefix（不論來自 `newline_smart` 或 `newline_before`）在「檔案為空」或
「截斷後變空」時**不插入換行**，否則檔案開頭會多一個空行。
已由測試涵蓋（原檔 `b''` 與 `b'\n\n\n'` 兩個案例）。

### content 自己的換行不處理

`content` 內含的換行原樣寫入；`content` 尾端自帶換行而 `newline_after` 也勾時，
結果會有兩個換行。使用者的規則只約束「檔案既有內容」的尾端。
**這一點列入待確認**（第八節）。

---

## 三、三道護欄

| # | 護欄 | 失效時的行為 |
|---|---|---|
| 1 | `.env` 的 `OS_FILE_WRITE_NODE_ENABLED` | `not_authorized` |
| 2 | 企業授權 `workflow_node_org_grants`（經 `node_grant_service.is_node_allowed`） | `not_authorized` |
| 3 | `workflow_node_definitions.is_active`（出廠 **FALSE**） | 節點不出現在設計器 |

護欄 2 走的是 2026-08-31 通用化後的節點授權機制（PF-185），
**三個消費點自動涵蓋**，本節點不需要自己寫任何企業判斷：

| 消費點 | 位置 | 本次實測結果 |
|---|---|---|
| 設計器面板可見性 | `api/workflows.py::get_node_definitions()` | 未授權企業看不到（BELUGA / LION 皆 0 命中） |
| graph 寫入（含 publish，7 個入口） | `api/workflows.py` ×4、`api/workflow_routes.py` ×2、`api/mappings.py` | 未授權企業 POST 含 OsFileWrite 的 graph → **403** |
| handler 執行期 | `os_file_write_handler.py::_check_authorized()` | 直接改 DB 繞過前兩層仍被擋 → `not_authorized` |

出廠授權只有系統企業（migration 124 的最後一段 `WHERE organizations.is_system_org = TRUE`）。

### base_dir 三層交集

平台層 `system_settings.os_file_write_base_dirs`（list，**預設 `[]` 表示全部拒絕**）
∩ 企業層 `os_file_write_org_base_dirs`（dict，key 為 org secure_code，
**企業無設定時不收窄平台清單**）∩ 節點 config 的 `base_dir`。

所有路徑先 `os.path.realpath()` 再用 `os.path.commonpath()` 比對。

### 目標檔的路徑解析比 OsFileRead 更嚴（因為要寫）

```
abs_path = requested if isabs else join(node_base, requested)
parent   = realpath(dirname(abs_path))      # 解析中間層 symlink
name     = basename(abs_path)               # 空 / '.' / '..' 一律拒絕
final    = join(parent, name)               # 刻意不 realpath 最後一段
```

- **最後一段刻意不 realpath**，否則等於跟著 symlink 走。改用
  `os.path.islink(final)` 判斷，**是 symlink 就拒絕**（不論指向 base_dir 內或外）
- 已存在時 `os.lstat()` + `stat.S_ISREG()`：目錄、FIFO、socket、device 一律拒絕
- 開檔用 `os.O_RDWR | os.O_NOFOLLOW`（`create_if_missing` 時再 `| os.O_CREAT`，
  模式 `0o640`），`O_NOFOLLOW` 是 TOCTOU 的第二道；`ELOOP` 轉成 `path_denied`
- 開檔後**再用 `os.fstat(fd)` 確認 `S_ISREG`**（fd 上的檢查才沒有空窗）
- **v1 不自動建立目錄**：父目錄不存在 → `path_denied`

---

## 四、結果語彙：全部回 `status='success'`

`_result` 只有三個值：**`ok` / `exception` / `timeout`**，
三者**一律**回 `{'status': 'success', ...}`。

**理由（這是本節點最重要的安全性質）**：`FwNodeExecutionQueue.fail()` 會
**無條件重試 3 次**，而寫檔有副作用，被平台自動重跑會寫進重複資料。

**所以判斷本節點成敗不能看 queue 的 status。**
真相在流程變數 `<result_var>_result` 與 `fw_node_execution_logs`（level=ERROR）。
2026-08-31 端對端實測（真實 executor 派工）：

```
queue f7ec6a84... status=SUCCESS retry_count=0  → 流程變數 e2e_result="ok"
queue 38a18c26... status=SUCCESS retry_count=0  → 流程變數 e2e_result="exception"
                                                   e2e_error_kind="path_denied"
```

`OsFileRead` 與 `OsExecutor` 的四分法（多一個 `dispatched`）在此只用得到三個，
因為 OsFileWrite **v1 同步完成、不派工到 OS**。

> **警告**：若日後改成非同步而回 `waiting` / `pending`，
> `workflow_executor.py` 內**兩處**節點型別清單都必須加上 `OsFileWrite`。
> 漏掉的話節點會永遠卡在 WAITING 而且不報錯（`Converge` 就是這樣死的，
> 2026-08-30 OsExecutor 上線時又踩過一次）。

### error_kind 清單（機器可讀，不包翻譯函式）

`not_authorized`／`bad_config`／`path_denied`／`file_not_found`／
`permission_denied`／`file_too_large`／`encode_error`／`lock_timeout`／
`io_error`／`runtime_error`

---

## 五、config 與流程變數

### config

| key | 型別 | 預設 | 說明 |
|---|---|---|---|
| `base_dir` | string 必填 | — | 節點層允許根目錄，**不做變數替換** |
| `file_path` | string 必填 | — | 支援 `${...}`，替換後才做路徑驗證 |
| `content` | string 必填 | — | 支援 `${...}`；**空字串合法**（等同只整理檔尾） |
| `newline_smart` | bool | `true` | 「緊接上一筆，另起新行」。啟用時 `newline_before` 無作用；**缺 key＝啟用**（PF-191） |
| `newline_before` | bool | `false` | 僅 `newline_smart=false` 時生效 |
| `newline_after` | bool | `true` | |
| `create_if_missing` | bool | `true` | |
| `encoding` | string | `utf-8` | 見第六節的限制 |
| `max_file_bytes` | int | 64MB | 硬上限 512MB。判定用 `size_before + len(payload)`（保守） |
| `lock_timeout_ms` | int | 5000 | 硬上限 60000 |
| `result_var` | string 必填 | — | `^[a-zA-Z_][a-zA-Z0-9_]{0,63}$` |
| `stop_after` | bool | `false` | 語意同 OsFileRead |

### 寫出的流程變數

`<result_var>` 加上：`_result`／`_error_kind`／`_file_path`／`_bytes_written`／
`_trimmed_bytes`／`_size_before`／`_size_after`／`_created`。

**`content` 不寫進流程變數**（可能很長）；只在 node log 的 `content_head`
留前 2048 字供事後稽核。

### skip_advance

`stop_after=true` → `filewrite_stop_after`；沒有出邊 → `filewrite_no_outgoing`。
兩者都走 `skip_advance`（回 `selected_edges: []` 沒有用——空 list 是 falsy，
會落到「取所有出邊」）。

---

## 六、編碼決策（fail-closed）

- `content` 一律 `errors='strict'`。編碼失敗 → `encode_error`，**檔案完全不動**。
  **不用 `errors='replace'`**——把使用者的字寫成問號等於靜默毀損資料
- **明確拒絕 UTF-16 / UTF-32 家族**（`bad_config`）：第二節的尾端換行掃描是
  位元組級的（`0x0A`/`0x0D`），這在 ASCII 相容編碼（utf-8 / big5 / cp950 /
  latin-1 / gbk）正確，在 UTF-16/32 會誤判並毀損檔案
- codec 查得到但不是文字編碼（`rot13`、`base64`）→ `bad_config`
  （`str.encode()` 會拋 `LookupError`，特別攔下來歸類，否則會落到 `runtime_error`）
- 寫入用的換行是 `'\n'.encode(encoding)`，**v1 固定 LF**，不偵測既有檔案風格
  （空檔無從判斷，且平台跑 Linux）

**注意 Big5 收錄了日文假名、希臘字母與西里爾字母**——寫「無法編碼」的測試
案例時拿那些字會編得過去而讓測試失效，要用 emoji 或 CJK 擴充 B 區的字。
（本 session 第一版測試就踩過。）

---

## 七、併發

`fcntl.flock(fd, LOCK_EX | LOCK_NB)` 非阻塞重試（每 50ms），逾時 `lock_timeout_ms`
→ `_result='timeout'` + `lock_timeout`。**不用阻塞式 flock**（沒有逾時會把節點卡死）。
收尾一律在 `finally` 中 `LOCK_UN` 後 `os.close(fd)`。

2026-08-31 實測：5 個 OS 行程各寫 20 筆（每筆 208 bytes）到同一個檔，
結果 100 行、0 交錯、0 重複、0 漏寫、檔尾單一換行。

**跨主機（NFS）不保證**：`flock` 在部分 NFS 實作上是 no-op。
base_dir 一律設在本機檔案系統。

---

## 八、待 Ethan 裁決 / 已知限制

1. **命名**：已定案 `OsFileWrite`（Ethan 2026-08-31，系統級節點一律 `Os` 前綴，
   migration 129 完成改名）
2. **換行出廠預設**：已定案（PF-191，2026-08-31）——不改 before/after 的預設，
   改為新增 `newline_smart`（預設啟用）接管 prefix，見第二節
3. **`content` 尾端自帶換行 + `newline_after` 也勾** → 會有兩個換行。
   已定案維持現況（PF-191）：content 自身的換行原樣寫入，保留設計者刻意留空行的能力；
   規則只約束「檔案既有內容」的尾端
4. **v1 不做的**：不自動建目錄、不支援覆寫模式、不支援指定寫入位置、
   不做 log rotation、不偵測既有檔案的換行風格（固定 LF）
5. **實體層**：`max_file_bytes` 只擋單一檔案大小，**不擋磁碟寫滿**。
   磁碟滿時 `os.write` 拋 `OSError` → `io_error`，流程不會崩，但要靠主機端監控
6. **`_write_all` 的部分寫入**：`os.write` 中途失敗時檔案可能留下半行。
   v1 接受（log 追加場景），沒有做 write-to-temp + rename（那會改變 inode 與權限，
   且對「追加」語意不成立）

---

## 九、驗收記錄（2026-08-31）

原始輸出：`/opt/tmp/verify/20260831-filewrite.log`

| # | 項目 | 方法 | 結果 |
|---|---|---|---|
| 1 | 尾端換行 truncate 全矩陣（10 種檔尾） | handler harness，逐位元組比對 | 全過 |
| 2 | `newline_before` × `newline_after` 四種組合 | 同上 | 全過 |
| 3 | 既有位元組不變（含 0x01~0xFF 全位元組） | md5 前綴比對 | 相同 |
| 4 | 非 UTF-8（Big5 / 任意二進位） | 前綴 bytes 比對 | 不變 |
| 5 | 路徑逃逸（`../`、絕對路徑、base_dir 外、目錄、FIFO、symlink ×2） | 同上 | 全部 `path_denied`，目標檔未被建立或改動 |
| 6 | 企業授權三層（面板 / graph 寫入 / handler） | curl + harness | 三層皆擋（BELUGA / LION 403 與 `not_authorized`） |
| 7 | `.env` 開關關閉 / `=0` | harness | `not_authorized` |
| 8 | 併發 5 行程 × 20 次 | 真實多行程 | 100 行、0 交錯 |
| 9 | queue 綠燈但流程變數記錄失敗 | 真實 executor 派工 | queue SUCCESS / retry 0，流程變數 `exception` + `path_denied` |
| 10 | 設計器面板（chrome-devtools 實測） | 勾選存檔 → 重載讀回 | 11 欄位往返一致，checkbox 未被撐成全寬（FRONT-05） |

harness 檢查項共 99 條全過（尾端換行、編碼、路徑、授權、語彙、skip_advance、變數替換）。
