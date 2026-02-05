"""
Boomshakalaka Management Dashboard

A modern Flask dashboard to monitor automation modules, view logs, and check system health.

Run:
    python -m dashboard.server

Then visit http://localhost:3003
"""

import os
import re
import subprocess
import sys
import json
import uuid
import logging
import sqlite3
import socket
import threading
import time
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import websocket as ws_client
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, redirect, url_for, request, send_file, session, Response
from flask_sock import Sock
from werkzeug.utils import secure_filename

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Authentication module
try:
    from dashboard.auth import (
        init_firebase, verify_firebase_token, get_user_role,
        get_current_user, is_authenticated, is_admin as auth_is_admin,
        requires_auth, requires_role, login_user, logout_user
    )
    AUTH_AVAILABLE = True
except ImportError as e:
    print(f"Auth import failed: {e}")
    AUTH_AVAILABLE = False

# Theme generator for AI-powered theme customization
try:
    from dashboard.theme_generator import (
        generate_theme_from_prompt, colors_to_css_variables,
        colors_to_ttyd_theme, generate_ttyd_service_command, DEFAULT_THEME
    )
    THEME_GENERATOR_AVAILABLE = True
except ImportError:
    THEME_GENERATOR_AVAILABLE = False
    DEFAULT_THEME = None

# Claude Code terminal parser for mobile chat interface
try:
    from dashboard.claude_parser import (
        get_chat_buffer, get_terminal_state, send_to_tmux
    )
    CLAUDE_PARSER_AVAILABLE = True
except ImportError:
    CLAUDE_PARSER_AVAILABLE = False

# Video model parameters for AI Studio Video generation
try:
    from dashboard.video_model_params import (
        VIDEO_MODEL_PARAMS, get_model_type, get_model_params,
        get_default_negative_prompt, get_param_defaults, validate_frames,
        get_all_model_params_json
    )
    VIDEO_PARAMS_AVAILABLE = True
except ImportError:
    try:
        # Fallback for when running directly from dashboard directory
        from video_model_params import (
            VIDEO_MODEL_PARAMS, get_model_type, get_model_params,
            get_default_negative_prompt, get_param_defaults, validate_frames,
            get_all_model_params_json
        )
        VIDEO_PARAMS_AVAILABLE = True
    except ImportError:
        VIDEO_PARAMS_AVAILABLE = False
        VIDEO_MODEL_PARAMS = {}

# Video utilities for FFmpeg operations (frame extraction, stitching)
try:
    from dashboard.video_utils import get_video_utils, VideoUtils
    VIDEO_UTILS_AVAILABLE = True
except ImportError:
    VIDEO_UTILS_AVAILABLE = False

# Automation Hub for job scheduling and monitoring
# Add project root to path for automation imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    from automation.runner.db import (
        init_database as init_jobs_db,
        get_all_jobs, get_job, create_job, update_job, toggle_job,
        get_job_runs, get_run, get_stats_summary, get_recent_failures,
        clear_recent_failures
    )
    from automation.runner.executor import JobExecutor, register_job
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    print(f"Automation import failed: {e}")
    AUTOMATION_AVAILABLE = False

# Project Management database
try:
    from dashboard.projects_db import (
        init_database as init_projects_db,
        import_areas_from_directory, import_projects_from_directory,
        get_all_areas, get_area, get_area_by_name,
        create_area, update_area, delete_area, reorder_areas,
        get_all_projects, get_projects_by_area, get_project, get_project_by_name,
        create_project, update_project, delete_project,
        get_tasks_by_project, get_all_tasks, get_task,
        create_task, update_task, delete_task, reorder_tasks,
        get_all_active_tasks, get_active_tasks_by_area,
        get_all_lists, get_list, create_list, update_list, delete_list,
        add_list_item, update_list_item, delete_list_item,
        get_stats as get_pm_stats,
        create_task_attachment, get_task_attachment, get_task_attachments,
        delete_task_attachment, get_project_for_task,
        # SMS Allowlist functions
        add_to_sms_allowlist, get_sms_allowlist_entry, is_phone_allowed,
        get_sms_allowlist, remove_from_sms_allowlist, update_sms_allowlist_name,
        log_sms_message, get_sms_conversation, get_recent_sms_messages,
        normalize_phone_number,
        AVAILABLE_ICONS, DEFAULT_COLORS
    )
    PROJECTS_AVAILABLE = True
except ImportError as e:
    print(f"Projects import failed: {e}")
    PROJECTS_AVAILABLE = False

# Twilio SMS Client (voice is handled by MacBook)
try:
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:
    print("Twilio import failed - SMS features disabled")
    TWILIO_AVAILABLE = False

# Setup logging for AI Studio debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ai_studio')

# Add polymarket to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Flask secret key for sessions (required for login)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable template hot reload without full debug mode
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Initialize Flask-Sock for WebSocket support (OpenClaw proxy)
sock = Sock(app)

# Initialize Firebase on startup
if AUTH_AVAILABLE:
    init_firebase()

# Configuration
PROJECT_ROOT = Path('/home/pds/boomshakalaka')
# Updated 2026-01-27: money_printing moved into boomshakalaka
POLYMARKET_DIR = Path('/home/pds/money_printing/polymarket')

# AI Studio Configuration (100% local - no external calls)
COMFY_HOST = '127.0.0.1'  # Localhost only - never exposed
COMFY_PORT = 8188
COMFY_DIR = Path('/home/pds/image_gen/ComfyUI')
MODELS_DIR = PROJECT_ROOT / 'models'  # Symlink to ComfyUI models
GENERATIONS_DIR = PROJECT_ROOT / 'data' / 'generations'
DATABASES_DIR = PROJECT_ROOT / 'data' / 'databases'
THEMES_FILE = PROJECT_ROOT / 'data' / 'themes.json'

# Twilio SMS/Voice Configuration
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '+16122559398')

# Initialize Twilio client
twilio_client = None
if TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print(f"Twilio client initialized for {TWILIO_PHONE_NUMBER}")
    except Exception as e:
        print(f"Failed to initialize Twilio client: {e}")

# OpenClaw Gateway for AI responses
OPENCLAW_GATEWAY_URL = 'http://192.168.0.168:18789'

# Dev server port ranges to monitor
# Each tuple: (start, end, category_name)
DEV_PORT_RANGES = [
    (3000, 3010, 'Node.js'),
    (4000, 4019, 'Allocated'),
    (5000, 5010, 'Flask'),
    (8000, 8010, 'Django/FastAPI'),
]

# System ports to exclude even if in range
EXCLUDED_PORTS = {3003, 3004}  # Dashboard, dashboard-ctl

# Module Registry
MODULES = {
    'sports': {
        'name': 'Sports',
        'modules': [
            {
                'name': 'Sports Replays',
                'description': 'YouTube highlights for Liverpool, Timbers, Tigers, Wild',
                'log': POLYMARKET_DIR / 'sports_replays' / 'cron.log',
                'schedule': 'Daily at 4:00 AM',
                'active': True,
            },
            {
                'name': 'Garbage Time Monitor',
                'description': 'NBA/NFL blowout detection for betting',
                'log': POLYMARKET_DIR / 'sports_betting' / 'cron.log',
                'schedule': 'Every 10 min during games',
                'active': True,
            },
        ]
    },
    'crypto': {
        'name': 'Crypto',
        'modules': [
            {
                'name': 'Insider Detector',
                'description': 'Polymarket suspicious trading detection',
                'log': POLYMARKET_DIR / 'insider' / 'cron.log',
                'schedule': 'Every 15 min (6 AM - 11 PM)',
                'active': True,
            },
            {
                'name': 'Conditional Arb',
                'description': 'Logical relationship arbitrage scanner',
                'log': None,
                'schedule': 'Not scheduled',
                'active': False,
            },
            {
                'name': 'Political Data',
                'description': 'Polling, trends, and sentiment aggregation',
                'log': None,
                'schedule': 'Not scheduled',
                'active': False,
            },
        ]
    },
    'ai': {
        'name': 'AI Studio',
        'modules': [
            {
                'name': 'Image Generator',
                'description': 'Local AI image generation with iteration tools',
                'log': DATABASES_DIR / 'ai_studio.log',
                'schedule': 'On-demand',
                'active': True,
            },
            {
                'name': 'Video Generator',
                'description': 'LTX-Video and HunyuanVideo generation',
                'log': None,
                'schedule': 'On-demand',
                'active': False,
            },
        ]
    }
}

# Log files to monitor
LOG_FILES = {
    'Sports Replays': POLYMARKET_DIR / 'sports_replays' / 'cron.log',
    'Garbage Time Monitor': POLYMARKET_DIR / 'sports_betting' / 'cron.log',
    'Insider Detector': POLYMARKET_DIR / 'insider' / 'cron.log',
    'Polymarket Scanner': POLYMARKET_DIR / 'scanner.log',
}


def parse_crontab():
    """Parse user crontab and return list of jobs"""
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        if result.returncode != 0:
            return []

        jobs = []
        lines = result.stdout.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('SHELL=') or line.startswith('PATH=') or line.startswith('MAILTO='):
                continue
            if line.startswith('#'):
                continue

            parts = line.split(None, 5)
            if len(parts) >= 6:
                schedule = ' '.join(parts[:5])
                command = parts[5]

                job_name = 'Unknown'
                category = 'Other'

                if 'garbage_time' in command or 'cron_runner.sh' in command:
                    job_name = 'Garbage Time Monitor'
                    category = 'Sports'
                elif 'live_monitor.py analyze' in command:
                    job_name = 'Daily Analysis Report'
                    category = 'Sports'
                elif 'weekly_report' in command:
                    job_name = 'Weekly Report'
                    category = 'Sports'
                elif 'insider' in command:
                    job_name = 'Insider Detector'
                    category = 'Crypto'
                elif 'sports_replays' in command:
                    job_name = 'Sports Replays'
                    category = 'Sports'
                elif 'ingest' in command or 'scanner' in command:
                    job_name = 'Polymarket Scanner'
                    category = 'Crypto'

                jobs.append({
                    'name': job_name,
                    'schedule': schedule,
                    'command': command[:100] + '...' if len(command) > 100 else command,
                    'human_schedule': humanize_cron(schedule),
                    'category': category,
                })

        return jobs
    except Exception as e:
        return [{'name': 'Error', 'schedule': '', 'command': str(e), 'human_schedule': '', 'category': 'Error'}]


def humanize_cron(schedule):
    """Convert cron expression to human-readable format"""
    parts = schedule.split()
    if len(parts) != 5:
        return schedule

    minute, hour, day, month, dow = parts

    if minute == '*' and hour == '*':
        return 'Every minute'
    elif minute.startswith('*/'):
        interval = minute[2:]
        if hour == '*':
            return f"Every {interval} minutes"
        else:
            return f"Every {interval} min ({hour}:00-{hour}:59)"
    elif minute == '0' and hour == '*':
        return 'Every hour on the hour'
    elif minute == '0' and hour.isdigit():
        h = int(hour)
        ampm = 'AM' if h < 12 else 'PM'
        h12 = h if h <= 12 else h - 12
        h12 = 12 if h12 == 0 else h12
        return f"Daily at {h12}:00 {ampm}"
    elif dow == '0':
        return f"Sundays at {hour}:{minute.zfill(2)}"
    elif '-' in hour:
        start, end = hour.split('-')
        return f"Every {minute[2:] if minute.startswith('*/') else minute} min ({start}:00-{end}:59)"

    return schedule


def read_log_tail(log_path, lines=50):
    """Read the last N lines of a log file"""
    try:
        if not log_path or not log_path.exists():
            return f"Log file not found: {log_path}"

        result = subprocess.run(['tail', '-n', str(lines), str(log_path)],
                              capture_output=True, text=True)
        return result.stdout or "Empty log file"
    except Exception as e:
        return f"Error reading log: {e}"


def count_errors_in_log(log_path, hours=24):
    """Count error occurrences in log file"""
    try:
        if not log_path or not log_path.exists():
            return 0

        result = subprocess.run(
            ['grep', '-c', '-i', 'error', str(log_path)],
            capture_output=True, text=True
        )
        return int(result.stdout.strip()) if result.stdout.strip() else 0
    except:
        return 0


def get_last_success_time(log_path):
    """Try to find the last successful run timestamp from log"""
    try:
        if not log_path or not log_path.exists():
            return None

        result = subprocess.run(
            ['grep', '-E', r'\[20[0-9]{2}-[0-9]{2}-[0-9]{2}', str(log_path)],
            capture_output=True, text=True
        )

        lines = result.stdout.strip().split('\n')
        if lines and lines[-1]:
            match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', lines[-1])
            if match:
                return match.group(1)

        mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
        return mtime.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return None


def check_api_health():
    """Check health of external APIs"""
    health = {}

    try:
        import httpx
        api_key = os.getenv('ODDS_API_KEY')
        response = httpx.get(
            'https://api.the-odds-api.com/v4/sports/',
            params={'apiKey': api_key},
            timeout=10
        )
        health['odds_api'] = {
            'status': 'healthy' if response.status_code == 200 else 'error',
            'code': response.status_code,
            'message': f'{len(response.json())} sports available' if response.status_code == 200 else response.text[:100]
        }
    except Exception as e:
        health['odds_api'] = {'status': 'error', 'code': 0, 'message': str(e)}

    try:
        import httpx
        response = httpx.get(
            'https://gamma-api.polymarket.com/markets',
            params={'closed': 'false', 'limit': 1},
            timeout=10
        )
        health['polymarket_api'] = {
            'status': 'healthy' if response.status_code == 200 else 'error',
            'code': response.status_code,
            'message': 'Markets API accessible' if response.status_code == 200 else response.text[:100]
        }
    except Exception as e:
        health['polymarket_api'] = {'status': 'error', 'code': 0, 'message': str(e)}

    return health


def get_log_data():
    """Get log data for all monitored files"""
    log_data = {}
    for name, path in LOG_FILES.items():
        log_data[name] = {
            'content': read_log_tail(path, 50),
            'errors_24h': count_errors_in_log(path),
            'last_run': get_last_success_time(path),
            'path': str(path) if path else 'N/A',
        }
    return log_data


def get_common_context():
    """Get common context for all pages"""
    # Get user from session (Firebase auth)
    user = None
    is_admin = False

    if AUTH_AVAILABLE:
        user = get_current_user()
        if user:
            is_admin = user.get('role') in ['admin', 'super_admin']
    else:
        # Fallback to cookie-based admin mode if auth not available
        is_admin = request.cookies.get('admin_mode', '0') == '1'

    return {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'user': user,
        'is_admin': is_admin,
    }


# --- Garbage Time Analysis Functions ---

GARBAGE_TIME_DB = POLYMARKET_DIR / 'sports_betting' / 'garbage_time.db'
OPTIMIZATION_RESULTS = POLYMARKET_DIR / 'sports_betting' / 'optimization_results.json'


def get_completed_blowout_games():
    """Get all completed blowout games from garbage_time.db"""
    if not GARBAGE_TIME_DB.exists():
        return []

    conn = sqlite3.connect(str(GARBAGE_TIME_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            game_id,
            sport,
            home_team,
            away_team,
            game_date,
            halftime_lead,
            halftime_spread,
            final_margin,
            underdog_covered,
            regression_amount
        FROM games
        WHERE status = 'completed'
        AND is_blowout = 1
        ORDER BY game_date ASC
    ''')

    games = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return games


def load_optimization_results():
    """Load historical optimization results from JSON file"""
    if not OPTIMIZATION_RESULTS.exists():
        return {}

    with open(OPTIMIZATION_RESULTS, 'r') as f:
        return json.load(f)


def calculate_kelly_results(games, threshold, starting_bankroll=10000):
    """
    Calculate Kelly-based P&L for games at a given threshold.
    Returns dict with games, wins, win_rate, kelly_pct, final_bankroll, roi
    """
    if not games:
        return {
            'threshold': threshold,
            'games': 0,
            'wins': 0,
            'win_rate': 0,
            'kelly_pct': 0,
            'final_bankroll': starting_bankroll,
            'roi': 0
        }

    qualifying = [g for g in games if g['halftime_lead'] and g['halftime_lead'] >= threshold]

    if not qualifying:
        return {
            'threshold': threshold,
            'games': 0,
            'wins': 0,
            'win_rate': 0,
            'kelly_pct': 0,
            'final_bankroll': starting_bankroll,
            'roi': 0
        }

    wins = sum(1 for g in qualifying if g['underdog_covered'])
    win_rate = wins / len(qualifying)

    # Kelly: (bp - q) / b where b=0.909 for -110 odds
    b = 0.909  # profit multiplier at -110 odds
    p = win_rate
    q = 1 - p
    kelly = max(0, (b * p - q) / b)

    # Simulate betting each game chronologically
    bankroll = starting_bankroll
    for game in sorted(qualifying, key=lambda x: x['game_date'] or ''):
        bet_size = bankroll * kelly
        if game['underdog_covered']:
            bankroll += bet_size * 0.909  # Win at -110
        else:
            bankroll -= bet_size

    return {
        'threshold': threshold,
        'games': len(qualifying),
        'wins': wins,
        'win_rate': win_rate,
        'kelly_pct': kelly * 100,
        'final_bankroll': round(bankroll, 2),
        'roi': round((bankroll - starting_bankroll) / starting_bankroll * 100, 1)
    }


def calculate_bankroll_series(games, threshold, starting_bankroll=10000):
    """Calculate bankroll over time for chart visualization"""
    qualifying = [g for g in games if g['halftime_lead'] and g['halftime_lead'] >= threshold]

    if not qualifying:
        return {'labels': [], 'values': []}

    wins = sum(1 for g in qualifying if g['underdog_covered'])
    win_rate = wins / len(qualifying) if qualifying else 0

    b = 0.909
    p = win_rate
    q = 1 - p
    kelly = max(0, (b * p - q) / b)

    bankroll = starting_bankroll
    labels = ['Start']
    values = [starting_bankroll]

    for game in sorted(qualifying, key=lambda x: x['game_date'] or ''):
        bet_size = bankroll * kelly
        if game['underdog_covered']:
            bankroll += bet_size * 0.909
        else:
            bankroll -= bet_size

        labels.append(game['game_date'])
        values.append(round(bankroll, 2))

    return {'labels': labels, 'values': values}


def calculate_bucket_results(games, lower_bound, upper_bound):
    """
    Calculate results for a specific point bucket (e.g., 15-16pt leads).
    This gives ROI per dollar wagered for that specific range.
    """
    BREAKEVEN = 0.5238  # 52.38% needed at -110 odds

    if not games:
        return {
            'bucket': f'{lower_bound}-{upper_bound}pt',
            'lower': lower_bound,
            'upper': upper_bound,
            'games': 0,
            'wins': 0,
            'win_rate': 0,
            'edge': 0,
            'ev_per_100': 0,
            'recommendation': 'NO DATA'
        }

    # Filter games in this specific bucket (inclusive lower, exclusive upper)
    qualifying = [g for g in games
                  if g['halftime_lead'] and lower_bound <= g['halftime_lead'] < upper_bound]

    if not qualifying:
        return {
            'bucket': f'{lower_bound}-{upper_bound}pt',
            'lower': lower_bound,
            'upper': upper_bound,
            'games': 0,
            'wins': 0,
            'win_rate': 0,
            'edge': 0,
            'ev_per_100': 0,
            'recommendation': 'NO DATA'
        }

    wins = sum(1 for g in qualifying if g['underdog_covered'])
    win_rate = wins / len(qualifying)
    edge = (win_rate - BREAKEVEN) * 100

    # EV per $100 wagered: (win_rate * $90.91) - ((1-win_rate) * $100)
    ev_per_100 = (win_rate * 90.91) - ((1 - win_rate) * 100)

    # Determine recommendation
    if edge >= 9:
        recommendation = 'OPTIMAL'
    elif edge >= 5:
        recommendation = 'BET'
    elif edge > 0:
        recommendation = 'MARGINAL'
    else:
        recommendation = 'SKIP'

    return {
        'bucket': f'{lower_bound}-{upper_bound}pt',
        'lower': lower_bound,
        'upper': upper_bound,
        'games': len(qualifying),
        'wins': wins,
        'win_rate': win_rate,
        'edge': round(edge, 1),
        'ev_per_100': round(ev_per_100, 2),
        'recommendation': recommendation
    }


def get_bucket_distribution(games):
    """
    Get the full bucket distribution for bell curve visualization.
    Returns list of bucket results from 12-13pt through 24-25pt.
    """
    buckets = []
    for lower in range(12, 25):
        bucket = calculate_bucket_results(games, lower, lower + 1)
        buckets.append(bucket)
    return buckets


def calculate_running_profit(games, lower_bound=15, upper_bound=17, bet_size=100):
    """
    Calculate running profit for games in the optimal range.
    Returns detailed game-by-game P&L for the optimal bucket.
    """
    # Filter games in optimal range
    qualifying = [g for g in games
                  if g['halftime_lead'] and lower_bound <= g['halftime_lead'] < upper_bound]

    if not qualifying:
        return {
            'total_pnl': 0,
            'total_wagered': 0,
            'wins': 0,
            'losses': 0,
            'roi': 0,
            'games': []
        }

    # Sort by date
    sorted_games = sorted(qualifying, key=lambda x: x['game_date'] or '')

    total_pnl = 0
    games_with_pnl = []

    for game in sorted_games:
        if game['underdog_covered']:
            pnl = bet_size * 0.909  # Win at -110
            result = 'WIN'
        else:
            pnl = -bet_size
            result = 'LOSS'

        total_pnl += pnl

        games_with_pnl.append({
            **game,
            'pnl': round(pnl, 2),
            'result': result,
            'running_total': round(total_pnl, 2)
        })

    wins = sum(1 for g in games_with_pnl if g['result'] == 'WIN')
    losses = len(games_with_pnl) - wins
    total_wagered = bet_size * len(games_with_pnl)

    return {
        'total_pnl': round(total_pnl, 2),
        'total_wagered': total_wagered,
        'wins': wins,
        'losses': losses,
        'roi': round((total_pnl / total_wagered) * 100, 1) if total_wagered > 0 else 0,
        'games': list(reversed(games_with_pnl))  # Most recent first
    }



# YouTube Data API v3 key
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')


def strip_score_from_title(title: str, strip_spoiler_text: bool = False) -> str:
    """
    Remove score spoilers from video titles.

    Examples:
        "Highlights: Fulham 2-2 Liverpool" -> "Highlights: Fulham vs Liverpool"
        "Wild vs. Kings 3-1 | NHL Highlights" -> "Wild vs. Kings | NHL Highlights"
        "Team A 10 - 3 Team B" -> "Team A vs Team B"
        "Game Highlights: Tigers Offense Powers Win..." -> "Game Highlights"

    If strip_spoiler_text is True, also removes descriptive text that spoils results.
    """
    # Pattern: digits, optional spaces, dash/hyphen, optional spaces, digits
    # Also handles en-dash (–) and em-dash (—)
    score_pattern = r'\s*\d+\s*[-–—]\s*\d+\s*'

    # Check if there's a score in the title
    if re.search(score_pattern, title):
        # Replace score with " vs " if it's between two words (team names)
        # First, check if score is between words
        between_words = r'(\w)\s*\d+\s*[-–—]\s*\d+\s*(\w)'
        if re.search(between_words, title):
            title = re.sub(between_words, r'\1 vs \2', title)
        else:
            # Score is at end or followed by separator, just remove it
            title = re.sub(score_pattern, ' ', title)

    if strip_spoiler_text:
        # Strip spoiler text after pipe
        if '|' in title:
            title = title.split('|')[0]

        # Strip spoiler text after "Highlights:" if it contains result-indicative words
        # Pattern: "Game Highlights: [spoiler text]" or "Highlights: [spoiler text]"
        spoiler_words = ['win', 'won', 'lose', 'loss', 'beat', 'defeat', 'powers', 'clinch',
                         'advance', 'eliminate', 'walk-off', 'walkoff', 'comeback', 'rally',
                         'shutout', 'shut out', 'crush', 'rout', 'dominate', 'edge', 'top']

        # Check if there's a colon after "Highlights" and spoiler words follow
        highlights_match = re.search(r'(.*?[Hh]ighlights)\s*:\s*(.*)', title)
        if highlights_match:
            before_colon = highlights_match.group(1)
            after_colon = highlights_match.group(2).lower()

            # Check if the text after colon contains spoiler words
            has_spoiler = any(word in after_colon for word in spoiler_words)
            if has_spoiler:
                title = before_colon

    # Clean up any double spaces or awkward separators
    title = re.sub(r'\s+', ' ', title)  # Multiple spaces to single
    title = re.sub(r'\s*\|\s*\|\s*', ' | ', title)  # Double pipes
    title = re.sub(r'^\s*\|\s*', '', title)  # Leading pipe
    title = re.sub(r'\s*\|\s*$', '', title)  # Trailing pipe

    return title.strip()


# Team logo URLs for thumbnail replacement (avoids spoilery YouTube thumbnails)
TEAM_LOGOS = {
    'Liverpool FC': 'https://upload.wikimedia.org/wikipedia/en/0/0c/Liverpool_FC.svg',
    'Detroit Tigers': 'https://upload.wikimedia.org/wikipedia/commons/e/e3/Detroit_Tigers_logo.svg',
}

# Team configurations for video fetching
TEAM_CONFIGS = {
    'Liverpool FC': {
        'channel_id': 'UC9LQwHZoucFT94I2h6JOcjw',
        'league': 'Premier League / Champions League',
        'method': 'rss',
        'strip_spoiler_text': True,  # Remove descriptive text that spoils results
        'use_logo': True,  # Use team logo instead of YouTube thumbnail
    },
    'Portland Timbers': {
        'channel_id': 'UCm0KnY18KTa_h9bcm3aFEBw',
        'league': 'MLS',
        'method': 'api_search',  # Use API to find highlights (RSS doesn't have them)
        'search_query': 'HIGHLIGHTS',
        'title_must_contain': 'HIGHLIGHTS',  # Only videos with HIGHLIGHTS in title
        'title_exclude': ['timbers2', 'timbers 2'],  # Exclude Timbers 2 reserve team
    },
    'Detroit Tigers': {
        'channel_id': 'UCKKG465DFaJ3Yp-jQHA3jhw',
        'league': 'MLB',
        'method': 'rss',
        'strip_spoiler_text': True,
        'use_logo': True,
    },
    'Minnesota Wild': {
        'league': 'NHL',
        'method': 'api_search',
        'search_query': 'Minnesota Wild highlights',
        'channel_id': 'UCqFMzb-4AUf6WAIbl132QKA',  # NHL channel
        'title_filter': 'wild',  # Only videos with "Wild" in title
    },
}


def fetch_team_videos_api(team_name: str, config: dict, max_videos: int = 10) -> list:
    """Fetch videos using YouTube Data API v3 search."""
    import requests

    videos = []
    try:
        params = {
            'part': 'snippet',
            'q': config.get('search_query', f'{team_name} highlights'),
            'type': 'video',
            'maxResults': max_videos * 3,  # Fetch extra to filter
            'order': 'date',
            'key': YOUTUBE_API_KEY,
        }

        # Optionally filter to specific channel
        if 'channel_id' in config:
            params['channelId'] = config['channel_id']

        response = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params=params,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            title_filter = config.get('title_filter', '').lower()
            title_must_contain = config.get('title_must_contain', '')
            title_exclude = config.get('title_exclude', [])
            strip_spoiler = config.get('strip_spoiler_text', False)
            use_logo = config.get('use_logo', False)

            for item in data.get('items', []):
                snippet = item.get('snippet', {})
                video_id = item.get('id', {}).get('videoId')

                if not video_id:
                    continue

                title = snippet.get('title', '')

                # Apply title filter if specified (e.g., must contain "Wild")
                if title_filter and title_filter not in title.lower():
                    continue

                # Must contain filter (case-sensitive, e.g., "HIGHLIGHTS")
                if title_must_contain and title_must_contain not in title:
                    continue

                # Exclude filter (e.g., exclude "Timbers2")
                if title_exclude:
                    skip = False
                    for exclude_term in title_exclude:
                        if exclude_term.lower() in title.lower():
                            skip = True
                            break
                    if skip:
                        continue

                # Strip score spoilers from title
                display_title = strip_score_from_title(title, strip_spoiler_text=strip_spoiler)

                published = snippet.get('publishedAt', '')[:10]

                # Use team logo or YouTube thumbnail
                if use_logo and team_name in TEAM_LOGOS:
                    thumbnail = TEAM_LOGOS[team_name]
                else:
                    thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"

                videos.append({
                    'title': display_title,
                    'video_id': video_id,
                    'link': f"https://www.youtube.com/watch?v={video_id}",
                    'published': published,
                    'is_highlight': 'highlight' in title.lower() or 'HIGHLIGHTS' in title,
                    'thumbnail': thumbnail,
                })

                if len(videos) >= max_videos:
                    break
        else:
            print(f"YouTube API error: {response.status_code} - {response.text[:200]}")

    except Exception as e:
        print(f"Error fetching videos via API for {team_name}: {e}")

    return videos


def fetch_team_videos_rss(team_name: str, config: dict, max_videos: int = 10) -> list:
    """Fetch videos using YouTube RSS feed."""
    import feedparser

    videos = []
    strip_spoiler = config.get('strip_spoiler_text', False)
    use_logo = config.get('use_logo', False)

    try:
        # Build RSS URL
        if 'rss_url' in config:
            rss_url = config['rss_url']
        else:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={config['channel_id']}"

        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:50]:
            video_id = entry.get('yt_videoid')
            if not video_id:
                link = entry.get('link', '')
                if 'watch?v=' in link:
                    video_id = link.split('watch?v=')[-1].split('&')[0]

            if not video_id:
                continue

            title = entry.get('title', '')

            # Only show highlight videos (must have "highlight" in title)
            if 'highlight' not in title.lower():
                continue

            # Apply additional filter for shared channels (like NHL)
            if 'filter' in config:
                if config['filter'].lower() not in title.lower():
                    continue

            # Strip score spoilers from title
            display_title = strip_score_from_title(title, strip_spoiler_text=strip_spoiler)

            # Parse published date
            published = entry.get('published', '')

            # Use team logo or YouTube thumbnail
            if use_logo and team_name in TEAM_LOGOS:
                thumbnail = TEAM_LOGOS[team_name]
            else:
                thumbnail = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"

            videos.append({
                'title': display_title,
                'video_id': video_id,
                'link': f"https://www.youtube.com/watch?v={video_id}",
                'published': published[:10] if published else '',
                'is_highlight': 'highlight' in title.lower(),
                'thumbnail': thumbnail,
            })

            if len(videos) >= max_videos:
                break

    except Exception as e:
        print(f"Error fetching videos via RSS for {team_name}: {e}")

    return videos


def fetch_team_videos(team_name: str, max_videos: int = 10) -> list:
    """Fetch recent highlight videos for a team."""
    if team_name not in TEAM_CONFIGS:
        return []

    config = TEAM_CONFIGS[team_name]
    method = config.get('method', 'rss')

    if method == 'api_search':
        return fetch_team_videos_api(team_name, config, max_videos)
    else:
        return fetch_team_videos_rss(team_name, config, max_videos)


def get_all_team_videos() -> dict:
    """Fetch recent videos for all tracked teams."""
    results = {}

    for team, config in TEAM_CONFIGS.items():
        results[team] = {
            'videos': fetch_team_videos(team, max_videos=5),
            'league': config.get('league', ''),
        }

    return results


# ============================================
# AI Studio Helper Functions
# ============================================

def check_comfy_status() -> dict:
    """Check if ComfyUI is running and responsive."""
    import socket

    status = {
        'running': False,
        'message': 'Not running',
        'url': f'http://{COMFY_HOST}:{COMFY_PORT}'
    }

    try:
        # Quick socket check first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((COMFY_HOST, COMFY_PORT))
        sock.close()

        if result == 0:
            # Port is open, try to get system stats
            import httpx
            response = httpx.get(
                f'http://{COMFY_HOST}:{COMFY_PORT}/system_stats',
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                vram = data.get('devices', [{}])[0]
                vram_used = vram.get('vram_used', 0) / (1024**3)
                vram_total = vram.get('vram_total', 0) / (1024**3)
                status['running'] = True
                status['message'] = f'Running - VRAM: {vram_used:.1f}/{vram_total:.1f} GB'
                status['vram_used'] = vram_used
                status['vram_total'] = vram_total
        else:
            status['message'] = 'ComfyUI not running. Start it to generate images.'
    except Exception as e:
        status['message'] = f'Connection error: {str(e)[:50]}'

    return status


def get_available_models() -> list:
    """Get list of available checkpoint models from ComfyUI models directory."""
    models = []
    checkpoints_dir = MODELS_DIR / 'checkpoints'

    if checkpoints_dir.exists():
        for f in checkpoints_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ['.safetensors', '.ckpt']:
                stat = f.stat()
                size_gb = stat.st_size / (1024**3)
                # Use modification time as "installed" date
                installed_date = datetime.fromtimestamp(stat.st_mtime)

                # Determine model type from name/size
                model_type = 'Unknown'
                if 'flux' in f.name.lower():
                    model_type = 'Flux'
                elif 'xl' in f.name.lower() or size_gb > 6:
                    model_type = 'SDXL'
                elif 'sd3' in f.name.lower():
                    model_type = 'SD3'
                elif size_gb < 5:
                    model_type = 'SD 1.5'

                models.append({
                    'name': f.stem,  # Filename without extension
                    'filename': f.name,
                    'size_gb': round(size_gb, 1),
                    'type': model_type,
                    'path': str(f),
                    'installed': installed_date.strftime('%Y-%m-%d'),
                    'installed_timestamp': stat.st_mtime,
                })

    # Sort by type, then name
    models.sort(key=lambda x: (x['type'], x['name']))
    return models


def get_available_video_models() -> list:
    """Get list of available video models from ComfyUI models directories."""
    video_models = []

    # Known video model locations and their info
    video_model_info = {
        # LTX models (in checkpoints)
        'ltxv-13b-0.9.8-distilled-fp8.safetensors': {
            'name': 'LTX-Video 13B FP8',
            'type': 'ltx',
            'vram_gb': 14,
            'recommended': True,
            'dir': 'checkpoints',
        },
        'ltx-video-2b-v0.9.safetensors': {
            'name': 'LTX-Video 2B',
            'type': 'ltx',
            'vram_gb': 8,
            'recommended': False,
            'dir': 'checkpoints',
        },
        # Wan models (in diffusion_models/TI2V)
        'TI2V/Wan2_2-TI2V-5B_fp8_e4m3fn_scaled_KJ.safetensors': {
            'name': 'Wan2.2 TI2V 5B FP8',
            'type': 'wan',
            'vram_gb': 10,
            'recommended': False,
            'dir': 'diffusion_models',
        },
        # HunyuanVideo (in diffusion_models)
        'hunyuanvideo1.5_720p_i2v_cfg_distilled_fp16.safetensors': {
            'name': 'HunyuanVideo 1.5 720p i2v',
            'type': 'hunyuan',
            'vram_gb': 16,
            'recommended': False,
            'dir': 'diffusion_models',
        },
    }

    for filename, info in video_model_info.items():
        model_path = MODELS_DIR / info['dir'] / filename
        if model_path.exists():
            stat = model_path.stat()
            size_gb = stat.st_size / (1024**3)
            installed_date = datetime.fromtimestamp(stat.st_mtime)

            video_models.append({
                'name': info['name'],
                'filename': filename,
                'size_gb': round(size_gb, 1),
                'type': info['type'],
                'vram_gb': info['vram_gb'],
                'recommended': info['recommended'],
                'installed': installed_date.strftime('%Y-%m-%d'),
            })

    # Sort: recommended first, then by VRAM (lower first)
    video_models.sort(key=lambda x: (not x['recommended'], x['vram_gb']))
    return video_models


def get_available_loras() -> list:
    """Get list of available LoRA models."""
    loras = []
    loras_dir = MODELS_DIR / 'loras'

    if loras_dir.exists():
        for f in loras_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ['.safetensors', '.ckpt', '.pt']:
                stat = f.stat()
                size_mb = stat.st_size / (1024**2)
                installed_date = datetime.fromtimestamp(stat.st_mtime)

                loras.append({
                    'name': f.stem,
                    'filename': f.name,
                    'size_mb': round(size_mb, 1),
                    'path': str(f),
                    'installed': installed_date.strftime('%Y-%m-%d'),
                    'installed_timestamp': stat.st_mtime,
                })

    loras.sort(key=lambda x: x['name'].lower())
    return loras


def delete_model(filename: str) -> dict:
    """Delete a checkpoint model from the system."""
    model_path = MODELS_DIR / 'checkpoints' / filename
    if not model_path.exists():
        return {'error': f'Model not found: {filename}'}

    try:
        model_path.unlink()
        return {'success': True, 'deleted': filename}
    except Exception as e:
        return {'error': str(e)}


def delete_lora(filename: str) -> dict:
    """Delete a LoRA from the system."""
    lora_path = MODELS_DIR / 'loras' / filename
    if not lora_path.exists():
        return {'error': f'LoRA not found: {filename}'}

    try:
        lora_path.unlink()
        return {'success': True, 'deleted': filename}
    except Exception as e:
        return {'error': str(e)}


def parse_model_url(url: str) -> dict:
    """Parse a model URL to determine source and download info."""
    url_lower = url.lower()

    if 'huggingface.co' in url_lower or 'hf.co' in url_lower:
        # HuggingFace URL
        # Format: https://huggingface.co/org/repo/blob/main/file.safetensors
        # or: https://huggingface.co/org/repo/resolve/main/file.safetensors
        return {'source': 'huggingface', 'url': url}

    elif 'civitai.com' in url_lower:
        # CivitAI URL
        # Format: https://civitai.com/models/12345 or /api/download/models/12345
        return {'source': 'civitai', 'url': url}

    elif url_lower.endswith('.safetensors') or url_lower.endswith('.ckpt'):
        # Direct download URL
        return {'source': 'direct', 'url': url}

    else:
        return {'source': 'unknown', 'url': url}


# Model metadata with best practices and tips
MODEL_TIPS = {
    # SDXL Models
    'juggernautXL': {
        'type': 'SDXL',
        'best_cfg': '4-7',
        'best_steps': '25-35',
        'best_size': '1024x1024, 1152x896, 896x1152',
        'sampler': 'DPM++ 2M SDE or Euler',
        'tips': [
            'Great for photorealistic images',
            'Works well with detailed prompts',
            'Lower CFG (4-6) often produces more natural results',
        ],
        'recommended_negative': 'ugly, deformed, noisy, blurry, low contrast, poorly drawn, bad anatomy, wrong anatomy, extra limbs, missing limbs',
        'trigger_words': None,
        'prompt_template': '[subject description], [action/pose], [setting/environment], [lighting: natural light/studio lighting/golden hour/etc], [camera: portrait shot/wide angle/close-up/etc], photorealistic, highly detailed, 8k',
        'example_prompt': 'A woman with auburn hair wearing a vintage dress, sitting in a sunlit café by the window, soft natural lighting, bokeh background, portrait photography, highly detailed, 8k',
    },
    'epicrealismXL': {
        'type': 'SDXL',
        'best_cfg': '4-6',
        'best_steps': '25-40',
        'best_size': '1024x1024, 1152x896',
        'sampler': 'DPM++ SDE Karras',
        'tips': [
            'Excellent for portraits and people',
            'Use detailed lighting descriptions',
            'Lower CFG keeps skin tones natural',
        ],
        'recommended_negative': 'cartoon, painting, illustration, worst quality, low quality, bad anatomy, bad hands',
        'trigger_words': None,
        'prompt_template': '[subject], [skin/features detail], [expression], [lighting setup], [background], professional photography, sharp focus, detailed skin texture',
        'example_prompt': 'Portrait of a man in his 30s with stubble, confident smile, dramatic Rembrandt lighting, dark studio background, professional headshot, sharp focus, detailed skin texture, catchlights in eyes',
    },
    'CyberRealisticPony': {
        'type': 'SDXL/Pony',
        'best_cfg': '5-7',
        'best_steps': '25-35',
        'best_size': '1024x1024',
        'sampler': 'Euler a or DPM++ 2M',
        'tips': [
            'Based on Pony Diffusion - use score tags',
            'Add "score_9, score_8_up" for quality',
            'Good for stylized and anime content',
        ],
        'recommended_negative': 'score_4, score_3, score_2, score_1, ugly, deformed',
        'trigger_words': 'score_9, score_8_up, score_7_up',
        'prompt_template': 'score_9, score_8_up, score_7_up, [subject], [style: realistic/anime/stylized], [details], [setting]',
        'example_prompt': 'score_9, score_8_up, score_7_up, 1girl, cyberpunk style, neon lighting, futuristic cityscape background, detailed eyes, dynamic pose, rain effects',
    },
    'flux': {
        'type': 'Flux',
        'best_cfg': '1-2',
        'best_steps': '20-30',
        'best_size': '1024x1024, 1360x768, 768x1360',
        'sampler': 'Euler',
        'tips': [
            'Very low CFG (1-2) works best',
            'Excellent prompt following',
            'Great for text in images',
            'Requires ~20GB VRAM',
        ],
        'recommended_negative': '',  # Flux doesn't need negative prompts
        'trigger_words': None,
        'prompt_template': '[detailed natural language description]. Be specific and descriptive - Flux understands complex prompts well.',
        'example_prompt': 'A cozy coffee shop interior with exposed brick walls, warm Edison bulb lighting, a barista making latte art, steam rising from the cup, morning sunlight streaming through large windows, photorealistic',
    },
    'realisticVision': {
        'type': 'SD 1.5',
        'best_cfg': '7-9',
        'best_steps': '25-35',
        'best_size': '512x512, 768x512, 512x768',
        'sampler': 'DPM++ SDE Karras',
        'tips': [
            'Classic SD 1.5 model - smaller and faster',
            'Good for quick iterations',
            'Works with most SD 1.5 LoRAs',
        ],
        'recommended_negative': 'ugly, tiling, poorly drawn hands, poorly drawn feet, poorly drawn face, out of frame, mutation, mutated, extra limbs, disfigured, deformed, cross-eye, body out of frame, blurry, bad art, bad anatomy',
        'trigger_words': None,
        'prompt_template': '[subject], [details], [setting], [quality tags: masterpiece, best quality, highly detailed, sharp focus]',
        'example_prompt': 'A golden retriever puppy playing in autumn leaves, park setting, warm afternoon light, masterpiece, best quality, highly detailed, sharp focus, bokeh',
    },
    'sd3': {
        'type': 'SD3',
        'best_cfg': '4-7',
        'best_steps': '28-40',
        'best_size': '1024x1024',
        'sampler': 'DPM++ 2M',
        'tips': [
            'SD3 Medium - good text rendering',
            'Balanced quality and speed',
            'Moderate CFG works well',
        ],
        'recommended_negative': 'ugly, deformed, blurry, low quality',
        'trigger_words': None,
        'prompt_template': '[subject] with [details], [environment], [style], [lighting]',
        'example_prompt': 'A vintage typewriter on a wooden desk with scattered papers, morning light from a nearby window, nostalgic atmosphere, photorealistic, soft shadows',
    },
}


# Video model tips for Video Studio
VIDEO_MODEL_TIPS = {
    'ltx': {
        'type': 'Image-to-Video (Fast)',
        'optimal_cfg': '3.0-4.5',
        'optimal_steps': '20-30',
        'optimal_resolution': '768x768, 512x768',
        'frame_formula': '8n+1 (25, 49, 81, 121)',
        'negative_supported': True,
        'tips': [
            'Higher strength (0.9) = faithful to input, less motion',
            'Lower strength (0.6) = more creative motion',
            'Best for quick iterations and general use',
            'Sampler: euler is fastest, dpmpp variants may produce smoother motion',
            'Video Quality (CRF): 15-19 for high quality, higher for smaller files',
        ],
        'recommended_negative': 'worst quality, inconsistent motion, blurry, jittery, distorted, watermarks, text',
        'example_prompt': 'Gentle camera pan across scene, soft ambient motion, cinematic lighting',
    },
    'wan': {
        'type': 'Image-to-Video (Motion Control)',
        'optimal_cfg': '4.0-6.0',
        'optimal_steps': '25-35',
        'optimal_resolution': '768x768, 832x480',
        'frame_formula': '4n+1 (17, 25, 49, 81, 121)',
        'negative_supported': False,
        'tips': [
            'motion_strength is the key parameter - directly controls movement',
            'Shift: higher values = more dramatic motion (default 5.0)',
            'Scheduler: unipc is fastest, euler most stable, ddim for different look',
            'Video Quality (CRF): 15-19 for high quality, higher for smaller files',
        ],
        'recommended_negative': None,
        'example_prompt': 'Woman turns head slowly, hair flowing gently, soft smile emerging',
    },
    'hunyuan': {
        'type': 'Image-to-Video (High Quality)',
        'optimal_cfg': '6.0-8.0',
        'optimal_steps': '30-40',
        'optimal_resolution': '720x720, 720x480',
        'frame_formula': '4n+1 (17, 25, 49, 81, 121)',
        'negative_supported': False,
        'tips': [
            'embedded_cfg_scale balances quality vs creativity',
            'Higher values = sharper but potentially less natural',
            'Requires more VRAM than other models',
            'Video Quality (CRF): 15-19 for high quality, higher for smaller files',
        ],
        'recommended_negative': None,
        'example_prompt': 'Cinematic slow zoom into portrait, dramatic lighting shifts subtly',
    },
}


def get_model_tips(model_filename: str) -> dict:
    """Get tips for a specific model based on filename matching."""
    model_lower = model_filename.lower()

    for key, tips in MODEL_TIPS.items():
        if key.lower() in model_lower:
            return tips

    # Default tips for unknown models
    return {
        'type': 'Unknown',
        'best_cfg': '5-8',
        'best_steps': '20-30',
        'best_size': '1024x1024',
        'sampler': 'Euler or DPM++ 2M',
        'tips': ['No specific tips available for this model'],
        'recommended_negative': 'ugly, blurry, low quality',
        'trigger_words': None,
    }


def get_generation_count() -> int:
    """Get total number of generations from database."""
    db_path = DATABASES_DIR / 'generations.db'
    if not db_path.exists():
        return 0

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute('SELECT COUNT(*) FROM generations')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def get_recent_generations(limit: int = 50) -> list:
    """Get recent generations from database."""
    db_path = DATABASES_DIR / 'generations.db'
    if not db_path.exists():
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM generations
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except:
        return []


def init_generations_db():
    """Initialize the generations database if it doesn't exist."""
    db_path = DATABASES_DIR / 'generations.db'
    DATABASES_DIR.mkdir(parents=True, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS generations (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Generation parameters (for reproducibility)
            prompt TEXT NOT NULL,
            negative_prompt TEXT DEFAULT '',
            model TEXT NOT NULL,
            seed INTEGER,
            steps INTEGER DEFAULT 25,
            cfg_scale REAL DEFAULT 7.0,
            sampler TEXT DEFAULT 'euler',
            scheduler TEXT DEFAULT 'normal',
            width INTEGER DEFAULT 1024,
            height INTEGER DEFAULT 1024,

            -- Full workflow for exact reproduction
            workflow_json TEXT,

            -- Organization
            tags TEXT DEFAULT '',
            rating INTEGER DEFAULT 0,
            favorite INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',

            -- Lineage for variations
            parent_id TEXT,

            -- Output files
            output_path TEXT,
            thumbnail_path TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON generations(created_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_model ON generations(model)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_favorite ON generations(favorite)')

    # Video sequences table - for managing multi-segment video projects
    conn.execute('''
        CREATE TABLE IF NOT EXISTS video_sequences (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Sequence metadata
            name TEXT DEFAULT 'Untitled Sequence',
            description TEXT DEFAULT '',

            -- Base generation parameters (inherited by segments)
            base_prompt TEXT,
            base_negative_prompt TEXT,
            base_seed INTEGER,
            video_model TEXT,
            width INTEGER DEFAULT 768,
            height INTEGER DEFAULT 768,
            fps INTEGER DEFAULT 24,

            -- Output
            stitched_video_path TEXT,
            total_duration REAL,
            total_frames INTEGER,

            -- Status
            status TEXT DEFAULT 'draft'
        )
    ''')

    # Video segments table - individual video clips within a sequence
    conn.execute('''
        CREATE TABLE IF NOT EXISTS video_segments (
            id TEXT PRIMARY KEY,
            sequence_id TEXT,
            segment_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Generation parameters
            prompt TEXT NOT NULL,
            negative_prompt TEXT DEFAULT '',
            seed INTEGER,
            steps INTEGER DEFAULT 25,
            cfg_scale REAL DEFAULT 7.0,
            frames INTEGER DEFAULT 49,

            -- Model-specific parameters (JSON)
            model_params TEXT,

            -- Continuation tracking
            source_segment_id TEXT,
            input_image_path TEXT,

            -- Output files
            video_path TEXT,
            first_frame_path TEXT,
            last_frame_path TEXT,
            thumbnail_path TEXT,
            duration REAL,

            -- Status
            status TEXT DEFAULT 'pending',
            error_message TEXT,

            FOREIGN KEY (sequence_id) REFERENCES video_sequences(id),
            FOREIGN KEY (source_segment_id) REFERENCES video_segments(id)
        )
    ''')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_segment_sequence ON video_segments(sequence_id, segment_order)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_segment_status ON video_segments(status)')

    conn.commit()
    conn.close()


# Initialize database on module load
try:
    init_generations_db()
except Exception as e:
    print(f"Warning: Could not initialize generations DB: {e}")


# ============================================
# Routes
# ============================================

@app.route('/')
def index():
    """Redirect to home"""
    return redirect(url_for('home'))


@app.route('/home')
def home():
    """Home/overview page"""
    cron_jobs = parse_crontab()
    log_data = get_log_data()
    total_errors = sum(d['errors_24h'] for d in log_data.values())

    sports_modules = len(MODULES['sports']['modules'])
    crypto_modules = len(MODULES['crypto']['modules'])

    return render_template('home.html',
                         active_page='home',
                         cron_jobs=cron_jobs,
                         log_data=log_data,
                         total_errors=total_errors,
                         total_jobs=len(cron_jobs),
                         sports_modules=sports_modules,
                         crypto_modules=crypto_modules,
                         **get_common_context())


@app.route('/sports')
def sports():
    """Sports category overview page"""
    log_data = get_log_data()

    replays_errors = log_data.get('Sports Replays', {}).get('errors_24h', 0)
    replays_last_run = log_data.get('Sports Replays', {}).get('last_run', None)

    betting_errors = log_data.get('Garbage Time Monitor', {}).get('errors_24h', 0)
    betting_last_run = log_data.get('Garbage Time Monitor', {}).get('last_run', None)

    return render_template('sports.html',
                         active_page='sports',
                         active_category='sports',
                         replays_errors=replays_errors,
                         replays_last_run=replays_last_run,
                         betting_errors=betting_errors,
                         betting_last_run=betting_last_run,
                         **get_common_context())


@app.route('/sports/replays')
def sports_replays():
    """Sports Replays detailed page"""
    log_data = get_log_data()
    replays_data = log_data.get('Sports Replays', {})

    # Fetch recent videos for all teams
    team_videos = get_all_team_videos()

    return render_template('sports_replays.html',
                         active_page='sports_replays',
                         active_category='sports',
                         errors=replays_data.get('errors_24h', 0),
                         last_run=replays_data.get('last_run', None),
                         log_content=replays_data.get('content', ''),
                         team_videos=team_videos,
                         **get_common_context())


@app.route('/sports/betting')
def sports_betting():
    """Garbage Time Monitor detailed page"""
    log_data = get_log_data()
    betting_data = log_data.get('Garbage Time Monitor', {})

    return render_template('sports_betting.html',
                         active_page='sports_betting',
                         active_category='sports',
                         errors=betting_data.get('errors_24h', 0),
                         last_run=betting_data.get('last_run', None),
                         log_content=betting_data.get('content', ''),
                         **get_common_context())


@app.route('/sports/betting/analysis')
def sports_betting_analysis():
    """Garbage Time Analysis page with ROI-focused bucket analysis"""
    games = get_completed_blowout_games()
    historical = load_optimization_results()

    # === ROI-Focused Bucket Analysis (NEW) ===
    # Get bucket distribution for bell curve chart
    bucket_distribution = get_bucket_distribution(games)

    # Calculate running profit for optimal range (15-17pt)
    running_profit = calculate_running_profit(games, lower_bound=15, upper_bound=17, bet_size=100)

    # Find optimal bucket (highest EV per $100)
    profitable_buckets = [b for b in bucket_distribution if b['ev_per_100'] > 0]
    optimal_bucket = max(profitable_buckets, key=lambda x: x['ev_per_100']) if profitable_buckets else None

    # === Legacy Cumulative Threshold Analysis ===
    thresholds = [14, 15, 16, 17, 18, 19, 20, 22, 25]
    matrix = [calculate_kelly_results(games, t) for t in thresholds]

    # Add edge calculation (vs 52.38% breakeven at -110)
    BREAKEVEN = 0.5238
    for row in matrix:
        row['edge'] = round((row['win_rate'] - BREAKEVEN) * 100, 1)
        row['profitable'] = row['win_rate'] > BREAKEVEN

    # Find best threshold by final bankroll
    best = max(matrix, key=lambda x: x['final_bankroll']) if matrix else None

    # Calculate overall stats
    total_games = len(games)
    overall_wins = sum(1 for g in games if g['underdog_covered'])
    overall_win_rate = overall_wins / total_games if total_games > 0 else 0

    # Get NBA historical data for comparison
    nba_historical = historical.get('sports', {}).get('NBA', {}).get('results', {})

    # Build comparison data (only for thresholds with historical data)
    comparison = []
    for t in [14, 15, 16, 17, 18, 19, 20, 22, 25]:
        hist_data = nba_historical.get(str(t), {})
        live_data = next((m for m in matrix if m['threshold'] == t), None)
        if live_data and hist_data:
            comparison.append({
                'threshold': t,
                'historical_win_rate': hist_data.get('win_rate', 0),
                'live_win_rate': live_data['win_rate'],
                'delta': live_data['win_rate'] - hist_data.get('win_rate', 0),
                'status': 'outperform' if live_data['win_rate'] > hist_data.get('win_rate', 0) else 'underperform'
            })

    # Get recent games in optimal range (15-17pt) for display
    recent_optimal = [g for g in running_profit['games']][:10]

    return render_template('sports_betting_analysis.html',
                         active_page='sports_betting_analysis',
                         active_category='sports',
                         # ROI-focused data
                         bucket_distribution=bucket_distribution,
                         running_profit=running_profit,
                         optimal_bucket=optimal_bucket,
                         recent_optimal=recent_optimal,
                         # Legacy cumulative data
                         matrix=matrix,
                         best_threshold=best['threshold'] if best else 14,
                         total_pnl=round(best['final_bankroll'] - 10000, 2) if best else 0,
                         total_games=total_games,
                         overall_win_rate=overall_win_rate,
                         comparison=comparison,
                         **get_common_context())


@app.route('/api/betting/analysis/chart')
def api_betting_chart():
    """JSON endpoint for bankroll chart data"""
    threshold = request.args.get('threshold', 14, type=int)
    games = get_completed_blowout_games()
    chart_data = calculate_bankroll_series(games, threshold)
    return jsonify(chart_data)


@app.route('/api/betting/analysis/buckets')
def api_betting_buckets():
    """JSON endpoint for bucket distribution chart data"""
    games = get_completed_blowout_games()
    buckets = get_bucket_distribution(games)

    # Format for Chart.js
    return jsonify({
        'labels': [b['bucket'] for b in buckets],
        'edges': [b['edge'] for b in buckets],
        'ev_per_100': [b['ev_per_100'] for b in buckets],
        'games': [b['games'] for b in buckets],
        'recommendations': [b['recommendation'] for b in buckets],
        'buckets': buckets
    })


@app.route('/crypto')
def crypto():
    """Crypto category overview page"""
    log_data = get_log_data()

    insider_errors = log_data.get('Insider Detector', {}).get('errors_24h', 0)
    insider_last_run = log_data.get('Insider Detector', {}).get('last_run', None)

    return render_template('crypto.html',
                         active_page='crypto',
                         active_category='crypto',
                         insider_errors=insider_errors,
                         insider_last_run=insider_last_run,
                         **get_common_context())


@app.route('/crypto/insider')
def crypto_insider():
    """Insider Detector detailed page"""
    log_data = get_log_data()
    insider_data = log_data.get('Insider Detector', {})

    return render_template('crypto_insider.html',
                         active_page='crypto_insider',
                         active_category='crypto',
                         errors=insider_data.get('errors_24h', 0),
                         last_run=insider_data.get('last_run', None),
                         log_content=insider_data.get('content', ''),
                         **get_common_context())


@app.route('/crypto/arb')
def crypto_arb():
    """Conditional Arb Scanner detailed page"""
    return render_template('crypto_arb.html',
                         active_page='crypto_arb',
                         active_category='crypto',
                         **get_common_context())


# ============================================
# AI Studio Routes
# ============================================

@app.route('/ai')
def ai():
    """AI Studio category overview page"""
    # Check if ComfyUI is running
    comfy_status = check_comfy_status()

    # Get available models
    models = get_available_models()

    # Get recent generations count
    gen_count = get_generation_count()

    return render_template('ai.html',
                         active_page='ai',
                         active_category='ai',
                         comfy_status=comfy_status,
                         models=models,
                         gen_count=gen_count,
                         **get_common_context())


@app.route('/ai/generate')
def ai_generate():
    """AI Image and Video Generation page"""
    comfy_status = check_comfy_status()
    models = get_available_models()
    video_models = get_available_video_models()
    loras = get_available_loras()

    # Build model tips dict for frontend
    model_tips_json = {m['filename']: get_model_tips(m['filename']) for m in models}

    return render_template('ai_generate.html',
                         active_page='ai_generate',
                         active_category='ai',
                         comfy_status=comfy_status,
                         models=models,
                         video_models=video_models,
                         loras=loras,
                         model_tips=model_tips_json,
                         **get_common_context())


@app.route('/ai/video')
def ai_video():
    """Video Studio - dedicated video generation and stitching interface"""
    comfy_status = check_comfy_status()
    video_models = get_available_video_models()

    # Add display names and types for the UI
    for model in video_models:
        model_type = get_model_type(model['filename']) if VIDEO_PARAMS_AVAILABLE else 'ltx'
        model['type'] = model_type
        model_params = VIDEO_MODEL_PARAMS.get(model_type, {}) if VIDEO_PARAMS_AVAILABLE else {}
        model['display_name'] = model_params.get('display_name', model['filename'])

    return render_template('ai_video.html',
                         active_page='ai_video',
                         active_category='ai',
                         comfy_status=comfy_status,
                         video_models=video_models,
                         video_model_params=VIDEO_MODEL_PARAMS if VIDEO_PARAMS_AVAILABLE else {},
                         video_model_tips=VIDEO_MODEL_TIPS,
                         **get_common_context())


@app.route('/ai/saved')
def ai_saved():
    """AI Saved generations browser"""
    generations = get_recent_generations(limit=50)

    return render_template('ai_saved.html',
                         active_page='ai_saved',
                         active_category='ai',
                         generations=generations,
                         **get_common_context())


# Keep old route for backwards compatibility
@app.route('/ai/history')
def ai_history():
    """Redirect to saved"""
    return redirect(url_for('ai_saved'))


@app.route('/ai/models')
def ai_models():
    """AI Model and LoRA management page"""
    models = get_available_models()
    loras = get_available_loras()

    # Calculate totals
    total_model_size = sum(m['size_gb'] for m in models)
    total_lora_size = sum(l['size_mb'] for l in loras) / 1024  # Convert to GB

    return render_template('ai_models.html',
                         active_page='ai_models',
                         active_category='ai',
                         models=models,
                         loras=loras,
                         total_model_size=round(total_model_size, 1),
                         total_lora_size=round(total_lora_size, 2),
                         **get_common_context())


@app.route('/ai/compare')
def ai_compare():
    """AI Generation Comparison grid"""
    return render_template('ai_compare.html',
                         active_page='ai_compare',
                         active_category='ai',
                         **get_common_context())


@app.route('/logs')
def logs():
    """Logs page"""
    log_data = get_log_data()

    return render_template('logs.html',
                         active_page='logs',
                         log_data=log_data,
                         **get_common_context())


@app.route('/settings')
def settings():
    """Settings page"""
    total_modules = sum(len(cat['modules']) for cat in MODULES.values())
    total_categories = len(MODULES)

    return render_template('settings.html',
                         active_page='settings',
                         total_modules=total_modules,
                         total_categories=total_categories,
                         **get_common_context())


# =============================================================================
# Authentication Routes
# =============================================================================

@app.route('/login')
def login():
    """Login page with Firebase authentication"""
    # If already logged in, redirect to home
    if AUTH_AVAILABLE and is_authenticated():
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Authenticate user with Firebase token"""
    if not AUTH_AVAILABLE:
        return jsonify({'success': False, 'error': 'Authentication not available'}), 503

    data = request.get_json() or {}
    token = data.get('token')

    if not token:
        return jsonify({'success': False, 'error': 'Token required'}), 400

    success, error = login_user(token)

    if success:
        user = get_current_user()
        return jsonify({
            'success': True,
            'user': {
                'email': user.get('email'),
                'name': user.get('name'),
                'role': user.get('role'),
            }
        })
    else:
        return jsonify({'success': False, 'error': error}), 401


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """Logout current user"""
    if AUTH_AVAILABLE:
        logout_user()
    return jsonify({'success': True})


@app.route('/api/auth/me')
def api_auth_me():
    """Get current authenticated user info"""
    if not AUTH_AVAILABLE:
        return jsonify({'error': 'Authentication not available'}), 503

    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401

    return jsonify({
        'uid': user.get('uid'),
        'email': user.get('email'),
        'name': user.get('name'),
        'role': user.get('role'),
    })


# Legacy admin mode toggle (deprecated - kept for backward compatibility)
@app.route('/api/admin-mode', methods=['POST'])
def api_admin_mode():
    """Toggle admin mode on/off (deprecated - use Firebase auth instead)"""
    if AUTH_AVAILABLE and is_authenticated():
        # If using Firebase auth, admin mode is determined by role
        user = get_current_user()
        is_admin = user.get('role') in ['admin', 'super_admin'] if user else False
        return jsonify({'success': True, 'enabled': is_admin, 'message': 'Using Firebase role-based access'})

    # Fallback to cookie-based for non-auth mode
    data = request.get_json() or {}
    enabled = data.get('enabled', False)

    response = jsonify({'success': True, 'enabled': enabled})
    if enabled:
        response.set_cookie('admin_mode', '1', max_age=60*60*24*365)  # 1 year
    else:
        response.set_cookie('admin_mode', '0', max_age=0)  # Delete cookie
    return response


@app.route('/pfs')
def pfs():
    """Precision Fleet Support - Admin only business management section"""
    # Require admin or super_admin role
    if AUTH_AVAILABLE:
        user = get_current_user()
        if not user:
            return redirect(url_for('login', next=request.url))
        if user.get('role') not in ['admin', 'super_admin']:
            return render_template('error.html',
                                 error_code=403,
                                 error_message='Access Denied',
                                 error_details='This page requires admin privileges.',
                                 **get_common_context()), 403

    return render_template('pfs.html',
                         active_page='pfs',
                         active_category='pfs',
                         **get_common_context())


@app.route('/terminal')
def terminal():
    """Web terminal page - embeds ttyd for browser-based terminal access"""
    return render_template('terminal.html',
                         active_page='terminal',
                         active_category='workshop',
                         **get_common_context())


@app.route('/workshop/kanban')
def workshop_kanban():
    """Kanban board for task management"""
    return render_template('workshop_kanban.html',
                         active_page='workshop_kanban',
                         active_category='workshop',
                         **get_common_context())


@app.route('/workshop/agents')
def workshop_agents():
    """8-bit Agent Office visualization"""
    return render_template('workshop_agents.html',
                         active_page='workshop_agents',
                         active_category='workshop',
                         **get_common_context())


@app.route('/workshop/vibecraft')
def workshop_vibecraft():
    """Vibecraft - 3D Claude Code visualization"""
    return render_template('workshop_vibecraft.html',
                         active_page='workshop_vibecraft',
                         active_category='workshop',
                         **get_common_context())


@app.route('/reggie')
def reggie():
    """Reggie robot control dashboard - Overview page"""
    return render_template('reggie.html',
                         active_page='reggie',
                         reggie_page='overview',
                         page_name='Overview',
                         **get_common_context())


@app.route('/reggie/control')
def reggie_control():
    """Reggie motion control page"""
    return render_template('reggie_control.html',
                         active_page='reggie',
                         reggie_page='control',
                         page_name='Motion Control',
                         **get_common_context())


@app.route('/reggie/camera')
def reggie_camera():
    """Reggie camera feed page"""
    return render_template('reggie_camera.html',
                         active_page='reggie',
                         reggie_page='camera',
                         page_name='Camera',
                         **get_common_context())


@app.route('/reggie/moves')
def reggie_moves():
    """Reggie move player page"""
    return render_template('reggie_moves.html',
                         active_page='reggie',
                         reggie_page='moves',
                         page_name='Moves',
                         **get_common_context())


@app.route('/reggie/apps')
def reggie_apps():
    """Reggie apps management page"""
    return render_template('reggie_apps.html',
                         active_page='reggie',
                         reggie_page='apps',
                         page_name='Apps',
                         **get_common_context())


@app.route('/reggie/center')
def reggie_control_center():
    """Reggie unified control center - all controls in one page"""
    return render_template('reggie_control_center.html',
                         active_page='reggie',
                         reggie_page='center',
                         page_name='Control Center',
                         **get_common_context())


@app.route('/reggie/settings')
def reggie_settings():
    """Reggie settings and diagnostics page"""
    return render_template('reggie_settings.html',
                         active_page='reggie',
                         reggie_page='settings',
                         page_name='Settings',
                         **get_common_context())


@app.route('/reggie/openclaw')
def reggie_openclaw():
    """OpenClaw AI Gateway - Reggie's brain interface"""
    return render_template('reggie_openclaw.html',
                         active_page='reggie',
                         reggie_page='openclaw',
                         page_name='OpenClaw',
                         **get_common_context())


@app.route('/reggie/voice')
def reggie_voice():
    """Voice conversation interface for Reggie"""
    return render_template('reggie_voice.html',
                         active_page='reggie',
                         reggie_page='voice',
                         page_name='Voice',
                         **get_common_context())


# Keep old routes for backwards compatibility
@app.route('/overview')
def overview():
    """Redirect to home"""
    return redirect(url_for('home'))


@app.route('/automation')
@app.route('/jobs')
def automation():
    """Automation Hub - Job scheduling and monitoring"""
    jobs_list = []
    stats = {}
    failures = []

    if AUTOMATION_AVAILABLE:
        try:
            init_jobs_db()
            jobs_list = get_all_jobs()
            stats = get_stats_summary()
            failures = get_recent_failures(hours=24)
        except Exception as e:
            logger.error(f"Failed to load automation data: {e}")

    return render_template('automation.html',
                           active_category='automation',
                           active_page='automation',
                           jobs=jobs_list,
                           stats=stats,
                           failures=failures,
                           automation_available=AUTOMATION_AVAILABLE)


@app.route('/health')
def health():
    """Redirect to home (health is shown there now)"""
    return redirect(url_for('home'))


# ============================================
# API Endpoints
# ============================================

@app.route('/api/health')
def api_health():
    """API health check endpoint"""
    return jsonify(check_api_health())


@app.route('/api/logs/<name>')
def api_logs(name):
    """Get log content for a specific log"""
    for log_name, path in LOG_FILES.items():
        if name.lower() in log_name.lower():
            return jsonify({
                'name': log_name,
                'content': read_log_tail(path, 100),
                'errors_24h': count_errors_in_log(path),
            })
    return jsonify({'error': 'Log not found'}), 404


@app.route('/api/cron')
def api_cron():
    """Get cron job list"""
    return jsonify(parse_crontab())


@app.route('/api/stats')
def api_stats():
    """Get dashboard stats"""
    cron_jobs = parse_crontab()
    log_data = get_log_data()
    total_errors = sum(d['errors_24h'] for d in log_data.values())

    return jsonify({
        'jobs_count': len(cron_jobs),
        'total_errors': total_errors,
        'log_files_count': len(LOG_FILES),
        'timestamp': datetime.now().isoformat(),
    })


# ============================================
# Reggie Robot API Proxy Endpoints
# ============================================
# Direct connection to robot API at 192.168.0.11:8000
# MacBook dashboard at 192.168.0.168:3008 is optional (for iframe fallback)

REGGIE_ROBOT_URL = 'http://192.168.0.11:8000'
REGGIE_DASHBOARD_URL = 'http://192.168.0.168:3008'  # Optional MacBook dashboard
REGGIE_OPENCLAW_URL = 'http://192.168.0.168:18789'  # OpenClaw AI Gateway on MacBook
REGGIE_OPENCLAW_TOKEN = 'c424c9bb567e46dabf388b519688a21d'  # Gateway auth token


@app.route('/api/reggie/health')
def api_reggie_health():
    """Check Reggie robot health (primary) and optional MacBook dashboard/OpenClaw.

    All checks run in parallel for faster response times when accessed remotely.
    """
    result = {
        'robot': False,
        'dashboard': False,
        'openclaw': False,
        'daemon': None,
        'timestamp': datetime.now().isoformat()
    }

    def check_robot():
        """Check robot API (timeout 3s)"""
        try:
            resp = requests.get(f'{REGGIE_ROBOT_URL}/api/daemon/status', timeout=3)
            if resp.status_code == 200:
                return ('robot', True, resp.json().get('state', 'unknown'))
        except requests.RequestException:
            pass
        return ('robot', False, None)

    def check_dashboard():
        """Check MacBook dashboard (timeout 1s - fast LAN)"""
        try:
            resp = requests.get(REGGIE_DASHBOARD_URL, timeout=1)
            return ('dashboard', resp.status_code == 200)
        except requests.RequestException:
            pass
        return ('dashboard', False)

    def check_openclaw():
        """Check OpenClaw Gateway (fast fail, 3s timeout)"""
        try:
            resp = requests.get(
                REGGIE_OPENCLAW_URL,
                timeout=3,
                headers={'Connection': 'close'}
            )
            return ('openclaw', resp.status_code == 200)
        except requests.RequestException:
            return ('openclaw', False)

    # Run all checks in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(check_robot),
            executor.submit(check_dashboard),
            executor.submit(check_openclaw)
        ]
        for future in as_completed(futures):
            res = future.result()
            if res[0] == 'robot':
                result['robot'] = res[1]
                if len(res) > 2:
                    result['daemon'] = res[2]
            else:
                result[res[0]] = res[1]

    return jsonify(result)


@app.route('/api/reggie/status')
def api_reggie_status():
    """Get Reggie's full robot state"""
    try:
        resp = requests.get(f'{REGGIE_ROBOT_URL}/api/state/full', timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({'error': 'Robot returned error', 'status_code': resp.status_code}), 502
    except requests.Timeout:
        return jsonify({'error': 'Request to robot timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to connect to robot: {str(e)}'}), 503


@app.route('/api/reggie/daemon/<action>', methods=['POST'])
def api_reggie_daemon(action):
    """Control robot daemon (start/stop)"""
    if action not in ['start', 'stop']:
        return jsonify({'error': 'Invalid action. Use start or stop'}), 400

    try:
        params = request.get_json() or {}
        if action == 'start':
            url = f'{REGGIE_ROBOT_URL}/api/daemon/start'
            query_params = {'wake_up': str(params.get('wake_up', True)).lower()}
        else:
            url = f'{REGGIE_ROBOT_URL}/api/daemon/stop'
            query_params = {'goto_sleep': str(params.get('goto_sleep', True)).lower()}

        # Robot API expects query params, not JSON body
        resp = requests.post(url, params=query_params, timeout=10)
        return jsonify(resp.json() if resp.text else {'success': True}), resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/move/goto', methods=['POST'])
def api_reggie_move_goto():
    """Move robot to target pose"""
    try:
        data = request.get_json() or {}
        # Robot API requires duration field
        if 'duration' not in data:
            data['duration'] = 0.5  # Default 500ms for smooth movement
        resp = requests.post(f'{REGGIE_ROBOT_URL}/api/move/goto', json=data, timeout=10)
        return jsonify(resp.json() if resp.text else {'success': True}), resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/move/play/<path:move_path>', methods=['POST'])
def api_reggie_move_play(move_path):
    """Play a recorded move or animation"""
    try:
        resp = requests.post(f'{REGGIE_ROBOT_URL}/api/move/play/{move_path}', timeout=30)
        return jsonify(resp.json() if resp.text else {'success': True}), resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/move/stop', methods=['POST'])
def api_reggie_move_stop():
    """Stop current movement"""
    try:
        resp = requests.post(f'{REGGIE_ROBOT_URL}/api/move/stop', timeout=5)
        return jsonify(resp.json() if resp.text else {'success': True}), resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/moves/list/<dataset>')
def api_reggie_moves_list(dataset):
    """List available moves from a dataset"""
    # Map friendly names to full paths
    dataset_map = {
        'dances': 'pollen-robotics/reachy-mini-dances-library',
        'emotions': 'pollen-robotics/reachy-mini-emotions-library'
    }
    dataset_path = dataset_map.get(dataset, dataset)

    try:
        resp = requests.get(
            f'{REGGIE_ROBOT_URL}/api/move/recorded-move-datasets/list/{dataset_path}',
            timeout=5
        )
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({'error': 'Failed to get moves', 'status_code': resp.status_code}), 502
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/motors/mode', methods=['GET', 'POST'])
def api_reggie_motors_mode():
    """Get or set motor mode"""
    try:
        if request.method == 'POST':
            data = request.get_json()
            mode = data.get('mode', 'enabled')
            resp = requests.post(f'{REGGIE_ROBOT_URL}/api/motors/set_mode/{mode}', timeout=5)
        else:
            resp = requests.get(f'{REGGIE_ROBOT_URL}/api/motors/status', timeout=5)

        return jsonify(resp.json() if resp.text else {'success': True}), resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/reggie/proxy/<path:endpoint>', methods=['GET', 'POST'])
def api_reggie_proxy(endpoint):
    """Proxy any request to robot API"""
    url = f'{REGGIE_ROBOT_URL}/api/{endpoint}'

    try:
        if request.method == 'POST':
            resp = requests.post(url, json=request.get_json(), timeout=10)
        else:
            resp = requests.get(url, params=request.args, timeout=10)

        # Handle empty responses
        if not resp.text:
            return jsonify({'success': True}), resp.status_code

        try:
            return jsonify(resp.json()), resp.status_code
        except ValueError:
            return resp.text, resp.status_code
    except requests.Timeout:
        return jsonify({'error': 'Request timed out'}), 504
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 503


# ============================================
# OpenClaw Proxy Routes (Secure Context Fix)
# ============================================
# Proxy OpenClaw through localhost so browser treats it as secure context
# This fixes the WebSocket "secure context required" error

@app.route('/openclaw-proxy/')
@app.route('/openclaw-proxy/<path:path>')
def openclaw_proxy(path: str = ''):
    """Proxy HTTP requests to OpenClaw gateway"""
    target_url = f'{REGGIE_OPENCLAW_URL}/{path}'

    # Forward query string
    if request.query_string:
        target_url += '?' + request.query_string.decode()

    try:
        # Add Connection: close to prevent keep-alive issues
        proxy_headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'connection']}
        proxy_headers['Connection'] = 'close'

        # Forward the request
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=proxy_headers,
            data=request.get_data(),
            timeout=30,
            allow_redirects=False
        )

        # Build response - exclude hop-by-hop headers
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(k, v) for k, v in resp.raw.headers.items() if k.lower() not in excluded_headers]

        return Response(resp.content, resp.status_code, headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@sock.route('/openclaw-proxy')
@sock.route('/openclaw-ws')
def openclaw_ws_proxy(ws):
    """Proxy WebSocket connections to OpenClaw gateway"""
    openclaw_ws_url = REGGIE_OPENCLAW_URL.replace('http://', 'ws://')

    try:
        # Include auth token in WebSocket connection
        target = ws_client.create_connection(
            openclaw_ws_url,
            timeout=30,
            header=[f'Authorization: Bearer {REGGIE_OPENCLAW_TOKEN}']
        )
    except Exception as e:
        logger.error(f"OpenClaw WebSocket connection failed: {e}")
        return

    def forward_to_client():
        """Forward messages from OpenClaw to browser"""
        try:
            while True:
                msg = target.recv()
                if msg:
                    ws.send(msg)
        except Exception:
            pass

    thread = threading.Thread(target=forward_to_client, daemon=True)
    thread.start()

    try:
        while True:
            msg = ws.receive()
            if msg:
                target.send(msg)
    except Exception:
        pass
    finally:
        target.close()


# Root WebSocket proxy for OpenClaw iframe
# OpenClaw UI connects to ws://localhost:3003/ based on window.location.origin
@sock.route('/')
def openclaw_root_ws_proxy(ws):
    """Proxy root WebSocket connections to OpenClaw gateway (for iframe)"""
    openclaw_ws_url = REGGIE_OPENCLAW_URL.replace('http://', 'ws://')

    try:
        # Include auth token in WebSocket connection
        target = ws_client.create_connection(
            openclaw_ws_url,
            timeout=30,
            header=[f'Authorization: Bearer {REGGIE_OPENCLAW_TOKEN}']
        )
    except Exception as e:
        logger.error(f"OpenClaw root WebSocket connection failed: {e}")
        return

    running = True

    def forward_to_client():
        nonlocal running
        try:
            while running:
                opcode, data = target.recv_data(control_frame=True)
                if opcode == ws_client.ABNF.OPCODE_TEXT:
                    ws.send(data.decode('utf-8'))
                elif opcode == ws_client.ABNF.OPCODE_BINARY:
                    ws.send(data)
                elif opcode == ws_client.ABNF.OPCODE_CLOSE:
                    break
                elif opcode == ws_client.ABNF.OPCODE_PING:
                    target.pong(data)
                elif opcode == ws_client.ABNF.OPCODE_PONG:
                    pass
        except Exception as e:
            logger.debug(f"OpenClaw WS forward_to_client ended: {e}")
        finally:
            running = False

    thread = threading.Thread(target=forward_to_client, daemon=True)
    thread.start()

    try:
        while running:
            msg = ws.receive(timeout=1)
            if msg is None:
                continue
            if isinstance(msg, bytes):
                target.send_binary(msg)
            else:
                target.send(msg)
    except Exception as e:
        logger.debug(f"OpenClaw WS main loop ended: {e}")
    finally:
        running = False
        try:
            target.close()
        except Exception:
            pass


# ============================================
# WebSocket Proxy Helpers
# ============================================
def send_ws_error_and_close(ws, code, msg, close_status=1011, close_reason='proxy error'):
    """Send a JSON error frame and then properly close the WebSocket.

    This prevents 'Invalid frame header' errors by:
    1. Sending a JSON error message
    2. Sending a proper WebSocket close frame
    3. Closing the underlying socket (prevents Flask from sending HTTP bytes)
    """
    try:
        ws.send(json.dumps({"error": code, "message": msg}))
    except Exception:
        pass  # Client may already be gone
    try:
        ws.close(close_status, close_reason)
    except Exception:
        pass
    # CRITICAL: Close underlying socket to prevent Flask/Werkzeug
    # from writing HTTP response bytes on the WebSocket connection
    try:
        ws.sock.shutdown(socket.SHUT_RDWR)
        ws.sock.close()
    except Exception:
        pass


def send_ws_error_and_close_typed(ws, error_type, code, msg, close_status=1011, close_reason='proxy error'):
    """Send a typed JSON error frame (for camera signaling) and close properly."""
    try:
        ws.send(json.dumps({"type": error_type, "error": code, "message": msg}))
    except Exception:
        pass
    try:
        ws.close(close_status, close_reason)
    except Exception:
        pass
    # CRITICAL: Close underlying socket to prevent Flask/Werkzeug
    # from writing HTTP response bytes on the WebSocket connection
    try:
        ws.sock.shutdown(socket.SHUT_RDWR)
        ws.sock.close()
    except Exception:
        pass


# ============================================
# Camera Signaling Proxy (SSH Tunnel Support)
# ============================================
REGGIE_CAMERA_SIGNALING_URL = 'ws://192.168.0.11:8443'

@sock.route('/reggie/camera-signaling')
def reggie_camera_signaling_proxy(ws):
    """Proxy WebRTC signaling WebSocket to robot camera server.

    This enables camera access when connecting via SSH tunnel (localhost:3003)
    since the robot at 192.168.0.11 isn't directly reachable.

    IMPORTANT: flask-sock's ws object is NOT thread-safe. All ws.send/receive/close
    calls must happen in a single thread. We use a Queue to pass messages from
    the background thread (robot->client) to the main thread which does all ws operations.
    """
    logger.info("[CameraProxy] Client connected, connecting to robot...")
    logger.info(f"[CameraProxy] Target URL: {REGGIE_CAMERA_SIGNALING_URL}")

    try:
        target = ws_client.create_connection(REGGIE_CAMERA_SIGNALING_URL, timeout=30)
        logger.info("[CameraProxy] Connected to robot signaling server")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[CameraProxy] Failed to connect to robot: {error_msg}")
        # Send error and close with proper WebSocket close frame
        send_ws_error_and_close_typed(ws, "error", "connection_failed",
                                       f"Failed to connect to camera server: {error_msg}")
        return

    running = True
    send_queue = Queue()  # Thread-safe queue for robot->browser messages
    CLOSE_SENTINEL = object()  # Marker to signal close

    def robot_to_queue():
        """Background thread: reads from robot, puts messages in queue.
        Does NOT touch the browser ws object."""
        nonlocal running
        try:
            while running:
                opcode, data = target.recv_data(control_frame=True)
                if opcode == ws_client.ABNF.OPCODE_TEXT:
                    decoded = data.decode('utf-8')
                    preview = decoded[:100] + ('...' if len(decoded) > 100 else '')
                    logger.info(f"[CameraProxy] Robot->Queue: {preview}")
                    send_queue.put(('text', decoded))
                elif opcode == ws_client.ABNF.OPCODE_BINARY:
                    logger.info(f"[CameraProxy] Robot->Queue: (binary {len(data)} bytes)")
                    send_queue.put(('binary', data))
                elif opcode == ws_client.ABNF.OPCODE_CLOSE:
                    logger.info("[CameraProxy] Robot sent close frame")
                    send_queue.put(CLOSE_SENTINEL)
                    break
                elif opcode == ws_client.ABNF.OPCODE_PING:
                    target.pong(data)
                elif opcode == ws_client.ABNF.OPCODE_PONG:
                    pass
        except Exception as e:
            logger.info(f"[CameraProxy] Robot reader ended: {e}")
            send_queue.put(('error', str(e)))
        finally:
            running = False
            try:
                target.close()
            except Exception:
                pass

    thread = threading.Thread(target=robot_to_queue, daemon=True)
    thread.start()
    logger.info("[CameraProxy] Robot reader thread started, main loop handling all ws operations...")

    try:
        while running:
            # Drain the queue - send all robot messages to browser
            # This is the ONLY place we call ws.send()
            try:
                while True:
                    item = send_queue.get_nowait()
                    if item is CLOSE_SENTINEL:
                        logger.info("[CameraProxy] Got close sentinel, closing browser ws")
                        running = False
                        break
                    msg_type, payload = item
                    if msg_type == 'text':
                        ws.send(payload)
                    elif msg_type == 'binary':
                        ws.send(payload)
                    elif msg_type == 'error':
                        logger.info(f"[CameraProxy] Sending error to browser: {payload}")
                        ws.send(json.dumps({"type": "error", "error": "connection_lost",
                                            "message": f"Connection to camera server lost: {payload}"}))
                        running = False
                        break
            except Empty:
                pass

            if not running:
                break

            # Check for browser->robot messages (short timeout to stay responsive)
            msg = ws.receive(timeout=0.1)
            if msg is not None:
                if isinstance(msg, bytes):
                    logger.info(f"[CameraProxy] Client->Robot: (binary {len(msg)} bytes)")
                    target.send_binary(msg)
                else:
                    preview = msg[:100] + ('...' if len(msg) > 100 else '')
                    logger.info(f"[CameraProxy] Client->Robot: {preview}")
                    target.send(msg)

    except Exception as e:
        logger.info(f"[CameraProxy] Main loop ended: {e}")
    finally:
        running = False
        logger.info("[CameraProxy] Connection closed")
        try:
            target.close()
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass


# ============================================
# Robot State WebSocket Proxy (SSH Tunnel Support)
# ============================================
REGGIE_STATE_WS_URL = 'ws://192.168.0.11:8000/api/state/ws/full'

@sock.route('/reggie/state-ws')
def reggie_state_ws_proxy(ws):
    """Proxy robot state WebSocket for SSH tunnel access.

    This enables real-time state updates when connecting via localhost:3003
    since the robot at 192.168.0.11 isn't directly reachable.

    IMPORTANT: flask-sock's ws object is NOT thread-safe. All ws.send/receive/close
    calls must happen in a single thread. We use a Queue to pass messages from
    the background thread (robot->client) to the main thread which does all ws operations.
    """
    logger.info("[StateProxy] Client connected, connecting to robot...")

    try:
        target = ws_client.create_connection(REGGIE_STATE_WS_URL, timeout=10)
        logger.info("[StateProxy] Connected to robot state WebSocket")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"[StateProxy] Failed to connect to robot: {error_msg}")
        # Send error and close with proper WebSocket close frame
        if "503" in error_msg or "Backend not running" in error_msg:
            send_ws_error_and_close(ws, "robot_daemon_not_running",
                                    "Robot daemon is not running. Please start it from the Control page.")
        else:
            send_ws_error_and_close(ws, "connection_failed",
                                    f"Failed to connect to robot: {error_msg}")
        return

    running = True
    send_queue = Queue()  # Thread-safe queue for robot->browser messages
    CLOSE_SENTINEL = object()  # Marker to signal close

    def robot_to_queue():
        """Background thread: reads from robot, puts messages in queue.
        Does NOT touch the browser ws object."""
        nonlocal running
        try:
            while running:
                opcode, data = target.recv_data(control_frame=True)
                if opcode == ws_client.ABNF.OPCODE_TEXT:
                    send_queue.put(('text', data.decode('utf-8')))
                elif opcode == ws_client.ABNF.OPCODE_BINARY:
                    send_queue.put(('binary', data))
                elif opcode == ws_client.ABNF.OPCODE_CLOSE:
                    logger.info("[StateProxy] Robot closed connection")
                    send_queue.put(CLOSE_SENTINEL)
                    break
                elif opcode == ws_client.ABNF.OPCODE_PING:
                    target.pong(data)
        except Exception as e:
            logger.debug(f"[StateProxy] Robot reader ended: {e}")
            send_queue.put(('error', str(e)))
        finally:
            running = False
            try:
                target.close()
            except Exception:
                pass

    thread = threading.Thread(target=robot_to_queue, daemon=True)
    thread.start()

    try:
        while running:
            # Drain the queue - send all robot messages to browser
            # This is the ONLY place we call ws.send()
            try:
                while True:
                    item = send_queue.get_nowait()
                    if item is CLOSE_SENTINEL:
                        logger.info("[StateProxy] Got close sentinel, closing browser ws")
                        running = False
                        break
                    msg_type, payload = item
                    if msg_type == 'text':
                        ws.send(payload)
                    elif msg_type == 'binary':
                        ws.send(payload)
                    elif msg_type == 'error':
                        ws.send(json.dumps({"type": "error", "error": "connection_lost",
                                            "message": f"Connection to robot lost: {payload}"}))
                        running = False
                        break
            except Empty:
                pass

            if not running:
                break

            # Check for browser->robot messages (short timeout to stay responsive)
            msg = ws.receive(timeout=0.1)
            if msg is not None:
                if isinstance(msg, bytes):
                    target.send_binary(msg)
                else:
                    target.send(msg)

    except Exception as e:
        logger.debug(f"[StateProxy] Main loop ended: {e}")
    finally:
        running = False
        try:
            target.close()
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass


@app.route('/api/team-videos/<team>')
def api_team_videos(team):
    """Get recent videos for a specific team"""
    # URL decode the team name
    team_name = team.replace('-', ' ').title()
    if team_name == 'Liverpool Fc':
        team_name = 'Liverpool FC'

    videos = fetch_team_videos(team_name, max_videos=10)
    return jsonify({
        'team': team_name,
        'videos': videos,
    })


@app.route('/api/all-team-videos')
def api_all_team_videos():
    """Get recent videos for all teams"""
    return jsonify(get_all_team_videos())


# ============================================
# AI Studio API Endpoints
# ============================================

@app.route('/api/ai/generate', methods=['POST'])
def api_ai_generate():
    """
    Generate an image using ComfyUI.

    All processing happens locally - nothing is sent to external servers.
    """
    try:
        params = request.get_json()

        # Validate required fields
        if not params.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400

        # Check if ComfyUI is running
        comfy_status = check_comfy_status()
        if not comfy_status['running']:
            return jsonify({'error': 'ComfyUI is not running. Start it first.'}), 503

        # Generate unique ID for this generation
        gen_id = str(uuid.uuid4())[:8]

        # Prepare generation parameters
        prompt = params.get('prompt', '')
        negative_prompt = params.get('negative_prompt', '')
        model = params.get('model', 'juggernautXL_juggXIByRundiffusion.safetensors')
        width = int(params.get('width', 1024))
        height = int(params.get('height', 1024))
        seed = int(params.get('seed', -1))
        steps = int(params.get('steps', 25))
        cfg_scale = float(params.get('cfg_scale', 7.0))
        sampler = params.get('sampler', 'euler')
        loras = params.get('loras', [])  # List of {filename, strength} dicts
        batch_size = max(1, min(20, int(params.get('batch_size', 1))))  # Clamp to 1-20

        # img2img parameters
        input_image = params.get('input_image')  # Filename of uploaded image
        denoise = float(params.get('denoise', 0.75))  # img2img strength

        # Validate input image exists if provided
        if input_image:
            input_path = COMFY_DIR / 'input' / input_image
            if not input_path.exists():
                return jsonify({'error': f'Input image not found: {input_image}. Please re-upload.'}), 400

        # If seed is -1, generate a random one
        if seed == -1:
            import random
            seed = random.randint(0, 2147483647)

        # Build ComfyUI workflow based on mode
        if input_image:
            # img2img mode - batch_size not applicable (single input image)
            workflow = build_img2img_workflow(
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=model,
                image_filename=input_image,
                denoise=denoise,
                seed=seed,
                steps=steps,
                cfg_scale=cfg_scale,
                sampler=sampler,
                loras=loras,
            )
            actual_batch_size = 1  # img2img is single image
        else:
            # txt2img mode - supports batch generation
            workflow = build_txt2img_workflow(
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=model,
                width=width,
                height=height,
                seed=seed,
                steps=steps,
                cfg_scale=cfg_scale,
                sampler=sampler,
                loras=loras,
                batch_size=batch_size,
            )
            actual_batch_size = batch_size

        # Send to ComfyUI
        result = send_to_comfyui(workflow, gen_id, actual_batch_size)

        if result.get('error'):
            return jsonify({'error': result['error']}), 500

        # NOTE: We do NOT auto-save to database. User must explicitly click "Save to Gallery".
        # This keeps generation history opt-in only, per user privacy preference.

        # Return images array (for batch support) along with params
        images = result.get('images', [])
        return jsonify({
            'images': images,
            'seed': seed,
            'batch_size': actual_batch_size,
            'params': {
                'prompt': prompt,
                'negative_prompt': negative_prompt,
                'model': model,
                'width': width,
                'height': height,
                'seed': seed,
                'steps': steps,
                'cfg_scale': cfg_scale,
                'sampler': sampler,
            }
        })

    except httpx.TimeoutException:
        return jsonify({'error': 'ComfyUI request timed out. Try again or check if ComfyUI is responding.'}), 504
    except Exception as e:
        import traceback
        traceback.print_exc()  # Log full trace for debugging
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/image/<gen_id>')
def api_ai_image(gen_id):
    """Serve a generated image."""
    # Look for the image in generations directory
    for ext in ['.png', '.jpg', '.jpeg']:
        image_path = GENERATIONS_DIR / f'{gen_id}{ext}'
        if image_path.exists():
            return send_file(str(image_path), mimetype='image/png')

    # Check date-based directories
    today = datetime.now()
    for days_back in range(7):
        check_date = today - timedelta(days=days_back)
        date_dir = GENERATIONS_DIR / check_date.strftime('%Y/%m/%d')
        for ext in ['.png', '.jpg']:
            image_path = date_dir / f'{gen_id}_full{ext}'
            if image_path.exists():
                return send_file(str(image_path), mimetype='image/png')

    return jsonify({'error': 'Image not found'}), 404


@app.route('/api/ai/image/<gen_id>/thumb')
def api_ai_image_thumb(gen_id):
    """Serve a thumbnail of a generated image."""
    today = datetime.now()
    for days_back in range(30):
        check_date = today - timedelta(days=days_back)
        date_dir = GENERATIONS_DIR / check_date.strftime('%Y/%m/%d')
        thumb_path = date_dir / f'{gen_id}_thumb.jpg'
        if thumb_path.exists():
            return send_file(str(thumb_path), mimetype='image/jpeg')

    # Fall back to full image
    return api_ai_image(gen_id)


@app.route('/api/ai/models')
def api_ai_models():
    """Get list of available models."""
    return jsonify(get_available_models())


@app.route('/api/ai/loras')
def api_ai_loras():
    """Get list of available LoRAs."""
    return jsonify(get_available_loras())


@app.route('/api/ai/model-tips/<model_filename>')
def api_ai_model_tips(model_filename):
    """Get tips for a specific model."""
    return jsonify(get_model_tips(model_filename))


@app.route('/api/ai/comfy-status')
def api_ai_comfy_status():
    """Get ComfyUI status."""
    return jsonify(check_comfy_status())


@app.route('/api/ai/save', methods=['POST'])
def api_ai_save():
    """
    Explicitly save a generation to the gallery.
    Only called when user clicks 'Save to Gallery'.
    Supports both images and videos.
    """
    try:
        data = request.get_json()
        gen_id = data.get('id')
        params = data.get('params', {})
        is_video = data.get('is_video', False)

        if not gen_id:
            return jsonify({'error': 'Generation ID required'}), 400

        output_path_str = None
        thumbnail_path_str = None

        if is_video:
            # Check for video file in ComfyUI output directory
            output_dir = COMFY_DIR / 'output'
            video_path = None
            for ext in ['.mp4', '.webm', '.gif']:
                pattern = f'boomshakalaka_video_{gen_id}*{ext}'
                matches = list(output_dir.glob(pattern))
                if matches:
                    video_path = matches[0]
                    break

            if not video_path:
                # Try most recent video as fallback
                for ext in ['.mp4', '.webm']:
                    recent = list(output_dir.glob(f'*{ext}'))
                    if recent:
                        recent.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        video_path = recent[0]
                        break

            if not video_path:
                return jsonify({'error': 'Video file not found'}), 404

            output_path_str = str(video_path)
            # For videos, we don't have a thumbnail - use the video path
            # The gallery will need to handle video previews differently
            thumbnail_path_str = output_path_str
        else:
            # Check if image file exists
            image_path = GENERATIONS_DIR / f'{gen_id}.png'
            if not image_path.exists():
                # Also check for batch images (gen_id_0, gen_id_1, etc.)
                for ext in ['.png', '.jpg', '.jpeg']:
                    test_path = GENERATIONS_DIR / f'{gen_id}{ext}'
                    if test_path.exists():
                        image_path = test_path
                        break
                else:
                    return jsonify({'error': 'Image file not found'}), 404

            output_path_str = str(image_path)
            thumbnail_path_str = output_path_str

        # Save to database
        save_generation(
            gen_id=gen_id,
            prompt=params.get('prompt', ''),
            negative_prompt=params.get('negative_prompt', ''),
            model=params.get('model', ''),
            width=params.get('width', 1024),
            height=params.get('height', 1024),
            seed=params.get('seed', 0),
            steps=params.get('steps', 25),
            cfg_scale=params.get('cfg_scale', 7.0),
            sampler=params.get('sampler', 'euler'),
            output_path=output_path_str,
            thumbnail_path=thumbnail_path_str,
            workflow_json=json.dumps(params.get('workflow', {})),
        )

        return jsonify({'saved': True, 'id': gen_id, 'is_video': is_video})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/generation/<gen_id>')
def api_ai_generation(gen_id):
    """Get a saved generation's details for loading into the generate page."""
    import sqlite3

    db_path = DATABASES_DIR / 'generations.db'
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM generations WHERE id = ?', (gen_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify(dict(row))
        return jsonify({'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/generation/<gen_id>', methods=['DELETE'])
def api_ai_delete_generation(gen_id):
    """Delete a saved generation from the database and optionally its files."""
    import sqlite3

    db_path = DATABASES_DIR / 'generations.db'
    try:
        # Get the generation info first
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT output_path, thumbnail_path FROM generations WHERE id = ?', (gen_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({'error': 'Generation not found'}), 404

        # Delete from database
        conn.execute('DELETE FROM generations WHERE id = ?', (gen_id,))
        conn.commit()
        conn.close()

        # Optionally delete the image files
        delete_files = request.args.get('delete_files', 'false').lower() == 'true'
        if delete_files:
            if row['output_path']:
                output_path = Path(row['output_path'])
                if output_path.exists():
                    output_path.unlink()
            if row['thumbnail_path'] and row['thumbnail_path'] != row['output_path']:
                thumb_path = Path(row['thumbnail_path'])
                if thumb_path.exists():
                    thumb_path.unlink()

        return jsonify({'deleted': True, 'id': gen_id})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/generate-video', methods=['POST'])
def api_ai_generate_video():
    """
    Generate a video using ComfyUI with LTX, Wan, or HunyuanVideo models.

    All processing happens locally - nothing is sent to external servers.
    """
    logger.info("=" * 60)
    logger.info("VIDEO GENERATION REQUEST")
    logger.info("=" * 60)

    try:
        params = request.get_json()
        logger.info(f"Request params: {json.dumps(params, indent=2)}")

        # Validate required fields
        if not params.get('prompt'):
            logger.error("Missing prompt")
            return jsonify({'error': 'Prompt is required'}), 400
        if not params.get('input_image'):
            logger.error("Missing input_image")
            return jsonify({'error': 'Input image is required for img2vid'}), 400

        # Validate input image exists
        input_image_path = COMFY_DIR / 'input' / params.get('input_image')
        logger.info(f"Input image path: {input_image_path}")
        logger.info(f"Input image exists: {input_image_path.exists()}")
        if not input_image_path.exists():
            logger.error(f"Input image not found: {input_image_path}")
            return jsonify({'error': f'Input image not found: {params.get("input_image")}. Please re-upload.'}), 400

        # Check if ComfyUI is running
        comfy_status = check_comfy_status()
        logger.info(f"ComfyUI status: {comfy_status}")
        if not comfy_status['running']:
            logger.error("ComfyUI is not running")
            return jsonify({'error': 'ComfyUI is not running. Start it first.'}), 503

        # Generate unique ID for this generation
        gen_id = str(uuid.uuid4())[:8]
        logger.info(f"Generation ID: {gen_id}")

        # Prepare generation parameters
        prompt = params.get('prompt', '')
        input_image = params.get('input_image')
        video_model = params.get('video_model', 'ltxv-13b-0.9.8-distilled-fp8.safetensors')
        width = int(params.get('width', 768))
        height = int(params.get('height', 768))
        frames = int(params.get('frames', 49))
        fps = int(params.get('fps', 24))
        seed = int(params.get('seed', -1))
        steps = int(params.get('steps', 25))
        cfg_scale = float(params.get('cfg_scale', 7.0))
        motion_strength = float(params.get('motion_strength', 0.7))

        # Model-specific optional parameters
        negative_prompt = params.get('negative_prompt')  # Common to all models
        # LTX-specific
        strength = params.get('strength')
        if strength is not None:
            strength = float(strength)
        max_shift = params.get('max_shift')
        if max_shift is not None:
            max_shift = float(max_shift)
        base_shift = params.get('base_shift')
        if base_shift is not None:
            base_shift = float(base_shift)
        # Wan-specific
        shift = params.get('shift')
        if shift is not None:
            shift = float(shift)
        scheduler = params.get('scheduler')  # unipc, euler, ddim
        # Hunyuan-specific
        embedded_cfg_scale = params.get('embedded_cfg_scale')
        if embedded_cfg_scale is not None:
            embedded_cfg_scale = float(embedded_cfg_scale)
        # LTX sampler selection
        sampler = params.get('sampler')  # euler, dpmpp_2m, etc.
        # Common encoding params
        crf = params.get('crf')
        if crf is not None:
            crf = int(crf)

        # If seed is -1, generate a random one
        if seed == -1:
            import random
            seed = random.randint(0, 2147483647)

        logger.info(f"Video model: {video_model}")
        logger.info(f"Dimensions: {width}x{height}, frames: {frames}, fps: {fps}")
        logger.info(f"Seed: {seed}, steps: {steps}, cfg: {cfg_scale}, motion: {motion_strength}")

        # Determine model type
        if 'ltx' in video_model.lower():
            model_type = 'ltx'
        elif 'wan' in video_model.lower():
            model_type = 'wan'
        elif 'hunyuan' in video_model.lower():
            model_type = 'hunyuan'
        else:
            model_type = 'ltx'  # Default

        logger.info(f"Model type detected: {model_type}")

        # Build video generation workflow
        logger.info("Building video workflow...")
        workflow = build_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            model_type=model_type,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            motion_strength=motion_strength,
            gen_id=gen_id,
            # Model-specific params
            negative_prompt=negative_prompt,
            fps=fps,
            strength=strength,              # LTX
            max_shift=max_shift,            # LTX
            base_shift=base_shift,          # LTX
            sampler=sampler,                # LTX
            shift=shift,                    # Wan
            scheduler=scheduler,            # Wan
            embedded_cfg_scale=embedded_cfg_scale,  # Hunyuan
            crf=crf,                        # All (encoding quality)
        )
        logger.info(f"Workflow built with {len(workflow)} nodes")
        logger.debug(f"Workflow nodes: {list(workflow.keys())}")

        # Send to ComfyUI with extended timeout for video (30 minutes)
        logger.info("Sending workflow to ComfyUI (30 min timeout for video)...")
        result = send_to_comfyui(workflow, gen_id, batch_size=1, max_wait=1800)
        logger.info(f"ComfyUI result: {result}")

        if result.get('error'):
            logger.error(f"ComfyUI returned error: {result['error']}")
            return jsonify({'error': result['error']}), 500

        # Look for video output
        logger.info("Looking for video output...")
        video_path = None
        output_dir = COMFY_DIR / 'output'
        logger.info(f"Output directory: {output_dir}")

        # List recent files in output dir for debugging
        try:
            recent_files = sorted(output_dir.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)[:20]
            logger.info(f"Recent files in output: {[f.name for f in recent_files]}")
        except Exception as e:
            logger.warning(f"Could not list output dir: {e}")

        for ext in ['.mp4', '.webm', '.gif']:
            pattern = f'boomshakalaka_video_{gen_id}*{ext}'
            logger.debug(f"Trying pattern: {pattern}")
            matches = list(output_dir.glob(pattern))
            logger.debug(f"Matches: {matches}")
            if matches:
                video_path = matches[0]
                logger.info(f"Found video with pattern: {video_path}")
                break

        if not video_path:
            logger.info("No exact match, trying recent videos...")
            # Try general pattern
            for ext in ['.mp4', '.webm']:
                recent = list(output_dir.glob(f'*{ext}'))
                logger.debug(f"Found {len(recent)} {ext} files")
                if recent:
                    recent.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    video_path = recent[0]
                    logger.info(f"Using most recent video: {video_path}")
                    break

        if video_path:
            logger.info(f"SUCCESS! Video found: {video_path}")
            return jsonify({
                'video_url': f'/api/ai/video/{gen_id}',
                'id': gen_id,
                'seed': seed,
                'frames': frames,
                'fps': fps,
            })
        else:
            logger.error("Video generation completed but no output file found!")
            return jsonify({'error': 'Video generation completed but output not found'}), 500

    except httpx.TimeoutException:
        logger.error("ComfyUI request timed out")
        return jsonify({'error': 'ComfyUI request timed out. Video generation may take several minutes. Check ComfyUI console.'}), 504
    except Exception as e:
        import traceback
        logger.error(f"Exception in video generation: {e}")
        logger.error(traceback.format_exc())
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/<gen_id>')
def api_ai_video(gen_id):
    """Serve a generated video file."""
    # First, check database for saved video with output_path
    db_path = DATABASES_DIR / 'generations.db'
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('SELECT output_path FROM generations WHERE id = ?', (gen_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row['output_path']:
                video_path = Path(row['output_path'])
                if video_path.exists():
                    ext = video_path.suffix.lower()
                    mimetype = 'video/mp4' if ext == '.mp4' else 'video/webm' if ext == '.webm' else 'image/gif'
                    return send_file(str(video_path), mimetype=mimetype)
        except Exception as e:
            logger.error(f"Error checking database for video: {e}")

    output_dir = COMFY_DIR / 'output'

    # Find the video file by pattern
    for ext in ['.mp4', '.webm', '.gif']:
        pattern = f'boomshakalaka_video_{gen_id}*{ext}'
        matches = list(output_dir.glob(pattern))
        if matches:
            return send_file(matches[0], mimetype=f'video/{ext[1:]}')

    # Fallback to most recent video
    for ext in ['.mp4', '.webm']:
        recent = list(output_dir.glob(f'*{ext}'))
        if recent:
            recent.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            return send_file(recent[0], mimetype=f'video/{ext[1:]}')

    return jsonify({'error': 'Video not found'}), 404


# ============================================================================
# VIDEO STUDIO API ENDPOINTS
# ============================================================================

@app.route('/api/ai/video/model-params')
def api_ai_video_model_params():
    """Get all video model parameters for frontend rendering."""
    return jsonify({
        'available': VIDEO_PARAMS_AVAILABLE,
        'models': get_all_model_params_json() if VIDEO_PARAMS_AVAILABLE else {}
    })


@app.route('/api/ai/video/extract-frame', methods=['POST'])
def api_ai_video_extract_frame():
    """Extract first or last frame from a video file.

    Used for video continuation - extract last frame to use as input for next segment.

    Request JSON:
        video_path: Path to video file (relative to ComfyUI output or absolute)
        video_id: Alternatively, video generation ID to look up
        position: 'first' or 'last' (default: 'last')
        output_name: Optional output filename (default: auto-generated)
    """
    if not VIDEO_UTILS_AVAILABLE:
        return jsonify({'error': 'Video utils not available. FFmpeg may not be installed.'}), 503

    try:
        params = request.get_json()
        video_path = params.get('video_path')
        video_id = params.get('video_id')
        position = params.get('position', 'last')
        output_name = params.get('output_name')

        # Find video file
        if video_path:
            video_file = Path(video_path)
            if not video_file.is_absolute():
                video_file = COMFY_DIR / 'output' / video_path
        elif video_id:
            # Look up video by generation ID
            output_dir = COMFY_DIR / 'output'
            video_file = None
            for ext in ['.mp4', '.webm', '.gif']:
                matches = list(output_dir.glob(f'*{video_id}*{ext}'))
                if matches:
                    video_file = matches[0]
                    break
            if not video_file:
                return jsonify({'error': f'Video not found for ID: {video_id}'}), 404
        else:
            return jsonify({'error': 'Either video_path or video_id is required'}), 400

        if not video_file.exists():
            return jsonify({'error': f'Video file not found: {video_file}'}), 404

        # Generate output filename
        if not output_name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_name = f'frame_{position}_{timestamp}.png'

        # Output to ComfyUI input directory for immediate use
        output_path = COMFY_DIR / 'input' / output_name

        # Extract frame
        video_utils = get_video_utils()
        if position == 'first':
            result_path = video_utils.extract_first_frame(video_file, output_path)
        else:
            result_path = video_utils.extract_last_frame(video_file, output_path)

        logger.info(f"Extracted {position} frame from {video_file} to {result_path}")

        return jsonify({
            'success': True,
            'frame_path': str(result_path),
            'frame_filename': result_path.name,
            'source_video': str(video_file),
            'position': position
        })

    except Exception as e:
        logger.error(f"Error extracting frame: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/info', methods=['POST'])
def api_ai_video_info():
    """Get video metadata (duration, dimensions, fps, frame count)."""
    if not VIDEO_UTILS_AVAILABLE:
        return jsonify({'error': 'Video utils not available'}), 503

    try:
        params = request.get_json()
        video_path = params.get('video_path')
        video_id = params.get('video_id')

        # Find video file
        if video_path:
            video_file = Path(video_path)
            if not video_file.is_absolute():
                video_file = COMFY_DIR / 'output' / video_path
        elif video_id:
            output_dir = COMFY_DIR / 'output'
            video_file = None
            for ext in ['.mp4', '.webm']:
                matches = list(output_dir.glob(f'*{video_id}*{ext}'))
                if matches:
                    video_file = matches[0]
                    break
            if not video_file:
                return jsonify({'error': f'Video not found for ID: {video_id}'}), 404
        else:
            return jsonify({'error': 'Either video_path or video_id is required'}), 400

        if not video_file.exists():
            return jsonify({'error': f'Video file not found: {video_file}'}), 404

        video_utils = get_video_utils()
        info = video_utils.get_video_info(video_file)
        info['video_path'] = str(video_file)

        return jsonify(info)

    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/stitch', methods=['POST'])
def api_ai_video_stitch():
    """Concatenate multiple video segments into a single video.

    Request JSON:
        video_paths: List of video paths (relative to ComfyUI output or absolute)
        video_ids: Alternatively, list of generation IDs
        output_name: Optional output filename
        crossfade_frames: Number of frames for crossfade transition (0 = hard cut)
    """
    if not VIDEO_UTILS_AVAILABLE:
        return jsonify({'error': 'Video utils not available'}), 503

    try:
        params = request.get_json()
        video_paths = params.get('video_paths', [])
        video_ids = params.get('video_ids', [])
        output_name = params.get('output_name')
        crossfade_frames = int(params.get('crossfade_frames', 0))

        # Resolve video files
        video_files = []
        output_dir = COMFY_DIR / 'output'

        if video_paths:
            for vp in video_paths:
                video_file = Path(vp)
                if not video_file.is_absolute():
                    video_file = output_dir / vp
                if not video_file.exists():
                    return jsonify({'error': f'Video not found: {vp}'}), 404
                video_files.append(video_file)
        elif video_ids:
            for vid in video_ids:
                found = False
                for ext in ['.mp4', '.webm']:
                    matches = list(output_dir.glob(f'*{vid}*{ext}'))
                    if matches:
                        video_files.append(matches[0])
                        found = True
                        break
                if not found:
                    return jsonify({'error': f'Video not found for ID: {vid}'}), 404
        else:
            return jsonify({'error': 'Either video_paths or video_ids is required'}), 400

        if len(video_files) < 2:
            return jsonify({'error': 'At least 2 videos required for stitching'}), 400

        # Generate output filename
        if not output_name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_name = f'stitched_{timestamp}.mp4'

        output_path = output_dir / output_name

        # Stitch videos
        video_utils = get_video_utils()
        result_path = video_utils.concatenate_videos(
            video_files, output_path, crossfade_frames=crossfade_frames
        )

        # Get info about result
        result_info = video_utils.get_video_info(result_path)

        logger.info(f"Stitched {len(video_files)} videos into {result_path}")

        return jsonify({
            'success': True,
            'output_path': str(result_path),
            'output_filename': result_path.name,
            'segment_count': len(video_files),
            'crossfade_frames': crossfade_frames,
            'duration': result_info['duration'],
            'video_url': f'/api/ai/video/{result_path.stem}'
        })

    except Exception as e:
        logger.error(f"Error stitching videos: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/sequence', methods=['POST'])
def api_ai_video_sequence_create():
    """Create a new video sequence for multi-segment video generation."""
    try:
        params = request.get_json()

        sequence_id = str(uuid.uuid4())[:12]
        name = params.get('name', 'Untitled Sequence')
        base_prompt = params.get('base_prompt', '')
        video_model = params.get('video_model', 'ltxv-13b-0.9.8-distilled-fp8.safetensors')
        width = int(params.get('width', 768))
        height = int(params.get('height', 768))
        fps = int(params.get('fps', 24))

        db_path = DATABASES_DIR / 'generations.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute('''
            INSERT INTO video_sequences (id, name, base_prompt, video_model, width, height, fps, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
        ''', (sequence_id, name, base_prompt, video_model, width, height, fps))
        conn.commit()
        conn.close()

        logger.info(f"Created video sequence: {sequence_id}")

        return jsonify({
            'success': True,
            'id': sequence_id,
            'name': name,
            'video_model': video_model,
            'width': width,
            'height': height,
            'fps': fps
        })

    except Exception as e:
        logger.error(f"Error creating sequence: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/sequence/<sequence_id>', methods=['GET'])
def api_ai_video_sequence_get(sequence_id):
    """Get a video sequence and its segments."""
    try:
        db_path = DATABASES_DIR / 'generations.db'
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Get sequence
        cursor = conn.execute('SELECT * FROM video_sequences WHERE id = ?', (sequence_id,))
        sequence = cursor.fetchone()
        if not sequence:
            conn.close()
            return jsonify({'error': 'Sequence not found'}), 404

        # Get segments
        cursor = conn.execute('''
            SELECT * FROM video_segments
            WHERE sequence_id = ?
            ORDER BY segment_order
        ''', (sequence_id,))
        segments = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            'sequence': dict(sequence),
            'segments': segments
        })

    except Exception as e:
        logger.error(f"Error getting sequence: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/sequence/<sequence_id>/segment', methods=['POST'])
def api_ai_video_sequence_add_segment(sequence_id):
    """Add a segment to a video sequence.

    This records the segment metadata. The actual video generation
    should be done via /api/ai/generate-video with sequence_id parameter.
    """
    try:
        params = request.get_json()

        segment_id = str(uuid.uuid4())[:12]
        prompt = params.get('prompt', '')
        seed = params.get('seed')
        video_path = params.get('video_path')
        last_frame_path = params.get('last_frame_path')
        duration = params.get('duration')

        db_path = DATABASES_DIR / 'generations.db'
        conn = sqlite3.connect(str(db_path))

        # Get next segment order
        cursor = conn.execute('''
            SELECT COALESCE(MAX(segment_order), -1) + 1 as next_order
            FROM video_segments WHERE sequence_id = ?
        ''', (sequence_id,))
        next_order = cursor.fetchone()[0]

        # Insert segment
        conn.execute('''
            INSERT INTO video_segments (id, sequence_id, segment_order, prompt, seed, video_path, last_frame_path, duration, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed')
        ''', (segment_id, sequence_id, next_order, prompt, seed, video_path, last_frame_path, duration))

        # Update sequence total duration
        cursor = conn.execute('''
            SELECT COALESCE(SUM(duration), 0) as total FROM video_segments WHERE sequence_id = ?
        ''', (sequence_id,))
        total_duration = cursor.fetchone()[0]
        conn.execute('UPDATE video_sequences SET total_duration = ? WHERE id = ?', (total_duration, sequence_id))

        conn.commit()
        conn.close()

        logger.info(f"Added segment {segment_id} to sequence {sequence_id}")

        return jsonify({
            'success': True,
            'segment_id': segment_id,
            'segment_order': next_order,
            'total_duration': total_duration
        })

    except Exception as e:
        logger.error(f"Error adding segment: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/video/sequences', methods=['GET'])
def api_ai_video_sequences_list():
    """List all video sequences."""
    try:
        db_path = DATABASES_DIR / 'generations.db'
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute('''
            SELECT vs.*, COUNT(seg.id) as segment_count
            FROM video_sequences vs
            LEFT JOIN video_segments seg ON vs.id = seg.sequence_id
            GROUP BY vs.id
            ORDER BY vs.created_at DESC
        ''')
        sequences = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({'sequences': sequences})

    except Exception as e:
        logger.error(f"Error listing sequences: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/debug/outputs')
def api_ai_debug_outputs():
    """List recent files in ComfyUI output directory for debugging."""
    logger.info("Debug: Listing output directory")
    output_dir = COMFY_DIR / 'output'

    files = []
    try:
        for f in sorted(output_dir.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            files.append({
                'name': f.name,
                'size': f.stat().st_size,
                'mtime': datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                'is_video': f.suffix.lower() in ['.mp4', '.webm', '.gif'],
            })
    except Exception as e:
        logger.error(f"Error listing output dir: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'output_dir': str(output_dir),
        'file_count': len(files),
        'files': files
    })


@app.route('/api/ai/debug/workflow', methods=['POST'])
def api_ai_debug_workflow():
    """Return the workflow that would be generated without executing."""
    logger.info("Debug: Building workflow preview")

    try:
        params = request.get_json()
        gen_id = 'debug_preview'

        prompt = params.get('prompt', 'test prompt')
        input_image = params.get('input_image', 'test.png')
        video_model = params.get('video_model', 'ltxv-13b-0.9.8-distilled-fp8.safetensors')
        width = int(params.get('width', 768))
        height = int(params.get('height', 768))
        frames = int(params.get('frames', 49))
        seed = int(params.get('seed', 12345))
        steps = int(params.get('steps', 25))
        cfg_scale = float(params.get('cfg_scale', 7.0))
        motion_strength = float(params.get('motion_strength', 0.7))
        sampler = params.get('sampler')
        crf = params.get('crf')
        if crf is not None:
            crf = int(crf)

        # Determine model type
        if 'ltx' in video_model.lower():
            model_type = 'ltx'
        elif 'wan' in video_model.lower():
            model_type = 'wan'
        elif 'hunyuan' in video_model.lower():
            model_type = 'hunyuan'
        else:
            model_type = 'ltx'

        workflow = build_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            model_type=model_type,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            motion_strength=motion_strength,
            gen_id=gen_id,
            sampler=sampler,
            crf=crf,
        )

        return jsonify({
            'model_type': model_type,
            'node_count': len(workflow),
            'node_ids': list(workflow.keys()),
            'workflow': workflow
        })

    except Exception as e:
        logger.error(f"Error building debug workflow: {e}")
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/ai/debug/comfyui')
def api_ai_debug_comfyui():
    """Check ComfyUI status and available nodes."""
    logger.info("Debug: Checking ComfyUI status")

    try:
        import httpx

        # Check if ComfyUI is running
        status = check_comfy_status()

        # Get object info (available nodes)
        nodes_info = {}
        if status['running']:
            try:
                response = httpx.get(f'http://{COMFY_HOST}:{COMFY_PORT}/object_info', timeout=10)
                if response.status_code == 200:
                    all_nodes = response.json()
                    # Just return video-related nodes
                    video_node_prefixes = ['LTXV', 'Wan', 'Hunyuan', 'VHS_', 'Video']
                    for node_name in all_nodes:
                        if any(node_name.startswith(prefix) for prefix in video_node_prefixes):
                            nodes_info[node_name] = {
                                'input_types': list(all_nodes[node_name].get('input', {}).get('required', {}).keys()),
                            }
            except Exception as e:
                logger.warning(f"Could not get object info: {e}")

        return jsonify({
            'comfyui_status': status,
            'video_nodes': nodes_info,
            'video_node_count': len(nodes_info)
        })

    except Exception as e:
        logger.error(f"Error checking ComfyUI: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/upload', methods=['POST'])
def api_ai_upload():
    """Upload an image for img2img processing."""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Generate a unique filename
        import os
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
            return jsonify({'error': 'Invalid file type. Use PNG, JPG, or WebP'}), 400

        # Save to ComfyUI's input folder so it can be loaded
        upload_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
        comfy_input_dir = COMFY_DIR / 'input'
        comfy_input_dir.mkdir(parents=True, exist_ok=True)

        upload_path = comfy_input_dir / upload_filename
        file.save(str(upload_path))

        # Also save a copy to our uploads folder for reference
        uploads_dir = PROJECT_ROOT / 'data' / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(str(upload_path), str(uploads_dir / upload_filename))

        return jsonify({
            'filename': upload_filename,
            'path': str(upload_path),
            'url': f'/api/ai/upload/{upload_filename}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/upload/<filename>')
def api_ai_upload_get(filename):
    """Serve an uploaded image."""
    # Check ComfyUI input folder
    image_path = COMFY_DIR / 'input' / filename
    if image_path.exists():
        return send_file(str(image_path))

    # Check our uploads folder
    image_path = PROJECT_ROOT / 'data' / 'uploads' / filename
    if image_path.exists():
        return send_file(str(image_path))

    return jsonify({'error': 'Image not found'}), 404


@app.route('/api/ai/models/delete', methods=['POST'])
def api_ai_delete_model():
    """Delete a checkpoint model."""
    try:
        data = request.get_json()
        filename = data.get('filename')
        if not filename:
            return jsonify({'error': 'Filename required'}), 400

        result = delete_model(filename)
        if result.get('error'):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/loras/delete', methods=['POST'])
def api_ai_delete_lora():
    """Delete a LoRA."""
    try:
        data = request.get_json()
        filename = data.get('filename')
        if not filename:
            return jsonify({'error': 'Filename required'}), 400

        result = delete_lora(filename)
        if result.get('error'):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Track active downloads
active_downloads = {}


@app.route('/api/ai/models/download', methods=['POST'])
def api_ai_download_model():
    """Start downloading a model from URL."""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        model_type = data.get('type', 'checkpoint')  # 'checkpoint' or 'lora'

        if not url:
            return jsonify({'error': 'URL required'}), 400

        # Parse the URL to determine source
        url_info = parse_model_url(url)

        # Generate download ID
        download_id = str(uuid.uuid4())[:8]

        # Determine target directory
        if model_type == 'lora':
            target_dir = MODELS_DIR / 'loras'
        else:
            target_dir = MODELS_DIR / 'checkpoints'

        target_dir.mkdir(parents=True, exist_ok=True)

        # Start download in background thread
        import threading

        def download_file():
            import requests
            try:
                active_downloads[download_id] = {
                    'status': 'downloading',
                    'progress': 0,
                    'filename': None,
                    'error': None
                }

                # Handle different URL types
                download_url = url

                # Convert HuggingFace blob URLs to resolve URLs
                if 'huggingface.co' in url and '/blob/' in url:
                    download_url = url.replace('/blob/', '/resolve/')

                # For CivitAI, we need to handle the API differently
                if 'civitai.com' in url:
                    # Extract model version ID if it's a model page URL
                    if '/models/' in url and '?modelVersionId=' in url:
                        import re
                        match = re.search(r'modelVersionId=(\d+)', url)
                        if match:
                            version_id = match.group(1)
                            download_url = f'https://civitai.com/api/download/models/{version_id}'
                    elif '/models/' in url:
                        # Try to get the download URL from the API
                        # For now, just use the URL as-is and hope it redirects
                        pass

                # Start download with streaming
                headers = {'User-Agent': 'Boomshakalaka-AI-Studio/1.0'}
                response = requests.get(download_url, stream=True, headers=headers, allow_redirects=True, timeout=30)
                response.raise_for_status()

                # Try to get filename from Content-Disposition header
                content_disp = response.headers.get('Content-Disposition', '')
                if 'filename=' in content_disp:
                    import re
                    match = re.search(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\n]+)', content_disp)
                    if match:
                        filename = match.group(1)
                    else:
                        filename = url.split('/')[-1].split('?')[0]
                else:
                    filename = url.split('/')[-1].split('?')[0]

                # Ensure valid extension
                if not filename.endswith(('.safetensors', '.ckpt', '.pt')):
                    filename += '.safetensors'

                active_downloads[download_id]['filename'] = filename
                target_path = target_dir / filename

                # Get total size if available
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                active_downloads[download_id]['progress'] = int((downloaded / total_size) * 100)

                active_downloads[download_id]['status'] = 'complete'
                active_downloads[download_id]['progress'] = 100

            except Exception as e:
                active_downloads[download_id]['status'] = 'error'
                active_downloads[download_id]['error'] = str(e)

        thread = threading.Thread(target=download_file)
        thread.daemon = True
        thread.start()

        return jsonify({
            'download_id': download_id,
            'source': url_info['source'],
            'status': 'started'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/models/download/<download_id>')
def api_ai_download_status(download_id):
    """Get download progress."""
    if download_id not in active_downloads:
        return jsonify({'error': 'Download not found'}), 404

    return jsonify(active_downloads[download_id])


def build_txt2img_workflow(prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, loras=None, batch_size=1):
    """Build a ComfyUI workflow for text-to-image generation.

    Args:
        loras: List of dicts with 'filename' and 'strength' (0.0-2.0)
        batch_size: Number of images to generate in one batch (1-20)
    """
    loras = loras or []
    batch_size = max(1, min(20, batch_size))  # Clamp to 1-20

    # ComfyUI uses node-based workflows defined as JSON
    # Base nodes that are always present
    workflow = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": model
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": batch_size
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "boomshakalaka",
                "images": ["8", 0]
            }
        }
    }

    # Track the current model and clip outputs for chaining LoRAs
    current_model_source = ["4", 0]  # CheckpointLoader model output
    current_clip_source = ["4", 1]   # CheckpointLoader clip output

    # Add LoRA loaders if any are specified
    # Each LoRA chains from the previous one's output
    for i, lora in enumerate(loras):
        lora_filename = lora.get('filename', '')
        lora_strength = float(lora.get('strength', 1.0))

        if not lora_filename:
            continue

        node_id = f"lora_{i}"
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_filename,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": current_model_source,
                "clip": current_clip_source,
            }
        }
        # Update current sources to this LoRA's outputs
        current_model_source = [node_id, 0]
        current_clip_source = [node_id, 1]

    # CLIP text encoders - use final model/clip source (after LoRAs if any)
    workflow["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": prompt,
            "clip": current_clip_source
        }
    }
    workflow["7"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": negative_prompt or "",
            "clip": current_clip_source
        }
    }

    # KSampler - uses final model source
    workflow["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg_scale,
            "sampler_name": sampler,
            "scheduler": "normal",
            "denoise": 1.0,
            "model": current_model_source,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0]
        }
    }

    return workflow


def build_img2img_workflow(prompt, negative_prompt, model, image_filename, denoise, seed, steps, cfg_scale, sampler, loras=None):
    """Build a ComfyUI workflow for image-to-image generation.

    Args:
        image_filename: Name of the uploaded image in ComfyUI's input folder
        denoise: Strength of denoising (0.0 = no change, 1.0 = complete regeneration)
        loras: List of dicts with 'filename' and 'strength' (0.0-2.0)
    """
    loras = loras or []

    # Base workflow for img2img
    workflow = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": model
            }
        },
        # Load the input image
        "10": {
            "class_type": "LoadImage",
            "inputs": {
                "image": image_filename
            }
        },
        # Encode the image to latent space
        "11": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["10", 0],
                "vae": ["4", 2]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "boomshakalaka_img2img",
                "images": ["8", 0]
            }
        }
    }

    # Track the current model and clip outputs for chaining LoRAs
    current_model_source = ["4", 0]
    current_clip_source = ["4", 1]

    # Add LoRA loaders if any are specified
    for i, lora in enumerate(loras):
        lora_filename = lora.get('filename', '')
        lora_strength = float(lora.get('strength', 1.0))

        if not lora_filename:
            continue

        node_id = f"lora_{i}"
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": lora_filename,
                "strength_model": lora_strength,
                "strength_clip": lora_strength,
                "model": current_model_source,
                "clip": current_clip_source,
            }
        }
        current_model_source = [node_id, 0]
        current_clip_source = [node_id, 1]

    # CLIP text encoders
    workflow["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": prompt,
            "clip": current_clip_source
        }
    }
    workflow["7"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": negative_prompt or "",
            "clip": current_clip_source
        }
    }

    # KSampler with denoise setting - uses the encoded image as latent
    workflow["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": seed,
            "steps": steps,
            "cfg": cfg_scale,
            "sampler_name": sampler,
            "scheduler": "normal",
            "denoise": denoise,  # Key difference from txt2img
            "model": current_model_source,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["11", 0]  # Use encoded image instead of empty latent
        }
    }

    return workflow


def build_video_workflow(prompt, input_image, video_model, model_type, width, height, frames, seed, steps, cfg_scale, motion_strength, gen_id,
                         negative_prompt=None, fps=24,
                         # LTX-specific params
                         strength=None, max_shift=None, base_shift=None, sampler=None,
                         # Wan-specific params
                         shift=None, scheduler=None,
                         # Hunyuan-specific params
                         embedded_cfg_scale=None,
                         # Common encoding params
                         crf=None):
    """Build a ComfyUI workflow for image-to-video generation.

    Supports LTX-Video, Wan2.1/2.2, and HunyuanVideo models.

    Common params:
        negative_prompt: Things to avoid in the video
        fps: Output video frame rate
        crf: Video quality (10-35, lower=better quality)

    LTX-specific params:
        strength: Image fidelity (0.5-1.0)
        max_shift, base_shift: Noise schedule parameters
        sampler: Sampling algorithm (euler, dpmpp_2m, etc.)

    Wan-specific params:
        motion_strength: Amount of motion (0-1)
        shift: Sampling shift parameter
        scheduler: Sampling scheduler (unipc/euler/ddim)

    Hunyuan-specific params:
        embedded_cfg_scale: Secondary guidance scale
    """
    if model_type == 'ltx':
        return build_ltx_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            gen_id=gen_id,
            negative_prompt=negative_prompt,
            strength=strength,
            max_shift=max_shift,
            base_shift=base_shift,
            fps=fps,
            motion_strength=motion_strength,
            sampler=sampler,
            crf=crf,
        )
    elif model_type == 'wan':
        return build_wan_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            motion_strength=motion_strength,
            gen_id=gen_id,
            shift=shift,
            scheduler=scheduler,
            fps=fps,
            crf=crf,
        )
    elif model_type == 'hunyuan':
        return build_hunyuan_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            gen_id=gen_id,
            negative_prompt=negative_prompt,
            embedded_cfg_scale=embedded_cfg_scale,
            fps=fps,
            crf=crf,
        )
    else:
        # Default to LTX
        return build_ltx_video_workflow(
            prompt=prompt,
            input_image=input_image,
            video_model=video_model,
            width=width,
            height=height,
            frames=frames,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
            gen_id=gen_id,
            negative_prompt=negative_prompt,
            fps=fps,
            sampler=sampler,
            crf=crf,
        )


def build_ltx_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, gen_id,
                             negative_prompt=None, strength=None, max_shift=None, base_shift=None, fps=25, motion_strength=0.7,
                             sampler=None, crf=None):
    """Build workflow for LTX-Video image-to-video generation.

    Uses native ComfyUI LTX Video nodes (built-in support).

    Args:
        negative_prompt: Custom negative prompt (default uses standard quality prompt)
        strength: Image fidelity 0.5-1.0 (higher = more faithful to input, less motion)
        max_shift: Noise schedule max shift (default 2.05)
        base_shift: Noise schedule base shift (default 0.95)
        fps: Output frame rate (default 25)
        motion_strength: 0.0-1.0, used to modulate strength parameter
        sampler: Sampling algorithm (default 'euler')
        crf: Video quality (lower = better, default 19)
    """
    # Apply defaults
    if negative_prompt is None:
        negative_prompt = "worst quality, inconsistent motion, blurry, jittery, distorted, watermarks, text"
    if strength is None:
        # Motion strength inversely affects image fidelity
        # Higher motion = lower strength = more divergence from input
        strength = 1.0 - (motion_strength * 0.4)  # Range: 0.6-1.0
    if max_shift is None:
        max_shift = 2.05
    if base_shift is None:
        base_shift = 0.95
    if sampler is None:
        sampler = 'euler'
    if crf is None:
        crf = 19

    logger.info("Building LTX video workflow (native nodes):")
    logger.info(f"  prompt: {prompt[:100]}...")
    logger.info(f"  input_image: {input_image}")
    logger.info(f"  video_model: {video_model}")
    logger.info(f"  dimensions: {width}x{height}")
    logger.info(f"  frames: {frames}, seed: {seed}, steps: {steps}, cfg: {cfg_scale}")
    logger.info(f"  strength: {strength}, max_shift: {max_shift}, base_shift: {base_shift}")
    logger.info(f"  gen_id: {gen_id}")

    workflow = {
        # 1. Load LTX Video model (checkpoint includes model + vae)
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": video_model
            }
        },
        # 2. Load T5 CLIP for LTX Video
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "t5xxl_fp16.safetensors",
                "type": "ltxv"
            }
        },
        # 3. Load input image
        "3": {
            "class_type": "LoadImage",
            "inputs": {
                "image": input_image
            }
        },
        # 4. Encode positive prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["2", 0]
            }
        },
        # 5. Encode negative prompt - NOW CONFIGURABLE
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": negative_prompt,
                "clip": ["2", 0]
            }
        },
        # 6. LTX Video conditioning (adds frame rate info)
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "frame_rate": float(fps)
            }
        },
        # 7. LTX Img to Video - outputs [positive, negative, latent]
        "7": {
            "class_type": "LTXVImgToVideo",
            "inputs": {
                "positive": ["6", 0],
                "negative": ["6", 1],
                "vae": ["1", 2],
                "image": ["3", 0],
                "width": width,
                "height": height,
                "length": frames,
                "batch_size": 1,
                "strength": strength  # NOW CONFIGURABLE
            }
        },
        # 8. LTX Scheduler - creates sigmas for sampling
        "8": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": steps,
                "max_shift": max_shift,  # NOW CONFIGURABLE
                "base_shift": base_shift,  # NOW CONFIGURABLE
                "stretch": True,
                "terminal": 0.1,
                "latent": ["7", 2]
            }
        },
        # 9. Random noise
        "9": {
            "class_type": "RandomNoise",
            "inputs": {
                "noise_seed": seed
            }
        },
        # 10. Sampler select
        "10": {
            "class_type": "KSamplerSelect",
            "inputs": {
                "sampler_name": sampler  # NOW CONFIGURABLE
            }
        },
        # 11. Model sampling LTX (patches model for LTX-specific sampling)
        "11": {
            "class_type": "ModelSamplingLTXV",
            "inputs": {
                "model": ["1", 0],
                "max_shift": max_shift,  # NOW CONFIGURABLE
                "base_shift": base_shift  # NOW CONFIGURABLE
            }
        },
        # 12. CFG Guider
        "12": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["11", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "cfg": cfg_scale
            }
        },
        # 13. SamplerCustomAdvanced - main sampling
        "13": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0],
                "guider": ["12", 0],
                "sampler": ["10", 0],
                "sigmas": ["8", 0],
                "latent_image": ["7", 2]
            }
        },
        # 14. VAE Decode
        "14": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["13", 0],
                "vae": ["1", 2]
            }
        },
        # 15. Save video
        "15": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["14", 0],
                "frame_rate": fps,  # NOW CONFIGURABLE
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": crf,  # NOW CONFIGURABLE
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            }
        }
    }

    logger.info(f"LTX workflow built with {len(workflow)} nodes: {list(workflow.keys())}")
    return workflow


def build_wan_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, motion_strength, gen_id, shift=None, scheduler=None, fps=24, crf=None):
    """Build workflow for Wan2.x image-to-video generation using ComfyUI-WanVideoWrapper.

    Args:
        motion_strength: 0.0-1.0, controls amount of motion (higher = more movement)
        shift: Sampling shift parameter (default 5.0)
        scheduler: Sampling scheduler - 'unipc', 'euler', or 'ddim'
        fps: Output video frame rate
        crf: Video quality (lower = better, default 19)
    """
    # Apply defaults for optional params
    if shift is None:
        shift = 5.0
    if scheduler is None:
        scheduler = "unipc"
    if crf is None:
        crf = 19

    # Motion strength affects the shift parameter - higher motion = higher shift
    # Also affects cfg - lower cfg with higher motion for more dynamic results
    effective_shift = shift * (0.8 + motion_strength * 0.4)  # Range: 0.8x to 1.2x of base shift
    effective_cfg = cfg_scale * (1.0 - motion_strength * 0.2)  # Slightly reduce cfg for more motion

    workflow = {
        # Load text encoder
        "1": {
            "class_type": "DownloadAndLoadWanT5TextEncoder",
            "inputs": {
                "model": "umt5-xxl-enc-fp8_e4m3fn.safetensors",
                "precision": "fp8_e4m3fn"
            }
        },
        # Load CLIP vision
        "2": {
            "class_type": "DownloadAndLoadWanClipVision",
            "inputs": {
                "model": "open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors",
                "precision": "fp16"
            }
        },
        # Load main video model
        "3": {
            "class_type": "DownloadAndLoadWanModel",
            "inputs": {
                "model": video_model,
                "precision": "fp8_scaled",
                "quantization": "disabled",
            }
        },
        # Load VAE
        "4": {
            "class_type": "DownloadAndLoadWanVAE",
            "inputs": {
                "model": "Wan2_2_VAE_bf16.safetensors",
                "precision": "bf16"
            }
        },
        # Load input image
        "5": {
            "class_type": "LoadImage",
            "inputs": {
                "image": input_image
            }
        },
        # Encode text
        "6": {
            "class_type": "WanTextEncode",
            "inputs": {
                "text_encoder": ["1", 0],
                "prompt": prompt,
            }
        },
        # Encode image with CLIP
        "7": {
            "class_type": "WanClipVisionEncode",
            "inputs": {
                "clip_vision": ["2", 0],
                "image": ["5", 0],
            }
        },
        # Sample video - motion_strength now affects shift and cfg
        "8": {
            "class_type": "WanSampler",
            "inputs": {
                "model": ["3", 0],
                "positive": ["6", 0],
                "image_embeds": ["7", 0],
                "width": width,
                "height": height,
                "num_frames": frames,
                "seed": seed,
                "steps": steps,
                "cfg": effective_cfg,
                "shift": effective_shift,
                "scheduler": scheduler,
            }
        },
        # Decode with VAE
        "9": {
            "class_type": "WanVAEDecode",
            "inputs": {
                "vae": ["4", 0],
                "latent": ["8", 0],
            }
        },
        # Save video
        "10": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["9", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": crf,  # NOW CONFIGURABLE
                "pingpong": False,
                "save_output": True,
            }
        }
    }

    logger.info(f"Wan workflow built: motion_strength={motion_strength}, effective_shift={effective_shift:.2f}, effective_cfg={effective_cfg:.2f}, crf={crf}")
    return workflow


def build_hunyuan_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, gen_id,
                                  negative_prompt=None, embedded_cfg_scale=None, fps=24, crf=None):
    """Build workflow for HunyuanVideo image-to-video generation.

    Args:
        embedded_cfg_scale: Secondary guidance scale for quality/creativity balance (default 6.0)
        negative_prompt: Things to avoid in the video (currently not used by HunyuanVideo sampler)
        fps: Output video frame rate
        crf: Video quality (lower = better, default 19)
    """
    # Apply defaults
    if embedded_cfg_scale is None:
        embedded_cfg_scale = 6.0
    if negative_prompt is None:
        negative_prompt = "worst quality, low quality, blurry, distorted, deformed, ugly, watermark, text"
    if crf is None:
        crf = 19

    workflow = {
        # Load HunyuanVideo model
        "1": {
            "class_type": "HyVideoModelLoader",
            "inputs": {
                "model": video_model,
                "precision": "fp16",
            }
        },
        # Load text encoder
        "2": {
            "class_type": "HyVideoTextEncoderLoader",
            "inputs": {
                "llm_model": "llava_llama3_fp8_scaled.safetensors",
                "clip_model": "clip_l.safetensors",
            }
        },
        # Load VAE
        "3": {
            "class_type": "HyVideoVAELoader",
            "inputs": {
                "vae_name": "hunyuan_video_vae_bf16.safetensors",
            }
        },
        # Load input image
        "4": {
            "class_type": "LoadImage",
            "inputs": {
                "image": input_image
            }
        },
        # Encode prompt
        "5": {
            "class_type": "HyVideoTextEncode",
            "inputs": {
                "text_encoder": ["2", 0],
                "prompt": prompt,
            }
        },
        # Image to video sampling
        "6": {
            "class_type": "HyVideoI2VSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["5", 0],
                "image": ["4", 0],
                "vae": ["3", 0],
                "width": width,
                "height": height,
                "num_frames": frames,
                "seed": seed,
                "steps": steps,
                "cfg": cfg_scale,
                "embedded_cfg_scale": embedded_cfg_scale,
            }
        },
        # Decode video
        "7": {
            "class_type": "HyVideoVAEDecode",
            "inputs": {
                "vae": ["3", 0],
                "latent": ["6", 0],
            }
        },
        # Save video
        "8": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["7", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": crf,  # NOW CONFIGURABLE
                "pingpong": False,
                "save_output": True,
            }
        }
    }

    logger.info(f"Hunyuan workflow built: embedded_cfg_scale={embedded_cfg_scale}, fps={fps}, crf={crf}")
    return workflow


def send_to_comfyui(workflow, gen_id, batch_size=1, max_wait=300):
    """Send a workflow to ComfyUI and wait for the result.

    Args:
        workflow: ComfyUI workflow JSON
        gen_id: Base generation ID
        batch_size: Expected number of images (for multi-image batches)
        max_wait: Maximum wait time in seconds (default 300 = 5 min, use 1800 for video)

    Returns:
        dict with 'images' array containing all generated images, or 'error'
    """
    import httpx
    import time

    logger.info(f"send_to_comfyui called for gen_id: {gen_id}, batch_size: {batch_size}, max_wait: {max_wait}s")

    try:
        # Queue the prompt
        logger.info(f"Posting to ComfyUI at http://{COMFY_HOST}:{COMFY_PORT}/prompt")
        logger.debug(f"Workflow has {len(workflow)} nodes: {list(workflow.keys())}")

        response = httpx.post(
            f'http://{COMFY_HOST}:{COMFY_PORT}/prompt',
            json={'prompt': workflow},
            timeout=30
        )

        logger.info(f"ComfyUI prompt response status: {response.status_code}")
        logger.debug(f"Response body: {response.text[:1000] if len(response.text) > 1000 else response.text}")

        if response.status_code != 200:
            logger.error(f"ComfyUI returned non-200 status: {response.status_code}")
            return {'error': f'ComfyUI error: {response.text}'}

        data = response.json()
        prompt_id = data.get('prompt_id')
        logger.info(f"Prompt ID: {prompt_id}")

        if not prompt_id:
            logger.error("No prompt_id in response")
            return {'error': 'No prompt ID returned'}

        # Poll for completion
        poll_interval = 1
        elapsed = 0

        logger.info(f"Polling for completion (max {max_wait}s)...")

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            # Check history
            history_response = httpx.get(
                f'http://{COMFY_HOST}:{COMFY_PORT}/history/{prompt_id}',
                timeout=10
            )

            if elapsed % 10 == 0:  # Log every 10 seconds
                logger.debug(f"Polling at {elapsed}s - status: {history_response.status_code}")

            if history_response.status_code == 200:
                history = history_response.json()
                if prompt_id in history:
                    logger.info(f"Found in history at {elapsed}s")
                    outputs = history[prompt_id].get('outputs', {})
                    logger.info(f"Output node IDs: {list(outputs.keys())}")

                    # Log all outputs for debugging
                    for node_id, node_output in outputs.items():
                        logger.info(f"Node {node_id} output keys: {list(node_output.keys())}")
                        logger.debug(f"Node {node_id} full output: {json.dumps(node_output, indent=2)[:500]}")

                    # Find the SaveImage output - collect ALL images for batch support
                    images_result = []
                    for node_id, node_output in outputs.items():
                        if 'images' in node_output:
                            logger.info(f"Found {len(node_output['images'])} images in node {node_id}")
                            for idx, img in enumerate(node_output['images']):
                                filename = img.get('filename')
                                subfolder = img.get('subfolder', '')
                                logger.info(f"Image {idx}: {filename}, subfolder: {subfolder}")

                                # Copy the image to our generations directory
                                src_path = COMFY_DIR / 'output' / subfolder / filename
                                logger.info(f"Source path: {src_path}, exists: {src_path.exists()}")

                                if src_path.exists():
                                    # Create date-based directory
                                    date_dir = GENERATIONS_DIR / datetime.now().strftime('%Y/%m/%d')
                                    date_dir.mkdir(parents=True, exist_ok=True)

                                    # Generate unique ID for each image in batch
                                    img_gen_id = f"{gen_id}_{idx}" if batch_size > 1 else gen_id

                                    # Copy to our directory
                                    dst_path = date_dir / f'{img_gen_id}_full.png'
                                    import shutil
                                    shutil.copy2(str(src_path), str(dst_path))
                                    logger.info(f"Copied to {dst_path}")

                                    # Also create a simple version in root for easy access
                                    simple_dst = GENERATIONS_DIR / f'{img_gen_id}.png'
                                    shutil.copy2(str(src_path), str(simple_dst))
                                    logger.info(f"Copied to {simple_dst}")

                                    images_result.append({
                                        'id': img_gen_id,
                                        'url': f'/api/ai/image/{img_gen_id}',
                                        'output_path': str(dst_path),
                                        'filename': filename
                                    })

                            # If we found images, return them all
                            if images_result:
                                logger.info(f"Returning {len(images_result)} images")
                                return {'images': images_result}

                        # Check for video outputs (gifs/videos from VHS_VideoCombine)
                        # VHS_VideoCombine uses 'gifs' key even for mp4 output
                        if 'gifs' in node_output:
                            logger.info(f"Found gifs/video in node {node_id}: {node_output['gifs']}")
                            for vid in node_output['gifs']:
                                filename = vid.get('filename')
                                subfolder = vid.get('subfolder', '')
                                logger.info(f"Video file: {filename}, subfolder: {subfolder}")
                                return {
                                    'output_path': str(COMFY_DIR / 'output' / subfolder / filename),
                                    'filename': filename,
                                    'is_video': True
                                }
                        if 'videos' in node_output:
                            logger.info(f"Found videos in node {node_id}: {node_output['videos']}")
                            for vid in node_output['videos']:
                                filename = vid.get('filename')
                                subfolder = vid.get('subfolder', '')
                                logger.info(f"Video file: {filename}, subfolder: {subfolder}")
                                return {
                                    'output_path': str(COMFY_DIR / 'output' / subfolder / filename),
                                    'filename': filename,
                                    'is_video': True
                                }

                    logger.warning("No images or videos found in any output node")
                    return {'error': 'No images or videos in output'}

        logger.error(f"Generation timed out after {max_wait}s")
        return {'error': 'Generation timed out'}

    except Exception as e:
        logger.error(f"Exception in send_to_comfyui: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'error': str(e)}


def save_generation(gen_id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, workflow_json, thumbnail_path=None):
    """Save generation metadata to database."""
    import sqlite3

    db_path = DATABASES_DIR / 'generations.db'
    conn = sqlite3.connect(str(db_path))

    # Use output_path as thumbnail if not specified
    if thumbnail_path is None:
        thumbnail_path = output_path

    # Use INSERT OR REPLACE to handle re-saving the same generation
    conn.execute('''
        INSERT OR REPLACE INTO generations (id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, thumbnail_path, workflow_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (gen_id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, thumbnail_path, workflow_json))

    conn.commit()
    conn.close()


# ============================================
# Main
# ============================================

# =============================================================================
# Theme Customization API
# =============================================================================

def load_themes():
    """Load themes from JSON file."""
    if THEMES_FILE.exists():
        try:
            with open(THEMES_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # Return default structure
    return {
        "active": "teal-gold",
        "themes": {
            "teal-gold": DEFAULT_THEME if DEFAULT_THEME else {
                "name": "Teal Gold",
                "prompt": "Dark teal background with gold accents",
                "css": {},
                "ttyd": {}
            }
        }
    }


def save_themes(data):
    """Save themes to JSON file."""
    THEMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(THEMES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@app.route('/api/themes')
def api_themes_list():
    """Get all saved themes."""
    themes_data = load_themes()
    return jsonify({
        'active': themes_data.get('active'),
        'themes': {
            key: {
                'name': theme.get('name', key),
                'prompt': theme.get('prompt', '')
            }
            for key, theme in themes_data.get('themes', {}).items()
        }
    })


@app.route('/api/themes/<theme_id>')
def api_theme_get(theme_id):
    """Get a specific theme's full data."""
    themes_data = load_themes()
    theme = themes_data.get('themes', {}).get(theme_id)
    if not theme:
        return jsonify({'error': 'Theme not found'}), 404
    return jsonify(theme)


@app.route('/api/themes/generate', methods=['POST'])
def api_themes_generate():
    """Generate a new theme from a natural language prompt."""
    if not THEME_GENERATOR_AVAILABLE:
        return jsonify({'error': 'Theme generator not available. Install anthropic package.'}), 500

    data = request.get_json()
    prompt = data.get('prompt', '').strip()

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    try:
        # Generate colors from Claude API
        colors = generate_theme_from_prompt(prompt)

        # Convert to CSS variables and ttyd theme
        css_vars = colors_to_css_variables(colors)
        ttyd_theme = colors_to_ttyd_theme(colors)
        ttyd_command = generate_ttyd_service_command(ttyd_theme)

        return jsonify({
            'success': True,
            'theme': {
                'name': colors.get('name', 'Custom Theme'),
                'prompt': prompt,
                'css': css_vars,
                'ttyd': ttyd_theme,
                'ttyd_command': ttyd_command
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/themes/save', methods=['POST'])
def api_themes_save():
    """Save a generated theme."""
    data = request.get_json()
    theme = data.get('theme')

    if not theme:
        return jsonify({'error': 'Theme data is required'}), 400

    # Generate a slug from the theme name
    name = theme.get('name', 'Custom Theme')
    theme_id = name.lower().replace(' ', '-')
    theme_id = re.sub(r'[^a-z0-9-]', '', theme_id)

    # Make unique if needed
    themes_data = load_themes()
    base_id = theme_id
    counter = 1
    while theme_id in themes_data.get('themes', {}):
        theme_id = f"{base_id}-{counter}"
        counter += 1

    # Save the theme
    if 'themes' not in themes_data:
        themes_data['themes'] = {}
    themes_data['themes'][theme_id] = theme

    save_themes(themes_data)

    return jsonify({
        'success': True,
        'theme_id': theme_id,
        'message': f'Theme "{name}" saved successfully'
    })


@app.route('/api/themes/apply', methods=['POST'])
def api_themes_apply():
    """Set a theme as active."""
    data = request.get_json()
    theme_id = data.get('theme_id')

    if not theme_id:
        return jsonify({'error': 'Theme ID is required'}), 400

    themes_data = load_themes()
    if theme_id not in themes_data.get('themes', {}):
        return jsonify({'error': 'Theme not found'}), 404

    themes_data['active'] = theme_id
    save_themes(themes_data)

    theme = themes_data['themes'][theme_id]
    return jsonify({
        'success': True,
        'theme': theme,
        'message': f'Theme "{theme.get("name", theme_id)}" is now active'
    })


@app.route('/api/themes/<theme_id>', methods=['DELETE'])
def api_themes_delete(theme_id):
    """Delete a saved theme."""
    if theme_id == 'teal-gold':
        return jsonify({'error': 'Cannot delete the default theme'}), 400

    themes_data = load_themes()
    if theme_id not in themes_data.get('themes', {}):
        return jsonify({'error': 'Theme not found'}), 404

    del themes_data['themes'][theme_id]

    # If we deleted the active theme, switch to default
    if themes_data.get('active') == theme_id:
        themes_data['active'] = 'teal-gold'

    save_themes(themes_data)

    return jsonify({
        'success': True,
        'message': 'Theme deleted successfully'
    })


@app.route('/api/themes/active')
def api_themes_active():
    """Get the currently active theme's full data."""
    themes_data = load_themes()
    active_id = themes_data.get('active', 'teal-gold')
    theme = themes_data.get('themes', {}).get(active_id)

    if not theme:
        # Fallback to default
        theme = DEFAULT_THEME if DEFAULT_THEME else {}
        active_id = 'teal-gold'

    return jsonify({
        'theme_id': active_id,
        'theme': theme
    })


@app.route('/api/themes/ttyd-command')
def api_themes_ttyd_command():
    """Get the ttyd service update command for the current theme."""
    if not THEME_GENERATOR_AVAILABLE:
        return jsonify({'error': 'Theme generator not available'}), 500

    themes_data = load_themes()
    active_id = themes_data.get('active', 'teal-gold')
    theme = themes_data.get('themes', {}).get(active_id)

    if not theme or 'ttyd' not in theme:
        return jsonify({'error': 'No ttyd theme data available'}), 404

    command = generate_ttyd_service_command(theme['ttyd'])
    return jsonify({
        'command': command,
        'theme_id': active_id
    })


# ============================================================================
# Terminal Session Management API (tmux-backed persistent terminals)
# ============================================================================

TERMINAL_SESSIONS_FILE = PROJECT_ROOT / 'data' / 'terminal_sessions.json'


def get_terminal_sessions():
    """Load terminal session metadata from JSON file."""
    if TERMINAL_SESSIONS_FILE.exists():
        try:
            return json.loads(TERMINAL_SESSIONS_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"windows": {}, "active_window": "0"}


def save_terminal_sessions(data):
    """Save terminal session metadata to JSON file."""
    TERMINAL_SESSIONS_FILE.write_text(json.dumps(data, indent=2))


def get_tmux_windows():
    """Get list of tmux windows from dashboard-top session."""
    try:
        result = subprocess.run(
            ['tmux', 'list-windows', '-t', 'dashboard-top', '-F', '#{window_index}'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return [w.strip() for w in result.stdout.strip().split('\n') if w.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


@app.route('/api/terminal/windows')
def api_terminal_windows():
    """List all terminal windows."""
    sessions = get_terminal_sessions()
    tmux_windows = get_tmux_windows()

    # Sync: build list from actual tmux windows, use saved names if available
    windows = []
    for wid in tmux_windows:
        name = sessions.get('windows', {}).get(wid, {}).get('name', f'Terminal {int(wid)+1}')
        windows.append({
            'id': wid,
            'name': name,
            'active': wid == sessions.get('active_window', '0')
        })

    return jsonify({'windows': windows})


@app.route('/api/terminal/windows', methods=['POST'])
def api_terminal_create():
    """Create new terminal window in BOTH paired sessions."""
    data = request.get_json() or {}
    name = data.get('name', 'New Terminal')

    # Create new tmux window in top session
    try:
        result_top = subprocess.run(
            ['tmux', 'new-window', '-t', 'dashboard-top', '-P', '-F', '#{window_index}'],
            capture_output=True, text=True, timeout=5
        )

        if result_top.returncode == 0:
            window_id = result_top.stdout.strip()

            # Create matching window in bottom session
            subprocess.run(
                ['tmux', 'new-window', '-t', 'dashboard-bottom'],
                capture_output=True, text=True, timeout=5
            )

            # Select both windows to sync them
            subprocess.run(['tmux', 'select-window', '-t', f'dashboard-top:{window_id}'],
                          capture_output=True, timeout=5)
            subprocess.run(['tmux', 'select-window', '-t', f'dashboard-bottom:{window_id}'],
                          capture_output=True, timeout=5)

            # Initialize the new window with conda env and claude
            subprocess.run(
                ['tmux', 'send-keys', '-t', f'dashboard-top:{window_id}',
                 'conda activate boom_env && claude --dangerously-skip-permissions', 'Enter'],
                capture_output=True, timeout=5
            )

            # Save metadata
            sessions = get_terminal_sessions()
            sessions.setdefault('windows', {})[window_id] = {'name': name}
            sessions['active_window'] = window_id
            save_terminal_sessions(sessions)

            return jsonify({'id': window_id, 'name': name})

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return jsonify({'error': f'tmux error: {str(e)}'}), 500

    return jsonify({'error': 'Failed to create window'}), 500


@app.route('/api/terminal/windows/<window_id>', methods=['PUT'])
def api_terminal_rename(window_id):
    """Rename terminal window."""
    data = request.get_json() or {}
    name = data.get('name', '')

    if name:
        sessions = get_terminal_sessions()
        sessions.setdefault('windows', {})[window_id] = {'name': name}
        save_terminal_sessions(sessions)
        return jsonify({'success': True})

    return jsonify({'error': 'Name required'}), 400


@app.route('/api/terminal/windows/<window_id>', methods=['DELETE'])
def api_terminal_close(window_id):
    """Close terminal window from BOTH paired sessions."""
    # Don't allow closing last window
    tmux_windows = get_tmux_windows()
    if len(tmux_windows) <= 1:
        return jsonify({'error': 'Cannot close last window'}), 400

    try:
        # Kill window in both sessions
        subprocess.run(
            ['tmux', 'kill-window', '-t', f'dashboard-top:{window_id}'],
            capture_output=True, timeout=5
        )
        subprocess.run(
            ['tmux', 'kill-window', '-t', f'dashboard-bottom:{window_id}'],
            capture_output=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Remove from metadata
    sessions = get_terminal_sessions()
    sessions.get('windows', {}).pop(window_id, None)
    save_terminal_sessions(sessions)

    return jsonify({'success': True})


@app.route('/api/terminal/windows/<window_id>/select', methods=['POST'])
def api_terminal_select(window_id):
    """Select/focus terminal window in BOTH paired sessions."""
    try:
        # Select in both sessions to keep them in sync
        subprocess.run(
            ['tmux', 'select-window', '-t', f'dashboard-top:{window_id}'],
            capture_output=True, timeout=5
        )
        subprocess.run(
            ['tmux', 'select-window', '-t', f'dashboard-bottom:{window_id}'],
            capture_output=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    sessions = get_terminal_sessions()
    sessions['active_window'] = window_id
    save_terminal_sessions(sessions)

    return jsonify({'success': True})


# ============================================
# Terminal Content Viewer API
# ============================================

# In-memory storage for display content (could be moved to file/DB if persistence needed)
_terminal_display_state = {
    'type': None,      # 'markdown', 'url', 'code', 'file'
    'content': None,   # Raw content or URL
    'path': None,      # For file type
    'language': None,  # For code type
    'timestamp': None  # When content was last updated
}

# Allowed directories for file reading (security)
TERMINAL_DISPLAY_ALLOWED_DIRS = [
    Path('/home/pds/boomshakalaka'),
    Path('/home/pds'),
    Path('/tmp'),
]


def is_path_allowed(file_path):
    """Check if file path is within allowed directories."""
    try:
        resolved = Path(file_path).resolve()
        return any(
            resolved == allowed or allowed in resolved.parents
            for allowed in TERMINAL_DISPLAY_ALLOWED_DIRS
        )
    except (ValueError, OSError):
        return False


@app.route('/api/terminal/display', methods=['GET'])
def api_terminal_display_get():
    """Get current display content for terminal side panel."""
    return jsonify(_terminal_display_state)


@app.route('/api/terminal/display', methods=['POST'])
def api_terminal_display_set():
    """Set content to display in terminal side panel.

    Request body:
        type: 'markdown' | 'url' | 'code' | 'file'
        content: string (raw content or URL)
        path: string (optional, for file reading)
        language: string (optional, for code highlighting)
    """
    global _terminal_display_state

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    content_type = data.get('type')
    if content_type not in ('markdown', 'url', 'code', 'file'):
        return jsonify({'error': 'Invalid type. Must be: markdown, url, code, or file'}), 400

    content = data.get('content', '')
    path = data.get('path')
    language = data.get('language', 'plaintext')

    # Handle file type - read the file content
    if content_type == 'file':
        if not path:
            return jsonify({'error': 'path required for file type'}), 400

        if not is_path_allowed(path):
            return jsonify({'error': 'Path not allowed'}), 403

        file_path = Path(path)
        if not file_path.exists():
            return jsonify({'error': f'File not found: {path}'}), 404

        if not file_path.is_file():
            return jsonify({'error': f'Not a file: {path}'}), 400

        try:
            ext = file_path.suffix.lower()

            # Check for binary file types first
            image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'}
            pdf_exts = {'.pdf'}

            if ext in image_exts:
                # Return image as base64 data URL
                import base64
                mime_types = {
                    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
                    '.bmp': 'image/bmp', '.ico': 'image/x-icon'
                }
                mime = mime_types.get(ext, 'application/octet-stream')
                data = base64.b64encode(file_path.read_bytes()).decode('ascii')
                content = f"data:{mime};base64,{data}"
                content_type = 'image'

            elif ext in pdf_exts:
                # Return PDF as base64 data URL
                import base64
                data = base64.b64encode(file_path.read_bytes()).decode('ascii')
                content = f"data:application/pdf;base64,{data}"
                content_type = 'pdf'

            else:
                # Text file handling
                content = file_path.read_text(encoding='utf-8', errors='replace')
                # Detect language from extension
                ext_to_lang = {
                    '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
                    '.jsx': 'jsx', '.tsx': 'tsx', '.json': 'json',
                    '.html': 'html', '.css': 'css', '.scss': 'scss',
                    '.md': 'markdown', '.yaml': 'yaml', '.yml': 'yaml',
                    '.sh': 'bash', '.bash': 'bash', '.zsh': 'zsh',
                    '.sql': 'sql', '.go': 'go', '.rs': 'rust',
                    '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.h': 'c',
                    '.rb': 'ruby', '.php': 'php', '.swift': 'swift',
                    '.kt': 'kotlin', '.r': 'r', '.lua': 'lua',
                    '.toml': 'toml', '.ini': 'ini', '.xml': 'xml',
                }
                if ext == '.md':
                    content_type = 'markdown'  # Auto-render markdown files
                else:
                    language = ext_to_lang.get(ext, 'plaintext')
                    content_type = 'code'
        except Exception as e:
            return jsonify({'error': f'Failed to read file: {str(e)}'}), 500

    # Update state
    _terminal_display_state = {
        'type': content_type,
        'content': content,
        'path': path,
        'language': language,
        'timestamp': datetime.now().isoformat()
    }

    return jsonify({'success': True, 'state': _terminal_display_state})


@app.route('/api/terminal/display', methods=['DELETE'])
def api_terminal_display_clear():
    """Clear the display content."""
    global _terminal_display_state
    _terminal_display_state = {
        'type': None,
        'content': None,
        'path': None,
        'language': None,
        'timestamp': None
    }
    return jsonify({'success': True})


# =============================================================================
# TERMINAL CHAT API (Mobile Conversational Interface)
# =============================================================================

@app.route('/api/terminal/chat/buffer')
def api_terminal_chat_buffer():
    """Capture tmux buffer, parse Claude Code output, return structured messages.

    Query params:
        session: tmux session name (default: 'dashboard-top')
        lines: number of lines to capture (default: 500)

    Returns:
        {
            messages: [{type, content, tool_name, collapsed}, ...],
            state: 'idle' | 'working' | 'done',
            error: string | null
        }
    """
    if not CLAUDE_PARSER_AVAILABLE:
        return jsonify({
            'messages': [],
            'state': 'idle',
            'error': 'Claude parser module not available'
        }), 500

    session = request.args.get('session', 'dashboard-top')
    lines = request.args.get('lines', 500, type=int)

    # Validate session name to prevent command injection
    if not re.match(r'^[a-zA-Z0-9_-]+$', session):
        return jsonify({
            'messages': [],
            'state': 'idle',
            'error': 'Invalid session name'
        }), 400

    result = get_chat_buffer(session, lines)
    return jsonify(result)


@app.route('/api/terminal/chat/send', methods=['POST'])
def api_terminal_chat_send():
    """Send user input to tmux session via send-keys.

    Request body:
        text: string - the message to send
        session: string - tmux session name (default: 'dashboard-top')

    Returns:
        {success: boolean, error: string | null}
    """
    if not CLAUDE_PARSER_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Claude parser module not available'
        }), 500

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'text is required'}), 400

    session = data.get('session', 'dashboard-top')

    # Validate session name to prevent command injection
    if not re.match(r'^[a-zA-Z0-9_-]+$', session):
        return jsonify({'success': False, 'error': 'Invalid session name'}), 400

    # Send to tmux
    success = send_to_tmux(session, text)

    if success:
        return jsonify({'success': True, 'error': None})
    else:
        return jsonify({
            'success': False,
            'error': f'Failed to send to session: {session}'
        }), 500


@app.route('/api/terminal/keys', methods=['POST'])
def api_terminal_send_keys():
    """Send special key sequences to tmux session.

    JSON body:
        key: Key to send (e.g., 'S-Tab', 'Tab', 'Escape', 'Enter')
        session: tmux session name (default: 'dashboard-top')

    Returns:
        {success: bool, error: string | null}
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    key = data.get('key', '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'key is required'}), 400

    # Whitelist allowed keys for security
    ALLOWED_KEYS = {'S-Tab', 'Tab', 'Escape', 'Enter', 'Up', 'Down'}
    if key not in ALLOWED_KEYS:
        return jsonify({'success': False, 'error': f'Key not allowed: {key}'}), 400

    # Map user-friendly key names to tmux key names
    TMUX_KEY_MAP = {
        'S-Tab': 'BTab',  # Shift+Tab = Back Tab in tmux
    }
    tmux_key = TMUX_KEY_MAP.get(key, key)

    session = data.get('session', 'dashboard-top')
    if not re.match(r'^[a-zA-Z0-9_-]+$', session):
        return jsonify({'success': False, 'error': 'Invalid session name'}), 400

    try:
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', session, tmux_key],
            capture_output=True, timeout=5
        )
        return jsonify({'success': result.returncode == 0, 'error': None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/terminal/scroll', methods=['POST'])
def api_terminal_scroll():
    """Scroll terminal via tmux copy-mode.

    This enters tmux copy-mode and scrolls. The terminal stays in copy-mode
    so the user can see the scrolled content. User can press 'q' or 'Escape'
    to exit copy-mode and return to normal terminal operation.

    If already in copy-mode, additional scroll commands just scroll further.

    JSON body:
        session: tmux session name (e.g., 'dashboard-top', 'dashboard-bottom')
        direction: 'up' or 'down'

    Returns:
        {success: bool, error: string | null}
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'JSON body required'}), 400

    session = data.get('session', '').strip()
    direction = data.get('direction', '').strip()

    if not session:
        return jsonify({'success': False, 'error': 'session is required'}), 400

    if direction not in ('up', 'down'):
        return jsonify({'success': False, 'error': 'direction must be "up" or "down"'}), 400

    # Validate session name to prevent command injection
    if not re.match(r'^[a-zA-Z0-9_-]+$', session):
        return jsonify({'success': False, 'error': 'Invalid session name'}), 400

    # tmux Page Up = PPage, Page Down = NPage
    tmux_key = 'PPage' if direction == 'up' else 'NPage'

    try:
        # Enter copy-mode directly (not via send-keys)
        subprocess.run(
            ['tmux', 'copy-mode', '-t', session],
            capture_output=True, timeout=2
        )
        time.sleep(0.05)

        # Send page up/down to scroll within copy-mode
        result = subprocess.run(
            ['tmux', 'send-keys', '-t', session, tmux_key],
            capture_output=True, timeout=2
        )

        # Don't exit copy-mode - let user see the scrolled content
        # User can press 'q' or 'Escape' to exit copy-mode manually

        return jsonify({'success': result.returncode == 0, 'error': None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/terminal/chat/state')
def api_terminal_chat_state():
    """Lightweight state check for fast polling.

    Query params:
        session: tmux session name (default: 'dashboard-top')

    Returns:
        {state: 'idle' | 'working' | 'done', error: string | null}
    """
    if not CLAUDE_PARSER_AVAILABLE:
        return jsonify({
            'state': 'idle',
            'error': 'Claude parser module not available'
        }), 500

    session = request.args.get('session', 'dashboard-top')

    # Validate session name to prevent command injection
    if not re.match(r'^[a-zA-Z0-9_-]+$', session):
        return jsonify({'state': 'idle', 'error': 'Invalid session name'}), 400

    result = get_terminal_state(session)
    return jsonify(result)


@app.route('/api/terminal/files/list')
def api_terminal_files_list():
    """List files in a directory for the file browser."""
    dir_path = request.args.get('path', '/home/pds')

    if not is_path_allowed(dir_path):
        return jsonify({'error': 'Path not allowed'}), 403

    # Resolve the path to handle symlinks and relative components
    try:
        path = Path(dir_path).resolve()
    except (OSError, ValueError):
        return jsonify({'error': 'Invalid path'}), 400

    if not path.exists():
        return jsonify({'error': 'Directory not found'}), 404
    if not path.is_dir():
        return jsonify({'error': 'Not a directory'}), 400

    items = []
    try:
        for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Handle broken symlinks and symlink loops gracefully
            try:
                item_path = str(item.resolve())
                is_dir = item.is_dir()
            except (OSError, RuntimeError):
                # Broken symlink or symlink loop - use unresolved path
                item_path = str(item)
                is_dir = False
            items.append({
                'name': item.name,
                'path': item_path,
                'is_dir': is_dir,
                'ext': item.suffix.lower() if not is_dir else None
            })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403

    # Get parent directory (using resolved path)
    parent = str(path.parent) if str(path) != '/' else None
    if parent and not is_path_allowed(parent):
        parent = None

    return jsonify({
        'path': str(path),
        'parent': parent,
        'items': items
    })


@app.route('/api/terminal/files/search')
def api_terminal_files_search():
    """Search for files by name."""
    query = request.args.get('q', '').strip()
    base_path = request.args.get('path', '/home/pds')

    if not query or len(query) < 2:
        return jsonify({'error': 'Query too short'}), 400

    if not is_path_allowed(base_path):
        return jsonify({'error': 'Path not allowed'}), 403

    results = []
    base = Path(base_path)

    if not base.exists():
        return jsonify({'error': 'Base path not found'}), 404

    try:
        # Use glob to search, limit results
        patterns = [f'**/*{query}*', f'**/*{query.lower()}*', f'**/*{query.upper()}*']
        seen = set()

        for pattern in patterns:
            for match in base.glob(pattern):
                if str(match) in seen:
                    continue
                seen.add(str(match))

                # Skip hidden files/dirs
                if any(part.startswith('.') for part in match.parts):
                    continue

                # Only include viewable files
                if match.is_file():
                    ext = match.suffix.lower()
                    viewable = ext in ['.md', '.py', '.js', '.ts', '.jsx', '.tsx', '.json',
                                       '.html', '.css', '.yaml', '.yml', '.sh', '.txt',
                                       '.sql', '.go', '.rs', '.java', '.c', '.cpp', '.h',
                                       '.rb', '.php', '.toml', '.ini', '.xml', '.env']
                    if viewable:
                        results.append({
                            'name': match.name,
                            'path': str(match),
                            'is_dir': False,
                            'ext': ext
                        })

                if len(results) >= 50:  # Limit results
                    break

            if len(results) >= 50:
                break

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'results': results, 'query': query})


@app.route('/api/terminal/files/upload', methods=['POST'])
def terminal_file_upload():
    """Upload file to specified directory."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    target_dir = request.form.get('target_dir', '/home/pds')

    if not file.filename:
        return jsonify({'error': 'No filename'}), 400

    if not is_path_allowed(target_dir):
        return jsonify({'error': 'Directory not allowed'}), 403

    target_path = Path(target_dir)
    if not target_path.exists() or not target_path.is_dir():
        return jsonify({'error': 'Invalid directory'}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'error': 'Invalid filename'}), 400

    # Handle filename collisions
    dest_path = target_path / filename
    if dest_path.exists():
        base, ext = os.path.splitext(filename)
        counter = 1
        while dest_path.exists():
            filename = f"{base}_{counter}{ext}"
            dest_path = target_path / filename
            counter += 1

    file.save(str(dest_path))

    return jsonify({
        'success': True,
        'filename': filename,
        'path': str(dest_path),
        'size': dest_path.stat().st_size
    })


# ============================================
# Automation Hub API
# ============================================

@app.route('/api/automation/jobs')
def api_automation_jobs():
    """Get all automation jobs with stats."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        init_jobs_db()
        jobs = get_all_jobs()
        stats = get_stats_summary()
        return jsonify({'jobs': jobs, 'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/jobs/<job_id>')
def api_automation_job(job_id):
    """Get a single job by ID."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        job = get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/jobs/<job_id>', methods=['PUT'])
def api_automation_update_job(job_id):
    """Update a job's configuration."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Handle config specially - convert dict to JSON string
        updates = {}
        if 'config' in data:
            import json
            updates['config_json'] = json.dumps(data['config'])
        if 'enabled' in data:
            updates['enabled'] = 1 if data['enabled'] else 0
        if 'description' in data:
            updates['description'] = data['description']

        job = update_job(job_id, updates)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/jobs/<job_id>/runs')
def api_automation_job_runs(job_id):
    """Get run history for a job."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        limit = request.args.get('limit', 20, type=int)
        runs = get_job_runs(job_id, limit=limit)
        return jsonify({'runs': runs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/jobs/<job_id>/trigger', methods=['POST'])
def api_automation_trigger(job_id):
    """Manually trigger a job."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        executor = JobExecutor()
        result = executor.run_job(job_id, trigger_type='manual', triggered_by='dashboard')

        return jsonify({
            'success': result.success,
            'exit_code': result.exit_code,
            'duration_seconds': result.duration_seconds,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'error_message': result.error_message,
            'result_data': result.result_data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/jobs/<job_id>/toggle', methods=['POST'])
def api_automation_toggle(job_id):
    """Toggle a job's enabled state."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        job = toggle_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify(job)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/runs/<run_id>')
def api_automation_run(run_id):
    """Get details of a specific run."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        run = get_run(run_id)
        if not run:
            return jsonify({'error': 'Run not found'}), 404
        return jsonify(run)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/stats')
def api_automation_stats():
    """Get automation statistics summary."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        stats = get_stats_summary()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/failures')
def api_automation_failures():
    """Get recent failures."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        hours = request.args.get('hours', 24, type=int)
        failures = get_recent_failures(hours=hours)
        return jsonify({'failures': failures})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/automation/failures', methods=['DELETE'])
def api_automation_clear_failures():
    """Clear recent failures."""
    if not AUTOMATION_AVAILABLE:
        return jsonify({'error': 'Automation not available'}), 503

    try:
        hours = request.args.get('hours', 24, type=int)
        count = clear_recent_failures(hours=hours)
        return jsonify({'success': True, 'cleared': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Kanban Board API
# =============================================================================

KANBAN_FILE = PROJECT_ROOT / 'data' / 'kanban.json'


def load_kanban_data():
    """Load kanban tasks from JSON file."""
    if KANBAN_FILE.exists():
        try:
            with open(KANBAN_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {'tasks': []}


def save_kanban_data(data):
    """Save kanban tasks to JSON file."""
    KANBAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KANBAN_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@app.route('/api/kanban/tasks')
def api_kanban_tasks():
    """Get all kanban tasks."""
    data = load_kanban_data()
    return jsonify(data)


@app.route('/api/kanban/tasks', methods=['POST'])
def api_kanban_create_task():
    """Create a new kanban task."""
    task_data = request.get_json() or {}

    task = {
        'id': str(uuid.uuid4()),
        'title': task_data.get('title', 'Untitled Task'),
        'description': task_data.get('description', ''),
        'column': task_data.get('column', 'backlog'),
        'priority': task_data.get('priority', 'medium'),
        'due_date': task_data.get('due_date'),
        'created_at': datetime.now().isoformat(),
        'order': task_data.get('order', 0)
    }

    data = load_kanban_data()
    data['tasks'].append(task)
    save_kanban_data(data)

    return jsonify(task), 201


@app.route('/api/kanban/tasks/<task_id>', methods=['PUT'])
def api_kanban_update_task(task_id):
    """Update a kanban task."""
    task_data = request.get_json() or {}
    data = load_kanban_data()

    for task in data['tasks']:
        if task['id'] == task_id:
            task['title'] = task_data.get('title', task['title'])
            task['description'] = task_data.get('description', task['description'])
            task['column'] = task_data.get('column', task['column'])
            task['priority'] = task_data.get('priority', task['priority'])
            task['due_date'] = task_data.get('due_date', task.get('due_date'))
            task['order'] = task_data.get('order', task.get('order', 0))
            save_kanban_data(data)
            return jsonify(task)

    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/kanban/tasks/<task_id>', methods=['DELETE'])
def api_kanban_delete_task(task_id):
    """Delete a kanban task."""
    data = load_kanban_data()

    original_len = len(data['tasks'])
    data['tasks'] = [t for t in data['tasks'] if t['id'] != task_id]

    if len(data['tasks']) < original_len:
        save_kanban_data(data)
        return jsonify({'success': True})

    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/kanban/tasks/reorder', methods=['POST'])
def api_kanban_reorder_tasks():
    """Reorder tasks within or between columns."""
    reorder_data = request.get_json() or {}
    task_orders = reorder_data.get('tasks', [])

    data = load_kanban_data()

    # Create a lookup for quick access
    task_lookup = {t['id']: t for t in data['tasks']}

    for order_info in task_orders:
        task_id = order_info.get('id')
        if task_id in task_lookup:
            task_lookup[task_id]['column'] = order_info.get('column', task_lookup[task_id]['column'])
            task_lookup[task_id]['order'] = order_info.get('order', 0)

    save_kanban_data(data)
    return jsonify({'success': True})


# =============================================================================
# Project Management Routes
# =============================================================================

@app.route('/projects')
def projects():
    """Main projects overview page"""
    if not PROJECTS_AVAILABLE:
        return render_template('projects.html',
                             active_page='projects',
                             error='Project management not available',
                             areas=[], stats={},
                             available_icons=[], default_colors=[],
                             **get_common_context())

    # Get areas (user-created, no auto-sync)
    areas = get_all_areas()

    # Get projects for each area
    for area in areas:
        area['projects'] = get_projects_by_area(area['id'])

    stats = get_pm_stats()
    active_tasks = get_all_active_tasks()

    return render_template('projects.html',
                         active_page='projects',
                         areas=areas,
                         stats=stats,
                         active_tasks=active_tasks,
                         available_icons=AVAILABLE_ICONS,
                         default_colors=DEFAULT_COLORS,
                         **get_common_context())


@app.route('/projects/<area_name>')
def projects_area(area_name):
    """Area detail page showing all projects"""
    if not PROJECTS_AVAILABLE:
        return redirect(url_for('projects'))

    area = get_area_by_name(area_name)
    if not area:
        return redirect(url_for('projects'))

    # Get projects with task counts
    projects_list = get_projects_by_area(area['id'])
    for project in projects_list:
        tasks = get_tasks_by_project(project['id'])
        project['task_count'] = len(tasks)
        project['done_count'] = len([t for t in tasks if t['status'] == 'done'])
        project['in_progress_count'] = len([t for t in tasks if t['status'] == 'in_progress'])

    # Calculate area stats
    all_tasks = []
    for project in projects_list:
        tasks = get_tasks_by_project(project['id'])
        for t in tasks:
            t['project_name'] = project['name']
        all_tasks.extend(tasks)

    area_stats = {
        'open_tasks': len([t for t in all_tasks if t['status'] != 'done']),
        'in_progress': len([t for t in all_tasks if t['status'] == 'in_progress']),
        'done_tasks': len([t for t in all_tasks if t['status'] == 'done'])
    }

    # Recent tasks (sorted by created_at, non-done first)
    recent_tasks = sorted(all_tasks, key=lambda t: (t['status'] == 'done', t.get('created_at', '')), reverse=True)[:10]

    # Get active tasks grouped by priority
    active_tasks = get_active_tasks_by_area(area['id'])

    return render_template('area_detail.html',
                         active_page='projects',
                         area=area,
                         projects=projects_list,
                         stats=area_stats,
                         recent_tasks=recent_tasks,
                         active_tasks=active_tasks,
                         available_icons=AVAILABLE_ICONS,
                         default_colors=DEFAULT_COLORS,
                         **get_common_context())


@app.route('/projects/<area_name>/<project_name>')
def project_detail(area_name, project_name):
    """Project detail page with kanban board"""
    if not PROJECTS_AVAILABLE:
        return redirect(url_for('projects'))

    project = get_project_by_name(project_name, area_name)
    if not project:
        return redirect(url_for('projects'))

    tasks = get_tasks_by_project(project['id'])

    # Group tasks by status for kanban
    task_columns = {
        'backlog': [t for t in tasks if t['status'] == 'backlog'],
        'todo': [t for t in tasks if t['status'] == 'todo'],
        'in_progress': [t for t in tasks if t['status'] == 'in_progress'],
        'done': [t for t in tasks if t['status'] == 'done']
    }

    return render_template('project_detail.html',
                         active_page='projects',
                         project=project,
                         task_columns=task_columns,
                         **get_common_context())


@app.route('/lists')
def lists():
    """Personal lists page"""
    if not PROJECTS_AVAILABLE:
        return render_template('lists.html',
                             active_page='lists',
                             error='Lists not available',
                             lists=[],
                             **get_common_context())

    all_lists = get_all_lists()
    # Get items for each list
    lists_with_items = []
    for lst in all_lists:
        full_list = get_list(lst['id'])
        if full_list:
            lists_with_items.append(full_list)

    return render_template('lists.html',
                         active_page='lists',
                         lists=lists_with_items,
                         **get_common_context())


# =============================================================================
# Project Management API
# =============================================================================

@app.route('/api/pm/areas')
def api_pm_areas():
    """Get all areas with stats"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503
    return jsonify(get_all_areas())


@app.route('/api/pm/areas', methods=['POST'])
def api_pm_create_area():
    """Create a new area"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'error': 'name is required'}), 400

    area = create_area(
        name=data['name'],
        icon=data.get('icon', 'folder'),
        color=data.get('color', '#6b7280'),
        path=data.get('path')
    )
    return jsonify(area), 201


@app.route('/api/pm/areas/<area_id>', methods=['GET'])
def api_pm_get_area(area_id):
    """Get a single area"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    area = get_area(area_id)
    if not area:
        return jsonify({'error': 'Area not found'}), 404
    return jsonify(area)


@app.route('/api/pm/areas/<area_id>', methods=['PUT'])
def api_pm_update_area(area_id):
    """Update an area"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    area = update_area(area_id, **data)
    if not area:
        return jsonify({'error': 'Area not found'}), 404
    return jsonify(area)


@app.route('/api/pm/areas/<area_id>', methods=['DELETE'])
def api_pm_delete_area(area_id):
    """Delete an area"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    if delete_area(area_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Area not found'}), 404


@app.route('/api/pm/areas/reorder', methods=['POST'])
def api_pm_reorder_areas():
    """Reorder areas"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    area_orders = data.get('areas', [])

    if reorder_areas(area_orders):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to reorder'}), 500


@app.route('/api/pm/tasks/active')
def api_pm_active_tasks():
    """Get all active (in-progress or high-priority) tasks"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    return jsonify(get_all_active_tasks())


@app.route('/api/pm/import', methods=['POST'])
def api_pm_import():
    """Import areas and projects from filesystem (optional convenience feature)"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    directory_names = data.get('directories')

    # Import areas from directories
    areas = import_areas_from_directory(directory_names)

    # Optionally import projects for areas with paths
    if data.get('include_projects', True):
        for area in areas:
            if area.get('path'):
                import_projects_from_directory(area['id'])

    return jsonify({'success': True, 'imported_areas': len(areas)})


@app.route('/api/pm/areas/<area_id>/import-projects', methods=['POST'])
def api_pm_import_area_projects(area_id):
    """Import projects from an area's linked directory"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    area = get_area(area_id)
    if not area:
        return jsonify({'error': 'Area not found'}), 404

    if not area.get('path'):
        return jsonify({'error': 'Area has no linked directory'}), 400

    projects = import_projects_from_directory(area_id)
    return jsonify({'success': True, 'imported_projects': len(projects)})


@app.route('/api/pm/projects')
def api_pm_projects():
    """Get all projects"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    area_id = request.args.get('area_id')
    if area_id:
        return jsonify(get_projects_by_area(area_id))
    return jsonify(get_all_projects())


@app.route('/api/pm/projects', methods=['POST'])
def api_pm_create_project():
    """Create a new project"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    if not data.get('name') or not data.get('area_id'):
        return jsonify({'error': 'name and area_id required'}), 400

    project = create_project(
        area_id=data['area_id'],
        name=data['name'],
        description=data.get('description', ''),
        path=data.get('path')
    )
    return jsonify(project), 201


@app.route('/api/pm/projects/<project_id>', methods=['PUT'])
def api_pm_update_project(project_id):
    """Update a project"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    project = update_project(project_id, **data)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    return jsonify(project)


@app.route('/api/pm/projects/<project_id>', methods=['DELETE'])
def api_pm_delete_project(project_id):
    """Delete a project"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    if delete_project(project_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Project not found'}), 404


@app.route('/api/pm/tasks')
def api_pm_tasks():
    """Get all tasks, optionally filtered"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    project_id = request.args.get('project_id')
    status = request.args.get('status')
    priority = request.args.get('priority')

    if project_id:
        return jsonify(get_tasks_by_project(project_id))
    return jsonify(get_all_tasks(status=status, priority=priority))


@app.route('/api/pm/tasks', methods=['POST'])
def api_pm_create_task():
    """Create a new task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    if not data.get('title') or not data.get('project_id'):
        return jsonify({'error': 'title and project_id required'}), 400

    task = create_task(
        project_id=data['project_id'],
        title=data['title'],
        notes=data.get('notes', ''),
        status=data.get('status', 'backlog'),
        priority=data.get('priority', 'medium')
    )
    return jsonify(task), 201


@app.route('/api/pm/tasks/<task_id>')
def api_pm_get_task(task_id):
    """Get a single task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/api/pm/tasks/<task_id>', methods=['PUT'])
def api_pm_update_task(task_id):
    """Update a task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    task = update_task(task_id, **data)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/api/pm/tasks/<task_id>', methods=['DELETE'])
def api_pm_delete_task(task_id):
    """Delete a task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    if delete_task(task_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/pm/tasks/reorder', methods=['POST'])
def api_pm_reorder_tasks():
    """Reorder tasks"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    task_orders = data.get('tasks', [])

    if reorder_tasks(task_orders):
        return jsonify({'success': True})
    return jsonify({'error': 'Failed to reorder'}), 500


# =============================================================================
# Task Attachment APIs
# =============================================================================

@app.route('/api/pm/tasks/<task_id>/attachments', methods=['GET'])
def api_pm_task_attachments(task_id):
    """List all attachments for a task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify(get_task_attachments(task_id))


@app.route('/api/pm/tasks/<task_id>/attachments', methods=['POST'])
def api_pm_upload_attachment(task_id):
    """Upload an attachment to a task"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    task = get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Get the project to check for path
    project = get_project_for_task(task_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    if not project.get('path'):
        return jsonify({
            'error': 'Project has no linked directory. Please configure a directory path in project settings.'
        }), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Create attachments directory
    project_path = Path(project['path'])
    attachments_dir = project_path / 'attachments' / task_id
    attachments_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    original_name = secure_filename(file.filename)
    unique_id = str(uuid.uuid4())[:8]
    stored_filename = f"{unique_id}_{original_name}"
    file_path = attachments_dir / stored_filename

    # Save file
    file.save(str(file_path))

    # Get file info
    file_size = file_path.stat().st_size
    mime_type = file.content_type or 'application/octet-stream'

    # Create database record
    attachment = create_task_attachment(
        task_id=task_id,
        filename=stored_filename,
        original_name=original_name,
        file_path=str(file_path),
        file_size=file_size,
        mime_type=mime_type
    )

    return jsonify(attachment), 201


@app.route('/api/pm/attachments/<attachment_id>')
def api_pm_serve_attachment(attachment_id):
    """Serve an attachment file for download"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    attachment = get_task_attachment(attachment_id)
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    file_path = Path(attachment['file_path'])
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404

    return send_file(
        str(file_path),
        download_name=attachment['original_name'],
        as_attachment=True
    )


@app.route('/api/pm/tasks/<task_id>/attachments/<attachment_id>', methods=['DELETE'])
def api_pm_delete_attachment(task_id, attachment_id):
    """Delete an attachment"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    attachment = delete_task_attachment(attachment_id)
    if not attachment:
        return jsonify({'error': 'Attachment not found'}), 404

    # Delete file from disk
    file_path = Path(attachment['file_path'])
    if file_path.exists():
        file_path.unlink()

    # Try to remove empty directories
    try:
        parent_dir = file_path.parent
        if parent_dir.exists() and not any(parent_dir.iterdir()):
            parent_dir.rmdir()
    except Exception:
        pass  # Ignore cleanup errors

    return jsonify({'success': True})


@app.route('/api/pm/browse-directories')
def api_pm_browse_directories():
    """Browse directories for linking to projects/areas"""
    import os
    from pathlib import Path

    path = request.args.get('path', '/home/pds')

    # Security: Only allow browsing within /home/pds
    try:
        requested = Path(path).resolve()
        allowed_base = Path('/home/pds').resolve()
        if not str(requested).startswith(str(allowed_base)):
            return jsonify({'error': 'Access denied'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 400

    if not requested.exists():
        return jsonify({'error': 'Path does not exist'}), 404

    if not requested.is_dir():
        return jsonify({'error': 'Not a directory'}), 400

    # Get directory contents
    entries = []
    try:
        for entry in sorted(requested.iterdir()):
            # Skip hidden files and common non-project directories
            if entry.name.startswith('.'):
                continue
            if entry.name in ('node_modules', '__pycache__', '.venv', 'venv', '.git'):
                continue

            if entry.is_dir():
                entries.append({
                    'name': entry.name,
                    'path': str(entry),
                    'type': 'directory'
                })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403

    # Get parent path for navigation
    parent = str(requested.parent) if requested != allowed_base else None

    return jsonify({
        'current': str(requested),
        'parent': parent,
        'entries': entries
    })


@app.route('/api/pm/create-directory', methods=['POST'])
def api_pm_create_directory():
    """Create a new directory"""
    from pathlib import Path
    import re

    data = request.get_json() or {}
    parent_path = data.get('parent', '/home/pds')
    folder_name = data.get('name', '').strip()

    if not folder_name:
        return jsonify({'error': 'Folder name is required'}), 400

    # Validate folder name (no path separators, no special chars)
    if not re.match(r'^[\w\-. ]+$', folder_name):
        return jsonify({'error': 'Invalid folder name. Use only letters, numbers, dashes, underscores, dots, and spaces.'}), 400

    # Security: Only allow creating within /home/pds
    try:
        parent = Path(parent_path).resolve()
        allowed_base = Path('/home/pds').resolve()
        if not str(parent).startswith(str(allowed_base)):
            return jsonify({'error': 'Access denied'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 400

    if not parent.exists():
        return jsonify({'error': 'Parent directory does not exist'}), 404

    new_dir = parent / folder_name

    if new_dir.exists():
        return jsonify({'error': 'A folder with this name already exists'}), 400

    try:
        new_dir.mkdir(parents=False)
        return jsonify({
            'success': True,
            'path': str(new_dir),
            'name': folder_name
        })
    except PermissionError:
        return jsonify({'error': 'Permission denied'}), 403
    except Exception as e:
        return jsonify({'error': f'Failed to create folder: {str(e)}'}), 500


@app.route('/api/pm/lists')
def api_pm_lists():
    """Get all lists"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503
    return jsonify(get_all_lists())


@app.route('/api/pm/lists', methods=['POST'])
def api_pm_create_list():
    """Create a new list"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'error': 'name required'}), 400

    lst = create_list(
        name=data['name'],
        icon=data.get('icon', 'list')
    )
    return jsonify(lst), 201


@app.route('/api/pm/lists/<list_id>')
def api_pm_get_list(list_id):
    """Get a list with its items"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    lst = get_list(list_id)
    if not lst:
        return jsonify({'error': 'List not found'}), 404
    return jsonify(lst)


@app.route('/api/pm/lists/<list_id>', methods=['PUT'])
def api_pm_update_list(list_id):
    """Update a list"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    lst = update_list(list_id, **data)
    if not lst:
        return jsonify({'error': 'List not found'}), 404
    return jsonify(lst)


@app.route('/api/pm/lists/<list_id>', methods=['DELETE'])
def api_pm_delete_list(list_id):
    """Delete a list"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    if delete_list(list_id):
        return jsonify({'success': True})
    return jsonify({'error': 'List not found'}), 404


@app.route('/api/pm/lists/<list_id>/items', methods=['POST'])
def api_pm_add_list_item(list_id):
    """Add an item to a list"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    if not data.get('content'):
        return jsonify({'error': 'content required'}), 400

    item = add_list_item(list_id, data['content'])
    return jsonify(item), 201


@app.route('/api/pm/lists/<list_id>/items/<item_id>', methods=['PUT'])
def api_pm_update_list_item(list_id, item_id):
    """Update a list item"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    data = request.get_json() or {}
    item = update_list_item(item_id, **data)
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    return jsonify(item)


@app.route('/api/pm/lists/<list_id>/items/<item_id>', methods=['DELETE'])
def api_pm_delete_list_item(list_id, item_id):
    """Delete a list item"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503

    if delete_list_item(item_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Item not found'}), 404


@app.route('/api/pm/stats')
def api_pm_stats():
    """Get project management statistics"""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Project management not available'}), 503
    return jsonify(get_pm_stats())


# =============================================================================
# Dev Port Manager API
# =============================================================================

@app.route('/api/dev-port')
def api_dev_port():
    """Get next available dev server port."""
    import socket
    PORT_RANGE = (4000, 4019)

    for port in range(PORT_RANGE[0], PORT_RANGE[1] + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return jsonify({'port': port, 'range': list(PORT_RANGE)})

    return jsonify({'error': 'No available ports'}), 503


@app.route('/api/dev-port/list')
def api_dev_port_list():
    """List all dev ports and their status."""
    import socket
    PORT_RANGE = (4000, 4019)

    ports = []
    for port in range(PORT_RANGE[0], PORT_RANGE[1] + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            in_use = s.connect_ex(('localhost', port)) == 0
            ports.append({'port': port, 'in_use': in_use})

    return jsonify({'ports': ports, 'range': list(PORT_RANGE)})


def get_pm2_pids() -> set[int]:
    """Get set of PIDs managed by PM2."""
    try:
        result = subprocess.run(['pm2', 'jlist'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pm2_list = json.loads(result.stdout)
            return {proc['pid'] for proc in pm2_list if proc.get('pid')}
    except Exception:
        pass
    return set()


def is_dev_port(port: int) -> tuple[bool, str | None]:
    """Check if port is in any monitored dev range."""
    if port in EXCLUDED_PORTS:
        return False, None
    for start, end, category in DEV_PORT_RANGES:
        if start <= port <= end:
            return True, category
    return False, None


@app.route('/api/dev-port/active')
def api_dev_port_active():
    """List active dev servers with process info across all monitored port ranges."""
    active = []
    pm2_pids = get_pm2_pids()

    # Use ss to get all listening ports with PIDs (works for IPv4 and IPv6)
    try:
        result = subprocess.run(
            ['ss', '-tlnp'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return jsonify({
                'active': [],
                'ranges': [{'start': s, 'end': e, 'category': c} for s, e, c in DEV_PORT_RANGES],
                'error': 'ss command failed'
            })

        # Parse ss output to find ports in our ranges
        # Format: LISTEN 0 511 127.0.0.1:4010 0.0.0.0:* users:(("node",pid=1474380,fd=22))
        # Or:     LISTEN 0 511 *:4000 *:* users:(("next-server",pid=3139079,fd=22))
        for line in result.stdout.split('\n'):
            if 'LISTEN' not in line:
                continue

            # Extract port from local address (4th column)
            parts = line.split()
            if len(parts) < 5:
                continue

            local_addr = parts[3]
            # Handle formats: 127.0.0.1:4010, *:4000, [::]:4000, 0.0.0.0:4000
            if ':' in local_addr:
                port_str = local_addr.rsplit(':', 1)[-1]
                try:
                    port = int(port_str)
                except ValueError:
                    continue

                # Check if port is in any monitored range
                is_monitored, category = is_dev_port(port)
                if not is_monitored:
                    continue

                # Extract PID from users:(("name",pid=XXXX,fd=YY))
                pid_match = re.search(r'pid=(\d+)', line)
                pid = pid_match.group(1) if pid_match else ''

                if pid:
                    pid_int = int(pid)
                    is_managed = pid_int in pm2_pids

                    # Get working directory
                    cwd = ''
                    try:
                        cwd_result = subprocess.run(
                            ['readlink', '-f', f'/proc/{pid}/cwd'],
                            capture_output=True, text=True, timeout=2
                        )
                        if cwd_result.returncode == 0:
                            cwd = cwd_result.stdout.strip()
                    except Exception:
                        pass

                    # Get command
                    cmd = ''
                    try:
                        cmd_result = subprocess.run(
                            ['ps', '-p', pid, '-o', 'args='],
                            capture_output=True, text=True, timeout=2
                        )
                        if cmd_result.returncode == 0:
                            cmd = cmd_result.stdout.strip()
                    except Exception:
                        pass

                    # Extract project name from cwd or command
                    project = cwd.split('/')[-1] if cwd else f'Port {port}'
                    # Try to get a better name from pm2 or command
                    if is_managed:
                        # Try to find pm2 name
                        try:
                            pm2_result = subprocess.run(['pm2', 'jlist'], capture_output=True, text=True, timeout=5)
                            if pm2_result.returncode == 0:
                                pm2_list = json.loads(pm2_result.stdout)
                                for proc in pm2_list:
                                    if proc.get('pid') == pid_int:
                                        project = proc.get('name', project)
                                        break
                        except Exception:
                            pass

                    # Avoid duplicates (IPv4 and IPv6 might both show)
                    if not any(s['port'] == port for s in active):
                        active.append({
                            'port': port,
                            'project': project,
                            'cwd': cwd,
                            'command': cmd[:100],  # Truncate long commands
                            'pid': pid,
                            'category': category,
                            'managed': is_managed
                        })

    except Exception as e:
        return jsonify({
            'active': [],
            'ranges': [{'start': s, 'end': e, 'category': c} for s, e, c in DEV_PORT_RANGES],
            'error': str(e)
        })

    # Sort by port number
    active.sort(key=lambda x: x['port'])

    return jsonify({
        'active': active,
        'ranges': [{'start': s, 'end': e, 'category': c} for s, e, c in DEV_PORT_RANGES]
    })


# ============================================
# SMS / Twilio Routes
# ============================================

def send_to_openclaw(message: str, phone_number: str, channel: str = 'sms', contact_name: str = None) -> str:
    """Send a message to OpenClaw via CLI and get a response with session persistence.

    Uses the OpenClaw CLI on the MacBook (Reggie's brain) via SSH. This maintains
    conversation context across all channels through OpenClaw's native session system.

    Args:
        message: The user's message
        phone_number: The sender's phone number (used for session key)
        channel: The channel name (sms, whatsapp, etc.)
        contact_name: Optional contact name to include in context
    """
    import subprocess
    import json
    import shlex

    try:
        # Normalize phone number for session key
        normalized_phone = normalize_phone_number(phone_number)

        # Build the message with channel context
        # Include channel and contact info so Reggie knows who's messaging
        context_prefix = f"[{channel.upper()}]"
        if contact_name:
            context_prefix += f" [From: {contact_name}]"

        # Format: [SMS] [From: Paul] Hey Reggie
        full_message = f"{context_prefix} {message}"

        # Escape the message for shell
        escaped_message = shlex.quote(full_message)

        # Build the OpenClaw CLI command
        # Uses --to to maintain session persistence based on phone number
        # The session is shared with iMessage/WebChat via agent:main:main
        cmd = f'''ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node >/dev/null 2>&1 && openclaw agent --to {normalized_phone} --message {escaped_message} --json --timeout 60"'''

        logger.info(f"Calling OpenClaw for {channel} from {normalized_phone}")

        # Execute the command
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=90  # Allow time for AI response
        )

        if result.returncode != 0:
            logger.error(f"OpenClaw CLI error: {result.stderr}")
            return "I'm having trouble connecting to my brain. Try again in a bit!"

        # Parse the JSON response
        # Find the JSON object in the output (skip nvm messages)
        output = result.stdout.strip()
        json_start = output.find('{')
        if json_start == -1:
            logger.error(f"No JSON in OpenClaw response: {output[:200]}")
            return "I'm having trouble thinking right now. Try again later!"

        json_str = output[json_start:]
        data = json.loads(json_str)

        # Extract the response text
        if data.get('status') == 'ok' and 'result' in data:
            payloads = data['result'].get('payloads', [])
            if payloads and payloads[0].get('text'):
                response_text = payloads[0]['text']
                logger.info(f"OpenClaw response for {channel}: {response_text[:50]}...")
                return response_text

        # Handle error status
        if data.get('status') == 'error':
            logger.error(f"OpenClaw returned error: {data.get('error', 'unknown')}")
            return "Something went wrong on my end. Try again later!"

        logger.error(f"Unexpected OpenClaw response format: {json_str[:200]}")
        return "I'm having trouble thinking right now. Try again later!"

    except subprocess.TimeoutExpired:
        logger.error("OpenClaw request timed out")
        return "I'm thinking too hard! Give me a moment and try again."
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenClaw response: {e}")
        return "I'm having trouble thinking right now. Try again later!"
    except Exception as e:
        logger.error(f"Error calling OpenClaw: {e}")
        return "Something went wrong on my end. Try again later!"


@app.route('/sms/webhook', methods=['POST'])
def sms_webhook():
    """Receive inbound SMS from Twilio.

    Routes messages through OpenClaw for unified context across all channels.
    """
    if not TWILIO_AVAILABLE:
        return 'SMS not available', 503

    # Get message details from Twilio
    from_number = request.form.get('From', '')
    to_number = request.form.get('To', '')
    body = request.form.get('Body', '').strip()
    message_sid = request.form.get('MessageSid', '')

    logger.info(f"SMS received from {from_number}: {body[:50]}...")

    # Log the inbound message
    log_sms_message(from_number, 'inbound', body, message_sid)

    # Check if sender is on allowlist
    allowlist_entry = get_sms_allowlist_entry(from_number)
    if not allowlist_entry:
        logger.info(f"Ignoring SMS from non-allowlisted number: {from_number}")
        # Return empty TwiML response (no reply)
        resp = MessagingResponse()
        return str(resp), 200, {'Content-Type': 'text/xml'}

    # Get contact name for context
    contact_name = allowlist_entry.get('name') if allowlist_entry else None

    # Get AI response from OpenClaw (with session persistence)
    ai_response = send_to_openclaw(
        message=body,
        phone_number=from_number,
        channel='sms',
        contact_name=contact_name
    )

    # Log the outbound response
    log_sms_message(from_number, 'outbound', ai_response)

    # Send response via TwiML
    resp = MessagingResponse()
    resp.message(ai_response)

    return str(resp), 200, {'Content-Type': 'text/xml'}


@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """Receive inbound WhatsApp messages from Twilio.

    Uses same allowlist as SMS. Routes through OpenClaw for unified context.
    """
    if not TWILIO_AVAILABLE:
        return 'WhatsApp not available', 503

    # Get message details from Twilio
    # WhatsApp numbers come as "whatsapp:+15551234567"
    from_number_raw = request.form.get('From', '')
    from_number = from_number_raw.replace('whatsapp:', '')
    to_number = request.form.get('To', '').replace('whatsapp:', '')
    body = request.form.get('Body', '').strip()
    message_sid = request.form.get('MessageSid', '')

    logger.info(f"WhatsApp received from {from_number}: {body[:50]}...")

    # Log the inbound message (reuse SMS logging)
    log_sms_message(from_number, 'inbound', body, message_sid)

    # Check if sender is on allowlist (shared with SMS)
    allowlist_entry = get_sms_allowlist_entry(from_number)
    if not allowlist_entry:
        logger.info(f"Ignoring WhatsApp from non-allowlisted number: {from_number}")
        resp = MessagingResponse()
        return str(resp), 200, {'Content-Type': 'text/xml'}

    # Get contact name for context
    contact_name = allowlist_entry.get('name') if allowlist_entry else None

    # Get AI response from OpenClaw (with session persistence)
    ai_response = send_to_openclaw(
        message=body,
        phone_number=from_number,
        channel='whatsapp',
        contact_name=contact_name
    )

    # Log the outbound response
    log_sms_message(from_number, 'outbound', ai_response)

    # Send response via TwiML
    resp = MessagingResponse()
    resp.message(ai_response)

    return str(resp), 200, {'Content-Type': 'text/xml'}


@app.route('/api/sms/send', methods=['POST'])
def api_sms_send():
    """Send an outbound SMS (adds recipient to allowlist)."""
    if not twilio_client:
        return jsonify({'error': 'Twilio not configured'}), 503

    data = request.get_json() or {}
    to_number = data.get('to', '')
    message = data.get('message', '')
    name = data.get('name')  # Optional contact name

    if not to_number or not message:
        return jsonify({'error': 'Missing required fields: to, message'}), 400

    try:
        # Normalize the phone number
        normalized = normalize_phone_number(to_number)

        # Send the SMS
        sent_message = twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=normalized
        )

        # Add to allowlist (auto-allow anyone Reggie texts first)
        add_to_sms_allowlist(normalized, added_by='outbound', name=name)

        # Log the outbound message
        log_sms_message(normalized, 'outbound', message, sent_message.sid)

        logger.info(f"SMS sent to {normalized}: {message[:50]}...")

        return jsonify({
            'success': True,
            'sid': sent_message.sid,
            'to': normalized,
            'message': message,
            'status': sent_message.status
        })

    except Exception as e:
        logger.error(f"Failed to send SMS: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/sms/allowlist', methods=['GET'])
def api_sms_allowlist_get():
    """Get the SMS allowlist."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    allowlist = get_sms_allowlist()
    return jsonify({'allowlist': allowlist})


@app.route('/api/sms/allowlist', methods=['POST'])
def api_sms_allowlist_add():
    """Add a phone number to the allowlist."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    data = request.get_json() or {}
    phone_number = data.get('phone_number', '')
    name = data.get('name')

    if not phone_number:
        return jsonify({'error': 'Missing required field: phone_number'}), 400

    entry = add_to_sms_allowlist(phone_number, added_by='manual', name=name)
    return jsonify({'success': True, 'entry': entry})


@app.route('/api/sms/allowlist/<path:phone_number>', methods=['DELETE'])
def api_sms_allowlist_remove(phone_number):
    """Remove a phone number from the allowlist."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    # URL decode the phone number (+ becomes %2B)
    from urllib.parse import unquote
    phone_number = unquote(phone_number)

    removed = remove_from_sms_allowlist(phone_number)
    if removed:
        return jsonify({'success': True, 'removed': phone_number})
    else:
        return jsonify({'error': 'Phone number not found'}), 404


@app.route('/api/sms/allowlist/<path:phone_number>', methods=['PUT'])
def api_sms_allowlist_update(phone_number):
    """Update a phone number's name on the allowlist."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    from urllib.parse import unquote
    phone_number = unquote(phone_number)

    data = request.get_json() or {}
    name = data.get('name', '')

    entry = update_sms_allowlist_name(phone_number, name)
    if entry:
        return jsonify({'success': True, 'entry': entry})
    else:
        return jsonify({'error': 'Phone number not found'}), 404


@app.route('/api/sms/conversations', methods=['GET'])
def api_sms_conversations():
    """Get recent SMS conversations."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    limit = request.args.get('limit', 100, type=int)
    messages = get_recent_sms_messages(limit)
    return jsonify({'messages': messages})


@app.route('/api/sms/conversation/<path:phone_number>', methods=['GET'])
def api_sms_conversation(phone_number):
    """Get conversation history with a specific phone number."""
    if not PROJECTS_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    from urllib.parse import unquote
    phone_number = unquote(phone_number)

    limit = request.args.get('limit', 50, type=int)
    messages = get_sms_conversation(phone_number, limit)
    allowlist_entry = get_sms_allowlist_entry(phone_number)

    return jsonify({
        'phone_number': normalize_phone_number(phone_number),
        'contact': allowlist_entry,
        'messages': messages
    })


@app.route('/api/sms/status', methods=['GET'])
def api_sms_status():
    """Get SMS system status."""
    return jsonify({
        'twilio_available': TWILIO_AVAILABLE,
        'twilio_configured': twilio_client is not None,
        'phone_number': TWILIO_PHONE_NUMBER if twilio_client else None,
        'openclaw_url': OPENCLAW_GATEWAY_URL
    })


# ============================================
# Mobile Routes
# ============================================

@app.route('/m')
@app.route('/m/')
def mobile_home():
    """Mobile home page"""
    return render_template('mobile/home.html', active_page='home', **get_common_context())

@app.route('/m/workshop')
def mobile_workshop():
    """Mobile workshop hub"""
    return render_template('mobile/workshop/index.html', active_page='workshop', active_category='workshop', **get_common_context())

@app.route('/m/workshop/kanban')
def mobile_workshop_kanban():
    """Mobile kanban board"""
    return render_template('mobile/workshop/kanban.html', active_page='kanban', active_category='workshop', **get_common_context())

@app.route('/m/workshop/agents')
def mobile_workshop_agents():
    """Mobile agent office"""
    return render_template('mobile/workshop/agents.html', active_page='agents', active_category='workshop', **get_common_context())

@app.route('/m/workshop/vibecraft')
def mobile_workshop_vibecraft():
    """Mobile vibecraft studio"""
    return render_template('mobile/workshop/vibecraft.html', active_page='vibecraft', active_category='workshop', **get_common_context())

@app.route('/m/automation')
def mobile_automation():
    """Mobile automation hub"""
    return render_template('mobile/automation/index.html', active_page='automation', **get_common_context())

@app.route('/m/reggie')
def mobile_reggie():
    """Mobile reggie overview"""
    return render_template('mobile/reggie/index.html', active_page='reggie', active_category='reggie', **get_common_context())

@app.route('/m/reggie/control')
def mobile_reggie_control():
    """Mobile reggie control panel"""
    return render_template('mobile/reggie/control.html', active_page='control', active_category='reggie', **get_common_context())

@app.route('/m/reggie/camera')
def mobile_reggie_camera():
    """Mobile reggie camera feed"""
    return render_template('mobile/reggie/camera.html', active_page='camera', active_category='reggie', **get_common_context())

@app.route('/m/reggie/moves')
def mobile_reggie_moves():
    """Mobile reggie moves and emotions"""
    return render_template('mobile/reggie/moves.html', active_page='moves', active_category='reggie', **get_common_context())

@app.route('/m/reggie/apps')
def mobile_reggie_apps():
    """Mobile reggie huggingface apps"""
    return render_template('mobile/reggie/apps.html', active_page='apps', active_category='reggie', **get_common_context())

@app.route('/m/reggie/settings')
def mobile_reggie_settings():
    """Mobile reggie settings"""
    return render_template('mobile/reggie/settings.html', active_page='settings', active_category='reggie', **get_common_context())


def main():
    """Run the dashboard server"""
    print("Starting Boomshakalaka Management Dashboard...")
    print("Visit http://localhost:3003")
    app.run(host='0.0.0.0', port=3003, debug=False)


if __name__ == '__main__':
    main()
