import pytest
from services.agent.code_workspace import parse_diff_to_hunks, apply_hunks_to_file

def test_parse_diff_to_hunks():
    # Make edits far apart so difflib with default n=3 splits them into separate hunks
    old_lines = [f"line {i}" for i in range(1, 30)]
    old_text = "\n".join(old_lines) + "\n"
    
    new_lines = list(old_lines)
    new_lines[1] = "new line 2"      # edit 1 (index 1, line 2)
    new_lines[25] = "new line 26"    # edit 2 (index 25, line 26)
    new_text = "\n".join(new_lines) + "\n"
    
    hunks = parse_diff_to_hunks(old_text, new_text)
    assert len(hunks) == 2
    
    hunk0 = hunks[0]
    assert hunk0["old_start"] == 1
    assert "new line 2" in hunk0["new_lines"]
    
    hunk1 = hunks[1]
    assert hunk1["old_start"] == 23
    assert "new line 26" in hunk1["new_lines"]
    
def test_apply_hunks_with_rejections():
    old_lines = [f"line {i}" for i in range(1, 30)]
    old_text = "\n".join(old_lines) + "\n"
    
    new_lines = list(old_lines)
    new_lines[1] = "new line 2"
    new_lines[25] = "new line 26"
    new_text = "\n".join(new_lines) + "\n"
    
    hunks = parse_diff_to_hunks(old_text, new_text)
    # Reject the second hunk (which changes line 26)
    hunks[1]["status"] = "rejected"
    
    applied = apply_hunks_to_file(old_text, hunks)
    
    # The applied text should have edit 1 (new line 2) but keep original line 26
    applied_lines = applied.splitlines()
    assert applied_lines[1] == "new line 2"
    assert applied_lines[25] == "line 26"
