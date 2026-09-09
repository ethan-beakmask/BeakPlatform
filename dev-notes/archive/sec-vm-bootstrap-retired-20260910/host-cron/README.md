# host-cron — .20 sec-vm 主機層排程

這裡放的是**不在 docker-compose 內、但 sec-stack 少了會出事**的主機層腳本副本。
它們的執行位置在 .20 主機上，本目錄僅為權威文件副本（與 .16 其他素材同一原則）。

| 檔案 | .20 上的實際位置 | 用途 |
|---|---|---|
| `secstack-rotate-logs` | `/etc/cron.hourly/secstack-rotate-logs` | Suricata eve.json 與 ModSec audit.log 的每小時輪替 |

（`secstack-canary` 已於 2026-09-07 隨合成演習機制一併移除，
備份在 `.20` 與 `.16` 的 `/opt/tmp/backup/od-canary-retire-20260907/`。）

## 為什麼要單獨記一筆

2026-08-08 查出：這支腳本**從 2026-05-13 起每小時都在執行、每小時都在第一行失敗**，
沒有任何人知道，直到 eve.json 長到 554MB / 44.7 萬行才被發現。

根因鏈：
1. 舊版第一行呼叫 `logrotate /etc/logrotate.d/secstack-research` 處理 ModSec audit.log
2. 該設定帶 `su messagebus lxd`，降權後要 stat `/home/ethan/sec-vm-bootstrap/waf/log/audit.log`
3. `/home/ethan` 是 `drwxr-x---`(750) — 非 ethan 的 uid 穿不過 → Permission denied → 非零退出
4. 腳本有 `set -euo pipefail` → 整支中止 → **後面的 Suricata 段從未執行**

現版修法：不再依賴 logrotate，改由腳本以 root 直接 copy + truncate；
移除 `set -e`，兩段各自收斂錯誤；失敗寫 `/opt/tmp/sec-vm-rotate-logs.log`，
成功寫 heartbeat `/opt/tmp/heartbeat/secstack-rotate-logs`。

## 已知缺口

heartbeat 寫在 .20 本機，**目前沒有消費者**。要做到「失敗會有人知道」，
還需要在 .16 端加一個檢查該檔案時間戳的排程。

## 為什麼用 copy + truncate 而不是 rename

inode 不變，不會重讀整個舊檔；若改用 rename，Vector 需等 glob 掃描
（預設最長 60 秒）才接上新檔，中間的事件會漏。

**但「沒有重新發現新檔的空窗」這句是錯的**（2026-09-07 實測更正）。
Vector log 每小時 :17 固定出現這一對：

```
03:17:02 Stopped watching file. file=/var/log/suricata/eve.json reached_eof="true"
03:17:06 Found new file to watch. file=/var/log/suricata/eve.json
```

也就是 truncate 後 Vector 是**當成新檔重新開始**，中間有 3~4 秒空窗，
**truncate 當下尚未被讀走的那幾行永久遺失**。

這件事平常不明顯（真實事件不會剛好落在 :17 那一秒），但它讓同樣掛在
`/etc/cron.hourly/` 的合成演習 canary 幾乎全滅——run-parts 按字母序先跑
`secstack-canary`、不到一秒後跑本腳本，canary 寫進去的那行當場被清掉。
近 7 天 336 次演習只有 43 次進得了 ClickHouse（通過率 13%）。

**canary 已於 2026-09-07 廢除，這個競態 Ethan 決定不修**。若日後新的演習
仍要在 `.20` 上發動，記得把發動時間與本腳本錯開（本腳本可從 `cron.hourly`
移到 `/etc/crontab` 指定分鐘），否則會重演同一件事。
完整脈絡見 `.16` 的 `dev-notes/SEC_STACK_ARCHITECTURE.md`
「合成演習（canary）已於 2026-09-07 廢除」一節。
