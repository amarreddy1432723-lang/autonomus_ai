import re
import logging
from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from services.shared.models import CodeSession
from services.agent.code_workspace import get_code_session, get_session_sandbox, discover_workspace_commands, sync_workspace_runtime

logger = logging.getLogger("nexus-diagnostics")

# Standard patterns for compiler/linter error output parsing
PATTERNS = [
    # Match: src/file.ts(12,34): error TS2304: Cannot find name 'foo'.
    re.compile(r"^([^(]+)\((\d+),(\d+)\):\s*(error|warning)\s*(.*)$", re.IGNORECASE),
    # Match: src/file.py:12:34: E302 expected 2 blank lines
    re.compile(r"^([^:]+):(\d+):(\d+):\s*(error|warning|info)?\s*(.*)$", re.IGNORECASE),
    # Match: src/file.py:12: error: message
    re.compile(r"^([^:]+):(\d+):\s*(error|warning|info):\s*(.*)$", re.IGNORECASE),
]

def parse_diagnostics(output: str) -> List[Dict[str, Any]]:
    """Parse raw compiler/linter stdout/stderr logs into structured diagnostics."""
    diagnostics = []
    if not output:
        return diagnostics

    for line in output.splitlines():
        line = line.strip()
        matched = False
        for pattern in PATTERNS:
            match = pattern.match(line)
            if match:
                groups = match.groups()
                # Determine fields based on matched group length
                if len(groups) == 5:
                    file_path, line_no, col_no, severity, message = groups
                elif len(groups) == 4:
                    file_path, line_no, severity, message = groups
                    col_no = "1"
                else:
                    continue

                # Clean up severity
                sev = severity.lower() if severity else "error"
                if "warn" in sev:
                    sev = "warning"
                elif "info" in sev or "hint" in sev:
                    sev = "info"
                else:
                    sev = "error"

                diagnostics.append({
                    "file": file_path.strip(),
                    "line": int(line_no),
                    "column": int(col_no) if col_no.isdigit() else 1,
                    "severity": sev,
                    "message": message.strip()
                })
                matched = True
                break
        
        # Fallback keyword scan if not matched by structured regex
        if not matched and ("error:" in line.lower() or "warning:" in line.lower() or "failed:" in line.lower()):
            diagnostics.append({
                "file": "unknown",
                "line": 1,
                "column": 1,
                "severity": "error" if "error" in line.lower() or "failed" in line.lower() else "warning",
                "message": line
            })

    return diagnostics[:200]  # Cap to prevent overwhelming the Monaco editor

def run_diagnostics_checks(db: Session, user_id: UUID, session: CodeSession) -> List[Dict[str, Any]]:
    """Runs compiler, linter, or syntax checks in the workspace sandbox and compiles diagnostics."""
    discovered = discover_workspace_commands(db, user_id, session).get("commands") or []
    
    # Filter for lint, typecheck, compile, or build commands
    check_commands = []
    for item in discovered:
        label = str(item.get("label") or "").lower()
        command = str(item.get("command") or "").strip()
        if command and any(kw in label or kw in command for kw in ["lint", "typecheck", "tsc", "flake8", "eslint"]):
            check_commands.append(command)

    # Fallback default linter command if none discovered
    if not check_commands:
        # Check files to guess language
        runtime = sync_workspace_runtime(db, user_id, session)
        has_js = any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in runtime.get("files_written", []))
        if has_js:
            check_commands.append("npm run lint")
        else:
            check_commands.append("flake8 .")

    sandbox = get_session_sandbox(session)
    all_diagnostics = []

    # Run check commands inside sandbox and aggregate markers
    for cmd in check_commands[:2]:  # Limit to max 2 check scripts
        try:
            res = sandbox.run_command(cmd, timeout=30)
            parsed = parse_diagnostics(res.get("output") or "")
            # Fill command label context into diagnostics if they don't have file paths
            for diag in parsed:
                diag["source"] = cmd
            all_diagnostics.extend(parsed)
        except Exception as e:
            logger.error(f"Diagnostics runner command '{cmd}' failed: {e}")

    return all_diagnostics
