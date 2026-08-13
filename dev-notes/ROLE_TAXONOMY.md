# 角色/職務名詞定版（Role Taxonomy）

> 2026-07-16 起草。背景：超過半年的迭代後，「角色」「職務」「職稱」「職位」多處混用，
> 本文件收斂各名詞的唯一語意，作為 UI 用語、文件與後續開發的依據。
> 配套：`dev-notes/PERMISSION_MODEL.md`（權限模型）、`dev-notes/GLOSSARY.md`（溝通對照表）

## 1. 現況盤點（五個概念、六個落點）

| 中文慣稱 | Model / 表 | 實際用途 | 參與權限判斷 |
|---|---|---|---|
| 角色 | `Role`（role_type=ROLE，roles 表） | 權限載體：選單鑰匙2、role_permissions、簽核人指定 | **是** |
| 職務 | `Role`（role_type=POSITION，同一張 roles 表） | 部門內的位子：部門主管、副主管、代理人(一)(二)，參與簽核鏈與代理 | **是**（與 ROLE 同機制） |
| 職務 | `Duty` + `DutyCategory`（duties 表） | 部門內職責標籤（防火牆管理員、log 稽核） | 否 |
| 職稱 | `JobTitle`（+ 職等 JobLevel、職系 JobFamily） | HR 正式頭銜（經理、工程師） | 否 |
| 職位 | `EmployeePosition` | 人 ↔ 部門 ↔ 職稱的任職關聯 | 否（ABAC 直屬關係為 TODO 未實作） |

**混亂根源**：「職務」同時指 `Role.POSITION` 與 `Duty` 兩個不相干的東西；
而 `EmployeePosition`（職位）的英文名又與 `POSITION` 撞名。

**關鍵事實（2026-07-16 盤點）**：
- 權限判斷（雙鑰匙 Key2、role_permissions、workflow 簽核人解析）只認 `roles` 表，
  **不分 ROLE/POSITION**——兩者在權限機制中完全等價，差別只在語意與指派介面。
- `Duty` 是**孤兒功能**：只有 CRUD API（`/api/duties/`）與 Model，
  全站無任何前端消費者、無任何服務引用；DB 實料 0 筆職務、1 筆分類。
- `EmployeePosition` 僅服務 HR 頁面（/positions/）；
  permission_service 中只有一行 TODO 提到它（is_subordinate_of 未實作）。

## 2. 定版語意（本文件生效後的唯一解釋）

| 名詞 | 定義 | 一句話判斷 |
|---|---|---|
| **角色（Role.ROLE）** | 權限載體。決定「看得見什麼、能做什麼」的唯一單位 | 給權限，配角色 |
| **單位職務（Role.POSITION）** | 單位（部門/社群）內的位子，隨單位指派；參與簽核鏈與代理。權限機制上就是角色的一種 | 簽核找位子，位子在單位裡 |
| **職稱（JobTitle）** | HR 描述性頭銜，配套職等/職系。不參與任何權限判斷 | 名片上印的 |
| **職位（EmployeePosition）** | 誰在哪個部門掛哪個職稱的任職記錄。不參與權限判斷 | 人事任職卡 |

UI 用語規範：
- 涉及權限、選單、簽核的介面一律用「**角色**」；需要區分時用「**單位職務**」稱呼 POSITION 型
- 「職務」兩字**不再單獨使用**（必稱「單位職務」），避免與 HR 概念及 Duty 混淆
- 「職稱/職等/職系/職位」只出現在人資架構相關頁面

## 3. 收斂決策（2026-07-16 提案，待用戶確認後定案）

1. **Duty/DutyCategory 退役**：與 Role.POSITION 概念重疊且從未被使用。
   處理：API 與 Model 標記 deprecated，保留一個版本週期後移除（duties 表無實料，無遷移負擔）。
2. **Role.POSITION 保留**，中文顯示統一為「單位職務」；不合併入 ROLE
   （互斥群組 DEPT_POSITION 等 per-unit 語意依賴它）。
3. **權限文件與 UI 敘述**以「角色（含單位職務）」描述鑰匙2 的載體。

## 4. 現存 18 個系統預設角色的歸類

| 類型 | 角色 |
|---|---|
| 身分角色（IDENTITY_TYPE 互斥） | 企業管理員、企業成員、外部廠商 |
| 單位基底角色 | 部門成員、部門員工、社群成員、社群團員、社群團長 |
| 單位職務（POSITION） | 部門主管、副主管、代理人(一)、代理人(二) |
| 功能角色（平台） | 表單設計師、流程設計師、規格管理師、子系統架構師、弱點風險管制員 |
| 模組預設角色 | 資安人員（open_defense，見 PERMISSION_MODEL 3.1） |

註：表單/流程設計師等功能角色的模組歸屬遷移為另案（BroodNest 原子 4853）。
