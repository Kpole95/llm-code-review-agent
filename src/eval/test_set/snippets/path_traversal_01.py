def read_user_file(filename):
    # No validation — user could pass ../../etc/passwd
    with open("/var/data/" + filename) as f:
        return f.read()
