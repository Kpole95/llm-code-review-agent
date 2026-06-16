import sqlite3
 
 
def find_order(order_id):
    conn = sqlite3.connect("orders.db")
    cur = conn.cursor()
    query = "SELECT * FROM orders WHERE id=" + order_id
    cur.execute(query)
    return cur.fetchone()