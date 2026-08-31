# PF-145 階段二 交接（2026-08-23）

接手前先讀：**BBN 待辦 `PF-145`（`note_search("PF-145")`，atom 5247）**
與 **`dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`**。兩者都是自足的，本檔只寫
「下一步要做什麼」與「已經踩過不要再踩的坑」。

**本檔引用的東西全部在本機、直接讀就有**，不需要另外要權限：
`dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`（盤點全文）、
`dev-notes/pf145_module_api_audit.csv`（334 筆機器可讀）、
`/opt/tmp/verify/20260823-pf145-stage3.log`（施工3 的原始輸出）。
BBN 待辦走 MCP（`note_search` / `note_update`），全域 CLAUDE.md 的 Auto Memory 段有說明；
**MCP 不可用時本檔與 audit 文件已足夠動工**，只是收尾少一步回寫。

---

## 一、目前進度

| 項目 | 狀態 | commit |
|---|---|---|
| 階段一：open_defense 資安案件 5 支補 Key1 | 完成 | `809ea8ba` |
| 階段二：334 支模組 API 盤點清單 | 完成 | `f7b8a7fd` |
| 施工1：`/api/form-center/org-tree` 依身分裁剪 | 完成 | `95f85cd8` `cb7927e3` |
| 施工2：C 級選單唯一 29 支補 Key1 | 完成 | `f1461564` `3eabb1b2` |
| 附帶：管理員帳號發 ADM 編號（新企業＋回填） | 完成 | `3eabb1b2` `147f6f0e` |
| 施工3：B 級選單唯一（CSV 45 支，實際處理 52 支） | 完成 | `bc21a720` `97b6b892` |
| 附帶：表單中心選單 Key2 補 EXTERNAL_USERS（出廠預設＋migration 113） | 完成 | `bc21a720` |
| 施工4：4 支掛在 `/api/` 下的頁面路由（確認零引用後刪除） | 完成 | `640ddc2b` |
| 施工5：B 級無選單反查那批（實際 form_workflow 36＋spec 1：掛 28、刪 6、跨頁不掛 3；nocode 55 支另案） | 完成 | 2026-09-01，含 PF-149 收掉 |
| 階段三：模組 ACL fail-open→fail-closed、`roles` 加 user_type 約束 | 未開始（全平台變更，要單獨評估） | — |

盤點現況（**數字會腐爛，動工前自己重跑**）：

```bash
venv/bin/python scripts/audit_module_api_gates.py            # 產 CSV
venv/bin/python scripts/audit_module_api_gates.py --summary  # 只看統計
```

2026-08-23 施工3 收工時：**A35 / B101 / C16 / D170 / E12**，共 334 支。
**B 級選單唯一只剩 1 支**（`GET /api/mappings`，刻意不掛，理由見下）。

---

## 二、下一步（施工4 與施工5）

### 施工4：四支掛在 `/api/` 前綴下的頁面路由

> **2026-09-01 已完成（commit `640ddc2b`）**：重新確認零引用後直接刪除四支
> （含 `render_template` import；`forms_bp` 的 `template_folder` 保留）。
> route_guard_table `--update` 恰好移除那 4 個 endpoint。驗收：四支 404、
> 正牌頁 bytes 與刪除前完全相同、瀏覽器實測兩列表頁各 7 列 console error 0、
> 完整測試 1 failed（PF-34）/ 830 passed / 2 skipped。
> 留證 `/opt/tmp/verify/20260901-pf145-stage4.log`。
> 附帶事實：TEST00 的 form_workflow 合約與 ACL 現皆為 0 筆，8/23 那組
> fail-open 曝露面測試身分已不可用，日後要驗 PERM-04 得重造「有合約零 ACL」企業。
> 以下為當時的查證記錄，留供考古。

回的是 HTML 整頁，而 `/api/` 在 `PageRoleGuard.SKIP_PREFIXES` 內，
所以這四頁**結構上不可能被雙鑰匙保護**。定義位置與現況（2026-08-23 查證）：

| 路由 | 檔案:行 | endpoint | decorator | 渲染的模板 |
|---|---|---|---|---|
| `/api/forms/list` | `modules/form_workflow/api/forms.py:115` | `form_workflow_api_forms.list_page` | `module_access_required('form_workflow')` | `template_list.html` |
| `/api/forms/designer[/<sc>]` | `forms.py:125` | `...forms.designer` | 同上 | `form_designer.html` |
| `/api/workflows/list` | `modules/form_workflow/api/workflows.py:69` | `...workflows.list_page` | 同上 | `workflow_list.html` |
| `/api/workflows/designer[/<sc>]` | `workflows.py:79` | `...workflows.designer` | 同上 | `workflow_designer.html` |

**兩件已經查過、會直接決定做法的事實**：

1. **沒有任何地方連它們。** 全專案零命中：

```bash
grep -rn "api/workflows/list\|api/workflows/designer\|api/forms/list\|api/forms/designer" \
  --include=*.html --include=*.js --include=*.py backend modules \
  | grep -v "api/forms.py\|api/workflows.py"
```

2. **它們與 `web/__init__.py` 的正牌頁面渲染同一批模板**，是重複實作：

| `/api/` 這份 | 正牌頁面 |
|---|---|
| `/api/forms/list` | `/forms/templates`（`web/__init__.py:37`） |
| `/api/forms/designer/<sc>` | `/forms/templates/<sc>`（`web/__init__.py:54`） |
| `/api/workflows/list` | `/forms/workflows`（`web/__init__.py:84`） |
| `/api/workflows/designer/<sc>` | `/forms/workflows/<sc>`（`web/__init__.py:101`） |

**所以最可能的正解是刪掉這四支**（連同 `render_template` 的 import 殘留），
不是搬路徑也不是補 decorator。動工前只要再確認一次上面那條 grep 仍是零命中、
以及沒有外部書籤依賴（問用戶），就可以刪。
若決定保留，才需要選「搬到 `web_bp` 前綴」或「補 `@admin_required`」。

驗收：刪除後 `/forms/templates`、`/forms/workflows` 及兩個設計器頁以 ORG_ADMIN
與 FLOW_DESIGNER 各開一次（VERIFY-01 要實際點，不能只 curl），
完整測試無新增失敗。

### 施工5：B 級剩下的那批

> **2026-09-01 已完成**：處置明細與驗收記錄見
> `dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`「第 4、5 項已完成」節
> 與 `/opt/tmp/verify/20260901-pf145-stage5.log`。
> 掛 28（templates 8／workflows 20）、刪 6（含 PF-149 的 `/api/mappings/available`，
> 六支全歷史零呼叫者）、跨頁不掛 3（categories、backgrounds list/upload）、
> nocode_builder 55 支因選單隱藏中不動（另案）。
> 收工分級：**325 支，A36 / B63 / C16 / D198 / E12**（B 剩 nocode 55 ＋ fw 8）。
> 以下為當時的查證記錄，留供考古。

**「反查不到呼叫者的 104 支」這個講法已經過時**，施工3 之後 B 級是 101 支，
而且組成與原本的描述不一樣。當下分組（2026-08-23，重跑腳本後）：

| 分組 | 支數 | 模組分佈 |
|---|---:|---|
| 完全反查不到 caller | 10 | form_workflow 6、nocode_builder 4 |
| 有 caller 但反查不到選單 | 86 | **nocode_builder 51**、form_workflow 34、spec_formulate 1 |
| 選單候選多於一個 | 4 | 刻意不掛 |
| 選單唯一 | 1 | `GET /api/mappings`，刻意不掛（PF-149 是另一支） |

重跑分組（**不要相信上表的數字，自己跑**）：

```bash
cd /opt/BeakPlatform-dev
venv/bin/python scripts/audit_module_api_gates.py     # 先更新 CSV
venv/bin/python - <<'EOF'
import csv, collections
rows = list(csv.DictReader(open('dev-notes/pf145_module_api_audit.csv')))
b = [r for r in rows if r['level'] == 'B']
groups = {
    '無 caller':            [r for r in b if not r['callers']],
    '有 caller 但無選單':   [r for r in b if r['callers'] and not r['menu_candidates']],
    '多候選':               [r for r in b if ';' in r['menu_candidates']],
    '選單唯一':             [r for r in b if r['menu_candidates'] and ';' not in r['menu_candidates']],
}
for name, g in groups.items():
    print(f'{name:22} {len(g):4}  ', dict(collections.Counter(r['module'] for r in g)))
    for r in g if name == '無 caller' else []:
        print('     ', r['func'], r['url'])
EOF
```

CSV 欄位是 `level,module,url,file,line,func,gates,callers,menu_candidates`。

#### nocode_builder 那 51 支現在做不了，不要硬做

**NoCode 目前一筆 `menu_items` 都沒有**（鐵人賽期間刻意隱藏，見 CLAUDE.md
「NoCode 選單目前刻意隱藏中」）。`page_keys_required` 對不存在的選單是
**fail-closed 直接 403**，所以現在掛任何一支都會把 ORG_ADMIN 以外的人全部擋死。

反查不到選單也不是「沒有歸屬」，只是**沒有選單可反查**。NoCode 的元件級控制走
D2（`can()` + `@permission_required('nocode_builder.manage')`）與 portal 的
access_matrix，見 CLAUDE.md PERM-02。**這 51 支要等選單復原後再談，
或改用 D2 判準單獨處理，都不屬於「補 Key1」這條線。**

實務上施工5 可動的是 **form_workflow 的 40 支**（6 + 34）與 spec_formulate 1 支。

#### 「還活著嗎」與死碼怎麼處置（先訂判準再逐支看）

判準（由強到弱，任一成立即視為活著）：

1. 前端有呼叫（grep 全專案 `.js` / `.html`，**含 template 內嵌 script**）
2. 後端有呼叫（另一支 API 或 service 打它）
3. 是對外契約的一部分（webhook、service account、`scripts/examples/` 的範例腳本）
4. UI 上有觸發路徑（設計器內部 API 屬這類，要實際點過才算數）

四種結論的處置：

| 結論 | 處置 |
|---|---|
| 活著、只被單一選單頁用 | 掛該頁 `@page_keys_required` |
| 活著、跨頁 | 不掛，在 audit 文件記明理由（PF-142 的教訓） |
| 活著，但該頁的鑰匙比端點受眾寬很多 | 改掛符合實際受眾的 decorator（施工3 的 colcfg 就是這樣） |
| 確認沒人用 | **刪掉**（不要留著加 decorator）。刪完重跑腳本更新 CSV，完整測試比對基準 |

**「刪」要有依據**：上面四條判準逐條查過、且 `git log -S` 看得出它何時失去呼叫者。
拿不準就開單另議，不要留在原地。

### 施工3 的三個發現已開單，不在 PF-145 底下

| 單號 | 內容 |
|---|---|
| **PF-148** | route 型選單只守單一 endpoint，同 blueprint 的子路由不受雙鑰匙管。實測 49 條不受涵蓋的頁面路由逐條判過，真正的缺口只有 `/spec-formulate/<sc>/edit` 一條 |
| **PF-149** | `GET /api/mappings/available` 反查不到呼叫者，先確認存活再決定去留（本來屬施工5，單獨追蹤） |
| **PF-150** | `POST /api/users/` 忽略 `user_type`、一律建成 EMPLOYEE 並順帶指派 `EMPLOYEE` 角色 |

`note_search("PF-148")` 取全文。**施工5 動工時 PF-149 可以一起收掉。**

### 施工3 留下來的三條判讀教訓（施工5 會再遇到）

**一、CSV 的 `callers` 欄是按 URL 前綴聚合的，不是該端點的呼叫者清單。**
`/api/mappings` 那 19 支在 CSV 上看起來都被三個檔案呼叫，逐行 grep 才發現
`api-keys.js` 只打 `/published`、`ir-designer.js` 只打根路徑。
把它當成「要去看哪幾個檔案」的線索，不要當結論。

**二、「選單唯一 → 掛該頁 page_keys」不是萬用規則。**
遇到「該頁的鑰匙比這支端點的實際受眾寬很多」時，掛了等於沒掛。
施工3 的 `form-center/column-config` 兩支就是這樣——表單中心的 Key1 含 EXTERNAL、
Key2 是人人都有的預設角色，而那兩支是管理員專用（前端 `x-show="isAdmin"`、
後端零檢查）。判準改成先看**端點自己的受眾**，再決定掛什麼。

**三、「無選單候選」不一定代表沒有歸屬。**
spec_formulate 有 8 支被歸為無候選，成因只是它們的唯一呼叫者（規格編輯器頁）
不是選單項目。反查斷在「這個 template 由哪個 web route render」那一步時，
要再往上問一句「這個 route 是不是某個選單頁的子頁」。

### 每一批動手前仍然要做的三件事

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

**Key2 是 per-org 的，一定要 group by 企業**——不分組會把四家企業的角色混成一串，
看不出「只有 TEST00 缺一筆」這種缺陷（施工3 就是這樣才發現表單中心的出廠預設漏了
`EXTERNAL_USERS`）。

2. **查誰實際持有對應的 permission**，確認他們都通得過上面那組 Key1／Key2。
   對不上就**先修選單再掛**（範例 migration `111`、`113`，兩支都是冪等的）。
   改選單一定是 **DB + 出廠預設兩件事**（MENU-01）。

3. **修改前先跑一次基準**（六種身分 × 該批端點的狀態碼），改完再跑一次比對。
   **另外一定要補跑「無 ACL 企業的純員工」**（TEST00 的 `ethan`，
   `XeJUHw_SeDB7iern_QNEz4`）——BELUGA/SYSTEM 有模組 ACL，六身分矩陣會整片 403，
   看不出這批修改真正擋掉了什麼；PERM-04 的 fail-open 曝露面只在無 ACL 企業看得到。

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

**mutation 用的角色要選「該企業模組 ACL 實際放行的那個角色」**，否則會被 ACL 擋在
page_keys 之前，看起來像修復生效、其實什麼都沒證明。查法：

```sql
SELECT o.code, m.module_code, m.target_type, coalesce(r.code, u.username) AS target
FROM module_access_control m
JOIN organizations o ON o.secure_code = m.org_secure_code
LEFT JOIN roles r ON r.secure_code = m.target_secure_code
LEFT JOIN users u ON u.secure_code = m.target_secure_code
WHERE m.is_deleted = false ORDER BY o.code, m.module_code;
```

2026-08-23 的全部內容就這 6 筆（**其餘企業零 ACL ＝ fail-open 全開**）：

```
BELUGA  form_workflow   ROLE  FORM_DESIGNER
BELUGA  form_workflow   ROLE  FLOW_DESIGNER
BELUGA  spec_formulate  ROLE  SPEC_DESIGNER
SYSTEM  form_workflow   ROLE  FLOW_DESIGNER
SYSTEM  form_workflow   ROLE  FORM_DESIGNER
SYSTEM  spec_formulate  ROLE  SPEC_DESIGNER
```

所以 mutation 的身分組合是：**EXTERNAL `gg`（`WhFFX8FPLciXl9_aAudBtn`，BELUGA）
＋ 上表 BELUGA 那一列的角色**。open_defense / vuln_lifecycle 在 BELUGA 沒有 ACL，
用任何內部角色都通得過模組閘門。

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
不是壞掉。**先寫下預期再比對**，不要事後替意外的變動編理由。

#### 非 GET 端點也要進矩陣（施工3 用的寫法，不會改到任何資料）

上面那個迴圈只打 GET。**用 GET 去打 POST 端點量不到東西**——Flask 在進 decorator
之前就回 405。要把 POST/PUT/PATCH/DELETE 納入矩陣：

- **路徑參數一律填一個不存在的識別碼**（施工3 用 `PF145NOSUCH0000000001`）
- body 給 `{}`，帶 `Content-Type: application/json`
- 需要 CSRF token（非 `@csrf.exempt` 的端點），從登入後任一頁的 meta 取

授權通過就落到 **404 或 400**（查無資料／驗證失敗），被擋就是 **403** ——
403 與 404/400 的差別就是訊號，而且一筆資料都不會寫進去。

```bash
rm -f /tmp/cj.txt
curl -s -c /tmp/cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$id\"}" -o /dev/null
TOKEN=$(curl -s -b /tmp/cj.txt -c /tmp/cj.txt "$BASE/dashboard" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -s -b /tmp/cj.txt -o /dev/null -w '%{http_code}' -X DELETE \
  "$BASE/api/mappings/PF145NOSUCH0000000001" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{}'
```

施工3 完整的 45 端點矩陣腳本（含每支的 method）留在
`/opt/tmp/verify/20260823-pf145-stage3.log` 的輸出裡，端點清單可照抄改。

**建立型端點（`POST /api/mappings`、`POST .../specs`）用空 body 是安全的**——
兩支都在取 `org` 之後就檢查必填欄位並回 400，不會建出東西。**新增別的建立型端點
到矩陣前要自己確認這一點**，不要假設。

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

測試身分用「EXTERNAL 帳號 + **該企業模組 ACL 實際放行的**那個角色」
（挑錯角色會被 ACL 擋在 page_keys 之前，見上一節的對照表）。
beluga 的 gg（`WhFFX8FPLciXl9_aAudBtn`）已經有幾筆 soft-deleted 的測試指派，
復活即可、用完再關。**不要記 id，每次自己查**（id 會隨著別人建/刪指派而變）：

```bash
# 看 gg 現在有哪些指派（含已撤銷的）
$PG -c "
SELECT ura.id, r.code, o.code AS org, ura.is_deleted, ura.assigned_by
FROM user_role_assignments ura
JOIN roles r ON r.secure_code=ura.role_secure_code
JOIN organizations o ON o.secure_code=ura.org_secure_code
WHERE ura.user_secure_code='WhFFX8FPLciXl9_aAudBtn' ORDER BY ura.id;"

# 復活其中一筆（把 <角色> 換成上面查到的 code）
$PG -q -c "
UPDATE user_role_assignments SET is_deleted=false
WHERE user_secure_code='WhFFX8FPLciXl9_aAudBtn'
  AND role_secure_code=(SELECT secure_code FROM roles
      WHERE code='<角色>' AND org_secure_code='_9c8TewkRkCBEf3XsUdqeF' AND is_deleted=false);"
# ...測試...
$PG -q -c "
UPDATE user_role_assignments SET is_deleted=true, assigned_by='<本次任務代號>-mutation'
WHERE user_secure_code='WhFFX8FPLciXl9_aAudBtn'
  AND role_secure_code=(SELECT secure_code FROM roles
      WHERE code='<角色>' AND org_secure_code='_9c8TewkRkCBEf3XsUdqeF' AND is_deleted=false);"
```

（`_9c8TewkRkCBEf3XsUdqeF` 是 BELUGA 的 `org_secure_code`。
2026-08-23 收工時 gg 的狀態：`EXTERNAL_USERS` 生效中，
`SECURITY_STAFF`、`FLOW_DESIGNER` 都是 `is_deleted=true`。）

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
- **`POST /api/users/` 忽略 `user_type`，一律建成 EMPLOYEE**，而且會順帶指派
  `EMPLOYEE` 角色。要造 EXTERNAL 測試帳號得建完再用 SQL 改 `user_type`
  並補 `EXTERNAL_USERS`、拿掉 `EMPLOYEE` 指派（不拿掉會讓 Key2 測試多一個變因）。
  必填欄位是 `native_name` / `english_name` / `username` / `employee_id`
- **硬刪一個測試帳號要按 FK 順序清四張表**：`user_role_assignments` →
  `audit_logs` → `used_user_numbers` → `users`。少一張就會被 FK 擋住，
  而錯誤訊息只說「still referenced」不會列出全部

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
