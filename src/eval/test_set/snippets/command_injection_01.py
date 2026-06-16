import os
 
 
def ping_host(hostname):
    # User input passed directly to a shell command
    os.system("ping -c 1 " + hostname)
