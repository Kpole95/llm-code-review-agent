import os
import sqlite3
from contextlib import closing
 
 
def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a user record safely using parameterized query."""
    db_path = os.getenv("DATABASE_PATH", "app.db")
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "email": row[2]}
