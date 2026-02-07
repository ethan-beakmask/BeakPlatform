# Flask 安全檢查清單

## 認證相關

### CSRF 豁免
登入端點不需要 CSRF 保護（沒有已登入 session 可被攻擊），但需要:
- Rate limiting 防暴力破解
- 安全的錯誤訊息（不洩漏帳號是否存在）

```python
@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def login():
    ...
```

### 安全登出
```python
def logout():
    user_email = current_user.email
    logout_user()           # 1. Flask-Login 登出
    session.clear()         # 2. 清除所有 session 資料
    session.modified = True # 3. 強制 session 變更
    return redirect(url_for('auth.login'))
```

### 密碼處理
```python
import bcrypt

# 建立 hash
password = b'user_password'
hashed = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))

# 驗證
bcrypt.checkpw(password, stored_hash)
```

---

## Blueprint 命名

### 問題
API 和 Web routes 不能用相同的 blueprint 名稱。

### 規範
```python
# API blueprints: 前綴 api_
Blueprint('api_users', __name__)
Blueprint('api_organizations', __name__)

# Web blueprints: 無前綴或 web_ 前綴
Blueprint('users', __name__)
Blueprint('organizations', __name__)
```

---

## Session 設定

### 開發環境
```python
class DevelopmentConfig:
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/beakplatform_sessions'
    SESSION_COOKIE_SECURE = False  # 開發環境不強制 HTTPS
```

### 生產環境
```python
class ProductionConfig:
    SESSION_TYPE = 'redis'
    SESSION_REDIS = redis.from_url(os.getenv('REDIS_URL'))
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
```

---

## 資料庫權限

### PostgreSQL 權限設定
```sql
-- 授予權限
GRANT ALL PRIVILEGES ON DATABASE dbname TO username;
GRANT ALL PRIVILEGES ON SCHEMA public TO username;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO username;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO username;

-- 設定預設權限（給未來建立的表）
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO username;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO username;
```

### RLS 開發階段
```sql
-- 開發階段可暫時停用 RLS
ALTER TABLE users DISABLE ROW LEVEL SECURITY;

-- 生產環境重新啟用
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
```

---

## 錯誤處理

### 統一錯誤回應
```python
def error_response(message, status_code):
    if request.is_json:
        return jsonify({'error': message}), status_code
    else:
        return render_template(f'errors/{status_code}.html'), status_code
```

### 不洩漏敏感資訊
```python
# 錯誤: 洩漏帳號是否存在
if not user:
    return error_response('User not found', 404)

# 正確: 統一錯誤訊息
if not user or not user.check_password(password):
    return error_response('帳號或密碼錯誤', 401)
```
