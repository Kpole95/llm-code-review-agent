STRIPE_SECRET_KEY = "sk_live_51Hcd9f00000000000000000000000"
 
 
def charge_card(token, amount):
    return {"token": token, "amount": amount, "key": STRIPE_SECRET_KEY}
