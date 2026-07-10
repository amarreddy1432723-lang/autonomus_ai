import os
import time
import logging
import threading
import socket
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from services.shared.database import SessionLocal
from services.shared.models import AgentJob
from services.agent.config import settings
from services.agent.agent_jobs import append_job_log, complete_job, heartbeat_job, update_job_metadata
from services.agent.code_workspace import generate_patch, generate_plan, get_code_session
from services.agent.usage import record_usage

logger = logging.getLogger("nexus-worker")

def datetime_now() -> datetime:
    return datetime.now(timezone.utc)

class AgentWorkerQueue:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"

    def start(self):
        if not settings.AGENT_WORKER_ENABLED:
            logger.info("Agent background worker queue disabled by AGENT_WORKER_ENABLED=false.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="nexus-agent-worker")
        self._thread.start()
        logger.info("Agent background worker queue started.")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("Agent background worker queue stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            db = SessionLocal()
            try:
                self._mark_timed_out_jobs(db)
                # Find the oldest queued job
                job = db.query(AgentJob).filter(
                    AgentJob.status == "queued"
                ).order_by(AgentJob.created_at.asc()).first()
                
                if job:
                    # Mark job as running
                    job.status = "running"
                    job.started_at = datetime_now()
                    metadata = dict(job.metadata_json or {})
                    metadata["worker_id"] = self.worker_id
                    metadata["heartbeat_at"] = datetime_now().isoformat()
                    metadata["progress"] = {
                        "stage": "starting",
                        "detail": "Worker claimed the job.",
                        "percent": 5,
                        "updated_at": datetime_now().isoformat(),
                    }
                    job.metadata_json = metadata
                    db.commit()
                    db.refresh(job)
                    
                    logger.info(f"Processing background job {job.id} (mode: {job.mode})")
                    self._execute_job(db, job)
                else:
                    time.sleep(settings.AGENT_WORKER_POLL_SECONDS)
            except Exception as e:
                logger.error(f"Worker queue loop error: {e}")
                time.sleep(2.0)
            finally:
                db.close()

    def _mark_timed_out_jobs(self, db: Session) -> None:
        timeout_cutoff = datetime_now() - timedelta(seconds=settings.AGENT_JOB_TIMEOUT_SECONDS)
        stale_cutoff = datetime_now() - timedelta(seconds=settings.AGENT_JOB_STALE_SECONDS)
        jobs = (
            db.query(AgentJob)
            .filter(AgentJob.status == "running")
            .filter(AgentJob.started_at.isnot(None))
            .filter(AgentJob.started_at < timeout_cutoff)
            .limit(20)
            .all()
        )
        for job in jobs:
            metadata = dict(job.metadata_json or {})
            heartbeat_raw = metadata.get("heartbeat_at")
            heartbeat_at = None
            if heartbeat_raw:
                try:
                    heartbeat_at = datetime.fromisoformat(str(heartbeat_raw))
                    if heartbeat_at.tzinfo is None:
                        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    heartbeat_at = None
            if heartbeat_at and heartbeat_at > stale_cutoff:
                continue
            complete_job(db, job, "timeout", {
                "error": "Job exceeded runtime or heartbeat timeout.",
                "worker_id": metadata.get("worker_id"),
            })

    def _execute_job(self, db: Session, job: AgentJob):
        started = time.monotonic()
        try:
            user_uuid = job.user_id
            session_uuid = job.code_session_id
            
            # Resolve code session
            session = get_code_session(db, user_uuid, session_uuid)
            
            # Extract info from mode / prompt
            mode_type = job.mode.replace("background_", "")  # "plan" or "code"
            run_patch = (mode_type == "code")
            
            # Parse provider / model from metadata
            meta = job.metadata_json or {}
            provider = meta.get("llm_provider") or settings.LLM_PROVIDER
            model = meta.get("llm_model") or settings.LLM_MODEL
            
            append_job_log(db, job, "code", "Background task pick up", f"Running {mode_type} via {provider}/{model}")
            heartbeat_job(db, job, "planning", "Generating implementation plan.", 20)
            
            plan = generate_plan(db, user_uuid, session, job.prompt, provider, model, job, finalize_job=False)
            if time.monotonic() - started > settings.AGENT_JOB_TIMEOUT_SECONDS:
                complete_job(db, job, "timeout", {"error": "Job timed out after planning."})
                return
            
            patch = ""
            preview = []
            if run_patch:
                append_job_log(db, job, "edit", "Background patch started", "Patch will remain pending until reviewed.")
                heartbeat_job(db, job, "patching", "Generating reviewable patch.", 55)
                patch = generate_patch(db, user_uuid, session, job.prompt, provider, model, job, finalize_job=False)
                preview = (session.metadata_json or {}).get("patch_preview") or []
            heartbeat_job(db, job, "finalizing", "Recording result and usage.", 90)
                
            result = {
                "plan": plan,
                "patch": patch,
                "patch_preview": preview,
                "summary": (session.metadata_json or {}).get("patch_summary") or "",
            }
            
            record_usage(db, user_uuid, "/api/v1/code/background-run", provider, model, str(session_uuid), job.prompt, "\n".join([plan, patch]), session.file_ids)
            
            complete_job(
                db,
                job,
                "completed",
                result,
                files_touched=[{"file_id": item["file_id"], "filename": item["filename"]} for item in preview],
                approval_state="pending" if preview else "none",
            )
        except Exception as e:
            logger.error(f"Error executing job {job.id}: {e}")
            update_job_metadata(db, job, {"heartbeat_at": datetime_now().isoformat()})
            complete_job(db, job, "failed", {"error": str(e)})

    def status(self) -> dict:
        return {
            "enabled": bool(settings.AGENT_WORKER_ENABLED),
            "alive": bool(self._thread and self._thread.is_alive()),
            "worker_id": self.worker_id,
            "poll_seconds": settings.AGENT_WORKER_POLL_SECONDS,
            "job_timeout_seconds": settings.AGENT_JOB_TIMEOUT_SECONDS,
            "job_stale_seconds": settings.AGENT_JOB_STALE_SECONDS,
            "max_retries": settings.AGENT_JOB_MAX_RETRIES,
        }

# Global worker queue instance
worker_queue = AgentWorkerQueue()
