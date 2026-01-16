"""
Job definitions for the Automation Hub.

Each job inherits from BaseJob and implements the run() method.
"""

from automation.jobs.base import BaseJob, JobResult

__all__ = ['BaseJob', 'JobResult']
