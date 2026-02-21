# 變數系統規格書 (Variable System Specification)

> **狀態**: CONFIRMED — 已定案，開始實作
> **建立日期**: 2026-02-21
> **目的**: 統一流程設計工具中所有變數的語法、分類、作用域、優先序與生命週期

---

## 1. 設計原則

1. **兩大分類**: 使用者可見的變數分為「表單類」與「流程類」，直覺對應業務概念
2. **短前綴制**: 所有變數統一使用 `${prefix.name}` 語法，前綴簡短一致
3. **作用域明確**: 三層 scope 各有獨立隔離鍵與生命週期，不混淆
4. **單一解析器**: `replace_variables()` 統一處理所有前綴，不再有「有名無實」的變數

---

## 2. 變數語法

統一格式：`${prefix.name}`

所有變數必須帶前綴，無前綴的裸名 `${xxx}` 在新版中不合法（過渡期提供 fallback）。

---

## 3. 前綴對照表

### 3.1 表單類

| 前綴 | 全稱 | 說明 | 來源 |
|------|------|------|------|
| `f.` | form field | 表單欄位值 | `form_instance.form_data` (JSON) |
| `fi.` | form info | 表單實例元資料 | `FwFormInstance` model 欄位 |

### 3.2 流程類

| 前綴 | 全稱 | 說明 | 來源 |
|------|------|------|------|
| `v.` | variable | 使用者自定義流程變數 | `fw_workflow_variables` 表 |
| `wi.` | workflow info | 流程實例元資料 | `FwWorkflowInstance` model 欄位 |
| `n.` | node | 當前節點上下文 | `FwNodeExecutionQueue` queue_item |
| `t.` | time | 時間值 | 執行時動態產生 |

### 3.3 全部前綴一覽

```
表單類                          流程類
──────────────────────────      ──────────────────────────
f.   表單欄位 (form field)      v.   流程變數 (variable)
fi.  表單資訊 (form info)       wi.  流程資訊 (workflow info)
                                n.   節點上下文 (node)
                                t.   時間 (time)
```

---

## 4. 各前綴可用變數明細

### 4.1 `f.` — 表單欄位

取自 `form_instance.form_data` JSON，key 為 form.io 元件的 `key` 屬性。

```
${f.days}            → form_data['days']
${f.reason}          → form_data['reason']
${f.address.city}    → form_data['address']['city']  (巢狀欄位)
```

- 支援巢狀路徑（用 `.` 分隔）
- 值可為 string/number/boolean/array/object，替換時一律轉 string
- 欄位不存在時替換為空字串

### 4.2 `fi.` — 表單資訊

取自 `FwFormInstance` model 欄位，固定清單：

| 變數 | 來源欄位 | 說明 |
|------|---------|------|
| `${fi.applicant}` | `applicant_name` | 申請人姓名 |
| `${fi.applicant_dept}` | `applicant_dept` | 申請人部門 |
| `${fi.applicant_email}` | `applicant_email` | 申請人信箱 |
| `${fi.applicant_code}` | `applicant_secure_code` | 申請人代碼 |
| `${fi.serial}` | `serial_number` | 表單編號 |
| `${fi.name}` | `form_name` | 表單名稱 |
| `${fi.subject}` | `subject` | 表單主旨 |
| `${fi.code}` | `secure_code` | 表單實例代碼 |
| `${fi.status}` | `status` | 表單狀態 |

- 固定清單，不可自定義
- 值來自 model 欄位，不查 form_data

### 4.3 `v.` — 流程變數

使用者透過 OpSet、SqlExecutor、FormAdapter 等節點自行定義的變數。

```
${v.approval_result}     → 簽核決策
${v.counter}             → 計數器
${v.total_amount}        → 計算結果
```

- 存儲於 `fw_workflow_variables` 表
- 具備三種作用域 (見第 5 節)
- 讀取優先序：NODE > FLOW > TREE

### 4.4 `wi.` — 流程資訊

取自 `FwWorkflowInstance` model 欄位，固定清單：

| 變數 | 來源欄位 | 說明 |
|------|---------|------|
| `${wi.code}` | `secure_code` | 流程實例代碼 |
| `${wi.exec_code}` | `execution_code` | 流程執行代碼 |
| `${wi.name}` | `workflow_template.name` | 流程模板名稱 |
| `${wi.status}` | `status` | 流程狀態 |
| `${wi.depth}` | `workflow_depth` | 子流程深度 (0=主流程) |

- 每個流程實例取自己的值
- 子流程中 `${wi.code}` 是子流程自己的 code，不是父流程的

### 4.5 `n.` — 節點上下文

取自當前 handler 的 `queue_item`，per-node 解析：

| 變數 | 來源 | 說明 |
|------|------|------|
| `${n.name}` | `queue_item.node_name` | 節點顯示名稱 |
| `${n.id}` | `queue_item.node_id` | 節點 ID |
| `${n.type}` | `queue_item.node_type` | 節點類型 |

- 並發執行時各 handler 有獨立的 queue_item，不會互相干擾

### 4.6 `t.` — 時間

執行時動態產生：

| 變數 | 格式 | 範例 |
|------|------|------|
| `${t.now}` | `YYYY-MM-DD HH:MM:SS` | `2026-02-21 14:30:00` |
| `${t.date}` | `YYYY-MM-DD` | `2026-02-21` |
| `${t.time}` | `HH:MM:SS` | `14:30:00` |

- 每次 `replace_variables()` 呼叫時取當下時間
- 並發的不同節點會拿到各自的時間

---

## 5. 作用域 (Scope)

### 5.1 三層作用域

| Scope | 隔離鍵 | 生命週期 | 說明 |
|-------|--------|---------|------|
| **TREE** | `root_instance_code` | 整棵流程樹結束 | 跨父子流程共享 |
| **FLOW** | `workflow_instance_secure_code` | 單一流程實例結束 | 現有 GLOBAL 的取代 |
| **NODE** | `workflow_instance_secure_code` + auto-cleanup | 節點執行完成後清除 | 現有 LOCAL 的取代 |

### 5.2 Scope 命名對照 (新舊)

| 舊名 | 新名 | 變更原因 |
|------|------|---------|
| — (不存在) | TREE | 新增：跨流程共享 |
| GLOBAL | FLOW | GLOBAL 暗示全系統，FLOW 精準表達「單一流程」 |
| LOCAL | NODE | LOCAL 不表達是什麼 local，NODE 明確 |

### 5.3 讀取優先序

當同名變數存在於多個 scope 時：

```
NODE > FLOW > TREE
(最近的覆蓋最遠的)
```

### 5.4 `fw_workflow_variables` 表結構變更

```sql
-- var_type 欄位值變更
-- 舊: 'GLOBAL', 'LOCAL'
-- 新: 'TREE', 'FLOW', 'NODE'

-- TREE scope 使用 root_instance_code 而非 workflow_instance_secure_code
-- 需要新增欄位或調整查詢邏輯
```

### 5.5 TREE scope 的隔離鍵

- 使用 `root_instance_code` (在 `FwWorkflowInstance` 上已存在)
- 主流程：`root_instance_code = 自身 secure_code`
- 子流程：`root_instance_code = 最頂層主流程的 secure_code`
- 同一棵流程樹的所有實例共享同一個 `root_instance_code`

### 5.6 Scope 使用場景

| 場景 | 建議 Scope | 說明 |
|------|-----------|------|
| 節點間傳值 (同一流程) | FLOW | 一般用途 |
| 臨時計算中間值 | NODE | 用完即棄 |
| 父子流程間共享 | TREE | 跨流程變數傳遞 |
| OpSet 預設 | FLOW | 保持現有行為 |
| FormAdapter output | FLOW | 決策結果供後續節點使用 |
| SqlExecutor result | FLOW | 查詢結果供後續節點使用 |
| SubFlow paramMapping | TREE | 取代 TODO 的 input/output 映射 |

---

## 6. VariableService API 變更

### 6.1 新 API

```python
class VariableService:

    # TREE scope
    @staticmethod
    def get_tree_var(root_code: str, var_name: str, default=None) -> Any
    @staticmethod
    def set_tree_var(root_code: str, var_name: str, value: Any, ...) -> FwWorkflowVariable

    # FLOW scope (取代 get_global_var / set_global_var)
    @staticmethod
    def get_flow_var(instance_code: str, var_name: str, default=None) -> Any
    @staticmethod
    def set_flow_var(instance_code: str, var_name: str, value: Any, ...) -> FwWorkflowVariable

    # NODE scope (取代 get_local_var / set_local_var)
    @staticmethod
    def get_node_var(instance_code: str, var_name: str, default=None) -> Any
    @staticmethod
    def set_node_var(instance_code: str, var_name: str, value: Any, ...) -> FwWorkflowVariable

    # 統一讀取 (優先序: NODE > FLOW > TREE)
    @staticmethod
    def get_var(instance_code: str, root_code: str, var_name: str, default=None) -> Any

    # 取得所有可見變數
    @staticmethod
    def get_all_vars(instance_code: str, root_code: str) -> Dict[str, Any]
```

### 6.2 BaseNodeHandler API 變更

```python
class BaseNodeHandler:

    # 讀取 (自動查 NODE > FLOW > TREE)
    def get_var(self, var_name: str, default=None) -> Any

    # 寫入 (明確指定 scope)
    def set_tree_var(self, var_name: str, value: Any)
    def set_flow_var(self, var_name: str, value: Any)
    def set_node_var(self, var_name: str, value: Any)

    # replace_variables() — 統一前綴解析
    def replace_variables(self, text: str) -> str
```

---

## 7. `replace_variables()` 解析規則

### 7.1 解析順序

```
輸入文字 → 正則提取 ${...} → 依前綴分派 → 替換
```

解析器依前綴判斷：

```python
prefix_handlers = {
    'f.':  _resolve_form_field,       # 表單欄位
    'fi.': _resolve_form_info,        # 表單資訊
    'v.':  _resolve_variable,         # 流程變數 (NODE > FLOW > TREE)
    'wi.': _resolve_workflow_info,    # 流程資訊
    'n.':  _resolve_node,             # 節點上下文
    't.':  _resolve_time,             # 時間
}
```

### 7.2 無前綴裸名處理 (過渡期)

```
${approval_result}  →  警告 log + fallback 查 v. scope
```

過渡期結束後，無前綴裸名替換為空字串並記錄錯誤。

### 7.3 新式顯示變數 (設計器 UI 專用)

```
${請假申請單::姓名}  →  設計器顯示格式，不是引擎語法
```

- 設計器存儲時轉換為 `${f.field_key}`
- 設計器顯示時將 `${f.field_key}` 反查為人類可讀格式
- `replace_variables()` 不再直接處理 `::` 語法

---

## 8. 設計器 UI 影響

### 8.1 變數插入

設計器在使用者選擇變數時：
- UI 顯示人類可讀名稱（如「請假申請單 > 姓名」）
- 插入到節點配置時存為 `${f.applicant_name}`
- 流程變數插入為 `${v.my_var}`

### 8.2 變數總覽面板 (Tab 5)

掃描所有節點配置，依前綴分類顯示：

```
表單類
  f.days          [READ]  Telegram-1, Email-1
  fi.applicant    [READ]  Telegram-1
  fi.serial       [READ]  Email-1

流程類
  v.decision      [SET]   FormAdapter-1    [READ] Branch-1
  v.counter       [SET]   OpSet-1, OpSet-2
```

### 8.3 表單欄位面板 (Tab 4)

不變，仍顯示配對表單的欄位清單。
但「變數」欄統一顯示 `${f.field_key}` 格式。

---

## 9. 節點類型與變數操作對照

| 節點類型 | SET (寫入) | READ (讀取) | 預設 Scope |
|---------|-----------|------------|-----------|
| OpSet | `v.xxx` (可選 scope) | value 中的 `${...}` | FLOW |
| FormAdapter | `v.xxx` (output_variable) | input_variables 中的 `${...}` | FLOW |
| SqlExecutor | `v.xxx` (result_var) | SQL 中的 `${...}` | FLOW |
| OpFieldWrite | — | 寫入值中的 `${...}` | — |
| Branch | — | 條件中的 `${...}` | — |
| SubFlow | — | — | TREE (共享) |
| Telegram | — | 訊息中的 `${...}` | — |
| EmailAdapter | — | subject/body 中的 `${...}` | — |

---

## 10. 遷移計劃

### Phase 1: 規格確認
- [x] 本文件經討論定稿
- [x] 建立 Forgejo Issue 追蹤

### Phase 2: 後端核心 ✅
- [x] `fw_workflow_variables.var_type`: GLOBAL→FLOW, LOCAL→NODE, 新增 TREE
- [x] `VariableService` API 改名 + 新增 TREE scope
- [x] `BaseNodeHandler` API 改名
- [x] `replace_variables()` 重寫前綴解析邏輯 (f./fi./v./wi./n./t.)
- [x] `fi.*` 變數實作 (applicant_name 等 model 欄位)
- [x] DB migration script (029_variable_system_v2.sql)
- [x] `root_instance_code` 欄位新增 + 索引

### Phase 3: 前端設計器 ✅
- [x] 變數總覽 SET/READ 顯示 `v.` 前綴
- [x] 表單欄位面板顯示 `${f.key}` 引用語法
- [x] `_extractVarRefs` 排除 f./fi./wi./n./t. 前綴
- [x] Branch 條件面板支援 v2 前綴

### Phase 4: 節點 Handler 更新 ✅
- [x] 舊 API deprecated aliases 保留 (set_global_var→set_flow_var)
- [x] SubFlow handler: paramMapping 改用 TREE scope (實作完成)
- [x] Branch handler: _resolve_value 支援 f./fi./v. 前綴
- [x] variable_mapping API: 系統變數改為 fi. 前綴

### Phase 5: 相容與清理 ✅
- [x] 舊語法 fallback (form./workflow./timestamp./node. + 無前綴裸名)
- [x] 舊 API 別名 (get_global_var → get_flow_var) 標記 deprecated
- [x] 遷移既有節點配置中的變數語法 (`scripts/migrate_variable_syntax.py`，支援 --dry-run)
- [x] OpSet handler `_evaluate_value()` 改用 `replace_variables()` 統一解析
- [x] OpSet handler `_evaluate_expression()` 支援 v2 前綴 (v./f.)
- [x] NODE scope 自動清理：`node_runner.py` 節點完成後呼叫 `cleanup_node_vars()`
- [ ] 確認所有流程穩定運行後移除 legacy fallback（非急迫，留觀察期）

---

## 11. 決議記錄

| 項目 | 決議 | 日期 |
|------|------|------|
| Scope 命名 | TREE / FLOW / NODE | 2026-02-21 |
| 前綴命名 | `f.` / `fi.` / `v.` / `wi.` / `n.` / `t.` | 2026-02-21 |
| 新式顯示變數 | 純 UI 顯示層，存儲用 `${prefix.name}` | 2026-02-21 |
| NODE scope 清除 | 節點完成後自動清除 | 2026-02-21 |
| SubFlow 變數傳遞 | 使用 TREE scope，保留 paramMapping 結構做明確映射 | 2026-02-21 |

---

*文件版本: v1.0 (confirmed)*
