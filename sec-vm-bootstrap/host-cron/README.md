# host-cron — .20 sec-vm 主機層排程

這裡放的是**不在 docker-compose 內、但 sec-stack 少了會出事**的主機層腳本副本。
它們的執行位置在 .20 主機上，本目錄僅為權威文件副本（與 .16 其他素材同一原則）。

| 檔案 | .20 上的實際位置 | 用途 |
|---|---|---|
| `secstack-rotate-logs` | `/etc/cron.hourly/secstack-rotate-logs` | Suricata eve.json 與 ModSec audit.log 的每小時輪替 |

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

inode 不變，Vector 的 file source 偵測到 `size < offset` 會自行 reset 到 0 繼續讀，
沒有「重新發現新檔」的空窗，也不會重讀整個舊檔。
若改用 rename，Vector 需等 glob 掃描（預設最長 60 秒）才接上新檔，中間的事件會漏。
