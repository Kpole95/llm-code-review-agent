import os
 
 
def get_api_client():
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise RuntimeError("API_KEY environment variable is not set")
    return {"key": api_key}
