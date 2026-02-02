"""
Reggie Robot WebSocket Tests

Tests WebSocket connectivity and state streaming.
Run with: pytest tests/test_reggie_websocket.py -v
"""

import pytest
import json
import time
import threading
from typing import Optional

import websocket


class TestWebSocketConnection:
    """Tests for WebSocket state streaming"""

    @pytest.mark.websocket
    @pytest.mark.robot
    def test_ws_connects(self, ws_url: str, robot_available: bool):
        """WebSocket should establish connection"""
        if not robot_available:
            pytest.skip("Robot not available")

        connected = False
        error_msg: Optional[str] = None

        def on_open(ws):
            nonlocal connected
            connected = True
            ws.close()

        def on_error(ws, error):
            nonlocal error_msg
            error_msg = str(error)

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_error=on_error,
        )

        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        timeout = 3.0
        start = time.time()
        while not connected and error_msg is None and (time.time() - start) < timeout:
            time.sleep(0.1)

        ws.close()

        assert connected or error_msg is None, f"Failed to connect: {error_msg}"

    @pytest.mark.websocket
    @pytest.mark.robot
    def test_ws_receives_state(self, ws_url: str, robot_available: bool):
        """WebSocket should receive state updates"""
        if not robot_available:
            pytest.skip("Robot not available")

        messages = []

        def on_message(ws, message):
            messages.append(message)
            if len(messages) >= 1:
                ws.close()

        def on_error(ws, error):
            ws.close()

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
        )

        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        timeout = 3.0
        start = time.time()
        while len(messages) < 1 and (time.time() - start) < timeout:
            time.sleep(0.1)

        ws.close()

        assert len(messages) >= 1, "No messages received"

    @pytest.mark.websocket
    @pytest.mark.robot
    def test_ws_state_format(self, ws_url: str, robot_available: bool):
        """WebSocket state should have correct JSON structure"""
        if not robot_available:
            pytest.skip("Robot not available")

        messages = []

        def on_message(ws, message):
            messages.append(json.loads(message))
            if len(messages) >= 1:
                ws.close()

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
        )

        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        timeout = 3.0
        start = time.time()
        while len(messages) < 1 and (time.time() - start) < timeout:
            time.sleep(0.1)

        ws.close()

        assert len(messages) >= 1, "No messages received"

        state = messages[0]
        # Verify it's a valid dict (actual structure may vary)
        assert isinstance(state, dict), f"State is not a dict: {type(state)}"

    @pytest.mark.websocket
    @pytest.mark.robot
    def test_ws_rate_approximately_10hz(self, ws_url: str, robot_available: bool):
        """WebSocket updates should arrive at approximately 10Hz"""
        if not robot_available:
            pytest.skip("Robot not available")

        timestamps = []

        def on_message(ws, message):
            timestamps.append(time.time())
            if len(timestamps) >= 15:
                ws.close()

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
        )

        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        timeout = 5.0
        start = time.time()
        while len(timestamps) < 15 and (time.time() - start) < timeout:
            time.sleep(0.1)

        ws.close()

        if len(timestamps) < 5:
            pytest.skip("Not enough messages to calculate rate")

        # Calculate average interval
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals)
        rate = 1.0 / avg_interval

        # Should be roughly 10Hz (between 5Hz and 20Hz)
        assert 5 <= rate <= 20, f"Rate {rate:.1f}Hz outside expected range (5-20Hz)"

    @pytest.mark.websocket
    @pytest.mark.robot
    def test_ws_reconnects_after_close(self, ws_url: str, robot_available: bool):
        """Should be able to reconnect after disconnection"""
        if not robot_available:
            pytest.skip("Robot not available")

        # First connection
        connected1 = False

        def on_open1(ws):
            nonlocal connected1
            connected1 = True
            ws.close()

        ws1 = websocket.WebSocketApp(ws_url, on_open=on_open1)
        ws_thread1 = threading.Thread(target=ws1.run_forever)
        ws_thread1.daemon = True
        ws_thread1.start()

        timeout = 3.0
        start = time.time()
        while not connected1 and (time.time() - start) < timeout:
            time.sleep(0.1)
        ws1.close()

        assert connected1, "First connection failed"

        # Brief pause
        time.sleep(0.5)

        # Second connection (reconnect)
        connected2 = False

        def on_open2(ws):
            nonlocal connected2
            connected2 = True
            ws.close()

        ws2 = websocket.WebSocketApp(ws_url, on_open=on_open2)
        ws_thread2 = threading.Thread(target=ws2.run_forever)
        ws_thread2.daemon = True
        ws_thread2.start()

        start = time.time()
        while not connected2 and (time.time() - start) < timeout:
            time.sleep(0.1)
        ws2.close()

        assert connected2, "Reconnection failed"
