#!/usr/bin/env python3
"""
BeakPlatform 系統企業出廠資料補齊腳本
"""
import argparse
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            '補齊系統企業出廠資料。ORG_ADMIN 初始密碼只從 '
            'ADMIN_INITIAL_PASSWORD 環境變數讀取，不接受命令列密碼參數。'
        )
    )
    return parser.parse_args()


def main():
    parse_args()

    from app import create_app, db
    from app.defaults.system_org_defaults import seed_system_org_defaults

    app = create_app()
    with app.app_context():
        admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
        try:
            summary = seed_system_org_defaults(
                admin_password=admin_password or None)
            db.session.commit()
        except ValueError as exc:
            db.session.rollback()
            print(f'錯誤: {exc}', file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            db.session.rollback()
            app.logger.exception('系統企業出廠資料種入失敗')
            print(f'錯誤: 系統企業出廠資料種入失敗: {exc}', file=sys.stderr)
            sys.exit(1)

        print('系統企業出廠資料種入完成')
        for key, value in summary.items():
            print(f'{key}: {value}')


if __name__ == '__main__':
    main()
