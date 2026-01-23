# Reggie Dashboard Quick Reference

## URLs

| Page | URL |
|------|-----|
| Overview | http://localhost:3003/reggie |
| Control | http://localhost:3003/reggie/control |
| Camera | http://localhost:3003/reggie/camera |
| Moves | http://localhost:3003/reggie/moves |
| Apps | http://localhost:3003/reggie/apps |
| Settings | http://localhost:3003/reggie/settings |

## Robot Addresses

| Service | Address |
|---------|---------|
| Robot API | http://192.168.0.11:8000 |
| Camera WebRTC | ws://192.168.0.11:8443 |
| State WebSocket | ws://192.168.0.11:8000/api/state/ws/full |
| API Docs | http://192.168.0.11:8000/docs |

## Files

```
dashboard/templates/
├── reggie_base.html      # Shared base (nav, ReggieShared)
├── reggie.html           # Overview page
├── reggie_control.html   # Motion control
├── reggie_camera.html    # Camera feed
├── reggie_moves.html     # Move player
├── reggie_apps.html      # Apps management
└── reggie_settings.html  # Settings

dashboard/server.py       # Routes at lines 1917-1978
```

## Critical Gotchas

1. **Units:** Robot uses RADIANS, UI shows DEGREES
   ```javascript
   ReggieShared.degToRad(degrees)  // UI → Robot
   ReggieShared.radToDeg(radians)  // Robot → UI
   ```

2. **Antennas:** Array format, NOT object
   ```javascript
   // Correct
   antennas: [leftRad, rightRad]

   // WRONG
   antennas: {left: x, right: y}
   ```

3. **Daemon start/stop:** Query params, NOT JSON body
   ```
   POST /api/daemon/start?wake_up=true
   ```

4. **Move/goto:** Requires `duration` field (default: 0.5s)

## Common API Calls (via proxy)

```bash
# Health check
curl http://localhost:3003/api/reggie/health

# Daemon status
curl http://localhost:3003/api/reggie/status

# Start daemon
curl -X POST http://localhost:3003/api/reggie/daemon/start \
  -H "Content-Type: application/json" \
  -d '{"wake_up": true}'

# Move robot
curl -X POST http://localhost:3003/api/reggie/move/goto \
  -H "Content-Type: application/json" \
  -d '{
    "head_pose": {"roll": 0, "pitch": 0, "yaw": 0.5},
    "body_yaw": 0,
    "antennas": [0, 0]
  }'

# Set motor mode
curl -X POST http://localhost:3003/api/reggie/motors/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enabled"}'

# Play dance
curl -X POST "http://localhost:3003/api/reggie/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-dances-library/dance_name"

# Stop move
curl -X POST http://localhost:3003/api/reggie/move/stop
```

## JavaScript Events (ReggieShared)

```javascript
// Connection changes
ReggieShared.on('connectionChange', (data) => {
    // data: { connected: bool, daemon: string }
});

// State updates (30Hz from WebSocket)
ReggieShared.on('stateUpdate', (state) => {
    // state: { headPose, bodyYaw, antennas, motorMode }
});

// Motor mode changes
ReggieShared.on('motorModeChange', (mode) => {
    // mode: 'enabled' | 'disabled' | 'gravity_compensation'
});
```

## Motor Modes

| Mode | Description |
|------|-------------|
| `enabled` | Full control, motors active |
| `disabled` | Motors off, no resistance |
| `gravity_compensation` | Float mode, counteracts gravity |

## Move Datasets

| Type | Path |
|------|------|
| Dances | `pollen-robotics/reachy-mini-dances-library` |
| Emotions | `pollen-robotics/reachy-mini-emotions-library` |

## Slider Ranges (Degrees)

| Control | Min | Max |
|---------|-----|-----|
| Head Roll | -45 | 45 |
| Head Pitch | -45 | 45 |
| Head Yaw | -90 | 90 |
| Body Yaw | -180 | 180 |
| Antennas | -90 | 90 |

## Presets (ControlPage.preset)

| Preset | Head Values |
|--------|-------------|
| `up` | pitch: -30° |
| `down` | pitch: 30° |
| `left` | yaw: -45° |
| `right` | yaw: 45° |
| `center` | all: 0° |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Device or resource busy" | Power cycle robot |
| Camera won't connect | Start daemon with streaming |
| Sliders don't move robot | Check motor mode is "enabled" |
| WebSocket disconnects | Auto-reconnects in 3 seconds |
| API calls fail | Check robot IP reachable |
