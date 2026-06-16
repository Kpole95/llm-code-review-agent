import jwt
 
JWT_SECRET = "my_super_secret_jwt_key_do_not_share"
 
 
def create_token(user_id):
    payload = {"user_id": user_id}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
 
 
def verify_token(token):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
