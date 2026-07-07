#!/usr/bin/env python3
"""
079 - OdIntakeKey 遷移至平台 ApiKey(P2,規格: docs/API_KEY_TRIGGER_SPEC.md)

將 od_intake_keys 中未刪除的金鑰複製到 api_keys:
  - key_id 沿用(ik_ 開頭,新發平台 key 一律 ak_,用戶拍板)
  - secret 密文五欄位直搬(同為 KeyManager Org Key AES-256-GCM,免解密)
  - allowed_source_systems -> scopes = {"od_intake": {"source_systems": [...]}}
  - is_active=True -> status='active';is_active=False -> status='suspended'
  - expires_at / last_used_at / created_by_secure_code 原樣搬

od_intake_keys 表保留唯讀一個版本週期後刪除。
冪等:api_keys 已存在同 key_id 即跳過。
"""
import sys
import os

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(_ROOT, 'backend'))
sys.path.insert(0, _ROOT)  # modules/ 在 repo 根目錄


def main():
    from datetime import datetime
    from app import create_app, db
    from app.models.api_key import (
        ApiKey, STATUS_ACTIVE, STATUS_SUSPENDED,
    )
    from app.utils.security import generate_secure_code
    from modules.open_defense.models import OdIntakeKey

    app = create_app()
    with app.app_context():
        rows = OdIntakeKey.query.filter_by(is_deleted=False).all()
        print(f'od_intake_keys 未刪除記錄: {len(rows)} 筆')

        migrated = skipped = 0
        for r in rows:
            exists = ApiKey.query.filter_by(key_id=r.key_id).first()
            if exists:
                print(f'  跳過(已存在) key_id={r.key_id}')
                skipped += 1
                continue

            record = ApiKey(
                secure_code=generate_secure_code(),
                org_secure_code=r.org_secure_code,
                key_id=r.key_id,
                name=r.name,
                consumer_label=None,
                description='遷移自 OpenDefense intake key(migration 079)',
                secret_ciphertext=r.hmac_secret_ciphertext,
                secret_file_nonce=r.hmac_secret_file_nonce,
                secret_wrapped_dek=r.hmac_secret_wrapped_dek,
                secret_dek_nonce=r.hmac_secret_dek_nonce,
                secret_encryption_key_sc=r.hmac_secret_encryption_key_sc,
                status=STATUS_ACTIVE if r.is_active else STATUS_SUSPENDED,
                suspended_reason=(None if r.is_active
                                  else '遷移前即為停用狀態(migration 079)'),
                suspended_at=None if r.is_active else datetime.utcnow(),
                allowed_ips=None,
                scopes={'od_intake': {
                    'source_systems': r.allowed_source_systems or [],
                }},
                applicant_user_secure_code=None,
                expires_at=r.expires_at,
                last_used_at=r.last_used_at,
                created_by_secure_code=r.created_by_secure_code,
            )
            db.session.add(record)
            print(f'  遷移 key_id={r.key_id} org={r.org_secure_code} '
                  f'status={record.status} sources={r.allowed_source_systems}')
            migrated += 1

        db.session.commit()
        print(f'完成:遷移 {migrated} 筆,跳過 {skipped} 筆')


if __name__ == '__main__':
    main()
