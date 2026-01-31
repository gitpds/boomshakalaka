# Remote Camera Access via VPN

> **Created:** 2026-01-31
> **Status:** Working on laptop, mobile app issues pending

## Overview

Enables access to Reggie's camera when not on the local network by using a TURN server to relay WebRTC media traffic.

## The Problem

WebRTC has two types of traffic:
1. **Signaling (WebSocket)** - Works via VPN (stateful TCP)
2. **Media (UDP)** - Fails without TURN (robot can't route to VPN clients)

The robot (192.168.0.11) has no route to VPN client IPs (10.200.200.x), so return UDP packets never arrive.

## The Solution

A TURN server on the workstation relays media between VPN clients and the robot:

```
Browser (10.200.200.2)
    ↓ (via VPN)
TURN Server (192.168.0.199:3478)
    ↓ (local network)
Robot (192.168.0.11)
```

## Components

### TURN Server (coturn)

**Service:** `coturn.service`
**Config:** `/etc/turnserver.conf`

```ini
listening-port=3478
listening-ip=192.168.0.199
listening-ip=10.200.200.1
user=reggie:ReggieT0rn2026!
realm=reggie.local
min-port=49152
max-port=65535
```

**Commands:**
```bash
sudo systemctl status coturn
sudo systemctl restart coturn
tail -f /var/log/turnserver.log
```

### Camera Page ICE Config

**File:** `dashboard/templates/reggie_camera.html` (line ~507)

```javascript
iceServers: [
    { urls: 'stun:stun.l.google.com:19302' },
    {
        urls: 'turn:192.168.0.199:3478',
        username: 'reggie',
        credential: 'ReggieT0rn2026!'
    }
]
```

### WireGuard Client Config

**File:** `setup/wireguard-client.conf`

Key change: `AllowedIPs = 10.200.200.0/24, 192.168.0.0/24`

This routes robot subnet traffic through the VPN tunnel.

### Firewall Rules

```bash
# TURN port
sudo ufw allow from 10.200.200.0/24 to any port 3478
sudo ufw allow from 192.168.0.0/24 to any port 3478

# UDP relay ports
sudo ufw allow from 10.200.200.0/24 to any port 49152:65535 proto udp
sudo ufw allow from 192.168.0.0/24 to any port 49152:65535 proto udp
```

## Testing

### Run Validation Suite
```bash
cd /home/pds/boomshakalaka
python -m pytest dashboard/tests/test_remote_camera.py -v
```

### Manual Tests

1. **Local access** (baseline): Open http://localhost:3003/reggie/camera
2. **VPN access**: Connect VPN, open http://10.200.200.1:3003/reggie/camera
3. **TURN connectivity**: `nc -zv 192.168.0.199 3478`

## Known Issues

- **Mobile app**: Camera doesn't work on iOS WireGuard app (2026-01-31)
  - Laptop browser works fine
  - May be iOS-specific WebRTC/TURN handling
  - Future investigation needed

## Troubleshooting

### Camera won't connect remotely

1. Check VPN is connected: `ping 10.200.200.1`
2. Check TURN is running: `systemctl status coturn`
3. Check TURN port: `nc -zv 192.168.0.199 3478`
4. Check TURN logs: `tail -f /var/log/turnserver.log`

### TURN server not starting

```bash
# Check config syntax
turnserver -c /etc/turnserver.conf --no-loopback-peers

# Check port availability
ss -tulpn | grep 3478
```

### WireGuard routing issues

```bash
# On client, verify routes
ip route | grep 192.168.0

# On server, check forwarding
cat /proc/sys/net/ipv4/ip_forward  # should be 1
```

## Rollback

If issues occur:
1. Remove TURN from camera page (revert to STUN-only)
2. Stop coturn: `sudo systemctl stop coturn`
3. Local access will continue working
