import pytest
from services.agent.diagnostics import parse_diagnostics

def test_parse_typescript_diagnostics():
    raw_output = "src/index.ts(12,34): error TS2304: Cannot find name 'foo'.\nsrc/app.tsx(5,10): warning TS2552: Cannot find name 'bar'.\n"
    diags = parse_diagnostics(raw_output)
    
    assert len(diags) == 2
    assert diags[0]["file"] == "src/index.ts"
    assert diags[0]["line"] == 12
    assert diags[0]["column"] == 34
    assert diags[0]["severity"] == "error"
    assert "Cannot find name 'foo'" in diags[0]["message"]
    
    assert diags[1]["file"] == "src/app.tsx"
    assert diags[1]["line"] == 5
    assert diags[1]["column"] == 10
    assert diags[1]["severity"] == "warning"

def test_parse_python_flake8_diagnostics():
    raw_output = "src/main.py:10:5: E225 missing whitespace around operator\n"
    diags = parse_diagnostics(raw_output)
    
    assert len(diags) == 1
    assert diags[0]["file"] == "src/main.py"
    assert diags[0]["line"] == 10
    assert diags[0]["column"] == 5
    assert diags[0]["severity"] == "error"  # default mapping for code patterns without error word
    assert "E225 missing" in diags[0]["message"]
