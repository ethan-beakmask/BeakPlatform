-- 114: DecisionWriter 節點移入「資安處置」分類，並開放給企業的流程設計者
-- 建立日期: 2026-08-24
--
-- 背景：074 當初以 require_system_admin=true 限制只有系統管理員能在設計器放置此節點，
-- 該檔註解本身就寫明「後續若導入角色守衛，可改 require_system_admin=false」。
--
-- 改成 false 的理由（2026-08-24 Ethan 決定）：
--   1. 流程設計頁的雙鑰匙已經只放行 ORG_ADMIN 與 FLOW_DESIGNER
--      （Key1 是 ORG_ADMIN + EMPLOYEE，Key2 是 ORG_ADMIN + FLOW_DESIGNER，
--       EXTERNAL 進不來），暴露面就是這兩者。
--   2. 這兩者本來就能編輯既有流程裡的防禦決策節點（PF-84 的屬性面板），
--      「不能新增」只是形式限制，實質防護價值很低。
--   3. 服務層的封鎖保護清單（PF-83）不受此旗標影響，內網目標照樣擋，
--      覆寫保護清單一律留稽核痕跡。
--   4. 這個旗標在實務上等於「誰都看不到」：唯一的 SYSTEM_ADMIN 帳號打
--      /api/workflows/data/node-definitions 會被 @module_access_required('form_workflow')
--      擋成 403（系統企業沒有 form_workflow 合約），所以先前沒有任何帳號拉得出這個節點。
--
-- 前端對應：category '資安處置' -> key 'security_ops'
--   後端 modules/form_workflow/api/workflows.py::get_node_definitions 的 category_map
--   前端 workflow-designer-init.js 的 CATEGORY_NAMES / CATEGORY_ICONS / categoryOrder
--   樣式 workflow-designer.css 的 .palette-node.security_ops
--
-- 冪等：可重複執行。

UPDATE workflow_node_definitions
SET category = '資安處置',
    require_system_admin = false,
    updated_at = CURRENT_TIMESTAMP
WHERE node_type = 'DecisionWriter'
  AND (category <> '資安處置' OR require_system_admin IS DISTINCT FROM false);
