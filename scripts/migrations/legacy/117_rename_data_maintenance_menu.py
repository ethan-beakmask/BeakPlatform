#!/usr/bin/env python3
"""
117: 選單「資料維護」更名為「主機資料清理」（PF-170）

企業硬刪除已搬到 /organizations/ 企業與合約管理頁，
/hostconfig/data-maintenance 只剩「沒有歸屬的殘留」清理，
原名稱在改造後名不符實。

沿用既有 menu_items.secure_code 原地改標題，
不動 code / link_target，所以 menu_permissions 與
menu_role_requirements 都不必重建。

冪等；出廠預設同步改在 backend/app/defaults/menu_defaults.py。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

from app import create_app, db  # noqa: E402

OLD_TITLE = '資料維護'
NEW_TITLE = '主機資料清理'
NEW_TITLE_I18N = '{"en": "Host Data Cleanup"}'


def main():
    dry_run = '--dry-run' in sys.argv
    app = create_app()
    with app.app_context():
        row = db.session.execute(db.text(
            "SELECT secure_code, title FROM menu_items WHERE code = 'data_maintenance'"
        )).fetchone()

        if not row:
            print('找不到 code=data_maintenance 的選單項目，略過')
            return

        print(f'現況: secure_code={row[0]} title={row[1]}')

        if row[1] == NEW_TITLE:
            print('已是新名稱，無需變更')
            return

        if dry_run:
            print(f'[dry-run] 將把 title 改為「{NEW_TITLE}」')
            return

        db.session.execute(db.text(
            "UPDATE menu_items SET title = :t, title_i18n = CAST(:i AS jsonb), "
            "updated_at = (now() AT TIME ZONE 'UTC') WHERE code = 'data_maintenance'"
        ), {'t': NEW_TITLE, 'i': NEW_TITLE_I18N})

        db.session.execute(db.text(
            "INSERT INTO schema_migrations (filename) VALUES (:f) ON CONFLICT DO NOTHING"
        ), {'f': os.path.basename(__file__)})

        db.session.commit()
        print(f'已更名為「{NEW_TITLE}」')


if __name__ == '__main__':
    main()
