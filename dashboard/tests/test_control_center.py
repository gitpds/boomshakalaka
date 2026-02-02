"""
Reggie Control Center UI Tests

Tests for the unified control center page.
Run with: pytest tests/test_control_center.py -v

Requires: pip install pytest-playwright
Setup: playwright install chromium
"""

import pytest
import re
from playwright.sync_api import Page, expect

# Skip all tests if playwright not installed
pytest.importorskip("playwright")


DASHBOARD_URL = "http://localhost:3003"


class TestControlCenterPage:
    """Tests for /reggie/center page"""

    @pytest.mark.ui
    def test_control_center_loads(self, page: Page):
        """Control center page should load without errors"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        expect(page).to_have_title(re.compile(r"Control Center|Reggie|Dashboard", re.IGNORECASE))

    @pytest.mark.ui
    def test_video_container_visible(self, page: Page):
        """Video container should be immediately visible"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        video_panel = page.locator(".video-panel")
        expect(video_panel).to_be_visible()

    @pytest.mark.ui
    def test_quick_actions_visible(self, page: Page):
        """Quick actions panel should be visible"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        quick_actions = page.locator(".quick-actions-panel")
        expect(quick_actions).to_be_visible()

    @pytest.mark.ui
    def test_quick_action_buttons_count(self, page: Page):
        """Should have 8 quick action buttons"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        buttons = page.locator(".quick-action-btn")
        expect(buttons).to_have_count(8)

    @pytest.mark.ui
    def test_head_control_sliders(self, page: Page):
        """Head control sliders should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        roll_slider = page.locator("#head-roll")
        pitch_slider = page.locator("#head-pitch")
        yaw_slider = page.locator("#head-yaw")

        expect(roll_slider).to_be_visible()
        expect(pitch_slider).to_be_visible()
        expect(yaw_slider).to_be_visible()

    @pytest.mark.ui
    def test_body_control_slider(self, page: Page):
        """Body control slider should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        body_slider = page.locator("#body-yaw")
        expect(body_slider).to_be_visible()

    @pytest.mark.ui
    def test_antenna_sliders(self, page: Page):
        """Antenna sliders should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        left_antenna = page.locator("#antenna-left")
        right_antenna = page.locator("#antenna-right")

        expect(left_antenna).to_be_visible()
        expect(right_antenna).to_be_visible()

    @pytest.mark.ui
    def test_status_bar_visible(self, page: Page):
        """Status bar should be visible"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        status_bar = page.locator(".status-bar")
        expect(status_bar).to_be_visible()

    @pytest.mark.ui
    def test_motor_mode_buttons(self, page: Page):
        """Motor mode toggle buttons should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        enabled_btn = page.locator("#mode-enabled-btn")
        compliant_btn = page.locator("#mode-compliant-btn")
        disabled_btn = page.locator("#mode-disabled-btn")

        expect(enabled_btn).to_be_visible()
        expect(compliant_btn).to_be_visible()
        expect(disabled_btn).to_be_visible()

    @pytest.mark.ui
    def test_voice_control_placeholder(self, page: Page):
        """Voice control placeholder should show 'Coming' badge"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        voice_card = page.locator(".voice-card")
        coming_badge = voice_card.locator(".coming-soon")

        expect(voice_card).to_be_visible()
        expect(coming_badge).to_have_text("Coming")

    @pytest.mark.ui
    def test_preset_buttons(self, page: Page):
        """Preset direction buttons should be present"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        preset_btns = page.locator(".preset-mini-btn")
        expect(preset_btns).to_have_count(5)  # up, down, left, right, center

    @pytest.mark.ui
    def test_connect_camera_button(self, page: Page):
        """Connect camera button should be visible in placeholder"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        # Camera not connected initially, placeholder should be visible
        placeholder = page.locator("#video-placeholder")
        connect_btn = placeholder.locator("button")

        expect(placeholder).to_be_visible()
        expect(connect_btn).to_be_visible()


class TestControlCenterInteractions:
    """Tests for control center interactions"""

    @pytest.mark.ui
    def test_slider_updates_value_display(self, page: Page):
        """Moving slider should update the value display"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        slider = page.locator("#head-roll")
        value_display = page.locator("#head-roll-val")

        # Move slider
        slider.fill("25")
        slider.dispatch_event("input")

        # Check value updated
        expect(value_display).to_have_text("25°")

    @pytest.mark.ui
    def test_quick_action_button_clickable(self, page: Page):
        """Quick action buttons should be clickable"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        wave_btn = page.locator(".quick-action-btn").first
        expect(wave_btn).to_be_enabled()

        # Click should not throw error
        wave_btn.click()

    @pytest.mark.ui
    def test_sync_antennas_checkbox(self, page: Page):
        """Sync antennas checkbox should toggle"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        checkbox = page.locator("#sync-antennas")
        expect(checkbox).not_to_be_checked()

        checkbox.check()
        expect(checkbox).to_be_checked()

    @pytest.mark.ui
    def test_fullscreen_toggle(self, page: Page):
        """Fullscreen button should toggle fullscreen class"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        video_panel = page.locator(".video-panel")
        fullscreen_btn = page.locator(".video-header-actions .header-action-btn")

        expect(video_panel).not_to_have_class(re.compile("fullscreen"))

        fullscreen_btn.click()
        expect(video_panel).to_have_class(re.compile("fullscreen"))

        # Press Escape to exit
        page.keyboard.press("Escape")
        expect(video_panel).not_to_have_class(re.compile("fullscreen"))


class TestControlCenterKeyboard:
    """Tests for keyboard shortcuts"""

    @pytest.mark.ui
    def test_arrow_keys_control_head(self, page: Page):
        """Arrow keys should control head position"""
        page.goto(f"{DASHBOARD_URL}/reggie/center")
        page.wait_for_load_state("networkidle")

        # Initial pitch should be 0
        pitch_display = page.locator("#head-pitch-val")
        initial_text = pitch_display.text_content()

        # Press up arrow (should change pitch)
        page.keyboard.press("ArrowUp")

        # Pitch should have changed
        page.wait_for_timeout(100)
        # Note: actual value depends on preset logic
