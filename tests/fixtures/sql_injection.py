"""Deliberately vulnerable file — used to test bug_detector."""
import sqlite3


def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # BUG: SQL injection — user_id is concatenated directly into the query.
    query = "SELECT * FROM users WHERE id=" + user_id
    cur.execute(query)
    return cur.fetchone()


def safe_divide(a, b):
    # BUG: bare except swallows the ZeroDivisionError silently.
    try:
        return a / b
    except:
        pass