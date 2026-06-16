"""User lookup module."""
import sqlite3


def find_user_by_email(email):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # BUG: SQL injection via string formatting.
    query = f"SELECT * FROM users WHERE email='{email}'"
    cur.execute(query)
    return cur.fetchone()