#!/usr/bin/env python3
"""
Reboot Server - A lightweight service to restart the dashboard from mobile.

Runs on port 3004 and provides a simple red button interface for restarting
the main Boomshakalaka dashboard server.

Run:
    python scripts/reboot_server.py

Then visit http://localhost:3004
"""

import os
import sys
import subprocess
import time
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Get project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Reboot Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #fff;
        }

        .container {
            text-align: center;
            max-width: 400px;
            width: 100%;
        }

        h1 {
            font-size: 1.5rem;
            margin-bottom: 10px;
            color: #e94560;
        }

        .status {
            font-size: 0.9rem;
            color: #888;
            margin-bottom: 40px;
        }

        .status.online {
            color: #4ade80;
        }

        .status.offline {
            color: #f87171;
        }

        .status.restarting {
            color: #fbbf24;
        }

        .reboot-btn {
            width: 200px;
            height: 200px;
            border-radius: 50%;
            border: none;
            background: linear-gradient(145deg, #e94560, #c23a51);
            color: white;
            font-size: 1.2rem;
            font-weight: bold;
            cursor: pointer;
            box-shadow:
                0 10px 30px rgba(233, 69, 96, 0.4),
                0 0 0 8px rgba(233, 69, 96, 0.1),
                inset 0 -5px 20px rgba(0, 0, 0, 0.2);
            transition: all 0.2s ease;
            text-transform: uppercase;
            letter-spacing: 2px;
            -webkit-tap-highlight-color: transparent;
        }

        .reboot-btn:hover {
            transform: scale(1.02);
            box-shadow:
                0 15px 40px rgba(233, 69, 96, 0.5),
                0 0 0 12px rgba(233, 69, 96, 0.15),
                inset 0 -5px 20px rgba(0, 0, 0, 0.2);
        }

        .reboot-btn:active {
            transform: scale(0.98);
            box-shadow:
                0 5px 20px rgba(233, 69, 96, 0.3),
                0 0 0 6px rgba(233, 69, 96, 0.1),
                inset 0 5px 20px rgba(0, 0, 0, 0.3);
        }

        .reboot-btn:disabled {
            background: linear-gradient(145deg, #666, #555);
            cursor: not-allowed;
            box-shadow:
                0 5px 15px rgba(0, 0, 0, 0.3),
                0 0 0 8px rgba(100, 100, 100, 0.1);
        }

        .message {
            margin-top: 30px;
            padding: 15px 20px;
            border-radius: 10px;
            font-size: 0.9rem;
            display: none;
        }

        .message.success {
            background: rgba(74, 222, 128, 0.2);
            border: 1px solid rgba(74, 222, 128, 0.3);
            color: #4ade80;
            display: block;
        }

        .message.error {
            background: rgba(248, 113, 113, 0.2);
            border: 1px solid rgba(248, 113, 113, 0.3);
            color: #f87171;
            display: block;
        }

        .message.info {
            background: rgba(251, 191, 36, 0.2);
            border: 1px solid rgba(251, 191, 36, 0.3);
            color: #fbbf24;
            display: block;
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
            vertical-align: middle;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .footer {
            margin-top: 40px;
            font-size: 0.75rem;
            color: #555;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Dashboard Control</h1>
        <p class="status" id="status">Checking status...</p>

        <button class="reboot-btn" id="rebootBtn" onclick="rebootDashboard()">
            Restart<br>Dashboard
        </button>

        <div class="message" id="message"></div>

        <p class="footer">Boomshakalaka Reboot Server</p>
    </div>

    <script>
        const statusEl = document.getElementById('status');
        const messageEl = document.getElementById('message');
        const btn = document.getElementById('rebootBtn');

        async function checkStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                if (data.dashboard_running) {
                    statusEl.textContent = 'Dashboard is running';
                    statusEl.className = 'status online';
                } else {
                    statusEl.textContent = 'Dashboard is offline';
                    statusEl.className = 'status offline';
                }
            } catch (e) {
                statusEl.textContent = 'Status check failed';
                statusEl.className = 'status offline';
            }
        }

        async function rebootDashboard() {
            if (!confirm('Restart the dashboard server?')) return;

            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span><br>Restarting...';
            statusEl.textContent = 'Restarting dashboard...';
            statusEl.className = 'status restarting';
            messageEl.className = 'message info';
            messageEl.textContent = 'Sending restart command...';

            try {
                const res = await fetch('/api/restart', { method: 'POST' });
                const data = await res.json();

                if (data.success) {
                    messageEl.className = 'message success';
                    messageEl.textContent = data.message || 'Dashboard restarted successfully!';
                } else {
                    messageEl.className = 'message error';
                    messageEl.textContent = data.error || 'Restart failed';
                }
            } catch (e) {
                messageEl.className = 'message error';
                messageEl.textContent = 'Request failed: ' + e.message;
            }

            btn.disabled = false;
            btn.innerHTML = 'Restart<br>Dashboard';

            // Refresh status after a moment
            setTimeout(checkStatus, 2000);
        }

        // Check status on load and periodically
        checkStatus();
        setInterval(checkStatus, 10000);
    </script>
</body>
</html>
"""


def get_dashboard_pids():
    """Get PIDs of running dashboard processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "dashboard.server"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = [int(pid) for pid in result.stdout.strip().split('\n') if pid]
            # Filter out our own process if it somehow matches
            pids = [p for p in pids if p != os.getpid()]
            return pids
        return []
    except Exception:
        return []


def is_dashboard_running():
    """Check if the dashboard is running."""
    return len(get_dashboard_pids()) > 0


def restart_dashboard():
    """Restart the dashboard using the control script."""
    ctl_script = os.path.join(PROJECT_ROOT, "scripts", "dashboard_ctl.py")

    try:
        result = subprocess.run(
            [sys.executable, ctl_script, "restart"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_ROOT
        )

        success = result.returncode == 0
        output = result.stdout + result.stderr

        return {
            "success": success,
            "message": "Dashboard restarted successfully" if success else "Restart may have issues",
            "output": output.strip()
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Restart command timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.route('/')
def index():
    """Serve the main reboot page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    """Return dashboard status."""
    pids = get_dashboard_pids()
    return jsonify({
        "dashboard_running": len(pids) > 0,
        "pids": pids
    })


@app.route('/api/restart', methods=['POST'])
def api_restart():
    """Restart the dashboard."""
    result = restart_dashboard()
    return jsonify(result)


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "reboot-server"})


if __name__ == '__main__':
    print("Starting Reboot Server on port 3004...")
    print("Visit http://localhost:3004 to access the reboot interface")
    app.run(host='0.0.0.0', port=3004, debug=False)
