# Reggie Camera Streaming Configuration

> **Last Updated:** 2026-02-04
> **Status:** WORKING - Do not modify without reading this entire document

---

## Overview

Reggie's camera uses **WebRTC** for real-time video streaming from the robot to the browser. The signaling is handled by **GStreamer's webrtcsink** plugin running on the robot.

**Key files:**
- `dashboard/templates/reggie_camera.html` - Dedicated camera page
- `dashboard/templates/reggie_control.html` - Control page with embedded camera
- `dashboard/server.py` - WebSocket proxy for signaling (`/reggie/camera-signaling`)

---

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────────┐     WebSocket      ┌─────────────┐
│   Browser   │◄──────────────────►│   Dashboard     │◄──────────────────►│   Robot     │
│  (WebRTC)   │   localhost:3003   │  (Flask Proxy)  │   192.168.0.11:8443│  (GStreamer)│
└─────────────┘                    └─────────────────┘                    └─────────────┘
      │                                                                          │
      │                         WebRTC Media (UDP)                               │
      └──────────────────────────────────────────────────────────────────────────┘
```

### Connection Modes

1. **Proxy Mode** (SSH tunnel via localhost:3003)
   - Browser connects to `ws://localhost:3003/reggie/camera-signaling`
   - Dashboard proxies to `ws://192.168.0.11:8443`
   - Required for secure context (WebRTC needs HTTPS or localhost)

2. **Direct Mode** (LAN/VPN access)
   - Browser connects directly to `ws://192.168.0.11:8443`
   - Lower latency, but only works on local network

---

## GStreamer webrtcsink Signaling Protocol

### CRITICAL: Message Format

The robot uses GStreamer's webrtcsink which has a **specific JSON message format**. Getting this wrong will crash the daemon.

#### Message Types (Browser → Robot)

```javascript
// 1. Set peer status (after welcome)
{ "type": "setPeerStatus", "roles": ["listener"], "meta": {} }

// 2. Request producer list
{ "type": "list" }

// 3. Start session with a producer
{ "type": "startSession", "peerId": "<producer-id>" }

// 4. Send SDP Answer - MUST USE NESTED FORMAT
{
    "type": "peer",
    "sessionId": "<session-id>",
    "sdp": {
        "type": "answer",           // ← REQUIRED: tells robot this is an answer
        "sdp": "v=0\r\no=- ..."     // ← The actual SDP string
    }
}

// 5. Send ICE Candidate
{
    "type": "peer",
    "sessionId": "<session-id>",
    "ice": {
        "candidate": "candidate:...",
        "sdpMLineIndex": 0,
        "sdpMid": "0"
    }
}

// 6. End session
{ "type": "endSession", "sessionId": "<session-id>" }
```

#### Message Types (Robot → Browser)

```javascript
// 1. Welcome (sent on connect)
{ "type": "welcome" }

// 2. Peer status changed
{ "type": "peerStatusChanged", ... }

// 3. Producer list
{ "type": "list", "producers": [{ "id": "...", "meta": { "name": "reachymini" } }] }

// 4. Session started
{ "type": "sessionStarted", "sessionId": "<uuid>" }

// 5. SDP Offer
{
    "type": "peer",
    "sdp": {
        "type": "offer",
        "sdp": "v=0\r\no=- ..."
    }
}

// 6. ICE Candidate
{
    "type": "peer",
    "ice": {
        "candidate": "candidate:...",
        "sdpMLineIndex": 0,
        "sdpMid": "0"
    }
}
```

---

## The Crash Bug and Workaround

### The Problem

The robot's GStreamer signaling server has a bug that causes it to crash approximately **200ms after receiving the SDP answer**. This manifests as:

1. Browser console: `WebSocket connection failed: Invalid frame header`
2. Robot daemon crashes and restarts
3. Video disconnects

### Root Cause Analysis (2026-02-04)

After extensive debugging with OpenAI o3, we identified that:
- The crash occurs in GStreamer's JSON parser
- It happens after processing the SDP answer, during response generation
- The exact trigger is unclear, but it's related to internal state corruption

### The Workaround

Since the crash happens **after** ICE negotiation completes, the video stream is already established when the signaling server crashes. The workaround is:

```javascript
// In ws.onerror and ws.onclose handlers:
const iceState = this.pc?.iceConnectionState;
if (iceState === 'connected' || iceState === 'completed') {
    console.log('Signaling crashed after ICE connected - video still working');
    this.ws = null;  // Clear reference but DON'T cleanup video
    return;          // Don't tear down the connection
}
```

This allows the video to continue playing even though the signaling WebSocket died.

---

## Connection Flow

```
Browser                          Dashboard Proxy                    Robot
   │                                   │                              │
   │──── WS Connect ──────────────────►│                              │
   │                                   │──── WS Connect ─────────────►│
   │                                   │◄─── welcome ─────────────────│
   │◄─── welcome ──────────────────────│                              │
   │                                   │                              │
   │──── setPeerStatus ───────────────►│──── setPeerStatus ──────────►│
   │──── list ────────────────────────►│──── list ───────────────────►│
   │                                   │◄─── list (producers) ────────│
   │◄─── list (producers) ─────────────│                              │
   │                                   │                              │
   │──── startSession ────────────────►│──── startSession ───────────►│
   │                                   │◄─── sessionStarted ──────────│
   │◄─── sessionStarted ───────────────│                              │
   │                                   │                              │
   │                                   │◄─── peer (SDP offer) ────────│
   │◄─── peer (SDP offer) ─────────────│                              │
   │                                   │                              │
   │  [Browser creates answer]         │                              │
   │                                   │                              │
   │──── peer (SDP answer) ───────────►│──── peer (SDP answer) ──────►│
   │                                   │                              │
   │◄───────────────── ICE candidates exchanged ─────────────────────►│
   │                                   │                              │
   │◄═══════════════════ WebRTC Media Stream (UDP) ══════════════════►│
   │                                   │                              │
   │                                   │    [~200ms later: CRASH]     │
   │                                   │◄─── WS Close (1006) ─────────│
   │◄─── WS Close ─────────────────────│                              │
   │                                   │                              │
   │  [Workaround: ignore WS close     │                              │
   │   if ICE is connected]            │                              │
   │                                   │                              │
   │◄═══════════════════ Video continues playing ════════════════════►│
```

---

## Debugging Guide

### Check Daemon Status
```bash
curl -s http://192.168.0.11:8000/api/daemon/status | jq '{state, version}'
```

### Check Signaling Port
```bash
nc -zv 192.168.0.11 8443
```

### Enable Motors (if controls don't work)
```bash
curl -X POST "http://192.168.0.11:8000/api/motors/set_mode/enabled"
```

### Wake Up Robot
```bash
curl -X POST "http://192.168.0.11:8000/api/move/play/wake_up"
```

### Restart Daemon
```bash
curl -X POST "http://192.168.0.11:8000/api/daemon/restart"
# Or via SSH:
ssh pollen@192.168.0.11 "sudo systemctl restart reachy-mini-daemon"
```

### Browser Console Indicators

**Good connection:**
```
[Control] WebSocket OPEN
[Control] Message type: welcome
[Control] Message type: list
[Control] Message type: sessionStarted
[Control] Session started: <uuid>
[Control] Message type: peer  (multiple times)
[Control] Received track: video
[Control] Received track: audio
[Control] RTCPeerConnection state: connecting
[Control] RTCPeerConnection state: connected  ← SUCCESS
```

**Crash with workaround working:**
```
[Control] RTCPeerConnection state: connected
WebSocket connection failed: Invalid frame header  ← Daemon crashed
[Control] Signaling closed after ICE connected - video still working  ← Workaround
```

**Failed connection:**
```
[Control] Message type: error
[Control] Signaling error: Failed to connect to camera server
```

---

## Common Issues and Fixes

### 1. Black Screen (Connection Established)

**Symptoms:** Camera shows "Live" but video is black

**Causes:**
- Motors disabled (robot head not powered)
- Camera physically covered/obstructed
- Codec mismatch

**Fix:**
```bash
# Enable motors
curl -X POST "http://192.168.0.11:8000/api/motors/set_mode/enabled"
# Wake up robot
curl -X POST "http://192.168.0.11:8000/api/move/play/wake_up"
```

### 2. "Invalid Frame Header" Followed by Disconnect

**Symptoms:** Video connects briefly then disconnects with "Invalid frame header"

**Cause:** Robot daemon crashed, workaround not in place

**Fix:** Ensure the workaround code is present in both `reggie_camera.html` and `reggie_control.html`:
```javascript
// In ws.onerror and ws.onclose:
const iceState = this.pc?.iceConnectionState;
if (iceState === 'connected' || iceState === 'completed') {
    console.log('Signaling crashed after ICE connected - video still working');
    this.ws = null;
    return;  // Don't cleanup!
}
```

### 3. "Camera Not Available (timeout)"

**Symptoms:** Camera page shows timeout after 5 seconds

**Cause:** Robot's GStreamer pipeline not streaming

**Fix:**
```bash
# Restart daemon with streaming
curl -X POST "http://192.168.0.11:8000/api/daemon/restart"
# Wait 5 seconds, then try again
```

### 4. Controls Not Working

**Symptoms:** Sliders move but robot doesn't respond

**Cause:** Motors disabled

**Fix:**
```bash
curl -X POST "http://192.168.0.11:8000/api/motors/set_mode/enabled"
```

### 5. Connection Refused

**Symptoms:** Proxy error "Connection refused"

**Cause:** Robot daemon not running

**Fix:**
```bash
curl -X POST "http://192.168.0.11:8000/api/daemon/start?wake_up=true"
# Or restart via systemd
ssh pollen@192.168.0.11 "sudo systemctl restart reachy-mini-daemon"
```

---

## ICE/TURN Configuration

For remote access via VPN, the browser uses a TURN server to relay media:

```javascript
this.pc = new RTCPeerConnection({
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        {
            urls: 'turn:192.168.0.199:3478',
            username: 'reggie',
            credential: 'ReggieT0rn2026!'
        }
    ]
});
```

The TURN server runs on the workstation (192.168.0.199) and relays UDP traffic for VPN clients who can't receive direct UDP from the robot.

---

## Code Locations

### SDP Answer Sending (CRITICAL)
- `reggie_camera.html`: Lines ~836-850
- `reggie_control.html`: Lines ~934-950

**MUST use nested format:**
```javascript
this.sendMessage({
    type: 'peer',
    sessionId: this.sessionId,
    sdp: {
        type: 'answer',  // ← DO NOT REMOVE
        sdp: answer.sdp
    }
});
```

### Crash Workaround Locations
- `reggie_camera.html`: `ws.onerror`, `ws.onclose`, `case 'error'`
- `reggie_control.html`: `ws.onerror`, `ws.onclose`, `case 'error'`

### WebSocket Proxy
- `server.py`: `/reggie/camera-signaling` route

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-02-04 | Fixed crash by adding workaround for post-ICE signaling crash | Claude |
| 2026-02-04 | Confirmed nested SDP format required (flat format breaks ICE) | Claude |
| 2026-01-31 | Added TURN server for VPN access | Claude |
| 2026-02-01 | Added camera signaling proxy for SSH tunnel support | Claude |

---

## Testing Checklist

Before marking camera work as "done", verify:

- [ ] Camera connects from localhost (SSH tunnel)
- [ ] Camera connects from LAN (direct IP)
- [ ] Video displays (not black)
- [ ] Controls work (motors respond)
- [ ] Connection survives signaling crash (workaround works)
- [ ] Reconnection works after disconnect
- [ ] Page visibility change cleanup works (no FD leak)

---

## Emergency Recovery

If everything is broken:

```bash
# 1. Restart robot daemon
ssh pollen@192.168.0.11 "sudo systemctl restart reachy-mini-daemon"

# 2. Wait for startup
sleep 10

# 3. Enable motors
curl -X POST "http://192.168.0.11:8000/api/motors/set_mode/enabled"

# 4. Wake up
curl -X POST "http://192.168.0.11:8000/api/move/play/wake_up"

# 5. Restart dashboard
sudo systemctl restart dashboard

# 6. Clear browser cache and refresh
```

If still broken, check that the SDP format in the HTML files matches this document exactly.
