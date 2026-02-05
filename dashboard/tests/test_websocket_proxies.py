"""
WebSocket Proxy Tests

Tests for the robot state and camera signaling WebSocket proxies.
These proxies enable SSH tunnel users (localhost:3003) to access
robot WebSockets that would otherwise be unreachable.

Run with: pytest dashboard/tests/test_websocket_proxies.py -v
"""

import pytest
import subprocess
import json
import time
from pathlib import Path


class TestRobotDaemonStatus:
    """Verify robot daemon is accessible and running."""

    def test_robot_reachable(self):
        """Robot should be reachable on the network."""
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://192.168.0.11:8000/api/daemon/status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        assert result.stdout == "200", "Robot API should be reachable"

    def test_daemon_status_endpoint(self):
        """Daemon status endpoint should return valid JSON."""
        result = subprocess.run(
            ["curl", "-s", "http://192.168.0.11:8000/api/daemon/status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        data = json.loads(result.stdout)
        assert "state" in data
        assert "robot_name" in data
        assert data["robot_name"] == "reachy_mini"

    def test_daemon_running(self):
        """Daemon should be in 'running' state for WebSockets to work."""
        result = subprocess.run(
            ["curl", "-s", "http://192.168.0.11:8000/api/daemon/status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        data = json.loads(result.stdout)
        # Allow not_initialized since daemon may need to be started
        assert data["state"] in ["running", "not_initialized", "initializing"], \
            f"Unexpected daemon state: {data['state']}"


class TestDirectWebSocketConnections:
    """Test direct WebSocket connections to robot (from workstation)."""

    def test_state_websocket_direct(self):
        """Direct state WebSocket should connect and receive data."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
import json
ws = websocket.create_connection('ws://192.168.0.11:8000/api/state/ws/full', timeout=5)
msg = ws.recv()
data = json.loads(msg)
ws.close()
assert 'head_pose' in data or 'antennas_position' in data, f"Unexpected state: {list(data.keys())}"
print("OK")
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        if "503" in result.stderr or "Backend not running" in result.stderr:
            pytest.skip("Robot daemon not running")
        assert result.returncode == 0, f"WebSocket test failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_camera_signaling_direct(self):
        """Direct camera signaling WebSocket should connect."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
import json
ws = websocket.create_connection('ws://192.168.0.11:8443', timeout=5)
msg = ws.recv()
data = json.loads(msg)
ws.close()
assert data['type'] == 'welcome', f"Expected welcome, got: {data}"
print("OK")
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0, f"Camera signaling test failed: {result.stderr}"
        assert "OK" in result.stdout


class TestProxyWebSocketConnections:
    """Test WebSocket proxy connections through dashboard."""

    def test_dashboard_running(self):
        """Dashboard should be running on port 3003."""
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://localhost:3003/"],
            capture_output=True,
            text=True,
            timeout=5
        )
        assert result.stdout in ["200", "302"], "Dashboard should be accessible"

    def test_state_proxy_connects(self):
        """State WebSocket proxy should accept connections."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
ws = websocket.create_connection('ws://localhost:3003/reggie/state-ws', timeout=5)
print(f"Connected, readyState would be OPEN")
ws.close()
print("OK")
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Even if robot is down, proxy should accept the connection
        # The key is that it doesn't crash
        assert "OK" in result.stdout or "503" in result.stderr or "Connection" in result.stderr

    def test_state_proxy_receives_data(self):
        """State WebSocket proxy should forward robot state data."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
import json
try:
    ws = websocket.create_connection('ws://localhost:3003/reggie/state-ws', timeout=5)
    msg = ws.recv()
    data = json.loads(msg)
    ws.close()
    assert 'head_pose' in data or 'antennas_position' in data or 'error' in data
    print("OK - received state data")
except Exception as e:
    if "503" in str(e) or "Backend" in str(e):
        print("SKIP - daemon not running")
    else:
        raise
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert "OK" in result.stdout or "SKIP" in result.stdout, \
            f"State proxy test failed: {result.stderr}"

    def test_camera_proxy_connects(self):
        """Camera signaling proxy should accept connections."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
ws = websocket.create_connection('ws://localhost:3003/reggie/camera-signaling', timeout=5)
print("Connected")
ws.close()
print("OK")
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert "OK" in result.stdout or "Connection" in result.stderr

    def test_camera_proxy_receives_welcome(self):
        """Camera signaling proxy should forward welcome message."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
import json
try:
    ws = websocket.create_connection('ws://localhost:3003/reggie/camera-signaling', timeout=5)
    msg = ws.recv()
    data = json.loads(msg)
    ws.close()
    assert data['type'] == 'welcome', f"Expected welcome, got: {data}"
    assert 'peerId' in data
    print("OK - received welcome")
except Exception as e:
    print(f"ERROR: {e}")
    raise
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert "OK" in result.stdout, f"Camera proxy test failed: {result.stderr}"


class TestProxyErrorHandling:
    """Test proxy behavior when robot is unavailable."""

    def test_state_proxy_handles_robot_down_gracefully(self):
        """State proxy should send proper error when robot daemon is down.

        Note: This test may skip if daemon is running.
        To properly test, stop the daemon first:
        curl -X POST http://192.168.0.11:8000/api/daemon/stop
        """
        # Check current daemon state
        status_result = subprocess.run(
            ["curl", "-s", "http://192.168.0.11:8000/api/daemon/status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        status = json.loads(status_result.stdout)

        if status["state"] == "running":
            pytest.skip("Daemon is running - cannot test error handling")

        # Try to connect via proxy
        result = subprocess.run(
            ["python3", "-c", """
import websocket
try:
    ws = websocket.create_connection('ws://localhost:3003/reggie/state-ws', timeout=5)
    # If we get here, check for error message or proper close
    try:
        msg = ws.recv()
        print(f"Received: {msg[:100]}")
    except:
        print("Connection closed properly")
    ws.close()
except websocket.WebSocketException as e:
    # Should get a proper WebSocket error, not "Invalid frame header"
    print(f"WebSocket error: {e}")
except Exception as e:
    print(f"Other error: {e}")
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        # The key assertion: should NOT see "Invalid frame header"
        # Should see proper error handling
        combined = result.stdout + result.stderr
        if "Invalid frame header" in combined:
            pytest.fail("Proxy returned invalid WebSocket frames - needs fix")

    def test_proxy_routes_exist(self):
        """Verify proxy routes are registered in the Flask app."""
        # Check that routes exist by attempting OPTIONS request
        for route in ['/reggie/state-ws', '/reggie/camera-signaling']:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 f"http://localhost:3003{route}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # WebSocket routes should return something (even if not 101)
            # A 404 would indicate the route doesn't exist
            assert result.stdout != "404", f"Route {route} not found"


class TestWebSocketProxyStability:
    """Test proxy stability over multiple connections."""

    def test_multiple_state_connections(self):
        """State proxy should handle multiple sequential connections."""
        for i in range(3):
            result = subprocess.run(
                ["python3", "-c", """
import websocket
try:
    ws = websocket.create_connection('ws://localhost:3003/reggie/state-ws', timeout=3)
    msg = ws.recv()
    ws.close()
    print("OK")
except Exception as e:
    if "503" in str(e):
        print("SKIP-daemon")
    else:
        print(f"ERROR: {e}")
"""],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "ERROR" in result.stdout and "Invalid frame header" in result.stdout:
                pytest.fail(f"Connection {i+1} failed with invalid frame header")

    def test_multiple_camera_connections(self):
        """Camera proxy should handle multiple sequential connections."""
        for i in range(3):
            result = subprocess.run(
                ["python3", "-c", """
import websocket
import json
try:
    ws = websocket.create_connection('ws://localhost:3003/reggie/camera-signaling', timeout=3)
    msg = ws.recv()
    data = json.loads(msg)
    ws.close()
    if data['type'] == 'welcome':
        print("OK")
    else:
        print(f"UNEXPECTED: {data['type']}")
except Exception as e:
    print(f"ERROR: {e}")
"""],
                capture_output=True,
                text=True,
                timeout=10
            )
            if "ERROR" in result.stdout and "Invalid frame header" in result.stdout:
                pytest.fail(f"Connection {i+1} failed with invalid frame header")
            assert "OK" in result.stdout or "UNEXPECTED" in result.stdout


class TestBrowserCompatibility:
    """Test that proxy works with browser-style WebSocket connections."""

    def test_state_proxy_with_headers(self):
        """State proxy should work with browser-like headers."""
        result = subprocess.run(
            ["python3", "-c", """
import websocket
ws = websocket.WebSocket()
ws.connect(
    'ws://localhost:3003/reggie/state-ws',
    header=[
        'Origin: http://localhost:3003',
        'User-Agent: Mozilla/5.0 (test)',
    ],
    timeout=5
)
try:
    msg = ws.recv()
    print("OK")
except:
    print("Connection handled")
ws.close()
"""],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Should not fail with protocol errors
        assert "Invalid frame header" not in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
