---
title: API Key 管理
audience: ORG_ADMIN
order: 110
nav_menu: api_key_manage
covers:
  - backend/app/defaults/api_key_request_defaults.py
  - modules/form_workflow/services/node_handlers/api_key_issue_handler.py
  - backend/app/static/js/formio-form-picker.js
---

# API Key 管理

外部系統或設備要自動送表單進平台時，需要一把 API Key。Key 由成員填「API Key 申請單」申請，企業管理員核准後由系統自動核發。

!!! abstract "作業：申請 API Key"
    **MENU**：表單中心 ／ API Key 申請單

    1. 「使用者（Key 歸屬人）」預設是你自己；替同事申請時改選對方
    2. 在「授權表單」勾選這把 Key 可以代填的表單
    3. 填用途說明、有效期限；需要時填來源 IP 限制
    4. 送出，等企業管理員核准
    5. 核准後由 Key 歸屬人本人到個人設定「我的 API Key」按 [領取金鑰]，金鑰只顯示一次

## 授權表單的規則

**你手動填得到的表單，才能申請 Key 去自動填。**

- 「授權表單」只列出 Key 歸屬人自己填得到、而且已發行的表單。
- 替同事申請時，清單依那位同事計算；換人會重新載入，對方填不到的已勾項目會自動移除。
- 核發前系統會再驗一次。申請單上的表單超出歸屬人的填寫權限時，這張單不會核發 Key。
- 資安案件表單（處置中心那些）在表單中心看不到，但只要管理員在該表單的配對上授權了角色（例如資安人員），持有該角色的人就能在申請單裡選到它。沒有任何授權規則的資安表單，誰都申請不到，也不能手動送單。

## 自行設計申請單時

出廠的「API Key 申請單」可以直接用。要自己設計時，表單上的「API表單選擇」元件（設計器「系統申請單專用」群組）必須搭配流程裡的 ApiKeyIssue 節點：

- 元件的「Key 歸屬人欄位」要選表單上的人員選擇欄位。
- ApiKeyIssue 節點的 `beneficiary_field` 要填同一個欄位的 Key，`forms_field` 要填「API表單選擇」的 Key。
- 兩邊對不上時，發行會被擋下並指出是哪個節點的哪個設定。

!!! note "內容撰寫中"
    Key 的暫停、復原與撤銷等管理頁操作說明尚未撰寫。
