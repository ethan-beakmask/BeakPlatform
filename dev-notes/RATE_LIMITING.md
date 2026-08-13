# Rate Limiting 速率限制設計

## 機制概述

使用 Flask-Limiter，以 **來源 IP** (`get_remote_address`) 為限制單位。

儲存後端為 Redis，策略為 `fixed-window`（固定時間窗口）。

## 限制單位說明

`key_func=get_remote_address` 代表所有限制都是 **per IP**，不是 per user。

企業環境中，整間公司可能透過 NAT 共用同一個公網 IP，因此預設值必須考量多人共用情境。例如 20 人同時操作，每人每分鐘 5 次請求，一小時就會產生 6000 次請求。

## 限制設定

### 全域預設 (RATELIMIT_DEFAULT)

適用於所有未個別設定的路由。

| 層級 | 限制值 | 用途 |
|------|--------|------|
| 每分鐘 | 100 | 短期防護，擋自動化爆刷 |
| 每小時 | 2000 | 主要防線，允許多人共用 IP |
| 每日 | 10000 | 日總量上限 |

### 敏感路由（個別限制，較嚴格）

這些路由有獨立的限制設定，不受全域預設影響。

| 路由 | 環境變數 | 預設值 | 設計考量 |
|------|----------|--------|----------|
| 登入 | `RATELIMIT_LOGIN` | 5/min | 防暴力破解，共用 IP 下仍需偏嚴 |
| 忘記密碼 | `RATELIMIT_FORGOT_PASSWORD` | 3/hour | 防濫發重設信件 |
| 重設密碼 | `RATELIMIT_RESET_PASSWORD` | 5/hour | 防暴力猜測 token |

> dev 環境 `.env` 的 `RATELIMIT_LOGIN` 設為 30/min，方便測試。

## 調整方式

所有限制值均可透過環境變數 (`.env`) 覆蓋，不需改程式碼：

```bash
# .env
RATELIMIT_DEFAULT="10000 per day;2000 per hour;100 per minute"
RATELIMIT_LOGIN="5 per minute"
RATELIMIT_FORGOT_PASSWORD="3 per hour"
RATELIMIT_RESET_PASSWORD="5 per hour"
```

如需完全關閉速率限制（僅限測試）：

```bash
RATELIMIT_ENABLED=false
```

## 調整建議參考

以下為估算基準，供日後調整參考：

- 單一用戶正常操作：約 5-15 req/min（頁面載入 + API 呼叫）
- 共用 IP 人數估算：企業通常 10-50 人共用同一出口 IP
- 安全餘裕：建議預設值至少為「最大預估同時用戶數 x 每人每分鐘請求數」的 2 倍

## 程式碼位置

- 限制器初始化：`backend/app/__init__.py` (Limiter)
- 設定預設值：`backend/app/config.py` (BaseConfig)
- 敏感路由限制：`backend/app/api/auth.py`
- 測試環境關閉：`backend/app/config.py` (TestingConfig)
