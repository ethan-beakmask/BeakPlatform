-- 083: 清理 header/divider 型選單上的鑰匙2死資料
--
-- 背景 (2026-07-16):
--   _menu_tree._filter_by_role_requirements 對 header/divider（結構元素）直接放行，
--   其可見性由 _prune_empty_parents 依「是否有可見子項」決定——掛在結構元素上的
--   menu_role_requirements 永不被讀取，是純死資料，且會在 /menu/ 編輯頁（修正前）
--   與權限中央造成「根層要不要勾角色」的誤解。
--
--   來源：MENU_ROLE_DEFAULTS 原含 9 個 header 型 code（form_workflow、platform_help、
--   spec_formulate、nocode_builder、org_security、org_config_mgr、org_account、
--   jobs_config、roles_control），本次已自 menu_defaults.py 移除；
--   module_role_service 亦已加防呆跳過結構元素。
--
-- 處理方式：軟刪除（is_deleted=true），可回溯。冪等：重跑無副作用。

UPDATE menu_role_requirements mrr
SET is_deleted = true,
    deleted_at = now()
FROM menu_items mi
WHERE mi.secure_code = mrr.menu_secure_code
  AND mi.link_type IN ('header', 'divider')
  AND mrr.is_deleted = false;
