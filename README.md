# Boomshakalaka

Personal workstation server with web dashboard, remote terminal access, and secure remote access via SSH and WireGuard VPN.

## Features

- **Web Dashboard** - Flask-based dashboard with customizable UI
  - Home, Sports, Crypto, AI Studio sections
  - Integrated web terminal with tabbed interface
  - Logs viewer and settings
  - Customizable color themes

- **Web Terminal** - Browser-based terminal access via ttyd + tmux
  - Persistent sessions - tabs survive page refresh and browser close
  - Multiple tabs backed by tmux windows
  - Shared across devices - same terminals on desktop and mobile
  - Tab rename, close via right-click context menu
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
│   ├── theme_generator.py  # Theme generation utilities
│   ├── static/             # CSS and JavaScript
│   │   ├── styles.css
│   │   └── app.js
│   └── templates/          # Jinja2 HTML templates
│       ├── base.html       # Base template with sidebar nav
│       ├── terminal.html   # Tabbed terminal interface
│       ├── settings.html   # Settings page
│       └── ...
├── setup/                  # Server configuration files
│   ├── install.sh          # Installation script
│   ├── ttyd.service        # systemd service for web terminal
│   ├── ssh-security.conf   # SSH hardening config
│   └── wireguard-client.conf.example  # VPN client template
├── scripts/                # Utility scripts
│   ├── dashboard_ctl.py    # Dashboard management (start/stop/restart)
│   ├── start_dashboard.sh
│   ├── start_comfy.sh
│   └── generate-wireguard.sh  # Generate VPN configs from .env
├── data/                   # Data storage
│   └── themes.json         # Saved color themes
├── skills/                 # Reusable skill modules
│   └── slack_notification/ # Slack alerts to #boomshakalaka-alerts
├── docs/                   # Documentation
│   └── garbage-time-strategy.md  # Betting strategy docs
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

Add to `~/.ssh/config` on your **local machine** for convenience:
```
Host boomshakalaka
    HostName your-public-ip
    User pds
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 3003 localhost:3003
    LocalForward 7681 localhost:7681
    ServerAliveInterval 60
```

Then just: `ssh boomshakalaka` and open `http://localhost:3003`

**Important:** Both ports (3003 and 7681) must be forwarded for the web terminal to work. If you only forward 3003, the terminal iframe will fail to connect.

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

## Midnight Command Theme

The dashboard uses the "Midnight Command" theme with an Indiana Jones inspired aesthetic.

| Purpose | Color | Hex |
|---------|-------|-----|
| Background Primary | Midnight | `#060a14` |
| Background Secondary | Dark Blue | `#0e1117` |
| Background Tertiary | Navy | `#151a24` |
| Accent | Torchlight Orange | `#ff8c00` |
| Accent Hover | Golden Yellow | `#ffcc00` |
| Gold | Antique Gold | `#d4af37` |
| Text Primary | White | `#ffffff` |
| Text Secondary | Light Gray | `#c4c4c4` |

### Theme Features
- Glass-morphism card effects with gold borders
- Torchlight glow on logo hover
- Custom gold scrollbars
- Subtle dot pattern overlay
- Crimson Pro display font for headings

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

## Dashboard Management

Use the dashboard control script to manage the server:

```bash
# Check status
python scripts/dashboard_ctl.py status

# Restart (picks up code changes)
python scripts/dashboard_ctl.py restart

# Stop
python scripts/dashboard_ctl.py stop

# Start
python scripts/dashboard_ctl.py start
```

The script automatically detects if the dashboard is managed by systemd and handles restarts appropriately.

## Troubleshooting

### Terminal Shows "localhost refused to connect"

**Symptoms:**
- Terminal iframe shows connection refused error
- Dashboard works but terminal doesn't

**Cause:** Port 7681 isn't being forwarded through SSH tunnel.

**Fix:** Ensure your SSH config forwards both ports:
```
Host boomshakalaka
    LocalForward 3003 localhost:3003
    LocalForward 7681 localhost:7681
```

### Terminal Shows Blinking Cursor / Won't Connect

**Symptoms:**
- Terminal tab shows only a blinking cursor
- Console errors: `CORS policy`, `WebSocket closed`, or `Failed to fetch`

**Cause:** Flask is serving a cached template.

**Fix:**
```bash
# Restart the dashboard
python scripts/dashboard_ctl.py restart

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

### SSH Tunnel "Address Already in Use"

**Symptoms:**
- `bind [127.0.0.1]:3003: Address already in use` when connecting

**Cause:** A previous SSH session didn't close cleanly, or another process is using the port.

**Fix (on your local machine):**
```bash
# Find what's using the port
lsof -i :3003

# Kill the process (replace PID with actual number)
kill -9 <PID>

# Or kill all SSH sessions to boomshakalaka
pkill -f "ssh boomshakalaka"
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

### Web Terminal (ttyd + tmux)

The terminal uses ttyd for browser access and tmux for persistent sessions.

```bash
# Install tmux (for persistent sessions)
sudo apt install tmux

# Install ttyd 1.7.7 (supports themes)
sudo curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
    -o /usr/local/bin/ttyd
sudo chmod +x /usr/local/bin/ttyd

# Install service (connects ttyd to tmux session)
sudo cp setup/ttyd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ttyd
```

Each browser tab maps to a tmux window. Sessions persist across page refreshes, browser restarts, and are shared across all devices.

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

## Skills

### Slack Notification (`skills/slack_notification/`)

Sends notifications to `#boomshakalaka-alerts` channel.

```python
from skills.slack_notification import send_message, send_alert

# Simple message
send_message("Hello world")

# Formatted alert
send_alert("Title", "Message", level="success", fields={"Key": "Value"})
```

Levels: `info`, `success`, `warning`, `error`, `money`

See `skills/slack_notification/README.md` for full documentation.

## Sports Betting Analysis

The dashboard includes a garbage time betting analysis system at `/sports/betting/analysis`.

**Strategy**: Bet on the trailing team when halftime lead is 15-17 points for optimal ROI (+$17.31 EV per $100).

Features:
- Bell distribution chart showing edge by point bucket
- ROI-focused analysis (profit per dollar wagered)
- Running profit tracker for optimal range
- Slack alerts when blowouts are detected

See `docs/garbage-time-strategy.md` for full strategy documentation.

## Contributing

This is an open source project. Contributions welcome!

1. Fork the repository
2. Create a feature branch
3. Ensure no secrets are committed
4. Submit a pull request

## License

MIT License - See LICENSE file for details.
