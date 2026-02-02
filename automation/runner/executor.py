"""
Job executor with retry logic, database recording, and alert triggering.
"""

import importlib
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Type

from automation.jobs.base import BaseJob, JobResult
from automation.runner import db


logger = logging.getLogger("automation.executor")


class JobExecutor:
    """
    Executes jobs with retry logic, output capture, and database recording.

    Usage:
        executor = JobExecutor()
        result = executor.run_job('inventory_email', trigger_type='manual')
    """

    def __init__(self, db_path: Path = None):
        """
        Initialize the executor.

        Args:
            db_path: Path to the jobs database
        """
        self.db_path = db_path or db.DEFAULT_DB_PATH
        db.init_database(self.db_path)

    def run_job(
        self,
        job_id: str,
        trigger_type: str = 'manual',
        triggered_by: str = None,
        config_override: Dict[str, Any] = None
    ) -> JobResult:
        """
        Execute a job by ID with full retry and recording logic.

        Args:
            job_id: The job ID to execute
            trigger_type: How the job was triggered (manual, scheduled, retry)
            triggered_by: Who/what triggered the job
            config_override: Optional config to override stored config

        Returns:
            JobResult with execution details
        """
        # Get job definition
        job_def = db.get_job(job_id, self.db_path)
        if not job_def:
            return JobResult(
                success=False,
                exit_code=1,
                error_message=f"Job '{job_id}' not found"
            )

        if not job_def.get('enabled') and trigger_type == 'scheduled':
            return JobResult(
                success=False,
                exit_code=1,
                error_message=f"Job '{job_id}' is disabled"
            )

        # Load the job class
        job_class = self._load_job_class(job_def['job_class'])
        if not job_class:
            return JobResult(
                success=False,
                exit_code=1,
                error_message=f"Failed to load job class: {job_def['job_class']}"
            )

        # Prepare config
        config = {}
        if job_def.get('config_json'):
            try:
                config = json.loads(job_def['config_json'])
            except json.JSONDecodeError:
                pass
        if config_override:
            config.update(config_override)

        # Execute with retries
        max_retries = job_def.get('max_retries', 3)
        retry_delay = job_def.get('retry_delay_seconds', 60)

        result = None
        for attempt in range(1, max_retries + 1):
            run_id = str(uuid.uuid4())

            # Record run start
            db.create_run(
                job_id=job_id,
                run_id=run_id,
                trigger_type=trigger_type if attempt == 1 else 'retry',
                triggered_by=triggered_by,
                attempt_number=attempt,
                db_path=self.db_path
            )

            logger.info(f"Executing job '{job_def['name']}' (attempt {attempt}/{max_retries})")

            # Create and execute job instance
            try:
                job_instance = job_class(config=config, run_id=run_id)
                result = job_instance.execute()
            except Exception as e:
                result = JobResult(
                    success=False,
                    exit_code=1,
                    error_message=f"Job instantiation failed: {str(e)}"
                )

            # Record run completion
            db.complete_run(
                run_id=run_id,
                success=result.success,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                error_message=result.error_message,
                result_data=result.result_data,
                duration_seconds=result.duration_seconds,
                db_path=self.db_path
            )

            if result.success:
                logger.info(
                    f"Job '{job_def['name']}' completed successfully "
                    f"in {result.duration_seconds:.2f}s"
                )
                break
            else:
                logger.warning(
                    f"Job '{job_def['name']}' failed (attempt {attempt}): "
                    f"{result.error_message}"
                )
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)

        # Send alerts on final failure
        if not result.success and job_def.get('alert_on_failure'):
            self._send_alert(job_def, result)

        return result

    def run_job_direct(
        self,
        job_class: Type[BaseJob],
        config: Dict[str, Any] = None,
        job_id: str = None
    ) -> JobResult:
        """
        Execute a job class directly without database lookup.

        Useful for testing or one-off executions.

        Args:
            job_class: The job class to execute
            config: Job configuration
            job_id: Optional job ID for recording

        Returns:
            JobResult with execution details
        """
        run_id = str(uuid.uuid4())

        # Record if we have a job_id
        if job_id:
            db.create_run(
                job_id=job_id,
                run_id=run_id,
                trigger_type='direct',
                triggered_by='executor',
                db_path=self.db_path
            )

        # Execute
        job_instance = job_class(config=config or {}, run_id=run_id)
        result = job_instance.execute()

        # Record completion
        if job_id:
            db.complete_run(
                run_id=run_id,
                success=result.success,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                error_message=result.error_message,
                result_data=result.result_data,
                duration_seconds=result.duration_seconds,
                db_path=self.db_path
            )

        return result

    def _load_job_class(self, class_path: str) -> Optional[Type[BaseJob]]:
        """
        Dynamically load a job class from its module path.

        Args:
            class_path: Full path like 'automation.jobs.inventory_email.InventoryEmailJob'

        Returns:
            The job class or None if loading fails
        """
        try:
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            job_class = getattr(module, class_name)

            if not issubclass(job_class, BaseJob):
                logger.error(f"{class_path} is not a BaseJob subclass")
                return None

            return job_class

        except (ImportError, AttributeError) as e:
            logger.error(f"Failed to load job class '{class_path}': {e}")
            return None

    def _send_alert(self, job_def: Dict[str, Any], result: JobResult) -> None:
        """
        Send alert on job failure.

        Args:
            job_def: Job definition from database
            result: Failed job result
        """
        alert_channels = job_def.get('alert_channels', 'slack')

        logger.info(f"Sending failure alert for job '{job_def['name']}' via {alert_channels}")

        # Try Slack alert
        if 'slack' in alert_channels:
            try:
                from automation.runner.alerts import send_slack_alert
                send_slack_alert(
                    job_name=job_def['name'],
                    error_message=result.error_message,
                    stderr=result.stderr[:500] if result.stderr else None
                )
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")

        # Try email alert
        if 'email' in alert_channels:
            try:
                from automation.runner.alerts import send_email_alert
                send_email_alert(
                    job_name=job_def['name'],
                    error_message=result.error_message,
                    stderr=result.stderr[:1000] if result.stderr else None
                )
            except Exception as e:
                logger.error(f"Failed to send email alert: {e}")


def register_job(
    job_class: Type[BaseJob],
    schedule: str = None,
    config: Dict[str, Any] = None,
    enabled: bool = True,
    db_path: Path = None
) -> Dict[str, Any]:
    """
    Register a job class in the database.

    Convenience function to add a job to the database.

    Args:
        job_class: The job class to register
        schedule: Cron expression for scheduling
        config: Job configuration
        enabled: Whether the job is enabled

    Returns:
        The created job record
    """
    db.init_database(db_path)

    # Check if job already exists
    existing = db.get_job(job_class.name, db_path)
    if existing:
        logger.info(f"Job '{job_class.name}' already registered")
        return existing

    return db.create_job(
        job_id=job_class.name,
        name=job_class.name,
        job_class=f"{job_class.__module__}.{job_class.__name__}",
        description=job_class.description,
        schedule=schedule or job_class.default_schedule,
        schedule_human=_humanize_cron(schedule or job_class.default_schedule),
        config=config,
        enabled=enabled,
        db_path=db_path
    )


def _humanize_cron(cron_expr: str) -> Optional[str]:
    """Convert cron expression to human-readable format."""
    if not cron_expr:
        return None

    try:
        parts = cron_expr.split()
        if len(parts) != 5:
            return cron_expr

        minute, hour, day, month, dow = parts

        # Common patterns
        if cron_expr == "* * * * *":
            return "Every minute"
        if minute == "0" and hour == "*":
            return "Every hour"
        if minute == "0" and day == "*" and month == "*" and dow == "*":
            return f"Daily at {hour}:00"
        if minute == "0" and day == "1" and month == "*" and dow == "*":
            return f"Monthly on 1st at {hour}:00"
        if minute == "0" and day == "*" and month == "*" and dow == "0":
            return f"Weekly on Sunday at {hour}:00"

        return cron_expr
    except Exception:
        return cron_expr
