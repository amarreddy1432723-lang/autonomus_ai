import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
from fastapi import HTTPException
from openai import OpenAI
from .config import settings

def _training_data_path(filename: str) -> Path:
    root = Path(__file__).resolve().parents[3]
    path = root / "training" / "data" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def get_openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY or "mock-key" in settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API Key is not configured. Please set a valid OPENAI_API_KEY to train the model."
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY)

def prepare_openai_finetune_dataset() -> Path:
    candidate_path = _training_data_path("candidate_examples.jsonl")
    train_path = _training_data_path("train_openai.jsonl")

    if not candidate_path.exists():
        raise HTTPException(status_code=404, detail="No training candidate examples found. Click 'Train Autonomus' on answers first.")

    approved_records = []
    with candidate_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                # Filter for approved examples
                if record.get("quality_status") == "approved":
                    approved_records.append(record)
            except Exception:
                continue

    if len(approved_records) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"OpenAI requires at least 10 training examples. Currently found only {len(approved_records)} approved examples."
        )

    # Format into OpenAI conversation format
    with train_path.open("w", encoding="utf-8") as out:
        for rec in approved_records:
            system_content = "You are Autonomus AI, the user's unified personal AI model and learning agent."
            goal = rec.get("goal_context")
            if goal:
                system_content += f"\nActive Goal: {goal.get('title', '')} - {goal.get('description', '')}"

            user_msg = rec.get("user_request", "").strip()
            # If user provided a correction, train on that as the target response!
            assistant_msg = rec.get("user_correction", "").strip() or rec.get("assistant_response", "").strip()

            conversation = {
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg}
                ]
            }
            out.write(json.dumps(conversation, ensure_ascii=True) + "\n")

    return train_path

def start_self_training_job() -> Dict[str, Any]:
    dataset_path = prepare_openai_finetune_dataset()
    client = get_openai_client()

    # 1. Upload dataset file to OpenAI
    try:
        with dataset_path.open("rb") as file_data:
            uploaded_file = client.files.create(
                file=file_data,
                purpose="fine-tune"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload training dataset to OpenAI: {str(e)}")

    # 2. Trigger the Fine-Tuning Job
    try:
        job = client.fine_tuning.jobs.create(
            training_file=uploaded_file.id,
            model="gpt-4o-mini-2024-07-18",
            hyperparameters={"n_epochs": 3}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create OpenAI fine-tuning job: {str(e)}")

    # Save job details to state/history
    job_record = {
        "job_id": job.id,
        "status": job.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": job.model,
        "fine_tuned_model": job.fine_tuned_model,
        "training_file_id": uploaded_file.id,
    }
    history_path = _training_data_path("finetune_jobs.jsonl")
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(job_record) + "\n")

    return job_record

def list_self_training_jobs() -> List[Dict[str, Any]]:
    history_path = _training_data_path("finetune_jobs.jsonl")
    if not history_path.exists():
        return []

    jobs = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    jobs.append(json.loads(line))
                except Exception:
                    continue
    return jobs

def sync_job_statuses() -> List[Dict[str, Any]]:
    jobs = list_self_training_jobs()
    if not jobs:
        return []

    client = None
    try:
        client = get_openai_client()
    except Exception:
        return jobs  # Cannot sync without client

    updated_jobs = []
    changed = False
    for job in jobs:
        # Only query OpenAI for running jobs
        if job["status"] not in {"succeeded", "failed", "cancelled"}:
            try:
                remote_job = client.fine_tuning.jobs.retrieve(job["job_id"])
                job["status"] = remote_job.status
                job["fine_tuned_model"] = remote_job.fine_tuned_model
                changed = True
            except Exception:
                pass
        updated_jobs.append(job)

    if changed:
        history_path = _training_data_path("finetune_jobs.jsonl")
        with history_path.open("w", encoding="utf-8") as handle:
            for job in updated_jobs:
                handle.write(json.dumps(job) + "\n")

        # If a job succeeded, update the active fine-tuned model setting!
        succeeded = [j for j in updated_jobs if j["status"] == "succeeded"]
        if succeeded:
            # Sort by date, get the latest fine-tuned model ID
            latest_model = sorted(succeeded, key=lambda x: x["created_at"])[-1]["fine_tuned_model"]
            if latest_model:
                _save_active_finetuned_model(latest_model)

    return updated_jobs

def _save_active_finetuned_model(model_name: str):
    config_path = _training_data_path("active_model.json")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump({"active_finetuned_model": model_name}, handle)

def get_active_finetuned_model() -> str | None:
    config_path = _training_data_path("active_model.json")
    if config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data.get("active_finetuned_model")
        except Exception:
            return None
    return None
