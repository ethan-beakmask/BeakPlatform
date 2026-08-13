# 交接：BeakWatch 本機維運監控

> **下次對話使用此文件作為起始 prompt。** 由 2026-05-13 雪崩事件衍生。
> 前置條件：先完成 `dev-notes/handoff_burst_protection_ABC.md` 中的 A+B+C。

## 背景

BeakPlatform 自身雖然加上 A+B+C 三層防護（systemd 上限 + executor semaphore + intake dedup），但若整台主機因其他原因 OOM、queue 異常累積、或服務失能，沒有外部監控就無從察覺與緩解。

本任務在 BeakPlatform 專案內建立**本機維運監控工具 BeakWatch**，定位是「資安工程師的本機運維助手」，不是獨立產品。

## 定位（用戶已拍板）

- **不是**獨立專案，是 BeakPlatform 下的維運工具
- **不是**綁定 .20 (sec-stack) 的服務，sec-stack 只是「推薦但企業未必採用」的組合
- BeakWatch 應該 **deployment-agnostic**：可跑在 .20、可跑在 .16 本機（注意自監控盲點）、也可跑在任何第三方監控主機
- 程式碼放 `/opt/BeakPlatform-dev/maintenance/beakwatch/`，隨 BeakPlatform 一起進 GitHub
- 配置與部署為可選項，預設 disabled，企業導入時自行決定是否啟用、跑在哪台

## 設計決策（用戶已拍板，不需再討論）

| 項目 | 決策 |
|---|---|
| 程式碼位置 | `/opt/BeakPlatform-dev/maintenance/beakwatch/`（隨 BeakPlatform repo） |
| 語言 | Go |
| 通訊方向 | 監控主機 pull BeakPlatform 主機的 `/internal/metrics` HTTP endpoint |
| 控制管道 | SSH 金鑰 + `~/.ssh/authorized_keys` 限定指令（`command="..."`） |
| 認證資訊 | 用 credtool 取得（依 `~/.claude/knowledge_base/standards/coding_standards/go_credtool_standard.md`） |
| 告警通道 | `/opt/line-message/` + Telegram，雙通報（**不要用 /opt/line-bot/**，因 UI 盲抓聊天室已多次發送錯誤對象） |
| 部署彈性 | 同機自監控、異機監控、混合皆支援；config 指定 target host |

## 自監控盲點警告（重要）

若 BeakWatch 與被監控的 BeakPlatform 跑在**同一台主機**，當該主機整台 OOM 時 BeakWatch 自己也會死。同機部署只能應對「某個服務異常」場景，不能應對「整台失能」。文件須明確警告此限制。

最穩健的部署是異機（如家用環境的 .20、或企業內任何獨立監控主機）。

## 雙向擴展備忘（用戶要求記錄）

「日後擴展為雙向互相偵測」：
- 若部署在 .20 (sec-stack) 上，.20 直面攻擊負載大，需 BeakPlatform 端反向監測 .20 健康
- BeakPlatform 持有正式資料，必要時 **BeakPlatform 下令 .20 斷網（戰略迴避）等用戶回家處理**
- 設計時預留雙向控制框架，但本期只實作監控主機 → BeakPlatform 單向

## MVP 範圍（本期必做）

### 1. BeakPlatform 端：暴露 metrics endpoint

新檔案：`backend/app/api/internal_metrics.py`
- 路徑：`/internal/metrics`
- 認證：IP 白名單（從 config 讀允許來源）+ HMAC token（共享密鑰透過 credtool 取）
- 公開白名單加入此路徑（auth_interceptor）
- 回傳 JSON：
  ```
  {
    "ts": "2026-05-13T18:00:00Z",
    "host": "beakplatform-dev",
    "ram": {"used_mb": 1700, "total_mb": 11000, "pct": 15.5},
    "load_avg": [3.4, 5.1, 8.2],
    "executor": {
      "service_active": true,
      "subprocess_count": 8,
      "subprocess_limit": 8
    },
    "queue": {
      "pending": 0,
      "waiting": 0,
      "running": 0
    },
    "intake_rate_1min": 12,
    "active_workflows": 8
  }
  ```

注意：此 endpoint 是安全核心觸碰（security_core_touch），需更新 `dev-notes/manifests/security-core.yaml` 或對應 manifest 註記。

### 2. BeakWatch 本體

專案結構（在 BeakPlatform repo 內）：
```
maintenance/beakwatch/
  go.mod
  cmd/beakwatch/main.go
  internal/
    config/        # 讀 config.yaml（路徑由 -config 旗標指定）
    poller/        # pull metrics
    evaluator/     # 規則評估
    actuator/      # 執行緩解（SSH 命令）
    notifier/      # line-message + Telegram
  systemd/
    beakwatch.service.example   # 範本，安裝時客製
  scripts/
    install.sh                  # 互動式安裝，問用戶部署位置
  README.md                     # 含「自監控盲點」警告
```

#### Config（YAML）

```yaml
target:
  host: 192.168.0.16
  metrics_url: https://192.168.0.16:7000/internal/metrics
  hmac_key_credtool_alias: beakwatch-metrics-hmac
poll:
  interval_seconds: 15
  unreachable_threshold: 3
rules:
  ram_pct_high: 85
  queue_pending_high: 500
  subprocess_overrun_ratio: 1.5
  intake_rate_burst: 200
actuator:
  ssh:
    user: beakwatch
    host: 192.168.0.16
    key_path: /etc/beakwatch/id_ed25519
    allowed_commands: [pause-executor, resume-executor, pause-intake, resume-intake, status]
  auto_resume_after_seconds: 300
notifier:
  line_message:
    enabled: true
    cli_path: /opt/line-message/send.sh   # 安裝時確認實際介面
    recipient: "ethan"
  telegram:
    enabled: true
    bot_token_credtool_alias: beakwatch-telegram-bot
    chat_id_credtool_alias: beakwatch-telegram-chat
```

#### Poller
- 每 `interval_seconds` 拉一次
- 連續 `unreachable_threshold` 次失敗 → 觸發 `unreachable` 告警

#### Evaluator 規則（初版）
| 規則 | 條件 | 動作 |
|---|---|---|
| RAM 飆高 | ram.pct > `ram_pct_high` 連續 2 次 | actuator: pause-executor |
| Queue 暴漲 | queue.pending > `queue_pending_high` | actuator: pause-intake |
| Subprocess 失控 | executor.subprocess_count > limit × `subprocess_overrun_ratio` | actuator: pause-executor + 通知 |
| Intake 爆量 | intake_rate_1min > `intake_rate_burst` | actuator: pause-intake + 通知 |
| 無法連線 | 連續 N 次 pull 失敗 | actuator: 無，僅通知 |

緩解後若 `auto_resume_after_seconds` 內指標回到安全範圍，自動 resume（避免人不在時系統一直停擺）。

#### Actuator（SSH 控制管道）
BeakPlatform 主機上 `~/.ssh/authorized_keys` 限定：
```
command="/opt/BeakPlatform-dev/maintenance/beakwatch/scripts/server_actions.sh ${SSH_ORIGINAL_COMMAND}",no-pty,no-X11-forwarding,from="<watcher-ip>" ssh-ed25519 AAAA... beakwatch@watcher
```
`server_actions.sh` 只接受白名單動作；其他一律拒絕並 log。

#### Notifier
雙通報：
- line-message：透過 `/opt/line-message/` 的 CLI（安裝時先確認介面）
- Telegram：用 Bot token

告警內容：時間、規則、觸發指標、執行動作、後續建議。

### 3. 認證資訊

依 `go_credtool_standard.md`，所有密鑰透過 credtool 取得：
- BeakPlatform 的 `/internal/metrics` HMAC 共享密鑰
- Telegram Bot token + chat ID
- SSH 私鑰**路徑**（不是密鑰本身，但路徑也走 config）

### 4. systemd 安裝

`maintenance/beakwatch/systemd/beakwatch.service.example`：
```
[Unit]
Description=BeakWatch Local Ops Monitor
After=network.target

[Service]
Type=simple
User=beakwatch
ExecStart=/usr/local/bin/beakwatch -config /etc/beakwatch/config.yaml
Restart=always
RestartSec=10
MemoryMax=256M
TasksMax=20

[Install]
WantedBy=multi-user.target
```

## 完成判定

1. `/internal/metrics` endpoint 回傳正確 JSON，IP 白名單與 HMAC 驗證生效
2. BeakWatch 可在 .20 或 .16 任一台跑起來，systemd active
3. 人為製造爆量（如灌入 1000 個 fake intake event），BeakWatch 偵測到並 pause-executor，發雙通報
4. 故意斷網被監控主機，BeakWatch 連續 N 次 pull 失敗後發告警
5. 緩解後指標恢復，自動 resume

## GitHub Push

BeakWatch 是 BeakPlatform 的一部分，**走** BeakPlatform 的 push 流程（forgejo + push_github.sh）。Go binary 不進 repo，只進原始碼。

## 不要做的事

- 不要把 BeakWatch 變成獨立 repo
- 不要用 /opt/line-bot/（用戶明確指定用 /opt/line-message/）
- 不要在本期實作反向監測（架構預留即可）
- 不要做太多規則，先把 5 條核心規則跑穩
- 不要忘記在 README 警告「自監控盲點」
