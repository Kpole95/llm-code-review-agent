import sqlite3
 
DB_PASSWORD = "admin123supersecret"
 
 
def get_user(user_id):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = '%s'" % user_id)
    return cur.fetchone()
