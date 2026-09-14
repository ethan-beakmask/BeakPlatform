#!/usr/bin/env python3
"""
db_create_all.py - 依 ORM model 建立所有資料表（既有表不動）

Schema 權威是 ORM model（PF-168）。本工具給 install.sh 與
check_schema_drift.sh 共用；需在 backend/ 目錄下執行（或自帶 PYTHONPATH），
DATABASE_URL 由環境變數決定。

用法:
    cd backend && SKIP_MODULE_SYNC=1 python3 ../scripts/db_create_all.py
"""
import os
import sys

os.environ.setdefault('SKIP_MODULE_SYNC', '1')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))


def main():
    if len(sys.argv) > 1:
        print(__doc__)
        return
    from app import create_app
    from app.defaults.bootstrap import create_tables
    app = create_app()
    with app.app_context():
        table_count = create_tables()
        print(f"create_all 完成（metadata 內共 {table_count} 張表）")


if __name__ == '__main__':
    main()
