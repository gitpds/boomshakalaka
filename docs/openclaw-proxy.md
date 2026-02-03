# OpenClaw Proxy Architecture

> **Last Updated:** 2026-02-01

This document explains the Flask reverse proxy that enables OpenClaw embedding in the Boomshakalaka dashboard.

![OpenClaw Proxy Working](openclaw-proxy-working.png)
*The OpenClaw iframe loads successfully through the proxy with "Connected to OpenClaw Gateway" status.*

## Problem

OpenClaw's WebSocket connection requires a **secure context** per the W3C specification. When embedding OpenClaw via iframe, the browser enforces this requirement:

```
disconnected (1008): control ui requires HTTPS or localhost (secure context)
```

**Why it fails without proxy:**
- Dashboard loads from `localhost:3003` (secure context)
- iframe loads from `http://192.168.0.168:18789` (NOT secure - different host over HTTP)
- WebSocket connection is rejected

**Why localhost is secure:**
Per W3C spec, `localhost` and `127.0.0.1` are always treated as secure contexts, even over HTTP. This is intentional to support local development.

## Solution

Route OpenClaw traffic through the Flask dashboard so the browser sees everything as coming from `localhost:3003`.

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (localhost:3003)                 │
│                                                             │
│  ┌─────────────────┐        ┌────────────────────────────┐ │
│  │   Dashboard     │        │   OpenClaw iframe          │ │
│  │   (Flask)       │        │   src=/openclaw-proxy/     │ │
│  └─────────────────┘        └────────────────────────────┘ │
│                                        │                    │
└────────────────────────────────────────│────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │         Flask Proxy Routes              │
                    │                                         │
                    │  /openclaw-proxy/<path>  → HTTP proxy   │
                    │  /openclaw-proxy (ws)    → WS proxy     │
                    └────────────────────│────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │      OpenClaw Gateway (MacBook)         │
                    │      http://192.168.0.168:18789         │
                    └─────────────────────────────────────────┘
```

## Implementation

### Dependencies

```bash
# In money_env conda environment
pip install flask-sock websocket-client
```

### Server Code (server.py)

**Imports added:**
```python
import threading
import websocket as ws_client
from flask import Response
from flask_sock import Sock
```

**Flask-Sock initialization:**
```python
sock = Sock(app)
```

**HTTP Proxy Route:**
```python
@app.route('/openclaw-proxy/')
@app.route('/openclaw-proxy/<path:path>')
def openclaw_proxy(path: str = ''):
    """Proxy HTTP requests to OpenClaw gateway"""
    target_url = f'{REGGIE_OPENCLAW_URL}/{path}'

    if request.query_string:
        target_url += '?' + request.query_string.decode()

    resp = requests.request(
        method=request.method,
        url=target_url,
        headers={k: v for k, v in request.headers if k.lower() not in ['host']},
        data=request.get_data(),
        timeout=30,
        allow_redirects=False
    )

    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]

    return Response(resp.content, resp.status_code, headers)
```

**WebSocket Proxy Route:**
```python
@sock.route('/openclaw-proxy')
def openclaw_ws_proxy(ws):
    """Proxy WebSocket connections to OpenClaw gateway"""
    openclaw_ws_url = REGGIE_OPENCLAW_URL.replace('http://', 'ws://')
    target = ws_client.create_connection(openclaw_ws_url, timeout=30)

    def forward_to_client():
        while True:
            msg = target.recv()
            if msg:
                ws.send(msg)

    thread = threading.Thread(target=forward_to_client, daemon=True)
    thread.start()

    while True:
        msg = ws.receive()
        if msg:
            target.send(msg)
```

### Template Code (reggie_openclaw.html)

```javascript
// Proxy through localhost for secure context
const OPENCLAW_URL = '/openclaw-proxy/';
const OPENCLAW_DIRECT_URL = 'http://192.168.0.168:18789';

// iframe loads via proxy
frame.src = OPENCLAW_URL;

// "Open in New Tab" uses direct URL (works in its own context)
function openInNewTab() {
    window.open(OPENCLAW_DIRECT_URL, '_blank');
}
```

## URL Mapping

| Browser Request | Proxied To |
|-----------------|------------|
| `localhost:3003/openclaw-proxy/` | `192.168.0.168:18789/` |
| `localhost:3003/openclaw-proxy/assets/index.js` | `192.168.0.168:18789/assets/index.js` |
| `ws://localhost:3003/openclaw-proxy` | `ws://192.168.0.168:18789` |

## Verification

**Check all systems:**
```bash
curl -s http://localhost:3003/api/reggie/health | jq
```

Expected output:
```json
{
  "daemon": "running",
  "dashboard": true,
  "openclaw": true,
  "robot": true
}
```

**Test HTTP proxy:**
```bash
curl -sI http://localhost:3003/openclaw-proxy/ | head -3
# Should return: HTTP/1.1 200 OK
```

**Test asset proxy:**
```bash
curl -sI http://localhost:3003/openclaw-proxy/assets/index-CXUONUC9.js | head -3
# Should return: HTTP/1.1 200 OK, Content-Type: application/javascript
```

## Troubleshooting

### OpenClaw offline (502 errors)

1. Check if OpenClaw is running on MacBook:
   ```bash
   ssh reggiembp "lsof -i :18789"
   ```

2. Start OpenClaw:
   ```bash
   ssh reggiembp "source ~/.nvm/nvm.sh && cd ~/.openclaw && nohup openclaw gateway --bind lan > /tmp/openclaw.log 2>&1 &"
   ```

3. Check logs:
   ```bash
   ssh reggiembp "tail -50 /tmp/openclaw.log"
   ```

### WebSocket not connecting

1. Verify Flask-Sock is installed:
   ```bash
   source /home/pds/miniconda3/etc/profile.d/conda.sh
   conda activate money_env
   pip show flask-sock
   ```

2. Check dashboard logs:
   ```bash
   journalctl -u dashboard -f
   ```

### iframe shows "secure context" error

This means the proxy isn't being used. Check:
- Template has `OPENCLAW_URL = '/openclaw-proxy/'`
- Dashboard was restarted after changes

## Files Modified

| File | Purpose |
|------|---------|
| `dashboard/server.py` | Proxy routes and Flask-Sock init |
| `dashboard/templates/reggie_openclaw.html` | Use proxy URL for iframe |

## Why Not HTTPS?

HTTPS would also solve the secure context issue, but requires:
- SSL certificates (self-signed or CA-signed)
- Certificate management and renewal
- Browser warnings for self-signed certs
- More complex nginx/reverse proxy setup

The localhost proxy approach is simpler and works without certificates because localhost is inherently trusted as a secure context.

## Known Limitations

### WebSocket Chat Inside OpenClaw

The OpenClaw UI loads successfully in the iframe, but the internal chat WebSocket shows "disconnected". This is because:

1. OpenClaw's JavaScript calculates WebSocket URL from `window.location.origin` → `ws://localhost:3003/`
2. The root WebSocket proxy (`@sock.route('/')`) receives the connection
3. Connection proxies to `ws://192.168.0.168:18789` but frame handling has issues

**Current Status:**
- ✅ Iframe loads (secure context fix works)
- ✅ HTTP content proxies correctly
- ✅ OpenClaw UI fully visible and navigable
- ⚠️ WebSocket chat shows "disconnected (1006)"

**Workaround:** Use "Open in New Tab" to access OpenClaw directly at `http://192.168.0.168:18789` where WebSocket works natively.

**Future Fix:** The WebSocket proxy needs improved frame handling for OpenClaw's binary message protocol.

## Related Documentation

- [Reggie Master Context](/home/pds/robotics/reggie/CLAUDE.md)
- [Dev Servers](/home/pds/boomshakalaka/docs/dev-servers.md)
- [W3C Secure Contexts Spec](https://w3c.github.io/webappsec-secure-contexts/)
