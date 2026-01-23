# Automation Hub

The Automation Hub provides scheduled job execution and monitoring for Boomshakalaka. Access it via the dashboard at `/automation`.

## Overview

- **Dashboard**: http://localhost:3003/automation
- **Database**: `data/databases/jobs.db`
- **Job definitions**: `automation/jobs/`

## Current Jobs

### Precision Fleet Support Inventory Emails

Two monthly inventory reminder jobs send emails with Google Form links:

| Job ID | Location | Recipient | Form |
|--------|----------|-----------|------|
| `inventory_email_florida` | Florida | steve@precisionfleetsupport.com | [Florida Form](https://forms.gle/7zRwrhQ4s8sRkfpQ6) |
| `inventory_email_michigan` | Michigan | nathan@truetracking.com | [Michigan Form](https://forms.gle/9kotkd7mEN2ppu7v5) |

**Schedule**: 1st of each month at 9:00 AM

**Email Branding**: Precision Fleet Support (red/white theme)

## Configuration

### Gmail Credentials

The inventory email jobs require Gmail SMTP credentials. These are stored in `.env`:

```
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
```

To generate a Gmail App Password:
1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Create App Password: https://myaccount.google.com/apppasswords
3. Select "Mail" and your device, then copy the 16-character code

### Test vs Production Mode

**Switch to test mode** (sends to paul@paulstotts.com):
```bash
python3 -m automation.register_jobs
```

**Switch to production mode** (sends to actual recipients):
```bash
python3 -m automation.register_jobs --production
```

Test mode adds `[TEST]` prefix to email subjects.

## Managing Jobs

### Via Dashboard

1. Visit http://localhost:3003/automation
2. Click on a job to expand details
3. Available actions:
   - **Run Now**: Manually trigger the job
   - **Enable/Disable**: Toggle job scheduling
   - **View Logs**: See run history
   - **Edit Config**: Modify recipients and settings

### Via Command Line

**Trigger a job manually**:
```python
from automation.runner.executor import JobExecutor

executor = JobExecutor()
result = executor.run_job('inventory_email_florida', trigger_type='manual')
print(f'Success: {result.success}')
```

**List all jobs**:
```python
from automation.runner.db import init_database, get_all_jobs

init_database()
for job in get_all_jobs():
    print(f"{job['id']}: {job['name']} (enabled: {job['enabled']})")
```

## Adding New Jobs

1. Create a job class in `automation/jobs/`:

```python
from automation.jobs.base import BaseJob, JobResult

class MyNewJob(BaseJob):
    name = "my_job"
    description = "Does something useful"
    default_schedule = "0 9 * * *"  # Daily at 9 AM

    def run(self) -> JobResult:
        # Your job logic here
        return JobResult(success=True, exit_code=0)
```

2. Register the job in `automation/register_jobs.py`

3. Run the registration script:
```bash
python3 -m automation.register_jobs
```

## Schedule Format (Cron)

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

Examples:
- `0 9 1 * *` - 1st of month at 9:00 AM
- `0 9 * * *` - Daily at 9:00 AM
- `0 9 * * 1` - Every Monday at 9:00 AM
- `*/15 * * * *` - Every 15 minutes

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/automation/jobs` | List all jobs with stats |
| GET | `/api/automation/jobs/<id>` | Get single job details |
| PUT | `/api/automation/jobs/<id>` | Update job config |
| POST | `/api/automation/jobs/<id>/trigger` | Manually run a job |
| POST | `/api/automation/jobs/<id>/toggle` | Enable/disable job |
| GET | `/api/automation/jobs/<id>/runs` | Get job run history |
| GET | `/api/automation/stats` | Get overall statistics |
| GET | `/api/automation/failures` | Get recent failures |
| DELETE | `/api/automation/failures` | Clear recent failures |

## Troubleshooting

### "Gmail credentials not configured"

Ensure `.env` has valid `GMAIL_USER` and `GMAIL_APP_PASSWORD` values.

### "Authentication failed"

- Verify 2-Step Verification is enabled on the Gmail account
- Generate a new App Password
- Check the password doesn't have extra spaces

### Job not running on schedule

The cron scheduler must be running. Jobs are triggered by the system cron, not the dashboard. See `automation/cron/` for cron setup.

### Clear failed job history

Via dashboard: Click "Clear All" in the Recent Failures section

Via command line:
```python
from automation.runner.db import clear_recent_failures
clear_recent_failures(hours=24)  # Clears last 24 hours
```

## File Structure

```
automation/
├── README.md              # This file
├── __init__.py
├── register_jobs.py       # Job registration script
├── config/                # Configuration files
├── cron/                  # Cron job setup
├── jobs/                  # Job definitions
│   ├── base.py           # Base job class
│   └── inventory_email.py # PFS inventory email job
├── runner/                # Job execution engine
│   ├── db.py             # Database operations
│   ├── executor.py       # Job runner
│   └── alerts.py         # Failure notifications
└── sports/               # Sports-related automation
```
