#!/bin/bash
# ============================================================
# Open Defense — one-shot bootstrap on a fresh sec-vm
# ============================================================
# - Verifies .env (creates from .env.example if missing)
# - Sets host nftables blocklist sets
# - Pre-chowns WAF audit log dir
# - Pulls images and brings the stack up
# - Registers od-bridge as a CrowdSec machine on first run
# ============================================================
set -euo pipefail

DEST="${SECSTACK_DEST:-/home/ethan/sec-vm-bootstrap}"
HERE="$(cd "$(dirname "$0")" && pwd)"

err()  { printf '\033[31m[!]\033[0m %s\n' "$*" >&2; }
log()  { printf '\033[32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[~]\033[0m %s\n' "$*"; }

# ---------------- preflight ----------------

[[ $EUID -eq 0 ]] || { err "run with sudo"; exit 1; }
command -v docker  >/dev/null || { err "docker not found";        exit 1; }
docker compose version >/dev/null || { err "docker compose plugin required"; exit 1; }
command -v nft     >/dev/null || { err "nft (nftables) not found"; exit 1; }

if [[ ! -f "$HERE/.env" ]]; then
    if [[ -f "$HERE/.env.example" ]]; then
        cp "$HERE/.env.example" "$HERE/.env"
        warn ".env was missing — copied from .env.example.  Fill in secrets and re-run."
        exit 1
    else
        err ".env not found and no .env.example to copy from"
        exit 1
    fi
fi

# Require these to be non-empty
require_var() {
    local k="$1"
    if ! grep -qE "^${k}=.+" "$HERE/.env" 2>/dev/null; then
        err ".env missing required key: ${k}"
        exit 1
    fi
}
require_var INTAKE_KEY_ID
require_var INTAKE_SECRET_B64
require_var CLOUDFLARE_TUNNEL_TOKEN
require_var CLICKHOUSE_PASSWORD

# ---------------- copy to DEST if running from elsewhere ----------------

if [[ "$HERE" != "$DEST" ]]; then
    log "syncing $HERE → $DEST"
    mkdir -p "$DEST"
    rsync -a --exclude='.git' --exclude='.venv' "$HERE/" "$DEST/"
fi
cd "$DEST"

# ---------------- host firewall: nftables sets ----------------

if nft list table inet secstack >/dev/null 2>&1; then
    log "nft inet/secstack already exists"
else
    log "creating nft inet/secstack table + blocklist sets"
    bash "$DEST/nftables-bootstrap.sh"
fi

# ---------------- WAF audit log dir ----------------

mkdir -p "$DEST/waf/log"
chown -R 101:101 "$DEST/waf/log"

# ---------------- bridge state dir ----------------

mkdir -p "$DEST/od-bridge/state"

# ---------------- pull + up ----------------

log "docker compose pull"
docker compose pull --quiet || true   # OK if some images aren't yet pullable cleanly

log "docker compose up -d"
docker compose up -d

# ---------------- ClickHouse schema (idempotent) ----------------

log "waiting for ClickHouse healthy"
for i in $(seq 1 30); do
    if curl -fs -u "secstack:$(grep ^CLICKHOUSE_PASSWORD .env | cut -d= -f2)" \
            "http://127.0.0.1:8123/ping" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

log "applying ClickHouse schema"
docker compose cp clickhouse/init.sql clickhouse:/tmp/init.sql >/dev/null
docker compose exec -T clickhouse clickhouse-client \
    --user secstack --password "$(grep ^CLICKHOUSE_PASSWORD .env | cut -d= -f2)" \
    --multiquery --queries-file /tmp/init.sql 2>&1 | grep -v '^$' || true

# ---------------- CrowdSec machine for bridge ----------------

if [[ ! -s "$DEST/od-bridge/state/crowdsec_machine.json" ]]; then
    log "registering od-bridge as a CrowdSec machine"
    sleep 5  # let crowdsec finish init
    PASSWORD=$(openssl rand -hex 24)
    docker compose exec -T crowdsec cscli machines add od-bridge \
        --password "$PASSWORD" --force >/dev/null
    cat > "$DEST/od-bridge/state/crowdsec_machine.json" <<EOF
{"machine_id": "od-bridge", "password": "$PASSWORD"}
EOF
    chmod 600 "$DEST/od-bridge/state/crowdsec_machine.json"
    docker compose restart od-bridge
else
    log "CrowdSec bridge machine already registered"
fi

# ---------------- summary ----------------

echo
log "==== STATUS ===="
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
echo
log "==== HEALTH ===="
printf '  ClickHouse  /ping   : %s\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8123/ping)"
printf '  od-bridge   /health : %s\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8500/health)"
printf '  WAF         /       : %s\n' \
    "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/)"
echo
log "==== NEXT STEPS ===="
cat <<EOF
1. Cloudflare Zero Trust UI — set Public Hostname → http://waf-nginx:8080
2. Send a test event:
     curl -X POST http://127.0.0.1:8500/events \\
       -H 'Content-Type: application/json' \\
       -d '{"correlation_id":"...","source_system":"coraza","event_class":"web_activity",
            "occurred_at":"$(date -u +%FT%TZ)","severity_id":3,
            "finding":{"title":"test","rule_id":"X","rule_set":"manual"},
            "actor":{"ip":"1.2.3.4"},
            "target":{"host":"a","url":"/"}}'
3. Logs:    docker compose logs -f od-bridge
4. Suricata rules update:
     docker compose exec suricata suricata-update --no-test
     docker compose restart suricata
EOF
