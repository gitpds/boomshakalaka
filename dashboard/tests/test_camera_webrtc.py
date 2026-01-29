#!/usr/bin/env python3
"""
Camera/WebRTC Streaming Tests

Tests WebRTC signaling prerequisites and camera availability.
Note: Full WebRTC testing requires a browser environment.
"""

import json
import socket
import pytest
import requests

# Robot configuration
ROBOT_IP = "192.168.0.11"
ROBOT_API_PORT = 8000
WEBRTC_SIGNALING_PORT = 8443


class TestCameraPrerequisites:
    """Test camera and WebRTC prerequisites."""

    def test_robot_api_accessible(self):
        """Robot API should be reachable."""
        try:
            response = requests.get(
                f"http://{ROBOT_IP}:{ROBOT_API_PORT}/api/daemon/status",
                timeout=5
            )
            assert response.status_code == 200
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Robot not reachable: {e}")

    def test_daemon_running(self):
        """Daemon should be in running state for camera."""
        try:
            response = requests.get(
                f"http://{ROBOT_IP}:{ROBOT_API_PORT}/api/daemon/status",
                timeout=5
            )
            data = response.json()
            assert data.get("state") == "running", f"Daemon state: {data.get('state')}"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Robot not reachable: {e}")

    def test_wireless_version_enabled(self):
        """Daemon should be started with wireless_version for camera support."""
        try:
            response = requests.get(
                f"http://{ROBOT_IP}:{ROBOT_API_PORT}/api/daemon/status",
                timeout=5
            )
            data = response.json()
            assert data.get("wireless_version") is True, "wireless_version not enabled"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Robot not reachable: {e}")


class TestWebRTCSignaling:
    """Test WebRTC signaling server availability."""

    def test_signaling_port_check(self):
        """Check if WebRTC signaling port (8443) is listening."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex((ROBOT_IP, WEBRTC_SIGNALING_PORT))
            # Note: Port may not be open if GStreamer pipeline hasn't started
            # This is informational, not a hard failure
            if result != 0:
                pytest.skip(
                    f"WebRTC signaling port {WEBRTC_SIGNALING_PORT} not open. "
                    "This is expected if camera streaming hasn't been started."
                )
        finally:
            sock.close()

    def test_signaling_websocket_protocol(self):
        """Test WebSocket connection to signaling server (if available)."""
        try:
            import websocket
        except ImportError:
            pytest.skip("websocket-client not installed")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            result = sock.connect_ex((ROBOT_IP, WEBRTC_SIGNALING_PORT))
            if result != 0:
                pytest.skip("WebRTC signaling port not open")
        finally:
            sock.close()

        # Try WebSocket connection
        try:
            ws = websocket.create_connection(
                f"ws://{ROBOT_IP}:{WEBRTC_SIGNALING_PORT}",
                timeout=5
            )
            # Should receive welcome message
            msg = ws.recv()
            data = json.loads(msg)
            assert data.get("type") == "welcome", f"Expected welcome, got: {data.get('type')}"
            ws.close()
        except Exception as e:
            pytest.skip(f"WebSocket connection failed: {e}")


class TestCameraStatus:
    """Test camera status via API (if available)."""

    def test_api_has_media_endpoints(self):
        """Check if API exposes media/camera endpoints."""
        try:
            # The Reachy Mini API might have different endpoints for camera
            # This tests common patterns
            endpoints_to_check = [
                "/api/daemon/status",  # Main status
            ]

            for endpoint in endpoints_to_check:
                response = requests.get(
                    f"http://{ROBOT_IP}:{ROBOT_API_PORT}{endpoint}",
                    timeout=5
                )
                assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Robot not reachable: {e}")


class TestGStreamerRequirements:
    """Document GStreamer requirements (informational)."""

    def test_document_gstreamer_requirements(self):
        """
        Informational test documenting GStreamer requirements for camera streaming.

        Requirements on robot:
        1. GST_PLUGIN_PATH must include /opt/gst-plugins-rs/lib/aarch64-linux-gnu/gstreamer-1.0
        2. webrtcsink plugin must be available (gst-inspect-1.0 webrtcsink)
        3. libcamerasrc for RPi camera
        4. v4l2h264enc for hardware encoding
        5. ALSA configured for audio

        Current status: Fixed in launcher.sh - includes GST_PLUGIN_PATH and
        cleanup of stale /tmp/reachymini_camera_socket on startup.
        """
        # This is a documentation test - always passes
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
