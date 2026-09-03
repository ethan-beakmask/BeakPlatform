#!/usr/bin/env python3
"""複製系統企業 SMTP 測試設定到指定企業。

冪等規則：目標企業若已存在未刪除且 username 與來源相同的 SMTP 設定，
一律跳過，不新增、不更新密碼，也不改動既有預設設定。
"""
import argparse
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/seed_smtp_test_config.py --orgs BELUGA,LION --dry-run
  scripts/seed_smtp_test_config.py --orgs BELUGA,LION --apply
  scripts/seed_smtp_test_config.py --orgs BELUGA,LION --apply --source-name "lionsecbot@gmail.com"
  scripts/seed_smtp_test_config.py --orgs BELUGA,LION --apply --no-default
  scripts/seed_smtp_test_config.py --help

說明:
  從系統企業複製已驗證的 SMTP 設定到指定企業。
  已有相同 username 的未刪除設定時會跳過，不修改既有資料。
  --dry-run 只顯示將執行的動作；--apply 才會寫入資料庫。
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


def _parse_org_codes(raw_orgs):
    return [
        code
        for code in (part.strip().upper() for part in raw_orgs.split(','))
        if code
    ]


def _build_parser():
    parser = argparse.ArgumentParser(
        description='複製系統企業 SMTP 測試設定到指定企業。',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        '--orgs',
        required=True,
        help='逗號分隔的企業 code，例如 BELUGA,LION',
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--dry-run',
        action='store_true',
        help='只顯示將執行的動作，不寫入資料庫',
    )
    mode_group.add_argument(
        '--apply',
        action='store_true',
        help='寫入資料庫',
    )
    parser.add_argument(
        '--source-name',
        help='指定系統企業內的來源 SMTP 設定 name',
    )
    parser.add_argument(
        '--no-default',
        action='store_true',
        help='新設定不設為預設，也不清除其他設定的預設狀態',
    )
    return parser


def _print_source(source_org, source_config):
    print(
        f"來源: {source_org.code} / {source_config.name} / "
        f"{source_config.username} / {source_config.smtp_host}:{source_config.smtp_port}"
    )


def _print_result(code, action, secure_code='-'):
    print(f"{code}  {action}  {secure_code or '-'}")


def _find_source_config(source_org, source_name):
    from app.models import SmtpConfig

    if source_name:
        return SmtpConfig.query.filter_by(
            org_secure_code=source_org.secure_code,
            name=source_name,
            is_deleted=False,
        ).first()
    return SmtpConfig.get_default_config(source_org.secure_code)


def _clone_config(source, target_org, source_password, set_default):
    from app.models import SmtpConfig

    new_config = SmtpConfig(
        org_secure_code=target_org.secure_code,
        name=source.name,
        description=source.description,
        smtp_host=source.smtp_host,
        smtp_port=source.smtp_port,
        use_tls=source.use_tls,
        use_ssl=source.use_ssl,
        username=source.username,
        use_app_password=source.use_app_password,
        from_email=source.from_email,
        from_name=source.from_name,
        provider_type=source.provider_type,
        priority=source.priority,
        is_active=True,
        is_default=set_default,
        last_test_at=None,
        last_test_success=None,
        last_test_message=None,
    )
    new_config.set_password(source_password)
    return new_config


def main():
    if len(sys.argv) == 1:
        _print_usage()
        return 1

    args = _build_parser().parse_args()
    org_codes = _parse_org_codes(args.orgs)

    _load_dotenv()
    from app import create_app, db
    from app.models import Organization, SmtpConfig

    app = create_app()
    with app.app_context():
        try:
            system_org = Organization.query.filter_by(
                is_system_org=True,
                is_deleted=False,
            ).first()
            if not system_org:
                print("錯誤: 系統企業不存在")
                return 3

            source = _find_source_config(system_org, args.source_name)
            if not source:
                print("錯誤: 來源設定組找不到")
                return 3

            source_password = source.get_password()
            if not source_password:
                print("錯誤: 來源密碼無法解密或為空")
                return 3

            _print_source(system_org, source)

            has_missing_org = False
            results = []
            set_default = not args.no_default

            for code in org_codes:
                target_org = Organization.query.filter_by(
                    code=code,
                    is_deleted=False,
                ).first()
                if not target_org:
                    results.append((code, '找不到企業', '-'))
                    has_missing_org = True
                    continue

                if target_org.secure_code == system_org.secure_code:
                    results.append((target_org.code, '來源即目標，跳過', target_org.secure_code))
                    continue

                existing = SmtpConfig.query.filter_by(
                    org_secure_code=target_org.secure_code,
                    username=source.username,
                    is_deleted=False,
                ).first()
                if existing:
                    results.append((target_org.code, '已存在，跳過', existing.secure_code))
                    continue

                if args.dry_run:
                    results.append((target_org.code, '將建立', '-'))
                    continue

                if set_default:
                    other_configs = SmtpConfig.query.filter_by(
                        org_secure_code=target_org.secure_code,
                        is_deleted=False,
                    ).all()
                    for other_config in other_configs:
                        other_config.is_default = False

                new_config = _clone_config(source, target_org, source_password, set_default)
                db.session.add(new_config)
                results.append((target_org.code, '已建立', new_config))

            if args.apply:
                db.session.flush()
                db.session.commit()

            for code, action, secure_code in results:
                if isinstance(secure_code, SmtpConfig):
                    secure_code = secure_code.secure_code
                _print_result(code, action, secure_code)

            return 2 if has_missing_org else 0
        except Exception as exc:
            db.session.rollback()
            # 只印第一行：SQLAlchemy 例外的後續行會帶 [parameters: ...]，含 password_encrypted
            first_line = (str(exc).splitlines() or [''])[0]
            print(f"錯誤: {type(exc).__name__}: {first_line}")
            return 4


if __name__ == '__main__':
    sys.exit(main())
