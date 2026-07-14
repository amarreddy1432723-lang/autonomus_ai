#!/usr/bin/env bash
set -u

redact() {
  sed -E 's/(sk-[A-Za-z0-9_-]+)/[REDACTED]/g; s/(Bearer[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig; s/((password|token|secret)=)[^[:space:]]+/\1[REDACTED]/Ig'
}

run_step() {
  local label="$1"
  shift
  echo "==> ${label}"
  timeout "${SANDBOX_COMMAND_TIMEOUT:-120}" "$@" 2>&1 | redact
  local code=${PIPESTATUS[0]}
  echo "<== ${label} exited ${code}"
  return "${code}"
}

status=0

if [ "$#" -gt 0 ]; then
  run_step "custom check" "$@"
  exit $?
fi

if [ -f package.json ]; then
  for script in build typecheck lint test; do
    if node -e "const p=require('./package.json'); process.exit(p.scripts && p.scripts['${script}'] ? 0 : 1)" >/dev/null 2>&1; then
      run_step "npm run ${script}" npm run "${script}" || status=$?
    fi
  done
fi

if [ -f pyproject.toml ] || [ -d tests ]; then
  run_step "python -m pytest" python -m pytest || status=$?
fi

if [ "${status}" -eq 0 ]; then
  echo "All discovered checks completed."
fi

exit "${status}"
