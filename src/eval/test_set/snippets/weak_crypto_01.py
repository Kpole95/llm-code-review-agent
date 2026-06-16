import hashlib
 
 
def hash_password(password):
    # MD5 is cryptographically broken for password hashing
    return hashlib.md5(password.encode()).hexdigest()
