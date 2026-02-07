# Node Type 命名正規化計劃（方案 C）

> 建立日期: 2026-02-08
> 狀態: 待執行
> 關聯 Issue: #8 (代碼層命名重構的延伸)

---

## 問題摘要

workflow node type 在三個層級使用不同命名，導致設定面板無法顯示：

| DB (workflow_node_definitions) | API (_get_node_definitions) | JS normalizeNodeType 輸出 | JS 面板判斷 |
|---|---|---|---|
| `SUBFLOW` | `SubFlow` | `Subflow` | `Subflow` → **API 輸入不匹配** |
| `SQLEXECUTOR` | `SqlExecutor` | (無) | `SQLExecutor` → **拼寫錯誤** |
| `PARALLEL_FORK` | `ParallelFork` | (無映射) | (無) |
| `PARALLEL_JOIN` | `ParallelJoin` | (無映射) | (無) |
| `END` | `End` | (無) | `end`/`End`/`END` → **硬寫三種** |

**已確認影響**: SubFlow 設定面板完全無法顯示（使用者點擊只看到名稱欄位）。

---

## 方案 C：normalizeNodeType 不區分大小寫 + 補齊完整清單

### 核心改動

`normalizeNodeType()` 改為：
```javascript
function normalizeNodeType(type) {
    if (!type) return type;
    const typeMap = {
        // key 全部 lowercase，value 為 JS 標準 PascalCase
        'start': 'Start',
        'end': 'End',
        'formadapter': 'FormAdapter',
        'delay': 'Delay',
        'branch': 'Branch',
        'condition': 'Condition',
        'switch': 'Switch',
        'converge': 'Converge',
        'parallelfork': 'ParallelFork',
        'parallel_fork': 'ParallelFork',
        'paralleljoin': 'ParallelJoin',
        'parallel_join': 'ParallelJoin',
        'subflow': 'Subflow',
        'notification': 'Notification',
        'telegram': 'Telegram',
        'emailadapter': 'EmailAdapter',
        'opset': 'OpSet',
        'opfieldread': 'OpFieldRead',
        'op_fieldread': 'OpFieldRead',
        'opfieldwrite': 'OpFieldWrite',
        'op_fieldwrite': 'OpFieldWrite',
        'formexp': 'FormExp',
        'emailrelay': 'EmailRelay',
        'sqlexecutor': 'SqlExecutor',
        'sys_telegram': 'SysTelegram',
        'systelegram': 'SysTelegram',
        'abandon': 'Abandon',
        'opcopy': 'OpCopy',
    };
    return typeMap[type.toLowerCase()] || type;
}
```

**關鍵**: `type.toLowerCase()` 查表，無論輸入 `SubFlow`、`SUBFLOW`、`subflow` 都能正確映射。

---

## Checklist

### Phase 1: normalizeNodeType 修正
- [ ] 1.1 修改 `normalizeNodeType()` 函數：key 改全 lowercase + `.toLowerCase()` 查表
- [ ] 1.2 補齊所有 21 個 DB node type 的映射（含底線和無底線兩種 key）
- [ ] 1.3 移除不存在的 `OPCOPY` 映射（或確認是否需要保留）

### Phase 2: JS 硬編碼類型比較修正
- [ ] 2.1 修正 `SQLExecutor` → `SqlExecutor` 拼寫錯誤 (行 3556)
- [ ] 2.2 簡化 End 節點三重判斷 `end`/`End`/`END` → 統一為 `End` (行 4496)
- [ ] 2.3 確認 `nodesWithSettings` 陣列完整性 (行 3317-3321)
- [ ] 2.4 全面搜索 JS 中所有 `type === '...'` 硬編碼比較，確認與 normalize 輸出一致

### Phase 3: API 層 node_type 命名清理
- [ ] 3.1 比對 API `_get_node_definitions()` 的 node_type vs DB `workflow_node_definitions.node_type`
- [ ] 3.2 確認 API 是否需要統一改為與 DB 一致（或保持 PascalCase，由 normalize 層吸收差異）
- [ ] 3.3 補齊 API 缺少的 node type（DB 有 21 個，API 只有 18 個）

### Phase 4: 驗證
- [ ] 4.1 啟動服務，在 standalone designer 拖拉 SubFlow 節點，確認設定面板正常顯示
- [ ] 4.2 測試 SysTelegram 節點設定面板
- [ ] 4.3 測試 EmailRelay 節點設定面板
- [ ] 4.4 測試從 DB 載入舊流程（含 ALL_CAPS node type），確認 normalize 正確
- [ ] 4.5 測試 SqlExecutor 節點設定面板

### Phase 5: 文件更新
- [ ] 5.1 更新本文件 checklist 狀態
- [ ] 5.2 如有架構變更，更新 `PLATFORM_MODULARIZATION_PLAN.md`
- [ ] 5.3 關閉相關 Forgejo Issue

---

## 影響範圍

### 檔案清單
| 檔案 | 改動內容 |
|---|---|
| `modules/form_workflow/static/modules/form_workflow/js/workflow-main.js` | normalizeNodeType + 硬編碼修正 |
| `modules/form_workflow/api/workflows.py` | (Phase 3) API node_type 命名 |

### 風險評估
- **低風險**: normalizeNodeType 是純函數，改動不影響資料
- **低風險**: 所有比較都經過 normalize，統一入口
- **注意**: 已儲存的流程 graph JSON 中的 node type 值不會被改動，需確保 normalize 能涵蓋

---

## 相關檔案定位

- DB 定義: `workflow_node_definitions` 表
- API 定義: `modules/form_workflow/api/workflows.py` → `_get_node_definitions()` (行 62-348)
- JS normalize: `modules/form_workflow/static/modules/form_workflow/js/workflow-main.js` → `normalizeNodeType()` (行 3239-3257)
- JS 面板渲染: 同上 → `showNodeInfo()` (行 3260-4540)
- JS 硬編碼比較位置: 行 3272, 3286, 3317, 3347, 3454, 3509, 3556, 3610, 3687, 3795, 3935, 4102, 4182, 4281, 4393, 4496, 4550
