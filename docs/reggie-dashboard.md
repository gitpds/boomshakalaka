# Reggie Multi-Page Dashboard Documentation

**Last Updated:** 2026-01-22
**Implementation Date:** 2026-01-22

## Overview

The Reggie dashboard is a web-based control interface for the Reachy Mini robot ("Reggie"). It provides real-time control, monitoring, and management capabilities through a multi-page structure.

### Robot Details
- **Name:** Reggie (Reachy Mini)
- **Robot IP:** 192.168.0.11
- **API Port:** 8000
- **Camera Port:** 8443 (WebRTC via GStreamer)
- **WebSocket:** ws://192.168.0.11:8000/api/state/ws/full
- **SSH:** `ssh reggie` (key-based auth, user: pollen)

### MacBook ("Reggie's Brain")
- **IP:** 192.168.0.168
- **SSH:** `ssh reggiembp` (key-based auth, user: reggie)
- **Homebase Dashboard:** http://192.168.0.168:3008
- **Homebase API:** http://192.168.0.168:3001
- **Code Location:** `~/Reggie/reggie-homebase/`

---

## Architecture

### File Structure

```
dashboard/
├── templates/
│   ├── base.html              # Main site base template
│   ├── reggie_base.html       # Reggie-specific base with sub-navigation
│   ├── reggie.html            # Overview page
│   ├── reggie_control.html    # Motion control page
│   ├── reggie_camera.html     # Camera feed page
│   ├── reggie_moves.html      # Move player page
│   ├── reggie_apps.html       # Apps management page
│   └── reggie_settings.html   # Settings/diagnostics page
└── server.py                  # Flask routes and API proxy
```

### Template Hierarchy

```
base.html
└── reggie_base.html (extends base.html)
    ├── reggie.html (Overview)
    ├── reggie_control.html (Control)
    ├── reggie_camera.html (Camera)
    ├── reggie_moves.html (Moves)
    ├── reggie_apps.html (Apps)
    └── reggie_settings.html (Settings)
```

### URL Routes

| Route | Function | Template | Description |
|-------|----------|----------|-------------|
| `/reggie` | `reggie()` | reggie.html | Overview/landing page |
| `/reggie/control` | `reggie_control()` | reggie_control.html | Motion controls |
| `/reggie/camera` | `reggie_camera()` | reggie_camera.html | Camera feed |
| `/reggie/moves` | `reggie_moves()` | reggie_moves.html | Move player |
| `/reggie/apps` | `reggie_apps()` | reggie_apps.html | Apps management |
| `/reggie/settings` | `reggie_settings()` | reggie_settings.html | Settings |

---

## Shared Components (reggie_base.html)

### ReggieShared JavaScript Object

The `ReggieShared` object provides shared state management and utilities across all Reggie pages.

```javascript
const ReggieShared = {
    robotUrl: 'http://192.168.0.11:8000',
    ws: null,                    // WebSocket connection
    wsReconnectTimer: null,      // Auto-reconnect timer
    cameraConnected: false,      // Camera status flag

    state: {
        connected: false,        // Robot API reachable
        daemonRunning: false,    // Daemon state
        motorMode: 'disabled',   // Current motor mode
        headPose: { roll: 0, pitch: 0, yaw: 0 },  // In degrees
        bodyYaw: 0,              // In degrees
        antennas: [0, 0]         // [left, right] in degrees
    },

    // Event system
    listeners: {
        connectionChange: [],    // Robot connection changes
        stateUpdate: [],         // WebSocket state updates
        motorModeChange: []      // Motor mode changes
    }
};
```

### Key Methods

| Method | Description |
|--------|-------------|
| `ReggieShared.init()` | Initialize connection, start health checks |
| `ReggieShared.checkHealth()` | Check robot API status |
| `ReggieShared.connectWebSocket()` | Connect to state WebSocket |
| `ReggieShared.sendPose(pose)` | Send movement command |
| `ReggieShared.toggleDaemon()` | Start/stop daemon |
| `ReggieShared.setMotorMode(mode)` | Set motor mode |
| `ReggieShared.playAnimation(name)` | Play built-in animation |
| `ReggieShared.radToDeg(rad)` | Convert radians to degrees |
| `ReggieShared.degToRad(deg)` | Convert degrees to radians |
| `ReggieShared.on(event, callback)` | Subscribe to events |
| `ReggieShared.emit(event, data)` | Emit events |

### Sub-Navigation

The reggie_base.html provides a horizontal sub-navigation bar with:
- Links to all 6 Reggie pages
- Active page highlighting
- Status indicators (Robot, WebSocket, Camera)

```html
<div class="reggie-nav">
    <a href="/reggie" class="reggie-nav-item active">Overview</a>
    <a href="/reggie/control" class="reggie-nav-item">Control</a>
    <!-- ... -->
    <div class="reggie-nav-status">
        <div class="status-item">
            <span class="status-dot" id="robot-dot"></span>
            <span class="status-label">Robot</span>
        </div>
        <!-- ... -->
    </div>
</div>
```

---

## Page Details

### 1. Overview Page (`/reggie`)

**File:** `reggie.html`

**Purpose:** Landing page with quick status overview and navigation to other sections.

**Features:**
- Robot connection status (connected, daemon state, motor mode, WebSocket)
- Network info (IP, ports)
- Quick action buttons (Power toggle, Wake Up, Sleep, Emergency Stop)
- Mini camera preview with WebRTC
- Navigation cards to all other pages

**JavaScript Objects:**
- `CameraPreview` - Minimal WebRTC client for thumbnail preview
- `OverviewPage` - Page controller

**Key Elements:**
```html
<div id="conn-status">          <!-- Connection status text -->
<div id="daemon-status">        <!-- Daemon state -->
<div id="motor-mode">           <!-- Current motor mode -->
<div id="ws-status">            <!-- WebSocket status -->
<button id="power-btn">         <!-- Daemon toggle button -->
<video id="camera-video">       <!-- Camera preview -->
```

---

### 2. Motion Control Page (`/reggie/control`)

**File:** `reggie_control.html`

**Purpose:** Full motion control interface for head, body, and antennas.

**Features:**
- Head pose sliders (Roll: ±45°, Pitch: ±45°, Yaw: ±90°)
- Body yaw slider (±180°) with visual indicator
- Antenna sliders (Left/Right: ±90°) with sync option
- Motor mode selector (Enabled, Disabled, Gravity Compensation)
- Quick presets (Up, Down, Left, Right, Center)
- Real-time state display from WebSocket

**JavaScript Object:** `ControlPage`

**Key Methods:**
```javascript
ControlPage.setupSliders()      // Initialize slider event handlers
ControlPage.sendPose()          // Send current slider values to robot
ControlPage.preset(direction)   // Apply preset (up/down/left/right/center)
ControlPage.setMotorMode(mode)  // Change motor mode
```

**Slider Behavior:**
- Updates display value on input
- Debounced API calls (50ms)
- User dragging flag prevents WebSocket overwrites
- Synced antennas option

---

### 3. Camera Page (`/reggie/camera`)

**File:** `reggie_camera.html`

**Purpose:** Full-screen WebRTC video feed from robot camera.

**Features:**
- Large video player with WebRTC stream
- Fullscreen toggle
- Screenshot button (downloads PNG)
- Stream info panel (status, resolution, producer)
- Requirements checklist (robot, daemon, streaming)
- Disconnect button

**JavaScript Object:** `CameraPage`

**WebRTC Flow:**
1. Create RTCPeerConnection with STUN server
2. Add video/audio transceivers (recvonly)
3. Connect to signaling WebSocket (ws://192.168.0.11:8443)
4. Send `setPeerStatus` with role "listener"
5. Request producer list
6. Find producer with meta.name === 'reachymini'
7. Start session with producer
8. Exchange SDP offer/answer
9. Exchange ICE candidates
10. Receive video track, attach to <video> element

**Key Methods:**
```javascript
CameraPage.connect()            // Start WebRTC connection
CameraPage.disconnect()         // End session and cleanup
CameraPage.toggleFullscreen()   // Toggle fullscreen mode
CameraPage.screenshot()         // Capture and download frame
```

---

### 4. Moves Page (`/reggie/moves`)

**File:** `reggie_moves.html`

**Purpose:** Play recorded dances and emotions.

**Features:**
- Dataset tabs (Dances, Emotions)
- Move grid with icons
- Now Playing card with play/stop controls
- Quick Play (Wake Up, Sleep animations)
- Recently played list (persisted to localStorage)
- Move dataset info

**JavaScript Object:** `MovesPage`

**Datasets:**
| Dataset | Path |
|---------|------|
| Dances | `pollen-robotics/reachy-mini-dances-library` |
| Emotions | `pollen-robotics/reachy-mini-emotions-library` |

**API Calls:**
```javascript
// List moves
GET /api/reggie/moves/list/dances
GET /api/reggie/moves/list/emotions

// Play move
POST /api/reggie/move/play/recorded-move-dataset/{dataset_path}/{move_name}

// Stop playback
POST /api/reggie/move/stop
```

**Local Storage:**
- Key: `reggie-recent-moves`
- Value: Array of `{name, dataset, time}` objects (max 10)

---

### 5. Apps Page (`/reggie/apps`)

**File:** `reggie_apps.html`

**Purpose:** Manage Hugging Face apps on the robot.

**Features:**
- Current running app display
- Apps grid with status indicators
- App details panel
- Start/Stop controls
- Auto-refresh every 10 seconds

**JavaScript Object:** `AppsPage`

**API Calls:**
```javascript
// List available apps
GET /api/reggie/proxy/apps/list-available

// Get current app status
GET /api/reggie/proxy/apps/current-app-status

// Start app
POST /api/reggie/proxy/apps/start-app/{app_name}

// Stop current app
POST /api/reggie/proxy/apps/stop-current-app
```

**App Icons:** Determined by name patterns (voice→🎤, vision→👁️, chat→💬, etc.)

---

### 6. Settings Page (`/reggie/settings`)

**File:** `reggie_settings.html`

**Purpose:** Configuration, diagnostics, and system controls.

**Features:**
- Volume controls (Speaker, Microphone) with test sound
- Network info (IPs, ports, WebSocket URL)
- API reference (common endpoints)
- Daemon control (Start/Stop/Restart with animation options)
- Motor status display
- Diagnostics (API latency, WS state, last update)
- External links (Robot API docs, MacBook dashboard)

**JavaScript Object:** `SettingsPage`

**Volume API:**
```javascript
// Get speaker volume
GET /api/reggie/proxy/volume/current

// Set speaker volume
POST /api/reggie/proxy/volume/set?volume={0-100}

// Get microphone volume
GET /api/reggie/proxy/volume/microphone/current

// Set microphone volume
POST /api/reggie/proxy/volume/microphone/set?volume={0-100}

// Test sound
POST /api/reggie/proxy/volume/test-sound
```

---

## Server-Side API Proxy (server.py)

The Flask server proxies requests to the robot API to handle CORS and provide error handling.

### Configuration

```python
REGGIE_ROBOT_URL = 'http://192.168.0.11:8000'
REGGIE_DASHBOARD_URL = 'http://192.168.0.168:3008'  # Optional MacBook dashboard
```

### Proxy Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/reggie/health` | GET | Check robot and dashboard health |
| `/api/reggie/status` | GET | Get full robot state |
| `/api/reggie/daemon/<action>` | POST | Start/stop daemon |
| `/api/reggie/move/goto` | POST | Move to pose |
| `/api/reggie/move/play/<path>` | POST | Play animation/move |
| `/api/reggie/move/stop` | POST | Stop current movement |
| `/api/reggie/moves/list/<dataset>` | GET | List available moves |
| `/api/reggie/motors/mode` | GET/POST | Get/set motor mode |
| `/api/reggie/proxy/<path>` | GET/POST | Generic proxy to robot API |

### Daemon Control Details

```python
# Start daemon (query params, not JSON body!)
POST /api/reggie/daemon/start
→ Robot: POST /api/daemon/start?wake_up=true

# Stop daemon
POST /api/reggie/daemon/stop
→ Robot: POST /api/daemon/stop?goto_sleep=true
```

### Move/Goto Details

```python
# The robot API requires a duration field
POST /api/reggie/move/goto
Body: {
    "head_pose": {"x": 0, "y": 0, "z": 0, "roll": rad, "pitch": rad, "yaw": rad},
    "body_yaw": rad,
    "antennas": [left_rad, right_rad],
    "duration": 0.5  # Added automatically if missing
}
```

---

## Technical Notes

### Unit Conversions

**CRITICAL:** The robot API uses **radians**, the UI displays **degrees**.

```javascript
// Conversion functions in ReggieShared
radToDeg(rad) { return rad * (180 / Math.PI); }
degToRad(deg) { return deg * (Math.PI / 180); }
```

### Antenna Format

**CRITICAL:** Robot expects array `[left, right]`, NOT object `{left, right}`.

```javascript
// Correct
antennas: [leftRadians, rightRadians]

// Wrong - will fail!
antennas: {left: leftRadians, right: rightRadians}
```

### Daemon Start/Stop

**CRITICAL:** Uses query parameters, NOT JSON body.

```python
# Correct
POST /api/daemon/start?wake_up=true

# Wrong - robot ignores this
POST /api/daemon/start
Body: {"wake_up": true}
```

### WebSocket State Format

The WebSocket at `/api/state/ws/full` sends JSON at ~30Hz:

```json
{
    "head_pose": {
        "roll": 0.0,      // radians
        "pitch": 0.0,     // radians
        "yaw": 0.0        // radians
    },
    "body_yaw": 0.0,      // radians
    "antennas_position": [0.0, 0.0],  // [left, right] in radians
    "control_mode": "enabled"  // enabled|disabled|gravity_compensation
}
```

### WebRTC Camera Signaling

The camera uses GStreamer's WebRTC signaling server on port 8443.

**Protocol:**
1. Connect to `ws://192.168.0.11:8443`
2. Receive `welcome` with peerId
3. Send `setPeerStatus` with roles: ["listener"]
4. Send `list` to get producers
5. Find producer with `meta.name === 'reachymini'`
6. Send `startSession` with producer's peerId
7. Receive `sessionStarted` with sessionId
8. Receive `peer` with SDP offer
9. Send `peer` with SDP answer
10. Exchange ICE candidates via `peer` messages

---

## CSS Styling

### CSS Variables Used

The dashboard uses CSS variables from the main theme:

```css
--bg-primary      /* Primary background */
--bg-secondary    /* Card background */
--bg-tertiary     /* Header background */
--border-color    /* Borders */
--text-primary    /* Main text */
--text-secondary  /* Secondary text */
--text-muted      /* Muted text */
--accent          /* Accent color (cyan) */
--success         /* Success green */
--error           /* Error red */
--warning         /* Warning orange */
```

### Common Classes

```css
.reggie-card           /* Card container */
.reggie-card-header    /* Card header with icon */
.reggie-card-body      /* Card content area */
.reggie-card-badge     /* Status badge in header */
.reggie-btn            /* Button base */
.reggie-btn-primary    /* Primary accent button */
.reggie-btn-sm         /* Small button */
.reggie-slider-row     /* Slider with label and value */
.reggie-slider-value   /* Slider value display */
.reggie-grid           /* Grid container */
.reggie-grid-2/3/4     /* 2/3/4 column grids */
```

---

## Extending the Dashboard

### Adding a New Page

1. Create template `reggie_newpage.html`:
```html
{% extends "reggie_base.html" %}

{% block reggie_content %}
<!-- Your content here -->
{% endblock %}

{% block reggie_scripts %}
<script>
const NewPage = {
    init() {
        // Subscribe to shared events
        ReggieShared.on('stateUpdate', (state) => {
            // Handle state updates
        });
    }
};

document.addEventListener('DOMContentLoaded', () => {
    NewPage.init();
});
</script>
{% endblock %}
```

2. Add route in `server.py`:
```python
@app.route('/reggie/newpage')
def reggie_newpage():
    return render_template('reggie_newpage.html',
                         active_page='reggie',
                         reggie_page='newpage',
                         page_name='New Page',
                         **get_common_context())
```

3. Add nav link in `reggie_base.html`:
```html
<a href="{{ url_for('reggie_newpage') }}"
   class="reggie-nav-item {% if reggie_page == 'newpage' %}active{% endif %}">
    <svg>...</svg>
    <span>New Page</span>
</a>
```

### Adding New API Endpoints

For robot API endpoints not covered by the generic proxy:

```python
@app.route('/api/reggie/custom/endpoint', methods=['POST'])
def api_reggie_custom():
    try:
        data = request.get_json() or {}
        # Transform data if needed
        resp = requests.post(f'{REGGIE_ROBOT_URL}/api/custom/endpoint',
                           json=data, timeout=10)
        return jsonify(resp.json()), resp.status_code
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503
```

---

## Troubleshooting

### Robot Not Connecting

1. Check robot is powered on
2. Verify IP: `ping 192.168.0.11`
3. Check API: `curl http://192.168.0.11:8000/api/daemon/status`
4. If "Device or resource busy" error, power cycle the robot

### Camera Not Working

1. Daemon must be running with streaming enabled
2. Check signaling: `wscat -c ws://192.168.0.11:8443`
3. Look for 'reachymini' producer in list
4. Browser must support WebRTC

### WebSocket Disconnecting

1. Robot may be overloaded - reduce polling frequency
2. Check network stability
3. WebSocket auto-reconnects after 3 seconds

### Sliders Not Updating Robot

1. Check motor mode is "enabled"
2. Verify daemon is running
3. Check browser console for API errors
4. Ensure values are being converted to radians

---

## Version History

| Date | Changes |
|------|---------|
| 2026-01-22 | Initial multi-page implementation |
| | - Split single page into 6 pages |
| | - Created reggie_base.html shared template |
| | - Added ReggieShared state management |
| | - Implemented sub-navigation |

---

---

## SSH Access

SSH access to all Reggie systems is configured for autonomous operation using the `automation_key`.

### SSH Configuration (`~/.ssh/config`)

```
Host reggiembp reggie-brain
    HostName 192.168.0.168
    User reggie
    IdentityFile ~/.ssh/automation_key
    IdentitiesOnly yes
    StrictHostKeyChecking no

Host reggie reggie-robot
    HostName 192.168.0.11
    User pollen
    IdentityFile ~/.ssh/automation_key
    IdentitiesOnly yes
    StrictHostKeyChecking no

Host dofbot
    HostName 192.168.0.52
    User jetson
    IdentityFile ~/.ssh/jetson_key
    IdentitiesOnly yes
```

### Common SSH Commands

```bash
# Robot commands
ssh reggie 'hostname'                                    # Test connection
ssh reggie 'systemctl status reachy-mini-daemon'        # Check daemon
ssh reggie 'sudo systemctl restart reachy-mini-daemon'  # Restart daemon
ssh reggie 'cat ~/reggie-audio-bridge/audio_bridge.py'  # View audio bridge

# MacBook commands
ssh reggiembp 'hostname'                                 # Test connection
ssh reggiembp 'ls ~/Reggie/reggie-homebase/'            # List homebase files
ssh reggiembp 'cd ~/Reggie/reggie-homebase && npm run dev'  # Start frontend

# Robot custom code
ssh reggie 'cat ~/reggie-audio-bridge/.env'             # Audio bridge config
```

### Network Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Boomshakalaka Server (206.55.184.182 / localhost)          │
│  - Main Dashboard: port 3003                                │
│  - Proxies to Reggie Robot API                              │
└───────────────────────┬─────────────────────────────────────┘
                        │ SSH / HTTP
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Reggie Robot  │ │ Reggie Brain  │ │ DofBot Arm    │
│ 192.168.0.11  │ │ 192.168.0.168 │ │ 192.168.0.52  │
│ User: pollen  │ │ User: reggie  │ │ User: jetson  │
│               │ │ (MacBook Pro) │ │               │
│ - Robot API   │ │ - ~/Reggie/   │ │ - Robotics    │
│   port 8000   │ │   homebase    │ │   control     │
│ - Camera 8443 │ │   port 3008   │ │               │
│ - Audio Bridge│ │ - API 3001    │ │               │
└───────────────┘ └───────────────┘ └───────────────┘
```

---

## MacBook Homebase (`~/Reggie/reggie-homebase/`)

The MacBook runs a React/TypeScript homebase application that handles:
- Twilio SMS/voice webhooks
- Robot audio bridge via WebSocket
- Memory/conversation management
- Real-time diagnostics

### Key Files

| File | Purpose |
|------|---------|
| `server/src/index.ts` | Express server with WebSocket support |
| `src/App.tsx` | Main React application |
| `src/pages/*.tsx` | Dashboard, Settings, Chat, Camera, etc. |
| `src/services/*.ts` | Robot API, audio, TTS, memory services |
| `CLAUDE.md` | Claude memory file with quick commands |

### Starting Homebase Services

```bash
# Terminal 1: Backend (port 3001)
ssh reggiembp 'cd ~/Reggie/reggie-homebase/server && npm run dev'

# Terminal 2: Frontend (port 3008)
ssh reggiembp 'cd ~/Reggie/reggie-homebase && npm run dev'

# Terminal 3: ngrok (for Twilio webhooks)
ssh reggiembp 'ngrok http 3001 --domain=uncontrovertedly-dynastic-imelda.ngrok-free.dev'
```

---

## Related Files

- `/home/pds/boomshakalaka/dashboard/server.py` - Flask server with routes
- `/home/pds/boomshakalaka/dashboard/templates/base.html` - Main site template
- `/home/pds/boomshakalaka/dashboard/static/styles.css` - Global styles
- `/home/pds/boomshakalaka/dashboard/static/app.js` - Global JavaScript
- `/home/pds/.ssh/config` - SSH host configuration
- `/home/pds/.ssh/automation_key` - Passphrase-less SSH key for automation
