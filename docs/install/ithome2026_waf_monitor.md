# Integrated-WAF：熱備健康監看（流程自動巡檢 + 看門狗）

這份文件接續 [WAF 節點熱備切換](ithome2026_waf_standby.md)。熱備做好之後還缺一件事：
**誰來發現現役節點死了。**

2026 年 9 月一次實際事故裡，現役防禦節點的網路靜默死亡——虛擬機還活著、主控台正常，
但不回 ARP、不發任何封包。對外服務中斷了約 12 小時才被人發現，而切換本身只花 15 秒。
偵測的價值遠大於切換速度。

本文的作法**不寫 crontab 巡檢腳本**，而是把巡檢做成平台上的一張表單流程：
每一輪檢查都留在流程執行記錄裡，告警與人員決策留在同一張單上，事後可稽核。

---

## 一、三個元件

| 元件 | 位置 | 做什麼 |
|---|---|---|
| `monitor_probe.sh` | `Integrated-WAF/` | 探測一次，把判定寫成 stdout 單行，並更新 heartbeat |
| 「WAF 熱備健康監看」表單流程 | 平台（node展覽館分類） | 常駐迴圈：每 N 分鐘呼叫探測、計數、告警、決策、切換 |
| `waf_monitor_watchdog.py` | `scripts/cron/` | 每 5 分鐘檢查 heartbeat，監看流程自己死掉時發 Telegram |

第三個元件是必要的：**監看流程無法監看自己**。流程若因故停住（例如重啟流程執行器時
剛好撞上節點執行中），它不會叫，症狀跟「一切正常」完全一樣。看門狗只做一件事——
確認巡檢還在跑——所以它簡單到不太可能自己壞掉。

---

## 二、探測怎麼判定

`monitor_probe.sh` 依序做四件事，輸出一行：

```
TS=2026-09-12 20:40:35 STATE=OK EXT=302 INT=404 GW=ok
```

| 步驟 | 判定 |
|---|---|
| 1. 停止旗標 | 旗標檔存在 → `STATE=STOP`（流程會據此正常結束） |
| 2. 自我隔離 | 閘道與兩台節點管理 IP **全部** ping 不到 → `STATE=ISOLATED` |
| 3. 對外 | `dig` 取 Cloudflare IPv4 後用 `--resolve` 打對外網址，期望 3xx/2xx |
| 4. 對內 | 打服務 IP 的 WAF 埠，**`000` 才算死**（404 代表節點活著、只是根路徑沒有內容） |

**對外通或對內通，就算 `STATE=OK`**；兩者都不通才是 `FAIL`。

三件容易寫錯的：

- **對外檢查一定要 `--resolve` 指定 IPv4**。管理機若同時有 IPv6，直接解析網域可能只拿到
  AAAA 記錄，測到的是另一條路徑，節點死了也可能測起來正常。
- **`STATE=ISOLATED` 不能當成節點故障**。管理機自己斷網時什麼都 ping 不到，
  這時候若照樣告警甚至自動切換，等於在網路最亂的時候亂動服務 IP。
- **探測腳本一律 `exit 0`**，判定寫在 stdout。這樣流程節點拿到的是「探測完成」，
  由流程自己判斷內容；離開碼非 0 只保留給「腳本本身出問題」（例如參數打錯）。

### 組態

探測與切換共用同一個組態檔 `failover.conf`：

```bash
PUBLIC_URL="https://example.com/"      # 對外網址
PUBLIC_HOST="example.com"              # 給 curl --resolve 用
INTERNAL_URL="http://192.168.1.20:8080/"   # 服務 IP 上的 WAF
GATEWAY_IP="192.168.1.1"
```

（`NODE_A` / `NODE_B` 沿用熱備切換那一節的設定。）

---

## 三、流程長什麼樣

```
Start → 初始化計數 → 等待 N 分鐘 ─┐
                       ↓          │
                    健康探測       │
                       ↓          │
                  探測結果分流 ────┼─→ STOP     → 結束
                       │          ├─→ OK       → 重置計數 ─┘
                       │          ├─→ ISOLATED → 直接回等待 ┘
                       ↓          │
                   失敗計數 +1     │
                       ↓          │
                  達到門檻？ ──否──┘
                       │是
                       ↓
                  Telegram 告警
                       ↓
              決策關卡（有逾時）
              ├ 執行切換 ────→ 切換 ─┐
              ├ 暫不切換 ──────────→ 寫回事件記錄 → 重置計數 → 回等待
              └ 依預設設定處置 → 判斷 ─┘
```

圖上有多條邊回到「等待下一輪」，**這個迴圈是刻意的**：同一張單承載長時間監看。

### 無人回應時怎麼辦

決策關卡設了逾時（預設 15 分鐘）。逾時後系統自動採用第三個選項「依本單預設設定處置」，
再依**送單時選的預設動作**分流：

| 送單時的選擇 | 逾時後 |
|---|---|
| 逾時自動執行切換（預設） | 執行 `failover.sh switch --yes` |
| 逾時不切換，只記錄並繼續監看 | 只寫事件記錄，回到監看 |

這個分法是刻意的：**「等多久」是流程設定，「等不到人時做什麼」是每次送單時的判斷**。
半夜的巡檢單可以選自動切換，維護期間的巡檢單可以選只記錄。

**決策關卡開著的時候，巡檢會暫停。** 這是取捨：避免關卡還沒處理就又發下一輪告警。
代價是這段期間服務若自己恢復了，流程也不知道，要等人回應或逾時。

---

## 四、佈建與啟動

```bash
cd /opt/BeakPlatform
set -a && source .env && set +a
venv/bin/python scripts/examples/provision_nodedemo_waf_monitor.py --dry-run
venv/bin/python scripts/examples/provision_nodedemo_waf_monitor.py --apply \
    --interval-minutes 3 --decision-timeout-minutes 15
```

常用參數：

| 參數 | 預設 | 說明 |
|---|---|---|
| `--interval-minutes` | 3 | 每輪間隔 |
| `--decision-timeout-minutes` | 15 | 決策關卡等多久 |
| `--telegram-config` | — | Telegram 設定組 secure_code（在「主機設定 → 發信服務」建立） |
| `--telegram-channel` | 測試頻道 | 頻道名稱 |
| `--approver-role` | 無 | 決策關卡指派角色；不給則由送單者自己決策 |

**間隔與逾時是佈建參數，不是表單欄位。** 平台的節點設定值不做變數展開，
`delay_minutes` 這類欄位只能是字面值；要改就重跑一次佈建腳本（冪等，會自動重新發行）。

佈建完成後到**表單中心 → 新填表單 → node展覽館 →「WAF 熱備健康監看」**，
填主旨、選門檻與逾時預設動作，送出。流程就開始跑了。

### 停止

```bash
touch /opt/tmp/waf-monitor.stop
```

下一輪探測會回報 `STATE=STOP`，流程走到「停止監看」正常結束。
要重新開始就刪掉旗標再送一張新單。

（看門狗看到這個旗標也會安靜下來，不會把「刻意停止」當成故障。）

---

## 五、看門狗

```
*/5 * * * * <使用者> flock -n /tmp/waf-monitor-watchdog.lock \
    /opt/BeakPlatform/venv/bin/python /opt/BeakPlatform/scripts/cron/waf_monitor_watchdog.py \
    >> /opt/tmp/BeakPlatform-cron-waf_monitor_watchdog.log 2>&1
```

行為：

- heartbeat 超過 `--stale-minutes`（預設 12）沒更新 → 發 Telegram
- 同一次異常在 `--alert-cooldown-minutes`（預設 60）內只發一次
- heartbeat 恢復更新 → 發一則恢復通知
- 停止旗標存在 → 什麼都不做

Telegram 的 bot token 不寫在腳本或排程裡，執行時才從平台的 Telegram 設定組讀取。

---

## 六、驗證

```bash
# 探測本身
bash Integrated-WAF/monitor_probe.sh
# → TS=... STATE=OK EXT=302 INT=404 GW=ok

# 看門狗（不會真的發送）
venv/bin/python scripts/cron/waf_monitor_watchdog.py --dry-run

# 告警鏈路（會真的發一則訊息）
venv/bin/python scripts/cron/waf_monitor_watchdog.py \
    --heartbeat /tmp/not-exist.ok --state-file /tmp/test.state --stale-minutes 1
```

流程送出後，到**表單流程 → 流程管理**點開該實例的「執行日誌」，
每一輪的探測輸出與分流判斷都在裡面。
