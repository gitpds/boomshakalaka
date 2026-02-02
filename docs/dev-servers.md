# Dev Servers System

> **Last Updated:** 2026-01-29
> **Status:** Working
> **Critical for:** Remote access to development servers via SSH tunnel

---

## Quick Start

```bash
# Start True Tracking on port 4000
cd /home/pds/businesses/true-tracking/customer_dashboard
nohup npm run dev -- -p 4000 > /tmp/true-tracking-4000.log 2>&1 &

# Verify it's running
curl -sI http://localhost:4000 | head -1
# Expected: HTTP/1.1 200 OK

# Check dashboard sees it
curl -s http://localhost:3003/api/dev-port/active | jq '.active'
```

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         YOUR LOCAL MACHINE                               │
│                                                                          │
│   Browser → http://localhost:4000 ──┐                                   │
│                                      │                                   │
│                              SSH Tunnel (port forward)                   │
│                                      │                                   │
└──────────────────────────────────────┼───────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         BOOMSHAKALAKA SERVER                             │
│                                                                          │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    │
│   │   Dashboard     │    │  True Tracking  │    │  Other Servers  │    │
│   │   Port 3003     │    │   Port 4000     │    │  Ports 4001+    │    │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘    │
│            │                                                             │
│            └──── Monitors ports via /api/dev-port/active                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Port Ranges Monitored

The dashboard monitors these port ranges and displays active servers:

| Range | Category | Purpose |
|-------|----------|---------|
| 3000-3010 | Node.js | General Node.js apps |
| **4000-4019** | **Allocated** | **Dev servers started by Claude** |
| 5000-5010 | Flask | Python Flask apps |
| 8000-8010 | Django/FastAPI | Python web frameworks |

**Excluded ports:** 3003 (dashboard), 3004 (dashboard-ctl)

### What's NOT Monitored (Intentionally Hidden)

These were removed from monitoring on 2026-01-29 per user request:
- Port 5678 (n8n) - automation tool, always running
- Port 8188 (ComfyUI) - AI image generation, always running

---

## SSH Port Forwarding

### User's Actual SSH Config

The user connects via SSH alias `boomshakalaka-remote`:

| Setting | Value |
|---------|-------|
| **Alias** | `boomshakalaka-remote` |
| **HostName** | `206.55.184.182` |
| **User** | `pds` |
| **Key** | ed25519 |
| **Keepalive** | 60s |

### Forwarded Ports (23 total)

| Port(s) | Purpose |
|---------|---------|
| **3003** | Dashboard |
| **7681-7682** | Terminal sessions (ttyd) |
| **4000-4019** | Dev server range (20 ports) |

### What This Means for Claude

**You can use ANY port from 4000-4019** for dev servers. The user has all 20 ports forwarded.

```bash
# These ALL work:
npm run dev -- -p 4000   # First choice
npm run dev -- -p 4005   # Also works
npm run dev -- -p 4019   # Also works
```

### Verifying Port Forwards

```bash
# On your LOCAL machine, after SSH connection
curl http://localhost:4000  # Should show dev server
curl http://localhost:3003  # Should show Dashboard
```

---

## Starting Dev Servers

### True Tracking (Next.js)

```bash
cd /home/pds/businesses/true-tracking/customer_dashboard
nohup npm run dev -- -p 4000 > /tmp/true-tracking-4000.log 2>&1 &

# Check logs if issues
tail -f /tmp/true-tracking-4000.log
```

### Generic Next.js Project

```bash
cd /path/to/project
nohup npm run dev -- -p 4001 > /tmp/project-4001.log 2>&1 &
```

### Flask Project

```bash
cd /path/to/flask/project
source .venv/bin/activate
nohup flask run --port 5001 > /tmp/flask-5001.log 2>&1 &
```

---

## Stopping Dev Servers

### By Port

```bash
# Find the PID
ss -tlnp | grep ':4000'
# Output: LISTEN ... users:(("next-server",pid=1565116,fd=22))

# Kill by PID
kill 1565116
```

### By Process Name

```bash
# Find and kill all Next.js dev servers
pkill -f "next-server"

# Find and kill specific project
pkill -f "customer_dashboard.*next"
```

---

## Dashboard API

### Get Active Dev Servers

```bash
curl -s http://localhost:3003/api/dev-port/active | jq
```

Response:
```json
{
  "active": [
    {
      "port": 4000,
      "project": "customer_dashboard",
      "cwd": "/home/pds/businesses/true-tracking/customer_dashboard",
      "command": "next-server (v16.1.1)",
      "pid": "1565116",
      "category": "Allocated",
      "managed": false
    }
  ],
  "ranges": [
    {"start": 3000, "end": 3010, "category": "Node.js"},
    {"start": 4000, "end": 4019, "category": "Allocated"},
    {"start": 5000, "end": 5010, "category": "Flask"},
    {"start": 8000, "end": 8010, "category": "Django/FastAPI"}
  ]
}
```

### Get Next Available Port

```bash
curl -s http://localhost:3003/api/dev-port | jq
```

Response:
```json
{
  "port": 4001,
  "message": "Port 4001 is available for use"
}
```

---

## Troubleshooting

### "Connection refused" when clicking dashboard links

**Cause:** Port not forwarded in SSH config

**Fix:**
1. Add `LocalForward <port> localhost:<port>` to SSH config
2. Reconnect SSH session

### Server shows in dashboard but can't access it

**Cause:** SSH tunnel not active for that port

**Verify:**
```bash
# On LOCAL machine
ss -tlnp | grep ':4000'
# Should show SSH listening on 4000
```

### Server not showing in dashboard

**Cause:** Server not running, or on wrong port range

**Verify:**
```bash
# On SERVER
ss -tlnp | grep ':4000'
# Should show the server process
```

### Dashboard showing old/stale servers

**Cause:** Dashboard cache (unlikely) or process still running

**Fix:**
```bash
# Find what's actually listening
ss -tlnp | grep LISTEN | grep -E ':(3[0-9]{3}|4[0-9]{3}|5[0-9]{3}|8[0-9]{3})'
```

---

## Configuration

### Modifying Monitored Port Ranges

Edit `/home/pds/boomshakalaka/dashboard/server.py`:

```python
# Around line 127
DEV_PORT_RANGES = [
    (3000, 3010, 'Node.js'),
    (4000, 4019, 'Allocated'),
    (5000, 5010, 'Flask'),
    (8000, 8010, 'Django/FastAPI'),
]

# Ports to exclude even if in range
EXCLUDED_PORTS = {3003, 3004}  # Dashboard, dashboard-ctl
```

After changes:
```bash
sudo systemctl restart dashboard
```

---

## History

### 2026-01-29: Simplified Dev Server Display
- Removed n8n (5678) and ComfyUI (8188) from monitored ranges
- These are always-on services, not dev servers
- User only cares about servers Claude starts
- Documented user's actual SSH config (`boomshakalaka-remote`)

### Port Allocation Strategy
- Ports 4000-4019 are "Allocated" for Claude-started dev servers
- Claude should use port 4000 first, then 4001, etc.
- **User's SSH config forwards ALL of 4000-4019** (20 ports available)
