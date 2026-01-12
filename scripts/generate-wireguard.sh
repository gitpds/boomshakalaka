#!/bin/bash
# Generate WireGuard configuration files from environment variables
# Usage: ./generate-wireguard.sh
#
# This script reads from .env and generates:
# - setup/wireguard-client.conf (for remote devices)
# - setup/wireguard-qr.txt (QR code for mobile)
# - /etc/wireguard/wg0.conf (server config, requires sudo)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
else
    echo "Error: .env file not found at $PROJECT_ROOT/.env"
    echo "Copy .env.example to .env and fill in your values"
    exit 1
fi

# Check required variables
required_vars=(
    "WG_SERVER_PRIVATE_KEY"
    "WG_SERVER_PUBLIC_KEY"
    "WG_SERVER_ADDRESS"
    "WG_SERVER_PORT"
    "WG_SERVER_PUBLIC_IP"
    "WG_CLIENT_PRIVATE_KEY"
    "WG_CLIENT_PUBLIC_KEY"
    "WG_CLIENT_ADDRESS"
)

missing=0
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "Error: $var is not set in .env"
        missing=1
    fi
done

if [ $missing -eq 1 ]; then
    echo ""
    echo "To generate new WireGuard keys:"
    echo "  wg genkey | tee privatekey | wg pubkey > publickey"
    exit 1
fi

echo "Generating WireGuard configurations..."

# Generate client config
cat > "$PROJECT_ROOT/setup/wireguard-client.conf" << EOF
[Interface]
Address = ${WG_CLIENT_ADDRESS}
PrivateKey = ${WG_CLIENT_PRIVATE_KEY}
DNS = 1.1.1.1

[Peer]
PublicKey = ${WG_SERVER_PUBLIC_KEY}
Endpoint = ${WG_SERVER_PUBLIC_IP}:${WG_SERVER_PORT}
AllowedIPs = 10.200.200.0/24
PersistentKeepalive = 25
EOF

chmod 600 "$PROJECT_ROOT/setup/wireguard-client.conf"
echo "Created: setup/wireguard-client.conf"

# Generate QR code for mobile (if qrencode is installed)
if command -v qrencode &> /dev/null; then
    qrencode -t ansiutf8 < "$PROJECT_ROOT/setup/wireguard-client.conf" > "$PROJECT_ROOT/setup/wireguard-qr.txt"
    echo "Created: setup/wireguard-qr.txt"

    qrencode -t png -o "$PROJECT_ROOT/setup/wireguard-qr.png" < "$PROJECT_ROOT/setup/wireguard-client.conf"
    echo "Created: setup/wireguard-qr.png"
else
    echo "Note: Install qrencode to generate QR codes: sudo apt install qrencode"
fi

# Generate server config (requires sudo to install)
SERVER_CONFIG=$(cat << EOF
[Interface]
Address = ${WG_SERVER_ADDRESS}
ListenPort = ${WG_SERVER_PORT}
PrivateKey = ${WG_SERVER_PRIVATE_KEY}

[Peer]
PublicKey = ${WG_CLIENT_PUBLIC_KEY}
AllowedIPs = ${WG_CLIENT_ADDRESS%/*}/32
EOF
)

echo ""
echo "Server configuration (for /etc/wireguard/wg0.conf):"
echo "=================================================="
echo "$SERVER_CONFIG"
echo "=================================================="
echo ""
echo "To install server config:"
echo "  echo '\$SERVER_CONFIG' | sudo tee /etc/wireguard/wg0.conf"
echo "  sudo chmod 600 /etc/wireguard/wg0.conf"
echo "  sudo systemctl enable --now wg-quick@wg0"
echo ""
echo "Done! Client config ready at: setup/wireguard-client.conf"
