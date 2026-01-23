#!/bin/bash
# Boomshakalaka Secure Remote Access Setup Script
# Run with: sudo bash /home/pds/boomshakalaka/setup/install.sh

set -e

# Handle apt update errors gracefully (some repos may have stale keys)
apt_update_quiet() {
    apt-get update 2>&1 | grep -v -E "GPG error|NO_PUBKEY|not signed|no longer has a Release|W:|E:" || true
}

echo "=========================================="
echo "Boomshakalaka Secure Remote Access Setup"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo bash $0${NC}"
    exit 1
fi

SETUP_DIR="/home/pds/boomshakalaka/setup"

# ==========================================
# STEP 1: SSH Hardening
# ==========================================
echo -e "${YELLOW}[1/6] Configuring SSH security...${NC}"

# Install SSH security config
cp "$SETUP_DIR/ssh-security.conf" /etc/ssh/sshd_config.d/99-security.conf
chmod 644 /etc/ssh/sshd_config.d/99-security.conf

echo -e "${GREEN}  ✓ SSH config installed${NC}"
echo "    - Internet: Key-only authentication"
echo "    - Local network (192.168.0.0/24): Password allowed"

# ==========================================
# STEP 2: Fail2ban
# ==========================================
echo -e "${YELLOW}[2/6] Installing fail2ban...${NC}"

apt_update_quiet
apt-get install -y -qq fail2ban

cp "$SETUP_DIR/fail2ban-jail.local" /etc/fail2ban/jail.local
chmod 644 /etc/fail2ban/jail.local

systemctl enable fail2ban
systemctl restart fail2ban

echo -e "${GREEN}  ✓ Fail2ban installed and configured${NC}"
echo "    - Bans IP after 3 failed attempts"
echo "    - Ban duration: 1 hour"

# ==========================================
# STEP 3: WireGuard
# ==========================================
echo -e "${YELLOW}[3/6] Setting up WireGuard VPN...${NC}"

apt-get install -y -qq wireguard qrencode

# Generate server keys
mkdir -p /etc/wireguard
chmod 700 /etc/wireguard

if [ ! -f /etc/wireguard/server_private.key ]; then
    wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
    chmod 600 /etc/wireguard/server_private.key
fi

SERVER_PRIVATE=$(cat /etc/wireguard/server_private.key)
SERVER_PUBLIC=$(cat /etc/wireguard/server_public.key)

# Generate client keys
if [ ! -f /etc/wireguard/client_private.key ]; then
    wg genkey | tee /etc/wireguard/client_private.key | wg pubkey > /etc/wireguard/client_public.key
    chmod 600 /etc/wireguard/client_private.key
fi

CLIENT_PRIVATE=$(cat /etc/wireguard/client_private.key)
CLIENT_PUBLIC=$(cat /etc/wireguard/client_public.key)

# Get public IP
PUBLIC_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "YOUR_PUBLIC_IP")

# Create server config
cat > /etc/wireguard/wg0.conf << WGEOF
[Interface]
Address = 10.200.200.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIVATE

[Peer]
# Phone/Laptop - Device 1
PublicKey = $CLIENT_PUBLIC
AllowedIPs = 10.200.200.2/32
WGEOF

chmod 600 /etc/wireguard/wg0.conf

# Create client config
CLIENT_CONF="/home/pds/boomshakalaka/setup/wireguard-client.conf"
cat > "$CLIENT_CONF" << CLIENTEOF
[Interface]
Address = 10.200.200.2/24
PrivateKey = $CLIENT_PRIVATE
DNS = 1.1.1.1

[Peer]
PublicKey = $SERVER_PUBLIC
Endpoint = $PUBLIC_IP:51820
AllowedIPs = 10.200.200.0/24
PersistentKeepalive = 25
CLIENTEOF

chown pds:pds "$CLIENT_CONF"
chmod 600 "$CLIENT_CONF"

# Generate QR code for mobile
qrencode -t ansiutf8 < "$CLIENT_CONF" > /home/pds/boomshakalaka/setup/wireguard-qr.txt
qrencode -o /home/pds/boomshakalaka/setup/wireguard-qr.png < "$CLIENT_CONF"
chown pds:pds /home/pds/boomshakalaka/setup/wireguard-qr.*

# Enable and start WireGuard
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0 || true  # May fail if already running

echo -e "${GREEN}  ✓ WireGuard installed and configured${NC}"
echo "    - Server: 10.200.200.1"
echo "    - Your device: 10.200.200.2"
echo "    - Public endpoint: $PUBLIC_IP:51820"

# ==========================================
# STEP 4: ttyd (Web Terminal)
# ==========================================
echo -e "${YELLOW}[4/6] Installing ttyd...${NC}"

apt-get install -y -qq ttyd

cp "$SETUP_DIR/ttyd.service" /etc/systemd/system/ttyd.service
chmod 644 /etc/systemd/system/ttyd.service

systemctl daemon-reload
systemctl enable ttyd
systemctl start ttyd

# Install ttyd-bottom service (bottom terminal pane)
cp "$SETUP_DIR/ttyd-bottom.service" /etc/systemd/system/ttyd-bottom.service
chmod 644 /etc/systemd/system/ttyd-bottom.service
systemctl daemon-reload
systemctl enable ttyd-bottom
systemctl start ttyd-bottom

echo -e "${GREEN}  ✓ ttyd installed and running${NC}"
echo "    - Top terminal on port 7681"
echo "    - Bottom terminal on port 7682"
echo "    - Each tab = independent terminal"

# ==========================================
# STEP 5: Firewall Configuration
# ==========================================
echo -e "${YELLOW}[5/6] Configuring firewall...${NC}"

# Reset UFW if needed
ufw --force reset > /dev/null 2>&1 || true

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow SSH from anywhere (already exposed via DMZ)
ufw allow 22/tcp

# Allow WireGuard
ufw allow 51820/udp

# Allow dashboard from local network and VPN only
ufw allow from 192.168.0.0/24 to any port 3003
ufw allow from 10.200.200.0/24 to any port 3003

# Allow ttyd from local network and VPN only (top terminal - port 7681)
ufw allow from 192.168.0.0/24 to any port 7681
ufw allow from 10.200.200.0/24 to any port 7681

# Allow ttyd-bottom from local network and VPN only (bottom terminal - port 7682)
ufw allow from 192.168.0.0/24 to any port 7682
ufw allow from 10.200.200.0/24 to any port 7682

# Enable firewall
ufw --force enable

echo -e "${GREEN}  ✓ Firewall configured${NC}"
echo "    - SSH: Open (key-only from internet)"
echo "    - WireGuard: UDP 51820"
echo "    - Dashboard: Local network + VPN only"
echo "    - ttyd (top): Port 7681, Local network + VPN only"
echo "    - ttyd (bottom): Port 7682, Local network + VPN only"

# ==========================================
# STEP 6: Restart SSH
# ==========================================
echo -e "${YELLOW}[6/6] Applying SSH configuration...${NC}"

# Test SSH config before restarting
sshd -t
if [ $? -eq 0 ]; then
    systemctl restart sshd
    echo -e "${GREEN}  ✓ SSH configuration applied${NC}"
else
    echo -e "${RED}  ✗ SSH config test failed! Not restarting.${NC}"
    exit 1
fi

# ==========================================
# DONE!
# ==========================================
echo ""
echo "=========================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. ${YELLOW}Add port forwarding on your router:${NC}"
echo "   UDP 51820 → 192.168.0.199:51820"
echo ""
echo "2. ${YELLOW}Import WireGuard config on your phone:${NC}"
echo "   - Open WireGuard app"
echo "   - Scan QR code or import config file"
echo ""
echo "   QR Code (display in terminal):"
echo "   cat /home/pds/boomshakalaka/setup/wireguard-qr.txt"
echo ""
echo "   Config file:"
echo "   /home/pds/boomshakalaka/setup/wireguard-client.conf"
echo ""
echo "3. ${YELLOW}Test the connection:${NC}"
echo "   - Connect to WireGuard on your phone"
echo "   - Open browser: http://10.200.200.1:3003"
echo "   - Click 'Terminal' in sidebar"
echo ""
echo "4. ${YELLOW}Current status:${NC}"
echo ""
wg show 2>/dev/null || echo "   WireGuard not running yet"
echo ""
systemctl status ttyd --no-pager -l | head -5
echo ""
echo "=========================================="
