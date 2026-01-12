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
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, redirect, url_for, request, send_file

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
            # img2img mode
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
        else:
            # txt2img mode
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
            )

        # Send to ComfyUI
        result = send_to_comfyui(workflow, gen_id)

        if result.get('error'):
            return jsonify({'error': result['error']}), 500

        # NOTE: We do NOT auto-save to database. User must explicitly click "Save to Gallery".
        # This keeps generation history opt-in only, per user privacy preference.

        return jsonify({
            'id': gen_id,
            'image_url': f'/api/ai/image/{gen_id}',
            'seed': seed,
            'params': {
                'prompt': prompt,
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
    """
    try:
        data = request.get_json()
        gen_id = data.get('id')
        params = data.get('params', {})

        if not gen_id:
            return jsonify({'error': 'Generation ID required'}), 400

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
            output_path=str(GENERATIONS_DIR / f'{gen_id}.png'),
            workflow_json=json.dumps(params.get('workflow', {})),
        )

        return jsonify({'saved': True, 'id': gen_id})

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

        # If seed is -1, generate a random one
        if seed == -1:
            import random
            seed = random.randint(0, 2147483647)

        logger.info(f"Video model: {video_model}")
        logger.info(f"Dimensions: {width}x{height}, frames: {frames}, fps: {fps}")
        logger.info(f"Seed: {seed}, steps: {steps}, cfg: {cfg_scale}")

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
        )
        logger.info(f"Workflow built with {len(workflow)} nodes")
        logger.debug(f"Workflow nodes: {list(workflow.keys())}")

        # Send to ComfyUI
        logger.info("Sending workflow to ComfyUI...")
        result = send_to_comfyui(workflow, gen_id)
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
    output_dir = COMFY_DIR / 'output'

    # Find the video file
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


def build_txt2img_workflow(prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, loras=None):
    """Build a ComfyUI workflow for text-to-image generation.

    Args:
        loras: List of dicts with 'filename' and 'strength' (0.0-2.0)
    """
    loras = loras or []

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
                "batch_size": 1
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


def build_video_workflow(prompt, input_image, video_model, model_type, width, height, frames, seed, steps, cfg_scale, motion_strength, gen_id):
    """Build a ComfyUI workflow for image-to-video generation.

    Supports LTX-Video, Wan2.1/2.2, and HunyuanVideo models.
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
        )


def build_ltx_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, gen_id):
    """Build workflow for LTX-Video image-to-video generation.

    Uses native ComfyUI LTX Video nodes (built-in support).
    """
    logger.info(f"Building LTX video workflow (native nodes):")
    logger.info(f"  prompt: {prompt[:100]}...")
    logger.info(f"  input_image: {input_image}")
    logger.info(f"  video_model: {video_model}")
    logger.info(f"  dimensions: {width}x{height}")
    logger.info(f"  frames: {frames}, seed: {seed}, steps: {steps}, cfg: {cfg_scale}")
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
        # 5. Encode negative prompt
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "worst quality, inconsistent motion, blurry, jittery, distorted, watermarks",
                "clip": ["2", 0]
            }
        },
        # 6. LTX Video conditioning (adds frame rate info)
        "6": {
            "class_type": "LTXVConditioning",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "frame_rate": 25.0
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
                "strength": 0.8
            }
        },
        # 8. LTX Scheduler - creates sigmas for sampling
        "8": {
            "class_type": "LTXVScheduler",
            "inputs": {
                "steps": steps,
                "max_shift": 2.05,
                "base_shift": 0.95,
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
                "sampler_name": "euler"
            }
        },
        # 11. Model sampling LTX (patches model for LTX-specific sampling)
        "11": {
            "class_type": "ModelSamplingLTXV",
            "inputs": {
                "model": ["1", 0],
                "max_shift": 2.05,
                "base_shift": 0.95
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
                "frame_rate": 25,
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "pingpong": False,
                "save_output": True
            }
        }
    }

    logger.info(f"LTX workflow built with {len(workflow)} nodes: {list(workflow.keys())}")
    return workflow


def build_wan_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, motion_strength, gen_id):
    """Build workflow for Wan2.x image-to-video generation using ComfyUI-WanVideoWrapper."""

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
        # Sample video
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
                "cfg": cfg_scale,
                "shift": 5.0,
                "scheduler": "unipc",
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
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            }
        }
    }

    return workflow


def build_hunyuan_video_workflow(prompt, input_image, video_model, width, height, frames, seed, steps, cfg_scale, gen_id):
    """Build workflow for HunyuanVideo image-to-video generation."""

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
                "embedded_cfg_scale": 6.0,
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
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"boomshakalaka_video_{gen_id}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
            }
        }
    }

    return workflow


def send_to_comfyui(workflow, gen_id):
    """Send a workflow to ComfyUI and wait for the result."""
    import httpx
    import time

    logger.info(f"send_to_comfyui called for gen_id: {gen_id}")

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
        max_wait = 300  # 5 minutes max
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

                    # Find the SaveImage output
                    for node_id, node_output in outputs.items():
                        if 'images' in node_output:
                            logger.info(f"Found images in node {node_id}")
                            for img in node_output['images']:
                                filename = img.get('filename')
                                subfolder = img.get('subfolder', '')
                                logger.info(f"Image file: {filename}, subfolder: {subfolder}")

                                # Copy the image to our generations directory
                                src_path = COMFY_DIR / 'output' / subfolder / filename
                                logger.info(f"Source path: {src_path}, exists: {src_path.exists()}")

                                if src_path.exists():
                                    # Create date-based directory
                                    date_dir = GENERATIONS_DIR / datetime.now().strftime('%Y/%m/%d')
                                    date_dir.mkdir(parents=True, exist_ok=True)

                                    # Copy to our directory
                                    dst_path = date_dir / f'{gen_id}_full.png'
                                    import shutil
                                    shutil.copy2(str(src_path), str(dst_path))
                                    logger.info(f"Copied to {dst_path}")

                                    # Also create a simple version in root for easy access
                                    simple_dst = GENERATIONS_DIR / f'{gen_id}.png'
                                    shutil.copy2(str(src_path), str(simple_dst))
                                    logger.info(f"Copied to {simple_dst}")

                                    return {
                                        'output_path': str(dst_path),
                                        'filename': filename
                                    }

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


def save_generation(gen_id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, workflow_json):
    """Save generation metadata to database."""
    import sqlite3

    db_path = DATABASES_DIR / 'generations.db'
    conn = sqlite3.connect(str(db_path))

    conn.execute('''
        INSERT INTO generations (id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, workflow_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (gen_id, prompt, negative_prompt, model, width, height, seed, steps, cfg_scale, sampler, output_path, workflow_json))

    conn.commit()
    conn.close()


# ============================================
# Main
# ============================================

def main():
    """Run the dashboard server"""
    print("Starting Boomshakalaka Management Dashboard...")
    print("Visit http://localhost:3003")
    app.run(host='0.0.0.0', port=3003, debug=False)


if __name__ == '__main__':
    main()
