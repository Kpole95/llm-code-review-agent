import pickle
 
 
def load_session(data):
    # Unpickling untrusted data can execute arbitrary code
    return pickle.loads(data)
