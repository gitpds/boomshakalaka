# Boomshakalaka

Personal workstation server with web dashboard, remote terminal access, and secure remote access via SSH and WireGuard VPN.

## Features

- **Web Dashboard** - Flask-based dashboard with customizable UI
  - Home, Sports, Crypto, AI Studio sections
  - Integrated web terminal with tabbed interface
  - Logs viewer and settings
  - Customizable color themes

- **Web Terminal** - Browser-based terminal access via ttyd + tmux
  - **Dual terminal panes** - Top and bottom terminals paired per tab
  - Persistent sessions - tabs survive page refresh and browser close
  - Multiple tabs backed by paired tmux windows
  - Shared across devices - same terminals on desktop and mobile
  - Tab rename, close via right-click context menu
  - Resizable pane divider (drag to resize, persists on refresh)
  - Keyboard shortcuts (Ctrl+T new tab, Ctrl+W close, Ctrl+` toggle pane focus)
  - Theme synced with dashboard
  - **Split-pane File Viewer** - View code/markdown alongside terminal
    - Browse files with built-in file browser
    - Search files by name
    - Recent files list
    - Markdown rendering with syntax highlighting
    - Code syntax highlighting (50+ languages)
    - API endpoint for Claude Code integration

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
# Create tunnel: local ports -> server's localhost
ssh -L 3003:localhost:3003 -L 7681:localhost:7681 -L 7682:localhost:7682 user@your-server-ip

# Now access in browser:
# Dashboard: http://localhost:3003
# Terminal:  http://localhost:7681 (top) / http://localhost:7682 (bottom)
```

Add to `~/.ssh/config` on your **local machine** for convenience:
```
Host boomshakalaka
    HostName your-public-ip
    User pds
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 3003 localhost:3003
    LocalForward 7681 localhost:7681
    LocalForward 7682 localhost:7682
    ServerAliveInterval 60
```

Then just: `ssh boomshakalaka` and open `http://localhost:3003`

**Important:** All three ports (3003, 7681, 7682) must be forwarded for the dual terminal panes to work. If you only forward 3003, the terminal iframes will fail to connect.

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
   sudo ufw allow 51820/udp                              # WireGuard
   sudo ufw allow from 10.200.200.0/24 to any port 3003  # Dashboard via VPN
   sudo ufw allow from 10.200.200.0/24 to any port 7681  # Terminal top pane via VPN
   sudo ufw allow from 10.200.200.0/24 to any port 7682  # Terminal bottom pane via VPN
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

5. **Add to Home Screen (iOS App)**:
   - Open `http://10.200.200.1:3003` in Safari
   - Tap Share → "Add to Home Screen"
   - Name it "Boomshakalaka" and tap Add
   - The app opens in standalone mode (no browser chrome)

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
| ttyd Top Pane | 7681 | Local, VPN, SSH tunnel |
| ttyd Bottom Pane | 7682 | Local, VPN, SSH tunnel |
| SSH | 22 | Internet (key auth only) |
| WireGuard | 51820/udp | Internet |

## Progressive Web App (PWA)

The dashboard supports installation as a standalone app on iOS and Android.

### Configuration Files

- **Manifest**: `dashboard/static/manifest.json` - App name, icons, theme colors
- **Icon**: `dashboard/static/images/favicon.png` - App icon (B logo on #122637 background)
- **Meta tags**: In `dashboard/templates/base.html` - Apple-specific PWA settings

### iOS Home Screen App

When added to Home Screen via Safari, the app:
- Opens in full-screen standalone mode (no Safari UI)
- Uses the custom "B" icon
- Has a dark status bar matching the theme

### Customizing the Icon

```bash
# The favicon serves as both browser tab icon and iOS app icon
# Original backup: dashboard/static/images/favicon_backup.png

# To modify icon background color or size, edit with PIL:
python3 << 'EOF'
from PIL import Image
img = Image.open("dashboard/static/images/favicon.png").convert("RGBA")
# ... modify as needed
img.save("dashboard/static/images/favicon.png")
EOF
```

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

## Terminal File Viewer

The terminal page includes a split-pane file viewer for viewing code, markdown, and text files alongside your terminal session.

### Using the File Viewer

1. **Toggle Panel** - Click the split-pane icon in the tab bar (or press `Ctrl+\`)
2. **Browse Files** - Click the folder icon to open the file browser
   - **Recent** tab shows recently viewed files
   - **Browse** tab lets you navigate directories
   - **Search** tab finds files by name
3. **Direct Path** - Paste a file path and press Enter

### API Endpoints

The file viewer can be controlled via API, useful for Claude Code integration:

```bash
# Display a file (auto-detects markdown vs code)
curl -X POST http://localhost:3003/api/terminal/display \
  -H "Content-Type: application/json" \
  -d '{"type": "file", "path": "/home/pds/project/README.md"}'

# Display raw code with language hint
curl -X POST http://localhost:3003/api/terminal/display \
  -H "Content-Type: application/json" \
  -d '{"type": "code", "content": "def hello():\n    print(\"hi\")", "language": "python"}'

# Display raw markdown
curl -X POST http://localhost:3003/api/terminal/display \
  -H "Content-Type: application/json" \
  -d '{"type": "markdown", "content": "# Hello\n\nThis is **bold**"}'

# Get current display state
curl http://localhost:3003/api/terminal/display

# Clear the display
curl -X DELETE http://localhost:3003/api/terminal/display

# List directory contents
curl "http://localhost:3003/api/terminal/files/list?path=/home/pds"

# Search for files
curl "http://localhost:3003/api/terminal/files/search?q=README"
```

### Claude Code Integration

When working in Claude Code, you can ask it to display files in the viewer:

```
"Hey Claude, load /home/pds/project/docs/api.md in the file viewer"
```

Claude will use the API to send the file to your terminal's side panel.

### Supported File Types

- **Markdown** (`.md`) - Rendered with full formatting
- **Code** - Syntax highlighted for 50+ languages including Python, JavaScript, TypeScript, Go, Rust, SQL, YAML, and more
- **Text** (`.txt`, `.env`, etc.) - Plain text display

## Troubleshooting

### Terminal Shows "localhost refused to connect"

**Symptoms:**
- Terminal iframe shows connection refused error
- Dashboard works but terminal doesn't

**Cause:** Ports 7681/7682 aren't being forwarded through SSH tunnel.

**Fix:** Ensure your SSH config forwards all three ports:
```
Host boomshakalaka
    LocalForward 3003 localhost:3003
    LocalForward 7681 localhost:7681
    LocalForward 7682 localhost:7682
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
sudo ufw allow from 10.200.200.0/24 to any port 7682
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

The terminal uses two ttyd instances for dual panes, each connected to a paired tmux session.

```bash
# Install tmux (for persistent sessions)
sudo apt install tmux

# Install ttyd 1.7.7 (supports themes)
sudo curl -L https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 \
    -o /usr/local/bin/ttyd
sudo chmod +x /usr/local/bin/ttyd

# Make scripts executable
chmod +x scripts/start_ttyd.sh scripts/start_ttyd_bottom.sh

# Install both services (top pane on 7681, bottom pane on 7682)
sudo cp setup/ttyd.service /etc/systemd/system/
sudo cp setup/ttyd-bottom.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ttyd ttyd-bottom
```

Each browser tab maps to paired tmux windows in `dashboard-top` and `dashboard-bottom` sessions. Sessions persist across page refreshes, browser restarts, and are shared across all devices.

### SSH Security

```bash
sudo cp setup/ssh-security.conf /etc/ssh/sshd_config.d/
sudo systemctl reload sshd
```

### Firewall

```bash
sudo ufw allow 22/tcp                               # SSH
sudo ufw allow from 192.168.0.0/24 to any port 3003 # Dashboard (local)
sudo ufw allow from 192.168.0.0/24 to any port 7681 # Terminal top (local)
sudo ufw allow from 192.168.0.0/24 to any port 7682 # Terminal bottom (local)
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
