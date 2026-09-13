# 範例資料包

**適用對象：** 剛完成安裝、想快速驗證企業管理、人資核決鏈、表單流程與 Open Defense 的系統管理員。

## 一、有哪兩包

| 資料包 | 佈建方式 | 內容 |
|---|---|---|
| 系統級 node 展覽館 | 安裝時內建（全新安裝時設環境變數 `SKIP_NODE_SHOWCASE=1` 可不種入；`--update` 不受影響） | 安裝完成後系統預設企業的表單中心會有「node展覽館」分類，用 `enterprise@<系統企業代碼>` 登入即可看；受限節點出廠關閉，看得到、要跑得動請見 `os_node.md`／`ai_node.md`。 |
| 企業級範例企業 | `scripts/seed_demo_org.py` | 建立一家可直接登入的「示範企業」，含人資結構、Open Defense 受理鏈路、SOC 團隊版/單人版流程與差旅費人事取值示範。 |

## 二、範例企業包含什麼

| 項目 | 內容 |
|---|---|
| 企業 | code `DEMOSOC`，domain `demo-soc.example`，合約啟用全部五個模組（`form_workflow`、`open_defense`、`nocode_builder`、`spec_formulate`、`vuln_lifecycle`） |
| 帳號 | 已完成初始設定精靈，原始 `admin@domain` 停用，改用綁定員工的 `admin-<username>@domain` |
| 人資 | 三層以上部門、10 級職等、差旅費核決上限、約 12 位虛構員工與主管鏈 |
| Open Defense | 資安事件受理表單、流程、發行版本與事件路由 |
| SOC 流程 | SOC 團隊版、小企業單人版；SOC 團隊版路由預設啟用，`severity_id >= 3` |
| 人事取值 | 差旅費申請流程示範依金額沿主管鏈找核決人 |

## 三、怎麼裝

先載入環境變數，再執行預演：

```bash
set -a && source .env && set +a
venv/bin/python scripts/seed_demo_org.py --dry-run
```

確認無誤後寫入：

```bash
venv/bin/python scripts/seed_demo_org.py --apply --password '<符合密碼政策的密碼>'
```

也可以用環境變數提供密碼：

```bash
DEMO_ORG_PASSWORD='<符合密碼政策的密碼>' venv/bin/python scripts/seed_demo_org.py --apply
```

如果 `--password` 與 `DEMO_ORG_PASSWORD` 都沒有提供，腳本會自動產生 16 碼密碼，並只在最後總結顯示一次。

## 四、裝完怎麼用

管理員登入：

```text
http://<平台IP>:<埠>/beakplatform/auth/org/demo-soc.example/login
```

使用總結列出的 `admin-<username>@demo-soc.example` 登入後，可查看組織、帳號角色與權限中心。

資安人員登入同一個企業網域後，進入「開放防禦 / 資安案件處置中心」，可查看 Open Defense 收案與處置流程。

申請人登入後，進入表單中心送出「差旅費申請（人事取值示範）」。填入金額後送單，可觀察系統依申請人的部門與職等上限找出主管鏈核決人。

## 五、怎麼移除

沒有移除參數。請用系統管理員到：

```text
http://<平台IP>:<埠>/beakplatform/organizations/
```

先將「示範企業」軟刪除，再到列表頁最下方使用「永久刪除已軟刪除的企業」。硬刪除流程會動態掃 `org_secure_code` 全表清理該企業資料。

## 六、常見問題

| 問題 | 說明 |
|---|---|
| domain 已存在，exit 2 | 腳本不覆蓋、不部分建立。請由系統管理員先軟刪再硬刪該企業後重跑。 |
| 密碼不過政策 | 預設至少 12 碼，且需大小寫字母、數字、特殊字元。請改用符合政策的 `--password` 或 `DEMO_ORG_PASSWORD`。 |
| `open_defense` 模組未註冊 | 請先完成安裝/bootstrap，確認模組表已有 `form_workflow` 與 `open_defense`，再重跑腳本。 |
