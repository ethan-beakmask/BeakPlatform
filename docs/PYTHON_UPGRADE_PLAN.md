# Python 套件升級計劃

> Forgejo Issue #13
> 建立日期: 2026-02-22

## 現況

套件版本比對頁面 (`/hostconfig/server-settings` → 套件版本) 顯示：
- 大版本更新: 8 個
- 小版本更新: 13 個
- 已是最新: 5 個

## 執行前置作業（每次對話開始時）

1. **全目錄備份**: `cp -a /opt/BeakPlatform /opt/BeakPlatform_backup_$(date +%Y%m%d)`
2. **DB 備份**: `sudo -u postgres pg_dump beakplatform_dev > /opt/BeakPlatform_backup_$(date +%Y%m%d)/db_dump.sql`
3. **記錄 pip freeze**: `pip freeze > /opt/BeakPlatform_backup_$(date +%Y%m%d)/pip_freeze.txt`

## 升級批次

每批升級後必須驗證：
1. `flask run` 啟動正常
2. 系統管理員 + 企業管理員 + 員工登入正常
3. 相關功能快速驗證
4. `pytest` 通過

---

### Batch 1: bcrypt + gunicorn（優先處理）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| bcrypt | 4.1.1 | 5.0.0 | 密碼 hash |
| gunicorn | 21.2.0 | 25.1.0 | WSGI server |

**bcrypt 5.0.0 分析結果（低風險）：**
- 唯一 breaking change: 密碼超過 72 bytes 拋 ValueError（舊版靜默截斷）
- BeakPlatform **未使用 passlib**，直接呼叫 `bcrypt.hashpw()`/`bcrypt.checkpw()`
- 密碼長度限制 8~12 碼，不可能超過 72 bytes
- 升級時在 `User.set_password()` 加防禦性長度檢查

**gunicorn 21→25：**
- 需同步修正 Docker 部署 (192.168.0.15:8000) 的 gunicorn 配置
- 之前部署曾有問題，一併檢查 gunicorn config 與啟動參數

**驗證**: 登入/登出、密碼重設、Docker 部署啟動正常

---

### Batch 2: 測試工具（零風險，不影響 runtime）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| pytest | 7.4.3 | 9.0.2 | 測試框架 |
| pytest-cov | 4.1.0 | 7.0.0 | 覆蓋率 |
| pytest-flask | 1.3.0 | (最新) | Flask 測試 |

**驗證**: `pytest` 能正常執行

---

### Batch 3: 時區/日期/工具（低風險）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| pytz | 2023.3 | 2025.2 | 時區資料庫更新 |
| python-dateutil | 2.8.2 | 2.9.0 | 日期工具 |
| requests | 2.31.0 | 2.32.5 | HTTP client |
| pypinyin | 0.50.0 | 0.55.0 | 中文拼音 |

**驗證**: 日期相關功能、Telegram 測試連線、用戶姓名羅馬拼音

---

### Batch 4: Flask 核心生態（中風險，一起升）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| Flask | 3.0.0 | 3.1.3 | Web 框架 |
| Werkzeug | 3.0.1 | 3.1.6 | WSGI 工具 |
| itsdangerous | 2.1.2 | 2.2.0 | 簽名/序列化 |
| Flask-WTF | 1.2.1 | 1.2.2 | CSRF 保護 |
| WTForms | 3.1.1 | 3.2.1 | 表單驗證 |
| Flask-Babel | 4.0.0 | (最新) | i18n |

**注意**: Flask + Werkzeug + itsdangerous 版本必須互相相容
**驗證**: 所有頁面能正常渲染、CSRF token 正常、i18n 切換正常

---

### Batch 5: DB 層（中風險）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| SQLAlchemy | 2.0.23 | 2.0.46 | ORM |
| psycopg2-binary | 2.9.9 | 2.9.11 | PostgreSQL driver |
| Flask-SQLAlchemy | 3.1.1 | (最新) | Flask 整合 |
| Flask-Migrate | 4.0.5 | 4.1.0 | DB migration |
| alembic | 1.13.0 | 1.18.4 | Migration engine |

**驗證**: CRUD 操作正常、RLS 正常、migration 指令可執行

---

### Batch 6: Session/Cache（高風險）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| redis | 5.0.1 | 7.2.0 | Redis client (大版本 x2) |
| Flask-Session | 0.5.0 | 0.8.0 | Session backend |

**風險**: redis 5→7 跳了兩個大版本，API 可能有 breaking change
**注意**: `config.py` 中 `SESSION_REDIS = redis.from_url()` 可能需要調整
**驗證**: 登入後 session 保持、多頁面切換不掉線、session 過期正常

---

### Batch 7: 認證/加密其餘（中風險）

| 套件 | 現在 | 最新 | 說明 |
|------|------|------|------|
| cryptography | 41.0.7 | 46.0.5 | SMTP 密碼加密 |
| Flask-Login | 0.6.3 | (最新) | 登入管理 |
| Flask-Limiter | 3.5.0 | 4.1.1 | API 限流 |

**策略**: 先升 Flask-Login，再升 Flask-Limiter，最後升 cryptography，每個單獨測試
**驗證**: 登入/登出、限流正常、SMTP 密碼解密正常

---

## 注意事項

- 每批升級前先備份 `requirements.txt`
- 升級指令: `pip install --upgrade 套件名==版本`
- 升級後更新 `requirements.txt` 中的版本號
- 如遇 breaking change 無法快速解決，回退到原版本
- 全部完成後在套件版本頁面確認結果
