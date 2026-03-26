#!/bin/bash
set -e

echo "=== BeakPlatform Docker Entrypoint ==="

# Wait for database
echo "Waiting for database..."
python3 -c "
import time, os, psycopg2
dsn = os.environ['DATABASE_URL']
for i in range(30):
    try:
        conn = psycopg2.connect(dsn)
        conn.close()
        print('Database ready.')
        break
    except Exception:
        print(f'Waiting... ({i+1}/30)')
        time.sleep(2)
else:
    print('ERROR: Database not available after 60s')
    exit(1)
"

# Initialize database tables if needed
echo "Checking database tables..."
FRESH_INSTALL="no"
python3 << 'PYEOF'
import os
from app import create_app, db
app = create_app()
with app.app_context():
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if not tables or 'organizations' not in tables:
        print("Creating database tables...")
        db.create_all()

        # Admin password: use env var if set, otherwise generate random
        import sys, bcrypt, secrets, string
        admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
        generated = False
        if not admin_password:
            alphabet = string.ascii_letters + string.digits
            admin_password = (
                secrets.choice(string.ascii_uppercase)
                + secrets.choice(string.ascii_lowercase)
                + secrets.choice(string.digits)
                + ''.join(secrets.choice(alphabet) for _ in range(13))
            )
            generated = True
        elif len(admin_password) < 8:
            print("ERROR: ADMIN_INITIAL_PASSWORD must be at least 8 characters.")
            sys.exit(1)

        # Create initial admin
        from app.models import Organization, User, UserType
        system_org = Organization(
            secure_code='system.local',
            code='SYSTEM',
            name='system.local',
            domain_name='system.local',
            is_active=True
        )
        db.session.add(system_org)
        db.session.flush()

        password = admin_password.encode('utf-8')
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password, salt).decode('utf-8')
        admin = User(
            org_secure_code='system.local',
            username='admin',
            email='admin@system.local',
            display_name='System Admin',
            password_hash=password_hash,
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Database initialized with admin account. (must_change_password=True)")

        if generated:
            print("")
            print("============================================")
            print("  INITIAL ADMIN CREDENTIALS")
            print("  Username: admin")
            print(f"  Password: {admin_password}")
            print("")
            print("  ** Save this password now --")
            print("     it will NOT be shown again **")
            print("============================================")
            print("")

        # Signal fresh install
        with open('/tmp/.fresh_install', 'w') as f:
            f.write('1')
    else:
        print(f"Database has {len(tables)} tables, skipping init.")
PYEOF

# Migration tracking
echo "Checking migrations..."
cd /opt/BeakPlatform
if [ -f /tmp/.fresh_install ]; then
    # 全新安裝：db.create_all() 已建立最新 schema，標記所有 migrations 為已執行
    echo "Fresh install detected, marking all migrations as applied..."
    python3 scripts/run_migrations.py --mark-all
    rm -f /tmp/.fresh_install
else
    # 既有環境：執行待處理的 migrations
    python3 scripts/run_migrations.py --run
fi
cd /opt/BeakPlatform/backend

# Initialize platform menus (runs before module sync to avoid menu count conflict)
# init_menus.py is idempotent -- skips if platform menus already exist
echo "Initializing platform menus..."
cd /opt/BeakPlatform
python3 scripts/init_menus.py || echo "Menu init skipped"

# Initialize system permissions and ABAC conditions
# init_permissions.py is idempotent -- skips if permissions already exist
echo "Initializing system permissions..."
python3 scripts/init_permissions.py || echo "Permission init skipped"
cd /opt/BeakPlatform/backend

# Sync modules (registers module menus, permissions, etc.)
echo "Syncing modules..."
FLASK_ENV=${FLASK_ENV:-production} flask module sync 2>/dev/null || echo "Module sync skipped"

echo "Starting Gunicorn..."
exec gunicorn -c gunicorn.conf.py wsgi:application
