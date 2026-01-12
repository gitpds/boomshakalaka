#!/usr/bin/env python3
"""
ttyd Terminal Control Script

Manages the ttyd web terminal service which provides browser-based
terminal access backed by tmux for persistent sessions.

Usage:
    python scripts/ttyd_ctl.py restart   # Restart ttyd service
    python scripts/ttyd_ctl.py status    # Check status
    python scripts/ttyd_ctl.py install   # Install service file (requires sudo)

Note: restart/start/stop/daemon-reload use passwordless sudo via:
    /etc/sudoers.d/ttyd-service
"""

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SERVICE_SOURCE = PROJECT_ROOT / 'setup' / 'ttyd.service'
SERVICE_DEST = Path('/etc/systemd/system/ttyd.service')


def check_root():
    """Check if running with root privileges."""
    return os.geteuid() == 0


def run_systemctl(*args, check=True, use_sudo=True):
    """Run a systemctl command, optionally with sudo."""
    if use_sudo:
        cmd = ['sudo', 'systemctl'] + list(args)
    else:
        cmd = ['systemctl'] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running {' '.join(cmd)}: {e.stderr}")
        raise


def install_service():
    """Install or update the ttyd service file."""
    if not check_root():
        print("Error: 'install' requires root privileges. Run with sudo.")
        return False

    if not SERVICE_SOURCE.exists():
        print(f"Error: Service file not found: {SERVICE_SOURCE}")
        return False

    print(f"Installing service file...")
    print(f"  Source: {SERVICE_SOURCE}")
    print(f"  Destination: {SERVICE_DEST}")

    # Copy service file
    shutil.copy2(SERVICE_SOURCE, SERVICE_DEST)
    os.chmod(SERVICE_DEST, 0o644)
    print("  Service file installed.")

    # Reload systemd
    print("Reloading systemd daemon...")
    run_systemctl('daemon-reload')
    print("  Daemon reloaded.")

    return True


def restart_service():
    """Restart the ttyd service."""
    print("Restarting ttyd service...")
    run_systemctl('restart', 'ttyd')
    print("  Service restarted.")

    # Show status
    return status_service()


def stop_service():
    """Stop the ttyd service."""
    print("Stopping ttyd service...")
    run_systemctl('stop', 'ttyd')
    print("  Service stopped.")
    return True


def start_service():
    """Start the ttyd service."""
    print("Starting ttyd service...")
    run_systemctl('start', 'ttyd')
    print("  Service started.")
    return status_service()


def status_service():
    """Show ttyd service status."""
    print("=== ttyd Service Status ===")

    # Check if service exists (no sudo needed for status check)
    result = run_systemctl('is-active', 'ttyd', check=False, use_sudo=False)
    status = result.stdout.strip()

    if status == 'active':
        print("Status: RUNNING")
    elif status == 'inactive':
        print("Status: STOPPED")
    elif status == 'failed':
        print("Status: FAILED")
    else:
        print(f"Status: {status}")

    # Get more details
    result = subprocess.run(
        ['systemctl', 'show', 'ttyd', '--property=MainPID,ExecStart'],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split('\n'):
        if line.startswith('MainPID='):
            pid = line.split('=')[1]
            if pid != '0':
                print(f"  PID: {pid}")

    # Check if port is listening
    try:
        result = subprocess.run(
            ['ss', '-tlnp'], capture_output=True, text=True
        )
        if ':7681' in result.stdout:
            print("  Port 7681: LISTENING")
        else:
            print("  Port 7681: NOT LISTENING")
    except FileNotFoundError:
        pass

    # Check tmux session
    try:
        result = subprocess.run(
            ['tmux', 'has-session', '-t', 'dashboard'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            # Get window count
            result = subprocess.run(
                ['tmux', 'list-windows', '-t', 'dashboard'],
                capture_output=True, text=True
            )
            window_count = len(result.stdout.strip().split('\n'))
            print(f"  Tmux session 'dashboard': ACTIVE ({window_count} windows)")
        else:
            print("  Tmux session 'dashboard': NOT FOUND")
    except FileNotFoundError:
        print("  Tmux: NOT INSTALLED")

    return status == 'active'


def deploy_service():
    """Full deployment: install service file and restart."""
    if not check_root():
        print("Error: 'deploy' requires root privileges. Run with sudo.")
        return False

    print("=== Deploying ttyd Service ===")

    if not install_service():
        return False

    print()
    return restart_service()


def main():
    parser = argparse.ArgumentParser(
        description="ttyd Terminal Control Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s restart        Restart the ttyd service
    %(prog)s status         Show service status
    %(prog)s start          Start the ttyd service
    %(prog)s stop           Stop the ttyd service
    sudo %(prog)s deploy    Install service file and restart (rare)
    sudo %(prog)s install   Install/update service file only (rare)
        """
    )
    parser.add_argument(
        "action",
        choices=["deploy", "install", "start", "stop", "restart", "status"],
        help="Action to perform"
    )

    args = parser.parse_args()

    actions = {
        "deploy": deploy_service,
        "install": install_service,
        "start": start_service,
        "stop": stop_service,
        "restart": restart_service,
        "status": status_service,
    }

    try:
        success = actions[args.action]()
        sys.exit(0 if success else 1)
    except subprocess.CalledProcessError:
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
