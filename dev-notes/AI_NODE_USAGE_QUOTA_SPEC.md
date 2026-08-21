# AI Node Usage Quota Spec

## 資料表

`fw_ai_usage_records` 記錄 AiAgent 節點每次嘗試執行的用量與配額狀態。資料列繼承模組基礎欄位，
包含 `secure_code`、`org_secure_code`、`created_at`、`updated_at`、`is_deleted` 等欄位。

主要欄位語意：

| 欄位 | 語意 |
|---|---|
| `workflow_instance_secure_code` | 流程實例識別碼 |
| `form_instance_secure_code` | 表單實例識別碼 |
| `node_id` / `node_name` | 工作流節點識別與顯示名稱 |
| `node_queue_secure_code` | 節點執行佇列識別碼，用於 blocked 去重 |
| `model` | 主要模型名稱 |
| `status` | `running` / `success` / `failed` / `blocked` |
| `input_tokens` / `output_tokens` | top-level usage 的主模型 token 數 |
| `cache_creation_input_tokens` / `cache_read_input_tokens` | top-level usage 的 cache token 數 |
| `cost_usd` | 依 CLI envelope 與 API 牌價換算的估算成本 |
| `duration_ms` / `num_turns` | CLI 回報的耗時與回合數 |
| `model_usage` | CLI 回報的 per-model 明細，可能包含多個模型 |
| `error_message` | 失敗或被配額擋下的原因 |
| `started_at` / `finished_at` | naive UTC 時間 |

`to_dict()` 對外只輸出 `secure_code`，不輸出自增 ID，也刻意不輸出 `org_secure_code`。

## 設定 fallback

設定有兩層可配置來源與一層程式內 fallback：

1. 企業層：`Organization.settings` 內的 `ai_node_<key>`
2. 系統層：`system_settings.key = 'ai_node_defaults'`
3. 內建預設：`ai_usage_service.HARDCODED_DEFAULTS`

五個 key：

| key | 型別 | 語意 |
|---|---|---|
| `enabled` | bool | 企業是否允許使用 AiAgent 節點 |
| `daily_max_runs` | int | 每日執行次數上限，0 表示不限 |
| `monthly_max_runs` | int | 每月執行次數上限，0 表示不限 |
| `daily_max_cost_usd` | float | 每日估算成本上限，0 表示不限 |
| `monthly_max_cost_usd` | float | 每月估算成本上限，0 表示不限 |

所有讀寫與有效值計算都集中在 `modules/form_workflow/services/ai_usage_service.py`。

## 配額判定流程

`check_and_reserve()` 是 handler 執行前的唯一入口：

1. 以 `org_secure_code` 找企業，讀企業時區。
2. PostgreSQL 環境使用 `pg_advisory_xact_lock(hashtext('ai_usage:<org>'))` 鎖住企業層配額判定。
3. 讀有效設定，若 `enabled = false`，寫入 `blocked` 記錄並回傳錯誤。
4. 以企業時區取得當地今日與本月起點，再統計已用次數與估算成本。
5. 依序檢查每日次數、每月次數、每日估算成本、每月估算成本。
6. 通過後先寫入 `running` 佔位列並 commit，釋放 advisory lock。
7. CLI 完成後由 `finalize()` 補上 token、估算成本、耗時、模型明細與最終狀態。

先佔位的理由是避免並行節點同時通過配額檢查而超額。`running` 會計入配額，代表已取得執行名額。

## status 與配額計入

| status | 意義 | 是否計入配額 |
|---|---|---|
| `running` | 已通過配額並佔位，CLI 執行中或尚未 finalize | 是 |
| `success` | CLI 成功且輸出已被接受 | 是 |
| `failed` | 已嘗試執行但失敗，可能已有 token 或估算成本 | 是 |
| `blocked` | 配額或 enabled 檢查擋下，沒有呼叫 CLI | 否 |

同一個 `node_queue_secure_code` 的 blocked 記錄只寫一筆，避免流程引擎重試造成「被擋次數」膨脹。

## API

所有端點都掛在 `/api/form-workflow`，且需要 `form_workflow.admin`：

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/ai-usage/config` | 取得有效設定與每項來源 |
| PUT | `/ai-usage/config` | 寫入企業層覆寫或清除企業層覆寫 |
| GET | `/ai-usage/summary` | 回今日、本月用量、有效配額與本月 blocked 次數 |
| GET | `/ai-usage/records` | 分頁查詢明細，支援 status、start、end |

所有 API 的企業來源只能是 `get_current_org()`，實際查詢以 `org_secure_code` 過濾。

## 時區規則

DB 時間是 naive UTC。日界與月界依企業設定時區計算：

- 今日起點：企業當地日期 00:00 對應的 naive UTC
- 本月起點：企業當地本月 1 日 00:00 對應的 naive UTC
- `/records` 的 `start` / `end` 是企業當地日期；`end` 含當日，查詢時換成隔日 00:00 UTC 作為上界

前端顯示時間交給 `BkTime.format(dateStr, 'short')`，避免瀏覽器時區誤差。

## 成本口徑

`cost_usd` 是 CLI 依 Anthropic 標準 API 牌價換算的等值估算成本，用於相對比較與配額判定。
它不是實際扣款金額，也不代表訂閱制方案的帳單金額。

一次 AiAgent 執行可能使用多個模型。top-level token 欄位只代表主模型 usage，
完整 per-model token 與成本明細在 `model_usage`。

**2026-08-21 經 executor 實跑取得的實際樣本**（這不是推測，寫 parser 或報表前先看）：

```json
{"claude-sonnet-5":            {"costUSD": 0.0108,   "inputTokens": 2,    "outputTokens": 270},
 "claude-haiku-4-5-20251001":  {"costUSD": 0.001421, "inputTokens": 1331, "outputTokens": 18}}
```

`total_cost_usd` = 0.012221 = 0.0108 + 0.001421，**正是所有模型 costUSD 的總和**。
而 top-level `usage.input_tokens` 只有 2 —— haiku 另外用掉的 1331 不在裡面。

也就是說 **`cost_usd` 是全部模型的、token 欄位只是主模型的**，兩者口徑不同。
明細表因此把該欄標為「主模型 tokens」；要看實際總量必須展開 `model_usage`。
（PF-139 卡片曾記錄「有一次 total_cost_usd 試算未吻合、原因未查」，
成因就是當時只用主模型的牌價回推，沒有把第二個模型算進去。）

## 已知限制

`status='running'` 的列計入配額，而 executor 若在 AiAgent 執行途中被 kill，
該列不會被 `finalize()` 補完，會**永久佔用一次配額額度**。

這是刻意選擇的保守方向（寧可多算，不要讓崩潰成為繞過配額的手段），
但目前沒有回收機制。

**要做回收時不要用時間閾值猜**——本節點的執行時間有硬上界
（`_run_cli` 的 `subprocess.run(..., timeout=...)`，預設 60 秒＋CLI 能力檢查 10 秒），
所以「還在跑只是比較久」不存在，但更重要的是有兩層**確定性**判定可用：

**第一層：看對應佇列項目的狀態（零誤殺，涵蓋絕大多數情況）**

`fw_ai_usage_records.node_queue_secure_code` → `fw_node_execution_queue.secure_code`。
佇列已是 `SUCCESS` / `FAILED` / `CANCELLED` 時，handler 必然已結束，
usage 列還停在 `running` 就一定是殘留：

```sql
SELECT u.secure_code, u.started_at, q.status AS queue_status, q.process_id
FROM fw_ai_usage_records u
LEFT JOIN fw_node_execution_queue q ON q.secure_code = u.node_queue_secure_code
WHERE u.status = 'running'
  AND (q.secure_code IS NULL OR q.status IN ('SUCCESS','FAILED','CANCELLED'));
```

**第二層：佇列也還是 RUNNING 時，比對 PID 與 executor 啟動時間**

`report_running()`（`node_handlers/base.py`）在 `handle()` 開頭就寫入
`process_id = os.getpid()`，而 usage 列在那之後才建立，所以每筆 running usage
都對得到一個 PID。PID 不存在即已死；PID 存在但 `started_at` 早於
`systemctl show beakplatform-dev-executor -p ExecMainStartTimestamp`，
表示那是重啟前的執行、PID 被重用了。

**`worker_id` 欄位全為 NULL 是預期狀態，不是缺陷、也不是待辦**
（Ethan 2026-08-21 定調：**本專案沒有跨主機 executor 的構想**）。
`fw_node_execution_queue.worker_id` 存在但全專案沒有任何地方寫入它，
而單一 executor 下 `process_id` 已足以判定存活。
未來 session 看到這個空欄位不要主動補寫入、也不要建卡——
真的哪天要水平擴展再一起評估，第一層判定則完全不受影響。

時間閾值只該當作前兩層都判不出來時的兜底，**不是主要手段**。

另外，`running` 殘留除了 executor 崩潰，還有一個更常見的來源：
**End 節點的 `finish_mode='cancel'`** 會取消所有未完成節點，此時 AiAgent 可能
正在執行、handler 被中斷、usage 列留在 `running`。這種情況第一層判定抓得到
（佇列會是 `CANCELLED`）。

無論用哪一層，回收動作都是把該列標成 `failed`（保留已知的 tokens/cost），
**不是**把 `running` 從計入配額的狀態裡拿掉。

## 刻意沒做

- 不查詢或顯示帳號剩餘額度：CLI envelope 沒有提供剩餘額度欄位。
- 不嘗試對訂閱制帳單做對帳：`cost_usd` 只按 API 牌價估算。
- 不在 API 或前端重算配額：配額判定只在 `ai_usage_service.py`。
- 不讓使用者從 request 指定企業：所有企業來源都取自登入 session 的 `get_current_org()`。
- 不新增細粒度權限碼：管理頁沿用 `form_workflow.admin`。
