---
title: 部門設定
audience: ORG_ADMIN
order: 20
nav_menu: departments
covers:
  - backend/app/web/departments.py
  - backend/app/templates/pages/admin/departments.html
  - backend/app/static/js/departments.js
  - backend/app/services/dept_membership_service.py
---

# 部門設定

部門設定用來維護部門成員、正副主管與候補代理人。

## 正主管、副主管與候補代理人

部門頁用三格拖放維護主管與候補。

!!! abstract "作業：調整主管與候補"
    **MENU**：帳號管理 ／ 部門設定

    1. 把成員拖到主管格，成為部門正主管
    2. 把成員拖到副主管格，成為部門副主管
    3. 把成員拖到候補代理人格，登記為候補代理人
    4. 把人拖回一般成員，即撤銷該格設定

正主管與副主管都會同時取得「部門主管」角色。
拖到候補代理人格時，候補對部門主管、部門正主管、部門副主管三個角色都生效。
候補只在該角色沒有任何在職持有者時才接手簽核。

## 常見問題

**設了正主管，為什麼「部門主管」也出現？**
正主管與副主管都持有「部門主管」角色，流程關卡指定「部門主管」時，正副主管任一人都可簽。

**候補和代理有什麼不同？**
代理是在指定期間內視同持有某個人的角色；候補是該角色沒有人可用時才生效。

!!! note "其他設定撰寫中"
    部門基本資料、成員清單與其他欄位的完整操作說明仍在撰寫中。
