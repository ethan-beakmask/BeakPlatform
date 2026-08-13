# 交接提示詞:API 層缺細粒度授權(PageRoleGuard 跳過 /api/)

> 把這份文件**整段貼給下一次對話的 Claude**(在 `/opt/BeakPlatform-dev/` 開的對話)。
> 這是既有安全稽核發現的結構性缺口之一,已壓縮成接手包。

---

## 你接手的脈絡

前一輪對話針對「appscan 登入後仍看見授權外項目」做了權限安控稽核,修掉了兩個立即破口:

1. PageRoleGuard 對 user_type 不符的頁面由「放行」改「fail-closed 擋下」(`services/page_role_guard.py`)。
2. 10 個 `@login_required` API 收斂為 `@admin_required`(numbering / enterprise_data / modules)。

稽核過程中確認**還有兩個超出當輪範圍的架構弱點**,這份是其中第二個(另一個見 `dev-notes/handoff_authz_list_rbac.md`)。

---

## 這個弱點是什麼

**PageRoleGuard(雙鑰匙頁面守衛)整段跳過 `/api/`,API 的細粒度授權完全靠各端點自己的 decorator 自律。**

- 位置:`backend/app/services/page_role_guard.py` 的 `SKIP_PREFIXES`,其中含 `/api/`。
- 網頁(非 /api/)請求會經過 PageRoleGuard,依 `menu_items` + `menu_permissions`(Key1 user_type)+ `menu_role_requirements`(Key2 角色)做雙鑰匙檢查。
- **API 請求完全不經過這套**,唯一關卡是各端點掛的 `@login_required` / `@admin_required` / `@system_admin_required` / `@module_access_required`。
- 這些 decorator 只能表達「四個硬等級」+「模組合約/ACL」,**無法表達「這個 API 對應到某選單、需要某角色」**。

**後果**:登入後用「角色」細化的可視控制,在 API 層沒有統一執法點。網頁被 Key2 角色守衛擋住的功能,若對應的 API 只掛四層 decorator,同層級但無該角色的使用者仍可直接打 API 拿到資料/執行操作。與 `handoff_authz_list_rbac.md`(list 不做 RBAC)疊加後,API 層等於幾乎沒有角色細分。

---

## 必讀(按順序)

1. `CLAUDE.md` — 專案規範,AUTH-01/02、TENANT-02、manifest 流程、安全核心禁區
2. `dev-notes/manifests/security-core.yaml` — 確認 page_role_guard.py / auth_interceptor.py 是禁區
3. `dev-notes/manifests/SECURITY_PITFALLS.md` — 第 3 點(雙鑰匙選單安全)
4. `backend/app/services/page_role_guard.py` — 主角,看 `SKIP_PREFIXES` 與 `check_access` 的比對三策略
5. `backend/app/security/auth_interceptor.py` — PageRoleGuard 在 before_request 的呼叫點
6. `backend/app/security/decorators.py` — 現有四層 + module_access + permission_required decorator
7. `backend/app/services/menu_service.py` 與 `_menu_tree.py` — 網頁側是怎麼做角色過濾的(要對齊的語意)

---

## 設計難點(要先跟用戶討論清楚,不要直接寫)

1. **API 沒有選單對應關係**。網頁靠 URL/endpoint 反查 `menu_items`,但 API 端點(如 `/api/users/<sc>`)不在 `menu_items` 裡,無法直接沿用同一套 URL→menu 比對。需要決定映射方式:
   - 方案 a:每個 API 端點宣告它「服務哪個選單/功能」(新 decorator 參數,如 `@guarded_by_menu('users')`),再共用 Key2 角色檢查。
   - 方案 b:改用 `@permission_required('user','read')` 這類 RBAC decorator 逐一標註 API(檔案已有此 decorator,目前幾乎沒用)。
   - 方案 c:把 API 與其對應的網頁 endpoint 綁定,由 API decorator 反查該網頁的角色需求。
2. **blast radius 極大**:web/ 885 條 + modules/ 大量 API。逐一標註是大工程,要分批(先最敏感的 users/roles/organizations/permissions)。
3. **與 module_access_required 的關係**:模組 API 已有合約 + ACL 檢查,角色細分要疊在其上還是取代,需釐清。
4. **不要重蹈覆轍**:網頁側 PageRoleGuard 曾經 fail-open(「選單藏起來就算數」),前一輪已修。API 層設計時要一開始就 fail-closed 思維,別再把「前端不顯示按鈕」當安全。

---

## 建議做法(草案,待用戶定案)

- 先做**盤點與分類**:延用前一輪的稽核腳本(用 Flask `app.url_map` 比對每個 `/api/` 端點的 decorator),對每個端點標記「該不該有角色細分、對應哪個功能」,產出表給用戶定案。
- 選一個**統一機制**(建議方案 b 的 `@permission_required`,因為 RBAC 基礎設施 `PermissionService` 已完整),不要每支 API 各寫各的。
- **分批上線**,每批配一個低權限測試帳號做 before/after 驗收(該擋的擋、該通的通、admin 不受影響)。

---

## 邊界

- 這是 security-core 禁區,**先討論清楚方案再動手**。
- 別動 `ResourceGateway.list()` 的 RBAC(那是 `handoff_authz_list_rbac.md` 的範圍),但兩者最終要協同:decorator 管「能不能呼叫這支 API」,ResourceGateway 管「回傳的每一筆資料能不能看」。
