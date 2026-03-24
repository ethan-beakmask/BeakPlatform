# BeakPlatform

Multi-tenant RBAC platform with dynamic menu system, organization isolation, and module architecture.

## Prerequisites

- Docker Engine 24+
- Docker Compose v2+

## Installation

```bash
# Clone the repository
git clone https://github.com/beakplatform/BeakPlatform.git
cd BeakPlatform/deploy

# Create environment configuration
cp .env.example .env.production

# Edit .env.production:
#   - Set DB_PASSWORD (database password)
#   - Set SECRET_KEY (run: python3 -c "import secrets; print(secrets.token_hex(32))")
#   - Optionally set ADMIN_INITIAL_PASSWORD (if not set, a random one will be generated)

# Start all services
docker compose --env-file .env.production up -d
```

## First Login

Check the app container logs for admin credentials:

```bash
docker compose --env-file .env.production logs app | grep -A 5 "INITIAL ADMIN"
```

If `ADMIN_INITIAL_PASSWORD` was set in `.env.production`, use that password.
Otherwise, the auto-generated password is printed once during first startup.

- **URL**: `http://localhost:8000`
- **Username**: `admin`
- **Password**: (see logs above)

You will be prompted to change the password on first login.

## Services

| Service | Container | Port |
|---------|-----------|------|
| App (Gunicorn) | beakmask-app | 5000 (internal) |
| PostgreSQL 16 | beakmask-db | 5432 (internal) |
| Redis 7 | beakmask-redis | 6379 (internal) |
| Nginx | beakmask-nginx | 8000 |

## Stopping / Restarting

```bash
cd deploy

# Stop
docker compose --env-file .env.production down

# Restart
docker compose --env-file .env.production up -d

# View logs
docker compose --env-file .env.production logs -f app
```

## Data Persistence

Database data is stored in Docker volume `deploy_pgdata`. Removing this volume will delete all data.

## License

All rights reserved.
