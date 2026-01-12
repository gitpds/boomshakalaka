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

## License

Private repository - personal use only.
