from __future__ import annotations

import os

from celery import Celery


def _redis_url() -> str:
    return os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"


def _result_url() -> str:
    return os.getenv("CELERY_RESULT_BACKEND") or "redis://localhost:6379/1"


celery_app = Celery(
    "arceus_worker",
    broker=_redis_url(),
    backend=_result_url(),
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="agent_tasks",
    task_routes={
        "worker.tasks.run_agent_task": {"queue": "agent_tasks"},
        "worker.tasks.run_workspace_checks": {"queue": "checks_queue"},
        "worker.tasks.run_install_deps": {"queue": "install_queue"},
        "worker.tasks.run_preview_check": {"queue": "checks_queue"},
        "worker.tasks.recover_stale_jobs": {"queue": "agent_tasks"},
    },
    beat_schedule={
        "recover-stale-agent-jobs": {
            "task": "worker.tasks.recover_stale_jobs",
            "schedule": 300.0,
        },
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
