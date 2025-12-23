# =============================================================================
# Add these methods to your db.py class
# =============================================================================

def get_user_environments(self, user_id: int) -> list:
    """
    Get list of environments a user can access.
    Returns list like ['DEV', 'TEST'] or ['*'] for superadmin.
    """
    query = """
        SELECT environment 
        FROM user_agent_access 
        WHERE user_id = ?
    """
    rows = self.query(query, (user_id,))
    return [row['environment'] for row in rows] if rows else []


def get_user_by_username(self, username: str) -> dict:
    """Get user record by username"""
    query = "SELECT * FROM users WHERE username = ?"
    rows = self.query(query, (username,))
    return rows[0] if rows else None


def update_agent_environment(self, agent_name: str, environment: str):
    """Update an agent's environment"""
    self.execute(
        "UPDATE agents SET environment = ? WHERE agent_name = ?",
        (environment.upper(), agent_name)
    )


def register_agent(self, agent_name: str, host: str, port: int, 
                   status: str = "online", ssl_enabled: bool = True,
                   environment: str = "DEV"):
    """Register or update an agent with environment support"""
    query = """
        INSERT INTO agents (agent_name, host, port, status, ssl_enabled, environment, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(agent_name) DO UPDATE SET
            host = excluded.host,
            port = excluded.port,
            status = excluded.status,
            ssl_enabled = excluded.ssl_enabled,
            environment = excluded.environment,
            last_seen = datetime('now')
    """
    self.execute(query, (agent_name, host, port, status, ssl_enabled, environment.upper()))
    return self.get_agent(agent_name)


# =============================================================================
# Alternative: If your db.py uses a different pattern, here's raw SQL approach
# =============================================================================

"""
If your db.py doesn't have query() and execute() methods, use these raw SQL 
statements in agents.py instead:

import sqlite3

def get_user_environments_raw(db_path: str, user_id: int) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT environment FROM user_agent_access WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['environment'] for row in rows] if rows else []
"""
