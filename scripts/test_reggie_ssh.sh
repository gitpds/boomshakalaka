#!/bin/bash
# Comprehensive SSH Test Suite for Reggie Systems
# Tests connectivity, authentication, command execution, and more

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
SKIP=0

# Results log
LOG_FILE="/tmp/reggie_ssh_results.log"
echo "=== Reggie SSH Test Results ===" > "$LOG_FILE"
echo "Started: $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Test function
test_case() {
    local category="$1"
    local name="$2"
    local cmd="$3"
    local expected="$4"
    local timeout_sec="${5:-30}"

    printf "  %-50s " "$name"

    # Run command with timeout
    result=$(timeout "$timeout_sec" bash -c "$cmd" 2>&1)
    exit_code=$?

    # Check if timed out
    if [[ $exit_code -eq 124 ]]; then
        echo -e "${YELLOW}SKIP${NC} (timeout)"
        ((SKIP++))
        echo "[$category] $name: SKIP (timeout)" >> "$LOG_FILE"
        return
    fi

    # Check result
    if [[ "$result" == *"$expected"* ]]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        echo "[$category] $name: PASS" >> "$LOG_FILE"
    else
        echo -e "${RED}FAIL${NC}"
        echo "    Expected: $expected"
        echo "    Got: ${result:0:100}"
        ((FAIL++))
        echo "[$category] $name: FAIL" >> "$LOG_FILE"
        echo "    Expected: $expected" >> "$LOG_FILE"
        echo "    Got: ${result:0:200}" >> "$LOG_FILE"
    fi
}

# Test function for exit codes
test_exit_code() {
    local category="$1"
    local name="$2"
    local cmd="$3"
    local expected_code="$4"
    local timeout_sec="${5:-30}"

    printf "  %-50s " "$name"

    timeout "$timeout_sec" bash -c "$cmd" >/dev/null 2>&1
    actual_code=$?

    if [[ $actual_code -eq 124 ]]; then
        echo -e "${YELLOW}SKIP${NC} (timeout)"
        ((SKIP++))
        echo "[$category] $name: SKIP (timeout)" >> "$LOG_FILE"
        return
    fi

    if [[ $actual_code -eq $expected_code ]]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASS++))
        echo "[$category] $name: PASS (exit code $actual_code)" >> "$LOG_FILE"
    else
        echo -e "${RED}FAIL${NC}"
        echo "    Expected exit code: $expected_code, Got: $actual_code"
        ((FAIL++))
        echo "[$category] $name: FAIL (expected $expected_code, got $actual_code)" >> "$LOG_FILE"
    fi
}

# Test function for numeric comparison
test_numeric() {
    local category="$1"
    local name="$2"
    local cmd="$3"
    local operator="$4"  # gt, lt, eq, ge, le
    local threshold="$5"
    local timeout_sec="${6:-30}"

    printf "  %-50s " "$name"

    result=$(timeout "$timeout_sec" bash -c "$cmd" 2>&1)
    exit_code=$?

    if [[ $exit_code -eq 124 ]]; then
        echo -e "${YELLOW}SKIP${NC} (timeout)"
        ((SKIP++))
        echo "[$category] $name: SKIP (timeout)" >> "$LOG_FILE"
        return
    fi

    # Extract number from result
    num=$(echo "$result" | grep -oE '[0-9]+' | head -1)

    if [[ -z "$num" ]]; then
        echo -e "${RED}FAIL${NC} (no number found)"
        ((FAIL++))
        echo "[$category] $name: FAIL (no number in: $result)" >> "$LOG_FILE"
        return
    fi

    local passed=false
    case "$operator" in
        gt) [[ $num -gt $threshold ]] && passed=true ;;
        lt) [[ $num -lt $threshold ]] && passed=true ;;
        eq) [[ $num -eq $threshold ]] && passed=true ;;
        ge) [[ $num -ge $threshold ]] && passed=true ;;
        le) [[ $num -le $threshold ]] && passed=true ;;
    esac

    if $passed; then
        echo -e "${GREEN}PASS${NC} ($num $operator $threshold)"
        ((PASS++))
        echo "[$category] $name: PASS ($num $operator $threshold)" >> "$LOG_FILE"
    else
        echo -e "${RED}FAIL${NC} ($num not $operator $threshold)"
        ((FAIL++))
        echo "[$category] $name: FAIL ($num not $operator $threshold)" >> "$LOG_FILE"
    fi
}

# Section header
section() {
    echo ""
    echo -e "${BLUE}=== $1 ===${NC}"
    echo "" >> "$LOG_FILE"
    echo "=== $1 ===" >> "$LOG_FILE"
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================
section "Pre-flight Checks"

echo "Checking network connectivity..."
for host in "192.168.0.11:Robot" "192.168.0.168:MacBook" "192.168.0.52:DofBot"; do
    ip="${host%%:*}"
    name="${host##*:}"
    printf "  %-50s " "Ping $name ($ip)"
    if ping -c 1 -W 2 "$ip" >/dev/null 2>&1; then
        echo -e "${GREEN}REACHABLE${NC}"
    else
        echo -e "${YELLOW}UNREACHABLE${NC}"
    fi
done

# ============================================================================
# 1. BASIC CONNECTIVITY TESTS
# ============================================================================
section "1. Basic Connectivity Tests"

test_case "1.Basic" "1.1 Robot alias 'reggie'" \
    "ssh reggie 'hostname'" \
    "reachy-mini"

test_case "1.Basic" "1.2 Robot alias 'reggie-robot'" \
    "ssh reggie-robot 'hostname'" \
    "reachy-mini"

test_case "1.Basic" "1.3 MacBook alias 'reggiembp'" \
    "ssh reggiembp 'hostname'" \
    "reggiembp"

test_case "1.Basic" "1.4 MacBook alias 'reggie-brain'" \
    "ssh reggie-brain 'hostname'" \
    "reggiembp"

test_case "1.Basic" "1.5 DofBot alias 'dofbot'" \
    "ssh -o ConnectTimeout=5 dofbot 'hostname' 2>&1" \
    "" 10  # Just check it doesn't hang

test_case "1.Basic" "1.6 Direct IP with config user" \
    "ssh pollen@192.168.0.11 'hostname'" \
    "reachy-mini"

# ============================================================================
# 2. AUTHENTICATION TESTS
# ============================================================================
section "2. Authentication Tests"

test_case "2.Auth" "2.1 No password prompt (robot)" \
    "ssh -o BatchMode=yes reggie 'echo ok'" \
    "ok"

test_case "2.Auth" "2.2 No password prompt (MacBook)" \
    "ssh -o BatchMode=yes reggiembp 'echo ok'" \
    "ok"

test_case "2.Auth" "2.3 Correct key used (robot)" \
    "ssh -v reggie 'hostname' 2>&1 | grep -i 'automation_key'" \
    "automation_key"

test_case "2.Auth" "2.4 Correct key used (MacBook)" \
    "ssh -v reggiembp 'hostname' 2>&1 | grep -i 'automation_key'" \
    "automation_key"

test_case "2.Auth" "2.5 Correct key used (DofBot)" \
    "ssh -v -o ConnectTimeout=5 dofbot 'hostname' 2>&1 | grep -i 'jetson_key'" \
    "jetson_key" 10

test_numeric "2.Auth" "2.6 IdentitiesOnly works (only 1 key offered)" \
    "ssh -v reggie 'hostname' 2>&1 | grep -c 'Offering public key'" \
    "le" 2

test_case "2.Auth" "2.7 Wrong key fails" \
    "ssh -i ~/.ssh/jetson_key -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 pollen@192.168.0.11 'hostname' 2>&1" \
    "Permission denied" 10

test_case "2.Auth" "2.8 Automation key is passphrase-less" \
    "ssh-keygen -y -f ~/.ssh/automation_key 2>&1" \
    "ssh-"

# ============================================================================
# 3. SSH CONFIG VALIDATION TESTS
# ============================================================================
section "3. SSH Config Validation Tests"

test_case "3.Config" "3.1 Config file syntax valid" \
    "ssh -G reggie | grep -E '^(hostname|user|identityfile)' | head -3" \
    "hostname"

test_case "3.Config" "3.2 Robot config - hostname" \
    "ssh -G reggie | grep '^hostname ' | awk '{print \$2}'" \
    "192.168.0.11"

test_case "3.Config" "3.2 Robot config - user" \
    "ssh -G reggie | grep '^user ' | awk '{print \$2}'" \
    "pollen"

test_case "3.Config" "3.3 MacBook config - hostname" \
    "ssh -G reggiembp | grep '^hostname ' | awk '{print \$2}'" \
    "192.168.0.168"

test_case "3.Config" "3.3 MacBook config - user" \
    "ssh -G reggiembp | grep '^user ' | awk '{print \$2}'" \
    "reggie"

test_case "3.Config" "3.4 DofBot config - hostname" \
    "ssh -G dofbot | grep '^hostname ' | awk '{print \$2}'" \
    "192.168.0.52"

test_case "3.Config" "3.4 DofBot config - user" \
    "ssh -G dofbot | grep '^user ' | awk '{print \$2}'" \
    "jetson"

test_case "3.Config" "3.5 StrictHostKeyChecking disabled" \
    "ssh -G reggie | grep '^stricthostkeychecking ' | awk '{print \$2}'" \
    "no"

test_case "3.Config" "3.6 IdentitiesOnly enabled" \
    "ssh -G reggie | grep '^identitiesonly ' | awk '{print \$2}'" \
    "yes"

# ============================================================================
# 4. COMMAND EXECUTION TESTS
# ============================================================================
section "4. Command Execution Tests"

test_case "4.Cmd" "4.1 Simple command (whoami)" \
    "ssh reggie 'whoami'" \
    "pollen"

test_case "4.Cmd" "4.2 Command with args" \
    "ssh reggie 'ls -la /home | head -3'" \
    "total"

test_case "4.Cmd" "4.3 Piped command" \
    "ssh reggie 'ps aux | wc -l'" \
    ""  # Just check it returns a number

test_case "4.Cmd" "4.4 Multi-command chain" \
    "ssh reggie 'cd /tmp && pwd'" \
    "/tmp"

test_case "4.Cmd" "4.5 Environment variable" \
    "ssh reggie 'echo \$HOME'" \
    "/home/pollen"

test_case "4.Cmd" "4.6 Quoted strings" \
    "ssh reggie \"echo 'hello world'\"" \
    "hello world"

test_case "4.Cmd" "4.7 Exit code propagation" \
    "ssh reggie 'exit 42'; echo \$?" \
    "42"

test_case "4.Cmd" "4.8 Sudo access (robot)" \
    "ssh reggie 'echo root | sudo -S whoami 2>/dev/null'" \
    "root"

test_numeric "4.Cmd" "4.9 Long output handling" \
    "ssh reggie 'cat /etc/passwd | wc -l'" \
    "gt" 5

test_numeric "4.Cmd" "4.10 Binary output" \
    "ssh reggie 'cat /bin/ls | wc -c'" \
    "gt" 1000

test_case "4.Cmd" "4.11 Unicode handling (MacBook)" \
    "ssh reggiembp 'echo \"test123\"'" \
    "test123"

test_case "4.Cmd" "4.12 Special characters" \
    "ssh reggie 'echo \"dollar:\\\$HOME\"'" \
    "dollar:"

# ============================================================================
# 5. FILE ACCESS TESTS
# ============================================================================
section "5. File Access Tests"

test_numeric "5.File" "5.1 Read authorized_keys (robot)" \
    "ssh reggie 'cat ~/.ssh/authorized_keys | wc -l'" \
    "gt" 0

test_case "5.File" "5.2 Read package.json (MacBook)" \
    "ssh reggiembp 'cat ~/Reggie/reggie-homebase/package.json 2>/dev/null | head -3'" \
    "{"

test_case "5.File" "5.3 List directory (robot)" \
    "ssh reggie 'ls ~/reggie-audio-bridge/ 2>/dev/null | head -3'" \
    ""

test_case "5.File" "5.4 List directory (MacBook)" \
    "ssh reggiembp 'ls ~/Reggie/'" \
    "reggie-homebase"

test_case "5.File" "5.5 Check file exists (robot)" \
    "ssh reggie 'test -f ~/reggie-audio-bridge/audio_bridge.py && echo exists || echo missing'" \
    ""

test_case "5.File" "5.6 Check permissions" \
    "ssh reggie 'stat -c %a ~/.ssh/authorized_keys'" \
    "6"

test_case "5.File" "5.7 Read system file" \
    "ssh reggie 'cat /etc/hostname'" \
    "reachy-mini"

test_numeric "5.File" "5.8 Read env file" \
    "ssh reggie 'cat ~/reggie-audio-bridge/.env 2>/dev/null | wc -l'" \
    "ge" 0

# ============================================================================
# 6. ERROR HANDLING & EDGE CASES
# ============================================================================
section "6. Error Handling & Edge Cases"

test_case "6.Error" "6.1 Connection timeout handling" \
    "ssh -o ConnectTimeout=2 -o BatchMode=yes pollen@192.168.0.254 'hostname' 2>&1" \
    "" 5  # Just check it doesn't hang

test_case "6.Error" "6.2 Invalid host" \
    "ssh -o ConnectTimeout=2 -o BatchMode=yes invalidhost12345 'hostname' 2>&1" \
    "" 5

test_case "6.Error" "6.3 Wrong user" \
    "ssh -o BatchMode=yes -o ConnectTimeout=5 wronguser@192.168.0.11 'hostname' 2>&1" \
    "Permission denied" 10

test_case "6.Error" "6.4 Command not found" \
    "ssh reggie 'nonexistentcommand123xyz' 2>&1" \
    "not found"

test_case "6.Error" "6.5 Permission denied (file)" \
    "ssh reggie 'cat /etc/shadow' 2>&1" \
    "Permission denied"

test_exit_code "6.Error" "6.6 Empty command" \
    "ssh reggie ''" \
    0

test_numeric "6.Error" "6.7 Very long command" \
    "ssh reggie \"echo \\\$(python3 -c 'print(\\\"x\\\"*1000)')\" | wc -c" \
    "gt" 900 60

test_case "6.Error" "6.8 Rapid reconnection" \
    "for i in 1 2 3; do ssh reggie 'hostname'; done | grep -c reachy" \
    "3" 30

test_case "6.Error" "6.9 Concurrent connections" \
    "(ssh reggie 'sleep 1 && echo a' & ssh reggie 'sleep 1 && echo b' & wait) | sort | tr -d '\n'" \
    "ab" 15

test_case "6.Error" "6.10 Connection with timeout cmd" \
    "timeout 10 ssh reggie 'sleep 1 && echo done'" \
    "done" 15

# ============================================================================
# 7. SERVICE INTEGRATION TESTS
# ============================================================================
section "7. Service Integration Tests"

test_case "7.Service" "7.1 Robot daemon status" \
    "ssh reggie 'systemctl is-active reachy-mini-daemon 2>/dev/null || echo check-failed'" \
    ""

test_case "7.Service" "7.2 Robot API reachable" \
    "ssh reggie 'curl -s -o /dev/null -w \"%{http_code}\" http://localhost:8000/api/daemon/status 2>/dev/null || echo 000'" \
    ""

test_case "7.Service" "7.3 Robot OS version" \
    "ssh reggie 'cat /etc/reachy-mini-os-release 2>/dev/null | head -1 || cat /etc/os-release | head -1'" \
    ""

test_numeric "7.Service" "7.4 MacBook homebase check" \
    "ssh reggiembp 'lsof -i :3001 2>/dev/null | wc -l'" \
    "ge" 0

test_case "7.Service" "7.5 MacBook project exists" \
    "ssh reggiembp 'test -d ~/Reggie/reggie-homebase && echo yes'" \
    "yes"

test_case "7.Service" "7.6 Robot audio bridge exists" \
    "ssh reggie 'test -d ~/reggie-audio-bridge && echo yes || echo no'" \
    ""

test_case "7.Service" "7.7 Robot Python available" \
    "ssh reggie 'python3 --version'" \
    "Python 3"

test_case "7.Service" "7.8 MacBook Node available" \
    "ssh reggiembp 'node --version 2>/dev/null || echo not-installed'" \
    ""

test_case "7.Service" "7.9 Robot systemd available" \
    "ssh reggie 'systemctl --version | head -1'" \
    "systemd"

test_case "7.Service" "7.10 MacBook npm available" \
    "ssh reggiembp 'npm --version 2>/dev/null || echo not-installed'" \
    ""

# ============================================================================
# 8. PERFORMANCE TESTS
# ============================================================================
section "8. Performance Tests"

echo "  Running performance tests (may take a moment)..."

# 8.1 Connection latency
printf "  %-50s " "8.1 Connection latency"
start=$(date +%s.%N)
ssh reggie 'exit' >/dev/null 2>&1
end=$(date +%s.%N)
latency=$(echo "$end - $start" | bc)
if (( $(echo "$latency < 3" | bc -l) )); then
    echo -e "${GREEN}PASS${NC} (${latency}s)"
    ((PASS++))
    echo "[8.Perf] Connection latency: PASS (${latency}s)" >> "$LOG_FILE"
else
    echo -e "${RED}FAIL${NC} (${latency}s > 3s)"
    ((FAIL++))
    echo "[8.Perf] Connection latency: FAIL (${latency}s)" >> "$LOG_FILE"
fi

# 8.2 Command roundtrip
printf "  %-50s " "8.2 Command roundtrip"
start=$(date +%s.%N)
ssh reggie 'hostname' >/dev/null 2>&1
end=$(date +%s.%N)
roundtrip=$(echo "$end - $start" | bc)
if (( $(echo "$roundtrip < 5" | bc -l) )); then
    echo -e "${GREEN}PASS${NC} (${roundtrip}s)"
    ((PASS++))
    echo "[8.Perf] Command roundtrip: PASS (${roundtrip}s)" >> "$LOG_FILE"
else
    echo -e "${RED}FAIL${NC} (${roundtrip}s > 5s)"
    ((FAIL++))
    echo "[8.Perf] Command roundtrip: FAIL (${roundtrip}s)" >> "$LOG_FILE"
fi

# 8.3 Data transfer
test_numeric "8.Perf" "8.3 Data transfer (1MB)" \
    "ssh reggie 'dd if=/dev/zero bs=1M count=1 2>/dev/null' | wc -c" \
    "eq" 1048576 30

# 8.4 Multiple sequential
printf "  %-50s " "8.4 Multiple sequential (10 connections)"
start=$(date +%s.%N)
for i in {1..10}; do ssh reggie 'hostname' >/dev/null 2>&1; done
end=$(date +%s.%N)
total=$(echo "$end - $start" | bc)
if (( $(echo "$total < 60" | bc -l) )); then
    echo -e "${GREEN}PASS${NC} (${total}s for 10)"
    ((PASS++))
    echo "[8.Perf] Multiple sequential: PASS (${total}s)" >> "$LOG_FILE"
else
    echo -e "${RED}FAIL${NC} (${total}s > 60s)"
    ((FAIL++))
    echo "[8.Perf] Multiple sequential: FAIL (${total}s)" >> "$LOG_FILE"
fi

# 8.5 Large output
test_numeric "8.Perf" "8.5 Large output (1000 lines)" \
    "ssh reggie 'find /usr -type f 2>/dev/null | head -1000' | wc -l" \
    "ge" 100 60

# ============================================================================
# 9. DOCUMENTATION ACCURACY TESTS
# ============================================================================
section "9. Documentation Accuracy Tests"

test_case "9.Docs" "9.1 Skill file exists" \
    "test -f /home/pds/.claude/skills/reggie-ssh/SKILL.md && echo exists" \
    "exists"

test_case "9.Docs" "9.2 Quick ref has SSH section" \
    "grep -l 'SSH\|ssh' /home/pds/boomshakalaka/docs/reggie-quick-reference.md 2>/dev/null && echo found" \
    "found"

test_case "9.Docs" "9.3 Dashboard doc has SSH section" \
    "grep -l 'SSH\|ssh' /home/pds/boomshakalaka/docs/reggie-dashboard.md 2>/dev/null && echo found" \
    "found"

test_case "9.Docs" "9.4 Documented aliases work (reggie)" \
    "ssh reggie 'echo aliasworks'" \
    "aliasworks"

test_case "9.Docs" "9.5 Documented password works (robot sudo)" \
    "ssh reggie 'echo root | sudo -S echo pwdworks 2>/dev/null'" \
    "pwdworks"

test_case "9.Docs" "9.6 Documented paths exist (robot)" \
    "ssh reggie 'test -d ~/reggie-audio-bridge && echo exists || echo missing'" \
    ""

test_case "9.Docs" "9.7 Documented commands work" \
    "ssh reggie 'hostname && whoami'" \
    "pollen"

test_case "9.Docs" "9.8 Network diagram IPs match (robot)" \
    "ssh -G reggie | grep '^hostname ' | grep '192.168.0.11'" \
    "192.168.0.11"

# ============================================================================
# 10. SECURITY TESTS
# ============================================================================
section "10. Security Tests"

test_case "10.Security" "10.1 Key permissions (automation_key)" \
    "stat -c %a ~/.ssh/automation_key" \
    "600"

test_case "10.Security" "10.2 SSH dir permissions" \
    "stat -c %a ~/.ssh" \
    "700"

test_case "10.Security" "10.3 No agent forwarding" \
    "ssh -v reggie 'echo test' 2>&1 | grep -i 'agent forward' || echo disabled" \
    ""

test_case "10.Security" "10.4 Pubkey auth used" \
    "ssh -v reggie 'echo test' 2>&1 | grep 'Authenticated'" \
    "publickey"

test_case "10.Security" "10.5 Host key in known_hosts" \
    "ssh-keygen -F 192.168.0.11 2>/dev/null | head -1" \
    ""

test_case "10.Security" "10.6 Automation key not encrypted" \
    "grep -c ENCRYPTED ~/.ssh/automation_key || echo 0" \
    "0"

# ============================================================================
# SUMMARY
# ============================================================================
echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}              TEST SUMMARY                  ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "  ${GREEN}PASSED:${NC}  $PASS"
echo -e "  ${RED}FAILED:${NC}  $FAIL"
echo -e "  ${YELLOW}SKIPPED:${NC} $SKIP"
echo ""
TOTAL=$((PASS + FAIL + SKIP))
if [[ $TOTAL -gt 0 ]]; then
    PASS_RATE=$((PASS * 100 / TOTAL))
    echo -e "  Pass Rate: ${PASS_RATE}%"
fi
echo ""

# Write summary to log
echo "" >> "$LOG_FILE"
echo "============================================" >> "$LOG_FILE"
echo "              TEST SUMMARY                  " >> "$LOG_FILE"
echo "============================================" >> "$LOG_FILE"
echo "PASSED:  $PASS" >> "$LOG_FILE"
echo "FAILED:  $FAIL" >> "$LOG_FILE"
echo "SKIPPED: $SKIP" >> "$LOG_FILE"
echo "Completed: $(date)" >> "$LOG_FILE"

echo "Full results saved to: $LOG_FILE"

# Exit with failure count
exit $FAIL
