def calculate(expression):
    # Dangerous: executes arbitrary user input as Python code
    return eval(expression)
