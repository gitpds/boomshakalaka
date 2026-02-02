"""
Tests for Firebase authentication integration in Boomshakalaka Dashboard.

Run with: pytest dashboard/tests/test_auth.py -v
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.server import app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestAuthEndpoints:
    """Test authentication API endpoints."""

    def test_auth_me_returns_401_when_not_logged_in(self, client):
        """GET /api/auth/me should return 401 when not authenticated."""
        response = client.get('/api/auth/me')
        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Not authenticated'

    def test_auth_login_requires_token(self, client):
        """POST /api/auth/login should require a token."""
        response = client.post('/api/auth/login', json={})
        assert response.status_code == 400
        data = response.get_json()
        assert data['error'] == 'Token required'

    def test_auth_login_rejects_invalid_token(self, client):
        """POST /api/auth/login should reject invalid tokens."""
        response = client.post('/api/auth/login', json={'token': 'invalid-token'})
        assert response.status_code == 401
        data = response.get_json()
        assert data['success'] == False
        assert 'error' in data

    def test_auth_logout_succeeds(self, client):
        """POST /api/auth/logout should succeed."""
        response = client.post('/api/auth/logout')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True


class TestProtectedRoutes:
    """Test that protected routes require authentication."""

    def test_pfs_redirects_when_not_logged_in(self, client):
        """GET /pfs should redirect to login when not authenticated."""
        response = client.get('/pfs')
        assert response.status_code == 302
        assert '/login' in response.location

    def test_pfs_redirect_includes_next_url(self, client):
        """GET /pfs redirect should include next parameter."""
        response = client.get('/pfs')
        assert 'next=' in response.location


class TestPublicRoutes:
    """Test that public routes are accessible without authentication."""

    def test_home_accessible_without_auth(self, client):
        """GET / should be accessible without authentication."""
        response = client.get('/', follow_redirects=True)
        assert response.status_code == 200

    def test_login_page_accessible(self, client):
        """GET /login should be accessible."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Sign in with Google' in response.data

    def test_settings_accessible_without_auth(self, client):
        """GET /settings should be accessible (shows guest state)."""
        response = client.get('/settings')
        assert response.status_code == 200
        # Should show guest state
        assert b'Account' in response.data


class TestNavVisibility:
    """Test that navigation items are shown/hidden based on auth state."""

    def test_pfs_nav_hidden_when_not_logged_in(self, client):
        """PFS nav link should not appear when not authenticated."""
        response = client.get('/', follow_redirects=True)
        # The nav link should NOT be present (only the comment is there)
        assert b'href="/pfs"' not in response.data

    def test_login_link_shown_when_not_logged_in(self, client):
        """Login link should appear when not authenticated."""
        response = client.get('/', follow_redirects=True)
        assert b'Sign In' in response.data or b'/login' in response.data


class TestUserContext:
    """Test that user context is properly passed to templates."""

    def test_settings_shows_guest_state_when_not_logged_in(self, client):
        """Settings page should show guest state when not authenticated."""
        response = client.get('/settings')
        assert response.status_code == 200
        # Should show "not signed in" message
        assert b'not signed in' in response.data.lower() or b'Sign In' in response.data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
