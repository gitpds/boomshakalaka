"""
Alert system for job failure notifications.

Supports Slack and Email alerting.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

# Try to load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


logger = logging.getLogger("automation.alerts")


def send_slack_alert(
    job_name: str,
    error_message: str,
    stderr: str = None,
    webhook_url: str = None
) -> bool:
    """
    Send a Slack notification for a job failure.

    Uses the existing Slack skill if available, otherwise uses webhook directly.

    Args:
        job_name: Name of the failed job
        error_message: The error message
        stderr: Optional stderr output
        webhook_url: Optional webhook URL (uses env var if not provided)

    Returns:
        True if sent successfully
    """
    # Try using the existing Slack skill
    try:
        skill_path = Path("/home/pds/boomshakalaka/skills/slack_notification")
        if skill_path.exists():
            import sys
            if str(skill_path) not in sys.path:
                sys.path.insert(0, str(skill_path))

            from notify import send_notification
            send_notification(
                title=f"Job Failed: {job_name}",
                message=error_message,
                status="failure",
                details=stderr
            )
            logger.info(f"Slack alert sent for job '{job_name}'")
            return True
    except Exception as e:
        logger.warning(f"Slack skill not available: {e}")

    # Fallback to direct webhook
    url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
    if not url:
        logger.warning("No Slack webhook URL configured")
        return False

    try:
        import urllib.request
        import json

        payload = {
            "text": f":x: *Job Failed: {job_name}*",
            "attachments": [
                {
                    "color": "#dc3545",
                    "fields": [
                        {
                            "title": "Error",
                            "value": error_message or "Unknown error",
                            "short": False
                        },
                        {
                            "title": "Time",
                            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "short": True
                        }
                    ]
                }
            ]
        }

        if stderr:
            payload["attachments"][0]["fields"].append({
                "title": "Output (truncated)",
                "value": f"```{stderr[:500]}```",
                "short": False
            })

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        urllib.request.urlopen(req)
        logger.info(f"Slack webhook alert sent for job '{job_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to send Slack webhook: {e}")
        return False


def send_email_alert(
    job_name: str,
    error_message: str,
    stderr: str = None,
    recipient: str = None,
    gmail_user: str = None,
    gmail_password: str = None
) -> bool:
    """
    Send an email notification for a job failure.

    Args:
        job_name: Name of the failed job
        error_message: The error message
        stderr: Optional stderr output
        recipient: Email recipient (uses env var if not provided)
        gmail_user: Gmail username (uses env var if not provided)
        gmail_password: Gmail app password (uses env var if not provided)

    Returns:
        True if sent successfully
    """
    recipient = recipient or os.getenv('ALERT_EMAIL_RECIPIENT')
    gmail_user = gmail_user or os.getenv('GMAIL_USER')
    gmail_password = gmail_password or os.getenv('GMAIL_APP_PASSWORD')

    if not all([recipient, gmail_user, gmail_password]):
        logger.warning("Email configuration incomplete - skipping email alert")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[Automation Alert] Job Failed: {job_name}"
        msg['From'] = gmail_user
        msg['To'] = recipient

        # Build HTML email
        html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0e16; padding: 30px;">
            <div style="max-width: 600px; margin: 0 auto; background: #151a24; border-radius: 12px; padding: 30px; border: 1px solid rgba(220, 53, 69, 0.3);">
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <span style="font-size: 24px; margin-right: 10px;">&#10060;</span>
                    <h1 style="color: #dc3545; margin: 0; font-size: 20px;">Job Failed: {job_name}</h1>
                </div>

                <div style="background: #1a1f2e; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                    <h3 style="color: #ff8c00; margin: 0 0 10px 0; font-size: 14px;">Error Message</h3>
                    <p style="color: #e4e4e4; margin: 0; font-family: monospace;">{error_message or 'Unknown error'}</p>
                </div>

                {f'''
                <div style="background: #1a1f2e; border-radius: 8px; padding: 16px; margin-bottom: 20px;">
                    <h3 style="color: #ff8c00; margin: 0 0 10px 0; font-size: 14px;">Output (truncated)</h3>
                    <pre style="color: #c4c4c4; margin: 0; font-size: 12px; white-space: pre-wrap; overflow-wrap: break-word;">{stderr[:1000] if stderr else ''}</pre>
                </div>
                ''' if stderr else ''}

                <div style="color: #888; font-size: 12px; border-top: 1px solid #2a2f3e; padding-top: 16px; margin-top: 20px;">
                    <p style="margin: 0;">Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p style="margin: 8px 0 0 0;">Sent by Boomshakalaka Automation Hub</p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        logger.info(f"Email alert sent for job '{job_name}' to {recipient}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False


def send_alert(
    job_name: str,
    error_message: str,
    stderr: str = None,
    channels: str = 'slack'
) -> None:
    """
    Send alerts to specified channels.

    Args:
        job_name: Name of the failed job
        error_message: The error message
        stderr: Optional stderr output
        channels: Comma-separated list of channels ('slack', 'email', or 'slack,email')
    """
    channels_list = [c.strip().lower() for c in channels.split(',')]

    if 'slack' in channels_list:
        send_slack_alert(job_name, error_message, stderr)

    if 'email' in channels_list:
        send_email_alert(job_name, error_message, stderr)
