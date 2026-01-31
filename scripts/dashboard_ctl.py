#!/usr/bin/env python3
"""
Dashboard Control Script

A safe management script for the Boomshakalaka dashboard.
This script provides controlled operations that can be executed
without requiring elevated permissions or dangerous shell commands.

Usage:
    python scripts/dashboard_ctl.py restart
    python scripts/dashboard_ctl.py status
    python scripts/dashboard_ctl.py stop
"""

import os
import sys
import signal
import subprocess
import time
import argparse


def get_dashboard_pids():
    """Get PIDs of running dashboard processes."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "dashboard.server"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return [int(pid) for pid in result.stdout.strip().split('\n') if pid]
        return []
    except Exception as e:
        print(f"Error getting PIDs: {e}")
        return []


def stop_dashboard():
    """Stop the dashboard by sending SIGTERM to processes."""
    pids = get_dashboard_pids()
    if not pids:
        print("No dashboard processes found.")
        return True

    print(f"Stopping dashboard processes: {pids}")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            print(f"  PID {pid} already terminated")
        except PermissionError:
            print(f"  Permission denied for PID {pid}")
            return False

    # Wait for processes to terminate
    for _ in range(10):
        time.sleep(0.5)
        remaining = get_dashboard_pids()
        if not remaining:
            print("All dashboard processes stopped.")
            return True

    print(f"Warning: Some processes still running: {get_dashboard_pids()}")
    return False


def start_dashboard():
    """Start the dashboard server."""
    # Check if already running
    pids = get_dashboard_pids()
    if pids:
        print(f"Dashboard already running with PIDs: {pids}")
        return False

    # Start the dashboard
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("Starting dashboard...")
    process = subprocess.Popen(
        [sys.executable, "-m", "dashboard.server"],
        cwd=project_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True  # Detach from parent
    )

    # Wait a moment and check if it started
    time.sleep(2)
    pids = get_dashboard_pids()
    if pids:
        print(f"Dashboard started with PID(s): {pids}")
        return True
    else:
        print("Failed to start dashboard.")
        return False


def is_systemd_managed():
    """Check if dashboard is managed by systemd."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "polymarket-dashboard.service"],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() in ("active", "activating", "inactive")
    except FileNotFoundError:
        return False


def restart_dashboard():
    """Restart the dashboard (stop then start)."""
    print("=== Restarting Dashboard ===")

    # Check if managed by systemd or other supervisor
    will_respawn = is_systemd_managed()
    if will_respawn:
        print("Dashboard appears to be managed by a process supervisor.")
        print("Stopping process - supervisor will auto-respawn with new code...")

    # Stop the dashboard
    stop_dashboard()
    time.sleep(1)

    if will_respawn:
        # Poll for respawn
        print("Waiting for respawn...")
        for i in range(10):
            time.sleep(1)
            pids = get_dashboard_pids()
            if pids:
                print(f"Respawned with PID(s): {pids}")
                break
            print(f"  Waiting... ({i+1}/10)")
    else:
        # Manual start
        start_dashboard()

    return status_dashboard()


def status_dashboard():
    """Show dashboard status."""
    pids = get_dashboard_pids()

    if not pids:
        print("Dashboard: NOT RUNNING")
        return False

    print("Dashboard: RUNNING")
    print(f"  PIDs: {pids}")

    # Try to check if responding
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:3003/api/themes", timeout=5) as response:
            if response.status == 200:
                print("  HTTP: Responding on port 3003")
    except Exception as e:
        print(f"  HTTP: Not responding ({e})")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Dashboard Control Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s status     Show dashboard status
    %(prog)s restart    Restart the dashboard
    %(prog)s stop       Stop the dashboard
    %(prog)s start      Start the dashboard
        """
    )
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status"],
        help="Action to perform"
    )

    args = parser.parse_args()

    actions = {
        "start": start_dashboard,
        "stop": stop_dashboard,
        "restart": restart_dashboard,
        "status": status_dashboard,
    }

    success = actions[args.action]()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
