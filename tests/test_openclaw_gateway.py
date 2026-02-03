#!/usr/bin/env python3
"""
OpenClaw Gateway Validation Tests
Run from workstation to verify gateway is working correctly.
"""
import subprocess
import requests
import time
import sys

MACBOOK_IP = "192.168.0.168"
GATEWAY_PORT = 18789
GATEWAY_URL = f"http://{MACBOOK_IP}:{GATEWAY_PORT}"
DASHBOARD_HEALTH_URL = "http://localhost:3003/api/reggie/health"
SSH_ALIAS = "reggiembp"

def test_tcp_connectivity():
    """Test 1: TCP connection to gateway port"""
    print("Test 1: TCP connectivity...", end=" ")
    result = subprocess.run(
        ["nc", "-zv", "-w", "3", MACBOOK_IP, str(GATEWAY_PORT)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("PASS")
        return True
    print(f"FAIL - {result.stderr}")
    return False

def test_http_response():
    """Test 2: HTTP response from gateway"""
    print("Test 2: HTTP response...", end=" ")
    try:
        resp = requests.get(GATEWAY_URL, timeout=5)
        if resp.status_code == 200 and "<!doctype html>" in resp.text.lower():
            print("PASS")
            return True
        print(f"FAIL - Status {resp.status_code}")
        return False
    except Exception as e:
        print(f"FAIL - {e}")
        return False

def test_dashboard_health_api():
    """Test 3: Dashboard health API reports OpenClaw online"""
    print("Test 3: Dashboard health API...", end=" ")
    try:
        resp = requests.get(DASHBOARD_HEALTH_URL, timeout=5)
        data = resp.json()
        if data.get("openclaw") == True:
            print("PASS")
            return True
        print(f"FAIL - openclaw={data.get('openclaw')}")
        return False
    except Exception as e:
        print(f"FAIL - {e}")
        return False

def test_launchd_service_status():
    """Test 4: launchd service is registered"""
    print("Test 4: launchd service status...", end=" ")
    result = subprocess.run(
        ["ssh", SSH_ALIAS, "launchctl list | grep ai.openclaw.gateway"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and "ai.openclaw.gateway" in result.stdout:
        # Parse status: PID<tab>ExitCode<tab>Label
        parts = result.stdout.strip().split()
        if len(parts) >= 3:
            pid = parts[0]
            if pid != "-" and pid.isdigit():
                print(f"PASS (PID {pid})")
                return True
        print(f"FAIL - Service not running: {result.stdout.strip()}")
        return False
    print(f"FAIL - Service not found")
    return False

def test_process_listening():
    """Test 5: Node process listening on correct port"""
    print("Test 5: Process listening on port...", end=" ")
    result = subprocess.run(
        ["ssh", SSH_ALIAS, "lsof -i :18789 | grep LISTEN"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and "node" in result.stdout:
        print("PASS")
        return True
    print(f"FAIL - {result.stdout or 'No process listening'}")
    return False

def test_auto_restart():
    """Test 6: Service auto-restarts after kill"""
    print("Test 6: Auto-restart capability...", end=" ")

    # Get current PID (process is named openclaw-gateway)
    result = subprocess.run(
        ["ssh", SSH_ALIAS, "pgrep -f 'openclaw-gateway'"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("FAIL - Cannot get current PID")
        return False

    old_pid = result.stdout.strip().split()[0]

    # Kill the process
    subprocess.run(["ssh", SSH_ALIAS, f"kill -9 {old_pid}"], capture_output=True)

    # Wait for restart (ThrottleInterval is 30s, but first restart should be quick)
    print("(waiting 10s for restart)...", end=" ")
    time.sleep(10)

    # Check if new process started
    result = subprocess.run(
        ["ssh", SSH_ALIAS, "pgrep -f 'openclaw-gateway'"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        new_pid = result.stdout.strip().split()[0]
        if new_pid != old_pid:
            print(f"PASS (PID {old_pid} -> {new_pid})")
            return True
        print(f"FAIL - Same PID (process didn't restart)")
        return False
    print("FAIL - Process not restarted")
    return False

def run_all_tests():
    """Run all validation tests"""
    print("\n" + "="*50)
    print("OpenClaw Gateway Validation Tests")
    print("="*50 + "\n")

    tests = [
        test_tcp_connectivity,
        test_http_response,
        test_dashboard_health_api,
        test_launchd_service_status,
        test_process_listening,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "-"*50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("Status: ALL TESTS PASSED")
        return 0
    else:
        print("Status: SOME TESTS FAILED")
        return 1

def run_restart_test():
    """Run the auto-restart test separately (destructive)"""
    print("\n" + "="*50)
    print("OpenClaw Auto-Restart Test (Destructive)")
    print("="*50 + "\n")

    if test_auto_restart():
        print("\nAuto-restart: WORKING")
        return 0
    else:
        print("\nAuto-restart: FAILED")
        return 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restart-test":
        sys.exit(run_restart_test())
    else:
        sys.exit(run_all_tests())
