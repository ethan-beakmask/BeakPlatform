---
title: 送出第一筆事件
audience: ORG_ADMIN
order: 30
visible_user_types: [ORG_ADMIN]
produces:
  - 資安案件
covers:
  - scripts/examples/od_intake_send_event.py
  - scripts/examples/provision_od_intake_for_org.py
  - modules/open_defense/api/intake.py
---

# 送出第一筆事件

## 一道指令建好整條鏈路

不想一步步點的話，專案內附一支建置腳本，把[逐步建置](02_build_it.md)的六件事一次做完，
而且**重複執行不會產生重複資料**。

這支要在**平台主機上**執行（它直接連平台資料庫，不是打 API），
在專案根目錄下、載入平台環境變數之後跑：

```bash
set -a && source .env && set +a
venv/bin/python scripts/examples/provision_od_intake_for_org.py --org your-company.example --apply
```

先不加 `--apply` 跑一次就是預演，只印出「會做什麼」不寫入，確認無誤再加上去。

`--org` 填企業的網域名稱（登入頁輸入的那個 `@` 後面的網域，例如 `your-company.example`）
或企業識別碼。填錯時腳本會直接報錯並列出可用的企業，不會亂寫資料。

它會建立：資安分類（識別碼前綴正確）、表單範本、最小處置流程、配對並發行、
一條全部事件都適用的路由規則、一把勾好 `od_intake` 的 API Key。
執行完會印出 key_id 與 secret，**secret 只印這一次**。

其他參數：

| 參數 | 用途 |
|---|---|
| `--source-system` | 寫進金鑰白名單的來源系統名稱，可重複指定，預設 `elk` |
| `--skip-api-key` | 企業已經有金鑰時跳過建立 |
| `--assignee-role` | 簽核角色，預設資安人員角色 |
| `--force` | 表單或流程已存在時覆寫內容並重新發行 |

## 送出事件

另一支範例程式負責送事件，只用 Python 標準函式庫，不需要安裝任何套件，
可以直接複製到你的分析主機上。

`BP_BASE_URL` 就是你平時登入平台的網址，**去掉最後的頁面路徑、保留前綴那一段**——
例如登入後網址列是 `https://platform.example.com/beakplatform/dashboard`，
那 `BP_BASE_URL` 就是 `https://platform.example.com/beakplatform`。

```bash
export BP_BASE_URL=https://platform.example.com/beakplatform
export BP_API_KEY_ID=ak_xxxxxxxx
export BP_API_KEY_SECRET='建立金鑰時顯示的一次性 secret'

python3 scripts/examples/od_intake_send_event.py \
  --source-system elk \
  --event-class web_activity \
  --severity 4 \
  --title "後台登入暴力破解" \
  --rule-id ELK-4625-BURST \
  --actor-ip 203.0.113.42 \
  --target-host portal.example.com \
  --target-url /admin/login \
  --summary "10 分鐘內 200 次登入失敗，來源單一 IP"
```

成功會印出案件識別碼。想先確認送出去的內容與簽章，加 `--dry-run`；
要改用 curl 或其他語言實作，加 `--print-curl` 取得等價指令。

真正接上自家分析系統時，通常是把查詢結果整理成事件 JSON，再用 `--event-file` 送：

```bash
python3 scripts/examples/od_intake_send_event.py --event-file event.json
```

`--event-file -` 則是從標準輸入讀，方便接在自己的查詢指令後面。

!!! note "要用其他語言自己實作，不透過這支程式"
    `--help` 列出全部參數與退出碼，`--dry-run --print-curl` 會印出**這一筆事件**
    完整的簽章素材與等價 curl 指令（headers、簽章算法、body 都在裡面），
    照著翻成任何語言都可以。程式本身只有一個檔案、沒有第三方依賴，
    直接讀它比讀規格書快。

## 確認三個地方

!!! abstract "作業：確認案件真的進來了"
    **MENU**：開放防禦 ／ 儀表板

    1. 看「今日收到事件」是否 +1
    2. 「最近事件」清單是否出現剛才那筆

!!! abstract "作業：確認案件可以被處理"
    **MENU**：開放防禦 ／ 資安案件處置中心

    1. 看上方統計是否顯示進行中案件
    2. 把「僅我可簽核」按掉
    3. 點左側案件，右側出現內容與決策按鈕

!!! warning "統計有數字、清單卻說「目前沒有輪到您簽核的案件」"
    這不是故障。處置中心預設只列**輪到你簽核**的案件，
    而你的帳號可能沒有被指派到流程裡的簽核角色。

    把「僅我可簽核」按掉就會看到全部案件。要讓它在預設檢視就出現，
    到「角色管控 ／ 權限管理中心」把你的帳號配上該簽核角色。

簽核任務本身會出現在「表單流程 ／ 待處理」，那是實際執行處置的入口。

## 事件送成功但案件沒增加

有兩種情況是**正常**的，不要當成故障：

| 回應 | 意思 |
|---|---|
| `duplicate: true` | 這個 `correlation_id` 收過了。冪等設計，重送不會重複開案 |
| 成功但案件數沒變 | 被聚合併入既有案件了——同一條偵測規則、同一個來源 IP、同一個目標，短時間內視為同一起事件 |

測試時想每次都開新案，把 `--correlation-id`、`--rule-id`、`--target-host` 都換掉。
