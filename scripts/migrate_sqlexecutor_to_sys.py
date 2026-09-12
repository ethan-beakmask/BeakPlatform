#!/usr/bin/env python3
"""PF-254 將 SqlExecutor 一次性遷移為 SysSqlExecutor。"""
import os
import sys
import argparse

from sqlalchemy import text

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/migrate_sqlexecutor_to_sys.py --dry-run
  scripts/migrate_sqlexecutor_to_sys.py --apply

說明:
  PF-254 第一階段遷移：
  1. workflow_node_definitions: SqlExecutor 更名為 SysSqlExecutor，改成系統分類與受限節點
  2. workflow_node_org_grants: 授權紀錄的 node_type 同步更名（含軟刪除歷史）
  3. fw_workflow_templates: graph 與 cytoscape_config 內的節點型別字串同步更名
  4. fw_published_form_workflows: workflow_snapshot 內的節點型別字串同步更名
  5. fw_node_execution_queue / fw_node_execution_logs: 歷史 node_type 同步更名
  6. 對系統預設企業補種 SysSqlExecutor 出廠授權
  7. graph / cytoscape_config / workflow_snapshot 內 SQL 節點的 icon 路徑改新檔名
     （只換 type 為 SQL 節點的，AiAgent 借用舊圖示的歷史節點不動）

  --dry-run 只顯示結果；--apply 才會寫入資料庫。
"""


def _print_usage():
    print(USAGE)


def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _parse_args(argv):
    if any(arg in ('--help', '-h') for arg in argv):
        _print_usage()
        return None, 0
    if not argv:
        _print_usage()
        return None, 1

    parser = argparse.ArgumentParser(add_help=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--apply', action='store_true')
    try:
        parsed = parser.parse_args(argv)
    except SystemExit:
        _print_usage()
        return None, 1
    return ('--apply' if parsed.apply else '--dry-run'), 0


ICON_OLD_SUFFIX = 'workflow/sqlexecutor.svg'
ICON_NEW_SUFFIX = 'workflow/syssqlexecutor.svg'
ICON_AIAGENT_SUFFIX = 'workflow/aiagent.svg'
SQL_NODE_TYPES = ('SqlExecutor', 'SysSqlExecutor')


def _fix_icons_in_payload(payload):
    """把引用舊 `sqlexecutor.svg` 的節點 icon 導到正確的新檔案，回傳換掉幾個節點。

    **依 node type 分流，不做無差別字串替換**：
      - SQL 節點  -> `syssqlexecutor.svg`（本次更名的目的地）
      - `AiAgent` -> `aiagent.svg`。舊 graph 裡 AiAgent 借用過 sqlexecutor.svg
        （2026-08-20 才補自己的圖示），舊檔已隨本次更名 git mv 走，
        不一起導向正確檔案的話那些節點會破圖，而畫面不會有任何錯誤訊息。
      - 其他 type 一律不動。

    節點可能在 `graph.nodes` 也可能在 `cytoscape_config.nodes`，而發行快照是
    「graph ＋ cytoscape_config」的組合體，所以這裡遞迴走訪整包而不是只看頂層。
    icon 前綴有 `/static/` 與 `/beakplatform/static/` 兩種，比對結尾不比對整串。
    """
    counter = {'n': 0}

    def _walk(node):
        if isinstance(node, dict):
            icon = node.get('icon')
            if isinstance(icon, str) and icon.endswith(ICON_OLD_SUFFIX):
                node_type = node.get('type')
                target = None
                if node_type in SQL_NODE_TYPES:
                    target = ICON_NEW_SUFFIX
                elif node_type == 'AiAgent':
                    target = ICON_AIAGENT_SUFFIX
                if target:
                    node['icon'] = icon[: -len(ICON_OLD_SUFFIX)] + target
                    counter['n'] += 1
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(payload)
    return counter['n']


def _fix_node_icons(db, apply_changes):
    """graph / cytoscape_config / workflow_snapshot 三處的節點 icon。

    node_type 改名不會動到 icon 路徑，而 icon 檔案已隨更名 git mv 過去——
    漏了這一段的症狀是設計器畫布上該節點破圖，畫面沒有任何錯誤訊息。
    """
    import json as _json

    total = 0
    rows = db.session.execute(text("""
        SELECT id, graph::text, cytoscape_config::text
        FROM fw_workflow_templates
        WHERE graph::text LIKE :pat OR cytoscape_config::text LIKE :pat
    """), {'pat': f'%{ICON_OLD_SUFFIX}%'}).fetchall()
    for row_id, graph_text, cyto_text in rows:
        graph = _json.loads(graph_text) if graph_text else None
        cyto = _json.loads(cyto_text) if cyto_text else None
        hits = _fix_icons_in_payload(graph) + _fix_icons_in_payload(cyto)
        if not hits:
            continue
        total += hits
        if apply_changes:
            db.session.execute(text("""
                UPDATE fw_workflow_templates
                SET graph = CAST(:graph AS jsonb),
                    cytoscape_config = CAST(:cyto AS jsonb),
                    updated_at = NOW()
                WHERE id = :id
            """), {
                'graph': _json.dumps(graph, ensure_ascii=False) if graph is not None else None,
                'cyto': _json.dumps(cyto, ensure_ascii=False) if cyto is not None else None,
                'id': row_id,
            })

    rows = db.session.execute(text("""
        SELECT id, workflow_snapshot::text
        FROM fw_published_form_workflows
        WHERE workflow_snapshot::text LIKE :pat
    """), {'pat': f'%{ICON_OLD_SUFFIX}%'}).fetchall()
    for row_id, snap_text in rows:
        snap = _json.loads(snap_text) if snap_text else None
        hits = _fix_icons_in_payload(snap)
        if not hits:
            continue
        total += hits
        if apply_changes:
            db.session.execute(text("""
                UPDATE fw_published_form_workflows
                SET workflow_snapshot = CAST(:snap AS json)
                WHERE id = :id
            """), {'snap': _json.dumps(snap, ensure_ascii=False), 'id': row_id})

    return total


def _scalar(db, sql, params=None):
    return db.session.execute(text(sql), params or {}).scalar() or 0


def _execute(db, sql, params=None):
    result = db.session.execute(text(sql), params or {})
    return result.rowcount or 0


def _collect_counts(db):
    return {
        'node_definitions': _scalar(db, """
            SELECT count(*)
            FROM workflow_node_definitions
            WHERE node_type = 'SqlExecutor'
        """),
        'org_grants': _scalar(db, """
            SELECT count(*)
            FROM workflow_node_org_grants
            WHERE node_type = 'SqlExecutor'
        """),
        'template_graph': _scalar(db, """
            SELECT count(*)
            FROM fw_workflow_templates
            WHERE graph::text LIKE '%"SqlExecutor"%'
        """),
        'template_cytoscape_config': _scalar(db, """
            SELECT count(*)
            FROM fw_workflow_templates
            WHERE cytoscape_config::text LIKE '%"SqlExecutor"%'
        """),
        'published_snapshots': _scalar(db, """
            SELECT count(*)
            FROM fw_published_form_workflows
            WHERE workflow_snapshot::text LIKE '%"SqlExecutor"%'
        """),
        'execution_queue': _scalar(db, """
            SELECT count(*)
            FROM fw_node_execution_queue
            WHERE node_type = 'SqlExecutor'
        """),
        'execution_logs': _scalar(db, """
            SELECT count(*)
            FROM fw_node_execution_logs
            WHERE node_type = 'SqlExecutor'
        """),
        'system_org_grants_seeded': _scalar(db, """
            SELECT count(*)
            FROM workflow_node_definitions d
            CROSS JOIN organizations o
            WHERE d.node_type IN ('SqlExecutor', 'SysSqlExecutor')
              AND (d.node_type = 'SqlExecutor' OR d.org_restricted = TRUE)
              AND d.is_deleted = FALSE
              AND o.is_system_org = TRUE
              AND o.is_deleted = FALSE
              AND NOT EXISTS (
                  SELECT 1 FROM workflow_node_org_grants g
                  WHERE g.node_type = 'SysSqlExecutor'
                    AND g.org_secure_code = o.secure_code
                    AND g.is_deleted = FALSE
              )
        """),
    }


def _collect_icon_count(db):
    return _fix_node_icons(db, apply_changes=False)


def _apply(db):
    counts = {}
    counts['node_definitions'] = _execute(db, """
        UPDATE workflow_node_definitions
        SET node_type = 'SysSqlExecutor',
            display_name = '系統 SQL 執行',
            category = '系統',
            org_restricted = TRUE,
            description = '呼叫平台白名單內的預存程序（唯讀），結果寫入流程變數，可選擇插入一筆簽核註記。'
                          '企業識別碼由系統強制帶入。本節點為受限節點，出廠只授權系統預設企業。',
            icon = '/static/modules/form_workflow/icons/workflow/syssqlexecutor.svg',
            execution_handler = 'modules.form_workflow.services.node_handlers.sys_sqlexecutor_handler.SysSqlExecutorHandler',
            updated_at = NOW()
        WHERE node_type = 'SqlExecutor'
    """)
    counts['org_grants'] = _execute(db, """
        UPDATE workflow_node_org_grants
        SET node_type = 'SysSqlExecutor'
        WHERE node_type = 'SqlExecutor'
    """)
    counts['template_graph'] = _execute(db, """
        UPDATE fw_workflow_templates
        SET graph = replace(graph::text, '"SqlExecutor"', '"SysSqlExecutor"')::jsonb
        WHERE graph::text LIKE '%"SqlExecutor"%'
    """)
    counts['template_cytoscape_config'] = _execute(db, """
        UPDATE fw_workflow_templates
        SET cytoscape_config = replace(cytoscape_config::text, '"SqlExecutor"', '"SysSqlExecutor"')::jsonb
        WHERE cytoscape_config::text LIKE '%"SqlExecutor"%'
    """)
    counts['published_snapshots'] = _execute(db, """
        UPDATE fw_published_form_workflows
        SET workflow_snapshot = replace(workflow_snapshot::text, '"SqlExecutor"', '"SysSqlExecutor"')::json
        WHERE workflow_snapshot::text LIKE '%"SqlExecutor"%'
    """)
    counts['execution_queue'] = _execute(db, """
        UPDATE fw_node_execution_queue
        SET node_type = 'SysSqlExecutor'
        WHERE node_type = 'SqlExecutor'
    """)
    counts['execution_logs'] = _execute(db, """
        UPDATE fw_node_execution_logs
        SET node_type = 'SysSqlExecutor'
        WHERE node_type = 'SqlExecutor'
    """)
    counts['system_org_grants_seeded'] = _execute(db, """
        INSERT INTO workflow_node_org_grants (
            secure_code, node_type, org_secure_code, granted_by_secure_code,
            granted_by_name, note, created_at, updated_at, is_deleted
        )
        SELECT
            substr(md5(random()::text || clock_timestamp()::text), 1, 32),
            d.node_type, o.secure_code, NULL,
            'install_seed', 'system_org_default',
            now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', FALSE
        FROM workflow_node_definitions d
        CROSS JOIN organizations o
        WHERE d.node_type = 'SysSqlExecutor'
          AND d.org_restricted = TRUE
          AND d.is_deleted = FALSE
          AND o.is_system_org = TRUE
          AND o.is_deleted = FALSE
          AND NOT EXISTS (
              SELECT 1 FROM workflow_node_org_grants g
              WHERE g.node_type = d.node_type
                AND g.org_secure_code = o.secure_code
                AND g.is_deleted = FALSE
          )
    """)
    counts['node_icons'] = _fix_node_icons(db, apply_changes=True)
    return counts


def _print_counts(prefix, counts):
    print(prefix)
    for key, value in counts.items():
        print(f"  {key}: {value}")


def main():
    mode, exit_code = _parse_args(sys.argv[1:])
    if mode is None:
        return exit_code

    _load_dotenv()
    from app import create_app, db

    app = create_app()
    with app.app_context():
        try:
            if mode == '--apply':
                counts = _apply(db)
                db.session.commit()
                _print_counts('已寫入資料庫：', counts)
            else:
                counts = _collect_counts(db)
                counts['node_icons'] = _collect_icon_count(db)
                db.session.rollback()
                _print_counts('預覽，未寫入：', counts)
        except Exception:
            db.session.rollback()
            raise

    return 0


if __name__ == '__main__':
    sys.exit(main())
