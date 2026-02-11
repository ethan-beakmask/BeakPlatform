#!/bin/bash
# Generate SSH deploy key and configure it for CI/CD
# Run this on 192.168.0.16 (the CI host)
set -e

KEY_FILE="$HOME/.ssh/beakplatform_deploy"
REMOTE_HOST="192.168.0.15"
REMOTE_USER="ethan"
FORGEJO_API="http://192.168.0.16:3000/api/v1"
FORGEJO_TOKEN="be6f8e52f155aa026ac12c5bd470114aa7c54333"
REPO="forgejoadmin/BeakPlatform"

echo "=== SSH Deploy Key Setup ==="

# 1. Generate key pair if not exists
if [ ! -f "$KEY_FILE" ]; then
    echo "Generating SSH key pair..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -C "beakplatform-deploy"
else
    echo "Key already exists: $KEY_FILE"
fi

# 2. Copy public key to remote host
echo ""
echo "Copying public key to $REMOTE_USER@$REMOTE_HOST..."
echo "You will be prompted for the remote password."
ssh-copy-id -i "$KEY_FILE.pub" "$REMOTE_USER@$REMOTE_HOST"

# 3. Test SSH connection
echo "Testing SSH connection..."
ssh -i "$KEY_FILE" -o BatchMode=yes "$REMOTE_USER@$REMOTE_HOST" "echo 'SSH connection OK: $(hostname)'"

# 4. Add private key as Forgejo secret
echo ""
echo "Adding deploy key to Forgejo secrets..."
PRIVATE_KEY=$(cat "$KEY_FILE")
curl -s -X PUT \
    "$FORGEJO_API/repos/$REPO/actions/secrets/DEPLOY_SSH_KEY" \
    -H "Authorization: token $FORGEJO_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg key "$PRIVATE_KEY" '{data: $key}')" \
    && echo "Secret DEPLOY_SSH_KEY saved to Forgejo." \
    || echo "ERROR: Failed to save secret."

echo ""
echo "=== Setup Complete ==="
echo "The CI/CD pipeline can now SSH to $REMOTE_HOST for deployment."
