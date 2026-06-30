import argparse
import json
from pathlib import Path


def score_example(example: dict) -> dict:
    assistant = example.get("assistant", "")
    user = example.get("user", "")
    issues = []
    if "Autonomus AI" not in example.get("system", ""):
        issues.append("system_identity_missing")
    if len(assistant) < 80:
        issues.append("assistant_too_short")
    image_url_is_input = "image url:" in user.lower() or "http" in user.lower()
    if "image" in user.lower() and not image_url_is_input and "http" not in assistant and "![" not in assistant:
        issues.append("image_request_without_media_or_url")
    if "web_search{" in assistant:
        issues.append("malformed_tool_call_text")
    return {"issues": issues, "passed": not issues}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run simple quality gates over Autonomus AI data.")
    parser.add_argument("--input", default="training/data/train.jsonl")
    args = parser.parse_args()

    path = Path(args.input)
    total = 0
    failed = []
    with path.open("r", encoding="utf-8") as source:
        for index, line in enumerate(source, start=1):
            if not line.strip():
                continue
            total += 1
            result = score_example(json.loads(line))
            if not result["passed"]:
                failed.append({"line": index, "issues": result["issues"]})

    print(json.dumps({"total": total, "passed": total - len(failed), "failed": failed}, indent=2))


if __name__ == "__main__":
    main()
