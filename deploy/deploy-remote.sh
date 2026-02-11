#!/bin/bash
# Remote deployment script - runs on 192.168.0.15
# Called by Forgejo Actions CD pipeline via SSH
set -e

DEPLOY_DIR="/opt/BeakPlatform"
REPO_URL="http://192.168.0.16:3000/forgejoadmin/BeakPlatform.git"

echo "=== BeakPlatform CD Deploy ==="
echo "Host: $(hostname)"
echo "Time: $(date)"

# Clone or pull
if [ -d "$DEPLOY_DIR/.git" ]; then
    echo "Pulling latest code..."
    cd "$DEPLOY_DIR"
    git fetch origin main
    git reset --hard origin/main
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$DEPLOY_DIR"
    cd "$DEPLOY_DIR"
fi

# Generate SECRET_KEY if not exists
ENV_FILE="$DEPLOY_DIR/deploy/.env.production"
if grep -q "CHANGE-THIS" "$ENV_FILE"; then
    echo "Generating production SECRET_KEY..."
    NEW_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE-THIS-TO-A-RANDOM-STRING-IN-PRODUCTION/$NEW_KEY/" "$ENV_FILE"
fi

# Build and deploy
echo "Building and deploying with Docker Compose..."
cd "$DEPLOY_DIR/deploy"
docker compose build --no-cache
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d

# Wait for health check
echo "Waiting for application to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "Application is healthy!"
        docker compose ps
        echo ""
        echo "=== Deploy Complete ==="
        echo "URL: http://$(hostname -I | awk '{print $1}'):8000"
        exit 0
    fi
    echo "  Waiting... ($i/30)"
    sleep 3
done

echo "ERROR: Application failed health check after 90s"
docker compose logs --tail=50 app
exit 1
