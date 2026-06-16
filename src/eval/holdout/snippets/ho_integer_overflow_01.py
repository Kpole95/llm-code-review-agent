def calculate_discount(price, discount_percent):
    discount = price * discount_percent / 100
    final_price = price - discount
    # No validation: discount_percent could be >100, giving negative price
    if final_price > 0:
        return int(final_price)
    return 0
 
 
def apply_bulk_discount(items, discount):
    total = 0
    for item in items:
        total += calculate_discount(item["price"], discount)
    return total
