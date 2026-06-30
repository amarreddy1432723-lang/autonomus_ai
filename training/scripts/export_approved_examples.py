import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CANDIDATES = DATA_DIR / "candidate_examples.jsonl"
OUTPUT = DATA_DIR / "approved_from_chat.jsonl"


SYSTEM_PROMPT = (
    "You are Autonomus AI, a clear, careful personal learning agent. "
    "Use goal context when provided, teach step by step, and avoid malformed tool calls."
)


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    exported = 0
    with OUTPUT.open("w", encoding="utf-8") as output:
        for record in iter_jsonl(CANDIDATES) or []:
            if record.get("quality_status") != "approved":
                continue
            user_request = (record.get("user_request") or "").strip()
            assistant_response = (record.get("assistant_response") or "").strip()
            if not user_request or not assistant_response:
                continue
            example = {
                "system": SYSTEM_PROMPT,
                "user": user_request,
                "assistant": assistant_response,
                "metadata": {
                    "domain": "chat_approved",
                    "quality_score": 0.95,
                    "source": record.get("source") or "chat_manual_approval",
                    "selected_model": record.get("selected_model") or {},
                    "goal_context": record.get("goal_context") or {},
                    "media_urls": record.get("media_urls") or [],
                    "captured_at": record.get("captured_at"),
                },
            }
            output.write(json.dumps(example, ensure_ascii=True) + "\n")
            exported += 1

    print(f"Exported {exported} approved examples to {OUTPUT}")


if __name__ == "__main__":
    main()
