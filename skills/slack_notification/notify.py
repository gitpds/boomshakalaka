#!/usr/bin/env python3
"""
Boomshakalaka Slack Notification Skill

Sends notifications to #boomshakalaka-alerts channel.

Usage as module:
    from skills.slack_notification.notify import send_message, send_alert

    send_message("Hello world")
    send_alert("Warning", "Something happened", level="warning")

Usage from command line:
    python notify.py "Simple message"
    python notify.py --title "Alert" --message "Details here" --level warning
"""

import os
import sys
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load config from skill directory
SKILL_DIR = Path(__file__).parent
load_dotenv(SKILL_DIR / '.env')

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
SLACK_CHANNEL_ID = os.getenv('SLACK_CHANNEL_ID')

# Level colors/emoji
LEVELS = {
    'info': {'emoji': 'ℹ️', 'color': '#3b82f6'},
    'success': {'emoji': '✅', 'color': '#22c55e'},
    'warning': {'emoji': '⚠️', 'color': '#f59e0b'},
    'error': {'emoji': '🚨', 'color': '#ef4444'},
    'money': {'emoji': '💰', 'color': '#22c55e'},
}


def send_message(text: str) -> bool:
    """Send a simple text message to Slack."""
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Error: Slack credentials not configured")
        return False

    try:
        response = requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
                'Content-Type': 'application/json'
            },
            json={
                'channel': SLACK_CHANNEL_ID,
                'text': text
            },
            timeout=30
        )
        data = response.json()
        return data.get('ok', False)
    except Exception as e:
        print(f"Error sending Slack message: {e}")
        return False


def send_alert(title: str, message: str, level: str = 'info', fields: dict = None) -> bool:
    """
    Send a formatted alert to Slack.

    Args:
        title: Alert title/header
        message: Main message body (supports markdown)
        level: One of 'info', 'success', 'warning', 'error', 'money'
        fields: Optional dict of field_name: value pairs to display
    """
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Error: Slack credentials not configured")
        return False

    level_config = LEVELS.get(level, LEVELS['info'])
    emoji = level_config['emoji']

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {title}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message
            }
        }
    ]

    # Add fields if provided
    if fields:
        field_blocks = []
        for name, value in fields.items():
            field_blocks.append({
                "type": "mrkdwn",
                "text": f"*{name}*\n{value}"
            })

        # Slack allows max 10 fields, split into sections of 2
        for i in range(0, len(field_blocks), 2):
            blocks.append({
                "type": "section",
                "fields": field_blocks[i:i+2]
            })

    try:
        response = requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
                'Content-Type': 'application/json'
            },
            json={
                'channel': SLACK_CHANNEL_ID,
                'blocks': blocks,
                'text': f"{emoji} {title}: {message}"  # Fallback
            },
            timeout=30
        )
        data = response.json()
        if data.get('ok'):
            return True
        else:
            print(f"Slack API error: {data.get('error')}")
            return False
    except Exception as e:
        print(f"Error sending Slack alert: {e}")
        return False


def send_blocks(blocks: list, fallback_text: str = "Notification") -> bool:
    """Send a custom Block Kit message to Slack."""
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Error: Slack credentials not configured")
        return False

    try:
        response = requests.post(
            'https://slack.com/api/chat.postMessage',
            headers={
                'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
                'Content-Type': 'application/json'
            },
            json={
                'channel': SLACK_CHANNEL_ID,
                'blocks': blocks,
                'text': fallback_text
            },
            timeout=30
        )
        data = response.json()
        return data.get('ok', False)
    except Exception as e:
        print(f"Error sending Slack blocks: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Send Slack notification to #boomshakalaka-alerts')
    parser.add_argument('message', nargs='?', help='Simple message to send')
    parser.add_argument('--title', '-t', help='Alert title (enables formatted mode)')
    parser.add_argument('--level', '-l', choices=LEVELS.keys(), default='info',
                        help='Alert level (default: info)')
    parser.add_argument('--field', '-f', action='append', nargs=2, metavar=('NAME', 'VALUE'),
                        help='Add a field (can be repeated)')

    args = parser.parse_args()

    if not args.message and not args.title:
        parser.print_help()
        sys.exit(1)

    # Simple message mode
    if args.message and not args.title:
        success = send_message(args.message)
        sys.exit(0 if success else 1)

    # Formatted alert mode
    fields = dict(args.field) if args.field else None
    message = args.message or ""
    success = send_alert(args.title, message, args.level, fields)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
