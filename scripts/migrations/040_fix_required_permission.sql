-- 040_fix_required_permission.sql
-- Issue #16: 修正 required_permission 不一致
-- 選單門檻對齊路由實際檢查的最低權限

-- form_workflow: manage -> view (路由用 view)
UPDATE menu_items SET required_permission = 'form_workflow.template.view'
  WHERE code = 'form_workflow.templates' AND required_permission = 'form_workflow.template.manage';

UPDATE menu_items SET required_permission = 'form_workflow.workflow.view'
  WHERE code = 'form_workflow.workflows' AND required_permission = 'form_workflow.workflow.manage';

UPDATE menu_items SET required_permission = 'form_workflow.workflow.view'
  WHERE code = 'form_workflow.mappings' AND required_permission = 'form_workflow.workflow.manage';

-- spec_formulate 根選單: 清除跨模組引用 (區塊標題不需要 required_permission)
UPDATE menu_items SET required_permission = NULL
  WHERE code = 'spec_formulate' AND required_permission = 'form_workflow.template.manage';
