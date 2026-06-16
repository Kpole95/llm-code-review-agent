import sqlite3
 
 
def search_products(category, max_price):
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    query = "SELECT * FROM products WHERE category='%s' AND price < %s" % (
        category,
        max_price,
    )
    cur.execute(query)
    results = cur.fetchall()
    conn.close()
    return results
