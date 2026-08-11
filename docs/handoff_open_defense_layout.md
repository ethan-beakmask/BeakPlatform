# 交接：/open-defense/ 版面調整（2026-08-11 ~ 08-12）

> 本次 session 只動版面與一個清單過濾條件，**沒有動安全核心、沒有改資料模型**。
> 接手前讀 `CLAUDE.md`（專案規範）與 `docs/OPEN_DEFENSE_ARCHITECTURE.md`（模組架構）。

---

## 一、這次改了什麼（全部已 commit，未 push）

| commit | 內容 |
|---|---|
| `6740c052` | 容器 1480→1000px、案件卡兩列化、只顯示可簽核、修選取高亮 |
| `98daeda3` | 容器寬度更正為 **1800px** |
| `40f7e091` | decisions 目標欄／TTL 欄各 +10px |
| `df3e6686` | decisions 表格 `width:auto`、目標值截斷 + title、執行方欄 835→340 |
| `0775d921` | decisions 恢復顯示 `target_type`（用戶最後指示） |

動到的檔案：

```
modules/open_defense/api/security_cases.py                          # mine=1 過濾
modules/open_defense/templates/modules/open_defense/security_cases.html
modules/open_defense/templates/modules/open_defense/decisions.html
modules/open_defense/static/modules/open_defense/css/od-common.css  # 容器寬 + decisions 欄寬
modules/open_defense/static/modules/open_defense/css/sc-cases.css   # 案件清單
backend/translations/en/LC_MESSAGES/messages.po|mo                  # 兩條新字串
```

交接當下**工作區乾淨**（`git status --short` 無輸出），這 5 個 commit 之後沒有未提交變更。
`0775d921` 是最新一筆，接手時先 `git log --oneline -1` 確認沒有其他人再推過東西。

---

## 二、現行版面數值（要再調時對照這張表，不要重新量）

### 模組容器（6 個頁面共用）

`od-common.css` 的 `.od-container { max-width: 1800px; }`
—— 儀表板／決策列表／資安案件處置中心／事件接收金鑰／執行端帳號／事件路由設定全吃這條。

> **1600px 螢幕上量不出 1000px 與 1800px 的差別**，兩者都是滿版（實際 1568px）。
> 要驗證這個值必須把視窗拉到 1832px 以上，或用 `resize_page`。

### `/open-defense/security-cases`

| 元素 | 值 | 位置 |
|---|---|---|
| `.sc-main` 欄寬 | `minmax(0, 460px) minmax(0, 1fr)` | `sc-cases.css` |
| 案件卡 | 兩列：列1 = 案件名稱 + 等級徽章，列2 = 編號 + 立案時間 + SLA | `security_cases.html` |
| 卡片高 | 64px（原三列版 86px） | |

**兩欄都必須是 `minmax(0, ...)`**：右側明細表格有 `min-width: 720px`，
少了 `minmax(0, 1fr)` 會把版面撐破容器。

### `/open-defense/decisions`（容器 1549px 時實測）

表格總寬 1056px，右側留白約 490px。

| 欄 | 寬 | 由什麼決定 |
|---|---|---|
| 建立時間 | 128 | `white-space: nowrap` |
| 動作 | 66 | 自然寬 |
| 目標 | 116 | `min-width` 116（106 +10） |
| EP | 118 | 自然寬 |
| 嚴重度 | 71 | 自然寬 |
| TTL | 66 | `min-width` 66（56 +10） |
| 狀態 | 75 | 自然寬 |
| 執行方 | 340 | `.od-err` 限寬 320 |
| 來源 | 56 | 自然寬 |
| 操作 | 20 | 自然寬 |

規則全在 `od-common.css` 的 `.od-decisions-table` 區塊。**三條缺一不可**：

1. `.od-decisions-table { width: auto; }` —— 不寫的話 `.od-table` 的 `width:100%`
   會把容器多出的 490px 按 max-content 比例分散，`min-width` 直接失效
   （實測目標欄被撐到 166、TTL 到 95）
2. `box-sizing: border-box` —— table cell 的 `min-width` 預設是 content-box，
   不寫的話 116 會變成 116 + 20（padding）= 136
3. `.od-err { max-width: 320px }` —— `error_message` 是 231 字元的單行 JSON，
   不限寬時執行方欄吃掉 800~1080px，還把建立時間壓成兩行

**長值防護**：目標值掛 `.od-target-value`（`max-width: 240px` + ellipsis）與
`:title="d.target_value"`。注入 131 字元 `user_agent` 實測欄寬止於 260px。
`VALID_TARGET_TYPES` 有 9 種，但 `user_agent` / `jwt_sub` 目前**沒有任何程式碼會產生**，
DB 21 筆全是 `ip` —— 這是預防性防護。

---

## 三、行為變更：清單只顯示有權簽核的案件

`GET /api/open_defense/cases` 新增 `mine=1`，判定沿用
`modules/form_workflow/services/task_authorizer.py::can_act_on_task`（沒有另寫一套）。

- 「進行中」預設帶 `mine=1`，`[僅我可簽核]` 按鈕可切回全部
- 「已結案」不套用（結案案件沒有 WAITING 節點，過濾後必然全空），該按鈕隱藏

**已知限制見待辦 `PF-77`**：過濾是在 SQL `limit 200` **之後**才算的，
進行中案件超過 200 筆時會漏掉排在後面的可簽核案件。目前 43 筆未觸發。

---

## 四、驗證指令（本 session 實際跑過，照抄即可）

### 登入與 API

```bash
BASE=http://192.168.0.16:7000/beakplatform
# ORG_ADMIN admin-ethanyu@beluga.com（beluga 是唯一有 OD 資料的企業，8010 筆 intake 事件）
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"jIYEQ-_lZMZNBkVy-hijal"}'

curl -s -b cj.txt "$BASE/api/open_defense/cases?status=open" | \
  python3 -c "import sys,json;d=json.load(sys.stdin);print('total',len(d['data']),'can_act',sum(1 for x in d['data'] if x['can_act']))"
# 2026-08-12 實測：total 43 can_act 2
```

那個 `user_id` 是 `users.secure_code`，資料庫重建就會變。失效時自己重查（不要猜密碼，會觸發鎖定）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -c \
  "SELECT secure_code, email FROM users
   WHERE email LIKE '%@beluga.com' AND user_type='ORG_ADMIN'
     AND is_deleted=false AND is_active=true;"
```

`/dev/quick-login` 只在內網開放（iptables → nginx → `dev.py::internal_network_only` 三層）。
從白名單外連會是**連線逾時而不是 403**，白名單維護見全域
`~/.claude/knowledge_base/configurations/system_configs/network_architecture.md` 的 Layer 1。

### 瀏覽器量測（chrome-devtools MCP，只有主 Claude 有）

沒有這個 MCP 時，**欄寬、折行、選取高亮這幾類斷言就驗不了**——
curl 拿到的 HTML 看不出渲染後的寬度，也看不出 Alpine 綁定的實際 class。
這種情況只能改由人工目視，不要用 curl 的結果宣稱版面驗過（VERIFY-01）。

decisions 頁預設篩選是 `pending`，**目前 0 筆**（21 筆分佈在 applied 7 / failed 6 / expired 8）。
這批是先前 intake 端對端測試留下的資料，**沒有重建腳本**；
欄寬驗證不依賴特定筆數，但要驗 `.od-err` 限寬**必須有 failed 案件**（目前 6 筆）。
資料若沒了，用 `docs/OPEN_DEFENSE_ARCHITECTURE.md` 的 intake webhook 流程重灌幾筆即可。
要看到資料必須改篩選，頁面 filter 是 Alpine 狀態、不吃 query string：

```
evaluate_script(function="async () => {
  const d = Alpine.$data(document.querySelector('.od-container'));
  d.filters.status = '';
  await d.load();
  await new Promise(r => setTimeout(r, 400));
  return [...document.querySelectorAll('.od-table thead th')]
    .map((th,i) => ({i: i+1, label: th.innerText.trim() || '(空)',
                     w: Math.round(th.getBoundingClientRect().width)}));
}")
```

溢出檢查（比截圖可靠，且 `take_screenshot` 本機一律逾時）：

```
evaluate_script(function="() => [...document.querySelectorAll('.od-container *')]
  .filter(e => e.scrollWidth - e.clientWidth > 2 && e.clientWidth > 0)
  .map(e => ({cls: e.className.toString().slice(0,40), cw: e.clientWidth, sw: e.scrollWidth}))")
```

### 服務與測試

```bash
sudo systemctl restart beakplatform-dev.service   # 模板／Python 改動必須重啟，CSS/JS 不用
cd /opt/BeakPlatform-dev && bash scripts/run_tests.sh tests/test_od_aggregation.py \
  tests/test_od_native_intake.py tests/test_od_routing_service.py -q
# 2026-08-12 基準：39 passed in 58s
```

驗收原始輸出全部落在 `/opt/tmp/verify/20260811-od-layout.log`。

---

## 五、本次踩到、下次別再踩的兩個坑

1. **Alpine `:class` 陣列不能混物件**（知識庫 #5139，已寫進全域
   `~/.claude/knowledge_base/standards/ui_frameworks/alpine_standards.md`）——
   案件卡的選取高亮從第一版起就沒生效過，因為寫成
   `:class="[\`sev-${n}\`, { selected: ... }]"`，物件被字串化成 `"[object Object]"`。
   不報錯、grep 會命中、`node --check` 會過，只有讀 DOM className 才看得出來。

2. **表格欄寬**（知識庫 #5140）—— 見上面第二節的三條規則。
   另外：長欄的正解是限寬 + ellipsis，**不是把它移到最右邊**
   （移到最右一樣撐出橫向捲軸），也不是改成兩列（列數翻倍）。

---

## 六、待辦：PF-77

全文在 BeakBroodNest（`note_search("PF-77")`）。**沒有 BBN MCP 也能動工**，重點抄在這裡：

**問題**：`list_cases` 是先 SQL `limit 200` 撈案件、再在 Python 層逐筆算 `can_act`。
進行中案件超過 200 筆時，排在後面的可簽核案件不會出現在清單上，畫面也沒有任何提示。
排序是 `submitted_at DESC`，被吃掉的是舊案 —— 偏偏 SLA 逾時的就是舊案。
`limit` 上限 500（`min(int(request.args.get('limit', 200)), 500)`）。

**不能怎麼修**：`can_act` 走 `task_authorizer.can_act_on_task`，判定是
「節點快照指派 ∪ 當前角色 ∪ 生效中代理」的聯集，不是單一欄位比對。
那是簽核授權的唯一實作（12 個判定點），**不可為了效能在 open_defense 這邊另寫 SQL 判定**。

**建議做法**：反過來查 —— 先撈當前帳號可簽核的 WAITING 佇列（`fw_node_execution_queue`），
再用 `workflow_instance_secure_code` 反查資安分類案件，最後才套 limit。
`mine=1` 與不帶 `mine` 走兩條查詢路徑。

**現況**：2026-08-12 實測 beluga 進行中 43 筆、`can_act` 2 筆，未觸發。

---

## 七、需要 BeakBroodNest MCP 才拿得到的東西

以下只是補充脈絡，**沒有 MCP 也不影響動工**（該知道的都已抄進本檔）：

| 編號 | 內容 |
|---|---|
| `#5139` | Alpine `:class` 陣列混物件的完整說明（已同步寫進全域 `alpine_standards.md`，那份讀得到） |
| `#5140` | 表格 auto layout 欄寬控制的三種解法對照表 |
| `PF-77` | 上一節已摘錄核心 |
