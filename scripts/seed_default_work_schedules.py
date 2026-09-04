#!/usr/bin/env python3
"""補種企業預設班表。"""
import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


USAGE = """用法:
  scripts/seed_default_work_schedules.py --dry-run
  scripts/seed_default_work_schedules.py --apply
  scripts/seed_default_work_schedules.py --dry-run --include-system
  scripts/seed_default_work_schedules.py --apply --include-system

說明:
  補上尚未有預設班表的企業。已存在企業預設班表時一律不修改。
  系統企業預設略過；加 --include-system 時會列出系統企業的 skipped(system) 狀態。
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
    if not argv or any(arg in ('--help', '-h') for arg in argv):
        _print_usage()
        return None, 0
    mode_args = [arg for arg in argv if arg in ('--dry-run', '--apply')]
    allowed = {'--dry-run', '--apply', '--include-system'}
    if len(mode_args) != 1 or any(arg not in allowed for arg in argv):
        _print_usage()
        return None, 1
    return (mode_args[0], '--include-system' in argv), 0


def main():
    parsed, exit_code = _parse_args(sys.argv[1:])
    if parsed is None:
        return exit_code
    mode, include_system = parsed

    _load_dotenv()
    from app import create_app, db
    from app.models import Organization, WorkSchedule
    from app.services.schedule_service import ScheduleService

    app = create_app()
    with app.app_context():
        orgs = Organization.query.filter(
            Organization.is_deleted == False  # noqa: E712
        ).order_by(Organization.code.asc()).all()

        created_count = 0
        exists_count = 0
        skipped_count = 0

        for org in orgs:
            if org.is_system_org:
                skipped_count += 1
                if include_system:
                    print(f"{org.code}: skipped(system)")
                continue

            existing = WorkSchedule.query.filter_by(
                org_secure_code=org.secure_code,
                is_default=True,
                is_deleted=False,
            ).first()
            if existing:
                exists_count += 1
                print(f"{org.code}: exists ({existing.schedule_code})")
                continue

            created_count += 1
            if mode == '--dry-run':
                print(f"{org.code}: created")
            else:
                schedule = ScheduleService.ensure_default_schedule(org)
                print(f"{org.code}: created ({schedule.schedule_code})")

        if mode == '--apply':
            db.session.commit()
            print("已寫入資料庫")
        else:
            db.session.rollback()
            print("dry-run，未寫入資料庫")

        print(
            f"統計: created={created_count}, exists={exists_count}, "
            f"skipped(system)={skipped_count}"
        )

    return 0


if __name__ == '__main__':
    sys.exit(main())
