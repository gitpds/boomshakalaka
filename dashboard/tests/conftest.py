"""
Pytest configuration and shared fixtures for dashboard tests.
"""

import pytest
import requests
from typing import Generator

# Configuration
ROBOT_URL = "http://192.168.0.11:8000"
DASHBOARD_URL = "http://localhost:3003"
WS_URL = "ws://192.168.0.11:8000/api/state/ws/full"


@pytest.fixture(scope="session")
def robot_url() -> str:
    """Return the robot API URL"""
    return ROBOT_URL


@pytest.fixture(scope="session")
def dashboard_url() -> str:
    """Return the dashboard URL"""
    return DASHBOARD_URL


@pytest.fixture(scope="session")
def ws_url() -> str:
    """Return the WebSocket URL"""
    return WS_URL


@pytest.fixture(scope="session")
def robot_available() -> bool:
    """Check if robot is available"""
    try:
        resp = requests.get(f"{ROBOT_URL}/api/daemon/status", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def dashboard_available() -> bool:
    """Check if dashboard is available"""
    try:
        resp = requests.get(DASHBOARD_URL, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture
def robot_session(robot_url: str) -> Generator[requests.Session, None, None]:
    """Provide a requests session configured for robot API"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    yield session
    session.close()


@pytest.fixture
def dashboard_session(dashboard_url: str) -> Generator[requests.Session, None, None]:
    """Provide a requests session configured for dashboard API"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    yield session
    session.close()


def pytest_configure(config):
    """Add custom markers"""
    config.addinivalue_line(
        "markers", "robot: tests that require robot connection"
    )
    config.addinivalue_line(
        "markers", "dashboard: tests that require dashboard running"
    )
    config.addinivalue_line(
        "markers", "websocket: tests that use WebSocket connections"
    )
    config.addinivalue_line(
        "markers", "ui: tests that use Playwright for UI testing"
    )
