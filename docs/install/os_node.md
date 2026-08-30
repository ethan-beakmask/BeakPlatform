# 主機側節點（OS 命令 / 檔案讀取）的部署需求

**這兩個都是選用功能，出廠預設全部關閉。** 沒有要用的話，本頁整份可以略過，
平台其餘功能不受影響。

| 節點 | 做什麼 | 風險等級 |
|---|---|---|
| **OS 命令**（`OsExecutor`） | 在平台主機上執行流程設計者指定的命令 | **等同把主機 shell 開給流程設計者** |
| **檔案讀取**（`FileRead`） | 唯讀讀取指定目錄底下的檔案（整份 / 檔頭 / 檔尾 / 關鍵字前後） | 低一階：不經 shell、唯讀、鎖在允許目錄內 |

這份文件寫給**安裝與維運人員**。

---

## 一、先讀這段：這兩個節點的授權是各自獨立的

**它們的開關與企業授權刻意分開，不要當成一組一起開放。**

大部分「只想讀 log 判斷狀態」的需求用「檔案讀取」就夠了，不必開「OS 命令」。
把兩個一起開等於白白放大授權面。

### 為什麼「OS 命令」需要這麼慎重

節點設定存在流程圖裡，而流程圖可由**企業管理員或持有流程設計角色的人**修改。
如果不設閘門，等於「任一租戶的管理員 → 平台主機 shell」，而他們並不是平台的
系統管理者。

**平台刻意不做命令黑白名單。** `sh -c` 間接呼叫、腳本層層包裹、自寫執行檔——
任何名單都繞得過去，做了只會產生虛假的安全感。**OS 的穩定由 OS 管理員負責**
（cgroup、quota、sudoers、防毒、備份），平台只負責「誰能用」這件事。

---

## 二、啟用「OS 命令」節點

四個步驟，缺一不可。少任何一步，節點都不會執行（而且是明確拒絕、不是靜默失敗）。

### 1. 設定 `.env`

```bash
# <安裝目錄>/.env
OS_NODE_ENABLED=1

# 選填：同一企業同時執行中的 OS 命令節點數上限（預設 3）
# 超過上限的節點會自動排隊等待，不會失敗
OS_NODE_MAX_CONCURRENT_PER_ORG=3
```

改完必須**重新啟動流程執行服務**才會生效。

### 2. 讓節點在設計器裡出現

出廠時節點定義是停用狀態：

```sql
UPDATE workflow_node_definitions SET is_active = true WHERE node_type = 'OsExecutor';
```

### 3. 指定允許的企業

企業授權統一存在 `workflow_node_org_grants`。安裝後預設只有系統企業獲得授權；
客戶企業即使有流程設計權限，也看不到、存不了、發行不了未授權節點。

**首選：用管理頁授權。** 以系統管理員登入後，左側選單「權限管理 → 節點授權」
（網址 `/node-grants/`）是一張授權矩陣：**每一列是一家企業，每一欄是一種受限節點型別**，
勾選即授權、取消勾選即撤銷（撤銷會要求二次確認）。
節點欄標題與「批次」列固定在表格最上方，系統預設企業列緊接其下也固定，
所以企業數量再多、往下捲動時仍看得到自己在設定哪個節點。
每個節點欄的「批次」列有「全部授權」「全部撤銷」，一次套用到所有企業。
已授權的格子會顯示授權者與授權時間。此頁只有系統管理員進得去，
企業管理員無法替自己企業授權。

沒有圖形介面時，也可以用維運工具授權：

```bash
venv/bin/python scripts/node_grant.py list
venv/bin/python scripts/node_grant.py grant OsExecutor <企業識別碼或企業代碼>
venv/bin/python scripts/node_grant.py revoke OsExecutor <企業識別碼或企業代碼>
```

也可以用 SQL 授權：

```sql
INSERT INTO workflow_node_org_grants (
    secure_code, node_type, org_secure_code, granted_by_name,
    created_at, updated_at, is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'OsExecutor',
    '<企業識別碼>',
    'manual_sql',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1
      FROM workflow_node_org_grants
     WHERE node_type = 'OsExecutor'
       AND org_secure_code = '<企業識別碼>'
       AND is_deleted = FALSE
);
```

**這兩道閘門在每次執行時都會重新檢查。** 把開關關掉或撤銷企業授權之後，
流程圖裡已經存在的節點會立刻停止執行；同時設計器可見性、graph 儲存與發行也會拒絕未授權企業。

### 4. sudoers（只有「交給 OS 執行」模式需要）

節點有兩種執行方式，只有後者需要 sudoers：

| 模式 | 行為 |
|---|---|
| 等待結果（預設） | 平台直接執行命令並等它結束，取得輸出與離開代碼 |
| 交給 OS 執行 | 把命令交給系統的服務管理員（systemd）在背景執行，**這次不等結果** |

「交給 OS 執行」需要三條 sudoers 規則（`<執行帳號>` 換成流程執行服務的 OS 帳號）：

```
<執行帳號> ALL=(root) NOPASSWD: /usr/bin/systemd-run --uid=* --unit=bp-* *
<執行帳號> ALL=(root) NOPASSWD: /usr/bin/systemctl stop bp-*
<執行帳號> ALL=(root) NOPASSWD: /usr/bin/systemctl reset-failed bp-*
```

> ### 這裡有一個必須知情的風險
>
> 第一條的萬用字元允許以 root 身分建立任意的系統服務單元，**實質上等於 root**。
> 這與「OS 命令」節點本身的權限等級一致（它本來就能執行任意命令），
> 不算額外擴大，但有一個推論：
>
> **流程執行服務應該使用專用的 OS 帳號，不要與人類使用者的帳號共用。**
> 否則這三條規則等於把 root 送給那個人類帳號。

命令本身仍以**執行帳號**的身分執行，不會自動變成 root；設計者要 root 得在自己的
命令裡明確使用 `sudo`。

---

## 三、啟用「檔案讀取」節點

同樣是四步，但**開關與企業授權與「OS 命令」完全分開**。

```bash
# <安裝目錄>/.env
FILE_READ_NODE_ENABLED=1
```

```sql
UPDATE workflow_node_definitions SET is_active = true WHERE node_type = 'FileRead';

-- 允許使用此節點的企業；安裝後預設只有系統企業獲得授權
INSERT INTO workflow_node_org_grants (
    secure_code, node_type, org_secure_code, granted_by_name,
    created_at, updated_at, is_deleted
)
SELECT
    substr(md5(random()::text || clock_timestamp()::text), 1, 32),
    'FileRead',
    '<企業識別碼>',
    'manual_sql',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1
      FROM workflow_node_org_grants
     WHERE node_type = 'FileRead'
       AND org_secure_code = '<企業識別碼>'
       AND is_deleted = FALSE
);

-- 全平台允許讀取的根目錄（預設空 = 讀不到任何檔案）
UPDATE system_settings SET value = '["/var/log/myapp", "/srv/exports"]'
 WHERE key = 'file_read_base_dirs';

-- 選填：再針對個別企業收窄成子集合（沒設定該企業就沿用上面的全平台清單）
UPDATE system_settings SET value = '{"<企業識別碼>": ["/var/log/myapp"]}'
 WHERE key = 'file_read_org_base_dirs';
```

等效的維運工具命令：

```bash
venv/bin/python scripts/node_grant.py grant FileRead <企業識別碼或企業代碼>
venv/bin/python scripts/node_grant.py revoke FileRead <企業識別碼或企業代碼>
```

### 允許目錄是三層取交集

```
平台允許目錄  ∩  該企業允許目錄  ∩  節點設定的目錄  →  實際可讀範圍
```

路徑檢查會先解開符號連結再判定，所以在允許目錄裡放一個指向 `/etc/shadow` 的
符號連結是無效的。

**平台不會自動把 OS 命令節點的輸出目錄加進允許清單。** 想讓流程用「檔案讀取」
把 OS 命令的完整輸出讀回來（見第五節），要自己把 `/opt/tmp/osnode` 加進
`file_read_base_dirs`。

---

## 四、設計流程的人必須知道的三件事

這三件事平台修不了，只能靠設計者自己處理。**請轉達給流程設計者。**

1. **離開代碼 0 不等於工作完成。**
   `nohup xxx &` 或 `ssh host 'cmd &'` 會立刻回 0，節點判定為成功，但工作其實還在跑。
   節點描述的是「這一次執行的生命週期」，不是「工作是否真的完成」。
   要判斷後者，請讓下一個節點去讀檔案或查詢狀態，或讓命令自己回報給平台。

2. **逾時的收尾會連坐殺掉背景子孫。**
   逾時時平台預設會把整個行程群組收乾淨，所以命令裡用 `&` 起的常駐程序會在那一刻
   一起結束。這是刻意的——不收的話平台等於自己養殭屍行程。
   需要改變這個行為時，節點設定有「逾時處理方式」可選。

3. **`ssh` 逾時只殺得掉本地的連線，遠端命令會繼續跑。**
   這是 SSH 協定的性質。跨主機的長時間作業請改用「命令回報給平台」的做法。

還有一個節點設定要注意：勾了**「這一步做完就結束這條分支」**之後，
節點執行完就不會推進任何後續節點。用在並行流程的某一條分支上是對的；
但如果整條流程只有這一條路徑，流程實例會**停在執行中、永遠不會結束**。
需要結束整個流程請接「結束」節點，不要靠這個選項。

另外，**填表人填的值一律會被引號化後才代入命令**，所以表單欄位不可能被拿來注入
額外的命令。設計者確實需要讓某個變數帶多個參數時，要在變數後面明確加上 `!raw`
標記——那是明確標示的例外，用之前請確認該變數不會被外部使用者控制。

---

## 五、輸出檔與定期清理

「等待結果」模式的完整輸出會寫成檔案，流程變數與執行紀錄裡只留摘要：

```
/opt/tmp/osnode/<日期>/<節點執行識別碼>.out    標準輸出全文
/opt/tmp/osnode/<日期>/<節點執行識別碼>.err    標準錯誤全文
```

執行紀錄裡會記下這兩個檔的路徑與內容的 sha256，出問題時照著路徑去讀即可
（也可以用「檔案讀取」節點在流程裡直接讀回來，前提是第三節那個允許目錄有設）。

「交給 OS 執行」模式沒有輸出檔，輸出會進系統日誌：

```bash
journalctl -u bp-<節點執行識別碼>
```

> 系統日誌有速率限制，**大量輸出會被靜默丟棄**。輸出量大的命令請自己在命令裡
> 重導向到檔案，不要依賴系統日誌。

### 事後查詢「交給 OS 執行」的最終結果

```bash
systemctl show bp-<節點執行識別碼> -p Result -p ExecMainStatus -p ActiveState
```

**注意：只有失敗的單元查得到。** 系統會自動回收成功結束的暫時性單元，
查詢那些單元只會拿到預設值。要確認成功與否請看系統日誌。

### 建議的清理排程

```bash
# 每天清一次：輸出檔與失敗單元的殘留記錄（寫進 /etc/crontab）
10 4 * * * <執行帳號> flock -n /tmp/os-node-cleanup.lock <安裝目錄>/venv/bin/python <安裝目錄>/scripts/cron/os_node_cleanup.py >> /opt/tmp/<安裝目錄名>-cron-os_node_cleanup.stderr.log 2>&1
```

腳本做兩件事：刪掉超過保留期的輸出檔（正常 7 天、例外與逾時 30 天，
保留期依該次執行的結果自動區分），以及 `systemctl reset-failed 'bp-*'`
清掉失敗單元的殘留記錄。

```bash
# 先看會刪什麼再實際執行
<安裝目錄>/venv/bin/python <安裝目錄>/scripts/cron/os_node_cleanup.py --dry-run
```

腳本自己的執行紀錄寫在 `/opt/tmp/<安裝目錄名>-cron-os_node_cleanup.log`，
正常完成會更新 `/opt/tmp/heartbeat/os_node_cleanup.ok`。

---

## 六、流程被中止時會發生什麼

流程用「取消/終止」模式結束時：

| 情況 | 行為 |
|---|---|
| 等待結果模式，命令還在跑 | 命令連同它的子孫行程一起被收掉 |
| 交給 OS 執行，預設 | 對應的系統服務單元被停止（含命令內自行提權出來的 root 子行程） |
| 交給 OS 執行，節點設為「流程取消後仍繼續」 | **不會停止**，作業會自己跑完 |

最後一種適合「這件事一旦送出就該做完」的作業。設計器上該選項有明確標示。

---

## 七、常見問題

| 症狀 | 原因 |
|---|---|
| 設計器左側工具列找不到這兩個節點 | 節點定義還是停用狀態（第二節第 2 步） |
| 節點執行完是「成功」，但結果變數寫著 `exception` / `not_authorized` | 開關未啟用，或該企業沒有節點授權。這是刻意的：授權拒絕不重試 |
| 結果變數寫著 `exception` / `path_denied` | 檔案不在允許目錄內，或路徑解開符號連結後跑到允許範圍外 |
| 節點卡在等待很久才執行 | 同企業同時執行的數量到達上限，正在排隊（見第二節的併發設定） |
| 改了 `.env` 沒有效果 | 流程執行服務沒有重新啟動 |

> **重新啟動流程執行服務會中止當下正在執行的節點。** 重啟前先確認沒有流程在跑。

---

## 八、不需要安裝的東西

- **不需要 `at`。** 平台只用系統的服務管理員（systemd）派工。
  `at` 的工作行程掛在 `atd` 自己的行程群組底下，收尾時會誤傷整台機器上的其他排程，
  已明確排除。
- **不需要額外的資源限制設定**（記憶體/檔案大小上限之類）。
  命令用掉多少資源是 OS 管理員該管的事，平台不在節點層模擬。
