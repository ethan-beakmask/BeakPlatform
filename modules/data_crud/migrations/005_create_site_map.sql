-- 005_create_site_map.sql
-- Site Map 樹狀網站地圖
-- dc_site_map_nodes: 樹狀結構節點
-- dc_site_map_permissions: 節點權限白名單

-- =============================================================================
-- dc_site_map_nodes
-- =============================================================================
CREATE TABLE IF NOT EXISTS dc_site_map_nodes (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    sub_system_secure_code VARCHAR(32) NOT NULL,
    parent_secure_code VARCHAR(32),
    name VARCHAR(200) NOT NULL,
    icon VARCHAR(50),
    node_type VARCHAR(20) NOT NULL DEFAULT 'page'
        CHECK (node_type IN ('folder', 'page')),
    page_layout_secure_code VARCHAR(32),
    display_order INTEGER NOT NULL DEFAULT 0,
    crud_overrides JSONB DEFAULT '{}'::jsonb,
    data_filters JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_site_map_nodes_org
    ON dc_site_map_nodes (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_site_map_nodes_sub_system
    ON dc_site_map_nodes (sub_system_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_site_map_nodes_parent
    ON dc_site_map_nodes (parent_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_site_map_nodes_deleted
    ON dc_site_map_nodes (is_deleted);

GRANT SELECT, INSERT, UPDATE, DELETE ON dc_site_map_nodes TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE dc_site_map_nodes_id_seq TO beakplatform;


-- =============================================================================
-- dc_site_map_permissions
-- =============================================================================
CREATE TABLE IF NOT EXISTS dc_site_map_permissions (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,
    node_secure_code VARCHAR(32) NOT NULL,
    target_type VARCHAR(20) NOT NULL
        CHECK (target_type IN ('ROLE', 'DEPARTMENT', 'GROUP', 'ACCOUNT')),
    target_secure_code VARCHAR(32) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_site_map_permissions_org
    ON dc_site_map_permissions (org_secure_code);
CREATE INDEX IF NOT EXISTS idx_dc_site_map_permissions_node
    ON dc_site_map_permissions (node_secure_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dc_site_map_permissions_unique
    ON dc_site_map_permissions (node_secure_code, target_type, target_secure_code)
    WHERE is_deleted = FALSE;

GRANT SELECT, INSERT, UPDATE, DELETE ON dc_site_map_permissions TO beakplatform;
GRANT USAGE, SELECT ON SEQUENCE dc_site_map_permissions_id_seq TO beakplatform;
