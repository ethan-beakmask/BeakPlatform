# CI/CD 環境建置記錄

建置日期：2026-02-12

## 架構總覽

```
                    ┌─────────────────────────────┐
                    │   Forgejo (192.168.0.16:3000)│
                    │   git push to main           │
                    └──────────┬──────────────────┘
                               │ trigger
                    ┌──────────▼──────────────────┐
                    │   CI: Forgejo Actions        │
                    │   192.168.0.16 (act_runner)  │
                    │   ┌──────────┐ ┌──────────┐ │
                    │   │ Security │ │  Tests   │ │
                    │   │  Scan    │ │ (pytest) │ │
                    │   └────┬─────┘ └────┬─────┘ │
                    │        └──────┬─────┘        │
                    └───────────────┼──────────────┘
                                    │ both pass
                    ┌───────────────▼──────────────┐
                    │   CD: SSH Deploy             │
                    │   192.168.0.15:8000           │
                    │   ┌────────┐ ┌─────┐ ┌─────┐│
                    │   │  App   │ │ DB  │ │Redis││
                    │   │Gunicorn│ │PG16 │ │  7  ││
                    │   └───┬────┘ └─────┘ └─────┘│
                    │   ┌───▼────┐                 │
                    │   │ Nginx  │ → :8000         │
                    │   └────────┘                 │
                    └──────────────────────────────┘
```

---

## CI 主機：192.168.0.16 (RD-coding)

### 變更清單

| 項目 | 說明 |
|------|------|
| Forgejo Actions Runner | `forgejo-runner.service` (systemd, enabled) |
| Runner binary | `/usr/local/bin/act_runner` v6.3.1 |
| Runner config | `/opt/forgejo-runner/config.yaml` |
| Runner labels | `ubuntu-latest`, `ubuntu-22.04` (Docker 模式) |
| CI Workflow | `.forgejo/workflows/security-check.yml` |
| Docker | 28.2.2 (apt 安裝) |
| Docker Compose | v2.35.1 (`/usr/local/bin/docker-compose` + plugin symlink) |
| SSH Deploy Key | `~/.ssh/beakplatform_deploy` (ed25519) |
| Forgejo Secret | `DEPLOY_SSH_KEY` (deploy key private key) |
| Semgrep | 1.145.2 (`~/.local/bin/semgrep`) |

### CI Pipeline (`.forgejo/workflows/security-check.yml`)

觸發條件：push 或 PR 到 `main` 分支

| Job | 內容 | 阻斷？ |
|-----|------|--------|
| Security Scan | Semgrep 自訂規則 (ERROR 級) | 是 |
| Security Scan | Semgrep Flask 規則 | 否 |
| Security Scan | Bandit 靜態分析 | 否 |
| Tests | pytest (PostgreSQL 16 容器) | 是 |
| Deploy | SSH 到 0.15 執行部署腳本 | CI 通過後 |

### CD Deploy 方式

Deploy job 使用直接 SSH 命令（非第三方 action）：

```yaml
- name: Deploy via SSH
  run: |
    mkdir -p ~/.ssh
    echo "${{ secrets.DEPLOY_SSH_KEY }}" > ~/.ssh/deploy_key
    chmod 600 ~/.ssh/deploy_key
    ssh -o StrictHostKeyChecking=no -i ~/.ssh/deploy_key ethan@192.168.0.15 /opt/BeakPlatform/deploy/deploy-remote.sh
    rm -f ~/.ssh/deploy_key
```

> **注意**：不使用 `appleboy/ssh-action`，因為 Forgejo 的 action mirror (`data.forgejo.org`) 沒有收錄此 action。

### Semgrep 自訂規則 (`.semgrep/beakplatform-security.yaml`)

9 條規則，4 條 ERROR 級（會阻斷 pipeline）：

| 規則 | 嚴重度 | 說明 |
|------|--------|------|
| missing-auth-decorator | ERROR | Route 缺少認證 decorator |
| sql-injection | ERROR | SQL 字串拼接 (CWE-89) |
| command-injection | ERROR | shell=True / os.system (CWE-78) |
| hardcoded-secret | ERROR | 硬編碼密鑰 (CWE-798) |
| direct-model-query-in-api | WARNING | API 層直接查 Model |
| insecure-random | WARNING | 使用 random 而非 secrets |
| debug-enabled | WARNING | Debug 模式 |
| insecure-pickle | WARNING | pickle 反序列化 |
| log-sensitive-data | WARNING | Log 記錄敏感資料 |

### 新增/修改的檔案

```
.dockerignore                              # Docker build 排除規則
.forgejo/workflows/security-check.yml      # CI/CD pipeline (直接 SSH deploy)
backend/app/config.py                      # SESSION_REDIS 修正
deploy/Dockerfile                          # App image 定義
deploy/docker-compose.yml                  # 4 容器 stack
deploy/.env.production                     # 生產環境變數
deploy/docker-entrypoint.sh                # DB init + menu init + module sync + Gunicorn
deploy/init-db.sh                          # PostgreSQL 額外 DB
deploy/nginx/default.conf                  # Nginx reverse proxy
deploy/deploy-remote.sh                    # CD 自動拉取+部署腳本
deploy/setup-remote-host.sh                # 首次設定遠端主機
deploy/setup-ssh-deploy-key.sh             # SSH key 配置腳本
CHANGELOG.md                               # Keep a Changelog 格式
```

---

## CD 主機：192.168.0.15 (guest01)

### 主機資訊

| 項目 | 值 |
|------|-----|
| OS | Ubuntu 24.04 (kernel 6.8.0-90-generic) |
| CPU/RAM | 2 vCPU / 5.8 GB |
| Disk | 98 GB (15% used) |
| SSH User | ethan (SSH key 認證，key 在 0.16 `~/.ssh/beakplatform_deploy`) |

### 安裝的軟體

| 軟體 | 版本 | 安裝方式 |
|------|------|----------|
| Docker CE | 29.2.1 | Docker 官方 apt repo |
| Docker Compose | 5.0.2 (plugin) | 隨 Docker CE 安裝 |
| Git | 2.43.0 | 系統內建 |
| Python | 3.12.3 | 系統內建 |

### Docker Stack

服務 URL：**http://192.168.0.15:8000**

| 容器 | Image | 用途 | 健康檢查 |
|------|-------|------|----------|
| beakmask-app | deploy-app (自建) | Flask + Gunicorn | `curl /health` |
| beakmask-db | postgres:16-alpine | 主資料庫 | `pg_isready` |
| beakmask-redis | redis:7-alpine | Session + Rate Limiting | `redis-cli ping` |
| beakmask-nginx | nginx:alpine | Reverse Proxy → :8000 | — |

### Docker Volumes

| Volume | 用途 |
|--------|------|
| `deploy_pgdata` | PostgreSQL 資料持久化 |
| `deploy_app-sessions` | Flask session 檔案 |

### App 容器啟動流程 (`docker-entrypoint.sh`)

1. 等待 PostgreSQL 就緒（最多 60 秒）
2. 檢查 `organizations` 表是否存在
   - 不存在 → `db.create_all()` + 建立系統企業 (SYSTEM_ORG_CODE) + admin 帳號
   - 存在 → 跳過
3. 執行 `scripts/init_menus.py`（平台選單初始化，冪等操作）
4. 執行 `flask module sync`（模組選單/權限同步）
5. 啟動 Gunicorn

> **注意**：`init_menus.py` 必須在 `flask module sync` 之前執行，否則模組選單會先佔位，導致 init_menus 誤判「已有選單」而跳過平台級選單。

### 部署流程

CD 觸發後執行 `deploy/deploy-remote.sh`：

1. `git fetch origin main && git reset --hard origin/main`
2. `docker compose build --no-cache`
3. `docker compose down && docker compose up -d`
4. 輪詢 `/health` 等待 app 啟動（最多 90 秒）

### 管理員帳號

| 帳號 | 密碼 | 說明 |
|------|------|------|
| admin@BeakPlatform_Identifier_Code | 由 `ADMIN_INITIAL_PASSWORD` 環境變數設定 | 系統管理員（首次登入強制改密碼） |

---

## 已知問題與修復記錄

| 問題 | 原因 | 修復 |
|------|------|------|
| Deploy job 失敗 (6s) | `appleboy/ssh-action@v1` 不在 `data.forgejo.org` mirror | 改用 `run:` 直接 SSH 命令 |
| App 重啟循環 (IntegrityError) | entrypoint 檢查 `'user'` 表名，實際為 `'users'` | 改為檢查 `'organizations'` 表 |
| 系統管理選單缺失 | entrypoint 未執行 `init_menus.py` | 加入 init_menus.py 步驟，排在 module sync 之前 |

---

## 維運指令

### 0.15 上手動操作

```bash
# 查看容器狀態
cd /opt/BeakPlatform/deploy && docker compose ps

# 查看 app log
docker compose logs app --tail=50

# 重新部署（拉最新程式碼）
cd /opt/BeakPlatform && git pull origin main
cd deploy && docker compose build app && docker compose up -d

# 完全重建（含清除資料）
docker compose down -v && docker compose up -d --build
```

### 0.16 上遠端操作

```bash
# SSH 到 0.15
ssh -i ~/.ssh/beakplatform_deploy ethan@192.168.0.15

# 直接觸發遠端部署
ssh -i ~/.ssh/beakplatform_deploy ethan@192.168.0.15 /opt/BeakPlatform/deploy/deploy-remote.sh
```

---

*最後更新: 2026-02-12*
