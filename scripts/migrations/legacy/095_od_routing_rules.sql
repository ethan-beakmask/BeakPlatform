-- 095: OpenDefense 事件路由改為規則式
-- 建立日期: 2026-08-09
-- 對應程式: modules/open_defense/services/routing_service.py
--           modules/open_defense/api/admin/routing_rules.py
--
-- 將 od_form_template_mappings 從單維 event_class 對照表擴充為多條、
-- 可排序、可組合條件的路由規則。既有資料 event_class 保留、priority=0、
-- match_rules=NULL，故舊行為維持不變。

ALTER TABLE od_form_template_mappings
    ALTER COLUMN event_class DROP NOT NULL;

ALTER TABLE od_form_template_mappings
    DROP CONSTRAINT IF EXISTS uq_od_template_map_org_event;

ALTER TABLE od_form_template_mappings
    ADD COLUMN IF NOT EXISTS name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS match_rules JSONB,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_od_template_map_org_priority
    ON od_form_template_mappings(org_secure_code, priority DESC, id);

COMMENT ON TABLE od_form_template_mappings IS
  'OpenDefense: 規則式事件路由,依 event_class/條件/priority 決定 form_template';
