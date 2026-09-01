"""
Migration 068: User 外部身份識別碼

新增 external_identity 欄位，用於儲存外部身份來源的識別碼（如 AD userPrincipalName）。
此欄位為跨 BeakPlatform 站點識別同一自然人的錨點。

組合唯一約束：同一企業內 external_identity 不可重複（允許跨企業相同值）。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app import create_app, db

DDL = """
ALTER TABLE users
ADD COLUMN IF NOT EXISTS external_identity VARCHAR(500);

COMMENT ON COLUMN users.external_identity
IS '外部身份識別碼 (如 AD userPrincipalName)，跨站錨點';

CREATE INDEX IF NOT EXISTS idx_users_external_identity
ON users (external_identity)
WHERE external_identity IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_external_identity_org
ON users (external_identity, org_secure_code)
WHERE external_identity IS NOT NULL AND is_deleted = FALSE;
"""


def run():
    app = create_app()
    with app.app_context():
        db.session.execute(db.text(DDL))
        db.session.commit()
        print("[068] users.external_identity 欄位新增完成")


if __name__ == '__main__':
    run()
