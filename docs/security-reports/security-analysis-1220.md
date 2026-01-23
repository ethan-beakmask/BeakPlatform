# BeakMask 安全掃描專業分析報告

**掃描日期**: 2025-12-20
**掃描工具**: Semgrep 1.145.2
**掃描範圍**: backend/
**規則來源**: 自定義規則 (.semgrep/) + Semgrep Community 規則 (auto)

---

## 執行摘要

| 指標 | 數值 |
|------|------|
| 掃描檔案數 | 127 |
| 執行規則數 | 469 |
| 發現總數 | 71 |
| ERROR 等級 | 7 |
| WARNING 等級 | 64 |

---

## 發現分類統計

| 類別 | 數量 | 嚴重度 | 說明 |
|------|------|--------|------|
| TENANT-02 違規 | 37 | WARNING | API 層直接使用 Model.query |
| CSRF Token 缺失 | 19 | WARNING | 表單未包含 CSRF token (誤報) |
| SQL Injection 風險 | 6 | ERROR | 使用 f-string 建構 SQL |
| AUTH-02 違規 | 3 | ERROR | 路由缺少認證 decorator |
| 密碼未驗證 | 5 | WARNING | set_password 前未驗證強度 (誤報) |
| 硬編碼密鑰 | 1 | ERROR | 測試環境 SECRET_KEY |

---

## 詳細分析

### 1. TENANT-02 違規 (37 處) - 需處理

**問題**: API 路由直接使用 `Model.query` 而非透過 `ResourceGateway`

**影響檔案**:
- `api/auth.py` (1)
- `api/contracts.py` (5)
- `api/menu.py` (2)
- `api/modules.py` (2)
- `api/organizational_units.py` (7)
- `api/organizations.py` (6)
- `api/pages.py` (4)
- `api/roles.py` (9)
- `api/users.py` (1)

**風險等級**: 中

**說明**:
雖然程式碼有手動加入 `org_secure_code` 過濾，但繞過 ResourceGateway 增加遺漏過濾的風險。這是專案標準 TENANT-02 的核心要求。

**建議**: 依 CLAUDE.md 規劃，進行 TENANT-02 重構，將所有 API 查詢改用 ResourceGateway。

---

### 2. SQL Injection 風險 (6 處) - 需立即處理

**位置**: `web/portal.py:40, 56, 58`

**問題程式碼**:
```python
text(f'SELECT COUNT(*) FROM "{table_name}"')
text(f'SELECT * FROM "{table_name}" ORDER BY "{order_column}" DESC LIMIT 10')
```

**風險等級**: 高 (但實際風險有限)

**分析**:
- `table_name` 來自 `inspector.get_table_names()`，是系統內部資料
- `order_column` 來自 `inspector.get_columns()`，也是系統內部資料
- **實際風險低**，因為資料來源為資料庫 metadata，非用戶輸入

**建議**:
1. 加入白名單驗證（雖非必要，但符合防禦深度原則）
2. 或加入 `# nosemgrep` 註解說明已評估風險

---

### 3. AUTH-02 違規 (3 處) - 需評估

**位置**:
- `__init__.py:70` - `/health` 健康檢查端點
- `web/portal.py:19` - 公開專區首頁
- `web/portal.py:25` - db-viewer 開發工具

**分析**:

| 路由 | 應有 Decorator | 說明 |
|------|----------------|------|
| `/health` | `@public_route` | 健康檢查應為公開，但需明確標記 |
| `/` (portal) | `@public_route` | 公開專區首頁 |
| `/db-viewer` | `@system_admin_required` | 高權限開發工具！危險！ |

**建議**:
1. `/health` 加上 `@public_route`
2. Portal 首頁加上 `@public_route`
3. **db-viewer 必須加上認證保護或移除**

---

### 4. 硬編碼密鑰 (1 處) - 可接受

**位置**: `config.py:90`

```python
SECRET_KEY = 'test-secret-key-for-testing-only'
```

**分析**: 這是 TestingConfig 類別中的設定，用於測試環境。生產環境使用環境變數。

**建議**: 可忽略，但考慮在註解說明僅限測試。

---

### 5. CSRF Token 缺失 (19 處) - 誤報

**說明**: Semgrep 使用 Django 模板規則掃描 Jinja2 模板，導致誤報。

**實際情況**:
- 多數表單已有 `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
- 使用 Flask-WTF 的 CSRF 保護機制
- Semgrep 的 Django 規則無法識別 Jinja2 語法

**建議**:
1. 建立 `.semgrepignore` 排除 Django 規則對 Jinja2 模板的掃描
2. 或建立自定義 Jinja2 CSRF 檢查規則

---

### 6. 密碼未驗證 (5 處) - 誤報

**說明**: Semgrep 誤將 Flask 應用視為 Django，建議使用 `django.contrib.auth.password_validation`。

**實際情況**: 這是 Flask 專案，不使用 Django 驗證系統。

**建議**:
1. 考慮實作自訂密碼強度驗證
2. 忽略此誤報

---

## 優先處理順序

### P0 - 立即處理
| 項目 | 說明 |
|------|------|
| db-viewer 認證 | 開發工具暴露資料庫內容，必須加認證 |

### P1 - 短期處理
| 項目 | 說明 |
|------|------|
| AUTH-02 修正 | 3 處路由加上適當 decorator |
| SQL 注入防護 | 加入白名單或 nosemgrep 註解 |

### P2 - 中期處理
| 項目 | 說明 |
|------|------|
| TENANT-02 重構 | 37 處 API 改用 ResourceGateway |

### P3 - 可選處理
| 項目 | 說明 |
|------|------|
| 減少誤報 | 建立 .semgrepignore 或自訂規則 |
| 密碼強度驗證 | 實作 Flask 版本的密碼驗證 |

---

## Semgrep 規則改進建議

### 1. 減少 Django 規則誤報

建立 `.semgrepignore`:
```
# 排除 Django 規則對 Jinja2 模板的誤報
templates/
```

或在 `.semgrep/` 中建立排除設定。

### 2. 新增自訂規則建議

**Jinja2 CSRF 檢查**:
```yaml
- id: beakmask-jinja2-missing-csrf
  patterns:
    - pattern: <form method="POST" ...>
    - pattern-not-inside: |
        <form ...>
          ...
          <input ... name="csrf_token" ...>
          ...
        </form>
  paths:
    include:
      - "**/templates/**/*.html"
  message: "Form missing csrf_token hidden input"
  languages: [html]
  severity: WARNING
```

---

## 附錄

### 官方報告檔案位置

| 格式 | 路徑 |
|------|------|
| SARIF (業界標準) | `docs/security-reports/semgrep-official-report.sarif` |
| Text (人類可讀) | `docs/security-reports/semgrep-official-report.txt` |

### 掃描指令

```bash
# 執行掃描
semgrep --config=.semgrep/ --config=auto backend/

# 產生 SARIF 報告 (可匯入 GitHub Security)
semgrep --config=.semgrep/ --config=auto backend/ --sarif -o report.sarif

# 產生 JSON 報告 (程式處理)
semgrep --config=.semgrep/ --config=auto backend/ --json -o report.json
```

---

*報告產生時間: 2025-12-20*
*分析者: Claude Code*
