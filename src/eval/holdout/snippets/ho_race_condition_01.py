import os
 
 
def save_user_file(username, content):
    filepath = f"/uploads/{username}/data.txt"
    # TOCTOU: check then act - another process can create the file between
    # the check and the write
    if not os.path.exists(filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)
        return True
    return False
