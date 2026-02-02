#!/usr/bin/env python3
"""
Register automation jobs in the database.

Run this script to set up initial jobs or update job configurations.

Usage:
    python -m automation.register_jobs
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from automation.runner.db import init_database, create_job, get_job, update_job


def register_inventory_email_job(job_id: str, name: str, location: str,
                                  recipients: list, form_urls: dict,
                                  test_mode: bool = True):
    """
    Register an inventory email job for a specific location.

    Args:
        job_id: Unique job identifier
        name: Human-readable job name
        location: Location name (e.g., "Florida", "Michigan")
        recipients: List of email recipients
        form_urls: Dict mapping recipient email to form URL
        test_mode: If True, use test email recipient. If False, use production recipients.
    """
    # Check if job exists
    existing = get_job(job_id)

    if test_mode:
        # Test configuration - sends to paul@paulstotts.com
        config = {
            "recipients": ["paul@paulstotts.com"],
            "form_urls": {
                "paul@paulstotts.com": list(form_urls.values())[0] if form_urls else "https://forms.gle/example"
            },
            "subject_prefix": f"[TEST] Monthly Inventory Check - {location}",
            "location": location
        }
        print("  Using TEST mode - emails will go to paul@paulstotts.com")
    else:
        # Production configuration
        config = {
            "recipients": recipients,
            "form_urls": form_urls,
            "subject_prefix": f"Monthly Inventory Check - {location}",
            "location": location
        }
        print(f"  Using PRODUCTION mode - emails will go to: {', '.join(recipients)}")

    if existing:
        print(f"  Job '{job_id}' already exists, updating config...")
        import json
        update_job(job_id, {'config_json': json.dumps(config)})
        print(f"  Updated job: {job_id}")
    else:
        print(f"  Creating new job: {job_id}")
        job = create_job(
            job_id=job_id,
            name=name,
            job_class="automation.jobs.inventory_email.InventoryEmailJob",
            description=f"Monthly inventory reminder for {location} with Google Form link",
            schedule="0 9 1 * *",  # 1st of month at 9 AM
            schedule_human="Monthly on 1st at 9:00 AM",
            config=config,
            enabled=True,
            max_retries=2,
            alert_on_failure=True
        )
        print(f"  Created job: {job['name']}")

    return get_job(job_id)


def register_florida_inventory_job(test_mode: bool = True):
    """Register the Florida inventory email job."""
    return register_inventory_email_job(
        job_id="inventory_email_florida",
        name="Florida Inventory Email",
        location="Florida",
        recipients=["steve@precisionfleetsupport.com"],
        form_urls={
            "steve@precisionfleetsupport.com": "https://forms.gle/7zRwrhQ4s8sRkfpQ6"
        },
        test_mode=test_mode
    )


def register_michigan_inventory_job(test_mode: bool = True):
    """Register the Michigan inventory email job."""
    return register_inventory_email_job(
        job_id="inventory_email_michigan",
        name="Michigan Inventory Email",
        location="Michigan",
        recipients=["nathan@truetracking.com"],
        form_urls={
            "nathan@truetracking.com": "https://forms.gle/9kotkd7mEN2ppu7v5"
        },
        test_mode=test_mode
    )


def main():
    """Register all jobs."""
    import argparse

    parser = argparse.ArgumentParser(description='Register automation jobs')
    parser.add_argument('--production', action='store_true',
                        help='Use production configuration (sends to real recipients)')
    args = parser.parse_args()

    print("Initializing jobs database...")
    init_database()

    print("\n=== Registering Precision Fleet Support Inventory Jobs ===\n")

    test_mode = not args.production

    # Register Florida inventory job
    print("Florida Inventory:")
    florida_job = register_florida_inventory_job(test_mode=test_mode)
    print(f"  ID: {florida_job['id']}")
    print(f"  Schedule: {florida_job['schedule_human']}")

    # Register Michigan inventory job
    print("\nMichigan Inventory:")
    michigan_job = register_michigan_inventory_job(test_mode=test_mode)
    print(f"  ID: {michigan_job['id']}")
    print(f"  Schedule: {michigan_job['schedule_human']}")

    print("\n=== Done ===")
    print("\nYou can now:")
    print("1. Visit http://localhost:3003/automation to see the jobs")
    print("2. Click 'Run Now' to test each job")
    print("3. Run with --production to switch to production recipients")


if __name__ == '__main__':
    main()
