def get_status_code(response):
    if response.status == "ok":
        return 200
        return 201  # unreachable
    elif response.status == "error":
        return 500
    return 404
