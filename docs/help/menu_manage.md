---
menu_code: menu_manage
title: 選單管理
audiences:
  - SYSTEM_ADMIN
  - ORG_ADMIN
sections:
  - audience: SYSTEM_ADMIN
    body: |
      ## 選單管理（系統管理員）

      管理整個 BeakPlatform 的導覽選單結構與權限。

      ### 雙鑰匙安全模型

      BeakPlatform 採用「雙鑰匙」設計，**兩把鑰匙都符合**才能看到選單：

      | 鑰匙 | 表 | 控制粒度 |
      |---|---|---|
      | 鑰匙 1：用戶類型 | `menu_permissions` | SYSTEM_ADMIN / ORG_ADMIN / EMPLOYEE / EXTERNAL |
      | 鑰匙 2：角色 | `menu_role_requirements` | 細到每個企業的特定角色 |

      若鑰匙 2 為空，則只看鑰匙 1；若鑰匙 2 有值，則用戶必須擁有指定角色之一才能看到。

      ### 新增選單項目

      | 欄位 | 說明 |
      |---|---|
      | code | 程式內識別碼，用於 help 文件對應 |
      | title | 顯示名稱（支援後續 i18n 多語） |
      | icon | Remix Icon class，如 `ri-dashboard-line` |
      | link_type | `route` / `url` / `page` / `divider` / `header` |
      | link_target | 依 link_type 不同：endpoint 名 / URL 路徑 / 頁面 secure_code |
      | parent | 上層選單（為空表示頂層） |

      **重要**：`link_type` 只能用上述五個值。其他值（如 `path`）會導致選單點擊無反應。

      ### 出廠重置

      `[重置為出廠值]` 會把所有預設選單恢復到 `menu_defaults` 表的快照狀態，
      但**不會刪除**用戶自建的選單（`is_user_created=True`）。

      ### 安全提醒

      修改選單**只控制顯示**，不控制路由的存取權限。
      路由本身的 `@admin_required` / `@login_required` 才是真正的存取控制。
      如有不一致，平台啟動時的 SEC-03 audit 會回報。

  - audience: ORG_ADMIN
    body: |
      ## 選單管理（企業管理員）

      企業管理員可調整本企業內各角色看得到的選單。

      ### 您能做什麼

      - 為本企業內已存在的選單項目，**指定哪些角色**可以看到
      - 例：將「報表中心」這個項目限定給 `MANAGER` 角色才能看

      ### 您不能做什麼

      - **無法新增/刪除選單項目**（這是系統管理員的權限）
      - 無法修改選單的圖示、連結、層級結構
      - 無法跨企業設定

      ### 操作步驟

      1. 從列表選擇要設定的選單項目，點擊 `[編輯]`
      2. 在「角色需求」區塊勾選或新增允許的角色
      3. 儲存後，**該角色的成員下次重新整理頁面**即生效

      ### 常見問題

      **Q：我新建了一個角色，但用該角色登入後看不到任何選單？**
      A：選單預設只允許 `ORG_ADMIN` / `EMPLOYEE` 等內建類型。
      新建角色需要在每個目標選單的「角色需求」中加入此角色，才能讓擁有者看到。
---
