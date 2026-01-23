# 資料庫加密策略 (ISO 27701)

> 決議日期：2026-01-09

## 設計目標

1. **PII 保護**：符合 ISO 27701 個資保護要求
2. **開發影響最小化**：AP 層不需大幅修改
3. **效能考量**：只加密需要保護的資料

---

## 架構設計

```
┌─────────────────────────────────────────────────────────────┐
│                        BeakMask AP                          │
└──────────┬────────────────────────────┬─────────────────────┘
           │                            │
           ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐
│   Acra Proxy        │      │   直連 (無加密)      │
└──────────┬──────────┘      └──────────┬──────────┘
           │                            │
           ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐
│  PostgreSQL (主)    │      │  TimescaleDB        │
│  業務資料 (加密)     │      │  網路 Log (明文)     │
│  PII 保護           │      │  時序查詢優化        │
└──────────┬──────────┘      └─────────────────────┘
           │
           ▼ (非同步 ETL)
┌─────────────────────┐
│  PostgreSQL (副本)  │
│  除錯用 (明文)       │
│  隔離環境/受限存取   │
└─────────────────────┘
```

---

## 採用工具：Acra

**選擇 Acra 的原因：**
- 開源、專為資料庫加密設計
- AP 層零修改（只改連線字串）
- 欄位級加密（可配置）
- 內建 SQL 注入防護
- 支援盲索引（可搜尋加密欄位）

**官網**：https://www.cossacklabs.com/acra/

---

## 三個資料庫角色

| 資料庫 | 用途 | 加密 | 連線方式 | 環境 |
|--------|------|------|----------|------|
| **主 DB** | 業務資料 | ✅ Acra | AP → Acra → DB | 生產 |
| **除錯 DB** | 開發除錯 | ❌ 明文 | ETL 同步 | 開發/內網 |
| **TimescaleDB** | 網路 Log | ❌ 明文 | AP 直連 | 生產 |

---

## 敏感欄位分類

| 分類 | 欄位範例 | 加密 | 可搜尋 |
|------|----------|------|--------|
| **L1 極機密** | id_number, 銀行帳號 | ✅ AES-256-GCM | ❌ |
| **L2 機密** | email, phone | ✅ AES-256-GCM | ✅ 盲索引 |
| **L3 內部** | 地址, 生日 | ✅ AES-256-GCM | ❌ |
| **L4 一般** | name, 職稱 | ❌ 明文 | ✅ |
| **Log 資料** | 網路流量 | ❌ 明文 | ✅ |

---

## 加密行為說明

### 隨機化加密（AES-GCM）
- 同一個明文每次加密產生不同密文（因隨機 IV）
- 功能正確性不受影響（解密後值相同）
- **禁止直接比較密文**

### 盲索引（HMAC）
- 確定性：同明文產生同索引
- 用於精確匹配搜尋 `WHERE email_blind_index = ?`

```python
# ❌ 禁止：比較密文
if user1.email_encrypted == user2.email_encrypted:  # 永遠 False

# ✅ 正確：比較盲索引
if user1.email_blind_index == user2.email_blind_index:  # 可判斷
```

---

## 開發規範（加密欄位查詢限制）

為確保有/無 Acra 兩種部署模式相容，敏感欄位有查詢限制：

| 操作 | 可用性 | 說明 |
|------|--------|------|
| `WHERE email = ?` | ✅ 可用 | 精確匹配（盲索引）|
| `WHERE email LIKE '%@%'` | ❌ 禁止 | 模糊搜尋不支援 |
| `ORDER BY email` | ❌ 禁止 | 加密後無法排序 |
| `COUNT(DISTINCT phone)` | ❌ 禁止 | 聚合函數不支援 |

```python
# 開發時標記敏感欄位
ENCRYPTED_FIELDS = ['email', 'phone', 'id_number']
SEARCHABLE_ENCRYPTED = ['email']  # 有盲索引
```

---

## 部署模式（初次選擇不可逆）

系統初次部署時選擇，之後無法切換：

| 模式 | 連線 | 適用 |
|------|------|------|
| `disabled` | AP → PostgreSQL | 無加密需求 |
| `acra` | AP → Acra → PostgreSQL | 有 PII 保護需求 |

```python
# config.py
ENCRYPTION_MODE = os.getenv('ENCRYPTION_MODE', 'disabled')

DATABASE_URL = (
    os.getenv('ACRA_DATABASE_URL')
    if ENCRYPTION_MODE == 'acra'
    else os.getenv('DATABASE_URL')
)
```

**注意**：兩種模式的加密格式不相容，切換需要資料遷移。

---

## 金鑰管理

| 環境 | 方案 | 說明 |
|------|------|------|
| 開發 | 環境變數 | 簡單但不安全 |
| 生產 | HashiCorp Vault | 推薦 |
| 雲端 | AWS KMS / GCP KMS | 託管服務 |

---

## 除錯副本同步

```bash
# 定時同步（經 Acra 解密匯出）
0 * * * * pg_dump -h acra-server -p 9393 beakmask \
  | psql -h debug-db beakmask_debug
```

**安全要求**：
- 除錯 DB 只能在內網存取
- 存取需記錄稽核日誌
- 定期清理過期資料

---

## PostgreSQL HA/LB 工具

| 工具 | 用途 |
|------|------|
| **Pgpool-II** | HA、LB、讀寫分離（最完整）|
| **PgBouncer** | 連線池（輕量）|
| **HAProxy** | TCP 負載均衡 |
| **Patroni** | 自動 failover（K8s）|

---

## 實作優先順序

1. [ ] 盤點所有敏感欄位，標記分類
2. [ ] 建立 Acra 開發環境（Docker）
3. [ ] 配置加密規則（哪些表/欄位）
4. [ ] 測試 CRUD 功能正確性
5. [ ] 設定 TimescaleDB 連線（獨立路徑）
6. [ ] 建立除錯 DB 同步機制
7. [ ] 金鑰管理整合（Vault）
8. [ ] 存取稽核日誌

---

## 參考資料

- [Acra 官方文件](https://docs.cossacklabs.com/acra/)
- [ISO 27701 標準](https://www.iso.org/standard/71670.html)
- [PostgreSQL 加密選項](https://www.postgresql.org/docs/current/encryption-options.html)
- [TimescaleDB](https://www.timescale.com/)

---

*建立日期：2026-01-09*
