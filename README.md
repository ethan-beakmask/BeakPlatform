# BeakPlatform

Multi-tenant RBAC platform with dynamic menu system, organization isolation, and module architecture.

## Module Status

| Module | Status |
|---|---|
| form_workflow | Stable |
| open_defense | Stable |
| spec_formulate | Stable |
| nocode_builder | Experimental, incomplete, may be removed. Do not use in production. |

## Requirements

- Ubuntu 22.04 / 24.04 LTS
- Root access (sudo)

The install script automatically installs all dependencies: PostgreSQL, Redis, Nginx, Python 3.

Optional: the workflow designer's *AI analysis* node calls a locally installed
Claude Code CLI. It is not required for any other feature. See
`docs/install/ai_node.md` for its prerequisites (CLI path, credentials, proxy/CA).

## Quick Install

```bash
curl -sL -H "Authorization: token YOUR_GITHUB_TOKEN" \
  https://raw.githubusercontent.com/beakplatform/BeakPlatform/main/scripts/install.sh \
  | sudo GITHUB_TOKEN=YOUR_GITHUB_TOKEN ADMIN_INITIAL_PASSWORD='yourpassword' bash
```

Replace:
- `YOUR_GITHUB_TOKEN` -- GitHub Personal Access Token with `repo` scope
- `yourpassword` -- Admin initial password (min 8 characters, will be prompted to change on first login)

The script performs a fully automated installation:
1. Installs system dependencies (PostgreSQL, Redis, Nginx, Python)
2. Creates database and application user
3. Clones the repository to `/opt/BeakPlatform`
4. Sets up Python virtual environment
5. Initializes database schema, menus, and permissions
6. Configures systemd service and Nginx reverse proxy

## First Login

- **URL**: `http://YOUR_SERVER_IP`
- **Username**: `admin`
- **Password**: (the password you set during installation)

You will be prompted to change the password on first login.

## Services

| Service | Description | Port |
|---------|-------------|------|
| Nginx | Reverse proxy | 80 |
| Gunicorn | Application server | 8000 (internal) |
| PostgreSQL | Database | 5432 (internal) |
| Redis | Session / cache | 6379 (internal) |

## Management

```bash
# Check service status
sudo bash /opt/BeakPlatform/scripts/install.sh --status

# Start / Stop
sudo bash /opt/BeakPlatform/scripts/install.sh --start
sudo bash /opt/BeakPlatform/scripts/install.sh --stop

# View logs
journalctl -u beakplatform -f
```

## Updating

```bash
sudo bash /opt/BeakPlatform/scripts/install.sh --update
```

This pulls the latest code, updates dependencies, runs pending database migrations, syncs menus and permissions, and restarts the service. All data is preserved.

## Uninstall

```bash
sudo bash /opt/BeakPlatform/scripts/install.sh --uninstall
```

## License

All rights reserved.
