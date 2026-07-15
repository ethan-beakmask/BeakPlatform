# 資料出口政策 (Egress Policy) 規格 v1.0

> 目標：伺服器統一決定「哪些資料離開伺服器」，同時涵蓋一般 Web UI（SQL 列表）
> 與 Form.io 表單（JSON form_data）。設計討論定案於 2026-07-15。

---

## 術語表

| 術語 | 定義 |
|------|------|
| 出口（egress） | 資料經 API 序列化後離開伺服器、進入瀏覽器的那一刻 |
| 語境（context） | 資料呈現形態：`list`（表，多筆）/ `detail`（單，單筆攤開）/ `form_node`（Form.io 流程節點）/ `export`（匯出） |
| 能見度（visibility） | 欄位在某語境對某角色的出口行為：`clear` / `masked` / `hidden` |
| 哨兵（sentinel） | masked 欄位下發的佔位物 `{"__masked": true}`，真值不離開伺服器 |
| 揭示（reveal） | 用戶對 masked 格主動請求真值的動作，逐格進行、逐格稽核 |
| 水表（meter） | 計量器。三個獨立水表：list 列數、reveal 次數、export 筆數 |
| 敏感度分級（tier） | 欄位的機密等級，水表閾值依 tier 設定 |

## 三值能見度

| visibility | 行為 |
|---|---|
| `clear` | 明文直接下發（**未設政策的欄位預設值**，確保漸進接入不斷全站） |
| `masked` | 下發哨兵，值不離開伺服器；唯一取值通道是 `POST /api/egress/reveal` |
| `hidden` | 序列化投影階段直接剔除，前端不知欄位存在 |

## 政策解析順序

政策鍵：`(org, resource_code, field_name, context)` + 適用對象。
適用對象比對優先序（先命中先用）：

1. `role_secure_code` + `department_secure_code` 都相符（部門限定的角色政策）
2. `role_secure_code` 相符且政策 `department_secure_code IS NULL`（角色全部門）
3. `role_secure_code IS NULL`（該資源該語境的預設政策）
4. 無任何政策 → `clear`

多筆同級命中時取**最嚴格**者（hidden > masked > clear）。
SYSTEM_ADMIN 不豁免——政策要對誰寬鬆，用政策資料表達，引擎不硬編碼後門。

## 三種呈現形態

1. **表（list）**：遮罩單位是「格」。敏感欄整欄下發哨兵，揭示逐格 fetch。
   不提供整欄揭示；需要整欄請走 export 語境（另設政策與計量權重）。
2. **單（detail）**：政策通常較 list 寬，但這是政策資料的選擇，引擎不硬編碼。
3. **Master-Detail 同屏**：**鐵律——detail 資料必須由獨立 API 呼叫取得，
   禁止內嵌在 list 回應預載**。master 走 list 政策、detail 走 detail 政策，
   兩次政策評估自然發生。（已列入 SECURITY_PITFALLS.md）
4. **export**：必須走同一政策表；masked 欄位在 export 語境建議設 hidden。
   計量權重最高。

## 計量（三水表）

滑動時間窗以 `egress_audit_logs` 聚合計算（無額外快取層，窗內 COUNT）。
閾值定義在 `egress_tier_thresholds`：`(org, tier, meter, threshold, window_minutes)`。

| meter | 計什麼 | 建議定位 |
|---|---|---|
| `list_rows` | list/detail 出口的資料筆數累計 | 高閾值，抓爬庫 |
| `reveal` | 逐格揭示次數 | 低閾值，最強盜資料訊號 |
| `export` | 匯出筆數 | 單次即可觸發等級 |

觸發後行為：寫一筆 `action='alert'` 稽核 + 插入 LookupItem alert 廣播
（category=broadcast, value.type=alert，target 為企業管理員角色），
沿用既有 `/api/broadcasts/active` 推播管道。同一 (user, meter) 在冷卻時間
（同 window_minutes）內不重複告警。

## 稽核

`egress_audit_logs`：user、resource_code、context、action
（`list` / `detail` / `reveal` / `export` / `alert`）、record_scs（JSONB 陣列）、
field_name（reveal 時）、row_count、ip、時間。
clear-only 且未設任何政策的資源**不記錄**（避免全站稽核噪音）；
資源一旦設有任何政策即開始計量記錄。

## 掛點與接入方式

引擎位置：`backend/app/services/egress_service.py`。

```python
from app.services import egress_service

# list（API 序列化處，to_dict 之後）
items = [u.to_dict() for u in users]
items = egress_service.apply('user', 'list', items)

# detail
data = egress_service.apply('user', 'detail', [user.to_dict()])[0]
```

- `apply()` 需要 request context（讀 current_user / g）；無政策資源為 no-op。
- 哨兵格前端由 `egress-mask.js` 渲染，hover 揭示自動走 `/api/egress/reveal`。
- 揭示端點需要知道 resource_code → 值的取法：`EGRESS_RESOURCE_REGISTRY`
  註冊 `resource_code -> (Model, 欄位取值函式)`。模組（含 Form.io form_data
  的 JSON 欄位）在載入時自行註冊 accessor。
- `form_node` 語境：form_workflow 渲染服務以 `node_key` 欄位綁定政策到
  流程節點，過濾 Form.io schema 與 form_data（本期完成引擎支援，
  form_workflow 端接入為下一期試點）。

## 資料表

- `egress_field_policies`：org、resource_code、field_name、context、
  role_secure_code(NULL=預設)、department_secure_code(NULL=全部門)、
  node_key(form_node 語境用)、visibility、tier
- `egress_tier_thresholds`：org、tier、meter、threshold、window_minutes、is_active
- `egress_audit_logs`：見稽核節

Migration：`scripts/migrations/081_egress_policy.sql`

## 明示的限制（非資安承諾）

- 視覺遮罩與揭示摩擦**擋不了螢幕錄影與肉眼記憶**，定位是嚇阻與留跡。
- 計量是事後告警不是事前阻斷（阻斷會誤傷合法尖峰作業，v1 不做）。
- 政策快取 60 秒，政策異動最遲 60 秒生效。
