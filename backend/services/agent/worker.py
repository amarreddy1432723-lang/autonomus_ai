import os
import time
import logging
import threading
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from services.shared.database import SessionLocal
from services.shared.models import AgentJob
from services.agent.config import settings
from services.agent.agent_jobs import append_job_log, complete_job
from services.agent.code_workspace import generate_patch, generate_plan, get_code_session
from services.agent.usage import record_usage

logger = logging.getLogger("nexus-worker")

def datetime_now() -> datetime:
    return datetime.now(timezone.utc)

class AgentWorkerQueue:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
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
                # Find the oldest queued job
                job = db.query(AgentJob).filter(
                    AgentJob.status == "queued"
                ).order_by(AgentJob.created_at.asc()).first()
                
                if job:
                    # Mark job as running
                    job.status = "running"
                    job.started_at = datetime_now()
                    db.commit()
                    db.refresh(job)
                    
                    logger.info(f"Processing background job {job.id} (mode: {job.mode})")
                    self._execute_job(db, job)
                else:
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Worker queue loop error: {e}")
                time.sleep(2.0)
            finally:
                db.close()

    def _execute_job(self, db: Session, job: AgentJob):
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
            
            plan = generate_plan(db, user_uuid, session, job.prompt, provider, model, job, finalize_job=False)
            
            patch = ""
            preview = []
            if run_patch:
                append_job_log(db, job, "edit", "Background patch started", "Patch will remain pending until reviewed.")
                patch = generate_patch(db, user_uuid, session, job.prompt, provider, model, job, finalize_job=False)
                preview = (session.metadata_json or {}).get("patch_preview") or []
                
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
            complete_job(db, job, "failed", {"error": str(e)})

# Global worker queue instance
worker_queue = AgentWorkerQueue()
