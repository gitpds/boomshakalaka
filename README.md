# Boomshakalaka

Personal workstation server with web dashboard, remote terminal access, and secure SSH configuration.

## Features

- **Web Dashboard** - Flask-based dashboard with dark theme UI
  - Home, Sports, Crypto, AI Studio sections
  - Integrated web terminal with tabbed interface
  - Logs viewer and settings

- **Web Terminal** - Browser-based terminal access via ttyd
  - Multiple tabs in same window
  - Tab rename, close, reconnect via right-click
  - Keyboard shortcuts (Ctrl+T new tab, Ctrl+W close)

- **Secure Remote Access**
  - SSH with key-only authentication from internet
  - Password authentication allowed from local network (192.168.0.0/24)
  - WireGuard VPN configuration included

## Project Structure

```
boomshakalaka/
├── dashboard/           # Flask web dashboard
│   ├── server.py        # Main Flask application
│   ├── static/          # CSS and JavaScript
│   │   ├── styles.css
│   │   └── app.js
│   └── templates/       # Jinja2 HTML templates
│       ├── base.html    # Base template with sidebar nav
│       ├── terminal.html # Tabbed terminal interface
│       └── ...
├── setup/               # Server configuration files
│   ├── install.sh       # Installation script
│   ├── ttyd.service     # systemd service for web terminal
│   ├── ssh-security.conf # SSH hardening config
│   ├── wireguard-client.conf # VPN client config
│   └── wireguard-qr.txt # QR code for mobile VPN setup
├── scripts/             # Utility scripts
│   ├── start_dashboard.sh
│   └── start_comfy.sh
├── ai_studio/           # AI/ML related code
├── automation/          # Automation scripts
└── data/                # Data storage
```

## Installation

### Prerequisites
- Ubuntu 22.04+
- Python 3.10+

### Quick Start

1. Run the install script:
   ```bash
   cd setup
   chmod +x install.sh
   ./install.sh
   ```

2. Start the dashboard:
   ```bash
   cd dashboard
   python server.py
   ```

3. Access at `http://<server-ip>:3003`

### Manual Setup

#### Web Terminal (ttyd)
```bash
sudo apt install ttyd
sudo cp setup/ttyd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ttyd
```

#### SSH Security
```bash
sudo cp setup/ssh-security.conf /etc/ssh/sshd_config.d/
sudo systemctl reload sshd
```

#### Firewall
```bash
# Allow dashboard
sudo ufw allow 3003/tcp

# Allow ttyd from local network
sudo ufw allow from 192.168.0.0/24 to any port 7681

# Allow SSH
sudo ufw allow 22/tcp
```

## Remote Access

### SSH
From any machine with your key:
```bash
ssh pds@<server-ip>
```

Add to `~/.ssh/config` for convenience:
```
Host boomshakalaka
    HostName <public-ip>
    User pds
    IdentityFile ~/.ssh/id_ed25519
```

Then: `ssh boomshakalaka`

### Port Forwarding (Router)
For remote SSH access, forward port 22 to the server's local IP in your router's Virtual Server settings.

## Services

| Service | Port | Description |
|---------|------|-------------|
| Dashboard | 3003 | Web UI |
| ttyd | 7681 | Web terminal backend |
| SSH | 22 | Secure shell |
| WireGuard | 51820 | VPN (if configured) |

## Color Palette

The dashboard uses a dark teal theme:
- Background: `#122637`
- Accent: `#f0cb09` (gold)
- Tab bar: `#0a1820`
- Border: `#1e3a4c`

## Troubleshooting

### Terminal Shows Blinking Cursor / Won't Connect

**Symptoms:**
- Terminal tab shows only a blinking cursor
- Console errors: `CORS policy`, `WebSocket closed`, or `Failed to fetch`
- Error mentions `/token` endpoint

**Cause:** Flask is serving a cached template. The dashboard was started before the template file was updated.

**Fix:**
```bash
# Restart the dashboard to reload templates
pkill -f "dashboard.server"
cd /home/pds/boomshakalaka
/home/pds/miniconda3/envs/money_env/bin/python -m dashboard.server &

# Hard refresh browser (clears browser cache too)
# Chrome/Firefox: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
```

**Verify fix:**
```bash
# Check that served template matches file on disk
curl -s http://localhost:3003/terminal | wc -l
wc -l dashboard/templates/terminal.html
# Both should show ~593 lines (iframe version)
# If served version shows ~1087 lines, dashboard needs restart
```

### Terminal CORS Errors

**Symptoms:**
```
Access to fetch at 'http://192.168.0.199:7681/token' blocked by CORS policy
```

**Cause:** This error is expected when using direct WebSocket connections to ttyd. The current iframe-based implementation avoids this issue. If you see this error, you're likely running an old cached template (see above).

### Terminal WebSocket Immediately Closes

**Symptoms:**
- WebSocket connects then immediately closes
- ttyd logs show `SEGV` or crash

**Cause:** ttyd version 1.6.3 has compatibility issues with custom xterm.js WebSocket implementations using the `['tty']` subprotocol.

**Solution:** Use the iframe-based terminal (current implementation). The iframe embeds ttyd's own frontend which handles the WebSocket protocol correctly.

### ttyd Service Shows "invalid option" Warning

**Symptoms:**
```
ttyd[67602]: /usr/bin/ttyd: invalid option -- 'W'
```

**Cause:** The `-W` flag (writable) doesn't exist in ttyd 1.6.3.

**Fix:**
```bash
# Update the installed service file
sudo cp /home/pds/boomshakalaka/setup/ttyd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart ttyd
```

### Terminal Not Accessible from Browser

**Symptoms:**
- `ERR_CONNECTION_REFUSED` when accessing terminal
- ttyd is running but browser can't connect

**Diagnosis:**
```bash
# Check ttyd is running
systemctl status ttyd

# Check it's listening
ss -tlnp | grep 7681

# Test local access
curl http://localhost:7681/token
```

**Fix (if firewall is blocking):**
```bash
# Allow ttyd from local network
sudo ufw allow from 192.168.0.0/24 to any port 7681

# If using WireGuard VPN
sudo ufw allow from 10.200.200.0/24 to any port 7681
```

### Dashboard Not Starting

**Check logs:**
```bash
# If running manually, check terminal output
# If running as service:
journalctl --user -u dashboard -n 50
```

**Common issues:**
- Missing dependencies: `pip install flask httpx`
- Port in use: `lsof -i :3003` then `kill <PID>`
- Wrong working directory: must run from project root

## License

Private repository - personal use only.
