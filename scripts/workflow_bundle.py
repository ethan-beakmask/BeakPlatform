#!/usr/bin/env python3
"""
BeakPlatform - 工作流設計稿匯出匯入工具

跨主機搬遷表單+流程+規格設計稿。匯出產生 JSON 包，匯入讀取後建立到目標企業。

** 開發工具 -- 僅限內部使用，不可外傳到 GitHub **

用法:
    # 全量匯出（整個企業的所有設計稿）
    python workflow_bundle.py export --db <DB_URL> --org-sc <ORG_SC> --all --output bundle.json

    # 匯出單一配對（表單+流程完整組合）
    python workflow_bundle.py export --db <DB_URL> --mapping-sc <SC> --output bundle.json

    # 匯出孤立表單
    python workflow_bundle.py export --db <DB_URL> --form-sc <SC> --output bundle.json

    # 匯出孤立流程
    python workflow_bundle.py export --db <DB_URL> --workflow-sc <SC> --output bundle.json

    # 預覽匯入（不寫入）
    python workflow_bundle.py import --db <DB_URL> --org-sc <ORG_SC> --input bundle.json --dry-run

    # 正式匯入
    python workflow_bundle.py import --db <DB_URL> --org-sc <ORG_SC> --input bundle.json

    # 匯入並覆蓋同名物件
    python workflow_bundle.py import --db <DB_URL> --org-sc <ORG_SC> --input bundle.json --force

參數說明:
    DB_URL  = .env 裡的 DATABASE_URL（PostgreSQL 連線字串）
    ORG_SC  = organizations 表的 secure_code（企業識別碼）

    查詢 ORG_SC:
        psql -h localhost -U beakplatform -d <資料庫名>
        SELECT secure_code, name FROM organizations WHERE is_deleted = false;

範例:
    # 家用開發環境，匯出 beluga 企業全量
    python workflow_bundle.py export --db postgresql://beakplatform:<密碼>@localhost/beakplatform_dev --org-sc _9c8TewkRkCBEf3XsUdqeF --all -o /mnt/smb/bundle.json

    # 家用正式環境，匯入到指定企業（先預覽）
    python workflow_bundle.py import --db postgresql://beakplatform:<密碼>@localhost/beakplatform --org-sc <目標企業SC> -i /mnt/smb/bundle.json --dry-run

    # 公司環境，匯出
    python workflow_bundle.py export --db postgresql://beakplatform:<密碼>@localhost/beakplatform --org-sc <公司企業SC> --all -o bundle.json

無參數執行顯示本說明。
"""
import argparse
import json
import secrets
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any

from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------
BUNDLE_FORMAT = 'beakplatform-workflow-bundle'
BUNDLE_VERSION = 1

# 需要清空的環境相依 assignee 類型
ENV_DEPENDENT_ASSIGNEE_TYPES = {'USER', 'ROLE', 'DEPARTMENT'}

# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def new_sc() -> str:
    """產生新的 secure_code"""
    return secrets.token_urlsafe(16)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row) -> dict:
    """sqlalchemy Row → dict"""
    return dict(row._mapping)


def log(msg: str):
    print(f'  {msg}')


def warn(msg: str):
    print(f'  [警告] {msg}')


def err(msg: str):
    print(f'  [錯誤] {msg}', file=sys.stderr)

# ---------------------------------------------------------------------------
# 匯出
# ---------------------------------------------------------------------------

class BundleExporter:
    """匯出器"""

    def __init__(self, engine):
        self.engine = engine
        self.conn = engine.connect()
        # 收集的物件（去重用 secure_code）
        self.categories: Dict[str, dict] = {}
        self.form_templates: Dict[str, dict] = {}
        self.workflow_templates: Dict[str, dict] = {}
        self.specs: Dict[str, dict] = {}
        self.mappings: Dict[str, dict] = {}
        self.published: Dict[str, dict] = {}
        # 追蹤已處理的 workflow（防遞迴無限迴圈）
        self._visited_workflows: Set[str] = set()

    def close(self):
        self.conn.close()

    # ── 收集方法 ──

    def collect_category(self, sc: str):
        """收集分類"""
        if not sc or sc in self.categories:
            return
        row = self.conn.execute(
            text('SELECT * FROM fw_categories WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': sc}
        ).fetchone()
        if row:
            d = row_to_dict(row)
            self.categories[sc] = d
            # 遞迴收集父分類
            parent_sc = d.get('parent_secure_code')
            if parent_sc:
                self.collect_category(parent_sc)

    def collect_form_template(self, sc: str):
        """收集表單模板"""
        if not sc or sc in self.form_templates:
            return
        row = self.conn.execute(
            text('SELECT * FROM fw_form_templates WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': sc}
        ).fetchone()
        if row:
            d = row_to_dict(row)
            self.form_templates[sc] = d
            # 收集分類
            self.collect_category(d.get('category_secure_code'))
            # 收集關聯的 spec
            self._collect_spec_by_form(sc)

    def collect_workflow_template(self, sc: str):
        """收集流程模板（含遞迴 Subflow）"""
        if not sc or sc in self._visited_workflows:
            return
        self._visited_workflows.add(sc)

        row = self.conn.execute(
            text('SELECT * FROM fw_workflow_templates WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': sc}
        ).fetchone()
        if not row:
            return
        d = row_to_dict(row)
        self.workflow_templates[sc] = d

        # 收集分類
        self.collect_category(d.get('category_secure_code'))

        # 遞迴收集 Subflow 引用的子流程
        graph = d.get('graph') or {}
        for node in graph.get('nodes', []):
            if node.get('type') == 'Subflow':
                subflow_sc = (node.get('config') or {}).get('workflow_secure_code')
                if subflow_sc:
                    self.collect_workflow_template(subflow_sc)

        # 收集子流程 (is_subprocess 標記的)
        if not d.get('is_subprocess'):
            subs = self.conn.execute(
                text('''SELECT secure_code FROM fw_workflow_templates
                        WHERE parent_workflow_secure_code = :sc AND is_deleted = false'''),
                {'sc': sc}
            ).fetchall()
            for sub in subs:
                self.collect_workflow_template(sub[0])

    def collect_mapping(self, sc: str):
        """收集配對及其關聯"""
        if not sc or sc in self.mappings:
            return
        row = self.conn.execute(
            text('SELECT * FROM fw_form_workflow_mappings WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': sc}
        ).fetchone()
        if not row:
            return
        d = row_to_dict(row)
        self.mappings[sc] = d

        # 收集表單和流程
        self.collect_form_template(d.get('form_template_secure_code'))
        self.collect_workflow_template(d.get('workflow_template_secure_code'))

        # 收集最新 published
        self._collect_latest_published(sc)

    def collect_spec(self, sc: str):
        """收集規格"""
        if not sc or sc in self.specs:
            return
        row = self.conn.execute(
            text('SELECT * FROM fw_spec_schema WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': sc}
        ).fetchone()
        if row:
            self.specs[sc] = row_to_dict(row)

    def _collect_spec_by_form(self, form_sc: str):
        """透過 form template SC 找到關聯的 spec"""
        row = self.conn.execute(
            text('''SELECT * FROM fw_spec_schema
                    WHERE linked_form_template_sc = :sc AND is_deleted = false'''),
            {'sc': form_sc}
        ).fetchone()
        if row:
            d = row_to_dict(row)
            self.specs[d['secure_code']] = d

    def _collect_latest_published(self, mapping_sc: str):
        """收集 mapping 的最新一版 published"""
        row = self.conn.execute(
            text('''SELECT * FROM fw_published_form_workflows
                    WHERE source_mapping_secure_code = :sc AND is_deleted = false
                    ORDER BY publish_version DESC LIMIT 1'''),
            {'sc': mapping_sc}
        ).fetchone()
        if row:
            d = row_to_dict(row)
            self.published[d['secure_code']] = d

    # ── 全量收集 ──

    def collect_all(self, org_sc: str):
        """全量收集企業所有設計稿"""
        # 所有分類
        rows = self.conn.execute(
            text('SELECT secure_code FROM fw_categories WHERE org_secure_code = :org AND is_deleted = false'),
            {'org': org_sc}
        ).fetchall()
        for r in rows:
            self.collect_category(r[0])

        # 所有表單模板
        rows = self.conn.execute(
            text('SELECT secure_code FROM fw_form_templates WHERE org_secure_code = :org AND is_deleted = false'),
            {'org': org_sc}
        ).fetchall()
        for r in rows:
            self.collect_form_template(r[0])

        # 所有流程模板
        rows = self.conn.execute(
            text('SELECT secure_code FROM fw_workflow_templates WHERE org_secure_code = :org AND is_deleted = false'),
            {'org': org_sc}
        ).fetchall()
        for r in rows:
            self.collect_workflow_template(r[0])

        # 所有配對
        rows = self.conn.execute(
            text('SELECT secure_code FROM fw_form_workflow_mappings WHERE org_secure_code = :org AND is_deleted = false'),
            {'org': org_sc}
        ).fetchall()
        for r in rows:
            self.collect_mapping(r[0])

        # 所有規格
        rows = self.conn.execute(
            text('SELECT secure_code FROM fw_spec_schema WHERE org_secure_code = :org AND is_deleted = false'),
            {'org': org_sc}
        ).fetchall()
        for r in rows:
            self.collect_spec(r[0])

    # ── 打包 ──

    def build_bundle(self, source_label: str = '') -> dict:
        """打包為 bundle dict"""
        # 建立 references 對照表
        refs = {}
        for sc, d in self.categories.items():
            refs[sc] = f"category:{d.get('name', '?')}"
        for sc, d in self.form_templates.items():
            refs[sc] = f"form_template:{d.get('name', '?')}"
        for sc, d in self.workflow_templates.items():
            refs[sc] = f"workflow_template:{d.get('name', '?')}"
        for sc, d in self.specs.items():
            refs[sc] = f"spec:{d.get('name', '?')}"
        for sc, d in self.mappings.items():
            refs[sc] = f"mapping:{d.get('description', '')} (form={d.get('form_template_secure_code', '?')})"
        for sc, d in self.published.items():
            refs[sc] = f"published:v{d.get('publish_version', '?')} {d.get('name', '')}"

        return {
            'format': BUNDLE_FORMAT,
            'version': BUNDLE_VERSION,
            'exported_at': now_iso(),
            'source': source_label,
            'objects': {
                'categories': list(self.categories.values()),
                'form_templates': list(self.form_templates.values()),
                'workflow_templates': list(self.workflow_templates.values()),
                'specs': list(self.specs.values()),
                'mappings': list(self.mappings.values()),
                'published': list(self.published.values()),
            },
            'references': refs,
        }


def _serialize_bundle(bundle: dict) -> str:
    """序列化 bundle（處理 datetime 等不可序列化類型）"""
    def _default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, '__str__'):
            return str(o)
        raise TypeError(f'Cannot serialize {type(o)}')
    return json.dumps(bundle, ensure_ascii=False, indent=2, default=_default)


def do_export(args):
    """執行匯出"""
    engine = create_engine(args.db)
    exporter = BundleExporter(engine)

    try:
        mode_count = sum([
            bool(args.all),
            bool(args.mapping_sc),
            bool(args.form_sc),
            bool(args.workflow_sc),
        ])
        if mode_count == 0:
            err('請指定匯出模式: --all, --mapping-sc, --form-sc, 或 --workflow-sc')
            sys.exit(1)
        if mode_count > 1:
            err('匯出模式只能擇一: --all, --mapping-sc, --form-sc, --workflow-sc')
            sys.exit(1)

        if args.all:
            if not args.org_sc:
                err('全量匯出需要 --org-sc')
                sys.exit(1)
            log(f'全量匯出企業: {args.org_sc}')
            exporter.collect_all(args.org_sc)
            source_label = f'org:{args.org_sc} (全量)'

        elif args.mapping_sc:
            log(f'匯出配對: {args.mapping_sc}')
            exporter.collect_mapping(args.mapping_sc)
            source_label = f'mapping:{args.mapping_sc}'

        elif args.form_sc:
            log(f'匯出表單: {args.form_sc}')
            exporter.collect_form_template(args.form_sc)
            source_label = f'form:{args.form_sc}'

        elif args.workflow_sc:
            log(f'匯出流程: {args.workflow_sc}')
            exporter.collect_workflow_template(args.workflow_sc)
            source_label = f'workflow:{args.workflow_sc}'

        bundle = exporter.build_bundle(source_label)

        # 統計
        objs = bundle['objects']
        log(f'收集完成:')
        log(f'  分類: {len(objs["categories"])}')
        log(f'  表單模板: {len(objs["form_templates"])}')
        log(f'  流程模板: {len(objs["workflow_templates"])}')
        log(f'  規格: {len(objs["specs"])}')
        log(f'  配對: {len(objs["mappings"])}')
        log(f'  發行版: {len(objs["published"])}')

        # 寫入
        output_path = args.output or f'bundle_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(_serialize_bundle(bundle))
        log(f'已寫入: {output_path}')

    finally:
        exporter.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# 匯入
# ---------------------------------------------------------------------------

class BundleImporter:
    """匯入器"""

    def __init__(self, engine, target_org_sc: str, force: bool = False, dry_run: bool = False):
        self.engine = engine
        self.conn = engine.connect()
        self.target_org_sc = target_org_sc
        self.force = force
        self.dry_run = dry_run
        # old_sc → new_sc 對照表
        self.sc_map: Dict[str, str] = {}
        # old_id → new_id 對照表
        self.id_map: Dict[str, int] = {}
        # 匯入統計
        self.stats = {
            'created': 0,
            'skipped': 0,
            'warnings': [],
        }

    def close(self):
        self.conn.close()

    def map_sc(self, old_sc: Optional[str]) -> Optional[str]:
        """查詢 old_sc 對應的 new_sc，沒有對照就回傳 None"""
        if not old_sc:
            return None
        return self.sc_map.get(old_sc)

    # ── 匯入各類物件 ──

    def import_categories(self, items: List[dict]):
        """匯入分類"""
        if not items:
            return
        log(f'匯入分類 ({len(items)} 筆)...')

        # 依 parent 排序：先匯入無 parent 的
        root_items = [i for i in items if not i.get('parent_secure_code')]
        child_items = [i for i in items if i.get('parent_secure_code')]

        for item in root_items + child_items:
            self._import_one_category(item)

    def _import_one_category(self, item: dict):
        old_sc = item['secure_code']
        name = item.get('name', '')

        # 檢查同名
        existing = self.conn.execute(
            text('''SELECT secure_code FROM fw_categories
                    WHERE org_secure_code = :org AND name = :name AND is_deleted = false'''),
            {'org': self.target_org_sc, 'name': name}
        ).fetchone()

        if existing:
            if self.force:
                self.sc_map[old_sc] = existing[0]
                log(f'  分類「{name}」已存在，使用既有 (force)')
            else:
                self.sc_map[old_sc] = existing[0]
                log(f'  分類「{name}」已存在，跳過')
                self.stats['skipped'] += 1
            return

        sc = new_sc()
        self.sc_map[old_sc] = sc

        if self.dry_run:
            log(f'  [預覽] 將建立分類「{name}」')
            return

        parent_sc = self.map_sc(item.get('parent_secure_code'))
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        self.conn.execute(
            text('''INSERT INTO fw_categories
                    (secure_code, org_secure_code, name, description, display_order,
                     is_system, show_in_form_design, show_in_workflow_design, show_in_form_center,
                     parent_secure_code, created_at, updated_at, is_deleted)
                    VALUES (:sc, :org, :name, :desc, :order,
                            :is_sys, :sfd, :swd, :sfc,
                            :parent, :now, :now, false)'''),
            {
                'sc': sc, 'org': self.target_org_sc,
                'name': name, 'desc': item.get('description', ''),
                'order': item.get('display_order', 0),
                'is_sys': item.get('is_system', False),
                'sfd': item.get('show_in_form_design', True),
                'swd': item.get('show_in_workflow_design', True),
                'sfc': item.get('show_in_form_center', True),
                'parent': parent_sc,
                'now': now,
            }
        )
        self.conn.commit()
        log(f'  建立分類「{name}」→ {sc}')
        self.stats['created'] += 1

    def import_form_templates(self, items: List[dict]):
        """匯入表單模板"""
        if not items:
            return
        log(f'匯入表單模板 ({len(items)} 筆)...')

        for item in items:
            old_sc = item['secure_code']
            name = item.get('name', '')
            code = item.get('code', '')

            # 檢查同名或同 code
            existing = self.conn.execute(
                text('''SELECT secure_code FROM fw_form_templates
                        WHERE org_secure_code = :org AND is_deleted = false
                          AND (name = :name OR code = :code)'''),
                {'org': self.target_org_sc, 'name': name, 'code': code}
            ).fetchone()

            if existing:
                if self.force:
                    self.sc_map[old_sc] = existing[0]
                    log(f'  表單「{name}」已存在，使用既有 (force)')
                else:
                    self.sc_map[old_sc] = existing[0]
                    log(f'  表單「{name}」已存在，跳過')
                    self.stats['skipped'] += 1
                continue

            sc = new_sc()
            self.sc_map[old_sc] = sc

            if self.dry_run:
                log(f'  [預覽] 將建立表單「{name}」(code={code})')
                continue

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cat_sc = self.map_sc(item.get('category_secure_code'))

            self.conn.execute(
                text('''INSERT INTO fw_form_templates
                        (secure_code, org_secure_code, code, name, description, category,
                         schema, version, revision, builder_config,
                         thumbnail_2x1, thumbnail_1x1, thumbnail_1x2,
                         is_published, is_active, is_protected,
                         permission_type, owner_secure_code, allowed_editors,
                         category_secure_code,
                         created_at, updated_at, is_deleted)
                        VALUES (:sc, :org, :code, :name, :desc, :cat,
                                :schema, :ver, :rev, :builder,
                                :t2x1, :t1x1, :t1x2,
                                false, true, false,
                                :perm, NULL, :editors,
                                :cat_sc,
                                :now, :now, false)'''),
                {
                    'sc': sc, 'org': self.target_org_sc,
                    'code': code, 'name': name,
                    'desc': item.get('description', ''),
                    'cat': item.get('category', ''),
                    'schema': json.dumps(item.get('schema') or {}, ensure_ascii=False),
                    'ver': item.get('version', '1'),
                    'rev': item.get('revision', 1),
                    'builder': json.dumps(item.get('builder_config') or {}, ensure_ascii=False),
                    't2x1': item.get('thumbnail_2x1'),
                    't1x1': item.get('thumbnail_1x1'),
                    't1x2': item.get('thumbnail_1x2'),
                    'perm': item.get('permission_type', 'org'),
                    'editors': json.dumps(item.get('allowed_editors') or [], ensure_ascii=False),
                    'cat_sc': cat_sc,
                    'now': now,
                }
            )
            self.conn.commit()

            # 記錄 old_id → new_id
            new_row = self.conn.execute(
                text('SELECT id FROM fw_form_templates WHERE secure_code = :sc'),
                {'sc': sc}
            ).fetchone()
            if new_row:
                self.id_map[f'ft:{old_sc}'] = new_row[0]

            log(f'  建立表單「{name}」→ {sc}')
            self.stats['created'] += 1

    def import_workflow_templates(self, items: List[dict]):
        """匯入流程模板"""
        if not items:
            return
        log(f'匯入流程模板 ({len(items)} 筆)...')

        # 先處理非子流程，再處理子流程（確保 parent 已建立）
        main_items = [i for i in items if not i.get('is_subprocess')]
        sub_items = [i for i in items if i.get('is_subprocess')]

        for item in main_items + sub_items:
            self._import_one_workflow(item)

    def _import_one_workflow(self, item: dict):
        old_sc = item['secure_code']
        name = item.get('name', '')
        code = item.get('code', '')

        # 檢查同名
        existing = self.conn.execute(
            text('''SELECT secure_code FROM fw_workflow_templates
                    WHERE org_secure_code = :org AND is_deleted = false
                      AND name = :name'''),
            {'org': self.target_org_sc, 'name': name}
        ).fetchone()

        if existing:
            if self.force:
                self.sc_map[old_sc] = existing[0]
                log(f'  流程「{name}」已存在，使用既有 (force)')
            else:
                self.sc_map[old_sc] = existing[0]
                log(f'  流程「{name}」已存在，跳過')
                self.stats['skipped'] += 1
            return

        sc = new_sc()
        self.sc_map[old_sc] = sc

        # 處理 graph 內的引用
        graph = item.get('graph') or {}
        graph, graph_warnings = self._process_graph(graph)

        for w in graph_warnings:
            warn(w)
            self.stats['warnings'].append(w)

        if self.dry_run:
            log(f'  [預覽] 將建立流程「{name}」(code={code})')
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cat_sc = self.map_sc(item.get('category_secure_code'))
        form_sc = self.map_sc(item.get('form_template_secure_code'))
        parent_wf_sc = self.map_sc(item.get('parent_workflow_secure_code'))

        self.conn.execute(
            text('''INSERT INTO fw_workflow_templates
                    (secure_code, org_secure_code, code, name, description, category,
                     graph, cytoscape_config, version, revision,
                     thumbnail_2x1, thumbnail_1x1, thumbnail_1x2,
                     is_published, is_active, is_protected,
                     permission_type, owner_secure_code, allowed_editors,
                     is_subprocess, parent_workflow_secure_code, timeout_minutes,
                     category_secure_code, form_template_secure_code,
                     created_at, updated_at, is_deleted)
                    VALUES (:sc, :org, :code, :name, :desc, :cat,
                            :graph, :cyto, :ver, :rev,
                            :t2x1, :t1x1, :t1x2,
                            false, true, false,
                            :perm, NULL, :editors,
                            :is_sub, :parent_wf, :timeout,
                            :cat_sc, :form_sc,
                            :now, :now, false)'''),
            {
                'sc': sc, 'org': self.target_org_sc,
                'code': code or '', 'name': name,
                'desc': item.get('description', ''),
                'cat': item.get('category', ''),
                'graph': json.dumps(graph, ensure_ascii=False),
                'cyto': json.dumps(item.get('cytoscape_config') or {}, ensure_ascii=False),
                'ver': item.get('version', '1'),
                'rev': item.get('revision', 1),
                't2x1': item.get('thumbnail_2x1'),
                't1x1': item.get('thumbnail_1x1'),
                't1x2': item.get('thumbnail_1x2'),
                'perm': item.get('permission_type', 'org'),
                'editors': json.dumps(item.get('allowed_editors') or [], ensure_ascii=False),
                'is_sub': item.get('is_subprocess', False),
                'parent_wf': parent_wf_sc,
                'timeout': item.get('timeout_minutes'),
                'cat_sc': cat_sc,
                'form_sc': form_sc,
                'now': now,
            }
        )
        self.conn.commit()

        new_row = self.conn.execute(
            text('SELECT id FROM fw_workflow_templates WHERE secure_code = :sc'),
            {'sc': sc}
        ).fetchone()
        if new_row:
            self.id_map[f'wt:{old_sc}'] = new_row[0]

        log(f'  建立流程「{name}」→ {sc}')
        self.stats['created'] += 1

    def _process_graph(self, graph: dict) -> tuple:
        """
        處理 graph JSON 內嵌的環境相依引用

        Returns:
            (processed_graph, warnings)
        """
        if not graph or 'nodes' not in graph:
            return graph, []

        import copy
        graph = copy.deepcopy(graph)
        warnings = []

        for node in graph.get('nodes', []):
            node_type = node.get('type', '')
            config = node.get('config') or {}
            node_label = node.get('label', node.get('id', '?'))

            if node_type == 'FormAdapter':
                assignee_type = config.get('assignee_type', '')
                if assignee_type in ENV_DEPENDENT_ASSIGNEE_TYPES:
                    old_value = config.get('assignee_value', '')
                    if old_value:
                        config['assignee_value'] = ''
                        config['assignee_list'] = []
                        warnings.append(
                            f'節點「{node_label}」: {assignee_type} 指派 '
                            f'"{old_value}" 已清空，需在目標環境重新設定'
                        )

            elif node_type == 'Subflow':
                old_wf_sc = config.get('workflow_secure_code', '')
                if old_wf_sc:
                    new_wf_sc = self.map_sc(old_wf_sc)
                    if new_wf_sc:
                        config['workflow_secure_code'] = new_wf_sc
                    else:
                        warnings.append(
                            f'節點「{node_label}」: Subflow 引用 {old_wf_sc} '
                            f'在匯入包中找不到對應，保留原值'
                        )

            elif node_type in ('SysEmailRelay', 'Telegram', 'Email'):
                warnings.append(
                    f'節點「{node_label}」({node_type}): '
                    f'通知設定為環境相依，需在目標環境檢查'
                )

            node['config'] = config

        return graph, warnings

    def import_specs(self, items: List[dict]):
        """匯入規格"""
        if not items:
            return
        log(f'匯入規格 ({len(items)} 筆)...')

        for item in items:
            old_sc = item['secure_code']
            name = item.get('name', '')

            existing = self.conn.execute(
                text('''SELECT secure_code FROM fw_spec_schema
                        WHERE org_secure_code = :org AND name = :name AND is_deleted = false'''),
                {'org': self.target_org_sc, 'name': name}
            ).fetchone()

            if existing:
                if self.force:
                    self.sc_map[old_sc] = existing[0]
                    log(f'  規格「{name}」已存在，使用既有 (force)')
                else:
                    self.sc_map[old_sc] = existing[0]
                    log(f'  規格「{name}」已存在，跳過')
                    self.stats['skipped'] += 1
                continue

            sc = new_sc()
            self.sc_map[old_sc] = sc

            if self.dry_run:
                log(f'  [預覽] 將建立規格「{name}」')
                continue

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            linked_ft_sc = self.map_sc(item.get('linked_form_template_sc'))

            self.conn.execute(
                text('''INSERT INTO fw_spec_schema
                        (secure_code, org_secure_code, name, description, version,
                         fields, active_facets, status, table_name,
                         linked_form_template_sc, linked_sql_table, linked_sql_target,
                         last_modified_by, last_modified_by_name,
                         created_at, updated_at, is_deleted)
                        VALUES (:sc, :org, :name, :desc, :ver,
                                :fields, :facets, :status, :tbl,
                                :ft_sc, :sql_tbl, :sql_target,
                                NULL, NULL,
                                :now, :now, false)'''),
                {
                    'sc': sc, 'org': self.target_org_sc,
                    'name': name, 'desc': item.get('description', ''),
                    'ver': item.get('version', 1),
                    'fields': json.dumps(item.get('fields') or [], ensure_ascii=False),
                    'facets': json.dumps(item.get('active_facets') or [], ensure_ascii=False),
                    'status': item.get('status', 'active'),
                    'tbl': item.get('table_name', ''),
                    'ft_sc': linked_ft_sc,
                    'sql_tbl': item.get('linked_sql_table', ''),
                    'sql_target': item.get('linked_sql_target', ''),
                    'now': now,
                }
            )
            self.conn.commit()
            log(f'  建立規格「{name}」→ {sc}')
            self.stats['created'] += 1

    def import_mappings(self, items: List[dict]):
        """匯入配對"""
        if not items:
            return
        log(f'匯入配對 ({len(items)} 筆)...')

        for item in items:
            old_sc = item['secure_code']
            ft_sc = self.map_sc(item.get('form_template_secure_code'))
            wt_sc = self.map_sc(item.get('workflow_template_secure_code'))

            if not ft_sc or not wt_sc:
                warn(f'  配對 {old_sc}: 表單或流程未成功匯入，跳過')
                self.stats['skipped'] += 1
                continue

            # 檢查同組合是否已存在
            existing = self.conn.execute(
                text('''SELECT secure_code FROM fw_form_workflow_mappings
                        WHERE org_secure_code = :org AND is_deleted = false
                          AND form_template_secure_code = :ft
                          AND workflow_template_secure_code = :wt'''),
                {'org': self.target_org_sc, 'ft': ft_sc, 'wt': wt_sc}
            ).fetchone()

            if existing:
                self.sc_map[old_sc] = existing[0]
                log(f'  配對 (form={ft_sc}, wf={wt_sc}) 已存在，跳過')
                self.stats['skipped'] += 1
                continue

            sc = new_sc()
            self.sc_map[old_sc] = sc

            if self.dry_run:
                log(f'  [預覽] 將建立配對 (form={ft_sc}, wf={wt_sc})')
                continue

            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # 取得新的 id
            ft_id = self.id_map.get(f'ft:{item.get("form_template_secure_code")}')
            wt_id = self.id_map.get(f'wt:{item.get("workflow_template_secure_code")}')

            # 如果是既有物件，查 id
            if not ft_id:
                r = self.conn.execute(
                    text('SELECT id FROM fw_form_templates WHERE secure_code = :sc'),
                    {'sc': ft_sc}
                ).fetchone()
                ft_id = r[0] if r else None

            if not wt_id:
                r = self.conn.execute(
                    text('SELECT id FROM fw_workflow_templates WHERE secure_code = :sc'),
                    {'sc': wt_sc}
                ).fetchone()
                wt_id = r[0] if r else None

            self.conn.execute(
                text('''INSERT INTO fw_form_workflow_mappings
                        (secure_code, org_secure_code,
                         form_template_id, form_template_secure_code, form_template_code, form_template_version,
                         workflow_template_id, workflow_template_secure_code, workflow_template_code, workflow_template_version,
                         is_active, priority, is_published, is_archived,
                         sql_sync_enabled, numbering_rule_secure_code,
                         description,
                         created_at, updated_at, is_deleted)
                        VALUES (:sc, :org,
                                :ft_id, :ft_sc, :ft_code, :ft_ver,
                                :wt_id, :wt_sc, :wt_code, :wt_ver,
                                true, :pri, false, false,
                                :sync, NULL,
                                :desc,
                                :now, :now, false)'''),
                {
                    'sc': sc, 'org': self.target_org_sc,
                    'ft_id': ft_id, 'ft_sc': ft_sc,
                    'ft_code': item.get('form_template_code', ''),
                    'ft_ver': item.get('form_template_version', '1'),
                    'wt_id': wt_id, 'wt_sc': wt_sc,
                    'wt_code': item.get('workflow_template_code', ''),
                    'wt_ver': item.get('workflow_template_version', '1'),
                    'pri': item.get('priority', 10),
                    'sync': item.get('sql_sync_enabled', False),
                    'desc': item.get('description', ''),
                    'now': now,
                }
            )
            self.conn.commit()
            log(f'  建立配對 → {sc}')
            self.stats['created'] += 1

    def import_published(self, items: List[dict]):
        """匯入發行版（選用）"""
        if not items:
            return
        log(f'匯入發行版 ({len(items)} 筆)...')

        for item in items:
            old_sc = item['secure_code']
            mapping_sc = self.map_sc(item.get('source_mapping_secure_code'))
            ft_sc = self.map_sc(item.get('source_form_template_secure_code'))
            wt_sc = self.map_sc(item.get('source_workflow_template_secure_code'))

            if not mapping_sc:
                warn(f'  發行版 {old_sc}: 配對未匯入，跳過')
                self.stats['skipped'] += 1
                continue

            # 檢查同 mapping + 同版本是否已存在
            existing = self.conn.execute(
                text('''SELECT secure_code FROM fw_published_form_workflows
                        WHERE org_secure_code = :org AND source_mapping_secure_code = :m_sc
                          AND publish_version = :pv AND is_deleted = false'''),
                {'org': self.target_org_sc, 'm_sc': mapping_sc, 'pv': item.get('publish_version', 1)}
            ).fetchone()

            if existing:
                self.sc_map[old_sc] = existing[0]
                log(f'  發行版 v{item.get("publish_version")} 已存在，跳過')
                self.stats['skipped'] += 1
                continue

            sc = new_sc()
            self.sc_map[old_sc] = sc

            if self.dry_run:
                log(f'  [預覽] 將建立發行版 v{item.get("publish_version")}')
                continue

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            mapping_id = None
            ft_id = self.id_map.get(f'ft:{item.get("source_form_template_secure_code")}')
            wt_id = self.id_map.get(f'wt:{item.get("source_workflow_template_secure_code")}')

            # 查 mapping id
            r = self.conn.execute(
                text('SELECT id FROM fw_form_workflow_mappings WHERE secure_code = :sc'),
                {'sc': mapping_sc}
            ).fetchone()
            mapping_id = r[0] if r else None

            if not ft_id and ft_sc:
                r = self.conn.execute(
                    text('SELECT id FROM fw_form_templates WHERE secure_code = :sc'),
                    {'sc': ft_sc}
                ).fetchone()
                ft_id = r[0] if r else None

            if not wt_id and wt_sc:
                r = self.conn.execute(
                    text('SELECT id FROM fw_workflow_templates WHERE secure_code = :sc'),
                    {'sc': wt_sc}
                ).fetchone()
                wt_id = r[0] if r else None

            self.conn.execute(
                text('''INSERT INTO fw_published_form_workflows
                        (secure_code, org_secure_code,
                         source_mapping_id, source_mapping_secure_code,
                         source_form_template_id, source_form_template_secure_code,
                         source_form_version, source_form_revision,
                         source_workflow_template_id, source_workflow_template_secure_code,
                         source_workflow_version, source_workflow_revision,
                         publish_version, name, description,
                         form_snapshot, workflow_snapshot,
                         status, is_used, instance_count,
                         published_by, published_by_name, published_at,
                         sql_sync_enabled, numbering_rule_secure_code,
                         created_at, updated_at, is_deleted)
                        VALUES (:sc, :org,
                                :m_id, :m_sc,
                                :ft_id, :ft_sc,
                                :fv, :fr,
                                :wt_id, :wt_sc,
                                :wv, :wr,
                                :pv, :name, :desc,
                                :f_snap, :w_snap,
                                :status, false, 0,
                                NULL, NULL, :now,
                                :sync, NULL,
                                :now, :now, false)'''),
                {
                    'sc': sc, 'org': self.target_org_sc,
                    'm_id': mapping_id, 'm_sc': mapping_sc,
                    'ft_id': ft_id, 'ft_sc': ft_sc,
                    'fv': item.get('source_form_version', '1'),
                    'fr': item.get('source_form_revision', 1),
                    'wt_id': wt_id, 'wt_sc': wt_sc,
                    'wv': item.get('source_workflow_version', '1'),
                    'wr': item.get('source_workflow_revision', 1),
                    'pv': item.get('publish_version', 1),
                    'name': item.get('name', ''),
                    'desc': item.get('description', ''),
                    'f_snap': json.dumps(item.get('form_snapshot') or {}, ensure_ascii=False),
                    'w_snap': json.dumps(item.get('workflow_snapshot') or {}, ensure_ascii=False),
                    'status': item.get('status') if item.get('status') in ('Published', 'Suspended', 'Archived') else 'Suspended',
                    'sync': item.get('sql_sync_enabled', False),
                    'now': now,
                }
            )
            self.conn.commit()
            log(f'  建立發行版 v{item.get("publish_version")} → {sc} (status={item.get("status", "?")}→Suspended)')
            self.stats['created'] += 1


def do_import(args):
    """執行匯入"""
    if not args.input:
        err('請指定 --input 檔案路徑')
        sys.exit(1)
    if not args.org_sc:
        err('請指定 --org-sc 目標企業 secure_code')
        sys.exit(1)

    # 讀取 bundle
    with open(args.input, 'r', encoding='utf-8') as f:
        bundle = json.load(f)

    if bundle.get('format') != BUNDLE_FORMAT:
        err(f'格式不符: 預期 {BUNDLE_FORMAT}，得到 {bundle.get("format")}')
        sys.exit(1)

    objs = bundle.get('objects', {})
    refs = bundle.get('references', {})

    print(f'Bundle 資訊:')
    print(f'  匯出時間: {bundle.get("exported_at")}')
    print(f'  來源: {bundle.get("source")}')
    print(f'  分類: {len(objs.get("categories", []))}')
    print(f'  表單模板: {len(objs.get("form_templates", []))}')
    print(f'  流程模板: {len(objs.get("workflow_templates", []))}')
    print(f'  規格: {len(objs.get("specs", []))}')
    print(f'  配對: {len(objs.get("mappings", []))}')
    print(f'  發行版: {len(objs.get("published", []))}')
    print()

    engine = create_engine(args.db)
    importer = BundleImporter(engine, args.org_sc, force=args.force, dry_run=args.dry_run)

    try:
        if args.dry_run:
            print('=== 預覽模式（不寫入資料庫）===')
        else:
            print('=== 開始匯入 ===')

        # 驗證目標企業存在
        row = importer.conn.execute(
            text('SELECT name FROM organizations WHERE secure_code = :sc AND is_deleted = false'),
            {'sc': args.org_sc}
        ).fetchone()
        if not row:
            err(f'目標企業 {args.org_sc} 不存在')
            sys.exit(1)
        log(f'目標企業: {row[0]} ({args.org_sc})')
        print()

        # 依序匯入（依賴順序）
        importer.import_categories(objs.get('categories', []))
        importer.import_form_templates(objs.get('form_templates', []))
        importer.import_workflow_templates(objs.get('workflow_templates', []))
        importer.import_specs(objs.get('specs', []))
        importer.import_mappings(objs.get('mappings', []))
        importer.import_published(objs.get('published', []))

        # 統計
        print()
        print('=== 匯入完成 ===')
        print(f'  建立: {importer.stats["created"]}')
        print(f'  跳過: {importer.stats["skipped"]}')
        if importer.stats['warnings']:
            print(f'  警告: {len(importer.stats["warnings"])}')
            for w in importer.stats['warnings']:
                print(f'    - {w}')

    finally:
        importer.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='BeakPlatform 工作流設計稿匯出匯入工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest='command', help='指令')

    # ── export ──
    p_export = subparsers.add_parser('export', help='匯出設計稿')
    p_export.add_argument('--db', required=True, help='資料庫連線字串 (postgresql://...)')
    p_export.add_argument('--org-sc', help='企業 secure_code（全量匯出必填）')
    p_export.add_argument('--all', action='store_true', help='全量匯出')
    p_export.add_argument('--mapping-sc', help='匯出指定配對')
    p_export.add_argument('--form-sc', help='匯出指定表單')
    p_export.add_argument('--workflow-sc', help='匯出指定流程')
    p_export.add_argument('--output', '-o', help='輸出檔路徑（預設自動命名）')

    # ── import ──
    p_import = subparsers.add_parser('import', help='匯入設計稿')
    p_import.add_argument('--db', required=True, help='資料庫連線字串 (postgresql://...)')
    p_import.add_argument('--org-sc', required=True, help='目標企業 secure_code')
    p_import.add_argument('--input', '-i', required=True, help='輸入 bundle 檔路徑')
    p_import.add_argument('--force', action='store_true', help='覆蓋同名物件')
    p_import.add_argument('--dry-run', action='store_true', help='預覽模式（不寫入）')

    args = parser.parse_args()

    if not args.command:
        print(__doc__.strip())
        sys.exit(0)

    if args.command == 'export':
        do_export(args)
    elif args.command == 'import':
        do_import(args)


if __name__ == '__main__':
    main()
