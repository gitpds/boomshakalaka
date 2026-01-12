# Slack Notification Skill

Sends notifications to `#boomshakalaka-alerts` channel.

## Setup

The `.env` file contains:
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C0A93DU5Z7A
```

Bot name: `@gcp_build_notifier`

## Usage

### As Python Module

```python
from skills.slack_notification import send_message, send_alert, send_blocks

# Simple text message
send_message("Hello world")

# Formatted alert
send_alert(
    title="Alert Title",
    message="Message body with *markdown* support",
    level="success",  # info, success, warning, error, money
    fields={
        "Field 1": "Value 1",
        "Field 2": "Value 2"
    }
)

# Custom Block Kit message
send_blocks([
    {"type": "header", "text": {"type": "plain_text", "text": "Header"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "Body"}}
], fallback_text="Notification")
```

### From Command Line

```bash
# Simple message
python skills/slack_notification/notify.py "Hello world"

# Formatted alert
python skills/slack_notification/notify.py \
    --title "Build Complete" \
    --level success \
    "All tests passed"

# With fields
python skills/slack_notification/notify.py \
    --title "Deploy" \
    --level info \
    --field "Environment" "production" \
    --field "Version" "1.2.3" \
    "Deployment started"
```

## Alert Levels

| Level | Emoji | Use Case |
|-------|-------|----------|
| `info` | ℹ️ | General information |
| `success` | ✅ | Successful operations |
| `warning` | ⚠️ | Warnings, attention needed |
| `error` | 🚨 | Errors, failures |
| `money` | 💰 | Financial alerts, opportunities |

## Functions

### `send_message(text: str) -> bool`
Send a simple text message. Returns True on success.

### `send_alert(title, message, level='info', fields=None) -> bool`
Send a formatted alert with optional fields. Returns True on success.

### `send_blocks(blocks: list, fallback_text: str) -> bool`
Send a custom Slack Block Kit message. Returns True on success.
