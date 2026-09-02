---
title: 模組權限管理
audience: ORG_ADMIN
order: 170
nav_menu: module_perm_mgmt
covers:
  - backend/app/web/admin.py
  - backend/app/templates/pages/admin/module_permissions.html
  - backend/app/static/js/module-permissions.js
  - backend/app/api/module_access.py
  - backend/app/services/module_access_service.py
---

# 模組權限管理

這一頁列出貴公司**依合約可用的模組**，並決定**公司裡的誰能用**每個模組。

!!! abstract "作業：讓某個部門能用某模組"
    **MENU**：角色管控 ／ 模組權限管理

    1. 在該模組列按 [管理使用者]
    2. 按 [新增指派]
    3. 指派類型選「部門」，搜尋並點選部門
    4. 按 [確定新增]

!!! abstract "作業：收回某人的模組使用權"
    **MENU**：角色管控 ／ 模組權限管理

    1. 在該模組列按 [管理使用者]
    2. 找到該筆指派按 [移除]

## 畫面上看不出來的規則

- 「授權狀態」與剩餘天數來自合約，**這裡改不了**。合約到期模組會整個消失，
  要延長請聯絡平台的系統管理員
- 指派對象四種：角色、部門、群組、個人帳號，符合任一筆即可用
- **企業管理員永遠能用所有已授權模組**，不需要也不必替自己加指派
- **一筆指派都沒有時，只有企業管理員能用**。把指派全部移除不會開放給所有人，
  而是只剩管理員
- 合約建立時系統已自動帶入預設角色，所以剛開通時通常已經有幾筆指派。
  想改成只給特定人用，先新增自己的指派再移除預設的那幾筆
- 移除立刻生效，正在該模組頁面操作中的人下一個動作就會被擋

## 常見問題

**員工說模組的選單看得到，點進去卻沒權限。**
選單可見性與模組使用權是兩件事。先在這裡確認他符合某一筆指派，
再到[權限管理中心](access_center.md)確認該選單的角色門檻。
