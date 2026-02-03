#!/usr/bin/env python3
"""
Health Check Script

Performs health checks on all automation systems and optionally sends alerts.
Can be run via cron for continuous monitoring.

Usage:
    python -m polymarket.dashboard.health_check          # Print status
    python -m polymarket.dashboard.health_check --email  # Send email if issues found
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import argparse

# Configuration - Updated 2026-01-27: money_printing moved into boomshakalaka
PROJECT_ROOT = Path('/home/pds/money_printing')
POLYMARKET_DIR = PROJECT_ROOT / 'polymarket'

# Log files to check
LOG_FILES = {
    'Garbage Time Monitor': {
        'path': POLYMARKET_DIR / 'sports_betting' / 'cron.log',
        'error_threshold': 50,  # Alert if more than this many errors
        'stale_hours': 2,  # Alert if no updates in this many hours
    },
}


def check_log_health(name: str, config: dict) -> dict:
    """Check health of a log file"""
    path = config['path']
    result = {
        'name': name,
        'path': str(path),
        'status': 'healthy',
        'issues': [],
    }

    if not path.exists():
        result['status'] = 'error'
        result['issues'].append(f'Log file not found: {path}')
        return result

    # Check for errors
    try:
        output = subprocess.run(
            ['grep', '-c', '-i', 'error', str(path)],
            capture_output=True, text=True
        )
        error_count = int(output.stdout.strip()) if output.stdout.strip() else 0
        result['error_count'] = error_count

        if error_count > config.get('error_threshold', 100):
            result['status'] = 'warning'
            result['issues'].append(f'High error count: {error_count}')
    except Exception as e:
        result['issues'].append(f'Could not count errors: {e}')

    # Check for staleness
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        stale_threshold = datetime.now() - timedelta(hours=config.get('stale_hours', 4))

        result['last_modified'] = mtime.isoformat()

        if mtime < stale_threshold:
            result['status'] = 'warning'
            result['issues'].append(f'Log is stale: last updated {mtime}')
    except Exception as e:
        result['issues'].append(f'Could not check modification time: {e}')

    return result


def check_api_health(name: str, url: str, params: dict = None) -> dict:
    """Check health of an API endpoint"""
    result = {
        'name': name,
        'url': url,
        'status': 'healthy',
        'issues': [],
    }

    try:
        import httpx
        response = httpx.get(url, params=params, timeout=10)
        result['status_code'] = response.status_code

        if response.status_code != 200:
            result['status'] = 'error'
            result['issues'].append(f'HTTP {response.status_code}')
    except Exception as e:
        result['status'] = 'error'
        result['issues'].append(str(e))

    return result


def check_cron_jobs() -> dict:
    """Check that cron jobs are configured"""
    result = {
        'name': 'Cron Jobs',
        'status': 'healthy',
        'issues': [],
        'jobs': [],
    }

    try:
        output = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if output.returncode != 0:
            result['status'] = 'error'
            result['issues'].append('Could not read crontab')
            return result

        lines = output.stdout.strip().split('\n')
        job_count = sum(1 for line in lines
                       if line.strip() and not line.strip().startswith('#')
                       and not line.startswith('SHELL=')
                       and not line.startswith('PATH=')
                       and not line.startswith('MAILTO='))

        result['job_count'] = job_count

        if job_count == 0:
            result['status'] = 'warning'
            result['issues'].append('No cron jobs configured')

    except Exception as e:
        result['status'] = 'error'
        result['issues'].append(str(e))

    return result


def run_health_checks() -> list:
    """Run all health checks"""
    results = []

    # Check logs
    for name, config in LOG_FILES.items():
        results.append(check_log_health(name, config))

    # Check APIs
    api_key = os.getenv('ODDS_API_KEY')
    results.append(check_api_health(
        'The Odds API',
        'https://api.the-odds-api.com/v4/sports/',
        {'apiKey': api_key}
    ))

    results.append(check_api_health(
        'Polymarket API',
        'https://gamma-api.polymarket.com/markets',
        {'closed': 'false', 'limit': '1'}
    ))

    # Check cron
    results.append(check_cron_jobs())

    return results


def format_report(results: list) -> str:
    """Format health check results as text"""
    lines = [
        "=" * 60,
        "HEALTH CHECK REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        ""
    ]

    has_issues = False

    for result in results:
        status_icon = {
            'healthy': '✓',
            'warning': '⚠',
            'error': '✗',
        }.get(result['status'], '?')

        lines.append(f"{status_icon} {result['name']}: {result['status'].upper()}")

        if result.get('issues'):
            has_issues = True
            for issue in result['issues']:
                lines.append(f"    - {issue}")

        lines.append("")

    if not has_issues:
        lines.append("All systems healthy!")

    return '\n'.join(lines)


def send_alert_email(report: str):
    """Send email alert if issues found"""
    EMAIL_SCRIPT = os.path.expanduser('~/.claude/skills/email-notification/send_email.py')

    if not os.path.exists(EMAIL_SCRIPT):
        print(f"Email script not found: {EMAIL_SCRIPT}")
        return

    try:
        result = subprocess.run([
            'python3', EMAIL_SCRIPT,
            '--subject', f"[ALERT] Money Printing Health Check - {datetime.now().strftime('%Y-%m-%d')}",
            '--body', report
        ], capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("Alert email sent")
        else:
            print(f"Failed to send email: {result.stderr}")
    except Exception as e:
        print(f"Error sending email: {e}")


def main():
    parser = argparse.ArgumentParser(description='Run health checks')
    parser.add_argument('--email', action='store_true', help='Send email if issues found')
    args = parser.parse_args()

    results = run_health_checks()
    report = format_report(results)

    print(report)

    # Check if any issues
    has_issues = any(r['status'] != 'healthy' for r in results)

    if has_issues and args.email:
        send_alert_email(report)

    return 0 if not has_issues else 1


if __name__ == '__main__':
    sys.exit(main())
