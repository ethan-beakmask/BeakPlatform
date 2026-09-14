---
title: 人事資料取值節點
audience: ORG_ADMIN
order: 34
nav_menu: form_workflow.workflows
requires:
  - manual/04_form_workflow/workflows
  - manual/03_org_setup/positions
  - manual/03_org_setup/departments
produces:
  - 申請人職級職稱變數
  - 依金額找到的核決人
covers:
  - backend/app/services/unit_resolver.py
  - modules/form_workflow/services/node_handlers/hr_lookup_handler.py
  - modules/form_workflow/static/modules/form_workflow/js/wf-node-hr-lookup.js
---

# 人事資料取值節點

把某位成員在[職位設定](../03_org_setup/positions.md)裡的資料（職等、職稱、職系、部門、核決上限）
加上由部門主管推導的直屬主管變成流程變數，讓後面的「分支」能依**職等高低、是不是管理職、哪個職系**分流，
讓「簽核」能直接派給直屬主管，或依金額沿主管鏈找到有權核決的人。

!!! abstract "作業：讓簽核送給申請人的直屬主管"
    **MENU**：表單流程 ／ 流程設計

    1. 從左側「變數」分類拖出 [人事資料取值]，接在 Start 之後
    2. 面板保持「表單申請人」、前綴 `hr`，其餘不動
    3. 後面的「簽核」節點，簽核人選「動態（從變數取）」，填 `hr_direct_manager`

!!! abstract "作業：依金額自動找核決人"
    **MENU**：表單流程 ／ 流程設計

    1. 同上放好 [人事資料取值]
    2. 面板選「核決類別」（例如差旅費），勾「依金額找核決人」，金額欄填表單金額欄位，例如 `${f.amount}`
    3. 「簽核」節點的簽核人選「動態（從變數取）」，填 `hr_approver`

!!! abstract "作業：依職等或職系分流"
    **MENU**：表單流程 ／ 流程設計

    1. 同上放好 [人事資料取值]
    2. 接一個「分支」，條件用 `${v.hr_job_level_order}`（數字，越大越高）、`${v.hr_is_supervisor}`（`true`／`false`）或 `${v.hr_job_family_code}`

## 會寫出哪些變數

前綴預設 `hr`，可以改；面板下方會依當時的前綴列出名稱。常用的：

| 變數 | 內容 |
|---|---|
| `hr_found` | 有沒有取到職位，`true`／`false` |
| `hr_job_level_order` | 職等序號（數字），分支比大小用 |
| `hr_job_level_code`、`hr_job_level_is_manager` | 職等代碼、職等是否勾了管理職 |
| `hr_job_title`、`hr_is_supervisor` | 職稱名稱、職稱是否帶人主管 |
| `hr_job_family_code`、`hr_job_family_root_code` | 職系代碼、它所屬根職系的代碼（想只分「管理職／專業職」大類時用後者） |
| `hr_unit_code`、`hr_is_unit_head` | 職位的部門代碼、是不是部門主管 |
| `hr_direct_manager` | 直屬主管的帳號識別碼，直接餵給簽核節點的「動態」 |
| `hr_direct_manager_unit_name` | 推導出直屬主管的那一層部門名稱 |
| `hr_approval_limit` | 有選核決類別時才有：申請人職等在該類別的上限 |
| `hr_approver`、`hr_approver_found` | 有勾「依金額找核決人」時才有 |
| `hr_approver_unit_name` | 核決人所在的那一層部門名稱 |

## 畫面上看不出來的規則

- **取的是「有效職位」**：啟用中、生效日已到、失效日未過。一個人有多筆時**主要職位優先**，沒有主要職位就取生效最早的一筆
- **取不到職位不會讓流程失敗**：`hr_found` 會是 `false`，其餘變數全部空字串，流程照走。
  要擋下這種案件，在後面的分支判 `${v.hr_found}` 等於 `false`
- **直屬主管不是在職位設定填的，是推導出來的**：申請人所屬部門在[部門設定](../03_org_setup/departments.md)設定的部門主管；
  申請人自己就是主管、或那個部門沒有主管時，往上一層部門找，一路到最上層都沒有就是空的。副主管與代理人不算直屬主管。
- **依金額找核決人是從直屬主管開始往上找**，不含申請人自己；每一站看那位主管職位的職等在所選類別的上限，
  第一個「上限 ≥ 金額」的人就是核決人。沒設上限的職等視為 0；每一站主管若沒有有效職位，視為上限 0、繼續往上。整條鏈都不夠就 `hr_approver_found=false`
- 對象選「變數」時，變數裡要放帳號識別碼（例如上一顆節點寫出的 `${v.hr_direct_manager}`），
  這樣就能查「主管的主管」；別家企業的帳號一律視為找不到
- 金額欄位裡的逗號會自動去掉；解析不成數字時 `hr_approver_found=false`，流程照走
- 這顆節點只讀不寫，執行完立刻往下走，不會等待

## 常見問題

**申請單被退回，簽核歷程出現「找不到簽核人」。**
代表人事取值結果沒有找到可派簽的人。依序查：取值節點有沒有放在簽核之前、簽核節點填的是變數名 `hr_direct_manager`（不是 `${...}`）、
申請人在職位設定裡有沒有有效職位、申請人所屬部門（或上層部門）有沒有設定部門主管。若希望找不到人時先交給窗口處理，可在簽核節點設定改成「改派給角色」；
詳見[流程設計](workflows.md)的「簽核者解析為空時：退回或改派角色」一節。

**金額很小卻派到很高層。**
中間那幾層主管的職等在該類別沒有設上限（視為 0）。到[核決權限](../03_org_setup/job_approval_categories.md)補上。
