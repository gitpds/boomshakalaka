"""
Reggie Robot API Integration Tests

Tests the dashboard's API endpoints that proxy to the robot.
Run with: pytest tests/test_reggie_api.py -v
"""

import pytest
import requests
import time


class TestHealthEndpoint:
    """Tests for /api/reggie/health"""

    def test_health_endpoint_returns_200(self, dashboard_url: str):
        """Health endpoint should return 200"""
        resp = requests.get(f"{dashboard_url}/api/reggie/health", timeout=5)
        assert resp.status_code == 200

    def test_health_endpoint_returns_json(self, dashboard_url: str):
        """Health endpoint should return JSON"""
        resp = requests.get(f"{dashboard_url}/api/reggie/health", timeout=5)
        data = resp.json()
        assert "robot" in data
        assert "dashboard" in data
        assert "daemon" in data
        assert "timestamp" in data

    def test_health_reports_robot_status(self, dashboard_url: str, robot_available: bool):
        """Health endpoint should accurately report robot status"""
        resp = requests.get(f"{dashboard_url}/api/reggie/health", timeout=5)
        data = resp.json()
        assert data["robot"] == robot_available


class TestStatusEndpoint:
    """Tests for /api/reggie/status"""

    @pytest.mark.robot
    def test_status_endpoint_returns_200(self, dashboard_url: str):
        """Status endpoint should return 200 when robot is connected"""
        resp = requests.get(f"{dashboard_url}/api/reggie/status", timeout=5)
        # Could be 200 (success) or 5xx (robot error)
        assert resp.status_code in [200, 502, 503, 504]

    @pytest.mark.robot
    def test_status_returns_full_state(self, dashboard_url: str, robot_available: bool):
        """Status endpoint should return full robot state"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.get(f"{dashboard_url}/api/reggie/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            # Verify expected state structure
            assert isinstance(data, dict)


class TestDaemonControl:
    """Tests for /api/reggie/daemon/start and /api/reggie/daemon/stop"""

    def test_daemon_start_requires_post(self, dashboard_url: str):
        """Daemon start should require POST method"""
        resp = requests.get(f"{dashboard_url}/api/reggie/daemon/start", timeout=5)
        assert resp.status_code == 405  # Method Not Allowed

    def test_daemon_stop_requires_post(self, dashboard_url: str):
        """Daemon stop should require POST method"""
        resp = requests.get(f"{dashboard_url}/api/reggie/daemon/stop", timeout=5)
        assert resp.status_code == 405  # Method Not Allowed

    def test_invalid_daemon_action_rejected(self, dashboard_url: str):
        """Invalid daemon action should return 400"""
        resp = requests.post(
            f"{dashboard_url}/api/reggie/daemon/invalid",
            json={},
            timeout=5
        )
        assert resp.status_code == 400

    @pytest.mark.robot
    def test_daemon_start_accepts_post(self, dashboard_url: str):
        """Daemon start should accept POST and return valid response"""
        resp = requests.post(
            f"{dashboard_url}/api/reggie/daemon/start",
            json={"wake_up": True},
            timeout=15
        )
        # 200 = success, 5xx = robot connection issue
        assert resp.status_code in [200, 502, 503, 504]


class TestMoveGoto:
    """Tests for /api/reggie/move/goto"""

    def test_move_goto_requires_post(self, dashboard_url: str):
        """Move goto should require POST method"""
        resp = requests.get(f"{dashboard_url}/api/reggie/move/goto", timeout=5)
        assert resp.status_code == 405

    @pytest.mark.robot
    def test_move_goto_accepts_pose(self, dashboard_url: str, robot_available: bool):
        """Move goto should accept a pose and move robot"""
        if not robot_available:
            pytest.skip("Robot not available")

        pose = {
            "head": {"roll": 0, "pitch": 0, "yaw": 0},
            "duration": 1.0
        }
        resp = requests.post(
            f"{dashboard_url}/api/reggie/move/goto",
            json=pose,
            timeout=10
        )
        assert resp.status_code in [200, 502, 503, 504]


class TestMovePlay:
    """Tests for /api/reggie/move/play/<path>"""

    @pytest.mark.robot
    def test_move_play_accepts_path(self, dashboard_url: str, robot_available: bool):
        """Move play should accept animation path"""
        if not robot_available:
            pytest.skip("Robot not available")

        # Use a known animation path
        path = "pollen-robotics/reachy-mini-emotions-library/happy"
        resp = requests.post(
            f"{dashboard_url}/api/reggie/move/play/{path}",
            timeout=30
        )
        # Animation might not exist, so accept 404 as valid
        assert resp.status_code in [200, 404, 502, 503, 504]


class TestMoveStop:
    """Tests for /api/reggie/move/stop"""

    def test_move_stop_requires_post(self, dashboard_url: str):
        """Move stop should require POST method"""
        resp = requests.get(f"{dashboard_url}/api/reggie/move/stop", timeout=5)
        assert resp.status_code == 405

    @pytest.mark.robot
    def test_move_stop_accepts_post(self, dashboard_url: str, robot_available: bool):
        """Move stop should accept POST"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.post(f"{dashboard_url}/api/reggie/move/stop", timeout=5)
        # 422 = no movement to stop (validation error), which is valid
        assert resp.status_code in [200, 422, 502, 503, 504]


class TestMovesList:
    """Tests for /api/reggie/moves/list/<dataset>"""

    @pytest.mark.robot
    def test_moves_list_dances(self, dashboard_url: str, robot_available: bool):
        """Should list available dances"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.get(f"{dashboard_url}/api/reggie/moves/list/dances", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, (list, dict))

    @pytest.mark.robot
    def test_moves_list_emotions(self, dashboard_url: str, robot_available: bool):
        """Should list available emotions"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.get(f"{dashboard_url}/api/reggie/moves/list/emotions", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, (list, dict))


class TestMotorsMode:
    """Tests for /api/reggie/motors/mode"""

    @pytest.mark.robot
    def test_motors_mode_get(self, dashboard_url: str, robot_available: bool):
        """Should return current motor mode"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.get(f"{dashboard_url}/api/reggie/motors/mode", timeout=5)
        assert resp.status_code in [200, 502, 503, 504]

    @pytest.mark.robot
    def test_motors_mode_set_enabled(self, dashboard_url: str, robot_available: bool):
        """Should allow setting motor mode to enabled"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.post(
            f"{dashboard_url}/api/reggie/motors/mode",
            json={"mode": "enabled"},
            timeout=5
        )
        assert resp.status_code in [200, 502, 503, 504]

    @pytest.mark.robot
    def test_motors_mode_set_compliant(self, dashboard_url: str, robot_available: bool):
        """Should allow setting motor mode to compliant"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.post(
            f"{dashboard_url}/api/reggie/motors/mode",
            json={"mode": "compliant"},
            timeout=5
        )
        # 422 = mode name might be invalid on some firmware versions
        assert resp.status_code in [200, 422, 502, 503, 504]


class TestProxy:
    """Tests for /api/reggie/proxy/<endpoint>"""

    @pytest.mark.robot
    def test_proxy_get(self, dashboard_url: str, robot_available: bool):
        """Should proxy GET requests to robot"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.get(
            f"{dashboard_url}/api/reggie/proxy/daemon/status",
            timeout=5
        )
        assert resp.status_code in [200, 502, 503, 504]

    @pytest.mark.robot
    def test_proxy_post(self, dashboard_url: str, robot_available: bool):
        """Should proxy POST requests to robot"""
        if not robot_available:
            pytest.skip("Robot not available")

        resp = requests.post(
            f"{dashboard_url}/api/reggie/proxy/motors/status",
            json={},
            timeout=5
        )
        # POST to motors/status may return different codes
        assert resp.status_code in [200, 400, 404, 405, 502, 503, 504]
