"""
Monthly Inventory Email Job

Sends monthly inventory check reminders with Google Form links.
Migrated from N8N workflow.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from automation.jobs.base import BaseJob, JobResult

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


class InventoryEmailJob(BaseJob):
    """
    Send monthly inventory check emails with Google Form links.

    Config:
        recipients: List of email addresses
        form_urls: Dict mapping recipient name/email to form URL
        subject_prefix: Optional subject prefix (default: "Monthly Inventory Check")

    Example config:
        {
            "recipients": ["nathan@truetracking.com", "steve@precisionfleetsupport.com"],
            "form_urls": {
                "nathan@truetracking.com": "https://forms.gle/7zRwrhQ4s8sRkfpQ6",
                "steve@precisionfleetsupport.com": "https://forms.gle/9kotkd7mEN2ppu7v5"
            }
        }
    """

    name = "inventory_email"
    description = "Monthly inventory email with Google Form links"
    default_schedule = "0 9 1 * *"  # 1st of each month at 9 AM

    def validate_config(self) -> bool:
        """Validate that required configuration is present."""
        if not self.require_config('recipients'):
            return False

        recipients = self.config.get('recipients', [])
        if not recipients:
            print("No recipients configured")
            return False

        return True

    def run(self) -> JobResult:
        """Send inventory emails to all recipients."""
        gmail_user = os.getenv('GMAIL_USER')
        gmail_password = os.getenv('GMAIL_APP_PASSWORD')

        if not gmail_user or not gmail_password:
            return JobResult(
                success=False,
                exit_code=1,
                error_message="Gmail credentials not configured. Set GMAIL_USER and GMAIL_APP_PASSWORD environment variables."
            )

        recipients = self.config.get('recipients', [])
        form_urls = self.config.get('form_urls', {})
        subject_prefix = self.config.get('subject_prefix', 'Monthly Inventory Check')

        month_name = datetime.now().strftime('%B %Y')
        sent_count = 0
        errors = []

        print(f"Sending inventory emails for {month_name}")
        print(f"Recipients: {recipients}")

        for recipient in recipients:
            # Get form URL for this recipient
            form_url = form_urls.get(recipient) or form_urls.get('default', '#')

            try:
                self._send_email(
                    gmail_user=gmail_user,
                    gmail_password=gmail_password,
                    recipient=recipient,
                    subject=f"{subject_prefix} - {month_name}",
                    month_name=month_name,
                    form_url=form_url
                )
                sent_count += 1
                print(f"  Sent to: {recipient}")
            except Exception as e:
                error_msg = f"Failed to send to {recipient}: {str(e)}"
                errors.append(error_msg)
                print(f"  ERROR: {error_msg}")

        if errors:
            if sent_count == 0:
                return JobResult(
                    success=False,
                    exit_code=1,
                    error_message=f"All emails failed: {'; '.join(errors)}"
                )
            else:
                # Partial success
                return JobResult(
                    success=True,
                    exit_code=0,
                    error_message=f"Some emails failed: {'; '.join(errors)}",
                    result_data={
                        'sent_count': sent_count,
                        'total_recipients': len(recipients),
                        'errors': errors
                    }
                )

        return JobResult(
            success=True,
            exit_code=0,
            result_data={
                'sent_count': sent_count,
                'total_recipients': len(recipients),
                'month': month_name
            }
        )

    def _send_email(
        self,
        gmail_user: str,
        gmail_password: str,
        recipient: str,
        subject: str,
        month_name: str,
        form_url: str
    ) -> None:
        """Send a single inventory email."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = gmail_user
        msg['To'] = recipient

        # Get recipient's first name for personalization
        first_name = recipient.split('@')[0].capitalize()

        # Get location name if available
        location = self.config.get('location', '')
        location_text = f" - {location}" if location else ""

        # Build HTML email with Precision Fleet Support branding (red/white)
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e0e0e0; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="background: #CC0000; padding: 30px; text-align: center;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                                Precision Fleet Support
                            </h1>
                            <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">Monthly Inventory Check{location_text}</p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 30px;">
                            <p style="color: #333333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Hi {first_name},
                            </p>
                            <p style="color: #555555; font-size: 15px; line-height: 1.6; margin: 0 0 30px 0;">
                                It's time for the monthly inventory check. Please take a few minutes to complete the inventory form for <strong style="color: #CC0000;">{month_name}</strong>.
                            </p>

                            <!-- CTA Button -->
                            <table role="presentation" style="width: 100%; margin: 30px 0;">
                                <tr>
                                    <td style="text-align: center;">
                                        <a href="{form_url}"
                                           style="display: inline-block; background: #CC0000; color: #ffffff; padding: 16px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 2px 8px rgba(204, 0, 0, 0.3);">
                                            Complete Inventory Form
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <p style="color: #888888; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                                If the button doesn't work, you can copy and paste this link into your browser:
                            </p>
                            <p style="color: #CC0000; font-size: 13px; word-break: break-all; margin: 10px 0 0 0;">
                                {form_url}
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background: #f8f8f8; padding: 20px 30px; border-top: 1px solid #e0e0e0;">
                            <p style="margin: 0; color: #888888; font-size: 12px; text-align: center;">
                                This is an automated message from Precision Fleet Support
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        # Plain text alternative
        text = f"""
Precision Fleet Support - Monthly Inventory Check{location_text}
{month_name}

Hi {first_name},

It's time for the monthly inventory check. Please complete the inventory form for {month_name}.

Form Link: {form_url}

This is an automated message from Precision Fleet Support.
"""

        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
