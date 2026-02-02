#!/usr/bin/env python3
"""
Remote Camera Access Tests

Validates that all components are in place for remote camera access via VPN.
"""
import socket
import subprocess
import pytest
import requests

WORKSTATION_IP = "192.168.0.199"
WORKSTATION_VPN_IP = "10.200.200.1"
ROBOT_IP = "192.168.0.11"
TURN_PORT = 3478
WEBRTC_PORT = 8443


class TestLocalBaseline:
    """Verify local access still works (no regression)."""

    def test_robot_api_reachable(self):
        """Robot API should be accessible from workstation."""
        try:
            r = requests.get(f"http://{ROBOT_IP}:8000/api/daemon/status", timeout=5)
            assert r.status_code == 200
        except requests.RequestException as e:
            pytest.skip(f"Robot not reachable: {e}")

    def test_webrtc_signaling_reachable(self):
        """WebRTC signaling port should be open."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex((ROBOT_IP, WEBRTC_PORT))
            if result != 0:
                pytest.skip(f"Robot port {WEBRTC_PORT} not open (robot may be off)")
        finally:
            sock.close()

    def test_dashboard_health(self):
        """Dashboard should report healthy."""
        r = requests.get("http://localhost:3003/api/reggie/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        # daemon may not be running, just check endpoint works
        assert "daemon" in data


class TestTurnServer:
    """Verify TURN server is configured and running."""

    def test_coturn_service_running(self):
        """coturn service should be active."""
        result = subprocess.run(
            ["systemctl", "is-active", "coturn"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "active", "coturn not running"

    def test_turn_port_listening_local(self):
        """TURN server should be listening on port 3478 (local IP)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex((WORKSTATION_IP, TURN_PORT))
            assert result == 0, f"TURN port {TURN_PORT} not listening on {WORKSTATION_IP}"
        finally:
            sock.close()

    def test_turn_port_listening_vpn(self):
        """TURN should also listen on VPN interface."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            result = sock.connect_ex((WORKSTATION_VPN_IP, TURN_PORT))
            assert result == 0, f"TURN not listening on VPN IP {WORKSTATION_VPN_IP}"
        finally:
            sock.close()


class TestWireGuardConfig:
    """Verify WireGuard is configured for robot subnet."""

    def test_wireguard_running(self):
        """WireGuard interface should be up."""
        result = subprocess.run(
            ["ip", "link", "show", "wg0"],
            capture_output=True, text=True
        )
        assert "state UP" in result.stdout or "state UNKNOWN" in result.stdout

    def test_ip_forwarding_enabled(self):
        """IP forwarding should be enabled."""
        with open("/proc/sys/net/ipv4/ip_forward") as f:
            value = f.read().strip()
        assert value == "1", "IP forwarding not enabled"

    def test_client_config_includes_robot_subnet(self):
        """Client config should route robot subnet."""
        with open("/home/pds/boomshakalaka/setup/wireguard-client.conf") as f:
            content = f.read()
        assert "192.168.0.0/24" in content, "Robot subnet not in AllowedIPs"


class TestFirewall:
    """Verify firewall allows necessary traffic."""

    def test_turn_port_allowed(self):
        """UFW should allow TURN port."""
        result = subprocess.run(
            ["sudo", "ufw", "status"],
            capture_output=True, text=True
        )
        # Check for 3478 in output
        assert "3478" in result.stdout, "TURN port 3478 not in firewall rules"


class TestCameraPageConfig:
    """Verify camera page has TURN server configured."""

    def test_ice_servers_include_turn(self):
        """Camera page should have TURN server in ICE config."""
        with open("/home/pds/boomshakalaka/dashboard/templates/reggie_camera.html") as f:
            content = f.read()
        assert "turn:" in content.lower(), "No TURN server in ICE config"
        assert "192.168.0.199:3478" in content, "TURN server IP not configured"

    def test_turn_credentials_present(self):
        """Camera page should have TURN credentials."""
        with open("/home/pds/boomshakalaka/dashboard/templates/reggie_camera.html") as f:
            content = f.read()
        assert "username:" in content, "TURN username not configured"
        assert "credential:" in content, "TURN credential not configured"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
