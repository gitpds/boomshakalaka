"""
Database operations for the Automation Hub.

Handles job definitions, run history, and statistics.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from contextlib import contextmanager


# Default database path
DEFAULT_DB_PATH = Path("/home/pds/boomshakalaka/data/databases/jobs.db")


@contextmanager
def get_db_connection(db_path: Path = None):
    """
    Context manager for database connections.

    Args:
        db_path: Path to the database file

    Yields:
        sqlite3 connection with row factory set to dict
    """
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_database(db_path: Path = None) -> None:
    """
    Initialize the jobs database with required tables.

    Args:
        db_path: Path to the database file
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Job definitions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                job_class TEXT NOT NULL,
                schedule TEXT,
                schedule_human TEXT,
                enabled INTEGER DEFAULT 1,
                config_json TEXT,
                max_retries INTEGER DEFAULT 3,
                retry_delay_seconds INTEGER DEFAULT 60,
                alert_on_failure INTEGER DEFAULT 1,
                alert_channels TEXT DEFAULT 'slack',
                depends_on TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run_at TIMESTAMP,
                next_run_at TIMESTAMP
            )
        """)

        # Job execution history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                run_id TEXT NOT NULL UNIQUE,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                duration_seconds REAL,
                status TEXT DEFAULT 'running',
                exit_code INTEGER,
                attempt_number INTEGER DEFAULT 1,
                trigger_type TEXT DEFAULT 'scheduled',
                triggered_by TEXT,
                stdout TEXT,
                stderr TEXT,
                error_message TEXT,
                result_json TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)

        # Job statistics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_stats (
                job_id TEXT PRIMARY KEY,
                total_runs INTEGER DEFAULT 0,
                successful_runs INTEGER DEFAULT 0,
                failed_runs INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0,
                avg_duration_seconds REAL,
                last_success_at TIMESTAMP,
                last_failure_at TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_status ON job_runs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_started_at ON job_runs(started_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_enabled ON jobs(enabled)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON jobs(next_run_at)")

        conn.commit()


# --- Job CRUD Operations ---

def get_all_jobs(db_path: Path = None) -> List[Dict[str, Any]]:
    """Get all jobs with their stats."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.*,
                   s.total_runs, s.successful_runs, s.failed_runs,
                   s.success_rate, s.avg_duration_seconds,
                   s.last_success_at, s.last_failure_at
            FROM jobs j
            LEFT JOIN job_stats s ON j.id = s.job_id
            ORDER BY j.name
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_job(job_id: str, db_path: Path = None) -> Optional[Dict[str, Any]]:
    """Get a single job by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.*,
                   s.total_runs, s.successful_runs, s.failed_runs,
                   s.success_rate, s.avg_duration_seconds,
                   s.last_success_at, s.last_failure_at
            FROM jobs j
            LEFT JOIN job_stats s ON j.id = s.job_id
            WHERE j.id = ?
        """, (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_job(
    job_id: str,
    name: str,
    job_class: str,
    description: str = None,
    schedule: str = None,
    schedule_human: str = None,
    config: Dict[str, Any] = None,
    enabled: bool = True,
    max_retries: int = 3,
    alert_on_failure: bool = True,
    db_path: Path = None
) -> Dict[str, Any]:
    """Create a new job."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (
                id, name, job_class, description, schedule, schedule_human,
                config_json, enabled, max_retries, alert_on_failure
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, name, job_class, description, schedule, schedule_human,
            json.dumps(config) if config else None,
            1 if enabled else 0, max_retries, 1 if alert_on_failure else 0
        ))

        # Initialize stats
        cursor.execute("INSERT INTO job_stats (job_id) VALUES (?)", (job_id,))

        conn.commit()
        return get_job(job_id, db_path)


def update_job(job_id: str, updates: Dict[str, Any], db_path: Path = None) -> Optional[Dict[str, Any]]:
    """Update a job's fields."""
    allowed_fields = {
        'name', 'description', 'schedule', 'schedule_human', 'enabled',
        'config_json', 'max_retries', 'alert_on_failure', 'alert_channels'
    }

    # Filter to allowed fields
    fields = {k: v for k, v in updates.items() if k in allowed_fields}
    if not fields:
        return get_job(job_id, db_path)

    # Handle config specially
    if 'config' in updates:
        fields['config_json'] = json.dumps(updates['config'])

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE jobs SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values + [job_id]
        )
        conn.commit()

    return get_job(job_id, db_path)


def toggle_job(job_id: str, db_path: Path = None) -> Optional[Dict[str, Any]]:
    """Toggle a job's enabled state."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET enabled = NOT enabled, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (job_id,)
        )
        conn.commit()
    return get_job(job_id, db_path)


def delete_job(job_id: str, db_path: Path = None) -> bool:
    """Delete a job and its history."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_runs WHERE job_id = ?", (job_id,))
        cursor.execute("DELETE FROM job_stats WHERE job_id = ?", (job_id,))
        cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- Run History Operations ---

def create_run(
    job_id: str,
    run_id: str,
    trigger_type: str = 'manual',
    triggered_by: str = None,
    attempt_number: int = 1,
    db_path: Path = None
) -> Dict[str, Any]:
    """Create a new job run record."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_runs (
                job_id, run_id, started_at, status,
                trigger_type, triggered_by, attempt_number
            ) VALUES (?, ?, ?, 'running', ?, ?, ?)
        """, (job_id, run_id, datetime.now().isoformat(), trigger_type, triggered_by, attempt_number))
        conn.commit()

        cursor.execute("SELECT * FROM job_runs WHERE run_id = ?", (run_id,))
        return dict(cursor.fetchone())


def complete_run(
    run_id: str,
    success: bool,
    exit_code: int = 0,
    stdout: str = None,
    stderr: str = None,
    error_message: str = None,
    result_data: Dict[str, Any] = None,
    duration_seconds: float = 0,
    db_path: Path = None
) -> Dict[str, Any]:
    """Complete a job run with results."""
    status = 'success' if success else 'failed'

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE job_runs SET
                completed_at = ?,
                status = ?,
                exit_code = ?,
                stdout = ?,
                stderr = ?,
                error_message = ?,
                result_json = ?,
                duration_seconds = ?
            WHERE run_id = ?
        """, (
            datetime.now().isoformat(), status, exit_code,
            stdout, stderr, error_message,
            json.dumps(result_data) if result_data else None,
            duration_seconds, run_id
        ))

        # Get job_id for stats update
        cursor.execute("SELECT job_id FROM job_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row:
            job_id = row['job_id']

            # Update job's last_run_at
            cursor.execute(
                "UPDATE jobs SET last_run_at = CURRENT_TIMESTAMP WHERE id = ?",
                (job_id,)
            )

            # Update stats
            _update_job_stats(cursor, job_id, success, duration_seconds)

        conn.commit()

        cursor.execute("SELECT * FROM job_runs WHERE run_id = ?", (run_id,))
        return dict(cursor.fetchone())


def _update_job_stats(cursor, job_id: str, success: bool, duration: float) -> None:
    """Update job statistics after a run."""
    if success:
        cursor.execute("""
            UPDATE job_stats SET
                total_runs = total_runs + 1,
                successful_runs = successful_runs + 1,
                success_rate = CAST(successful_runs + 1 AS REAL) / (total_runs + 1) * 100,
                avg_duration_seconds = (COALESCE(avg_duration_seconds, 0) * total_runs + ?) / (total_runs + 1),
                last_success_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (duration, job_id))
    else:
        cursor.execute("""
            UPDATE job_stats SET
                total_runs = total_runs + 1,
                failed_runs = failed_runs + 1,
                success_rate = CAST(successful_runs AS REAL) / (total_runs + 1) * 100,
                last_failure_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        """, (job_id,))


def get_job_runs(job_id: str, limit: int = 20, db_path: Path = None) -> List[Dict[str, Any]]:
    """Get recent runs for a job."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM job_runs
            WHERE job_id = ?
            ORDER BY started_at DESC
            LIMIT ?
        """, (job_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_run(run_id: str, db_path: Path = None) -> Optional[Dict[str, Any]]:
    """Get a single run by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_recent_failures(hours: int = 24, db_path: Path = None) -> List[Dict[str, Any]]:
    """Get failures from the last N hours."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, j.name as job_name
            FROM job_runs r
            JOIN jobs j ON r.job_id = j.id
            WHERE r.status = 'failed'
            AND r.completed_at >= datetime('now', ? || ' hours')
            ORDER BY r.completed_at DESC
        """, (f'-{hours}',))
        return [dict(row) for row in cursor.fetchall()]


def clear_recent_failures(hours: int = 24, db_path: Path = None) -> int:
    """Clear (delete) failure records from the last N hours. Returns count of deleted records."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM job_runs
            WHERE status = 'failed'
            AND completed_at >= datetime('now', ? || ' hours')
        """, (f'-{hours}',))
        conn.commit()
        return cursor.rowcount


def get_stats_summary(db_path: Path = None) -> Dict[str, Any]:
    """Get overall statistics summary."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # Total jobs
        cursor.execute("SELECT COUNT(*) as count FROM jobs")
        total_jobs = cursor.fetchone()['count']

        # Enabled jobs
        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE enabled = 1")
        enabled_jobs = cursor.fetchone()['count']

        # 24h stats
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
            FROM job_runs
            WHERE started_at >= datetime('now', '-24 hours')
        """)
        row = cursor.fetchone()

        return {
            'total_jobs': total_jobs,
            'enabled_jobs': enabled_jobs,
            'runs_24h': row['total'] or 0,
            'successes_24h': row['successes'] or 0,
            'failures_24h': row['failures'] or 0,
            'success_rate_24h': round(
                (row['successes'] / row['total'] * 100) if row['total'] else 0, 1
            )
        }
