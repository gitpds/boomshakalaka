# Boomshakalaka

Personal workstation server with web dashboard, remote terminal access, and secure remote access via SSH and WireGuard VPN.

## Features

- **Web Dashboard** - Flask-based dashboard with customizable dark theme UI
  - Home, Sports, Crypto, AI Studio sections
  - Integrated web terminal with tabbed interface
  - Logs viewer and settings
  - AI-powered theme customization via Claude API

- **Web Terminal** - Browser-based terminal access via ttyd
  - Multiple tabs in same window
  - Tab rename, close, reconnect via right-click
  - Keyboard shortcuts (Ctrl+T new tab, Ctrl+W close)
  - Theme synced with dashboard

- **Secure Remote Access**
  - SSH with key-only authentication from internet
  - Password authentication allowed from local network
  - WireGuard VPN for secure remote access to all services
  - SSH tunneling for accessing dashboard remotely

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/gitpds/boomshakalaka.git
   cd boomshakalaka
   ```

2. Copy and configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

3. Run the install script:
   ```bash
   cd setup
   chmod +x install.sh
   ./install.sh
   ```

4. Start the dashboard:
   ```bash
   python -m dashboard.server
   ```

5. Access at `http://localhost:3003`

## Project Structure

```
boomshakalaka/
├── dashboard/              # Flask web dashboard
│   ├── server.py           # Main Flask application
│   ├── theme_generator.py  # AI theme generation
│   ├── static/             # CSS and JavaScript
│   │   ├── styles.css
│   │   └── app.js
│   └── templates/          # Jinja2 HTML templates
│       ├── base.html       # Base template with sidebar nav
│       ├── terminal.html   # Tabbed terminal interface
│       ├── settings.html   # Settings with theme customization
│       └── ...
├── setup/                  # Server configuration files
│   ├── install.sh          # Installation script
│   ├── ttyd.service        # systemd service for web terminal
│   ├── ssh-security.conf   # SSH hardening config
│   └── wireguard-client.conf.example  # VPN client template
├── scripts/                # Utility scripts
│   ├── start_dashboard.sh
│   ├── start_comfy.sh
│   └── generate-wireguard.sh  # Generate VPN configs from .env
├── data/                   # Data storage
│   └── themes.json         # Saved color themes
├── .env.example            # Environment variables template
└── .env                    # Your local config (not in git)
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `ODDS_API_KEY` | API key for sports odds data |
| `YOUTUBE_API_KEY` | YouTube Data API key |
| `ANTHROPIC_API_KEY` | Claude API key for theme generation |
| `WG_SERVER_*` | WireGuard server configuration |
| `WG_CLIENT_*` | WireGuard client configuration |

### Generating WireGuard Keys

```bash
# Generate a keypair
wg genkey | tee privatekey | wg pubkey > publickey

# View the keys
cat privatekey  # Add to WG_*_PRIVATE_KEY
cat publickey   # Add to WG_*_PUBLIC_KEY
```

## Remote Access

### Option 1: SSH with Port Forwarding (Recommended for Desktop)

If you have SSH access to the server, you can tunnel the dashboard through SSH:

```bash
# Create tunnel: local port 3003 -> server's localhost:3003
ssh -L 3003:localhost:3003 -L 7681:localhost:7681 user@your-server-ip

# Now access in browser:
# Dashboard: http://localhost:3003
# Terminal:  http://localhost:7681
```

Add to `~/.ssh/config` for convenience:
```
Host boomshakalaka
    HostName your-public-ip
    User pds
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 3003 localhost:3003
    LocalForward 7681 localhost:7681
```

Then just: `ssh boomshakalaka` and open `http://localhost:3003`

### Option 2: WireGuard VPN (Recommended for Mobile)

WireGuard provides secure access to all services without individual port forwards.

#### Server Setup

1. Install WireGuard:
   ```bash
   sudo apt install wireguard qrencode
   ```

2. Generate keys and add to `.env`:
   ```bash
   # Server keys
   wg genkey | tee /tmp/server_private | wg pubkey > /tmp/server_public
   echo "WG_SERVER_PRIVATE_KEY=$(cat /tmp/server_private)"
   echo "WG_SERVER_PUBLIC_KEY=$(cat /tmp/server_public)"

   # Client keys
   wg genkey | tee /tmp/client_private | wg pubkey > /tmp/client_public
   echo "WG_CLIENT_PRIVATE_KEY=$(cat /tmp/client_private)"
   echo "WG_CLIENT_PUBLIC_KEY=$(cat /tmp/client_public)"

   # Clean up
   rm /tmp/*_private /tmp/*_public
   ```

3. Generate configs from environment:
   ```bash
   ./scripts/generate-wireguard.sh
   ```

4. Install and start server:
   ```bash
   # Copy the output server config to WireGuard
   sudo cp /path/to/wg0.conf /etc/wireguard/
   sudo chmod 600 /etc/wireguard/wg0.conf
   sudo systemctl enable --now wg-quick@wg0
   ```

5. Configure firewall:
   ```bash
   sudo ufw allow 51820/udp                           # WireGuard
   sudo ufw allow from 10.200.200.0/24 to any port 3003  # Dashboard via VPN
   sudo ufw allow from 10.200.200.0/24 to any port 7681  # Terminal via VPN
   ```

#### Client Setup (Mobile)

1. Install WireGuard app on your phone (iOS/Android)

2. Display QR code on server:
   ```bash
   cat setup/wireguard-qr.txt
   # Or view the PNG: setup/wireguard-qr.png
   ```

3. Scan QR code with WireGuard app

4. Connect and access:
   - Dashboard: `http://10.200.200.1:3003`
   - Terminal: `http://10.200.200.1:7681`

#### Client Setup (Desktop)

1. Install WireGuard: https://www.wireguard.com/install/

2. Import `setup/wireguard-client.conf`

3. Connect and access services at `10.200.200.1`

### Option 3: Direct Access (Local Network Only)

From the same network:
- Dashboard: `http://192.168.x.x:3003`
- Terminal: `http://192.168.x.x:7681`

## Services

| Service | Port | Access |
|---------|------|--------|
| Dashboard | 3003 | Local, VPN, SSH tunnel |
| ttyd Terminal | 7681 | Local, VPN, SSH tunnel |
| SSH | 22 | Internet (key auth only) |
| WireGuard | 51820/udp | Internet |

## Theme Customization

The dashboard supports AI-generated color themes:

1. Go to **Settings** in the dashboard
2. Enter a natural language description (e.g., "cyberpunk purple with neon pink accents")
3. Click **Generate Theme** - Claude AI creates a matching color palette
4. **Apply Theme** to see it instantly
5. **Save Theme** to keep it for later

Themes are stored in `data/themes.json` and persist across sessions.

To update the terminal theme to match, copy and run the displayed command.

### Default Color Palette

| Purpose | Color | Hex |
|---------|-------|-----|
| Background Primary | Dark Teal | `#122637` |
| Background Secondary | Darker Teal | `#0a1820` |
| Background Tertiary | Border Teal | `#1e3a4c` |
| Accent | Gold | `#f0cb09` |
| Text Primary | White | `#ffffff` |
| Text Secondary | Light Blue | `#b8d4e8` |

## Security Notes

- **Never commit `.env`** - It's in `.gitignore` but double-check
- **WireGuard keys are sensitive** - Keep private keys secret
- **SSH key auth** - Password auth is disabled for internet access
- **Firewall** - Services are restricted to local network and VPN by default

### Checking for Leaked Secrets

```bash
# Before committing, verify no secrets are staged
git diff --cached | grep -E "(KEY|PRIVATE|SECRET|PASSWORD)"

# Check if .env is tracked (should return nothing)
git ls-files | grep "\.env$"
```

## Troubleshooting

### Terminal Shows Blinking Cursor / Won't Connect

**Symptoms:**
- Terminal tab shows only a blinking cursor
- Console errors: `CORS policy`, `WebSocket closed`, or `Failed to fetch`

**Cause:** Flask is serving a cached template.

**Fix:**
```bash
# Restart the dashboard
pkill -f "dashboard.server"
python -m dashboard.server &

# Hard refresh browser: Ctrl+Shift+R
```

### Can't Connect to VPN

**Symptoms:**
- WireGuard shows "handshake did not complete"
- Connection timeout

**Diagnosis:**
```bash
# Check WireGuard is running on server
sudo wg show

# Check port is open
sudo ufw status | grep 51820

# Check from client
nc -zvu your-server-ip 51820
```

**Common fixes:**
- Ensure port 51820/udp is forwarded in router
- Check server firewall allows WireGuard
- Verify public IP hasn't changed

### SSH Connection Refused

**Diagnosis:**
```bash
# Check SSH is running
systemctl status sshd

# Check firewall
sudo ufw status | grep 22

# Test connection verbosely
ssh -v user@server
```

### Dashboard Not Accessible via VPN

**Ensure firewall allows VPN subnet:**
```bash
sudo ufw allow from 10.200.200.0/24 to any port 3003
sudo ufw allow from 10.200.200.0/24 to any port 7681
```

### ttyd Terminal Read-Only

If you can see the terminal but typing doesn't work:

**Cause:** ttyd 1.7+ defaults to read-only mode

**Fix:** Ensure `-W` flag is in the service file:
```bash
# Check current config
grep ExecStart /etc/systemd/system/ttyd.service

# Should include -W flag
# ExecStart=/usr/local/bin/ttyd -p 7681 -W ...
```

## Manual Installation

### Web Terminal (ttyd)

```bash
# Install ttyd 1.7.7 (supports themes)
sudo curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
    -o /usr/local/bin/ttyd
sudo chmod +x /usr/local/bin/ttyd

# Install service
sudo cp setup/ttyd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ttyd
```

### SSH Security

```bash
sudo cp setup/ssh-security.conf /etc/ssh/sshd_config.d/
sudo systemctl reload sshd
```

### Firewall

```bash
sudo ufw allow 22/tcp                               # SSH
sudo ufw allow from 192.168.0.0/24 to any port 3003 # Dashboard (local)
sudo ufw allow from 192.168.0.0/24 to any port 7681 # Terminal (local)
sudo ufw allow 51820/udp                            # WireGuard
sudo ufw enable
```

## Contributing

This is an open source project. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Ensure no secrets are committed
4. Submit a pull request

## License

MIT License - See LICENSE file for details.
