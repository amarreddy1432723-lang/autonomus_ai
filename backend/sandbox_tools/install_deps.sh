#!/usr/bin/env bash
set -u

redact() {
  sed -E 's/(sk-[A-Za-z0-9_-]+)/[REDACTED]/g; s/(Bearer[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig; s/((password|token|secret)=)[^[:space:]]+/\1[REDACTED]/Ig'
}

run_install() {
  local label="$1"
  shift
  echo "==> ${label}"
  timeout "${SANDBOX_INSTALL_TIMEOUT:-300}" "$@" 2>&1 | redact
  local code=${PIPESTATUS[0]}
  echo "<== ${label} exited ${code}"
  return "${code}"
}

status=0

if [ -f package-lock.json ]; then
  run_install "npm ci" npm ci || status=$?
elif [ -f package.json ]; then
  run_install "npm install" npm install || status=$?
fi

if [ -f requirements.txt ]; then
  run_install "pip install requirements" python -m pip install -r requirements.txt || status=$?
fi

if [ "${status}" -ne 0 ]; then
  echo "Dependency install failed. If this is a network error, enable SANDBOX_ALLOW_NETWORK only for approved install jobs."
fi

exit "${status}"
