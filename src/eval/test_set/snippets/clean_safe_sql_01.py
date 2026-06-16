import sqlite3
 
 
def find_user(user_id):
    conn = sqlite3.connect("app.db")
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()
