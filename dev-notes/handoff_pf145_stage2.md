# PF-145 階段二 交接（2026-08-23）

接手前先讀：**BBN 待辦 `PF-145`（`note_search("PF-145")`，atom 5247）**
與 **`dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`**。兩者都是自足的，本檔只寫
「下一步要做什麼」與「已經踩過不要再踩的坑」。

---

## 一、目前進度

| 項目 | 狀態 | commit |
|---|---|---|
| 階段一：open_defense 資安案件 5 支補 Key1 | 完成 | `809ea8ba` |
| 階段二：334 支模組 API 盤點清單 | 完成 | `f7b8a7fd` |
| 施工1：`/api/form-center/org-tree` 依身分裁剪 | 完成 | `95f85cd8` `cb7927e3` |
| 施工2：C 級選單唯一 29 支補 Key1 | 完成 | `f1461564` `3eabb1b2` |
| 附帶：管理員帳號發 ADM 編號（新企業＋回填） | 完成 | `3eabb1b2` `147f6f0e` |
| **施工3：B 級選單唯一 45 支** | **未開始** | — |
| 施工4：4 支掛在 `/api/` 下的頁面路由，確認去留 | 未開始 | — |
| 施工5：B 級反查不到呼叫者的 104 支 | 未開始 | — |
| 階段三：模組 ACL fail-open→fail-closed、`roles` 加 user_type 約束 | 未開始（全平台變更，要單獨評估） | — |

盤點現況（**數字會腐爛，動工前自己重跑**）：

```bash
venv/bin/python scripts/audit_module_api_gates.py            # 產 CSV
venv/bin/python scripts/audit_module_api_gates.py --summary  # 只看統計
```

2026-08-23 收工時：**A35 / B153 / C16 / D118 / E12**，共 334 支。

---

## 二、下一步（施工3）的具體做法

從 `dev-notes/pf145_module_api_audit.csv` 篩 `level=B` 且 `menu_candidates`
只有一個值的，2026-08-23 是 45 支。**一模組一 commit。**

每一支動手前的三個檢查（前兩個沒做會擋掉正牌使用者）：

1. **查該 menu_code 的 Key1／Key2 現況**：

```sql
SELECT m.code,
       string_agg(DISTINCT mp.user_type, ',') AS key1,
       string_agg(DISTINCT o.code||':'||r.code, ' | ') AS key2
FROM menu_items m
LEFT JOIN menu_permissions mp ON mp.menu_secure_code=m.secure_code AND mp.is_deleted=false
LEFT JOIN menu_role_requirements mrr ON mrr.menu_secure_code=m.secure_code AND mrr.is_deleted=false
LEFT JOIN roles r ON r.secure_code=mrr.role_secure_code
LEFT JOIN organizations o ON o.secure_code=mrr.org_secure_code
WHERE m.is_deleted=false AND m.code='<menu_code>' GROUP BY m.code;
```

2. **查誰實際持有對應的 permission**，確認他們都通得過上面那組 Key1／Key2。
   對不上就**先修選單再掛**（施工2 的 vuln_lifecycle 就是這樣處理的，
   範例 migration `scripts/migrations/111_open_vuln_lifecycle_menu_to_risk_controller.py`）。
   改選單一定是 **DB + 出廠預設兩件事**（MENU-01）。

3. **修改前先跑一次基準**（六種身分 × 該批端點的狀態碼），改完再跑一次比對。
   身分清單見 audit 文件；`/dev/quick-login` 的 user secure_code 也在那裡。

### 掛上去之後如果狀態碼完全沒變，必須做 mutation 驗證

這批修改的正常結果就是「行為不變」（是加防線，不是改權限）。所以全綠不能當作
驗證通過——要把修復暫時拿掉再測一次：

```bash
git stash push -q <改過的檔案>
sudo systemctl restart beakplatform-dev.service && sleep 5
# 用「EXTERNAL 帳號 + 該功能的內部角色」打，應該 200（漏洞重現）
git stash pop -q
sudo systemctl restart beakplatform-dev.service && sleep 5
# 同一組再打一次，應該 403
```

**不要用「對照組也 403」來推論擋在哪一層**——施工2 第一次就這樣誤判，
實際上對照組是被 permission 擋的，不是 Key1。只有 stash 這招問得出來。

---

## 三、已經踩過的坑（別再踩一次）

- **盤點腳本的反查曾漏掉 `.html` caller**（template 內嵌 script 直接打 API），
  害 vuln_lifecycle 11 支被誤歸為「無選單候選」。已修，但**再改腳本時注意這條**
- **多候選一律不掛**：`/api/form-workflow/templates` 五支同時被
  `open_defense.event_routing` 用，掛了會誤擋（PF-142 實測過）
- **A 級的 24 支 form-center 不要一律掛**：表單中心對 EXTERNAL 是刻意開放的，
  多數端點以呼叫者身分為過濾條件（`pending-tasks` 對 EXTERNAL 回空陣列是對的）。
  該修的是「回傳與呼叫者身分無關的全企業資料」那種，例如已修掉的 `org-tree`
- **`db.session.rollback()` 清不掉試建的企業**：`create_organization()` 會呼叫
  `seed_org_builtin_protected_targets()`，那支自己 commit。試建企業後請用
  `/hostconfig/hard-delete`（先把企業 `is_deleted=true` 再執行）收尾
- **改編號規則的 `default_for` 要同步兩個模板**：`numbering/list.html` 的 badge、
  `numbering/edit.html` 的 select 選項。少了 select 選項的話，編輯該規則時會落回
  「非預設」，一存檔就把 `default_for` 清掉，而且不會報錯

---

## 四、本次順帶完成、與 PF-145 無關但要知道的

- **PF-143 已完成**（commit `a60ac3a9`）：系統設定 `system_base_url` + Jinja2 global
  `external_url()`。**對外連結一律走它**，禁用 `_external=True` 與 `request.host_url`
  （CLAUDE.md URL-02）。開發庫已設為 `http://192.168.0.16:7000`
- **CLAUDE.md 新增 PERM-04**（模組 ACL 是 fail-open，新企業預設全開）
  與 **URL-02**，兩條都是判讀既有程式時會用到的前提
- **`api-keys.js::copySecret()` 仍是壞的**：它自己直呼 `navigator.clipboard`，
  在 http 非安全上下文恆失敗。`Utils.copyToClipboard()` 已修好 fallback，
  但那支沒改過去
- **`backend/app/api/files.py:263,275` 還在用 `request.remote_addr`**（違反 NET-01），
  屬待辦 PF-36
