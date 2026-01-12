# Monitoring Dashboard

Web-based dashboard for monitoring all Money Printing automation systems.

## Access

| Type | URL |
|------|-----|
| **Network** | http://192.168.0.199:8080 |
| **Local** | http://localhost:8080 |

## Features

### Cron Job Overview
- Lists all scheduled cron jobs
- Shows human-readable schedules
- Displays truncated commands

### Log Viewer
- Tails last 25 lines of each log file
- Shows last successful run timestamp
- Counts errors in last 24 hours

### API Health Checks
- Tests The Odds API connectivity
- Tests Polymarket Gamma API
- Shows response codes and messages

## Running the Dashboard

### As a Service (Recommended)

The dashboard runs as a systemd user service that auto-starts on boot.

```bash
# Check status
systemctl --user status polymarket-dashboard

# Start
systemctl --user start polymarket-dashboard

# Stop
systemctl --user stop polymarket-dashboard

# Restart
systemctl --user restart polymarket-dashboard

# View logs
journalctl --user -u polymarket-dashboard -f

# Enable auto-start
systemctl --user enable polymarket-dashboard

# Disable auto-start
systemctl --user disable polymarket-dashboard
```

### Manual Start

```bash
cd /home/pds/money_printing/polymarket
python -m dashboard.server
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard HTML page |
| `/api/health` | GET | JSON health check results |
| `/api/logs/<name>` | GET | Get specific log content |
| `/api/cron` | GET | List all cron jobs as JSON |

### Example API Usage

```bash
# Get health status
curl http://192.168.0.199:8080/api/health

# Get cron jobs
curl http://192.168.0.199:8080/api/cron

# Get sports betting log
curl http://192.168.0.199:8080/api/logs/garbage
```

## Service Configuration

Service file: `~/.config/systemd/user/polymarket-dashboard.service`

```ini
[Unit]
Description=Polymarket Automation Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/pds/money_printing/polymarket
Environment="PATH=/home/pds/miniconda3/envs/money_env/bin:..."
ExecStart=/home/pds/miniconda3/envs/money_env/bin/python -m dashboard.server
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

## Module Structure

```
dashboard/
├── __init__.py
├── server.py           # Flask application (port 8080)
├── health_check.py     # CLI health check script
└── templates/
    └── dashboard.html  # Web UI template
```

## Health Check CLI

Run health checks from command line:

```bash
cd /home/pds/money_printing/polymarket
python -m dashboard.health_check
```

Output:
```
=== Money Printing Health Check ===
Generated: 2026-01-08 14:30:00

[LOGS]
  sports_betting/cron.log
    Last run: 2026-01-08 14:20:01
    Errors (24h): 0
    Status: OK

  insider/cron.log
    Last run: 2026-01-08 14:15:01
    Errors (24h): 0
    Status: OK

[APIs]
  The Odds API: OK (200)
  Polymarket API: OK (200)

[CRON JOBS]
  5 jobs configured
  All schedules valid
```

## Customization

### Adding New Log Files

Edit `server.py`:

```python
LOG_FILES = {
    'Garbage Time Monitor': POLYMARKET_DIR / 'sports_betting' / 'cron.log',
    'Insider Detector': POLYMARKET_DIR / 'insider' / 'cron.log',
    'New System': POLYMARKET_DIR / 'new_system' / 'cron.log',  # Add here
}
```

### Changing Port

Edit `server.py`:

```python
app.run(host='0.0.0.0', port=8080)  # Change 8080 to desired port
```

Then update the systemd service and restart.

## Troubleshooting

### Port Already in Use

```bash
# Find process using port 8080
lsof -i :8080

# Kill it
kill <PID>

# Restart service
systemctl --user restart polymarket-dashboard
```

### Service Won't Start

```bash
# Check logs
journalctl --user -u polymarket-dashboard -n 50

# Common issues:
# - Flask not installed: pip install flask
# - Port in use: kill existing process
# - Path issues: check WorkingDirectory in service file
```

### Dashboard Not Accessible from Network

1. Verify server binds to `0.0.0.0` (not `127.0.0.1`)
2. Check firewall: `sudo ufw status`
3. Verify IP address: `hostname -I`

## Screenshots

The dashboard displays:
- Dark theme UI
- Card-based layout for each system
- Color-coded status indicators (green/yellow/red)
- Scrollable log output areas
- Refresh button for real-time updates
