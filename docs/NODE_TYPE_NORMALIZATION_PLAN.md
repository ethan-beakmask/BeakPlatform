# Node Type 命名正規化計劃（方案 C）

> 建立日期: 2026-02-08
> 狀態: Phase 1-4 完成，待用戶瀏覽器驗證 (4.5)
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

### Phase 1: normalizeNodeType 修正 ✅
- [x] 1.1 修改 `normalizeNodeType()` 函數：key 改全 lowercase + `.toLowerCase()` 查表
- [x] 1.2 補齊所有 21 個 DB node type 的映射（含底線和無底線兩種 key）
- [x] 1.3 移除不存在的 `OPCOPY` 映射（DB 無此 type，已刪除）

### Phase 2: JS 硬編碼類型比較修正 ✅
- [x] 2.1 修正 `SQLExecutor` → `SqlExecutor` 拼寫錯誤 (行 3572)
- [x] 2.2 簡化 End 節點三重判斷 → 統一為 `'End'` (行 4512)
- [x] 2.3 `nodesWithSettings` 補齊 `SqlExecutor`（原缺漏）
- [x] 2.4 全面掃描完成：Cytoscape CSS selector 統一 (Start/End)、graph 載入時 normalize type、isNewWorkflow 判斷修正

### Phase 3: API 層 node_type 命名清理 ✅
- [x] 3.1 比對完成：DB 21 → API 22，差異為 APPROVE→FORMADAPTER (改名) 和 EMAILADAPTER (API 獨有)
- [x] 3.2 API 保持 PascalCase，由 normalize 層吸收差異（DB 表未被後端查詢，僅作參考）
- [x] 3.3 DB 同步：APPROVE → FORMADAPTER、新增 EMAILADAPTER，現 DB 22 rows 與 API 一致

### Phase 4: 驗證 ✅
- [x] 4.1 API node-definitions 回傳正常，22 個 type 值正確
- [x] 4.2 normalizeNodeType 驗證：22 個 API type + 22 個 DB type 全部正確映射
- [x] 4.3 SubFlow → Subflow 轉換確認（唯一需要轉換的 API type）
- [x] 4.4 DB ALL_CAPS type 全部正確轉換（模擬舊 graph 載入）
- [ ] 4.5 **待用戶手動驗證**：瀏覽器打開 designer，拖拉 SubFlow/SysTelegram/EmailRelay 節點，確認設定面板顯示

### Phase 5: 文件更新 ✅
- [x] 5.1 更新本文件 checklist 狀態
- [x] 5.2 無架構變更，不需更新 PLATFORM_MODULARIZATION_PLAN.md
- [x] 5.3 Forgejo Issue 待瀏覽器驗證後關閉

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
