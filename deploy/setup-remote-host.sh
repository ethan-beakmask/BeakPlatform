#!/bin/bash
# First-time setup script for the deployment host (192.168.0.15)
# Run this ONCE from 192.168.0.16 via SSH
set -e

echo "=== BeakPlatform Remote Host Setup ==="

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to logout/login for group changes."
else
    echo "Docker already installed: $(docker --version)"
fi

# 2. Install git if not present
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    sudo apt-get install -y git
fi

# 3. Clone repository
DEPLOY_DIR="/opt/BeakPlatform"
if [ ! -d "$DEPLOY_DIR" ]; then
    echo "Cloning repository..."
    sudo mkdir -p /opt
    sudo chown $USER:$USER /opt
    git clone http://192.168.0.16:3000/forgejoadmin/BeakPlatform.git "$DEPLOY_DIR"
else
    echo "Repository already exists at $DEPLOY_DIR"
    cd "$DEPLOY_DIR"
    git pull origin main
fi

# 4. Generate production SECRET_KEY
ENV_FILE="$DEPLOY_DIR/deploy/.env.production"
if grep -q "CHANGE-THIS" "$ENV_FILE"; then
    echo "Generating production SECRET_KEY..."
    NEW_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/CHANGE-THIS-TO-A-RANDOM-STRING-IN-PRODUCTION/$NEW_KEY/" "$ENV_FILE"
    echo "SECRET_KEY generated."
fi

# 5. Initial build and start
echo "Building Docker images..."
cd "$DEPLOY_DIR/deploy"
docker compose build

echo "Starting services..."
docker compose up -d

# 6. Wait for health
echo "Waiting for application..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo ""
        echo "=== Setup Complete ==="
        docker compose ps
        echo ""
        echo "Application running at http://$(hostname -I | awk '{print $1}'):8000"
        echo "Default login: admin@system.local (password set via ADMIN_INITIAL_PASSWORD, must change on first login)"
        exit 0
    fi
    echo -n "."
    sleep 3
done

echo ""
echo "WARNING: Health check not passing yet. Check logs:"
echo "  cd $DEPLOY_DIR/deploy && docker compose logs"
