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
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, redirect, url_for, request, send_file, Response, stream_with_context

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

# Configuration
PROJECT_ROOT = Path('/home/pds/boomshakalaka')
# Keep pointing to old location for logs during migration
LEGACY_POLYMARKET_DIR = Path('/home/pds/money_printing/polymarket')
POLYMARKET_DIR = LEGACY_POLYMARKET_DIR  # Alias for backwards compatibility

# AI Studio Configuration (100% local - no external calls)
COMFY_HOST = '127.0.0.1'  # Localhost only - never exposed
COMFY_PORT = 8188
COMFY_DIR = Path('/home/pds/image_gen/ComfyUI')
MODELS_DIR = PROJECT_ROOT / 'models'  # Symlink to ComfyUI models
GENERATIONS_DIR = PROJECT_ROOT / 'data' / 'generations'
DATABASES_DIR = PROJECT_ROOT / 'data' / 'databases'
THEMES_FILE = PROJECT_ROOT / 'data' / 'themes.json'

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
            f'https://api.the-odds-api.com/v4/sports/',
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
    return {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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


import re

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


@app.route('/terminal')
def terminal():
    """Web terminal page - embeds ttyd for browser-based terminal access"""
    return render_template('terminal.html',
                         active_page='terminal',
                         **get_common_context())


# Keep old routes for backwards compatibility
@app.route('/overview')
def overview():
    """Redirect to home"""
    return redirect(url_for('home'))


@app.route('/jobs')
def jobs():
    """Redirect to home (jobs are shown there now)"""
    return redirect(url_for('home'))


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

    logger.info(f"Building LTX video workflow (native nodes):")
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
    """Get list of tmux windows in dashboard session."""
    try:
        result = subprocess.run(
            ['tmux', 'list-windows', '-t', 'dashboard', '-F', '#{window_index}'],
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
    """Create new terminal window."""
    data = request.get_json() or {}
    name = data.get('name', 'New Terminal')

    # Create new tmux window
    try:
        result = subprocess.run(
            ['tmux', 'new-window', '-t', 'dashboard', '-P', '-F', '#{window_index}'],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            window_id = result.stdout.strip()

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
    """Close terminal window."""
    # Don't allow closing last window
    tmux_windows = get_tmux_windows()
    if len(tmux_windows) <= 1:
        return jsonify({'error': 'Cannot close last window'}), 400

    try:
        subprocess.run(
            ['tmux', 'kill-window', '-t', f'dashboard:{window_id}'],
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
    """Select/focus terminal window."""
    try:
        subprocess.run(
            ['tmux', 'select-window', '-t', f'dashboard:{window_id}'],
            capture_output=True, timeout=5
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    sessions = get_terminal_sessions()
    sessions['active_window'] = window_id
    save_terminal_sessions(sessions)

    return jsonify({'success': True})


def main():
    """Run the dashboard server"""
    print("Starting Boomshakalaka Management Dashboard...")
    print("Visit http://localhost:3003")
    app.run(host='0.0.0.0', port=3003, debug=False)


if __name__ == '__main__':
    main()
