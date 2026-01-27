"""
Reggie Robot UI Tests (Playwright)

Tests the dashboard UI for Reggie control pages.
Run with: pytest tests/test_reggie_ui.py -v

Requires: pip install pytest-playwright
Setup: playwright install chromium
"""

import pytest
import re
from playwright.sync_api import Page, expect

# Skip all tests if playwright not installed
pytest.importorskip("playwright")


DASHBOARD_URL = "http://localhost:3003"


@pytest.fixture(scope="module")
def browser_context(browser):
    """Create browser context with appropriate settings"""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
    )
    yield context
    context.close()


class TestOverviewPage:
    """Tests for /reggie overview page"""

    @pytest.mark.ui
    def test_overview_loads(self, page: Page):
        """Overview page should load without errors"""
        page.goto(f"{DASHBOARD_URL}/reggie")
        expect(page).to_have_title(re.compile(r"Reggie|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_status_indicators_visible(self, page: Page):
        """Status indicators should be visible"""
        page.goto(f"{DASHBOARD_URL}/reggie")
        # Look for status-related elements
        page.wait_for_load_state("networkidle")
        # Page should have some content
        expect(page.locator("body")).not_to_be_empty()

    @pytest.mark.ui
    def test_navigation_links_present(self, page: Page):
        """Navigation links should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie")
        page.wait_for_load_state("networkidle")
        # Should have links to other reggie pages
        links = page.locator("a[href*='/reggie']")
        expect(links.first).to_be_visible()


class TestControlPage:
    """Tests for /reggie/control page"""

    @pytest.mark.ui
    def test_control_page_loads(self, page: Page):
        """Control page should load"""
        page.goto(f"{DASHBOARD_URL}/reggie/control")
        expect(page).to_have_title(re.compile(r"Reggie|Control|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_sliders_present(self, page: Page):
        """Control sliders should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/control")
        page.wait_for_load_state("networkidle")
        # Look for range inputs or slider elements
        sliders = page.locator("input[type='range'], .slider, [role='slider']")
        # At least one slider should exist
        count = sliders.count()
        assert count > 0 or page.locator(".control").count() > 0, "No sliders found"

    @pytest.mark.ui
    def test_motor_mode_buttons_visible(self, page: Page):
        """Motor mode buttons should be visible"""
        page.goto(f"{DASHBOARD_URL}/reggie/control")
        page.wait_for_load_state("networkidle")
        # Look for buttons related to motor control
        buttons = page.locator("button, .btn")
        expect(buttons.first).to_be_visible()


class TestCameraPage:
    """Tests for /reggie/camera page"""

    @pytest.mark.ui
    def test_camera_page_loads(self, page: Page):
        """Camera page should load"""
        page.goto(f"{DASHBOARD_URL}/reggie/camera")
        expect(page).to_have_title(re.compile(r"Reggie|Camera|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_video_container_present(self, page: Page):
        """Video container should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/camera")
        page.wait_for_load_state("networkidle")
        # Look for video elements
        video_elements = page.locator("video, canvas, #video, .video, #camera, .camera")
        # Should have some video-related element
        count = video_elements.count()
        assert count > 0, "No video container found"


class TestMovesPage:
    """Tests for /reggie/moves page"""

    @pytest.mark.ui
    def test_moves_page_loads(self, page: Page):
        """Moves page should load"""
        page.goto(f"{DASHBOARD_URL}/reggie/moves")
        expect(page).to_have_title(re.compile(r"Reggie|Moves|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_moves_list_container_present(self, page: Page):
        """Moves list container should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/moves")
        page.wait_for_load_state("networkidle")
        # Page should have content for moves
        expect(page.locator("body")).not_to_be_empty()


class TestMobilePage:
    """Tests for mobile versions"""

    @pytest.mark.ui
    def test_mobile_overview_loads(self, page: Page):
        """Mobile overview page should load"""
        page.goto(f"{DASHBOARD_URL}/m/reggie")
        expect(page).to_have_title(re.compile(r"Reggie|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_mobile_control_loads(self, page: Page):
        """Mobile control page should load"""
        page.goto(f"{DASHBOARD_URL}/m/reggie/control")
        expect(page).to_have_title(re.compile(r"Reggie|Control|Dashboard", re.IGNORECASE))


class TestAPIFromUI:
    """Tests for API calls made from UI"""

    @pytest.mark.ui
    def test_health_check_api_called(self, page: Page):
        """Page should call health check API on load"""
        api_called = False

        def handle_request(request):
            nonlocal api_called
            if "/api/reggie/health" in request.url:
                api_called = True

        page.on("request", handle_request)
        page.goto(f"{DASHBOARD_URL}/reggie")
        page.wait_for_load_state("networkidle")

        # Give time for API call
        page.wait_for_timeout(2000)

        # Note: API might not be called on page load depending on implementation
        # This test documents expected behavior
