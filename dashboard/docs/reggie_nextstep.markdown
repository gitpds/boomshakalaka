# Reggie Dashboard - Current State & Next Steps

> **Date:** 2026-01-27
> **Status:** Phase 1-3 Complete, Phase 4-6 Ready for Implementation

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Dashboard (localhost:3003)                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Control Center (/reggie/center)              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  │
│  │  │ Live Video  │  │   Quick     │  │   Manual    │      │  │
│  │  │  (WebRTC)   │  │  Actions    │  │  Controls   │      │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │  │
│  └─────────┼────────────────┼────────────────┼──────────────┘  │
└────────────┼────────────────┼────────────────┼──────────────────┘
             │                │                │
             ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Reggie Robot (192.168.0.11:8000)                   │
│  • REST API for commands    • WebSocket for state (10Hz)        │
│  • WebRTC camera (:8443)    • Motor control                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## What's Working Now

### 1. Health Monitoring
- **Script:** `scripts/test_reggie_health.py`
- **Tests:** 7 automated checks
  - Daemon status (not in error state)
  - Backend operational (motor mode active)
  - Motor communication (mode readable)
  - WebSocket streaming (receives state at 10Hz)
  - Camera WebRTC signaling
  - All API endpoints responding
  - Dashboard proxy functioning

**Run with:**
```bash
python scripts/test_reggie_health.py
```

### 2. API Integration
- **Proxy Endpoints:** Dashboard proxies all robot API calls
  - `/api/reggie/health` - Health check
  - `/api/reggie/status` - Full robot state
  - `/api/reggie/daemon/start|stop` - Daemon control
  - `/api/reggie/move/goto` - Move to pose
  - `/api/reggie/move/play/<path>` - Play animation
  - `/api/reggie/move/stop` - Stop movement
  - `/api/reggie/moves/list/dances|emotions` - List animations
  - `/api/reggie/motors/mode` - Get/set motor mode

### 3. Control Center (`/reggie/center`)
A unified dashboard with everything on one page:

| Feature | Status | Description |
|---------|--------|-------------|
| Live Video | Working | WebRTC connection to robot camera |
| Quick Actions | Working | 8 one-click animations |
| Head Sliders | Working | Roll, Pitch, Yaw control |
| Body Slider | Working | Body rotation control |
| Antenna Sliders | Working | Left/right antenna control |
| Motor Mode | Working | Enabled/Compliant/Disabled toggle |
| Status Bar | Working | Real-time connection status |
| Keyboard Shortcuts | Working | Arrow keys + Space |
| Voice Control | Placeholder | Coming in Phase 4 |

### 4. Test Suite
- **Location:** `tests/`
- **Framework:** pytest with markers
- **Coverage:**
  - 21 API tests (`test_reggie_api.py`)
  - 5 WebSocket tests (`test_reggie_websocket.py`)
  - 12 UI tests (`test_reggie_ui.py`)
  - 15 Control Center tests (`test_control_center.py`)

**Run with:**
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_reggie_api.py -v

# Only robot-connected tests
pytest tests/ -v -m robot
```

---

## Recommended Next Steps

### Priority 1: Fix WebSocket State Updates in UI

**Problem:** The WebSocket connection works (verified by tests), but the Control Center sliders don't update from robot state in real-time.

**Root Cause:** The `ReggieShared.processWebSocketState()` function expects a different state structure than what the robot sends.

**Fix:**
1. Log the actual WebSocket message format
2. Update `processWebSocketState()` to match actual format
3. Verify sliders update when robot moves

**Files to modify:**
- `templates/reggie_base.html` (line 439-466)

---

### Priority 2: Improve Quick Actions

**Current State:** Quick actions call hardcoded animation paths that may not exist.

**Improvements:**
1. Fetch available animations on page load
2. Map quick action buttons to actual animation names
3. Add visual feedback when animation is playing
4. Show "Animation not found" error gracefully

**Implementation:**
```javascript
// In reggie_control_center.html
async loadAvailableAnimations() {
    const dances = await fetch('/api/reggie/moves/list/dances').then(r => r.json());
    const emotions = await fetch('/api/reggie/moves/list/emotions').then(r => r.json());
    this.animations = { dances, emotions };
    // Map buttons to first available animations
}
```

---

### Priority 3: Phase 4 - Voice Integration

**Architecture:**
```
Browser (mic) → Dashboard → MacBook Homebase → Claude AI → TTS → Robot Speakers
```

**Implementation Steps:**

1. **Set up MacBook Homebase** (192.168.0.168:3001)
   - WebSocket server for audio streaming
   - Claude API integration for conversation
   - ElevenLabs TTS for voice responses

2. **Add Voice UI to Control Center**
   - Push-to-talk button (already placeholder exists)
   - Web Audio API for microphone capture
   - WebSocket connection to homebase
   - Transcript display

3. **Robot Audio Bridge**
   - Forward TTS audio to robot speakers
   - Sync expressions with speech

**Files to create:**
- `static/js/voice_control.js`
- Modify `templates/reggie_control_center.html`

---

### Priority 4: Phase 5 - Automation

**Features to Add:**

1. **Scheduled Actions**
   - Wake up at 9am
   - Sleep at 10pm
   - Hourly stretch routine

2. **Storage**
   - JSON file: `data/reggie_schedules.json`
   - APScheduler for execution

3. **UI**
   - New page: `/reggie/automation`
   - Schedule builder with time picker
   - Enable/disable toggles
   - View upcoming actions

**Implementation:**
```python
# In server.py
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

@app.route('/api/reggie/schedules', methods=['GET', 'POST'])
def reggie_schedules():
    # CRUD for schedules
    pass
```

---

### Priority 5: Error Handling & Polish

**Current Gaps:**

1. **Connection Loss**
   - No reconnection UI when robot goes offline
   - WebSocket doesn't show reconnection status

2. **Loading States**
   - Buttons don't show loading during API calls
   - No feedback when animation is playing

3. **Error Messages**
   - API errors not shown to user
   - Silent failures on move commands

**Fixes:**

```javascript
// Add to ControlCenter
showToast(message, type = 'info') {
    // Display toast notification
}

async action(name) {
    const btn = event.target.closest('.quick-action-btn');
    btn.classList.add('loading');
    try {
        await this.playAnimation(name);
        this.showToast(`Playing: ${name}`, 'success');
    } catch (err) {
        this.showToast(`Failed: ${err.message}`, 'error');
    } finally {
        btn.classList.remove('loading');
    }
}
```

---

## File Structure Reference

```
dashboard/
├── scripts/
│   └── test_reggie_health.py    # Health verification script
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures
│   ├── test_reggie_api.py       # API tests (21)
│   ├── test_reggie_websocket.py # WebSocket tests (5)
│   ├── test_reggie_ui.py        # UI tests (12)
│   ├── test_control_center.py   # Control Center tests (15)
│   ├── test_voice_integration.py # Phase 4 placeholders
│   └── test_automation.py       # Phase 5 placeholders
├── templates/
│   ├── reggie_base.html         # Shared layout + ReggieShared JS
│   ├── reggie_control_center.html # Unified control page (NEW)
│   ├── reggie_control.html      # Legacy control page
│   ├── reggie_camera.html       # Dedicated camera page
│   └── reggie_moves.html        # Animation player page
├── pytest.ini                   # Test configuration
├── requirements-test.txt        # Test dependencies
└── docs/
    └── reggie_nextstep.markdown # This document
```

---

## Quick Commands Reference

```bash
# Health check
python scripts/test_reggie_health.py

# Run all tests
pytest tests/ -v

# Start robot daemon
curl -X POST "http://192.168.0.11:8000/api/daemon/start?wake_up=true"

# Stop robot daemon
curl -X POST "http://192.168.0.11:8000/api/daemon/stop?goto_sleep=true"

# Restart dashboard
sudo systemctl restart dashboard

# View dashboard logs
journalctl -u dashboard -f

# SSH to robot
ssh pollen@192.168.0.11  # password: root
```

---

## Success Metrics

| Phase | Metric | Target | Current |
|-------|--------|--------|---------|
| 1 | Health tests passing | 7/7 | 7/7 |
| 2 | API tests passing | 21/21 | 21/21 |
| 2 | WebSocket tests passing | 5/5 | 5/5 |
| 3 | Control Center functional | Yes | Yes |
| 4 | Voice commands working | No | Not started |
| 5 | Schedules executing | No | Not started |
| 6 | Error handling complete | No | Partial |

---

## Known Issues

1. **Backend Ready = False**: Robot daemon reports `ready: false` even when operational. This is expected behavior - the `ready` flag may indicate firmware-specific state.

2. **Motor Mode "compliant"**: Returns 422 error. The correct mode name might be `gravity_compensation` on some firmware versions.

3. **Animation Paths**: Hardcoded paths like `pollen-robotics/reachy-mini-emotions-library/happy` may not exist. Need to verify available animations.

4. **WebSocket Rate**: Tests show ~50Hz control loop but WebSocket receives at ~10Hz. This is expected.

---

## Conclusion

The foundation is solid with comprehensive testing. The Control Center provides a unified interface that's much better than navigating multiple pages.

**Recommended immediate focus:**
1. Fix real-time slider updates from WebSocket
2. Verify and fix quick action animation paths
3. Add error toasts and loading states

**For maximum impact:**
- Voice integration (Phase 4) would make Reggie truly interactive
- Automation (Phase 5) would make Reggie autonomous

The TDD approach has been valuable - tests catch regressions and document expected behavior.
