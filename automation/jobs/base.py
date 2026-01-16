"""
Base job class that all automation jobs inherit from.
Provides stdout/stderr capture, timing, and error handling.
"""

import io
import sys
import time
import traceback
import logging
from abc import ABC, abstractmethod
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class JobResult:
    """Result of a job execution."""
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None
    result_data: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'error_message': self.error_message,
            'result_data': self.result_data,
            'duration_seconds': self.duration_seconds,
        }


class BaseJob(ABC):
    """
    Abstract base class for all automation jobs.

    Subclasses must implement:
        - run(self) -> JobResult

    Optional overrides:
        - validate_config(self) -> bool
        - on_success(self, result: JobResult)
        - on_failure(self, result: JobResult)

    Example:
        class MyJob(BaseJob):
            name = "my_job"
            description = "Does something useful"
            default_schedule = "0 9 * * *"  # Daily at 9 AM

            def run(self) -> JobResult:
                print("Doing something...")
                return JobResult(success=True)
    """

    # Class-level metadata (override in subclasses)
    name: str = "base_job"
    description: str = "Base job class"
    default_schedule: Optional[str] = None  # Cron expression

    def __init__(self, config: Dict[str, Any] = None, run_id: str = None):
        """
        Initialize the job.

        Args:
            config: Job-specific configuration dictionary
            run_id: Unique identifier for this execution run
        """
        self.config = config or {}
        self.run_id = run_id
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up a logger for this job."""
        logger = logging.getLogger(f"automation.job.{self.name}")
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def execute(self) -> JobResult:
        """
        Execute the job with full output capture.

        This is the main entry point called by the executor.
        Do not override this method - override run() instead.

        Returns:
            JobResult with captured output, timing, and status
        """
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        start_time = time.time()

        try:
            # Validate config first
            if not self.validate_config():
                return JobResult(
                    success=False,
                    exit_code=1,
                    error_message="Configuration validation failed",
                    duration_seconds=time.time() - start_time
                )

            # Run with output capture
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                result = self.run()

            # Merge captured output into result
            result.stdout = stdout_capture.getvalue() + (result.stdout or "")
            result.stderr = stderr_capture.getvalue() + (result.stderr or "")
            result.duration_seconds = time.time() - start_time

            # Call hooks
            if result.success:
                self.on_success(result)
            else:
                self.on_failure(result)

            return result

        except Exception as e:
            # Handle unexpected exceptions
            duration = time.time() - start_time
            error_tb = traceback.format_exc()

            result = JobResult(
                success=False,
                exit_code=1,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue() + f"\n\nException:\n{error_tb}",
                error_message=str(e),
                duration_seconds=duration
            )
            self.on_failure(result)
            return result

    @abstractmethod
    def run(self) -> JobResult:
        """
        Main job logic. Override this in subclasses.

        Returns:
            JobResult indicating success/failure and any output
        """
        pass

    def validate_config(self) -> bool:
        """
        Validate job configuration before execution.

        Override this to add custom validation logic.

        Returns:
            True if config is valid, False otherwise
        """
        return True

    def on_success(self, result: JobResult) -> None:
        """
        Called after successful execution.

        Override for custom success handling (e.g., cleanup).
        """
        self.logger.info(
            f"Job '{self.name}' completed successfully in {result.duration_seconds:.2f}s"
        )

    def on_failure(self, result: JobResult) -> None:
        """
        Called after failed execution.

        Override for custom failure handling (e.g., cleanup, notifications).
        """
        self.logger.error(
            f"Job '{self.name}' failed: {result.error_message}"
        )

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Safely get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def require_config(self, *keys: str) -> bool:
        """
        Check that required configuration keys are present.

        Args:
            keys: Required configuration keys

        Returns:
            True if all keys present, False otherwise
        """
        missing = [k for k in keys if k not in self.config]
        if missing:
            self.logger.error(f"Missing required config keys: {missing}")
            return False
        return True
