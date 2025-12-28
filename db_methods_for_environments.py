# =============================================================================
# Add these methods to your controller/db/db.py OrchestrationDB class
# =============================================================================

def get_user_environments(self, user_id: int) -> list:
    """
    Get list of environments a user can access.
    Returns list like ['DEV', 'TEST'] or ['*'] for all access.
    """
    cursor = self.conn.cursor()
    cursor.execute(
        "SELECT environment FROM user_agent_access WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    return [row[0] for row in rows] if rows else []


def get_user_by_username(self, username: str) -> dict:
    """Get user record by username"""
    cursor = self.conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    )
    row = cursor.fetchone()
    if row:
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
    return None


# =============================================================================
# SQL to create the user_agent_access table (run once)
# =============================================================================
"""
CREATE TABLE IF NOT EXISTS user_agent_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    environment VARCHAR(10) NOT NULL,  -- 'DEV', 'TEST', 'PROD', or '*' for all
    granted_by VARCHAR(255),
    granted_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(user_id, environment)
);

-- Grant all access to existing admins
INSERT OR IGNORE INTO user_agent_access (user_id, environment, granted_by)
SELECT user_id, '*', 'system_migration' 
FROM users 
WHERE role = 'admin';
"""
