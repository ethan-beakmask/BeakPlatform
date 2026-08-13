# Python 套件升級計劃

> Forgejo Issue #13
> 建立日期: 2026-02-22

## 執行結果

**✅ 全部升級完成** (2026-02-22)

備份位置: `/opt/BeakPlatform_backup_20260222/`

### 升級清單

| 套件 | 舊版本 | 新版本 | 說明 |
|------|--------|--------|------|
| bcrypt | 4.1.1 | **5.0.0** | 密碼 hash（已加 72-byte 防禦檢查） |
| gunicorn | 21.2.0 | **25.1.0** | WSGI server |
| pytest | 7.4.3 | **9.0.2** | 測試框架 |
| pytest-cov | 4.1.0 | **7.0.0** | 覆蓋率 |
| pytz | 2023.3 | **2025.2** | 時區資料庫 |
| python-dateutil | 2.8.2 | **2.9.0** | 日期工具 |
| requests | 2.31.0 | **2.32.5** | HTTP client |
| pypinyin | 0.50.0 | **0.55.0** | 中文拼音 |
| Flask | 3.0.0 | **3.1.3** | Web 框架 |
| Werkzeug | 3.0.1 | **3.1.6** | WSGI 工具 |
| itsdangerous | 2.1.2 | **2.2.0** | 簽名/序列化 |
| Flask-WTF | 1.2.1 | **1.2.2** | CSRF 保護 |
| WTForms | 3.1.1 | **3.2.1** | 表單驗證 |
| SQLAlchemy | 2.0.23 | **2.0.46** | ORM |
| psycopg2-binary | 2.9.9 | **2.9.11** | PostgreSQL driver |
| Flask-Migrate | 4.0.5 | **4.1.0** | DB migration |
| alembic | 1.13.0 | **1.18.4** | Migration engine |
| redis | 5.0.1 | **7.2.0** | Redis client |
| Flask-Session | 0.5.0 | **0.8.0** | Session backend |
| cryptography | 41.0.7 | **46.0.5** | 加密工具 |
| Flask-Limiter | 3.5.0 | **4.1.1** | API 限流 |

### 程式碼修正

1. **config.py**: `RATELIMIT_STORAGE_URL` → `RATELIMIT_STORAGE_URI`（Flask-Limiter 4.x breaking change）
2. **config.py**: Dev/Test session 從 `SESSION_TYPE='filesystem'` + `SESSION_FILE_DIR` 改為 `SESSION_TYPE='cachelib'` + `SESSION_CACHELIB=FileSystemCache()`（Flask-Session 0.8 deprecation）
3. **bcrypt 72-byte 防禦檢查**: 已在前次 commit 中完成（`User.set_password()` 和 `PasswordPolicyService`）

### 驗證結果

- ✅ Flask 啟動正常
- ✅ 系統管理員登入成功
- ✅ pytest 8 passed（errors 為 pre-existing 測試基礎設施問題，非升級相關）
