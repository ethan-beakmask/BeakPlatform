# NT-31 OpHrLookup 人事資料取值節點規格

`OpHrLookup` 會把目標成員的職級、職稱、職系、部門、直屬主管與核決資料寫入流程變數，供後續 `Branch` 與 `FormAdapter` 動態簽核人使用。

## 直屬主管推導

`EmployeePosition.direct_manager_secure_code` 已於 2026-09-05（PF-247 第 4 期）退役。直屬主管只由部門角色推導：

1. 申請人單位先用 `resolve_user_unit()` 解析，找不到時直屬主管為空。
2. 查同企業、未刪除的 `DEPT_MANAGER` 角色；角色不存在時主管鏈為空。
3. 從申請人單位開始，依序走 `[申請人單位, 父, 祖父, ...]`。
4. 每一層先取**單位指派**（`unit_secure_code`＝該單位）的有效 `DEPT_MANAGER` 持有人；單位指派沒有可用的人（職缺、或只有申請人本人）才退回**全企業指派**（unit NULL）；同類內多人依 `assigned_at`、`id` 順序（2026-09-05 PF-247 補丁 4a 起；此前兩類混排、全企業指派較早者會壓過單位主管）。
5. 申請人本人是該層主管，或該層職缺時，往上一層找；同一人身兼多層主管只算一站。
6. 副主管、代理人一、代理人二不算直屬主管；主管推導不看請假，請假只在簽核授權層處理。

## 職位選取規則

1. 目標成員來源：
   - `target_source=applicant`：使用表單申請人 `form_instance.applicant_secure_code`
   - `target_source=variable`：先對 `target_expr` 執行 `replace_variables()`，結果作為 user secure_code
2. 目標 user 必須存在、`is_deleted=false`、`is_active=true`，且 `org_secure_code` 必須等於 queue item 的企業。
3. 生效日使用 `Organization.local_today()`，禁止用主機日期。
4. 候選職位必須符合：
   - `user_secure_code=目標 user`
   - `org_secure_code=queue_item.org_secure_code`
   - `is_deleted=false`
   - `is_active=true`
   - `effective_from <= today`
   - `effective_until IS NULL OR effective_until >= today`
5. 排序：
   - `position_type='PRIMARY'` 優先
   - 其餘取 `effective_from` 最早者
   - 再平手取 `id` 最小者
6. 找不到 user 或有效職位時，節點仍同步回 success；`<prefix>_found='false'`，其他輸出變數寫空字串，並記 warning。

## 輸出變數

以下以預設前綴 `hr` 表示。`var_prefix` 只允許 `[A-Za-z_][A-Za-z0-9_]*`；不合法時改用 `hr` 並記 warning。

| 變數 | 值 |
|---|---|
| `hr_found` | 是否取到有效職位，字串 `true` / `false` |
| `hr_user_code` | 目標 user secure_code |
| `hr_user_name` | 目標 user display_name |
| `hr_position_type` | `PRIMARY` / `CONCURRENT` / `ACTING` / `TEMPORARY` |
| `hr_job_title` | 職稱名稱 |
| `hr_job_title_code` | 職稱代碼 |
| `hr_job_title_short` | 職稱簡稱 |
| `hr_is_supervisor` | 職稱是否主管，字串 `true` / `false` |
| `hr_job_level_code` | 職等代碼 |
| `hr_job_level_name` | 職等名稱 |
| `hr_job_level_order` | 職等排序，整數 |
| `hr_job_level_is_manager` | 職等是否管理職，字串 `true` / `false` |
| `hr_job_family_code` | 職系代碼 |
| `hr_job_family_name` | 職系名稱 |
| `hr_job_family_type` | `MANAGER` / `PROFESSIONAL` |
| `hr_job_family_root_code` | 職系根節點 code；兩層樹，最多往上查一層 |
| `hr_unit_code` | 部門代碼 |
| `hr_unit_name` | 部門名稱 |
| `hr_is_unit_head` | 是否部門主管，字串 `true` / `false` |
| `hr_direct_manager` | 由部門推導的直屬主管 user secure_code |
| `hr_direct_manager_name` | 由部門推導的直屬主管 display_name |
| `hr_direct_manager_unit` | 主管所在單位 code |
| `hr_direct_manager_unit_name` | 主管所在單位名稱 |
| `hr_approval_limit` | `approval_category_code` 非空時輸出；類別存在但無 limit 或 NULL 時為 `0`；類別不存在或停用時為空字串 |

## 核決人模式

`approver_mode=true` 時，節點會額外輸出：

| 變數 | 值 |
|---|---|
| `hr_approver` | 達標主管 user secure_code |
| `hr_approver_name` | 達標主管 display_name |
| `hr_approver_level_code` | 達標主管職等代碼 |
| `hr_approver_unit` | 達標主管所在單位 code |
| `hr_approver_unit_name` | 達標主管所在單位名稱 |
| `hr_approver_found` | 是否找到核決人，字串 `true` / `false` |

規則：

1. 必須同時設定 `approval_category_code` 與 `amount_expr`；缺任一時 `hr_approver_found='false'`，其他核決人變數寫空字串。
2. `amount_expr` 先 `replace_variables()`，移除逗號與空白後轉 `Decimal`；失敗時同上。
3. 從目標成員的直屬主管（部門推導第一站）開始，不包含目標本人；沿祖先單位的主管往上，一人只算一站。
4. 每一站主管必須同企業、未刪除、啟用（`resolve_role_holders` 已保證）。
5. 每一站以主管有效任職卡（同一套選取規則）的職等查 `JobLevelApprovalLimit`；主管沒有有效任職卡、無記錄或 NULL 一律視為 0，繼續往上。
6. 第一個 `approval_limit >= amount` 的主管即為核決人。
7. 到根仍無或超過 20 站時停止，`hr_approver_found='false'`。

## 已知限制

- 職系樹目前依資料模型規格只支援兩層，根節點查找最多往上一層。
- 核決金額不做幣別轉換，僅使用指定核決類別的數值上限比較。
- 本節點只同步寫流程變數，不會改變 `FormAdapter`、`Branch` 或 executor 行為。
