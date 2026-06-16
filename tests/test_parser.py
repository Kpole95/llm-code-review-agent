from src.parsing.code_parser import parse_file

SAMPLE_PY = '''
import os

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
'''


def test_parse_python_functions():
    parsed = parse_file(SAMPLE_PY, "python")
    names = [f.name for f in parsed.functions]
    assert "add" in names
    assert "subtract" in names
    assert parsed.imports  # at least one import found
    assert parsed.loc == len(SAMPLE_PY.splitlines())