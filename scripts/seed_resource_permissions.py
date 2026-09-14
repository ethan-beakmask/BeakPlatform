#!/usr/bin/env python3
"""
Seed 資源類型的標準 CRUD 權限代碼

為指定 resource_type 建立 {type}:read / create / update / delete 四個權限。
已存在（含軟刪除）的代碼會跳過，可重複執行。

配合 ResourceGateway 階段 B 漸進推進：每批 model 註冊前先跑本腳本。

注意：本腳本是開發期工具，只影響當前環境的 DB。跑完後必須把新增的
權限代碼同步進編號 migration（參考 scripts/migrations/075_*.py 的格式），
否則 prod 部署時權限代碼缺漏，LIST_RBAC_ENFORCED_MODELS 內的 model
會全面拒絕存取。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

ACTIONS = ['read', 'create', 'update', 'delete']


def usage():
    print("""用法: python3 seed_resource_permissions.py <resource_type> [resource_type ...] [--level ORG|SYSTEM|MODULE]

為每個 resource_type 建立 read/create/update/delete 四個權限代碼。

參數:
  resource_type   資源類型（如 job_family duty_category），可一次多個
  --level         權限層級，預設 ORG

範例:
  python3 seed_resource_permissions.py job_family duty_category
  python3 seed_resource_permissions.py contract --level SYSTEM""")
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        usage()

    level = 'ORG'
    if '--level' in args:
        i = args.index('--level')
        try:
            level = args[i + 1]
        except IndexError:
            usage()
        args = args[:i] + args[i + 2:]

    if not args or level not in ('ORG', 'SYSTEM', 'MODULE'):
        usage()

    from app import create_app, db
    from app.models import Permission
    from app.utils.security import generate_secure_code

    app = create_app()
    with app.app_context():
        created, skipped = [], []
        for rtype in args:
            for action in ACTIONS:
                code = f"{rtype}:{action}"
                existing = Permission.query.filter_by(code=code).first()
                if existing:
                    skipped.append(code)
                    continue
                db.session.add(Permission(
                    secure_code=generate_secure_code(),
                    resource_type=rtype,
                    action=action,
                    code=code,
                    name=f"{rtype} {action}",
                    description=f"自動 seed：{rtype} 的 {action} 權限",
                    permission_level=level,
                    is_system_permission=False,
                    is_active=True,
                ))
                created.append(code)
        db.session.commit()
        print(f"建立 {len(created)} 筆: {', '.join(created) if created else '無'}")
        print(f"跳過 {len(skipped)} 筆(已存在): {', '.join(skipped) if skipped else '無'}")


if __name__ == '__main__':
    main()
