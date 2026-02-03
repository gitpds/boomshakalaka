"""
Project Management Database Layer

SQLite-based storage for areas, projects, tasks, and personal lists.
User-driven creation with optional directory linking.
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


# Database location
PROJECT_ROOT = Path('/home/pds/boomshakalaka')
DB_FILE = PROJECT_ROOT / 'data' / 'projects.db'
HOME_DIR = Path('/home/pds')

# Available icons for areas
AVAILABLE_ICONS = [
    'folder', 'briefcase', 'cpu', 'zap', 'brain', 'server',
    'code', 'database', 'globe', 'home', 'star', 'heart',
    'rocket', 'tool', 'terminal', 'layers', 'box', 'archive'
]

# Default colors for areas
DEFAULT_COLORS = [
    '#10b981',  # green
    '#8b5cf6',  # purple
    '#ff8c00',  # orange
    '#3b82f6',  # blue
    '#ec4899',  # pink
    '#ef4444',  # red
    '#f59e0b',  # amber
    '#06b6d4',  # cyan
    '#6b7280',  # gray
]


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_database() -> None:
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Areas table - user-created with optional directory linking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS areas (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path TEXT,
            icon TEXT DEFAULT 'folder',
            color TEXT DEFAULT '#6b7280',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')

    # Migration: Remove UNIQUE constraint from path if it exists
    # Check if we need to migrate (old schema had UNIQUE on path)
    cursor.execute("PRAGMA table_info(areas)")
    # This is safe - if table was just created, no migration needed

    # Projects table - within areas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            area_id TEXT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (area_id) REFERENCES areas (id) ON DELETE SET NULL
        )
    ''')

    # Tasks table - with hierarchy support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'backlog',
            priority TEXT DEFAULT 'medium',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )
    ''')

    # Personal lists table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'list',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')

    # List items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS list_items (
            id TEXT PRIMARY KEY,
            list_id TEXT NOT NULL,
            content TEXT NOT NULL,
            checked INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (list_id) REFERENCES lists (id) ON DELETE CASCADE
        )
    ''')

    # Task attachments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_attachments (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
    ''')

    # SMS Allowlist table - for Twilio bidirectional SMS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_allowlist (
            phone_number TEXT PRIMARY KEY,
            added_at TEXT NOT NULL,
            added_by TEXT,
            name TEXT
        )
    ''')

    # SMS Conversations table - store message history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_conversations (
            id TEXT PRIMARY KEY,
            phone_number TEXT NOT NULL,
            direction TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            twilio_sid TEXT
        )
    ''')

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_area ON projects (area_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_list_items_list ON list_items (list_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_attachments_task ON task_attachments (task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sms_conversations_phone ON sms_conversations (phone_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sms_conversations_timestamp ON sms_conversations (timestamp)')

    conn.commit()
    conn.close()


# =============================================================================
# Area Functions
# =============================================================================

def create_area(name: str, icon: str = 'folder', color: str = '#6b7280',
                path: Optional[str] = None) -> dict:
    """Create a new area manually."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Get max sort order
    cursor.execute('SELECT MAX(sort_order) FROM areas')
    max_order = cursor.fetchone()[0] or 0

    area_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO areas (id, name, path, icon, color, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (area_id, name, path, icon, color, max_order + 1, now))

    conn.commit()
    conn.close()
    return get_area(area_id)


def update_area(area_id: str, **kwargs) -> Optional[dict]:
    """Update an area."""
    conn = get_db_connection()
    cursor = conn.cursor()

    allowed_fields = {'name', 'path', 'icon', 'color', 'sort_order'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        conn.close()
        return get_area(area_id)

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [area_id]

    cursor.execute(f'UPDATE areas SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

    return get_area(area_id)


def delete_area(area_id: str) -> bool:
    """Delete an area. Projects in this area will have area_id set to NULL."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM areas WHERE id = ?', (area_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def import_areas_from_directory(directory_names: list[str] = None) -> list[dict]:
    """
    Import areas from filesystem directories.
    Optional convenience feature - creates areas from existing directories.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Default directories if none specified
    if directory_names is None:
        directory_names = ['businesses', 'robotics', 'boomshakalaka', 'millcityai', 'mcp_servers']

    # Default styling for known directories
    known_defaults = {
        'businesses': {'icon': 'briefcase', 'color': '#10b981'},
        'robotics': {'icon': 'cpu', 'color': '#8b5cf6'},
        'boomshakalaka': {'icon': 'zap', 'color': '#ff8c00'},
        'millcityai': {'icon': 'brain', 'color': '#3b82f6'},
        'mcp_servers': {'icon': 'server', 'color': '#ec4899'},
    }

    imported_areas = []

    for i, area_name in enumerate(directory_names):
        area_path = HOME_DIR / area_name
        if not area_path.exists():
            continue

        defaults = known_defaults.get(area_name, {'icon': 'folder', 'color': '#6b7280'})

        # Check if area with this path already exists
        cursor.execute('SELECT id FROM areas WHERE path = ?', (str(area_path),))
        existing = cursor.fetchone()

        if existing:
            area_id = existing['id']
        else:
            # Get max sort order
            cursor.execute('SELECT MAX(sort_order) FROM areas')
            max_order = cursor.fetchone()[0] or 0

            area_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO areas (id, name, path, icon, color, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (area_id, area_name, str(area_path), defaults['icon'],
                  defaults['color'], max_order + 1, now))

        imported_areas.append({
            'id': area_id,
            'name': area_name,
            'path': str(area_path),
            'icon': defaults['icon'],
            'color': defaults['color']
        })

    conn.commit()
    conn.close()
    return imported_areas


def get_all_areas() -> list[dict]:
    """Get all areas with project and task counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.*,
               COUNT(DISTINCT p.id) as project_count,
               COUNT(DISTINCT t.id) as task_count,
               COUNT(DISTINCT CASE WHEN t.status = 'todo' THEN t.id END) as todo_count,
               COUNT(DISTINCT CASE WHEN t.status = 'in_progress' THEN t.id END) as in_progress_count
        FROM areas a
        LEFT JOIN projects p ON p.area_id = a.id
        LEFT JOIN tasks t ON t.project_id = p.id AND t.status != 'done'
        GROUP BY a.id
        ORDER BY a.sort_order, a.name
    ''')

    areas = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return areas


def get_area(area_id: str) -> Optional[dict]:
    """Get a single area by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM areas WHERE id = ?', (area_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_area_by_name(name: str) -> Optional[dict]:
    """Get a single area by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM areas WHERE name = ?', (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# Project Functions
# =============================================================================

def import_projects_from_directory(area_id: str) -> list[dict]:
    """
    Import projects from an area's linked directory.
    Optional convenience feature - discovers subdirectories as projects.
    Requires the area to have a path set.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Get area path
    cursor.execute('SELECT path FROM areas WHERE id = ?', (area_id,))
    area = cursor.fetchone()
    if not area or not area['path']:
        conn.close()
        return []

    area_path = Path(area['path'])
    if not area_path.exists():
        conn.close()
        return []

    imported_projects = []

    # Scan subdirectories
    for subdir in sorted(area_path.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith('.'):
            continue
        if subdir.name in ['__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build']:
            continue

        # Check if project with this path already exists
        cursor.execute('SELECT id FROM projects WHERE path = ?', (str(subdir),))
        existing = cursor.fetchone()

        if existing:
            project_id = existing['id']
        else:
            project_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO projects (id, area_id, name, path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (project_id, area_id, subdir.name, str(subdir), now, now))

        imported_projects.append({
            'id': project_id,
            'name': subdir.name,
            'path': str(subdir)
        })

    conn.commit()
    conn.close()
    return imported_projects


def get_all_projects() -> list[dict]:
    """Get all projects with task counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.*, a.name as area_name, a.color as area_color,
               COUNT(t.id) as task_count,
               COUNT(CASE WHEN t.status = 'todo' THEN 1 END) as todo_count,
               COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress_count,
               COUNT(CASE WHEN t.status = 'done' THEN 1 END) as done_count
        FROM projects p
        LEFT JOIN areas a ON a.id = p.area_id
        LEFT JOIN tasks t ON t.project_id = p.id
        GROUP BY p.id
        ORDER BY a.sort_order, p.name
    ''')

    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects


def get_projects_by_area(area_id: str) -> list[dict]:
    """Get projects for a specific area with task counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.*,
               COUNT(t.id) as task_count,
               COUNT(CASE WHEN t.status = 'todo' THEN 1 END) as todo_count,
               COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress_count,
               COUNT(CASE WHEN t.status = 'done' THEN 1 END) as done_count
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id
        WHERE p.area_id = ?
        GROUP BY p.id
        ORDER BY p.name
    ''', (area_id,))

    projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return projects


def get_project(project_id: str) -> Optional[dict]:
    """Get a single project by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.*, a.name as area_name, a.color as area_color
        FROM projects p
        LEFT JOIN areas a ON a.id = p.area_id
        WHERE p.id = ?
    ''', (project_id,))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_project_by_name(project_name: str, area_name: Optional[str] = None) -> Optional[dict]:
    """Get a project by name, optionally filtered by area."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if area_name:
        cursor.execute('''
            SELECT p.*, a.name as area_name, a.color as area_color
            FROM projects p
            LEFT JOIN areas a ON a.id = p.area_id
            WHERE p.name = ? AND a.name = ?
        ''', (project_name, area_name))
    else:
        cursor.execute('''
            SELECT p.*, a.name as area_name, a.color as area_color
            FROM projects p
            LEFT JOIN areas a ON a.id = p.area_id
            WHERE p.name = ?
        ''', (project_name,))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_project(area_id: str, name: str, description: str = '',
                   path: Optional[str] = None) -> dict:
    """Create a new project."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    project_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO projects (id, area_id, name, description, path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (project_id, area_id, name, description, path, now, now))

    conn.commit()
    conn.close()

    return get_project(project_id)


def update_project(project_id: str, **kwargs) -> Optional[dict]:
    """Update a project."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    allowed_fields = {'name', 'description', 'status', 'area_id', 'path'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    updates['updated_at'] = now

    if not updates or (len(updates) == 1 and 'updated_at' in updates):
        conn.close()
        return get_project(project_id)

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [project_id]

    cursor.execute(f'UPDATE projects SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    """Delete a project and its tasks."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


# =============================================================================
# Task Functions
# =============================================================================

def get_tasks_by_project(project_id: str) -> list[dict]:
    """Get all tasks for a project."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM tasks
        WHERE project_id = ?
        ORDER BY
            CASE status
                WHEN 'in_progress' THEN 0
                WHEN 'todo' THEN 1
                WHEN 'backlog' THEN 2
                WHEN 'done' THEN 3
            END,
            CASE priority
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
            END,
            sort_order
    ''', (project_id,))

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks


def get_all_tasks(status: Optional[str] = None, priority: Optional[str] = None) -> list[dict]:
    """Get all tasks, optionally filtered."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
        SELECT t.*, p.name as project_name, a.name as area_name, a.color as area_color
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN areas a ON a.id = p.area_id
        WHERE 1=1
    '''
    params = []

    if status:
        query += ' AND t.status = ?'
        params.append(status)
    if priority:
        query += ' AND t.priority = ?'
        params.append(priority)

    query += '''
        ORDER BY
            CASE t.status
                WHEN 'in_progress' THEN 0
                WHEN 'todo' THEN 1
                WHEN 'backlog' THEN 2
                WHEN 'done' THEN 3
            END,
            CASE t.priority
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
            END
    '''

    cursor.execute(query, params)
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks


def get_task(task_id: str) -> Optional[dict]:
    """Get a single task by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.*, p.name as project_name, a.name as area_name
        FROM tasks t
        LEFT JOIN projects p ON p.id = t.project_id
        LEFT JOIN areas a ON a.id = p.area_id
        WHERE t.id = ?
    ''', (task_id,))

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_task(project_id: str, title: str, notes: str = '',
                status: str = 'backlog', priority: str = 'medium') -> dict:
    """Create a new task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Get max sort order
    cursor.execute('SELECT MAX(sort_order) FROM tasks WHERE project_id = ?', (project_id,))
    max_order = cursor.fetchone()[0] or 0

    task_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO tasks (id, project_id, title, notes, status, priority, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, project_id, title, notes, status, priority, max_order + 1, now, now))

    conn.commit()
    conn.close()

    return get_task(task_id)


def update_task(task_id: str, **kwargs) -> Optional[dict]:
    """Update a task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    allowed_fields = {'title', 'notes', 'status', 'priority', 'sort_order', 'project_id'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    updates['updated_at'] = now

    # Handle completion
    if kwargs.get('status') == 'done':
        updates['completed_at'] = now
    elif kwargs.get('status') and kwargs.get('status') != 'done':
        updates['completed_at'] = None

    if not updates:
        conn.close()
        return get_task(task_id)

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [task_id]

    cursor.execute(f'UPDATE tasks SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

    return get_task(task_id)


def delete_task(task_id: str) -> bool:
    """Delete a task."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def reorder_tasks(task_orders: list[dict]) -> bool:
    """Reorder tasks by updating sort_order and optionally status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    for order_info in task_orders:
        task_id = order_info.get('id')
        sort_order = order_info.get('order', 0)
        status = order_info.get('status')

        if status:
            completed_at = now if status == 'done' else None
            cursor.execute('''
                UPDATE tasks SET sort_order = ?, status = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
            ''', (sort_order, status, completed_at, now, task_id))
        else:
            cursor.execute('UPDATE tasks SET sort_order = ? WHERE id = ?', (sort_order, task_id))

    conn.commit()
    conn.close()
    return True


def reorder_areas(area_orders: list[dict]) -> bool:
    """Reorder areas by updating sort_order."""
    conn = get_db_connection()
    cursor = conn.cursor()

    for order_info in area_orders:
        area_id = order_info.get('id')
        sort_order = order_info.get('order', 0)
        cursor.execute('UPDATE areas SET sort_order = ? WHERE id = ?', (sort_order, area_id))

    conn.commit()
    conn.close()
    return True


def get_all_active_tasks() -> list[dict]:
    """Get all active tasks (todo/in_progress) across all projects, grouped by priority."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.*, p.name as project_name, a.name as area_name, a.color as area_color
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        JOIN areas a ON p.area_id = a.id
        WHERE t.status IN ('todo', 'in_progress')
        ORDER BY
            CASE t.status WHEN 'in_progress' THEN 0 ELSE 1 END,
            t.created_at DESC
    ''')

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Group by priority
    grouped = {
        'high': [t for t in tasks if t['priority'] == 'high'],
        'medium': [t for t in tasks if t['priority'] == 'medium'],
        'low': [t for t in tasks if t['priority'] == 'low']
    }
    return grouped


def get_active_tasks_by_area(area_id: str) -> dict:
    """Get all active tasks (todo/in_progress) for a specific area, grouped by priority."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT t.*, p.name as project_name, a.name as area_name, a.color as area_color
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        JOIN areas a ON p.area_id = a.id
        WHERE a.id = ?
        AND t.status IN ('todo', 'in_progress')
        ORDER BY
            CASE t.status WHEN 'in_progress' THEN 0 ELSE 1 END,
            t.created_at DESC
    ''', (area_id,))

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Group by priority
    grouped = {
        'high': [t for t in tasks if t['priority'] == 'high'],
        'medium': [t for t in tasks if t['priority'] == 'medium'],
        'low': [t for t in tasks if t['priority'] == 'low']
    }
    return grouped


# =============================================================================
# List Functions
# =============================================================================

def get_all_lists() -> list[dict]:
    """Get all personal lists with item counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT l.*,
               COUNT(li.id) as item_count,
               COUNT(CASE WHEN li.checked = 1 THEN 1 END) as checked_count
        FROM lists l
        LEFT JOIN list_items li ON li.list_id = l.id
        GROUP BY l.id
        ORDER BY l.sort_order, l.name
    ''')

    lists = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return lists


def get_list(list_id: str) -> Optional[dict]:
    """Get a single list by ID with its items."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM lists WHERE id = ?', (list_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    result = dict(row)

    cursor.execute('''
        SELECT * FROM list_items
        WHERE list_id = ?
        ORDER BY checked, sort_order
    ''', (list_id,))

    result['items'] = [dict(item) for item in cursor.fetchall()]
    conn.close()
    return result


def create_list(name: str, icon: str = 'list') -> dict:
    """Create a new personal list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Get max sort order
    cursor.execute('SELECT MAX(sort_order) FROM lists')
    max_order = cursor.fetchone()[0] or 0

    list_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO lists (id, name, icon, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (list_id, name, icon, max_order + 1, now))

    conn.commit()
    conn.close()

    return get_list(list_id)


def update_list(list_id: str, **kwargs) -> Optional[dict]:
    """Update a list."""
    conn = get_db_connection()
    cursor = conn.cursor()

    allowed_fields = {'name', 'icon', 'sort_order'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        conn.close()
        return get_list(list_id)

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [list_id]

    cursor.execute(f'UPDATE lists SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

    return get_list(list_id)


def delete_list(list_id: str) -> bool:
    """Delete a list and its items."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM lists WHERE id = ?', (list_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def add_list_item(list_id: str, content: str) -> dict:
    """Add an item to a list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Get max sort order
    cursor.execute('SELECT MAX(sort_order) FROM list_items WHERE list_id = ?', (list_id,))
    max_order = cursor.fetchone()[0] or 0

    item_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO list_items (id, list_id, content, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (item_id, list_id, content, max_order + 1, now))

    conn.commit()

    cursor.execute('SELECT * FROM list_items WHERE id = ?', (item_id,))
    item = dict(cursor.fetchone())
    conn.close()
    return item


def update_list_item(item_id: str, **kwargs) -> Optional[dict]:
    """Update a list item."""
    conn = get_db_connection()
    cursor = conn.cursor()

    allowed_fields = {'content', 'checked', 'sort_order'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        cursor.execute('SELECT * FROM list_items WHERE id = ?', (item_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [item_id]

    cursor.execute(f'UPDATE list_items SET {set_clause} WHERE id = ?', values)
    conn.commit()

    cursor.execute('SELECT * FROM list_items WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_list_item(item_id: str) -> bool:
    """Delete a list item."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM list_items WHERE id = ?', (item_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


# =============================================================================
# Stats Functions
# =============================================================================

def get_stats() -> dict:
    """Get overall project management statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Task stats
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'backlog' THEN 1 END) as backlog,
            COUNT(CASE WHEN status = 'todo' THEN 1 END) as todo,
            COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
            COUNT(CASE WHEN status = 'done' THEN 1 END) as done,
            COUNT(CASE WHEN priority = 'high' AND status != 'done' THEN 1 END) as high_priority
        FROM tasks
    ''')
    task_stats = dict(cursor.fetchone())

    # Project/area counts
    cursor.execute('SELECT COUNT(*) as count FROM areas')
    area_count = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) as count FROM projects')
    project_count = cursor.fetchone()['count']

    conn.close()

    return {
        'areas': area_count,
        'projects': project_count,
        'tasks': task_stats
    }


# =============================================================================
# Task Attachment Functions
# =============================================================================

def create_task_attachment(task_id: str, filename: str, original_name: str,
                           file_path: str, file_size: int = None,
                           mime_type: str = None) -> dict:
    """Create a new task attachment record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    attachment_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO task_attachments (id, task_id, filename, original_name, file_path, file_size, mime_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (attachment_id, task_id, filename, original_name, file_path, file_size, mime_type, now))

    conn.commit()
    conn.close()

    return get_task_attachment(attachment_id)


def get_task_attachment(attachment_id: str) -> Optional[dict]:
    """Get a single attachment by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM task_attachments WHERE id = ?', (attachment_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_task_attachments(task_id: str) -> list[dict]:
    """Get all attachments for a task."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM task_attachments
        WHERE task_id = ?
        ORDER BY created_at DESC
    ''', (task_id,))
    attachments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return attachments


def delete_task_attachment(attachment_id: str) -> Optional[dict]:
    """Delete an attachment and return its info (for file cleanup)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get attachment info first
    cursor.execute('SELECT * FROM task_attachments WHERE id = ?', (attachment_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    attachment = dict(row)

    # Delete from database
    cursor.execute('DELETE FROM task_attachments WHERE id = ?', (attachment_id,))
    conn.commit()
    conn.close()

    return attachment


def get_project_for_task(task_id: str) -> Optional[dict]:
    """Get the project associated with a task (for determining attachment storage path)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.* FROM projects p
        JOIN tasks t ON t.project_id = p.id
        WHERE t.id = ?
    ''', (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# SMS Allowlist Functions
# =============================================================================

def normalize_phone_number(phone: str) -> str:
    """Normalize phone number to E.164 format (+1XXXXXXXXXX)."""
    # Remove all non-digit characters
    digits = ''.join(c for c in phone if c.isdigit())

    # Handle US numbers
    if len(digits) == 10:
        return f'+1{digits}'
    elif len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    elif len(digits) > 10:
        return f'+{digits}'
    else:
        return f'+{digits}'


def add_to_sms_allowlist(phone_number: str, added_by: str = 'manual',
                          name: Optional[str] = None) -> dict:
    """Add a phone number to the SMS allowlist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    normalized = normalize_phone_number(phone_number)

    # Use INSERT OR REPLACE to handle duplicates
    cursor.execute('''
        INSERT OR REPLACE INTO sms_allowlist (phone_number, added_at, added_by, name)
        VALUES (?, ?, ?, ?)
    ''', (normalized, now, added_by, name))

    conn.commit()
    conn.close()

    return get_sms_allowlist_entry(normalized)


def get_sms_allowlist_entry(phone_number: str) -> Optional[dict]:
    """Get a single allowlist entry by phone number."""
    conn = get_db_connection()
    cursor = conn.cursor()

    normalized = normalize_phone_number(phone_number)
    cursor.execute('SELECT * FROM sms_allowlist WHERE phone_number = ?', (normalized,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def is_phone_allowed(phone_number: str) -> bool:
    """Check if a phone number is on the allowlist."""
    return get_sms_allowlist_entry(phone_number) is not None


def get_sms_allowlist() -> list[dict]:
    """Get all allowlist entries."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM sms_allowlist ORDER BY added_at DESC')
    entries = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return entries


def remove_from_sms_allowlist(phone_number: str) -> bool:
    """Remove a phone number from the allowlist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    normalized = normalize_phone_number(phone_number)
    cursor.execute('DELETE FROM sms_allowlist WHERE phone_number = ?', (normalized,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def update_sms_allowlist_name(phone_number: str, name: str) -> Optional[dict]:
    """Update the name for an allowlist entry."""
    conn = get_db_connection()
    cursor = conn.cursor()

    normalized = normalize_phone_number(phone_number)
    cursor.execute('UPDATE sms_allowlist SET name = ? WHERE phone_number = ?',
                   (name, normalized))

    conn.commit()
    conn.close()

    return get_sms_allowlist_entry(normalized)


# =============================================================================
# SMS Conversation Functions
# =============================================================================

def log_sms_message(phone_number: str, direction: str, message: str,
                    twilio_sid: Optional[str] = None) -> dict:
    """Log an SMS message to the conversation history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    normalized = normalize_phone_number(phone_number)
    msg_id = str(uuid.uuid4())

    cursor.execute('''
        INSERT INTO sms_conversations (id, phone_number, direction, message, timestamp, twilio_sid)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (msg_id, normalized, direction, message, now, twilio_sid))

    conn.commit()
    conn.close()

    return {
        'id': msg_id,
        'phone_number': normalized,
        'direction': direction,
        'message': message,
        'timestamp': now,
        'twilio_sid': twilio_sid
    }


def get_sms_conversation(phone_number: str, limit: int = 50) -> list[dict]:
    """Get conversation history for a phone number."""
    conn = get_db_connection()
    cursor = conn.cursor()

    normalized = normalize_phone_number(phone_number)
    cursor.execute('''
        SELECT * FROM sms_conversations
        WHERE phone_number = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (normalized, limit))

    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Return in chronological order
    return list(reversed(messages))


def get_recent_sms_messages(limit: int = 100) -> list[dict]:
    """Get recent SMS messages across all conversations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.*, a.name as contact_name
        FROM sms_conversations c
        LEFT JOIN sms_allowlist a ON c.phone_number = a.phone_number
        ORDER BY c.timestamp DESC
        LIMIT ?
    ''', (limit,))

    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return messages


# Initialize database on import
init_database()
