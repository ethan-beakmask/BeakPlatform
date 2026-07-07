# 交接提示詞:ResourceGateway list/filter 缺 RBAC 過濾

> **狀態更新 (2026-07-06)**:階段 A 已完成。
> - `list()`/`filter()`/`count()`/`exists()` 新增 opt-in `require_permission` 參數(`_check_list_permission`),未通過拋 `PermissionDeniedError`(全域 handler 回 403)。
> - 已接上:`api/users.py list_users`(user:read)、`web/roles.py list_roles`(role:read)、`api/organizational_units.py list_units`(department:read)。
> - **偏差**:`api/organizations.py list_organizations` 未接。原因:`organization:read` 是 SYSTEM 級,[SEC-02] 已移除 SYSTEM_ADMIN 捷徑且 roles 表無 SYSTEM_ADMIN 角色(靠 user_type 判定),接上會讓所有系統管理員 403。該端點已有 `@system_admin_required` 把關。
> - `/units/groups` 端點也未接:它是 `@login_required` 且自帶「團長只看管理群組」縮限,接 department:read 會弄壞團長流程。
> - 階段 B(fail-open 翻 fail-closed)未做,仍待另案討論。

> **狀態更新 (2026-07-06 第二輪)**:階段 B 機制完成,採漸進推進。
> - `list()`/`filter()` 新增 `check_permission=True` 參數:model 在 `LIST_RBAC_ENFORCED_MODELS` 集合內時自動檢查 `{resource_type}:read`,逃生門 `check_permission=False`。
> - 首批範例:JobFamily(job_family)、DutyCategory(duty_category),已註冊 map + seed 權限代碼 + 驗證三身分。
> - 新增可重複執行的 seed 腳本:`scripts/seed_resource_permissions.py <type> [--level ORG|SYSTEM|MODULE]`（已移出 migrations/，跑完須同步進編號 migration，見 075）。
> - **全域 fail-closed 尚未翻轉**:未在集合內的 model 仍 fail-open。剩餘 29 個 model 依「每批 5 個」節奏補做,每批流程:seed 權限代碼 -> 加入 MODEL_RESOURCE_TYPE_MAP 與 LIST_RBAC_ENFORCED_MODELS -> 盤點該 model 全部呼叫端身分可達性(EMPLOYEE 可達端點要先授權或加 check_permission=False) -> 三身分冒煙。全部完成後才評估把 `_get_resource_type() -> None` 改為拋例外。
> - **SYSTEM 級資源(Organization/Contract 等)留到最後**:需先建 SYSTEM_ADMIN 角色並授 SYSTEM 權限(roles 表目前沒有此角色,[SEC-02] 已無 user_type 捷徑)。
> - 剩餘 29 個 model 清單(依呼叫次數):DcSubSystem、WorkSchedule、JobLevel、Duty、JobTitle、DcPageLayout、SmtpConfig、UserNumberingRule、Page、DcCrudView、Contract、RecipientGroup、TelegramConfig、ApprovalCategory、Delegation、DcSubSystemPage、EmployeePosition、DcPageTemplate、JobLevelApprovalLimit、Form、UserRoleAssignment、DcBackground、DcSiteMapNode(其中 6 個已在 map 但未在 enforced 集合:User、Organization、OrganizationalUnit、Role、Module、MenuItem)。

> **狀態更新 (2026-07-06 第三輪)**:第二批 10 個完成(HR/通知設定家族,全部呼叫端 @admin_required,零誤傷)。
> - 已 enforced:JobLevel、JobTitle、Duty、WorkSchedule、ApprovalCategory、JobLevelApprovalLimit、SmtpConfig、TelegramConfig、RecipientGroup、UserNumberingRule(+首批 JobFamily、DutyCategory,共 12 個)。
> - 批次大小改為**依關聯性分組**,不固定數量(用戶指示)。剩餘分組建議:
>   1. ~~**Dc* 子系統家族(7 個)**~~ **已處理 (2026-07-06 第四輪)**:DcPageTemplate、DcSiteMapNode 已 enforced(呼叫端全 admin);DcSubSystem、DcCrudView、DcPageLayout、DcSubSystemPage、DcBackground 列入新的 `RBAC_EXEMPT_MODELS` 明確豁免清單(閘門為模組合約 + 模組 ACL + 子系統權限政策,端用戶 portal 與設計師流程皆會員層級可達,疊平台 RBAC 會癱瘓 portal)。豁免清單即 fail-closed 翻轉時的白名單依據。
>   2. ~~員工自助類~~ ~~平台核心~~ ~~已註冊未 enforced~~ ~~SYSTEM 級~~ **全部完成,見下方最終狀態**

> **最終狀態 (2026-07-06 第五輪) -- 階段 B 收尾完成**
>
> **Enforced(list/filter 自動檢查 {type}:read,共 24 個)**:
> JobFamily、DutyCategory、JobLevel、JobTitle、Duty、WorkSchedule、ApprovalCategory、
> JobLevelApprovalLimit、SmtpConfig、TelegramConfig、RecipientGroup、UserNumberingRule、
> DcPageTemplate、DcSiteMapNode、Delegation、EmployeePosition、UserRoleAssignment、
> User、Role、OrganizationalUnit、Module、MenuItem、Organization、Contract
>
> **明確豁免(RBAC_EXEMPT_MODELS,各附理由)**:DcSubSystem、DcCrudView、DcPageLayout、
> DcSubSystemPage、DcBackground(nocode 模組 ACL 把關)、Page(page_permission_service 自身即閘門)。
> Form 無實際 gateway 呼叫端(僅 docstring 範例),無需處理。
>
> **逃生門(check_permission=False,各附註解)**:
> - `api/organizational_units.py` list_groups x2(團長分流縮限)
> - `modules/form_workflow/api/fc_utils.py` get_org_tree(員工填單選簽核人)
> - `api/contracts.py` list_my_contracts(contract:read 是 SYSTEM 級,org admin 看自己合約由 decorator+租戶過濾把關)
>
> **SYSTEM_ADMIN 角色已建置**:`scripts/migrations/076_seed_system_admin_role.py`（系統企業由 DB code=SYSTEM 動態解析）
> (角色+全權限授予+指派給 user_type=SYSTEM_ADMIN 帳號)。階段 A 擱置的
> list_organizations 現已被 enforced 覆蓋,sysadmin 走 RBAC 通過。
>
> **唯一遺留**:全域 fail-closed 翻轉(`_get_resource_type() -> None` 改拋例外)
> 尚未執行。目前所有「有 gateway 呼叫端的 model」都已 enforced 或明確豁免,
> 翻轉只影響未來新增的 model(強迫開發者表態)。屬低風險小改動,
> 可與 handoff_authz_api_guard.md 一併處理或另行指示。

> 把這份文件**整段貼給下一次對話的 Claude**(在 `/opt/BeakPlatform-dev/` 開的對話)。
> 這是既有安全稽核發現的結構性缺口之一,已壓縮成接手包。

---

## 你接手的脈絡

前一輪對話針對「appscan 登入後仍看見授權外項目」做了權限安控稽核,修掉了兩個立即破口:

1. PageRoleGuard 對 user_type 不符的頁面由「放行」改「fail-closed 擋下」(`services/page_role_guard.py`)。
2. 10 個 `@login_required` API 收斂為 `@admin_required`(numbering / enterprise_data / modules)。

稽核過程中確認**還有兩個超出當輪範圍的架構弱點**,這份是其中第一個(另一個見 `docs/handoff_authz_api_guard.md`)。

---

## 這個弱點是什麼

**`ResourceGateway.list()` 與 `ResourceGateway.filter()` 只做租戶(org_secure_code)過濾,不做 RBAC 權限檢查。**

- 只有單筆 `ResourceGateway.get()` / `get_by()` 會呼叫 `_check_view_permission()`(進而走 `PermissionService.can_view`)。
- `list()` / `filter()` / `count()` / `exists()` 完全沒有權限檢查,只套租戶過濾。
- 位置:`backend/app/security/resource_gateway.py`(security-core **禁區**,改前必須與用戶確認)。

**後果**:所有走 `list()`/`filter()` 回傳集合的 API,對「同企業任何登入者」全開,登入後的「role 細化可視資料」在這條路徑上完全失效。EMPLOYEE / EXTERNAL 只要能呼叫到該端點(通過 decorator 的四層關卡),就能拿到整個租戶的列表資料,不管他的角色有沒有被授權看。

這正是平台宣稱「用 role 去細化更細的可視資料」但實際沒落實的核心原因之一。

---

## 必讀(按順序)

1. `CLAUDE.md` — 專案規範,特別是 TENANT-02(ResourceGateway 要求)、DATA-01、manifest 流程
2. `docs/manifests/security-core.yaml` — 確認這是禁區檔案,改前須用戶同意
3. `docs/manifests/SECURITY_PITFALLS.md` — 第 1、2、4、11 點(租戶隔離、帳號狀態、ResourceGateway、軟刪除)
4. `backend/app/security/resource_gateway.py` — 主角,看 `filter`/`list`/`_check_view_permission` 三者的落差
5. `backend/app/services/permission_service.py` — `can_view` / `get_all_permission_codes` 的 RBAC 語意
6. `docs/manifests/permissions.yaml` — 權限模型檔案清單

---

## 設計難點(要先跟用戶討論清楚,不要直接寫)

1. **粒度**:list 的 RBAC 該用「資源類型層級」(有 `{resource_type}:read` 就全看)還是「逐列 ABAC」(每列跑 `can_view`,如 OWNER/SAME_DEPT)?後者效能成本高(N 列 N 次評估),需要批量化或查詢下推。
2. **blast radius**:全平台大量 API 走 `filter()`。一旦 list 開始檢查權限,沒有對應 `{resource_type}:read` 權限的角色會突然看到空列表。需要先盤點:
   - 哪些 model 有註冊在 `MODEL_RESOURCE_TYPE_MAP`(目前只有 User/Organization/OrganizationalUnit/Role/Module/MenuItem)。
   - 未註冊的 model 會 `_get_resource_type() → None → 跳過檢查`,等於預設放行,這本身也是缺口。
3. **相容性**:ORG_ADMIN 對非 SYSTEM 權限一律通過(`permission_service` 已有此捷徑),所以管理員不受影響;衝擊面集中在 EMPLOYEE / EXTERNAL。
4. **效能**:`filter()` 目前是純 SQL 一次撈。逐列 ABAC 會破壞這點,可能要改成「查詢層級的條件下推」(把 OWNER/SAME_DEPT 翻成 WHERE 條件)而非取回後再過濾。

---

## 建議做法(草案,待用戶定案)

分兩階段,降低風險:

- **階段 A(低風險、先做)**:在 `list()`/`filter()` 加一個**選擇性** `require_permission='user:read'` 參數,呼叫端明確要求時才檢查資源類型層級權限。先替最敏感的列表 API(users、roles、organizational_units 等)接上,不動預設行為,避免全平台空列表。
- **階段 B(高風險、後做)**:評估是否把「未註冊資源類型 = 放行」改為「明確標記哪些 model 免檢查」,把預設從 fail-open 翻成 fail-closed。這步要全面盤點呼叫端。

**驗收**:以一個「有角色 R、R 只授權 users:read」的 EMPLOYEE 帳號,呼叫各列表 API,確認只拿到被授權的資源類型;以「無任何 read 權限」的 EMPLOYEE 確認拿到空列表或 403,且既有 admin 流程不受影響。

---

## 邊界

- 這是 security-core 禁區,**先討論清楚方案再動手**。
- 別為了「讓某頁面有資料」而放寬檢查——問題根因若在 DB 角色/權限設定,先查資料。
- 別動 PageRoleGuard 的 `/api/` 跳過邏輯,那是另一份交接(`handoff_authz_api_guard.md`)的範圍。
