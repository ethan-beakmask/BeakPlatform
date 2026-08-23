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

## 二之二、可直接照抄的指令（本 session 全部實際跑過）

冷讀審核（codex，2026-08-23）指出交接檔缺可執行內容，以下原樣補上。

### 環境

```bash
cd /opt/BeakPlatform-dev
BASE=http://192.168.0.16:7000/beakplatform
PG="PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev"
# 重啟服務（Python/模板不會自動重載，不重啟等於在測舊程式碼）
sudo systemctl restart beakplatform-dev.service && sleep 5 && systemctl is-active beakplatform-dev.service
# 起不來時看這裡（常見成因：殘留的 flask run 佔住 7000 埠）
sudo journalctl -u beakplatform-dev.service --since "-5 min" | tail -30
ss -tlnp | grep :7000
```

### 六種測試身分（beluga 為主，`/dev/quick-login` 免密碼）

| 身分 | user secure_code |
|---|---|
| ORG_ADMIN | `jIYEQ-_lZMZNBkVy-hijal` |
| EMPLOYEE + FLOW_DESIGNER（ethanyu） | `FhsmtyPjsnXYotN-iz_Q-X` |
| EMPLOYEE + RISK_CONTROLLER（shen.qing.zhe） | `unSuAD3AonAoTQ8TDa7ipd` |
| 純 EMPLOYEE（aaaa） | `9De0TEngQTU35rbJn7q2Uk` |
| EXTERNAL（gg） | `WhFFX8FPLciXl9_aAudBtn` |
| SYSTEM_ADMIN | `nH5liUKQikH1NM2osVVXuF` |

### 基準／驗收矩陣（改之前跑一次，改之後跑一次比對）

```bash
for who in "ORG_ADMIN:jIYEQ-_lZMZNBkVy-hijal" "FLOW_DESIGNER:FhsmtyPjsnXYotN-iz_Q-X" \
           "RISK_CONTROLLER:unSuAD3AonAoTQ8TDa7ipd" "純EMPLOYEE:9De0TEngQTU35rbJn7q2Uk" \
           "EXTERNAL:WhFFX8FPLciXl9_aAudBtn" "SYSTEM_ADMIN:nH5liUKQikH1NM2osVVXuF"; do
  id=${who#*:}; label=${who%%:*}
  rm -f /tmp/cj.txt
  curl -s -c /tmp/cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
    -d "{\"user_id\":\"$id\"}" -o /dev/null
  printf '%-22s' "$label"
  for u in <這批要測的端點路徑>; do
    printf ' %s' "$(curl -s -b /tmp/cj.txt -o /dev/null -w '%{http_code}' "$BASE$u")"
  done
  echo ""
done
```

**判準是「與基準逐格相同」，不是某個絕對值。** 這批修改是加防線、不改變現有行為，
所以任何一格變動都要能解釋（施工2 唯一預期的變動是 vuln 那組，而那組先跑了
migration 111 所以最後也沒變）。SYSTEM_ADMIN 打別家企業的資源得 404 是租戶隔離，
不是壞掉。

### 查 permission 的實際持有者

```bash
$PG -c "
SELECT p.code AS permission, o.code AS org, r.code AS role, u.username, u.user_type
FROM permissions p
JOIN role_permissions rp ON rp.permission_secure_code=p.secure_code AND rp.is_deleted=false
JOIN roles r ON r.secure_code=rp.role_secure_code AND r.is_deleted=false
JOIN organizations o ON o.secure_code=r.org_secure_code
LEFT JOIN user_role_assignments ura ON ura.role_secure_code=r.secure_code AND ura.is_deleted=false
LEFT JOIN users u ON u.secure_code=ura.user_secure_code AND u.is_deleted=false AND u.is_active=true
WHERE p.code LIKE '<permission 前綴>%' AND u.username IS NOT NULL
ORDER BY p.code, o.code;"
```

**判準**：持有者的 user_type 要在該選單的 Key1 內、角色要在 Key2 內。
對不上時**以 permission 持有者為準去擴 Key1／Key2**（施工2 的 vuln_lifecycle 就是
這樣處理的）——因為 permission 是該功能設計時就定好的授權，選單設定才是後來漏配的。
反過來縮 permission 會把正在用的人擋掉。

### 修改模式（decorator 位置與順序）

插在 `@module_access_required(...)` **之後**、其餘 decorator 之前：

```python
@bp.route('/xxx', methods=['GET'])
@module_access_required('form_workflow')
@page_keys_required('form_workflow.workflows')   # PF-145：API 不吃雙鑰匙，須自掛 Key1+Key2
@require_permission('form_workflow.workflow.view')
def xxx():
```

import 一律加在既有那行後面，不要另開一行：

```python
from app.security.decorators import module_access_required, page_keys_required
```

**既有的 decorator 全部保留**，`page_keys_required` 是加上去的第三道，不是替換。

改完用 AST 逐一驗證掛對目標（`grep` 只能證明字串存在，證明不了掛在哪個函式上）：

```bash
venv/bin/python - <<'EOF'
import ast
TARGETS = {'函式名': 'menu_code', ...}
tree = ast.parse(open('<檔案路徑>').read())
seen = {}
for node in ast.walk(tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for d in node.decorator_list:
        if isinstance(d, ast.Call):
            f = d.func
            name = getattr(f, 'attr', None) or getattr(f, 'id', '')
            if name == 'page_keys_required' and d.args and isinstance(d.args[0], ast.Constant):
                seen[node.name] = d.args[0].value
for fn, code in TARGETS.items():
    print(('OK ' if seen.get(fn) == code else '!! '), fn, seen.get(fn))
print('多掛在:', sorted(set(seen) - set(TARGETS)))
EOF
```

### mutation 驗證：要 stash 哪些、測試身分怎麼生

**只 stash「加了 decorator 的那幾個 api 檔」**，migration、`menu_defaults.py`、
模組 `__init__.py` 都不要 stash——那些是選單設定，stash 掉會讓驗證的變因不只一個。

測試身分用「EXTERNAL 帳號 + 該功能的內部角色」。beluga 的 gg
（`WhFFX8FPLciXl9_aAudBtn`）已經有兩筆 soft-deleted 的測試指派，復活即可用完再關：

```bash
# FLOW_DESIGNER（id=443）／SECURITY_STAFF（id=444）
$PG -q -c "UPDATE user_role_assignments SET is_deleted=false WHERE id=443;"
# ...測試...
$PG -q -c "UPDATE user_role_assignments SET is_deleted=true, assigned_by='pf142-boundary-test' WHERE id=443;"
```

需要其他角色時自己 INSERT 一筆、測完 DELETE（用可辨識的 secure_code 方便清）：

```bash
$PG -q -c "
INSERT INTO user_role_assignments
  (user_secure_code, role_secure_code, org_secure_code, assigned_at, assigned_by,
   created_at, updated_at, is_deleted, secure_code)
VALUES ('WhFFX8FPLciXl9_aAudBtn','<role secure_code>','_9c8TewkRkCBEf3XsUdqeF',
        now(),'pf145-mutation', now(), now(), false, 'pf145mutationtest0001');"
# ...測試...
$PG -q -c "DELETE FROM user_role_assignments WHERE secure_code='pf145mutationtest0001';"
```

**驗完務必撤銷**，並用這條確認乾淨：

```bash
$PG -t -A -F'|' -c "
SELECT r.code, ura.is_deleted FROM user_role_assignments ura
JOIN roles r ON r.secure_code=ura.role_secure_code
WHERE ura.user_secure_code='WhFFX8FPLciXl9_aAudBtn';"
```

### 分組與收尾

- **「一模組一 commit」的分組依據是 CSV 的 `module` 欄**（`modules/<name>`），
  不是 menu_code。同一模組內若跨多個 menu_code 仍是一個 commit
- 完成後三件事：更新 `dev-notes/PF145_MODULE_API_KEY1_AUDIT.md` 第四節的施工順序表
  （劃掉已完成項並在下方補一段做法與驗收）、`note_update` 回寫 PF-145（atom 5247）
  照既有那幾段的粒度、重跑 `scripts/audit_module_api_gates.py` 更新 CSV
- 完整測試基準：`bash scripts/run_tests.sh -q`，約 8 分鐘，
  **1 failed（PF-34 已知）/ 623 passed / 2 skipped**

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
