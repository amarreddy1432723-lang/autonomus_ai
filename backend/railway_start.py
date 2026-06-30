import os
import subprocess
import sys

import uvicorn


SERVICE_APPS = {
    "auth": "services.auth.main:app",
    "goals": "services.goals.main:app",
    "agent": "services.agent.main:app",
}


def main() -> None:
    service = os.getenv("APP_SERVICE", "agent").lower()
    app = SERVICE_APPS.get(service)
    if not app:
        raise SystemExit(f"Unsupported APP_SERVICE={service!r}. Use one of: {', '.join(SERVICE_APPS)}")

    if service == "auth" and os.getenv("RUN_MIGRATIONS", "true").lower() in {"1", "true", "yes", "on"}:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
